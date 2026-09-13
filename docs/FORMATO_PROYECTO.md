# Formato de proyecto VisionStudio

Fecha: 2026/09/13
Estado: Aprobado (fase 9)
Autor: Agent Architecture

Un proyecto es un archivo JSON con versión de formato explícita. La versión
actual es **1**. Este documento define el formato, las reglas de versionado y
el contrato de migraciones.

## 1. Estructura general

```json
{
  "format_version": 1,
  "name": "proyecto",
  "language": "es",
  "camera": { "index": 0, "width": 640, "height": 480 },
  "flow": { "mode": "continuous", "interval_ms": 100 },
  "blocks": [
    { "id": "n1", "type": "block.camera", "x": 0, "y": 0, "params": { "camera_index": 0 } }
  ],
  "connections": [
    { "from": { "block": "n1", "port": "out" }, "to": { "block": "n2", "port": "in" } }
  ]
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `format_version` | `int` | Versión del formato (actual: 1). Obligatorio. |
| `name` | `string` | Nombre del proyecto. Default `"Untitled"`. |
| `language` | `string` | Idioma preferido (`es`/`en`). Default `"es"`. |
| `camera` | `object` | Configuración de cámara por defecto (`index`, `width`, `height`). |
| `flow` | `object` | Modo de ejecución (`mode`: `continuous`/`timer`/`manual`) e `interval_ms`. |
| `blocks` | `array` | Nodos del grafo. |
| `connections` | `array` | Aristas del grafo (una entrada por puerto). |

## 2. Bloques

```json
{ "id": "n1", "type": "block.grayscale", "x": 120, "y": 80, "params": {} }
```

- `id`: identificador del nodo dentro del proyecto (único). Estable por archivo.
- `type`: identificador ESTABLE del bloque (ver `docs/CONTRATOS.md` §3).
- `x`, `y`: posición en el lienzo (float).
- `params`: solo los parámetros MODIFICADOS por el usuario; los no presentes se
  completan con los valores por defecto del bloque al ejecutar.

## 3. Conexiones

```json
{ "from": { "block": "n1", "port": "out" }, "to": { "block": "n2", "port": "in" } }
```

- `from.block`/`to.block`: ids de nodo del archivo.
- `from.port`/`to.port`: ids de puerto de la especificación del bloque.
- Regla MVP: una entrada acepta **una** conexión; una salida puede tener N.
- La validación estructural completa (tipos, ciclos, puertos, entradas
  requeridas) la aplica `GraphValidator` antes de aceptar el proyecto.

## 4. Versionado y migraciones

- Cada versión del formato tiene una función de migración `migrate_vN_to_vN+1`
  registrada en `backend/visionstudio/persistence/migrations.py`.
- **Carga de un proyecto:**
  - `format_version` igual a la actual -> se parsea directamente.
  - `format_version` MENOR -> se encadenan las migraciones registradas hasta la
    versión actual y se parsea el resultado migrado.
  - `format_version` MAYOR -> se rechaza con `ERR_PROJECT_VERSION_UNSUPPORTED`.
  - `format_version` ausente o no entero -> `ERR_PROJECT_VERSION_UNSUPPORTED`.
- Si una migración falta o falla durante el encadenamiento, se lanza
  `ERR_MIGRATION_FAILED` y el proyecto se rechaza (nunca se carga a medias).
- Contrato de una migración: función pura `dict -> dict` que convierte un
  proyecto de versión `N` a `N+1`; debe actualizar `format_version` al nuevo
  valor. No debe mutar el dict de entrada.
- Regla de guardado: siempre se guarda con la versión ACTUAL del backend.

## 5. Códigos de error relacionados

| Código | Parámetros | Situación |
|--------|-----------|-----------|
| `ERR_PROJECT_VERSION_UNSUPPORTED` | `version` | Versión futura, ausente o no entera. |
| `ERR_MIGRATION_FAILED` | `from_version`, `to_version`, `detail` | Migración ausente o fallida. |

## 6. Ejemplo completo (formato v1)

```json
{
  "format_version": 1,
  "name": "Grises con umbral",
  "language": "es",
  "camera": { "index": 0, "width": 640, "height": 480 },
  "flow": { "mode": "continuous", "interval_ms": 100 },
  "blocks": [
    { "id": "cam", "type": "block.camera", "x": 20, "y": 60, "params": {} },
    { "id": "gray", "type": "block.grayscale", "x": 220, "y": 60, "params": {} },
    { "id": "thr", "type": "block.threshold", "x": 420, "y": 60, "params": { "threshold": 127 } },
    { "id": "sink", "type": "block.sink_image", "x": 620, "y": 60, "params": {} }
  ],
  "connections": [
    { "from": { "block": "cam", "port": "out" }, "to": { "block": "gray", "port": "in" } },
    { "from": { "block": "gray", "port": "out" }, "to": { "block": "thr", "port": "in" } },
    { "from": { "block": "thr", "port": "out" }, "to": { "block": "sink", "port": "in" } }
  ]
}
```