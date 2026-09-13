# VisionStudio

Aplicación educativa de visión artificial basada en bloques visuales conectables.
Construye flujos `Cámara -> Procesamiento -> Análisis -> Sink` arrastrando y
conectando bloques en un lienzo, sin escribir código.

**Versión actual: 0.1.0** (MVP funcional).

## ¿Qué es VisionStudio?

VisionStudio es una herramienta local para aprender y experimentar con visión
por computador de forma visual. En lugar de programar, colocas bloques que
representan operaciones (captura de cámara, filtros, detección de contornos,
comparaciones, indicadores OK/NOK...) y los conectas entre sí como en un
diagrama de flujo. El programa se encarga de ejecutar el grafo en tiempo real y
te muestra el resultado de cada bloque (imagen, texto, valores) directamente en
el lienzo.

## Funcionamiento general

- **Bloques conectables**: cada bloque tiene entradas y salidas tipadas (frame,
  número, booleano, texto, coordenadas, rectángulo, detecciones, análisis).
  Solo se pueden conectar puertos de tipo compatible; el editor lo valida al
  instante.
- **Flujo típico**: `Cámara -> Escala de grises -> Umbral -> Contornos -> Sink de
  imagen`. Puedes combinar fuentes, procesamiento, análisis y salidas a tu gusto.
- **Ejecución en tiempo real**: el grafo se ejecuta en modo continuo (a la
  velocidad de la cámara), por temporizador, o paso a paso ("un frame"). Puedes
  pausar, reanudar y detener el flujo en cualquier momento.
- **Resultados en vivo**: los bloques de salida (sink) muestran la imagen, texto,
  booleano o estado OK/NOK que reciben, actualizándose en tiempo real.
- **Proyectos**: guarda, carga, descarga y sube proyectos (JSON versionado con
  migraciones automáticas) para reutilizar tus flujos.
- **Idiomas**: interfaz completa en español e inglés (selector en la barra).

### Bloques disponibles (21 en el MVP)

| Categoría | Bloques |
|-----------|---------|
| Fuentes | Cámara |
| Control | Temporizador, Ejecución manual, Pausa/reanudar |
| Procesamiento | Escala de grises, Blanco y negro, Umbral, Desenfoque, Detección de bordes, Contornos, Texto sobre imagen |
| Análisis | Resultado OK/NOK, Comparación, Valor numérico, Coordenadas, Rectángulos, Lista de detecciones |
| Salidas | Sink de imagen, Sink de texto, Sink booleano, Indicador de estado |

## Arquitectura

- **Backend** (Python): FastAPI + OpenCV. Define los bloques, ejecuta el grafo,
  gestiona la cámara y publica los resultados por WebSocket.
- **Frontend** (React + TypeScript + React Flow): editor visual, paneles y
  visualización de resultados en el navegador.
- En producción el backend sirve el frontend compilado: una única aplicación.

## Requisitos

- Python >= 3.11 (desarrollado con 3.14)
- Node.js >= 20 y npm (solo para compilar el frontend)
- Una cámara (webcam) para los flujos que la usan; los bloques de lógica y
  análisis funcionan sin ella.

## Instalación del entorno

```bash
# Backend
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt

# Frontend (compilar la interfaz)
cd frontend && npm install && npm run build
```

## Ejecución

### Opción A — Aplicación unificada (recomendada)

Con el frontend ya compilado (`npm run build`), el backend sirve la aplicación
completa en un solo puerto:

```bash
backend/.venv/bin/uvicorn visionstudio.api.app:app --app-dir backend --port 8000
```

Abre **http://localhost:8000** y empieza a montar tu flujo.

### Opción B — Desarrollo (backend y frontend por separado)

```bash
backend/.venv/bin/uvicorn visionstudio.api.app:app --app-dir backend --reload --port 8000
cd frontend && npm run dev   # Vite en :5173 con proxy a :8000
```

### Pruebas

```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests
```

## Cómo empezar

1. Arrastra un bloque **Cámara** al lienzo (Fuentes).
2. Arrastra un **Sink de imagen** (Salidas) y conéctalos: salida `frame` de la
   cámara -> entrada `frame` del sink.
3. Pulsa **Ejecutar**: verás la imagen de tu cámara en el sink, en tiempo real.
4. Añade bloques entre ambos (grises, umbral, bordes...) y observa cómo cambia
   el resultado. Consulta `Ejemplo_uso.md` para 10 ejemplos guiados.

## Estado del proyecto

- Fases 1-9 completadas: arquitectura y contratos, tipos y registro de bloques,
  motor de ejecución, cámara y runloop, bloques OpenCV, API + WebSocket, editor
  visual, resto de bloques MVP, y persistencia con migraciones.
- La documentación técnica (arquitectura, contratos, plan, formato de proyecto)
  vive en el directorio `docs/`.