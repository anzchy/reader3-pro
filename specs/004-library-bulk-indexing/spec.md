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

## Requirements *(mandatory)*

### Functional Requirements

#### Index Status & Counts

- **FR-001**: Library MUST display per-book semantic index status and chunk count (from `GET /api/index/{book_id}/status`).
- **FR-002**: Library MUST display per-book section count (number of `book.spine` items).
- **FR-003**: Library MUST display per-book title and author.

#### Views

- **FR-004**: Library MUST provide a view toggle: `image` and `list`.
- **FR-005**: View mode MUST persist in localStorage and restore on reload.
- **FR-006**: Image view MUST show a small cover image when available; otherwise show a placeholder.
- **FR-007**: List view MUST show columns: `Title`, `Author`, `Chunks`, `Sections`, and a `Read` action.

#### Selection & Bulk Indexing

- **FR-008**: Library MUST provide selection mode to select multiple books (checkbox/click selection).
- **FR-009**: Library MUST provide `Select all` and `Clear selection` actions.
- **FR-010**: Library MUST provide an “Index selected” action that indexes all selected books using `POST /api/index/{book_id}`.
- **FR-011**: Library MUST show an overall progress indicator during bulk indexing (e.g., “Indexing 2/5”).
- **FR-012**: Bulk indexing MUST be resilient: failures for one book MUST NOT prevent other books from completing.

### Non-Functional Requirements

- **NFR-001**: Bulk indexing UI MUST remain responsive; indexing is performed asynchronously from the user’s perspective.
- **NFR-002**: Status fetches SHOULD avoid blocking the initial library render; client-side lazy fetch is acceptable.

## Out of Scope

- Drag-marquee (“框选拖拽”) selection.
- Cancel/stop an in-progress index operation (backend currently synchronous per book).
- Background queueing or parallel indexing across multiple books (the UI may run sequential requests).

