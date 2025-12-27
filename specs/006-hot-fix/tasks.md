# 006-hot-fix Tasks

## Summary

UI improvements for Settings page and Reader page.

---

## Phase 1: UI Cleanup (Completed)

### Task 1: Settings Page - Collapsible Provider Configs
- [x] **Status**: Completed
- **Description**: Settings 页面的 Providers 区域中所有的模型配置折叠起来，不需要摊开。当用户在 AI Preference 选定 AI model provider 之后，下面 Providers 只显示对应的 AI model 的配置展开，其他的模型配置默认折叠。
- **Files Modified**:
  - `src/reader3_app/web/static/settings.js` - Added collapsible card functionality with toggle on header click
  - `src/reader3_app/web/static/settings.css` - Added chevron animation and expand/collapse styles

### Task 2: Settings Page - Provider Cards Collapse on Demand
- [x] **Status**: Completed
- **Description**: 同 Task 1，确保所有 provider cards 都可以按需折叠显示。
- **Files Modified**: Same as Task 1

### Task 3: Reader Page - Remove Top Header Bar
- [x] **Status**: Completed
- **Description**: 去掉 Reader 页面上面的顶栏，把 back to Library button 移动到右边 ToC button 上面。
- **Files Modified**:
  - `src/reader3_app/web/templates/reader.html` - Removed header element and related CSS

### Task 4: Reader Page - Reorganize Right Sidebar Buttons
- [x] **Status**: Completed
- **Description**: back to Library button 放在右侧工具栏最上面，将星星图标换成机器人 icon 用于 AI Assistant。
- **Files Modified**:
  - `src/reader3_app/web/templates/reader.html` - Added back-to-library link at top of right toolbar, changed star SVG to robot icon

### Task 5: Fix Text Selection Popup for Notes/Highlighting
- [x] **Status**: Completed
- **Description**: 在电子书页面选择文字时，无法弹出划线以及记录笔记的功能。修复 CSS class 不匹配问题。
- **Root Cause**: CSS expected `.is-visible` class but JavaScript was adding `.is-open` class
- **Files Modified**:
  - `src/reader3_app/web/static/js/annotations.js` - Changed all `is-open` to `is-visible` to match CSS selectors

### Task 6: Reader Page - Remove Bottom Footer Bar
- [x] **Status**: Completed
- **Description**: 去掉 Reader 页面最下面的 bottom bar (footer)。导航功能已在 chapter-nav 和右侧工具栏中提供。
- **Files Modified**:
  - `src/reader3_app/web/templates/reader.html` - Removed footer element and all footer-related CSS, updated panel positions from `bottom: var(--dedao-footer-height)` to `bottom: 0`

---

## Phase 2: Full-Screen Paginated Reader (Completed)

> See `spec.md` section "Feature Specification: Full-Screen Paginated Reader" for detailed requirements.
> See `plan.md` for implementation architecture and technology decisions.

### User Story 1 — Full-Width Content Display (P1)

**Goal**: Content uses full viewport width with 80px margins for immersive reading.

**Acceptance Test**: Open a book chapter → content area is `100vw - 160px` wide.

- [x] T007 [US1] Add CSS variables for reader layout in `src/reader3_app/web/templates/reader.html`
  - `--reader-margin-x: 80px`
  - `--reader-padding-top: 40px`
  - `--reader-padding-bottom: 60px`
  - `--reader-nav-zone-width: 120px`
  - `--reader-transition-duration: 180ms`
  - `--reader-min-pagination-width: 600px`
- [x] T008 [US1] Remove narrow card constraint (`max-width: 768px`) from `#main` in `src/reader3_app/web/templates/reader.html`
- [x] T009 [US1] Update `.content-container` to use full width with 80px margins in `src/reader3_app/web/templates/reader.html`
- [x] T010 [US1] Remove card shadow from `.content-container` for clean reading experience in `src/reader3_app/web/templates/reader.html`
- [x] T011 [US1] Add mobile fallback: disable wide layout for viewports < 600px in `src/reader3_app/web/templates/reader.html`

**Requirements**: FR-R001, FR-R002, FR-R003, FR-R004

### User Story 2 — Automatic Content Pagination (P1)

**Goal**: Content flows horizontally into discrete pages without vertical scrolling.

**Acceptance Test**: Long chapter content divides into pages → no vertical scrollbar → pages flip horizontally.

- [x] T012 [US2] Create pagination container wrapper (`.pagination-container`) with CSS in `src/reader3_app/web/templates/reader.html`
  - `overflow-x: auto`, `scroll-snap-type: x mandatory`
  - Full viewport height minus header/footer padding
- [x] T013 [US2] Apply CSS Multi-column Layout to `.book-content` in `src/reader3_app/web/templates/reader.html`
  - `column-width: calc(100vw - 160px)`
  - `column-fill: auto`
  - `column-gap: 0`
  - `height: calc(100vh - 100px)`
- [x] T014 [US2] Add `break-inside: avoid` to block elements (p, img, blockquote, table) in `src/reader3_app/web/templates/reader.html`
- [x] T015 [US2] Add image scaling rule: `max-height: calc(100vh - 120px)` to prevent overflow in `src/reader3_app/web/templates/reader.html`
- [x] T016 [US2] Create `src/reader3_app/web/static/js/pagination.js` with core module structure
  - `initPagination()` - entry point
  - `calculatePages()` - compute total pages from scrollWidth/clientWidth
  - `isPaginationEnabled()` - check viewport >= 600px
- [x] T017 [US2] Implement resize handler with position preservation in `src/reader3_app/web/static/js/pagination.js`
  - Track scroll position as percentage before resize
  - Restore approximate position after reflow

**Requirements**: FR-R005, FR-R006, FR-R007, FR-R008, FR-R009

### User Story 3 — Page Navigation (P1)

**Goal**: Navigate between pages via keyboard arrows and clickable edge zones.

**Acceptance Test**: Press → key → advance one page → press ← key → go back one page.

- [x] T018 [US3] Add keyboard navigation (←/→ arrow keys) in `src/reader3_app/web/static/js/pagination.js`
  - `navigateToPage(pageNum)` - scroll to page N
  - Handle edge cases: first/last page of section
- [x] T019 [US3] Add invisible click zones (120px width) on left/right edges in `src/reader3_app/web/templates/reader.html`
  - `.nav-zone-left`, `.nav-zone-right` - fixed positioned, transparent
  - `cursor: pointer` on hover
- [x] T020 [US3] Implement click handlers for edge zones in `src/reader3_app/web/static/js/pagination.js`
  - Left zone → previous page
  - Right zone → next page
- [x] T021 [US3] Add smooth page transition animation (180ms ease) in `src/reader3_app/web/static/js/pagination.js`
  - Use `scrollTo({ left: x, behavior: 'smooth' })` or CSS scroll-snap
- [x] T022 [US3] Implement cross-section navigation in `src/reader3_app/web/static/js/pagination.js`
  - Last page + next → navigate to `/read/{book_id}/{next_idx}`
  - First page + prev → navigate to `/read/{book_id}/{prev_idx}`
- [x] T023 [US3] Ensure side panels (TOC, Search, AI, Notes) overlay on top of content in `src/reader3_app/web/templates/reader.html`
  - Verify z-index ordering: panels > nav zones > content
  - Content pagination remains unchanged when panels open

**Requirements**: FR-R010, FR-R011, FR-R012, FR-R013, FR-R019

### User Story 4 — Reading Progress Indicator (P2)

**Goal**: Display current reading progress as percentage at bottom of viewport.

**Acceptance Test**: Navigate to page 3 of 10 → indicator shows "当前阅读至 30%".

- [x] T024 [US4] Add progress indicator HTML element in `src/reader3_app/web/templates/reader.html`
  - `.reading-progress` - fixed bottom, centered
  - Semi-transparent background, small font
- [x] T025 [US4] Style progress indicator (non-intrusive) in `src/reader3_app/web/templates/reader.html`
  - `position: fixed; bottom: 16px`
  - `font-size: 12px; color: var(--dedao-light)`
  - `background: rgba(255,255,255,0.8); padding: 4px 12px; border-radius: 12px`
- [x] T026 [US4] Implement progress calculation in `src/reader3_app/web/static/js/pagination.js`
  - `updateProgress()` - calculate `round(currentPage / totalPages * 100)`
  - Call on page change and initial load
- [x] T027 [US4] Handle single-page sections: show "100%" immediately in `src/reader3_app/web/static/js/pagination.js`
- [x] T028 [US4] Wire progress update to scroll/navigation events in `src/reader3_app/web/static/js/pagination.js`

**Requirements**: FR-R014, FR-R015, FR-R016, FR-R017, FR-R018

### Polish & Integration

- [x] T029 Include `pagination.js` script in `src/reader3_app/web/templates/reader.html`
- [ ] T030 Test annotation toolbar positioning with new layout in browser
- [ ] T031 Test all side panels (TOC, Notes, Search, AI) overlay correctly
- [ ] T032 Verify mobile fallback (< 600px viewport) uses vertical scroll
- [ ] T033 Browser compatibility testing: Chrome, Safari, Firefox, Edge

---

## Dependencies

```text
Phase 1 (Completed) → US1 (Layout) → US2 (Pagination) → US3 (Navigation) → US4 (Progress) → Polish
                           │              │                   │                  │
                           └──────────────┴───────────────────┴──────────────────┘
                                     All depend on previous
```

## Parallel Execution Opportunities

Tasks can be parallelized when they modify **different files**:
- **US1**: T007-T011 are sequential (all modify `reader.html`)
- **US2**: T012-T015 (HTML/CSS in `reader.html`) then T016-T017 (JS in `pagination.js`) - sequential within file groups
- **US3**: T019 (HTML) sequential with US2 CSS; T018, T020-T022 (JS) can follow T016-T017
- **US4**: T024-T025 (HTML/CSS) sequential; T026-T028 (JS) can follow after T016-T017

**True parallelization**: Once `reader.html` CSS tasks complete, JS tasks in `pagination.js` can proceed independently.

---

## Implementation Notes

### Settings Page Changes
- Provider cards are now collapsible with a clickable header
- Chevron icon rotates to indicate expand/collapse state
- Only the provider matching the selected "Default provider" in AI Preferences is expanded by default
- Click any provider header to toggle expand/collapse

### Reader Page Changes
- Removed top header bar for cleaner reading experience
- Removed bottom footer bar for more reading space
- Back-to-library navigation moved to right toolbar (top position)
- AI Assistant icon changed from star to robot icon
- All side panels (TOC, Notes, Search, AI) now extend full height (`top: 0` to `bottom: 0`)
- Chapter navigation available via:
  - Previous/Next buttons in content area
  - TOC sidebar

### Annotation System Fix
- Fixed CSS class mismatch that prevented annotation toolbar from appearing
- All popup elements now correctly use `is-visible` class

---

## Phase 3: Bug Fixes & Enhancements

> See `spec.md` Phase 3 section for detailed requirements (FR-P3-001 to FR-P3-014).
> See `plan.md` Phase 3 section for technical analysis and solution approach.

### Issue 1 — First Page Content Overflow (Bug Fix, P1)

**Goal**: Fix left-side content overflow on first page of each chapter.

**Acceptance Test**: Open any chapter → first page content is fully within 80px left margin.

- [x] T034 [Issue1] Debug CSS columns first-page margin issue in `reader.html`
  - Changed from `padding: 0 80px` to `margin-left: 80px` on `.book-content`
  - Added `box-sizing: content-box` for accurate column-width calculation
  - Added `container.scrollLeft = 0` reset in pagination.js initialization
- [x] T035 [Issue1] Verify fix works across multiple chapters and book content types

**Requirements**: FR-P3-001

### Issue 2 — AI Chat Panel Width & Resizable (Enhancement, P2)

**Goal**: Increase AI panel default width to 546px and enable manual resize.

**Acceptance Test**: Open AI panel → width is 546px → drag left edge to resize → close/reopen retains width.

- [x] T036 [Issue2] Update AI panel CSS to use `--ai-panel-width: 546px` variable in `reader.html`
- [x] T037 [Issue2] Add resize handle element (`.ai-resize-handle`) to AI sidebar HTML
- [x] T038 [Issue2] Style resize handle (vertical bar, cursor: ew-resize) in `reader.html`
- [x] T039 [Issue2] Implement drag-to-resize JavaScript for AI panel
  - mousedown on handle → track movement → update panel width
  - Constrain: min 320px, max 800px
- [x] T040 [Issue2] Persist resized width to localStorage (`reader3-ai-panel-width`)
- [x] T041 [Issue2] Restore saved width on page load

**Requirements**: FR-P3-002, FR-P3-003, FR-P3-004, FR-P3-005

### Issue 3 — Annotation/Highlight/Notes Not Working (Bug Fix, P1)

**Goal**: Restore text selection popup functionality for highlighting, copying, and notes.

**Acceptance Test**: Select text in book content → annotation toolbar appears → highlight works.

- [x] T042 [Issue3] Debug annotation toolbar visibility with pagination container
  - Lowered nav zones z-index from 25 to 15 (below annotation toolbar at 100)
- [x] T043 [Issue3] Update nav zone click handlers to check for text selection
  - Added `hasActiveSelection()` check to skip navigation when text is selected
- [x] T044 [Issue3] Removed ineffective scroll-snap-align from child elements

**Requirements**: FR-P3-006, FR-P3-007, FR-P3-008

### Issue 4 — Font Settings Panel (New Feature, P2)

**Goal**: Add font settings button with popup UI for adjusting font size and paragraph spacing.

**Acceptance Test**: Click Aa button → popup opens → adjust font size → text size changes → persists on reload.

- [x] T045 [Issue4] Add "Aa" (font settings) button to right toolbar in `reader.html`
  - Position: between AI Assistant and Notes buttons
- [x] T046 [Issue4] Create font settings popup HTML structure in `reader.html`
  - Theme selector (4 options: 白色/黄色/护眼/夜间) - UI only, disabled
  - Font size control: [-] [value] [+] with current value display
  - Paragraph spacing control: [-] [value] [+] with current value display
  - Font family selector (4 options) - UI only, disabled
- [x] T047 [Issue4] Style font settings popup in `reader.html`
  - Position: fixed right 68px, centered vertically
  - Clean grid layout for controls
- [x] T048 [Issue4] Implement font settings JavaScript
  - Toggle popup visibility on button click
  - Close popup on outside click
  - Increment/decrement handlers for font size (14-24px, step 1)
  - Increment/decrement handlers for line-height (1.5-2.5, step 0.1)
- [x] T049 [Issue4] Apply font changes to `.book-content` via CSS custom properties
  - `--reader-font-size: 17px` (default)
  - `--reader-line-height: 1.9` (default)
- [x] T050 [Issue4] Persist font settings to localStorage (`reader3-font-settings`)
- [x] T051 [Issue4] Restore font settings on page load
- [x] T052 [Issue4] Trigger pagination recalculation when font settings change

**Requirements**: FR-P3-009, FR-P3-010, FR-P3-011, FR-P3-012, FR-P3-013, FR-P3-014

### Phase 3 Polish & Testing

- [x] T053 Verify all 4 issues fixed in Chrome
- [ ] T054 Cross-browser testing: Safari, Firefox, Edge
- [x] T055 Test font settings + pagination interaction (page count changes)

---

## Phase 4: Annotation System Enhancements (Completed)

> See `spec.md` Phase 4 section for detailed requirements (FR-P4-001 to FR-P4-010).
> See `plan.md` Phase 4 section for technical implementation details.

### Issue 5 — Annotation Toggle Behavior (P1)

**Goal**: Clicking same annotation type on already-annotated text removes the annotation.

**Acceptance Test**: Select wavy-annotated text → click Wavy → annotation is removed.

- [x] T056 [Issue5] Add `toggleAnnotation(type)` method to check for existing annotations
- [x] T057 [Issue5] Add `getExistingAnnotationIds(type)` to find overlapping annotations by type
- [x] T058 [Issue5] Add `deleteAnnotations(ids)` to delete multiple annotations via API
- [x] T059 [Issue5] Update `handleAction()` to use toggle for wavy/underline actions
- [x] T060 [Issue5] Add `toggleMarkerAnnotation(color)` for marker color toggle
- [x] T061 [Issue5] Add Delete button to annotation toolbar HTML/CSS

**Requirements**: FR-P4-001, FR-P4-002

### Issue 6 — Click-to-Select Annotated Text (P1)

**Goal**: Click on annotated `<mark>` element to select text and show toolbar.

**Acceptance Test**: Click on highlight → text is selected → toolbar appears → click note → editor opens with existing content.

- [x] T062 [Issue6] Add `onAnnotationClick(e)` handler for `<mark>` elements in content
- [x] T063 [Issue6] Implement text selection via `Range.selectNodeContents()` on mark element
- [x] T064 [Issue6] Position and show toolbar after annotation click
- [x] T065 [Issue6] Add `openNoteEditorWithExisting(noteText, annotationIds)` for editing notes
- [x] T066 [Issue6] Update `saveNote()` to detect editing mode and use PUT request
- [x] T067 [Issue6] Add `update_annotation()` function to `notes_service.py`
- [x] T068 [Issue6] Add `UpdateAnnotationRequest` model to `server.py`
- [x] T069 [Issue6] Add PUT endpoint `/api/notes/{book_id}/{chapter_index}/{note_id}` to `server.py`

**Requirements**: FR-P4-003, FR-P4-004, FR-P4-005

### Issue 7 — Notes Panel UI Redesign (P2)

**Goal**: Redesign Notes panel with Dedao-style UI, chapter grouping, and copy functionality.

**Acceptance Test**: Open Notes panel → notes grouped by chapter → click "复制全部笔记" → copied to clipboard.

- [x] T070 [Issue7] Redesign Notes panel HTML structure (header, body, footer)
- [x] T071 [Issue7] Add chapter group headers with orange background styling
- [x] T072 [Issue7] Add note item icons (A for highlights, speech bubble for notes)
- [x] T073 [Issue7] Add footer buttons ("点评此书", "复制全部笔记")
- [x] T074 [Issue7] Implement `copyAllNotes()` function for Markdown export
- [x] T075 [Issue7] Update notes-panel.js to use new structure

**Requirements**: FR-P4-006, FR-P4-007, FR-P4-008

### Issue 8 — Annotation Style Fixes (P1)

**Goal**: Fix underline/wavy to show only line decoration without yellow background.

**Acceptance Test**: Create underline annotation → shows only orange underline, no background.

- [x] T076 [Issue8] Add `annotations.css` import to reader.html (was missing)
- [x] T077 [Issue8] Update underline CSS to `background: transparent`, orange text-decoration
- [x] T078 [Issue8] Update wavy CSS to `background: transparent`, lime green text-decoration
- [x] T079 [Issue8] Add base `background: transparent` to reset default mark yellow

**Requirements**: FR-P4-009, FR-P4-010

### Additional Fixes — Pagination Layout

**Goal**: Fix two-column layout issue and simplify navigation to keyboard-only.

- [x] T080 Add `updateColumnWidth()` function to pagination.js for dynamic column calculation
- [x] T081 Set column-gap to 160px (double margin) for proper page alignment
- [x] T082 Remove click navigation zones (keyboard-only navigation)
- [x] T083 Fix annotation toolbar layout (horizontal instead of vertical)
- [x] T084 Fix note editor positioning with viewport boundary checks

---

## Phase 4 Dependencies

```text
Issue 8 (T076-T079) ─┐
                     ├─→ Issue 5 (T056-T061) ─→ Issue 6 (T062-T069)
Issue 7 (T070-T075) ─┘                              ↓
                                              All Complete
```

---

## Phase 3 Dependencies

```text
Issue 1 (T034-T035) ─┐
                     ├─→ Issue 3 (T042-T044) ─→ Polish (T053-T055)
Issue 2 (T036-T041) ─┘        ↑
                     Issue 4 (T045-T052) ─┘
```

**Notes**:
- Issue 1 and Issue 2 can be done in parallel (different code areas)
- Issue 3 should follow Issue 1 (may share root cause in pagination CSS)
- Issue 4 is independent but should trigger pagination recalculation

---

_Phase 1 Completed: 2025-12-27_
_Phase 2 Completed: 2025-12-27_
_Phase 3 Completed: 2025-12-27 (T034-T055, cross-browser testing T054 pending)_
_Phase 4 Completed: 2025-12-27 (T056-T084, all annotation enhancements implemented)_

---

## Phase 5: Renderer Refactor (epub.js) (Implemented)

> See `spec.md` Phase 5 section for requirements (FR-RF-001 to FR-RF-008).
> See `plan.md` Phase 5 section for architecture and integration plan.

### Issue 9 — epub.js Renderer Integration (P1)

**Goal**: Replace direct HTML injection with epub.js rendering inside an isolated iframe.

**Acceptance Test**: Chapter renders via epub.js; clicking annotated text opens toolbar reliably.

- [x] T085 [Issue9] Persist original `.epub` alongside processed data
  - `src/reader3_app/reader3.py`
- [x] T086 [Issue9] Serve `book.epub` and expose `epub_url` to the reader template
  - `src/reader3_app/web/server.py`, `src/reader3_app/web/templates/reader.html`
- [x] T087 [Issue9] Add epub.js vendor deps and load renderer bootstrap
  - `src/reader3_app/web/static/vendor/epub.min.js`, `src/reader3_app/web/static/vendor/jszip.min.js`, `reader.html`
- [x] T088 [Issue9] Implement `epub-renderer.js` (mount, display, progress, TOC sync)
  - `src/reader3_app/web/static/js/epub-renderer.js`
- [x] T089 [Issue9] Use epub.js pagination for page turns (Left/Right) and chapter jumps (Up/Down)
  - `src/reader3_app/web/static/js/epub-renderer.js`

### Issue 10 — Iframe Bridge for Annotations (P1)

**Goal**: Make annotations work reliably inside iframe-rendered content.

**Acceptance Test**: Click marker/underline/wavy -> selection + toolbar; notes open for editing.

- [x] T090 [Issue10] Expose `window.Reader3Epub` helpers for iframe selection/content
  - `src/reader3_app/web/static/js/epub-renderer.js`
- [x] T091 [Issue10] Update annotations to read selection from iframe + store optional CFI
  - `src/reader3_app/web/static/js/annotations.js`
- [x] T092 [Issue10] Allow color for underline/wavy in API + model
  - `src/reader3_app/models/annotations.py`, `src/reader3_app/web/server.py`
- [x] T093 [Issue10] Re-apply annotations on render/chapter change events
  - `src/reader3_app/web/static/js/annotations.js`
- [x] T094 [Issue10] Redesign annotation toolbar for color-first workflow
  - `src/reader3_app/web/templates/reader.html`, `src/reader3_app/web/static/css/annotations.css`, `src/reader3_app/web/static/js/annotations.js`

### Issue 11 — Reader Panels & Focus (P1)

**Goal**: Ensure panels close on content click/Esc and keyboard navigation keeps working.

- [x] T102 [Issue11] Close TOC/Notes/Search/AI on content click or Esc
  - `src/reader3_app/web/static/js/toolbar.js`, `src/reader3_app/web/static/js/epub-renderer.js`
- [x] T103 [Issue11] Blur panel inputs on close to restore arrow-key navigation
  - `src/reader3_app/web/static/js/toolbar.js`
- [x] T104 [Issue11] Ensure back-to-library button navigates without toolbar interception
  - `src/reader3_app/web/static/js/toolbar.js`

### Issue 12 — Search/Notes with Iframe Content (P2)

**Goal**: Keep search highlights and notes panel synced with iframe-rendered content.

- [x] T105 [Issue12] Move in-chapter search highlight logic into iframe document
  - `src/reader3_app/web/static/search.js`
- [x] T106 [Issue12] Refresh notes panel on epub.js chapter change events
  - `src/reader3_app/web/static/js/notes-panel.js`, `src/reader3_app/web/static/js/epub-renderer.js`

### Issue 13 — Annotation Rendering Reliability (P2)

**Goal**: Ensure annotations render consistently without manual refresh.

- [x] T107 [Issue13] Render annotations on `reader3:content:rendered` and after create/delete
  - `src/reader3_app/web/static/js/annotations.js`
- [x] T108 [Issue13] Apply colored underline/wavy/marker styles in iframe
  - `src/reader3_app/web/static/js/epub-renderer.js`, `src/reader3_app/web/static/css/annotations.css`

### Phase 5 Polish & Docs

- [x] T109 Update technical docs for new `book.epub` storage + epub.js renderer
  - `docs/technical-detail.md`, `docs/storage-and-data-locations.md`, `docs/ai-providers-and-privacy.md`
- [x] T110 Update repo guidance docs (README/AGENTS/CLAUDE/specs)
  - `README.md`, `AGENTS.md`, `CLAUDE.md`, `specs/006-hot-fix/spec.md`, `specs/006-hot-fix/plan.md`, `specs/006-hot-fix/tasks.md`
- [ ] T111 Manual regression: annotations (click/delete/edit), search, TOC, AI panel, notes panel
