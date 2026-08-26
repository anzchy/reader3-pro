# reader 3 Pro

![reader3](reader3.png)

A lightweight, self-hosted EPUB reader that lets you read through EPUB books one chapter at a time. It includes a reorganized 3-pane Library UI with Collections, bulk semantic indexing, Dashboard stats, and cross-book search.

This project is an enhanced version (thus add `pro` to repo name) of Andrie Karpathy's reader3 project.



## How It Works

#### Reader

1. `src/reader3_app/reader3.py` parses an `.epub`, cleans HTML, extracts plain text, and writes a `books/{bookname}_data/` folder.
2. The folder contains `book.pkl` (a pickled `Book` dataclass), `book.epub` (original EPUB copy for the reader), and `images/` (extracted assets).
3. `src/reader3_app/web/server.py` serves the Library + Reader UI, uses `book.pkl` for metadata/TOC/search, and passes the EPUB URL to the frontend.
4. The reader page loads `book.epub` in the browser via epub.js and renders the chapter content inside an iframe.

#### Reader Navigation & Annotations

- **Keyboard navigation**: Left/Right arrow keys turn pages inside the current chapter. Up/Down arrow keys move to previous/next chapter.
- **TOC/Notes/Search/AI**: Use the right toolbar buttons to open panels; click the reading area or press `Esc` to close.
- **Mark text**: Select text to show the annotation toolbar, pick a color, then click Marker / Underline / Wavy to apply.
- **Reopen annotations**: Click existing highlighted text to reopen the toolbar for edits or deletion.
- **Add notes**: Select text, choose color, click Add Note, then save.
- **Unmark**: Select the annotated text and click Delete to remove the annotation.

#### Search (Keyword + RAG/Semantic)

- **Keyword search** scans `ChapterContent.text` with Latin diacritic normalization (e.g. `café` → `cafe`) and returns matches with context.
- **Semantic search** is a lightweight local RAG-style retrieval:
  - Indexing chunks each chapter into ~1000-character passages (with overlap), embeds them using `sentence-transformers`, and stores vectors in ChromaDB under `{book_id}/chroma_db/`.
  - Searching embeds your query and retrieves the most similar passages (even without exact keyword matches).

## Project Structure

```text
.
├── src/
│   └── reader3_app/
│       ├── collections_service.py   # Collections storage (config/library_collections.json)
│       ├── reader3.py              # EPUB processing + (optional) CLI indexing
│       ├── search_service.py       # Keyword + library search logic
│       ├── vector_search.py        # ChromaDB indexing + semantic retrieval
│       ├── ai/                     # AI assistant backend modules
│       └── web/
│           ├── server.py           # FastAPI app
│           ├── templates/          # Jinja templates (library.html, library_classic.html, reader.html)
│           └── static/             # JS/CSS assets (library.js/css, search.css, library-search.js)
├── config/
│   └── ai_settings.example.json    # Example AI config (copy to ai_settings.json)
├── docs/
│   └── plans/
│       ├── 20260816-tech-stack-migration/   # Backend half: plans, review, branch tasks
│       └── 20260817-frontend-ui-refactor/   # Frontend half: plan (WI-1..WI-20),
│                                            #   design spec, host contracts
├── specs/
│   └── _archive/           # Historical spec-kit records for shipped features (frozen)
└── books/                  # Generated per-book folders (ignored by git)
    └── *_data/             # One folder per book (book.pkl, book.epub, images/, chroma_db/)
```



## How to Use 

#### Setup

This project uses [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## AI Assistant (Anthropic / Ollama)

The AI panel uses the `default_provider` from `config/ai_settings.json` (editable via the web Settings page at `/settings` or by editing the file directly).

1) Copy the example config, and lock it down before a key goes in it:

```bash
cp config/ai_settings.example.json config/ai_settings.json
chmod 600 config/ai_settings.json   # 这份文件将保存明文 API key
```

`cp` 继承的是 umask，通常是 `0644`——同机器上的其他用户读得到。经 `/settings`
存过一次之后 `save_ai_settings` 会自己把它写成 `0600`（tmp + `os.replace`，新建和
既有一视同仁），但手抄 key 直接编辑文件的人永远走不到那一步，所以这里补一次。

2) Make sure the book is indexed for semantic retrieval (required for RAG summary/Q&A citations):

```bash
# 无需带./books/dracula_data
uv run reader3 --index dracula_data
# 成功后后显示：Indexed the-power-broker_data: 4556 chunks using paraphrase-multilingual-MiniLM-L12-v2
```

3) Start the server:

```bash
uv run reader3-server
```

Open a book, click the **AI** button on the right toolbar, and use quick actions or chat.

Technical details (chat storage locations, IndexedDB paths, provider privacy, speed tuning, model caches):
- `docs/technical-detail.md`



#### Add a New EPUB (from scratch)

Download an EPUB (e.g. [Dracula EPUB3](https://www.gutenberg.org/ebooks/345)) and run:

```bash
uv run reader3 ./books/dracula.epub
```

This creates `books/dracula_data/`, which registers the book to your local library. Then start the server:

```bash
uv run reader3-server
```

Visit [localhost:8123](http://localhost:8123/) to see your Library. To remove a book, delete its `books/*_data/` folder.

### Server Options (new in 1.5.0)

```bash
# Pick the port. Precedence: --port > READER3_PORT > 8123
uv run reader3-server --port 9000

# Point the library somewhere other than ./books
READER3_BOOKS_DIR=/path/to/library uv run reader3-server

# Readiness probe -- never touches disk, answers 200 even on an empty library
curl http://127.0.0.1:8123/api/health
```

**Reaching the server from another machine?** The server now validates the `Host`
header and answers `400 Invalid host header` to anything it does not recognise.
This shuts the door on DNS-rebinding attacks against your library, and it means a
default install only answers to `127.0.0.1`, `localhost` and `[::1]`. If you reach
it over a LAN address, a hostname or a reverse proxy, list those names yourself:

```bash
READER3_ALLOWED_HOSTS=192.168.1.20,reader.lan uv run reader3-server
```

Optionally, require a shared secret on every request:

```bash
READER3_TOKEN=$(openssl rand -hex 16) uv run reader3-server
```

The token suits CLI and reverse-proxy setups. The browser UI does not attach it to
its own `fetch` calls yet, so with a token set the pages load but in-page actions
fail -- leave it unset for normal desktop use.

### Library UI Mode (modern/classic)

The Library UI supports rollback to the classic page:

```bash
# Modern (default)
READER3_LIBRARY_UI=modern uv run reader3-server

# Classic (pre-004)
READER3_LIBRARY_UI=classic uv run reader3-server
```

If you already have `*_data/` folders at repo root, move them into `books/`:

```bash
mkdir -p books
find . -maxdepth 1 -type d -name '*_data' -print0 | xargs -0 -I{} mv "{}" books/
```

#### (Optional) Manual Setup: Semantic Search Dependencies (Phase 1)

Keyword search works out of the box. Semantic search needs the extra dependencies and an embedding model:

```bash
uv add chromadb sentence-transformers
uv run python -c "import chromadb, sentence_transformers; print('OK')"
uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
```

The model download is large (~420MB) and is cached by HuggingFace after the first run. For cache locations and offline/portable setup, see:
- `docs/models-and-caches.md`

#### Index a Book (Semantic Search)

You can index from the Library UI (Selection mode → **Index selected**), from Library Search results (semantic/hybrid mode), or via CLI:

```bash
uv run reader3 --index dracula_data
```

This writes a per-book vector store to `books/dracula_data/chroma_db/`.



## How to Search

### Reader (in-book)

Open any book. Click the **search button** in the right-side vertical toolbar to open the search drawer, type your query, then press **Enter**.

- **Mode**: `keyword` (exact) / `semantic` (meaning) / `hybrid` (mix)
- Click a result to jump to that chapter. Keyword results highlight all occurrences and scroll to the selected match.
- Use **×** to clear results/highlights. Toggle **Case sensitive** as needed.

You can also deep-link to a highlighted chapter/occurrence:

`/read/{book_id}/{chapter_index}?q=your+term&occurrence=0`

Where `book_id` is the processed folder name (e.g. `dracula_data`).

### Library (cross-book)

On the Library page, open the right panel **Search** tab to search across all processed books (`*_data/`).

- Results are grouped by book; click a passage to open the book at the matching chapter/occurrence.
- Use **Sort** (relevance/title/author), **Case**, and **Mode**.
- In semantic/hybrid mode, each book shows its index status; click **Index** to build vectors if needed.

### Collections (Library organization)

Collections are user-defined groups of books:

- Create Collections in the left sidebar and add books via Selection mode → **Add to collection**.
- Collections persist to `config/library_collections.json` (gitignored).



## License

MIT
