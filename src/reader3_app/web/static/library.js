(() => {
  "use strict";

  const BULK_INDEX_STORAGE_KEY = "reader3.library.bulkIndexingActive";
  const VIEW_MODE_STORAGE_KEY = "reader3.library.viewMode";

  const state = {
    scope: "all",
    activeRightTab: "dashboard",
    viewMode: "grid",
    selectMode: false,
    selectedBookIds: new Set(),
    titleFilter: "",
    isIndexing: false,
    statuses: new Map(),
    inFlightStatus: new Set(),
    collections: [],
    collectionBookIdsById: new Map(),
  };

  const _lastFocusByDialog = new WeakMap();

  function qs(sel, root = document) {
    return root.querySelector(sel);
  }

  function qsa(sel, root = document) {
    return Array.from(root.querySelectorAll(sel));
  }

  function getAllBookCards() {
    return qsa(".book-card");
  }

  function getAllBookRows() {
    return qsa(".book-row");
  }

  function getAllBookElements() {
    return qsa(".book-card, .book-row");
  }

  function getBookIdFromElement(el) {
    return el?.getAttribute("data-book-id") || "";
  }

  function setHidden(el, hidden) {
    if (!el) return;
    if (hidden) el.setAttribute("hidden", "");
    else el.removeAttribute("hidden");
  }

  function announce(message) {
    const el = qs("#aria-live");
    if (!el) return;
    const text = String(message || "").trim();
    if (!text) return;
    el.textContent = "";
    window.setTimeout(() => {
      el.textContent = text;
    }, 10);
  }

  function _focusableElements(root) {
    const selectors = [
      'a[href]',
      "button:not([disabled])",
      "input:not([disabled])",
      "select:not([disabled])",
      "textarea:not([disabled])",
      '[tabindex]:not([tabindex="-1"])',
    ];
    return qsa(selectors.join(","), root).filter((el) => el.offsetParent !== null);
  }

  function setupDialog(dialog) {
    if (!dialog || dialog.dataset.dialogSetup === "true") return;
    dialog.dataset.dialogSetup = "true";

    dialog.addEventListener("cancel", (e) => {
      e.preventDefault();
      dialog.close();
    });

    dialog.addEventListener("keydown", (e) => {
      if (e.key !== "Tab") return;
      const focusables = _focusableElements(dialog);
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    });

    dialog.addEventListener("close", () => {
      const prev = _lastFocusByDialog.get(dialog);
      if (prev && typeof prev.focus === "function") prev.focus();
      _lastFocusByDialog.delete(dialog);
    });
  }

  function openDialog(dialog, initialFocusSelector) {
    if (!dialog || typeof dialog.showModal !== "function") return;
    setupDialog(dialog);
    _lastFocusByDialog.set(dialog, document.activeElement);
    dialog.showModal();
    const focusTarget =
      (initialFocusSelector && qs(initialFocusSelector, dialog)) || _focusableElements(dialog)[0];
    if (focusTarget && typeof focusTarget.focus === "function") focusTarget.focus();
  }

  function applyViewMode() {
    const grid = qs("#library-grid-view");
    const list = qs("#library-list-view");
    const isList = state.viewMode === "list";
    setHidden(grid, isList);
    setHidden(list, !isList);
    document.body.classList.toggle("view-list", isList);
  }

  function setViewMode(mode, persist) {
    const next = mode === "list" ? "list" : "grid";
    state.viewMode = next;
    applyViewMode();
    if (persist) {
      try {
        localStorage.setItem(VIEW_MODE_STORAGE_KEY, next);
      } catch {
        // ignore
      }
    }
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
    if (state.scope.startsWith("collection:")) {
      const id = state.scope.slice("collection:".length);
      const allowed = state.collectionBookIdsById.get(id);
      if (!allowed) return false;
      const bookId = getBookIdFromElement(card);
      return allowed.has(bookId);
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
    for (const el of getAllBookElements()) {
      const visible = matchesScope(el) && matchesTitleFilter(el);
      setHidden(el, !visible);
    }
  }

  function setActiveScopeButton() {
    for (const btn of qsa(".filter-btn[data-scope], .collection-btn[data-scope]")) {
      btn.classList.toggle("is-active", btn.getAttribute("data-scope") === state.scope);
    }
  }

  function setScope(nextScope) {
    if (!nextScope || nextScope === state.scope) return;
    state.scope = nextScope;
    setActiveScopeButton();
    applyFilters();
    clearSelection();
    if (state.activeRightTab === "dashboard") {
      void refreshStats(false);
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

  function getAllBookIds() {
    return Array.from(
      new Set(getAllBookElements().map(getBookIdFromElement).filter(Boolean)),
    );
  }

  function syncSelectionForBookId(bookId) {
    const selected = state.selectedBookIds.has(bookId);
    for (const el of qsa(`[data-book-id="${CSS.escape(bookId)}"]`)) {
      const checkbox = qs(".select-checkbox", el);
      if (checkbox) checkbox.checked = selected;
      el.classList.toggle("is-selected", selected);
    }
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

    const addToCollectionBtn = qs("#add-to-collection-btn");
    if (addToCollectionBtn) {
      addToCollectionBtn.disabled =
        state.isIndexing || state.selectedBookIds.size === 0 || state.collections.length === 0;
    }
  }

  function clearSelection() {
    state.selectedBookIds.clear();
    for (const id of getAllBookIds()) syncSelectionForBookId(id);
    updateSelectionUi();
  }

  function selectAllVisible() {
    const elements = state.viewMode === "list" ? getAllBookRows() : getAllBookCards();
    for (const el of elements) {
      if (el.hasAttribute("hidden")) continue;
      const id = getBookIdFromElement(el);
      if (!id) continue;
      state.selectedBookIds.add(id);
      syncSelectionForBookId(id);
    }
    updateSelectionUi();
  }

  function setStatusForBook(bookId, status) {
    state.statuses.set(bookId, status);
    const normalized = String(status?.status || "unknown");
    const targets = [
      qs(`.book-card[data-book-id="${CSS.escape(bookId)}"]`),
      qs(`.book-row[data-book-id="${CSS.escape(bookId)}"]`),
    ].filter(Boolean);

    for (const target of targets) {
      const pill = qs(".status-pill", target);
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

      const cc = status?.chunk_count;
      const chunkPill = qs(".chunk-pill", target);
      if (chunkPill) {
        if (normalized === "indexed" && typeof cc === "number") {
          chunkPill.textContent = `${cc} chunks`;
          setHidden(chunkPill, false);
        } else {
          setHidden(chunkPill, true);
        }
      }
      const chunkCell = qs('[data-role="chunk-count"]', target);
      if (chunkCell) {
        if (normalized === "indexed" && typeof cc === "number") chunkCell.textContent = String(cc);
        else if (normalized === "not_indexed") chunkCell.textContent = "—";
        else chunkCell.textContent = "—";
      }
    }
  }

  function setLoadingStatus(bookId) {
    setStatusForBook(bookId, { book_id: bookId, status: "unknown", chunk_count: null });
    for (const target of [
      qs(`.book-card[data-book-id="${CSS.escape(bookId)}"]`),
      qs(`.book-row[data-book-id="${CSS.escape(bookId)}"]`),
    ].filter(Boolean)) {
      const pill = qs(".status-pill", target);
      if (!pill) continue;
      pill.classList.remove("is-indexed", "is-not-indexed", "is-indexing", "is-unknown", "is-error");
      pill.classList.add("is-loading");
      pill.textContent = "Loading…";
    }
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
    const ids = getAllBookCards().map(getBookIdFromElement).filter(Boolean);
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
    if (visible) announce("Indexing was interrupted.");
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
    openDialog(modal, "#index-errors-ok");
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
    announce(`Indexing ${selected.length} book(s).`);

    const errors = [];
    for (let i = 0; i < selected.length; i++) {
      const bookId = selected[i];
      setIndexProgress(`Indexing ${i + 1}/${selected.length}…`);
      announce(`Indexing book ${i + 1} of ${selected.length}.`);
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
    announce(errors.length ? "Indexing finished with errors." : "Indexing finished.");
  }

  function setActiveRightTab(tab) {
    const name = tab || "dashboard";
    state.activeRightTab = name;
    qsa(".right-tab").forEach((el) => el.classList.toggle("is-active", el.id === `${name}-tab`));
    qsa("#right-tabbar .tab-btn").forEach((el) => {
      const active = el.getAttribute("data-tab") === name;
      el.classList.toggle("is-active", active);
      el.setAttribute("aria-selected", active ? "true" : "false");
    });
    if (state.activeRightTab === "dashboard") void refreshStats(false);
  }

  function initTabSwitcher() {
    const tabbar = qs("#right-tabbar");
    if (!tabbar) return;
    tabbar.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-tab]");
      if (!btn) return;
      setActiveRightTab(btn.getAttribute("data-tab"));
    });
  }

  function setRightPanelCollapsed(collapsed, persist) {
    const layout = qs(".library-layout");
    if (!layout) return;
    const isCollapsed = Boolean(collapsed);
    layout.classList.toggle("is-right-collapsed", isCollapsed);
    const toggle = qs("#right-collapse-toggle");
    if (toggle) {
      toggle.setAttribute("aria-label", isCollapsed ? "Show right panel" : "Hide right panel");
      toggle.title = isCollapsed ? "Show right panel" : "Hide right panel";
      toggle.textContent = isCollapsed ? "›" : "›";
    }
    if (persist) {
      try {
        localStorage.setItem("reader3.library.rightPanelCollapsed", isCollapsed ? "true" : "false");
      } catch {
        // ignore
      }
    }
  }

  function initRightPanelCollapse() {
    const toggle = qs("#right-collapse-toggle");
    const layout = qs(".library-layout");
    if (!toggle || !layout) return;
    let stored = null;
    try {
      stored = localStorage.getItem("reader3.library.rightPanelCollapsed");
    } catch {
      stored = null;
    }
    setRightPanelCollapsed(stored === "true", false);
    toggle.addEventListener("click", () => {
      const next = !layout.classList.contains("is-right-collapsed");
      setRightPanelCollapsed(next, true);
    });
  }

  function initAddBooksModal() {
    const addBtn = qs("#add-books-btn");
    const modal = qs("#add-books-modal");
    const closeEls = [qs("#add-books-close"), qs("#add-books-ok")].filter(Boolean);
    if (!addBtn || !modal || typeof modal.showModal !== "function") return;
    setupDialog(modal);
    addBtn.addEventListener("click", () => openDialog(modal, "#add-books-ok"));
    closeEls.forEach((el) => el.addEventListener("click", () => modal.close()));
  }

  function initFilters() {
    for (const btn of qsa(".filter-btn[data-scope]")) {
      btn.addEventListener("click", () => {
        const nextScope = btn.getAttribute("data-scope") || "all";
        setScope(nextScope);
      });
    }

    const collectionsList = qs("#collections-list");
    if (collectionsList) {
      collectionsList.addEventListener("click", (e) => {
        const actionBtn = e.target.closest("button[data-action]");
        if (actionBtn) return;
        const scopeBtn = e.target.closest("button[data-scope]");
        if (scopeBtn) setScope(scopeBtn.getAttribute("data-scope") || "all");
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

  function initViewToggle() {
    let stored = null;
    try {
      stored = localStorage.getItem(VIEW_MODE_STORAGE_KEY);
    } catch {
      stored = null;
    }
    if (stored === "list" || stored === "grid") {
      setViewMode(stored, false);
    } else {
      applyViewMode();
    }

    const btn = qs("#view-toggle-btn");
    if (!btn) return;
    btn.addEventListener("click", () => {
      setViewMode(state.viewMode === "grid" ? "list" : "grid", true);
    });
  }

  function initSort() {
    const btn = qs("#sort-btn");
    const shelf = qs("#library-grid-view");
    const tbody = qs("#library-list-view tbody");
    if (!btn || !shelf || !tbody) return;
    btn.addEventListener("click", () => {
      const ids = getAllBookCards()
        .map((c) => ({ id: getBookIdFromElement(c), title: c.getAttribute("data-title") || "" }))
        .filter((x) => x.id);
      ids.sort((a, b) => a.title.localeCompare(b.title));

      for (const { id } of ids) {
        const card = qs(`.book-card[data-book-id="${CSS.escape(id)}"]`);
        if (card) shelf.appendChild(card);
        const row = qs(`.book-row[data-book-id="${CSS.escape(id)}"]`);
        if (row) tbody.appendChild(row);
      }
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

    const addToCollectionBtn = qs("#add-to-collection-btn");
    if (addToCollectionBtn) addToCollectionBtn.addEventListener("click", () => openAddToCollectionModal());

    for (const el of getAllBookElements()) {
      const checkbox = qs(".select-checkbox", el);
      const bookId = getBookIdFromElement(el);
      if (!checkbox || !bookId) continue;

      checkbox.addEventListener("click", (e) => e.stopPropagation());
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) state.selectedBookIds.add(bookId);
        else state.selectedBookIds.delete(bookId);
        syncSelectionForBookId(bookId);
        updateSelectionUi();
      });

      el.addEventListener("click", (e) => {
        if (!state.selectMode) return;
        e.preventDefault();
        checkbox.checked = !checkbox.checked;
        checkbox.dispatchEvent(new Event("change", { bubbles: true }));
      });
    }

    updateSelectionUi();
  }

  function existingBookIdSet() {
    return new Set(getAllBookCards().map(getBookIdFromElement).filter(Boolean));
  }

  function updateCollectionMaps() {
    const existingIds = existingBookIdSet();
    state.collectionBookIdsById = new Map();
    for (const c of state.collections) {
      const allowed = new Set();
      for (const bid of c.book_ids || []) {
        if (existingIds.has(bid)) allowed.add(bid);
      }
      state.collectionBookIdsById.set(c.id, allowed);
    }
  }

  function renderCollections() {
    const container = qs("#collections-list");
    if (!container) return;
    container.innerHTML = "";

    const existingIds = existingBookIdSet();
    const collections = Array.from(state.collections).sort((a, b) =>
      String(a.name || "").localeCompare(String(b.name || ""), undefined, { sensitivity: "base" }),
    );

    for (const c of collections) {
      const row = document.createElement("div");
      row.className = "collection-row";
      row.dataset.collectionId = c.id;

      const present = [];
      const missing = [];
      for (const bid of c.book_ids || []) {
        if (existingIds.has(bid)) present.push(bid);
        else missing.push(bid);
      }

      const mainBtn = document.createElement("button");
      mainBtn.type = "button";
      mainBtn.className = "collection-btn";
      mainBtn.dataset.scope = `collection:${c.id}`;
      if (state.scope === mainBtn.dataset.scope) mainBtn.classList.add("is-active");

      const nameSpan = document.createElement("span");
      nameSpan.className = "collection-name";
      nameSpan.textContent = String(c.name || "");

      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = String(present.length);

      mainBtn.appendChild(nameSpan);
      mainBtn.appendChild(badge);

      const actions = document.createElement("div");
      actions.className = "collection-actions";

      if (missing.length) {
        const cleanBtn = document.createElement("button");
        cleanBtn.type = "button";
        cleanBtn.className = "mini-btn";
        cleanBtn.dataset.action = "cleanup";
        cleanBtn.textContent = `Clean (${missing.length})`;
        cleanBtn.title = "Remove missing books from this collection";
        actions.appendChild(cleanBtn);
      }

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "mini-btn mini-btn--danger";
      delBtn.dataset.action = "delete";
      delBtn.textContent = "Delete";
      actions.appendChild(delBtn);

      row.appendChild(mainBtn);
      row.appendChild(actions);
      container.appendChild(row);
    }
  }

  async function apiJson(url, opts) {
    const res = await fetch(url, opts);
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        if (data?.detail) detail = String(data.detail);
      } catch {
        // ignore
      }
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    if (res.status === 204) return null;
    return res.json();
  }

  function setStatsUiLoading(loading) {
    const btn = qs("#refresh-stats-btn");
    if (btn) btn.disabled = loading;
    const stateEl = qs("#stats-state");
    if (stateEl && loading) stateEl.textContent = "Loading…";
  }

  function renderStats(stats) {
    const booksTotal = Number(stats?.books_total ?? 0);
    const booksIndexed = Number(stats?.books_indexed ?? 0);
    const indexedPercent = Number(stats?.indexed_percent ?? 0);
    const sectionsTotal = Number(stats?.sections_total ?? 0);
    const chunksTotal = Number(stats?.chunks_total ?? 0);

    const setText = (id, text) => {
      const el = qs(id);
      if (el) el.textContent = text;
    };

    setText("#stats-books-total", String(booksTotal));
    setText("#stats-books-indexed", String(booksIndexed));
    setText("#stats-indexed-percent", booksTotal ? `${indexedPercent}% indexed` : "—");
    setText("#stats-sections-total", String(sectionsTotal));
    setText("#stats-chunks-total", String(chunksTotal));

    const fill = qs("#stats-bar-fill");
    if (fill) fill.style.width = `${Math.max(0, Math.min(100, indexedPercent))}%`;

    const barLabel = qs("#stats-bar-label");
    if (barLabel) {
      if (booksTotal === 0) {
        barLabel.textContent = "No books in this scope.";
      } else if (indexedPercent >= 100) {
        barLabel.textContent = "All books in this scope are indexed.";
      } else {
        barLabel.textContent = `Indexed ${booksIndexed}/${booksTotal} (${indexedPercent}%)`;
      }
    }

    const stateEl = qs("#stats-state");
    if (stateEl) {
      if (booksTotal === 0) stateEl.textContent = "No books in this scope.";
      else stateEl.textContent = "";
    }
  }

  async function refreshStats(fresh) {
    if (state.activeRightTab !== "dashboard") return;
    setStatsUiLoading(true);
    try {
      const url = `/api/library/stats?scope=${encodeURIComponent(state.scope)}${fresh ? "&fresh=true" : ""}`;
      const data = await apiJson(url, {});
      renderStats(data);
    } catch (e) {
      const stateEl = qs("#stats-state");
      if (stateEl) stateEl.textContent = String(e?.message || "Failed to load stats.");
    } finally {
      setStatsUiLoading(false);
    }
  }

  async function loadCollections() {
    const errEl = qs("#collections-error");
    const emptyEl = qs("#collections-empty-message");
    try {
      const data = await apiJson("/api/collections", {});
      state.collections = Array.isArray(data?.collections) ? data.collections : [];
      if (errEl) {
        errEl.textContent = "";
        setHidden(errEl, true);
      }
    } catch (e) {
      state.collections = [];
      if (errEl) {
        errEl.textContent = String(e?.message || "Failed to load collections.");
        setHidden(errEl, false);
      }
    }
    if (emptyEl) setHidden(emptyEl, state.collections.length !== 0);
    updateCollectionMaps();
    renderCollections();
    updateSelectionUi();
    setActiveScopeButton();
  }

  async function createCollection(name) {
    const created = await apiJson("/api/collections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    await loadCollections();
    return created;
  }

  async function deleteCollection(collectionId) {
    await apiJson(`/api/collections/${encodeURIComponent(collectionId)}`, { method: "DELETE" });
    if (state.scope === `collection:${collectionId}`) setScope("all");
    await loadCollections();
  }

  async function updateCollectionBooks(collectionId, body) {
    await apiJson(`/api/collections/${encodeURIComponent(collectionId)}/books`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    await loadCollections();
  }

  function initCollectionsActions() {
    const container = qs("#collections-list");
    if (!container) return;
    container.addEventListener("click", async (e) => {
      const actionBtn = e.target.closest("button[data-action]");
      if (!actionBtn) return;
      const rowEl = actionBtn.closest(".collection-row");
      const collectionId = rowEl?.dataset?.collectionId;
      if (!collectionId) return;

      if (actionBtn.dataset.action === "delete") {
        if (!confirm("Delete this collection?")) return;
        await deleteCollection(collectionId);
        return;
      }

      if (actionBtn.dataset.action === "cleanup") {
        const c = state.collections.find((x) => x.id === collectionId);
        if (!c) return;
        const existingIds = existingBookIdSet();
        const missing = (c.book_ids || []).filter((bid) => !existingIds.has(bid));
        if (!missing.length) return;
        await updateCollectionBooks(collectionId, { remove: missing });
      }
    });
  }

  function openCreateCollectionModal() {
    const modal = qs("#create-collection-modal");
    const nameInput = qs("#create-collection-name");
    const errEl = qs("#create-collection-error");
    const closeEls = [qs("#create-collection-close"), qs("#create-collection-cancel")].filter(Boolean);
    const submit = qs("#create-collection-submit");
    if (!modal || !nameInput || !submit || typeof modal.showModal !== "function") return;

    nameInput.value = "";
    setHidden(errEl, true);
    submit.disabled = false;
    openDialog(modal, "#create-collection-name");

    closeEls.forEach((el) => el.addEventListener("click", () => modal.close(), { once: true }));

    const onSubmit = async () => {
      const name = nameInput.value || "";
      submit.disabled = true;
      setHidden(errEl, true);
      try {
        await createCollection(name);
        modal.close();
      } catch (e) {
        submit.disabled = false;
        if (errEl) {
          errEl.textContent = String(e?.message || "Failed to create collection.");
          setHidden(errEl, false);
        }
      }
    };
    submit.addEventListener("click", onSubmit);
    modal.addEventListener(
      "close",
      () => {
        submit.removeEventListener("click", onSubmit);
      },
      { once: true },
    );
  }

  function openAddToCollectionModal() {
    const modal = qs("#add-to-collection-modal");
    const picker = qs("#collections-picker");
    const errEl = qs("#add-to-collection-error");
    const closeEls = [qs("#add-to-collection-close"), qs("#add-to-collection-cancel")].filter(Boolean);
    if (!modal || !picker || typeof modal.showModal !== "function") return;

    picker.innerHTML = "";
    setHidden(errEl, true);
    for (const c of state.collections) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "toolbar-btn";
      btn.textContent = String(c.name || "");
      btn.addEventListener("click", async () => {
        try {
          const add = Array.from(state.selectedBookIds);
          await updateCollectionBooks(c.id, { add });
          modal.close();
        } catch (e) {
          if (errEl) {
            errEl.textContent = String(e?.message || "Failed to update collection.");
            setHidden(errEl, false);
          }
        }
      });
      picker.appendChild(btn);
    }

    openDialog(modal, "button");
    closeEls.forEach((el) => el.addEventListener("click", () => modal.close(), { once: true }));
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
    initRightPanelCollapse();
    initAddBooksModal();
    initFilters();
    initTitleFilter();
    initViewToggle();
    initSort();
    initSelection();
    initCollectionsActions();
    initInterruptedHint();
    attachBeforeUnload();
    applyFilters();
    void loadCollections();
    void lazyFetchStatuses();

    const createBtn = qs("#collections-create");
    if (createBtn) createBtn.addEventListener("click", () => openCreateCollectionModal());

    const refreshBtn = qs("#refresh-stats-btn");
    if (refreshBtn) refreshBtn.addEventListener("click", () => refreshStats(true));
    void refreshStats(false);

    setActiveRightTab(state.activeRightTab);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
