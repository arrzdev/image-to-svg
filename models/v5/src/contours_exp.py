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


def _corner_indices(pts: np.ndarray, w: float,
                    min_turn_deg: float = 45.0) -> List[int]:
    """Sharp-corner indices on a raw centerline chain (serration V-notches).

    Turning angle between the incoming and outgoing chords of length ~1.5w;
    local maxima above min_turn_deg, non-max suppressed within a chord. Run
    BEFORE smoothing — the moving average erases exactly these corners, which
    is why serration notches used to render soft."""
    k = max(3, int(round(1.5 * w)))
    n = len(pts)
    if n < 2 * k + 3:
        return []
    p = np.asarray(pts, float)
    v1 = p[k:n - k] - p[:n - 2 * k]
    v2 = p[2 * k:] - p[k:n - k]
    dot = (v1 * v2).sum(1) / (np.linalg.norm(v1, axis=1)
                              * np.linalg.norm(v2, axis=1) + 1e-9)
    ang = np.degrees(np.arccos(np.clip(dot, -1, 1)))
    idx = []
    order = np.argsort(ang)[::-1]
    taken = np.zeros(len(ang), bool)
    for i in order:
        if ang[i] < min_turn_deg:
            break
        if taken[max(0, i - k):i + k].any():
            continue
        taken[i] = True
        idx.append(int(i) + k)          # offset back into pts index space
    return sorted(idx)


def _smooth_open_corners(pts: np.ndarray, win: int,
                         corners: List[int]) -> np.ndarray:
    """Moving-average smooth with CORNERS PINNED: each inter-corner segment
    smooths independently (endpoints pinned), so sharp V-notches survive for
    the fitter to anchor as hard corners."""
    if not corners:
        return _smooth_open(pts, win)
    out = []
    bounds = [0] + corners + [len(pts) - 1]
    for a, b in zip(bounds[:-1], bounds[1:]):
        seg = _smooth_open(pts[a:b + 1], win)
        out.append(seg if a == 0 else seg[1:])
    return np.vstack(out)


# ------------------------------------------------------------- texture gate

def _wiggle_rate(pix, win: int = 9, step: int = 3) -> float:
    """Alternating-turn density of a branch chain: (total |turning| minus
    |net turning|) per px of arclength, measured on the smoothed chain.

    A drawn line is straight, a single arc, or a deliberate curl — its turns
    all point one way, so total ~= net and the rate sits near 0 (elephant
    network branches: <= ~1.9 even at junction-merged S-bends; isolated real
    marks: <= ~0.9). A painted TEXTURE daub wobbles back and forth — turns
    cancel, total >> net (chopchop trunk/wood squiggles: 1.5-7.8). The win-9
    smoothing first removes skeleton staircase so it never reads as wiggle."""
    p = np.asarray(pix, float)
    if len(p) < 2 * step + 3:
        return 0.0
    p = _smooth_open(p, win)
    q = p[::step]
    if len(q) < 3:
        return 0.0
    v = np.diff(q, axis=0)
    n = np.linalg.norm(v, axis=1)
    keep = n > 1e-9
    v, n = v[keep], n[keep]
    if len(v) < 2:
        return 0.0
    ang = np.arctan2(v[:, 1], v[:, 0])
    d = np.diff(ang)
    d = (d + np.pi) % (2 * np.pi) - np.pi
    tot = float(np.degrees(np.abs(d).sum()))
    net = float(abs(np.degrees(d.sum())))
    return (tot - net) / max(float(n.sum()), 1e-9)


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
                            src_img: Optional[np.ndarray] = None,
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

    # ---- adjacency-based fleck recolor (stroke-layer only).  A dark-brown
    # label leaves tiny fragments hugging the black serrated line network;
    # each fleck gets stroked in its own brown, littering the outline.  Absorb
    # them: a SMALL component (< 250 px) of one dark label that is 8-adjacent
    # to a MUCH larger component (>= 10x its area) of a DIFFERENT dark label is
    # reassigned to that larger neighbour's label — the fleck folds into the
    # black line it clings to.  Large SHADING bands are safe (neither side
    # hits the 10x ratio).  Mutate a COPY so the fill layer never sees this.
    flecks_absorbed = 0
    if len(dark) > 1:
        labels = labels.copy()
        comp_id = np.zeros(labels.shape, np.int32)
        comp_label = {0: -1}
        comp_area = {0: 0}
        small: List[Tuple[int, np.ndarray]] = []
        nid = 1
        for li in dark:
            lm = labels == li
            if not lm.any():
                continue
            comp, n = ndimage.label(lm, structure=_STRUCT8)
            for ci in range(1, n + 1):
                m = comp == ci
                a = int(m.sum())
                comp_id[m] = nid
                comp_label[nid] = li
                comp_area[nid] = a
                if a < 250:
                    small.append((nid, m))
                nid += 1
        for cid, m in small:
            a = comp_area[cid]
            border = ndimage.binary_dilation(m, structure=_STRUCT8) & ~m
            best = None
            for ncid in np.unique(comp_id[border]):
                ncid = int(ncid)
                if ncid == 0 or ncid == cid:
                    continue
                if comp_label[ncid] == comp_label[cid]:
                    continue
                if comp_area[ncid] >= 10 * a:
                    if best is None or comp_area[ncid] > comp_area[best]:
                        best = ncid
            if best is not None:
                labels[m] = comp_label[best]
                flecks_absorbed += 1

    stroke_mask = np.zeros(labels.shape, bool)
    strokes: List[dict] = []
    pend: List[dict] = []          # branch records awaiting global width
    tot_area = tot_skel = 0
    info = {"dark_labels": dark, "components": 0, "branches": 0,
            "widths": [], "wlens": [], "blob_px": 0, "global_width": 0.0,
            "spread": 0.0, "flecks_absorbed": flecks_absorbed}

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
            is_band = False
            if float(np.percentile(wp0, 90)) > shape_p90 * med_w:
                # outline-BAND exemption (run-7 design): serrated outline
                # fragments are drawn LINES whose p90 is inflated by notch
                # pooling — signature: line-like coverage (area ≈ skeleton
                # length × width), elongated, and swells LOCALIZED (pools at
                # notches), unlike a glyph's smooth intentional taper (wink
                # swoosh: large swollen fraction) or a solid blob (coverage
                # ratio >> 1). Bands get corner-aware constant-width
                # stroking; glyphs stay fills.
                skel_px = int(skel.sum())
                cov = area / max(skel_px * med_w, 1.0)
                elong = skel_px / max(med_w, 1.0)
                # band vs glyph: a serrated band keeps a SOLID BASELINE width
                # between notch pools (p25 ≈ median), a tapered glyph's width
                # spans a ramp (p25 well below median — rabbit eyelids 0.4-0.6,
                # solid-baseline lines 0.8-1.0 across all targets).
                p25r = float(np.percentile(wp0, 25)) / max(med_w, 1e-6)
                # med_w >= 3: below EDT resolution the p25 test saturates and
                # tapered 2px glyphs (fox fur flicks) masquerade as bands.
                if med_w >= 3.0 and cov < 1.4 and elong > 6 and p25r > 0.8:
                    is_band = True
                else:
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
                # junction-pool exemption: a SMALL wide zone sitting ON a
                # skeleton junction (deg >= 3) is crossing-ink POOLING, not a
                # drawn blob — cut to a fill it renders as a black splat where
                # the reference keeps thin crossing lines. Keep it in the
                # stroke mask instead: the crossing strokes overlap there at
                # constant width (same color — the overlap is invisible).
                # Measured separation on chopchop: pools extent <= ~3.8x
                # med_w; genuine glyph blobs (trunk knots) >= 6x.
                if keep:
                    deg0 = ndimage.convolve(skel.astype(np.uint8),
                                            np.ones((3, 3), np.uint8),
                                            mode="constant") - 1
                    deg0[~skel] = 0
                    jn0 = skel & (deg0 >= 3)
                    kept2 = []
                    for b in keep:
                        m = bl == b
                        yx = np.argwhere(m)
                        ext = int(max(yx[:, 0].ptp(), yx[:, 1].ptp())) + 1
                        if ext < 4.0 * med_w and (m & jn0).any():
                            info["junction_pools"] = (
                                info.get("junction_pools", 0) + 1)
                            continue
                        kept2.append(b)
                    keep = kept2
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

            # ---- per-branch texture gate, BEFORE continuation merging: a
            # painted texture daub that touches the line network (directly or
            # via fleck absorption) becomes a short high-wiggle side branch —
            # stroked, it renders as a squiggly "noodle"; worse, the tangent
            # merge can fuse it into a real through-line and hook its end.
            # Drop such branches while they are still their own chains and
            # CARVE their ink out of the absorbed mask (nearest-skeleton-
            # branch ownership) so the fill layer renders the daub instead.
            # Threshold 2.2 clears every real elephant network branch
            # (max ~1.9 with junction-merged S-bends; pre-merge branches sit
            # lower still); measured daub branches run 2.4-7.8.
            if not is_band and len(branches) > 1:
                removed_chains: List[np.ndarray] = []
                noodle = [i for i, b in enumerate(branches)
                          if len(b["pix"]) >= 10
                          and _wiggle_rate(b["pix"]) > 2.2]
                for i in noodle:
                    removed_chains.append(
                        np.asarray(branches[i]["pix"], int))
                branches = [b for i, b in enumerate(branches)
                            if i not in noodle]
                # a daub glued END-TO-END onto a real line (no junction —
                # fleck absorption does this a lot) extends the line's own
                # branch with a squiggly tail that global wiggle can't see:
                # trim FREE ends back while their terminal window squiggles.
                deg_t = _branch_degrees(branches)
                K = 24
                for b in branches:
                    if b["closed"] or len(b["pix"]) < 2 * K:
                        continue
                    for at_head in (True, False):
                        nid = b["a"] if at_head else b["b"]
                        if nid != 0 and deg_t.get(nid, 0) > 1:
                            continue          # junction end: leave anchored
                        cut = 0
                        while (len(b["pix"]) - cut >= 2 * K
                               and cut <= len(b["pix"]) // 3):
                            term = (b["pix"][cut:cut + K] if at_head
                                    else b["pix"][-K - cut:
                                                  len(b["pix"]) - cut])
                            if _wiggle_rate(term) <= 2.2:
                                break
                            cut += K // 2
                        if cut:
                            if at_head:
                                removed_chains.append(
                                    np.asarray(b["pix"][:cut], int))
                                b["pix"] = b["pix"][cut:]
                            else:
                                removed_chains.append(
                                    np.asarray(b["pix"][-cut:], int))
                                b["pix"] = b["pix"][:-cut]
                            info["texture_trims"] = (
                                info.get("texture_trims", 0) + 1)
                if removed_chains:
                    brid = np.zeros(mask.shape, np.int32)
                    for b in branches:
                        yx = np.asarray(b["pix"], int)
                        brid[yx[:, 0], yx[:, 1]] = 1
                    for yx in removed_chains:
                        brid[yx[:, 0], yx[:, 1]] = 2
                    on = brid > 0
                    _, (iy2, ix2) = ndimage.distance_transform_edt(
                        ~on, return_indices=True)
                    drop_px = mask & (brid[iy2, ix2] == 2)
                    mask = mask & ~drop_px
                    info["texture_branches"] = (
                        info.get("texture_branches", 0) + len(noodle))
                    branches = [b for b in branches
                                if len(b["pix"]) >= min_branch_px]
                    if not branches or int(mask.sum()) < min_area:
                        continue

            if merge_turn_deg > 0:
                branches = _merge_continuations(branches, merge_turn_deg)
            branches = [b for b in branches if len(b["pix"]) >= min_branch_px]
            if not branches:
                continue

            # ---- texture-squiggle gate: a SMALL isolated component whose
            # centerline wiggles back and forth is a painted texture daub
            # (wood grain / trunk marks), not a drawn line — stroked at
            # constant width it renders as a wobbly "noodle". Leave it OUT of
            # the stroke mask entirely so the fill layer renders the daub
            # faithfully (blobby, like the source). Guard rails: bands are
            # exempt (serration zigzag is intentional); big multi-branch
            # networks are exempt (junction-merged through-strokes can carry
            # legitimate S-bends, elephant measures up to ~1.9); long chains
            # are exempt (a long wavy line is drawn, not daubed). Isolated
            # REAL marks measure <= ~0.9; daubs 1.5-7.8.
            if not is_band and len(branches) <= 3:
                chain_len = sum(len(b["pix"]) for b in branches)
                if chain_len <= 160:
                    wavg = sum(_wiggle_rate(b["pix"]) * len(b["pix"])
                               for b in branches) / max(chain_len, 1)
                    if wavg > 1.0:
                        info["texture_fills"] = info.get("texture_fills",
                                                         0) + 1
                        continue

            # node centroids: every incident branch ends on the same point
            cent = {0: None}
            for nid in range(1, int(node_lbl.max()) + 1):
                yx = np.argwhere(node_lbl == nid)
                if len(yx):
                    cent[nid] = yx.mean(axis=0)

            info["components"] += 1
            deg = _branch_degrees(branches)
            # distance-to-junction map for the swell clamp at emit time:
            # junction ink pooling inflates the EDT right where branches
            # meet, and the swell profile (sm_w > 1.3*w_body) would follow
            # it — every converging branch fattens and the union renders as
            # a black blob. Junction nodes come from the SAME skeleton the
            # branches were traced on, so merged through-strokes see their
            # mid-chain junctions too.
            degj = ndimage.convolve(skel.astype(np.uint8),
                                    np.ones((3, 3), np.uint8),
                                    mode="constant") - 1
            degj[~skel] = 0
            jnm = skel & (degj >= 3)
            jdist = (ndimage.distance_transform_edt(~jnm) if jnm.any()
                     else None)
            # anchor target per node: the node-cluster centroid is elongated by
            # junction ink pooling, so it can sit OFF the through-line's
            # centerline — a side branch capped there pokes a nub through the
            # through stroke (visible on the silhouette). Anchor instead to the
            # nearest pixel of ANOTHER incident branch's path near the node:
            # the cap then lands flush under the through stroke by construction
            # (all strokes share w_body). Falls back to the centroid when no
            # other branch passes nearby (true endpoint clusters).
            med_w_a = float(np.median(dist[skel] * 2.0))
            for br in branches:
                pix = np.asarray(br["pix"], float)
                widths = dist[tuple(pix.astype(int).T)] * 2.0
                junc_d = (jdist[tuple(pix.astype(int).T)]
                          if jdist is not None
                          else np.full(len(pix), 1e9))
                w_med = float(np.median(widths))
                for end, nid in ((0, br["a"]), (-1, br["b"])):
                    if not br["closed"] and nid and cent.get(nid) is not None:
                        target = cent[nid]
                        # tight radius: the through-line passes THROUGH the
                        # node (centroid bias <= w/2); parallel neighboring
                        # strokes sit >= 1 width away — must never be caught
                        # (dense-line art: snapping to them detaches the end).
                        best_d2 = max(2.0, 0.8 * med_w_a) ** 2
                        for ob in branches:
                            if ob is br:
                                continue
                            op = np.asarray(ob["pix"], float)
                            d2 = ((op - target) ** 2).sum(axis=1)
                            j = int(np.argmin(d2))
                            if d2[j] < best_d2:
                                best_d2 = float(d2[j])
                                target = op[j]
                        pix[end] = target
                pts = pix[:, ::-1] + 0.5      # (y,x) -> (x,y) pixel centers
                head_free = (not br["closed"]
                             and (br["a"] == 0 or deg.get(br["a"], 0) <= 1))
                tail_free = (not br["closed"]
                             and (br["b"] == 0 or deg.get(br["b"], 0) <= 1))
                pend.append({"pts": pts, "widths": widths, "w_med": w_med,
                             "closed": br["closed"], "color": color,
                             "head_free": head_free, "tail_free": tail_free,
                             "band": is_band, "junc_d": junc_d})
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

    # ---- cross-component free-end bridging.  The label map breaks a drawn
    # line wherever a lighter region crosses it (straps, highlights, AA fuzz):
    # the pieces land in different components (or labels), no shared skeleton
    # node exists, and every break renders as a dash-gap the run-2 anchoring
    # can't reach.  Bridge them here: a FREE end that continues FORWARD
    # (<60° off its outward tangent — never sideways onto a parallel
    # neighbor) into another stroke within ~1.2 widths snaps onto it; two
    # mutually-facing free ends meet at their midpoint.  Snapped ends stop
    # being "free": no taper, no stub-drop (rescues tiny bridge dashes).
    raw_ends = []            # (pend_idx, 'head'|'tail', end_pt, out_tangent)
    for pi, pb in enumerate(pend):
        if pb["closed"] or len(pb["pts"]) < 2:
            continue
        pts = pb["pts"]
        k = min(6, len(pts) - 1)
        if pb["head_free"]:
            t = pts[0] - pts[k]
            raw_ends.append((pi, "head", pts[0].copy(),
                             t / (np.linalg.norm(t) + 1e-9)))
        if pb["tail_free"]:
            t = pts[-1] - pts[-1 - k]
            raw_ends.append((pi, "tail", pts[-1].copy(),
                             t / (np.linalg.norm(t) + 1e-9)))
    snap_r = max(2.0, 1.2 * gw)
    free_end_pts = {(pi, side): pt for pi, side, pt, _ in raw_ends}
    for pi, side, end, tdir in raw_ends:
        best = None
        for pj, ob in enumerate(pend):
            if pj == pi:
                continue
            d = np.linalg.norm(ob["pts"] - end, axis=1)
            j = int(np.argmin(d))
            if 1e-6 < d[j] < (best[0] if best else snap_r):
                best = (float(d[j]), pj, ob["pts"][j].copy(), j, len(ob["pts"]))
        if best is None:
            continue
        v = best[2] - end
        cosang = float(np.dot(v, tdir)) / (np.linalg.norm(v) + 1e-9)
        if cosang < 0.5:          # >60° off-tangent: parallel neighbor, skip
            continue
        target = best[2]
        # mutually-facing free ends meet halfway (end-to-end dash bridge)
        oj, olen = best[3], best[4]
        oside = "head" if oj <= 1 else ("tail" if oj >= olen - 2 else None)
        if oside is not None and (best[1], oside) in free_end_pts:
            target = (end + free_end_pts[(best[1], oside)]) / 2.0
        pb = pend[pi]
        if side == "head":
            pb["pts"][0] = target
            pb["head_free"] = False
        else:
            pb["pts"][-1] = target
            pb["tail_free"] = False
        info["bridged_ends"] = info.get("bridged_ends", 0) + 1

    # ---- source-ink-continuity extension.  Bridging only spans gaps
    # <= 1.2w; LONGER runs of drawn line lost by despeckle/smoothing (rabbit's
    # heart outline) leave a still-free end whose ink demonstrably continues
    # in the SOURCE raster.  Walk the dark ridge greedily from such ends (a
    # ±23° probe fan per 1px step, always the darkest sub-threshold pixel),
    # up to 4 widths; if the walk comes within 0.75w of another stroke, snap
    # to it and close the end (bridge); otherwise keep the traced tail and
    # leave the end free so it tapers at the TRUE ink end.  The dark_lum
    # cutoff (same as label selection) keeps the walker off midtone fills.
    if src_img is not None and len(src_img.shape) == 3:
        gray = src_img.astype(np.float32) @ np.array([0.299, 0.587, 0.114],
                                                     np.float32)
        Hs, Ws = gray.shape
        max_steps = int(round(4.0 * gw))
        snap_r2 = (0.75 * gw) ** 2
        for pi, pb in enumerate(pend):
            if pb["closed"] or len(pb["pts"]) < 4:
                continue
            for side in ("head", "tail"):
                if not pb[side + "_free"]:
                    continue
                pts = pb["pts"]
                k = min(6, len(pts) - 1)
                end = pts[0] if side == "head" else pts[-1]
                t = (pts[0] - pts[k]) if side == "head" else (pts[-1] - pts[-1 - k])
                n = np.linalg.norm(t)
                if n < 1e-6:
                    continue
                d = t / n
                p = end.copy()
                trail, snapped = [], None
                turn_budget = 2.1      # ~120° cumulative: lines curve, walks
                                       # that curl (blob boundaries) don't ship
                for _ in range(max_steps):
                    best = None
                    for ang in (-0.4, -0.2, 0.0, 0.2, 0.4):
                        ca, sa = np.cos(ang), np.sin(ang)
                        nd = np.array([d[0] * ca - d[1] * sa,
                                       d[0] * sa + d[1] * ca])
                        q = p + nd
                        xi, yi = int(q[0]), int(q[1])   # pts carry +0.5 already
                        if not (0 <= xi < Ws and 0 <= yi < Hs):
                            continue
                        v = float(gray[yi, xi])
                        if v >= dark_lum:
                            continue
                        # ridge test: a LINE has light ground within ~1 width
                        # on both sides; inside a dark blob it does not — the
                        # walker must never roam filled regions.
                        perp = np.array([-nd[1], nd[0]])
                        off = max(1.5, 1.1 * gw)
                        clear = 0
                        for s in (off, -off):
                            sx, sy = int(q[0] + perp[0] * s), int(q[1] + perp[1] * s)
                            if not (0 <= sx < Ws and 0 <= sy < Hs) or \
                                    gray[sy, sx] >= dark_lum:
                                clear += 1
                        if clear < 2:
                            continue
                        if best is None or v < best[0]:
                            best = (v, q, nd, abs(ang))
                    if best is None:
                        break
                    turn_budget -= best[3]
                    if turn_budget < 0:
                        break
                    _, p, d = best[:3]
                    trail.append(p.copy())
                    for pj, ob in enumerate(pend):
                        if pj == pi:
                            continue
                        d2 = ((ob["pts"] - p) ** 2).sum(axis=1)
                        j = int(np.argmin(d2))
                        if d2[j] < snap_r2:
                            snapped = ob["pts"][j].copy()
                            break
                    if snapped is not None:
                        break
                if not trail:
                    continue
                if snapped is not None:
                    trail.append(snapped)
                ext = np.asarray(trail)
                wext = np.full(len(ext), pb["widths"][0 if side == "head"
                                                      else -1], float)
                jext = np.full(len(ext), 1e9)   # open ink: no junction near
                if side == "head":
                    pb["pts"] = np.vstack([ext[::-1], pts])
                    pb["widths"] = np.r_[wext, pb["widths"]]
                    pb["junc_d"] = np.r_[jext, pb["junc_d"]]
                    if snapped is not None:
                        pb["head_free"] = False
                else:
                    pb["pts"] = np.vstack([pts, ext])
                    pb["widths"] = np.r_[pb["widths"], wext]
                    pb["junc_d"] = np.r_[pb["junc_d"], jext]
                    if snapped is not None:
                        pb["tail_free"] = False
                info["ink_extended"] = info.get("ink_extended", 0) + 1

    for pb in pend:
        base = gw if width_mode == "global" else pb["w_med"]
        w_body = max(base * width_scale, 0.75)
        seg, segw = pb["pts"], np.asarray(pb["widths"], float)
        # drop floating stubs: an isolated snippet shorter than ~1.5 widths
        # renders as a lone dot (label-map break debris), worse than nothing
        if (pb["head_free"] and pb["tail_free"]
                and len(seg) < stub_factor * w_body):
            continue
        # ---- serration BANDS: corner-aware CONSTANT-width stroke (run-7
        # design). Detect V-notch corners on the RAW chain (smoothing erases
        # them), smooth segments with corners pinned, fit with a corner
        # threshold the fitter will honor, and emit with MITER joins so the
        # renderer re-sharpens every notch geometrically. No swell profile —
        # the drawn serration line is uniform weight; notch pools are ink
        # artifacts, not intent.
        if pb.get("band"):
            corners = [] if pb["closed"] else _corner_indices(seg, w_body)
            import svgcore
            if pb["closed"]:
                d = _fit_branch(seg, stroke_tol, 60.0, stroke_smooth, True)
            else:
                sm = _smooth_open_corners(seg, stroke_smooth, corners)
                flat = [float(v) for p in sm for v in p]
                d = _cubics_to_d(svgcore.fit_open(flat, stroke_tol, 60.0),
                                 False)
            if d:
                strokes.append({"d": d, "width": w_body, "color": pb["color"],
                                "kind": "stroke", "join": "miter"})
                info["band_strokes"] = info.get("band_strokes", 0) + 1
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
            # junction-pool clamp: a swell within ~2.5 widths of a skeleton
            # junction node is crossing-ink pooling, not a calligraphic
            # joint — the drawn lines pass through at their own weight and
            # simply overlap. Following the pooled EDT there fattens every
            # converging branch into one black blob (palm-frond centers).
            jd = pb.get("junc_d")
            if jd is not None and len(jd) == len(swell):
                swell &= np.asarray(jd, float) > 2.5 * w_body
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
            join = st.get("join", "round")
            miter = ' stroke-miterlimit="8"' if join == "miter" else ""
            parts.append(
                f'<path d="{st["d"]}" fill="none" stroke="{hexc}" '
                f'stroke-width="{st["width"]:.2f}" stroke-linecap="round" '
                f'stroke-linejoin="{join}"{miter}/>')
    return "\n".join(parts)


def contour_svg(labels: np.ndarray, centers: np.ndarray,
                fill_tol: float = 2.5, fill_smooth: int = 9,
                fill_corner_deg: float = 60.0, fill_parsimony: float = 0.0,
                **kw) -> Tuple[str, dict]:
    """Full width-constant emission: absorbed fills + stroke network on top.

    fill_parsimony > 0 fits the shading-region boundaries with the Potrace
    parsimony fitter (wobble-free by construction) instead of smooth+Schneider
    — the fills then read as idealized flat shapes, like Recraft's."""
    import boundary

    strokes, stroke_mask, info = extract_contour_strokes(labels, centers, **kw)
    new_labels = absorb_mask(labels, stroke_mask)
    edges, _ = boundary.build_edges(new_labels)
    loops = boundary.region_loops(edges, len(centers))
    svg = boundary.loops_to_svg_curves(new_labels, centers, edges, loops,
                                       tol=fill_tol,
                                       corner_deg=fill_corner_deg,
                                       smooth_win=fill_smooth,
                                       parsimony=fill_parsimony)
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
