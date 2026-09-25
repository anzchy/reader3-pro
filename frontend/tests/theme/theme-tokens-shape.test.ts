// 013 WI-10 A10.12 (C10.01) and the axis-disjointness law (C10.02).
//
// The two theme axes are two exports, never one table: CHROME_THEMES (data-theme) and
// READING_THEMES (data-reading-theme). The only token names both axes declare are the
// reading tokens whose `auto` value the chrome axis supplies (spec §3.3 rule 3); that
// overlap is committed as ALLOWED_SHARED and asserted exactly, so a paper theme that
// redeclares a chrome token (or a chrome block that grows a new page token) goes red.
import { describe, expect, it } from "vitest";

import * as themeModule from "@shared/theme-tokens";
import { ALLOWED_SHARED, CHROME_THEMES, READING_THEMES } from "@shared/theme-tokens";

const MARKER_COLORS = ["blue", "green", "pink", "yellow"];

function names(decls: Readonly<Record<string, string>> | null): string[] {
  return decls === null ? [] : Object.keys(decls);
}

describe("CHROME_THEMES / READING_THEMES exports (C10.01)", () => {
  it("are two independent exports with exact key sets", () => {
    expect(Object.keys(CHROME_THEMES).sort()).toEqual(["dark", "light"]);
    expect(Object.keys(READING_THEMES).sort()).toEqual(["auto", "green", "night", "paper", "sepia"]);
    expect(CHROME_THEMES as unknown).not.toBe(READING_THEMES as unknown);
  });

  it("exports no merged theme table", () => {
    const exported = Object.keys(themeModule).sort();
    expect(exported).toEqual(["ALLOWED_SHARED", "CHROME_THEMES", "READING_THEMES"]);
  });

  it("gives auto no declarations: auto is 'no override', not a fifth paper", () => {
    expect(READING_THEMES.auto).toBeNull();
  });

  it("declares only --r3-* names with non-empty values", () => {
    const all = [
      ...Object.values(CHROME_THEMES),
      ...Object.values(READING_THEMES).filter((d): d is NonNullable<typeof d> => d !== null),
    ];
    for (const decls of all) {
      expect(Object.keys(decls).length).toBeGreaterThan(0);
      for (const [name, value] of Object.entries(decls)) {
        expect(name).toMatch(/^--r3-[a-z0-9]+(-[a-z0-9]+)*$/);
        expect(value.trim()).not.toBe("");
        expect(value).not.toMatch(/[;{}]/);
      }
    }
  });
});

describe("axis disjointness (C10.02)", () => {
  it("the chrome and reading declaration names intersect in exactly ALLOWED_SHARED", () => {
    const chrome = new Set([...names(CHROME_THEMES.light), ...names(CHROME_THEMES.dark)]);
    const reading = new Set(Object.values(READING_THEMES).flatMap(names));
    const intersection = [...chrome].filter((n) => reading.has(n)).sort();
    expect(intersection).toEqual([...ALLOWED_SHARED].sort());
  });

  it("ALLOWED_SHARED is the page and highlight tokens only", () => {
    for (const name of ALLOWED_SHARED) {
      expect(name).toMatch(/^--r3-(page-(bg|ink|quiet)|hl-(yellow|green|pink|blue)(-rgb)?)$/);
    }
    expect(ALLOWED_SHARED.length).toBe(3 + 4 * 2);
  });

  it("every absolute paper declares the whole reading token set, nothing more", () => {
    for (const paper of ["paper", "sepia", "green", "night"] as const) {
      expect(names(READING_THEMES[paper]).sort()).toEqual([...ALLOWED_SHARED].sort());
    }
  });

  it("the light chrome declares every name the dark chrome overrides", () => {
    const light = new Set(names(CHROME_THEMES.light));
    const missing = names(CHROME_THEMES.dark).filter((n) => !light.has(n));
    expect(missing).toEqual([]);
  });

  it("the hl colour names equal MarkerColor", () => {
    const colours = new Set(
      ALLOWED_SHARED.map((n) => /^--r3-hl-([a-z]+)-rgb$/.exec(n)?.[1]).filter((c): c is string => !!c),
    );
    expect([...colours].sort()).toEqual(MARKER_COLORS);
  });
});
