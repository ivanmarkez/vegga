# VEGGA Agrónic para Home Assistant

Integración HACS para equipos VEGGA / Agrónic.

## Versión 0.4.21

### Confirmación de seguridad para sectores

Cambiar el selector de modo ya no envía ninguna orden al Agrónic. El cambio queda pendiente y solo se ejecuta al pulsar **Confirmar cambio de modo**. De este modo, un clic accidental no puede arrancar, detener o desbloquear un sector.


- Control de cada sector mediante un único selector de tres estados: **Automático**, **Marcha manual** y **Paro manual**.
- Eliminados los botones duplicados de sector.
- Limpieza automática de las entidades antiguas «Iniciar riego», «Parar riego», «Marcha manual», «Paro manual» y «Automático».
- Se mantienen los botones de inicio y parada de programas.
- Icono y versión sincronizados para Home Assistant y HACS.
