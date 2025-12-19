# Tasks: Library Bulk Indexing & Views

**Input**: [spec.md](./spec.md), [plan.md](./plan.md)
**Scope**: Library-only UX for semantic index management + image/list layouts.

## Phase 1 — Data & Rendering

- [ ] T001 Extend `src/reader3_app/web/server.py` library view to include `section_count` and `cover_url` per book (best-effort).
- [ ] T002 Decide status strategy:
  - [ ] Option A (recommended): client-side fetch `GET /api/index/{book_id}/status` after render.
  - [ ] Option B: server-side call `BookVectorIndex(book_id).status()` during render (watch performance).

## Phase 2 — Library UI (Template + CSS)

- [ ] T003 Add `src/reader3_app/web/static/library.css` with:
  - [ ] action bar layout
  - [ ] image view grid + selected states
  - [ ] list view table/rows + selected states
  - [ ] status pills (not_indexed/indexing/indexed/error)
- [ ] T004 Update `src/reader3_app/web/templates/library.html`:
  - [ ] add action bar (select toggle, select all, clear, index selected, view toggle, progress text)
  - [ ] render per-book containers with data attributes (`data-book-id`, `data-sections`, etc.)
  - [ ] show cover (or placeholder) and metadata fields in both views
  - [ ] keep “Read Book” link/button functional

## Phase 3 — Library Behavior (JS)

- [ ] T005 Create `src/reader3_app/web/static/library.js`:
  - [ ] view mode persistence in localStorage (default: image)
  - [ ] selection state (selected set + selected count)
  - [ ] enable/disable bulk actions based on selection
- [ ] T006 Implement per-book status loading:
  - [ ] fetch `GET /api/index/{book_id}/status`
  - [ ] update per-book chunk count + status pill
- [ ] T007 Implement single-book “Index” button (only for `not_indexed`):
  - [ ] call `POST /api/index/{book_id}`
  - [ ] update UI to `indexing` then `indexed` (chunk count) or `error`
- [ ] T008 Implement “Index selected” bulk flow:
  - [ ] sequentially index selected books
  - [ ] overall progress indicator (“Indexing i/n”)
  - [ ] continue on error per book (do not abort the batch)
  - [ ] re-fetch status after each index completes (source of truth)
- [ ] T009 Ensure click targets do not conflict:
  - [ ] selecting a book does not trigger “Read” navigation
  - [ ] clicking buttons/links does not toggle selection accidentally

## Phase 4 — Manual Validation

- [ ] T010 Run manual validation from `specs/004-library-bulk-indexing/plan.md` and confirm acceptance scenarios.

