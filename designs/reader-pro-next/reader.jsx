const { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } = React;
const RD = window.ReaderProData;
const { useFocusTrap, Modal, ConfirmModal, LiveRegion } = window;

/* ================================================================== */
/* Annotation geometry                                                 */
/* ================================================================== */

/* Character offset of (node, offset) within `root`, counting only text.
   Annotations are stored as {paragraph, start, end} character ranges rather
   than DOM ranges so they survive re-render, theme changes and repagination —
   Range.surroundContents() cannot span element boundaries and breaks as soon
   as one highlight overlaps another. */
function textOffset(root, node, offset) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
  let total = 0;
  let current = walker.nextNode();
  while (current) {
    if (current === node) return total + offset;
    total += current.nodeValue.length;
    current = walker.nextNode();
  }
  return total;
}

/* Split paragraph text at every annotation boundary so overlapping ranges each
   get their own segment. Returns [{text, marks}] in document order. */
function segmentParagraph(text, marks) {
  const points = new Set([0, text.length]);
  marks.forEach((mark) => {
    if (mark.start > 0 && mark.start < text.length) points.add(mark.start);
    if (mark.end > 0 && mark.end < text.length) points.add(mark.end);
  });
  const sorted = Array.from(points).sort((a, b) => a - b);
  const out = [];
  for (let i = 0; i < sorted.length - 1; i += 1) {
    const start = sorted[i];
    const end = sorted[i + 1];
    if (end <= start) continue;
    out.push({
      text: text.slice(start, end),
      marks: marks.filter((mark) => mark.start <= start && mark.end >= end)
    });
  }
  return out;
}

const TYPE_LABEL = { marker: "Marker", wavy: "Wavy", underline: "Underline", note: "Note" };
const COLORS = ["yellow", "green", "pink", "blue"];

/* 0.5：testid 值必须是字面量。取值集合写死的走静态映射表；取值来自用户数据的
   （笔记、会话、章节、标注 span）走「字面量 testid + 另一个 data-* 携带 id」。 */
const RD_ANNO_TYPE_TESTID = {
  marker: "rd-anno-type-marker",
  wavy: "rd-anno-type-wavy",
  underline: "rd-anno-type-underline",
};

const RD_ANNO_COLOR_TESTID = {
  yellow: "rd-anno-color-yellow",
  green: "rd-anno-color-green",
  pink: "rd-anno-color-pink",
  blue: "rd-anno-color-blue",
};

const RD_RAIL_TESTID = {
  toc: "rd-rail-toc",
  search: "rd-rail-search",
  notes: "rd-rail-notes",
  ai: "rd-rail-ai",
};

const RD_AI_QUICK_TESTID = {
  summary: "rd-ai-quick-summary",
  highlights: "rd-ai-quick-highlights",
  background: "rd-ai-quick-background",
};

const RD_PREF_FONT_TESTID = {
  system: "rd-pref-font-system",
  kai: "rd-pref-font-kai",
  hei: "rd-pref-font-hei",
  song: "rd-pref-font-song",
};

const RD_PREF_THEME_TESTID = {
  auto: "rd-pref-theme-auto",
  paper: "rd-pref-theme-paper",
  sepia: "rd-pref-theme-sepia",
  green: "rd-pref-theme-green",
  night: "rd-pref-theme-night",
};

/* ================================================================== */
/* Horizontal pagination                                               */
/* ================================================================== */

/* Multi-column pagination, the same technique epub.js uses for
   `flow: "paginated"`: lay the chapter out in columns exactly one viewport
   wide inside an overflow:hidden parent, then translate by whole pages. */
function usePagination(viewportRef, flowRef, resetKey, deps) {
  const [state, setState] = useState({ page: 0, pages: 1, width: 0, gap: 64 });
  /* Mirrors of page/pages kept in sync synchronously. Handlers that fire
     several times in one tick (held arrow key, fast clicks) would otherwise
     all read the same stale render value and advance a single page. */
  const pageRef = useRef(0);
  const pagesRef = useRef(1);
  /* Raised when the content is about to change (chapter turn) and lowered by
     the next measure. Until then the page count belongs to the old chapter,
     so acting on it would skip pages — or whole chapters. */
  const staleRef = useRef(false);
  /* Set when we enter a chapter by paging backwards: the reader should land on
     its last page, otherwise backward paging skips the chapter it just opened. */
  const landAtEndRef = useRef(false);

  const measure = useCallback(() => {
    const viewport = viewportRef.current;
    const flow = flowRef.current;
    if (!viewport || !flow) return;
    const gap = 64;
    const width = viewport.clientWidth;
    if (width <= 0) return;
    flow.style.columnWidth = width + "px";
    flow.style.columnGap = gap + "px";
    flow.style.height = viewport.clientHeight + "px";
    flow.style.width = width + "px";
    const pages = Math.max(1, Math.round((flow.scrollWidth + gap) / (width + gap)));
    pagesRef.current = pages;
    pageRef.current = landAtEndRef.current ? pages - 1 : Math.min(pageRef.current, pages - 1);
    landAtEndRef.current = false;
    staleRef.current = false;
    setState({ page: pageRef.current, pages, width, gap });
  }, [flowRef, viewportRef]);

  useLayoutEffect(() => {
    pageRef.current = 0;
    setState((current) => ({ ...current, page: 0 }));
  }, [resetKey]);

  useLayoutEffect(() => {
    measure();
    const observer = new ResizeObserver(measure);
    if (viewportRef.current) observer.observe(viewportRef.current);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const goTo = useCallback((next) => {
    const clamped = Math.max(0, Math.min(next, pagesRef.current - 1));
    pageRef.current = clamped;
    setState((current) => ({ ...current, page: clamped }));
  }, []);

  return { ...state, goTo, pageRef, pagesRef, staleRef, landAtEndRef, remeasure: measure };
}

/* ================================================================== */
/* Overlays                                                            */
/* ================================================================== */

function Sheet(props) {
  const { title, side, width, onClose, children, testId, onResize } = props;
  const ref = useRef(null);
  useFocusTrap(ref, true, onClose);

  const startResize = (event) => {
    if (!onResize) return;
    event.preventDefault();
    const move = (moveEvent) => {
      const next = side === "right" ? window.innerWidth - moveEvent.clientX : moveEvent.clientX;
      onResize(Math.max(320, Math.min(800, next)));
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  return (
    <aside
      className={"reader-sheet is-" + side}
      role="dialog"
      aria-modal="false"
      aria-label={title}
      tabIndex="-1"
      ref={ref}
      style={width ? { width: width + "px" } : undefined}
      data-testid={testId}
    >
      {onResize && (
        <div
          className="sheet-resizer"
          role="separator"
          aria-orientation="vertical"
          aria-label={"Resize " + title + " panel"}
          tabIndex="0"
          data-testid="rd-sheet-resizer"
          data-sheet={testId}
          onMouseDown={startResize}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft") onResize(Math.max(320, (width || 546) + (side === "right" ? 24 : -24)));
            if (event.key === "ArrowRight") onResize(Math.min(800, (width || 546) + (side === "right" ? -24 : 24)));
          }}
        ></div>
      )}
      <header className="sheet-header">
        <h2 className="sheet-title">{title}</h2>
        <div className="sheet-header-actions">{props.actions}</div>
        <button className="btn btn-icon" type="button" aria-label={"Close " + title} data-testid="rd-sheet-close" data-sheet={testId} onClick={onClose}>×</button>
      </header>
      <div className="sheet-body">{children}</div>
    </aside>
  );
}

/* ------------------------------ TOC ------------------------------- */

function TocPanel(props) {
  const { current, onJump, onClose } = props;
  const [filter, setFilter] = useState("");
  const rows = RD.toc.filter((entry) => entry.title.toLowerCase().includes(filter.trim().toLowerCase()));

  return (
    <Sheet title="Contents" side="left" onClose={onClose} testId="rd-toc-panel">
      <input
        className="field-control"
        value={filter}
        placeholder="Filter sections…"
        aria-label="Filter sections"
        data-testid="rd-toc-filter"
        onChange={(event) => setFilter(event.target.value)}
      />
      {rows.length === 0 && <p className="empty-copy" style={{marginTop: "16px"}}>No section matches “{filter}”.</p>}
      <ol className="toc-list">
        {rows.map((entry) => (
          <li key={entry.section + "-" + entry.title}>
            <button
              className={"toc-row is-depth-" + entry.depth + " " + (entry.section === current ? "is-current" : "")}
              type="button"
              aria-current={entry.section === current ? "true" : undefined}
              data-testid="rd-toc-row" data-section={entry.section}
              onClick={() => onJump(entry.section)}
            >
              <span className="toc-label">{entry.title}</span>
              <span className="toc-num">{entry.section}</span>
            </button>
          </li>
        ))}
      </ol>
    </Sheet>
  );
}

/* --------------------------- Notes panel --------------------------- */

function NotesPanel(props) {
  const { annotations, onClose, onJump, onDelete, onReview, onExport } = props;

  const groups = useMemo(() => {
    const map = new Map();
    annotations.forEach((note) => {
      if (!map.has(note.chapter_index)) map.set(note.chapter_index, { title: note.chapter_title, index: note.chapter_index, items: [] });
      map.get(note.chapter_index).items.push(note);
    });
    return Array.from(map.values()).sort((a, b) => a.index - b.index);
  }, [annotations]);

  const copyAll = () => {
    const text = groups
      .map((group) => group.title + "\n" + group.items.map((n) => "  “" + n.quote + "”" + (n.note_text ? "\n    — " + n.note_text : "")).join("\n"))
      .join("\n\n");
    navigator.clipboard && navigator.clipboard.writeText(text);
  };

  return (
    <Sheet
      title="Notes"
      side="right"
      onClose={onClose}
      testId="rd-notes-panel"
      actions={
        <>
          <button className="text-button" type="button" data-testid="rd-notes-review" onClick={onReview}>Review book</button>
          <button className="text-button" type="button" data-testid="rd-notes-export" onClick={onExport}>Export</button>
        </>
      }
    >
      {annotations.length === 0 ? (
        <div className="empty-panel-inner" data-testid="rd-notes-empty">
          <div className="empty-symbol" aria-hidden="true">✎</div>
          <h3 className="empty-title">No notes yet</h3>
          <p className="empty-copy">Select any passage to highlight it or attach a note.</p>
        </div>
      ) : (
        <>
          <div className="notes-toolbar">
            <span className="result-summary" style={{margin: 0}}>{annotations.length} notes · {groups.length} sections</span>
            <button className="text-button" type="button" data-testid="rd-notes-copy-all" onClick={copyAll}>Copy all · {annotations.length}</button>
          </div>
          {groups.map((group) => (
            <section className="note-group" key={group.index}>
              <h3 className="note-group-title">{group.title} <span>{group.items.length}</span></h3>
              {group.items.map((note) => (
                <article className="note-item" key={note.id} data-testid="rd-notes-item" data-note-id={note.id}>
                  <div className="note-item-head">
                    <span className={"note-chip is-" + (note.color || "plain")}>{TYPE_LABEL[note.type]}</span>
                    <button className="text-button" type="button" data-testid="rd-notes-jump" data-note-id={note.id} onClick={() => onJump(note)}>Go to</button>
                    <button className="text-button is-danger" type="button" data-testid="rd-notes-delete" data-note-id={note.id} onClick={() => onDelete(note)}>Delete</button>
                  </div>
                  <blockquote className="note-quote">{note.quote}</blockquote>
                  {note.note_text && <p className="note-text">{note.note_text}</p>}
                </article>
              ))}
            </section>
          ))}
        </>
      )}
    </Sheet>
  );
}

/* -------------------------- Search panel --------------------------- */

function ReaderSearchPanel(props) {
  const { onClose, onJump, indexStatus, onIndex } = props;
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("keyword");
  const [phase, setPhase] = useState("idle");
  const timer = useRef(null);

  const run = (value, nextMode) => {
    window.clearTimeout(timer.current);
    if (!value.trim()) {
      setPhase("idle");
      return;
    }
    setPhase("loading");
    timer.current = window.setTimeout(() => {
      if (nextMode !== "keyword" && indexStatus !== "indexed") setPhase("error");
      else if (value.trim().toLowerCase() === "zzz") setPhase("empty");
      else setPhase("done");
    }, 420);
  };

  useEffect(() => () => window.clearTimeout(timer.current), []);

  return (
    <Sheet title="Search in book" side="right" onClose={onClose} testId="rd-search-panel">
      <div className="index-banner" data-testid="rd-search-index-status">
        <span>Semantic index: <strong>{window.STATUS_META[indexStatus].label}</strong></span>
        {indexStatus !== "indexed" && (
          <button className="btn btn-sm" type="button" data-testid="rd-search-index-book" onClick={onIndex}>Index book</button>
        )}
      </div>
      <input
        className="field-control"
        value={query}
        placeholder="Search this book…"
        aria-label="Search in book"
        data-testid="rd-search-input"
        onChange={(event) => {
          setQuery(event.target.value);
          run(event.target.value, mode);
        }}
      />
      <div className="control-row" style={{marginTop: "10px"}}>
        <label className="field-label" style={{flex: 1}}>Mode
          <select className="field-control" value={mode} data-testid="rd-search-mode" onChange={(event) => {
            setMode(event.target.value);
            run(query, event.target.value);
          }}>
            <option value="keyword">keyword</option>
            <option value="semantic">semantic</option>
            <option value="hybrid">hybrid</option>
          </select>
        </label>
      </div>

      {phase === "idle" && <p className="empty-copy" style={{marginTop: "18px"}}>Keyword search works on any book. Semantic and hybrid need an index.</p>}
      {phase === "loading" && <p className="state-line" data-testid="rd-search-loading">Searching…</p>}
      {phase === "error" && <p className="state-line is-error" data-testid="rd-search-failed">Search failed — this book has no semantic index yet.</p>}
      {phase === "empty" && <p className="state-line" data-testid="rd-search-empty">No results found for “{query}”</p>}
      {phase === "done" && (
        <div data-testid="rd-search-results">
          <p className="result-summary">{RD.readerResults.length} results in this book</p>
          {RD.readerResults.map((hit, index) => (
            <button className="search-result" type="button" key={index} data-testid="rd-search-hit" onClick={() => onJump(hit)}>
              <div className="result-section">Section {hit.section} · {hit.section_title} · match {hit.occurrence}</div>
              <div className="result-copy" dangerouslySetInnerHTML={{__html: hit.snippet}}></div>
            </button>
          ))}
        </div>
      )}
    </Sheet>
  );
}

/* ----------------------------- AI panel ---------------------------- */

function AiPanel(props) {
  const { onClose, width, onResize, onJump } = props;
  const [thread, setThread] = useState(RD.aiThread);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [history, setHistory] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const timer = useRef(null);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const send = (text) => {
    const body = (text || draft).trim();
    if (!body) return;
    setThread((current) => current.concat([{ role: "user", text: body, ts: "now" }]));
    setDraft("");
    setStreaming(true);
    timer.current = window.setTimeout(() => {
      setThread((current) => current.concat([{
        role: "assistant",
        text: "Here is a grounded answer drawn from the indexed passages of this book.",
        ts: "now",
        citations: [{ section: 8, label: "§8 May I Have Your Attention Please" }]
      }]));
      setStreaming(false);
    }, 1400);
  };

  const stop = () => {
    window.clearTimeout(timer.current);
    setStreaming(false);
  };

  const exportAs = (format) => {
    const payload = format === "json"
      ? JSON.stringify(thread, null, 2)
      : thread.map((m) => (format === "md" ? "**" + m.role + "**: " + m.text : m.role + ": " + m.text)).join("\n\n");
    const blob = new Blob([payload], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "conversation." + format;
    link.click();
    URL.revokeObjectURL(url);
    setExporting(false);
  };

  return (
    <Sheet
      title="AI assistant"
      side="right"
      width={width}
      onResize={onResize}
      onClose={onClose}
      testId="rd-ai-panel"
      actions={
        <>
          <button className="text-button" type="button" aria-expanded={history} data-testid="rd-ai-history" onClick={() => setHistory((v) => !v)}>History</button>
          <button className="text-button" type="button" data-testid="rd-ai-new" onClick={() => setThread([])}>New chat</button>
          <button className="text-button is-danger" type="button" data-testid="rd-ai-clear" onClick={() => setConfirmClear(true)}>Clear</button>
          <button className="text-button" type="button" aria-expanded={exporting} data-testid="rd-ai-export" onClick={() => setExporting((v) => !v)}>Export</button>
        </>
      }
    >
      {exporting && (
        <div className="export-row" role="group" aria-label="Export conversation" data-testid="rd-ai-export-menu">
          <button className="btn btn-sm" type="button" onClick={() => exportAs("md")}>Markdown</button>
          <button className="btn btn-sm" type="button" onClick={() => exportAs("txt")}>Plain text</button>
          <button className="btn btn-sm" type="button" onClick={() => exportAs("json")}>JSON</button>
        </div>
      )}
      {history && (
        <div className="history-list" data-testid="rd-ai-history-list">
          <p className="section-eyebrow">Recent conversations</p>
          {RD.conversations.map((conversation) => (
            <button className="history-row" type="button" key={conversation.id} data-testid="rd-ai-conversation" data-conversation-id={conversation.id}>
              <span>{conversation.title}</span>
              <small>{conversation.updated}</small>
            </button>
          ))}
        </div>
      )}

      <div className="quick-actions" role="group" aria-label="Quick prompts">
        {["Summary", "Highlights", "Background"].map((label) => (
          <button className="chip-button" type="button" key={label} data-testid={RD_AI_QUICK_TESTID[label.toLowerCase()]} onClick={() => send(label + " of this section")}>{label}</button>
        ))}
      </div>

      {thread.length === 0 ? (
        <div className="empty-panel-inner" data-testid="rd-ai-empty">
          <div className="empty-symbol" aria-hidden="true">AI</div>
          <h3 className="empty-title">Ask about this section</h3>
          <p className="empty-copy">Answers cite the passages they came from.</p>
        </div>
      ) : (
        <div className="thread" data-testid="rd-ai-thread">
          {thread.map((message, index) => (
            <div className={"msg is-" + message.role} key={index}>
              <div className="msg-meta">{message.role === "user" ? "You" : "Assistant"} · {message.ts}</div>
              <div className="msg-body">{message.text}</div>
              {message.citations && (
                <div className="citations">
                  {message.citations.map((citation) => (
                    <button className="citation" type="button" key={citation.section} data-testid="rd-ai-citation" data-section={citation.section} onClick={() => onJump(citation.section)}>{citation.label}</button>
                  ))}
                </div>
              )}
            </div>
          ))}
          {streaming && (
            <div className="msg is-assistant" data-testid="rd-ai-streaming">
              <div className="msg-meta">Assistant · generating</div>
              <div className="typing" aria-label="Generating"><i></i><i></i><i></i></div>
            </div>
          )}
        </div>
      )}

      <div className="composer-row">
        <textarea
          className="field-control composer"
          value={draft}
          placeholder="Ask about this book…"
          data-testid="rd-ai-input"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              send();
            }
          }}
        ></textarea>
        {streaming
          ? <button className="btn" type="button" data-testid="rd-ai-stop" onClick={stop}>Stop</button>
          : <button className="btn btn-primary" type="button" data-testid="rd-ai-send" onClick={() => send()}>Send</button>}
      </div>

      {confirmClear && (
        <ConfirmModal page="rd" name="clear-conversation"
          title="Clear this conversation?"
          body="All messages in the current conversation will be removed. This cannot be undone."
          confirmLabel="Clear conversation"
          onCancel={() => setConfirmClear(false)}
          onConfirm={() => {
            setThread([]);
            setConfirmClear(false);
          }}
        />
      )}
    </Sheet>
  );
}

/* -------------------------- Font popover --------------------------- */

/* Five, not four. `auto` is the default and means "follow the interface theme"
   (ruling R7). It is not a colour of its own — it is the absence of an
   override, so it has no CSS rule in index.html. */
const READING_THEMES = [
  { id: "auto", label: "Auto" },
  { id: "paper", label: "Paper" },
  { id: "sepia", label: "Sepia" },
  { id: "green", label: "Green" },
  { id: "night", label: "Night" }
];

const READING_FONTS = [
  { id: "system", label: "System default" },
  { id: "kai", label: "Kai — brush serif" },
  { id: "hei", label: "Hei — modern sans" },
  { id: "song", label: "Song — book serif" }
];

function FontPopover(props) {
  const { prefs, onPrefs, onClose } = props;
  const ref = useRef(null);
  useFocusTrap(ref, true, onClose);

  return (
    <div className="popover" role="dialog" aria-modal="false" aria-label="Reading appearance" tabIndex="-1" ref={ref} data-testid="rd-font-popover">
      <label className="field-label">Text size · {prefs.size}px
        <input
          className="range"
          type="range"
          min="14"
          max="24"
          step="1"
          value={prefs.size}
          data-testid="rd-pref-size"
          onChange={(event) => onPrefs({ ...prefs, size: Number(event.target.value) })}
        />
      </label>
      <label className="field-label">Line height · {prefs.leading.toFixed(2)}
        <input
          className="range"
          type="range"
          min="1.5"
          max="2.5"
          step="0.05"
          value={prefs.leading}
          data-testid="rd-pref-leading"
          onChange={(event) => onPrefs({ ...prefs, leading: Number(event.target.value) })}
        />
      </label>
      <fieldset className="pref-group">
        <legend className="section-eyebrow">Typeface</legend>
        <div className="pref-grid">
          {READING_FONTS.map((font) => (
            <button
              className={"pref-option " + (prefs.font === font.id ? "is-active" : "")}
              type="button"
              key={font.id}
              aria-pressed={prefs.font === font.id}
              data-testid={RD_PREF_FONT_TESTID[font.id]}
              onClick={() => onPrefs({ ...prefs, font: font.id })}
            >{font.label}</button>
          ))}
        </div>
      </fieldset>
      <fieldset className="pref-group">
        <legend className="section-eyebrow">Reading theme</legend>
        <div className="pref-grid">
          {READING_THEMES.map((theme) => (
            <button
              className={"pref-option swatch-" + theme.id + " " + (prefs.readingTheme === theme.id ? "is-active" : "")}
              type="button"
              key={theme.id}
              aria-pressed={prefs.readingTheme === theme.id}
              data-testid={RD_PREF_THEME_TESTID[theme.id]}
              onClick={() => onPrefs({ ...prefs, readingTheme: theme.id })}
            >{theme.label}</button>
          ))}
        </div>
      </fieldset>
    </div>
  );
}

/* ----------------------- Annotation toolbar ------------------------ */

function AnnotationToolbar(props) {
  const { rect, existing, onApply, onDelete, onNote, onAsk, onCopy, onClose } = props;
  const ref = useRef(null);
  useFocusTrap(ref, true, onClose);

  const [type, setType] = useState(existing ? existing.type : "marker");
  const style = {
    top: Math.max(64, rect.top - 12) + "px",
    left: Math.min(Math.max(150, rect.left + rect.width / 2), window.innerWidth - 160) + "px"
  };

  return (
    <div className="annotation-toolbar" role="dialog" aria-modal="false" aria-label="Annotate selection" tabIndex="-1" ref={ref} style={style} data-testid="rd-anno-toolbar">
      <div className="tool-row">
        <button className="tool-button" type="button" data-testid="rd-anno-copy" onClick={onCopy}>Copy</button>
        {["marker", "wavy", "underline"].map((kind) => (
          <button
            className={"tool-button " + (type === kind ? "is-active" : "")}
            type="button"
            key={kind}
            aria-pressed={type === kind}
            data-testid={RD_ANNO_TYPE_TESTID[kind]}
            onClick={() => {
              setType(kind);
              onApply(kind, null);
            }}
          >{TYPE_LABEL[kind]}</button>
        ))}
        <button className="tool-button" type="button" data-testid="rd-anno-note" onClick={onNote}>Add Note</button>
        <button className="tool-button" type="button" data-testid="rd-anno-ask" onClick={onAsk}>Ask AI</button>
        {existing && <button className="tool-button is-danger" type="button" data-testid="rd-anno-delete" onClick={onDelete}>Delete</button>}
      </div>
      <div className="tool-row is-colors" role="group" aria-label="Highlight color">
        {COLORS.map((color) => (
          <button
            className={"color-dot is-" + color}
            type="button"
            key={color}
            aria-label={color + " highlight"}
            data-testid={RD_ANNO_COLOR_TESTID[color]}
            onClick={() => onApply(type, color)}
          ></button>
        ))}
      </div>
    </div>
  );
}

function NoteEditor(props) {
  const { quote, initial, onSave, onClose } = props;
  const [text, setText] = useState(initial || "");
  return (
    <Modal page="rd" name="note-editor" title="Add note" primaryLabel="Save note" onClose={onClose} onPrimary={() => onSave(text)}>
      <blockquote className="note-quote" data-testid="rd-note-editor-quote">{quote}</blockquote>
      <label className="field-label">Your note
        <textarea
          className="field-control composer"
          value={text}
          rows="5"
          placeholder="What does this passage mean to you?"
          data-testid="rd-note-editor-input"
          onChange={(event) => setText(event.target.value)}
        ></textarea>
      </label>
    </Modal>
  );
}

/* ================================================================== */
/* Reader screen                                                       */
/* ================================================================== */

function ReaderScreen(props) {
  const { book, onBack, errorState } = props;
  const [panel, setPanel] = useState(null);
  const [fontOpen, setFontOpen] = useState(false);
  /* size/leading here are prototype values; production ships 17 / 1.9 (R7 tail). */
  const [prefs, setPrefs] = useState({ size: 18, leading: 1.85, font: "system", readingTheme: "auto" });
  const [chapterIndex, setChapterIndex] = useState(RD.chapter.index);
  const [annotations, setAnnotations] = useState(RD.annotations);
  const [selection, setSelection] = useState(null);
  const [editing, setEditing] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [review, setReview] = useState(false);
  const [aiWidth, setAiWidth] = useState(546);
  const [announce, setAnnounce] = useState("");

  const viewportRef = useRef(null);
  const flowRef = useRef(null);
  const chapterRef = useRef(RD.chapter.index);
  const paging = usePagination(viewportRef, flowRef, chapterIndex, [chapterIndex, prefs.size, prefs.leading, prefs.font, panel, aiWidth]);

  /* The paper axis is stamped on <html>, not on .reader-shell (ruling R7):
     in production a synchronous <head> script sets it before <body> exists,
     so .reader-shell is not available as a mount point. Scoping is done by
     the selector `html[data-reading-theme=x] .reader-shell` instead. `auto`
     is stamped like any other value — only the chrome axis removes its
     attribute (for "system"). */
  useEffect(() => {
    document.documentElement.setAttribute("data-reading-theme", prefs.readingTheme);
  }, [prefs.readingTheme]);

  const chapterNotes = annotations.filter((note) => note.chapter_index === chapterIndex);

  /* Single-panel exclusivity: opening one side panel closes the others. */
  const togglePanel = (next) => {
    setFontOpen(false);
    setPanel((current) => (current === next ? null : next));
  };

  /* Spec §5.3 layered Escape: note editor → annotation toolbar → TOC → Notes → Search/AI. */
  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        if (editing) return;              // NoteEditor's own trap handles it
        if (selection) { setSelection(null); return; }
        if (fontOpen) { setFontOpen(false); return; }
        if (panel) { setPanel(null); return; }
        return;
      }
      if (event.target.closest && event.target.closest("input, textarea, select")) return;
      if (event.key === "ArrowRight" || event.key === "PageDown" || event.key === " ") {
        event.preventDefault();
        turn(1);
      }
      if (event.key === "ArrowLeft" || event.key === "PageUp") {
        event.preventDefault();
        turn(-1);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  /* Read through the refs, not the rendered values: a held arrow key or a
     burst of clicks fires several times before React re-renders, and the
     rendered chapterIndex/page would be identical for every one of them. */
  const turn = (direction) => {
    if (paging.staleRef.current) return;
    const next = paging.pageRef.current + direction;
    if (next < 0) {
      if (chapterRef.current > 0) {
        paging.landAtEndRef.current = true;
        goToChapter(chapterRef.current - 1);
      }
      return;
    }
    if (next > paging.pagesRef.current - 1) {
      if (chapterRef.current < RD.chapter.total - 1) goToChapter(chapterRef.current + 1);
      return;
    }
    paging.goTo(next);
  };

  const goToChapter = (index) => {
    const clamped = Math.max(0, Math.min(index, RD.chapter.total - 1));
    if (clamped !== chapterRef.current) paging.staleRef.current = true;
    chapterRef.current = clamped;
    setChapterIndex(clamped);
    setAnnounce("Section " + (clamped + 1) + " of " + RD.chapter.total);
  };

  const stepChapter = (delta) => goToChapter(chapterRef.current + delta);

  /* Selection → annotation toolbar */
  const onMouseUp = () => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) return;
    const range = sel.getRangeAt(0);
    const host = range.startContainer.parentElement && range.startContainer.parentElement.closest("[data-paragraph]");
    if (!host || !host.contains(range.endContainer)) return;
    const start = textOffset(host, range.startContainer, range.startOffset);
    const end = textOffset(host, range.endContainer, range.endOffset);
    if (end - start < 2) return;
    const rect = range.getBoundingClientRect();
    setSelection({
      paragraph: Number(host.dataset.paragraph),
      start: Math.min(start, end),
      end: Math.max(start, end),
      quote: sel.toString(),
      rect: { top: rect.top, left: rect.left, width: rect.width }
    });
  };

  const openExisting = (note, event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    setSelection({
      id: note.id,
      paragraph: note.paragraph,
      start: note.start,
      end: note.end,
      quote: note.quote,
      existing: note,
      rect: { top: rect.top, left: rect.left, width: rect.width }
    });
  };

  const applyAnnotation = (type, color) => {
    if (!selection) return;
    setAnnotations((current) => {
      if (selection.id) {
        return current.map((note) => (note.id === selection.id
          ? { ...note, type, color: color || note.color }
          : note));
      }
      return current.concat([{
        id: "note-" + (current.length + 1000),
        chapter_index: chapterIndex,
        chapter_title: RD.chapter.title,
        paragraph: selection.paragraph,
        start: selection.start,
        end: selection.end,
        type,
        color: color || "yellow",
        quote: selection.quote,
        note_text: null,
        created_at: "2026-08-15T00:00:00Z"
      }]);
    });
    setAnnounce(TYPE_LABEL[type] + " applied");
    window.getSelection().removeAllRanges();
    setSelection(null);
  };

  const saveNote = (text) => {
    const target = editing;
    setAnnotations((current) => {
      if (target.id) return current.map((note) => (note.id === target.id ? { ...note, note_text: text, type: "note" } : note));
      return current.concat([{
        id: "note-" + (current.length + 2000),
        chapter_index: chapterIndex,
        chapter_title: RD.chapter.title,
        paragraph: target.paragraph,
        start: target.start,
        end: target.end,
        type: "note",
        color: null,
        quote: target.quote,
        note_text: text,
        created_at: "2026-08-15T00:00:00Z"
      }]);
    });
    setEditing(null);
    setSelection(null);
    setAnnounce("Note saved");
  };

  if (errorState === "epub-missing") {
    return (
      <div className="reader-error" data-testid="rd-error">
        <div className="empty-panel-inner">
          <div className="empty-symbol" aria-hidden="true">!</div>
          <h1 className="empty-title">This book’s EPUB file is missing</h1>
          <p className="empty-copy">
            <code>books/{book.id}/book.epub</code> could not be read, so the paginated view cannot render.
            Re-process the book to restore it.
          </p>
          <div className="settings-actions" style={{justifyContent: "center", marginTop: "16px"}}>
            <button className="btn" type="button" onClick={onBack}>Back to Library</button>
            <button className="btn btn-primary" type="button" data-testid="rd-error-reprocess">Re-process book</button>
          </div>
        </div>
      </div>
    );
  }

  const progress = Math.round(((paging.page + 1) / paging.pages) * 100);

  return (
    <div className="reader-shell" data-reading-font={prefs.font} data-testid="rd-shell">
      <LiveRegion page="rd" message={announce} />

      <header className="reader-header" data-testid="rd-header">
        <button className="btn btn-icon" type="button" aria-label="Back to library" data-testid="rd-header-back" onClick={onBack}>‹</button>
        <div className="reader-heading">
          <h1 className="reader-book-title">{book.title}</h1>
          <p className="reader-chapter-title">{RD.chapter.number} · {RD.chapter.title}</p>
        </div>
        <div className="reader-progress" aria-label={"Page " + (paging.page + 1) + " of " + paging.pages}>
          <div className="progress-track"><div className="progress-fill" style={{width: progress + "%"}}></div></div>
          <span data-testid="rd-page-indicator">{paging.page + 1} / {paging.pages}</span>
        </div>
      </header>

      <div className="reader-body">
        <main className="reader-stage" data-testid="rd-stage">
          <button className="page-arrow is-prev" type="button" aria-label="Previous page" data-testid="rd-page-prev" onClick={() => turn(-1)}>‹</button>
          <div className="reader-viewport" ref={viewportRef} onMouseUp={onMouseUp} data-testid="rd-viewport">
            <div
              className="page-flow"
              ref={flowRef}
              style={{
                transform: "translateX(" + -paging.page * (paging.width + paging.gap) + "px)",
                fontSize: prefs.size + "px",
                lineHeight: prefs.leading
              }}
            >
              <h2 className="chapter-heading">{RD.chapter.title}</h2>
              <p className="chapter-deck">{RD.chapter.deck}</p>
              {RD.chapter.paragraphs.map((text, index) => {
                const marks = chapterNotes.filter((note) => note.paragraph === index);
                if (marks.length === 0) return <p className="chapter-para" data-paragraph={index} key={index}>{text}</p>;
                return (
                  <p className="chapter-para" data-paragraph={index} key={index}>
                    {segmentParagraph(text, marks).map((segment, segIndex) => {
                      if (segment.marks.length === 0) return <React.Fragment key={segIndex}>{segment.text}</React.Fragment>;
                      const top = segment.marks[segment.marks.length - 1];
                      return (
                        <span
                          className={"anno is-" + top.type + " is-" + (top.color || "plain")}
                          key={segIndex}
                          role="button"
                          tabIndex="0"
                          title={top.note_text || TYPE_LABEL[top.type]}
                          data-testid="rd-anno-span" data-annotation-id={top.id}
                          onClick={(event) => openExisting(top, event)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") openExisting(top, event);
                          }}
                        >{segment.text}</span>
                      );
                    })}
                  </p>
                );
              })}
            </div>
          </div>
          <button className="page-arrow is-next" type="button" aria-label="Next page" data-testid="rd-page-next" onClick={() => turn(1)}>›</button>

          <footer className="chapter-nav" data-testid="rd-chapter-nav">
            <button
              className="btn"
              type="button"
              disabled={chapterIndex === 0}
              data-testid="rd-chapter-prev"
              onClick={() => stepChapter(-1)}
            >Previous</button>
            <span className="chapter-count" data-testid="rd-chapter-count">Section {chapterIndex + 1} of {RD.chapter.total}</span>
            <button
              className="btn"
              type="button"
              disabled={chapterIndex >= RD.chapter.total - 1}
              data-testid="rd-chapter-next"
              onClick={() => stepChapter(1)}
            >Next</button>
          </footer>
        </main>

        <nav className="reader-rail" aria-label="Reader tools" data-testid="rd-rail">
          {[["toc", "Contents", "≡"], ["search", "Search", "⌕"], ["notes", "Notes", "✎"], ["ai", "AI", "AI"]].map((item) => (
            <button
              className={"rail-button " + (panel === item[0] ? "is-active" : "")}
              type="button"
              key={item[0]}
              aria-label={item[1]}
              aria-pressed={panel === item[0]}
              title={item[1]}
              data-testid={RD_RAIL_TESTID[item[0]]}
              onClick={() => togglePanel(item[0])}
            >{item[2]}</button>
          ))}
          <div className="rail-divider" aria-hidden="true"></div>
          <div className="rail-popover-anchor">
            <button
              className={"rail-button " + (fontOpen ? "is-active" : "")}
              type="button"
              aria-label="Reading appearance"
              aria-expanded={fontOpen}
              title="Reading appearance"
              data-testid="rd-rail-font"
              onClick={() => {
                setPanel(null);
                setFontOpen((value) => !value);
              }}
            >Aa</button>
            {fontOpen && <FontPopover prefs={prefs} onPrefs={setPrefs} onClose={() => setFontOpen(false)} />}
          </div>
        </nav>

        {panel === "toc" && (
          <TocPanel
            current={chapterIndex}
            onClose={() => setPanel(null)}
            onJump={(section) => {
              goToChapter(section);
              setPanel(null);
            }}
          />
        )}
        {panel === "notes" && (
          <NotesPanel
            annotations={annotations}
            onClose={() => setPanel(null)}
            onReview={() => setReview(true)}
            onExport={() => setReview(true)}
            onJump={(note) => goToChapter(note.chapter_index)}
            onDelete={(note) => setConfirmDelete(note)}
          />
        )}
        {panel === "search" && (
          <ReaderSearchPanel
            indexStatus={book.index_status}
            onIndex={() => setAnnounce("Indexing started")}
            onClose={() => setPanel(null)}
            onJump={(hit) => {
              goToChapter(hit.section);
              setPanel(null);
            }}
          />
        )}
        {panel === "ai" && (
          <AiPanel
            width={aiWidth}
            onResize={setAiWidth}
            onClose={() => setPanel(null)}
            onJump={(section) => goToChapter(section)}
          />
        )}
      </div>

      {selection && !editing && (
        <AnnotationToolbar
          rect={selection.rect}
          existing={selection.existing}
          onClose={() => setSelection(null)}
          onCopy={() => {
            navigator.clipboard && navigator.clipboard.writeText(selection.quote);
            setAnnounce("Copied");
            setSelection(null);
          }}
          onApply={applyAnnotation}
          onNote={() => setEditing(selection)}
          onAsk={() => {
            setSelection(null);
            setPanel("ai");
          }}
          onDelete={() => {
            setAnnotations((current) => current.filter((note) => note.id !== selection.id));
            setSelection(null);
            setAnnounce("Annotation deleted");
          }}
        />
      )}

      {editing && (
        <NoteEditor
          quote={editing.quote}
          initial={editing.existing ? editing.existing.note_text : ""}
          onSave={saveNote}
          onClose={() => setEditing(null)}
        />
      )}

      {confirmDelete && (
        <ConfirmModal page="rd" name="delete-note"
          title="Delete this note?"
          body={"“" + confirmDelete.quote.slice(0, 90) + "…” and any attached text will be removed."}
          confirmLabel="Delete note"
          onCancel={() => setConfirmDelete(null)}
          onConfirm={() => {
            setAnnotations((current) => current.filter((note) => note.id !== confirmDelete.id));
            setConfirmDelete(null);
            setAnnounce("Note deleted");
          }}
        />
      )}

      {review && (
        <Modal page="rd" name="notes-review" title={"Review · " + annotations.length + " notes"} size="wide" onClose={() => setReview(false)}>
          <div className="review-list" data-testid="rd-notes-review-list">
            {annotations.map((note) => (
              <article className="review-item" key={note.id}>
                <div className="note-item-head">
                  <span className={"note-chip is-" + (note.color || "plain")}>{TYPE_LABEL[note.type]}</span>
                  <span className="result-section">{note.chapter_title}</span>
                </div>
                <blockquote className="note-quote">{note.quote}</blockquote>
                {note.note_text && <p className="note-text">{note.note_text}</p>}
              </article>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}

Object.assign(window, { ReaderScreen, segmentParagraph, textOffset, READING_THEMES, READING_FONTS });
