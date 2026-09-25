const { useEffect, useMemo, useState } = React;
const A = window.ReaderProData;
const {
  LiveRegion, Modal, ConfirmModal, TopBar, LibrarySidebar, BookCard, BookTable,
  DashboardPanel, ChatPanel, SearchPanel, InsightsPanel, ReaderScreen, SettingsScreen
} = window;

/* ================================================================== */
/* Library                                                             */
/* ================================================================== */

function LibraryScreen(props) {
  const { onOpenReader, mobileNav, mobileInsights, onCloseMobile } = props;

  const [scope, setScope] = useState("all");
  const [filter, setFilter] = useState("");
  const [view, setView] = useState("grid");
  const [sort, setSort] = useState("recent");
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState([]);
  const [tab, setTab] = useState("dashboard");
  const [collapsed, setCollapsed] = useState(false);
  const [collections, setCollections] = useState(A.collections);
  const [dialog, setDialog] = useState(null);
  const [announce, setAnnounce] = useState("");
  const [toast] = useState("");

  /* Search panel state */
  const [query, setQuery] = useState("");
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [mode, setMode] = useState("keyword");
  const [searchSort, setSearchSort] = useState("relevance");
  const [expanded, setExpanded] = useState({});

  /* Chat panel state */
  const [draft, setDraft] = useState("");
  const [thread, setThread] = useState([]);
  const [streaming, setStreaming] = useState(false);

  const books = useMemo(() => {
    const collection = collections.find((item) => item.id === scope);
    let rows = A.books;
    if (scope === "epub") rows = rows.filter((book) => book.format === "epub");
    else if (collection) rows = rows.filter((book) => collection.book_ids.includes(book.id));
    const needle = filter.trim().toLowerCase();
    if (needle) rows = rows.filter((book) => book.title.toLowerCase().includes(needle) || book.author.toLowerCase().includes(needle));
    const sorted = rows.slice();
    if (sort === "title") sorted.sort((a, b) => a.title.localeCompare(b.title));
    if (sort === "author") sorted.sort((a, b) => a.author.localeCompare(b.author));
    if (sort === "progress") sorted.sort((a, b) => b.progress - a.progress);
    return sorted;
  }, [collections, filter, scope, sort]);

  const toggleSelected = (id) => {
    setSelectedIds((current) => (current.includes(id) ? current.filter((item) => item !== id) : current.concat([id])));
  };

  const send = () => {
    const body = draft.trim();
    if (!body) return;
    setThread((current) => current.concat([{ role: "user", text: body, ts: "now" }]));
    setDraft("");
    setStreaming(true);
    window.setTimeout(() => {
      setThread((current) => current.concat([{
        role: "assistant",
        text: "Answering from the indexed passages of the selected book.",
        ts: "now",
        citations: [{ section: 8, label: "§8 May I Have Your Attention Please" }]
      }]));
      setStreaming(false);
    }, 1200);
  };

  const panelBody = tab === "dashboard"
    ? <DashboardPanel onRefresh={() => setAnnounce("Stats refreshed")} onShowErrors={() => setDialog({ kind: "errors" })} />
    : tab === "chat"
      ? <ChatPanel draft={draft} onDraft={setDraft} thread={thread} streaming={streaming} onSend={send} onStop={() => setStreaming(false)} />
      : <SearchPanel
          query={query} onQuery={setQuery}
          caseSensitive={caseSensitive} onCase={setCaseSensitive}
          mode={mode} onMode={setMode}
          sort={searchSort} onSort={setSearchSort}
          expanded={expanded} onExpand={(id) => setExpanded((current) => ({ ...current, [id]: true }))}
          staleCount={A.books.filter((b) => b.status === "stale").length}
        />;

  return (
    <div className={"library-shell " + (collapsed ? "is-collapsed" : "")} data-testid="lib-shell">
      <LiveRegion page="lib" message={announce} />
      {/* 2026-09-25 013 WI-13（原型先行，A11.4/A11.4a）：书库 toast 的落点，住在常驻 aria-live 区里。 */}
      <div className="toast-region" aria-live="polite">
        {toast && <div className="toast" role="status" data-testid="lib-toast">{toast}</div>}
      </div>

      <div className={"drawer-scrim " + (mobileNav || mobileInsights ? "is-open" : "")} onClick={onCloseMobile} aria-hidden="true"></div>

      <div className={"sidebar-slot " + (mobileNav ? "is-open" : "")}>
        <LibrarySidebar
          scope={scope}
          onScope={(next) => {
            setScope(next);
            onCloseMobile();
          }}
          collections={collections}
          counts={{ all: A.books.length, epub: A.books.filter((b) => b.format === "epub").length }}
          onCreateCollection={() => setDialog({ kind: "create" })}
          onRenameCollection={(collection) => setDialog({ kind: "rename", collection })}
          onDeleteCollection={(collection) => setDialog({ kind: "delete", collection })}
          onCleanCollection={(collection) => setDialog({ kind: "clean", collection })}
        />
      </div>

      <main className="library-main" data-testid="lib-main">
        <div className="library-toolbar">
          <input
            className="field-control filter-input"
            value={filter}
            placeholder="Filter by title or author…"
            aria-label="Filter books"
            data-testid="lib-toolbar-filter"
            onChange={(event) => setFilter(event.target.value)}
          />
          <label className="field-label inline">Sort
            <select className="field-control" value={sort} data-testid="lib-toolbar-sort" onChange={(event) => setSort(event.target.value)}>
              <option value="recent">Recently read</option>
              <option value="title">Title</option>
              <option value="author">Author</option>
              <option value="progress">Progress</option>
            </select>
          </label>
          <div className="view-switch" role="group" aria-label="View mode">
            <button className={"view-button " + (view === "grid" ? "is-active" : "")} type="button" aria-pressed={view === "grid"} data-testid="lib-toolbar-view-grid" onClick={() => setView("grid")}>Grid</button>
            <button className={"view-button " + (view === "list" ? "is-active" : "")} type="button" aria-pressed={view === "list"} data-testid="lib-toolbar-view-list" onClick={() => setView("list")}>List</button>
          </div>
          <button
            className={"btn " + (selectionMode ? "btn-primary" : "btn")}
            type="button"
            aria-pressed={selectionMode}
            data-testid="lib-toolbar-select-mode"
            onClick={() => {
              setSelectionMode((value) => !value);
              setSelectedIds([]);
            }}
          >{selectionMode ? "Done" : "Select"}</button>
        </div>

        {selectionMode && (
          <div className="bulk-bar" role="region" aria-label="Bulk actions" data-testid="lib-bulk-bar">
            <span>{selectedIds.length} selected</span>
            <button className="text-button" type="button" data-testid="lib-bulk-select-all" onClick={() => setSelectedIds(books.map((book) => book.id))}>Select all</button>
            <button className="text-button" type="button" data-testid="lib-bulk-select-none" onClick={() => setSelectedIds([])}>Clear</button>
            <div className="bulk-spacer"></div>
            <button className="btn btn-sm" type="button" disabled={!selectedIds.length} data-testid="lib-bulk-collection" onClick={() => setDialog({ kind: "addTo" })}>Add to collection</button>
            <button className="btn btn-primary btn-sm" type="button" disabled={!selectedIds.length} data-testid="lib-bulk-index" onClick={() => setAnnounce("Indexing " + selectedIds.length + " books")}>Index selected</button>
          </div>
        )}

        {/* 2026-09-25 013 WI-13（裁定 D12，原型先行）：加载失败态，与 lib-empty / lib-filter-empty 互斥。
            生产侧待客户端书目拉取存在后接入（归属 012/014），本 WI 不接进 library.html。 */}
        {A.loadFailed ? (
          <div className="empty-panel-inner" role="alert" data-testid="lib-load-failed">
            <h2 className="empty-title">书库加载失败</h2>
            <p className="empty-copy">网络或服务出错，书目没有取到。</p>
            <button className="btn" type="button" data-testid="lib-load-retry">重试</button>
          </div>
        ) : A.books.length === 0 ? (
          <div className="empty-panel-inner" data-testid="lib-empty">
            <div className="empty-symbol" aria-hidden="true">📚</div>
            <h2 className="empty-title">Your library is empty</h2>
            <p className="empty-copy">Add an EPUB to get started. Reader3 processes it locally — nothing leaves your machine.</p>
          </div>
        ) : books.length === 0 ? (
          <div className="empty-panel-inner" data-testid="lib-filter-empty">
            <div className="empty-symbol" aria-hidden="true">⌕</div>
            <h2 className="empty-title">No books match “{filter}”</h2>
            <p className="empty-copy">Try a different title or author, or clear the filter.</p>
            <button className="btn" type="button" style={{marginTop: "12px"}} onClick={() => setFilter("")}>Clear filter</button>
          </div>
        ) : view === "grid" ? (
          <div className="book-grid" data-testid="lib-book-grid">
            {books.map((book) => (
              <BookCard
                key={book.id}
                book={book}
                selectionMode={selectionMode}
                selected={selectedIds.includes(book.id)}
                onToggleSelected={toggleSelected}
                onOpenReader={onOpenReader}
              />
            ))}
          </div>
        ) : (
          <BookTable
            books={books}
            selectionMode={selectionMode}
            selectedIds={selectedIds}
            onToggleSelected={toggleSelected}
            onOpenReader={onOpenReader}
          />
        )}
      </main>

      <div className={"insights-slot " + (mobileInsights ? "is-open" : "")}>
        <InsightsPanel tab={tab} onTab={setTab} collapsed={collapsed} onCollapse={setCollapsed}>
          {panelBody}
        </InsightsPanel>
      </div>

      {dialog && dialog.kind === "create" && (
        <Modal modal="create-collection" title="New collection" primaryLabel="Create" onClose={() => setDialog(null)} onPrimary={() => {
          setCollections((current) => current.concat([{ id: "c" + (current.length + 1), name: "Untitled collection", book_ids: [], stale: 0 }]));
          setDialog(null);
          setAnnounce("Collection created");
        }}>
          <label className="field-label">Name
            <input className="field-control" defaultValue="Untitled collection" data-testid="lib-collection-name-input" />
          </label>
        </Modal>
      )}

      {dialog && dialog.kind === "rename" && (
        <Modal modal="rename-collection" title={"Rename “" + dialog.collection.name + "”"} primaryLabel="Save" onClose={() => setDialog(null)} onPrimary={() => {
          setDialog(null);
          setAnnounce("Collection renamed");
        }}>
          <label className="field-label">Name
            <input className="field-control" defaultValue={dialog.collection.name} data-testid="lib-collection-rename-input" />
          </label>
        </Modal>
      )}

      {dialog && dialog.kind === "delete" && (
        <ConfirmModal modal="delete-collection"
          title={"Delete “" + dialog.collection.name + "”?"}
          body="The collection is removed. The books inside it stay in your library."
          confirmLabel="Delete collection"
          onCancel={() => setDialog(null)}
          onConfirm={() => {
            setCollections((current) => current.filter((item) => item.id !== dialog.collection.id));
            if (scope === dialog.collection.id) setScope("all");
            setDialog(null);
            setAnnounce("Collection deleted");
          }}
        />
      )}

      {dialog && dialog.kind === "clean" && (
        <ConfirmModal modal="clean-collection"
          title="Remove missing books?"
          body={dialog.collection.stale + " book(s) in this collection no longer exist on disk. Removing them only updates the collection."}
          confirmLabel="Remove missing"
          onCancel={() => setDialog(null)}
          onConfirm={() => {
            setCollections((current) => current.map((item) => (item.id === dialog.collection.id
              ? { ...item, stale: 0, book_ids: item.book_ids.filter((id) => A.books.some((book) => book.id === id)) }
              : item)));
            setDialog(null);
            setAnnounce("Missing books removed");
          }}
        />
      )}

      {dialog && dialog.kind === "addTo" && (
        <Modal modal="add-to-collection" title={"Add " + selectedIds.length + " books to collection"} primaryLabel="Add" onClose={() => setDialog(null)} onPrimary={() => {
          setDialog(null);
          setAnnounce("Books added to collection");
        }}>
          <label className="field-label">Collection
            <select className="field-control" data-testid="lib-add-to-collection-select">
              {collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}
            </select>
          </label>
        </Modal>
      )}

      {dialog && dialog.kind === "errors" && (
        <Modal modal="index-errors" title="Index errors" onClose={() => setDialog(null)}>
          <div data-testid="lib-index-errors">
            {A.indexErrors.map((error) => (
              <article className="error-row" key={error.book_id}>
                <h3 className="note-group-title">{error.book_title}</h3>
                <p className="empty-copy">{error.message}</p>
                <p className="result-section">{error.at}</p>
                <button className="btn btn-sm" type="button" data-testid="lib-index-retry">Retry indexing</button>
              </article>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}

/* ================================================================== */
/* App shell                                                           */
/* ================================================================== */

function App() {
  const params = new URLSearchParams(window.location.search);
  const [screen, setScreen] = useState(params.get("screen") || "library");
  const [book, setBook] = useState(A.books[0]);
  const [theme, setTheme] = useState(localStorage.getItem("reader3.ui.colorScheme") || "system");
  const [mobileNav, setMobileNav] = useState(false);
  const [mobileInsights, setMobileInsights] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const errorState = params.get("state");

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    localStorage.setItem("reader3.ui.colorScheme", theme);
  }, [theme]);

  const closeMobile = () => {
    setMobileNav(false);
    setMobileInsights(false);
  };

  if (screen === "reader") {
    return <ReaderScreen book={book} errorState={errorState} onBack={() => setScreen("library")} />;
  }

  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <TopBar
        screen={screen}
        onScreen={setScreen}
        theme={theme}
        onTheme={setTheme}
        onAdd={() => setAddOpen(true)}
        onMobileMenu={() => {
          setMobileInsights(false);
          setMobileNav((value) => !value);
        }}
        onMobileInsights={() => {
          setMobileNav(false);
          setMobileInsights((value) => !value);
        }}
      />
      <div id="main">
        {screen === "library" ? (
          <LibraryScreen
            mobileNav={mobileNav}
            mobileInsights={mobileInsights}
            onCloseMobile={closeMobile}
            onOpenReader={(next) => {
              setBook(next);
              setScreen("reader");
            }}
          />
        ) : (
          <SettingsScreen theme={theme} onTheme={setTheme} />
        )}
      </div>

      {addOpen && (
        <Modal modal="add-books" title="Add books" primaryLabel="Process 0 files" onClose={() => setAddOpen(false)} onPrimary={() => setAddOpen(false)}>
          <div className="dropzone" data-testid="lib-add-dropzone">
            <p className="empty-title" style={{fontSize: "15px"}}>Drop EPUB files here</p>
            <p className="empty-copy">or</p>
            <button className="btn" type="button" data-testid="lib-add-choose-files">Choose files</button>
          </div>
          <p className="empty-copy" style={{marginTop: "12px"}}>
            Files are processed locally into <code>books/&#123;name&#125;_data/</code>. PDF support is not available yet.
          </p>
        </Modal>
      )}
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
