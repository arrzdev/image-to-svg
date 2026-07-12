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
