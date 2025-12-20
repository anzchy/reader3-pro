# Implementation Plan: Library UI Reorganization + Bulk Indexing (004)

**Branch**: `004-library-bulk-indexing` | **Date**: 2025-12-19 | **Spec**: [spec.md](./spec.md)

## Summary

Refactor the current `library.html` (single-column + inline styles + cross-book search panel) into a **3-pane Library UI** matching the target screenshot:

- Left sidebar: doc-type counts (All/EPUB/PDF disabled) + Collections
- Center: toolbar (Find books, Add, Sort, Grid/List, Select) + book grid/list with multi-select actions
- Right panel: Dashboard / Chat / Search switcher (bottom-right)

Keep the existing semantic indexing endpoints and integrate them into library-level bulk actions:

- `POST /api/index/{book_id}` (existing)
- `GET /api/index/{book_id}/status` (existing)

Add new capabilities required by the spec:

- Collections persisted to `config/library_collections.json` (gitignored)
- Aggregated stats API `GET /api/library/stats?scope=...&fresh=true`
- Rollback/feature flag: `READER3_LIBRARY_UI=modern|classic`

## Decisions (from clarifications + spec)

- Collections persistence: server-side `config/library_collections.json` (gitignored; schema_version=1; atomic writes).
- PDF filter: visible but disabled (count=0 + tooltip “PDF not supported yet”).
- Stats: computed server-side via `GET /api/library/stats?scope=...` with optional `fresh=true`; short TTL cache allowed (<=5s).
- Stats scope encoding: `all`, `format:epub`, `format:pdf`, `collection:<collection_id>`.
- Chat: single-book only; all-books/collection are disabled/coming soon.
- Right panel v2: tab bar is full-width at the bottom of the right sidebar; right panel can be collapsed via a mid-gutter chevron; Dashboard has no outer frame.
- Lazy status fetch definition: after first render, batches <=20, max 4 concurrent, 5s timeout; failures show `unknown`.
- Rollback: `READER3_LIBRARY_UI=modern|classic` (default: `modern`).

## Technical Approach

### Backend

#### 1) Library UI template switching (rollback)

- Keep a “classic” version of the current library page (so rollback is real).
- Implement:
  - `READER3_LIBRARY_UI=classic` → serve `library_classic.html`
  - `READER3_LIBRARY_UI=modern` (default) → serve the new 3-pane `library.html`

#### 2) Library view context (books + counts)

Extend the `GET /` template context with:

- `books`: list of rendered book cards/rows with:
  - `id`, `title`, `author`
  - `section_count` (`len(book.spine)`)
  - `cover_url` (best-effort; reuse existing `/read/{book_id}/images/{image_name}`)
  - `format` (`epub` for now)
- `counts`: `all`, `epub`, `pdf` (pdf always 0 until PDF pipeline exists)

Index status/chunk counts should be fetched lazily client-side via `GET /api/index/{book_id}/status` (avoid blocking first paint).

#### 3) Collections persistence + endpoints (new)

- Storage: `config/library_collections.json` (gitignored).
- Atomic write: write temp file then rename.
- Name validation per spec (trim, allowed chars, 1–60, case-insensitive uniqueness).
- Missing/invalid file handling:
  - missing file → treat as empty; create on first write
  - invalid JSON/unsupported schema → return error; UI shows “Collections unavailable”

Endpoints (contract-driven; all errors use `{"detail": "..."}`):

- `GET /api/collections`
- `POST /api/collections` (create)
- `PUT /api/collections/{collection_id}` (rename)
- `POST /api/collections/{collection_id}/books` (add/remove membership)
- `DELETE /api/collections/{collection_id}` (delete)

#### 4) Library stats endpoint (new)

- `GET /api/library/stats?scope=...&fresh=true`
  - returns `books_total`, `books_indexed`, `indexed_percent`, `sections_total`, `chunks_total`, `computed_at`
  - validates `scope` encoding; invalid → 400
  - if `scope` is `collection:<id>` and collection missing → 404
  - optional TTL cache per scope (<=5s); `fresh=true` bypasses cache

#### 5) Security and path-safety

- Validate `book_id` values in collections endpoints against known `*_data` folders (same constraints as existing routes).
- HTML-escape collection names at render time; do not allow raw HTML injection.

### Frontend (Library)

#### 1) Structure and styling

- Replace inline styles in `library.html` with `library.css`.
- Build a 3-pane layout using CSS Grid:
  - left: filters + collections
  - center: toolbar + grid/list
  - right: panel container
- Add bottom-right tab switcher (z-index >= 900).

#### 2) Client state and persistence

State:

- `scope` (all/format/collection)
- `viewMode` (`grid|list`) persisted in localStorage (`reader3.library.viewMode`)
- `selectMode` and `selectedBookIds`
- `titleFilter` (center “Find books…”)
- `rightPanelTab` (dashboard/chat/search) persisted optionally (`reader3.library.activeTab`)

If localStorage is unavailable: fall back to defaults without errors.

#### 3) Lazy index status fetch

- After initial render, fetch statuses for visible books in batches <=20.
- Max 4 concurrent requests; 5s timeout; on failure → `unknown`.
- Render status pills and chunk counts consistently across grid/list and dashboard.

#### 4) Selection + bulk actions

- Selection mode reveals checkboxes.
- Selection persists across grid/list toggles.
- Switching scope clears selection.
- Bulk indexing:
  - sequential `POST /api/index/{book_id}`
  - per-book status transitions: `not_indexed|unknown → indexing → indexed|error`
  - continue-on-error; show summary modal listing failures
  - warn before leaving page while indexing
  - no auto-resume after refresh; show “Indexing interrupted” hint

#### 5) Right panel pages

- Dashboard:
  - fetch `/api/library/stats?scope=...` (and `fresh=true` on refresh)
  - display empty/error/loading states
  - optional “Index all in scope” uses the same bulk indexing logic
- Search:
  - move existing cross-book search UI into the Search tab
  - adjust `library-search.js` so it no longer hides the center grid/list
  - keep semantic/hybrid “Index” affordance consistent with index endpoint response shape
- Chat:
  - implement single-book selector + a real chat input + message list
  - reuse the existing backend AI generation endpoints (`/api/ai/question/{book_uuid}?stream=true`) where possible
  - reuse the existing conversation persistence endpoints (`/api/ai/conversations/{book_uuid}/*`) so Library Chat shares `books/{book_id}/ai_conversations/*.json` history with in-book AI
  - Library Chat must be independent from in-book AI UI state and must not reuse the in-book browser IndexedDB store (`reader3_ai_assistant`) for persistence
  - when a user selects a book, load the latest 5 conversation threads (sorted by `created_at` descending) and show them in a History dropdown; selecting one loads messages

#### 5a) Right panel v2 layout rules

- Dashboard/Chat/Search content fills the right sidebar width (no outer “card” wrapper around the whole tab).
- Add a mid-gutter collapse/expand chevron to hide/show the right sidebar; persist optional localStorage key `reader3.library.rightPanelCollapsed`.
- Replace the floating/fixed switcher with a bottom tab bar inside the right sidebar:
  - full width; 3 buttons; each button width = 1/3
  - no outer border/frame
  - pinned to bottom of sidebar (e.g., `position: sticky; bottom: 0;`)

#### 6) Accessibility baseline

- Keyboard reachable controls across panes; logical focus order.
- Modals trap focus and restore focus on close.
- Icon-only buttons have accessible labels (ARIA).
- `Esc` closes modals and exits selection mode.
- Bulk indexing progress is announced via an `aria-live` region (non-blocking).

## Implementation Phases

### Phase 0 — Safe refactor + rollback

- Preserve current library page as `library_classic.html`.
- Add env flag switching (`READER3_LIBRARY_UI`) and serve either classic or modern template.
- Introduce `library.css`; remove inline `<style>` from modern template.

### Phase 1 — 3-pane UI scaffold

- Left sidebar skeleton (All/EPUB/PDF disabled + counts) and Collections placeholder.
- Center toolbar + grid/list toggle + title/author filter + selection mode toggle.
- Right panel container + tab switcher shell.
- Add “Add books” modal (CLI instructions only).

### Phase 2 — Index status + bulk indexing

- Implement lazy status fetch and status pills.
- Implement “Index selected books” with progress + summary.
- Add navigation-away warning during indexing.

### Phase 3 — Collections (API + UI)

- Add collections endpoints + file persistence.
- Implement create, delete (with confirm), add-to-collection.
- Implement collection scope switching and missing-book cleanup.

### Phase 4 — Stats + Search + Chat panel wiring

- Add `/api/library/stats` + caching + `fresh=true`.
- Dashboard UI binds to stats API and handles error/empty/loading states.
- Search tab uses refactored `library-search.js` (no center hide).
- Chat tab provides single-book selector + input + message list; disabled options show tooltips.

### Phase 5 — Right panel v2 polish (layout + collapse)

- Remove outer frame styling from right panel tab content.
- Implement full-width bottom tab bar (3 buttons, 1/3 each).
- Add mid-gutter collapse/expand chevron; persist optional collapsed state.

### Phase 6 — Library Chat history integration

- On book selection, fetch threads via `GET /api/ai/conversations/{book_uuid}` and sort by `created_at` descending to take the latest 5.
- Provide a History dropdown to select a thread; load via `GET /api/ai/conversations/{book_uuid}/{conversation_id}`.
- Persist updates by `PUT /api/ai/conversations/{book_uuid}/{conversation_id}` (shared storage with reader chat).

## Files to Change (expected)

- `src/reader3_app/web/server.py`
- `src/reader3_app/web/templates/library.html`
- `src/reader3_app/web/templates/library_classic.html` (new)
- `src/reader3_app/web/static/library.css` (new)
- `src/reader3_app/web/static/library.js` (new)
- `src/reader3_app/web/static/library-search.js` (refactor)
- `config/library_collections.json` (runtime file; gitignored; created at runtime)
- `.gitignore` (add `config/library_collections.json`)
- `docs/technical-detail/storage-and-data-locations.md` (document collections + stats endpoint cache behavior)
- `docs/technical-detail/technical-detail.md`

## Manual Validation

1. Run server: `uv run reader3-server`
2. Open `http://127.0.0.1:8123`
3. Toggle `READER3_LIBRARY_UI=classic` and confirm classic page still works.
4. Modern UI: verify 3-pane layout renders; grid/list toggle persists; disabled PDF filter has tooltip.
5. Select mode: select multiple books; bulk index; confirm progress + per-book status + summary on failure; leaving page warns.
6. Collections: create, add books, switch scope, delete with confirm; missing book ids show “missing” indicator and can be cleaned up.
7. Dashboard: stats for current scope; refresh uses `fresh=true`; error/empty states render.
8. Search tab: cross-book search works without hiding center shelf; semantic/hybrid mode offers indexing for not-indexed books.
