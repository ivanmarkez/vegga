# VEGGA Agrónic para Home Assistant — v0.4.30

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
   - URL: `/vegga_static/vegga-sector-card.js`
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
- Nueva tarjeta `VEGGA - Últimos riegos ordenados`.
- Ordena automáticamente los sensores de último riego por la hora real de ejecución.
- Muestra la posición 1.º, 2.º, 3.º, etc.
- Por defecto presenta primero el riego más antiguo para leer la secuencia en orden.

```yaml
type: custom:vegga-last-irrigations-card
title: Últimos riegos
order: oldest_first
```


## 0.4.27
- Añade a cada dispositivo de sector el sensor **Programas relacionados**.
- Muestra todos los programas que contienen el sector y su posición dentro de cada programa.
- La relación se obtiene automáticamente de la configuración descargada de VEGGA/Agrónic.


## 0.4.30
- El nombre de cada tarjeta de sector abre directamente la ficha del dispositivo de Home Assistant.
- La navegación usa el `device_id` real del registro de entidades.
- Si no puede resolverse el dispositivo, abre la ventana de más información de la entidad.
- El recurso frontend se sirve sin caché persistente, por lo que ya no hace falta cambiar manualmente `?v=` en cada actualización.
