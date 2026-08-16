# Implementation Plan: Search Functionality

**Branch**: `001-search-features` | **Date**: 2025-12-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-search-features/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Implement search functionality for Reader3 Pro in three layers: (P1) in-book keyword search with highlighting + context extraction, (P2) cross-book keyword search on the library page with results grouped by book, and (P3, optional) semantic cross-book search using embeddings. The implementation uses ChromaDB for vector storage with paraphrase-multilingual-MiniLM-L12-v2 embeddings, maintaining per-book `chroma_db/` folders alongside existing `book.pkl` files to preserve the filesystem-based architecture. Keyword search uses Python stdlib (re + unicodedata) for diacritic normalization with <500ms single-book and <2s library-wide performance targets.

## Technical Context

**Language/Version**: Python 3.10+ (current project requirement)
**Primary Dependencies**:
- Existing: FastAPI 0.121.2+, Jinja2 3.1.6+, BeautifulSoup4 4.14.2+, ebooklib 0.20+
- New: ChromaDB 0.4.22+, sentence-transformers 2.3.0+
**Storage**: File-based (pickle + ChromaDB persistent storage in `{bookname}_data/chroma_db/`)
**Testing**: pytest (to be added for search functionality)
**Target Platform**: Self-hosted web application (macOS/Linux/Windows, localhost:8123)
**Project Type**: Single-project web application with FastAPI backend + Jinja2 templates frontend
**Performance Goals**:
- In-book keyword search: <500ms for books up to 500 pages
- Library-wide search: <2s for libraries up to 50 books
- Semantic search: <1s single book, <3s library-wide
- Search input debouncing: 300ms
**Constraints**:
- Self-hosted single-user deployment (no authentication required initially)
- Must maintain existing pickle-based architecture (no migration)
- Storage overhead: <50% additional per book (~2-3 MB embeddings per typical book)
- Memory footprint: <200 MB for in-memory search index (50 books)
**Scale/Scope**:
- Target: <100 books in typical library
- Support: Up to 500 pages per book
- Languages: English + Chinese (primary), extensible to other scripts
- Search results: Max 1,000 occurrences displayed per query

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Data Structures First
**Status**: ✅ PASS
- Will define `@dataclass` for: `SearchResult`, `SearchQuery`, ~~`SearchIndex`~~, `HighlightRange`
  - ⚠️ `SearchIndex` **SUPERSEDED 2026-08-16**：已作为死代码删除，改为 per-book 惰性加载 `load_book_index()`。`BookIndex` / `ChapterIndex` 保留为活代码。见 `specs/001-search-features/data-model.md` 文首说明
- All search entities have explicit type annotations
- ChromaDB integration abstracted behind `BookVectorIndex` class
- Clear separation: search logic in `search_service.py`, vector storage in `vector_search.py`

### II. Simplicity Over Engineering
**Status**: ✅ PASS
- ChromaDB chosen over complex alternatives (Qdrant, Milvus) for zero-infrastructure deployment
- Keyword search uses Python stdlib (re + unicodedata) instead of heavyweight libraries
- No repository pattern, service locator, or DI containers
- Lazy indexing: generate embeddings only on first search (YAGNI)
- Per-book indexes avoid global state complexity

### III. File-Based State Management
**Status**: ✅ PASS
- Maintains `{bookname}_data/` directory pattern
- Adds `chroma_db/` folder alongside existing `book.pkl` and `images/`
- No global search index or shared state files
- Book deletion removes entire `{bookname}_data/` directory (existing behavior preserved)
- Library scanning still uses glob patterns (`*_data/`)

### IV. HTML Content Sanitization
**Status**: ✅ PASS
- Search terms escaped via `html.escape()` before highlighting (FR-012a)
- Prevents XSS: `<script>` → `&lt;script&gt;`
- Search operates on `ChapterContent.text` (plain text, no HTML)
- Highlighting applied to sanitized content only

### V. Path Security
**Status**: ✅ PASS
- Book IDs validated against enumerated `*_data/` directories before search
- No direct path construction from user input
- ChromaDB paths constructed via `os.path.join()` with validated book_id
- Search queries are string content only (no file path operations)

### VI. Explicit Over Implicit
**Status**: ✅ PASS
- Clear distinction between keyword search (exact matching) and semantic search (embedding-based)
- Diacritic normalization explicitly documented: Latin scripts normalized, non-Latin preserved
- Type-annotated function signatures for all search operations
- Comments explain relevance scoring formula (FR-022)

### VII. Performance Through Caching
**Status**: ✅ PASS
- `@lru_cache` for frequently searched terms (keyword search)
- ChromaDB HNSW index provides built-in caching for semantic search
- In-memory search index built once on server start, reused for all queries
- Lazy indexing: generate embeddings only when needed, cache thereafter

### Additional Checks

**Security Requirements**:
- ✅ XSS prevention: HTML entity escaping (Principle IV)
- ✅ Path security: Book ID validation (Principle V)
- ✅ No user authentication required (self-hosted, trusted environment)

**Performance Targets**:
- ✅ <500ms in-book search (validated in research)
- ✅ <2s library-wide search (validated in research)
- ✅ 300ms debouncing prevents excessive searches

**Dependencies**:
- ✅ ChromaDB: Minimal, pip-installable, no services required
- ✅ sentence-transformers: Standard library for embeddings
- ✅ No framework sprawl beyond FastAPI (existing)

### Final Verdict: ✅ ALL GATES PASSED

No constitution violations. Implementation aligns with all 7 core principles and maintains project philosophy of simplicity and filesystem-based state.

## Project Structure

### Documentation (this feature)

```text
specs/001-search-features/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output - RAG/vector DB research ✓
├── data-model.md        # Phase 1 output - Search entities
├── quickstart.md        # Phase 1 output - Developer guide
├── contracts/           # Phase 1 output - API specifications
│   └── search-api.yaml  # OpenAPI spec for search endpoints
├── checklists/          # Quality validation
│   └── requirements.md  # Spec validation checklist ✓
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
reader3-pro/
├── reader3.py                    # Existing: EPUB processing
├── server.py                     # Existing: FastAPI server (add search endpoints)
├── search_service.py             # NEW: Keyword search implementation
├── vector_search.py              # NEW: ChromaDB semantic search
├── templates/
│   ├── library.html              # UPDATE: Add library search box
│   └── reader.html               # UPDATE: Add sidebar search box + results UI
├── static/
│   └── search.js                 # NEW: Search UI interactions, highlighting
├── {bookname}_data/              # Existing pattern, now with vector storage
│   ├── book.pkl                  # Existing: Serialized Book object
│   ├── images/                   # Existing: Extracted images
│   └── chroma_db/                # NEW: Per-book vector embeddings
│       ├── chroma.sqlite3        # ChromaDB metadata
│       └── vectors/              # HNSW index files
└── tests/                        # NEW: Test suite for search
    ├── test_search_service.py    # Keyword search unit tests
    ├── test_vector_search.py     # Semantic search unit tests
    └── test_integration.py       # End-to-end search tests
```

**Structure Decision**: Single-project web application structure. Reader3 Pro is a FastAPI backend with Jinja2 templates for the frontend. All search functionality will be added as new Python modules (`search_service.py`, `vector_search.py`) and new API endpoints in `server.py`. The per-book `chroma_db/` folders maintain the existing filesystem-based architecture where each book is self-contained in its `{bookname}_data/` directory. No separate frontend/backend split needed - templates are enhanced with JavaScript for search UI interactions.

## Complexity Tracking

**Status**: No violations recorded.

All constitution principles satisfied. No complexity justifications required.
