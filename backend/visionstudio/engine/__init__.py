"""Motor de ejecución del grafo.

Punto de entrada único: exporta el modelo de grafo, la validación, los
ejecutores y el runner. El resto del backend (API, runloop) importa de aquí.
"""

from visionstudio.engine.errors import EngineError, ErrorCode
from visionstudio.engine.executors import (
    BlockExecutor,
    ExecutorRegistry,
    build_default_registry,
    default_executors,
)
from visionstudio.engine.executors_cv import (
    BlackWhiteExecutor,
    BlurExecutor,
    CameraExecutor,
    ContoursExecutor,
    DetectionListExecutor,
    DrawTextExecutor,
    EdgeDetectionExecutor,
    GrayscaleExecutor,
    ThresholdExecutor,
    build_full_registry,
    full_executors,
)
from visionstudio.engine.graph import Edge, Graph, Node
from visionstudio.engine.runner import GraphRunner
from visionstudio.engine.validation import GraphValidator, Issue

__all__ = [
    "BlackWhiteExecutor",
    "BlurExecutor",
    "BlockExecutor",
    "CameraExecutor",
    "ContoursExecutor",
    "DetectionListExecutor",
    "DrawTextExecutor",
    "EdgeDetectionExecutor",
    "Edge",
    "EngineError",
    "ErrorCode",
    "ExecutorRegistry",
    "Graph",
    "GraphRunner",
    "GraphValidator",
    "GrayscaleExecutor",
    "Issue",
    "Node",
    "ThresholdExecutor",
    "build_default_registry",
    "build_full_registry",
    "default_executors",
    "full_executors",
]