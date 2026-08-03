## 0.5.7 — Horas reales coherentes y tarjetas móviles compactas

- Corrige registros de VEGGA donde `dateFrom` corresponde al inicio del programa, no al inicio real del sector.
- Conserva el fin real y reconstruye el inicio real usando la duración efectiva cuando las horas no cuadran.
- Oculta el bloque “Programas” en móvil cuando no existe una relación conocida.
- Mejora la detección de entidades antiguas cuyos IDs no contienen el prefijo del controlador.
