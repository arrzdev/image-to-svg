"""EXPERIMENT: width-constant contour rendering for drawn line networks.

Hypothesis: a character's dark contour network is a drawn stroke of roughly
constant width. The shared-boundary pipeline models it as a filled region
between two independently-wobbling boundaries — hence wavering width, wobbly
lines, and shading regions painted over the line art. Verified on elephant:
the network's EDT width spread (p10-p90) is only ~6% of its mean — ONE global
width (area-calibrated: ink px / skeleton px) models the whole network.

Emission model (arrived at by eye against the Recraft reference):
  * whole dark network -> skeleton graph -> junction-to-junction branches;
    spur pruning (strokes._prune_and_merge), Y-fork tip pruning
    (_prune_fork_tines), then tangent-CONTINUATION merging at junctions
    (_merge_continuations) so a through-stroke is smoothed+fitted as one
    path — the tangent kink at T-junction nodes was the first visible flaw.
  * per branch, a CONSTANT-BASELINE width profile: w_global everywhere,
    EXCEPT genuine local swells (smoothed EDT > 1.3*w — calligraphic joints,
    junction ink pooling) which follow the ink, and free ends whose ink
    tapers, which narrow to a pointed tip. Flat profile -> cheap
    <path stroke> with round caps/joins; varying profile -> ONE symmetric
    ribbon fill (single centerline, smooth width — no wedge seams, no
    independent-side waver).
  * SHAPE components (wink swoosh, eye glyph: skeleton p90/med width >= 1.5,
    vs <= 1.2 for every true line) are NOT stroked — the fill pipeline
    renders drawn glyphs faithfully; centerline models make them lumpy.
  * strokes paint LAST, so shading regions can never eat the line art.
    Fills come from shared-boundary emission on a label map whose line
    pixels were absorbed into the nearest region (strokes.absorb_mask).

Public API:
    contour_svg(labels, centers, **kw) -> (svg, info)
        kw: dark_lum=96, stroke_tol=2.5, stroke_smooth=11, corner_deg=75,
            width_mode="global"|"branch", width_scale=1.0, shape_p90=1.5,
            fill_tol=2.5, fill_smooth=9, blob_factor=1.9, spur_factor=0.9,
            merge_turn_deg=50, taper_ends=True, stub_factor=1.5
    contour_svg_from_testbed(tb, label_params=None, **kw) -> (svg, info)
        convenience: cached labels + fit_svg_size to original dims.

Reuses (imports, does not modify) strokes.py machinery:
_skeleton_branches, _prune_and_merge, _ribbon, absorb_mask.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
from scipy import ndimage

from strokes import (_STRUCT8, _luminance, _skeleton_branches,
                     _prune_and_merge, _branch_degrees, _smooth_open,
                     _smooth1d, _cubics_to_d, _ribbon, absorb_mask)


# ------------------------------------------------------------ centerline fit

def _fit_branch(pts: np.ndarray, tol: float, corner_deg: float,
                smooth_win: int, closed: bool) -> str:
    """Aggressively smoothed Schneider fit of one branch centerline.

    The centerline should look DRAWN: skeleton staircase wobble is the enemy,
    so the moving average runs wide (9-15) before fitting. Endpoints stay
    pinned (junction anchors must coincide across branches)."""
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


# --------------------------------------------------- junction continuation

def _end_dir(pix: List, at_head: bool, k: int = 9) -> Optional[np.ndarray]:
    """Unit direction pointing AWAY from the branch end (into the branch)."""
    p = np.asarray(pix, float)
    if len(p) < 2:
        return None
    seg = p[:min(k, len(p))] if at_head else p[::-1][:min(k, len(p))]
    v = seg[-1] - seg[0]
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else None


def _prune_fork_tines(branches: List[dict], med_w: float) -> List[dict]:
    """Resolve Y-forks at stroke tips: the skeleton of a tapering flick often
    splits into two short tines right at the tip; the runt renders as a barb
    (and can hijack the continuation merge, hooking the flick's end). At each
    node, among incident branches whose far end is free, keep the longest and
    drop the runts — a runt being clearly shorter than the winner AND only a
    couple of stroke widths long (genuine double flicks like a wink's two
    lashes are similar length and stay)."""
    deg = _branch_degrees(branches)
    drop = set()
    by_node: dict = {}
    for i, br in enumerate(branches):
        if br["closed"]:
            continue
        for here, far in ((br["a"], br["b"]), (br["b"], br["a"])):
            if here and (far == 0 or deg.get(far, 0) <= 1):
                by_node.setdefault(here, []).append(i)
    for node, idxs in by_node.items():
        if len(idxs) < 2:
            continue
        idxs = sorted(set(idxs), key=lambda i: -len(branches[i]["pix"]))
        longest = len(branches[idxs[0]]["pix"])
        for i in idxs[1:]:
            n = len(branches[i]["pix"])
            if n < max(2.0 * med_w, 0.5 * longest):
                drop.add(i)
    return [br for i, br in enumerate(branches) if i not in drop]


def _merge_continuations(branches: List[dict], max_turn_deg: float = 50.0
                         ) -> List[dict]:
    """Fuse the smoothest-through pair of branches at each junction.

    A drawn contour PASSES THROUGH a T-junction; the skeleton graph cuts it
    in two, and fitting the halves with pinned endpoints leaves a tangent
    kink right at the node. At every node, greedily merge the incident pair
    whose end tangents are most anti-aligned (turn angle through the node
    below max_turn_deg), so the through-stroke is smoothed and fitted as ONE
    path. Side branches keep ending on the node and just abut (round caps)."""
    cos_lim = -np.cos(np.radians(max_turn_deg))   # dot must be below this
    changed = True
    while changed:
        changed = False
        deg = _branch_degrees(branches)
        for node, d in deg.items():
            if d < 2:
                continue
            inc = []                       # (branch, at_head, away_dir)
            for br in branches:
                if br["closed"]:
                    continue
                for at_head, nid in ((True, br["a"]), (False, br["b"])):
                    if nid == node:
                        v = _end_dir(br["pix"], at_head)
                        if v is not None:
                            inc.append((br, at_head, v))
            best, best_dot = None, cos_lim
            for i in range(len(inc)):
                for j in range(i + 1, len(inc)):
                    if inc[i][0] is inc[j][0]:
                        continue           # a loop back onto itself
                    dot = float(np.dot(inc[i][2], inc[j][2]))
                    if dot < best_dot:
                        best, best_dot = (inc[i], inc[j]), dot
            if best is None:
                continue
            (b1, h1, _), (b2, h2, _) = best
            p1 = list(reversed(b1["pix"])) if h1 else list(b1["pix"])
            n1 = b1["b"] if h1 else b1["a"]
            p2 = list(b2["pix"]) if h2 else list(reversed(b2["pix"]))
            n2 = b2["b"] if h2 else b2["a"]
            branches = [br for br in branches if br is not b1 and br is not b2]
            branches.append({"pix": p1 + p2[1:], "a": n1, "b": n2,
                             "closed": False})
            changed = True
            break
    return branches


# --------------------------------------------------------------- extraction

def extract_contour_strokes(labels: np.ndarray, centers: np.ndarray,
                            dark_lum: float = 96.0,
                            stroke_tol: float = 2.5,
                            stroke_smooth: int = 11,
                            corner_deg: float = 75.0,
                            width_mode: str = "global",
                            width_scale: float = 1.0,
                            blob_factor: float = 1.9,
                            spur_factor: float = 0.9,
                            min_area: int = 30,
                            min_branch_px: int = 4,
                            merge_turn_deg: float = 50.0,
                            taper_ends: bool = True,
                            stub_factor: float = 1.5,
                            shape_p90: float = 1.5,
                            ) -> Tuple[List[dict], np.ndarray, dict]:
    """Model every dark-label component as constant-width strokes.

    Unlike strokes.line_components there is NO thinness gate: the whole
    contour network qualifies. Blob zones (medial width > blob_factor *
    component median) are cut out and left as fills.

    Returns (strokes, stroke_mask, info); each stroke is
    {"d", "width", "color"}; stroke_mask covers the absorbed (line) pixels.
    info: {"widths": per-branch medians, "global_width", "spread", ...}
    """
    from skimage.morphology import medial_axis

    dark = [li for li in range(len(centers))
            if _luminance(centers[li]) < dark_lum]
    stroke_mask = np.zeros(labels.shape, bool)
    strokes: List[dict] = []
    pend: List[dict] = []          # branch records awaiting global width
    tot_area = tot_skel = 0
    info = {"dark_labels": dark, "components": 0, "branches": 0,
            "widths": [], "wlens": [], "blob_px": 0, "global_width": 0.0,
            "spread": 0.0}

    for li in dark:
        lab_mask = labels == li
        if not lab_mask.any():
            continue
        comp, n = ndimage.label(lab_mask, structure=_STRUCT8)
        color = tuple(int(v) for v in centers[li])
        for ci in range(1, n + 1):
            mask = comp == ci
            area = int(mask.sum())
            if area < min_area:
                continue
            skel, dist = medial_axis(mask, return_distance=True)
            if not skel.any():
                continue
            med_w = float(np.median(dist[skel] * 2.0))

            # ---- shape gate FIRST (before blob split): a component whose
            # width profile is strongly non-constant (wink swoosh, eye glyph:
            # p90/med >= ~2.3 vs <= 1.2 for every true line component) is a
            # drawn SHAPE — the fill pipeline renders it faithfully; any
            # centerline decomposition (or blob-patch + stroke mix) is lumpy.
            wp0 = dist[skel] * 2.0
            if float(np.percentile(wp0, 90)) > shape_p90 * med_w:
                info["shape_fills"] = info.get("shape_fills", 0) + 1
                continue

            # ---- wide-band gate: a UNIFORM thick band (shield rim ~36px,
            # badge ring ~40px) passes the shape gate (constant width!) but
            # is a silhouette element, not a drawn line — stroke-ifying it at
            # the network width erodes it catastrophically (QA: q −0.28).
            # True line networks measure ~4-8px at 1024.
            max_w = max(12.0, 0.014 * max(labels.shape))
            if med_w > max_w:
                info["band_fills"] = info.get("band_fills", 0) + 1
                continue

            # ---- blob split: solid patches are fills, not strokes
            blob_skel = skel & (dist * 2.0 > blob_factor * med_w)
            if blob_skel.any():
                _, (iy, ix) = ndimage.distance_transform_edt(
                    ~skel, return_indices=True)
                blob_mask = mask & blob_skel[iy, ix]
                bl, nb = ndimage.label(blob_mask, structure=_STRUCT8)
                sizes = np.bincount(bl.ravel())
                keep = [b for b in range(1, nb + 1)
                        if sizes[b] > (1.5 * med_w) ** 2]
                if keep:
                    blob_mask = np.isin(bl, keep)
                    info["blob_px"] += int(blob_mask.sum())
                    mask = mask & ~blob_mask
                    if int(mask.sum()) < min_area:
                        continue
                    skel, dist = medial_axis(mask, return_distance=True)
                    if not skel.any():
                        continue

            branches, node_lbl = _skeleton_branches(skel)
            branches = _prune_and_merge(branches, dist, spur_factor)
            med_w_c = float(np.median(dist[skel] * 2.0))
            branches = _prune_fork_tines(branches, med_w_c)
            if merge_turn_deg > 0:
                branches = _merge_continuations(branches, merge_turn_deg)
            branches = [b for b in branches if len(b["pix"]) >= min_branch_px]
            if not branches:
                continue

            # node centroids: every incident branch ends on the same point
            cent = {0: None}
            for nid in range(1, int(node_lbl.max()) + 1):
                yx = np.argwhere(node_lbl == nid)
                if len(yx):
                    cent[nid] = yx.mean(axis=0)

            info["components"] += 1
            deg = _branch_degrees(branches)
            for br in branches:
                pix = np.asarray(br["pix"], float)
                widths = dist[tuple(pix.astype(int).T)] * 2.0
                w_med = float(np.median(widths))
                for end, nid in ((0, br["a"]), (-1, br["b"])):
                    if not br["closed"] and nid and cent.get(nid) is not None:
                        pix[end] = cent[nid]
                pts = pix[:, ::-1] + 0.5      # (y,x) -> (x,y) pixel centers
                head_free = (not br["closed"]
                             and (br["a"] == 0 or deg.get(br["a"], 0) <= 1))
                tail_free = (not br["closed"]
                             and (br["b"] == 0 or deg.get(br["b"], 0) <= 1))
                pend.append({"pts": pts, "widths": widths, "w_med": w_med,
                             "closed": br["closed"], "color": color,
                             "head_free": head_free, "tail_free": tail_free})
                info["widths"].append(w_med)
                info["wlens"].append(len(br["pix"]))
                info["branches"] += 1
            stroke_mask |= mask
            tot_area += int(mask.sum())
            tot_skel += int(skel.sum())

    if not pend:
        return strokes, stroke_mask, info

    w = np.asarray(info["widths"], float)
    l = np.asarray(info["wlens"], float)
    # area calibration: ink mass / centerline length is the width that
    # reproduces the drawn coverage (EDT medians sit a half-pixel low on
    # antialiased quantized masks)
    gw = tot_area / max(tot_skel, 1)
    lo, hi = np.percentile(np.repeat(w, l.astype(int)), (10, 90))
    info["global_width"] = float(gw)
    info["median_width"] = float(np.average(w, weights=l))
    info["spread"] = float((hi - lo) / max(gw, 0.5))

    for pb in pend:
        base = gw if width_mode == "global" else pb["w_med"]
        w_body = max(base * width_scale, 0.75)
        seg, segw = pb["pts"], np.asarray(pb["widths"], float)
        # drop floating stubs: an isolated snippet shorter than ~1.5 widths
        # renders as a lone dot (label-map break debris), worse than nothing
        if (pb["head_free"] and pb["tail_free"]
                and len(seg) < stub_factor * w_body):
            continue
        # ---- constant-baseline width profile.  The drawn line is w_body
        # everywhere EXCEPT where the ink genuinely departs: local swells
        # (calligraphic joints, junction pooling — sm_w >> w_body) rise with
        # the ink, and free ends whose ink thins out taper to a point.
        # Branches whose profile stays flat emit as cheap constant-width
        # <path stroke>; the rest emit as ONE symmetric ribbon — a single
        # centerline with a smooth width function, so there are no wedge
        # seams and no independently-wobbling sides.
        sm_w = _smooth1d(segw, 9)
        prof = np.full(len(seg), w_body, float)
        varying = False
        if not pb["closed"]:
            swell = sm_w > 1.3 * w_body
            if swell.any():
                prof[swell] = sm_w[swell]
                varying = True
            if taper_ends:
                for at_tail in (False, True):
                    free = pb["tail_free"] if at_tail else pb["head_free"]
                    if not free or len(seg) < 8:
                        continue
                    view_w = sm_w if at_tail else sm_w[::-1]
                    K = int(min(max(2.5 * w_body, 6), len(seg) // 2))
                    if K < 3 or float(np.mean(view_w[-3:])) > 0.8 * w_body:
                        continue      # end doesn't taper — keep round cap
                    full = np.nonzero(view_w[-K:] >= 0.95 * w_body)[0]
                    j = len(seg) - K + (int(full[-1]) if len(full) else 0)
                    j = min(max(j, 2), len(seg) - 3)
                    sl = slice(j, None) if at_tail else slice(None, len(seg) - j)
                    vw = sm_w[sl]
                    prof[sl] = np.minimum(prof[sl], np.maximum(vw, 0.7))
                    varying = True
                    if at_tail:
                        pb["tail_tip"] = max(float(sm_w[-1]) / 2.0, 0.5)
                    else:
                        pb["head_tip"] = max(float(sm_w[0]) / 2.0, 0.5)
        if varying:
            prof = _smooth1d(prof, 5)
            # same aggressive centerline smoothing as strokes get (_ribbon
            # itself only smooths win-5; skeleton staircase would leak back)
            seg = _smooth_open(seg, stroke_smooth)
            dr = _ribbon(seg, prof * width_scale / 2.0, stroke_tol,
                         head_tip_r=pb.get("head_tip"),
                         tail_tip_r=pb.get("tail_tip"))
            if dr:
                strokes.append({"d": dr, "width": 0.0,
                                "color": pb["color"], "kind": "ribbon"})
                info["ribbons"] = info.get("ribbons", 0) + 1
                continue
        d = _fit_branch(seg, stroke_tol, corner_deg, stroke_smooth,
                        pb["closed"])
        if d:
            strokes.append({"d": d, "width": w_body, "color": pb["color"],
                            "kind": "stroke"})
    info["strokes"] = len(strokes)
    return strokes, stroke_mask, info


# ------------------------------------------------------------------ emission

def _stroke_elements(strokes: List[dict]) -> str:
    parts = []
    for st in strokes:
        r, g, b = st["color"]
        hexc = f"#{r:02x}{g:02x}{b:02x}"
        if st.get("kind") in ("wedge", "ribbon"):
            parts.append(f'<path d="{st["d"]}" fill="{hexc}"/>')
        else:
            parts.append(
                f'<path d="{st["d"]}" fill="none" stroke="{hexc}" '
                f'stroke-width="{st["width"]:.2f}" stroke-linecap="round" '
                f'stroke-linejoin="round"/>')
    return "\n".join(parts)


def contour_svg(labels: np.ndarray, centers: np.ndarray,
                fill_tol: float = 2.5, fill_smooth: int = 9,
                fill_corner_deg: float = 60.0,
                **kw) -> Tuple[str, dict]:
    """Full width-constant emission: absorbed fills + stroke network on top."""
    import boundary

    strokes, stroke_mask, info = extract_contour_strokes(labels, centers, **kw)
    new_labels = absorb_mask(labels, stroke_mask)
    edges, _ = boundary.build_edges(new_labels)
    loops = boundary.region_loops(edges, len(centers))
    svg = boundary.loops_to_svg_curves(new_labels, centers, edges, loops,
                                       tol=fill_tol,
                                       corner_deg=fill_corner_deg,
                                       smooth_win=fill_smooth)
    if strokes:
        svg = svg.replace("\n</svg>",
                          "\n" + _stroke_elements(strokes) + "\n</svg>")
    info["strokes"] = len(strokes)
    return svg, info


def contour_svg_from_testbed(tb, label_params: Optional[dict] = None,
                             **kw) -> Tuple[str, dict]:
    """Testbed convenience: cached label map in, original-size SVG out."""
    from svgutil import fit_svg_size

    labels, centers = tb.labels(**(label_params or {}))
    svg, info = contour_svg(labels, centers, **kw)
    _, _, (ow, oh), _ = tb.prep()
    return fit_svg_size(svg, ow, oh), info
