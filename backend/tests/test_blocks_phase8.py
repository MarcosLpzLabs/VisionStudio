"""Pruebas de los bloques OpenCV de la fase 8.

Cubre los bloques restantes del MVP (docs/CONTRATOS.md §3):
binarización (black_white), umbral configurable (threshold), desenfoque (blur),
bordes de Canny (edge_detection), contornos (contours), texto (draw_text) y la
envoltura de detecciones (detection_list).

Verifica además que el registro completo implementa ya los 21 bloques del MVP y
que un flujo cámara -> procesamiento -> sink funciona de punta a punta con
cámaras falsas (sin hardware).
"""

import numpy as np
import pytest

from visionstudio.engine.executors_cv import (
    BlackWhiteExecutor,
    BlurExecutor,
    ContoursExecutor,
    DetectionListExecutor,
    DrawTextExecutor,
    EdgeDetectionExecutor,
    ThresholdExecutor,
    build_full_registry,
)
from visionstudio.engine.graph import Edge, Graph, Node
from visionstudio.errors import EngineError, ErrorCode
from visionstudio.runloop import GraphPipeline, RunMode
from visionstudio.types import frame_value
from tests.fakes import FakeCaptureFactory, synthetic_frame


def two_tone_frame(dark=50, bright=200, height=20, width=30):
    """Frame BGR partido en dos: superior `bright`, inferior `dark`."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[: height // 2, :, :] = bright
    frame[height // 2 :, :, :] = dark
    return frame


def white_square_image(height=50, width=50, box=(10, 10, 30, 30)):
    """Imagen BGR con un cuadrado blanco sobre fondo negro."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    x, y, w, h = box
    frame[y : y + h, x : x + w, :] = 255
    return frame


# ===========================================================================
# block.black_white
# ===========================================================================

def test_black_white_binariza_en_blanco_y_negro():
    executor = BlackWhiteExecutor()
    out = executor.execute(
        {"in": frame_value(two_tone_frame())}, {"threshold": 127}
    )["out"].value
    # Salida BGR de 3 canales y monocroma (R == G == B).
    assert out.shape == (20, 30, 3)
    assert np.all(out[:, :, 0] == out[:, :, 1])
    assert np.all(out[:, :, 1] == out[:, :, 2])
    # La mitad brillante (200 > 127) se enciende; la oscura (50) se apaga.
    assert np.all(out[:10] == 255)
    assert np.all(out[10:] == 0)


# ===========================================================================
# block.threshold
# ===========================================================================

def test_threshold_binary_e_inverso():
    executor = ThresholdExecutor()
    params = {"threshold": 127, "max_value": 255}
    out = executor.execute(
        {"in": frame_value(two_tone_frame())}, {**params, "type": "THRESH_BINARY"}
    )["out"].value
    assert out.shape == (20, 30, 3)
    assert np.all(out[:10] == 255) and np.all(out[10:] == 0)

    out_inv = executor.execute(
        {"in": frame_value(two_tone_frame())}, {**params, "type": "THRESH_BINARY_INV"}
    )["out"].value
    # THRESH_BINARY_INV invierte: lo oscuro se enciende.
    assert np.all(out_inv[:10] == 0) and np.all(out_inv[10:] == 255)


def test_threshold_trunc_y_tozero_respetan_semantica():
    executor = ThresholdExecutor()
    frame = two_tone_frame()
    # THRESH_TRUNC: los píxeles por encima del umbral se recortan a él; los
    # que están por debajo se conservan intactos.
    out = executor.execute(
        {"in": frame_value(frame)},
        {"threshold": 100, "max_value": 255, "type": "THRESH_TRUNC"},
    )["out"].value
    assert out[5, 15, 0] == 100  # 200 se recorta a 100
    assert np.all(out[10:] == 50)  # 50 < umbral se conserva

    # THRESH_TOZERO: los píxeles por debajo del umbral se apagan; los demás
    # quedan con su valor original.
    out_tz = executor.execute(
        {"in": frame_value(frame)},
        {"threshold": 100, "max_value": 255, "type": "THRESH_TOZERO"},
    )["out"].value
    assert np.all(out_tz[:10] == 200)  # 200 > umbral se conserva
    assert np.all(out_tz[10:] == 0)  # 50 < umbral se apaga


# ===========================================================================
# block.blur
# ===========================================================================

def test_blur_suaviza_imagen_con_ruido():
    rng = np.random.default_rng(0)
    frame = rng.integers(0, 256, (30, 40, 3), dtype=np.uint8).astype(np.uint8)
    executor = BlurExecutor()
    out = executor.execute({"in": frame_value(frame)}, {"kernel": 5, "sigma": 0})["out"].value
    assert out.shape == frame.shape
    # El desenfoque reduce la desviación típica del ruido.
    assert out.std() < frame.std()


def test_blur_rechaza_kernel_par():
    executor = BlurExecutor()
    with pytest.raises(EngineError) as exc:
        executor.execute(
            {"in": frame_value(synthetic_frame())}, {"kernel": 4, "sigma": 0}
        )
    assert exc.value.code == ErrorCode.PARAM_INVALID


# ===========================================================================
# block.edge_detection
# ===========================================================================

def test_edge_detection_encuentra_bordes_de_cuadrado():
    executor = EdgeDetectionExecutor()
    out = executor.execute(
        {"in": frame_value(white_square_image())}, {"low": 100, "high": 200}
    )["out"].value
    assert out.shape == (50, 50, 3)
    # Un cuadrado sobre fondo uniforme produce píxeles de borde.
    assert np.any(out > 0)
    # El interior del cuadrado no es borde (en BGR monocromo el borde es 255).
    assert np.all(out[25, 25] == 0)


# ===========================================================================
# block.contours
# ===========================================================================

def test_contours_detecta_cuadrado_y_dibuja_frame():
    executor = ContoursExecutor()
    out = executor.execute(
        {"in": frame_value(white_square_image())},
        {"retrieve_mode": "RETR_EXTERNAL", "approx": "CHAIN_APPROX_SIMPLE", "min_area": 10},
    )
    detections = out["detections"].value
    assert len(detections.items) == 1
    d = detections.items[0]
    assert d.label == "contour"
    assert d.confidence == pytest.approx(1.0)  # caja totalmente rellena
    assert (d.x, d.y, d.width, d.height) == (10.0, 10.0, 30.0, 30.0)
    # La salida de imagen dibuja el contorno y no muta el frame de entrada.
    canvas = out["out"].value
    assert canvas.shape == (50, 50, 3)
    assert np.any(canvas != white_square_image())


def test_contours_filtra_por_min_area():
    frame = np.zeros((60, 60, 3), dtype=np.uint8)
    frame[5:10, 5:10] = 255  # área 25: se descarta con min_area 100
    frame[30:50, 30:50] = 255  # área 400: se conserva
    executor = ContoursExecutor()
    out = executor.execute(
        {"in": frame_value(frame)},
        {"retrieve_mode": "RETR_EXTERNAL", "approx": "CHAIN_APPROX_SIMPLE", "min_area": 100},
    )
    items = out["detections"].value.items
    assert len(items) == 1
    assert items[0].x == 30.0 and items[0].y == 30.0


# ===========================================================================
# block.draw_text
# ===========================================================================

def test_draw_text_dibuja_texto_sin_mutar_entrada():
    frame = np.zeros((60, 100, 3), dtype=np.uint8)
    executor = DrawTextExecutor()
    out = executor.execute(
        {"in": frame_value(frame)},
        {"text": "Hola", "x": 10, "y": 30, "size": 1.0, "color": [0, 255, 0]},
    )["out"].value
    # No se modifica el array de entrada (se trabaja sobre una copia).
    assert np.all(frame == 0)
    # Aparecen píxeles del color pedido (verde en BGR).
    green = np.all(out[:, :, :] == [0, 255, 0], axis=-1)
    assert np.any(green)


# ===========================================================================
# block.detection_list
# ===========================================================================

def test_detection_list_genera_detecciones_con_confianza():
    executor = DetectionListExecutor()
    out = executor.execute(
        {"in": frame_value(white_square_image())},
        {"max_items": 10, "min_confidence": 0.5},
    )
    items = out["detections"].value.items
    assert len(items) == 1
    assert items[0].label == "contour"
    assert items[0].confidence >= 0.5
    assert (items[0].width, items[0].height) == (30.0, 30.0)


def test_detection_list_filtra_por_confianza_y_limita_items():
    frame = np.zeros((60, 60, 3), dtype=np.uint8)
    frame[5:10, 5:10] = 255  # caja rellena -> confianza 1.0
    frame[30:50, 30:50] = 255  # caja rellena -> confianza 1.0
    executor = DetectionListExecutor()
    out = executor.execute(
        {"in": frame_value(frame)},
        {"max_items": 1, "min_confidence": 0.9},
    )
    items = out["detections"].value.items
    # Ambos superan la confianza mínima pero solo pasa el límite de 1.
    assert len(items) == 1


def test_detection_list_sin_detecciones_devuelve_vacio():
    executor = DetectionListExecutor()
    out = executor.execute(
        {"in": frame_value(synthetic_frame())},  # todo negro: sin contornos
        {"max_items": 10, "min_confidence": 0.5},
    )
    assert out["detections"].value.items == []


# ===========================================================================
# Registro completo y flujo end-to-end
# ===========================================================================

def test_registro_completo_implementa_los_21_bloques():
    implemented = build_full_registry().implemented()
    assert len(implemented) == 21


def graph_camara_procesamiento_sink() -> Graph:
    # camera -> grayscale -> threshold -> contours -> sink_image
    g = Graph()
    g.add_node(Node(id="cam", type="block.camera"))
    g.add_node(Node(id="gray", type="block.grayscale"))
    g.add_node(Node(id="thr", type="block.threshold"))
    g.add_node(Node(id="cnt", type="block.contours"))
    g.add_node(Node(id="sink", type="block.sink_image"))
    g.add_edge(Edge(from_block="cam", from_port="out", to_block="gray", to_port="in"))
    g.add_edge(Edge(from_block="gray", from_port="out", to_block="thr", to_port="in"))
    g.add_edge(Edge(from_block="thr", from_port="out", to_block="cnt", to_port="in"))
    g.add_edge(Edge(from_block="cnt", from_port="out", to_block="sink", to_port="in"))
    return g


def test_flujo_completo_camara_threshold_contornos_sink():
    factory = FakeCaptureFactory(
        open_indices=[0], frames={0: [white_square_image(height=60, width=60)]}
    )
    executors = build_full_registry(capture_factory=factory)
    pipeline = GraphPipeline(graph_camara_procesamiento_sink(), executors=executors,
                             mode=RunMode.MANUAL)
    pipeline.step_once()
    value = pipeline.sink_value("sink", "in")
    assert value is not None and value.is_frame()
    assert value.value.shape == (60, 60, 3)
    pipeline.close()
    assert factory.instance(0).released