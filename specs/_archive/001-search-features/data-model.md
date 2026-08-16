# Data Model: Search Functionality

**Feature**: 001-search-features
**Date**: 2025-12-17
**Status**: Design Phase — **部分条目已 SUPERSEDED，见下方说明**

> ## ⚠️ SUPERSEDED —— `SearchIndex` 与 `BookIndex.from_book_pkl()`（2026-08-16）
>
> 本文档描述的以下三项**已不存在于代码中**，2026-08-16 作为死代码删除，**不要照本文实现**：
>
> | 本文条目 | 状态 |
> |---|---|
> | `SearchIndex` dataclass（§4 及后续各处） | ❌ 已删除 |
> | `BookIndex.from_book_pkl()` classmethod | ❌ 已删除 |
> | `SearchIndex.build_from_library()` classmethod | ❌ 已删除 |
> | `BookIndex` dataclass 本身 | ✅ **保留，活代码** |
> | `ChapterIndex` dataclass | ✅ **保留，活代码** |
>
> **当前真相源**：per-book 惰性加载 `load_book_index()`（`search_service.py`），带 `lru_cache`。没有全库级的索引容器；跨库搜索由 `search_library()` 逐本调用 `load_book_index()` 完成。
>
> 删除理由与边界见 `docs/plans/20260816-plan-ui-migration-sequencing.md` 的 R4 落地记录。

## Overview

This document defines all data structures for search functionality in Reader3 Pro, following the constitution principle "Data Structures First." All entities are implemented as Python `@dataclass` with explicit type annotations to ensure type safety and self-documentation.

---

## Core Search Entities

### 1. SearchQuery

**Purpose**: Represents user search parameters and configuration

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class SearchMode(Enum):
    """Search operation modes."""
    KEYWORD = "keyword"           # Exact text matching with diacritic normalization
    SEMANTIC = "semantic"         # Embedding-based similarity search
    HYBRID = "hybrid"             # Combined keyword + semantic results

class SearchScope(Enum):
    """Search target scope."""
    CURRENT_BOOK = "current_book"  # Search within single open book
    ALL_BOOKS = "all_books"        # Search across entire library

@dataclass
class SearchQuery:
    """
    User search request with configuration.

    Attributes:
        term: Search query string (user input)
        mode: Search algorithm to use (keyword/semantic/hybrid)
        scope: Search within current book or all books
        case_sensitive: Whether to match case exactly (default: False)
        max_results: Maximum results to return (default: 1000, per FR-008a)
        book_id: Target book ID (required if scope=CURRENT_BOOK)
    """
    term: str
    mode: SearchMode = SearchMode.KEYWORD
    scope: SearchScope = SearchScope.CURRENT_BOOK
    case_sensitive: bool = False
    max_results: int = 1000
    book_id: Optional[str] = None

    def __post_init__(self):
        """Validate query constraints."""
        if self.scope == SearchScope.CURRENT_BOOK and not self.book_id:
            raise ValueError("book_id required for CURRENT_BOOK scope")
        if self.max_results < 1 or self.max_results > 1000:
            raise ValueError("max_results must be between 1 and 1000")
        # Empty/whitespace term is treated as "clear search" (FR-010).
        # The UI should clear results/highlights and avoid issuing a search request,
        # but the server-side model allows it for robustness.
        self.term = self.term or ""
```

---

### 2. SearchResult

**Purpose**: Represents a single search match with context

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class SearchResult:
    """
    A single search match occurrence.

    Attributes:
        book_id: Identifier of the book containing this match
        book_title: Human-readable book title (for display)
        chapter_id: EPUB internal chapter identifier
        chapter_title: Human-readable chapter title
        chapter_order: Sequential position in book spine (0-indexed)
        occurrence_index: 0-indexed occurrence within the chapter for this query
        match_text: The actual matching text snippet
        context_before: Text before the match (20 words or 40 chars, per FR-012)
        context_after: Text after the match (20 words or 40 chars)
        position: Character offset of match start in chapter.text
        relevance_score: Numeric score for ranking (higher = more relevant)
        highlight_start: Start offset for highlighting (relative to context)
        highlight_end: End offset for highlighting (relative to context)
    """
    book_id: str
    book_title: str
    chapter_id: str
    chapter_title: str
    chapter_order: int
    occurrence_index: int
    match_text: str
    context_before: str
    context_after: str
    position: int
    relevance_score: float
    highlight_start: Optional[int] = None
    highlight_end: Optional[int] = None

    def get_full_context(self) -> str:
        """Return combined context string with match."""
        return f"{self.context_before}{self.match_text}{self.context_after}"

    def get_display_snippet(self, max_length: int = 150) -> str:
        """
        Generate truncated snippet for UI display.
        Ensures snippet doesn't exceed max_length (FR-035).
        """
        full = self.get_full_context()
        if len(full) <= max_length:
            return full

        # Truncate with ellipsis
        half = max_length // 2
        return f"{full[:half]}...{full[-half:]}"
```

---

### 3. SearchResultSet

**Purpose**: Collection of search results with metadata

```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class SearchResultSet:
    """
    Complete set of results for a search query.

    Attributes:
        query: The original search query
        results: List of SearchResult objects
        total_matches: Total number of matches found (may exceed len(results) if truncated)
        searched_books: Number of books searched
        failed_books: List of book_ids that failed to search (per FR-022a)
        is_truncated: Whether results were limited due to max_results cap
        execution_time_ms: Search operation duration in milliseconds
        grouped_by_book: Results organized by book_id for library search display
    """
    query: SearchQuery
    results: List[SearchResult] = field(default_factory=list)
    total_matches: int = 0
    searched_books: int = 0
    failed_books: List[str] = field(default_factory=list)
    is_truncated: bool = False
    execution_time_ms: float = 0.0
    grouped_by_book: Dict[str, List[SearchResult]] = field(default_factory=dict)

    def get_status_message(self) -> str:
        """
        Generate user-facing status message (FR-022a).
        Examples:
        - "Found 23 results in this book"
        - "Found 156 results across 8 books"
        - "Results from 8 of 10 books (2 failed)"
        - "Showing first 1000 of 2,347 results"
        """
        if self.failed_books:
            success_count = self.searched_books - len(self.failed_books)
            status = f"Results from {success_count} of {self.searched_books} books ({len(self.failed_books)} failed)"
        elif self.query.scope == SearchScope.CURRENT_BOOK:
            status = f"Found {self.total_matches} results"
        else:
            status = f"Found {self.total_matches} results across {self.searched_books} books"

        if self.is_truncated:
            status += f" (showing first {len(self.results)} of {self.total_matches})"

        return status

    def group_by_book(self):
        """Organize results by book_id for library search display."""
        self.grouped_by_book = {}
        for result in self.results:
            if result.book_id not in self.grouped_by_book:
                self.grouped_by_book[result.book_id] = []
            self.grouped_by_book[result.book_id].append(result)
```

---

### 4. SearchIndex

> ⚠️ **SUPERSEDED 2026-08-16 —— 本节整节作废，不要实现。** `SearchIndex` 与 `build_from_library()` 已作为死代码从 `search_service.py` 删除。当前用 per-book 惰性加载 `load_book_index()`。见文首说明。

**Purpose**: In-memory index for keyword search

```python
from dataclasses import dataclass, field
from typing import Dict, List
import pickle
import os

@dataclass
class ChapterIndex:
    """Index for a single chapter."""
    chapter_id: str
    chapter_title: str
    chapter_order: int
    normalized_text: str  # Diacritic-normalized for fast matching
    original_text: str    # Preserve original for context extraction

@dataclass
class BookIndex:
    """Index for a single book."""
    book_id: str
    book_title: str
    author: str
    chapters: List[ChapterIndex] = field(default_factory=list)

    @classmethod
    def from_book_pkl(cls, book_id: str, pkl_path: str) -> "BookIndex":
        """
        Build index from existing book.pkl file.

        Loads the Book object and extracts searchable text from spine.
        """
        with open(pkl_path, 'rb') as f:
            book = pickle.load(f)

        chapters = []
        for chapter in book.spine:
            normalized = normalize_for_search(chapter.text)  # Import from search_service
            chapters.append(ChapterIndex(
                chapter_id=chapter.id,
                chapter_title=chapter.title,
                chapter_order=chapter.order,
                normalized_text=normalized,
                original_text=chapter.text
            ))

        return cls(
            book_id=book_id,
            book_title=book.metadata.title,
            author=", ".join(book.metadata.authors),
            chapters=chapters
        )

@dataclass
class SearchIndex:
    """
    In-memory search index for all books in library.

    Built once on server start or first search request (lazy loading).
    Cached for subsequent queries for performance (FR-030: <2s target).
    """
    books: Dict[str, BookIndex] = field(default_factory=dict)
    last_updated: Optional[str] = None  # ISO timestamp of last index build

    @classmethod
    def build_from_library(cls, data_dir: str = ".") -> "SearchIndex":
        """
        Scan *_data/ directories and build index for all books.

        Called on server startup or first search request.
        Handles partial failures gracefully (logs errors, continues indexing).
        """
        index = {}
        failed = []

        for entry in os.listdir(data_dir):
            if entry.endswith("_data"):
                book_id = entry  # Book ID is the folder name (matches existing routes)
                pkl_path = os.path.join(data_dir, entry, "book.pkl")

                try:
                    if os.path.exists(pkl_path):
                        index[book_id] = BookIndex.from_book_pkl(book_id, pkl_path)
                except Exception as e:
                    logger.warning(f"Failed to index book {book_id}: {e}")
                    failed.append(book_id)

        import datetime
        return cls(
            books=index,
            last_updated=datetime.datetime.utcnow().isoformat()
        )

    def search_keyword(self, query: SearchQuery) -> SearchResultSet:
        """
        Perform keyword search across indexed books.

        Delegates to search_service.search_text() for actual matching.
        """
        # Implementation delegated to search_service.py
        pass
```

---

### 5. VectorIndex (ChromaDB Integration)

**Purpose**: Semantic search index management

```python
from dataclasses import dataclass
from typing import List, Dict, Optional
import os

@dataclass
class EmbeddingChunk:
    """
    A chunk of text with its embedding vector.

    Large chapters are split into chunks for better retrieval granularity.
    """
    chunk_id: str              # Unique identifier: {chapter_id}_chunk_{index}
    chapter_id: str            # Parent chapter identifier
    chapter_title: str         # For display in results
    chapter_order: int         # Sequential position in book
    text: str                  # Original text content of this chunk
    chunk_index: int           # Position within chapter (0-indexed)
    embedding: Optional[List[float]] = None  # 384-dim vector (generated by ChromaDB)

@dataclass
class VectorIndex:
    """
    Wrapper for ChromaDB collection for a single book.

    Attributes:
        book_id: Identifier for this book
        book_data_dir: Path to {bookname}_data/ directory
        chroma_path: Path to chroma_db/ subdirectory
        is_indexed: Whether embeddings have been generated
        chunk_count: Number of text chunks indexed
        model_name: Embedding model used (for version tracking)
    """
    book_id: str
    book_data_dir: str
    chroma_path: str
    is_indexed: bool = False
    chunk_count: int = 0
    model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"

    def __post_init__(self):
        """Initialize ChromaDB client (lazy)."""
        self.chroma_path = os.path.join(self.book_data_dir, "chroma_db")
        self.is_indexed = os.path.exists(self.chroma_path)

    def get_indexing_status(self) -> str:
        """
        Return human-readable indexing status (FR-027).
        Examples:
        - "Indexed (324 chunks)"
        - "Not indexed"
        - "Indexing in progress..."
        """
        if self.is_indexed:
            return f"Indexed ({self.chunk_count} chunks)"
        else:
            return "Not indexed"
```

---

### 6. HighlightRange

**Purpose**: Represents text ranges to be visually highlighted in reader

```python
from dataclasses import dataclass
from enum import Enum

class HighlightStyle(Enum):
    """Visual styling for different highlight types."""
    SEARCH_MATCH = "search-match"        # Primary search term matches
    CONTEXT = "search-context"           # Surrounding context
    CURRENT_RESULT = "search-current"    # Currently selected result

@dataclass
class HighlightRange:
    """
    A range of text to be highlighted in the reader interface.

    Used to apply <mark> tags or CSS styling to search matches.
    Positions are character offsets within chapter.text (plain text).
    The UI is responsible for mapping these matches to the rendered content safely.

    Attributes:
        start: Start character offset (inclusive)
        end: End character offset (exclusive)
        style: Visual styling to apply
        result_index: Index of corresponding SearchResult (for navigation)
    """
    start: int
    end: int
    style: HighlightStyle = HighlightStyle.SEARCH_MATCH
    result_index: Optional[int] = None

    def to_html_mark(self, text: str) -> str:
        """
        Apply <mark> tag to this range in the given text.
        XSS-safe: text is already sanitized chapter content.
        """
        before = text[:self.start]
        match = text[self.start:self.end]
        after = text[self.end:]

        css_class = self.style.value
        return f"{before}<mark class='{css_class}'>{match}</mark>{after}"
```

---

## Relationships

```
SearchQuery
    ↓ (input to search operation)
SearchResultSet
    ├── query: SearchQuery (reference)
    ├── results: List[SearchResult]
    │   └── Each SearchResult contains match location + context
    ├── grouped_by_book: Dict[book_id, List[SearchResult]]
    └── failed_books: List[book_id]

SearchIndex (keyword search)
    ├── books: Dict[book_id, BookIndex]
    │   └── BookIndex
    │       └── chapters: List[ChapterIndex]
    └── Builds from: book.pkl files

VectorIndex (semantic search)
    ├── Per-book ChromaDB collection
    ├── Builds from: book.pkl → EmbeddingChunk objects
    └── Stored in: {bookname}_data/chroma_db/

HighlightRange
    ├── Applied to: chapter.content (HTML)
    ├── Derived from: SearchResult.position
    └── Used by: reader.html JavaScript for UI highlighting
```

---

## Validation Rules

### SearchQuery
- `term`: Empty/whitespace indicates "clear search" (FR-010); non-empty executes a search
- `max_results`: Between 1 and 1,000 (FR-008a)
- `book_id`: Required if `scope=CURRENT_BOOK`, must match existing book

### SearchResult
- `chapter_order`: Must be >= 0, < len(book.spine)
- `position`: Must be >= 0, < len(chapter.text)
- `relevance_score`: Between 0.0 and 1.0 (normalized)
- `context_before/after`: Max 200 characters each (UI truncation)

### SearchIndex
- `books`: Keys must match `*_data/` directory names
- `last_updated`: ISO 8601 timestamp format

### VectorIndex
- `chroma_path`: Must be subdirectory of `book_data_dir`
- `chunk_count`: Must match number of chunks in ChromaDB collection
- `model_name`: Must match sentence-transformers model ID

---

## State Transitions

### VectorIndex Lifecycle

```
[Not Created]
    ↓ (first semantic search request)
[Indexing] (is_indexed=False, chroma_path doesn't exist)
    ↓ (generate embeddings, save to ChromaDB)
[Indexed] (is_indexed=True, chroma_path exists)
    ↓ (book.pkl modified/updated)
[Stale] (needs re-indexing)
    ↓ (user runs `uv run reader3.py --reindex {book_id}`)
[Indexing] (regenerate embeddings)
    ↓
[Indexed]
```

### SearchResultSet Lifecycle

```
[Query Created]
    ↓ (execute search)
[Results Found] (results populated)
    ↓ (user clicks result)
[Navigating] (jump to chapter + highlight)
    ↓ (user clears search)
[Cleared] (highlights removed, results discarded)
```

---

## Serialization

### Persistence Strategy

**SearchQuery**: Not persisted (session-only, per FR-036)
- Stored in session-scoped client state for navigation context
- Cleared on page reload or search box clear

**SearchResultSet**: Not persisted (transient)
- Regenerated on each search request
- Cached in memory on server for current session only

**SearchIndex**: In-memory only (rebuilt on server restart)
- Built from `book.pkl` files on demand
- Invalidated when books added/removed

**VectorIndex**: Persisted by ChromaDB
- Stored in `{bookname}_data/chroma_db/` directory
- SQLite database + HNSW index files
- Survives server restarts (persistent embeddings)

---

## File References

- **Existing Book dataclass**: `/Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/reader3.py:56-67`
- **Existing ChapterContent**: `/Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/reader3.py:20-30`
- **Constitution Data Structures Principle**: `/Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/.specify/memory/constitution.md:29-46`

---

## Implementation Notes

### Type Safety
- All dataclasses use explicit type annotations (`str`, `int`, `List[SearchResult]`, etc.)
- `Optional[T]` for nullable fields
- Enums for constrained value sets (`SearchMode`, `SearchScope`, `HighlightStyle`)

### Performance Considerations
- `SearchIndex.books` uses `Dict` for O(1) book lookup by ID
- `SearchResultSet.grouped_by_book` pre-computed for fast UI rendering
- `ChapterIndex.normalized_text` cached to avoid repeated normalization

### XSS Prevention
- `SearchResult.match_text` is plain text only (no HTML)
- `HighlightRange.to_html_mark()` applies to sanitized chapter.content
- Search terms escaped via `html.escape()` before any HTML rendering

---

## Next Steps

1. Implement these dataclasses in `search_service.py` and `vector_search.py`
2. Add type checking with `mypy` to validate annotations
3. Write unit tests for each dataclass's methods and validation rules
4. Generate API contracts (OpenAPI spec) using these data structures

---

**Status**: ✅ Data model complete and ready for implementation.
