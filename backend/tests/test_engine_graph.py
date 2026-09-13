"""Pruebas del modelo de grafo."""

import pytest

from visionstudio.engine.graph import Edge, Graph, Node


def build_graph() -> Graph:
    # Grafo válido de ejemplo: camera -> grayscale -> sink_image
    g = Graph()
    g.add_node(Node(id="n1", type="block.camera"))
    g.add_node(Node(id="n2", type="block.grayscale"))
    g.add_node(Node(id="n3", type="block.sink_image"))
    g.add_edge(Edge(from_block="n1", from_port="out", to_block="n2", to_port="in"))
    g.add_edge(Edge(from_block="n2", from_port="out", to_block="n3", to_port="in"))
    return g


def test_add_node_y_consulta():
    g = Graph()
    g.add_node(Node(id="a", type="block.camera", x=10, y=20, params={"camera_index": 1}))
    assert g.has_node("a")
    assert g.node("a").params["camera_index"] == 1
    assert g.node_ids() == ["a"]


def test_nodo_duplicado_rechazado():
    g = Graph()
    g.add_node(Node(id="a", type="block.camera"))
    with pytest.raises(ValueError):
        g.add_node(Node(id="a", type="block.grayscale"))


def test_node_desconocido_lanza_keyerror():
    g = Graph()
    with pytest.raises(KeyError):
        g.node("no_existe")


def test_incoming_outgoing():
    g = build_graph()
    assert [e.from_block for e in g.outgoing("n1")] == ["n1"]
    assert [e.from_block for e in g.incoming("n3")] == ["n2"]


def test_output_edges_de_puerto():
    g = build_graph()
    edges = g.output_edges("n1", "out")
    assert len(edges) == 1 and edges[0].to_block == "n2"


def test_remove_node_elimina_aristas():
    g = build_graph()
    g.remove_node("n2")
    assert not g.has_node("n2")
    # Ninguna arista referencia al nodo eliminado.
    assert all(e.from_block != "n2" and e.to_block != "n2" for e in g.edges)


def test_remove_edge():
    g = build_graph()
    edge = g.edges[0]
    g.remove_edge(edge)
    assert g.edges == [Edge(from_block="n2", from_port="out", to_block="n3", to_port="in")]


def test_serializacion_roundtrip():
    g = build_graph()
    data = g.model_dump()
    g2 = Graph.model_validate(data)
    assert g2 == g
    assert g2.node_ids() == g.node_ids()