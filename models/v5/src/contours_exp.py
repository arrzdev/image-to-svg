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


_DEBUG: dict = {}    # diagnostic capture (pend snapshot); no pipeline effect


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

    # Stroke candidates: truly dark labels (lum<60) may be colored ink (rabbit
    # navy spread 62), but MID-dark labels (60..dark_lum) must be near-neutral
    # — a saturated mid-dark is a colored GLYPH FILL (pizza letterforms lum~76
    # spread 151, crystals gem fills spread 118-164); stroke-ifying one
    # centerline-loops its sharp corners (run 26 culprit: the "ZZA" squiggles).
    dark = [li for li in range(len(centers))
            if _luminance(centers[li]) < dark_lum
            and (_luminance(centers[li]) < 60
                 or (int(max(centers[li])) - int(min(centers[li]))) <= 45)]

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
            skel, dist = medial_axis(mask, return_distance=True, rng=0)
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
                    skel, dist = medial_axis(mask, return_distance=True, rng=0)
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

        # ---- long-gap chord bridging.  Ends STILL free after bridging and
        # ridge extension can face each other across gaps far beyond those
        # caps (rabbit heart-bottom 3.8w, bag outline 6.7w) where the label
        # map lost a LONG ink run but the SOURCE still shows one continuous
        # dark line.  The ridge walker cannot cross these (measured: it dies
        # on the absolute darkness test over thin antialiased ink, on ridge
        # fails beside shading, or burns its turn budget on staircase jitter
        # within ~5-9 steps).  Bridge instead: a mutually-facing free-end
        # pair (both cos >= 0.3 toward each other — the direction gate that
        # keeps parallel neighbors safe) within 7 widths joins at the chord
        # midpoint IFF the source ink supports the WHOLE chord — sampled as
        # the min over a ±1.5px perpendicular fan (the thin line wanders
        # off the straight chord): mean < 140, >= 60% of samples < 160, and
        # NO bright run over 2px (>176).  Measured on rabbit: every true
        # break has bright-run 0 and mean <= 118; every non-break (light
        # gaps that must stay open) has bright-run >= 7px and mean >= 143.
        # Bridged ends stop being free: no taper, no stub-drop.
        ends2 = []
        for pi, pb in enumerate(pend):
            if pb["closed"] or len(pb["pts"]) < 2:
                continue
            pts = pb["pts"]
            k = min(6, len(pts) - 1)
            for side, e_i, k_i in (("head", 0, k), ("tail", -1, -1 - k)):
                if not pb[side + "_free"]:
                    continue
                t = pts[e_i] - pts[k_i]
                n = np.linalg.norm(t)
                if n > 1e-9:
                    ends2.append((pi, side, pts[e_i].copy(), t / n))
        cand = []
        for i in range(len(ends2)):
            for j in range(i + 1, len(ends2)):
                pi_, _, a, ta = ends2[i]
                pj_, _, b, tb_ = ends2[j]
                if pi_ == pj_:
                    continue
                v = b - a
                dch = float(np.linalg.norm(v))
                if not (1e-6 < dch <= 7.0 * gw):
                    continue
                u = v / dch
                if (float(np.dot(u, ta)) < 0.3
                        or float(np.dot(-u, tb_)) < 0.3):
                    continue
                ns = max(int(dch * 2), 8)
                q = a[None] + v[None] * np.linspace(0, 1, ns)[:, None]
                perp = np.array([-u[1], u[0]])
                vmin = np.full(ns, 255.0)
                for s in (-1.5, -0.75, 0.0, 0.75, 1.5):
                    xs = np.clip((q[:, 0] + perp[0] * s).astype(int),
                                 0, Ws - 1)
                    ys = np.clip((q[:, 1] + perp[1] * s).astype(int),
                                 0, Hs - 1)
                    vmin = np.minimum(vmin, gray[ys, xs])
                if float(vmin.mean()) >= 140.0:
                    continue
                if float((vmin < 160.0).mean()) < 0.6:
                    continue
                run = mx = 0
                for is_br in (vmin > 176.0):
                    run = run + 1 if is_br else 0
                    mx = max(mx, run)
                if mx > 4:          # 2 samples/px: >2px of clear ground
                    continue
                cand.append((dch, i, j))
        cand.sort(key=lambda c: c[0])
        used: set = set()
        for dch, i, j in cand:
            if i in used or j in used:
                continue
            pi_, si, a, _ = ends2[i]
            pj_, sj, b, _ = ends2[j]
            if (not pend[pi_][si + "_free"]
                    or not pend[pj_][sj + "_free"]):
                continue
            mid = (a + b) / 2.0
            for pk, sk in ((pi_, si), (pj_, sj)):
                pbk = pend[pk]
                if sk == "head":
                    pbk["pts"][0] = mid
                    pbk["head_free"] = False
                else:
                    pbk["pts"][-1] = mid
                    pbk["tail_free"] = False
            used.update((i, j))
            info["long_bridges"] = info.get("long_bridges", 0) + 1
            info.setdefault("long_bridge_at", []).append(
                (float(mid[0]), float(mid[1]), float(dch)))

        # ---- arc-aware endpoint bridging (run-17 B).  The free-free chord
        # bridge above cannot close the rabbit heart's top gap: the notch
        # counterpart ends consume each other in the midpoint bridge, so the
        # lobe's still-free end has NO free partner (measured 18/18 runs) —
        # and short curved nicks (head-tuft apex) need a path that TURNS,
        # which a chord can't.  This pass lets a STILL-free end join any
        # other stroke's ENDPOINT (free or not) along a tangent-constrained
        # path: a quadratic arc through the tangent-ray intersection for
        # short strongly-curved gaps, else the straight chord.  Same
        # perpendicular-fan darkness gates as the chord bridge, plus a ridge
        # test (light ground both sides at ±1.1w for ≥50% of samples) so the
        # path must trace a drawn LINE, never a fill edge.  Measured
        # (rabbit + chopchop candidate sweeps, margins in parens):
        #   arcs   — true gaps ≤1.8w, false (frond-V/scribble hooks) ≥4.4w
        #            → reach 2.5w; turn ≤135° (true 105-107°);
        #   chords — true tangent mismatch ≤35° vs false ≥46° → turn ≤40°;
        #            true fan-mean ≤43 vs false ≥51 → mean <50;
        #   ridge2 — true ≥0.58 vs fill-edge runs ≤0.27 → ≥0.5.
        # Chopchop weld landmines under these gates: 0 false fires (all
        # 100+ scribble/fill candidates blocked), 6 solid-ink true joins.
        ends3 = []           # every open-stroke endpoint, free or not
        for pi, pb in enumerate(pend):
            if pb["closed"] or len(pb["pts"]) < 2:
                continue
            pts = pb["pts"]
            k = min(6, len(pts) - 1)
            for side, e_i, k_i in (("head", 0, k), ("tail", -1, -1 - k)):
                t = pts[e_i] - pts[k_i]
                n = np.linalg.norm(t)
                if n > 1e-9:
                    ends3.append((pi, side, pts[e_i].copy(), t / n,
                                  bool(pb[side + "_free"])))

        def _fan_ridge(P, Dn):
            ns = len(P)
            perp = np.stack([-Dn[:, 1], Dn[:, 0]], axis=1)
            vmin = np.full(ns, 255.0)
            for s_ in (-1.5, -0.75, 0.0, 0.75, 1.5):
                xs = np.clip((P[:, 0] + perp[:, 0] * s_).astype(int),
                             0, Ws - 1)
                ys = np.clip((P[:, 1] + perp[:, 1] * s_).astype(int),
                             0, Hs - 1)
                vmin = np.minimum(vmin, gray[ys, xs])
            run_ = mx_ = 0
            for is_br in (vmin > 176.0):
                run_ = run_ + 1 if is_br else 0
                mx_ = max(mx_, run_)
            off = max(1.5, 1.1 * gw)
            clear = np.zeros(ns)
            for sgn in (off, -off):
                xs = np.clip((P[:, 0] + perp[:, 0] * sgn).astype(int),
                             0, Ws - 1)
                ys = np.clip((P[:, 1] + perp[:, 1] * sgn).astype(int),
                             0, Hs - 1)
                clear += (gray[ys, xs] >= dark_lum)
            return (float(vmin.mean()), float((vmin < 160.0).mean()),
                    mx_, float((clear == 2).mean()))

        cand3 = []
        for i, (pi_, si, A, ta, fa) in enumerate(ends3):
            if not fa:
                continue
            for j, (pj_, sj, B, tbv, fb) in enumerate(ends3):
                if pj_ == pi_ or (fb and j <= i):
                    continue        # free-free pairs once; nonfree all
                v = B - A
                dch = float(np.linalg.norm(v))
                if not (1e-6 < dch <= 7.0 * gw):
                    continue
                u = v / dch
                # tangent-ray intersection  A + s·ta = B + r·tb
                det = ta[0] * (-tbv[1]) - (-tbv[0]) * ta[1]
                s_ = r_ = -1.0
                if abs(det) > 1e-9:
                    s_ = (v[0] * (-tbv[1]) - (-tbv[0]) * v[1]) / det
                    r_ = (ta[0] * v[1] - ta[1] * v[0]) / det
                turn_dot = float(np.dot(ta, -tbv))
                P = None
                if (dch <= 2.5 * gw and 1e-6 < s_ <= 2.0 * dch
                        and 1e-6 < r_ <= 2.0 * dch
                        and turn_dot >= -0.7071):        # arc, turn ≤135°
                    X = A + s_ * ta
                    ts_ = np.linspace(0.0, 1.0, 24)[:, None]
                    Pc = (1-ts_)**2 * A + 2*ts_*(1-ts_) * X + ts_**2 * B
                    L = float(np.linalg.norm(np.diff(Pc, axis=0),
                                             axis=1).sum())
                    ns = max(int(L * 2), 8)
                    ts_ = np.linspace(0.0, 1.0, ns)[:, None]
                    P = (1-ts_)**2 * A + 2*ts_*(1-ts_) * X + ts_**2 * B
                    D = 2*(1-ts_) * (X - A) + 2*ts_ * (B - X)
                    Dn = D / (np.linalg.norm(D, axis=1, keepdims=True)
                              + 1e-9)
                    kind, need_mean = "arc", 140.0
                elif (float(np.dot(u, ta)) >= 0.3
                      and float(np.dot(-u, tbv)) >= 0.3
                      and turn_dot >= 0.766):            # chord, turn ≤40°
                    L = dch
                    ns = max(int(dch * 2), 8)
                    P = A[None] + v[None] * np.linspace(0, 1, ns)[:, None]
                    Dn = np.tile(u, (ns, 1))
                    kind, need_mean = "chord", 50.0
                if P is None:
                    continue
                mean_, f160, mx_, ridge2 = _fan_ridge(P, Dn)
                if (mean_ >= need_mean or f160 < 0.6 or mx_ > 4
                        or ridge2 < 0.5):
                    continue
                cand3.append((L, i, j, kind, P))
        cand3.sort(key=lambda c: c[0])
        used_ends: set = set()
        used_tgts: set = set()
        for L, i, j, kind, P in cand3:
            pi_, si, A, ta, fa = ends3[i]
            pj_, sj, B, tbv, fb = ends3[j]
            if i in used_ends or j in used_ends:
                continue
            tkey = (round(float(B[0]) * 2), round(float(B[1]) * 2))
            if tkey in used_tgts:
                continue
            if not pend[pi_][si + "_free"]:
                continue
            if fb and not pend[pj_][sj + "_free"]:
                continue

            def _append(pk, sk, ext):
                pbk = pend[pk]
                if len(ext) == 0:
                    return
                wext = np.full(len(ext), pbk["widths"][
                    0 if sk == "head" else -1], float)
                jext = np.full(len(ext), 1e9)
                if sk == "head":
                    pbk["pts"] = np.vstack([ext[::-1], pbk["pts"]])
                    pbk["widths"] = np.r_[wext, pbk["widths"]]
                    pbk["junc_d"] = np.r_[jext, pbk["junc_d"]]
                    pbk["head_free"] = False
                else:
                    pbk["pts"] = np.vstack([pbk["pts"], ext])
                    pbk["widths"] = np.r_[pbk["widths"], wext]
                    pbk["junc_d"] = np.r_[pbk["junc_d"], jext]
                    pbk["tail_free"] = False
            step = max(len(P) // max(int(L), 1), 1)      # ~1px spacing

            def _sub(Q):                 # subsample, always keep the last
                if len(Q) <= 1 or step == 1:
                    return Q
                R = Q[::step]
                if not np.array_equal(R[-1], Q[-1]):
                    R = np.vstack([R, Q[-1:]])
                return R
            if fb:                       # free-free: meet at path midpoint
                h = len(P) // 2
                _append(pi_, si, _sub(P[1:h + 1]))       # A outward to mid
                _append(pj_, sj, _sub(P[h:-1][::-1]))    # B outward to mid
                used_ends.update((i, j))
            else:                        # join onto the existing endpoint
                _append(pi_, si, _sub(P[1:]))
                used_ends.add(i)
            used_tgts.add(tkey)
            info["arc_bridges"] = info.get("arc_bridges", 0) + 1
            info.setdefault("arc_bridge_at", []).append(
                (float((A[0] + B[0]) / 2), float((A[1] + B[1]) / 2),
                 float(L), kind))

    _DEBUG.clear()
    _DEBUG.update({"pend": pend, "gw": gw})

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


# ------------------------------------------------------- light-line capsules

def _trace_skeleton_path(skel: np.ndarray) -> Optional[np.ndarray]:
    """Longest path through a thin skeleton, as (x,y) pixel centers.

    Double-BFS over the 8-connected skeleton graph (farthest node from an
    arbitrary start, then farthest from that) — exact on trees, and thin
    light scratches skeletonize to near-trees. Side twigs are dropped."""
    from collections import deque

    ys, xs = np.nonzero(skel)
    if len(ys) < 3:
        return None
    pts = set(zip(ys.tolist(), xs.tolist()))
    nbrs = {p: [(p[0] + dy, p[1] + dx)
                for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                if (dy or dx) and (p[0] + dy, p[1] + dx) in pts]
            for p in pts}

    def farthest(start):
        seen = {start: None}
        q = deque([start])
        last = start
        while q:
            p = q.popleft()
            last = p
            for nb in nbrs[p]:
                if nb not in seen:
                    seen[nb] = p
                    q.append(nb)
        return last, seen

    a, _ = farthest(next(iter(pts)))
    b, seen = farthest(a)
    path = [b]
    while seen[path[-1]] is not None:
        path.append(seen[path[-1]])
    if len(path) < 3:
        return None
    return np.array([(x + 0.5, y + 0.5) for y, x in path], float)


def _extend_into_light(path: np.ndarray, src: np.ndarray, lum: np.ndarray,
                       bg: int, max_ext: float = 8.0,
                       cone: float = 0.5) -> np.ndarray:
    """Prolong each path end to the nearest remaining light-LABEL pixel in a
    forward cone, so a capsule's round cap tucks INTO the light shape the
    line emerges from (mouth-corner swoosh, background) instead of stopping
    with a visible gap where the tophat/label cut amputated the junction."""
    h, w = src.shape
    out = path
    for end in (0, -1):
        p = out[end]
        q = out[3 if end == 0 else -4] if len(out) >= 4 else \
            out[1 if end == 0 else -2]
        t = p - q
        n = float(np.hypot(*t))
        if n < 1e-6:
            continue
        t = t / n
        r = int(max_ext) + 1
        x0, x1 = max(int(p[0]) - r, 0), min(int(p[0]) + r + 1, w)
        y0, y1 = max(int(p[1]) - r, 0), min(int(p[1]) + r + 1, h)
        win = lum[src[y0:y1, x0:x1]] > lum[bg] + 50.0
        yy, xx = np.nonzero(win)
        if len(yy) == 0:
            continue
        d = np.stack([xx + x0 + 0.5 - p[0], yy + y0 + 0.5 - p[1]], 1)
        dist = np.hypot(d[:, 0], d[:, 1])
        fwd = (d @ t) >= np.maximum(dist * cone, 1e-6)
        good = (dist <= max_ext) & (dist >= 1.0) & fwd
        if not good.any():
            continue
        i = int(np.argmin(np.where(good, dist, np.inf)))
        tgt = p + d[i] * (1.0 + 1.5 / max(dist[i], 1e-6))   # ~1.5px inside
        out = np.vstack([[tgt], out]) if end == 0 else np.vstack([out, [tgt]])
    return out


def _light_line_capsules(labels: np.ndarray, centers: np.ndarray,
                         src_img: np.ndarray,
                         tophat_thresh: float = 60.0,
                         min_area: int = 40,
                         max_med_w: float = 3.5,
                         min_skel_px: int = 30,
                         min_elong: float = 8.0,
                         min_contrast: float = 60.0,
                         min_fragments: int = 3,
                         whole_min_skel: int = 20,
                         whole_cv: float = 0.2,
                         whole_wm: float = 1.45,
                         sliver_reach: float = 6.0,
                         ) -> Tuple[np.ndarray, List[dict]]:
    """Rescue thin light lines that the label map renders as beads or lumps.

    A ~1-2px light line inside a dark region (monster's white scratch)
    survives quantization either as a DASHED run of small light components
    (the fill fitter rounds each dash into a teardrop bead) or as one
    WHOLE-carried thin sliver — often a tentacle appendage of a big light
    region (the white background) — which the fitter renders lumpy/wobbly.
    The source image still carries the line cleanly, so: white-tophat the
    source, keep components that are thin + elongated + light-on-dark, and
    take them from the fill fitter in two cases:

    - FRAGMENTED (>= min_fragments bead components): always — the dash trail
      can never render as a line.
    - CARRIED WHOLE (< min_fragments): ONLY when the label-map ink under the
      line is itself line-like but width-wavy, i.e. the fitter will lump it:
      width variation along the bead skeleton cv >= whole_cv AND mean bead
      width <= whole_wm * the tophat line width. The width-ratio cap keeps
      thin TIPS of larger light shapes (eye-wedge tails, background wedges
      between limbs, wide highlights) with the fill fitter — stealing those
      would redraw a shape tip as a fat-capped stroke. A clean-carried line
      (low cv, e.g. a long straight scratch the fitter fits well) is left
      alone too. This branch admits slightly shorter lines
      (skel >= whole_min_skel) than the dashed one.

    Reassigned pixels go to the surrounding dark label and ONE continuous
    stroke capsule is emitted along the source centerline instead.

    Returns (patched_labels, capsule_strokes); labels is copied before any
    patch, capsule strokes are {"d","width","color","kind":"stroke"}.
    """
    import cv2
    from skimage.morphology import medial_axis

    gray = src_img.astype(np.float32).mean(2)
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    opened = cv2.morphologyEx(gray.astype(np.uint8), cv2.MORPH_OPEN, kern)
    cand = (gray - opened) > tophat_thresh
    comp, n = ndimage.label(cand, structure=_STRUCT8)
    if n == 0:
        return labels, []

    lum = centers.astype(np.float64).mean(1)
    patched = None
    capsules: List[dict] = []
    for ci in range(1, n + 1):
        m = comp == ci
        area = int(m.sum())
        if area < min_area:
            continue
        skel, dist = medial_axis(m, return_distance=True, rng=0)
        skel_px = int(skel.sum())
        med_w = float(np.median(dist[m]) * 2.0)
        if med_w > max_med_w or skel_px < min(min_skel_px, whole_min_skel):
            continue
        if skel_px / max(med_w, 1.0) < min_elong:
            continue
        dil = ndimage.binary_dilation(m, structure=_STRUCT8, iterations=2)
        ring = dil & ~m
        src = labels if patched is None else patched
        bg = int(np.bincount(src[ring].ravel(),
                             minlength=len(centers)).argmax())
        line_lum = float(np.median(gray[m]))
        if line_lum - lum[bg] < min_contrast:
            continue                       # not light-on-dark
        # -- label-map evidence: light labels overlapping the line
        under = src[m]
        light_ids = [li for li in np.unique(under)
                     if lum[li] > lum[bg] + 50.0]
        beads = np.isin(src, light_ids) & dil if light_ids else \
            np.zeros_like(m)
        _, nfrag = ndimage.label(beads, structure=_STRUCT8)
        if nfrag >= min_fragments:
            if skel_px < min_skel_px:
                continue                   # dashed path keeps the 30px floor
        else:
            # -- carried whole (or absent): steal ONLY lumpy-rendering slivers
            if skel_px < whole_min_skel:
                continue
            if float(beads[m].sum()) / area < 0.5:
                continue                   # label barely carries it: leave
            bskel, bdist = medial_axis(beads, return_distance=True, rng=0)
            if bskel.sum() < 5:
                continue
            rr = bdist[bskel]
            if float(rr.std() / max(rr.mean(), 1e-6)) < whole_cv:
                continue                   # constant width: fitter is fine
            if float(rr.mean() * 2.0) / max(med_w, 2.0) > whole_wm:
                continue                   # fat tip of a bigger light shape
        # -- absorb the bead pixels into the surrounding dark label.
        if patched is None:
            patched = labels.copy()
            src = patched
        if nfrag >= min_fragments:
            # Whole-component test keeps the big light region the line runs
            # into safe: only small components mostly inside the line get
            # eaten.
            for li in light_ids:
                lcomp, ln = ndimage.label(src == li, structure=_STRUCT8)
                for lci in np.unique(lcomp[beads]):
                    if lci == 0:
                        continue
                    cm = lcomp == lci
                    ca = int(cm.sum())
                    if ca < 400 and float((cm & dil).sum()) / ca >= 0.6:
                        src[cm] = bg
                        continue
                    # KEPT big region (background / adjoining light shape):
                    # absorb only its corridor-CARRIED sliver — overlap
                    # pixels living deeper than sliver_reach inside the line
                    # corridor, measured as euclidean distance to the
                    # component's out-of-corridor body. The capsule redraws
                    # the line, so a carried sliver is redundant fill; left
                    # in, the fill fitter curls its free tip past the capsule
                    # at a ridge apex (monster nub at (560,690)@1024).
                    # Measured on monster: edge grazes / junction roots sit
                    # at dist <= 5.0; carried slivers mass at 8-53. Roots
                    # (<= sliver_reach) stay, so fill junctions at the line
                    # ends keep their anchor and heal cleanly.
                    ov = cm & dil
                    if not ov.any():
                        continue
                    body = cm & ~dil
                    if not body.any():
                        continue
                    oy, ox = np.nonzero(ov)
                    pad = int(sliver_reach) + 4
                    wy0 = max(oy.min() - pad, 0)
                    wy1 = min(oy.max() + pad + 1, cm.shape[0])
                    wx0 = max(ox.min() - pad, 0)
                    wx1 = min(ox.max() + pad + 1, cm.shape[1])
                    win = np.s_[wy0:wy1, wx0:wx1]
                    d_body = ndimage.distance_transform_edt(~body[win])
                    deep = ov[win] & (d_body > sliver_reach)
                    if deep.any():
                        src[win][deep] = bg
        else:
            # Whole-carried tentacles hang off big regions (the background),
            # so cut just the bead PIXELS near the line — the capsule redraws
            # the line; the donor region's boundary heals straight.
            src[beads] = bg
        # -- one continuous capsule along the source centerline
        path = _trace_skeleton_path(skel)
        if path is None:
            continue
        if nfrag < min_fragments:
            # whole-carried slivers are amputated from the light shape they
            # emerge from by the tophat/label cut — tuck the cap back into it
            path = _extend_into_light(path, src, lum, bg)
        d = _fit_branch(path, 2.5, 75.0, 11, False)
        if not d:
            continue
        if light_ids:
            dom = max(light_ids,
                      key=lambda li: int((under == li).sum()))
            color = tuple(int(v) for v in centers[dom])
        else:
            med_rgb = np.median(src_img[m].reshape(-1, 3), axis=0)
            dom = int(np.argmin(((centers.astype(np.float64) - med_rgb) ** 2
                                 ).sum(1)))
            color = tuple(int(v) for v in centers[dom])
        # flux width: integrated tophat excess / (contrast * length) gives the
        # sub-pixel effective ink width; the thresholded mask itself is fat
        # with antialias skirt (median mask width read 4px on a ~1.5px line).
        excess = np.clip(gray - opened, 0, None)[m].sum()
        contrast = max(line_lum - float(np.median(opened[m])), 1.0)
        width = float(np.clip(excess / (contrast * skel_px), 1.0, 3.0))
        capsules.append({"d": d, "width": width, "color": color,
                         "kind": "stroke"})
    return (patched if patched is not None else labels), capsules


# ------------------------------------------------------------------ emission

def _fill_edge_corners(pts: np.ndarray, k: int = 6,
                       min_turn_deg: float = 80.0,
                       loc_ratio: float = 0.7,
                       closed: bool = False) -> List[int]:
    """Sharp-corner indices on a RAW crack-lattice fill-edge polyline
    (serration V-notches on region boundaries — monster teeth).

    Same idea as _corner_indices (run 10, stroke bands) extended to the fill
    fitter: turning angle between the incoming/outgoing chords of length k,
    measured BEFORE any fitting — the parsimony fitter's polygon+merge passes
    round exactly these small notches into scallops.

    Two-scale LOCALIZATION test separates a true corner from a tight smooth
    arc: at a corner the turning angle survives when the chord halves
    (ratio ~0.8+); on an arc it halves with the chord (~0.5). Measured on
    monster teeth: ang(k=6)=104-117 deg, ang(k=3)=90 -> ratio ~0.83; a
    lattice circle of radius ~8px reads ang(k=6)~86 but ratio ~0.5. Smooth
    big-radius boundaries sit at the staircase noise floor (<=27 deg @k=4).

    closed=True treats pts as a loop (pts[0]==pts[-1]) with wraparound;
    returned indices are into pts[:-1]."""
    p = np.asarray(pts, float)
    if closed:
        p = p[:-1]
    n = len(p)
    if n < (2 * k + 3 if not closed else 3 * k):
        return []

    def turn(q, kk):
        if closed:
            ext = np.vstack([q[-kk:], q, q[:kk]])
            v1 = ext[kk:kk + n] - ext[:n]
            v2 = ext[2 * kk:2 * kk + n] - ext[kk:kk + n]
        else:
            v1 = q[kk:n - kk] - q[:n - 2 * kk]
            v2 = q[2 * kk:] - q[kk:n - kk]
        dot = (v1 * v2).sum(1) / (np.linalg.norm(v1, axis=1)
                                  * np.linalg.norm(v2, axis=1) + 1e-9)
        return np.degrees(np.arccos(np.clip(dot, -1, 1)))

    k2 = max(2, k // 2)
    a_k = turn(p, k)                     # index i -> pts[i(+k if open)]
    a_k2 = turn(p, k2)
    off = 0 if closed else k
    off2 = 0 if closed else k2
    idx: List[int] = []
    order = np.argsort(a_k)[::-1]
    taken = np.zeros(n, bool)
    for i in order:
        if a_k[i] < min_turn_deg:
            break
        j = i + off                      # index into p
        j2 = j - off2                    # index into a_k2
        if not closed and not (0 <= j2 < len(a_k2)):
            continue
        if a_k2[j2 % len(a_k2)] < loc_ratio * a_k[i]:
            continue                     # distributed turning: smooth arc
        lo, hi = j - k, j + k
        if closed:
            win = np.arange(lo, hi + 1) % n
            if taken[win].any():
                continue
            taken[j] = True
        else:
            if taken[max(0, lo):hi + 1].any():
                continue
            taken[j] = True
        idx.append(int(j))
    return sorted(idx)


def _fill_svg_corner_pinned(labels: np.ndarray, centers: np.ndarray,
                            edges, loops_by_region,
                            parsimony: float) -> str:
    """Parsimony fill emission with serration corners pinned as fit
    breakpoints (drop-in for boundary.loops_to_svg_curves, parsimony>0).

    Each edge polyline is split at _fill_edge_corners; every piece is fitted
    independently with svgcore.fit_open_parsimony (endpoints exact), so the
    corner survives as a hard vertex the merge pass cannot round away. A
    closed loop with corners is rotated to start at its first corner first,
    so ALL its corners become pinned endpoints. Edges without corners fit
    byte-identically to the un-pinned path."""
    import svgcore
    import boundary

    fitted = {}
    for i, e in enumerate(edges):
        if boundary._is_border_edge(e):
            fitted[i] = boundary._line_cubics(e["pts"])
            continue
        pts = np.asarray(e["pts"], float)
        closed = bool(len(pts) > 1 and tuple(pts[0]) == tuple(pts[-1]))
        corners = _fill_edge_corners(pts, closed=closed)
        if closed and corners:
            body = pts[:-1]
            r0 = corners[0]
            body = np.roll(body, -r0, axis=0)
            pts = np.vstack([body, body[:1]])
            corners = [c - r0 for c in corners]
        cubics: List[Tuple[float, ...]] = []
        bounds = [0] + [c for c in corners if 0 < c < len(pts) - 1] \
            + [len(pts) - 1]
        for a, b in zip(bounds[:-1], bounds[1:]):
            seg = pts[a:b + 1]
            if len(seg) < 2:
                continue
            flat = [float(v) for xy in seg for v in xy]
            cs = svgcore.fit_open_parsimony(flat, 1.0, parsimony)
            cubics += [tuple(cs[j:j + 8]) for j in range(0, len(cs), 8)]
        fitted[i] = cubics
    svg, _plan = boundary._emit_regions(labels, centers, loops_by_region,
                                        fitted)
    return svg


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
    capsules: List[dict] = []
    src_img = kw.get("src_img")
    if src_img is not None:
        new_labels, capsules = _light_line_capsules(new_labels, centers,
                                                    src_img)
    edges, _ = boundary.build_edges(new_labels)
    loops = boundary.region_loops(edges, len(centers))
    if fill_parsimony > 0:
        # corner-pinned parsimony fills: serration V-notches (monster teeth)
        # survive as hard vertices instead of rounding into scallops
        svg = _fill_svg_corner_pinned(new_labels, centers, edges, loops,
                                      parsimony=fill_parsimony)
    else:
        svg = boundary.loops_to_svg_curves(new_labels, centers, edges, loops,
                                           tol=fill_tol,
                                           corner_deg=fill_corner_deg,
                                           smooth_win=fill_smooth,
                                           parsimony=fill_parsimony)
    if capsules:                     # light accents under the dark line art
        svg = svg.replace("\n</svg>",
                          "\n" + _stroke_elements(capsules) + "\n</svg>")
    if strokes:
        svg = svg.replace("\n</svg>",
                          "\n" + _stroke_elements(strokes) + "\n</svg>")
    info["strokes"] = len(strokes)
    info["light_capsules"] = len(capsules)
    return svg, info


def contour_svg_from_testbed(tb, label_params: Optional[dict] = None,
                             **kw) -> Tuple[str, dict]:
    """Testbed convenience: cached label map in, original-size SVG out."""
    from svgutil import fit_svg_size

    labels, centers = tb.labels(**(label_params or {}))
    svg, info = contour_svg(labels, centers, **kw)
    _, _, (ow, oh), _ = tb.prep()
    return fit_svg_size(svg, ow, oh), info
