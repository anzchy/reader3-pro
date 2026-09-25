// 013 WI-12 (fe-unit half of C12.04 / C12.05 / C12.14): pure helpers of the settings page.
//   * clampInt: the RAG inputs' clamp (FB-S07). Always an integer in [min, max]; an in-range
//     integer is kept; anything non-numeric falls back.
//   * readScheme: an absent or unknown key reads as "system", and reading never writes (gap 12).
//   * applyScheme: system removes data-theme, light / dark set it; the chosen value is written,
//     "system" included; data-reading-theme is never touched; a throwing storage is survived.
import fc from "fast-check";
import { describe, expect, it, vi } from "vitest";

import { applyScheme, clampInt, readScheme, SCHEME_KEY, type Scheme } from "../../src/settings/prefs";

function memoryStorage(initial: Record<string, string> = {}): Storage & { data: Map<string, string> } {
  const data = new Map(Object.entries(initial));
  return {
    data,
    get length() {
      return data.size;
    },
    clear: vi.fn(() => data.clear()),
    getItem: vi.fn((k: string) => (data.has(k) ? (data.get(k) as string) : null)),
    key: vi.fn((i: number) => Array.from(data.keys())[i] ?? null),
    removeItem: vi.fn((k: string) => {
      data.delete(k);
    }),
    setItem: vi.fn((k: string, v: string) => {
      data.set(k, String(v));
    }),
  };
}

function throwingStorage(): Storage {
  const boom = () => {
    throw new Error("SecurityError");
  };
  return { length: 0, clear: boom, getItem: boom, key: boom, removeItem: boom, setItem: boom };
}

describe("clampInt", () => {
  it.each([
    ["0", 1, 20, 6, 1],
    ["21", 1, 20, 6, 20],
    ["7", 1, 20, 6, 7],
    ["999", 1000, 32000, 8000, 1000],
    ["32001", 1000, 32000, 8000, 32000],
    ["", 1, 20, 6, 6],
    ["abc", 1, 20, 6, 6],
    ["7.6", 1, 20, 6, 8],
  ])("clampInt(%j, %i, %i, %i) = %i", (raw, min, max, fallback, out) => {
    expect(clampInt(raw, min, max, fallback)).toBe(out);
  });

  it("is an integer in [min, max] for any finite input, and keeps in-range integers", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: -1000, max: 1000 }),
        fc.integer({ min: 0, max: 1000 }),
        fc.double({ noNaN: true, min: -1e6, max: 1e6 }),
        (min, span, value) => {
          const max = min + span;
          const out = clampInt(String(value), min, max, min);
          expect(Number.isInteger(out)).toBe(true);
          expect(out).toBeGreaterThanOrEqual(min);
          expect(out).toBeLessThanOrEqual(max);
          const whole = Math.trunc(value) + 0; // + 0 folds -0 into 0
          if (whole >= min && whole <= max) expect(clampInt(whole, min, max, min)).toBe(whole);
        },
      ),
    );
  });
});

describe("readScheme", () => {
  it("uses the shared chrome-scheme key", () => {
    expect(SCHEME_KEY).toBe("reader3.ui.colorScheme");
  });

  it.each([
    [undefined, "system"],
    ["system", "system"],
    ["light", "light"],
    ["dark", "dark"],
    ["sepia", "system"],
    ["", "system"],
  ])("stored %j reads as %j and nothing is written", (stored, expected) => {
    const storage = memoryStorage(stored === undefined ? {} : { [SCHEME_KEY]: stored });
    expect(readScheme(storage)).toBe(expected);
    expect(storage.setItem).not.toHaveBeenCalled();
    expect(storage.removeItem).not.toHaveBeenCalled();
    expect(storage.clear).not.toHaveBeenCalled();
  });

  it("an unavailable storage reads as system", () => {
    expect(readScheme(null)).toBe("system");
    expect(readScheme(throwingStorage())).toBe("system");
  });
});

describe("applyScheme", () => {
  const SCHEMES: Scheme[] = ["system", "light", "dark"];

  it("for any sequence, the last choice is on the root and in storage; the reading axis is untouched", () => {
    fc.assert(
      fc.property(
        fc.array(fc.constantFrom(...SCHEMES), { minLength: 1, maxLength: 8 }),
        fc.constantFrom("auto", "paper", "sepia", "green", "night"),
        (seq, reading) => {
          const root = document.createElement("html");
          root.setAttribute("data-reading-theme", reading);
          const storage = memoryStorage();
          for (const s of seq) applyScheme(s, root, storage);
          const last = seq[seq.length - 1];
          expect(root.getAttribute("data-theme")).toBe(last === "system" ? null : last);
          expect(storage.data.get(SCHEME_KEY)).toBe(last);
          expect(root.getAttribute("data-reading-theme")).toBe(reading);
          expect(readScheme(storage)).toBe(last);
        },
      ),
    );
  });

  it("a throwing storage still applies the attribute and does not throw", () => {
    const root = document.createElement("html");
    expect(() => applyScheme("dark", root, throwingStorage())).not.toThrow();
    expect(root.getAttribute("data-theme")).toBe("dark");
    expect(() => applyScheme("system", root, null)).not.toThrow();
    expect(root.hasAttribute("data-theme")).toBe(false);
  });
});
