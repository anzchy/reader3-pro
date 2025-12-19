(() => {
  function qs(id) {
    return document.getElementById(id);
  }

  function isOpen(el) {
    return !!el && el.classList.contains("is-open");
  }

  function setOpen(el, open) {
    if (!el) return;
    el.classList.toggle("is-open", !!open);
    el.setAttribute("aria-hidden", open ? "false" : "true");
  }

  function getCtx() {
    const ctx = window.Reader3Ctx || {};
    return {
      bookId: ctx.bookId || null,
      chapterIndex: Number.isFinite(ctx.chapterIndex) ? Number(ctx.chapterIndex) : null,
      totalChapters: Number.isFinite(ctx.totalChapters) ? Number(ctx.totalChapters) : null,
      title: ctx.title || "",
      coverUrl: ctx.coverUrl || null,
    };
  }

  function clamp(n, min, max) {
    return Math.max(min, Math.min(max, n));
  }

  class NotesPanel {
    constructor() {
      this.mode = qs("notes-mode");
      this.titleEl = qs("notes-title");
      this.progressEl = qs("notes-progress");
      this.countEl = qs("notes-count");
      this.coverEl = qs("notes-cover-img");
      this.body = qs("notes-body");
    }

    open() {
      if (!this.mode) return;
      setOpen(this.mode, true);
      this.renderHeader();
      this.loadAndRender().catch(() => {});
    }

    close() {
      if (!this.mode) return;
      setOpen(this.mode, false);
    }

    closeIfOpen() {
      if (!isOpen(this.mode)) return false;
      this.close();
      return true;
    }

    renderHeader() {
      const ctx = getCtx();
      if (this.titleEl) this.titleEl.textContent = ctx.title || "";
      if (this.coverEl) {
        if (ctx.coverUrl) this.coverEl.src = ctx.coverUrl;
        else this.coverEl.removeAttribute("src");
      }

      const total = ctx.totalChapters || 0;
      const idx = ctx.chapterIndex == null ? 0 : ctx.chapterIndex;
      const pct = total > 1 ? Math.round((idx / (total - 1)) * 100) : 0;
      if (this.progressEl) this.progressEl.textContent = `已读到${clamp(pct, 0, 100)}%`;
    }

    async loadAndRender() {
      const ctx = getCtx();
      if (!ctx.bookId || !this.body) return;
      const resp = await fetch(`/api/notes/${encodeURIComponent(ctx.bookId)}`);
      const data = await resp.json().catch(() => ({}));
      const groups = Array.isArray(data?.annotations_by_chapter) ? data.annotations_by_chapter : [];
      const totalCount = Number.isFinite(data?.total_count) ? Number(data.total_count) : 0;
      if (this.countEl) this.countEl.textContent = `共${totalCount}条笔记`;

      this.body.innerHTML = "";

      if (!groups.length || totalCount === 0) {
        const empty = document.createElement("div");
        empty.className = "notes-empty";
        empty.textContent = "你可以在这里记录本书的想法、划线、书签";
        this.body.appendChild(empty);
        return;
      }

      for (const g of groups) {
        const chapterTitle = String(g?.chapter_title || "");
        const chapterIndex = Number(g?.chapter_index || 0);
        const anns = Array.isArray(g?.annotations) ? g.annotations : [];

        const groupEl = document.createElement("div");
        groupEl.className = "notes-group";

        const titleEl = document.createElement("div");
        titleEl.className = "notes-group-title";
        titleEl.textContent = chapterTitle || `Chapter ${chapterIndex + 1}`;
        groupEl.appendChild(titleEl);

        for (const ann of anns) {
          const id = String(ann?.id || "");
          const quote = String(ann?.quote || "");
          const noteText = ann?.note_text == null ? "" : String(ann.note_text);

          const item = document.createElement("div");
          item.className = "notes-item";
          item.tabIndex = 0;
          item.addEventListener("click", () => {
            if (!ctx.bookId) return;
            const url = `/read/${encodeURIComponent(ctx.bookId)}/${encodeURIComponent(String(chapterIndex))}?note_id=${encodeURIComponent(id)}`;
            window.location.href = url;
          });

          const quoteEl = document.createElement("div");
          quoteEl.className = "notes-item-quote";
          quoteEl.textContent = quote;
          item.appendChild(quoteEl);

          if (noteText) {
            const noteEl = document.createElement("div");
            noteEl.className = "notes-item-note";
            noteEl.textContent = noteText;
            item.appendChild(noteEl);
          }

          groupEl.appendChild(item);
        }

        this.body.appendChild(groupEl);
      }
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const panel = new NotesPanel();
    window.Reader3NotesPanel = panel;
  });
})();

