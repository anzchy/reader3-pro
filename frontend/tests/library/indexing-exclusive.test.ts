// 013 final review L5 (RV-6): the S2 banner's 重建索引 and the bulk "index selected" are one
// indexing slot (state.indexing). While either is running the other sends nothing, and the
// bulk control reads disabled; when the running one settles, the other works again.
//
// The page module boots on import, so every test mounts a minimal library DOM, stubs fetch,
// and imports a fresh copy of the module.
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

// The theme entry imports the build-time virtual stylesheet (a Vite plugin, not in the Vitest
// host); it carries no behaviour this test needs.
vi.mock("@shared/theme", () => ({}));

const STALE = "stale_data";
const FRESH = "fresh_data";

function bookCard(id: string): string {
  return `
    <div class="book-card" data-book-id="${id}" data-format="epub">
      <input type="checkbox" class="select-checkbox">
      <span class="lib-card-title">${id}</span>
      <span class="status-pill"></span>
    </div>`;
}

function mount(): void {
  document.body.innerHTML = `
    <div id="aria-live"></div>
    <button type="button" id="select-toggle-btn">Select</button>
    <div id="selection-group" hidden>
      <span id="selected-count"></span>
      <button type="button" id="index-selected-btn">Index selected</button>
    </div>
    <div id="lib-search-degrade"></div>
    ${bookCard(STALE)}
    ${bookCard(FRESH)}`;
}

interface Pending {
  url: string;
  body: { force_reindex?: boolean };
  resolve: () => void;
}

let posts: Pending[] = [];

function stubFetch(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "POST" && /^\/api\/index\/[^/]+$/.test(url)) {
        return new Promise<Response>((resolve) => {
          posts.push({
            url,
            body: JSON.parse(String(init.body ?? "{}")) as { force_reindex?: boolean },
            resolve: () => resolve(new Response(JSON.stringify({ chunk_count: 3 }), { status: 200 })),
          });
        });
      }
      if (url.endsWith(`/${STALE}/status`)) {
        return Promise.resolve(new Response(JSON.stringify({ status: "indexed", stale: true }), { status: 200 }));
      }
      if (url.endsWith("/status")) {
        return Promise.resolve(new Response(JSON.stringify({ status: "not_indexed" }), { status: 200 }));
      }
      if (url === "/api/collections") {
        return Promise.resolve(new Response(JSON.stringify({ collections: [] }), { status: 200 }));
      }
      return Promise.resolve(new Response("{}", { status: 200 }));
    }),
  );
}

const byTestId = (id: string): HTMLElement | null => document.querySelector(`[data-testid="${id}"]`);
const reindexButton = (): HTMLButtonElement => byTestId("lib-degrade-s2-reindex") as HTMLButtonElement;
const indexSelected = (): HTMLButtonElement => document.getElementById("index-selected-btn") as HTMLButtonElement;

async function settle(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await new Promise((r) => setTimeout(r, 0));
}

async function boot(): Promise<void> {
  await import("../../src/library/index");
  await vi.waitFor(() => expect(reindexButton()).not.toBeNull());
}

function selectFresh(): void {
  (document.getElementById("select-toggle-btn") as HTMLButtonElement).click();
  const box = document.querySelector<HTMLInputElement>(`.book-card[data-book-id="${FRESH}"] .select-checkbox`);
  box!.checked = true;
  box!.dispatchEvent(new Event("change", { bubbles: true }));
}

beforeAll(() => {
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & { showModal: () => void };
  proto.showModal ??= function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
});

beforeEach(() => {
  vi.resetModules();
  posts = [];
  sessionStorage.clear();
  localStorage.clear();
  mount();
  stubFetch();
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

describe("one indexing slot for the S2 rebuild and the bulk index", () => {
  it("a bulk index cannot start while the S2 rebuild is running", async () => {
    await boot();
    selectFresh();
    expect(indexSelected().disabled).toBe(false);

    reindexButton().click();
    await vi.waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].body.force_reindex).toBe(true);

    expect(indexSelected().disabled).toBe(true);
    indexSelected().click();
    await settle();
    expect(posts).toHaveLength(1);

    posts[0].resolve();
    await vi.waitFor(() => expect(reindexButton()?.getAttribute("aria-busy") ?? null).toBeNull());
    await settle();
    expect(indexSelected().disabled).toBe(false);
    indexSelected().click();
    await vi.waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[1].url).toBe(`/api/index/${FRESH}`);
  });

  it("the S2 rebuild sends nothing while a bulk index is running", async () => {
    await boot();
    selectFresh();

    indexSelected().click();
    await vi.waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].url).toBe(`/api/index/${FRESH}`);

    reindexButton().click();
    await settle();
    expect(posts).toHaveLength(1);
    expect(reindexButton().getAttribute("aria-busy")).toBeNull();

    posts[0].resolve();
    await vi.waitFor(() => expect(indexSelected().disabled).toBe(false));
    await settle();
    reindexButton().click();
    await vi.waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[1].url).toBe(`/api/index/${STALE}`);
    expect(posts[1].body.force_reindex).toBe(true);
  });
});
