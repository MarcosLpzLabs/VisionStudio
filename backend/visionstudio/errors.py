"""Errores transversales del sistema.

Cada error tiene un código ESTABLE (contrato con el frontend) y parámetros
serializables. El frontend traduce el código y formatea con los parámetros.

Este módulo es transversal a todas las capas (motor, cámara, API,
persistencia) para evitar dependencias cruzadas. Los códigos coinciden con
docs/CONTRATOS.md §4.
"""

from __future__ import annotations

from typing import Any, Optional


class ErrorCode:
    """Códigos de error estables. No renombrar: son contrato con el frontend."""

    # Cámara
    CAMERA_OPEN = "ERR_CAMERA_OPEN"
    CAMERA_RELEASE = "ERR_CAMERA_RELEASE"
    # Grafo / conexiones
    CONNECTION_TYPE = "ERR_CONNECTION_TYPE"
    GRAPH_CYCLE = "ERR_GRAPH_CYCLE"
    GRAPH_EDIT_WHILE_RUNNING = "ERR_GRAPH_EDIT_WHILE_RUNNING"
    BLOCK_NOT_FOUND = "ERR_BLOCK_NOT_FOUND"
    PORT_NOT_FOUND = "ERR_PORT_NOT_FOUND"
    PORT_ALREADY_CONNECTED = "ERR_PORT_ALREADY_CONNECTED"
    BLOCK_INPUT_MISSING = "ERR_BLOCK_INPUT_MISSING"
    # Parámetros / ejecución
    PARAM_INVALID = "ERR_PARAM_INVALID"
    BLOCK_EXECUTION = "ERR_BLOCK_EXECUTION"
    COMMAND_UNKNOWN = "ERR_COMMAND_UNKNOWN"  # comando WS/REST no reconocido
    # Persistencia
    PROJECT_VERSION_UNSUPPORTED = "ERR_PROJECT_VERSION_UNSUPPORTED"
    MIGRATION_FAILED = "ERR_MIGRATION_FAILED"
    # Genérico
    INTERNAL = "ERR_INTERNAL"


class EngineError(Exception):
    """Excepción del sistema con código y parámetros para el frontend.

    Se mantiene el nombre `EngineError` por compatibilidad; representa cualquier
    error controlado del backend (no solo del motor).
    """

    def __init__(self, code: str, params: Optional[dict[str, Any]] = None) -> None:
        self.code = code
        self.params: dict[str, Any] = params or {}
        super().__init__(code)

    def to_dict(self) -> dict[str, Any]:
        """Representación JSON-serializable para la API/WebSocket."""
        return {"code": self.code, "params": self.params}