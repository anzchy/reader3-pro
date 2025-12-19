# Feature Specification: Book Notes & Annotations

**Feature Branch**: `003-add-book-notes`  
**Created**: 2025-12-18  
**Last Updated**: 2025-12-19  
**Status**: Draft  
**Input** (CN):  
- “阅读时用鼠标选择文本，弹出复制/马克笔/波浪线/直线/写想法（笔记）/AI 问书；标注会在网页端生效；写想法悬浮可见；AI 问书把选中文本发送到 002-ai-assistant 窗口。”  
- “Reader 页面需要完全复刻微信读书网页端的右侧工具栏与笔记/目录交互：全屏显示；所有按钮在右侧，从上到下分别是 `目录页`、`Search`、`AI`、`Notes`；Notes 打开后展示全书笔记，且刷新/下次打开仍可看到。”

## UI Reference (pixel-perfect target)

- WeRead-style Notes panel: `codex-clipboard-1TRmE3.png`
- WeRead-style TOC panel + right toolbar: `codex-clipboard-07jNlB.png`

## Terminology (to avoid ambiguity)

- `book_id`: The existing identifier used by routes/APIs: the processed book folder name ending with `_data` (e.g., `the-cold-start-problem_data`). This same value is used for persistence paths under `books/`.
- `chapter_index`: 0-based spine index used by `/read/{book_id}/{chapter_index}`.
- “Tool panels”: the UI surfaces opened by the right toolbar buttons: `目录页` (TOC), `Search`, `AI`, `Notes`.

## Clarifications

### Session 2025-12-18 (proposed defaults; update if you want different behavior)

- Q: 标注的持久化范围？→ A: **按书籍 + 章节持久化**（`book_id` + `chapter_index`），刷新/重启浏览器后仍可恢复。
- Q: 标注存储位置？→ A: **文件系统为真相来源**：`books/{book_id}/notes.json`（例如 `books/the-cold-start-problem_data/notes.json`）。
- Q: 选区跨多个段落/节点怎么办？→ A: 允许跨节点选区，但标注落地以"文本 quote + 上下文"方式重定位，避免依赖脆弱的 DOM path。
- Q: "AI 问书"交互？→ A: 触发事件把选中文本发送给 002 的 AI 侧边栏；若 AI 面板未实现/未加载，则提示"AI 面板未启用"。
- Q: Annotation Display Priority & Overlap → A: Layer all annotation styles (yellow background + wavy underline visible simultaneously), with Notes having highest visual priority.
- Q: Re-anchoring Failure Handling → A: Mark as `orphaned=true` in storage; hide from display but keep data (no debug/admin UI in v1).
- Q: Marker Color Palette → A: 3-5 preset colors (yellow, green, pink, blue) to match common highlighter sets.
- Q: Note 是否需要颜色？→ A: `type="note"` 允许携带 `color`（与 marker 同一色板）；v1 默认 `yellow`，可先不做“笔记颜色选择”UI。
- Q: Note Editor UI Pattern → A: Inline popover positioned near the selection (like Google Docs comments).
- Q: Re-anchoring Context Length → A: 50 characters before and after (100 total context).

### Session 2025-12-19 (WeRead-like reader layout)

- Q: `reader.html` 默认布局？→ A: **全屏阅读**，不再使用“左侧常开侧边栏”；阅读内容以居中“纸张”呈现，页面背景为浅灰。
- Q: 工具栏位置与按钮顺序？→ A: **右侧垂直悬浮工具栏**固定在视口右侧，按钮从上到下严格为：`目录页`、`Search`、`AI`、`Notes`。
- Q: Notes 展示形态？→ A: `Notes` 打开后显示**全书笔记面板**（覆盖/替代阅读内容区域，UI 按参考截图像素级复刻）；关闭后返回到原阅读位置（scroll + 当前章节不变）。
- Q: 面板互斥？→ A: 同一时刻最多打开一个面板（打开一个自动关闭其它）。
- Q: 已读百分比如何显示？→ A: v1 使用近似值：`chapter_index / (total_chapters - 1)`，四舍五入为整数百分比；用于 Notes 头部的“已读到 X%”展示。
- Q: `Esc` 行为优先级？→ A: `Esc` 优先关闭“写想法”编辑 popover；其次关闭选区浮动工具条；最后关闭当前打开的 tool panel（TOC/Search/AI/Notes）。
- Q: TOC panel 顶部搜索框是否需要功能？→ A: v1 **需要**：在 TOC 面板内按章节标题做实时过滤（不做全文搜索）。
- Q: Search/AI 的面板形态要不要也复刻微信读书？→ A: v1 **不要求**完全复刻；Search/AI 继续复用现有实现（Search 右侧抽屉；AI 右侧面板）。WeRead-style 的“像素级复刻”要求主要针对：右侧工具栏、TOC 模式、Notes 模式。

## User Scenarios & Testing *(mandatory)*

### User Story 0 — Fullscreen Reader + Right Toolbar (WeRead-style) (Priority: P0)

As a reader, the book reader is fullscreen and I can access all tools from a right-side vertical button stack, just like WeRead web.

**Acceptance Scenarios**
1. **Given** I open any `reader.html` page, **Then** the reader renders fullscreen with no left “always-on” sidebar; the reading content is centered; the page background is light gray.
2. **Then** a floating right toolbar is visible and fixed on the right side of the viewport.
3. **Then** the toolbar buttons are ordered from top to bottom: `目录页`, `Search`, `AI`, `Notes` (exact order).
4. **When** I click one button, **Then** its corresponding panel opens and the button has an active state; **And** any other open panel closes.
5. **When** I press `Esc`, **Then** the UI closes in this order: note editor popover → selection toolbar → open tool panel; **And** focus returns to the reader.

### User Story 1 — Inline Annotation Toolbar (Priority: P1)

As a reader, I select text in the reader content and immediately get a floating toolbar with actions (Copy / Marker / Wavy / Underline / Note / Ask AI).

**Acceptance Scenarios**
1. **Given** I select text inside `.book-content`, **When** I finish selection (mouse up), **Then** a floating toolbar appears near the selection.
2. **Given** I click outside the selection or press `Esc`, **Then** the toolbar closes.
3. **Given** I select text outside `.book-content` (sidebar/TOC), **Then** no annotation toolbar is shown.

### User Story 2 — Highlight/Underline Rendering (Priority: P1)

As a reader, when I choose Marker/Wavy/Underline, the selected text is visibly annotated in-place and persists when I revisit the chapter.

**Acceptance Scenarios**
1. **When** I choose **Marker**, **Then** the toolbar shows color options (yellow/green/pink/blue); **When** I select a color, **Then** the selected range is highlighted with that color background.
2. **When** I choose **Wavy**, **Then** the selected range shows a wavy underline.
3. **When** I choose **Underline**, **Then** the selected range shows a straight underline.
4. **When** I refresh the page, **Then** all previously created annotations for this chapter are re-applied with their original colors/styles.

### User Story 3 — Notes ("写想法") with Hover Tooltip (Priority: P1)

As a reader, I can attach a note to the selected text, and later hover that annotated text to see the note content (PDF-style).

**Acceptance Scenarios**
1. **When** I choose **写想法**, **Then** an inline popover appears near the selection with a text input field and Save/Cancel buttons.
2. **When** I save, **Then** the selected range is annotated and hovering shows the note content in a tooltip.
3. **When** I cancel or click outside the popover, **Then** the popover closes and no annotation is created.
4. **Given** the popover is open, **When** the selected text is still visible on screen, **Then** I can see both the selection and the note editor simultaneously.

### User Story 4 — Ask AI (“AI 问书”) Integration (Priority: P2)

As a reader, I can send the selected text to the AI sidebar (feature `002-ai-assistant`) to ask questions about it.

**Acceptance Scenarios**
1. **When** I choose **AI 问书**, **Then** the AI panel opens (if available) and receives the selected quote + book/chapter context.
2. **If** the AI panel is not available, **Then** the UI shows a clear message (“AI 面板未启用/未加载”).

### User Story 5 — Notes Panel (All Notes) (Priority: P1)

As a reader, I can click `Notes` to view all highlights and notes for the entire book, and I can jump back to the original location.

**Acceptance Scenarios**
1. **When** I click the `Notes` button on the right toolbar, **Then** a Notes panel opens with UI matching the reference screenshot (layout, spacing, colors, typography, rounded corners, shadows).
2. **Then** the Notes header shows: book title, cover, “已读到 X%”、and “共 N 条笔记” (N counts all non-orphaned annotations of types marker/wavy/underline/note).
3. **Given** the book has no notes, **Then** the Notes body shows the empty-state card copy exactly: “你可以在这里记录本书的想法、划线、书签”.
4. **Given** the book has notes, **Then** the Notes body lists notes grouped by chapter (spine order) and then by position within chapter (top-to-bottom).
5. **When** I click a note item, **Then** the reader navigates to the corresponding chapter and scrolls to the annotated quote, with the annotation visibly highlighted.
6. **When** I refresh or reopen the same book later, **Then** Notes still shows all previously created annotations and they still render in-place inside chapters.

### User Story 6 — TOC Panel (Directory Page) (Priority: P1)

As a reader, I can click `目录页` to open a WeRead-like table-of-contents view and navigate to a chapter.

**Acceptance Scenarios**
1. **When** I click the `目录页` button, **Then** a TOC panel opens with UI matching the reference screenshot (including search input styling + list styling).
2. **Then** the TOC list shows all TOC entries in a scrollable list (nested structure preserved).
3. **When** I click a TOC item, **Then** the reader navigates to that chapter and closes the TOC panel.
4. **When** I click `目录页` again (or press `Esc`), **Then** the TOC panel closes and returns to the prior reading view/scroll position.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The reader MUST show an annotation toolbar when a non-empty text selection is made within `.book-content`.
- **FR-002**: Toolbar actions MUST include: Copy, Marker, Wavy underline, Straight underline, Note, Ask AI.
- **FR-003**: Copy MUST copy the selected plain text to clipboard.
- **FR-004**: Marker/Wavy/Underline MUST apply an in-page visual style to the selected text range.
- **FR-004a**: Marker MUST support 3-5 preset colors (yellow, green, pink, blue) with yellow as default; the toolbar MUST allow color selection when creating a marker annotation.
- **FR-005**: Notes MUST be stored and rendered with a hoverable tooltip showing the note text.
- **FR-005a**: The note creation UI MUST use an inline popover positioned near the selection (not a modal or sidebar) with text input and Save/Cancel actions.
- **FR-006**: Annotations MUST persist across page refresh and restore on chapter load.
- **FR-007**: Annotation scope MUST be at least: `{book_id, chapter_index}`.
- **FR-008**: The system MUST support multiple annotations per chapter and display them all.
- **FR-008a**: When annotations overlap on the same text, the system MUST layer all styles visually (e.g., background color + underline simultaneously); Notes MUST have highest visual priority.
- **FR-009**: The UI MUST avoid corrupting the book HTML structure (no breaking tags; handle nested text nodes safely).
- **FR-009a**: If an annotation cannot be re-anchored (quote not found in chapter text), the system MUST mark it as `orphaned=true`, exclude it from display, and preserve the data in storage.
- **FR-010**: `Esc` MUST dismiss UI in this order: note editor popover → selection toolbar → open tool panel.

### Reader Layout & Right Toolbar (WeRead-style)

- **FR-020**: `reader.html` MUST render fullscreen (100vh) with no persistent left sidebar; reading content MUST be centered in a “paper” container on a light-gray page background.
- **FR-021**: The reader MUST provide a right-side floating toolbar with exactly 4 buttons, ordered top-to-bottom: `目录页`, `Search`, `AI`, `Notes`.
- **FR-022**: The toolbar button style MUST match the reference screenshots: circular buttons, light neutral background, subtle shadow, and icon-only appearance (no text labels in the button body; tooltips allowed).
- **FR-023**: Only one tool panel MAY be open at a time; opening one tool panel MUST close any other open tool panel(s).
- **FR-024**: When a tool panel is open and there is no higher-priority UI open (note editor popover or selection toolbar), `Esc` MUST close the open tool panel.
- **FR-025**: Opening `目录页` or `Notes` MUST preserve the current reading location (current `chapter_index` + scroll offset); closing them MUST restore to that preserved location.

### Notes Panel (WeRead-style)

- **FR-030**: Clicking `Notes` MUST open a Notes panel that lists all annotations for the current book.
- **FR-031**: Notes panel header MUST display: book title, cover image, “已读到 X%” (approximate), and “共 N 条笔记”.
- **FR-032**: Empty state MUST match the reference copy exactly: “你可以在这里记录本书的想法、划线、书签”.
- **FR-033**: Notes panel MUST allow jumping: clicking an item navigates to the corresponding chapter + scroll position and closes the panel.
- **FR-034**: Notes panel MUST render as a “mode” in the main reading area (reading content hidden but preserved); it is NOT a right-side drawer.
- **FR-035**: Notes panel UI MUST be pixel-accurate to the screenshot (spacing/typography/colors/shadows/rounded corners), within the tolerances defined in **Visual Fidelity**.

### TOC Panel (Directory Page)

- **FR-040**: Clicking `目录页` MUST open a TOC panel with WeRead-like styling (reference screenshot).
- **FR-041**: TOC panel MUST render the nested TOC structure and allow chapter navigation.
- **FR-042**: TOC panel MUST be closable via clicking the `目录页` button again or pressing `Esc`.
- **FR-043**: TOC panel search input MUST filter TOC entries by title substring in real time (case-insensitive), without performing full-text search.
- **FR-044**: TOC panel MUST render as a “mode” in the main reading area (reading content hidden but preserved); it is NOT a right-side drawer.

### Integration Requirements (002-ai-assistant)

- **FR-011**: “AI 问书” MUST send payload `{book_id, chapter_index, quote, context}` to the AI panel.
- **FR-012**: The integration MUST be decoupled (e.g., `CustomEvent` or a shared `window.Reader3AI` bridge) so 003 can work even if 002 is not present.

### Data & Storage Requirements

- **FR-013**: Notes/annotations MUST be stored in `books/{book_id}/notes.json` (single file per book).
- **FR-013a**: `notes.json` MUST include `schema_version: 1` at the top-level for future migrations.
- **FR-014**: The server MUST expose an API to load/save annotations (see API section).
- **FR-015**: `note_text` MUST be HTML-escaped before persisting to disk, and MUST be treated as untrusted at render time (no `innerHTML`).

### Performance & UX

- **FR-016**: Applying annotations on chapter load SHOULD complete in under 200ms for a typical chapter.
- **FR-017**: The toolbar positioning SHOULD follow the selection and avoid going off-screen.

### Security

- **FR-018**: `book_id` MUST be validated against enumerated `books/*_data/` directories (same rule as search).
- **FR-019**: Saved note content MUST be treated as untrusted and sanitized/escaped before inserting into DOM.

## Visual Fidelity (how “pixel-perfect” is evaluated)

Primary verification environment: Chromium-based browser at 100% zoom (default font settings). Minor variations due to font rendering are acceptable.

- Scope: visual fidelity requirements apply to the right toolbar, TOC mode, and Notes mode only (not Search/AI panels).
- Layout structure MUST match the reference screenshots (same major regions/containers and hierarchy).
- Spacing (padding/margins/gaps) SHOULD match within ±2px.
- Font sizes SHOULD match within ±1px; font family differences are acceptable if the overall hierarchy/weight/contrast is preserved.
- Colors SHOULD be visually indistinguishable in normal viewing; exact hex equality is NOT required.
- Rounded corners/shadows SHOULD match within reasonable CSS differences across browsers.

## API (proposed)

All responses are JSON.

- `GET /api/notes/{book_id}` → returns all notes for a book (grouped by chapter).
- `GET /api/notes/{book_id}/{chapter_index}` → returns notes for the chapter only (faster for page load).
- `POST /api/notes/{book_id}/{chapter_index}` → create an annotation (server generates `id` + `created_at`).
- `DELETE /api/notes/{book_id}/{chapter_index}/{note_id}` → delete an annotation (optional for v1; can be deferred).

## Data Model (proposed)

### Annotation

- `id`: string (uuid)
- `book_id`: string (`*_data` folder name)
- `chapter_index`: int (spine index used by `/read/{book_id}/{chapter_index}`)
- `type`: `"marker" | "wavy" | "underline" | "note"`
- `color`: string | null (for `type in {"marker","note"}` only; values: `"yellow" | "green" | "pink" | "blue"`; default: `"yellow"`)
- `position`: int | null (optional hint; start char offset of the match within chapter plain text at creation time; used for stable ordering and jump targeting; may be recomputed on load)
- `quote`: string (selected text)
- `prefix`: string (up to 50 chars before selection in chapter plain text; for re-anchoring)
- `suffix`: string (up to 50 chars after selection; for re-anchoring)
- `created_at`: ISO datetime
- `note_text`: string | null (only for `type="note"`)
- `orphaned`: boolean (default: false; set to true if re-anchoring fails)

**Re-anchoring strategy**: On chapter load, rebuild `chapterPlainText` (DOM textContent), find the best match for `prefix + quote + suffix` (fallback: first occurrence of `quote`), then apply marks to DOM via a safe text-node walker (similar to search highlighting). If re-anchoring fails (quote not found), mark the annotation as `orphaned=true` in storage, hide from display, and preserve data for potential recovery.

## Success Criteria *(mandatory)*

- **SC-001**: Users can create a marker/wavy/underline annotation on selected text in under 2 seconds.
- **SC-002**: Notes show correct tooltip content on hover and persist after refresh.
- **SC-003**: Annotations do not break chapter rendering (no malformed HTML after applying marks).
- **SC-004**: “AI 问书” reliably delivers the selected quote to the AI panel when enabled.
- **SC-005**: The right toolbar + Notes/TOC modes meet the **Visual Fidelity** criteria against the reference screenshots.

## Assumptions

- **Assumption 1**: Reader content is static per chapter (EPUB content doesn’t change after processing).
- **Assumption 2**: The app is single-user and runs locally; file-based persistence is acceptable.
- **Assumption 3**: Exact text re-anchoring is sufficient for v1 (no need for robust W3C Web Annotation selectors yet).

## Non-Goals (v1)

- Editing/deleting annotations UI (can be added later; API may exist without UI).
- Admin/debug UI to review or recover orphaned annotations (data is preserved but UI deferred to v2).
- Cross-device sync.
- PDF-level precision in re-anchoring for heavily duplicated quotes across chapter.
- Exact reading progress tracking across sessions (v1 uses approximate percentage for display only).
