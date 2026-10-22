# Research log

Append-only, newest first. **One log — no separate observations file.**
**Iterations are worktree-parallel** (research/loop/autoresearch.md
"Worktree-parallel iterations"): log an entry for **every candidate worktree** —
whether it ships alone, ships in a combination, or is discarded — not just the
shipped result. Each entry:
- **What was tried** — the specific change + which module/domain/worktree.
- **What the `tb.crops` grid showed** — including anything unrelated or
  disproportionate to the change (unexpectedly clean regions, odd side effects).
- **Verdict + the real reason** (orchestrator's own re-verified eye verdict, not
  the sub-agent's self-report). Benchmark delta if the sanity harness was run.
- **If discarded — a lead-grade note:** which target, which spot, which
  parameter, what it looked like — pickable-up later, never just "investigate."
- **If discarded when combined:** name the combination, so that interaction is
  not retried blind.
- **commit sha** for anything that shipped.

When picking the next iteration's candidates, skim recent discard entries here
for unfollowed threads worth promoting into research/docs/BACKLOG.md items.
Mission: `research/docs/PROJECT_SPEC.md`; `research/docs/archive/STATE.md` =
consolidated state; `research/docs/BACKLOG.md` = idea queue. Machine-readable
results → `research/loop/autoresearch.jsonl`; running narrative →
`research/loop/worklog.md`; in-flight worktree state (incl. the mandatory
`next_action` field) → `research/loop/autoresearch.iteration.json`.

---

## 2026-07-08 · Runs 21–22 (iteration 18 complete) — the TEETH iteration: A+B both ship, compound verified (c51d025 + ea329bd)

Attacked run-17's staged diagnosis (label chain erodes monster's tooth
spikes; fill fitter rounds the survivors) with a disjoint-scope A/B pair.
Both shipped; the compound was eye-verified explicitly: **teeth are now tall
AND sharp, approaching Recraft** — prev (B-only) was sharp-but-low, A-only
tall-but-scalloped.

**Run 21 — B-cornerfit SHIPPED (c51d025), fill emitter.**
`_fill_edge_corners` detects corners on the RAW crack-lattice edge polyline
(turn ≥80° over k=6 chords, NMS, two-scale localization ratio ≥0.7 to
reject tight smooth arcs; measured: teeth 90–117°, eye-triangles 117–127°,
smooth staircase floor ≤18° — ~60° margin) and the parsimony path splits
edges at corners, fitting each piece with endpoints exact so V-notches
survive as hard vertices. Verified from artifacts by orch-own renders,
including diff-LOCATED broaden grids: teeth scallops → sharp Vs; eye lenses
→ wedges; and a corpus-wide sharpness win — mountain pine tips, fox fur
wisps, crystals facet joins, logo-badge blade points. Landmine controls
smooth (rabbit heart/eye, elephant domes, mountain clouds). 2 targets
byte-identical; integrated render byte-identical to the artifact (exact
transplant). Lateral trades logged: mouth-left plateau step; two
capsule/arm 90°-steps (same angle class as teeth — not threshold-separable).
Lead: the mouth-corner swoosh square-step points at the capsule/fill SEAM.

**Run 22 — A-spikeguard SHIPPED (ea329bd), label chain.** Its pixel-level
diagnosis CORRECTED diag17: connected teeth lose only ~1px to smooth — the
half-height kill is DISCRETE. A sharp spike's sub-pixel tip anti-aliases
into midtones and quantization SEVERS it into a tiny same-label island
(corner tooth: 8px island, 4px from parent) which despeckle junked. The
guard rescues sub-floor light fragments iff anchored (survivor ≤5px),
contrast-extremal (gap ≥210 — population-measured: true tips 218, AA-fringe
falses ≤204; the brief's naive gap 60 fired 128 chopchop FALSE rescues —
the run-13 landmine confirmed and dodged), and weldable via a 2px clean
corridor that never overwrites survivors. Two refuted designs logged
(exemption-without-weld → floating comma; naive nearest-pair weld →
self-abort). Orch verification: corner tooth at (504,245) restored to full
quantize height matching original+Recraft; weld sites artifact-free;
chopchop planks flat, no daubs; 14 targets byte-identical (claim verified
5/6 on the integrated build; chopchop = equal-quality lattice reshuffles).
Sanity: monster 0.9587, elephant 0.853 flat; points 815→713 across it18.

**Iteration write-off:** the label-chain thin-boundary-feature FAMILY
(buttons/ring, heart-crown, cream-on-ink tips) now has a proven mechanism
to extend (A's rescue+weld with per-family signals) — queued as the it19
headline. Wait-time diagnoses this iteration: buttons/ring root-caused
(label chain, not skeletonization), heart-crown staged, strap-curl
attributed to stroke layer, width-metric methodology negative result,
scribble-nondeterminism item closed, v5 examples refreshed.

## 2026-07-08 · Run 20 (iteration 17 complete) — B-arcsupport SHIPS (c61755e); it17 = research + pin + A + B, all four kept

**Candidate B-arcsupport — VERIFIED, SHIPPED.** Its measurement REVISES the
run-15 diagnosis (log correction): the rabbit heart-top gap is NOT a
free-free pair diverging >72° off-chord — in 18/18 deterministic repros the
still-free end at (490.7,745.8)@1024 faces a notch whose counterpart ends
were already CONSUMED by a run-3 midpoint bridge, so no free partner exists;
chord support there is overwhelming (fan-min mean 41–43, bright-run 0). The
new pass (after the long-bridge block) generalizes bridging two ways: targets
= ANY other stroke's endpoint (free or not), and path = tangent-ray quadratic
ARC for short strongly-curved gaps (chord fallback). Measured constants with
margins: arc reach ≤2.5gw (true ≤1.8 vs false ≥4.4); chord turn ≤40°
(true ≤35 vs false ≥46) + fan-mean <50 (true ≤43 vs false ≥51, the thin
margin deliberately double-covered by the turn gate); NEW ridge2 ≥0.5 — ≥50%
of path samples must have light ground on BOTH sides at ±1.1gw (true ≥0.58
vs fill-edge ≤0.27) — this single gate kills ~100 chopchop scribble/fill
candidates. Orchestrator verification, twice (artifact SVGs, then the
integrated build vs deterministic head19 baselines): rabbit heart top CLOSED
(the objective) + head-tuft apex closed; chopchop trunk outline reconnected
×2 + coconut-cup rim + chair-joint micro-break, ZERO welds (struts/Vs/
lattice/deck eyed); scallop + ring stay-open controls held; elephant/monster/
fox BYTE-IDENTICAL to head19 — the determinism pin turned "no side effects"
from a sampling claim into a proof. 8 full-coverage pages, zero regressions.
Sanity: rabbit 0.7492 (−0.006 = idealization penalty, eye decisive),
elephant 0.853 byte-flat.

**Iteration-17 protocol notes.** Both candidates native-dispatched with
model inherited + deliberate effort; B silently stalled once and was nudged
via SendMessage (it was alive — measurement phase); every verdict came from
orchestrator-rendered grids off the shared artifact dirs; integration was
orchestrator-owned and one-at-a-time (pin → A → B) with re-verification at
each step; the wait time produced runs 17–18 (root-cause research + infra
fix) plus five diagnosis addenda now feeding BACKLOG/it18.

**B leads (→ BACKLOG):** heart lobes render FLATTENED (~5px label-map crown
loss — idealization refit, not bridging); rabbit tiny ring (424,737) renders
as a "v" hook every run (closed-loop loss in skeletonization); chopchop
serration S-wavy zone unchanged (existing item).

## 2026-07-08 · Runs 18–19 (iteration 17, partial — B-arcsupport still in flight)

**Run 18 — determinism pin (infra keep, da5d4b6, orchestrator-owned).**
Integration step 1, executed while candidates ran: `rng=0` at all six
`medial_axis` call sites (contours_exp 353/441/1122/1153, strokes 99/123).
The monster render is now byte-identical across repeated runs AND separate
processes (probe hash d68bde3c39; before the pin, four consecutive renders
produced four different hashes). The one-time tie-pick shift was eyed on
five targets (monster/rabbit/chopchop/elephant/fox, `orch17_pin_*.png`) —
lateral everywhere, no welds, no losses; sanity flat (monster 0.9595,
elephant 0.853). Payoff: "byte-identical SVG = skip" is now a routinely
available shortcut, diffpx spot-finding is noise-free, and integration
re-verification is exact. Incidental find filed to BACKLOG: rabbit's coat
BUTTONS render as a thin line + hook in ours (~(358,676)@1024) where
original and Recraft draw two circles — pre-existing, eye-loud, gold-pair
target.

**Run 19 — candidate A-apexsnap SHIPPED (1e0adb6).** Dispatched under the
full §1/§8/§9 protocol (native worktree, artifact dir, orchestrator-own
renders); agent survived one silent stall and reported with a CORRECTED
diagnosis: the monster apex nub was never a capsule-end overshoot — with
capsule strokes stripped, the nub is the fill fitter curling the tip of a
thin background-component tentacle carried under the capsule corridor
(fragmented branch keeps big components whole; only sub-400px beads were
absorbed). Fix, one mechanism: for each KEPT large light component
overlapping a corridor, absorb only overlap pixels farther than
sliver_reach=6.0px (windowed distance transform) from the out-of-corridor
body — junction roots and edge grazes stay. Measured margin: genuine grazes
max 5.0px vs carried-sliver mass 8–53px. Orchestrator verification (own
renders from `research/it17/candidates/A-apexsnap/` artifacts, then again
after integration onto pinned main): apex nub gone (560,690), mid-segment
double-render gone (600,712), left-end kink cleaner (524,732); capsules
5/5; 4 focus spots + 4 full-coverage pages, zero regressions; determinism
made the re-verify exact — only A's fix differs between renders. Sanity
0.9591 flat, points 815→773. Leads → BACKLOG: fill-fitter tip-curl is a
FAMILY (swoosh hooks suspected); Recraft draws the apex as a sharp Λ —
corner-aware capsule fitting (run-10 style) is the remaining headroom;
agent independently re-confirmed the pre-pin in-process wobble.

## 2026-07-08 · Run 17 (research, orchestrator-side) — render nondeterminism ROOT-CAUSED: skimage `medial_axis`, not k-means

Measured while iteration-17 candidates A-apexsnap/B-arcsupport were in flight
(no engine files touched — their scope). The standing "k-means
nondeterminism" explanation was WRONG:

- **k-means is innocent.** `_quantize` calls `cv2.setRNGSeed(seed)` per call;
  two full label-cleanup chains hash BYTE-IDENTICAL in-process
  (quantize `1116d670`, cleaned `ee3b0a20`, both runs).
- **`contour_svg` on identical inputs still diverges**, and the unified diff
  isolates it to the light-capsule stroke paths (fitted coordinates change).
  `svgcore.fit_open` is stable on fixed input (5/5 identical) — the
  centerline POINTS differ before fitting.
- **Root cause: `skimage.morphology.medial_axis(rng=None)`** (skimage 0.22)
  permutes the tie-pixel processing order with an unseeded RNG and consumes
  global numpy state. Demonstrated: same tie-rich mask, two consecutive calls
  → different skeletons; `rng=0` → stable in-process AND cross-process.
- This explains, in one mechanism: the chopchop wheel white-arc run-to-run
  variance, dark-stroke counts wobbling 195–200 (chopchop) / 64–68 (rabbit),
  the run-15 mountain crevasse shuffle, and the ~8k px render self-diff floor.

**Fix queued (one atomic commit at it17 integration):** pass a fixed `rng=` at
all 6 `medial_axis` call sites — contours_exp.py:353/441/1122/1153,
strokes.py:99/123. Outputs will shift ONCE (different tie-picks freeze), so
every touched target gets a fresh eye pass per the verify-by-looking rule —
never assume "same code, cosmetic seed" is a no-op. Probe scripts in the
session scratchpad; findings reproducible from this entry alone.

**Addendum — monster light-line loss map (same research pass).** Swept every
thin light-on-dark tophat component on the focus target against the current
render (presence = fraction of skeleton pixels light in the render): 12
qualifying components, NONE fully missing — the run-13 BACKLOG item "monster
drops a thin white scratch line" is RESOLVED by the run-15/16 capsule work
(closed by eye, not by the number: grid `models/v5/outputs/diag17_scratch.png`
at the 3 lowest-presence spots). What the grid DID show, vs original AND
Recraft (both sharp):
- **Monster mouth teeth render as soft scallops** (~x430-560/y230-280 @1024)
  — the white mouth region's zigzag edge is smoothed away by the fill fitter;
  original and Recraft keep sharp triangular teeth. Same disease run 10 cured
  on chopchop's DARK serration bands (corners-as-hard-nodes + miter), never
  applied to light-region boundaries inside dark shapes. Eye-loud on the
  FOCUS target → promoted to a top iteration-18 candidate.
- **Mouth-corner crease** renders as a wobbly thin curl (the known
  mouth-corner-hook lead; presence 0.51 at (499,250), tophat stats cv_w 0.49
  ratio 1.29) — folds into the existing BACKLOG item, now with a picture.
- Eye-triangle (504,189): acceptable; faint gray edge sliver only.

## 2026-07-08 · Run 16 (iteration 16) — 1 candidate, SHIPS (A-sliver, commit 9242186); first full §8/§9 protocol iteration

First iteration run end-to-end under the 9-section protocol: candidate wrote
its outputs to the shared artifact dir `research/it16/candidates/A-sliver/`
(new_/prev_ SVGs + notes.md) and EVERY orchestrator verdict below came from
grids the orchestrator rendered ITSELF from those artifact SVGs (§9 — the
sub-agent's own grid images were never reused); the ship decision was gated on
`tb.full_grid` FULL-COVERAGE pages (§8), not just focused spots — 16 pages
eyed across monster (4), fox (4), crystals (4), game-assets-2 (4), on top of
17 broaden crop-grids and 4 focused monster spots.

**Candidate A-sliver — VERIFIED, SHIPPED alone.** Change
(`models/v5/src/contours_exp.py`, `_light_line_capsules`): run-15's capsule
mechanism required >=3 label-chain fragments, so ~10 monster thin lights
carried WHOLE by the label map (fragments=1, coverage 0.6-0.87) still went to
the fill fitter and rendered as lumpy slivers. Fix: whole-carried components
are also stolen iff the mask itself confesses lumpiness — width variation
`cv_w >= 0.2` AND `wmean/max(med_w,2) <= 1.45` (rejects fat eye-tail-like
blobs, ratio >=1.53) with skeleton >=20px and >=0.5 light coverage; bead
pixels absorbed into bg (`src[beads]=bg`); new `_extend_into_light` tucks
capsule ends up to 8px forward (dot >=0.5 cone) so they terminate inside the
light line instead of stopping at the fragment edge. Capsule counts attribute
every visible change: monster 2->5, fox 4, crystals 1, game-assets-2 6,
chopchop/rabbit/elephant and all others 0 (gate held where it must).
Orchestrator verdict from its OWN artifact renders: monster's three lumpy
slivers -> clean constant-width thin light lines (the run-15 leftover lead,
now closed); fox whisker-crease and game-assets-2 broaden grids read as small
WINS, everything else lateral-or-identical; full-coverage pages show ZERO
regressions (fox haunch-crease sliver unchanged, crystals facet squiggle and
game-assets-2 spotted-hills differ only within the known k-means wobble).
Sanity in-worktree: monster 0.9596, elephant 0.8515 vs 0.8548 (flat, noise).

**Leads (new, -> BACKLOG):**
- **Mouth-corner hook** (monster x494-507/y240-261): cv_w 0.396 but ratio
  1.73 — falls BETWEEN the steal band (<=1.45) and the eye-tail reject band
  (>=1.53 is safe); discriminating it needs a donor-size or curvature signal,
  not more ratio-threshold tuning.
- **Donor stump**: where a sliver is stolen, the donor fill keeps a rounded
  stump (monster x531) — fill-side sharpening at capsule take-off points.
- **Wheel-arc nondeterminism**: chopchop wheel white-arc varies run-to-run
  with identical code+labels; dark-stroke extraction counts wobble 195-200
  (chopchop) / 64-68 (rabbit) — k-means seed or order sensitivity worth
  pinning before it muddies a future eye-diff.

Protocol proof points banked this iteration: §1 native dispatch + SendMessage
resume ✓, §5 /clear next_action rehydration at two sub-boundaries ✓, §8
full-coverage ship gate ✓, §9 artifact-dir + orchestrator-own renders ✓.

## 2026-07-08 · Run 15 (iteration 15) — 2 candidates, BOTH ship combined (A+B, commit 44351d0); first NATIVE-isolation iteration

First iteration under the hardened protocol: candidates dispatched via the
Agent tool's native `isolation:"worktree"` (no manual git plumbing), model
inherited (never set), effort recorded as a deliberate inherit per candidate,
delegation prompts carrying the full checklist (read spec+protocol first,
objective, scope boundary, focus/data paths, render recipe, report format).
Both agents died mid-run on a transient API server error and were RESUMED via
SendMessage with worktrees intact — state writes to iteration.json (with the
new mandatory `next_action`) carried the interruption losslessly; the
post-/clear rehydration hook chain was fired at the A-verified sub-boundary
and stated the next action verbatim from disk (persistence proof, part 1).

**Candidate A-lightbead — VERIFIED, SHIPPED in combination.** Change
(`models/v5/src/contours_exp.py`, fill-emission path only): run-14's premise
("label map carries the scratch continuously") was PARTLY WRONG — the label
chain (medianBlur + smooth/despeckle) itself dashes a ~1.5px light line into
bead fragments (monster vertical scratch = 6 fragments, coverage 0.52); the
fill fitter faithfully rounds each dash into a teardrop. Fix: white-tophat the
SOURCE (>60), keep thin (med w <=3.5px) long (skel >=30px) elongated (>=8)
light-on-dark (contrast >=60) components **carried as >=3 fragments** (the
chopchop-safety gate — a line carried whole stays with the fill fitter);
absorb the bead fragments into the surrounding dark label and emit ONE light
capsule along the source-traced centerline; width = ink excess/(contrast*len)
clamped 1-3px (mask width over-reads by ~2.5px of antialias skirt — first
render was visibly fat). Orchestrator verdict from its OWN renders: monster's
three scratch sites continuous at Recraft-like weight (prev: dotted teardrop
trails); chopchop 0 capsules fired, straw clean. Leads: capsule-end nub at the
scratch apex (~1024 (560,690)) — needs end-snap to the adjacent light region;
~10 more monster thin lights carried whole (fragments=1, coverage 0.6-0.87)
render as lumpy slivers — extending to min_fragments>=1 + a lumpiness test is
ready follow-up; `contour_svg_from_testbed`/`tb.svg()` don't pass `src_img`,
so capsules no-op there — verify through `get_pipeline(...).run`.

**Candidate B-longgap — VERIFIED, SHIPPED in combination.** Change
(`models/v5/src/contours_exp.py`, stroke network only): measured diagnosis
first — rabbit's breaks are free-end pairs at 2.2-6.7w, beyond bridge (1.2w)
and ridge-walk (4w) caps; traced the run-4 walker at each break: it DIES at
0-2.3w (absolute dark_lum test on thin antialiased ink; ridge-test failures
beside shading; turn budget burnt by per-step staircase jitter in 5-9 steps) —
"raise the cap" was the wrong lever. Fix: long-gap chord bridge after
bridging+extension — mutually-facing ends (cos >=0.3 both sides) within 7.0*gw
join iff the source shows ONE continuous dark line along the whole chord
(+-1.5px perpendicular-fan min: mean<140, frac(<160)>=0.6, **no bright(>176)
run over 2px**). Constants measured with margin: true breaks bright-run 0 /
mean <=118; must-stay-open gaps bright-run >=7px / mean >=143. Orchestrator
verdict from its OWN renders (bridge sites located via the new
`long_bridge_at` info, after a y/x-order misread put crops on flat fill — the
coordinates are (x,y)): heart outline closes at bottom tip + right lobe, paw
finger lines connect, scallop chain reconnects; chopchop weld landmines
(parallel struts, serration Vs) clean — bright-ground chords blocked exactly
as designed. Broaden co-win: elephant ear-V/toe-seam/belly gaps close. Leads:
heart TOP-LEFT lobe still open (ends diverge >72 deg off-chord — needs an
arc-aware support test, not a chord); run-4 walker should charge NET signed
turn, not |dTheta| per step (staircase jitter halves its range); watch
midtone-texture ridges between facing ends as the failure mode if a future
target regresses; chopchop chair-lattice junction tangles equal-weight in
new/prev (pre-existing, own backlog item); chopchop interior-scribble strokes
redraw differently run-to-run (nondeterminism lead — makes chopchop
eye-comparisons noisy).

**Combined + broaden (existing rules; full-coverage gate lands next
iteration):** A then B applied by git-diff into `_integrate`, eye-verified
after EACH apply (A: monster identical to A-alone; A+B: no interaction — A is
light-capsule emission, B dark-stroke bridging). Broaden: 15 diff-spotted
grids + 4 rendered-identical (coins, logo-badge/geometric/wordmark) all
eye-checked; mountain crevasse texture shuffle attributed (0 capsules, bridges
can't create light patches -> k-means nondeterminism, same family as run-14's
ticks); files-pile/game-assets-2 lateral in rough texture regions with
slightly more-connected edges. Sanity (in _integrate): rabbit 0.7468->0.7555
(+points 4073 — bridged outlines are real ink), elephant 0.8548 flat. One
process slip logged: the first sanity run executed against the MAIN tree via
stale cwd — caught because the numbers were suspiciously close; re-ran inside
_integrate. Absolute paths / explicit cd for harness runs, always.

---

## 2026-07-08 · Run 14 (iteration 14) — 2 candidates, BOTH ship combined (A+B, commit 3d251ad)

Scout pass found the two dominant chopchop residuals and pinned domains before
dispatch: the striped straw rendering as a SOLID BLACK BAR (label probe: the
straw's pale stripe labels, lum 155/210, are sub-120px fragments absorbed by
`_despeckle_labels` — which has no ink-lock — into the black outline, black
963→1585px in the probe window), and junction ink pooling (frond centers,
chair-frame/strap crossings). Quantize domain vs stroke domain → genuinely
independent, N=2.

**Candidate A-strawguard — VERIFIED, SHIPPED in combination.** Change
(`quantize_contours.py`): light-accent guard in `_despeckle_labels`, two-pass.
A sub-floor light component ≥10px is exempt from despeckle when its ring —
**after excluding fellow sub-floor fragments** — is ≥0.6 ink and the component
is ≥80 lum lighter than that ink. The fellow-fragment exclusion is the
load-bearing insight (sub-agent's, from a failed first attempt): stripes
sandwich each other, so a white fragment's ring is ~40% ink + ~40% blue
fragments and no plain ring test fires; once both junk, `_reassign_pixels`
hands the whole straw to the outline. A genuine light fleck sits ON a big
surviving fill → still dissolves. Orchestrator re-verified: straw striped at
rim AND bend. Broaden co-wins (each eye-confirmed): crystals pink gem Y-vein
continuous again (prev broke it dark); monster scratch-line T-branches render
as thin tapers near Recraft (prev: blunt wedges); **fox eye specular glint
restored** (prev lost it entirely; Recraft keeps it) — initially flagged as a
suspect new speck, resolved by locating all rescued-light clusters and zooming:
the 301px cluster IS the glint. game-assets potion highlight splits into its
true two-piece shape. Cost: chopchop SVG 219→254KB (+16%), points 12.9k→15.8k.

**Candidate B-junctionpool — VERIFIED, SHIPPED in combination.** Diagnosis
first (sub-agent): the "pooled blob" was TWO element types — the chair-crossing
splat was a blob-split FILL polygon (pool EDT 2.85×med_w passes blob_factor,
251px passes the keep gate → heart-shaped splat), the frond-center mass was
swollen RIBBONS (the swell profile follows pooled junction EDT, fattening every
converging branch). Measured discriminator: junction pools extend ≤~3.8×med_w
and contain a deg≥3 skeleton node; genuine glyph blobs run 6–14×med_w. Change
(`contours_exp.py`): (1) a kept blob component with extent <4.0×med_w
containing a deg≥3 node stays in the stroke mask (17 fired on chopchop);
(2) swell clamp — `swell &= junc_dist > 2.5*w_body` via per-chain-point
distance to junction nodes. No snap radii touched (run-2 weld landmine);
run-10 bands and run-13 wiggle gate untouched by construction. Orchestrator
re-verified: frond center crosses cleanly, chair splat gone, serrations and
coconut unregressed. Side effect logged: width calibration 5.83→6.08 (pool px
now count as stroke ink), line weight visually unchanged; branch topology
shifts (220→196 branches) with no visible harm. Broaden co-win: rabbit
cabbage-leaf base black pooling cleaned.

**Combined (orchestrator, `_integrate`, A then B, re-verified after each):**
no interaction regression — A is fill-label domain, B is stroke domain.
Full broaden: 13 rendered grids eye-checked + 3 byte-identical skips
(logo-badge/geometric/wordmark); pizza-box/logo-lineart diffs are pure edge
drift (invisible at zoom); mountain lateral (crevasse picks up small ticks —
Recraft's own crevasse has similar nicks); game-assets-2/app-asset/files-pile
lateral shuffles in already-rough texture regions; shield lateral-to-better
(prev's over-wide purple rim crescent thinned). **Sanity: chopchop quality
0.144 → 0.6732** — the black straw bar was a major driver of the "chopchop
metric ≈ 0.14 known-meaningless" quirk (partially explained now); elephant
0.8533/ssim 0.961 flat.

**Leads (new):** strap-end curl at the chair crossing traced loopier than
reference in ours (free-end shaping, not pooling); **vectorizer beads thin
light regions** — monster's vertical scratch is in the label map end-to-end
(923px pre-despeckle, 928 after all stages) but `contour_svg` fragments a
~1-2px light region into a dotted bead-trail → the light-hairline fix's second
half lives in the fill emitter, not quantize; A×dissolve interaction to
remember: rescued blue stripes survive `_dissolve_speckle` only because white
ring fraction 0.47 < its 0.6 ring-dominance guard — lowering that threshold
would eat them; occasional off-color light-gray fleck where a rescued fragment
quantizes grayish (chopchop plank end) — minor vs the black mass it replaces.
Iteration hiccup logged: one integration command ran with a stale cwd inside
the B worktree and created a NESTED worktree + rendered unmodified code —
caught because the cp failed loudly; always absolute-path worktree ops.

---

## 2026-07-08 · Run 13 (iteration 13) — 2 candidates, BOTH ship combined (A+B, commit b409934)

Two independent candidates in worktrees off best `4c616ce`… (`e0a1c45` local
best snapshot); both orchestrator-verified, combined one-at-a-time in an
`_integrate` worktree with re-verification after each apply. Integration
surfaced two regressions in B; both fixed by orchestrator-authored guards
inside the integration worktree, re-verified, shipped.

**Candidate A-noodles — VERIFIED, SHIPPED in combination.** Change
(`backend/contours_exp.py`): three-part texture gate on the stroke network —
`_wiggle_rate` = alternating-turn density (total |turning| − |net turning|) /
arclength per branch; real drawn lines measure ≤1.9, texture daubs 2.4–7.8
(measured, not guessed); gate at >2.2 before `_merge_continuations`, plus a
small-component gate and free-end trimming; ink dropped from the stroke layer
is carved into the FILL layer so texture reads as soft daubs, not vanishing.
Grid (orchestrator's own render): chopchop trunk's squiggly stroke "noodles"
become soft fill daubs matching Recraft's treatment; knot daub soft; real
lines (serrations, outline, eye) untouched. Residual lead: a few S-wavy
strokes sit just UNDER the gate (wiggle 1.5–2.2) — a lower threshold welds
real lines, so any further cleanup needs a second signal (width variance?
fill-contrast?), not a lower cutoff. Second lead: `ink_extended≈102` on
chopchop — run-4 ridge extension regrows small hooks off texture remnants;
worth an ablation pass.

**Candidate B-speckle2 — VERIFIED after 2 debug guards, SHIPPED in
combination.** Change (`quantize_contours.py` + `contour_lines.py` call):
`_dissolve_speckle(labels, centers, 300)` after `_smooth_labels` — exactly the
run-12 lead (floor ABOVE despeckle's 120). Guard saga, all caught by
eye-verification, all fixed in `_integrate` by the orchestrator:
1. **Ink-locked** (from dispatch): counts zero'd for dark labels — dissolve
   never feeds the line network.
2. **Ring-dominance ≥0.6** (debug 1): unguarded B1 ate the orange gem's facet
   mosaic on crystals (a facet's neighbors are many labels; a noise daub sits
   in a single-label ring). Guard restored facets; chopchop win held.
3. **Darker-only luminance** (debug 2, found in broadening): combined AB
   deleted a drawn cloud wisp beside the mountain peak — isolated to B (A
   never touches fills). Noise daubs are DARK stains; LIGHT accents are drawn
   intent (cloud wisp, plank-top highlight — Recraft keeps both). Dissolve
   only when source is darker than target. Cloud eye-confirmed restored at
   the actual wisp coordinates (located via label-map analysis, not assumed).
Effect: chopchop plank speckle flattens to clean planks.

**Combined verdict (orchestrator eye, all 8 targets under final guards):**
chopchop planks flat + noodles gone + serrations sharp; crystals facets intact
AND the pink shoulder-fleck that prev painted on the orange gem is GONE in new
(original has no pink there — prev artifact removed, a small bonus); mountain
cloud restored; elephant/rabbit/fox clean (checked pre-darker-guard; guard
only makes B dissolve LESS, and their B-fire sites were re-eyed);
logo-geometric + monster-flat-line re-rendered fresh under final AB2 —
diffpx 0 AND eye-identical. Non-regression lead spotted on monster: BOTH new
and prev drop a thin white scratch line inside the dark shape that Recraft
keeps — pre-existing hairline-detail loss, → BACKLOG. Sanity: chopchop
quality 0.144 (known-meaningless for this target), elephant 0.8574 /
ssim 0.9624 / 2645 pts — series-consistent.

**Interaction note:** A+B combined cleanly (A = stroke layer, B = fill labels;
disjoint domains). The two B regressions were B-alone effects exposed at
integration time, not A×B interactions. No bisect needed.

---

## 2026-07-08 · Run 12 (iteration 12) — FIRST worktree-parallel iteration: 2 candidates, A ships, B discarded

Architecture test + real iteration. Two independent candidates dispatched to
parallel git worktrees off best `32da8eb`; orchestrator independently
re-rendered both (did NOT trust sub-agent self-reports) and reached a different
verdict than one sub-agent.

**Candidate A-fleck — SHIPPED (commit 4c616ce).** Change: adjacency-based fleck
absorption in `backend/contours_exp.py` `extract_contour_strokes` — a small
(<250px) dark-label component 8-adjacent to a ≥10× larger component of a
*different* dark label is reassigned to the big neighbor (stroke-layer copy
only; fill `labels` untouched). This is the run-11 "next design" (union family
was refuted there). `tb.crops` (orchestrator's own render, cols
original|A|prev|recraft): the medium-brown fleck-wedges nested in chopchop
serration notches are absorbed into the black line they hug; serration teeth
stay sharp; no shading welded (large bands never hit the 10× ratio). Broaden (all
EYE-CHECKED, not inferred): rabbit absorbs a stray blue dab (collar) + a gray
belly-line fleck — small genuine cleanup; **elephant** grid A-vs-preA visually
identical (true no-op, `flecks_absorbed=0`, single dark label); **fox** grid
A-vs-preA equivalent by eye — eyes/ear-lines/whiskers/fur intact, nothing
welded or broken — but **81 flecks DID fire on fox** (it is NOT a no-op; the
low diffpx only meant each reassigned fragment is tiny). logo/monster
bit-identical.

Correction on record: I initially labeled elephant AND fox "no-op within noise"
from `flecks_absorbed`/diffpx alone. That was wrong for fox (81 flecks fired) —
vision-first means render and look, never infer "probably fine" from a number,
including a noise-floor number. Both grids were then rendered and eye-checked
(outputs/it12_eyecheck_{elephant,fox}.png); both clean, verdict holds. **Disproportionate side effect (noted):** chopchop
SVG ~50KB smaller (259KB→209KB) and 234 flecks absorbed — each fleck had been
emitting its own brown micro-stroke, so the fix cleans the outline AND cuts
file size. quality (elephant sanity) 0.849, points 2604.

**Candidate B-speckle — DISCARDED (orchestrator overruled the sub-agent).**
Change (in its worktree, never merged): `_dissolve_speckle` in
`quantize_contours.py` dissolving sub-`min_area` NON-dark components into their
majority neighbor, called after `_smooth_labels`. Sub-agent self-reported
"beats prev (mild)". **Orchestrator's own eye verdict: LATERAL — not clearly
better, discard.** Lead-grade note for later: on chopchop the tan trunk/plank
speckle is *barely* changed at spots (2600,1500)/(3000,1400)/(1800,1200)
because `_despeckle_labels` already runs first at floor `max(min_area,16)=120`
and clears most <120px fill components before `_dissolve_speckle` sees them —
so the pass is nearly redundant. **To make it real, it must dissolve at a floor
ABOVE what despeckle already applies** (e.g. 200–400px) and/or target the
components `_smooth_labels` *re-creates* afterward; retry only with that
change, on the trunk-plank speckle specifically. One observed non-speckle side
effect: a thin white seam between a dark blob and its outline got filled solid
(a blob's tiny component handed to its dark surround) — a fill change slightly
outside the "speckle" framing, worth watching if retried.

**Methodology finding (affects all diffpx gating, not just this run):** the
pipeline is **non-deterministic across renders** — same code, two renders →
~8.3k-pixel self-diff on the elephant (cv2 k-means is not fully seed-stable
across processes). So "diffpx" spot-finding carries a per-image noise floor
(~8k elephant). A number below it does NOT imply "no change": fox diffpx 8379 ≈
floor yet 81 flecks fired — the reassignments were just individually tiny, and
only the eye-check confirmed them harmless. The EYE verdict — the actual gate —
is what settles it; treat diffpx as a spot-finder, never a verdict, and never
infer a candidate is fine from it. New
BACKLOG item: consider pinning k-means determinism for cleaner ablations.

**Architecture test result:** 2 parallel worktrees ✓; orchestrator
independently re-verified both, overruling B's self-report ✓; `/clear`
mid-cycle resume surfaced the live state (both single-winner and simulated
multi-winner mid-merge) ✓; both worktrees removed regardless of outcome ✓.

---

## 2026-07-07 · Run 4 — source-ink ridge extension (commit 5eb37ad)

**What changed:** bridging (run 3) spans gaps ≤1.2w; longer ink runs lost by
despeckle/label-smoothing still broke lines (rabbit heart, elephant ear). A
still-free end now walks the SOURCE raster's dark ridge (probe fan, darkest
sub-`dark_lum` pixel per step, ≤4 widths), snapping to another stroke if
reached, else keeping the traced tail with a taper at the true ink end. Two
guards proved essential (debug attempt 2): a **perpendicular ridge test**
(light ground within ~1.1w on both sides each step — never roam filled
regions) and a **~120° cumulative turn cap** (kills blob-boundary curls).

**Eye verdict:** rabbit heart arcs + coat edge near-continuous, sleeve and
carrot-vein joins closed; elephant's lost ear line completes to the silhouette;
chopchop's long-detached handle outline finally attached (fixed a pre-existing
defect); fox/crystals equal-plus; mountain/logo/monster unchanged. 8/8.

**Benchmark (sanity):** rabbit 0.713 → 0.7272. Elephant composite 0.8708 →
0.8599 with FLAT sub-metrics (ssim −0.0015) — dip sits in the composite's
noisy coherence/local terms while the eye is clearly better; logged as a flag,
not a gate. Unguarded version (roaming walker) was caught by eye on chopchop
and never shipped — negative result kept.

**Next:** true source gaps (light-pixel jumps where tangents agree) — riskier;
curvature drift; chopchop junction ink pooling.

---

## 2026-07-07 · Run 3 — bridge free ends across label components (commit 2570c63)

**What changed:** the label map breaks a drawn line wherever a lighter region
crosses it (straps, highlights, AA fuzz); the pieces land in different
components, share no skeleton node, and every break rendered as a dash-gap —
rabbit's outlines were dashes. In `extract_contour_strokes`, a free end now
snaps onto another stroke within 1.2 widths when the target lies <60° off its
outward tangent (never sideways onto a parallel neighbor); mutually-facing free
ends meet at the midpoint; snapped ends lose free status (no taper, no
stub-drop — which also rescues tiny bridge dashes).

**Eye verdict:** rabbit heart/cheek/paw dash-gaps closed; elephant ear
junctions now fully joined (they were cross-component too); chopchop safe (60°
gate rejected all parallel-line snaps); crystals/fox/mountain equal-or-better;
logo-geometric/monster-flat-line bit-identical. 8/8 no regression.

**Benchmark delta (sanity):** elephant 0.8669 → 0.8708 (above the 0.8682
baseline — bridging restores real ink, so even the noise-loving metric agrees).
Rabbit first reference: 0.713 @ 4339 pts. Focus target moved elephant → rabbit
this run (defect showed there; `./autoresearch.focus`).

**Remaining (logged in BACKLOG):** long label-map losses (>1.2w) still break
rabbit's heart-left outline — needs source-ink-continuity extension (walk the
darkness ridge in the ORIGINAL raster beyond the label map).

---

## 2026-07-07 · Run 2 — junction anchor: flush joins, no more nubs (commit c0adad6)

**What changed:** `extract_contour_strokes` (contours_exp.py) anchored branch
ends at the junction node-cluster *centroid*; ink pooling elongates that
cluster, so the centroid sits off the through-line's centerline and the round
cap pokes a nub through it — visible on the silhouette (elephant ear T) as a
bump into the sky. Now ends anchor to the nearest pixel of another kept
branch's centerline within a 0.8-width radius (fallback: centroid), so caps
land flush under the through stroke by construction.

**Why 0.8w:** the first attempt (1.5w) snapped ends onto *parallel neighboring*
strokes in dense-line art — chopchop grew detached ends and white slivers.
Through-lines pass ≤0.5w from the centroid; parallel neighbors sit ≥1w away.

**Eye verdict (8k grids, new vs prev vs Recraft):** elephant T-nub gone and
Y-join flush (both now match Recraft's cleanliness); chopchop joins continuous;
crystals facet-edge breaks now connect; rabbit/fox/mountain unchanged;
logo-geometric/monster-flat-line bit-identical. 8/8 no regression.

**Benchmark delta (sanity only):** quality 0.8682 → 0.8669 (−0.15%), ssim
0.9643 → 0.9630 — expected: the nub covered source ink, and the metric rewards
copying it (PROJECT_SPEC §4). Eye verdict rules.

**Negative results kept:** (a) "dropped junction-junction connector" hypothesis
refuted on the elephant — contour_lines drops zero such connectors at defaults;
(b) missing-ink clusters are mostly the deliberate width_scale=0.85 undershoot,
not gaps — don't chase them as defects.

**Next:** rabbit's ear line stops short of the outline in both versions — a
*cross-component* junction (different label components ⇒ no shared skeleton
node ⇒ anchoring can't reach). That's the remaining true "crossing gap" class.

---

## 2026-07-07 · Loop N+1 — course correction: vision-first

**User verdict on the milestone:** benchmarks say we beat Recraft; eyes say
"<70% of their quality". Wobbly lines, width thinning, shadows painted over
line art. New goal set: research + improve continuously, judge by grid-crop
vision (ours vs Recraft vs ORIGINAL), idealize instead of copying source
noise.

**Done this loop:**
- Memory + docs infrastructure created (this file, STATE.md, BACKLOG.md) —
  updated every loop from now on.
- `backend/testbed.py` started: disk-memoized stage cache (image+params hash →
  labels/graph/fit results) so single-variable experiments run in seconds
  instead of 2-7 min.
- Vision diagnostic protocol: `testbed.crops()` renders ours/Recraft/original
  grid crops for eye judgment.
- Agents running: grail wall-clock (owns engine.py), stroke junction
  ink-pooling (owns strokes.py).

**Learned:** (from earlier tonight, context for the record)
- Independent-point DiffVG cheats via region overlap (2.5px divergence) —
  fixed with shared-edge parameterization; integrity judge catches the rest.
- Post-DV quality is coarseness-insensitive on clean partitions → coarse fits
  + DV = compact wins; but coarse fits can carry unheva unhealable slivers on
  detail-rich images — judge damage post-refinement.
- Both library "regressions" (wordmark, shield) were cheat-DV cleanup.

**Done (continued):**
- `backend/testbed.py` shipped and smoke-tested: stage cache works (fit 8.2s
  first run → 0.00s cached); `tb.crops()` produces original|variants vision
  grids (aspect-alignment bug found and fixed same loop).
- First vision diagnostic (outputs/diag_grid.png) confirms the user's
  defects precisely: three-way junctions wobble and thin, toe outlines
  angular, line width visibly varies vs Recraft's uniform strokes.
- Agents spawned: (a) literature/web research on clean-line vectorization
  (centerline methods, curve fairing/clothoids, sketch simplification,
  commercial tools' mechanisms); (b) width-constant contour experiment —
  full line network as constant-width strokes painted on top, judged by eye
  via testbed grids (owns backend/contours_exp.py).
- Still running from previous wave: grail wall-clock (owns engine.py),
  stroke junction ink-pooling (owns strokes.py).

**Landed later this loop:**
- **Grail wall-clock 289.6s → 79-84s (3.7x, verified)**: the three shared-DV
  refines now run concurrently in the process pool (spawn-safe worker
  rebuilds ctx in the child), structcheck threaded, torch threads governed
  per worker. Board identical to reference. engine.py has phase timing in
  the result dict now.
- **Clean-line research survey (agent, full citations in transcript /
  BACKLOG)**. Core diagnosis: clean-output systems (Potrace, Vectorizer.AI,
  Image Trace) fit the SIMPLEST curve within a tolerance band of the
  evidence; our refiner minimizes L2 to the raster and converges TOWARD
  noise. Ranked prototypes:
  1. **Deadband fidelity + curvature-variation (MVC) regularizer** in the
     shared-edge refiner; corners detected first and exempted (PolyVector
     lesson). ψ(r)=max(0,|r|−τ)², τ≈0.5px; κ(t) closed-form on cubics.
  2. **Potrace-style parsimony refit** in svgcore: minimal-segment DP
     (±0.5px straightness band), sub-pixel vertex adjust, tangent-to-polygon
     fitting (automatic G1), area-preserving Bézier merge.
  3. **L0 gradient-minimization pre-pass** (literally demonstrated on
     clip-art JPEG cleanup) + refine against the IDEALIZED raster.
  Later: centerline+width-profile strokes (Bao & Fu near-constant width),
  primitive/symmetry snapping (Vectorizer.AI's "designed" look).

**Landed (later still):**
- **Junction ink pooling** (strokes.py): filled discs at deg≥3 skeleton
  nodes (radius from local EDT max, gate 1.25× half-width; disc beat convex
  hull), + union-find contraction of sub-threshold junction-junction
  connector branches — root cause of the X-crossing pinch was medial_axis
  splitting shallow X's into two 3-way nodes whose connector got filtered.
  Elephant hybrid q 0.9094→0.9107 (+2σ), worst-region improved; visual: the
  smile/trunk crossing now meets at a single knot like the source. Width
  flare-blend near junctions REJECTED (EDT measures pooled union → paints
  outside ink, −0.0018 q). Emitter has ±0.0008 q run-to-run nondeterminism
  (threading in fill fit) — validate stroke changes on pickled contexts.

**All three line-quality agents landed (eye-verified):**
- **Width-constant contours = the breakthrough** (`contours_exp.py`, wired as
  `contour_lines` pipeline + `sb-contour`/`grail-contour` candidates): full
  dark network as constant-BASELINE centerline strokes (global width from
  ink-area calibration ≈5.95px; genuine swells + free-end tapers kept as
  symmetric ribbons; shape gate p90/med≥1.5 keeps eye glyphs as fills).
  MY eye check of the 4-way grid: uniform confident weight, clean junctions,
  round toes — clearly Recraft-class line work. 703 pts / 39 paths / 10KB /
  2.6s (q=0.864 — metric punishes idealization as expected). Remaining gap
  is fills/palette, not lines.
- **Deadband+MVC v3 refiner** (`refine_shared_v3.py`, NOT yet default):
  τ=1/255, λ=15, κ clamped at 2px⁻¹ (naive MVC too stiff for Adam), corners
  masked r=4. Long curves visibly calmer; known regression: thin-sliver tips
  blob. Needs multi-image validation + sliver gate before swapping in.
- **L0 idealization** (`idealize.py`, NOT a default): hurts clean flat inputs
  (plateaus→extra clusters→wobbly iso-contours, 825→2500 pts) but WINS on
  noisy detail-rich (fox: integrity 0.481→1.0, −27% size, watermark erased).
  Wire later as opt-in gated on a noisiness heuristic. lam=0.02.
- Junction ink-pooling landed earlier (see above).

**Cross-image QA of contour_lines (agent, eye-verified) + hardening:**
- Wins on genuine line art: rabbit (melted cheek-fluff → drawn lines),
  fox (75 vs 637 paths, q +0.012), chopchop (smile/sunglasses/leaf veins all
  cleaner, 297 vs 743 paths). Failure mode found: thick uniform dark BANDS
  (shield rim 36px, badge ring 40px) pass the shape gate and get
  stroke-ified at network width → silhouette erosion (q −0.28).
- FIXED: wide-band gate in contours_exp (med_w > max(12, 1.4% of max dim) →
  stays a fill) + dark_lum exposed as pipeline Param. Verified: shield
  0.553→0.847 (beats its 0.832 baseline), badge 0.799→0.900 (beats 0.876),
  elephant network kept (0.861@39 paths). contour_lines now safe standalone.
- Minor open nits: small closed rings become broken arcs (shield rivets),
  occasional gap/spur at dense junctions (rabbit charm).
- E2E after everything: grail 77s / fast 7.4s, boards stable; sb-contour
  loses on the metric (expected — metric can't see the drawn look) →
  BACKLOG: line-consistency metric component.

**Potrace-parsimony fitter LANDED (svgcore + wired):** full §2.2-2.4 port in
Rust — constraint-cone straightness (real potrace semantics, not the naive
0.5px test which over-segments 10x), lexicographic DP, sub-pixel vertex
adjust, α-family tangent-constrained cubics, area-preserving opticurve
merge. On RAW lattice polylines (no pre-smoothing): opttol 0.2 beats
smooth+Schneider on ALL axes (0.9164/1247pts/17.3KB vs 0.9151/1337/18.6KB);
0.5→1023pts@0.9157, 1.0→937@0.9134 — marching into Recraft's corner above
Recraft's quality. Eye-verified at 8192 zoom: no S-kinks, no notches, crisp
tapers. 32ms/120 edges. Wired: boundary.loops_to_svg_curves(parsimony=),
shared_boundary Param, candidates sb-pars02 (fast) + grail-pars05/10.
Caveats: alphamax 4/3 flips a fill (avoid); closed islands fitted as
pinned-open (cyclic DP would save more).

**User suggestion → preprocessing sweep agent running:** unsharp mask,
bilateral, mean-shift, combos + ADAPTIVE-k coupling (L0's missing piece).

**Next:**
- Grail e2e with parsimony candidates (running); v3 validation + preprocess
  agents out; integrate on GO.
- Line-consistency judge component; artifact refresh.

---

## 2026-07-06 → 07 (pre-docs, summarized)

Shared-boundary vectorization built and shipped (exact reconstruction,
boundary graph, per-edge Schneider fitting, smoothing, dissolve, split
paths). Shared-edge DV v1→v2 (honest, 3x faster, color opt). structcheck
integrity judge. Centerline strokes prototype (clean tips). Pareto frontier
mapped (tol5/w13 = 679 pts). Elephant: 0.9317@727 / 0.9246@679 / 0.9390@1337,
integrity 1.0. SVG-Bench still leading all splits. Library 16/16 grail,
17/17 fast. Milestone artifact:
https://claude.ai/code/artifact/24a07afa-9af5-48a3-8d42-87ad5fd12e52

## 2026-07-07 · Preprocessing sweep landed (user suggestion)

Bilateral (d9,σc50,σs9) = safe win: parity on clean flat, rescues soft-shaded
AI art (rabbit coat seams solid again, q .669→.757 pre-DV; fast-tier verify:
sb-bilat 0.8327@2225 = top compact candidate). Mean-shift (sp12,sr30) = noisy
detail winner (fox −37% pts, most "designed" look) but eats small details —
candidate only. UNSHARP REJECTED with data: overshoot mints new colors,
+30-60% unique colors, MORE halo clusters (inverted hypothesis). Adaptive-k
unnecessary — merge_de consolidation already adapts downstream. Wired:
preproc param in shared_boundary + candidates sb-bilat / grail-bilat /
grail-ms (meanshift+parsimony). backend/preprocess.py has the recipes.
Also this loop: git repo initialized (v3 = first commit), models/vN
snapshot convention, parsimony e2e (pars05+dv q=0.9394@1023 board 2nd).

## 2026-07-07 · v3 refiner swapped in (GO) + hairline hunt

v3 (deadband τ=1/255 + MVC λ=15, sliver-gated) validated across 5 images:
eye equal-or-better everywhere, no new artifact class; the sliver-tip blob
was killed by a DYNAMIC thin-zone gate (tips extrude during optimization —
init-time masks miss them). Swapped into engine DV worker. e2e: 76s, winner
0.9250@727 (metric −0.6pt = designed noise-divorce); MY grid check: v3
strokes evener than v2, toes rounder, closing on Recraft.
NEW BUG surfaced by validation: shield/pizza/badge emissions have deep-zoom
hairlines BEFORE refinement (integrity 0.1-0.8; elephant/rabbit 1.0) —
contradicts coincidence-by-construction; agent hunting root cause
(suspects: split_paths grouping, dropped directed edges in region_loops,
non-square viewBox).

## 2026-07-07 · Canvas-frame hairline bug FIXED (agent root-cause + patch)

The shared-boundary guarantee only covers INTERIOR edges — canvas-frame
edges (vs outside label -1) are single-coverage, and smoothing rounds canvas
corners / fit_open bows ~tol across 90° corners → real hairlines at the
frame. FIX: border edges bypass smoothing/fitting entirely, emitted as exact
line-cubics (one per straight run). SECOND bug: structcheck itself had an
aspect-rounding measurement artifact (root width/height vs viewBox → 0.4px
global shift = fake hairline row); fixed by rewriting dims to the raster.
Verified: shield 0.832→1.000, elephant/rabbit 0.727→1.000 (they had it too,
just less), badge 0.127→0.832 (residual = near-threshold AA noise), pizza
0.216→0.526 (residual = THIRD bug: thin regions evert under win-9 smoothing
— opposite edges cross; 1.000 at smooth_win=0; backlogged). Also noted:
resnap_refined has the same latent frame exposure if ever reused.

## 2026-07-07 · v4 — vision-first line/fill idealization (goal-directed)

Direct attack on the user's "<70% of Recraft" verdict, judged by eye at zoom:
- Parsimony-fitted SHADING boundaries (fill_parsimony=1.0, fill_smooth=0 in
  contour_lines): shading regions now read as flat idealized shapes with
  wobble-free edges — the fill/shading gap, not just lines. Beat Schneider
  fills by eye (fill_grid.png) at 918 pts.
- Line weight width_scale=0.85 default: tracks Recraft's line weight (Recraft's
  lines are boldish; ws1.0 was a touch heavy, 0.72 too thin).
- Exposed width_scale + fill_parsimony as contour_lines Params.
VERDICT (final_full.png full-frame, final_zoom.png deep-zoom, vs recraft):
lines uniform+confident, fills clean flat shapes — now in Recraft's quality
tier. Three cited defects (wobble / width-thinning / shadows-over-lines) all
resolved. Residual gap = subtle palette/shading-color choices (Recraft's
softer blue-gray tints) + occasional shading-shape simplification, NOT
structural line/fill quality. models/v4 snapshot committed.
Remaining backlog for parity: palette idealization (match Recraft's shading
tints / merge to fewer cleaner shading shapes); line-consistency judge so the
tournament PICKS these idealized candidates (metric still underrates them,
so contour_lines must be run directly rather than auto-selected).

## 2026-07-07 · PAUSED — handoff (see docs/RESUME.md)

User paused the work to resume next week. Confirmed the contour_lines output
(the direct command) is "very good" and fast. Fresh defect report to attack
next (now top of BACKLOG + detailed in RESUME.md):
1. Perpendicular stroke crossings leave GAPS (caps stop short of intersection).
2. Some line curvatures differ from the original (centerline smoothing/fit).
3. Rectangular nub artifacts where strokes join (butt caps / segment seams).
All three are stroke-layer issues in contours_exp.py / strokes.py. After them:
palette idealization (Recraft's softer shading tints) is the last quality gap.
State snapshot: v4 (git c463914), docs/RESUME.md is the single start-here doc.

---

## 2026-07-10 · Segment 2 armed (runs 41-48): audit-24 reframe, v10 cut, it24 dispatched, diagnosis sweep

USER re-armed the loop: "push past Recraft, beating our own last shipped
version every iteration." Boundary work: audit24 (full-set zoomed eye audit
at HEAD) produced VISION.md (USER blueprint + ABSOLUTE close-out bar) and
audit24/FINDINGS.md (root causes E1-E8, process failures P1-P4 — the
plateau mechanism was relative close-outs + low-zoom verdicts + local gates
on structural causes). v10 cut at 01e80e0 (runs 38-40); v9 re-frozen;
staged→v10.

it24 dispatched (worktree candidates): A-transown (E1 transition-ownership
in the label chain; app-asset primary) + B-lineintent (E4/E5 corner-pinned
ruler-straightness in geometry/fit; monster primary — ledger 0k). Both
briefed with paper mechanisms mid-flight (Potrace alphamax + straightness
certificate → B; Depixelizing two-tier shading/contour edges + T-junction
rule → A).

Orchestrator diagnosis sweep while candidates ran (all logged in jsonl +
worklog; highlights):
- **Run 41**: recraft_gap harness had been rendering STALE v5 code since
  ~run 33 (hardcoded sys.path) — fixed to models/staged/src; full v10
  re-baseline taken. v10 cut was missing data/frontend/outputs symlinks.
- **Run 42**: native-res ramp census NEGATIVE (resolution confound) —
  corrected coordinate frame identified (working-res, label-boundary,
  width-normalized).
- **Run 43**: E2 shadow census at working res — clean separation: drawn
  flat 0-1px ramp p50 vs soft shadows 7-20px + 5-7 labels each; rabbit
  ground reclassified SOFT (recraft idealizes it). E2 gates now measured.
- **Run 44**: batch-1 paper digests → PAPER_NOTES.md (8 PDFs; Potrace
  corner semantics, VectorArk degradation model + rounded polygons,
  Depixelizing edge classes, topology-on-simplified). Extracts forwarded
  to in-flight candidates.
- **Run 45**: 0h DIAGNOSED — recraft is overlap-sealed (seam=0 on 7/10);
  seal-stroke PoC kills our seam class (84→0.7) + fixes monster eye smudge
  by eye; ship fix = underpaint dilation ⇒ 0h+E8 = one it25 candidate.
  Recraft's own chopchop scores 0.072 at deep zoom (their bar is
  normal-zoom — calibrates ours).
- **Run 46**: degradation suite BUILT (clean-truth idealization gauge):
  v10 baseline dSSIM crystals .873 / chopchop .877 (== audit's eye
  ranking). Load-bearing: facet melt/ridge loss reproduce from CLEAN
  flat-color input — E3/E4/E5 are engine behavior, no source-noise alibi.
- **Run 47**: 0l culprit CORRECTED — flatten exonerated by toggle; open
  gaps = E1 shrapnel slivers (2-3 interior clusters); A-transown gains an
  objective acceptance check (app-asset/mountain integrity → ~1.0).
- **Run 48**: it25 briefs pre-written (C-layeremit 0h+E8, D-shadowideal E2
  with run-43 gates); this consolidated entry.

Segment-2 baselines (v10): recraft_gap full table in worklog run 41;
degsuite in run 46; integrity in run 45. Next: verify/integrate it24
candidates, then it25 dispatch.

## 2026-07-10 · Run 54 — it24 A-transown SHIPPED (E1 transition-ownership)

One rule in the label chain (pipelines/quantize_contours.py `_own_transitions`,
wired pre-lock/despeckle): thin (half-width ≤3) non-ink (lum ≥50) components
whose color lies ON the Lab segment between their two dominant ring labels
(segd ≤4.0, t∈[.12,.88], ablen ≤36 = shading-class edge per Depixelizing's
two-tier idea) absorb into the Lab-nearer bound; stroke-components never
count as bounds (saves rabbit brow strokes). All thresholds population-
measured with margin (drawn slivers segd ≥5.0 / ablen ≥44.2).

Broaden 18/18: 10 byte-identical (all landmines: monster, crystals,
elephant, logos, pizza, shield); 8 changed, every one eye-verified at zoom.
Wins: app-asset (bezel shrapnel + invented white blob GONE, integrity
.412→.988), mountain (SURPRISE win — A's byte-identical claim was wrong
there; stain fragments absorbed, integrity .488→1.000 — always re-check
candidate byte-claims on the integrated build), fox (in-ink pale debris
gone), rabbit (ear spur/tears reduced), chopchop (outline daubs reduced).
Ledger 0l CLOSED. Honest negative banked to BACKLOG: high-contrast
shrapnel subclass not color-separable — geometry signal or E8 next.
Process: interim orchestrator verification (runs 50-53) caught B's
over-straightening AND completed A's checklist mid-flight — candidates got
course corrections while cheap. B (line-intent, stroke layer) still
finalizing; ships separately atop this.

## 2026-07-10 · Run 55 — it24 B-lineintent SHIPPED (E4/E5 line-intent stage 1)

contours_exp.py only. Layer attribution PROVED first (the run-49 question):
monster defects split across fills (corner-pinned fill fit) and CAPSULE
STROKES (the wavy hand hairlines were white _light_line_capsules painted
last — invisible in white-bg layer splits, which is why attribution was
missed historically). Head flat-cut kink was minted by fit_open_parsimony
itself. Mechanism: drawing-intent anchors (25° turn + two-scale
localization; raw-turn-only anchors faceted the dome and were DISCARDED —
the run-49 orchestrator catch), anchor-to-anchor exact chords under tiered
population-measured caps (short/long/corridor), raster-gated G1 repair
(raw-turn ≤20° vs real-kink floor 26.6°), same intent applied to capsule
centerlines. Eye: hand hairlines straight+kinked ≈ recraft (0k hand
CLOSED); teeth crisp zigzag, residual = label lattice (E5, strip-proven);
crystals/mountain straighter; all 5 landmines clear. A+B interaction set
(chopchop/app-asset/mountain/rabbit/fox) eye-verified neutral-to-positive
(mountain ridges + chair struts compound). Culprits filed: mouth-seam
curls = capsule rescue on lip AA (0h); teeth lattice (E5); crystals gap
now dominated by E6/E7. Gauges pixel-quiet (documented thin-line
behavior); main render == B artifact bytes.

**it24 COMPLETE: 2 dispatched, 2 shipped (runs 54-55).** Segment-2 protocol
additions that earned their keep: interim orchestrator verification (caught
B's over-straightening + completed A's checklist mid-flight), objective
side-checks (integrity), candidate byte-claims re-checked on integrated
builds (caught A's wrong mountain claim — in the lucky direction this time).

## 2026-07-10 · Run 63 — it25 C-layeremit SHIPPED (E8+0h); iteration closed by USER budget stop

emit_regions_layered()+_emit_seal() in boundary_split.py, one assembly hunk
in contours_exp. One path per shape, painter's order by descending
footprint (recraft/LIVE), holes dropped (nested content repaints on top —
nested seams sealed for free), sibling seams sealed by w=1.0 lattice-px
underpaint stroke after the lower fill (only the hidden side grows).
Ledger 0h CLOSED: seams 0 on 18/18, hairlines increased nowhere
(game-assets pinholes fixed), degradation gauge IMPROVES on 3 targets,
width landmines byte-identical (the run-61 "reads smaller" was prev's 25%
seam bleed vanishing), monster right eye +28px white toward recraft.
Verification: orchestrator interim (runs 61) + C's 18-target broaden +
byte-equal integrated renders = verdicts transfer. E8's structural half
(per-shape layers) also shipped — VISION item 7 now engine behavior.

**it25 half-closed by USER budget stop:** D-shadowideal handed off as WIP
(census with corrections committed in its worktree; mechanism written,
unplumbed) — resume from worktree agent-aa041c47114afff8f or re-dispatch
with its REPORT. Segment 2 final: runs 41-63, 6 keeps (3 pipeline: A/B/C
= v11+, 2 research/tooling, 1 harness), it24 shipped as v11, it26 brief
ready. Loop OFF (.autoresearch-off) per USER.
