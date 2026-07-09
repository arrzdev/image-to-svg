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
    _quantize,
    _smooth_labels,
)


# Upscale factor for the sharpen prepass (fixed by the it22 sweep; the
# exposed knob is the unsharp amount — one atomic mechanism, one lever).
_PRESHARPEN_UP = 3


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
        if p["presharpen"] > 0:
            # Flat-art skip (run 38): sharpening pure flat art has no blur
            # noise to melt and DEFORMS it — run 37 mangled the monster mouth
            # (agent mislabeled it "lateral"; USER caught it). imgstats kind
            # separates cleanly: flat = monster + 4 logos (all revert to the
            # pre-sharpen output byte-identically), lineart = all 9 win
            # targets. Same signal entry.py uses to gate upscaling.
            from imgstats import analyze
            if analyze(img)["kind"] != "flat":
                img = _sharpen_prepass(img, p["presharpen"])
        if p["blur"] > 0:
            img = cv2.medianBlur(img, p["blur"] * 2 + 1)

        labels, centers = _quantize(img, p["num_colors"], p["seed"])
        if p["merge_de"] > 0:
            labels, centers = _consolidate_palette(labels, centers, p["merge_de"])
            labels, centers = _merge_shadow_tones(labels, centers)
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
                                 src_img=img)
        return svg
