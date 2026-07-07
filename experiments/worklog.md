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

### Run 3: bridge free ends across components — quality=0.8708 elephant / 0.713 rabbit (KEEP, by EYE)
- Timestamp: 2026-07-07 late · commit 2570c63 (parent run 2) · focus → rabbit
- Diagnosis: rabbit outlines render as DASHES — the label map breaks drawn
  lines wherever a lighter region (strap, highlight, AA fuzz) crosses; pieces
  land in different components ⇒ no shared skeleton node ⇒ run-2 anchoring
  can't reach. 12 genuine free-end gaps found, ALL cross-component, forward
  angles 5–52°; one 104° parallel case correctly identified as a non-junction.
- Change (one atomic): free ends snap onto another stroke ≤1.2·gw away when
  the target lies <60° off the outward tangent (never sideways onto parallel
  neighbors); mutually-facing free ends meet at the midpoint; snapped ends
  lose free status (no taper, no stub-drop — rescues bridge dashes).
- Eye verdict: rabbit heart/cheek/paw gaps closed (9 bridges); elephant ear
  junctions now fully joined (bonus — those were cross-component too);
  chopchop rim joins slightly better, 60° gate held (no parallel snaps);
  crystals/fox equal-plus; mountain equal (tree shape better);
  logo-geometric/monster-flat-line bit-identical. 8/8 no regression → SHIP.
- Sanity metric: elephant 0.8669 → 0.8708 (above the 0.8682 baseline —
  bridged gaps restore real ink, so even the noise-loving metric agrees).
  Rabbit first reference: 0.713 @ 4339 pts.
- Remaining on rabbit: LONG label-map losses (> 1.2w) still break the heart's
  left outline — needs source-ink-continuity extension (walk the darkness
  ridge in the ORIGINAL image beyond the label map), a separate experiment.

### Run 4: source-ink ridge extension — rabbit 0.7272 / elephant 0.8599 (KEEP, by EYE)
- Timestamp: 2026-07-07 night · commit 5eb37ad (parent run 3) · focus rabbit
- Change (one atomic): still-free ends walk the SOURCE raster's dark ridge
  (probe fan, < dark_lum) up to 4w; snap to another stroke if reached, else
  keep the traced tail (taper at true ink end).
- Debug 2: unguarded walker ROAMED DARK FILLS on chopchop (curled hooks on the
  arm line, junction blobs) → added (a) perpendicular ridge test: light ground
  within ~1.1w on BOTH sides at every step — a line, not a blob; (b) ~120°
  cumulative turn cap — real lines curve, blob-boundary curls don't ship.
  Guards fixed chopchop AND kept every rabbit/elephant win.
- Eye verdict: rabbit heart arcs + coat edge now near-continuous, sleeve
  junction + carrot vein joined; elephant lost ear line COMPLETES; chopchop's
  long-detached handle outline finally attached (pre-existing defect fixed);
  fox/crystals equal-plus; mountain 467 diff px; logo/monster identical.
  8/8 no regression → SHIP.
- Sanity: rabbit 0.713→0.7272 (+2%). Elephant composite 0.8708→0.8599 (−1.25%)
  FLAG: sub-metrics flat (ssim −0.0015, msssim −0.0009) — dip is in the
  composite's coherence/local terms, eye clearly better; composite `quality`
  is noisy at the ±1% level; keep watching the trend, don't chase it.
- Next candidates: (a) remaining rabbit heart tip/top-left gaps (ends whose
  ink truly breaks in source — needs gap-jump across LIGHT pixels when both
  sides' tangents agree, riskier); (b) curvature drift (BACKLOG #2);
  (c) chopchop toe-blob / junction ink pooling cleanup.

### Run 5: parsimony centerline fit — DISCARD (negative result, kept on record)
- Timestamp: 2026-07-08 · vs HEAD b801c6b (parent run 4) · focus elephant
- Tried: `_fit_branch` open branches → `svgcore.fit_open_parsimony` on the RAW
  skeleton chain (no pre-smoothing), targeting the user's "curvature drift".
- Finding 1 (the real result): **curvature drift is ALREADY RESOLVED at
  current HEAD** — mechanical check: mean distance from source-skeleton points
  to rendered ink = 0.04–0.05px, p95 = 0, for BOTH variants. The user's v4-era
  defect report predates the runs 2–4 junction/continuity work.
- Finding 2: parsimony ≈ smooth+Schneider by eye at 8k (no corners, no win),
  and points went UP (2612 → 2639) — no economy benefit either.
- Verdict: discard per "simpler is better" — don't swap a proven code path for
  a lateral move. Do NOT retry parsimony centerlines without a new reason.
- Next: chopchop junction ink pooling / toe blobs (last visible join defect),
  or palette idealization (the declared last gap to Recraft on the elephant).

### Run 6: chopchop serration heaviness — DISCARD, but the diagnosis is the win
- Timestamp: 2026-07-08 · vs HEAD 2899af9 · focus chopchop
- Palette pre-check (before any code): per-label MEDIANS == kmeans means
  (≤3/255) — our tints are faithful to the source; Recraft *deliberately
  re-grades* shadow tints (our 98bee3 → their A6B8D0, −13% saturation, cooler).
  Matching that = a re-grading POLICY (taste), parked in BACKLOG, likely wants
  user input.
- Serration diagnosis (measured): chopchop excess ink = 17.7k px, of which
  STROKES contribute only 271 — the heavy blobby outlines are the FILL layer:
  96/144 dark components fail the shape gate (notch pooling makes them
  width-varying) and render as faithful ink-pool fills.
- Tried (one change, two coherent halves): swell cap 1.6×w + shape_p90 1.5→2.0
  (69 components became strokes). Excess ink flat (17.7k→17.8k), eye = lateral:
  the stroked serrations lay the same ink. Reverted.
- Real gap vs Recraft: it REDRAWS serrated outlines as uniform-weight strokes
  with SHARPENED V-notches — shape idealization of notch geometry, not a knob.
  Queued in BACKLOG as a design item.
- Harness quirk noted: chopchop sanity quality = 0.14 (vs elephant ~0.87) —
  likely background/alpha handling in the metric for this PNG; treat chopchop
  numbers as meaningless, eye only. (Harness is locked; not investigating now.)

### Run 7: RESEARCH pass (spec §8.2) — designs unblocked for both stalled items
- Timestamp: 2026-07-08 · no code change (research iteration; sub-agent web pass)
- Serrations: the missing ingredient is CORNERS AS HARD NODES + miter joins —
  `stroke-linejoin:miter` re-sharpens V-notches geometrically; detect notch
  pools as width-max ∧ high turning angle, split centerline there, fit
  branches ignoring pooled pixels. (Puhachov 2021, PolyFit 2020, Favreau 2016;
  no public Recraft tech docs exist — verified.)
- Palette: Recraft's re-grade is MEASURABLE from our own 8 input↔target pairs:
  fit (ΔL, ΔC, Δh) per matched shadow pair in OKLCH; clustering ⇒ ramp
  constants ⇒ autonomous, data-driven re-grader (no taste call needed).
- Both designs written into docs/BACKLOG.md with sources. Run 8 should start
  with the palette RAMP MEASUREMENT (zero-risk, half-day, pure measurement)
  or the serration miter experiment (bigger, higher payoff).

## Key Insights
- The metric is a sanity check, not the gate. A change can raise `quality` by
  copying noise and still LOOK worse — always render `tb.crops` and decide by eye.
- Stage caching (testbed) makes single-knob re-renders take seconds; put zoom
  `spots` on the specific defect.

## Next Ideas
See **docs/BACKLOG.md** — the single idea queue, ranked by visual impact.
