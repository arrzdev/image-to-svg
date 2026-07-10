"""ideal-5 — AGGREGATION approach (USER direction, 2026-07-10).

The pivot away from denoise-by-merging. ideal-4 removed noise by merging small
regions (felzenszwalb scale=400), which ate thin dark OUTLINES into the light
neighbour beside them → grey outlines. USER's fix: don't remove regions to kill
noise — keep segmentation GENTLE so every region (incl. the dark outline)
survives, and clean the *appearance* by AGGREGATING the rough fragmented
geometry into smooth shapes (a rough 9-segment circle → one smooth closed
curve). Noise goes away because the shapes get clean, not because pixels merged.

Pipeline:
  1. resize  — cap longest side at work_dim (downscale only, never upscale);
     images already smaller stay native.
  2. colour group — a SMALL edge-preserving average (bilateral) so near-
     identical pixels read as one piece, kept gentle so coloured shadows
     survive (no big mean-shift).
  3. segment — Felzenszwalb GENTLE (low scale): outlines survive as their own
     dark regions instead of being merged/greyed. min_size only drops sub-px
     specks (relative to frame).
  4. colour last — each region = median of the ORIGINAL eroded interior.
  5. aggregate — emit with the FILL boundary fitter (smooth curves + corners):
     rough pixel-staircase boundaries become clean smooth paths, many
     fragments of one form become one path. This is the fill fitter, NOT the
     stroke machinery.
"""
from __future__ import annotations

import os
import sys
from typing import Dict

import cv2
import numpy as np

_BACKEND = os.path.join(os.path.dirname(__file__), "..", "..", "quant-11", "src")
if _BACKEND not in sys.path:
    sys.path.insert(0, os.path.abspath(_BACKEND))


def merge_similar(labels: np.ndarray, work: np.ndarray, de: float) -> np.ndarray:
    """AGGREGATE BY COLOUR (USER's key idea): union adjacent regions whose mean
    colours are within `de` (LAB). Same-colour fragments (the JPEG/AA noise)
    join into one piece; the dark OUTLINE is a different colour so it never
    merges — outlines stay dark AND the noise-seams vanish. Not aggressive:
    coloured shadows sit far above `de` and survive."""
    n = int(labels.max()) + 1
    of = work.reshape(-1, 3).astype(np.float64)
    lb = labels.ravel()
    cnt = np.maximum(np.bincount(lb, minlength=n), 1)
    means = np.stack([np.bincount(lb, weights=of[:, c], minlength=n) / cnt
                      for c in range(3)], 1)
    meansL = cv2.cvtColor(means.reshape(1, -1, 3).astype(np.uint8),
                          cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float64)
    a = labels
    pr = np.vstack([np.stack([a[:, :-1].ravel(), a[:, 1:].ravel()], 1),
                    np.stack([a[:-1, :].ravel(), a[1:, :].ravel()], 1)])
    pr = np.unique(np.sort(pr[pr[:, 0] != pr[:, 1]], 1), axis=0)
    parent = np.arange(n)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    d2 = de * de
    for r, q in pr:
        if ((meansL[r] - meansL[q]) ** 2).sum() <= d2:
            ra, rb = find(int(r)), find(int(q))
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    roots = np.array([find(i) for i in range(n)])
    _, new = np.unique(roots, return_inverse=True)
    return new[labels].astype(np.int32)


def unify_ink(centres: np.ndarray, lum_max: float = 55.0,
              chroma_max: float = 40.0) -> np.ndarray:
    """Give the OUTLINE one solid ink colour. color-last samples each dark
    outline segment locally, so AA bleeds neighbour colours in and the ink
    comes out a patchwork of dark tones. Snap every NEUTRAL-dark region
    (luminance < lum_max AND low chroma) to a single ink = their median, so the
    outline reads as one clean digital ink. Chromatic darks (navy eyes, dark
    coloured shadows) have chroma >= chroma_max and are left alone."""
    c = centres.astype(int)
    lum = 0.299 * c[:, 0] + 0.587 * c[:, 1] + 0.114 * c[:, 2]
    chroma = c.max(1) - c.min(1)
    ink = (lum < lum_max) & (chroma < chroma_max)
    if ink.any():
        centres = centres.copy()
        centres[ink] = np.median(centres[ink], axis=0)
    return centres


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


def run_pipeline(image_path: str, params: dict,
                 dump: Dict[str, np.ndarray] = None) -> str:
    p = {"work_dim": 1536, "group_color": 14.0, "group_space": 3.0,
         "fz_scale": 120.0, "min_area_frac": 1.1e-5, "merge_de": 7.0,
         "ink_lum": 55.0, "ink_chroma": 40.0,
         "corner_deg": 155.0, "smooth_win": 11, "fit_tol": 2.0}
    p.update(params or {})

    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"cannot read {image_path}")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    wd = int(p["work_dim"])
    s = wd / max(img.shape[:2])
    if s < 1.0:                                    # downscale only
        work = cv2.resize(img, (max(1, round(img.shape[1] * s)),
                                max(1, round(img.shape[0] * s))),
                          interpolation=cv2.INTER_AREA)
    else:
        work = img
    Hh, Ww = work.shape[:2]

    # 2. light colour group — gentle, coloured shadows survive
    group = cv2.bilateralFilter(work, d=0, sigmaColor=float(p["group_color"]),
                                sigmaSpace=float(p["group_space"]))
    if dump is not None:
        dump["01_group"] = group.copy()

    # 3. GENTLE segmentation — outlines survive as their own dark regions
    from skimage.segmentation import felzenszwalb
    lab = cv2.cvtColor(group, cv2.COLOR_RGB2LAB)
    min_size = max(6, int(round(p["min_area_frac"] * Hh * Ww)))
    fz = felzenszwalb(lab, scale=float(p["fz_scale"]), sigma=0.5,
                      min_size=min_size)
    _, labels = np.unique(fz, return_inverse=True)
    labels = labels.reshape(work.shape[:2]).astype(np.int32)

    # 4. AGGREGATE BY COLOUR — join same-colour fragments (kills noise seams,
    # leaves the differently-coloured dark outline alone)
    labels = merge_similar(labels, work, float(p["merge_de"]))

    # 5. colour last from the ORIGINAL, then UNIFY the outline ink to one solid
    # colour (patchy dark tones → one clean digital ink; navy eyes kept)
    centres = recolor_from_interior(work, labels, 1)
    centres = unify_ink(centres, float(p["ink_lum"]), float(p["ink_chroma"]))
    if dump is not None:
        dump["02_regions"] = centres[labels]

    # 6. aggregate GEOMETRY — smooth curve fit (loops_to_svg_curves: gentle
    # curves through the region boundaries; corner_deg high so organic blobs
    # round into smooth shapes instead of polygonising). Fill fitter, NOT
    # stroke machinery.
    import boundary
    edges, _ = boundary.build_edges(labels)
    loops = boundary.region_loops(edges, len(centres))
    return boundary.loops_to_svg_curves(labels, centres, edges, loops,
                                        tol=float(p["fit_tol"]),
                                        corner_deg=float(p["corner_deg"]),
                                        smooth_win=int(p["smooth_win"]),
                                        parsimony=0.0)
