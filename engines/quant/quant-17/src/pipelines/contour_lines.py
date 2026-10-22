"""Width-constant contour pipeline: the drawn-look line layer.

The character's contour network is a stroke of near-constant width; modeling
it as two independently-fitted region boundaries produces the wobble and
width-waver the user rejected. Here the full dark line network becomes
centerline strokes at one calibrated global width (constant BASELINE —
genuine calligraphic swells and free-end tapers are kept as symmetric
ribbons), painted last so shading can never eat the lines. Fills come from
the shared-boundary emitter on a label map with line pixels absorbed.

Eye-verified against the Recraft reference: uniform confident line weight at
8k zoom, 39 paths / 710 pts on the elephant.
"""
from __future__ import annotations

from typing import List

import cv2
import numpy as np

from .base import Param, Pipeline
from .quantize_contours import (
    _absorb_same_fill_shrapnel,
    _consolidate_palette,
    _despeckle_labels,
    _dissolve_blend_bands,
    _dissolve_speckle,
    _merge_shadow_tones,
    _own_transitions,
    _quantize,
    _resnap_fill_boundaries,
    _smooth_labels,
    _split_structured_regions,
)


# Upscale factor for the sharpen prepass (fixed by the it22 sweep; the
# exposed knob is the unsharp amount — one atomic mechanism, one lever).
_PRESHARPEN_UP = 3


# --- Gradient-region flattening (GAP_LEDGER 0f, it23 A-gradientflat) --------
# Measured on all 18 targets (region_stats2, it23): the flatten-wanted
# population (app-asset purple bg 71% / sat 120 / hue-spread 0.6°; shield
# straps 5.5-7.9% / sat 201 / hue 0.3-1.1°) versus the must-not population
# (mountain sky+clouds sat 20 / hue-spread 13°; rabbit body sat 2; elephant
# shading sat 14-20; files-pile paper sat 3-10; game-assets gray bg sat 5.5)
# separates on SATURATION (>=40 vs <=29) and hue coherence (<=1.1° vs >=12°)
# with wide margins. The per-pixel ramp cap (<10 gray/8px) is what cuts
# percolation through wide soft 3D edges (phone/bg edge ~24/8px) and slices
# soft SHADING STEPS between intentional tones (fox flank, chopchop wood:
# each tone becomes its own near-flat component, so flattening it is a
# near-no-op) while a continuous background gradient stays ONE component.
_GRADFLAT_RNG9 = 45.0      # locally quiet: 9px per-channel dynamic range
_GRADFLAT_RAMP = 10.0      # low-freq ramp cap, gray-units per 8 source px
_GRADFLAT_MIN_AREA = 0.04  # of frame; bg gradient regions are huge
_GRADFLAT_MIN_SAT = 40.0   # protects neutral shading/paper (all <=29 measured)
_GRADFLAT_MAX_HUE = 8.0    # sat-weighted circular hue std, degrees
_GRADFLAT_HUE_PURGE = 12.0  # px hue-distance to region hue that stays, degrees
_GRADFLAT_PURGE_SAT = 25.0  # only saturated px are hue-purgeable


def _flatten_gradient_regions(img: np.ndarray) -> tuple:
    """Flatten large smooth-gradient regions to their mean color (ledger 0f).

    Our quantizer turns smooth radial/linear background gradients into 2-3
    k-means labels whose boundaries render as huge ragged blob rings
    (app-asset). Recraft averages such regions into ONE flat solid — the
    correct SVG idealization. This runs BEFORE the sharpen prepass because
    (a) the gates were population-measured on the raw image, (b) sharpen
    amplifies micro-noise which punches holes in the quiet mask, and (c) a
    later sharpen steepens the leftover soft rim INTO the new solid, so the
    halo band that could mint rim labels shrinks instead of growing.

    Returns (img, regions) with regions a list of (mask, mean_rgb) so the
    caller can stamp each region to ONE quantize label.
    """
    h, w = img.shape[:2]
    frame = h * w
    gray = (0.299 * img[..., 0] + 0.587 * img[..., 1]
            + 0.114 * img[..., 2]).astype(np.float32)
    k9 = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    rng9 = np.zeros(gray.shape, np.float32)
    sw, sh = max(1, w // 8), max(1, h // 8)
    mag8 = np.zeros((sh, sw), np.float32)
    for c in range(3):
        ch = img[..., c].astype(np.float32)
        rng9 = np.maximum(rng9, cv2.dilate(ch, k9) - cv2.erode(ch, k9))
        small = cv2.GaussianBlur(
            cv2.resize(ch, (sw, sh), interpolation=cv2.INTER_AREA), (0, 0), 2)
        gx = cv2.Sobel(small, cv2.CV_32F, 1, 0, ksize=3) / 8.0
        gy = cv2.Sobel(small, cv2.CV_32F, 0, 1, ksize=3) / 8.0
        mag8 = np.maximum(mag8, np.sqrt(gx * gx + gy * gy))
    ramp = cv2.resize(mag8, (w, h), interpolation=cv2.INTER_LINEAR)
    quiet = (rng9 < _GRADFLAT_RNG9) & (ramp < _GRADFLAT_RAMP)
    n, lab, st, _ = cv2.connectedComponentsWithStats(
        quiet.astype(np.uint8), connectivity=8)
    if n <= 1:
        return img, []
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    out = img.copy()
    flattened = []
    for i in range(1, n):
        if st[i, 4] < _GRADFLAT_MIN_AREA * frame:
            continue
        m = lab == i
        sat = hsv[..., 1][m].astype(np.float32)
        if sat.mean() < _GRADFLAT_MIN_SAT:
            continue
        ws = sat.sum()
        ang = hsv[..., 0][m].astype(np.float32) / 180.0 * 2 * np.pi
        coher = np.sqrt((np.cos(ang) * sat).sum() ** 2
                        + (np.sin(ang) * sat).sum() ** 2) / max(ws, 1e-6)
        hue_spread = np.sqrt(max(0.0, -2 * np.log(max(coher, 1e-6)))) \
            * 180.0 / (2 * np.pi)
        if hue_spread > _GRADFLAT_MAX_HUE:
            continue
        # Hue-coherence purge (rabbit landmine, it23): a soft SHADOW of a
        # different hue (mauve on the peach bg) blends into the region
        # through an everywhere-gentle transition — no ramp cap can cut it
        # without fragmenting true gradients (shadow edge ~8/8px vs shield
        # strap p90 7.1). But its HUE is 30-50 deg off while every true
        # gradient region measures <=3 deg spread: drop saturated pixels
        # whose hue strays >12 deg from the region hue, then keep only the
        # big surviving pieces. Without this the stamp repaints the shadow
        # INTERIOR as bg and its steep rim renders as a floating squiggle.
        ang0 = np.arctan2((np.sin(ang) * sat).sum(),
                          (np.cos(ang) * sat).sum())
        hdeg = hsv[..., 0].astype(np.float32) * 2.0
        h0 = np.degrees(ang0) % 360.0
        hd = np.abs(hdeg - h0) % 360.0
        hd = np.minimum(hd, 360.0 - hd)
        keep2 = m & ~((hsv[..., 1] > _GRADFLAT_PURGE_SAT)
                      & (hd > _GRADFLAT_HUE_PURGE))
        if not keep2.any():
            continue
        nk, labk, stk, _ = cv2.connectedComponentsWithStats(
            keep2.astype(np.uint8), connectivity=8)
        for j in range(1, nk):
            if stk[j, 4] < _GRADFLAT_MIN_AREA * frame:
                continue
            mj = labk == j
            mean = [int(round(float(img[..., c][mj].mean())))
                    for c in range(3)]
            for c in range(3):
                out[..., c][mj] = mean[c]
            flattened.append((mj, np.array(mean, np.float32)))
    return out, flattened


# --- Ramp band-split (auto-loop COLOR, gradient banding) --------------------
# Where the SOURCE has a smooth wide-span luminance ramp inside one label,
# our collapse-to-one-tone reads as COLOR error (tile evidence: ours dE 6-18
# vs source where Recraft sits at 1-3). Recraft's idealization is 2-3 FLAT
# BANDS whose tones track the source — not one median tone, and never an SVG
# gradient (USER design rule). This pass splits such labels at iso-level
# cuts of a heavily smoothed ramp coordinate (the component's dominant Lab
# axis) measured on the SOURCE. Evidence gates keep flat regions
# and subtle shading alone: the component must be LARGE, its interior locally
# QUIET (a ramp, not texture/edges), and its L* span WIDE. Fill tones then
# come from _source_region_colors, which re-anchors each new band label to
# the source pixels it covers.
# The ramp coordinate is the component's dominant Lab axis (PCA), not L*
# alone: crystal facet ramps are chroma-heavy (lbl6 maroon: L*-span 0.8 but
# Lab-span 12.3; lbl10 red: 11.4 vs 22.5-38.1), so an L-only span gate missed
# most of the banding population. Population-measured on all 11 gate targets
# + files-pile as texture control (components >=0.4% frame):
#   fire:  crystals facets spanP 12.3-38.1 / med9 1.4-8.7 / res 0.75-0.98;
#          app-asset blue+orange 12.0-26.3 / <=6.7 / >=0.78; fox dark body
#          14.7 / 5.1 / 0.81; mountain rock 13.8 / 9.0 / 0.97
#   hold:  chopchop / rabbit / elephant / logos / monster: NO comp reaches
#          spanP 8; pizza-box max 8.6 (gradflat-owned); shield straps 11.0-
#          11.5 (ledger-0f one-solid population) sit just under the span cut
#   texture (must-not): files-pile paper spanP 18-62 but med9 12.8-27.7 or
#          res-frac 0.15-0.66 — blocked by BOTH smoothness gates
_BAND_MIN_AREA = 0.0015   # component area, fraction of frame
_BAND_SPAN = 12.0         # p92-p8 interior span of the ramp coord (~dE)
_BAND_SPAN3 = 26.0        # span at/above which 3 bands instead of 2
                          # (23 probed: census win shrank -0.0166->-0.0131
                          # on crystals; the extra cuts over-fragment)
_BAND_QUIET_MED = 8.8     # median 9px local range of DENOISED ramp coord
                          # (fox fur-textured body shading sits at 9.0 and
                          # bands it wrongly — measured +0.008 color on fox;
                          # smooth crystal paint winners top out at 8.7)
_BAND_RES_TOL = 4.0       # |proj - heavy-blur(proj)| residual tolerance
_BAND_RES_FRAC = 0.75     # interior fraction the smoothed field must explain
_BAND_MIN_PIECE = 0.15    # every band must hold >= this fraction of the comp
_BAND_FRAG = 0.02         # band islands below this comp-fraction are absorbed
_BAND_INK_LUM = 40.0      # never band near-black labels: they own the drawn
                          # ink network, and recoloring half of it wrecked fox
                          # (color +0.075; ink lum 30.4 vs darkest true-fill
                          # winner 47.9 — measured this loop)
_BAND_MIN_EDGE = 0.06     # scene gate: imgstats edge_density. Banding is the
                          # Recraft idealization for PAINTED art (crystals
                          # 0.116, chopchop 0.123); in soft 3D-render scenes
                          # (app-asset 0.042) Recraft flattens the same ramps
                          # to ONE tone (eye-verified on the target arrow),
                          # and banding there minted census/flow boundaries.


def _band_split_ramps(labels: np.ndarray, centers: np.ndarray,
                      raw: np.ndarray,
                      exclude: np.ndarray = None) -> tuple:
    """Split smooth wide-span ramp labels into 2-3 iso-level flat bands.

    Runs AFTER the full label-cleanup chain so bands cannot be re-absorbed,
    and measures ALL evidence on the RAW source (never the sharpened frame).
    `exclude` masks pixels already idealized by _flatten_gradient_regions —
    those were measured (ledger 0f) as Recraft ONE-solid regions; re-banding
    them would undo a shipped win. Returns (labels, centers) with new band
    labels appended; the largest band keeps the original label id.
    """
    h, w = labels.shape
    frame = float(h * w)
    lab = cv2.cvtColor(raw, cv2.COLOR_RGB2Lab).astype(np.float32)
    lab[..., 0] *= 100.0 / 255.0
    lab[..., 1] -= 128.0
    lab[..., 2] -= 128.0
    k9 = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    out = labels.copy()
    new_centers = list(centers)
    n_orig = len(centers)
    for li in range(n_orig):
        c = centers[li].astype(np.float32)
        if 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] < _BAND_INK_LUM:
            continue          # ink-layer guard: never recolor the line labels
        m = labels == li
        if m.sum() < _BAND_MIN_AREA * frame:
            continue
        ncc, cc, st, _ = cv2.connectedComponentsWithStats(
            m.astype(np.uint8), connectivity=8)
        for ci in range(1, ncc):
            area = float(st[ci, 4])
            if area < _BAND_MIN_AREA * frame:
                continue
            x, y, ww, hh = st[ci, 0], st[ci, 1], st[ci, 2], st[ci, 3]
            sub = cc[y:y + hh, x:x + ww] == ci
            if exclude is not None and \
                    (exclude[y:y + hh, x:x + ww] & sub).sum() > 0.3 * area:
                continue
            # interior only: boundary AA / neighbour bleed must not fake a
            # wide span or break the quiet gate
            dist = cv2.distanceTransform(sub.astype(np.uint8), cv2.DIST_L2, 3)
            interior = dist > 4.0
            if interior.sum() < 0.25 * area:
                continue
            sublab = lab[y:y + hh, x:x + ww]
            P = sublab[interior]
            mu = P.mean(0)
            ax = np.linalg.eigh(np.cov((P - mu).T))[1][:, -1]
            dint = (P - mu) @ ax
            span = float(np.percentile(dint, 92) - np.percentile(dint, 8))
            if span < _BAND_SPAN:
                continue          # flat or subtle shading: leave alone
            proj = ((sublab - mu[None, None, :]) @ ax).astype(np.float32)
            # local range on a lightly DENOISED coord: the raw 9px range is
            # dominated by JPEG noise (measured: real crystal ramps fail a
            # raw-range gate at any cap that still blocks texture)
            pd = cv2.GaussianBlur(proj, (0, 0), 1.5)
            rng9 = cv2.dilate(pd, k9) - cv2.erode(pd, k9)
            if float(np.median(rng9[interior])) > _BAND_QUIET_MED:
                continue          # textured / edgy interior: not a ramp
            # heavily smoothed masked coord so the iso-cuts are clean curves
            sig = float(np.clip(np.sqrt(area) / 20.0, 3.0, 12.0))
            mf = sub.astype(np.float32)
            Lb = cv2.GaussianBlur(proj * mf, (0, 0), sig) \
                / np.maximum(cv2.GaussianBlur(mf, (0, 0), sig), 1e-6)
            res = np.abs(proj - Lb)[interior]
            if float((res < _BAND_RES_TOL).mean()) < _BAND_RES_FRAC:
                continue          # smoothed field can't explain the interior
            vals = Lb[sub]
            nb = 3 if span >= _BAND_SPAN3 else 2
            bmap = None
            while nb >= 2:
                qs = np.percentile(vals, [100.0 * i / nb
                                          for i in range(1, nb)])
                cand = np.digitize(Lb, qs)
                cand[~sub] = -1
                # absorb band islands (level-set pockets around local
                # extrema) into the adjacent band so they don't mint paths
                for b in range(nb):
                    bm = cand == b
                    if not bm.any():
                        continue
                    nf, lf, sf, _ = cv2.connectedComponentsWithStats(
                        bm.astype(np.uint8), connectivity=8)
                    for j in range(1, nf):
                        if sf[j, 4] >= max(48.0, _BAND_FRAG * area):
                            continue
                        frag = lf == j
                        cand[frag] = b + 1 if b == 0 else b - 1
                sizes = [int((cand == b).sum()) for b in range(nb)]
                if min(sizes) >= _BAND_MIN_PIECE * area:
                    bmap = cand
                    break
                nb -= 1
            if bmap is None:
                continue
            # largest band keeps li; the rest become new source-toned labels
            order = np.argsort(sizes)[::-1]
            rsub = raw[y:y + hh, x:x + ww]
            for b in order[1:]:
                bm = bmap == b
                mean = np.clip(np.round(
                    rsub[bm].reshape(-1, 3).mean(0)), 0, 255).astype(np.uint8)
                out[y:y + hh, x:x + ww][bm] = len(new_centers)
                new_centers.append(mean)
    if len(new_centers) == n_orig:
        return labels, centers
    return out, np.stack(new_centers).astype(centers.dtype)


# --- Component-tone re-anchor (auto-loop it69, UNDER-RESOLVE) ---------------
# A light minority CONNECTED COMPONENT one-clustered into a bigger fill label
# paints with the label's tone and vanishes against its surroundings — the
# crystals pale-cyan facet strip (src ~(200,247,247)) absorbed by the WHITE
# background label at k=16 renders white-on-white (region dE-to-source 10-18
# where Recraft sits at 1.5). The merge happens AT _quantize (global k has no
# centroid for the tint), so no merge/split gate downstream can see it; the
# per-LABEL source re-anchor (_source_region_colors) is dominated by the
# label's majority component. Cure: after the label chain settles, give each
# large FLAT component whose own source tone genuinely differs from the tone
# emission will paint a fresh label carrying its own trimmed source mean.
# Geometry is untouched (components already trace as their own loops); only
# the minority component's fill tone changes — toward the source, which on
# every population-checked instance is also toward Recraft (crystals facets,
# rabbit bag mint rim, mountain teal peak, shield rivets, app-asset glyph).
#
# Population-measured 2026-07-12 on all 11 gate targets (comps >=300px of
# fill-grade labels, quant-12 params):
#   fire  (eye-verified matches Recraft): dE 12.38-33.91, span 2.18-12.03 —
#         crystals facet/tint family (22), rabbit bag rim (1, dE 16.57),
#         mountain teal peak (1, 27.60), shield rivets (4, 19.75-22.70),
#         app-asset icon glyph (1, 12.97)
#   hold  (flat must-not ceiling): fox 7.14, chopchop 6.77, rabbit 7.62,
#         elephant 8.95 (span 16.4 besides), monster 0.36, logo-geo none,
#         pizza-box all < 12 -> elephant/fox/chopchop/pizza/monster/logo see
#         ZERO fires; margin 12.0/7.14 = 1.7x
#   span  (ramp fragments stay banded/band-split territory): true fires reach
#         span 17.85 (crystals pink-gem faces dE 18.5-21.3, eye-verified:
#         Recraft paints them the comp's peach tone); the blocked ramp
#         population starts at 21.58 (crystals L12) -> gate 18.5 sits ~1.17x
#         under it. Everything a wider span admits corpus-wide at dE>=12 is
#         on crystals; must-not stems stay dE-blocked (elephant max 8.95 at
#         span 16.4 keeps the 12.0/8.95 = 1.34x dE margin).
_REANC_DE = 12.0          # CIEDE2000(comp trimmed tone, label emission tone)
_REANC_SPAN = 18.5        # interior dominant-Lab-axis p92-p8 flatness cap
_REANC_MIN_FRAC = 0.00028  # comp area >= this fraction of frame (300px@1024^2)
_REANC_DOM = 0.9          # skip the label's dominant component (it IS the tone)
_REANC_LUM = 96.0         # fill-grade guard, both parent center AND minted
                          # tone (= emission dark_lum default): stroke-grade
                          # labels and stroke-grade tones stay untouched so
                          # the line network never changes
_REANC_TRIM = 40.0        # RGB trim radius for the robust tone (=_FILLC_TRIM)


def _reanchor_component_tones(labels: np.ndarray, centers: np.ndarray,
                              raw: np.ndarray,
                              protect: np.ndarray = None) -> tuple:
    """Mint source-toned labels for mis-toned flat minority components.

    Runs LAST in the label chain (after struct-split) so it sees final
    geometry; evidence measured on the RAW source. Returns (labels, centers)
    with new labels appended — the component keeps its exact pixel mask, so
    fills keep their shapes and only the painted tone moves to the source."""
    from skimage.color import rgb2lab, deltaE_ciede2000

    from contours_exp import _source_region_colors

    h, w = labels.shape
    frame = float(h * w)
    min_area = _REANC_MIN_FRAC * frame
    fillc = _source_region_colors(labels, centers, raw)
    lab_fill = rgb2lab(fillc.reshape(1, -1, 3) / 255.0)[0]
    out = labels
    new_centers = list(centers)
    n_orig = len(centers)
    slab = None                     # lazy full-frame Lab of the raw source
    for li in range(n_orig):
        c = centers[li].astype(np.float32)
        if 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] < _REANC_LUM:
            continue                # stroke-candidate label: hands off
        m = labels == li
        tot = int(m.sum())
        if tot < min_area:
            continue
        ncc, cc, st, _ = cv2.connectedComponentsWithStats(
            m.astype(np.uint8), connectivity=8)
        for ci in range(1, ncc):
            area = float(st[ci, 4])
            if area < min_area or area > _REANC_DOM * tot:
                continue
            x, y, ww, hh = (int(v) for v in st[ci, :4])
            sub = cc[y:y + hh, x:x + ww] == ci
            if protect is not None and \
                    (protect[y:y + hh, x:x + ww] & sub).sum() > 0.3 * area:
                continue            # gradflat-idealized: deliberately ONE tone
            dist = cv2.distanceTransform(sub.astype(np.uint8), cv2.DIST_L2, 3)
            interior = dist > 1.5   # keep boundary AA out of the tone vote
            if interior.sum() < max(48, 0.2 * area):
                continue
            pix = raw[y:y + hh, x:x + ww][interior].reshape(-1, 3) \
                .astype(np.float64)
            med = np.median(pix, axis=0)
            keep = pix[((pix - med) ** 2).sum(1) < _REANC_TRIM * _REANC_TRIM]
            tone = keep.mean(0) if len(keep) >= 0.5 * len(pix) else med
            if 0.299 * tone[0] + 0.587 * tone[1] + 0.114 * tone[2] \
                    < _REANC_LUM:
                continue            # minted label must stay fill-grade too
            tl = rgb2lab(tone[None, None, :] / 255.0)[0, 0]
            de = float(deltaE_ciede2000(tl[None, None, :],
                                        lab_fill[li][None, None, :])[0, 0])
            if de < _REANC_DE:
                continue            # tone family: the label paint is right
            if slab is None:
                slab = rgb2lab(raw.astype(np.float64) / 255.0)
            P = slab[y:y + hh, x:x + ww][interior]
            if len(P) < 9:
                continue
            mu = P.mean(0)
            ax = np.linalg.eigh(np.cov((P - mu).T))[1][:, -1]
            dint = (P - mu) @ ax
            span = float(np.percentile(dint, 92) - np.percentile(dint, 8))
            if span > _REANC_SPAN:
                continue            # internal ramp/texture: not a flat tint
            if out is labels:
                out = labels.copy()
            out[y:y + hh, x:x + ww][sub] = len(new_centers)
            new_centers.append(np.clip(np.round(tone), 0, 255)
                               .astype(centers.dtype))
    if out is labels:
        return labels, centers
    return out, np.stack(new_centers).astype(centers.dtype)


def _sharpen_prepass(img: np.ndarray, amount: float,
                     up: int = None, radius: float = 2.0) -> np.ndarray:
    """USER-validated blur-killer prepass (GAP_LEDGER 0e, it22 A-sharpen).

    Upscale LANCZOS ×up → unsharp mask (σ = radius·up/2, source-scale radius
    ≈2px) → INTER_AREA back down. Steepens soft AA/blur ramps into step edges
    BEFORE quantization, so gradient daubs stop becoming k-means labels (and
    then geometry); the INTER_AREA downscale averages the overshoot ring back
    into the flat regions instead of minting halo colors (the failure mode of
    plain single-scale unsharp, rejected 2026-07-07).

    Anti-ringing clamp (it22 landmine fix): the raw unsharp OVERSHOOTS at
    hard graphic edges — on logo-badge it minted a brighter-yellow ring
    along every yellow/navy boundary that quantize then kept as a real rim
    shape. Clipping the sharpened image to the local (erode/dilate) min/max
    of the pre-sharpen upscale makes minting values brighter/darker than
    anything nearby impossible, while gradient steepening toward existing
    local extremes (what kills the blur daubs) is untouched.
    """
    if amount <= 0:
        return img
    if up is None:
        up = _PRESHARPEN_UP
    h, w = img.shape[:2]
    big = cv2.resize(img, (w * up, h * up), interpolation=cv2.INTER_LANCZOS4)
    blur = cv2.GaussianBlur(big, (0, 0), radius * up / 2.0)
    sharp = cv2.addWeighted(big, 1.0 + amount, blur, -amount, 0)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * up + 1, 2 * up + 1))
    sharp = np.clip(sharp, cv2.erode(big, k), cv2.dilate(big, k))
    return cv2.resize(sharp, (w, h), interpolation=cv2.INTER_AREA)


def _thin_dark_line_lock(labels: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Mask of thin drawn dark-line pixels the label cleanup must not erase.

    thin (half-width <=1.6px) AND not within 2px of thick ink (>2.5px
    half-width — excludes blob fringes) AND in an elongated component
    (>=40px at ~2.5px width ≈ >=16px of length).
    """
    dark = np.zeros(labels.shape, bool)
    for ci, c in enumerate(centers):
        # true ink only (rabbit ink 9-49 lum; AA-fringe/shadow midtones 60-95
        # lock as phantom dashes — measured run 25)
        if 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] < 60:
            dark |= labels == ci
    if not dark.any():
        return dark
    dist = cv2.distanceTransform(dark.astype(np.uint8), cv2.DIST_L2, 3)
    thick = (dist > 2.5).astype(np.uint8)
    k5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    near_thick = cv2.dilate(thick, k5).astype(bool)
    thin_line = dark & (dist <= 1.6) & ~near_thick
    n, lab = cv2.connectedComponents(thin_line.astype(np.uint8), connectivity=8)
    if n <= 1:
        return np.zeros(labels.shape, bool)
    sizes = np.bincount(lab.ravel())
    keep = np.zeros(n, bool)
    keep[1:] = sizes[1:] >= 40
    return keep[lab]


class ContourLinesPipeline(Pipeline):
    id = "contour_lines"
    name = "Contour lines (width-constant)"
    description = ("Dark line network as constant-baseline centerline strokes "
                   "on top of shared-boundary fills — the digital drawn look.")
    params: List[Param] = [
        Param("num_colors", "Colors (k)", "int", 16, min=4, max=32, step=1),
        Param("seed", "K-means seed", "int", 0, min=0, max=99999, step=1),
        Param("merge_de", "Palette merge ΔE", "float", 12.0, min=0.0, max=30.0, step=0.5),
        Param("min_area", "Despeckle (px)", "int", 120, min=0, max=2000, step=10),
        Param("blur", "Pre-blur (px)", "int", 1, min=0, max=9, step=1),
        Param("presharpen", "Pre-sharpen amount", "float", 1.6, min=0.0, max=3.0, step=0.1,
              help="Unsharp amount for the upscale(3x)->sharpen->downscale "
                   "prepass that melts blur/AA gradient noise before it can "
                   "become labels (0 = off). Runs before the median pre-blur."),
        Param("gradflat", "Flatten gradient regions", "int", 1, min=0, max=1, step=1,
              help="Pre-flatten large smooth-gradient regions (saturated, "
                   "hue-coherent, locally quiet) to their mean color before "
                   "sharpening/quantization, so background gradients render "
                   "as ONE flat solid instead of ragged banding rings (0 = off)."),
        Param("fill_tol", "Fill fit tolerance", "float", 2.5, min=0.25, max=6.0, step=0.25),
        Param("fill_smooth", "Fill smoothing", "int", 0, min=0, max=15, step=1),
        Param("fill_parsimony", "Fill parsimony (opttol)", "float", 1.0, min=0.0, max=2.0, step=0.1,
              help="Potrace parsimony fit for the shading-region boundaries — flat "
                   "idealized shapes like Recraft's, wobble-free by construction. "
                   "0 falls back to smooth+Schneider fills."),
        Param("dark_lum", "Line luminance cutoff", "float", 96.0, min=10.0, max=160.0, step=1.0,
              help="Labels darker than this are stroke candidates; lower it when a "
                   "dark-but-not-line palette entry (maroon rim, navy ring) gets "
                   "stroke-ified. Wide uniform bands are auto-skipped regardless."),
        Param("width_scale", "Line weight", "float", 0.85, min=0.5, max=1.5, step=0.05,
              help="Multiplies the calibrated stroke width. The ink-area calibration "
                   "matches the source line weight; lower this for the more delicate "
                   "line a designer might prefer (~0.85 tracks Recraft's elephant)."),
    ]

    def run(self, image_path: str, params: dict) -> str:
        from contours_exp import contour_svg

        p = self.resolved_params(params)
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError(f"Could not read image: {image_path}")
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        raw = img
        _regions = []
        if p.get("gradflat", 1):
            img, _regions = _flatten_gradient_regions(img)

        # Flat-art skip (run 38): sharpening pure flat art has no blur noise
        # to melt and DEFORMS it — run 37 mangled the monster mouth (agent
        # mislabeled it "lateral"; USER caught it). imgstats kind separates
        # cleanly: flat = monster + 4 logos (all revert to the pre-sharpen
        # output byte-identically), lineart = all 9 win targets. Decided on
        # the RAW image so flattening can't flip the classification.
        from imgstats import analyze
        _stats = analyze(raw)
        _sharpen_ok = True
        if p["presharpen"] > 0:
            _sharpen_ok = _stats["kind"] != "flat"

        def _prepasses(a):
            if p["presharpen"] > 0 and _sharpen_ok:
                a = _sharpen_prepass(a, p["presharpen"])
            if p["blur"] > 0:
                a = cv2.medianBlur(a, p["blur"] * 2 + 1)
            return a

        img = _prepasses(img)
        if _regions:
            # QUANTIZE the UNflattened image (palette AND labels byte-equal
            # to the no-gradflat path). Letting k-means see the flattened
            # frame reallocates the centroids the gradient used to occupy —
            # measured on app-asset: the freed slots split the white cluster
            # (new 200,218,248 center) and the "Share" glyph AA thinned into
            # fragments. Per-pixel re-assignment against the final centers is
            # no better (cv2.kmeans labels come from the E-step BEFORE the
            # last centroid update, so borderline glyph-AA pixels flip), and
            # stamping BEFORE palette consolidation still diverges (the
            # area-weighted dE merges see the ballooned bg label and merge
            # different pairs — measured: darkest purple 48,42,75 vanished).
            # So the stamp happens AFTER consolidate+shadow-merge, right
            # before the cleanup chain: everything up to there is
            # byte-identical to prev, then each gradient region becomes ONE
            # label — banding gone, zero side effects outside the regions.
            qimg = _prepasses(raw)
            labels, centers = _quantize(qimg, p["num_colors"], p["seed"])
        else:
            qimg = img
            labels, centers = _quantize(img, p["num_colors"], p["seed"])
        if p["merge_de"] > 0:
            labels, centers = _consolidate_palette(labels, centers, p["merge_de"])
            labels, centers = _merge_shadow_tones(labels, centers)
            if _regions:
                cf = centers.astype(np.float32)
                for m, mean in _regions:
                    li = int(((cf - mean[None, :]) ** 2).sum(1).argmin())
                    labels[m] = li
            # Transition-ownership (audit24 E1, it24 A-transown): thin mid-
            # tone labels sandwiched between two color-close region fills are
            # quantized AA/blur ramps, not drawing — absorb each into the
            # nearer bounding region BEFORE the lock/despeckle chain, so ramp
            # shrapnel neither gets ink privileges nor survives as dashes.
            labels = _own_transitions(labels, centers)
            lock = _thin_dark_line_lock(labels, centers)
            labels0 = labels.copy()
            labels = _despeckle_labels(labels, max(p["min_area"], 16), centers)
            labels = _smooth_labels(labels, len(centers), centers=centers)
            labels = _dissolve_speckle(labels, centers, 300)
            # Thin drawn lines (heart outline, paw fingers, button rings) are
            # sub-mode-filter width: despeckle/smooth erase them wholesale and
            # downstream bridging then "closes" the survivors into blobs. The
            # lock re-stamps pre-cleanup labels wherever cleanup flipped a
            # locked line pixel to a light label. Locked pixels are thin
            # (half-width <=1.6px), not blob fringe (no thick ink within 2px),
            # and elongated (component >=40px) — measured: true lines have
            # thin-fraction >=0.77, blob fringes <=0.35 (rabbit + chopchop).
            flipped = lock & (labels != labels0)
            labels[flipped] = labels0[flipped]
            # Same-fill shrapnel absorption (OVER-FRAGMENT, auto-loop
            # 2026-07-10): the passes above all PROTECT dark labels, so
            # dark-on-dark shadow shrapnel (k-means splitting one soft shadow
            # into interleaved near-identical tones) survives to become
            # spurious paths. Merge a small component into an adjacent
            # near-same-fill region ONLY where the RAW source shows no real
            # boundary between them (evidence gate — drawn marks contrast in
            # the source and are refused). Locked thin-line pixels are sacred.
            labels = _absorb_same_fill_shrapnel(labels, centers, raw, lock)
            # Blend-band dissolution (AA TRANSITION MUD, auto-loop
            # 2026-07-10 COLOR): _own_transitions only handles shading-class
            # pairs (ablen <= 36), so the mid-tone ramp bands that hug
            # HIGH-CONTRAST boundaries (ink vs fill — chopchop plank
            # outlines, fox in-ink debris, mountain ridges) survive the
            # whole chain and render as mud that matches neither neighbor.
            # Source-evidence-gated: the band's own source color must BE the
            # blend of its two bounds' source colors and its pixels must
            # SPAN the ramp; each pixel then joins the source-nearer side
            # (midline split = Recraft's crisp two-region boundary).
            labels = _dissolve_blend_bands(labels, centers, raw, lock)
            # ... and its zero-width case: even where the ramp mints no
            # third label, the boundary between two fills lands where pixel
            # color crosses the GLOBAL-centroid midpoint, not the local
            # ramp's 50% crossing. Re-vote the 2px ribbon around every
            # fill<->fill boundary with local plateau evidence (stroke-grade
            # labels untouched — global width calibration).
            labels = _resnap_fill_boundaries(labels, centers, raw)

        # Ramp band-split (auto-loop COLOR): smooth wide-span source ramps
        # collapsed to one label become 2-3 flat iso-level bands (the
        # Recraft idealization). Gradflat-stamped regions are excluded —
        # those were measured as Recraft ONE-solid (ledger 0f). Scene gate:
        # only PAINTED art (dense drawn edges); Recraft flattens soft-render
        # scenes' ramps to one tone (see _BAND_MIN_EDGE).
        if _stats["kind"] != "flat" \
                and _stats["edge_density"] >= _BAND_MIN_EDGE:
            _excl = None
            if _regions:
                _excl = np.zeros(labels.shape, bool)
                for _m, _mean in _regions:
                    _excl |= _m
            labels, centers = _band_split_ramps(labels, centers, raw, _excl)

        # Structured-region split (UNDER-RESOLVE fix, autoresearch 2026-07-10):
        # adjacent drawn facets sharing one k-means label fuse into one path
        # (crystals: 16 paths vs Recraft's 58 in one region). Where a region's
        # INTERIOR still shows strong source edges, re-segment it locally so
        # each drawn sub-shape gets its own label. Evidence-gated per
        # component (edge density + boundary coincidence + colour separation)
        # so shading and gradients never split; gradflat stamps are protected.
        _protect = None
        if _regions:
            _protect = np.zeros(labels.shape, bool)
            for _m, _ in _regions:
                _protect |= _m
        labels, centers = _split_structured_regions(labels, centers, qimg,
                                                    protect=_protect)

        # Component-tone re-anchor (UNDER-RESOLVE): light flat minority
        # components one-clustered into a bigger fill label (crystals pale
        # facet in the white bg label) get their own source-toned label.
        # Last in the chain so it sees final geometry; flat art skipped
        # (conservatism precedent: sharpen skip / band-split / wander).
        if _stats["kind"] != "flat":
            labels, centers = _reanchor_component_tones(labels, centers, raw,
                                                        protect=_protect)

        # Wander erasure only for non-flat scenes: flat art's boundaries are
        # drawn ink (no quantizer ramp for an iso-line to wander through) —
        # same scene gate as the sharpen skip above (run 38 precedent).
        svg, _info = contour_svg(labels, centers, fill_tol=p["fill_tol"],
                                 fill_smooth=p["fill_smooth"],
                                 fill_parsimony=p["fill_parsimony"],
                                 dark_lum=p["dark_lum"],
                                 width_scale=p["width_scale"],
                                 src_img=img, color_img=raw,
                                 fill_wander=_stats["kind"] != "flat")
        return svg
