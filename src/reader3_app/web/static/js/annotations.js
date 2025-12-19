(() => {
  function qs(id) {
    return document.getElementById(id);
  }

  function getReaderContext() {
    const parts = window.location.pathname.split("/").filter(Boolean);
    if (parts.length >= 3 && parts[0] === "read") {
      return { bookId: parts[1], chapterIndex: Number(parts[2]) };
    }
    return { bookId: null, chapterIndex: null };
  }

  function clamp(n, min, max) {
    return Math.max(min, Math.min(max, n));
  }

  function showToast(message) {
    const el = document.createElement("div");
    el.textContent = String(message || "");
    el.style.position = "fixed";
    el.style.left = "50%";
    el.style.bottom = "26px";
    el.style.transform = "translateX(-50%)";
    el.style.padding = "10px 12px";
    el.style.background = "rgba(17, 24, 39, 0.92)";
    el.style.color = "rgba(255, 255, 255, 0.92)";
    el.style.borderRadius = "12px";
    el.style.fontFamily = "-apple-system, system-ui, sans-serif";
    el.style.fontSize = "12px";
    el.style.zIndex = "2000";
    el.style.boxShadow = "0 14px 30px rgba(0,0,0,0.22)";
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 1400);
  }

  function clearExistingAnnotationMarks(container) {
    container.querySelectorAll("mark.annotation").forEach((mark) => {
      const parent = mark.parentNode;
      while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
      parent.removeChild(mark);
      parent.normalize();
    });
  }

  function buildTextIndex(container) {
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (!node.nodeValue) return NodeFilter.FILTER_REJECT;
        const parent = node.parentElement;
        if (!parent) return NodeFilter.FILTER_REJECT;
        if (parent.closest("script, style, mark, #annotation-toolbar, #note-editor, #note-tooltip")) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });

    const nodes = [];
    let text = "";
    let pos = 0;
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const value = node.nodeValue || "";
      nodes.push({ node, start: pos, end: pos + value.length });
      text += value;
      pos += value.length;
    }
    return { text, nodes };
  }

  function offsetFromNode(nodes, targetNode, nodeOffset) {
    if (!targetNode) return null;
    const isText = targetNode.nodeType === Node.TEXT_NODE;
    const textNode = isText ? targetNode : null;
    if (textNode) {
      const found = nodes.find((x) => x.node === textNode);
      if (!found) return null;
      return found.start + nodeOffset;
    }
    // If it's an element, attempt to find a nearby text node within it.
    const el = targetNode.nodeType === Node.ELEMENT_NODE ? targetNode : targetNode.parentElement;
    if (!el) return null;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
    let n = walker.nextNode();
    if (!n) return null;
    const found = nodes.find((x) => x.node === n);
    if (!found) return null;
    return found.start;
  }

  function findRange(text, ann) {
    const prefix = String(ann.prefix || "");
    const quote = String(ann.quote || "");
    const suffix = String(ann.suffix || "");
    const combo = `${prefix}${quote}${suffix}`;
    let idx = -1;
    if (prefix || suffix) idx = text.indexOf(combo);
    if (idx !== -1) {
      const start = idx + prefix.length;
      return { start, end: start + quote.length };
    }
    idx = text.indexOf(quote);
    if (idx !== -1) return { start: idx, end: idx + quote.length };
    return null;
  }

  function buildSegments(ranges) {
    const boundaries = new Set();
    for (const r of ranges) {
      boundaries.add(r.start);
      boundaries.add(r.end);
    }
    const sorted = Array.from(boundaries).sort((a, b) => a - b);
    const segments = [];
    for (let i = 0; i < sorted.length - 1; i++) {
      const start = sorted[i];
      const end = sorted[i + 1];
      if (end <= start) continue;
      const covering = ranges.filter((r) => r.start <= start && r.end >= end).map((r) => r.ann);
      if (!covering.length) continue;
      segments.push({ start, end, anns: covering });
    }
    return segments.sort((a, b) => a.start - b.start);
  }

  function segmentStyle(seg) {
    const anns = seg.anns || [];
    const ids = anns.map((a) => String(a.id)).filter(Boolean);

    const notes = anns.filter((a) => a.type === "note");
    const markers = anns.filter((a) => a.type === "marker");
    const wavy = anns.some((a) => a.type === "wavy");
    const underline = anns.some((a) => a.type === "underline");

    let color = null;
    let isNote = false;
    let noteText = null;
    if (notes.length) {
      isNote = true;
      color = notes[notes.length - 1].color || "yellow";
      noteText = notes[notes.length - 1].note_text || null;
    } else if (markers.length) {
      color = markers[markers.length - 1].color || "yellow";
    }

    const classes = ["annotation"];
    if (color) {
      classes.push("annotation--marker", `annotation--${color}`);
    }
    if (wavy) classes.push("annotation--wavy");
    else if (underline) classes.push("annotation--underline");
    if (isNote) classes.push("annotation--note");

    return { classes, ids, noteText };
  }

  function applySegments(container, index, segments) {
    const nodes = index.nodes;
    let segIdx = 0;

    for (const entry of nodes) {
      const nodeStart = entry.start;
      const nodeEnd = entry.end;
      const text = entry.node.nodeValue || "";
      if (!text) continue;

      while (segIdx < segments.length && segments[segIdx].end <= nodeStart) segIdx++;
      let j = segIdx;
      const local = [];
      while (j < segments.length && segments[j].start < nodeEnd) {
        const seg = segments[j];
        const start = Math.max(nodeStart, seg.start);
        const end = Math.min(nodeEnd, seg.end);
        if (end > start) {
          local.push({ start: start - nodeStart, end: end - nodeStart, seg });
        }
        j++;
      }
      if (!local.length) continue;

      local.sort((a, b) => a.start - b.start);
      const frag = document.createDocumentFragment();
      let cursor = 0;
      for (const r of local) {
        if (r.start > cursor) frag.appendChild(document.createTextNode(text.slice(cursor, r.start)));
        const mark = document.createElement("mark");
        const style = segmentStyle(r.seg);
        mark.className = style.classes.join(" ");
        mark.setAttribute("data-annotation-ids", JSON.stringify(style.ids));
        mark.setAttribute("data-annotation-id", style.ids[0] || "");
        if (style.noteText) mark.setAttribute("data-note-text", style.noteText);
        mark.textContent = text.slice(r.start, r.end);
        frag.appendChild(mark);
        cursor = r.end;
      }
      if (cursor < text.length) frag.appendChild(document.createTextNode(text.slice(cursor)));
      entry.node.parentNode.replaceChild(frag, entry.node);
    }
  }

  class AnnotationRenderer {
    constructor(contentEl) {
      this.contentEl = contentEl;
      this.lastAnnotations = [];
    }

    async loadAndRender() {
      const ctx = getReaderContext();
      if (!ctx.bookId || ctx.chapterIndex == null || !this.contentEl) return;
      const resp = await fetch(`/api/notes/${encodeURIComponent(ctx.bookId)}/${encodeURIComponent(String(ctx.chapterIndex))}`);
      const data = await resp.json().catch(() => ({}));
      const anns = Array.isArray(data?.annotations) ? data.annotations : [];
      this.render(anns);
      this.scrollToNoteIdFromUrl();
    }

    render(annotations) {
      clearExistingAnnotationMarks(this.contentEl);
      const idx = buildTextIndex(this.contentEl);

      const ranges = [];
      for (const ann of annotations) {
        const r = findRange(idx.text, ann);
        if (!r) continue;
        ranges.push({ start: r.start, end: r.end, ann });
      }
      if (!ranges.length) return;
      const segments = buildSegments(ranges);
      applySegments(this.contentEl, idx, segments);
    }

    scrollToNoteIdFromUrl() {
      const params = new URLSearchParams(window.location.search);
      const noteId = params.get("note_id");
      if (!noteId) return;
      const marks = Array.from(this.contentEl.querySelectorAll("mark.annotation"));
      let target = null;
      for (const m of marks) {
        const raw = m.getAttribute("data-annotation-ids");
        try {
          const ids = JSON.parse(raw || "[]");
          if (Array.isArray(ids) && ids.includes(noteId)) {
            target = m;
            break;
          }
        } catch {
          // ignore
        }
      }
      if (!target) return;
      target.classList.add("is-jump-target");
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      setTimeout(() => target && target.classList.remove("is-jump-target"), 1400);
    }
  }

  class AnnotationUI {
    constructor(contentEl) {
      this.contentEl = contentEl;
      this.toolbar = qs("annotation-toolbar");
      this.colorRow = qs("anno-color-row");
      this.noteEditor = qs("note-editor");
      this.noteTextarea = qs("note-editor-text");
      this.noteSave = qs("note-editor-save");
      this.noteCancel = qs("note-editor-cancel");
      this.tooltip = qs("note-tooltip");

      this.currentRange = null;
      this.currentIndex = null;
      this.renderer = new AnnotationRenderer(contentEl);
    }

    init() {
      if (!this.contentEl || !this.toolbar) return;

      this.contentEl.addEventListener("mouseup", () => this.onSelection());
      document.addEventListener("mousedown", (e) => {
        const t = e.target;
        if (this.toolbar?.contains(t) || this.noteEditor?.contains(t)) return;
        this.closeSelectionToolbarIfOpen();
      });

      this.toolbar.addEventListener("click", (e) => {
        const btn = e.target.closest("button[data-action]");
        if (!btn) return;
        const action = btn.getAttribute("data-action");
        this.handleAction(action);
      });

      this.colorRow?.addEventListener("click", (e) => {
        const swatch = e.target.closest("button[data-color]");
        if (!swatch) return;
        const color = swatch.getAttribute("data-color");
        this.createAnnotation({ type: "marker", color });
      });

      this.noteSave?.addEventListener("click", () => this.saveNote());
      this.noteCancel?.addEventListener("click", () => this.closeNoteEditorIfOpen());

      this.contentEl.addEventListener("mouseover", (e) => this.onHover(e));
      this.contentEl.addEventListener("mouseout", () => this.hideTooltip());

      this.renderer.loadAndRender().catch(() => {});
    }

    onSelection() {
      if (!this.contentEl) return;
      const sel = window.getSelection();
      if (!sel || sel.rangeCount < 1) return;
      const range = sel.getRangeAt(0);
      if (range.collapsed) return;
      const common = range.commonAncestorContainer;
      const within = common.nodeType === Node.ELEMENT_NODE ? common : common.parentElement;
      if (!within || !within.closest(".book-content")) return;
      this.currentRange = range;

      const rect = range.getBoundingClientRect();
      const x = clamp(rect.left + rect.width / 2, 20, window.innerWidth - 20);
      const y = clamp(rect.top - 12, 20, window.innerHeight - 20);
      this.openToolbarAt(x, y);
    }

    openToolbarAt(x, y) {
      if (!this.toolbar) return;
      this.toolbar.classList.add("is-open");
      this.toolbar.style.left = `${Math.round(x)}px`;
      this.toolbar.style.top = `${Math.round(y)}px`;
      this.toolbar.style.transform = "translate(-50%, -100%)";
      this.hideColorRow();
    }

    closeSelectionToolbarIfOpen() {
      if (!this.toolbar?.classList.contains("is-open")) return false;
      this.toolbar.classList.remove("is-open");
      this.hideColorRow();
      return true;
    }

    showColorRow() {
      this.colorRow?.classList.add("is-open");
    }

    hideColorRow() {
      this.colorRow?.classList.remove("is-open");
    }

    closeNoteEditorIfOpen() {
      if (!this.noteEditor?.classList.contains("is-open")) return false;
      this.noteEditor.classList.remove("is-open");
      if (this.noteTextarea) this.noteTextarea.value = "";
      return true;
    }

    handleAction(action) {
      if (!action) return;
      if (action === "copy") return this.copySelection();
      if (action === "marker") return this.showColorRow();
      if (action === "wavy") return this.createAnnotation({ type: "wavy" });
      if (action === "underline") return this.createAnnotation({ type: "underline" });
      if (action === "note") return this.openNoteEditor();
      if (action === "ask_ai") return this.askAi();
    }

    copySelection() {
      const sel = window.getSelection();
      const text = sel ? String(sel.toString() || "") : "";
      if (!text.trim()) return;
      navigator.clipboard?.writeText?.(text).catch(() => {});
      this.closeSelectionToolbarIfOpen();
    }

    openNoteEditor() {
      if (!this.currentRange || !this.noteEditor) return;
      const rect = this.currentRange.getBoundingClientRect();
      const x = clamp(rect.right + 12, 20, window.innerWidth - 20);
      const y = clamp(rect.top, 20, window.innerHeight - 20);
      this.noteEditor.classList.add("is-open");
      this.noteEditor.style.left = `${Math.round(x)}px`;
      this.noteEditor.style.top = `${Math.round(y)}px`;
      this.noteEditor.style.transform = "translate(0, 0)";
      this.noteTextarea?.focus?.();
    }

    async saveNote() {
      const text = String(this.noteTextarea?.value || "").trim();
      if (!text) return;
      await this.createAnnotation({ type: "note", color: "yellow", note_text: text });
      this.closeNoteEditorIfOpen();
    }

    async createAnnotation(extra) {
      if (!this.currentRange || !this.contentEl) return;
      const ctx = getReaderContext();
      if (!ctx.bookId || ctx.chapterIndex == null) return;

      const idx = buildTextIndex(this.contentEl);
      const start = offsetFromNode(idx.nodes, this.currentRange.startContainer, this.currentRange.startOffset);
      const end = offsetFromNode(idx.nodes, this.currentRange.endContainer, this.currentRange.endOffset);
      if (start == null || end == null) return;
      const s = Math.min(start, end);
      const e = Math.max(start, end);

      const quote = idx.text.slice(s, e);
      const prefix = idx.text.slice(Math.max(0, s - 50), s);
      const suffix = idx.text.slice(e, Math.min(idx.text.length, e + 50));

      const payload = {
        type: extra.type,
        color: extra.color || null,
        quote,
        prefix,
        suffix,
        position: s,
        note_text: extra.note_text || null,
      };

      await fetch(`/api/notes/${encodeURIComponent(ctx.bookId)}/${encodeURIComponent(String(ctx.chapterIndex))}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).catch(() => {});

      this.closeSelectionToolbarIfOpen();
      this.hideColorRow();
      await this.renderer.loadAndRender().catch(() => {});
    }

    askAi() {
      if (!this.currentRange || !this.contentEl) return;
      const ctx = getReaderContext();
      if (!ctx.bookId || ctx.chapterIndex == null) return;

      const quote = String(this.currentRange.toString() || "").trim();
      if (!quote) return;
      const context = String(this.contentEl.textContent || "").slice(0, 2000);
      const event = new CustomEvent("reader3:ai:ask", {
        detail: { book_id: ctx.bookId, chapter_index: ctx.chapterIndex, quote, context },
      });
      window.dispatchEvent(event);
      if (!window.Reader3AIAskEnabled) showToast("AI 面板未启用/未加载");
      this.closeSelectionToolbarIfOpen();
    }

    onHover(e) {
      const target = e.target.closest("mark.annotation.annotation--note");
      if (!target) return;
      const text = target.getAttribute("data-note-text");
      if (!text) return;
      this.showTooltip(text, target.getBoundingClientRect());
    }

    showTooltip(text, rect) {
      if (!this.tooltip) return;
      this.tooltip.textContent = text;
      const x = clamp(rect.left + rect.width / 2, 20, window.innerWidth - 20);
      const y = clamp(rect.top - 10, 20, window.innerHeight - 20);
      this.tooltip.classList.add("is-open");
      this.tooltip.style.left = `${Math.round(x)}px`;
      this.tooltip.style.top = `${Math.round(y)}px`;
      this.tooltip.style.transform = "translate(-50%, -100%)";
    }

    hideTooltip() {
      this.tooltip?.classList.remove("is-open");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const contentEl = document.querySelector(".book-content");
    if (!contentEl) return;
    const ui = new AnnotationUI(contentEl);
    ui.init();
    window.Reader3AnnotationUI = ui;
  });
})();
