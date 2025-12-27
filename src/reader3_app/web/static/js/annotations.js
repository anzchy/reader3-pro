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
        if (parent.closest("script, style, #annotation-toolbar, #note-editor, #note-tooltip")) return NodeFilter.FILTER_REJECT;
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

  function getEventTargetElement(target) {
    if (!target) return null;
    if (target.nodeType === Node.TEXT_NODE) return target.parentElement;
    if (target.nodeType === Node.ELEMENT_NODE) return target;
    return null;
  }

  function elementDebugInfo(el) {
    if (!el) return null;
    let style = null;
    try {
      style = window.getComputedStyle(el);
    } catch {
      style = null;
    }
    return {
      tag: el.tagName,
      id: el.id || "",
      className: typeof el.className === "string" ? el.className : "",
      pointerEvents: style ? style.pointerEvents : "",
      position: style ? style.position : "",
      zIndex: style ? style.zIndex : "",
    };
  }

  function dedupeAnnotationMeta(items) {
    const out = [];
    const seen = new Set();
    for (const item of items || []) {
      const id = String(item?.id || "");
      if (!id || seen.has(id)) continue;
      seen.add(id);
      out.push({
        id,
        type: item?.type || null,
        color: item?.color || null,
        note_text: item?.note_text ?? null,
      });
    }
    return out;
  }

  function segmentStyle(seg) {
    const anns = seg.anns || [];
    const meta = anns
      .map((a) => ({
        id: String(a.id),
        type: a.type,
        color: a.color || null,
        note_text: a.note_text ?? null,
      }))
      .filter((item) => item.id);
    const ids = meta.map((item) => item.id);

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

    return { classes, ids, meta, noteText };
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
        mark.setAttribute("data-annotation-meta", JSON.stringify(style.meta || []));
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
      this.currentAnnotationMeta = [];
      this.currentAnnotationIds = [];
      this.editingNoteId = null;
      this.renderer = new AnnotationRenderer(contentEl);
    }

    init() {
      if (!this.contentEl || !this.toolbar) return;

      console.log("[Annotations] init", { hasContent: !!this.contentEl, hasToolbar: !!this.toolbar });

      document.addEventListener("click", (e) => {
        const elements = document.elementsFromPoint(e.clientX, e.clientY) || [];
        const slice = elements.slice(0, 8).map((el) => elementDebugInfo(el));
        console.log("[Annotations] elementsFromPoint", {
          x: e.clientX,
          y: e.clientY,
          count: elements.length,
          top: slice,
        });
      }, true);

      this.contentEl.addEventListener("mouseup", () => this.onSelection());
      this.contentEl.addEventListener("click", (e) => {
        const target = getEventTargetElement(e.target);
        const mark = target?.closest ? target.closest("mark.annotation") : null;
        const tagName = target?.tagName || "unknown";
        const className = target?.className || "";
        const nodeType = target?.nodeType || e.target?.nodeType;
        console.log("[Annotations] content click", { tagName, className, nodeType, hasMark: !!mark });
      }, true);
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
        this.toggleMarkerAnnotation(color);
      });

      this.noteSave?.addEventListener("click", () => this.saveNote());
      this.noteCancel?.addEventListener("click", () => this.closeNoteEditorIfOpen());

      this.contentEl.addEventListener("mouseover", (e) => this.onHover(e));
      this.contentEl.addEventListener("mouseout", () => this.hideTooltip());

      // Click on annotated text to select and show toolbar
      this.contentEl.addEventListener("click", (e) => this.onAnnotationClick(e));

      this.renderer.loadAndRender().catch(() => {});
    }

    setCurrentAnnotations(meta) {
      const deduped = dedupeAnnotationMeta(meta);
      this.currentAnnotationMeta = deduped;
      this.currentAnnotationIds = deduped.map((item) => item.id);
    }

    getAnnotationMetaFromMark(mark) {
      if (!mark) return [];
      const rawMeta = mark.getAttribute("data-annotation-meta");
      if (rawMeta) {
        try {
          const parsed = JSON.parse(rawMeta || "[]");
          if (Array.isArray(parsed)) return dedupeAnnotationMeta(parsed);
        } catch {
          // ignore
        }
      }
      const rawIds = mark.getAttribute("data-annotation-ids");
      try {
        const parsedIds = JSON.parse(rawIds || "[]");
        if (Array.isArray(parsedIds)) {
          return dedupeAnnotationMeta(parsedIds.map((id) => ({ id })));
        }
      } catch {
        // ignore
      }
      return [];
    }

    getAnnotationMetaForRange(range) {
      if (!range || !this.contentEl) return [];
      const marks = this.contentEl.querySelectorAll("mark.annotation");
      const meta = [];
      for (const mark of marks) {
        if (!range.intersectsNode(mark)) continue;
        meta.push(...this.getAnnotationMetaFromMark(mark));
      }
      return dedupeAnnotationMeta(meta);
    }

    /**
     * Handle click on annotated text
     */
    onAnnotationClick(e) {
      const target = getEventTargetElement(e.target);
      const mark = target?.closest ? target.closest("mark.annotation") : null;
      console.log("[Annotations] onAnnotationClick", { hasMark: !!mark });
      if (!mark) return;

      const sel = window.getSelection();
      console.log("[Annotations] selection", { text: sel ? sel.toString() : "" });

      // Get annotation info and meta
      const meta = this.getAnnotationMetaFromMark(mark);
      console.log("[Annotations] mark meta", meta);
      this.setCurrentAnnotations(meta);
      this.editingNoteId = null;

      // Select the text in the mark element
      if (sel) {
        const range = document.createRange();
        range.selectNodeContents(mark);
        sel.removeAllRanges();
        sel.addRange(range);
        this.currentRange = range;
      }
      console.log("[Annotations] range set", { hasRange: !!this.currentRange });

      // Position and show toolbar
      const rect = mark.getBoundingClientRect();
      const toolbarHalfWidth = 200;
      const x = clamp(rect.left + rect.width / 2, 20 + toolbarHalfWidth, window.innerWidth - 20 - toolbarHalfWidth);
      const y = clamp(rect.top - 12, 60, window.innerHeight - 20);
      this.openToolbarAt(x, y);
      console.log("[Annotations] toolbar opened", { x, y });

      // If it has a note, open note editor with existing content
      const noteMeta = meta.find((item) => item.type === "note");
      const noteText = noteMeta?.note_text || mark.getAttribute("data-note-text") || "";
      if (noteMeta && noteText) {
        this.openNoteEditorWithExisting(noteText, noteMeta.id);
        console.log("[Annotations] note editor opened", { noteId: noteMeta.id });
      }

      e.preventDefault();
      e.stopPropagation();
    }

    /**
     * Open note editor with existing note content for editing
     */
    openNoteEditorWithExisting(noteText, noteId) {
      if (!this.noteEditor || !this.noteTextarea) return;

      // Store the annotation IDs being edited
      this.editingNoteId = noteId;

      // Set the existing note text
      this.noteTextarea.value = noteText;

      // Position the note editor
      const sel = window.getSelection();
      if (!sel || sel.rangeCount < 1) return;
      const range = sel.getRangeAt(0);
      const rect = range.getBoundingClientRect();

      const editorWidth = 320;
      const editorHeight = 180;

      let x = rect.right + 12;
      if (x + editorWidth > window.innerWidth - 20) {
        x = rect.left - editorWidth - 12;
      }
      x = clamp(x, 20, window.innerWidth - editorWidth - 20);

      let y = rect.top;
      if (y + editorHeight > window.innerHeight - 20) {
        y = window.innerHeight - editorHeight - 20;
      }
      y = clamp(y, 20, window.innerHeight - editorHeight - 20);

      this.noteEditor.classList.add("is-visible");
      this.noteEditor.setAttribute("aria-hidden", "false");
      this.noteEditor.style.left = `${Math.round(x)}px`;
      this.noteEditor.style.top = `${Math.round(y)}px`;
      this.noteEditor.style.transform = "translate(0, 0)";
      this.noteTextarea.focus();
    }

    /**
     * Toggle marker annotation with specific color
     */
    async toggleMarkerAnnotation(color) {
      if (!this.currentRange || !this.contentEl) return;

      // Check if there's existing marker annotation with same color
      const existingIds = this.getExistingMarkerIds(color);

      if (existingIds.length > 0) {
        // Delete existing marker annotations
        console.log('[Annotations] Removing existing markers:', existingIds);
        await this.deleteAnnotations(existingIds);
      } else {
        // Create new marker annotation
        console.log('[Annotations] Creating new marker:', color);
        await this.createAnnotation({ type: "marker", color });
      }
    }

    /**
     * Get IDs of existing marker annotations with specific color
     */
    getExistingMarkerIds(color) {
      return this.getExistingAnnotationIds("marker", color);
    }

    onSelection() {
      console.log('[Annotations] onSelection triggered');
      if (!this.contentEl) {
        console.log('[Annotations] contentEl not found');
        return;
      }
      const sel = window.getSelection();
      console.log('[Annotations] Selection object:', sel);
      if (!sel || sel.rangeCount < 1) {
        console.log('[Annotations] No selection or rangeCount < 1');
        return;
      }
      const range = sel.getRangeAt(0);
      console.log('[Annotations] Range:', range, 'collapsed:', range.collapsed);
      if (range.collapsed) {
        console.log('[Annotations] Range is collapsed, ignoring');
        return;
      }
      const common = range.commonAncestorContainer;
      const within = common.nodeType === Node.ELEMENT_NODE ? common : common.parentElement;
      console.log('[Annotations] Common ancestor:', common, 'Within element:', within);
      if (!within || !within.closest(".book-content")) {
        console.log('[Annotations] Selection not within .book-content');
        return;
      }
      this.currentRange = range;
      this.setCurrentAnnotations(this.getAnnotationMetaForRange(range));
      this.editingNoteId = null;

      const rect = range.getBoundingClientRect();
      console.log('[Annotations] Selection rect:', rect);
      // Horizontal toolbar is approximately 400px wide, centered via transform
      const toolbarHalfWidth = 200;
      const x = clamp(rect.left + rect.width / 2, 20 + toolbarHalfWidth, window.innerWidth - 20 - toolbarHalfWidth);
      const y = clamp(rect.top - 12, 60, window.innerHeight - 20);
      console.log('[Annotations] Positioning toolbar at:', x, y);
      this.openToolbarAt(x, y);
    }

    openToolbarAt(x, y) {
      if (!this.toolbar) return;
      this.toolbar.classList.add("is-visible");
      this.toolbar.style.left = `${Math.round(x)}px`;
      this.toolbar.style.top = `${Math.round(y)}px`;
      this.toolbar.style.transform = "translate(-50%, -100%)";
      this.hideColorRow();
    }

    closeSelectionToolbarIfOpen() {
      if (!this.toolbar?.classList.contains("is-visible")) return false;
      this.toolbar.classList.remove("is-visible");
      this.hideColorRow();
      return true;
    }

    showColorRow() {
      this.colorRow?.classList.add("is-visible");
    }

    hideColorRow() {
      this.colorRow?.classList.remove("is-visible");
    }

    closeNoteEditorIfOpen() {
      if (!this.noteEditor?.classList.contains("is-visible")) return false;
      this.noteEditor.classList.remove("is-visible");
      this.noteEditor.setAttribute("aria-hidden", "true");
      if (this.noteTextarea) this.noteTextarea.value = "";
      this.editingNoteId = null;
      return true;
    }

    handleAction(action) {
      console.log('[Annotations] handleAction called with:', action);
      if (!action) return;
      if (action === "copy") return this.copySelection();
      if (action === "marker") return this.showColorRow();
      if (action === "wavy") {
        console.log('[Annotations] Toggle wavy annotation');
        return this.toggleAnnotation("wavy");
      }
      if (action === "underline") {
        console.log('[Annotations] Toggle underline annotation');
        return this.toggleAnnotation("underline");
      }
      if (action === "note") return this.openNoteEditor();
      if (action === "ask_ai") return this.askAi();
      if (action === "delete") return this.deleteCurrentAnnotation();
    }

    /**
     * Toggle annotation: if same type exists at selection, remove it; otherwise create new
     */
    async toggleAnnotation(type) {
      if (!this.currentRange || !this.contentEl) return;

      // Check if there are existing annotations of this type covering the selection
      const existingIds = this.getExistingAnnotationIds(type);

      if (existingIds.length > 0) {
        // Delete existing annotations of this type
        console.log('[Annotations] Removing existing annotations:', existingIds);
        await this.deleteAnnotations(existingIds);
      } else {
        // Create new annotation
        console.log('[Annotations] Creating new annotation:', type);
        await this.createAnnotation({ type });
      }
    }

    /**
     * Get IDs of existing annotations of given type that cover current selection
     */
    getExistingAnnotationIds(type, color = null) {
      if (!this.currentRange) return [];

      const meta = this.getAnnotationMetaForRange(this.currentRange);
      const filtered = meta.filter((item) => {
        if (item.type !== type) return false;
        if (color && item.color !== color) return false;
        return true;
      });
      return filtered.map((item) => item.id);
    }

    /**
     * Delete annotations by IDs
     */
    async deleteAnnotations(ids) {
      const uniqueIds = [...new Set(ids)].filter(Boolean);
      if (!uniqueIds.length) return;

      const ctx = getReaderContext();
      if (!ctx.bookId || ctx.chapterIndex == null) return;

      for (const id of uniqueIds) {
        await fetch(`/api/notes/${encodeURIComponent(ctx.bookId)}/${encodeURIComponent(String(ctx.chapterIndex))}/${encodeURIComponent(id)}`, {
          method: "DELETE",
        }).catch(() => {});
      }

      this.closeSelectionToolbarIfOpen();
      this.hideColorRow();
      await this.renderer.loadAndRender().catch(() => {});
      this.setCurrentAnnotations([]);
      window.dispatchEvent(new CustomEvent("reader3:annotations:updated"));
    }

    /**
     * Delete the currently selected/clicked annotation
     */
    async deleteCurrentAnnotation() {
      let meta = this.currentAnnotationMeta || [];
      if (!meta.length && this.currentRange) {
        meta = this.getAnnotationMetaForRange(this.currentRange);
      }
      const ids = meta.map((item) => item.id).filter(Boolean);
      if (!ids.length) return;
      await this.deleteAnnotations(ids);
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
      this.editingNoteId = null;
      const rect = this.currentRange.getBoundingClientRect();
      const editorWidth = 320; // matches CSS width
      const editorHeight = 180; // approximate height

      // Try positioning to the right of selection
      let x = rect.right + 12;
      // If would overflow right, position to left of selection
      if (x + editorWidth > window.innerWidth - 20) {
        x = rect.left - editorWidth - 12;
      }
      // Clamp to stay within viewport
      x = clamp(x, 20, window.innerWidth - editorWidth - 20);

      // Position vertically, ensuring it stays in viewport
      let y = rect.top;
      if (y + editorHeight > window.innerHeight - 20) {
        y = window.innerHeight - editorHeight - 20;
      }
      y = clamp(y, 20, window.innerHeight - editorHeight - 20);

      this.noteEditor.classList.add("is-visible");
      this.noteEditor.setAttribute("aria-hidden", "false");
      this.noteEditor.style.left = `${Math.round(x)}px`;
      this.noteEditor.style.top = `${Math.round(y)}px`;
      this.noteEditor.style.transform = "translate(0, 0)";
      this.noteTextarea?.focus?.();
    }

    async saveNote() {
      const text = String(this.noteTextarea?.value || "").trim();
      if (!text) return;

      // If editing an existing note, update it
      if (this.editingNoteId) {
        const ctx = getReaderContext();
        if (ctx.bookId && ctx.chapterIndex != null) {
          await fetch(`/api/notes/${encodeURIComponent(ctx.bookId)}/${encodeURIComponent(String(ctx.chapterIndex))}/${encodeURIComponent(this.editingNoteId)}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ note_text: text }),
          }).catch(() => {});

          this.editingNoteId = null;
          this.closeNoteEditorIfOpen();
          this.closeSelectionToolbarIfOpen();
          await this.renderer.loadAndRender().catch(() => {});
          window.dispatchEvent(new CustomEvent("reader3:annotations:updated"));
          return;
        }
      }

      // Otherwise create a new note annotation
      await this.createAnnotation({ type: "note", color: "yellow", note_text: text });
      this.closeNoteEditorIfOpen();
    }

    async createAnnotation(extra) {
      console.log('[Annotations] createAnnotation called with:', extra);
      if (!this.currentRange || !this.contentEl) {
        console.log('[Annotations] createAnnotation: missing currentRange or contentEl');
        return;
      }
      const ctx = getReaderContext();
      if (!ctx.bookId || ctx.chapterIndex == null) {
        console.log('[Annotations] createAnnotation: missing bookId or chapterIndex');
        return;
      }

      const idx = buildTextIndex(this.contentEl);
      const start = offsetFromNode(idx.nodes, this.currentRange.startContainer, this.currentRange.startOffset);
      const end = offsetFromNode(idx.nodes, this.currentRange.endContainer, this.currentRange.endOffset);
      if (start == null || end == null) {
        console.log('[Annotations] createAnnotation: could not calculate start/end positions');
        return;
      }
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
      console.log('[Annotations] createAnnotation: sending payload:', payload);

      const resp = await fetch(`/api/notes/${encodeURIComponent(ctx.bookId)}/${encodeURIComponent(String(ctx.chapterIndex))}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).catch((err) => { console.error('[Annotations] createAnnotation fetch error:', err); });
      console.log('[Annotations] createAnnotation: response:', resp);

      this.closeSelectionToolbarIfOpen();
      this.hideColorRow();
      await this.renderer.loadAndRender().catch(() => {});

      // Notify notes panel to refresh
      window.dispatchEvent(new CustomEvent("reader3:annotations:updated"));
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
      const target = getEventTargetElement(e.target);
      const mark = target?.closest ? target.closest("mark.annotation.annotation--note") : null;
      if (!mark) return;
      const text = mark.getAttribute("data-note-text");
      if (!text) return;
      this.showTooltip(text, mark.getBoundingClientRect());
    }

    showTooltip(text, rect) {
      if (!this.tooltip) return;
      this.tooltip.textContent = text;
      const x = clamp(rect.left + rect.width / 2, 20, window.innerWidth - 20);
      const y = clamp(rect.top - 10, 20, window.innerHeight - 20);
      this.tooltip.classList.add("is-visible");
      this.tooltip.style.left = `${Math.round(x)}px`;
      this.tooltip.style.top = `${Math.round(y)}px`;
      this.tooltip.style.transform = "translate(-50%, -100%)";
    }

    hideTooltip() {
      this.tooltip?.classList.remove("is-visible");
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
