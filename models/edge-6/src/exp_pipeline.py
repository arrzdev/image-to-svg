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

_BACKEND = os.path.join(os.path.dirname(__file__), "..", "..", "quant-11", "src")
if _BACKEND not in sys.path:
    sys.path.insert(0, os.path.abspath(_BACKEND))


def run_pipeline(image_path: str, params: dict,
                 dump: Dict[str, np.ndarray] = None) -> str:
    p = {"work_dim": 1536, "threshold": 14.0, "fit_tol": 2.0,
         "smooth_win": 3, "corner_deg": 155.0,
         "smooth_passes": 3, "smooth_ksize": 7}   # score-chosen: jag 0.35→0.24
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

    # darker-side colour per pixel (ink -> black)
    lum = 0.299 * work[:, :, 0] + 0.587 * work[:, :, 1] + 0.114 * work[:, :, 2]
    stk = [np.roll(work, 1, 0), np.roll(work, -1, 0),
           np.roll(work, 1, 1), np.roll(work, -1, 1)]
    lums = [np.roll(lum, 1, 0), np.roll(lum, -1, 0),
            np.roll(lum, 1, 1), np.roll(lum, -1, 1)]
    darkest = np.argmin(np.stack(lums, 0), 0)
    bcol = np.choose(darkest[..., None].repeat(3, 2), stk)
    bcol_lum = 0.299 * bcol[:, :, 0] + 0.587 * bcol[:, :, 1] + 0.114 * bcol[:, :, 2]

    # ONLY dark boundaries become ink fill-regions (the actual outline). Weak
    # boundaries (between similar light colours) are NOT lines — absorb them
    # into the adjacent fills so two cells just meet, no thin line.
    ink_lum = float(p.get("ink_lum", 100.0))
    ink_mask = bndc & (bcol_lum < ink_lum)
    from scipy import ndimage as _ndi
    _, cells = cv2.connectedComponents((~bndc).astype(np.uint8), connectivity=4)
    nc = int(cells.max())
    _, ink = cv2.connectedComponents(ink_mask.astype(np.uint8), connectivity=8)
    labels = cells.copy().astype(np.int32)
    labels[ink_mask] = nc + ink[ink_mask]       # dark ink regions -> nc+1..
    # weak-boundary pixels (bndc & ~ink_mask) are still 0 -> assign to nearest
    zero = labels == 0
    if zero.any():
        ii = _ndi.distance_transform_edt(zero, return_distances=False,
                                         return_indices=True)
        labels = labels[tuple(ii)]
    _, labels = np.unique(labels, return_inverse=True)
    labels = labels.reshape(H, W).astype(np.int32)
    n = int(labels.max()) + 1
    bndc = ink_mask                             # only true ink counts as ink now

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

    # GUARDED shape-smoothing (per-region-bbox mode filter) to de-jag region
    # shapes; thin dark ink restored so outlines aren't eroded. Then recolour.
    passes = int(p.get("smooth_passes", 2))
    ksize = int(p.get("smooth_ksize", 5))
    if passes > 0:
        labels = _guarded_smooth(labels, centres, bndc, passes, ksize)
        centres = _recolor(work, bcol, labels, bndc, int(labels.max()) + 1)

    import boundary
    edges, _ = boundary.build_edges(labels)
    loops = boundary.region_loops(edges, len(centres))
    svg = boundary.loops_to_svg_curves(
        labels, centres, edges, loops, tol=float(p["fit_tol"]),
        corner_deg=float(p["corner_deg"]), smooth_win=int(p["smooth_win"]),
        parsimony=0.0)
    return _seal_seams(svg, float(p.get("seal_w", 1.3)),
                       float(p.get("seal_dark_lum", 110.0)))


def _seal_seams(svg, stroke_w, dark_lum):
    """Approach-2 seam seal: give each LIGHT fill a thin same-colour stroke so
    it grows ~0.5px and tucks under its neighbour — the half-covered boundary
    pixel is now backed by a fill colour instead of the background, so the 1px
    anti-alias seam disappears. DARK ink paths get NO stroke (would re-thicken
    the outline); they're painted last on top, so their own edges need no seal."""
    import re

    def repl(m):
        full = m.group(0)
        fm = re.search(r'fill="#([0-9a-fA-F]{6})"', full)
        if not fm:
            return full
        hexc = fm.group(1)
        r = int(hexc[0:2], 16); g = int(hexc[2:4], 16); b = int(hexc[4:6], 16)
        if 0.299 * r + 0.587 * g + 0.114 * b < dark_lum:      # ink -> leave
            return full
        return (full[:-2] + f' stroke="#{hexc}" stroke-width="{stroke_w:.2f}"'
                f' stroke-linejoin="round"/>')
    return re.sub(r'<path\b[^>]*/>', repl, svg)


def _mode_smooth_fast(labels, ksize):
    from scipy import ndimage
    H, W = labels.shape
    n = int(labels.max()) + 1
    slices = ndimage.find_objects(labels + 1)
    best_score = np.zeros((H, W), np.float32)
    best_label = labels.copy()
    for r in range(n):
        sl = slices[r]
        if sl is None:
            continue
        y0 = max(0, sl[0].start - ksize); y1 = min(H, sl[0].stop + ksize)
        x0 = max(0, sl[1].start - ksize); x1 = min(W, sl[1].stop + ksize)
        v = cv2.boxFilter((labels[y0:y1, x0:x1] == r).astype(np.float32),
                          -1, (ksize, ksize))
        bs = best_score[y0:y1, x0:x1]
        upd = v > bs
        bs[upd] = v[upd]
        best_label[y0:y1, x0:x1][upd] = r
    return best_label


def _guarded_smooth(labels, centres, ink_mask, passes, ksize):
    """Smooth ONLY the light cells among themselves. The ink shape is FROZEN
    pixel-exact (like the raster) — mode-filter rounding a 2px line fattens it,
    which made the SVG outlines too thick. So each pass: ink pixels keep their
    original label, and no light pixel is allowed to become an ink label."""
    orig = labels.copy()
    n = len(centres)
    ink_labels = np.zeros(n, bool)
    if ink_mask.any():
        ink_labels[np.unique(orig[ink_mask])] = True
    out = labels
    for _ in range(passes):
        out = _mode_smooth_fast(out, ksize)
        out[ink_mask] = orig[ink_mask]                     # ink stays exact
        became = (~ink_mask) & ink_labels[np.clip(out, 0, n - 1)]
        out[became] = orig[became]                         # no fattening
    _, out = np.unique(out, return_inverse=True)
    return out.reshape(labels.shape).astype(np.int32)


def _recolor(work, bcol, labels, ink_mask, n):
    from scipy import ndimage
    b2 = np.zeros(labels.shape, bool)
    b2[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    b2[1:, :] |= labels[1:, :] != labels[:-1, :]
    dist = ndimage.distance_transform_edt(~b2)
    interior = (dist >= 1).ravel()
    lb = labels.ravel(); of = work.reshape(-1, 3); bc = bcol.reshape(-1, 3)
    ink_flat = ink_mask.ravel()
    order = np.argsort(lb, kind="stable")
    starts = np.searchsorted(lb[order], np.arange(n))
    ends = np.searchsorted(lb[order], np.arange(n) + 1)
    centres = np.zeros((n, 3), np.uint8)
    for r in range(n):
        idx = order[starts[r]:ends[r]]
        if not idx.size:
            continue
        if ink_flat[idx].mean() > 0.5:
            centres[r] = np.median(bc[idx], axis=0)
        else:
            sel = idx[interior[idx]]
            px = of[sel] if sel.size else of[idx]
            centres[r] = np.median(px, axis=0)
    return centres
