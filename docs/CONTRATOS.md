# Contratos de bloques y tipos de datos

Fecha: 2026/09/13
Estado: Aprobado (revisión inicial)
Autor: Agent Architecture

Este documento define el contrato formal que implementarán Backend y Frontend.
Los identificadores son **estables**: no se renombran ni reutilizan.

## 1. Tipos de datos

Unión discriminada; el campo `type` identifica el tipo.

| `type` | Esquema | Notas |
|--------|---------|-------|
| `frame` | imagen OpenCV (BGR, numpy) | Interno; no se serializa en el proyecto. En el transporte: JPEG/base64 |
| `number` | `{ type:"number", value: number }` | `float` |
| `boolean` | `{ type:"boolean", value: bool }` | |
| `string` | `{ type:"string", value: str }` | |
| `coordinates` | `{ type:"coordinates", value:{x,y} }` | enteros o flotantes |
| `rectangle` | `{ type:"rectangle", value:{x,y,w,h} }` | |
| `detections` | `{ type:"detections", value:[{label, confidence, x, y, w, h}] }` | |
| `analysis` | `{ type:"analysis", value:{ok: bool, detail?: str} }` | OK/NOK |
| `trigger` | señal interna de control (Timer/Manual) | No es dato serializable; solo conecta fuentes o disparadores |

## 2. Esquema de un bloque

```jsonc
{
  "id": "block.camera",            // identificador ESTABLE
  "category": "source",            // source | control | processing | analysis | output
  "name_key": "block.camera.name", // clave i18n
  "description_key": "block.camera.desc",
  "inputs":  [ { "id":"in", "label_key":"...", "type":"frame", "required":true } ],
  "outputs": [ { "id":"out", "label_key":"...", "type":"frame" } ],
  "params": [
    {
      "id":"camera_index", "label_key":"...", "type":"number", "kind":"int",
      "default":0, "min":0, "required":true,
      "validation": { "min":0 }
    }
  ],
  "behavior": "continuous"  // continuo | on_tick | on_trigger | passthrough
}
```

Campos de parámetro:
- `type`: `number | boolean | string | select | color`
- `default`, `min`, `max`, `step`, `options` (para `select`), `validation`
- `required`

Validaciones de conexión: el tipo de la salida debe ser compatible con el tipo de la
entrada (tipos idénticos en el MVP; `frame` y `detections` permiten subtipos futuros).

## 3. Bloques del MVP

### Fuentes (source)

| id | Parámetros | Salida | Comportamiento |
|----|-----------|--------|----------------|
| `block.camera` | `camera_index:number(0)`, `width:number(640)`, `height:number(480)` | `trigger?` (opcional) | `frame` | Captura continua, o 1 frame por tick/trigger. Requiere cámara abierta |

### Control (control)

| id | Parámetros | Entrada | Salida | Comportamiento |
|----|-----------|---------|--------|----------------|
| `block.timer` | `interval_ms:number(100)` | — | `tick:trigger` | Emite ticks a intervalos; cada tick dispara el grafo |
| `block.manual_trigger` | — | — | `tick:trigger` | Emite un tick por petición del usuario (botón "frame") |
| `block.pause_resume` | — | `in` (cualquier tipo de dato) | `out` (mismo tipo) | Bloque puerta: pausado no propaga el valor entrante (conserva el último); reanudado lo deja pasar |

> El MVP simplifica: los controles (Timer, Manual, Pausa) también se gestionan en la
> barra de control; el bloque Timer puede añadirse al grafo para temporizar una fuente
> conectando su salida `tick` a la entrada `trigger` de la cámara.

### Procesamiento (processing)

| id | Parámetros | Entrada | Salida | Notas |
|----|-----------|---------|--------|-------|
| `block.grayscale` | — | `frame` | `frame` | `cv2.cvtColor BGR2GRAY` (emitido como 3 canales para Sink) |
| `block.black_white` | `threshold:number(127)` | `frame` | `frame` | Binarización simple |
| `block.threshold` | `threshold:number(127)`, `max_value:number(255)`, `type:select(THRESH_BINARY, THRESH_BINARY_INV, ...)` | `frame` | `frame` | `cv2.threshold` |
| `block.blur` | `kernel:number(5)` (impar, >=1), `sigma:number(0)` | `frame` | `frame` | `cv2.GaussianBlur` |
| `block.edge_detection` | `low:number(100)`, `high:number(200)` | `frame` | `frame` | `cv2.Canny` |
| `block.contours` | `retrieve_mode:select`, `approx:select` | `frame` | `detections` + `frame` (opcional dibujado) | `cv2.findContours` |
| `block.draw_text` | `text:string("")`, `x:number`, `y:number`, `size:number(1)`, `color:color(0,255,0)` | `frame` | `frame` | `cv2.putText` |

### Análisis (analysis)

| id | Parámetros | Entrada | Salida | Notas |
|----|-----------|---------|--------|-------|
| `block.ok_nok` | `rule:select` | `boolean` u `analysis` | `analysis` | Traduce booleano/estado a OK/NOK |
| `block.compare` | `op:select(==, !=, <, <=, >, >=)`, `reference:number` | `number` | `boolean` | Compara valor de entrada con referencia |
| `block.numeric_value` | `value:number(0)` | — | `number` | Fuente de valor numérico (configurable) |
| `block.coordinates` | `x:number(0)`, `y:number(0)` | — | `coordinates` | Fuente/transformación de coordenadas |
| `block.rectangles` | `x,y,w,h` por defecto | `detections` | `rectangle` | Primer rectángulo de una detección |
| `block.detection_list` | `max_items:number(10)`, `min_confidence:number(0.5)` | `frame` | `detections` | En el MVP: envoltura de contornos u otras fuentes |

> `rectangles` y `detection_list` quedan implementados en la fase 8; las firmas
> de esta tabla son el contrato estable.

### Salidas (output)

| id | Entrada | Publica en WebSocket | Notas |
|----|---------|----------------------|-------|
| `block.sink_image` | `frame` | `{type:"frame", sink, data}` | Muestra la imagen |
| `block.sink_text` | `string` | `{type:"text", sink, value}` | Muestra texto |
| `block.sink_boolean` | `boolean` | `{type:"boolean", sink, value}` | Muestra booleano |
| `block.status_indicator` | `analysis` o `boolean` | `{type:"status", sink, value}` | Indicador OK/NOK con color |

## 4. Comportamiento ante errores

- `ERR_CAMERA_OPEN`: no se puede abrir la cámara del índice pedido.
- `ERR_CAMERA_RELEASE`: fallo al liberar la cámara (se registra y continúa).
- `ERR_CONNECTION_TYPE`: conexión entre tipos incompatibles (se rechaza al validar el grafo).
- `ERR_GRAPH_CYCLE`: el grafo contiene un ciclo (no es un DAG válido).
- `ERR_GRAPH_EDIT_WHILE_RUNNING`: se intentó editar el grafo en ejecución.
- `ERR_BLOCK_NOT_FOUND` / `ERR_PORT_NOT_FOUND`: referencia a bloque/puerto inexistente.
- `ERR_PORT_ALREADY_CONNECTED`: un puerto de entrada con más de una conexión.
- `ERR_BLOCK_INPUT_MISSING`: una entrada requerida de un bloque no está conectada.
- `ERR_PARAM_INVALID`: parámetro fuera de rango o inválido (incluye el id del parámetro).
- `ERR_BLOCK_EXECUTION`: fallo al ejecutar un bloque (sin ejecutor, o excepción interna con contexto del nodo).
- `ERR_PROJECT_VERSION_UNSUPPORTED`: versión de proyecto mayor que la soportada.
- `ERR_MIGRATION_FAILED`: fallo durante una migración de proyecto.
- `ERR_INTERNAL`: error no clasificado (se incluye el mensaje interno como parámetro).

Cada error lleva `code` (estable) y `params` (diccionario serializable). El frontend
traduce `code` y formatea con `params`.

## 5. Conexiones

```jsonc
{ "from": { "block": "nodo_1", "port": "out" }, "to": { "block": "nodo_2", "port": "in" } }
```

- Un puerto de entrada acepta **una** conexión (MVP); un puerto de salida puede tener **N**.
- Se rechazan: tipos incompatibles, ciclos, puertos inexistentes, puertos ya ocupados.
- Los mensajes de error de validación de conexión se muestran en el panel de errores.

## 6. Estado y transiciones

Estados del flujo: `stopped`, `running`, `paused`.

| Transición | Comando |
|-----------|---------|
| `stopped -> running` | start |
| `running -> paused` | pause |
| `paused -> running` | resume |
| `running|paused -> stopped` | stop |
| `stopped -> running` (1 frame) | step (solo si hay fuente manual) |

Regla: el grafo solo es editable en `stopped`.