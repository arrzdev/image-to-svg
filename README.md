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
| v5      | 2026-07-08 03:01          | `c61755e` | **yes**  | autoresearch arc (runs 2–20): junction anchoring/bridging/ink-extension, corner+miter serrations, shadow-tone merge, fleck absorption, wiggle-gate texture→daubs, guarded speckle dissolve, light-accent guard, junction pool clamp, light-line capsules + sliver steal, chord/arc endpoint bridging (rabbit heart closed), byte-deterministic renders |
| v6      | 2026-07-08 05:01          | `a8d728d` | **yes**  | serration sharpness (runs 21–23): monster teeth tall AND sharp (corner-pinned fills + spike-tip rescue), corpus-wide corner sharpness, round-capped ribbon ends |
| v7      | 2026-07-09 07:45          | `8431d34` | **yes**  | straight lines + letterforms (runs 25–29): thin-dark-line lock (heart notch + paw fingers back), two-tier chroma gate (ZZA letters + chopchop junction tangles fixed), straight-piece priors (pizza checkers ruler-straight) |
| v8      | 2026-07-09 12:06          | `5d1a9d6` | **yes**  | color-guarded joins + deep cusps (runs 34–35): refuse welds across a color break (over-joins gone), junction cusp descent (heart notch full depth), straight-chain lock (pizza verticals straight through crossings) |
| v9      | 2026-07-09 16:15          | `18797ae` | **yes (LIVE)** | 40x performance (byte-identical output) + sharpen prepass default-ON (USER idea: blur-noise melted pre-quantize; heart flat+rim, strut daubs gone, dropped letter restored) |

All runnable versions expose the same pipeline (`contour_lines`, each at its
own vintage) through `entry.py`; v3's `examples/` additionally keeps its
`elephant_fast` / `elephant_grail` tournament outputs for reference. **v9 is
the current/live engine**; v3–v8 are frozen milestones. `models/README.md`
narrates each version vs the previous and vs Recraft.

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
models/            v3–v9 + staged→live symlink: entry.py + src/ + examples/
                   (`-m staged` runs the loop's current work-in-progress)
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
`models/v9/src/` (the live engine); the next structural milestone snapshots it
to `models/v10/`.
