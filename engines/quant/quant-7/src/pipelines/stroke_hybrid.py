"""Stroke-hybrid pipeline: shared-boundary fills + centerline strokes.

Thin dark line-art regions modeled as filled outlines produce the two last
deep-zoom artifact classes (notched/hooked stroke TIPS, wavering width).
strokes.py extracts their medial-axis centerlines and emits real SVG strokes
(constant-width) / ribbon fills (tapered), while all other regions keep the
shared-boundary fill emission. Tips become clean tapers by construction.
"""
from __future__ import annotations

from typing import List

from .base import Param, Pipeline


class StrokeHybridPipeline(Pipeline):
    id = "stroke_hybrid"
    name = "Stroke hybrid (centerlines)"
    description = ("Shared-boundary fills + medial-axis centerline strokes for "
                   "thin line art — clean tapered tips, constant widths, fewer points.")
    params: List[Param] = [
        Param("num_colors", "Colors (k)", "int", 16, min=4, max=32, step=1),
        Param("seed", "K-means seed", "int", 0, min=0, max=99999, step=1),
        Param("merge_de", "Palette merge ΔE", "float", 12.0, min=0.0, max=30.0, step=0.5),
        Param("min_area", "Despeckle (px)", "int", 120, min=0, max=2000, step=10),
        Param("blur", "Pre-blur (px)", "int", 1, min=0, max=9, step=1),
        Param("tol", "Fit tolerance", "float", 1.0, min=0.25, max=4.0, step=0.25),
        Param("smooth_win", "Pre-fit smoothing", "int", 5, min=0, max=15, step=1),
    ]

    def run(self, image_path: str, params: dict) -> str:
        import strokes
        p = self.resolved_params(params)
        svg, _info = strokes.hybrid_svg(image_path, p)
        return svg
