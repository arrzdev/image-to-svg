"""ideal-2 — idealize-first pipeline + DEDICATED INK LAYER.

ideal-1 proved the front-half thesis (idealize → local topology → colour-last
gives clean flat bucket-fills) but 36% of black ink was absorbed into
neighbour fills — a thin line between two regions IS their shared boundary, it
has no interior to colour, so fills can never carry ink (research/design/
BLUEPRINT.md "Experimental v1 finding").

ideal-2 fixes exactly that: it extracts the dark ink/line network FIRST and
protects it as its own layer, so fills close underneath it and the ink is
painted back on top as confident, line-intent-classified black strokes. The
architecture is now the blueprint's union:

    idealize  →  ink layer (protected)  →  local fills (colour-last)
              →  emit fills UNDER + strokes ON TOP (quant-11 backend)

Backend reuse: quant-11's `contour_svg` already does fills + dark-line strokes
+ line-intent + layered painter's order. ideal-2 feeds it OUR labels (local,
edge-based, with the ink carved out as a dedicated dark label) instead of
quant-11's global-k-means labels. R2 survival floor is applied to the emitted
strokes so outlines hold at any display size.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Dict, Tuple

import cv2
import numpy as np

_BACKEND = os.path.join(os.path.dirname(__file__), "..", "..", "quant-11", "src")
if _BACKEND not in sys.path:
    sys.path.insert(0, os.path.abspath(_BACKEND))


# ---------------------------------------------------------------- idealize
def measure_scale(img: np.ndarray) -> float:
    return float(np.clip(max(img.shape[:2]) / 256.0, 2.0, 24.0))


def idealize(img: np.ndarray, scale: float) -> np.ndarray:
    a = cv2.bilateralFilter(img, d=0, sigmaColor=18,
                            sigmaSpace=max(2.0, scale * 0.6))
    sp = float(np.clip(scale * 1.2, 6, 40))
    a = cv2.pyrMeanShiftFiltering(a, sp=sp, sr=24.0, maxLevel=2)
    return a


# ------------------------------------------------------------- ink layer
def detect_ink(work: np.ndarray, simp: np.ndarray, scale: float,
               dark_lum: float = 82.0) -> np.ndarray:
    """The dark line network: low-luminance structure that fills cannot carry.

    Threshold on the ORIGINAL luminance (the idealize step lightens thin dark
    lines by averaging them with neighbours — sampling the original keeps the
    true ink). Speckle-cleaned relative to artwork scale."""
    lum = (0.299 * work[:, :, 0] + 0.587 * work[:, :, 1]
           + 0.114 * work[:, :, 2])
    ink = lum < dark_lum
    # drop specks smaller than the line scale; close 1px gaps along lines
    k = max(2, int(round(scale * 0.4)))
    ink = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_OPEN,
                           np.ones((2, 2), np.uint8))
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE,
                           np.ones((k, k), np.uint8))
    return ink.astype(bool)


# ---------------------------------------------------------- local regions
def local_regions(simp: np.ndarray, tol: float, min_area: int) -> np.ndarray:
    from skimage.segmentation import felzenszwalb
    lab = cv2.cvtColor(simp, cv2.COLOR_RGB2LAB)
    fz = felzenszwalb(lab, scale=float(tol) ** 2, sigma=0.5,
                      min_size=int(min_area))
    _, labels = np.unique(fz, return_inverse=True)
    return labels.reshape(simp.shape[:2]).astype(np.int32)


def recolor_from_interior(orig: np.ndarray, labels: np.ndarray,
                          erode: int) -> np.ndarray:
    from scipy import ndimage
    n = int(labels.max()) + 1
    centres = np.zeros((n, 3), np.uint8)
    of = orig.reshape(-1, 3)
    lb = labels.ravel()
    bnd = np.zeros(labels.shape, bool)
    bnd[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    bnd[1:, :] |= labels[1:, :] != labels[:-1, :]
    dist = ndimage.distance_transform_edt(~bnd)
    interior = (dist >= erode).ravel()
    order = np.argsort(lb, kind="stable")
    starts = np.searchsorted(lb[order], np.arange(n))
    ends = np.searchsorted(lb[order], np.arange(n) + 1)
    for r in range(n):
        idx = order[starts[r]:ends[r]]
        sel = idx[interior[idx]]
        px = of[sel] if sel.size else of[idx]
        centres[r] = np.median(px, axis=0)
    return centres


# ---------------------------------------------------------- R2 stroke floor
def apply_stroke_floor(svg: str, floor_frac: float = 0.0033) -> str:
    """Give every stroke a viewBox-relative survival floor so outlines hold at
    any display size (BLUEPRINT R2). floor = DIM * floor_frac."""
    m = re.search(r'viewBox="0 0 ([0-9.]+) ([0-9.]+)"', svg)
    dim = max(float(m.group(1)), float(m.group(2))) if m else 1024.0
    floor = max(0.75, dim * floor_frac)

    def repl(mm):
        w = float(mm.group(1))
        return f'stroke-width="{max(w, floor):.2f}"'
    return re.sub(r'stroke-width="([0-9.]+)"', repl, svg)


# ------------------------------------------------------------------- run
def run_pipeline(image_path: str, params: dict,
                 dump: Dict[str, np.ndarray] = None) -> str:
    p = {"work_dim": 1024, "tol": 11.0, "min_area_frac": 0.00035,
         "erode_frac": 0.004, "parsimony": 1.0, "dark_lum": 82.0,
         "width_scale": 1.1, "stroke_floor": 0.0033}
    p.update(params or {})

    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"cannot read {image_path}")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    H0, W0 = img.shape[:2]
    wd = int(p["work_dim"])
    s = wd / max(H0, W0)
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC
    work = cv2.resize(img, (max(1, round(W0 * s)), max(1, round(H0 * s))),
                      interpolation=interp) if abs(s - 1) > 1e-3 else img
    Hh, Ww = work.shape[:2]
    scale = measure_scale(work)

    simp = idealize(work, scale)
    if dump is not None:
        dump["01_idealized"] = simp.copy()

    # 1) INK LAYER first (protected)
    ink = detect_ink(work, simp, scale, p["dark_lum"])
    if dump is not None:
        v = work.copy(); v[ink] = (255, 0, 0); dump["02_ink_mask"] = v

    # 2) LOCAL FILL topology
    min_area = max(24, int(p["min_area_frac"] * Hh * Ww))
    labels = local_regions(simp, p["tol"], min_area)

    # 3) carve the ink out into its OWN dark label so fills can't absorb it
    ink_lbl = int(labels.max()) + 1
    labels[ink] = ink_lbl
    _, flat = np.unique(labels, return_inverse=True)
    labels = flat.reshape(Hh, Ww).astype(np.int32)

    # 4) colour LAST from interior (ink label falls back to its own dark px)
    erode = max(1, int(p["erode_frac"] * max(Hh, Ww)))
    centres = recolor_from_interior(work, labels, erode)
    if dump is not None:
        dump["03_labels_with_ink"] = centres[labels]

    # 5) emit fills UNDER + line-intent strokes ON TOP (quant-11 backend)
    from contours_exp import contour_svg
    svg, _info = contour_svg(labels, centres,
                             fill_tol=2.5, fill_smooth=0,
                             fill_parsimony=p["parsimony"],
                             dark_lum=p["dark_lum"],
                             width_scale=p["width_scale"],
                             src_img=simp)
    # 6) R2 survival floor on the emitted strokes
    svg = apply_stroke_floor(svg, p["stroke_floor"])
    return svg
