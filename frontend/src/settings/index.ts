// Vite entry for the settings page (013 WI-9; the page itself since WI-12, replacing
// static/settings.js). The static structure lives in settings.html; this module fills the
// provider cards and wires every control.
//
// Rules the page keeps (WI-12 acceptance):
// * no native confirm / alert / prompt: destructive actions go through per-action <dialog>s
//   (components/modal.ts), outcomes are written to result lines (no toast, ruling D9)
// * save / test / refresh are single-flight (aria-busy while in flight); the provider switch
//   serialises its PUTs so every flip is persisted in order
// * every write conditional on the settings revision (provider switch, provider save, preferences
//   save) sends If-Match from the page revision and runs through one page-wide queue; a 409 says
//   the settings changed elsewhere, keeps the typed values and is not retried (018 WI-3). Import
//   stays unconditional and outside the queue.
// * API keys are write-only: the key field is a password input, cleared after a save, and
//   never filled from the server (which never returns keys)
// * the appearance section is the chrome axis only (data-theme), never data-reading-theme
// * deferred server half (ruling D11): bulk reindex says so on the page and sends nothing. The
//   library JSON export is live since 018 WI-6: one GET /api/library/export (default body, no
//   conversations), single-flight, failures shown in the export result line
import "@shared/theme";
import "./index.css";

import { markBooted } from "@shared/boot";

import { bindModal } from "../components/modal";
import { applyScheme, clampInt, readScheme, SCHEMES, type Scheme } from "./prefs";

// ---------------------------------------------------------------------------
// constants
// ---------------------------------------------------------------------------
const PROVIDER_LABELS: Readonly<Record<string, string>> = {
  anthropic: "Anthropic Claude",
  openai: "OpenAI",
  gemini: "Google Gemini",
  ollama: "Ollama（本地）",
  openrouter: "OpenRouter",
};
const KEYED = new Set(["anthropic", "openai", "gemini", "openrouter"]);
const SCHEME_LABELS: Readonly<Record<Scheme, string>> = { system: "跟随系统", light: "浅色", dark: "深色" };

// Bounded testid tables (ADR-0014): every name is a literal, none is built by interpolation.
type DataAction = "reindex" | "conversations" | "cache";
const SCHEME_TESTIDS: Readonly<Record<Scheme, string>> = {
  system: "set-appearance-scheme-system",
  light: "set-appearance-scheme-light",
  dark: "set-appearance-scheme-dark",
};
const MODAL_TESTIDS: Readonly<
  Record<DataAction, { trigger: string; root: string; close: string; cancel: string; primary: string }>
> = {
  reindex: {
    trigger: "set-data-reindex",
    root: "set-modal-reindex",
    close: "set-modal-reindex-close",
    cancel: "set-modal-reindex-cancel",
    primary: "set-modal-reindex-primary",
  },
  conversations: {
    trigger: "set-data-conversations",
    root: "set-modal-conversations",
    close: "set-modal-conversations-close",
    cancel: "set-modal-conversations-cancel",
    primary: "set-modal-conversations-primary",
  },
  cache: {
    trigger: "set-data-cache",
    root: "set-modal-cache",
    close: "set-modal-cache-close",
    cancel: "set-modal-cache-cancel",
    primary: "set-modal-cache-primary",
  },
};

const RAG_CHUNKS = { min: 1, max: 20, fallback: 6 } as const;
const RAG_CONTEXT = { min: 1000, max: 32000, fallback: 8000 } as const;

/** Longest the first render waits for the Ollama probe (status + model list). */
const PROBE_CAP_MS = 3000;

const IDB_NAME = "reader3_ai_assistant";
const IDB_VERSION = 1;
const EXPORT_FILE = "reader3_ai_settings.export.json";
const LIBRARY_EXPORT_FILE = "reader3-library.json";

// ---------------------------------------------------------------------------
// API shapes (web/routers/settings.py)
// ---------------------------------------------------------------------------
interface ProviderConfig {
  name: string;
  api_key_configured?: boolean;
  base_url?: string;
  model_name?: string;
  enabled?: boolean;
}

interface SettingsResponse {
  default_provider?: string;
  providers?: ProviderConfig[];
  preferences?: Record<string, unknown>;
}

interface TestResponse {
  success?: boolean;
  message?: string;
  details?: { model?: string; latency_ms?: number };
}

class HttpError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** Fetch JSON; the caller's headers are kept, Content-Type is added when there is a body. */
async function requestJsonWithMeta<T>(url: string, init?: RequestInit): Promise<{ data: T; etag: string | null }> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const res = await fetch(url, { ...init, headers });
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data && typeof data === "object" && "detail" in data ? String((data as { detail: unknown }).detail) : "";
    throw new HttpError(`HTTP ${res.status}${detail ? ` · ${detail}` : ""}`, res.status);
  }
  return { data: data as T, etag: res.headers.get("ETag") || null };
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  return (await requestJsonWithMeta<T>(url, init)).data;
}

const CONFLICT_TEXT = "设置已在别处更改，请刷新页面后再试";

function errorText(err: unknown): string {
  if (err instanceof HttpError && err.status === 409) return CONFLICT_TEXT;
  return err instanceof Error ? err.message : String(err);
}

// ---------------------------------------------------------------------------
// settings revision and the page-wide write queue (018 WI-3, debt #51)
// ---------------------------------------------------------------------------
// One revision for the page, because the server's ETag covers the whole settings file. It is set
// from the boot GET and replaced only by the ETag of a successful conditional write; a success
// without an ETag keeps it, and a failure never moves it.
let revision: string | null = null;

// Every conditional write (each card's toggle and save, the preferences save) runs through this
// one chain, so at most one is in flight and each reads `revision` when its turn comes. A job's
// failure is swallowed here so it can never stall the jobs queued behind it.
let writeQueue: Promise<void> = Promise.resolve();

function enqueueWrite(job: () => Promise<void>): Promise<void> {
  const run = writeQueue.then(job).catch(() => undefined);
  writeQueue = run;
  return run;
}

/** A write conditional on the page revision. Call only from inside an `enqueueWrite` job. */
async function conditionalWrite<T>(url: string, init: RequestInit): Promise<T> {
  const headers = new Headers(init.headers);
  if (revision) headers.set("If-Match", revision);
  const { data, etag } = await requestJsonWithMeta<T>(url, { ...init, headers });
  if (etag) revision = etag;
  return data;
}

// ---------------------------------------------------------------------------
// small DOM helpers
// ---------------------------------------------------------------------------
function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`settings.html is missing #${id}`);
  return el as T;
}

/** The one element carrying `testid` (a literal from the tables below; no selector is built). */
function byTestId<T extends HTMLElement>(testid: string): T {
  for (const node of document.querySelectorAll<HTMLElement>("[data-testid]")) {
    if (node.dataset.testid === testid) return node as T;
  }
  throw new Error(`settings.html is missing testid ${testid}`);
}

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Record<string, string> = {},
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}

type ResultState = "ok" | "error" | "";

function setResult(node: HTMLElement, state: ResultState, text: string): void {
  node.dataset.state = state;
  node.textContent = text;
}

function setBusy(button: HTMLElement, busy: boolean): void {
  if (busy) button.setAttribute("aria-busy", "true");
  else button.removeAttribute("aria-busy");
}

/** Run `task` unless one is already in flight on `button`; aria-busy marks the flight. */
function singleFlight(button: HTMLElement, task: () => Promise<void>): () => Promise<void> {
  let inFlight = false;
  return async () => {
    if (inFlight) return;
    inFlight = true;
    setBusy(button, true);
    try {
      await task();
    } finally {
      inFlight = false;
      setBusy(button, false);
    }
  };
}

let liveRegion: HTMLElement | null = null;

function announce(message: string): void {
  if (!liveRegion) return;
  liveRegion.textContent = "";
  window.setTimeout(() => {
    if (liveRegion) liveRegion.textContent = message;
  }, 0);
}

function safeStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// provider cards
// ---------------------------------------------------------------------------
interface Card {
  name: string;
  toggle: HTMLButtonElement;
  model: HTMLInputElement;
  url: HTMLInputElement;
  key: HTMLInputElement | null;
  result: HTMLElement;
  sub: HTMLElement;
  models: HTMLDataListElement | null;
  loadedUrl: string;
}

const cards: Card[] = [];
let guide: HTMLElement | null = null;

function updateGuide(): void {
  if (!guide) return;
  guide.hidden = cards.some((c) => c.toggle.getAttribute("aria-checked") === "true");
}

function keySubtitle(name: string, configured: boolean): string {
  if (!KEYED.has(name)) return "本地运行 · 无需 API 密钥";
  return configured ? "已配置 API 密钥（不会回传到浏览器）" : "未配置 API 密钥";
}

function renderCard(cfg: ProviderConfig): { root: HTMLElement; card: Card } {
  const name = cfg.name;
  const label = PROVIDER_LABELS[name] ?? name;
  const p = { "data-provider": name };

  const root = el("article", { class: "set-card", "data-testid": "set-provider-card", ...p });

  const head = el("header", { class: "set-card-head" });
  const title = el("div", { class: "set-card-title" });
  title.append(el("h3", { class: "set-card-name" }, label));
  const sub = el("p", { class: "set-card-sub" }, keySubtitle(name, Boolean(cfg.api_key_configured)));
  title.append(sub);
  const toggle = el("button", {
    type: "button",
    class: "set-switch",
    role: "switch",
    "aria-checked": cfg.enabled ? "true" : "false",
    "aria-label": `启用 ${label}`,
    "data-testid": "set-provider-toggle",
    ...p,
  });
  head.append(title, toggle);

  const grid = el("div", { class: "set-grid" });
  const modelField = el("label", { class: "set-field" }, "模型");
  const model = el("input", {
    class: "set-input",
    type: "text",
    autocomplete: "off",
    spellcheck: "false",
    "data-testid": "set-provider-model",
    ...p,
  });
  model.value = cfg.model_name ?? "";
  modelField.append(model);
  let models: HTMLDataListElement | null = null;
  if (name === "ollama") {
    const listId = "set-ollama-models";
    model.setAttribute("list", listId);
    models = el("datalist", { id: listId });
    modelField.append(models);
  }
  const urlField = el("label", { class: "set-field" }, "服务地址");
  const url = el("input", {
    class: "set-input",
    type: "url",
    autocomplete: "off",
    spellcheck: "false",
    "data-testid": "set-provider-url",
    ...p,
  });
  url.value = cfg.base_url ?? "";
  urlField.append(url);
  grid.append(modelField, urlField);

  let key: HTMLInputElement | null = null;
  if (KEYED.has(name)) {
    const keyField = el("label", { class: "set-field" }, "API 密钥");
    key = el("input", {
      class: "set-input",
      type: "password",
      autocomplete: "off",
      spellcheck: "false",
      placeholder: cfg.api_key_configured ? "已保存（不显示）；输入新密钥可替换" : "粘贴 API 密钥",
      "data-testid": "set-provider-key",
      ...p,
    });
    keyField.append(key);
    grid.append(keyField);
  }

  const actions = el("div", { class: "set-actions" });
  const save = el("button", { type: "button", class: "set-btn set-btn-primary", "data-testid": "set-provider-save", ...p }, "保存");
  const test = el("button", { type: "button", class: "set-btn", "data-testid": "set-provider-test", ...p }, "测试连接");
  actions.append(save, test);
  let refresh: HTMLButtonElement | null = null;
  if (name === "ollama") {
    refresh = el("button", { type: "button", class: "set-btn", "data-testid": "set-provider-refresh-models" }, "刷新模型");
    actions.append(refresh);
  }

  const result = el("p", {
    class: "set-result",
    role: "status",
    "aria-live": "polite",
    "data-state": "",
    "data-testid": "set-provider-result",
    ...p,
  });

  root.append(head, grid, actions, result);
  if (name === "ollama") {
    const hint = el("p", { class: "set-hint", "data-testid": "set-provider-ollama-hint" });
    hint.append(
      "Ollama 需要在本机运行：先执行 ",
      el("code", {}, "ollama serve"),
      "，再用 ",
      el("code", {}, "ollama pull llama3"),
      " 拉取一个模型。",
    );
    root.append(hint);
  }

  const card: Card = { name, toggle, model, url, key, result, sub, models, loadedUrl: url.value };
  wireToggle(card, label);
  save.addEventListener("click", singleFlight(save, () => enqueueWrite(() => saveProvider(card, label))));
  test.addEventListener("click", singleFlight(test, () => testProvider(card)));
  if (refresh) {
    const button = refresh;
    button.addEventListener("click", singleFlight(button, () => refreshModels(card)));
  }
  return { root, card };
}

/** Every flip is persisted, in order (page-wide write queue); aria-busy covers this card's flips. */
function wireToggle(card: Card, label: string): void {
  const { toggle } = card;
  let confirmed = toggle.getAttribute("aria-checked") === "true";
  let pending = 0;

  toggle.addEventListener("click", () => {
    const next = toggle.getAttribute("aria-checked") !== "true";
    toggle.setAttribute("aria-checked", next ? "true" : "false");
    updateGuide();
    announce(`${label} ${next ? "已启用" : "已停用"}`);
    pending += 1;
    setBusy(toggle, true);
    void enqueueWrite(async () => {
      try {
        await conditionalWrite(`/api/settings/providers/${encodeURIComponent(card.name)}`, {
          method: "PUT",
          body: JSON.stringify({ enabled: next }),
        });
        confirmed = next;
      } catch (err) {
        setResult(card.result, "error", `开关未保存：${errorText(err)}`);
      } finally {
        pending -= 1;
        if (pending === 0) {
          if (toggle.getAttribute("aria-checked") !== (confirmed ? "true" : "false")) {
            toggle.setAttribute("aria-checked", confirmed ? "true" : "false");
            updateGuide();
          }
          setBusy(toggle, false);
        }
      }
    });
  });
}

async function saveProvider(card: Card, label: string): Promise<void> {
  const body: Record<string, string> = {
    model_name: card.model.value.trim(),
    base_url: card.url.value.trim(),
  };
  const typedKey = card.key ? card.key.value.trim() : "";
  if (typedKey) body.api_key = typedKey;
  try {
    const saved = await conditionalWrite<ProviderConfig>(`/api/settings/providers/${encodeURIComponent(card.name)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    if (card.key) {
      card.key.value = "";
      if (saved?.api_key_configured) card.key.placeholder = "已保存（不显示）；输入新密钥可替换";
    }
    card.sub.textContent = keySubtitle(card.name, Boolean(saved?.api_key_configured));
    card.loadedUrl = card.url.value.trim();
    setResult(card.result, "ok", "已保存");
    announce(`${label} 已保存`);
  } catch (err) {
    setResult(card.result, "error", `保存没有成功：${errorText(err)}`);
  }
}

async function testProvider(card: Card): Promise<void> {
  const body: Record<string, string> = { model_name: card.model.value.trim() };
  const typedKey = card.key ? card.key.value.trim() : "";
  if (typedKey) body.api_key = typedKey;
  // A base URL other than the stored one needs its own key (server rule, finding web/C2).
  const url = card.url.value.trim();
  if (url !== card.loadedUrl) body.base_url = url;
  setResult(card.result, "", "正在测试连接…");
  try {
    const res = await requestJson<TestResponse>(
      `/api/settings/providers/${encodeURIComponent(card.name)}/test`,
      { method: "POST", body: JSON.stringify(body) },
    );
    if (res?.success) {
      const model = res.details?.model ? ` · ${res.details.model}` : "";
      const latency = typeof res.details?.latency_ms === "number" ? ` · ${res.details.latency_ms} ms` : "";
      setResult(card.result, "ok", `连接成功${model}${latency}`);
    } else {
      setResult(card.result, "error", `连接失败：${res?.message || "未知原因"}`);
    }
  } catch (err) {
    setResult(card.result, "error", `连接失败：${errorText(err)}`);
  }
}

// Model list for Ollama: loaded once when the local server is running, and on demand. One
// request at a time; a failure keeps the value and the options already known.
let modelsInFlight: Promise<void> | null = null;

function loadModels(card: Card, report: boolean): Promise<void> {
  if (modelsInFlight) return modelsInFlight;
  modelsInFlight = (async () => {
    try {
      const data = await requestJson<{ models?: Array<{ name?: string }> }>("/api/ollama/models");
      const names = (data?.models ?? []).map((m) => String(m?.name ?? "")).filter(Boolean);
      const list = card.models;
      if (list) list.replaceChildren(...names.map((n) => el("option", { value: n })));
      if (report) setResult(card.result, "ok", `已刷新：${names.length} 个模型`);
    } catch (err) {
      if (report) setResult(card.result, "error", `刷新模型失败：${errorText(err)}`);
    } finally {
      modelsInFlight = null;
    }
  })();
  return modelsInFlight;
}

function refreshModels(card: Card): Promise<void> {
  return loadModels(card, true);
}

async function probeOllama(card: Card): Promise<void> {
  try {
    const status = await requestJson<{ running?: boolean }>("/api/ollama/status");
    if (status?.running) await loadModels(card, false);
  } catch {
    // the status probe is advisory; the refresh button reports errors
  }
}

// ---------------------------------------------------------------------------
// AI preferences
// ---------------------------------------------------------------------------
function wirePreferences(settings: SettingsResponse): void {
  const prefs = settings.preferences ?? {};
  const provider = byId<HTMLSelectElement>("set-default-provider");
  provider.replaceChildren(
    ...Object.entries(PROVIDER_LABELS).map(([value, label]) => el("option", { value }, label)),
  );
  provider.value = settings.default_provider ?? "anthropic";

  const streaming = byId<HTMLInputElement>("set-pref-streaming");
  const timestamps = byId<HTMLInputElement>("set-pref-timestamps");
  const suggest = byId<HTMLInputElement>("set-pref-suggest");
  streaming.checked = prefs.streaming_enabled !== false;
  timestamps.checked = prefs.show_timestamps !== false;
  suggest.checked = prefs.auto_suggest_questions !== false;

  const chunks = byTestId<HTMLInputElement>("set-rag-chunks");
  const context = byTestId<HTMLInputElement>("set-rag-context");
  const clampChunks = () => clampInt(chunks.value, RAG_CHUNKS.min, RAG_CHUNKS.max, RAG_CHUNKS.fallback);
  const clampContext = () => clampInt(context.value, RAG_CONTEXT.min, RAG_CONTEXT.max, RAG_CONTEXT.fallback);
  chunks.value = String(clampInt(String(prefs.rag_chunks ?? ""), RAG_CHUNKS.min, RAG_CHUNKS.max, RAG_CHUNKS.fallback));
  context.value = String(
    clampInt(String(prefs.rag_context_window ?? ""), RAG_CONTEXT.min, RAG_CONTEXT.max, RAG_CONTEXT.fallback),
  );
  chunks.addEventListener("blur", () => {
    chunks.value = String(clampChunks());
  });
  context.addEventListener("blur", () => {
    context.value = String(clampContext());
  });

  const save = byId<HTMLButtonElement>("set-save-prefs");
  const result = byId<HTMLElement>("set-prefs-result");
  save.addEventListener(
    "click",
    singleFlight(save, () => enqueueWrite(async () => {
      const ragChunks = clampChunks();
      const ragContext = clampContext();
      chunks.value = String(ragChunks);
      context.value = String(ragContext);
      try {
        await conditionalWrite("/api/settings", {
          method: "PUT",
          body: JSON.stringify({
            default_provider: provider.value,
            preferences: {
              streaming_enabled: streaming.checked,
              show_timestamps: timestamps.checked,
              auto_suggest_questions: suggest.checked,
              rag_chunks: ragChunks,
              rag_context_window: ragContext,
            },
          }),
        });
        result.setAttribute("role", "status");
        setResult(result, "ok", "偏好已保存");
      } catch (err) {
        result.setAttribute("role", "alert");
        setResult(result, "error", `保存失败：${errorText(err)}。输入的内容仍在，稍后可以再试。`);
      }
    })),
  );
}

// ---------------------------------------------------------------------------
// appearance: the chrome colour scheme, a radiogroup with roving tabindex
// ---------------------------------------------------------------------------
function wireAppearance(): void {
  const radios = new Map<Scheme, HTMLButtonElement>(
    SCHEMES.map((s) => [s, byTestId<HTMLButtonElement>(SCHEME_TESTIDS[s])]),
  );
  const render = (current: Scheme) => {
    for (const [scheme, radio] of radios) {
      radio.setAttribute("aria-checked", scheme === current ? "true" : "false");
      radio.tabIndex = scheme === current ? 0 : -1;
    }
  };
  const select = (scheme: Scheme, focus: boolean) => {
    applyScheme(scheme, document.documentElement, safeStorage());
    render(scheme);
    if (focus) radios.get(scheme)?.focus();
    announce(`界面明暗：${SCHEME_LABELS[scheme]}`);
  };
  render(readScheme(safeStorage()));

  for (const [scheme, radio] of radios) {
    radio.addEventListener("click", () => select(scheme, false));
    radio.addEventListener("keydown", (event) => {
      const i = SCHEMES.indexOf(scheme);
      let next: Scheme | null = null;
      if (event.key === "ArrowRight" || event.key === "ArrowDown") next = SCHEMES[(i + 1) % SCHEMES.length];
      else if (event.key === "ArrowLeft" || event.key === "ArrowUp")
        next = SCHEMES[(i - 1 + SCHEMES.length) % SCHEMES.length];
      else if (event.key === "Home") next = SCHEMES[0];
      else if (event.key === "End") next = SCHEMES[SCHEMES.length - 1];
      if (!next) return;
      event.preventDefault();
      select(next, true);
    });
  }
}

// ---------------------------------------------------------------------------
// data: per-action confirm dialogs
// ---------------------------------------------------------------------------
function clearStore(store: "conversations" | "summaries"): Promise<void> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, IDB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains("conversations")) {
        const s = db.createObjectStore("conversations", { keyPath: "id" });
        s.createIndex("book_uuid", "book_uuid", { unique: false });
        s.createIndex("book_uuid_provider", ["book_uuid", "provider"], { unique: false });
      }
      if (!db.objectStoreNames.contains("summaries")) {
        const s = db.createObjectStore("summaries", { keyPath: "cache_key" });
        s.createIndex("book_uuid", "book_uuid", { unique: false });
      }
    };
    req.onerror = () => reject(req.error ?? new Error("IndexedDB open failed"));
    req.onsuccess = () => {
      const db = req.result;
      const tx = db.transaction(store, "readwrite");
      tx.objectStore(store).clear();
      tx.oncomplete = () => {
        db.close();
        resolve();
      };
      tx.onerror = () => {
        db.close();
        reject(tx.error ?? new Error("IndexedDB clear failed"));
      };
    };
  });
}

function wireDataActions(): void {
  const result = byId<HTMLElement>("set-data-result");
  const actions: Record<"reindex" | "conversations" | "cache", () => Promise<void>> = {
    reindex: async () => {
      setResult(result, "", "批量重建索引暂不支持：请在终端对每本书运行 uv run reader3 --index <书目录>。");
    },
    conversations: async () => {
      try {
        await clearStore("conversations");
        setResult(result, "ok", "已清除本浏览器中的全部 AI 对话。");
      } catch (err) {
        setResult(result, "error", `对话没有删掉：${errorText(err)}`);
      }
    },
    cache: async () => {
      try {
        await clearStore("summaries");
        setResult(result, "ok", "已清除本浏览器中的 AI 摘要缓存。");
      } catch (err) {
        setResult(result, "error", `缓存没有清掉：${errorText(err)}`);
      }
    },
  };
  for (const [action, run] of Object.entries(actions)) {
    const t = MODAL_TESTIDS[action as DataAction];
    const trigger = byTestId<HTMLButtonElement>(t.trigger);
    const modal = bindModal(
      {
        dialog: byTestId<HTMLDialogElement>(t.root),
        close: byTestId<HTMLButtonElement>(t.close),
        cancel: byTestId<HTMLButtonElement>(t.cancel),
        primary: byTestId<HTMLButtonElement>(t.primary),
      },
      run,
    );
    trigger.addEventListener("click", () => modal.open(trigger));
  }
}

// ---------------------------------------------------------------------------
// export / import
// ---------------------------------------------------------------------------
function download(text: string, filename: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const a = el("a", { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * 018 audit 20261007 #8 / #18 (FX37-8): a 2xx is only a library export when its body is the
 * `{books: [...]}` envelope. A proxy page, an empty body or any other JSON shape is an error, so
 * nothing that is not an export is ever saved as one.
 */
function isLibraryExport(data: unknown): data is { books: unknown[] } {
  return (
    typeof data === "object" &&
    data !== null &&
    !Array.isArray(data) &&
    Array.isArray((data as { books?: unknown }).books)
  );
}

function wireExport(): void {
  const result = byId<HTMLElement>("set-export-result");
  // 018 WI-6: the default export (no ?include). `disabled` is set before the first await, so a
  // second click in the same tick is already refused; clicks on a disabled button never fire.
  const exportLibrary = byTestId<HTMLButtonElement>("set-export-json");
  exportLibrary.addEventListener("click", async () => {
    if (exportLibrary.disabled) return;
    exportLibrary.disabled = true;
    try {
      const data = await requestJson<unknown>("/api/library/export");
      if (!isLibraryExport(data)) throw new Error("响应不是有效的书库导出（缺少 books 列表）");
      download(JSON.stringify(data, null, 2), LIBRARY_EXPORT_FILE);
      setResult(result, "ok", "书库已导出。");
    } catch (err) {
      setResult(result, "error", `导出书库失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      exportLibrary.disabled = false;
    }
  });

  const exportSettings = byTestId<HTMLButtonElement>("set-export-settings");
  exportSettings.addEventListener("click", async () => {
    if (exportSettings.disabled) return;
    exportSettings.disabled = true;
    try {
      const data = await requestJson<unknown>("/api/settings/export");
      download(JSON.stringify(data, null, 2), EXPORT_FILE);
      setResult(result, "ok", "设置已导出（不含 API 密钥）。");
    } catch (err) {
      setResult(result, "error", `导出设置失败：${errorText(err)}`);
    } finally {
      exportSettings.disabled = false;
    }
  });

  const importButton = byId<HTMLButtonElement>("set-import-settings");
  const file = byId<HTMLInputElement>("set-import-file");
  importButton.addEventListener("click", () => file.click());
  file.addEventListener("change", async () => {
    const chosen = file.files?.[0];
    file.value = "";
    if (!chosen) return;
    importButton.disabled = true;
    try {
      const payload: unknown = JSON.parse(await chosen.text());
      await requestJson("/api/settings/import", { method: "POST", body: JSON.stringify(payload) });
      window.location.reload();
    } catch (err) {
      setResult(result, "error", `导入设置失败：${errorText(err)}`);
      importButton.disabled = false;
    }
  });
}

// ---------------------------------------------------------------------------
// boot
// ---------------------------------------------------------------------------
async function boot(): Promise<void> {
  liveRegion = byTestId<HTMLElement>("set-live-region");
  guide = byId<HTMLElement>("set-provider-guide");
  wireAppearance();
  wireDataActions();
  wireExport();

  const container = byId<HTMLElement>("set-providers");
  let settings: SettingsResponse;
  try {
    const boot = await requestJsonWithMeta<SettingsResponse>("/api/settings");
    settings = boot.data;
    if (boot.etag) revision = boot.etag;
  } catch (err) {
    const failed = el("p", { class: "set-result", role: "alert", "data-state": "error" });
    failed.textContent = `读取设置失败：${errorText(err)}`;
    container.replaceChildren(failed);
    markBooted("settings");
    return;
  }
  wirePreferences(settings);
  const rendered = (settings.providers ?? []).map(renderCard);
  cards.push(...rendered.map((r) => r.card));
  // The Ollama model list is part of the first render: the cards appear once the probe has
  // answered (capped, so an unresponsive local server cannot hold the page back), and the
  // page's own start-up traffic is over by the time the cards are there.
  const ollama = cards.find((c) => c.name === "ollama");
  if (ollama) {
    await Promise.race([probeOllama(ollama), new Promise((r) => window.setTimeout(r, PROBE_CAP_MS))]);
  }
  container.replaceChildren(...rendered.map((r) => r.root));
  updateGuide();
  // The boot marker goes on last, as on the library page: once it is there, the provider
  // cards (or the error line above) are in the DOM.
  markBooted("settings");
}

void boot();
