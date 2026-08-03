## 0.5.8 — Hora local y primer inicio real

- Corrige el desfase de dos horas de los registros VEGGA sin zona horaria.
- Interpreta las horas del Agrónic en la zona horaria configurada en Home Assistant.
- Usa directamente `dateFrom` como primer inicio real y `dateTo` como último fin real.
- No reconstruye las horas a partir de la duración acumulada diaria.
- Mantiene el resumen móvil unificado y las tarjetas de control de sectores y programas.
