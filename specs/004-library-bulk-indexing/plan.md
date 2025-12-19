# Implementation Plan: Library Bulk Indexing & Views

**Branch**: `004-library-bulk-indexing` | **Date**: 2025-12-19 | **Spec**: [spec.md](./spec.md)

## Summary

Add a library-level workflow to index books for semantic retrieval (semantic search + AI RAG) via multi-select + “Index selected”, and add a library view toggle (image/list) that displays per-book index status, chunk count, and section count. Reuse the existing indexing endpoints:

- `POST /api/index/{book_id}`
- `GET /api/index/{book_id}/status`

## Technical Approach

### Backend

- Extend the `GET /` library view context to include per-book metadata needed by the UI:
  - `section_count` (spine length)
  - best-effort `cover_url` (reusing existing `/read/{book_id}/images/{image_name}`)
  - optionally `index_status` + `chunk_count` (either server-side or client-side fetch)

**Recommendation**: Keep server-side library render fast; fetch index statuses client-side after page load.

### Frontend (Library)

- Update `src/reader3_app/web/templates/library.html`:
  - Add a small “action bar” above the grid/list:
    - selection mode toggle
    - select all / clear selection
    - index selected
    - view toggle (image/list)
    - progress indicator
  - Render both layouts (or render one container with switchable classes).

- Add new static assets:
  - `src/reader3_app/web/static/library.js`: selection state + bulk indexing + view persistence.
  - `src/reader3_app/web/static/library.css`: layout styles and selected states for image/list views.

### States & UX

- Index status states:
  - `not_indexed` (from status endpoint)
  - `indexing` (client-side transient)
  - `indexed` (from status endpoint or returned from index call)
  - `error` (client-side transient with message)

- Bulk indexing:
  - sequential `POST /api/index/{book_id}` calls
  - per-book UI updates + overall progress label (“Indexing i/n”)
  - continue-on-error per book

### Persistence

- `localStorage` key for view mode, e.g. `reader3.library.viewMode = "image" | "list"`.

## Files to Change

- `src/reader3_app/web/server.py`
- `src/reader3_app/web/templates/library.html`
- `src/reader3_app/web/static/library-search.js` (only if needed to avoid conflicts)
- `src/reader3_app/web/static/library.js` (new)
- `src/reader3_app/web/static/library.css` (new)

## Manual Validation

1. Run server: `uv run reader3-server`
2. Open `http://127.0.0.1:8123`
3. Toggle image/list view; refresh; verify persistence.
4. Select multiple books; click “Index selected”; verify per-book statuses and chunk counts update.
5. Open reader → AI chat; verify RAG retrieval works for indexed books without “not indexed” error.

