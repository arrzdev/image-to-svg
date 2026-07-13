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

### Run 17 addendum 2: teeth degradation staged — despeckle erodes, fitter rounds
- Stage strip (ORIGINAL/rawquant/despeckle/smooth/dissolve/RENDER,
  diag17_teeth_stages2.png): quantize preserves tall sharp teeth;
  _despeckle_labels+_smooth_labels erode spikes to ~half height; the fill
  fitter rounds the remaining nubs into scallops.
- it18 design: label-side spike guard (boundary-subpart protection — run-14
  guard covers whole components only) + fitter-side corner preservation
  (run-10 cure for dark bands, extended to light regions). Natural A/B pair.

### Run 17 addendum 3: deep-zoom hairline bug triaged — v5 already clean except pizza-box eversion
- structcheck on v5 HEAD shared-boundary emissions: shield 1.000,
  logo-badge 1.000, elephant 1.000 — the BACKLOG "0.1-0.8" bug was v2/v3-era,
  closed for v5. pizza-box 0.875: 166 hairline px in two clusters; worst
  (285,170)@1024 = hairline crack + everted gray lens (eyed,
  diag17_pizza_gap.png) = the known thin-region eversion, now with coords.

### Run 17 addendum 4: lattice-tangle probe — not located; strap-curl pictured
- Junction-density probe on chopchop's dark skeleton (826 deg>=3 nodes) top
  clusters = strap (268,617), goggles rim (571,327), coconut (217,760) —
  diag17_lattice.png. Strap-end curl lead CONFIRMED with picture (current
  loops where original tapers); goggles junction mild pooling only; coconut
  scratch daubs lateral. The chair-lattice tangles did NOT surface via dark
  junction density — bars likely non-dark or tangles not junction-dense;
  next attempt needs run-15's grid coords, not this heuristic. Negative
  result logged so the heuristic isn't retried blind.

### Run 17 addendum 5: rectangular-nub audit + lattice tangles located
- Nub mechanism found: strokes are round-capped; wedge/ribbon elements are
  filled polygons with flat width-spanning ends (209 on chopchop). Pictures:
  flat lattice-bar butts (425,790), maroon slab ~(600,640), diag17_nubs.png.
  Fix candidates: semicircular ribbon end arcs, or short-ribbon->stroke.
- Chair-lattice tangles finally LOCATED at (425,790)@1024 (the ribbon
  first-node listing walked straight into the lattice the junction-density
  heuristic missed): tangled knot glyph + doubled bars.

### it17 A-apexsnap: orchestrator VERIFIED (beats prev) — awaiting B
- Agent's corrected diagnosis: apex nub = fill fitter curling the tip of a
  corridor-carried sliver of the 719k-px background component (NOT capsule
  overshoot). Fix: absorb only corridor-carried sliver pixels >6px reach
  from the out-of-corridor body (measured margin: grazes max 5.0 vs carried
  mass 8-53). Capsules 5/5 unchanged; only monster fires.
- Orch verification (own renders, artifact new vs orch-own prev vs recraft):
  apex nub GONE (560,690); mid-segment (600,712) cleaner (no double render);
  other spots + 4 full-coverage pages identical/lateral. Zero regressions.
- Agent leads: fill-fitter tip-curl family (swoosh hooks?); confirms
  in-process wobble beyond k-means (= our medial_axis finding); Recraft's
  sharp-Lambda apex needs corner-aware capsule fit (run-10 style).

### Run 18: determinism pin — medial_axis rng=0 (KEEP, infra) — commit da5d4b6
- Timestamp: 2026-07-08 03:05
- What changed: rng=0 at all 6 medial_axis call sites (contours_exp
  353/441/1122/1153, strokes 99/123) = integration step 1 of it17,
  done orchestrator-side while B-arcsupport ran.
- Result: monster render byte-identical across runs AND processes
  (probe d68bde3c39; was 4/4 different). Eye pass on the one-time tie-pick
  shift: 5 targets all lateral (orch17_pin_*.png), no welds/losses.
  Sanity flat: monster 0.9595, elephant 0.853.
- Insight: eye-diffs and diffpx spot-finding are now noise-free — future
  broaden sweeps can trust "byte-identical = skip" far more often.
- Incidental lead: rabbit coat BUTTONS render as thin line + hook in both
  new and prev (original + Recraft show two circles), ~(358,676)@1024 —
  pre-existing, filed to BACKLOG.
- Next: A-apexsnap integration onto pinned main once B-arcsupport reports.

### Run 19: A-apexsnap integrated — quality_monster=0.9591 (KEEP) — commit 1e0adb6
- Timestamp: 2026-07-08 03:20
- What changed: A's corridor-carried sliver absorption applied to pinned
  main (clean 3-way patch). Deterministic renders made the re-verify crisp:
  new vs pinned-prev differences are exactly A's fix, nothing else.
- Result: apex nub gone (560,690), mid-segment double-render gone (600,712),
  left-end kink cleaner (524,732); 4 full-coverage pages zero regressions;
  monster sanity 0.9591 flat, points 815->773 (simpler output).
- Insight: with determinism in, integration re-verification no longer fights
  the tie-jitter noise floor — first iteration where "only the fix changed"
  is literally provable from the diff of two renders.
- Next: B-arcsupport verdict when it reports; then it17 ship + docs.

### Run 20: B-arcsupport integrated — rabbit heart CLOSED (KEEP) — commit c61755e
- Timestamp: 2026-07-08 03:35
- What changed: arc-aware endpoint bridging pass (free end x any endpoint,
  tangent-arc / strict-chord, ridge2 both-sides-light gate). Run-15 >72deg
  folklore corrected: real blocker = endpoint consumption by midpoint
  bridges.
- Result: rabbit heart top + tuft apex closed; chopchop trunk outline x2 +
  cup rim + chair micro-break, 0 welds; elephant/monster/fox BYTE-IDENTICAL
  (deterministic no-side-effect proof). 9 focus spots + 8 full-coverage
  pages eyed. Sanity: rabbit 0.7492 (idealization penalty), elephant flat.
- it17 complete: research (17) + rng-pin (18) + A-apexsnap (19) + B (20),
  four keeps, two worktrees removed. Iteration wait-time yielded 5 diagnosis
  addenda + it18 brief.
- Next: iteration 18 from research/it18/brief.md (teeth A/B pair).

### it18 wait diagnosis: buttons/ring die in the LABEL CHAIN (correction)
- Stage strip diag18_buttons.png: rabbit button ring + strap J-curve are
  INTACT at rawquant, broken to "u"/")" hooks by despeckle/smooth, render
  faithfully reproduces the broken labels. Run-20 "skeletonization" guess
  corrected in BACKLOG. Dark-on-light dual of the monster-teeth disease —
  natural extension of it18 A-spikeguard if it ships.

### it18 wait diagnosis 2: heart-crown flattening staged — label chain again
- diag18_lobe.png: crown intact at rawquant; despeckle displaces the thin
  left-lobe apex outline with a shadow-tone blob + shallows the notch;
  fitter rounds the remainder. Third label-chain thin-boundary casualty
  (teeth = light spikes, buttons/ring = dark annuli, lobe = outline arc).
  One generalized guard could close the family — hinges on it18 A's design.

### it18 wait diagnosis 3: strap-end curl attributed to stroke layer
- Layer-strip render (diag18_curl.png): the curl reproduces in STROKE-ONLY —
  free-end/ribbon shaping, distinct from the run-19 fill-fitter tip-curl
  family. BACKLOG items stay separate.

### it18 wait diagnosis 4: width-constancy metric — component-level is useless
- Whole-component cv_w on elephant: ours 0.295, recraft 0.363, source 0.355
  (n=5 components) — "we beat Recraft", i.e. the granularity is too coarse to
  see perceived wobble. Monster's dark mask is fill, not lines (crashes the
  approach). A viable line-consistency metric needs junction-to-junction
  branch decomposition + separate light-line handling. Filed under Judge
  upgrades; no metric work shipped (harness stays locked).

### it18 wait: chopchop scribble-nondeterminism item closed (verified)
- Double render post-pin: byte-identical (b4510fe016 x2). Run-15 observation
  was the medial_axis tie-order; BACKLOG item closed against run 18.

### Run 21: B-cornerfit integrated — corner-pinned fills (KEEP) — commit c51d025
- Timestamp: 2026-07-08 03:35
- What changed: corner detection on raw fill edges (turn>=80 @k=6, two-scale
  localization) + per-piece parsimony fits pin V-notches as hard vertices.
- Result: teeth scallops -> sharp Vs (half-height; A owns the label side),
  eye wedges; broad sharpness win verified by orch renders (mountain pines,
  fox fur, crystals facets, logo-badge blades); controls smooth; monster
  sanity 0.9584 flat, points 773->701. Artifact chain integrity: candidate
  prev AND integrated render byte-identical to canonical/artifact.
- Leads: mouth-corner swoosh square-step = capsule/fill SEAM (not fill fit);
  pinning-before-fit beats alphamax tuning.
- Next: A-spikeguard verdict; combination should compound to full-height
  sharp teeth.

### Run 22: A-spikeguard integrated — severed-tip rescue; A+B COMPOUND lands (KEEP) — commit ea329bd
- Timestamp: 2026-07-08 04:00
- What changed: despeckle rescues anchored, contrast-extremal (gap>=210)
  severed spike tips and welds them via clean corridors. diag17 corrected:
  the half-height kill was discrete tip-severing at quantize.
- Result: corner tooth full height; COMPOUND with run-21 corner pinning
  eye-verified: teeth tall AND sharp, approaching Recraft. 5/6 broaden
  byte-identical; chopchop lattice reshuffles equal-quality, planks flat
  (the 128-false-rescue naive-gap landmine was real and dodged). Sanity
  monster 0.9587 / elephant 0.853 flat.
- it18 complete: 2 dispatched, 2 shipped, compound verified; 6 wait-time
  diagnoses banked. Next headline (it19): generalize A's rescue+weld to the
  thin-boundary family (rabbit buttons/ring, heart crown, cream-on-ink).

### Run 23: it19 — B-ribboncap ships, A-darkguard discarded — commit a8d728d
- Timestamp: 2026-07-08 04:50
- B-ribboncap (KEEP): round-cap ribbon/wedge polygon ends via separate cap
  subpath; bodies byte-identical, only cap crescent added. chopchop 347 caps
  (dark ribbon ends round to original+recraft), monster byte-identical,
  rabbit 92 / fox 15 clean. END-CAP rounding, NOT line-body.
- A-darkguard (DISCARD/hold): dark-subfeature rescue+weld in despeckle
  (dual of it18-A). Regression-free (chopchop landmine clear, monster
  byte-identical) but NO visible win — proved the contour_lines FITTER is a
  co-bottleneck: the lower button's label map is a solid dark dot in BOTH
  new and prev yet renders as a 'u' hook in both. Label-side half is ready
  to compose once a fitter-side "small isolated dark region -> filled
  dot/closed loop" fix exists. Do not ship dead code for no visible gain.
- ⚠ USER STEER (mid-iteration): top defects are line OVER-ROUNDING
  (heart->circle, pizza straight lines), OVER-JOINING, and loss of
  MEANINGFUL small details (rabbit paw fingers). Color match should target
  ORIGINAL not recraft. chopchop is THE benchmark. it20 re-orients to this;
  see [[user-visual-priorities]] memory + BACKLOG top.

### Run 24: recraft_gap.py tool (MEASURE) — it20 suspended on weekly API limit
- Timestamp: 2026-07-08 05:30
- USER asked: is ours-vs-Recraft SVG comparison a trustworthy speed-up
  signal? YES with caveats (direction gauge to the north-star, not a gate;
  can't detect passing Recraft; eye still decides). Built
  research/tools/recraft_gap.py: render-vs-render SSIM/deltaE + worst-tile
  ranking (mechanizes the per-grid-square review the user does by hand).
- Baseline at a8d728d CONFIRMS the user's eye: chopchop 0.868 = worst
  (their benchmark call), rabbit worst COLOR (dE 4.18), monster 0.989 best.
  Worst chopchop tiles (1,3),(2,3) = chair-lattice zone.
- it20 A-linefit/B-localcolor: both agents died pre-code on the weekly API
  limit (resets 4am Asia/Dubai). Re-dispatch both after reset — briefs
  preserved in iteration.json + BACKLOG top. Track recraft_gap as a
  secondary metric from run 25 on.

### Run 25: thin-dark-line lock (KEEP) — commit 5ad6d14 — 3 USER defects hit
- Timestamp: 2026-07-08 06:10
- Staged diagnosis first (diag20_heart_stages.png): heart outline+notch
  INTACT through rawquant/consolidate/mergeshadow, ERASED by despeckle+
  smooth (mode filter kills sub-3px lines); bridging closes survivors into
  the blob the user flagged. NOT the fitter.
- Fix: _thin_dark_line_lock in contour_lines.py — re-stamp pre-cleanup
  labels on true-ink thin elongated pixels after despeckle/smooth/dissolve.
  Ink-only (lum<60) is load-bearing: first attempt at lum<96 locked
  AA-fringe midtones -> phantom scratch dashes (run-25a, discarded inline).
- Eye wins: rabbit heart NOTCH restored + paw toe-hooks back; pizza-box
  straight edges continuous+straight (part of the user's straight-line
  defect was label-chain erasure, not only the fitter!); chopchop palm-crown
  tangle REDUCED + leg X-crack gone; shield seams continue. 10 targets
  byte-identical; monster teeth untouched. recraft_gap flat — thin lines
  are pixel-quiet; the gauge tracks big structure, eye stays the gate.
- Remaining (it20 A/B when limit resets): heart notch shallower than
  recraft (fitter depth); over-joining color guard; chopchop color bleed.

### Run 26 (measure): chopchop brown-bleed diagnosis + PROTOCOL UPGRADE (user steer)
- Timestamp: 2026-07-08 06:40
- Measured: green->brown bleed is only 347px total (one 291px cluster at
  (720,299)@1024). The page-1 "brown in fronds" impression = dark squiggle
  TANGLES at frond/trunk junctions + coconut mess, not wide palette bleed.
  B-localcolor re-scoped: junction cleanliness >> palette merge for chopchop.
- USER STEER (full steering granted): (1) bake recraft_gap into validation
  (never replacing eye); (2) culprit-pause protocol — every grid verdict
  must name WHY ours < recraft and the suspected pipeline stage; (3) framing:
  REACH recraft first, then surpass; (4) improve the harness itself.
  Implemented: autoresearch.md edits, GAP_LEDGER.md, recraft_gap --spots.

### Run 27: two-tier chroma gate on stroke candidates (KEEP) — ZZA + junction tangles
- Timestamp: 2026-07-08 07:30
- Culprit protocol first live use: diag'd ledger #3 (PIZZA ZZA squiggles) —
  letterforms lum~76/spread151 passed dark_lum<96 and got stroke-ified;
  fitter looped the Z corners. Measured 6 targets: ink = lum<60 (may be
  colored: rabbit navy spread 62) OR near-neutral spread<=45; saturated
  mid-darks are glyph/gem FILLS. Gate accordingly.
- Eye: ZZA crisp (~original); chopchop junction tangles LARGELY CURED
  (ledger #1 — the tangles were stroke-ified brown texture labels, not the
  stroke network's geometry at all); crystals drips gone; rabbit/monster/
  shield byte-identical. Flat <=45 gate REFUTED first (would de-ink rabbit).
- Gauge: chopchop rSSIM .868->.873, dE 2.81->2.66 — first eye+gauge
  agreement on a structural change. Ledger updated (items 1,3).
- Next: ledger #2 fitter straightness (checker bows remain); heart notch
  depth; A-linefit dispatch brief now sharper (bows+overshoots at crossings
  documented in diag26 grids).

### Run 28: chord-straight branch fit (KEEP, modest) + ledger-#2 negative finding
- Timestamp: 2026-07-08 08:00
- Raw-chord-straight branches (dev<=1.2px, len>=30px) emit L segments.
  Elephant: brow closer to original, ear corner crisper, -20% size. Fox
  neutral. pizza/rabbit/monster/chopchop byte-identical.
- LOAD-BEARING NEGATIVE: pizza checker bows unchanged — the bow is in the
  CENTERLINE (medial axis of the wobbly quantized band deviates >1.2px),
  NOT the fit. A-linefit brief updated: regularize/straighten the
  centerline polyline (or fit with line candidates at laxer tolerance);
  the fit call was the wrong lever.

### Run 29: fill-fit straight-piece prior (KEEP) — pizza straights land
- Timestamp: 2026-07-08 08:40
- Instrumented first: pizza checker grid = 100% FILL-layer (0 open branches,
  0 ribbons) — the run-21 parsimony fill fit was the bower, not strokes.
  Fix: TLS-line pieces between pinned corners emit straight cubics.
- Eye: checker horizontals RULER-STRAIGHT (user defect #1 visible progress);
  all-8-target size drop (simpler geometry); mountain/monster/rabbit/fox/
  elephant sweep — zero curve flattening. Residual: vertical hooks near
  junctions (fill-edge corner region) + heart notch depth -> A-linefit scope
  now surgical: junction-adjacent fill-edge behavior + concave cusp depth.
- Run 30 = maxRuns boundary next; prepare segment report.

### Run 30: SEGMENT CLOSE-OUT (maxRuns=30) — meta-review
- Timestamp: 2026-07-08 09:00
- Gauge at segment end: chopchop .871 (was .868 at run 24; dE 2.68 from
  2.82), elephant .981 (.970), rabbit .948 flat (COLOR gap: dE 4.16 =
  ledger #7), crystals .884/-.006 + mountain/fox -.007 dips on eye-verified
  lateral-or-better changes (gauge can't score better-than-recraft;
  crystals re-eye queued).
- META-REVIEW (what wins vs loses across runs 12-30):
  WINS: (1) measure-first staged diagnosis — every big keep this segment
  started as a stage-strip or instrumentation run (heart stages -> despeckle
  guilty; pizza probe -> 100% fill-layer; ZZA -> stroke-ified letterforms);
  (2) population-measured gates with margins (chroma two-tier, thin-line
  lock, spike gap 210) — every threshold set from measured true/false
  populations survived broadening; (3) label-chain guards + fit priors as
  a FAMILY (rescue/lock/pin/straight-prior).
  LOSES: (1) tuning the fit when the defect is upstream (runs 5, 28-neg);
  (2) naive single thresholds without population measurement (25a lum<96,
  27 flat spread<=45 — both caught before shipping); (3) walker/cap raises
  (run-15 postmortem).
  ARCHITECTURE: culprit protocol + GAP_LEDGER (run 26) measurably steered
  runs 27-29; recraft_gap agrees with eye on structural changes, silent on
  thin lines — both behaved as designed.
- Segment ends at budget. Next segment (user re-arms): junction-adjacent
  hooks + heart cusp depth (A-linefit surgical), color-guarded joining
  (ledger #5), buttons fitter dual (#6), color-to-original (#7, rabbit
  dE 4.16), crystals re-eye.

### Runs 31-32 (segment tail): crystals dip refuted; color measured vs ORIGINAL
- Run 31 (verify): crystals -.006 dip re-eyed at worst tiles — new==prev
  geometrically; low tiles = COLOR shift, not geometry. Logged as discard
  (nothing shipped).
- Run 32 (measure, ledger #7): dE vs ORIGINAL — rabbit 1.90 (FINE; its rdE
  4.16 vs recraft is RECRAFT's own deviation from the original — per the
  user's match-the-original rule, do not chase); crystals 3.82 = real hue
  drift (blue/pink centroid pull). Fix idea queued: post-assignment re-tint
  of region colors to the ORIGINAL region mean. Gauge caveat added: rdE
  compares to recraft, cross-check vs original before acting on color.

### Run 33 (segment-final): re-tint-to-original — DISCARD with a strong lead
- Naive region re-tint (mean of source pixels, cap 12): helps midtone fills
  (mountain -0.51, elephant -0.27, rabbit -0.15, fox -0.16 dE-vs-original)
  but pulls INK toward AA gray (monster +0.21, pizza +0.16) and misses
  crystals (means themselves drift-polluted). Reverted.
- LEAD (next segment, ledger #7): re-tint from ERODED region masks (exclude
  boundary/AA pixels), skip ink labels; expect the fill wins without the ink
  cost. Crystals may need per-facet means.
- SEGMENT 0 COMPLETE: 30 result lines. The Stop hook pauses here.

### Run 34 (segment 1): B-colorguard integrated — color-guarded joining (KEEP) — USER idea lands
- Timestamp: 2026-07-09 01:15
- _join_color_ok (RGB dist<=30) at all 4 join sites. Good joins are
  label-identical (dist 0); over-joins span 51-125. Margin >=21.
- Orch-verified: chopchop knot-hole weld -> clean ring, leaf brown-detours
  gone (106->83 joins); fox chin worm gone; rabbit back-spur/sleeve welds
  gone; heart/tuft/trunk still fire; 4 byte-identical; full grids clean.
- Ledger #5 (over-joining) CLOSED. B's culprit notes: chopchop smile barb
  is NOT a weld (persists with all cross-color snaps blocked) -> skeleton
  fork family, A-linefit scope; fox haunch dash chain -> ledger #6.

### Run 35: A-cusp integrated — heart notch FULL depth + pizza verticals straight (KEEP)
- Timestamp: 2026-07-09 02:40
- Both briefed defects proved STROKE-layer (layer-split proofs; run-29
  "all fill-layer" probe was flawed — patched strokes._ribbon missed the
  direct import; pizza grid = 45 ribbon strokes). M1 junction cusp descent
  -> heart notch deep-V ~= original/recraft, lobes/cheeks round. M2
  straight-chain lock (sagitta bow<=0.4; fit drift measured -2.75px) ->
  pizza verticals ruler-straight through crossings, ZZA intact.
- A+B interaction verified on integrated build; monster byte-identical.
- it21 COMPLETE: 2 dispatched, 2 shipped (runs 34-35). Ledger: #4 CLOSED,
  #2 residual CLOSED, #5 CLOSED (run 34). New leads: pizza crossing nubs +
  upper-band cell separators lost (label chain, pre-existing, eye-loud);
  chopchop smile barb = skeleton fork; fox haunch dash chain (#6).

### Run 36: B-perf integrated — 40x chopchop, byte-identical (KEEP)
- Timestamp: 2026-07-09 17:10
- cProfile found 88% of the v5->v8 regression in r35 _junction_cusp_exts
  (argwhere rescan per node x pocket, 275s of 311s); rest = full-frame
  medial_axis/EDT/dilation per component. Fixes: caching + padded-bbox
  locality; all byte-verified (18/18 worktree, 7/7 on main post-transplant).
- chopchop 298.5->7.4s, rabbit 31.4->3.5s: v8 now FASTER than v5. USER
  perf complaint resolved same-day. Ledger 0d closed (suspects corrected).
- Lead: files-pile now slowest (18.3s, different cost structure); vendored
  medial_axis LUT could save ~1.8s more on chopchop.

### Run 37: A-sharpen integrated (KEEP, judgment call) + 3 negative results
- Timestamp: 2026-07-09 19:00
- USER's sharpen recipe productionized (agent added anti-ringing clamp
  after the flat-art landmine FIRED as predicted: logo halo rims — clamp
  kills all). 9 wins / 7 lateral / 2 soft-gradient trades.
- NEGATIVE RESULTS (3 gate attempts, all measured): per-pixel smoothness
  blend prints zigzag SEAMS at the weight ramp (new artifact class);
  per-image ramp-fraction overlaps wins (mountain .239 vs chopchop .259);
  smooth-area label-flip overlaps too (app-asset's WIN is a big flip).
  The soft-gradient banding trade is not separable by cheap global stats.
- JUDGMENT CALL (stated in commit): default ON; shield rim-blob trade
  accepted vs 9 wins on the user's benchmark/defect list; presharpen=0
  escape hatch. it22 COMPLETE (runs 36+37). Cutting v9 milestone next.

### Runs 39-40: it23 complete — gradient flatten (USER-style recraft) + glyph rescue
- Run 39 B-icongeom: chromatic-mark rescue; Share + envelope restored;
  over-rounding exonerated; 0g closed; 0c discriminator measured (ab-shift).
- Run 40 A-gradientflat: bg gradients -> ONE solid like recraft; app-asset
  rings ALL gone; 0f closed. Verification hardened protocol followed: focus
  + all user-flagged targets re-eyed/byte-checked on the COMBINED build;
  baseline-gap script bug caught before misjudging (16-changed false alarm).
- it23: 2 dispatched, 2 shipped + run-38 hotfix inline. ITERATION BOUNDARY.

### Segment 2 armed: /autoresearch "past Recraft, beat last shipped every iteration" — v10 cut + it24 dispatched
- Timestamp: 2026-07-10 00:20
- Boundary work: audit24 committed (VISION.md = USER blueprint + absolute bar;
  FINDINGS.md E1-E8/P1-P4; ledger reframe + 0k monster reopened); v10 milestone
  cut at 01e80e0 (runs 38-40), v9 re-frozen to 678d98f, staged->v10, loop ->
  models/v10/src; segment-2 config appended (maxRuns 30); focus -> monster-flat-line.
- it24 dispatch (audit24 campaign, disjoint domains per runs-13-22 meta-review):
  A-transown = E1 transition-ownership in the label chain (app-asset shrapnel);
  B-lineintent = E4/E5 corner-pinned ruler-straightness in geometry/fit
  (monster 0k, zero quantize confound). E2/E3/E7/E8 queued behind.
- Keep bar this segment: beats v10 by eye at ZOOM; ledger close = ~Recraft
  absolute. Paper-mining agents (LIVE digest landed; 2nd batch pending) ->
  PAPER_NOTES.md when they report.

### Run 41 (measure): segment-2 re-baseline + recraft_gap harness fix — quality=0.8974 monster (DISCARD-by-convention, nothing shipped pipeline-side)
- Timestamp: 2026-07-10 00:55
- HARNESS FIX (deliberate, locked-harness protocol): recraft_gap.py pinned
  sys.path to models/v5/src — full-table runs with svg_ours=None rendered
  STALE v5 code ever since the live tree moved past v5 (~run 33). Now points
  at models/staged/src (symlink tracks live). Numbers in ledger's run-24
  table were v5-era-consistent; anything later from the full table is suspect.
- Also: v10 cut was missing the data/frontend/outputs symlinks (testbed
  import failed) — added, matching v9's layout.
- v10 LIVE baseline (10 recraft targets): app-asset .924/1.54 · chopchop
  .870/2.80 · crystals .886/3.64 · elephant .982/0.92 · fox .902/3.27 ·
  logo-geometric .985/0.62 · monster .987/0.32 · mountain .958/2.12 ·
  rabbit .950/4.11 · shield .937/2.28. These are the segment-2 alarm floors.
- PAPER_NOTES.md created with the full LIVE digest (UDF boundary-band color
  fitting -> E7/E1; component-init layer order -> E8; Xing validity check).
- it24 A-transown + B-lineintent still running in worktrees.
- Next: verify candidates on arrival (iteration.json next_action).

### Run 42 (measure): ramp-width census — NEGATIIVE, flaw named (DISCARD)
- Timestamp: 2026-07-10 01:20
- Edge ramp-width census (research/audit24/ramp_census.py) across 17 inputs:
  does NOT separate defect classes at native res — elephant 45% >4px tail vs
  app-asset 25.8% (inverted vs eye evidence); logo-lineart/geometric saturate
  (resolution+thick-AA confound); L=12 profile cap clips tails.
- Banked lead for A-transown/E2 briefs: measure ramps at the PIPELINE WORKING
  resolution, only at LABEL-BOUNDARY pixels (the E1 ownership decision
  points), normalize by local stroke width. Monster/logo-wordmark 0% >4px
  confirms the flat-art floor exists; the census direction is right, the
  coordinate frame was wrong.
- No pipeline change; candidates A/B still in flight.

### Run 43 (measure): E2 shadow census at working res — separation found (DISCARD-by-convention, measurement only)
- Timestamp: 2026-07-10 01:45
- research/audit24/shadow_census.py (fixed run-42 flaw: working res, ROI-scoped,
  pipeline label map via tb.labels()). Results (ramp p50 px @1024 / sig labels):
  DRAWN-FLAT controls: monster hand-lines 0.0/sat0/2, elephant ground 1.0/5.
  SOFT class: app-asset red-icon shadow 7.0/7, arrow 20.0/5, chopchop
  stool-under 9.0/7. rabbit ground 15.0/6 -> RECLASSIFIED soft: recraft
  IDEALIZES it into a crisp ellipse (class boundary = raster softness, not
  apparent intent). app-asset music ROI missed (-1, bad bbox) - redo in brief.
- E2 idealizer gate candidate (for it25 dispatch): region ramp p50 >= ~5px at
  1024 + low-sat + darker-than-parent + attached -> replace with ONE flat
  offset/dilated shape (or drop if lumDrop small, e.g. arrow shadow lumDrop 11).
  Fragmentation to undo: 5-7 labels per shadow today.
- Candidates A/B still in flight; A got a path correction (label chain is
  pipelines/quantize_contours.py).

### Run 44 (research): paper digests landed + forwarded to in-flight candidates (KEEP, docs-only)
- Timestamp: 2026-07-10 02:05
- All 8 batch-1 papers extracted (agent read the PDFs): full digests in
  research/docs/PAPER_NOTES.md with a ranked TRANSFERABLE IDEAS section
  mapped to root causes E1-E8.
- Direct hits on in-flight work, forwarded via SendMessage:
  B-lineintent <- Potrace alphamax (a=4gamma/3, >=1.0 sharp corner; long
  segments at slight angles = corners = drawing intent) + +-0.5px
  straightness certificate + direction test + corner-exclusion-from-
  smoothing (Depixelizing) + reminder that svgcore already has the potrace
  parsimony port (check what feeds it before writing new fit code).
  A-transown <- two-tier shading/contour edge classes (YUV merge vs contour
  thresholds), T-junction rule (contour edges continue, shading edges
  terminate), island/curve-continuation votes, decide-colors-last.
- New idealization-QA idea banked (BACKLOG-worthy): VectorArk degradation
  suite — render recraft targets small+blurred, run our engine, diff vs the
  clean geometry = automated idealization regression our eye-only gate can't
  scale to.
- Correction: Layered Semantic Simplification = arXiv 2406.05404 (the
  reference sheet's 2412.15673 is a trajectory paper; sheet is USER-verbatim,
  correction recorded here + PAPER_NOTES only).
- Batch-2 (judge/layering papers) agent was USER-cancelled; not relaunched.

### Run 45 (measure+PoC): 0h seam diagnosis — recraft is overlap-sealed; seal-stroke PoC works; NEW bug 0l isolated (DISCARD-by-convention)
- Timestamp: 2026-07-10 02:30
- structcheck census OURS (v10): coincident seams 30-87 px/kb on ALL 18;
  true open gaps only app-asset (score .412) + mountain (.488).
  RECRAFT: 7/10 overlap-sealed (seam=0 = "pro style"); monster via holes;
  their chopchop scores .072 at deep zoom -> recraft tolerates deep-zoom
  gaps on complex art; the bar is normal-zoom appearance.
- PoC same-color 0.06%-width strokes: seam 84/78/83 -> 0.7/0/0.4; monster
  right-eye gray smudge FIXED by eye (grids/seam_poc_monster.png, BASE vs
  SEALED vs RECRAFT). Trade: thin white cutouts shrink ~w/2 -> ship fix =
  underpaint dilation in paint order = E8 layered emission. 0h+E8 = ONE
  it25 candidate.
- NEW ledger 0l: app-asset/mountain open gaps = run-40 flatten boundary
  mismatch (geometry-level; strokes don't fix). Pairs naturally with
  A-transown's domain -> assess after A lands.

### Run 46 (tool): degradation suite built + v10 baseline — E3/E4/E5 proven engine-side (KEEP, tool+docs only)
- Timestamp: 2026-07-10 02:55
- research/tools/degradation_suite.py (VectorArk idea, run-44 backlog):
  clean recraft render -> degrade (0.45x bicubic + JPEG78 + upsample) ->
  live engine -> dSSIM/ddE vs CLEAN render. Ground-truth-clean idealization
  gauge, zero recraft-interpretation confound. Secondary signal only.
- v10 baseline: crystals .873/3.56, chopchop .877/2.93, fox .907, shield
  .924, rabbit .944, app-asset .949, mountain .960, elephant .978, monster
  .989, logo-geometric .990. Ranking == audit24 eye ranking (validates both).
- LOAD-BEARING eye finding (grids/degsuite_crystals.png): from a CLEAN
  flat-color degraded render the engine STILL deletes thin facet ridge
  lines, melts straight facet edges painterly, deforms highlights, varies
  ink weight. E3/E4/E5 are engine behavior, full stop — no source-noise
  alibi. B-lineintent's mechanism has a clean regression test waiting.
- Per-keep convention addition: record dssim_crystals + dssim_chopchop in
  jsonl metrics from now on (started this run).

### Run 47 (measure): 0l culprit corrected — gaps are E1 slivers, flatten exonerated (DISCARD-by-convention)
- Timestamp: 2026-07-10 03:15
- gradflat toggle: app-asset .412->.484 (flatten = only ~25% contributor);
  mountain BYTE-IDENTICAL (flatten never fired -> hypothesis refuted for it).
- Interior gap clusters localized (structcheck alpha map): app-asset 2
  clusters at the phone-edge shrapnel zone ((0.46,0.80) area 1556px@4096);
  mountain 1 at the peak fragment patches ((0.48,0.23) 1347px). Eyed both
  (z_0l_appasset_gap/z_0l_mountain_gap): torn micro-labels don't tile ->
  exposed-background slivers + invented white highlight blob. 0l = E1's
  geometric fingerprint; folds into A-transown acceptance (integrity ~1.0
  on app-asset/mountain = free objective check at integration).
- Runs-13-22 meta-lesson holds again: measure-first culprit testing beat
  the plausible-sounding suspect (flatten) before any code was written.

### Run 49 (verify-interim): B's interim artifact — over-straightening regression caught + fed back (DISCARD as-is; B iterating)
- Timestamp: 2026-07-10 03:45
- B dropped interim new.svg (no REPORT yet). Orchestrator-independent
  renders (verifyB_hand.png / verifyB_mouth.png):
  (1) head dome silhouette now flat-cut with corner kinks = straightness
  gate firing on gentle arcs (the briefed landmine, live). Fix sent: whole-
  run +-0.5px certificate / arc-fit rejection, not short-window flatness.
  (2) left eye degraded; (3) hand hairline UNCHANGED - may live outside
  the fill-boundary layer B is editing (layer-split strip requested);
  (4) teeth unchanged.
- Value of interim verification: regression caught while B is still in
  the loop, not at integration. The P2 lesson (zoom or it didn't happen)
  applied to a candidate mid-flight for the first time.

### Run 50 (verify-interim): A-transown preliminarily VERIFIED on 4/4 dropped pairs (logged discard-by-convention; keep decision at integration)
- Timestamp: 2026-07-10 04:10
- Orchestrator-independent renders (verifyA_{icons,phone,fox,rabbit,chop}.png):
  app-asset white blob GONE + specks reduced + integrity .412->.988 (0l
  objective check PASSED); fox ink debris gone; rabbit spur/tears reduced
  (tuft landmine ok); chopchop outline daubs reduced. No regressions at
  these zooms. Shadow moats/screen strips remain = E2 scope (correct).
- Note: slight frame offset in chopchop panels (viewBox variance?) —
  re-check via tb.crops at integration.
- Pending: A REPORT.md (mechanism/populations), crystals+monster landmine
  evidence, mountain integrity, full broaden. B iterating on run-49
  feedback.

### Run 51 (verify-interim): B-v2 hand FIXED at zoom; A complete w/ report; mountain discrepancy reconciled (DISCARD-by-convention)
- Timestamp: 2026-07-10 04:40
- B-v2 (post run-49 feedback): hand hairline = straight segments + sharp
  corner ~= recraft structure (verifyB2_hand.png) - 0k hand defect fixed
  pending landmines; eye crisper than PREV; crystals long facet edges
  straighter, no regression; dome TOP facet residue remains (hardest
  low-curvature case); teeth unchanged. Checklist sent (dome trade
  quantification ok, teeth layer attribution, REPORT + landmines).
- A COMPLETE: report consistent with my independent run-50 checks;
  mechanism = _own_transitions (thin non-ink Lab-segment components absorb
  into nearer bound; stroke-components never count as bounds = rabbit brow
  save); every gate population-measured; monster/crystals/shield/pizza/
  elephant/mountain byte-identical. HONEST NEGATIVE banked: high-contrast
  E1 subclass (pizza dashes, fox in-ink debris, shield flecks) NOT
  color-separable - needs geometry signal or E8 layering; do not retry
  color gates blind.
- Mountain integrity reconciled: main fresh render == audit24 svg bytes,
  0.488 reproduces; A's 1.0 was worktree-side - recheck on integrated
  build; mountain gaps NOT fixed by A (byte-identical) -> 0l mountain half
  stays open, likely A's "3-label blend" subclass.
- Next: B's REPORT -> then integration (A first, then B), broaden 18,
  keep decision.

### Run 52 (integrate): A applied + verified in integration worktree — mountain surprise WIN (DISCARD-by-convention until ship)
- Timestamp: 2026-07-10 05:10
- A's diff (141 insertions, quantize_contours.py + contour_lines.py wiring)
  applied cleanly off 1173cf8. Verification: app-asset integrated render ==
  A's artifact BYTES (r21-style verdict transfer) + integrity .988;
  monster + crystals byte-identical to v10 baseline (landmine claims
  CONFIRMED); mountain NOT byte-identical (A's report claim wrong there)
  -> mandatory eye-check: WIN (peak stain fragments absorbed, ridge
  boundary cleaner, hills unchanged; verifyINT_mountain_{peak,hills}.png),
  integrity .488 -> 1.000. Ledger 0l: BOTH halves fixed by A.
- Process note: "byte-identical" claims from candidates get re-checked on
  the integrated build ALWAYS (this one was wrong in the lucky direction).
- Holding ship one cycle for B's REPORT (hand fix verified run 51); then
  apply B to the same worktree, re-eye, broaden all 18, keep/ship.

### Run 53 (verify-interim): B landmines pre-cleared at my zooms (DISCARD-by-convention)
- Timestamp: 2026-07-10 05:40
- verifyB2_{logo,pizza,eleph,chopface}.png: logo circles round + apex sharp
  (the critical straightener landmine PASSES); elephant/chopchop curves
  smooth, no faceting; pizza lateral+. Combined with run-51 (hand FIXED,
  eye crisper, crystals facets straighter): B verifies on everything I can
  render. Known blemish: dome-top facet residue (quantified trade pending
  in its REPORT).
- Layer attribution confirmed: B's diff = contours_exp.py (STROKE layer),
  not boundary.py — the run-49 "which layer is the hand hairline" question
  answered; scope extension was legitimate per brief (layer-split proof).
- B uncommitted; integration step 2 waits for its commit + REPORT.

### Run 54: it24 A-transown SHIPPED (KEEP) — first pipeline keep of segment 2
- Timestamp: 2026-07-10 06:10
- Broaden 18/18 clean (10 byte-identical incl all landmines; 8 changed all
  eye-verified: 5 wins + 3 lateral+). Shipped to main 8ea46c9. Ledger 0l
  CLOSED (app-asset .988 / mountain 1.000 integrity, eye-verified).
  Gauges up: rssim app-asset .925, degsuite .951. Honest negative ->
  BACKLOG (high-contrast subclass needs geometry/E8).
- B next: verification pre-passed (runs 51/53); awaiting its commit.

### Run 55 + it24 close-out: B SHIPPED; v11 milestone cut — ITERATION BOUNDARY
- Timestamp: 2026-07-10 07:00
- B shipped 8315d66 (0k hand CLOSED; teeth residual -> E5; seam curls ->
  0h). A+B interaction set eye-verified neutral-to-positive. Main render ==
  B artifact bytes; gauges pixel-quiet (documented thin-line behavior).
- v11 CUT (transition ownership + line-intent stage 1; first audit-24
  campaign milestone); v10 re-frozen to 0c86ca9; staged->v11; loop docs
  repointed. Worktrees cleaned (main only remains).
- it24 COMPLETE: 2 dispatched, 2 shipped. Segment 2: runs 41-55, 4 keeps
  (2 pipeline, 2 research/tooling), 11 measurement/verify discards - every
  one with banked leads.
- NEXT: it25 dispatch (C-layeremit E8+0h, D-shadowideal E2) per BRIEFS.md.

### Run 56 (harness maintenance): autoresearch.sh repointed to staged — TRUE v11 baseline quality=0.8981
- Timestamp: 2026-07-10 07:20
- autoresearch.sh was still pinned to models/v9/src (frozen at run-37 state
  since the v10 cut) — the segment's identical 0.8974 readings were STALE.
  Same bug class as run-41's recraft_gap fix; the v10 cut checklist missed
  the harness repoint. Fix: models/staged/src (symlink tracks live) — bumps
  are now repoint-free. No verdict was corrupted (the metric never gates;
  the eye did all gating). New true baseline on v11: quality 0.8981.
- Memory (repo-layout) updated with the complete cut recipe including both
  staged-pointer fixes and the symlink footgun.

### it25 DISPATCHED: C-layeremit (E8+0h) + D-shadowideal (E2)
- Timestamp: 2026-07-10 07:45
- Both worktree candidates launched off b6c94e0 (v11 live) with full
  briefs: C = per-shape layered emission + underpaint dilation seal
  (run-45 PoC + recraft overlap-sealed evidence; acceptance = seams ~0 on
  flat targets with NO thin-feature width change, monster mouth/eye
  hairlines gone by eye); D = shadow idealizer on run-43 measured gates
  (acceptance = app-asset moats -> one clean offset shape or dropped,
  rabbit ground -> crisp shape, controls untouched, monster byte-identical
  expected). Both must pass degradation-suite non-regression.
- Orchestrator protocol per it24 lessons: interim verification on first
  artifact drops; byte-claims re-checked on integrated builds; C
  integrates first (emission downstream of D's labels).

### Run 57 (measure): E5 teeth census — recraft AMPLIFIES the repeat; ours drops tips below prominence (DISCARD-by-convention)
- Timestamp: 2026-07-10 08:05
- teeth_census.py (mouth top-edge zigzag profile @2048; caveats: one
  window, 4px prominence): ORIGINAL 7 tips / spacing CV .09 / depth 11.4px;
  RECRAFT 5 tips / CV .32 / depth 18.2px (fewer, BIGGER, DEEPER = amplify+
  simplify the repeat — sharpens VISION item 6); OURS 3 detectable tips /
  CV .69 / depth 10.5 (most tips blunted below prominence; matches B's
  lattice attribution).
- it26 E5 acceptance (quantified): >=5 detectable teeth in this window,
  depth ~18px-class, spacing CV <=~0.3 — PLUS the eye at deep zoom.
- Detector needed 2 debug fixes (wrong edge, wrong bbox — eye smudge mask
  caught it); logged within the 3-attempt cap.

### Run 58 (measure): 0b pinstripe staged probe — label chain exonerated; culprit = stroke routing/absorption (DISCARD-by-convention)
- Timestamp: 2026-07-10 08:30
- stripe_probe.py: the maroon pinstripe keeps its own label (51,33,16,
  100% share) through quantize/consolidate/own_transitions/despeckle/
  smooth/dissolve. NOT a label-chain kill. Centroid lum~36 < 60 = ink-class
  by the two-tier gate -> routed to strokes -> absorbed by the parallel
  heavy black edge (skeleton pooling or ribbon coverage; run-34 join guard
  can't fire pre-join). it26 first step: stroke-layer-only strip at the
  strut. Note: 56 core px @1024 - the stripe is sub-2px and mostly blended;
  Recraft re-draws it at full strength (amplify, like the teeth run 57).
- Pattern echo: 0b joins runs 28/47 as "the plausible suspect was innocent"
  - three staged probes, three exonerations. Measure-first keeps winning.

### Run 59 (measure): 0j paw probe — label chain exonerated again; E3 family points downstream (DISCARD-by-convention)
- Timestamp: 2026-07-10 08:50
- paw_probe.py: paw white interior (share .95) + ink outline (.96) both
  survive the full chain. Combined with run 58 (0b stripe survives too):
  the E3 boundary-destruction family is NOT a label-chain problem on these
  two cases - it lives in stroke extraction/network merging or fill
  emission. This REVISES audit24's E3 framing (was: "despeckle/dissolve
  cannot tell drawn lines from noise" - true in it19-22 era, but the locks
  shipped since then hold; the remaining destruction is geometric).
- Caveat: bbox covers the paw core; the finger-vegetable contact zone needs
  a render-diff-guided re-probe (it26 first step, with the 0b stroke strip).
- it26 brief shape firming up: ONE stroke-network candidate covering 0b
  absorption + 0j junction mangling + E5 teeth amplification (all
  stroke/geometry-stage, all with measured acceptance).

### Run 60 (docs): it26 brief written — E-stroke consolidates 0b+0j+E5 (KEEP, docs-only)
- Timestamp: 2026-07-10 09:05
- research/it26/BRIEFS.md: one stroke-network candidate for the whole
  downstream family the diagnosis sweep isolated (runs 57-59), with
  measured acceptance per sub-defect and the historical landmines
  (snap radii, color guard, B's anchor machinery is load-bearing).
- Orchestrator prep queue is now fully drained: it25 verification is the
  only remaining work and it gates on candidate artifacts.

### Run 61 (verify-interim): C's first drops — seams dead, eye smudge fixed; white-detail shrinkage watch-item fed back (DISCARD-by-convention)
- Timestamp: 2026-07-10 09:30
- My renders confirm C's stats: seam 77/30/33 -> 0 on monster/rabbit/
  shield, integrity 1.0, monster eye smudge GONE (the run-45 PoC target),
  shield ring cleaner. Teeth widths unchanged.
- Watch-item (fed back with quantitative check): monster left eye + shield
  knob highlight slightly smaller at deep zoom -> light-on-dark details may
  sit BELOW dark neighbors in the paint order, so underpaint dilation eats
  their edges. LIVE area-ordering (small=later=on top) is the fix shape.
- Interesting: monster output SHRANK (431->233 points) under per-shape
  emission; rabbit/shield +33% KB (expected E8 trade).

### Run-43 correction (from D-shadowideal's interim census, 2026-07-10)
- D's target-wide census v2 AMENDS run 43: (1) the raw ramp-p50 measure does
  NOT reproduce on rabbit's true shadow against JPEG noise (needs
  band-neighborhood sampling + smoothed profiles — use D's shadow_census2
  form, not audit24/shadow_census.py, for future gates); (2) app-asset icon
  "moats" are LIGHTER bg-gradient glow remnants, not dark shadows — recraft
  DROPS them (drop-only path, not offset-shape); (3) new measured landmine:
  glyph wedges inside icons are statistically shadow-like — separator =
  field >= 6% of frame; (4) hue-similarity gates unusable (rabbit designed
  mauve, ab-shift 30) — softness stays load-bearing, as briefed.
- Lesson: my 7-ROI census was directionally right (class separation exists)
  but its exact statistic was fragile; target-wide re-measurement by the
  implementing candidate caught it BEFORE any threshold shipped. This is the
  population-first discipline working end-to-end.

### Run 62 (prep): full-18 v11 baselines + seam table (DISCARD-by-convention)
- Timestamp: 2026-07-10 10:40
- research/baselines/v11/*.svg (fresh main renders) + seam/integrity table.
  it24 wins held everywhere (app-asset .988, mountain 1.000); game-assets
  .944 = only integrity residual (pre-existing). Seams 28-87 px/kb on 17/18
  targets (logo-lineart 0 = all-stroke output) — C's improvement surface.
  C/D broaden byte-compares now use baselines/v11, NOT audit24/svg (v10-era).

### USER STOP (budget ended) — loop off; it25 winding down
- Timestamp: 2026-07-10 (USER directive mid-it25)
- .autoresearch-off set. Both candidates sent finalize-now directives:
  C = commit + REPORT (objective checks all green orchestrator-side;
  integration-ready pending its report); D = commit WIP + handoff REPORT
  (census+corrections done, mechanism unplumbed).
- Segment 2 totals at stop: runs 41-62; it24 SHIPPED as v11 (transition
  ownership E1 + line-intent E4/E5; ledger 0l closed, 0k hand closed);
  it25 C at final verification (seams->0 everywhere, degsuite IMPROVED),
  D mid-build. it26 brief ready (E-stroke: 0b+0j+E5).
- Resume path documented in iteration.json next_action.

### Run 63: it25 C SHIPPED — ledger 0h CLOSED; loop stopping (USER)
- Timestamp: 2026-07-10 (final run of the session)
- C integrated + shipped at ff05495 (byte-transfer verification: integrated
  monster+shield == C artifacts, seam 0, integrity 1.0). 0h closed on all
  18 targets. New culprit notes filed (E1 residual eye label, 0g rivet).
- D = WIP handoff (worktree commit + REPORT requested; resume next session).
- Loop OFF. Next session: D resume/re-dispatch -> it26 (E-stroke brief
  ready) -> E7. v12 cut decision next session (A+B+C = clearly structural).

### D-shadowideal handoff landed (post-stop): plumbed + candidate-verified, integration-ready
- Timestamp: 2026-07-10 (after run 63; no run logged — USER stop in effect)
- D finished further than directed: _idealize_shadows plumbed (commit 407db19
  in its worktree), candidate eye verdicts: app-asset WIN (7/7 moats gone,
  bg flat = recraft), 6 landmines byte-identical (incl monster), rabbit
  honest LATERAL (measured non-separability vs elephant's drawn control),
  mountain 2px peak nub flagged. 3 refuted mechanisms banked. REPORT.md +
  14-target artifacts in research/it25/candidates/D-shadowideal/.
- NOT integrated (USER budget stop) — next session's first action per
  iteration.json. D's worktree preserved.

### Run 64: edge-11 corpus benchmark (first ever) — tilecmp=0.2487 live / edge-11 0.3376 (DISCARD, measurement)
- Timestamp: 2026-07-12 (segment 3 opens: goal = never stop improving; tilecmp gate regime)
- What changed: nothing in the engine — measured models/edge-11 across all 11 paired stems vs the quant-13 gate baseline (research/design/bench_edge11.py, artifacts research/edge11_bench/).
- Result: edge-11 loses 10/11 stems, corpus 0.3376 vs 0.2487. Channel autopsy: color +0.163 (RAG merge ΔE22, no palette idealization = the disease), census +0.062, flow +0.042. WINS: pizza-box overall −0.020 (census −0.036, flow −0.058), app-asset flow −0.065. Robust: 11/11 ran, 2-5 s/stem. monster-flat-line collapsed to 8 paths (grayscale kills the line detector).
- Insight: the USER's stroke-synthesis architecture wins exactly where structural straight lines dominate (pizza box text/edges, app-asset arrows) — digitally-perfect strokes beat traced ones there. As a whole engine it's not a competitor (color/fragmentation).
- Next: (a) graft lead → BACKLOG: quant-13 fills + edge-11 synthesized-stroke layer; (b) run 65 = adjudicate the 5 stashed sub-bar patches as a BATCH (batching resolves the gate-recalibration question without touching the locked gate).

### Run 65: SHIP it9 wander-erasure + gate recalibration + quant-14 — tilecmp=0.2457 (KEEP)
- Timestamp: 2026-07-12
- What changed: (1) stash adjudication: it3_localsplit/it6_rampband/it7_transmud turned out ALREADY SHIPPED in the pre-cut merges (their symbols live in the tree; the "5 stashed patches" memory was stale) — only it9 wander-erasure was real cargo; it10_satink dropped (+0.0000). (2) it9 re-validated solo on current tree in a worktree with the CORRECT engine (quant-12 wrapper — first attempt swept raw quant-11 and produced a phantom 0.0010 drift; lesson below): +0.0029 exactly reproduced, census −0.0068, flow −0.0027, color +0.0007 < eps. (3) Eye audit (shield/app-asset/chopchop, before/after on top-changed regions): shield rim wobble GONE, app-asset shadow-fringe teeth GONE, chopchop deltas invisible → ship confirmed. (4) MIN_GAIN 0.004 → 0.0015: deliberate, documented recalibration to the MEASURED 0.0000 deterministic floor (the 0.004 was provisional per its own comment; CH_EPS 0.006 unchanged as the anti-overfit guard). (5) it9 applied to models/quant-11/src (298ee06), baseline re-frozen FROM the candidate sweep pickle (bit-identical engine — saved a redundant 10-min sweep), quant-14 cut (entry byte-equivalent to quant-13's wrapper), staged → quant-14.
- Result: corpus 0.2487 → 0.2457 (−1.2%). New best.
- Insight: (a) ALWAYS sweep the wrapper engine the gate froze (quant-12), not the raw tree entry — the retuned DEFAULTS + straighten post-pass shift all channels ~0.001-0.009. (b) A stash label's gain can survive tree drift exactly when its domain is disjoint from the drift (it9 = fitter-input polyline; shipped trio = label-map ops). (c) Baseline-from-candidate-sweep is a legitimate freeze when the ship is byte-identical to the swept worktree.
- Next: run 66 = color campaign (--brief targeting COLOR; color 0.1784 is the best channel absolute but the largest Recraft-gap mode share). Then [graft-strokes] from BACKLOG.

### Run 66 side-note (while it66 agent runs): [edge11-grayscale] RETRACTED
- Population-measured the wall-ink hypothesis (monster/elephant/chopchop): refuted — monster walls are LIGHTER than their cells (p50 −103; ink forms CELLS, not walls). Stage rasters eyeballed: monster-flat-line is a black silhouette; edge-11's 8-path output is structurally correct. Original backlog item was a number-inferred misdiagnosis (path count, no render) — the ban on number-only verdicts applies to benchmark tables too. BACKLOG corrected; graft plan (run 67) not blocked.

### Run 66: SHIP it66 structured-split recalibration (worktree agent) — tilecmp=0.2442 (KEEP)
- Timestamp: 2026-07-12
- What changed: first worktree-agent iteration of segment 3. Brief targeted UNDER-RESOLVE (crystals 30 omitted strokes in region [0.52,0.5,0.62,0.6]). Agent diagnosed the omitted paths as compact dark facet FILLS (0/32 thin) blocked by _split_structured_regions' blanket dark-skip; recalibrated eligibility (ink-rule per stroke-layer candidacy + saturation escape spread>70 + ef floor 0.03 behind maxde>=17 rescue bar), population-measured every threshold (fox false-fire 16.4 set the 17 bar). Its 3rd gate run passed at +0.0015 — exactly the recalibrated bar (would have been blocked under 0.004: recalibration paid off same-day).
- Result: wrapper independent gate CONFIRMED: 0.2457 -> 0.2442, census -0.0016, color -0.0033, flow +0.0004 < eps, UNDER-RESOLVE share 20.0% -> 18.8%; merged 70d43aa, baseline re-frozen. Orchestrator eye pass (OWN renders, not agent's): crystals dark-red waves + cyan-gem rim + pink-gem band recovered; pizza lid-crease "leech" blob confirmed as disclosed (localized; net pizza -0.0043) -> GAP_LEDGER it66-leads with two more low-contrast facet leads. quant-15 cut, staged repointed.
- Insight: the recalibrated gate immediately enabled a real win that the old bar would have discarded — and the agent's population-measurement discipline (predicting the corpus gate within 1e-4 from per-target reconstruction) is the pattern to keep in briefs. New corpus fingerprint: MIXED 27% is now the TOP failure mode (FITTER 24, COLOR 20, UR 19, OF 10).
- Next: it67 graft-strokes candidate still running (its gate math must account for the new 0.2442 baseline — its worktree lacks it66; orchestrator will integrate its diff ON TOP and sweep the combination). Then next --brief (likely MIXED mode).

### Runs 67-68: it67 graft-strokes — near-miss converted, SHIPPED — tilecmp=0.2426 (KEEP)
- Timestamp: 2026-07-12
- What changed: [graft-strokes] BACKLOG lead executed by a worktree agent (two waves). Wave-1: stroke_graft.py (750 lines) — blackhat re-detection of label-chain-lost thin dark lines, stacked evidence gates, constant-width synthesis, dash completion + old-dash suppression; fires ONLY pizza-box; standalone +0.0017. Run-67 combination gate vs post-it66 baseline: +0.0014 — REVERT by 0.0001 (sub-additivity: it66's split already recovered some seams; the UR-share sub-criterion was also structurally unreachable for a single-target fix). Decision: do NOT bend the gate; resumed the candidate on its own measured lead. Wave-2 (fresh agent in the preserved worktree): implemented the mandated per-piece sagitta, HONESTLY verified it a corpus no-op (apex line is bowed — dies at the straight-run gate, never reaches sagitta), kept it for correctness, and built the actual mechanism: curved structural rescue behind an in-image context precondition (>=3 pass-1 accepts; organic stems measured 0 accepts = structurally inert). Standalone +0.0020.
- Result: final combination gate 0.2442 -> 0.2426 (+0.0016 >= 0.0015), census/flow/color all improve, pizza-box alone -0.0177 (0.2982 ~ edge-11's whole-engine 0.2949 reference), 10/10 other stems byte-identical twice-verified. Orchestrator eye grid: checker-band boundaries restored to continuous strokes, apex inner diagonal restored, wedge-tip curl replaced. quant-16 cut, staged repointed, baseline re-frozen 0.2426.
- Insight: (a) the near-miss protocol worked — a 0.0001 shortfall was earned back by the candidate's own follow-up lead instead of gate-bending; (b) sub-agents can be trusted to REFUTE their own mandated fix when instrumented verification says so (wave-2's no-op finding) — brief them to verify premises, not just implement; (c) single-target fixes structurally cannot move corpus mode-share sub-criteria — the mode check belongs to brief-compliance, not to orchestrator integration gates.
- Next: iteration.json -> idle; next --brief (MIXED top mode 27%). GAP_LEDGER new nibbles: old-dash gray residue on pizza right arm, far-left apex arm (flank 0.00 unrescuable), trim-seam gaps.

### Run 69: SHIP it69 component-tone re-anchor — tilecmp=0.2411 (KEEP)
- Timestamp: 2026-07-12
- What changed: worktree agent, briefed with it66's band-split lead — which it DISCONFIRMED by premise verification (the region is a FLAT tint, not a ramp; real root cause = global k=16 k-means allocates no centroid to pale minority tints → the crystals apex facet lived inside the WHITE background label, painted white-on-white: the "omitted strokes" and the ΔE 10.3 were ONE defect). Mechanism shipped: _reanchor_component_tones — fill-grade labels' large non-dominant flat components (dE≥12 from emission tone, span≤18.5) minted their own source-toned label. Pure paint; geometry byte-identical.
- Result: orchestrator independent sweep: 0.2426 → 0.2411 (+0.0015 at bar), color 0.1725→0.1677, census +0.0002/flow 0.0000, crystals −0.0135 + app-asset/mountain/rabbit small wins, 6 stems byte-identical. Own-render eye grid: apex facet restored, purple wedge→gray-teal, amber-gem faces cream/peach — every fire toward Recraft, zero visible regressions. quant-17 cut, staged repointed, baseline re-frozen 0.2411.
- Insight + PROCESS RULE: the UNDER-RESOLVE mode-share sub-criterion gates on INK-WEIGHTED share, which is geometry-fixed under recoloring — the agent PROVED (share_math.out, exact per-tile recomputation) that no pure recolor can ever satisfy it. Rule for future briefs/gates: pure-color candidates are gated on the keep law (or routed as COLOR mode); the mode-share check applies only to geometry-moving candidates. Second insight: agents genuinely disconfirm briefed hypotheses when told to verify premises first — two for two today (wave-2 sagitta no-op, ramp-band disconfirm).
- Next: run 70 = the agent's enumerated lead — STROKE-GRADE component recovery (extend re-anchor to lum<96 comps but emit via the stroke system; candidates already measured: crystals deep-blue edge strip L12 2454px dE 18.4, shield strap). That IS the UR-share lever (arc recovery flips ink tiles). GAP_LEDGER: apex outline warp (fitter family) added.

### Run 70: it70 stroke-grade recovery — sub-bar, STASHED as rider (DISCARD)
- Timestamp: 2026-07-13
- What changed: nothing shipped. Agent extended it69's re-anchor to saturated mid-dark minted tones (provably outside ink candidacy — mirrors extract_contour_strokes' own refusal clause; coupling MEASURED zero: dark_labels/strokes/global_width/flecks identical). Fires on exactly 2 comps corpus-wide (crystals deep-blue strip, shield strap surround), both eye-verified toward Recraft, 9 targets byte-identical.
- Result: +0.0002 (crystals −0.0014, shield −0.0009, rest 0.0000) — population-exhausted under the shipped locked gates; 7.5× under MIN_GAIN. Stashed as it70_satdark_reanchor_+0.0002_rider.diff with a new loop_candidates/MANIFEST.md (anti-staleness rule from the run-65 audit). Ships as a rider on a future keep.
- Insight: (a) third consecutive brief-premise disconfirmation by a verifying agent — the "verify premises first" mandate is now the highest-value line in the dispatch template; (b) UR mode-share moved +0.2pp on a pure IMPROVEMENT (fixed COLOR tile relabels as UR) — the mode-share criterion is bidirectionally decoupled from quality for non-arc changes; (c) the re-anchor family is now mined out (fill-grade shipped, sat-dark stashed, remaining dark classes have zero population).
- Next: run 71 = rivet-ring family (GAP_LEDGER it70 culprit: thin dark rings quantize INTO their dark parent label — dark/dark boundary ownership; named mechanism = extend _resnap_fill_boundaries to dark/dark). True arc-adder = actual UR lever.

### Run 71: it71 dark-ring carve — sub-bar, STASHED as rider #2 (DISCARD)
- Timestamp: 2026-07-13
- What changed: nothing shipped. _carve_dark_ribbons (+211 lines, worktree): thin dark ribbons minted from fill-grade parents via local masked-mean seeding + blend veto + enclosure gate (the must-not killer: kills all 8 eye-verified bad fires — pizza JPEG halos, elephant lavender ink-halos, rabbit ink band). Fires: 4 shield rivet arcs + 1 mountain streak; shield −0.0034; 9 stems byte-identical; deep-zoom eye pass clean incl. a 27-blob shield jitter contact sheet (all lateral 1px refits).
- Result: +0.0004 corpus — honest ceiling of a ~1,100-px defect family; stashed (rider pool now it70+it71 = +0.0006; MANIFEST notes apply-order). Premise corrections: ring lived in the TAN strap label (not maroon bg — ledger rule added: attributions must carry label id + rgb+lum); resnap-extension refuted (nothing to re-vote; must mint).
- Insight: two consecutive verified-safe sub-bar mechanisms = the single-defect well at 0.0015 is thinning for UR crumbs. FITTER (24% ink-share, stale default exclusion, three converging leads: crystals apex warp dominating residual dE 24 vs Recraft 7.5, pizza corner rounding, leech-blob width wander) is the biggest unopened family. Run 72 = fitter campaign opener.
- Next: dispatch it72 (fitter: outline fitting at high-curvature bends / corner rounding / synthesized-width wander — diagnose which is the common stage first). Riders ship with the first future keep.

### Run 72: it72 fitter opener — diagnosis gold, mechanism sub-bar, STASHED as rider #3 (DISCARD)
- Timestamp: 2026-07-13
- What changed: nothing shipped. Agent's phase-1 stage strips (emission-trace validated byte-exact vs shipped SVGs) turned three converging leads into a precise map: leech-blobs + pinstripe wobble share ONE stage (constant-baseline width policy + swell/taper crutches — fixed by per-chain width grading, rider); pizza corner rounding is bend-radius INFLATION of drawn small-radius arcs through win-11 pre-fit smoothing (corner pinning provably can't reach: k6-turn 11-62°, localization fails); crystals apex warp is SHAPE-GATE ROUTING — the outline is a line NETWORK (elong 134) failing band exemption p25r 0.8, so it fill-routes and reproduces label-map wobble with no width idealization possible. Same class: rabbit's ENTIRE 2.83px ink network (elong 840).
- Result: best config +0.0006 (all channels clean, eye wins dramatic at deep zoom on 6 stems, must-nots hold, one REVIEW flag: chopchop goggle ring). Stashed as rider #3; pool it70+it71+it72 ≈ +0.0012.
- Insight — THE METRIC FLOOR IS NOW THE STORY: three consecutive verified-safe, eye-loud mechanisms landed 2.5-7× under MIN_GAIN because 1-3px geometry/color corrections dilute at 40×40 tiles. The loop is functioning perfectly and honestly, and it is systematically stashing exactly the "idealization polish" class the USER's defect list names (straights, joins, width). If run 73 (shape-gate routing, genuinely structural: whole networks re-routed) also lands sub-bar, the regime question goes to the USER: rider-accumulation (current), an all-channels-clean batch bar, or an eye-audit co-gate.
- Next: run 73 = shape-gate routing flip (population table ready in it72 artifacts; separator must exclude fox/monster silhouettes).

### Run 73: it73 shape-route — eye-positive/metric-negative, metric-floor CASE 4 (DISCARD, not-a-rider)
- Timestamp: 2026-07-13
- What changed: nothing shipped. Network exemption (med_w>=3, cov<1.4, elong>=60, p25r>0.5, area<=30k, lum<60, deep<=0.25 — every guard population-measured, fox/monster/mountain excluded by 3+ guards each) + junction-pool solidify. Premise verification corrected it72's table: rabbit ink net already stroke-routes at HEAD; the mis-routed class = 4 crystals outline components (~13k px).
- Result: eye at 4096/8192 zoom: all 15 fire sites clearly better (single uniform Recraft-weight strokes replace wobbly independently-fitted fill pairs; junction wedges solid in v2). tilecmp: −0.0001, FITTER share up (relabeling), junction-knot tiles +0.2/0.3. Stashed as EYEONLY_notarider.
- Insight — THE REGIME QUESTION IS NOW FORMALLY OPEN: four consecutive verified-safe, eye-verified mechanisms (it70 +0.0002, it71 +0.0004, it72 +0.0006, it73 −0.0001) fall 2.5×-under to actively-negative on tilecmp@40 while looking clearly better at deep zoom — including exactly the polish classes the USER's defect list names. tilecmp remains the right anti-gaming gate for label/color/structure families (it shipped 4 real keeps this segment), but it is blind-to-hostile on 1-3px geometry polish. Decision needed from USER (options in dashboard): (a) keep current regime, riders accumulate; (b) all-channels-clean batch bar ~0.0010; (c) eye co-gate for the polish class (metric-neutral + orchestrator deep-zoom eye pass = ship); (d) park polish until a metric v2 (higher tile count / edge-weighted). Meanwhile the loop pivots to CENSUS-heavy/MIXED classes (census 0.3002 = worst channel, barely moved all segment, never directly targeted).
- Next: run 74 = --brief with FITTER+UNDER-RESOLVE excluded (steer to MIXED/COLOR/OVER-FRAGMENT).

### Run 74: it74 sat-dark parent admission — metric-floor case 5, rider #4 replaces it70 (DISCARD→rider)
- Timestamp: 2026-07-13
- Root cause premise-verified: label 11's tone is right GLOBALLY (dE 1.8) but its crystals-region component is a distinct crimson sub-population at dE 17.6 — blocked from it69's re-anchor solely by the PARENT lum<96 gate (it70's rider only relaxed the minted-tone gate). Fix: one shared admissibility predicate (fill-grade OR sat-mid-dark) on both gates; structural mirror of the ink clause, not a tuned knob.
- Result: +0.0003 (COLOR share 18.9→18.6 = criterion PASSED; only the bar failed); 3 fires (subsumes it70's 2); 9 stems byte-identical; eye dramatic. Family mined out at dE≥12 (fire floor 17.77 vs must-not ceiling 10.55). Stashed as rider; it70 DELETED from pool (hard-conflict superset). Pool = it74+it71+it72 ≈ +0.0013.
- Insight: (a) the pool sits ONE +0.0002 clean win from the 0.0015 batch bar — next candidate that lands anything clean ships the whole batch; (b) the agent's COLOR decomposition probe: corpus excess-term 0.1315 vs distinct-term 0.0362, and chopchop (#2 color stem, excess 0.2247) has ZERO re-anchor population — its color error is ink-coverage/geometry-coupled tile means = a DIFFERENT color family, unmined, possibly bar-scale; (c) sub-12 dE compromise class exists but its margin to elephant's must-not is 0.05 dE — needs a Recraft-repaints eye study, not a threshold.
- Next: run 75 = chopchop color family investigation (diagnose-first: why do chopchop's tile means sit dE 4.40 from source where Recraft manages 1.93, with no mis-toned flat comps?).

### Run 75: BATCH SHIPPED (it75 + it74 + it71) — tilecmp=0.2387 (KEEP), quant-18
- Timestamp: 2026-07-13
- The headline (it75): width_scale=0.85 was eye-tuned to track elephant — which routes ZERO ink through the stroke system at HEAD. Every stroke the engine ever drew was 15% thinner than source against a phantom target. Found by per-tile counterfactual decomposition (coverage/ink-tone/fill-tone split; we cover 87.7% of source ink px, Recraft 97.6%), two hypotheses refuted with numbers, blind global retunes measured and REJECTED (ws=0.95: eye-verified pizza gap-pinch). Fix: per-image source-anchored pen scale behind 3 evidence gates; fires 5 stems, holds out exactly the two where boldening hurts.
- Batch assembly: it74 + it71 riders applied on top (it72 conflicts semantically with the new pen — left stashed with a precise rebase note; it73 EYEONLY awaits USER). Combined sweep: 0.2411→0.2387 (+0.0024), color −0.0067, COLOR share 18.9→17.2, flow +0.00007, chopchop −0.0195, 6 stems byte-identical. Batch eye grid: chopchop outlines at Recraft weight; shield rivet = compound win (it71 ring + it74 tone + it75 pen); crystals gems correct; residuals are pre-existing families (ledgered).
- Insight: (a) the rider-accumulation pattern WORKS — two sub-bar verified mechanisms shipped legitimately by riding a bar-clearing keep; (b) the deepest bugs are stale calibration targets, not wrong algorithms — width_scale's help text still said "track elephant"; (c) counterfactual decomposition (oracle: "fix X, what's the ceiling?") is the strongest diagnosis pattern of the segment and should be in future briefs.
- Next: run 76 = ribbon double-scale bug (found by it75, real bug, own gated candidate). Segment 3 total: 0.2487 → 0.2387 = −4.0% in ~14 hours.

### Run 76: it76 ribbon eff² bug — fixed, evidence-gated, rider #5 (DISCARD→rider)
- Timestamp: 2026-07-13
- Bug confirmed at exact lines (w_body carries it75_eff, _ribbon call re-applies it): ribbons at 0.72×gw unfired / cal² fired, since bulk-import 3d5ae16, sole live call site. The subtle part: un-gating the fix REGRESSES pizza +0.0207 COLOR — the accidental square was compensating an over-wide pen on spill stems (ovh .27-.48). Fix gated by it75's own ovh≤0.19 (no new tuned constant); spill stems byte-identical with documented reason.
- Result: +0.0000 corpus, no channel regresses, flow −0.0001, COLOR share 17.2→16.9, chopchop fronds/paws + logo-lineart glyphs eye-better toward source mass. Metric-floor case 6. Stashed as pure-correctness rider.
- Insight: bugs can be load-bearing — two wrongs (thin pen × squared ribbon) were partially cancelling on spill stems; fix one wrong only where the other is absent. The correct endgame is a spill-side pen calibration arm (scale DOWN where ovh is huge), after which rib_fix dissolves.
- Next: run 77 = MIXED/census brief (census 0.2998 = worst channel, MIXED 27% = top mode, both unmined); it72 semantic rebase queued for the next batch assembly.
