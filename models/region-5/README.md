# ideal-5 — aggregation approach (gentle segmentation + smooth fit)

USER direction (2026-07-10). ideal-4 killed noise by MERGING small regions,
which ate thin dark outlines into gray. ideal-5 keeps segmentation gentle so
outlines survive as their own dark regions, and cleans the appearance by
AGGREGATING rough geometry into smooth shapes (fill boundary fitter), plus a
light color group. Outlines stay dark by construction.

Pipeline: resize (downscale-only) → light color group (bilateral) → gentle
Felzenszwalb (low scale, outlines kept) → color-last from original → smooth
fill-boundary fit. Knobs: fz_scale (segmentation gentleness), group_color
(grouping strength), min_area_frac (speck floor), parsimony (fit smoothness).

Repro: python run_model.py -m ideal-5 -i data/inputs/rabbit.jpg
