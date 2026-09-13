# Ejemplos de uso de VisionStudio

Guía práctica para descargar, ejecutar y probar VisionStudio con 10 ejemplos
de dificultad ascendente. Cada ejemplo indica qué bloques arrastrar, cómo
conectarlos y qué resultado esperar.

---

## 1. Descargar y ejecutar

### Requisitos

- Python >= 3.11 (desarrollado con 3.14).
- Node.js >= 20 y npm (solo para compilar la interfaz).
- Una webcam para los ejemplos con cámara (los ejemplos de análisis funcionan sin ella).

### Descarga

Obtén el proyecto (clona el repositorio o copia la carpeta del proyecto) y
entra en su raíz:

```bash
cd VisionStudio
```

### Instalación

```bash
# Backend (entorno Python + dependencias)
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt

# Frontend (compilar la interfaz)
cd frontend && npm install && npm run build && cd ..
```

### Ejecución

```bash
backend/.venv/bin/uvicorn visionstudio.api.app:app --app-dir backend --port 8000
```

Abre **http://localhost:8000** en el navegador. Si todo fue bien verás el
editor de VisionStudio: biblioteca de bloques a la izquierda, lienzo en el
centro y panel de propiedades a la derecha.

### Cómo interactuar (consejos generales)

1. **Añadir un bloque**: arrástralo desde la biblioteca (izquierda) al lienzo.
2. **Conectar puertos**: arrastra desde el punto de salida (borde derecho de un
   bloque) hasta el punto de entrada (borde izquierdo del siguiente). Junto a
   cada punto se indica el tipo de dato (`frame`, `bool`, `num`...).
3. **Configurar un bloque**: haz clic en él para abrir sus propiedades a la
   derecha (umbral, kernel, referencia...).
4. **Ejecutar**: usa los botones de la barra superior — Ejecutar, Detener,
   Pausar/Reanudar y "Un frame" (paso manual).
5. **Resultados en vivo**: los bloques de salida muestran la imagen o el valor
   que reciben dentro del propio nodo.
6. **Guardar tu trabajo**: botones Guardar/Cargar (servidor) y Descargar/Subir
   (archivo `.vsproj.json`).

> Los bloques solo se pueden editar/conectar cuando el flujo está **detenido**.

---

## 2. Ejemplos

### Ejemplo 1 — Cámara + Sink de imagen (lo más básico)

Objetivo: ver tu cámara en la aplicación.

1. Arrastra **Cámara** (categoría *Fuentes*).
2. Arrastra **Sink de imagen** (categoría *Salidas*).
3. Conecta la salida `frame` de la cámara con la entrada `frame` del sink.
4. Pulsa **Ejecutar**.

Resultado: la imagen de tu cámara se muestra en tiempo real dentro del sink.
Pulsa **Detener** para terminar.

---

### Ejemplo 2 — Escala de grises

Objetivo: aplicar el primer filtro.

1. Monta el ejemplo 1.
2. Añade **Escala de grises** (Procesamiento) entre la cámara y el sink:
   `Cámara -> Escala de grises -> Sink`.
3. Ejecuta.

Resultado: la imagen aparece en blanco y negro (la salida sigue siendo un
`frame` de 3 canales, así que el sink no nota la diferencia).

---

### Ejemplo 3 — Blanco y negro / Umbral (binarización)

Objetivo: convertir la imagen en dos tonos según un umbral.

1. Monta `Cámara -> Escala de grises -> Sink`.
2. Añade **Blanco y negro** entre grises y el sink. Selecciona el bloque y
   ajusta `Umbral` (127 por defecto).
3. Ejecuta y mueve el umbral: cuanto más alto, más píxeles se apagan.

Variante: usa **Umbral** (Procesamiento) en lugar de *Blanco y negro* y prueba
los distintos modos (`THRESH_BINARY`, `THRESH_BINARY_INV`, `THRESH_TRUNC`,
`THRESH_TOZERO`): el modo invertido "negativa" la binarización.

---

### Ejemplo 4 — Desenfoque (reducir ruido)

Objetivo: suavizar la imagen.

1. Monta `Cámara -> Escala de grises -> Sink`.
2. Inserta **Desenfoque** entre grises y el sink.
3. Selecciona el bloque: `Tamaño de núcleo` (kernel) debe ser impar (1, 3, 5...)
   — un valor par se rechaza con error. `Sigma` 0 deja que OpenCV calcule la
   intensidad.
4. Ejecuta y compara con el frame original aumentando el kernel.

Resultado: la imagen se ve "desenfocada". Este filtro es la preparación
habitual antes de detectar bordes.

---

### Ejemplo 5 — Detección de bordes (Canny)

Objetivo: ver solo los contornos de la escena.

1. Monta `Cámara -> Escala de grises -> Sink`.
2. Sustituye el sink por esta cadena: `... -> Desenfoque -> Detección de bordes -> Sink`.
3. Selecciona **Detección de bordes** y ajusta `Umbral bajo` (100) y `Umbral
   alto` (200).
4. Ejecuta.

Resultado: la imagen se reduce a las líneas de los bordes (blanco sobre negro).
Con el desenfoque previo el resultado es más limpio (menos ruido).

---

### Ejemplo 6 — Contornos (objetos de la imagen)

Objetivo: detectar objetos y dibujarlos en verde.

1. Monta `Cámara -> Escala de grises -> Umbral -> Sink` (ejemplo 3).
2. Sustituye el sink por **Contornos** y conecta su salida `frame` a un
   **Sink de imagen**:
   `Cámara -> Escala de grises -> Umbral -> Contornos -> Sink`.
3. Selecciona **Contornos**: `Modo de contornos` (RETR_EXTERNAL encuentra los
   contornos exteriores) y `Área mínima` (descarta los objetos pequeños/ruido).
4. Ejecuta y muestra un objeto frente a la cámara.

Resultado: el contorno de cada objeto se dibuja en verde sobre la imagen. La
salida `detections` del bloque queda lista para futuros bloques de análisis.

---

### Ejemplo 7 — Texto sobre la imagen

Objetivo: rotular el frame con texto.

1. Monta `Cámara -> Sink` (ejemplo 1).
2. Inserta **Texto sobre imagen** entre ambos.
3. Selecciónalo y escribe el `Texto` (p. ej. "VISION"), posición `X`/`Y`,
   `Tamaño de letra` y `Color` (verde por defecto).
4. Ejecuta.

Resultado: el texto aparece dibujado sobre el frame en la posición indicada.
Ideal para etiquetar o sobreimpresionar información.

---

### Ejemplo 8 — Análisis numérico (comparación) sin cámara

Objetivo: entender los bloques de análisis sin necesidad de hardware.

1. Arrastra **Valor numérico** (Análisis), **Comparación** y **Sink booleano**.
2. Conecta: `Valor numérico -> Comparación -> Sink booleano`.
3. Selecciona **Valor numérico**: `Valor` = 7.
4. Selecciona **Comparación**: `Operador` = `>=`, `Referencia` = 5.
5. Pulsa **Un frame** (o Ejecutar).

Resultado: el sink booleano muestra `true`, porque 7 >= 5. Cambia la referencia
a 10 y volverá a mostrar `false`. El `num`/`bool` junto a los puertos te indica
los tipos que conectas.

---

### Ejemplo 9 — Indicador OK/NOK

Objetivo: convertir un booleano en un indicador de calidad.

1. Monta el ejemplo 8 (`Valor numérico -> Comparación`).
2. Conecta la salida de **Comparación** a un **Indicador de estado** (Salidas)
   en lugar del sink booleano.
3. Pulsa **Un frame**.

Resultado: el indicador se pinta verde (OK) o rojo (NOK) según el resultado de
la comparación. Este es el patrón básico de control de calidad: medir un valor,
compararlo con una referencia y mostrar si pasa o no.

---

### Ejemplo 10 — Flujo combinado con temporizador y guardado

Objetivo: un flujo completo con control de cadencia y persistencia.

1. Monta `Cámara -> Escala de grises -> Umbral -> Contornos -> Sink de imagen`.
2. Arrastra **Temporizador** (Control) y conecta su salida `tick` a la entrada
   `trigger` de la cámara: ahora el flujo se dispara a intervalos en lugar de a
   velocidad continua. Ajusta `Intervalo (ms)` (p. ej. 200).
3. Prueba la pausa (botón **Pausar**/**Reanudar**) y el modo manual con
   **Un frame**.
4. Pulsa **Guardar**, cambia algo, pulsa **Cargar** y observa que se restaura.
   Luego **Descargar**: se genera un archivo `*.vsproj.json` que puedes volver a
   **Subir** en otra sesión o compartir.

Resultado: un flujo de visión completo (captura temporizada + procesamiento +
detección + visualización) guardable y reutilizable.

---

## 3. Siguientes pasos

- Combina los ejemplos: añade `Texto sobre imagen` al flujo del ejemplo 10 para
  rotular lo que ves.
- Conecta la salida `detections` de **Contornos** a **Rectángulos** (Análisis)
  para quedarte con la primera detección.
- Consulta `docs/CONTRATOS.md` para ver la lista completa de bloques, tipos y
  parámetros.