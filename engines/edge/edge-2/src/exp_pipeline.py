"""edge-2 — boundary-first, REAL VECTORS (faithful vectorization of edge-1).

edge-1 froze the target look (bucket-fills + darker-side boundary lines) but as
an embedded raster. edge-2 emits true vector paths of that same result:
  * cells  -> filled vector paths (bucket-fills), via the shared-boundary fitter,
  * boundaries -> STROKED smoothed centerlines (build_edges gives them for
    free), coloured by the darkest ORIGINAL pixel along each edge so ink stays
    black. Stroked (not filled) so a thin line stays SOLID at any width — the
    filled-thin-shape approach greyed out; that was the edge-1 vector failure.
Measured against the frozen edge-1 raster + the Recraft score.
"""
from __future__ import annotations

import os
import sys
from typing import Dict

import cv2
import numpy as np

_BACKEND = os.path.join(os.path.dirname(__file__), "..", "..", "..", "quant", "quant-11", "src")
if _BACKEND not in sys.path:
    sys.path.insert(0, os.path.abspath(_BACKEND))


def _smooth_poly(pts, win):
    if win < 3 or len(pts) < 3:
        return pts
    closed = tuple(pts[0]) == tuple(pts[-1])
    half = win // 2
    k = np.ones(2 * half + 1) / (2 * half + 1)
    if closed:
        body = pts[:-1]
        pad = np.concatenate([body[-half:], body, body[:half]], 0)
    else:                                    # replicate ends — NO zero-pad drag
        pad = np.concatenate([np.repeat(pts[:1], half, 0), pts,
                              np.repeat(pts[-1:], half, 0)], 0)
    sx = np.convolve(pad[:, 0], k, "valid")
    sy = np.convolve(pad[:, 1], k, "valid")
    out = np.stack([sx, sy], 1)
    if closed:
        return np.vstack([out, out[:1]])
    out[0] = pts[0]; out[-1] = pts[-1]       # pin junctions exactly
    return out


def _edge_color(pts, work, lum):
    H, W = lum.shape
    xs = np.clip(pts[:, 0].astype(int), 0, W - 1)
    ys = np.clip(pts[:, 1].astype(int), 0, H - 1)
    best_l, best_c = 1e9, np.array([20, 20, 20])
    for dy in (-1, 0):
        for dx in (-1, 0):
            yy = np.clip(ys + dy, 0, H - 1); xx = np.clip(xs + dx, 0, W - 1)
            i = int(np.argmin(lum[yy, xx]))
            l = float(lum[yy[i], xx[i]])
            if l < best_l:
                best_l = l; best_c = work[yy[i], xx[i]]
    return best_c


def run_pipeline(image_path: str, params: dict,
                 dump: Dict[str, np.ndarray] = None) -> str:
    p = {"work_dim": 1536, "threshold": 14.0, "stroke_w": 2.6,
         "poly_smooth": 7, "fit_tol": 2.0, "smooth_win": 11,
         "corner_deg": 155.0}
    p.update(params or {})

    img = cv2.cvtColor(cv2.imread(image_path, cv2.IMREAD_COLOR),
                       cv2.COLOR_BGR2RGB)
    WD = int(p["work_dim"])
    s = WD / max(img.shape[:2])
    work = cv2.resize(img, (round(img.shape[1] * s), round(img.shape[0] * s)),
                      interpolation=cv2.INTER_AREA)
    H, W = work.shape[:2]
    lab = cv2.cvtColor(work, cv2.COLOR_RGB2LAB).astype(np.float32)
    thr = float(p["threshold"])
    bnd = np.zeros((H, W), bool)
    dh = np.sqrt(((lab[:, 1:] - lab[:, :-1]) ** 2).sum(2))
    bnd[:, :-1] |= dh > thr; bnd[:, 1:] |= dh > thr
    dv = np.sqrt(((lab[1:, :] - lab[:-1, :]) ** 2).sum(2))
    bnd[:-1, :] |= dv > thr; bnd[1:, :] |= dv > thr
    bndc = cv2.morphologyEx(bnd.astype(np.uint8), cv2.MORPH_CLOSE,
                            np.ones((3, 3), np.uint8))
    ncell, cells = cv2.connectedComponents((1 - bndc).astype(np.uint8),
                                           connectivity=4)
    from scipy import ndimage
    idx = ndimage.distance_transform_edt(cells == 0, return_distances=False,
                                         return_indices=True)
    cells_full = cells[tuple(idx)]
    _, cells_full = np.unique(cells_full, return_inverse=True)
    cells_full = cells_full.reshape(H, W).astype(np.int32)

    # cell (bucket-fill) colours from the ORIGINAL interior
    of = work.reshape(-1, 3).astype(np.float64); cl = cells_full.ravel()
    n = int(cells_full.max()) + 1
    cnt = np.maximum(np.bincount(cl, minlength=n), 1)
    centres = np.stack([np.bincount(cl, weights=of[:, c], minlength=n) / cnt
                        for c in range(3)], 1).astype(np.uint8)

    import boundary
    edges, _ = boundary.build_edges(cells_full)
    loops = boundary.region_loops(edges, len(centres))
    fills_svg = boundary.loops_to_svg_curves(
        cells_full, centres, edges, loops, tol=float(p["fit_tol"]),
        corner_deg=float(p["corner_deg"]), smooth_win=int(p["smooth_win"]),
        parsimony=0.0)

    # boundary strokes: trace the ENTIRE boundary network (skeleton of the
    # boundary mask — NOT just cell borders, which drops every open/dead-end
    # detail line), smoothed centrelines, coloured darkest-along, SOLID stroke.
    from skimage.morphology import skeletonize
    from strokes import _skeleton_branches
    lum = 0.299 * work[:, :, 0] + 0.587 * work[:, :, 1] + 0.114 * work[:, :, 2]
    sw = float(p["stroke_w"])
    skel = skeletonize(bndc.astype(bool))
    branches, _ = _skeleton_branches(skel)
    parts = []
    for br in branches:
        pix = np.asarray(br["pix"], float)          # (M,2) as (y,x)
        if len(pix) < 2:
            continue
        pts = pix[:, ::-1]                           # -> (x,y)
        col = _edge_color(pts, work, lum)
        hexc = "#%02x%02x%02x" % (int(col[0]), int(col[1]), int(col[2]))
        sp = _smooth_poly(pts, int(p["poly_smooth"]))
        d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in sp)
        parts.append(f'<path d="{d}" stroke="{hexc}" stroke-width="{sw:.2f}" '
                     f'fill="none" stroke-linejoin="round" '
                     f'stroke-linecap="round"/>')
    stroke_svg = "".join(parts)
    return fills_svg.replace("</svg>", stroke_svg + "</svg>") if stroke_svg \
        else fills_svg
