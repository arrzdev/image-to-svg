"""Shared-boundary pipeline: quantize -> boundary graph -> per-edge curve fit.

The structural fix for deep-zoom artifacts: independent per-region tracing fits
every boundary twice and the fits never coincide (hairline gaps, overlaps,
junction spurs). Here each edge of the region-adjacency graph is Schneider-
fitted ONCE in svgcore and both neighbors reuse the identical cubic chain
(cubic reversal is exact), so boundaries coincide by construction.

Runs the whole stack in ~2s at 1024px — this is also the engine's fast tier.
"""
from __future__ import annotations

from typing import List

import cv2
import numpy as np

from .base import Param, Pipeline
from .quantize_contours import (
    _consolidate_palette,
    _despeckle_labels,
    _quantize,
    _smooth_labels,
)


class SharedBoundaryPipeline(Pipeline):
    id = "shared_boundary"
    name = "Shared boundary (curves)"
    description = ("Region-adjacency boundary graph; every edge curve-fitted once "
                   "and shared by both neighbors — zero gaps/overlaps by construction.")
    params: List[Param] = [
        Param("num_colors", "Colors (k)", "int", 16, min=4, max=32, step=1),
        Param("seed", "K-means seed", "int", 0, min=0, max=99999, step=1),
        Param("merge_de", "Palette merge ΔE", "float", 12.0, min=0.0, max=30.0, step=0.5),
        Param("min_area", "Despeckle (px)", "int", 120, min=0, max=2000, step=10),
        Param("blur", "Pre-blur (px)", "int", 1, min=0, max=9, step=1),
        Param("tol", "Fit tolerance", "float", 1.0, min=0.25, max=4.0, step=0.25,
              help="Schneider max-error in pixels; lower = more faithful, more points."),
        Param("corner_deg", "Corner angle (°)", "float", 60.0, min=20.0, max=120.0, step=5.0),
        Param("smooth_win", "Pre-fit smoothing", "int", 5, min=0, max=15, step=1,
              help="Moving-average window on each boundary polyline before fitting; "
                   "kills quantizer staircase wobble so strokes sweep like the artist's."),
        Param("dissolve", "Edge-support dissolve", "float", 0.0, min=0.0, max=40.0, step=1.0,
              help="Merge region pairs whose shared boundary has mean source contrast "
                   "below this (RGB units). Kills boundaries manufactured by quantizing "
                   "smooth shading; 0 = off. Risky on faint-but-real contours — meant "
                   "as a tournament candidate, not a default."),
        Param("parsimony", "Parsimony fit (opttol)", "float", 0.0, min=0.0, max=2.0, step=0.1,
              help="Potrace-style minimal-knot fitting; sub-±0.5px wobble structurally "
                   "cannot survive. 0.2 beats the default fitter on all axes; 0.5-1.0 "
                   "marches into the Recraft point corner. 0 = classic smooth+Schneider."),
        Param("split_paths", "One path per element", "bool", True,
              help="Emit each connected element (outer loop + its holes) as its own "
                   "<path> — professional structure, pixel-identical to compound "
                   "emission and slightly smaller gzipped."),
    ]

    def run(self, image_path: str, params: dict) -> str:
        return self.build_context(image_path, params)["svg"]

    def build_context(self, image_path: str, params: dict) -> dict:
        """Full pipeline returning the boundary-graph context alongside the
        SVG — the engine needs it to resnap shared edges after DiffVG
        refinement (see boundary.resnap_refined)."""
        import boundary

        p = self.resolved_params(params)
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError(f"Could not read image: {image_path}")
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        if p["blur"] > 0:
            img = cv2.medianBlur(img, p["blur"] * 2 + 1)

        labels, centers = _quantize(img, p["num_colors"], p["seed"])
        if p["merge_de"] > 0:
            labels, centers = _consolidate_palette(labels, centers, p["merge_de"])
            labels = _despeckle_labels(labels, max(p["min_area"], 16), centers)
            labels = _smooth_labels(labels, len(centers), centers=centers)

        if p["dissolve"] > 0:
            labels, centers = boundary.dissolve_faint_pairs(
                labels, centers, img, contrast_thresh=p["dissolve"])

        edges, _nodes = boundary.build_edges(labels)
        loops = boundary.region_loops(edges, len(centers))
        svg, plan, fitted = boundary.loops_to_svg_curves(
            labels, centers, edges, loops, tol=p["tol"],
            corner_deg=p["corner_deg"], smooth_win=p["smooth_win"],
            return_plan=True, parsimony=p["parsimony"])
        if p["split_paths"]:
            # per-element emission: pixel-identical, professional structure
            # (plan/fitted stay in compound form for the DV/resnap machinery)
            from boundary_split import _emit_regions_split
            svg = _emit_regions_split(labels, centers, loops, fitted, edges)
        return {"svg": svg, "plan": plan, "fitted": fitted, "labels": labels,
                "centers": centers, "edges": edges, "loops": loops,
                "split_paths": bool(p["split_paths"])}
