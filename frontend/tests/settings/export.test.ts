// 018 WI-6 (FB-S06), cases F1..F6: the settings page's "export library JSON" button.
//   * one click -> exactly one GET /api/library/export (no query), a pretty-printed download named
//     reader3-library.json, ok text 书库已导出。; the old 「暂不支持」 stub is gone
//   * the button is disabled exactly while the request is pending; clicks while pending send nothing
//   * any non-2xx status or a network rejection is a visible error (prefix 导出书库失败：), with no
//     download, and the button is re-enabled
//
// The module exports nothing, so everything is observed through fetch (the network boundary,
// stubbed with a scripted router), URL.createObjectURL / the anchor click (the download boundary),
// and the DOM. Harness copied from revision.test.ts.
import fc from "fast-check";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@shared/theme", () => ({}));

function modal(action: string): string {
  return `
    <button type="button" data-testid="set-data-${action}">${action}</button>
    <dialog data-testid="set-modal-${action}">
      <button type="button" data-testid="set-modal-${action}-close">×</button>
      <button type="button" data-testid="set-modal-${action}-cancel">cancel</button>
      <button type="button" data-testid="set-modal-${action}-primary">ok</button>
    </dialog>`;
}

function mountSettingsBody(): void {
  document.body.innerHTML = `
    <div data-testid="set-live-region" aria-live="polite"></div>
    <div role="radiogroup">
      <button type="button" role="radio" data-testid="set-appearance-scheme-system">system</button>
      <button type="button" role="radio" data-testid="set-appearance-scheme-light">light</button>
      <button type="button" role="radio" data-testid="set-appearance-scheme-dark">dark</button>
    </div>
    <div id="set-provider-guide" role="note">guide</div>
    <div id="set-providers"></div>
    <select id="set-default-provider"></select>
    <input type="checkbox" id="set-pref-streaming">
    <input type="checkbox" id="set-pref-timestamps">
    <input type="checkbox" id="set-pref-suggest">
    <input data-testid="set-rag-chunks">
    <input data-testid="set-rag-context">
    <button type="button" id="set-save-prefs">save</button>
    <p id="set-prefs-result"></p>
    ${modal("reindex")}${modal("conversations")}${modal("cache")}
    <p id="set-data-result"></p>
    <button type="button" data-testid="set-export-json">json</button>
    <button type="button" data-testid="set-export-settings">export</button>
    <button type="button" id="set-import-settings">import</button>
    <input type="file" id="set-import-file">
    <p id="set-export-result"></p>`;
}

// Non-literal specifier: see boot-marker.test.ts for why tsc must not type-resolve the entry.
const SETTINGS_ENTRY = "../../src/settings/index.ts";
const importSettings = (): Promise<unknown> => import(/* @vite-ignore */ SETTINGS_ENTRY);

const EXPORT_URL = "/api/library/export";
const FILENAME = "reader3-library.json";
const OK_TEXT = "书库已导出。";
const ERR_PREFIX = "导出书库失败：";
const STUB_TEXT = "暂不支持";

// Vitest runs in Node; the frontend tsconfig carries no Node types, so reach the process
// object through a narrow structural type instead of the global name.
type RejectionHook = (reason: unknown) => void;
const nodeProcess = (globalThis as unknown as {
  process: { on(e: "unhandledRejection", f: RejectionHook): void; off(e: "unhandledRejection", f: RejectionHook): void };
}).process;

// ---------------------------------------------------------------------------
// scripted fetch router
// ---------------------------------------------------------------------------
interface Deferred<T> {
  promise: Promise<T>;
  resolve: (v: T) => void;
  reject: (e: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

type Reply = Response | Deferred<Response> | Error;

interface Rec {
  method: string;
  url: string;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function settingsBody(): Record<string, unknown> {
  return {
    default_provider: "openai",
    providers: ["anthropic", "openai", "gemini", "ollama", "openrouter"].map((name) => ({
      name,
      enabled: false,
      api_key_configured: false,
      base_url: "",
      model_name: "m",
    })),
    preferences: {},
  };
}

interface Router {
  records: Rec[];
  /** FIFO replies for GET /api/library/export (any query). */
  exports: Reply[];
}

function installRouter(): Router {
  const router: Router = { records: [], exports: [] };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      router.records.push({ method, url });
      if (method === "GET" && url === "/api/settings") return json(settingsBody());
      if (method === "GET" && url === "/api/ollama/status") return json({ running: false });
      if (url.startsWith(EXPORT_URL)) {
        const next = router.exports.shift();
        if (!next) throw new Error(`unscripted ${method} ${url}`);
        if (next instanceof Response) return next;
        if (next instanceof Error) throw next;
        return next.promise;
      }
      throw new Error(`unscripted ${method} ${url}`);
    }),
  );
  return router;
}

/** Every request to the library routes (the export or anything else under /api/library). */
const libraryRequests = (r: Router): Rec[] => r.records.filter((x) => x.url.startsWith("/api/library"));
const exportCount = (r: Router): number => r.records.filter((x) => x.url.startsWith(EXPORT_URL)).length;

// ---------------------------------------------------------------------------
// download capture
// ---------------------------------------------------------------------------
interface Downloads {
  blobs: Blob[];
  anchors: string[];
  revoked: string[];
}

let downloads: Downloads;
const realCreate = URL.createObjectURL;
const realRevoke = URL.revokeObjectURL;

function installDownloads(): Downloads {
  const d: Downloads = { blobs: [], anchors: [], revoked: [] };
  URL.createObjectURL = ((obj: Blob | MediaSource): string => {
    d.blobs.push(obj as Blob);
    return `blob:fixture/${d.blobs.length}`;
  }) as typeof URL.createObjectURL;
  URL.revokeObjectURL = ((url: string): void => {
    d.revoked.push(url);
  }) as typeof URL.revokeObjectURL;
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    d.anchors.push(this.download);
  });
  return d;
}

async function blobText(blob: Blob): Promise<string> {
  if (typeof blob.text === "function") return blob.text();
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

// ---------------------------------------------------------------------------
// DOM handles
// ---------------------------------------------------------------------------
const exportButton = (): HTMLButtonElement =>
  document.querySelector<HTMLButtonElement>('[data-testid="set-export-json"]') as HTMLButtonElement;
const result = (): HTMLElement => document.getElementById("set-export-result") as HTMLElement;

async function flush3(): Promise<void> {
  for (let i = 0; i < 3; i += 1) await new Promise((r) => setTimeout(r, 0));
}

const FAST = { timeout: 2000, interval: 1 };

async function settled(): Promise<void> {
  await vi.waitFor(() => expect(["ok", "error"]).toContain(result().dataset.state), FAST);
  await flush3();
}

async function bootPage(): Promise<Router> {
  document.documentElement.removeAttribute("data-r3-page");
  mountSettingsBody();
  const router = installRouter();
  await importSettings();
  await vi.waitFor(() => expect(document.documentElement.getAttribute("data-r3-page")).toBe("settings"), FAST);
  return router;
}

function teardown(): void {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  URL.createObjectURL = realCreate;
  URL.revokeObjectURL = realRevoke;
  document.body.replaceChildren();
  document.documentElement.removeAttribute("data-r3-page");
}

beforeEach(() => {
  vi.resetModules();
  downloads = installDownloads();
});

afterEach(() => {
  teardown();
});

// ---------------------------------------------------------------------------
// F1 .. F5
// ---------------------------------------------------------------------------
describe("export library JSON (FB-S06)", () => {
  it("F1: one click sends exactly one GET /api/library/export and downloads the exact pretty JSON", async () => {
    const payload = {
      books: [
        {
          book_id: "a_data",
          title: '甲 "q"',
          authors: ["乙"],
          cover_url: null,
          book_uuid: null,
          annotations: [],
          component_errors: [],
        },
      ],
    };
    const router = await bootPage();
    router.exports.push(json(payload));
    const before = router.records.length;

    exportButton().click();
    await flush3();
    expect(libraryRequests({ ...router, records: router.records.slice(before) })).toEqual([
      { method: "GET", url: EXPORT_URL },
    ]);
    await settled();

    expect(downloads.anchors).toEqual([FILENAME]);
    expect(downloads.blobs).toHaveLength(1);
    expect(await blobText(downloads.blobs[0])).toBe(JSON.stringify(payload, null, 2));
    expect(result().dataset.state).toBe("ok");
    expect(result().textContent).toBe(OK_TEXT);
    expect(result().textContent).not.toContain(STUB_TEXT);
    expect(exportButton().disabled).toBe(false);
  });

  it("F2: the button is disabled exactly while the request is pending", async () => {
    const router = await bootPage();
    const pending = deferred<Response>();
    router.exports.push(pending);

    exportButton().click();
    await flush3();
    expect(exportCount(router)).toBe(1);
    expect(exportButton().disabled).toBe(true);
    expect(result().dataset.state).not.toBe("error");

    pending.resolve(json({ books: [] }));
    await settled();
    expect(exportButton().disabled).toBe(false);
    expect(result().dataset.state).toBe("ok");
  });

  it("F3 same_tick: a same-tick double click sends one request and downloads once", async () => {
    const router = await bootPage();
    router.exports.push(json({ books: [] }), json({ books: [] }));

    exportButton().click();
    exportButton().click();
    await flush3();
    expect(exportCount(router)).toBe(1);
    await settled();
    expect(exportCount(router)).toBe(1);
    expect(downloads.anchors).toHaveLength(1);
  });

  it("F3 while_pending: clicks while pending send nothing; after settle one click sends exactly one more", async () => {
    const router = await bootPage();
    const pending = deferred<Response>();
    router.exports.push(pending);

    exportButton().click();
    await flush3();
    expect(exportCount(router)).toBe(1);
    exportButton().click();
    exportButton().dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await flush3();
    expect(exportCount(router)).toBe(1);

    pending.resolve(json({ books: [] }));
    await settled();
    result().dataset.state = "";
    router.exports.push(json({ books: [] }));
    exportButton().click();
    await settled();
    expect(exportCount(router)).toBe(2);
    expect(downloads.anchors).toHaveLength(2);
  });

  it.each([
    ["500 with detail", () => json({ detail: "boom" }, 500), 500, "boom"],
    ["400 with detail", () => json({ detail: 'include must be "conversations"' }, 400), 400, 'include must be "conversations"'],
    ["404 empty body", () => new Response("", { status: 404 }), 404, null],
  ] as Array<[string, () => Response, number, string | null]>)(
    "F4 %s: an HTTP failure is visible, nothing is downloaded, the button is re-enabled",
    async (_row, reply, status, detail) => {
      const router = await bootPage();
      router.exports.push(reply());

      exportButton().click();
      await flush3();
      expect(exportCount(router)).toBe(1);
      await settled();

      const text = result().textContent ?? "";
      expect(result().dataset.state).toBe("error");
      expect(text.startsWith(ERR_PREFIX)).toBe(true);
      expect(text).toContain(`HTTP ${status}`);
      if (detail !== null) expect(text).toContain(detail);
      expect(downloads.blobs).toHaveLength(0);
      expect(downloads.anchors).toHaveLength(0);
      expect(exportButton().disabled).toBe(false);
    },
  );

  it("F5: a network rejection is visible and the button is re-enabled", async () => {
    const unhandled: unknown[] = [];
    const onUnhandled = (reason: unknown): void => {
      unhandled.push(reason);
    };
    nodeProcess.on("unhandledRejection", onUnhandled);
    try {
      const router = await bootPage();
      router.exports.push(new TypeError("Failed to fetch"));

      exportButton().click();
      await flush3();
      expect(exportCount(router)).toBe(1);
      await settled();

      const text = result().textContent ?? "";
      expect(result().dataset.state).toBe("error");
      expect(text.startsWith(ERR_PREFIX)).toBe(true);
      expect(text).toContain("Failed to fetch");
      expect(downloads.anchors).toHaveLength(0);
      expect(exportButton().disabled).toBe(false);
      await flush3();
      expect(unhandled).toEqual([]);
    } finally {
      nodeProcess.off("unhandledRejection", onUnhandled);
    }
  });
});

// ---------------------------------------------------------------------------
// F6: the status law
// ---------------------------------------------------------------------------
describe("export status law", () => {
  it(
    "F6: 2xx -> ok and one download; any other status -> error and no download; always re-enabled",
    async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.integer({ min: 200, max: 599 }).filter((s) => ![204, 205, 304].includes(s)),
          async (status) => {
            teardown();
            vi.resetModules();
            downloads = installDownloads();
            const router = await bootPage();
            router.exports.push(json({ books: [], detail: "d" }, status));

            exportButton().click();
            await flush3();
            expect(exportCount(router)).toBe(1);
            await settled();

            const text = result().textContent ?? "";
            if (status >= 200 && status < 300) {
              expect(result().dataset.state).toBe("ok");
              expect(downloads.anchors).toEqual([FILENAME]);
            } else {
              expect(result().dataset.state).toBe("error");
              expect(text.startsWith(ERR_PREFIX)).toBe(true);
              expect(downloads.anchors).toHaveLength(0);
              expect(downloads.blobs).toHaveLength(0);
            }
            expect(exportButton().disabled).toBe(false);
            expect(exportCount(router)).toBe(1);
          },
        ),
        { numRuns: 60, endOnFailure: true },
      );
    },
    60_000,
  );
});


// ---------------------------------------------------------------------------
// F7 / F8 (FX37-8, audit #8 / #18): a 2xx is only a download when its body is the export envelope
// ---------------------------------------------------------------------------
describe("export envelope (FX37-8)", () => {
  const raw = (body: string): (() => Response) => () =>
    new Response(body, { status: 200, headers: { "Content-Type": "application/json" } });

  it.each([
    ["empty body", raw("")],
    ["html body", raw("<html><body>proxy error</body></html>")],
    ["truncated json", raw('{"books": [')],
    ["null", () => json(null)],
    ["array", () => json([])],
    ["empty object", () => json({})],
    ["books is an object", () => json({ books: {} })],
    ["books is a string", () => json({ books: "x" })],
    ["books is null", () => json({ books: null })],
  ] as Array<[string, () => Response]>)(
    "F7 %s: a 200 that is not {books: [...]} is an error, nothing is downloaded, the button is re-enabled",
    async (_row, reply) => {
      const router = await bootPage();
      router.exports.push(reply());

      exportButton().click();
      await flush3();
      expect(exportCount(router)).toBe(1);
      await settled();

      const text = result().textContent ?? "";
      expect(result().dataset.state).toBe("error");
      expect(text.startsWith(ERR_PREFIX)).toBe(true);
      expect(text.length).toBeGreaterThan(ERR_PREFIX.length);
      expect(downloads.blobs).toHaveLength(0);
      expect(downloads.anchors).toHaveLength(0);
      expect(exportButton().disabled).toBe(false);
    },
  );

  it("F8: an empty library ({books: []}) is a valid export and downloads", async () => {
    const router = await bootPage();
    router.exports.push(json({ books: [] }));

    exportButton().click();
    await settled();

    expect(result().dataset.state).toBe("ok");
    expect(downloads.anchors).toEqual([FILENAME]);
    expect(await blobText(downloads.blobs[0])).toBe(JSON.stringify({ books: [] }, null, 2));
  });
});
