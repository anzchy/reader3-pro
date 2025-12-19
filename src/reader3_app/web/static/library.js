(() => {
  "use strict";

  const BULK_INDEX_STORAGE_KEY = "reader3.library.bulkIndexingActive";

  const state = {
    scope: "all",
    selectMode: false,
    selectedBookIds: new Set(),
    titleFilter: "",
    isIndexing: false,
    statuses: new Map(),
    inFlightStatus: new Set(),
  };

  function qs(sel, root = document) {
    return root.querySelector(sel);
  }

  function qsa(sel, root = document) {
    return Array.from(root.querySelectorAll(sel));
  }

  function getAllBookCards() {
    return qsa(".book-card");
  }

  function getBookIdFromCard(card) {
    return card?.getAttribute("data-book-id") || "";
  }

  function setHidden(el, hidden) {
    if (!el) return;
    if (hidden) el.setAttribute("hidden", "");
    else el.removeAttribute("hidden");
  }

  function safeLower(s) {
    return String(s || "").toLowerCase();
  }

  function matchesScope(card) {
    const fmt = card.getAttribute("data-format") || "";
    if (state.scope === "all") return true;
    if (state.scope.startsWith("format:")) {
      return fmt === state.scope.slice("format:".length);
    }
    return true;
  }

  function matchesTitleFilter(card) {
    const term = safeLower(state.titleFilter).trim();
    if (!term) return true;
    const title = card.getAttribute("data-title") || "";
    return title.includes(term);
  }

  function applyFilters() {
    for (const card of getAllBookCards()) {
      const visible = matchesScope(card) && matchesTitleFilter(card);
      setHidden(card, !visible);
    }
  }

  function setActiveScopeButton() {
    for (const btn of qsa(".filter-btn[data-scope]")) {
      btn.classList.toggle("is-active", btn.getAttribute("data-scope") === state.scope);
    }
  }

  function setSelectMode(enabled) {
    state.selectMode = Boolean(enabled);
    document.body.classList.toggle("select-mode", state.selectMode);
    const selectionGroup = qs("#selection-group");
    setHidden(selectionGroup, !state.selectMode);
    if (!state.selectMode) {
      clearSelection();
    }
  }

  function setBookSelected(card, selected) {
    const checkbox = qs(".select-checkbox", card);
    if (checkbox) checkbox.checked = selected;
    card.classList.toggle("is-selected", selected);
  }

  function updateSelectionUi() {
    const selectedCount = qs("#selected-count");
    if (selectedCount) {
      selectedCount.textContent = `${state.selectedBookIds.size} selected`;
    }
    const indexBtn = qs("#index-selected-btn");
    if (indexBtn) {
      indexBtn.disabled = state.selectedBookIds.size === 0 || state.isIndexing;
    }
    const selectAllBtn = qs("#select-all-btn");
    if (selectAllBtn) {
      selectAllBtn.disabled = state.isIndexing;
    }
    const clearBtn = qs("#clear-selection-btn");
    if (clearBtn) {
      clearBtn.disabled = state.isIndexing;
    }
  }

  function clearSelection() {
    state.selectedBookIds.clear();
    for (const card of getAllBookCards()) {
      setBookSelected(card, false);
    }
    updateSelectionUi();
  }

  function selectAllVisible() {
    for (const card of getAllBookCards()) {
      if (card.hasAttribute("hidden")) continue;
      const id = getBookIdFromCard(card);
      if (!id) continue;
      state.selectedBookIds.add(id);
      setBookSelected(card, true);
    }
    updateSelectionUi();
  }

  function setStatusForBook(bookId, status) {
    state.statuses.set(bookId, status);
    const card = qs(`.book-card[data-book-id="${CSS.escape(bookId)}"]`);
    if (!card) return;
    const pill = qs(".status-pill", card);
    const chunkPill = qs(".chunk-pill", card);

    const normalized = String(status?.status || "unknown");
    if (pill) {
      pill.classList.remove(
        "is-loading",
        "is-indexed",
        "is-not-indexed",
        "is-indexing",
        "is-unknown",
        "is-error",
      );
      if (normalized === "indexed") {
        pill.classList.add("is-indexed");
        pill.textContent = "Indexed";
      } else if (normalized === "not_indexed") {
        pill.classList.add("is-not-indexed");
        pill.textContent = "Not indexed";
      } else if (normalized === "indexing") {
        pill.classList.add("is-indexing");
        pill.textContent = "Indexing…";
      } else if (normalized === "error") {
        pill.classList.add("is-error");
        pill.textContent = "Error";
      } else {
        pill.classList.add("is-unknown");
        pill.textContent = "Unknown";
      }
    }

    if (chunkPill) {
      const cc = status?.chunk_count;
      if (normalized === "indexed" && typeof cc === "number") {
        chunkPill.textContent = `${cc} chunks`;
        setHidden(chunkPill, false);
      } else {
        setHidden(chunkPill, true);
      }
    }
  }

  function setLoadingStatus(bookId) {
    setStatusForBook(bookId, { book_id: bookId, status: "unknown", chunk_count: null });
    const card = qs(`.book-card[data-book-id="${CSS.escape(bookId)}"]`);
    if (!card) return;
    const pill = qs(".status-pill", card);
    if (!pill) return;
    pill.classList.remove("is-indexed", "is-not-indexed", "is-indexing", "is-unknown", "is-error");
    pill.classList.add("is-loading");
    pill.textContent = "Loading…";
  }

  async function fetchWithTimeout(url, opts = {}, timeoutMs = 5000) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(url, { ...opts, signal: controller.signal });
      return res;
    } finally {
      clearTimeout(timeout);
    }
  }

  async function fetchStatus(bookId) {
    if (!bookId || state.inFlightStatus.has(bookId)) return;
    state.inFlightStatus.add(bookId);
    setLoadingStatus(bookId);
    try {
      const res = await fetchWithTimeout(`/api/index/${encodeURIComponent(bookId)}/status`, {}, 5000);
      if (!res.ok) {
        setStatusForBook(bookId, { book_id: bookId, status: "unknown", chunk_count: null });
        return;
      }
      const data = await res.json();
      setStatusForBook(bookId, data);
    } catch {
      setStatusForBook(bookId, { book_id: bookId, status: "unknown", chunk_count: null });
    } finally {
      state.inFlightStatus.delete(bookId);
    }
  }

  function chunkArray(arr, size) {
    const out = [];
    for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
    return out;
  }

  async function runWithConcurrency(items, concurrency, fn) {
    const results = new Array(items.length);
    let idx = 0;
    const workers = new Array(Math.max(1, concurrency)).fill(null).map(async () => {
      while (idx < items.length) {
        const i = idx++;
        results[i] = await fn(items[i]);
      }
    });
    await Promise.all(workers);
    return results;
  }

  async function lazyFetchStatuses() {
    const ids = getAllBookCards().map(getBookIdFromCard).filter(Boolean);
    const batches = chunkArray(ids, 20);
    for (const batch of batches) {
      await runWithConcurrency(batch, 4, (id) => fetchStatus(id));
    }
  }

  function setIndexProgress(text) {
    const el = qs("#selected-count");
    if (!el) return;
    if (!text) {
      el.textContent = `${state.selectedBookIds.size} selected`;
      return;
    }
    el.textContent = text;
  }

  function setInterruptedNoticeVisible(visible) {
    const el = qs("#indexing-interrupted");
    setHidden(el, !visible);
  }

  function attachBeforeUnload() {
    window.addEventListener("beforeunload", (e) => {
      if (!state.isIndexing) return;
      e.preventDefault();
      e.returnValue = "";
    });
  }

  function showErrorsModal(errors) {
    const modal = qs("#index-errors-modal");
    const summary = qs("#index-errors-summary");
    const closeEls = [qs("#index-errors-close"), qs("#index-errors-ok")].filter(Boolean);
    if (!modal || !summary || typeof modal.showModal !== "function") return;

    summary.innerHTML = "";
    const list = document.createElement("ul");
    for (const err of errors) {
      const li = document.createElement("li");
      li.textContent = `${err.book_id}: ${err.detail}`;
      list.appendChild(li);
    }
    summary.appendChild(list);
    modal.showModal();
    closeEls.forEach((el) =>
      el.addEventListener(
        "click",
        () => {
          modal.close();
        },
        { once: true },
      ),
    );
  }

  async function indexBook(bookId) {
    const res = await fetchWithTimeout(
      `/api/index/${encodeURIComponent(bookId)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force_reindex: false }),
      },
      300000,
    );
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        if (data?.detail) detail = String(data.detail);
      } catch {
        // ignore
      }
      return { ok: false, book_id: bookId, detail };
    }
    const data = await res.json();
    return { ok: true, data };
  }

  async function bulkIndexSelected() {
    if (state.isIndexing) return;
    const selected = Array.from(state.selectedBookIds);
    if (selected.length === 0) return;

    state.isIndexing = true;
    updateSelectionUi();
    try {
      localStorage.setItem(BULK_INDEX_STORAGE_KEY, "true");
    } catch {
      // ignore
    }
    setInterruptedNoticeVisible(false);

    const errors = [];
    for (let i = 0; i < selected.length; i++) {
      const bookId = selected[i];
      setIndexProgress(`Indexing ${i + 1}/${selected.length}…`);
      setStatusForBook(bookId, { book_id: bookId, status: "indexing", chunk_count: null });
      try {
        const result = await indexBook(bookId);
        if (result.ok) {
          setStatusForBook(bookId, result.data);
        } else {
          errors.push({ book_id: bookId, detail: result.detail });
          setStatusForBook(bookId, { book_id: bookId, status: "error", chunk_count: null });
        }
      } catch (e) {
        errors.push({ book_id: bookId, detail: String(e || "Unknown error") });
        setStatusForBook(bookId, { book_id: bookId, status: "error", chunk_count: null });
      }
    }

    state.isIndexing = false;
    try {
      localStorage.removeItem(BULK_INDEX_STORAGE_KEY);
    } catch {
      // ignore
    }
    setIndexProgress("");
    updateSelectionUi();
    if (errors.length) showErrorsModal(errors);
  }

  function initTabSwitcher() {
    const switcher = qs(".right-tab-switcher");
    if (!switcher) return;
    switcher.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-tab]");
      if (!btn) return;
      const name = btn.getAttribute("data-tab");
      qsa(".right-tab").forEach((el) => el.classList.toggle("is-active", el.id === `${name}-tab`));
      qsa(".tab-btn").forEach((el) => el.classList.toggle("is-active", el === btn));
    });
  }

  function initAddBooksModal() {
    const addBtn = qs("#add-books-btn");
    const modal = qs("#add-books-modal");
    const closeEls = [qs("#add-books-close"), qs("#add-books-ok")].filter(Boolean);
    if (!addBtn || !modal || typeof modal.showModal !== "function") return;
    addBtn.addEventListener("click", () => modal.showModal());
    closeEls.forEach((el) => el.addEventListener("click", () => modal.close()));
  }

  function initFilters() {
    for (const btn of qsa(".filter-btn[data-scope]")) {
      btn.addEventListener("click", () => {
        const nextScope = btn.getAttribute("data-scope") || "all";
        if (nextScope === state.scope) return;
        state.scope = nextScope;
        setActiveScopeButton();
        applyFilters();
        clearSelection();
      });
    }
  }

  function initTitleFilter() {
    const input = qs("#title-filter");
    if (!input) return;
    input.addEventListener("input", () => {
      state.titleFilter = input.value || "";
      applyFilters();
    });
  }

  function initSort() {
    const btn = qs("#sort-btn");
    const shelf = qs("#library-shelf");
    if (!btn || !shelf) return;
    btn.addEventListener("click", () => {
      const cards = getAllBookCards();
      cards.sort((a, b) => {
        const ta = a.getAttribute("data-title") || "";
        const tb = b.getAttribute("data-title") || "";
        return ta.localeCompare(tb);
      });
      for (const card of cards) shelf.appendChild(card);
    });
  }

  function initSelection() {
    const toggle = qs("#select-toggle-btn");
    if (toggle) toggle.addEventListener("click", () => setSelectMode(!state.selectMode));

    const selectAllBtn = qs("#select-all-btn");
    if (selectAllBtn) selectAllBtn.addEventListener("click", () => selectAllVisible());

    const clearBtn = qs("#clear-selection-btn");
    if (clearBtn) clearBtn.addEventListener("click", () => clearSelection());

    const indexBtn = qs("#index-selected-btn");
    if (indexBtn) indexBtn.addEventListener("click", () => bulkIndexSelected());

    for (const card of getAllBookCards()) {
      const checkbox = qs(".select-checkbox", card);
      const bookId = getBookIdFromCard(card);
      if (!checkbox || !bookId) continue;

      checkbox.addEventListener("click", (e) => {
        e.stopPropagation();
      });
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) state.selectedBookIds.add(bookId);
        else state.selectedBookIds.delete(bookId);
        setBookSelected(card, checkbox.checked);
        updateSelectionUi();
      });

      card.addEventListener("click", (e) => {
        if (!state.selectMode) return;
        e.preventDefault();
        checkbox.checked = !checkbox.checked;
        checkbox.dispatchEvent(new Event("change", { bubbles: true }));
      });
    }

    updateSelectionUi();
  }

  function initInterruptedHint() {
    let wasIndexing = false;
    try {
      wasIndexing = localStorage.getItem(BULK_INDEX_STORAGE_KEY) === "true";
    } catch {
      wasIndexing = false;
    }
    if (wasIndexing) setInterruptedNoticeVisible(true);
  }

  function init() {
    initTabSwitcher();
    initAddBooksModal();
    initFilters();
    initTitleFilter();
    initSort();
    initSelection();
    initInterruptedHint();
    attachBeforeUnload();
    applyFilters();
    void lazyFetchStatuses();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
