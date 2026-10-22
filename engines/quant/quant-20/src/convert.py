"""The product face of the engine: one command, image in, best SVG out.

    python backend/convert.py input.png                     # balanced
    python backend/convert.py input.png -o out.svg --mode fidelity --dv
    python backend/convert.py *.png --mode editable         # batch

Runs the full pipeline per image: analyze -> candidate tournament -> optional
DiffVG refinement -> lossless output optimization -> write winner.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main():
    ap = argparse.ArgumentParser(description="image -> best SVG (tournament engine)")
    ap.add_argument("images", nargs="+", help="input raster image(s)")
    ap.add_argument("-o", "--output", default=None,
                    help="output path (single input only; default: alongside input)")
    ap.add_argument("--mode", default="balanced",
                    choices=["fidelity", "balanced", "editable", "grail", "fast"])
    ap.add_argument("--dv", action="store_true",
                    help="DiffVG-refine the winner (needs the diffvg build)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.output and len(args.images) > 1:
        sys.exit("-o only works with a single input")

    import engine

    # default destination: data/outputs/{name}-{algoVersion}-{timestamp}.svg
    # (algoVersion = current git short sha, so every deliverable is traceable
    # to the exact engine that made it). -o overrides for a single input.
    from datetime import datetime
    import subprocess
    OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "outputs"
    try:
        ver = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(OUT_DIR.parent.parent), stderr=subprocess.DEVNULL
        ).decode().strip() or "nogit"
    except Exception:
        ver = "nogit"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    failures = 0
    for img in args.images:
        p = Path(img)
        if not p.exists():
            print(f"skip (not found): {img}", file=sys.stderr)
            failures += 1
            continue
        if args.output:
            out = Path(args.output)
        else:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            out = OUT_DIR / f"{p.stem}-{ver}-{stamp}.svg"
        t0 = time.time()
        try:
            res = engine.tournament(p.read_bytes(), mode=args.mode, top_n=1, dv=args.dv)
            if not res["board"]:
                raise RuntimeError("no candidate succeeded")
            w = res["board"][0]
            out.write_text(w["svg"])
            if not args.quiet:
                m = w["metrics"]
                print(f"{p.name} -> {out}  [{w['label']}]  quality={m['quality']} "
                      f"points={m['num_points']} gzip={m['gzip_bytes']//1024}KB "
                      f"({time.time()-t0:.1f}s, {res['analysis']['kind']})")
        except Exception as e:
            print(f"FAILED {p.name}: {e}", file=sys.stderr)
            failures += 1
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
