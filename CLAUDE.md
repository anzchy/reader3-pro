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

**Layer 3: AI Assistant (`ai/`)**
- `config.py` - Multi-provider settings management
- `providers/` - Provider implementations (anthropic, openai, gemini, ollama, openrouter)
- `rag.py` - RAG pipeline with retrieval + context injection
- `conversations.py` - Conversation storage (per-book or project-root)

**Layer 4: Web Server (`web/server.py`)**
- FastAPI app with Jinja2 templates
- Caches loaded books with `lru_cache(maxsize=10)`
- Endpoint groups: `/api/search/*`, `/api/ai/*`, `/api/settings/*`, `/api/library/*`

### Spine vs TOC (Critical Distinction)

- **Spine**: Linear sequence of physical HTML files in reading order. What the reader displays chapter-by-chapter. Navigate with Previous/Next.
- **TOC**: Logical navigation tree that maps to spine files via `href`. Multiple TOC entries may point to the same spine file with different anchors. Shown in sidebar.

### Key Data Structures

```python
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
```

### Book Identity System

Each book has two identifiers:
- **book_folder**: Filesystem name (e.g., `dracula_data`) - used for file paths
- **book_uuid**: Stable UUID in `{book_folder}/ai_meta.json` - used for conversation tracking

## Frontend Development

Templates in `src/reader3_app/web/templates/`:
- `library.html` - Modern 3-pane library UI (left: collections, center: book grid, right: search/chat)
- `library_classic.html` - Legacy grid view
- `reader.html` - Reading interface with TOC sidebar and chapter content

Static assets in `src/reader3_app/web/static/`:
- `library.js` / `library.css` - Library UI logic and styles
- `library-search.js` - Cross-book search functionality
- `search.css` - Search panel styles

JavaScript uses vanilla ES6+ (no frameworks). CSS is plain CSS (no preprocessors).

## Constitution Principles (Summary)

Reader3 Pro follows 7 core principles in `.specify/memory/constitution.md`:

1. **Data Structures First**: All entities as `@dataclass` with type annotations
2. **Simplicity Over Engineering**: YAGNI - no abstractions beyond FastAPI/BeautifulSoup
3. **File-Based State Management**: Filesystem IS the database (`*_data/` directories)
4. **HTML Content Sanitization**: XSS prevention via `html.escape()` and `clean_html_content()`
5. **Path Security**: Validate book IDs against enumerated directories, use `os.path.basename()`
6. **Explicit Over Implicit**: Type hints everywhere, clear naming, documented distinctions
7. **Performance Through Caching**: `@lru_cache` for expensive operations

**Key architectural decision**: Maintain simplicity. Resist premature optimization. The codebase should remain "vibes codable" with LLMs.

## Feature Development Workflow

Uses spec-driven development with numbered feature branches:

**Branch naming**: `{number}-{short-name}` (e.g., `001-search-features`, `002-ai-assistant`)

**Specs directory**: `specs/{number}-{short-name}/` contains:
- `spec.md` - User stories, requirements, success criteria
- `plan.md` - Technical design, architecture decisions
- `tasks.md` - Implementation tasks organized by user story
- `data-model.md` - Entity definitions
- `contracts/` - API specifications (OpenAPI YAML)

**Feature status**:
- `001-search-features`: Keyword + semantic search (✅ Completed)
- `002-ai-assistant`: Multi-provider AI with RAG (✅ Completed)
- `003-add-book-notes`: Book annotation system (📋 Spec phase)
- `004-library-bulk-indexing`: 3-pane UI, collections, bulk indexing (✅ Completed)

**Speckit commands**:
- `/speckit.specify` - Create feature specification
- `/speckit.clarify` - Resolve ambiguous requirements
- `/speckit.plan` - Generate technical implementation plan
- `/speckit.tasks` - Generate implementation task breakdown

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
