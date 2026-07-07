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

### Run 2: junction anchor → nearest other-branch centerline — quality=0.8669 (KEEP, by EYE)
- Timestamp: 2026-07-07 evening · commit c0adad6 (parent run 1)
- Hypothesis chain: (a) dropped junction-junction connectors → REFUTED, 0 found
  on elephant defaults; (b) missing-ink clusters → mostly deliberate
  width_scale=0.85 undershoot, NOT gaps; (c) 8k-zoom eye pass at junction nodes
  → CONFIRMED defect: side-stroke round cap anchored at node-cluster CENTROID
  overshoots through the through-line (nub pokes through silhouette into sky at
  T-junctions; node13 of elephant ear). Recraft: flush.
- Change (one atomic): in extract_contour_strokes, anchor junction ends to the
  nearest pixel of ANOTHER kept branch's path near the node (fallback:
  centroid). Cap lands flush under the through stroke by construction.
- Debug 1: first radius (1.5w) snapped ends onto PARALLEL neighboring strokes in
  dense-line art (chopchop: detached ends, white slivers) → tightened to 0.8w
  (through-line is ≤0.5w from centroid; parallel neighbors ≥1w away). Fixed.
- Eye verdict: elephant T-nub GONE, Y flush (matches Recraft); chopchop joins
  continuous (≥prev); crystals facet-edge breaks now CONNECT (improved);
  rabbit/fox/mountain unchanged; logo-geometric/monster-flat-line 0px diff.
  8/8 no regression → SHIP.
- Sanity metric: quality 0.8669 (−0.15% vs 0.8682) — expected: the nub used to
  cover source ink; metric rewards noise-copying (spec §4). Eye rules.
- Next: rabbit ear-line still stops short of the outline in BOTH versions —
  cross-component junction (line and outline in different label components; no
  shared skeleton node, so anchoring can't reach it). That's the real
  "crossing gap" class. Candidate: snap free stroke ends to NEARBY strokes of
  other components/labels when source ink is continuous across.

## Key Insights
- The metric is a sanity check, not the gate. A change can raise `quality` by
  copying noise and still LOOK worse — always render `tb.crops` and decide by eye.
- Stage caching (testbed) makes single-knob re-renders take seconds; put zoom
  `spots` on the specific defect.

## Next Ideas
See **docs/BACKLOG.md** — the single idea queue, ranked by visual impact.
