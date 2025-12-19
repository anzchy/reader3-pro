# Data Model: Book Notes & Annotations

**Feature**: 003-add-book-notes
**Date**: 2025-12-19
**Phase**: 1 (Design)

## Overview

This document defines the data structures for book annotations following Reader3 Pro's constitution principle I: "Data Structures First". All entities use Python `@dataclass` with explicit type annotations.

---

## Core Entity: Annotation

### Dataclass Definition

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4


# Type aliases for clarity
AnnotationType = Literal["marker", "wavy", "underline", "note"]
MarkerColor = Literal["yellow", "green", "pink", "blue"]


@dataclass
class Annotation:
    """
    Represents a single user annotation (highlight, underline, or note) on book content.

    Annotations are anchored to chapter text using prefix+quote+suffix for robust
    re-anchoring across page refreshes. The `orphaned` flag tracks re-anchoring failures.

    Storage: Serialized to books/{book_id}/notes.json alongside book.pkl and images/.
    """

    # Identity
    id: str = field(default_factory=lambda: str(uuid4()))
    """Unique identifier (UUID v4)"""

    book_id: str = ""
    """Book folder name (e.g., 'dracula_data'). Must match {book_id} in /read/{book_id}/{chapter_index}"""

    chapter_index: int = 0
    """0-based spine index. Maps to chapter_order in ChapterContent from reader3.py"""

    # Annotation Type & Styling
    type: AnnotationType = "marker"
    """
    Annotation visual style:
    - marker: Colored background highlight
    - wavy: Wavy underline
    - underline: Straight underline
    - note: Marker with attached note text (hover tooltip)
    """

    color: Optional[MarkerColor] = "yellow"
    """
    Background color for type='marker' or type='note'.
    Null for wavy/underline. Default: yellow.
    Colors match common highlighter sets.
    """

    # Text Anchoring (for persistence & re-anchoring)
    quote: str = ""
    """The exact selected text. Required for re-anchoring."""

    prefix: str = ""
    """
    Up to 50 characters before the selection in chapter plain text.
    Used for re-anchoring to find unique match.
    """

    suffix: str = ""
    """
    Up to 50 characters after the selection in chapter plain text.
    Used for re-anchoring to find unique match.
    """

    position: Optional[int] = None
    """
    Character offset of quote start within chapter plain text at creation time.
    Hint for ordering and jump targeting. May be recomputed on load.
    Null if position unknown (e.g., imported from external source).
    """

    # Note Content (optional)
    note_text: Optional[str] = None
    """
    User's note text (only for type='note').
    Must be HTML-escaped before persisting to disk; render via textContent (no innerHTML).
    Null for marker/wavy/underline annotations.
    """

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    """ISO 8601 UTC timestamp of annotation creation"""

    orphaned: bool = False
    """
    True if re-anchoring failed (quote not found in chapter text).
    Orphaned annotations are excluded from display but preserved in storage
    for potential recovery (e.g., EPUB reprocessing, text search).
    """

    # Validation
    def __post_init__(self) -> None:
        """Validate field constraints after initialization"""
        if not self.book_id:
            raise ValueError("book_id is required")
        if self.chapter_index < 0:
            raise ValueError("chapter_index must be >= 0")
        if not self.quote:
            raise ValueError("quote is required (empty selections not allowed)")
        if self.type == "marker" and self.color is None:
            self.color = "yellow"  # Auto-fix: default color for markers
        if self.type in ("wavy", "underline") and self.color is not None:
            self.color = None  # Auto-fix: underlines don't have colors
        if len(self.prefix) > 50:
            self.prefix = self.prefix[-50:]  # Truncate to last 50 chars
        if len(self.suffix) > 50:
            self.suffix = self.suffix[:50]  # Truncate to first 50 chars

    # Serialization
    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict for storage"""
        return {
            "id": self.id,
            "book_id": self.book_id,
            "chapter_index": self.chapter_index,
            "type": self.type,
            "color": self.color,
            "quote": self.quote,
            "prefix": self.prefix,
            "suffix": self.suffix,
            "position": self.position,
            "note_text": self.note_text,
            "created_at": self.created_at,
            "orphaned": self.orphaned,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Annotation:
        """Deserialize from JSON dict"""
        return cls(
            id=str(data.get("id", "")),
            book_id=str(data.get("book_id", "")),
            chapter_index=int(data.get("chapter_index", 0)),
            type=data.get("type", "marker"),
            color=data.get("color"),
            quote=str(data.get("quote", "")),
            prefix=str(data.get("prefix", "")),
            suffix=str(data.get("suffix", "")),
            position=data.get("position"),
            note_text=data.get("note_text"),
            created_at=str(data.get("created_at", "")),
            orphaned=bool(data.get("orphaned", False)),
        )
```

---

## Storage Schema: notes.json

### File Location

`books/{book_id}/notes.json`

Example: `books/dracula_data/notes.json`

### JSON Structure

```json
{
  "schema_version": 1,
  "book_id": "dracula_data",
  "annotations": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "book_id": "dracula_data",
      "chapter_index": 3,
      "type": "marker",
      "color": "yellow",
      "quote": "It was a lovely sight, even to me",
      "prefix": "...shone on the water as the moonlight. ",
      "suffix": ", who had seen so many sunsets...",
      "position": 1234,
      "note_text": null,
      "created_at": "2025-12-19T10:30:00Z",
      "orphaned": false
    },
    {
      "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "book_id": "dracula_data",
      "chapter_index": 3,
      "type": "note",
      "color": "yellow",
      "quote": "the Count's mysterious power",
      "prefix": "...I began to understand ",
      "suffix": " over the wolves and the...",
      "position": 2456,
      "note_text": "Key theme: supernatural control over nature",
      "created_at": "2025-12-19T10:35:00Z",
      "orphaned": false
    },
    {
      "id": "a3d5e8f9-1234-5678-9abc-def012345678",
      "book_id": "dracula_data",
      "chapter_index": 5,
      "type": "wavy",
      "color": null,
      "quote": "strange and uncanny",
      "prefix": "...atmosphere was ",
      "suffix": " as we approached...",
      "position": 567,
      "note_text": null,
      "created_at": "2025-12-19T11:00:00Z",
      "orphaned": false
    }
  ]
}
```

### Schema Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | int | Yes | Storage format version (1 for v1). For future migrations. |
| `book_id` | string | Yes | Redundant with file path but aids validation and migration. |
| `annotations` | array | Yes | List of Annotation objects (may be empty for new books). |

### Schema Versioning

**Current Version**: 1

**Future Migration Path**:
- v1 → v2: Add `last_modified` field to Annotation
- v2 → v3: Add `tags` array for categorization
- Migration script: `scripts/migrate_notes_schema.py` (to be created when needed)

**Backward Compatibility**: Older schema versions auto-upgrade on first save (add missing fields with defaults).

---

## Data Relationships

### Book ↔ Annotations

**Cardinality**: One book → Many annotations (0..N)

**Referential Integrity**:
- Annotations reference `book_id` (folder name) and `chapter_index` (spine position)
- No foreign key enforcement (file-based storage)
- Orphaned books (deleted `{book_id}` folder) leave stale `notes.json` → cleaned up manually

**Cascade Deletion**:
- Deleting `books/{book_id}/` removes `notes.json` automatically (directory delete)
- No server-side cascade logic needed

### Chapter ↔ Annotations

**Cardinality**: One chapter → Many annotations (0..N)

**Mapping**:
- `Annotation.chapter_index` maps to `ChapterContent.order` in `book.pkl` spine
- Chapter re-ordering (EPUB reprocessing) breaks annotation links → orphaned annotations

**Ordering**:
- Annotations sorted by `position` (character offset) within chapter
- Fallback: `created_at` timestamp if position unavailable

---

## Validation Rules

### Server-Side (Python)

Enforced in `notes_service.py`:

1. **book_id validation**:
   ```python
   available_books = get_available_books()  # From server.py
   if book_id not in available_books:
       raise HTTPException(status_code=404, detail="Book not found")
   ```

2. **chapter_index validation**:
   ```python
   book = load_book(book_id)  # From server.py
   if chapter_index < 0 or chapter_index >= len(book.spine):
       raise HTTPException(status_code=400, detail="Invalid chapter_index")
   ```

3. **quote validation**:
   ```python
   if not quote or len(quote) > 10000:  # Sanity limit
       raise HTTPException(status_code=400, detail="Invalid quote length")
   ```

4. **note_text sanitization**:
   ```python
   import html
   note_text_safe = html.escape(note_text) if note_text else None
   ```

### Client-Side (JavaScript)

Enforced in `annotations.js`:

1. **Selection validation**:
   ```javascript
   const selection = window.getSelection();
   if (selection.isCollapsed || selection.toString().trim() === '') {
       return;  // Don't show toolbar for empty selection
   }
   ```

2. **Context extraction**:
   ```javascript
   const chapterText = document.querySelector('.book-content').textContent;
   const start = chapterText.indexOf(quote);
   const prefix = chapterText.substring(Math.max(0, start - 50), start);
   const suffix = chapterText.substring(start + quote.length, start + quote.length + 50);
   ```

---

## Performance Considerations

### Storage Size Estimates

**Assumptions**:
- Average quote length: 50 characters
- Average note_text length: 100 characters (when present)
- Annotation overhead (JSON fields): ~200 bytes

**Calculations**:
- Marker: ~300 bytes
- Note with text: ~400 bytes
- 200 annotations/book: ~60 KB
- 1000 annotations/book: ~300 KB

**Conclusion**: File size manageable; no pagination needed for v1.

### Load Performance

**Current Approach** (no caching):
1. API request: `GET /api/notes/{book_id}/{chapter_index}`
2. Read `notes.json` from disk (~1-5ms for 60KB file)
3. Parse JSON (~1-2ms)
4. Filter by chapter_index (~0.1ms)
5. Return JSON response

**Estimated Total**: 5-10ms (well below 200ms target)

**Optimization** (if needed in Phase 2):
```python
@lru_cache(maxsize=50)  # Cache 50 books' annotations
def load_book_annotations(book_id: str) -> dict:
    # ...existing load logic...
```

### Render Performance

**Client-Side Rendering** (per chapter):
1. Fetch annotations via API (~10ms network)
2. Extract chapter plain text (~5ms)
3. Re-anchor 50 annotations (~20ms string search)
4. Apply `<mark>` elements (~50ms DOM manipulation)

**Estimated Total**: ~85ms (well below 200ms target)

**Worst Case** (500 annotations/chapter): ~400ms → needs optimization (rare scenario)

---

## Security Considerations

### XSS Prevention

**Threat**: User enters `<script>alert('XSS')</script>` in note_text

**Mitigation**:
1. **Server-side escaping**:
   ```python
   import html
   annotation.note_text = html.escape(user_input)
   ```

2. **Client-side safe rendering**:
   ```javascript
   tooltipEl.textContent = annotation.note_text;  // Uses textContent, not innerHTML
   ```

**Constitution Compliance**: Principle IV (HTML Content Sanitization)

### Path Traversal

**Threat**: Malicious `book_id` like `../../etc/passwd` to read arbitrary files

**Mitigation**:
```python
def validate_book_id(book_id: str) -> str:
    available = get_available_books()  # Enumerates books/*_data/
    if book_id not in available:
        raise HTTPException(status_code=404, detail="Book not found")
    return book_id
```

**Constitution Compliance**: Principle V (Path Security)

### Input Validation

**Limits**:
- `quote`: 10,000 chars max (prevents DoS via huge quotes)
- `note_text`: 10,000 chars max
- `prefix`/`suffix`: Auto-truncated to 50 chars

**Rate Limiting**: Not implemented in v1 (single-user localhost). Add in production deployment.

---

## Migration & Compatibility

### v1 Migration Plan

**From**: No annotations (new feature)
**To**: `notes.json` with schema_version=1

**Process**:
1. First annotation creation triggers `notes.json` creation
2. Subsequent annotations append to `annotations` array
3. No migration script needed (fresh start)

### Future Schema Changes

**Example**: Adding `tags` field in v2

**Migration Function**:
```python
def migrate_notes_v1_to_v2(notes_path: str) -> None:
    with open(notes_path, 'r') as f:
        data = json.load(f)

    if data.get('schema_version') == 1:
        for annotation in data['annotations']:
            annotation['tags'] = []  # Add default tags
        data['schema_version'] = 2

        # Atomic write
        tmp_path = f"{notes_path}.tmp"
        with open(tmp_path, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, notes_path)
```

**Trigger**: Run migration on server startup (check all `notes.json` files)

---

## Testing Data

### Sample Annotations for QA

**Test Book**: `dracula_data` (from Project Gutenberg EPUB)

**Annotations**:
1. **Marker (yellow)**: Chapter 1, "the castle was hidden in darkness" → Test basic highlight
2. **Marker (green)**: Chapter 1, "strange journey" → Test color variants
3. **Wavy**: Chapter 2, "uncanny atmosphere" → Test underline style
4. **Underline**: Chapter 3, "mysterious count" → Test straight underline
5. **Note**: Chapter 1, "Jonathan Harker" → note_text: "Protagonist" → Test hover tooltip
6. **Overlapping**: Chapter 1, "dark night" → Both marker (yellow) + wavy → Test layering
7. **Orphaned**: Delete "hidden in darkness" from chapter 1, reload → Test orphaned flag

**JSON File** (`specs/003-add-book-notes/test-data/sample-notes.json`):
```json
{
  "schema_version": 1,
  "book_id": "dracula_data",
  "annotations": [
    {
      "id": "test-001",
      "book_id": "dracula_data",
      "chapter_index": 0,
      "type": "marker",
      "color": "yellow",
      "quote": "the castle was hidden in darkness",
      "prefix": "As we climbed higher, ",
      "suffix": " and I could see nothing...",
      "position": 150,
      "note_text": null,
      "created_at": "2025-12-19T10:00:00Z",
      "orphaned": false
    }
  ]
}
```

---

## Summary

**Entities**: 1 dataclass (`Annotation`)
**Storage**: 1 JSON file per book (`notes.json`)
**Validation**: 4 server-side rules, 2 client-side rules
**Security**: XSS escaping, path traversal prevention, input limits
**Performance**: <10ms load, <100ms render (typical case)
**Migration**: Fresh start (v1), versioned schema for future changes

**Constitution Compliance**:
- ✅ Principle I: Data Structures First (Annotation @dataclass)
- ✅ Principle III: File-Based State (notes.json per book)
- ✅ Principle IV: HTML Sanitization (note_text escaped)
- ✅ Principle V: Path Security (book_id validation)
- ✅ Principle VI: Explicit Types (all fields type-hinted)
