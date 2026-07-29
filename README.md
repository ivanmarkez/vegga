# VEGGA Agrónic para Home Assistant — v0.4.48

Integración no oficial de VEGGA/Agrónic para Home Assistant.

## Novedad: tarjeta segura de sectores

Esta versión incorpora `VEGGA - Control seguro de sector`, una tarjeta Lovelace propia con tres modos:

- Automático
- Marcha manual
- Paro manual

La tarjeta **nunca envía la orden al primer toque**. Antes abre una ventana emergente indicando el sector, el modo actual y el nuevo modo. La orden se envía únicamente al pulsar **Sí, cambiar modo**.

## Activar la tarjeta

Desde la versión 0.4.45 la integración registra y carga automáticamente el
módulo de las tarjetas al arrancar Home Assistant. No es necesario añadir ni
actualizar recursos Lovelace manualmente.

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

## 0.4.48

- Consulta `/units/{id}/programs/{programa}` para cada programa activo, igual
  que la pantalla de detalle oficial de VEGGA.
- Obtiene desde ese detalle el `xValue`, la unidad y el subprograma en curso.
- Añade `live_detail_loaded` a los botones para confirmar que se recibió el
  detalle vivo.

## 0.4.47

- Obtiene el tiempo pendiente desde `program.xValue` cuando el A-5500 devuelve
  `subprograms: null`.
- Como respaldo, utiliza `sector.xValue` del sector activo asociado mediante
  `xProgramN`, igual que el detalle oficial de VEGGA.
- Conserva el formato de riego del programa para distinguir HH:MM y MM:SS.

## 0.4.46

- Corrige la detección de programas activos leyendo `xState` del programa.
- Confirma además la actividad mediante `xProgramN` de los sectores que están
  regando, incluida la activación automática por horario.
- Conserva como fuente autoritativa la misma lista viva que ya corrige el
  contador de sectores activos.

## 0.4.45

- Registra automáticamente el JavaScript de las tarjetas mediante el frontend
  de Home Assistant.
- Utiliza una ruta estable con versión de caché, de modo que las futuras
  actualizaciones solo requieren instalar el ZIP y reiniciar Home Assistant.
- Mantiene la ruta 0.4.44 como alias compatible con el recurso manual existente.

## 0.4.44

- Muestra en cada tarjeta si el programa está detenido o en marcha.
- Para programas temporizados, muestra el tiempo restante del subprograma
  activo utilizando `xSubProgramInProgress` y `xValue`, igual que VEGGA.
- Expone `active`, `remaining_seconds` y `remaining_time` como atributos de
  los botones de programa.

## 0.4.43

- Añade `custom:vegga-programs-grid`, una cuadrícula compacta que descubre
  automáticamente todos los programas.
- Cada programa dispone únicamente de Marcha y Paro, con confirmación previa.

## 0.4.42

- Corrige las tarjetas de la cuadrícula compacta: una actualización periódica
  de Home Assistant ya no destruye el diálogo de confirmación mientras se pulsa.
- Publica el frontend con una URL nueva para evitar la caché de la 0.4.40.
- Conserva la lectura inicial del modo real del Agrónic añadida en la 0.4.41.

## 0.4.41

- Sincroniza el modo de cada sector desde `xManual` y `xStartStop` al arrancar y actualizar.
- Evita mostrar Automático por defecto cuando el A-5500 confirma Marcha o Paro manual.

## 0.4.40

- Rediseña la cuadrícula de sectores en formato compacto para mostrar los 30 en una pantalla.

## 0.4.39

- Publica la tarjeta Lovelace en una ruta nueva y versionada para evitar copias antiguas.

## 0.4.38

- Añade `custom:vegga-sectors-grid`, una pantalla responsive con todos los sectores.
- Descubre automáticamente los selectores VEGGA y mantiene la confirmación de cada orden.

## 0.4.37

- Refuerza la limpieza de entidades obsoletas recorriendo el registro de esta configuración.
- Elimina también su estado restaurado antes de cargar las plataformas.

## 0.4.36

- Elimina del registro la entidad de presión antigua que quedó duplicada y no disponible.
- Retira `Sectores con consumo anómalo` mientras no exista una fuente de datos válida.

## 0.4.35

- Registra Presión como entidad independiente con identificador propio.
- Normaliza la unidad devuelta por VEGGA de `bars` a `bar`.

## 0.4.34

- Añade el sensor de presión de la entrada analógica 3, expresado en bar.

## 0.4.33

- Vincula la entrada analógica 1 a conductividad y la 2 a pH en el Agrónic 17669.
- Corrige la escala implícita de un decimal: `5 → 0,5 mS` y `77 → 7,7 pH`.

## 0.4.32

- Añade `securityPH` como segunda entrada válida cuando no existe `checkPH`.
- Usa `fertilizer.pidRegulation[1].xValue` como respaldo del valor vivo de pH.
- Aplica la escala de un decimal utilizada por el A-5500 para el pH.

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
