# image → svg

Raster-to-SVG **idealization** engine: clean confident lines, flat solid
shading, source noise removed — judged by eye against Recraft references, not
by pixel fidelity. Every engine version is kept **runnable side by side** on
the main branch.

## Quickstart

```bash
# one-time: python deps + the Rust svgcore extension (already built into .venv)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# svgcore rebuild if ever needed:  cd svgcore && ../.venv/bin/maturin develop --release

# run a version on an image (writes data/outputs/<image>-<version>-<timestamp>.svg)
python3 run_model.py --model v5 --image data/inputs/elephant.jpg
python3 run_model.py -m v3 -i data/inputs/chopchop.png -o /tmp/out.svg
python3 run_model.py --list

# browser tester: pick image + version, see ORIGINAL | OUTPUT | TARGET
./run.sh          # http://127.0.0.1:8000
```

macOS note: SVG rendering needs `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`
(cairo). `run.sh`, `run_model.py`, and the entry points set it automatically.

## Versions

Each runnable version lives in `models/<v>/` with the **same stable entry
contract**, so routing between versions is non-destructive regardless of how
different the internals are:

```
models/<v>/entry.py     # run(image_path: str, params: dict|None = None) -> str (SVG)
models/<v>/src/         # that version's complete engine code (frozen)
models/<v>/examples/    # SVGs produced by exactly this code — quick visual check
models/<v>/MANIFEST.md  # what changed, eye-verdicts, negative results
```

| version | produced (commit time)    | commit    | runnable | what it is |
|---------|---------------------------|-----------|----------|------------|
| v1      | ~2026-07-05               | pre-git   | no (historical) | first tournament engine: vtracer/potrace/quantize portfolios + DiffVG refine; structurally dirty at deep zoom |
| v2      | 2026-07-06                | pre-git   | no (historical) | shared-boundary vectorization + honest shared-edge DV + structural-integrity judge |
| v3      | 2026-07-07 01:58          | `d7804f5` | **yes**  | parsimony fitter (wobble-free fills), first width-constant contour strokes, cached testbed |
| v4      | 2026-07-07 03:03          | `c463914` | **yes**  | line/fill idealization: centerline stroke network + flat parsimony shading, Recraft-calibrated line weight |
| v5      | 2026-07-07 23:29          | `3d251ad` | **yes**  | autoresearch arc (runs 2–14): junction anchoring/bridging/ink-extension, corner+miter serrations, shadow-tone merge, fleck absorption, wiggle-gate texture→daubs, guarded speckle dissolve, light-accent guard (striped straw!), junction pool clamp |

All runnable versions expose the same pipeline (`contour_lines`, each at its
own vintage) through `entry.py`; v3's `examples/` additionally keeps its
`elephant_fast` / `elephant_grail` tournament outputs for reference.
`models/README.md` narrates each version vs the previous and vs Recraft.

One version per process: the version sources share module names, so the CLI
and the frontend run every call in an isolated subprocess. Import
`models/<v>/entry.py` directly only if your process touches a single version.

## Frontend

`./run.sh` serves `frontend/` via `server.py` (FastAPI). Pick an image from
`data/inputs/`, pick a version, **Run** — the page shows the original, the
fresh output (also saved under `data/outputs/`), and the Recraft target when
one exists in `data/targets/`. No knobs; each run goes through the same
`entry.py` contract as the CLI.

## Repo map

```
run_model.py       CLI — route any image through any version
run.sh / server.py browser tester
models/            v3 / v4 / v5: entry.py + src/ + examples/ (see above)
data/inputs/       test images   · data/targets/  Recraft references (locked)
data/outputs/      run artifacts (gitignored)
frontend/          the minimal tester UI
svgcore/           Rust extension (Schneider fitting etc.), pip-installed into .venv
research/          the autonomous improvement loop: spec, backlog, research log,
                   worklog, autoresearch state + sanity harness (paused; see
                   research/autoresearch.md)
outputs/           render cache (gitignored, regenerable)
```

## The research loop (paused)

Engine quality came from an autonomous vision-first experiment loop
(`research/`): worktree-parallel candidates, eye verdicts on zoomed
comparison grids, rich discard logging. It is paused via `.autoresearch-off`.
`research/docs/PROJECT_SPEC.md` is the mission; `research/docs/BACKLOG.md` the
idea queue; `research/docs/RESEARCH_LOG.md` the full journal. The loop edits
`models/v5/src/` (the live engine); the next structural change bumps to
`models/v6/`.
