"""SVG root-tag utilities.

The playground traces a downscaled raster (denser pixels smooth noise + faster)
but wants the returned SVG to render at the image's ORIGINAL size. Because SVG
is resolution-independent, we keep the traced path coordinates in their
processing-pixel space (the viewBox) and only rewrite the root width/height to
the original dimensions. Anything that renders the SVG scales it up smoothly.
"""
from __future__ import annotations

import re

_SVG_OPEN_RE = re.compile(r"<svg\b[^>]*>", re.IGNORECASE)
_ATTR_RE = lambda name: re.compile(rf'\b{name}\s*=\s*"([^"]*)"', re.IGNORECASE)
_WIDTH_RE = _ATTR_RE("width")
_HEIGHT_RE = _ATTR_RE("height")
_VIEWBOX_RE = _ATTR_RE("viewBox")
_NUM_RE = re.compile(r"[-+]?\d*\.?\d+")


def fit_svg_size(svg: str, out_w: float, out_h: float) -> str:
    """Return `svg` with root width/height set to (out_w, out_h).

    Ensures a viewBox exists (derived from the current width/height if absent)
    so the coordinate space is preserved and the new width/height simply rescale
    the render. Idempotent and safe if the tag already has a viewBox.
    """
    m = _SVG_OPEN_RE.search(svg)
    if not m:
        return svg
    tag = m.group(0)

    if not _VIEWBOX_RE.search(tag):
        w = _first_num(_WIDTH_RE, tag)
        h = _first_num(_HEIGHT_RE, tag)
        if w and h:
            tag = tag[:-1] + f' viewBox="0 0 {w} {h}">'

    tag = _set_attr(tag, "width", _fmt(out_w))
    tag = _set_attr(tag, "height", _fmt(out_h))
    return svg[: m.start()] + tag + svg[m.end():]


def _first_num(rx: re.Pattern, tag: str):
    mm = rx.search(tag)
    if not mm:
        return None
    nums = _NUM_RE.findall(mm.group(1))
    return nums[0] if nums else None


def _set_attr(tag: str, name: str, value: str) -> str:
    rx = _ATTR_RE(name)
    if rx.search(tag):
        return rx.sub(f'{name}="{value}"', tag, count=1)
    return tag[:-1] + f' {name}="{value}">'


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.3f}"
