"""Edge-aware color aggregation before quantization.

Tested 2026-07 (unsharp x3, bilateral x2, mean-shift, combos, adaptive-k on
elephant / cute-rabbit / fox; grids in outputs/pre_*.png):

- **bilateral** is the safe default. Parity on clean flat art (elephant),
  clear visible win on soft AI-shaded art (rabbit: broken coat buttons and
  seam lines come back solid; q 0.67 -> 0.76, points 2055 -> 1456 at
  tol=3.0/smooth_win=9). Flattens AA halos without moving edges, so k-means
  stops spending clusters on transition colors.
- **meanshift** is the pick for noisy / texture-dense inputs (fox: visibly
  cleaner, more "designed" shapes, points 7337 -> 4591, q +0.04). But it
  eats small low-contrast details on soft-shaded art (rabbit's buttons
  vanish) — do not make it the default.
- Null results, do not revisit: unsharp mask (any amount) before quantize
  INCREASES AA-halo clusters (overshoot mints new colors; //16 unique count
  grows 30-60%), amount >= 1.5 shifts the whole palette dark and can blow
  pale fills to white. Combos (bilateral->unsharp, meanshift->unsharp) never
  beat the plain filter. Adaptive-k coupling barely fires (aggregated images
  still cover >=14 of 16 colors at 95% pixel coverage) and forcing smaller k
  is seed-unstable; the pipeline's merge_de consolidation already adapts the
  label count (16 -> 9-14 after bilateral).
"""
from __future__ import annotations

import cv2
import numpy as np


def aggregate_colors(img_rgb: np.ndarray, mode: str = "bilateral") -> np.ndarray:
    """Flatten AA transitions / soft shading before k-means quantization.

    img_rgb: HxWx3 uint8 (the pipeline's `proc` raster). Returns same shape.

    mode:
      "bilateral" — safe default; edge-preserving smoothing (d=9, 50, 9).
      "meanshift" — stronger cartoon flattening (sp=12, sr=30); best for
                    noisy/texture-dense inputs, loses tiny low-contrast
                    details on soft-shaded art.
      "none"      — passthrough.
    """
    img = np.ascontiguousarray(img_rgb[:, :, :3], dtype=np.uint8)
    if mode == "bilateral":
        return cv2.bilateralFilter(img, 9, 50, 9)
    if mode == "meanshift":
        return cv2.pyrMeanShiftFiltering(img, 12, 30)
    if mode == "none":
        return img
    raise ValueError(f"unknown aggregation mode: {mode!r}")
