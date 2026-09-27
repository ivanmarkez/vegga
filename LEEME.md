# VEGGA 0.5.30 — carga automática de tarjetas

Parche para instalar sobre la integración existente (0.5.29). No es la integración completa.

## Instalación
1. Copia la carpeta `custom_components/vegga` sobre la misma carpeta del repositorio, conservando los demás archivos.
2. Incluye el NUEVO archivo `frontend_setup.py` además de los cuatro archivos actualizados.
3. Actualiza/reinstala desde HACS y reinicia Home Assistant.
4. Cierra completamente la app del móvil y vuelve a abrirla para iniciar una sesión con los recursos actualizados.

No hay que añadir ni cambiar recursos manualmente. La integración registra y actualiza sus recursos automáticamente al arrancar. Conserva el YAML actual de la vista con `type: masonry` y la tarjeta dentro de `cards`.

## Cambios
- Registro automático de las tarjetas Días de riego y Resumen en Lovelace.
- Actualización de sus URLs con la versión instalada y migración del antiguo cargador.
- Carga del registro existente antes de editarlo, conservando recursos ajenos a VEGGA.
- Carga independiente de las dos tarjetas; un error en una no bloquea la otra.
- Carga extra del frontend como respaldo y para recursos gestionados mediante YAML.
- Diseño adaptado al ancho real de la tarjeta: una columna en espacios estrechos, dos cuando caben.

## Comprobaciones
- Sintaxis de Python y JavaScript.
- Pruebas simuladas del registro: primera carga, actualización, conservación de recursos ajenos, duplicados, segundo arranque y modo YAML.
- Registro y lógica de tarjeta verificados con DOM y datos simulados: lectura, selección, envío y error de guardado. No se cambian programas reales.
- La comprobación visual en navegador no pudo ejecutarse en este entorno; falta validar el aspecto en el móvil real.

No se ha accedido al Home Assistant ni al teléfono reales. El mensaje genérico «Error de configuración» no permite confirmar por sí solo su causa exacta. Este parche corrige la gestión automática y elimina la dependencia de carga entre tarjetas; la comprobación final debe hacerse tras instalarlo.
