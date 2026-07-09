# v8 — color-guarded joins + deep concave cusps + ruler-straight grids (it21)

Git: **5d1a9d6** (runs 34–35, over v7 @ 8431d34). Engine = `contour_lines`.
The current shipped engine. Examples rendered at 5d1a9d6.

Adds over v7:
- **Color-guarded joining** (run 34, USER idea): the bridge/chord/extension
  chain welded lines of different source colors. A join now refuses when the
  two strokes' label colors differ (RGB distance >30 — good joins are
  label-identical at 0; over-joins measured 51–125). Removes chopchop
  knot-hole/leaf welds, fox chin-worm weld, rabbit spur/sleeve welds; the
  hard-won heart/tuft/trunk closures still fire.
- **Junction cusp descent** (run 35): the rabbit heart notch is drawn by the
  stroke layer (the fill edge is flat — the ink V is absorbed); its
  medial-axis junction sat at the wedge top with no descending branch. One
  tangent-aligned extension into the ink pocket renders the notch at **full
  depth ≈ original/Recraft**.
- **Straight-chain lock** (run 35): the fit itself added a measured −2.75px
  S-bow to straight ribbon chains; a sagitta-bow lock (≤0.4) projects them
  onto their TLS line pre-fit. Pizza verticals ruler-straight through
  crossings.

Verified by eye vs prev + Recraft; A+B interaction confirmed on the
integrated build. USER-reported defects closed to date: over-rounding /
straight lines, over-joining, the heart, ZZA letterforms, junction tangles,
paw fingers.

Repro: `python run_model.py -m v8 -i data/inputs/<img>`
