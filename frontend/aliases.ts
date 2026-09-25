// The ONE module-resolution alias definition for the frontend (013 WI-9 A9.8).
//
// Vite (frontend/vite.config.ts) and Vitest (frontend/vitest.config.ts) both import
// `alias` from here; neither config writes an alias of its own. The data comes from
// `compilerOptions.paths` in the root tsconfig.json, so the type checker, depcruise
// (which reads the same tsconfig) and both bundlers can never disagree: retarget an
// alias in tsconfig.json and all four follow. tsconfig.json must stay plain JSON
// (no comments) for that reason.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const FRONTEND_ROOT = dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = resolve(FRONTEND_ROOT, "..");

interface TsConfig {
  compilerOptions: { paths: Record<string, string[]> };
}

function aliasesFromTsconfig(): Record<string, string> {
  const tsconfig = JSON.parse(readFileSync(resolve(REPO_ROOT, "tsconfig.json"), "utf8")) as TsConfig;
  const out: Record<string, string> = {};
  for (const [pattern, targets] of Object.entries(tsconfig.compilerOptions.paths)) {
    if (!pattern.endsWith("/*") || targets.length !== 1 || !targets[0].endsWith("/*")) {
      throw new Error(`tsconfig paths entry ${pattern} must be "<key>/*": ["<dir>/*"] with one target`);
    }
    // paths without baseUrl are relative to the tsconfig's own directory (the repo root).
    out[pattern.slice(0, -2)] = resolve(REPO_ROOT, targets[0].slice(0, -2));
  }
  return out;
}

export const alias: Record<string, string> = aliasesFromTsconfig();
