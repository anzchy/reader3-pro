// 013 WI-10: the Vite plugin that authors the theme stylesheet (spec §3.3, decision D6).
//
// Three jobs, all build-time:
//   1. buildStart: scan frontend/src/**/*.ts and refuse to build unless CHROME_THEMES is
//      defined exactly once (a second table would be a second author of the dark block).
//   2. serve `virtual:r3-theme.css`: emitThemeCss(CHROME_THEMES, READING_THEMES) --
//      :root light chrome, the two dark rules sharing one rendered body, one rule per
//      absolute reading paper, and nothing for `auto`.
//   3. transform: refuse any handwritten stylesheet that carries a dark chrome block.
//
// The rendering itself is pure and lives in theme-build.ts, where Vitest tests it.
import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import type { Plugin } from "vite";

import { CHROME_THEMES, READING_THEMES } from "./src/shared/theme-tokens.ts";
import { assertNoHandwrittenDark, assertSingleAuthor, emitThemeCss, type Source } from "./theme-build.ts";

export const THEME_CSS_ID = "virtual:r3-theme.css";
const RESOLVED_ID = "\0r3-theme.css";

function tsSources(dir: string, root: string): Source[] {
  const out: Source[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...tsSources(path, root));
    else if (entry.name.endsWith(".ts")) out.push({ path: relative(root, path), text: readFileSync(path, "utf8") });
  }
  return out;
}

export function themePlugin(frontendRoot: string): Plugin {
  const srcDir = resolve(frontendRoot, "src");
  return {
    name: "r3-theme",
    enforce: "pre",
    buildStart() {
      try {
        assertSingleAuthor(tsSources(srcDir, frontendRoot));
      } catch (err) {
        this.error((err as Error).message);
      }
    },
    resolveId(id) {
      return id === THEME_CSS_ID ? RESOLVED_ID : null;
    },
    load(id) {
      return id === RESOLVED_ID ? emitThemeCss(CHROME_THEMES, READING_THEMES) : null;
    },
    transform(code, id) {
      if (id === RESOLVED_ID || !/\.css(\?|$)/.test(id)) return null;
      try {
        assertNoHandwrittenDark(id, code);
      } catch (err) {
        this.error((err as Error).message);
      }
      return null;
    },
  };
}
