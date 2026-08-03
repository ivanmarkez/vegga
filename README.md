# VEGGA Agrónic para Home Assistant — v0.5.10

- Corrige las horas reales usando los cambios de estado registrados por Home Assistant.
- El inicio es el primer cambio real a `on` del sector durante el día.
- El fin es el último cambio real a `off`; la duración suma los intervalos activos.
- Evita usar `dateFrom` del histórico diario de VEGGA, que representa el inicio del bloque agregado y no el arranque real del sector.
- Mantiene el mismo recurso frontend y el mismo YAML.
