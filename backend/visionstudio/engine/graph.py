"""Modelo del grafo de bloques.

Un `Graph` es un DAG de `Node` (instancias de bloques) y `Edge` (conexiones
entre puerto de salida y puerto de entrada). Los modelos son pydantic para
poder serializarlos a JSON (persistencia, fase 9) con validación de tipos.

Identificadores de nodo: únicos dentro del grafo (los pone el frontend).
Identificadores de tipo: los del registro de bloques (block.camera, ...).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Node(BaseModel):
    """Instancia de un bloque dentro del grafo."""

    id: str  # id único del nodo (lo asigna el frontend)
    type: str  # tipo de bloque (id del registro, p. ej. "block.grayscale")
    x: float = 0.0  # posición en el lienzo (se guarda en el proyecto)
    y: float = 0.0
    params: dict[str, Any] = Field(default_factory=dict)  # parámetros del usuario


class Edge(BaseModel):
    """Conexión entre el puerto de salida de un nodo y el de entrada de otro."""

    from_block: str  # id del nodo origen
    from_port: str  # id del puerto de salida del origen
    to_block: str  # id del nodo destino
    to_port: str  # id del puerto de entrada del destino


class Graph(BaseModel):
    """Grafo completo de bloques y conexiones."""

    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)

    # --- consultas ---------------------------------------------------------

    def node_ids(self) -> list[str]:
        return [n.id for n in self.nodes]

    def has_node(self, node_id: str) -> bool:
        return any(n.id == node_id for n in self.nodes)

    def node(self, node_id: str) -> Node:
        """Devuelve el nodo o lanza KeyError (para detectar referencias rotas)."""
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(f"nodo {node_id!r} no existe en el grafo")

    def incoming(self, node_id: str) -> list[Edge]:
        """Aristas que entran al nodo."""
        return [e for e in self.edges if e.to_block == node_id]

    def outgoing(self, node_id: str) -> list[Edge]:
        """Aristas que salen del nodo."""
        return [e for e in self.edges if e.from_block == node_id]

    def output_edges(self, node_id: str, port_id: str) -> list[Edge]:
        """Aristas que salen de un puerto concreto del nodo."""
        return [e for e in self.edges if e.from_block == node_id and e.from_port == port_id]

    # --- mutaciones --------------------------------------------------------
    # Las mutaciones se usan al construir el grafo en el frontend/API. El
    # motor NO debe editar el grafo en ejecución (contrato: solo lectura).

    def add_node(self, node: Node) -> None:
        if self.has_node(node.id):
            raise ValueError(f"id de nodo duplicado: {node.id!r}")
        self.nodes.append(node)

    def add_edge(self, edge: Edge) -> None:
        self.edges.append(edge)

    def remove_node(self, node_id: str) -> None:
        """Elimina un nodo y sus aristas (las conexiones huérfanas no valen)."""
        self.nodes = [n for n in self.nodes if n.id != node_id]
        self.edges = [
            e
            for e in self.edges
            if e.from_block != node_id and e.to_block != node_id
        ]

    def remove_edge(self, edge: Edge) -> None:
        self.edges = [e for e in self.edges if e != edge]