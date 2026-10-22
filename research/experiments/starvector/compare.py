#!/usr/bin/env python3
"""
Side-by-side: source raster | rendered SVG. Writes a PNG for eyeballing.

    python compare.py rabbit.jpg out_rabbit.svg -o compare.png

Renders with resvg when it is on PATH (matches the rest of this repo's
tooling), else falls back to cairosvg.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


def render_svg(svg_path, size):
    if shutil.which("resvg"):
        out = Path(tempfile.mkdtemp()) / "r.png"
        r = subprocess.run(
            ["resvg", "-w", str(size), "-h", str(size), str(svg_path), str(out)],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and out.exists():
            return Image.open(out).convert("RGB"), "resvg"
        print(f"resvg failed: {r.stderr.strip()[:300]}", file=sys.stderr)

    import cairosvg
    out = Path(tempfile.mkdtemp()) / "c.png"
    cairosvg.svg2png(url=str(svg_path), write_to=str(out),
                     output_width=size, output_height=size)
    return Image.open(out).convert("RGB"), "cairosvg"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("svg")
    ap.add_argument("-o", "--output", default="compare.png")
    ap.add_argument("--size", type=int, default=512)
    args = ap.parse_args()

    src = Image.open(args.source).convert("RGB")
    # Pad to square the same way SimpleStarVectorProcessor does, so the two
    # panels are geometrically comparable.
    m = max(src.size)
    sq = Image.new("RGB", (m, m), (255, 255, 255))
    sq.paste(src, ((m - src.size[0]) // 2, (m - src.size[1]) // 2))
    src = sq.resize((args.size, args.size), Image.LANCZOS)

    svg_img, backend = render_svg(args.svg, args.size)

    pad, label = 8, 24
    canvas = Image.new("RGB", (args.size * 2 + pad * 3, args.size + pad * 2 + label),
                       (240, 240, 240))
    canvas.paste(src, (pad, pad + label))
    canvas.paste(svg_img, (args.size + pad * 2, pad + label))
    d = ImageDraw.Draw(canvas)
    d.text((pad, pad), "source", fill=(0, 0, 0))
    d.text((args.size + pad * 2, pad), f"svg via {backend}", fill=(0, 0, 0))
    canvas.save(args.output)

    n = Path(args.svg).read_text()
    print(f"wrote {args.output}  |  svg: {len(n)} bytes, "
          f"{n.count('<path')} paths, {n.count('<')} elements  |  render: {backend}")


if __name__ == "__main__":
    main()
