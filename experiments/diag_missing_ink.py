"""Run 2 diagnostic B: find MISSING INK — places where the source's dark line
network is not covered by the v4 render. Clusters of uncovered dark pixels =
crossing gaps / dropped stubs / cap shortfalls. Rank by size, crop the top.
"""
import sys
sys.path.insert(0, "backend")
import numpy as np
from scipy import ndimage

from testbed import Testbed
from strokes import _luminance, _STRUCT8
from render import svg_to_rgb

tb = Testbed("elephant.jpg")
labels, centers = tb.labels()
_, _, (ow, oh), _ = tb.prep()
base = open("experiments/baseline_v4.svg").read()

H, W = labels.shape
ren = svg_to_rgb(base, W, H)            # render at label-map resolution
ren_lum = ren.astype(float) @ np.array([0.299, 0.587, 0.114])

dark_src = np.zeros((H, W), bool)
for li in range(len(centers)):
    if _luminance(centers[li]) < 96.0:
        dark_src |= labels == li

missing = dark_src & (ren_lum > 128)     # source says line, render says light
# ignore 1px antialias fuzz at edges
missing = ndimage.binary_erosion(missing, np.ones((2, 2), bool))
cl, n = ndimage.label(missing, structure=_STRUCT8)
sizes = np.bincount(cl.ravel()); sizes[0] = 0
order = np.argsort(sizes)[::-1][:12]
print(f"missing-ink clusters: {n}, top sizes: {[int(sizes[i]) for i in order if sizes[i]>0]}")

sc = 4096.0 / max(ow, oh)
lab_to_render = sc * max(ow, oh) / max(H, W)
spots = []
for i in order:
    if sizes[i] < 12:
        break
    yx = np.argwhere(cl == i).mean(axis=0)
    ry, rx = yx[0] * lab_to_render, yx[1] * lab_to_render
    print(f"  cluster {int(sizes[i])}px at label({yx[0]:.0f},{yx[1]:.0f}) -> render ({ry:.0f},{rx:.0f})")
    spots.append((int(ry) - 210, int(rx) - 210))

out = tb.crops({"v4": base, "recraft": tb.target()},
               out="run2_missing_ink.png", spots=spots[:6])
print("crops ->", out)
