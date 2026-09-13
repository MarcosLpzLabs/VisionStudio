"""Pruebas end-to-end de Cámara, Escala de grises y Sink de imagen (fase 5).

Usan `FakeCaptureFactory` para no depender de hardware. Verifican el flujo
completo: camera -> grayscale -> sink_image, además de los ejecutores unitarios
y la integración con el pipeline (liberación de cámara al cerrar).
"""

import time

import numpy as np
import pytest

from visionstudio.engine.executors_cv import (
    CameraExecutor,
    GrayscaleExecutor,
    build_full_registry,
)
from visionstudio.engine.graph import Edge, Graph, Node
from visionstudio.errors import EngineError, ErrorCode
from visionstudio.runloop import GraphPipeline, RunMode
from visionstudio.types import frame_value
from tests.fakes import FakeCaptureFactory, synthetic_frame


def colored_frame(color=(10, 200, 100), height=40, width=60):
    """Frame BGR de color uniforme (para comprobar la escala de grises)."""
    return np.full((height, width, 3), color, dtype=np.uint8)


def graph_camara_grises_sink() -> Graph:
    # camera -> grayscale -> sink_image
    g = Graph()
    g.add_node(Node(id="cam", type="block.camera"))
    g.add_node(Node(id="gray", type="block.grayscale"))
    g.add_node(Node(id="sink", type="block.sink_image"))
    g.add_edge(Edge(from_block="cam", from_port="out", to_block="gray", to_port="in"))
    g.add_edge(Edge(from_block="gray", from_port="out", to_block="sink", to_port="in"))
    return g


def test_flujo_completo_camara_grises_sink():
    factory = FakeCaptureFactory(open_indices=[0], frames={0: [colored_frame()]})
    executors = build_full_registry(capture_factory=factory)
    pipeline = GraphPipeline(graph_camara_grises_sink(), executors=executors, mode=RunMode.MANUAL)

    # Paso manual (sin hilo): ejecuta una pasada síncrona.
    pipeline.step_once()

    value = pipeline.sink_value("sink", "in")
    assert value is not None and value.is_frame()
    frame = value.value
    # El frame de salida es BGR de 3 canales y en escala de grises (R==G==B).
    assert frame.shape == (40, 60, 3)
    assert np.all(frame[:, :, 0] == frame[:, :, 1])
    assert np.all(frame[:, :, 1] == frame[:, :, 2])

    # La cámara quedó abierta durante el paso; se libera al cerrar el pipeline.
    pipeline.close()
    assert factory.instance(0).released


def test_camera_executor_abre_y_reusa_dispositivo():
    factory = FakeCaptureFactory(open_indices=[0], frames={0: [synthetic_frame(), synthetic_frame()]})
    executor = CameraExecutor(capture_factory=factory)

    out1 = executor.execute({}, {"camera_index": 0, "width": 640, "height": 480})
    out2 = executor.execute({}, {"camera_index": 0, "width": 640, "height": 480})
    assert out1["out"].is_frame() and out2["out"].is_frame()

    capture = factory.instance(0)
    # Dos ejecuciones con la misma configuración: un único dispositivo, dos lecturas.
    assert len(factory.instances) == 1
    assert capture.read_count == 2

    executor.close()
    assert capture.released


def test_camera_executor_reabre_al_cambiar_indice():
    factory = FakeCaptureFactory(open_indices=[0, 1],
                                 frames={0: [synthetic_frame()], 1: [synthetic_frame()]})
    executor = CameraExecutor(capture_factory=factory)

    executor.execute({}, {"camera_index": 0, "width": 640, "height": 480})
    executor.execute({}, {"camera_index": 1, "width": 640, "height": 480})

    # Dos dispositivos distintos: al cambiar de cámara se cierra la anterior.
    assert len(factory.instances) == 2
    assert factory.instance(0).released

    executor.close()


def test_camera_executor_error_si_no_puede_abrir():
    factory = FakeCaptureFactory(open_indices=[])
    executor = CameraExecutor(capture_factory=factory)
    with pytest.raises(EngineError) as exc:
        executor.execute({}, {"camera_index": 0, "width": 640, "height": 480})
    assert exc.value.code == ErrorCode.CAMERA_OPEN


def test_camera_executor_error_sin_frames():
    factory = FakeCaptureFactory(open_indices=[0], frames={0: []})
    executor = CameraExecutor(capture_factory=factory)
    with pytest.raises(EngineError) as exc:
        executor.execute({}, {"camera_index": 0, "width": 640, "height": 480})
    assert exc.value.code == ErrorCode.CAMERA_OPEN
    executor.close()


def test_grayscale_executor_convierte_a_grises():
    executor = GrayscaleExecutor()
    frame = colored_frame(color=(10, 200, 100))

    out = executor.execute({"in": frame_value(frame)}, {})
    gray = out["out"].value
    assert gray.shape == (40, 60, 3)
    assert np.all((gray[:, :, 0] == gray[:, :, 1]) & (gray[:, :, 1] == gray[:, :, 2]))


def test_pipeline_continuo_ejecuta_varios_pasos_y_libera_camara():
    # Suficientes frames para varios pasos a 50 fps.
    frames = [colored_frame(color=(i, i, i)) for i in range(20)]
    factory = FakeCaptureFactory(open_indices=[0], frames={0: frames})
    executors = build_full_registry(capture_factory=factory)
    pipeline = GraphPipeline(graph_camara_grises_sink(), executors=executors,
                             mode=RunMode.CONTINUOUS, fps=50)

    pipeline.start()
    try:
        # Esperar a que el sink reciba al menos un frame.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and pipeline.sink_value("sink", "in") is None:
            time.sleep(0.005)
        assert pipeline.sink_value("sink", "in") is not None
    finally:
        pipeline.close()

    assert pipeline.state.value == "stopped"
    assert factory.instance(0).released


def test_pipeline_close_idempotente():
    factory = FakeCaptureFactory(open_indices=[0], frames={0: [synthetic_frame()]})
    executors = build_full_registry(capture_factory=factory)
    pipeline = GraphPipeline(graph_camara_grises_sink(), executors=executors, mode=RunMode.MANUAL)
    pipeline.step_once()
    pipeline.close()
    pipeline.close()  # segundo cierre: no debe fallar
    assert factory.instance(0).released