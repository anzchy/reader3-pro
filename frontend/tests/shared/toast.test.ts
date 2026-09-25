// 013 WI-11 A11.4 (fe-unit half): the Toast.
//   C11.06  at most one toast container under arbitrary show/advance sequences (model oracle)
//   C11.14  the dwell is `--r3-dwell-toast` read at show time: 1500 / 4000 / 7000 ms rows
// The real-browser halves (C11.07, C11.08 reduced motion, C11.15) need a page that mounts a
// toast; they are not in this file.
import fc from "fast-check";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { readToastDwellMs, showToast, type ToastTestId } from "@shared/toast";

const TOKEN = "--r3-dwell-toast";

function setDwell(value: string): void {
  document.documentElement.style.setProperty(TOKEN, value);
}

function toasts(testId: ToastTestId = "lib-toast"): Element[] {
  return Array.from(document.querySelectorAll(`[data-testid="${testId}"]`));
}

function anyToasts(): Element[] {
  return Array.from(document.querySelectorAll(".r3-toast"));
}

beforeEach(() => {
  vi.useFakeTimers();
  document.body.replaceChildren();
  document.documentElement.removeAttribute("style");
  setDwell("4000ms");
});

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  document.body.replaceChildren();
  document.documentElement.removeAttribute("style");
});

describe("readToastDwellMs", () => {
  it.each([
    ["4000ms", 4000],
    ["1500ms", 1500],
    ["4s", 4000],
    ["  2.5s ", 2500],
  ])("parses %j as %i ms", (raw, ms) => {
    setDwell(raw);
    expect(readToastDwellMs()).toBe(ms);
  });

  it.each(["", "0ms", "0s", "fast", "-100ms", "4000"])(
    "refuses an unresolved or non-positive token %j instead of guessing a constant",
    (raw) => {
      if (raw === "") document.documentElement.style.removeProperty(TOKEN);
      else setDwell(raw);
      expect(() => readToastDwellMs()).toThrow(/--r3-dwell-toast/);
    },
  );
});

describe("showToast structure", () => {
  it("renders the message as text under the testid the page passes in", () => {
    showToast("<b>已保存</b>", { testId: "lib-toast" });
    const [el] = toasts("lib-toast");
    expect(el.textContent).toBe("<b>已保存</b>");
    expect(el.children.length).toBe(0);
    expect(toasts("rd-toast")).toHaveLength(0);
  });

  it("uses rd-toast when the reader asks for it", () => {
    showToast("x", { testId: "rd-toast" });
    expect(toasts("rd-toast")).toHaveLength(1);
  });

  it("lives inside one persistent polite, atomic live region that has no role", () => {
    showToast("a", { testId: "lib-toast" });
    const regions = document.querySelectorAll("[aria-live]");
    expect(regions).toHaveLength(1);
    const region = regions[0];
    expect(region.getAttribute("aria-live")).toBe("polite");
    expect(region.getAttribute("aria-atomic")).toBe("true");
    expect(region.hasAttribute("role")).toBe(false);
    expect(region.contains(toasts()[0])).toBe(true);
    // The toast element itself carries no live-region or alert semantics.
    const el = toasts()[0];
    expect(el.hasAttribute("aria-live")).toBe(false);
    expect(el.hasAttribute("role")).toBe(false);

    vi.advanceTimersByTime(4001);
    expect(toasts()).toHaveLength(0);
    // The region stays after the toast leaves: it is the persistent container.
    expect(document.querySelectorAll("[aria-live]")).toHaveLength(1);
  });

  it.each(["success", "error", "info"] as const)("applies the %s tone modifier", (tone) => {
    showToast("x", { testId: "lib-toast", tone });
    expect(toasts()[0].classList.contains(`r3-toast--${tone}`)).toBe(true);
  });

  it("defaults to the info tone", () => {
    showToast("x", { testId: "lib-toast" });
    expect(toasts()[0].classList.contains("r3-toast--info")).toBe(true);
  });

  it("writes no inline z-index or inline styles (layering comes from --r3-z-toast in CSS)", () => {
    showToast("x", { testId: "lib-toast" });
    expect(toasts()[0].getAttribute("style")).toBeNull();
  });

  it("recreates its region when the page replaced the body", () => {
    showToast("a", { testId: "lib-toast" });
    document.body.replaceChildren();
    showToast("b", { testId: "lib-toast" });
    expect(toasts()).toHaveLength(1);
    expect(toasts()[0].textContent).toBe("b");
    expect(document.querySelectorAll("[aria-live]")).toHaveLength(1);
  });

  it("does not mount anything when the dwell token is unresolved", () => {
    document.documentElement.style.removeProperty(TOKEN);
    expect(() => showToast("x", { testId: "lib-toast" })).toThrow(/--r3-dwell-toast/);
    expect(anyToasts()).toHaveLength(0);
  });
});

describe("dwell tracks the token (C11.14)", () => {
  it.each(["1500ms", "4000ms", "7000ms"])("with %s: present at N-250, gone at N+250", (raw) => {
    setDwell(raw);
    const n = Number.parseInt(raw, 10);
    showToast("x", { testId: "lib-toast" });
    vi.advanceTimersByTime(n - 250);
    expect(toasts()).toHaveLength(1);
    vi.advanceTimersByTime(500);
    expect(toasts()).toHaveLength(0);
  });

  it("reads the token at show time, not at import", () => {
    setDwell("1500ms");
    showToast("a", { testId: "lib-toast" });
    vi.advanceTimersByTime(1750);
    expect(toasts()).toHaveLength(0);
    setDwell("7000ms");
    showToast("b", { testId: "lib-toast" });
    vi.advanceTimersByTime(6750);
    expect(toasts()).toHaveLength(1);
    vi.advanceTimersByTime(500);
    expect(toasts()).toHaveLength(0);
  });

  it("a replacement resets the dwell", () => {
    showToast("a", { testId: "lib-toast" });
    vi.advanceTimersByTime(3000);
    showToast("b", { testId: "lib-toast" });
    vi.advanceTimersByTime(3000);
    expect(toasts()).toHaveLength(1);
    expect(toasts()[0].textContent).toBe("b");
    vi.advanceTimersByTime(1001);
    expect(toasts()).toHaveLength(0);
  });
});

describe("single container under arbitrary sequences (C11.06)", () => {
  type Op = { kind: "show"; text: string } | { kind: "advance"; ms: number };
  const op: fc.Arbitrary<Op> = fc.oneof(
    fc.record({ kind: fc.constant("show" as const), text: fc.string({ minLength: 1, maxLength: 8 }) }),
    fc.record({ kind: fc.constant("advance" as const), ms: fc.integer({ min: 0, max: 5000 }) }),
  );

  it("never has more than one container, and its text matches the model", () => {
    fc.assert(
      fc.property(fc.array(op, { maxLength: 25 }), (ops) => {
        vi.clearAllTimers();
        document.body.replaceChildren();
        let model = null as { text: string; remaining: number } | null;
        for (const o of ops) {
          if (o.kind === "show") {
            showToast(o.text, { testId: "lib-toast" });
            model = { text: o.text, remaining: 4000 };
          } else {
            vi.advanceTimersByTime(o.ms);
            if (model) {
              model = o.ms >= model.remaining ? null : { ...model, remaining: model.remaining - o.ms };
            }
          }
          const found = anyToasts();
          expect(found.length).toBeLessThanOrEqual(1);
          expect(found.length).toBe(model ? 1 : 0);
          if (model) expect(found[0].textContent).toBe(model.text);
        }
      }),
      { numRuns: 200 },
    );
  });
});
