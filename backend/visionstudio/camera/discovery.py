"""Descubrimiento de cámaras disponibles.

Sondea índices de cámara y devuelve las que responden. El MVP usa una sola
cámara, pero el contrato permite listar varias para una futura configuración
multi-cámara (docs/ARQUITECTURA.md §11).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from visionstudio.camera.device import CaptureFactory, OpenCVCapture


@dataclass
class CameraInfo:
    """Descripción de una cámara detectada."""

    index: int
    name: str


def list_cameras(
    capture_factory: Optional[CaptureFactory] = None,
    max_index: int = 10,
    read_probe: bool = False,
) -> list[CameraInfo]:
    """Devuelve las cámaras detectadas sondeando índices 0..max_index-1.

    - `capture_factory`: backend inyectable para pruebas.
    - `read_probe`: si True, además de `isOpened()` intenta leer un frame
      (más fiable pero más lento y puede bloquearse en algunas webcams).
    """
    factory = capture_factory or OpenCVCapture
    found: list[CameraInfo] = []

    for index in range(max_index):
        capture = factory(index)
        try:
            if not capture.isOpened():
                continue
            if read_probe:
                ok, _ = capture.read()
                if not ok:
                    continue
            found.append(CameraInfo(index=index, name=f"Camera {index}"))
        finally:
            # Siempre se libera el sondeo: no dejar cámaras abiertas tras listar.
            capture.release()

    return found