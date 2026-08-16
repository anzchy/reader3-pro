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

# Use classic library UI (pre-004)
READER3_LIBRARY_UI=classic uv run reader3-server
```

### Dependency Management
```bash
# Install dependencies
uv sync

# Add a new dependency
uv add <package-name>

# Update dependencies
uv lock --upgrade
```

### AI Assistant Setup
```bash
# Copy example config
cp config/ai_settings.example.json config/ai_settings.json

# Configure via Web UI: http://127.0.0.1:8123/settings
# Or edit config/ai_settings.json directly (API keys never returned to browser)
```

**Supported providers**: `anthropic`, `openai`, `gemini`, `openrouter`, `ollama`

**Key API endpoints**:
- `GET/PUT /api/settings` - Global settings
- `POST /api/ai/question/{book_uuid}?stream=true` - Q&A streaming (SSE)
- `GET/POST/DELETE /api/ai/conversations/{book_uuid}` - Conversation management
- `GET /api/notes/{book_id}` - List annotations for a book
- `GET/POST /api/notes/{book_id}/{chapter_index}` - Fetch/create annotations for a chapter
- `PUT/DELETE /api/notes/{book_id}/{chapter_index}/{note_id}` - Update/delete an annotation

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

```python
# Core book model (reader3.py)
@dataclass
class Book:
    metadata: BookMetadata
    spine: List[ChapterContent]    # Linear reading order
    toc: List[TOCEntry]            # Hierarchical navigation

@dataclass
class ChapterContent:
    id: str          # EPUB internal ID
    href: str        # Filename (e.g., 'part01.html')
    title: str       # Title from filename
    content: str     # Cleaned HTML
    text: str        # Plain text for search/LLM
    order: int       # Spine index for navigation

# Annotation model (models/annotations.py)
@dataclass
class Annotation:
    id: str                        # UUID
    book_id: str                   # Book folder name
    chapter_index: int             # Spine index
    type: AnnotationType           # "marker" | "wavy" | "underline" | "note"
    color: Optional[MarkerColor]   # "yellow" | "green" | "pink" | "blue" (marker/underline/wavy)
    quote: str                     # Selected text
    prefix: str                    # Context before (max 50 chars)
    suffix: str                    # Context after (max 50 chars)
    note_text: Optional[str]       # User's note content
    cfi: Optional[str]             # epub.js CFI anchor (optional)
```

### Book Identity System

Each book has two identifiers:
- **book_folder**: Filesystem name (e.g., `dracula_data`) - used for file paths
- **book_uuid**: Stable UUID in `{book_folder}/ai_meta.json` - used for conversation tracking

## Frontend Development

Templates in `src/reader3_app/web/templates/`:
- `library.html` - Modern 3-pane library UI (left: collections, center: book grid, right: search/chat)
- `library_classic.html` - Legacy grid view
- `reader.html` - Full-screen paginated reading interface with TOC sidebar, annotations, and panels

Static assets in `src/reader3_app/web/static/`:
- `library.js` / `library.css` - Library UI logic and styles
- `library-search.js` - Cross-book search functionality
- `js/epub-renderer.js` - epub.js integration (iframe rendering, progress, navigation)
- `js/pagination.js` - Legacy CSS column pagination (not loaded by reader.html)
- `js/annotations.js` - Text selection, highlighting, and notes toolbar
- `js/notes-panel.js` - Notes panel with chapter grouping
- `js/toolbar.js` - Right-side vertical toolbar
- `js/toc-panel.js` - Table of contents panel
- `css/reader.css` - Full-screen reader styles
- `css/annotations.css` - Annotation styling (marker, underline, wavy)

JavaScript uses vanilla ES6+ (no frameworks). CSS is plain CSS (no preprocessors).

## Constitution Principles (Summary)

Reader3 Pro follows 7 core principles. This list is the authority — the former
`.specify/memory/constitution.md` was removed with the spec-kit toolchain (2026-08-16):

1. **Data Structures First**: All entities as `@dataclass` with type annotations
2. **Simplicity Over Engineering**: YAGNI - no abstractions beyond FastAPI/BeautifulSoup
3. **File-Based State Management**: Filesystem IS the database (`*_data/` directories)
4. **HTML Content Sanitization**: XSS prevention via `html.escape()` and `clean_html_content()`
5. **Path Security**: Validate book IDs against enumerated directories, use `os.path.basename()`
6. **Explicit Over Implicit**: Type hints everywhere, clear naming, documented distinctions
7. **Performance Through Caching**: `@lru_cache` for expensive operations

**Key architectural decision**: Maintain simplicity. Resist premature optimization. The codebase should remain "vibes codable" with LLMs.

## Feature Development Workflow

**The spec-kit framework is no longer used.** `.specify/` and the `/speckit.*` commands were
removed on 2026-08-16. Do not attempt to invoke them.

### Where documents live

| Directory | Contents | Lifecycle |
|---|---|---|
| `docs/plans/{date}-{topic}/` | One self-contained body of planning work: plans, specs, contracts, review records, per-branch task lists | Living until the work ships |
| `docs/plans/*.md` | Standalone plans that aren't part of a larger effort | Living |
| `specs/_archive/` | Historical spec-kit records for shipped features | **Frozen. Code is authoritative. Never implement from here.** |
| `designs/` | Design references and executable prototypes | Living |

**A planning effort is one folder.** Everything a plan needs to be read and executed —
the plan itself, its design spec, its interface contracts, its review record, and the
task list for each branch it spawns — lives together under one dated folder. Don't scatter
these across `docs/`, `specs/`, and `docs/contracts/`; a reader who opens the folder should
need nothing outside it except the code and `designs/`.

The one active effort today is
[`docs/plans/20260816-tech-stack-and-ui-changes/`](docs/plans/20260816-tech-stack-and-ui-changes/README.md) —
the tech-stack migration and UI redesign (branches 007–015). Start at its `README.md`.

`specs/` now contains only `_archive/`. It holds 171 unchecked `- [ ]` items that all describe
already-shipped or abandoned work. See [`specs/_archive/README.md`](specs/_archive/README.md)
before reading anything in there — `003-add-book-notes` in particular describes an annotation
system that was never built that way (the shipped one came from `006-hot-fix`).

### Branch naming

`{number}-{short-name}`. **Numbers are allocated in one place only**: §9 of
[`plan-ui-migration-sequencing.md`](docs/plans/20260816-tech-stack-and-ui-changes/plan-ui-migration-sequencing.md).
Do not invent a new number without updating that table.

| Milestone | Branch | Status |
|---|---|---|
| M0 — Phase 0 contracts + hygiene | `007-hygiene-and-contracts` | 🚧 In progress |
| M1 — tests + CI + API freeze | `008-test-safety-net` | Allocated |
| M1b — Playwright E2E | `009-e2e-annotations` | Tasks drafted |
| MD — design degradation states | `010-design-degradation-states` | Allocated |
| M2 — backend refactor | `011-backend-refactor` | Allocated |
| M3 — storage migration | `012-storage-format` | Allocated |
| M4a — TS shell + settings + library | `013-ts-frontend-shell` | Allocated |
| M4b — TS reader | `014-ts-frontend-reader` | Tasks drafted |
| M5 — launch + PWA | `015-launch-experience` | Allocated |

"Allocated" means the number is reserved but no branch exists yet. "Tasks drafted" means
`docs/plans/20260816-tech-stack-and-ui-changes/tasks/{branch}.md` exists.

### Shipped features (implemented; see code, not specs)

Keyword + semantic search · multi-provider AI with RAG · 3-pane library with collections and bulk
indexing · Dedao-style UI · full-screen paginated reader with annotations.

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
