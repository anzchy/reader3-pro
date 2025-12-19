# Feature Specification: Library Bulk Indexing & Views

**Feature Branch**: `004-library-bulk-indexing`  
**Created**: 2025-12-19  
**Status**: Draft  
**Input**: User description: “AI chat 中语义检索提示未索引；希望在 Library 界面增加 Index 按钮，可选择特定书籍进行 index；支持多选；支持 list/image 两种视图并展示 author、indexed chunk 数、section 数。”

## Overview

### Problem Statement

- Semantic retrieval (semantic search + AI RAG) requires a per-book semantic index (`books/{book_id}/chroma_db/`).
- Today, when a book is not indexed, the user may see an error like:
  - `Error: This book is not indexed for semantic retrieval yet. Run /api/index/{book_id} or click the 'Index for semantic' button first.`
- The existing indexing workflow is not obvious at the library level, and indexing one-by-one is cumbersome.

### Solution

Enhance the **Library** page to support:

1. **Multi-select** books for bulk actions (indexing).
2. **Bulk “Index selected”** using the existing endpoint `POST /api/index/{book_id}`.
3. Two library layouts:
   - **Image view**: cover grid (small cover + metadata under).
   - **List view**: rows showing book title/author/indexed chunk count/section count.
4. Show per-book **semantic index status** and counts using `GET /api/index/{book_id}/status`.

## Clarifications

- “框选选择特定书籍” is implemented as **explicit selection UI** (checkbox/click selection).  
  Drag-marquee selection is out of scope for this phase.
- Indexing is **per book folder** (e.g., `dracula_data`) and uses existing indexing logic.
- The library view toggle persists in **localStorage** (client-only).

### Session 2025-12-19

- Q: Where should Collections be stored for MVP? → A: Server-side persisted in `config/library_collections.json` (gitignored).
- Q: How should the PDF filter appear in the left sidebar? → A: Show it disabled with count=0 and a tooltip (“PDF not supported yet”).
- Q: Where should Dashboard stats be computed? → A: Server provides an aggregated stats endpoint (`GET /api/library/stats?scope=...`).
- Q: Should Chat support all-books/collection chat in 004? → A: No—only single-book chat; all-books/collection are disabled/coming soon.
- Q: How should the `/api/library/stats` scope be encoded? → A: Single `scope` param: `all`, `format:epub`, `format:pdf`, `collection:<collection_id>`.

## Definitions

- **Library scope**: The current subset of books the Library UI operates on (left sidebar selection): `all`, `format:epub`, `format:pdf`, or `collection:<collection_id>` (where `collection_id` is a UUID v4).
- **Section count**: `len(book.spine)` (reading-order items), not TOC depth/entries.
- **Semantic index**: Per-book vector index under `books/{book_id}/chroma_db/`.
- **Semantic index status (server)**: The `status` field returned by `GET /api/index/{book_id}/status`:
  - `not_indexed`: `index_meta.json` missing
  - `indexed`: `index_meta.json` exists with `status: "indexed"`
  - `unknown`: `index_meta.json` exists but unreadable/unparseable
- **Semantic index status (UI)**: Uses server status plus client transient states:
  - `indexing`: a client-side in-progress state during `POST /api/index/{book_id}`
  - `error`: a client-side failure state for the last attempted operation
- **Chunks**: The number of text chunks indexed for a book (`chunk_count`).

## Assumptions

- Single-user, local deployment (no authentication/authorization requirements for v1).
- Book folder IDs (`*_data`) are treated as stable identifiers; if a folder is renamed/moved manually, collections may reference missing book_ids until cleaned up.
- `config/` is writable and persists across server restarts (otherwise collections are unavailable and the UI must degrade gracefully).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Bulk Index Selected Books (Priority: P1)

As a user, I want to select multiple books in the library and index them in one click so that semantic search and AI RAG work without “not indexed” errors.

**Acceptance Scenarios**:

1. **Given** the user is on the library page, **When** they enable selection and select multiple books, **Then** the UI indicates which books are selected and shows the selected count.
2. **Given** at least one book is selected, **When** the user clicks “Index selected”, **Then** indexing starts and the UI shows per-book states: `indexing` → `indexed` or `error`.
3. **Given** indexing fails for one book, **When** the batch completes, **Then** other books can still succeed and the UI shows errors per-book without aborting the rest.

### User Story 2 — Switch Between Image/List Views (Priority: P1)

As a user, I want to switch between an image grid and a list view so I can browse by covers or by metadata.

**Acceptance Scenarios**:

1. **Given** the user switches the library view, **When** toggling between image and list, **Then** the same set of books is shown in the selected layout.
2. **Given** the user already selected books, **When** toggling views, **Then** selection remains unchanged.
3. **Given** the user refreshes the page, **When** the library loads, **Then** the previously chosen view mode is restored.

### User Story 3 — Collections (Priority: P1)

As a user, I want to create Collections and add selected books to them so I can browse by author/theme.

**Acceptance Scenarios**:

1. **Given** the user creates a collection, **When** they provide a valid unique name, **Then** it appears in the left sidebar sorted A→Z with a count.
2. **Given** the user is in selection mode, **When** they add selected books to a collection, **Then** the collection count updates and switching to that collection scope shows only those books.
3. **Given** the user attempts to create a duplicate collection name, **When** they submit, **Then** the UI shows a clear error and no collection is created.

### User Story 4 — Dashboard/Search/Chat Panel (Priority: P2)

As a user, I want a right-panel switcher so I can see stats, run cross-book search, and access chat from the library.

**Acceptance Scenarios**:

1. **Given** the user switches to Dashboard, **When** stats are available, **Then** it shows Books/Indexed/Sections/Chunks for the current scope.
2. **Given** the user switches to Search, **When** they run a query, **Then** results render in the panel without hiding the center bookshelf.
3. **Given** the user switches to Chat, **When** they open the scope selector, **Then** only single-book chat is enabled and other options show “Coming soon”.

## Requirements *(mandatory)*

### Functional Requirements

#### Index Status & Counts

- **FR-001**: Library MUST display per-book semantic index status and chunk count (from `GET /api/index/{book_id}/status`).
- **FR-002**: Library MUST display per-book section count (number of `book.spine` items).
- **FR-003**: Library MUST display per-book title and author.

#### Views

- **FR-004**: Library MUST provide a view toggle: `image` and `list`.
- **FR-005**: View mode MUST persist in localStorage and restore on reload; if localStorage is unavailable, the UI MUST fall back to the default view without errors.
- **FR-006**: Image view MUST show a cover image when available; if missing or the image fails to load, the UI MUST show a deterministic placeholder (e.g., book initials) without breaking layout.
- **FR-007**: List view MUST show columns: `Title`, `Author`, `Chunks`, `Sections`, `Index Status`, and a `Read` action.
- **FR-007a**: Library MUST show a `PDF` filter entry in the left sidebar; until PDF support exists it MUST be disabled and show a count of `0` with a “not supported yet” tooltip.

#### Dashboard (Library Stats)

- **FR-016**: Library MUST provide an aggregated stats API for the current scope: `GET /api/library/stats?scope=...` (books count, indexed count/percent, sections sum, chunks sum).
- **FR-016a**: `GET /api/library/stats` MUST accept a `scope` query param encoded as: `all`, `format:epub`, `format:pdf`, or `collection:<collection_id>`.
- **FR-019**: `indexed_percent` MUST be computed as `round(books_indexed / books_total * 100)`; when `books_total == 0`, it MUST be `0`.
- **FR-020**: Dashboard MUST define empty-scope display: for an empty collection or no books, show all counts as `0` and a short “No books in this scope” hint.
- **FR-021**: When stats computation fails or times out, Dashboard MUST show a non-blocking error state and provide a “Refresh stats” action.
- **FR-022**: Dashboard MUST define a refresh strategy: “Refresh stats” MUST request fresh values; otherwise values MAY be cached server-side for a short TTL.
- **FR-022a**: If server-side caching is used, `GET /api/library/stats` MUST accept an optional `fresh=true` query param that forces a recompute (bypasses cache) for that request.

#### Selection & Bulk Indexing

- **FR-008**: Library MUST provide selection mode to select multiple books (checkbox/click selection).
- **FR-009**: Library MUST provide `Select all` and `Clear selection` actions.
- **FR-010**: Library MUST provide an “Index selected” action that indexes all selected books using `POST /api/index/{book_id}`.
- **FR-011**: Library MUST show an overall progress indicator during bulk indexing (e.g., “Indexing 2/5”).
- **FR-012**: Bulk indexing MUST be resilient: failures for one book MUST NOT prevent other books from completing.
- **FR-023**: Bulk indexing MUST be sequential (one in-flight `POST /api/index/{book_id}` at a time) and MUST surface per-book state transitions: `not_indexed|unknown` → `indexing` → `indexed` OR `error`.
- **FR-024**: Bulk indexing MUST define failure tolerance: if any subset of books fail, the batch still completes; the UI MUST show a summary that includes `book_id` and an error message for each failure.
- **FR-025**: If the user refreshes or closes the page during bulk indexing, the operation MUST NOT “resume automatically”; on next load the UI MUST reflect the on-disk index state via the status endpoint and provide a clear “Indexing was interrupted” hint.
- **FR-026**: If the user attempts to navigate away while bulk indexing is running, the UI MUST warn that indexing will be interrupted (confirm/leave pattern).
- **FR-027**: Indexing requests MUST define timeout and retry semantics:
  - status fetch (`GET /api/index/{book_id}/status`): retry once on network error; treat timeout/error as `unknown` status
  - indexing (`POST /api/index/{book_id}`): no automatic retries; surface error in UI
- **FR-028**: Selection behavior MUST be explicitly defined:
  - checkboxes appear only when selection mode is enabled
  - selection MUST persist across grid/list toggles
  - switching Library scope MUST clear selection to prevent accidental bulk actions in a new scope
- **FR-028a**: Alternate flows:
  - switching scope while books are selected MUST clear selection and exit selection mode
  - toggling grid/list view during an active bulk indexing operation MUST NOT interrupt the operation

#### Collections (Grouping)

- **FR-013**: Library MUST support user-defined Collections that group multiple books (e.g., by author/theme).
- **FR-014**: Library MUST allow adding selected books to a Collection from selection mode.
- **FR-015**: Collections MUST persist server-side in `config/library_collections.json` (gitignored).
- **FR-015a**: Collections persistence MUST NOT modify any per-book processed outputs (`books/*_data/book.pkl`, `images/`, etc.); it is library-level metadata only.
- **FR-029**: Collection names MUST be validated:
  - 1–60 characters after trimming
  - allow letters, numbers, space, `_`, `-`, `.`, `&`, `()`
  - uniqueness MUST be case-insensitive (e.g., “SciFi” == “scifi”)
- **FR-030**: Creating a collection with a duplicate name MUST fail with a clear, user-visible error message (no silent rename).
- **FR-031**: Collections list ordering MUST be deterministic: default sort by name A→Z (case-insensitive).
- **FR-032**: Deleting the currently active collection scope MUST reset scope to `all` and clear any selection.
- **FR-033**: Collections MUST define scalability constraints:
  - max collections per library: 200
  - max books per collection: 2000
- **FR-034**: Orphaned book ids:
  - if a `book_id` referenced by a collection no longer exists in the library, the UI MUST not error
  - the UI MUST surface a non-blocking indication (e.g., “1 missing”) and provide a way to remove missing references from the collection
- **FR-035**: Collections edits MUST be immediate (no unsaved local draft state); the server is the source of truth after each create/update/delete/membership change.
- **FR-036**: If `config/library_collections.json` is missing, the system MUST treat it as “no collections” (empty list) and create it on first write.
- **FR-037**: If `config/library_collections.json` is unreadable/invalid JSON or schema version is unsupported, the API MUST return a clear error and the UI MUST show “Collections unavailable” with a suggested recovery action (restore from backup).
- **FR-057**: Collection IDs MUST be UUID v4 strings.
- **FR-058**: All collection timestamps MUST be ISO 8601 UTC with timezone (e.g., `...Z` or `...+00:00`).
- **FR-059**: Collections persistence MUST be atomic (write-to-temp + rename) to avoid partial writes.
- **FR-060**: Collections API MUST define status code mapping:
  - `201` create success, `200` get/list/update success, `204` delete success
  - `400` invalid input (including duplicate name)
  - `404` collection not found
  - `500` collections file read/write failure (or schema incompatibility)
- **FR-060a**: Collections rollout MUST be explicit: when `READER3_LIBRARY_UI=modern`, Collections are enabled by default (no gradual rollout required in v1).

#### Chat (Library Panel)

- **FR-017**: Library MUST provide a Chat panel that supports single-book chat selection (reusing existing reader AI endpoints).
- **FR-018**: All-books and collection chat MUST be shown as disabled/coming soon in 004 (out of scope for this phase).
- **FR-038**: The “coming soon” pattern MUST be defined consistently:
  - disabled control (not clickable) with tooltip text: “Coming soon”
  - reduced opacity (0.5) and `cursor: not-allowed`
  - no keyboard focus for disabled controls

#### Library Layout & Interaction Details

- **FR-039**: The Library page MUST be a 3-pane layout with these baseline dimensions (desktop):
  - left sidebar: 240px
  - right panel: 320px
  - center: flexible remaining width
  - max content width: 1400px centered
- **FR-040**: The right-panel tab switcher MUST be fixed to the bottom-right of the viewport with: `right: 20px`, `bottom: 20px`, and `z-index >= 900`.
- **FR-041**: Toolbar controls MUST define consistent UI states (default/hover/active/disabled) with deterministic styling; disabled state MUST use opacity 0.5 and prevent interaction.
- **FR-042**: Panel transitions MUST be specified: open/close animations use a 160–200ms ease transition (no long animations).
- **FR-043**: The Library MUST provide clear loading states for async operations:
  - index status fetch: per-book “Loading…” state (non-blocking)
  - stats fetch: panel-level spinner/skeleton (non-blocking)
  - bulk indexing: both overall progress and per-book indexing state
- **FR-044**: The Library MUST provide explicit empty states:
  - no books: show “No processed books found” plus “Add books” instructions
  - zero filter results: show “No books match your filter”
  - no collections: show “No collections yet” plus create affordance
- **FR-045**: Spacing/padding MUST be specified via CSS variables and applied consistently:
  - page padding: 16px
  - pane gap: 16px
  - card padding: 10–12px
- **FR-046**: List view column sizing MUST be specified (allowing responsive adjustment):
  - Title: flexible (min 240px)
  - Author: 160–220px
  - Sections: 80–100px
  - Chunks: 80–110px
  - Index Status: 110–140px
  - Read/Actions: 80–110px
- **FR-047**: Keyboard behavior MUST be explicitly defined:
  - `Esc` closes the active modal, exits selection mode, and dismisses transient error popovers
  - no additional custom keyboard shortcuts are required in v1 beyond standard Tab/Shift+Tab navigation
- **FR-048**: Tooltips MUST be specified for disabled UI elements:
  - PDF filter tooltip text: “PDF not supported yet”
  - disabled Chat options tooltip text: “Coming soon”
- **FR-049**: Deleting a collection MUST require confirmation (to prevent accidental destructive action).
- **FR-049a**: Selected-book visual state MUST be consistent across grid and list:
  - selected cards/rows MUST show an accent border (2px) and a subtle background tint
  - hover styling MUST not override the selected styling
- **FR-049b**: Responsiveness MUST be specified for the center bookshelf:
  - grid view uses a responsive column layout (auto-fill) with a minimum card width of 140px
  - list view remains readable down to 960px viewport width without horizontal scrolling

#### API Contracts, Validation, and Security

- **FR-050**: API error responses MUST use the FastAPI `HTTPException` shape: `{"detail": "<message>"}` consistently across new endpoints.
- **FR-050a**: API contracts for this feature MUST be reflected in `contracts/library-api.yaml` (endpoints, request/response schemas, and status codes).
- **FR-051**: Collection name inputs MUST be validated server-side (length/allowed characters/uniqueness) and MUST be HTML-escaped when rendered to prevent XSS.
- **FR-052**: Collections membership operations MUST validate `book_id` values using the same path-safety constraints as other book routes (reject path separators; allow only known `*_data` book folders).
- **FR-052a**: Indexing endpoints MUST be treated as the source of truth for index state:
  - `POST /api/index/{book_id}` accepts `{"force_reindex": boolean}` and returns an index meta payload including `status`, `chunk_count`, `model_name`, `indexed_at`
  - `GET /api/index/{book_id}/status` returns `status in {not_indexed,indexed,unknown}` and `chunk_count` (nullable for `unknown`)
- **FR-053**: Stats endpoint caching MUST be explicitly defined:
  - server MAY cache `/api/library/stats` responses per scope for up to 5 seconds
  - “Refresh stats” MUST bypass cache by requesting a fresh recompute (e.g., `fresh=true`)
- **FR-054**: Rollback/feature-flag requirement:
  - the server MUST allow switching the Library UI between `modern` (3-pane) and `classic` (current single-column) via `READER3_LIBRARY_UI=modern|classic` (default: `modern`)
- **FR-055**: Local persistence compatibility:
  - existing session storage used by cross-library search MUST remain compatible across the UI migration
  - view mode localStorage MUST use a stable key name and versionless value strings (`reader3.library.viewMode` = `grid|list`)
  - active right-panel tab MAY be persisted with a stable key (`reader3.library.activeTab` = `dashboard|chat|search`)
- **FR-056**: Multi-device expectations MUST be explicit: localStorage persistence is per-browser and is not synchronized across devices; this is acceptable for UI preferences.
- **FR-056a**: Search tab scope MUST be explicit: cross-book Search operates across the whole library (not limited by the current scope) in v1.
- **FR-056b**: Semantic dependency failures MUST be specified: if semantic search dependencies are missing, indexing endpoints MUST return `400` with guidance text, and the UI MUST surface that guidance to the user.

### Non-Functional Requirements

- **NFR-001**: Bulk indexing UI MUST remain responsive; indexing is performed asynchronously from the user’s perspective.
- **NFR-002**: Status fetches SHOULD avoid blocking the initial library render; client-side lazy fetch is acceptable.
- **NFR-002a**: “Lazy fetch” MUST be defined as:
  - status requests start only after the initial book list is rendered
  - fetch statuses in small batches (<=20 book_ids) with a maximum of 4 concurrent requests
  - per-request timeout: 5 seconds; on timeout/network error, mark status as `unknown` and do not block the UI
- **NFR-003**: Performance targets:
  - initial library HTML render: <500ms for 50 books on localhost
  - status lazy fetch: visible books’ status pills populated within 2s for 50 books
  - stats endpoint: <250ms for 100 books; <1s for 500 books on localhost
- **NFR-004**: Accessibility baseline:
  - all interactive controls MUST be reachable by keyboard
  - focus order MUST be logical across panes
  - modals MUST trap focus and restore focus on close
  - all icon-only buttons MUST have accessible labels (ARIA)
- bulk indexing progress SHOULD be announced via an `aria-live` region
- status pills and disabled states MUST meet WCAG AA contrast guidelines
- **NFR-005**: Browser support assumptions MUST be explicit: latest Chrome/Safari/Firefox, ES6+, CSS Grid; if features are unavailable, the UI MUST degrade gracefully (no blank page).
- **NFR-006**: Large-book expectations MUST be explicit:
  - indexing large books (e.g., >1000 sections or >10000 chunks) may take minutes
  - the UI MUST communicate this to users (non-blocking hint) and remain responsive during indexing

## Out of Scope

- Drag-marquee (“框选拖拽”) selection.
- Cancel/stop an in-progress index operation (backend currently synchronous per book).
- Background queueing or parallel indexing across multiple books (the UI may run sequential requests).
- All-books and collection chat (multi-book chat scope).
- PDF ingestion and reading support (filter is UI-only for now).
