# Autoresearch — image→SVG engine (VISION-FIRST loop)
<!-- Lines 1–15 = SessionStart rehydration window (sed 1,15p): keep objective+focus+best+EYE-gate here. -->
Mission (canonical): **docs/PROJECT_SPEC.md** · Handoff: **docs/RESUME.md** · Work: **docs/BACKLOG.md**

## Objective — rehydrate from here
- ⚠ **KEEP/DISCARD IS BY EYE, NOT THE METRIC** (spec §4): render `tb.crops` and
  look. `quality`/`ssim` are a regression sanity check only — they reward
  copying source noise and penalize the idealization we want.
- GOAL: an *idealized* vector reconstruction (clean confident lines, solid flat
  regions, source noise removed) that **beats OUR LAST VERSION by EYE**, Recraft
  (`data/targets/`) in frame as the north-star. NOT pixel fidelity.
- CURRENT VERSION: **v5 `contour_lines`** (git `3d251ad`); focus **chopchop** (`./autoresearch.focus`).
- BEST-SO-FAR: run 14 A+B — straw/light-accents un-flooded (despeckle guard) + junction pools clamped; r13 wiggle gate + speckle dissolve; v4 defects cleared. 10 keeps / 4 discards.
- ⚠ ITERATIONS ARE WORKTREE-PARALLEL — if `autoresearch.iteration.json` phase≠idle, RESUME that in-flight iteration (see "Worktree-parallel iterations"); the SessionStart hook surfaces it.
- OPEN: thin-light-region beading (fill emitter), chopchop S-wavy strokes/strap curl, rabbit long-gap breaks → docs/BACKLOG.md.

## The metric is NOT the arbiter here (the key adaptation)
The stock autoresearch loop treats a bare number as the keep/discard gate. **This
project explicitly rejects that** (spec §4): our perceptual metric rewards
matching the source raster — i.e. copying JPEG noise and soft shading — so
Recraft itself scores *lower* on it than our worse-looking outputs. Therefore:

- **`./autoresearch.sh` emits `METRIC quality=… ssim=…`** for the plugin's
  dashboard/JSONL format, but it is a **REGRESSION SANITY CHECK ONLY**, run
  *after* an eye verdict has already passed. It never gates a keep.
- The config header sets `targetMetric: null` and `maxSeconds: null` so the Stop
  hook never auto-stops on the number — only `maxRuns` or `/autoresearch off`
  ends the loop. `bestDirection` is nominal; do not chase it.
- **⚠ The ban covers EVERY number, including ones WE derive** — `diffpx`, the
  k-means noise floor, `flecks_absorbed`, points count. These are **spot-finders
  and sanity checks, never verdicts.** A low `diffpx` or a zero change-count
  tells you *where* (or *whether*) code fired — it does NOT tell you a target is
  fine. **You may not declare any target clean from a number; render the grid
  and look.** (Run 12: fox `diffpx` sat at the noise floor while 81 flecks
  fired — only rendering the grid showed the 81 changes were harmless. Calling
  it a "no-op" from the number was the exact mistake this rule exists to stop.)

## How "better" is judged — the vision verdict (THE gate)
For the focus target, render the comparison grid and LOOK:
```python
import sys; sys.path.insert(0, "backend")
from testbed import Testbed
tb = Testbed("elephant.jpg")          # or the current focus basename
new  = tb.svg(...) / your rendered candidate SVG string
prev = <previous version's SVG for this target>
grid = tb.crops({"new": new, "prev": prev, "recraft": tb.target()},
                out="verdict.png", spots=[(y,x), ...])   # 4096-render pixel space
# Then Read outputs/verdict.png and form the verdict by eye.
```
- `new` **keeps** iff it is *clearly better than `prev`* on at least one visual
  axis — wobble, width consistency, junctions, curves, color idealization,
  structural cleanliness, or speed — **with no regression on the others**.
- Recraft is **reference/headroom, not pass/fail**. Not reaching Recraft does
  NOT block a keep (spec §3). Beating our own last version does.
- Put the zoom `spots` on the defect under study (a crossing, a join seam), not
  random locations. Stage caching makes single-knob re-renders take seconds.
- If `tb.target()` is `None` for a target, drop the `recraft` key (don't pass None).

## Testing progression (spec §6) — one focus target, then broaden
Every experiment follows this order; **do not commit before step 4**:
1. **Focus target first.** Make ONE atomic pipeline change. Render `new` vs
   `prev` vs `recraft` on the focus target (`./autoresearch.focus`). Eye-verdict.
   Iterate here until `new` beats `prev` on this single target.
2. **Broaden to all 8 targets — render and LOOK at every target the change can
   touch.** Eye-check that the change generalizes across the style spread
   (characters, gradients, flat-line, logo) **without regressing any**. A win on
   the focus target that regresses another does NOT ship.
   - **You may NOT declare a target clean from a count or a diff number.**
     `diffpx`/`flecks_absorbed`/etc. only pick the crop `spots` (and tell you
     whether the code even fired) — the EYE forms the verdict. Because renders
     are non-deterministic (~8k-px `diffpx` noise floor, see "What's Been
     Tried"), a small `diffpx` can hide real changes (run 12: fox, 81 flecks).
   - **The only no-render skip is a *byte-identical* SVG** (`new == prev` as
     strings — then it truly cannot differ). "Small diff" or "count is zero" is
     NOT identity; render it and look.
3. **Benchmark last (sanity only).** Run `./autoresearch.sh` on the focus target
   (and spot-check others) to catch external regressions in the numbers. A worse
   number after a passed eye verdict is a flag to investigate, not an auto-reject.
4. **Ship** (spec §3): commit (concise msg) → append `docs/RESEARCH_LOG.md` →
   log to `autoresearch.jsonl` + `experiments/worklog.md` → bump `models/vN/` +
   `models/README.md` **iff structural** → update `docs/RESUME.md` + memory.

## Changing the focus target
The focus target is a **mutable field**. When the current defect is fixed and
you move to the next (or broaden), update **`./autoresearch.focus`** (one
basename, e.g. `rabbit`) and the "CURRENT FOCUS TARGET" line above. `ar_eval.py`
and `autoresearch.sh` both read `autoresearch.focus`.

## Files in Scope (the loop may edit these — the SVG pipeline)
- `backend/contours_exp.py` — contour_lines pipeline: `_stroke_elements`,
  `_ribbon`, cap/join style at internal joins, junction handling.
- `backend/strokes.py` — centerline/skeleton, junction-patch/union-find,
  ribbon width, curvature-aware smoothing.
- `backend/pipelines/*.py` — pipeline definitions/registration.
- `backend/boundary.py`, `boundary_split.py`, `refine_shared_v3.py`,
  `postprocess.py`, `idealize.py`, `preprocess.py`, `schneider.py` — supporting
  vectorization stages, when the change is on them.
- Palette/color idealization code when that becomes the focus.

## Off Limits (LOCKED eval harness — spec task H; never edit in the loop)
- **`backend/testbed.py`** — the judging harness (`tb.crops`, `tb.target`,
  `tb.score`, caching). The loop proposes changes to the pipeline, NEVER to how
  its own results get judged.
- **`backend/metrics.py`** — the metric-emitting code.
- **`backend/ar_eval.py`** and **`./autoresearch.sh`** — the sanity harness.
- **`data/targets/*.svg`** — the Recraft north-star references.
- If one genuinely needs a fix, do it as a deliberate, separately-noted
  re-baseline step (worklog + RESEARCH_LOG), never as a routine experiment.

## Worktree-parallel iterations (spec §8.3-4 — the iteration architecture)

An iteration tests several genuinely independent candidate changes **in parallel,
in isolated git worktrees**, then the **orchestrator (never a sub-agent) decides
what ships** — including whether to combine multiple winners into one version.
(The Stop-hook nudge says "one atomic change per experiment" — that is the
*per-candidate* rule; the iteration dispatches N such candidates at once.)

### §1 — Worktree lifecycle (per iteration)
1. **Select N candidates** from docs/BACKLOG.md that touch **genuinely
   independent parts of the pipeline** — different modules/domains (stroke
   extractor vs. quantize/palette vs. fill emitter), not different lines of the
   same function. **N scales to how many independent candidates are actually
   queued — do NOT manufacture parallelism.** N=1 is correct when only one
   independent lead is ready; then this reduces to the classic single-experiment
   flow. Skim recent RESEARCH_LOG discard entries for unfollowed threads worth
   promoting into candidates (§3).
2. **One worktree per candidate, off the current best:**
   `git worktree add .autoresearch-worktrees/<slug> <best-sha>` (best-sha = HEAD
   of the current best commit). Record it in `autoresearch.iteration.json` (§4).
3. **Dispatch one sub-agent per worktree** (Agent tool). Its task, ENTIRELY
   inside its own worktree (no shared mutable state, no editing outside it):
   implement the one change → render `tb.crops` on the focus target from within
   the worktree → form its own eye verdict → report back the crop path, verdict,
   and observations. **Its self-report is a CLAIM, not a verified result.**
4. **Orchestrator independently re-verifies — uniformly, no exceptions.** When a
   sub-agent reports, the orchestrator itself re-renders `tb.crops` for that
   worktree's output (run the pipeline with that worktree's `backend/` on the
   path — e.g. `cd .autoresearch-worktrees/<slug>` and render) and forms its own
   eye verdict before the candidate counts as a winner. A confident-sounding
   sub-agent report changes nothing about this.
5. **Clean up:** `git worktree remove .autoresearch-worktrees/<slug>` (add
   `--force` if it holds uncommitted probe files) once the result is logged —
   whether kept, discarded, or merged. No worktree survives its iteration.

### §2 — Orchestrator-owned integration (the orchestrator decides what ships)
- **Exactly one candidate independently verifies** (beats best, no regression on
  the focus target) → it is the new candidate version → go to the existing
  **broaden-to-all-8-targets** step (Testing progression §2) before shipping.
- **Multiple candidates each independently verify** → the orchestrator **combines
  them itself**: a fresh integration worktree off the current best
  (`.autoresearch-worktrees/_integrate`), apply each verified change **one at a
  time**, re-render + re-verify by eye **after each apply — not only after the
  final combination.** Two independently-good changes can interact badly in the
  *rendered output* even when the *code* merges cleanly, so the combination is
  its own experiment, never assumed safe from the parts.
- **A merge step regresses** → isolate which change caused it (bisect by
  re-testing combinations), **ship the subset that holds up**, and log the
  interaction as its own discard entry naming the combination (§3). Do NOT
  discard everything just because the full combination failed.
- Only after the (possibly combined) result **broadens cleanly across all 8
  targets** does it get committed and shipped (Versioning, spec §5). Update
  `autoresearch.iteration.json` phase at every transition (§4).

### §3 — Rich discard logging (every worktree, every outcome)
For **every** candidate — ships alone, ships in a combination, or discarded —
append a docs/RESEARCH_LOG.md entry (format is specified in that file's header).
It must contain: what was actually tried; what the `tb.crops` grid showed
**including anything unrelated or disproportionate to the change** (unexpectedly
clean regions, odd side effects); the verdict and its real reason; and **if
discarded, a lead-grade note** (which target, which spot, which parameter, what
it looked like) — pickable-up later, never just "interesting, investigate."
**If discarded because it broke when combined**, name the combination so that
interaction is not retried blind. This is not optional book-keeping — the discard
log is where the next iteration's candidates come from.

### §4 — In-flight state: `autoresearch.iteration.json` (rehydration-safe)
Mutable per-iteration state the append-only `autoresearch.jsonl` cannot hold.
**Rewrite it at every lifecycle transition** (dispatch → verify → integrate →
broaden → idle) so a `/clear`, resume, or compaction picks up mid-iteration.
Schema:
```json
{"iteration": 12, "phase": "dispatched|verifying|integrating|broadening|idle",
 "focus": "chopchop", "best_sha": "50c0a03", "updated": "<YYYY-MM-DD HH:MM>",
 "candidates": [
   {"id": "fleck-recolor", "domain": "stroke-extractor (contours_exp.py)",
    "worktree": ".autoresearch-worktrees/fleck-recolor", "backlog": "brown flecks",
    "subagent_verdict": "beats prev|worse|mixed",
    "orchestrator_verdict": "VERIFIED|REFUTED|PENDING", "crop": "outputs/..png"}],
 "integration": {"order": ["a","b"], "applied": ["a"], "step": 1,
                 "last_verified_ok": true, "worktree": ".autoresearch-worktrees/_integrate"}}
```
Set `phase:"idle"` (or delete the file) when the iteration fully ships/aborts.
The project hook `.claude/hooks/autoresearch-iteration-state.sh` (registered in
`.claude/settings.json` for SessionStart + PreCompact) surfaces this on resume
and snapshots it before compaction — so a rehydrated session is told "you were
mid-merge across worktrees, phase X, re-verify PENDING candidates yourself,"
not just "you were mid single-experiment." On resume, reconcile the recorded
worktrees against `git worktree list` before continuing.

## Versioning & deliverables (spec §5 — task F)
- One git commit per accepted improvement (concise message).
- `models/vN/` bumped **only on structural changes**, not every tweak; update
  `models/README.md` on every bump (each version vs previous vs Recraft).
- Deliverables are written by the harness to
  `data/outputs/{name}-{gitsha}-{timestamp}.svg` (gitignored) so any SVG traces
  to the exact engine that made it.

## How to Run
`./autoresearch.sh [FOCUS_BASENAME] [SEED]` — renders the current `contour_lines`
output for the focus target, writes the deliverable, prints `METRIC` lines
(sanity only). Reproducible (fixed seed). ~2–8 s on the elephant thanks to the
cached testbed.

Full-engine repro (env prefix mandatory — native renderer + Rust svgcore):
```bash
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -c "
import sys; sys.path.insert(0,'backend')
from pipelines import get_pipeline; from testbed import Testbed; from svgutil import fit_svg_size
tb=Testbed('elephant.jpg'); pp,_,(ow,oh),_=tb.prep()
open('out.svg','w').write(fit_svg_size(get_pipeline('contour_lines').run(pp,{}),ow,oh))"
```

## Constraints
- Judge by eye first, always; keep Recraft in every comparison; record negative
  results (worklog + RESEARCH_LOG) too.
- One atomic change per experiment (so the worklog is a clean ablation).
- Every run: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` + `.venv/bin/python`,
  absolute paths, `if __name__=='__main__'` guard for any pool-using script
  (macOS spawn).
- Keep docs current so any session resumes cold from docs/RESUME.md.

## Context management between iterations (task I — READ THIS)
The plugin's Stop hook keeps the loop going **in one long context**; it CANNOT
trigger `/clear` (Claude Code hooks cannot invoke slash commands — verified).
So per-iteration context is managed by:
- **Nothing durable lives in-conversation** — all state is on disk
  (`autoresearch.jsonl`, `autoresearch.iteration.json` for in-flight worktree
  state, `experiments/worklog.md`, `docs/RESEARCH_LOG.md`, `docs/RESUME.md`,
  `autoresearch.focus`, git worktrees). A clear/compaction loses nothing.
- **PreCompact hooks** snapshot state before auto-compaction — the plugin's
  snapshots `autoresearch.jsonl`; the project hook snapshots
  `autoresearch.iteration.json`.
- **SessionStart hooks** (matcher includes `clear`) rehydrate on
  startup/resume/compact/clear: the plugin's injects objective + focus +
  best-so-far (top of THIS file + worklog); the **project hook**
  (`.claude/hooks/autoresearch-iteration-state.sh`) injects any MID-ITERATION
  worktree/merge state so an interrupted parallel iteration resumes correctly.
- To get a genuinely clean context per iteration you (or the user) run `/clear`
  manually, or run each iteration headless (`claude -p`) from an external loop —
  see docs/RESUME.md "Loop operating model". This must be a deliberate choice;
  it is NOT automatic.

## Idea source
The single ranked idea queue is **docs/BACKLOG.md** (there is no
`autoresearch.ideas.md` — ignore the plugin's default mention of it). Pick the
next experiment from BACKLOG's top; append newly discovered ideas back to it.

## What's Been Tried
Seeded from v1→v4 history (see models/README.md + docs/RESEARCH_LOG.md for the
full journal). Update this section every 5–10 experiments with wins, dead ends,
and a meta-review of which *classes* of change win vs lose.
- v3→v4: `contour_lines` (width-constant centerline strokes + parsimony-fitted
  flat shading) reached Recraft's tier on the elephant by eye. Resolved the
  three original defects (wobble, width thinning, shadows-over-lines).
- Run 2 (c0adad6): junction ends anchor to nearest other-branch centerline
  (0.8w) — T-nubs/Y-pinches fixed. Lesson: 1.5w radius snapped parallel
  neighbors (chopchop) — keep snap radii under ~0.8w near dense lines.
- Run 3 (2570c63): free ends bridge across label components (1.2w, fwd<60°,
  midpoint end-to-end) — rabbit dash-gaps closed. Lesson: direction gate is
  what keeps parallel lines safe, not the radius alone.
- Run 4 (5eb37ad): still-free ends walk the source-ink ridge (≤4w). Lesson:
  UNGUARDED walkers roam dark fills (curls on chopchop) — the perpendicular
  ridge test + ~120° cumulative turn cap are mandatory for any ink tracer.
- Metric lesson: composite `quality` swings ±1% on tiny geometry changes with
  flat ssim/ms-ssim — never steer by it; sub-metrics + eye only.
- Run 12 (4c616ce): adjacency fleck absorption (first worktree-parallel
  iteration; candidate A shipped, B refuted by orchestrator). **Process lesson —
  the mistake to never repeat:** during broaden I first called fox + elephant
  "no-op within noise" from `flecks_absorbed`/`diffpx` *without rendering them*.
  Fox had 81 flecks fire *under* the ~8k `diffpx` noise floor — not a no-op at
  all. Rule now enforced above: never infer a target is fine from a number
  (even our own noise-floor number); render new-vs-prev and eye-check every
  touched target; the only no-render skip is a byte-identical SVG.
- Render nondeterminism: same code → ~8k-px `diffpx` self-diff (cv2 k-means not
  seed-stable across processes). `diffpx` is a spot-finder, never a verdict.
