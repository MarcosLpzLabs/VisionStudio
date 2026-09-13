"""Ejecutores de bloques con comportamiento OpenCV (fases 5 y 8).

Aquí se implementan los bloques que tocan imágenes:
- `block.camera`: lee frames de una cámara (a través de CameraDevice).
- `block.grayscale`: convierte un frame BGR a escala de grises (3 canales).
- Fase 8: `block.black_white`, `block.threshold`, `block.blur`,
  `block.edge_detection`, `block.contours`, `block.draw_text` y
  `block.detection_list`.

Regla de contrato: todos los `frame` del sistema son BGR de 3 canales. Los
bloques que operan en una sola banda (umbral, Canny, contornos) convierten a
grises internamente y devuelven BGR (GRAY2BGR), igual que GrayscaleExecutor.

El Sink de imagen usa el ejecutor genérico de sinks (recoge su entrada como
resultado). El registro completo (`full_executors`) se construye sobre el de
lógica pura (fase 3) añadiendo estos ejecutores.
"""

from __future__ import annotations

from typing import Any, Optional

import cv2
import numpy as np

from visionstudio.camera.device import CameraConfig, CameraDevice, CaptureFactory
from visionstudio.engine.executors import ExecutorRegistry, build_default_registry
from visionstudio.errors import EngineError, ErrorCode
from visionstudio.types import Detection, Detections, Value, ValueType, frame_value


class CameraExecutor:
    """Bloque `block.camera`: produce un frame por cada ejecución del grafo.

    Gestiona UN dispositivo de cámara (MVP con una sola cámara). Si los
    parámetros cambian (índice/resolución), reabre el dispositivo. Para una
    futura configuración multi-cámara habrá que gestionar un dispositivo por
    nodo (docs/ARQUITECTURA.md §11).

    `capture_factory` es inyectable para pruebas sin hardware real.
    """

    def __init__(self, capture_factory: Optional[CaptureFactory] = None) -> None:
        self._device = CameraDevice(capture_factory=capture_factory)

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        config = CameraConfig(
            index=int(params["camera_index"]),
            width=int(params["width"]),
            height=int(params["height"]),
        )

        # Reabrir solo si cambia la configuración o la cámara se cerró (p. ej.
        # tras una detención). Evita abrir/cerrar en cada frame.
        if not self._device.is_open or self._device.config != config:
            self._device.open(config)

        frame = self._device.read()
        if frame is None:
            # La cámara está abierta pero no produce frames (desconectada).
            raise EngineError(ErrorCode.CAMERA_OPEN, {"index": config.index, "detail": "no_frame"})
        return {"out": frame_value(frame)}

    def close(self) -> None:
        """Libera la cámara. Lo llama el pipeline al detener el flujo."""
        self._device.release()


class GrayscaleExecutor:
    """Bloque `block.grayscale`: frame BGR -> escala de grises en 3 canales.

    Se devuelven 3 canales (GRAY2BGR) para mantener el contrato `frame` = imagen
    BGR de 3 canales que esperan los sinks y los bloques posteriores.
    """

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        frame = inputs["in"].value
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        return {"out": frame_value(gray_bgr)}


# ===========================================================================
# Utilidades compartidas por los bloques de imagen
# ===========================================================================

def _to_gray(frame: np.ndarray) -> np.ndarray:
    """Convierte un frame del sistema (BGR) a una sola banda para OpenCV.

    Acepta también imágenes ya en una banda (robustez ante entradas 2D) para
    que los bloques de umbral/bordes/contornos no dependan del canal.
    """
    if frame.ndim == 2:
        return frame
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def _contours_to_detections(contours: list, gray: np.ndarray) -> list[Detection]:
    """Convierte contornos de OpenCV en detecciones con confianza.

    Etiqueta fija "contour" (MVP). La confianza es la fracción de la caja
    delimitadora ocupada por el contorno relleno (píxeles sólidos / box_area),
    un valor 0..1 que expresa lo "compacto" del objeto; sirve para que
    `block.detection_list` pueda filtrar por `min_confidence`.

    Se calcula con una máscara rellena en lugar de contourArea porque la
    aproximación de cadena (CHAIN_APPROX_SIMPLE) subestima el área real del
    polígono y daría 0.93 para un cuadrado sólido en vez de 1.0.
    """
    height, width = gray.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    items: list[Detection] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        box_area = float(w) * float(h)
        if box_area <= 0:
            # Contorno degenerado (sin caja): no aporta una detección útil.
            continue
        # Rellenar solo este contorno en la máscara y contar sus píxeles.
        mask[:] = 0
        cv2.drawContours(mask, [contour], -1, 255, thickness=-1)
        solid = float(cv2.countNonZero(mask))
        confidence = min(1.0, max(0.0, solid / box_area))
        items.append(
            Detection(
                label="contour",
                confidence=confidence,
                x=float(x),
                y=float(y),
                width=float(w),
                height=float(h),
            )
        )
    return items


# ===========================================================================
# Bloques de procesamiento (fase 8)
# ===========================================================================
# Transforman frame -> frame. Todos devuelven BGR de 3 canales (contrato).
# ===========================================================================

class BlackWhiteExecutor:
    """Bloque `block.black_white`: binarización simple (negro/blanco).

    Aplica un umbral fijo a la imagen en grises: los píxeles por debajo del
    umbral se apagan (0) y los demás se encienden (255). Equivale a
    THRESH_BINARY con max_value=255.
    """

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        gray = _to_gray(inputs["in"].value)
        _, bw = cv2.threshold(gray, float(params["threshold"]), 255, cv2.THRESH_BINARY)
        bw_bgr = cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR)
        return {"out": frame_value(bw_bgr)}


class ThresholdExecutor:
    """Bloque `block.threshold`: umbral con modo configurable.

    El parámetro `type` es el nombre de la constante OpenCV (p. ej.
    THRESH_BINARY_INV) y se resuelve con getattr sobre el módulo cv2. Los
    modos ofrecidos (binario/inverso/truncado/tozero) son los del contrato y
    no incluyen variantes automáticas (OTSU/TRIANGLE), por lo que el umbral
    siempre lo fija el usuario.
    """

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        gray = _to_gray(inputs["in"].value)
        mode = getattr(cv2, str(params["type"]))
        _, out = cv2.threshold(gray, float(params["threshold"]), float(params["max_value"]), mode)
        out_bgr = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
        return {"out": frame_value(out_bgr)}


class BlurExecutor:
    """Bloque `block.blur`: desenfoque gaussiano.

    `kernel` debe ser impar (OpenCV lo exige para GaussianBlur); el rango del
    contrato (1..99) no puede expresarlo, así que se valida aquí. `sigma` 0
    deja que OpenCV derive la desviación a partir del tamaño del núcleo.
    """

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        kernel = int(params["kernel"])
        if kernel < 1 or kernel % 2 == 0:
            # Configuración inválida: kernel par rompería GaussianBlur.
            raise EngineError(
                ErrorCode.PARAM_INVALID,
                {"detail": f"kernel debe ser impar y mayor o igual que 1: {kernel}"},
            )
        blurred = cv2.GaussianBlur(inputs["in"].value, (kernel, kernel), float(params["sigma"]))
        return {"out": frame_value(blurred)}


class EdgeDetectionExecutor:
    """Bloque `block.edge_detection`: bordes con el detector de Canny.

    Canny trabaja en una sola banda; el resultado se devuelve como BGR. OpenCV
    intercambia los umbrales si `low` > `high`, por lo que no hace falta
    validar ese orden (el rango del contrato ya limita ambos a 0..1000).
    """

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        gray = _to_gray(inputs["in"].value)
        edges = cv2.Canny(gray, float(params["low"]), float(params["high"]))
        edges_bgr = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
        return {"out": frame_value(edges_bgr)}


class ContoursExecutor:
    """Bloque `block.contours`: detección de contornos.

    Salidas:
    - `detections`: cada contorno como detección (caja delimitadora + confianza).
    - `out`: frame BGR con los contornos dibujados (verde), para visualizar.

    `retrieve_mode` y `approx` son constantes OpenCV seleccionables en el
    contrato; `min_area` descarta contornos demasiado pequeños (ruido).
    """

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        frame = inputs["in"].value
        gray = _to_gray(frame)
        retrieve_mode = getattr(cv2, str(params["retrieve_mode"]))
        approx = getattr(cv2, str(params["approx"]))
        contours, _ = cv2.findContours(gray, retrieve_mode, approx)

        min_area = float(params["min_area"])
        filtered = [c for c in contours if cv2.contourArea(c) >= min_area]
        detections = Detections(_contours_to_detections(filtered, gray))

        # Se copia el frame para no mutar el array que puede compartir el
        # origen de la conexión (los bloques anteriores pueden reutilizarlo).
        canvas = frame.copy()
        cv2.drawContours(canvas, filtered, -1, (0, 255, 0), 2)
        return {
            "detections": Value(ValueType.DETECTIONS, detections),
            "out": frame_value(canvas),
        }


class DrawTextExecutor:
    """Bloque `block.draw_text`: dibuja texto literal sobre el frame.

    `color` es una tupla BGR (contrato de `color`); `size` es la escala de la
    fuente. Se copia el frame de entrada para no mutarlo (igual que contornos).
    """

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        frame = inputs["in"].value
        color = tuple(int(c) for c in params["color"])
        canvas = frame.copy()
        cv2.putText(
            canvas,
            str(params["text"]),
            (int(params["x"]), int(params["y"])),
            cv2.FONT_HERSHEY_SIMPLEX,
            float(params["size"]),
            color,
            thickness=2,
            lineType=cv2.LINE_AA,
        )
        return {"out": frame_value(canvas)}


class DetectionListExecutor:
    """Bloque `block.detection_list`: envoltura de detecciones sobre un frame.

    En el MVP genera las detecciones a partir de los contornos externos del
    frame (preparado para sustituirse por YOLO en el futuro). Aplica los dos
    filtros del contrato:
    - `min_confidence`: descarta detecciones con confianza inferior.
    - `max_items`: limita el número de detecciones (las de mayor confianza).
    """

    def execute(self, inputs: dict[str, Value], params: dict[str, Any]) -> dict[str, Value]:
        frame = inputs["in"].value
        gray = _to_gray(frame)
        contours, _ = cv2.findContours(gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        items = _contours_to_detections(contours, gray)
        min_confidence = float(params["min_confidence"])
        max_items = int(params["max_items"])
        # Orden estable: mayor confianza primero y, a igualdad, por área.
        items.sort(key=lambda it: (it.confidence, it.width * it.height), reverse=True)
        items = [it for it in items if it.confidence >= min_confidence][:max_items]
        return {"detections": Value(ValueType.DETECTIONS, Detections(items))}


def build_full_registry(capture_factory: Optional[CaptureFactory] = None) -> ExecutorRegistry:
    """Registro completo: lógica pura (fase 3) + bloques OpenCV implementados.

    `capture_factory` permite inyectar un backend de cámara falso en las
    pruebas; por defecto usa la cámara real de OpenCV.
    """
    registry = build_default_registry()
    registry.register("block.camera", CameraExecutor(capture_factory=capture_factory))
    registry.register("block.grayscale", GrayscaleExecutor())
    # Fase 8: procesamiento de imagen restante.
    registry.register("block.black_white", BlackWhiteExecutor())
    registry.register("block.threshold", ThresholdExecutor())
    registry.register("block.blur", BlurExecutor())
    registry.register("block.edge_detection", EdgeDetectionExecutor())
    registry.register("block.contours", ContoursExecutor())
    registry.register("block.draw_text", DrawTextExecutor())
    registry.register("block.detection_list", DetectionListExecutor())
    return registry


# Registro global con los bloques OpenCV implementados hasta el momento.
full_executors = build_full_registry()