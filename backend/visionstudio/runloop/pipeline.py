"""Pipeline: integración RunLoop + runner + cámaras (fase 5).

Une las capas 2 (motor), 3 (cámara) y 4 (runloop) en un único objeto que la
API puede manejar:

- El `step_fn` del RunLoop es `runner.run_one()`: cada paso ejecuta el grafo.
- Al detener/cerrar, se liberan los ejecutores que tengan `close()` (cámaras),
  garantizando una detención limpia y sin fugas de dispositivos.

El pipeline NO conoce el frontend: solo expone estado, control y resultados.
"""

from __future__ import annotations

from typing import Optional

from visionstudio.blocks import BlockRegistry, registry as block_registry
from visionstudio.engine.executors import ExecutorRegistry
from visionstudio.engine.executors_cv import full_executors
from visionstudio.engine.graph import Graph
from visionstudio.engine.runner import GraphRunner
from visionstudio.runloop.runloop import RunLoop, RunMode, RunState


class GraphPipeline:
    """Flujo ejecutable: grafo + ejecución + cámaras, sin interfaz."""

    def __init__(
        self,
        graph: Graph,
        executors: Optional[ExecutorRegistry] = None,
        registry: Optional[BlockRegistry] = None,
        mode: RunMode = RunMode.CONTINUOUS,
        interval_ms: int = 100,
        fps: float = 30.0,
        on_state_change=None,
        on_error=None,
        on_results=None,
    ) -> None:
        self.registry = registry or block_registry
        self.executors = executors or full_executors
        self.runner = GraphRunner(graph, registry=self.registry, executors=self.executors)
        # `on_results` recibe los resultados de cada pasada (sinks) para que la
        # API pueda difundirlos por WebSocket sin acoplar el pipeline al WS.
        self._on_results = on_results
        self.runloop = RunLoop(
            self._step,
            mode=mode,
            interval_ms=interval_ms,
            fps=fps,
            on_state_change=on_state_change,
            on_error=on_error,
        )

    def _step(self) -> None:
        """Ejecuta una pasada y notifica los resultados del sink."""
        results = self.runner.run_one()
        if self._on_results is not None:
            self._on_results(results)

    # --- estado (delegado al RunLoop) --------------------------------------

    @property
    def state(self) -> RunState:
        return self.runloop.state

    @property
    def last_error(self) -> Optional[Exception]:
        return self.runloop.last_error

    # --- control (delegado al RunLoop) -------------------------------------

    def start(self) -> None:
        self.runloop.start()

    def pause(self) -> None:
        self.runloop.pause()

    def resume(self) -> None:
        self.runloop.resume()

    def stop(self) -> None:
        self.runloop.stop()

    def step_once(self) -> None:
        self.runloop.step_once()

    # --- resultados --------------------------------------------------------

    def last_results(self):
        """Resultados de los sinks en la última pasada (node_id -> {port: Value})."""
        return self.runner.last_results()

    def sink_value(self, node_id: str, port_id: str = "in"):
        """Valor que recibió un sink en la última pasada."""
        return self.runner.sink_value(node_id, port_id)

    # --- cierre ------------------------------------------------------------

    def close(self) -> None:
        """Detiene el flujo y libera todos los recursos (cámaras).

        Idempotente. Es el cierre que debe llamar la API al detener o al
        apagar el servidor.
        """
        self.runloop.stop()
        for block_id in self.executors.implemented():
            executor = self.executors.get(block_id)
            close = getattr(executor, "close", None)
            if callable(close):
                close()