# Research: Book Notes & Annotations

**Feature**: 003-add-book-notes
**Date**: 2025-12-19
**Phase**: 0 (Technical Research)

## Overview

This document resolves technical unknowns and design decisions for implementing WeRead-style book annotations in Reader3 Pro. All decisions follow the constitution's "simplicity over engineering" principle.

---

## R1: Text Selection & Re-anchoring Strategy

### Decision

Use **prefix + quote + suffix** text-based anchoring with graceful degradation.

### Rationale

**Problem**: Annotations must persist across page refreshes when chapter HTML/DOM may rebuild. DOM path selectors (XPath, CSS selectors) are brittle to HTML structure changes.

**Solution**: Store textual context around selection:
- `prefix`: 50 chars before selection
- `quote`: Selected text (exact match required)
- `suffix`: 50 chars after selection

**Re-anchoring algorithm** (on chapter load):
1. Extract chapter plain text (`.textContent` of `.book-content`)
2. Search for `prefix + quote + suffix` substring
3. Fallback: Search for `quote` only (first occurrence)
4. If not found: Mark annotation as `orphaned=true`, hide from display

**Precedents**:
- PDF.js text layer selection
- Google Docs comment anchoring
- Medium.com text highlighting
- Existing search highlighting in Reader3 Pro (feature 001)

**Complexity**: ~100 LOC for re-anchoring logic (simple string search)

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| W3C Web Annotation selectors (TextQuoteSelector, RangeSelector) | Over-engineered for v1; requires external library; violates constitution principle II |
| DOM XPath storage | Brittle to HTML changes; requires XPath library; not robust |
| Character offset only | Fails when chapter text changes (e.g., EPUB reprocessing) |
| CSS selector + offset | Depends on stable DOM structure; violates "explicit over implicit" |

### Implementation Notes

- Use existing search highlighting code (`static/js/reader.js`) as reference for DOM text traversal
- Plain text extraction: `document.querySelector('.book-content').textContent`
- String matching: JavaScript `indexOf()` with manual substring extraction
- Performance: O(n) single pass over chapter text (<10ms for typical chapters)

---

## R2: Annotation Rendering (DOM Manipulation)

### Decision

Use **`<mark>` elements with CSS classes** for visual annotations, inserted via DOM text-node walker.

### Rationale

**Requirements**:
- Multiple annotation types (marker/wavy/underline/note) must coexist
- Overlapping annotations must layer (background + underline visible simultaneously)
- Must not corrupt existing HTML structure (preserve headings, links, etc.)

**Solution**:
```html
<mark class="annotation annotation--marker annotation--yellow" data-annotation-id="uuid">
  selected text
</mark>
```

**CSS approach**:
- `.annotation--marker`: Background color (yellow/green/pink/blue)
- `.annotation--wavy`: `text-decoration: wavy underline`
- `.annotation--underline`: `text-decoration: underline`
- `.annotation--note`: Cursor pointer + tooltip data attribute

**DOM traversal** (similar to search highlighting):
1. Build plain text from `.book-content` with character-to-node mapping
2. Find annotation positions in plain text
3. Traverse text nodes, split at annotation boundaries
4. Wrap matching ranges in `<mark>` elements

**Precedents**:
- Search result highlighting (feature 001)
- PDF.js text layer highlights
- Chrome "Find in Page" highlighting

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| CSS `::selection` pseudo-element | Cannot persist after selection cleared; no per-annotation control |
| `<span>` instead of `<mark>` | `<mark>` is semantically correct for highlights |
| Canvas overlay rendering | Breaks text selection/copy; inaccessible; over-complex |
| SVG overlay | Same issues as canvas; unnecessary complexity |

### Implementation Notes

- Reuse search highlighting text-node walker from `static/js/reader.js` (modify for multi-range support)
- CSS file: `static/css/annotations.css` (~50 LOC)
- JavaScript: `static/js/annotations.js` (~200 LOC for rendering engine)

---

## R3: WeRead-Style UI Components

### Decision

**Right toolbar**: Floating vertical `<div>` with `position: fixed; right: 20px`

**Tool panels** (TOC/Notes): Fullscreen overlay modes that hide/show `.book-content` container

**Color scheme**: Extract from screenshots using browser DevTools color picker

### Rationale

**Requirements**:
- Visual fidelity vs WeRead screenshots (±2px spacing, ±1px fonts) applies to: right toolbar + TOC mode + Notes mode (Search/AI panels may reuse existing UI)
- Fullscreen reading mode (no left sidebar)
- Only one panel open at a time
- Smooth transitions between modes

**Component Architecture**:

**1. Right Toolbar** (`static/js/toolbar.js`, `static/css/toolbar.css`):
```javascript
class RightToolbar {
  constructor() {
    this.buttons = ['toc', 'search', 'ai', 'notes'];
    this.activePanel = null;
  }

  openPanel(panelName) {
    if (this.activePanel) this.closePanel(this.activePanel);
    // Show panel, hide .book-content, update button state
  }
}
```

**2. Notes Panel** (`static/js/notes-panel.js`, `static/css/notes-panel.css`):
- Header: Book title, cover, "已读到 X%", "共 N 条笔记"
- Body: Scrollable list grouped by chapter
- Empty state: "你可以在这里记录本书的想法、划线、书签"
- Click handler: Navigate to chapter + scroll to annotation

**3. TOC Panel** (`static/js/toc-panel.js`, `static/css/toc-panel.css`):
- Search input with real-time filter (case-insensitive substring)
- Nested TOC list (reuse existing recursive Jinja2 macro structure)
- Click handler: Navigate to chapter, close panel

**Color Values** (extracted from screenshots):
- Page background: `#f7f7f7` (light gray)
- Toolbar buttons: `#ffffff` with `box-shadow: 0 2px 8px rgba(0,0,0,0.1)`
- Active button: `#1677ff` (blue accent)
- Notes panel background: `#ffffff`
- Marker yellow: `#fff3cd`, green: `#d4edda`, pink: `#f8d7da`, blue: `#d1ecf1`

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| React/Vue components | Violates constitution (no new frameworks); unnecessary complexity |
| Right drawer (slides in) | Screenshots show fullscreen panel modes, not drawers |
| CSS Grid layout | Flexbox simpler for vertical toolbar + fullscreen panels |
| Web Components | Over-engineered for single-project use case |

### Implementation Notes

- Total CSS: ~400 LOC across 4 files (toolbar, toc-panel, notes-panel, annotations)
- Total JS: ~600 LOC across 4 modules (toolbar, toc-panel, notes-panel, annotations)
- Use CSS transitions (`transition: opacity 0.2s`) for smooth panel open/close
- Keyboard support: `Esc` handler with priority queue (note editor > toolbar > panel)

---

## R4: Backend Storage & API Design

### Decision

**Storage**: Single `notes.json` file per book with atomic write (temp + rename)

**API**: RESTful endpoints matching existing `/api/search/*` and `/api/ai/*` patterns

### Rationale

**Storage Format** (`books/{book_id}/notes.json`):
```json
{
  "schema_version": 1,
  "book_id": "dracula_data",
  "annotations": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "chapter_index": 3,
      "type": "marker",
      "color": "yellow",
      "position": 1234,
      "quote": "It was a lovely sight",
      "prefix": "...moonlight. ",
      "suffix": ", even to me...",
      "created_at": "2025-12-19T10:30:00Z",
      "note_text": null,
      "orphaned": false
    }
  ]
}
```

**API Endpoints**:
- `GET /api/notes/{book_id}` → All annotations for book
- `GET /api/notes/{book_id}/{chapter_index}` → Chapter annotations only (faster)
- `POST /api/notes/{book_id}/{chapter_index}` → Create annotation (returns id)
- `DELETE /api/notes/{book_id}/{chapter_index}/{note_id}` → Delete (optional v1)

**Atomic Write Pattern** (reused from `ai/conversations.py`):
```python
def save_annotations(book_id: str, annotations: List[Annotation]) -> None:
    path = f"books/{book_id}/notes.json"
    tmp_path = f"{path}.tmp"
    with open(tmp_path, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, path)  # Atomic on POSIX
```

**Precedents**:
- AI conversations storage (feature 002): `ai_conversations/{uuid}.json`
- Search service (feature 001): JSON responses with similar structure

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| SQLite database | Over-engineered for <1000 annotations/book; violates constitution III |
| One JSON file per annotation | Excessive file I/O; fragile atomic updates |
| PostgreSQL/MySQL | Requires separate service; violates "file-based state" principle |
| Embedded in `book.pkl` | Requires reprocessing EPUB to update notes; violates separation of concerns |

### Implementation Notes

- Service module: `src/reader3_app/notes_service.py` (~150 LOC)
- API endpoints: Add to `src/reader3_app/web/server.py` (~100 LOC)
- Validation: Reuse `get_available_books()` for book_id validation
- Error handling: Return 404 if book not found, 400 if invalid request

---

## R5: AI Assistant Integration

### Decision

Use **CustomEvent** for decoupled communication: `003-notes` → `002-ai-assistant`

### Rationale

**Problem**: "AI 问书" must send selected quote to AI panel without tight coupling.

**Solution**:
```javascript
// In annotations.js (003-notes)
function askAI(quote, context) {
  const event = new CustomEvent('reader3:ai:ask', {
    detail: {
      book_id: window.currentBookId,
      chapter_index: window.currentChapterIndex,
      quote: quote,
      context: context  // prefix + suffix
    }
  });
  document.dispatchEvent(event);
}

// In ai-panel.js (002-ai-assistant)
document.addEventListener('reader3:ai:ask', (e) => {
  const {quote, context} = e.detail;
  openAIPanel();
  prefillInput(`关于这段话："${quote}"...\n\n${context}`);
});
```

**Benefits**:
- Feature 003 works even if feature 002 not loaded
- No import dependencies between modules
- Follows existing event-driven pattern in Reader3 Pro

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Shared `window.Reader3AI` object | Requires 002 to initialize global; tighter coupling |
| Import 002's modules in 003 | Creates circular dependency risk; violates decoupling |
| URL parameter passing | Loses state on navigation; clunky UX |

### Implementation Notes

- Event namespace: `reader3:ai:*` (consistent with potential future events)
- Graceful degradation: If no listener, show toast "AI 面板未启用"
- Implementation: ~20 LOC in `annotations.js`, ~30 LOC in existing `ai-panel.js`

---

## R6: Testing Strategy

### Decision

**Manual QA** with pixel-perfect screenshot comparison + functional checklist

No automated tests for v1 (consistent with existing project patterns)

### Rationale

**Current State**: Reader3 Pro has no pytest suite; features 001 and 002 validated manually

**v1 Testing Plan**:
1. **Visual QA**: Compare rendered UI to WeRead screenshots using browser DevTools
   - Overlay screenshots at 50% opacity to check alignment
   - Measure spacing with DevTools ruler (±2px tolerance)
   - Compare colors with color picker

2. **Functional Checklist** (from spec.md acceptance scenarios):
   - [ ] Create marker annotation with each color
   - [ ] Create wavy/underline annotations
   - [ ] Create note with hover tooltip
   - [ ] Verify persistence after refresh
   - [ ] Test re-anchoring after browser restart
   - [ ] Test overlapping annotations (marker + underline)
   - [ ] Test orphaned annotation handling (delete text, verify hidden)
   - [ ] Test TOC panel search
   - [ ] Test Notes panel navigation
   - [ ] Test Esc key priority (note editor > toolbar > panel)

3. **Performance Profiling**:
   - Chrome DevTools Performance tab
   - Measure annotation rendering time (target <200ms)
   - Measure Notes panel render time (target <300ms)

**Future**: Add pytest suite when project scales beyond 3 features or adds CI/CD

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Jest unit tests | Requires Node.js test runner; over-engineered for vanilla JS |
| Playwright E2E tests | Heavy dependency for localhost-only single-user app |
| pytest with Selenium | Slow; brittle; maintenance burden |

### Implementation Notes

- Document test checklist in `quickstart.md`
- Include screenshots in pull request for visual review
- Profile during Phase 2 implementation, optimize if >200ms

---

## R7: Progressive Enhancement

### Decision

Annotations require JavaScript; no server-side rendering fallback

### Rationale

**Current State**: Reader3 Pro already requires JavaScript for:
- Search result highlighting (feature 001)
- AI panel interactions (feature 002)
- TOC navigation (existing reader.html)

**Justification**:
- Annotation rendering requires DOM manipulation (re-anchoring, `<mark>` insertion)
- Floating toolbar and panels require dynamic show/hide logic
- WeRead-style UI requires client-side state management

**Accessibility**:
- Use semantic HTML (`<mark>` for highlights)
- Add ARIA labels to toolbar buttons
- Ensure keyboard navigation (`Tab`, `Esc`)
- Tooltip content readable by screen readers

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Server-side pre-rendered highlights | Requires storing rendered HTML per user; state explosion |
| Progressive enhancement (JS-optional) | Core feature requires JS; partial experience confusing |

### Implementation Notes

- Add `<noscript>` warning in reader.html: "JavaScript required for annotations"
- Include ARIA attributes in quickstart.md accessibility checklist

---

## Summary of Decisions

| Research Area | Decision | Complexity | Precedent |
|---------------|----------|------------|-----------|
| R1: Re-anchoring | Prefix+quote+suffix text matching | ~100 LOC | Search highlighting (001) |
| R2: Rendering | `<mark>` elements + CSS classes | ~200 LOC | Search highlighting (001) |
| R3: UI Components | Fixed toolbar + fullscreen panels | ~600 LOC JS, ~400 LOC CSS | Existing reader layout |
| R4: Storage | JSON file + atomic writes | ~150 LOC | AI conversations (002) |
| R5: AI Integration | CustomEvent decoupling | ~50 LOC | Event-driven pattern |
| R6: Testing | Manual QA + checklists | N/A | Existing practice |
| R7: Enhancement | JavaScript required | N/A | Existing requirement |

**Total New Code Estimate**: ~1100 LOC (backend + frontend)

**Risk Assessment**: Low - all patterns proven in features 001 and 002

---

## Next Steps (Phase 1)

1. Generate `data-model.md` with detailed `Annotation` dataclass
2. Generate `contracts/notes-api.yaml` with OpenAPI specification
3. Generate `quickstart.md` with development workflow and testing checklist
4. Update agent context via `.specify/scripts/bash/update-agent-context.sh`
5. Re-check constitution compliance after detailed design
