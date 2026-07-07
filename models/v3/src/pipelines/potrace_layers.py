"""Potrace per color layer: quantize, then trace each color as a mono bitmap.

Potrace only traces 1-bit bitmaps, so for color we posterize to k colors and
run potrace once per layer, stacking the results largest-area-first. Potrace's
curve optimizer produces very clean, smooth outlines -- a strong contrast point
against vtracer and the raw-contour pipeline.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from typing import List, Tuple

import cv2
import numpy as np

from .base import Pipeline, Param, order_layers as _order_layers, DARK_LINE_LUM

_POTRACE = shutil.which("potrace")
_VIEWBOX_RE = re.compile(r'viewBox="([^"]+)"')
_TRANSFORM_RE = re.compile(r"<g\b[^>]*transform=\"([^\"]+)\"[^>]*>")
_PATH_RE = re.compile(r"<path\b[^>]*\bd=\"([^\"]*)\"[^>]*/?>")


def _quantize(img_rgb: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
    Z = img_rgb.reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(Z, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    centers = np.clip(centers, 0, 255).astype(np.uint8)
    return labels.reshape(img_rgb.shape[:2]), centers


class PotraceLayersPipeline(Pipeline):
    id = "potrace_layers"
    name = "Potrace (color layers)"
    description = "Posterize to k colors, trace each layer with Potrace's optimized curves, stack largest-first."
    available = _POTRACE is not None
    unavailable_reason = "" if _POTRACE else "potrace binary not found (brew install potrace)"

    params = [
        Param("num_colors", "Colors (k)", "int", 6, min=2, max=24, step=1),
        Param("mono", "Mono direct (Otsu)", "bool", False,
              help="Skip k-means entirely: Otsu-threshold to 1-bit and trace "
                   "directly — the classic Potrace path, strongest on glyphs/icons."),
        Param("gap_fill", "Gap fill (px)", "int", 2, min=0, max=6, step=1,
              help="Dilate each color layer so neighbors overlap, closing white seams between regions."),
        Param("lines_on_top", "Dark lines on top", "bool", True,
              help="Paint dark (outline) colors last so gap-fill dilation can't erode line art."),
        Param("turdsize", "Speckle suppression", "int", 4, min=0, max=64, step=1,
              help="Ignore blobs smaller than this many pixels."),
        Param("alphamax", "Corner smoothness", "float", 1.0, min=0.0, max=1.334, step=0.05,
              help="0 = sharp corners, 1.334 = maximally rounded."),
        Param("opttolerance", "Curve optimization", "float", 0.2, min=0.0, max=1.0, step=0.05,
              help="Higher = fewer segments, looser fit."),
    ]

    def _trace_layer(self, mask: np.ndarray, workdir: str, p: dict) -> str:
        """Run potrace on a boolean mask, return its inner path 'd' strings joined."""
        pbm_path = os.path.join(workdir, "layer.pbm")
        svg_path = os.path.join(workdir, "layer.svg")
        # PBM P4: 1 = black (traced). Our mask True should be traced -> value 1.
        h, w = mask.shape
        with open(pbm_path, "wb") as f:
            f.write(f"P4\n{w} {h}\n".encode("ascii"))
            packed = np.packbits(mask.astype(np.uint8), axis=1)
            f.write(packed.tobytes())

        subprocess.run(
            [
                _POTRACE, pbm_path, "-s", "-o", svg_path,
                "--turdsize", str(p["turdsize"]),
                "--alphamax", str(p["alphamax"]),
                "--opttolerance", str(p["opttolerance"]),
            ],
            check=True, capture_output=True,
        )
        with open(svg_path, "r", encoding="utf-8") as f:
            svg = f.read()

        # Potrace wraps paths in a <g transform="translate(...) scale(...)">.
        # We reproduce that transform so coordinates land correctly.
        tm = _TRANSFORM_RE.search(svg)
        transform = tm.group(1) if tm else ""
        ds = _PATH_RE.findall(svg)
        return transform, ds

    def run(self, image_path: str, params: dict) -> str:
        if _POTRACE is None:
            raise RuntimeError(self.unavailable_reason)
        p = self.resolved_params(params)
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError(f"Could not read image: {image_path}")
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        H, W = img.shape[:2]  # already downscaled to the processing size by caller

        if p["mono"]:
            # Direct 1-bit trace: Otsu on luminance; colors sampled from the
            # image itself (mean of each side), background as a full rect.
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            fg = bw == 0          # dark side = glyph
            if fg.mean() > 0.5:   # invert if "foreground" is the majority
                fg = ~fg
            fg_col = img[fg].mean(axis=0) if fg.any() else np.zeros(3)
            bg_col = img[~fg].mean(axis=0) if (~fg).any() else np.full(3, 255)
            with tempfile.TemporaryDirectory() as workdir:
                transform, ds = self._trace_layer(fg, workdir, p)
            bh, bw2 = img.shape[:2]
            br, bgc, bb = [int(round(c)) for c in bg_col]
            fr, fgc, fb = [int(round(c)) for c in fg_col]
            body = [f'<path d="M0 0H{bw2}V{bh}H0Z" fill="#{br:02x}{bgc:02x}{bb:02x}"/>']
            if ds:
                g_open = f'<g transform="{transform}">' if transform else "<g>"
                body.append(f'{g_open}<path d="{" ".join(ds)}" '
                            f'fill="#{fr:02x}{fgc:02x}{fb:02x}" fill-rule="evenodd"/></g>')
            return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{bw2}" height="{bh}" '
                    f'viewBox="0 0 {bw2} {bh}">\n' + "\n".join(body) + "\n</svg>\n")

        labels, centers = _quantize(img, p["num_colors"])
        areas = {ci: int(np.count_nonzero(labels == ci)) for ci in range(len(centers))}
        layers = _order_layers(centers, areas, p["lines_on_top"])

        gap = p["gap_fill"]
        kernel = None
        if gap > 0:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (gap * 2 + 1, gap * 2 + 1))

        # Dark "line" layers are painted last, so their dilation is never
        # covered by anything — it just fattens every stroke. Never dilate them;
        # the layers UNDER the lines bleed enough to close seams.
        from .base import _luminance
        no_dilate = {ci for ci in layers
                     if p["lines_on_top"] and _luminance(centers[ci]) < DARK_LINE_LUM}

        body: List[str] = []
        with tempfile.TemporaryDirectory() as workdir:
            for ci in layers:
                mask = labels == ci
                if kernel is not None and ci not in no_dilate:
                    # Dilate so this layer bleeds under adjacent layers; since we
                    # paint largest-first, foreground layers cover the overlap.
                    mask = cv2.dilate(mask.astype(np.uint8), kernel).astype(bool)
                transform, ds = self._trace_layer(mask, workdir, p)
                if not ds:
                    continue
                r, g, b = centers[ci]
                fill = f"#{r:02x}{g:02x}{b:02x}"
                joined = " ".join(ds)
                g_open = f'<g transform="{transform}">' if transform else "<g>"
                body.append(f'{g_open}<path d="{joined}" fill="{fill}" fill-rule="evenodd"/></g>')

        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">\n' + "\n".join(body) + "\n</svg>\n"
        )
        return svg
