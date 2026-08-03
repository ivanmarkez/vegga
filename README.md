# VEGGA Agrónic para Home Assistant — v0.5.12

- Corrige las horas reales usando los cambios de estado registrados por Home Assistant.
- El inicio es el primer cambio real a `on` del sector durante el día.
- El fin es el último cambio real a `off`; la duración suma los intervalos activos.
- Evita usar `dateFrom` del histórico diario de VEGGA, que representa el inicio del bloque agregado y no el arranque real del sector.
- Mantiene el mismo recurso frontend y el mismo YAML.


## Cambios 0.5.12

- Vista móvil compacta con 4 columnas por fila.
- Ocho datos visibles: inicio, fin, duración, consumo de hoy, ayer, diferencia, orden y estado.
- Programas relacionados plegados por defecto para reducir el desplazamiento vertical.
- Menos márgenes, altura y separación entre sectores.
- La vista de escritorio y las tarjetas de control permanecen sin cambios.

## Cambios 0.5.11

- El orden diario usa el último ciclo real completo de cada sector.
- Evita mezclar un encendido temprano aislado con el final del riego principal.
- Mantiene las tarjetas de resumen, sectores y programas.
