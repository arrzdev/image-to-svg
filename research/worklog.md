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

### Run 8: palette ramp MEASUREMENT — hypothesis refuted, real gap identified
- Timestamp: 2026-07-08 · measurement only (`experiments/measure_ramp.py`,
  kept as a reusable tool) · no pipeline change
- Result: across all 8 gold pairs, ours→Recraft chromatic-midtone deltas in
  OKLCH center on ZERO (dL +0.001±0.044, dC +0.002±0.032, dh −0.3±40 — the
  scatter is crystals matching noise). Recraft palettes ≈ OURS on 6/8 targets
  to ~0.005. **Recraft does NOT re-grade tints. Never build a re-grader.**
- The elephant's "softer tints" (run-6 observation) decoded: we keep TWO mid
  shadow tones (aeb4c4 + 98bee3), Recraft merges to ONE (a6b8d0 ≈ between
  them). Structural, not colorimetric. New BACKLOG item: low-chroma
  same-hue-family tone merging (must not touch crystals' chromatic ramps).
- Crystals caveat: palette matching fails on gradient-banded images (many-to-
  one matches) — measure_ramp numbers for crystals are unreliable.

### Run 9: merge near-duplicate shadow tones — quality=0.8562 (KEEP, by EYE)
- Timestamp: 2026-07-08 · commit a3ccbd3 (parent run 4) · focus elephant
- Change: `_merge_shadow_tones` in quantize_contours (called from
  contour_lines): merge label pairs with OKLab C<0.08, |dL|<0.03, dE<0.06.
- Debug 1: first version merged mountain's WARM cream snowband into the COOL
  blue-gray sky (both low-chroma, equal-L). Added hue-opposition guard
  (cos dh > 0.3). Lesson: at low chroma, hue TEMPERATURE still reads across
  large areas — never merge across warm/cool.
- Eye verdict: elephant cast shadow now renders Recraft's exact tone (merged
  a4b8d1 vs their a6b8d0 — 2/255 apart, derived from data); fox merge mirrors
  Recraft's own; chopchop bowl sliver + rabbit ear arc joined as bonus;
  mountain warm/cool preserved; logo/monster identical. 8/8 → SHIP.
- Sanity: delta_e 1.61→1.83 BY DESIGN (we moved color away from the source
  toward Recraft — the metric penalizes idealization, spec §4). quality 0.8562.
- Remaining big item: serration corner-nodes + miter joins (design in BACKLOG).

### Run 10: serration corner-nodes + miter joins — KEEP (commit 50c0a03)
- Change: outline-BAND exemption in the shape gate + corner-preserving
  smoothing (_corner_indices on RAW chain + _smooth_open_corners) + constant
  width + stroke-linejoin:miter (miterlimit 8) for band strokes.
- Debug 1: hole-enclosure band test never fired (serration outlines are OPEN
  arc fragments in the label map) → signature test (cov<1.4, elong>6).
- Debug 2: swell_frac<0.25 rejected ALL serrations (pools at every notch,
  frac 0.3–0.45) → replaced with p25r>0.8 (solid baseline between pools;
  tapered glyphs 0.4–0.6 — verified on rabbit/fox data).
- Debug 3: at med_w=2px the EDT can't express taper → fox fur flicks
  masqueraded as bands and lost their drawn character → med_w>=3 gate.
- Chopchop eye verdict (before debug 3, unaffected by it): serration Vs
  visibly SHARPER + uniform weight, clear step toward Recraft. Excess-ink
  metric flat all along — it cannot see sharpness; eye rules.
- Final eye sweep: chopchop serration Vs SHARPER + uniform (main win);
  elephant tail-fork/toe joins crisper (bands fire via pipeline path — merged
  labels shift component stats); rabbit ear lines normalized from fat fills to
  drawn weight; fox flicks reverted to fills (med_w gate ✓); crystals/mountain
  small+safe; logo/monster identical. 8/8 → SHIP.
- Sanity: elephant 0.8574 (flat vs 0.8562), points 2601. Chopchop metric
  still meaningless (0.144) — eye only, as established run 6.

### Run 11: dark-label UNION — DISCARD (two designs refuted, lesson kept)
- Target defect: brown flecks along chopchop serrations = small components of
  sibling dark labels stroked in their own color; per-label processing also
  splits the physically-connected network at color seams.
- Debug 1: naive full union REGRESSED the trunk — welded the dark-brown
  SHADING band into the black outline (majority color black → lumpy black
  blobs). Lesson: dark ≠ line; dark shading fills must stay fills.
- Debug 1 result: dominance rule (≥70% one label → unify; else split back
  per label) fixed the trunk weld BUT flecks persist in the crown crops and a
  leg tip got marginally heavier — mixed/lateral by eye → DISCARD, revert.
- Lesson + next design: flecks need ADJACENCY-BASED SMALL-FRAGMENT RECOLOR
  (small dark fragment touching a much larger other-dark-label line inherits
  its color/mask), not any form of union. The union family is exhausted —
  don't retry it.

## Key Insights
- The metric is a sanity check, not the gate. A change can raise `quality` by
  copying noise and still LOOK worse — always render `tb.crops` and decide by eye.
- Stage caching (testbed) makes single-knob re-renders take seconds; put zoom
  `spots` on the specific defect.

## Next Ideas
See **docs/BACKLOG.md** — the single idea queue, ranked by visual impact.

### Run 12: worktree-parallel iteration (A ships, B discarded) — commit 4c616ce
- FIRST run under the new worktree-parallel architecture. 2 independent
  candidates in git worktrees off best; orchestrator re-verified both itself.
- A-fleck (contours_exp.py): adjacency fleck absorption — SHIPPED. chopchop 234
  flecks -> black line, -50KB; rabbit dabs absorbed; elephant no-op; eye 8/8.
- B-speckle (quantize_contours.py): shading despeckle — DISCARDED. Sub-agent
  said "mild win"; ORCHESTRATOR eye said lateral (despeckle already clears
  <120px first). Lead: retry only at a floor >120px on trunk-plank speckle.
- Methodology: pipeline renders are non-deterministic (~8k self-diff floor on
  elephant); diffpx is a spot-finder, not a verdict — a low number does NOT mean
  no-op (fox: 81 flecks fired under the floor). EYE-checked elephant (identical)
  + fox (81 flecks, all harmless) explicitly; initial 'no-op' label on fox was
  a number-inference mistake, corrected by looking.
- Both worktrees removed; /clear mid-cycle resume verified (single + merge).

### Run 13: worktree-parallel iteration (A+B BOTH ship combined) — commit b409934
- Timestamp: 2026-07-08
- 2 candidates off best, orchestrator-verified, combined one-at-a-time in an
  _integrate worktree with an eye re-verify after EACH apply.
- A-noodles (contours_exp.py): _wiggle_rate alternating-turn-density gate >2.2
  per branch + small-component gate + free-end trim; dropped ink carved to the
  fill layer. Chopchop trunk squiggle-noodles -> soft fill daubs. SHIPPED.
- B-speckle2 (quantize_contours.py): _dissolve_speckle floor 300 (the run-12
  lead). TWO regressions caught at integration/broadening, both fixed by
  orchestrator guards: ring-dominance >=0.6 (crystals orange-gem facets were
  being eaten) and darker-only luminance (mountain's drawn cloud wisp was
  deleted — light accents are intent, noise daubs are dark). SHIPPED.
- Broadening: all 8 targets eye-checked under FINAL guards; logo/monster
  re-rendered fresh (diffpx 0 AND eyed); crystals' pink shoulder-fleck on the
  orange gem (a prev artifact, absent in the original) is gone in new — bonus.
- Sanity: elephant q 0.8574 / ssim 0.9624 / 2645 pts (series-consistent);
  chopchop q 0.144 (known-meaningless for this target).
- Leads filed to BACKLOG: S-wavy strokes at wiggle 1.5-2.2 need a second
  signal; ink_extended~102 regrows hooks; tiny ISOLATED dark daubs untreated;
  black-blob lattice flood (unverified B-agent claim); monster's thin white
  scratch line lost by prev AND new (Recraft keeps it).
- All 3 worktrees (A-noodles, B-speckle2, _integrate) removed; iteration.json
  -> idle.

### Run 14: worktree-parallel iteration (A+B BOTH ship combined) — commit 3d251ad
- Timestamp: 2026-07-08
- Scout first: full-frame + zoom grids found the two dominant chopchop
  residuals and a label probe pinned domains (quantize vs stroke) -> N=2.
- A-strawguard (quantize_contours.py): light-accent guard in _despeckle_labels
  (ring >=0.6 ink among SURVIVING neighbors + >=80 lum gap; excluding fellow
  sub-floor fragments is what makes sandwiched stripes work). Straw striped
  again; co-wins: crystals gem vein, monster scratch tapers, FOX EYE GLINT
  restored, game-assets potion highlight. SHIPPED.
- B-junctionpool (contours_exp.py): junction pools (<4x med_w, deg>=3 node)
  stay in the stroke mask (no fill splat) + swell profile clamped within
  2.5x w_body of junctions. Frond centers + chair crossings cross cleanly;
  rabbit leaf-base pooling cleaned. SHIPPED.
- Broaden: 13 grids eyed + 3 byte-identical skips; no regressions (mountain
  lateral ticks match recraft's own; texture targets shuffle equally-rough).
- Sanity: chopchop quality 0.144 -> 0.6732 (black straw bar was a major
  driver of the metric quirk); elephant 0.8533 flat.
- Leads: vectorizer beads 1-2px light regions (fill emitter, monster scratch
  second half); strap-end curl loopier (free-end shaping); dissolve 0.6
  ring-guard is what lets rescued stripes survive (don't lower it).
- Process: a stale cwd created a nested worktree mid-integration; caught by
  loud cp failure. Rule: absolute paths for all worktree ops.

### Iteration 15: ABORTED before dispatch — loop PAUSED by user
- Worktrees created but no sub-agents launched, no code changed. Removed both.
- User request: repo restructure (versioned models/ with runnable code per
  version, clean README, minimal frontend). `.autoresearch-off` set.
- Queued leads when the loop resumes: A thin-light beading (fill emitter),
  B rabbit long-gap breaks (stroke domain). Focus file now says `rabbit`.

### Run 15: FIRST native-isolation iteration (A+B BOTH ship) — commit 44351d0
- Timestamp: 2026-07-08
- Dispatched via Agent isolation:"worktree" (model inherit, effort recorded);
  both agents killed mid-run by a transient API server error and RESUMED via
  SendMessage with worktrees intact; iteration.json next_action carried state.
- A-lightbead (fill path): the label chain itself dashes ~1.5px light lines;
  >=3-fragment gate + source-traced light capsule + flux width (1-3px).
  Monster scratches continuous; chopchop 0 capsules (gate held).
- B-longgap (stroke path): walker post-mortem (dies at 0-2.3w, jitter burns
  turn budget) -> chord bridge <=7w with whole-chord dark support + bright-run
  gate. Rabbit heart/paw/scallops close; elephant seams close; 35 chopchop
  bridges, zero welds.
- Broaden: 19 targets eyed (15 grids + 4 rendered-identical); mountain
  crevasse shuffle attributed to k-means nondeterminism (0 capsules there).
- Sanity in _integrate: rabbit 0.7555 (up), elephant 0.8548 flat. Slip: first
  sanity ran on MAIN tree via stale cwd - caught, re-ran. Absolute paths.
- Leads -> BACKLOG: capsule apex nub; fragments=1 lumpy slivers; heart
  top-left lobe (arc-aware support); walker net-turn budget; chopchop lattice
  tangles + scribble nondeterminism.

### ⟳ Compaction checkpoint — 2026-07-08 01:50:27
- Context is about to compact. State snapshot: experiments/autoresearch.jsonl.precompact.bak
- Runs so far: 13 | kept: 10
- On resume: read autoresearch.md, autoresearch.jsonl, and this worklog, then CONTINUE the loop (do not restart).

### Run 16: whole-carried sliver steal + bead absorption + end tucking — quality_monster=0.9596 (KEEP) — commit 9242186
- Timestamp: 2026-07-08 02:00
- What changed: `_light_line_capsules` also steals whole-carried slivers
  (fragments<3) iff cv_w>=0.2 AND wmean/max(med_w,2)<=1.45, skel>=20px,
  light coverage>=0.5; bead pixels absorbed into bg; `_extend_into_light`
  tucks capsule ends <=8px into the light line. Closes run-15's
  "fragments=1 lumpy slivers" lead.
- Result: monster slivers -> clean constant-width capsules (capsules 2->5);
  fox 4 / crystals 1 / game-assets-2 6 fired, all others 0. Eye: 4 focused
  spots + 17 broaden grids + 16 FULL-COVERAGE pages (sec8 gate, first use) —
  zero regressions; fox + game-assets-2 read as small wins. Sanity:
  monster 0.9596, elephant 0.8515 vs 0.8548 (flat/noise).
- Protocol firsts: sec9 shared artifact dir (research/it16/candidates/A-sliver/)
  with ALL verdicts from orchestrator-own renders of artifact SVGs; sec8
  tb.full_grid ship gate; agent resumed via SendMessage after API error.
- Insight: the mask confesses lumpiness — width-variation (cv_w) + fatness
  ratio separates dashed-line slivers from legit fill blobs, EXCEPT the
  mouth-corner hook (cv_w 0.396, ratio 1.73) which sits between the bands;
  needs a donor-size/curvature signal, not more threshold tuning.
- Next: iteration 17 from BACKLOG (capsule apex nub / mouth-corner hook /
  donor stump / heart top-left lobe arc-aware support / wheel-arc
  nondeterminism pinning).

### Run 17: nondeterminism root cause — medial_axis rng, not k-means (RESEARCH)
- Timestamp: 2026-07-08 04:30
- What changed: nothing (measurement only, while it17 A/B agents in flight).
- Result: k-means exonerated (seeded; label chains hash byte-identical);
  divergence isolated to capsule stroke paths; svgcore.fit_open stable;
  root cause = skimage medial_axis(rng=None) permutes tie-pixel order +
  consumes global RNG. rng=0 pins it in-process and cross-process.
- Insight: one mechanism explains the wheel-arc variance, 195-200/64-68
  stroke-count wobble, mountain crevasse shuffle, and the ~8k px diffpx
  floor. The "k-means nondeterminism" folklore in earlier entries was wrong.
- Next: one atomic rng-pin commit at it17 integration (6 call sites:
  contours_exp 353/441/1122/1153, strokes 99/123) + fresh eye pass on all
  touched targets (tie-picks shift once, then freeze).

### Run 17 addendum: monster light-loss map — teeth lead found (RESEARCH cont.)
- Swept all thin light-on-dark tophat components vs current render: 12
  qualify, none fully missing -> run-13 "dropped white scratch" CLOSED
  (eye-verified at the 3 lowest-presence spots, diag17_scratch.png).
- NEW eye-loud lead on the focus target: mouth TEETH render as soft scallops;
  original + Recraft = sharp zigzag (~x430-560/y230-280). Fill-fitter
  smoothing eats the serration — the run-10 corner+miter cure never reached
  light-region boundaries. Promoted to top it18 candidate.
- Mouth-corner hook now has a picture: wobbly thin curl (presence 0.51).
