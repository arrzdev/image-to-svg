"""edge-3 — boundary-first, everything is a FILLED CONTAINER (USER idea).

No stroke tracing (that produced junction blobs). The boundary-first pass gives
filled containers; the INK line network is just another container (a thin dark
region). Emit EVERY container — light cells AND the ink — as one clean filled
vector path via the shared-boundary fitter. Ink is coloured by the darker side
(stays black); cells by their interior average.
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


def run_pipeline(image_path: str, params: dict,
                 dump: Dict[str, np.ndarray] = None) -> str:
    p = {"work_dim": 1536, "threshold": 14.0, "fit_tol": 2.0,
         "smooth_win": 11, "corner_deg": 155.0}
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
                            np.ones((3, 3), np.uint8)).astype(bool)

    # containers: light cells (non-ink) AND ink regions, all labelled
    _, cells = cv2.connectedComponents((~bndc).astype(np.uint8), connectivity=4)
    nc = int(cells.max())                       # 0 = ink, 1..nc = light cells
    ni, ink = cv2.connectedComponents(bndc.astype(np.uint8), connectivity=8)
    labels = cells.copy().astype(np.int32)
    labels[bndc] = nc + ink[bndc]               # ink regions -> nc+1..
    _, labels = np.unique(labels, return_inverse=True)
    labels = labels.reshape(H, W).astype(np.int32)
    n = int(labels.max()) + 1

    # darker-side colour per pixel (ink -> black)
    lum = 0.299 * work[:, :, 0] + 0.587 * work[:, :, 1] + 0.114 * work[:, :, 2]
    stk = [np.roll(work, 1, 0), np.roll(work, -1, 0),
           np.roll(work, 1, 1), np.roll(work, -1, 1)]
    lums = [np.roll(lum, 1, 0), np.roll(lum, -1, 0),
            np.roll(lum, 1, 1), np.roll(lum, -1, 1)]
    darkest = np.argmin(np.stack(lums, 0), 0)
    bcol = np.choose(darkest[..., None].repeat(3, 2), stk)

    # colour: ink regions from darker-side (black); cells from interior median
    from scipy import ndimage
    b2 = np.zeros((H, W), bool)
    b2[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    b2[1:, :] |= labels[1:, :] != labels[:-1, :]
    dist = ndimage.distance_transform_edt(~b2)
    interior = (dist >= 1).ravel()
    lb = labels.ravel()
    of = work.reshape(-1, 3); bc = bcol.reshape(-1, 3)
    is_ink = np.zeros(n, bool)
    order = np.argsort(lb, kind="stable")
    starts = np.searchsorted(lb[order], np.arange(n))
    ends = np.searchsorted(lb[order], np.arange(n) + 1)
    centres = np.zeros((n, 3), np.uint8)
    ink_mask_flat = bndc.ravel()
    for r in range(n):
        idx = order[starts[r]:ends[r]]
        if idx.size and ink_mask_flat[idx].mean() > 0.5:      # an ink region
            centres[r] = np.median(bc[idx], axis=0)           # darker-side=black
        else:
            sel = idx[interior[idx]]
            px = of[sel] if sel.size else of[idx]
            centres[r] = np.median(px, axis=0)

    import boundary
    edges, _ = boundary.build_edges(labels)
    loops = boundary.region_loops(edges, len(centres))
    return boundary.loops_to_svg_curves(
        labels, centres, edges, loops, tol=float(p["fit_tol"]),
        corner_deg=float(p["corner_deg"]), smooth_win=int(p["smooth_win"]),
        parsimony=0.0)
