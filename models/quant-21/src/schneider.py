"""Schneider cubic-bezier fitting (Graphics Gems: "An Algorithm for
Automatically Fitting Digitized Curves", Philip J. Schneider, 1990).

Given a dense sampled polyline, fits a minimal chain of cubic beziers whose
max deviation from the samples stays under `tol` px. Compared to
DP + Catmull-Rom (which threads curves through surviving vertices), the least-
squares fit uses ALL samples, so long smooth arcs collapse into single curves:
fewer anchor points at the same visual error.

Closed paths are split at detected corners (or an arbitrary seam when smooth)
and each piece is fit independently with corner tangent breaks preserved.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np


def _normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def _bezier_point(ctrl, t: float) -> np.ndarray:
    p0, p1, p2, p3 = ctrl
    mt = 1 - t
    return (mt ** 3) * p0 + 3 * (mt ** 2) * t * p1 + 3 * mt * (t ** 2) * p2 + (t ** 3) * p3


def _chord_lengths(pts: np.ndarray) -> np.ndarray:
    d = np.zeros(len(pts))
    d[1:] = np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))
    total = d[-1]
    return d / total if total > 1e-12 else np.linspace(0, 1, len(pts))


def _generate_bezier(pts, u, t_hat1, t_hat2):
    """Least-squares inner control points for fixed endpoints + tangents."""
    n = len(pts)
    A = np.zeros((n, 2, 2))
    mt = 1 - u
    b1 = 3 * mt * mt * u
    b2 = 3 * mt * u * u
    A[:, 0] = t_hat1[None, :] * b1[:, None]
    A[:, 1] = t_hat2[None, :] * b2[:, None]

    b0 = mt ** 3
    b3 = u ** 3
    base = (pts[0][None, :] * (b0 + b1)[:, None] + pts[-1][None, :] * (b2 + b3)[:, None])
    tmp = pts - base

    C = np.zeros((2, 2))
    X = np.zeros(2)
    C[0, 0] = np.einsum("ij,ij->", A[:, 0], A[:, 0])
    C[0, 1] = C[1, 0] = np.einsum("ij,ij->", A[:, 0], A[:, 1])
    C[1, 1] = np.einsum("ij,ij->", A[:, 1], A[:, 1])
    X[0] = np.einsum("ij,ij->", A[:, 0], tmp)
    X[1] = np.einsum("ij,ij->", A[:, 1], tmp)

    det_C = C[0, 0] * C[1, 1] - C[0, 1] * C[1, 0]
    alpha_l = alpha_r = 0.0
    if abs(det_C) > 1e-12:
        alpha_l = (X[0] * C[1, 1] - X[1] * C[0, 1]) / det_C
        alpha_r = (C[0, 0] * X[1] - C[1, 0] * X[0]) / det_C

    seg_len = np.linalg.norm(pts[-1] - pts[0])
    eps = 1e-6 * seg_len
    if alpha_l < eps or alpha_r < eps:
        # Wu/Barsky heuristic fallback
        alpha_l = alpha_r = seg_len / 3.0

    return np.array([pts[0], pts[0] + t_hat1 * alpha_l, pts[-1] + t_hat2 * alpha_r, pts[-1]])


def _max_error(pts, ctrl, u):
    d = np.array([_bezier_point(ctrl, t) for t in u]) - pts
    errs = np.einsum("ij,ij->i", d, d)
    i = int(np.argmax(errs))
    return float(np.sqrt(errs[i])), i


def _reparameterize(pts, ctrl, u):
    """One Newton-Raphson step per parameter."""
    p0, p1, p2, p3 = ctrl
    # derivative control points
    d1 = 3 * (np.array([p1, p2, p3]) - np.array([p0, p1, p2]))
    d2 = 2 * (d1[1:] - d1[:-1])
    out = np.copy(u)
    for i, t in enumerate(u):
        pt = _bezier_point(ctrl, t)
        mt = 1 - t
        q1 = (mt ** 2) * d1[0] + 2 * mt * t * d1[1] + (t ** 2) * d1[2]
        q2 = mt * d2[0] + t * d2[1]
        diff = pt - pts[i]
        num = np.dot(diff, q1)
        den = np.dot(q1, q1) + np.dot(diff, q2)
        if abs(den) > 1e-12:
            out[i] = t - num / den
    return np.clip(out, 0.0, 1.0)


def _fit_cubic(pts, t_hat1, t_hat2, tol, depth=0) -> List[np.ndarray]:
    if len(pts) == 2:
        seg = np.linalg.norm(pts[1] - pts[0]) / 3.0
        return [np.array([pts[0], pts[0] + t_hat1 * seg, pts[1] + t_hat2 * seg, pts[1]])]

    u = _chord_lengths(pts)
    ctrl = _generate_bezier(pts, u, t_hat1, t_hat2)
    err, split = _max_error(pts, ctrl, u)
    if err < tol:
        return [ctrl]

    # try iterative reparameterization before splitting
    if err < tol * 4:
        for _ in range(4):
            u = _reparameterize(pts, ctrl, u)
            ctrl = _generate_bezier(pts, u, t_hat1, t_hat2)
            err, split = _max_error(pts, ctrl, u)
            if err < tol:
                return [ctrl]

    if depth > 24 or split <= 0 or split >= len(pts) - 1:
        return [ctrl]

    # split at max error; center tangent keeps C1 across the join
    t_center = _normalize(pts[split - 1] - pts[split + 1])
    left = _fit_cubic(pts[: split + 1], t_hat1, t_center, tol, depth + 1)
    right = _fit_cubic(pts[split:], -t_center, t_hat2, tol, depth + 1)
    return left + right


def _find_corners(pts: np.ndarray, corner_deg: float, win: int = 3) -> List[int]:
    """Indices of sharp corners on a dense closed polyline."""
    n = len(pts)
    if n < 2 * win + 1:
        return []
    prev_i = (np.arange(n) - win) % n
    next_i = (np.arange(n) + win) % n
    a = pts - pts[prev_i]
    b = pts[next_i] - pts
    na = np.linalg.norm(a, axis=1)
    nb = np.linalg.norm(b, axis=1)
    ok = (na > 1e-9) & (nb > 1e-9)
    cosang = np.ones(n)
    cosang[ok] = np.einsum("ij,ij->i", a[ok], b[ok]) / (na[ok] * nb[ok])
    dev = np.degrees(np.arccos(np.clip(cosang, -1, 1)))
    idx = [i for i in range(n) if dev[i] > corner_deg]
    # non-max suppression within the window
    corners = []
    for i in idx:
        if all(dev[i] >= dev[j % n] for j in range(i - win, i + win + 1)):
            corners.append(i)
    return sorted(set(corners))


def fit_closed(pts: np.ndarray, tol: float, corner_deg: float = 60.0) -> Optional[str]:
    """Fit a closed dense polyline; returns an SVG path 'd' string."""
    n = len(pts)
    if n < 3:
        return None
    corners = _find_corners(pts, corner_deg)
    if not corners:
        corners = [0]  # smooth loop: arbitrary seam
    # build segments between consecutive corners (wrapping)
    segments = []
    for ci in range(len(corners)):
        a = corners[ci]
        b = corners[(ci + 1) % len(corners)]
        seg = pts[a: b + 1] if b > a else np.vstack([pts[a:], pts[: b + 1]])
        if len(seg) >= 2:
            segments.append(seg)
    curves: List[np.ndarray] = []
    for seg in segments:
        t1 = _normalize(seg[min(1, len(seg) - 1)] - seg[0])
        t2 = _normalize(seg[-2] - seg[-1]) if len(seg) >= 2 else -t1
        curves.extend(_fit_cubic(seg, t1, t2, tol))
    if not curves:
        return None
    d = f"M {curves[0][0][0]:.2f} {curves[0][0][1]:.2f} "
    for c in curves:
        d += (f"C {c[1][0]:.2f} {c[1][1]:.2f} {c[2][0]:.2f} {c[2][1]:.2f} "
              f"{c[3][0]:.2f} {c[3][1]:.2f} ")
    return d + "Z"
