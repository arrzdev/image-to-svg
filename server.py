"""Minimal version-testing frontend for the image→SVG engine.

    ./run.sh            # http://127.0.0.1:8000

Pick an image, pick a version, Run — the page shows ORIGINAL | OUTPUT | TARGET
(Recraft reference, when one exists). Every run goes through the same stable
entry contract (models/<v>/entry.py) in an isolated subprocess, exactly like
`python run_model.py`.

The Edge Lab tab (/api/edgelab) runs models/edge-10/src/pipeline.py IN-PROCESS
with full param passthrough — the lab and the edge-10 model are the same code.
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
    """Full param passthrough to models/edge-10/src/pipeline.py — defaults
    mirror the model's DEFAULTS (the USER's frozen recipe)."""
    image: str
    work_dim: int = 2048
    svg_eps: float = 1.0
    curve_fit: bool = True
    pre: str = "bilateral"
    pre_strength: int = 1
    threshold: float = 5.0
    close_k: int = 0
    min_cell: int = 0
    merge_de: float = 22.0
    ink: bool = True
    ink_strength: int = 0
    ink_lmax: float = 30.0
    ink_cmax: float = 100.0
    ink_threshold: float = 0.0
    ink_close: int = 0


@app.post("/api/edgelab")
def edgelab(req: EdgeLabReq):
    import base64

    import cv2

    image = INPUTS / Path(req.image).name
    if not image.exists():
        raise HTTPException(404, f"unknown image {req.image!r}")
    src = str(MODELS / "edge-10" / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    import pipeline as edge10

    t0 = time.time()
    params = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    params.pop("image")
    res = edge10.process(str(image), params)

    def png64(a):
        ok, buf = cv2.imencode(".png", cv2.cvtColor(a, cv2.COLOR_RGB2BGR))
        return "data:image/png;base64," + base64.b64encode(buf).decode()

    stats = dict(res["stats"])
    stats["seconds"] = round(time.time() - t0, 2)
    return {"edges": png64(res["edges"]), "fills": png64(res["fills"]),
            "composite": png64(res["composite"]), "svg": res["svg"],
            "stats": stats}


app.mount("/inputs", StaticFiles(directory=str(INPUTS)), name="inputs")
app.mount("/targets", StaticFiles(directory=str(TARGETS)), name="targets")
app.mount("/", StaticFiles(directory=str(ROOT / "frontend"), html=True), name="ui")
