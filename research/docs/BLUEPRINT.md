# Blueprint v2 — designing the ideal algorithm (design-mode sessions)

## ⚠ IMPROVEMENT IS DECIDED BY ALGORITHM, NOT THE EYE (USER 2026-07-10)

Orchestrator visual judgment proved unreliable (approved a badly-distorted
elephant as "digital-graphics quality"; the metric scored it worst of all
tested). **Process, mandatory:**
- To decide "did this change IMPROVE," run
  `eval/score_vs_recraft.py <version>` — MS-SSIM↑ / GMSD↑ /
  CIEDE2000 dE↓ of our output vs the Recraft target, per-image + mean over the
  11 targets. Keep a change only if the score improves. Tune params by
  sweeping + scoring, never by "looks better."
- Use **visuals for EXPLORATION ONLY** — understand where we are, find what's
  wrong, form hypotheses. The eye never renders the improvement verdict.
- See memory [[verify-by-looking-not-numbers]] (revised).



Working doc for the USER + orchestrator design conversation (2026-07-09 →).
Mode: **design, not work** — no engine changes until the blueprint is agreed
and the USER green-lights development. Companion evidence:
`research/experiments/design-studies/stages_rabbit*/` production lines
(`pipeline_stages.py` renders every v11 stage; FINAL byte-verified against
`entry.run()`, the web-interface path).

Authority context: `research/docs/VISION.md` (the Recraft blueprint),
`research/experiments/audit24/FINDINGS.md` (E1–E8 root causes),
`research/docs/PAPER_NOTES.md` (paper digests).

## Requirements (USER-set, hard)

- **R2 — Strokes must survive at display size (scale-invariant line weight).**
  v11 emits **116 of 118 strokes at `stroke-width="1.00"`** in a 1024-unit
  viewBox. That is fine at a 1400px+ render (≈1.4px, crisp) but becomes
  **sub-pixel (~0.5px) at the browser panel size (~480px)**, where the
  rasterizer renders it faint or drops it — the USER saw the rabbit's head
  crown outline "missing" in the web interface while the resvg production
  line (rendered large) showed it closed. Byte-identical SVG, different
  apparent quality **purely from display scale** (proof:
  `research/experiments/design-studies/figures/stroke_scale_proof.png`, `_scale_480.png`). Design
  consequence: stroke weight (and every emitted dimension) must be sized
  **relative to the artwork's own line weight**, so a main outline reads as a
  confident stroke at ANY display size — not a fixed user-unit that only
  looks right when rendered at high res. Recraft's outlines hold up at
  thumbnail size; ours must too. Tie-in to R1 (same scale-invariance root).
  **Process corollary:** we have been eye-checking via resvg at ≥1400px,
  BLIND to how thin/broken the output looks at the size users actually view.
  The idealization judge must render at display scale (≤512px) too, not only
  deep-zoom crops. (Deep zoom stays for structure; display scale is added
  for line-survival.)

  **Layer diagnosis (rabbit, verified `research/experiments/design-studies/figures/layer_diagnosis_480.png`):**
  the outline is emitted as TWO layers — dark FILLS (288 paths, the main
  silhouette/outline: filled areas, never go sub-pixel, survive small fine)
  and thin STROKES (118 paths, `width=1.00`, the DETAIL line layer: belly
  creases, crown wisps, basket/bag lines). Only the STROKE layer evaporates
  at 480px. So the fix is scoped: **give the detail-stroke layer a survival
  floor.**

  **Mechanism (validated by post-process demo
  `research/experiments/design-studies/figures/reweight_money_480.png`, ready to implement):**
  in emission, `contours_exp.py` sets `w_body = max(base*width_scale, 0.75)`
  — an ABSOLUTE 0.75-unit floor. Replace with a viewBox-RELATIVE survival
  floor: `floor = max(0.75, DIM*F)` where DIM = viewBox longest side and F is
  tuned so the floor is ≥~1.5px at the smallest target display
  (F≈0.0033 → 3.4u in a 1024 box → 1.6px @480). Main outlines that ARE
  strokes get weighted toward the artwork's measured ink width
  (`gw`/`median_width` already computed at contours_exp.py:978-981) rather
  than the uniform thin value. Caveat to eye-check across all 18: a global
  floor also thickens genuine fine detail (whiskers, tiny creases); verify it
  reads as confident-Recraft-ink, not clumsy. The demo used a crude uniform
  3.2× + floor 3.2; the real change is the relative floor above. **Touches
  every output → each of 18 must be eye-verified at BOTH display (≤512) and
  zoom before keep.** Answers USER 2026-07-09 "outlines weighted to survive
  at any size — can you do that?" → yes, proven.

- **R1 — Native resolution, no silent downscale.** The current entry prep
  resizes everything to 1024px longest-side before the pipeline runs; the
  USER rejects this. The engine must ingest the raw image at native
  resolution, and ideally *upscale* low-res inputs toward 4096 before
  vectorizing. Consequence (measured, rabbit 4096 vs 1024 production lines):
  v11's intent heuristics are absolute-pixel-unit (despeckle ≥120px,
  line-lock half-width ≤1.6px, stroke calibration…) and fall apart when the
  scale changes → **every threshold in the new design must be expressed in
  units of the artwork's own measured line weight / feature scale, not raw
  pixels.** (Caveat to engineer around: naive Lanczos upscale of flat/crisp
  art rings at hard edges — the old reason the prep avoided upscaling flat
  art.)

## Recraft engine — best-guess reconstruction (2026-07-09)

Synthesized from measured Recraft SVG structure + PAPER_NOTES + originals.
Confidence tagged. This is a hypothesis to design AGAINST, not fact.

**Thesis (high conf): Recraft LEARNED idealization (messy→clean mapping); it
does not trace.** The tell is VectorArk's degradation-training result —
"without it the model faithfully reproduces the imperfections of the input
raster." Idealization can't be bolted on as guards (what we do, one accident
at a time); it has to be learned wholesale. So Recraft is a different KIND of
system, not a better-tuned tracer.

Best-guess pipeline:
1. **Semantic understanding first, not color clustering** (learned; high
   conf neural). Segments objects/parts, not color clusters — the only thing
   that explains drawn boundaries surviving between same-colored objects AND
   repeated elements coming out MORE regular than the source (teeth, rivets).
   A pixel tracer can't regularize a motif it has no concept of.
2. **Geometry on a decolorized outline, color reattached after** (VectorArk
   outline-normalization; high conf). Inverse of us: WE quantize color first
   → geometry falls out of color regions → every color accident fractures
   geometry. Deciding geometry BEFORE color is the highest-leverage
   architectural reversal for us.
3. **Explicit line-intent + straightness certificate** (classical, matchable).
   Straight-command share is the smoking gun: mountain 644 L vs our 45,
   elephant 54 vs 0. Potrace-family straightness (±½px band) + alphamax
   corner test, per boundary, likely gated by learned line-type
   classification.
4. **Local region-interior color, decided last** (classical, matchable).
   ~78 colors chopchop ≈ 1/shape, each a flat interior-sampled tone (eroded
   band → dodges AA/occluder contamination, the UDF/contour-band idea).
   Shadows/gradients collapse to one tone or one real SVG gradient.
5. **Layered shapes, painter's order** (classical, matchable). One path per
   shape, single subpath, bg at bottom; falls out of back-to-front semantic
   masks or residual-size ranking (LIVE/Layered). Verified: their elephant
   path 1 = 810k-px bg.

**Division of the gap:** geometry = classical, closable (papers give recipes);
color = classical, closable (reverse our order so color stops driving
geometry); semantic understanding = the part a learned model wins. Our best
classical proxy for #1 is the Layered paper's move — decide topology on an
aggressively edge-preserving SIMPLIFIED raster so accidents never define
geometry (idealize BEFORE vectorizing, not clean up after).

## Experimental v1 finding (2026-07-09) — ink cannot come from fills

Built `models/experimental/` (idealize → local-segment → colour-last → v11
emit). Result (`research/experiments/design-studies/figures/exp_compare.png`, `exp_lost_ink.png`):

**Validated:** the front-half thesis works — local colour gives ONE flat
background (no bands/shrapnel), colour-last interior sampling gives accurate
fills, mean-shift flattens the soft drop-shadow with no special guard.
USER: "in places where outlines were being ignored they now exist" — the
edge-based front-end finds soft-edge boundaries v11's colour-quantize misses.

**The forcing finding (USER caught it, measured):** **36% of black-ink pixels
got painted a LIGHT neighbour colour**; only 16 of 322 regions stayed dark.
The red map traces the whole outer line-art contour. Mechanism: a thin black
line between two fills IS just their shared boundary — it has no interior to
sample, so colour-last inevitably gives it one side's colour; and it's too
small to survive segmentation as its own region. **Fills can NEVER carry the
ink.** This is exactly why VISION item 1 is "strokes AND bucket-fills" (two
layers) and why v11's outlines are crisp (dedicated stroke layer).

**Design conclusion → target architecture = the union:**
experimental's idealize-first, local, colour-last BUCKET-FILLS (its strength)
UNDER a dedicated line-intent INK layer (v11's strength: extract the dark thin
network, classify straight/curve/detail, paint confident strokes on top with
the R2 survival floor). Neither half alone is Recraft; the combination is the
blueprint. v2 = add the ink layer to experimental.

## Observations queue (to be pinned to stages as the USER reports them)

- (pending USER zoom pass over the rabbit production line)

## Where the current architecture fights us (orchestrator read)

- v11 is "quantize first, interpret later": global k-means slices color
  space with no concept of stroke/shadow/border, then six stages
  (consolidate → own-transitions → lock → despeckle/smooth/dissolve →
  restamp) repair the damage. The Recraft blueprint implies the inverse:
  classify intent first (line ink vs fill zones vs shadow), then choose one
  flat color per zone locally.
- The pipeline stays raster until very late: vectors only exist at stroke
  fitting (panel 12) and fill fitting (panel 14). Every intent decision is
  made on label-map pixels.
