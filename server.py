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


app.mount("/inputs", StaticFiles(directory=str(INPUTS)), name="inputs")
app.mount("/targets", StaticFiles(directory=str(TARGETS)), name="targets")
app.mount("/", StaticFiles(directory=str(ROOT / "frontend"), html=True), name="ui")
