// 013 WI-10 A10.11 (C10.03, C10.04): the dark chrome declarations have one author.
//
// `emitDarkCss(D)` renders D once and places the same string under both required
// selectors, so for ANY declaration map the two bodies are byte-equal (property test).
// The plugin's source scan refuses a second `CHROME_THEMES` definition (`/defined 2/`),
// so "write another table somewhere" fails the build instead of silently winning.
// The built-artefact half (exactly two rules in the unminified dist CSS) is C10.21 in
// tests/integration/test_theme_build.py.
import fc from "fast-check";
import { describe, expect, it } from "vitest";

import {
  assertSingleAuthor,
  countDefinitions,
  DARK_EXPLICIT_SELECTOR,
  DARK_MEDIA,
  DARK_SYSTEM_SELECTOR,
  emitDarkCss,
  emitThemeCss,
} from "../../theme-build";
import { CHROME_THEMES, READING_THEMES } from "@shared/theme-tokens";

interface FlatRule {
  context: string; // enclosing at-rule prelude, "" at top level
  selector: string;
  body: string; // raw text between the braces, byte for byte
}

/** Flatten one level of at-rule nesting. Enough for the plugin's output grammar. */
function flatRules(css: string): FlatRule[] {
  const out: FlatRule[] = [];
  const walk = (text: string, context: string): void => {
    let i = 0;
    while (i < text.length) {
      const open = text.indexOf("{", i);
      if (open < 0) return;
      const prelude = text.slice(i, open).replace(/\/\*[\s\S]*?\*\//g, "").trim();
      let depth = 1;
      let j = open + 1;
      while (j < text.length && depth > 0) {
        if (text[j] === "{") depth += 1;
        else if (text[j] === "}") depth -= 1;
        j += 1;
      }
      const inner = text.slice(open + 1, j - 1);
      if (prelude.startsWith("@")) walk(inner, prelude);
      else out.push({ context, selector: prelude, body: inner });
      i = j;
    }
  };
  walk(css, "");
  return out;
}

function declNames(body: string): string[] {
  return body
    .split(";")
    .map((d) => d.trim())
    .filter((d) => d !== "")
    .map((d) => d.slice(0, d.indexOf(":")).trim());
}

function darkRules(css: string): FlatRule[] {
  return flatRules(css).filter(
    (r) =>
      (r.context === DARK_MEDIA && r.selector === DARK_SYSTEM_SELECTOR) ||
      (r.context === "" && r.selector === DARK_EXPLICIT_SELECTOR),
  );
}

const tokenName = fc
  .stringMatching(/^[a-z][a-z0-9]{0,8}(-[a-z0-9]{1,6}){0,2}$/)
  .map((s) => `--r3-${s}`);
const tokenValue = fc
  .string({ minLength: 1, maxLength: 24 })
  .map((s) => s.replace(/[;{}\\\n\r"']/g, "x").trim())
  .filter((s) => s !== "");

describe("emitDarkCss (C10.03)", () => {
  it("names the two required selectors exactly", () => {
    expect(DARK_MEDIA).toBe("@media (prefers-color-scheme: dark)");
    expect(DARK_SYSTEM_SELECTOR).toBe(':root:not([data-theme="light"])');
    expect(DARK_EXPLICIT_SELECTOR).toBe(':root[data-theme="dark"]');
  });

  it("emits both selectors with byte-equal bodies for any declaration map", () => {
    fc.assert(
      fc.property(fc.dictionary(tokenName, tokenValue, { minKeys: 1, maxKeys: 12 }), (decls) => {
        const rules = darkRules(emitDarkCss(decls));
        expect(rules.length).toBe(2);
        expect(rules[0].body).toBe(rules[1].body);
        expect(declNames(rules[0].body).sort()).toEqual(Object.keys(decls).sort());
      }),
      { numRuns: 200, seed: 1013 },
    );
  });

  it("emits nothing but those two rules", () => {
    const rules = flatRules(emitDarkCss({ "--r3-bg": "#000" }));
    expect(rules.length).toBe(2);
  });

  it("refuses a value that would escape its declaration", () => {
    expect(() => emitDarkCss({ "--r3-bg": "red; color: blue" })).toThrow();
    expect(() => emitDarkCss({ "--r3-bg": "red } body { color: blue" })).toThrow();
  });
});

describe("emitThemeCss over the real tables", () => {
  const css = emitThemeCss(CHROME_THEMES, READING_THEMES);

  it("contains exactly the two dark rules, each equal to emitDarkCss(CHROME_THEMES.dark)", () => {
    const expected = darkRules(emitDarkCss(CHROME_THEMES.dark));
    const actual = darkRules(css);
    expect(actual.length).toBe(2);
    expect(actual.map((r) => r.body)).toEqual(expected.map((r) => r.body));
    expect(actual[0].body).toBe(actual[1].body);
  });

  it("puts the light chrome on :root and every absolute paper under .reader-shell", () => {
    const rules = flatRules(css);
    const root = rules.filter((r) => r.context === "" && r.selector === ":root");
    expect(root.length).toBe(1);
    expect(declNames(root[0].body).sort()).toEqual(Object.keys(CHROME_THEMES.light).sort());
    for (const paper of ["paper", "sepia", "green", "night"] as const) {
      const sel = `html[data-reading-theme="${paper}"] .reader-shell`;
      const hits = rules.filter((r) => r.selector === sel);
      expect(hits.length).toBe(1);
      expect(declNames(hits[0].body).sort()).toEqual(Object.keys(READING_THEMES[paper] ?? {}).sort());
    }
  });

  it("writes no rule for auto", () => {
    expect(css).not.toMatch(/data-reading-theme\s*=\s*["']?auto/);
  });
});

describe("single author (C10.04)", () => {
  const def = "export const CHROME_THEMES = { light: {}, dark: {} };";

  it("throws /defined 2/ on a second definition", () => {
    const sources = [
      { path: "a/theme-tokens.ts", text: def },
      { path: "b/copy.ts", text: `// copy\n${def}` },
    ];
    expect(countDefinitions(sources)).toBe(2);
    expect(() => assertSingleAuthor(sources)).toThrow(/defined 2/);
  });

  it("throws /defined 0/ when the table is gone", () => {
    expect(() => assertSingleAuthor([{ path: "a.ts", text: "export const X = 1;" }])).toThrow(/defined 0/);
  });

  it("does not count references, comparisons or imports as definitions", () => {
    const text = [
      'import { CHROME_THEMES } from "@shared/theme-tokens";',
      "const d = CHROME_THEMES.dark;",
      "if (CHROME_THEMES === d) {}",
    ].join("\n");
    expect(countDefinitions([{ path: "x.ts", text }])).toBe(0);
  });

  it("the real frontend source defines CHROME_THEMES exactly once", () => {
    const raw = import.meta.glob("/src/**/*.ts", { query: "?raw", import: "default", eager: true });
    const sources = Object.entries(raw).map(([path, text]) => ({ path, text: text as string }));
    expect(sources.length).toBeGreaterThan(0);
    expect(countDefinitions(sources)).toBe(1);
    expect(() => assertSingleAuthor(sources)).not.toThrow();
  });
});
