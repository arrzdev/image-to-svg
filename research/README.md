# research/

Everything that isn't a runnable engine or the metric: the written record,
the autonomous loop that produced most engine versions, and one-off studies.
Scripts are meant to be run from the repo root with `.venv/bin/python`.

## docs/ — the written record

| file | what it is |
|---|---|
| [`PROJECT_SPEC.md`](docs/PROJECT_SPEC.md) | mission, judging rules, versioning rules |
| [`VISION.md`](docs/VISION.md) | the thesis: reverse-engineer the drawing, don't trace the raster |
| [`BLUEPRINT.md`](docs/BLUEPRINT.md) | design record for the region- and edge-first rebuilds |
| [`GAP_LEDGER.md`](docs/GAP_LEDGER.md) | open gaps vs Recraft, with evidence |
| [`BACKLOG.md`](docs/BACKLOG.md) | ranked work items |
| [`RESEARCH_LOG.md`](docs/RESEARCH_LOG.md) | day-by-day journal up to loop run 63 |
| [`PAPER_NOTES.md`](docs/PAPER_NOTES.md), [`VECTORIZATION_PAPERS.md`](docs/VECTORIZATION_PAPERS.md) | literature notes |
| [`archive/`](docs/archive/) | `STATE.md` and `RESUME.md`, written for an earlier layout (`backend/`, `models/vN`); kept as history |

## loop/ — the autonomous research loop

| path | what it is |
|---|---|
| [`autoresearch.md`](loop/autoresearch.md) | the loop's operating manual (objective, protocol, off-limits files) |
| `autoresearch.sh` | locked sanity harness (runs the live engine's `ar_eval.py`) |
| `autoresearch.jsonl` | per-run metrics: 76 runs, 44 keep / 28 discard |
| `autoresearch.focus` | current focus image |
| [`worklog.md`](loop/worklog.md) | narrative log |
| `autoresearch_loop.py` | deterministic wrapper: picks a defect, briefs a coding agent, gates its worktree with `eval/tilecmp_gate.py` |
| `*_ledger.jsonl` | keep/discard ledgers of the wrapper and of `eval/tilecmp_loop.py` |
| [`candidates/`](loop/candidates/) | stashed diffs that passed by eye but missed the gate's minimum gain ("riders"); read `MANIFEST.md` before re-applying |
| `artifacts/` | a few SVGs referenced from the worklog |
| `claude/` | Claude Code hook + settings template that resume an in-flight worktree iteration |

The loop is paused (`.autoresearch-off` at the repo root). To resume it with the
autoresearch plugin, which expects its files at the repo root:

```bash
mkdir -p .claude && cp research/loop/claude/settings.json .claude/settings.json
for f in md jsonl sh focus; do ln -s research/loop/autoresearch.$f autoresearch.$f; done
rm -f .autoresearch-off
```

Per-iteration scratch (`loop/iterations/`) is local only and gitignored.

## experiments/ — individual studies

| folder | question | outcome |
|---|---|---|
| [`audit24/`](experiments/audit24/FINDINGS.md) | where does quant-11 stand vs Recraft, honestly? | plateau: parity on flat art, 50–70% on soft shading; root causes E1–E8 |
| [`design-studies/`](experiments/design-studies/) | stage-by-stage pipeline dumps, parameter sweeps, and the comparison figures cited in `BLUEPRINT.md` and the logs | — |
| [`edge11-bench/`](experiments/edge11-bench/) | edge-11 vs the quant-13 baseline on the whole corpus | lost 10 of 11; won pizza-box → stroke graft in quant-16 |
| [`hybrid/`](experiments/hybrid/FINDINGS.md) | does diffusion pre-idealization help the classical pipeline? | no, worse at every strength |
| [`omnisvg/`](experiments/omnisvg/) | OmniSVG 1.1 4B run locally | 2.4–3.2× worse than quant-13 |
| [`curveprior/`](experiments/curveprior/REPORT.md) | can a small model learn Recraft's curve idealization from mined pairs? | no, loses to identity on held-out images |
| [`starvector/`](experiments/starvector/README-MPS.md) | StarVector 1B/8B on Apple Silicon (MPS) | real primitives on simple logos, loops on illustrations |
| [`baselines-v11/`](experiments/baselines-v11/) | quant-11 outputs for all 18 inputs | reference snapshot |
| [`diag/`](experiments/diag/) | early stroke diagnostics | written against the pre-`models/` `backend/` layout; kept as history |
