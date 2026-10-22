"""Stroke-aware modeling: detect thin line-art regions, replace their filled
outlines with true SVG strokes.

Why: shared-boundary fills model a drawn line as TWO independently fitted
boundary sides. The two fits never agree, so stroke width wavers, and tips
(where both sides meet) end in jagged/notched blobs — the two remaining
deep-zoom artifact classes vs the professional reference. A stroke path is the
generative model of line art: ONE centerline + a width. Width is constant by
construction, tips get clean caps for free, and the path needs roughly half
the anchors of its outline.

Pipeline:
  1. detect: dark (lum < DARK_LINE_LUM) connected components that are thin +
     elongated by medial-axis width stats. Blobby sub-parts (a pupil touching
     the eye outline ring) are SPLIT OFF by medial width and stay as fills.
  2. centerline: medial_axis skeleton -> pixel graph -> junction-to-junction
     branch paths (with spur pruning and degree-2 merge), smoothed and
     Schneider-fitted once each (svgcore.fit_open).
  3. width: per-branch median of 2*EDT, globally calibrated so that
     sum(length*width) matches the component's true pixel area; branches whose
     width profile still varies >~30% split at the sharpest width change.
     Free ends whose width tapers off get a filled taper WEDGE from stroke
     width down to the true ink tip — the clean pointed tip the artist drew.
  4. junctions: where strokes meet, the source ink pools (fattens); a filled
     disc per junction node, sized to the local EDT maximum, recovers that
     mass (and hides round-cap overshoot at shallow-angle crossings). Tiny
     junction-junction connector branches are contracted into a single node
     first so split X-crossings anchor at ONE shared point.
  5. hybrid emit: stroke pixels are absorbed into their neighboring labels
     (nearest-label relabel) so the fill layer has no hole under the stroke;
     fills come from the standard shared-boundary emission on that absorbed
     map; stroke paths + junction discs append last and paint on top, like
     the original ink.

Public API:
    hybrid_svg(image_path, params)      -> (svg, info)   # full pipeline
    hybrid_from_context(ctx, **kw)      -> (svg, info)   # reuse a built ctx
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import ndimage

from pipelines.base import DARK_LINE_LUM

# 8-neighbourhood offsets, orthogonal first so chain walking prefers
# non-diagonal continuations (avoids skipping over a corner pixel).
_OFFS = ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1))
_STRUCT8 = np.ones((3, 3), bool)


def _luminance(c) -> float:
    return 0.299 * float(c[0]) + 0.587 * float(c[1]) + 0.114 * float(c[2])


# --------------------------------------------------------------- detection

def line_components(labels: np.ndarray, centers: np.ndarray,
                    dark_lum: float = DARK_LINE_LUM,
                    max_width: float = 8.0,
                    min_elongation: float = 5.0,
                    min_area: int = 30,
                    blob_factor: float = 1.7,
                    scale_ref: int = 1024) -> List[dict]:
    """Find stroke-like connected components in the label map.

    A component qualifies if its palette color is dark (line art) and its
    medial-axis stats say thin + elongated: median width <= max_width px
    (scaled by image size relative to scale_ref) and skeleton-length /
    median-width >= min_elongation.

    Blob separation: line art often TOUCHES filled dark shapes (a pupil
    resting on the eye-outline ring quantizes into one component). Medial
    pixels wider than blob_factor * median seed "blob" zones; mask pixels
    whose nearest medial pixel is a blob pixel are cut out and kept as fills,
    and only the thin remainder becomes strokes.

    Returns [{label, mask, skel, dist, med_w, skel_len, area}] where mask is
    the (blob-free) thin part only.
    """
    from skimage.morphology import medial_axis

    scale = max(labels.shape) / float(scale_ref)
    w_cap = max_width * max(scale, 0.5)
    out = []
    for li in range(len(centers)):
        if _luminance(centers[li]) >= dark_lum:
            continue
        lab_mask = labels == li
        if not lab_mask.any():
            continue
        comp, n = ndimage.label(lab_mask, structure=_STRUCT8)
        for ci in range(1, n + 1):
            mask = comp == ci
            if int(mask.sum()) < min_area:
                continue
            skel, dist = medial_axis(mask, return_distance=True, rng=0)
            widths = dist[skel] * 2.0
            if widths.size == 0:
                continue
            med_w = float(np.median(widths))
            if med_w > w_cap:
                continue

            # ---- split off blobby sub-parts (kept as fills)
            blob_skel = skel & (dist * 2.0 > blob_factor * med_w)
            if blob_skel.any():
                _, (iy, ix) = ndimage.distance_transform_edt(
                    ~skel, return_indices=True)
                blob_mask = mask & blob_skel[iy, ix]
                # ignore small bulges (junction thickenings), keep real blobs
                bl, nb = ndimage.label(blob_mask, structure=_STRUCT8)
                sizes = np.bincount(bl.ravel())
                keep_ids = [b for b in range(1, nb + 1)
                            if sizes[b] > (1.5 * med_w) ** 2]
                if keep_ids:
                    blob_mask = np.isin(bl, keep_ids)
                    mask = mask & ~blob_mask
                    if int(mask.sum()) < min_area:
                        continue
                    skel, dist = medial_axis(mask, return_distance=True, rng=0)
                    widths = dist[skel] * 2.0
                    if widths.size == 0:
                        continue
                    med_w = float(np.median(widths))

            skel_len = int(skel.sum())
            if med_w > w_cap or skel_len < min_elongation * max(med_w, 1.0):
                continue
            out.append({"label": li, "mask": mask, "skel": skel, "dist": dist,
                        "med_w": med_w, "skel_len": skel_len,
                        "area": int(mask.sum())})
    return out


# --------------------------------------------------- skeleton graph -> paths

def _skeleton_branches(skel: np.ndarray) -> Tuple[List[dict], np.ndarray]:
    """Decompose a skeleton into branch paths between nodes.

    Nodes are clusters of skeleton pixels with degree != 2 (endpoints and
    junctions). Returns (branches, node_lbl); each branch is
    {"pix": [(y,x)...], "a": node_id_or_0, "b": node_id_or_0, "closed": bool}
    where pix runs node-to-node inclusive of one anchor pixel at each end.
    Isolated cycles come back with closed=True and node ids 0.
    """
    H, W = skel.shape
    deg = ndimage.convolve(skel.astype(np.uint8), np.ones((3, 3), np.uint8),
                           mode="constant") - 1
    deg[~skel] = 0
    node_mask = skel & (deg != 2)
    node_lbl, n_nodes = ndimage.label(node_mask, structure=_STRUCT8)

    visited = np.zeros_like(skel, bool)      # chain pixels consumed
    branches: List[dict] = []

    def neighbors(y, x):
        for dy, dx in _OFFS:
            yy, xx = y + dy, x + dx
            if 0 <= yy < H and 0 <= xx < W and skel[yy, xx]:
                yield yy, xx

    # walks starting from every node pixel into each unvisited chain pixel
    node_pix = np.argwhere(node_mask)
    for ny, nx in node_pix:
        for cy, cx in neighbors(ny, nx):
            if node_mask[cy, cx] or visited[cy, cx]:
                continue
            path = [(int(ny), int(nx)), (int(cy), int(cx))]
            visited[cy, cx] = True
            py, px = ny, nx
            y, x = cy, cx
            end_node = 0
            while True:
                nxt = None
                for yy, xx in neighbors(y, x):
                    if (yy, xx) == (py, px):
                        continue
                    if node_mask[yy, xx]:
                        # don't jump diagonally back into the node we left
                        if len(path) == 2 and node_lbl[yy, xx] == node_lbl[ny, nx]:
                            continue
                        nxt = (yy, xx, True)
                        break
                    if not visited[yy, xx]:
                        nxt = (yy, xx, False)
                        break
                if nxt is None:
                    break
                yy, xx, is_node = nxt
                path.append((int(yy), int(xx)))
                if is_node:
                    end_node = int(node_lbl[yy, xx])
                    break
                visited[yy, xx] = True
                py, px = y, x
                y, x = yy, xx
            branches.append({"pix": path, "a": int(node_lbl[ny, nx]),
                             "b": end_node, "closed": False})

    # isolated cycles: chain pixels never reached from a node
    remaining = skel & ~node_mask & ~visited
    for y0, x0 in np.argwhere(remaining):
        if visited[y0, x0]:
            continue
        path = [(int(y0), int(x0))]
        visited[y0, x0] = True
        py, px = -1, -1
        y, x = int(y0), int(x0)
        while True:
            nxt = None
            for yy, xx in neighbors(y, x):
                if (yy, xx) != (py, px) and not visited[yy, xx] and not node_mask[yy, xx]:
                    nxt = (yy, xx)
                    break
            if nxt is None:
                break
            path.append((int(nxt[0]), int(nxt[1])))
            visited[nxt] = True
            py, px = y, x
            y, x = nxt
        if len(path) >= 4:
            branches.append({"pix": path, "a": 0, "b": 0, "closed": True})
    return branches, node_lbl


def _branch_degrees(branches: List[dict]) -> Dict[int, int]:
    d: Dict[int, int] = {}
    for br in branches:
        for n in (br["a"], br["b"]):
            if n:
                d[n] = d.get(n, 0) + 1
    return d


def _prune_and_merge(branches: List[dict], dist: np.ndarray,
                     spur_factor: float = 0.7) -> List[dict]:
    """Drop spur branches (short, ending at an endpoint) — medial-axis noise
    at stroke ends and corners — then merge branch pairs left alone at a
    junction into single through-paths.

    spur_factor is in units of the ATTACH-point width; medial noise spurs are
    about half that long (one radius), while genuine tapered flicks (an eye's
    eyeliner wing) run several widths — 0.7 measured best on the elephant
    (1.5 pruned real flicks and cost ~0.008 quality)."""
    deg = _branch_degrees(branches)
    kept = []
    for br in branches:
        if br["closed"]:
            kept.append(br)
            continue
        ends = (br["a"], br["b"])
        free = [n for n in ends if n and deg.get(n, 0) == 1]
        if free and len(br["pix"]) > 1:
            # width where the branch attaches to the rest of the network
            attach = br["pix"][0] if deg.get(br["a"], 0) > 1 else br["pix"][-1]
            w = dist[attach] * 2.0
            if len(br["pix"]) < max(3.0, spur_factor * w):
                continue
        kept.append(br)

    # merge junctions that now have exactly two incident branches
    changed = True
    while changed:
        changed = False
        deg = _branch_degrees(kept)
        for node, d in deg.items():
            if d != 2:
                continue
            pair = [br for br in kept if not br["closed"] and node in (br["a"], br["b"])]
            if len(pair) != 2 or pair[0] is pair[1]:
                continue
            b1, b2 = pair
            p1 = b1["pix"] if b1["b"] == node else list(reversed(b1["pix"]))
            n1 = b1["a"] if b1["b"] == node else b1["b"]
            p2 = b2["pix"] if b2["a"] == node else list(reversed(b2["pix"]))
            n2 = b2["b"] if b2["a"] == node else b2["a"]
            merged = {"pix": p1 + p2[1:], "a": n1, "b": n2, "closed": False}
            kept = [br for br in kept if br is not b1 and br is not b2]
            kept.append(merged)
            changed = True
            break
    return kept


# ------------------------------------------------------- width segmentation

def _smooth1d(v: np.ndarray, win: int) -> np.ndarray:
    if len(v) <= win or win <= 1:
        return np.asarray(v, float)
    k = np.ones(win) / win
    return np.convolve(np.r_[[v[0]] * win, v, [v[-1]] * win].astype(float),
                       k, "same")[win:-win]


def _split_by_width(widths: np.ndarray, var_tol: float = 0.35,
                    min_len: int = 12, depth: int = 0) -> List[Tuple[int, int]]:
    """Recursive segmentation of a width profile into pieces whose spread is
    within +-var_tol of the piece median. Returns [(start, end)) index spans."""
    n = len(widths)
    med = max(float(np.median(widths)), 0.5)
    if n < 2 * min_len or depth >= 3:
        return [(0, n)]
    lo, hi = np.percentile(widths, (10, 90))
    if (hi - lo) / (2.0 * med) <= var_tol:
        return [(0, n)]
    sm = _smooth1d(widths, 7)
    grad = np.abs(np.diff(sm))
    cut = int(np.argmax(grad[min_len - 1: n - min_len])) + min_len
    left = _split_by_width(widths[:cut], var_tol, min_len, depth + 1)
    right = _split_by_width(widths[cut:], var_tol, min_len, depth + 1)
    return left + [(a + cut, b + cut) for a, b in right]


# ------------------------------------------------------------------ fitting

def _smooth_open(pts: np.ndarray, win: int) -> np.ndarray:
    """Moving-average smooth an open polyline, endpoints pinned."""
    if win <= 1 or len(pts) <= win * 2:
        return np.asarray(pts, float)
    sm = np.asarray(pts, float).copy()
    k = np.ones(win) / win
    for i in range(2):
        sm[:, i] = np.convolve(np.r_[[pts[0, i]] * win, pts[:, i],
                                     [pts[-1, i]] * win], k, "same")[win:-win]
    sm[0], sm[-1] = pts[0], pts[-1]
    return sm


def _cubics_to_d(cubics, closed: bool) -> str:
    if not cubics:
        return ""
    parts = [f"M {cubics[0]:.2f} {cubics[1]:.2f}"]
    for k0 in range(0, len(cubics), 8):
        c = cubics[k0:k0 + 8]
        parts.append(f"C {c[2]:.2f} {c[3]:.2f} {c[4]:.2f} {c[5]:.2f} "
                     f"{c[6]:.2f} {c[7]:.2f}")
    if closed:
        parts.append("Z")
    return " ".join(parts)


def _fit_polyline(pts: np.ndarray, tol: float, corner_deg: float,
                  smooth_win: int, closed: bool) -> str:
    """Smooth + Schneider-fit an open/closed centerline; return path 'd'."""
    import svgcore

    pts = np.asarray(pts, float)
    if closed:
        if smooth_win > 1 and len(pts) > smooth_win * 2:
            k = np.ones(smooth_win) / smooth_win
            pts = np.stack([np.convolve(np.r_[pts[-smooth_win:, i], pts[:, i],
                                              pts[:smooth_win, i]], k, "same")
                            [smooth_win:-smooth_win] for i in range(2)], 1)
        pts = np.vstack([pts, pts[:1]])
    else:
        pts = _smooth_open(pts, smooth_win)
    flat = [float(v) for p in pts for v in p]
    return _cubics_to_d(svgcore.fit_open(flat, tol, corner_deg), closed)


# ------------------------------------------------------------- taper wedges

def _tangents(pts: np.ndarray) -> np.ndarray:
    t = np.gradient(pts, axis=0)
    n = np.linalg.norm(t, axis=1, keepdims=True)
    return t / np.maximum(n, 1e-9)


def _cap_subpath(center: np.ndarray, n_unit: np.ndarray, t_unit: np.ndarray,
                 r: float, n: int = 10) -> str:
    """A closed 180° round-cap subpath (extra `M…L…Z` appended to a ribbon's
    path 'd'). Runs from center + n_unit*r, through the OUTWARD bulge
    center + t_unit*r, to center - n_unit*r — i.e. a semicircle whose chord is
    exactly the ribbon's flat butt edge (the two nub corners) and whose bulge
    sits just past the end. As its own subpath it leaves the body fit
    byte-for-byte unchanged; the union with the body simply rounds the butt."""
    th = np.linspace(0.0, np.pi, n)
    p = (center[None, :]
         + np.cos(th)[:, None] * n_unit[None, :] * r
         + np.sin(th)[:, None] * t_unit[None, :] * r)
    d = f" M {p[0, 0]:.2f} {p[0, 1]:.2f}"
    for q in p[1:]:
        d += f" L {q[0]:.2f} {q[1]:.2f}"
    return d + " Z"


def _ribbon(pts: np.ndarray, halfw: np.ndarray, tol: float,
            head_tip_r: Optional[float] = None,
            tail_tip_r: Optional[float] = None) -> str:
    """Variable-width ribbon fill: symmetric offsets of the SAME centerline
    (so width is smooth and symmetric by construction — no independent-side
    waver). Ends with tip_r set get a pointed apex extended by that leftover
    medial radius (the true ink tip); ends without were cut flat — a
    width-spanning straight butt that reads as a rectangular NUB where the
    ribbon meets another element. Those flat butts now get a semicircular
    ROUND CAP (radius = the end half-width), appended as a separate subpath so
    the body fit is untouched, matching the stroke-linecap="round" of true
    strokes."""
    import svgcore

    pts = _smooth_open(np.asarray(pts, float), 5)
    halfw = np.maximum(_smooth1d(np.asarray(halfw, float), 5), 0.35)
    tang = _tangents(pts)
    norm = np.stack([-tang[:, 1], tang[:, 0]], 1)
    left = pts + norm * halfw[:, None]
    right = pts - norm * halfw[:, None]
    seq = [left]
    if tail_tip_r is not None:
        seq.append((pts[-1] + tang[-1] * max(tail_tip_r, 0.5))[None, :])
    seq.append(right[::-1])
    if head_tip_r is not None:
        seq.append((pts[0] - tang[0] * max(head_tip_r, 0.5))[None, :])
    seq.append(left[:1])
    poly = np.vstack(seq)
    flat = [float(v) for p in poly for v in p]
    d = _cubics_to_d(svgcore.fit_open(flat, tol, 45.0), True)
    if not d:
        return d
    # round-cap the flat butts (tip_r None); bulge outward past the end
    if tail_tip_r is None:
        d += _cap_subpath(pts[-1], norm[-1], tang[-1], float(halfw[-1]))
    if head_tip_r is None:
        d += _cap_subpath(pts[0], -norm[0], -tang[0], float(halfw[0]))
    return d


# ---------------------------------------------------------- junction patches

def _junction_patches(node_ids, cent, node_lbl, skel, dist, scale,
                      end_w, min_pool: float = 1.25
                      ) -> List[Tuple[float, float, float, float]]:
    """Ink-pooling discs for junction nodes.

    Where artist strokes meet, the source ink fattens (pools): the EDT at the
    junction is larger than any incident branch's width because the crossing
    strokes overlap. Our centerline strokes render junctions cleaner-but-
    thinner than the source. A filled disc at the junction, sized to the local
    EDT maximum (the inscribed radius of the pooled ink), recovers that mass —
    and also swallows the round-cap overshoot of shallow-angle crossings.

    Returns [(cx_px, cy_px, r, w_inc)] in pixel-center coordinates. A disc is
    only worth emitting when it pokes out of the strokes already painted
    there: r must exceed min_pool * the widest incident stroke's half-width.
    """
    H, W = skel.shape
    out = []
    for nid in node_ids:
        c = cent.get(nid)
        if c is None:
            continue
        cy, cx = c
        w_inc = end_w.get(nid, 0.0)          # widest incident stroke width
        # search window: junction fattening spreads ~1 width along branches
        rad = max(int(round(w_inc)), 2)
        y0, y1 = max(int(cy) - rad, 0), min(int(cy) + rad + 1, H)
        x0, x1 = max(int(cx) - rad, 0), min(int(cx) + rad + 1, W)
        win_sk = skel[y0:y1, x0:x1]
        if not win_sk.any():
            continue
        win_d = np.where(win_sk, dist[y0:y1, x0:x1], 0.0)
        yy, xx = np.unravel_index(int(np.argmax(win_d)), win_d.shape)
        r = float(win_d[yy, xx]) * scale
        if r <= min_pool * (w_inc / 2.0) or r < 1.0:
            continue                          # no real pooling — disc hidden
        out.append((x0 + xx + 0.5, y0 + yy + 0.5, r, w_inc))
    return out


def _disc_d(cx: float, cy: float, r: float) -> str:
    return (f"M {cx - r:.2f} {cy:.2f} "
            f"a {r:.2f} {r:.2f} 0 1 0 {2 * r:.2f} 0 "
            f"a {r:.2f} {r:.2f} 0 1 0 {-2 * r:.2f} 0 Z")


# junction-junction connector branches shorter than this fraction of their
# own (pooled) width are contracted into a single node (see extract_strokes).
# 0.0 = contract only sub-min_branch_px connectors (the ones that would be
# dropped anyway, leaving a pinched two-anchor junction); larger values
# measured worse — they start moving real geometry. (Convex-hull shaped
# patches and median->EDT flare ribbons were also tried and measured worse
# than plain inscribed discs: both overshoot into ink that isn't there.)
CONTRACT_FACTOR = 0.0


# ----------------------------------------------------------- stroke extract

def extract_strokes(labels: np.ndarray, centers: np.ndarray,
                    dark_lum: float = DARK_LINE_LUM,
                    max_width: float = 8.0,
                    min_elongation: float = 5.0,
                    tol: float = 1.0, corner_deg: float = 60.0,
                    smooth_win: int = 7,
                    width_var_tol: float = 0.35,
                    taper_ends: bool = True,
                    min_branch_px: int = 4,
                    junction_patches: bool = True) -> Tuple[List[dict], np.ndarray, dict]:
    """Detect line components and convert them to stroke primitives.

    Returns (strokes, stroke_mask, info). Each stroke:
      {"d": path_d, "width": float, "color": (r,g,b),
       "kind": "stroke"|"ribbon"|"wedge"|"junction"}
    (non-"stroke" kinds are filled shapes: width 0; "junction" is one path of
    ink-pooling discs per component). stroke_mask marks every pixel of
    every component that was converted (these get absorbed out of the fill
    label map). Components whose skeleton yields nothing usable stay fills.
    """
    comps = line_components(labels, centers, dark_lum, max_width, min_elongation)
    stroke_mask = np.zeros(labels.shape, bool)
    strokes: List[dict] = []
    stats = {"components": len(comps), "branches": 0, "ribbons": 0,
             "wedges": 0, "junctions": 0, "widths": [],
             "fallback_components": 0}

    for comp in comps:
        skel, dist = comp["skel"], comp["dist"]
        color = tuple(int(v) for v in centers[comp["label"]])
        branches, node_lbl = _skeleton_branches(skel)
        branches = _prune_and_merge(branches, dist)

        # contract junction-junction connector branches shorter than the
        # local stroke width: the medial axis splits an X-crossing (or any
        # tight multi-way junction) into two nearby nodes joined by a tiny
        # branch. Filtering that branch out would leave two independent
        # anchor points a few px apart — a pinched junction with cap
        # overshoot. Union the two nodes instead: every incident branch
        # anchors on ONE shared centroid and the node keeps its full degree
        # (so it also qualifies for a pooling patch below).
        parent: Dict[int, int] = {}

        def _find(x: int) -> int:
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        kept_branches = []
        for br in branches:
            if (not br["closed"] and br["a"] and br["b"]
                    and br["a"] != br["b"]):
                L = len(br["pix"])
                w_conn = float(np.median(
                    dist[tuple(np.asarray(br["pix"]).T)]) * 2.0)
                if L < max(min_branch_px, CONTRACT_FACTOR * w_conn):
                    ra, rb = _find(br["a"]), _find(br["b"])
                    if ra != rb:
                        parent[max(ra, rb)] = min(ra, rb)
                    continue          # connector absorbed into the junction
            kept_branches.append(br)
        branches = [b for b in kept_branches if len(b["pix"]) >= min_branch_px]
        if not branches:
            stats["fallback_components"] += 1
            continue
        for br in branches:
            br["a"], br["b"] = _find(br["a"]), _find(br["b"])
        deg = _branch_degrees(branches)

        # node cluster centroids: shared endpoint for every incident branch
        # (contracted clusters average all their member nodes' pixels)
        groups: Dict[int, List[int]] = {}
        for nid in range(1, int(node_lbl.max()) + 1):
            groups.setdefault(_find(nid), []).append(nid)
        cent = {0: None}
        for rep, members in groups.items():
            yx = (np.argwhere(node_lbl == members[0]) if len(members) == 1
                  else np.argwhere(np.isin(node_lbl, members)))
            if len(yx):
                cent[rep] = yx.mean(axis=0)

        # global width calibration: EDT medians systematically off by the
        # odd/even half-pixel + antialiased quantization; scale all branch
        # widths so sum(len*width) reproduces the component's pixel area.
        seglens, segmeds = [], []
        for br in branches:
            w = dist[tuple(np.array(br["pix"]).T)] * 2.0
            seglens.append(len(br["pix"]))
            segmeds.append(max(np.median(w), 0.5))
        est_area = float(np.dot(seglens, segmeds))
        s = comp["area"] / est_area if est_area > 0 else 1.0
        s = float(np.clip(s, 0.7, 1.15))

        comp_strokes: List[dict] = []
        end_w: Dict[int, float] = {}   # junction node -> widest incident stroke
        ok = True
        for br in branches:
            pix = np.asarray(br["pix"], float)
            widths = dist[tuple(pix.astype(int).T)] * 2.0 * s
            # anchor endpoints on their junction centroid (shared point)
            for end, nid in ((0, br["a"]), (-1, br["b"])):
                if not br["closed"] and nid and cent.get(nid) is not None:
                    pix[end] = cent[nid]
            pts = pix[:, ::-1] + 0.5     # (y,x) -> (x,y) pixel centers
            w_med = float(np.median(widths))
            sm_w = _smooth1d(widths, 7)
            lo, hi = np.percentile(sm_w, (10, 90))
            spread = (hi - lo) / (2.0 * max(w_med, 0.5))
            head_free = (not br["closed"]
                         and (br["a"] == 0 or deg.get(br["a"], 0) <= 1))
            tail_free = (not br["closed"]
                         and (br["b"] == 0 or deg.get(br["b"], 0) <= 1))

            if not br["closed"] and spread > width_var_tol and len(pts) >= 6:
                # width genuinely varies (e.g. a long taper): variable-width
                # ribbon fill — one centerline, symmetric offsets, pointed
                # apex at free tapering ends, flat cut under junctions.
                def tip_r(free, w_end):
                    if not (taper_ends and free):
                        return None
                    return max(float(w_end) / 2.0, 0.5)
                d = _ribbon(pts, sm_w / 2.0, tol,
                            head_tip_r=tip_r(head_free, sm_w[0]),
                            tail_tip_r=tip_r(tail_free, sm_w[-1]))
                if d:
                    comp_strokes.append({"d": d, "width": 0.0,
                                         "color": color, "kind": "ribbon"})
                    for end, nid in ((0, br["a"]), (-1, br["b"])):
                        if nid and deg.get(nid, 0) >= 3:
                            end_w[nid] = max(end_w.get(nid, 0.0),
                                             float(sm_w[end]))
                    stats["ribbons"] += 1
                    stats["widths"].append(w_med)
                    stats["branches"] += 1
                    continue

            seg, segw = pts, widths
            # taper free ends of constant-width strokes: replace the
            # overshooting round cap with a wedge down to the true ink tip
            for at_tail in ((False, True) if taper_ends else ()):
                free = tail_free if at_tail else head_free
                if not free or len(seg) < 8:
                    continue
                view_w = segw if at_tail else segw[::-1]
                K = int(min(max(2.5 * w_med, 6), len(seg) // 2))
                if K < 3 or float(np.mean(view_w[-3:])) > 0.8 * w_med:
                    continue   # end doesn't taper — keep the round cap
                view_p = seg if at_tail else seg[::-1]
                # trim point: last index (from the end) at ~full width
                full = np.nonzero(view_w[-K:] >= 0.95 * w_med)[0]
                j = len(seg) - K + (int(full[-1]) if len(full) else 0)
                j = min(max(j, 2), len(seg) - 3)
                wedge_pts = view_p[j:]
                wedge_hw = np.minimum(view_w[j:], w_med) / 2.0
                wedge_hw[0] = w_med / 2.0     # flush with the stroke body
                tip_r = max(float(view_w[-1]) / 2.0, 0.5)
                d = _ribbon(wedge_pts, wedge_hw, tol, tail_tip_r=tip_r)
                if d:
                    comp_strokes.append({"d": d, "width": 0.0,
                                         "color": color, "kind": "wedge"})
                    stats["wedges"] += 1
                    # stroke body stops at the wedge base
                    if at_tail:
                        seg, segw = seg[:j + 1], segw[:j + 1]
                    else:
                        seg, segw = seg[len(seg) - 1 - j:], segw[len(segw) - 1 - j:]

            if len(seg) >= 2:
                d = _fit_polyline(seg, tol, corner_deg, smooth_win, br["closed"])
                if not d:
                    ok = False
                else:
                    comp_strokes.append({"d": d, "width": max(w_med, 0.75),
                                         "color": color, "kind": "stroke"})
                    for nid in (br["a"], br["b"]):
                        if not br["closed"] and nid and deg.get(nid, 0) >= 3:
                            end_w[nid] = max(end_w.get(nid, 0.0),
                                             max(w_med, 0.75))
                    stats["widths"].append(w_med)
            stats["branches"] += 1

        # junction ink pooling: filled discs where strokes meet (see
        # _junction_patches). Emitted as ONE path per component.
        if junction_patches and comp_strokes and ok:
            jn = [nid for nid, dg in deg.items() if dg >= 3 and nid in end_w]
            discs = _junction_patches(jn, cent, node_lbl, skel, dist, s, end_w)
            if discs:
                d = " ".join(_disc_d(cx, cy, r) for cx, cy, r, _ in discs)
                comp_strokes.append({"d": d, "width": 0.0,
                                     "color": color, "kind": "junction"})
                stats["junctions"] += len(discs)

        if not comp_strokes or not ok:
            stats["fallback_components"] += 1
            continue
        strokes.extend(comp_strokes)
        stroke_mask |= comp["mask"]

    return strokes, stroke_mask, stats


# ------------------------------------------------------------- hybrid emit

def absorb_mask(labels: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Reassign every masked pixel to its nearest unmasked label (EDT
    nearest-neighbor relabel) so removing the stroke fills leaves no hole."""
    if not mask.any():
        return labels
    _, (iy, ix) = ndimage.distance_transform_edt(mask, return_indices=True)
    return labels[iy, ix]


def _stroke_elements(strokes: List[dict]) -> str:
    parts = []
    for st in strokes:
        r, g, b = st["color"]
        hexc = f"#{r:02x}{g:02x}{b:02x}"
        if st["kind"] != "stroke":
            parts.append(f'<path d="{st["d"]}" fill="{hexc}"/>')
        else:
            parts.append(
                f'<path d="{st["d"]}" fill="none" stroke="{hexc}" '
                f'stroke-width="{st["width"]:.2f}" stroke-linecap="round" '
                f'stroke-linejoin="round"/>')
    return "\n".join(parts)


def hybrid_from_context(ctx: dict, tol: float = 1.0, corner_deg: float = 60.0,
                        smooth_win: int = 5, stroke_smooth_win: int = 7,
                        max_width: float = 8.0, min_elongation: float = 5.0,
                        width_var_tol: float = 0.35,
                        taper_ends: bool = True,
                        junction_patches: bool = True) -> Tuple[str, dict]:
    """Hybrid emission from a shared_boundary build_context() result: fills
    re-emitted from the absorbed label map, stroke paths appended on top."""
    import boundary

    labels, centers = ctx["labels"], ctx["centers"]
    strokes, stroke_mask, stats = extract_strokes(
        labels, centers, max_width=max_width, min_elongation=min_elongation,
        tol=tol, corner_deg=corner_deg, smooth_win=stroke_smooth_win,
        width_var_tol=width_var_tol, taper_ends=taper_ends,
        junction_patches=junction_patches)
    stats["strokes"] = len(strokes)
    if not strokes:
        return ctx["svg"], stats

    new_labels = absorb_mask(labels, stroke_mask)
    edges, _ = boundary.build_edges(new_labels)
    loops = boundary.region_loops(edges, len(centers))
    svg = boundary.loops_to_svg_curves(new_labels, centers, edges, loops,
                                       tol=tol, corner_deg=corner_deg,
                                       smooth_win=smooth_win)
    svg = svg.replace("\n</svg>", "\n" + _stroke_elements(strokes) + "\n</svg>")
    return svg, stats


def hybrid_svg(image_path: str, params: Optional[dict] = None) -> Tuple[str, dict]:
    """Full pipeline: shared_boundary context + stroke-aware hybrid emission.

    params go to the shared_boundary pipeline (tol, smooth_win, num_colors...);
    stroke extraction reuses tol/corner_deg from them.
    """
    from pipelines import get_pipeline

    params = dict(params or {})
    pipe = get_pipeline("shared_boundary")
    ctx = pipe.build_context(image_path, params)
    p = pipe.resolved_params(params)
    return hybrid_from_context(ctx, tol=p["tol"], corner_deg=p["corner_deg"],
                               smooth_win=p["smooth_win"])
