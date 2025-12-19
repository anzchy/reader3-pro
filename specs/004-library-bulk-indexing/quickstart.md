# Quickstart: Library UI Reorganization + Bulk Indexing (004)

**Feature**: 004-library-bulk-indexing
**Branch**: `004-library-bulk-indexing`
**Date**: 2025-12-19

## Overview

This guide helps developers set up, develop, and test the redesigned library UI with Collections, bulk indexing, and dashboard/chat/search right-panel switcher.

---

## Prerequisites

- Python 3.10+
- `uv` package manager installed
- At least 2-3 processed EPUB books in `books/*_data/` directories
- Existing Reader3 Pro setup (if starting fresh, see main README.md)

---

## Initial Setup

### 1. Create Feature Branch

```bash
cd /path/to/reader3-pro-wt/003
git checkout -b 004-library-bulk-indexing
```

### 2. Verify Existing Functionality

Before making changes, confirm the current library page works:

```bash
# Start server
uv run reader3-server

# Open http://127.0.0.1:8123
# Verify: book grid renders, clicking a book opens reader
```

### 2a. Rollback Toggle (Library UI)

The redesigned Library UI supports rollback to the classic page:

```bash
# Modern (default)
READER3_LIBRARY_UI=modern uv run reader3-server

# Classic (pre-004)
READER3_LIBRARY_UI=classic uv run reader3-server
```

### 3. Create Test Data (if needed)

If you don't have enough books:

```bash
# Process some EPUBs
uv run reader3 books/sample1.epub
uv run reader3 books/sample2.epub
uv run reader3 books/sample3.epub

# Refresh library page to see new books
```

### 4. Set Up Collections Storage

```bash
# Create config directory if it doesn't exist
mkdir -p config

# Add to .gitignore
echo "config/library_collections.json" >> .gitignore
```

**Collection name rules (v1)**:
- 1–60 characters after trimming
- allowed: letters, numbers, space, `_`, `-`, `.`, `&`, `()`
- uniqueness is case-insensitive

---

## Development Workflow

### Phase 0: Baseline Refactor

**Goal**: Split library UI into 3-pane skeleton without breaking existing functionality.

**Tasks**:
1. Create `src/reader3_app/web/static/library.css`
2. Refactor `templates/library.html` into 3-pane layout:
   - Left sidebar (empty for now)
   - Center grid (existing book list)
   - Right panel (empty for now)
3. Move inline `<style>` from `library.html` to `library.css`

**Test**:
```bash
# Restart server
uv run reader3-server

# Verify:
# - Library page still loads
# - Book grid still renders
# - Clicking books still works
```

---

### Phase 1: Library UI Scaffolding

**Goal**: Add toolbar, filters, and grid/list toggle.

**Tasks**:
1. Add left sidebar filters (All Books / EPUB / PDF)
2. Add center toolbar (search box, Add, Sort, Grid/List, Select)
3. Implement grid/list view toggle with localStorage persistence
4. Add "Add books" modal with CLI instructions

**Test**:
```bash
# Restart server
uv run reader3-server

# Verify:
# - Left filters show correct counts
# - Grid/List toggle works and persists after refresh
# - "Add books" modal opens and shows instructions
# - Title/author search filters books in real-time
```

**Test Data**:
- Have at least 5 books with different authors/titles for filtering tests

---

### Phase 2: Bulk Indexing + Status Pills

**Goal**: Enable multi-select and bulk indexing with per-book status display.

**Backend Tasks**:
1. Verify existing endpoints work:
   - `POST /api/index/{book_id}`
   - `GET /api/index/{book_id}/status`
2. Extend library view context for rendering:
   - `section_count` + `cover_url` + `format` per book
   - index status/chunk counts are fetched client-side via `GET /api/index/{book_id}/status` (lazy fetch)

**Frontend Tasks**:
1. Create `src/reader3_app/web/static/library.js`
2. Implement selection mode (checkboxes, selected count, actions)
3. Add "Index selected books" button
4. Fetch and display per-book index status pills
5. Show indexing progress during bulk operation

**Test**:
```bash
# Start with mix of indexed/not-indexed books
# (Index 1-2 books manually first to create test data)

uv run reader3-server

# Verify:
# - Status pills show "indexed" vs "not indexed" correctly
# - Select mode enables checkboxes
# - Selecting books shows "Index N selected" button
# - Clicking index button shows progress ("Indexing 1/3...")
# - Per-book status updates in real-time
# - Chunk counts display correctly for indexed books
# - Errors for individual books don't abort the batch
```

**Manual Test Script**:
```bash
# Test bulk indexing error handling
# 1. Select 3 books: 2 unindexed + 1 already indexed
# 2. Click "Index selected books"
# Expected: all requests complete; already-indexed books are safe to re-index (idempotent) unless dependencies are missing
# Overall: progress completes; any failures are listed in the error summary
```

---

### Phase 3: Collections

**Goal**: Allow users to create collections and add books to them.

**Backend Tasks**:
1. Create collections service module
2. Implement endpoints:
   - `GET /api/collections`
   - `POST /api/collections`
   - `POST /api/collections/{id}/books`
   - `DELETE /api/collections/{id}`
3. Add collections to library page context
4. Update `docs/technical-detail/storage-and-data-locations.md`

**Frontend Tasks**:
1. Render collections list in left sidebar
2. Add "Create collection" button (+)
3. Show "Add to collection" button in selection mode
4. Implement scope switching (All / EPUB / Collection)

**Test**:
```bash
uv run reader3-server

# Verify:
# - Creating a collection works (modal + save)
# - Collections list renders in left sidebar
# - Selecting books + "Add to collection" adds them
# - Clicking a collection filters center grid to show only those books
# - Collection counts update correctly
# - Deleting a collection works
```

**Test Data**:
```bash
# Via curl or browser DevTools console:

# Create collection
curl -X POST http://127.0.0.1:8123/api/collections \
  -H "Content-Type: application/json" \
  -d '{"name": "Science Fiction"}'

# Add books to collection
curl -X POST http://127.0.0.1:8123/api/collections/<uuid>/books \
  -H "Content-Type: application/json" \
  -d '{"action": "add", "book_ids": ["foundation_data", "dune_data"]}'
```

---

### Phase 4: Right Panel Pages

**Goal**: Implement Dashboard, Chat, and Search tabs.

**Backend Tasks**:
1. Add `GET /api/library/stats?scope=...` endpoint
2. Compute aggregated stats (books, indexed %, sections, chunks)

**Frontend Tasks**:
1. Create right-panel tab switcher (bottom-right)
2. **Dashboard tab**:
   - Fetch and display stats for current scope
   - Add "Refresh stats" button
   - Optional: "Index all in scope" button
3. **Search tab**:
   - Move existing library-search UI into tab
   - Refactor to not hide center grid when showing results
4. **Chat tab**:
   - Single-book selector dropdown
   - Disable "All books" and "Collection" with tooltips

**Test**:
```bash
uv run reader3-server

# Dashboard:
# - Switch to Dashboard tab
# - Verify stats match actual counts (books, indexed %, sections, chunks)
# - Change scope (All → Collection) and verify stats update
# - Click "Refresh stats" and verify numbers recalculate (uses `fresh=true` to bypass cache)

# Search:
# - Switch to Search tab
# - Run keyword search; verify results render
# - Verify center grid remains visible (not hidden)
# - Run semantic search on unindexed book; verify "Index" button appears

# Chat:
# - Switch to Chat tab
# - Verify single-book dropdown works
# - Verify "All books" and "Collection" are disabled with tooltips
```

---

## Testing Checklist

### Manual QA

- [ ] Left sidebar shows correct book counts (All / EPUB / PDF=0)
- [ ] Clicking filters updates center grid
- [ ] Grid/List toggle persists after page refresh
- [ ] Search box filters by title/author in real-time
- [ ] Sort (A→Z) works correctly
- [ ] "Add books" modal shows CLI instructions
- [ ] Select mode shows checkboxes and selected count
- [ ] "Index selected books" shows progress and updates status pills
- [ ] Creating a collection adds it to left sidebar
- [ ] Adding books to collection works
- [ ] Clicking collection filters center grid
- [ ] Dashboard stats match actual library state
- [ ] Search tab renders results without hiding center grid
- [ ] Chat tab single-book selector works

### API Contract Tests

Run these curl commands to verify endpoints:

```bash
# Get all collections
curl http://127.0.0.1:8123/api/collections

# Create collection
curl -X POST http://127.0.0.1:8123/api/collections \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Collection"}'

# Get stats (all books)
curl "http://127.0.0.1:8123/api/library/stats?scope=all"

# Get stats (EPUB only)
curl "http://127.0.0.1:8123/api/library/stats?scope=format:epub"

# Index a book
curl -X POST http://127.0.0.1:8123/api/index/dracula_data

# Get index status
curl http://127.0.0.1:8123/api/index/dracula_data/status
```

### Browser DevTools Tests

```javascript
// In browser console (http://127.0.0.1:8123):

// Test localStorage persistence
localStorage.setItem('reader3.library.viewMode', 'list');
location.reload();
// Verify: list view is active after reload

// Test selection state
const checkboxes = document.querySelectorAll('.book-checkbox');
console.log('Total books:', checkboxes.length);
checkboxes[0].click();
checkboxes[1].click();
console.log('Selected:', document.querySelectorAll('.book-checkbox:checked').length);
// Verify: selected count UI updates
```

---

## Troubleshooting

### Issue: Collections not persisting after server restart

**Cause**: `config/library_collections.json` not being written correctly.

**Debug**:
```bash
# Check if file exists
ls -la config/library_collections.json

# Check file contents
cat config/library_collections.json

# Check server logs for write errors
uv run reader3-server
# Look for "Error writing collections" or similar
```

**Fix**: Ensure `config/` directory exists and has write permissions.

---

### Issue: Index status pills not updating

**Cause**: Client-side lazy fetch not triggering.

**Debug**:
```javascript
// In browser console:
// Check if status fetches are happening
console.log('Fetching status for dracula_data...');
fetch('/api/index/dracula_data/status')
  .then(r => r.json())
  .then(console.log);
```

**Fix**: Verify `library.js` is loaded and `fetchIndexStatuses()` is called after page render.

---

### Issue: Bulk indexing stuck on "Indexing 1/3..."

**Cause**: One book's indexing is hanging or erroring silently.

**Debug**:
```bash
# Check server logs for indexing errors
uv run reader3-server
# Look for stack traces or "Error indexing {book_id}"

# Manually index the problematic book
curl -X POST http://127.0.0.1:8123/api/index/problem_book_data -v
```

**Fix**: Add better error handling and timeout to frontend bulk indexing loop.

---

### Issue: Dashboard stats show 0 for everything

**Cause**: Stats endpoint not computing correctly.

**Debug**:
```bash
# Test stats endpoint directly
curl "http://127.0.0.1:8123/api/library/stats?scope=all" -v

# Check server logs for errors
# Look for "Error computing stats" or similar
```

**Fix**: Verify `compute_stats()` logic in backend and ensure all books are being enumerated.

---

## Performance Benchmarks

Expected performance (on modern hardware, <50 books):

- **Library page load**: <500ms
- **Stats computation**: <200ms
- **Index status fetch (per book)**: <50ms
- **Single book indexing**: 10-60s (depends on book size)
- **Bulk indexing 10 books**: ~2-10 minutes (sequential)

If performance degrades:
1. Profile with browser DevTools Network tab
2. Check server logs for slow queries
3. Consider adding `@lru_cache` to `compute_stats()`
4. Consider parallel indexing (requires backend async refactor)

---

## Documentation Updates

After implementation, update these docs:

- [ ] `CLAUDE.md`: Add 004 to "Active Technologies" section
- [ ] `docs/technical-detail/storage-and-data-locations.md`: Document `config/library_collections.json`
- [ ] `docs/technical-detail/technical-detail.md`: Add Collections architecture overview
- [ ] `README.md`: Add Collections to feature list (if user-facing)

---

## Next Steps After 004

Once 004 is complete:

1. **005 - All-books Chat**: Multi-book RAG pipeline for chat across entire library
2. **006 - PDF Support**: Add PDF ingestion and reading
3. **007 - Advanced Collections**: Nested collections, auto-collections by metadata

---

## References

- **Spec**: [spec.md](./spec.md)
- **Plan**: [plan.md](./plan.md)
- **Data Model**: [data-model.md](./data-model.md)
- **API Contract**: [contracts/library-api.yaml](./contracts/library-api.yaml)
- **Research**: [research.md](./research.md)
