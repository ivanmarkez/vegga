# VEGGA 0.5.28 — carga móvil

## Sustituir
- custom_components/vegga/__init__.py
- custom_components/vegga/manifest.json
- custom_components/vegga/frontend/vegga-program-days-card.js

## Añadir
- custom_components/vegga/frontend/vegga-loader.js

No borres `vegga-overview-card.js`; el loader lo usa tal como está.

Después:
1. Sube estos archivos a GitHub.
2. Actualiza/reinstala VEGGA desde HACS.
3. Reinicia Home Assistant.
4. Cierra completamente la app de Home Assistant del móvil y vuelve a abrirla.

Configuración de la vista:
```yaml
type: custom:vegga-program-days-card
controller: vivero_agronic_17669
title: Días de riego
cards: []
visible:
  - user: 45709bc3b6ec47f6a657e68c3150a5af
  - user: 14ee1ac23cbe468d9943740137dd24f2
```
