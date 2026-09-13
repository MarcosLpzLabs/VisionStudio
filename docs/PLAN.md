# Plan de desarrollo

Fecha: 2026/09/13
Estado: En curso (fase 10)
Fuente: Prompt maestro

## Reglas de avance

- No avanzar a una fase posterior si la anterior no tiene pruebas y documentación.
- Ejecutar Quality después de cada fase relevante.
- Ejecutar Report (avance.md) tras cada avance, bug solucionado o mejora.
- Las decisiones importantes no especificadas se consultan antes de implementar.

## Fases

| Fase | Descripción | Entregable | Estado |
|------|-------------|-----------|--------|
| 1 | Arquitectura y decisiones | `docs/ARQUITECTURA.md`, `docs/CONTRATOS.md` | **En curso** |
| 2 | Contratos de bloques y tipos | `docs/CONTRATOS.md` (completo), `types` + `blocks/registry` implementados (57 pruebas) | **Completado** |
| 3 | Motor de ejecución sin interfaz | `engine/` con DAG, orden topológico, validación de conexiones + tests | **Completado** |
| 4 | Captura de cámara y Timer | `camera/` (detección, apertura, frames, liberación), `runloop/` (modos, pausa, stop) + tests | **Completado** |
| 5 | Cámara, Escala de grises, Sink imagen | Bloques mínimos end-to-end sin UI (ejecutores OpenCV + pipeline) | **Completado** |
| 6 | API y tiempo real | FastAPI REST + WebSocket (frames, estado, errores) + tests | **Completado** |
| 7 | Editor visual | Frontend React+TS+Vite+React Flow, biblioteca, lienzo, paneles, controles | **Completado** |
| 8 | Resto de bloques MVP | Todos los bloques de `docs/CONTRATOS.md` con pruebas por bloque | **Completado** |
| 9 | Guardado, carga y migraciones | `persistence/` + registro de migraciones + tests | **Completado** |
| 10 | Español e inglés | Catálogos i18n `es`/`en`, selector de idioma, textos migrados a claves | Pendiente |
| 11 | Pruebas funcionales, rendimiento, compatibilidad | Ejecución de Quality + tests completos | Pendiente |
| 12 | Revisión de integración completa | Flujo end-to-end verificado (cámara -> bloque -> Sink -> UI) | Pendiente |
| 13 | Documentación del sistema | Guías de instalación, uso, creación de bloques, formato, troubleshooting | Pendiente |
| 14 | Preparación multi-cámara, multi-Sink y YOLO | Contratos ampliados + bloques YOLO (Ultralytics) | Pendiente |

## Secuencia de trabajo por fase (referencia)

Cada fase sigue: Architecture (contrato) -> Backend/Frontend (implementación) ->
Testing (pruebas) -> Integration (compatibilidad) -> Quality (verificación) ->
Report (avance.md).

## Ruta crítica del MVP

1. Definir `types` y `blocks/registry` (fase 2) -> desbloquea todo.
2. Motor de ejecución (fase 3) -> desbloquea API y frontend.
3. Cámara + Timer (fase 4) -> desbloquea la fuente real.
4. Bloques mínimos (fase 5) -> primer flujo end-to-end por API.
5. WebSocket (fase 6) -> el frontend puede mostrar frames.
6. Editor visual (fase 7) -> primera versión usable.

## Decisiones de entorno (sesión inicial)

- Python 3.14 + venv en `backend/.venv` con opencv-python 5.0.0, fastapi 0.141.1,
  uvicorn, websockets, pytest, pytest-asyncio, httpx. **Instalado**.
- Node.js/npm: **pendiente de instalar** manualmente por el usuario
  (`paru -S nodejs npm`) porque requiere sudo interactivo. Necesario en fase 7.
- Directorio `.private/` ignorado (referencias del cliente).