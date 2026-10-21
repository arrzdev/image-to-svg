#!/usr/bin/env python3
"""Run any engine version on an image.

    python run_model.py --model quant-hifi --image data/inputs/elephant.jpg
    python run_model.py -m staged -i data/inputs/chopchop.png -o out.svg
    python run_model.py --list

Every version lives in models/<v>/ with the same entry contract
(entry.py: run(image_path, params=None) -> svg string), so versions route
non-destructively however different their internals are. Each run happens in
its own subprocess — version sources share module names, so two versions can
never be imported into one interpreter.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
PYTHON = ROOT / ".venv" / "bin" / "python"
ALIASES = {"staged": "quant-hifi"}   # the current best engine


def versions() -> list[str]:
    return sorted(p.parent.name for p in MODELS.glob("*/entry.py"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-m", "--model", help="version to run (see --list)")
    ap.add_argument("-i", "--image", help="input raster (png/jpg)")
    ap.add_argument("-o", "--out", help="output svg path "
                    "(default: data/outputs/<image>-<model>-<timestamp>.svg)")
    ap.add_argument("--list", action="store_true", help="list runnable versions")
    args = ap.parse_args()

    if args.list or not (args.model and args.image):
        print("runnable versions:", ", ".join(versions()))
        print("aliases:", ", ".join(f"{a} -> {v}" for a, v in ALIASES.items()))
        return 0 if args.list else 2

    entry = MODELS / ALIASES.get(args.model, args.model) / "entry.py"
    if not entry.exists():
        sys.exit(f"unknown model {args.model!r} — runnable: {', '.join(versions())}")
    image = Path(args.image)
    if not image.exists():
        sys.exit(f"no such image: {image}")

    out = Path(args.out) if args.out else (
        ROOT / "data" / "outputs" /
        f"{image.stem}-{args.model}-{time.strftime('%Y%m%d-%H%M%S')}.svg")
    out.parent.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")
    python = PYTHON if PYTHON.exists() else Path(sys.executable)
    t0 = time.time()
    r = subprocess.run([str(python), str(entry), str(image), str(out)], env=env)
    if r.returncode != 0:
        sys.exit(r.returncode)
    print(f"{out}  ({out.stat().st_size//1024} KB, {time.time()-t0:.1f}s, {args.model})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
