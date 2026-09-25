// 013 WI-13 (fe-unit half of C13.08 / C13.33): the library header's chrome-scheme toggle.
//   * one state with the settings page: the key and the helpers are the shared ones, and the
//     settings module re-exports the very same functions (no second copy).
//   * mounting reads, never writes: an absent key shows 跟随系统 and leaves storage empty.
//   * three clicks cycle system -> light -> dark -> system and come back to the start; the
//     aria-label follows; a click to system writes "system".
import { beforeEach, describe, expect, it } from "vitest";

import * as shared from "@shared/scheme";
import * as prefs from "../../src/settings/prefs";
import { mountThemeToggle } from "../../src/library/theme-toggle";

function button(): HTMLButtonElement {
  const b = document.createElement("button");
  b.type = "button";
  document.body.append(b);
  return b;
}

beforeEach(() => {
  document.body.replaceChildren();
  document.documentElement.removeAttribute("data-theme");
  localStorage.clear();
});

describe("shared scheme module", () => {
  it("settings re-exports the shared helpers, not a copy", () => {
    expect(prefs.SCHEME_KEY).toBe(shared.SCHEME_KEY);
    expect(prefs.readScheme).toBe(shared.readScheme);
    expect(prefs.applyScheme).toBe(shared.applyScheme);
    expect(shared.SCHEME_KEY).toBe("reader3.ui.colorScheme");
  });

  it("nextScheme cycles system -> light -> dark -> system", () => {
    expect(shared.nextScheme("system")).toBe("light");
    expect(shared.nextScheme("light")).toBe("dark");
    expect(shared.nextScheme("dark")).toBe("system");
  });
});

describe("mountThemeToggle", () => {
  it("absent key: label 跟随系统, nothing written, no data-theme", () => {
    const b = button();
    mountThemeToggle(b, document.documentElement, localStorage);
    expect(b.getAttribute("aria-label")).toBe("界面明暗：跟随系统");
    expect(localStorage.length).toBe(0);
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("reflects a stored dark without rewriting it", () => {
    localStorage.setItem("reader3.ui.colorScheme", "dark");
    const b = button();
    mountThemeToggle(b, document.documentElement, localStorage);
    expect(b.getAttribute("aria-label")).toBe("界面明暗：深色");
  });

  it("three clicks return to the start; labels, attribute and storage follow", () => {
    const b = button();
    mountThemeToggle(b, document.documentElement, localStorage);
    const seen: Array<[string | null, string | null, string | null]> = [];
    for (let i = 0; i < 3; i++) {
      b.click();
      seen.push([
        b.getAttribute("aria-label"),
        document.documentElement.getAttribute("data-theme"),
        localStorage.getItem("reader3.ui.colorScheme"),
      ]);
    }
    expect(seen).toEqual([
      ["界面明暗：浅色", "light", "light"],
      ["界面明暗：深色", "dark", "dark"],
      ["界面明暗：跟随系统", null, "system"],
    ]);
  });

  it("never touches the reader's paper axis", () => {
    document.documentElement.setAttribute("data-reading-theme", "sepia");
    const b = button();
    mountThemeToggle(b, document.documentElement, localStorage);
    b.click();
    b.click();
    expect(document.documentElement.getAttribute("data-reading-theme")).toBe("sepia");
    document.documentElement.removeAttribute("data-reading-theme");
  });
});
