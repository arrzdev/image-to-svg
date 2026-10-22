"""LOCKED eval harness for the autoresearch loop — DO NOT EDIT DURING THE LOOP.

This is the *regression sanity check* only, NOT the keep/discard gate. Per
docs/PROJECT_SPEC.md §4, the real keep/discard decision is the agent's EYE
verdict on `tb.crops({...})`. This script exists so the plugin's dashboard has
`METRIC name=number` lines and so external regressions get caught after an eye
verdict has already passed. It renders the current pipeline for the focus
target, writes the SHA+timestamp deliverable (spec §5), and prints metrics.

Why locked: an agent that can edit what/how the metric is measured will
eventually game its own scorer (see autoresearch.md "Off Limits"). The loop
proposes changes to the SVG *pipeline*, never to this file, testbed.py, or
metrics.py.

Usage:  ar_eval.py [FOCUS_BASENAME] [SEED]
        FOCUS defaults to the contents of `autoresearch.focus`, else 'elephant'.
Emits:  METRIC quality=… / METRIC ssim=… / METRIC ms_ssim=… / METRIC points=… …
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

# repo root = nearest ancestor holding data/inputs (engines/quant/quant-hifi/src -> repo)
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "data" / "inputs").is_dir())


def _focus_target() -> str:
    if len(sys.argv) > 1 and sys.argv[1]:
        return sys.argv[1]
    f = ROOT / "research" / "loop" / "autoresearch.focus"
    if f.exists():
        name = f.read_text().strip()
        if name:
            return name
    return "elephant"


def _short_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "--short=7", "HEAD"],
            text=True).strip()
    except Exception:
        return "nogit"


def _count_points(svg: str) -> int:
    """Cheap anchor-point proxy: coordinate pairs across all path data."""
    import re
    total = 0
    for d in re.findall(r'\sd="([^"]*)"', svg):
        total += len(re.findall(r'-?\d*\.?\d+(?:e-?\d+)?', d)) // 2
    return total


def main() -> int:
    # Deterministic: fix seeds so re-runs reproduce (harness reproducibility).
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    os.environ.setdefault("PYTHONHASHSEED", str(seed))
    try:
        import numpy as np
        np.random.seed(seed)
    except Exception:
        pass

    name = _focus_target()
    from pipelines import get_pipeline
    from svgutil import fit_svg_size
    from testbed import Testbed

    tb = Testbed(f"{name}.jpg") if (ROOT / "data" / "inputs" / f"{name}.jpg").exists() \
        else Testbed(f"{name}.png") if (ROOT / "data" / "inputs" / f"{name}.png").exists() \
        else Testbed(name)
    pp, _, (ow, oh), _ = tb.prep()

    t0 = time.time()
    svg = fit_svg_size(get_pipeline("contour_lines").run(pp, {}), ow, oh)
    render_s = time.time() - t0

    # Write the traceable deliverable: data/outputs/{name}-{sha}-{ts}.svg (spec §5).
    sha = _short_sha()
    ts = time.strftime("%Y%m%dT%H%M%S")
    out_dir = ROOT / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    deliverable = out_dir / f"{tb.name}-{sha}-{ts}.svg"
    deliverable.write_text(svg)

    m = tb.score(svg)  # cached perceptual metrics (sanity only)
    points = _count_points(svg)

    # METRIC lines for the plugin dashboard. `quality` is the primary field the
    # JSONL logs, but per spec §4 it is NOT the keep/discard gate.
    print(f"METRIC quality={m.get('quality')}")
    print(f"METRIC ssim={m.get('ssim')}")
    print(f"METRIC ms_ssim={m.get('ms_ssim')}")
    print(f"METRIC psnr={m.get('psnr')}")
    print(f"METRIC delta_e={m.get('delta_e')}")
    print(f"METRIC points={points}")
    print(f"METRIC render_s={render_s:.2f}")
    print(f"# focus={tb.name} sha={sha} deliverable={deliverable.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
