"""Ejecutores de bloques (lógica pura, sin OpenCV).

Cada ejecutor implementa el comportamiento de un bloque: recibe las entradas
resueltas y los parámetros efectivos, y devuelve los valores de salida por
puerto.

En esta fase (3) solo se implementan los bloques de lógica pura. Los bloques
OpenCV (cámara, grises, threshold, blur, bordes, contornos, texto, detection_list)
se implementan en las fases 5 y 8.

Los ejecutores son SIN ESTADO en la medida de lo posible (los contadores de
trigger son la excepción).
"""

from __future__ import annotations

import operator
from typing import Any, Protocol

from visionstudio.blocks.registry import registry as block_registry
from visionstudio.engine.errors import EngineError, ErrorCode
from visionstudio.types import (
    Analysis,
    Coordinates,
    Rectangle,
    Value,
    ValueType,
)


class BlockExecutor(Protocol):
    """Contrato de un ejecutor de bloque."""

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        """Ejecuta el bloque.

        - `inputs`: valores recibidos por cada puerto de entrada conectado.
        - `params`: parámetros efectivos (por defecto + los del usuario).
        - Devuelve: dict puerto_de_salida -> Value.
        """
        ...


class _NumericValue:
    """Fuente de número: emite el valor configurado."""

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        return {"out": Value(ValueType.NUMBER, float(params["value"]))}


class _Coordinates:
    """Fuente de coordenadas: emite el punto configurado."""

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        return {
            "out": Value(
                ValueType.COORDINATES,
                Coordinates(float(params["x"]), float(params["y"])),
            )
        }


class _Compare:
    """Compara la entrada numérica con una referencia usando el operador `op`."""

    # Mapeo operador de parámetro -> función Python. El operador `in` no debe
    # usarse aquí; así evitamos inyección de código arbitrario por parámetro.
    _OPS = {
        "==": operator.eq,
        "!=": operator.ne,
        "<": operator.lt,
        "<=": operator.le,
        ">": operator.gt,
        ">=": operator.ge,
    }

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        value = float(inputs["in"].value)
        reference = float(params["reference"])
        op = params["op"]
        try:
            result = self._OPS[op](value, reference)
        except KeyError:
            # Operador desconocido: fallo de configuración, no de datos.
            raise EngineError(ErrorCode.PARAM_INVALID, {"detail": f"operador no soportado: {op}"})
        return {"out": Value(ValueType.BOOLEAN, result)}


class _OkNok:
    """Normaliza boolean/analysis a un resultado de análisis OK/NOK."""

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        incoming = inputs["in"]
        if incoming.type == ValueType.ANALYSIS:
            # Ya es un analysis: se pasa tal cual.
            return {"out": incoming}
        # Booleano simple -> analysis(ok=bool).
        return {"out": Value(ValueType.ANALYSIS, Analysis(ok=bool(incoming.value)))}


class _PauseResume:
    """Puerta de datos: deja pasar el valor entrante.

    El pausado en sí lo gestiona el runloop (fase 4) saltándose la ejecución
    mientras está pausado; este bloque solo reexpone la semántica de puerta en
    el grafo.
    """

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        return {"out": inputs["in"]}


class _Rectangles:
    """Emite un rectángulo.

    Si llegan detecciones, usa la primera; si no, los parámetros manuales.
    """

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        detections = inputs.get("detections")
        if detections is not None and detections.value.items:
            first = detections.value.items[0]
            rect = Rectangle(first.x, first.y, first.width, first.height)
        else:
            rect = Rectangle(
                float(params["x"]), float(params["y"]),
                float(params["w"]), float(params["h"]),
            )
        return {"out": Value(ValueType.RECTANGLE, rect)}


class _Timer:
    """Emite un tick de trigger por cada ejecución del grafo.

    El ritmo (intervalo) lo impone el runloop en fase 4; aquí solo se genera la
    señal. El contador da identidad a cada evento de trigger.
    """

    def __init__(self) -> None:
        self._counter = 0

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        self._counter += 1
        return {"tick": Value(ValueType.TRIGGER, self._counter)}


class _ManualTrigger:
    """Emite un tick por petición explícita (ejecución manual de un frame)."""

    def __init__(self) -> None:
        self._counter = 0

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        self._counter += 1
        return {"tick": Value(ValueType.TRIGGER, self._counter)}


class _Sink:
    """Sink genérico: no tiene salidas; sus entradas las recoge el runner.

    El runner registra el valor recibido como resultado del nodo sumidero, y la
    capa de API lo publica por WebSocket (fase 6).
    """

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        return {}


class ExecutorRegistry:
    """Registro de ejecutores por id de bloque."""

    def __init__(self) -> None:
        self._executors: dict[str, BlockExecutor] = {}

    def register(self, block_id: str, executor: BlockExecutor) -> None:
        # Un bloque que se registra dos veces es un bug de registro: fallar ya.
        if block_id in self._executors:
            raise ValueError(f"ejecutor duplicado para {block_id!r}")
        self._executors[block_id] = executor

    def get(self, block_id: str) -> Optional[BlockExecutor]:
        return self._executors.get(block_id)

    def implemented(self) -> set[str]:
        return set(self._executors)

    def has(self, block_id: str) -> bool:
        return block_id in self._executors


def build_default_registry() -> ExecutorRegistry:
    """Construye el registro de ejecutores con los bloques de lógica pura.

    Los bloques con comportamiento OpenCV (cámara, procesamiento de imagen)
    se añadirán en fases posteriores: aquí quedan registrados pero SIN ejecutor,
    de modo que ejecutarlos lanza ERR_BLOCK_EXECUTION de forma clara.
    """
    reg = ExecutorRegistry()
    # Análisis / control / salidas (lógica pura).
    reg.register("block.numeric_value", _NumericValue())
    reg.register("block.coordinates", _Coordinates())
    reg.register("block.compare", _Compare())
    reg.register("block.ok_nok", _OkNok())
    reg.register("block.pause_resume", _PauseResume())
    reg.register("block.rectangles", _Rectangles())
    reg.register("block.timer", _Timer())
    reg.register("block.manual_trigger", _ManualTrigger())
    # Sinks: recogen sus entradas como resultados.
    reg.register("block.sink_image", _Sink())
    reg.register("block.sink_text", _Sink())
    reg.register("block.sink_boolean", _Sink())
    reg.register("block.status_indicator", _Sink())
    # Los bloques OpenCV se registran sin ejecutor -> se detectan al ejecutar.
    for block_id in (
        "block.camera",
        "block.grayscale",
        "block.black_white",
        "block.threshold",
        "block.blur",
        "block.edge_detection",
        "block.contours",
        "block.draw_text",
        "block.detection_list",
    ):
        assert block_registry.has(block_id), f"bloque desconocido: {block_id}"
    return reg


# Registro global compartido por todo el sistema (runner, pruebas, API).
default_executors = build_default_registry()