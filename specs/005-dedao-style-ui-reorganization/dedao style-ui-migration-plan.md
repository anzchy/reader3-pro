 UI Migration Plan: Dedao Style for Reader3 Pro

 Executive Summary

 Migrate Reader3 Pro's library and reader pages to Dedao-style design while preserving all existing
 functionality. The generated mockups (library-dedao.html, reader-dedao.html) provide visual direction but are
 missing critical features that must be added.

---
 Part 1: Feature Mapping

 Library Page: Existing → Dedao

| Existing Feature   | Current Location   | Dedao Mockup Status | Migration Action               |
| ------------------ | ------------------ | ------------------- | ------------------------------ |
| Left Sidebar       |                    |                     |                                |
| Collections list   | Left pane (240px)  | ❌ Missing           | Add left pane with collections |
| Book type filters  | Left sidebar       | ❌ Missing           | Add filter section             |
| Create collection  | Left sidebar       | ❌ Missing           | Add + button                   |
| Center Content     |                    |                     |                                |
| Book grid (3-col)  | Center pane        | ✅ Present           | Adapt card design              |
| Book list view     | Center pane        | ❌ Missing           | Add toggle option              |
| Title filter input | Toolbar            | ❌ Missing           | Add to toolbar                 |
| Sort button        | Toolbar            | ❌ Missing           | Add to toolbar                 |
| Selection mode     | Toolbar            | ❌ Missing           | Add checkbox overlay           |
| Bulk indexing      | Selection toolbar  | ❌ Missing           | Add selection actions          |
| Status badges      | Book cards         | ❌ Missing           | Add indexed/unindexed badges   |
| Progress bar       | Book cards         | ✅ Present           | Keep                           |
| Right Panel        |                    |                     |                                |
| Dashboard tab      | Right pane (320px) | ❌ Missing           | Add tabbed right panel         |
| Chat tab           | Right pane         | ❌ Missing           | Add AI chat interface          |
| Search tab         | Right pane         | ❌ Missing           | Add cross-book search          |
| Panel collapse     | Toggle button      | ❌ Missing           | Add collapse toggle            |
| Header             |                    |                     |                                |
| Search bar         | Header             | ✅ Present           | Wire to title filter           |
| Add Book button    | Header             | ✅ Present           | Wire to dialog                 |

 Reader Page: Existing → Dedao

| Existing Feature  | Current Location | Dedao Mockup Status  | Migration Action               |
| ----------------- | ---------------- | -------------------- | ------------------------------ |
| TOC Sidebar       |                  |                      |                                |
| Collapsible TOC   | Left sidebar     | ✅ Present            | Wire to JS                     |
| Search/filter     | TOC header       | ❌ Missing            | Add filter input               |
| Active chapter    | TOC list         | ✅ Present            | Wire to spine index            |
| Content Area      |                  |                      |                                |
| Chapter content   | Center           | ✅ Present            | Keep Jinja rendering           |
| Chapter title     | Content header   | ✅ Present            | Keep                           |
| Previous/Next     | Footer           | ✅ Present            | Wire to navigation             |
| Right Toolbar     |                  |                      |                                |
| TOC toggle        | Toolbar          | ❌ Missing            | Add vertical toolbar           |
| Search toggle     | Toolbar          | ❌ Missing            | Add search button              |
| AI toggle         | Toolbar          | ✅ Partial (floating) | Move to toolbar                |
| Notes toggle      | Toolbar          | ❌ Missing            | Add notes button               |
| Search Drawer     |                  |                      |                                |
| Search panel      | Right drawer     | ❌ Missing            | Add sliding drawer             |
| Mode selector     | Search panel     | ❌ Missing            | Add keyword/semantic/hybrid    |
| Results list      | Search panel     | ❌ Missing            | Add results rendering          |
| AI Panel          |                  |                      |                                |
| Chat interface    | Right drawer     | ❌ Missing            | Add AI chat panel              |
| Quick actions     | AI panel         | ❌ Missing            | Add Summary/Highlights buttons |
| Thread history    | AI panel         | ❌ Missing            | Add conversation list          |
| Streaming         | AI panel         | ❌ Missing            | Wire SSE handling              |
| Annotations       |                  |                      |                                |
| Selection toolbar | Floating         | ❌ Missing            | Add annotation system          |
| Color markers     | Selection popup  | ❌ Missing            | Add marker tools               |
| Notes editor      | Popup            | ❌ Missing            | Add note creation              |
| Bottom Bar        |                  |                      |                                |
| Page indicator    | Footer           | ✅ Present            | Wire to spine                  |
| Progress bar      | Footer           | ✅ Present            | Wire to chapter index          |

---
 Part 2: Mockup Improvement Suggestions

 library-dedao.html Enhancements

 1. Add 3-Pane Layout (Critical)
 ┌──────────┬────────────────────┬──────────┐
  │ Left     │ Center             │ Right    │
  │ 240px    │ flex               │ 320px    │
  │          │                    │          │
  │ Types    │ Toolbar            │ [Tabs]   │
  │ ─────    │ ─────────────────  │ Dashboard│
  │ All      │ Filter | Sort | +  │ Chat     │
  │ EPUB     │                    │ Search   │
  │          │ Book Grid/List     │          │
  │ Collect  │                    │ [Content]│
  │ ─────    │                    │          │
  │ + Create │                    │          │
  │ My Books │                    │          │
  └──────────┴────────────────────┴──────────┘
 2. Enhance Book Cards
   - Add checkbox for selection mode
   - Add status badge (Indexed/Not indexed)
   - Add chunk count pill
   - Keep progress bar (already present)
 3. Add Toolbar Actions
   - Title filter input (left side)
   - Sort dropdown (A→Z / Z→A)
   - View toggle (grid/list icons)
   - Selection mode toggle
   - Add Book button (move from header)
 4. Add Right Panel Tabs
   - Dashboard: Stats grid + index progress
   - Chat: Book selector + conversation history + chat UI
   - Search: Mode selector + results grouped by book

 reader-dedao.html Enhancements

 1. Add Right Toolbar (Critical)
 <!-- Vertical toolbar, fixed right -->
 <div class="fixed right-4 top-1/2 -translate-y-1/2 flex flex-col gap-2">
   <button>目录</button>  <!-- TOC toggle -->
   <button>搜索</button>  <!-- Search toggle -->
   <button>AI</button>    <!-- AI panel toggle -->
   <button>笔记</button>  <!-- Notes toggle -->
 </div>
 2. Add Search Drawer
   - Slide-in from right (dark theme)
   - Mode selector: keyword/semantic/hybrid
   - Case sensitive checkbox
   - Index status + button
   - Results list with context
 3. Add AI Panel
   - Replace floating button with full panel
   - Thread list (left sidebar)
   - Quick actions: Summary/Highlights/Background
   - Chat messages with streaming
   - Citations linking to chapters
 4. Add Annotation System
   - Floating toolbar on text selection
   - Copy, Marker colors, Underline, Wavy, Note, Ask AI
   - Note editor popup
   - Tooltip on hover
 5. Enhance TOC Sidebar
   - Add search/filter input
   - Improve nested hierarchy styling
   - Better active state visibility

---
 Part 3: Migration Steps

 Phase 1: Foundation (Template Structure)

 Step 1.1: Create Dedao Design System CSS
 - File: static/dedao-theme.css
 - Define CSS variables matching Dedao style guide:
 :root {
   --dedao-orange: #ff6b00;
   --dedao-text: #333333;
   --dedao-muted: #666666;
   --dedao-light: #999999;
   --dedao-bg: #f5f5f5;
   --dedao-card: #ffffff;
   --dedao-border: #f0f0f0;
   --dedao-dark: #17222e;
  }

 Step 1.2: Update library.html Template
 - Keep existing Jinja2 logic
 - Replace HTML structure with Dedao layout
 - Preserve all id attributes for JS compatibility
 - Keep data attributes for JS initialization

 Step 1.3: Update reader.html Template
 - Keep Jinja2 chapter rendering
 - Replace layout with Dedao structure
 - Preserve all panel IDs
 - Keep window.Reader3Ctx initialization

 Phase 2: Library Page Migration

 Step 2.1: Left Sidebar
 - Implement collections with Dedao styling
 - Keep existing JS selectors
 - Update CSS classes

 Step 2.2: Center Content
 - Update book card HTML structure
 - Keep data-book-id, data-indexed attributes
 - Preserve selection checkboxes
 - Add Dedao-style progress bars

 Step 2.3: Right Panel
 - Recreate 3-tab interface with Dedao styling
 - Keep existing panel IDs:
   - #dashboard-tab, #chat-tab, #search-tab
 - Preserve all form inputs and their IDs

 Step 2.4: Wire JavaScript
 - Update CSS selectors in library.js if changed
 - Keep API calls unchanged
 - Test: filtering, selection, indexing, stats

 Phase 3: Reader Page Migration

 Step 3.1: Layout Structure
 - Main content with Dedao typography
 - TOC sidebar with toggle
 - Bottom navigation bar

 Step 3.2: Right Toolbar
 - Create vertical toolbar component
 - Wire toggle functions
 - Preserve RightToolbar class compatibility

 Step 3.3: Search Drawer
 - Rebuild with Dedao dark theme
 - Keep #reader-search-drawer ID
 - Preserve ReaderSearchUI selectors

 Step 3.4: AI Panel
 - Rebuild with Dedao styling
 - Keep #reader-ai-panel ID
 - Preserve ReaderAIUI selectors
 - Wire SSE streaming

 Step 3.5: Annotations
 - Keep annotation toolbar structure
 - Update styling to match Dedao
 - Preserve all annotation JS

 Phase 4: Testing & Polish

 Step 4.1: Functional Testing
 - Library: Filter, sort, select, bulk index
 - Library: Collections CRUD
 - Library: Dashboard stats refresh
 - Library: Chat with streaming
 - Library: Search across books
 - Reader: TOC navigation
 - Reader: Chapter Previous/Next
 - Reader: Search with highlighting
 - Reader: AI chat with citations
 - Reader: Annotations create/edit/delete

 Step 4.2: Responsive Testing
 - Mobile breakpoints
 - Tablet layout
 - Panel collapse behavior

 Step 4.3: Polish
 - Transitions and animations
 - Loading states
 - Error states
 - Empty states

---
 Part 4: Critical Files to Modify

 Templates (HTML)

 - src/reader3_app/web/templates/library.html - Full rewrite
 - src/reader3_app/web/templates/reader.html - Full rewrite

 Styles (CSS)

 - src/reader3_app/web/static/library.css - Full rewrite
 - src/reader3_app/web/static/reader.css - Full rewrite
 - src/reader3_app/web/static/toolbar.css - Update
 - src/reader3_app/web/static/search.css - Update styling
 - src/reader3_app/web/static/ai.css - Update styling
 - src/reader3_app/web/static/toc-panel.css - Update styling
 - src/reader3_app/web/static/notes-panel.css - Update styling
 - src/reader3_app/web/static/annotations.css - Update styling
 - NEW: src/reader3_app/web/static/dedao-theme.css - Design system

 JavaScript (Minimal Changes)

 - library.js - Update selectors if IDs change
 - library-chat.js - No changes expected
 - library-search.js - No changes expected
 - search.js - No changes expected
 - ai.js - No changes expected
 - annotations.js - No changes expected
 - toolbar.js - Update selectors if IDs change
 - toc-panel.js - Update selectors if IDs change
 - notes-panel.js - Update selectors if IDs change

---
 Part 5: User Decisions

 Confirmed Design Choices

 1. Right Panel Theme: ✅ All Light Dedao
   - Apply consistent light Dedao theme across Dashboard, Chat, and Search tabs
   - Warm, professional aesthetic throughout
   - Use orange (#ff6b00) for active states and CTAs
 2. Reader Panels: ✅ Slide-in Drawers (Right)
   - Keep current slide-in behavior from right side
   - Apply Dedao light styling to search and AI drawers
   - Same interaction pattern, new visual design
 3. Workflow: ✅ Update Mockups First
   - Revise library-dedao.html and reader-dedao.html with all missing features
   - Then implement in Jinja2 templates

---
 Part 6: Implementation Workflow

 Step 0: Update Mockups (NEXT ACTION)

 Task 0.1: Update library-dedao.html
 - Add left sidebar (collections, book type filters)
 - Add right panel with 3 tabs (Dashboard/Chat/Search)
 - Add toolbar (filter input, sort, view toggle, selection mode)
 - Update book cards (status badges, checkboxes)
 - Apply light Dedao theme throughout

 Task 0.2: Update reader-dedao.html
 - Add vertical right toolbar (TOC/Search/AI/Notes buttons)
 - Add search drawer (light Dedao theme, slide from right)
 - Add AI panel (light Dedao theme, slide from right)
 - Add annotation toolbar (floating on text selection)
 - Enhance TOC sidebar (add filter input)

 Step 1: Foundation

 Task 1.1: Create dedao-theme.css
 :root {
   --dedao-orange: #ff6b00;
   --dedao-text: #333333;
   --dedao-muted: #666666;
   --dedao-light: #999999;
   --dedao-bg: #f5f5f5;
   --dedao-card: #ffffff;
   --dedao-border: #f0f0f0;
   --dedao-dark: #17222e;
   --dedao-radius: 6px;
   --dedao-radius-lg: 12px;
   --dedao-radius-pill: 38px;
 }

 Step 2: Library Page Migration

 Task 2.1: Convert library.html structure from mockup
 Task 2.2: Wire existing JavaScript (preserve IDs)
 Task 2.3: Test all features

 Step 3: Reader Page Migration

 Task 3.1: Convert reader.html structure from mockup
 Task 3.2: Wire existing JavaScript (preserve IDs)
 Task 3.3: Test all features

 Step 4: Polish

 Task 4.1: Responsive breakpoints
 Task 4.2: Transitions and animations
 Task 4.3: Loading/error/empty states

---
 Part 7: Design Recommendations

 Typography

 - Use Noto Serif SC for book content (better Chinese reading)
 - Use system fonts for UI elements
 - Keep generous line-height (1.8-2.0) for readability

 Color Usage

 - Orange (#ff6b00) for CTAs and active states only
 - Avoid overusing orange (Dedao is restrained)
 - Use gray scale for hierarchy (#333, #666, #999)
 - Light backgrounds for all panels

 Component Patterns

 - Pill buttons for filters (rounded-full)
 - Card elevation: subtle shadow (0 2px 10px rgba(0,0,0,0.05))
 - Glassmorphism header (rgba(255,255,255,0.92) + backdrop-blur)
 - Progress bars: orange fill on gray track

 Responsive Considerations

 - Collapsible sidebars on smaller screens
 - Stack panels on mobile
 - Touch-friendly targets (min 44px)

---
 Summary

 What We're Doing

 1. Update mockups (library-dedao.html, reader-dedao.html) to include all missing features
 2. Migrate templates with Dedao styling while preserving JavaScript compatibility
 3. Apply light Dedao theme consistently across all panels (no dark theme)
 4. Keep slide-in drawer pattern for Reader search/AI panels

 Key Gaps to Fill in Mockups

 Library Page:
 - ❌ → ✅ Left sidebar (collections, type filters)
 - ❌ → ✅ Right panel with 3 tabs (Dashboard/Chat/Search)
 - ❌ → ✅ Toolbar (filter, sort, view toggle, selection)
 - ❌ → ✅ Book card enhancements (badges, checkboxes)

 Reader Page:
 - ❌ → ✅ Vertical right toolbar (TOC/Search/AI/Notes)
 - ❌ → ✅ Search drawer (light theme)
 - ❌ → ✅ AI panel (light theme)
 - ❌ → ✅ Annotation toolbar (floating)
 - ❌ → ✅ TOC filter input

 Critical Principle

 Preserve all JavaScript functionality by keeping element IDs consistent. Focus CSS changes on styling, not
 structure changes that would break JS bindings.

 Next Action

 Update library-dedao.html to include 3-pane layout with all missing features.