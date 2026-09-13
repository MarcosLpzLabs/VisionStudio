"""Pruebas del runner: ejecución de grafos por propagación topológica."""

import pytest

from visionstudio.engine.errors import EngineError, ErrorCode
from visionstudio.engine.graph import Edge, Graph, Node
from visionstudio.engine.runner import GraphRunner
from visionstudio.types import Analysis, Coordinates, Rectangle, Value, ValueType


def run(graph: Graph):
    """Atajo: ejecuta una pasada y devuelve los resultados de sinks."""
    runner = GraphRunner(graph)
    return runner.run_one()


def test_flujo_numerico_basico():
    # numeric_value(10) -> compare(>=5) -> sink_boolean => True
    g = Graph()
    g.add_node(Node(id="n1", type="block.numeric_value", params={"value": 10}))
    g.add_node(Node(id="c1", type="block.compare", params={"op": ">=", "reference": 5}))
    g.add_node(Node(id="s1", type="block.sink_boolean"))
    g.add_edge(Edge(from_block="n1", from_port="out", to_block="c1", to_port="in"))
    g.add_edge(Edge(from_block="c1", from_port="out", to_block="s1", to_port="in"))

    results = run(g)
    value = results["s1"]["in"]
    assert value.type == ValueType.BOOLEAN and value.value is True


def test_comparacion_con_operador_menor():
    g = Graph()
    g.add_node(Node(id="n1", type="block.numeric_value", params={"value": 3}))
    g.add_node(Node(id="c1", type="block.compare", params={"op": "<", "reference": 5}))
    g.add_node(Node(id="s1", type="block.sink_boolean"))
    g.add_edge(Edge(from_block="n1", from_port="out", to_block="c1", to_port="in"))
    g.add_edge(Edge(from_block="c1", from_port="out", to_block="s1", to_port="in"))

    results = run(g)
    assert results["s1"]["in"].value is True


def test_sink_value_helper():
    # El helper devuelve el valor recibido por un sink en la última pasada.
    g = Graph()
    g.add_node(Node(id="n1", type="block.numeric_value", params={"value": 42}))
    g.add_node(Node(id="c1", type="block.compare", params={"op": ">=", "reference": 0}))
    g.add_node(Node(id="s1", type="block.sink_boolean"))
    g.add_edge(Edge(from_block="n1", from_port="out", to_block="c1", to_port="in"))
    g.add_edge(Edge(from_block="c1", from_port="out", to_block="s1", to_port="in"))
    runner = GraphRunner(g)
    runner.run_one()
    assert runner.sink_value("s1", "in").value is True


def test_ok_nok_normaliza_booleano():
    # numeric_value(0) -> compare(>=5) -> ok_nok -> status_indicator
    g = Graph()
    g.add_node(Node(id="n1", type="block.numeric_value", params={"value": 0}))
    g.add_node(Node(id="c1", type="block.compare", params={"op": ">=", "reference": 5}))
    g.add_node(Node(id="ok", type="block.ok_nok"))
    g.add_node(Node(id="st", type="block.status_indicator"))
    g.add_edge(Edge(from_block="n1", from_port="out", to_block="c1", to_port="in"))
    g.add_edge(Edge(from_block="c1", from_port="out", to_block="ok", to_port="in"))
    g.add_edge(Edge(from_block="ok", from_port="out", to_block="st", to_port="in"))

    results = run(g)
    analysis = results["st"]["in"]
    assert analysis.type == ValueType.ANALYSIS
    assert analysis.value.ok is False  # 0 >= 5 es falso


def test_coordenadas_y_rectangulo_manual():
    # numeric_value -> coordinates es incompatible; el rectángulo manual se
    # comprueba con el ejecutor directo (sin detecciones conectadas).
    from visionstudio.engine.executors import _Rectangles

    exec_ = _Rectangles()
    out = exec_.execute({}, {"x": 1, "y": 2, "w": 30, "h": 40})
    assert out["out"].value == Rectangle(1, 2, 30, 40)


def test_rectangulo_desde_detecciones():
    from visionstudio.engine.executors import _Rectangles
    from visionstudio.types import Detection, Detections

    exec_ = _Rectangles()
    dets = Detections([Detection(label="a", confidence=0.9, x=5, y=6, width=7, height=8)])
    out = exec_.execute({"detections": Value(ValueType.DETECTIONS, dets)}, {})
    assert out["out"].value == Rectangle(5, 6, 7, 8)


def test_puerta_pause_resume_pasa_valor():
    g = Graph()
    g.add_node(Node(id="n1", type="block.numeric_value", params={"value": 7}))
    g.add_node(Node(id="p1", type="block.pause_resume"))
    g.add_node(Node(id="c1", type="block.compare", params={"op": "==", "reference": 7}))
    g.add_node(Node(id="s1", type="block.sink_boolean"))
    g.add_edge(Edge(from_block="n1", from_port="out", to_block="p1", to_port="in"))
    g.add_edge(Edge(from_block="p1", from_port="out", to_block="c1", to_port="in"))
    g.add_edge(Edge(from_block="c1", from_port="out", to_block="s1", to_port="in"))

    results = run(g)
    assert results["s1"]["in"].value is True


def test_timer_emite_trigger():
    g = Graph()
    g.add_node(Node(id="t1", type="block.timer"))
    g.add_node(Node(id="cam", type="block.camera"))
    g.add_edge(Edge(from_block="t1", from_port="tick", to_block="cam", to_port="trigger"))
    # camera no tiene ejecutor en fase 3 -> ERR_BLOCK_EXECUTION.
    with pytest.raises(EngineError) as exc:
        run(g)
    assert exc.value.code == ErrorCode.BLOCK_EXECUTION


def test_bloque_sin_ejecutor_lanza_error():
    # grayscale no tiene ejecutor en fase 3.
    g = Graph()
    g.add_node(Node(id="n1", type="block.camera"))
    g.add_node(Node(id="n2", type="block.grayscale"))
    g.add_edge(Edge(from_block="n1", from_port="out", to_block="n2", to_port="in"))
    with pytest.raises(EngineError) as exc:
        run(g)
    assert exc.value.code == ErrorCode.BLOCK_EXECUTION


def test_grafo_invalido_lanza_error_de_validacion():
    # compare sin entrada requerida conectada.
    g = Graph()
    g.add_node(Node(id="c1", type="block.compare"))
    with pytest.raises(EngineError) as exc:
        run(g)
    assert exc.value.code == ErrorCode.BLOCK_INPUT_MISSING


def test_excepcion_de_ejecutor_se_envuelve_con_contexto():
    # compare con operador desconocido -> el ejecutor lanza PARAM_INVALID.
    g = Graph()
    g.add_node(Node(id="n1", type="block.numeric_value", params={"value": 1}))
    g.add_node(Node(id="c1", type="block.compare", params={"op": "??", "reference": 0}))
    g.add_node(Node(id="s1", type="block.sink_boolean"))
    g.add_edge(Edge(from_block="n1", from_port="out", to_block="c1", to_port="in"))
    g.add_edge(Edge(from_block="c1", from_port="out", to_block="s1", to_port="in"))
    with pytest.raises(EngineError) as exc:
        run(g)
    assert exc.value.code == ErrorCode.PARAM_INVALID


def test_fuente_que_no_produce_lanza_error():
    # dos numeric_value, uno no conectado al otro... construir caso: arista a un
    # puerto que el origen no emite (from_port inexistente en la salida).
    g = Graph()
    g.add_node(Node(id="n1", type="block.numeric_value", params={"value": 1}))
    g.add_node(Node(id="s1", type="block.sink_boolean"))
    # La arista refiere a un puerto "other" que numeric_value no emite.
    g.add_edge(Edge(from_block="n1", from_port="other", to_block="s1", to_port="in"))
    with pytest.raises(EngineError) as exc:
        run(g)
    # El validador debe detectar el puerto inexistente primero.
    assert exc.value.code == ErrorCode.PORT_NOT_FOUND


def test_grafo_sin_sinks_devuelve_vacio():
    g = Graph()
    g.add_node(Node(id="n1", type="block.numeric_value", params={"value": 1}))
    g.add_node(Node(id="c1", type="block.compare"))
    g.add_edge(Edge(from_block="n1", from_port="out", to_block="c1", to_port="in"))
    results = run(g)
    assert results == {}