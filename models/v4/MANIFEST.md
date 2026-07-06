# v4 — line/fill idealization (vision-first pass)

Focus of this version: close the visual gap to Recraft the USER sees at zoom,
not the metric. Three cited defects addressed:
- Wobbly lines -> Potrace-parsimony fitter (sub-0.5px wobble structurally
  impossible) + width-constant centerline strokes.
- Line width thinning -> single calibrated stroke width (contour_lines).
- Shadows painted over lines -> strokes are the top layer.
Plus: parsimony-fitted SHADING boundaries (flat idealized shapes like
Recraft's), line-weight calibration width_scale=0.85 (tracks Recraft).

Best elephant output: contour_lines pipeline defaults -> ~918 pts / 39 paths
/ 13KB. Full-frame + deep-zoom comparisons vs recraft-elephant.svg saved
here (vs_recraft_fullframe.png, vs_recraft_zoom.png): line quality and fill
cleanliness now in Recraft's tier; residual differences are subtle palette/
shading-color choices, not structural line/fill quality.

Run it: convert.py picks it via the tournament, or directly:
  get_pipeline('contour_lines').run(proc_png, {})
