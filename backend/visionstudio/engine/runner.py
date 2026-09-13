"""Runner: ejecución del grafo por propagación topológica.

Una pasada (`run_one`) ejecuta los nodos en orden topológico:
1. Un nodo de origen produce sus salidas (ejecutor sin entradas conectadas).
2. Cada nodo posterior consume las salidas de sus predecesores vía aristas.
3. Los nodos sin salidas (sinks) registran los valores recibidos como resultado.

El runner valida el grafo antes de ejecutar. Un grafo inválido o un bloque sin
ejecutor lanzan EngineError con código estable. El runner NO edita el grafo
(contrato: solo lectura durante la ejecución).
"""

from __future__ import annotations

from typing import Optional

from visionstudio.blocks import BlockRegistry, registry as block_registry
from visionstudio.engine.errors import EngineError, ErrorCode
from visionstudio.engine.executors import ExecutorRegistry, default_executors
from visionstudio.engine.graph import Graph
from visionstudio.engine.validation import GraphValidator
from visionstudio.types import Value


class GraphRunner:
    """Ejecuta un grafo de bloques sin interfaz."""

    def __init__(
        self,
        graph: Graph,
        registry: Optional[BlockRegistry] = None,
        executors: Optional[ExecutorRegistry] = None,
        validator: Optional[GraphValidator] = None,
    ) -> None:
        self.graph = graph
        self.registry = registry or block_registry
        self.executors = executors or default_executors
        self.validator = validator or GraphValidator(self.registry)
        # Últimas salidas por (node_id, port_id): se limpian en cada pasada.
        self._outputs: dict[str, dict[str, Value]] = {}
        # Resultados de los nodos sumidero: node_id -> {port_id: Value}.
        self._last_results: dict[str, dict[str, Value]] = {}

    # --- API pública -------------------------------------------------------

    def validate(self) -> list[str]:
        """Valida el grafo y devuelve el orden topológico.

        Lanza EngineError con el primer problema encontrado si es inválido.
        """
        issues, order = self.validator.validate(self.graph)
        if issues:
            raise EngineError(issues[0].code, issues[0].params)
        assert order is not None
        return order

    def run_one(self) -> dict[str, dict[str, Value]]:
        """Ejecuta UNA pasada completa del grafo.

        Devuelve `{node_id: {port_id: Value}}` con los valores recibidos por
        cada nodo sumidero (sink). En un grafo sin sinks devuelve {}.
        """
        order = self.validate()
        self._outputs.clear()
        self._last_results.clear()

        for node_id in order:
            node = self.graph.node(node_id)
            spec = self.registry.get(node.type)

            # Ejecutor ausente: el bloque está declarado pero aún no implementado
            # (p. ej. bloques OpenCV en esta fase).
            executor = self.executors.get(node.type)
            if executor is None:
                raise EngineError(
                    ErrorCode.BLOCK_EXECUTION,
                    {
                        "node_id": node.id,
                        "block_type": node.type,
                        "detail": "no_executor",
                    },
                )

            inputs = self._resolve_inputs(node)
            # Parámetros efectivos = por defecto + los del usuario.
            params = {**self.registry.default_params(node.type), **node.params}
            try:
                outputs = executor.execute(inputs, params)
            except EngineError:
                raise
            except Exception as exc:
                # Cualquier fallo inesperado de un ejecutor se envuelve con
                # contexto del nodo para facilitar la depuración.
                raise EngineError(
                    ErrorCode.BLOCK_EXECUTION,
                    {"node_id": node.id, "block_type": node.type, "detail": str(exc)},
                )

            self._outputs[node_id] = outputs
            if not spec.outputs:
                # Nodo sumidero: registrar sus entradas como resultado.
                self._last_results[node_id] = inputs

        return self._last_results

    def last_results(self) -> dict[str, dict[str, Value]]:
        """Resultados de la última pasada ejecutada."""
        return self._last_results

    def sink_value(self, node_id: str, port_id: str = "in") -> Optional[Value]:
        """Valor que recibió un nodo sumidero en la última pasada."""
        return self._last_results.get(node_id, {}).get(port_id)

    # --- internos ----------------------------------------------------------

    def _resolve_inputs(self, node) -> dict[str, Value]:
        """Resuelve los valores de entrada de un nodo desde las salidas previas."""
        spec = self.registry.get(node.type)
        inputs: dict[str, Value] = {}

        for edge in self.graph.incoming(node.id):
            src_outputs = self._outputs.get(edge.from_block, {})
            if edge.from_port not in src_outputs:
                # El origen no produjo ese puerto en esta pasada: solo puede
                # pasar si la conexión es opcional (p. ej. trigger), pero no lo
                # es aquí porque la arista existe.
                raise EngineError(
                    ErrorCode.BLOCK_EXECUTION,
                    {
                        "node_id": node.id,
                        "from_block": edge.from_block,
                        "from_port": edge.from_port,
                        "detail": "source_did_not_produce",
                    },
                )
            inputs[edge.to_port] = src_outputs[edge.from_port]

        # Entradas requeridas sin conexión: el validador ya lo detecta, pero se
        # re-comprueba aquí por robustez (el grafo podría cambiar entre ambas).
        for port in spec.inputs:
            if port.required and port.id not in inputs:
                raise EngineError(
                    ErrorCode.BLOCK_INPUT_MISSING, {"node_id": node.id, "port_id": port.id}
                )
        return inputs