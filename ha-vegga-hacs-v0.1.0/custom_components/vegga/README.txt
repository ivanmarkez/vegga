VEGGA Agrónic para Home Assistant — versión 0.1.0

INSTALACIÓN

1. Descomprime el ZIP.
2. Copia la carpeta:
      custom_components/vegga
   dentro de:
      /config/custom_components/vegga
3. Reinicia Home Assistant.
4. Ve a Ajustes > Dispositivos y servicios > Añadir integración.
5. Busca "VEGGA Agrónic".
6. Introduce:
   - ID del equipo: 17669
   - Token Bearer obtenido en Chrome DevTools
   - Intervalo: 30 segundos

FUNCIONES DE ESTA PRIMERA VERSIÓN

- Comprueba la conexión con GET /units/{id}/programs.
- Crea un sensor con el número y nombres de programas.
- Crea un botón Iniciar y otro Parar para cada programa.
- Iniciar usa action=4.
- Parar usa action=5.
- parameter1 = número visible del programa - 1.

LIMITACIÓN ACTUAL

El token se introduce manualmente y puede caducar. La siguiente mejora será
implementar autenticación/renovación automática y después sectores, sensores,
alarmas e historial.
