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
    image: str
    work_dim: int = 1536
    pre: str = "none"          # none | gaussian | bilateral
    pre_strength: int = 3      # gaussian: kernel radius; bilateral: sigma/25
    threshold: float = 14.0    # Lab dE boundary trigger
    close_k: int = 3           # join kernel (0 = no join)
    min_cell: int = 0          # dissolve cells smaller than this (px)


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

    def png64(a):
        ok, buf = cv2.imencode(".png", cv2.cvtColor(a, cv2.COLOR_RGB2BGR))
        return "data:image/png;base64," + base64.b64encode(buf).decode()

    live = int((np.bincount(cells.ravel(), minlength=ncell)[1:] > 0).sum())
    return {"edges": png64(edges), "fills": png64(fill_full),
            "composite": png64(composite),
            "stats": {"boundary_px": int(bndc.sum()), "cells": live,
                      "dim": f"{W}x{H}",
                      "seconds": round(time.time() - t0, 2)}}


app.mount("/inputs", StaticFiles(directory=str(INPUTS)), name="inputs")
app.mount("/targets", StaticFiles(directory=str(TARGETS)), name="targets")
app.mount("/", StaticFiles(directory=str(ROOT / "frontend"), html=True), name="ui")
