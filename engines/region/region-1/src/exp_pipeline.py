"""EXPERIMENTAL engine — "how I think Recraft works" (design-mode build).

Thesis (research/docs/BLUEPRINT.md, "Recraft engine reconstruction"):
Recraft decides GEOMETRY BEFORE COLOR and idealizes the raster BEFORE
vectorizing. v11 does the opposite — global k-means colour quantize first,
geometry falls out of the colour regions, so every colour accident (JPEG
blur, AA fringe, soft shadow) fractures the geometry and six later stages try
to repair it.

This pipeline inverts that order:

  1. IDEALIZE the raster (edge-preserving) — flatten gradients / AA / JPEG
     noise while keeping strong edges. Soft transitions collapse toward flat
     BEFORE anything vectorizes them. (No global palette anywhere.)
  2. TOPOLOGY from edges, not colour — LOCAL region growing on the idealized
     image: adjacent pixels within a small colour distance are the same
     region (glued-similar colours merge; distant near-identical colours stay
     separate — the opposite of a global k-palette). Scale-relative small-
     region merge.
  3. COLOUR LAST — each final region's fill is sampled from its ERODED
     interior of the ORIGINAL image (median), so boundary AA / occluders
     never contaminate the fill. Per-region, local.
  4. GEOMETRY + EMISSION — reuse v11's shared-boundary, line-intent,
     corner-pinned, layered painter's-order emitter (proven; the part of v11
     that is already Recraft-shaped). Fed OUR labels+colours.

All thresholds are expressed relative to the artwork's own scale (R1/R2),
not absolute pixels. This is a first working version to prove the ARCHITECTURE
— individual stages are deliberately simple and will be iterated.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, Tuple

import cv2
import numpy as np

# reuse the quant lineage's proven geometry/emission backend + utilities
_BACKEND = os.path.join(os.path.dirname(__file__), "..", "..", "..", "quant", "quant-11", "src")
if _BACKEND not in sys.path:
    sys.path.insert(0, os.path.abspath(_BACKEND))


# ---------------------------------------------------------------- idealize
def idealize(img: np.ndarray, scale: float) -> np.ndarray:
    """Edge-preserving simplification: flatten soft transitions, keep edges.

    scale = artwork feature scale in px (see measure_scale). Filter radii are
    tied to it so the same call behaves identically at any resolution (R1)."""
    # light denoise first (kills JPEG blocking without moving edges)
    a = cv2.bilateralFilter(img, d=0, sigmaColor=18,
                            sigmaSpace=max(2.0, scale * 0.6))
    # mean-shift: spatial+range clustering — LOCAL colour merging + gradient
    # flatten in one operator. sr (colour radius) is the "glue similar colours"
    # knob; sp (spatial) is tied to feature scale.
    sp = float(np.clip(scale * 1.2, 6, 40))
    sr = 24.0
    a = cv2.pyrMeanShiftFiltering(a, sp=sp, sr=sr, maxLevel=2)
    return a


def measure_scale(img: np.ndarray) -> float:
    """Artwork feature scale in px: median connected-run of strong edges'
    spacing proxy. Cheap proxy = image longest side / 256, clamped — good
    enough to make radii resolution-relative; refined later."""
    return float(np.clip(max(img.shape[:2]) / 256.0, 2.0, 24.0))


# ---------------------------------------------------------- local regions
def local_regions(simp: np.ndarray, tol: float,
                  min_area: int) -> Tuple[np.ndarray, np.ndarray]:
    """LOCAL, edge-based region topology via Felzenszwalb graph segmentation
    (C-optimised): merges adjacent pixels by local colour affinity, splits at
    strong edges. No global palette — the thesis's "geometry/topology from
    edges, not a global colour k". `tol` scales the merge aggressiveness,
    `min_area` folds sub-scale regions in (both artwork-relative).

    Returns (labels HxW int32 contiguous, provisional centres Nx3 = mean of
    the SIMPLIFIED image; real colours are re-sampled from the ORIGINAL last).
    """
    from skimage.segmentation import felzenszwalb
    lab = cv2.cvtColor(simp, cv2.COLOR_RGB2LAB)
    fz = felzenszwalb(lab, scale=float(tol) ** 2, sigma=0.5,
                      min_size=int(min_area))
    _, labels = np.unique(fz, return_inverse=True)
    labels = labels.reshape(simp.shape[:2]).astype(np.int32)

    n = int(labels.max()) + 1
    simp_flat = simp.reshape(-1, 3).astype(np.float64)
    lb = labels.ravel()
    cnt = np.bincount(lb, minlength=n).astype(np.float64)
    centres = np.stack([
        np.bincount(lb, weights=simp_flat[:, c], minlength=n) / np.maximum(cnt, 1)
        for c in range(3)], axis=1).astype(np.uint8)
    return labels, centres


# ------------------------------------------------------------ colour last
def recolor_from_interior(orig: np.ndarray, labels: np.ndarray,
                          erode: int) -> np.ndarray:
    """Each region's fill = median of ORIGINAL pixels in its ERODED interior
    (boundary AA / neighbouring occluders excluded). Colour decided LAST, per
    region, locally. Falls back to full-region median for regions too thin to
    erode."""
    from scipy import ndimage
    n = int(labels.max()) + 1
    centres = np.zeros((n, 3), np.uint8)
    of = orig.reshape(-1, 3)
    lb = labels.ravel()

    # ONE distance transform from all region boundaries (fast) — interior =
    # pixels >= `erode` from any boundary, so per-region erosion is not needed.
    bnd = np.zeros(labels.shape, bool)
    bnd[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    bnd[1:, :] |= labels[1:, :] != labels[:-1, :]
    dist = ndimage.distance_transform_edt(~bnd)
    interior = (dist >= erode).ravel()

    order = np.argsort(lb, kind="stable")
    lb_s = lb[order]
    starts = np.searchsorted(lb_s, np.arange(n))
    ends = np.searchsorted(lb_s, np.arange(n) + 1)
    for r in range(n):
        idx = order[starts[r]:ends[r]]
        sel = idx[interior[idx]]
        px = of[sel] if sel.size else of[idx]
        centres[r] = np.median(px, axis=0)
    return centres


# ------------------------------------------------------------------- run
def run_pipeline(image_path: str, params: dict,
                 dump: Dict[str, np.ndarray] = None) -> str:
    p = {"work_dim": 1536, "tol": 10.0, "min_area_frac": 0.00030,
         "erode_frac": 0.004, "parsimony": 1.0}
    p.update(params or {})

    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"cannot read {image_path}")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    H0, W0 = img.shape[:2]

    # R1: work at native res, but cap the working dimension for tractability
    # (mean-shift is O(px)); upscale small art toward the cap. NEVER the old
    # hard 1024 downscale.
    wd = int(p["work_dim"])
    s = wd / max(H0, W0)
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC
    work = cv2.resize(img, (max(1, round(W0 * s)), max(1, round(H0 * s))),
                      interpolation=interp) if abs(s - 1) > 1e-3 else img
    if dump is not None:
        dump["00_work"] = work.copy()

    scale = measure_scale(work)
    simp = idealize(work, scale)
    if dump is not None:
        dump["01_idealized"] = simp.copy()

    Hh, Ww = work.shape[:2]
    min_area = max(24, int(p["min_area_frac"] * Hh * Ww))
    labels, prov = local_regions(simp, p["tol"], min_area)
    if dump is not None:
        dump["02_regions_provisional"] = prov[labels]

    erode = max(1, int(p["erode_frac"] * max(Hh, Ww)))
    centres = recolor_from_interior(work, labels, erode)
    if dump is not None:
        dump["03_recolored"] = centres[labels]

    # geometry + emission: v11's shared-boundary, line-intent, corner-pinned,
    # layered painter's-order emitter — fed OUR labels+colours.
    import boundary
    from contours_exp import _fill_svg_corner_pinned
    edges, _ = boundary.build_edges(labels)
    loops = boundary.region_loops(edges, len(centres))
    svg = _fill_svg_corner_pinned(labels, centres, edges, loops,
                                  parsimony=p["parsimony"], stats={})
    return svg
