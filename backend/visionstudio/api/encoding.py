"""Codificación de frames para transporte.

Los frames nunca se serializan como JSON crudo: se comprimen a JPEG y se
codifican en base64 para viajar por WebSocket (docs/ARQUITECTURA.md §6).
"""

from __future__ import annotations

import base64
from typing import Any

import cv2
import numpy as np


def frame_to_jpeg_base64(frame: np.ndarray, quality: int = 80) -> str:
    """Convierte un frame BGR a JPEG en base64.

    Devuelve "" si la codificación falla (no se lanza: un frame perdido no debe
    tumbar el flujo en tiempo real).
    """
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        return ""
    return base64.b64encode(buffer.tobytes()).decode("ascii")