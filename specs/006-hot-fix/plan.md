# Implementation Plan: Full-Screen Paginated Reader

**Branch**: `006-hot-fix` | **Date**: 2025-12-27 | **Spec**: [spec.md](./spec.md#feature-specification-full-screen-paginated-reader)
**Input**: Feature specification from `/specs/006-hot-fix/spec.md`

## Summary

Transform the reader page from a narrow card-based layout (`max-width: 768px`) to a full-screen paginated reading experience. Content will fill the viewport width with 80px margins on each side, be automatically paginated horizontally using CSS Multi-column Layout, and support keyboard/click navigation between pages with a reading progress indicator.

This is a **pure frontend feature** (CSS + JavaScript changes only) with no backend modifications required.

## Technical Context

**Language/Version**: JavaScript ES6+, CSS3
**Primary Dependencies**: Vanilla JS (no frameworks), existing reader.html template
**Storage**: N/A (frontend-only, no persistent state changes)
**Testing**: Manual browser testing across Chrome 90+, Safari 14+, Firefox 88+, Edge 90+
**Target Platform**: Desktop browsers (≥600px viewport), mobile fallback to vertical scroll
**Project Type**: Web application (frontend modification)
**Performance Goals**: Page transitions ≤200ms, pagination calculation ≤100ms
**Constraints**: Must maintain compatibility with existing annotation system, side panels (TOC, Search, AI, Notes)
**Scale/Scope**: Single file modification (`reader.html`), new JS file (`pagination.js`)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Data Structures First | ✅ PASS | No new data structures needed; frontend-only change |
| II. Simplicity Over Engineering | ✅ PASS | Uses native CSS columns, vanilla JS; no frameworks |
| III. File-Based State Management | ✅ PASS | No backend state changes |
| IV. HTML Content Sanitization | ✅ PASS | No change to content handling |
| V. Path Security | ✅ PASS | No new path operations |
| VI. Explicit Over Implicit | ✅ PASS | CSS variables for all magic numbers |
| VII. Performance Through Caching | ✅ PASS | No caching changes needed |

**Result**: All gates passed. No constitution violations.

## Project Structure

### Documentation (this feature)

```text
specs/006-hot-fix/
├── spec.md              # Feature specification (complete)
├── plan.md              # This file
├── tasks.md             # Implementation tasks (exists, needs Phase 2 update)
└── research.md          # Phase 0 output (minimal - no unknowns)
```

### Source Code (repository root)

```text
src/reader3_app/web/
├── templates/
│   └── reader.html          # UPDATE: CSS layout, add pagination container
└── static/
    └── js/
        └── pagination.js    # NEW: Pagination logic and navigation
```

**Structure Decision**: Minimal changes - one template update, one new JS file. Follows existing project structure.

## Phase 0: Research

### Unknowns Resolved

No critical unknowns identified. The feature uses well-documented CSS/JS techniques:

1. **CSS Multi-column Layout**: Widely supported (Chrome 50+, Safari 9+, Firefox 52+)
2. **CSS Scroll Snap**: Supported in all target browsers
3. **Reading position preservation**: Can be achieved by tracking scroll position as percentage before reflow

### Technology Decisions

| Decision | Rationale | Alternatives Rejected |
|----------|-----------|----------------------|
| CSS columns for pagination | Native browser support, no JS calculation needed for page breaks | JS-based pagination (more complex, less performant) |
| Scroll snap for page alignment | Smooth native animation, accessibility built-in | Manual transform animations (more code, less accessible) |
| Vanilla JS | Project constitution requires simplicity; no framework dependencies | React/Vue (violates constitution II) |

## Phase 1: Design

### Component Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│  reader.html                                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  .pagination-container (overflow-x: auto, scroll-snap) │  │
│  │  ┌─────────────────────────────────────────────────┐   │  │
│  │  │  .book-content (CSS columns, full height)       │   │  │
│  │  │  Content flows horizontally into columns        │   │  │
│  │  └─────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  .reading-progress (fixed bottom)                     │  │
│  │  "当前阅读至 30%"                                       │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌─────────┐                                   ┌─────────┐  │
│  │ .nav-   │                                   │ .nav-   │  │
│  │ zone    │                                   │ zone    │  │
│  │ left    │                                   │ right   │  │
│  │ 120px   │                                   │ 120px   │  │
│  └─────────┘                                   └─────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### CSS Variables (from spec)

```css
:root {
  --reader-margin-x: 80px;
  --reader-padding-top: 40px;
  --reader-padding-bottom: 60px;
  --reader-nav-zone-width: 120px;
  --reader-transition-duration: 180ms;
  --reader-min-pagination-width: 600px;
}
```

### JavaScript Module: pagination.js

```javascript
// Core responsibilities:
// 1. Calculate total pages from scrollWidth / clientWidth
// 2. Navigate to page N via scrollLeft = N * clientWidth
// 3. Handle keyboard (←/→) and click navigation
// 4. Update progress indicator on scroll/navigation
// 5. Preserve reading position on resize (track % position)
// 6. Detect viewport < 600px and disable pagination
```

### API Contracts

No new API endpoints. Frontend-only changes.

### Data Model

No new data structures. Reading position is transient (not persisted between sessions).

## Phase 2: Implementation Tasks

See `tasks.md` for detailed implementation breakdown organized by User Story:

- **US1 (T007-T011)**: Full-width content layout (CSS variables, margins, mobile fallback)
- **US2 (T012-T017)**: Horizontal pagination with CSS columns + pagination.js module
- **US3 (T018-T023)**: Page navigation controls (keyboard, click zones, cross-section)
- **US4 (T024-T028)**: Reading progress indicator
- **Polish (T029-T033)**: Integration and browser testing

### Implementation Order

```text
US1 (Layout) → US2 (Pagination) → US3 (Navigation) → US4 (Progress) → Polish
T007-T011       T012-T017          T018-T023          T024-T028        T029-T033
    │               │                   │                  │               │
    └───────────────┴───────────────────┴──────────────────┴───────────────┘
                            Sequential dependency chain
```

## Risk Mitigation

| Risk | Mitigation Strategy |
|------|---------------------|
| Annotation toolbar breaks with new layout | Test toolbar positioning after CSS changes; may need z-index adjustments |
| Long chapters cause performance issues | Monitor with large EPUBs; consider lazy rendering if needed |
| Browser compatibility | Test in all target browsers; fallback to vertical scroll if columns fail |
| Side panel overlay conflicts | Ensure panels have higher z-index than content |

## Success Criteria

1. ✅ Content uses full viewport width minus 160px (80px × 2)
2. ✅ Pages navigate horizontally without vertical scroll
3. ✅ Progress indicator shows current position
4. ✅ Keyboard navigation (←/→) works
5. ✅ Click zones (120px) work on screen edges
6. ✅ Resize preserves reading position
7. ✅ Mobile fallback to vertical scroll (< 600px)
8. ⚠️ Existing features (annotations, panels) still work - **Issue found, see Phase 3**

---

## Phase 3: Bug Fixes & Enhancements

> See `spec.md` Phase 3 section for detailed requirements (FR-P3-001 to FR-P3-014).

### Issue 1: First Page Content Overflow (Bug Fix)

**Problem**: CSS columns start at scroll position 0, but first column content overflows past left margin.

**Technical Analysis**:
- CSS Multi-column with `padding: 0 var(--reader-margin-x)` may not apply correctly to first column
- The `column-gap` creates space between columns, but first column needs explicit left padding

**Solution Approach**:
1. Add explicit left margin/padding to `.book-content` that accounts for first page
2. Alternatively, wrap content in inner container with proper margins
3. Adjust `scrollLeft` calculation in pagination.js to account for initial offset

**Files**: `reader.html` (CSS), possibly `pagination.js`

### Issue 2: AI Chat Panel Width + Resizable

**Problem**: Panel too narrow (420px default), needs 30% wider + manual resize.

**Technical Analysis**:
- Current: `.ai-sidebar` has fixed width
- Need: CSS custom property for default width, resize handle on left edge

**Solution Approach**:
1. Add CSS variable `--ai-panel-width: 546px` (420 × 1.3)
2. Add `.resize-handle` element on left edge of AI panel
3. Implement drag-to-resize in JavaScript (mousedown/mousemove/mouseup)
4. Store resized width in localStorage, restore on panel open
5. Constrain width: min 320px, max 800px

**Files**: `reader.html` (CSS + HTML), new or existing JS file

### Issue 3: Annotation/Highlight/Notes Not Working

**Problem**: Text selection popup doesn't appear after pagination changes.

**Technical Analysis**:
- Root cause likely: pagination container's `overflow-x: auto` or z-index affecting event propagation
- Annotation toolbar may be positioned incorrectly relative to paginated container
- Selection coordinates may need adjustment for horizontal scroll position

**Solution Approach**:
1. Verify annotation toolbar has higher z-index than pagination elements
2. Check if selection events are being captured by nav zones
3. Adjust toolbar positioning to account for `scrollLeft` offset
4. Ensure `pointer-events` are correctly set on nav zones (allow text selection through)

**Files**: `reader.html` (CSS z-index), `annotations.js` (positioning logic)

### Issue 4: Font Settings Popup

**Problem**: No way to adjust font size / paragraph spacing while reading.

**Technical Analysis**:
- New feature: popup triggered by toolbar button
- Controls: font size (14-24px), line-height (1.5-2.5)
- Theme/font family: UI placeholders only for v1
- Persist to localStorage, apply on page load

**Solution Approach**:
1. Add "Aa" icon button to right toolbar
2. Create popup HTML with theme selector (disabled), font size +/-, spacing +/-, font family (disabled)
3. Add CSS for popup styling
4. Implement JS for popup toggle, increment/decrement controls
5. Apply changes to `.book-content` via CSS custom properties
6. Save/load from localStorage

**Files**: `reader.html` (HTML + CSS), new `font-settings.js` or inline script

### Phase 3 Implementation Order

```text
Issue 1 (First Page Fix) → Issue 3 (Annotations) → Issue 2 (AI Panel) → Issue 4 (Font Settings)
    T034                       T035-T037              T038-T041            T042-T047
         │                          │                      │                    │
         └──────────────────────────┴──────────────────────┴────────────────────┘
                                 Priority order (P1 bugs first)
```

**Rationale**: Fix critical bugs first (Issue 1, 3 are P1), then enhancements (Issue 2, 4 are P2).

---

## Phase 4: Annotation System Enhancements

> See `spec.md` Phase 4 section for detailed requirements (FR-P4-001 to FR-P4-010).

### Issue 5 & 6: Annotation Toggle & Click-to-Select

**Problem**: Users need toggle behavior for annotations and ability to click on annotated text.

**Technical Analysis**:
- Need to detect existing annotations at selection range
- Need click handler on `<mark>` elements to select and show toolbar
- Need to track annotation IDs for deletion

**Solution Implemented**:
1. Added `toggleAnnotation(type)` method - checks for existing annotations, deletes if found, creates if not
2. Added `getExistingAnnotationIds(type)` to find overlapping annotations by type
3. Added `deleteAnnotations(ids)` to delete multiple annotations
4. Added `onAnnotationClick(e)` handler for `<mark>` elements
5. Added `openNoteEditorWithExisting(noteText, annotationIds)` for editing notes
6. Added Delete button to toolbar for explicit deletion
7. Added PUT endpoint `/api/notes/{book_id}/{chapter_index}/{note_id}` for updating notes

**Files Modified**:
- `src/reader3_app/web/static/js/annotations.js` - Toggle and click logic
- `src/reader3_app/web/templates/reader.html` - Delete button HTML/CSS
- `src/reader3_app/web/server.py` - PUT endpoint
- `src/reader3_app/notes_service.py` - `update_annotation()` function

### Issue 7: Notes Panel UI Redesign

**Problem**: Notes panel needs Dedao-style UI with chapter grouping and icons.

**Solution Implemented**:
1. Redesigned panel HTML structure with header, body, footer sections
2. Added chapter group headers with orange background
3. Added note item icons (A for highlights, speech bubble for notes)
4. Added footer with "点评此书" and "复制全部笔记" buttons
5. Implemented `copyAllNotes()` function for Markdown export

**Files Modified**:
- `src/reader3_app/web/templates/reader.html` - Panel HTML/CSS
- `src/reader3_app/web/static/js/notes-panel.js` - Panel logic and copy function

### Issue 8: Annotation Style Fixes

**Problem**: Underline/wavy annotations showed yellow background instead of line-only decoration.

**Solution Implemented**:
1. Added `background: transparent !important` to underline/wavy CSS rules
2. Set specific text-decoration colors: orange (#f97316) for underline, lime green (#84cc16) for wavy
3. Added base `background: transparent` to reset default `<mark>` yellow

**Files Modified**:
- `src/reader3_app/web/static/css/annotations.css` - Annotation styles
- `src/reader3_app/web/templates/reader.html` - Added annotations.css import (was missing!)

### Additional Fixes: Pagination Layout

**Problem**: Two-column layout appearing instead of single-column pagination.

**Solution Implemented**:
1. Added `updateColumnWidth()` function to dynamically calculate column width from container
2. Set `column-gap` to double the margin (160px) for proper page alignment
3. Removed click navigation zones (keyboard-only navigation now)

**Files Modified**:
- `src/reader3_app/web/static/js/pagination.js` - Dynamic column width
- `src/reader3_app/web/templates/reader.html` - Removed nav zone display

---

_Plan created: 2025-12-27_
_Phase 2 Status: Implemented_
_Phase 3 Status: Implemented_
_Phase 4 Status: Implemented_
