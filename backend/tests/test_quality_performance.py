"""Pruebas de referencia de rendimiento (Quality, fase 11).

No son benchmarks estrictos: fijan umbrales HOLGADOS para detectar regresiones
groseras sin volverse inestables en máquinas lentas. Se mide la latencia de una
pasada de lógica pura, la cadencia del modo continuo con cámara falsa y que los
resultados no crezcan entre pasadas.
"""

import time

from visionstudio.engine.executors_cv import build_full_registry
from visionstudio.engine.graph import Edge, Graph, Node
from visionstudio.engine.runner import GraphRunner
from visionstudio.runloop import GraphPipeline, RunMode
from tests.fakes import FakeCaptureFactory, synthetic_frame


def graph_numerico() -> Graph:
    graph = Graph()
    graph.add_node(Node(id="n1", type="block.numeric_value", params={"value": 7}))
    graph.add_node(Node(id="c1", type="block.compare", params={"op": ">=", "reference": 5}))
    graph.add_node(Node(id="s1", type="block.sink_boolean"))
    graph.add_edge(Edge(from_block="n1", from_port="out", to_block="c1", to_port="in"))
    graph.add_edge(Edge(from_block="c1", from_port="out", to_block="s1", to_port="in"))
    return graph


def graph_camara_sink() -> Graph:
    graph = Graph()
    graph.add_node(Node(id="cam", type="block.camera",
                        params={"camera_index": 0, "width": 60, "height": 60}))
    graph.add_node(Node(id="sink", type="block.sink_image"))
    graph.add_edge(Edge(from_block="cam", from_port="out", to_block="sink", to_port="in"))
    return graph


def test_pasada_de_logica_pura_es_rapida():
    """200 pasadas de un grafo numérico deben completarse con holgura."""
    runner = GraphRunner(graph_numerico())
    runner.run_one()  # calentamiento (imports/validación en frío)

    pasadas = 200
    inicio = time.perf_counter()
    for _ in range(pasadas):
        runner.run_one()
    transcurrido = time.perf_counter() - inicio

    # Umbral muy holgado (~10 ms/pasada de margen): solo detecta regresiones.
    assert transcurrido < 2.0


def test_modo_continuo_produce_varios_frames():
    """Con cámara falsa y 120 FPS, en 0.3 s deben salir varios frames."""
    factory = FakeCaptureFactory(
        open_indices=[0], frames={0: [synthetic_frame(width=60, height=60) for _ in range(2000)]}
    )
    executors = build_full_registry(capture_factory=factory)

    pasos = {"n": 0}

    def on_results(_results):
        pasos["n"] += 1

    pipeline = GraphPipeline(
        graph_camara_sink(),
        executors=executors,
        mode=RunMode.CONTINUOUS,
        fps=120.0,
        on_results=on_results,
    )
    pipeline.start()
    time.sleep(0.3)
    pipeline.stop()
    pipeline.close()

    # A 120 FPS cabrían ~36 pasos; exigir 5 evita falsos negativos por carga.
    assert pasos["n"] >= 5


def test_resultados_no_crecen_entre_pasadas():
    """El número de sinks con resultado se mantiene estable pasada tras pasada."""
    runner = GraphRunner(graph_numerico())
    runner.run_one()
    tamano_inicial = len(runner.last_results())

    for _ in range(100):
        runner.run_one()

    # No debe acumularse estado: mismas claves y mismos sinks.
    assert len(runner.last_results()) == tamano_inicial == 1
    assert set(runner.last_results()) == {"s1"}
