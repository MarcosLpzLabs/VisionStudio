# Arquitectura de VisionStudio

Fecha: 2026/09/13
Estado: Aprobado (revisión inicial)
Autor: Agent Architecture (coordinado por agente maestro)

## 1. Objetivo

Aplicación local educativa de visión artificial basada en bloques visuales conectables.
El usuario construye flujos `Fuente -> Procesamiento -> Análisis -> Sink` sin escribir código.

Flujo mínimo: `Cámara -> Escala de grises -> Sink de imagen`.

## 2. Principios

1. **Separación estricta** entre frontend y backend. El backend no depende de ningún
   componente visual; el frontend no implementa lógica OpenCV.
2. **Backend autónomo**: debe poder probarse y usarse por API/REST y WebSocket sin frontend.
3. **Contratos estables**: identificadores de bloques estables y versionados.
4. **Backend servidor de la aplicación**: el frontend compilado se sirve desde el backend
   (aplicación unificada) en producción; en desarrollo Vite sirve el frontend con proxy a la API.
5. **Portabilidad**: funciona en Arch/CachyOS y, por diseño, en Windows (sin rutas hardcodeadas,
   sin APIs específicas de Linux, gestión de cámaras a través de OpenCV).
6. **Extensibilidad**: el motor de ejecución y los contratos están preparados para múltiples
   cámaras, múltiples Sink y bloques YOLO (Ultralytics).

## 3. Capas (límites)

| Capa | Directorio | Responsabilidad |
|------|-----------|-----------------|
| 1. Definiciones de bloques | `backend/visionstudio/blocks` | Registro declarativo de bloques (metadatos, entradas, salidas, parámetros, validación) |
| 2. Motor de ejecución del grafo | `backend/visionstudio/engine` | Orden topológico, propagación de eventos, ejecución de nodos, validación de conexiones |
| 3. Captura de cámara | `backend/visionstudio/camera` | Detección, apertura, lectura de frames, liberación limpia |
| 4. Gestión de ejecución y Timer | `backend/visionstudio/runloop` | Modos continuo/timer/manual, pausa, detención, reinicio |
| 5. API local | `backend/visionstudio/api` | FastAPI: REST (proyectos, cámaras, control) |
| 6. Comunicación en tiempo real | `backend/visionstudio/api` | WebSocket: frames, estado, errores |
| 7. Persistencia y migraciones | `backend/visionstudio/persistence` | Guardado/carga JSON versionado + registro de migraciones |
| 8. Frontend visual | `frontend/src` | React + TS + React Flow, biblioteca de bloques, paneles, Sink |
| 9. Sistema de traducciones | `frontend/src/i18n` + `backend/visionstudio/i18n` | Catálogos es/en por claves estables |
| 10. Pruebas | `backend/tests` + `frontend` | Unitarias, integración, persistencia, migraciones, ejecución |

Reglas de capa:
- Las capas 2-7 dependen de la capa 1 (contratos), nunca a la inversa.
- La capa 5/6 dependen de 2, 3 y 7.
- La capa 8 solo consume la API (5/6) y los catálogos (9).
- Las capas 2-7 no deben importar nada de `frontend`.

## 4. Modelo de datos (tipos)

Tipos del sistema (unión discriminada por campo `type`). Definidos en
`backend/visionstudio/types` y replicados como contratos en `docs/CONTRATOS.md`.

| Tipo | Campo `type` | Contenido |
|------|-------------|-----------|
| Frame/Imagen | `frame` | Imagen OpenCV (nunca se serializa en el archivo de proyecto) |
| Número | `number` | `float` |
| Booleano | `boolean` | `bool` |
| Texto | `string` | `str` |
| Coordenadas | `coordinates` | `{x, y}` |
| Rectángulo | `rectangle` | `{x, y, w, h}` |
| Lista de detecciones | `detections` | `[{label, confidence, x, y, w, h}]` |
| Resultado de análisis | `analysis` | `{ok: bool, detail?: str}` |

Todas las conexiones se validan por tipo. Conexión incompatible -> rechazo o error
explicativo.

## 5. Motor de ejecución

### 5.1 Modelo

- El grafo es un DAG de nodos (bloques) y aristas (conexiones entre puerto de salida
  y puerto de entrada).
- Un nodo **Fuente** produce datos (frames) cuando recibe un *tick* de disparo.
- Un nodo **Procesamiento/Análisis** consume entradas, calcula y produce salidas.
- Un nodo **Sink** consume entradas y las publica (imagen al WebSocket, texto, booleano,
  indicador de estado).
- La ejecución se propaga por orden topológico: cada evento `run` recorre las aristas.

### 5.2 Semántica de ejecución

| Modo | Descripción |
|------|-------------|
| Continuo | La cámara publica frames a su FPS y el grafo se ejecuta por cada frame |
| Timer | Un bloque Timer emite ticks a un intervalo; cada tick dispara un frame y su propagación |
| Manual | El usuario pide un único frame: la cámara captura una vez y se propaga |
| Pausa | Se detiene la adquisición de nuevos frames/tick; el grafo queda en memoria |
| Detención | Se libera la cámara, se cancelan tareas y se reinicia el estado del grafo |
| Reinicio | Detención + inicio de nuevo con la misma configuración |

- Mientras el flujo está **en ejecución**, el grafo es de solo lectura (no se pueden
  editar bloques ni conexiones). Para editar hay que detener.
- La combinación de modos es válida: p. ej., Timer + Pausa.

### 5.3 Hilos y concurrencia

- `RunLoop` (capa 4) gestiona un hilo de captura/productor y un hilo de ejecución.
- Los Sink publican resultados vía WebSocket sin bloquear el hilo de procesamiento.
- Detención limpia: `stop_event` cooperativo + `join` con timeout + `camera.release()`.
- Sin `cv2.imshow` en el backend; la visualización es responsabilidad del frontend.

## 6. API y tiempo real

### REST (`/api`)
- `GET /api/cameras` -> lista de cámaras disponibles `[{index, name}]`.
- `GET /api/project` / `PUT /api/project` -> leer/guardar proyecto (JSON versionado).
- `POST /api/run/start`, `/api/run/stop`, `/api/run/pause`, `/api/run/resume`,
  `/api/run/step` -> control de ejecución.
- `GET /api/i18n/{lang}` -> catálogo de traducciones (o embebido en el frontend).

### WebSocket (`/ws`)
- Mensajes del servidor: `{type:"frame", sink, data}` (imagen JPEG base64),
  `{type:"text"|"boolean"|"analysis"|"status", sink, value}`,
  `{type:"state", state}` (estado del flujo), `{type:"error", code, params}`.
- Mensajes del cliente: comandos de control equivalentes a REST (redundancia para robustez).

### Contratos de error
- Los errores se comunican con **códigos estables** (p. ej. `ERR_CAMERA_OPEN`) + parámetros.
- El frontend traduce los códigos con el catálogo de i18n.
- La lista de códigos se documenta en `docs/CONTRATOS.md`.

## 7. Persistencia y migraciones

- Formato de proyecto: JSON con campo `format_version` (entero, comienza en 1).
- Cada versión dispone de una **función de migración** `migrate_vN_to_vN+1` registrada
  en `persistence/migrations`.
- Carga de un proyecto: si `format_version` es menor, se encadenan migraciones hasta la
  versión actual. Si es mayor, se rechaza con error explicativo.
- Contenido del archivo: versión, bloques (id, tipo, posición, parámetros),
  conexiones, configuración de cámara, configuración de flujo, idioma preferido.
- El formato está en `docs/FORMATO_PROYECTO.md` (se detallará en la fase 9).

## 8. Internacionalización

- Todos los textos visibles usan **claves** (p. ej. `block.camera.name`,
  `ui.run`, `err.camera_open`), nunca texto directo en componentes.
- Catálogos JSON en español e inglés (`es`, `en`).
- Selector de idioma en la interfaz; el idioma preferido se guarda en el proyecto.
- Los nombres/descripciones de bloques y las categorías se traducen con las mismas claves.
- El backend puede devolver mensajes localizados o códigos; se prefiere **código + parámetros**.

## 9. Frontend

- React + TypeScript + Vite.
- React Flow para el editor de grafos (bloques, conexiones, zoom, pan).
- Componentes: biblioteca lateral de bloques agrupados por categoría, lienzo central,
  panel de propiedades, vista previa de cámara, Sink múltiples, barra de control
  (ejecutar/detener/pausar/reanudar/frame), guardar/cargar, selector de idioma,
  panel de errores, barra de estado e indicador de conexión con el backend.
- Estado global con Zustand (ligero y sin boilerplate) o React Context; decisión final
  en la fase 7.
- **El frontend nunca importa OpenCV**; recibe frames por WebSocket.
- Durante la ejecución, los controles de edición del grafo quedan deshabilitados.

## 10. Despliegue / arranque

- **Desarrollo**: `uvicorn` en `:8000` (backend) y Vite en `:5173` (frontend) con proxy.
- **Producción**: `frontend/dist` servido por FastAPI como estático; una sola aplicación
  en `http://localhost:8000`.
- Comandos documentados en `docs/GUIA_USO.md` (fase 13).

## 11. Preparación para el futuro

- **Múltiples cámaras**: el contrato de Fuente Cámara lleva `camera_index`; el registro
  de fuentes permite instanciar N cámaras. La API ya expone la lista de cámaras.
- **Múltiples Sink**: el WebSocket direcciona por `sink` (id del bloque Sink).
- **YOLO**: un bloque futuro con entrada `frame` y salida `detections`/`analysis`,
  ejecutado por Ultralytics; no requiere cambios en el motor.

## 12. Decisiones registradas

| # | Decisión | Motivo |
|---|----------|--------|
| A1 | Backend sirve el frontend compilado en producción | Aplicación unificada, sin CORS en producción |
| A2 | Los bloques son declarativos (metadatos) + ejecutor | Facilita validación, traducción, serialización y testeo |
| A3 | Errores como códigos estables + parámetros | i18n en frontend sin depender del backend |
| A4 | El motor ejecuta por orden topológico con propagación | Semántica simple y determinista |
| A5 | Frame transportado como JPEG/base64 por WebSocket | Formato universal, sin dependencia OpenCV en el cliente |
| A6 | Un solo hilo de productor + un hilo de ejecución | Evita condiciones de carrera en el MVP |
| A7 | Grafo bloqueado (solo lectura) en ejecución | Evita inconsistencias y reconfiguraciones peligrosas |