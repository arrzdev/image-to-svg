"""Module-level worker for the process-pool sweep.

Multiprocessing requires the worker fn and its data to be picklable, so the job
is a fully self-describing tuple of primitives + file paths (no closures, no big
numpy arrays over the wire). Each worker process decodes eval images from disk
once and caches them, so repeated configs on the same image don't re-decode.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from pipelines import get_pipeline
from svgutil import fit_svg_size
import metrics as M

_EVAL_CACHE = {}


def init_worker():
    """Pool initializer: pin OpenCV to one thread inside each worker."""
    try:
        import cv2
        cv2.setNumThreads(1)
    except Exception:
        pass


def _eval_array(path: str) -> np.ndarray:
    arr = _EVAL_CACHE.get(path)
    if arr is None:
        arr = np.asarray(Image.open(path).convert("RGB"))
        _EVAL_CACHE[path] = arr
    return arr


def run_job(job):
    """job = (tag, pipeline_id, params, proc_path, eval_path, orig_w, orig_h
              [, simplify_eps[, return_svg]])."""
    tag, pid, params, proc_path, eval_path, ow, oh = job[:7]
    eps = job[7] if len(job) > 7 else 0.0
    return_svg = bool(job[8]) if len(job) > 8 else False
    try:
        svg = get_pipeline(pid).run(proc_path, params)
        if eps and eps > 0:
            from postprocess import simplify_svg
            svg = simplify_svg(svg, eps)
        svg = fit_svg_size(svg, ow, oh)
        m = M.all_metrics(svg, _eval_array(eval_path))
        out = {"tag": tag, "metrics": m}
        if return_svg:
            out["svg"] = svg
        return out
    except Exception as e:
        return {"tag": tag, "error": str(e)}
