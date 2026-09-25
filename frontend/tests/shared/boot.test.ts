// 013 WI-9 A9.8: the first real Vitest + jsdom spec. It runs in jsdom (a DOM exists),
// imports through the shared `@shared` alias, and pins the one fact every entry relies on:
// booting stamps the page name on the root element and nowhere else.
import { describe, expect, it } from "vitest";

import { markBooted, PAGE_NAMES } from "@shared/boot";

describe("markBooted", () => {
  it("runs under jsdom", () => {
    expect(typeof document).toBe("object");
    expect(document.documentElement.tagName).toBe("HTML");
  });

  it.each(PAGE_NAMES)("stamps data-r3-page=%s on the given root", (page) => {
    const root = document.createElement("div");
    markBooted(page, root);
    expect(root.dataset.r3Page).toBe(page);
    expect(root.getAttributeNames()).toEqual(["data-r3-page"]);
  });

  it("defaults to document.documentElement", () => {
    document.documentElement.removeAttribute("data-r3-page");
    markBooted("settings");
    expect(document.documentElement.getAttribute("data-r3-page")).toBe("settings");
  });

  it("names exactly the three Vite entries", () => {
    expect([...PAGE_NAMES].sort()).toEqual(["library", "reader", "settings"]);
  });
});
