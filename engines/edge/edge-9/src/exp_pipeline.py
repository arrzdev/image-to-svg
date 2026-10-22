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
    p = {"work_dim": 1536, "threshold": 9.0, "ink_erode": 1, "fit_tol": 2.0,
         "smooth_win": 3, "corner_deg": 155.0,
         "smooth_passes": 3, "smooth_ksize": 7}   # thr 14→9 (detail), ink erode 1 (thinner)
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
    # ERODE the ink to its core so the SOLID fill reads at the raster's apparent
    # (soft-edged) weight instead of its full detected width; skeleton-guard so
    # thin 1-2px lines survive erosion (else they vanish).
    ie = int(p.get("ink_erode", 1))
    if ie > 0 and ink_mask.any():
        from skimage.morphology import skeletonize
        core = cv2.erode(ink_mask.astype(np.uint8), np.ones((3, 3), np.uint8),
                         iterations=ie).astype(bool)
        ink_mask = core | skeletonize(ink_mask)
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
    import contours_exp
    from contours_exp import _fill_svg_corner_pinned
    edges, _ = boundary.build_edges(labels)
    loops = boundary.region_loops(edges, len(centres))
    # SCHNEIDER minimal-cubic fitter (Recraft's primitive strategy): fit the
    # FEWEST cubics per curved span within tolerance — a circle -> ~2-4 cubics,
    # not the Potrace merger's 16-floor or our old 34. Corner-split + line-intent
    # (straight runs -> L) are unchanged; only the curved-fit is swapped.
    contours_exp.SCHNEIDER_TOL = float(p.get("schneider_tol", 2.0))
    contours_exp.SCHNEIDER_SMOOTH = int(p.get("schneider_smooth", 5))
    try:
        svg = _fill_svg_corner_pinned(labels, centres, edges, loops,
                                      parsimony=float(p.get("parsimony", 1.0)),
                                      stats={})
    finally:
        contours_exp.SCHNEIDER_TOL = None
        contours_exp.SCHNEIDER_SMOOTH = 0
    # TIGHT straightness: only genuine geometric straights (logo edges) convert
    # to L. A looser tol facets organic curves (rabbit eyes went polygonal at
    # 1.5/45); 0.6px over >=90px fires on true straights, leaves arcs curved.
    return _straighten(svg, float(p.get("straight_eps", 0.6)),
                       float(p.get("straight_min_len", 90.0)))


def _straighten(svg, eps, min_len):
    """Straightness pass. A genuinely STRAIGHT EDGE is a run of segments (cubic
    or line) that stays within `eps` of the single chord from the run's start to
    its end AND spans at least `min_len` px — collapse it to one `L` (dead
    straight, few points, like Recraft's 11 L on a triangle side).

    The `min_len` gate is what stops arcs polygonizing: a circle arc is LOCALLY
    near-straight, but it bows past `eps` before the run ever reaches `min_len`,
    so its cubics are left untouched (stay smooth C). Also strips the emitter's
    `fill="none"` junk paths (draw nothing, inflate the path count)."""
    import re

    def do_d(d):
        toks = re.findall(r'([MLCZ])|(-?\d+(?:\.\d+)?)', d)
        seq = [('c', c) if c else ('n', float(n)) for c, n in toks]
        segs = []
        cur = (0.0, 0.0)
        j = 0
        while j < len(seq):
            kind, val = seq[j]
            if kind != 'c':
                j += 1; continue
            if val == 'M':
                x, y = seq[j + 1][1], seq[j + 2][1]
                segs.append(('M', (x, y), (x, y))); cur = (x, y); j += 3
            elif val == 'L':
                x, y = seq[j + 1][1], seq[j + 2][1]
                segs.append(('L', cur, (x, y))); cur = (x, y); j += 3
            elif val == 'C':
                c1 = (seq[j + 1][1], seq[j + 2][1])
                c2 = (seq[j + 3][1], seq[j + 4][1])
                p3 = (seq[j + 5][1], seq[j + 6][1])
                segs.append(('C', cur, c1, c2, p3)); cur = p3; j += 7
            elif val == 'Z':
                segs.append(('Z',)); j += 1
            else:
                j += 1
        return _emit(_straight_runs(segs, eps, min_len))

    svg = re.sub(r'\bd="([^"]*)"', lambda m: f'd="{do_d(m.group(1))}"', svg)
    # drop junk paths that paint nothing
    svg = re.sub(r'<path\b[^>]*fill="none"[^>]*/>\s*', '', svg)
    return svg


def _seg_end(s):
    return s[2] if s[0] in ('M', 'L') else s[4]


def _straight_runs(segs, eps, min_len):
    """Collapse each maximal straight run (>= min_len) into a single L; leave
    everything else (arcs, short bits) exactly as the fitter emitted it."""
    import math
    out = []
    i = 0
    n = len(segs)
    while i < n:
        if segs[i][0] in ('M', 'Z'):
            out.append(segs[i]); i += 1; continue
        start = segs[i][1]
        jmax = -1
        j = i
        while j < n and segs[j][0] in ('L', 'C'):
            end = _seg_end(segs[j])
            ok = True
            for k in range(i, j + 1):
                s = segs[k]
                pts = (s[2],) if s[0] == 'L' else (s[2], s[3], s[4])
                if not all(_near_line(start, end, w, eps) for w in pts):
                    ok = False; break
            if ok:
                jmax = j; j += 1
            else:
                break
        end = _seg_end(segs[jmax]) if jmax >= 0 else None
        if jmax >= 0 and math.hypot(end[0] - start[0],
                                    end[1] - start[1]) >= min_len:
            out.append(('L', start, end)); i = jmax + 1
        else:
            out.append(segs[i]); i += 1
    return out


def _emit(seg):
    parts = []
    for s in seg:
        if s[0] == 'M':
            parts.append(f"M{s[2][0]:.2f} {s[2][1]:.2f}")
        elif s[0] == 'L':
            parts.append(f"L{s[2][0]:.2f} {s[2][1]:.2f}")
        elif s[0] == 'C':
            _, _, c1, c2, p3 = s
            parts.append(f"C{c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} "
                         f"{c2[1]:.2f} {p3[0]:.2f} {p3[1]:.2f}")
        elif s[0] == 'Z':
            parts.append("Z")
    return "".join(parts)


def _near_line(a, b, p, eps):
    import math
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return math.hypot(px - ax, py - ay) < eps
    return abs((px - ax) * dy - (py - ay) * dx) / L < eps


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
