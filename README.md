# VEGGA Agrónic para Home Assistant — v0.4.26

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
   - URL: `/vegga_static/vegga-sector-card.js?v=0.4.25`
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

El frontend muestra el popup y, además, la integración conserva la protección de la versión 0.4.21: primero deja el cambio pendiente y después ejecuta el confirmación emergente de la tarjeta. Así, la tarjeta no llama directamente a una orden peligrosa.


## 0.4.24
- Añade al sensor de consumo de cada sector los atributos `yesterday_volume_m3`, `yesterday_irrigation_count` y `yesterday_date` para comparar visualmente con el riego del día anterior.


## 0.4.25
- El detector de consumo anómalo compara el último riego con la mediana de hasta 10 riegos anteriores del mismo sector y del mismo programa.
- Si VEGGA no aporta el programa en el histórico, usa como respaldo los últimos riegos del sector.
- Requiere al menos 3 muestras equivalentes para evaluar.
- Aviso desde ±20 % y alarma desde ±30 %.
- Los sensores muestran programa, método y número de muestras usados en la comparación.

## 0.4.26

- Marcha manual y Paro manual consultan el estado vivo de VEGGA después de
  enviar la orden.
- La integración solo actualiza el modo mostrado cuando VEGGA confirma el
  resultado; si no lo confirma tras cuatro intentos, Home Assistant muestra un
  error explícito.
- Se corrige la detección de sectores activos para evitar falsos positivos
  entre sectores consecutivos o registros sin indicador de riego.
