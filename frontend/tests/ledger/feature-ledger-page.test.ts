// Review T1 / L1 (2026-09-27): the feature-ledger dashboard's JS is executed, not grepped.
//
// docs/feature-ledger.html is loaded in a fresh jsdom with its scripts running, after
// its `ledger-data` block is replaced by a fixture of the generator's shape: one
// feature per status (all 8), Routes / Confirm / Tracked on some rows, two audit
// entries, and hostile strings in a name, what, limits, a code path and an audit
// title. The fixture is escaped exactly as scripts/build_feature_ledger.py escapes
// the real block (`</` -> `<\/`, `<!--` -> `<!--`).
import { JSDOM, VirtualConsole } from "jsdom";
import { describe, expect, it } from "vitest";

import pageHtml from "../../../docs/feature-ledger.html?raw";

const OPEN_TAG = '<script type="application/json" id="ledger-data">';
const CLOSE_TAG = "</script>";

const IMG = '<img src=x onerror="window.__xss=1">';
const BREAKOUT = "</script><script>window.__xss=1</script>";
const COMMENT = "<!--";

const STATUSES = ["accepted", "partial", "stub", "absent", "unknown", "deprecated", "superseded", "removed"];

interface Feature {
  id: string;
  name: string;
  area: string;
  status: string;
  what: string;
  routes: string[];
  code: string[];
  tests: string[];
  adr: string[];
  confirm: string;
  tracked: string;
  evidence: string;
  limits: string;
}

function feature(n: number, status: string, over: Partial<Feature> = {}): Feature {
  const id = `F-${String(n).padStart(3, "0")}`;
  return {
    id,
    name: `Feature ${id}`,
    area: n % 2 ? "Reader" : "Library",
    status,
    what: `Does ${id}.`,
    routes: [],
    code: [],
    tests: [],
    adr: [],
    confirm: "",
    tracked: "",
    evidence: "",
    limits: "",
    ...over,
  };
}

const HOSTILE_CODE = `src/${IMG}.py`;
const HOSTILE_TITLE = `Pass ${BREAKOUT} ${IMG}`;

const FIXTURE = {
  synced_from: "docs/feature-ledger.md",
  synced_at: "2026-09-27",
  commit: "8e1cf48",
  statuses: STATUSES,
  features: [
    feature(1, "accepted", {
      routes: ["GET /", "cli: reader3"],
      code: ["src/a.py"],
      tests: ["tests/unit/"],
      confirm: "Open the library at `/`.",
      evidence: "PR #1",
    }),
    feature(2, "partial", {
      name: IMG,
      what: BREAKOUT,
      code: [HOSTILE_CODE],
      tests: ["tests/unit/"],
      confirm: "Run it.",
      evidence: "PR #2",
      limits: `${COMMENT} ${IMG}`,
    }),
    feature(3, "stub", { code: ["src/b.js"], confirm: "Click it: nothing happens.", evidence: "baseline" }),
    feature(4, "absent", { routes: ["POST /api/books/delete"], tracked: "debt #58, 012" }),
    feature(5, "unknown", { code: ["src/c.py"], confirm: "Open /docs.", evidence: "baseline" }),
    feature(6, "deprecated", { code: ["src/d.py"], evidence: "PR #6" }),
    feature(7, "superseded → F-001", { code: ["src/e.py"], evidence: "PR #7" }),
    feature(8, "removed", { evidence: "PR #8" }),
  ],
  audit: [
    { date: "2026-09-27", title: HOSTILE_TITLE, commit: "8e1cf48", scope: "s1", found: "f1", not_audited: "n1" },
    { date: "2026-09-20", title: "Older pass", commit: "abcdef0", scope: "s2", found: "—", not_audited: "n2" },
  ],
};

function escapeBlock(json: string): string {
  return json.replace(/<\//g, "<\\/").replace(/<!--/g, "\\u003c!--");
}

function withFixture(html: string, block: string): string {
  expect(html.split(OPEN_TAG).length - 1).toBe(1);
  const start = html.indexOf(OPEN_TAG) + OPEN_TAG.length;
  const end = html.indexOf(CLOSE_TAG, start);
  return html.slice(0, start) + "\n" + block + "\n" + html.slice(end);
}

function load() {
  const pageErrors: unknown[] = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", (e) => pageErrors.push(e));
  virtualConsole.on("error", (e) => pageErrors.push(e));
  const block = escapeBlock(JSON.stringify(FIXTURE));
  const dom = new JSDOM(withFixture(pageHtml, block), {
    runScripts: "dangerously",
    url: "http://localhost/feature-ledger.html",
    virtualConsole,
  });
  return { dom, window: dom.window, doc: dom.window.document, pageErrors, block };
}

function head(doc: Document, id: string): HTMLElement {
  const h = doc.querySelector<HTMLElement>(`#list .row-head[aria-controls="d-${id}"]`);
  expect(h, `row head for ${id}`).not.toBeNull();
  return h as HTMLElement;
}

function row(doc: Document, id: string): HTMLElement {
  return head(doc, id).closest(".row") as HTMLElement;
}

/** Expand a row; returns its detail pairs as label -> text. */
function expand(doc: Document, id: string): Map<string, string> {
  head(doc, id).click();
  const dl = doc.getElementById(`d-${id}`);
  expect(dl, `detail list for ${id}`).not.toBeNull();
  const out = new Map<string, string>();
  (dl as HTMLElement).querySelectorAll("dt").forEach((dt) => {
    out.set(dt.textContent ?? "", dt.nextElementSibling?.textContent ?? "");
  });
  return out;
}

describe("docs/feature-ledger.html executed in jsdom", () => {
  it("the fixture block is escaped like the generator and parses back", () => {
    const { block } = load();
    expect(block).not.toMatch(/<\/script|<!--/i);
    expect(JSON.parse(block)).toEqual(FIXTURE);
  });

  it("runs without page errors and renders every feature", () => {
    const { doc, pageErrors } = load();
    expect(pageErrors).toEqual([]);
    expect(doc.querySelectorAll("#list .row").length).toBe(FIXTURE.features.length);
  });

  it("shows exactly one count and one row badge per status, for all 8", () => {
    const { doc } = load();
    for (const s of STATUSES) {
      const counts = doc.querySelectorAll(`#counts .badge.s-${s}`);
      expect(counts.length, `count badge for ${s}`).toBe(1);
      expect(counts[0].closest(".count")?.querySelector("b")?.textContent, `count for ${s}`).toBe("1");
      expect(doc.querySelectorAll(`#list .row-head .badge.s-${s}`).length, `row badge for ${s}`).toBe(1);
    }
    expect(doc.querySelectorAll("#counts .count").length).toBe(8);
    expect(row(doc, "F-007").querySelector(".badge")?.textContent).toBe("superseded → F-001");
  });

  it("expanding rows shows Routes, Confirm and Tracked", () => {
    const { doc } = load();
    const accepted = expand(doc, "F-001");
    expect(accepted.get("Routes")).toContain("GET /");
    expect(accepted.get("Routes")).toContain("cli: reader3");
    expect(accepted.get("Confirm")).toBe("Open the library at /.");
    expect(accepted.has("Tracked")).toBe(false);

    const absent = expand(doc, "F-004");
    expect(absent.get("Routes")).toContain("POST /api/books/delete");
    expect(absent.get("Tracked")).toBe("debt #58, 012");
    expect(absent.has("Confirm")).toBe(false);
  });

  it("renders audit entries newest first", () => {
    const { doc } = load();
    const dates = [...doc.querySelectorAll("#audit > li time")].map((t) => t.getAttribute("datetime"));
    expect(dates).toEqual(["2026-09-27", "2026-09-20"]);
    expect(doc.getElementById("synced")?.textContent).toContain("last audit 2026-09-27");
  });

  it("renders hostile strings as text: no element, no script run", () => {
    const { window, doc, pageErrors } = load();
    const details = expand(doc, "F-002");
    expect(pageErrors).toEqual([]);
    expect(doc.querySelectorAll("img").length).toBe(0);
    expect(window.__xss).toBeUndefined();

    expect(row(doc, "F-002").querySelector(".row-head .name")?.textContent).toContain(IMG);
    expect(row(doc, "F-002").textContent).toContain(IMG);
    expect(details.get("What")).toBe(BREAKOUT);
    expect(details.get("Limits")).toBe(`${COMMENT} ${IMG}`);
    expect(details.get("Code")).toBe(HOSTILE_CODE);
    expect(doc.querySelector("#audit > li .a-title")?.textContent).toBe(HOSTILE_TITLE);
  });
});
