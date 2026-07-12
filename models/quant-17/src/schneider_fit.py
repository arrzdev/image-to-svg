"""Schneider least-squares cubic fitter (Graphics Gems, 1990).

Fits the FEWEST cubic Béziers to a digitized curve within a max-error
tolerance: one cubic per maximal span that fits, recursive subdivision only
where the error exceeds tol. Unlike the Potrace segment-merger (which floors at
~16 cubics for a circle), this fits a circle quadrant with ONE cubic -> 4 total,
matching Recraft's minimal control-point count.

fit_curve(pts, max_err) -> list of cubics, each (x0,y0, x1,y1, x2,y2, x3,y3).
fit_closed(pts, max_err) treats a closed loop by seaming at pts[0].
"""
from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np


def _q(bez, t):
    mt = 1.0 - t
    return (bez[0] * mt ** 3 + 3 * bez[1] * mt ** 2 * t
            + 3 * bez[2] * mt * t ** 2 + bez[3] * t ** 3)


def _qprime(bez, t):
    mt = 1.0 - t
    return (3 * (bez[1] - bez[0]) * mt ** 2
            + 6 * (bez[2] - bez[1]) * mt * t
            + 3 * (bez[3] - bez[2]) * t ** 2)


def _qprimeprime(bez, t):
    mt = 1.0 - t
    return (6 * (bez[2] - 2 * bez[1] + bez[0]) * mt
            + 6 * (bez[3] - 2 * bez[2] + bez[1]) * t)


def _normalize(v):
    n = math.hypot(v[0], v[1])
    if n < 1e-12:
        return np.array([0.0, 0.0])
    return v / n


def _chord_params(pts):
    u = [0.0]
    for i in range(1, len(pts)):
        u.append(u[-1] + math.hypot(*(pts[i] - pts[i - 1])))
    total = u[-1]
    if total < 1e-12:
        return np.linspace(0, 1, len(pts))
    return np.array(u) / total


def _generate_bezier(pts, u, that1, that2):
    n = len(pts)
    A = np.zeros((n, 2, 2))
    for i in range(n):
        t = u[i]
        A[i, 0] = that1 * (3 * t * (1 - t) ** 2)
        A[i, 1] = that2 * (3 * t ** 2 * (1 - t))
    C = np.zeros((2, 2))
    X = np.zeros(2)
    p0, p3 = pts[0], pts[-1]
    for i in range(n):
        t = u[i]
        C[0, 0] += np.dot(A[i, 0], A[i, 0])
        C[0, 1] += np.dot(A[i, 0], A[i, 1])
        C[1, 0] = C[0, 1]
        C[1, 1] += np.dot(A[i, 1], A[i, 1])
        tmp = pts[i] - (p0 * (1 - t) ** 3 + p0 * 3 * t * (1 - t) ** 2
                        + p3 * 3 * t ** 2 * (1 - t) + p3 * t ** 3)
        X[0] += np.dot(A[i, 0], tmp)
        X[1] += np.dot(A[i, 1], tmp)
    det_C = C[0, 0] * C[1, 1] - C[1, 0] * C[0, 1]
    det_X0 = C[0, 0] * X[1] - C[1, 0] * X[0]
    det_X1 = X[0] * C[1, 1] - X[1] * C[0, 1]
    alpha_l = 0.0 if abs(det_C) < 1e-12 else det_X1 / det_C
    alpha_r = 0.0 if abs(det_C) < 1e-12 else det_X0 / det_C
    seg = math.hypot(*(p3 - p0))
    eps = 1e-6 * seg
    if alpha_l < eps or alpha_r < eps:
        # fall back to Wu/Barsky heuristic (handles at 1/3 chord)
        d = seg / 3.0
        return [p0, p0 + that1 * d, p3 + that2 * d, p3]
    return [p0, p0 + that1 * alpha_l, p3 + that2 * alpha_r, p3]


def _max_error(pts, bez, u):
    max_d = 0.0
    split = len(pts) // 2
    for i in range(1, len(pts) - 1):
        d = _q(bez, u[i]) - pts[i]
        dist = d[0] * d[0] + d[1] * d[1]
        if dist >= max_d:
            max_d = dist
            split = i
    return max_d, split


def _reparameterize(pts, u, bez):
    out = []
    for i in range(len(pts)):
        t = u[i]
        d = _q(bez, t) - pts[i]
        num = d[0] * _qprime(bez, t)[0] + d[1] * _qprime(bez, t)[1]
        qp = _qprime(bez, t)
        qpp = _qprimeprime(bez, t)
        den = qp[0] ** 2 + qp[1] ** 2 + d[0] * qpp[0] + d[1] * qpp[1]
        out.append(t if abs(den) < 1e-12 else t - num / den)
    return np.array(out)


def _fit_cubic(pts, that1, that2, max_err, out):
    if len(pts) == 2:
        seg = math.hypot(*(pts[1] - pts[0]))
        d = seg / 3.0
        out.append([pts[0], pts[0] + that1 * d, pts[1] + that2 * d, pts[1]])
        return
    u = _chord_params(pts)
    bez = _generate_bezier(pts, u, that1, that2)
    err, split = _max_error(pts, bez, u)
    if err < max_err:
        out.append(bez)
        return
    # try a few Newton reparameterizations before giving up and splitting
    if err < max_err * 16:
        for _ in range(4):
            u = _reparameterize(pts, u, bez)
            bez = _generate_bezier(pts, u, that1, that2)
            err, split = _max_error(pts, bez, u)
            if err < max_err:
                out.append(bez)
                return
    # split at max-error point; centre tangent from neighbours
    tang = _normalize(pts[split - 1] - pts[split + 1])
    _fit_cubic(pts[:split + 1], that1, tang, max_err, out)
    _fit_cubic(pts[split:], -tang, that2, max_err, out)


def fit_curve(pts, max_err) -> List[Tuple[float, ...]]:
    """pts: (N,2) array; max_err: max ALLOWED distance in px (not squared)."""
    pts = np.asarray(pts, float)
    if len(pts) < 2:
        return []
    # drop consecutive duplicates
    keep = [0]
    for i in range(1, len(pts)):
        if math.hypot(*(pts[i] - pts[keep[-1]])) > 1e-9:
            keep.append(i)
    pts = pts[keep]
    if len(pts) < 2:
        return []
    that1 = _normalize(pts[1] - pts[0])
    that2 = _normalize(pts[-2] - pts[-1])
    out: List = []
    _fit_cubic(pts, that1, that2, max_err * max_err, out)
    return [(b[0][0], b[0][1], b[1][0], b[1][1],
             b[2][0], b[2][1], b[3][0], b[3][1]) for b in out]


def fit_closed(pts, max_err) -> List[Tuple[float, ...]]:
    """Closed loop: pts[0]==pts[-1] optional. Seam tangent from wraparound so
    the start/end join is G1-ish; still fits the fewest cubics."""
    pts = np.asarray(pts, float)
    if len(pts) > 1 and math.hypot(*(pts[0] - pts[-1])) < 1e-9:
        pts = pts[:-1]
    if len(pts) < 3:
        return fit_curve(np.vstack([pts, pts[:1]]), max_err)
    seam = _normalize(pts[1] - pts[-1])   # centred tangent at the seam
    loop = np.vstack([pts, pts[:1]])
    out: List = []
    _fit_cubic(loop, seam, -seam, max_err * max_err, out)
    return [(b[0][0], b[0][1], b[1][0], b[1][1],
             b[2][0], b[2][1], b[3][0], b[3][1]) for b in out]
