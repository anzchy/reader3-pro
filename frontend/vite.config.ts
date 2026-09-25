// Vite multi-page build (013 WI-9 A9.1/A9.2). Three JS entries, one per page; each
// imports its own CSS, so each emits its own hashed .css asset (A9.6b, build half).
// Output is committed: src/reader3_app/web/static/dist/ (served at /static/dist/).
// Rebuild only right before merging (plan §7.5); the packaging lane's
// test_build_is_reproducible fails when the committed dist/ is stale.
//
// 013 WI-10: themePlugin authors the colour tokens (virtual:r3-theme.css). R3_BUILD_MINIFY=0
// is a test-only switch (tests/integration/test_theme_build.py): an unminified build keeps
// the two dark rules as two rules, which a minifier may legitimately merge.
import { resolve } from "node:path";
import { defineConfig } from "vite";

import { alias, FRONTEND_ROOT, REPO_ROOT } from "./aliases.ts";
import { themePlugin } from "./theme-plugin.ts";

export const ENTRIES: Record<string, string> = {
  library: "src/library/index.ts",
  reader: "src/reader/index.ts",
  settings: "src/settings/index.ts",
};

const UNMINIFIED = process.env.R3_BUILD_MINIFY === "0";

export default defineConfig({
  root: FRONTEND_ROOT,
  base: "/static/dist/",
  publicDir: false,
  resolve: { alias },
  plugins: [themePlugin(FRONTEND_ROOT)],
  build: {
    minify: UNMINIFIED ? false : undefined,
    cssMinify: UNMINIFIED ? false : undefined,
    outDir: resolve(REPO_ROOT, "src/reader3_app/web/static/dist"),
    emptyOutDir: true,
    manifest: "manifest.json",
    sourcemap: false,
    rolldownOptions: {
      input: Object.fromEntries(
        Object.entries(ENTRIES).map(([name, src]) => [name, resolve(FRONTEND_ROOT, src)]),
      ),
    },
  },
});
