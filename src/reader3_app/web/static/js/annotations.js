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

  // 017 WI-7（审计 #4）：`notesEtag` 跟着**读**走，而屏幕上那一版跟着**收尾**走，两者会分家。
  //
  // `settleConflict()` 把某一版正文放回编辑器，紧接着 `loadAndRender()` 去读一次 notes ——
  // 那次读会把 `notesEtag` 换成服务端此刻的版本。若 409 之后、用户点下出口之前别处又写了
  // 一版，编辑器里就是**旧那版的正文**配上**新那版的令牌**：用户在它上面接着改、保存，
  // 服务端一看令牌是最新的就收下了，中间那一版无声无息地没了 —— 乐观并发被绕了过去。
  //
  // 所以「正在编辑的这一版是从哪个版本长出来的」要单独记：`notesEditBaseEtag`。它由收尾
  // 时设定（正文从哪一版来，就钉哪一版），只被**本客户端自己**提交成功的写推进，读路径
  // 一律不碰；一轮编辑结束就清空 —— 不清的话，这一页此后每一次笔记编辑都会撞 409。
  let notesEditBaseEtag = null;

  function setNotesEditBase(etag) {
    notesEditBaseEtag = etag || null;
  }

  function rememberNotesEtag(resp, options) {
    // 009 欠账 #43 (i) WI-5 / 修订 A1：`notesEtag` 只经服务端**真提交过**的版本前进。失败响应
    // （`null`，或非 2xx）带回来的 ETag 不是那样的版本，吸收它会毒化此后每一次写的 `If-Match`；
    // 这里**原样返回、不清空**——清空等于让之后的写全变成无条件写，DEG-S5 的丢写保护就没了。
    // 409 体里服务端主动告知的版本是另一回事：那两处（建/删的 409 重试、冲突对话框的吸收）
    // 是对 `notesEtag` 的直接赋值，刻意不经过这个函数，也就不受这道守卫约束。
    if (!resp || !resp.ok) return;
    const tag = resp?.headers?.get?.("ETag");
    if (!tag) return;
    notesEtag = tag;
    // 017 WI-7：**自己**写成功了，说明这一版正文与服务端仍然同源，钉子跟着前进。别人的
    // 写没有这条理由，读回来的版本更没有 —— 那正是钉子要拦下的东西。
    if (options?.isOurWrite && notesEditBaseEtag) notesEditBaseEtag = tag;
  }

  function notesWriteHeaders(extra, options) {
    const headers = Object.assign({}, extra || {});
    // 017 WI-7：编辑一条已有笔记时，基准是「编辑器里这一版从哪来」，不是「刚才读到了什么」。
    const base = options?.useEditBase && notesEditBaseEtag ? notesEditBaseEtag : notesEtag;
    if (base) headers["If-Match"] = base;
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
    // 009 欠账 #43 (i) WI-4：失败响应带回来的 ETag 不是服务端提交过的版本，不吸收（W4-C5）。
    if (resp && resp.ok) rememberNotesEtag(resp, { isOurWrite: true });
    return resp;
  }

  // toast 是**单例**：同一时刻 DOM 里至多一个 `rd-toast`。新的一条先把旧节点连同它的
  // 移除计时器一起撤掉，再挂上新节点（删掉重插）。不叠放有两个理由：叠起来的节点让
  // `get_by_test_id("rd-toast")` 在 strict mode 下解析出多个节点；而且它们一层层盖在
  // 底部那一条带上。`pointer-events: none` 保证它**永远**不拦截指针——底部带里可能正
  // 摆着笔记编辑器的按钮，一个拦截指针的 toast 就是一次 actionability 超时。
  let toastEl = null;
  let toastTimer = null;

  function showToast(message) {
    if (toastTimer) {
      clearTimeout(toastTimer);
      toastTimer = null;
    }
    if (toastEl) {
      toastEl.remove();
      toastEl = null;
    }
    const el = document.createElement("div");
    el.setAttribute("data-testid", "rd-toast");
    el.textContent = String(message || "");
    el.style.pointerEvents = "none";
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
    toastEl = el;
    toastTimer = setTimeout(() => {
      el.remove();
      if (toastEl === el) {
        toastEl = null;
        toastTimer = null;
      }
    }, 1400);
  }

  // ---- 009 欠账 #43 part (i)：写路径失败的可归因诊断 ---------------------------------
  //
  // 一次写没落地时，「盘上少一条」是唯一的外部可观测面，而它背后有三种完全不同的失败：
  // 请求根本没发出去（`requested: false`）、发出去了但没回来（`status: null`——fetch 的
  // promise 被拒，`.catch(() => null)` 分不清中断与发不出去）、回来了但被拒（数字 `status`）。
  // `Reader3NotesDiag` 是把它们分开的那份记录：一个**有界** FIFO 环形缓冲，挂在 `window`
  // 上，随页面生灭。
  //
  // 容量 100：FIFO 丢的是**最旧**的，容量太小时一次压力运行里的**第一个**失败会被挤掉，
  // 而 `t` 字段存在的意义正是拿它去对服务端日志。100 是矩阵地板 50 的两倍，给一阵重试
  // 加上周围的守卫空转留出余量；条目是六个标量，100 条的内存可以忽略。
  //
  // `t` 取 `performance.timeOrigin + performance.now()`：与墙钟同一个纪元（能对服务端日志），
  // 且在页面内单调（`Date.now()` 会随系统校时往回跳）。
  //
  // `reportNotesWriteFailure` 是**唯一**的上报口：一次调用恰好一条 ring 条目、一条
  // `console.error`、一个 toast，三件事绑在一起，后面任何调用点都没法退化成「只加个 toast」。
  // console 行是**单个字符串实参**：对象实参在 Playwright 的 `msg.text()` 里渲染成
  // `JSHandle@object`，贴出来的 console 转储里也读不出字段。
  const NOTES_DIAG_CAPACITY = 100;
  const notesDiagEntries = [];

  function notesDiagNow() {
    return performance.timeOrigin + performance.now();
  }

  function recordNotesDiag(entry) {
    const src = entry || {};
    const stored = {
      op: src.op ?? null,
      requested: src.requested ?? null,
      status: src.status ?? null,
      ok: src.ok ?? null,
      id: src.id ?? null,
      t: notesDiagNow(),
    };
    notesDiagEntries.push(stored);
    while (notesDiagEntries.length > NOTES_DIAG_CAPACITY) notesDiagEntries.shift();
    return Object.assign({}, stored);
  }

  function notesDiagSnapshot() {
    return notesDiagEntries.map((e) => Object.assign({}, e));
  }

  function reportNotesWriteFailure({ op, resp, id, message, requested } = {}) {
    const hasResp = resp !== null && resp !== undefined;
    const entry = recordNotesDiag({
      op,
      id,
      requested: requested !== false,
      status: hasResp && typeof resp.status === "number" ? resp.status : null,
      ok: hasResp ? !!resp.ok : false,
    });
    const payload = Object.assign({}, entry, { message: message == null ? null : String(message) });
    console.error(`[Annotations] notes write failed ${JSON.stringify(payload)}`);
    showToast(message || "标注没能保存，请重试");
    return entry;
  }

  window.Reader3NotesDiag = Object.freeze({
    capacity: NOTES_DIAG_CAPACITY,
    record: recordNotesDiag,
    entries: notesDiagSnapshot,
    reportNotesWriteFailure,
    showToast,
  });

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

  function sameRange(sel, range) {
    if (!sel || sel.rangeCount !== 1 || !range) return false;
    try {
      const current = sel.getRangeAt(0);
      return (
        current.compareBoundaryPoints(Range.START_TO_START, range) === 0 &&
        current.compareBoundaryPoints(Range.END_TO_END, range) === 0
      );
    } catch {
      return false;
    }
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

  /**
   * 这条 cfi 解析出来的 Range，与这条标注自己存的 `quote` 对得上吗？（017 WI-5，审计 #3）
   *
   * `render()` 让 CFI 分支跑在文本匹配**之前**，所以一条解析得出来的 cfi 就是最终答案，
   * 从此没有第二次机会。而 cfi 与 quote 是**两个独立写进去的锚点**，它们可以不一致：
   * 旧数据、别的客户端、以及 `createAnnotation` 里那条今天还没接通的 cfi 生成路径
   * （见那里的注释）都能产出一条指向别处、或者塌成一点的 cfi。
   *
   * 不一致时信谁，是这里唯一要定的事：**信 quote**。quote 是用户真正选中的那段字，
   * cfi 只是指向它的一条路；路错了就重新按字找，而不是把线划在错的地方——
   * 「划在错的地方」和「划不出来」对用户不是同一件事，前者更坏：它看起来是对的。
   *
   * 没有 quote 可对照时（理论上的旧记录；`createAnnotation` 拒发空 quote），
   * 只挡住**证明无用**的那一种——零宽 Range 只会插进去一个空的 `<mark>`。
   */
  function cfiRangeAgreesWithQuote(range, ann) {
    if (!range || range.collapsed) return false;
    const quote = String(ann?.quote || "");
    if (!quote) return true;
    return range.toString() === quote;
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
        if (!cfiRangeAgreesWithQuote(range, ann)) {
          // 解析不出来、塌成一点、或者指向了别的文字——一律退回文本匹配。
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
      // 017 WI-6（审计 #5）：有没有一次「保留我的」的写还在飞。见 `setConflictBusy`。
      this.conflictSubmitting = false;

      this.currentRange = null;
      //【#44】选区落定那一刻算好的偏移快照。存在的理由是 currentRange 会被一次
      // 标注重绘悄悄作废：applySegments(:349) 用 replaceChild 把被标注段落的文本
      // 节点整个换掉，而 offsetFromNode(:122) 对文本节点做的是**身份**比较
      // (nodes.find((x) => x.node === textNode))，换掉之后就再也找不回来。
      // 偏移是纯数字、不持有任何 DOM 引用，所以重绘杀不死它。
      // 形状是 { start, end, chapterIndex }——chapterIndex 不是装饰，见 offsetsUsable()。
      this.currentOffsets = null;
      this.currentIndex = null;
      this.currentAnnotationMeta = [];
      this.currentAnnotationIds = [];
      this.editingNoteId = null;
      this.lastSelectionAt = 0;
      this.dismissedRange = null;
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
        this.rememberRange(range);
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
      // 017 WI-7：`editingNoteId` 与基准令牌**成对**出现 —— 谁让编辑分支变得可达，谁就得
      // 说清这一版正文是从哪个版本长出来的。这一轮的正文是刚从页面上读来的，基准就是全局
      // 那个值，上一轮冲突留下的钉子到此为止（另一处成对赋值在 `settleConflict()`）。
      // 不清它，这一页此后每一次保存都会拿一个过期版本去撞 409。
      setNotesEditBase(null);

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
      // 009 欠账 #43 (i) WI-6：请求前的守卫出口。什么都没发出去，但用户按了按钮——记一条
      // `requested: false`，让「请求没发出去」与「发出去了没落地」在诊断里分得开。
      if (!this.currentRange || !this.contentEl) {
        reportNotesWriteFailure({
          op: "marker-toggle-no-selection",
          requested: false,
          message: "选区已失效，请重新选中再试",
        });
        return;
      }

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
      // Rewriting an unchanged selection fires `selectionchange`, which makes epub.js emit
      // `selected` again ~250ms later: a self-sustaining loop that reopens a closed toolbar.
      if (sel && !sameRange(sel, range)) {
        sel.removeAllRanges();
        sel.addRange(range);
      }
      this.lastSelectionAt = Date.now();
      // epub.js still emits one trailing `selected` for the user's own selection; if the
      // toolbar was closed on this very range in the meantime, keep it closed.
      if (this.dismissedRange && sameRange(sel, this.dismissedRange)) return;
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
      this.rememberRange(range);
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
      this.dismissedRange = null;
      this.toolbar.classList.add("is-visible");
      this.toolbar.style.left = `${Math.round(x)}px`;
      this.toolbar.style.top = `${Math.round(y)}px`;
      this.toolbar.style.transform = "translate(-50%, -100%)";
      this.syncSelectedColor();
    }

    closeSelectionToolbarIfOpen() {
      if (!this.toolbar?.classList.contains("is-visible")) return false;
      this.toolbar.classList.remove("is-visible");
      this.dismissedRange = this.currentRange || null;
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
      // 009 欠账 #43 (i) WI-6：同 `toggleMarkerAnnotation` 的守卫，入口不同、op 不同。
      if (!this.currentRange || !this.contentEl) {
        reportNotesWriteFailure({
          op: "type-toggle-no-selection",
          requested: false,
          message: "选区已失效，请重新选中再试",
        });
        return;
      }

      // Check if there are existing annotations of this type covering the selection
      const selectedColor = this.selectedColor || "yellow";
      const existingIds = this.getExistingAnnotationIds(type, selectedColor);
      if (!existingIds.length) {
        const anyIds = this.getExistingAnnotationIds(type);
        if (anyIds.length) {
          // 修订 A2：改色 = 先删旧、再建新。删失败了就停在这里，不建——否则 ring 说「删失败」、
          // 盘上却多出一条新的，两份诊断互相矛盾。判据是**这一次**删除的返回值，不是任何
          // 模块级状态：下一次改色从零开始判定（W4-C7）。
          const removed = await this.deleteAnnotations(anyIds);
          if (!removed.ok) return;
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
     * Delete annotations by IDs.
     *
     * 返回 `{ ok, failedIds }`，调用方据此决定下一步（修订 A2：改色的「先删后建」删失败就不建）。
     * 这是**本次调用**的结果，不留任何模块级状态。
     *
     * 多条删除的失败策略（009 欠账 #43 (i) WI-4，写明而不是留成隐含；W4-C3 钉住它）：
     * - **失败不中断循环**：每条各删各的，删掉的就是删掉了（部分进度保留）；
     * - 每个失败的 id **各报一次** `reportNotesWriteFailure({op:"delete", id, …})`；
     * - 只要有一条失败就**不宣告整体成功**：不关工具条、不 `setCurrentAnnotations([])`、
     *   不派发 `reader3:annotations:updated`。有删成功的才重绘一次，让屏幕与盘面一致
     *   （删掉的消失、失败的留着），并只从当前选中集里去掉**删成功**的那些 id——失败的
     *   仍然选中，再按一次删除就是只重试它们。
     */
    async deleteAnnotations(ids) {
      const uniqueIds = [...new Set(ids)].filter(Boolean);
      if (!uniqueIds.length) return { ok: true, failedIds: [] };

      const ctx = getReaderContext();
      // 一条都没删：不能让调用方当成删成功了接着往下走。
      // 009 欠账 #43 (i) WI-6 / 修订 A3：一次调用只记**一条**（守卫触发了一次，什么都没发），
      // `id` 是被放弃删除的那些 id，逗号相连。
      if (!ctx.bookId || ctx.chapterIndex == null) {
        reportNotesWriteFailure({
          op: "delete-no-context",
          requested: false,
          id: uniqueIds.join(","),
          message: "没找到当前书章，标注没有删除，请刷新后重试",
        });
        return { ok: false, failedIds: uniqueIds };
      }

      const failedIds = [];
      for (const id of uniqueIds) {
        // 每删一条版本就前进一格，所以必须逐条吸收新版本（`notesWriteWithResync` 会做），
        // 否则这个循环的第二圈会带着第一圈之前的版本出门。
        const resp = await notesWriteWithResync(
          `/api/notes/${encodeURIComponent(ctx.bookId)}/${encodeURIComponent(String(ctx.chapterIndex))}/${encodeURIComponent(id)}`,
          { method: "DELETE" },
        );
        if (!resp || !resp.ok) {
          failedIds.push(id);
          reportNotesWriteFailure({
            op: "delete",
            resp,
            id,
            message: "标注没能删除，请重试",
          });
        }
      }

      if (failedIds.length) {
        if (failedIds.length < uniqueIds.length) {
          const failed = new Set(failedIds);
          const deleted = new Set(uniqueIds.filter((id) => !failed.has(id)));
          await this.renderer.loadAndRender().catch(() => {});
          this.setCurrentAnnotations((this.currentAnnotationMeta || []).filter((m) => !deleted.has(m.id)));
        }
        return { ok: false, failedIds };
      }

      this.closeSelectionToolbarIfOpen();
      await this.renderer.loadAndRender().catch(() => {});
      this.setCurrentAnnotations([]);
      window.dispatchEvent(new CustomEvent("reader3:annotations:updated"));
      return { ok: true, failedIds: [] };
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
      // 009 欠账 #43 (i) WI-6 / 修订 A3：重绘之后选区对不上任何标注时就落在这里——用户点了
      // 删除，什么都没发出去。不记下来的话，事后读到空的诊断会误以为「删除发出去了、只是慢」。
      if (!ids.length) {
        reportNotesWriteFailure({
          op: "delete-no-ids",
          requested: false,
          message: "这里没有可删除的标注",
        });
        return;
      }
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
      // 注意不能照抄 013 前 `static/library.js` 的 `setupDialog`（已删），它是 `preventDefault()` 之后**照样**
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
        // 017 WI-7：远端那版正文与这个版本号是同一次读的产物。「采用远端」把正文放进
        // 编辑器时必须把它一起带上，否则正文是这一版、令牌却是收尾时读到的更新那一版。
        remoteEtag: body?.etag || null,
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
     * 提交期间把两个出口一起锁上，写回来之后一起放开（017 WI-6，审计 #5）。
     *
     * 这是**给人看的**那一层：用户得看见「正在保存，别再点了」，而不是点下去没反应。
     * 它不是唯一一层，也不该是——`disabled` 是一条 DOM 属性，一次重绘、一段外部脚本、
     * 或者任何绕过按钮直接调 `Reader3AnnotationUI.resolveConflict(...)` 的路径都能越过它。
     * 真正挡住并发的是 `resolveConflict()` 开头那道 `conflictSubmitting` 守卫。
     */
    setConflictBusy(busy) {
      const on = !!busy;
      this.conflictSubmitting = on;
      if (this.conflictKeepMine) this.conflictKeepMine.disabled = on;
      if (this.conflictTakeRemote) this.conflictTakeRemote.disabled = on;
      this.conflictDialog?.setAttribute?.("aria-busy", on ? "true" : "false");
    }

    /**
     * 两个出口。`keepLocal` 为真 = 「保留我的」，为假 = 「采用远端」。
     *
     * **同一时刻只许有一次收尾在飞**（017 WI-6，审计 #5）。原先不是这样：「保留我的」
     * 的 PUT 还在飞时两个按钮都还能点，点「采用远端」会当场 `settleConflict()` 收尾，
     * 而那个在飞的写回来之后仍会 `settleConflict(c, c.localText)` —— 用户看见自己最后
     * 作出的选择被反了过来，再点一次「保留我的」还会再发一次写。
     *
     * 守卫分两个方向，谁也替不了谁：进门那道（`conflictSubmitting`）挡的是「新的调用
     * 进不来」；回来之后那道（`this.pendingConflict !== c`）挡的是「回来的这一次还算不算
     * 数」—— 一次回调只能收尾它出发时的那一场冲突。
     */
    async resolveConflict(keepLocal) {
      const c = this.pendingConflict;
      // 009 欠账 #43 (i) WI-6 / 修订 A3：防御性守卫——没有待决冲突就没有可写的东西。
      if (!c) {
        reportNotesWriteFailure({
          op: "conflict-no-pending",
          requested: false,
          message: "没有待解决的冲突",
        });
        return;
      }

      // 017 WI-6（审计 #5）：上一次选择还在写，这一次一律拒掉 —— 两个出口都拒。
      // 「采用远端」也要拒：它不发请求，却会**当场**把冲突收掉，于是在飞的那次写回来时
      // 用户的选择已经被换过一轮了。两条通道照记（ring ＋ console），因为这两种拒绝都
      // 不改屏幕，只看 DOM 分不出「守卫挡住了」和「代码压根没跑到」。
      if (this.conflictSubmitting) {
        reportNotesWriteFailure({
          op: "conflict-busy",
          requested: false,
          id: c.noteId,
          message: "上一次选择还在保存，请稍候",
        });
        return;
      }

      if (!keepLocal) {
        // 「采用远端」：本地那版是用户**主动放弃**的，不是要再写一遍 ——
        // 这一支一条带本地正文的写都不许发。盘上已经是远端那版，什么都不用做。
        this.settleConflict(c, c.remoteText, c.remoteEtag);
        return;
      }

      // 「保留我的」：必须**真的**写到服务端。只关对话框、只改前端内存的实现，会在下一次
      // 刷新时把用户的字变回远端那版 —— 那正是这条降级要消灭的静默丢写。
      this.setConflictBusy(true);
      let resp;
      try {
        resp = await fetch(c.url, {
          method: "PUT",
          headers: notesWriteHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ note_text: c.localText }),
        }).catch(() => null);
      } finally {
        // 任何出口都要放开：失败要能重试，409 之后那一场新冲突也要能点。
        this.setConflictBusy(false);
      }

      // 回来的这一次，还是当初点下去的那一场冲突吗？不是就只记账、不收尾 ——
      // 写本身可能已经落地了（下面盘上就是本地那版），我们拒绝的是**替它宣告收尾**：
      // 那会拿一份过期的 `localText` 盖掉用户此刻正在看、正在编辑的那一格。
      if (this.pendingConflict !== c) {
        reportNotesWriteFailure({
          op: "conflict-stale",
          resp,
          id: c.noteId,
          message: "这条冲突已经被别的操作收掉了，这次保存不再改动界面",
        });
        return;
      }

      if (resp && resp.status === 409) {
        // 重试的这一瞬间又被人改了。换上新的两版继续问，仍然不许静默丢。
        await this.openConflictFromResponse(resp, c);
        return;
      }
      // 009 欠账 #43 (i) WI-5：非 409 的失败（数字 status 被拒，或 `resp === null`——请求没回来）
      // **不收尾**：对话框留着、`pendingConflict` 留着、编辑器里的本地那版不动，再点一次
      // 「保留我的」就是重试。原先这里无条件 `settleConflict`，那就是在一次没落地的写上宣告成功。
      if (!resp || !resp.ok) {
        reportNotesWriteFailure({
          op: "conflict-keep-mine",
          resp,
          id: c.noteId,
          message: "「保留我的」没能保存，你的版本仍在，请重试",
        });
        return;
      }
      rememberNotesEtag(resp);
      // 017 WI-7：这一支放进编辑器的正文就是刚写上去的那一版，基准自然是那次写的版本号
      // —— 不是 409 体里报来的那一版（它已经被我们自己这次写顶掉了，钉它会让下一次保存
      // 撞上自己刚写出去的版本）。
      this.settleConflict(c, c.localText, resp?.headers?.get?.("ETag") || null);
    }

    /**
     * 收尾：关对话框、把**这一支承诺的那一版**当场放回编辑器、重绘标记。
     *
     * 为什么要当场写回 textarea 而不是等下一次刷新：编辑器此刻还开着，里面躺的是刚被判
     * 出局的那一版。放着不管，用户下一次按保存就会把它又推上去 —— 而他以为自己早放弃了。
     */
    settleConflict(conflict, settledText, baseEtag) {
      this.pendingConflict = null;
      // 必须钉在 `loadAndRender()` **之前**：那次读会把全局版本换成服务端此刻的值，
      // 而编辑器里这一版未必是从那儿来的（017 WI-7）。
      setNotesEditBase(baseEtag);
      if (this.conflictDialog?.open) this.conflictDialog.close();
      if (this.noteTextarea) this.noteTextarea.value = settledText;
      this.editingNoteId = conflict.noteId;
      this.renderer?.loadAndRender?.().catch(() => {});
      window.dispatchEvent(new CustomEvent("reader3:annotations:updated"));
    }

    async saveNote() {
      const text = String(this.noteTextarea?.value || "").trim();
      // 009 欠账 #43 (i) WI-6 / 修订 A3：用户点了保存，什么都没发出去。文案是提示而不是报错，
      // 但两条通道（ring ＋ console）照记——空的保存与「保存发出去了却丢了」必须分得开。
      if (!text) {
        reportNotesWriteFailure({
          op: "save-empty-text",
          requested: false,
          id: this.editingNoteId || null,
          message: "笔记是空的，没有保存",
        });
        return;
      }

      // If editing an existing note, update it
      if (this.editingNoteId) {
        const ctx = getReaderContext();
        if (ctx.bookId && ctx.chapterIndex != null) {
          const noteId = this.editingNoteId;
          const url = `/api/notes/${encodeURIComponent(ctx.bookId)}/${encodeURIComponent(String(ctx.chapterIndex))}/${encodeURIComponent(noteId)}`;
          const resp = await fetch(url, {
            method: "PUT",
            // 017 WI-7：拿「编辑器里这一版的出处」当基准，而不是最近一次读到的版本。
            headers: notesWriteHeaders({ "Content-Type": "application/json" }, { useEditBase: true }),
            body: JSON.stringify({ note_text: text }),
          }).catch(() => null);

          // DEG-S5：我手上的版本过期了 ⇒ 服务端拒绝，两版正文摆出来让用户二选一。
          // 这一支**刻意**不往下走 —— 不清 `editingNoteId`、不关编辑器：本地那版还躺在
          // textarea 里没被写出去，清掉它就是静默丢写。
          if (resp && resp.status === 409) {
            await this.openConflictFromResponse(resp, { url, noteId, localText: text });
            return;
          }
          // 009 欠账 #43 (i)：非 409 的失败（数字 status 被拒，或 `resp === null`——请求没回来）。
          // 与 409 同理**不往下走**：不清 `editingNoteId`、不关编辑器、不重绘——用户的字还在
          // textarea 里，再按一次保存就是重试。原先这里无条件收尾，那就是静默丢写。
          // 必须排在 `rememberNotesEtag` 之前：失败响应带回来的 ETag 不是服务端提交过的版本，
          // 吸收它会让下一次写带着毒化的 `If-Match` 出去。
          if (!resp || !resp.ok) {
            reportNotesWriteFailure({
              op: "edit",
              resp,
              id: noteId,
              message: "笔记没能保存，修改仍在编辑器里，请重试",
            });
            return;
          }
          rememberNotesEtag(resp, { isOurWrite: true });

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

    /**
     * 记住选区：活的 Range 一份，重绘杀不死的偏移快照一份。
     *
     * 两份都留着而不是只留快照，是因为快照丢信息——cfi 要从真 Range 上算
     * (contents.cfiFromRange)，Range 还在的时候就该用 Range。快照只在 Range
     * 指不回文档了的时候才顶上。
     */
    rememberRange(range) {
      this.currentRange = range;
      this.currentOffsets = this.offsetsForRange(range);
    }

    /** 把 Range 折算成 contentEl 文本轴上的 {start,end,chapterIndex}；折算不了返回 null。 */
    offsetsForRange(range) {
      if (!range || !this.contentEl) return null;
      const idx = buildTextIndex(this.contentEl);
      const start = offsetFromNode(idx.nodes, range.startContainer, range.startOffset);
      const end = offsetFromNode(idx.nodes, range.endContainer, range.endOffset);
      if (start == null || end == null) return null;
      return { start, end, chapterIndex: getReaderContext().chapterIndex };
    }

    /**
     * 快照只有对得上当前文档才敢用；对不上就返回 null，让调用方红着手退出。
     *
     * 这两道检查不是防御性编程的客套。**写进去但位置是错的，比不写更坏**——
     * 不写，用户至少看得见自己白按了一下；位置错了，是一条指向别处的标注被
     * 当成真的存进盘里，而且此后每次渲染都会在错的地方划一道。
     *
     * - chapterIndex：换章之后偏移轴是另一根，数字却照样落在合法区间里，
     *   所以长度检查**挡不住**这一种，必须单独比章节号。currentRange 本身
     *   从不在换章时置空（全文件只有建构子置过一次），快照也就不能指望
     *   "过期了自然就没了"。
     * - 长度：同一章内正文重新取过、变短了，旧偏移会越界。
     */
    offsetsUsable(snapshot, textLength, chapterIndex) {
      if (!snapshot) return null;
      const { start, end } = snapshot;
      if (!Number.isInteger(start) || !Number.isInteger(end)) return null;
      if (snapshot.chapterIndex !== chapterIndex) return null;
      if (start < 0 || end < 0 || start > textLength || end > textLength) return null;
      return { start, end };
    }

    /**
     * Range 的两个边界是否都还锚在当前的文本节点上。
     *
     * **这才是「选区被重绘作废了」的判据**，而不是「偏移算不出来」。一开始按后者
     * 写是错的，探针把它证伪了：`applySegments` 用 `replaceChild` 换掉文本节点时，
     * 按 DOM 规范，落在被移除节点内的 Range 边界**不会失效**，而是上浮到父元素、
     * 偏移变成子节点下标。于是 `offsetFromNode` 走元素分支，**不返回 null，而是
     * 静默给出一个错的偏移**——#44 现场里两端都塌到 3，quote 算成空串。
     * 换句话说，靠 null 判断的兜底永远不会被触发。
     */
    rangeAnchoredIn(range, nodes) {
      const anchored = (n) => !!n && n.nodeType === Node.TEXT_NODE && nodes.some((x) => x.node === n);
      return anchored(range.startContainer) && anchored(range.endContainer);
    }

    /**
     * 定下这次要写的 {start,end}：活 Range 还锚得住就用它，锚不住就用快照。
     *
     * 顺序是有讲究的。活 Range 优先，是因为它能反映选区在记下之后又被改动的情形；
     * 快照只在 Range 已经指不回文档时顶上。两者都拿不到就返回 null，由调用方
     * 出声放弃——**宁可不写，也不写一条位置是错的**。
     */
    resolveOffsets(idx, chapterIndex) {
      const range = this.currentRange;
      if (!range) return null;
      const snap = this.offsetsUsable(this.currentOffsets, idx.text.length, chapterIndex);
      if (!this.rangeAnchoredIn(range, idx.nodes)) {
        if (snap) {
          console.warn('[Annotations] 活选区已被重绘作废，回落到偏移快照', snap);
          return snap;
        }
        // 没有快照可用时仍走老路算一遍——元素边界的选区（三击整段之类）本来就
        // 走这条，不该因为这个改动而退化。
      }
      const start = offsetFromNode(idx.nodes, range.startContainer, range.startOffset);
      const end = offsetFromNode(idx.nodes, range.endContainer, range.endOffset);
      if (start == null || end == null) return snap;
      //【#9】活选区还锚在文本节点上，但已经塌成一个点。`render()` 里的 normalize() 把
      // 相邻文本节点并成一个，两个端点于是落到同一个偏移上——节点本身仍在索引里，
      // 所以上面的 rangeAnchoredIn 看不见这件事（它问的是「还在不在」，不是「还有没有宽度」）。
      // 塌掉的选区描述不出一段标注：quote 必为空串。快照若还是一段真区间就用快照。
      // 这正是异色重按 wavy / underline 那条路今天丢数据的地方（先 delete，再重绘，再新建）。
      if (start === end && snap && snap.start !== snap.end) {
        console.warn('[Annotations] 活选区已塌成一个点，回落到偏移快照', snap);
        return snap;
      }
      return { start, end };
    }

    async createAnnotation(extra) {
      console.log('[Annotations] createAnnotation called with:', extra);
      // 009 欠账 #43 (i) WI-6：这两道守卫原本是一句 console.log 就 return——不发请求、不提示。
      if (!this.currentRange || !this.contentEl) {
        reportNotesWriteFailure({
          op: "create-no-selection",
          requested: false,
          message: "选区已失效，请重新选中再试",
        });
        return;
      }
      const ctx = getReaderContext();
      if (!ctx.bookId || ctx.chapterIndex == null) {
        reportNotesWriteFailure({
          op: "create-no-context",
          requested: false,
          message: "没找到当前书章，标注没有保存，请刷新后重试",
        });
        return;
      }

      const idx = buildTextIndex(this.contentEl);
      const offsets = this.resolveOffsets(idx, ctx.chapterIndex);
      if (!offsets) {
        // 这里原本是一句 console.log 就 return：不发 POST、不提示、不报错。
        // 欠账 #44 让它开口；009 #50 把它接进诊断环——请求前放弃，所以 requested:false。
        reportNotesWriteFailure({
          op: "create-no-offsets",
          requested: false,
          message: "这段选区已失效，请重新选中再试",
        });
        return;
      }
      const s = Math.min(offsets.start, offsets.end);
      const e = Math.max(offsets.start, offsets.end);

      const quote = idx.text.slice(s, e);
      const prefix = idx.text.slice(Math.max(0, s - 50), s);
      const suffix = idx.text.slice(e, Math.min(idx.text.length, e + 50));

      // 空 quote 不是一条标注，是一次算错。#44 现场里它被照发不误，服务端回
      // 400，而下面那个 resp 从来没人看，于是一次写丢失长得和一次成功一模一样。
      // 009 #50：同样走诊断环，requested:false。
      if (!quote) {
        reportNotesWriteFailure({
          op: "create-empty-quote",
          requested: false,
          message: "没取到选中的文字，请重新选中再试",
        });
        return;
      }

      // cfi 只在它和上面那段 `quote` **对得上**的时候才写（017 WI-5，审计 #3）。
      //
      // 原来这里直接拿 `this.currentRange` 去算。问题在于：走到这一行时，那个 Range
      // 可能刚刚被 `resolveOffsets` 判定为不可信——重绘把端点顶到了父元素上，于是
      // 偏移取的是快照。拿一个已经作废的 Range 算 cfi，写进盘的就是一条与
      // `quote`／`position` 自相矛盾的锚点，而读侧**优先信 cfi**，用户看见的是一道
      // 划在别处（或者空）的线。#3 给的两条处方是「用回落后的偏移重建 Range」或
      // 「回落时就别写 cfi」；这里取后者，因为它与读侧那道
      // `cfiRangeAgreesWithQuote` 是**同一条规矩**——对不上就不写、不信——
      // 而不是又多一套只在这一处成立的说法。
      //
      // **这段今天一次都没执行过，是明账不是疏漏。** `getContents()`
      // （`epub-renderer.js`）返回的是 epub.js 的 **View**，不是 `Contents`；View 上
      // 没有 `cfiFromRange`，所以下面那个条件恒假、`cfi` 恒为 `null`，新建的标注全靠
      // quote/position 重锚。真正的 `Contents` 挂在 `view.contents` 上。**没有在这条
      // 分支里顺手接通它**：接通之后每条新标注都带 cfi，渲染会从「文本匹配 ＋ 相邻
      // 段合并」整体切到「一条标注一个 mark」，重叠标注、`data-annotation-ids`、
      // 孤儿判定全部换一条路——那是另一件事的代价，而 `baseline_1b` 是冻结的，
      // 兜不住。记在 017 的任务文件里，单独立项。
      let cfi = null;
      const contents = window.Reader3Epub?.getContents?.();
      const rangeIsStillTheQuote =
        !!this.currentRange && this.currentRange.toString() === quote;
      if (rangeIsStillTheQuote && contents && typeof contents.cfiFromRange === "function") {
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
      if (!resp || !resp.ok) {
        // 不看 resp 是 #44 之所以「静默」的最后一环：服务端已经明说 400 了，
        // 界面照样收工具条、照样重绘，看上去和成功一模一样。
        // 009 #50：网络层失败（resp 为 null）与非 2xx 都经唯一上报口记一条 op:"create"，
        // status 由 helper 从 resp 读出；文案不变。
        reportNotesWriteFailure({
          op: "create",
          resp,
          message: `标注没能保存${resp ? `（${resp.status}）` : ""}，请重试`,
        });
        return;
      }

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
