# Developer Quickstart: Book Notes & Annotations

**Feature**: 003-add-book-notes
**Date**: 2025-12-19
**Phase**: 1 (Design)

## Overview

This guide helps developers implement and test the WeRead-style book annotations feature. It covers setup, development workflow, testing procedures, and troubleshooting.

**Prerequisites**:
- Reader3 Pro repository cloned
- Feature branch `003-add-book-notes` checked out
- Python 3.10+, uv installed
- Chromium-based browser (Chrome/Edge) for testing

---

## Quick Start

### 1. Setup Development Environment

```bash
# Navigate to project root
cd reader3-pro-wt/003

# Install dependencies (if not already done)
uv sync

# Start development server
uv run reader3-server

# Server starts at http://127.0.0.1:8123
```

### 2. Verify Existing Features

Before implementing annotations, ensure existing features work:

```bash
# Open browser to library page
open http://127.0.0.1:8123

# Click any book → verify reader loads
# Verify TOC navigation works
# Verify search feature works (feature 001)
# Verify AI panel works (feature 002, if configured)
```

### 3. Implementation Order

Follow this sequence to minimize integration issues:

**Phase 1**: Backend (Day 1-2)
1. Create `src/reader3_app/models/annotations.py`
2. Create `src/reader3_app/notes_service.py`
3. Add `/api/notes/*` endpoints to `server.py`
4. Test API with curl/Postman

**Phase 2**: Frontend Core (Day 3-4)
5. Update `reader.html` for fullscreen layout
6. Implement right toolbar (`static/js/toolbar.js`)
7. Implement annotation rendering (`static/js/annotations.js`)
8. Test selection → toolbar → save → reload → re-anchor

**Phase 3**: Panels (Day 5-6)
9. Implement TOC panel (`static/js/toc-panel.js`)
10. Implement Notes panel (`static/js/notes-panel.js`)
11. Visual fidelity CSS matching WeRead screenshots (right toolbar + TOC/Notes modes only)

**Phase 4**: Integration (Day 7)
12. Wire up "AI 问书" CustomEvent
13. Test all keyboard shortcuts (Esc priority)
14. Final QA against acceptance scenarios

---

## Implementation Details

### Backend: Annotation Dataclass

**File**: `src/reader3_app/models/annotations.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4


AnnotationType = Literal["marker", "wavy", "underline", "note"]
MarkerColor = Literal["yellow", "green", "pink", "blue"]


@dataclass
class Annotation:
    """User annotation on book content"""

    # Identity
    id: str = field(default_factory=lambda: str(uuid4()))
    book_id: str = ""
    chapter_index: int = 0

    # Type & Style
    type: AnnotationType = "marker"
    color: Optional[MarkerColor] = "yellow"

    # Text Anchoring
    quote: str = ""
    prefix: str = ""
    suffix: str = ""
    position: Optional[int] = None

    # Note Content
    note_text: Optional[str] = None

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    orphaned: bool = False

    def __post_init__(self) -> None:
        """Validate and normalize fields"""
        if not self.book_id:
            raise ValueError("book_id is required")
        if self.chapter_index < 0:
            raise ValueError("chapter_index must be >= 0")
        if not self.quote:
            raise ValueError("quote is required")

        # Auto-fix colors
        if self.type == "marker" and self.color is None:
            self.color = "yellow"
        if self.type in ("wavy", "underline"):
            self.color = None

        # Truncate context
        if len(self.prefix) > 50:
            self.prefix = self.prefix[-50:]
        if len(self.suffix) > 50:
            self.suffix = self.suffix[:50]

    def to_dict(self) -> dict:
        """Serialize to JSON"""
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
        """Deserialize from JSON"""
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

### Backend: Notes Service

**File**: `src/reader3_app/notes_service.py`

```python
import json
import os
from typing import List, Optional

from reader3_app.models.annotations import Annotation


NOTES_FILENAME = "notes.json"


def _notes_path(books_dir: str, book_id: str) -> str:
    """Get path to notes.json for a book"""
    return os.path.join(books_dir, book_id, NOTES_FILENAME)


def load_annotations(books_dir: str, book_id: str) -> List[Annotation]:
    """Load all annotations for a book"""
    path = _notes_path(books_dir, book_id)
    if not os.path.exists(path):
        return []

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        annotations_data = data.get('annotations', [])
        return [Annotation.from_dict(a) for a in annotations_data]
    except Exception:
        return []


def save_annotations(books_dir: str, book_id: str, annotations: List[Annotation]) -> None:
    """Save annotations to notes.json (atomic write)"""
    path = _notes_path(books_dir, book_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    data = {
        "schema_version": 1,
        "book_id": book_id,
        "annotations": [a.to_dict() for a in annotations]
    }

    # Atomic write
    tmp_path = f"{path}.tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def add_annotation(books_dir: str, annotation: Annotation) -> str:
    """Add new annotation and return its ID"""
    annotations = load_annotations(books_dir, annotation.book_id)
    annotations.append(annotation)
    save_annotations(books_dir, annotation.book_id, annotations)
    return annotation.id


def delete_annotation(books_dir: str, book_id: str, note_id: str) -> bool:
    """Delete annotation by ID, return True if found and deleted"""
    annotations = load_annotations(books_dir, book_id)
    original_count = len(annotations)
    annotations = [a for a in annotations if a.id != note_id]

    if len(annotations) < original_count:
        save_annotations(books_dir, book_id, annotations)
        return True
    return False
```

### Backend: API Endpoints

**File**: `src/reader3_app/web/server.py` (additions)

```python
from fastapi import HTTPException
import html

from reader3_app import notes_service
from reader3_app.models.annotations import Annotation


@app.get("/api/notes/{book_id}")
def get_all_notes(book_id: str):
    """Get all annotations for a book, grouped by chapter"""
    # Validate book_id
    available_books = get_available_books()
    if book_id not in available_books:
        raise HTTPException(status_code=404, detail="Book not found")

    # Load annotations
    annotations = notes_service.load_annotations(BOOKS_DIR, book_id)
    annotations = [a for a in annotations if not a.orphaned]  # Exclude orphaned

    # Group by chapter
    book = load_book(book_id)
    by_chapter = {}
    for ann in annotations:
        if ann.chapter_index not in by_chapter:
            by_chapter[ann.chapter_index] = []
        by_chapter[ann.chapter_index].append(ann)

    # Sort within each chapter by position
    for anns in by_chapter.values():
        anns.sort(key=lambda a: a.position if a.position is not None else 0)

    # Build response
    annotations_by_chapter = []
    for chapter_index in sorted(by_chapter.keys()):
        chapter = book.spine[chapter_index]
        annotations_by_chapter.append({
            "chapter_index": chapter_index,
            "chapter_title": chapter.title,
            "count": len(by_chapter[chapter_index]),
            "annotations": [
                {
                    "id": a.id,
                    "type": a.type,
                    "color": a.color,
                    "quote": a.quote[:200],  # Truncate for display
                    "note_text": a.note_text[:200] if a.note_text else None,
                    "position": a.position,
                    "created_at": a.created_at,
                }
                for a in by_chapter[chapter_index]
            ]
        })

    return {
        "schema_version": 1,
        "book_id": book_id,
        "total_count": len(annotations),
        "annotations_by_chapter": annotations_by_chapter
    }


@app.get("/api/notes/{book_id}/{chapter_index}")
def get_chapter_notes(book_id: str, chapter_index: int):
    """Get annotations for a specific chapter"""
    # Validate book_id
    available_books = get_available_books()
    if book_id not in available_books:
        raise HTTPException(status_code=404, detail="Book not found")

    # Validate chapter_index
    book = load_book(book_id)
    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=400, detail="Invalid chapter_index")

    # Load and filter annotations
    annotations = notes_service.load_annotations(BOOKS_DIR, book_id)
    chapter_annotations = [
        a for a in annotations
        if a.chapter_index == chapter_index and not a.orphaned
    ]

    # Sort by position
    chapter_annotations.sort(key=lambda a: a.position if a.position is not None else 0)

    return {
        "book_id": book_id,
        "chapter_index": chapter_index,
        "count": len(chapter_annotations),
        "annotations": [a.to_dict() for a in chapter_annotations]
    }


@app.post("/api/notes/{book_id}/{chapter_index}")
def create_note(book_id: str, chapter_index: int, data: dict):
    """Create new annotation"""
    # Validate inputs
    available_books = get_available_books()
    if book_id not in available_books:
        raise HTTPException(status_code=404, detail="Book not found")

    book = load_book(book_id)
    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=400, detail="Invalid chapter_index")

    # Sanitize note_text
    note_text = data.get("note_text")
    if note_text:
        note_text = html.escape(note_text)

    # Create annotation
    annotation = Annotation(
        book_id=book_id,
        chapter_index=chapter_index,
        type=data.get("type", "marker"),
        color=data.get("color"),
        quote=data.get("quote", ""),
        prefix=data.get("prefix", ""),
        suffix=data.get("suffix", ""),
        position=data.get("position"),
        note_text=note_text,
    )

    # Save
    annotation_id = notes_service.add_annotation(BOOKS_DIR, annotation)

    return {
        "id": annotation_id,
        "created_at": annotation.created_at,
        "message": "Annotation created successfully"
    }


@app.delete("/api/notes/{book_id}/{chapter_index}/{note_id}")
def delete_note(book_id: str, chapter_index: int, note_id: str):
    """Delete annotation (optional for v1)"""
    available_books = get_available_books()
    if book_id not in available_books:
        raise HTTPException(status_code=404, detail="Book not found")

    deleted = notes_service.delete_annotation(BOOKS_DIR, book_id, note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Annotation not found")

    return {"message": "Annotation deleted successfully"}
```

### Frontend: Annotation Rendering

**File**: `static/js/annotations.js` (simplified excerpt)

```javascript
class AnnotationRenderer {
  constructor(bookId, chapterIndex) {
    this.bookId = bookId;
    this.chapterIndex = chapterIndex;
    this.annotations = [];
  }

  async loadAndRender() {
    // Fetch annotations from API
    const response = await fetch(`/api/notes/${this.bookId}/${this.chapterIndex}`);
    const data = await response.json();
    this.annotations = data.annotations;

    // Apply to DOM
    this.renderAnnotations();
  }

  renderAnnotations() {
    const contentEl = document.querySelector('.book-content');
    const chapterText = contentEl.textContent;

    // Sort by position (render in order)
    const sortedAnns = this.annotations.sort((a, b) =>
      (a.position || 0) - (b.position || 0)
    );

    sortedAnns.forEach(ann => {
      const range = this.findRange(chapterText, ann);
      if (range) {
        this.applyMark(contentEl, range, ann);
      } else {
        // Re-anchoring failed - mark as orphaned
        this.markOrphaned(ann.id);
      }
    });
  }

  findRange(chapterText, ann) {
    // Try prefix + quote + suffix
    const fullMatch = ann.prefix + ann.quote + ann.suffix;
    let start = chapterText.indexOf(fullMatch);
    if (start >= 0) {
      start += ann.prefix.length;
      return {start, end: start + ann.quote.length};
    }

    // Fallback: quote only (first occurrence)
    start = chapterText.indexOf(ann.quote);
    if (start >= 0) {
      return {start, end: start + ann.quote.length};
    }

    return null;  // Orphaned
  }

  applyMark(contentEl, range, ann) {
    // Traverse text nodes and wrap matching range
    // (Similar to search highlighting in feature 001)
    const walker = document.createTreeWalker(
      contentEl,
      NodeFilter.SHOW_TEXT,
      null
    );

    let charIndex = 0;
    const nodesToMark = [];

    let node;
    while (node = walker.nextNode()) {
      const nodeStart = charIndex;
      const nodeEnd = charIndex + node.textContent.length;

      if (nodeEnd > range.start && nodeStart < range.end) {
        const markStart = Math.max(0, range.start - nodeStart);
        const markEnd = Math.min(node.textContent.length, range.end - nodeStart);
        nodesToMark.push({node, markStart, markEnd});
      }

      charIndex = nodeEnd;
    }

    // Wrap each text node segment in <mark>
    nodesToMark.forEach(({node, markStart, markEnd}) => {
      const before = node.textContent.substring(0, markStart);
      const marked = node.textContent.substring(markStart, markEnd);
      const after = node.textContent.substring(markEnd);

      const mark = document.createElement('mark');
      mark.className = `annotation annotation--${ann.type}`;
      if (ann.color) mark.classList.add(`annotation--${ann.color}`);
      mark.dataset.annotationId = ann.id;
      mark.textContent = marked;

      // Replace text node with before + mark + after
      const parent = node.parentNode;
      if (before) parent.insertBefore(document.createTextNode(before), node);
      parent.insertBefore(mark, node);
      if (after) parent.insertBefore(document.createTextNode(after), node);
      parent.removeChild(node);
    });
  }

  async markOrphaned(annotationId) {
    // Send update to server to set orphaned=true
    console.warn(`Annotation ${annotationId} orphaned (quote not found)`);
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  const bookId = window.location.pathname.split('/')[2];
  const chapterIndex = parseInt(window.location.pathname.split('/')[3]);

  const renderer = new AnnotationRenderer(bookId, chapterIndex);
  renderer.loadAndRender();
});
```

---

## Testing Checklist

### Functional Tests

**Annotation Creation**:
- [ ] Select text → toolbar appears near selection
- [ ] Click "Marker" → color picker shows → select yellow → highlight applied
- [ ] Click "Wavy" → wavy underline applied
- [ ] Click "Underline" → straight underline applied
- [ ] Click "写想法" → popover appears → enter note → save → annotation has hover tooltip
- [ ] Click "AI 问书" → AI panel opens with prefilled quote (if feature 002 enabled)
- [ ] Click "Copy" → text copied to clipboard

**Persistence**:
- [ ] Create annotation → refresh page → annotation still visible
- [ ] Create annotation → restart server → open book → annotation still visible
- [ ] Verify `books/{book_id}/notes.json` exists and has correct schema

**Re-anchoring**:
- [ ] Create annotation → close book → reopen → annotation re-anchored to correct position
- [ ] Test overlapping annotations (marker + wavy on same text) → both styles visible
- [ ] Manually edit chapter text in EPUB → reprocess → orphaned annotation hidden

**WeRead UI**:
- [ ] Reader loads in fullscreen mode (no left sidebar)
- [ ] Right toolbar visible with 4 buttons (目录页/Search/AI/Notes)
- [ ] Click `Notes` → Notes panel opens → shows all annotations grouped by chapter
- [ ] Click annotation in Notes panel → jumps to chapter and scrolls to annotation
- [ ] Click `目录页` → TOC panel opens → nested TOC structure visible
- [ ] TOC search input filters chapters in real-time (case-insensitive)
- [ ] Only one panel open at a time (opening one closes others)

**Keyboard Navigation**:
- [ ] Press `Esc` when note popover open → popover closes
- [ ] Press `Esc` when selection toolbar visible → toolbar closes
- [ ] Press `Esc` when tool panel open → panel closes
- [ ] Tab through toolbar buttons → focus visible

**Edge Cases**:
- [ ] Select text spanning multiple paragraphs → annotation works
- [ ] Select text with special characters (quotes, em-dash) → annotation works
- [ ] Create 500 annotations in one chapter → render completes in <500ms
- [ ] Delete `notes.json` → create new annotation → file recreated with schema_version=1

### Visual QA

**Pixel-Perfect Comparison** (vs WeRead screenshots):

1. Open WeRead screenshot in image editor
2. Open Reader3 Pro in browser at same zoom level
3. Take screenshot of Reader3 Pro
4. Overlay screenshots at 50% opacity
5. Check alignment:
   - [ ] Right toolbar button spacing (±2px)
   - [ ] Toolbar button size and shadow
   - [ ] Notes panel header layout
   - [ ] Notes panel empty state text
   - [ ] TOC panel search input styling
   - [ ] Annotation colors (yellow/green/pink/blue)

**CSS Measurements** (Chrome DevTools):
- [ ] Page background: `#f7f7f7`
- [ ] Toolbar button: `#ffffff` with `box-shadow: 0 2px 8px rgba(0,0,0,0.1)`
- [ ] Active button: `#1677ff`
- [ ] Marker yellow: `#fff3cd`
- [ ] Font sizes within ±1px of screenshots

### Performance Profiling

**Chrome DevTools Performance Tab**:

1. Open reader at chapter with 100 annotations
2. Start recording → refresh page → stop recording
3. Check timings:
   - [ ] Annotation API fetch: <20ms
   - [ ] Annotation rendering: <200ms
   - [ ] Total page load: <500ms

4. Open Notes panel
   - [ ] Notes panel render: <300ms for 200 annotations
   - [ ] Scroll smoothness: 60fps

**Network Tab**:
- [ ] `/api/notes/{book_id}/{chapter_index}` returns in <10ms
- [ ] Response size reasonable (~5KB for 50 annotations)

---

## Troubleshooting

### Annotations Not Appearing

**Symptoms**: Created annotation disappears after refresh

**Diagnosis**:
```bash
# Check if notes.json exists
ls books/{book_id}/notes.json

# Check JSON syntax
cat books/{book_id}/notes.json | jq .

# Check server logs for errors
grep "notes" server.log
```

**Solutions**:
- Verify book_id matches folder name (e.g., `dracula_data`)
- Check file permissions (notes.json should be writable)
- Verify JSON schema has `schema_version` and `annotations` array

### Re-anchoring Failures

**Symptoms**: Annotation marked as orphaned (not displayed)

**Diagnosis**:
```javascript
// In browser console
const ann = {quote: "target text", prefix: "before ", suffix: " after"};
const chapterText = document.querySelector('.book-content').textContent;
console.log(chapterText.indexOf(ann.prefix + ann.quote + ann.suffix));
// Should return >= 0 if findable
```

**Solutions**:
- Increase context length (50 → 100 chars) in prefix/suffix
- Add fuzzy matching for minor text variations
- Check if EPUB was reprocessed (text changed)

### Toolbar Positioning Issues

**Symptoms**: Toolbar appears off-screen or overlaps content

**Diagnosis**:
```javascript
// In browser console
const selection = window.getSelection();
const range = selection.getRangeAt(0);
const rect = range.getBoundingClientRect();
console.log(rect);  // Check coordinates
```

**Solutions**:
- Add viewport boundary checks in `toolbar.js`
- Use `getBoundingClientRect()` to position relative to selection
- Add CSS `max-width: calc(100vw - 40px)` to prevent overflow

### Performance Issues

**Symptoms**: Annotation rendering takes >200ms

**Diagnosis**:
```javascript
// Add timing logs in annotations.js
console.time('render-annotations');
this.renderAnnotations();
console.timeEnd('render-annotations');
```

**Solutions**:
- Add `@lru_cache` to `load_annotations()` in notes_service.py
- Implement client-side caching (sessionStorage)
- Lazy-load annotations (fetch on scroll, not upfront)

---

## Development Tips

### Debugging

**Enable Debug Logging**:
```python
# In server.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Browser DevTools**:
- Use "Preserve log" in Console tab
- Use "Disable cache" in Network tab
- Use Breakpoints in Sources tab for JavaScript debugging

### Testing Workflow

1. **Backend-First**: Test API endpoints with curl before building UI
   ```bash
   # Create annotation
   curl -X POST http://127.0.0.1:8123/api/notes/dracula_data/0 \
     -H "Content-Type: application/json" \
     -d '{"type":"marker","color":"yellow","quote":"test","prefix":"","suffix":""}'

   # Get annotations
   curl http://127.0.0.1:8123/api/notes/dracula_data/0
   ```

2. **Incremental UI**: Build one component at a time
   - Right toolbar (no panels)
   - Annotation rendering only
   - Selection toolbar
   - Notes panel
   - TOC panel

3. **Visual Regression**: Take screenshots after each CSS change
   - Compare before/after using diff tools
   - Save reference screenshots in `specs/003-add-book-notes/screenshots/`

### Code Review Checklist

Before submitting PR:
- [ ] All dataclasses have `__post_init__` validation
- [ ] All user input HTML-escaped (note_text, quote)
- [ ] All book_id validated against enumerated directories
- [ ] All API endpoints return proper error codes (400/404/500)
- [ ] All JavaScript uses `textContent` not `innerHTML` for user data
- [ ] All CSS matches WeRead screenshots (within tolerances)
- [ ] All keyboard shortcuts tested (Esc priority)
- [ ] Performance profile included in PR (screenshot of DevTools)
- [ ] Test checklist completed (checkmarks in PR description)

---

## Next Steps

After completing quickstart.md:
1. Run `.specify/scripts/bash/update-agent-context.sh claude`
2. Re-check constitution compliance
3. Proceed to `/speckit.tasks` to generate implementation tasks
4. Begin Phase 2 implementation following task breakdown

**Estimated Implementation Time**: 7 days (1 developer, full-time)

**Risk Areas** (require extra attention):
- Re-anchoring robustness (handle edge cases)
- Pixel-perfect CSS (iterate with screenshots)
- Performance at scale (1000+ annotations per book)
