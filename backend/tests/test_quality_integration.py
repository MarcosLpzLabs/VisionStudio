"""Pruebas de integración de Quality (fase 11): flujo end-to-end.

Verifica que el pipeline completo (cámara falsa -> procesamiento -> sink)
produce resultados válidos en cada pasada, que los mensajes de sink se
codifican correctamente (frame -> JPEG/base64) y que el orden topológico
respeta las dependencias. No usa hardware real: la cámara se inyecta con
`FakeCaptureFactory`.
"""

import base64
import importlib

import numpy as np
from fastapi.testclient import TestClient

from visionstudio.api.controller import AppController
from visionstudio.engine.graph import Edge, Graph, Node
from visionstudio.engine.runner import GraphRunner
from tests.fakes import FakeCaptureFactory, synthetic_frame

# Módulo real de la app (importlib evita el sombreado del atributo `app`).
app_module = importlib.import_module("visionstudio.api.app")


def many_frames(count=400, height=60, width=60):
    """Cola de frames sintéticos suficiente para varias pasadas de un flujo."""
    return [synthetic_frame(width=width, height=height) for _ in range(count)]


def proyecto_camara_contornos() -> dict:
    """Proyecto válido v2: cámara -> grises -> umbral -> contornos -> sink."""
    return {
        "format_version": 2,
        "name": "calidad-camara",
        "language": "es",
        "camera": {"index": 0, "width": 60, "height": 60},
        "flow": {"mode": "manual", "interval_ms": 100},
        "blocks": [
            {"id": "cam", "type": "block.camera", "x": 0, "y": 0,
             "params": {"camera_index": 0, "width": 60, "height": 60}},
            {"id": "gray", "type": "block.grayscale", "x": 100, "y": 0, "params": {}},
            {"id": "thr", "type": "block.threshold", "x": 200, "y": 0,
             "params": {"threshold": 10, "max_value": 255, "type": "THRESH_BINARY"}},
            {"id": "cnt", "type": "block.contours", "x": 300, "y": 0, "params": {}},
            {"id": "sink", "type": "block.sink_image", "x": 400, "y": 0, "params": {}},
        ],
        "connections": [
            {"from": {"block": "cam", "port": "out"}, "to": {"block": "gray", "port": "in"}},
            {"from": {"block": "gray", "port": "out"}, "to": {"block": "thr", "port": "in"}},
            {"from": {"block": "thr", "port": "out"}, "to": {"block": "cnt", "port": "in"}},
            {"from": {"block": "cnt", "port": "out"}, "to": {"block": "sink", "port": "in"}},
        ],
    }


def test_flujo_completo_emite_frames_jpeg_por_paso():
    """Cada paso manual produce un frame de sink codificable como JPEG."""
    factory = FakeCaptureFactory(open_indices=[0], frames={0: many_frames()})
    controller = AppController(capture_factory=factory)
    mensajes: list[dict] = []
    controller.set_broadcaster(mensajes.append)

    controller.load_project(proyecto_camara_contornos())
    for _ in range(3):
        controller.step()

    frames = [m for m in mensajes if m.get("type") == "frame" and m.get("sink") == "sink"]
    assert len(frames) >= 3
    for message in frames:
        raw = base64.b64decode(message["data"])
        # Firma JPEG: todo frame debe ser una imagen válida para el navegador.
        assert raw[:2] == b"\xff\xd8"
    controller.stop()


def test_orden_topologico_respeta_dependencias():
    """El runner ejecuta las fuentes antes que sus consumidores."""
    graph = Graph()
    graph.add_node(Node(id="n1", type="block.numeric_value", params={"value": 7}))
    graph.add_node(Node(id="c1", type="block.compare", params={"op": ">=", "reference": 5}))
    graph.add_node(Node(id="s1", type="block.sink_boolean"))
    graph.add_edge(Edge(from_block="n1", from_port="out", to_block="c1", to_port="in"))
    graph.add_edge(Edge(from_block="c1", from_port="out", to_block="s1", to_port="in"))

    runner = GraphRunner(graph)
    order = runner.validate()
    assert order.index("n1") < order.index("c1") < order.index("s1")

    results = runner.run_one()
    assert results["s1"]["in"].value is True


def test_pipeline_encadena_salida_detecciones_y_frame():
    """Contornos expone `detections` y `out`; el sink recibe el frame."""
    from visionstudio.engine.executors_cv import build_full_registry
    from visionstudio.runloop import GraphPipeline, RunMode

    # Frame con un cuadrado blanco: debe generar al menos un contorno.
    frame = np.zeros((60, 60, 3), dtype=np.uint8)
    frame[15:45, 15:45, :] = 255
    factory = FakeCaptureFactory(open_indices=[0], frames={0: [frame]})
    executors = build_full_registry(capture_factory=factory)

    graph = Graph()
    graph.add_node(Node(id="cam", type="block.camera",
                        params={"camera_index": 0, "width": 60, "height": 60}))
    graph.add_node(Node(id="gray", type="block.grayscale"))
    graph.add_node(Node(id="cnt", type="block.contours"))
    graph.add_node(Node(id="sink", type="block.sink_image"))
    graph.add_edge(Edge(from_block="cam", from_port="out", to_block="gray", to_port="in"))
    graph.add_edge(Edge(from_block="gray", from_port="out", to_block="cnt", to_port="in"))
    graph.add_edge(Edge(from_block="cnt", from_port="out", to_block="sink", to_port="in"))

    pipeline = GraphPipeline(graph, executors=executors, mode=RunMode.MANUAL)
    pipeline.step_once()
    value = pipeline.sink_value("sink", "in")
    assert value is not None and value.is_frame()
    assert value.value.shape == (60, 60, 3)
    pipeline.close()


def test_ws_stream_continuo_emite_varios_frames():
    """En modo temporizado, el WebSocket recibe varios frames seguidos."""
    factory = FakeCaptureFactory(open_indices=[0], frames={0: many_frames(count=2000)})
    test_controller = AppController(capture_factory=factory)
    test_controller.set_broadcaster(app_module.manager.broadcast)
    original = app_module.controller
    app_module.controller = test_controller
    try:
        with TestClient(app_module.app) as client:
            client.put("/api/project", json=proyecto_camara_contornos())
            with client.websocket_connect("/ws") as ws:
                assert ws.receive_json()["type"] == "state"
                # Cadencia rápida (10 ms) para no alargar la prueba.
                ws.send_json({"command": "start", "mode": "timer", "interval_ms": 10})
                frames = 0
                for _ in range(80):
                    message = ws.receive_json()
                    if message.get("type") == "frame":
                        frames += 1
                        if frames >= 2:
                            break
                ws.send_json({"command": "stop"})
                assert frames >= 2
    finally:
        app_module.controller = original
