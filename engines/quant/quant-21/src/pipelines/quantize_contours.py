"""Color-quantize -> per-region contours -> smoothed Bezier paths.

Fully in-process (numpy/OpenCV), so every knob is ours to expose. This is the
pipeline to hack on when testing custom hypotheses about simplification and
smoothing. Layers are painted largest-area-first (painter's algorithm), each
region emitted as a single compound path (outer + holes) with evenodd fill.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np

from .base import Pipeline, Param, order_layers as _order_layers, _luminance, DARK_LINE_LUM


def _quantize(img_rgb: np.ndarray, k: int, seed: int = 1234567) -> Tuple[np.ndarray, np.ndarray]:
    """K-means color quantization. Returns (label_map HxW, centers kx3 uint8)."""
    # cv2's RNG is STATEFUL across calls in one process — unseeded, every
    # sequential run gets a different cluster map, making configs impossible
    # to compare (phantom point-count swings). Pin it per call.
    cv2.setRNGSeed(int(seed))
    Z = img_rgb.reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    attempts = 3
    _, labels, centers = cv2.kmeans(Z, k, None, criteria, attempts, cv2.KMEANS_PP_CENTERS)
    centers = np.clip(centers, 0, 255).astype(np.uint8)
    labels = labels.reshape(img_rgb.shape[:2])
    return labels, centers


def _merge_shadow_tones(labels: np.ndarray, centers: np.ndarray
                        ) -> Tuple[np.ndarray, np.ndarray]:
    """Merge near-duplicate LOW-CHROMA shadow tones (measured Recraft gap).

    8-pair OKLCH measurement (experiments/measure_ramp.py, run 8): Recraft's
    palettes match ours to ~0.005 EXCEPT it keeps ONE mid shadow tone where
    our k-means keeps two near-duplicates (elephant: aeb4c4 + 98bee3 → their
    a6b8d0). Merge criterion tuned against that data so distinct grays
    survive: BOTH tones low-chroma (OKLab C < 0.08), nearly equal lightness
    (|dL| < 0.03 — mountain's d0dfe4/b6d2df pair at dL 0.04 must NOT merge),
    and OKLab dE < 0.06. Merged color = area-weighted mean. Chromatic ramps
    (crystals) are untouched by the C gate."""
    n = len(centers)
    if n <= 2:
        return labels, centers
    c = (centers.astype(np.float64) / 255.0)
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    l = c @ np.array([0.4122214708, 0.5363325363, 0.0514459929])
    m = c @ np.array([0.2119034982, 0.6806995451, 0.1073969566])
    s = c @ np.array([0.0883024619, 0.2817188376, 0.6299787005])
    l_, m_, s_ = np.cbrt(l), np.cbrt(m), np.cbrt(s)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    A = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    B = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    C = np.hypot(A, B)
    areas = np.bincount(labels.ravel(), minlength=n).astype(np.float64)
    remap = np.arange(n)
    for i in range(n):
        for j in range(i + 1, n):
            if remap[i] != i or remap[j] != j:
                continue
            if C[i] >= 0.08 or C[j] >= 0.08:
                continue
            if abs(L[i] - L[j]) >= 0.03:
                continue
            de = np.sqrt((L[i] - L[j]) ** 2 + (A[i] - A[j]) ** 2
                         + (B[i] - B[j]) ** 2)
            if de >= 0.06:
                continue
            # hue-opposition guard: even at low chroma, warm-vs-cool reads
            # across large areas (mountain: cream snowband vs blue-gray sky
            # must NOT merge). Require the chroma vectors to point the same
            # general direction when both carry any hue at all.
            if C[i] > 0.005 and C[j] > 0.005 and \
                    (A[i] * A[j] + B[i] * B[j]) / (C[i] * C[j]) <= 0.3:
                continue
            keep, drop = (i, j) if areas[i] >= areas[j] else (j, i)
            w = areas[keep] + areas[drop]
            if w > 0:
                centers[keep] = ((centers[keep].astype(np.float64) * areas[keep]
                                  + centers[drop].astype(np.float64) * areas[drop])
                                 / w).astype(centers.dtype)
            areas[keep] = w
            remap[drop] = keep
    if (remap == np.arange(n)).all():
        return labels, centers
    labels = remap[labels]
    used = np.unique(labels)
    lut = np.zeros(n, dtype=labels.dtype)
    lut[used] = np.arange(len(used))
    return lut[labels], centers[used]


def _consolidate_palette(labels: np.ndarray, centers: np.ndarray,
                         min_de: float) -> Tuple[np.ndarray, np.ndarray]:
    """Absorb anti-aliasing HALO clusters into the region they wrap.

    K-means splits a stroke's anti-aliasing into near-duplicate shades that
    paint as stacked fragments — 'multiple blocks of different shades' where a
    professional asset has one solid container. Naive global dE-merge is WRONG
    (semantically distinct colors can be close: white belly vs light-gray body;
    Recraft's own palette has pairs at dE 2.4). The correct signal is
    STRUCTURAL: halo clusters are THIN (low area/perimeter). Absorb a thin
    cluster into the neighbor it shares the most boundary with, guarded by
    dE < min_de so genuinely different thin features (dark outlines!) survive.
    """
    n = len(centers)
    if n <= 1 or min_de <= 0:
        return labels, centers
    from skimage.color import rgb2lab, deltaE_ciede2000
    lab = rgb2lab(centers.reshape(1, -1, 3) / 255.0)[0]

    remap = np.arange(n, dtype=np.int32)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    areas = np.bincount(labels.ravel(), minlength=n)
    for ci in range(n):
        mask = (labels == ci).astype(np.uint8)
        area = int(areas[ci])
        if area == 0:
            continue
        per = float(cv2.countNonZero(mask - cv2.erode(mask, kernel)))
        thinness = area / max(per, 1.0)   # ~ mean half-width of the region
        ring = cv2.dilate(mask, kernel).astype(bool) & (labels != ci)
        if not ring.any():
            continue
        neigh = np.bincount(labels[ring].ravel(), minlength=n)
        nb = int(np.argmax(neigh))
        share = float(neigh[nb]) / max(float(neigh.sum()), 1.0)
        de = float(deltaE_ciede2000(lab[ci][None, None, :], lab[nb][None, None, :]))
        # Absorb when near-duplicate AND either:
        #  (a) a thin AA halo (classic), or
        #  (b) an INTERLEAVED dither twin: k-means splitting a flat area into
        #      two near-identical scattered clusters (huge mutual boundary).
        #      Left unmerged, despeckle later nukes the whole dithered region
        #      and floods it from outside — the seed-lottery catastrophe.
        interleaved = share > 0.5
        # Acyclicity: absorb only into a STRICTLY "larger" cluster (area,
        # index tiebreak). Mutual near-duplicates otherwise absorb EACH OTHER
        # (remap cycle) — both leave the survivor set and their pixels remap
        # to index 0 = the background. That was the vanished-outline bug: the
        # whole stroke network relabeled as sky at unlucky seeds.
        bigger = (areas[nb] > area) or (areas[nb] == area and nb > ci)
        if de < min_de and bigger and (thinness <= 2.0 or interleaved):
            remap[ci] = nb

    dissolved = [ci for ci in range(n) if remap[ci] != ci]
    if not dissolved:
        return labels, centers

    # Twins/halos have a KNOWN target — assign directly. Spatial nearest-
    # survivor reassignment steals up to half of a dithered stroke's pixels
    # for adjacent regions, thinning lines to 1-2px (which the mode filter
    # then erases entirely — the vanished-outline catastrophe).
    final = np.arange(n, dtype=np.int32)
    for _ in range(n):
        nxt = final[remap] if False else remap[final]
        if np.array_equal(nxt, final):
            break
        final = nxt
    new_labels = final[labels]
    survivors = sorted(set(range(n)) - set(dissolved))
    dense = np.zeros(n, dtype=np.int32)
    for i, old in enumerate(survivors):
        dense[old] = i
    return dense[new_labels], centers[survivors]


def _reassign_pixels(labels: np.ndarray, dis_mask: np.ndarray) -> np.ndarray:
    """Give masked pixels the label of their spatially nearest unmasked pixel."""
    if not dis_mask.any():
        return labels
    if dis_mask.all():
        return labels
    _, near = cv2.distanceTransformWithLabels(
        dis_mask.astype(np.uint8), cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL)
    lut = np.zeros(int(near.max()) + 1, dtype=np.int32)
    lut[near[~dis_mask]] = labels[~dis_mask]
    out = labels.copy()
    out[dis_mask] = lut[near[dis_mask]]
    return out


# Light-accent guard constants (straw-stripe fix, see _despeckle_labels):
_ACCENT_INK_RING_FRAC = 0.6   # non-small ring must be this dominated by ink
_ACCENT_INK_LUM_GAP = 80.0    # component must be this much lighter than the ink
_ACCENT_MIN_PX = 10           # below this it's a stray fleck -- dissolve as usual

# Chromatic-mark guard constants (app-asset icon-glyph fix, it23 B-icongeom;
# GAP_LEDGER 0g + the 0c intent-vs-noise discriminator, measured):
# a small drawn GLYPH PART — the 'r' of "Share", the mail icon's envelope
# fold creases, a letter counter-hole — sits INSIDE one flat field and is
# HUE-SHIFTED from it (white-on-purple, purple-on-white: ab-plane shift
# 48-62). Noise is not: shading daubs / fur fragments are same-hue luminance
# shifts (ab-shift 4.6-6.2 measured on chopchop planks + fox), and AA fringes
# lie BETWEEN two labels (ring split, majority share < 0.85, or their color
# sandwiched between the neighbors'). Populations measured 2026-07-09 on
# app-asset (must-live: 4 glyph parts) vs chopchop/fox/monster (must-die:
# 0 false fires at these thresholds; nearest miss gap 49.7 / ab 36.8 is a
# chopchop leaf-edge highlight, benign either way):
_MARK_MIN_PX = 15             # smallest must-live ('a' counter-hole) = 19
_MARK_FIELD_SHARE = 0.85      # must-live ring majority >= 0.88; AA rings split
_MARK_LUM_GAP = 50.0          # must-live |lum - field| >= 66.2; false <= 49.7
_MARK_CHROMA_AB = 20.0        # must-live CIELAB ab-shift >= 48.3; noise <= 6.2,
                              # AA-on-white fringes <= 18.2
_MARK_DARK_OWN_C = 27.0       # a DARKER-than-field mark must carry its own hue
                              # (CIELAB chroma >= this): shadow shades are
                              # desaturated versions of their field (pizza-box
                              # lid-seam gray C 13.9 on tan, game-assets purple
                              # cast shadows C 21.9 on gray — both must die) vs
                              # drawn dark marks (envelope creases C 52.5,
                              # 'a' counter-hole C 66.2, chest studs C 32.1 —
                              # must live). Lighter marks skip this test (white
                              # text C 6.1 is a legit highlight/glyph).

# Transition-ownership constants (audit24 E1, it24 A-transown; populations
# measured 2026-07-09 on app-asset/fox/chopchop/rabbit (true: ramp shrapnel
# that must dissolve) vs crystals/monster/rabbit-brows (false: drawn thin
# marks that must live) — see research/it24/candidates/A-transown/REPORT.md):
_TRANS_MIN_LUM = 50.0     # never touch true ink (measured ink lum 9-49 run 25;
                          # every true shrapnel label >= 61.7)
_TRANS_MAX_THIN = 3.0     # mean half-width gate; true shrapnel <= 2.9
                          # (app-asset icon moat bands 3.4-4.0 stay — E2's job)
_TRANS_MIN_SHARE2 = 0.85  # ring two-sidedness: top-2 neighbors' ring share
_TRANS_MIN_SHAREB = 0.15  # ... with the minority side substantial
_TRANS_MAX_SEGD = 4.0     # Lab distance to the A<->B segment: true ramps
                          # <= 3.5; crystals drawn facet slivers >= 5.0
_TRANS_T_LO, _TRANS_T_HI = 0.12, 0.88  # interpolation parameter along A->B
_TRANS_MAX_ABLEN = 36.0   # the bounding pair must be color-CLOSE (a shading-
                          # class pair, cf. Depixelizing Pixel Art's two-tier
                          # edge classes): true pairs <= 35.6; crystals
                          # contour-class pairs >= 44.2 (facet vs facet)
_TRANS_SMALLTHIN_PX = 300  # a bound label doesn't count as a bounding REGION
                           # if its whole component is small+thin (a stroke):
                           # protects nested drawn strokes (rabbit brows —
                           # the second "bound" is just the sibling stroke)


def _own_transitions(labels: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Transition-ownership quantize (audit24 root cause E1).

    Every soft transition (AA, JPEG blur, focus falloff) between two color
    regions quantizes into thin mid-tone labels along the edge that render as
    torn dash/speck shrapnel (app-asset bezel, fox shading rims) — the #1
    'looks traced, not drawn' defect. Recraft's rule (VISION.md #2): a ramp
    pixel belongs to one of its two bounding regions; a 2-region transition
    never spawns a third label.

    Mechanism (constants above, all population-measured): mark every thin
    non-ink component whose own color lies ON the Lab segment between its two
    dominant ring labels AND whose bounding pair is itself color-close (a
    shading-family pair — drawn lines between far-apart colors are contour-
    class and sacred). Group marked pixels into 8-connected STACKS (multi-band
    ramps form adjacent bands), take each stack's outer ring excluding other
    marked pixels and excluding small+thin stroke components (not regions):
    if the ring is dominated by exactly two region-grade labels, every marked
    label in the stack is absorbed into the Lab-nearer of the two bounds.
    One-sided or mixed rings keep their pixels (drawn detail on a field —
    rabbit brow strokes; junction zones).
    """
    n = len(centers)
    if n <= 2:
        return labels
    from skimage.color import rgb2lab
    lab = rgb2lab(centers.reshape(1, -1, 3) / 255.0)[0]
    lum = np.array([_luminance(c) for c in centers])
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    h, w = labels.shape
    marked = np.zeros(labels.shape, bool)
    smallthin = np.zeros(labels.shape, bool)
    for ci in range(n):
        mask = (labels == ci).astype(np.uint8)
        if not mask.any():
            continue
        ncomp, comp, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        for k in range(1, ncomp):
            area = int(stats[k, cv2.CC_STAT_AREA])
            x0 = max(0, stats[k, cv2.CC_STAT_LEFT] - 1)
            y0 = max(0, stats[k, cv2.CC_STAT_TOP] - 1)
            x1 = min(w, stats[k, cv2.CC_STAT_LEFT] + stats[k, cv2.CC_STAT_WIDTH] + 1)
            y1 = min(h, stats[k, cv2.CC_STAT_TOP] + stats[k, cv2.CC_STAT_HEIGHT] + 1)
            sub = (comp[y0:y1, x0:x1] == k).astype(np.uint8)
            per = float(cv2.countNonZero(sub - cv2.erode(sub, k3)))
            thin = area / max(per, 1.0)
            if area <= _TRANS_SMALLTHIN_PX and thin <= _TRANS_MAX_THIN:
                smallthin[y0:y1, x0:x1] |= sub.astype(bool)
            if lum[ci] < _TRANS_MIN_LUM or area < 4 or thin > _TRANS_MAX_THIN:
                continue
            ring = cv2.dilate(sub, k3).astype(bool) & (sub == 0)
            neigh = labels[y0:y1, x0:x1][ring]
            if neigh.size == 0:
                continue
            cnts = np.bincount(neigh, minlength=n)
            cnts[ci] = 0
            order = np.argsort(cnts)[::-1]
            if len(order) < 2 or cnts[order[1]] == 0:
                continue
            a_, b_ = int(order[0]), int(order[1])
            tot = float(cnts.sum())
            if (cnts[a_] + cnts[b_]) / tot < _TRANS_MIN_SHARE2 \
                    or cnts[b_] / tot < _TRANS_MIN_SHAREB:
                continue
            ca, cb, cc = lab[a_], lab[b_], lab[ci]
            ab = cb - ca
            L2 = float(ab @ ab)
            if L2 < 1e-9 or L2 > _TRANS_MAX_ABLEN ** 2:
                continue
            t = float((cc - ca) @ ab / L2)
            if not (_TRANS_T_LO <= t <= _TRANS_T_HI):
                continue
            if float(np.linalg.norm(cc - (ca + t * ab))) > _TRANS_MAX_SEGD:
                continue
            marked[y0:y1, x0:x1] |= sub.astype(bool)
    if not marked.any():
        return labels
    out = labels.copy()
    nst, comp, stats, _ = cv2.connectedComponentsWithStats(marked.astype(np.uint8), 8)
    for k in range(1, nst):
        x0 = max(0, stats[k, cv2.CC_STAT_LEFT] - 1)
        y0 = max(0, stats[k, cv2.CC_STAT_TOP] - 1)
        x1 = min(w, stats[k, cv2.CC_STAT_LEFT] + stats[k, cv2.CC_STAT_WIDTH] + 1)
        y1 = min(h, stats[k, cv2.CC_STAT_TOP] + stats[k, cv2.CC_STAT_HEIGHT] + 1)
        sub = comp[y0:y1, x0:x1] == k
        ring = cv2.dilate(sub.astype(np.uint8), k3).astype(bool) & ~sub \
            & ~marked[y0:y1, x0:x1] & ~smallthin[y0:y1, x0:x1]
        neigh = labels[y0:y1, x0:x1][ring]
        if neigh.size == 0:
            continue  # no region-grade bound in sight: keep (stroke island)
        cnts = np.bincount(neigh, minlength=n)
        order = np.argsort(cnts)[::-1]
        if len(order) < 2:
            continue
        a_, b_ = int(order[0]), int(order[1])
        tot = float(cnts.sum())
        if (cnts[a_] + cnts[b_]) / tot < _TRANS_MIN_SHARE2 \
                or cnts[b_] / tot < _TRANS_MIN_SHAREB:
            continue  # one-sided (drawn detail on a field) or mixed junction
        ca, cb = lab[a_], lab[b_]
        ab = cb - ca
        L2 = float(ab @ ab)
        wlab = out[y0:y1, x0:x1]
        for ci in np.unique(labels[y0:y1, x0:x1][sub]):
            tci = float((lab[ci] - ca) @ ab / L2) if L2 > 1e-9 else 0.0
            owner = a_ if tci < 0.5 else b_
            m = sub & (labels[y0:y1, x0:x1] == ci)
            wlab[m] = owner
    return out


# Spike-tip guard constants (monster teeth fix, see _despeckle_labels):
# a sharp spike's tip tapers below pixel width, so the raster anti-aliases it
# into midtones and quantization SEVERS the tip from its parent region
# (measured monster mouth: 8px white tip, parent 4px away across an AA bridge).
_SPIKE_MAX_PX = 60            # tip fragments are tiny (measured teeth: 8-22 px)
_SPIKE_BRIDGE_PX = 5          # max AA-gap tip->parent (measured 4 + 1 margin)
_SPIKE_SURROUND_LUM_GAP = 210.0  # tip must be EXTREMAL vs its surround, not an
                                 # intermediate AA tone. Measured populations:
                                 # every true spike tip (monster teeth + back
                                 # spikes) sits at gap 218 (white 255 on ink
                                 # 37); every chopchop/mountain/crystals AA
                                 # fringe fleck sits at gap <= 204 (midtones
                                 # 104-211 beside ink). Shape tests do NOT
                                 # separate (a severed tip can be a 3x3 blob).
_SPIKE_WELD_W = 2             # reattachment corridor width (measured tip width)


def _despeckle_labels(labels: np.ndarray, min_component_px: int,
                      centers: np.ndarray = None) -> np.ndarray:
    """Dissolve connected components smaller than a floor, in every layer,
    reassigning their pixels to the surrounding regions.

    Line-art clusters (dark/outline colors) get a FAR smaller floor: stroke
    networks legitimately fragment into small pieces (eyes, brows, short line
    segments) — a uniform floor massacres them, which was the seed-lottery
    catastrophe's kill stage (forensics: despeckle erased the whole outline).

    Light-accent guard (straw-stripe fix, mirrors _dissolve_speckle's rules):
    a sub-floor LIGHT component that is INK-LOCKED — once fellow sub-floor
    fragments are excluded, its ring is essentially all ink far darker than
    itself — is a drawn accent (straw stripe, white scratch line), not noise:
    nearest-pixel reassignment would paint it into the ink (striped straw →
    solid black bar). Exempt it. The fellow-fragment exclusion matters
    because stripes sandwich each other (white ring = ink + blue fragments;
    neither alone looks ink-locked, and junking both hands the whole straw to
    the outline). A genuine light fleck sits ON a big fill: its non-small
    ring IS that fill, not ink, so it still dissolves — as do speck-scale
    bits below _ACCENT_MIN_PX.

    Spike-tip guard (monster-teeth fix): a sharp spike on a light region's
    boundary tapers below pixel width at its tip, so the source raster
    anti-aliases the tip into midtones and quantization SEVERS it — the tip
    becomes a tiny same-label island a few px from its parent, bridged by
    sub-floor AA fragments. Junking it cuts the spike to half height (the
    scalloped-teeth defect). Rescue a tiny LIGHT fragment when (a) ANCHORED:
    a *surviving* component of the SAME label lies within _SPIKE_BRIDGE_PX,
    and (b) CONTRAST-CONSISTENT: the fragment out-shines every non-parent
    surviving label around it by _SPIKE_SURROUND_LUM_GAP (a spike tip floats
    over the contrasting background its parent cuts into; a noise daub /
    dither fleck sits beside near-equal tones and fails). A rescued tip is
    WELDED back: a tip-width corridor along the shortest tip->parent path is
    relabeled to the parent (measured: that path follows the spike's true
    flank), refused if it would overwrite any surviving foreign pixel (a
    drawn line is not an AA gap). Exemption without the weld was refuted by
    eye: the bridge reassigns to the dark surround and the tip renders as a
    floating fleck. Unweldable candidates dissolve as usual.
    """
    lum = dark = lab_ab = None
    if centers is not None:
        lum = np.array([_luminance(c) for c in centers])
        dark = lum < DARK_LINE_LUM
        from skimage.color import rgb2lab
        lab_ab = rgb2lab(centers.reshape(1, -1, 3) / 255.0)[0][:, 1:]
    kernel = np.ones((3, 3), np.uint8)
    h, w = labels.shape
    # pass 1: mark every sub-floor component (per-label floors)
    small = np.zeros(labels.shape, dtype=bool)
    for ci in np.unique(labels):
        floor = min_component_px
        if dark is not None and dark[ci]:
            floor = max(6, min_component_px // 10)
        mask = (labels == ci).astype(np.uint8)
        ncomp, comp, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        for k in range(1, ncomp):
            if stats[k, cv2.CC_STAT_AREA] < floor:
                # bbox-local |= (comp == k is False outside its own bbox;
                # the full-frame compare per component was a profiled hotspot)
                bx0, by0 = stats[k, cv2.CC_STAT_LEFT], stats[k, cv2.CC_STAT_TOP]
                bx1 = bx0 + stats[k, cv2.CC_STAT_WIDTH]
                by1 = by0 + stats[k, cv2.CC_STAT_HEIGHT]
                small[by0:by1, bx0:bx1] |= comp[by0:by1, bx0:bx1] == k
    # pass 2: junk sub-floor components unless ink-locked light accents
    junk = np.zeros(labels.shape, dtype=bool)
    for ci in np.unique(labels):
        floor = min_component_px
        if dark is not None and dark[ci]:
            floor = max(6, min_component_px // 10)
        mask = (labels == ci).astype(np.uint8)
        ncomp, comp, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        for k in range(1, ncomp):
            if stats[k, cv2.CC_STAT_AREA] >= floor:
                continue
            if (dark is not None and not dark[ci]
                    and stats[k, cv2.CC_STAT_AREA] >= _ACCENT_MIN_PX):
                x0 = max(0, stats[k, cv2.CC_STAT_LEFT] - 1)
                y0 = max(0, stats[k, cv2.CC_STAT_TOP] - 1)
                x1 = min(w, stats[k, cv2.CC_STAT_LEFT] + stats[k, cv2.CC_STAT_WIDTH] + 1)
                y1 = min(h, stats[k, cv2.CC_STAT_TOP] + stats[k, cv2.CC_STAT_HEIGHT] + 1)
                sub = comp[y0:y1, x0:x1] == k
                ring = cv2.dilate(sub.astype(np.uint8), kernel).astype(bool) & ~sub
                # judge only against SURVIVING neighbors: fellow sub-floor
                # fragments are junk candidates themselves, not absorbers
                ring &= ~small[y0:y1, x0:x1]
                neigh = labels[y0:y1, x0:x1][ring]
                if neigh.size:
                    ink = dark[neigh]
                    # ink-dominated survivor ring + big luminance drop =
                    # drawn accent between ink edges: exempt from despeckle.
                    if (ink.mean() >= _ACCENT_INK_RING_FRAC
                            and lum[ci] >= lum[neigh[ink]].min() + _ACCENT_INK_LUM_GAP):
                        continue
            if (dark is not None and not dark[ci]
                    and stats[k, cv2.CC_STAT_AREA] >= _MARK_MIN_PX):
                # chromatic-mark rescue (it23 B-icongeom, constants above):
                # a small drawn glyph part — letter, envelope fold crease,
                # counter-hole — sits INSIDE one flat non-ink field
                # (ring majority >= 0.85) and is BOTH luminance-contrasting
                # and HUE-SHIFTED from it. Same-hue shading daubs and
                # ring-split AA fringes fail; drawn marks survive.
                x0 = max(0, stats[k, cv2.CC_STAT_LEFT] - 1)
                y0 = max(0, stats[k, cv2.CC_STAT_TOP] - 1)
                x1 = min(w, stats[k, cv2.CC_STAT_LEFT] + stats[k, cv2.CC_STAT_WIDTH] + 1)
                y1 = min(h, stats[k, cv2.CC_STAT_TOP] + stats[k, cv2.CC_STAT_HEIGHT] + 1)
                sub = comp[y0:y1, x0:x1] == k
                ring = cv2.dilate(sub.astype(np.uint8), kernel).astype(bool) & ~sub
                ring &= ~small[y0:y1, x0:x1]      # judge vs survivors only
                neigh = labels[y0:y1, x0:x1][ring]
                if neigh.size:
                    cnts = np.bincount(neigh, minlength=len(centers))
                    maj = int(np.argmax(cnts))
                    if (not dark[maj]
                            and cnts[maj] >= _MARK_FIELD_SHARE * cnts.sum()
                            and abs(lum[ci] - lum[maj]) >= _MARK_LUM_GAP
                            and float(np.hypot(*(lab_ab[ci] - lab_ab[maj])))
                            >= _MARK_CHROMA_AB
                            and (lum[ci] > lum[maj]
                                 or float(np.hypot(*lab_ab[ci]))
                                 >= _MARK_DARK_OWN_C)):
                        continue
            if (dark is not None and not dark[ci]
                    and stats[k, cv2.CC_STAT_AREA] <= _SPIKE_MAX_PX):
                # spike-tip rescue: anchored + contrast-consistent (docstring)
                b = _SPIKE_BRIDGE_PX
                x0 = max(0, stats[k, cv2.CC_STAT_LEFT] - b)
                y0 = max(0, stats[k, cv2.CC_STAT_TOP] - b)
                x1 = min(w, stats[k, cv2.CC_STAT_LEFT] + stats[k, cv2.CC_STAT_WIDTH] + b)
                y1 = min(h, stats[k, cv2.CC_STAT_TOP] + stats[k, cv2.CC_STAT_HEIGHT] + b)
                sub = (comp[y0:y1, x0:x1] == k).astype(np.uint8)
                zone = cv2.dilate(sub, kernel, iterations=b).astype(bool) & (sub == 0)
                wsmall = small[y0:y1, x0:x1]
                wlab = labels[y0:y1, x0:x1]
                surv = zone & ~wsmall             # judge against survivors only
                neigh = wlab[surv]
                same = neigh == ci
                if same.any():
                    others = neigh[~same]
                    if (others.size == 0
                            or lum[ci] >= lum[others].max() + _SPIKE_SURROUND_LUM_GAP):
                        # WELD the tip back onto its parent: exemption alone
                        # leaves an island (the junked AA bridge reassigns to
                        # the dark surround, and the fitter then paints a
                        # floating fleck). Draw a tip-width corridor along the
                        # shortest tip->parent path — measured, this follows
                        # the spike's true flank direction.
                        pmask = surv & (wlab == ci)
                        sy, sx = np.nonzero(sub)
                        py, px = np.nonzero(pmask)
                        d2 = ((sy[:, None] - py[None, :]) ** 2
                              + (sx[:, None] - px[None, :]) ** 2)
                        # never overwrite a SURVIVING foreign pixel: a drawn
                        # dark line between two light areas is a line, not an
                        # AA gap. Take the SHORTEST CLEAN path: the 1px core
                        # must be all junk-candidate (or same-label) px — the
                        # euclidean-nearest pair can graze a surviving dark
                        # px while the true AA gap sits a fraction farther
                        # (measured on the monster tooth). The tip-width band
                        # then paints only such px: survivors never touched.
                        welded = False
                        for oi in np.argsort(d2, axis=None)[:64]:
                            i, j = np.unravel_index(int(oi), d2.shape)
                            q = (int(sx[i]), int(sy[i]))
                            pt = (int(px[j]), int(py[j]))
                            core = np.zeros_like(sub)
                            cv2.line(core, q, pt, 1, 1)
                            if (core.astype(bool) & (wlab != ci) & ~wsmall).any():
                                continue
                            band = np.zeros_like(sub)
                            cv2.line(band, q, pt, 1, _SPIKE_WELD_W)
                            wmask = band.astype(bool) & ((wlab == ci) | wsmall)
                            wlab[wmask] = ci
                            junk[y0:y1, x0:x1][wmask] = False
                            welded = True
                            break
                        if welded:
                            continue
            bx0, by0 = stats[k, cv2.CC_STAT_LEFT], stats[k, cv2.CC_STAT_TOP]
            bx1 = bx0 + stats[k, cv2.CC_STAT_WIDTH]
            by1 = by0 + stats[k, cv2.CC_STAT_HEIGHT]
            junk[by0:by1, bx0:bx1] |= comp[by0:by1, bx0:bx1] == k
    return _reassign_pixels(labels, junk)


def _dissolve_speckle(labels: np.ndarray, centers: np.ndarray,
                      min_area: int) -> np.ndarray:
    """Dissolve small components of NON-dark labels into the surrounding FILL.

    Targets residual daubs (e.g. darker-brown speckle inside chopchop's flat
    tan trunk/planks) that survive `_despeckle_labels` because they sit above
    its floor. Two hard guards keep this from repeating past catastrophes:

    - Dark labels (luminance < DARK_LINE_LUM) are never dissolved — the line
      network stays untouchable.
    - A component is never merged INTO a dark label. Last attempt filled the
      thin white seam between a dark blob and its outline solid; speckle must
      dissolve into fills, never into ink. If the majority-boundary neighbor
      is dark, the largest non-dark neighbor wins instead; if every neighbor
      is dark, the component is left alone.
    """
    out = labels.copy()
    dark = np.array([_luminance(c) < DARK_LINE_LUM for c in centers])
    from skimage.color import rgb2lab
    lab_ab = rgb2lab(centers.reshape(1, -1, 3) / 255.0)[0][:, 1:]
    kernel = np.ones((3, 3), np.uint8)
    h, w = labels.shape
    for ci in np.unique(labels):
        if dark[ci]:
            continue
        mask = (labels == ci).astype(np.uint8)
        ncomp, comp, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        for k in range(1, ncomp):
            if stats[k, cv2.CC_STAT_AREA] >= min_area:
                continue
            x0 = max(0, stats[k, cv2.CC_STAT_LEFT] - 1)
            y0 = max(0, stats[k, cv2.CC_STAT_TOP] - 1)
            x1 = min(w, stats[k, cv2.CC_STAT_LEFT] + stats[k, cv2.CC_STAT_WIDTH] + 1)
            y1 = min(h, stats[k, cv2.CC_STAT_TOP] + stats[k, cv2.CC_STAT_HEIGHT] + 1)
            sub = comp[y0:y1, x0:x1] == k
            ring = cv2.dilate(sub.astype(np.uint8), kernel).astype(bool) & ~sub
            neigh = out[y0:y1, x0:x1][ring]
            if neigh.size == 0:
                continue
            counts = np.bincount(neigh, minlength=len(centers))
            counts[ci] = 0
            counts[dark] = 0                      # fills only, never ink
            if counts.max() == 0:
                continue                          # ink-locked: leave it
            # daub-vs-facet guard (orchestrator debug 1): a NOISE daub sits
            # inside ONE flat fill -- its ring is dominated by a single
            # non-dark label. A gem FACET sits in a mosaic (ring split among
            # facets and dark edge lines) -- never dissolve those (crystals
            # regression: real facets were being eaten).
            if counts.max() < 0.6 * neigh.size:
                continue
            # darker-only guard (orchestrator debug 2): noise daubs are DARK
            # stains on their fill; LIGHT accents are drawn intent (mountain
            # cloud wisp, plank-top highlight -- Recraft keeps both). Never
            # dissolve a component lighter than its absorber.
            tgt = int(np.argmax(counts))
            if _luminance(centers[ci]) >= _luminance(centers[tgt]):
                continue
            # chromatic-mark guard (it23 B-icongeom, constants above): a
            # darker-than-field component that is strongly HUE-SHIFTED from
            # its absorber is a drawn mark (mail-icon envelope creases on
            # white), not a shading daub (daubs are same-hue: ab-shift <= 6
            # measured; creases 48). Measured 0 false keeps on
            # chopchop/fox/monster at these thresholds.
            if (stats[k, cv2.CC_STAT_AREA] >= _MARK_MIN_PX
                    and abs(_luminance(centers[ci]) - _luminance(centers[tgt]))
                    >= _MARK_LUM_GAP
                    and float(np.hypot(*(lab_ab[ci] - lab_ab[tgt])))
                    >= _MARK_CHROMA_AB
                    and float(np.hypot(*lab_ab[ci])) >= _MARK_DARK_OWN_C):
                continue
            region = out[y0:y1, x0:x1]
            region[sub] = tgt
    return out


# Same-fill shrapnel absorption constants (OVER-FRAGMENT, auto-loop 2026-07-10;
# populations measured on app-asset post-cleanup label map, 159 small comps):
# shrapnel that must merge (interleaved shadow-tone fragments L4/L10/L12,
# ramp leftovers) sits at palette dE 3.2-7.2 AND source-side dE <= 6.6; drawn
# detail that must live (glyph parts, mail-icon creases, screen highlights)
# sits at palette dE >= 10.5 or source-side dE >= 8.9. The SOURCE-side test is
# the evidence gate: a fragment whose own source pixels match the neighbor's
# local source pixels is a quantizer artifact (one flat tone split across a
# centroid boundary / an AA band) — the source shows NO real boundary there.
_SHRAP_MAX_FRAC = 0.002   # comp area cap, fraction of frame (~1400px at 1024)
_SHRAP_MAX_DPAL = 8.0     # palette CIEDE2000 guard (shrapnel <= 7.2; next 10.5)
_SHRAP_MAX_DSRC = 4.0     # source-evidence CIEDE2000 (comp mean vs neighbor's
                          # near-band mean in the RAW image; gate-swept: 3.0
                          # gave +0.0063/color+0.0017, 5.0 gave +0.0057/
                          # color+0.0024, 4.0 gave +0.0069/color+0.0009)
_SHRAP_MIN_RING = 8       # px; below this the evidence is too thin to act on
_SHRAP_PASSES = 3         # cascade: multi-band ramps merge one band per pass


def _absorb_same_fill_shrapnel(labels: np.ndarray, centers: np.ndarray,
                               src: np.ndarray,
                               lock: np.ndarray = None) -> np.ndarray:
    """Merge small components into an adjacent near-same-fill region when the
    SOURCE image shows no real boundary between them (OVER-FRAGMENT fix).

    The cleanup chain deliberately protects dark labels everywhere (despeckle
    floor /10, mode-filter immunity, _dissolve_speckle skips them) to keep
    line art alive — so dark-on-dark shadow shrapnel has NO cleanup path:
    k-means splits one soft shadow into 2-3 near-identical dark tones whose
    tiny interleaved components each become a path (app-asset x[0.54-0.62]
    y[0.60-0.71]: 7 paths vs Recraft's 3). This pass is the evidence-gated
    reverse of a split, label-color-agnostic and component-local:

    absorb comp -> neighbor iff
      * comp is small (area <= _SHRAP_MAX_FRAC of frame),
      * comp contains no locked thin-line pixel (drawn strokes are sacred),
      * neighbor's palette color is near-same (dE <= _SHRAP_MAX_DPAL), and
      * EVIDENCE: comp's own mean SOURCE color is within _SHRAP_MAX_DSRC of
        the neighbor's mean SOURCE color in a 2px band beside the comp —
        i.e. in the source there is no boundary here, the split is ours.

    Among passing neighbors the source-closest wins (a ramp band joins the
    side it actually resembles, cf. _own_transitions). Drawn marks keep
    their fragment: any visible mark contrasts with its field in the source
    (measured >= 8.9 dE), so the evidence gate refuses the merge. Guards are
    dE-based (scale-free) and frame-relative (scale-invariant)."""
    n = len(centers)
    if n <= 1 or src is None or src.ndim != 3:
        return labels
    from skimage.color import rgb2lab, deltaE_ciede2000
    lab = rgb2lab(centers.reshape(1, -1, 3) / 255.0)[0]

    def _de(mean_a, mean_b):
        la = rgb2lab(np.asarray(mean_a, np.float64).reshape(1, 1, 3) / 255.0)
        lb = rgb2lab(np.asarray(mean_b, np.float64).reshape(1, 1, 3) / 255.0)
        return float(deltaE_ciede2000(la, lb))

    h, w = labels.shape
    max_area = _SHRAP_MAX_FRAC * h * w
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    srcf = src[..., :3].astype(np.float32)
    out = labels.copy()
    for _ in range(_SHRAP_PASSES):
        merged = 0
        for ci in range(n):
            mask = (out == ci).astype(np.uint8)
            if not mask.any():
                continue
            ncomp, comp, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
            for k in range(1, ncomp):
                if stats[k, cv2.CC_STAT_AREA] > max_area:
                    continue
                x0 = max(0, stats[k, cv2.CC_STAT_LEFT] - 3)
                y0 = max(0, stats[k, cv2.CC_STAT_TOP] - 3)
                x1 = min(w, stats[k, cv2.CC_STAT_LEFT]
                         + stats[k, cv2.CC_STAT_WIDTH] + 3)
                y1 = min(h, stats[k, cv2.CC_STAT_TOP]
                         + stats[k, cv2.CC_STAT_HEIGHT] + 3)
                sub = (comp[y0:y1, x0:x1] == k).astype(np.uint8)
                subb = sub.astype(bool)
                if lock is not None and (lock[y0:y1, x0:x1] & subb).any():
                    continue
                wl = out[y0:y1, x0:x1]
                ring = cv2.dilate(sub, k3).astype(bool) & ~subb
                neigh = wl[ring]
                neigh = neigh[neigh != ci]
                if neigh.size < _SHRAP_MIN_RING:
                    continue
                cnts = np.bincount(neigh, minlength=n)
                ws = srcf[y0:y1, x0:x1]
                cmean = ws[subb].mean(0)
                band = cv2.dilate(sub, k3, iterations=2).astype(bool) & ~subb
                best, best_d = -1, 1e9
                for nb in np.flatnonzero(cnts >= _SHRAP_MIN_RING):
                    if float(deltaE_ciede2000(lab[ci][None, None],
                                              lab[nb][None, None])) \
                            > _SHRAP_MAX_DPAL:
                        continue
                    nbm = band & (wl == nb)
                    if int(nbm.sum()) < _SHRAP_MIN_RING:
                        continue
                    d = _de(cmean, ws[nbm].mean(0))
                    if d <= _SHRAP_MAX_DSRC and d < best_d:
                        best, best_d = int(nb), d
                if best >= 0:
                    wl[subb] = best
                    merged += 1
        if merged == 0:
            break
    return out


# Blend-band dissolution constants (AA TRANSITION MUD, auto-loop 2026-07-10,
# COLOR iteration; populations measured on all 11 gate-target final label
# maps). At a boundary between two flat regions the AA/JPEG blur ramp
# quantizes into a thin third label hugging the edge ("mud") that
# _own_transitions cannot touch: its bounding pair is color-FAR (ablen > 36,
# e.g. ink vs fill), a contour-class edge by the shipped rule. The honest
# negative banked in RESEARCH_LOG run 54 ("high-contrast shrapnel subclass
# not color-separable") is resolved here with SOURCE-side evidence plus the
# already-validated neutral-ink test from contours_exp stroke candidacy:
#   fire population (chopchop ink skirts 30-500px, fox in-ink pale debris,
#     mountain ridge fringe, pizza-box rim dashes, shield outline mud):
#     source-segment t 0.15-0.84, segd <= 4.7, t-spread >= 0.35, thin <= 4.6,
#     and every one bounded by NEUTRAL ink (RGB spread 2-27) or a
#     shading-class pair (pal ablen 22-36).
#   must-keep population, all REFUSED with margin:
#     crystals drawn facet slivers: dark bounds are SATURATED (spread
#       56-147 vs true ink <= 27) and pairs contour-class (ablen 44-67);
#       the pale gem streak also sits at t=0.88 > 0.85,
#     app-asset icon shadow moat (soft-shadow REGION, E2's job): 1995 px
#       > _BLEND_MAX_PX (bands hug edges; big mid-tone areas are shadows),
#     rabbit brows / drawn thin marks: ink-locked, or their color clusters
#       at its own tone (t-spread below floor) instead of SPANNING the ramp.
_BLEND_MIN_PX = 24        # smaller mud is despeckle/shrapnel territory
_BLEND_MAX_PX = 250       # dash/rim mud only. Above this the population mixes
                          # with DRAWN soft-shading bands whose color is also
                          # the ink<->fill blend (fox iris crescent 469px, fur
                          # tuft 428px — Recraft keeps both; eye-verified) —
                          # not separable by blend-position/spread evidence.
_BLEND_MAX_THIN = 5.0     # mean half-width: a band hugs its boundary
_BLEND_MIN_SHARE2 = 0.80  # ring two-sidedness (top-2 neighbor share)
_BLEND_MIN_SHAREB = 0.10
_BLEND_T_LO, _BLEND_T_HI = 0.15, 0.85  # source blend position along A->B
_BLEND_MAX_SEGD = 5.0     # Lab distance to the source A<->B segment
_BLEND_MIN_TSP = 0.35     # ramp evidence: pixel t p90-p10 spans the segment
                          # (a drawn intermediate tone clusters at ONE t)
_BLEND_INK_LUM = 60.0     # arm 1: a bound is true ink — dark AND near-
_BLEND_INK_SPREAD = 45    # neutral (max-min RGB; contours_exp stroke rule —
                          # crystals' saturated dark facet edges fail this)
_BLEND_PAIR_AB = 36.0     # arm 2: shading-class pair (= _TRANS_MAX_ABLEN)
_BLEND_PASSES = 2         # multi-band ramps dissolve one band per pass


def _dissolve_blend_bands(labels: np.ndarray, centers: np.ndarray,
                          src: np.ndarray,
                          lock: np.ndarray = None) -> np.ndarray:
    """Dissolve AA-ramp "mud" bands into their two bounding regions (COLOR).

    A thin component sandwiched between exactly two region-grade labels whose
    own SOURCE color is the blend of the two bounds' SOURCE colors (on the
    Lab segment between them) — and whose pixels SPAN that segment — is a
    quantized anti-alias/blur ramp, not drawing. Recraft's rule (VISION #2):
    a 2-region transition never spawns a third shape. Unlike
    _own_transitions (palette-space, shading-class pairs only) this handles
    the HIGH-CONTRAST subclass (ink vs fill) by requiring either a
    neutral-ink bound or a shading-class pair, so crystals' saturated drawn
    facet slivers never qualify (constants above, population-measured).

    Each mud pixel goes to the side its source color is nearer — a midline
    split that lands the new crisp boundary on the ramp's 50% crossing.
    Locked thin-line pixels (drawn strokes) are sacred."""
    n = len(centers)
    if n <= 2 or src is None or src.ndim != 3:
        return labels
    from skimage.color import rgb2lab
    lab_pal = rgb2lab(centers.reshape(1, -1, 3) / 255.0)[0]
    h, w = labels.shape
    srcf = src[..., :3].astype(np.float32)
    lab_src = rgb2lab(srcf / 255.0)
    # per-pixel OWNERSHIP votes use a 3x3-mean source (JPEG-noise denoise) so
    # the split boundary comes out clean; the evidence STATISTICS use the raw
    # source (thresholds above were population-measured on it).
    lab_smooth = rgb2lab(cv2.blur(srcf, (3, 3)) / 255.0)
    lum = np.array([_luminance(c) for c in centers])
    spread = centers.astype(np.int32).max(1) - centers.astype(np.int32).min(1)
    ink_like = (lum < _BLEND_INK_LUM) & (spread <= _BLEND_INK_SPREAD)
    # stroke-grade labels feed the centerline layer whose width is calibrated
    # GLOBALLY from the ink mask (contours_exp) — adding even a small skirt
    # band to one changes every stroke's rendered width (measured: chopchop
    # tile regressions far from any dissolved band). Mud pixels therefore
    # NEVER join a stroke-grade bound: the fill side takes the whole band and
    # the untouched ink stroke keeps painting the crisp boundary on top.
    stroke_grade = (lum < DARK_LINE_LUM) \
        & ((lum < 60.0) | (spread <= _BLEND_INK_SPREAD))
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    out = labels.copy()
    for _ in range(_BLEND_PASSES):
        changed = 0
        for ci in range(n):
            mask = (out == ci).astype(np.uint8)
            if not mask.any():
                continue
            ncomp, comp, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
            for k in range(1, ncomp):
                area = int(stats[k, cv2.CC_STAT_AREA])
                if not (_BLEND_MIN_PX <= area <= _BLEND_MAX_PX):
                    continue
                x0 = max(0, stats[k, cv2.CC_STAT_LEFT] - 3)
                y0 = max(0, stats[k, cv2.CC_STAT_TOP] - 3)
                x1 = min(w, stats[k, cv2.CC_STAT_LEFT]
                         + stats[k, cv2.CC_STAT_WIDTH] + 3)
                y1 = min(h, stats[k, cv2.CC_STAT_TOP]
                         + stats[k, cv2.CC_STAT_HEIGHT] + 3)
                sub = (comp[y0:y1, x0:x1] == k).astype(np.uint8)
                subb = sub.astype(bool)
                if lock is not None and (lock[y0:y1, x0:x1] & subb).any():
                    continue
                per = float(cv2.countNonZero(sub - cv2.erode(sub, k3)))
                if area / max(per, 1.0) > _BLEND_MAX_THIN:
                    continue
                ring = cv2.dilate(sub, k3).astype(bool) & ~subb
                wl = out[y0:y1, x0:x1]
                neigh = wl[ring]
                neigh = neigh[neigh != ci]
                if neigh.size < _SHRAP_MIN_RING:
                    continue
                cnts = np.bincount(neigh, minlength=n)
                order = np.argsort(cnts)[::-1]
                a_, b_ = int(order[0]), int(order[1])
                if cnts[b_] == 0:
                    continue
                tot = float(cnts.sum())
                if (cnts[a_] + cnts[b_]) / tot < _BLEND_MIN_SHARE2 \
                        or cnts[b_] / tot < _BLEND_MIN_SHAREB:
                    continue
                if not (ink_like[a_] or ink_like[b_]
                        or float(np.linalg.norm(lab_pal[a_] - lab_pal[b_]))
                        <= _BLEND_PAIR_AB):
                    continue  # contour-class pair, no neutral-ink bound
                band = cv2.dilate(sub, k3, iterations=2).astype(bool) & ~subb
                wsrc = lab_src[y0:y1, x0:x1]
                la = wsrc[band & (wl == a_)]
                lb = wsrc[band & (wl == b_)]
                if len(la) < _SHRAP_MIN_RING or len(lb) < _SHRAP_MIN_RING:
                    continue
                ca, cb = la.mean(0), lb.mean(0)
                ab = cb - ca
                L2 = float(ab @ ab)
                if L2 < 1e-9:
                    continue
                cme = wsrc[subb].mean(0)
                t = float((cme - ca) @ ab / L2)
                if not (_BLEND_T_LO <= t <= _BLEND_T_HI):
                    continue
                if float(np.linalg.norm(cme - (ca + t * ab))) \
                        > _BLEND_MAX_SEGD:
                    continue
                tpix = (wsrc[subb] - ca) @ ab / L2
                if float(np.percentile(tpix, 90) - np.percentile(tpix, 10)) \
                        < _BLEND_MIN_TSP:
                    continue
                if stroke_grade[a_] and stroke_grade[b_]:
                    continue          # would have to grow ink: leave it
                if stroke_grade[a_] or stroke_grade[b_]:
                    # ink-bounded mud: the whole band joins the FILL side.
                    # The untouched ink stroke keeps painting the crisp
                    # boundary on top; a midline split was measured to
                    # ripple every stroke via the global width calibration.
                    wl[subb] = b_ if stroke_grade[a_] else a_
                else:
                    tvote = (lab_smooth[y0:y1, x0:x1][subb] - ca) @ ab / L2
                    wl[subb] = np.where(tvote < 0.5, a_, b_)
                changed += 1
        if changed == 0:
            break
    return out


def _resnap_fill_boundaries(labels: np.ndarray, centers: np.ndarray,
                            src: np.ndarray, reach: int = 2) -> np.ndarray:
    """Re-snap fill<->fill boundary ribbons to the source's 50% ramp crossing.

    The zero-width case of transition ownership: even when the AA/blur ramp
    between two fills mints no third label, nearest-CENTROID assignment puts
    the boundary where pixel color crosses the midpoint of the two GLOBAL
    centroids — not where the LOCAL ramp actually crosses halfway between its
    two plateaus. The systematic offset (highlight bands painted wide, shadow
    edges displaced) is the largest anchored-COLOR bucket vs Recraft. For
    every adjacent fill-grade pair, ribbon pixels within `reach` px of the
    interface re-vote against the pair's plateau colors sampled just beyond
    the ribbon; stroke-grade labels are untouchable (their mask feeds the
    GLOBAL stroke width calibration; touching it ripples every stroke).

    Design notes from the measured variant ladder (this loop iteration):
    per-pixel flank vetoes orphan slivers (app-asset census +0.0095),
    segment-local plateaus scallop the contour between segments (elephant
    flow +0.026), median plateaus and sigma-relative contrast floors each
    traded away more than they saved. Whole-pair voting with a hard local
    contrast floor is the only variant that nets positive corpus-wide.
    """
    n = len(centers)
    if n <= 1 or src is None or src.ndim != 3:
        return labels
    from skimage.color import rgb2lab
    lum = np.array([_luminance(c) for c in centers])
    spread = centers.astype(np.int32).max(1) - centers.astype(np.int32).min(1)
    stroke_grade = (lum < DARK_LINE_LUM) & ((lum < 60.0) | (spread <= 45))
    srcf = src[..., :3].astype(np.float32)
    lab_smooth = rgb2lab(cv2.blur(srcf, (3, 3)) / 255.0)
    out = labels.copy()
    # adjacent pairs + interface lengths via 4-neighbor shifts
    right = (labels[:, :-1] != labels[:, 1:])
    down = (labels[:-1, :] != labels[1:, :])
    pk = []
    for m, (sa, sb) in ((right, (labels[:, :-1], labels[:, 1:])),
                        (down, (labels[:-1, :], labels[1:, :]))):
        la, lb = sa[m], sb[m]
        lo = np.minimum(la, lb).astype(np.int64)
        hi = np.maximum(la, lb).astype(np.int64)
        pk.append(lo * n + hi)
    keys, cnts = np.unique(np.concatenate(pk), return_counts=True)
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    for key, blen in zip(keys, cnts):
        a_, b_ = int(key // n), int(key % n)
        if blen < 30 or stroke_grade[a_] or stroke_grade[b_]:
            continue
        ma = out == a_
        mb = out == b_
        iface = (cv2.dilate(ma.astype(np.uint8), k3).astype(bool) & mb) | \
                (cv2.dilate(mb.astype(np.uint8), k3).astype(bool) & ma)
        d2 = cv2.dilate(iface.astype(np.uint8), k3,
                        iterations=max(1, reach)).astype(bool)
        d3 = cv2.dilate(d2.astype(np.uint8), k3)
        d6 = cv2.dilate(d3, k3, iterations=3).astype(bool)
        d3 = d3.astype(bool)
        ribbon = d2 & (ma | mb)
        pa = ma & d6 & ~d3
        pb = mb & d6 & ~d3
        if int(pa.sum()) < 30 or int(pb.sum()) < 30:
            continue
        ca = lab_smooth[pa].mean(0)
        cb = lab_smooth[pb].mean(0)
        ab = cb - ca
        L2 = float(ab @ ab)
        # local plateau contrast floor, two measured failure classes below:
        # (a) WIDE smooth gradients — the 3-6px "plateaus" are still mid-ramp
        #     and near-equal (mountain sky bands, the crystals banding class):
        #     boundary placement there is arbitrary, re-voting only jitters
        #     the contour (census churn, measured at floor 0);
        # (b) fills split at TEXTURE/JPEG-noise scale — votes are noise and
        #     scramble a settled boundary wholesale (pizza-box lid tans at
        #     local dE 10.6 under heavy mottle: 4077 of 9899 ribbon px
        #     flipped, flow +0.022, measured).
        # True mud boundaries measure local dE 18-56 (fox/chopchop pairs).
        if L2 < 14.0 ** 2:
            continue
        t = (lab_smooth[ribbon] - ca) @ ab / L2
        # decisive votes only: mid-ramp pixels (|t-0.5|<=0.1) keep their old
        # side, so weak/noisy evidence never wiggles a settled boundary.
        rl = out[ribbon]
        newl = np.where(t < 0.4, a_, np.where(t > 0.6, b_, rl))
        out[ribbon] = newl
    return out
# Structured-region split constants (UNDER-RESOLVE fix, autoresearch
# 2026-07-10). Root cause (probe-verified on crystals x[0.54-0.65]
# y[0.52-0.65]: ours 16 paths vs Recraft 58): adjacent drawn facets share ONE
# global k-means colour label, so they fuse into one connected component and
# one path — no despeckle/min_area change can recover them. Fix: LOCAL
# re-segmentation, evidence-gated so shading/gradients never split.
# Populations measured 2026-07-10 (probe_split, post-cleanup label maps,
# interior fraction of px with Sobel/4 magnitude >= 12):
#   must-split  (crystals facet components incl. the low-contrast defect
#               region x[.54-.65] y[.52-.65]): 0.079-0.484, sub-boundary edge
#               coincidence 0.62-1.00, sub-center Lab dE 16-46
#   must-not    (rabbit shading <= 0.079 with interior p90 magnitude 5-7,
#               elephant, mountain sky/clouds): fail the interior gate AND,
#               decisively, a smooth gradient that k-means DOES split puts
#               the sub-boundary on the ramp where the local magnitude is
#               far below _SPLIT_EDGE_MAG (rabbit shading p90 5-7 vs gate
#               12), so the boundary-coincidence gate kills banding splits
#               independently of the interior gate.
_SPLIT_EDGE_MAG = 12.0     # Sobel/4 per-px magnitude that counts as drawn edge
_SPLIT_MIN_PX = 500        # component must be big enough to hold >1 shape
_SPLIT_MIN_INTERIOR = 100  # need a real interior sample after 2px erosion
_SPLIT_EDGE_FRAC = 0.03    # interior drawn-edge density ENTRY gate. Lowered
                           # 0.075 -> 0.03 (it66): this is only the entry —
                           # a low-ef survivor must prove itself on the
                           # OUTCOME axes instead (maxde >= _SPLIT_RESCUE_DE
                           # below). Population re-measured 2026-07-12 on all
                           # 11 gate targets, ef in [0.02, 0.075):
                           #   fire (maxde >= 17 & bnd >= 0.6): crystals teal
                           #     streaks maxde 19.7-27.1 bnd 1.0, crystals
                           #     dark-red 17.1/1.0, chopchop trunk knot
                           #     25.3/1.0, mountain terrain band 18.8/0.955
                           #     — all drawn structure by eye
                           #   refused: fox inner-ear 16.4 (gate-measured
                           #     census regression — Recraft keeps ONE tone),
                           #     app-asset purple shadow moat (bnd .66, maxde
                           #     6.7), elephant shading pockets (maxde <=
                           #     11.6), shield tans (<= 12.1), rabbit (9.5),
                           #     fox body shading (14.5-15.8), chopchop
                           #     fronds (bnd 0.396) — weak on the dE axis or
                           #     boundary off the drawn edges
_SPLIT_EDGE_SOLID = 0.075  # the original ef floor = the solid-evidence band;
                           # below it the rescue-dE bar applies
_SPLIT_BND_FRAC = 0.60     # sub-boundary px must sit ON drawn edges
_SPLIT_MERGE_DE = 9.0      # fold near-duplicate local k-means sub-centers
_SPLIT_MIN_DE = 12.0       # surviving sub-regions must be this separated
                           # (lowering to 10 gate-measured WORSE: the dE
                           # 10-12 splits are census poison corpus-wide)
_SPLIT_STRONG_DE = 16.0    # joint quality gate: a split in the weak band
_SPLIT_STRONG_EF = 0.12    # (maxde < 16 AND interior edge frac < 0.12) is
                           # single-pocket shading noise, not a mosaic —
                           # measured: every elephant/shield regression split
                           # is weak on BOTH axes (ef<=0.138 & de<=15.6, only
                           # one exception) while crystals/fox/chopchop wins
                           # are strong on at least one (defect-region split
                           # ef 0.139 @ de 12.7; chromatic facets de 16-45)
_SPLIT_SUB_MIN_PX = 40     # sub-fragments below this absorb into siblings
_SPLIT_KMAX = 4            # local k-means size (facet mosaics are 2-4 tones;
                           # k=6, area-adaptive k, and per-pair boundary
                           # healing ALL gate-measured worse: extra clusters
                           # mint boundaries off the drawn edges, and healed
                           # partial splits leak paths census punishes)
_SPLIT_MAX_NEW = 128       # per-image cap on appended labels (runaway guard;
                           # crystals pass 1 alone mints ~55)
_SPLIT_PASSES = 2          # recurse once into just-split regions: a facet
                           # MOSAIC holds more than _SPLIT_KMAX tones, so the
                           # remainder still shows interior structure and
                           # splits again; a clean flat region's remainder
                           # fails the evidence gates and stops (measured:
                           # elephant/shield fire 1-5 single-pocket splits,
                           # crystals fires 42 mosaic splits)
_SPLIT_PROTECT_OVL = 0.3   # never split gradflat-stamped regions
# Ink-skip refinement (UNDER-RESOLVE, it66): "ink is sacred" now uses the
# SAME candidacy test as the stroke layer (contours_exp._stroke_elements):
# a label can only become ink when truly dark (lum < 60 — colored ink like
# rabbit navy) or dark AND near-neutral (spread <= 45). A mid-dark SATURATED
# label (60 <= lum < DARK_LINE_LUM, spread > 45) is by that same rule a
# colored glyph/gem FILL (pizza letterforms lum~76 spr 151, crystals gem
# fills spr 118-164) — the stroke layer refuses it, so the splitter
# protecting it as "ink" only suppressed drawn facet structure. Measured on
# the crystals defect region x[.52-.62] y[.50-.60]: the dark-red wave labels
# rgb(154,23,7) lum 60.3 spr 147 PASS all three evidence gates (ef .238/.103,
# bnd 1.0/.99, maxde 17.3/24.0) and were blocked ONLY by the old blanket
# lum<96 skip; true-ink labels (chopchop outlines lum 9-49 near-neutral,
# rabbit navy lum<60) remain skipped via the two arms below.
_SPLIT_INK_LUM = 60.0      # truly-dark arm (any hue may be colored ink)
_SPLIT_INK_SPREAD = 45     # mid-dark arm: near-neutral RGB spread = ink
_SPLIT_DARK_SPREAD = 70    # ... truly-dark ESCAPE: measured colored-ink tops
                           # out at RGB spread 59 (rabbit navy 19,3,62 — the
                           # corpus' only exemplar); truly-dark gem/glyph
                           # fills sit at 85-94 (crystals maroon-purple l6
                           # spr 85, shield rust l10 spr 94). Beyond 70 the
                           # label is a saturated FILL, splittable under the
                           # SAME evidence gates as every other label. No
                           # extra dE bar for this class: measured corpus
                           # fires are crystals l6 19.4/28.9 (facet mosaics;
                           # low-ef so the joint gate demands >= 16 anyway)
                           # and shield l10 13.6/14.9 (ef-STRONG .178/.213
                           # rim structure — measured shield overall -0.0008,
                           # census -0.0023, flow -0.0015; a >= 16 bar was
                           # costing that win for no measured protection).
_SPLIT_RESCUE_DE = 17.0    # low-ef rescue band (ef < _SPLIT_EDGE_SOLID)
                           # demands stronger colour proof than the joint
                           # gate's 16: fires 17.1/18.8/19.7/25.3/27.1
                           # (crystals dark-red + teals, mountain terrain,
                           # chopchop knot) vs refused 16.4 (fox inner-ear —
                           # source-real but Recraft draws ONE tone there;
                           # gate-measured fox census +0.004) and 16.3


def _split_structured_regions(labels: np.ndarray, centers: np.ndarray,
                              img: np.ndarray,
                              protect: np.ndarray = None
                              ) -> Tuple[np.ndarray, np.ndarray]:
    """Locally-adaptive label split for regions with real internal structure.

    For every large non-dark component whose INTERIOR still contains strong
    source edges (drawn facet lines, glyph detail — not shading ramps), re-run
    a small local k-means (k<=4) on the source pixels under its mask and give
    each surviving sub-region its own label, so downstream emission draws the
    detail Recraft draws. Three independent evidence gates (constants above)
    keep this strictly local and kill the over-split failure mode:
    interior edge density, sub-boundary/edge coincidence, sub-center
    separation. Possible-ink labels (the stroke layer's candidacy class:
    truly dark, or dark and near-neutral — see _SPLIT_INK_LUM/_SPLIT_INK_SPREAD)
    and gradflat-stamped regions are untouched.
    """
    n0 = len(centers)
    lum = [_luminance(c) for c in centers]
    spread = [int(max(c)) - int(min(c)) for c in centers]
    from skimage.color import rgb2lab

    mag = np.zeros(img.shape[:2], np.float32)
    for c in range(3):
        ch = img[..., c].astype(np.float32)
        gx = cv2.Sobel(ch, cv2.CV_32F, 1, 0, ksize=3) / 4.0
        gy = cv2.Sobel(ch, cv2.CV_32F, 0, 1, ksize=3) / 4.0
        mag = np.maximum(mag, np.hypot(gx, gy))
    edge = mag >= _SPLIT_EDGE_MAG
    k3 = np.ones((3, 3), np.uint8)
    h, w = labels.shape
    out = labels.copy()
    new_centers = []
    worklist = list(range(n0))
    for _pass in range(_SPLIT_PASSES):
        touched = []
        for ci in worklist:
            # possible ink is sacred (stroke-layer candidacy + saturation
            # escape for truly-dark fills — constants above)
            if lum[ci] < DARK_LINE_LUM:
                if lum[ci] < _SPLIT_INK_LUM:
                    if spread[ci] <= _SPLIT_DARK_SPREAD:
                        continue        # truly dark, plausibly colored ink
                elif spread[ci] <= _SPLIT_INK_SPREAD:
                    continue            # mid-dark near-neutral = ink
            mask = (out == ci).astype(np.uint8)
            ncomp, comp, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
            for k in range(1, ncomp):
                if len(new_centers) >= _SPLIT_MAX_NEW:
                    break
                area = int(stats[k, cv2.CC_STAT_AREA])
                if area < _SPLIT_MIN_PX:
                    continue
                x0 = max(0, stats[k, cv2.CC_STAT_LEFT] - 1)
                y0 = max(0, stats[k, cv2.CC_STAT_TOP] - 1)
                x1 = min(w, stats[k, cv2.CC_STAT_LEFT] + stats[k, cv2.CC_STAT_WIDTH] + 1)
                y1 = min(h, stats[k, cv2.CC_STAT_TOP] + stats[k, cv2.CC_STAT_HEIGHT] + 1)
                sub = comp[y0:y1, x0:x1] == k
                if protect is not None and \
                        protect[y0:y1, x0:x1][sub].mean() > _SPLIT_PROTECT_OVL:
                    continue                    # gradflat idealization stands
                interior = cv2.erode(sub.astype(np.uint8), k3,
                                     iterations=2).astype(bool)
                if interior.sum() < _SPLIT_MIN_INTERIOR:
                    continue
                ewin = edge[y0:y1, x0:x1]
                ef = float(ewin[interior].mean())
                if ef < _SPLIT_EDGE_FRAC:
                    continue                    # flat/shaded: no structure
                # local k-means on the source pixels under the component mask
                px = img[y0:y1, x0:x1][sub].reshape(-1, 3).astype(np.float32)
                kk = min(_SPLIT_KMAX, len(px))
                if kk < 2:
                    continue
                cv2.setRNGSeed(1234567)
                crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                        15, 1.0)
                _, ll, cc = cv2.kmeans(px, kk, None, crit, 2,
                                       cv2.KMEANS_PP_CENTERS)
                ll = ll.ravel().astype(np.int32)
                cc = np.clip(cc, 0, 255)
                labc = rgb2lab(cc.reshape(1, -1, 3) / 255.0)[0]
                merge = np.arange(kk)
                for i in range(kk):
                    for j in range(i + 1, kk):
                        if merge[i] != i or merge[j] != j:
                            continue
                        if np.linalg.norm(labc[i] - labc[j]) < _SPLIT_MERGE_DE:
                            merge[j] = i
                ll = merge[ll]
                sizes = np.bincount(ll, minlength=kk)
                floor = max(_SPLIT_SUB_MIN_PX, int(0.04 * area))
                keep = [s for s in range(kk)
                        if merge[s] == s and sizes[s] >= floor]
                if len(keep) < 2:
                    continue
                # px of dropped clusters -> colour-nearest kept center
                bad = ~np.isin(ll, keep)
                if bad.any():
                    d = ((px[bad][:, None, :] - cc[None, keep, :]) ** 2).sum(2)
                    ll[bad] = np.array(keep)[d.argmin(1)]
                slab = np.full(sub.shape, -1, np.int32)
                slab[sub] = ll
                # local mode smooth (de-jag) among kept sub-labels only
                votes = np.stack([cv2.boxFilter((slab == s).astype(np.float32),
                                                -1, (3, 3)) for s in keep])
                smoothed = np.array(keep, np.int32)[votes.argmax(0)]
                slab[sub] = smoothed[sub]
                # absorb tiny sub-fragments into their spatial sibling
                junk = np.zeros(sub.shape, bool)
                for s in keep:
                    sm = (slab == s).astype(np.uint8)
                    nc2, cmp2, st2, _ = cv2.connectedComponentsWithStats(sm, 8)
                    for k2 in range(1, nc2):
                        if st2[k2, cv2.CC_STAT_AREA] < _SPLIT_SUB_MIN_PX:
                            junk |= cmp2 == k2
                ok = sub & ~junk
                if junk.any() and ok.any():
                    _, near = cv2.distanceTransformWithLabels(
                        (~ok).astype(np.uint8), cv2.DIST_L2, 3,
                        labelType=cv2.DIST_LABEL_PIXEL)
                    lut = np.zeros(int(near.max()) + 1, np.int32)
                    lut[near[ok]] = slab[ok]
                    jj = junk & sub
                    slab[jj] = lut[near[jj]]
                sizes = np.bincount(slab[sub], minlength=kk)
                keep = [s for s in keep if sizes[s] >= _SPLIT_SUB_MIN_PX]
                if len(keep) < 2:
                    continue
                # gate 2: the split boundary must coincide with drawn edges —
                # a gradient/banding split fails (boundary sits on the ramp)
                b = np.zeros(sub.shape, bool)
                b[:, 1:] |= (slab[:, 1:] != slab[:, :-1]) \
                    & (slab[:, 1:] >= 0) & (slab[:, :-1] >= 0)
                b[1:, :] |= (slab[1:, :] != slab[:-1, :]) \
                    & (slab[1:, :] >= 0) & (slab[:-1, :] >= 0)
                if not b.any() or float(ewin[b].mean()) < _SPLIT_BND_FRAC:
                    continue
                # gate 3: final sub-region mean colours must truly separate
                means = np.array([[img[y0:y1, x0:x1][slab == s][:, c].mean()
                                   for c in range(3)] for s in keep],
                                 np.float64)
                labm = rgb2lab(means.reshape(1, -1, 3) / 255.0)[0]
                maxde = max(np.linalg.norm(labm[i] - labm[j])
                            for i in range(len(keep))
                            for j in range(i + 1, len(keep)))
                if maxde < _SPLIT_MIN_DE:
                    continue
                # joint quality gate: weak on BOTH evidence axes = a single
                # shading pocket, not drawn structure (constants above)
                if maxde < _SPLIT_STRONG_DE and ef < _SPLIT_STRONG_EF:
                    continue
                # low-ef rescue-band entries (below the original solid
                # floor) need STRONG colour proof — populations in the
                # constants block
                if ef < _SPLIT_EDGE_SOLID and maxde < _SPLIT_RESCUE_DE:
                    continue
                # apply: largest sub-region keeps ci, the rest get new labels
                order = sorted(keep, key=lambda s: -sizes[s])
                wout = out[y0:y1, x0:x1]
                for s in order[1:]:
                    if len(new_centers) >= _SPLIT_MAX_NEW:
                        break
                    m = sub & (slab == s)
                    nid = n0 + len(new_centers)
                    wout[m] = nid
                    cnew = np.clip(np.round(means[keep.index(s)]),
                                   0, 255).astype(centers.dtype)
                    new_centers.append(cnew)
                    lum.append(_luminance(cnew))
                    spread.append(int(max(cnew)) - int(min(cnew)))
                    touched.append(nid)
                touched.append(ci)              # remainder may split again
        if not touched:
            break
        worklist = sorted(set(touched))         # recurse into split regions
    if not new_centers:
        return labels, centers
    return out, np.concatenate([centers, np.stack(new_centers)], axis=0)


def _smooth_labels(labels: np.ndarray, n_labels: int, ksize: int = 3,
                   centers: np.ndarray = None) -> np.ndarray:
    """Majority (mode) filter on the label map — de-jags region boundaries.

    Line-art clusters are IMMUNE: a 1-3px stroke loses every 3x3 majority vote
    against its background, so unprotected smoothing erases entire outline
    networks (the vanished-outline catastrophe)."""
    votes = np.zeros((n_labels,) + labels.shape, dtype=np.float32)
    for ci in range(n_labels):
        votes[ci] = cv2.boxFilter((labels == ci).astype(np.float32), -1, (ksize, ksize))
    out = np.argmax(votes, axis=0).astype(labels.dtype)
    if centers is not None:
        for ci in range(n_labels):
            if _luminance(centers[ci]) < DARK_LINE_LUM:
                out[labels == ci] = ci
    return out


def _corner_aware_bezier(pts: np.ndarray, corner_deg: float) -> str:
    """Closed corner-preserving spline through pts -> cubic bezier 'd' string.

    Vertices whose turn deviates more than `corner_deg` from straight are kept
    as hard corners (zero-length tangents), so the curve stays sharp there and
    smoothly rounds everywhere else. This avoids the overshoot that plain
    Catmull-Rom produces on the sharp corners common in logos.
    """
    n = len(pts)
    tangents = []
    for i in range(n):
        p0 = pts[(i - 1) % n]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        a = p1 - p0
        b = p2 - p1
        na = np.linalg.norm(a)
        nb = np.linalg.norm(b)
        if na < 1e-6 or nb < 1e-6:
            tangents.append(np.zeros(2))
            continue
        cosang = np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0)
        deviation = np.degrees(np.arccos(cosang))  # 0 = straight, 180 = U-turn
        if deviation > corner_deg:
            tangents.append(np.zeros(2))          # hard corner
        else:
            tangents.append((p2 - p0) / 6.0)      # smooth

    d = f"M {pts[0][0]:.2f} {pts[0][1]:.2f} "
    for i in range(n):
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        c1 = p1 + tangents[i]
        c2 = p2 - tangents[(i + 1) % n]
        d += f"C {c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} {p2[0]:.2f} {p2[1]:.2f} "
    return d + "Z"


def _polygon_to_d(pts: np.ndarray) -> str:
    d = f"M {pts[0][0]:.2f} {pts[0][1]:.2f} "
    for x, y in pts[1:]:
        d += f"L {x:.2f} {y:.2f} "
    return d + "Z"


class QuantizeContoursPipeline(Pipeline):
    id = "quantize_contours"
    name = "Quantize + Contours"
    description = "K-means color layers, OpenCV contours, Douglas-Peucker simplify, optional Catmull-Rom Bezier smoothing."

    params = [
        Param("num_colors", "Colors (k)", "int", 8, min=2, max=32, step=1),
        Param("seed", "K-means seed", "int", 0, min=1, max=99999999, step=1,
              help="Deterministic clustering seed. Different seeds give different "
                   "partitions of varying quality — the tournament judges the draws."),
        Param("merge_de", "Palette merge ΔE", "float", 0.0, min=0.0, max=25.0, step=1.0,
              help="Merge cluster colors closer than this CIEDE2000 distance. "
                   "Kills near-duplicate shades so each element is ONE solid container."),
        Param("simplify", "Simplify epsilon (px)", "float", 1.5, min=0.0, max=10.0, step=0.5,
              help="Douglas-Peucker tolerance. Higher = fewer points."),
        Param("smoothing", "Smoothing", "select", "bezier", options=["bezier", "polygon", "schneider"],
              help="bezier = corner-aware curves, polygon = straight lines, "
                   "schneider = Rust least-squares fit (fewest points, smoothest)."),
        Param("corner_deg", "Corner angle (deg)", "float", 35.0, min=0.0, max=120.0, step=5.0,
              help="Turns sharper than this stay as hard corners; gentler ones are smoothed."),
        Param("min_area", "Min region area (px^2)", "int", 40, min=0, max=2000, step=10,
              help="Drop regions smaller than this."),
        Param("blur", "Pre-blur (px)", "int", 0, min=0, max=9, step=1,
              help="Median blur to reduce speckle before quantizing."),
        Param("morph", "Morph cleanup", "int", 1, min=0, max=5, step=1,
              help="Open/close kernel size to smooth mask edges."),
        Param("gap_fill", "Gap fill (px)", "int", 2, min=0, max=6, step=1,
              help="Dilate each color layer so neighbors overlap, closing white seams between regions."),
        Param("lines_on_top", "Dark lines on top", "bool", True,
              help="Paint dark (outline) colors last so gap-fill dilation can't erode line art."),
        Param("split_paths", "One path per element", "bool", True,
              help="Emit each connected component (outer contour + its holes) as its own "
                   "<path> instead of one compound path per color — professional structure: "
                   "every visual element is individually selectable/editable."),
    ]

    def run(self, image_path: str, params: dict) -> str:
        p = self.resolved_params(params)
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError(f"Could not read image: {image_path}")
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        H, W = img.shape[:2]  # already downscaled to the processing size by caller

        if p["blur"] > 0:
            img = cv2.medianBlur(img, p["blur"] * 2 + 1)

        labels, centers = _quantize(img, p["num_colors"], p["seed"])
        if p["merge_de"] > 0:
            # Flat-partition cleanup: absorb AA-halo clusters, despeckle every
            # layer's tiny components, then mode-smooth the boundaries.
            labels, centers = _consolidate_palette(labels, centers, p["merge_de"])
            labels = _despeckle_labels(labels, max(p["min_area"], 16), centers)
            labels = _smooth_labels(labels, len(centers), centers=centers)

        # Paint order (bottom -> top): largest area first, dark outlines last.
        areas = {ci: int(np.count_nonzero(labels == ci)) for ci in range(len(centers))}
        layers = _order_layers(centers, areas, p["lines_on_top"])

        smoothing = p["smoothing"]
        eps = p["simplify"]
        min_area = p["min_area"]
        ksize = p["morph"]
        gap = p["gap_fill"]

        # Ordered gap-fill: a layer may bleed ONLY into pixels that a LATER
        # painted layer will cover. Unconstrained dilation bleeds over earlier
        # layers too, which shows up as color halos beside thin strokes.
        later_union = {}
        acc = np.zeros(labels.shape, dtype=bool)
        for ci in reversed(layers):
            later_union[ci] = acc.copy()
            acc |= (labels == ci)

        body: List[str] = []
        for ci in layers:
            mask = (labels == ci).astype(np.uint8) * 255
            is_line_layer = p["lines_on_top"] and _luminance(centers[ci]) < DARK_LINE_LUM
            if ksize > 0:
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize * 2 + 1, ksize * 2 + 1))
                # OPEN erases thin strokes (a 5px kernel eats a 5px line, leaving
                # broken dashes) — line layers only get CLOSE (seals pinholes).
                if not is_line_layer:
                    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            if gap > 0:
                gk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (gap * 2 + 1, gap * 2 + 1))
                bleed = cv2.dilate(mask, gk).astype(bool) & later_union[ci]
                mask = ((mask.astype(bool)) | bleed).astype(np.uint8) * 255

            contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue

            # Thin strokes fragment into small-area pieces; dropping them breaks
            # outlines into dashes. Line layers get a much gentler cutoff.
            layer_min_area = min_area / 8 if is_line_layer else min_area

            def render_contour(cnt) -> Optional[str]:
                if cv2.contourArea(cnt) < layer_min_area:
                    return None
                approx = cnt.reshape(-1, 2).astype(np.float64)
                if smoothing == "schneider":
                    # Least-squares fit the DENSE contour: long smooth arcs
                    # collapse into single cubics (Recraft-style few points).
                    try:
                        import svgcore
                        poly_d = _polygon_to_d(approx)
                        fitted = svgcore.simplify_path(poly_d, max(eps, 0.75),
                                                       0.0, p["corner_deg"] + 25.0)
                        if fitted:
                            return fitted
                    except ImportError:
                        pass  # fall through to bezier
                pts = approx
                if eps > 0 and len(pts) > 4:
                    pts = cv2.approxPolyDP(pts.astype(np.float32), eps, True).reshape(-1, 2).astype(np.float64)
                if len(pts) < 3:
                    return None
                if smoothing in ("bezier", "schneider") and len(pts) >= 4:
                    return _corner_aware_bezier(pts, p["corner_deg"])
                return _polygon_to_d(pts)

            r, g, b = centers[ci]
            fill = f"#{r:02x}{g:02x}{b:02x}"

            if p["split_paths"] and hierarchy is not None:
                # One <path> per ELEMENT: each outer contour + its hole children.
                # RETR_CCOMP: hierarchy[i] = [next, prev, first_child, parent];
                # outers have parent == -1.
                h = hierarchy[0]
                for i, cnt in enumerate(contours):
                    if h[i][3] != -1:
                        continue  # hole; attached to its parent below
                    outer_d = render_contour(cnt)
                    if not outer_d:
                        continue
                    piece = [outer_d]
                    child = h[i][2]
                    while child != -1:
                        hole_d = render_contour(contours[child])
                        if hole_d:
                            piece.append(hole_d)
                        child = h[child][0]
                    body.append(f'<path d="{" ".join(piece)}" fill="{fill}" fill-rule="evenodd"/>')
            else:
                subpaths = [d for d in (render_contour(c) for c in contours) if d]
                if subpaths:
                    body.append(
                        f'<path d="{" ".join(subpaths)}" fill="{fill}" fill-rule="evenodd"/>'
                    )

        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">\n' + "\n".join(body) + "\n</svg>\n"
        )
        return svg
