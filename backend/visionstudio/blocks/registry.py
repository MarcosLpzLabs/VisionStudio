"""Registro central de bloques.

Ofrece acceso a las especificaciones, validación de parámetros y
compatibilidad de conexiones. Los identificadores son estables.
"""

from __future__ import annotations

from typing import Any, Optional

from visionstudio.blocks.specs import ALL_BLOCKS, BlockSpec, Category, ParamSpec
from visionstudio.types import compatible


class BlockRegistry:
    """Registro inmutable de bloques del sistema."""

    def __init__(self, specs: tuple[BlockSpec, ...] = ALL_BLOCKS) -> None:
        self._specs: dict[str, BlockSpec] = {}
        # Índice por id. El `dict` mantiene el orden de inserción, por eso la
        # tupla ALL_BLOCKS define también el orden de presentación.
        for spec in specs:
            if spec.id in self._specs:
                # Detectar ids duplicados al arrancar evita bugs de registro
                # difíciles de rastrear (dos bloques con el mismo id).
                raise ValueError(f"identificador de bloque duplicado: {spec.id!r}")
            self._specs[spec.id] = spec

    def get(self, block_id: str) -> BlockSpec:
        """Devuelve la especificación del bloque o lanza KeyError."""
        return self._specs[block_id]

    def has(self, block_id: str) -> bool:
        return block_id in self._specs

    def all(self) -> tuple[BlockSpec, ...]:
        return tuple(self._specs.values())

    def categories(self) -> dict[Category, list[BlockSpec]]:
        """Bloques agrupados por categoría, en orden de definición."""
        result: dict[Category, list[BlockSpec]] = {}
        for spec in self._specs.values():
            # setdefault crea la lista la primera vez que aparece la categoría.
            result.setdefault(spec.category, []).append(spec)
        return result

    def port_types(self, block_id: str, port_id: str) -> tuple[str, ...]:
        """Tipos del puerto de un bloque."""
        # Delegado a BlockSpec.port, que lanza KeyError si el puerto no existe.
        return self.get(block_id).port(port_id).types

    def compatible(self, from_type: str, to_block: str, to_port: str) -> bool:
        """¿Puede conectarse un valor de tipo `from_type` al puerto destino?"""
        # Se usa al validar el grafo: el tipo emitido por una salida debe ser
        # aceptado por la entrada destino.
        accepted = self.port_types(to_block, to_port)
        return compatible(from_type, accepted)

    def default_params(self, block_id: str) -> dict[str, Any]:
        """Parámetros por defecto del bloque (JSON-serializables)."""
        spec = self.get(block_id)
        # _json_safe convierte tuplas (color) a listas para que el JSON de
        # proyectos no contenga estructuras no estándar.
        return {p.id: _json_safe(p.default) for p in spec.params}

    def validate_params(self, block_id: str, params: dict[str, Any]) -> Optional[str]:
        """Valida parámetros de un bloque.

        Devuelve `None` si son válidos o, en caso contrario, un mensaje de error
        que incluye el id del parámetro culpable (para traducir en el frontend).

        Formato de error: "param_<motivo>:<block_id>:<param_id>[:detalle]".

        Se validan los parámetros EFECTIVOS: los no provistos se completan con
        sus valores por defecto. Así, un nodo que solo guarda los parámetros
        modificados por el usuario sigue siendo válido (el runner aplica los
        defaults al ejecutar).
        """
        spec = self.get(block_id)
        # 1) Rechazar parámetros que no existen en la especificación (typos).
        known = {p.id for p in spec.params}
        for key in params:
            if key not in known:
                return f"param_unknown:{block_id}:{key}"

        # 2) Completar con defaults y validar rango/tipo de cada valor efectivo.
        effective = {**self.default_params(block_id), **params}
        for p in spec.params:
            value = effective[p.id]
            if value is None:
                continue
            error = _validate_value(p, value)
            if error is not None:
                return f"param_invalid:{block_id}:{p.id}:{error}"
        return None


# ===========================================================================
# Validación de un valor concreto contra su ParamSpec
# ===========================================================================

def _validate_value(p: ParamSpec, value: Any) -> Optional[str]:
    """Valida `value` contra las reglas del parámetro `p`.

    Devuelve None si es válido o una clave corta de motivo (p. ej. "below_min").
    El frontend traduce estas claves.
    """
    if p.type == "number":
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "not_a_number"
        # kind="int" exige que el valor sea entero (1.5 en camera_index es error).
        if p.kind == "int" and float(value).is_integer() is False:
            return "not_an_integer"
        if p.min is not None and number < p.min:
            return f"below_min:{p.min}"
        if p.max is not None and number > p.max:
            return f"above_max:{p.max}"
        return None

    if p.type == "boolean":
        # isinstance evita que 0/1/"" pasen como booleanos (True == 1 en Python).
        if not isinstance(value, bool):
            return "not_a_boolean"
        return None

    if p.type == "string":
        if not isinstance(value, str):
            return "not_a_string"
        return None

    if p.type == "select":
        if value not in p.options:
            return "not_an_option"
        return None

    if p.type == "color":
        if not _valid_color(value):
            return "not_a_color"
        return None

    # Llegar aquí significa un type de parámetro no manejado: fallo de
    # definición, no de datos.
    return "unsupported_param_type"


def _valid_color(value: Any) -> bool:
    """Acepta tuplas/listas BGR (3 enteros 0-255) o string "r,g,b"."""
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return all(isinstance(c, int) and 0 <= c <= 255 for c in value)
    if isinstance(value, str):
        # Formato alternativo del frontend (inputs de color en HTML).
        parts = value.split(",")
        if len(parts) != 3:
            return False
        try:
            return all(0 <= int(c) <= 255 for c in parts)
        except ValueError:
            return False
    return False


def _json_safe(value: Any) -> Any:
    """Convierte tuplas (p. ej. color) a listas para JSON."""
    if isinstance(value, tuple):
        return list(value)
    return value


# Instancia global: el registro único usado por todo el sistema. Se exporta
# desde visionstudio.blocks para que motor, API y pruebas compartan la misma
# instancia (y eviten configuraciones divergentes).
registry = BlockRegistry()