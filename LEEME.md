# VEGGA 0.5.29 — compatibilidad móvil

Este parche corrige diferencias de JavaScript/CSS entre navegador de escritorio
y el WebView móvil de Home Assistant.

Cambios:
- elimina `String.replaceAll()` de la tarjeta de días;
- usa el mismo escape HTML compatible que la tarjeta Resumen;
- elimina `color-mix()` de esta tarjeta;
- elimina `aspect-ratio` de los botones de días;
- fuerza nuevas URLs `?v=0.5.29` para evitar reutilizar el JS anterior.

## Sustituir
- custom_components/vegga/__init__.py
- custom_components/vegga/manifest.json
- custom_components/vegga/frontend/vegga-loader.js
- custom_components/vegga/frontend/vegga-program-days-card.js

Después:
1. Actualiza desde HACS.
2. Reinicia Home Assistant.
3. Cierra por completo la app del móvil y vuelve a abrirla.
