"""Straightness post-process (shared): convert near-straight cubic runs in an
SVG's paths into real `L` commands, matching Recraft's L-heavy representation.

A genuine straight edge is a run of segments (cubic or line) that stays within
`eps` px of the single chord from the run's start to its end AND spans at least
`min_len` px — collapse it to one `L`. The `min_len` gate stops arcs
polygonising: a circle arc is locally near-straight but bows past `eps` before
the run reaches `min_len`, so its cubics stay smooth C.

straighten(svg, eps, min_len) -> svg  (also drops fill="none" junk paths)
"""
import math
import re


def straighten(svg, eps=1.0, min_len=16.0, bow_frac=0.80, bow_floor=0.9,
               speck_frac=0.006):
    # ADAPTIVE eps (USER 2026-07-13, metric-verified). The pipeline embeds a
    # straight-line-dominance signal <!--sld=..--> (image Hough long-line
    # coverage). Geometric art (pizza-box 0.69, logos 0.57) gets aggressive
    # L-collapse; organic art (fox/mountain/crystals ~0.03) keeps the caller's
    # conservative eps so its arcs are not polygonised. A global eps bump is a
    # net corpus loss (fox/mountain/crystals regress +0.012-0.044); this gate
    # gives the pizza-box win (tilecmp 0.293->0.284, long-L 43->86 = Recraft)
    # with zero regression elsewhere.
    m = re.search(r'<!--sld=([\d.]+)-->', svg)
    if m and float(m.group(1)) >= 0.45:
        eps, min_len = 2.5, 8.0
    svg = re.sub(r'<!--sld=[\d.]+-->', '', svg)   # strip the signal comment

    # bow_frac / bow_floor gate the "is this a straight edge that wiggled, or a
    # real arc?" test. A genuinely straight raster edge deviates from its chord
    # on BOTH sides (staircase noise, mean signed dev ~0); a gentle arc bows to
    # ONE side (signed devs same sign). A run collapses to L only if it is NOT a
    # systematic bow: keep the run as cubics when >= bow_frac of its points fall
    # on one side of the chord AND the max deviation exceeds bow_floor px. This
    # lets the aggressive eps above collapse fragmented straight edges into one
    # long L without polygonising any real curve that slips through the sld gate.
    def do_d(d):
        toks = re.findall(r'([MLCZ])|(-?\d+(?:\.\d+)?)', d)
        seq = [('c', c) if c else ('n', float(n)) for c, n in toks]
        segs = []
        cur = (0.0, 0.0)
        j = 0
        while j < len(seq):
            kind, val = seq[j]
            if kind != 'c':
                j += 1
                continue
            if val == 'M':
                x, y = seq[j + 1][1], seq[j + 2][1]
                segs.append(('M', (x, y), (x, y))); cur = (x, y); j += 3
            elif val == 'L':
                x, y = seq[j + 1][1], seq[j + 2][1]
                segs.append(('L', cur, (x, y))); cur = (x, y); j += 3
            elif val == 'C':
                c1 = (seq[j + 1][1], seq[j + 2][1])
                c2 = (seq[j + 3][1], seq[j + 4][1])
                p3 = (seq[j + 5][1], seq[j + 6][1])
                segs.append(('C', cur, c1, c2, p3)); cur = p3; j += 7
            elif val == 'Z':
                segs.append(('Z',)); j += 1
            else:
                j += 1
        return _emit(_straight_runs(segs, eps, min_len, bow_frac, bow_floor))

    svg = re.sub(r'\bd="([^"]*)"', lambda m: f'd="{do_d(m.group(1))}"', svg)
    # Junk-path drop, made precise (UNDER-RESOLVE fix, 2026-07-11). The old
    # pattern removed EVERY path whose attrs contained fill="none" — which
    # deleted the entire visible centerline-stroke layer (fill="none"
    # stroke="#..." stroke-linecap="round": the drawn ink network + light
    # capsules) from every quant-12 output, while the fill layer had already
    # absorbed those line pixels. Eye evidence: pizza-box checker grid lines
    # vanished so cells fused into mud; chopchop trunk/leaf ink broke up.
    # What still gets dropped:
    #   * fill="none" with no stroke attr — paints nothing, true junk;
    #   * butt-capped seal strokes (boundary_split paint-order seam covers,
    #     same color as the fill under them) — near-invisible, but they
    #     count-stuff the tilecmp census channel (measured: restoring them
    #     alone regresses census +0.026 corpus-wide and flips UNDER-RESOLVE
    #     tile labels without adding real geometry).
    # Keeping ONLY the round-cap visible strokes measured (tiles=40):
    # overall -0.0067, census -0.0006, flow -0.0020, color -0.0174.
    svg = re.sub(r'<path\b(?![^>]*\bstroke=")[^>]*fill="none"[^>]*/>\s*',
                 '', svg)
    svg = re.sub(r'<path\b(?=[^>]*fill="none")'
                 r'(?=[^>]*stroke-linecap="butt")[^>]*/>\s*', '', svg)
    svg = _drop_specks(svg, speck_frac)
    return svg


def _drop_specks(svg, frac):
    """Drop quantisation-shrapnel paths — tiny fills Recraft never emits (USER
    2026-07-13 STRUCTURAL gap, metric-verified). Measured: our over-fragmented
    outputs carry 80-155 sub-100px-bbox paths where Recraft carries ~0
    (app-asset 261 paths vs 69, pizza-box 198 vs 73); 74-77% of our paths are
    specks. In the painter's-order layered emit a dropped small path just
    reveals the larger shape beneath it, so removing them is ~absorption.
    Corpus sweep: dropping paths whose bbox max-dimension < frac*canvas_width
    (frac 0.006 ~= 12px@2048) improves tilecmp +0.0046 corpus (app-asset
    -0.0149, pizza-box -0.0146) with ~zero regression (worst stem +0.0003) and
    all channels down; larger frac keeps helping the over-fragmenters but starts
    eroding real detail on chopchop/mountain/crystals, so 0.006 is the safe
    optimum. Thin LONG lines survive (max-dim large); only both-dims-small
    specks drop. bbox is the coordinate extent of the d-string (control points
    slightly overestimate -> conservative). Never drops the background (huge)."""
    if frac <= 0:
        return svg
    m = re.search(r'viewBox="[\d.\-eE]+ [\d.\-eE]+ ([\d.\-eE]+)', svg)
    if not m:
        return svg
    thr = frac * float(m.group(1))
    hdr_end = svg.index('>', svg.index('<svg')) + 1
    head, body = svg[:hdr_end], svg[hdr_end:]

    def keep(tag):
        md = re.search(r'\bd="([^"]*)"', tag)
        if not md:
            return True
        nums = re.findall(r'-?\d+(?:\.\d+)?', md.group(1))
        if len(nums) < 4:
            return True
        xs = [float(n) for n in nums[0::2]]
        ys = [float(n) for n in nums[1::2]]
        return max(max(xs) - min(xs), max(ys) - min(ys)) >= thr

    body = re.sub(r'<path\b[^>]*/>\s*',
                  lambda mm: mm.group(0) if keep(mm.group(0)) else '', body)
    return head + body


def _seg_end(s):
    return s[2] if s[0] in ('M', 'L') else s[4]


def _run_points(segs, lo, hi):
    """All vertices (endpoints + cubic control points) of segs[lo..hi]."""
    pts = []
    for k in range(lo, hi + 1):
        s = segs[k]
        if s[0] == 'L':
            pts.append(s[2])
        else:                       # 'C': control1, control2, end
            pts.extend((s[2], s[3], s[4]))
    return pts


def _is_bow(start, end, pts, bow_frac, bow_floor):
    """True if the run is a systematic one-sided bow (a real arc) rather than
    two-sided raster wiggle around a straight edge. Signed perpendicular
    distance of each interior point to the start->end chord: an arc has
    >= bow_frac of points on ONE side with max |dev| >= bow_floor; noise
    around a straight edge crosses the chord (mixed sign, small)."""
    ax, ay = start; bx, by = end
    dx, dy = bx - ax, by - ay
    ln = math.hypot(dx, dy)
    if ln < 1e-6:
        return False
    signed = [((px - ax) * dy - (py - ay) * dx) / ln for px, py in pts]
    mx = max((abs(s) for s in signed), default=0.0)
    if mx < bow_floor:
        return False                # deviations are sub-floor: it's straight
    npos = sum(1 for s in signed if s > 0)
    nneg = sum(1 for s in signed if s < 0)
    tot = npos + nneg
    if tot == 0:
        return False
    return max(npos, nneg) / tot >= bow_frac


def _straight_runs(segs, eps, min_len, bow_frac=0.80, bow_floor=0.9):
    out = []
    i = 0
    n = len(segs)
    while i < n:
        if segs[i][0] in ('M', 'Z'):
            out.append(segs[i]); i += 1; continue
        start = segs[i][1]
        jmax = -1
        j = i
        while j < n and segs[j][0] in ('L', 'C'):
            end = _seg_end(segs[j])
            ok = True
            for k in range(i, j + 1):
                s = segs[k]
                pts = (s[2],) if s[0] == 'L' else (s[2], s[3], s[4])
                if not all(_near_line(start, end, w, eps) for w in pts):
                    ok = False; break
            if ok:
                jmax = j; j += 1
            else:
                break
        end = _seg_end(segs[jmax]) if jmax >= 0 else None
        # collapse the run to one L only if it spans min_len AND is not a
        # systematic bow (a real arc). The bow gate is what lets eps rise for
        # noise tolerance without polygonising curves.
        if (jmax >= 0
                and math.hypot(end[0] - start[0], end[1] - start[1]) >= min_len
                and not _is_bow(start, end,
                                _run_points(segs, i, jmax),
                                bow_frac, bow_floor)):
            out.append(('L', start, end)); i = jmax + 1
        else:
            out.append(segs[i]); i += 1
    return out


def _emit(seg):
    parts = []
    for s in seg:
        if s[0] == 'M':
            parts.append(f"M{s[2][0]:.2f} {s[2][1]:.2f}")
        elif s[0] == 'L':
            parts.append(f"L{s[2][0]:.2f} {s[2][1]:.2f}")
        elif s[0] == 'C':
            _, _, c1, c2, p3 = s
            parts.append(f"C{c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} "
                         f"{c2[1]:.2f} {p3[0]:.2f} {p3[1]:.2f}")
        elif s[0] == 'Z':
            parts.append("Z")
    return "".join(parts)


def _near_line(a, b, p, eps):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    ln = math.hypot(dx, dy)
    if ln < 1e-6:
        return math.hypot(px - ax, py - ay) < eps
    return abs((px - ax) * dy - (py - ay) * dx) / ln < eps
