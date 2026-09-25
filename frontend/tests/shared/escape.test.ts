// 013 WI-11 A11.3 / A11.3a / A11.3b (ET-9): `escapeHtml` is the single escaping definition.
// Cases C11.01 (DOM round-trip property), C11.02 (nullish / non-strings), C11.03 (entities),
// plus the "exports exactly one symbol" half of A11.3.
import fc from "fast-check";
import { describe, expect, it } from "vitest";

import * as escapeModule from "@shared/escape";
import { escapeHtml } from "@shared/escape";

const SPECIALS = ["&", "<", ">", '"', "'"] as const;

// Strings the HTML tokenizer rewrites on input (CR normalisation, NUL) are not escaping
// questions, so they are kept out of the generator instead of being special-cased in the law.
const hostile = fc.string({
  unit: fc.constantFrom("&", "<", ">", '"', "'", "a", "Z", " ", "#", ";", "x", "1", "é", "中", "/", "=", "\n"),
});
const general = fc.string({ unit: "grapheme" }).filter((s) => !/[\r\0]/.test(s));

describe("escapeHtml exports", () => {
  it("escape.ts exports exactly one symbol, escapeHtml", () => {
    expect(Object.keys(escapeModule)).toEqual(["escapeHtml"]);
  });
});

describe("escapeHtml entities (A11.3b)", () => {
  it.each([
    ["&", "&amp;"],
    ["<", "&lt;"],
    [">", "&gt;"],
    ['"', "&quot;"],
    ["'", "&#39;"],
  ])("maps %s to the literal entity %s", (char, entity) => {
    expect(escapeHtml(char)).toBe(entity);
  });

  it("escapes & first, so an existing entity is escaped rather than preserved", () => {
    expect(escapeHtml("&lt;")).toBe("&amp;lt;");
  });

  it("covers all five characters in one string in order", () => {
    expect(escapeHtml(`<a href="x">Tom & Jerry's</a>`)).toBe(
      "&lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry&#39;s&lt;/a&gt;",
    );
  });
});

describe("escapeHtml nullish and non-string input (A11.3a)", () => {
  it.each([
    [null, ""],
    [undefined, ""],
    [0, "0"],
    [false, "false"],
    [12.5, "12.5"],
  ])("escapeHtml(%s) returns %j", (value, expected) => {
    expect(escapeHtml(value)).toBe(expected);
  });
});

describe("escapeHtml DOM round-trip law (C11.01)", () => {
  it("parsing the output as HTML text gives back the input, with no elements and no raw specials", () => {
    fc.assert(
      fc.property(fc.oneof(hostile, general), (input) => {
        const out = escapeHtml(input);
        const host = document.createElement("div");
        host.innerHTML = out;
        expect(host.textContent).toBe(input);
        expect(host.children.length).toBe(0);
        expect(out).not.toMatch(/[<>"']/);
        // Every & in the output starts one of the five entities: no bare ampersand.
        expect(out.replace(/&(?:amp|lt|gt|quot|#39);/g, "")).not.toContain("&");
      }),
      { numRuns: 500 },
    );
  });

  it("is a function of String(value ?? '') for arbitrary non-nullish primitives", () => {
    fc.assert(
      fc.property(fc.oneof(fc.integer(), fc.double({ noNaN: false }), fc.boolean()), (value) => {
        expect(escapeHtml(value)).toBe(escapeHtml(String(value)));
      }),
      { numRuns: 200 },
    );
  });

  it("each special character appears in the output only as its entity", () => {
    for (const char of SPECIALS) {
      expect(escapeHtml(char.repeat(3))).toBe(escapeHtml(char).repeat(3));
    }
  });
});
