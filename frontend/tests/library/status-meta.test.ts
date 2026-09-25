// 013 WI-13 (fe-unit support of C13.18 / C13.20): the single status table and the library's
// status rendering. The Track-D rows WI-3 #2-#4 are tagged on the e2e test that renders them on
// the real page (the ledger keeps one source per row); these are the fast, exhaustive halves.
//   * normalizeIndexStatus is total: any payload maps to one of six states; `stale: true` wins;
//     anything outside the enum is "unknown", never "not_indexed" (the `|| not_indexed` bug).
//   * the six states render six distinct testids per view, and grid/row never share a name.
//   * "unknown" reads 状态未知, which is not the not-indexed text.
//   * only a not-indexed book offers 「开始索引」; unknown never does.
import fc from "fast-check";
import { beforeEach, describe, expect, it } from "vitest";

import { INDEX_STATES, normalizeIndexStatus, statusMeta, type IndexState } from "@shared/status-meta";
import { renderStatusPill, startIndexButton } from "../../src/library/status";

beforeEach(() => document.body.replaceChildren());

const REAL = ["not_indexed", "indexing", "indexed", "error"] as const;

describe("normalizeIndexStatus", () => {
  it("has exactly six states", () => {
    expect([...INDEX_STATES].sort()).toEqual(["error", "indexed", "indexing", "not_indexed", "stale", "unknown"]);
  });

  it.each(REAL)("passes %s through", (s) => {
    expect(normalizeIndexStatus({ status: s })).toBe(s);
  });

  it("stale:true wins over the status field", () => {
    expect(normalizeIndexStatus({ status: "not_indexed", stale: true })).toBe("stale");
    expect(normalizeIndexStatus({ status: "indexed", stale: true })).toBe("stale");
  });

  it.each([undefined, null, 7, "indexed", {}, { status: 3 }, { status: "bogus" }, { status: "stale" }])(
    "maps %j to unknown without throwing",
    (payload) => {
      expect(normalizeIndexStatus(payload)).toBe("unknown");
    },
  );

  it("any out-of-enum status string is unknown (property)", () => {
    fc.assert(
      fc.property(
        fc.string().filter((s) => !(REAL as readonly string[]).includes(s)),
        (s) => normalizeIndexStatus({ status: s }) === "unknown",
      ),
    );
  });
});

describe("statusMeta", () => {
  it("labels every state, all distinct; unknown is 状态未知 and not the not-indexed text", () => {
    const labels = INDEX_STATES.map((s) => statusMeta[s].label);
    expect(new Set(labels).size).toBe(6);
    expect(statusMeta.unknown.label).toBe("状态未知");
    expect(statusMeta.unknown.label).not.toBe(statusMeta.not_indexed.label);
    expect(statusMeta.not_indexed.label).toBe("未索引");
    expect(statusMeta.stale.label).toContain("索引已过期");
  });

  it("only not_indexed can start an index", () => {
    const can = INDEX_STATES.filter((s) => statusMeta[s].canStartIndex);
    expect(can).toEqual(["not_indexed"]);
  });
});

function pill(): HTMLSpanElement {
  const el = document.createElement("span");
  document.body.append(el);
  return el;
}

describe("renderStatusPill", () => {
  it("six states render six distinct testids per view, 12 across both views", () => {
    const seen = new Set<string>();
    for (const view of ["grid", "row"] as const) {
      const perView = new Set<string>();
      for (const s of INDEX_STATES) {
        const el = pill();
        renderStatusPill(el, "b1", s, view);
        const id = el.getAttribute("data-testid") ?? "";
        expect(id).toMatch(view === "grid" ? /^lib-book-grid-status-/ : /^lib-book-row-status-/);
        perView.add(id);
        seen.add(id);
        expect(el.getAttribute("data-book-id")).toBe("b1");
        expect(el.textContent).toBe(statusMeta[s].label);
      }
      expect(perView.size).toBe(6);
    }
    expect(seen.size).toBe(12);
  });

  it("re-rendering replaces the state (no stale modifier left behind)", () => {
    const el = pill();
    for (const s of [...INDEX_STATES, ...INDEX_STATES].reverse() as IndexState[]) {
      renderStatusPill(el, "b1", s, "grid");
      expect(el.getAttribute("data-status")).toBe(s);
      expect(el.textContent).toBe(statusMeta[s].label);
    }
  });
});

describe("startIndexButton", () => {
  it("is offered only for not_indexed, named per book", () => {
    for (const s of INDEX_STATES) {
      const b = startIndexButton(s, "Dracula");
      if (s === "not_indexed") {
        expect(b).not.toBeNull();
        expect(b!.getAttribute("aria-label")).toBe("开始索引：Dracula");
        expect(b!.type).toBe("button");
      } else {
        expect(b).toBeNull();
      }
    }
  });
});
