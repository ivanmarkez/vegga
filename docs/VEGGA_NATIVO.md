# Dashboard VEGGA nativo de respaldo

Esta vista alternativa usa exclusivamente tarjetas **Markdown nativas** de Home Assistant y plantillas ejecutadas por HA. No utiliza `custom:vegga-*`, HACS para tarjetas, recursos Lovelace JavaScript ni IDs de entidad adivinados.

## Instalación segura
1. **No sustituyas todavía el dashboard VEGGA actual.** En HA, ve a **Ajustes → Paneles → Añadir panel** y crea un panel nuevo (por ejemplo, «VEGGA respaldo»).
2. Abre el panel nuevo, edítalo y entra en el **editor de configuración sin procesar**. Pega el contenido completo de [`dashboard-vegga-nativo.yaml`](dashboard-vegga-nativo.yaml).
3. Abre el panel desde el móvil y el PC. Si los sensores de la integración están disponibles, la lista de sectores y programas se generará automáticamente mediante `integration_entities('vegga')`.
4. Para **control manual**, añade desde la interfaz gráfica tarjetas **Entidades** o **Mosaico** eligiendo las entidades existentes: el selector *Modo de funcionamiento* de cada sector y los botones *Iniciar/Parar programa*. No adivines los IDs. Los selectores cambian físicamente el riego al elegir un modo, por lo que conviene dejar los controles separados del resumen y restringir su acceso.
5. Conserva el dashboard anterior hasta comprobar la nueva vista y los controles en todos los dispositivos. No se modifica el código de las órdenes ni se reinicia el Agrónic.

## Qué ofrece y qué no
- Muestra conexión, programas/sectores activos, última actualización, consumo del **último riego**, volumen de **ayer**, desviación frente al consumo habitual y programación por sector.
- **No** muestra aún un consumo «hoy» en tiempo real, ni reproduce exactamente los horarios de inicio/fin y orden calculados por la tarjeta JavaScript. Es importante **no confundir** «último riego» con «hoy».
- La programación semanal es de **solo lectura** en este respaldo. Para cambiar días sigue existiendo el servicio `vegga.set_program_days`; no lo actives en automatizaciones sin comprobar el programa.
- Si la API VEGGA, el coordinador o la integración dejan de actualizar, **también** faltarán datos aquí: la solución elimina la dependencia del frontend JavaScript, no sustituye la conexión de datos.
- Esta vista está preparada para el Agrónic **17669** y una única entrada VEGGA. Si hay múltiples controladores debe ajustarse el filtro del resumen.

## Evolución recomendada
Para migrar con paridad completa y reducir puntos de fallo, convertir los cálculos hoy/ayer, inicio/fin y calendario semanal en sensores y controles nativos expuestos por Python; después reemplazar gradualmente las tarjetas personalizadas. Hacer pruebas en una rama, validar contra el Agrónic y desplegar sin alterar los comandos de riego.

Referencias: documentación oficial de [tarjeta Markdown](https://www.home-assistant.io/dashboards/markdown/), [entidades de integración](https://www.home-assistant.io/template-functions/integration_entities/) y [tarjeta Entidades](https://www.home-assistant.io/dashboards/entities/).
