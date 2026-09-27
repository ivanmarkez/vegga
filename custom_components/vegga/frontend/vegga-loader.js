// Compatibility for previously registered VEGGA loader URLs.
// Each module loads independently; errors cannot block the other card.
for (const file of ["vegga-program-days-card.js", "vegga-overview-card.js"]) {
  import(`/vegga_static/${file}?v=0.5.30`).catch((error) => {
    console.error(`[VEGGA] Error loading ${file}`, error);
  });
}
