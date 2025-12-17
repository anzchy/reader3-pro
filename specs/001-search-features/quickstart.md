# Quickstart: Search Functionality Implementation

**Feature**: 001-search-features
**Date**: 2025-12-17
**For**: Developers implementing search in Reader3 Pro

## Overview

This guide provides step-by-step instructions for implementing and using the search functionality in Reader3 Pro. Follow the phases in order for incremental feature delivery.

---

## Prerequisites

- Python 3.10+
- Existing Reader3 Pro installation
- `uv` package manager
- At least one processed EPUB book in the library

---

## Phase 1: Setup Dependencies (5 minutes)

### Step 1.1: Install Required Packages

```bash
cd /path/to/reader3-pro
uv add chromadb sentence-transformers
```

This installs:
- **ChromaDB** (0.4.22+): Vector database for semantic search
- **sentence-transformers** (2.3.0+): Embedding model library

### Step 1.2: Verify Installation

```bash
python -c "import chromadb; import sentence_transformers; print('Dependencies installed successfully')"
```

Expected output: `Dependencies installed successfully`

### Step 1.3: Download Embedding Model (One-Time, ~420 MB)

```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
```

Model downloads to `~/.cache/huggingface/` automatically on first use.

---

## Phase 2: Implement Keyword Search (2-3 hours)

### Step 2.1: Create `search_service.py`

Create a new file at the repository root:

```python
# search_service.py
"""
Keyword search functionality for Reader3 Pro.
Implements FR-001 to FR-012a (in-book keyword search).
"""

import re
import unicodedata
import html
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from enum import Enum
import pickle
import os

# Import existing Book structures
from reader3 import Book, ChapterContent


class SearchMode(Enum):
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class SearchScope(Enum):
    CURRENT_BOOK = "current_book"
    ALL_BOOKS = "all_books"


@dataclass
class SearchQuery:
    """User search request with configuration."""
    term: str
    mode: SearchMode = SearchMode.KEYWORD
    scope: SearchScope = SearchScope.CURRENT_BOOK
    case_sensitive: bool = False
    max_results: int = 1000
    book_id: Optional[str] = None

    def __post_init__(self):
        if self.scope == SearchScope.CURRENT_BOOK and not self.book_id:
            raise ValueError("book_id required for CURRENT_BOOK scope")
        # Empty/whitespace is treated as "clear search" (FR-010).
        self.term = self.term or ""


@dataclass
class SearchResult:
    """A single search match occurrence."""
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


@dataclass
class SearchResultSet:
    """Complete set of results for a search query."""
    query: SearchQuery
    results: List[SearchResult] = field(default_factory=list)
    total_matches: int = 0
    searched_books: int = 0
    failed_books: List[str] = field(default_factory=list)
    is_truncated: bool = False
    execution_time_ms: float = 0.0

    def get_status_message(self) -> str:
        """Generate user-facing status message (FR-022a)."""
        if self.failed_books:
            success_count = self.searched_books - len(self.failed_books)
            status = f"Results from {success_count} of {self.searched_books} books ({len(self.failed_books)} failed)"
        elif self.query.scope == SearchScope.CURRENT_BOOK:
            status = f"Found {self.total_matches} results"
        else:
            status = f"Found {self.total_matches} results across {self.searched_books} books"

        if self.is_truncated:
            status += f" (showing first {len(self.results)})"

        return status


def normalize_for_search(text: str) -> str:
    """
    Normalize Latin diacritics while preserving non-Latin scripts.
    Implements FR-009 (handle multi-language search).
    """
    # Detect if text contains primarily Latin characters
    latin_pattern = re.compile(r'[a-zA-Z]')
    has_latin = bool(latin_pattern.search(text))

    if has_latin:
        # NFD: Decompose characters (café → cafe + ´) without compatibility expansions
        nfd_form = unicodedata.normalize('NFD', text)
        # Strip combining diacritics (U+0300 to U+036F)
        return ''.join([c for c in nfd_form if not unicodedata.combining(c)])
    else:
        # Preserve Chinese, Japanese, Korean, Arabic, Cyrillic exactly
        return text


def extract_context(text: str, match_start: int, match_end: int,
                    words_before: int = 20, words_after: int = 20) -> Tuple[str, str]:
    """
    Extract context around a match (FR-012).
    Returns (context_before, context_after) tuple.
    """
    words = text.split()

    if len(words) > 0:
        # Find word indices
        char_to_word = {}
        char_pos = 0
        for word_idx, word in enumerate(words):
            for _ in range(len(word) + 1):  # +1 for space
                char_to_word[char_pos] = word_idx
                char_pos += 1

        match_word_idx = char_to_word.get(match_start, 0)
        start_word = max(0, match_word_idx - words_before)
        end_word = min(len(words), match_word_idx + words_after + 1)

        context_before = ' '.join(words[start_word:match_word_idx])
        context_after = ' '.join(words[match_word_idx + 1:end_word])
    else:
        # Fallback: Character-based window
        start = max(0, match_start - 40)
        end = min(len(text), match_end + 40)
        context_before = text[start:match_start]
        context_after = text[match_end:end]

    return context_before.strip(), context_after.strip()


def search_text(text: str, query: str, case_sensitive: bool = False,
                max_results: int = 1000) -> List[Tuple[int, int]]:
    """
    Find all occurrences of query in text.
    Returns list of (start, end) tuples (FR-008a: limit to max_results).
    """
    # Normalize query and text
    if not case_sensitive:
        normalized_query = normalize_for_search(query).lower()
        normalized_text = normalize_for_search(text).lower()
    else:
        normalized_query = query
        normalized_text = text

    # Escape special regex characters for literal matching
    pattern = re.escape(normalized_query)

    matches = []
    for match in re.finditer(pattern, normalized_text):
        if len(matches) >= max_results:
            break
        matches.append((match.start(), match.end()))

    return matches


def search_book(book_id: str, query: SearchQuery, data_dir: str = ".") -> SearchResultSet:
    """
    Search within a single book.
    Implements FR-001 to FR-012a.
    """
    import time
    start_time = time.time()

    trimmed = query.term.strip()
    if not trimmed:
        return SearchResultSet(
            query=query,
            results=[],
            total_matches=0,
            searched_books=1,
            is_truncated=False,
            execution_time_ms=0.0
        )

    # Load book.pkl (book_id matches the folder name, e.g. dracula_data/)
    pkl_path = os.path.join(data_dir, book_id, "book.pkl")
    if not os.path.exists(pkl_path):
        raise FileNotFoundError(f"Book {book_id} not found")

    with open(pkl_path, 'rb') as f:
        book = pickle.load(f)

    # Search all chapters
    results = []
    total_matches = 0

    for chapter in book.spine:
        matches = search_text(chapter.text, trimmed, query.case_sensitive, query.max_results)
        total_matches += len(matches)

        for occurrence_index, (start, end) in enumerate(matches):
            if len(results) >= query.max_results:
                break

            match_text = chapter.text[start:end]
            context_before, context_after = extract_context(chapter.text, start, end)

            # Simple relevance score: earlier occurrences are slightly higher.
            relevance = 1.0 / (start + 1)

            results.append(SearchResult(
                book_id=book_id,
                book_title=book.metadata.title,
                chapter_id=chapter.id,
                chapter_title=chapter.title,
                chapter_order=chapter.order,
                occurrence_index=occurrence_index,
                match_text=match_text,
                context_before=context_before,
                context_after=context_after,
                position=start,
                relevance_score=relevance
            ))

        if len(results) >= query.max_results:
            break

    execution_time = (time.time() - start_time) * 1000  # Convert to ms

    return SearchResultSet(
        query=query,
        results=results,
        total_matches=total_matches,
        searched_books=1,
        is_truncated=(total_matches > len(results)),
        execution_time_ms=execution_time
    )


def escape_for_highlighting(term: str) -> str:
    """
    Escape HTML entities to prevent XSS (FR-012a).
    """
    return html.escape(term, quote=True)
```

### Step 2.2: Add Search Endpoint to `server.py`

Add these routes to your FastAPI application:

```python
# In server.py, add these imports at the top
from search_service import search_book, SearchQuery, SearchMode, SearchScope, escape_for_highlighting

# Add this route
@app.get("/api/search/{book_id}")
async def api_search_book(
    book_id: str,
    q: str = "",
    mode: str = "keyword",
    case_sensitive: bool = False,
    max_results: int = 100
):
    """
    Search within a single book.
    GET /api/search/dracula_data?q=vampire&mode=keyword
    """
    try:
        query = SearchQuery(
            term=q,
            mode=SearchMode(mode),
            scope=SearchScope.CURRENT_BOOK,
            case_sensitive=case_sensitive,
            max_results=min(max_results, 1000),  # Cap at 1000
            book_id=book_id
        )

        result_set = search_book(book_id, query)

        return {
            "query": {
                "term": query.term,
                "mode": query.mode.value,
                "scope": query.scope.value,
                "case_sensitive": query.case_sensitive,
                "max_results": query.max_results,
                "book_id": query.book_id
            },
            "results": [
                {
                    "book_id": r.book_id,
                    "book_title": r.book_title,
                    "chapter_id": r.chapter_id,
                    "chapter_title": r.chapter_title,
                    "chapter_order": r.chapter_order,
                    "occurrence_index": r.occurrence_index,
                    "match_text": r.match_text,
                    "context_before": r.context_before,
                    "context_after": r.context_after,
                    "position": r.position,
                    "relevance_score": r.relevance_score
                }
                for r in result_set.results
            ],
            "total_matches": result_set.total_matches,
            "searched_books": result_set.searched_books,
            "failed_books": result_set.failed_books,
            "is_truncated": result_set.is_truncated,
            "execution_time_ms": result_set.execution_time_ms,
            "status_message": result_set.get_status_message()
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

### Step 2.3: Test Keyword Search

```bash
# Start server
uv run server.py

# In another terminal, test the API
curl "http://127.0.0.1:8123/api/search/dracula_data?q=vampire&max_results=10"
```

Expected: JSON response with search results.

---

## Phase 3: Add Search UI (2-3 hours)

### Step 3.1: Update `reader.html` Template

Add search box to the sidebar:

```html
<!-- In templates/reader.html, add this to the sidebar -->
<div class="search-box">
    <input
        type="text"
        id="search-input"
        placeholder="Search in this book..."
        autocomplete="off"
    />
    <button id="search-btn">Search</button>
    <button id="clear-search-btn" style="display:none;">Clear</button>
</div>

<div id="search-results" style="display:none;">
    <div id="search-status"></div>
    <div id="results-list"></div>
</div>
```

### Step 3.2: Create `static/search.js`

```javascript
// static/search.js
class SearchUI {
    constructor(bookId) {
        this.bookId = bookId;
        this.searchInput = document.getElementById('search-input');
        this.searchBtn = document.getElementById('search-btn');
        this.clearBtn = document.getElementById('clear-search-btn');
        this.resultsDiv = document.getElementById('search-results');
        this.statusDiv = document.getElementById('search-status');
        this.resultsList = document.getElementById('results-list');

        this.debounceTimer = null;
        this.currentResults = [];

        this.init();
    }

    init() {
        // Search button click
        this.searchBtn.addEventListener('click', () => this.performSearch());

        // Enter key in search box
        this.searchInput.addEventListener('keyup', (e) => {
            if (e.key === 'Enter') {
                this.performSearch();
            } else {
                // Debounce: wait 300ms after typing stops (FR-032)
                clearTimeout(this.debounceTimer);
                this.debounceTimer = setTimeout(() => {
                    this.performSearch();
                }, 300);
            }
        });

        // Clear button
        this.clearBtn.addEventListener('click', () => this.clearSearch());
    }

    async performSearch() {
        const query = this.searchInput.value.trim();
        if (!query) {
            this.clearSearch();
            return;
        }

        this.statusDiv.textContent = 'Searching...';
        this.resultsDiv.style.display = 'block';
        this.clearBtn.style.display = 'inline';

        try {
            const response = await fetch(
                `/api/search/${this.bookId}?q=${encodeURIComponent(query)}&max_results=100`
            );
            const data = await response.json();

            this.currentResults = data.results;
            this.displayResults(data);

        } catch (error) {
            this.statusDiv.textContent = 'Search failed: ' + error.message;
        }
    }

    displayResults(data) {
        this.statusDiv.textContent = data.status_message;
        this.resultsList.innerHTML = '';

        if (data.results.length === 0) {
            this.resultsList.textContent = `No results found for "${data.query.term}"`;
            return;
        }

        data.results.forEach((result, index) => {
            const resultItem = document.createElement('div');
            resultItem.className = 'search-result-item';
            resultItem.innerHTML = `
                <div class="result-chapter">${result.chapter_title}</div>
                <div class="result-snippet">
                    ${result.context_before}
                    <mark class="search-match">${result.match_text}</mark>
                    ${result.context_after}
                </div>
            `;

            // Click to navigate
            resultItem.addEventListener('click', () => {
                window.location.href = `/read/${this.bookId}/${result.chapter_order}?q=${encodeURIComponent(data.query.term)}&occurrence=${result.occurrence_index}`;
            });

            this.resultsList.appendChild(resultItem);
        });
    }

    clearSearch() {
        this.searchInput.value = '';
        this.resultsDiv.style.display = 'none';
        this.clearBtn.style.display = 'none';
        this.currentResults = [];
        // Remove highlighting from chapter content
        document.querySelectorAll('mark.search-match').forEach(el => {
            el.outerHTML = el.innerHTML;
        });
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const bookId = window.location.pathname.split('/')[2];  // Extract from /read/{book_id}/...
    new SearchUI(bookId);
});
```

### Step 3.3: Add CSS Styling

```css
/* Add to your existing CSS or create static/search.css */
.search-box {
    padding: 10px;
    border-bottom: 1px solid #ddd;
}

.search-box input {
    width: 70%;
    padding: 5px;
    font-size: 14px;
}

.search-box button {
    padding: 5px 10px;
    font-size: 14px;
    cursor: pointer;
}

#search-results {
    max-height: 400px;
    overflow-y: auto;
    padding: 10px;
}

.search-result-item {
    padding: 10px;
    margin-bottom: 10px;
    border: 1px solid #eee;
    border-radius: 4px;
    cursor: pointer;
}

.search-result-item:hover {
    background-color: #f5f5f5;
}

.result-chapter {
    font-weight: bold;
    margin-bottom: 5px;
    color: #333;
}

.result-snippet {
    font-size: 13px;
    color: #666;
}

mark.search-match {
    background-color: yellow;
    font-weight: bold;
}
```

### Step 3.4: Link JavaScript in Template

```html
<!-- In templates/reader.html, add before closing </body> -->
<script src="/static/search.js"></script>
```

### Step 3.5: Test Search UI

1. Start server: `uv run server.py`
2. Open a book: `http://127.0.0.1:8123/read/dracula_data/0`
3. Type a search term in the sidebar
4. Click results to jump to chapters

---

## Phase 4: Implement Semantic Search (3-4 hours)

### Step 4.1: Create `vector_search.py`

```python
# vector_search.py
"""
Semantic search using ChromaDB and sentence-transformers.
Implements FR-023 to FR-029 (semantic search requirements).
"""

import chromadb
from chromadb.utils import embedding_functions
from typing import List, Dict, Optional
import pickle
import os
from dataclasses import dataclass, field


@dataclass
class SemanticSearchResult:
    """Semantic search result with similarity score."""
    chunk_id: str
    chapter_id: str
    chapter_title: str
    chapter_order: int
    text: str
    similarity_score: float  # 0-1, higher = more similar
    metadata: Dict = field(default_factory=dict)


class BookVectorIndex:
    """Manages vector embeddings for a single book."""

    def __init__(self, book_id: str, book_data_dir: str):
        self.book_id = book_id
        self.book_data_dir = book_data_dir
        self.chroma_path = os.path.join(book_data_dir, "chroma_db")

        # Use multilingual model for English + Chinese (FR-009)
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"
        )

        self.client = chromadb.PersistentClient(path=self.chroma_path)
        self.collection = self.client.get_or_create_collection(
            name="chapters",
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"}
        )

    def is_indexed(self) -> bool:
        """Check if this book has been indexed."""
        return os.path.exists(self.chroma_path) and self.collection.count() > 0

    def index_book(self, force_reindex: bool = False):
        """
        Generate embeddings for all chapters (FR-024).
        If force_reindex=True, regenerates even if already indexed (FR-028).
        """
        if self.is_indexed() and not force_reindex:
            print(f"Book {self.book_id} already indexed, skipping...")
            return

        # Load book.pkl
        pkl_path = os.path.join(self.book_data_dir, "book.pkl")
        with open(pkl_path, 'rb') as f:
            book = pickle.load(f)

        # Prepare documents for batch indexing
        documents = []
        metadatas = []
        ids = []

        for chapter in book.spine:
            # Chunk large chapters for better retrieval
            text_chunks = self._chunk_text(chapter.text, max_length=1000)

            for i, chunk in enumerate(text_chunks):
                doc_id = f"{chapter.id}_chunk_{i}"
                ids.append(doc_id)
                documents.append(chunk)
                metadatas.append({
                    "chapter_id": chapter.id,
                    "chapter_title": chapter.title,
                    "chapter_order": chapter.order,
                    "book_title": book.metadata.title,
                    "chunk_index": i
                })

        # Batch upsert (idempotent)
        self.collection.upsert(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )

        print(f"Indexed {len(documents)} chunks from {len(book.spine)} chapters")

    def semantic_search(self, query: str, n_results: int = 10) -> List[SemanticSearchResult]:
        """
        Perform semantic search (FR-025).
        Returns results ranked by similarity.
        """
        if not self.is_indexed():
            raise ValueError(f"Book {self.book_id} not indexed. Run indexing first.")

        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            include=['documents', 'metadatas', 'distances']
        )

        return self._format_results(results)

    def _chunk_text(self, text: str, max_length: int = 1000) -> List[str]:
        """Split text into chunks for better retrieval granularity."""
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0

        for word in words:
            current_chunk.append(word)
            current_length += len(word) + 1

            if current_length >= max_length:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_length = 0

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks or [text]

    def _format_results(self, results) -> List[SemanticSearchResult]:
        """Convert ChromaDB results to SemanticSearchResult objects."""
        formatted = []
        for i in range(len(results['ids'][0])):
            # Convert cosine distance to similarity (1 - distance)
            distance = results['distances'][0][i]
            similarity = max(0, 1 - distance)  # Clamp to [0, 1]

            formatted.append(SemanticSearchResult(
                chunk_id=results['ids'][0][i],
                chapter_id=results['metadatas'][0][i]['chapter_id'],
                chapter_title=results['metadatas'][0][i]['chapter_title'],
                chapter_order=results['metadatas'][0][i]['chapter_order'],
                text=results['documents'][0][i],
                similarity_score=similarity,
                metadata=results['metadatas'][0][i]
            ))
        return formatted
```

### Step 4.2: Add Indexing CLI Command

Update `reader3.py` to add indexing capability:

```python
# In reader3.py, add at the end of the file

def index_book_for_search(epub_path: str, book_id: str):
    """Index a book for semantic search after processing."""
    from vector_search import BookVectorIndex

    # book_id matches the processed folder name, e.g. dracula_data/
    book_data_dir = book_id
    if not os.path.exists(os.path.join(book_data_dir, "book.pkl")):
        print(f"Error: {book_id} not processed yet. Run 'uv run reader3.py {epub_path}' first.")
        return

    print(f"Indexing {book_id} for semantic search...")
    index = BookVectorIndex(book_id, book_data_dir)
    index.index_book()
    print(f"✓ Indexing complete")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: uv run reader3.py <file.epub>")
        print("       uv run reader3.py --index <book_id>")
        sys.exit(1)

    if sys.argv[1] == "--index":
        if len(sys.argv) < 3:
            print("Usage: uv run reader3.py --index <book_id>")
            sys.exit(1)
        book_id = sys.argv[2]
        index_book_for_search(None, book_id)
    else:
        epub_path = sys.argv[1]
        process_epub(epub_path)
```

### Step 4.3: Test Semantic Search

```bash
# Index a book
uv run reader3.py --index dracula_data

# Test via API (add endpoint to server.py first)
curl "http://127.0.0.1:8123/api/search/dracula_data?q=immortality&mode=semantic"
```

---

## Quick Reference

### Common Commands

```bash
# Process an EPUB
uv run reader3.py book.epub

# Index a book for semantic search
uv run reader3.py --index book_id

# Start the server
uv run server.py

# Run tests (once implemented)
pytest tests/
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/search/{book_id}` | GET | Search within a single book |
| `/api/search/library` | GET | Search across all books |
| `/api/index/{book_id}` | POST | Index a book for semantic search |
| `/api/index/{book_id}/status` | GET | Check indexing status |

### Search Modes

- **keyword**: Exact text matching with diacritic normalization
- **semantic**: Embedding-based similarity search
- **hybrid**: Combined keyword + semantic results

---

## Troubleshooting

### Issue: ChromaDB fails to install

**Solution**: Ensure Python 3.10+ and try:
```bash
uv add chromadb --no-cache
```

### Issue: Embedding model download fails

**Solution**: Manual download:
```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2', cache_folder='./models')"
```

### Issue: Search returns no results

**Checklist**:
1. Verify book.pkl exists: `ls {book_id}/book.pkl`
2. Check chapter.text is populated: `python -c "import pickle; print(pickle.load(open('{book_id}/book.pkl', 'rb')).spine[0].text[:100])"`
3. Test API directly: `curl "http://127.0.0.1:8123/api/search/{book_id}?q=test"`

### Issue: Semantic search is slow

**Solutions**:
1. Reduce chunk size in `_chunk_text()` (fewer, larger chunks)
2. Limit `n_results` parameter
3. Use CPU with multiple cores: `os.environ['OMP_NUM_THREADS'] = '4'`

---

## Performance Targets

| Operation | Target | Typical |
|-----------|--------|---------|
| Keyword search (single book) | <500ms | 50-200ms |
| Keyword search (50 books) | <2s | 500ms-1s |
| Semantic search (single book) | <1s | 300-600ms |
| Indexing (single book) | N/A | 10-15s |

---

## Next Steps

1. **Phase 5**: Implement library-wide search (`/api/search/library`)
2. **Phase 6**: Add hybrid search (combine keyword + semantic)
3. **Phase 7**: Implement search result highlighting in chapter content
4. **Phase 8**: Add search history and saved queries

---

## Additional Resources

- **API Contract**: `specs/001-search-features/contracts/search-api.yaml`
- **Data Model**: `specs/001-search-features/data-model.md`
- **Research**: `specs/001-search-features/research.md`
- **ChromaDB Docs**: https://docs.trychroma.com/
- **Sentence Transformers**: https://huggingface.co/sentence-transformers

---

**Status**: ✅ Quickstart guide complete. Ready for implementation.
