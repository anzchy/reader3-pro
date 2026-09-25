// 013 final review L4 (RV-5): the settings page stamps its boot marker (data-r3-page) only
// once boot() has rendered the provider cards, as the library page does at the end of init().
// A marker present before the cards tells a waiting test (or anything else) that the page is
// ready while the provider list is still an empty container.
//
// The DOM is the minimum the settings entry wires (the ids and testids it looks up in
// settings.html). It is built here, not read from the template: the Vitest suite runs from a
// copy of frontend/ alone (tests/unit/test_vitest_host.py), so a spec may not reach into src/.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The theme entry imports the build-time virtual stylesheet (a Vite plugin, not in the Vitest
// host); it carries no behaviour this test needs.
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

// The entry is imported through a non-literal specifier so tsc does not type-resolve it: a
// literal import here would make `tsc --noEmit` the first to report a deleted settings entry,
// and by this file's path, pre-empting the build's own "settings/index.ts" diagnostic that
// tests/integration/test_frontend_build.py::test_missing_entry_module_fails_build pins.
const SETTINGS_ENTRY = "../../src/settings/index.ts";
const bootSettings = (): Promise<unknown> => import(/* @vite-ignore */ SETTINGS_ENTRY);

const marker = (): string | null => document.documentElement.getAttribute("data-r3-page");
const cardCount = (): number => document.querySelectorAll('[data-testid="set-provider-card"]').length;

function deferred<T>(): { promise: Promise<T>; resolve: (v: T) => void } {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

async function settle(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await new Promise((r) => setTimeout(r, 0));
}

const SETTINGS = {
  default_provider: "openai",
  providers: [
    { name: "openai", enabled: true, api_key_configured: false, base_url: "", model_name: "m" },
    { name: "anthropic", enabled: false, api_key_configured: false, base_url: "", model_name: "m" },
  ],
  preferences: {},
};

beforeEach(() => {
  vi.resetModules();
  document.documentElement.removeAttribute("data-r3-page");
  mountSettingsBody();
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.replaceChildren();
  document.documentElement.removeAttribute("data-r3-page");
});

describe("settings boot marker", () => {
  it("is absent while /api/settings is pending and appears only once the cards exist", async () => {
    const settings = deferred<Response>();
    let cardsWhenMarked = -1;
    const observer = new MutationObserver(() => {
      if (cardsWhenMarked < 0 && marker() !== null) cardsWhenMarked = cardCount();
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-r3-page"] });
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        url === "/api/settings" ? settings.promise : Promise.resolve(new Response("{}", { status: 404 })),
      ),
    );

    await bootSettings();
    await settle();
    expect(cardCount()).toBe(0);
    expect(marker()).toBeNull();

    settings.resolve(new Response(JSON.stringify(SETTINGS), { status: 200 }));
    await vi.waitFor(() => expect(cardCount()).toBe(2));
    await vi.waitFor(() => expect(marker()).toBe("settings"));
    observer.disconnect();
    expect(cardsWhenMarked).toBe(2);
  });

  it("still boots (after the error line is rendered) when /api/settings fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: "boom" }), { status: 500 }))),
    );
    await bootSettings();
    await vi.waitFor(() => expect(marker()).toBe("settings"));
    expect(document.querySelector('#set-providers [role="alert"]')?.textContent).toContain("读取设置失败");
  });
});
