# VEGGA Agrónic para Home Assistant — v0.4.0

Integración no oficial para Agrónic A-5500 mediante VEGGA.

## Incluye
- Login automático y renovación de sesión.
- Programas y sectores con controles de inicio/parada.
- Estado de conexión, programas y sectores activos.
- Histórico de riego por sectores desde VEGGA.
- Sensor de último volumen por sector.
- Media robusta de hasta 20 registros anteriores por sector.
- Desviación porcentual, duración y caudal medio en atributos.
- Sensor binario de consumo anómalo por sector.
- Contador global de sectores con anomalías.

El histórico se actualiza cada 30 minutos y analiza los últimos 60 días. El control en tiempo real mantiene el intervalo configurado en Home Assistant.

### Umbrales iniciales
- Normal: desviación menor del 15 %.
- Advertencia: 15–25 %.
- Alarma: 25 % o más.
- Se necesitan al menos 5 registros previos para establecer una referencia.
