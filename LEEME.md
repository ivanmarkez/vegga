# VEGGA 0.5.25 — editor de días de riego

Este paquete añade una tarjeta independiente para cambiar únicamente los días semanales de los programas.

## Archivos

Sustituir:
- `custom_components/vegga/__init__.py`
- `custom_components/vegga/manifest.json`

Añadir:
- `custom_components/vegga/services.py`
- `custom_components/vegga/services.yaml`
- `custom_components/vegga/frontend/vegga-program-days-card.js`

## Después de subirlo

1. Actualiza/reinstala la integración desde HACS.
2. Reinicia Home Assistant.
3. Añade una tarjeta manual con:

```yaml
type: custom:vegga-program-days-card
controller: vivero_agronic_17669
title: Días de riego
```

## Importante

La lectura de los días ya está confirmada en la integración.

La escritura se ha implementado de forma conservadora mediante:

`PATCH /units/{device_id}/programs/{program_number}`

y el cuerpo contiene **solo**:
`monday`, `tuesday`, `wednesday`, `thursday`, `friday`, `saturday`, `sunday`.

El endpoint de guardado no estaba capturado en el HAR anterior. Si VEGGA responde 404/405 u otro error, Home Assistant mostrará el fallo y habrá que capturar una modificación real desde la web de VEGGA para confirmar la URL/método exactos. No se hace un PUT completo del programa.
