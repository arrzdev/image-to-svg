"""vtracer: modern color/spline tracer. Strong default for logos & flat art."""
from __future__ import annotations

import os
import tempfile

from .base import Pipeline, Param

try:
    import vtracer
    _AVAILABLE = True
    _REASON = ""
except Exception as e:  # pragma: no cover
    vtracer = None
    _AVAILABLE = False
    _REASON = f"vtracer import failed: {e}"


class VtracerPipeline(Pipeline):
    id = "vtracer"
    name = "vtracer (color spline)"
    description = "Rust color tracer. Clusters color, traces smooth spline paths. Best all-round baseline for logos."
    available = _AVAILABLE
    unavailable_reason = _REASON

    params = [
        Param("posterize", "Posterize first (k colors)", "int", 0, min=0, max=32, step=1,
              help="0 = off. K-means flatten before tracing: collapses anti-aliased "
                   "line halos so a stroke traces as ONE region instead of many thin "
                   "noisy patches. Try 12-20 for line-art."),
        Param("colormode", "Color mode", "select", "color", options=["color", "binary"]),
        Param("mode", "Curve mode", "select", "spline", options=["spline", "polygon", "none"],
              help="spline = smooth bezier, polygon = straight edges"),
        Param("hierarchical", "Hierarchy", "select", "stacked", options=["stacked", "cutout"],
              help="stacked overlaps layers; cutout carves holes"),
        Param("filter_speckle", "Filter speckle (px)", "int", 2, min=0, max=64, step=1,
              help="Discard blobs smaller than this. Lower = keep more small detail; higher = fewer tiny paths."),
        Param("color_precision", "Color precision (bits)", "int", 8, min=1, max=8, step=1,
              help="Significant color bits. Below 8, close colors merge — can DELETE whole "
                   "objects (white clouds into pale sky). Lower only for deliberate flattening."),
        Param("layer_difference", "Layer difference", "int", 8, min=0, max=256, step=1,
              help="Color delta between layers. Higher = fewer layers but close-color "
                   "content can merge away; 8 beat 16 across the whole sample set."),
        Param("corner_threshold", "Corner threshold", "int", 60, min=0, max=180, step=1,
              help="Angle to treat as a corner vs. smooth."),
        Param("length_threshold", "Length threshold", "float", 2.0, min=0.0, max=16.0, step=0.5,
              help="Minimum path segment length. Lower = keep finer detail."),
        Param("splice_threshold", "Splice threshold", "int", 45, min=0, max=180, step=1),
        Param("path_precision", "Path precision (decimals)", "int", 3, min=0, max=8, step=1),
    ]

    def _posterize(self, image_path: str, k: int) -> str:
        """K-means flatten to k colors; returns path of the temp posterized PNG.

        Anti-aliased strokes otherwise fragment into several intermediate-color
        clusters, which vtracer traces as separate ragged patches; flattening
        assigns the halo to its nearest real color so each stroke is one region.
        """
        import cv2
        import numpy as np
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        Z = img.reshape(-1, 3).astype(np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
        _, labels, centers = cv2.kmeans(Z, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
        flat = np.clip(centers, 0, 255).astype(np.uint8)[labels.flatten()].reshape(img.shape)
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        cv2.imwrite(path, flat)
        return path

    def run(self, image_path: str, params: dict) -> str:
        if not _AVAILABLE:
            raise RuntimeError(_REASON)
        p = self.resolved_params(params)
        posterized = None
        if p["posterize"] > 1:
            posterized = self._posterize(image_path, p["posterize"])
            image_path = posterized
        out_fd, out_path = tempfile.mkstemp(suffix=".svg")
        os.close(out_fd)
        try:
            vtracer.convert_image_to_svg_py(
                image_path,
                out_path,
                colormode=p["colormode"],
                hierarchical=p["hierarchical"],
                mode=p["mode"],
                filter_speckle=p["filter_speckle"],
                color_precision=p["color_precision"],
                layer_difference=p["layer_difference"],
                corner_threshold=p["corner_threshold"],
                length_threshold=p["length_threshold"],
                splice_threshold=p["splice_threshold"],
                path_precision=p["path_precision"],
            )
            with open(out_path, "r", encoding="utf-8") as f:
                return f.read()
        finally:
            if os.path.exists(out_path):
                os.remove(out_path)
            if posterized and os.path.exists(posterized):
                os.remove(posterized)
