# experimental — "how I think Recraft works"

A from-scratch architecture built in design mode (2026-07-09) to test the
Recraft reconstruction in `research/design/BLUEPRINT.md`. **Not a vN milestone**
— it does not descend from v11's approach; it inverts it. Runnable in the web
interface (pick `experimental`) and CLI (`python run_model.py -m experimental`
/ `models/experimental/entry.py <img> <out>`).

## The thesis it embodies

v11 = **colour first, geometry falls out of colour** (global k-means quantize →
region boundaries → repair the damage in 6 stages). Every colour accident
(JPEG blur, AA, soft shadow) fractures geometry.

experimental = **idealize first, geometry from edges, colour last**:

1. **Idealize** (`idealize`): edge-preserving mean-shift — flatten gradients /
   AA / JPEG noise, keep strong edges. Soft transitions collapse toward flat
   BEFORE vectorizing. LOCAL colour merging, no global palette.
2. **Topology** (`local_regions`): Felzenszwalb graph segmentation — regions
   from local colour affinity + strong edges, not a global colour k. Distant
   near-identical colours stay separate; glued-similar colours merge.
3. **Colour last** (`recolor_from_interior`): each region's fill = median of
   the ORIGINAL image over its ERODED interior (one distance-transform, not
   per-region erosion) — boundary AA / occluders can't contaminate the fill.
4. **Geometry + emit**: reuse v11's shared-boundary, line-intent, corner-
   pinned, layered painter's-order emitter (the already-Recraft-shaped half of
   v11), fed OUR labels + colours.

All radii/areas are artwork-relative (R1/R2), so behaviour is resolution-
stable. Entry does NOT hard-downscale to 1024 (R1) — it works at a cap
(`work_dim`, default 1024 while iterating; raise toward native) and upscales
small art up.

## v1 status (rabbit, `research/design/exp_compare.png`,
`exp_production_line.png`)

**Validated (front-half thesis works):** local colour → flat clean background
(one orange, no bands); colour-last → accurate fills, no shrapnel; mean-shift →
soft shadow/gradient flattened; coherent output in ~3s.

**Open (v2 targets):**
- **No dedicated ink/line layer yet.** Felzenszwalb treats the black outline
  as just another region; mean-shift + interior sampling thin it → outlines
  read soft, not the confident black ink of Recraft/v11. Next: extract the
  ink/line network + line-intent classification (strokes ON TOP of the
  bucket-fills — "a drawing is strokes + fills").
- **Over-fragmented:** ~1900 paths / ~1.1 MB vs Recraft ~700 / 11 KB. Coarsen
  segmentation (scale/min_size up) + stronger parsimony.
- `measure_scale` is a placeholder (longest-side/256), not a real line-weight
  measurement.

Repro: `python run_model.py -m experimental -i data/inputs/rabbit.jpg`
