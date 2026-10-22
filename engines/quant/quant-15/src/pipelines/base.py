"""Pipeline framework: a Pipeline turns a raster image into an SVG string.

Each pipeline declares a typed parameter schema so the frontend can render
controls automatically. Keep pipelines pure: input path + params -> SVG string.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional


def _luminance(color) -> float:
    r, g, b = float(color[0]), float(color[1]), float(color[2])
    return 0.299 * r + 0.587 * g + 0.114 * b


# Outline strokes aren't always near-black — purple cartoon lines sit around
# luminance 74. Layers below this count as "line art" for ordering/protection.
DARK_LINE_LUM = 96.0


def order_layers(centers, areas: Dict[int, int], lines_on_top: bool,
                 dark_threshold: float = DARK_LINE_LUM) -> List[int]:
    """Paint order (bottom -> top) for color layers in a layered tracer.

    Default painter's algorithm is largest-area-first. When `lines_on_top` is
    set, dark colors (typical of outlines/line art) are moved to the very top so
    gap-fill dilation of lighter fills can't erode them. Returns color indices
    with a positive area, in paint order.
    """
    live = [ci for ci, a in areas.items() if a > 0]

    def key(ci: int):
        dark = 1 if (lines_on_top and _luminance(centers[ci]) < dark_threshold) else 0
        return (dark, -areas[ci])  # non-dark first; within a group, largest first

    return sorted(live, key=key)


@dataclass
class Param:
    key: str
    label: str
    type: str  # 'int' | 'float' | 'bool' | 'select'
    default: Any
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    options: Optional[List[str]] = None
    help: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


class Pipeline:
    id: str = "base"
    name: str = "Base"
    description: str = ""
    params: List[Param] = []

    # Set to False by pipelines whose external dependency is missing.
    available: bool = True
    unavailable_reason: str = ""

    def run(self, image_path: str, params: dict) -> str:
        """Return an SVG document string."""
        raise NotImplementedError

    def resolved_params(self, params: dict) -> dict:
        """Merge user params over declared defaults, coercing types."""
        out = {}
        for p in self.params:
            val = params.get(p.key, p.default)
            try:
                if p.type == "int":
                    val = int(round(float(val)))
                elif p.type == "float":
                    val = float(val)
                elif p.type == "bool":
                    val = bool(val) if isinstance(val, bool) else str(val).lower() in ("1", "true", "yes", "on")
            except (TypeError, ValueError):
                val = p.default
            out[p.key] = val
        return out

    def describe(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "params": [p.to_dict() for p in self.params],
        }
