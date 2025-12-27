# Feature Specification: Full-Screen Paginated Reader

**Feature Branch**: `006-hot-fix`
**Created**: 2025-12-27
**Status**: Implemented (Phase 1-4 Complete)
**Input**: User description: "Reader page 目前的章节显示不是 full screen，两边有大量的空白，而且内容没有自动分页。期望效果是每一个 section 内容根据浏览器页面自动分页，两边各留出 80px 的空白。"

## Overview

### Problem Statement

The current reader page uses a narrow card-based layout (`max-width: 768px`) that wastes significant screen real estate on wide monitors. Content scrolls vertically without pagination, which differs from the familiar "page-turning" experience of physical books and dedicated e-readers.

**Current issues**:
- Content is constrained to a narrow card container centered on the page
- Large empty spaces exist on both sides of the content (visible whitespace)
- Content scrolls vertically without discrete page breaks
- Poor reading experience on wide screens (wasted space, overly long line lengths in some cases)

### Desired State

Transform the reader into a full-screen paginated experience similar to professional e-reader apps (e.g., Dedao 得到, Apple Books):
- Content fills the viewport width with consistent margins (80px on each side)
- Content is automatically paginated horizontally based on viewport dimensions
- Users navigate between pages like turning pages in a book
- Reading progress indicator shows percentage completion

## Definitions

- **Page**: A viewport-sized "slice" of chapter content; content flows horizontally into multiple pages.
- **Section**: A chapter/spine item in the EPUB structure; contains one or more pages.
- **Pagination**: Automatic horizontal division of content based on viewport height and width.
- **Reading progress**: Percentage of current section consumed (e.g., "当前阅读至 20%").

## Assumptions

- Single-column layout is acceptable for v1; multi-column layouts (magazine style) are out of scope.
- Touch gestures (swipe) are desirable but not required for v1 (keyboard/click navigation is sufficient).
- Images and block elements may occasionally cause suboptimal page breaks; this is acceptable for v1.

## User Scenarios & Testing

### User Story 1 — Full-Width Content Display (Priority: P1)

As a reader, I want the chapter content to use the full browser width (minus margins) so that I can make better use of my screen space and have a more immersive reading experience.

**Acceptance Scenarios**:

1. **Given** the user opens a book chapter, **When** the page loads, **Then** the content area extends to the full viewport width minus 80px margins on each side.
2. **Given** the viewport is 1200px wide, **When** content renders, **Then** the reading area is 1040px wide (1200 - 80 - 80).
3. **Given** the user resizes the browser window, **When** the viewport changes, **Then** the content area adjusts responsively while maintaining 80px margins.

### User Story 2 — Automatic Content Pagination (Priority: P1)

As a reader, I want chapter content to be automatically divided into pages based on my viewport so that I can read in discrete pages without vertical scrolling.

**Acceptance Scenarios**:

1. **Given** a chapter with content taller than the viewport, **When** the page renders, **Then** content is divided into horizontal "pages" using CSS columns or similar technique.
2. **Given** content is paginated, **When** viewing page 1, **Then** only page 1 content is visible (no partial page 2 content showing).
3. **Given** the user resizes the viewport, **When** dimensions change significantly, **Then** pagination recalculates and content reflows appropriately.

### User Story 3 — Page Navigation (Priority: P1)

As a reader, I want to navigate between pages within a section so that I can read through content page by page.

**Acceptance Scenarios**:

1. **Given** a paginated section with multiple pages, **When** the user presses the right arrow key or clicks the right edge, **Then** the view advances to the next page with smooth animation.
2. **Given** the user is on the last page of a section, **When** they navigate "next", **Then** they are taken to the next section (if available).
3. **Given** the user is on the first page of a section, **When** they navigate "previous", **Then** they are taken to the last page of the previous section (if available).

### User Story 4 — Reading Progress Indicator (Priority: P2)

As a reader, I want to see my reading progress within the current section so that I know how much content remains.

**Acceptance Scenarios**:

1. **Given** a paginated section, **When** the user views page 3 of 10, **Then** a progress indicator shows "当前阅读至 30%" or similar.
2. **Given** the user navigates between pages, **When** page changes, **Then** the progress indicator updates in real-time.
3. **Given** the progress indicator is visible, **When** reading, **Then** it does not obscure any content (positioned in a non-intrusive location).

## Requirements

### Functional Requirements

#### Layout & Margins

- **FR-R001**: Reader content area MUST use the full viewport width minus 80px margins on each side (`padding: 0 80px` or equivalent).
- **FR-R002**: Reader MUST remove the narrow card container constraint (`max-width: 768px` removed).
- **FR-R003**: Reader layout MUST maintain consistent 80px margins on all viewport sizes ≥ 600px; for viewports < 600px, pagination MUST be disabled and fall back to vertical scroll.
- **FR-R004**: Reader content background SHOULD be clean (no card shadow) to create an immersive reading experience.

#### Pagination

- **FR-R005**: Reader MUST implement horizontal pagination using CSS Multi-column Layout (`column-width`, `column-fill: auto`, `column-gap`) or equivalent technique.
- **FR-R006**: Each "page" MUST fit within the visible viewport height (content does not overflow vertically within a page).
- **FR-R007**: Pagination MUST recalculate when viewport dimensions change (resize event); the reader MUST preserve approximate reading position after reflow.
- **FR-R008**: Reader MUST use `break-inside: avoid` on block elements (paragraphs, images, blockquotes) to prevent mid-element page breaks where possible.
- **FR-R009**: Images larger than viewport height SHOULD be scaled to fit within a single page.

#### Navigation

- **FR-R010**: Reader MUST support page navigation via:
  - Left/Right arrow keys
  - Click/tap on left/right screen edges (clickable zones of 120px width)
  - Previous/Next UI buttons (if visible)
- **FR-R011**: Page transitions MUST use smooth horizontal animation (CSS `transform: translateX()` or scroll-snap).
- **FR-R012**: Navigating past the last page of a section MUST load the next section (via existing `/read/{book_id}/{index}` route).
- **FR-R013**: Navigating before the first page of a section MUST load the previous section.

#### Progress Indicator

- **FR-R014**: Reader MUST display reading progress as a percentage (e.g., "当前阅读至 20%").
- **FR-R015**: Progress percentage MUST be calculated as: `round(currentPage / totalPages * 100)`.
- **FR-R016**: Progress indicator MUST update in real-time as the user navigates between pages.
- **FR-R017**: Progress indicator MUST be positioned at the bottom of the viewport in a non-intrusive manner (e.g., small text, semi-transparent background).
- **FR-R018**: For single-page sections, progress indicator MUST show "100%" or "1/1" immediately (not hidden).
- **FR-R019**: When side panels (TOC, Search, AI, Notes) are open, they MUST overlay on top of the paginated content; content area and pagination remain unchanged.

### Non-Functional Requirements

- **NFR-R001**: Page transitions MUST complete in ≤ 200ms.
- **NFR-R002**: Pagination calculation MUST complete in ≤ 100ms for typical chapters (< 50KB content).
- **NFR-R003**: Reader MUST remain responsive during pagination recalculation (no UI freeze).
- **NFR-R004**: Keyboard navigation MUST be accessible; focus indicators MUST be visible.

### Technical Specifications

| Property | Value |
|----------|-------|
| Left margin | 80px |
| Right margin | 80px |
| Top padding | 40px |
| Bottom padding | 60px (space for progress indicator) |
| Page transition duration | 160–200ms ease |
| Min viewport width for pagination | 600px |
| Clickable navigation zone width | 120px (each side) |

### Browser Compatibility

- Chrome 90+
- Safari 14+
- Firefox 88+
- Edge 90+

### CSS Technologies

- CSS Multi-column Layout (`column-width`, `column-gap`, `column-fill`)
- CSS Scroll Snap (`scroll-snap-type: x mandatory`) for page alignment
- CSS `break-inside: avoid` for preventing awkward element breaks
- CSS Transforms for page transition animations

## UI/UX Design Reference

### Current Layout (Problem)

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│      ┌─────────────────────────────────┐                │
│      │                                 │                │
│      │   Narrow card with content      │                │
│      │   max-width: 768px              │                │
│      │                                 │                │
│      │   (lots of wasted space)        │                │
│      │                                 │                │
│      └─────────────────────────────────┘                │
│                                                         │
│  ← Large empty space    Large empty space →             │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Desired Layout

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  80px  ┌─────────────────────────────────────┐  80px    │
│   ←    │                                     │    →     │
│        │  Full-width paginated content       │          │
│        │                                     │          │
│        │  八、中介服务能力不够                   │          │
│        │  ——牌照业务下的艰难转型                 │          │
│        │                                     │          │
│        │  Content flows horizontally         │          │
│        │  into multiple "pages"              │          │
│        │                                     │          │
│        └─────────────────────────────────────┘          │
│                                                         │
│                    当前阅读至20%                          │
└─────────────────────────────────────────────────────────┘
```

---

## Phase 3: Bug Fixes & Enhancements

### Issue 1 — First Page Content Overflow (Bug Fix, Priority: P1)

**Problem**: On the first page of each chapter, left-side content overflows beyond the 80px margin boundary.

**Root Cause**: CSS columns start content at scroll position 0, but the first column doesn't respect the left padding properly.

**Acceptance Scenarios**:
1. **Given** a chapter loads, **When** viewing the first page, **Then** content MUST be fully within the 80px left margin (no overflow).
2. **Given** any page in a chapter, **When** content displays, **Then** left and right margins are consistent at 80px.

**Requirements**:
- **FR-P3-001**: First page content MUST NOT overflow beyond the left margin boundary.

---

### Issue 2 — AI Chat Panel Width & Resizable (Enhancement, Priority: P2)

**Problem**: The AI Chat panel is too narrow; user wants 30% wider default and manual resize capability.

**Acceptance Scenarios**:
1. **Given** the user opens the AI panel, **When** it appears, **Then** the default width is 546px (420px × 1.3).
2. **Given** the AI panel is open, **When** the user drags the left edge, **Then** the panel width adjusts smoothly (min: 320px, max: 800px).
3. **Given** the user has resized the panel, **When** they close and reopen it, **Then** the width persists within the session.

**Requirements**:
- **FR-P3-002**: AI panel default width MUST be 546px (30% wider than current 420px).
- **FR-P3-003**: AI panel MUST support drag-to-resize via a left edge resize handle.
- **FR-P3-004**: AI panel width MUST be constrained between 320px (min) and 800px (max).
- **FR-P3-005**: AI panel resized width SHOULD persist within the browser session (localStorage).

---

### Issue 3 — Annotation/Highlight/Notes Not Working (Bug Fix, Priority: P1)

**Problem**: Text selection popup for highlighting, copying, and adding notes does not appear after pagination changes.

**Root Cause**: The pagination container's CSS (overflow, z-index, or event handling) may be interfering with text selection events or toolbar positioning.

**Acceptance Scenarios**:
1. **Given** the user selects text in the book content, **When** selection completes, **Then** the annotation toolbar appears near the selection.
2. **Given** the annotation toolbar is visible, **When** the user clicks "Marker", **Then** the color picker appears.
3. **Given** the user selects a highlight color, **When** clicked, **Then** the text is highlighted and the toolbar closes.
4. **Given** the user clicks "Add Note", **When** clicked, **Then** the note editor appears.

**Requirements**:
- **FR-P3-006**: Text selection within paginated content MUST trigger the annotation toolbar.
- **FR-P3-007**: Annotation toolbar z-index MUST be higher than pagination container.
- **FR-P3-008**: All annotation actions (copy, highlight, note, ask AI) MUST function correctly.

---

### Issue 4 — Font Settings Panel (New Feature, Priority: P2)

**Problem**: User wants to adjust font size and paragraph spacing while reading, with a clean popup UI similar to Dedao app.

**UI Reference**: Similar to the provided screenshot showing:
- Theme selector (白色, 黄色, 护眼, 夜间) — UI only for v1
- Font size control (减小 / 当前字号 / 放大) — functional
- Paragraph spacing control — functional
- Font family selector (系统字体, 得到今楷, etc.) — UI only for v1

**Acceptance Scenarios**:
1. **Given** the reader page, **When** user clicks the font settings button in right toolbar, **Then** a popup appears with reading settings.
2. **Given** the popup is open, **When** user clicks + on font size, **Then** font size increases by 1px (range: 14px–24px).
3. **Given** the popup is open, **When** user clicks + on paragraph spacing, **Then** line-height increases by 0.1 (range: 1.5–2.5).
4. **Given** font/spacing is changed, **When** user closes popup, **Then** settings persist via localStorage.
5. **Given** the page reloads, **When** content renders, **Then** saved font size and line-height are applied.

**Requirements**:
- **FR-P3-009**: Right toolbar MUST include a "Font Settings" button (Aa icon).
- **FR-P3-010**: Font Settings popup MUST display: theme selector (UI only), font size control, paragraph spacing control, font family selector (UI only).
- **FR-P3-011**: Font size MUST be adjustable from 14px to 24px in 1px increments.
- **FR-P3-012**: Paragraph line-height MUST be adjustable from 1.5 to 2.5 in 0.1 increments.
- **FR-P3-013**: Font and spacing settings MUST persist to localStorage.
- **FR-P3-014**: Keyboard shortcuts SHOULD be supported: Cmd/Ctrl+Option++ (increase), Cmd/Ctrl+Option+- (decrease).

**UI Wireframe**:
```
┌─────────────────────────────────────┐
│  主题                                │
│  ○ 白色  ○ 黄色  ○ 护眼  ● 夜间      │
│                                     │
│  文字                                │
│  [ - ]     17     [ + ]             │
│           当前字号                   │
│                                     │
│  段落间距                            │
│  [ - ]    1.9     [ + ]             │
│          当前间距                    │
│                                     │
│  字体                                │
│  [系统字体] [得到今楷]                │
│  [汉仪旗黑] [思源宋体]                │
└─────────────────────────────────────┘
```

---

---

## Phase 4: Annotation System Enhancements

### Issue 5 — Annotation Toggle Behavior (Enhancement, Priority: P1)

**Problem**: Users expect clicking the same annotation type on already-annotated text to remove the annotation (toggle behavior).

**Acceptance Scenarios**:
1. **Given** text is already marked as wavy, **When** user selects that text and clicks Wavy, **Then** the wavy annotation is removed.
2. **Given** text has an underline annotation, **When** user selects that text and clicks Underline, **Then** the underline is removed.
3. **Given** text has a marker highlight, **When** user selects that text and clicks the same color, **Then** the highlight is removed.

**Requirements**:
- **FR-P4-001**: Clicking an annotation action on already-annotated text of the same type MUST remove the annotation.
- **FR-P4-002**: Delete button MUST be added to annotation toolbar to explicitly remove annotations.

---

### Issue 6 — Click-to-Select Annotated Text (Enhancement, Priority: P1)

**Problem**: Users want to click on annotated text to select it and show the toolbar, similar to WeChat Reading.

**Acceptance Scenarios**:
1. **Given** text is annotated with any style, **When** user clicks on the `<mark>` element, **Then** the text is selected and toolbar appears.
2. **Given** text has a note annotation, **When** user clicks on it, **Then** the note editor opens with the existing note content pre-filled.
3. **Given** the note editor is open with existing content, **When** user edits and saves, **Then** the note is updated (not created as new).

**Requirements**:
- **FR-P4-003**: Clicking on annotated `<mark>` element MUST select the text and show the toolbar.
- **FR-P4-004**: Clicking on a note annotation MUST open the note editor with existing content.
- **FR-P4-005**: Saving an edited note MUST update the existing annotation (PUT request).

---

### Issue 7 — Notes Panel UI Redesign (Enhancement, Priority: P2)

**Problem**: Notes panel UI needs to match the Dedao-style design with chapter grouping, icons, and copy functionality.

**UI Reference**: Dedao reading notes panel with:
- Chapter headers with orange background
- Note items with icons (A for highlights, speech bubble for notes)
- Footer buttons for "点评此书" and "复制全部笔记"

**Acceptance Scenarios**:
1. **Given** the Notes panel is open, **When** notes exist, **Then** they are grouped by chapter with orange header backgrounds.
2. **Given** a note item, **When** it is a highlight, **Then** it shows an "A" icon; **When** it has a note, **Then** it shows a speech bubble icon.
3. **Given** the user clicks "复制全部笔记", **When** clicked, **Then** all notes are copied to clipboard in Markdown format.

**Requirements**:
- **FR-P4-006**: Notes panel MUST display notes grouped by chapter with styled headers.
- **FR-P4-007**: Notes panel MUST show appropriate icons for highlight vs. note annotations.
- **FR-P4-008**: Notes panel MUST include "复制全部笔记" button that copies all notes in Markdown format.

---

### Issue 8 — Annotation Style Fixes (Bug Fix, Priority: P1)

**Problem**: Underline and wavy annotations incorrectly show yellow background fill; should only show line decoration.

**Acceptance Scenarios**:
1. **Given** text has underline annotation, **When** rendered, **Then** it shows only orange underline (no background color).
2. **Given** text has wavy annotation, **When** rendered, **Then** it shows only lime green wavy underline (no background color).

**Requirements**:
- **FR-P4-009**: Underline annotations MUST show only text decoration (orange underline), no background.
- **FR-P4-010**: Wavy annotations MUST show only text decoration (lime green wavy), no background.

---

## Out of Scope

- Multi-column magazine-style layouts
- Dark mode / theme switching (UI placeholder only in Phase 3)
- Bookmark functionality within pages
- Touch swipe gestures (keyboard/click is sufficient for v1)
- Offline reading support
- Custom font families (UI placeholder only in Phase 3)

---

## Phase 5: Renderer Refactor (epub.js)

### Problem Statement

The current reader injects raw EPUB HTML directly into the DOM and overlays annotations on top. This makes the UI sensitive to inline styles and absolute positioning in EPUB content, which can block clicks and selection on annotated text. We need a more reliable rendering mechanism that isolates EPUB styles and normalizes interaction behavior.

### Desired State

Render EPUB content using a dedicated renderer (epub.js) inside an isolated container (iframe) so that:
- EPUB styles are sandboxed and do not interfere with reader UI or annotation interactions.
- Clicking on annotated text reliably selects the annotation (WeChat Reading-style behavior).
- The annotation system continues to work with minimal user-visible changes.

### Acceptance Scenarios

1. **Given** the reader page is open, **When** a chapter renders, **Then** content is rendered via epub.js in an isolated frame (no direct HTML injection into `.book-content`).
2. **Given** text is annotated (marker/underline/wavy), **When** the user clicks the annotated text, **Then** the annotation is selected and the toolbar opens.
3. **Given** an existing note annotation, **When** the user clicks it, **Then** the note editor opens with existing content and updates via PUT.
4. **Given** EPUB content contains absolute-positioned elements or custom styles, **When** the user clicks text, **Then** clicks are still captured by the annotation layer (no blocked clicks).
5. **Given** the user navigates chapters, **When** they go next/previous, **Then** epub.js renders the correct spine item and annotations re-apply.

### Requirements

#### Renderer Integration
- **FR-RF-001**: The reader MUST render EPUB content via epub.js rather than direct HTML injection.
- **FR-RF-002**: The epub.js renderer MUST run inside an isolated container (iframe or equivalent).
- **FR-RF-003**: The renderer MUST expose DOM selection events to the annotation system.

#### Annotation Compatibility
- **FR-RF-004**: Annotation selection MUST work consistently (click-to-select).
- **FR-RF-005**: Annotation CRUD MUST continue to use the existing `/api/notes` endpoints.
- **FR-RF-006**: Notes editing MUST still use PUT updates with existing annotation IDs.

#### Reader UI Compatibility
- **FR-RF-007**: Existing reader UI (TOC, search, AI panel, notes panel, toolbar) MUST continue to work.
- **FR-RF-008**: Pagination logic MUST be re-evaluated; either replaced by epub.js pagination or integrated with it.

### Decision Summary (Confirmed)

- **Renderer source**: Render from the original `.epub` (stored alongside processed data).
- **Annotation anchors**: Add epub.js CFI anchors for new annotations and keep quote/prefix/suffix fallback for legacy notes.
- **Pagination**: Use epub.js pagination and update progress tracking accordingly.
- **Reading settings**: Keep existing font/spacing UI, inject via epub.js themes.
- **Search**: Keep DOM-based search, target the iframe document.

### Data Storage Impact

- A copy of the original `.epub` MUST be stored in `books/<book_id>_data/` for epub.js rendering.
- `notes.json` SHOULD support a new optional `cfi` field on annotations for precise anchors.

### Non-Functional Requirements

- **NFR-RF-001**: Rendering MUST complete within 200ms for typical chapters.
- **NFR-RF-002**: Annotation interaction MUST not regress compared to Phase 4.
- **NFR-RF-003**: No new security risks (sanitize input, avoid unsafe iframe messaging).

### Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| epub.js integration conflicts with existing pagination | Medium | High | Decide on epub.js pagination vs. custom pagination early; update spec accordingly |
| Annotation selection inside iframe is harder | Medium | Medium | Use epub.js hooks + postMessage to bridge selection/mark rendering |
| Search highlighting conflicts with annotations | Medium | Medium | Consolidate highlight logic inside iframe renderer |
| Performance regressions for large chapters | Low | Medium | Lazy-load spine items, defer annotation rendering |

### Out of Scope (Phase 5)

- Full offline caching of EPUB assets
- Cross-device sync for annotations
- Mobile gesture controls

## Success Metrics

1. **Screen utilization**: Content area width increases from ~768px to `100vw - 160px`
2. **User experience**: No vertical scrolling needed within a page
3. **Performance**: Page transitions complete in < 200ms
4. **Accessibility**: Keyboard navigation fully functional

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Complex EPUB content (tables, large images) may break pagination | Medium | Medium | Use `break-inside: avoid` and scale oversized images |
| Performance issues with very long chapters | Low | Medium | Consider lazy rendering or chunking for chapters > 100KB |
| Browser compatibility with CSS columns | Low | High | Test across target browsers; provide vertical scroll fallback |
| Existing annotation/highlight features may conflict with new layout | Medium | Medium | Test annotation toolbar positioning with new layout |

## Clarifications

### Session 2025-12-27 (Initial)

- Q: When a side panel (TOC, Search, AI, or Notes) is open, how should the paginated content area behave? → A: Overlay panel on top (content unchanged, partially hidden)
- Q: For viewports narrower than 600px (mobile), what should the pagination behavior be? → A: Fall back to vertical scroll (disable pagination)
- Q: When a section has very short content (fits in less than one page), should the progress indicator show "100%" immediately or be hidden? → A: Show "100%" or "1/1" immediately
- Q: When the user resizes the browser window mid-reading, should the reader preserve their reading position? → A: Yes, preserve approximate reading position after reflow
- Q: How wide should the clickable edge zones for page navigation be? → A: 120px (wider, easier to click)

### Session 2025-12-27 (Phase 4)

- Q: Should clicking the same annotation type on already-annotated text remove the annotation? → A: Yes, implement toggle behavior
- Q: Should click navigation zones be removed in favor of keyboard-only navigation? → A: Yes, remove click zones to avoid interfering with text selection
- Q: Should underline/wavy annotations have background color? → A: No, only show line decoration (no yellow fill)
- Q: How should clicking on annotated text behave? → A: Select the text, show toolbar; if note, open note editor with existing content
- Q: Should notes be editable after creation? → A: Yes, add PUT endpoint for updating note_text

## Dependencies

- None (pure frontend CSS/JS changes)
- Must maintain compatibility with existing annotation system (`annotations.js`)
- Must maintain compatibility with existing search/AI panels (side panel positioning)

---

_Created: 2025-12-27_
_Status: Implemented (Phase 1-4 Complete)_
_Last Updated: 2025-12-27_
