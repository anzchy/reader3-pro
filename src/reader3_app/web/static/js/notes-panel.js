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
      this.copyCountEl = qs("notes-copy-count");
      this.coverEl = qs("notes-cover-img");
      this.body = qs("notes-body");
      this.copyBtn = qs("notes-copy-btn");
      this.allAnnotations = [];

      // Setup copy button handler
      if (this.copyBtn) {
        this.copyBtn.addEventListener("click", () => this.copyAllNotes());
      }
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

      // Update counts
      if (this.countEl) this.countEl.textContent = `共${totalCount}条笔记`;
      if (this.copyCountEl) this.copyCountEl.textContent = totalCount;

      // Store all annotations for copy function
      this.allAnnotations = groups;

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
          const hasNote = !!noteText;

          const item = document.createElement("div");
          item.className = "notes-item" + (hasNote ? " has-note" : "");
          item.tabIndex = 0;
          item.addEventListener("click", () => {
            if (!ctx.bookId) return;
            const url = `/read/${encodeURIComponent(ctx.bookId)}/${encodeURIComponent(String(chapterIndex))}?note_id=${encodeURIComponent(id)}`;
            window.location.href = url;
          });

          // Icon - A for highlights, speech bubble for notes
          const iconEl = document.createElement("div");
          iconEl.className = "notes-item-icon" + (hasNote ? " is-note" : "");
          iconEl.innerHTML = hasNote
            ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>'
            : '<span style="font-family: serif; font-style: italic;">A</span>';
          item.appendChild(iconEl);

          // Content container
          const contentEl = document.createElement("div");
          contentEl.className = "notes-item-content";

          // For notes: show note text first, then quote
          if (hasNote) {
            const noteEl = document.createElement("div");
            noteEl.className = "notes-item-note";
            noteEl.textContent = noteText;
            contentEl.appendChild(noteEl);
          }

          const quoteEl = document.createElement("div");
          quoteEl.className = "notes-item-quote";
          quoteEl.textContent = quote;
          contentEl.appendChild(quoteEl);

          item.appendChild(contentEl);
          groupEl.appendChild(item);
        }

        this.body.appendChild(groupEl);
      }
    }

    copyAllNotes() {
      if (!this.allAnnotations.length) return;

      const ctx = getCtx();
      let text = `《${ctx.title || ""}》笔记摘录\n\n`;

      for (const g of this.allAnnotations) {
        const chapterTitle = String(g?.chapter_title || "");
        const anns = Array.isArray(g?.annotations) ? g.annotations : [];

        if (anns.length) {
          text += `## ${chapterTitle}\n\n`;
          for (const ann of anns) {
            const quote = String(ann?.quote || "");
            const noteText = ann?.note_text || "";

            text += `> ${quote}\n`;
            if (noteText) {
              text += `\n💭 ${noteText}\n`;
            }
            text += `\n`;
          }
        }
      }

      navigator.clipboard?.writeText?.(text).then(() => {
        // Show brief feedback
        if (this.copyBtn) {
          const originalText = this.copyBtn.innerHTML;
          this.copyBtn.innerHTML = "已复制!";
          setTimeout(() => {
            this.copyBtn.innerHTML = originalText;
          }, 1500);
        }
      }).catch(() => {});
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const panel = new NotesPanel();
    window.Reader3NotesPanel = panel;

    // Listen for annotation updates to refresh the notes panel
    window.addEventListener("reader3:annotations:updated", () => {
      if (isOpen(panel.mode)) {
        panel.loadAndRender().catch(() => {});
      }
    });
  });
})();

