"""Especificaciones declarativas de los bloques de VisionStudio.

Metadatos estables que consumen el motor, la API y el frontend.
El esquema sigue docs/CONTRATOS.md §2. Los identificadores NO se renombran.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from visionstudio.types import ValueType

# Tipos de parámetro y categorías disponibles. Se usan como literales en los
# modelos para que pydantic rechace valores no soportados en la definición.
ParamType = Literal["number", "boolean", "string", "select", "color"]
ParamKind = Literal["float", "int"]
Category = Literal["source", "control", "processing", "analysis", "output"]


# ===========================================================================
# Modelos de especificación
# ===========================================================================
# Un bloque se describe ENTERAMENTE con datos (id, puertos, parámetros). El
# motor y el frontend interpretan estos datos, por lo que añadir un bloque nuevo
# solo requiere añadir un BlockSpec (más su ejecutor en fases posteriores).
# ===========================================================================

class PortSpec(BaseModel):
    """Puerto de entrada o salida de un bloque.

    - `types`: tipos aceptados (entrada) o emitidos (salida). Una entrada con
      varios tipos admite conectar cualquiera de ellos (p. ej. status_indicator
      acepta "analysis" o "boolean").
    - `required`: en entradas, indica si la conexión es obligatoria para poder
      ejecutar el bloque.
    """

    id: str
    label_key: str
    types: tuple[str, ...] = (ValueType.FRAME,)  # tipos aceptados/emitidos
    required: bool = True

    @field_validator("types")
    @classmethod
    def _valid_types(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        # Falla en la definición (no en runtime) si un puerto usa un tipo que
        # no existe en el sistema.
        for t in v:
            if t not in ValueType.ALL:
                raise ValueError(f"tipo de puerto no soportado: {t!r}")
        return v


class ParamSpec(BaseModel):
    """Parámetro configurable de un bloque.

    Ejemplos:
    - Número entero con rango: camera_index (min=0, kind="int").
    - Selector: tipo de threshold (options de strings).
    - Color: tupla (B, G, R) con valores 0-255.
    """

    id: str
    label_key: str
    type: ParamType = "number"
    kind: ParamKind = "float"
    default: Any = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    options: tuple[str, ...] = ()  # valores para type="select"
    required: bool = True
    # Poka-yoke: si es True, el valor entero debe ser IMPAR (p. ej. el tamaño de
    # núcleo de GaussianBlur, que OpenCV rechaza si es par). La UI fuerza
    # impares y el registro rechaza el resto antes de ejecutar.
    odd: bool = False

    @field_validator("options")
    @classmethod
    def _options_tuple(cls, v: Any) -> tuple[str, ...]:
        # Normaliza listas a tuplas: los datos deben ser inmutables y hashables.
        return tuple(v)

    @field_validator("default")
    @classmethod
    def _default_tuple(cls, v: Any) -> Any:
        # Tuplas pydantic se normalizan a list; mantener como tuple para color.
        return v


class BlockSpec(BaseModel):
    """Definición completa de un bloque.

    `behavior` indica al motor cómo se ejecuta:
    - continuous:  emite salidas por sí solo (cámara, timer, valores).
    - on_tick:     produce un dato cuando recibe un trigger (cámara temporizada).
    - on_trigger:  solo responde a peticiones explícitas (ejecución manual).
    - passthrough: transforma una entrada en una salida (procesamiento/análisis).
    """

    id: str
    category: Category
    name_key: str
    description_key: str
    inputs: tuple[PortSpec, ...] = ()
    outputs: tuple[PortSpec, ...] = ()
    params: tuple[ParamSpec, ...] = ()
    behavior: Literal["continuous", "on_tick", "on_trigger", "passthrough"] = "passthrough"
    doc_url: str = ""  # documentación educativa (opcional)

    @field_validator("inputs", "outputs", "params")
    @classmethod
    def _to_tuple(cls, v: Any) -> tuple:
        # Igual que arriba: inmutabilidad en los datos de la especificación.
        return tuple(v)

    def param(self, param_id: str) -> ParamSpec:
        # Acceso cómodo: spec.param("kernel") en vez de buscar en la lista.
        for p in self.params:
            if p.id == param_id:
                return p
        raise KeyError(f"parámetro {param_id!r} no existe en {self.id!r}")

    def port(self, port_id: str) -> PortSpec:
        # Igual que param() pero para puertos. Lanza KeyError si no existe, lo
        # que ayuda a detectar referencias rotas en las conexiones.
        for p in (*self.inputs, *self.outputs):
            if p.id == port_id:
                return p
        raise KeyError(f"puerto {port_id!r} no existe en {self.id!r}")


# ===========================================================================
# Constructores compactos
# ===========================================================================
# Abreviaturas para escribir especificaciones con menos ruido y evitar
# errores de tipeo en label_key (los prefijos "param." y "port." son convención).
# ===========================================================================

def _p(id_: str, label: str, **kw: Any) -> ParamSpec:
    return ParamSpec(id=id_, label_key=label, **kw)


def _in(id_: str, label: str, types: tuple[str, ...], **kw: Any) -> PortSpec:
    return PortSpec(id=id_, label_key=label, types=types, **kw)


def _out(id_: str, label: str, types: tuple[str, ...]) -> PortSpec:
    return PortSpec(id=id_, label_key=label, types=types)


# ===========================================================================
# Fuentes (source)
# ===========================================================================
# Bloques que PRODUCEN datos hacia el grafo. La cámara es la fuente principal.
# La entrada "trigger" es opcional: si se conecta un Timer, la cámara captura
# un frame por cada tick; si no, captura en modo continuo a su FPS.

BLOCK_CAMERA = BlockSpec(
    id="block.camera",
    category="source",
    name_key="block.camera.name",
    description_key="block.camera.desc",
    # required=False: en modo continuo no necesita trigger.
    inputs=(_in("trigger", "port.trigger", (ValueType.TRIGGER,), required=False),),
    outputs=(_out("out", "port.frame", (ValueType.FRAME,)),),
    params=(
        # camera_index: qué cámara (0 = primera). Estable por contrato para
        # soportar futuras configuraciones multi-cámara.
        _p("camera_index", "param.camera_index", type="number", kind="int", default=0, min=0),
        _p("width", "param.width", type="number", kind="int", default=640, min=16, max=7680),
        _p("height", "param.height", type="number", kind="int", default=480, min=16, max=4320),
    ),
    behavior="on_tick",
)

# ===========================================================================
# Control (control)
# ===========================================================================
# Bloques que gobiernan CUÁNDO se ejecuta el grafo. Emiten señales `trigger`.

BLOCK_TIMER = BlockSpec(
    id="block.timer",
    category="control",
    name_key="block.timer.name",
    description_key="block.timer.desc",
    inputs=(),
    outputs=(_out("tick", "port.trigger", (ValueType.TRIGGER,)),),
    params=(_p("interval_ms", "param.interval_ms", type="number", kind="int", default=100, min=1),),
    behavior="continuous",
)

BLOCK_MANUAL_TRIGGER = BlockSpec(
    id="block.manual_trigger",
    category="control",
    name_key="block.manual_trigger.name",
    description_key="block.manual_trigger.desc",
    inputs=(),
    outputs=(_out("tick", "port.trigger", (ValueType.TRIGGER,)),),
    params=(),
    behavior="on_trigger",
)

BLOCK_PAUSE_RESUME = BlockSpec(
    id="block.pause_resume",
    category="control",
    name_key="block.pause_resume.name",
    description_key="block.pause_resume.desc",
    # Puerta de datos: acepta CUALQUIER tipo de dato y lo deja pasar o no.
    inputs=(_in("in", "port.any", (ValueType.FRAME, ValueType.NUMBER, ValueType.BOOLEAN,
                                   ValueType.STRING, ValueType.COORDINATES, ValueType.RECTANGLE,
                                   ValueType.DETECTIONS, ValueType.ANALYSIS)),),
    outputs=(_out("out", "port.any", (ValueType.FRAME, ValueType.NUMBER, ValueType.BOOLEAN,
                                      ValueType.STRING, ValueType.COORDINATES, ValueType.RECTANGLE,
                                      ValueType.DETECTIONS, ValueType.ANALYSIS)),),
    params=(),
    behavior="passthrough",
)

# ===========================================================================
# Procesamiento (processing)
# ===========================================================================
# Transforman imágenes (frame -> frame). Aquí vive la lógica OpenCV que se
# implementará en la fase 5/8; de momento solo el contrato.

BLOCK_GRAYSCALE = BlockSpec(
    id="block.grayscale",
    category="processing",
    name_key="block.grayscale.name",
    description_key="block.grayscale.desc",
    inputs=(_in("in", "port.frame", (ValueType.FRAME,)),),
    outputs=(_out("out", "port.frame", (ValueType.FRAME,)),),
    params=(),
    behavior="passthrough",
)

BLOCK_BLACK_WHITE = BlockSpec(
    id="block.black_white",
    category="processing",
    name_key="block.black_white.name",
    description_key="block.black_white.desc",
    inputs=(_in("in", "port.frame", (ValueType.FRAME,)),),
    outputs=(_out("out", "port.frame", (ValueType.FRAME,)),),
    # threshold: umbral de binarización simple (valores 0-255).
    params=(_p("threshold", "param.threshold", type="number", kind="int", default=127, min=0, max=255),),
    behavior="passthrough",
)

BLOCK_THRESHOLD = BlockSpec(
    id="block.threshold",
    category="processing",
    name_key="block.threshold.name",
    description_key="block.threshold.desc",
    inputs=(_in("in", "port.frame", (ValueType.FRAME,)),),
    outputs=(_out("out", "port.frame", (ValueType.FRAME,)),),
    params=(
        _p("threshold", "param.threshold", type="number", kind="int", default=127, min=0, max=255),
        _p("max_value", "param.max_value", type="number", kind="int", default=255, min=0, max=255),
        # type: nombre del modo OpenCV (cv2.THRESH_*). Se mapea en el ejecutor.
        _p(
            "type",
            "param.threshold_type",
            type="select",
            default="THRESH_BINARY",
            options=("THRESH_BINARY", "THRESH_BINARY_INV", "THRESH_TRUNC", "THRESH_TOZERO", "THRESH_TOZERO_INV"),
        ),
    ),
    behavior="passthrough",
)

BLOCK_BLUR = BlockSpec(
    id="block.blur",
    category="processing",
    name_key="block.blur.name",
    description_key="block.blur.desc",
    inputs=(_in("in", "port.frame", (ValueType.FRAME,)),),
    outputs=(_out("out", "port.frame", (ValueType.FRAME,)),),
    params=(
        # kernel debe ser impar (1, 3, 5...) para GaussianBlur; `odd=True` lo
        # impone en la validación y la UI solo ofrece impares (poka-yoke).
        _p("kernel", "param.kernel", type="number", kind="int", default=5, min=1, max=99, odd=True),
        _p("sigma", "param.sigma", type="number", kind="float", default=0.0, min=0.0),
    ),
    behavior="passthrough",
)

BLOCK_EDGE_DETECTION = BlockSpec(
    id="block.edge_detection",
    category="processing",
    name_key="block.edge_detection.name",
    description_key="block.edge_detection.desc",
    inputs=(_in("in", "port.frame", (ValueType.FRAME,)),),
    outputs=(_out("out", "port.frame", (ValueType.FRAME,)),),
    params=(
        # Umbrales alto y bajo del detector Canny.
        _p("low", "param.low_threshold", type="number", kind="int", default=100, min=0, max=1000),
        _p("high", "param.high_threshold", type="number", kind="int", default=200, min=0, max=1000),
    ),
    behavior="passthrough",
)

BLOCK_CONTOURS = BlockSpec(
    id="block.contours",
    category="processing",
    name_key="block.contours.name",
    description_key="block.contours.desc",
    inputs=(_in("in", "port.frame", (ValueType.FRAME,)),),
    outputs=(
        # Dos salidas: las detecciones (para análisis) y un frame opcional con
        # los contornos dibujados (para visualizar).
        _out("detections", "port.detections", (ValueType.DETECTIONS,)),
        _out("out", "port.frame", (ValueType.FRAME,)),
    ),
    params=(
        _p("retrieve_mode", "param.retrieve_mode", type="select",
           default="RETR_EXTERNAL", options=("RETR_EXTERNAL", "RETR_LIST", "RETR_TREE")),
        _p("approx", "param.approx", type="select",
           default="CHAIN_APPROX_SIMPLE", options=("CHAIN_APPROX_NONE", "CHAIN_APPROX_SIMPLE")),
        _p("min_area", "param.min_area", type="number", kind="int", default=10, min=0),
    ),
    behavior="passthrough",
)

BLOCK_DRAW_TEXT = BlockSpec(
    id="block.draw_text",
    category="processing",
    name_key="block.draw_text.name",
    description_key="block.draw_text.desc",
    inputs=(_in("in", "port.frame", (ValueType.FRAME,)),),
    outputs=(_out("out", "port.frame", (ValueType.FRAME,)),),
    params=(
        # text: texto literal a dibujar sobre la imagen (no es clave i18n: es
        # contenido del usuario, no etiqueta de la interfaz).
        _p("text", "param.text", type="string", default="VisionStudio"),
        _p("x", "param.x", type="number", kind="int", default=10, min=0),
        _p("y", "param.y", type="number", kind="int", default=30, min=0),
        _p("size", "param.font_size", type="number", kind="float", default=1.0, min=0.1, max=10.0),
        # color: tupla BGR. Default (0, 255, 0) = verde.
        _p("color", "param.color", type="color", default=(0, 255, 0)),
    ),
    behavior="passthrough",
)

# ===========================================================================
# Análisis (analysis)
# ===========================================================================
# Reducen o transforman datos en resultados (números, booleanos, rectángulos,
# listas de detecciones, OK/NOK). Algunos son fuentes de valor (sin entradas).

BLOCK_OK_NOK = BlockSpec(
    id="block.ok_nok",
    category="analysis",
    name_key="block.ok_nok.name",
    description_key="block.ok_nok.desc",
    # Acepta tanto un analysis como un boolean simple y lo normaliza a analysis.
    inputs=(_in("in", "port.analysis", (ValueType.ANALYSIS, ValueType.BOOLEAN)),),
    outputs=(_out("out", "port.analysis", (ValueType.ANALYSIS,)),),
    params=(),
    behavior="passthrough",
)

BLOCK_COMPARE = BlockSpec(
    id="block.compare",
    category="analysis",
    name_key="block.compare.name",
    description_key="block.compare.desc",
    inputs=(_in("in", "port.number", (ValueType.NUMBER,)),),
    outputs=(_out("out", "port.boolean", (ValueType.BOOLEAN,)),),
    params=(
        # op: operador de comparación entre la entrada y el reference.
        _p("op", "param.operator", type="select", default=">=",
           options=("==", "!=", "<", "<=", ">", ">=")),
        _p("reference", "param.reference", type="number", kind="float", default=0.0),
    ),
    behavior="passthrough",
)

BLOCK_NUMERIC_VALUE = BlockSpec(
    id="block.numeric_value",
    category="analysis",
    name_key="block.numeric_value.name",
    description_key="block.numeric_value.desc",
    inputs=(),
    outputs=(_out("out", "port.number", (ValueType.NUMBER,)),),
    # Fuente de valor: emite continuamente el número configurado.
    params=(_p("value", "param.value", type="number", kind="float", default=0.0),),
    behavior="continuous",
)

BLOCK_COORDINATES = BlockSpec(
    id="block.coordinates",
    category="analysis",
    name_key="block.coordinates.name",
    description_key="block.coordinates.desc",
    inputs=(),
    outputs=(_out("out", "port.coordinates", (ValueType.COORDINATES,)),),
    # Fuente de coordenadas: emite continuamente el punto configurado.
    params=(
        _p("x", "param.x", type="number", kind="int", default=0, min=0),
        _p("y", "param.y", type="number", kind="int", default=0, min=0),
    ),
    behavior="continuous",
)

BLOCK_RECTANGLES = BlockSpec(
    id="block.rectangles",
    category="analysis",
    name_key="block.rectangles.name",
    description_key="block.rectangles.desc",
    # Entrada opcional: si hay detecciones, extrae la primera como rectángulo;
    # si no, usa los parámetros manuales x/y/w/h.
    inputs=(_in("detections", "port.detections", (ValueType.DETECTIONS,), required=False),),
    outputs=(_out("out", "port.rectangle", (ValueType.RECTANGLE,)),),
    params=(
        _p("x", "param.x", type="number", kind="int", default=0, min=0),
        _p("y", "param.y", type="number", kind="int", default=0, min=0),
        _p("w", "param.width", type="number", kind="int", default=10, min=0),
        _p("h", "param.height", type="number", kind="int", default=10, min=0),
    ),
    behavior="passthrough",
)

BLOCK_DETECTION_LIST = BlockSpec(
    id="block.detection_list",
    category="analysis",
    name_key="block.detection_list.name",
    description_key="block.detection_list.desc",
    inputs=(_in("in", "port.frame", (ValueType.FRAME,)),),
    outputs=(_out("detections", "port.detections", (ValueType.DETECTIONS,)),),
    # En el MVP actúa como envoltura de detección sobre frames (p. ej. a partir
    # de contornos). Preparado para YOLO en el futuro.
    params=(
        _p("max_items", "param.max_items", type="number", kind="int", default=10, min=1, max=100),
        _p("min_confidence", "param.min_confidence", type="number", kind="float", default=0.5, min=0.0, max=1.0),
    ),
    behavior="passthrough",
)

# ===========================================================================
# Salidas (output)
# ===========================================================================
# Consumen datos y los PUBLICAN hacia el frontend vía WebSocket. No tienen
# salidas: son el final del grafo.

BLOCK_SINK_IMAGE = BlockSpec(
    id="block.sink_image",
    category="output",
    name_key="block.sink_image.name",
    description_key="block.sink_image.desc",
    inputs=(_in("in", "port.frame", (ValueType.FRAME,)),),
    outputs=(),
    params=(),
    behavior="passthrough",
)

BLOCK_SINK_TEXT = BlockSpec(
    id="block.sink_text",
    category="output",
    name_key="block.sink_text.name",
    description_key="block.sink_text.desc",
    inputs=(_in("in", "port.string", (ValueType.STRING,)),),
    outputs=(),
    params=(),
    behavior="passthrough",
)

BLOCK_SINK_BOOLEAN = BlockSpec(
    id="block.sink_boolean",
    category="output",
    name_key="block.sink_boolean.name",
    description_key="block.sink_boolean.desc",
    inputs=(_in("in", "port.boolean", (ValueType.BOOLEAN,)),),
    outputs=(),
    params=(),
    behavior="passthrough",
)

BLOCK_STATUS_INDICATOR = BlockSpec(
    id="block.status_indicator",
    category="output",
    name_key="block.status_indicator.name",
    description_key="block.status_indicator.desc",
    # Muestra estado OK/NOK; acepta un analysis o un boolean directo.
    inputs=(_in("in", "port.analysis", (ValueType.ANALYSIS, ValueType.BOOLEAN)),),
    outputs=(),
    params=(),
    behavior="passthrough",
)

# ===========================================================================
# Registro completo
# ===========================================================================
# El orden aquí determina el orden de presentación en la biblioteca lateral.
# Todos los bloques del MVP (21). Cualquier bloque nuevo se añade a esta tupla.

ALL_BLOCKS: tuple[BlockSpec, ...] = (
    BLOCK_CAMERA,
    BLOCK_TIMER,
    BLOCK_MANUAL_TRIGGER,
    BLOCK_PAUSE_RESUME,
    BLOCK_GRAYSCALE,
    BLOCK_BLACK_WHITE,
    BLOCK_THRESHOLD,
    BLOCK_BLUR,
    BLOCK_EDGE_DETECTION,
    BLOCK_CONTOURS,
    BLOCK_DRAW_TEXT,
    BLOCK_OK_NOK,
    BLOCK_COMPARE,
    BLOCK_NUMERIC_VALUE,
    BLOCK_COORDINATES,
    BLOCK_RECTANGLES,
    BLOCK_DETECTION_LIST,
    BLOCK_SINK_IMAGE,
    BLOCK_SINK_TEXT,
    BLOCK_SINK_BOOLEAN,
    BLOCK_STATUS_INDICATOR,
)