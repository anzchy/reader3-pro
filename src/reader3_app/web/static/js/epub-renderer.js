(() => {
  "use strict";

  const ctx = window.Reader3Ctx || {};
  const logPrefix = "[Reader3] epub-renderer";
  const viewer = document.getElementById("epub-viewer");
  const missing = document.getElementById("epub-missing");
  const progressIndicator = document.getElementById("reading-progress");
  const prevLink = document.getElementById("prev-chapter-link");
  const nextLink = document.getElementById("next-chapter-link");
  const navIndicator = document.querySelector(".nav-indicator");

  if (!viewer) return;

  console.log(`${logPrefix} init`, {
    epubUrl: ctx.epubUrl,
    epubAvailable: ctx.epubAvailable,
    chapterIndex: ctx.chapterIndex,
  });

  const isEpubAvailable = ctx.epubAvailable === true || ctx.epubAvailable === "true";
  if (!isEpubAvailable) {
    if (missing) missing.classList.add("is-visible");
    return;
  }

  if (typeof window.ePub !== "function") {
    console.warn(`${logPrefix} epub.js not loaded`);
    return;
  }

  let book = null;
  try {
    book = window.ePub(ctx.epubUrl);
  } catch (err) {
    console.error(`${logPrefix} failed to create book`, err);
    return;
  }
  console.log(`${logPrefix} book created`);
  if (book && book.opened && typeof book.opened.then === "function") {
    book.opened
      .then(() => console.log(`${logPrefix} book opened`))
      .catch((err) => console.error(`${logPrefix} book opened error`, err));
  }
  if (book?.loaded?.metadata && typeof book.loaded.metadata.then === "function") {
    book.loaded.metadata
      .then((meta) => console.log(`${logPrefix} metadata`, meta))
      .catch((err) => console.error(`${logPrefix} metadata error`, err));
  }
  const initialFlow = window.innerWidth < 600 ? "scrolled-doc" : "paginated";
  const rendition = book.renderTo(viewer, {
    width: "100%",
    height: "100%",
    flow: initialFlow,
    spread: "none",
  });
  console.log(`${logPrefix} rendition created`, { flow: initialFlow });

  let currentSectionIndex = Number.isFinite(ctx.chapterIndex) ? Number(ctx.chapterIndex) : 0;
  // 页面请求的章节号，此后不变（F6b）。`rendered` 会改写 currentSectionIndex 和
  // ctx.chapterIndex，getDebugState 要能看出「请求的」和「实际渲染的」是不是同一章。
  const requestedIndex = currentSectionIndex;
  let currentContents = null;
  const contentsCallbacks = [];

  // 宿主页（reader.html）一旦通过 applyThemeSettings(settings) 说过话，就以它为准。
  // 边界校验（MIN/MAX_FONT_SIZE、MIN/MAX_LINE_HEIGHT）只写在宿主页的 loadSettings()
  // 里；渲染器再去回读一遍 localStorage 原始值，等于给同一份数据开了第二个不做校验的
  // 读者，越界值会只被其中一个挡住——面板显示 17、正文渲染 99（欠账 #22 的第二个入口，
  // 2026-09-06 实测）。localStorage 只作为**首屏**的来源保留，那时宿主页还没说话。
  let hostFontSettings = null;

  function getFontSettings() {
    const defaults = { fontSize: 17, lineHeight: 1.9 };
    if (hostFontSettings) return hostFontSettings;
    const saved = window.localStorage?.getItem("reader3-font-settings");
    if (!saved) return defaults;
    try {
      const parsed = JSON.parse(saved);
      return {
        fontSize: Number(parsed.fontSize) || defaults.fontSize,
        lineHeight: Number(parsed.lineHeight) || defaults.lineHeight,
      };
    } catch {
      return defaults;
    }
  }

  function buildContentCss() {
    const { fontSize, lineHeight } = getFontSettings();
    const marginX = window.innerWidth < 600 ? 16 : 80;

    return `
      :root {
        --reader-font-size: ${fontSize}px;
        --reader-line-height: ${lineHeight};
        --reader-margin-x: ${marginX}px;
        --reader-text: #333333;
      }
      html, body {
        margin: 0;
        padding: 0;
      }
      body {
        color: var(--reader-text);
        font-family: "Noto Serif SC", serif;
        font-size: var(--reader-font-size);
        line-height: var(--reader-line-height);
        padding: 40px var(--reader-margin-x) 60px;
      }
      p {
        text-indent: 4ch !important;
        margin-bottom: 1.5rem;
      }
      h1, h2 {
        font-size: 22px;
        font-weight: 600;
        margin-top: 2.5rem;
        margin-bottom: 1.5rem;
        text-indent: 0;
      }
      h3, h4 {
        font-size: 18px;
        font-weight: 500;
        margin-top: 2rem;
        margin-bottom: 1rem;
        text-indent: 0;
      }
      img {
        max-width: 100%;
        height: auto;
        border-radius: 8px;
        margin: 1.5rem 0;
      }
      mark.annotation {
        padding: 0 2px;
        border-radius: 3px;
        background: transparent;
        cursor: pointer;
      }
      mark.annotation.annotation--marker.annotation--yellow { background: rgba(251, 191, 36, 0.6); }
      mark.annotation.annotation--marker.annotation--green { background: rgba(74, 222, 128, 0.6); }
      mark.annotation.annotation--marker.annotation--pink { background: rgba(248, 113, 113, 0.5); }
      mark.annotation.annotation--marker.annotation--blue { background: rgba(96, 165, 250, 0.55); }
      mark.annotation.annotation--underline {
        background: transparent !important;
        text-decoration: underline;
        text-decoration-thickness: 2px;
        text-decoration-color: #f97316;
        text-underline-offset: 3px;
      }
      mark.annotation.annotation--underline.annotation--yellow { text-decoration-color: rgba(251, 191, 36, 0.95); }
      mark.annotation.annotation--underline.annotation--green { text-decoration-color: rgba(74, 222, 128, 0.95); }
      mark.annotation.annotation--underline.annotation--pink { text-decoration-color: rgba(248, 113, 113, 0.95); }
      mark.annotation.annotation--underline.annotation--blue { text-decoration-color: rgba(96, 165, 250, 0.95); }
      mark.annotation.annotation--wavy {
        background: transparent !important;
        text-decoration: underline wavy;
        text-decoration-thickness: 2px;
        text-decoration-color: #84cc16;
        text-underline-offset: 3px;
      }
      mark.annotation.annotation--wavy.annotation--yellow { text-decoration-color: rgba(251, 191, 36, 0.95); }
      mark.annotation.annotation--wavy.annotation--green { text-decoration-color: rgba(74, 222, 128, 0.95); }
      mark.annotation.annotation--wavy.annotation--pink { text-decoration-color: rgba(248, 113, 113, 0.95); }
      mark.annotation.annotation--wavy.annotation--blue { text-decoration-color: rgba(96, 165, 250, 0.95); }
      mark.search-match {
        background: #ffe58f;
        padding: 0 2px;
        border-radius: 3px;
      }
      mark.search-current {
        background: #ffd43b;
        outline: 2px solid #ff922b;
      }
      mark.annotation.is-jump-target {
        outline: 2px solid rgba(37, 99, 235, 0.6);
      }
    `;
  }

  function ensureContentStyles(contents) {
    if (!contents?.document) return;
    const doc = contents.document;
    let styleEl = doc.getElementById("reader3-epub-theme");
    if (!styleEl) {
      styleEl = doc.createElement("style");
      styleEl.id = "reader3-epub-theme";
      doc.head.appendChild(styleEl);
    }
    styleEl.textContent = buildContentCss();

    if (!doc.getElementById("reader3-epub-font")) {
      const link = doc.createElement("link");
      link.id = "reader3-epub-font";
      link.rel = "stylesheet";
      link.href = "https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;500;600&display=swap";
      doc.head.appendChild(link);
    }
  }

  function updateNavIndicator() {
    if (!navIndicator) return;
    const total = Number.isFinite(ctx.totalChapters) ? Number(ctx.totalChapters) : 0;
    const idx = Number.isFinite(currentSectionIndex) ? currentSectionIndex : 0;
    navIndicator.textContent = `Section ${idx + 1} of ${total}`;
  }

  function updateNavButtons() {
    if (prevLink) prevLink.classList.toggle("disabled", currentSectionIndex <= 0);
    if (nextLink) {
      const total = Number.isFinite(ctx.totalChapters) ? Number(ctx.totalChapters) : 0;
      nextLink.classList.toggle("disabled", total > 0 && currentSectionIndex >= total - 1);
    }
  }

  function updateTocActive(fileHref) {
    if (!fileHref) return;
    const cleanHref = String(fileHref).split("#")[0];
    const links = document.querySelectorAll(".toc-link[data-file-href]");
    links.forEach((link) => {
      const match = link.getAttribute("data-file-href") === cleanHref;
      link.classList.toggle("active", match);
    });
  }

  function syncLocationToUrl() {
    if (!ctx.bookId) return;
    const url = new URL(window.location.href);
    url.pathname = `/read/${encodeURIComponent(ctx.bookId)}/${encodeURIComponent(String(currentSectionIndex))}`;
    history.replaceState({}, "", url.toString());
  }

  function notifyContentsReady(contents) {
    contentsCallbacks.forEach((cb) => cb(contents));
  }

  // 章内页码进度，pill 和 getDebugState 共用这一份（评审 D6）。只看 start.displayed：
  // start.percentage 在本项目里恒为假 0（locations 未生成，F2），不能进共享口径。
  function sectionProgressOf(location) {
    const displayed = location?.start?.displayed;
    if (!displayed?.total) return null;
    const percent = Math.round((displayed.page / displayed.total) * 100);
    if (Number.isNaN(percent)) return null;
    return { page: displayed.page, total: displayed.total, percent };
  }

  function updateProgress(location) {
    if (!progressIndicator) return;
    const progress = sectionProgressOf(location);
    let percentage = progress ? progress.percent : null;
    // percentage 回退只在没有 displayed.total 时生效：total 为真而页码是 NaN 时，
    // 原逻辑显示 0%，不回退（R4）。pill 文本必须逐字不变。
    if (!location?.start?.displayed?.total && typeof location?.start?.percentage === "number") {
      percentage = Math.round(location.start.percentage * 100);
    }
    if (percentage == null || Number.isNaN(percentage)) {
      percentage = 0;
    }
    progressIndicator.textContent = `当前阅读至 ${percentage}%`;
  }

  function displaySectionIndex(index) {
    const total = Number.isFinite(ctx.totalChapters) ? Number(ctx.totalChapters) : null;
    if (total != null && (index < 0 || index >= total)) return;
    const section = book.spine.get(index);
    if (!section) return;
    return rendition.display(section.href);
  }

  rendition.on("rendered", (section, contents) => {
    if (contents?.document && !contents.document.__reader3Bound) {
      contents.document.__reader3Bound = true;
      contents.document.addEventListener("click", () => {
        window.dispatchEvent(new CustomEvent("reader3:content:click"));
      });
      contents.document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
          window.dispatchEvent(new CustomEvent("reader3:escape"));
        }
      });
    }
    if (contents?.document && !contents.document.__reader3NavBound) {
      contents.document.__reader3NavBound = true;
      contents.document.addEventListener("keydown", (e) => {
        handleNavKey(e);
      });
    }
    const bodyText = contents?.document?.body?.textContent || "";
    console.log(`${logPrefix} rendered`, {
      sectionHref: section?.href,
      sectionIndex: section?.index,
      textSample: bodyText.slice(0, 80),
      textLength: bodyText.length,
    });
    if (section?.index != null) {
      currentSectionIndex = section.index;
      ctx.chapterIndex = currentSectionIndex;
      window.Reader3Ctx = ctx;
      updateTocActive(section.href);
      syncLocationToUrl();
      updateNavIndicator();
      updateNavButtons();
      window.dispatchEvent(new CustomEvent("reader3:chapter:change", {
        detail: { chapterIndex: currentSectionIndex },
      }));
    }
    currentContents = contents || null;
    ensureContentStyles(contents);
    notifyContentsReady(contents);
    window.dispatchEvent(new CustomEvent("reader3:content:rendered", {
      detail: { chapterIndex: currentSectionIndex },
    }));
  });

  rendition.on("relocated", (location) => updateProgress(location));

  book.ready.then(() => {
    const spineCount = book?.spine?.length ?? book?.spine?.items?.length ?? null;
    console.log(`${logPrefix} book ready`, { spineCount });
    updateNavIndicator();
    updateNavButtons();
    const section = book.spine.get(currentSectionIndex);
    const target = section ? section.href : undefined;
    console.log(`${logPrefix} display`, { target, currentSectionIndex });
    return rendition.display(target).then(() => {
      console.log(`${logPrefix} display resolved`, { target });
    });
  }).catch((err) => {
    console.error(`${logPrefix} display failed`, err);
  });

  if (prevLink) {
    prevLink.addEventListener("click", (e) => {
      e.preventDefault();
      displaySectionIndex(currentSectionIndex - 1);
    });
  }

  if (nextLink) {
    nextLink.addEventListener("click", (e) => {
      e.preventDefault();
      displaySectionIndex(currentSectionIndex + 1);
    });
  }

  function handleNavKey(e) {
    if (e.defaultPrevented) return false;
    const target = e.target;
    if (target?.tagName === "INPUT" || target?.tagName === "TEXTAREA") return false;
    if (target?.isContentEditable) return false;
    if (e.key === "ArrowRight" || e.key === "PageDown") {
      e.preventDefault();
      rendition.next();
      return true;
    }
    if (e.key === "ArrowLeft" || e.key === "PageUp") {
      e.preventDefault();
      rendition.prev();
      return true;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      displaySectionIndex(currentSectionIndex + 1);
      return true;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      displaySectionIndex(currentSectionIndex - 1);
      return true;
    }
    return false;
  }

  document.addEventListener("keydown", (e) => {
    handleNavKey(e);
  });

  window.addEventListener("resize", () => {
    const flow = window.innerWidth < 600 ? "scrolled-doc" : "paginated";
    if (typeof rendition.flow === "function") {
      rendition.flow(flow);
    }
    rendition.resize();
    if (currentContents) ensureContentStyles(currentContents);
  });

  // ---- 只读状态观测面（020，契约见 docs/plans/20260928-debug-state-getter.md §3）------
  //
  // 给 agent 和测试读阅读器状态用。只读缓存值：位置读 rendition.location（上一次
  // relocated 写入的快照），不调用 epub.js 的布局 API，也不读元素几何——那会强制
  // reflow（F4）。每个字段各自 try/catch，出错写进 errors（「字段: 消息」）并把该字段
  // 置 null，函数本身从不抛错。结果只含 JSON 原生值，不含书籍正文。
  const DIAG_LIMIT_DEFAULT = 20;
  const DIAG_LIMIT_MAX = 100;

  function diagLimitOf(opts) {
    const n = opts?.diagLimit;
    // 只认真正的有限数：全局 isFinite 会把 "5"、true 也放进来（R1）。
    if (typeof n !== "number" || !Number.isFinite(n)) return DIAG_LIMIT_DEFAULT;
    return Math.min(DIAG_LIMIT_MAX, Math.max(0, Math.floor(n)));
  }

  function narrowString(value, cap) {
    return typeof value === "string" ? value.slice(0, cap) : null;
  }

  function narrowNumber(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) return null;
    return value === 0 ? 0 : value; // -0 → 0，否则 JSON 往返不相等
  }

  function narrowBoolean(value) {
    return typeof value === "boolean" ? value : null;
  }

  // Reader3NotesDiag 挂在可写的 window 上，entries() 返回什么都不能信：逐字段收窄，
  // 非对象条目变成全 null 记录而不是丢掉，保证返回条数恰好是 diagLimit 截出的条数（R9）。
  function narrowDiagEntry(entry) {
    const src = entry !== null && typeof entry === "object" ? entry : {};
    return {
      op: narrowString(src.op, 32),
      requested: narrowBoolean(src.requested),
      status: narrowNumber(src.status),
      ok: narrowBoolean(src.ok),
      id: narrowString(src.id, 64),
      t: narrowNumber(src.t),
    };
  }

  function errorMessage(err) {
    try {
      return err && typeof err.message === "string" ? err.message : String(err);
    } catch {
      return "unknown error";
    }
  }

  function getDebugState(opts) {
    const errors = [];
    const fail = (field, err) => errors.push(`${field}: ${errorMessage(err)}`);

    // 读一次快照，后面的字段都从它派生；读取本身抛错时报在 cfi 上，派生字段降为 null。
    let location = null;
    try {
      location = rendition.location || null;
    } catch (err) {
      fail("cfi", err);
    }

    let cfi = null;
    try {
      const start = location?.start?.cfi;
      const end = location?.end?.cfi;
      if (typeof start === "string" && typeof end === "string") cfi = { start, end };
    } catch (err) {
      fail("cfi", err);
    }

    const section = {
      // rendered 回调原样写入 section.index，不保证是数。
      index: Number.isFinite(currentSectionIndex) ? currentSectionIndex : null,
      href: null,
      requestedIndex,
      spineCount: null,
    };
    try {
      // href 取位置快照，不取 rendered 回调里的 section：两者在换章瞬间可能不一致。
      const href = location?.start?.href;
      section.href = typeof href === "string" ? href : null;
    } catch (err) {
      fail("section.href", err);
    }
    try {
      section.spineCount = Number.isFinite(ctx.totalChapters) ? ctx.totalChapters : null;
    } catch (err) {
      fail("section.spineCount", err);
    }

    const progress = { sectionPage: null, sectionPercent: null, spinePercent: null, bookPercent: null };
    try {
      const sectionProgress = sectionProgressOf(location);
      // sectionProgressOf 原样透传 displayed，pill 要的就是这份逐字节不变；getter 这边再收窄：
      // 三个数里有一个不是有限数就整组给 null，-0 归 0，保证 JSON 往返不变（不变量 3，CP3 M1）。
      const page = narrowNumber(sectionProgress?.page);
      const total = narrowNumber(sectionProgress?.total);
      const percent = narrowNumber(sectionProgress?.percent);
      if (page !== null && total !== null && percent !== null) {
        progress.sectionPage = { page, total };
        progress.sectionPercent = percent;
      }
    } catch (err) {
      fail("progress.section", err);
    }
    // 与 notes-panel 同口径：index / (spineCount - 1)，截到 [0, 100]（R2）。两个输入都已
    // 收窄成有限数或 null，这里只是算术，不会抛错。
    if (section.index != null && section.spineCount != null && section.spineCount > 1) {
      const percent = Math.round((section.index / (section.spineCount - 1)) * 100);
      progress.spinePercent = Math.min(100, Math.max(0, percent));
    }

    let annotations = null;
    try {
      const doc = currentContents?.document;
      if (doc) {
        const marks = doc.querySelectorAll("[data-annotation-ids]");
        const ids = new Set();
        marks.forEach((mark) => {
          const parsed = JSON.parse(mark.getAttribute("data-annotation-ids"));
          // 解析成字符串会被 Set 拆成单个字符来数，非数组一律按坏数据处理（R7）。
          if (!Array.isArray(parsed)) throw new Error("data-annotation-ids is not an array");
          parsed.forEach((id) => ids.add(id));
        });
        annotations = { renderedIds: ids.size, marks: marks.length };
      }
    } catch (err) {
      annotations = null;
      fail("annotations", err);
    }

    let diag = [];
    let diagAvailable = false;
    try {
      // 调用时再查：生产里 annotations.js 在本脚本之后加载（F6）。
      const notesDiag = window.Reader3NotesDiag;
      diagAvailable = notesDiag != null;
      if (notesDiag != null) {
        const entries = notesDiag.entries();
        if (!Array.isArray(entries)) throw new Error("entries() did not return an array");
        const limit = diagLimitOf(opts);
        diag = entries.slice(Math.max(0, entries.length - limit)).map(narrowDiagEntry);
      }
    } catch (err) {
      diag = [];
      fail("diag", err);
    }

    return {
      v: 1,
      ready: location != null,
      cfi,
      section,
      progress,
      annotations,
      diag,
      diagAvailable,
      errors,
    };
  }

  window.Reader3Epub = {
    book,
    rendition,
    getContents: () => currentContents,
    getContentDocument: () => (currentContents ? currentContents.document : null),
    getContentRoot: () => (currentContents ? currentContents.document.body : null),
    getFrameElement: () => (currentContents ? currentContents.document.defaultView.frameElement : null),
    onContentsReady: (cb) => {
      if (typeof cb === "function") {
        contentsCallbacks.push(cb);
        if (currentContents) cb(currentContents);
      }
    },
    applyThemeSettings: (settings) => {
      // 参数可选：不给就沿用上一次宿主页给过的值（首屏之前是 localStorage）。
      // 给了就必须是两个有限数，否则宁可不动——半份设置比旧的整份更糟。
      if (settings) {
        const fontSize = Number(settings.fontSize);
        const lineHeight = Number(settings.lineHeight);
        if (Number.isFinite(fontSize) && Number.isFinite(lineHeight)) {
          hostFontSettings = { fontSize, lineHeight };
        }
      }
      if (currentContents) ensureContentStyles(currentContents);
    },
    displaySectionIndex,
    getDebugState,
  };
})();
