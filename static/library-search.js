function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function sessionKey() {
  return "reader3.search.library";
}

class LibrarySearchUI {
  constructor() {
    this.input = document.getElementById("library-search-input");
    this.caseBox = document.getElementById("library-search-case");
    this.sortBy = document.getElementById("library-search-sort");
    this.clearBtn = document.getElementById("library-search-clear");
    this.status = document.getElementById("library-search-status");
    this.panel = document.getElementById("library-search-panel");
    this.results = document.getElementById("library-search-results");
    this.grid = document.getElementById("library-book-grid");
    this.debounceTimer = null;
  }

  init() {
    if (!this.input || !this.panel || !this.results) return;
    this.input.addEventListener("input", () => {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = setTimeout(() => this.performSearch(), 300);
    });
    this.caseBox?.addEventListener("change", () => this.performSearch());
    this.sortBy?.addEventListener("change", () => this.performSearch());
    this.clearBtn?.addEventListener("click", () => this.clearSearch(true));

    this.restoreFromSession();
  }

  restoreFromSession() {
    try {
      const raw = sessionStorage.getItem(sessionKey());
      if (!raw) return;
      const data = JSON.parse(raw);
      if (data?.q) this.input.value = data.q;
      if (typeof data?.caseSensitive === "boolean" && this.caseBox) this.caseBox.checked = data.caseSensitive;
      if (data?.sortBy && this.sortBy) this.sortBy.value = data.sortBy;
      if (data?.payload) this.renderPayload(data.payload);
    } catch {
      // ignore
    }
  }

  persistToSession(payload, q, caseSensitive, sortBy) {
    try {
      sessionStorage.setItem(sessionKey(), JSON.stringify({ payload, q, caseSensitive, sortBy }));
    } catch {
      // ignore
    }
  }

  clearSearch(clearSession) {
    this.input.value = "";
    this.panel.style.display = "none";
    this.results.innerHTML = "";
    this.status.textContent = "";
    this.grid.style.display = "grid";
    if (clearSession) {
      try {
        sessionStorage.removeItem(sessionKey());
      } catch {
        // ignore
      }
    }
  }

  async performSearch(maxResultsPerBook = 3) {
    const q = this.input.value.trim();
    if (!q) {
      this.clearSearch(false);
      return;
    }

    const caseSensitive = Boolean(this.caseBox?.checked);
    const sortBy = this.sortBy?.value || "relevance";

    this.panel.style.display = "block";
    this.grid.style.display = "none";
    this.status.textContent = "Searching…";
    this.results.innerHTML = "";

    const url = new URL("/api/search/library", window.location.origin);
    url.searchParams.set("q", q);
    url.searchParams.set("mode", "keyword");
    url.searchParams.set("max_results_per_book", String(maxResultsPerBook));
    url.searchParams.set("max_total_results", "100");
    url.searchParams.set("sort_by", sortBy);
    if (caseSensitive) url.searchParams.set("case_sensitive", "true");

    const resp = await fetch(url.toString());
    const payload = await resp.json();
    this.renderPayload(payload);
    this.persistToSession(payload, q, caseSensitive, sortBy);
  }

  renderPayload(payload) {
    const q = this.input.value.trim();
    const status = payload?.status_message || "";
    this.status.textContent = status;
    this.results.innerHTML = "";

    const bookOrder = Array.isArray(payload?.book_order) ? payload.book_order : [];
    const grouped = payload?.grouped_by_book || {};
    const meta = payload?.book_metadata || {};

    let foundAny = false;
    for (const bookId of bookOrder) {
      const bookResults = grouped[bookId] || [];
      if (!Array.isArray(bookResults) || !bookResults.length) continue;
      foundAny = true;

      const group = document.createElement("div");
      group.className = "library-book-group";

      const header = document.createElement("div");
      header.className = "library-book-header";

      const left = document.createElement("div");
      const title = document.createElement("div");
      title.className = "library-book-title";
      title.textContent = meta?.[bookId]?.title || bookId;
      const author = document.createElement("div");
      author.className = "library-book-author";
      author.textContent = meta?.[bookId]?.author || "";
      left.appendChild(title);
      left.appendChild(author);

      const right = document.createElement("div");
      const showMore = document.createElement("button");
      showMore.className = "library-show-more";
      showMore.type = "button";
      showMore.textContent = "Show more";
      showMore.addEventListener("click", () => this.performSearch(10));
      right.appendChild(showMore);

      header.appendChild(left);
      header.appendChild(right);
      group.appendChild(header);

      for (const r of bookResults) {
        const item = document.createElement("div");
        item.className = "search-result-item";
        const chapter = document.createElement("div");
        chapter.className = "search-result-chapter";
        chapter.textContent = r.chapter_title;

        const snippet = document.createElement("div");
        snippet.className = "search-result-snippet";
        snippet.innerHTML =
          `${escapeHtml(r.context_before)} ` +
          `<mark class="search-match">${escapeHtml(r.match_text)}</mark>` +
          ` ${escapeHtml(r.context_after)}`;

        item.appendChild(chapter);
        item.appendChild(snippet);
        item.addEventListener("click", () => {
          const occ = Number(r.occurrence_index);
          window.location.href = `/read/${bookId}/${r.chapter_order}?q=${encodeURIComponent(q)}&occurrence=${encodeURIComponent(String(occ))}`;
        });
        group.appendChild(item);
      }

      this.results.appendChild(group);
    }

    if (!foundAny) {
      const empty = document.createElement("div");
      empty.className = "search-status";
      empty.textContent = `No results found for "${q}"`;
      this.results.appendChild(empty);
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const ui = new LibrarySearchUI();
  ui.init();
});

