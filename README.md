# VEGGA Agrónic para Home Assistant — v0.5.15

- Corrige las horas reales usando los cambios de estado registrados por Home Assistant.
- El inicio es el primer cambio real a `on` del sector durante el día.
- El fin es el último cambio real a `off`; la duración suma los intervalos activos.
- Evita usar `dateFrom` del histórico diario de VEGGA, que representa el inicio del bloque agregado y no el arranque real del sector.
- Mantiene el mismo recurso frontend y el mismo YAML.



## Cambios 0.5.15

- Corrige el porcentaje de diferencia en móvil para que use el mismo tamaño de cifra que el resto de valores.
- No cambia ninguna otra fuente, medida, tarjeta ni la vista de escritorio.


## Cambios 0.5.14

- En la vista móvil, el consumo de **Hoy** queda justo encima del consumo de **Ayer**.
- Se conserva la rejilla compacta de cuatro columnas.
- No cambia la tabla de escritorio ni las tarjetas de control.

## Cambios 0.5.13

- Se eliminan los programas relacionados de las fichas móviles del resumen.
- Los valores numéricos del resumen móvil aumentan aproximadamente un 20 %.
- La tabla de escritorio y las tarjetas de control no cambian.

- Vista móvil compacta con 4 columnas por fila.
- Ocho datos visibles: inicio, fin, duración, consumo de hoy, ayer, diferencia, orden y estado.
- Programas relacionados plegados por defecto para reducir el desplazamiento vertical.
- Menos márgenes, altura y separación entre sectores.
- La vista de escritorio y las tarjetas de control permanecen sin cambios.

## Cambios 0.5.11

- El orden diario usa el último ciclo real completo de cada sector.
- Evita mezclar un encendido temprano aislado con el final del riego principal.
- Mantiene las tarjetas de resumen, sectores y programas.
