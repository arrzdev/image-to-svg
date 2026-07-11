"""edge-10 — the Edge Lab pipeline, frozen (USER settings 2026-07-11).

Two INDEPENDENT detectors over the same image:
  BUCKETS  sensitive boundary detection (Lab dE) -> watertight cells ->
           RAG merge of near-colour neighbours (area-weighted, boundary
           deleted) -> transition-ribbon absorption -> one fill path per cell.
  INK      LCh body gate (dark AND near-neutral) + per-component contrast
           gate -> connected components -> one filled RIBBON path each,
           drawn ON TOP; fills extend underneath (layered overdraw).

Seam glue (USER report: "no lines between regions, they just glue"):
  * every fill mask is dilated 2px before tracing, so painter's-order
    neighbours overlap instead of abutting — independent simplification can
    no longer open gaps between them;
  * thin cells (max half-width < 3px) whose colour lies ON the Lab segment
    between their two dominant neighbours are AA transition ribbons, not
    drawn detail — absorbed into the nearer neighbour (a real thin pale line
    between two DARK regions fails the segment test and survives).

The Edge Lab server endpoint calls process() directly — the lab and the
model are the same code and cannot drift.

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

DEFAULTS = {
    # general
    "work_dim": 2048,
    "svg_eps": 1.0,
    "curve_fit": True,    # smooth line+arc fitting (circles look like circles);
                          # off = raw Douglas-Peucker polygons
    "smoothness": 3.0,    # 0-10: how hard to iron out boundary WANDER (the
                          # 1-2px jitter at 10-30px wavelength that survives
                          # a small smoothing window). Scales the smoothing
                          # window, displacement leash, fit tolerance and the
                          # seam overlap together. 0 = staircase-only smoothing.
    # buckets (USER elephant recipe)
    "pre": "bilateral",
    "pre_strength": 1,
    "threshold": 5.0,
    "close_k": 0,
    "min_cell": 0,
    "merge_de": 22.0,
    # ink
    "ink": True,
    "ink_strength": 0,
    "ink_lmax": 30.0,
    "ink_cmax": 100.0,
    "ink_threshold": 0.0,
    "ink_close": 0,
}
_SEAM_DILATE = 2          # px each side: fill overlap glue
_THIN_HALFW = 3.0         # px: max half-width that still counts as a ribbon
_SEG_D = 10.0             # Lab distance-to-segment for the blend test


def _trace_subs(mask_crop, eps, x0, y0, curve, smooth=3.0):
    """Trace one mask crop into SVG subpath strings. curve=True fits smooth
    LINE+ARC runs; `smooth` (0-10) scales how hard boundary wander is ironed
    out: window grows past the wander wavelength, the leash allows the ironing
    (still capped, so neighbours can't drift far), the fit tolerance lets arcs
    sweep THROUGH residual wobble instead of tracking it. curve=False emits
    raw Douglas-Peucker polygons."""
    mode = cv2.CHAIN_APPROX_NONE if curve else cv2.CHAIN_APPROX_SIMPLE
    cs, _h = cv2.findContours(mask_crop, cv2.RETR_CCOMP, mode)
    s = max(0.0, float(smooth))
    win = 5 + 2 * int(round(s))              # 5 .. 25 px window
    leash = 1.0 + 0.6 * s                    # 1 .. 7 px displacement cap
    tol = max(0.8, float(eps) or 1.2) + 0.35 * s
    cwin = 4.0 + 0.6 * s                     # corner window keeps up with win
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
    """(pairs, border_len) measured on the wall-free partition."""
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
    """Agglomerative merge of adjacent cells by area-weighted Lab dE."""
    labm = cv2.cvtColor(work, cv2.COLOR_RGB2LAB).astype(np.float64)
    flatL = labm.reshape(-1, 3)
    cl0 = cells.ravel()
    cnt = np.bincount(cl0, minlength=ncell).astype(np.float64)
    sums = np.stack([np.bincount(cl0, weights=flatL[:, c], minlength=ncell)
                     for c in range(3)], 1)
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
    """Thin cells whose colour is the BLEND of their two dominant neighbours
    are AA transition ribbons -> absorbed (the seam-line killer). Thin cells
    with their own colour (a real drawn hairline) survive."""
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
            mapping[t] = a if tt < 0.5 else b     # blend -> nearer end
    return mapping[cells]


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

    # buckets: detect -> join -> cells
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

    # ink v3: LCh body + component contrast
    ink_mask = None
    if p["ink"]:
        ib = raw
        if int(p["ink_strength"]) > 0:
            sig = 25 * int(p["ink_strength"])
            ib = cv2.bilateralFilter(raw, 9, sig, sig)
        labi = cv2.cvtColor(ib, cv2.COLOR_RGB2LAB).astype(np.float32)
        Li = labi[:, :, 0] * (100.0 / 255.0)
        Ci = np.sqrt((labi[:, :, 1] - 128.0) ** 2
                     + (labi[:, :, 2] - 128.0) ** 2)
        body = ((Li < float(p["ink_lmax"]))
                & (Ci < float(p["ink_cmax"]))).astype(np.uint8)
        body = cv2.morphologyEx(body, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        if int(p["ink_close"]) >= 3:
            k = int(p["ink_close"]) | 1
            body = cv2.morphologyEx(body, cv2.MORPH_CLOSE,
                                    np.ones((k, k), np.uint8))
        n_b, blab, bst, _ = cv2.connectedComponentsWithStats(body, 8)
        keep = np.zeros(n_b, bool)
        junk_floor = max(24, int(2e-5 * H * W))
        for j in range(1, n_b):
            if bst[j, cv2.CC_STAT_AREA] < junk_floor:
                continue
            if float(p["ink_threshold"]) <= 0:
                keep[j] = True
                continue
            x0 = bst[j, cv2.CC_STAT_LEFT]; y0 = bst[j, cv2.CC_STAT_TOP]
            wj = bst[j, cv2.CC_STAT_WIDTH]; hj = bst[j, cv2.CC_STAT_HEIGHT]
            xa, ya = max(0, x0 - 8), max(0, y0 - 8)
            xb, yb = min(W, x0 + wj + 8), min(H, y0 + hj + 8)
            sub = blab[ya:yb, xa:xb] == j
            ring = cv2.dilate(sub.astype(np.uint8),
                              np.ones((7, 7), np.uint8)).astype(bool) & ~sub
            ring &= body[ya:yb, xa:xb] == 0
            if ring.sum() < 12:
                keep[j] = True
                continue
            csub = labi[ya:yb, xa:xb]
            dE = float(np.linalg.norm(np.median(csub[sub], axis=0)
                                      - np.median(csub[ring], axis=0)))
            keep[j] = dE >= float(p["ink_threshold"])
        ink_mask = keep[blab]
        inv = (~ink_mask).astype(np.uint8)
        n_h, hlab, hst, _ = cv2.connectedComponentsWithStats(inv, 4)
        hole_floor = max(16, int(1e-5 * H * W))
        for j in range(1, n_h):
            if hst[j, cv2.CC_STAT_AREA] <= hole_floor:
                ink_mask[hlab == j] = True
        cells[ink_mask] = 0
        c2 = np.bincount(cells.ravel(), minlength=ncell)
        c2[0] = 0
        cells[(c2 < 24)[cells]] = 0

    # fills: mean colour per cell + wall/ink backfill
    flat = work.reshape(-1, 3).astype(np.float64)
    cl = cells.ravel()
    cnt = np.maximum(np.bincount(cl, minlength=ncell), 1)
    mean = np.stack([np.bincount(cl, weights=flat[:, c], minlength=ncell) / cnt
                     for c in range(3)], 1).astype(np.uint8)
    fillimg = mean[cells]
    idx = ndimage.distance_transform_edt(cells == 0, return_distances=False,
                                         return_indices=True)
    fill_full = fillimg[tuple(idx)]

    # SVG: one dilated fill path per cell + ink ribbons on top
    cells_full = cells[tuple(idx)]
    eps = max(0.0, float(p["svg_eps"]))
    counts_full = np.bincount(cells_full.ravel(), minlength=ncell)
    slices = ndimage.find_objects(cells_full)
    svg_paths = []
    smooth = float(p.get("smoothness", 3.0))
    # seam overlap must grow with the fit's freedom to deviate
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
        # seam glue: neighbours overlap instead of abutting
        m = cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=seam)
        subs = _trace_subs(m, eps, x0, y0, bool(p["curve_fit"]), smooth)
        if not subs:
            continue
        fill = "#%02x%02x%02x" % tuple(int(v) for v in mean[lab_id])
        svg_paths.append(f'<path d="{" ".join(subs)}" fill="{fill}" '
                         f'fill-rule="evenodd"/>')

    ink_paths = []
    if ink_mask is not None and ink_mask.any():
        n_i, ilab, istats, _ = cv2.connectedComponentsWithStats(
            ink_mask.astype(np.uint8), 8)
        order = np.argsort(-istats[1:, cv2.CC_STAT_AREA]) + 1
        srcf = raw.astype(np.float64)
        for j in order:
            if istats[j, cv2.CC_STAT_AREA] < 40:
                break
            x0 = istats[j, cv2.CC_STAT_LEFT]; y0 = istats[j, cv2.CC_STAT_TOP]
            wj = istats[j, cv2.CC_STAT_WIDTH]; hj = istats[j, cv2.CC_STAT_HEIGHT]
            m = (ilab[y0:y0 + hj, x0:x0 + wj] == j).astype(np.uint8)
            subs = _trace_subs(m, eps, x0, y0, bool(p["curve_fit"]), smooth)
            if not subs:
                continue
            med = np.median(srcf[ilab == j], axis=0)
            fillc = "#%02x%02x%02x" % tuple(int(v) for v in med)
            ink_paths.append(f'<path d="{" ".join(subs)}" fill="{fillc}" '
                             f'fill-rule="evenodd"/>')

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{ow}" '
           f'height="{oh}" viewBox="0 0 {W} {H}">'
           + "".join(svg_paths) + "".join(ink_paths) + "</svg>")

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
    composite = fill_full.copy()
    composite[bndc] = bcol[bndc]

    live = int((np.bincount(cells.ravel(), minlength=ncell)[1:] > 0).sum())
    return {"svg": svg, "edges": edges, "fills": fill_full,
            "composite": composite,
            "stats": {"boundary_px": int(bndc.sum()), "cells": live,
                      "dim": f"{W}x{H}", "svg_paths": len(svg_paths),
                      "ink_paths": len(ink_paths),
                      "svg_kb": len(svg) // 1024}}


def run(image_path: str, params: Optional[dict] = None) -> str:
    return process(image_path, params)["svg"]
