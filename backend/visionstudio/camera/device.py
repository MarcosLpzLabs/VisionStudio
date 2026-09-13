"""Dispositivo de cámara.

Envuelve un backend de captura (OpenCV por defecto) para ofrecer una API
simple y liberable: abrir con configuración, leer frames, liberar.

El backend es inyectable para poder probar sin hardware real: los tests usan
un `FakeCapture` que produce frames sintéticos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

import cv2

from visionstudio.errors import EngineError, ErrorCode


@dataclass
class CameraConfig:
    """Configuración de captura de una cámara."""

    index: int = 0  # índice de la cámara (0 = primera detectada)
    width: int = 640
    height: int = 480


class OpenCVCapture:
    """Adaptador mínimo sobre cv2.VideoCapture (backend por defecto)."""

    def __init__(self, index: int) -> None:
        # El backend real: cualquier objeto con isOpened/set/read/release.
        self._cap = cv2.VideoCapture(index)

    def isOpened(self) -> bool:
        return self._cap.isOpened()

    def set(self, prop: int, value: Any) -> bool:
        return self._cap.set(prop, value)

    def read(self) -> tuple[bool, Any]:
        return self._cap.read()

    def release(self) -> None:
        self._cap.release()


CaptureLike = Any  # protocolo informal: isOpened/set/read/release
CaptureFactory = Callable[[int], CaptureLike]


class CameraDevice:
    """Gestiona el ciclo de vida de una cámara.

    - `open(config)`: abre la cámara y configura la resolución.
    - `read()`: devuelve el frame BGR o None si no pudo leerse.
    - `release()`: libera la cámara de forma segura (idempotente).
    """

    def __init__(self, capture_factory: Optional[CaptureFactory] = None) -> None:
        self._capture_factory = capture_factory or OpenCVCapture
        self._capture: Optional[CaptureLike] = None
        self._config: Optional[CameraConfig] = None

    # --- estado ------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._capture is not None and self._capture.isOpened()

    @property
    def config(self) -> Optional[CameraConfig]:
        return self._config

    # --- ciclo de vida -----------------------------------------------------

    def open(self, config: CameraConfig) -> "CameraDevice":
        """Abre la cámara con la configuración dada.

        Reabrir libera primero la cámara anterior (evita fugas). Lanza
        EngineError(CAMERA_OPEN) si la cámara no puede abrirse.
        """
        self.release()
        capture = self._capture_factory(config.index)
        if capture is None or not capture.isOpened():
            raise EngineError(ErrorCode.CAMERA_OPEN, {"index": config.index})

        # Configurar resolución (puede no aplicarse según el driver; es
        # un intento de mejor esfuerzo).
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.height)

        self._capture = capture
        self._config = config
        return self

    def read(self) -> Optional[Any]:
        """Lee un frame (BGR, numpy).

        Devuelve None si la cámara no pudo producir un frame válido (p. ej.
        cámara desconectada). Lanza CAMERA_OPEN si no hay cámara abierta.
        """
        if not self.is_open:
            raise EngineError(ErrorCode.CAMERA_OPEN, {"index": self._config.index if self._config else -1})
        ok, frame = self._capture.read()
        if not ok or frame is None:
            return None
        return frame

    def release(self) -> None:
        """Libera la cámara. Idempotente y nunca lanza si ya está cerrada."""
        capture = self._capture
        # Capturar el índice ANTES de limpiar el estado (se usa en el error).
        index = self._config.index if self._config else -1
        self._capture = None
        self._config = None
        if capture is None:
            return
        try:
            capture.release()
        except Exception as exc:
            # La cámara debe liberarse siempre; si el backend falla, se informa
            # pero no se propaga (para no bloquear la detención del flujo).
            raise EngineError(ErrorCode.CAMERA_RELEASE, {"index": index, "detail": str(exc)})