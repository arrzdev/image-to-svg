"""Run 3 diagnostic: on the FOCUS target, find FREE stroke ends that stop near
another stroke's centerline (cross-component/cross-label abutments the run-2
anchor can't reach — it only sees branches of the same skeleton component).

Prints candidates (end position, gap distance, forward-angle) in label space +
renders crops at the top spots. Forward-angle ~0° = continuation into the other
stroke (a real junction); ~90° = merely parallel (must NOT snap).
"""
import sys
sys.path.insert(0, "backend")
import numpy as np

from testbed import Testbed
from contours_exp import extract_contour_strokes

tb = Testbed("rabbit.jpg")
labels, centers = tb.labels()
_, _, (ow, oh), _ = tb.prep()

# reproduce the pend-level geometry: run extraction but capture branch data via
# the info/strokes it returns is post-fit; instead re-run the internal loop the
# cheap way — call extract and use its returned strokes' d endpoints? Fits hide
# raw ends. Simplest faithful probe: monkeypatch _ribbon/_fit_branch? No —
# reimplement the first phase quickly via the same helpers.
from scipy import ndimage
from skimage.morphology import medial_axis
from strokes import (_STRUCT8, _luminance, _skeleton_branches, _prune_and_merge,
                     _branch_degrees)
from contours_exp import _prune_fork_tines, _merge_continuations

polylines = []   # (pts Nx2 (y,x), comp_id, head_free, tail_free)
comp_id = 0
dark = [li for li in range(len(centers)) if _luminance(centers[li]) < 96.0]
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
        comp_id += 1
        branches, node_lbl = _skeleton_branches(skel)
        branches = _prune_and_merge(branches, dist, 0.9)
        branches = _prune_fork_tines(branches, med_w)
        branches = _merge_continuations(branches, 50.0)
        branches = [b for b in branches if len(b["pix"]) >= 4]
        deg = _branch_degrees(branches)
        for br in branches:
            pts = np.asarray(br["pix"], float)
            hf = not br["closed"] and (br["a"] == 0 or deg.get(br["a"], 0) <= 1)
            tf = not br["closed"] and (br["b"] == 0 or deg.get(br["b"], 0) <= 1)
            polylines.append((pts, comp_id, hf, tf, med_w))

print(f"branches: {len(polylines)} across {comp_id} components")
cands = []
for i, (pts, cid, hf, tf, w) in enumerate(polylines):
    for free, idx, tvec in (((hf), 0, pts[min(6, len(pts)-1)] - pts[0]),
                            ((tf), -1, pts[max(-7, -len(pts))] - pts[-1])):
        if not free:
            continue
        end = pts[idx]
        tdir = -tvec / (np.linalg.norm(tvec) + 1e-9)   # outward tangent
        best = None
        for j, (opts, ocid, _, _, _) in enumerate(polylines):
            if j == i:
                continue
            d = np.linalg.norm(opts - end, axis=1)
            k = int(np.argmin(d))
            if best is None or d[k] < best[0]:
                best = (float(d[k]), j, ocid, opts[k])
        if best and best[0] < 1.2 * w:
            v = best[3] - end
            ang = np.degrees(np.arccos(np.clip(
                np.dot(v, tdir) / (np.linalg.norm(v) + 1e-9), -1, 1)))
            cands.append((best[0], ang, end, cid, best[2]))

cands.sort(key=lambda c: c[0])
print(f"free ends within 1.2w of another stroke: {len(cands)}")
spots = []
for (d, ang, end, cid, ocid) in cands[:10]:
    cross = "CROSS-COMP" if cid != ocid else "same-comp"
    print(f"  gap={d:.1f}px fwd-angle={ang:.0f}° at label({end[0]:.0f},{end[1]:.0f}) [{cross}]")
    spots.append((int(end[0] * 4) - 210, int(end[1] * 4) - 210))

if spots:
    prev = open(f"experiments/run3_prev_rabbit.svg").read() if False else None
from pipelines import get_pipeline
from svgutil import fit_svg_size
pp, _, _, _ = tb.prep()
cur = fit_svg_size(get_pipeline("contour_lines").run(pp, {}), ow, oh)
open("experiments/run3_prev_rabbit.svg", "w").write(cur)
seen = set(); uniq = []
for s in spots:
    key = (s[0] // 150, s[1] // 150)
    if key not in seen:
        seen.add(key); uniq.append(s)
out = tb.crops({"prev": cur, "recraft": tb.target()},
               out="run3_free_ends.png", spots=uniq[:5])
print("crops ->", out)
