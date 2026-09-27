# VEGGA 0.5.26 — editor de días de riego

Corrección del guardado de los días de programa.

## Endpoint confirmado en VEGGA

- Método: `POST`
- Ruta: `/agronic/api/v1/units/{device_id}/programs/{program_number}`
- Ejemplo confirmado: `/units/17669/programs/1`
- Respuesta observada: `200 OK`

## Cómo guarda esta versión

1. Lee el programa individual justo antes del cambio.
2. Conserva el objeto completo devuelto por VEGGA.
3. Añade/mantiene `progtype: "6"`.
4. Cambia exclusivamente:
   - monday
   - tuesday
   - wednesday
   - thursday
   - friday
   - saturday
   - sunday
5. Envía el programa mediante POST al mismo endpoint que usa la web de VEGGA.

Así no se reconstruyen horas, sectores, fertilización ni otros parámetros.

## Archivos

Sustituir:
- `custom_components/vegga/__init__.py`
- `custom_components/vegga/manifest.json`
- `custom_components/vegga/services.py`
- `custom_components/vegga/frontend/vegga-program-days-card.js`

`services.yaml` puede quedarse como en 0.5.25, pero se incluye también en el paquete.

## Después de subir a GitHub

1. Actualiza/reinstala la integración desde HACS.
2. Reinicia Home Assistant.
3. Comprueba que la tarjeta muestra `v0.5.26`.
4. Prueba primero cambiando un único día del Programa 1.
