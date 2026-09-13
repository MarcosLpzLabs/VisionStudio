"""Pruebas de validación del grafo (estructura, tipos, ciclos, orden topológico)."""

from visionstudio.engine.errors import ErrorCode
from visionstudio.engine.graph import Edge, Graph, Node
from visionstudio.engine.validation import GraphValidator
from visionstudio.blocks import registry


def validate(graph: Graph):
    """Atajo: devuelve las issues de validación."""
    validator = GraphValidator(registry)
    issues, order = validator.validate(graph)
    return issues, order


def graph_valido_basico() -> Graph:
    # numeric_value -> compare -> sink_boolean (todo lógica pura, ejecutable)
    g = Graph()
    g.add_node(Node(id="n1", type="block.numeric_value", params={"value": 10}))
    g.add_node(Node(id="n2", type="block.compare", params={"op": ">=", "reference": 5}))
    g.add_node(Node(id="n3", type="block.sink_boolean"))
    g.add_edge(Edge(from_block="n1", from_port="out", to_block="n2", to_port="in"))
    g.add_edge(Edge(from_block="n2", from_port="out", to_block="n3", to_port="in"))
    return g


def test_grafo_valido_sin_issues_y_orden():
    issues, order = validate(graph_valido_basico())
    assert issues == []
    assert order == ["n1", "n2", "n3"]


def test_bloque_desconocido():
    g = Graph()
    g.add_node(Node(id="a", type="block.no_existe"))
    issues, order = validate(g)
    assert issues and issues[0].code == ErrorCode.BLOCK_NOT_FOUND
    assert order is None


def test_parametro_invalido():
    g = Graph()
    g.add_node(Node(id="a", type="block.blur", params={"kernel": 0}))  # min=1
    issues, _ = validate(g)
    assert issues and issues[0].code == ErrorCode.PARAM_INVALID


def test_puerto_desconocido():
    g = graph_valido_basico()
    g.add_edge(Edge(from_block="n1", from_port="out", to_block="n2", to_port="no_existe"))
    issues, order = validate(g)
    assert any(i.code == ErrorCode.PORT_NOT_FOUND for i in issues)
    assert order is None


def test_tipos_incompatibles():
    g = Graph()
    # numeric_value (number) -> grayscale (frame): incompatibles.
    g.add_node(Node(id="n1", type="block.numeric_value"))
    g.add_node(Node(id="n2", type="block.grayscale"))
    g.add_edge(Edge(from_block="n1", from_port="out", to_block="n2", to_port="in"))
    issues, order = validate(g)
    assert any(i.code == ErrorCode.CONNECTION_TYPE for i in issues)
    assert order is None


def test_puerto_entrada_conectado_dos_veces():
    g = Graph()
    g.add_node(Node(id="n1", type="block.numeric_value"))
    g.add_node(Node(id="n2", type="block.numeric_value"))
    g.add_node(Node(id="s", type="block.sink_boolean"))
    # Dos fuentes intentan conectar la misma entrada del sink (tipos ok: number->boolean NO).
    # Usamos compare como puente: number -> compare.in
    c = Node(id="c", type="block.compare")
    g.add_node(c)
    g.add_edge(Edge(from_block="n1", from_port="out", to_block="c", to_port="in"))
    g.add_edge(Edge(from_block="n2", from_port="out", to_block="c", to_port="in"))
    issues, order = validate(g)
    assert any(i.code == ErrorCode.PORT_ALREADY_CONNECTED for i in issues)
    assert order is None


def test_entrada_requerida_sin_conectar():
    g = Graph()
    # compare exige "in"; no se conecta nada.
    g.add_node(Node(id="c", type="block.compare"))
    issues, order = validate(g)
    assert any(i.code == ErrorCode.BLOCK_INPUT_MISSING for i in issues)
    assert order is None


def test_ciclo_detectado():
    # pause_resume admite cualquier tipo, por lo que un ciclo entre dos puertas
    # es compatible por tipo y debe detectarse por estructura.
    g = Graph()
    g.add_node(Node(id="p1", type="block.pause_resume"))
    g.add_node(Node(id="p2", type="block.pause_resume"))
    g.add_edge(Edge(from_block="p1", from_port="out", to_block="p2", to_port="in"))
    g.add_edge(Edge(from_block="p2", from_port="out", to_block="p1", to_port="in"))
    issues, order = validate(g)
    assert any(i.code == ErrorCode.GRAPH_CYCLE for i in issues)
    assert order is None


def test_orden_topologico_diamante():
    # Una fuente alimenta dos comparadores y cada uno un sink: orden respeta deps.
    g = Graph()
    g.add_node(Node(id="n1", type="block.numeric_value"))
    g.add_node(Node(id="c1", type="block.compare"))
    g.add_node(Node(id="c2", type="block.compare"))
    g.add_node(Node(id="s1", type="block.sink_boolean"))
    g.add_node(Node(id="s2", type="block.sink_boolean"))
    g.add_edge(Edge(from_block="n1", from_port="out", to_block="c1", to_port="in"))
    g.add_edge(Edge(from_block="n1", from_port="out", to_block="c2", to_port="in"))
    g.add_edge(Edge(from_block="c1", from_port="out", to_block="s1", to_port="in"))
    g.add_edge(Edge(from_block="c2", from_port="out", to_block="s2", to_port="in"))
    issues, order = validate(g)
    assert issues == []
    # n1 debe ir antes que c1/c2, y c1/c2 antes de s1/s2.
    assert order.index("n1") < order.index("c1")
    assert order.index("n1") < order.index("c2")
    assert order.index("c1") < order.index("s1")
    assert order.index("c2") < order.index("s2")


def test_trigger_opcional_de_camara():
    # timer -> camera.trigger es válido (trigger opcional no exige conexión).
    g = Graph()
    g.add_node(Node(id="t", type="block.timer"))
    g.add_node(Node(id="cam", type="block.camera"))
    g.add_edge(Edge(from_block="t", from_port="tick", to_block="cam", to_port="trigger"))
    issues, order = validate(g)
    assert issues == []
    assert order == ["t", "cam"]