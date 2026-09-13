"""Validación del grafo y orden topológico.

Reglas de validación (docs/CONTRATOS.md §5 y §6):
1. Los tipos de bloque deben existir en el registro.
2. Los parámetros de cada nodo deben ser válidos.
3. Las aristas deben referenciar nodos y puertos existentes.
4. Los tipos de los puertos conectados deben ser compatibles.
5. Un puerto de entrada solo admite una conexión.
6. Las entradas requeridas deben estar conectadas.
7. El grafo no puede contener ciclos (debe ser un DAG).

La validación es ESTRUCTURAL: no ejecuta bloques ni comprueba la existencia de
ejecutores (eso es responsabilidad del runner).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from visionstudio.blocks import BlockRegistry
from visionstudio.engine.errors import ErrorCode
from visionstudio.engine.graph import Graph
from visionstudio.types import compatible


@dataclass
class Issue:
    """Un problema detectado en la validación."""

    code: str  # código estable (ErrorCode)
    params: dict = field(default_factory=dict)  # contexto para el frontend

    def to_dict(self) -> dict:
        return {"code": self.code, "params": self.params}


class GraphValidator:
    """Valida la estructura de un grafo y calcula el orden de ejecución."""

    def __init__(self, registry: BlockRegistry) -> None:
        self.registry = registry

    def validate(self, graph: Graph) -> tuple[list[Issue], Optional[list[str]]]:
        """Devuelve (issues, orden_topologico).

        Si `issues` no está vacío, `orden_topologico` es None (no se ejecuta un
        grafo inválido). El orden es una lista de ids de nodo (topológico).
        """
        issues: list[Issue] = []

        # 1. Tipos de bloque existentes.
        for n in graph.nodes:
            if not self.registry.has(n.type):
                issues.append(
                    Issue(ErrorCode.BLOCK_NOT_FOUND, {"node_id": n.id, "block_type": n.type})
                )
        if issues:
            # Sin tipos válidos no tiene sentido seguir validando puertos.
            return issues, None

        # 2. Parámetros válidos (rangos, selects, colores, tipos).
        for n in graph.nodes:
            err = self.registry.validate_params(n.type, n.params)
            if err is not None:
                issues.append(Issue(ErrorCode.PARAM_INVALID, {"node_id": n.id, "detail": err}))

        # 3/4. Aristas: nodos y puertos existentes + compatibilidad de tipos.
        for e in graph.edges:
            src = self._find_node(graph, e.from_block)
            dst = self._find_node(graph, e.to_block)
            if src is None:
                issues.append(Issue(ErrorCode.BLOCK_NOT_FOUND, {"node_id": e.from_block}))
                continue
            if dst is None:
                issues.append(Issue(ErrorCode.BLOCK_NOT_FOUND, {"node_id": e.to_block}))
                continue
            # Puertos existentes (port() lanza KeyError si no).
            try:
                out_types = self.registry.get(src.type).port(e.from_port).types
                in_types = self.registry.get(dst.type).port(e.to_port).types
            except KeyError:
                issues.append(
                    Issue(
                        ErrorCode.PORT_NOT_FOUND,
                        {"from_block": e.from_block, "from_port": e.from_port,
                         "to_block": e.to_block, "to_port": e.to_port},
                    )
                )
                continue
            # Compatibilidad: intersección no vacía entre tipos emitidos y aceptados.
            if not compatible_set(out_types, in_types):
                issues.append(
                    Issue(
                        ErrorCode.CONNECTION_TYPE,
                        {"from_block": e.from_block, "from_port": e.from_port,
                         "to_block": e.to_block, "to_port": e.to_port,
                         "from_types": list(out_types), "to_types": list(in_types)},
                    )
                )

        # 5. Una sola conexión por puerto de entrada.
        seen: set[tuple[str, str]] = set()
        for e in graph.edges:
            key = (e.to_block, e.to_port)
            if key in seen:
                issues.append(
                    Issue(
                        ErrorCode.PORT_ALREADY_CONNECTED,
                        {"node_id": e.to_block, "port_id": e.to_port},
                    )
                )
            seen.add(key)

        # 6. Entradas requeridas conectadas.
        for n in graph.nodes:
            spec = self.registry.get(n.type)
            connected = {e.to_port for e in graph.incoming(n.id)}
            for port in spec.inputs:
                if port.required and port.id not in connected:
                    issues.append(
                        Issue(ErrorCode.BLOCK_INPUT_MISSING, {"node_id": n.id, "port_id": port.id})
                    )

        if issues:
            return issues, None

        # 7. Ciclos y orden topológico (Kahn).
        order = self._topological_order(graph)
        if order is None:
            # Hay al menos un ciclo: el grafo no es ejecutable.
            issues.append(Issue(ErrorCode.GRAPH_CYCLE, {}))
            return issues, None
        return issues, order

    # --- helpers -----------------------------------------------------------

    @staticmethod
    def _find_node(graph: Graph, node_id: str):
        """Devuelve el nodo o None (sin lanzar, para acumular issues)."""
        for n in graph.nodes:
            if n.id == node_id:
                return n
        return None

    def _topological_order(self, graph: Graph) -> Optional[list[str]]:
        """Orden topológico por algoritmo de Kahn. None si hay ciclo."""
        indegree: dict[str, int] = {n.id: 0 for n in graph.nodes}
        # lista de adyacencia: salida -> destinos
        adjacency: dict[str, list[str]] = {n.id: [] for n in graph.nodes}
        for e in graph.edges:
            indegree[e.to_block] += 1
            adjacency[e.from_block].append(e.to_block)

        queue = deque(n.id for n in graph.nodes if indegree[n.id] == 0)
        order: list[str] = []
        while queue:
            node_id = queue.popleft()
            order.append(node_id)
            for dst in adjacency[node_id]:
                indegree[dst] -= 1
                if indegree[dst] == 0:
                    queue.append(dst)

        if len(order) != len(graph.nodes):
            # Quedan nodos con indegree > 0: forman al menos un ciclo.
            return None
        return order


def compatible_set(from_types: tuple[str, ...], to_types: tuple[str, ...]) -> bool:
    """Compatibilidad entre CONJUNTOS de tipos emitidos y aceptados.

    Basta con que algún tipo emitido sea aceptado (intersección no vacía).
    """
    return any(t in to_types for t in from_types)