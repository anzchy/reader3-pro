const { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } = React;
const D = window.ReaderProData;

/* ------------------------------------------------------------------ */
/* Focus management                                                     */
/* ------------------------------------------------------------------ */

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])'
].join(",");

/* Traps Tab inside `ref`, focuses the first control on open, and returns focus
   to whatever was focused before. Spec §2.2 / §4.1 require this for Library
   dialogs; §10.2 item 6 lists its absence on Reader panels as a gap, so every
   overlay in this prototype uses it. */
function useFocusTrap(ref, active, onClose) {
  useEffect(() => {
    if (!active || !ref.current) return undefined;
    const node = ref.current;
    const previous = document.activeElement;

    const items = () => Array.from(node.querySelectorAll(FOCUSABLE)).filter((el) => el.offsetParent !== null || el === document.activeElement);
    const first = items()[0];
    if (first) first.focus();
    else node.focus();

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose && onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const list = items();
      if (!list.length) return;
      const firstItem = list[0];
      const lastItem = list[list.length - 1];
      if (event.shiftKey && document.activeElement === firstItem) {
        event.preventDefault();
        lastItem.focus();
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault();
        firstItem.focus();
      }
    };

    node.addEventListener("keydown", onKeyDown);
    return () => {
      node.removeEventListener("keydown", onKeyDown);
      if (previous && typeof previous.focus === "function") previous.focus();
    };
  }, [active, onClose, ref]);
}

/* ------------------------------------------------------------------ */
/* 跨页共享 chrome 的 testid（0.5）                                     */
/* ------------------------------------------------------------------ */
/* TopBar / Modal / ConfirmModal / LiveRegion 这几个 DOM 节点在书库、阅读器、
   设置三个页面各出现一次，而命名方案只有 lib- / rd- / set- 三个前缀，没有
   「共享」这一档。所以组件内部不写死 testid：调用点传 page，组件从这张静态
   表里取。表里全是字符串字面量，命名 lint 扫得到，仓库里 grep 得到——这正是
   设计规格 §4 规则 5 说的「改静态映射表」。 */
const SHARED_TESTIDS = {
  lib: {
    liveRegion: "lib-live-region",
    topbar: "lib-topbar", brand: "lib-brand", themeToggle: "lib-theme-toggle",
    mobileMenu: "lib-topbar-mobile-menu", mobileInsights: "lib-topbar-mobile-insights",
    navLibrary: "lib-topbar-nav-library", navSettings: "lib-topbar-nav-settings",
    addBooks: "lib-topbar-add-books", backToLibrary: "lib-topbar-back-to-library",
  },
  rd: {
    liveRegion: "rd-live-region",
    topbar: "rd-topbar", brand: "rd-brand", themeToggle: "rd-theme-toggle",
    mobileMenu: "rd-topbar-mobile-menu", mobileInsights: "rd-topbar-mobile-insights",
    navLibrary: "rd-topbar-nav-library", navSettings: "rd-topbar-nav-settings",
    addBooks: "rd-topbar-add-books", backToLibrary: "rd-topbar-back-to-library",
  },
  set: {
    liveRegion: "set-live-region",
    topbar: "set-topbar", brand: "set-brand", themeToggle: "set-theme-toggle",
    mobileMenu: "set-topbar-mobile-menu", mobileInsights: "set-topbar-mobile-insights",
    navLibrary: "set-topbar-nav-library", navSettings: "set-topbar-nav-settings",
    addBooks: "set-topbar-add-books", backToLibrary: "set-topbar-back-to-library",
  },
};

/* ------------------------------------------------------------------ */
/* 弹层的 testid：有界枚举表（ADR-0014）                                 */
/* ------------------------------------------------------------------ */
/* 14 个弹层是编译期可枚举的有界集合，所以每个成员各有唯一的 data-testid
   字面量，而不是共用一个名字再挂判别位——裁决见
   docs/adr/0014-bounded-testid-enumeration.md。键是 Modal / ConfirmModal 的
   `modal` prop（settings.jsx 传的是运行期变量，所以只能查表，不能写成字面量
   prop）；值按 -close / -cancel / -primary / -body 派生。唯一的保留名例外是
   note-editor，宿主沿用契约已定的 rd-note-editor。 */
const MODAL_TESTIDS = {
  "add-books": { root: "lib-modal-add-books", close: "lib-modal-add-books-close", cancel: "lib-modal-add-books-cancel", primary: "lib-modal-add-books-primary", body: "lib-modal-add-books-body" },
  "index-errors": { root: "lib-modal-index-errors", close: "lib-modal-index-errors-close", cancel: "lib-modal-index-errors-cancel", primary: "lib-modal-index-errors-primary", body: "lib-modal-index-errors-body" },
  "create-collection": { root: "lib-modal-create-collection", close: "lib-modal-create-collection-close", cancel: "lib-modal-create-collection-cancel", primary: "lib-modal-create-collection-primary", body: "lib-modal-create-collection-body" },
  "rename-collection": { root: "lib-modal-rename-collection", close: "lib-modal-rename-collection-close", cancel: "lib-modal-rename-collection-cancel", primary: "lib-modal-rename-collection-primary", body: "lib-modal-rename-collection-body" },
  "delete-collection": { root: "lib-modal-delete-collection", close: "lib-modal-delete-collection-close", cancel: "lib-modal-delete-collection-cancel", primary: "lib-modal-delete-collection-primary", body: "lib-modal-delete-collection-body" },
  "clean-collection": { root: "lib-modal-clean-collection", close: "lib-modal-clean-collection-close", cancel: "lib-modal-clean-collection-cancel", primary: "lib-modal-clean-collection-primary", body: "lib-modal-clean-collection-body" },
  "add-to-collection": { root: "lib-modal-add-to-collection", close: "lib-modal-add-to-collection-close", cancel: "lib-modal-add-to-collection-cancel", primary: "lib-modal-add-to-collection-primary", body: "lib-modal-add-to-collection-body" },

  "note-editor": { root: "rd-note-editor", close: "rd-note-editor-close", cancel: "rd-note-editor-cancel", primary: "rd-note-editor-primary", body: "rd-note-editor-body" },
  "clear-conversation": { root: "rd-modal-clear-conversation", close: "rd-modal-clear-conversation-close", cancel: "rd-modal-clear-conversation-cancel", primary: "rd-modal-clear-conversation-primary", body: "rd-modal-clear-conversation-body" },
  "delete-note": { root: "rd-modal-delete-note", close: "rd-modal-delete-note-close", cancel: "rd-modal-delete-note-cancel", primary: "rd-modal-delete-note-primary", body: "rd-modal-delete-note-body" },
  "notes-review": { root: "rd-modal-notes-review", close: "rd-modal-notes-review-close", cancel: "rd-modal-notes-review-cancel", primary: "rd-modal-notes-review-primary", body: "rd-modal-notes-review-body" },

  "reindex": { root: "set-modal-reindex", close: "set-modal-reindex-close", cancel: "set-modal-reindex-cancel", primary: "set-modal-reindex-primary", body: "set-modal-reindex-body" },
  "conversations": { root: "set-modal-conversations", close: "set-modal-conversations-close", cancel: "set-modal-conversations-cancel", primary: "set-modal-conversations-primary", body: "set-modal-conversations-body" },
  "cache": { root: "set-modal-cache", close: "set-modal-cache-close", cancel: "set-modal-cache-cancel", primary: "set-modal-cache-primary", body: "set-modal-cache-body" },
};

/* Screen-reader announcements (spec §3.1 "Live region"). */
function LiveRegion(props) {
  const t = SHARED_TESTIDS[props.page];
  return <div className="sr-only" role="status" aria-live="polite" data-testid={t.liveRegion}>{props.message}</div>;
}

/* ------------------------------------------------------------------ */
/* Primitives                                                           */
/* ------------------------------------------------------------------ */

function Brand(props) {
  const t = SHARED_TESTIDS[props.page];
  return (
    <div className="brand" data-testid={t.brand}>
      <span className="brand-mark" aria-hidden="true">R3</span>
      <span>Reader3 Pro</span>
    </div>
  );
}

function Toggle(props) {
  const { checked, onChange, label } = props;
  return (
    <button
      className={"toggle " + (checked ? "is-on" : "")}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      data-testid={props["data-testid"]}
      data-provider={props["data-provider"]}
      onClick={(event) => {
        event.stopPropagation();
        onChange(!checked);
      }}
    >
      <span className="toggle-knob" aria-hidden="true"></span>
    </button>
  );
}

function ThemeToggle(props) {
  const { theme, onTheme } = props;
  const t = SHARED_TESTIDS[props.page];
  const next = { light: "dark", dark: "system", system: "light" };
  const glyph = { light: "☀", dark: "☾", system: "◐" };
  const title = { light: "Theme: light", dark: "Theme: dark", system: "Theme: follow system" };
  return (
    <button
      className="btn btn-icon"
      type="button"
      aria-label={title[theme] + " — click to change"}
      title={title[theme]}
      data-testid={t.themeToggle}
      onClick={() => onTheme(next[theme])}
    >
      {glyph[theme]}
    </button>
  );
}

/* 弹层是有界集合：每个各有唯一 testid，从 MODAL_TESTIDS 查表取。
   判别位 data-modal 已删除——理由见 docs/adr/0014-bounded-testid-enumeration.md。 */
function Modal(props) {
  const { title, children, onClose, primaryLabel, onPrimary, tone, cancelLabel, size, modal } = props;
  const t = MODAL_TESTIDS[modal];
  const ref = useRef(null);
  useFocusTrap(ref, true, onClose);

  return (
    <div className="overlay" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section
        className={"modal " + (size === "wide" ? "is-wide" : "")}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex="-1"
        ref={ref}
        data-testid={t.root}
      >
        <header className="modal-header">
          <h2 className="modal-title">{title}</h2>
          <button className="btn btn-icon" type="button" aria-label="Close dialog" style={{marginLeft: "auto"}} data-testid={t.close} onClick={onClose}>×</button>
        </header>
        <div className="modal-body">{children}</div>
        {primaryLabel && (
          <footer className="modal-footer">
            <button className="btn" type="button" data-testid={t.cancel} onClick={onClose}>{cancelLabel || "Cancel"}</button>
            <button className={"btn " + (tone === "danger" ? "btn-danger" : "btn-primary")} type="button" data-testid={t.primary} onClick={onPrimary}>{primaryLabel}</button>
          </footer>
        )}
      </section>
    </div>
  );
}

/* Destructive actions must confirm (spec §4.3 Data, §4.1 item 7). */
function ConfirmModal(props) {
  const { title, body, confirmLabel, onCancel, onConfirm, modal } = props;
  const t = MODAL_TESTIDS[modal];
  return (
    <Modal modal={modal} title={title} primaryLabel={confirmLabel} tone="danger" onClose={onCancel} onPrimary={onConfirm}>
      <p className="empty-copy" style={{fontSize: "13px"}} data-testid={t.body}>{body}</p>
    </Modal>
  );
}

/* ------------------------------------------------------------------ */
/* Shell                                                                */
/* ------------------------------------------------------------------ */

function TopBar(props) {
  const { screen, onScreen, onAdd, onMobileMenu, onMobileInsights, theme, onTheme } = props;
  /* 原型是单页外壳，同一条 TopBar 在两个 screen 下复用；生产是两张 Jinja 页，
     各自渲染自己那一份。testid 跟 screen 走，两侧因此一致。 */
  const page = screen === "settings" ? "set" : "lib";
  const t = SHARED_TESTIDS[page];

  return (
    <header className="topbar" data-testid={t.topbar}>
      {screen === "library" && (
        <button className="btn btn-icon mobile-only" type="button" aria-label="Open library navigation" data-testid={t.mobileMenu} onClick={onMobileMenu}>☰</button>
      )}
      <Brand page={page} />
      <nav className="topnav" aria-label="Primary navigation">
        <button className={"topnav-button " + (screen === "library" ? "is-active" : "")} type="button" data-testid={t.navLibrary} onClick={() => onScreen("library")}>My Library</button>
        <button className={"topnav-button " + (screen === "settings" ? "is-active" : "")} type="button" data-testid={t.navSettings} onClick={() => onScreen("settings")}>Settings</button>
      </nav>
      <div className="topbar-actions">
        <ThemeToggle page={page} theme={theme} onTheme={onTheme} />
        {screen === "library" && (
          <>
            <button className="btn btn-icon mobile-only tablet-visible" type="button" aria-label="Open insights panel" data-testid={t.mobileInsights} onClick={onMobileInsights}>◎</button>
            <button className="btn btn-primary" type="button" data-testid={t.addBooks} onClick={onAdd}>Add books</button>
          </>
        )}
        {screen === "settings" && (
          <button className="btn" type="button" data-testid={t.backToLibrary} onClick={() => onScreen("library")}>Back to Library</button>
        )}
      </div>
    </header>
  );
}

/* ------------------------------------------------------------------ */
/* Library sidebar                                                      */
/* ------------------------------------------------------------------ */

function CollectionRow(props) {
  const { collection, active, onScope, onRename, onDelete, onClean } = props;
  const [menu, setMenu] = useState(false);

  useEffect(() => {
    if (!menu) return undefined;
    const close = () => setMenu(false);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [menu]);

  return (
    <div className="collection-item">
      <button className={"sidebar-row " + (active ? "is-active" : "")} type="button" data-testid="lib-sidebar-collection" data-collection-id={collection.id} onClick={() => onScope(collection.id)}>
        <span className="sidebar-icon" aria-hidden="true">{collection.name.charAt(0).toUpperCase()}</span>
        <span className="row-label">{collection.name}</span>
        {collection.stale ? <span className="stale-dot" title={collection.stale + " missing book(s)"} aria-label={collection.stale + " missing books"}>!</span> : null}
        <span className="count-badge">{collection.book_ids.length - (collection.stale || 0)}</span>
      </button>
      <button
        className="row-more"
        type="button"
        aria-label={"Actions for " + collection.name}
        aria-expanded={menu}
        data-testid="lib-sidebar-collection-menu-toggle" data-collection-id={collection.id}
        onClick={(event) => {
          event.stopPropagation();
          setMenu((current) => !current);
        }}
      >⋯</button>
      {menu && (
        <div className="row-menu" role="menu" data-testid="lib-sidebar-collection-menu" data-collection-id={collection.id}>
          <button className="row-menu-item" type="button" role="menuitem" onClick={() => onRename(collection)}>Rename…</button>
          <button className="row-menu-item" type="button" role="menuitem" disabled={!collection.stale} onClick={() => onClean(collection)}>
            Remove {collection.stale || 0} missing book{collection.stale === 1 ? "" : "s"}
          </button>
          <button className="row-menu-item is-danger" type="button" role="menuitem" onClick={() => onDelete(collection)}>Delete collection…</button>
        </div>
      )}
    </div>
  );
}

function LibrarySidebar(props) {
  const { scope, onScope, collections, counts, onCreateCollection, onRenameCollection, onDeleteCollection, onCleanCollection } = props;
  return (
    <aside className="library-sidebar" aria-label="Library navigation" data-testid="lib-sidebar">
      <section className="sidebar-section">
        <p className="section-eyebrow">Types</p>
        <button className={"sidebar-row " + (scope === "all" ? "is-active" : "")} type="button" data-testid="lib-sidebar-scope-all" onClick={() => onScope("all")}>
          <span className="sidebar-icon" aria-hidden="true">A</span>
          <span className="row-label">All Books</span>
          <span className="count-badge">{counts.all}</span>
        </button>
        <button className={"sidebar-row " + (scope === "epub" ? "is-active" : "")} type="button" data-testid="lib-sidebar-scope-epub" onClick={() => onScope("epub")}>
          <span className="sidebar-icon" aria-hidden="true">E</span>
          <span className="row-label">EPUB</span>
          <span className="count-badge">{counts.epub}</span>
        </button>
        <button className="sidebar-row is-disabled" type="button" disabled title="PDF not supported yet" data-testid="lib-sidebar-scope-pdf">
          <span className="sidebar-icon" aria-hidden="true">P</span>
          <span className="row-label">PDF</span>
          <span className="count-badge">0</span>
        </button>
      </section>
      <section className="sidebar-section">
        <div className="sidebar-heading-row">
          <p className="section-eyebrow">Collections</p>
          <button className="mini-add" type="button" aria-label="Create collection" data-testid="lib-sidebar-create-collection" onClick={onCreateCollection}>+</button>
        </div>
        {collections.length === 0 && <p className="empty-copy" style={{margin: "4px 10px"}}>No collections yet.</p>}
        {collections.map((collection) => (
          <CollectionRow
            key={collection.id}
            collection={collection}
            active={scope === collection.id}
            onScope={onScope}
            onRename={onRenameCollection}
            onDelete={onDeleteCollection}
            onClean={onCleanCollection}
          />
        ))}
      </section>
    </aside>
  );
}

/* ------------------------------------------------------------------ */
/* Book views                                                           */
/* ------------------------------------------------------------------ */

/* 0.5：testid 值必须是字面量，不能拼。取值集合写死的走静态映射表；
   取值来自用户数据的（书、集合、笔记、会话）走「字面量 testid + 另一个
   data-* 携带 id」，见本文件里的 lib-book-card / lib-sidebar-collection。 */
const LIB_BOOK_STATUS_TESTID = {
  not_indexed: "lib-book-status-not-indexed",
  indexing: "lib-book-status-indexing",
  indexed: "lib-book-status-indexed",
  error: "lib-book-status-error",
  // 2026-09-25 013 WI-13（裁定 D12，原型先行）：WI-3 的六态收敛——stale（索引指纹过期）与
  // unknown（状态读不出来）。unknown 不许回落成 not_indexed 的文案（WI-3 验收 3）。
  stale: "lib-book-status-stale",
  unknown: "lib-book-status-unknown",
};

const LIB_CHAT_MSG_TESTID = {
  user: "lib-chat-msg-user",
  assistant: "lib-chat-msg-assistant",
};

const LIB_PANEL_TAB_TESTID = {
  dashboard: "lib-panel-tab-dashboard",
  chat: "lib-panel-tab-chat",
  search: "lib-panel-tab-search",
};

const STATUS_META = {
  not_indexed: { label: "Not indexed", tone: "warn" },
  indexing: { label: "Indexing…", tone: "busy" },
  indexed: { label: "Indexed", tone: "ok" },
  error: { label: "Index error", tone: "bad" },
  stale: { label: "Index stale", tone: "warn" },
  unknown: { label: "Status unknown", tone: "muted" }
};

function StatusPill(props) {
  // 2026-09-25（WI-3 验收 3 / C9）：枚举外的值落到 unknown，不再冒充 not_indexed。
  const meta = STATUS_META[props.status] || STATUS_META.unknown;
  return (
    <span className={"status-pill is-" + meta.tone} data-testid={LIB_BOOK_STATUS_TESTID[props.status] || LIB_BOOK_STATUS_TESTID.unknown}>
      {props.status === "indexing" && <span className="spinner" aria-hidden="true"></span>}
      {meta.label}
    </span>
  );
}

function CoverImage(props) {
  const { book } = props;
  if (book.cover) return <img className="book-cover" src={book.cover} alt={"Cover of " + book.title} />;
  return (
    <div className="book-cover book-cover-fallback" role="img" aria-label={"No cover art for " + book.title}>
      <span>{book.title}</span>
      <small>{book.author}</small>
    </div>
  );
}

function BookCard(props) {
  const { book, selectionMode, selected, onToggleSelected, onOpenReader } = props;
  const handleActivate = () => {
    if (selectionMode) onToggleSelected(book.id);
    else onOpenReader(book);
  };

  return (
    <div
      className={"book-card " + (selected ? "is-selected" : "")}
      role="button"
      tabIndex="0"
      aria-pressed={selectionMode ? selected : undefined}
      aria-label={book.title + " by " + book.author}
      data-testid="lib-book-card" data-book-id={book.id}
      onClick={handleActivate}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          handleActivate();
        }
      }}
    >
      {selectionMode && <span className={"selection-check " + (selected ? "" : "is-empty")} aria-hidden="true">{selected ? "✓" : ""}</span>}
      <div className="book-cover-wrap">
        <CoverImage book={book} />
        <StatusPill status={book.index_status} />
      </div>
      <div className="book-meta">
        <h2 className="book-title">{book.title}</h2>
        <p className="book-author">{book.author}</p>
        <p className="book-sub">{book.section_count} sections · {book.chunk_count} chunks</p>
        <div className="book-progress" aria-label={"Reading progress " + book.progress + "%"}>
          <div className="progress-track"><div className="progress-fill" style={{width: book.progress + "%"}}></div></div>
          <span>{book.progress}%</span>
        </div>
      </div>
    </div>
  );
}

/* List view is a real table (spec §6.1: Title / Author / Chunks / Sections / Status / Read). */
function BookTable(props) {
  const { books, selectionMode, selectedIds, onToggleSelected, onOpenReader } = props;
  return (
    <div className="table-wrap">
      <table className="book-table" data-testid="lib-book-table">
        <thead>
          <tr>
            {selectionMode && <th scope="col" className="col-check"><span className="sr-only">Selected</span></th>}
            <th scope="col">Title</th>
            <th scope="col">Author</th>
            <th scope="col" className="col-num">Chunks</th>
            <th scope="col" className="col-num">Sections</th>
            <th scope="col">Status</th>
            <th scope="col" className="col-num">Read</th>
          </tr>
        </thead>
        <tbody>
          {books.map((book) => (
            <tr key={book.id} data-testid="lib-book-row" data-book-id={book.id}>
              {selectionMode && (
                <td className="col-check">
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(book.id)}
                    aria-label={"Select " + book.title}
                    onChange={() => onToggleSelected(book.id)}
                  />
                </td>
              )}
              <th scope="row">
                <button className="link-button" type="button" onClick={() => onOpenReader(book)}>{book.title}</button>
              </th>
              <td>{book.author}</td>
              <td className="col-num">{book.chunk_count}</td>
              <td className="col-num">{book.section_count}</td>
              <td><StatusPill status={book.index_status} /></td>
              <td className="col-num">{book.progress}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Right panel: Dashboard / Chat / Search                               */
/* ------------------------------------------------------------------ */

function DashboardPanel(props) {
  const indexed = D.books.filter((b) => b.index_status === "indexed").length;
  const pct = Math.round((indexed / D.books.length) * 100);
  return (
    <div className="panel-content" data-testid="lib-panel-dashboard">
      <div className="panel-title-row">
        <h2 className="panel-title">Library overview</h2>
        <button className="text-button" type="button" data-testid="lib-panel-refresh-stats" onClick={props.onRefresh}>Refresh stats</button>
      </div>
      <div className="stats-grid">
        {D.stats.map((stat) => (
          <div className="stat-card" key={stat.label}>
            <div className="stat-label">{stat.label}</div>
            <div className="stat-value">{stat.value}</div>
            <div className="stat-note">{stat.note}</div>
          </div>
        ))}
      </div>
      <div className="index-card">
        <div className="index-copy"><span>Semantic index</span><strong>{indexed} of {D.books.length}</strong></div>
        <div className="progress-track"><div className="progress-fill" style={{width: pct + "%"}}></div></div>
        <p className="empty-copy">Indexing a book enables semantic search and grounded AI answers. Dashboard progress counts indexed books, not reading progress.</p>
        <div className="settings-actions" style={{marginTop: "12px"}}>
          <button className="btn btn-primary" type="button" data-testid="lib-panel-index-remaining">Index remaining</button>
          <button className="btn" type="button" data-testid="lib-panel-open-index-errors" onClick={props.onShowErrors}>View 1 error</button>
        </div>
      </div>
    </div>
  );
}

function ChatPanel(props) {
  const { draft, onDraft, thread, streaming, onSend, onStop } = props;
  return (
    <div className="panel-content is-flex" data-testid="lib-panel-chat">
      <div className="panel-title-row">
        <h2 className="panel-title">Ask your book</h2>
      </div>
      <div className="panel-form">
        <label className="field-label">Scope
          <select className="field-control" defaultValue="single" aria-label="Chat scope" data-testid="lib-chat-scope">
            <option value="all" disabled>All books — Coming soon</option>
            <option value="collection" disabled>Collection — Coming soon</option>
            <option value="single">Single book · The Art of Spending Money</option>
          </select>
        </label>
      </div>
      {thread.length === 0 ? (
        <div className="empty-panel">
          <div className="empty-panel-inner">
            <div className="empty-symbol" aria-hidden="true">AI</div>
            <h3 className="empty-title">Start with the book</h3>
            <p className="empty-copy">Ask a question and Reader3 answers from indexed passages.</p>
          </div>
        </div>
      ) : (
        <div className="thread" data-testid="lib-chat-thread">
          {thread.map((message, index) => <Message key={index} message={message} />)}
          {streaming && <TypingRow />}
        </div>
      )}
      <div className="composer-row">
        <textarea
          className="field-control composer"
          value={draft}
          placeholder="Ask about this book…  (Enter to send, Shift+Enter for a new line)"
          data-testid="lib-chat-input"
          onChange={(event) => onDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              onSend();
            }
          }}
        ></textarea>
        {streaming
          ? <button className="btn" type="button" data-testid="lib-chat-stop" onClick={onStop}>Stop</button>
          : <button className="btn btn-primary" type="button" data-testid="lib-chat-send" onClick={onSend}>Send</button>}
      </div>
    </div>
  );
}

function Message(props) {
  const { message } = props;
  return (
    <div className={"msg is-" + message.role} data-testid={LIB_CHAT_MSG_TESTID[message.role]}>
      <div className="msg-meta">{message.role === "user" ? "You" : "Assistant"} · {message.ts}</div>
      <div className="msg-body">{message.text}</div>
      {message.citations && (
        <div className="citations">
          {message.citations.map((citation) => (
            <button className="citation" type="button" key={citation.section} data-testid="lib-chat-citation" data-section={citation.section}>{citation.label}</button>
          ))}
        </div>
      )}
    </div>
  );
}

function TypingRow() {
  return (
    <div className="msg is-assistant" data-testid="lib-chat-msg-streaming">
      <div className="msg-meta">Assistant · generating</div>
      <div className="typing" aria-label="Generating"><i></i><i></i><i></i></div>
    </div>
  );
}

function SearchPanel(props) {
  const { query, onQuery, caseSensitive, onCase, mode, onMode, sort, onSort, expanded, onExpand } = props;
  const active = query.trim().length > 0;
  const total = D.libraryResults.reduce((sum, group) => sum + group.total, 0);

  return (
    <div className="panel-content" data-testid="lib-panel-search">
      {/* 2026-09-25 013 WI-13（原型先行）：DEG-S2 横幅住在搜索面板顶部（WI-3 验收 6），
          warn 调、可关闭；「重建索引」是单飞按钮（WI-3 验收 7）。 */}
      {props.staleCount > 0 && (
        <section className="degrade-banner is-warn" role="status" aria-live="polite" data-testid="lib-degrade-s2">
          <span className="degrade-icon" aria-hidden="true">⚠</span>
          <div className="degrade-body">
            <strong>索引已过期，结果可能不全</strong>
            <p>{props.staleCount} 本书的语义索引与当前模型不符，重建后恢复。</p>
          </div>
          <div className="degrade-actions">
            <button className="btn btn-sm" type="button" data-testid="lib-degrade-s2-reindex">重建索引</button>
          </div>
          <button className="btn btn-icon" type="button" aria-label="关闭" data-testid="lib-degrade-s2-dismiss">×</button>
        </section>
      )}
      <div className="panel-title-row">
        <h2 className="panel-title">Search library</h2>
        {active && <button className="text-button" type="button" data-testid="lib-search-clear" onClick={() => onQuery("")}>Clear</button>}
      </div>
      <div className="panel-form">
        <label className="field-label">Search all books
          <input className="field-control" value={query} placeholder="Try “money”" data-testid="lib-search-input" onChange={(event) => onQuery(event.target.value)} />
        </label>
        <div className="control-row">
          <label className="field-label" style={{flex: 1}}>Mode
            <select className="field-control" value={mode} data-testid="lib-search-mode" onChange={(event) => onMode(event.target.value)}>
              <option value="keyword">keyword</option>
              <option value="semantic">semantic</option>
              <option value="hybrid">hybrid</option>
            </select>
          </label>
          <label className="field-label" style={{flex: 1}}>Sort
            <select className="field-control" value={sort} data-testid="lib-search-sort" onChange={(event) => onSort(event.target.value)}>
              <option value="relevance">relevance</option>
              <option value="book_title">book title</option>
            </select>
          </label>
        </div>
        <label className="check-row">
          <input type="checkbox" checked={caseSensitive} data-testid="lib-search-case" onChange={(event) => onCase(event.target.checked)} />
          <span>Case sensitive</span>
        </label>
        {mode !== "keyword" && (
          <div className="inline-note is-warn" data-testid="lib-search-index-warning">
            Semantic and hybrid need a semantic index. 3 of 4 books are not indexed and will be skipped.
          </div>
        )}
      </div>

      {!active ? (
        <div className="empty-panel">
          <div className="empty-panel-inner">
            <div className="empty-symbol" aria-hidden="true">⌕</div>
            <h3 className="empty-title">Find a passage</h3>
            <p className="empty-copy">Keyword search works without an index. Index a book to unlock semantic and hybrid results.</p>
          </div>
        </div>
      ) : (
        <div data-testid="lib-search-results">
          <p className="result-summary">Found {total} results across {D.libraryResults.length} books</p>
          {D.libraryResults.map((group) => {
            const limit = expanded[group.book_id] ? 10 : 3;
            const shown = group.hits.slice(0, limit);
            return (
              <section className="result-group" key={group.book_id}>
                <h3 className="result-group-title">{group.book_title} <span>{group.total}</span></h3>
                {shown.map((hit, index) => (
                  <button className="search-result" type="button" key={index} data-testid="lib-search-hit">
                    <div className="result-section">Section {hit.section} · {hit.section_title} · {hit.score.toFixed(2)}</div>
                    <div className="result-copy" dangerouslySetInnerHTML={{__html: hit.snippet}}></div>
                  </button>
                ))}
                {group.hits.length > shown.length && (
                  <button className="text-button" type="button" data-testid="lib-search-show-more" data-book-id={group.book_id} onClick={() => onExpand(group.book_id)}>
                    Show more ({group.hits.length - shown.length})
                  </button>
                )}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

function InsightsPanel(props) {
  const { tab, onTab, collapsed, onCollapse } = props;
  if (collapsed) {
    return (
      <aside className="library-insights is-collapsed" aria-label="Library insights" data-testid="lib-insights-collapsed">
        <button className="btn btn-icon" type="button" aria-label="Expand insights panel" data-testid="lib-insights-expand" onClick={() => onCollapse(false)}>‹</button>
      </aside>
    );
  }
  return (
    <aside className="library-insights" aria-label="Library insights" data-testid="lib-insights">
      <div className="panel-tabs" role="tablist" aria-label="Insights views">
        {[["dashboard", "Overview"], ["chat", "Chat"], ["search", "Search"]].map((item) => (
          <button
            className={"panel-tab " + (tab === item[0] ? "is-active" : "")}
            type="button"
            role="tab"
            id={"tab-" + item[0]}
            aria-selected={tab === item[0]}
            aria-controls={"tabpanel-" + item[0]}
            key={item[0]}
            data-testid={LIB_PANEL_TAB_TESTID[item[0]]}
            onClick={() => onTab(item[0])}
          >{item[1]}</button>
        ))}
        <button className="collapse-button desktop-only" type="button" aria-label="Collapse insights panel" data-testid="lib-insights-collapse" onClick={() => onCollapse(true)}>›</button>
      </div>
      {/* 2026-09-25 013 WI-13（原型先行）：lib-right-panel 是右栏的内容区，移动端抽屉可达性断言的目标。 */}
      <div className="tabpanel" role="tabpanel" id={"tabpanel-" + tab} aria-labelledby={"tab-" + tab} data-testid="lib-right-panel">
        {props.children}
      </div>
    </aside>
  );
}

Object.assign(window, {
  useFocusTrap,
  LiveRegion,
  Brand,
  Toggle,
  ThemeToggle,
  Modal,
  ConfirmModal,
  TopBar,
  LibrarySidebar,
  BookCard,
  BookTable,
  StatusPill,
  DashboardPanel,
  ChatPanel,
  SearchPanel,
  InsightsPanel,
  Message,
  STATUS_META
});
