"""Fugas de recursos y liberación de cámaras (Quality, fase 11).

Comprueba que las cámaras se liberan en todos los caminos de detención:
ciclos start/stop, descarte del pipeline al cargar otro proyecto y cierre
idempotente. Usa cámaras falsas para inspeccionar el flag `released` sin
hardware real.
"""

from visionstudio.api.controller import AppController
from visionstudio.engine.executors_cv import build_full_registry
from visionstudio.engine.graph import Edge, Graph, Node
from visionstudio.errors import EngineError, ErrorCode
from visionstudio.runloop import GraphPipeline, RunMode
from tests.fakes import FakeCapture, FakeCaptureFactory, synthetic_frame


def frames(count=50):
    return [synthetic_frame(width=60, height=60) for _ in range(count)]


def graph_camara_sink() -> Graph:
    graph = Graph()
    graph.add_node(Node(id="cam", type="block.camera",
                        params={"camera_index": 0, "width": 60, "height": 60}))
    graph.add_node(Node(id="sink", type="block.sink_image"))
    graph.add_edge(Edge(from_block="cam", from_port="out", to_block="sink", to_port="in"))
    return graph


def proyecto_camara() -> dict:
    return {
        "format_version": 2,
        "name": "fugas",
        "language": "es",
        "camera": {"index": 0, "width": 60, "height": 60},
        "flow": {"mode": "manual", "interval_ms": 100},
        "blocks": [
            {"id": "cam", "type": "block.camera", "x": 0, "y": 0,
             "params": {"camera_index": 0, "width": 60, "height": 60}},
            {"id": "sink", "type": "block.sink_image", "x": 100, "y": 0, "params": {}},
        ],
        "connections": [
            {"from": {"block": "cam", "port": "out"}, "to": {"block": "sink", "port": "in"}},
        ],
    }


def proyecto_numerico() -> dict:
    return {
        "format_version": 2,
        "name": "numerico",
        "language": "es",
        "camera": {"index": 0, "width": 640, "height": 480},
        "flow": {"mode": "manual", "interval_ms": 100},
        "blocks": [
            {"id": "n1", "type": "block.numeric_value", "x": 0, "y": 0, "params": {"value": 1}},
            {"id": "c1", "type": "block.compare", "x": 100, "y": 0,
             "params": {"op": ">=", "reference": 0}},
            {"id": "s1", "type": "block.sink_boolean", "x": 200, "y": 0, "params": {}},
        ],
        "connections": [
            {"from": {"block": "n1", "port": "out"}, "to": {"block": "c1", "port": "in"}},
            {"from": {"block": "c1", "port": "out"}, "to": {"block": "s1", "port": "in"}},
        ],
    }


def test_ciclos_start_stop_liberan_todas_las_camaras():
    """Tras cada detención, ninguna instancia de cámara queda abierta."""
    factory = FakeCaptureFactory(open_indices=[0], frames={0: frames()})
    executors = build_full_registry(capture_factory=factory)
    pipeline = GraphPipeline(graph_camara_sink(), executors=executors, mode=RunMode.MANUAL)

    for _ in range(3):
        pipeline.step_once()  # abre (o reabre) la cámara
        assert any(not inst.released for inst in factory.instances)
        pipeline.close()  # libera
        assert all(inst.released for inst in factory.instances)

    # El número de instancias creadas es el de aperturas, no un crecimiento raro.
    assert len(factory.instances) == 3


def test_controller_stop_libera_la_camara():
    factory = FakeCaptureFactory(open_indices=[0], frames={0: frames()})
    controller = AppController(capture_factory=factory)
    controller.load_project(proyecto_camara())
    controller.step()

    capture = factory.instance(0)
    assert capture is not None and not capture.released
    controller.stop()
    assert capture.released


def test_cargar_otro_proyecto_libera_el_pipeline_anterior():
    """`load_project` descarta el pipeline: la cámara anterior se libera."""
    factory = FakeCaptureFactory(open_indices=[0], frames={0: frames()})
    controller = AppController(capture_factory=factory)
    controller.load_project(proyecto_camara())
    controller.step()
    capture = factory.instance(0)
    assert capture is not None and not capture.released

    # Cargar un proyecto sin cámara debe cerrar el pipeline (y su dispositivo).
    controller.load_project(proyecto_numerico())
    assert capture.released


def test_close_es_idempotente():
    factory = FakeCaptureFactory(open_indices=[0], frames={0: frames()})
    executors = build_full_registry(capture_factory=factory)
    pipeline = GraphPipeline(graph_camara_sink(), executors=executors, mode=RunMode.MANUAL)
    pipeline.step_once()
    pipeline.close()
    pipeline.close()  # segundo cierre: no debe fallar
    assert all(inst.released for inst in factory.instances)


def test_close_no_propaga_fallo_de_liberacion():
    """Un fallo del backend al liberar no debe tumbar la detención (BUG-003).

    Contrato: `ERR_CAMERA_RELEASE` "se registra y continúa". El pipeline debe
    informar por `on_error` y cerrar sin lanzar, liberando el resto.
    """
    errores: list[Exception] = []

    def factory(index):
        return FakeCapture(index=index, open_ok=True, frames=frames(), release_raises=True)

    executors = build_full_registry(capture_factory=factory)
    pipeline = GraphPipeline(
        graph_camara_sink(),
        executors=executors,
        mode=RunMode.MANUAL,
        on_error=errores.append,
    )
    pipeline.step_once()
    # No debe lanzar: la liberación fallida se registra/informa y la detención sigue.
    pipeline.close()
    # El fallo se informa con el código estable de liberación de cámara.
    assert len(errores) == 1
    assert isinstance(errores[0], EngineError)
    assert errores[0].code == ErrorCode.CAMERA_RELEASE
