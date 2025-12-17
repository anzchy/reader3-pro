# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Reader3 Pro is a lightweight, self-hosted EPUB reader designed for reading books with LLMs. The application processes EPUB files into a structured format and serves them via a web interface, making it easy to copy chapter content and paste it into LLM conversations.

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

## Architecture

### Two-Step Architecture

**Step 1: EPUB Processing (`reader3.py`)**
- Parses EPUB files using `ebooklib`
- Extracts and cleans HTML content with BeautifulSoup
- Builds two structures:
  - **Spine** (linear reading order): Physical HTML files from the EPUB
  - **TOC** (logical navigation): Hierarchical table of contents
- Extracts images and rewrites paths
- Serializes everything into `book.pkl` using pickle

**Step 2: Web Server (`server.py`)**
- FastAPI application serving the reader interface
- Loads `book.pkl` files from `*_data/` directories
- Uses Jinja2 templates for rendering
- Caches loaded books with `lru_cache` (maxsize=10)

### Key Data Structures

All defined in `reader3.py`:

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

## Security Considerations

- **Pickle deserialization**: Currently loads pickle files without validation. Only process trusted EPUB files.
- **Path traversal**: Image serving uses `os.path.basename()` for sanitization but should be reviewed for production use.
- **Input validation**: EPUB file uploads should validate file type (magic bytes) and size limits.
- **HTML sanitization**: `clean_html_content()` removes script/style/iframe tags, but review for XSS if allowing user-uploaded EPUBs.

## Performance Notes

- `lru_cache(maxsize=10)` on book loading - increase if serving many concurrent users
- Pickle files can be large (multi-MB for image-heavy books)
- No pagination on library view - may need limiting for large libraries
- Consider database migration for >100 books or multi-user scenarios

## Enhancement Plans

See `reader3-enhancement-workflow.md` for comprehensive roadmap including:
- Database migration (SQLite/PostgreSQL)
- React frontend rebuild
- User authentication
- Annotation system

See `search-features-workflow.md` for planned search features:
- RAG-based cross-book semantic search
- In-book keyword search sidebar with highlighting
