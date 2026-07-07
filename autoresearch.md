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
- CURRENT VERSION: **v4 + runs 2–4** (git `5eb37ad`).
- CURRENT FOCUS TARGET: **rabbit** (source of truth: `./autoresearch.focus`).
- BEST-SO-FAR (run 4): line network near-continuous (junction anchoring +
  cross-component bridging + source-ink extension), 8/8 by eye.
- OPEN DEFECTS (ranked): true source gaps (light-pixel jump) → curvature
  drift → junction ink pooling → palette idealization. See docs/BACKLOG.md.

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
2. **Broaden to all 8 targets.** Render each and eye-check that the change
   generalizes across the style spread (characters, gradients, flat-line, logo)
   **without regressing any**. A win on the focus target that regresses another
   target does NOT ship.
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

## Sub-agent parallelism (spec §8.3-4; file-ownership map — task G)
Prototype experiments may run in parallel sub-agents, but with **strict file
ownership so they never collide**:
- Give each sub-agent **exactly one** in-scope file (or one disjoint set) to
  edit — e.g. agent A owns `strokes.py`, agent B owns `contours_exp.py`. No two
  agents write the same file in the same round.
- **Shared, read-only for all agents:** `backend/testbed.py`, `metrics.py`,
  `data/`, `docs/`. Each agent renders into its **own** `outputs/<agent>-*.png`
  crop file (unique name) so grids don't overwrite each other.
- Each sub-agent judges its own result by eye and reports the verdict + the crop
  path. **The orchestrator MUST independently re-render the claimed result and
  look at the grid itself before trusting it (spec §8.4).** Self-report is not
  sufficient to ship — a sub-agent claiming "beats prev" is a hypothesis until
  the orchestrator sees it.
- Only the orchestrator integrates a winner into the real pipeline and commits.

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
  (`autoresearch.jsonl`, `experiments/worklog.md`, `docs/RESEARCH_LOG.md`,
  `docs/RESUME.md`, `autoresearch.focus`, git). A clear/compaction loses nothing.
- **PreCompact hook** snapshots state before auto-compaction.
- **SessionStart hook** (matcher now includes `clear`) rehydrates objective +
  focus target + best-so-far from the top of THIS file + the worklog on
  startup/resume/compact/clear.
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
