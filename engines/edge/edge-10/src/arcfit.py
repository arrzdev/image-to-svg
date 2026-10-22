"""arcfit — line + circular-arc boundary fitter (VectorArk-style primitive).

Replaces cubic-Bezier fitting with the rounded-polygon primitive from VectorArk
(arXiv 2605.24398): boundaries become runs of straight lines and circular arcs.
Why: curvature is piecewise-constant BY CONSTRUCTION, so the "lumpy cubic"
faceting mode (tilecmp FITTER) cannot occur inside a primitive; straightness is
structural (a line is a line, not a flat cubic); corners are explicit split
points (Potrace-alphamax spirit: drawing intent, not noise).

Pipeline per closed contour:
  1. smooth the pixel staircase (small window, positional leash)
  2. corner detection: turning angle over an arc-length window
  3. per smooth piece: greedy split-fit with circles (Taubin fit) --
     one arc if it fits within tol, else split at max-error point; arcs with
     negligible bend emit as lines; arcs spanning >=120 deg are subdivided
     (VectorArk rule) for numerical stability
  4. emit SVG `L` / `A` commands

All tolerances are expressed in *pixels at the working resolution* and passed
in by the caller (keep them proportional to image size for scale invariance).
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np

EPS = 1e-9
TAU = 2.0 * np.pi


# --------------------------------------------------------------- smoothing
def smooth_closed(pts: np.ndarray, win: int = 5,
                  leash: float = 1.25) -> np.ndarray:
    """Box-smooth a closed polyline with a positional leash: erases staircase
    and short-wavelength boundary wander without letting geometry drift
    (Depixelizing's E_p idea, cheap version). `leash` caps per-point
    displacement in px; `win` must exceed the wander wavelength to remove it."""
    n = len(pts)
    if n < win + 2 or win < 3:
        return pts
    k = win // 2
    idx = np.arange(-k, k + 1)
    sm = np.empty_like(pts, dtype=np.float64)
    for i in range(n):
        sm[i] = pts[(i + idx) % n].mean(axis=0)
    d = sm - pts
    dist = np.hypot(d[:, 0], d[:, 1])
    over = dist > leash
    if over.any():
        sm[over] = pts[over] + d[over] * (leash / dist[over, None])
    return sm


# ---------------------------------------------------------- corner detection
def find_corners(pts: np.ndarray, corner_deg: float = 55.0,
                 win_px: float = 4.0) -> List[int]:
    """Indices of corner vertices on a closed polyline: where the direction
    turns more than `corner_deg` across an arc-length window of ~win_px on
    each side. Non-max suppressed within the window."""
    n = len(pts)
    if n < 8:
        return []
    seg = np.diff(np.vstack([pts, pts[:1]]), axis=0)
    seglen = np.hypot(seg[:, 0], seg[:, 1]) + EPS
    # direction at each vertex = direction of window before/after
    turn = np.zeros(n)
    for i in range(n):
        # walk back and forward ~win_px of arc length
        acc, j = 0.0, i
        while acc < win_px:
            j = (j - 1) % n
            acc += seglen[j]
            if j == i:
                break
        back = pts[i] - pts[j]
        acc, k = 0.0, i
        while acc < win_px:
            acc += seglen[k]
            k = (k + 1) % n
            if k == i:
                break
        fwd = pts[k] - pts[i]
        nb, nf = np.hypot(*back) + EPS, np.hypot(*fwd) + EPS
        cosv = np.clip(np.dot(back, fwd) / (nb * nf), -1.0, 1.0)
        turn[i] = np.degrees(np.arccos(cosv))
    thr = corner_deg
    cand = [i for i in range(n) if turn[i] >= thr]
    # non-max suppression within win_px arc length
    corners = []
    cand_set = set(cand)
    for i in sorted(cand, key=lambda i: -turn[i]):
        if i not in cand_set:
            continue
        corners.append(i)
        # suppress neighbours within window
        acc, j = 0.0, i
        while acc < win_px:
            j = (j + 1) % n
            acc += seglen[(j - 1) % n]
            cand_set.discard(j)
        acc, j = 0.0, i
        while acc < win_px:
            j = (j - 1) % n
            acc += seglen[j]
            cand_set.discard(j)
    return sorted(corners)


# ------------------------------------------------------------- circle fitting
def fit_circle_taubin(pts: np.ndarray):
    """Taubin algebraic circle fit. Returns (cx, cy, r) or None."""
    x, y = pts[:, 0], pts[:, 1]
    xm, ym = x.mean(), y.mean()
    u, v = x - xm, y - ym
    z = u * u + v * v
    zm = z.mean()
    # solve the Taubin eigen problem via the simple Newton form
    a0 = np.array([[ (u*u).mean(), (u*v).mean(), (u*z).mean()/2 ],
                   [ (u*v).mean(), (v*v).mean(), (v*z).mean()/2 ],
                   [ (u*z).mean()/2, (v*z).mean()/2, (z*z).mean()/4 ]])
    try:
        # Kasa-style linear solve is adequate at our tolerances
        A = np.column_stack([u, v, np.ones(len(pts))])
        b = z
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
        cx = sol[0] / 2
        cy = sol[1] / 2
        r2 = sol[2] + cx * cx + cy * cy
        if r2 <= 0:
            return None
        return (cx + xm, cy + ym, float(np.sqrt(r2)))
    except np.linalg.LinAlgError:
        return None
    _ = a0  # (Taubin matrix kept for future upgrade)


def _arc_error(pts: np.ndarray, cx: float, cy: float, r: float) -> float:
    d = np.hypot(pts[:, 0] - cx, pts[:, 1] - cy)
    return float(np.abs(d - r).max())


def _chord_dev(pts: np.ndarray) -> float:
    """Max deviation of the run from its chord (straightness test)."""
    a, b = pts[0], pts[-1]
    ab = b - a
    L = np.hypot(*ab) + EPS
    return float(np.abs(np.cross(ab, pts - a) / L).max())


# ------------------------------------------------------------- primitives
class Prim:
    __slots__ = ("kind", "p0", "p1", "c", "r", "sweep", "large")

    def __init__(self, kind, p0, p1, c=None, r=0.0, sweep=0, large=0):
        self.kind = kind          # 'L' or 'A'
        self.p0, self.p1 = np.asarray(p0, float), np.asarray(p1, float)
        self.c, self.r = c, r
        self.sweep, self.large = sweep, large


def _make_arc(pts: np.ndarray, cx: float, cy: float, r: float) -> List[Prim]:
    """Build Arc prim(s) from a fitted run; subdivide so each spans < 120 deg
    (VectorArk stability rule). Span/direction come from the UNWRAPPED angle
    sequence of the actual points, so full circles (end==start) and long arcs
    work correctly — endpoint-only math sees a full circle as span 0."""
    ang = np.unwrap(np.arctan2(pts[:, 1] - cy, pts[:, 0] - cx))
    total = float(ang[-1] - ang[0])          # signed swept angle
    span = abs(total)
    if span < 1e-4 or r < 1.0:
        return [Prim('L', pts[0], pts[-1])]
    sweep = 1 if total > 0 else 0            # y-down: increasing angle = SVG sweep 1
    nseg = max(1, int(np.ceil(span / (TAU / 3.0 - 1e-6))))   # each < 120 deg
    prims = []
    prev = pts[0]
    for k in range(1, nseg + 1):
        a = ang[0] + total * k / nseg
        end = np.array([cx + r * np.cos(a), cy + r * np.sin(a)]) \
            if k < nseg else pts[-1]
        if np.hypot(*(end - prev)) < 1e-6:   # degenerate (exact closure)
            end = end + 1e-3
        prims.append(Prim('A', prev, end, c=(cx, cy), r=r,
                          sweep=sweep, large=0))
        prev = end
    return prims


def fit_piece(pts: np.ndarray, tol: float, depth: int = 0) -> List[Prim]:
    """Greedy split-fit of one smooth (corner-free) run into lines + arcs."""
    n = len(pts)
    if n < 2:
        return []
    chord = float(np.hypot(*(pts[-1] - pts[0])))
    arclen = float(np.hypot(*np.diff(pts, axis=0).T).sum())
    # loop guard: a run that curls back on itself (chord << arclen) must be
    # split, never collapsed to a chord line
    if arclen > 3.0 * max(chord, 2.0) and n >= 8:
        k = n // 2
        return fit_piece(pts[:k + 1], tol, depth + 1) + \
            fit_piece(pts[k:], tol, depth + 1)
    if n < 5 or chord < 2.0:
        return [Prim('L', pts[0], pts[-1])]
    # straight?
    if _chord_dev(pts) <= tol:
        return [Prim('L', pts[0], pts[-1])]
    # one arc?
    fitres = fit_circle_taubin(pts)
    if fitres is not None:
        cx, cy, r = fitres
        # reject absurd radii (nearly straight fits explode r)
        if r < 1e5 and _arc_error(pts, cx, cy, r) <= tol:
            return _make_arc(pts, cx, cy, r)
    if depth > 12:
        return [Prim('L', pts[0], pts[-1])]
    # split at the point farthest from the chord (curvature apex)
    a, b = pts[0], pts[-1]
    ab = b - a
    L = np.hypot(*ab) + EPS
    dev = np.abs(np.cross(ab, pts - a) / L)
    k = int(np.argmax(dev))
    k = max(2, min(n - 3, k))
    return fit_piece(pts[:k + 1], tol, depth + 1) + \
        fit_piece(pts[k:], tol, depth + 1)


def fit_closed_contour(pts: np.ndarray, tol: float = 1.2,
                       corner_deg: float = 55.0, smooth_win: int = 5,
                       corner_win: float = 4.0,
                       leash: float = 1.25) -> List[Prim]:
    """Full fit of a closed contour: smooth -> corners -> per-piece line/arc."""
    pts = np.asarray(pts, dtype=np.float64)
    if len(pts) < 4:
        return []
    pts = smooth_closed(pts, smooth_win, leash)
    corners = find_corners(pts, corner_deg, corner_win)
    prims: List[Prim] = []
    if not corners:
        # closed smooth loop: seam at the point farthest from centroid
        c = pts.mean(axis=0)
        seam = int(np.argmax(np.hypot(*(pts - c).T)))
        loop = np.vstack([pts[seam:], pts[:seam + 1]])
        prims = fit_piece(loop, tol)
    else:
        for ci in range(len(corners)):
            i0, i1 = corners[ci], corners[(ci + 1) % len(corners)]
            if i1 > i0:
                piece = pts[i0:i1 + 1]
            else:
                piece = np.vstack([pts[i0:], pts[:i1 + 1]])
            prims.extend(fit_piece(piece, tol))
    return prims


# ------------------------------------------------------------- SVG emission
def prims_to_d(prims: List[Prim], nd: int = 2) -> str:
    """Emit one closed subpath ('M ... Z') from a primitive chain."""
    if not prims:
        return ""
    f = f"%.{nd}f"
    out = ["M" + f % prims[0].p0[0] + " " + f % prims[0].p0[1]]
    for p in prims:
        if p.kind == 'L':
            out.append("L" + f % p.p1[0] + " " + f % p.p1[1])
        else:
            out.append(f"A{p.r:.2f} {p.r:.2f} 0 {p.large} {p.sweep} "
                       + f % p.p1[0] + " " + f % p.p1[1])
    out.append("Z")
    return "".join(out)


def census(prims: List[Prim]) -> Tuple[int, int]:
    """(n_lines, n_arcs) for diagnostics."""
    nl = sum(1 for p in prims if p.kind == 'L')
    return nl, len(prims) - nl
