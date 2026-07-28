# VEGGA Agrónic para Home Assistant

Integración no oficial para controlar equipos Agrónic mediante VEGGA.

## Estado inicial

- Lectura de programas.
- Botones para iniciar programas.
- Botones para detener programas.
- Configuración desde la interfaz de Home Assistant.
- Token Bearer manual.

## Instalación mediante HACS

1. Publica este contenido en un repositorio de GitHub.
2. En HACS, abre **Integraciones**.
3. Pulsa el menú de tres puntos.
4. Entra en **Repositorios personalizados**.
5. Añade la URL del repositorio como categoría **Integración**.
6. Instala **VEGGA Agrónic**.
7. Reinicia Home Assistant.
8. Añade la integración desde **Ajustes > Dispositivos y servicios**.

## Datos actuales

- Endpoint manual: `/agronic/api/v1/units/{device_id}/manual`
- Iniciar programa: `action = 4`
- Detener programa: `action = 5`
- `parameter1 = número del programa - 1`

## Aviso

Esta integración es experimental y no oficial.
