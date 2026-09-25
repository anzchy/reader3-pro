// Library-wide search panel (013 WI-13; replaces static/library-search.js).
//
// Behaviour kept from the legacy module: a 300 ms debounce, so one settled query sends one
// request; the last result is restored from sessionStorage; hits are grouped by book, and each
// group has a "Show more" button. Unlike the legacy module, visibility is driven by the
// `hidden` attribute and classes, never by inline styles, and escaping goes through the one
// shared helper.
import { escapeHtml } from "@shared/escape";

const SESSION_KEY = "reader3.search.library";
const DEBOUNCE_MS = 300;

// Bounded testid table (ADR-0014): literal names, the per-book discriminator is data-book-id.
const SEARCH_TESTID = {
  hit: "lib-search-hit",
  showMore: "lib-search-show-more",
};

export interface SearchHit {
  chapter_order?: number | string;
  chapter_title?: string;
  context_before?: string;
  context_after?: string;
  match_text?: string;
  match_explanation?: string;
  occurrence_index?: number | string;
  mode?: string;
}

interface SearchPayload {
  status_message?: string;
  book_order?: string[];
  grouped_by_book?: Record<string, SearchHit[]>;
  book_metadata?: Record<string, { title?: string; author?: string }>;
  index_status_by_book?: Record<string, string>;
  detail?: string;
}

interface SearchParts {
  input: HTMLInputElement;
  caseBox: HTMLInputElement | null;
  mode: HTMLSelectElement | null;
  sort: HTMLSelectElement | null;
  clear: HTMLButtonElement | null;
  status: HTMLElement;
  panel: HTMLElement;
  results: HTMLElement;
}

function byId<T extends HTMLElement>(id: string): T | null {
  return document.getElementById(id) as T | null;
}

function div(className: string, text?: string): HTMLDivElement {
  const el = document.createElement("div");
  el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

/** Where a hit opens (both path segments percent-encoded): the chapter, plus q / occurrence (occurrence only when numeric) unless it is a semantic hit in semantic mode. */
export function searchHitHref(bookId: string, r: SearchHit, q: string, semanticMode: boolean): string {
  const base = `/read/${encodeURIComponent(bookId)}/${encodeURIComponent(String(r.chapter_order))}`;
  if (semanticMode && r.mode === "semantic") return base;
  const href = `${base}?q=${encodeURIComponent(q)}`;
  // A missing / blank / non-numeric index is omitted, not sent as "NaN" (or "" coerced to 0):
  // the reader already treats an absent `occurrence` as "no occurrence selected".
  const raw = r.occurrence_index;
  const occ = typeof raw === "string" && raw.trim() === "" ? NaN : Number(raw);
  if (raw == null || !Number.isFinite(occ)) return href;
  return `${href}&occurrence=${encodeURIComponent(String(occ))}`;
}

class LibrarySearch {
  private timer: number | undefined;
  private seq = 0;

  constructor(private readonly p: SearchParts) {}

  init(): void {
    this.p.input.addEventListener("input", () => {
      window.clearTimeout(this.timer);
      this.timer = window.setTimeout(() => void this.perform(), DEBOUNCE_MS);
    });
    this.p.caseBox?.addEventListener("change", () => void this.perform());
    this.p.mode?.addEventListener("change", () => void this.perform());
    this.p.sort?.addEventListener("change", () => void this.perform());
    this.p.clear?.addEventListener("click", () => this.clear(true));
    this.restore();
  }

  private modeValue(): string {
    return this.p.mode?.value || "keyword";
  }

  private restore(): void {
    try {
      const raw = sessionStorage.getItem(SESSION_KEY);
      if (!raw) return;
      const data = JSON.parse(raw) as { q?: string; caseSensitive?: boolean; mode?: string; sortBy?: string; payload?: SearchPayload };
      if (data.q) this.p.input.value = data.q;
      if (typeof data.caseSensitive === "boolean" && this.p.caseBox) this.p.caseBox.checked = data.caseSensitive;
      if (data.mode && this.p.mode) this.p.mode.value = data.mode;
      if (data.sortBy && this.p.sort) this.p.sort.value = data.sortBy;
      if (data.payload) this.render(data.payload);
    } catch {
      // a stale or unreadable session entry only costs the restored result
    }
  }

  private persist(payload: SearchPayload, q: string, caseSensitive: boolean, sortBy: string): void {
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({ payload, q, caseSensitive, sortBy, mode: this.modeValue() }));
    } catch {
      // storage unavailable: the result is simply not restored next time
    }
  }

  private clear(clearSession: boolean): void {
    window.clearTimeout(this.timer);
    this.seq += 1;
    this.p.input.value = "";
    this.p.panel.hidden = true;
    this.p.results.replaceChildren();
    this.p.status.textContent = "";
    if (!clearSession) return;
    try {
      sessionStorage.removeItem(SESSION_KEY);
    } catch {
      // nothing to clear
    }
  }

  async perform(maxResultsPerBook = 3): Promise<void> {
    const q = this.p.input.value.trim();
    if (!q) {
      this.clear(false);
      return;
    }
    const caseSensitive = Boolean(this.p.caseBox?.checked);
    const sortBy = this.p.sort?.value || "relevance";
    const seq = ++this.seq;

    this.p.panel.hidden = false;
    this.p.status.textContent = "Searching…";
    this.p.results.replaceChildren();

    const url = new URL("/api/search/library", window.location.origin);
    url.searchParams.set("q", q);
    url.searchParams.set("mode", this.modeValue());
    url.searchParams.set("max_results_per_book", String(maxResultsPerBook));
    url.searchParams.set("max_total_results", "100");
    url.searchParams.set("sort_by", sortBy);
    if (caseSensitive) url.searchParams.set("case_sensitive", "true");

    try {
      const resp = await fetch(url.toString());
      const payload = (await resp.json().catch(() => ({}))) as SearchPayload;
      if (seq !== this.seq) return; // superseded by a newer query or a clear
      if (!resp.ok) {
        this.p.status.textContent = payload.detail || "Search failed";
        return;
      }
      this.render(payload);
      this.persist(payload, q, caseSensitive, sortBy);
    } catch {
      if (seq === this.seq) this.p.status.textContent = "Search failed";
    }
  }

  private indexBadge(bookId: string, st: string): HTMLElement[] {
    const badge = document.createElement("span");
    badge.className = "lib-search-badge";
    badge.dataset.status = st;
    badge.textContent = st === "indexed" ? "Indexed" : st === "not_indexed" ? "Not indexed" : "Index: unknown";
    if (st !== "not_indexed") return [badge];

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "lib-mini-btn";
    btn.textContent = "Index";
    btn.addEventListener("click", async (event) => {
      event.stopPropagation();
      if (btn.disabled) return;
      btn.disabled = true;
      badge.textContent = "Indexing…";
      try {
        const resp = await fetch(`/api/index/${encodeURIComponent(bookId)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ force_reindex: false }),
        });
        const data = (await resp.json().catch(() => ({}))) as { detail?: string; chunk_count?: number };
        if (!resp.ok) {
          badge.textContent = data.detail || "Indexing failed";
          return;
        }
        badge.textContent = `Indexed (${data.chunk_count ?? "?"})`;
        badge.dataset.status = "indexed";
        btn.remove();
      } catch {
        badge.textContent = "Indexing failed";
      } finally {
        btn.disabled = false;
      }
    });
    return [badge, btn];
  }

  private hit(bookId: string, r: SearchHit, q: string): HTMLElement {
    const item = div("lib-search-hit");
    item.dataset.testid = SEARCH_TESTID.hit;
    item.dataset.bookId = bookId;
    item.dataset.section = String(r.chapter_order);
    item.tabIndex = 0;
    item.setAttribute("role", "link");
    if (r.match_explanation) item.title = r.match_explanation;

    const snippet = div("lib-search-snippet");
    snippet.innerHTML =
      `${escapeHtml(r.context_before ?? "")} ` +
      `<mark class="search-match">${escapeHtml(r.match_text ?? "")}</mark>` +
      ` ${escapeHtml(r.context_after ?? "")}`;
    item.append(div("lib-search-chapter", String(r.chapter_title ?? "")), snippet);
    if (r.match_explanation) item.append(div("lib-search-expl", r.match_explanation));

    const go = (): void => {
      window.location.href = searchHitHref(bookId, r, q, this.modeValue() === "semantic");
    };
    item.addEventListener("click", go);
    item.addEventListener("keydown", (event) => {
      if (event.key === "Enter") go();
    });
    return item;
  }

  private render(payload: SearchPayload): void {
    const q = this.p.input.value.trim();
    this.p.panel.hidden = false;
    this.p.status.textContent = payload.status_message || "";
    this.p.results.replaceChildren();

    const order = Array.isArray(payload.book_order) ? payload.book_order : [];
    const grouped = payload.grouped_by_book || {};
    const meta = payload.book_metadata || {};
    const indexStatus = payload.index_status_by_book || {};
    const mode = this.modeValue();

    let foundAny = false;
    for (const bookId of order) {
      const hits = grouped[bookId];
      if (!Array.isArray(hits) || hits.length === 0) continue;
      foundAny = true;

      const group = div("lib-search-group");
      const header = div("lib-search-group-head");
      const left = div("lib-search-group-meta");
      left.append(div("lib-search-book-title", meta[bookId]?.title || bookId), div("lib-search-book-author", meta[bookId]?.author || ""));
      const right = div("lib-search-group-actions");
      if (mode !== "keyword") right.append(...this.indexBadge(bookId, String(indexStatus[bookId] || "unknown")));

      const more = document.createElement("button");
      more.type = "button";
      more.className = "lib-mini-btn";
      more.dataset.testid = SEARCH_TESTID.showMore;
      more.dataset.bookId = bookId;
      more.textContent = "Show more";
      more.addEventListener("click", () => void this.perform(10));
      right.append(more);

      header.append(left, right);
      group.append(header, ...hits.map((r) => this.hit(bookId, r, q)));
      this.p.results.append(group);
    }

    if (!foundAny) this.p.results.append(div("lib-search-empty", `No results found for "${q}"`));
  }
}

export function initLibrarySearch(): void {
  const input = byId<HTMLInputElement>("library-panel-search-input");
  const status = byId<HTMLElement>("library-panel-search-status");
  const panel = byId<HTMLElement>("library-panel-search-panel");
  const results = byId<HTMLElement>("library-panel-search-results");
  if (!input || !status || !panel || !results) return;
  new LibrarySearch({
    input,
    status,
    panel,
    results,
    caseBox: byId<HTMLInputElement>("library-panel-search-case"),
    mode: byId<HTMLSelectElement>("library-panel-search-mode"),
    sort: byId<HTMLSelectElement>("library-panel-search-sort"),
    clear: byId<HTMLButtonElement>("library-panel-search-clear"),
  }).init();
}
