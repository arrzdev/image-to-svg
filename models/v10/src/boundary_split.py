"""Per-element path emission for the shared-boundary pipeline.

`boundary.loops_to_svg_curves` emits ONE compound path per color region: every
disjoint island of that color plus every hole lives in a single evenodd path.
Renders fine, edits terribly — in Illustrator/Figma a professional expects one
path per visual element (Recraft's reference output averages ~10 pts/path).

This module regroups each region's loops into CONNECTED COMPONENTS before
emission:

  * an outer boundary loop + the holes directly inside it  -> one path,
  * a disjoint island of the same color                    -> its own path,
  * an island nested inside a hole (depth 2)               -> again its own
    path, with its OWN direct holes (depth 3), and so on.

Grouping is pure containment nesting computed on the ORIGINAL lattice
polylines (integer corner coordinates), so it is exact and independent of
smoothing/fitting. Loops of one region never share a crack segment (an edge
always separates two different labels), so a test point taken at the midpoint
of a vertical crack of loop A — coordinates (int, int+0.5) — can never lie on
loop B, and even-odd ray casting is unambiguous: horizontal segments are
skipped, vertical segments cross the ray at integer x only.

Paint order (regions large -> small) and the fitted cubic geometry are reused
verbatim from `boundary`, so the rendered pixels are identical to the compound
emitter's.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from boundary import _is_border_edge, _line_cubics, _reverse_cubic, smooth_edges


def _loop_polyline(loop, edges) -> np.ndarray:
    """Closed (N,2) float array of the loop's ORIGINAL lattice points."""
    pts: List[Tuple[float, float]] = []
    for eid, rev in loop:
        seg = edges[eid]["pts"]
        seg = list(reversed(seg)) if rev else list(seg)
        if pts and pts[-1] == tuple(map(float, seg[0])):
            seg = seg[1:]
        pts.extend((float(x), float(y)) for x, y in seg)
    if len(pts) > 1 and pts[0] != pts[-1]:
        pts.append(pts[0])
    return np.asarray(pts, dtype=float)


def _test_point(poly: np.ndarray):
    """Midpoint of a VERTICAL crack of the loop: y is half-integer, so a
    horizontal ray through it never passes through any lattice vertex."""
    dx = poly[1:, 0] - poly[:-1, 0]
    dy = poly[1:, 1] - poly[:-1, 1]
    vert = np.nonzero((dx == 0) & (dy != 0))[0]
    if len(vert):
        k = int(vert[0])
        return float(poly[k, 0]), float((poly[k, 1] + poly[k + 1, 1]) / 2.0)
    # degenerate loop (no area) — fall back to first segment midpoint
    return float((poly[0, 0] + poly[1, 0]) / 2.0), float((poly[0, 1] + poly[1, 1]) / 2.0)


def _contains(poly: np.ndarray, px: float, py: float) -> bool:
    """Even-odd ray cast (ray toward +x). Robust here because py is a
    half-integer and every vertex y of `poly` is an integer."""
    x1, y1 = poly[:-1, 0], poly[:-1, 1]
    x2, y2 = poly[1:, 0], poly[1:, 1]
    m = (y1 > py) != (y2 > py)
    if not m.any():
        return False
    xin = x1[m] + (py - y1[m]) * (x2[m] - x1[m]) / (y2[m] - y1[m])
    return bool(np.count_nonzero(xin > px) & 1)


def _group_loops(loops, edges) -> List[List[int]]:
    """Group a region's loops into connected components by containment
    nesting. Returns a list of groups; each group is [outer_idx, hole_idx...]
    where the holes are the outer loop's DIRECT children. Loops at even
    nesting depth start a new group (outer / island-in-hole); odd depth loops
    are holes attached to their direct parent."""
    n = len(loops)
    if n == 1:
        return [[0]]

    polys = [_loop_polyline(lp, edges) for lp in loops]
    bboxes, areas = [], []
    for poly in polys:
        if len(poly) < 4:
            bboxes.append((0.0, 0.0, -1.0, -1.0))
            areas.append(0.0)
            continue
        x, y = poly[:, 0], poly[:, 1]
        bboxes.append((x.min(), y.min(), x.max(), y.max()))
        areas.append(abs(float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1])) / 2.0))

    parent = [-1] * n
    for i in range(n):
        if len(polys[i]) < 4:
            continue
        px, py = _test_point(polys[i])
        best, best_area = -1, np.inf
        bi = bboxes[i]
        for j in range(n):
            if j == i or areas[j] <= areas[i] or areas[j] >= best_area:
                continue
            bj = bboxes[j]
            if bi[0] < bj[0] or bi[1] < bj[1] or bi[2] > bj[2] or bi[3] > bj[3]:
                continue
            if _contains(polys[j], px, py):
                best, best_area = j, areas[j]
        parent[i] = best

    depth = [-1] * n

    def _depth(i):
        if depth[i] >= 0:
            return depth[i]
        depth[i] = 0 if parent[i] < 0 else _depth(parent[i]) + 1
        return depth[i]

    groups = []
    slot = {}
    for i in range(n):            # original loop order kept for determinism
        if _depth(i) % 2 == 0:
            slot[i] = len(groups)
            groups.append([i])
    for i in range(n):
        if _depth(i) % 2 == 1:
            groups[slot[parent[i]]].append(i)
    return groups


def _emit_loop(loop, fitted) -> str:
    parts = []
    first = None
    for eid, rev in loop:
        chain = fitted[eid]
        if rev:
            chain = [_reverse_cubic(c) for c in reversed(chain)]
        for c in chain:
            if first is None:
                first = (c[0], c[1])
                parts.append(f"M {c[0]:.2f} {c[1]:.2f}")
            parts.append(f"C {c[2]:.2f} {c[3]:.2f} {c[4]:.2f} {c[5]:.2f} {c[6]:.2f} {c[7]:.2f}")
    if first is None:
        return ""
    parts.append("Z")
    return " ".join(parts)


def _emit_regions_split(labels, centers, loops_by_region, fitted, edges) -> str:
    H, W = labels.shape
    areas = np.bincount(labels.ravel())
    order = np.argsort(areas)[::-1]
    body = []
    for r in order:
        if r >= len(centers) or r not in loops_by_region:
            continue
        loops = loops_by_region[r]
        cr, cg, cb = centers[r]
        fill = f"#{cr:02x}{cg:02x}{cb:02x}"
        for grp in _group_loops(loops, edges):
            subpaths = [d for d in (_emit_loop(loops[i], fitted) for i in grp) if d]
            if not subpaths:
                continue
            body.append(f'<path d="{" ".join(subpaths)}" '
                        f'fill="{fill}" fill-rule="evenodd"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">\n' + "\n".join(body) + "\n</svg>\n")


def loops_to_svg_split(labels: np.ndarray, centers: np.ndarray, edges,
                       loops_by_region, tol: float = 1.5,
                       corner_deg: float = 60.0, smooth_win: int = 0) -> str:
    """Drop-in alternative to `boundary.loops_to_svg_curves`: identical
    fitting and paint order, but each connected component (outer boundary +
    its direct holes) becomes its OWN <path> instead of one compound path per
    color. Same rendered pixels; professionally editable structure."""
    import svgcore
    fit_edges = smooth_edges(edges, smooth_win) if smooth_win > 1 else edges

    fitted: Dict[int, List[Tuple[float, ...]]] = {}
    for i, e in enumerate(fit_edges):
        if _is_border_edge(e):
            fitted[i] = _line_cubics(edges[i]["pts"])
            continue
        pts = e["pts"]
        flat = [float(v) for xy in pts for v in xy]
        cubics = svgcore.fit_open(flat, tol, corner_deg)
        fitted[i] = [tuple(cubics[k:k + 8]) for k in range(0, len(cubics), 8)]

    # containment grouping uses the ORIGINAL (unsmoothed) integer lattice
    return _emit_regions_split(labels, centers, loops_by_region, fitted, edges)
