# Research: Library UI Reorganization + Bulk Indexing (004)

**Feature**: 004-library-bulk-indexing
**Date**: 2025-12-19
**Status**: Complete

## Overview

This document consolidates research for the Library UI rebuild into a 3-pane layout with Collections, bulk indexing, and dashboard/chat/search right-panel switcher.

---

## Research Tasks

### 1. Collections Persistence Strategy

**Decision**: Server-side JSON file (`config/library_collections.json`)

**Rationale**:
- Aligns with constitution principle III (File-Based State Management)
- Simpler than adding database for a single entity
- Enables future migration to DB alongside other persistent entities
- Gitignored to avoid accidental commit of user-specific data

**Alternatives Considered**:
- **Client-only localStorage**: Rejected—data would be lost if user clears browser or accesses from different device
- **SQLite database**: Over-engineering for single entity; adds complexity without proven need (violates principle II)
- **Embedded in book folders**: Rejected—collections are library-level metadata, not book-specific

**Schema Design**:
```json
{
  "schema_version": 1,
  "collections": [
    {
      "id": "uuid-string",
      "name": "Science Fiction",
      "created_at": "2025-12-19T10:00:00Z",
      "book_ids": ["foundation_data", "dune_data"]
    }
  ]
}
```

**Implementation Notes**:
- Use Python's `json` module for read/write
- Atomic writes via write-to-temp + rename pattern
- Add validation on load (schema_version check)
- Update `.gitignore` and `docs/technical-detail/storage-and-data-locations.md`
- Validate collection names (trim, 1–60 chars, allowed chars, case-insensitive uniqueness) and HTML-escape names on render (XSS-safe)

---

### 2. Dashboard Stats Computation

**Decision**: Server-side aggregation via `GET /api/library/stats?scope=...`

**Rationale**:
- Centralized logic ensures consistency across UI components
- Avoids duplicating aggregation logic client-side
- Enables caching if needed (future optimization)
- Simpler client code—just fetch and display

**Alternatives Considered**:
- **Client-side aggregation**: Rejected—requires fetching all book statuses upfront; inefficient for large libraries
- **Background job**: Over-engineering; stats can be computed on-demand fast enough

**Scope Encoding**:
- `all`: All books in library
- `format:epub`: Filter by EPUB format
- `format:pdf`: Filter by PDF format (count=0 for now)
- `collection:<collection_id>`: Books in a specific collection

**Performance Considerations**:
- For MVP: synchronous computation (acceptable for <100 books)
- Server may apply a short in-memory TTL cache (<=5s) per scope if needed
- Add `fresh=true` query param to bypass cache for the “Refresh stats” button

---

### 3. PDF Support Status

**Decision**: Show `PDF` filter disabled with count=0 and tooltip "PDF not supported yet"

**Rationale**:
- Future-proofs UI for when PDF ingestion is added
- Communicates feature roadmap to users
- Minimal implementation cost (just UI state + tooltip)

**Alternatives Considered**:
- **Hide PDF filter entirely**: Rejected—better to show roadmap than hide capabilities
- **Show PDF count as placeholder**: Rejected—misleading; implies partial support

**Implementation**:
- CSS: `opacity: 0.5; cursor: not-allowed`
- Tooltip on hover: "PDF support coming soon"
- Backend returns `format: "epub"` for all current books; `pdf` reserved for future

---

### 4. Chat Scope in Library Panel

**Decision**: Single-book chat only for 004; all-books/collection chat marked "coming soon"

**Rationale**:
- Single-book chat reuses existing reader AI endpoints (minimal new code)
- Multi-book chat requires new RAG pipeline (out of scope for 004)
- Honest communication to users about feature status

**Alternatives Considered**:
- **Implement all-books chat in 004**: Rejected—adds significant complexity; violates principle II (simplicity)
- **Hide chat panel entirely**: Rejected—defeats purpose of unified library UI

**Implementation**:
- Chat panel shows dropdown: `Single book` (enabled), `All books` (disabled), `Collection` (disabled)
- Disabled options show tooltip: "Coming in future update"
- Single-book chat uses existing `/api/ai/question/{book_uuid}` endpoint (streaming when `stream=true`).
- Library Chat must be independent from in-book AI UI state and should not reuse the in-book IndexedDB store (`reader3_ai_assistant`) in v1; prefer `sessionStorage` under `reader3.library.chat.*`.

---

## Right Panel v2 (UX Updates)

**Decision**: Update right panel layout to match the latest UI requirements.

**Requirements summary**:
- Dashboard/Chat/Search content fills the right sidebar width with no outer “card” wrapper.
- Replace floating switcher with a full-width bottom tab bar (3 buttons; each 1/3 of sidebar width; no outer border).
- Add a mid-gutter chevron to collapse/expand the right sidebar; optionally persist `reader3.library.rightPanelCollapsed`.

---

### 4a. Rollback Strategy (Library UI)

**Decision**: Provide a rollback switch for the Library UI via environment variable.

**Rationale**:
- Enables incremental refactor without losing access to the working library page
- Provides a simple escape hatch if the new layout has regressions

**Implementation**:
- `READER3_LIBRARY_UI=modern|classic` (default: `modern`)
- `classic` serves the pre-004 single-column library UI

### 5. Search Panel Integration

**Decision**: Adapt existing `library-search.js` to render inside right-panel Search tab

**Rationale**:
- Reuses working cross-book search implementation
- Avoids rewriting tested code
- Current search UI is good enough; doesn't need pixel-perfect redesign

**Refactor Strategy**:
- Extract search results rendering into function
- Change search results container to mount inside right-panel `#search-tab`
- Remove current behavior that hides `#library-book-grid` (keep center visible)
- Preserve all search modes (keyword/semantic/hybrid) and per-book index affordance

**Alternatives Considered**:
- **Rewrite search UI from scratch**: Rejected—unnecessary duplication
- **Keep search above book grid**: Rejected—doesn't match target 3-pane layout

---

### 6. "Add Books" MVP Approach

**Decision**: Modal with CLI instructions for MVP; upload flow deferred

**Rationale**:
- Current workflow (`uv run reader3 book.epub`) works and is documented
- File upload + server-side processing adds complexity without user demand
- Keeps 004 focused on library UI + indexing (not ingestion)

**Modal Content**:
```
Add Books to Library

1. Place your EPUB files in the books/ directory
2. Run: uv run reader3 path/to/book.epub
3. Refresh this page

Future versions will support drag-and-drop upload.
```

**Follow-up Task** (out of scope for 004):
- Add `/api/upload` endpoint accepting EPUB multipart/form-data
- Call `reader3.py` processing logic server-side
- Show processing progress (requires async job queue)

---

### 7. Grid/List View Toggle Persistence

**Decision**: `localStorage` with key `reader3.library.viewMode`

**Rationale**:
- Simple, proven pattern for client-only UI preferences
- No need for server-side persistence of view mode
- Already used successfully in reader3 for other preferences

**Implementation**:
```javascript
const VIEW_MODE_KEY = 'reader3.library.viewMode';
const DEFAULT_VIEW = 'grid';

function getViewMode() {
  return localStorage.getItem(VIEW_MODE_KEY) || DEFAULT_VIEW;
}

function setViewMode(mode) {
  localStorage.setItem(VIEW_MODE_KEY, mode);
  applyViewMode(mode);
}
```

---

### 8. Multi-Select UX Pattern

**Decision**: Explicit selection mode with checkbox/click toggle

**Rationale**:
- Matches common pattern in file managers, Gmail, etc.
- Clear affordance (checkboxes appear when mode enabled)
- Avoids ambiguity with navigation clicks

**Interaction Flow**:
1. User clicks "Select" toggle button in toolbar
2. Checkboxes appear on all book cards/rows
3. Clicking book selects/deselects (does NOT navigate)
4. Actions appear: "Add to collection", "Index selected books"
5. Click "Select" again or action completes → exit selection mode

**Alternatives Considered**:
- **Drag-marquee selection**: Rejected—complex to implement; minimal benefit over checkboxes
- **Always show checkboxes**: Rejected—clutters UI when not in selection mode

---

### 9. Bulk Indexing UX

**Decision**: Sequential API calls with per-book progress updates

**Rationale**:
- Simple implementation (no backend queueing needed)
- Frontend can show clear progress ("Indexing 3/10...")
- Continue-on-error naturally handled with try/catch per book

**UI States**:
- **Before**: Button shows "Index N books"
- **During**: Button disabled, progress label updates ("Indexing 3/10")
- **After success**: Status pills update to "indexed", chunk counts refresh
- **After partial failure**: Show error summary modal listing failed books

**Error Handling**:
```javascript
async function indexSelectedBooks(bookIds) {
  let completed = 0;
  const errors = [];

  for (const bookId of bookIds) {
    updateProgress(`Indexing ${completed + 1}/${bookIds.length}`);
    try {
      await indexBook(bookId);
      updateBookStatus(bookId, 'indexed');
    } catch (err) {
      errors.push({ bookId, error: err.message });
      updateBookStatus(bookId, 'error');
    }
    completed++;
  }

  if (errors.length > 0) {
    showErrorModal(errors);
  }
}
```

**Lazy status fetch definition**:
- Start fetching `GET /api/index/{book_id}/status` only after the initial book list is rendered
- Fetch in batches <=20 with max 4 concurrent requests
- 5s timeout; failures show `unknown` without blocking the UI

---

### 10. Right-Panel Tab Switcher

**Decision**: Bottom-right tab bar with 3 tabs (Dashboard / Chat / Search)

**Rationale**:
- Matches screenshot placement
- Common pattern in tools with secondary panels (VSCode, browser DevTools)
- Keeps primary interaction (book browsing) in center focus

**Persistence**:
- Optional: persist active tab in `localStorage` (`reader3.library.activeTab`)
- Default tab: Dashboard (shows useful stats on first visit)

**Implementation**:
- CSS: fixed position tab bar at `bottom: 0; right: 0` inside right panel
- JavaScript: simple state toggle + show/hide panel content
- Accessibility: keyboard navigation (Tab key), ARIA labels

---

## Technology Stack Confirmation

### Frontend
- **Vanilla JavaScript ES6+**: No framework; keeps codebase simple (constitution principle II)
- **CSS Grid + Flexbox**: Layout primitives for 3-pane structure
- **localStorage API**: View mode + tab persistence

### Backend
- **FastAPI 0.121.2+**: Existing stack; add new routes for collections + stats
- **Python 3.10+ dataclasses**: Collections schema + stats models
- **JSON serialization**: `config/library_collections.json` persistence

### New Dependencies
- **None**: All features implementable with existing stack

---

## Best Practices

### 1. State Management

**Pattern**: Single source of truth per concern
- **Server state** (collections, book metadata): Fetched via API, cached client-side
- **UI state** (view mode, selection, active tab): localStorage + in-memory
- **Transient state** (indexing progress): In-memory only

**Anti-pattern to avoid**: Duplicating state across localStorage and server

### 2. API Design

**RESTful principles**:
- Collections: `/api/collections` (list), `POST /api/collections` (create), `PUT /api/collections/{id}` (update)
- Stats: `GET /api/library/stats?scope=...` (read-only, idempotent)
- Indexing: `POST /api/index/{book_id}` (idempotent—re-indexing safe)

**Error responses**: Standard HTTP status codes (400, 404, 500) with JSON error bodies

### 3. Progressive Enhancement

**Phases**:
1. **Phase 0**: Refactor to 3-pane skeleton (no new features)
2. **Phase 1**: Add basic UI (toggles, filters) without backend integration
3. **Phase 2**: Wire bulk indexing + status pills
4. **Phase 3**: Add collections endpoints + UI
5. **Phase 4**: Complete right-panel pages (Dashboard, Chat, Search)

**Benefit**: Each phase is testable; can pause development without broken UI

---

## Complexity Tracking

| Component | Complexity | Justification | Alternatives |
|-----------|-----------|---------------|--------------|
| Collections persistence | Medium | Adds new JSON file management; justified by user need to organize books | None—localStorage insufficient for multi-device |
| 3-pane layout | Medium | CSS Grid layout; justified by target UI requirements | Could keep simple 1-column layout (rejected—doesn't meet spec) |
| Right-panel tabs | Low | Simple show/hide toggle; no routing needed | None |
| Bulk indexing | Low | Sequential fetch loop; no concurrency complexity | Parallel requests (rejected—sequential simpler, backend synchronous) |

**Total added complexity**: Within acceptable bounds per constitution principle II (Simplicity Over Engineering). All complexity justified by spec requirements; no speculative features.

---

## Open Questions (Resolved)

1. **Q**: Should collections be per-user or global?
   **A**: Not applicable for MVP (single-user local deployment). Revisit when/if multi-user support added.

2. **Q**: How to handle book renames (folder name changes)?
   **A**: Out of scope for 004. Collections store `book_id` (folder name); if user renames folder, collection breaks. Document as known limitation; fix when book UUID system added.

3. **Q**: Should stats endpoint cache results?
   **A**: MVP may use a short TTL cache (<=5s) per scope; `fresh=true` bypasses cache for the refresh button.

---

## Summary

All research complete. Key decisions documented. No blockers to Phase 1 (Design & Contracts).

**Next Steps**:
1. Generate `data-model.md` (entities: Collection, LibraryStats, BookMetadata)
2. Generate API contracts (`contracts/library-api.yaml`)
3. Generate `quickstart.md` (developer setup + testing guide)
4. Update agent context with new technologies (none—reusing existing stack)
