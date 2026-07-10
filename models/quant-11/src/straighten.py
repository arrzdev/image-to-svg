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


def straighten(svg, eps=1.0, min_len=16.0):
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
        return _emit(_straight_runs(segs, eps, min_len))

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
    return svg


def _seg_end(s):
    return s[2] if s[0] in ('M', 'L') else s[4]


def _straight_runs(segs, eps, min_len):
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
        if jmax >= 0 and math.hypot(end[0] - start[0],
                                    end[1] - start[1]) >= min_len:
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
