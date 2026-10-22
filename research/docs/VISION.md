# VISION — what this engine is trying to be

_USER's vision, stated 2026-07-09, rewritten for the loop. This outranks every
metric, ledger item, and benchmark. When a change is judged, it is judged
against THIS._

## The one-sentence goal

**Reverse-engineer the drawing, don't trace the raster.** Recraft's engine
behaves as if it asks: "if a designer drew this cleanly in a vector tool, what
brushstrokes and bucket-fills would they use?" — and then draws THAT. The
output is a minimalist, idealized re-drawing that keeps every drawn boundary
and drops every raster accident.

## The blueprint (how Recraft appears to think)

1. **A drawing is strokes + bucket-fills.** Big zones are one flat fill — the
   averaged color of that zone ("bucket fill"). Lines are confident single
   movements. The SVG is the plausible *edit history* of the drawing, not a
   partition of pixels.

2. **Color merging is LOCAL, not global.** Similar colors that are *glued
   together* merge into one region colored by their area-weighted average.
   Recraft's palettes are large (78 colors on chopchop — roughly one per
   shape) but each *region* is a single flat tone. There is no global
   k-palette: two distant regions may keep two near-identical browns, while
   five glued-together shades of one brown become one. Raster accidents —
   JPEG blur, AA fringes, soft shadow ramps, pixel-blur blackish tones along
   lines — are exactly "similar colors glued to each other" and get absorbed
   into their parent zone.

3. **Shadows and gradients flatten.** A soft drop-shadow becomes either
   nothing or ONE clean offset shape in a single darker tone. A large smooth
   gradient becomes one flat average fill — or (Recraft does this on
   app-asset) one genuine SVG `linearGradient`/`radialGradient` fill. It is
   never 2-3 posterized bands with ragged boundaries.

4. **Line intent decides geometry.** The engine must classify what each
   boundary IS in drawing terms:
   - a *single-movement curve* (a cheek, a tail) → smooth it confidently,
     even-width, no wobble;
   - a *ruler line* (facet edge, hand/body separation, checker grid, ridge) →
     dead straight, and its corners stay sharp kinks;
   - *parallel/detail strokes* (pinstripes, fur ticks, teeth) → keep each
     one; never merge neighbors, never round a zigzag's points.
   Recraft's straight-segment share proves this is explicit: mountain 644 L
   commands vs our 45; elephant 54 vs our 0; app-asset 116 vs our 9.

5. **Boundaries are sacred.** If the original draws a border between two
   objects — even same-ink or near-same-color (hand on basket, facet on
   facet, string on heart) — the border survives. Losing a drawn boundary is
   worse than keeping some noise: it changes what the image *says*.

6. **Repeated elements are regularized.** Teeth, rivets, checker cells, icon
   corners: Recraft renders repeated features *more* even than the original —
   idealization means the pattern's rule is drawn, not each instance's pixels.

7. **Output structure = layered shapes.** One path per shape, single subpath,
   painter's order (background first, details on top) — not one giant
   multi-subpath path per palette color. This is what makes the SVG read as
   "how it would be drawn" and stay editable.

8. **Minimalist styling is allowed to deviate.** Recraft re-tints (rabbit bg
   more saturated than the original), simplifies fur zigzags, drops sub-pixel
   junk. Deviation from the original in the direction of *cleaner design
   language* is a win; deviation toward noise is the only real loss.

## The bar (how to judge)

**AMENDED 2026-07-10 — improvement is scored by ALGORITHM, not the eye.**
Orchestrator visual judgment proved unreliable (approved a distorted elephant).
To decide whether a change improved, run
`eval/score_vs_recraft.py` (MS-SSIM↑ / GMSD↑ / CIEDE2000 dE↓ vs the
Recraft targets) and keep the change only if the score improves. Visuals are
for EXPLORATION — understand where we are, find defects, form hypotheses; the
eye does NOT render the improvement verdict. The rules below still govern how
you EXPLORE and describe defects.

- **Absolute, not relative.** A defect is closed when the zoomed grid shows
  ours ≈ Recraft at that spot — not when it's better than last run.
  (Postmortem: monster teeth were "closed" runs 21-22, but HEAD teeth are
  still blunt/uneven vs Recraft. Closed-at-80% is how the plateau happened.)
- **Zoom or it didn't happen.** Full-frame 640px verdicts are void. Every
  verdict comes from crops at ≥2 zoom levels; flat art especially — its
  defects are 1-3px (seams, corner melts, tooth tips).
- Where no Recraft target exists, judge vs the original under the blueprint
  above ("what would the clean redraw look like?").

## Where the engine stands vs this vision (audit 2026-07-09)

See `research/experiments/audit24/FINDINGS.md`. Short version: quantize-partition +
boundary-fit copies raster accidents into geometry (edge shrapnel, shadow
blobs, facet melts), has no line-intent classification (everything tends to
cubic), no local color-merge model (global palette + size-based despeckle),
and no per-shape layer structure. Flat clean inputs are near-parity; anything
with soft shading/AA is 50-70%.
