"""Pruebas del RunLoop: estados, modos y temporización."""

import threading
import time

import pytest

from visionstudio.runloop import RunLoop, RunMode, RunState


def wait_until(predicate, timeout: float = 2.0) -> bool:
    """Espera a que una condición se cumpla (evita dormir a ciegas)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class StepCounter:
    """Contador de pasos seguro para hilos."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.count = 0
        self.reached = threading.Event()

    def __call__(self) -> None:
        with self.lock:
            self.count += 1
            if self.count >= 3:
                self.reached.set()

    def value(self) -> int:
        with self.lock:
            return self.count


def test_transiciones_de_estado():
    states: list[RunState] = []
    loop = RunLoop(lambda: None, on_state_change=states.append)

    loop.start()
    assert loop.state == RunState.RUNNING

    loop.pause()
    assert loop.state == RunState.PAUSED

    loop.resume()
    assert loop.state == RunState.RUNNING

    loop.stop()
    assert loop.state == RunState.STOPPED

    assert states == [
        RunState.RUNNING,
        RunState.PAUSED,
        RunState.RUNNING,
        RunState.STOPPED,
    ]


def test_modo_continuo_ejecuta_pasos():
    counter = StepCounter()
    loop = RunLoop(counter, mode=RunMode.CONTINUOUS, fps=100)
    loop.start()
    try:
        assert wait_until(counter.reached.is_set)
    finally:
        loop.stop()
    assert counter.value() >= 3


def test_modo_timer_ejecuta_a_intervalo():
    counter = StepCounter()
    loop = RunLoop(counter, mode=RunMode.TIMER, interval_ms=5)
    loop.start()
    try:
        assert wait_until(counter.reached.is_set)
    finally:
        loop.stop()
    assert counter.value() >= 3


def test_modo_manual_no_automatiza_y_step_once_dispara():
    counter = StepCounter()
    loop = RunLoop(counter, mode=RunMode.MANUAL)
    loop.start()
    try:
        # Sin peticiones manuales, no debe ejecutarse nada.
        time.sleep(0.05)
        assert counter.value() == 0

        # Cada step_once dispara exactamente un paso (el bucle lo procesa).
        loop.step_once()
        assert wait_until(lambda: counter.value() == 1)
        loop.step_once()
        assert wait_until(lambda: counter.value() == 2)

        # Sin nuevas peticiones, no hay más pasos.
        time.sleep(0.05)
        assert counter.value() == 2
    finally:
        loop.stop()


def test_step_once_sin_hilo_ejecuta_sincrono():
    # Flujo detenido: step_once ejecuta el paso directamente (frame a frame).
    counter = StepCounter()
    loop = RunLoop(counter, mode=RunMode.MANUAL)
    loop.step_once()
    assert counter.value() == 1


def test_pausa_detiene_pasos_y_resume_los_reanuda():
    counter = StepCounter()
    loop = RunLoop(counter, mode=RunMode.CONTINUOUS, fps=100)
    loop.start()
    try:
        assert wait_until(lambda: counter.value() >= 1)

        loop.pause()
        frozen = counter.value()
        time.sleep(0.05)
        assert counter.value() == frozen  # pausado: sin pasos

        loop.resume()
        assert wait_until(lambda: counter.value() > frozen)
    finally:
        loop.stop()


def test_stop_detiene_el_bucle():
    counter = StepCounter()
    loop = RunLoop(counter, mode=RunMode.CONTINUOUS, fps=100)
    loop.start()
    assert wait_until(lambda: counter.value() >= 1)

    loop.stop()
    frozen = counter.value()
    time.sleep(0.05)
    # Tras stop, el bucle no debe seguir ejecutando pasos.
    assert counter.value() == frozen
    assert loop.state == RunState.STOPPED


def test_error_de_paso_detiene_y_notifica():
    errors: list[Exception] = []

    def failing():
        raise ValueError("boom")

    loop = RunLoop(failing, mode=RunMode.TIMER, interval_ms=5, on_error=errors.append)
    loop.start()

    assert wait_until(lambda: loop.state == RunState.STOPPED)
    assert loop.last_error is not None
    assert errors and isinstance(errors[0], ValueError)


def test_start_doble_no_duplica_hilo():
    counter = StepCounter()
    loop = RunLoop(counter, mode=RunMode.TIMER, interval_ms=5)
    loop.start()
    thread = loop._thread
    loop.start()  # segundo start: no debe crear otro hilo
    assert loop._thread is thread
    loop.stop()


def test_set_mode_y_set_interval():
    loop = RunLoop(lambda: None, mode=RunMode.CONTINUOUS, fps=30)
    loop.set_mode(RunMode.TIMER)
    loop.set_interval_ms(10)
    loop.set_fps(60)
    assert loop.mode == RunMode.TIMER
    assert loop._interval_ms == 10
    assert loop._fps == 60