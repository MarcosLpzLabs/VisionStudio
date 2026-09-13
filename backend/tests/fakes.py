"""Fakes para pruebas de cámara.

Un `FakeCapture` imita la interfaz mínima de OpenCV (isOpened/set/read/release)
y permite simular cámaras abiertas/cerradas, frames disponibles y fallos de
liberación, sin hardware real.
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np


def synthetic_frame(width: int = 640, height: int = 480) -> np.ndarray:
    """Frame sintético (negro) de prueba."""
    return np.zeros((height, width, 3), dtype=np.uint8)


class FakeCapture:
    """Backend falso de captura.

    - `open_ok`: si la cámara "responde" a isOpened.
    - `frames`: cola de frames; al agotarse read() devuelve (False, None).
    - `release_raises`: si release() debe lanzar (para probar CAMERA_RELEASE).
    """

    def __init__(
        self,
        index: int,
        open_ok: bool = True,
        frames: Optional[list] = None,
        release_raises: bool = False,
    ) -> None:
        self.index = index
        self.opened = open_ok
        self.frames = list(frames or [])
        self.release_raises = release_raises
        self.set_calls: list[tuple[int, object]] = []
        self.read_count = 0
        self.released = False

    def isOpened(self) -> bool:
        return self.opened

    def set(self, prop: int, value: object) -> bool:
        self.set_calls.append((prop, value))
        return True

    def read(self) -> tuple[bool, object]:
        self.read_count += 1
        if self.frames:
            return True, self.frames.pop(0)
        return False, None

    def release(self) -> None:
        if self.release_raises:
            raise RuntimeError("fallo simulado de release")
        self.released = True
        self.opened = False


class FakeCaptureFactory:
    """Fábrica de FakeCapture con catálogo de cámaras.

    `open_indices`: índices que deben abrirse (el resto devuelve cámara cerrada).
    Registra todas las instancias creadas para poder inspeccionar `released`.
    """

    def __init__(self, open_indices: list[int] = (0,), frames: Optional[dict] = None) -> None:
        self.open_indices = set(open_indices)
        self.frames = frames or {}
        self.instances: list[FakeCapture] = []

    def __call__(self, index: int) -> FakeCapture:
        open_ok = index in self.open_indices
        capture = FakeCapture(index=index, open_ok=open_ok, frames=self.frames.get(index))
        self.instances.append(capture)
        return capture

    def instance(self, index: int) -> Optional[FakeCapture]:
        for inst in self.instances:
            if inst.index == index:
                return inst
        return None