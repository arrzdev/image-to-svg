# data/

The benchmark set. Inputs and Recraft references are paired by **basename**.

| folder | contents |
|---|---|
| `inputs/` | 18 test rasters: logos, flat illustrations, game assets (`<name>.jpg\|png`) |
| `targets/` | 11 Recraft vectorizer outputs (`<name>.svg`), the quality reference every metric compares against |
| `inputs_idealized/` | SD-turbo img2img pre-idealized inputs from the hybrid experiment (`research/experiments/hybrid/`) |
| `_archive/` | stray SVGs from an early migration, kept for provenance |
| `outputs/` | where `run_model.py` and the browser tester write results (gitignored) |

The 11 images that have a Recraft target form the scoring corpus for
`eval/tilecmp_gate.py` and `eval/struct_compare.py`: app-asset, chopchop,
crystals, elephant, fox, logo-geometric, monster-flat-line, mountain,
pizza-box, rabbit, shield. The remaining 7 inputs (coins, files-pile,
game-assets, game-assets-2, logo-badge, logo-lineart, logo-wordmark) are used
for eye checks and generalization only.

Image credits are in the root README.
