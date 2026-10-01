// 018 WI-3 (009 debt #51), cases R3-3-01..14: the settings page's revision plumbing.
//   * one module-level revision: set from the boot GET's ETag, replaced only by the ETag of a
//     successful conditional write (a success without an ETag keeps it; a failure never moves it,
//     even when the failure response carries an ETag)
//   * provider save, provider toggle and the preferences save send If-Match: <revision> when one
//     is known, and no If-Match at all when none is; Content-Type is kept
//   * one page-wide queue serialises every conditional write; each reads the revision when it is
//     sent; a failed or rejected head write does not stall it
//   * a 409 is visible and distinct; non-409 errors keep their legacy text; import is
//     unconditional and outside the queue
//
// The module exports nothing, so everything is observed through the requests it issues (fetch is
// the network boundary, stubbed with a scripted router) and the DOM. The DOM is built here, as in
// boot-marker.test.ts: the Vitest suite runs from a copy of frontend/ alone.
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

const CONFLICT = "保存没有成功：设置已在别处更改，请刷新页面后再试";
const PROVIDERS = ["anthropic", "openai", "gemini", "ollama", "openrouter"] as const;
type Provider = (typeof PROVIDERS)[number];

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

type Reply = Response | Deferred<Response>;

interface Rec {
  method: string;
  url: string;
  headers: Headers;
  body: string | null;
}

function json(body: unknown, status = 200, etag?: string): Response {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (etag !== undefined) headers.ETag = etag;
  return new Response(JSON.stringify(body), { status, headers });
}

function providerBody(name: string): Record<string, unknown> {
  return { name, enabled: true, api_key_configured: false, base_url: "", model_name: "m" };
}

function settingsBody(): Record<string, unknown> {
  return {
    default_provider: "openai",
    providers: PROVIDERS.map((name) => ({
      name,
      enabled: name === "ollama",
      api_key_configured: false,
      base_url: "",
      model_name: "m",
    })),
    preferences: {},
  };
}

interface Router {
  records: Rec[];
  /** FIFO replies for PUT requests, in send order. */
  puts: Reply[];
  /** FIFO replies for POST /api/settings/import. */
  imports: Reply[];
}

function installRouter(bootEtag: string | null): Router {
  const router: Router = { records: [], puts: [], imports: [] };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      router.records.push({
        method,
        url,
        headers: new Headers(init?.headers),
        body: typeof init?.body === "string" ? init.body : null,
      });
      if (method === "GET" && url === "/api/settings") return json(settingsBody(), 200, bootEtag ?? undefined);
      if (method === "GET" && url === "/api/ollama/status") return json({ running: false });
      const queue = method === "PUT" ? router.puts : url === "/api/settings/import" ? router.imports : null;
      const next = queue?.shift();
      if (!next) throw new Error(`unscripted ${method} ${url}`);
      return next instanceof Response ? next : next.promise;
    }),
  );
  return router;
}

const putRecords = (r: Router): Rec[] => r.records.filter((x) => x.method === "PUT");
const ifMatches = (r: Router): Array<string | null> => putRecords(r).map((x) => x.headers.get("if-match"));

// ---------------------------------------------------------------------------
// DOM handles
// ---------------------------------------------------------------------------
function byProvider<T extends HTMLElement>(testid: string, p: Provider): T {
  const node = document.querySelector<T>(`[data-testid="${testid}"][data-provider="${p}"]`);
  if (!node) throw new Error(`missing ${testid} for ${p}`);
  return node;
}
const toggleOf = (p: Provider) => byProvider<HTMLButtonElement>("set-provider-toggle", p);
const saveOf = (p: Provider) => byProvider<HTMLButtonElement>("set-provider-save", p);
const modelOf = (p: Provider) => byProvider<HTMLInputElement>("set-provider-model", p);
const urlOf = (p: Provider) => byProvider<HTMLInputElement>("set-provider-url", p);
const keyOf = (p: Provider) => byProvider<HTMLInputElement>("set-provider-key", p);
const resultOf = (p: Provider) => byProvider<HTMLElement>("set-provider-result", p);
const prefsSave = () => document.getElementById("set-save-prefs") as HTMLButtonElement;
const prefsResult = () => document.getElementById("set-prefs-result") as HTMLElement;
const ragChunks = () => document.querySelector<HTMLInputElement>('[data-testid="set-rag-chunks"]') as HTMLInputElement;

function type(input: HTMLInputElement, value: string): void {
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

async function flush3(): Promise<void> {
  for (let i = 0; i < 3; i += 1) await new Promise((r) => setTimeout(r, 0));
}

const FAST = { timeout: 2000, interval: 1 };

async function idle(node: HTMLElement): Promise<void> {
  await vi.waitFor(() => expect(node.hasAttribute("aria-busy")).toBe(false), FAST);
}

async function bootPage(bootEtag: string | null): Promise<Router> {
  document.documentElement.removeAttribute("data-r3-page");
  mountSettingsBody();
  const router = installRouter(bootEtag);
  await importSettings();
  await vi.waitFor(() => expect(document.documentElement.getAttribute("data-r3-page")).toBe("settings"), FAST);
  return router;
}

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.replaceChildren();
  document.documentElement.removeAttribute("data-r3-page");
});

// ---------------------------------------------------------------------------
// R3-3-01 / R3-3-02: requestJson header merge and status
// ---------------------------------------------------------------------------
describe("requestJson", () => {
  it("header merge", async () => {
    const router = await bootPage('"e1"');
    const boot = router.records.find((x) => x.method === "GET" && x.url === "/api/settings") as Rec;
    expect(boot.headers.get("content-type")).toBeNull();
    expect(boot.headers.get("if-match")).toBeNull();

    router.puts.push(json(providerBody("ollama"), 200, '"w"'));
    saveOf("ollama").click();
    await vi.waitFor(() => expect(putRecords(router)).toHaveLength(1), FAST);
    const put = putRecords(router)[0];
    expect(put.headers.get("content-type")).toBe("application/json");
    expect(put.headers.get("if-match")).toBe('"e1"');
  });

  it.each([
    [409, CONFLICT],
    [412, "保存没有成功：HTTP 412 · x"],
    [400, "保存没有成功：HTTP 400 · x"],
  ])("only 409 is a conflict (status %i)", async (status, text) => {
    const router = await bootPage('"e0"');
    router.puts.push(json({ detail: "x" }, status));
    saveOf("ollama").click();
    await vi.waitFor(() => expect(resultOf("ollama").dataset.state).toBe("error"), FAST);
    expect(resultOf("ollama").textContent).toBe(text);
  });
});

// ---------------------------------------------------------------------------
// R3-3-03..14: module revision and the page-wide write queue
// ---------------------------------------------------------------------------
describe("revision and write queue", () => {
  it("boot revision is sent on provider save", async () => {
    const router = await bootPage('"boot-1"');
    router.puts.push(json(providerBody("ollama"), 200, '"w-1"'));
    type(modelOf("ollama"), "m-typed");
    saveOf("ollama").click();
    await vi.waitFor(() => expect(resultOf("ollama").dataset.state).toBe("ok"), FAST);
    const puts = putRecords(router);
    expect(puts).toHaveLength(1);
    expect(puts[0].url).toBe("/api/settings/providers/ollama");
    expect(puts[0].headers.get("if-match")).toBe('"boot-1"');
    expect(JSON.parse(puts[0].body as string).model_name).toBe("m-typed");
  });

  it(
    "chaining law (fast-check)",
    async () => {
      type Op = { op: "save" | "toggle" | "prefs"; provider: Provider; outcome: 200 | "200-no-etag" | 409 | 500 };
      await fc.assert(
        fc.asyncProperty(
          fc.array(
            fc.record({
              op: fc.constantFrom("save" as const, "toggle" as const, "prefs" as const),
              provider: fc.constantFrom(...PROVIDERS),
              outcome: fc.constantFrom(200 as const, "200-no-etag" as const, 409 as const, 500 as const),
            }),
            { minLength: 1, maxLength: 8 },
          ),
          async (ops: Op[]) => {
            vi.resetModules();
            const router = await bootPage('"e0"');
            let expected = "e0";
            for (let i = 0; i < ops.length; i += 1) {
              const k = i + 1;
              const { op, provider, outcome } = ops[i];
              const okBody = op === "prefs" ? {} : providerBody(provider);
              if (outcome === 200) router.puts.push(json(okBody, 200, `"e${k}"`));
              else if (outcome === "200-no-etag") router.puts.push(json(okBody, 200));
              else router.puts.push(json({ detail: "nope" }, outcome, `"bad-${k}"`));

              const control = op === "save" ? saveOf(provider) : op === "toggle" ? toggleOf(provider) : prefsSave();
              control.click();
              await vi.waitFor(() => expect(putRecords(router)).toHaveLength(k), FAST);
              await idle(control);
              expect(putRecords(router)[i].headers.get("if-match")).toBe(`"${expected}"`);
              if (outcome === 200) expected = `e${k}`;
            }
            for (const value of ifMatches(router)) expect(String(value).startsWith('"bad-')).toBe(false);
            vi.unstubAllGlobals();
          },
        ),
        { numRuns: 50 },
      );
    },
    60_000,
  );

  it("queued toggle uses the revision from the previous toggle response", async () => {
    const router = await bootPage('"e0"');
    const first = deferred<Response>();
    router.puts.push(first, json(providerBody("openai"), 200, '"t2"'));
    toggleOf("openai").click();
    toggleOf("openai").click();
    await flush3();
    expect(putRecords(router)).toHaveLength(1);

    first.resolve(json(providerBody("openai"), 200, '"t1"'));
    await vi.waitFor(() => expect(putRecords(router)).toHaveLength(2), FAST);
    await idle(toggleOf("openai"));
    expect(ifMatches(router)).toEqual(['"e0"', '"t1"']);
    expect(putRecords(router)).toHaveLength(2);
  });

  it("provider save 409 is visible", async () => {
    const router = await bootPage('"e0"');
    const bootCount = router.records.length;
    router.puts.push(json({ detail: "Settings were changed elsewhere." }, 409));
    type(modelOf("openai"), "m-typed");
    type(urlOf("openai"), "http://typed");
    type(keyOf("openai"), "sk-typed");
    saveOf("openai").click();
    await vi.waitFor(() => expect(resultOf("openai").dataset.state).toBe("error"), FAST);
    await idle(saveOf("openai"));
    await flush3();

    expect(resultOf("openai").textContent).toBe(CONFLICT);
    expect(modelOf("openai").value).toBe("m-typed");
    expect(urlOf("openai").value).toBe("http://typed");
    expect(keyOf("openai").value).toBe("sk-typed");
    expect(putRecords(router)).toHaveLength(1);
    expect(router.records.slice(bootCount).filter((x) => x.method === "GET")).toHaveLength(0);

    router.puts.push(json(providerBody("openai"), 200, '"e1"'));
    saveOf("openai").click();
    await vi.waitFor(() => expect(putRecords(router)).toHaveLength(2), FAST);
    expect(putRecords(router)[1].headers.get("if-match")).toBe('"e0"');
  });

  it("provider save 500 legacy text", async () => {
    const router = await bootPage('"e0"');
    router.puts.push(json({ detail: "boom" }, 500));
    saveOf("ollama").click();
    await vi.waitFor(() => expect(resultOf("ollama").dataset.state).toBe("error"), FAST);
    expect(resultOf("ollama").textContent).toBe("保存没有成功：HTTP 500 · boom");
  });

  it("toggle 409 reverts aria-checked", async () => {
    const router = await bootPage('"e0"');
    router.puts.push(json({ detail: "conflict" }, 409));
    toggleOf("openai").click();
    await vi.waitFor(() => expect(putRecords(router)).toHaveLength(1), FAST);
    await idle(toggleOf("openai"));
    expect(toggleOf("openai").getAttribute("aria-checked")).toBe("false");
    expect(resultOf("openai").textContent?.startsWith("开关未保存：")).toBe(true);
    expect(resultOf("openai").textContent).toContain("设置已在别处更改");

    router.puts.push(json(providerBody("openai"), 200, '"t1"'));
    toggleOf("openai").click();
    await vi.waitFor(() => expect(putRecords(router)).toHaveLength(2), FAST);
    expect(putRecords(router)[1].headers.get("if-match")).toBe('"e0"');
  });

  it("prefs 409 uses role=alert", async () => {
    const router = await bootPage('"e0"');
    router.puts.push(json({ detail: "conflict" }, 409));
    type(ragChunks(), "9");
    prefsSave().click();
    await vi.waitFor(() => expect(prefsResult().getAttribute("role")).toBe("alert"), FAST);
    const text = prefsResult().textContent ?? "";
    expect(text.startsWith("保存失败：")).toBe(true);
    expect(text).toContain("设置已在别处更改");
    expect(text).toContain("输入的内容仍在");
    expect(ragChunks().value).toBe("9");
    const puts = putRecords(router);
    expect(puts).toHaveLength(1);
    expect(puts[0].url).toBe("/api/settings");
    expect(puts[0].headers.get("if-match")).toBe('"e0"');
  });

  it("old server without ETag degrades to unconditional", async () => {
    const router = await bootPage(null);
    router.puts.push(json(providerBody("ollama"), 200));
    saveOf("ollama").click();
    await vi.waitFor(() => expect(putRecords(router)).toHaveLength(1), FAST);
    await idle(saveOf("ollama"));

    router.puts.push(json(providerBody("openai"), 200));
    toggleOf("openai").click();
    await vi.waitFor(() => expect(putRecords(router)).toHaveLength(2), FAST);
    await idle(toggleOf("openai"));

    router.puts.push(json({}, 200));
    prefsSave().click();
    await vi.waitFor(() => expect(putRecords(router)).toHaveLength(3), FAST);
    await idle(prefsSave());

    for (const put of putRecords(router)) {
      expect(put.headers.has("if-match")).toBe(false);
      expect(put.headers.get("if-match")).toBeNull();
      expect(put.headers.get("content-type")).toBe("application/json");
    }
  });

  function chooseImportFile(): void {
    const input = document.getElementById("set-import-file") as HTMLInputElement;
    const file = new File(['{"providers": {}}'], "settings.json", { type: "application/json" });
    Object.defineProperty(input, "files", { configurable: true, value: [file] });
    input.dispatchEvent(new Event("change"));
  }

  it("import sends no If-Match", async () => {
    const router = await bootPage('"e0"');
    const reload = vi.fn();
    vi.stubGlobal("location", { ...location, reload });
    router.imports.push(json({}, 200));
    chooseImportFile();
    await vi.waitFor(() => expect(reload).toHaveBeenCalledTimes(1), FAST);
    const posts = router.records.filter((x) => x.method === "POST" && x.url === "/api/settings/import");
    expect(posts).toHaveLength(1);
    expect(posts[0].headers.get("if-match")).toBeNull();
  });

  it("import is not queued behind a pending conditional write", async () => {
    const router = await bootPage('"e0"');
    const reload = vi.fn();
    vi.stubGlobal("location", { ...location, reload });
    const never = deferred<Response>();
    router.puts.push(never);
    router.imports.push(json({}, 200));
    toggleOf("openai").click();
    await flush3();
    expect(putRecords(router)).toHaveLength(1);

    chooseImportFile();
    const posts = () => router.records.filter((x) => x.method === "POST" && x.url === "/api/settings/import");
    await vi.waitFor(() => expect(posts()).toHaveLength(1), FAST);
    expect(toggleOf("openai").getAttribute("aria-busy")).toBe("true");
    expect(posts()[0].headers.get("if-match")).toBeNull();
    expect(putRecords(router)).toHaveLength(1);
  });

  it("success without ETag keeps the previous revision", async () => {
    const router = await bootPage('"e0"');
    router.puts.push(json(providerBody("ollama"), 200));
    saveOf("ollama").click();
    await vi.waitFor(() => expect(resultOf("ollama").dataset.state).toBe("ok"), FAST);
    expect(resultOf("ollama").textContent).toBe("已保存");

    router.puts.push(json(providerBody("openai"), 200, '"t1"'));
    toggleOf("openai").click();
    await vi.waitFor(() => expect(putRecords(router)).toHaveLength(2), FAST);
    expect(putRecords(router)[1].headers.get("if-match")).toBe('"e0"');
  });

  it.each([
    ["ollama save", "/api/settings/providers/ollama"],
    ["prefs save", "/api/settings"],
  ])("page-wide queue serializes writes across cards (third write = %s)", async (third, thirdUrl) => {
    const router = await bootPage('"e0"');
    const openai = deferred<Response>();
    const gemini = deferred<Response>();
    const last = deferred<Response>();
    router.puts.push(openai, gemini, last);

    toggleOf("openai").click();
    toggleOf("gemini").click();
    if (third === "ollama save") {
      type(modelOf("ollama"), "m-typed");
      saveOf("ollama").click();
    } else {
      type(ragChunks(), "9");
      prefsSave().click();
    }
    await flush3();
    expect(putRecords(router)).toHaveLength(1); // check point A

    openai.resolve(json(providerBody("openai"), 200, '"t1"'));
    await vi.waitFor(() => expect(putRecords(router)).toHaveLength(2), FAST);
    await flush3();
    expect(putRecords(router)).toHaveLength(2); // check point B

    gemini.resolve(json(providerBody("gemini"), 200, '"t2"'));
    await vi.waitFor(() => expect(putRecords(router)).toHaveLength(3), FAST);
    last.resolve(json(third === "prefs save" ? {} : providerBody("ollama"), 200, '"t3"'));

    await idle(toggleOf("openai"));
    await idle(toggleOf("gemini"));
    await idle(third === "prefs save" ? prefsSave() : saveOf("ollama"));
    await flush3();

    expect(putRecords(router).map((x) => x.url)).toEqual([
      "/api/settings/providers/openai",
      "/api/settings/providers/gemini",
      thirdUrl,
    ]);
    expect(ifMatches(router)).toEqual(['"e0"', '"t1"', '"t2"']);
    for (const node of document.querySelectorAll<HTMLElement>('[data-testid="set-provider-result"]')) {
      expect(node.dataset.state).not.toBe("error");
    }
    expect(prefsResult().getAttribute("role")).not.toBe("alert");
    expect(toggleOf("openai").getAttribute("aria-checked")).toBe("true");
    expect(toggleOf("gemini").getAttribute("aria-checked")).toBe("true");
    expect(toggleOf("openai").hasAttribute("aria-busy")).toBe(false);
    expect(toggleOf("gemini").hasAttribute("aria-busy")).toBe(false);
  });

  it.each(["409", "500", "network"] as const)(
    "a failed head write does not stall queued writes (openai outcome = %s)",
    async (outcome) => {
      const router = await bootPage('"e0"');
      const openai = deferred<Response>();
      const gemini = deferred<Response>();
      router.puts.push(openai, gemini);

      toggleOf("openai").click();
      toggleOf("gemini").click();
      await flush3();
      expect(putRecords(router)).toHaveLength(1);

      if (outcome === "409") {
        openai.resolve(new Response('{"detail":"conflict"}', { status: 409, headers: { ETag: '"bad-1"' } }));
      } else if (outcome === "500") {
        openai.resolve(new Response('{"detail":"boom"}', { status: 500, headers: { ETag: '"bad-1"' } }));
      } else {
        openai.reject(new TypeError("Failed to fetch"));
      }

      await vi.waitFor(() => expect(putRecords(router)).toHaveLength(2), FAST);
      gemini.resolve(json(providerBody("gemini"), 200, '"t2"'));
      await idle(toggleOf("gemini"));

      router.puts.push(json(providerBody("ollama"), 200, '"t3"'));
      type(modelOf("ollama"), "m-typed");
      saveOf("ollama").click();
      await vi.waitFor(() => expect(putRecords(router)).toHaveLength(3), FAST);
      await idle(saveOf("ollama"));
      await idle(toggleOf("openai"));

      expect(ifMatches(router)).toEqual(['"e0"', '"e0"', '"t2"']);
      for (const value of ifMatches(router)) expect(String(value).startsWith('"bad-')).toBe(false);
      expect(putRecords(router)).toHaveLength(3);

      expect(toggleOf("openai").getAttribute("aria-checked")).toBe("false");
      expect(toggleOf("openai").hasAttribute("aria-busy")).toBe(false);
      expect(resultOf("openai").dataset.state).toBe("error");
      const text = resultOf("openai").textContent ?? "";
      expect(text.startsWith("开关未保存：")).toBe(true);
      if (outcome === "network") expect(text).toBe("开关未保存：Failed to fetch");

      expect(toggleOf("gemini").getAttribute("aria-checked")).toBe("true");
      expect(toggleOf("gemini").hasAttribute("aria-busy")).toBe(false);
      expect(resultOf("gemini").dataset.state).not.toBe("error");
    },
  );
});
