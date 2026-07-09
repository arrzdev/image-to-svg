# Autoresearch — image→SVG engine (VISION-FIRST loop)
<!-- RESTRUCTURED 2026-07-07: engine folders = models/vN/src (was backend/); state/docs = research/.
     2026-07-09: milestones backfilled v6/v7/v8; LIVE tree is now models/v9/src (v5-v7 frozen).
     Root SYMLINKS (autoresearch.{md,jsonl,focus,sh}, experiments->research) keep the
     plugin hooks working — do not remove them. -->
<!-- Lines 1–15 = SessionStart rehydration window (sed 1,15p): keep objective+focus+best+EYE-gate here. -->
Mission: **research/docs/PROJECT_SPEC.md** · Work: **research/docs/BACKLOG.md** · Trigger: `/autoresearch <objective>` — $ARGUMENTS states the current objective (this file + spec carry detail; empty args = objective below). If `research/autoresearch.iteration.json` phase≠idle: execute its **next_action** field.

## Objective — rehydrate from here
- ⚠ **KEEP/DISCARD IS BY EYE, NOT THE METRIC** (spec §4): render `tb.crops` and
  look. `quality`/`ssim` are a regression sanity check only — they reward
  copying source noise and penalize the idealization we want.
- GOAL (USER framing 2026-07-08): **REACH Recraft's state FIRST, then surpass it.**
  Work the defect scoreboard `research/docs/GAP_LEDGER.md` — close items with
  before/after grids. chopchop is THE benchmark target. Idealized vector look
  (clean confident lines, flat regions, noise removed), NOT pixel fidelity.
- CURRENT VERSION: **v8 `contour_lines`** (git `5d1a9d6`, live tree = `models/v9/src`; v5–v7 frozen milestones); focus **chopchop** (`./research/autoresearch.focus`). Segment 1 live (2/30).
- Numeric direction gauge: `research/tools/recraft_gap.py [target] --spots` (ours-vs-RECRAFT render rSSIM/rΔE + worst tiles → mandatory eye-spots). Spot-finder + per-keep secondary; NEVER the gate.
- ⚠ CULPRIT PROTOCOL: every eye verdict that sees ours < recraft must PAUSE and name (a) the concrete defect, (b) the suspected pipeline stage (staged-diagnosis strips when unsure), (c) ledger/BACKLOG entry. See "How better is judged".
- BEST-SO-FAR: it21 runs 34-35 — color-guarded joining (USER idea; over-join welds gone, ledger #5) + junction cusp descent (heart notch FULL depth, #4) + straight-chain lock (pizza verticals straight, #2 CLOSED). Atop segment-0 wins (tangles, ZZA, thin-line lock, teeth). Gauge: chopchop .871, elephant .981.
- ⚠ ITERATIONS ARE WORKTREE-PARALLEL — if `research/autoresearch.iteration.json` phase≠idle, RESUME that in-flight iteration (see "Worktree-parallel iterations"); the SessionStart hook surfaces it.
- ⚠ ITERATION LIFECYCLE (USER mandate 2026-07-09, see "Iteration lifecycle"): research→test→validate→document→version-if-better→/clear→continue. `models/staged` symlinks the live tree so the USER can test in-flight work (`run_model.py -m staged`).
- OPEN (it22 queue): #6 small-detail fitter dual (buttons hooks + fox dash chain); NEW pizza upper-band cell separators lost (label chain, eye-loud); #7 refined re-tint (eroded masks, skip ink); crystals hue drift; pizza crossing nubs → GAP_LEDGER.md.

## The metric is NOT the arbiter here (the key adaptation)
The stock autoresearch loop treats a bare number as the keep/discard gate. **This
project explicitly rejects that** (spec §4): our perceptual metric rewards
matching the source raster — i.e. copying JPEG noise and soft shading — so
Recraft itself scores *lower* on it than our worse-looking outputs. Therefore:

- **`./research/autoresearch.sh` emits `METRIC quality=… ssim=…`** for the plugin's
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
import sys; sys.path.insert(0, "models/v9/src")
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

### ⚠ Culprit protocol (USER mandate 2026-07-08) — the pause behind every verdict
Verdicting "better/worse/lateral" is NOT enough. **Whenever a grid shows ours
worse than Recraft — even in a crop you rendered for a different reason — STOP
and think for a moment about WHY, then write it down:**
1. **Name the defect concretely** ("the PIZZA 'ZZ' strokes break and warp",
   "heart notch shallower", "frond/trunk junction is a tangled double-stroke
   knot") — never just "worse" or "messy".
2. **Name the suspected culprit stage** — pre-blur / quantize / palette merge /
   despeckle-smooth (label cleanup) / stroke extraction / bridging-joining /
   centerline+fill FIT / emission. If unsure, run a **staged-diagnosis strip**
   (dump the artifact at each stage exactly like diag20_heart_stages.png — the
   run-25 pattern: it found despeckle guilty when everyone suspected the
   fitter). The smoking gun is usually one stage; find it, don't guess.
3. **Record it** in `research/docs/GAP_LEDGER.md` (new item or evidence on an
   existing one) so the defect enters the priority queue with its diagnosis
   attached. An eye-pass that produces only verdicts and no culprits on visible
   gaps is an incomplete pass.
This is how "reach Recraft first" becomes mechanism: the ledger accumulates
root-caused, ranked gaps; iterations close them with evidence.

### recraft_gap — the numeric direction gauge (alongside, never instead)
`research/tools/recraft_gap.py [targets] --spots` renders ours vs RECRAFT'S SVG
(render-to-render, never vs original pixels — that rewards noise-copying) and
reports rSSIM + rΔE + the worst 4×4 tiles, `--spots` emitting them as
`tb.crops` (y,x)@4096 coordinates. Standing usage:
- **Per keep**: record `rssim_<focus>` (+ rΔE if color-relevant) in the jsonl
  `metrics` and re-run the full-table occasionally; a falling rSSIM on an
  UNTOUCHED target is a spot-finder alarm.
- **Per verification**: the worst tiles of the touched target(s) are MANDATORY
  eye-spots in the crop grid, in addition to the defect-under-study spots.
- Thin-line changes are pixel-quiet (run 25 measured: eye-loud wins moved rSSIM
  <0.001) — a flat number NEVER means "no visual change", and a number never
  gates a keep. Direction gauge + tile-ranker only.

## Testing progression (spec §6) — one focus target, then broaden
Every experiment follows this order; **do not commit before step 4**:
1. **Focus target first.** Make ONE atomic pipeline change. Render `new` vs
   `prev` vs `recraft` on the focus target (`./research/autoresearch.focus`). Eye-verdict
   — including the recraft_gap worst-tile spots and the CULPRIT pause on any
   ours-vs-recraft gap seen ("How better is judged"). Iterate here until `new`
   beats `prev` on this single target.
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
3. **FULL-COVERAGE eye pass — MANDATORY before any keep/ship decision.**
   Focused `spots=[...]` crops are for diagnosing a specific defect; they are
   NEVER sufficient to declare "verified, no regression". Before shipping (and
   for the focus target before calling a candidate verified), render
   `tb.full_grid({'new':…,'prev':…,'recraft':…}, out=…)` — it tiles the ENTIRE
   image into blocks and emits ORIGINAL | new | prev | recraft pages for every
   block — and LOOK at every page. This is what spec §4's "no regression on
   the others" actually requires. Focused mode stays for investigation;
   full-coverage is the final gate on top of it.
4. **Benchmark last (sanity only).** Run `./research/autoresearch.sh` on the focus target
   (and spot-check others) to catch external regressions in the numbers. A worse
   number after a passed eye verdict is a flag to investigate, not an auto-reject.
5. **Ship** (spec §3): commit (concise msg) → append `research/docs/RESEARCH_LOG.md` →
   log to `research/autoresearch.jsonl` + `research/worklog.md` → bump `models/vN/` +
   `models/README.md` **iff structural** → update `research/docs/RESUME.md` + memory.

## Changing the focus target
The focus target is a **mutable field**. When the current defect is fixed and
you move to the next (or broaden), update **`./research/autoresearch.focus`** (one
basename, e.g. `rabbit`) and the "CURRENT FOCUS TARGET" line above. `ar_eval.py`
and `autoresearch.sh` both read `autoresearch.focus`.

## Files in Scope (the loop may edit these — the SVG pipeline)
- `models/v9/src/contours_exp.py` — contour_lines pipeline: `_stroke_elements`,
  `_ribbon`, cap/join style at internal joins, junction handling.
- `models/v9/src/strokes.py` — centerline/skeleton, junction-patch/union-find,
  ribbon width, curvature-aware smoothing.
- `models/v9/src/pipelines/*.py` — pipeline definitions/registration.
- `models/v9/src/boundary.py`, `boundary_split.py`, `refine_shared_v3.py`,
  `postprocess.py`, `idealize.py`, `preprocess.py`, `schneider.py` — supporting
  vectorization stages, when the change is on them.
- Palette/color idealization code when that becomes the focus.

## Off Limits (LOCKED eval harness — spec task H; never edit in the loop)
- **`models/v9/src/testbed.py`** — the judging harness (`tb.crops`, `tb.target`,
  `tb.score`, caching). The loop proposes changes to the pipeline, NEVER to how
  its own results get judged.
- **`models/v9/src/metrics.py`** — the metric-emitting code.
- **`models/v9/src/ar_eval.py`** and **`./research/autoresearch.sh`** — the sanity harness.
- **`data/targets/*.svg`** — the Recraft north-star references.
- If one genuinely needs a fix, do it as a deliberate, separately-noted
  re-baseline step (worklog + RESEARCH_LOG), never as a routine experiment.

## Iteration lifecycle (USER mandate 2026-07-09 — follow EXACTLY, every iteration)
1. **Research if needed** — mine `research/docs/VECTORIZATION_PAPERS.md`
   (USER-compiled) + web for the defect class before inventing; note what was
   consulted.
2. **Test things** — candidates per the worktree protocol below (or inline
   when agents are unavailable/the change is small).
3. **Validate the tests** — orchestrator re-verification by EYE from
   artifacts. ⚠ HARDENED after the run-37 monster-mouth miss (agent labeled a
   focus-target regression "lateral"; orchestrator only re-eyed hero+claimed
   spots; USER caught it): the orchestrator must ALWAYS re-eye, minimum, (a)
   the FOCUS target full-grid, (b) every target the USER has ever flagged
   (monster mouth, rabbit heart/hand, chopchop, pizza straights, app-asset),
   (c) the candidate's claimed wins AND claimed laterals on those targets.
   A sub-agent "lateral" on a user-flagged target is a claim like any other.
4. **Document** — what was tested, what improved, what didn't, negative
   results: RESEARCH_LOG + worklog + jsonl + dashboard + GAP_LEDGER, every
   iteration, before anything else ends.
5. **Version if better** — a structural milestone ships as a new
   `models/vN/` (git archive snapshot + entry.py + examples via
   `run_model.py` + MANIFEST + README matrices) and the loop repoints to it;
   `models/staged` symlink ALWAYS points at the live tree (repoint on bump:
   `ln -sfn v<N> models/staged`) so the USER can test work-in-progress and
   give feedback mid-loop.
6. **Run /clear and keep going** — after ALL state is on disk (step 4/5 +
   iteration.json next_action rewritten), the iteration boundary is the
   /clear point: context resets, the SessionStart hook + iteration.json
   rehydrate, the loop continues fresh. Never carry a stale context across
   iterations; never stop the loop at a boundary — clear and continue.
   (The orchestrator cannot invoke the CLI /clear itself; it MUST end the
   close-out turn with state fully disk-rehydratable and mark
   "ITERATION BOUNDARY — safe to /clear" in next_action, so a clear at any
   moment loses nothing.)

## Worktree-parallel iterations (spec §8.3-4 — the iteration architecture)

An iteration tests several genuinely independent candidate changes **in parallel,
in isolated git worktrees**, then the **orchestrator (never a sub-agent) decides
what ships** — including whether to combine multiple winners into one version.
(The Stop-hook nudge says "one atomic change per experiment" — that is the
*per-candidate* rule; the iteration dispatches N such candidates at once.)

### §1 — Worktree lifecycle (per iteration)
1. **Select N candidates** from research/docs/BACKLOG.md that touch **genuinely
   independent parts of the pipeline** — different modules/domains (stroke
   extractor vs. quantize/palette vs. fill emitter), not different lines of the
   same function. **N scales to how many independent candidates are actually
   queued — do NOT manufacture parallelism.** N=1 is correct when only one
   independent lead is ready; then this reduces to the classic single-experiment
   flow. Skim recent RESEARCH_LOG discard entries for unfollowed threads worth
   promoting into candidates (§3).
2. **Dispatch one sub-agent per candidate with NATIVE worktree isolation** —
   `Agent(isolation: "worktree", run_in_background: true, ...)`. The framework
   creates the worktree copy of the repo and auto-cleans it if unchanged; do
   NOT run manual `git worktree add`/`remove` for candidates. HEAD must be the
   current best commit when dispatching (it always is under the
   commit-per-keep convention). Record the candidate in
   `research/autoresearch.iteration.json` (§4) at dispatch; fill in its
   worktree path from the sub-agent's report.
3. **The delegation prompt is the sub-agent's ONLY channel — nothing else
   crosses automatically.** Every dispatch prompt must explicitly contain:
   - instruction to FIRST read `research/docs/PROJECT_SPEC.md` and
     `research/autoresearch.md` (in its own worktree copy);
   - the specific objective for THIS candidate (defect, diagnosis so far,
     acceptance criterion in eye terms);
   - the scope boundary — exactly which files/module under `models/v9/src/`
     it may touch, and the locked-harness list it may NOT;
   - the focus target and the `data/inputs/` / `data/targets/` paths;
   - exactly how to render and judge: env prefix
     `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`, the repo venv python,
     `sys.path.insert(0,'models/v9/src')`, render baseline-then-new,
     `tb.crops({'new','prev','recraft'})`, LOOK at the png;
   - the ABSOLUTE shared artifact dir `<repo>/research/it<N>/candidates/<id>/`
     (in the MAIN repo — the one path a sub-agent may write outside its
     worktree): write the final `new.svg`, the baseline `prev.svg`, and any
     key intermediates there;
   - the CULPRIT PROTOCOL instruction (see "How better is judged"): any grid
     where ours < recraft must yield named-defect + suspected-stage notes
     (staged-diagnosis strip when unsure), reported back for the ledger;
   - recraft_gap usage where the target has a Recraft reference: run
     `research/tools/recraft_gap.py <target> --spots`, include the worst
     tiles as eye-spots, report before/after rSSIM/rΔE (secondary signal —
     the eye stays the gate);
   - the report format: files changed + mechanism, the artifact dir path,
     crop paths, eye verdict (labelled as a claim), side observations,
     culprit notes for the GAP_LEDGER, lead-grade notes, **and its worktree
     path (`pwd`)**.
4. **Model & effort policy (every dispatch, no exceptions):**
   - **Model: never set explicitly.** Leave it to inherit so sub-agents always
     run whatever model the orchestrator session is on.
   - **Effort: a deliberate choice every time, recorded in the candidate's
     iteration.json entry** (`"effort"` field). A candidate MAY run at lower
     effort than the orchestrator when the task doesn't need full depth
     (mechanical renders, parameter sweeps); it must NEVER run at an effort
     level above the orchestrator's own. Where the dispatch mechanism has no
     effort knob, inherit (= orchestrator level, satisfying the cap) and
     record `"effort": "inherit"` — the point is that the choice is written
     down, not silent.
5. **Wait natively.** After dispatching background sub-agents, do NOT poll
   their worktrees/output files in wait loops — the framework delivers a
   completion notification per agent. Use the wait to do orchestrator-side
   prep (baseline renders on the main tree) or simply end the turn.
6. **Orchestrator independently re-verifies — uniformly, no exceptions.** The
   orchestrator reads the candidate's `new.svg` from the shared artifact dir
   and renders ITS OWN comparison grids from it — focused crops on the defect
   AND the full-coverage grid (`tb.full_grid`) — before any verdict. **A grid
   image the sub-agent rendered is never the verdict source** (that would be
   trusting self-report one layer removed); artifacts save re-running the
   generation pipeline, not the independent comparison render. When in doubt
   that the SVG matches the code (or the artifact is missing), re-run the
   pipeline from the candidate's worktree as a spot-check. A
   confident-sounding sub-agent report changes nothing about this.
7. **Clean up:** the framework auto-removes an unchanged worktree; a worktree
   the candidate modified persists for orchestrator verification — after the
   result is logged (kept, discarded, or merged), remove it
   (`git worktree remove --force <path>`). No worktree survives its
   iteration. Always use ABSOLUTE paths for worktree operations (a stale cwd
   once created a nested worktree — run 14).

### §2 — Orchestrator-owned integration (the orchestrator decides what ships)
- **Exactly one candidate independently verifies** (beats best, no regression on
  the focus target) → it is the new candidate version → go to the existing
  **broaden-to-all-8-targets** step (Testing progression §2) before shipping.
- **Multiple candidates each independently verify** → the orchestrator **combines
  them itself** in a fresh integration worktree off the current best (this is
  the orchestrator's own workspace — create it with the native EnterWorktree
  tool when available, else `git worktree add --detach <ABSOLUTE path> HEAD`),
  apply each verified change **one at a
  time**, re-render + re-verify by eye **after each apply — not only after the
  final combination.** Two independently-good changes can interact badly in the
  *rendered output* even when the *code* merges cleanly, so the combination is
  its own experiment, never assumed safe from the parts. When candidates touch
  the same file (different functions), integrate via `git diff`/`apply` of each
  candidate's changes, not whole-file copies.
- **A merge step regresses** → isolate which change caused it (bisect by
  re-testing combinations), **ship the subset that holds up**, and log the
  interaction as its own discard entry naming the combination (§3). Do NOT
  discard everything just because the full combination failed.
- Only after the (possibly combined) result **broadens cleanly across ALL
  targets in data/inputs/** does it get committed and shipped (Versioning,
  spec §5). Broadening may render live per target through the stable entry —
  `python3 run_model.py -m v5 -i data/inputs/<t>` (or the testbed inside the
  integration worktree for cached zoom grids); either way the verdict is the
  EYE on the grid, per Testing progression §2. Update
  `research/autoresearch.iteration.json` phase **and `next_action`** at every
  transition (§4).

### §3 — Rich discard logging (every worktree, every outcome)
For **every** candidate — ships alone, ships in a combination, or discarded —
append a research/docs/RESEARCH_LOG.md entry (format is specified in that file's header).
It must contain: what was actually tried; what the `tb.crops` grid showed
**including anything unrelated or disproportionate to the change** (unexpectedly
clean regions, odd side effects); the verdict and its real reason; and **if
discarded, a lead-grade note** (which target, which spot, which parameter, what
it looked like) — pickable-up later, never just "interesting, investigate."
**If discarded because it broke when combined**, name the combination so that
interaction is not retried blind. This is not optional book-keeping — the discard
log is where the next iteration's candidates come from.

### §4 — In-flight state: `research/autoresearch.iteration.json` (rehydration-safe)
Mutable per-iteration state the append-only `research/autoresearch.jsonl` cannot hold.
**Rewrite it at every SUB-BOUNDARY, not just phase changes**: at dispatch, after
EACH candidate's independent verification completes, after EACH merge step in a
multi-winner integration, after each broaden batch, and at ship/abort. Each
sub-boundary is a valid `/clear` point — the loop must never depend on
in-context memory to know its next step. (Hooks cannot invoke `/clear`
themselves — verified limitation — so the contract is: the state on disk is
always `/clear`-ready; the user or an external runner may clear at any
sub-boundary and the next session continues losslessly.)
Schema:
```json
{"iteration": 12, "phase": "dispatched|verifying|integrating|broadening|idle",
 "focus": "chopchop", "best_sha": "50c0a03", "updated": "<YYYY-MM-DD HH:MM>",
 "next_action": "LITERAL next step, e.g. 'verify candidate B-longgap in its worktree at <abs path>: re-render tb.crops spots [(y,x),...] and eye-judge' or 'broaden shipped AB to remaining targets: mountain, rabbit, fox (live: python3 run_model.py -m v5 -i data/inputs/<t>)'",
 "candidates": [
   {"id": "fleck-recolor", "domain": "stroke-extractor (models/v9/src/contours_exp.py)",
    "worktree": "<abs path reported by the sub-agent (native isolation)>",
    "backlog": "brown flecks", "effort": "inherit|low (deliberate, ≤ orchestrator)",
    "artifacts": "research/it<N>/candidates/<id>/",
    "subagent_verdict": "beats prev|worse|mixed",
    "orchestrator_verdict": "VERIFIED|REFUTED|PENDING", "crop": "outputs/..png"}],
 "integration": {"order": ["a","b"], "applied": ["a"], "step": 1,
                 "last_verified_ok": true, "worktree": "<abs path>"}}
```
**`next_action` is MANDATORY at every write** — the literal next step, specific
enough that a fresh session executes it without re-deriving anything. If a
rehydrated session cannot state its next action from this file alone, that is
a schema gap: fix the writer, not the reader.
Set `phase:"idle"` (or delete the file) when the iteration fully ships/aborts.
The project hook `.claude/hooks/autoresearch-iteration-state.sh` (registered in
`.claude/settings.json` for SessionStart + PreCompact) surfaces this on resume —
`next_action` FIRST — and snapshots it before compaction, so a rehydrated
session is told exactly where it was, not just "you were mid-experiment." On
resume, reconcile the recorded worktrees against `git worktree list` before
continuing.

## Versioning & deliverables (spec §5 — task F)
- One git commit per accepted improvement (concise message).
- `models/vN/` bumped **only on structural changes**, not every tweak; update
  `models/README.md` on every bump (each version vs previous vs Recraft).
- Deliverables are written by the harness to
  `data/outputs/{name}-{gitsha}-{timestamp}.svg` (gitignored) so any SVG traces
  to the exact engine that made it.

## How to Run
`./research/autoresearch.sh [FOCUS_BASENAME] [SEED]` — renders the current `contour_lines`
output for the focus target, writes the deliverable, prints `METRIC` lines
(sanity only). Reproducible (fixed seed). ~2–8 s on the elephant thanks to the
cached testbed.

Full-engine repro (env prefix mandatory — native renderer + Rust svgcore):
```bash
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -c "
import sys; sys.path.insert(0,'models/v9/src')
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
- Keep docs current so any session resumes cold from research/docs/RESUME.md.

## Context management between iterations (task I — READ THIS)
The plugin's Stop hook keeps the loop going **in one long context**; it CANNOT
trigger `/clear` (Claude Code hooks cannot invoke slash commands — verified).
So per-iteration context is managed by:
- **Nothing durable lives in-conversation** — all state is on disk
  (`research/autoresearch.jsonl`, `research/autoresearch.iteration.json` for in-flight worktree
  state, `research/worklog.md`, `research/docs/RESEARCH_LOG.md`, `research/docs/RESUME.md`,
  `autoresearch.focus`, git worktrees). A clear/compaction loses nothing.
- **PreCompact hooks** snapshot state before auto-compaction — the plugin's
  snapshots `research/autoresearch.jsonl`; the project hook snapshots
  `research/autoresearch.iteration.json`.
- **SessionStart hooks** (matcher includes `clear`) rehydrate on
  startup/resume/compact/clear: the plugin's injects objective + focus +
  best-so-far (top of THIS file + worklog); the **project hook**
  (`.claude/hooks/autoresearch-iteration-state.sh`) injects any MID-ITERATION
  worktree/merge state so an interrupted parallel iteration resumes correctly.
- To get a genuinely clean context per iteration you (or the user) run `/clear`
  manually, or run each iteration headless (`claude -p`) from an external loop —
  see research/docs/RESUME.md "Loop operating model". This must be a deliberate choice;
  it is NOT automatic.

## Idea source
The single ranked idea queue is **research/docs/BACKLOG.md** (there is no
`autoresearch.ideas.md` — ignore the plugin's default mention of it). Pick the
next experiment from BACKLOG's top; append newly discovered ideas back to it.

## What's Been Tried

### Segment-0 meta-review (runs 12-30, 2026-07-08)
WINS: measure-first staged diagnosis (stage strips + instrumentation found the
real culprit 4/4 times); population-measured gates with margins; label-chain
guards + fit priors as one family. LOSES: tuning the fit when the defect is
upstream; naive single thresholds. Runs 25-29 (inline): thin-dark-line lock,
two-tier chroma gate (ZZA + junction tangles), chord-straight emit,
fill straight-piece prior — user ledger items #1 #2 #3 closed/mostly.
Gauge at close: chopchop .871, elephant .981, rabbit color gap dE 4.16 open.
Seeded from v1→v4 history (see models/README.md + research/docs/RESEARCH_LOG.md for the
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
  CLOSED run 18 (da5d4b6): root cause was the `medial_axis` tie-order, not
  k-means; an rng-pin made chopchop renders byte-identical. Pin determinism
  BEFORE chasing a "noisy" eye-diff — the noise was our own tie-break.

### Meta-review, runs 13–22 (iterations 13–18, all worktree-parallel)
Which *classes* of change win vs lose, distilled to steer candidate picks:

- **The label chain (`quantize_contours.py` despeckle/smooth) is the dominant
  defect source, not the fitter.** Run after run, the visible damage traced to
  despeckle/smooth eroding a THIN BOUNDARY SUBFEATURE of a large region before
  the fitter ever sees it: monster light scratches beaded (r15), straw stripes
  flooded (r14), monster teeth spikes severed (r22). The run-14 light-accent
  guard protects whole COMPONENTS; the recurring miss is SUBPARTS of a big
  region's boundary. **This is a family, and it has a proven cure shape:**
  source-anchored rescue + contrast-extremal gate + clean weld corridor
  (r15 capsules for light lines, r22 spike-tips for light spikes). it19-A
  extends it to the DARK dual (buttons/heart). When a defect looks like "a
  thin drawn detail went missing/lumpy," suspect the label chain FIRST and
  reach for the rescue+weld shape.
- **Corner geometry must be pinned BEFORE fitting, never tuned into alphamax**
  (r10 stroke serrations, r21 fill V-notches). Detect corners on the raw
  polyline (turn-angle over a k-chord + a two-scale localization test to
  reject smooth arcs) and split the fit there. Tuning the fitter's smoothing
  to "keep corners" always loses — the polygon step drops the vertex first.
- **Disjoint-scope A/B pairs compound cleanly; same-function pairs don't.**
  Every shipped combination (r13, r14, r21+r22) paired candidates on
  genuinely separate code paths (label chain vs stroke net vs fill emitter).
  The r21+r22 teeth win REQUIRED both halves (B sharpened surviving nubs, A
  restored severed ones) — neither alone reached Recraft. Pick candidates by
  code-path disjointness, and expect the real win to be the interaction.
- **Population-measure every threshold with margin; the naive brief value is
  usually a landmine.** r22's naive contrast gap 60 fired 128 FALSE rescues on
  chopchop; the measured separation (true tips 218, falses ≤204) set gap 210.
  Always measure the true-feature population against the false-fire population
  before trusting a constant.
- **Byte-identical + integrated-render-equals-artifact = verification transfers
  exactly.** r21/r22 confirmed the candidate's artifact SVG was byte-identical
  to the integrated-on-main render, so the artifact eye-verdict applied
  verbatim — determinism turned "re-verify after integrate" into a hash check.
  Worth reproducing: render the integrated build and compare to the artifact
  before re-eyeballing everything.
- **Negative results banked (don't retry blind):** parsimony centerline fit ≈
  smooth+Schneider by eye at higher point cost (r5); palette re-grading refuted
  by measurement — Recraft does NOT re-grade tints (r8); the run-4 ridge walker
  never reached its 4w cap (dies 0–2.3w) so "raise the cap" is the wrong lever
  (r15).
