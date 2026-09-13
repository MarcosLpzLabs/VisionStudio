"""Pruebas de integridad de cada bloque del MVP.

Una prueba por bloque, verificando el contrato de docs/CONTRATOS.md §3:
categoría, entradas, salidas, parámetros, comportamiento.
"""

import pytest

from visionstudio.blocks import registry
from visionstudio.blocks.specs import BlockSpec
from visionstudio.types import ValueType

FRAME = ValueType.FRAME
NUM = ValueType.NUMBER
BOOL = ValueType.BOOLEAN
STR = ValueType.STRING
COORD = ValueType.COORDINATES
RECT = ValueType.RECTANGLE
DET = ValueType.DETECTIONS
ANA = ValueType.ANALYSIS
TRG = ValueType.TRIGGER


def spec(block_id: str) -> BlockSpec:
    return registry.get(block_id)


def test_block_camera():
    s = spec("block.camera")
    assert s.category == "source"
    assert s.behavior == "on_tick"
    assert s.outputs[0].types == (FRAME,)
    assert {p.id for p in s.params} == {"camera_index", "width", "height"}
    assert s.param("camera_index").kind == "int"


def test_block_timer():
    s = spec("block.timer")
    assert s.category == "control"
    assert s.outputs[0].id == "tick" and s.outputs[0].types == (TRG,)
    assert s.param("interval_ms").default == 100
    assert s.param("interval_ms").min == 1


def test_block_manual_trigger():
    s = spec("block.manual_trigger")
    assert s.category == "control"
    assert s.behavior == "on_trigger"
    assert s.outputs[0].types == (TRG,)


def test_block_pause_resume():
    s = spec("block.pause_resume")
    assert s.category == "control"
    assert s.behavior == "passthrough"
    assert FRAME in s.inputs[0].types and FRAME in s.outputs[0].types


def test_block_grayscale():
    s = spec("block.grayscale")
    assert s.category == "processing"
    assert s.inputs[0].types == (FRAME,) and s.outputs[0].types == (FRAME,)


def test_block_black_white():
    s = spec("block.black_white")
    assert s.category == "processing"
    assert s.param("threshold").default == 127
    assert s.param("threshold").min == 0 and s.param("threshold").max == 255


def test_block_threshold():
    s = spec("block.threshold")
    assert s.category == "processing"
    assert s.param("max_value").default == 255
    assert "THRESH_BINARY" in s.param("type").options


def test_block_blur():
    s = spec("block.blur")
    assert s.category == "processing"
    assert s.param("kernel").min == 1
    assert s.param("kernel").default == 5


def test_block_edge_detection():
    s = spec("block.edge_detection")
    assert s.category == "processing"
    assert s.param("low").default == 100 and s.param("high").default == 200


def test_block_contours():
    s = spec("block.contours")
    assert s.category == "processing"
    assert s.outputs[0].id == "detections" and s.outputs[0].types == (DET,)
    assert s.outputs[1].types == (FRAME,)


def test_block_draw_text():
    s = spec("block.draw_text")
    assert s.category == "processing"
    assert s.param("text").type == "string"
    assert s.param("color").type == "color"


def test_block_ok_nok():
    s = spec("block.ok_nok")
    assert s.category == "analysis"
    assert set(s.inputs[0].types) == {ANA, BOOL}
    assert s.outputs[0].types == (ANA,)


def test_block_compare():
    s = spec("block.compare")
    assert s.category == "analysis"
    assert s.inputs[0].types == (NUM,)
    assert s.outputs[0].types == (BOOL,)
    assert s.param("op").default == ">="


def test_block_numeric_value():
    s = spec("block.numeric_value")
    assert s.category == "analysis"
    assert s.behavior == "continuous"
    assert s.outputs[0].types == (NUM,)


def test_block_coordinates():
    s = spec("block.coordinates")
    assert s.category == "analysis"
    assert s.outputs[0].types == (COORD,)


def test_block_rectangles():
    s = spec("block.rectangles")
    assert s.category == "analysis"
    assert s.outputs[0].types == (RECT,)
    assert {p.id for p in s.params} == {"x", "y", "w", "h"}


def test_block_detection_list():
    s = spec("block.detection_list")
    assert s.category == "analysis"
    assert s.outputs[0].types == (DET,)
    assert s.param("max_items").default == 10


def test_block_sink_image():
    s = spec("block.sink_image")
    assert s.category == "output"
    assert s.inputs[0].types == (FRAME,)
    assert s.outputs == ()


def test_block_sink_text():
    s = spec("block.sink_text")
    assert s.category == "output"
    assert s.inputs[0].types == (STR,)


def test_block_sink_boolean():
    s = spec("block.sink_boolean")
    assert s.category == "output"
    assert s.inputs[0].types == (BOOL,)


def test_block_status_indicator():
    s = spec("block.status_indicator")
    assert s.category == "output"
    assert set(s.inputs[0].types) == {ANA, BOOL}


def test_todos_los_bloques_tienen_especificacion_valida():
    for s in registry.all():
        assert s.id.startswith("block.")
        assert s.name_key.startswith("block.") and s.name_key.endswith(".name")
        assert s.description_key.endswith(".desc")
        assert s.category in {"source", "control", "processing", "analysis", "output"}