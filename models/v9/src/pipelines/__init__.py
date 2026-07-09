"""Pipeline registry. Import a pipeline here to expose it in the playground."""
from __future__ import annotations

from typing import Dict, List

from .base import Pipeline
from .vtracer_pipe import VtracerPipeline
from .quantize_contours import QuantizeContoursPipeline
from .potrace_layers import PotraceLayersPipeline
from .shared_boundary import SharedBoundaryPipeline
from .stroke_hybrid import StrokeHybridPipeline
from .contour_lines import ContourLinesPipeline

_PIPELINES: List[Pipeline] = [
    VtracerPipeline(),
    QuantizeContoursPipeline(),
    PotraceLayersPipeline(),
    SharedBoundaryPipeline(),
    StrokeHybridPipeline(),
    ContourLinesPipeline(),
]

REGISTRY: Dict[str, Pipeline] = {p.id: p for p in _PIPELINES}


def list_pipelines() -> List[dict]:
    return [p.describe() for p in _PIPELINES]


def get_pipeline(pipeline_id: str) -> Pipeline:
    if pipeline_id not in REGISTRY:
        raise KeyError(pipeline_id)
    return REGISTRY[pipeline_id]
