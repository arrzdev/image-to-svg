# Audit 24 — full-set eye audit at HEAD (659597f), 2026-07-09

Every input re-generated fresh at HEAD (`research/audit24/svg/`), compared
ORIGINAL | OURS | RECRAFT full-frame + zoom crops (`grids/`). Structural
stats: `analyze_recraft.py`. This audit exists because the USER called the
plateau: runs close ledger items but the visual gap to Recraft isn't closing.

## Verdict per target (zoomed, absolute bar)

| target | verdict | loudest gaps |
|---|---|---|
| logo-geometric | ≈parity | circle roundness a hair off |
| logo-badge / wordmark / lineart | ≈parity-ish | lineart ring wobble |
| monster-flat-line | **below** | teeth blunt/uneven; hand/body straight lines turned wavy; head silhouette kink; mouth seam hairline |
| elephant | close | outline width fluctuates; shadow-ellipse edge ragged; mouth-line kink |
| chopchop | close-ish | outline weight varies + interior edge daubs; lens gradient bands; stool shadow "drips"; strut hole = broken hook; ear canal mangle |
| fox | mid | ink-weight inflation (all strokes heavier); soft shading → hard-edged jagged patches; pale debris inside dark ink |
| rabbit | mid | hand/basket boundary WELD (paw gone); ground shadow smeared vs Recraft's clean flat ellipse; cheek-fluff tears; edge spurs |
| mountain | mid | ridge lines wiggle (0 straight segments); trees merge/dissolve; hill bands hard-edged wrong shapes; cloud strips ragged |
| shield | mid | silhouette wobble+kinks; triangle corners blob; boss two-tone split line wobbly (Recraft: dead straight); tan crescent invented under knob; purple flecks |
| crystals | **below** | facet polygons melt into painterly smudges; thin facet ridge lines deleted; highlight shapes deformed; hue drift |
| app-asset | **below** | edge shrapnel everywhere; icon drop-shadows → ragged moats; white blob invented; phone bezel shredded (Recraft: 2-3 clean nested rounded-rects + real gradient fills) |
| coins | mid | metallic shading → muddy smears; rim structure lost |
| game-assets | mid-good | small-object color drift (silver→teal streak); tiny glyph mangles; wood grain OK-simplified |
| game-assets-2 | mid | platform texture rows melt; small plants merge; color drift on small gems |
| files-pile | **far below** | text → speckle noise (should be dropped or kept legible, not shredded); paper-edge stack → smears |
| pizza-box | close-ish | checker grid separator lines dissolve into floating dashes; letter edges lumpy |

## The core engine problems (cross-image, ranked by eye-loudness)

**E1. Soft-transition shrapnel.** Every soft edge (AA, blur, focus falloff)
between two fills becomes torn dash/speck labels along the edge (app-asset
bezel, pizza grid dashes, rabbit ear spurs, boss ring flecks, chop outline
daubs). The quantizer partitions the transition ramp instead of assigning it
to one side. This is the #1 source of "looks traced, not drawn".

**E2. Shadow/highlight non-idealization.** Soft drop-shadows and speculars
become ragged multi-band blobs or invented white/tan patches (app-asset icon
moats, shield knob crescent, rabbit ground shadow, phone bezel white blob).
Blueprint says: one clean offset shape in one darker tone, or nothing.
Run-40 flattened *backgrounds* only — object-level shadows are untouched.

**E3. Drawn-boundary destruction.** Thin/low-contrast borders between
similar regions get dissolved or welded: crystal facet ridges, rabbit
paw-vs-basket, heart/string, pinstripes, checker separators, tree
silhouettes into hillside. Size/contrast-based despeckle+dissolve cannot
tell a drawn 2px line from a 2px noise fleck (ledger 0c — intent, not size).

**E4. No line-intent model (straight vs single-movement vs detail).**
Everything trends to smoothed cubics. Monster hand/body straight lines →
wavy S-curves; mountain ridges wiggle (ours 45 L cmds vs Recraft 644);
elephant 0 L vs 54; facet edges curve. Meanwhile genuinely curved lines
wobble (elephant outline width flutter). The run-35 straight-chain lock only
fires on near-exact chains (chopchop 2052 L — it CAN work); it misses
short segments, angled ruler lines, and everything in fills.

**E5. Repeated-element erosion.** Teeth blunt+uneven, rivet ring broken into
hooks, checker cells wobble, icon corner radii vary. Recraft renders repeats
MORE regular than the source.

**E6. Ink-weight inflation + interior debris.** Stroke weights come out
heavier than original (fox worst), vary along a line, and dark fills carry
pale AA-rescue debris inside them.

**E7. Local color model missing.** Global palette + centroid pull causes hue
drift (crystals pinks/teals, game-asset silver→teal). Recraft: per-region
averaged color, huge palettes, no global quantization; large smooth regions
→ flat average or a real SVG gradient fill (app-asset uses 5).

**E8. No layer structure.** Ours: one path per color, hundreds of subpaths
(app-asset 17 paths/547 subpaths). Recraft: one path per shape, single
subpath, painter's order (69-997 paths). Blocks editability AND several
fixes (per-shape shadow merge, per-shape regularization, paint-order
overlap to kill AA seams = ledger 0h).

## Process findings (why the loop plateaued)

**P1. Relative close-out bar.** Items closed at "clearly better than last
run" (monster teeth runs 21-22, straights run 35) while still below Recraft.
Nothing re-opens them; the ledger empties while the gap remains. Fix: close
only at ≈Recraft in the zoomed grid (now in VISION.md).

**P2. Verdicts at insufficient zoom.** Full-frame or 1024-grid verdicts pass
1-3px defects (this audit's own first pass repeated the mistake on monster —
USER caught it). Fix: mandatory ≥2 zoom levels per touched target, and
flat-art targets get the deepest zoom, not the shallowest.

**P3. Whack-a-mole beats blueprint.** 40 runs of local defect-fixes (gates,
locks, rescues) patched symptoms of E1-E8 one label at a time. The wins are
real but each new image re-manifests the same root causes. The papers +
Recraft stats point at structural answers (region-local color merge, layered
emission, line-intent classification, band-limited boundary ownership) that
no local gate reaches.

**P4. The metric still steers candidate selection.** contour_lines must be
run directly; the tournament's perceptual metric prefers noise-copying
candidates. Until the judge rewards idealization (line evenness, boundary
count preservation, flatness), automated selection fights the vision.

## What "reaching Recraft" needs (it24+ campaign skeleton)

1. **Transition-ownership quantize** (kills E1, most of E2): assign every
   AA/blur ramp pixel to one of its two bounding regions (or to an explicit
   shadow layer) BEFORE labeling — no third labels allowed on a 2-region
   transition. Region-wise smoothness stats exist (run-37/40 work).
2. **Object-shadow idealizer** (E2): detect soft dark halo attached to a
   shape → replace with one offset/dilated copy of the shape in one darker
   flat tone (or drop if <threshold contrast) — recraft-style.
3. **Boundary-intent classifier** (E3+E4+E5): for every boundary polyline,
   classify {ruler-straight | single-movement curve | detail/repeat} from
   the RASTER evidence (local straightness, curvature autocorrelation,
   parallel-neighbor detection, repeat periodicity), then fit under that
   class's constraints (line-lock with corner pins / low-tol cubic with
   width-constancy / per-instance preservation + regularized repetition).
3b. **Never-dissolve guard for drawn lines**: a thin label whose spine has
   consistent width + contrast + length is INK regardless of area —
   exempt from despeckle/dissolve floors (E3, ledger 0c).
4. **Per-shape layered emission** (E8, enables 2, kills 0h seams by
   paint-order overlap): shapes as single-subpath paths, background→detail.
5. **Region-local color** (E7): final colors = eroded-mask means per region
   (run-33 lead), no global centroid pull; optional single gradient fill for
   large monotone-ramp regions.
6. **Idealization judge** (P4): score = boundary-intent compliance + line
   evenness + region flatness + drawn-boundary preservation vs original —
   used at least as the tournament tie-breaker.

Paper support: LIVE's component-init/layer-order + UDF boundary-band loss;
Potrace's constraint-cone straightness (already ported) extended by corner
pins; SuperSVG path-efficiency; Depixelizing Pixel Art's similarity-graph
boundary heuristics; Deep Vectorization's explicit cleaning stage. Full
digests land in `research/docs/PAPER_NOTES.md`.
