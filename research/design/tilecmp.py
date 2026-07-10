"""tilecmp — tiled structural-comparison of two SVGs (ours vs a Recraft target).

WHY THIS EXISTS
---------------
Whole-image metrics (MS-SSIM / GMSD / global path counts, see
metrics_vs_recraft.py) average over everything: they can't say *where* we
diverge from the grail or *what kind* of divergence it is. And eyeballing a
busy image is unreliable. This tool localises the comparison to small tiles and
reports, per tile, a *labelled* distance vector split into three independent
channels:

    census  — HOW MUCH geometry each engine spent
              (n_paths, n_cubic, n_line, n_subpath)
    flow    — HOW the geometry is drawn
              (straightness, curvature rate, corner rate, edge-orientation)
    color   — fill behaviour, incl. dE to the source raster
              (mean color, distinct-color count, dE)

The three channels are kept SEPARATE on purpose. That separation is the whole
point: it lets each hot tile self-classify its failure mode —
  * census high, ours >> theirs   -> OVER-FRAGMENT
  * census high, ours << theirs   -> UNDER-RESOLVE
  * census low  but flow high      -> FITTER (lumpy curves, right budget)
  * color dominates                -> COLOR / GRADIENT
Collapsing to a single scalar throws that away and re-creates the SSIM trap.

This is a DIAGNOSTIC and an ATTENTION-DIRECTOR, not a fitness function: it tells
you which few tiles to deep-zoom and what to look for. The eye stays the judge.

USAGE
-----
    python research/design/tilecmp.py OURS.svg THEIRS.svg \
        [--input data/inputs/chopchop.png] [--tiles 64] [--native 2048] \
        [--out research/design/tilecmp_out/chopchop]

Writes <out>/report.json and <out>/heatmaps.png. Prints the aggregate labelled
vector and the worst tiles with their auto-classified failure mode.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import numpy as np
from svgpathtools import parse_path

# reuse the project's rasteriser (resvg/cairosvg) for the color channel
_Q11_SRC = os.path.join(os.path.dirname(__file__), "..", "..",
                        "models", "quant-11", "src")
sys.path.insert(0, _Q11_SRC)
from render import svg_to_rgb  # noqa: E402

EPS = 1e-9


# ------------------------------------------------------------------- parsing
def _viewbox(svg: str):
    m = re.search(r'viewBox="([\d.\-eE ]+)"', svg)
    if m:
        x, y, w, h = (float(v) for v in m.group(1).split())
        return x, y, w, h
    # fall back to width/height
    w = re.search(r'\bwidth="([\d.]+)', svg)
    h = re.search(r'\bheight="([\d.]+)', svg)
    if w and h:
        return 0.0, 0.0, float(w.group(1)), float(h.group(1))
    raise ValueError("no viewBox or width/height on <svg>")


def _paths_and_fills(svg: str):
    """Return list of (d_string, fill) for every <path>. Targets and our output
    are both flat <path fill=...> with no group transforms (verified), so a
    regex over path elements is exact here."""
    out = []
    for m in re.finditer(r"<path\b([^>]*)>", svg):
        attrs = m.group(1)
        d = re.search(r'\bd="([^"]*)"', attrs)
        if not d:
            continue
        fill = re.search(r'\bfill="([^"]*)"', attrs)
        out.append((d.group(1), fill.group(1) if fill else "#000000"))
    return out


# ------------------------------------------------------------- tile geometry
class TileGrid:
    """Per-tile accumulators for one SVG, in a common CANVAS pixel space."""

    def __init__(self, n, cw, ch):
        self.n = n                     # tiles per side (square grid of n x n)
        self.cw, self.ch = cw, ch      # canvas pixel dims
        self.tw = cw / n               # tile width  (px)
        self.th = ch / n               # tile height (px)
        z = lambda: np.zeros((n, n), dtype=np.float64)  # noqa: E731
        self.arc = z()                 # total polyline length in tile
        self.turn = z()                # total |turning angle| (rad)
        self.corners = z()             # count of sharp turns
        self.n_cubic = z()
        self.n_line = z()
        self.n_quad = z()
        self.n_sub = z()               # subpath starts (M)
        self.orient = np.zeros((n, n, 8), dtype=np.float64)  # dir hist (len-wt)
        self._paths = [[set() for _ in range(n)] for _ in range(n)]

    def _ij(self, x, y):
        j = int(x / self.tw)
        i = int(y / self.th)
        return (min(max(i, 0), self.n - 1), min(max(j, 0), self.n - 1))

    def add_segment_count(self, x, y, kind):
        i, j = self._ij(x, y)
        if kind == "C":
            self.n_cubic[i, j] += 1
        elif kind == "L":
            self.n_line[i, j] += 1
        elif kind == "Q":
            self.n_quad[i, j] += 1

    def add_subpath(self, x, y):
        i, j = self._ij(x, y)
        self.n_sub[i, j] += 1

    def add_step(self, x, y, length, turn, path_idx):
        i, j = self._ij(x, y)
        self.arc[i, j] += length
        self.turn[i, j] += abs(turn)
        self._paths[i][j].add(path_idx)

    def add_corner(self, x, y):
        i, j = self._ij(x, y)
        self.corners[i, j] += 1

    def add_orient(self, x, y, ang, length):
        i, j = self._ij(x, y)
        b = int(((ang % np.pi) / np.pi) * 8) % 8   # direction mod 180deg -> 8
        self.orient[i, j, b] += length

    def n_paths(self):
        return np.array([[len(self._paths[i][j]) for j in range(self.n)]
                         for i in range(self.n)], dtype=np.float64)


def build_grid(svg, n, native):
    vbx, vby, vbw, vbh = _viewbox(svg)
    aspect = vbh / vbw
    cw = native
    ch = native * aspect
    g = TileGrid(n, cw, ch)
    sx, sy = cw / vbw, ch / vbh

    def to_canvas(pt):
        return ((pt.real - vbx) * sx, (pt.imag - vby) * sy)

    STEP = max(cw, ch) / (n * 8.0)   # ~1/8 tile: fine enough for turning
    for pidx, (d, _fill) in enumerate(_paths_and_fills(svg)):
        try:
            path = parse_path(d)
        except Exception:
            continue
        prev_end = None
        prev_dir = None
        for seg in path:
            s = seg.start
            # subpath break (M) when this segment doesn't continue the last
            if prev_end is None or abs(seg.start - prev_end) > 1e-6:
                cx, cy = to_canvas(seg.start)
                g.add_subpath(cx, cy)
                prev_dir = None
            kind = seg.__class__.__name__
            code = {"CubicBezier": "C", "Line": "L",
                    "QuadraticBezier": "Q"}.get(kind, "C")
            mx, my = to_canvas(seg.point(0.5))
            g.add_segment_count(mx, my, code)
            # sample the segment into a polyline (canvas space)
            seg_len_guess = abs(seg.point(0.0) - seg.point(0.5)) + \
                abs(seg.point(0.5) - seg.point(1.0))
            k = max(2, int(seg_len_guess * ((sx + sy) / 2) / STEP) + 1)
            ts = np.linspace(0.0, 1.0, k)
            pts = [to_canvas(seg.point(t)) for t in ts]
            for a in range(1, len(pts)):
                x0, y0 = pts[a - 1]
                x1, y1 = pts[a]
                dx, dy = x1 - x0, y1 - y0
                length = float(np.hypot(dx, dy))
                if length < EPS:
                    continue
                ang = float(np.arctan2(dy, dx))
                turn = 0.0
                if prev_dir is not None:
                    turn = ang - prev_dir
                    while turn > np.pi:
                        turn -= 2 * np.pi
                    while turn < -np.pi:
                        turn += 2 * np.pi
                    if abs(turn) > (40.0 * np.pi / 180.0):
                        g.add_corner((x0 + x1) / 2, (y0 + y1) / 2)
                g.add_step((x0 + x1) / 2, (y0 + y1) / 2, length, turn, pidx)
                g.add_orient((x0 + x1) / 2, (y0 + y1) / 2, ang, length)
                prev_dir = ang
            prev_end = seg.end
    return g, (cw, ch)


# --------------------------------------------------------------- color channel
def color_tiles(svg_or_img, n, cw, ch, is_svg=True):
    if is_svg:
        img = svg_to_rgb(svg_or_img, int(round(cw)), int(round(ch)))
    else:
        img = svg_or_img
    img = np.asarray(img)[:, :, :3].astype(np.float64)
    H, W = img.shape[:2]
    mean = np.zeros((n, n, 3))
    distinct = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            y0, y1 = int(i * H / n), int((i + 1) * H / n)
            x0, x1 = int(j * W / n), int((j + 1) * W / n)
            block = img[y0:y1, x0:x1].reshape(-1, 3)
            if block.size == 0:
                continue
            mean[i, j] = block.mean(axis=0)
            q = (block.astype(np.int32) >> 4)           # quantise 4 bits/chan
            keys = (q[:, 0] << 8) | (q[:, 1] << 4) | q[:, 2]
            distinct[i, j] = len(np.unique(keys))
    return mean, distinct


def _rgb2lab(rgb):
    from skimage.color import rgb2lab
    return rgb2lab((rgb / 255.0)[None, :, :]).reshape(rgb.shape)


def de76(a, b):
    la, lb = _rgb2lab(a), _rgb2lab(b)
    return np.sqrt(((la - lb) ** 2).sum(axis=-1))


# --------------------------------------------------------------- distances
def ndiff(a, b):
    """symmetric normalised difference in [0,1]: 0 identical, 1 max disagreement"""
    return np.abs(a - b) / (np.abs(a) + np.abs(b) + EPS)


def compare(ours_svg, theirs_svg, n=64, native=2048, input_img=None):
    go, (cw, ch) = build_grid(ours_svg, n, native)
    gt, _ = build_grid(theirs_svg, n, native)

    # --- census channel
    po, pt = go.n_paths(), gt.n_paths()
    census = np.mean([ndiff(po, pt),
                      ndiff(go.n_cubic, gt.n_cubic),
                      ndiff(go.n_line, gt.n_line),
                      ndiff(go.n_sub, gt.n_sub)], axis=0)

    # --- flow channel (all terms accumulated per-step at the SAME midpoint
    #     tiles, so each is bounded in [0,1] and mutually consistent)
    curv_o = go.turn / (go.arc + EPS)           # rad per px (choppiness)
    curv_t = gt.turn / (gt.arc + EPS)
    corner_o = go.corners / (go.arc + EPS)      # sharp turns per px
    corner_t = gt.corners / (gt.arc + EPS)
    ho = go.orient / (go.orient.sum(axis=2, keepdims=True) + EPS)
    ht = gt.orient / (gt.orient.sum(axis=2, keepdims=True) + EPS)
    orient_d = 0.5 * np.abs(ho - ht).sum(axis=2)   # L1/2 in [0,1]
    flow = np.mean([ndiff(curv_o, curv_t),
                    ndiff(corner_o, corner_t),
                    orient_d], axis=0)

    # --- color channel
    mo, do = color_tiles(ours_svg, n, cw, ch)
    mt, dt = color_tiles(theirs_svg, n, cw, ch)
    dE_ot = de76(mo, mt)
    dE_os = dE_ts = None
    if input_img is not None:
        # ANCHORED colour error: penalise a tile only where OUR fill is farther
        # from the source than Recraft's is. Removes the "Recraft legitimately
        # re-colours away from source" confound — we're dinged only where we're
        # genuinely worse than the grail against ground truth.
        from PIL import Image
        src = np.asarray(Image.open(input_img).convert("RGB")
                         .resize((int(round(cw)), int(round(ch)))))
        ms, _ = color_tiles(src, n, cw, ch, is_svg=False)
        dE_os = de76(mo, ms)
        dE_ts = de76(mt, ms)
        excess = np.clip(dE_os - dE_ts, 0, None)          # our excess vs grail
        color = 0.7 * np.clip(excess / 8.0, 0, 1) + 0.3 * ndiff(do, dt)
    else:
        # no source: fall back to raw ours-vs-theirs colour distance
        color = 0.6 * np.clip(dE_ot / 10.0, 0, 1) + 0.4 * ndiff(do, dt)

    # --- per-tile weight = ink present (so empty tiles don't dominate)
    weight = np.maximum(go.arc, gt.arc)
    W = weight.sum() + EPS

    def wmean(x):
        return float((x * weight).sum() / W)

    agg = {"census": wmean(census), "flow": wmean(flow),
           "color": wmean(color),
           "overall": wmean(np.mean([census, flow, color], axis=0))}

    # --- failure-mode label per tile (only meaningful where weighted)
    #
    # Ink-presence is checked FIRST: if we have ~no stroke where Recraft has
    # stroke it is a missing-geometry problem (UNDER-RESOLVE) no matter how big
    # the mean-colour delta looks — otherwise a dropped white line on a black
    # field reads as "COLOR" (calibration bug found on flat line-art). COLOR
    # only wins when BOTH sides have geometry and the hue still differs.
    labels = np.empty((n, n), dtype=object)
    ratio = (po + EPS) / (pt + EPS)              # path-count ratio ours/theirs
    ink = (go.arc + EPS) / (gt.arc + EPS)        # stroke-presence ratio
    for i in range(n):
        for j in range(n):
            if ink[i, j] < 0.35:
                labels[i, j] = "UNDER-RESOLVE"    # we're missing geometry here
                continue
            if ink[i, j] > 2.85:
                labels[i, j] = "OVER-FRAGMENT"    # spurious geometry here
                continue
            comps = {"census": census[i, j], "flow": flow[i, j],
                     "color": color[i, j]}
            dom = max(comps, key=comps.get)
            if dom == "color":
                labels[i, j] = "COLOR"
            elif dom == "census" and ratio[i, j] > 1.5:
                labels[i, j] = "OVER-FRAGMENT"
            elif dom == "census" and ratio[i, j] < 0.66:
                labels[i, j] = "UNDER-RESOLVE"
            elif dom == "flow":
                labels[i, j] = "FITTER"
            else:
                labels[i, j] = "MIXED"

    return {
        "n": n, "canvas": [cw, ch], "weight": weight,
        "census": census, "flow": flow, "color": color,
        "overall": np.mean([census, flow, color], axis=0),
        "labels": labels, "agg": agg,
        "extra": {
            "paths_ours": po, "paths_theirs": pt,
            "cubic_ours": go.n_cubic, "cubic_theirs": gt.n_cubic,
            "line_ours": go.n_line, "line_theirs": gt.n_line,
            "curv_ours": curv_o, "curv_theirs": curv_t,
            "dE_ours_src": dE_os, "dE_theirs_src": dE_ts,
        },
    }


# --------------------------------------------------------------- reporting
def _heatmaps(res, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = res["n"]
    w = res["weight"]
    wn = w / (w.max() + EPS)
    panels = [("census", res["census"]), ("flow", res["flow"]),
              ("color", res["color"]), ("overall", res["overall"])]
    fig, ax = plt.subplots(1, 4, figsize=(20, 5))
    for k, (name, arr) in enumerate(panels):
        # dim empty tiles by weight so the eye tracks real ink
        disp = arr * (0.25 + 0.75 * wn)
        im = ax[k].imshow(disp, cmap="inferno", vmin=0, vmax=max(arr.max(), 0.3))
        ax[k].set_title(f"{name}  (agg={res['agg'][name]:.3f})")
        ax[k].set_xticks([]); ax[k].set_yticks([])
        fig.colorbar(im, ax=ax[k], fraction=0.046)
    fig.tight_layout()
    fig.savefig(out_png, dpi=90)
    plt.close(fig)


def _worst(res, k=12):
    n = res["n"]
    w = res["weight"]
    over = res["overall"] * (w > np.percentile(w[w > 0], 50) if (w > 0).any()
                             else w > -1)
    flat = [(res["overall"][i, j], i, j) for i in range(n) for j in range(n)
            if w[i, j] > 0]
    flat.sort(reverse=True)
    return flat[:k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ours"); ap.add_argument("theirs")
    ap.add_argument("--input", default=None)
    ap.add_argument("--tiles", type=int, default=64)
    ap.add_argument("--native", type=int, default=2048)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    ours = open(a.ours).read()
    theirs = open(a.theirs).read()
    res = compare(ours, theirs, n=a.tiles, native=a.native, input_img=a.input)

    ag = res["agg"]
    print(f"=== tilecmp  {os.path.basename(a.ours)}  vs  "
          f"{os.path.basename(a.theirs)}  ({a.tiles}x{a.tiles} tiles) ===")
    print(f"  census={ag['census']:.3f}  flow={ag['flow']:.3f}  "
          f"color={ag['color']:.3f}  overall={ag['overall']:.3f}")
    print(f"  (0 = identical to target, 1 = maximally different; ink-weighted)")
    print("  worst tiles (row,col):")
    for score, i, j in _worst(res):
        po = res["extra"]["paths_ours"][i, j]
        pt = res["extra"]["paths_theirs"][i, j]
        print(f"    ({i:2d},{j:2d})  overall={score:.2f}  "
              f"census={res['census'][i,j]:.2f} flow={res['flow'][i,j]:.2f} "
              f"color={res['color'][i,j]:.2f}  paths {int(po)}/{int(pt)}  "
              f"-> {res['labels'][i, j]}")

    # failure-mode histogram over weighted tiles
    w = res["weight"]
    hist = {}
    for i in range(res["n"]):
        for j in range(res["n"]):
            if w[i, j] > 0:
                lab = res["labels"][i, j]
                hist[lab] = hist.get(lab, 0.0) + w[i, j]
    tot = sum(hist.values()) + EPS
    print("  failure-mode mix (ink-weighted):")
    for lab, v in sorted(hist.items(), key=lambda x: -x[1]):
        print(f"    {lab:14s} {100*v/tot:5.1f}%")

    if a.out:
        os.makedirs(a.out, exist_ok=True)
        _heatmaps(res, os.path.join(a.out, "heatmaps.png"))
        dump = {"agg": ag, "worst": [[float(s), int(i), int(j),
                                      res["labels"][i, j]]
                                     for s, i, j in _worst(res, 30)],
                "failure_mix": hist}
        json.dump(dump, open(os.path.join(a.out, "report.json"), "w"),
                  indent=2)
        print(f"  -> wrote {a.out}/heatmaps.png and report.json")


if __name__ == "__main__":
    main()
