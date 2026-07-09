"""Trace-then-simplify post-processing.

Strategy: let the tracer chase pixel fidelity (many control points), then walk
the result back toward editability as a SEPARATE, measurable stage:

    raster --(vtracer, high fidelity)--> dense SVG --(simplify eps)--> editable SVG

Each path's cubic beziers are sampled to a polyline, simplified with
Douglas-Peucker (eps = max deviation in px), and refit with corner-aware cubic
beziers. Because the quality metric re-scores the simplified SVG, the
quality-vs-editability frontier becomes an explicit, tunable curve instead of a
tracer-internal tradeoff.

Handles absolute M/L/C/Z path data (what vtracer and quantize_contours emit).
Paths with other commands are passed through untouched. Transforms are kept
as-is (translation doesn't affect local geometry).
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

import cv2
import numpy as np

from pipelines.quantize_contours import _corner_aware_bezier, _polygon_to_d

_PATH_TAG_RE = re.compile(r"<path\b[^>]*>")
_D_RE = re.compile(r'\bd="([^"]*)"')
_TOKEN_RE = re.compile(r"([MLCZmlcz])|(-?\d*\.?\d+(?:[eE][-+]?\d+)?)")

# Points sampled per cubic segment (before simplification).
_SAMPLES_PER_CURVE = 8


def _parse_subpaths(d: str) -> Optional[List[Tuple[np.ndarray, bool]]]:
    """Parse an absolute M/L/C/Z 'd' string into [(polyline Nx2, closed)].

    Cubics are sampled; returns None if an unsupported command is found.
    """
    tokens = _TOKEN_RE.findall(d)
    seq: List = []
    for cmd, num in tokens:
        seq.append(cmd if cmd else float(num))

    subpaths: List[Tuple[np.ndarray, bool]] = []
    pts: List[np.ndarray] = []
    cur = np.zeros(2)
    i = 0

    def flush(closed: bool):
        nonlocal pts
        if len(pts) >= 2:
            subpaths.append((np.array(pts), closed))
        pts = []

    while i < len(seq):
        tok = seq[i]
        if tok in ("M", "m"):
            rel = tok == "m" and len(subpaths + pts) > 0
            flush(False)
            delta = np.array([seq[i + 1], seq[i + 2]])
            cur = cur + delta if rel else delta
            pts = [cur.copy()]
            i += 3
            # implicit lineto for extra coordinate pairs after M/m
            while i + 1 < len(seq) and not isinstance(seq[i], str):
                step = np.array([seq[i], seq[i + 1]])
                cur = cur + step if tok == "m" else step
                pts.append(cur.copy())
                i += 2
        elif tok in ("L", "l"):
            rel = tok == "l"
            i += 1
            while i + 1 < len(seq) and not isinstance(seq[i], str):
                step = np.array([seq[i], seq[i + 1]])
                cur = cur + step if rel else step
                pts.append(cur.copy())
                i += 2
        elif tok in ("C", "c"):
            rel = tok == "c"
            i += 1
            while i + 5 < len(seq) and not isinstance(seq[i], str):
                base = cur if rel else np.zeros(2)
                p1 = base + np.array([seq[i], seq[i + 1]])
                p2 = base + np.array([seq[i + 2], seq[i + 3]])
                p3 = base + np.array([seq[i + 4], seq[i + 5]])
                t = np.linspace(0, 1, _SAMPLES_PER_CURVE + 1)[1:]
                mt = 1 - t
                curve = (mt[:, None] ** 3 * cur + 3 * mt[:, None] ** 2 * t[:, None] * p1
                         + 3 * mt[:, None] * t[:, None] ** 2 * p2 + t[:, None] ** 3 * p3)
                pts.extend(list(curve))
                cur = p3
                i += 6
        elif tok in ("Z", "z"):
            flush(True)
            i += 1
        elif isinstance(tok, str):
            return None  # unsupported command; caller passes path through
        else:
            i += 1
    flush(False)
    return subpaths


def _shoelace(poly: np.ndarray) -> float:
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def simplify_path_d(d: str, eps: float, min_area: float, corner_deg: float = 35.0,
                    method: str = "catmull") -> Optional[str]:
    """Simplify one 'd' string. Returns new d, '' if everything vanished, or
    None if the path uses unsupported commands (caller keeps the original).

    method='catmull': Douglas-Peucker on samples, corner-aware Catmull refit.
    method='schneider': least-squares cubic fitting on the DENSE samples
    (Graphics Gems) — long smooth arcs collapse into single curves.
    """
    subpaths = _parse_subpaths(d)
    if subpaths is None:
        return None
    out: List[str] = []
    for poly, closed in subpaths:
        if closed and _shoelace(poly) < min_area:
            continue
        if method == "schneider" and closed and len(poly) >= 6:
            from schneider import fit_closed
            seg = fit_closed(poly.astype(np.float64), tol=max(eps, 0.25))
            if seg:
                out.append(seg)
            continue
        pts = poly.astype(np.float32)
        if eps > 0 and len(pts) > 4:
            pts = cv2.approxPolyDP(pts.reshape(-1, 1, 2), eps, closed).reshape(-1, 2)
        pts = pts.astype(np.float64)
        if closed:
            if len(pts) < 3:
                continue
            if len(pts) >= 4:
                out.append(_corner_aware_bezier(pts, corner_deg))
            else:
                out.append(_polygon_to_d(pts))
        else:
            if len(pts) < 2:
                continue
            seg = f"M {pts[0][0]:.2f} {pts[0][1]:.2f} " + " ".join(
                f"L {p[0]:.2f} {p[1]:.2f}" for p in pts[1:])
            out.append(seg)
    return " ".join(out)


try:
    import svgcore as _svgcore   # Rust: Schneider fitting at ~30x Catmull speed
except ImportError:              # pragma: no cover
    _svgcore = None


def simplify_svg(svg: str, eps: float, min_area: float = 4.0,
                 method: str = "auto") -> str:
    """Simplify every supported <path> in an SVG document.

    method='auto' uses the Rust Schneider fitter when built (equal quality to
    the Python reference at ~23% fewer points and 30x the speed of Catmull);
    falls back to DP+Catmull otherwise. 'catmull'/'schneider' force a path.
    """
    use_rust = _svgcore is not None and method in ("auto", "schneider")

    def repl(m: re.Match) -> str:
        tag = m.group(0)
        dm = _D_RE.search(tag)
        if not dm:
            return tag
        if use_rust:
            new_d = _svgcore.simplify_path(dm.group(1), eps, min_area, 60.0)
        else:
            new_d = simplify_path_d(dm.group(1), eps, min_area,
                                    method="catmull" if method == "auto" else method)
        if new_d is None:
            return tag          # unsupported commands: keep original
        if new_d == "":
            return ""           # path fully vanished (below min_area)
        return tag[: dm.start(1)] + new_d + tag[dm.end(1):]

    return _PATH_TAG_RE.sub(repl, svg)
