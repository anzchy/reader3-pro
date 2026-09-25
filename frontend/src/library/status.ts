// The library's index-status rendering (013 WI-13; C13.18 / Track-D WI-3 #2-#4).
//
// Testids are written out whole, one per (view, state): the naming lint and the e2e contract
// look for the literal strings, so they are never assembled from parts.
import { statusMeta, type IndexState } from "@shared/status-meta";

export type StatusView = "grid" | "row";

const GRID_TESTID: Readonly<Record<IndexState, string>> = {
  not_indexed: "lib-book-grid-status-not-indexed",
  indexing: "lib-book-grid-status-indexing",
  indexed: "lib-book-grid-status-indexed",
  error: "lib-book-grid-status-error",
  stale: "lib-book-grid-status-stale",
  unknown: "lib-book-grid-status-unknown",
};

const ROW_TESTID: Readonly<Record<IndexState, string>> = {
  not_indexed: "lib-book-row-status-not-indexed",
  indexing: "lib-book-row-status-indexing",
  indexed: "lib-book-row-status-indexed",
  error: "lib-book-row-status-error",
  stale: "lib-book-row-status-stale",
  unknown: "lib-book-row-status-unknown",
};

/** Paint `pill` for `state`: testid, book id, `data-status` (the CSS hook) and the label. */
export function renderStatusPill(pill: HTMLElement, bookId: string, state: IndexState, view: StatusView): void {
  pill.dataset.testid = (view === "grid" ? GRID_TESTID : ROW_TESTID)[state];
  pill.dataset.bookId = bookId;
  pill.dataset.status = state;
  pill.textContent = statusMeta[state].label;
}

/** The per-book 「开始索引」 action, or null when `state` may not start one (statusMeta). */
export function startIndexButton(state: IndexState, title: string): HTMLButtonElement | null {
  if (!statusMeta[state].canStartIndex) return null;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "lib-start-index";
  button.setAttribute("aria-label", `开始索引：${title}`);
  button.textContent = "开始索引";
  return button;
}
