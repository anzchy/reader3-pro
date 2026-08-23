// 0.4（007）：包成 IIFE，顶层符号不再挂到 window 上。
// 此前这四个文件各自定义一份 escapeHtml，同一页里谁后加载谁赢——reader.html
// 同时加载 search.js 与 ai.js，两份实现对 null/undefined 的处理并不相同。
// 无导出：四个文件都自初始化，实测无任何跨文件符号引用。
// 函数体不整体缩进，是为了不让这次的两行包裹淹没在 1900 行 whitespace diff 里。
(() => {
function getReaderContext() {
  const ctx = window.Reader3Ctx || {};
  if (ctx.bookId && Number.isFinite(ctx.chapterIndex)) {
    return { bookId: ctx.bookId, chapterIndex: Number(ctx.chapterIndex) };
  }
  const parts = window.location.pathname.split("/").filter(Boolean);
  // /read/{book_id}/{chapter_index}
  if (parts.length >= 3 && parts[0] === "read") {
    return { bookId: parts[1], chapterIndex: Number(parts[2]) };
  }
  return { bookId: null, chapterIndex: null };
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function getQueryParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    q: params.get("q") || "",
    occurrence: params.get("occurrence"),
  };
}

function sessionKey(bookId) {
  return `reader3.search.reader.${bookId}`;
}

function clearExistingMarks(container) {
  container.querySelectorAll("mark.search-match, mark.search-current").forEach((mark) => {
    const parent = mark.parentNode;
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
    parent.removeChild(mark);
    parent.normalize();
  });
}

function isLatinChar(ch) {
  try {
    return /\p{Script=Latin}/u.test(ch);
  } catch {
    return /[A-Za-z]/.test(ch);
  }
}

function isCombiningMark(ch) {
  try {
    return /\p{Mark}/u.test(ch);
  } catch {
    // best-effort fallback
    const code = ch.codePointAt(0);
    return code >= 0x300 && code <= 0x36f;
  }
}

function normalizeWithMap(text, caseSensitive) {
  const out = [];
  const map = [];
  let inLatinRun = false;

  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (isCombiningMark(ch)) {
      if (inLatinRun) continue;
      const emit = caseSensitive ? ch : ch.toLocaleLowerCase();
      for (const c of emit) {
        out.push(c);
        map.push(i);
      }
      continue;
    }

    if (isLatinChar(ch)) {
      inLatinRun = true;
      const nfd = ch.normalize("NFD");
      let base = "";
      for (const c of nfd) {
        if (!isCombiningMark(c)) base += c;
      }
      const emit = caseSensitive ? base : base.toLocaleLowerCase();
      for (const c of emit) {
        out.push(c);
        map.push(i);
      }
      continue;
    }

    inLatinRun = false;
    const emit = caseSensitive ? ch : ch.toLocaleLowerCase();
    for (const c of emit) {
      out.push(c);
      map.push(i);
    }
  }

  return { normalized: out.join(""), map };
}

function findAllOccurrencesInTextNode(text, term, caseSensitive) {
  const trimmed = String(term || "").trim();
  if (!trimmed) return [];

  const { normalized: haystack, map } = normalizeWithMap(text, caseSensitive);
  const { normalized: needle } = normalizeWithMap(trimmed, caseSensitive);
  if (!needle) return [];

  const positions = [];
  let idx = 0;
  while (true) {
    const found = haystack.indexOf(needle, idx);
    if (found === -1) break;
    const startOrig = map[found];
    const endOrig = map[found + needle.length - 1] + 1;
    positions.push([startOrig, endOrig]);
    idx = found + needle.length;
  }
  return positions;
}

function applyHighlights(container, term, caseSensitive) {
  if (!term) return [];
  clearExistingMarks(container);
  const doc = container?.ownerDocument || document;

  const marks = [];
  const walker = doc.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.nodeValue) return NodeFilter.FILTER_REJECT;
      if (!node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
      const parent = node.parentElement;
      if (!parent) return NodeFilter.FILTER_REJECT;
      if (parent.closest("script, style, mark")) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });

  const textNodes = [];
  while (walker.nextNode()) textNodes.push(walker.currentNode);

  for (const node of textNodes) {
    const text = node.nodeValue;
    const hits = findAllOccurrencesInTextNode(text, term, caseSensitive);
    if (!hits.length) continue;

    const frag = doc.createDocumentFragment();
    let cursor = 0;
    for (const [start, end] of hits) {
      if (start > cursor) frag.appendChild(doc.createTextNode(text.slice(cursor, start)));
      const mark = doc.createElement("mark");
      mark.className = "search-match";
      mark.textContent = text.slice(start, end);
      frag.appendChild(mark);
      marks.push(mark);
      cursor = end;
    }
    if (cursor < text.length) frag.appendChild(doc.createTextNode(text.slice(cursor)));
    node.parentNode.replaceChild(frag, node);
  }

  return marks;
}

function scrollToOccurrence(marks, occurrenceIndex) {
  if (!marks.length) return;
  let idx = Number.isFinite(occurrenceIndex) ? occurrenceIndex : 0;
  if (idx < 0 || idx >= marks.length) idx = 0;
  marks.forEach((m) => m.classList.remove("search-current"));
  const target = marks[idx];
  target.classList.add("search-current");
  target.scrollIntoView({ behavior: "smooth", block: "center" });
}

function getContentRoot() {
  if (window.Reader3Epub && window.Reader3Epub.getContentRoot) {
    return window.Reader3Epub.getContentRoot();
  }
  return document.querySelector(".book-content");
}

class ReaderSearchUI {
  constructor(bookId) {
    this.bookId = bookId;
    this.toggleBtn = document.getElementById("reader-search-toggle");
    this.drawer = document.getElementById("reader-search-drawer");
    this.closeBtn = document.getElementById("reader-search-close");
    this.input = document.getElementById("reader-search-input");
    this.caseBox = document.getElementById("reader-search-case");
    this.modeSelect = document.getElementById("reader-search-mode");
    this.clearBtn = document.getElementById("reader-search-clear");
    this.indexBtn = document.getElementById("reader-index-btn");
    this.indexStatus = document.getElementById("reader-index-status");
    this.status = document.getElementById("reader-search-status");
    this.list = document.getElementById("reader-search-results");
    this.panel = document.getElementById("reader-search-panel");
    this.content = getContentRoot();
    this.pendingHighlight = null;
  }

  init() {
    if (!this.bookId || !this.input || !this.drawer || !this.toggleBtn) return;

    if (!this.content && window.Reader3Epub && window.Reader3Epub.onContentsReady) {
      window.Reader3Epub.onContentsReady(() => {
        this.content = getContentRoot();
        if (this.input.value.trim()) {
          const pending = this.pendingHighlight;
          this.performSearch().then(() => {
            if (pending) {
              this.highlightFromUrl(pending.term, pending.occurrence);
              this.pendingHighlight = null;
            }
          });
        }
      });
    }


    this.toggleBtn.addEventListener("click", () => this.openDrawer());
    this.closeBtn?.addEventListener("click", () => this.closeDrawer());
    this.clearBtn?.addEventListener("click", () => this.clearSearch(true));
    this.caseBox?.addEventListener("change", () => {
      if (this.input.value.trim()) this.performSearch();
    });
    this.modeSelect?.addEventListener("change", () => {
      this.refreshIndexStatus();
      if (this.input.value.trim()) this.performSearch();
    });
    this.indexBtn?.addEventListener("click", () => this.indexBook());
    this.input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        this.performSearch();
      } else if (e.key === "Escape") {
        this.closeDrawer();
      }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.drawer.classList.contains("is-open")) {
        this.closeDrawer();
      }
    });

    this.restoreFromSession();
    this.refreshIndexStatus();

    const qp = getQueryParams();
    if (qp.q) {
      this.input.value = qp.q;
      this.openDrawer();
      this.pendingHighlight = { term: qp.q, occurrence: qp.occurrence };
      this.performSearch().then(() => {
        const occ = qp.occurrence == null ? null : Number(qp.occurrence);
        this.highlightFromUrl(qp.q, occ);
      });
    }
  }

  openDrawer() {
    this.drawer.classList.add("is-open");
    this.drawer.setAttribute("aria-hidden", "false");
    this.input.focus();
    this.input.select();
  }

  closeDrawer() {
    this.drawer.classList.remove("is-open");
    this.drawer.setAttribute("aria-hidden", "true");
  }

  restoreFromSession() {
    try {
      const raw = sessionStorage.getItem(sessionKey(this.bookId));
      if (!raw) return;
      const data = JSON.parse(raw);
      if (data?.q) this.input.value = data.q;
      if (typeof data?.caseSensitive === "boolean" && this.caseBox) this.caseBox.checked = data.caseSensitive;
      if (data?.mode && this.modeSelect) this.modeSelect.value = data.mode;
      if (Array.isArray(data?.results)) this.renderResults(data.results, data.statusMessage || "");
    } catch {
      // ignore
    }
  }

  persistToSession(payload) {
    try {
      sessionStorage.setItem(sessionKey(this.bookId), JSON.stringify(payload));
    } catch {
      // ignore
    }
  }

  clearSearch(clearSession) {
    this.input.value = "";
    this.status.textContent = "";
    this.list.innerHTML = "";
    if (this.content) clearExistingMarks(this.content);
    if (clearSession) {
      try {
        sessionStorage.removeItem(sessionKey(this.bookId));
      } catch {
        // ignore
      }
    }
  }

  async performSearch() {
    const q = this.input.value.trim();
    if (!q) {
      this.clearSearch(false);
      return;
    }
    if (!this.content) {
      this.status.textContent = "Content not ready";
      return;
    }

    const caseSensitive = Boolean(this.caseBox?.checked);
    const mode = this.modeSelect?.value || "keyword";
    this.status.textContent = "Searching…";

    const url = new URL(`/api/search/${encodeURIComponent(this.bookId)}`, window.location.origin);
    url.searchParams.set("q", q);
    url.searchParams.set("max_results", "1000");
    url.searchParams.set("mode", mode);
    if (caseSensitive) url.searchParams.set("case_sensitive", "true");

    const resp = await fetch(url.toString());
    const data = await resp.json();
    if (!resp.ok) {
      this.status.textContent = data?.detail || "Search failed";
      return;
    }
    const results = Array.isArray(data?.results) ? data.results : [];
    const statusMessage = data?.status_message || "";
    this.renderResults(results, statusMessage);

    this.persistToSession({ q, caseSensitive, mode, results, statusMessage });
  }

  renderResults(results, statusMessage) {
    this.status.textContent = statusMessage || `Found ${results.length} results`;
    this.list.innerHTML = "";

    if (!results.length) {
      const empty = document.createElement("div");
      empty.className = "search-status";
      empty.textContent = `No results found for "${this.input.value.trim()}"`;
      this.list.appendChild(empty);
      return;
    }

    for (const r of results) {
      const item = document.createElement("div");
      item.className = "search-result-item";
      if (r.match_explanation) item.title = r.match_explanation;

      const chapter = document.createElement("div");
      chapter.className = "search-result-chapter";
      chapter.textContent = r.chapter_title;

      const snippet = document.createElement("div");
      snippet.className = "search-result-snippet";
      const before = r.context_before ? `${escapeHtml(r.context_before)} ` : "";
      const after = r.context_after ? ` ${escapeHtml(r.context_after)}` : "";
      snippet.innerHTML = `${before}<mark class="search-match">${escapeHtml(r.match_text)}</mark>${after}`;

      if (r.match_explanation) {
        const expl = document.createElement("div");
        expl.className = "search-status";
        expl.style.marginTop = "6px";
        expl.textContent = r.match_explanation;
        item.appendChild(expl);
      }

      item.appendChild(chapter);
      item.appendChild(snippet);

      item.addEventListener("click", () => {
        const term = this.input.value.trim();
        const occ = Number(r.occurrence_index);
        const mode = this.modeSelect?.value || "keyword";
        if (mode === "semantic" && r.mode === "semantic") {
          window.location.href = `/read/${this.bookId}/${r.chapter_order}`;
          return;
        }
        window.location.href = `/read/${this.bookId}/${r.chapter_order}?q=${encodeURIComponent(term)}&occurrence=${encodeURIComponent(String(occ))}`;
      });

      this.list.appendChild(item);
    }
  }

  async refreshIndexStatus() {
    const mode = this.modeSelect?.value || "keyword";
    if (!this.indexBtn || !this.indexStatus) return;
    if (mode === "keyword") {
      this.indexBtn.style.display = "none";
      this.indexStatus.textContent = "";
      return;
    }
    try {
      const resp = await fetch(`/api/index/${encodeURIComponent(this.bookId)}/status`);
      const data = await resp.json();
      if (resp.ok && data?.status === "indexed") {
        this.indexBtn.style.display = "none";
        this.indexStatus.textContent = `Indexed (${data.chunk_count ?? "?"} chunks)`;
      } else {
        this.indexBtn.style.display = "inline-block";
        this.indexStatus.textContent = "Not indexed";
      }
    } catch {
      this.indexBtn.style.display = "inline-block";
      this.indexStatus.textContent = "Index status unavailable";
    }
  }

  async indexBook() {
    if (!this.indexBtn || !this.indexStatus) return;
    this.indexBtn.disabled = true;
    this.indexStatus.textContent = "Indexing…";
    try {
      const resp = await fetch(`/api/index/${encodeURIComponent(this.bookId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force_reindex: false }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        this.indexStatus.textContent = data?.detail || "Indexing failed";
      } else {
        this.indexStatus.textContent = `Indexed (${data.chunk_count ?? "?"} chunks)`;
        this.indexBtn.style.display = "none";
      }
    } catch (e) {
      this.indexStatus.textContent = "Indexing failed";
    } finally {
      this.indexBtn.disabled = false;
    }
  }

  async highlightFromUrl(term, occurrenceIndex) {
    const ctx = getReaderContext();
    if (!ctx.bookId || ctx.chapterIndex == null) return;
    const caseSensitive = Boolean(this.caseBox?.checked);
    if (!this.content) {
      this.content = getContentRoot();
    }
    if (!this.content) return;

    try {
      const resp = await fetch(`/api/highlight/${encodeURIComponent(ctx.bookId)}/${encodeURIComponent(String(ctx.chapterIndex))}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          search_term: term,
          occurrence_index: occurrenceIndex,
          case_sensitive: caseSensitive,
        }),
      });
      const data = await resp.json();
      const selected = data?.selected_occurrence_index;
      const marks = applyHighlights(this.content, term, caseSensitive);
      scrollToOccurrence(marks, typeof selected === "number" ? selected : occurrenceIndex);
    } catch {
      const marks = applyHighlights(this.content, term, caseSensitive);
      scrollToOccurrence(marks, occurrenceIndex);
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const ctx = getReaderContext();
  if (!ctx.bookId) return;
  const ui = new ReaderSearchUI(ctx.bookId);
  ui.init();
});
})();
