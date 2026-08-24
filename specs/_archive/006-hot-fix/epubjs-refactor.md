# EPUB.js Refactor (Phase 5) - Before vs After

This doc records the EPUB.js refactor changes for 006-hot-fix, including which files changed and the logic differences.

## Summary

Goal: replace server-rendered chapter HTML with client-side EPUB rendering (epub.js) to fix annotation click/selection issues and improve layout/pagination reliability.

## Before vs After (High Level)

**Before**
- Reader page renders chapter HTML directly in the template (`current_chapter.content`) inside `.book-content`.
- Pagination relies on CSS multi-column layout + `pagination.js`.
- Annotations/search operate on the main document DOM.
- Chapter navigation triggers full page loads (`/read/{book_id}/{chapter_index}`).

**After**
- Reader page loads original EPUB into an iframe via epub.js.
- Pagination handled by epub.js flow (`paginated` / `scrolled-doc`).
- Annotations/search operate inside the iframe document (via `Reader3Epub` bridge).
- Chapter navigation updates the URL via `history.replaceState` and emits a `reader3:chapter:change` event.

## File-by-File Changes

### 1) Reader Template
**File:** `src/reader3_app/web/templates/reader.html`

**Before**
- Injected chapter HTML into `.book-content`.
- `pagination.js` controlled pagination.
- TOC links navigated via full page loads.

**After**
- Replaced chapter HTML with `<div id="epub-viewer">` (epub.js mount).
- Added `epubUrl` / `epubAvailable` to `Reader3Ctx`.
- TOC links include `data-file-href` for active state updates.
- `pagination.js` removed; `jszip.min.js` + `epub.min.js` + `epub-renderer.js` added.

### 2) EPUB Rendering
**File:** `src/reader3_app/web/static/js/epub-renderer.js` (new)

**Before**
- No EPUB client renderer; relied on server-rendered HTML.

**After**
- Creates a `book` with `ePub(epubUrl)` and renders into `#epub-viewer`.
- Chooses `paginated` flow on desktop, `scrolled-doc` on small screens.
- Updates progress indicator on `relocated`.
- Updates URL + TOC active state on `rendered`.
- Exposes `window.Reader3Epub` API:
  - `getContents()`, `getContentRoot()`, `getFrameElement()`
  - `onContentsReady(cb)`
  - `displaySectionIndex(index)`
  - `applyThemeSettings()`

### 3) Server Routing + Context
**File:** `src/reader3_app/web/server.py`

**Before**
- No endpoint to serve original EPUB.
- Template had no `epubUrl` / `epubAvailable`.

**After**
- Added `GET /read/{book_id}/book.epub` (serves `books/{book_id}/book.epub`).
- `read_chapter` now injects `epub_url` + `epub_available`.
- Route order adjusted so `/read/{book_id}/book.epub` is matched before `/read/{book_id}/{chapter_index}`.
- Create annotation request accepts optional `cfi` for precise anchoring.

### 4) EPUB Persistence
**File:** `src/reader3_app/reader3.py`

**Before**
- Only wrote parsed `book.pkl` + extracted images.

**After**
- Copies the original EPUB into `books/{book_id}/book.epub` for epub.js rendering.

### 5) Annotations
**File:** `src/reader3_app/web/static/js/annotations.js`

**Before**
- Selection/marks handled in main document.
- No CFI support; relied on text offsets.
- Toolbar positioning did not account for iframe offsets.

**After**
- Uses iframe document + selection (`Reader3Epub.getContents()`).
- Captures CFI via `contents.cfiFromRange`.
- Renders annotations via CFI when available; text fallback kept for legacy notes.
- Toolbar positioning adjusted using iframe bounding rect.
- Added debug logs for click/selection and `elementsFromPoint`.

### 6) Notes & Search Bridging
**Files:**
- `src/reader3_app/web/static/js/notes-panel.js`
- `src/reader3_app/web/static/search.js`

**Before**
- Assumed `.book-content` in main document.
- Notes header not refreshed on in-place chapter changes.

**After**
- Pull content root from `Reader3Epub.getContentRoot()`.
- Defer search highlight until iframe content is ready.
- Notes header refreshes on `reader3:chapter:change`.

### 7) Annotation Model
**File:** `src/reader3_app/models/annotations.py`

**Before**
- No CFI field.

**After**
- Added optional `cfi` field to the dataclass and serialization.

### 8) Static Vendor Libraries
**Files:**
- `src/reader3_app/web/static/vendor/jszip.min.js` (new)
- `src/reader3_app/web/static/vendor/epub.min.js` (new)

**Before**
- No epub.js dependency.

**After**
- Bundled JSZip (v3.10.1) - **required dependency** for epub.js to unzip EPUB files.
- Bundled epub.js to render EPUB content on the client.

**IMPORTANT:** JSZip must be loaded **before** epub.js in the HTML:
```html
<script src="/static/vendor/jszip.min.js"></script>
<script src="/static/vendor/epub.min.js"></script>
<script src="/static/js/epub-renderer.js"></script>
```

Without JSZip, epub.js will fail silently with `book.opened` promise never resolving and error: `"JSZip lib not loaded"`.

### 9) Docs & Specs
**Files:**
- `docs/storage-and-data-locations.md`
- `docs/technical-detail.md`
- `specs/006-hot-fix/spec.md`
- `specs/006-hot-fix/plan.md`
- `specs/006-hot-fix/tasks.md`

**Before**
- No record of `book.epub` storage or `cfi` in annotations.

**After**
- Documented `books/{book_id}/book.epub` + `cfi` field.
- Phase 5 changes logged in spec/plan/tasks.

## Behavioral Differences (Quick List)

**Rendering**
- Before: server renders HTML from `book.pkl`.
- After: client renders EPUB via epub.js.

**Pagination**
- Before: CSS columns + `pagination.js`.
- After: epub.js flow (`paginated` / `scrolled-doc`).

**Annotations**
- Before: text range offsets only.
- After: prefer CFI + text fallback.

**Navigation**
- Before: full page reload for chapter changes.
- After: in-place navigation with URL updates.
