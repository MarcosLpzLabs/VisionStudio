"""Controlador de la aplicación: estado, proyecto y ejecución.

Es el punto único que usa la API. Mantiene el grafo actual, el pipeline en
ejecución y los metadatos del proyecto, y difunde por un `broadcaster` (el
WSManager) los resultados de los sinks, los cambios de estado y los errores.

No depende de FastAPI: es lógica pura y por tanto testeable directamente.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from visionstudio.api.encoding import frame_to_jpeg_base64
from visionstudio.blocks import BlockRegistry, registry as block_registry
from visionstudio.camera.device import CameraConfig
from visionstudio.camera.discovery import list_cameras as _list_cameras
from visionstudio.engine.executors import ExecutorRegistry
from visionstudio.engine.executors_cv import build_full_registry
from visionstudio.engine.graph import Graph
from visionstudio.engine.validation import GraphValidator
from visionstudio.errors import EngineError, ErrorCode
from visionstudio.persistence.project import (
    ProjectMeta,
    project_from_dict,
    project_to_dict,
)
from visionstudio.runloop import GraphPipeline, RunMode, RunState
from visionstudio.types import Value, ValueType

Broadcaster = Callable[[dict], None]


class AppController:
    """Estado de la aplicación y control de ejecución."""

    def __init__(
        self,
        capture_factory: Optional[Callable[[int], Any]] = None,
        registry: Optional[BlockRegistry] = None,
        executors: Optional[ExecutorRegistry] = None,
    ) -> None:
        self.registry = registry or block_registry
        # El factory de captura se inyecta en pruebas (cámaras falsas).
        self._capture_factory = capture_factory
        self.executors = executors or build_full_registry(capture_factory=capture_factory)

        self._graph = Graph()
        self._meta = ProjectMeta()
        self._pipeline: Optional[GraphPipeline] = None
        self._broadcaster: Optional[Broadcaster] = None

    # --- difusión ----------------------------------------------------------

    def set_broadcaster(self, broadcaster: Broadcaster) -> None:
        """Registra el difusor (WSManager.broadcast)."""
        self._broadcaster = broadcaster

    def _emit(self, message: dict) -> None:
        if self._broadcaster is not None:
            self._broadcaster(message)

    # --- catálogos ---------------------------------------------------------

    def list_cameras(self) -> list[dict]:
        """Cámaras detectadas (índice y nombre)."""
        cameras = _list_cameras(capture_factory=self._capture_factory)
        return [{"index": c.index, "name": c.name} for c in cameras]

    def block_catalog(self) -> dict[str, list[dict]]:
        """Bloques agrupados por categoría, para la biblioteca del frontend."""
        result: dict[str, list[dict]] = {}
        for category, specs in self.registry.categories().items():
            result[category] = [spec.model_dump() for spec in specs]
        return result

    # --- proyecto ----------------------------------------------------------

    def get_project(self) -> dict:
        """Proyecto actual serializado (formato v1)."""
        return project_to_dict(self._graph, self._meta)

    def load_project(self, data: dict) -> dict:
        """Carga un proyecto. Rechaza la edición si el flujo está en marcha."""
        if self.state != RunState.STOPPED:
            raise EngineError(ErrorCode.GRAPH_EDIT_WHILE_RUNNING, {})

        graph, meta = project_from_dict(data, self.registry)
        # Validación estructural completa antes de aceptar el proyecto.
        issues, _ = GraphValidator(self.registry).validate(graph)
        if issues:
            raise EngineError(issues[0].code, issues[0].params)

        # Sustituir el proyecto: cerrar el pipeline anterior (libera cámaras).
        self._discard_pipeline()
        self._graph = graph
        self._meta = meta
        return self.get_project()

    def _discard_pipeline(self) -> None:
        if self._pipeline is not None:
            self._pipeline.close()
            self._pipeline = None

    # --- estado y control --------------------------------------------------

    @property
    def state(self) -> RunState:
        if self._pipeline is None:
            return RunState.STOPPED
        return self._pipeline.state

    @property
    def last_error(self) -> Optional[Exception]:
        return self._pipeline.last_error if self._pipeline else None

    def _ensure_pipeline(self) -> GraphPipeline:
        """Crea el pipeline si no existe (o si se descartó tras cargar proyecto)."""
        if self._pipeline is None:
            try:
                mode = RunMode(self._meta.mode)
            except ValueError:
                mode = RunMode.CONTINUOUS
            self._pipeline = GraphPipeline(
                self._graph,
                executors=self.executors,
                registry=self.registry,
                mode=mode,
                interval_ms=self._meta.interval_ms,
                on_state_change=self._on_state,
                on_error=self._on_error,
                on_results=self._on_results,
            )
        return self._pipeline

    def start(self, mode: Optional[str] = None, interval_ms: Optional[int] = None) -> RunState:
        """Arranca el flujo, opcionalmente con modo/intervalo indicados."""
        pipeline = self._ensure_pipeline()
        if mode is not None:
            try:
                pipeline.runloop.set_mode(RunMode(mode))
            except ValueError:
                raise EngineError(ErrorCode.PARAM_INVALID, {"detail": f"modo desconocido: {mode}"})
        if interval_ms is not None:
            pipeline.runloop.set_interval_ms(interval_ms)
        pipeline.start()
        return self.state

    def stop(self) -> RunState:
        """Detiene el flujo y libera las cámaras (el pipeline se reutiliza)."""
        if self._pipeline is not None:
            self._pipeline.close()
        return RunState.STOPPED

    def pause(self) -> RunState:
        self._ensure_pipeline().pause()
        return self.state

    def resume(self) -> RunState:
        self._ensure_pipeline().resume()
        return self.state

    def step(self) -> RunState:
        """Ejecuta un único frame (manual)."""
        self._ensure_pipeline().step_once()
        return self.state

    # --- resultados --------------------------------------------------------

    def results(self) -> dict[str, dict[str, Any]]:
        """Últimos resultados de los sinks serializables (sin frames).

        Los frames van por WebSocket; aquí solo se exponen los valores JSON
        (número, texto, booleano, análisis...), útiles para el panel de estado.
        """
        if self._pipeline is None:
            return {}
        output: dict[str, dict[str, Any]] = {}
        for node_id, ports in self._pipeline.last_results().items():
            for port_id, value in ports.items():
                if value.is_frame():
                    continue
                output.setdefault(node_id, {})[port_id] = value.to_payload()
        return output

    # --- callbacks del pipeline -------------------------------------------

    def _on_state(self, state: RunState) -> None:
        self._emit({"type": "state", "state": state.value})

    def _on_error(self, exc: Exception) -> None:
        if isinstance(exc, EngineError):
            self._emit({"type": "error", "code": exc.code, "params": exc.params})
        else:
            self._emit({"type": "error", "code": ErrorCode.INTERNAL, "params": {"detail": str(exc)}})

    def _on_results(self, results: dict[str, dict[str, Value]]) -> None:
        for node_id, ports in results.items():
            for port_id, value in ports.items():
                message = self._sink_message(node_id, port_id, value)
                if message is not None:
                    self._emit(message)

    def _sink_message(self, node_id: str, port_id: str, value: Value) -> Optional[dict]:
        """Construye el mensaje WS de un sink según su bloque y tipo de dato."""
        block_type = ""
        try:
            block_type = self._graph.node(node_id).type
        except KeyError:
            pass

        # Frame: se codifica a JPEG/base64 (mensaje "frame").
        if value.type == ValueType.FRAME:
            return {"type": "frame", "sink": node_id, "port": port_id,
                    "data": frame_to_jpeg_base64(value.value)}

        # Mensajes por tipo de sink (contrato docs/CONTRATOS.md §6).
        if block_type == "block.sink_text":
            return {"type": "text", "sink": node_id, "port": port_id, "value": value.to_payload()}
        if block_type == "block.sink_boolean":
            return {"type": "boolean", "sink": node_id, "port": port_id, "value": value.to_payload()}
        if block_type == "block.status_indicator":
            return {"type": "status", "sink": node_id, "port": port_id, "value": value.to_payload()}

        # Fallback: mensaje por tipo de dato.
        type_map = {
            ValueType.NUMBER: "number",
            ValueType.BOOLEAN: "boolean",
            ValueType.STRING: "text",
            ValueType.COORDINATES: "coordinates",
            ValueType.RECTANGLE: "rectangle",
            ValueType.DETECTIONS: "detections",
            ValueType.ANALYSIS: "analysis",
        }
        message_type = type_map.get(value.type)
        if message_type is None:
            return None
        return {"type": message_type, "sink": node_id, "port": port_id, "value": value.to_payload()}