# Implementation Tasks: Library UI Reorganization + Bulk Indexing (004)

**Feature Branch**: `004-library-bulk-indexing`
**Date**: 2025-12-19
**Status**: Ready for Implementation

**Total Tasks**: 107
**Estimated MVP Scope**: Phase 0-3 + Phase 6 + Phase 8 (security/a11y)

---

## Task Index

- [Phase 0: Setup & Configuration](#phase-0-setup--configuration) (6 tasks)
- [Phase 1: Baseline Refactor + Rollback](#phase-1-baseline-refactor--rollback) (9 tasks)
- [Phase 2: 3-Pane UI Scaffold](#phase-2-3-pane-ui-scaffold) (17 tasks)
- [Phase 3: Index Status + Bulk Indexing](#phase-3-index-status--bulk-indexing) (27 tasks) - **US1**
- [Phase 4: Collections API + UI](#phase-4-collections-api--ui) (17 tasks) - **US3**
- [Phase 5: Dashboard Stats](#phase-5-dashboard-stats) (7 tasks) - **US4**
- [Phase 6: Grid/List View Toggle](#phase-6-gridlist-view-toggle) (5 tasks) - **US2**
- [Phase 7: Search & Chat Panels](#phase-7-search--chat-panels) (4 tasks) - **US4**
- [Documentation Updates](#documentation-updates) (3 tasks)

---

## Dependency Graph

```
Phase 0 (Setup)
    ↓
Phase 1 (Baseline Refactor + Rollback)
    ↓
Phase 2 (3-Pane Scaffold)
    ├→ Phase 3 (Bulk Indexing) [US1]
    ├→ Phase 4 (Collections) [US3]
    ├→ Phase 5 (Dashboard Stats) [US4]
    ├→ Phase 6 (View Toggle) [US2]
    └→ Phase 7 (Search/Chat) [US4]

Notes:
- Phases 3-7 can proceed in parallel after Phase 2 completes
- Phase 6 (View Toggle) has minimal dependencies and can be developed concurrently with Phase 3
```

---

## Phase 0: Setup & Configuration

**Goal**: Prepare filesystem and configuration for collections and UI mode switching.

- [x] T001 [P1] Create repo-root `config/` directory if it doesn't exist (config/)
- [x] T002 [P1] Add `config/library_collections.json` to `.gitignore` (.gitignore)
- [x] T003 [P1] Read `READER3_LIBRARY_UI=modern|classic` (default `modern`) in the library route and switch templates accordingly (src/reader3_app/web/server.py)
- [x] T004 [P1] Verify existing `/api/index/{book_id}` and `/api/index/{book_id}/status` endpoints work correctly (manual test)
- [x] T005 [P1] Verify `section_count` is derived from `len(book.spine)` (src/reader3_app/reader3.py)
- [x] T006 [P1] Verify cover images are served via `/read/{book_id}/images/{image_name}` (manual test)

---

## Phase 1: Baseline Refactor + Rollback

**Goal**: Split library UI into modern/classic versions without breaking existing functionality.

- [x] T007 [P1] Copy current `templates/library.html` to `templates/library_classic.html` (src/reader3_app/web/templates/)
- [x] T008 [P1] Update library route to switch templates based on `READER3_LIBRARY_UI` env var (src/reader3_app/web/server.py)
- [x] T009 [P1] Create empty `static/library.css` file (src/reader3_app/web/static/)
- [x] T010 [P1] Extract inline `<style>` from `library.html` to `library.css` (src/reader3_app/web/static/library.css)
- [x] T011 [P1] Link `library.css` in `library.html` `<head>` (src/reader3_app/web/templates/library.html)
- [x] T012 [P1] Test rollback: `READER3_LIBRARY_UI=classic` serves classic page correctly (manual test)
- [x] T013 [P1] Test modern: `READER3_LIBRARY_UI=modern` serves new page with external CSS (manual test)
- [x] T014 [P1] Verify book grid still renders and clicking books navigates to reader (manual test)
- [x] T015 [P1] Document rollback toggle in quickstart.md (specs/004-library-bulk-indexing/quickstart.md)

---

## Phase 2: 3-Pane UI Scaffold

**Goal**: Build the 3-pane layout skeleton with toolbar and empty right panel.

### Left Sidebar (Filters + Collections Placeholder)

- [ ] T016 [P1] Add 3-pane CSS Grid layout to `library.css` (left: 240px, right: 320px, center: flex) (src/reader3_app/web/static/library.css)
- [ ] T017 [P1] Implement left sidebar structure in `library.html` with filters section (src/reader3_app/web/templates/library.html)
- [ ] T018 [P1] Add "All Books" filter with count badge (src/reader3_app/web/templates/library.html)
- [ ] T019 [P1] Add "EPUB" filter with count badge (src/reader3_app/web/templates/library.html)
- [ ] T020 [P1] Add "PDF" filter disabled with count=0 and tooltip "PDF not supported yet" (src/reader3_app/web/templates/library.html)
- [ ] T021 [P1] Add Collections section placeholder with "+" create button (src/reader3_app/web/templates/library.html)
- [ ] T022 [P1] Extend library view context to include `counts: {all, epub, pdf}` (src/reader3_app/web/server.py)

### Center Toolbar + Grid

- [ ] T023 [P1] Add center toolbar structure with search box "Find books…" (src/reader3_app/web/templates/library.html)
- [ ] T024 [P1] Add "Add books" button opening modal with CLI instructions (src/reader3_app/web/templates/library.html)
- [ ] T025 [P1] Add Sort (A→Z) button (src/reader3_app/web/templates/library.html)
- [ ] T026 [P1] Add Grid/List toggle button (src/reader3_app/web/templates/library.html)
- [ ] T027 [P1] Add "Select" mode toggle button (src/reader3_app/web/templates/library.html)
- [ ] T028 [P1] Move existing book grid into center pane (src/reader3_app/web/templates/library.html)
- [ ] T029 [P1] Extend book context to include `section_count`, `cover_url`, `format` (src/reader3_app/web/server.py)

### Right Panel Container

- [ ] T030 [P1] Add right panel container structure (src/reader3_app/web/templates/library.html)
- [ ] T031 [P1] Add bottom-right tab switcher with Dashboard/Chat/Search tabs (src/reader3_app/web/templates/library.html)
- [ ] T032 [P1] Style tab switcher with fixed position (right: 20px, bottom: 20px, z-index: 900) (src/reader3_app/web/static/library.css)

---

## Phase 3: Index Status + Bulk Indexing

**Goal**: Enable multi-select and bulk indexing with per-book status display. (**User Story 1**)

### Client State Management

- [ ] T033 [P1] [US1] Create `static/library.js` with module structure (src/reader3_app/web/static/library.js)
- [ ] T034 [P1] [US1] Implement client state object (scope, viewMode, selectMode, selectedBookIds, titleFilter) (src/reader3_app/web/static/library.js)
- [ ] T035 [P1] [US1] Implement selection mode toggle (show/hide checkboxes, update UI) (src/reader3_app/web/static/library.js)
- [ ] T036 [P1] [US1] Implement "Select all" and "Clear selection" actions (src/reader3_app/web/static/library.js)
- [ ] T037 [P1] [US1] Implement selected count display in toolbar (src/reader3_app/web/static/library.js)
- [ ] T038 [P1] [US1] Add selection persistence across grid/list toggle (src/reader3_app/web/static/library.js)
- [ ] T039 [P1] [US1] Implement scope switching clears selection logic (src/reader3_app/web/static/library.js)

### Lazy Index Status Fetch

- [ ] T040 [P1] [US1] Implement lazy status fetch after initial render (src/reader3_app/web/static/library.js)
- [ ] T041 [P1] [US1] Batch status requests (<=20 book_ids per batch, max 4 concurrent) (src/reader3_app/web/static/library.js)
- [ ] T042 [P1] [US1] Add 5s timeout per status request; mark failures as `unknown` (src/reader3_app/web/static/library.js)
- [ ] T043 [P1] [US1] Render status pills in grid view (not_indexed/indexed/unknown/indexing/error) (src/reader3_app/web/templates/library.html)
- [ ] T044 [P1] [US1] Render chunk counts in grid view when `status=indexed` (src/reader3_app/web/templates/library.html)
- [ ] T045 [P1] [US1] Add loading state "Loading…" for status pills before fetch completes (src/reader3_app/web/static/library.js)

### Bulk Indexing UI

- [ ] T046 [P1] [US1] Add "Index selected books" button (disabled when no selection) (src/reader3_app/web/templates/library.html)
- [ ] T047 [P1] [US1] Implement sequential bulk indexing loop (one `POST /api/index/{book_id}` at a time) (src/reader3_app/web/static/library.js)
- [ ] T048 [P1] [US1] Implement per-book state transitions (not_indexed → indexing → indexed/error) (src/reader3_app/web/static/library.js)
- [ ] T049 [P1] [US1] Add overall progress indicator "Indexing 2/5…" in toolbar (src/reader3_app/web/static/library.js)
- [ ] T050 [P1] [US1] Implement continue-on-error for bulk indexing (src/reader3_app/web/static/library.js)
- [ ] T051 [P1] [US1] Collect indexing errors and show summary modal after batch completes (src/reader3_app/web/static/library.js)
- [ ] T052 [P1] [US1] Add navigation-away warning during active bulk indexing (beforeunload handler) (src/reader3_app/web/static/library.js)
- [ ] T053 [P1] [US1] Add "Indexing interrupted" hint when page loads after interrupted indexing (src/reader3_app/web/static/library.js)
- [ ] T054 [P1] [US1] Update status pills in real-time as indexing progresses (src/reader3_app/web/static/library.js)

### Backend Support

- [ ] T055 [P1] [US1] Verify `POST /api/index/{book_id}` accepts `{"force_reindex": bool}` and returns IndexMeta (src/reader3_app/web/server.py)
- [ ] T056 [P1] [US1] Verify `GET /api/index/{book_id}/status` returns `{status, chunk_count, model_name, indexed_at?}` (src/reader3_app/web/server.py)
- [ ] T057 [P1] [US1] Add error handling for missing semantic dependencies (return 400 with guidance) (src/reader3_app/web/server.py)
- [ ] T058 [P1] [US1] Test bulk indexing with mix of indexed/not-indexed books (manual test)
- [ ] T059 [P1] [US1] Test error handling when one book fails during bulk indexing (manual test)

---

## Phase 4: Collections API + UI

**Goal**: Allow users to create collections and add books to them. (**User Story 3**)

### Collections Service Module

- [ ] T060 [P1] [US3] Create `src/reader3_app/collections_service.py` module (src/reader3_app/collections_service.py)
- [ ] T061 [P1] [US3] Implement Collection dataclass (id: UUID, name: str, created_at: str, book_ids: List[str]) (src/reader3_app/collections_service.py)
- [ ] T062 [P1] [US3] Implement atomic write-to-temp + rename for `config/library_collections.json` (src/reader3_app/collections_service.py)
- [ ] T063 [P1] [US3] Implement collection name validation (1-60 chars, allowed chars, case-insensitive uniqueness) (src/reader3_app/collections_service.py)
- [ ] T064 [P1] [US3] Implement missing/invalid file handling (treat missing as empty; error on invalid JSON) (src/reader3_app/collections_service.py)

### Collections API Endpoints

- [ ] T065 [P1] [US3] Implement `GET /api/collections` (list all) (src/reader3_app/web/server.py)
- [ ] T066 [P1] [US3] Implement `POST /api/collections` (create with name validation) (src/reader3_app/web/server.py)
- [ ] T067 [P1] [US3] Implement `GET /api/collections/{collection_id}` (get single collection) (src/reader3_app/web/server.py)
- [ ] T068 [P1] [US3] Implement `PUT /api/collections/{collection_id}` (rename) (src/reader3_app/web/server.py)
- [ ] T069 [P1] [US3] Implement `POST /api/collections/{collection_id}/books` (add/remove books) (src/reader3_app/web/server.py)
- [ ] T070 [P1] [US3] Implement `DELETE /api/collections/{collection_id}` (src/reader3_app/web/server.py)
- [ ] T071 [P1] [US3] Add collections to library view context (src/reader3_app/web/server.py)

### Collections UI

- [ ] T072 [P1] [US3] Render collections list in left sidebar sorted A→Z with counts (src/reader3_app/web/templates/library.html)
- [ ] T073 [P1] [US3] Implement "Create collection" modal with name input and validation (src/reader3_app/web/static/library.js)
- [ ] T074 [P1] [US3] Implement "Add to collection" button in selection mode (src/reader3_app/web/static/library.js)
- [ ] T075 [P1] [US3] Implement collection scope switching (filter center grid to show only collection books) (src/reader3_app/web/static/library.js)
- [ ] T076 [P1] [US3] Implement delete collection with confirmation dialog (src/reader3_app/web/static/library.js)
- [ ] T077 [P1] [US3] Add orphaned book cleanup UI (show "1 missing" indicator and cleanup button) (src/reader3_app/web/static/library.js)
- [ ] T078 [P1] [US3] Implement active collection scope resets to "all" when deleted (src/reader3_app/web/static/library.js)
- [ ] T079 [P1] [US3] Test creating collection, adding books, switching scope, and deleting (manual test)

---

## Phase 5: Dashboard Stats

**Goal**: Implement aggregated statistics for current scope. (**User Story 4 - Dashboard**)

### Stats API

- [ ] T080 [P2] [US4] Create LibraryStats dataclass (scope, books_total, books_indexed, indexed_percent, sections_total, chunks_total, computed_at) (src/reader3_app/web/server.py)
- [ ] T081 [P2] [US4] Implement `GET /api/library/stats?scope=...&fresh=true` endpoint (src/reader3_app/web/server.py)
- [ ] T082 [P2] [US4] Implement scope validation (all, format:epub, format:pdf, collection:<uuid>) (src/reader3_app/web/server.py)
- [ ] T083 [P2] [US4] Implement stats computation logic (filter books by scope, aggregate counts) (src/reader3_app/web/server.py)
- [ ] T084 [P2] [US4] Add optional TTL cache (<=5s) per scope with `fresh=true` bypass (src/reader3_app/web/server.py)

### Dashboard UI

- [ ] T085 [P2] [US4] Implement Dashboard tab panel rendering stats cards (src/reader3_app/web/templates/library.html)
- [ ] T086 [P2] [US4] Fetch stats on tab switch and scope change (src/reader3_app/web/static/library.js)
- [ ] T087 [P2] [US4] Add "Refresh stats" button using `fresh=true` parameter (src/reader3_app/web/static/library.js)
- [ ] T088 [P2] [US4] Implement empty state display (0 books, "No books in this scope") (src/reader3_app/web/static/library.js)
- [ ] T089 [P2] [US4] Implement error state display with retry action (src/reader3_app/web/static/library.js)

---

## Phase 6: Grid/List View Toggle

**Goal**: Switch between image grid and list view with persistence. (**User Story 2**)

- [ ] T090 [P1] [US2] Implement list view HTML structure (table with columns: Title, Author, Chunks, Sections, Status, Read) (src/reader3_app/web/templates/library.html)
- [ ] T091 [P1] [US2] Add view mode toggle handler in `library.js` (src/reader3_app/web/static/library.js)
- [ ] T092 [P1] [US2] Implement localStorage persistence for `reader3.library.viewMode` (grid|list) (src/reader3_app/web/static/library.js)
- [ ] T093 [P1] [US2] Restore view mode on page load with fallback to grid (src/reader3_app/web/static/library.js)
- [ ] T094 [P1] [US2] Test view toggle persists after refresh and selection remains unchanged (manual test)

---

## Phase 7: Search & Chat Panels

**Goal**: Complete right panel pages with Search and Chat tabs. (**User Story 4 - Search & Chat**)

### Search Tab

- [ ] T095 [P2] [US4] Refactor `library-search.js` to render results inside right panel `#search-tab` (src/reader3_app/web/static/library-search.js)
- [ ] T096 [P2] [US4] Remove behavior that hides center grid when showing search results (src/reader3_app/web/static/library-search.js)

### Chat Tab

- [ ] T097 [P2] [US4] Implement Chat tab with single-book dropdown selector (src/reader3_app/web/templates/library.html)
- [ ] T098 [P2] [US4] Disable "All books" and "Collection" options with tooltips "Coming soon" (src/reader3_app/web/templates/library.html)

---

## Documentation Updates

- [ ] T099 [P3] Update `CLAUDE.md` to add 004 to Active Technologies section (CLAUDE.md)
- [ ] T100 [P3] Update `docs/technical-detail/storage-and-data-locations.md` to document `config/library_collections.json` (docs/technical-detail/storage-and-data-locations.md)
- [ ] T101 [P3] Update `docs/technical-detail/technical-detail.md` to add Collections architecture overview (docs/technical-detail/technical-detail.md)
- [ ] T102 [P3] Verify `contracts/library-api.yaml` matches the implemented endpoints, request/response schemas, and status codes (specs/004-library-bulk-indexing/contracts/library-api.yaml)

---

## Phase 8: Security & Accessibility Requirements

**Goal**: Ensure explicit coverage for FR-051/FR-052, FR-038, FR-047/FR-050, and NFR-004.

### Security (XSS + Path Safety)

- [ ] T103 [P1] [SEC] Ensure collection names are HTML-escaped at render time and validated server-side (length/allowed chars/uniqueness) (src/reader3_app/web/templates/library.html, src/reader3_app/web/server.py, src/reader3_app/collections_service.py)
- [ ] T104 [P1] [SEC] Validate `book_id` inputs for collection membership operations using the same path-safety constraints as other book routes (reject separators; allow only known `*_data` folders) (src/reader3_app/web/server.py, src/reader3_app/collections_service.py)
- [ ] T105 [P2] [SEC] Standardize new API error responses to FastAPI `{"detail": "..."}` across collections + stats endpoints (src/reader3_app/web/server.py)

### Accessibility (Keyboard + Focus + Announcements)

- [ ] T106 [P1] [A11Y] Ensure all interactive controls are keyboard reachable and not implemented as click-only `<div>`/`<span>` (src/reader3_app/web/templates/library.html)
- [ ] T107 [P1] [A11Y] Implement modal focus management: trap focus while open, restore focus on close, and `Esc` closes the active modal (src/reader3_app/web/static/library.js)
- [ ] T108 [P1] [A11Y] Add an `aria-live` region for bulk indexing progress and ensure status changes are announced non-intrusively (src/reader3_app/web/templates/library.html, src/reader3_app/web/static/library.js)
- [ ] T109 [P2] [A11Y] Ensure disabled “Coming soon” chat options are not focusable and have accessible tooltip text (src/reader3_app/web/templates/library.html)
- [ ] T110 [P2] [A11Y] Ensure icon-only buttons have accessible labels (ARIA) (src/reader3_app/web/templates/library.html)

---

## Parallel Execution Opportunities

The following task groups can be worked on in parallel after Phase 2 completes:

**Group A** (Bulk Indexing):
- T033-T059 (Phase 3)

**Group B** (Collections):
- T060-T079 (Phase 4)

**Group C** (Dashboard):
- T080-T089 (Phase 5)

**Group D** (View Toggle):
- T090-T094 (Phase 6)

**Group E** (Search/Chat):
- T095-T098 (Phase 7)

**Recommendation**: Prioritize Group A (US1) and Group D (US2) for MVP; defer Groups B, C, and E to post-MVP.

---

## Testing & Validation

### Manual QA Checklist

After implementation, verify all acceptance scenarios from spec.md:

**US1 - Bulk Indexing**:
- [ ] Selection mode shows checkboxes and selected count
- [ ] "Index selected" shows progress "Indexing 2/5…" and per-book states
- [ ] Failures for individual books don't abort batch
- [ ] Navigation-away warning appears during indexing
- [ ] Interrupted indexing shows hint on reload

**US2 - View Toggle**:
- [ ] Grid/List toggle preserves same book set
- [ ] Selection remains unchanged across toggle
- [ ] View mode persists after page refresh

**US3 - Collections**:
- [ ] Creating collection adds it to left sidebar sorted A→Z
- [ ] Adding books updates collection count
- [ ] Switching to collection scope filters center grid
- [ ] Duplicate collection name shows error

**US4 - Dashboard/Search/Chat**:
- [ ] Dashboard stats match actual library state
- [ ] Search results render without hiding center grid
- [ ] Chat single-book selector works; all-books/collection disabled

### API Contract Tests

Run curl commands from quickstart.md:
- [ ] `GET /api/collections`
- [ ] `POST /api/collections`
- [ ] `GET /api/library/stats?scope=all`
- [ ] `POST /api/index/{book_id}`
- [ ] `GET /api/index/{book_id}/status`

### Browser DevTools Tests

Test localStorage persistence:
- [ ] `reader3.library.viewMode` persists across reload
- [ ] Selection count updates correctly

---

## Definition of Done

A task is complete when:

1. Code is written and follows constitution principles (Data Structures First, Simplicity, Explicit Over Implicit)
2. Manual test passes (for tasks with [manual test] marker)
3. No regressions in existing functionality (verify with rollback to classic UI)
4. XSS prevention applied (HTML-escape collection names, search terms)
5. Error handling implemented (graceful degradation for localStorage/collections failures)

---

## MVP Scope Recommendation

**Minimum viable implementation** (59 tasks):
- Phase 0: Setup (T001-T006)
- Phase 1: Baseline Refactor (T007-T015)
- Phase 2: 3-Pane Scaffold (T016-T032)
- Phase 3: Bulk Indexing (T033-T059)
- Phase 6: View Toggle (T090-T094)

**Defer to post-MVP**:
- Phase 4: Collections (T060-T079) - P1 but can ship incrementally
- Phase 5: Dashboard Stats (T080-T089) - P2
- Phase 7: Search/Chat Panels (T095-T098) - P2

This allows shipping bulk indexing and view toggle (core user pain points) quickly, then iterating on collections and right panel features.

---

## Summary

**Total tasks**: 107
**MVP tasks**: 59 (Phases 0-3 + Phase 6)
**Post-MVP tasks**: 48 (Phases 4-5, 7, documentation)

**Priority order for implementation**:
1. Phase 0-1: Setup and rollback (critical foundation)
2. Phase 2: 3-pane scaffold (enables all parallel work)
3. Phase 3 + Phase 6: Bulk indexing + view toggle (core user stories)
4. Phase 4: Collections (enhance organization)
5. Phase 5 + Phase 7: Dashboard/Search/Chat (polish and analytics)
6. Documentation updates (final step)
