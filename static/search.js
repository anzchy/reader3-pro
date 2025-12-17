function getReaderContext() {
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

  const marks = [];
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
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

    const frag = document.createDocumentFragment();
    let cursor = 0;
    for (const [start, end] of hits) {
      if (start > cursor) frag.appendChild(document.createTextNode(text.slice(cursor, start)));
      const mark = document.createElement("mark");
      mark.className = "search-match";
      mark.textContent = text.slice(start, end);
      frag.appendChild(mark);
      marks.push(mark);
      cursor = end;
    }
    if (cursor < text.length) frag.appendChild(document.createTextNode(text.slice(cursor)));
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

class ReaderSearchUI {
  constructor(bookId) {
    this.bookId = bookId;
    this.toggleBtn = document.getElementById("reader-search-toggle");
    this.drawer = document.getElementById("reader-search-drawer");
    this.closeBtn = document.getElementById("reader-search-close");
    this.input = document.getElementById("reader-search-input");
    this.caseBox = document.getElementById("reader-search-case");
    this.clearBtn = document.getElementById("reader-search-clear");
    this.status = document.getElementById("reader-search-status");
    this.list = document.getElementById("reader-search-results");
    this.panel = document.getElementById("reader-search-panel");
    this.content = document.querySelector(".book-content");
  }

  init() {
    if (!this.bookId || !this.input || !this.content || !this.drawer || !this.toggleBtn) return;

    this.toggleBtn.addEventListener("click", () => this.openDrawer());
    this.closeBtn?.addEventListener("click", () => this.closeDrawer());
    this.clearBtn?.addEventListener("click", () => this.clearSearch(true));
    this.caseBox?.addEventListener("change", () => {
      if (this.input.value.trim()) this.performSearch();
    });
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

    const qp = getQueryParams();
    if (qp.q) {
      this.input.value = qp.q;
      this.openDrawer();
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
    clearExistingMarks(this.content);
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

    const caseSensitive = Boolean(this.caseBox?.checked);
    this.status.textContent = "Searching…";

    const url = new URL(`/api/search/${encodeURIComponent(this.bookId)}`, window.location.origin);
    url.searchParams.set("q", q);
    url.searchParams.set("max_results", "1000");
    if (caseSensitive) url.searchParams.set("case_sensitive", "true");

    const resp = await fetch(url.toString());
    const data = await resp.json();
    const results = Array.isArray(data?.results) ? data.results : [];
    const statusMessage = data?.status_message || "";
    this.renderResults(results, statusMessage);

    this.persistToSession({ q, caseSensitive, results, statusMessage });
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
        const term = this.input.value.trim();
        const occ = Number(r.occurrence_index);
        window.location.href = `/read/${this.bookId}/${r.chapter_order}?q=${encodeURIComponent(term)}&occurrence=${encodeURIComponent(String(occ))}`;
      });

      this.list.appendChild(item);
    }
  }

  async highlightFromUrl(term, occurrenceIndex) {
    const ctx = getReaderContext();
    if (!ctx.bookId || ctx.chapterIndex == null) return;
    const caseSensitive = Boolean(this.caseBox?.checked);

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
