// 020 WI-1: `Reader3Epub.getDebugState()` in the legacy epub.js renderer.
//
// Test matrix: .claude/tdd-guardian/tests-20260930-113500.md (U-cases, rulings R1-R9).
// Contract: docs/plans/20260928-debug-state-getter.md §3.
//
// Harness. The production script is imported with `?raw` and evaluated in a FRESH
// JSDOM per test (`runScripts: "outside-only"`), so `Reader3Epub` and the renderer's
// keydown/resize listeners never leak between tests. The window is awaited to
// readyState "complete" before any script runs; otherwise annotations.js would defer
// its init to DOMContentLoaded and bind to the renderer instead of no-op'ing.
//
// epub.js (`window.ePub`) needs a layout engine jsdom does not have, so it is stubbed.
// Every stubbed epub.js API the renderer touches:
//   - ePub(url)                   -> book
//   - book.ready                  a real resolved Promise
//   - book.opened                 a resolved Promise (optional in the renderer)
//   - book.loaded.metadata        a resolved Promise (optional in the renderer)
//   - book.spine.get(i)           -> { href: "ch"+i+".xhtml", index: i }; book.spine.length
//   - book.renderTo(el, opts)     -> rendition
//   - rendition.on(name, fn)      records fn in `handlers` (tests call rendered/relocated)
//   - rendition.display(target)   counting spy -> Promise.resolve()
//   - rendition.next / prev / resize / flow   counting spies
//   - rendition.currentLocation   counting spy; the getter must never call it (invariant 8)
//   - rendition.location          plain assignable property, starts undefined
// The iframe document is `window.document.implementation.createHTMLDocument()`, and
// `contents = { document }` mirrors an epub.js view's `.document`.
// The real path for every stubbed case is WI-2's E1-E4 (tests/e2e/test_debug_state.py).
import { JSDOM, VirtualConsole } from "jsdom";
import fc from "fast-check";
import { describe, expect, it } from "vitest";

import rendererSrc from "../../../src/reader3_app/web/static/js/epub-renderer.js?raw";
import annotationsSrc from "../../../src/reader3_app/web/static/js/annotations.js?raw";

// ---- Oracle -------------------------------------------------------------------------
// VERBATIM frozen copy of `updateProgress` in epub-renderer.js as of HEAD 00e966c
// (:235-248), taken before WI-1 touched the renderer. Only two things differ: it
// returns the text instead of writing it, and it carries TS annotations. NEVER edit
// this to match new code — it is the independent specification of "pill unchanged".
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function legacyPill(location: any): string {
  const displayed = location?.start?.displayed;
  let percentage: number | null = null;
  if (displayed?.total) {
    percentage = Math.round((displayed.page / displayed.total) * 100);
  } else if (typeof location?.start?.percentage === "number") {
    percentage = Math.round(location.start.percentage * 100);
  }
  if (percentage == null || Number.isNaN(percentage)) {
    percentage = 0;
  }
  return `当前阅读至 ${percentage}%`;
}

// ---- Types --------------------------------------------------------------------------
interface DiagEntry {
  op: string | null;
  requested: boolean | null;
  status: number | null;
  ok: boolean | null;
  id: string | null;
  t: number | null;
}

interface DebugState {
  v: number;
  ready: boolean;
  cfi: { start: string; end: string } | null;
  section: { index: number | null; href: string | null; requestedIndex: number | null; spineCount: number | null };
  progress: {
    sectionPage: { page: number; total: number } | null;
    sectionPercent: number | null;
    spinePercent: number | null;
    bookPercent: null;
  };
  annotations: { renderedIds: number; marks: number } | null;
  diag: DiagEntry[];
  diagAvailable: boolean;
  errors: string[];
}

interface NotesDiagSurface {
  record: (entry: unknown) => unknown;
  entries: () => unknown[];
}

interface Reader3EpubSurface {
  getDebugState?: (opts?: unknown) => DebugState;
  [key: string]: unknown;
}

type Handler = (...args: unknown[]) => void;

interface RenditionStub {
  handlers: Record<string, Handler>;
  calls: Record<"display" | "next" | "prev" | "resize" | "flow" | "currentLocation", number>;
  location?: unknown;
  on: (name: string, fn: Handler) => void;
  display: (target?: unknown) => Promise<void>;
  next: () => void;
  prev: () => void;
  resize: () => void;
  flow: (f: unknown) => void;
  currentLocation: () => unknown;
}

type TestWindow = Window &
  typeof globalThis & {
    Reader3Epub?: Reader3EpubSurface;
    Reader3Ctx?: Record<string, unknown>;
    Reader3NotesDiag?: unknown;
    ePub?: unknown;
  };

// ---- Harness ------------------------------------------------------------------------
const URL_ = "http://127.0.0.1/read/smoke_data/1";
const NO_TOTAL = Symbol("no totalChapters");

interface SetupOptions {
  chapterIndex?: number;
  totalChapters?: unknown; // NO_TOTAL omits the key
  epubAvailable?: unknown;
  viewer?: boolean;
  epubMissingEl?: boolean;
  ePub?: "stub" | "missing" | "throws";
  realDiag?: boolean; // eval annotations.js before the renderer
  stubDiag?: unknown; // assigned to window.Reader3NotesDiag before the renderer
  noProgressEl?: boolean; // remove #reading-progress before the renderer runs (U30)
}

interface Harness {
  win: TestWindow;
  rendition: RenditionStub;
  pill: () => string | null;
  doc: (bodyHtml: string) => Document;
  rendered: (section: { href?: string; index: number }, doc?: Document) => { document: Document };
  relocated: (loc: unknown, assign?: boolean) => void;
  state: (...args: unknown[]) => DebugState;
}

function flush(): Promise<void> {
  return new Promise((r) => setTimeout(r, 0));
}

async function untilComplete(win: TestWindow): Promise<void> {
  for (let i = 0; i < 50 && win.document.readyState !== "complete"; i++) await flush();
}

function makeRendition(): RenditionStub {
  const r: RenditionStub = {
    handlers: {},
    calls: { display: 0, next: 0, prev: 0, resize: 0, flow: 0, currentLocation: 0 },
    location: undefined,
    on(name, fn) {
      r.handlers[name] = fn;
    },
    display() {
      r.calls.display++;
      return Promise.resolve();
    },
    next() {
      r.calls.next++;
    },
    prev() {
      r.calls.prev++;
    },
    resize() {
      r.calls.resize++;
    },
    flow() {
      r.calls.flow++;
    },
    currentLocation() {
      r.calls.currentLocation++;
      return null;
    },
  };
  return r;
}

async function setup(o: SetupOptions = {}): Promise<Harness> {
  const viewer = o.viewer === false ? "" : '<div id="epub-viewer"></div>';
  const missing = o.epubMissingEl ? '<div id="epub-missing"></div>' : "";
  const html =
    `<!doctype html><html><body>${viewer}${missing}` +
    '<div id="reading-progress"></div>' +
    '<a id="prev-chapter-link" href="#">prev</a><a id="next-chapter-link" href="#">next</a>' +
    '<span class="nav-indicator"></span></body></html>';
  const dom = new JSDOM(html, { runScripts: "outside-only", url: URL_, virtualConsole: new VirtualConsole() });
  const win = dom.window as unknown as TestWindow;
  await untilComplete(win);
  if (o.noProgressEl) win.document.getElementById("reading-progress")!.remove();

  const ctx: Record<string, unknown> = {
    epubAvailable: "epubAvailable" in o ? o.epubAvailable : true,
    epubUrl: "/read/smoke_data/book.epub",
    bookId: "smoke_data",
    chapterIndex: o.chapterIndex ?? 1,
  };
  if (o.totalChapters !== NO_TOTAL) ctx.totalChapters = "totalChapters" in o ? o.totalChapters : 5;
  win.Reader3Ctx = ctx;

  const rendition = makeRendition();
  const spineLength = typeof ctx.totalChapters === "number" ? ctx.totalChapters : 5;
  const book = {
    ready: Promise.resolve(),
    opened: Promise.resolve(),
    loaded: { metadata: Promise.resolve({ title: "stub" }) },
    spine: { length: spineLength, get: (i: number) => ({ href: `ch${i}.xhtml`, index: i }) },
    renderTo: () => rendition,
  };
  if (o.ePub === "throws") {
    win.ePub = () => {
      throw new Error("x");
    };
  } else if (o.ePub !== "missing") {
    win.ePub = () => book;
  }

  if (o.realDiag) win.eval(annotationsSrc);
  if (o.stubDiag !== undefined) win.Reader3NotesDiag = o.stubDiag;
  win.eval(rendererSrc);
  await flush();

  const doc = (bodyHtml: string): Document => {
    const d = win.document.implementation.createHTMLDocument("");
    d.body.innerHTML = bodyHtml;
    return d;
  };

  return {
    win,
    rendition,
    pill: () => win.document.getElementById("reading-progress")!.textContent,
    doc,
    rendered(section, d) {
      const contents = { document: d ?? doc("<p>chapter text</p>") };
      rendition.handlers.rendered!({ href: `ch${section.index}.xhtml`, ...section }, contents);
      return contents;
    },
    relocated(loc, assign = true) {
      if (assign) rendition.location = loc;
      rendition.handlers.relocated!(loc);
    },
    state(...args: unknown[]) {
      const surface = win.Reader3Epub;
      expect(typeof surface?.getDebugState, "Reader3Epub.getDebugState must be a function").toBe("function");
      return (surface!.getDebugState as (...a: unknown[]) => DebugState)(...args);
    },
  };
}

function loc(page: unknown, total: unknown, extra: Record<string, unknown> = {}) {
  return {
    start: { cfi: "epubcfi(/6/2!/4/1:0)", displayed: { page, total }, ...extra },
    end: { cfi: "epubcfi(/6/2!/4/1:9)" },
  };
}

function diagFixture(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    op: "create",
    requested: true,
    status: 500 + i,
    ok: false,
    id: `id-${i}`,
    t: 1000 + i,
  }));
}

function stubDiag(fixture: object[]) {
  return { entries: () => fixture.map((e) => ({ ...e })) };
}

function ids(n0: number, n1: number): string[] {
  const out: string[] = [];
  for (let i = n0; i <= n1; i++) out.push(`id-${i}`);
  return out;
}

const K5_MEMBERS = [
  "applyThemeSettings",
  "book",
  "displaySectionIndex",
  "getContentDocument",
  "getContentRoot",
  "getContents",
  "getDebugState",
  "getFrameElement",
  "onContentsReady",
  "rendition",
];

// ---- Surface -----------------------------------------------------------------------
describe("Reader3Epub surface", () => {
  it("U22: Reader3Epub has exactly the 10 K5 members and getDebugState is a function", async () => {
    const h = await setup();
    expect(Object.keys(h.win.Reader3Epub!).sort()).toEqual(K5_MEMBERS);
    expect(typeof h.win.Reader3Epub!.getDebugState).toBe("function");
  });

  it("U23: source guard — getContentDocument once, no Reader3Epub.book / currentLocation( / getBoundingClientRect", () => {
    const stripped = rendererSrc.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
    const count = (needle: string) => stripped.split(needle).length - 1;
    expect(count("getContentDocument")).toBe(1);
    expect(count("Reader3Epub.book")).toBe(0);
    expect(count("currentLocation(")).toBe(0);
    expect(count("getBoundingClientRect")).toBe(0);
  });

  it("U10: no #epub-viewer means window.Reader3Epub stays undefined", async () => {
    const h = await setup({ viewer: false });
    expect(h.win.Reader3Epub).toBeUndefined();
  });

  it.each([
    ["(i) epubAvailable false", { epubAvailable: false, epubMissingEl: true }],
    ["(ii) epubAvailable \"false\"", { epubAvailable: "false" }],
    ["(iii) window.ePub undefined", { ePub: "missing" as const }],
    ["(iv) ePub() throws", { ePub: "throws" as const }],
  ])("U10b: early return %s leaves Reader3Epub undefined", async (_label, opts) => {
    const h = await setup(opts);
    expect(h.win.Reader3Epub).toBeUndefined();
    if ("epubMissingEl" in opts) {
      expect(h.win.document.getElementById("epub-missing")!.classList.contains("is-visible")).toBe(true);
    }
  });
});

// ---- Initial state, location and section --------------------------------------------
describe("getDebugState: location, section and spine", () => {
  it("U1: before the first relocated — not ready, all location fields null, no errors; always on", async () => {
    const h = await setup({ chapterIndex: 1, totalChapters: 5 });
    expect(h.win.localStorage.getItem("reader3.debug")).toBeNull();
    expect(h.rendition.location).toBeUndefined();
    const s = h.state();
    expect(s.v).toBe(1);
    expect(s.ready).toBe(false);
    expect(s.cfi).toBeNull();
    expect(s.section).toEqual({ index: 1, href: null, requestedIndex: 1, spineCount: 5 });
    expect(s.progress).toEqual({ sectionPage: null, sectionPercent: null, spinePercent: 25, bookPercent: null });
    expect(s.annotations).toBeNull();
    expect(s.errors).toEqual([]);
  });

  it("U2: mid-section 3/10 passes cfi, href and section progress through", async () => {
    const h = await setup({ chapterIndex: 2, totalChapters: 5 });
    h.rendered({ href: "ch2.xhtml", index: 2 });
    const location = {
      start: { cfi: "epubcfi(/6/6!/4/2/1:0)", href: "ch2.xhtml", displayed: { page: 3, total: 10 }, percentage: 0 },
      end: { cfi: "epubcfi(/6/6!/4/2/1:120)" },
    };
    h.relocated(location);
    const s = h.state();
    expect(s.ready).toBe(true);
    expect(s.cfi).toEqual({ start: "epubcfi(/6/6!/4/2/1:0)", end: "epubcfi(/6/6!/4/2/1:120)" });
    expect(s.section.href).toBe("ch2.xhtml");
    expect(s.progress.sectionPage).toEqual({ page: 3, total: 10 });
    expect(s.progress.sectionPercent).toBe(30);
    expect(s.progress.bookPercent).toBeNull();
    expect(s.v).toBe(1);
    expect(s.errors).toEqual([]);
    expect(h.pill()).toBe("当前阅读至 30%");
  });

  it("U2b: page > total is not clamped (R3)", async () => {
    const h = await setup();
    h.relocated(loc(12, 10));
    const s = h.state();
    expect(s.progress.sectionPercent).toBe(120);
    expect(s.progress.sectionPage).toEqual({ page: 12, total: 10 });
    expect(s.errors).toEqual([]);
    expect(h.pill()).toBe("当前阅读至 120%");
  });

  it("U2c: section.href follows the location snapshot, not the rendered section", async () => {
    const h = await setup({ chapterIndex: 2, totalChapters: 5 });
    h.rendered({ href: "ch2.xhtml", index: 2 });
    const sameLocation = {
      start: { cfi: "epubcfi(/6/8!/4/1:0)", href: "ch3.xhtml", displayed: { page: 1, total: 4 } },
      end: { cfi: "epubcfi(/6/8!/4/1:50)" },
    };
    h.rendition.location = sameLocation;
    h.relocated(sameLocation, false);
    const s = h.state();
    expect(s.section.href).toBe("ch3.xhtml");
    expect(s.section.index).toBe(2);
    expect(s.ready).toBe(true);
    expect(s.errors).toEqual([]);
  });

  it("U3: the false 0 from percentage does not leak into progress", async () => {
    const h = await setup();
    h.relocated({ start: { cfi: "epubcfi(/6/2!/4/1:0)", percentage: 0 }, end: { cfi: "epubcfi(/6/2!/4/1:9)" } });
    const s = h.state();
    expect(s.progress.sectionPercent).toBeNull();
    expect(s.progress.sectionPage).toBeNull();
    expect(s.progress.bookPercent).toBeNull();
    expect(s.section.href).toBeNull();
    expect(s.ready).toBe(true);
    expect(s.errors).toEqual([]);
    expect(h.pill()).toBe("当前阅读至 0%");
  });

  it("U4: spine progress follows the rendered index", async () => {
    const h = await setup({ chapterIndex: 0, totalChapters: 5 });
    h.rendered({ href: "ch2.xhtml", index: 2 });
    const s = h.state();
    expect(s.section.index).toBe(2);
    expect(s.section.spineCount).toBe(5);
    expect(s.progress.spinePercent).toBe(50);
  });

  it("U4b: rendered without relocated — not ready, no href, but annotations are counted", async () => {
    const h = await setup({ chapterIndex: 0, totalChapters: 5 });
    h.rendered({ href: "ch2.xhtml", index: 2 });
    expect(h.rendition.location).toBeUndefined();
    const s = h.state();
    expect(s.ready).toBe(false);
    expect(s.section.href).toBeNull();
    expect(s.cfi).toBeNull();
    expect(s.section.index).toBe(2);
    expect(s.progress.sectionPage).toBeNull();
    expect(s.annotations).not.toBeNull();
    expect(s.errors).toEqual([]);
  });

  it.each([
    ["1", 1, 1],
    ["0", 0, 0],
    ["missing", NO_TOTAL, null],
    ['"5" (a string)', "5", null],
  ])("U14: totalChapters %s gives spinePercent null with no error", async (_label, total, spineCount) => {
    const h = await setup({ chapterIndex: 0, totalChapters: total });
    h.rendered({ index: 0 });
    const s = h.state();
    expect(s.progress.spinePercent).toBeNull();
    expect(s.errors).toEqual([]);
    expect(s.section.spineCount).toBe(spineCount);
  });

  it.each([
    ["(i) 1/3 rounds to 33", { chapterIndex: 0, totalChapters: 4 }, 1, 33],
    ["(ii) 2/3 rounds to 67", { chapterIndex: 0, totalChapters: 4 }, 2, 67],
    ["(iii) 7/4 clamps to 100", { chapterIndex: 0, totalChapters: 5 }, 7, 100],
    ["(iv) -1/4 clamps to 0", { chapterIndex: -1, totalChapters: 5 }, null, 0],
  ])("U14b: spinePercent %s (R2)", async (_label, opts, renderIndex, expected) => {
    const h = await setup(opts);
    if (renderIndex !== null) h.rendered({ index: renderIndex });
    const s = h.state();
    expect(s.progress.spinePercent).toBe(expected);
    if (renderIndex === null) {
      expect(s.section.index).toBe(-1);
      expect(s.section.requestedIndex).toBe(-1);
    }
  });

  it("U13: requestedIndex stays fixed while index follows renders", async () => {
    const h = await setup({ chapterIndex: 1, totalChapters: 5 });
    const a = h.state();
    h.rendered({ index: 3 });
    const b = h.state();
    h.rendered({ index: 0 });
    const c = h.state();
    expect([a, b, c].map((s) => s.section.requestedIndex)).toEqual([1, 1, 1]);
    expect([a, b, c].map((s) => s.section.index)).toEqual([1, 3, 0]);
    expect(h.win.Reader3Ctx!.chapterIndex).toBe(0);
  });

  it("U13b: requestedIndex is captured at IIFE start, not on the first getter call", async () => {
    const h = await setup({ chapterIndex: 1, totalChapters: 5 });
    h.rendered({ href: "ch3.xhtml", index: 3 });
    expect(h.win.Reader3Ctx!.chapterIndex).toBe(3);
    const s = h.state();
    expect(s.section.requestedIndex).toBe(1);
    expect(s.section.index).toBe(3);
  });

  it("U9: a throwing rendition.location getter is isolated to the location fields", async () => {
    const h = await setup({ chapterIndex: 1, totalChapters: 5, stubDiag: stubDiag(diagFixture(3)) });
    h.rendered({ index: 2 }, h.doc(`<p><mark data-annotation-ids='["a"]'>x</mark></p>`));
    Object.defineProperty(h.rendition, "location", {
      get() {
        throw new Error("boom");
      },
      configurable: true,
    });
    let s: DebugState | undefined;
    expect(() => {
      s = h.state();
    }).not.toThrow();
    expect(typeof s).toBe("object");
    expect(typeof s!.ready).toBe("boolean");
    expect(s!.ready).toBe(false);
    expect(s!.cfi).toBeNull();
    expect(s!.errors.some((e) => e === "cfi: boom")).toBe(true);
    for (const e of s!.errors) expect(e).toMatch(/^[a-zA-Z.]+: /);
    expect(s!.annotations).toEqual({ renderedIds: 1, marks: 1 });
    expect(s!.section.index).toBe(2);
    expect(s!.section.requestedIndex).toBe(1);
    expect(s!.diag.length).toBe(3);
    expect(s!.section.href).toBeNull();
    expect(s!.progress.sectionPage).toBeNull();
    expect(s!.progress.sectionPercent).toBeNull();
  });
});

// ---- Pill and sectionProgressOf -----------------------------------------------------
describe("sectionProgressOf and the reading-progress pill", () => {
  it("U12: pill regression across three input classes, getter half reports null for the invalid two", async () => {
    const h = await setup();
    const cases: Array<[unknown, string, number | null, { page: number; total: number } | null]> = [
      [loc(3, 10), "当前阅读至 30%", 30, { page: 3, total: 10 }],
      [{ start: { cfi: "epubcfi(/6/2!/4/1:0)" }, end: { cfi: "epubcfi(/6/2!/4/1:9)" } }, "当前阅读至 0%", null, null],
      [loc(NaN, 10), "当前阅读至 0%", null, null],
    ];
    for (const [location, pill, percent, page] of cases) {
      h.relocated(location);
      expect(h.pill()).toBe(pill);
      expect(h.pill()).toBe(legacyPill(location));
      const s = h.state();
      expect(s.progress.sectionPercent).toBe(percent);
      expect(s.progress.sectionPage).toEqual(page);
      expect(s.errors).toEqual([]);
    }
  });

  it("U12b: NaN page with a truthy total suppresses the percentage fallback (R4)", async () => {
    const h = await setup();
    const location = {
      start: { cfi: "epubcfi(/6/2!/4/1:0)", displayed: { page: NaN, total: 10 }, percentage: 0.5 },
      end: { cfi: "epubcfi(/6/2!/4/1:9)" },
    };
    h.relocated(location);
    expect(h.pill()).toBe("当前阅读至 0%");
    expect(h.pill()).toBe(legacyPill(location));
    expect(h.state().progress.sectionPercent).toBeNull();
  });

  it("U12c: the percentage fallback still drives the pill when displayed is absent; the getter never reports it", async () => {
    const h = await setup();
    const location = { start: { cfi: "epubcfi(/6/2!/4/1:0)", percentage: 0.5 }, end: { cfi: "epubcfi(/6/2!/4/1:9)" } };
    h.relocated(location);
    expect(h.pill()).toBe("当前阅读至 50%");
    expect(h.pill()).toBe(legacyPill(location));
    const s = h.state();
    expect(s.progress.sectionPercent).toBeNull();
    expect(s.progress.bookPercent).toBeNull();
  });

  it("U17: total of 0 gives null section progress and no error", async () => {
    const h = await setup();
    const location = loc(0, 0);
    h.relocated(location);
    const s = h.state();
    expect(s.progress.sectionPage).toBeNull();
    expect(s.progress.sectionPercent).toBeNull();
    expect(s.errors).toEqual([]);
    expect(h.pill()).toBe("当前阅读至 0%");
    expect(h.pill()).toBe(legacyPill(location));
  });

  it("U19: pill agreement property against the frozen legacyPill oracle", async () => {
    const h = await setup();
    const pageArb = fc.oneof(fc.integer({ min: -5, max: 500 }), fc.constant(NaN), fc.constant(undefined));
    const totalArb = fc.oneof(fc.integer({ min: -3, max: 200 }), fc.constant(0), fc.constant(NaN), fc.constant(undefined));
    const pctArb = fc.oneof(fc.constant(0), fc.double({ min: 0, max: 1, noNaN: true }), fc.constant(undefined));
    const displayedArb = fc.record({ page: pageArb, total: totalArb }, { requiredKeys: [] });
    const startArb = fc.record(
      { cfi: fc.constant("epubcfi(/6/2!/4/1:0)"), displayed: displayedArb, percentage: pctArb },
      { requiredKeys: ["cfi"] },
    );
    const locArb = fc.oneof(
      fc.constant(undefined),
      fc.record({ start: startArb, end: fc.constant({ cfi: "epubcfi(/6/2!/4/1:9)" }) }, { requiredKeys: ["end"] }),
    );
    fc.assert(
      fc.property(locArb, (location) => {
        h.relocated(location);
        const s = h.state();
        // (a) pill is unchanged relative to the frozen oracle
        expect(h.pill()).toBe(legacyPill(location));
        const { sectionPage, sectionPercent, bookPercent } = s.progress;
        // (b) getter and pill agree whenever the getter reports a percent
        if (sectionPercent !== null) {
          expect(h.pill()).toBe(`当前阅读至 ${sectionPercent}%`);
          expect(sectionPercent).toBe(Math.round((sectionPage!.page / sectionPage!.total) * 100));
        }
        // (c) sectionPercent and sectionPage are null together
        expect(sectionPercent === null).toBe(sectionPage === null);
        // (d) bookPercent is always null in v1
        expect(bookPercent).toBeNull();
        // (e) a valid location never produces an error entry (G1)
        if (location && "start" in location && location.start && location.end) {
          expect(s.errors).toEqual([]);
        }
      }),
      { numRuns: 300 },
    );
  });
});

// ---- Annotations --------------------------------------------------------------------
describe("getDebugState: annotations", () => {
  it("U5: annotation IDs are deduplicated across marks; plain marks are not counted", async () => {
    const h = await setup();
    h.rendered(
      { index: 0 },
      h.doc(
        `<p>x <mark data-annotation-ids='["a"]'>1</mark> <mark data-annotation-ids='["a","b"]'>2</mark> ` +
          `<mark data-annotation-ids='["c"]'>3</mark> <mark>plain</mark></p>`,
      ),
    );
    expect(h.state().annotations).toEqual({ renderedIds: 3, marks: 3 });
  });

  it("U11: annotations are recounted from the current contents after a chapter change", async () => {
    const h = await setup();
    h.rendered({ index: 0 }, h.doc(`<mark data-annotation-ids='["a"]'>1</mark><mark data-annotation-ids='["b"]'>2</mark>`));
    const s1 = h.state();
    h.rendered({ index: 1 }, h.doc(`<mark data-annotation-ids='["z"]'>1</mark>`));
    const s2 = h.state();
    expect(s1.annotations).toEqual({ renderedIds: 2, marks: 2 });
    expect(s1.section.index).toBe(0);
    expect(s2.annotations).toEqual({ renderedIds: 1, marks: 1 });
    expect(s2.section.index).toBe(1);
  });

  it("U15: contents not ready gives null without error; ready-and-empty gives {0,0}", async () => {
    const notReady = await setup();
    const s1 = notReady.state();
    expect(s1.annotations).toBeNull();
    expect(s1.errors.some((e) => e.startsWith("annotations"))).toBe(false);

    const empty = await setup();
    empty.rendered({ index: 0 }, empty.doc("<p>no marks here</p>"));
    expect(empty.state().annotations).toEqual({ renderedIds: 0, marks: 0 });
  });

  it("U6: invalid mark JSON nulls annotations with one error and leaves every other field intact", async () => {
    const good = `<mark data-annotation-ids='["a"]'>1</mark><mark data-annotation-ids='["b"]'>2</mark>`;
    const control = await setup({ chapterIndex: 2 });
    control.rendered({ index: 2 }, control.doc(good));
    control.relocated(loc(3, 10));
    const bad = await setup({ chapterIndex: 2 });
    bad.rendered({ index: 2 }, bad.doc(good + `<mark data-annotation-ids='[not json'>3</mark>`));
    bad.relocated(loc(3, 10));

    let sb: DebugState | undefined;
    expect(() => {
      sb = bad.state();
    }).not.toThrow();
    const sc = control.state();
    expect(sb!.annotations).toBeNull();
    expect(sb!.errors.filter((e) => e.startsWith("annotations: ")).length).toBe(1);
    expect({ ...sb!, annotations: undefined, errors: undefined }).toEqual({
      ...sc,
      annotations: undefined,
      errors: undefined,
    });
  });

  it.each([
    ["a string", `'"abc"'`],
    ["an object", `'{"x":1}'`],
  ])("U6b: mark JSON that parses to %s is treated as corrupt (R7)", async (_label, attr) => {
    const h = await setup();
    h.rendered({ index: 2 }, h.doc(`<mark data-annotation-ids='["a"]'>1</mark><mark data-annotation-ids=${attr}>2</mark>`));
    h.relocated(loc(3, 10));
    const s = h.state();
    expect(s.annotations).toBeNull();
    expect(s.errors.filter((e) => e.startsWith("annotations: ")).length).toBe(1);
    expect(s.ready).toBe(true);
    expect(s.progress.sectionPercent).toBe(30);
  });
});

// ---- Diag ---------------------------------------------------------------------------
describe("getDebugState: diag", () => {
  it("U7: diag is an ordered suffix, truncated at the top, and empty when Reader3NotesDiag is absent", async () => {
    const h = await setup({ stubDiag: stubDiag(diagFixture(30)) });
    expect(h.state({ diagLimit: 5 }).diag.map((e) => e.id)).toEqual(ids(25, 29));
    const all = h.state({ diagLimit: 500 });
    expect(all.diag.length).toBe(30);
    expect(all.diag.map((e) => e.id)).toEqual(ids(0, 29));
    expect(h.state().diag.map((e) => e.id)).toEqual(ids(10, 29));
    let sNull: DebugState | undefined;
    expect(() => {
      sNull = h.state(null);
    }).not.toThrow();
    expect(sNull!.diag.map((e) => e.id)).toEqual(ids(10, 29));
    expect(all.diagAvailable).toBe(true);

    const absent = await setup();
    const s = absent.state();
    expect(s.diag).toEqual([]);
    expect(s.diagAvailable).toBe(false);
    expect(s.errors.some((e) => e.startsWith("diag"))).toBe(false);
  });

  it.each([
    ["0", 0, [] as string[]],
    ["-3", -3, [] as string[]],
    ["NaN", NaN, ids(10, 29)],
    ['"5"', "5", ids(10, 29)],
  ])("U16: diagLimit %s", async (_label, n, expected) => {
    const h = await setup({ stubDiag: stubDiag(diagFixture(30)) });
    expect(h.state({ diagLimit: n }).diag.map((e) => e.id)).toEqual(expected);
  });

  it.each([
    ["2.7 floors to 2", 2.7, 2],
    ["-0.5 floors to -1 and clamps to 0", -0.5, 0],
    ["100.9 floors to 100", 100.9, 100],
    ["101 clamps to 100", 101, 100],
    ["Infinity falls back to 20", Infinity, 20],
    ["-Infinity falls back to 20", -Infinity, 20],
    ["true falls back to 20", true, 20],
    ["{} falls back to 20", {}, 20],
  ])("U16b: diagLimit %s (R1)", async (_label, n, k) => {
    const h = await setup({ stubDiag: stubDiag(diagFixture(150)) });
    const d = h.state({ diagLimit: n }).diag;
    expect(d.length).toBe(k);
    if (k > 0) {
      expect(d[0]!.id).toBe(`id-${150 - k}`);
      expect(d[k - 1]!.id).toBe("id-149");
    }
  });

  it("U20: diagLimit suffix law over arbitrary inputs", async () => {
    const h = await setup();
    const L = (n: unknown) =>
      typeof n === "number" && Number.isFinite(n) ? Math.min(100, Math.max(0, Math.floor(n))) : 20;
    const nArb = fc.oneof(
      fc.anything(),
      fc.double(),
      fc.integer({ min: -10, max: 200 }),
      fc.constantFrom(NaN, Infinity, -0, "5", null, undefined),
    );
    fc.assert(
      fc.property(nArb, fc.integer({ min: 0, max: 150 }), (n, count) => {
        const fixture = diagFixture(count);
        h.win.Reader3NotesDiag = stubDiag(fixture);
        let s: DebugState | undefined;
        expect(() => {
          s = h.state({ diagLimit: n });
        }).not.toThrow();
        const k = Math.min(L(n), count);
        expect(s!.diag.map((e) => e.id)).toEqual(fixture.slice(count - k).map((e) => e.id));
      }),
      { numRuns: 500 },
    );
  });

  it("U18: hostile values through the real record() are narrowed", async () => {
    const h = await setup({ realDiag: true });
    const diag = h.win.Reader3NotesDiag as NotesDiagSurface;
    const cyc: Record<string, unknown> = { op: "c" };
    cyc.self = cyc;
    cyc.id = cyc;
    diag.record({ op: { x: 1 } });
    diag.record({ id: "i".repeat(200) });
    diag.record({ status: "500" });
    diag.record({ ok: "yes" });
    diag.record(cyc);
    const s = h.state();
    expect(s.diag.length).toBe(5);
    expect(s.diag[0]!.op).toBeNull();
    expect(s.diag[1]!.id).toBe("i".repeat(64));
    expect(s.diag[1]!.id!.length).toBe(64);
    expect(s.diag[2]!.status).toBeNull();
    expect(s.diag[3]!.ok).toBeNull();
    expect(s.diag[4]!.op).toBe("c");
    expect(s.diag[4]!.id).toBeNull();
    for (const e of s.diag) {
      expect(Number.isFinite(e.t)).toBe(true);
      expect(e.requested).toBeNull();
    }
    expect(() => JSON.stringify(s)).not.toThrow();
  });

  it("U18b: fields real record() cannot corrupt are still narrowed; non-objects become all-null records (R9)", async () => {
    const entries = [
      { op: "create", requested: "true", status: Infinity, ok: 1, id: 42, t: "now" },
      { t: NaN, status: NaN },
      { t: -0, status: -0 },
      null,
      7,
    ];
    const h = await setup({ stubDiag: { entries: () => entries } });
    const s = h.state();
    const allNull = { op: null, requested: null, status: null, ok: null, id: null, t: null };
    expect(s.diag.length).toBe(5);
    expect(s.diag[0]).toEqual({ op: "create", requested: null, status: null, ok: null, id: null, t: null });
    expect(s.diag[1]!.t).toBeNull();
    expect(s.diag[1]!.status).toBeNull();
    expect(Object.is(s.diag[2]!.t, 0)).toBe(true);
    expect(Object.is(s.diag[2]!.status, 0)).toBe(true);
    expect(s.diag[3]).toEqual(allNull);
    expect(s.diag[4]).toEqual(allNull);
    expect(JSON.parse(JSON.stringify(s))).toEqual(s);
  });

  it("U21: narrowing, preservation and round-trip law over the real record()", async () => {
    const h = await setup({ realDiag: true });
    const diag = h.win.Reader3NotesDiag as NotesDiagSurface;
    const anyArb = fc.anything({ withBoxedValues: true, withMap: true, withSet: true, withNullPrototype: true });
    const validArb = fc.record({
      op: fc.string({ maxLength: 80 }),
      id: fc.string({ maxLength: 200 }),
      status: fc.oneof(fc.integer(), fc.double()),
      ok: fc.boolean(),
      requested: fc.boolean(),
    });
    const isFiniteNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
    fc.assert(
      fc.property(fc.array(fc.oneof(anyArb, validArb), { maxLength: 30 }), (inputs) => {
        for (const el of inputs) diag.record(el);
        const raw = diag.entries() as Array<Record<string, unknown>>;
        const s = h.state({ diagLimit: 100 });
        expect(s.diag.length).toBe(raw.length);
        const offset = raw.length - inputs.length; // the ring holds at most 100; inputs are its tail
        s.diag.forEach((o, j) => {
          const r = raw[j]!;
          expect(Object.keys(o).sort()).toEqual(["id", "ok", "op", "requested", "status", "t"]);
          expect(o.op === null || (typeof o.op === "string" && o.op.length <= 32)).toBe(true);
          expect(o.id === null || (typeof o.id === "string" && o.id.length <= 64)).toBe(true);
          expect(o.status === null || isFiniteNum(o.status)).toBe(true);
          expect(o.ok === null || typeof o.ok === "boolean").toBe(true);
          expect(o.requested === null || typeof o.requested === "boolean").toBe(true);
          // G4: t is the raw ring value, exactly, with -0 normalised to 0
          expect(o.t).toBe(r.t === 0 ? 0 : r.t);
          if (j >= offset) {
            // record() stores `(entry || {}).field ?? null`
            const src = (inputs[j - offset] || {}) as Record<string, unknown>;
            if (typeof src.op === "string") expect(o.op).toBe(src.op.slice(0, 32));
            if (typeof src.id === "string") expect(o.id).toBe(src.id.slice(0, 64));
            if (isFiniteNum(src.status)) expect(o.status).toBe(src.status === 0 ? 0 : src.status);
            if (typeof src.ok === "boolean") expect(o.ok).toBe(src.ok);
            if (typeof src.requested === "boolean") expect(o.requested).toBe(src.requested);
          }
        });
        expect(JSON.parse(JSON.stringify(s))).toEqual(s);
      }),
      { numRuns: 200 },
    );
  });

  it("U24: Reader3NotesDiag is looked up at call time, not captured at init", async () => {
    const h = await setup();
    const a = h.state();
    expect(a.diagAvailable).toBe(false);
    expect(a.diag).toEqual([]);
    h.win.eval(annotationsSrc);
    (h.win.Reader3NotesDiag as NotesDiagSurface).record({ op: "late", id: "L1" });
    const b = h.state();
    expect(b.diagAvailable).toBe(true);
    expect(b.diag.length).toBe(1);
    expect(b.diag[0]!.op).toBe("late");
    expect(b.diag[0]!.id).toBe("L1");
  });

  it.each([
    [
      "(i) entries() throws",
      {
        entries: () => {
          throw new Error("gone");
        },
      },
    ],
    ["(ii) entries() returns a non-array", { entries: () => "nope" }],
    ["(iii) entries is missing", {}],
  ])("U26: %s gives diag [] with one diag error (R8)", async (label, notesDiag) => {
    const h = await setup({ stubDiag: notesDiag });
    h.relocated(loc(3, 10));
    let s: DebugState | undefined;
    expect(() => {
      s = h.state();
    }).not.toThrow();
    expect(s!.diag).toEqual([]);
    expect(s!.diagAvailable).toBe(true);
    const diagErrors = s!.errors.filter((e) => e.startsWith("diag: "));
    expect(diagErrors.length).toBe(1);
    if (label.startsWith("(i)")) expect(diagErrors[0]).toBe("diag: gone");
    expect(s!.progress.sectionPercent).toBe(30);
    expect(s!.ready).toBe(true);
  });
});

// ---- Read-only, idempotent, serializable --------------------------------------------
const SENTINEL = "SENTINEL-不应外泄-7f3a";

function leavesArePlain(value: unknown): boolean {
  if (value === null) return true;
  if (typeof value === "string" || typeof value === "boolean") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (Array.isArray(value)) return value.every(leavesArePlain);
  if (typeof value === "object") {
    const proto = Object.getPrototypeOf(value);
    if (proto !== Object.prototype && proto !== null && proto?.constructor?.name !== "Object") return false;
    return Object.values(value as object).every(leavesArePlain);
  }
  return false; // undefined, function, symbol, bigint
}

describe("getDebugState: read-only invariants", () => {
  it.each([
    ["(a) before relocated, no contents", "a"],
    ["(b) after rendered + relocated with sentinel text", "b"],
    ["(c) state (b) with the real diag ring", "c"],
  ])("U8: read-only, idempotent and serializable %s", async (_label, state) => {
    const h = await setup({ realDiag: state === "c" });
    const { win, rendition } = h;
    let iframeDoc: Document | null = null;
    if (state !== "a") {
      iframeDoc = h.doc(`<p>${SENTINEL} <mark data-annotation-ids='["a"]'>${SENTINEL}</mark></p>`);
      h.rendered({ index: 1 }, iframeDoc);
      h.relocated(loc(3, 10));
    }
    if (state === "c") {
      const diag = win.Reader3NotesDiag as NotesDiagSurface;
      diag.record({ op: "create", id: "n1" });
      diag.record({ op: SENTINEL + "x".repeat(40), id: "n2" });
      diag.record({ op: "delete", id: "n3", status: 409 });
    }
    await flush();

    const notesDiag = win.Reader3NotesDiag as NotesDiagSurface | undefined;
    const snapshot = () => ({
      body: win.document.body.innerHTML,
      iframeBody: iframeDoc?.body.innerHTML ?? null,
      href: win.location.href,
      locationJson: JSON.stringify(rendition.location),
      calls: { ...rendition.calls },
      diagLength: notesDiag?.entries().length ?? null,
      ctx: JSON.stringify(win.Reader3Ctx),
      historyLength: win.history.length,
    });
    // jsdom artifact, not the getter: the FIRST querySelectorAll on a document builds
    // @asamuzakjp/dom-selector's Evaluator, whose constructor registers 9 listeners
    // (focus, keydown, mouse*, click) on the window. Chromium has no such lazy init
    // (E4 is the real-browser check). Warm the engine up before the probes go in.
    iframeDoc?.querySelectorAll("[data-annotation-ids]");
    const before = snapshot();
    const locationRef = rendition.location;

    // Probes installed after setup, so they measure the calls alone.
    const counters = { addEventListener: 0, events: 0, layout: 0 };
    const wrapAdd = (target: EventTarget) => {
      const original = target.addEventListener;
      target.addEventListener = function (this: EventTarget, ...args: Parameters<EventTarget["addEventListener"]>) {
        counters.addEventListener++;
        return original.apply(this, args);
      } as EventTarget["addEventListener"];
    };
    for (const name of [
      "reader3:chapter:change",
      "reader3:content:rendered",
      "reader3:content:click",
      "reader3:escape",
      "reader3:annotations:updated",
    ]) {
      win.addEventListener(name, () => counters.events++);
    }
    wrapAdd(win);
    wrapAdd(win.document);
    if (iframeDoc) wrapAdd(iframeDoc);
    const proto = win.Element.prototype;
    const origRect = proto.getBoundingClientRect;
    const origRects = proto.getClientRects;
    proto.getBoundingClientRect = function (this: Element) {
      counters.layout++;
      return origRect.call(this);
    };
    proto.getClientRects = function (this: Element) {
      counters.layout++;
      return origRects.call(this);
    };

    const s1 = h.state();
    const s2 = h.state();

    proto.getBoundingClientRect = origRect;
    proto.getClientRects = origRects;

    // (i) world unchanged
    expect(snapshot()).toEqual(before);
    expect(rendition.location).toBe(locationRef);
    // (ii) every counter delta is 0
    expect(rendition.calls).toEqual(before.calls);
    expect(counters).toEqual({ addEventListener: 0, events: 0, layout: 0 });
    // (iii) JSON round-trip
    expect(JSON.parse(JSON.stringify(s1))).toEqual(s1);
    // (iv) no book text
    const json = JSON.stringify(s1);
    if (state === "b") expect(json).not.toContain(SENTINEL);
    if (state === "c") {
      expect(json).not.toContain("x".repeat(40));
      // the sentinel may appear only once: inside the truncated diag op, never from the iframe
      expect(json.split(SENTINEL).length - 1).toBe(1);
    }
    // (v) idempotent
    expect(s2).toEqual(s1);
    // (vi) only plain leaves
    expect(leavesArePlain(s1)).toBe(true);
    // (vii) no errors
    expect(s1.errors).toEqual([]);
  });
});

// ---- Added after green: branch paths found by re-deriving the map from the code ----
describe("getDebugState: paths derived from the implementation", () => {
  it.each([
    ["a non-Error string", () => "str", "cfi: str"],
    ["an unstringifiable value", () => Object.create(null), "cfi: unknown error"],
  ])("U27: a location read that throws %s still yields a per-field message", async (_label, thrown, expected) => {
    const h = await setup();
    Object.defineProperty(h.rendition, "location", {
      get() {
        throw thrown();
      },
      configurable: true,
    });
    let s: DebugState | undefined;
    expect(() => {
      s = h.state();
    }).not.toThrow();
    expect(s!.errors).toEqual([expected]);
    expect(s!.ready).toBe(false);
  });

  it("U28: a location whose start accessor throws isolates cfi, section.href and progress.section", async () => {
    const h = await setup({ chapterIndex: 2, totalChapters: 5, stubDiag: stubDiag(diagFixture(3)) });
    h.rendered({ index: 2 }, h.doc(`<mark data-annotation-ids='["a"]'>x</mark>`));
    // assigned directly: relocated would throw inside the renderer's own pill update
    h.rendition.location = {
      get start() {
        throw new Error("bad start");
      },
      end: { cfi: "epubcfi(/6/2!/4/1:9)" },
    };
    const s = h.state();
    expect(s.ready).toBe(true);
    expect(s.cfi).toBeNull();
    expect(s.section).toEqual({ index: 2, href: null, requestedIndex: 2, spineCount: 5 });
    expect(s.progress).toEqual({ sectionPage: null, sectionPercent: null, spinePercent: 50, bookPercent: null });
    expect(s.annotations).toEqual({ renderedIds: 1, marks: 1 });
    expect(s.diag.length).toBe(3);
    expect([...s.errors].sort()).toEqual(["cfi: bad start", "progress.section: bad start", "section.href: bad start"]);
  });

  it("U29: a non-numeric rendered section.index is reported as null and spinePercent follows", async () => {
    const h = await setup({ chapterIndex: 1, totalChapters: 5 });
    h.rendered({ index: "3" as unknown as number });
    const s = h.state();
    expect(s.section.index).toBeNull();
    expect(s.section.requestedIndex).toBe(1);
    expect(s.progress.spinePercent).toBeNull();
    expect(s.errors).toEqual([]);
  });

  it("U30: without #reading-progress, relocated is a no-op for the pill and the getter still reports", async () => {
    const h = await setup({ noProgressEl: true });
    expect(() => h.relocated(loc(3, 10))).not.toThrow();
    const s = h.state();
    expect(s.progress.sectionPercent).toBe(30);
    expect(s.errors).toEqual([]);
  });

  it("U31: a throwing totalChapters read is isolated to section.spineCount", async () => {
    const h = await setup({ chapterIndex: 1, totalChapters: 5 });
    h.relocated(loc(3, 10));
    Object.defineProperty(h.win.Reader3Ctx!, "totalChapters", {
      get() {
        throw new Error("ctx gone");
      },
      configurable: true,
    });
    const s = h.state();
    expect(s.errors).toEqual(["section.spineCount: ctx gone"]);
    expect(s.section.spineCount).toBeNull();
    expect(s.progress.spinePercent).toBeNull();
    expect(s.progress.sectionPercent).toBe(30);
    expect(s.section.index).toBe(1);
  });
});
