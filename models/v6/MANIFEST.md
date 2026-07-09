# v6 — serration sharpness + clean stroke terminals (autoresearch it18–it19)

Git: **a8d728d** (runs 21–23, over v5 @ c61755e). Engine = `contour_lines`.
Examples rendered at a8d728d.

Adds over v5:
- **Monster teeth: tall AND sharp** (runs 21–22, A+B compound). Corner-pinned
  parsimony fill fits keep V-notches as hard vertices (turn≥80° @k=6 +
  two-scale localization); severed spike tips rescued and welded in despeckle
  (contrast gap≥210, population-measured — a naïve gap fired 128 false
  rescues on chopchop). Corpus-wide corner sharpness win: mountain pine tips,
  fox fur wisps, crystals facet joins, logo-badge blade points.
- **Ribbon/wedge end-caps rounded** (run 23): flat width-spanning butts →
  semicircular caps emitted as a separate subpath, bodies byte-identical.

Verified by eye vs prev + Recraft on all 8 targets; monster teeth approach
the Recraft reference. Negative result kept: dark-subfeature label-guard
(A-darkguard) regression-free but no visible win — the fill fitter is a
co-bottleneck (closed later in v7/v8).

Repro: `python run_model.py -m v6 -i data/inputs/<img>`
