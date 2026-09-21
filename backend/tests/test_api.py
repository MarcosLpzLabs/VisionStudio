"""Pruebas de integración de la API REST y WebSocket.

Se inyecta un controlador con cámaras falsas (`FakeCaptureFactory`) y se
comprueban los contratos de docs/CONTRATOS.md §6 y §7: proyecto, control de
ejecución, estados, resultados y mensajes WebSocket.
"""

import base64
import importlib

import pytest
from fastapi.testclient import TestClient

from visionstudio.api.controller import AppController
from visionstudio.persistence.project import CURRENT_FORMAT_VERSION
from tests.fakes import FakeCaptureFactory, synthetic_frame

# Módulo real de la app (importlib evita el sombreado del atributo `app`,
# que es la instancia FastAPI y no el submódulo).
app_module = importlib.import_module("visionstudio.api.app")


@pytest.fixture
def client():
    """Cliente con un controlador fresco (cámaras falsas), aislado por test."""
    factory = FakeCaptureFactory(open_indices=[0], frames={0: [synthetic_frame()]})
    test_controller = AppController(capture_factory=factory)
    test_controller.set_broadcaster(app_module.manager.broadcast)
    original = app_module.controller
    app_module.controller = test_controller
    try:
        with TestClient(app_module.app) as test_client:
            yield test_client, test_controller
    finally:
        app_module.controller = original


def proyecto_numerico() -> dict:
    """Proyecto válido: numeric_value -> compare -> sink_boolean."""
    return {
        "format_version": 1,
        "name": "demo",
        "language": "es",
        "camera": {"index": 0, "width": 640, "height": 480},
        "flow": {"mode": "manual", "interval_ms": 100},
        "blocks": [
            {"id": "n1", "type": "block.numeric_value", "x": 0, "y": 0, "params": {"value": 10}},
            {"id": "c1", "type": "block.compare", "x": 100, "y": 0, "params": {"op": ">=", "reference": 5}},
            {"id": "s1", "type": "block.sink_boolean", "x": 200, "y": 0, "params": {}},
        ],
        "connections": [
            {"from": {"block": "n1", "port": "out"}, "to": {"block": "c1", "port": "in"}},
            {"from": {"block": "c1", "port": "out"}, "to": {"block": "s1", "port": "in"}},
        ],
    }


def proyecto_camara() -> dict:
    """Proyecto con cámara -> grises -> sink imagen."""
    return {
        "format_version": 1,
        "name": "cam",
        "language": "es",
        "camera": {"index": 0, "width": 640, "height": 480},
        "flow": {"mode": "manual", "interval_ms": 100},
        "blocks": [
            {"id": "cam", "type": "block.camera", "x": 0, "y": 0,
             "params": {"camera_index": 0, "width": 640, "height": 480}},
            {"id": "gray", "type": "block.grayscale", "x": 100, "y": 0, "params": {}},
            {"id": "sink", "type": "block.sink_image", "x": 200, "y": 0, "params": {}},
        ],
        "connections": [
            {"from": {"block": "cam", "port": "out"}, "to": {"block": "gray", "port": "in"}},
            {"from": {"block": "gray", "port": "out"}, "to": {"block": "sink", "port": "in"}},
        ],
    }


def test_health(client):
    test_client, _ = client
    response = test_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_catalogo_bloques(client):
    test_client, _ = client
    categories = test_client.get("/api/blocks").json()["categories"]
    assert set(categories) == {"source", "control", "processing", "analysis", "output"}
    total = sum(len(specs) for specs in categories.values())
    assert total == 21


def test_camaras_detectadas_con_fake(client):
    test_client, _ = client
    cameras = test_client.get("/api/cameras").json()["cameras"]
    assert [c["index"] for c in cameras] == [0]


def test_proyecto_roundtrip(client):
    test_client, _ = client
    assert test_client.put("/api/project", json=proyecto_numerico()).status_code == 200
    project = test_client.get("/api/project").json()
    # El guardado usa SIEMPRE la versión actual del backend (los v1 se migran).
    assert project["format_version"] == CURRENT_FORMAT_VERSION
    assert len(project["blocks"]) == 3
    assert len(project["connections"]) == 2


def test_proyecto_con_conexion_incompatible_rechazado(client):
    test_client, _ = client
    data = proyecto_numerico()
    # number -> number: la conexión n1.out (number) a c1.in (number) es válida;
    # forzamos una inválida conectando number a un puerto que pide frame.
    data["blocks"].append({"id": "g", "type": "block.grayscale", "x": 0, "y": 0, "params": {}})
    data["connections"].append({"from": {"block": "n1", "port": "out"}, "to": {"block": "g", "port": "in"}})
    response = test_client.put("/api/project", json=data)
    assert response.status_code == 400
    assert response.json()["code"] == "ERR_CONNECTION_TYPE"


def test_proyecto_version_mayor_rechazado(client):
    test_client, _ = client
    data = proyecto_numerico()
    data["format_version"] = 99
    response = test_client.put("/api/project", json=data)
    assert response.status_code == 400
    assert response.json()["code"] == "ERR_PROJECT_VERSION_UNSUPPORTED"


def test_paso_manual_produce_resultado(client):
    test_client, _ = client
    test_client.put("/api/project", json=proyecto_numerico())
    assert test_client.post("/api/run/step").json()["state"] == "stopped"

    results = test_client.get("/api/results").json()["results"]
    assert results["s1"]["in"] is True  # 10 >= 5


def test_ciclo_de_vida_start_pause_resume_stop(client):
    test_client, _ = client
    test_client.put("/api/project", json=proyecto_numerico())

    assert test_client.post("/api/run/start").json()["state"] == "running"
    assert test_client.post("/api/run/pause").json()["state"] == "paused"
    assert test_client.post("/api/run/resume").json()["state"] == "running"
    assert test_client.post("/api/run/stop").json()["state"] == "stopped"


def test_no_se_edita_proyecto_en_ejecucion(client):
    test_client, _ = client
    test_client.put("/api/project", json=proyecto_numerico())
    test_client.post("/api/run/start")
    try:
        response = test_client.put("/api/project", json=proyecto_numerico())
        assert response.status_code == 400
        assert response.json()["code"] == "ERR_GRAPH_EDIT_WHILE_RUNNING"
    finally:
        test_client.post("/api/run/stop")


def test_modo_desconocido_rechazado(client):
    test_client, _ = client
    test_client.put("/api/project", json=proyecto_numerico())
    response = test_client.post("/api/run/start", json={"mode": "inexistente"})
    assert response.status_code == 400
    assert response.json()["code"] == "ERR_PARAM_INVALID"


def test_ws_paso_manual_emite_sink_booleano(client):
    test_client, _ = client
    test_client.put("/api/project", json=proyecto_numerico())
    with test_client.websocket_connect("/ws") as ws:
        # Mensaje inicial de estado.
        assert ws.receive_json()["type"] == "state"

        ws.send_json({"command": "step"})
        received = False
        for _ in range(5):
            message = ws.receive_json()
            if message.get("type") == "boolean":
                assert message["sink"] == "s1"
                assert message["value"] is True
                received = True
                break
        assert received


def test_ws_frame_imagen_emitido(client):
    test_client, _ = client
    test_client.put("/api/project", json=proyecto_camara())
    with test_client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "state"

        ws.send_json({"command": "step"})
        received = False
        for _ in range(5):
            message = ws.receive_json()
            if message.get("type") == "frame":
                assert message["sink"] == "sink"
                data = message["data"]
                assert data  # base64 no vacío
                # Debe decodificar como JPEG válido.
                raw = base64.b64decode(data)
                assert raw[:2] == b"\xff\xd8"  # firma JPEG
                received = True
                break
        assert received


def test_ws_comando_desconocido_envia_error(client):
    test_client, _ = client
    with test_client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "state"
        ws.send_json({"command": "volar"})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "ERR_COMMAND_UNKNOWN"