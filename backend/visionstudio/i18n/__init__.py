"""Internacionalización (capa transversal).

El backend NO localiza textos. Los errores viajan como `code` + `params` (con
`detail` como clave estable cuando aplica) y las etiquetas de bloques/puertos son
claves i18n (`name_key`, `description_key`, `label_key`). El catálogo real
(`es`/`en`) vive en el frontend (`frontend/src/i18n`), que traduce al renderizar.

Este paquete se mantiene como punto de extensión por si en el futuro el backend
necesitara exponer catálogos (p. ej. mensajes localizados en la API), pero a día
de hoy está vacío a propósito: la decisión está registrada en docs/CONTRATOS.md §4
y docs/ARQUITECTURA.md §8.
"""
