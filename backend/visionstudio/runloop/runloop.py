"""RunLoop: gestión de la ejecución del flujo (fase 4).

Orquesta CUÁNDO se ejecuta un paso del grafo según el modo:
- `continuous`: pasos automáticos a una frecuencia (FPS de la cámara).
- `timer`: pasos automáticos a un intervalo fijo (bloque Timer).
- `manual`: pasos solo por petición explícita (ejecución de un frame).

Estados: stopped -> running -> paused (transiciones en docs/CONTRATOS.md §6).

El RunLoop es AGNÓSTICO del grafo: recibe un `step_fn` que ejecuta un paso
(luego el responsable de construir ese paso es la capa de ejecución/fase 5).
Admite combinar modos: un paso manual puede dispararse incluso en modo
continuo o timer (el bucle procesa peticiones pendientes).

Toda la concurrencia se gestiona con hilos de Python y `threading.Event`:
detención cooperativa con join con timeout; nunca se bloquea la interfaz.
"""

from __future__ import annotations

import threading
from enum import Enum
from typing import Callable, Optional


class RunMode(str, Enum):
    """Modo de ejecución del flujo."""

    CONTINUOUS = "continuous"  # a la frecuencia de la fuente (FPS)
    TIMER = "timer"  # a un intervalo fijo en milisegundos
    MANUAL = "manual"  # solo por petición explícita (frame a frame)


class RunState(str, Enum):
    """Estado del flujo (docs/CONTRATOS.md §6)."""

    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


class RunLoop:
    """Máquina de estados + bucle de ejecución con temporización."""

    def __init__(
        self,
        step_fn: Callable[[], None],
        mode: RunMode = RunMode.CONTINUOUS,
        interval_ms: int = 100,
        fps: float = 30.0,
        on_state_change: Optional[Callable[[RunState], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self._step_fn = step_fn
        self._mode = mode
        self._interval_ms = interval_ms
        self._fps = fps

        # Callbacks informan al exterior (API/WebSocket) de cambios de estado y
        # errores, sin que el RunLoop dependa de ellos.
        self._on_state_change = on_state_change
        self._on_error = on_error

        self._state = RunState.STOPPED
        self._lock = threading.RLock()  # protege el estado (lectores y cambios)
        self._stop_event = threading.Event()  # señal de detención
        self._step_event = threading.Event()  # petición de paso manual
        self._thread: Optional[threading.Thread] = None
        self._last_error: Optional[Exception] = None

    # --- acceso al estado --------------------------------------------------

    @property
    def state(self) -> RunState:
        with self._lock:
            return self._state

    @property
    def mode(self) -> RunMode:
        return self._mode

    @property
    def last_error(self) -> Optional[Exception]:
        return self._last_error

    def is_running(self) -> bool:
        return self.state == RunState.RUNNING

    # --- configuración -----------------------------------------------------

    def set_mode(self, mode: RunMode) -> None:
        # Cambiar el modo con el flujo en marcha es válido (se aplica en el
        # siguiente ciclo del bucle); no requiere detener.
        with self._lock:
            self._mode = mode

    def set_interval_ms(self, interval_ms: int) -> None:
        with self._lock:
            self._interval_ms = max(1, interval_ms)

    def set_fps(self, fps: float) -> None:
        with self._lock:
            self._fps = max(1.0, fps)

    # --- control -----------------------------------------------------------

    def start(self) -> None:
        """Arranca el flujo (STOPPED -> RUNNING)."""
        with self._lock:
            if self._state == RunState.RUNNING:
                return  # ya en marcha: no duplicar el hilo
            if self._state == RunState.PAUSED:
                # Reanudar es lo mismo que volver a ejecutar tras pausa.
                self._set_state(RunState.RUNNING)
                return

        # Estado STOPPED: crear un hilo nuevo (desechable, nunca bloquea la UI).
        self._stop_event.clear()
        self._last_error = None
        self._thread = threading.Thread(target=self._loop, name="vs-runloop", daemon=True)
        self._set_state(RunState.RUNNING)
        self._thread.start()

    def pause(self) -> None:
        """Pausa el flujo (RUNNING -> PAUSED): deja de ejecutar pasos."""
        with self._lock:
            if self._state == RunState.RUNNING:
                self._set_state(RunState.PAUSED)

    def resume(self) -> None:
        """Reanuda el flujo (PAUSED -> RUNNING)."""
        with self._lock:
            if self._state == RunState.PAUSED:
                self._set_state(RunState.RUNNING)

    def stop(self, timeout: float = 5.0) -> None:
        """Detiene el flujo y espera a que el hilo termine.

        Siempre deja el flujo en STOPPED. La detención es cooperativa: se
        señaliza, se despierta cualquier wait y se hace join con timeout para
        no colgar nunca la llamada.
        """
        self._stop_event.set()
        self._step_event.set()  # despierta el wait del bucle
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout)
        self._thread = None
        self._stop_event.clear()
        self._step_event.clear()
        self._set_state(RunState.STOPPED)

    def step_once(self) -> None:
        """Ejecuta UN paso manual (frame a frame).

        - Si el hilo está vivo (modo manual en marcha): se encola la petición
          y el bucle la ejecuta.
        - Si no hay hilo (flujo detenido): se ejecuta directamente, de forma
          síncrona. Esto permite ejecutar un único frame sin arrancar el flujo.
        """
        if self._thread is not None and self._thread.is_alive():
            self._step_event.set()
        else:
            self._run_step()

    # --- bucle interno -----------------------------------------------------

    def _period(self) -> float:
        """Periodo de espera entre pasos según el modo (en segundos)."""
        with self._lock:
            if self._mode == RunMode.TIMER:
                return self._interval_ms / 1000.0
            return 1.0 / self._fps

    def _loop(self) -> None:
        """Bucle del hilo: ejecuta pasos según estado y modo hasta detener."""
        while not self._stop_event.is_set():
            with self._lock:
                state = self._state
                mode = self._mode

            if state == RunState.PAUSED:
                # Pausado: no ejecuta; despierta cada poco para responder a
                # resume/stop sin consumir CPU.
                self._stop_event.wait(0.05)
                continue

            if state != RunState.RUNNING:
                break  # (defensa) cualquier otro estado detiene el bucle

            auto_step = mode in (RunMode.CONTINUOUS, RunMode.TIMER)
            has_manual_request = self._step_event.is_set()
            if has_manual_request:
                self._step_event.clear()

            if auto_step or has_manual_request:
                if not self._run_step():
                    break  # un error de paso detiene el bucle (estado->STOPPED)

            # Espera del periodo. En manual no hay periodo: se espera a la
            # siguiente petición (timeout corto para responder a stop/resume).
            if auto_step:
                self._stop_event.wait(self._period())
            else:
                self._step_event.wait(0.05)

    def _run_step(self) -> bool:
        """Ejecuta un paso capturando errores. Devuelve False si falló."""
        try:
            self._step_fn()
            return True
        except Exception as exc:
            # Error del paso: se registra, se informa y se detiene el flujo
            # (un paso fallido no debe seguir ejecutándose en bucle).
            self._last_error = exc
            if self._on_error is not None:
                self._on_error(exc)
            self._set_state(RunState.STOPPED)
            return False

    def _set_state(self, state: RunState) -> None:
        """Cambia el estado si es distinto y notifica al callback."""
        with self._lock:
            if self._state == state:
                return
            self._state = state
        if self._on_state_change is not None:
            self._on_state_change(state)