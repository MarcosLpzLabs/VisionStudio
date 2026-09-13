"""Pruebas de los tipos de datos del motor."""

import pytest

from visionstudio.types import (
    Analysis,
    Coordinates,
    Detection,
    Detections,
    Rectangle,
    Value,
    ValueType,
    compatible,
    frame_value,
)


def test_value_rechaza_tipo_desconocido():
    with pytest.raises(ValueError):
        Value("no_existe", None)


def test_frame_value():
    import numpy as np

    img = np.zeros((10, 10, 3), dtype=np.uint8)
    v = frame_value(img)
    assert v.type == ValueType.FRAME
    assert v.is_frame()


def test_to_payload_numero():
    assert Value(ValueType.NUMBER, 3.5).to_payload() == 3.5


def test_to_payload_booleano():
    assert Value(ValueType.BOOLEAN, True).to_payload() is True


def test_to_payload_texto():
    assert Value(ValueType.STRING, "hola").to_payload() == "hola"


def test_to_payload_coordenadas():
    assert Value(ValueType.COORDINATES, Coordinates(1.0, 2.0)).to_payload() == {"x": 1.0, "y": 2.0}


def test_to_payload_rectangulo():
    assert Value(ValueType.RECTANGLE, Rectangle(1, 2, 3, 4)).to_payload() == {"x": 1, "y": 2, "w": 3, "h": 4}


def test_to_payload_detecciones():
    d = Detections([Detection(label="a", confidence=0.9, x=0, y=0, width=1, height=1)])
    assert Value(ValueType.DETECTIONS, d).to_payload() == [
        {"label": "a", "confidence": 0.9, "x": 0, "y": 0, "w": 1, "h": 1}
    ]


def test_to_payload_analysis():
    a = Analysis(ok=False, detail="bajo")
    assert Value(ValueType.ANALYSIS, a).to_payload() == {"ok": False, "detail": "bajo"}


def test_to_payload_rechaza_frame_y_trigger():
    import numpy as np

    with pytest.raises(ValueError):
        frame_value(np.zeros((2, 2, 3), dtype=np.uint8)).to_payload()
    with pytest.raises(ValueError):
        Value(ValueType.TRIGGER, 1).to_payload()


@pytest.mark.parametrize(
    "type_,payload",
    [
        (ValueType.NUMBER, 1.0),
        (ValueType.BOOLEAN, False),
        (ValueType.STRING, "x"),
        (ValueType.COORDINATES, {"x": 1, "y": 2}),
        (ValueType.RECTANGLE, {"x": 1, "y": 2, "w": 3, "h": 4}),
        (ValueType.DETECTIONS, [{"label": "a", "confidence": 1.0, "x": 0, "y": 0, "w": 1, "h": 1}]),
        (ValueType.ANALYSIS, {"ok": True, "detail": None}),
    ],
)
def test_roundtrip_payload(type_, payload):
    v = Value.from_payload(type_, payload)
    assert v.type == type_
    assert v.to_payload() == payload


def test_compatible():
    assert compatible(ValueType.FRAME, (ValueType.FRAME,))
    assert not compatible(ValueType.FRAME, (ValueType.NUMBER,))
    assert compatible(ValueType.BOOLEAN, (ValueType.ANALYSIS, ValueType.BOOLEAN))