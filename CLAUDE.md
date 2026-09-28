# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Reader3 Pro is a lightweight, self-hosted EPUB reader designed for reading books with LLMs. The application processes EPUB files into a structured format and serves them via a web interface, making it easy to copy chapter content and paste it into LLM conversations. The project includes full-text search capabilities (keyword and semantic) with RAG technology for intelligent book querying.

## Core Commands

### Processing EPUB Files
```bash
# Process an EPUB file and add it to the library
uv run reader3 ./books/<file.epub>

# Example: Process Dracula
uv run reader3 ./books/dracula.epub

# Index a book for semantic search/RAG
uv run reader3 --index dracula_data
```

This creates a `books/{bookname}_data/` directory containing:
- `book.pkl` - Serialized Book object
- `book.epub` - Original EPUB copy for epub.js rendering
- `images/` - Extracted images from the EPUB
- `chroma_db/` - Vector embeddings for semantic search (created on demand)

### Running the Server
```bash
# Start the web server on http://127.0.0.1:8123
uv run reader3-server
```

### AI Assistant Setup
```bash
# Copy example config. chmod is not optional: cp inherits the umask (usually 0644)
# and this file holds plaintext API keys. Saving via /settings rewrites it 0600,
# but hand-editing the copied file never reaches that path.
cp config/ai_settings.example.json config/ai_settings.json
chmod 600 config/ai_settings.json

# Configure via Web UI: http://127.0.0.1:8123/settings
# Or edit config/ai_settings.json directly (API keys never returned to browser)
```

**Supported providers**: `anthropic`, `openai`, `gemini`, `openrouter`, `ollama`

### Tests and Checks
```bash
uv run pytest tests/unit tests/contract      # backend unit + API contract (the commit-gated lane)
npm test                                     # frontend Vitest (also commit-gated)
npm run typecheck                            # frontend tsc
uv run pytest tests/e2e --browser chromium   # Playwright E2E (push-gated)
uv run ruff check src/ tests/ scripts/       # lint -- do NOT run `ruff format`; line length is a cap, not a format target
uv run mypy src/
python3 scripts/check_router_size.py         # router size gate; the other scripts/lint_*.py run the same way
python3 scripts/build_feature_ledger.py --check   # feature ledger md↔html drift
```

The authoritative lane definitions (commands, which trigger gates them) are in
`.claude/tdd-guardian/config.json`; CI mirrors them in `.github/workflows/{tests,lint}.yml`.

## Architecture

### Four-Layer Architecture

```
Layer 1: EPUB Processing (reader3.py)
         ↓ book.pkl
Layer 2: Search & Vector Services (search_service.py, vector_search.py)
         ↓
Layer 3: AI Assistant (ai/)
         ↓
Layer 4: Web Server (web/server.py)
```

**Layer 1: EPUB Processing (`reader3.py`)**
- Parses EPUB files using `ebooklib`, cleans HTML with BeautifulSoup
- Builds **Spine** (linear reading order) and **TOC** (hierarchical navigation)
- Serializes to `book.pkl` using pickle

**Layer 2: Search & Vector Services**
- `search_service.py` - Keyword search with diacritic normalization (café→cafe)
- `vector_search.py` - Semantic search using ChromaDB + `paraphrase-multilingual-MiniLM-L12-v2`
- `notes_service.py` - Annotation persistence to `books/{book_id}_data/notes.json`

**Layer 3: AI Assistant (`ai/`)**
- `config.py` - Multi-provider settings management
- `providers/` - Provider implementations (anthropic, openai, gemini, ollama, openrouter)
- `rag.py` - RAG pipeline with retrieval + context injection
- `conversations.py` - Conversation storage (per-book or project-root)

**Layer 4: Web Server (`web/server.py`)**
- FastAPI app with Jinja2 templates
- Caches loaded books with `lru_cache(maxsize=10)`
- Serves `book.epub` at `/read/{book_id}/book.epub` for epub.js rendering
- Endpoint groups: `/api/search/*`, `/api/ai/*`, `/api/settings/*`, `/api/library/*`, `/api/notes/*`

### Spine vs TOC (Critical Distinction)

- **Spine**: Linear sequence of physical HTML files in reading order. What the reader displays chapter-by-chapter. Navigate with Previous/Next.
- **TOC**: Logical navigation tree that maps to spine files via `href`. Multiple TOC entries may point to the same spine file with different anchors. Shown in sidebar.

### Key Data Structures

`Book` / `ChapterContent` in `src/reader3_app/reader3.py`; `Annotation` in
`src/reader3_app/models/annotations.py`. Read them there — they are the definition site.

### Book Identity System

Each book has two identifiers:
- **book_folder**: Filesystem name (e.g., `dracula_data`) - used for file paths
- **book_uuid**: Stable UUID in `{book_folder}/ai_meta.json` - used for conversation tracking

Why two identifiers, and the rule that an unreadable `ai_meta.json` degrades to `uuid=None` rather than being overwritten: [ADR-0003](docs/adr/0003-dual-book-identity.md).

## Frontend Development

Templates live in `src/reader3_app/web/templates/`, static assets in
`src/reader3_app/web/static/` — `ls` them rather than trusting a list here.

Two things `ls` won't tell you:
- `js/epub-renderer.js` is the live renderer (epub.js); the old CSS-column pagination
  script was deleted in 013 WI-9, so don't look for a second renderer.
- JavaScript is vanilla ES6+ (no frameworks). CSS is plain CSS (no preprocessors).

## Constitution Principles (Summary)

Reader3 Pro follows 7 core principles. This list is the authority — the former
`.specify/memory/constitution.md` was removed with the spec-kit toolchain (2026-08-16):

1. **Data Structures First**: All entities as `@dataclass` with type annotations
2. **Simplicity Over Engineering**: YAGNI - no abstractions beyond FastAPI/BeautifulSoup → [ADR-0008](docs/adr/0008-tech-stack-boundary.md)
3. **File-Based State Management**: Filesystem IS the database (`*_data/` directories) → [ADR-0001](docs/adr/0001-filesystem-as-database.md), write protocol [ADR-0007](docs/adr/0007-crash-safe-publish-protocol.md), on-disk format [ADR-0009](docs/adr/0009-book-format-manifest-jsonl.md)
4. **HTML Content Sanitization**: XSS prevention via `html.escape()` and `clean_html_content()`
5. **Path Security**: Validate book IDs against enumerated directories, use `os.path.basename()` → [ADR-0012](docs/adr/0012-security-boundaries.md), provider egress [ADR-0006](docs/adr/0006-provider-egress-single-gate.md)
6. **Explicit Over Implicit**: Type hints everywhere, clear naming, documented distinctions
7. **Performance Through Caching**: `@lru_cache` for expensive operations

**Key architectural decision**: Maintain simplicity. Resist premature optimization. The codebase should remain "vibes codable" with LLMs.

## Feature Development Workflow

**The spec-kit framework is no longer used.** `.specify/` and the `/speckit.*` commands were
removed on 2026-08-16. Do not attempt to invoke them.

Planning docs live under `docs/plans/{date}-{topic}/`; long-lived decisions live in `docs/adr/`
(read the Accepted ADRs before touching a data model, a public interface, or anything crossing
modules). `specs/` holds only frozen `_archive/` — **never implement from it**.

**Before opening a branch, allocating a branch number, editing anything under `docs/plans/`, or
deciding what to work on next, load the `plan-and-branch-map` skill** — it carries the
authoritative milestone table, the branch-numbering rule, and the 「权威范围」 split between the
two active plan folders.

### Feature Ledger

[`docs/feature-ledger.md`](docs/feature-ledger.md) is the as-built record of what the product can do
(`F-NNN` rows: status, code, tests, evidence, known limits). Read it at session start instead of
re-deriving "what exists" from code.

**After every feature module is accepted — merged to `master` with its gating lanes green — update
the ledger in the same PR or the plan write-back commit.** Add a row for a new capability, or edit
the existing row (evidence, limits, `partial` → `accepted`). Never log planned or unmerged work there,
never delete or renumber rows, and keep every `Code`/`Tests` path real. Rules and the checklist are
at the top and bottom of that file.
[`docs/feature-ledger.html`](docs/feature-ledger.html) is the status dashboard view of the same data;
the `.md` is the source — regenerate its `ledger-data` block with `python3 scripts/build_feature_ledger.py`
in the same change (never hand-edit it). CI runs `python3 scripts/build_feature_ledger.py --check`.

## Data Flow

1. User processes `book.epub` → creates `books/book_data/` with `book.pkl` + images
2. Server scans for `books/*_data/` directories on library page load
3. User clicks book → redirects to `/read/{book_id}/0` (first spine item)
4. Reader loads `book.pkl`, displays spine[0], renders TOC sidebar
5. Navigation: Previous/Next uses spine indices, TOC clicks map to spine via JavaScript

## Troubleshooting

**AI Assistant Issues**:
- `AI provider is disabled`: Enable in `/settings` and restart server
- `API key not configured`: Set provider API key in `/settings`
- `Ollama not running`: Start with `ollama serve`, verify with `ollama ps`
- Semantic index missing: Run `uv run reader3 --index <book_folder>`

**Common Operations**:
- Delete a book: Remove its `books/{bookname}_data/` directory
- Move existing `*_data/` folders to `books/`: `find . -maxdepth 1 -type d -name '*_data' -exec mv {} books/ \;`
