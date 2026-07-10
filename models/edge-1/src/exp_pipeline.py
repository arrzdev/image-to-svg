"""edge-1 — boundary-first, the LITERAL prototype (USER 2026-07-10).

This is the exact prototype code that produced research/design/bf_full.png,
no more no less: detect colour boundaries -> bucket-fill the enclosed cells ->
overlay the boundary lines coloured by the DARKER side (ink stays black). The
result is a pixel-exact RASTER; the model entry must return SVG, so the raster
is embedded as a single <image>. This is intentionally NOT vectorized yet —
turning these exact pixels into real vector paths (without the degradation the
first vector attempt introduced) is the next step (edge-2).
"""
from __future__ import annotations

import base64
import io
import os
import sys
from typing import Dict

import cv2
import numpy as np
from PIL import Image

# entry.py imports svgutil/render from the quant-11 backend; put it on the path
_BACKEND = os.path.join(os.path.dirname(__file__), "..", "..", "quant-11", "src")
if _BACKEND not in sys.path:
    sys.path.insert(0, os.path.abspath(_BACKEND))


def run_pipeline(image_path: str, params: dict,
                 dump: Dict[str, np.ndarray] = None) -> str:
    p = {"work_dim": 1536, "threshold": 14.0}
    p.update(params or {})

    # ---- literal prototype (bf.py) ------------------------------------------
    img = cv2.cvtColor(cv2.imread(image_path, cv2.IMREAD_COLOR),
                       cv2.COLOR_BGR2RGB)
    WD = int(p["work_dim"])
    s = WD / max(img.shape[:2])
    work = cv2.resize(img, (round(img.shape[1] * s), round(img.shape[0] * s)),
                      interpolation=cv2.INTER_AREA)
    H, Wd = work.shape[:2]
    lab = cv2.cvtColor(work, cv2.COLOR_RGB2LAB).astype(np.float32)
    thr = float(p["threshold"])
    # 1. boundary mask (pixel differs from right or down neighbour)
    bnd = np.zeros((H, Wd), bool)
    dh = np.sqrt(((lab[:, 1:] - lab[:, :-1]) ** 2).sum(2))
    bnd[:, :-1] |= dh > thr; bnd[:, 1:] |= dh > thr
    dv = np.sqrt(((lab[1:, :] - lab[:-1, :]) ** 2).sum(2))
    bnd[:-1, :] |= dv > thr; bnd[1:, :] |= dv > thr
    # 2. close small gaps so cells are watertight
    bndc = cv2.morphologyEx(bnd.astype(np.uint8), cv2.MORPH_CLOSE,
                            np.ones((3, 3), np.uint8))
    # 3. cells = connected components of non-boundary
    ncell, cells = cv2.connectedComponents((1 - bndc).astype(np.uint8),
                                           connectivity=4)
    # 4. bucket-fill each cell with avg original colour
    flat = work.reshape(-1, 3).astype(np.float64); cl = cells.ravel()
    cnt = np.maximum(np.bincount(cl, minlength=ncell), 1)
    mean = np.stack([np.bincount(cl, weights=flat[:, c], minlength=ncell) / cnt
                     for c in range(3)], 1).astype(np.uint8)
    fill = mean[cells]
    from scipy import ndimage
    idx = ndimage.distance_transform_edt(cells == 0, return_distances=False,
                                         return_indices=True)
    fill_full = fill[tuple(idx)]
    # 5. boundary colour = DARKEST neighbour (keeps ink black)
    lum = (0.299 * work[:, :, 0] + 0.587 * work[:, :, 1]
           + 0.114 * work[:, :, 2])
    shifts = [np.roll(work, 1, 0), np.roll(work, -1, 0),
              np.roll(work, 1, 1), np.roll(work, -1, 1)]
    lums = [np.roll(lum, 1, 0), np.roll(lum, -1, 0),
            np.roll(lum, 1, 1), np.roll(lum, -1, 1)]
    darkest = np.argmin(np.stack(lums, 0), 0)
    bcol = np.choose(darkest[..., None].repeat(3, 2), shifts)
    # 6. assemble: fills + boundary lines on top
    out = fill_full.copy()
    out[bndc.astype(bool)] = bcol[bndc.astype(bool)]
    # -------------------------------------------------------------------------

    buf = io.BytesIO()
    Image.fromarray(out).save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'viewBox="0 0 {Wd} {H}"><image width="{Wd}" height="{H}" '
            f'xlink:href="data:image/png;base64,{b64}"/></svg>')
