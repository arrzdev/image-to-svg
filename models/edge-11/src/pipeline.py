"""edge-11 — synthesized strokes over buckets (USER architecture 2026-07-12).

Evolution of edge-10's dual-detector design. The line layer is no longer
detected by colour (LCh gates) but STRUCTURALLY, and no longer traced but
SYNTHESIZED:

  BUCKETS  sensitive Lab-dE walls -> cells -> RAG merge -> transition-ribbon
           absorption -> one smooth fill path per cell (traced, arcfit).
  LINES    a thin cell (max half-width <= cap) whose interior is UNIFORM and
           NOT the blend of its neighbours is a ribbon of paint, whatever its
           colour: purple outlines, white hairlines on black, all qualify.
           Line + its walls leave the partition; fills extend underneath.
  STROKES  per line component: skeleton centerline graph -> prune spurs ->
           merge collinear runs across junctions -> smooth the centerline
           (1D, collision-free) -> low-pass the width profile -> SYNTHESIZE
           the output: <path stroke> when width ~constant, variable-width
           ribbon fill otherwise. Painted last. Pixel noise cannot reach the
           output: nothing pixel-traced is emitted for lines.
  EDGES    walls that bound nothing uniform are pure topology references —
           they shape the buckets via backfill and never appear in output.

The Edge Lab server endpoint calls process() directly — lab == model.
Contract: run(image_path, params) -> svg string.
"""
from __future__ import annotations

import heapq
import os
import sys
from typing import Optional

import cv2
import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arcfit import fit_closed_contour, prims_to_d  # noqa: E402
from strokes import strokes_from_mask  # noqa: E402

DEFAULTS = {
    # general
    "work_dim": 2048,
    "svg_eps": 1.0,
    "curve_fit": True,
    "smoothness": 3.0,    # bucket-boundary wander ironing (see edge-10)
    # buckets (USER recipe)
    "pre": "bilateral",
    "pre_strength": 1,
    "threshold": 5.0,
    "close_k": 0,
    "min_cell": 0,
    "merge_de": 22.0,
    # lines / strokes
    "strokes": True,
    "line_max_w": 16.0,   # px: max FULL width that still counts as a line
    "line_uniform": 12.0, # Lab std cap: interior must be one flat colour
    "line_smooth": 4.0,   # centerline smoothing (collision-free, go higher)
    "line_lmax": 100.0,   # optional L* filter (100 = any lightness)
    "line_cmax": 100.0,   # optional C* filter (100 = any chroma)
}
_SEAM_DILATE = 2
_THIN_HALFW = 3.0
_SEG_D = 10.0


def _trace_subs(mask_crop, eps, x0, y0, curve, smooth=3.0):
    """Trace one bucket mask crop into SVG subpaths (see edge-10)."""
    mode = cv2.CHAIN_APPROX_NONE if curve else cv2.CHAIN_APPROX_SIMPLE
    cs, _h = cv2.findContours(mask_crop, cv2.RETR_CCOMP, mode)
    s = max(0.0, float(smooth))
    win = 5 + 2 * int(round(s))
    leash = 1.0 + 0.6 * s
    tol = max(0.8, float(eps) or 1.2) + 0.35 * s
    cwin = 4.0 + 0.6 * s
    subs = []
    for c in cs:
        if len(c) < 3 or cv2.contourArea(c) < 3:
            continue
        pts = c[:, 0, :].astype(np.float64)
        if curve and len(pts) >= 12:
            pts[:, 0] += x0; pts[:, 1] += y0
            prims = fit_closed_contour(pts, tol=tol, corner_deg=55.0,
                                       smooth_win=win, corner_win=cwin,
                                       leash=leash)
            d = prims_to_d(prims)
            if d:
                subs.append(d)
            continue
        ap = cv2.approxPolyDP(c, eps, True) if eps > 0 else c
        if len(ap) < 3:
            continue
        subs.append("M" + "L".join(
            f"{x + x0} {y + y0}" for x, y in ap[:, 0, :]) + "Z")
    return subs


def _lab_boundary(img_rgb, thr):
    lab = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    H, W = img_rgb.shape[:2]
    bnd = np.zeros((H, W), bool)
    dh = np.sqrt(((lab[:, 1:] - lab[:, :-1]) ** 2).sum(2))
    bnd[:, :-1] |= dh > thr; bnd[:, 1:] |= dh > thr
    dv = np.sqrt(((lab[1:, :] - lab[:-1, :]) ** 2).sum(2))
    bnd[:-1, :] |= dv > thr; bnd[1:, :] |= dv > thr
    return bnd


def _adjacency(cells):
    idx = ndimage.distance_transform_edt(cells == 0, return_distances=False,
                                         return_indices=True)
    cf = cells[tuple(idx)]
    keys = []
    for a, b in ((cf[:, :-1].ravel(), cf[:, 1:].ravel()),
                 (cf[:-1, :].ravel(), cf[1:, :].ravel())):
        m = a != b
        lo = np.minimum(a[m], b[m]).astype(np.int64)
        hi = np.maximum(a[m], b[m]).astype(np.int64)
        keys.append(lo * (cells.max() + 1) + hi)
    keys = np.concatenate(keys)
    uk, uc = np.unique(keys, return_counts=True)
    n = cells.max() + 1
    return [(int(k // n), int(k % n), int(c)) for k, c in zip(uk, uc)], cf


def _rag_merge(cells, work, ncell, thr_m):
    labm = cv2.cvtColor(work, cv2.COLOR_RGB2LAB).astype(np.float64)
    flatL = labm.reshape(-1, 3)
    cl0 = cells.ravel()
    cnt = np.bincount(cl0, minlength=ncell).astype(np.float64)
    sums = np.stack([np.bincount(cl0, weights=flatL[:, c],
                                 minlength=ncell) for c in range(3)], 1)
    pairs, _ = _adjacency(cells)
    parent = list(range(ncell))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def mean_of(r):
        return sums[r] / max(cnt[r], 1.0)

    heap = []
    neigh = {}
    for (pa, pb, _bl) in pairs:
        if pa == 0 or pb == 0:
            continue
        d = float(np.linalg.norm(mean_of(pa) - mean_of(pb)))
        if d < thr_m * 2:
            heapq.heappush(heap, (d, pa, pb))
        neigh.setdefault(pa, set()).add(pb)
        neigh.setdefault(pb, set()).add(pa)
    while heap:
        d, pa, pb = heapq.heappop(heap)
        ra, rb = find(pa), find(pb)
        if ra == rb:
            continue
        if float(np.linalg.norm(mean_of(ra) - mean_of(rb))) > thr_m:
            continue
        parent[rb] = ra
        sums[ra] += sums[rb]; cnt[ra] += cnt[rb]
        for nb in neigh.get(rb, ()):
            rn = find(nb)
            if rn != ra:
                dn = float(np.linalg.norm(mean_of(ra) - mean_of(rn)))
                if dn < thr_m * 2:
                    heapq.heappush(heap, (dn, ra, rn))
                neigh.setdefault(ra, set()).add(rn)
    root = np.arange(ncell)
    for i in range(1, ncell):
        root[i] = find(i)
    root[0] = 0
    return root[cells]


def _absorb_transition_ribbons(cells, work, ncell):
    dt = cv2.distanceTransform((cells != 0).astype(np.uint8), cv2.DIST_L2, 3)
    cl = cells.ravel()
    maxw = np.zeros(ncell)
    np.maximum.at(maxw, cl, dt.ravel())
    cnt = np.bincount(cl, minlength=ncell)
    thin = (maxw < _THIN_HALFW) & (cnt > 0)
    thin[0] = False
    if not thin.any():
        return cells
    labm = cv2.cvtColor(work, cv2.COLOR_RGB2LAB).astype(np.float64)
    flatL = labm.reshape(-1, 3)
    sums = np.stack([np.bincount(cl, weights=flatL[:, c], minlength=ncell)
                     for c in range(3)], 1)
    mean = sums / np.maximum(cnt, 1)[:, None]
    pairs, _ = _adjacency(cells)
    nb = {}
    for (pa, pb, bl) in pairs:
        nb.setdefault(pa, []).append((bl, pb))
        nb.setdefault(pb, []).append((bl, pa))
    mapping = np.arange(ncell)
    for t in np.nonzero(thin)[0]:
        cand = sorted(nb.get(t, []), reverse=True)
        cand = [c for c in cand if c[1] != 0 and not thin[c[1]]][:2]
        if not cand:
            continue
        if len(cand) == 1:
            a = cand[0][1]
            if np.linalg.norm(mean[t] - mean[a]) < 28:
                mapping[t] = a
            continue
        a, b = cand[0][1], cand[1][1]
        va = mean[a]; vb = mean[b]; vt = mean[t]
        ab = vb - va
        L2 = float(ab @ ab) or 1.0
        tt = float((vt - va) @ ab) / L2
        proj = va + np.clip(tt, 0, 1) * ab
        if 0.08 <= tt <= 0.92 and np.linalg.norm(vt - proj) <= _SEG_D:
            mapping[t] = a if tt < 0.5 else b
    return mapping[cells]


def _classify_lines(cells, work, ncell, p):
    """Structural line detection: thin + uniform interior + (optional LCh
    filters). Returns the LINE mask (cell + claimed walls) or None. Blend
    ribbons are already gone (absorbed), so what's thin and uniform here is
    self-coloured paint."""
    halfmax = float(p["line_max_w"]) / 2.0
    dtc = cv2.distanceTransform((cells != 0).astype(np.uint8),
                                cv2.DIST_L2, 3)
    cl = cells.ravel()
    maxw = np.zeros(ncell)
    np.maximum.at(maxw, cl, dtc.ravel())
    cnt = np.bincount(cl, minlength=ncell)
    labm = cv2.cvtColor(work, cv2.COLOR_RGB2LAB).astype(np.float64)
    flatL = labm.reshape(-1, 3)
    sums = np.stack([np.bincount(cl, weights=flatL[:, c], minlength=ncell)
                     for c in range(3)], 1)
    sq = np.stack([np.bincount(cl, weights=flatL[:, c] ** 2, minlength=ncell)
                   for c in range(3)], 1)
    n = np.maximum(cnt, 1)[:, None]
    mean = sums / n
    var = np.maximum(sq / n - mean ** 2, 0.0)
    std = np.sqrt(var.mean(axis=1))
    cand = (cnt > 0) & (maxw <= halfmax) & (std <= float(p["line_uniform"]))
    if float(p["line_lmax"]) < 100:
        Lstar = mean[:, 0] * (100.0 / 255.0)
        cand &= Lstar <= float(p["line_lmax"])
    if float(p["line_cmax"]) < 100:
        Cstar = np.sqrt((mean[:, 1] - 128.0) ** 2 + (mean[:, 2] - 128.0) ** 2)
        cand &= Cstar <= float(p["line_cmax"])
    cand[0] = False
    if not cand.any():
        return None
    line_mask = cand[cells]
    # claim the walls: the line's paint extends to mid-wall and beyond; being
    # drawn ON TOP, a slightly fat claim is free (fills tuck underneath)
    line_mask = cv2.dilate(line_mask.astype(np.uint8),
                           np.ones((3, 3), np.uint8), iterations=2)
    # re-bridge pinch breaks: where a line narrows below the wall thickness
    # its interior cell vanishes and the mask arrives as DASHES — one drawn
    # line must be one component or every break renders as a stroke cap
    line_mask = cv2.morphologyEx(line_mask, cv2.MORPH_CLOSE,
                                 np.ones((9, 9), np.uint8)).astype(bool)
    return line_mask


def process(image_path: str, params: Optional[dict] = None) -> dict:
    p = dict(DEFAULTS)
    p.update(params or {})
    img = cv2.cvtColor(cv2.imread(image_path, cv2.IMREAD_COLOR),
                       cv2.COLOR_BGR2RGB)
    ow, oh = img.shape[1], img.shape[0]
    wd = max(256, min(2304, int(p["work_dim"])))
    s = wd / max(img.shape[:2])
    raw = cv2.resize(img, (round(ow * s), round(oh * s)),
                     interpolation=cv2.INTER_AREA)
    work = raw
    if p["pre"] == "gaussian" and int(p["pre_strength"]) > 0:
        k = 2 * int(p["pre_strength"]) + 1
        work = cv2.GaussianBlur(raw, (k, k), 0)
    elif p["pre"] == "bilateral" and int(p["pre_strength"]) > 0:
        sig = 25 * int(p["pre_strength"])
        work = cv2.bilateralFilter(raw, 9, sig, sig)
    H, W = work.shape[:2]

    # buckets
    bnd = _lab_boundary(work, float(p["threshold"]))
    if int(p["close_k"]) >= 3:
        k = int(p["close_k"]) | 1
        bndc = cv2.morphologyEx(bnd.astype(np.uint8), cv2.MORPH_CLOSE,
                                np.ones((k, k), np.uint8)).astype(bool)
    else:
        bndc = bnd
    ncell, cells = cv2.connectedComponents((~bndc).astype(np.uint8), 4)
    if int(p["min_cell"]) > 0:
        counts = np.bincount(cells.ravel(), minlength=ncell)
        tiny = counts < int(p["min_cell"])
        tiny[0] = False
        cells[tiny[cells]] = 0
    if float(p["merge_de"]) > 0 and ncell > 2:
        cells = _rag_merge(cells, work, ncell, float(p["merge_de"]))
    cells = _absorb_transition_ribbons(cells, work, ncell)

    # structural lines -> leave the partition, fills extend underneath
    line_mask = None
    if p["strokes"]:
        line_mask = _classify_lines(cells, work, ncell, p)
        if line_mask is not None:
            cells[line_mask] = 0
            c2 = np.bincount(cells.ravel(), minlength=ncell)
            c2[0] = 0
            cells[(c2 < 24)[cells]] = 0

    # fills + backfill
    flat = work.reshape(-1, 3).astype(np.float64)
    cl = cells.ravel()
    cnt = np.maximum(np.bincount(cl, minlength=ncell), 1)
    mean = np.stack([np.bincount(cl, weights=flat[:, c], minlength=ncell) / cnt
                     for c in range(3)], 1).astype(np.uint8)
    fillimg = mean[cells]
    idx = ndimage.distance_transform_edt(cells == 0, return_distances=False,
                                         return_indices=True)
    fill_full = fillimg[tuple(idx)]

    # SVG fills (traced, arcfit-smoothed, seam-glued)
    cells_full = cells[tuple(idx)]
    eps = max(0.0, float(p["svg_eps"]))
    counts_full = np.bincount(cells_full.ravel(), minlength=ncell)
    slices = ndimage.find_objects(cells_full)
    svg_paths = []
    smooth = float(p.get("smoothness", 3.0))
    seam = max(_SEAM_DILATE, int(np.ceil(1.0 + 0.45 * smooth)))
    pad = seam + 1
    for lab_id in np.argsort(-counts_full):
        if lab_id == 0 or counts_full[lab_id] == 0:
            continue
        sl = slices[lab_id - 1]
        if sl is None:
            continue
        y0 = max(0, sl[0].start - pad); x0 = max(0, sl[1].start - pad)
        y1 = min(H, sl[0].stop + pad); x1 = min(W, sl[1].stop + pad)
        m = (cells_full[y0:y1, x0:x1] == lab_id).astype(np.uint8)
        m = cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=seam)
        subs = _trace_subs(m, eps, x0, y0, bool(p["curve_fit"]), smooth)
        if not subs:
            continue
        fill = "#%02x%02x%02x" % tuple(int(v) for v in mean[lab_id])
        svg_paths.append(f'<path d="{" ".join(subs)}" fill="{fill}" '
                         f'fill-rule="evenodd"/>')

    # SYNTHESIZED strokes, painted last
    stroke_paths = []
    if line_mask is not None and line_mask.any():
        stroke_paths = strokes_from_mask(
            line_mask, raw, smooth=float(p["line_smooth"]), eps=eps,
            max_w=float(p["line_max_w"]),
            min_area=max(24, int(2e-5 * H * W)))

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{ow}" '
           f'height="{oh}" viewBox="0 0 {W} {H}">'
           + "".join(svg_paths) + "".join(stroke_paths) + "</svg>")

    # diagnostic rasters
    lum = (0.299 * work[:, :, 0] + 0.587 * work[:, :, 1]
           + 0.114 * work[:, :, 2])
    shifts = [np.roll(work, 1, 0), np.roll(work, -1, 0),
              np.roll(work, 1, 1), np.roll(work, -1, 1)]
    lums = [np.roll(lum, 1, 0), np.roll(lum, -1, 0),
            np.roll(lum, 1, 1), np.roll(lum, -1, 1)]
    darkest = np.argmin(np.stack(lums, 0), 0)
    bcol = np.choose(darkest[..., None].repeat(3, 2), shifts)
    edges = np.full((H, W, 3), 255, np.uint8)
    edges[bndc] = (0, 0, 0)
    if line_mask is not None:
        edges[line_mask] = (200, 30, 30)      # lines highlighted in red
    composite = fill_full.copy()
    composite[bndc] = bcol[bndc]

    live = int((np.bincount(cells.ravel(), minlength=ncell)[1:] > 0).sum())
    return {"svg": svg, "edges": edges, "fills": fill_full,
            "composite": composite,
            "stats": {"boundary_px": int(bndc.sum()), "cells": live,
                      "dim": f"{W}x{H}", "svg_paths": len(svg_paths),
                      "stroke_paths": len(stroke_paths),
                      "svg_kb": len(svg) // 1024}}


def run(image_path: str, params: Optional[dict] = None) -> str:
    return process(image_path, params)["svg"]
