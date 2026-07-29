# VEGGA Agrónic para Home Assistant — v0.4.22

Integración no oficial de VEGGA/Agrónic para Home Assistant.

## Novedad: tarjeta segura de sectores

Esta versión incorpora `VEGGA - Control seguro de sector`, una tarjeta Lovelace propia con tres modos:

- Automático
- Marcha manual
- Paro manual

La tarjeta **nunca envía la orden al primer toque**. Antes abre una ventana emergente indicando el sector, el modo actual y el nuevo modo. La orden se envía únicamente al pulsar **Sí, cambiar modo**.

## Activar la tarjeta (una sola vez)

Tras instalar o actualizar la integración y reiniciar Home Assistant:

1. Abre **Ajustes → Paneles → Recursos**.
2. Añade el recurso:
   - URL: `/vegga_static/vegga-sector-card.js?v=0.4.22`
   - Tipo: `Módulo JavaScript`
3. Recarga completamente el navegador o la aplicación.
4. Añade una tarjeta y busca **VEGGA - Control seguro de sector**.
5. Selecciona la entidad `select` llamada **Modo de funcionamiento** del sector.

La tarjeta detecta automáticamente el botón interno de confirmación del mismo dispositivo. También puede indicarse manualmente con `confirm_entity`.

### Ejemplo YAML

```yaml
type: custom:vegga-sector-card
entity: select.sector_1_modo_de_funcionamiento
```

## Seguridad en dos capas

El frontend muestra el popup y, además, la integración conserva la protección de la versión 0.4.21: primero deja el cambio pendiente y después ejecuta el botón de confirmación. Así, la tarjeta no llama directamente a una orden peligrosa.
