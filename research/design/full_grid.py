"""Render all 11 targets: ours (left) vs Recraft (right), stacked into one grid
for a visual record of the current version. Usage: python full_grid.py <version>
"""
import glob
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                "models", "quant-11", "src"))
import numpy as np
from render import svg_to_rgb
from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
version = sys.argv[1] if len(sys.argv) > 1 else "quant-12"
out = sys.argv[2] if len(sys.argv) > 2 else f"/tmp/{version}_grid.png"

spec = importlib.util.spec_from_file_location(
    "e", os.path.join(ROOT, "models", version, "entry.py"))
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)

S = 300
targets = sorted(glob.glob(os.path.join(ROOT, "data", "targets", "*.svg")))
rows = []
for tp in targets:
    stem = os.path.splitext(os.path.basename(tp))[0]
    inp = None
    for ext in (".jpg", ".png", ".jpeg", ".webp"):
        c = os.path.join(ROOT, "data", "inputs", stem + ext)
        if os.path.exists(c):
            inp = c
            break
    if inp is None:
        continue
    ttxt = open(tp).read()
    if not ttxt.lstrip().startswith("<"):
        continue
    our = svg_to_rgb(e.run(inp), S, S)
    rec = svg_to_rgb(ttxt, S, S)
    strip = np.full((S, S * 2 + 6, 3), 30, np.uint8)
    strip[:, :S] = our
    strip[:, S + 6:] = rec
    rows.append((stem, strip))
    print("rendered", stem)

cols = 2
n = len(rows)
rh = (n + cols - 1) // cols
cell_w = S * 2 + 6
grid = np.full((rh * (S + 20), cols * (cell_w + 10), 3), 15, np.uint8)
for i, (stem, strip) in enumerate(rows):
    r, c = i % rh, i // rh
    y = r * (S + 20) + 20
    x = c * (cell_w + 10)
    grid[y:y + S, x:x + cell_w] = strip
Image.fromarray(grid).save(out)
print("saved", out)
