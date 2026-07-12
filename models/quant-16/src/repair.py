"""Targeted repair: find the worst-damaged regions of a traced SVG and heal
them with high-fidelity local patches.

The local-damage detector (box-filtered CIEDE2000, same machinery as the
metric's `local` component) tells us exactly WHERE a winner lost content or
flattened shading. Instead of paying max-fidelity cost everywhere, we re-trace
only those crops at maximum settings and append them as an overlay layer
(translated into the winner's viewBox space). Global structure stays simple
and editable; local damage gets healed.

    winner SVG + source --detect worst regions--> crops --max-fidelity trace-->
    patch <g> layers appended --> repaired SVG (re-scored by the caller)
"""
from __future__ import annotations

import re
from typing import List, Tuple

import cv2
import numpy as np
from skimage.color import rgb2lab, deltaE_ciede2000

from render import svg_to_rgb
from pipelines import get_pipeline

_VB_RE = re.compile(r'viewBox="\s*([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)\s*"')
_SVG_INNER_RE = re.compile(r"<svg\b[^>]*>(.*)</svg>", re.DOTALL)

# Max-fidelity settings for patch traces.
_PATCH_PARAMS = {"color_precision": 8, "layer_difference": 4,
                 "filter_speckle": 1, "corner_threshold": 30}


def find_damage(svg: str, eval_rgb: np.ndarray, threshold: float = 0.0,
                max_regions: int = 3, win: int = 32) -> List[Tuple[float, float, float, float]]:
    """Return damage bboxes in EVAL-pixel coords [(x, y, w, h)], worst first.

    threshold <= 0 means ADAPTIVE: cut at 75% of the image's own damage peak
    (floor 2.5 dE) so the worst regions are targeted whatever the absolute
    scale — mild diffuse flattening and hard object-loss both yield patches.
    """
    h, w = eval_rgb.shape[:2]
    rendered = svg_to_rgb(svg, w, h)
    de = deltaE_ciede2000(rgb2lab(eval_rgb / 255.0), rgb2lab(rendered / 255.0))
    box = cv2.boxFilter(de, -1, (win, win))
    if threshold <= 0:
        peak = float(box.max())
        if peak < 2.5:
            return []          # nothing worth repairing
        threshold = max(2.5, 0.75 * peak)
    mask = (box > threshold).astype(np.uint8)
    if not mask.any():
        return []
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    regions = []
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area < 16:
            continue
        peak = float(box[labels == i].max())
        regions.append((peak, (float(x), float(y), float(bw), float(bh))))
    regions.sort(reverse=True)
    return [r for _, r in regions[:max_regions]]


def repair_svg(svg: str, proc_path: str, eval_rgb: np.ndarray,
               threshold: float = 0.0, max_regions: int = 3,
               pad: int = 12) -> Tuple[str, int]:
    """Append high-fidelity patch layers over damaged regions.

    Returns (repaired_svg, num_patches). The winner's viewBox is assumed to be
    processing-pixel space (all our pipelines emit that).
    """
    m = _VB_RE.search(svg)
    if not m:
        return svg, 0
    vb_w, vb_h = float(m.group(3)), float(m.group(4))
    eh, ew = eval_rgb.shape[:2]
    sx, sy = vb_w / ew, vb_h / eh          # eval px -> viewBox units

    proc = cv2.imread(proc_path, cv2.IMREAD_COLOR)
    if proc is None:
        return svg, 0
    ph, pw = proc.shape[:2]
    px, py = pw / vb_w, ph / vb_h          # viewBox units -> proc px (≈1.0)

    regions = find_damage(svg, eval_rgb, threshold, max_regions)
    if not regions:
        return svg, 0

    patches = []
    for (x, y, w, h) in regions:
        # eval coords -> viewBox coords, padded
        vx, vy = x * sx - pad, y * sy - pad
        vw, vh = w * sx + 2 * pad, h * sy + 2 * pad
        # -> proc pixel crop
        cx0 = max(0, int(vx * px)); cy0 = max(0, int(vy * py))
        cx1 = min(pw, int((vx + vw) * px)); cy1 = min(ph, int((vy + vh) * py))
        if cx1 - cx0 < 8 or cy1 - cy0 < 8:
            continue
        crop = proc[cy0:cy1, cx0:cx1]
        import tempfile, os
        fd, cpath = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        cv2.imwrite(cpath, crop)
        try:
            patch = get_pipeline("vtracer").run(cpath, _PATCH_PARAMS)
        finally:
            os.unlink(cpath)
        inner = _SVG_INNER_RE.search(patch)
        if not inner:
            continue
        # crop-local coords -> viewBox coords
        tx, ty = cx0 / px, cy0 / py
        patches.append(f'<g transform="translate({tx:.2f},{ty:.2f}) '
                       f'scale({1/px:.6f},{1/py:.6f})">{inner.group(1)}</g>')

    if not patches:
        return svg, 0
    out = svg.replace("</svg>", "\n".join(patches) + "\n</svg>")
    return out, len(patches)
