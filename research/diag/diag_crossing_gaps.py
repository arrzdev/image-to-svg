"""Run 2 diagnostic: locate junction-junction connector branches that
extract_contour_strokes DROPS (len < min_branch_px) without contracting their
nodes — hypothesis: these are the perpendicular-crossing gaps.

Prints spot list in 4096-render space + renders baseline crops there.
"""
import sys
sys.path.insert(0, "backend")
import numpy as np
from scipy import ndimage

from testbed import Testbed
from strokes import (_STRUCT8, _luminance, _skeleton_branches, _prune_and_merge,
                     _branch_degrees)
from contours_exp import _prune_fork_tines, _merge_continuations

tb = Testbed("elephant.jpg")
labels, centers = tb.labels()
_, _, (ow, oh), _ = tb.prep()

from skimage.morphology import medial_axis

dark = [li for li in range(len(centers)) if _luminance(centers[li]) < 96.0]
drops = []   # (y, x, connector_len, local_width) in label-map space
for li in dark:
    comp, n = ndimage.label(labels == li, structure=_STRUCT8)
    for ci in range(1, n + 1):
        mask = comp == ci
        if int(mask.sum()) < 30:
            continue
        skel, dist = medial_axis(mask, return_distance=True)
        if not skel.any():
            continue
        med_w = float(np.median(dist[skel] * 2.0))
        wp0 = dist[skel] * 2.0
        if float(np.percentile(wp0, 90)) > 1.5 * med_w:
            continue
        if med_w > max(12.0, 0.014 * max(labels.shape)):
            continue
        branches, node_lbl = _skeleton_branches(skel)
        branches = _prune_and_merge(branches, dist, 0.9)
        branches = _prune_fork_tines(branches, float(np.median(dist[skel] * 2.0)))
        branches = _merge_continuations(branches, 50.0)
        # replicate the silent drop: junction-junction branches shorter than 4px
        for br in branches:
            if (not br["closed"] and br["a"] and br["b"] and br["a"] != br["b"]
                    and len(br["pix"]) < 4):
                yx = np.asarray(br["pix"], float).mean(axis=0)
                w_conn = float(np.median(dist[tuple(np.asarray(br["pix"]).T)]) * 2.0)
                drops.append((yx[0], yx[1], len(br["pix"]), w_conn))

print(f"dropped junction-junction connectors: {len(drops)}")
sc = 4096.0 / max(ow, oh)                    # render scale for tb.crops
lab_to_render = sc * max(ow, oh) / max(labels.shape)   # label px -> render px
spots = []
for (y, x, L, w) in drops:
    ry, rx = y * lab_to_render, x * lab_to_render
    print(f"  label({y:.0f},{x:.0f}) len={L} w={w:.1f} -> render spot ({ry:.0f},{rx:.0f})")
    spots.append((int(ry) - 210, int(rx) - 210))   # center the 420px crop

if spots:
    svg = tb.svg.__self__ and None  # placeholder no-op
from pipelines import get_pipeline
from svgutil import fit_svg_size
pp, _, _, _ = tb.prep()
base = fit_svg_size(get_pipeline("contour_lines").run(pp, {}), ow, oh)
open("experiments/baseline_v4.svg", "w").write(base)
out = tb.crops({"v4": base, "recraft": tb.target()},
               out="run2_gaps_baseline.png", spots=spots[:6] or None)
print("crops ->", out)
