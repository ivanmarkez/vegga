VEGGA Agrónic v0.5.21

Tarjetas Lovelace integradas para resumen de riego, control de sectores y control de programas.
Recurso frontend estable: /vegga_static/vegga-overview-card.js

Corrección v0.5.21:
- Corrige la asociación del sector 1 con programas ajenos: sectorPerGroup ya no se interpreta como un número de sector.

Novedad v0.5.20:
- Muestra la programación de días por sector y por programa (L M X J V S D).
- Los días activos se resaltan visualmente en el resumen, control de sectores y tarjeta individual.
- Los programas configurados por frecuencia muestran "Cada N días" en lugar de días fijos.
- El sensor "Programas relacionados" expone weekdays, active_days y schedule_text para cada programa.
