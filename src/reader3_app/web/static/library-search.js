// 0.4（007）：包成 IIFE，顶层符号不再挂到 window 上。
// 此前这四个文件各自定义一份 escapeHtml，同一页里谁后加载谁赢——reader.html
// 同时加载 search.js 与 ai.js，两份实现对 null/undefined 的处理并不相同。
// 无导出：四个文件都自初始化，实测无任何跨文件符号引用。
// 函数体不整体缩进，是为了不让这次的两行包裹淹没在 1900 行 whitespace diff 里。
(() => {
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
    this.input = document.getElementById("library-panel-search-input");
    this.caseBox = document.getElementById("library-panel-search-case");
    this.modeSelect = document.getElementById("library-panel-search-mode");
    this.sortBy = document.getElementById("library-panel-search-sort");
    this.clearBtn = document.getElementById("library-panel-search-clear");
    this.status = document.getElementById("library-panel-search-status");
    this.panel = document.getElementById("library-panel-search-panel");
    this.results = document.getElementById("library-panel-search-results");
    this.debounceTimer = null;
  }

  init() {
    if (!this.input || !this.panel || !this.results) return;
    this.input.addEventListener("input", () => {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = setTimeout(() => this.performSearch(), 300);
    });
    this.caseBox?.addEventListener("change", () => this.performSearch());
    this.modeSelect?.addEventListener("change", () => this.performSearch());
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
      if (data?.mode && this.modeSelect) this.modeSelect.value = data.mode;
      if (data?.sortBy && this.sortBy) this.sortBy.value = data.sortBy;
      if (data?.payload) this.renderPayload(data.payload);
    } catch {
      // ignore
    }
  }

  persistToSession(payload, q, caseSensitive, sortBy) {
    try {
      const mode = this.modeSelect?.value || "keyword";
      sessionStorage.setItem(sessionKey(), JSON.stringify({ payload, q, caseSensitive, sortBy, mode }));
    } catch {
      // ignore
    }
  }

  clearSearch(clearSession) {
    this.input.value = "";
    this.panel.style.display = "none";
    this.results.innerHTML = "";
    this.status.textContent = "";
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
    const mode = this.modeSelect?.value || "keyword";

    this.panel.style.display = "block";
    this.status.textContent = "Searching…";
    this.results.innerHTML = "";

    const url = new URL("/api/search/library", window.location.origin);
    url.searchParams.set("q", q);
    url.searchParams.set("mode", mode);
    url.searchParams.set("max_results_per_book", String(maxResultsPerBook));
    url.searchParams.set("max_total_results", "100");
    url.searchParams.set("sort_by", sortBy);
    if (caseSensitive) url.searchParams.set("case_sensitive", "true");

    const resp = await fetch(url.toString());
    const payload = await resp.json();
    if (!resp.ok) {
      this.status.textContent = payload?.detail || "Search failed";
      return;
    }
    this.renderPayload(payload);
    this.persistToSession(payload, q, caseSensitive, sortBy);
  }

  renderPayload(payload) {
    const q = this.input.value.trim();
    const status = payload?.status_message || "";
    this.panel.style.display = "block";
    this.status.textContent = status;
    this.results.innerHTML = "";

    const bookOrder = Array.isArray(payload?.book_order) ? payload.book_order : [];
    const grouped = payload?.grouped_by_book || {};
    const meta = payload?.book_metadata || {};
    const indexStatus = payload?.index_status_by_book || {};
    const mode = this.modeSelect?.value || "keyword";

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
      right.style.display = "flex";
      right.style.alignItems = "center";
      right.style.gap = "8px";

      if (mode !== "keyword") {
        const badge = document.createElement("span");
        badge.className = "library-index-badge";
        const st = String(indexStatus?.[bookId] || "unknown");
        badge.dataset.status = st;
        badge.textContent = st === "indexed" ? "Indexed" : st === "not_indexed" ? "Not indexed" : "Index: unknown";
        right.appendChild(badge);

        if (st === "not_indexed") {
          const indexBtn = document.createElement("button");
          indexBtn.className = "library-index-btn";
          indexBtn.type = "button";
          indexBtn.textContent = "Index";
          indexBtn.addEventListener("click", async (e) => {
            e.stopPropagation();
            indexBtn.disabled = true;
            badge.textContent = "Indexing…";
            try {
              const resp = await fetch(`/api/index/${encodeURIComponent(bookId)}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ force_reindex: false }),
              });
              const data = await resp.json();
              if (!resp.ok) {
                badge.textContent = data?.detail || "Indexing failed";
                return;
              }
              badge.textContent = `Indexed (${data.chunk_count ?? "?"})`;
              badge.dataset.status = "indexed";
              indexBtn.remove();
            } catch {
              badge.textContent = "Indexing failed";
            } finally {
              indexBtn.disabled = false;
            }
          });
          right.appendChild(indexBtn);
        }
      }

      const showMore = document.createElement("button");
      showMore.className = "library-show-more";
      showMore.type = "button";
      showMore.setAttribute("data-testid", "lib-search-show-more");
      showMore.setAttribute("data-book-id", String(bookId));
      showMore.textContent = "Show more";
      showMore.addEventListener("click", () => this.performSearch(10));
      right.appendChild(showMore);

      header.appendChild(left);
      header.appendChild(right);
      group.appendChild(header);

      for (const r of bookResults) {
        const item = document.createElement("div");
        item.className = "search-result-item";
        item.setAttribute("data-testid", "lib-search-hit");
        item.setAttribute("data-book-id", String(bookId));
        item.setAttribute("data-section", String(r.chapter_order));
        if (r.match_explanation) item.title = r.match_explanation;
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
        if (r.match_explanation) {
          const expl = document.createElement("div");
          expl.className = "search-status";
          expl.style.marginTop = "6px";
          expl.textContent = r.match_explanation;
          item.appendChild(expl);
        }
        item.addEventListener("click", () => {
          const occ = Number(r.occurrence_index);
          const mode = this.modeSelect?.value || "keyword";
          if (mode === "semantic" && r.mode === "semantic") {
            window.location.href = `/read/${bookId}/${r.chapter_order}`;
            return;
          }
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
})();
