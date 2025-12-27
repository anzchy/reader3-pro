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

  function closeSearchDrawer() {
    const drawer = qs("reader-search-drawer");
    if (!drawer) return false;
    if (!drawer.classList.contains("is-open")) return false;
    drawer.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");
    return true;
  }

  function closeAiPanel() {
    const panel = qs("reader-ai-panel");
    if (!panel) return false;
    if (!panel.classList.contains("is-open")) return false;
    panel.classList.remove("is-open");
    panel.setAttribute("aria-hidden", "true");
    return true;
  }

  function closeAllPanels() {
    const closed = [closeSearchDrawer(), closeAiPanel()];
    resetFocusAfterClose();
    return closed.some(Boolean);
  }

  function isInside(el, selectors) {
    if (!el) return false;
    return selectors.some((sel) => el.closest(sel));
  }

  function resetFocusAfterClose() {
    const active = document.activeElement;
    if (!active || active === document.body) return;
    const focusTargets = [
      "#toc-mode",
      "#notes-mode",
      "#reader-search-drawer",
      "#reader-ai-panel",
      "#font-settings-popup",
      "#annotation-toolbar",
      "#note-editor",
    ];
    if (active.closest && focusTargets.some((sel) => active.closest(sel))) {
      active.blur();
    }
  }

  class RightToolbar {
    constructor() {
      this.btnToc = qs("reader-toc-toggle");
      this.btnSearch = qs("reader-search-toggle");
      this.btnAi = qs("reader-ai-toggle");
      this.btnNotes = qs("reader-notes-toggle");

      this.tocMode = qs("toc-mode");
      this.notesMode = qs("notes-mode");

      this._savedScrollTop = null;

      this.btnToc?.addEventListener("click", () => this.toggle("toc"));
      this.btnNotes?.addEventListener("click", () => this.toggle("notes"));

      // Ensure mutual exclusion even when Search/AI are toggled by their own modules.
      this.btnSearch?.addEventListener(
        "click",
        () => {
          this.close("toc");
          this.close("notes");
          this._syncActive();
        },
        true
      );
      this.btnAi?.addEventListener(
        "click",
        () => {
          this.close("toc");
          this.close("notes");
          this._syncActive();
        },
        true
      );

      document.addEventListener(
        "click",
        (e) => {
          const target = e.target;
          const ignoreSelectors = [
            "#toc-mode",
            "#notes-mode",
            "#reader-search-drawer",
            "#reader-ai-panel",
            "#annotation-toolbar",
            "#note-editor",
            "#right-toolbar",
            "#reader-toc-toggle",
            "#reader-search-toggle",
            "#reader-ai-toggle",
            "#reader-notes-toggle",
            "#font-settings-popup",
            "#reader-font-toggle",
          ];
          if (isInside(target, ignoreSelectors)) return;
          const closedPanels = closeAllPanels();
          const closedModes = this.close("toc") || this.close("notes");
          if (closedPanels || closedModes) {
            e.preventDefault();
          }
        },
        true
      );

      window.addEventListener("reader3:content:click", () => {
        closeAllPanels();
        this.close("toc");
        this.close("notes");
        resetFocusAfterClose();
      });

      window.addEventListener("reader3:escape", () => {
        if (closeAllPanels()) return;
        this.close("toc");
        this.close("notes");
        resetFocusAfterClose();
      });

      const watch = (el) => {
        if (!el) return;
        const obs = new MutationObserver(() => this._syncActive());
        obs.observe(el, { attributes: true, attributeFilter: ["class"] });
      };
      watch(qs("reader-search-drawer"));
      watch(qs("reader-ai-panel"));

      document.addEventListener(
        "keydown",
        (e) => {
          if (e.key !== "Escape") return;

          if (window.Reader3AnnotationUI?.closeNoteEditorIfOpen?.()) {
            e.preventDefault();
            e.stopPropagation();
            return;
          }
          if (window.Reader3AnnotationUI?.closeSelectionToolbarIfOpen?.()) {
            e.preventDefault();
            e.stopPropagation();
            return;
          }
          if (isOpen(this.tocMode)) {
            this.close("toc");
            e.preventDefault();
            e.stopPropagation();
            return;
          }
          if (isOpen(this.notesMode)) {
            this.close("notes");
            e.preventDefault();
            e.stopPropagation();
            return;
          }
          if (closeAllPanels()) {
            e.preventDefault();
            e.stopPropagation();
          }
        },
        true
      );
    }

    _saveScroll() {
      const main = qs("main");
      if (!main) return;
      this._savedScrollTop = main.scrollTop;
    }

    _restoreScroll() {
      const main = qs("main");
      if (!main) return;
      if (this._savedScrollTop == null) return;
      main.scrollTop = this._savedScrollTop;
      this._savedScrollTop = null;
    }

    _openMode(mode) {
      const body = document.body;
      this._saveScroll();
      body.classList.add("reader-mode-open");

      // Close the other tool panels (Search/AI).
      closeSearchDrawer();
      closeAiPanel();

      if (mode === "toc") {
        setOpen(this.tocMode, true);
        setOpen(this.notesMode, false);
        window.Reader3TOCPanel?.open?.();
      } else if (mode === "notes") {
        setOpen(this.notesMode, true);
        setOpen(this.tocMode, false);
        window.Reader3NotesPanel?.open?.();
      }
    }

    _closeAllModes() {
      setOpen(this.tocMode, false);
      setOpen(this.notesMode, false);
      document.body.classList.remove("reader-mode-open");
      this._restoreScroll();
    }

    toggle(mode) {
      if (mode === "toc") {
        if (isOpen(this.tocMode)) {
          this.close("toc");
          return;
        }
        this._openMode("toc");
        this._syncActive();
        return;
      }
      if (mode === "notes") {
        if (isOpen(this.notesMode)) {
          this.close("notes");
          return;
        }
        this._openMode("notes");
        this._syncActive();
      }
    }

    close(mode) {
      const wasTocOpen = isOpen(this.tocMode);
      const wasNotesOpen = isOpen(this.notesMode);
      if (mode === "toc") setOpen(this.tocMode, false);
      if (mode === "notes") setOpen(this.notesMode, false);

      if (!isOpen(this.tocMode) && !isOpen(this.notesMode)) {
        document.body.classList.remove("reader-mode-open");
        this._restoreScroll();
      }
      this._syncActive();
      resetFocusAfterClose();
      if (mode === "toc") return wasTocOpen;
      if (mode === "notes") return wasNotesOpen;
      return false;
    }

    _syncActive() {
      const tocOpen = isOpen(this.tocMode);
      const notesOpen = isOpen(this.notesMode);
      const searchOpen = isOpen(qs("reader-search-drawer"));
      const aiOpen = isOpen(qs("reader-ai-panel"));

      this.btnToc?.classList.toggle("is-active", tocOpen);
      this.btnNotes?.classList.toggle("is-active", notesOpen);
      this.btnSearch?.classList.toggle("is-active", searchOpen);
      this.btnAi?.classList.toggle("is-active", aiOpen);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const toolbar = new RightToolbar();
    window.Reader3Toolbar = toolbar;
    toolbar._syncActive();
  });
})();
