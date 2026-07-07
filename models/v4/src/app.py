"""Image -> SVG playground: FastAPI backend + static frontend.

Endpoints:
  GET  /                  -> frontend
  GET  /api/pipelines     -> pipeline list + param schemas + AI status
  POST /api/vectorize     -> run one or more pipelines on an uploaded image
  GET  /api/samples       -> list bundled sample images
  GET  /samples/<file>    -> sample image bytes
"""
from __future__ import annotations

import base64
import io
import os
import time
import traceback
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

import metrics as metrics_mod
from ai import gemini
from pipelines import get_pipeline, list_pipelines
from svgutil import fit_svg_size
from postprocess import simplify_svg
from svgopt import optimize_svg

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
SAMPLES = ROOT / "samples"
SCRATCH = ROOT / "outputs"
SCRATCH.mkdir(exist_ok=True)

app = FastAPI(title="image-to-svg playground")


# Default tracing resolution. We vectorize a downscaled raster (denser pixels
# smooth noise + faster) and stamp the ORIGINAL size back onto the SVG, which is
# resolution-independent. Hard ceiling guards against pathological inputs.
DEFAULT_PROCESS_DIM = 2048
MAX_PROCESS_DIM = 4096

# Metrics are scored against the image downscaled to this size (NOT the trace
# input), so a low "Trace at" is honestly penalized: the SVG is rendered at this
# resolution, revealing faceting/detail loss that a proc-resolution score hides.
EVAL_DIM = 1536


def _flatten_white(image_bytes: bytes) -> Image.Image:
    """Load, composite transparency over WHITE, return RGB at native size.

    Transparent PNGs otherwise become black after a naive .convert('RGB')
    (alpha dropped, RGB left at 0,0,0), which quantizers trace as a big black
    region; compositing over white matches the preview and the metric renderer.
    """
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img)
    return img.convert("RGB")


# Max upscale factor for small inputs. Measured on 626px sources: 2x Lanczos
# before tracing lifts quality substantially (fox 0.870 -> 0.925) by giving the
# tracer denser pixels to fit; beyond 2x returns diminish or reverse.
MAX_UPSCALE = 2.0


def _rescale(img: Image.Image, target: int, allow_upscale: bool = False) -> Image.Image:
    w, h = img.size
    scale = target / max(w, h)
    if scale > 1.0:
        scale = min(scale, MAX_UPSCALE) if allow_upscale else 1.0
    if abs(scale - 1.0) < 1e-6:
        return img
    return img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)


def _prepare(image_bytes: bytes, process_dim: int):
    """Return (proc_image, eval_image, (orig_w, orig_h)).

    proc_image is the (downscaled) raster we trace; eval_image is the target we
    score against — a higher, fixed-resolution view of the original so metrics
    reflect fidelity to the original, not to the downscaled trace input.
    """
    base = _flatten_white(image_bytes)
    orig_w, orig_h = base.size
    target = max(16, min(int(process_dim), MAX_PROCESS_DIM))
    # Trace raster may be UPSCALED for small sources (denser pixels = smoother,
    # more faithful curve fits) — but NOT for flat/crisp art: Lanczos ringing
    # around hard edges gets traced as thousands of junk points (see imgstats).
    # The eval target is never upscaled (score vs the real thing).
    allow_up = True
    if target > max(orig_w, orig_h):
        from imgstats import analyze
        allow_up = analyze(np.asarray(base))["kind"] != "flat"
    proc = _rescale(base, target, allow_upscale=allow_up)
    eval_img = _rescale(base, EVAL_DIM, allow_upscale=False)
    return proc, eval_img, (orig_w, orig_h)


def _write_temp(img: Image.Image) -> Path:
    # Persist to disk since some tracers (vtracer, potrace) need a file path.
    path = SCRATCH / f"input_{int(time.time()*1000)}.png"
    img.save(path)
    return path


@app.get("/api/pipelines")
def api_pipelines():
    return {"pipelines": list_pipelines(), "ai": gemini.status()}


@app.get("/api/samples")
def api_samples():
    if not SAMPLES.exists():
        return {"samples": []}
    files = sorted(p.name for p in SAMPLES.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
    return {"samples": files}


@app.get("/samples/{name}")
def api_sample_file(name: str):
    path = SAMPLES / name
    if not path.exists() or path.parent != SAMPLES:
        raise HTTPException(404, "sample not found")
    return FileResponse(path)


@app.post("/api/vectorize")
async def api_vectorize(
    image: Optional[UploadFile] = File(None),
    sample: Optional[str] = Form(None),
    pipelines: str = Form(...),          # comma-separated pipeline ids
    params_json: str = Form("{}"),       # {pipeline_id: {param: value}}
    ai_preprocess: Optional[str] = Form(None),  # prompt key, or None
    process_dim: int = Form(DEFAULT_PROCESS_DIM),  # tracing resolution (long side)
    simplify_eps: float = Form(0.0),     # post-trace simplification strength (px, 0 = off)
):
    import json

    if image is not None:
        image_bytes = await image.read()
    elif sample:
        spath = SAMPLES / sample
        if not spath.exists() or spath.parent != SAMPLES:
            raise HTTPException(400, "unknown sample")
        image_bytes = spath.read_bytes()
    else:
        raise HTTPException(400, "provide an image upload or a sample name")

    ai_info = None
    if ai_preprocess:
        try:
            processed = gemini.preprocess(image_bytes, ai_preprocess)
            image_bytes = processed
            ai_info = {"applied": True, "prompt": ai_preprocess, "model": gemini.MODEL}
        except Exception as e:
            ai_info = {"applied": False, "error": str(e)}

    proc_img, eval_img, (orig_w, orig_h) = _prepare(image_bytes, process_dim)
    source_rgb = np.asarray(eval_img)           # score against the original view
    proc_w, proc_h = proc_img.size
    input_path = _write_temp(proc_img)

    try:
        param_map = json.loads(params_json or "{}")
    except json.JSONDecodeError:
        param_map = {}

    pipeline_ids = [pid.strip() for pid in pipelines.split(",") if pid.strip()]
    results = []
    for pid in pipeline_ids:
        entry = {"pipeline": pid}
        t0 = time.perf_counter()
        try:
            pipe = get_pipeline(pid)
            svg = pipe.run(str(input_path), param_map.get(pid, {}))
            # Optional trace-then-simplify: trade fidelity for editability as an
            # explicit post stage; metrics score the simplified result.
            if simplify_eps > 0:
                svg = simplify_svg(svg, simplify_eps)
            # Stamp the original size back on (viewBox stays in processing coords
            # so it scales up cleanly). Metric rendering forces the eval size, so
            # scores are unaffected by the declared width/height.
            svg = fit_svg_size(svg, orig_w, orig_h)
            svg = optimize_svg(svg)   # lossless output shrink (~20-35%)
            entry["ms"] = round((time.perf_counter() - t0) * 1000, 1)
            entry["svg"] = svg
            entry["metrics"] = metrics_mod.all_metrics(svg, source_rgb)
            entry["ok"] = True
        except Exception as e:
            entry["ok"] = False
            entry["ms"] = round((time.perf_counter() - t0) * 1000, 1)
            entry["error"] = f"{e}"
            entry["trace"] = traceback.format_exc()
        results.append(entry)

    # clean up temp input
    try:
        input_path.unlink()
    except OSError:
        pass

    buf = io.BytesIO()
    eval_img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return JSONResponse({
        "source": {
            "width": orig_w, "height": orig_h,          # SVGs render at this size
            "proc_width": proc_w, "proc_height": proc_h,  # traced at this size
            "data_url": f"data:image/png;base64,{b64}",
        },
        "ai": ai_info,
        "results": results,
    })


@app.post("/api/optimize")
async def api_optimize(
    image: Optional[UploadFile] = File(None),
    sample: Optional[str] = Form(None),
    pipeline: str = Form("vtracer"),
    mode: str = Form("fidelity"),        # fidelity | balanced | editable
    budget: int = Form(48),
):
    """Auto-optimize: coordinate ascent over params+resolution+simplify for
    THIS image; returns the winning config and its SVG."""
    import optimize as opt  # lazy: optimize imports app at module load

    if image is not None:
        image_bytes = await image.read()
    elif sample:
        spath = SAMPLES / sample
        if not spath.exists() or spath.parent != SAMPLES:
            raise HTTPException(400, "unknown sample")
        image_bytes = spath.read_bytes()
    else:
        raise HTTPException(400, "provide an image upload or a sample name")

    lam = {"fidelity": 0.0, "balanced": 0.03, "editable": 0.06}.get(mode, 0.0)
    budget = max(8, min(int(budget), 120))
    try:
        res = opt.optimize_bytes(image_bytes, pipeline=pipeline, lam=lam, budget=budget)
    except Exception as e:
        raise HTTPException(500, f"optimize failed: {e}")

    # Same shape the frontend uses for /api/vectorize results.
    _, eval_img, (ow, oh) = _prepare(image_bytes, res["best"]["process_dim"])
    buf = io.BytesIO()
    eval_img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return JSONResponse({
        "source": {"width": ow, "height": oh,
                   "proc_width": res["best"]["process_dim"], "proc_height": res["best"]["process_dim"],
                   "data_url": f"data:image/png;base64,{b64}"},
        "ai": None,
        "results": [{
            "pipeline": f"auto:{pipeline} ({mode})",
            "ok": True,
            "ms": res["seconds"] * 1000,
            "svg": res["svg"],
            "metrics": res["metrics"],
            "config": res["best"],
            "evals": res["evals"],
        }],
    })


@app.post("/api/tournament")
async def api_tournament(
    image: Optional[UploadFile] = File(None),
    sample: Optional[str] = Form(None),
    mode: str = Form("fidelity"),
    top: int = Form(5),
    refine: bool = Form(False),
    dv: bool = Form(False),        # DiffVG post-refine winner (low-complexity only)
):
    """Tournament: run a diverse candidate portfolio, return the leaderboard."""
    import engine  # lazy: engine imports app at module load

    if image is not None:
        image_bytes = await image.read()
    elif sample:
        spath = SAMPLES / sample
        if not spath.exists() or spath.parent != SAMPLES:
            raise HTTPException(400, "unknown sample")
        image_bytes = spath.read_bytes()
    else:
        raise HTTPException(400, "provide an image upload or a sample name")

    try:
        res = engine.tournament(image_bytes, mode=mode, top_n=max(1, min(top, 10)),
                                refine=refine, dv=dv)
    except Exception as e:
        raise HTTPException(500, f"tournament failed: {e}")

    _, eval_img, (ow, oh) = _prepare(image_bytes, DEFAULT_PROCESS_DIM)
    buf = io.BytesIO()
    eval_img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    results = []
    for r in res["board"]:
        results.append({
            "pipeline": f"🏆 {r['label']}",
            "ok": True,
            "ms": 0,
            "svg": r["svg"],
            "metrics": r["metrics"],
            "config": {**r["params"], "process_dim": r["process_dim"],
                       "simplify_eps": r["simplify_eps"], "pipeline": r["pipeline"]},
        })
    return JSONResponse({
        "source": {"width": ow, "height": oh, "data_url": f"data:image/png;base64,{b64}",
                   "proc_width": ow, "proc_height": oh},
        "ai": None,
        "analysis": res["analysis"],
        "seconds": res["seconds"],
        "results": results,
    })


# Serve the frontend at the root. Mounted last so /api/* wins.
app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
