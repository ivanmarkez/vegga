# VEGGA Agrónic para Home Assistant — v0.4.31

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

- Mantiene sin cambios los comandos Automático, Marcha manual y Paro manual de
  la versión 0.4.25.
- Corrige el testigo de riego resolviendo los identificadores internos que
  VEGGA devuelve en el estado vivo contra los sectores configurados.
- El sensor `Sectores activos` muestra el número de sectores en marcha y expone
  sus nombres en `active_sector_names`.
- El sensor binario `Riego activo` de cada sector utiliza la misma resolución
  de identificadores.
- Amplía el sensor de diagnóstico en tiempo real con una muestra de las filas
  devueltas por el endpoint `irrigation=true`.

## 0.4.27

- Corrige el testigo del A-5500 utilizando la propiedad `sector.irrigation`,
  que es el campo que el frontend oficial de VEGGA emplea para mostrar
  `En riego`.
- La detección funciona tanto para riego manual como para riego iniciado por
  programación; no depende de que exista un número de programa activo.
- Mantiene sin cambios los comandos Automático, Marcha manual y Paro manual.

## 0.4.31

- Lee `checkPH` y `checkCE` desde `unit_status.fertilizer`, que es la fuente usada por la vista A-5500.
- Expone en cada entidad el índice analógico configurado, identificador, valor crudo y número de entradas.

## 0.4.30

- Corrige los sectores activos usando el `xStatus` de la lista general, igual que la web oficial.
- Localiza pH y conductividad mediante `checkPH` y `checkCE` de la configuración del A-5500.
- Añade la configuración de fertilización al diagnóstico para contemplar variantes de firmware.

## 0.4.29

- Añade sensores del controlador para pH, conductividad y caudalímetro.
- Convierte los valores crudos usando los formatos y decimales configurados en VEGGA.
- Mantiene cada fuente de sensores aislada para que un sensor no configurado no afecte al control de riego.

## 0.4.28

- Replica la regla exacta del frontend oficial para el A-5500: un sector está
  en riego cuando `xStatus` no es `0`, `3`, `5` ni `6`.
- Corrige la interpretación de `irrigation=true`: el parámetro solicita que
  VEGGA incluya el estado dinámico, pero no filtra la respuesta para devolver
  únicamente los sectores activos.
- Mantiene sin cambios los comandos Automático, Marcha manual y Paro manual.
