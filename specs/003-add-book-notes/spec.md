# Feature Specification: Book Notes & Annotations

**Feature Branch**: `003-add-book-notes`  
**Created**: 2025-12-18  
**Status**: Draft  
**Input**: User description (CN): “阅读时用鼠标选择文本，弹出复制/马克笔/波浪线/直线/写想法（笔记）/AI 问书；标注会在网页端生效；写想法悬浮可见；AI 问书把选中文本发送到 002-ai-assistant 窗口。”

## Clarifications

### Session 2025-12-18 (proposed defaults; update if you want different behavior)

- Q: 标注的持久化范围？→ A: **按书籍 + 章节持久化**（`book_id` + `chapter_index`），刷新/重启浏览器后仍可恢复。
- Q: 标注存储位置？→ A: **文件系统为真相来源**：`books/{book_id}/notes.json`（符合项目“filesystem IS database”的风格）。
- Q: 选区跨多个段落/节点怎么办？→ A: 允许跨节点选区，但标注落地以“文本 quote + 上下文”方式重定位，避免依赖脆弱的 DOM path。
- Q: “AI 问书”交互？→ A: 触发事件把选中文本发送给 002 的 AI 侧边栏；若 AI 面板未实现/未加载，则提示“AI 面板未启用”。

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Inline Annotation Toolbar (Priority: P1)

As a reader, I select text in the reader content and immediately get a floating toolbar with actions (Copy / Marker / Wavy / Underline / Note / Ask AI).

**Acceptance Scenarios**
1. **Given** I select text inside `.book-content`, **When** I finish selection (mouse up), **Then** a floating toolbar appears near the selection.
2. **Given** I click outside the selection or press `Esc`, **Then** the toolbar closes.
3. **Given** I select text outside `.book-content` (sidebar/TOC), **Then** no annotation toolbar is shown.

### User Story 2 — Highlight/Underline Rendering (Priority: P1)

As a reader, when I choose Marker/Wavy/Underline, the selected text is visibly annotated in-place and persists when I revisit the chapter.

**Acceptance Scenarios**
1. **When** I choose **Marker**, **Then** the selected range is highlighted with a marker-style background.
2. **When** I choose **Wavy**, **Then** the selected range shows a wavy underline.
3. **When** I choose **Underline**, **Then** the selected range shows a straight underline.
4. **When** I refresh the page, **Then** all previously created annotations for this chapter are re-applied.

### User Story 3 — Notes (“写想法”) with Hover Tooltip (Priority: P1)

As a reader, I can attach a note to the selected text, and later hover that annotated text to see the note content (PDF-style).

**Acceptance Scenarios**
1. **When** I choose **写想法**, **Then** a small editor (popover/modal) prompts me to enter note text and Save/Cancel.
2. **When** I save, **Then** the selected range is annotated and hovering shows the note content.
3. **When** I cancel, **Then** no annotation is created.

### User Story 4 — Ask AI (“AI 问书”) Integration (Priority: P2)

As a reader, I can send the selected text to the AI sidebar (feature `002-ai-assistant`) to ask questions about it.

**Acceptance Scenarios**
1. **When** I choose **AI 问书**, **Then** the AI panel opens (if available) and receives the selected quote + book/chapter context.
2. **If** the AI panel is not available, **Then** the UI shows a clear message (“AI 面板未启用/未加载”).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The reader MUST show an annotation toolbar when a non-empty text selection is made within `.book-content`.
- **FR-002**: Toolbar actions MUST include: Copy, Marker, Wavy underline, Straight underline, Note, Ask AI.
- **FR-003**: Copy MUST copy the selected plain text to clipboard.
- **FR-004**: Marker/Wavy/Underline MUST apply an in-page visual style to the selected text range.
- **FR-005**: Notes MUST be stored and rendered with a hoverable tooltip showing the note text.
- **FR-006**: Annotations MUST persist across page refresh and restore on chapter load.
- **FR-007**: Annotation scope MUST be at least: `{book_id, chapter_index}`.
- **FR-008**: The system MUST support multiple annotations per chapter and display them all.
- **FR-009**: The UI MUST avoid corrupting the book HTML structure (no breaking tags; handle nested text nodes safely).
- **FR-010**: The toolbar MUST be keyboard-dismissable via `Esc`.

### Integration Requirements (002-ai-assistant)

- **FR-011**: “AI 问书” MUST send payload `{book_id, chapter_index, quote, context}` to the AI panel.
- **FR-012**: The integration MUST be decoupled (e.g., `CustomEvent` or a shared `window.Reader3AI` bridge) so 003 can work even if 002 is not present.

### Data & Storage Requirements

- **FR-013**: Notes/annotations MUST be stored in `books/{book_id}/notes.json` (single file per book).
- **FR-014**: The server MUST expose an API to load/save annotations (see API section).
- **FR-015**: Stored note text MUST be HTML-escaped on render to prevent XSS.

### Performance & UX

- **FR-016**: Applying annotations on chapter load SHOULD complete in under 200ms for a typical chapter.
- **FR-017**: The toolbar positioning SHOULD follow the selection and avoid going off-screen.

### Security

- **FR-018**: `book_id` MUST be validated against enumerated `books/*_data/` directories (same rule as search).
- **FR-019**: Saved note content MUST be treated as untrusted and sanitized/escaped before inserting into DOM.

## API (proposed)

All responses are JSON.

- `GET /api/notes/{book_id}` → returns all notes for a book (grouped by chapter).
- `GET /api/notes/{book_id}/{chapter_index}` → returns notes for the chapter only (faster for page load).
- `POST /api/notes/{book_id}/{chapter_index}` → upsert an annotation (creates or updates).
- `DELETE /api/notes/{book_id}/{chapter_index}/{note_id}` → delete an annotation (optional for v1; can be deferred).

## Data Model (proposed)

### Annotation

- `id`: string (uuid)
- `book_id`: string (`*_data` folder name)
- `chapter_index`: int (spine index used by `/read/{book_id}/{chapter_index}`)
- `type`: `"marker" | "wavy" | "underline" | "note"`
- `quote`: string (selected text)
- `prefix`: string (up to N chars before selection in chapter plain text; for re-anchoring)
- `suffix`: string (up to N chars after selection; for re-anchoring)
- `created_at`: ISO datetime
- `note_text`: string | null (only for `type="note"`)

**Re-anchoring strategy**: On chapter load, rebuild `chapterPlainText` (DOM textContent), find the best match for `prefix + quote + suffix` (fallback: first occurrence of `quote`), then apply marks to DOM via a safe text-node walker (similar to search highlighting).

## Success Criteria *(mandatory)*

- **SC-001**: Users can create a marker/wavy/underline annotation on selected text in under 2 seconds.
- **SC-002**: Notes show correct tooltip content on hover and persist after refresh.
- **SC-003**: Annotations do not break chapter rendering (no malformed HTML after applying marks).
- **SC-004**: “AI 问书” reliably delivers the selected quote to the AI panel when enabled.

## Assumptions

- **Assumption 1**: Reader content is static per chapter (EPUB content doesn’t change after processing).
- **Assumption 2**: The app is single-user and runs locally; file-based persistence is acceptable.
- **Assumption 3**: Exact text re-anchoring is sufficient for v1 (no need for robust W3C Web Annotation selectors yet).

## Non-Goals (v1)

- Editing/deleting annotations UI (can be added later; API may exist without UI).
- Cross-device sync.
- PDF-level precision in re-anchoring for heavily duplicated quotes across chapter.

