# Reader Pro Next — design notes

## Context

- Product source: designs/reader-pro-next/spec/reader-pro-spec.md
- Visual evidence: designs/reader-pro-next/spec/screenshots/*.png
- HTML/CSS source: src/reader3_app/web/templates/ and src/reader3_app/web/static/
- Real content asset: books/the-art-of-spending-money_data/images/9780593716632_title_page.jpg

## Assumptions

- This is a standalone high-fidelity prototype, not a production implementation.
- It covers the core Library, Reader, Settings, Search, Notes, TOC, AI and selection flows.
- Existing information architecture and product copy remain recognizable.
- The current info blue from the specification, #3b82f6, becomes the primary brand color.
- The prototype fixes the documented mobile reachability gaps by providing explicit menu and panel controls.

## Design system

- Primary: #3b82f6; hover: #2563eb; soft state: #eff6ff.
- Ink: #0f172a; secondary: #475569; muted: #94a3b8.
- Canvas: #f6f8fb; surfaces: #ffffff; border: #e2e8f0.
- UI type: system sans with CJK fallbacks.
- Reading type: Georgia with Songti SC and Noto Serif SC fallbacks.
- Spacing follows 4/8/12/16/24/32/48px.
- Corners are 8/12/16px; shadows are quiet and reserved for floating layers.
- Motion is 160–240ms and disabled under prefers-reduced-motion.

## Interaction model

- A single prototype switches between Library, Reader and Settings without a reload.
- Desktop Library keeps three panes; mobile uses explicit left and right drawers.
- Reader tools open one mutually exclusive side sheet.
- Selection mode, collection dialog, Library search, Reader TOC/Search/Notes/AI and type controls are interactive.
- No prototype action writes to the real Reader3 API or user data.

