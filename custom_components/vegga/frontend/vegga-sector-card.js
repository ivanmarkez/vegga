/* VEGGA frontend loader. This stable file is served without cache. */
(async () => {
  const version = "0.4.31";
  const moduleUrl = `/vegga_static/vegga-cards-v${version}.js`;
  try {
    await import(moduleUrl);
    console.info(`VEGGA frontend ${version} cargado`);
  } catch (error) {
    console.error("VEGGA: no se pudo cargar el frontend", error);
  }
})();
