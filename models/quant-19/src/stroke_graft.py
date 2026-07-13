"""stroke_graft — structural-line rescue layer (edge-11 graft, it67).

The label-cleanup chain LOSES thin dark structural lines: the pizza-box
checkered-grid separators quantize into fragments that despeckle/smooth/
own-transitions absorb into the neighbouring fills (and into the red cell
blobs, which the stroke layer correctly routes to fills), so whole grid
lines vanish from the output while Recraft keeps them crisp. The old
stroke layer cannot see them — its input is the post-cleanup label map.

This module re-detects such lines from the RASTER (evidence the chain
cannot destroy) and SYNTHESIZES strokes for exactly the ones the engine
provably lost, edge-11 style (centerline chains + width profile -> <path
stroke>), painted last. Detection and synthesis are deliberately narrow:

  ridge px    morphological blackhat (thin dark structures only; wide
              regions and step edges do not respond) outside the old
              stroke layer's claim,
  component   welded across old-stroke crossings (a grid separator that
              crosses a kept vertical stays ONE chain), then gated on
              population-measured evidence (constants below),
  LOST        the px would render far from source (their label's fill
              colour is not their colour) — ink the pipeline dropped.
              Correct fills (glyphs, kept black fragments) score near 0,
  structural  long + thin + uniform width + darker than BOTH flanks +
              composed of straight runs joined at corners. Organic art
              (elephant/fox/rabbit contours, fur, face curves) fails the
              straight-run / lost gates — measured fire-rate 0 there,
  synthesis   skeleton chains -> leashed smoothing -> constant width ->
              polyline <path fill="none" stroke>. Anything that does not
              resolve into clean near-constant-width chains is DROPPED
              (status quo preserved), never ribbon-guessed.

Absorption: claimed px (outside the old stroke mask) are handed back to
the caller to fold into stroke_mask BEFORE absorb_mask, so fills tuck
underneath and never double-draw the line. Old strokes keep their own
claim — a graft component never re-emits one (its px are excluded from
detection), so nothing is drawn twice.

All px constants are calibrated at work dim 1024 and scaled by S/1024
(edge-11 ran at 2048; its constants were halved and re-measured here).
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

import cv2
import numpy as np
from scipy import ndimage

_STRUCT8 = np.ones((3, 3), bool)

# --- population-measured gates (2026-07-12, work dim 1024) -------------------
# fire population: pizza-box lost grid separators / band-boundary line
#   (lost .62-1.0, wmed 1.9-2.7, skl 57-1016, straight runs), chopchop lost
#   straight ink marks. must-not population: elephant purple contour net
#   (lost .24), fox fur/shading boundaries (lost .13-.79 but curved:
#   straight-frac ~0), rabbit face curves (curved) and sewing dashes
#   (straight but skl 30-46). Margins noted per constant.
_BH_KSIZE = 9          # blackhat kernel: fits lines to ~7px full width
_BH_GATE = 30.0        # ridge contrast: true lines 46-132, JPEG/shading <20
_LOST_DE = 48.0        # src-vs-rendered RGB distance that counts as lost
_LOST_FRAC = 0.35      # component lost share: fires .62+, elephant .24-.28,
                       # chopchop kept-ink .00-.29 (margin both sides)
_MAX_W = 4.5           # median full width cap: separators 1.9-2.7, pizza
                       # glyph strokes 7.6, corner shade bands 5.7
_MIN_SKL = 48.0        # skeleton length: separators 57+, rabbit dashes <=46
_MIN_AREA = 30
_FLANK_LUM = 12.0      # darker than BOTH flanks by this margin
_FLANK_FRAC = 0.70     # share of sampled centerline px passing the flank test
_CORNER_DEG = 28.0     # chain corner split angle (over a 6px chord)
_STRAIGHT_DEV = 1.5    # max chord deviation of a "straight" run
_STRAIGHT_FRAC = 0.75  # share of chain px in straight runs: grid 1.0 (bends
                       # are corners), fox/rabbit curves ~0
_WIDTH_CV = 0.20       # constant-width acceptance (edge-11: 0.18)
_MIN_WIDTH = 1.6       # emitted stroke width floor (display-scale safe)
_WELD_K = 7            # close kernel: re-welds a line across a crossing
                       # old stroke (~2.7px + 2px dilation gap)
_EXT_MAX = 5.0         # max px a chain end may extend to meet old ink
_CLAIM_CAP = 0.015     # runaway guard: claimed px share of frame
# --- dash completion: a structural line the old layer HALF-kept renders as
# interleaved [old stroke dash][lost gap][dash…] (pizza-box band boundary).
# The lost gaps alone fail the length gate; if marching from a gap seed
# along its end tangents finds near-continuous thin-dark evidence (ridge px
# under the dashes count) spanning a full line, ONE stroke is drawn over
# the whole span and the dash strokes inside its corridor are suppressed
# (they must not also emit — the double-draw rule).
_COMPL_MIN_SKL = 16.0  # seed floor: shorter fragments are noise
_COMPL_EXT = 260.0     # max march per side
_COMPL_GAP = 4.0       # max consecutive unsupported march px — an
                       # INTENTIONALLY dashed source line (rabbit sewing
                       # dashes, source-light gaps 4-8px) must stop the
                       # march; pipeline-damaged lines are source-dark
                       # continuous (support is the undilated blackhat)
_COMPL_COVER = 0.80    # supported share of the marched span
_SUPPRESS_TOL = 3.5    # old-stroke pt distance to the completed centerline
# --- curved structural rescue (pass 3): structural lines that are hand-
# drawn with a gentle BOW (pizza-box apex inner roof lines: chord deviation
# 1.1-3.0 over 26-59 px corner-split pieces, no >=28 deg corner) fail the
# straight-run gate (sfrac 0.00-0.60) and never seed completions. They are
# rescued ONLY when the image itself proves structural-line context
# (pass-1 accepts) and every remaining evidence gate agrees. Populations
# measured 2026-07-12: pizza-box 12 pass-1 accepts / rescue targets flank
# .57-1.00 dev<=2.98 tips-at-ink 1.9-3.7; must-not stems rabbit/fox/
# chopchop/elephant have ZERO pass-1 accepts (pass inert), and fox's
# curved fur pieces additionally sit 148-311 px from any ink.
_RESCUE_MIN_CTX = 3    # pass-1 accepted comps required before rescue runs
_RESCUE_DEV = 3.4      # per corner-split-piece chord deviation cap (px at
                       # 1024): gentle bow passes, organic arcs (fox 5.4,
                       # 13.9) do not
_RESCUE_FLANK = 0.50   # flank bar for junction-laden lines (cell corners
                       # sample non-darker): targets 0.57-1.00, the
                       # junction weld blob (0.31) stays out
_RESCUE_ANCHOR = 6.0   # chain-tip -> old-ink distance that counts anchored
                       # (a dash-cut line abuts its kept dashes: measured
                       # tips 1.9-3.7, farthest true tip 8.5 stays free)
_RESCUE_MAX = 40       # candidate memory cap per image


def _order_skeleton(sk: np.ndarray) -> List[np.ndarray]:
    """Trace a skeleton crop into ordered polylines (split at junctions).

    Returns a list of (N,2) float arrays in (x, y) crop coordinates. Same
    walk as edge-11 strokes._walk_segments, with collinear continuations
    merged across junctions so a through-line is one chain.
    """
    ys, xs = np.nonzero(sk)
    if len(ys) < 4:
        return []
    skel_set = set(zip(ys.tolist(), xs.tolist()))

    def nbrs(p):
        return [(p[0] + dy, p[1] + dx)
                for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                if (dy or dx) and (p[0] + dy, p[1] + dx) in skel_set]

    deg = {p: len(nbrs(p)) for p in skel_set}
    seen = set()

    def walk(start, first):
        seg = [start, first]
        seen.add((start, first)); seen.add((first, start))
        prev, cur = start, first
        while deg.get(cur) == 2:
            step = [q for q in nbrs(cur) if q != prev]
            if not step or (cur, step[0]) in seen:
                break
            nq = step[0]
            seen.add((cur, nq)); seen.add((nq, cur))
            seg.append(nq)
            prev, cur = cur, nq
        return seg

    segments = []
    for pp in skel_set:
        if deg[pp] != 2:
            for q in nbrs(pp):
                if (pp, q) not in seen:
                    segments.append(walk(pp, q))
    for pp in skel_set:                      # pure loops
        if deg[pp] == 2:
            for q in nbrs(pp):
                if (pp, q) not in seen:
                    segments.append(walk(pp, q))

    def end_dir(seg, at_start, k=6):
        k = min(k, len(seg) - 1)
        if at_start:
            v = (seg[0][0] - seg[k][0], seg[0][1] - seg[k][1])
        else:
            v = (seg[-1][0] - seg[-1 - k][0], seg[-1][1] - seg[-1 - k][1])
        n = math.hypot(v[0], v[1]) or 1.0
        return (v[0] / n, v[1] / n)

    # merge collinear continuations at junctions
    junc = {}
    alive = [s for s in segments if len(s) >= 2]
    for i, s in enumerate(alive):
        for end, pp in ((0, s[0]), (1, s[-1])):
            if deg.get(pp, 0) > 2:
                junc.setdefault(pp, []).append((i, end))
    link = {}
    for jp, ends in junc.items():
        cand = []
        for a in range(len(ends)):
            for b in range(a + 1, len(ends)):
                ia, ea = ends[a]; ib, eb = ends[b]
                if ia == ib:
                    continue
                da = end_dir(alive[ia], ea == 0)
                db = end_dir(alive[ib], eb == 0)
                ang = math.degrees(math.acos(
                    max(-1.0, min(1.0, -(da[0] * db[0] + da[1] * db[1])))))
                if ang <= 40.0:
                    cand.append((ang, ends[a], ends[b]))
        used = set()
        for ang, ea_, eb_ in sorted(cand):
            if ea_ in used or eb_ in used or ea_ in link or eb_ in link:
                continue
            link[ea_] = eb_; link[eb_] = ea_
            used.add(ea_); used.add(eb_)

    consumed = set()
    chains = []
    for i, s in enumerate(alive):
        if i in consumed:
            continue
        start = None
        for end in (0, 1):
            if (i, end) not in link:
                start = (i, 1 - end)
                break
        if start is None:
            start = (i, 1)
        pts = []
        cur, exit_end = start
        while True:
            consumed.add(cur)
            seg = alive[cur] if exit_end == 1 else alive[cur][::-1]
            pts.extend(seg if not pts else seg[1:])
            nxt = link.get((cur, exit_end))
            if nxt is None or nxt[0] in consumed:
                break
            cur = nxt[0]
            exit_end = 1 - nxt[1]
        chains.append(np.array([(x, y) for (y, x) in pts], dtype=np.float64))
    return chains


def _corner_split(pts: np.ndarray, k: int = 6,
                  deg: float = _CORNER_DEG) -> List[np.ndarray]:
    """Split a polyline at hard direction changes (structural corners)."""
    n = len(pts)
    if n < 2 * k + 3:
        return [pts]
    cuts = [0]
    i = k
    while i < n - k:
        v1 = pts[i] - pts[i - k]
        v2 = pts[i + k] - pts[i]
        n1 = np.hypot(*v1) or 1.0
        n2 = np.hypot(*v2) or 1.0
        cosang = float(np.dot(v1, v2) / (n1 * n2))
        ang = math.degrees(math.acos(max(-1.0, min(1.0, cosang))))
        if ang >= deg:
            cuts.append(i)
            i += k          # one corner per neighbourhood
        i += 1
    cuts.append(n - 1)
    return [pts[a:b + 1] for a, b in zip(cuts[:-1], cuts[1:]) if b > a]


def _straight_frac(pts: np.ndarray) -> float:
    """Fraction of the chain's px lying in straight runs between corners."""
    total = 0
    straight = 0
    for piece in _corner_split(pts):
        m = len(piece)
        total += m
        if m < 5:
            straight += m       # too short to bend
            continue
        a, b = piece[0], piece[-1]
        ab = b - a
        L = float(np.hypot(*ab))
        if L < 1e-6:
            continue
        d = np.abs(np.cross(ab / L, piece - a))
        if float(d.max()) <= _STRAIGHT_DEV:
            straight += m
    return straight / max(total, 1)


def _smooth_leashed(pts: np.ndarray, win: int, leash: float) -> np.ndarray:
    n = len(pts)
    if n < win + 2 or win < 3:
        return pts
    k = win // 2
    sm = np.empty_like(pts)
    for i in range(n):
        a = max(0, i - k); b = min(n, i + k + 1)
        sm[i] = pts[a:b].mean(axis=0)
    d = sm - pts
    dist = np.hypot(d[:, 0], d[:, 1])
    over = dist > leash
    if over.any():
        sm[over] = pts[over] + d[over] * (leash / dist[over, None])
    return sm


def _movavg(v: np.ndarray, win: int) -> np.ndarray:
    if len(v) < 3 or win < 3:
        return v
    k = win // 2
    out = np.empty_like(v)
    for i in range(len(v)):
        a = max(0, i - k); b = min(len(v), i + k + 1)
        out[i] = v[a:b].mean()
    return out


def _poly_d(pts: np.ndarray, eps: float = 0.9) -> Optional[str]:
    ap = cv2.approxPolyDP(pts.astype(np.float32).reshape(-1, 1, 2), eps,
                          False)
    ap = ap[:, 0, :]
    if len(ap) < 2:
        return None
    return "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in ap)


def _flank_ok_mask(pts: np.ndarray, gray: np.ndarray,
                   halfw: float) -> np.ndarray:
    """Per-point darker-than-both-flanks mask along a polyline."""
    n = len(pts)
    if n < 5:
        return np.ones(n, bool)
    i0 = np.arange(n)
    a = np.maximum(i0 - 2, 0)
    b = np.minimum(i0 + 2, n - 1)
    t = pts[b] - pts[a]
    tl = np.hypot(t[:, 0], t[:, 1])
    tl[tl < 1e-6] = 1.0
    nrm = np.stack([-t[:, 1], t[:, 0]], 1) / tl[:, None]
    off = halfw + 2.5
    H, W = gray.shape

    def _sample(q):
        xq = np.clip(q[:, 0].round().astype(int), 0, W - 1)
        yq = np.clip(q[:, 1].round().astype(int), 0, H - 1)
        return gray[yq, xq]

    f1 = _sample(pts - nrm * off)
    f2 = _sample(pts + nrm * off)
    c = _sample(pts)
    return (c + _FLANK_LUM < f1) & (c + _FLANK_LUM < f2)


def _flank_ok_frac(pts: np.ndarray, gray: np.ndarray, halfw: float) -> float:
    """Share of centerline samples darker than BOTH flanks by _FLANK_LUM."""
    n = len(pts)
    if n < 5:
        return 0.0
    idx = np.arange(2, n - 2, 3)
    if len(idx) == 0:
        idx = np.array([n // 2])
    t = pts[np.minimum(idx + 2, n - 1)] - pts[np.maximum(idx - 2, 0)]
    tl = np.hypot(t[:, 0], t[:, 1])
    ok_t = tl > 1e-6
    if not ok_t.any():
        return 0.0
    nrm = np.stack([-t[:, 1], t[:, 0]], 1) / np.maximum(tl, 1e-6)[:, None]
    off = halfw + 2.5
    H, W = gray.shape
    P = pts[idx]

    def _sample(q):
        xq = np.clip(q[:, 0].round().astype(int), 0, W - 1)
        yq = np.clip(q[:, 1].round().astype(int), 0, H - 1)
        return gray[yq, xq]

    f1 = _sample(P - nrm * off)
    f2 = _sample(P + nrm * off)
    c = _sample(P)
    passed = (c + _FLANK_LUM < f1) & (c + _FLANK_LUM < f2) & ok_t
    return float(passed.sum()) / max(int(ok_t.sum()), 1)


def graft_structural_strokes(labels: np.ndarray, centers: np.ndarray,
                             stroke_mask: np.ndarray,
                             src: np.ndarray,
                             fill_centers: Optional[np.ndarray] = None,
                             ) -> Tuple[List[dict], np.ndarray, dict]:
    """Detect + synthesize the structural lines the pipeline lost.

    labels/centers: post-cleanup label map (what the fills will render).
    stroke_mask: the old stroke layer's claim (never re-claimed here).
    src: the un-sharpened work-dim source raster (RGB) — all evidence.
    fill_centers: source-anchored fill palette if the caller has one
        (what the fills will ACTUALLY paint); defaults to centers.

    Returns (strokes, claim_mask, info): strokes are _stroke_elements
    dicts painted last; claim_mask px must be folded into the absorb
    mask so fills tuck underneath.
    """
    info = {"graft_strokes": 0, "graft_px": 0, "graft_comps": 0}
    if src is None or src.ndim != 3:
        return [], np.zeros(labels.shape, bool), [], info
    H, W = labels.shape
    S = max(H, W)
    sc = S / 1024.0
    gray = (0.299 * src[..., 0] + 0.587 * src[..., 1]
            + 0.114 * src[..., 2]).astype(np.float32)
    kbh = max(5, int(round(_BH_KSIZE * sc)) | 1)
    kb = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kbh, kbh))
    bh = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kb)
    ridge = bh > _BH_GATE
    if not ridge.any():
        return [], np.zeros(labels.shape, bool), [], info

    excl = cv2.dilate(stroke_mask.astype(np.uint8),
                      np.ones((3, 3), np.uint8)).astype(bool)
    cand = ridge & ~excl
    kw = max(3, int(round(_WELD_K * sc)) | 1)
    welded = cv2.morphologyEx(cand.astype(np.uint8), cv2.MORPH_CLOSE,
                              np.ones((kw, kw), np.uint8)).astype(bool)
    # welds may run THROUGH an old stroke (crossings) but a claim never
    # absorbs old-stroke px; also never let a weld bloat past the ridge
    # by more than the crossing corridor
    n, lab = cv2.connectedComponents(welded.astype(np.uint8), connectivity=8)
    if n <= 1:
        return [], np.zeros(labels.shape, bool), [], info

    fc = centers if fill_centers is None else fill_centers
    rendered = fc[labels].astype(np.float32)
    dE = np.sqrt(((src.astype(np.float32) - rendered) ** 2).sum(-1))

    from skimage.morphology import skeletonize

    objs = ndimage.find_objects(lab)
    claim = np.zeros((H, W), bool)
    strokes: List[dict] = []
    corridors: List[Tuple[np.ndarray, float]] = []
    seeds: List[dict] = []
    rescues: List[dict] = []
    n_p1 = 0                # pass-1 accepted comps (rescue context gate)
    min_skl = _MIN_SKL * sc
    max_w = _MAX_W * sc
    cap_px = _CLAIM_CAP * H * W
    # distance to old ink for the end-extension step
    ink_dist = cv2.distanceTransform((~stroke_mask).astype(np.uint8),
                                     cv2.DIST_L2, 3) if stroke_mask.any() \
        else None

    for ci in range(1, n):
        sl = objs[ci - 1]
        if sl is None:
            continue
        y0 = max(0, sl[0].start - 2); x0 = max(0, sl[1].start - 2)
        y1 = min(H, sl[0].stop + 2); x1 = min(W, sl[1].stop + 2)
        m = lab[y0:y1, x0:x1] == ci
        area = int(m.sum())
        if area < _MIN_AREA * sc * sc:
            continue
        own = m & ~excl[y0:y1, x0:x1]        # evidence + claim px
        if own.sum() < 0.5 * area:
            continue                          # mostly weld corridor: junk
        # LOST evidence: would render far from source
        lost_frac = float((dE[y0:y1, x0:x1][own] > _LOST_DE).mean())
        if lost_frac < _LOST_FRAC:
            continue
        dist = cv2.distanceTransform(np.pad(m, 1).astype(np.uint8),
                                     cv2.DIST_L2, 3)[1:-1, 1:-1]
        sk = skeletonize(m)
        skl = int(sk.sum())
        if skl < _COMPL_MIN_SKL * sc:
            continue
        wprof_all = 2.0 * dist[sk]
        wmed = float(np.median(wprof_all))
        if wmed > max_w or wmed <= 0:
            continue
        chains = _order_skeleton(sk)
        if not chains:
            continue
        # fragmented skeleton -> drop (never guess); structural lines
        # resolve into few long chains
        mean_len = sum(len(c) for c in chains) / len(chains)
        if mean_len < max(12.0 * sc, 2.5 * wmed):
            continue
        pts_all = np.vstack(chains)
        sfrac = sum(_straight_frac(c) * len(c) for c in chains) \
            / max(len(pts_all), 1)
        if sfrac < _STRAIGHT_FRAC:
            # failed ONLY the straight-run gate so far — remember it for
            # the curved-rescue pass (its remaining gates run there)
            if len(rescues) < _RESCUE_MAX:
                rescues.append({"chains": chains, "wmed": wmed, "own": own,
                                "crop": (y0, y1, x0, x1)})
            continue
        # darker than BOTH flanks along the centerline (blend-band killer)
        gcrop = gray[y0:y1, x0:x1]
        fl = sum(_flank_ok_frac(c, gcrop, wmed / 2.0) * len(c)
                 for c in chains) / max(len(pts_all), 1)
        if fl < _FLANK_FRAC:
            continue
        if skl < min_skl:
            # too short alone — candidate SEED for dash completion (pass 2)
            longest = max(chains, key=len)
            if len(longest) >= 0.6 * skl and len(longest) >= 8:
                seeds.append({"chain": longest, "wmed": wmed,
                              "skl": skl, "crop": (y0, y1, x0, x1)})
            continue
        if claim.sum() + own.sum() > cap_px:
            break
        # ---- accepted: synthesize ----
        # colour: median of source at centerline px (line core, robust to
        # the flank AA mix) — never the palette
        xi = np.clip(pts_all[:, 0].round().astype(int), 0, x1 - x0 - 1)
        yi = np.clip(pts_all[:, 1].round().astype(int), 0, y1 - y0 - 1)
        core = src[y0:y1, x0:x1][yi, xi].reshape(-1, 3)
        col = tuple(int(v) for v in np.median(core, axis=0))
        comp_strokes = []
        painted = np.zeros(m.shape, np.uint8)
        ok = True
        for ch in chains:
            if len(ch) < max(6.0 * sc, 2.0 * wmed):
                continue
            w = 2.0 * dist[np.clip(ch[:, 1].round().astype(int), 0,
                                   y1 - y0 - 1),
                           np.clip(ch[:, 0].round().astype(int), 0,
                                   x1 - x0 - 1)]
            w = _movavg(w, 9)
            cv_ = float(w.std() / (w.mean() + 1e-9))
            if cv_ > _WIDTH_CV:
                ok = False
                break
            wid = max(_MIN_WIDTH * sc, float(w.mean()))
            sm = _smooth_leashed(ch.copy(), win=7, leash=1.2)
            cv2.polylines(painted,
                          [sm.round().astype(np.int32).reshape(-1, 1, 2)],
                          False, 1, thickness=int(round(wid)) + 3)
            sm = sm + np.array([x0, y0], np.float64)
            # extend free ends to meet the old ink they abut (T-junctions)
            if ink_dist is not None:
                for end in (0, -1):
                    p = sm[end]
                    q = sm[1] if end == 0 else sm[-2]
                    t = p - q
                    tn = np.hypot(*t)
                    if tn < 1e-6:
                        continue
                    t /= tn
                    yi_, xi_ = int(round(p[1])), int(round(p[0]))
                    if 0 <= yi_ < H and 0 <= xi_ < W:
                        d0 = float(ink_dist[yi_, xi_])
                        if 0.5 < d0 <= _EXT_MAX * sc:
                            sm[end] = p + t * min(d0 + 0.5, _EXT_MAX * sc)
            d = _poly_d(sm)
            if d:
                comp_strokes.append(
                    {"d": d, "width": wid, "color": col, "kind": "stroke"})
        if not ok or not comp_strokes:
            continue
        strokes.extend(comp_strokes)
        # claim ONLY px the emitted strokes actually cover — absorption
        # must never erase a detail the graft does not redraw (short spur
        # chains keep their current rendering)
        claim[y0:y1, x0:x1] |= own & painted.astype(bool)
        info["graft_comps"] += 1
        n_p1 += 1

    # ---- pass 2: dash completion --------------------------------------
    # seeds passed every evidence gate except length. If marching from a
    # seed's ends along its end tangents finds near-continuous thin-dark
    # evidence (ridge px under the old dash strokes included), the seed is
    # a LOST GAP of a half-kept structural line: emit ONE stroke over the
    # whole supported span; the dash strokes inside its corridor are
    # suppressed by the caller (suppress_old_strokes).
    if seeds:
        ridge_edt = None
        covered = np.zeros((H, W), np.uint8)
        gap_max = _COMPL_GAP * sc
        seeds.sort(key=lambda s: -s["skl"])

        def _march(p0, u):
            gap = 0.0
            last = 0.0
            support = 0
            steps = int(_COMPL_EXT * sc)
            nx, ny = -u[1], u[0]
            off = 4.0 * sc
            for t in range(1, steps + 1):
                fx = p0[0] + u[0] * t
                fy = p0[1] + u[1] * t
                x = int(round(fx)); y = int(round(fy))
                if not (0 <= x < W and 0 <= y < H):
                    break
                if covered[y, x]:
                    break                    # tile against prior corridors
                # support = thin-dark evidence that IS line ink here IN THE
                # SOURCE (undilated blackhat — an intentionally dashed
                # source line must read as gaps), AND that px is either
                # still rendering far from source (lost) or an old stroke
                # DASH thin across the march normal. A bare nearby ridge
                # (or riding a thick outline's flank) is NOT enough:
                # marching along a CONVERGING second line overran the merge
                # point (pizza left pinch) and minted a floating double.
                ok = False
                if bh[y, x] > 0.8 * _BH_GATE:
                    if dE[y, x] > 0.75 * _LOST_DE:
                        ok = True
                    elif excl[y, x]:
                        xa = int(round(fx + nx * off))
                        ya = int(round(fy + ny * off))
                        xb = int(round(fx - nx * off))
                        yb = int(round(fy - ny * off))
                        ina = excl[ya, xa] if (0 <= xa < W and 0 <= ya < H) \
                            else False
                        inb = excl[yb, xb] if (0 <= xb < W and 0 <= yb < H) \
                            else False
                        ok = not (ina or inb)   # thin dash, not outline
                if ok:
                    gap = 0.0
                    last = float(t)
                    support += 1
                else:
                    gap += 1.0
                    if gap > gap_max:
                        break
            return last, support

        for sd in seeds:
            y0, y1, x0, x1 = sd["crop"]
            ch = sd["chain"]
            wmed = sd["wmed"]
            sm = _smooth_leashed(ch.copy(), win=7, leash=1.2) \
                + np.array([x0, y0], np.float64)
            # trim chain ends that fail the flank test (px hugging a
            # neighbouring thick line where the two converge — they would
            # aim the march tangent along the WRONG line)
            fok = _flank_ok_mask(sm, gray, wmed / 2.0)
            max_trim = len(sm) // 4
            h = 0
            while h < max_trim and not fok[h]:
                h += 1
            tzz = 0
            while tzz < max_trim and not fok[len(sm) - 1 - tzz]:
                tzz += 1
            if h or tzz:
                sm = sm[h:len(sm) - tzz]
            if len(sm) < 8:
                continue
            xi_s = np.clip(sm[:, 0].round().astype(int), 0, W - 1)
            yi_s = np.clip(sm[:, 1].round().astype(int), 0, H - 1)
            if covered[yi_s, xi_s].mean() > 0.4:
                continue                     # a corridor already owns it
            k = min(6, len(sm) - 1)
            u_head = sm[0] - sm[k]
            u_tail = sm[-1] - sm[-1 - k]
            nh = float(np.hypot(*u_head)); nt = float(np.hypot(*u_tail))
            if nh < 1e-6 or nt < 1e-6:
                continue
            u_head /= nh; u_tail /= nt
            lh, sh = _march(sm[0], u_head)
            lt, st_ = _march(sm[-1], u_tail)
            span = sd["skl"] + lh + lt
            if span < min_skl:
                continue
            cover = (sd["skl"] + sh + st_) / max(span, 1e-6)
            if cover < _COMPL_COVER:
                continue
            full = sm
            if lh > 0.5:
                full = np.vstack([(sm[0] + u_head * lh)[None, :], full])
            if lt > 0.5:
                full = np.vstack([full, (sm[-1] + u_tail * lt)[None, :]])
            # completions must be RULER-STRAIGHT PER PIECE: a structural
            # span may legitimately bend at a hard corner, so the sagitta
            # cap applies to each corner-split piece (same machinery as
            # the straight-run gate), NOT end to end. Rabbit's must-not
            # organic creases (ear fold, bag crease — ink-anchored both
            # ends!) have NO >=28 deg corner: measured, they stay ONE
            # piece at sag 1.64-2.21 and die here exactly as before
            # (pizza's six true spans: single piece, sag 0.0-1.1, pass).
            ab = full[-1] - full[0]
            if float(np.hypot(*ab)) < 1e-6:
                continue                     # degenerate folded span
            sag_ok = True
            for piece in _corner_split(full):
                if len(piece) < 2:
                    continue
                pab = piece[-1] - piece[0]
                Lab = float(np.hypot(*pab))
                if Lab < 1e-6:
                    continue
                sag = float(np.abs(np.cross(pab / Lab,
                                            piece - piece[0])).max())
                if sag > 1.3 * sc:
                    sag_ok = False
                    break
            if not sag_ok:
                continue
            # END ANCHORS: a structural completion reconnects ink to ink —
            # both ends must land at old strokes, an accepted graft claim,
            # or another corridor (dash-line segments abut their dashes).
            # Organic creases/shadow streaks (rabbit ear fold, soft-shadow
            # streak: high contrast but free-floating ends) die here —
            # measured the only remaining separator vs must-not targets.
            anchored = True
            atol = 6.0 * sc
            for endpt in (full[0], full[-1]):
                ex = int(round(endpt[0])); ey = int(round(endpt[1]))
                if not (0 <= ex < W and 0 <= ey < H):
                    continue                 # frame border = anchored
                d_ink = float(ink_dist[ey, ex]) if ink_dist is not None \
                    else 1e9
                if d_ink <= atol:
                    continue
                w0 = np.s_[max(0, ey - 4):ey + 5, max(0, ex - 4):ex + 5]
                if claim[w0].any() or covered[w0].any():
                    continue
                anchored = False
                break
            if not anchored:
                continue
            # width from the WHOLE span's ridge support, not the seed's own
            # px (a seed at a locally wide pinch minted a fat line before)
            if ridge_edt is None:
                ridge_edt = cv2.distanceTransform(
                    ridge.astype(np.uint8), cv2.DIST_L2, 3)
            samp = []
            for a, b in zip(full[:-1], full[1:]):
                seg_len = float(np.hypot(*(b - a)))
                for tt in np.linspace(0.0, 1.0,
                                      max(2, int(seg_len / 3.0))):
                    q = a + (b - a) * tt
                    xq = int(round(q[0])); yq = int(round(q[1]))
                    if 0 <= xq < W and 0 <= yq < H \
                            and ridge_edt[yq, xq] > 0:
                        samp.append(2.0 * float(ridge_edt[yq, xq]))
            wid = float(np.median(samp)) if samp else wmed
            wid = float(np.clip(wid, _MIN_WIDTH * sc, _MAX_W * sc))
            core = src[np.clip(ch[:, 1].round().astype(int) + y0, 0, H - 1),
                       np.clip(ch[:, 0].round().astype(int) + x0, 0, W - 1)]
            col = tuple(int(v) for v in np.median(core.reshape(-1, 3),
                                                  axis=0))
            d = _poly_d(full)
            if not d:
                continue
            strokes.append({"d": d, "width": wid, "color": col,
                            "kind": "stroke"})
            rad = max(wid / 2.0 + 2.0, 3.0)
            corr = np.zeros((H, W), np.uint8)
            cv2.polylines(corr,
                          [full.round().astype(np.int32).reshape(-1, 1, 2)],
                          False, 1, thickness=int(round(2 * rad)) + 1)
            covered |= corr
            # absorb every lost-evidence px the new stroke paints over
            # (the seed px + speck fragments along the line)
            claim |= cand & corr.astype(bool)
            corridors.append((full, rad))
            info["graft_comps"] += 1
            info["graft_completions"] = info.get("graft_completions", 0) + 1

    # ---- pass 3: curved structural rescue ------------------------------
    # A structural line drawn with a gentle hand bow (pizza-box apex inner
    # roof lines) fails the straight-run gate and cannot be marched over
    # (the completion ray is straight). Rescue such a component — along
    # its OWN centerline chains, bow preserved — only when EVERYTHING
    # else proves it is line ink the pipeline lost:
    #   context   the image already yielded >= _RESCUE_MIN_CTX pass-1
    #             accepts (structural-line art). Organic stems measure 0
    #             pass-1 accepts -> this pass cannot run there,
    #   bow       every corner-split piece stays within _RESCUE_DEV of
    #             its chord (organic arcs exceed it),
    #   flank     darker than both flanks at _RESCUE_FLANK (junctions
    #             with kept lines sample non-darker, hence < pass-1 bar),
    #   anchored  >= 2 chain tips at old ink (a dash-cut line abuts its
    #             kept dashes), >= 1 of them on the emitted chain,
    #   width     constant per component (its wmed — the median is robust
    #             to the junction bulges that break the pass-1 width-cv).
    # Only the LONGEST chain is emitted — junction spur chains self-cross
    # into scribbles (eye-checked) — and its ends are flank-trimmed like
    # pass-2 seeds (the apex tip curls into the roof edge it abuts).
    if rescues and n_p1 >= _RESCUE_MIN_CTX:
        atol = _RESCUE_ANCHOR * sc
        for rc in rescues:
            y0, y1, x0, x1 = rc["crop"]
            wmed = rc["wmed"]
            chains = [c for c in rc["chains"]
                      if len(c) >= max(6.0 * sc, 2.0 * wmed)]
            if not chains:
                continue
            pts_all = np.vstack(rc["chains"])
            gcrop = gray[y0:y1, x0:x1]
            fl = sum(_flank_ok_frac(c, gcrop, wmed / 2.0) * len(c)
                     for c in rc["chains"]) / max(len(pts_all), 1)
            if fl < _RESCUE_FLANK:
                continue
            bow_ok = True
            for ch in chains:
                for piece in _corner_split(ch):
                    if len(piece) < 5:
                        continue
                    pab = piece[-1] - piece[0]
                    Lp = float(np.hypot(*pab))
                    if Lp < 1e-6:
                        continue
                    dev = float(np.abs(np.cross(
                        pab / Lp, piece - piece[0])).max())
                    if dev > _RESCUE_DEV * sc:
                        bow_ok = False
                        break
                if not bow_ok:
                    break
            if not bow_ok:
                continue
            main = max(chains, key=len)

            def _tip_anch(ch):
                cnt = 0
                for e in (0, -1):
                    ex = int(round(ch[e][0] + x0))
                    ey = int(round(ch[e][1] + y0))
                    if not (0 <= ex < W and 0 <= ey < H):
                        cnt += 1             # frame border = anchored
                        continue
                    d_ink = float(ink_dist[ey, ex]) \
                        if ink_dist is not None else 1e9
                    if d_ink <= atol:
                        cnt += 1
                return cnt

            anch = sum(_tip_anch(ch) for ch in chains)
            if anch < 2 or _tip_anch(main) < 1:
                continue
            if claim.sum() + rc["own"].sum() > cap_px:
                break
            xi = np.clip(main[:, 0].round().astype(int), 0, x1 - x0 - 1)
            yi = np.clip(main[:, 1].round().astype(int), 0, y1 - y0 - 1)
            core = src[y0:y1, x0:x1][yi, xi].reshape(-1, 3)
            col = tuple(int(v) for v in np.median(core, axis=0))
            wid = max(_MIN_WIDTH * sc, float(wmed))
            painted = np.zeros(rc["own"].shape, np.uint8)
            smc = _smooth_leashed(main.copy(), win=7, leash=1.2)
            sm = smc + np.array([x0, y0], np.float64)
            # trim ends that fail the flank test (the apex tip curls into
            # the roof edge it abuts) — same rule as pass-2 seeds
            fok = _flank_ok_mask(sm, gray, wmed / 2.0)
            max_trim = len(sm) // 4
            h = 0
            while h < max_trim and not fok[h]:
                h += 1
            tz = 0
            while tz < max_trim and not fok[len(sm) - 1 - tz]:
                tz += 1
            if h or tz:
                sm = sm[h:len(sm) - tz]
                smc = smc[h:len(smc) - tz]
            if len(sm) < 8:
                continue
            cv2.polylines(painted,
                          [smc.round().astype(np.int32).reshape(-1, 1, 2)],
                          False, 1, thickness=int(round(wid)) + 3)
            # extend free ends to meet the old ink they abut (same rule
            # as pass 1 — closes the dash-cut seams)
            if ink_dist is not None:
                for end in (0, -1):
                    p = sm[end]
                    q = sm[1] if end == 0 else sm[-2]
                    t = p - q
                    tn = np.hypot(*t)
                    if tn < 1e-6:
                        continue
                    t /= tn
                    yi_, xi_ = int(round(p[1])), int(round(p[0]))
                    if 0 <= yi_ < H and 0 <= xi_ < W:
                        d0 = float(ink_dist[yi_, xi_])
                        if 0.5 < d0 <= _EXT_MAX * sc:
                            sm[end] = p + t * min(d0 + 0.5, _EXT_MAX * sc)
            d = _poly_d(sm)
            if not d:
                continue
            strokes.append({"d": d, "width": wid, "color": col,
                            "kind": "stroke"})
            claim[y0:y1, x0:x1] |= rc["own"] & painted.astype(bool)
            info["graft_comps"] += 1
            info["graft_rescues"] = info.get("graft_rescues", 0) + 1

    info["graft_strokes"] = len(strokes)
    info["graft_px"] = int(claim.sum())
    return strokes, claim, corridors, info


_FLOAT_RE = None


def suppress_old_strokes(old: List[dict],
                         corridors: List[Tuple[np.ndarray, float]]
                         ) -> Tuple[List[dict], int]:
    """Drop old stroke elements that lie WHOLLY inside a completed-line
    corridor — the graft redraws that line as one continuous stroke, so
    the dash pieces must not also emit (double-draw rule)."""
    if not corridors or not old:
        return old, 0
    global _FLOAT_RE
    if _FLOAT_RE is None:
        import re
        _FLOAT_RE = re.compile(r"-?\d+\.?\d*(?:e-?\d+)?")

    def _min_dist(px, py, poly):
        best = 1e18
        a = poly[:-1]; b = poly[1:]
        ab = b - a
        ap = np.array([px, py])[None, :] - a
        L2 = (ab * ab).sum(1)
        t = np.clip((ap * ab).sum(1) / np.maximum(L2, 1e-9), 0.0, 1.0)
        proj = a + ab * t[:, None]
        d2 = ((np.array([px, py])[None, :] - proj) ** 2).sum(1)
        best = float(np.sqrt(d2.min())) if len(d2) else 1e18
        return best

    kept = []
    dropped = 0
    for st in old:
        vals = [float(v) for v in _FLOAT_RE.findall(st.get("d", ""))]
        if len(vals) < 4 or len(vals) % 2:
            kept.append(st)
            continue
        pts = list(zip(vals[0::2], vals[1::2]))
        inside = False
        for poly, rad in corridors:
            tol = rad + _SUPPRESS_TOL
            if all(_min_dist(px, py, poly) <= tol for px, py in pts):
                inside = True
                break
        if inside:
            dropped += 1
        else:
            kept.append(st)
    return kept, dropped
