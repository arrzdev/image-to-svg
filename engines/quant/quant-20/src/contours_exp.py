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


def _medial_axis_crop(mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """medial_axis(mask, return_distance=True, rng=0) on the component's
    1px-padded bounding box, pasted back full-frame — exactly equal to the
    full-frame call, at a fraction of the cost (profiled hotspot: full-frame
    EDT + corner table + mgrid per component).

    Why byte-identical: skimage's medial_axis orders pixels by (EDT distance,
    corner score, seeded-permutation tiebreak). The EDT and 3x3 corner scores
    of an isolated component only depend on the component plus one background
    pixel of padding; the rng=0 tiebreaker is a permutation of
    arange(mask.sum()) — a function of the foreground COUNT, and foreground
    pixels keep their row-major order under cropping. The thinning loop
    itself only looks at 3x3 neighborhoods, so it is translation-invariant.
    Background stays 0 in both skeleton and distance outputs, exactly as the
    full-frame call returns them."""
    from skimage.morphology import medial_axis

    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return np.zeros(mask.shape, bool), np.zeros(mask.shape, np.float64)
    y0 = max(int(ys.min()) - 1, 0)
    y1 = min(int(ys.max()) + 2, mask.shape[0])
    x0 = max(int(xs.min()) - 1, 0)
    x1 = min(int(xs.max()) + 2, mask.shape[1])
    sk_s, di_s = medial_axis(mask[y0:y1, x0:x1], return_distance=True, rng=0)
    skel = np.zeros(mask.shape, bool)
    skel[y0:y1, x0:x1] = sk_s
    dist = np.zeros(mask.shape, di_s.dtype)
    dist[y0:y1, x0:x1] = di_s
    return skel, dist


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


def _straight_chain_lock(seg: np.ndarray, head_free: bool, tail_free: bool,
                         min_chord: float = 16.0, min_n: int = 12,
                         rms_thr: float = 0.75, max_thr: float = 2.5,
                         bow_thr: float = 0.4,
                         end_dev_cap: float = 5.0) -> Optional[np.ndarray]:
    """RULER-STRAIGHT centerline lock (GAP_LEDGER #2 residual, stroke layer).

    Pizza's checker verticals are dead straight in label space (interior TLS
    rms 0.36-0.40 / max <=1.7 over ~100pt chains) yet render with an S-bow up
    to 2.75px: fit_open's tol=2.5 band lets a long straight outline drift,
    and the eye reads any bow on a ruler line instantly. Mirror of the run-29
    FILL straight-piece prior, applied to the raw stroke chain: if the
    interior (6-pt end windows trimmed — junction anchors and label-noise
    end-dips live there) is TLS-straight AND shows no net arc, project the
    chain onto the line so the fitter cannot bow it.

    The decisive gate is the BOW statistic (mean signed residual of the
    middle third minus the outer thirds = sagitta estimate): staircase noise
    on a true straight is unbiased, a gentle drawn arc is one-signed.
    Population-measured (run it21, 5 targets): every pizza grid line /
    box edge bows <= 0.26 (one short-chain outlier 0.53); the gentlest
    curves that must stay round (rabbit cheek/ear arcs 1.10-1.55, heart
    cord 0.68, chopchop limbs >= 0.52) all sit above 0.5. bow 0.4 splits
    the gap; rms 0.75 / max 2.5 only bound the staircase envelope.

    Ends: a FREE end is projected fully (its 2-4px label-noise dip — the
    'junction-adjacent hook' — is exactly what this kills); an ANCHORED /
    bridged end keeps its exact endpoint (connectivity contract) with the
    correction ramped to zero across the trim window. A free-end window
    deviating more than end_dev_cap from the line is a deliberate curl
    (flick tails measure >= 7px; true hooks <= 4px) — bail, lock nothing."""
    n = len(seg)
    if n < min_n:
        return None
    t = min(6, n // 6)
    interior = seg[t:n - t]
    if len(interior) < 8:
        return None
    c = interior.mean(0)
    _, _, vt = np.linalg.svd(interior - c, full_matrices=False)
    v = vt[0]
    sr = np.cross(v, interior - c)
    resid = np.abs(sr)
    if (float(np.sqrt((resid ** 2).mean())) > rms_thr
            or float(resid.max()) > max_thr):
        return None
    s = (interior - c) @ v
    if float(s.max() - s.min()) < min_chord:
        return None
    order = np.argsort(s)
    so = sr[order]
    k = len(so) // 3
    if k >= 2 and abs(float(so[k:2 * k].mean())
                      - float(np.r_[so[:k], so[2 * k:]].mean())) > bow_thr:
        return None                      # net arc: a drawn curve, keep round
    dev = np.abs(np.cross(v, seg - c))
    if (head_free and float(dev[:t].max(initial=0.0)) > end_dev_cap) or \
            (tail_free and float(dev[n - t:].max(initial=0.0)) > end_dev_cap):
        return None                      # deliberate end curl: keep as-is
    proj = c + ((seg - c) @ v)[:, None] * v
    out = proj.copy()
    if not head_free:                    # pinned end: keep endpoint, ramp
        w = np.linspace(1.0, 0.0, t + 1)[:t, None]
        out[:t] = proj[:t] + (seg[:t] - proj[:t]) * w
    if not tail_free:
        w = np.linspace(0.0, 1.0, t + 1)[1:, None]
        out[n - t:] = proj[n - t:] + (seg[n - t:] - proj[n - t:]) * w
    return out


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


def _junction_cusp_exts(branches: List[dict], cent: dict, mask: np.ndarray,
                        med_w: float, width_scale: float,
                        debug: Optional[list] = None) -> dict:
    """Concave-cusp descent targets at skeleton junctions (GAP_LEDGER #4).

    The rabbit heart's notch is a downward INK WEDGE between the two lobes:
    the lobes' outline ink and the cord ink merge, the medial-axis junction
    sits at the TOP of the wedge, and the wedge's descending tip has no
    skeleton branch (pruned/never formed). Rendered, no stroke descends into
    the V — the notch reads shallow (run 25 residual).

    Detection: rasterize the component's branch centerlines, take the ink
    pixels FARTHER from every centerline than the rendered stroke half-width
    (cover_r = med_w*width_scale/2 + 0.75 — what the emitted strokes will
    actually paint), and keep connected pockets that (a) touch a junction
    node and (b) run DEEP: max centerline distance >= cover_r + 0.45*med_w
    and tip at least 1.0*med_w from the node. Junction ink POOLING also
    leaves thin uncovered crescents, but they hug the centerlines (measured
    populations, run it21: pools' depth-beyond-cover <= 0.30*med_w; true
    cusp wedges >= 0.75*med_w) — the depth gate separates them.

    The wedge is then drawn by extending the ONE incident branch whose end
    tangent best continues toward the wedge tip (dot >= 0.3): a straight
    chain of pixels from the branch end to the tip, appended after junction
    anchoring. Returns {(branch_index, end_index): chain_yx float array}."""
    if not branches or len(cent) <= 1:
        return {}
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return {}
    m = 3
    y0, y1 = max(int(ys.min()) - m, 0), min(int(ys.max()) + m + 1,
                                            mask.shape[0])
    x0, x1 = max(int(xs.min()) - m, 0), min(int(xs.max()) + m + 1,
                                            mask.shape[1])
    sub = mask[y0:y1, x0:x1]
    brmask = np.zeros(sub.shape, bool)
    for br in branches:
        pix = np.asarray(br["pix"], int)
        brmask[np.clip(pix[:, 0] - y0, 0, sub.shape[0] - 1),
               np.clip(pix[:, 1] - x0, 0, sub.shape[1] - 1)] = True
    if not brmask.any():
        return {}
    dbr = ndimage.distance_transform_edt(~brmask)
    cover_r = 0.5 * med_w * width_scale + 0.75
    uncov = sub & (dbr > cover_r)
    if not uncov.any():
        return {}
    pk, npk = ndimage.label(uncov, structure=_STRUCT8)
    # pocket pixel coords + depth are node-independent: compute ONCE (the
    # per-node argwhere(pk == p) rescan was a profiled hotspot). The grouped
    # coords are the exact row-major arrays argwhere produced.
    pk_coords = np.argwhere(pk > 0)
    pk_vals = (pk[pk_coords[:, 0], pk_coords[:, 1]]
               if len(pk_coords) else np.empty(0, pk.dtype))
    pockets: dict = {}
    for p in range(1, npk + 1):
        pyx = pk_coords[pk_vals == p]
        if len(pyx) >= 6:
            pockets[p] = (pyx, float(dbr[tuple(pyx.T)].max()) - cover_r)
    exts: dict = {}
    used_pockets: set = set()
    for nid, cyx in cent.items():
        if not nid or cyx is None:
            continue
        node = np.asarray(cyx, float) - (y0, x0)
        if not (0 <= node[0] < sub.shape[0] and 0 <= node[1] < sub.shape[1]):
            continue
        best_pocket = None
        for p in range(1, npk + 1):
            if p in used_pockets:
                continue
            if p not in pockets:
                continue
            pyx, depth = pockets[p]
            dnode = np.hypot(pyx[:, 0] - node[0], pyx[:, 1] - node[1])
            if float(dnode.min()) > 1.2 * med_w:
                continue                          # not this node's pocket
            extent = float(dnode.max())
            if debug is not None:
                tp = pyx[int(np.argmax(dnode))] + (y0, x0)
                debug.append({"node": (float(cyx[0]), float(cyx[1])),
                              "area": int(len(pyx)),
                              "depth_bc": depth, "depth_bc_w": depth / med_w,
                              "extent_w": extent / med_w,
                              "tip": (int(tp[0]), int(tp[1]))})
            # wedge gates (population-measured, run it21, 5 targets):
            # a true concave-cusp wedge is SMALL and just-beyond-cover
            # (heart notch: depth_bc 0.64w, extent 1.19w, area 10). The
            # false pockets are glyph/fill ink masses near junctions and
            # run DEEP and LARGE (depth_bc >= 1.75w, extent >= 2.36w,
            # area >= 25) — ceiling gates, with the floor separating
            # junction-pool crescents (depth_bc <= 0.30w).
            if not (0.45 * med_w <= depth <= 1.2 * med_w
                    and 1.0 * med_w <= extent <= 2.0 * med_w
                    and len(pyx) <= 24):
                continue
            if best_pocket is None or depth > best_pocket[0]:
                tip = pyx[int(np.argmax(dnode))].astype(float)
                best_pocket = (depth, p, tip)
        if best_pocket is None:
            continue
        _, p, tip = best_pocket
        tip_g = tip + (y0, x0)
        u = tip - node
        nu = float(np.hypot(*u))
        if nu < 1e-6:
            continue
        u = u / nu
        best_end = None
        for bi, br in enumerate(branches):
            if br["closed"]:
                continue
            pix = np.asarray(br["pix"], float)
            if len(pix) < 4:
                continue
            k = min(6, len(pix) - 1)
            for end, e_nid, kk in ((0, br["a"], k), (-1, br["b"], -1 - k)):
                if e_nid != nid:
                    continue
                t = pix[end] - pix[kk]
                nt = float(np.hypot(*t))
                if nt < 1e-6:
                    continue
                dot = float(np.dot(t / nt, u))
                if dot >= 0.3 and (best_end is None or dot > best_end[0]):
                    best_end = (dot, bi, end)
        if best_end is None:
            if debug is not None:
                debug.append({"node": (float(cyx[0]), float(cyx[1])),
                              "skipped": "no aligned branch end"})
            continue
        _, bi, end = best_end
        start = np.asarray(branches[bi]["pix"][end], float)
        L = float(np.hypot(*(tip_g - start)))
        if L > 2.5 * med_w:
            continue                      # a cusp descent is short by nature
        nseg = max(int(np.ceil(L)), 2)
        chain = start[None] + (tip_g - start)[None] * \
            np.linspace(0.0, 1.0, nseg + 1)[1:, None]
        # ink support: the descent must run THROUGH source ink, never air
        ci = np.clip(chain.astype(int), (0, 0),
                     (mask.shape[0] - 1, mask.shape[1] - 1))
        if float(mask[ci[:, 0], ci[:, 1]].mean()) < 0.9:
            continue
        if debug is not None:
            debug.append({"node": (float(cyx[0]), float(cyx[1])),
                          "fired_tip": (float(tip_g[0]), float(tip_g[1])),
                          "dot": best_end[0]})
        exts[(bi, end)] = chain
        used_pockets.add(p)
    return exts


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

def _join_color_ok(ca, cb) -> bool:
    """Color-guarded joining (GAP_LEDGER #5, USER idea): two stroke ends may
    weld only when their source label colors agree — a join whose color
    BREAKS is connecting two DIFFERENT drawn lines (smile end onto a teal
    lens stroke, ink outline onto a mauve shadow stroke) and must not fire.

    Measured populations (chopchop + fox + rabbit + crystals, run it21-B):
    every eye-good join is label-identical (RGB distance 0 — the ΔE-12
    palette merge already collapsed same-ink twins); every eye-confirmed
    over-join pairs distinct families (distance 51-125: black↔brown 51,
    teal↔black 89, ink↔purple 74, dark↔gray 105, ink↔mauve 125).
    Threshold 30 sits between with wide margin while still allowing
    near-twin dark labels (ΔE just above the merge) to weld."""
    return (float(ca[0] - cb[0]) ** 2 + float(ca[1] - cb[1]) ** 2
            + float(ca[2] - cb[2]) ** 2) <= 30.0 ** 2


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
    _DEBUG.pop("cusp", None)      # fresh diagnostics per call

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
        # (nid, window_slice, mask_in_window) — bbox-local masks; operating
        # on full-image masks per component (and dilating them full-frame)
        # was the profiled hotspot, with identical results.
        small: List[Tuple[int, tuple, np.ndarray]] = []
        Hl, Wl = labels.shape
        nid = 1
        for li in dark:
            lm = labels == li
            if not lm.any():
                continue
            comp, n = ndimage.label(lm, structure=_STRUCT8)
            objs = ndimage.find_objects(comp)
            for ci in range(1, n + 1):
                sl = objs[ci - 1]
                m_sub = comp[sl] == ci
                a = int(m_sub.sum())
                comp_id[sl][m_sub] = nid
                comp_label[nid] = li
                comp_area[nid] = a
                if a < 250:
                    # pad the bbox by 1 so the 8-dilated border fits inside
                    y0 = max(sl[0].start - 1, 0)
                    y1 = min(sl[0].stop + 1, Hl)
                    x0 = max(sl[1].start - 1, 0)
                    x1 = min(sl[1].stop + 1, Wl)
                    mw = np.zeros((y1 - y0, x1 - x0), bool)
                    mw[sl[0].start - y0:sl[0].stop - y0,
                       sl[1].start - x0:sl[1].stop - x0] = m_sub
                    small.append((nid, np.s_[y0:y1, x0:x1], mw))
                nid += 1
        for cid, win, mw in small:
            a = comp_area[cid]
            border = ndimage.binary_dilation(mw, structure=_STRUCT8) & ~mw
            best = None
            for ncid in np.unique(comp_id[win][border]):
                ncid = int(ncid)
                if ncid == 0 or ncid == cid:
                    continue
                if comp_label[ncid] == comp_label[cid]:
                    continue
                if comp_area[ncid] >= 10 * a:
                    if best is None or comp_area[ncid] > comp_area[best]:
                        best = ncid
            if best is not None:
                labels[win][mw] = comp_label[best]
                flecks_absorbed += 1

    stroke_mask = np.zeros(labels.shape, bool)
    skel_union = np.zeros(labels.shape, bool)   # it75: pen-coverage proxy
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
        objs = ndimage.find_objects(comp)
        color = tuple(int(v) for v in centers[li])
        for ci in range(1, n + 1):
            mask = comp == ci
            area = int(mask.sum())
            if area < min_area:
                continue
            # padded component window: every in-component computation below
            # (EDTs, junction maps) reads only inside it, so cropping to it
            # is exact — full-frame transforms per component were profiled
            # hotspots.
            _sl = objs[ci - 1]
            msl = np.s_[max(_sl[0].start - 1, 0):
                        min(_sl[0].stop + 1, labels.shape[0]),
                        max(_sl[1].start - 1, 0):
                        min(_sl[1].stop + 1, labels.shape[1])]
            skel, dist = _medial_axis_crop(mask)
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
                    ~skel[msl], return_indices=True)
                blob_mask = np.zeros(mask.shape, bool)
                blob_mask[msl] = mask[msl] & blob_skel[msl][iy, ix]
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
                    skel, dist = _medial_axis_crop(mask)
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
                    on = brid[msl] > 0
                    _, (iy2, ix2) = ndimage.distance_transform_edt(
                        ~on, return_indices=True)
                    drop_px = np.zeros(mask.shape, bool)
                    drop_px[msl] = mask[msl] & (brid[msl][iy2, ix2] == 2)
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
            # (single nonzero pass, then group — a full-image argwhere per
            # nid was a profiled hotspot; coords[vals == nid] is the exact
            # same row-major coordinate array argwhere produced)
            cent = {0: None}
            nl_coords = np.argwhere(node_lbl > 0)
            nl_vals = (node_lbl[nl_coords[:, 0], nl_coords[:, 1]]
                       if len(nl_coords) else np.empty(0, node_lbl.dtype))
            for nid in range(1, int(node_lbl.max()) + 1):
                yx = nl_coords[nl_vals == nid]
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
            # jdist is only ever read at in-component pixels (branch chains,
            # cusp chains), all inside the padded window, and every junction
            # pixel lives there too — the window EDT is exact at those reads.
            # Outside the window 1e9 stands in for "far from any junction".
            jdist = None
            if jnm.any():
                jdist = np.full(mask.shape, 1e9)
                jdist[msl] = ndimage.distance_transform_edt(~jnm[msl])
            # anchor target per node: the node-cluster centroid is elongated by
            # junction ink pooling, so it can sit OFF the through-line's
            # centerline — a side branch capped there pokes a nub through the
            # through stroke (visible on the silhouette). Anchor instead to the
            # nearest pixel of ANOTHER incident branch's path near the node:
            # the cap then lands flush under the through stroke by construction
            # (all strokes share w_body). Falls back to the centroid when no
            # other branch passes nearby (true endpoint clusters).
            med_w_a = float(np.median(dist[skel] * 2.0))
            # concave-cusp ink-wedge descent (GAP_LEDGER #4): junction-
            # adjacent ink pockets deeper than what the emitted strokes
            # cover get ONE branch extended into their tip (heart notch V).
            cusp_exts = ({} if is_band else _junction_cusp_exts(
                branches, cent, mask, med_w_a, width_scale,
                debug=_DEBUG.setdefault("cusp", [])))
            for bi, br in enumerate(branches):
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
                # apply cusp-wedge extensions AFTER anchoring (the anchor
                # snap only moves the end point; the wedge chain continues
                # beyond it into the uncovered ink tip). Junction ends stay
                # non-free, so no taper/bridge logic sees the new tail.
                for end, key in ((0, (bi, 0)), (-1, (bi, -1))):
                    chain = cusp_exts.get(key)
                    if chain is None:
                        continue
                    ci = np.clip(chain.astype(int),
                                 (0, 0), (dist.shape[0] - 1,
                                          dist.shape[1] - 1))
                    cw = dist[ci[:, 0], ci[:, 1]] * 2.0
                    cj = (jdist[ci[:, 0], ci[:, 1]] if jdist is not None
                          else np.full(len(chain), 1e9))
                    if end == 0:
                        pix = np.vstack([chain[::-1], pix])
                        widths = np.r_[cw[::-1], widths]
                        junc_d = np.r_[cj[::-1], junc_d]
                    else:
                        pix = np.vstack([pix, chain])
                        widths = np.r_[widths, cw]
                        junc_d = np.r_[junc_d, cj]
                    info["cusp_exts"] = info.get("cusp_exts", 0) + 1
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
            skel_union |= skel
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
    # ---- it75 source-anchored pen calibration (COLOR family, run 75).
    # DIAGNOSIS (research/it75): on ink-heavy stems the emitted pen
    # (w_body = 0.85 * gw) systematically under-covers the source's own
    # dark-ink footprint — chopchop missed 12.3% of the source's dark px
    # (Recraft: 2.4%) as a 1-3px "fringe" along every stroke, and tilecmp
    # charges the lightened tile means as COLOR error (excess 0.2247).
    # The 0.85 default was eye-tuned against Recraft's ELEPHANT in the v4
    # era — and elephant no longer routes ANY ink through the stroke
    # system (it72 verified), so the calibration target is gone.
    # MECHANISM: measure the source's ink mass over the stroke-owned
    # region (per dark label: its kept components' mask px + their 1px
    # ring owned by light labels, counted at that label's own darkness
    # threshold) and, where the planned pen demonstrably under-covers it,
    # emit at the source-mass width gw_src instead of 0.85*gw.
    # FIRE GATE (population-measured, research/it75 table): the two stems
    # widening provably hurts (pizza-box: close parallel pairs pinch shut,
    # eye-verified; rabbit: pen already spills, extra 23.7% > miss) are
    # exactly the stems with NO fringe deficit and huge overhang — three
    # independent guards with margins hold them out.
    it75_eff = width_scale        # effective emission scale (unfired: as-is)
    if src_img is not None and pend:
        _g = (src_img.astype(np.float32) @ np.array([0.299, 0.587, 0.114],
                                                    np.float32)
              if src_img.ndim == 3 else src_img.astype(np.float32))
        _lut = np.array([_luminance(c) for c in centers], np.float32)
        _light_owner = _lut[labels] >= dark_lum
        # source-ink mass per dark label at the label's own threshold
        # (lum+24, clipped to [80,110]): a mid-dark label (fox 95, shield
        # 95) needs a higher cut for its own soft core, but must not drag
        # tan shading into a BLACK network's count (global-T landmine:
        # shield's global T=110 inflated R to 1.20).
        darkS = np.zeros(labels.shape, bool)
        for li in dark:
            lm = (labels == li) & stroke_mask
            if not lm.any():
                continue
            T_li = float(np.clip(_lut[li] + 24.0, 80.0, 110.0))
            ring = (ndimage.binary_dilation(lm, structure=_STRUCT8)
                    & ~stroke_mask & _light_owner)
            darkS |= (lm | ring) & (_g < T_li)
        src_mass = int(darkS.sum())
        gw_src = src_mass / max(tot_skel, 1)
        # planned-pen coverage proxy: distance from the skeleton union
        D = ndimage.distance_transform_edt(~skel_union)
        r0 = 0.5 * gw * width_scale
        cov = D <= r0 + 0.5
        nearmiss = int((darkS & ~cov & (D <= r0 + 3.0)).sum())
        region3 = ndimage.binary_dilation(stroke_mask, structure=_STRUCT8,
                                          iterations=3)
        # overhang: planned-pen px that are decisively NOT ink in the
        # source (luma > 125 = the darkest per-label cut + 45). A pen that
        # already spills must never be widened.
        overhang = int((cov & region3 & (_g > 125.0)).sum())
        nm_area = nearmiss / max(tot_area, 1)
        ovh_area = overhang / max(tot_area, 1)
        # fire iff (population table, research/it75, 8 stroke stems):
        #  * the fringe deficit is substantial — nm_area >= 0.033
        #    (must-not-fire pizza 0.0126 / rabbit 0.0103 sit 2.6x/3.2x
        #    BELOW; the firing cohort's min, shield 0.0497, is 1.5x above);
        #  * the pen does not already spill — ovh_area <= 0.19 (pizza
        #    0.274 / rabbit 0.415 sit 1.44x/2.2x ABOVE; firing max
        #    crystals 0.159);
        #  * the network is statistically real — tot_area >= 2000 px
        #    (app-asset 346, a 46px-fringe fleck, 5.8x below; firing min
        #    mountain 4381, 2.2x above).
        # Fired scale: the source-mass width, never below the shipped
        # default and never beyond the mask evidence — fired cohort today
        # lands at cal 0.927..0.969 (chopchop 0.950, crystals 0.946, fox
        # 0.927, mountain 0.965, shield 0.969), inside the corpus band
        # measured at width_scale 0.90/0.95 (all channels clean).
        if (nm_area >= 0.033 and ovh_area <= 0.19 and tot_area >= 2000
                and gw > 0):
            it75_eff = float(np.clip(gw_src / gw, width_scale, 1.0))
        info["it75_stats"] = {"gw_src": round(gw_src, 3),
                              "nm_area": round(nm_area, 4),
                              "ovh_area": round(ovh_area, 4),
                              "tot_area": int(tot_area),
                              "cal": round(it75_eff, 4)}
        import os as _os
        if _os.environ.get("IT75_CALIB"):
            import json as _json, sys as _sys
            print("IT75_CALIB " + _json.dumps(info["it75_stats"]),
                  file=_sys.stderr)
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
                # color guard: never weld onto a differently-colored line
                if not _join_color_ok(pend[pi]["color"], ob["color"]):
                    info.setdefault("color_blocked", []).append(
                        ("snap", float(ob["pts"][j][0]),
                         float(ob["pts"][j][1]),
                         pend[pi]["color"], ob["color"]))
                    continue
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
        info.setdefault("join_events", []).append(
            ("snap", float(target[0]), float(target[1]),
             pend[pi]["color"], pend[best[1]]["color"]))

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
                            # color guard (GAP_LEDGER #5)
                            if not _join_color_ok(pb["color"], ob["color"]):
                                info.setdefault("color_blocked", []).append(
                                    ("ink", float(ob["pts"][j][0]),
                                     float(ob["pts"][j][1]),
                                     pb["color"], ob["color"]))
                                continue
                            snapped = ob["pts"][j].copy()
                            snapped_pj = pj
                            break
                    if snapped is not None:
                        break
                if not trail:
                    continue
                if snapped is not None:
                    trail.append(snapped)
                    info.setdefault("join_events", []).append(
                        ("ink", float(snapped[0]), float(snapped[1]),
                         pb["color"], pend[snapped_pj]["color"]))
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
                # color guard (GAP_LEDGER #5): the ink gates test darkness,
                # not identity — a chord from an ink line to a mauve shadow
                # stroke passes them; the color break says two different
                # drawn lines.
                if not _join_color_ok(pend[pi_]["color"], pend[pj_]["color"]):
                    info.setdefault("color_blocked", []).append(
                        ("chord", float((a[0] + b[0]) / 2),
                         float((a[1] + b[1]) / 2),
                         pend[pi_]["color"], pend[pj_]["color"]))
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
            info.setdefault("join_events", []).append(
                ("chord", float(mid[0]), float(mid[1]),
                 pend[pi_]["color"], pend[pj_]["color"]))

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
                # color guard (GAP_LEDGER #5)
                if not _join_color_ok(pend[pi_]["color"], pend[pj_]["color"]):
                    info.setdefault("color_blocked", []).append(
                        (kind, float((A[0] + B[0]) / 2),
                         float((A[1] + B[1]) / 2),
                         pend[pi_]["color"], pend[pj_]["color"]))
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
            info.setdefault("join_events", []).append(
                (kind, float((A[0] + B[0]) / 2), float((A[1] + B[1]) / 2),
                 pend[pi_]["color"], pend[pj_]["color"]))

    cusp_dbg = _DEBUG.get("cusp", [])
    _DEBUG.clear()
    _DEBUG.update({"pend": pend, "gw": gw, "cusp": cusp_dbg})

    for pb in pend:
        base = gw if width_mode == "global" else pb["w_med"]
        # it75: fired source-anchored calibration re-levels the pen; the
        # stub-drop below stays on the UNCALIBRATED width so WHICH chains
        # ship is untouched by calibration (debris policy != pen width).
        w_stub = max(base * width_scale, 0.75)
        w_body = max(base * it75_eff, 0.75)
        seg, segw = pb["pts"], np.asarray(pb["widths"], float)
        # drop floating stubs: an isolated snippet shorter than ~1.5 widths
        # renders as a lone dot (label-map break debris), worse than nothing
        if (pb["head_free"] and pb["tail_free"]
                and len(seg) < stub_factor * w_stub):
            continue
        # ---- straight-chain lock: TLS-straight raw chains render as exact
        # lines (fit-tol bows + end-dips erased; swell suppressed below —
        # a drawn ruler line is uniform weight, its mid-span EDT bulges are
        # crossing-ink artifacts). See _straight_chain_lock.
        locked = False
        if not pb["closed"] and not pb.get("band"):
            seg2 = _straight_chain_lock(seg, pb["head_free"],
                                        pb["tail_free"])
            if seg2 is not None:
                seg = seg2
                locked = True
                info["straight_locks"] = info.get("straight_locks", 0) + 1
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
            if not locked and jd is not None and len(jd) == len(swell):
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
            dr = _ribbon(seg, prof * it75_eff / 2.0, stroke_tol,
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
        skel, dist = _medial_axis_crop(m)
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
            bskel, bdist = _medial_axis_crop(beads)
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
        d = _li_capsule_d(path, 2.5, 75.0, 11)
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


# --- Line-intent stage 1 (it24 B-lineintent, GAP_LEDGER 0k / audit24 E4-E5) --
# Populations measured on the live label lattices (diag it24):
#   monster teeth pieces (corner-bounded): chord 5.8-8.6, dmax<=1.41,
#     |mean signed|<=0.58 — the run-29 prior (chord>=20, n>=12) misses ALL;
#   true ruler runs (wrist hairline, claws, checker): dev<=1.0, |sag|<=0.35
#     (run-35 stroke populations: straights bow <=0.26, gentle curves >=0.5);
#   anchor turns at REAL sub-80deg kinks (crystal facets, ridges, claws):
#     raw k=6 turn >= 26.6; SPURIOUS fitter kinks on smooth raw <= 18.4
#     (monster head flat-cut 11.3, elephant 18.4) — anchor gate 25 splits;
#   G1-repair gate 20 (below the real-kink floor with margin) — the parsimony
#     fitter mints corners at polygon vertices even on smooth raw (head-left
#     kink brk 16.8 @ rawturn 11.3, same at every opttol), so smoothness is
#     decided from the RASTER polyline, never from the fit.
_LI_ANCHOR_DEG = 25.0    # raw k-chord turn that marks a drawing-intent kink
_LI_G1_RAW_DEG = 20.0    # raw turn below which a fitted kink is spurious
_LI_G1_BRK_MAX = 45.0    # never G1-repair breaks larger than this
_LI_SHORT_CHORD = 4.0    # corner-bounded short-piece prior (teeth)
_LI_SHORT_DMAX = 1.6     # teeth measured <=1.41
_LI_SHORT_SAG = 0.65     # teeth measured <=0.58; R~5 rounded arcs >=0.8
_LI_SHORT_MAX_CHORD = 12.0   # above this the tight long-span caps apply
_LI_SPAN_DEV = 1.1       # anchored long span (hand-top 1.01, knuckle 1.07;
_LI_SPAN_SAG = 0.35      #  rabbit cheek pieces 1.18+ stay out)
_LI_CORR_THIN = 3.0      # neighbor-region local thickness = drawn hairline
_LI_CORR_DEV = 1.8       # corridor spans: wrist 1.42/0.50 + 1.41/0.48 in;
_LI_CORR_SAG = 0.85      #  chopchop curved corridor 3.37/2.23, rabbit
                         #  outline 2.95/1.37, monster eye tip 1.94/0.91 out
_LI_CAP_DEV = 1.35       # capsule skeleton spans (8-connected, noisier):
_LI_CAP_SAG = 0.6        #  wrist hairline 0.99-1.06/<=0.54 + body lines
_LI_CAP_CHORD = 8.0      #  1.19-1.22/<=0.56 in; curved seams >=1.7 out


def _li_raw_turn(seg: np.ndarray, idx: int, k: int = 6) -> float:
    """Turn angle (deg) at seg[idx] between k-chords before/after."""
    n = len(seg)
    i0, i1 = max(0, idx - k), min(n - 1, idx + k)
    v1 = seg[idx] - seg[i0]
    v2 = seg[i1] - seg[idx]
    n1, n2 = float(np.hypot(*v1)), float(np.hypot(*v2))
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0
    c = float(v1 @ v2) / (n1 * n2)
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))


def _li_run_stats(seg: np.ndarray, i: int, j: int):
    """(chord_len, max|perp|, |mean signed perp|) of seg[i..j] vs its chord."""
    q0, q1 = seg[i], seg[j]
    v = q1 - q0
    L = float(np.hypot(*v))
    if L < 1e-9:
        return L, 1e9, 1e9
    nrm = np.array([-v[1], v[0]]) / L
    d = (seg[i:j + 1] - q0) @ nrm
    return L, float(np.abs(d).max()), float(abs(d.mean()))


def _li_line_cubic(q0, q1) -> Tuple[float, ...]:
    third = (q1 - q0) / 3.0
    p1c = q0 + third
    p2c = q0 + 2 * third
    return (q0[0], q0[1], p1c[0], p1c[1], p2c[0], p2c[1], q1[0], q1[1])


def _li_g1_repair(cubics: List[Tuple[float, ...]],
                  seg: np.ndarray) -> List[Tuple[float, ...]]:
    """Kill fitter-minted kinks on smooth raster: at each interior cubic
    join whose RAW polyline turn is below _LI_G1_RAW_DEG, rotate both
    handles to the bisector tangent (G1). True kinks (raw turn high) and
    piece endpoints are never touched — smoothness is decided from the
    raster, not the fit (audit24: head-left flat-cut, elephant mouth kink)."""
    if len(cubics) < 2:
        return cubics
    out = [list(c) for c in cubics]
    for ci in range(len(out) - 1):
        c1, c2 = out[ci], out[ci + 1]
        t_in = np.array([c1[6] - c1[4], c1[7] - c1[5]])
        t_out = np.array([c2[2] - c2[0], c2[3] - c2[1]])
        if float(np.hypot(*t_in)) < 1e-9:
            t_in = np.array([c1[6] - c1[0], c1[7] - c1[1]])
        if float(np.hypot(*t_out)) < 1e-9:
            t_out = np.array([c2[6] - c2[0], c2[7] - c2[1]])
        n1, n2 = float(np.hypot(*t_in)), float(np.hypot(*t_out))
        if n1 < 1e-9 or n2 < 1e-9:
            continue
        cosb = float(t_in @ t_out) / (n1 * n2)
        brk = float(np.degrees(np.arccos(np.clip(cosb, -1.0, 1.0))))
        if brk < 1.0 or brk > _LI_G1_BRK_MAX:
            continue
        jp = np.array([c1[6], c1[7]])
        idx = int(np.linalg.norm(seg - jp, axis=1).argmin())
        if _li_raw_turn(seg, idx) > _LI_G1_RAW_DEG:
            continue                      # real drawn kink: keep sharp
        b = t_in / n1 + t_out / n2
        nb = float(np.hypot(*b))
        if nb < 1e-9:
            continue
        b /= nb
        l_in = float(np.hypot(c1[6] - c1[4], c1[7] - c1[5]))
        l_out = float(np.hypot(c2[2] - c2[0], c2[3] - c2[1]))
        c1[4] = c1[6] - b[0] * l_in
        c1[5] = c1[7] - b[1] * l_in
        c2[2] = c2[0] + b[0] * l_out
        c2[3] = c2[1] + b[1] * l_out
    return [tuple(c) for c in out]


def _li_anchors(seg: np.ndarray, head_anchored: bool,
                tail_anchored: bool) -> List[int]:
    """Drawing-intent kink vertices inside a piece: k-chord turn >=
    _LI_ANCHOR_DEG that passes the TWO-SCALE LOCALIZATION test (turn
    survives at half chord => true kink; lattice noise and smooth arcs
    read up to ~27deg at k=6 but do NOT localize — without this test,
    noise anchors partition gentle silhouettes into facetable spans and
    the dome grows flat cuts). Piece endpoints are anchors iff they are
    real corners/junctions (not a closed loop's arbitrary seam)."""
    n = len(seg)
    idx = _fill_edge_corners(seg, k=6, min_turn_deg=_LI_ANCHOR_DEG,
                             loc_ratio=0.7, closed=False)
    out: List[int] = ([0] if head_anchored else []) \
        + [i for i in idx if 0 < i < n - 1] \
        + ([n - 1] if tail_anchored else [])
    return sorted(set(out))


def _li_thin_side(labels: Optional[np.ndarray], seg: np.ndarray, i: int,
                  j: int, pair: Tuple[int, int]) -> float:
    """Min local thickness (px) of either neighbor region along span
    midpoints — <=3 means the span bounds a drawn hairline corridor whose
    lattice wobble is quantize noise, not geometry."""
    if labels is None:
        return 99.0
    H, W = labels.shape
    q0, q1 = seg[i], seg[j]
    v = q1 - q0
    L = float(np.hypot(*v))
    if L < 1e-9:
        return 99.0
    nrm = np.array([-v[1], v[0]]) / L
    # Probe from POLYLINE points (never the chord: on a sagged arc the chord
    # sits inside one region and the walk exits instantly — a bowed dome apex
    # then reads "thin" and gets flattened; measured bug, it24). Each walk:
    # thickness of whatever region sits 1.5px off the boundary, until its
    # label changes. The boundary wobbles +-1.4px inside a hairline corridor,
    # so some walks start on the wrong side and read deep — a corridor is
    # called when >=2 of the 6 walks read thin (dome/eye read 0 of 6).
    thin_walks = 0
    for kk in (0.25, 0.5, 0.75):
        p = seg[i + int(round(kk * (j - i)))]
        for sgn in (1.0, -1.0):
            q = p + nrm * sgn * 1.5
            xi, yi = int(round(q[0] - 0.5)), int(round(q[1] - 0.5))
            if not (0 <= xi < W and 0 <= yi < H):
                continue
            lab = labels[yi, xi]
            if lab not in pair:
                continue
            d = 8
            for step in range(2, 8):
                q2 = p + nrm * sgn * (0.5 + step)
                x2, y2 = int(round(q2[0] - 0.5)), int(round(q2[1] - 0.5))
                if not (0 <= x2 < W and 0 <= y2 < H) \
                        or labels[y2, x2] != lab:
                    d = step
                    break
            if d <= _LI_CORR_THIN:
                thin_walks += 1
    return 2.0 if thin_walks >= 2 else 99.0


def _li_span_is_line(seg: np.ndarray, a: int, b: int,
                     labels: Optional[np.ndarray],
                     pair: Tuple[int, int]) -> bool:
    """Is the anchor-to-anchor span a drawn ruler line? Tiered caps
    (population-measured, see block comment above)."""
    L, dmax, smean = _li_run_stats(seg, a, b)
    if L < _LI_SHORT_CHORD:
        return False
    if L <= _LI_SHORT_MAX_CHORD:
        return dmax <= _LI_SHORT_DMAX and smean <= _LI_SHORT_SAG
    if dmax <= _LI_SPAN_DEV and smean <= _LI_SPAN_SAG:
        return True
    if dmax <= _LI_CORR_DEV and smean <= _LI_CORR_SAG \
            and _li_thin_side(labels, seg, a, b, pair) <= _LI_CORR_THIN:
        return True
    return False


# Edge-lineage opt-in: when set to a px tolerance, curved stretches are fit
# with the Schneider minimal-cubic least-squares fitter (a circle -> ~2-4
# cubics) instead of the Potrace segment-merger (which floors at ~16). None =
# quant-11 default behaviour, byte-identical. Set/reset by the edge pipeline.
SCHNEIDER_TOL: Optional[float] = None
SCHNEIDER_SMOOTH: int = 0        # polyline moving-average window (0 = off)


def _smooth_poly(p, win, closed):
    """Moving-average the boundary polyline to erase the pixel staircase before
    fitting (a raw circle contour needs ~20 cubics to hold 2px; smoothed, ~5).
    Endpoints of an OPEN piece are pinned corners — never move them."""
    n = len(p)
    k = win // 2
    if win < 3 or n < win:
        return p
    if closed:
        dup = float(np.hypot(*(p[0] - p[-1]))) < 1e-6
        core = p[:-1] if dup else p
        m = len(core)
        oc = core.copy()
        for i in range(m):
            idx = [(i + o) % m for o in range(-k, k + 1)]
            oc[i] = core[idx].mean(0)
        return np.vstack([oc, oc[:1]]) if dup else oc
    out = p.copy()
    for i in range(k, n - k):        # pinned endpoints (they are corners)
        out[i] = p[i - k:i + k + 1].mean(0)
    return out


# Wander erasure (FITTER, auto-loop 2026-07-11 — the change under test).
# MEASURED: the FITTER lumpiness is NOT the 1px crack staircase (raw-vs-
# smoothed residual is ~0.5px p95 on every stretch = pure alias, absorbed by
# the parsimony fitter's ±0.5px band) but a 6-30px-wavelength, ~1-2px-
# amplitude WANDER of the label boundary — the iso-line a quantizer draws
# through a soft ramp has no pixel-exact home, so it wanders, the wander's
# lumps localize and mint their own >=25deg anchors, and the fitter
# faithfully reproduces the lot as lumpy curves. Fix at the polyline, band-
# limited: fit a REFERENCE curve with coordinates SHRUNK by _LI_IDEAL_SCALE
# (potrace's polygon band is lattice-fixed, so the shrunk band is
# 1/scale px in real units — sub-2px wander cannot create polygon segments
# and vanishes from the reference), then remove from the raw polyline ONLY
# the HIGH-FREQUENCY part of its signed residual about the reference. The
# low-frequency residual (moving average, _LI_IDEAL_LOWIN points) is kept,
# so everywhere the coarse reference is WRONG about real shape — arc
# sagitta, genuine dents, slow curvature — the error cancels out and the
# geometry survives; only the oscillatory wander band is erased. Raw >=25deg
# localized kinks are protected (correction tapered to zero around them) and
# every correction is leash-clamped. Downstream anchor/line-span/fit logic
# then runs UNCHANGED on the cleaned polyline.
_LI_IDEAL_SCALE: float = 0.5     # coordinate shrink for the reference fit
                                 # (0 = off; band = 1/scale px real units)
_LI_IDEAL_LOWIN: int = 21        # low-pass window (points ~ px of arc):
                                 # residual wavelengths shorter than this
                                 # are wander/alias and get removed
_LI_IDEAL_CLAMP: float = 0.9     # max px correction per point (leash)
_LI_IDEAL_PROT: int = 3          # points around a raw kink anchor with the
                                 # correction tapered to zero (corner guard)
_LI_IDEAL_MIN_PTS: int = 40      # pieces shorter than this keep baseline
                                 # (small drawn shapes — eyes, teeth, glyph
                                 # bowls — must never be re-idealized;
                                 # ungated probe: monster color +0.033)
_LI_IDEAL_EXC: float = 0.7       # excursion floor px for wander EVIDENCE:
                                 # above the crack-lattice alias (~0.5) —
                                 # a boundary whose hf residual never
                                 # exceeds this is clean and stays baseline
_LI_IDEAL_FLIPS: int = 6         # min alternating >EXC excursions: one dent
                                 # is a feature, oscillation is wander
_LI_WANDER_ON: bool = True       # scene gate (set per-run by contour_svg):
                                 # FLAT art has no quantizer ramps to wander
                                 # through — its boundaries are drawn ink and
                                 # every sub-px re-idealization is pure risk
                                 # (measured: monster color +0.033 from
                                 # benign-looking <=1px moves). Same
                                 # precedent as the flat-art sharpen/band-
                                 # split skips in pipelines/contour_lines.


def _li_wander_erase(p: np.ndarray, parsimony: float,
                     seam_free: bool = False) -> np.ndarray:
    """Remove the wander band from one fill-edge piece polyline (see block
    comment above). Returns the cleaned polyline (same length/indexing) or
    the input unchanged when no reference fit is available.

    seam_free: the piece is a closed loop whose endpoints are an arbitrary
    seam, NOT a junction/corner — wraparound low-pass, seam unpinned. A
    self-loop edge anchored at a real junction must pass False."""
    import svgcore
    c = _LI_IDEAL_SCALE
    n = len(p)
    flat = [float(v) * c for xy in p for v in xy]
    cs = svgcore.fit_open_parsimony(flat, 1.0, parsimony * c)
    if not cs:
        return p
    chain = [tuple(v / c for v in cs[k:k + 8]) for k in range(0, len(cs), 8)]
    qs = []                          # sample the reference at ~1px
    for (x0, y0, x1, y1, x2, y2, x3, y3) in chain:
        npts = max(4, int(np.hypot(x3 - x0, y3 - y0)) + 2)
        t = np.linspace(0.0, 1.0, npts)[:, None]
        p0 = np.array([x0, y0]); p1 = np.array([x1, y1])
        p2 = np.array([x2, y2]); p3 = np.array([x3, y3])
        qs.append(((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1
                  + 3 * (1 - t) * (t ** 2) * p2 + (t ** 3) * p3)
    Q = np.vstack(qs)
    if len(Q) < 3:
        return p
    d2 = ((p[:, None, :] - Q[None, :, :]) ** 2).sum(2)
    near = d2.argmin(1)
    tang = np.gradient(Q, axis=0)
    tq = tang[near]
    tn = np.hypot(tq[:, 0], tq[:, 1])
    tn[tn < 1e-9] = 1.0
    nrm = np.stack([tq[:, 1], -tq[:, 0]], 1) / tn[:, None]  # unit normals
    s = ((p - Q[near]) * nrm).sum(1)          # signed offset about reference
    closed = seam_free and bool(np.hypot(*(p[0] - p[-1])) < 1e-6)
    # low-pass along the piece: keep everything the coarse reference got
    # wrong at long wavelengths; remove only the wander band. A seam-free
    # CLOSED loop low-passes with WRAParound — reflect-padding at the
    # arbitrary seam removes real geometry there and mints a seam kink.
    w = min(_LI_IDEAL_LOWIN, n if n % 2 == 1 else n - 1)
    if w >= 3 and closed:
        core = s[:-1]
        pad = w // 2
        s_pad = np.concatenate([core[-pad:], core, core[:pad]])
        s_lo = np.convolve(s_pad, np.ones(w) / w, "valid")
        s_lo = np.concatenate([s_lo, s_lo[:1]])
    elif w >= 3:
        pad = w // 2
        s_pad = np.concatenate([s[pad:0:-1], s, s[-2:-pad - 2:-1]])
        s_lo = np.convolve(s_pad, np.ones(w) / w, "valid")
    else:
        s_lo = s
    hf_raw = s - s_lo
    # wander EVIDENCE gate: the high-frequency residual must OSCILLATE with
    # amplitude above the alias floor. Pure staircase alias (<=~0.5px) needs
    # no fixing (the fitter's own band absorbs it), and a single deep
    # excursion is a real feature — both keep the piece byte-identical.
    exc = np.abs(hf_raw) > _LI_IDEAL_EXC
    sig = np.sign(hf_raw[exc])
    flips = int((sig[1:] != sig[:-1]).sum()) if len(sig) > 1 else 0
    if flips < _LI_IDEAL_FLIPS:
        return p
    hf = np.clip(hf_raw, -_LI_IDEAL_CLAMP, _LI_IDEAL_CLAMP)
    # corner guard: raw localized kinks (>=25deg) keep their exact geometry
    # — but ONLY those sitting ON the reference (|s| <= 0.5px). A kink whose
    # tip is 1-2px OFF the reference is one the wander itself minted (the
    # lump localizes and passes the anchor test); protecting it would re-pin
    # the very lump being erased.
    if _LI_IDEAL_PROT > 0:
        kinks = _fill_edge_corners(p, k=6, min_turn_deg=_LI_ANCHOR_DEG,
                                   loc_ratio=0.7, closed=False)
        for ki in kinks:
            if abs(float(s[ki])) > 0.5:
                continue              # wander-minted lump kink: erase it
            a = max(0, ki - _LI_IDEAL_PROT)
            b = min(n, ki + _LI_IDEAL_PROT + 1)
            hf[a:b] = 0.0
    out = p - hf[:, None] * nrm
    if closed:
        # a seam-free loop has no junction: keep it closed, seam unpinned
        out[-1] = out[0]
    else:
        out[0] = p[0]                 # junction/corner endpoints stay exact
        out[-1] = p[-1]
    return out


def _li_fit_piece(seg: np.ndarray, parsimony: float, head_anchored: bool,
                  tail_anchored: bool, stats: Optional[dict] = None,
                  labels: Optional[np.ndarray] = None,
                  pair: Tuple[int, int] = (-1, -1)
                  ) -> List[Tuple[float, ...]]:
    """Line-intent fit of one inter-corner piece: partition at drawing-
    intent anchors (kinks), emit exact chords for anchor-to-anchor spans
    that measure ruler-straight (kinks between spans stay pinned), fit the
    curved remainder with parsimony cubics + raster-gated G1 repair."""
    import svgcore

    # SCHNEIDER path: erase the pixel staircase from the WHOLE piece before any
    # anchor/line-intent classification — otherwise false kinks fragment a
    # smooth loop into ~35 short spans (a circle came out 35 cubics instead of
    # ~8). Smoothing first lets the loop stay one piece and fit minimally.
    if SCHNEIDER_TOL is not None and SCHNEIDER_SMOOTH:
        seg = np.asarray(seg, float)
        _closed = len(seg) > 3 and float(np.hypot(*(seg[0] - seg[-1]))) < 1e-6
        seg = _smooth_poly(seg, SCHNEIDER_SMOOTH, _closed)

    def _fit_curved(pts, gate_pts=None):
        """Fit a curved (already corner-split) stretch to the fewest cubics.
        gate_pts: the pre-erase polyline for the same stretch — G1 repair's
        real-kink gate must read RAW turns (the cleaned polyline reads a
        real 25-30deg kink below the 20deg gate and the corner is lost)."""
        if SCHNEIDER_TOL is not None:
            import schneider_fit
            arr = np.asarray(pts, float)
            closed = len(arr) > 3 and float(np.hypot(*(arr[0] - arr[-1]))) < 1e-6
            if closed:
                return schneider_fit.fit_closed(arr, SCHNEIDER_TOL)
            return schneider_fit.fit_curve(arr, SCHNEIDER_TOL)
        flat = [float(v) for xy in pts for v in xy]
        cs = svgcore.fit_open_parsimony(flat, 1.0, parsimony)
        chain = [tuple(cs[k:k + 8]) for k in range(0, len(cs), 8)]
        gp = pts if gate_pts is None else gate_pts
        return _li_g1_repair(chain, np.asarray(gp, float))

    npts = len(seg)
    q0, q1 = seg[0], seg[-1]
    plen = float(np.hypot(*(q1 - q0)))
    # Straight-piece prior (run 29, GAP_LEDGER #2), kept verbatim: pizza's
    # black grid is ALL fill-layer; parsimony bows its ruler-straight
    # boundaries. RMS<=0.9px / max<=2.8px over >=20px = straight.
    if plen >= 20.0 and npts >= 12:
        c0 = seg.mean(0)
        _, _, vt = np.linalg.svd(seg - c0, full_matrices=False)
        resid = np.abs(np.cross(vt[0], seg - c0))
        if (float(np.sqrt((resid ** 2).mean())) <= 0.9
                and float(resid.max()) <= 2.8):
            if stats is not None:
                stats["li_run29"] = stats.get("li_run29", 0) + 1
            return [_li_line_cubic(q0, q1)]

    # Piece-level wander erasure BEFORE anchor detection: deep label-
    # boundary wander (1-2px lumps) turns ~50deg over a 6px chord and
    # LOCALIZES, so it mints its own 25deg anchors — the piece is then
    # chopped at the lumps and no inter-anchor treatment can ever see a full
    # wander period (measured: shield outer edge, wobble tiles unchanged by
    # stretch-level smoothing). Cleaning the polyline first removes the
    # lumps AND their minted anchors; real kinks survive (corner guard +
    # low-pass keeps all long-wavelength geometry) and everything below
    # runs UNCHANGED on the cleaned polyline.
    raw_seg = None
    if SCHNEIDER_TOL is None and _LI_WANDER_ON and _LI_IDEAL_SCALE > 0 \
            and npts >= _LI_IDEAL_MIN_PTS:
        raw_seg = np.asarray(seg, float)
        seg = _li_wander_erase(raw_seg, parsimony,
                               seam_free=not head_anchored
                               and not tail_anchored)
        if seg is raw_seg:
            raw_seg = None               # evidence gate skipped this piece
        elif stats is not None:
            stats["li_wander"] = stats.get("li_wander", 0) + 1

    anchors = _li_anchors(seg, head_anchored, tail_anchored)
    # classify each consecutive anchor span; merge non-line stretches
    line_spans: List[Tuple[int, int]] = []
    for a, b in zip(anchors[:-1], anchors[1:]):
        if b - a >= 4 and _li_span_is_line(seg, a, b, labels, pair):
            line_spans.append((a, b))
    if not line_spans:
        # no ruler evidence: whole piece = curve fit (parsimony or Schneider)
        return _fit_curved(seg, raw_seg)

    cubics: List[Tuple[float, ...]] = []
    pos = 0
    for (i, j) in line_spans + [(npts - 1, None)]:
        if pos < i:                      # curved stretch before the line
            gap = seg[pos:i + 1]
            if len(gap) >= 2:
                cubics += _fit_curved(
                    gap, None if raw_seg is None else raw_seg[pos:i + 1])
        if j is None:
            break
        if stats is not None:
            stats["li_lines"] = stats.get("li_lines", 0) + 1
        cubics.append(_li_line_cubic(seg[i], seg[j]))
        pos = j
    return cubics


def _li_capsule_d(path, tol: float = 2.5, corner_deg: float = 75.0,
                  smooth_win: int = 11) -> str:
    """Line-intent centerline fit for light-line capsules (the monster
    hand/body hairlines are capsule STROKES painted last — a straight fill
    boundary underneath cannot fix a wavy capsule over it). Decompose the
    skeleton path at localized kinks (two-scale 25deg test: wrist kinks
    34/43deg localize, staircase noise does not); ruler spans emit as exact
    L segments with the kink pinned, curved spans keep the smoothed
    Schneider fit. Paths with no ruler span are fitted exactly as before."""
    p = np.asarray(path, float)
    if len(p) < 5:
        return _fit_branch(p, tol, corner_deg, smooth_win, False)
    corners = _fill_edge_corners(p, k=6, min_turn_deg=_LI_ANCHOR_DEG,
                                 loc_ratio=0.7, closed=False)
    anchors = [0] + [c for c in corners if 0 < c < len(p) - 1] + [len(p) - 1]
    spans = []
    any_line = False
    for a, b in zip(anchors[:-1], anchors[1:]):
        if b - a < 2:
            continue
        L, dmax, smean = _li_run_stats(p, a, b)
        is_line = (L >= _LI_CAP_CHORD and dmax <= _LI_CAP_DEV
                   and smean <= _LI_CAP_SAG)
        any_line |= is_line
        spans.append((a, b, is_line))
    if not any_line:
        return _fit_branch(p, tol, corner_deg, smooth_win, False)
    parts = [f"M {p[0][0]:.2f} {p[0][1]:.2f}"]
    for a, b, is_line in spans:
        if is_line:
            parts.append(f"L {p[b][0]:.2f} {p[b][1]:.2f}")
        else:
            d = _fit_branch(p[a:b + 1], tol, corner_deg, smooth_win, False)
            body = d.split(" ", 3)[3] if d.startswith("M ") else d
            parts.append(body)
    return " ".join(parts)


def _fill_svg_corner_pinned(labels: np.ndarray, centers: np.ndarray,
                            edges, loops_by_region,
                            parsimony: float,
                            stats: Optional[dict] = None) -> str:
    """Parsimony fill emission with serration corners pinned as fit
    breakpoints (drop-in for boundary.loops_to_svg_curves, parsimony>0).

    Each edge polyline is split at _fill_edge_corners; every piece is fitted
    independently (endpoints exact), so the corner survives as a hard vertex
    the merge pass cannot round away. A closed loop with corners is rotated
    to start at its first corner first, so ALL its corners become pinned
    endpoints. Per-piece fitting is line-intent aware (_li_fit_piece):
    ruler-straight runs anchored at real kinks emit as exact chords, the
    curved remainder is parsimony-fitted with raster-gated G1 repair."""
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
        # piece ends anchored = real corner or junction node; a closed loop
        # WITHOUT corners has an arbitrary seam at 0 — never an anchor.
        seam_free = closed and not corners
        for pi, (a, b) in enumerate(zip(bounds[:-1], bounds[1:])):
            seg = pts[a:b + 1]
            if len(seg) < 2:
                continue
            head_anchored = not (seam_free and pi == 0)
            tail_anchored = not (seam_free and pi == len(bounds) - 2)
            cubics += _li_fit_piece(seg, parsimony, head_anchored,
                                    tail_anchored, stats, labels=labels,
                                    pair=(e["left"], e["right"]))
        fitted[i] = cubics
    # Per-shape layered emission + underpaint seal (audit24 E8 / ledger 0h,
    # it25 C-layeremit): one single-subpath path per shape in painter's
    # order, nested seams sealed by the hole drop, sibling seams by
    # paint-order seal strokes. Fit logic above is untouched — this only
    # changes how the fitted chains are assembled into paths.
    from boundary_split import emit_regions_layered
    # seal_width 2.0 (USER coverage feedback 2026-07-13): the 1.0 sibling seal
    # left a ~1px background sliver between a fill and its neighbour/ink where
    # the two independently-fitted boundaries didn't quite coincide (visible
    # as white gaps inside the glasses lens, beaver tail). The seal grows only
    # the HIDDEN side (inner half over the lower fill = same colour; outer half
    # under the upper fill), so widening closes the sliver with no change to
    # visible line weight — verified corpus-wide by eye (5 diverse images
    # full-frame identical) and KB (flat). Deep-zoom: lens/tail coverage gaps
    # close. Does NOT address gaps whose cause is a genuinely inset fill
    # contour (residual tail sliver) — that's an AA/fit issue, tracked separately.
    return emit_regions_layered(labels, centers, loops_by_region, fitted,
                                edges, seal_width=2.0)


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


# Fill-colour source re-anchor (COLOR mode): RGB trim radius around the
# centroid and the minimum in-trim coverage to accept a re-centre.
_FILLC_TRIM = 40.0
_FILLC_MIN_FRAC = 0.5


def _source_region_colors(labels: np.ndarray, centers: np.ndarray,
                          color_img: Optional[np.ndarray]) -> np.ndarray:
    """Per-region fill palette anchored to the SOURCE pixels each region covers.

    The k-means centroid a region carries drifts from the pixels it actually
    ends up painting: k-means runs on the SHARPENED frame (steeper contrast /
    saturation than the source), and palette consolidation folds thin AA-halo
    clusters into the neighbour they wrap WITHOUT recomputing the survivor's
    centre. The tilecmp COLOR channel scores our fills against the SOURCE
    raster, so that drift shows up directly as ΔE-to-source.

    Re-anchor each label's fill to the source pixels it covers, but as a
    centroid-trimmed mean rather than a raw mean/median: keep only the covered
    pixels within _FILLC_TRIM RGB of the centroid, then average those. The
    trim rejects exactly the two populations that would otherwise poison a
    plain region average — the dark AA-halo ring consolidation absorbed into
    the fill, and the far tail of a merged gradient the quantizer under-split —
    so we recover the region's DOMINANT flat tone (the Recraft-style
    idealisation) re-centred on the true source values. Uses the ORIGINAL
    label map (ink is still its own dark label here, before stroke pixels are
    absorbed into fills), so a fill's colour is never dragged toward the line
    it abuts. A region with too few in-trim pixels keeps its centroid, so the
    change can only re-centre a well-populated flat tone, never invent one.
    Stroke colours are untouched — only the fill palette is re-derived."""
    if color_img is None or color_img.ndim != 3:
        return centers
    out = centers.copy()
    flat = labels.ravel()
    px = color_img.reshape(-1, color_img.shape[2])[:, :3].astype(np.float64)
    cen = centers.astype(np.float64)
    order = np.argsort(flat, kind="stable")
    sl = flat[order]
    bounds = np.searchsorted(sl, np.arange(len(centers) + 1))
    t2 = _FILLC_TRIM * _FILLC_TRIM
    for r in range(len(centers)):
        a, b = bounds[r], bounds[r + 1]
        if b <= a:
            continue
        reg = px[order[a:b]]
        d2 = ((reg - cen[r]) ** 2).sum(1)
        keep = reg[d2 < t2]
        if len(keep) < _FILLC_MIN_FRAC * len(reg):
            continue
        out[r] = np.clip(np.round(keep.mean(0)), 0, 255).astype(out.dtype)
    return out


def contour_svg(labels: np.ndarray, centers: np.ndarray,
                fill_tol: float = 2.5, fill_smooth: int = 9,
                fill_corner_deg: float = 60.0, fill_parsimony: float = 0.0,
                color_img: Optional[np.ndarray] = None,
                fill_wander: bool = True,
                **kw) -> Tuple[str, dict]:
    """Full width-constant emission: absorbed fills + stroke network on top.

    fill_parsimony > 0 fits the shading-region boundaries with the Potrace
    parsimony fitter (wobble-free by construction) instead of smooth+Schneider
    — the fills then read as idealized flat shapes, like Recraft's.

    color_img (source raster, optional): re-derives the FILL palette from the
    actual source pixels each region covers (source-anchored ΔEc), leaving the
    stroke palette on the original centroids.

    fill_wander: enables the parsimony fills' wander-erasure prepass
    (_li_wander_erase). Pass False for FLAT art — no quantizer ramps, drawn
    boundaries only (see _LI_WANDER_ON)."""
    import boundary

    global _LI_WANDER_ON
    _LI_WANDER_ON = bool(fill_wander)

    strokes, stroke_mask, info = extract_contour_strokes(labels, centers, **kw)
    # Fill palette anchored to the source pixels each region covers; strokes
    # keep the original centroids (their dark_lum / join-colour decisions).
    fill_centers = _source_region_colors(labels, centers, color_img)
    # Structural-line rescue (edge-11 graft, it67): thin dark structural
    # lines the label chain LOST (pizza-box grid separators absorbed into
    # the cell fills) are re-detected from the source raster and
    # synthesized as strokes painted last; their px join the absorb mask
    # so fills tuck underneath. Components the old stroke layer claimed
    # are excluded by construction, and where a completed line re-draws a
    # half-kept dashed one, the old dash strokes are suppressed — nothing
    # emits twice.
    if color_img is not None and color_img.ndim == 3:
        from stroke_graft import graft_structural_strokes, \
            suppress_old_strokes
        graft, graft_claim, corridors, ginfo = graft_structural_strokes(
            labels, centers, stroke_mask, color_img, fill_centers)
        info.update(ginfo)
        if graft:
            strokes, ndrop = suppress_old_strokes(strokes, corridors)
            info["graft_suppressed"] = ndrop
            stroke_mask = stroke_mask | graft_claim
            strokes = strokes + graft
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
        svg = _fill_svg_corner_pinned(new_labels, fill_centers, edges, loops,
                                      parsimony=fill_parsimony, stats=info)
    else:
        svg = boundary.loops_to_svg_curves(new_labels, fill_centers, edges,
                                           loops,
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
