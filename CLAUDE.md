# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Reader3 Pro is a lightweight, self-hosted EPUB reader designed for reading books with LLMs. The application processes EPUB files into a structured format and serves them via a web interface, making it easy to copy chapter content and paste it into LLM conversations. The project includes full-text search capabilities (keyword and semantic) with RAG technology for intelligent book querying.

## Core Commands

### Processing EPUB Files
```bash
# Process an EPUB file and add it to the library
uv run reader3.py <file.epub>

# Example: Process Dracula
uv run reader3.py dracula.epub
```

This creates a `{bookname}_data/` directory containing:
- `book.pkl` - Serialized Book object
- `images/` - Extracted images from the EPUB
- `chroma_db/` - Vector embeddings for semantic search (created on demand)

### Running the Server
```bash
# Start the web server on http://127.0.0.1:8123
uv run server.py
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

### Search Features
```bash
# Keyword search works out of the box (no additional setup)

# For semantic search, ensure ChromaDB dependencies are installed:
uv add chromadb sentence-transformers

# Download the embedding model (paraphrase-multilingual-MiniLM-L12-v2, ~420MB):
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

# Model is cached at ~/.cache/huggingface/hub/ (macOS/Linux) or %USERPROFILE%\.cache\huggingface\hub\ (Windows)
```

## Architecture

### Three-Layer Architecture

**Layer 1: EPUB Processing (`reader3.py`)**
- Parses EPUB files using `ebooklib`
- Extracts and cleans HTML content with BeautifulSoup
- Builds two structures:
  - **Spine** (linear reading order): Physical HTML files from the EPUB
  - **TOC** (logical navigation): Hierarchical table of contents
- Extracts images and rewrites paths
- Serializes everything into `book.pkl` using pickle

**Layer 2: Search Service (`search_service.py`)**
- Provides keyword search across books with diacritic normalization
- Implements SearchQuery, SearchResult, SearchResultSet dataclasses
- Functions: `search_text()`, `search_book()`, `search_library()`
- Normalizes Latin scripts (café→cafe) while preserving non-Latin (Chinese, Japanese)
- XSS-safe HTML escaping via `escape_for_highlighting()`
- Performance: <500ms in-book search, <2s library-wide (up to 50 books)

**Layer 3: Web Server (`server.py`)**
- FastAPI application serving the reader interface
- Loads `book.pkl` files from `*_data/` directories
- Uses Jinja2 templates for rendering
- Caches loaded books with `lru_cache` (maxsize=10)
- Search endpoints: `/api/search/{book_id}`, `/api/search/library`, `/api/highlight/{book_id}/{chapter_order}`

### Key Data Structures

**Book Processing (`reader3.py`):**
```python
@dataclass
class Book:
    metadata: BookMetadata
    spine: List[ChapterContent]    # Linear reading order (actual files)
    toc: List[TOCEntry]            # Hierarchical navigation tree
    images: Dict[str, str]         # Original path -> local path mapping

@dataclass
class ChapterContent:
    id: str          # EPUB internal ID
    href: str        # Filename (e.g., 'part01.html')
    title: str       # Title from filename
    content: str     # Cleaned HTML
    text: str        # Plain text for search/LLM
    order: int       # Reading order
```

**Search (`search_service.py`):**
```python
@dataclass
class SearchQuery:
    term: str                                    # User search input
    mode: SearchMode                             # KEYWORD, SEMANTIC, HYBRID
    scope: SearchScope                           # CURRENT_BOOK, ALL_BOOKS
    case_sensitive: bool = False
    max_results: int = 1000                      # Capped at 1000
    book_id: Optional[str] = None

@dataclass
class SearchResult:
    book_id: str
    book_title: str
    book_author: str
    chapter_title: str
    chapter_order: int                           # Spine index for navigation
    occurrence_index: int                        # 0-indexed within chapter
    match_text: str
    context_before: str                          # 20 words or 40 chars
    context_after: str
    position: int                                # Character offset in chapter.text
    relevance_score: float = 0.0

@dataclass
class SearchResultSet:
    query: SearchQuery
    results: List[SearchResult]
    total_matches: int                           # May exceed len(results) if truncated
    searched_books: int
    failed_books: List[str]                      # Books that failed to search
    is_truncated: bool
    execution_time_ms: float
    grouped_by_book: Dict[str, List[SearchResult]]  # For library search
```

### Spine vs TOC

**Critical distinction:**
- **Spine**: Linear sequence of physical HTML files in reading order. What the reader displays chapter-by-chapter.
- **TOC**: Logical navigation tree that maps to spine files via `href`. Multiple TOC entries may point to the same spine file with different anchors.

The reader navigates spine sequentially (Previous/Next), while the sidebar shows the hierarchical TOC.

### Templates

`templates/library.html` - Library grid view listing all processed books
`templates/reader.html` - Reader interface with:
- Left sidebar: TOC navigation with recursive macro for nested entries
- Center: Current chapter content (from spine)
- Bottom: Previous/Next navigation
- JavaScript mapping: TOC hrefs → spine indices for click navigation

### Image Serving

Images are served via `/read/{book_id}/images/{image_name}` with path sanitization. HTML content has rewritten `<img src="images/pic.jpg">` paths that resolve to the book-specific route.

## Data Flow

1. User processes `book.epub` → creates `book_data/` with `book.pkl` + images
2. Server scans for `*_data/` directories on library page load
3. User clicks book → redirects to `/read/{book_id}/0` (first spine item)
4. Reader loads `book.pkl`, displays spine[0], renders TOC sidebar
5. Navigation: Previous/Next uses spine indices, TOC clicks map to spine via JavaScript

## Library Management

Books are added by processing EPUBs and removed by deleting the `{bookname}_data/` directory. There is no database - the filesystem is the source of truth.

## Constitution Principles

Reader3 Pro follows 7 core principles documented in `.specify/memory/constitution.md`:

1. **Data Structures First**: All entities as `@dataclass` with explicit type annotations before implementation
2. **Simplicity Over Engineering**: YAGNI - no frameworks, patterns, or abstractions beyond FastAPI/BeautifulSoup
3. **File-Based State Management**: Filesystem IS the database - each book = one `{bookname}_data/` directory
4. **HTML Content Sanitization**: XSS prevention via `html.escape()` before rendering user input (search terms)
5. **Path Security**: Book IDs validated against enumerated `*_data/` directories, no direct path construction
6. **Explicit Over Implicit**: Clear distinctions (spine vs TOC, keyword vs semantic), type-annotated signatures
7. **Performance Through Caching**: `@lru_cache` for frequent operations, ChromaDB HNSW for semantic search

**Key architectural decision**: Maintain simplicity and filesystem-based state. Resist premature optimization and over-engineering. The codebase should remain "vibes codable" with LLMs.

## Search Implementation Details

**Keyword Search** (no additional deps):
- Uses Python stdlib `re` + `unicodedata` for diacritic normalization
- Latin scripts normalized (café→cafe), non-Latin preserved exactly (Chinese, Japanese, etc.)
- Debouncing: 300ms in UI to prevent excessive requests
- Result limits: 1000 max per query, with truncation notification
- XSS prevention: All search terms HTML-escaped before highlighting

**Semantic Search** (requires ChromaDB setup):
- Uses ChromaDB with `paraphrase-multilingual-MiniLM-L12-v2` (384-dim embeddings)
- Per-book vector storage in `{bookname}_data/chroma_db/`
- RAG pattern: semantic search → retrieve relevant passages → provide context to LLM
- Indexing: On-demand (first search) or manual via CLI
- Performance: <1s single book, <3s library-wide

**Search UI**:
- Reader sidebar: In-book search with live results and highlighting
- Library page: Cross-book search with results grouped by book
- Deep linking: `/read/{book_id}/{chapter_index}?q=term&occurrence=0`

## Security Considerations

- **Pickle deserialization**: Currently loads pickle files without validation. Only process trusted EPUB files.
- **Path traversal**: Book IDs validated against enumerated directories (constitution principle V)
- **XSS prevention**: Search terms HTML-escaped via `escape_for_highlighting()` (constitution principle IV)
- **Input validation**: Search terms capped at 500 chars, max_results capped at 1000
- **HTML sanitization**: `clean_html_content()` removes script/style/iframe tags

## Performance Targets

- **In-book keyword search**: <500ms for books up to 500 pages
- **Library-wide search**: <2s for libraries up to 50 books
- **Semantic search**: <1s single book, <3s library-wide
- **Book loading**: `lru_cache(maxsize=10)` - increase for concurrent users
- **Scalability**: Tested up to 50 books; consider database migration for >100 books

## Feature Development Workflow

Reader3 Pro uses a spec-driven development process with numbered feature branches:

**Branch naming**: `{number}-{short-name}` (e.g., `001-search-features`, `002-ai-assistant`)

**Specs directory**: Each feature has its own `specs/{number}-{short-name}/` with:
- `spec.md` - User stories, requirements, success criteria
- `plan.md` - Technical design, architecture decisions
- `tasks.md` - Implementation tasks organized by user story
- `data-model.md` - Entity definitions
- `contracts/` - API specifications (OpenAPI YAML)
- `checklists/` - Quality validation checklists

**Current features**:
- `001-search-features`: Keyword + semantic search (completed: P1-P2, pending: P3)
- `002-ai-assistant`: AI-powered book summarization and Q&A (spec complete, planning phase)

**Commands**:
- `/speckit.specify` - Create feature specification
- `/speckit.clarify` - Resolve ambiguous requirements
- `/speckit.plan` - Generate technical implementation plan
- `/speckit.tasks` - Generate implementation task breakdown
