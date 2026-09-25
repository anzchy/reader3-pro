// Track-D rows hosted in 013 WI-11 (WI-1 #2, #4, #5, #6): the DegradeBanner base component.
// Test titles carry `[track_d_013 WI-1#n]` so the WI-13 A13.10 ledger can match them in the
// Vitest JSON report. Rows 1, 3, 7 (computed border colour, page-level live regions, token lint
// on the component CSS) need a real page or the CSS and are hosted in WI-13.
import fc from "fast-check";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  DEGRADE_VARIANTS,
  degradeBannerSpec,
  mountDegradeBanner,
  type DegradeVariant,
} from "../../src/components/degrade-banner";

const CANONICAL = /^(?:lib|rd|set)-[a-z0-9]+(?:-[a-z0-9]+)*$/;
const WARN: DegradeVariant[] = ["rd-s1", "lib-s2", "lib-s4"];
const DANGER: DegradeVariant[] = ["lib-s3", "rd-s3"];

function action(label = "操作"): HTMLButtonElement {
  const b = document.createElement("button");
  b.className = "r3-btn";
  b.textContent = label;
  return b;
}

function body(text = "正文"): HTMLElement {
  const p = document.createElement("p");
  p.textContent = text;
  return p;
}

function mount(variant: DegradeVariant, dismissible = false): HTMLElement | null {
  const host = document.body;
  if (DANGER.includes(variant)) {
    return mountDegradeBanner(host, { variant: variant as "lib-s3" | "rd-s3", body: body(), actions: [action()] });
  }
  return mountDegradeBanner(host, {
    variant: variant as "rd-s1" | "lib-s2" | "lib-s4",
    body: body(),
    actions: [action()],
    dismissible,
  });
}

function byTestId(id: string): Element[] {
  return Array.from(document.querySelectorAll(`[data-testid="${id}"]`));
}

beforeEach(() => {
  document.body.replaceChildren();
  sessionStorage.clear();
  localStorage.clear();
});

afterEach(() => {
  document.body.replaceChildren();
  sessionStorage.clear();
  localStorage.clear();
});

describe("DegradeBanner variants", () => {
  it("has exactly the five root variants", () => {
    expect([...DEGRADE_VARIANTS].sort()).toEqual(["lib-s2", "lib-s3", "lib-s4", "rd-s1", "rd-s3"]);
  });

  it("maps tone by state: warn = S1/S2/S4, danger = S3", () => {
    for (const v of WARN) expect(degradeBannerSpec(v).tone).toBe("warn");
    for (const v of DANGER) expect(degradeBannerSpec(v).tone).toBe("danger");
  });

  it("only warn variants have a dismiss testid; S3 has none", () => {
    expect(degradeBannerSpec("rd-s1").dismissTestId).toBe("rd-degrade-s1-dismiss");
    expect(degradeBannerSpec("lib-s2").dismissTestId).toBe("lib-degrade-s2-dismiss");
    expect(degradeBannerSpec("lib-s4").dismissTestId).toBe("lib-degrade-s4-dismiss");
    expect(degradeBannerSpec("lib-s3").dismissTestId).toBeNull();
    expect(degradeBannerSpec("rd-s3").dismissTestId).toBeNull();
  });
});

describe("DegradeBanner structure", () => {
  it("renders icon, body slot and actions slot; the icon is component-owned", () => {
    const root = mount("lib-s2")!;
    const icon = root.querySelector(".r3-degrade-banner__icon");
    expect(icon).not.toBeNull();
    expect(icon?.getAttribute("aria-hidden")).toBe("true");
    expect(root.querySelector(".r3-degrade-banner__body")?.textContent).toBe("正文");
    expect(root.querySelectorAll(".r3-degrade-banner__actions .r3-btn")).toHaveLength(1);
    expect(root.classList.contains("r3-degrade-banner")).toBe(true);
    expect(root.classList.contains("r3-degrade-banner--warn")).toBe(true);
  });

  it("danger variants carry the danger modifier", () => {
    const root = mount("rd-s3")!;
    expect(root.classList.contains("r3-degrade-banner--danger")).toBe(true);
  });

  it("refuses to render without at least one action", () => {
    expect(() =>
      mountDegradeBanner(document.body, { variant: "lib-s2", body: body(), actions: [], dismissible: false }),
    ).toThrow(/action/);
    expect(document.body.children).toHaveLength(0);
  });

  it("refuses dismissible=true on a danger variant at runtime as well as in the type", () => {
    expect(() =>
      // @ts-expect-error -- danger variants have no dismissible=true in their props type
      mountDegradeBanner(document.body, { variant: "lib-s3", body: body(), actions: [action()], dismissible: true }),
    ).toThrow(/dismiss/);
    expect(document.body.children).toHaveLength(0);
  });
});

describe("[track_d_013 WI-1#2] role status and aria-live polite (C11.10)", () => {
  it.each(DEGRADE_VARIANTS)("[track_d_013 WI-1#2] %s root is role=status aria-live=polite, one live region", (v) => {
    const root = mount(v)!;
    expect(root.getAttribute("role")).toBe("status");
    expect(root.getAttribute("aria-live")).toBe("polite");
    // Single live region: the banner itself, nothing nested inside it re-announces.
    expect(root.querySelectorAll("[aria-live]")).toHaveLength(0);
    expect(root.querySelectorAll('[role="status"],[role="alert"]')).toHaveLength(0);
    expect(document.querySelectorAll("[aria-live]")).toHaveLength(1);
  });
});

describe("[track_d_013 WI-1#5] no dismiss control when not dismissible (C11.12)", () => {
  it.each(WARN)("[track_d_013 WI-1#5] %s: dismissible=false renders 0 dismiss, true renders 1", (v) => {
    const id = degradeBannerSpec(v).dismissTestId!;
    mount(v, false);
    expect(byTestId(id)).toHaveLength(0);
    expect(document.querySelectorAll(".r3-degrade-banner__dismiss")).toHaveLength(0);
    document.body.replaceChildren();
    mount(v, true);
    expect(byTestId(id)).toHaveLength(1);
  });

  it.each(DANGER)("[track_d_013 WI-1#5] %s never renders a dismiss control", (v) => {
    mount(v);
    expect(document.querySelectorAll(".r3-degrade-banner__dismiss")).toHaveLength(0);
    expect(document.querySelectorAll("button")).toHaveLength(1); // only the action
  });
});

describe("[track_d_013 WI-1#6] five distinct root testids (C11.13)", () => {
  it("[track_d_013 WI-1#6] the five variants render five distinct canonical root testids", () => {
    const ids = DEGRADE_VARIANTS.map((v) => {
      document.body.replaceChildren();
      const root = mount(v)!;
      return root.getAttribute("data-testid");
    });
    expect(new Set(ids).size).toBe(5);
    for (const id of ids) expect(id).toMatch(CANONICAL);
    expect([...ids].sort()).toEqual(["lib-degrade-s2", "lib-degrade-s3", "lib-degrade-s4", "rd-degrade-s1", "rd-degrade-s3"]);
  });
});

describe("[track_d_013 WI-1#4] dismiss persists for the session (C11.11)", () => {
  it("[track_d_013 WI-1#4] click dismiss: removed from DOM, sessionStorage key set, remount absent", () => {
    const root = mount("lib-s2", true)!;
    (byTestId("lib-degrade-s2-dismiss")[0] as HTMLElement).click();
    expect(root.isConnected).toBe(false);
    expect(byTestId("lib-degrade-s2")).toHaveLength(0);
    expect(sessionStorage.getItem("reader3.degrade.s2")).not.toBeNull();
    expect(mount("lib-s2", true)).toBeNull();
    expect(byTestId("lib-degrade-s2")).toHaveLength(0);
    expect(localStorage.length).toBe(0);
  });

  it("[track_d_013 WI-1#4] visibility and session keys follow the model under arbitrary sequences", () => {
    type Op =
      | { kind: "mount"; variant: DegradeVariant; dismissible: boolean }
      | { kind: "dismiss"; variant: DegradeVariant }
      | { kind: "newSession" };
    const variant = fc.constantFrom<DegradeVariant>(...DEGRADE_VARIANTS);
    const op: fc.Arbitrary<Op> = fc.oneof(
      fc.record({ kind: fc.constant("mount" as const), variant, dismissible: fc.boolean() }),
      fc.record({ kind: fc.constant("dismiss" as const), variant }),
      fc.record({ kind: fc.constant("newSession" as const) }),
    );
    fc.assert(
      fc.property(fc.array(op, { maxLength: 30 }), (ops) => {
        document.body.replaceChildren();
        sessionStorage.clear();
        localStorage.clear();
        const dismissed = new Set<string>(); // state ids, e.g. "s2"
        for (const o of ops) {
          const spec = o.kind === "newSession" ? null : degradeBannerSpec(o.variant);
          if (o.kind === "newSession") {
            document.body.replaceChildren();
            sessionStorage.clear();
            dismissed.clear();
          } else if (o.kind === "mount") {
            // One banner per variant on the page at a time, like a real page.
            byTestId(spec!.rootTestId).forEach((el) => el.remove());
            const el = mount(o.variant, spec!.tone === "warn" && o.dismissible);
            expect(el === null).toBe(dismissed.has(spec!.stateId));
          } else {
            const btn = spec!.dismissTestId ? byTestId(spec!.dismissTestId)[0] : undefined;
            if (btn) {
              (btn as HTMLElement).click();
              dismissed.add(spec!.stateId);
            }
          }
          for (const v of DEGRADE_VARIANTS) {
            const s = degradeBannerSpec(v);
            if (dismissed.has(s.stateId)) expect(byTestId(s.rootTestId)).toHaveLength(0);
          }
          const keys = Array.from({ length: sessionStorage.length }, (_, i) => sessionStorage.key(i)!).sort();
          expect(keys).toEqual([...dismissed].map((id) => `reader3.degrade.${id}`).sort());
          expect(localStorage.length).toBe(0);
        }
      }),
      { numRuns: 200 },
    );
  });
});
