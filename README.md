# VEGGA Agrónic para Home Assistant

Integración personalizada para consultar los programas de un controlador Agrónic mediante VEGGA y lanzar las órdenes manuales de inicio y parada.

## Versión 0.2.1

- Inicio de sesión automático con usuario y contraseña VEGGA.
- Gestión automática del `access_token`.
- Intento de renovación con `refresh_token`, con nuevo inicio de sesión como respaldo.
- Descubrimiento de controladores mediante los endpoints observados en VEGGA:
  - `/core-service/users/{usuario}/auth`
  - `/agronic/api/v1/users/{id_usuario}/units`
- Selección automática si la cuenta solo tiene un controlador.

## Instalación

Copia `custom_components/vegga` dentro de la carpeta `custom_components` de Home Assistant, reinicia Home Assistant y añade **VEGGA Agrónic** desde Integraciones.

La configuración solicita usuario, contraseña e intervalo de actualización. No requiere pegar manualmente un Bearer Token.


## v0.2.4
Corrige la identificación del usuario Agrónic: ya no usa el claim `sub` del JWT para consultar los controladores.
