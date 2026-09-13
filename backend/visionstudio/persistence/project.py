"""Persistencia de proyectos (formato JSON versionado).

Formato v1 (docs/FORMATO_PROYECTO.md):

```json
{
  "format_version": 1,
  "name": "proyecto",
  "language": "es",
  "camera": {"index": 0, "width": 640, "height": 480},
  "flow": {"mode": "continuous", "interval_ms": 100},
  "blocks": [{"id": "n1", "type": "block.camera", "x": 0, "y": 0, "params": {}}],
  "connections": [
    {"from": {"block": "n1", "port": "out"}, "to": {"block": "n2", "port": "in"}}
  ]
}
```

La versión actual es 1. Las migraciones entre versiones anteriores se
encadenan automáticamente (persistence/migrations.py): si el archivo declara
una versión menor, se migra hasta la actual antes de parsear. Un proyecto con
versión MAYOR a la soportada se rechaza con ERR_PROJECT_VERSION_UNSUPPORTED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from visionstudio.blocks import BlockRegistry
from visionstudio.camera.device import CameraConfig
from visionstudio.engine.errors import ErrorCode
from visionstudio.engine.graph import Edge, Graph, Node
from visionstudio.errors import EngineError
from visionstudio.persistence.migrations import MIGRATIONS

# Versión del formato de proyecto soportada por esta versión del backend.
CURRENT_FORMAT_VERSION = 1


@dataclass
class ProjectMeta:
    """Metadatos y configuración global del proyecto (fuera del grafo)."""

    name: str = "Untitled"
    language: str = "es"
    camera: CameraConfig = field(default_factory=CameraConfig)
    mode: str = "continuous"  # modo de ejecución (continuous | timer | manual)
    interval_ms: int = 100


def project_to_dict(graph: Graph, meta: ProjectMeta) -> dict[str, Any]:
    """Serializa un grafo + metadatos al formato de proyecto v1."""
    return {
        "format_version": CURRENT_FORMAT_VERSION,
        "name": meta.name,
        "language": meta.language,
        "camera": {"index": meta.camera.index, "width": meta.camera.width, "height": meta.camera.height},
        "flow": {"mode": meta.mode, "interval_ms": meta.interval_ms},
        "blocks": [
            {
                "id": n.id,
                "type": n.type,
                "x": n.x,
                "y": n.y,
                "params": n.params,
            }
            for n in graph.nodes
        ],
        "connections": [
            {
                "from": {"block": e.from_block, "port": e.from_port},
                "to": {"block": e.to_block, "port": e.to_port},
            }
            for e in graph.edges
        ],
    }


def project_from_dict(data: dict[str, Any], registry: BlockRegistry) -> tuple[Graph, ProjectMeta]:
    """Reconstruye (Graph, ProjectMeta) desde el formato de proyecto.

    Comprueba la versión del formato y la estructura básica. La validación
    estructural completa (tipos, ciclos, conexiones) la hace GraphValidator
    (la aplica la API antes de aceptar el proyecto).
    """
    # 1. Versión del formato: mayor que la soportada -> rechazar. Menor ->
    #    encadenar migraciones hasta la versión actual (si alguna falta o
    #    falla, ERR_MIGRATION_FAILED; el proyecto nunca se carga a medias).
    version = data.get("format_version")
    if version is None or not isinstance(version, int):
        raise EngineError(ErrorCode.PROJECT_VERSION_UNSUPPORTED, {"version": version})
    if version > CURRENT_FORMAT_VERSION:
        raise EngineError(ErrorCode.PROJECT_VERSION_UNSUPPORTED, {"version": version})
    if version < CURRENT_FORMAT_VERSION:
        data = MIGRATIONS.apply(data, version, CURRENT_FORMAT_VERSION)

    # 2. Metadatos con valores por defecto tolerantes.
    meta = ProjectMeta(
        name=str(data.get("name") or "Untitled"),
        language=str(data.get("language") or "es"),
        camera=_camera_config(data.get("camera")),
        mode=str(data.get("flow", {}).get("mode") or "continuous"),
        interval_ms=int(data.get("flow", {}).get("interval_ms") or 100),
    )

    # 3. Bloques.
    graph = Graph()
    for item in data.get("blocks", []):
        node = Node(
            id=str(item["id"]),
            type=str(item["type"]),
            x=float(item.get("x", 0.0)),
            y=float(item.get("y", 0.0)),
            params=dict(item.get("params") or {}),
        )
        if graph.has_node(node.id):
            raise EngineError(ErrorCode.BLOCK_NOT_FOUND, {"node_id": node.id, "detail": "id duplicado"})
        graph.add_node(node)

    # 4. Conexiones.
    for item in data.get("connections", []):
        frm = item.get("from") or {}
        to = item.get("to") or {}
        edge = Edge(
            from_block=str(frm.get("block")),
            from_port=str(frm.get("port")),
            to_block=str(to.get("block")),
            to_port=str(to.get("port")),
        )
        graph.add_edge(edge)

    return graph, meta


def _camera_config(data: Any) -> CameraConfig:
    if not isinstance(data, dict):
        return CameraConfig()
    return CameraConfig(
        index=int(data.get("index") or 0),
        width=int(data.get("width") or 640),
        height=int(data.get("height") or 480),
    )