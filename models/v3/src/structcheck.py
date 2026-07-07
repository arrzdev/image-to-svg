"""Structural-integrity detector for deep-zoom SVG artifacts.

Quantifies hairline gaps between adjacent filled regions (and junction
pinholes/spurs that expose the background) — subpixel boundary damage that
the 1536px perceptual metric in metrics.py cannot see.

How it works
------------
The SVG is rendered ONCE at high zoom (default 4096px long side) with a
TRANSPARENT background, and the alpha channel is read as a coverage map.
The key physical fact: where two opaque paths share a perfectly coincident
boundary, antialiasing composites to alpha >= ~0.75 (two ~0.5-coverage
fragments: 0.5 + 0.5*0.5), and this floor is *scale-invariant*. A real
geometric gap, however, drives alpha toward 0 as zoom increases. So
``alpha < 0.5`` at deep zoom is unambiguous evidence of background bleeding
through — a hairline, pinhole, or spur-shaped hole.

Legitimately transparent areas (an SVG without a background rect) are wide
blobs, not thin ridges: they are identified via distance transforms (any
gap pixel within reach of a deep transparent core is background, plus a
margin that drops the silhouette's own AA ring) and excluded.

The count of hairline pixels is normalized by total region-boundary length
(color-edge pixels in the composited render), making the score independent
of image size and shape count.

Limitations: opaque overlaps that fully swallow their seam are invisible by
design (they produce no visual artifact at any zoom — professional assets
like recraft-elephant.svg overlap deliberately). Gaps narrower than ~1/4 of
a user-space pixel fall into the same alpha band as benign coincident seams
at the default zoom; raise ``size`` if that regime ever matters.

API
---
``integrity(svg) -> dict`` with at least ``score`` (1.0 = clean, -> 0 dirty)
and ``hairline_px_per_kboundary``. Runs in ~1.5 s per SVG.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile

import cv2
import numpy as np
from PIL import Image

try:
    from render import _RESVG  # backend modules are imported flat (sys.path)
except ImportError:
    from .render import _RESVG

# Render zoom: long side of the analysis raster. 4096 over a typical
# 900-1024 viewBox is a 4-4.5x deep zoom — enough for any gap >= ~0.25
# user px to produce alpha < 0.5 pixels.
_SIZE = 4096

# alpha < _GAP_THRESH (of 255) counts as exposed background. 128 sits well
# below the ~191 (0.75) floor of a coincident AA seam and well above the
# near-zero alpha of a real hairline at deep zoom.
_GAP_THRESH = 128

# Boundary map: a pixel is "boundary" if any RGB channel changes by more
# than this within its 3x3 neighborhood (morphological gradient).
_EDGE_THRESH = 24

# Half-score point of the score curve, in hairline px per 1000 boundary px.
# Clean files measure < 1; known-dirty independently-refined files 50-85.
_H50 = 5.0


def _viewbox_aspect(svg: str) -> float:
    """width/height aspect of the SVG canvas (1.0 if undeterminable)."""
    m = re.search(r'viewBox\s*=\s*["\']\s*([\d.eE+-]+)[\s,]+([\d.eE+-]+)'
                  r'[\s,]+([\d.eE+-]+)[\s,]+([\d.eE+-]+)', svg)
    if m:
        w, h = float(m.group(3)), float(m.group(4))
        if w > 0 and h > 0:
            return w / h
    mw = re.search(r'<svg[^>]*\bwidth\s*=\s*["\']([\d.]+)', svg)
    mh = re.search(r'<svg[^>]*\bheight\s*=\s*["\']([\d.]+)', svg)
    if mw and mh and float(mh.group(1)) > 0:
        return float(mw.group(1)) / float(mh.group(1))
    return 1.0


def _render_rgba(svg: str, width: int, height: int) -> np.ndarray:
    """Render to (H, W, 4) uint8 with a TRANSPARENT background.

    render.svg_to_rgb composites over white, which is exactly what hides
    hairlines' alpha signature — so this module renders on its own.
    Channel order is BGRA (resvg path) or RGBA (cairosvg fallback); the
    analysis only distinguishes the alpha plane at index 3, so color order
    does not matter.
    """
    if _RESVG:
        with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
            f.write(svg)
            svg_path = f.name
        png_path = svg_path + ".png"
        try:
            subprocess.run(
                [_RESVG, svg_path, png_path,
                 "--width", str(width), "--height", str(height)],
                check=True, capture_output=True,
            )
            # cv2 decodes big PNGs ~2x faster than PIL
            arr = cv2.imread(png_path, cv2.IMREAD_UNCHANGED)
            if arr is not None:
                if arr.ndim == 2:  # grayscale, no alpha: fully opaque
                    arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGRA)
                elif arr.shape[2] == 3:
                    arr = cv2.cvtColor(arr, cv2.COLOR_BGR2BGRA)
                if arr.shape[:2] != (height, width):
                    arr = cv2.resize(arr, (width, height),
                                     interpolation=cv2.INTER_LINEAR)
                return arr
        except Exception:
            pass  # fall through to cairosvg
        finally:
            for p in (svg_path, png_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass
    import io

    import cairosvg
    png_bytes = cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        output_width=width, output_height=height,
    )
    return np.asarray(Image.open(io.BytesIO(png_bytes)).convert("RGBA"))


def integrity(svg: str, size: int = _SIZE) -> dict:
    """Score deep-zoom structural integrity of an SVG in [0, 1].

    Returns a dict with:
      score                       1.0 = structurally clean, -> 0 = riddled
                                  with hairline gaps at deep zoom
      hairline_px_per_kboundary   hairline-gap pixels per 1000 boundary px
                                  (the raw, size-independent measurement)
      deep_gap_px_per_kboundary   subset with alpha < 0.25 — fully open
                                  gaps, the worst offenders
      seam_px_per_kboundary       benign coincident-seam pixels (alpha in
                                  [0.5, 0.78)); NOT in the score. 0 means
                                  boundaries are overlap-sealed (pro style),
                                  large means shared edges are coincident.
      hairline_px, boundary_px    raw counts at the analysis resolution
      render_w, render_h          analysis raster dimensions
    """
    aspect = _viewbox_aspect(svg)
    if aspect >= 1.0:
        w, h = size, max(1, round(size / aspect))
    else:
        w, h = max(1, round(size * aspect)), size

    rgba = _render_rgba(svg, w, h)
    channels = cv2.split(rgba)  # contiguous planes: fast morphology
    alpha = channels[3]

    # --- boundary length (normalizer): color edges between regions.
    # Raw (unpremultiplied) channels suffice: transparent px decode as
    # RGB=0, so region/background transitions register as edges too, and
    # the alpha plane itself is included so pure-coverage edges count.
    k3 = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    grad = np.zeros(alpha.shape, np.uint8)
    for ch in channels:
        grad = np.maximum(grad, cv2.morphologyEx(ch, cv2.MORPH_GRADIENT, k3))
    boundary_px = int((grad > _EDGE_THRESH).sum())

    # --- exposed-background mask
    gap = (alpha < _GAP_THRESH).astype(np.uint8)

    # Wide transparent blobs are legitimate background, not damage.
    # Identified via two distance transforms (kernel-size-independent
    # runtime, unlike a large morphological opening): pixels deeper than
    # _WIDE_R inside the gap mask are background cores; everything within
    # _WIDE_R + 4 of a core (the reconstruction + the silhouette's own AA
    # ring) is excluded. Hairlines/spurs are far thinner than 2*_WIDE_R
    # render px (~16 user px at this zoom) and survive.
    scale = size / 1024.0  # user px -> render px for a typical 1024 canvas
    wide_r = float(min(100, max(12, round(8 * scale))))
    if gap.any():
        dist_in = cv2.distanceTransform(gap, cv2.DIST_L2, 3)
        core = (dist_in > wide_r).astype(np.uint8)
        if core.any():
            dist_out = cv2.distanceTransform(1 - core, cv2.DIST_L2, 3)
            gap &= dist_out > (wide_r + 4.0)

    hairline_px = int(gap.sum())
    deep_px = int(((alpha < 64) & (gap > 0)).sum())
    # benign coincident seams: alpha in [0.5, ~0.78) but not counted as gap
    seam_px = int(((alpha >= _GAP_THRESH) & (alpha < 199)).sum())

    kb = max(boundary_px, 1) / 1000.0
    h_per_kb = hairline_px / kb
    score = 1.0 / (1.0 + h_per_kb / _H50)

    return {
        "score": float(score),
        "hairline_px_per_kboundary": float(h_per_kb),
        "deep_gap_px_per_kboundary": float(deep_px / kb),
        "seam_px_per_kboundary": float(seam_px / kb),
        "hairline_px": hairline_px,
        "boundary_px": boundary_px,
        "render_w": w,
        "render_h": h,
    }
