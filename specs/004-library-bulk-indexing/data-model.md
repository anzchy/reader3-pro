# Data Model: Library UI Reorganization + Bulk Indexing (004)

**Feature**: 004-library-bulk-indexing
**Date**: 2025-12-19
**Status**: Draft

## Overview

This document defines all data entities for the redesigned library UI, including Collections, aggregated stats, and extended book metadata for grid/list views.

It also documents client-only UI state keys that are intentionally not persisted server-side.

---

## Entities

### 1. Collection

**Purpose**: User-defined grouping of books by author, theme, or arbitrary criteria.

**Storage**: `config/library_collections.json` (gitignored)

**Schema**:
```python
@dataclass
class Collection:
    """
    Represents a user-created collection of books.

    Collections are persisted server-side in config/library_collections.json
    and provide a way to group books beyond filesystem directories.
    """
    id: str                    # UUID (e.g., "550e8400-e29b-41d4-a716-446655440000")
    name: str                  # User-visible name (e.g., "Science Fiction")
    created_at: str            # ISO 8601 UTC timestamp
    book_ids: List[str]        # List of book folder IDs (e.g., ["dracula_data", "foundation_data"])

    # Future fields (not in v1):
    # description: Optional[str]  # User notes about the collection
    # color: Optional[str]        # UI accent color
    # sort_order: int             # Manual ordering in sidebar
```

**Validation Rules**:
- `id`: Must be valid UUID v4
- `name`: Required, 1-60 chars after trimming; allowed chars: letters, numbers, space, `_`, `-`, `.`, `&`, `()`;
  uniqueness is case-insensitive (e.g., “SciFi” == “scifi”)
- `book_ids`: May be empty (new collection); items must match existing `*_data` folders at write time
- `created_at`: ISO 8601 timestamp in UTC with timezone (e.g., `2025-12-19T10:00:00Z` or `2025-12-19T10:00:00+00:00`)

**Relationships**:
- One collection has many books (book_ids)
- One book may belong to multiple collections (many-to-many)

**State Transitions**:
```
[New] --create()--> [Persisted]
[Persisted] --add_books()--> [Persisted] (book_ids updated)
[Persisted] --remove_books()--> [Persisted] (book_ids updated)
[Persisted] --rename()--> [Persisted] (name updated)
[Persisted] --delete()--> [Deleted]
```

**Invariants**:
- Collection names must be unique at any given time
- Deleting a book from filesystem does NOT auto-remove it from collections; the system treats missing book_ids as “orphaned” and supports cleanup
- Empty collections are valid and displayed

---

### 2. LibraryStats

**Purpose**: Aggregated statistics for a given scope (all books, format filter, or collection).

**Usage**: Returned by `GET /api/library/stats?scope=...`

**Schema**:
```python
@dataclass
class LibraryStats:
    """
    Aggregated statistics for books in a given scope.

    Computed server-side on demand; not persisted.
    """
    scope: str                 # Scope identifier (e.g., "all", "format:epub", "collection:uuid")
    books_total: int           # Total books in scope
    books_indexed: int         # Books with semantic index (chroma_db exists)
    indexed_percent: int       # Round(books_indexed / books_total * 100) if books_total > 0 else 0
    sections_total: int        # Sum of section_count across all books in scope
    chunks_total: int          # Sum of chunk_count across indexed books in scope

    # Metadata (for debugging/caching):
    computed_at: str           # ISO 8601 timestamp when stats were computed
```

**Validation Rules**:
- `books_total >= books_indexed >= 0`
- `indexed_percent` in range [0, 100]
- `sections_total >= 0`, `chunks_total >= 0`

**Computation Logic**:
```python
def compute_stats(scope: str, all_books: List[BookMetadata]) -> LibraryStats:
    # Filter books by scope
    filtered = filter_books_by_scope(all_books, scope)

    books_total = len(filtered)
    books_indexed = sum(1 for b in filtered if b.is_indexed)
    indexed_percent = round(books_indexed / books_total * 100) if books_total > 0 else 0
    sections_total = sum(b.section_count for b in filtered)
    chunks_total = sum(int(b.chunk_count or 0) for b in filtered if b.is_indexed)

    return LibraryStats(
        scope=scope,
        books_total=books_total,
        books_indexed=books_indexed,
        indexed_percent=indexed_percent,
        sections_total=sections_total,
        chunks_total=chunks_total,
        computed_at=datetime.utcnow().isoformat() + 'Z'
    )
```

**Caching**:
- The stats response may be cached in-memory per-scope for a short TTL (<=5s).
- `GET /api/library/stats?fresh=true` forces a recompute for that request.

---

### 3. BookMetadata (Extended)

**Purpose**: Metadata for a single book, used in library grid/list views.

**Usage**: Returned by `GET /` (library page) as `books: List[BookMetadata]`

**Schema**:
```python
@dataclass
class BookMetadata:
    """
    Extended book metadata for library UI rendering.

    Built from existing Book dataclass + index status lookups.
    """
    id: str                    # Book folder ID (e.g., "dracula_data")
    title: str                 # Book title from metadata
    author: str                # Book author from metadata
    format: str                # "epub" | "pdf" (only "epub" for now)

    # Cover image:
    cover_url: Optional[str]   # Relative URL (e.g., "/read/dracula_data/images/cover.jpg") or None

    # Structural metadata:
    section_count: int         # Number of spine items (len(book.spine))

    # Index metadata (lazily fetched by the client):
    # - Source of truth (server): GET /api/index/{book_id}/status returns status in {"not_indexed","indexed","unknown"}
    # - UI adds transient states: "indexing" and "error"
    is_indexed: Optional[bool]           # True iff server status == "indexed"; may be null before lazy fetch completes
    chunk_count: Optional[int]           # Chunk count from server (0 for not_indexed; null for unknown or before fetch)
    index_status: Optional[str]          # "not_indexed" | "indexed" | "unknown" | "indexing" | "error"; may be null before fetch

    # Navigation:
    read_url: str              # URL to start reading (e.g., "/read/dracula_data/0")
```

**Validation Rules**:
- `id`: Must match `*_data` folder pattern
- `title`, `author`: Non-empty strings
- `format`: Enum {"epub", "pdf"}
- `section_count >= 1` (every book has at least one spine item)
- `index_status` is `None` before lazy fetch completes
- `chunk_count` is `None` when `index_status` is `None` or `unknown`
- once populated, `index_status` in {"not_indexed", "indexed", "unknown", "indexing", "error"}

**Derivation**:
```python
def build_book_metadata(book: Book, book_id: str) -> BookMetadata:
    # Find cover image
    cover_url = find_cover_image(book, book_id)  # Best-effort search

    return BookMetadata(
        id=book_id,
        title=book.metadata.title,
        author=book.metadata.author,
        format="epub",  # Hardcoded for now; PDF support later
        cover_url=cover_url,
        section_count=len(book.spine),
        # Index metadata is filled in client-side after render via GET /api/index/{book_id}/status
        is_indexed=None,
        chunk_count=None,
        index_status=None,
        read_url=f"/read/{book_id}/0"
    )
```

**Performance Note**:
- Initial library load should NOT block on index status fetches
- Options:
  1. Server pre-fetches index statuses (sync, may slow page load)
  2. Client lazy-fetches statuses after page render (async, faster initial load)

**Decision**: Use option 2 (client lazy-fetch) for MVP; add server-side caching if needed.

---

### 4. CollectionMembership (Implicit)

**Purpose**: Represents the many-to-many relationship between Collections and Books.

**Representation**: Embedded in `Collection.book_ids` list (denormalized).

**Why not a separate entity?**
- Simplicity—no need for join table in file-based storage
- Collections are small (<100 books typical); in-memory filtering is fast
- When migrating to DB: can normalize into separate table

**Query Patterns**:
```python
# Get all books in a collection:
books_in_collection = [b for b in all_books if b.id in collection.book_ids]

# Get all collections containing a book:
collections_for_book = [c for c in all_collections if book_id in c.book_ids]

# Add book to collection:
collection.book_ids.append(book_id)
save_collections()  # Atomic write

# Remove book from collection:
collection.book_ids.remove(book_id)
save_collections()
```

---

## Storage Schema

### config/library_collections.json

```json
{
  "schema_version": 1,
  "collections": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Science Fiction",
      "created_at": "2025-12-19T10:00:00Z",
      "book_ids": ["foundation_data", "dune_data", "neuromancer_data"]
    },
    {
      "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "name": "Non-Fiction",
      "created_at": "2025-12-19T11:30:00Z",
      "book_ids": ["sapiens_data"]
    }
  ]
}
```

**File Management**:
- **Read**: `json.load()`
- **Write**: Atomic write pattern (write to `.tmp`, then `os.rename()`)
- **Validation**: Check `schema_version` on load; treat unsupported versions as a recoverable error surfaced to the UI/API
- **Concurrency**: Single-user app; no locking needed for MVP (atomic write is sufficient)
- **Gitignore**: Add `config/library_collections.json` to `.gitignore`

---

## API Request/Response Models

### POST /api/collections

**Request**:
```json
{
  "name": "Science Fiction"
}
```

**Response** (201 Created):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Science Fiction",
  "created_at": "2025-12-19T10:00:00Z",
  "book_ids": []
}
```

---

### POST /api/collections/{collection_id}/books

**Request**:
```json
{
  "action": "add",
  "book_ids": ["dracula_data", "foundation_data"]
}
```

**Response** (200 OK):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Science Fiction",
  "created_at": "2025-12-19T10:00:00Z",
  "book_ids": ["dracula_data", "foundation_data"]
}
```

---

### GET /api/library/stats?scope=all

**Response** (200 OK):
```json
{
  "scope": "all",
  "books_total": 42,
  "books_indexed": 30,
  "indexed_percent": 71,
  "sections_total": 1250,
  "chunks_total": 8400,
  "computed_at": "2025-12-19T12:00:00Z"
}
```

---

### GET / (Library Page Context)

**Response** (partial; added fields highlighted):
```python
{
  "books": [
    {
      "id": "dracula_data",
      "title": "Dracula",
      "author": "Bram Stoker",
      "format": "epub",
      "cover_url": "/read/dracula_data/images/cover.jpg",
      "section_count": 27,
      "read_url": "/read/dracula_data/0"
    },
    // ... more books
  ],
  "collections": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Science Fiction",
      "created_at": "2025-12-19T10:00:00Z",
      "book_ids": ["foundation_data", "dune_data"]
    }
  ]
}
```

---

## Migration Path (Future)

When migrating to SQLite/PostgreSQL:

**Collections Table**:
```sql
CREATE TABLE collections (
    id UUID PRIMARY KEY,
    name VARCHAR(60) UNIQUE NOT NULL,
    created_at TIMESTAMP NOT NULL,
    description TEXT,
    color VARCHAR(7)
);
```

**Collection Memberships Table**:
```sql
CREATE TABLE collection_memberships (
    collection_id UUID REFERENCES collections(id) ON DELETE CASCADE,
    book_id VARCHAR(255) NOT NULL,
    added_at TIMESTAMP NOT NULL,
    PRIMARY KEY (collection_id, book_id)
);
```

**Migration Script**:
```python
def migrate_collections_to_db():
    with open('config/library_collections.json') as f:
        data = json.load(f)

    for coll in data['collections']:
        db.execute(
            "INSERT INTO collections (id, name, created_at) VALUES (?, ?, ?)",
            (coll['id'], coll['name'], coll['created_at'])
        )
        for book_id in coll['book_ids']:
            db.execute(
                "INSERT INTO collection_memberships (collection_id, book_id, added_at) VALUES (?, ?, ?)",
                (coll['id'], book_id, coll['created_at'])
            )
    db.commit()
```

---

## Constitution Compliance

### Principle I: Data Structures First
✅ All entities defined as `@dataclass` with explicit types before implementation.

### Principle III: File-Based State Management
✅ Collections stored as `config/library_collections.json` (filesystem-based).
✅ LibraryStats computed on-demand (no persistent state).
✅ BookMetadata derived from existing `book.pkl` files.

### Principle VI: Explicit Over Implicit
✅ Clear separation between persisted (Collection) and computed (LibraryStats) entities.
✅ All fields documented with semantic meaning.
✅ State transitions explicitly defined.

---

## Summary

All entities defined. Ready for contract generation (`contracts/library-api.yaml`).

**Next**: Generate OpenAPI schema for collections + stats endpoints.

---

## Client-Side UI State (Non-persisted server-side)

### localStorage keys

- `reader3.library.viewMode`: `grid` | `list`
- `reader3.library.rightPanelCollapsed` (optional): `true` | `false`

### sessionStorage keys

Library Chat (v1) may persist per-tab history:

- `reader3.library.chat.*`: implementation-defined JSON payloads (kept separate from the in-book AI IndexedDB store `reader3_ai_assistant`)
