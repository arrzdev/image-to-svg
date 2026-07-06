"""Shared-boundary vectorization: fit every region boundary ONCE.

Independent per-region tracing fits each boundary twice (once per neighbor);
the two fits never coincide, so every boundary is a potential hairline gap or
overlap and every junction grows spurs — exactly the deep-zoom artifacts a
professional output cannot have. Here we extract the label map's boundary
GRAPH (junction nodes + edges between region pairs), simplify/fit each edge
once, and rebuild every region from the shared geometry. Coincidence is then
guaranteed by construction.

Coordinates: pixel-corner lattice. Corner (x, y) with x in 0..W, y in 0..H.
Pixel (i, j) spans corners (j, i)-(j+1, i+1). The image border counts as a
boundary against the virtual outside label -1.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np


def build_edges(labels: np.ndarray):
    """Extract the boundary graph.

    Returns (edges, node_set) where edges is a list of dicts:
      {"pts": [(x,y), ...], "pair": (label_a, label_b)}
    Each edge runs junction-to-junction (or is a closed loop with no junction).
    """
    H, W = labels.shape
    ext = np.full((H + 2, W + 2), -1, dtype=np.int64)
    ext[1:-1, 1:-1] = labels

    # crack segments between corners; key = sorted corner pair
    # vertical crack at corner column x between rows y..y+1 separates
    # pixels ext[y+1, x] (left) and ext[y+1, x+1] (right) in ext coords.
    segs: Dict[Tuple[Tuple[int, int], Tuple[int, int]], Tuple[int, int]] = {}
    for y in range(H):
        rowL = ext[y + 1, : W + 1]
        rowR = ext[y + 1, 1: W + 2]
        for x in np.nonzero(rowL != rowR)[0]:
            a, b = (int(x), y), (int(x), y + 1)
            segs[(a, b)] = (int(rowL[x]), int(rowR[x]))   # (west, east)
    for y in range(H + 1):
        rowU = ext[y, 1: W + 1]
        rowD = ext[y + 1, 1: W + 1]
        for x in np.nonzero(rowU != rowD)[0]:
            a, b = (int(x), y), (int(x) + 1, y)
            segs[(a, b)] = (int(rowU[x]), int(rowD[x]))   # (north, south)

    # corner incidence
    inc: Dict[Tuple[int, int], List] = defaultdict(list)
    for key in segs:
        a, b = key
        inc[a].append(key)
        inc[b].append(key)

    nodes = {c for c, ks in inc.items() if len(ks) != 2}

    edges = []
    used = set()

    def walk(start_key, from_corner):
        """Walk from a node along cracks until the next node; return pts."""
        pts = [from_corner]
        key = start_key
        cur = key[1] if key[0] == from_corner else key[0]
        used.add(key)
        pts.append(cur)
        while cur not in nodes:
            nxt = [k for k in inc[cur] if k not in used]
            if not nxt:
                break
            key = nxt[0]
            used.add(key)
            cur = key[1] if key[0] == cur else key[0]
            pts.append(cur)
        return pts

    def left_labels(key, pts):
        """Which label is on the LEFT when walking pts[0]->pts[1] (screen
        coords, y down)? Returns (left_label, right_label) for that direction.
        Vertical crack pair=(west,east); horizontal crack pair=(north,south)."""
        (x0, y0), (x1, y1) = pts[0], pts[1]
        a, b = segs[key]
        if x0 == x1:          # vertical crack
            return (b, a) if y1 > y0 else (a, b)   # walking down: left=east
        return (a, b) if x1 > x0 else (b, a)       # walking right: left=north

    for n in nodes:
        for key in inc[n]:
            if key in used:
                continue
            pts = walk(key, n)
            first_key = tuple(sorted((pts[0], pts[1])))
            lf, rt = left_labels(first_key, pts)
            edges.append({"pts": pts, "pair": segs[key], "left": lf, "right": rt})

    # closed loops with no junctions (island boundaries)
    for key in segs:
        if key in used:
            continue
        start = key[0]
        pts = walk(key, start)
        first_key = tuple(sorted((pts[0], pts[1])))
        lf, rt = left_labels(first_key, pts)
        edges.append({"pts": pts, "pair": segs[key], "left": lf, "right": rt,
                      "loop": True})

    return edges, nodes


def region_loops(edges, n_labels: int):
    """Assemble each region's boundary loops from DIRECTED edges: every edge
    is walked with the region on its LEFT, so at any node the continuation is
    (near-)unique and loops close by construction."""
    # directed edge lists per region: (edge_index, reversed)
    directed: Dict[int, List[Tuple[int, bool]]] = defaultdict(list)
    for i, e in enumerate(edges):
        if e["left"] >= 0:
            directed[e["left"]].append((i, False))   # forward keeps left=r
        if e["right"] >= 0:
            directed[e["right"]].append((i, True))   # reversed puts r on left

    loops_by_region: Dict[int, List[List[Tuple[int, bool]]]] = {}
    for r, dedges in directed.items():
        remaining = set(dedges)
        # start-point index for directed edges
        starts: Dict[Tuple[int, int], List[Tuple[int, bool]]] = defaultdict(list)
        for i, rev in dedges:
            pts = edges[i]["pts"]
            starts[pts[-1] if rev else pts[0]].append((i, rev))
        loops = []
        while remaining:
            de = next(iter(remaining))
            remaining.discard(de)
            i0, rev0 = de
            pts0 = edges[i0]["pts"]
            loop = [de]
            start = pts0[-1] if rev0 else pts0[0]
            head = pts0[0] if rev0 else pts0[-1]
            guard = 0
            while head != start and guard < 200000:
                guard += 1
                cands = [d for d in starts[head] if d in remaining]
                if not cands:
                    break
                nxt = cands[0]
                remaining.discard(nxt)
                loop.append(nxt)
                j, jrev = nxt
                pj = edges[j]["pts"]
                head = pj[0] if jrev else pj[-1]
            loops.append(loop)
        loops_by_region[r] = loops
    return loops_by_region


def loops_to_svg(labels: np.ndarray, centers: np.ndarray, edges, loops_by_region,
                 simplify_fn=None) -> str:
    """Emit one path per region built from SHARED edge geometry.

    simplify_fn: optional fn(list[(x,y)], closed_hint) -> list[(x,y)] applied
    ONCE per edge; both adjacent regions then reuse the identical result.
    """
    H, W = labels.shape
    simplified: Dict[int, List[Tuple[float, float]]] = {}
    for i, e in enumerate(edges):
        pts = e["pts"]
        is_closed = len(pts) > 2 and pts[0] == pts[-1]
        if simplify_fn is not None and len(pts) > 2:
            if is_closed:
                # closed loop (island/border): simplify in CLOSED mode on the
                # open form, then re-close — open-mode DP collapses a loop to
                # its two identical endpoints and the region loses its boundary.
                interior = simplify_fn([(float(x), float(y)) for x, y in pts[:-1]],)
                if len(interior) < 3:
                    interior = [(float(x), float(y)) for x, y in pts[:-1]]
                interior = interior + [interior[0]]
            else:
                interior = simplify_fn([(float(x), float(y)) for x, y in pts])
                # endpoints are junctions — NEVER move them, or edges disconnect
                interior[0] = (float(pts[0][0]), float(pts[0][1]))
                interior[-1] = (float(pts[-1][0]), float(pts[-1][1]))
            simplified[i] = interior
        else:
            simplified[i] = [(float(x), float(y)) for x, y in pts]

    areas = np.bincount(labels.ravel())
    order = np.argsort(areas)[::-1]

    body = []
    for r in order:
        if r >= len(centers) or r not in loops_by_region:
            continue
        subpaths = []
        for loop in loops_by_region[r]:
            pts: List[Tuple[float, float]] = []
            for eid, rev in loop:
                seg = simplified[eid]
                seg = list(reversed(seg)) if rev else list(seg)
                if pts and pts[-1] == seg[0]:
                    pts.extend(seg[1:])
                else:
                    pts.extend(seg)
            if len(pts) < 3:
                continue
            d = f"M {pts[0][0]:.2f} {pts[0][1]:.2f} " + " ".join(
                f"L {p[0]:.2f} {p[1]:.2f}" for p in pts[1:-1]) + " Z"
            subpaths.append(d)
        if not subpaths:
            continue
        cr, cg, cb = centers[r]
        body.append(f'<path d="{" ".join(subpaths)}" '
                    f'fill="#{cr:02x}{cg:02x}{cb:02x}" fill-rule="evenodd"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">\n' + "\n".join(body) + "\n</svg>\n")


def dissolve_faint_pairs(labels: np.ndarray, centers: np.ndarray,
                         img: np.ndarray, contrast_thresh: float = 18.0,
                         protect_lum: int = 96):
    """Edge-support simplification: merge region pairs whose shared boundary
    has weak SOURCE-image contrast. Quantizing a smooth shading gradient
    manufactures boundaries the artist never drew — along those cracks the
    source pixels barely differ, while a real contour shows strong contrast.
    Measured per region-PAIR (mean RGB distance across every boundary crack),
    so a boundary that is partly faint but genuinely drawn elsewhere survives.
    Dark regions (lum < protect_lum) are line art and never merged.
    Returns (labels, centers) relabeled after union-find merging."""
    K = len(centers)
    imf = img.astype(np.float32)
    sums = np.zeros((K, K), np.float64)
    counts = np.zeros((K, K), np.int64)

    for (la, lb, diff) in (
        (labels[:, :-1], labels[:, 1:], np.linalg.norm(imf[:, :-1] - imf[:, 1:], axis=2)),
        (labels[:-1, :], labels[1:, :], np.linalg.norm(imf[:-1, :] - imf[1:, :], axis=2)),
    ):
        m = la != lb
        a, b = la[m], lb[m]
        lo, hi = np.minimum(a, b), np.maximum(a, b)
        np.add.at(sums, (lo, hi), diff[m])
        np.add.at(counts, (lo, hi), 1)

    lum = 0.2126 * centers[:, 0] + 0.7152 * centers[:, 1] + 0.0722 * centers[:, 2]
    parent = list(range(K))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    los, his = np.nonzero(counts)
    order = np.argsort(sums[los, his] / counts[los, his])
    for idx in order:
        i, j = int(los[idx]), int(his[idx])
        if counts[i, j] < 8:            # too short to judge
            continue
        if sums[i, j] / counts[i, j] >= contrast_thresh:
            break                        # sorted: everything after is stronger
        if lum[i] < protect_lum or lum[j] < protect_lum:
            continue
        parent[find(i)] = find(j)

    roots = [find(i) for i in range(K)]
    if len(set(roots)) == K:
        return labels, centers

    areas = np.bincount(labels.ravel(), minlength=K).astype(np.float64)
    new_ids = {}
    new_centers = []
    remap = np.zeros(K, np.int64)
    for i in range(K):
        r = roots[i]
        if r not in new_ids:
            members = [k for k in range(K) if roots[k] == r]
            w = areas[members]
            c = (centers[members].astype(np.float64) * w[:, None]).sum(0) / max(w.sum(), 1)
            new_ids[r] = len(new_centers)
            new_centers.append(np.round(c).astype(centers.dtype))
        remap[i] = new_ids[r]
    return remap[labels], np.asarray(new_centers)


def smooth_edges(edges, win: int = 5):
    """Moving-average along-curve smoothing of every edge polyline, applied
    BEFORE curve fitting. The crack lattice is pixel-staircase noise from the
    quantizer; the fitter tracks it faithfully, producing wobbly strokes.
    Smoothing first lets Schneider find the sweeping curve the artist drew.
    Junction endpoints stay pinned (open edges) so regions still connect;
    closed loops smooth with wraparound. Shared geometry stays shared: each
    edge is smoothed once, both neighbors reuse it."""
    if win <= 1:
        return edges
    k = np.ones(win) / win
    out = []
    for e in edges:
        pts = np.asarray(e["pts"], dtype=float)
        if len(pts) > win * 2:
            closed = tuple(pts[0]) == tuple(pts[-1])
            if closed:
                inner = pts[:-1]
                sm = np.stack([np.convolve(np.r_[inner[:, i][-win:], inner[:, i],
                                                 inner[:, i][:win]], k, 'same')[win:-win]
                               for i in range(2)], 1)
                pts = np.vstack([sm, sm[:1]])
            else:
                sm = pts.copy()
                for i in range(2):
                    sm[:, i] = np.convolve(np.r_[[pts[0, i]] * win, pts[:, i],
                                                 [pts[-1, i]] * win], k, 'same')[win:-win]
                sm[0], sm[-1] = pts[0], pts[-1]
                pts = sm
        out.append({**e, "pts": [tuple(p) for p in pts]})
    return out


def _reverse_cubic(c):
    return (c[6], c[7], c[4], c[5], c[2], c[3], c[0], c[1])


def _is_border_edge(e) -> bool:
    """Edge against the virtual outside label (-1): it lies ON the canvas
    frame and is covered by only ONE region, so the shared-boundary
    coincidence guarantee does not apply — it must stay exactly on the frame
    (smoothing rounds canvas corners; fit_open bows up to ~tol across 90°
    corners; both expose transparent hairlines nothing papers over)."""
    return e["left"] < 0 or e["right"] < 0


def _line_cubics(pts):
    """Exact line-cubics for an axis-aligned lattice polyline: one segment per
    straight run (vertices kept only where the direction changes). Used for
    canvas-frame edges, which the fitter cannot reproduce exactly."""
    P = [(float(x), float(y)) for x, y in pts]
    vs = [P[0]]
    for i in range(1, len(P) - 1):
        (x0, y0), (x1, y1), (x2, y2) = vs[-1], P[i], P[i + 1]
        if (x1 - x0) * (y2 - y1) != (y1 - y0) * (x2 - x1):
            vs.append(P[i])
    vs.append(P[-1])
    return [(ax, ay, ax + (bx - ax) / 3.0, ay + (by - ay) / 3.0,
             ax + 2.0 * (bx - ax) / 3.0, ay + 2.0 * (by - ay) / 3.0, bx, by)
            for (ax, ay), (bx, by) in zip(vs[:-1], vs[1:])]


def _emit_regions(labels, centers, loops_by_region, fitted) -> Tuple[str, list]:
    """Emit region paths from per-edge cubic chains. Returns (svg, plan);
    plan records, in emission order, every (region, loop, edge, rev, n_cubics)
    so a post-refinement pass can map refined coordinates back to edges."""
    H, W = labels.shape

    def emit(loop):
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

    areas = np.bincount(labels.ravel())
    order = np.argsort(areas)[::-1]
    body = []
    plan = []   # per emitted path: list of loops, each list of (eid, rev, n)
    for r in order:
        if r >= len(centers) or r not in loops_by_region:
            continue
        subpaths, ploops = [], []
        for lp in loops_by_region[r]:
            d = emit(lp)
            if not d:
                continue
            subpaths.append(d)
            ploops.append([(eid, rev, len(fitted[eid])) for eid, rev in lp])
        if not subpaths:
            continue
        cr, cg, cb = centers[r]
        body.append(f'<path d="{" ".join(subpaths)}" '
                    f'fill="#{cr:02x}{cg:02x}{cb:02x}" fill-rule="evenodd"/>')
        plan.append(ploops)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}">\n' + "\n".join(body) + "\n</svg>\n")
    return svg, plan


def loops_to_svg_curves(labels: np.ndarray, centers: np.ndarray, edges,
                        loops_by_region, tol: float = 1.5,
                        corner_deg: float = 60.0, smooth_win: int = 0,
                        return_plan: bool = False, parsimony: float = 0.0):
    """Curve-fitted emission: each edge Schneider-fitted ONCE (svgcore), both
    regions reuse the identical cubic chain (reversal of a cubic is exact:
    P0,P1,P2,P3 -> P3,P2,P1,P0), so boundaries still coincide perfectly.

    parsimony > 0 switches to the Potrace-style fitter (fit_open_parsimony,
    value = opttolerance): minimal-segment polygon within a ±0.5px band +
    sub-pixel vertex adjust + area-preserving merge. Fits the RAW lattice
    (no pre-smoothing) yet is structurally wobble-free — sub-band noise
    cannot create segments. 0.2 beats smooth+Schneider on all axes; 0.5-1.0
    trades quality for the Recraft point corner."""
    import svgcore
    raw_edges = edges
    if parsimony <= 0 and smooth_win > 1:
        edges = smooth_edges(edges, smooth_win)

    fitted: Dict[int, List[Tuple[float, ...]]] = {}
    for i, e in enumerate(edges):
        if _is_border_edge(e):
            fitted[i] = _line_cubics(raw_edges[i]["pts"])
            continue
        pts = e["pts"]
        flat = [float(v) for xy in pts for v in xy]
        if parsimony > 0:
            cubics = svgcore.fit_open_parsimony(flat, 1.0, parsimony)
        else:
            cubics = svgcore.fit_open(flat, tol, corner_deg)
        fitted[i] = [tuple(cubics[k:k + 8]) for k in range(0, len(cubics), 8)]

    svg, plan = _emit_regions(labels, centers, loops_by_region, fitted)
    return (svg, plan, fitted) if return_plan else svg


_NUM_RE = None


def resnap_refined(refined_svg: str, plan, labels, centers, loops_by_region,
                   edges=None) -> str:
    """Restore shared-edge coincidence after DiffVG refinement.

    DV moves each path's points independently, so the two copies of a shared
    edge drift apart — white hairline gaps at deep zoom, the exact artifact
    class shared-boundary vectorization exists to kill. But DV preserves point
    ORDER, and `plan` records which cubics belong to which edge in every path;
    so: parse the refined paths, collect each edge's (up to two) refined
    copies, AVERAGE them, and re-emit every region from the averaged shared
    geometry. The fidelity gain survives; coincidence is exact again."""
    import re
    global _NUM_RE
    if _NUM_RE is None:
        _NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")

    d_strings = re.findall(r'\bd="([^"]+)"', refined_svg)
    if len(d_strings) != len(plan):
        return refined_svg   # structure changed — refuse to guess

    acc: Dict[int, List[List[Tuple[float, ...]]]] = defaultdict(list)
    for d, ploops in zip(d_strings, plan):
        # cubics appear in emission order: subpaths concatenated; each
        # subpath contributes 1 M-point + 3 pts per C segment.
        nums = [float(x) for x in _NUM_RE.findall(d)]
        pos = 0
        for lp in ploops:
            n_cub = sum(n for _, _, n in lp)
            # M(2 floats) + n_cub * C(6 floats)
            block = nums[pos: pos + 2 + 6 * n_cub]
            pos += 2 + 6 * n_cub
            cur = (block[0], block[1])
            cubs = []
            for k in range(n_cub):
                c1x, c1y, c2x, c2y, ex, ey = block[2 + 6 * k: 8 + 6 * k]
                cubs.append((cur[0], cur[1], c1x, c1y, c2x, c2y, ex, ey))
                cur = (ex, ey)
            i = 0
            for eid, rev, n in lp:
                chain = cubs[i: i + n]
                i += n
                if rev:   # store in the edge's canonical (forward) direction
                    chain = [_reverse_cubic(c) for c in reversed(chain)]
                acc[eid].append(chain)

    fitted: Dict[int, List[Tuple[float, ...]]] = {}
    for eid, copies in acc.items():
        if len(copies) == 1:
            fitted[eid] = copies[0]
        else:
            a, b = copies[0], copies[1]
            fitted[eid] = [tuple((x + y) / 2.0 for x, y in zip(ca, cb))
                           for ca, cb in zip(a, b)]

    # Junction snap: each edge's copies averaged independently, so edges
    # meeting at a node can still disagree by a hair — cluster by the node's
    # ORIGINAL lattice coordinate (open-edge endpoints are pinned junctions)
    # and set every incident anchor to the cluster mean.
    if edges is not None:
        at_node = defaultdict(list)   # node -> [(eid, 'start'|'end')]
        for eid in fitted:
            pts = edges[eid]["pts"]
            if tuple(pts[0]) == tuple(pts[-1]):
                continue   # closed loop, no junction
            at_node[tuple(pts[0])].append((eid, 0))
            at_node[tuple(pts[-1])].append((eid, 1))
        for node, incident in at_node.items():
            if len(incident) < 2:
                continue
            xs, ys = [], []
            for eid, end in incident:
                c = fitted[eid][-1] if end else fitted[eid][0]
                xs.append(c[6] if end else c[0])
                ys.append(c[7] if end else c[1])
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            for eid, end in incident:
                ch = fitted[eid]
                if end:
                    ch[-1] = ch[-1][:6] + (mx, my)
                else:
                    ch[0] = (mx, my) + ch[0][2:]

    svg, _ = _emit_regions(labels, centers, loops_by_region, fitted)
    # The refined coordinates live in the refined DOCUMENT's space (pydiffvg
    # bakes the input's width/height into them), not the label lattice —
    # reuse its <svg> opening tag verbatim so the viewBox matches the coords.
    m_hdr = re.search(r"<svg[^>]*>", refined_svg)
    if m_hdr:
        svg = re.sub(r"<svg[^>]*>", lambda _: m_hdr.group(0), svg, count=1)
    return svg
