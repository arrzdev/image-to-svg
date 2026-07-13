# Model versions

**Naming (2026-07-09): folders are `prefix-N`, split by architecture lineage.**
The web dropdown groups by prefix and sorts each group numerically.

- **`quant-N`** (was `vN`, N=3..11) — the QUANTIZE-FIRST lineage: global
  k-means colour quantize decides topology, then contour/line idealization.
  `quant-11` is the mature production engine; `models/staged` symlinks it.
- **`ideal-N`** — the IDEALIZE-FIRST lineage (the "how Recraft works" rebuild,
  design 2026-07-09): edge-preserving idealize → local region topology (no
  global palette) → colour sampled last → dedicated ink layer. `ideal-1` =
  clean fills only (proved fills can't carry ink); `ideal-2` = + ink layer
  (the blueprint union). Design record: `research/design/BLUEPRINT.md`. These
  reuse `quant-11/src` as the geometry/emission backend and do NOT hard-
  downscale to 1024 (R1).

Each runnable version folder contains the version's **complete code** and a
stable entry point, so any version runs from the main branch without touching
git history:

- `entry.py` — `run(image_path, params=None) -> str` (SVG). Same contract in
  every version; the root `run_model.py` CLI and `server.py` frontend route
  through it in isolated subprocesses.
- `src/` — the engine as it was at that version's commit (frozen; the LIVE
  engine is the newest version's src, which the research loop edits).
- `examples/` — SVGs produced by exactly this folder's code (regenerate with
  `python3 run_model.py -m vN -i data/inputs/<img>`), plus historical
  comparison PNGs.
- `MANIFEST.md` — what changed, eye verdicts, negative results.

The newest version (currently **v9**) is the LIVE tree the research loop edits
(`models/staged` always symlinks it — `run_model.py -m staged` tests in-flight
work mid-loop);
v3–v8 are frozen. Each version carries `data`/`outputs`/`frontend` symlinks so
its code finds the shared cache; the research harness (`research/autoresearch.sh`)
runs the live version's `src/ar_eval.py` (→ `src/testbed.py`). At each
**structural** milestone the loop snapshots the live tree into the next `vN/`
(via `git archive <commit> models/<live>/src`) with its own manifest + freshly
rendered examples, and that new folder becomes the live tree.

Mission & versioning rules: `research/docs/PROJECT_SPEC.md` (§5). Bump N only
on **structural** changes; update this file on every bump, narrating each
version vs the previous **and vs Recraft**.

- **v1** (pre-git, ~Jul 5): first tournament engine — vtracer/potrace/quantize
  portfolios, composite metric, DiffVG refinement. Elephant grail ≈ 0.934 @
  ~1.1k pts, but structurally dirty at deep zoom (independent tracing:
  hairlines, spurs; independent DV overlap-cheating discovered later).
- **v2** (pre-git, Jul 6 milestone): shared-boundary vectorization + honest
  shared-edge DV + structural integrity judge. Elephant 0.9312 @ 727 pts,
  integrity 1.0. Artifact: claude.ai/code/artifact/24a07afa-...
- **v3** (git `d7804f5`, 2026-07-07 01:58; code in `v3/src`): + Potrace-parsimony fitter (wobble-free by
  construction), width-constant contour strokes (the drawn look), junction
  ink pooling, 3.7x faster grail (~80s), cached testbed, vision-first
  process per user direction.
- **v4** (git `c463914`, 2026-07-07 03:03; code in `v4/src`): line/fill idealization —
  vision-first pass. `contour_lines` pipeline: width-constant centerline
  strokes for the line network + parsimony-fitted flat SHADING shapes,
  line-weight calibrated to Recraft (`width_scale=0.85`), strokes as the top
  layer. **vs v3:** the three user-cited defects (wobbly lines, width thinning,
  shadows-over-lines) resolved; lines read as confident digital strokes.
  **vs Recraft:** line + fill quality now in Recraft's tier on the elephant by
  eye (`v4/vs_recraft_fullframe.png`, `v4/vs_recraft_zoom.png`); residual gap is
  subtle palette/shading-color, not structural. Elephant `contour_lines`
  ≈ 918 pts / 39 paths / 13KB. Open defects → docs/BACKLOG.md.
- **v5** (git `c61755e`, 2026-07-08 03:01; code in `v5/src`): the autoresearch arc, runs 2–20 —
  line-network integrity + measured idealization. **vs v4:** the v4 defect
  report is cleared — junction nubs/pinches fixed, cross-component dash-gaps
  bridged, despeckle-lost ink re-traced from the source raster, curvature
  drift measured resolved (0.04px), shadow tones merged, serrated outlines
  redrawn as corner-sharp constant-width strokes (miter joins). **vs Recraft:**
  junction/join cleanliness and shadow palette now match on the elephant by
  eye; chopchop serrations moved decisively toward Recraft's crisp zigzag;
  rabbit's dashed outlines are near-continuous (long label-map losses remain
  the visible gap). Runs 11–14 added (worktree-parallel iterations): adjacency
  fleck absorption, wiggle-gate texture→soft daubs, guarded plank-speckle
  dissolve, the despeckle light-accent guard (striped straw / gem vein / fox
  eye glint / monster scratch rescued), and the junction pool clamp (frond
  centers + chair crossings cross clean). Runs 15–20 (native worktree
  iterations): light-line capsules un-bead thin light lines, source-supported
  chord + arc endpoint bridging closes the rabbit heart + chopchop trunk (0
  welds), medial_axis RNG pinned so renders are byte-deterministic. Each keep
  eye-verified; negatives in v5/MANIFEST.md + research/docs/RESEARCH_LOG.md.
- **v6** (git `a8d728d`, 2026-07-08 05:01; code in `v6/src`): serration
  sharpness + clean terminals (runs 21–23). **vs v5:** monster teeth render
  tall AND sharp (corner-pinned fills + severed-spike-tip rescue, compound);
  corpus-wide corner sharpness (mountain pine tips, fox fur wisps, crystals
  facet joins, logo-badge blade points); ribbon/wedge ends round-capped.
  **vs Recraft:** monster serration approaches the reference zigzag.
- **v7** (git `8431d34`, 2026-07-09 07:45; code in `v7/src`): straight lines,
  letterforms, un-tangled junctions (runs 25–29) — answering the user's
  eye-verdict. **vs v6:** thin-dark-line lock restores the rabbit heart notch +
  paw fingers (label cleanup was erasing sub-3px lines); two-tier chroma gate
  un-mangles the pizza "ZZA" letters and clears the chopchop junction tangles
  (stroke-ified texture labels); straight-piece priors make pizza checker
  horizontals ruler-straight. **vs Recraft:** chopchop gap narrows (recraft_gap
  0.868→0.871); the benchmark moves.
- **v8** (git `5d1a9d6`, 2026-07-09 12:06; code in `v8/src`): color-guarded
  joins + deep cusps + ruler-straight grids (runs 34–35).
  **vs v7:** color-guarded joining (USER idea — refuse a weld across a color
  break) removes chopchop knot/leaf welds, fox chin-worm, rabbit spur welds
  while keeping the heart/trunk closures; junction cusp descent renders the
  heart notch at full depth ≈ original/Recraft; straight-chain lock kills the
  fitter's −2.75px S-bow so pizza verticals stay straight through crossings.
  **vs Recraft:** the user-reported defects (over-rounding/straights,
  over-joining, the heart, ZZA, junction tangles, paw fingers) are closed by
  eye. 
- **v9** (git `18797ae`, 2026-07-09 16:15; code in `v9/src`): sharpen prepass + 40× perf
  (runs 36–37). **vs v8:** byte-identical-output perf rewrite (chopchop
  298→7.4s — faster than v5); USER's sharpen prepass default-ON with
  anti-ringing clamp (chopchop strut noise daubs gone, rabbit heart flat +
  highlight rim, app-asset dropped letter restored; soft-gradient trade
  logged, presharpen=0 escape). **vs Recraft:** benchmark noise gap visibly
  narrows; rSSIM rabbit .951, monster .990.
- **v10** (git `01e80e0`, cut 2026-07-09 late; code in `v10/src`): glyph
  rescue + gradient flatten + flat-art guard (runs 38–40). **vs v9:**
  flat-art skip restores the monster mouth (run-37 sharpen regression);
  chromatic-mark rescue survives despeckle floors (app-asset "Share" r +
  envelope creases back, ledger 0g); recraft-style gradient-region flatten
  turns the app-asset bg into ONE solid, ragged rings gone (ledger 0f).
  **vs Recraft:** audit24 (research/audit24/FINDINGS.md) sets the absolute
  bar: flat clean inputs ≈ parity; soft-shaded/AA classes remain 50–70% —
  root causes E1–E8 drive the it24+ campaign.
- **v11** (git `8315d66`, cut 2026-07-10; code in `v11/src`): transition
  ownership + line-intent stage 1 (it24, runs 54–55) — the first audit-24
  campaign milestone. **vs v10:** E1 AA-ramp shrapnel absorbed into owning
  regions (app-asset integrity .412→.988, mountain 1.000, ledger 0l closed);
  drawing-intent anchors + tiered exact-chord emission + G1 kink repair
  (monster hand hairlines straight with sharp kinks ≈ recraft — ledger 0k
  hand closed; teeth crisp, residual = label lattice; crystals/mountain
  edges straighter; circles stay round). **vs Recraft:** the two loudest
  structural root causes (E1, E4) now have shipped mechanisms; remaining
  gap concentrates in E2 shadows, 0h seams/E8 emission, E5 lattice
  regularity, E7 color. _(Live tree — next bump = v12.)_
- **quant-13** (cut 2026-07-11; frozen `quant-13/src`; `staged` → here): the
  full-auto tilecmp loop's shipped wins on top of quant-12 — source-anchored
  fill recolor, dark-shrapnel absorption, evidence-gated region split,
  gradient banding (2-3 flat bands like Recraft), transition-mud
  ownership/boundary resnap. **vs quant-12:** tilecmp corpus distance to
  Recraft 0.2725 → 0.2553, all three channels improved, every merge gated
  (research/design/tilecmp_gate.py) + eye-audited. Lineage decision recorded:
  QUANTIZED backbone is the engine (edge lineage dead — over-fragments 10x;
  vectorark-1 paper-fusion challenger parked at 0.367). Loop machinery:
  research/design/autoresearch_loop.py; run ledger:
  research/design/autoresearch_loop_ledger.jsonl.
- **quant-23** (cut 2026-07-13; frozen `quant-23/src`; `staged` → here): quant-22
  + flow-aware ink split (USER idea, USER-decided ship). `_flow_split_dark_ink`
  separates merged ink where branch flow diverges (crossings=different objects),
  on organic ink networks only. **vs quant-22:** chopchop paths 520→546, cubics
  4235→4388 toward Recraft; flow improves; coarse-tile win (n=20 chopchop −0.0061);
  geometric over-fragmenters BYTE-IDENTICAL. Strict n=40 gate −0.0003 (seam noise)
  — shipped for the structural/flow win; seam-clean recovery open. Metric-verified.
- **quant-22** (cut 2026-07-13; frozen `quant-22/src`; `staged` → here): quant-21
  + fill_tol 2.5→3.5 — looser fill fit cuts cubics ~25% toward Recraft (app-asset
  1585→1180, pizza-box 568→432, shield 1331→1145; Recraft 629/377/751) at zero
  tilecmp cost (0.2334, worst stem 0.0); straightness win preserved. Fewer/better
  cubics = Recraft's economy, smaller SVG. Metric-verified.
- **quant-21** (cut 2026-07-13; frozen `quant-21/src`; `staged` → here): quant-20
  + speck drop. struct_compare found Recraft emits ~0 tiny paths while we emitted
  80-155/image (74-77% of our paths were sub-2000px shrapnel). `_drop_specks`
  removes paths with bbox max-dim < 0.6% of canvas (layered emit reveals the shape
  beneath = absorption). **vs quant-20:** corpus 0.2379→0.2334 (+0.0045, all
  channels, worst regression +0.0003); path counts → Recraft (app-asset 261→109,
  pizza-box 198→137, shield 198→128, rabbit 367→152). Biggest structural win of
  segment 3. Metric-verified (tilecmp + struct_compare).
- **quant-20** (cut 2026-07-13; frozen `quant-20/src`; `staged` → here): quant-19
  + adaptive straightening (USER "curly straight lines"). Pipeline embeds an image
  Hough straight-line-dominance signal; straighten collapses aggressively (eps 2.5,
  bow-gated) only for geometric art (pizza/logos), conservative for organic.
  **vs quant-19:** corpus 0.2387→0.2379; pizza-box −0.0087 (long-L 43→50 toward
  Recraft 86); 9 stems byte-identical, zero regression. Metric-verified
  (tilecmp + research/tools/struct_compare.py), no visual judgment. Remaining pizza
  gap = over-fragmentation (198 paths vs 73).
- **quant-19** (cut 2026-07-13; frozen `quant-19/src`; `staged` → here): quant-18
  + fill-coverage seal widen 1.0→2.0 (USER feedback: white sliver between colour
  and outline in glasses/tail). Hidden-side-only seal → closes the gap with no
  visible weight change. **EYE-GATED** ship: tilecmp neutral (0.2387, bit-identical
  — blind to a 1px seal), corpus-verified by eye + KB-flat. First eye-gated keep
  of the coverage class (USER made the eye the authority here 2026-07-13).
- **quant-18** (cut 2026-07-13; frozen `quant-18/src`; `staged` → here): quant-17
  + the run-75 batch — pen calibration (width_scale was tracking elephant,
  which has zero strokes at HEAD: all ink was 15% thin; now source-anchored
  per image, evidence-gated) + tone re-anchor parent admission + dark-ring
  carve. **vs quant-17:** 0.2387 (+0.0024; color 0.1677→0.1610); chopchop
  −0.0195 (largest single-stem win of the segment); shield rivet compound win
  (ring+tone+pen); 6 stems byte-identical. Segment 3 running total: −4.0%.
- **quant-17** (cut 2026-07-12; frozen `quant-17/src`; `staged` → here): quant-16
  + it69 component-tone re-anchor — flat minority components mis-anchored inside
  another label's tone get their own source-toned label (crystals apex facet was
  white-on-white; k=16 had no centroid for the tint). Pure recolor, geometry
  unchanged. **vs quant-16:** corpus 0.2411 (color 0.1725→0.1677); crystals
  −0.0135; 6 stems byte-identical; every fire eye-verified toward Recraft.
  Shipped on the keep law — the UR mode-share sub-criterion is arithmetically
  unreachable for recolors (share_math.out in research/it69 artifacts).
- **quant-16** (cut 2026-07-12; frozen `quant-16/src`; `staged` → here): quant-15
  + it67 graft-strokes — the edge-11 structural-stroke layer grafted onto quant
  fills (stroke_graft.py: blackhat lost-line re-detection, stacked evidence
  gates, constant-width synthesis, dash completion + old-dash suppression,
  curved rescue behind a scene-context gate). **vs quant-15:** corpus 0.2426
  (all channels improve); pizza-box 0.3159→0.2982 (edge-11 whole-engine ref
  0.2949) with checker separators + apex diagonal + underline bar restored
  (eye-verified); 10/10 other stems byte-identical. Run-67 near-miss (+0.0014
  vs 0.0015 bar) converted by an agent wave-2 (+0.0020 standalone) rather than
  bending the gate.
- **quant-15** (cut 2026-07-12; frozen `quant-15/src`; `staged` → here): quant-14
  + it66 structured-split recalibration (dark-skip → ink-rule + saturation
  escape; ef floor 0.03 behind maxde≥17 rescue bar). **vs quant-14:** tilecmp
  corpus 0.2442 (census −0.0016, color −0.0033, flow +0.0004 < eps);
  UNDER-RESOLVE share 20.0%→18.8%; crystals facet/wave recovery eye-verified
  by orchestrator renders. Known cost: pizza lid-crease leech blob
  (GAP_LEDGER it66-leads). First worktree-agent keep of segment 3 (70d43aa).
- **quant-14** (cut 2026-07-12; frozen `quant-14/src`; `staged` → here): quant-13
  + it9 wander-erasure — band-limited removal of the 6-30px quantizer-boundary
  wander before fitting (coarse-reference high-pass split, corner-protected,
  0.9px leash, flat-art scene gate). **vs quant-13:** tilecmp corpus 0.2487 →
  0.2457 (census −0.0068, flow −0.0027, color +0.0007 < eps); eye audit: shield
  rim wobble gone, app-asset shadow-fringe teeth gone, chopchop lateral. First
  keep under the gate recalibration to the measured 0.0000 noise floor
  (MIN_GAIN 0.004 → 0.0015; research/design/tilecmp_gate.py, run 65).
- **edge-10** (cut 2026-07-11; `edge-10/src/pipeline.py`; the Edge Lab web tab
  runs THIS module in-process — lab tinkering IS model behaviour): the
  boundary-first lineage resurrected via the interactive Edge Lab. Two
  independent detectors: buckets (bilateral-1, dE 5, RAG merge 22 — close
  shades merge, the wall between them deleted) + ink (LCh gates L*<30 /
  C*<100 / contrast 0, filled RIBBON paths on top, Recraft-style). Seam glue:
  fills dilated 2px before tracing (painter's-order overlap, no hairline gaps)
  + AA transition-ribbon cells absorbed via the Lab blend-segment test.
  USER-frozen recipe (elephant: 56 paths / 61 KB; chopchop: 229 paths /
  112 KB). Not yet tilecmp-benchmarked vs quant-13.
- **edge-11** (cut 2026-07-12; `edge-11/src/`; the Edge Lab tab now runs THIS
  module): synthesized strokes over buckets (USER architecture). Lines are
  detected STRUCTURALLY (thin + uniform interior + not-a-blend — any colour:
  purple outlines, white hairlines) and REBUILT from centerline + low-passed
  width profile instead of traced: skeleton graph -> spur pruning -> collinear
  junction merging -> leashed 1D smoothing -> emit <path stroke> when width
  ~constant, variable-width ribbon fill otherwise; traced-ribbon fallback for
  fragmented skeletons (sausage guard); pinch-break bridging so one drawn line
  = one component. Buckets inherited from edge-10 (RAG merge, transition
  absorption, seam glue, arcfit). elephant 44 fills + 89 strokes / 37 KB;
  chopchop 116 + 213 / 93 KB. Reference edges are topology-only.
