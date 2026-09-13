"""Tipos de datos del motor de VisionStudio.

Unión discriminada por el campo `type` (ver docs/CONTRATOS.md §1).
`frame` es una imagen OpenCV (numpy, BGR); no se serializa en proyectos.

Los valores que viajan entre puertos se envuelven en :class:`Value`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np


# ===========================================================================
# ValorType: identificadores estables de tipos
# ===========================================================================
# Son el "contrato" entre bloques, motor y frontend. Un puerto de salida emite
# un tipo y una entrada acepta uno o varios. Cambiar estos nombres rompería
# proyectos guardados y conexiones, por eso NUNCA se renombran.
# ===========================================================================
class ValueType:
    """Identificadores estables de los tipos de datos del sistema.

    La lista coincide con docs/CONTRATOS.md §1. No renombrar: son contrato.
    """

    FRAME = "frame"
    NUMBER = "number"
    BOOLEAN = "boolean"
    STRING = "string"
    COORDINATES = "coordinates"
    RECTANGLE = "rectangle"
    DETECTIONS = "detections"
    ANALYSIS = "analysis"
    TRIGGER = "trigger"  # señal interna de control (Timer/Manual); no es dato serializable

    # Todos los tipos conocidos. Se usa para validar que un Value nunca
    # transporte un tipo inexistente.
    ALL = (
        FRAME,
        NUMBER,
        BOOLEAN,
        STRING,
        COORDINATES,
        RECTANGLE,
        DETECTIONS,
        ANALYSIS,
        TRIGGER,
    )

    # Tipos que pueden transportarse como JSON (frame y trigger no).
    # frame requiere codificación JPEG/base64 en la capa de API; trigger solo
    # existe dentro del motor.
    SERIALIZABLE = (
        NUMBER,
        BOOLEAN,
        STRING,
        COORDINATES,
        RECTANGLE,
        DETECTIONS,
        ANALYSIS,
    )


# ===========================================================================
# Estructuras de valor
# ===========================================================================
# Cada estructura envuelve un valor concreto que viaja por un puerto. Son
# dataclasses simples (no pydantic) porque a veces contienen numpy (frames) y
# se serializan explícitamente cuando hace falta (método to_payload).
# ===========================================================================

@dataclass
class Coordinates:
    """Par de coordenadas (x, y)."""

    x: float
    y: float


@dataclass
class Rectangle:
    """Rectángulo con origen (x, y) y tamaño (width, height)."""

    x: float
    y: float
    width: float
    height: float


@dataclass
class Detection:
    """Detección: etiqueta, confianza y caja (x, y, w, h)."""

    label: str
    confidence: float
    x: float
    y: float
    width: float
    height: float


@dataclass
class Detections:
    """Lista de detecciones."""

    # field(default_factory=list) evita compartir una misma lista entre todas
    # las instancias (error clásico de Python con mutables en dataclasses).
    items: list[Detection] = field(default_factory=list)


@dataclass
class Analysis:
    """Resultado de análisis OK/NOK con detalle opcional."""

    ok: bool
    detail: Optional[str] = None


# ===========================================================================
# Value: valor que viaja por un puerto
# ===========================================================================
# Un Value es (type, value): el tipo discriminante y el dato en sí. El motor
# lo pasa de salida a entrada siguiendo las conexiones del grafo.
# ===========================================================================
@dataclass
class Value:
    """Valor que viaja por un puerto.

    `type` es uno de :data:`ValueType.ALL`. Para `frame`, `value` es un
    `numpy.ndarray` (BGR). Para `trigger`, `value` es un contador de evento.
    """

    type: str
    value: Any

    def __post_init__(self) -> None:
        # Validación en la creación: evita que tipos mal escritos (p. ej.
        # "Frame" o "frame2") circulen silenciosamente por el grafo y provoquen
        # fallos difíciles de depurar más adelante.
        if self.type not in ValueType.ALL:
            raise ValueError(f"tipo de valor desconocido: {self.type!r}")

    def is_frame(self) -> bool:
        # Atajo usado por el motor para saber si debe propagar una imagen.
        return self.type == ValueType.FRAME

    def to_payload(self) -> Any:
        """Representación JSON-serializable del valor.

        `frame` y `trigger` no son serializables aquí: el frame se codifica a
        JPEG/base64 en la capa de API; el trigger es interno al motor.
        """
        # Cada tipo serializa de forma distinta: los simples (número, texto,
        # booleano) tal cual, y los compuestos como diccionarios/listas.
        if self.type == ValueType.NUMBER:
            return float(self.value)
        if self.type == ValueType.BOOLEAN:
            return bool(self.value)
        if self.type == ValueType.STRING:
            return str(self.value)
        if self.type == ValueType.COORDINATES:
            c: Coordinates = self.value
            return {"x": c.x, "y": c.y}
        if self.type == ValueType.RECTANGLE:
            r: Rectangle = self.value
            return {"x": r.x, "y": r.y, "w": r.width, "h": r.height}
        if self.type == ValueType.DETECTIONS:
            d: Detections = self.value
            return [
                {
                    "label": it.label,
                    "confidence": it.confidence,
                    "x": it.x,
                    "y": it.y,
                    "w": it.width,
                    "h": it.height,
                }
                for it in d.items
            ]
        if self.type == ValueType.ANALYSIS:
            a: Analysis = self.value
            return {"ok": a.ok, "detail": a.detail}
        # Llegar aquí significa que el tipo es frame o trigger: no deben pedir
        # serialización, por eso se lanza error en vez de devolver algo raro.
        raise ValueError(f"el tipo {self.type!r} no es serializable a JSON")

    @staticmethod
    def from_payload(type_: str, payload: Any) -> "Value":
        """Reconstruye un Value serializable a partir de su payload JSON.

        Operación inversa de to_payload. Se usa para validar grafos/proyectos
        cargados sin ejecutar procesamiento (los frames nunca llegan aquí).
        """
        if type_ == ValueType.NUMBER:
            return Value(type_, float(payload))
        if type_ == ValueType.BOOLEAN:
            return Value(type_, bool(payload))
        if type_ == ValueType.STRING:
            return Value(type_, str(payload))
        if type_ == ValueType.COORDINATES:
            return Value(type_, Coordinates(payload["x"], payload["y"]))
        if type_ == ValueType.RECTANGLE:
            return Value(
                type_,
                Rectangle(payload["x"], payload["y"], payload["w"], payload["h"]),
            )
        if type_ == ValueType.DETECTIONS:
            return Value(
                type_,
                Detections(
                    [
                        Detection(
                            label=it["label"],
                            confidence=it["confidence"],
                            x=it["x"],
                            y=it["y"],
                            width=it["w"],
                            height=it["h"],
                        )
                        for it in payload
                    ]
                ),
            )
        if type_ == ValueType.ANALYSIS:
            return Value(
                type_, Analysis(ok=bool(payload["ok"]), detail=payload.get("detail"))
            )
        raise ValueError(f"el tipo {type_!r} no es deserializable desde JSON")


# ===========================================================================
# Helpers
# ===========================================================================

def frame_value(image: np.ndarray) -> Value:
    """Crea un Value de tipo frame a partir de una imagen OpenCV (BGR)."""
    # Función de conveniencia: oculta el detalle de construir Value a mano,
    # dejando claro que aquí solo entran imágenes OpenCV reales.
    return Value(ValueType.FRAME, image)


def compatible(output_type: str, accepted_types: tuple[str, ...]) -> bool:
    """Compatibilidad de conexión: ¿el tipo de salida cabe en el puerto de entrada?"""
    # Regla MVP: compatibilidad por tipo idéntico. Una salida `boolean` puede
    # conectarse a una entrada que acepte ("analysis", "boolean") porque basta
    # con que el tipo de salida esté dentro de los aceptados.
    return output_type in accepted_types