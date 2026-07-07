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


def _despeckle_labels(labels: np.ndarray, min_component_px: int,
                      centers: np.ndarray = None) -> np.ndarray:
    """Dissolve connected components smaller than a floor, in every layer,
    reassigning their pixels to the surrounding regions.

    Line-art clusters (dark/outline colors) get a FAR smaller floor: stroke
    networks legitimately fragment into small pieces (eyes, brows, short line
    segments) — a uniform floor massacres them, which was the seed-lottery
    catastrophe's kill stage (forensics: despeckle erased the whole outline).
    """
    junk = np.zeros(labels.shape, dtype=bool)
    for ci in np.unique(labels):
        floor = min_component_px
        if centers is not None and _luminance(centers[ci]) < DARK_LINE_LUM:
            floor = max(6, min_component_px // 10)
        mask = (labels == ci).astype(np.uint8)
        ncomp, comp, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        for k in range(1, ncomp):
            if stats[k, cv2.CC_STAT_AREA] < floor:
                junk |= comp == k
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
            region = out[y0:y1, x0:x1]
            region[sub] = tgt
    return out


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
