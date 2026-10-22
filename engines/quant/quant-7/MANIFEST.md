# v7 — straight lines, crisp letterforms, un-tangled junctions (autoresearch it20)

Git: **8431d34** (runs 25–29, over v6 @ a8d728d). Engine = `contour_lines`.
Examples rendered at 8431d34. This milestone answers the user's 2026-07-08
eye-verdict (straight-line fidelity, small-detail loss, chopchop quality).

Adds over v6:
- **Thin-dark-line lock** (run 25): the label cleanup (despeckle/smooth) was
  erasing sub-3px drawn lines wholesale; downstream bridging then closed the
  survivors into blobs. True-ink thin elongated pixels (lum<60, half-width
  ≤1.6px, not blob-fringe, ≥40px) are re-stamped after cleanup. Restores the
  **rabbit heart notch, paw finger lines**, and part of the pizza straights.
- **Two-tier chroma gate on stroke candidates** (run 27): saturated mid-darks
  (pizza "ZZA" letters lum~76 spread 151, gem fills) were being stroke-ified
  and centerline-looped into squiggles. Gate: stroke iff lum<60 OR
  chroma-spread≤45. **Fixes the ZZA letterforms and the chopchop junction
  tangles** (those were stroke-ified brown texture labels).
- **Straight-piece priors** (runs 28–29): chord-straight branch fits + TLS
  straight-piece fill fits — pizza checker horizontals render ruler-straight;
  every target's SVG got simpler (−8..13KB).

Verified by eye across all targets; recraft_gap chopchop 0.868→0.871.

Repro: `python run_model.py -m v7 -i data/inputs/<img>`
