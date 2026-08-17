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

/* Screen-reader announcements (spec §3.1 "Live region"). */
function LiveRegion(props) {
  return <div className="sr-only" role="status" aria-live="polite" data-testid="live-region">{props.message}</div>;
}

/* ------------------------------------------------------------------ */
/* Primitives                                                           */
/* ------------------------------------------------------------------ */

function Brand() {
  return (
    <div className="brand" data-testid="brand">
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
  const next = { light: "dark", dark: "system", system: "light" };
  const glyph = { light: "☀", dark: "☾", system: "◐" };
  const title = { light: "Theme: light", dark: "Theme: dark", system: "Theme: follow system" };
  return (
    <button
      className="btn btn-icon"
      type="button"
      aria-label={title[theme] + " — click to change"}
      title={title[theme]}
      data-testid="theme-toggle"
      onClick={() => onTheme(next[theme])}
    >
      {glyph[theme]}
    </button>
  );
}

function Modal(props) {
  const { title, children, onClose, primaryLabel, onPrimary, tone, cancelLabel, size } = props;
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
        data-testid="modal"
      >
        <header className="modal-header">
          <h2 className="modal-title">{title}</h2>
          <button className="btn btn-icon" type="button" aria-label="Close dialog" style={{marginLeft: "auto"}} data-testid="modal-close" onClick={onClose}>×</button>
        </header>
        <div className="modal-body">{children}</div>
        {primaryLabel && (
          <footer className="modal-footer">
            <button className="btn" type="button" data-testid="modal-cancel" onClick={onClose}>{cancelLabel || "Cancel"}</button>
            <button className={"btn " + (tone === "danger" ? "btn-danger" : "btn-primary")} type="button" data-testid="modal-primary" onClick={onPrimary}>{primaryLabel}</button>
          </footer>
        )}
      </section>
    </div>
  );
}

/* Destructive actions must confirm (spec §4.3 Data, §4.1 item 7). */
function ConfirmModal(props) {
  const { title, body, confirmLabel, onCancel, onConfirm } = props;
  return (
    <Modal title={title} primaryLabel={confirmLabel} tone="danger" onClose={onCancel} onPrimary={onConfirm}>
      <p className="empty-copy" style={{fontSize: "13px"}} data-testid="confirm-body">{body}</p>
    </Modal>
  );
}

/* ------------------------------------------------------------------ */
/* Shell                                                                */
/* ------------------------------------------------------------------ */

function TopBar(props) {
  const { screen, onScreen, onAdd, onMobileMenu, onMobileInsights, theme, onTheme } = props;

  return (
    <header className="topbar" data-testid="topbar">
      {screen === "library" && (
        <button className="btn btn-icon mobile-only" type="button" aria-label="Open library navigation" data-testid="mobile-menu" onClick={onMobileMenu}>☰</button>
      )}
      <Brand />
      <nav className="topnav" aria-label="Primary navigation">
        <button className={"topnav-button " + (screen === "library" ? "is-active" : "")} type="button" data-testid="nav-library" onClick={() => onScreen("library")}>My Library</button>
        <button className={"topnav-button " + (screen === "settings" ? "is-active" : "")} type="button" data-testid="nav-settings" onClick={() => onScreen("settings")}>Settings</button>
      </nav>
      <div className="topbar-actions">
        <ThemeToggle theme={theme} onTheme={onTheme} />
        {screen === "library" && (
          <>
            <button className="btn btn-icon mobile-only tablet-visible" type="button" aria-label="Open insights panel" data-testid="mobile-insights" onClick={onMobileInsights}>◎</button>
            <button className="btn btn-primary" type="button" data-testid="add-books" onClick={onAdd}>Add books</button>
          </>
        )}
        {screen === "settings" && (
          <button className="btn" type="button" data-testid="back-to-library" onClick={() => onScreen("library")}>Back to Library</button>
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
      <button className={"sidebar-row " + (active ? "is-active" : "")} type="button" data-testid={"collection-" + collection.id} onClick={() => onScope(collection.id)}>
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
        data-testid={"collection-menu-" + collection.id}
        onClick={(event) => {
          event.stopPropagation();
          setMenu((current) => !current);
        }}
      >⋯</button>
      {menu && (
        <div className="row-menu" role="menu" data-testid="collection-menu">
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
    <aside className="library-sidebar" aria-label="Library navigation" data-testid="library-sidebar">
      <section className="sidebar-section">
        <p className="section-eyebrow">Types</p>
        <button className={"sidebar-row " + (scope === "all" ? "is-active" : "")} type="button" data-testid="scope-all" onClick={() => onScope("all")}>
          <span className="sidebar-icon" aria-hidden="true">A</span>
          <span className="row-label">All Books</span>
          <span className="count-badge">{counts.all}</span>
        </button>
        <button className={"sidebar-row " + (scope === "epub" ? "is-active" : "")} type="button" data-testid="scope-epub" onClick={() => onScope("epub")}>
          <span className="sidebar-icon" aria-hidden="true">E</span>
          <span className="row-label">EPUB</span>
          <span className="count-badge">{counts.epub}</span>
        </button>
        <button className="sidebar-row is-disabled" type="button" disabled title="PDF not supported yet" data-testid="scope-pdf">
          <span className="sidebar-icon" aria-hidden="true">P</span>
          <span className="row-label">PDF</span>
          <span className="count-badge">0</span>
        </button>
      </section>
      <section className="sidebar-section">
        <div className="sidebar-heading-row">
          <p className="section-eyebrow">Collections</p>
          <button className="mini-add" type="button" aria-label="Create collection" data-testid="create-collection" onClick={onCreateCollection}>+</button>
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

const STATUS_META = {
  not_indexed: { label: "Not indexed", tone: "warn" },
  indexing: { label: "Indexing…", tone: "busy" },
  indexed: { label: "Indexed", tone: "ok" },
  error: { label: "Index error", tone: "bad" }
};

function StatusPill(props) {
  const meta = STATUS_META[props.status] || STATUS_META.not_indexed;
  return (
    <span className={"status-pill is-" + meta.tone} data-testid={"status-" + props.status}>
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
      data-testid={"book-card-" + book.id}
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
      <table className="book-table" data-testid="book-table">
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
            <tr key={book.id} data-testid={"book-row-" + book.id}>
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
    <div className="panel-content" data-testid="panel-dashboard">
      <div className="panel-title-row">
        <h2 className="panel-title">Library overview</h2>
        <button className="text-button" type="button" data-testid="refresh-stats" onClick={props.onRefresh}>Refresh stats</button>
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
          <button className="btn btn-primary" type="button" data-testid="index-remaining">Index remaining</button>
          <button className="btn" type="button" data-testid="open-index-errors" onClick={props.onShowErrors}>View 1 error</button>
        </div>
      </div>
    </div>
  );
}

function ChatPanel(props) {
  const { draft, onDraft, thread, streaming, onSend, onStop } = props;
  return (
    <div className="panel-content is-flex" data-testid="panel-chat">
      <div className="panel-title-row">
        <h2 className="panel-title">Ask your book</h2>
      </div>
      <div className="panel-form">
        <label className="field-label">Scope
          <select className="field-control" defaultValue="single" aria-label="Chat scope" data-testid="chat-scope">
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
        <div className="thread" data-testid="chat-thread">
          {thread.map((message, index) => <Message key={index} message={message} />)}
          {streaming && <TypingRow />}
        </div>
      )}
      <div className="composer-row">
        <textarea
          className="field-control composer"
          value={draft}
          placeholder="Ask about this book…  (Enter to send, Shift+Enter for a new line)"
          data-testid="chat-input"
          onChange={(event) => onDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              onSend();
            }
          }}
        ></textarea>
        {streaming
          ? <button className="btn" type="button" data-testid="chat-stop" onClick={onStop}>Stop</button>
          : <button className="btn btn-primary" type="button" data-testid="chat-send" onClick={onSend}>Send</button>}
      </div>
    </div>
  );
}

function Message(props) {
  const { message } = props;
  return (
    <div className={"msg is-" + message.role} data-testid={"msg-" + message.role}>
      <div className="msg-meta">{message.role === "user" ? "You" : "Assistant"} · {message.ts}</div>
      <div className="msg-body">{message.text}</div>
      {message.citations && (
        <div className="citations">
          {message.citations.map((citation) => (
            <button className="citation" type="button" key={citation.section} data-testid={"citation-" + citation.section}>{citation.label}</button>
          ))}
        </div>
      )}
    </div>
  );
}

function TypingRow() {
  return (
    <div className="msg is-assistant" data-testid="msg-streaming">
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
    <div className="panel-content" data-testid="panel-search">
      <div className="panel-title-row">
        <h2 className="panel-title">Search library</h2>
        {active && <button className="text-button" type="button" data-testid="search-clear" onClick={() => onQuery("")}>Clear</button>}
      </div>
      <div className="panel-form">
        <label className="field-label">Search all books
          <input className="field-control" value={query} placeholder="Try “money”" data-testid="library-search-input" onChange={(event) => onQuery(event.target.value)} />
        </label>
        <div className="control-row">
          <label className="field-label" style={{flex: 1}}>Mode
            <select className="field-control" value={mode} data-testid="library-search-mode" onChange={(event) => onMode(event.target.value)}>
              <option value="keyword">keyword</option>
              <option value="semantic">semantic</option>
              <option value="hybrid">hybrid</option>
            </select>
          </label>
          <label className="field-label" style={{flex: 1}}>Sort
            <select className="field-control" value={sort} data-testid="library-search-sort" onChange={(event) => onSort(event.target.value)}>
              <option value="relevance">relevance</option>
              <option value="book_title">book title</option>
            </select>
          </label>
        </div>
        <label className="check-row">
          <input type="checkbox" checked={caseSensitive} data-testid="library-search-case" onChange={(event) => onCase(event.target.checked)} />
          <span>Case sensitive</span>
        </label>
        {mode !== "keyword" && (
          <div className="inline-note is-warn" data-testid="search-index-warning">
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
        <div data-testid="library-search-results">
          <p className="result-summary">Found {total} results across {D.libraryResults.length} books</p>
          {D.libraryResults.map((group) => {
            const limit = expanded[group.book_id] ? 10 : 3;
            const shown = group.hits.slice(0, limit);
            return (
              <section className="result-group" key={group.book_id}>
                <h3 className="result-group-title">{group.book_title} <span>{group.total}</span></h3>
                {shown.map((hit, index) => (
                  <button className="search-result" type="button" key={index} data-testid="search-hit">
                    <div className="result-section">Section {hit.section} · {hit.section_title} · {hit.score.toFixed(2)}</div>
                    <div className="result-copy" dangerouslySetInnerHTML={{__html: hit.snippet}}></div>
                  </button>
                ))}
                {group.hits.length > shown.length && (
                  <button className="text-button" type="button" data-testid={"show-more-" + group.book_id} onClick={() => onExpand(group.book_id)}>
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
      <aside className="library-insights is-collapsed" aria-label="Library insights" data-testid="insights-collapsed">
        <button className="btn btn-icon" type="button" aria-label="Expand insights panel" data-testid="expand-insights" onClick={() => onCollapse(false)}>‹</button>
      </aside>
    );
  }
  return (
    <aside className="library-insights" aria-label="Library insights" data-testid="insights">
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
            data-testid={"tab-" + item[0]}
            onClick={() => onTab(item[0])}
          >{item[1]}</button>
        ))}
        <button className="collapse-button desktop-only" type="button" aria-label="Collapse insights panel" data-testid="collapse-insights" onClick={() => onCollapse(true)}>›</button>
      </div>
      <div className="tabpanel" role="tabpanel" id={"tabpanel-" + tab} aria-labelledby={"tab-" + tab}>
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
