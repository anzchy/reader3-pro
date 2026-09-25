// Vite entry for the library page (013 WI-9; the page itself since WI-13, replacing
// static/library.js, library-search.js and library-chat.js). The static structure lives in
// library.html; this module wires every control.
//
// Rules the page keeps (WI-13 acceptance):
// * filters only toggle `hidden`; they never remove a card or row (the frozen baseline counts
//   nodes). Selection state (`is-selected`) lands only on `.book-card` / `.book-row`, never on
//   a status pill.
// * status pills come from the shared state table (`renderStatusPill`), six states, one
//   literal testid per (view, state), with the book id as the discriminator
// * create collection and the S2 rebuild are single-flight (aria-busy while in flight)
// * the S2 banner carries its own text in its own live region; lib-live-region only
//   announces outcomes, and it announces them before the banner goes away
// * drawers (<= 1279px insights, <= 767px sidebar) report aria-expanded, move focus in on
//   open and back to their toggle on close, and close on Esc
import "@shared/theme";
import "./index.css";

import { markBooted } from "@shared/boot";
import { normalizeIndexStatus, type IndexState } from "@shared/status-meta";
import { showToast } from "@shared/toast";

import { mountDegradeBanner } from "../components/degrade-banner";
import { bindModal } from "../components/modal";
import { createSkeleton } from "../components/skeleton";
import { initLibraryChat } from "./chat";
import { initLibrarySearch } from "./search";
import { renderStatusPill, startIndexButton } from "./status";
import { mountThemeToggle } from "./theme-toggle";

// ---------------------------------------------------------------------------
// constants and state
// ---------------------------------------------------------------------------
const BULK_INDEX_KEY = "reader3.library.bulkIndexingActive";
const VIEW_MODE_KEY = "reader3.library.viewMode";
const COLLAPSED_KEY = "reader3.library.rightPanelCollapsed";
const STATUS_TIMEOUT_MS = 5000;
const INDEX_TIMEOUT_MS = 300000;

// Static testid (ADR-0014): the S2 banner's one action.
const S2_TESTID = {
  reindex: "lib-degrade-s2-reindex",
};

type ViewMode = "grid" | "list";
type Tab = "dashboard" | "chat" | "search";

interface StatusPayload {
  status?: string;
  stale?: boolean;
  chunk_count?: number | null;
}

interface Collection {
  id: string;
  name: string;
  book_ids: string[];
}

const state = {
  scope: "all",
  tab: "dashboard" as Tab,
  view: "grid" as ViewMode,
  selectMode: false,
  selected: new Set<string>(),
  titleFilter: "",
  indexing: false,
  statuses: new Map<string, IndexState>(),
  inFlight: new Set<string>(),
  collections: [] as Collection[],
  collectionBooks: new Map<string, Set<string>>(),
};

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------
function qs<T extends Element = HTMLElement>(sel: string, root: ParentNode = document): T | null {
  return root.querySelector<T>(sel as never) as T | null;
}

function qsa<T extends Element = HTMLElement>(sel: string, root: ParentNode = document): T[] {
  return Array.from(root.querySelectorAll(sel)) as T[];
}

function byId<T extends HTMLElement = HTMLElement>(id: string): T | null {
  return document.getElementById(id) as T | null;
}

function safeStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function store(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // storage unavailable: the preference lasts for this page view only
  }
}

function load(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

const cards = (): HTMLElement[] => qsa(".book-card[data-book-id]");
const rows = (): HTMLElement[] => qsa(".book-row[data-book-id]");
const bookElements = (): HTMLElement[] => [...cards(), ...rows()];
const bookIdOf = (el: Element): string => el.getAttribute("data-book-id") || "";
const titleOf = (id: string): string => qs(`.book-card[data-book-id="${CSS.escape(id)}"] .lib-card-title`)?.textContent || id;

function cardAndRow(bookId: string): HTMLElement[] {
  const esc = CSS.escape(bookId);
  return qsa(`.book-card[data-book-id="${esc}"], .book-row[data-book-id="${esc}"]`);
}

function announce(message: string): void {
  const live = byId("aria-live");
  if (live) live.textContent = message;
}

function errText(e: unknown, fallback: string): string {
  return e instanceof Error && e.message ? e.message : fallback;
}

async function fetchWithTimeout(url: string, opts: RequestInit, ms: number): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, { ...opts, signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}

async function apiJson<T>(url: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(url, opts);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (data.detail) detail = String(data.detail);
    } catch {
      // body was not JSON: keep the status line
    }
    throw new Error(detail);
  }
  return (res.status === 204 ? null : await res.json()) as T;
}

const postJson = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

// ---------------------------------------------------------------------------
// filters, scope, view, sort
// ---------------------------------------------------------------------------
function matchesScope(el: HTMLElement): boolean {
  if (state.scope === "all") return true;
  if (state.scope.startsWith("format:")) return (el.dataset.format || "") === state.scope.slice(7);
  if (state.scope.startsWith("collection:")) {
    return state.collectionBooks.get(state.scope.slice(11))?.has(bookIdOf(el)) ?? false;
  }
  return true;
}

function applyFilters(): void {
  const term = state.titleFilter.toLowerCase().trim();
  for (const el of bookElements()) {
    el.hidden = !(matchesScope(el) && (!term || (el.dataset.title || "").includes(term)));
  }
  const all = cards();
  const filterEmpty = byId("lib-filter-empty");
  if (filterEmpty) filterEmpty.hidden = !(all.length > 0 && all.every((c) => c.hidden));
}

function syncScopeButtons(): void {
  for (const btn of qsa("[data-scope]")) {
    const active = btn.dataset.scope === state.scope;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-pressed", String(active));
  }
}

function setScope(next: string): void {
  if (!next || next === state.scope) return;
  state.scope = next;
  syncScopeButtons();
  applyFilters();
  clearSelection();
  if (state.tab === "dashboard") void refreshStats(false);
}

function setView(mode: ViewMode, persist: boolean): void {
  state.view = mode;
  const grid = byId("library-grid-view");
  const list = byId("library-list-view");
  if (grid) grid.hidden = mode !== "grid";
  if (list) list.hidden = mode !== "list";
  byId("view-grid-btn")?.setAttribute("aria-pressed", String(mode === "grid"));
  byId("view-list-btn")?.setAttribute("aria-pressed", String(mode === "list"));
  if (persist) store(VIEW_MODE_KEY, mode);
}

function sortAtoZ(): void {
  const shelf = byId("library-grid-view");
  const tbody = qs("#library-list-view tbody");
  if (!shelf || !tbody) return;
  const order = cards()
    .map((c) => ({ id: bookIdOf(c), title: c.dataset.title || "" }))
    .sort((a, b) => a.title.localeCompare(b.title));
  for (const { id } of order) {
    const [card, row] = [qs(`.book-card[data-book-id="${CSS.escape(id)}"]`), qs(`.book-row[data-book-id="${CSS.escape(id)}"]`)];
    if (card) shelf.append(card);
    if (row) tbody.append(row);
  }
  announce("Sorted A to Z.");
}

// ---------------------------------------------------------------------------
// selection and bulk actions
// ---------------------------------------------------------------------------
function syncSelection(bookId: string): void {
  const selected = state.selected.has(bookId);
  for (const el of cardAndRow(bookId)) {
    const box = qs<HTMLInputElement>(".select-checkbox", el);
    if (box) box.checked = selected;
    el.classList.toggle("is-selected", selected);
  }
}

function updateSelectionUi(): void {
  const count = byId("selected-count");
  if (count && !state.indexing) count.textContent = `${state.selected.size} selected`;
  const none = state.selected.size === 0;
  const set = (id: string, disabled: boolean): void => {
    const btn = byId<HTMLButtonElement>(id);
    if (btn) btn.disabled = disabled;
  };
  set("index-selected-btn", none || state.indexing);
  set("select-all-btn", state.indexing);
  set("clear-selection-btn", state.indexing);
  set("add-to-collection-btn", state.indexing || none || state.collections.length === 0);
}

function clearSelection(): void {
  const ids = [...state.selected];
  state.selected.clear();
  ids.forEach(syncSelection);
  updateSelectionUi();
}

function selectAllVisible(): void {
  for (const el of state.view === "list" ? rows() : cards()) {
    if (el.hidden) continue;
    const id = bookIdOf(el);
    if (!id) continue;
    state.selected.add(id);
    syncSelection(id);
  }
  updateSelectionUi();
}

function setSelectMode(on: boolean): void {
  state.selectMode = on;
  document.body.classList.toggle("select-mode", on);
  byId("select-toggle-btn")?.setAttribute("aria-pressed", String(on));
  const bar = byId("selection-group");
  if (bar) bar.hidden = !on;
  if (!on) clearSelection();
}

function initSelection(): void {
  byId("select-toggle-btn")?.addEventListener("click", () => setSelectMode(!state.selectMode));
  byId("select-all-btn")?.addEventListener("click", selectAllVisible);
  byId("clear-selection-btn")?.addEventListener("click", clearSelection);
  byId("index-selected-btn")?.addEventListener("click", () => void bulkIndexSelected());
  byId("add-to-collection-btn")?.addEventListener("click", (e) => openAddToCollection(e.currentTarget as HTMLElement));

  for (const el of bookElements()) {
    const box = qs<HTMLInputElement>(".select-checkbox", el);
    const id = bookIdOf(el);
    if (!box || !id) continue;
    box.addEventListener("click", (e) => e.stopPropagation());
    box.addEventListener("change", () => {
      if (box.checked) state.selected.add(id);
      else state.selected.delete(id);
      syncSelection(id);
      updateSelectionUi();
    });
    el.addEventListener("click", (e) => {
      if (!state.selectMode) return;
      if ((e.target as Element | null)?.closest(".lib-start-index")) return;
      e.preventDefault();
      box.checked = !box.checked;
      box.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }
  // Space activates the card link too (a link natively answers only Enter).
  for (const link of qsa<HTMLAnchorElement>(".book-link")) {
    link.addEventListener("keydown", (e) => {
      if (e.key !== " ") return;
      e.preventDefault();
      link.click();
    });
  }
  updateSelectionUi();
}

// ---------------------------------------------------------------------------
// index status
// ---------------------------------------------------------------------------
function setStatus(bookId: string, payload: StatusPayload | null): void {
  const st = payload ? normalizeIndexStatus(payload) : "unknown";
  state.statuses.set(bookId, st);
  const cc = payload?.chunk_count;
  const chunks = st === "indexed" && typeof cc === "number" ? cc : null;
  for (const target of cardAndRow(bookId)) {
    const isRow = target.classList.contains("book-row");
    const pill = qs(".status-pill", target);
    if (pill) renderStatusPill(pill, bookId, st, isRow ? "row" : "grid");
    const chunkPill = qs(".chunk-pill", target);
    if (chunkPill) {
      chunkPill.hidden = chunks === null;
      chunkPill.textContent = chunks === null ? "" : `${chunks} chunks`;
    }
    const cell = qs('[data-role="chunk-count"]', target);
    if (cell) cell.textContent = chunks === null ? "—" : String(chunks);
    if (isRow) renderStartButton(target, bookId, st);
  }
}

function renderStartButton(row: HTMLElement, bookId: string, st: IndexState): void {
  const cell = qs(".lib-cell-status", row);
  if (!cell) return;
  qs(".lib-start-index", cell)?.remove();
  const btn = startIndexButton(st, titleOf(bookId));
  if (!btn) return;
  btn.classList.add("lib-mini-btn");
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (btn.disabled || state.indexing) return;
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    void indexOne(bookId, false).then((err) => announce(err ? `索引失败：${err}` : `已索引「${titleOf(bookId)}」。`));
  });
  cell.append(btn);
}

function setLoading(bookId: string): void {
  for (const target of cardAndRow(bookId)) {
    const pill = qs(".status-pill", target);
    if (!pill) continue;
    pill.removeAttribute("data-testid");
    pill.removeAttribute("data-book-id");
    pill.dataset.status = "loading";
    const sr = document.createElement("span");
    sr.className = "sr-only";
    sr.textContent = "加载中";
    pill.replaceChildren(createSkeleton(), sr);
  }
}

async function fetchStatus(bookId: string): Promise<void> {
  if (!bookId || state.inFlight.has(bookId)) return;
  state.inFlight.add(bookId);
  setLoading(bookId);
  try {
    const res = await fetchWithTimeout(`/api/index/${encodeURIComponent(bookId)}/status`, {}, STATUS_TIMEOUT_MS);
    setStatus(bookId, res.ok ? ((await res.json()) as StatusPayload) : null);
  } catch {
    setStatus(bookId, null);
  } finally {
    state.inFlight.delete(bookId);
  }
}

async function fetchAllStatuses(): Promise<void> {
  const ids = cards().map(bookIdOf).filter(Boolean);
  for (let i = 0; i < ids.length; i += 20) {
    const batch = ids.slice(i, i + 20);
    let next = 0;
    const worker = async (): Promise<void> => {
      while (next < batch.length) await fetchStatus(batch[next++]);
    };
    await Promise.all([worker(), worker(), worker(), worker()]);
  }
  syncStaleBanner();
}

/** POST one index request; returns an error message, or null on success. */
async function indexOne(bookId: string, force: boolean): Promise<string | null> {
  setStatus(bookId, { status: "indexing" });
  try {
    const res = await fetchWithTimeout(`/api/index/${encodeURIComponent(bookId)}`, postJson({ force_reindex: force }), INDEX_TIMEOUT_MS);
    const data = (await res.json().catch(() => ({}))) as StatusPayload & { detail?: string };
    if (!res.ok) {
      setStatus(bookId, { status: "error" });
      return data.detail ? String(data.detail) : `HTTP ${res.status}`;
    }
    setStatus(bookId, { status: "indexed", ...data });
    return null;
  } catch (e) {
    setStatus(bookId, { status: "error" });
    return errText(e, "Unknown error");
  }
}

let errorsModal: ReturnType<typeof bindModal> | null = null;

function showErrors(errors: Array<{ book_id: string; detail: string }>): void {
  const summary = byId("index-errors-summary");
  if (!summary || !errorsModal) return;
  const list = document.createElement("ul");
  for (const err of errors) {
    const li = document.createElement("li");
    li.textContent = `${err.book_id}: ${err.detail}`;
    list.append(li);
  }
  summary.replaceChildren(list);
  errorsModal.open(null);
}

async function bulkIndexSelected(): Promise<void> {
  if (state.indexing) return;
  const ids = [...state.selected];
  if (ids.length === 0) return;
  state.indexing = true;
  updateSelectionUi();
  store(BULK_INDEX_KEY, "true");
  const notice = byId("indexing-interrupted");
  if (notice) notice.hidden = true;
  announce(`Indexing ${ids.length} book(s).`);
  const count = byId("selected-count");
  const errors: Array<{ book_id: string; detail: string }> = [];
  for (let i = 0; i < ids.length; i++) {
    if (count) count.textContent = `Indexing ${i + 1}/${ids.length}…`;
    const err = await indexOne(ids[i], false);
    if (err) errors.push({ book_id: ids[i], detail: err });
  }
  state.indexing = false;
  store(BULK_INDEX_KEY, null);
  updateSelectionUi();
  syncStaleBanner();
  if (errors.length) showErrors(errors);
  announce(errors.length ? "Indexing finished with errors." : "Indexing finished.");
}

// ---------------------------------------------------------------------------
// DEG-S2: stale indexes -> warn banner at the top of the search panel
// ---------------------------------------------------------------------------
let s2Banner: HTMLElement | null = null;

function staleIds(): string[] {
  return [...state.statuses].filter(([, st]) => st === "stale").map(([id]) => id);
}

function syncStaleBanner(): void {
  const stale = staleIds();
  if (stale.length === 0) {
    s2Banner?.remove();
    s2Banner = null;
    return;
  }
  const slot = byId("lib-search-degrade");
  if (!slot || (s2Banner && s2Banner.isConnected)) return;

  const title = document.createElement("strong");
  title.className = "lib-degrade-title";
  title.textContent = "索引已过期，结果可能不全";
  const copy = document.createElement("span");
  copy.textContent = `${stale.length} 本书的语义索引与当前模型不符，重建后恢复。`;

  const reindex = document.createElement("button");
  reindex.type = "button";
  reindex.className = "r3-btn lib-btn";
  reindex.dataset.testid = S2_TESTID.reindex;
  reindex.textContent = "重建索引";
  let busy = false;
  reindex.addEventListener("click", () => {
    // One indexing slot for the page: a running bulk index holds it, and this rebuild takes it,
    // so neither can start while the other runs (the bulk controls read state.indexing).
    if (busy || state.indexing) return;
    busy = true;
    state.indexing = true;
    updateSelectionUi();
    reindex.setAttribute("aria-busy", "true");
    void (async () => {
      const targets = staleIds();
      const failed: string[] = [];
      try {
        for (const id of targets) if (await indexOne(id, true)) failed.push(id);
      } finally {
        busy = false;
        state.indexing = false;
        updateSelectionUi();
        reindex.removeAttribute("aria-busy");
      }
      if (failed.length) {
        announce(`重建失败：${failed.length} 本书的索引未能重建。`);
        return;
      }
      // announce first, then drop the banner: the outcome must outlive its trigger
      announce(`已重建 ${targets.length} 本书的索引。`);
      s2Banner?.remove();
      s2Banner = null;
      void refreshStats(false);
    })();
  });

  s2Banner = mountDegradeBanner(slot, { variant: "lib-s2", body: [title, copy], actions: [reindex], dismissible: true });
}

// ---------------------------------------------------------------------------
// right panel: tabs, stats, collapse; drawers
// ---------------------------------------------------------------------------
const TABS: readonly Tab[] = ["dashboard", "chat", "search"];

function setTab(tab: Tab, focus = false): void {
  state.tab = tab;
  for (const name of TABS) {
    const btn = byId(`lib-tab-${name}`);
    const panel = byId(`${name}-tab`);
    const active = name === tab;
    if (panel) panel.hidden = !active;
    if (!btn) continue;
    btn.setAttribute("aria-selected", String(active));
    btn.tabIndex = active ? 0 : -1;
    btn.classList.toggle("is-active", active);
    if (active && focus) btn.focus();
  }
  if (tab === "dashboard") void refreshStats(false);
}

function initTabs(): void {
  const bar = byId("right-tabbar");
  bar?.addEventListener("click", (e) => {
    const tab = (e.target as Element | null)?.closest<HTMLElement>("[data-tab]")?.dataset.tab as Tab | undefined;
    if (tab && TABS.includes(tab)) setTab(tab);
  });
  bar?.addEventListener("keydown", (e) => {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step && e.key !== "Home" && e.key !== "End") return;
    e.preventDefault();
    const i = TABS.indexOf(state.tab);
    const next = e.key === "Home" ? 0 : e.key === "End" ? TABS.length - 1 : (i + step + TABS.length) % TABS.length;
    setTab(TABS[next], true);
  });
}

async function refreshStats(fresh: boolean): Promise<void> {
  if (state.tab !== "dashboard") return;
  const btn = byId<HTMLButtonElement>("refresh-stats-btn");
  const stateEl = byId("stats-state");
  if (btn) btn.disabled = true;
  if (stateEl) stateEl.textContent = "Loading…";
  try {
    const url = `/api/library/stats?scope=${encodeURIComponent(state.scope)}${fresh ? "&fresh=true" : ""}`;
    const s = await apiJson<Record<string, unknown>>(url);
    const total = Number(s.books_total ?? 0);
    const indexed = Number(s.books_indexed ?? 0);
    const pct = Number(s.indexed_percent ?? 0);
    const text = (id: string, value: string): void => {
      const el = byId(id);
      if (el) el.textContent = value;
    };
    text("stats-books-total", String(total));
    text("stats-books-indexed", String(indexed));
    text("stats-indexed-percent", total ? `${pct}% indexed` : "—");
    text("stats-sections-total", String(Number(s.sections_total ?? 0)));
    text("stats-chunks-total", String(Number(s.chunks_total ?? 0)));
    const bar = byId<HTMLProgressElement>("stats-bar");
    if (bar) bar.value = Math.max(0, Math.min(100, pct));
    text(
      "stats-bar-label",
      total === 0 ? "No books in this scope." : pct >= 100 ? "All books in this scope are indexed." : `Indexed ${indexed}/${total} (${pct}%)`,
    );
    if (stateEl) stateEl.textContent = total === 0 ? "No books in this scope." : "";
  } catch (e) {
    if (stateEl) stateEl.textContent = errText(e, "Failed to load stats.");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function initCollapse(): void {
  const toggle = byId("right-collapse-toggle");
  const shell = byId("library-layout");
  if (!toggle || !shell) return;
  const apply = (collapsed: boolean, persist: boolean): void => {
    shell.classList.toggle("is-collapsed", collapsed);
    toggle.setAttribute("aria-expanded", String(!collapsed));
    const label = collapsed ? "Show right panel" : "Hide right panel";
    toggle.setAttribute("aria-label", label);
    toggle.title = label;
    toggle.textContent = collapsed ? "‹" : "›";
    if (persist) store(COLLAPSED_KEY, String(collapsed));
  };
  apply(load(COLLAPSED_KEY) === "true", false);
  toggle.addEventListener("click", () => apply(!shell.classList.contains("is-collapsed"), true));
}

interface Drawer {
  toggle: HTMLElement;
  panel: HTMLElement;
  focusIn: () => HTMLElement | null;
}

function initDrawers(): void {
  const scrim = byId("lib-scrim");
  const make = (toggleId: string, panelId: string, focusIn: () => HTMLElement | null): Drawer | null => {
    const toggle = byId(toggleId);
    const panel = byId(panelId);
    return toggle && panel ? { toggle, panel, focusIn } : null;
  };
  const drawers = [
    make("lib-menu-toggle", "lib-sidebar", () => qs<HTMLElement>("#lib-sidebar .is-active") || byId("collections-create")),
    make("lib-insights-toggle", "lib-insights", () => byId(`lib-tab-${state.tab}`)),
  ].filter((d): d is Drawer => d !== null);

  const isOpen = (d: Drawer): boolean => d.panel.classList.contains("is-open");
  const close = (d: Drawer, restoreFocus: boolean): void => {
    if (!isOpen(d)) return;
    d.panel.classList.remove("is-open");
    d.toggle.setAttribute("aria-expanded", "false");
    if (scrim) scrim.hidden = !drawers.some(isOpen);
    if (restoreFocus) d.toggle.focus();
  };
  const open = (d: Drawer): void => {
    for (const other of drawers) if (other !== d) close(other, false);
    d.panel.classList.add("is-open");
    d.toggle.setAttribute("aria-expanded", "true");
    if (scrim) scrim.hidden = false;
    d.focusIn()?.focus();
  };

  for (const d of drawers) d.toggle.addEventListener("click", () => (isOpen(d) ? close(d, true) : open(d)));
  scrim?.addEventListener("click", () => drawers.forEach((d) => close(d, true)));
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || document.querySelector("dialog[open]")) return;
    for (const d of drawers) if (isOpen(d)) close(d, true);
  });
}

// ---------------------------------------------------------------------------
// collections
// ---------------------------------------------------------------------------
function presentIds(): Set<string> {
  return new Set(cards().map(bookIdOf).filter(Boolean));
}

function collectionRow(c: Collection, present: Set<string>): HTMLElement {
  const row = document.createElement("div");
  row.className = "lib-collection";
  row.dataset.testid = "lib-sidebar-collection";
  row.dataset.collectionId = c.id;

  const inside = c.book_ids.filter((id) => present.has(id));
  const missing = c.book_ids.length - inside.length;

  const main = document.createElement("button");
  main.type = "button";
  main.className = "lib-scope-btn collection-btn";
  main.dataset.scope = `collection:${c.id}`;
  const name = document.createElement("span");
  name.className = "lib-scope-label";
  name.textContent = c.name;
  const badge = document.createElement("span");
  badge.className = "lib-badge";
  badge.textContent = String(inside.length);
  main.append(name, badge);

  const actions = document.createElement("div");
  actions.className = "lib-collection-actions";
  if (missing) {
    const clean = document.createElement("button");
    clean.type = "button";
    clean.className = "lib-mini-btn";
    clean.dataset.action = "cleanup";
    clean.title = "Remove missing books";
    clean.textContent = `Clean (${missing})`;
    actions.append(clean);
  }
  const del = document.createElement("button");
  del.type = "button";
  del.className = "lib-mini-btn lib-mini-btn--danger";
  del.dataset.action = "delete";
  del.textContent = "Delete";
  actions.append(del);

  row.append(main, actions);
  return row;
}

async function loadCollections(): Promise<void> {
  const errEl = byId("collections-error");
  try {
    const data = await apiJson<{ collections?: Collection[] }>("/api/collections");
    state.collections = (Array.isArray(data?.collections) ? data.collections : []).map((c) => ({
      id: String(c.id),
      name: String(c.name || ""),
      book_ids: Array.isArray(c.book_ids) ? c.book_ids.map(String) : [],
    }));
    if (errEl) {
      errEl.textContent = "";
      errEl.hidden = true;
    }
  } catch (e) {
    state.collections = [];
    if (errEl) {
      errEl.textContent = errText(e, "Failed to load collections.");
      errEl.hidden = false;
    }
  }
  const present = presentIds();
  state.collectionBooks = new Map(state.collections.map((c) => [c.id, new Set(c.book_ids.filter((id) => present.has(id)))]));
  const empty = byId("collections-empty-message");
  if (empty) empty.hidden = state.collections.length !== 0;
  const list = byId("collections-list");
  if (list) {
    const sorted = [...state.collections].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
    list.replaceChildren(...sorted.map((c) => collectionRow(c, present)));
  }
  syncScopeButtons();
  applyFilters();
  updateSelectionUi();
}

async function updateCollectionBooks(id: string, body: { add?: string[]; remove?: string[] }): Promise<void> {
  await apiJson(`/api/collections/${encodeURIComponent(id)}/books`, postJson(body));
  await loadCollections();
}

function initCollections(): void {
  const list = byId("collections-list");
  list?.addEventListener("click", (e) => {
    const target = e.target as Element | null;
    const action = target?.closest<HTMLElement>("button[data-action]");
    if (!action) {
      const scope = target?.closest<HTMLElement>("button[data-scope]")?.dataset.scope;
      if (scope) setScope(scope);
      return;
    }
    const id = action.closest<HTMLElement>("[data-collection-id]")?.dataset.collectionId;
    if (!id) return;
    void (async () => {
      try {
        if (action.dataset.action === "delete") {
          if (!window.confirm("Delete this collection?")) return;
          await apiJson(`/api/collections/${encodeURIComponent(id)}`, { method: "DELETE" });
          if (state.scope === `collection:${id}`) setScope("all");
          await loadCollections();
        } else if (action.dataset.action === "cleanup") {
          const present = presentIds();
          const missing = state.collections.find((c) => c.id === id)?.book_ids.filter((b) => !present.has(b)) ?? [];
          if (missing.length) await updateCollectionBooks(id, { remove: missing });
        }
      } catch (err) {
        showToast(errText(err, "Collection update failed."), { testId: "lib-toast", tone: "error" });
      }
    })();
  });

  for (const btn of qsa(".filter-btn[data-scope]")) {
    btn.addEventListener("click", () => setScope(btn.dataset.scope || "all"));
  }

  // create collection: single-flight through the modal's primary
  const dialog = byId<HTMLDialogElement>("create-collection-modal");
  const nameInput = byId<HTMLInputElement>("create-collection-name");
  const close = byId("create-collection-close");
  const cancel = byId("create-collection-cancel");
  const primary = byId<HTMLButtonElement>("create-collection-submit");
  const createBtn = byId("collections-create");
  if (!dialog || !nameInput || !close || !cancel || !primary || !createBtn) return;
  const modal = bindModal({ dialog, close, cancel, primary }, async () => {
    const name = nameInput.value.trim();
    try {
      await apiJson("/api/collections", postJson({ name }));
      showToast(`已创建收藏夹「${name}」`, { testId: "lib-toast", tone: "success" });
      await loadCollections();
    } catch (e) {
      showToast(errText(e, "Failed to create collection."), { testId: "lib-toast", tone: "error" });
    }
  });
  createBtn.addEventListener("click", () => {
    nameInput.value = "";
    modal.open(createBtn);
    nameInput.focus();
  });
}

function openAddToCollection(trigger: HTMLElement): void {
  const dialog = byId<HTMLDialogElement>("add-to-collection-modal");
  const picker = byId("collections-picker");
  const errEl = byId("add-to-collection-error");
  if (!dialog || !picker || dialog.open) return;
  if (errEl) errEl.hidden = true;
  let busy = false;
  picker.replaceChildren(
    ...state.collections.map((c) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "lib-btn lib-picker-btn";
      btn.textContent = c.name;
      btn.addEventListener("click", async () => {
        if (busy) return;
        busy = true;
        btn.setAttribute("aria-busy", "true");
        try {
          await updateCollectionBooks(c.id, { add: [...state.selected] });
          dialog.close();
          showToast(`已加入「${c.name}」`, { testId: "lib-toast", tone: "success" });
        } catch (e) {
          if (errEl) {
            errEl.textContent = errText(e, "Failed to update collection.");
            errEl.hidden = false;
          }
        } finally {
          busy = false;
          btn.removeAttribute("aria-busy");
        }
      });
      return btn;
    }),
  );
  dialog.addEventListener("close", () => (trigger.isConnected ? trigger.focus() : undefined), { once: true });
  dialog.showModal();
  qs<HTMLElement>("button", picker)?.focus();
}

function initAddToCollectionDialog(): void {
  const dialog = byId<HTMLDialogElement>("add-to-collection-modal");
  if (!dialog) return;
  for (const id of ["add-to-collection-close", "add-to-collection-cancel"]) {
    byId(id)?.addEventListener("click", () => dialog.close());
  }
}

// ---------------------------------------------------------------------------
// boot
// ---------------------------------------------------------------------------
function bindInfoModal(dialogId: string, closeId: string, okId: string): ReturnType<typeof bindModal> | null {
  const dialog = byId<HTMLDialogElement>(dialogId);
  const close = byId(closeId);
  const ok = byId<HTMLButtonElement>(okId);
  return dialog && close && ok ? bindModal({ dialog, close, cancel: close, primary: ok }, () => undefined) : null;
}

function init(): void {
  const addBooks = bindInfoModal("add-books-modal", "add-books-close", "add-books-ok");
  const addBtn = byId("add-books-btn");
  addBtn?.addEventListener("click", () => addBooks?.open(addBtn));
  errorsModal = bindInfoModal("index-errors-modal", "index-errors-close", "index-errors-ok");

  const theme = byId<HTMLButtonElement>("lib-theme-toggle");
  if (theme) mountThemeToggle(theme, document.documentElement, safeStorage());

  initTabs();
  initCollapse();
  initDrawers();
  initCollections();
  initAddToCollectionDialog();
  initSelection();

  const filter = byId<HTMLInputElement>("title-filter");
  filter?.addEventListener("input", () => {
    state.titleFilter = filter.value;
    applyFilters();
  });
  const stored = load(VIEW_MODE_KEY);
  setView(stored === "list" ? "list" : "grid", false);
  byId("view-grid-btn")?.addEventListener("click", () => setView("grid", true));
  byId("view-list-btn")?.addEventListener("click", () => setView("list", true));
  byId("sort-btn")?.addEventListener("click", sortAtoZ);
  byId("refresh-stats-btn")?.addEventListener("click", () => void refreshStats(true));

  if (load(BULK_INDEX_KEY) === "true") {
    const notice = byId("indexing-interrupted");
    if (notice) notice.hidden = false;
    announce("Indexing was interrupted.");
  }
  window.addEventListener("beforeunload", (e) => {
    if (state.indexing) e.preventDefault();
  });

  applyFilters();
  setTab(state.tab);
  void loadCollections();
  void fetchAllStatuses();
  initLibrarySearch();
  initLibraryChat();
  markBooted("library");
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
else init();
