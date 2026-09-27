"""Compatibilidad de proyectos antiguos (Quality, fase 11).

Comprueba que un proyecto v1 real (bloques sin `width`/`height`) se carga por
la API, se migra a la versión actual (v2) con tamaño automático (`null`) y
conserva intactos sus bloques y conexiones. También verifica que la migración
no muta el diccionario original y que los tamaños de un v2 se respetan.
"""

import copy

from visionstudio.api.controller import AppController
from visionstudio.persistence.project import CURRENT_FORMAT_VERSION
from tests.fakes import FakeCaptureFactory


def proyecto_v1() -> dict:
    """Proyecto antiguo (v1): numeric_value -> compare -> sink_boolean."""
    return {
        "format_version": 1,
        "name": "antiguo",
        "language": "es",
        "camera": {"index": 0, "width": 640, "height": 480},
        "flow": {"mode": "manual", "interval_ms": 100},
        "blocks": [
            {"id": "n1", "type": "block.numeric_value", "x": 0, "y": 0, "params": {"value": 7}},
            {"id": "c1", "type": "block.compare", "x": 100, "y": 0,
             "params": {"op": ">=", "reference": 5}},
            {"id": "s1", "type": "block.sink_boolean", "x": 200, "y": 0, "params": {}},
        ],
        "connections": [
            {"from": {"block": "n1", "port": "out"}, "to": {"block": "c1", "port": "in"}},
            {"from": {"block": "c1", "port": "out"}, "to": {"block": "s1", "port": "in"}},
        ],
    }


def test_proyecto_v1_migra_a_v2_con_tamano_automatico():
    controller = AppController(capture_factory=FakeCaptureFactory(open_indices=[0]))
    guardado = controller.load_project(proyecto_v1())

    assert guardado["format_version"] == CURRENT_FORMAT_VERSION
    # La migración añade width/height como null (tamaño automático).
    assert all(b["width"] is None and b["height"] is None for b in guardado["blocks"])
    # Bloques y conexiones se conservan.
    assert [b["id"] for b in guardado["blocks"]] == ["n1", "c1", "s1"]
    assert len(guardado["connections"]) == 2
    # `GET /api/project` devuelve exactamente lo cargado (sin migrar dos veces).
    assert controller.get_project() == guardado


def test_migracion_no_muta_el_dict_original():
    data = proyecto_v1()
    snapshot = copy.deepcopy(data)
    controller = AppController(capture_factory=FakeCaptureFactory(open_indices=[0]))
    controller.load_project(data)
    # La migración es pura: el diccionario recibido no debe cambiar.
    assert data == snapshot


def test_proyecto_v2_con_tamanos_los_conserva():
    data = proyecto_v1()
    data["format_version"] = 2
    data["blocks"][0]["width"] = 260
    data["blocks"][0]["height"] = 140

    controller = AppController(capture_factory=FakeCaptureFactory(open_indices=[0]))
    guardado = controller.load_project(data)
    primero = guardado["blocks"][0]
    assert (primero["width"], primero["height"]) == (260, 140)
