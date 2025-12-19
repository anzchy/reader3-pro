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

  class TOCPanel {
    constructor() {
      this.mode = qs("toc-mode");
      this.input = qs("toc-search-input");
      this.listRoot = qs("toc-list-root");

      this.input?.addEventListener("input", () => this.applyFilter());
    }

    open() {
      if (!this.mode) return;
      setOpen(this.mode, true);
      this.input?.focus();
      this.applyFilter();
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

    applyFilter() {
      if (!this.listRoot) return;
      const q = String(this.input?.value || "").trim().toLowerCase();
      const items = Array.from(this.listRoot.querySelectorAll("li.toc-item"));
      if (!q) {
        items.forEach((li) => (li.style.display = ""));
        return;
      }
      items.forEach((li) => {
        const a = li.querySelector("a.toc-link");
        const title = String(a?.textContent || "").trim().toLowerCase();
        li.style.display = title.includes(q) ? "" : "none";
      });
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const panel = new TOCPanel();
    window.Reader3TOCPanel = panel;
  });
})();

