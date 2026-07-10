"""pathflow (phase 2) — path-correspondence drilldown for a single tile.

tilecmp's `flow` channel is aggregate-per-tile: it says "this tile is drawn
choppier than Recraft" but not *which stroke* or *how*. pathflow answers that:
inside one tile it matches our path to Recraft's (centroid + fill + length),
then compares the matched pair's GEOMETRY directly via the TURNING FUNCTION
(unwrapped direction angle vs normalised arc length). A smooth sweep is a near-
straight ramp; a zigzag oscillates — so the turning-function L2 distance is a
literal measure of "their stroke flows like this, ours stutters like that",
invariant to translation and overall rotation.

Reserve it for the worst tiles tilecmp flags (correspondence is fuzzy and only
worth it where the aggregate channel already says something is wrong).

    python research/design/pathflow.py OURS.svg THEIRS.svg --tile 20,20 \
        --tiles 48 --input data/inputs/chopchop.png --out flow_2020.png
"""
import argparse
import os
import sys

import numpy as np
from svgpathtools import parse_path
from PIL import Image, ImageDraw

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "models", "quant-11", "src"))
import tilecmp  # noqa: E402

EPS = 1e-9


def _hex_rgb(fill):
    fill = (fill or "#000000").strip()
    if fill.startswith("#") and len(fill) == 7:
        return np.array([int(fill[1:3], 16), int(fill[3:5], 16),
                         int(fill[5:7], 16)], float)
    return np.array([0, 0, 0], float)


def polylines_in_region(svg, region, native, step):
    """Return local polyline fragments (longest run inside the expanded region)
    for every path that visits the region. Coordinates in canvas pixels."""
    x0, y0, x1, y1 = region
    mx, my = (x1 - x0) * 0.5, (y1 - y0) * 0.5      # half-tile margin
    ex0, ey0, ex1, ey1 = x0 - mx, y0 - my, x1 + mx, y1 + my
    vbx, vby, vbw, vbh = tilecmp._viewbox(svg)
    cw = native
    ch = native * (vbh / vbw)
    sx, sy = cw / vbw, ch / vbh

    def tc(pt):
        return ((pt.real - vbx) * sx, (pt.imag - vby) * sy)

    out = []
    for d, fill in tilecmp._paths_and_fills(svg):
        try:
            path = parse_path(d)
        except Exception:
            continue
        pts = []
        for seg in path:
            k = max(2, int(abs(seg.end - seg.start) * ((sx + sy) / 2) / step) + 1)
            for t in np.linspace(0, 1, k):
                pts.append(tc(seg.point(t)))
        pts = np.asarray(pts)
        if len(pts) < 3:
            continue
        inside = ((pts[:, 0] >= ex0) & (pts[:, 0] <= ex1) &
                  (pts[:, 1] >= ey0) & (pts[:, 1] <= ey1))
        # is any sample in the *core* tile (not just the margin)?
        core = ((pts[:, 0] >= x0) & (pts[:, 0] <= x1) &
                (pts[:, 1] >= y0) & (pts[:, 1] <= y1))
        if not core.any():
            continue
        # longest contiguous run inside the expanded region
        best, cur = (0, 0), None
        for i, f in enumerate(inside):
            if f:
                cur = (cur[0], i) if cur else (i, i)
                if cur[1] - cur[0] > best[1] - best[0]:
                    best = cur
            else:
                cur = None
        a, b = best
        frag = pts[a:b + 1]
        if len(frag) < 4:
            continue
        out.append({"pts": frag, "rgb": _hex_rgb(fill),
                    "centroid": frag.mean(axis=0),
                    "length": float(np.hypot(*np.diff(frag, axis=0).T).sum()),
                    "ncubic": sum(1 for s in path
                                  if s.__class__.__name__ == "CubicBezier"),
                    "d": d, "fill": fill,           # raw source for LLM snippets
                    "frac_inside": float(inside.mean())})
    return out


def turning_fn(pts, N=64):
    """Unwrapped direction angle re-sampled over normalised arc length [0,1]."""
    d = np.diff(pts, axis=0)
    seglen = np.hypot(d[:, 0], d[:, 1])
    keep = seglen > EPS
    d, seglen = d[keep], seglen[keep]
    if len(seglen) < 2:
        return np.zeros(N)
    ang = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    ang -= ang[0]
    s = np.concatenate([[0.0], np.cumsum(seglen)])
    s = s / (s[-1] + EPS)
    return np.interp(np.linspace(0, 1, N), s[:-1], ang)


def turning_dist(a, b):
    ta, tb = turning_fn(a), turning_fn(b)
    diff = ta - tb
    diff = diff - diff.mean()          # remove global rotation offset
    return float(np.sqrt((diff ** 2).mean()))


def match(ours, theirs, tile_px):
    """Greedy correspondence by centroid + fill + length."""
    pairs = []
    used = set()
    for oi, o in enumerate(ours):
        best, bj = 1e9, -1
        for tj, t in enumerate(theirs):
            if tj in used:
                continue
            col_de = float(np.linalg.norm(o["rgb"] - t["rgb"]))
            if col_de > 120:          # different colour => not the same stroke
                continue              # (leave it unmatched = structural, honest)
            cd = np.hypot(*(o["centroid"] - t["centroid"])) / (tile_px + EPS)
            lr = abs(np.log((o["length"] + EPS) / (t["length"] + EPS)))
            cost = cd + 0.6 * (col_de / 255.0) + 0.3 * lr
            if cost < best:
                best, bj = cost, tj
        if bj >= 0 and best < 1.2:
            used.add(bj)
            pairs.append((oi, bj, best))
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ours"); ap.add_argument("theirs")
    ap.add_argument("--tile", required=True, help="i,j")
    ap.add_argument("--tiles", type=int, default=48)
    ap.add_argument("--native", type=int, default=2048)
    ap.add_argument("--input", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    i, j = (int(v) for v in a.tile.split(","))
    ours_svg = open(a.ours).read()
    theirs_svg = open(a.theirs).read()

    C = a.native
    tile_px = C / a.tiles
    region = (j * tile_px, i * tile_px, (j + 1) * tile_px, (i + 1) * tile_px)
    step = tile_px / 8.0
    ours = polylines_in_region(ours_svg, region, C, step)
    theirs = polylines_in_region(theirs_svg, region, C, step)
    pairs = match(ours, theirs, tile_px)

    print(f"=== pathflow tile ({i},{j})  tiles={a.tiles} ===")
    print(f"  paths in tile: ours={len(ours)}  theirs={len(theirs)}  "
          f"matched={len(pairs)}")
    print(f"  {'pair':10s} {'turn-dist':>9s} {'len o/t':>13s} "
          f"{'cubic o/t':>10s} {'ΔE':>5s}")
    rows = []
    for oi, tj, cost in pairs:
        o, t = ours[oi], theirs[tj]
        td = turning_dist(o["pts"], t["pts"])
        de = float(np.linalg.norm(o["rgb"] - t["rgb"]))
        rows.append((td, oi, tj, o, t, de))
    for td, oi, tj, o, t, de in sorted(rows, reverse=True):
        print(f"  o{oi:<3d}<-t{tj:<3d} {td:9.3f} "
              f"{o['length']:6.0f}/{t['length']:<6.0f} "
              f"{o['ncubic']:4d}/{t['ncubic']:<4d} {de:5.1f}")
    if rows:
        print(f"  MEAN turning-distance (flow mismatch): "
              f"{np.mean([r[0] for r in rows]):.3f}  "
              f"(0 = identical flow; ~>0.4 = clearly different)")
    unmatched_o = len(ours) - len(pairs)
    unmatched_t = len(theirs) - len(pairs)
    if unmatched_o or unmatched_t:
        print(f"  unmatched: ours={unmatched_o} theirs={unmatched_t} "
              f"(structural, not flow — one side has strokes the other lacks)")

    if a.out:
        _overlay(a, i, j, region, tile_px, ours, theirs, pairs, rows)


def _overlay(a, i, j, region, tile_px, ours, theirs, pairs, rows):
    C = a.native
    pad = tile_px
    x0, y0, x1, y1 = region
    vx0, vy0 = int(x0 - pad), int(y0 - pad)
    W = int(x1 - x0 + 2 * pad)
    bg = np.full((W, W, 3), 245, np.uint8)
    if a.input:
        src = np.asarray(Image.open(a.input).convert("RGB").resize((C, C)))
        bg = src[vy0:vy0 + W, vx0:vx0 + W].copy()
        bg = (bg.astype(float) * 0.35 + 255 * 0.65).astype(np.uint8)
    SCALE = 3
    im = Image.fromarray(bg).resize((W * SCALE, W * SCALE), Image.NEAREST)
    dr = ImageDraw.Draw(im)

    def draw(pts, color, width):
        p = [((x - vx0) * SCALE, (y - vy0) * SCALE) for x, y in pts]
        if len(p) > 1:
            dr.line(p, fill=color, width=width)

    for t in theirs:                      # Recraft = magenta
        draw(t["pts"], (220, 30, 200), 5)
    for o in ours:                        # ours = cyan
        draw(o["pts"], (0, 170, 220), 5)
    # tile boundary
    dr.rectangle([(x0 - vx0) * SCALE, (y0 - vy0) * SCALE,
                  (x1 - vx0) * SCALE, (y1 - vy0) * SCALE],
                 outline=(255, 0, 0), width=2)
    dr.text((4, 4), f"tile({i},{j})  cyan=ours  magenta=Recraft", fill=(0, 0, 0))
    im.save(a.out)
    print(f"  overlay -> {a.out}")


if __name__ == "__main__":
    main()
