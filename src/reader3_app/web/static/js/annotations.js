(() => {
  let globalListenersBound = false;
  let toolbarListenersBound = false;
  let renditionListenersBound = false;

  function qs(id) {
    return document.getElementById(id);
  }

  function getReaderContext() {
    const ctx = window.Reader3Ctx || {};
    if (ctx.bookId && Number.isFinite(ctx.chapterIndex)) {
      return { bookId: ctx.bookId, chapterIndex: Number(ctx.chapterIndex) };
    }
    const parts = window.location.pathname.split("/").filter(Boolean);
    if (parts.length >= 3 && parts[0] === "read") {
      return { bookId: parts[1], chapterIndex: Number(parts[2]) };
    }
    return { bookId: null, chapterIndex: null };
  }

  function clamp(n, min, max) {
    return Math.max(min, Math.min(max, n));
  }

  // ---- 011 WI-5b：notes 乐观并发的客户端半边 -----------------------------------------
  //
  // 版本的粒度是**整本书**的标注列表（服务端 `routers/notes.py` 的 `_etag()` 包的是
  // `annotations_version(整份 annotations)`），不是单条、也不是单章 —— 所以这里只存一个
  // 值，不按章、不按 id 分桶。读的时候原样记下，写的时候原样带上，**前端一次比较都不做**：
  // compare-and-swap 在服务端的书级锁里，前端比出来的结论在请求飞出去的那一刻就已经过期。
  //
  // `If-Match` 一律「有就带、没有就不带」。不带它的写与乐观并发落地之前逐字节同构
  // （ADR-0011），所以「页面还没读过任何 ETag 就先写」不会被误判成冲突。
  let notesEtag = null;

  function rememberNotesEtag(resp) {
    const tag = resp?.headers?.get?.("ETag");
    if (tag) notesEtag = tag;
  }

  function notesWriteHeaders(extra) {
    const headers = Object.assign({}, extra || {});
    if (notesEtag) headers["If-Match"] = notesEtag;
    return headers;
  }

  /**
   * 带版本写一次；撞 409 就吸收服务端回来的版本再写一次。
   *
   * 只给**建**与**删**用。这两种写没有「两版正文二选一」可言（建冲突时 409 体里的
   * `annotation` 本来就是 `null`），它们撞 409 的原因是本书**别的**标注动了；不重试的话，
   * 「连点两下删」的第二下会带着过期版本静默失败 —— 那是本次改动**引入**的坏法，不是它要
   * 治的那个。**改**不走这里：正文冲突必须浮到 DEG-S5 的对话框上由用户二选一。
   */
  async function notesWriteWithResync(url, init) {
    const send = () =>
      fetch(url, Object.assign({}, init, { headers: notesWriteHeaders(init?.headers) })).catch(() => null);
    let resp = await send();
    if (resp && resp.status === 409) {
      const body = await resp.json().catch(() => null);
      if (body?.etag) notesEtag = body.etag;
      resp = await send();
    }
    rememberNotesEtag(resp);
    return resp;
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
    const doc = container?.ownerDocument || document;
    const walker = doc.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
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
    const doc = el?.ownerDocument || document;
    const walker = doc.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
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

  function offsetRect(rect, frameEl) {
    if (!rect) return rect;
    if (!frameEl) return rect;
    const frameRect = frameEl.getBoundingClientRect();
    return {
      left: rect.left + frameRect.left,
      right: rect.right + frameRect.left,
      top: rect.top + frameRect.top,
      bottom: rect.bottom + frameRect.top,
      width: rect.width,
      height: rect.height,
    };
  }

  function elementDebugInfo(el) {
    if (!el) return null;
    let style = null;
    try {
      const view = el.ownerDocument?.defaultView || window;
      style = view.getComputedStyle(el);
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
    let colorSource = null;
    let isNote = false;
    let noteText = null;
    if (notes.length) {
      isNote = true;
      color = notes[notes.length - 1].color || "yellow";
      colorSource = "note";
      noteText = notes[notes.length - 1].note_text || null;
    } else if (markers.length) {
      color = markers[markers.length - 1].color || "yellow";
      colorSource = "marker";
    } else if (wavy || underline) {
      const styled = anns.filter((a) => a.type === "wavy" || a.type === "underline");
      const last = styled[styled.length - 1];
      color = last?.color || "yellow";
      colorSource = last?.type || "underline";
    }

    const classes = ["annotation"];
    if (color) {
      if (colorSource === "marker" || colorSource === "note") {
        classes.push("annotation--marker");
      }
      classes.push(`annotation--${color}`);
    }
    if (wavy) classes.push("annotation--wavy");
    else if (underline) classes.push("annotation--underline");
    if (isNote) classes.push("annotation--note");

    return { classes, ids, meta, noteText };
  }

  function rangeFromCfi(cfi, contents, doc) {
    if (!cfi) return null;
    if (contents && typeof contents.range === "function") {
      try {
        const range = contents.range(cfi);
        if (range) return range;
      } catch {
        // ignore
      }
    }
    if (window.ePub && window.ePub.CFI && doc) {
      try {
        const cfiObj = new window.ePub.CFI(cfi);
        return cfiObj.toRange(doc);
      } catch {
        // ignore
      }
    }
    return null;
  }

  function applySegments(container, index, segments) {
    const nodes = index.nodes;
    const doc = container?.ownerDocument || document;
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
      const frag = doc.createDocumentFragment();
      let cursor = 0;
      for (const r of local) {
        if (r.start > cursor) frag.appendChild(doc.createTextNode(text.slice(cursor, r.start)));
        const mark = doc.createElement("mark");
        const style = segmentStyle(r.seg);
        mark.className = style.classes.join(" ");
        mark.setAttribute("data-testid", "rd-anno-span");
        mark.setAttribute("data-annotation-ids", JSON.stringify(style.ids));
        mark.setAttribute("data-annotation-id", style.ids[0] || "");
        if (style.noteText) mark.setAttribute("data-note-text", style.noteText);
        mark.textContent = text.slice(r.start, r.end);
        mark.setAttribute("data-annotation-meta", JSON.stringify(style.meta || []));
        frag.appendChild(mark);
        cursor = r.end;
      }
      if (cursor < text.length) frag.appendChild(doc.createTextNode(text.slice(cursor)));
      entry.node.parentNode.replaceChild(frag, entry.node);
    }
  }

  class AnnotationRenderer {
    constructor(contentEl, getContents) {
      this.contentEl = contentEl;
      this.lastAnnotations = [];
      this.getContents = typeof getContents === "function" ? getContents : null;
    }

    async loadAndRender() {
      const ctx = getReaderContext();
      if (!this.contentEl && this.getContents) {
        const contents = this.getContents();
        if (contents?.document?.body) {
          this.contentEl = contents.document.body;
        }
      }
      if (!ctx.bookId || ctx.chapterIndex == null || !this.contentEl) return;
      const resp = await fetch(`/api/notes/${encodeURIComponent(ctx.bookId)}/${encodeURIComponent(String(ctx.chapterIndex))}`);
      // 读到的 ETag 就是随后每一次写要带的 `If-Match`。章级与书级两条读路由给的是同一个
      // 值（整本书标注的版本），所以记在哪一次读上都一样。
      rememberNotesEtag(resp);
      const data = await resp.json().catch(() => ({}));
      const anns = Array.isArray(data?.annotations) ? data.annotations : [];
      this.render(anns);
      this.scrollToNoteIdFromUrl();
    }

    render(annotations) {
      const contents = this.getContents ? this.getContents() : null;
      if (contents?.document?.body && this.contentEl?.ownerDocument !== contents.document) {
        this.contentEl = contents.document.body;
      }
      if (!this.contentEl) return;
      clearExistingAnnotationMarks(this.contentEl);
      const doc = this.contentEl?.ownerDocument || document;

      const textAnnotations = [];
      const cfiAnnotations = annotations.filter((ann) => ann?.cfi);
      for (const ann of cfiAnnotations) {
        const range = rangeFromCfi(String(ann.cfi || ""), contents, doc);
        if (!range) {
          textAnnotations.push(ann);
          continue;
        }
        const style = segmentStyle({ anns: [ann] });
        const mark = doc.createElement("mark");
        mark.className = style.classes.join(" ");
        mark.setAttribute("data-testid", "rd-anno-span");
        mark.setAttribute("data-annotation-ids", JSON.stringify(style.ids));
        mark.setAttribute("data-annotation-id", style.ids[0] || "");
        if (style.noteText) mark.setAttribute("data-note-text", style.noteText);
        mark.setAttribute("data-annotation-meta", JSON.stringify(style.meta || []));
        try {
          const fragment = range.extractContents();
          mark.appendChild(fragment);
          range.insertNode(mark);
        } catch (err) {
          console.warn("[Annotations] failed to wrap CFI range, falling back to text match", err);
          textAnnotations.push(ann);
        }
      }

      textAnnotations.push(...annotations.filter((ann) => !ann?.cfi));
      if (!textAnnotations.length) return;

      const idx = buildTextIndex(this.contentEl);
      const ranges = [];
      for (const ann of textAnnotations) {
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
    constructor(contentEl, frameEl) {
      this.contentEl = contentEl;
      this.frameEl = frameEl || null;
      this.contentDocument = contentEl?.ownerDocument || document;
      this.contentWindow = this.contentDocument?.defaultView || window;
      this.toolbar = qs("annotation-toolbar");
      this.colorRow = qs("anno-color-row");
      this.noteEditor = qs("note-editor");
      this.noteTextarea = qs("note-editor-text");
      this.noteSave = qs("note-editor-save");
      this.noteCancel = qs("note-editor-cancel");
      this.tooltip = qs("note-tooltip");
      this.conflictDialog = qs("note-conflict-dialog");
      this.conflictLocal = qs("note-conflict-local");
      this.conflictRemote = qs("note-conflict-remote");
      this.conflictKeepMine = qs("note-conflict-keep-mine");
      this.conflictTakeRemote = qs("note-conflict-take-remote");
      this.pendingConflict = null;

      this.currentRange = null;
      this.currentIndex = null;
      this.currentAnnotationMeta = [];
      this.currentAnnotationIds = [];
      this.editingNoteId = null;
      this.lastSelectionAt = 0;
      this.selectedColor = "yellow";
      this.renderer = new AnnotationRenderer(contentEl, () => window.Reader3Epub?.getContents?.());
    }

    init() {
      if (!this.contentEl || !this.toolbar) return;

      console.log("[Annotations] init", { hasContent: !!this.contentEl, hasToolbar: !!this.toolbar });

      if (!globalListenersBound) {
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

        document.addEventListener("mousedown", (e) => {
          const t = e.target;
          if (this.toolbar?.contains(t) || this.noteEditor?.contains(t)) return;
          this.closeSelectionToolbarIfOpen();
        });

        globalListenersBound = true;
      }

      this.contentDocument.addEventListener("mouseup", () => this.onSelection());
      this.contentDocument.addEventListener("click", (e) => {
        const target = getEventTargetElement(e.target);
        const mark = target?.closest ? target.closest("mark.annotation") : null;
        const tagName = target?.tagName || "unknown";
        const className = target?.className || "";
        const nodeType = target?.nodeType || e.target?.nodeType;
        console.log("[Annotations] content click", { tagName, className, nodeType, hasMark: !!mark });

        const elements = this.contentDocument.elementsFromPoint?.(e.clientX, e.clientY) || [];
        const slice = elements.slice(0, 8).map((el) => elementDebugInfo(el));
        console.log("[Annotations] iframe elementsFromPoint", {
          x: e.clientX,
          y: e.clientY,
          count: elements.length,
          top: slice,
        });
      }, true);
      if (!toolbarListenersBound) {
        this.toolbar.addEventListener("click", (e) => {
          const btn = e.target.closest("button[data-action]");
          if (!btn) return;
          const action = btn.getAttribute("data-action");
          window.Reader3AnnotationUI?.handleAction?.(action);
        });

        this.colorRow?.addEventListener("click", (e) => {
          const swatch = e.target.closest("button[data-color]");
          if (!swatch) return;
          const color = swatch.getAttribute("data-color");
          window.Reader3AnnotationUI?.setSelectedColor?.(color);
        });

        this.noteSave?.addEventListener("click", () => window.Reader3AnnotationUI?.saveNote?.());
        this.noteCancel?.addEventListener("click", () => window.Reader3AnnotationUI?.closeNoteEditorIfOpen?.());
        this.setupConflictDialog();

        toolbarListenersBound = true;
      }

      if (!renditionListenersBound && window.Reader3Epub?.rendition) {
        window.Reader3Epub.rendition.on("selected", (cfiRange, contents) => {
          window.Reader3AnnotationUI?.handleRenditionSelection?.(cfiRange, contents);
        });
        renditionListenersBound = true;
      }

      this.contentDocument.addEventListener("mousedown", (e) => {
        const t = e.target;
        if (this.toolbar?.contains(t) || this.noteEditor?.contains(t)) return;
        this.closeSelectionToolbarIfOpen();
      });

      this.contentDocument.addEventListener("mouseover", (e) => this.onHover(e));
      this.contentDocument.addEventListener("mouseout", () => this.hideTooltip());

      // Click on annotated text to select and show toolbar
      this.contentDocument.addEventListener("click", (e) => this.onAnnotationClick(e));

      this.syncSelectedColor();
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

      const sel = this.contentWindow?.getSelection?.();
      console.log("[Annotations] selection", { text: sel ? sel.toString() : "" });

      // Get annotation info and meta
      const meta = this.getAnnotationMetaFromMark(mark);
      console.log("[Annotations] mark meta", meta);
      this.setCurrentAnnotations(meta);
      this.editingNoteId = null;

      // Select the text in the mark element
      if (sel) {
        const range = this.contentDocument.createRange();
        range.selectNodeContents(mark);
        sel.removeAllRanges();
        sel.addRange(range);
        this.currentRange = range;
      }
      console.log("[Annotations] range set", { hasRange: !!this.currentRange });

      // Position and show toolbar
      const rect = offsetRect(mark.getBoundingClientRect(), this.frameEl);
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
      const sel = this.contentWindow?.getSelection?.();
      if (!sel || sel.rangeCount < 1) return;
      const range = sel.getRangeAt(0);
      const rect = offsetRect(range.getBoundingClientRect(), this.frameEl);

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

      const selected = color || this.selectedColor || "yellow";
      // Check if there's existing marker annotation with same color
      const existingIds = this.getExistingMarkerIds(selected);

      if (existingIds.length > 0) {
        // Delete existing marker annotations
        console.log('[Annotations] Removing existing markers:', existingIds);
        await this.deleteAnnotations(existingIds);
      } else {
        // Create new marker annotation
        console.log('[Annotations] Creating new marker:', selected);
        await this.createAnnotation({ type: "marker", color: selected });
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
      const sel = this.contentWindow?.getSelection?.();
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
      if (Date.now() - this.lastSelectionAt < 120) return;
      this.handleSelectionRange(range);
    }

    handleRenditionSelection(cfiRange, contents) {
      if (!cfiRange) return;
      const doc = contents?.document || this.contentDocument;
      if (contents?.document) {
        this.contentDocument = contents.document;
        this.contentWindow = contents.document.defaultView || window;
        if (contents.document.body) {
          this.contentEl = contents.document.body;
        }
        if (contents.document.defaultView?.frameElement) {
          this.frameEl = contents.document.defaultView.frameElement;
        }
        if (this.renderer) {
          this.renderer.contentEl = this.contentEl;
        }
      }
      const range = rangeFromCfi(String(cfiRange), contents, doc);
      if (!range) return;
      const sel = doc?.defaultView?.getSelection?.();
      if (sel) {
        sel.removeAllRanges();
        sel.addRange(range);
      }
      this.lastSelectionAt = Date.now();
      this.handleSelectionRange(range);
    }

    handleSelectionRange(range) {
      if (!range || !this.contentEl) return;
      const rangeDoc = range.commonAncestorContainer?.ownerDocument || this.contentDocument;
      if (rangeDoc && this.contentDocument !== rangeDoc) {
        this.contentDocument = rangeDoc;
        this.contentWindow = rangeDoc.defaultView || window;
      }
      if (!this.contentEl || (rangeDoc && this.contentEl.ownerDocument !== rangeDoc)) {
        this.contentEl = rangeDoc?.body || this.contentEl;
        if (rangeDoc?.defaultView?.frameElement) {
          this.frameEl = rangeDoc.defaultView.frameElement;
        }
        if (this.renderer) {
          this.renderer.contentEl = this.contentEl;
        }
      }
      const common = range.commonAncestorContainer;
      const within = common.nodeType === Node.ELEMENT_NODE ? common : common.parentElement;
      console.log('[Annotations] Common ancestor:', common, 'Within element:', within, {
        contentEl: this.contentEl?.tagName || null,
        sameDoc: within?.ownerDocument === this.contentEl?.ownerDocument,
      });
      if (!within || !this.contentEl || !this.contentEl.contains(within)) {
        console.log('[Annotations] Selection not within content container');
        return;
      }
      this.currentRange = range;
      this.setCurrentAnnotations(this.getAnnotationMetaForRange(range));
      this.editingNoteId = null;

      const rect = offsetRect(range.getBoundingClientRect(), this.frameEl);
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
      this.syncSelectedColor();
    }

    closeSelectionToolbarIfOpen() {
      if (!this.toolbar?.classList.contains("is-visible")) return false;
      this.toolbar.classList.remove("is-visible");
      return true;
    }

    setSelectedColor(color) {
      if (!color) return;
      this.selectedColor = color;
      this.syncSelectedColor();
    }

    syncSelectedColor() {
      if (!this.colorRow) return;
      const buttons = this.colorRow.querySelectorAll("button[data-color]");
      buttons.forEach((btn) => {
        const active = btn.getAttribute("data-color") === this.selectedColor;
        btn.classList.toggle("is-selected", active);
      });
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
      if (action === "marker") return this.toggleMarkerAnnotation(this.selectedColor);
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
      const selectedColor = this.selectedColor || "yellow";
      const existingIds = this.getExistingAnnotationIds(type, selectedColor);
      if (!existingIds.length) {
        const anyIds = this.getExistingAnnotationIds(type);
        if (anyIds.length) {
          await this.deleteAnnotations(anyIds);
        }
      }

      if (existingIds.length > 0) {
        // Delete existing annotations of this type
        console.log('[Annotations] Removing existing annotations:', existingIds);
        await this.deleteAnnotations(existingIds);
      } else {
        // Create new annotation
        console.log('[Annotations] Creating new annotation:', type);
        await this.createAnnotation({ type, color: selectedColor });
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
        // 每删一条版本就前进一格，所以必须逐条吸收新版本（`notesWriteWithResync` 会做），
        // 否则这个循环的第二圈会带着第一圈之前的版本出门。
        await notesWriteWithResync(
          `/api/notes/${encodeURIComponent(ctx.bookId)}/${encodeURIComponent(String(ctx.chapterIndex))}/${encodeURIComponent(id)}`,
          { method: "DELETE" },
        );
      }

      this.closeSelectionToolbarIfOpen();
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
      const sel = this.contentWindow?.getSelection?.();
      const text = sel ? String(sel.toString() || "") : "";
      if (!text.trim()) return;
      navigator.clipboard?.writeText?.(text).catch(() => {});
      this.closeSelectionToolbarIfOpen();
    }

    openNoteEditor() {
      if (!this.currentRange || !this.noteEditor) return;
      // 编辑器已经为某条**既有**笔记开着（`onAnnotationClick` → `openNoteEditorWithExisting`）
      // 时，再点一下「Add Note」的意思是「接着编辑那条」，不是「在同一段文字上再建一条」。
      // 不留这个口子的话，`editingNoteId` 会被清成 null，`saveNote()` 于是走新建分支：用户
      // 看到的是「我刚改的那条没变，旁边多了一条一模一样引文的」。新建路径不受影响 ——
      // 从一段干净选区过来时 `editingNoteId` 本来就是 null。
      if (this.editingNoteId && this.noteEditor.classList.contains("is-visible")) return;
      this.editingNoteId = null;
      const rect = offsetRect(this.currentRange.getBoundingClientRect(), this.frameEl);
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

    /**
     * 装 DEG-S5 对话框的三条线：Esc、遮罩、两个出口按钮。只在 `toolbarListenersBound`
     * 那一格里调一次。
     */
    setupConflictDialog() {
      const dialog = this.conflictDialog;
      if (!dialog) return;
      // **零关闭路径**（设计规格 §6.4 要求 3）。模板里没有关闭按钮；这里把 Esc 也堵上 ——
      // 注意不能照抄 `library.js` 的 `setupDialog`，它是 `preventDefault()` 之后**照样**
      // `close()`，那是给可关闭弹层用的。遮罩点击则是「不装」就没有：原生 <dialog> 的
      // light-dismiss 要自己写坐标判断才有，不写就关不掉。
      dialog.addEventListener("cancel", (e) => e.preventDefault());
      this.conflictKeepMine?.addEventListener("click", () => {
        window.Reader3AnnotationUI?.resolveConflict?.(true);
      });
      this.conflictTakeRemote?.addEventListener("click", () => {
        window.Reader3AnnotationUI?.resolveConflict?.(false);
      });
    }

    /**
     * 从一条 409 响应里取出「服务端当前版本 ＋ 服务端当前正文」，连同本地那版一起开对话框。
     */
    async openConflictFromResponse(resp, pending) {
      const body = await resp.json().catch(() => null);
      // 吸收服务端版本：「保留我的」要拿它做下一次 `If-Match`，不吸收的话重试必然再撞 409，
      // 用户会陷在一个永远点不动的对话框里。
      if (body?.etag) notesEtag = body.etag;
      const remote = body?.annotation;
      const remoteText = remote && remote.note_text != null ? String(remote.note_text) : "";
      this.pendingConflict = {
        url: pending.url,
        noteId: pending.noteId,
        localText: pending.localText,
        remoteText,
      };
      this.showConflictDialog();
    }

    showConflictDialog() {
      const c = this.pendingConflict;
      if (!c) return;
      const dialog = this.conflictDialog;
      if (!dialog || typeof dialog.showModal !== "function") {
        // 没有原生 <dialog> 就退到提示。本地那版仍留在 textarea 里、仍没被写出去 ——
        // 降级可以难看，不可以替用户丢字。
        showToast("保存冲突：这条笔记已被另一处改过，请重新保存");
        return;
      }
      // 两版正文都摆出来。少摆一版，用户就是在闭着眼睛丢自己的字。
      if (this.conflictLocal) this.conflictLocal.textContent = c.localText;
      if (this.conflictRemote) this.conflictRemote.textContent = c.remoteText;
      if (!dialog.open) dialog.showModal();
      this.conflictKeepMine?.focus?.();
    }

    /**
     * 两个出口。`keepLocal` 为真 = 「保留我的」，为假 = 「采用远端」。
     */
    async resolveConflict(keepLocal) {
      const c = this.pendingConflict;
      if (!c) return;

      if (!keepLocal) {
        // 「采用远端」：本地那版是用户**主动放弃**的，不是要再写一遍 ——
        // 这一支一条带本地正文的写都不许发。盘上已经是远端那版，什么都不用做。
        this.settleConflict(c, c.remoteText);
        return;
      }

      // 「保留我的」：必须**真的**写到服务端。只关对话框、只改前端内存的实现，会在下一次
      // 刷新时把用户的字变回远端那版 —— 那正是这条降级要消灭的静默丢写。
      const resp = await fetch(c.url, {
        method: "PUT",
        headers: notesWriteHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ note_text: c.localText }),
      }).catch(() => null);

      if (resp && resp.status === 409) {
        // 重试的这一瞬间又被人改了。换上新的两版继续问，仍然不许静默丢。
        await this.openConflictFromResponse(resp, c);
        return;
      }
      rememberNotesEtag(resp);
      this.settleConflict(c, c.localText);
    }

    /**
     * 收尾：关对话框、把**这一支承诺的那一版**当场放回编辑器、重绘标记。
     *
     * 为什么要当场写回 textarea 而不是等下一次刷新：编辑器此刻还开着，里面躺的是刚被判
     * 出局的那一版。放着不管，用户下一次按保存就会把它又推上去 —— 而他以为自己早放弃了。
     */
    settleConflict(conflict, settledText) {
      this.pendingConflict = null;
      if (this.conflictDialog?.open) this.conflictDialog.close();
      if (this.noteTextarea) this.noteTextarea.value = settledText;
      this.editingNoteId = conflict.noteId;
      this.renderer?.loadAndRender?.().catch(() => {});
      window.dispatchEvent(new CustomEvent("reader3:annotations:updated"));
    }

    async saveNote() {
      const text = String(this.noteTextarea?.value || "").trim();
      if (!text) return;

      // If editing an existing note, update it
      if (this.editingNoteId) {
        const ctx = getReaderContext();
        if (ctx.bookId && ctx.chapterIndex != null) {
          const noteId = this.editingNoteId;
          const url = `/api/notes/${encodeURIComponent(ctx.bookId)}/${encodeURIComponent(String(ctx.chapterIndex))}/${encodeURIComponent(noteId)}`;
          const resp = await fetch(url, {
            method: "PUT",
            headers: notesWriteHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({ note_text: text }),
          }).catch(() => null);

          // DEG-S5：我手上的版本过期了 ⇒ 服务端拒绝，两版正文摆出来让用户二选一。
          // 这一支**刻意**不往下走 —— 不清 `editingNoteId`、不关编辑器：本地那版还躺在
          // textarea 里没被写出去，清掉它就是静默丢写。
          if (resp && resp.status === 409) {
            await this.openConflictFromResponse(resp, { url, noteId, localText: text });
            return;
          }
          rememberNotesEtag(resp);

          this.editingNoteId = null;
          this.closeNoteEditorIfOpen();
          this.closeSelectionToolbarIfOpen();
          await this.renderer.loadAndRender().catch(() => {});
          window.dispatchEvent(new CustomEvent("reader3:annotations:updated"));
          return;
        }
      }

      // Otherwise create a new note annotation
      const color = this.selectedColor || "yellow";
      await this.createAnnotation({ type: "note", color, note_text: text });
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

      let cfi = null;
      const contents = window.Reader3Epub?.getContents?.();
      if (contents && typeof contents.cfiFromRange === "function") {
        try {
          cfi = contents.cfiFromRange(this.currentRange);
        } catch {
          cfi = null;
        }
      }
      if (typeof cfi !== "string" || !cfi.startsWith("epubcfi(")) {
        cfi = null;
      }

      const payload = {
        type: extra.type,
        color: extra.color || null,
        quote,
        prefix,
        suffix,
        position: s,
        cfi,
        note_text: extra.note_text || null,
      };
      console.log('[Annotations] createAnnotation: sending payload:', payload);

      const resp = await notesWriteWithResync(
        `/api/notes/${encodeURIComponent(ctx.bookId)}/${encodeURIComponent(String(ctx.chapterIndex))}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      console.log('[Annotations] createAnnotation: response:', resp);

      this.closeSelectionToolbarIfOpen();
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
      const rect = offsetRect(mark.getBoundingClientRect(), this.frameEl);
      this.showTooltip(text, rect);
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

  function initAnnotations() {
    if (window.Reader3AnnotationUI) return; // Already initialized

    const initForContent = (contentEl, frameEl) => {
      if (!contentEl) return;
      const ui = new AnnotationUI(contentEl, frameEl);
      ui.init();
      window.Reader3AnnotationUI = ui;
    };

    let refreshTimer = null;
    const scheduleRefresh = () => {
      if (refreshTimer) clearTimeout(refreshTimer);
      refreshTimer = setTimeout(() => {
        window.Reader3AnnotationUI?.renderer?.loadAndRender?.().catch(() => {});
      }, 80);
    };

    window.addEventListener("reader3:content:rendered", scheduleRefresh);
    window.addEventListener("reader3:chapter:change", scheduleRefresh);
    window.addEventListener("reader3:annotations:updated", scheduleRefresh);

    // For epub.js rendering: use Reader3Epub bridge
    if (window.Reader3Epub && window.Reader3Epub.onContentsReady) {
      window.Reader3Epub.onContentsReady(() => {
        const root = window.Reader3Epub.getContentRoot?.();
        const frameEl = window.Reader3Epub.getFrameElement?.() || null;
        if (!root) return;
        const ui = window.Reader3AnnotationUI;
        if (ui) {
          ui.contentEl = root;
          ui.frameEl = frameEl;
          ui.contentDocument = root.ownerDocument || document;
          ui.contentWindow = ui.contentDocument.defaultView || window;
          if (ui.renderer) ui.renderer.contentEl = root;
          ui.renderer?.loadAndRender?.().catch(() => {});
          return;
        }
        initForContent(root, frameEl);
      });
      return;
    }

    // Fallback: use .book-content in main document
    const contentEl = document.querySelector(".book-content");
    initForContent(contentEl, null);
  }

  // Initialize immediately if DOM is ready, otherwise wait for DOMContentLoaded
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAnnotations);
  } else {
    initAnnotations();
  }
})();
