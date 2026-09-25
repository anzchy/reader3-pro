// dependency-cruiser (013 WI-9 A9.4). Zero rules on purpose: WI-14 fills `forbidden`.
// tsConfig makes it follow the same `paths` alias Vite/Vitest use (frontend/aliases.ts).
/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [],
  options: {
    doNotFollow: { path: "node_modules" },
    // 013 WI-10: `virtual:r3-theme.css` exists only inside Vite (frontend/theme-plugin.ts
    // serves it); there is no file to resolve, so it is left out of the graph by exact name.
    exclude: { path: "^virtual:r3-theme\\.css$" },
    tsConfig: { fileName: "tsconfig.json" },
    tsPreCompilationDeps: true,
    enhancedResolveOptions: {
      exportsFields: ["exports"],
      conditionNames: ["import", "require", "node", "default", "types"],
      extensions: [".ts", ".js", ".css"],
    },
  },
};
