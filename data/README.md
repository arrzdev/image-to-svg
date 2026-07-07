# data/

The image→SVG working set. Everything is paired by **basename**.

- **inputs/** — source raster images (`<name>.jpg|png`). Fed to our engine
  and to Recraft.
- **targets/** — Recraft's "holy grail" SVG for each input (`<name>.svg`).
  Files that start with `PLACEHOLDER` are **not real** — they mark inputs we
  still need a Recraft output for (see the fetch list below). `elephant.svg`
  is the one real target we have.
- **outputs/** — our engine's generated SVGs, named
  `{name}-{algoVersion}-{timestamp}.svg` (gitignored; regenerate any time).
- **_archive/** — stray SVGs found during migration, kept for safety.
  `shield.maybe-recraft.svg` and `elephant.old.svg` MIGHT be older Recraft
  outputs — worth checking before discarding.

## Recraft targets still needed (replace the placeholders)

Run each input through Recraft with the **same tool/mode** (tell us which),
and drop the SVG at `data/targets/<name>.svg`:

| target file | input | why we want it |
|---|---|---|
| rabbit.svg | data/inputs/rabbit.jpg | outlined character — line-work generalization + junctions |
| crystals.svg | data/inputs/crystals.jpg | gradient — how Recraft bands smooth shading (biggest gap) |
| chopchop.svg | data/inputs/chopchop.png | dense line crossings (the perpendicular-gap defect) |
| logo-geometric.svg | data/inputs/logo-geometric.png | circles/edges — does Recraft snap to primitives |
| flat-noline.svg | *(source a new image)* | flat illustration with NO dark outlines |
| app-character.svg | *(source a new image)* | your real, noisy app character asset |

The two `*.SOURCE-ME.txt` files in inputs/ describe the new images to source.
Highest value if only a few: **rabbit + crystals**.
