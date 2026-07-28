# VEGGA Agrónic v0.4.16

Versión temporal de diagnóstico de estado en tiempo real. Consulta una lista
limitada de endpoints GET observados en la aplicación web y registra por separado
la respuesta y los campos candidatos de programa, sector y estado activo.


## v0.4.17
- Estado real mediante `GET /units/{device}/sectors?irrigation=true`.
- Detección de sectores en riego y programa activo usando `xProgramN`.
- Eliminado el sondeo masivo temporal de diagnóstico.
