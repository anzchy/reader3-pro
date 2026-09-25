// 013 WI-11: `getEventTargetElement` and `elementDebugInfo`, moved out of annotations.js into
// the shared DOM helpers (A11.5 counts the definitions; this file pins the behaviour).
import { describe, expect, it } from "vitest";

import { elementDebugInfo, getEventTargetElement } from "@shared/dom";

describe("getEventTargetElement", () => {
  it("returns null for null and undefined", () => {
    expect(getEventTargetElement(null)).toBeNull();
    expect(getEventTargetElement(undefined)).toBeNull();
  });

  it("returns an element target unchanged", () => {
    const el = document.createElement("span");
    expect(getEventTargetElement(el)).toBe(el);
  });

  it("maps a text node to its parent element", () => {
    const p = document.createElement("p");
    const text = document.createTextNode("hi");
    p.append(text);
    expect(getEventTargetElement(text)).toBe(p);
  });

  it("returns null for a detached text node", () => {
    expect(getEventTargetElement(document.createTextNode("x"))).toBeNull();
  });

  it.each([
    ["document", () => document],
    ["a comment node", () => document.createComment("c")],
    ["window", () => window],
  ])("returns null for %s", (_label, make) => {
    expect(getEventTargetElement(make())).toBeNull();
  });

  it("uses the real event target of a dispatched event", () => {
    const button = document.createElement("button");
    document.body.append(button);
    let seen: Element | null = null;
    document.body.addEventListener("click", (e) => {
      seen = getEventTargetElement(e.target);
    });
    button.click();
    expect(seen).toBe(button);
    button.remove();
  });
});

describe("elementDebugInfo", () => {
  it("returns null for null", () => {
    expect(elementDebugInfo(null)).toBeNull();
  });

  it("reports tag, id, class and computed layering properties", () => {
    const el = document.createElement("div");
    el.id = "x";
    el.className = "a b";
    el.style.position = "absolute";
    el.style.pointerEvents = "none";
    document.body.append(el);
    expect(elementDebugInfo(el)).toEqual({
      tag: "DIV",
      id: "x",
      className: "a b",
      pointerEvents: "none",
      position: "absolute",
      zIndex: getComputedStyle(el).zIndex,
    });
    el.remove();
  });

  it("gives an empty className for SVG elements (className is not a string there)", () => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "icon");
    const info = elementDebugInfo(svg);
    expect(info?.className).toBe("");
    expect(info?.tag).toBe("svg");
  });

  it("empty strings for id when absent", () => {
    const info = elementDebugInfo(document.createElement("span"));
    expect(info?.id).toBe("");
    expect(info?.className).toBe("");
  });
});
