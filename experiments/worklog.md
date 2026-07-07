# Autoresearch worklog — image→SVG (vision-first)

Narrative that survives compaction/clear. On resume: read `autoresearch.md`
(objective + rules), then this file (what's been tried), then continue.

**Mission:** docs/PROJECT_SPEC.md · **Handoff:** docs/RESUME.md · **Work queue:** docs/BACKLOG.md

## Data summary (become one with the workload)
- 8 focus-able targets in `data/inputs/` paired with Recraft SVGs in
  `data/targets/`: elephant, rabbit, fox (outlined characters), chopchop (dense
  line crossings), crystals (gradient), mountain, logo-geometric, monster-flat-line.
- Current focus: **elephant** (`./autoresearch.focus`). Its open defects are the
  most tractable line-quality wins.
- Judge by EYE via `tb.crops`, not the metric (spec §4). Metric rewards copying
  source noise; Recraft scores lower on it than our noisier output.

## Runs

### Run 1: v4 contour_lines baseline — quality=0.8682 (KEEP)
- Timestamp: 2026-07-07
- What changed: none — this is the starting point (git d5fad37, v4).
- Result: quality 0.8682, ssim 0.9643, ms_ssim 0.9864, 2609 pts, ~2.1s render.
- Insight: reached Recraft's tier on the elephant by eye; three original defects
  (wobble, width thinning, shadows-over-lines) already resolved in v3→v4.
- Next: fix the open stroke defects on the elephant, one atomic change each —
  perpendicular-crossing gaps first (highest visual impact, see BACKLOG.md).

## Key Insights
- The metric is a sanity check, not the gate. A change can raise `quality` by
  copying noise and still LOOK worse — always render `tb.crops` and decide by eye.
- Stage caching (testbed) makes single-knob re-renders take seconds; put zoom
  `spots` on the specific defect.

## Next Ideas
See **docs/BACKLOG.md** — the single idea queue, ranked by visual impact.
