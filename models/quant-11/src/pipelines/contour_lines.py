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
    _consolidate_palette,
    _despeckle_labels,
    _dissolve_speckle,
    _merge_shadow_tones,
    _own_transitions,
    _quantize,
    _smooth_labels,
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
        _sharpen_ok = True
        if p["presharpen"] > 0:
            from imgstats import analyze
            _sharpen_ok = analyze(raw)["kind"] != "flat"

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
            labels, centers = _quantize(_prepasses(raw), p["num_colors"],
                                        p["seed"])
        else:
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

        svg, _info = contour_svg(labels, centers, fill_tol=p["fill_tol"],
                                 fill_smooth=p["fill_smooth"],
                                 fill_parsimony=p["fill_parsimony"],
                                 dark_lum=p["dark_lum"],
                                 width_scale=p["width_scale"],
                                 src_img=img, color_img=raw)
        return svg
