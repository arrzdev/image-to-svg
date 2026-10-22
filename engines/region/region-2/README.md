# ideal-2 — idealize-first + dedicated ink layer

Second in the `ideal-` lineage (idealize-first / geometry-before-colour), the
"how Recraft works" rebuild. Runnable: web dropdown `ideal-2`, or
`python run_model.py -m ideal-2`.

## What it adds over ideal-1

ideal-1 proved idealize→local-segment→colour-last makes clean flat
bucket-fills, but **36% of black ink was absorbed into neighbour fills** — a
thin line between two regions has no interior to colour (BLUEPRINT.md
"Experimental v1 finding"). ideal-2 adds the missing half of "a drawing is
strokes AND bucket-fills":

1. **idealize** — edge-preserving mean-shift (flatten gradients/AA, local
   colour merge, no global palette).
2. **ink layer FIRST** (`detect_ink`) — the dark line network from the
   ORIGINAL luminance (idealize lightens thin lines, so sample the original),
   speckle-cleaned + gap-closed at artwork scale.
3. **local fill topology** (Felzenszwalb) — regions from edges, not colour k.
4. **carve ink out** into its own dark label so fills close UNDER it and can
   never absorb it.
5. **colour last** — each region's fill = median of the ORIGINAL over its
   eroded interior; the ink label falls back to its own dark pixels (black).
6. **emit** via quant-11's `contour_svg` — fills UNDER + line-intent
   (straight/curve/detail) confident strokes ON TOP, layered painter's order.
7. **R2 survival floor** (`apply_stroke_floor`) — viewBox-relative min stroke
   width so outlines hold at any display size, in any renderer.

## Status (rabbit — research/experiments/design-studies/figures/ideal2_compare.png, ideal2_survival.png)

**Win:** confident black outlines are back (232 strokes) AND survive at 480px
display, over clean flat idealize-first fills — the blueprint union, and
outlines hold in a real browser because the geometry itself is thicker (not a
display hack). Competitive with quant-11 by eye at this scale.

**Open:** over-fragmented (~1700 paths / ~1 MB vs Recraft ~700 / 11 KB — coarsen
segmentation + parsimony); ink slightly heavy/rough in places vs Recraft's
crisp line; `measure_scale`/`detect_ink` thresholds are first-cut, need eye-
tuning across all 18 (thin whiskers vs bold outline) and at deep zoom.

Repro: `python run_model.py -m ideal-2 -i data/inputs/rabbit.jpg`
