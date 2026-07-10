"""vectorark-1 pipeline — classical fusion of the two deep-read papers.

Topology  (Layered 2406.05404): decide region topology on an edge-preserving
  SIMPLIFICATION CASCADE (their own supp's bilateral schedule replaces the SDS
  diffusion — its only non-replicable ability is amodal completion), with masks
  layered back-to-front by their exact containment rules. Coarse shapes are
  never subdivided; detail stacks IN FRONT. This kills the quant-lineage failure
  where adjacent detail sharing one k-means label collapses into one path
  (tilecmp UNDER-RESOLVE root cause, auto-loop iteration 2 finding).

Geometry  (VectorArk 2605.24398): boundaries fit with LINE + CIRCULAR-ARC
  rounded polygons (arcfit.py) — curvature piecewise-constant by construction,
  so cubic lumpiness (tilecmp FITTER) cannot occur inside a primitive.

Color     (VectorArk supp 7.1): per-shape fill = per-channel MEDIAN of the
  SOURCE pixels the shape actually shows in the final painter's order (paint-map
  variant of their exclusive-mask voting; occluded shapes fall back to their
  full-mask median). Anchors every fill to ground truth (tilecmp COLOR).

Layer-rule thresholds follow the official Layered code (IoU>0.70 dup-discard,
50% containment front/behind); resolution-dependent values scale with the
working dim (BLUEPRINT R1).
"""
from __future__ import annotations

from typing import List, Optional

import cv2
import numpy as np

from arcfit import fit_closed_contour, prims_to_d

DEFAULTS = {
    "dim": 1024,          # working resolution (long side)
    "levels": 4,          # bilateral cascade steps on top of the original
    "skip_original": True,# topology ONLY from simplified levels (v0 sweep: the
                          # raw level injects AA-fringe masks -> OVER-FRAGMENT 64%)
    "k": 14,              # k-means colors per level
    "min_area": 90,       # component floor, px^2 at dim=1024 (scaled by (dim/1024)^2)
    "per_level_cap": 180, # biggest-N masks kept per level
    "mask_levels": 0,     # >0: masks from only the N coarsest levels. v0.2
                          # measured this trades OVER-FRAG for UNDER-RES+COLOR
                          # ~1:1 (0.367->0.383): duplicates and genuine detail
                          # die together. Defrag needs cross-level region
                          # TRACKING (structural), not level culling. Default off.
    "max_paths": 900,     # global shape budget
    "tol": 1.6,           # arc/line fit tolerance, px at dim=1024
    "corner_deg": 55.0,   # corner split threshold
    "iou_dup": 0.60,      # layer rule 1 (0.70 official; 0.45 tried in v0.2 = net loss)
    "contain": 0.50,      # layer rules 2-3
}


# ------------------------------------------------------------- preprocessing
def load_rgb(path: str, dim: int):
    from PIL import Image
    img = Image.open(path)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img)
    img = img.convert("RGB")
    ow, oh = img.size
    s = dim / max(ow, oh)
    if s < 1.0:
        img = img.resize((round(ow * s), round(oh * s)), Image.LANCZOS)
    return np.asarray(img).copy(), (ow, oh)


def cascade(img: np.ndarray, levels: int) -> List[np.ndarray]:
    """[coarsest ... finest=original]; cumulative bilateral per the Layered
    supp schedule (d, sigmaColor, sigmaSpace) = (10+5N, 100+50N, 100+50N)."""
    seq = [img]
    cur = img
    for n in range(levels):
        cur = cv2.bilateralFilter(cur, 10 + 5 * n, 100 + 50 * n, 100 + 50 * n)
        seq.append(cur)
    return seq[::-1]


# ------------------------------------------------------------- mask extraction
def kmeans_labels(img: np.ndarray, k: int) -> np.ndarray:
    h, w = img.shape[:2]
    data = img.reshape(-1, 3).astype(np.float32)
    sub = data[::4] if len(data) > 400_000 else data
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 12, 1.0)
    _, _, centers = cv2.kmeans(sub, k, None, crit, 2,
                               cv2.KMEANS_PP_CENTERS)
    # assign every pixel to nearest center (chunked)
    lab = np.empty(len(data), dtype=np.int32)
    step = 1_000_000
    for i in range(0, len(data), step):
        d2 = ((data[i:i + step, None, :] - centers[None]) ** 2).sum(axis=2)
        lab[i:i + step] = d2.argmin(axis=1)
    return lab.reshape(h, w)


def level_masks(img: np.ndarray, k: int, min_area: int, cap: int):
    """Connected components of the k-means color regions -> list of masks
    (uint8 arrays), biggest first."""
    lab = kmeans_labels(img, k)
    out = []
    for c in range(k):
        binm = (lab == c).astype(np.uint8)
        if binm.sum() < min_area:
            continue
        n, comp, stats, _ = cv2.connectedComponentsWithStats(binm, 8)
        for j in range(1, n):
            a = stats[j, cv2.CC_STAT_AREA]
            if a >= min_area:
                out.append((a, (comp == j)))
    out.sort(key=lambda t: -t[0])
    return [m for _, m in out[:cap]]


# ------------------------------------------------------------- layer assignment
class _M:
    __slots__ = ("mask", "small", "area")

    def __init__(self, mask):
        self.mask = mask
        self.small = mask[::4, ::4]           # analysis grid for pair ratios
        self.area = int(self.small.sum()) + 1


def assign_layers(masks: List[np.ndarray], iou_dup: float, contain: float,
                  max_paths: int) -> List[List[_M]]:
    """The Layered official-code rules, masks given coarse->fine, big->small."""
    if not masks:
        return []
    layers: List[List[_M]] = [[_M(masks[0])]]
    for raw in masks[1:]:
        m = _M(raw)
        placed = False
        li = 0
        while li < len(layers):
            keep_here = True
            for e in layers[li]:
                inter = int((m.small & e.small).sum())
                if inter == 0:
                    continue
                union = m.area + e.area - inter
                if inter / union > iou_dup:                # rule 1: duplicate
                    placed = True
                    break
                if inter / e.area >= contain and m.area > e.area:
                    placed = True                           # rule 2: redundant macro
                    break
                if inter / m.area >= contain and m.area < e.area:
                    keep_here = False                       # rule 3: sits in front
                    break
            if placed:
                break
            if keep_here:                                   # rule 4: join layer
                layers[li].append(m)
                placed = True
                break
            li += 1
        if not placed:                                      # new front layer
            layers.append([m])
        if sum(len(l) for l in layers) >= max_paths:
            break
    return layers


# ------------------------------------------------------------- geometry + color
def mask_to_d(mask: np.ndarray, tol: float, corner_deg: float,
              min_len: int = 12) -> Optional[str]:
    cs, hier = cv2.findContours(mask.astype(np.uint8), cv2.RETR_CCOMP,
                                cv2.CHAIN_APPROX_NONE)
    subs = []
    for c in cs:
        if len(c) < min_len:
            continue
        pts = c[:, 0, :].astype(np.float64)
        prims = fit_closed_contour(pts, tol=tol, corner_deg=corner_deg)
        if prims:
            d = prims_to_d(prims)
            if d:
                subs.append(d)
    return " ".join(subs) if subs else None


def run_pipeline(image_path: str, params: Optional[dict] = None) -> str:
    p = dict(DEFAULTS)
    p.update(params or {})
    dim = int(p["dim"])
    scale2 = (dim / 1024.0) ** 2
    min_area = max(8, int(p["min_area"] * scale2))
    tol = p["tol"] * (dim / 1024.0)

    img, (ow, oh) = load_rgb(image_path, dim)
    h, w = img.shape[:2]
    seq = cascade(img, int(p["levels"]))
    if p.get("skip_original"):
        seq = seq[:-1]                      # drop the raw finest level
    ml = int(p.get("mask_levels", 0))
    if ml > 0:
        seq = seq[:ml]                      # only the N coarsest levels

    # masks: coarsest level first, canvas prepended
    masks: List[np.ndarray] = [np.ones((h, w), bool)]
    for lvl in seq:
        masks.extend(level_masks(lvl, int(p["k"]), min_area,
                                 int(p["per_level_cap"])))
    layers = assign_layers(masks, p["iou_dup"], p["contain"],
                           int(p["max_paths"]))

    # flatten to painter's order and build the paint map (id per visible px)
    order: List[np.ndarray] = []
    for layer in layers:
        for m in layer:
            order.append(m.mask)
    paint = np.full((h, w), -1, dtype=np.int32)
    for i, m in enumerate(order):
        paint[m] = i

    src = img.astype(np.float64)
    paths = []
    for i, m in enumerate(order):
        vis = paint == i
        nvis = int(vis.sum())
        if i > 0 and nvis < min_area // 2:
            continue                     # fully occluded detail: drop
        sel = vis if nvis >= 24 else m   # occluded fallback: whole mask
        med = np.median(src[sel], axis=0)
        fill = "#%02x%02x%02x" % tuple(int(round(v)) for v in med)
        if i == 0:
            d = f"M0 0L{w} 0L{w} {h}L0 {h}Z"
        else:
            d = mask_to_d(m, tol, p["corner_deg"])
            if not d:
                continue
        paths.append(f'<path d="{d}" fill="{fill}" fill-rule="evenodd"/>')

    body = "\n".join(paths)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{ow}" '
            f'height="{oh}" viewBox="0 0 {w} {h}">\n{body}\n</svg>')
