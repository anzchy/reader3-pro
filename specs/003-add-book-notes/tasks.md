# Tasks: Book Notes & Annotations

**Input**: Design documents from `/specs/003-add-book-notes/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/notes-api.yaml, quickstart.md

**Tests**: Not included (manual QA per existing project pattern - see quickstart.md for test procedures)

**Organization**: Tasks grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US0, US1, US2...)
- Include exact file paths in descriptions

## Path Conventions

Project uses existing `src/reader3_app/` structure (single FastAPI application). No separate backend/frontend directories.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create new files and directories for annotations feature

- [ ] T001 Create `src/reader3_app/models/` directory if not exists
- [ ] T002 Create `src/reader3_app/models/__init__.py` and empty `src/reader3_app/models/annotations.py` file
- [ ] T003 [P] Create empty `src/reader3_app/notes_service.py` file
- [ ] T004 [P] Create `src/reader3_app/web/static/css/toolbar.css` file
- [ ] T005 [P] Create `src/reader3_app/web/static/css/toc-panel.css` file
- [ ] T006 [P] Create `src/reader3_app/web/static/css/notes-panel.css` file
- [ ] T007 [P] Create `src/reader3_app/web/static/css/annotations.css` file
- [ ] T008 [P] Create `src/reader3_app/web/static/js/toolbar.js` file
- [ ] T009 [P] Create `src/reader3_app/web/static/js/toc-panel.js` file
- [ ] T010 [P] Create `src/reader3_app/web/static/js/notes-panel.js` file
- [ ] T011 [P] Create `src/reader3_app/web/static/js/annotations.js` file

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data structures and backend services that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Backend Foundation

- [ ] T012 Implement `Annotation` dataclass in `src/reader3_app/models/annotations.py` with fields: id, book_id, chapter_index, type, color, quote, prefix, suffix, position, note_text, created_at, orphaned
- [ ] T013 Add `__post_init__` validation to `Annotation` dataclass (validate book_id, chapter_index >=0, quote non-empty, auto-fix colors, truncate prefix/suffix to 50 chars)
- [ ] T014 Add `to_dict()` and `from_dict()` methods to `Annotation` dataclass for JSON serialization
- [ ] T015 Implement `load_annotations()` function in `src/reader3_app/notes_service.py` to read `books/{book_id}/notes.json` and return List[Annotation]
- [ ] T016 Implement `save_annotations()` function in `src/reader3_app/notes_service.py` with atomic write pattern (temp file + rename) and top-level `{schema_version: 1, book_id, annotations:[...]}` format
- [ ] T017 Implement `add_annotation()` function in `src/reader3_app/notes_service.py` (load, append, save, return id)
- [ ] T018 Implement `delete_annotation()` function in `src/reader3_app/notes_service.py` (load, filter by id, save, return success)

### API Foundation

- [ ] T019 Add `GET /api/notes/{book_id}` endpoint in `src/reader3_app/web/server.py` matching `contracts/notes-api.yaml#/components/schemas/BookAnnotationsResponse` (include `schema_version`, `book_id`, `total_count` excluding orphaned, and `annotations_by_chapter` with `chapter_title`)
- [ ] T020 Add `GET /api/notes/{book_id}/{chapter_index}` endpoint in `src/reader3_app/web/server.py` matching `contracts/notes-api.yaml#/components/schemas/ChapterAnnotationsResponse` (omit orphaned items; `count` excludes orphaned)
- [ ] T021 Add `POST /api/notes/{book_id}/{chapter_index}` endpoint in `src/reader3_app/web/server.py` matching `contracts/notes-api.yaml#/components/schemas/CreateAnnotationRequest` (validate `type`; enforce `note_text` required when `type=note`; ignore `color` for wavy/underline; escape `note_text` before saving; server generates `id` + `created_at`; return 201 response schema)
- [ ] T022 Add `DELETE /api/notes/{book_id}/{chapter_index}/{note_id}` endpoint in `src/reader3_app/web/server.py` (optional v1; match `contracts/notes-api.yaml` response/behavior)
- [ ] T023 Add book_id validation to all `/api/notes/*` endpoints (validate against `get_available_books()` enumeration)
- [ ] T024 Add chapter_index validation to all chapter-specific endpoints (validate against book.spine length)

**Checkpoint**: Backend foundation ready - frontend user story implementation can now begin in parallel

---

## Phase 3: User Story 0 - Fullscreen Reader + Right Toolbar (Priority: P0) 🎯 MVP

**Goal**: Convert reader from left-sidebar layout to fullscreen WeRead-style with right vertical toolbar

**Independent Test**: Open any book → reader displays fullscreen with centered content, light gray background, and right-side floating toolbar with 4 buttons in correct order (目录页, Search, AI, Notes)

### Layout Restructure

- [ ] T025 [US0] Modify `src/reader3_app/web/templates/reader.html` to remove left sidebar structure and add fullscreen container with centered `.book-content` area; ensure new assets are loaded via `<link>`/`<script>` tags: `/static/css/reader.css`, `/static/css/toolbar.css`, `/static/css/toc-panel.css`, `/static/css/notes-panel.css`, `/static/css/annotations.css`, and `/static/js/toolbar.js`, `/static/js/toc-panel.js`, `/static/js/notes-panel.js`, `/static/js/annotations.js` (keep existing Search/AI assets working)
- [ ] T026 [US0] Create/update `src/reader3_app/web/static/css/reader.css` to implement fullscreen layout (100vh height, centered paper container, light gray #f7f7f7 background)
- [ ] T027 [US0] Move existing TOC navigation to hidden panel mode (will be shown/hidden by toolbar button in later tasks)

### Right Toolbar Component

- [ ] T028 [P] [US0] Implement HTML structure for right toolbar in `src/reader3_app/web/templates/reader.html` (fixed position, 4 buttons; reuse existing Search/AI toggle IDs if already present; add new `reader-toc-toggle` + `reader-notes-toggle`)
- [ ] T029 [P] [US0] Implement CSS for right toolbar in `src/reader3_app/web/static/css/toolbar.css` (fixed right positioning, circular buttons, subtle shadow, icon-only style per WeRead screenshots ±2px tolerance)
- [ ] T030 [P] [US0] Add toolbar button icons and ordering (目录页 top → Search → AI → Notes bottom) in `reader.html` (Search/AI visuals may reuse existing implementations; pixel-fidelity scope is toolbar + TOC/Notes modes)
- [ ] T031 [US0] Implement `RightToolbar` class in `src/reader3_app/web/static/js/toolbar.js` with methods: constructor(), openPanel(panelName), closePanel(panelName), closeAllPanels()
- [ ] T032 [US0] Add full tool-panel mutual exclusion logic to `toolbar.js` for TOC/Notes/Search/AI (opening any one closes the other three; implement both directions by also intercepting Search/AI toggle clicks to close TOC/Notes; close Search/AI by removing `.is-open` and setting `aria-hidden="true"`)
- [ ] T033 [US0] Add active button state management in `toolbar.js` (visual highlight when panel is open)

### Keyboard & Accessibility

- [ ] T034 [P] [US0] Implement a single global Esc key handler (capture phase) in `toolbar.js` with priority order: note editor popover → selection toolbar → open tool panel (TOC/Notes/Search/AI); stop propagation when consumed; other modules should expose `closeIfOpen()` hooks (and avoid adding competing document-level Esc listeners)
- [ ] T035 [P] [US0] Add ARIA labels to toolbar buttons in `reader.html` (aria-label="目录页", "搜索", "AI助手", "笔记")
- [ ] T036 [P] [US0] Add keyboard navigation support (Tab through buttons, Enter/Space to activate) in `toolbar.js`

**Story Completion Check**: ✅ Fullscreen layout + right toolbar with mutual exclusion + Esc handling

---

## Phase 4: User Story 6 - TOC Panel (Priority: P1)

**Goal**: Implement WeRead-style TOC panel as fullscreen overlay mode (not drawer)

**Independent Test**: Click 目录页 button → TOC panel opens fullscreen with nested TOC structure + search input → click chapter → navigates and closes panel → click button again → panel closes and returns to prior reading position

### TOC Panel UI

- [ ] T037 [P] [US6] Implement TOC panel HTML structure in `src/reader3_app/web/templates/reader.html` (fullscreen overlay, search input at top, scrollable TOC list container)
- [ ] T038 [P] [US6] Implement CSS for TOC panel in `src/reader3_app/web/static/css/toc-panel.css` matching WeRead screenshots (fullscreen mode, search input styling, nested list styling, ±2px spacing tolerance)
- [ ] T039 [US6] Implement `TOCPanel` class in `src/reader3_app/web/static/js/toc-panel.js` with methods: open(), close(), handleSearch(query), navigateToChapter(href)

### TOC Functionality

- [ ] T040 [US6] Implement real-time TOC search filter in `toc-panel.js` (case-insensitive substring match on chapter titles, update list display without full-text search)
- [ ] T041 [US6] Add TOC item click handler in `toc-panel.js` (navigate to chapter using existing spine mapping logic, close panel after navigation)
- [ ] T042 [US6] Implement reading position preservation in `toc-panel.js` (save current chapter_index + scroll offset on panel open, restore on panel close)
- [ ] T043 [US6] Wire up 目录页 button to TOC panel in `toolbar.js` (call TOCPanel.open() on click, toggle behavior if already open)

### TOC Keyboard Support

- [ ] T044 [P] [US6] Expose `TOCPanel.closeIfOpen()` hook (close TOC panel, restore focus to reader) for the global Esc handler in `toolbar.js`

**Story Completion Check**: ✅ TOC panel opens/closes with search, navigation works, reading position preserved

---

## Phase 5: User Story 1 - Inline Annotation Toolbar (Priority: P1)

**Goal**: Show floating toolbar when user selects text in book content with 6 action buttons

**Independent Test**: Select text in `.book-content` → toolbar appears near selection with Copy/Marker/Wavy/Underline/Note/Ask AI buttons → click outside or press Esc → toolbar closes

### Selection Detection

- [ ] T046 [US1] Implement selection detection in `src/reader3_app/web/static/js/annotations.js` (listen for mouseup on `.book-content`, check if selection non-empty and inside .book-content)
- [ ] T047 [US1] Add HTML structure for annotation toolbar in `src/reader3_app/web/templates/reader.html` (floating div with 6 buttons, initially hidden)
- [ ] T048 [P] [US1] Implement CSS for annotation toolbar in `src/reader3_app/web/static/css/annotations.css` (floating position, button layout, z-index above content)

### Toolbar Positioning & Lifecycle

- [ ] T049 [US1] Implement toolbar positioning logic in `annotations.js` (use Range.getBoundingClientRect(), position near selection, handle viewport boundaries to avoid off-screen)
- [ ] T050 [US1] Add toolbar close logic in `annotations.js` (click outside selection, selection cleared) and expose `closeSelectionToolbarIfOpen()` for global Esc handling
- [ ] T051 [US1] Add selection outside `.book-content` guard (no toolbar shown for TOC/sidebar selections)

- [ ] T053 [US1] Ensure focus returns to reader when selection toolbar closes via global Esc

**Story Completion Check**: ✅ Annotation toolbar appears on text selection, positioned correctly, closes on Esc/click-outside

---

## Phase 6: User Story 2 - Highlight/Underline Rendering (Priority: P1)

**Goal**: Apply visual annotations (marker/wavy/underline) when user clicks toolbar buttons and persist across refreshes

**Independent Test**: Select text → click Marker → choose yellow → text highlighted with yellow background → refresh page → highlight still visible in same location

### Annotation Creation (Frontend)

- [ ] T054 [US2] Implement "Copy" button handler in `annotations.js` (copy selection text to clipboard using navigator.clipboard.writeText())
- [ ] T055 [US2] Implement "Marker" button handler in `annotations.js` (show color picker with yellow/green/pink/blue options)
- [ ] T056 [US2] Implement "Wavy" button handler in `annotations.js` (create annotation with type="wavy", no color)
- [ ] T057 [US2] Implement "Underline" button handler in `annotations.js` (create annotation with type="underline", no color)
- [ ] T058 [US2] Implement `createAnnotation()` function in `annotations.js` (extract quote, prefix 50 chars, suffix 50 chars, position from chapter plain text, POST to API)

### Annotation Rendering (Re-anchoring)

- [ ] T059 [US2] Implement `AnnotationRenderer` class in `annotations.js` with methods: loadAndRender(), findRange(chapterText, annotation), applyMark(contentEl, range, annotation)
- [ ] T060 [US2] Implement re-anchoring algorithm in `findRange()` (try prefix+quote+suffix match → fallback quote-only → return null if orphaned)
- [ ] T061 [US2] Implement DOM traversal in `applyMark()` (walk text nodes, split at annotation boundaries, wrap in `<mark>` elements with CSS classes and `data-annotation-id` for jump targeting)
- [ ] T062 [US2] Add annotation CSS classes in `src/reader3_app/web/static/css/annotations.css` (.annotation--marker with color variants, .annotation--wavy with wavy underline, .annotation--underline with straight underline)

### Persistence Integration

- [ ] T063 [US2] Call `AnnotationRenderer.loadAndRender()` on chapter load in `annotations.js` (fetch from GET /api/notes/{book_id}/{chapter_index}, render all non-orphaned annotations)
- [ ] T064 [US2] Implement orphaned annotation handling without a client update API: on `GET /api/notes/{book_id}/{chapter_index}`, server checks each non-orphaned annotation against `ChapterContent.text` (prefix+quote+suffix → fallback quote) and persists `orphaned=true` when not found; orphaned items are excluded from responses but preserved on disk
- [ ] T065 [US2] Add overlapping annotation support in CSS (layer background colors + underlines, ensure all styles visible simultaneously)

**Story Completion Check**: ✅ Marker/Wavy/Underline annotations created, rendered with correct styles, persisted across refreshes

---

## Phase 7: User Story 3 - Notes with Hover Tooltip (Priority: P1)

**Goal**: Allow users to attach text notes to selections with inline popover editor and hover tooltips

**Independent Test**: Select text → click "写想法" → popover appears → enter note → save → selection annotated → hover shows note content in tooltip → refresh → note still visible

### Note Creation UI

- [ ] T066 [US3] Add HTML structure for note editor popover in `src/reader3_app/web/templates/reader.html` (inline div with textarea, Save/Cancel buttons, initially hidden)
- [ ] T067 [P] [US3] Implement CSS for note editor popover in `src/reader3_app/web/static/css/annotations.css` (positioned near selection, elevated z-index, Save/Cancel button styling)
- [ ] T068 [US3] Implement "写想法" button handler in `annotations.js` (show note editor popover near selection, focus textarea)
- [ ] T069 [US3] Implement popover positioning logic (use selection.getBoundingClientRect(), handle viewport boundaries)

### Note Save/Cancel Logic

- [ ] T070 [US3] Implement Save button handler in `annotations.js` (create annotation with type="note", color="yellow", note_text from textarea, POST to API, close popover, render annotation)
- [ ] T071 [US3] Implement Cancel button handler and click-outside logic (close popover without creating annotation)
- [ ] T072 [US3] Add note_text HTML escaping verification (ensure backend escapes via html.escape(), frontend renders via textContent not innerHTML)

### Hover Tooltip

- [ ] T073 [US3] Implement hover tooltip display in `annotations.js` (detect mouseenter on .annotation[data-note-text], show tooltip with note_text content)
- [ ] T074 [P] [US3] Implement CSS for note hover tooltip in `src/reader3_app/web/static/css/annotations.css` (positioned near annotation, elevated z-index, max-width, word-wrap)
- [ ] T075 [US3] Add note visual priority styling in CSS (notes have highest visual priority when overlapping with other annotation types)

### Esc Integration

- [ ] T077 [US3] Expose `closeNoteEditorIfOpen()` hook in `annotations.js` (close popover, clear textarea, return focus) for the global Esc handler in `toolbar.js`

**Story Completion Check**: ✅ Note editor popover works, tooltips display on hover, notes persist, Esc closes editor

---

## Phase 8: User Story 5 - Notes Panel (All Notes) (Priority: P1)

**Goal**: Display all book annotations in fullscreen Notes panel with grouping by chapter and navigation to annotation location

**Independent Test**: Click Notes button → panel opens showing all annotations grouped by chapter → displays "已读到 X%" and "共 N 条笔记" → click annotation → navigates to chapter and scrolls to annotation → close panel → returns to prior reading position

### Notes Panel UI

- [ ] T078 [P] [US5] Implement Notes panel HTML structure in `src/reader3_app/web/templates/reader.html` (fullscreen overlay, header with book info, scrollable notes list container, empty state card)
- [ ] T079 [P] [US5] Implement CSS for Notes panel in `src/reader3_app/web/static/css/notes-panel.css` matching WeRead screenshots (fullscreen mode, header layout with cover/title/"已读到 X%"/"共 N 条笔记", list grouping styles, empty state card, ±2px spacing tolerance, ±1px font tolerance)
- [ ] T080 [US5] Implement `NotesPanel` class in `src/reader3_app/web/static/js/notes-panel.js` with methods: open(), close(), loadNotes(), renderNotes(annotations), handleNoteClick(annotationId)

### Notes Data Loading

- [ ] T081 [US5] Implement `loadNotes()` in `notes-panel.js` (fetch from GET /api/notes/{book_id}, group by chapter, sort by position within chapter)
- [ ] T082 [US5] Implement "已读到 X%" calculation (approximate: chapter_index / (total_chapters - 1), round to integer percentage)
- [ ] T083 [US5] Implement "共 N 条笔记" count (count all non-orphaned annotations of types marker/wavy/underline/note)
- [ ] T084 [US5] Implement empty state detection and display (show "你可以在这里记录本书的想法、划线、书签" when zero annotations)

### Notes Rendering & Navigation

- [ ] T085 [US5] Implement `renderNotes()` in `notes-panel.js` (create DOM elements for each annotation, group by chapter with chapter titles from book.spine, truncate long quotes to 200 chars)
- [ ] T086 [US5] Implement annotation click handler in `notes-panel.js` (navigate to chapter using `/read/{book_id}/{chapter_index}?note_id={annotation.id}`, close Notes panel)
- [ ] T087 [US5] Implement scroll-to-annotation logic in `annotations.js` on chapter load (after rendering, read `note_id` from URL, find matching `<mark data-annotation-id="...">`, scrollIntoView + briefly highlight; fallback to `position` if element not found)
- [ ] T088 [US5] Implement reading position preservation for Notes panel (save current chapter_index + scroll offset on panel open, restore on panel close)

### Notes Panel Integration

- [ ] T089 [US5] Wire up Notes button to Notes panel in `toolbar.js` (call NotesPanel.open() on click, toggle behavior if already open)
- [ ] T090 [US5] Expose `NotesPanel.closeIfOpen()` hook (close Notes panel, restore focus to reader) for the global Esc handler in `toolbar.js`

**Story Completion Check**: ✅ Notes panel displays all annotations, shows correct counts, navigation works, empty state shows

---

## Phase 9: User Story 4 - AI Integration (Priority: P2)

**Goal**: Send selected quote to AI panel when user clicks "AI 问书" button

**Independent Test**: Select text → click "AI 问书" → AI panel opens (if feature 002 enabled) with prefilled quote and context → if AI not available → shows "AI 面板未启用" message

### CustomEvent Integration

- [ ] T091 [P] [US4] Implement "AI 问书" button handler in `annotations.js` (extract quote + context, dispatch CustomEvent 'reader3:ai:ask' with payload {book_id, chapter_index, quote, context})
- [ ] T092 [P] [US4] Add graceful degradation logic (if no CustomEvent listener, show toast notification "AI 面板未启用/未加载")
- [ ] T093 [US4] Document CustomEvent contract in code comments (event name, payload structure, expected listener behavior from feature 002)

### AI Panel Listener (if feature 002 exists)

- [ ] T094 [US4] Add CustomEvent listener to existing `src/reader3_app/web/static/ai.js` to receive 'reader3:ai:ask' events and prefill AI input with quote + context
- [ ] T095 [US4] Handle AI panel auto-open on CustomEvent receipt (call `ReaderAIUI.open()`/`toggle()` to ensure the panel is visible before prefilling)

**Story Completion Check**: ✅ AI 问书 sends quote via CustomEvent, AI panel receives and displays (or graceful error if unavailable)

---

## Phase 10: Polish & Cross-Cutting Concerns

**Goal**: Final refinements, visual fidelity validation, performance optimization, accessibility enhancements

### Visual Fidelity Validation

- [ ] T096 [P] Extract exact color values from WeRead screenshots using browser DevTools color picker (toolbar button background, active state, marker colors, shadows)
- [ ] T097 [P] Update CSS files to match extracted colors (verify toolbar.css, toc-panel.css, notes-panel.css, annotations.css)
- [ ] T098 [P] Perform pixel-perfect comparison between implementation and WeRead screenshots (overlay at 50% opacity, measure spacing with DevTools ruler, verify ±2px spacing, ±1px fonts)
- [ ] T099 [P] Fix any visual fidelity discrepancies found in comparison (iterate on CSS until tolerance met)

### Performance Optimization

- [ ] T100 [P] Profile annotation rendering performance (Chrome DevTools Performance tab, measure time from API fetch to DOM render for chapter with 100 annotations)
- [ ] T101 [P] If rendering exceeds 200ms: Add `@lru_cache` to a read-path helper in `notes_service.py` (e.g., cached `load_annotations(book_id)`), cache ~50 books' annotations
- [ ] T102 [P] If still slow: Implement client-side annotation caching in `annotations.js` (store in sessionStorage after first load)
- [ ] T103 [P] Profile Notes panel rendering (measure render time for 200 annotations, target <300ms)

### Accessibility Enhancements

- [ ] T104 [P] Add missing ARIA roles to panels (role="dialog" for popover, role="navigation" for TOC panel, role="complementary" for Notes panel)
- [ ] T105 [P] Add aria-expanded attributes to toolbar buttons (indicate panel open/closed state)
- [ ] T106 [P] Implement focus trap for open panels (Tab navigation stays within panel, Shift+Tab cycles backwards)
- [ ] T107 [P] Add screen reader announcements for dynamic content (aria-live regions for annotation count updates, panel open/close)

### Error Handling & Edge Cases

- [ ] T108 [P] Add error handling for failed API calls in `annotations.js` (display user-friendly error toast, retry logic for transient failures)
- [ ] T109 [P] Add error handling for corrupted notes.json (backend catches JSON parse errors, returns empty annotations list instead of 500 error)
- [ ] T110 [P] Handle extremely long note_text (truncate display in Notes panel to 200 chars with "..." ellipsis, show full text in tooltip)
- [ ] T111 [P] Handle missing book cover images in Notes panel (display placeholder icon or book title initials)

### Browser Compatibility

- [ ] T112 [P] Test in Chrome (verify all features work, visual fidelity matches screenshots)
- [ ] T113 [P] Test in Edge (verify annotation rendering, panel behavior)
- [ ] T114 [P] Add browser compatibility notes to README if any issues found (document known limitations)

### Documentation Updates

- [ ] T115 [P] Update CLAUDE.md with annotation feature architecture (add notes.json storage, re-anchoring algorithm, CustomEvent integration to architecture section)
- [ ] T116 [P] Add annotation feature usage examples to README.md (how to create highlights, notes, use TOC/Notes panels)

**Final Checkpoint**: ✅ All user stories complete, visual fidelity verified, performance optimized, accessible

---

## Dependencies & Execution Order

### Story Dependency Graph

```text
Setup (Phase 1)
  ↓
Foundational (Phase 2) ← BLOCKING: Must complete before any user story
  ↓
├─→ US0: Fullscreen + Toolbar (P0) ← MVP Foundation
│     ↓
├─→ US6: TOC Panel (P1) ← Depends on US0 toolbar
│     ↓
├─→ US1: Selection Toolbar (P1) ← Depends on US0 Esc priority
│     ↓
├─→ US2: Annotation Rendering (P1) ← Depends on US1 selection detection
│     ↓
├─→ US3: Notes with Tooltip (P1) ← Depends on US2 annotation rendering
│     ↓
├─→ US5: Notes Panel (P1) ← Depends on US2 (needs annotations to display)
│     ↓
├─→ US4: AI Integration (P2) ← Independent, can implement anytime after US1
│     ↓
Polish (Phase 10) ← Final refinements
```

### Parallel Execution Opportunities

**After Foundational Phase Complete**:

**Parallel Group 1** (No dependencies on each other):
- US0 layout restructure (T025-T027) CAN run parallel with US0 toolbar CSS (T029)
- US6 TOC panel CSS (T038) CAN run parallel with US5 Notes panel CSS (T079)
- Setup tasks T004-T011 (create files) CAN all run in parallel

**Parallel Group 2** (After US0 Complete):
- US6 TOC panel UI (T037-T039) CAN run parallel with US1 annotation toolbar HTML/CSS (T047-T048)
- US5 Notes panel UI (T078-T079) CAN run parallel with US3 note editor UI (T066-T067)

**Parallel Group 3** (Polish Phase):
- All tasks T096-T116 marked with [P] can run in parallel (visual fidelity, performance, accessibility, error handling, browser testing)

### Sequential Constraints

**Must be sequential** (cannot parallelize):
1. T012-T014 (Annotation dataclass) BEFORE T015-T018 (notes_service using Annotation)
2. T015-T018 (notes_service) BEFORE T019-T024 (API endpoints using notes_service)
3. T025-T027 (layout restructure) BEFORE T031-T033 (toolbar.js using new layout)
4. T046-T050 (selection detection + toolbar lifecycle) BEFORE T054-T058 (annotation creation using toolbar)
5. T059-T062 (AnnotationRenderer) BEFORE T063-T065 (persistence integration calling renderer)

---

## Implementation Strategy

### MVP Scope (Minimum Viable Product)

**MVP = User Story 0 + User Story 2 (Basic Highlights)**

Delivers:
- ✅ Fullscreen WeRead-style reader with right toolbar
- ✅ Create marker highlights (yellow/green/pink/blue)
- ✅ Highlights persist across refreshes
- ✅ Basic annotation rendering (no notes, no Notes panel yet)

**MVP Tasks**: T001-T024 (Setup + Foundational) + T025-T036 (US0) + T054-T065 (US2 core)

**Estimated MVP Time**: 3-4 days (1 FTE)

### Incremental Delivery Plan

**Increment 1 (MVP)**: Fullscreen layout + basic highlights
- Delivers: Core value proposition (persistent annotations in WeRead UI)
- User can: Create and view color-coded highlights

**Increment 2**: Add TOC panel (US6) + Selection toolbar (US1)
- Delivers: Complete navigation UX + annotation creation flow
- User can: Browse TOC with search, create annotations via toolbar

**Increment 3**: Add Notes panel (US5) + Note tooltips (US3)
- Delivers: Complete annotation management + note-taking
- User can: View all annotations, add/read text notes

**Increment 4**: Add AI integration (US4) + Polish
- Delivers: AI question feature + production-ready quality
- User can: Ask AI about selected text, uses WeRead-style toolbar + TOC/Notes modes

### Task Estimation

**Total Tasks**: 113
- Phase 1 (Setup): 11 tasks (~1 hour)
- Phase 2 (Foundational): 13 tasks (~1 day)
- Phase 3 (US0): 12 tasks (~1 day)
- Phase 4 (US6): 8 tasks (~0.5 day)
- Phase 5 (US1): 7 tasks (~0.5 day)
- Phase 6 (US2): 12 tasks (~1.5 days)
- Phase 7 (US3): 11 tasks (~1 day)
- Phase 8 (US5): 13 tasks (~1.5 days)
- Phase 9 (US4): 5 tasks (~0.5 day)
- Phase 10 (Polish): 21 tasks (~1 day)

**Total Estimated Time**: 7-8 days (1 FTE developer, full-time)

### Risk Mitigation

**High-Risk Tasks** (require extra attention):
- T060-T061: Re-anchoring algorithm (complex DOM traversal, edge cases)
- T086-T087: Scroll-to-annotation (coordinate calculation, viewport positioning)
- T098-T099: Visual fidelity validation (subjective, iterative refinement)
- T100-T103: Performance optimization (may require multiple iterations)

**Mitigation Strategy**:
- Implement T060-T061 early, allocate extra time for edge case testing
- Use existing search highlighting code as reference for DOM traversal
- Take screenshots after each CSS change for visual regression detection
- Profile early and often (after T063, T081, T085)

---

## Task Validation

✅ **Format Check**: All 113 tasks follow checklist format with checkbox, ID, optional [P]/[Story] markers, and file paths
✅ **Story Coverage**: All 7 user stories (US0-US6, US4) have complete task sets
✅ **Independence**: Each user story phase has independent test criteria
✅ **Parallelization**: 42 tasks marked [P] for parallel execution opportunities
✅ **Dependencies**: Clear sequential constraints documented
✅ **Completeness**: All files from plan.md project structure covered (models, services, endpoints, CSS, JS)
✅ **Traceability**: Tasks map to acceptance scenarios in spec.md
