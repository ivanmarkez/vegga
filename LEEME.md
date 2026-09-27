# VEGGA 0.5.27 — actualización inmediata de días

Corrige el efecto por el que, después de pulsar Guardar, la tarjeta volvía a mostrar temporalmente los días anteriores.

## Qué cambia

- El `POST` de VEGGA sigue siendo el mismo y ya confirmado.
- Tras recibir respuesta correcta, la integración actualiza inmediatamente el caché del coordinator de Home Assistant.
- La tarjeta mantiene además el valor recién guardado de forma optimista hasta que el estado de HA coincide.
- No se fuerza un GET inmediato a VEGGA, evitando leer una copia todavía no actualizada justo después del POST.
- El sondeo normal de la integración confirma posteriormente el estado real.

## Archivos a sustituir

- `custom_components/vegga/__init__.py`
- `custom_components/vegga/manifest.json`
- `custom_components/vegga/services.py`
- `custom_components/vegga/frontend/vegga-program-days-card.js`

Después de actualizar desde HACS, reinicia Home Assistant y comprueba que la tarjeta muestra `v0.5.27`.
