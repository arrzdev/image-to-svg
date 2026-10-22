"""strokes — centerline extraction + digital stroke SYNTHESIS (edge-11 core).

Lines are not traced, they are REBUILT: per classified line component we
extract the skeleton centerline graph, prune spurs, merge collinear runs
across junctions, smooth the centerline (1D — no neighbour to collide with),
low-pass the width profile sampled from the distance transform, and then
SYNTHESIZE the output stroke from centerline + width. Pixel noise cannot
reach the output because nothing pixel-traced is emitted.

Emission is automatic per chain:
  * width nearly constant (cv < 0.18)  ->  <path fill="none" stroke=...>
    element (compact, editable, renderer draws perfect round joins)
  * tapered / variable width          ->  ribbon FILL synthesized from
    centerline +- w(t)/2 offsets (Recraft-style filled ribbon)
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

import cv2
import numpy as np


# ------------------------------------------------------------ skeleton graph
def _walk_segments(skel_set, deg):
    seen = set()

    def nbrs(p):
        return [(p[0] + dy, p[1] + dx)
                for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                if (dy or dx) and (p[0] + dy, p[1] + dx) in skel_set]

    def walk(start, first):
        seg = [start, first]
        seen.add((start, first)); seen.add((first, start))
        prev, cur = start, first
        while deg.get(cur) == 2:
            step = [q for q in nbrs(cur) if q != prev]
            if not step or (cur, step[0]) in seen:
                break
            nq = step[0]
            seen.add((cur, nq)); seen.add((nq, cur))
            seg.append(nq)
            prev, cur = cur, nq
        return seg

    segments = []
    for pp in skel_set:
        if deg[pp] != 2:
            for q in nbrs(pp):
                if (pp, q) not in seen:
                    segments.append(walk(pp, q))
    for pp in skel_set:                      # pure loops
        if deg[pp] == 2:
            for q in nbrs(pp):
                if (pp, q) not in seen:
                    segments.append(walk(pp, q))
    return segments


def _end_dir(seg, at_start, k=6):
    k = min(k, len(seg) - 1)
    if at_start:
        v = (seg[0][0] - seg[k][0], seg[0][1] - seg[k][1])
    else:
        v = (seg[-1][0] - seg[-1 - k][0], seg[-1][1] - seg[-1 - k][1])
    n = (v[0] ** 2 + v[1] ** 2) ** 0.5 or 1.0
    return (v[0] / n, v[1] / n)


def extract_chains(mask: np.ndarray, prune_len: float) -> List[dict]:
    """Skeletonize one line-component mask -> merged centerline chains.
    Returns [{'pts': (N,2) float array (x,y), 'closed': bool}]."""
    from skimage.morphology import skeletonize
    skel = skeletonize(mask.astype(bool))
    ys, xs = np.nonzero(skel)
    if len(ys) < 4:
        return []
    skel_set = set(zip(ys.tolist(), xs.tolist()))

    def nbr_count(p):
        return sum(1 for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                   if (dy or dx) and (p[0] + dy, p[1] + dx) in skel_set)

    deg = {p: nbr_count(p) for p in skel_set}
    segments = _walk_segments(skel_set, deg)

    # spur pruning: short runs with a free end are skeleton whiskers
    alive = []
    for seg in segments:
        free = (deg.get(seg[0], 0) == 1) or (deg.get(seg[-1], 0) == 1)
        if free and len(seg) < prune_len:
            continue
        if len(seg) >= 3:
            alive.append(seg)
    if not alive:
        return []

    # merge collinear continuations at junctions -> long chains
    junc = {}
    for i, s in enumerate(alive):
        for end, pp in ((0, s[0]), (1, s[-1])):
            if deg.get(pp, 0) > 2:
                junc.setdefault(pp, []).append((i, end))
    link = {}
    for jp, ends in junc.items():
        cand = []
        for a in range(len(ends)):
            for b in range(a + 1, len(ends)):
                ia, ea = ends[a]; ib, eb = ends[b]
                if ia == ib:
                    continue
                da = _end_dir(alive[ia], ea == 0)
                db = _end_dir(alive[ib], eb == 0)
                ang = math.degrees(math.acos(
                    max(-1.0, min(1.0, -(da[0] * db[0] + da[1] * db[1])))))
                if ang <= 45.0:
                    cand.append((ang, ends[a], ends[b]))
        used = set()
        for ang, ea_, eb_ in sorted(cand):
            if ea_ in used or eb_ in used or ea_ in link or eb_ in link:
                continue
            link[ea_] = eb_; link[eb_] = ea_
            used.add(ea_); used.add(eb_)

    consumed = set()
    chains = []
    for i, s in enumerate(alive):
        if i in consumed:
            continue
        start = None
        for end in (0, 1):
            if (i, end) not in link:
                start = (i, 1 - end)
                break
        closed_chain = start is None
        if start is None:
            start = (i, 1)
        pts = []
        cur, exit_end = start
        while True:
            consumed.add(cur)
            seg = alive[cur] if exit_end == 1 else alive[cur][::-1]
            pts.extend(seg if not pts else seg[1:])
            nxt = link.get((cur, exit_end))
            if nxt is None or nxt[0] in consumed:
                break
            cur = nxt[0]
            exit_end = 1 - nxt[1]
        arr = np.array([(x, y) for (y, x) in pts], dtype=np.float64)
        # single segments forming a loop (start==end) count as closed
        closed = closed_chain or (len(arr) > 8
                                  and np.hypot(*(arr[0] - arr[-1])) < 3.0)
        chains.append({"pts": arr, "closed": bool(closed)})
    return chains


# ---------------------------------------------------------------- synthesis
def _smooth_open(pts, win, leash, closed):
    n = len(pts)
    if n < win + 2 or win < 3:
        return pts
    k = win // 2
    sm = np.empty_like(pts)
    if closed:
        idx = np.arange(-k, k + 1)
        for i in range(n):
            sm[i] = pts[(i + idx) % n].mean(axis=0)
    else:
        for i in range(n):
            a = max(0, i - k); b = min(n, i + k + 1)
            sm[i] = pts[a:b].mean(axis=0)
    d = sm - pts
    dist = np.hypot(d[:, 0], d[:, 1])
    over = dist > leash
    if over.any():
        sm[over] = pts[over] + d[over] * (leash / dist[over, None])
    return sm


def _movavg(v, win):
    if len(v) < 3 or win < 3:
        return v
    k = win // 2
    out = np.empty_like(v)
    for i in range(len(v)):
        a = max(0, i - k); b = min(len(v), i + k + 1)
        out[i] = v[a:b].mean()
    return out


def _poly_d(pts, closed, eps=1.0, nd=1):
    ap = cv2.approxPolyDP(pts.astype(np.float32).reshape(-1, 1, 2),
                          eps, closed)
    ap = ap[:, 0, :]
    if len(ap) < 2:
        return None
    f = f"%.{nd}f"
    d = "M" + "L".join(f % x + " " + f % y for x, y in ap)
    return d + ("Z" if closed else "")


def synthesize(chains: List[dict], dist: np.ndarray, junction_pts,
               color_hex: str, smooth: float, eps: float,
               max_w: float, ox: float = 0.0,
               oy: float = 0.0) -> Tuple[List[str], int]:
    """Turn centerline chains + width field into SVG stroke/ribbon paths.
    (ox, oy) shift crop-local coords into canvas space at emission."""
    out = []
    win = 3 + 2 * int(round(smooth))
    jset = junction_pts
    H, W = dist.shape
    for ch in chains:
        pts = ch["pts"]
        if len(pts) < 4:
            continue
        closed = ch["closed"]
        pts = _smooth_open(pts, win, leash=2.5 + 0.4 * smooth, closed=closed)
        # width profile from the distance transform, junction-corrupted
        # samples masked out, then low-passed
        xi = np.clip(pts[:, 0].round().astype(int), 0, W - 1)
        yi = np.clip(pts[:, 1].round().astype(int), 0, H - 1)
        w = 2.0 * dist[yi, xi]
        ok = np.ones(len(w), bool)
        if jset is not None and len(jset):
            for k, (x, y) in enumerate(zip(xi, yi)):
                if (y, x) in jset:
                    ok[max(0, k - 4):k + 5] = False
        if ok.sum() >= 4:
            wmed = float(np.median(w[ok]))
            w[~ok] = wmed
        w = _movavg(w, max(5, win))
        w = np.clip(w, 1.2, 2.5 * max_w)
        cv_ = float(w.std() / (w.mean() + 1e-9))
        pts = pts + np.array([ox, oy])       # crop -> canvas space
        if cv_ < 0.18 or len(pts) < 10:
            d = _poly_d(pts, closed, eps=max(0.8, eps))
            if d:
                out.append(f'<path d="{d}" fill="none" stroke="{color_hex}" '
                           f'stroke-width="{w.mean():.1f}" '
                           f'stroke-linecap="round" stroke-linejoin="round"/>')
            continue
        # variable width -> synthesized ribbon fill from +-w/2 offsets
        tang = np.gradient(pts, axis=0)
        nrm = np.stack([-tang[:, 1], tang[:, 0]], 1)
        ln = np.hypot(nrm[:, 0], nrm[:, 1])[:, None]
        nrm = nrm / np.maximum(ln, 1e-9)
        left = pts + nrm * (w[:, None] / 2)
        right = pts - nrm * (w[:, None] / 2)
        if closed:
            # annulus: two loops, evenodd
            dl = _poly_d(left, True, eps=max(0.8, eps))
            dr = _poly_d(right, True, eps=max(0.8, eps))
            if dl and dr:
                out.append(f'<path d="{dl} {dr}" fill="{color_hex}" '
                           f'fill-rule="evenodd"/>')
            continue
        poly = np.vstack([left, right[::-1]])
        d = _poly_d(poly, True, eps=max(0.8, eps))
        if d:
            out.append(f'<path d="{d}" fill="{color_hex}"/>')
    return out, len(out)


def _ribbon_fallback(comp, xa, ya, color_hex, smooth, eps):
    """Traced smooth ribbon fill (edge-10 style) for components whose skeleton
    is too fragmented for clean synthesis — never worse than tracing."""
    from arcfit import fit_closed_contour, prims_to_d
    cs, _h = cv2.findContours(comp.astype(np.uint8), cv2.RETR_CCOMP,
                              cv2.CHAIN_APPROX_NONE)
    s = max(0.0, smooth)
    subs = []
    for c in cs:
        if len(c) < 3 or cv2.contourArea(c) < 3:
            continue
        pts = c[:, 0, :].astype(np.float64)
        pts[:, 0] += xa; pts[:, 1] += ya
        if len(pts) >= 12:
            prims = fit_closed_contour(
                pts, tol=max(0.8, eps) + 0.35 * s, corner_deg=55.0,
                smooth_win=5 + 2 * int(round(s)), corner_win=4.0 + 0.6 * s,
                leash=1.0 + 0.6 * s)
            d = prims_to_d(prims)
            if d:
                subs.append(d)
                continue
        ap = cv2.approxPolyDP((pts - [xa, ya]).astype(np.float32)
                              .reshape(-1, 1, 2), max(0.8, eps), True)
        if len(ap) >= 3:
            subs.append("M" + "L".join(
                f"{x + xa} {y + ya}" for x, y in ap[:, 0, :].astype(float))
                + "Z")
    if not subs:
        return None
    return (f'<path d="{" ".join(subs)}" fill="{color_hex}" '
            f'fill-rule="evenodd"/>')


def strokes_from_mask(line_mask: np.ndarray, raw: np.ndarray,
                      smooth: float = 4.0, eps: float = 1.0,
                      max_w: float = 16.0,
                      min_area: int = 40) -> List[str]:
    """Full stroke stage: per line component -> centerlines -> synthesis,
    with a traced-ribbon fallback for fragmented skeletons (sausage guard)."""
    from skimage.morphology import skeletonize
    n_i, ilab, istats, _ = cv2.connectedComponentsWithStats(
        line_mask.astype(np.uint8), 8)
    dist = cv2.distanceTransform(line_mask.astype(np.uint8), cv2.DIST_L2, 3)
    paths = []
    for j in np.argsort(-istats[1:, cv2.CC_STAT_AREA]) + 1:
        area = istats[j, cv2.CC_STAT_AREA]
        if area < min_area:
            break
        x0 = istats[j, cv2.CC_STAT_LEFT]; y0 = istats[j, cv2.CC_STAT_TOP]
        wj = istats[j, cv2.CC_STAT_WIDTH]; hj = istats[j, cv2.CC_STAT_HEIGHT]
        pad = 2
        xa, ya = max(0, x0 - pad), max(0, y0 - pad)
        xb, yb = min(line_mask.shape[1], x0 + wj + pad), \
            min(line_mask.shape[0], y0 + hj + pad)
        comp = (ilab[ya:yb, xa:xb] == j)
        med_w = 2.0 * float(np.median(dist[ya:yb, xa:xb][comp]))
        med = np.median(raw[ya:yb, xa:xb][comp], axis=0)
        col = "#%02x%02x%02x" % tuple(int(v) for v in med)
        prune = max(6.0, 1.5 * med_w)
        chains = extract_chains(comp, prune)
        # ACCEPTANCE: synthesis only pays off when the skeleton resolves into
        # long clean runs; a fragmented network (many short junction-cut
        # chains) renders as sausage links -> trace it as a smooth ribbon.
        mean_len = (sum(len(c["pts"]) for c in chains) / len(chains)) \
            if chains else 0.0
        if not chains or mean_len < max(25.0, 2.5 * med_w):
            rb = _ribbon_fallback(comp, xa, ya, col, smooth, eps)
            if rb:
                paths.append(rb)
            continue
        # junction pixels (deg>2) of this component's skeleton, in crop coords
        skel = skeletonize(comp)
        ys, xs = np.nonzero(skel)
        ss = set(zip(ys.tolist(), xs.tolist()))
        jpts = set()
        for pp in ss:
            dcount = sum(1 for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                         if (dy or dx) and (pp[0] + dy, pp[1] + dx) in ss)
            if dcount > 2:
                jpts.add(pp)
        dcrop = dist[ya:yb, xa:xb]
        ps, _n = synthesize(chains, dcrop, jpts, col, smooth, eps, max_w,
                            ox=xa, oy=ya)
        paths.extend(ps)
    return paths
