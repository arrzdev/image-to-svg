"""Minimal version-testing frontend for the image→SVG engine.

    ./run.sh            # http://127.0.0.1:8000

Pick an image, pick a version, Run — the page shows ORIGINAL | OUTPUT | TARGET
(Recraft reference, when one exists). Every run goes through the same stable
entry contract (models/<v>/entry.py) in an isolated subprocess, exactly like
`python run_model.py`.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
INPUTS = ROOT / "data" / "inputs"
TARGETS = ROOT / "data" / "targets"
MODELS = ROOT / "models"
PYTHON = ROOT / ".venv" / "bin" / "python"

app = FastAPI(title="image-to-svg version tester")


@app.get("/api/images")
def images():
    return sorted(p.name for p in INPUTS.iterdir()
                  if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))


@app.get("/api/versions")
def versions():
    return sorted(p.parent.name for p in MODELS.glob("*/entry.py"))


class RunReq(BaseModel):
    image: str
    version: str


@app.post("/api/run")
def run(req: RunReq):
    image = INPUTS / Path(req.image).name          # no traversal
    entry = MODELS / Path(req.version).name / "entry.py"
    if not image.exists():
        raise HTTPException(404, f"unknown image {req.image!r}")
    if not entry.exists():
        raise HTTPException(404, f"unknown version {req.version!r}")

    out = ROOT / "data" / "outputs" / \
        f"{image.stem}-{req.version}-{time.strftime('%Y%m%d-%H%M%S')}.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")
    python = PYTHON if PYTHON.exists() else Path(sys.executable)

    t0 = time.time()
    r = subprocess.run([str(python), str(entry), str(image), str(out)],
                       env=env, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise HTTPException(500, f"{req.version} failed:\n{r.stderr[-2000:]}")

    target = TARGETS / f"{image.stem}.svg"
    has_target = target.exists() and target.read_text().lstrip().startswith("<")
    return {
        "svg": out.read_text(),
        "seconds": round(time.time() - t0, 1),
        "kb": out.stat().st_size // 1024,
        "saved": str(out.relative_to(ROOT)),
        "target": f"/targets/{target.name}" if has_target else None,
        "target_kb": target.stat().st_size // 1024 if has_target else None,
    }


class EdgeLabReq(BaseModel):
    # defaults = the USER's hand-tuned recipe (2026-07-11): native-ish res,
    # light edge-preserving denoise, high sensitivity, hard weld.
    image: str
    work_dim: int = 2048
    pre: str = "bilateral"     # none | gaussian | bilateral
    pre_strength: int = 1      # gaussian: kernel radius; bilateral: sigma/25
    threshold: float = 5.0     # Lab dE boundary trigger
    close_k: int = 7           # join kernel (0 = no join)
    min_cell: int = 0          # dissolve cells smaller than this (px)
    svg_eps: float = 1.5       # polyline simplification (px) for the SVG stage
    ink: bool = False          # stroke the wall skeleton over the fills
                               # (off: fills-only — the backfilled partition
                               # already renders ink interiors as cells)


def _trace_ink(bndc, bcol, eps):
    """Vectorize the welded wall mask as INK: skeletonize, split the skeleton
    at junctions, and trace each continuous degree-2 run as ONE stroke path
    (width = 2x median distance-to-edge, colour = median darkest-side colour
    along the run). Returns list of <path .../> strings."""
    import cv2
    import numpy as np
    from skimage.morphology import skeletonize

    skel = skeletonize(bndc)
    dist = cv2.distanceTransform(bndc.astype(np.uint8), cv2.DIST_L2, 3)
    ys, xs = np.nonzero(skel)
    if not len(ys):
        return []
    skel_set = set(zip(ys.tolist(), xs.tolist()))
    OFF = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))

    def nbrs(p):
        return [(p[0] + dy, p[1] + dx) for dy, dx in OFF
                if (p[0] + dy, p[1] + dx) in skel_set]

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
    for p in skel_set:                      # junction/endpoint-anchored runs
        if deg[p] != 2:
            for q in nbrs(p):
                if (p, q) not in seen:
                    segments.append(walk(p, q))
    loops = []
    for p in skel_set:                      # pure loops (no junction anywhere)
        if deg[p] == 2:
            for q in nbrs(p):
                if (p, q) not in seen:
                    loops.append(walk(p, q))

    # ---- ink-graph optimization (the raw junction-cut segments are ~4x too
    # many paths): 1. prune noise spurs, 2. merge collinear continuations
    # across junctions so one visually continuous line = ONE path.
    SPUR_MIN = 20          # px: shorter free-ended stubs are skeleton noise
    CONT_DEG = 50.0        # max direction change that still reads "same line"

    def _end_dir(seg, at_start):
        k = min(6, len(seg) - 1)
        if at_start:
            v = (seg[0][0] - seg[k][0], seg[0][1] - seg[k][1])
        else:
            v = (seg[-1][0] - seg[-1 - k][0], seg[-1][1] - seg[-1 - k][1])
        n = (v[0] ** 2 + v[1] ** 2) ** 0.5 or 1.0
        return (v[0] / n, v[1] / n)         # unit vector pointing OUT the end

    junc = {}                               # junction px -> [(seg_i, end)]
    for i, s in enumerate(segments):
        for end, p in ((0, s[0]), (1, s[-1])):
            if deg.get(p, 0) > 2:
                junc.setdefault(p, []).append((i, end))
    alive = [len(s) >= 3 for s in segments]
    for i, s in enumerate(segments):        # spur pruning
        if len(s) < SPUR_MIN:
            free = (deg.get(s[0], 0) == 1) + (deg.get(s[-1], 0) == 1)
            if free:
                alive[i] = False

    # pair up best collinear continuations at every junction
    import math
    link = {}                               # (seg,end) -> (seg,end)
    for jp, ends in junc.items():
        ends = [(i, e) for (i, e) in ends if alive[i]]
        cand = []
        for a in range(len(ends)):
            for b in range(a + 1, len(ends)):
                ia, ea = ends[a]; ib, eb = ends[b]
                if ia == ib:
                    continue
                da = _end_dir(segments[ia], ea == 0)
                db = _end_dir(segments[ib], eb == 0)
                # both vectors point OUT of their ends i.e. away from the
                # junction; a continuation has them OPPOSITE
                ang = math.degrees(math.acos(
                    max(-1.0, min(1.0, -(da[0] * db[0] + da[1] * db[1])))))
                if ang <= CONT_DEG:
                    cand.append((ang, ends[a], ends[b]))
        used = set()
        for ang, ea_, eb_ in sorted(cand):
            if ea_ in used or eb_ in used or ea_ in link or eb_ in link:
                continue
            link[ea_] = eb_; link[eb_] = ea_
            used.add(ea_); used.add(eb_)

    # chain segments through links into merged polylines
    consumed = set()
    chains = []
    for i, s in enumerate(segments):
        if not alive[i] or i in consumed:
            continue
        # find a chain start: an end with no link (or fall back to i,0 for
        # closed chains)
        start = None
        for end in (0, 1):
            if (i, end) not in link:
                start = (i, 1 - end)        # begin traversal exiting other end
                break
        if start is None:
            start = (i, 1)
        pts = []
        cur, exit_end = start
        while True:
            consumed.add(cur)
            seg = segments[cur] if exit_end == 1 else segments[cur][::-1]
            pts.extend(seg if not pts else seg[1:])
            nxt = link.get((cur, exit_end))
            if nxt is None or nxt[0] in consumed:
                break
            cur = nxt[0]
            exit_end = 1 - nxt[1]           # enter at nxt end, exit the other
        chains.append(pts)
    chains.extend(l for l in loops if len(l) >= 4)

    out = []
    for seg in chains:
        if len(seg) < SPUR_MIN:             # post-merge dust
            continue
        py = np.array([p[0] for p in seg]); px = np.array([p[1] for p in seg])
        w = float(np.median(dist[py, px])) * 2.0
        w = max(1.2, min(24.0, round(w, 1)))
        col = np.median(bcol[py, px], axis=0)
        fillc = "#%02x%02x%02x" % tuple(int(v) for v in col)
        pts = np.stack([px, py], 1).astype(np.int32).reshape(-1, 1, 2)
        ap = cv2.approxPolyDP(pts, max(0.5, eps), False)[:, 0, :]
        if len(ap) < 2:
            continue
        d = "M" + "L".join(f"{x} {y}" for x, y in ap)
        out.append(f'<path d="{d}" fill="none" stroke="{fillc}" '
                   f'stroke-width="{w}" stroke-linecap="round" '
                   f'stroke-linejoin="round"/>')
    return out


@app.post("/api/edgelab")
def edgelab(req: EdgeLabReq):
    """Edge-lab playground: edge-1's boundary-first raster prototype with
    tinkerable params. Returns base64 PNGs of the three stages (edges /
    bucket fills / composite) computed in-process (~1-2 s)."""
    import base64

    import cv2
    import numpy as np
    from scipy import ndimage

    image = INPUTS / Path(req.image).name
    if not image.exists():
        raise HTTPException(404, f"unknown image {req.image!r}")
    t0 = time.time()
    img = cv2.cvtColor(cv2.imread(str(image), cv2.IMREAD_COLOR),
                       cv2.COLOR_BGR2RGB)
    wd = max(256, min(2304, int(req.work_dim)))
    s = wd / max(img.shape[:2])
    work = cv2.resize(img, (round(img.shape[1] * s), round(img.shape[0] * s)),
                      interpolation=cv2.INTER_AREA)
    if req.pre == "gaussian" and req.pre_strength > 0:
        k = 2 * int(req.pre_strength) + 1
        work = cv2.GaussianBlur(work, (k, k), 0)
    elif req.pre == "bilateral" and req.pre_strength > 0:
        sig = 25 * int(req.pre_strength)
        work = cv2.bilateralFilter(work, 9, sig, sig)
    H, W = work.shape[:2]
    lab = cv2.cvtColor(work, cv2.COLOR_RGB2LAB).astype(np.float32)

    # 1. boundary mask (edge-1's rule: pixel differs from right/down neighbour)
    thr = float(req.threshold)
    bnd = np.zeros((H, W), bool)
    dh = np.sqrt(((lab[:, 1:] - lab[:, :-1]) ** 2).sum(2))
    bnd[:, :-1] |= dh > thr; bnd[:, 1:] |= dh > thr
    dv = np.sqrt(((lab[1:, :] - lab[:-1, :]) ** 2).sum(2))
    bnd[:-1, :] |= dv > thr; bnd[1:, :] |= dv > thr
    # 2. join: morphological close makes the cell walls watertight
    if req.close_k >= 3:
        k = int(req.close_k) | 1
        bndc = cv2.morphologyEx(bnd.astype(np.uint8), cv2.MORPH_CLOSE,
                                np.ones((k, k), np.uint8)).astype(bool)
    else:
        bndc = bnd
    # 3. cells = connected components of non-boundary
    ncell, cells = cv2.connectedComponents((~bndc).astype(np.uint8),
                                           connectivity=4)
    # 3b. dissolve tiny cells (their px backfill from the nearest live cell)
    if req.min_cell > 0:
        counts = np.bincount(cells.ravel(), minlength=ncell)
        tiny = counts < int(req.min_cell)
        tiny[0] = False                      # label 0 = the boundary itself
        cells[tiny[cells]] = 0
    # 3c. INK extraction (Recraft-style): dark AND thin pixels form the ink
    # layer. Their px leave the cell partition entirely, so the backfill
    # extends the surrounding fills UNDERNEATH the ink (layered overdraw) —
    # this also stops thin dark line-interiors becoming confetti cells.
    ink_mask = None
    if req.ink:
        lum_w = (0.299 * work[:, :, 0] + 0.587 * work[:, :, 1]
                 + 0.114 * work[:, :, 2])
        darkm = (lum_w < 80).astype(np.uint8)
        half = cv2.distanceTransform(darkm, cv2.DIST_L2, 3)
        maxhalf = 10.0 * max(H, W) / 2048.0
        ink_mask = darkm.astype(bool) & (half < maxhalf)
        cells[ink_mask] = 0
    # 4. bucket fill each cell with its mean colour; backfill boundary px
    flat = work.reshape(-1, 3).astype(np.float64)
    cl = cells.ravel()
    cnt = np.maximum(np.bincount(cl, minlength=ncell), 1)
    mean = np.stack([np.bincount(cl, weights=flat[:, c], minlength=ncell) / cnt
                     for c in range(3)], 1).astype(np.uint8)
    fillimg = mean[cells]
    idx = ndimage.distance_transform_edt(cells == 0, return_distances=False,
                                         return_indices=True)
    fill_full = fillimg[tuple(idx)]
    # 5. edge colour = darkest neighbour (ink stays black)
    lum = (0.299 * work[:, :, 0] + 0.587 * work[:, :, 1]
           + 0.114 * work[:, :, 2])
    shifts = [np.roll(work, 1, 0), np.roll(work, -1, 0),
              np.roll(work, 1, 1), np.roll(work, -1, 1)]
    lums = [np.roll(lum, 1, 0), np.roll(lum, -1, 0),
            np.roll(lum, 1, 1), np.roll(lum, -1, 1)]
    darkest = np.argmin(np.stack(lums, 0), 0)
    bcol = np.choose(darkest[..., None].repeat(3, 2), shifts)
    # 6. stage renders
    edges = np.full((H, W, 3), 255, np.uint8)
    edges[bndc] = (0, 0, 0)
    composite = fill_full.copy()
    composite[bndc] = bcol[bndc]

    # 7. SVG stage: exactly ONE <path> per bucket cell. Vectorize the
    # BACKFILLED partition (every wall px assigned to its nearest cell), so
    # the paths tile the canvas watertight — no gaps where the walls were.
    cells_full = cells[tuple(idx)]
    eps = max(0.0, float(req.svg_eps))
    counts_full = np.bincount(cells_full.ravel(), minlength=ncell)
    slices = ndimage.find_objects(cells_full)
    svg_paths = []
    for lab_id in np.argsort(-counts_full):
        if lab_id == 0 or counts_full[lab_id] == 0:
            continue
        sl = slices[lab_id - 1]
        if sl is None:
            continue
        y0, x0 = sl[0].start, sl[1].start
        m = (cells_full[sl] == lab_id).astype(np.uint8)
        cs, _ = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        subs = []
        for c in cs:
            if len(c) < 3 or cv2.contourArea(c) < 3:
                continue
            ap = cv2.approxPolyDP(c, eps, True) if eps > 0 else c
            if len(ap) < 3:
                continue
            pts = ap[:, 0, :]
            d = "M" + "L".join(f"{x + x0} {y + y0}" for x, y in pts) + "Z"
            subs.append(d)
        if not subs:
            continue
        fill = "#%02x%02x%02x" % tuple(int(v) for v in mean[lab_id])
        svg_paths.append(f'<path d="{"".join(subs)}" fill="{fill}" '
                         f'fill-rule="evenodd"/>')
    # ink ribbons: one FILLED path per connected ink component (outer contour
    # + holes, evenodd) — how Recraft draws lines (verified on their targets:
    # long continuous ribbon fills, junction-branching included, no strokes)
    ink_paths = []
    if ink_mask is not None and ink_mask.any():
        n_i, ilab, istats, _ = cv2.connectedComponentsWithStats(
            ink_mask.astype(np.uint8), 8)
        order = np.argsort(-istats[1:, cv2.CC_STAT_AREA]) + 1
        srcf = work.astype(np.float64)
        for j in order:
            if istats[j, cv2.CC_STAT_AREA] < 40:
                break
            x0, y0 = istats[j, cv2.CC_STAT_LEFT], istats[j, cv2.CC_STAT_TOP]
            wj, hj = istats[j, cv2.CC_STAT_WIDTH], istats[j, cv2.CC_STAT_HEIGHT]
            m = (ilab[y0:y0 + hj, x0:x0 + wj] == j).astype(np.uint8)
            cs, _h = cv2.findContours(m, cv2.RETR_CCOMP,
                                      cv2.CHAIN_APPROX_SIMPLE)
            subs = []
            for c in cs:
                if len(c) < 3 or cv2.contourArea(c) < 3:
                    continue
                ap = cv2.approxPolyDP(c, eps, True) if eps > 0 else c
                if len(ap) < 3:
                    continue
                subs.append("M" + "L".join(
                    f"{x + x0} {y + y0}" for x, y in ap[:, 0, :]) + "Z")
            if not subs:
                continue
            med = np.median(srcf[ilab == j], axis=0)
            fillc = "#%02x%02x%02x" % tuple(int(v) for v in med)
            ink_paths.append(f'<path d="{"".join(subs)}" fill="{fillc}" '
                             f'fill-rule="evenodd"/>')
    svg_text = (f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'viewBox="0 0 {W} {H}">' + "".join(svg_paths)
                + "".join(ink_paths) + "</svg>")

    def png64(a):
        ok, buf = cv2.imencode(".png", cv2.cvtColor(a, cv2.COLOR_RGB2BGR))
        return "data:image/png;base64," + base64.b64encode(buf).decode()

    live = int((np.bincount(cells.ravel(), minlength=ncell)[1:] > 0).sum())
    return {"edges": png64(edges), "fills": png64(fill_full),
            "composite": png64(composite), "svg": svg_text,
            "stats": {"boundary_px": int(bndc.sum()), "cells": live,
                      "dim": f"{W}x{H}",
                      "svg_paths": len(svg_paths),
                      "ink_paths": len(ink_paths),
                      "svg_kb": len(svg_text) // 1024,
                      "seconds": round(time.time() - t0, 2)}}


app.mount("/inputs", StaticFiles(directory=str(INPUTS)), name="inputs")
app.mount("/targets", StaticFiles(directory=str(TARGETS)), name="targets")
app.mount("/", StaticFiles(directory=str(ROOT / "frontend"), html=True), name="ui")
