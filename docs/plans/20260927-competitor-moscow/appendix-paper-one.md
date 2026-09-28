> 附录来源：xiaolai/paper-one 深挖 scratchpad `paper-one.md`（gh api、`d39f2df` 浅克隆、Paper 课程版 feature ledger、commit 记录），整理日期 2026-09-27；以下正文逐字复制，未改动。

# xiaolai/paper-one: research notes (2026-09-27)

Sources used:
- **[API]**: `gh api repos/xiaolai/paper-one` (plus `/tags`, `/releases`, `/commits`)
- **[CLONE]**: a shallow clone at `d39f2df`, in `scratchpad/paper-one/`
- **[LEDGER]**: the course copy of Paper's feature ledger, `…/2026.09.16.功能账簿和莫斯科原则/feature-ledger.html`, whose header reads "rendered 2026-09-12 21:15". I parsed it to text; the extracts are `scratchpad/ledger.txt` and `scratchpad/inv.txt`.
- **[COMMIT]**: individual commit messages, read via `gh`.
- **[OURS]**: `docs/feature-ledger.md` in reader3-pro.

Anything marked *(inference)* is my reading, not a stated fact.

## 1. Facts

| Fact | Value | Source |
|---|---|---|
| Description | "Paper — a reading application"; homepage https://paper.one | API |
| Stars / forks / open issues | 8 / 5 / 1 (#3, a ResizeObserver loop error) | API, `gh issue list` |
| License | MIT | API, LICENSE |
| Language | TypeScript (plus Rust under `src-tauri/`) | API, CLONE |
| Topics | none | API |
| Created / pushed | 2026-08-24 / 2026-09-27 | API |
| Version | `package.json` 0.4.8. There are 2 tags (v0.4.7, v0.4.8) and **0 GitHub releases**. | CLONE, API |
| Commit pace | 500 commits between 2026-08-27 and 2026-09-27; that is the first 5 API pages, so it may be more | API |
| Status per the README | "personal project … nowhere near a release … no installer, no support"; developed on macOS; iOS/Android "compositions exist"; Windows/Linux "intended"; issues and PRs are not being solicited | CLONE README |
| Stack | Tauri 2 + React 19 + Vite 7 + TypeScript, with a Rust backend. EPUB goes through a **pinned fork of foliate-js** and PDF through **pdf.js 6.2**. Crypto uses `@noble/ed25519` and `@noble/hashes`. Peer-to-peer uses iroh / iroh-blobs. Tests are Vitest, Playwright, **Stryker mutation testing**, fast-check and dependency-cruiser. Package manager is pnpm; a CLI binary called `paper` ships alongside. | CLONE package.json, README, LEDGER |
| Architecture | A kernel plus optional **capabilities**, declared in `capabilities.manifest.json`: `peer`, `sync`, `circle`, `public`, `voices`, `passages`, `webhost`. Each capability declares its platforms. `pnpm verify:without` proves the app still builds without a given capability. | CLONE |
| Build targets | Scripts exist for `build:desktop`, `build:ios`, `build:android`, `build:web` and `build:cli`. The entry points are `index.html`, `index.mobile.html` and `index.web.html`. CI workflows are `verify.yml`, `bundle.yml` and `mobile.yml`. | CLONE |
| **The ledger is Paper's own** | The course HTML is titled "Feature ledger — Paper". Its Part 1 heading is "What Paper has", and it cites paths such as `src/capabilities/circle/…` that exist in the repo. The repo's `scripts/gen-feature-ledger.py` renders `dev-docs/feature-ledger.md` into `dev-docs/artifacts/feature-ledger.html`, and the course file matches that output (same five states, same CSS classes). | LEDGER, CLONE |
| The ledger is not in the repo | `.gitignore` excludes `dev-docs/` and `docs/`. It records that publishing the ledger was "set up on 2026-09-09 and REVERSED the same" day. The tracked parts are the generator, `scripts/check-ledger.mjs` (`pnpm ledger:check`) and a test ledger (`tests/ledger.json`, `pnpm test:ledger`). | CLONE .gitignore, scripts |
| **All AI features removed on 2026-09-19** | The commit "Remove every AI feature, and the surfaces they left behind" (+1 815 / −53 879 lines, 211 files) removed: the companion, Look up, the neural voice, the local `llama-server`, the Codex/Claude routes, cloud endpoints, and `tauri-plugin-inference`. The stated reason: "the providers cannot be unified … and the set of useful things to do with a model inside a reader turned out to be very small". The README's "gloss" bullet is therefore **stale**. | COMMIT |
| Added after the ledger snapshot | Neural read-aloud: "Paper's own voices", a Kokoro 82M ONNX model downloaded on demand, per `voices.manifest.json`; merged 2026-09-23. Search across the whole library: the `passages` capability, 2026-09-24, fully local. The reading-aloud transport and "audiobook", merged 2026-09-22. Auto page-turn and a time-left estimate (`core/autoAdvance.ts`). "Open a figure, seek to a place, cite a printed page", 2026-09-25. | COMMIT, CLONE |
| Homepage | **Not viewed.** The gstack browse `goto https://paper.one` failed with `ERR_CONNECTION_CLOSED`, and http failed with `ERR_EMPTY_RESPONSE`. DNS resolves to 198.18.1.6, a fake-IP range, so a local proxy is probably involved *(inference)*. curl was denied by permissions. | browse |

## 2. Feature inventory

The states come from LEDGER as of 2026-09-12. A **Now** note means the repo has since changed the row, based on COMMIT/CLONE evidence (commit subjects and file presence; I did not run the app). The ledger has 198 rows: Shipped 166, Partial 9, Stub 1, Absent 20, Unknown 2. The table groups them; rows not named individually are Shipped.

| Area | Feature (ledger state) | Now |
|---|---|---|
| **Platforms** | Desktop Tauri app, macOS primary (Shipped). A browser client served from the desktop through the `webhost` capability, with tap-to-turn (Shipped). The phone runs its own shell (**Partial**). A phone reading a book (**Absent**). Touch gestures (**Unknown**, inherited from foliate-js). | There is now a CI bundle build for Ubuntu 24.04 (commit of 2026-09-26). |
| **Formats** | EPUB and PDF, with PDF as a first-class book (Shipped). MOBI / AZW3 / CBZ / FB2 / FBZ (Shipped, via `core/formats.ts`). RTL and vertical writing (**Unknown**). Fixed-layout annotation (Shipped). | |
| **Layout / typography** (about 40 rows) | Scrolled and paginated flow. 14 text sizes from 15 to 28px. Size corrected for each typeface's x-height. 4 spacing axes. Brightness and contrast. Alignment and hyphenation treated as one decision. Language-aware hyphenation. 5 themes plus follow-OS. A "fidelity dial" deciding whether the book's or the reader's typography wins. Paragraph separation, an opening flourish, heading scale, CJK–Latin spacing. Settings for quotes, code face and wrapping, wide tables, note size, figure width/height/frame/scale, and minimum size. A choice of bundled typefaces. Scrollbar, progress rule, page-turn slide (**Partial**). All the rest Shipped. Continuous scroll, auto-scroll, split reading and per-book settings are **Absent**. | Auto page-turn appears in `autoAdvance.ts`; whether this closes "Auto-scroll" is unverified. |
| **Navigation** | TOC, in-book full-text search, footnote popover, back after a jump (⌘[ / ⌘]), position restore, bookmarks, a book switcher, a command palette (⌘K), a keyboard map, and wheel or gesture page turns (all Shipped). Image/figure zoom (**Absent**). | "Open a figure" was added 2026-09-25. |
| **Annotation** | Highlights anchored by CFI. 3 tints and 2 styles. Notes on a highlight. Margin notes beside their line. Selection tools. Copy with citation. Word-boundary snapping with gesture provenance. Overlap-based matching of marks. Unplaced marks and re-anchoring them. Export and import as JSON and Markdown (all Shipped). A companion provenance mark (**Stub**). Strikethrough/ink, annotation search and adjusting a mark's extent (**Absent**). | The companion mark kind was removed with the AI features. |
| **Cards** | Five card kinds, a card made from a mark, a filtered cards panel, export/import (Shipped). Spaced repetition (**Absent**). | |
| **Library** | A virtualised shelf with real covers. Shelf search with operators. Background metadata enrichment. Series shown. Folder import. Drag and drop anywhere. Collections, tags and shelves, with drag-to-tag. Trash plus undo. Mark as finished or unread. Two-click removal (all Shipped). Search across the whole library, folder watching and OPDS/Calibre (**Absent**). | Library-wide search has since **shipped** as the `passages` capability. |
| **Reading aids** | Reading ruler. Read-aloud with the system voice, with the spoken word followed on the page. Look up (all Shipped). Voice/rate/pitch control, translation and reading statistics (**Absent**). | Look up was removed. A voice picker and downloadable Kokoro voices were added 2026-09-22/23. Translation and statistics are still not seen. |
| **AI ("Companion")** | A provider interface, a conversation view, grounded answers with citations, Codex/Claude routes, a faster/more-thorough toggle, cloud endpoints and the gloss (Shipped). Local inference (**Partial**). Neural voice (**Absent**). | **All removed on 2026-09-19.** Paper now has no AI features. |
| **Sync** | Peer-to-peer sync between the owner's own devices (Shipped). Download a book this device lacks, evict the local copy, and a shelf vs satchel role per device (Shipped). Per-peer grants (**Partial**). Content-derived book identity (**Partial**). | |
| **Social: "the circle"** | Friends pair shelves using signed and sealed pages. Other features: a twelve-word identity, sharing a passage, a friend's passage drawn in your copy, a per-person budget, and mute/block/exit. There are also opinions and ratings per book, a friend's shelf and lists, and a Circle screen. Mostly Shipped; the circle end to end is **Partial**. Discovery, and a phone publishing, are **Absent**. | |
| **Social: "the public layer"** | Publishing to strangers by content hash, over iroh-blobs verified ranges. It includes a second signing key (the "voice"), withdrawal and expiry, silencing a voice, and receiving someone's notes. Mostly Shipped. DHT discovery and the Publish pane are **Partial**; following, feeds and a directory are **Absent**. | |
| **Data** | "A book is a folder." The app copies bytes into `$APPDATA/books/<id>/` on import. It also has local persistence, identity migration, work identity, and export/import of tags, marks and cards (Shipped). The `paper` CLI (**Partial**). | |
| **Security** | Book content cannot reach native code: a CSP plus script stripping at the loader (Shipped). Bundled font licences travel with the build. | |

## 3. Their ledger method, and MoSCoW

**MoSCoW does not appear anywhere in Paper's ledger or the repo.** I grepped the HTML for "MoSCoW / must have / should have / won't have" and got no hits; "could have" appears only in running prose. MoSCoW comes from the **course notes** (`20260916-…-notes.md`), which list "4. Feature Ledger / 5. MoSCoW / 6. 必须、应该、可能/可以、不能 / 7. pros and cons / 8. 权衡、选择、取舍" and link the repo. The other file in that folder is the course's full audio (`2026.09.16.功能账簿和莫斯科原则-完整音频.mp3`, 6.7M), which I did not listen to or transcribe. My guess is that it is where MoSCoW is taught *(inference)*.

What the ledger actually uses:
- **Five states**: `Shipped` means implemented and verified working in the app; `Partial` means it works with a named limit; `Stub` means types, a seam or UI exist but the behaviour does not ("A stub is not a feature"); `Absent` means not built; `Unknown` means inherited from a dependency and never tested ("claim nothing").
- **Part 1 inventory**: rows grouped by area, with columns **Capability | State | Where | How to confirm**. "How to confirm" is a hand check in the running app. The rows have **no IDs**.
- **Parts 2–3, a competitor gap matrix**: Paper against 10 readers (Readest, Foliate, Thorium, KOReader, Calibre, Apple Books, Kindle, Readwise Reader, Zotero, Highlights), marked with ● ◐ ○ – ◍. It has three buckets: **"Table stakes Paper is missing"**, **"Contested — real features, but not universal"** and **"What Paper has that most do not"**. This is the nearest thing to a prioritisation scheme. It is a market triage (table stakes, contested, differentiators), not MoSCoW. *Inference:* the course probably maps these onto Must, Should/Could and Won't.
- **Part 4, "Reading the matrix"**: argued prose naming "the first-ranked gap now". Closed gaps are struck through and kept as worked examples.
- **Dated re-audit passes** (08-21, 08-23, after phase 15, 09-05, 09-06, 09-09, 09-10, 09-11, 09-12). Each one names a **type of failure** in a table of its own: row drift (Was/Is), a whole surface missing, a misread of evidence, an overclaim against evidence, a claim true of one surface but written about the whole app, plus "What this does not close". There is also a "Sourcing" section that says the evidence is source reading plus tests, not app runs.
- **Mechanical gate `pnpm ledger:check`** asks three things. Does every `Where` path resolve? Is every State one of the five? Is every name the app registers covered by some row (`LEDGER_UNCOVERED`)? It explicitly states that it cannot judge whether a State is honest. Because the ledger is gitignored, the check **skips loudly** on a clean clone; `--require` turns the skip into a failure.
- **HTML is generated from the Markdown** and holds no data of its own. This follows an audit that found 44 records drifting between a hand-kept copy and the source. The page has a search box and state filter chips.

## 4. Gap against Reader3 Pro (F-001..F-041)

**What Paper has that we lack** (ours is a web app plus Python backend over EPUB only):
- Native desktop app (Tauri), with a mobile shell and a browser client served from the desktop.
- PDF, MOBI, AZW3, CBZ and FB2. Our PDF is a stub (F-038).
- Deep typography: x-height correction, a fidelity dial, CJK–Latin spacing, figure and code controls, a typeface choice, 5 themes. Ours has font size and paragraph spacing only (F-010 partial), while themes (F-031), font family (F-032) and page-turn buttons (F-033) are stubs.
- Anchoring by CFI with re-anchoring of unplaced marks. Ours is text-only with CFI always null (F-018 limits #6–#8).
- Margin notes, word-boundary snapping, copy with citation, bookmarks, footnote popover, back after a jump, reading ruler.
- Cards, as a separate kind from notes.
- Annotation export/import as JSON and Markdown. We export conversations (F-016) and have library JSON export only as a stub (F-036).
- Read-aloud, with both the system voice and downloadable neural voices.
- Import (folder, drag and drop, in-app). Ours is CLI-only; in-app Add is a stub (F-034).
- Trash with undo. Our delete is absent (F-035).
- Tags, series, cover art, metadata enrichment.
- Peer-to-peer sync, and the social layers (circle and public).
- CLI noun-verb commands with `--json`.
- Mutation testing (Stryker) and architecture/boundary gates.

**What we have that Paper lacks:**
- **AI Q&A and summaries with RAG** (F-012/F-013), **multiple providers** (F-014), per-book queue (F-015), conversation threads and export (F-016), library-panel chat (F-017). Paper *removed* all of this; the rationale is in the 2026-09-19 commit and is useful counter-evidence for our roadmap.
- **Semantic / hybrid vector search** with ChromaDB (F-012). Paper's library search is keyword postings only, local, with no embeddings. That is an inference from the passages header ("NOTHING IS SENT ANYWHERE"); I did not read its code in depth.
- Diacritic-normalized keyword search with deep links (F-011).
- A library stats dashboard (F-007). Paper lists reading statistics as Absent and "table stakes missing".
- A self-hosted HTTP server with a documented API, an origin guard, and a single gate for provider egress (F-023/F-024/F-027/F-041).
- Crash-safe publishing of a book (F-003). *Inference:* Paper has analogues (journal closed on quit, a durable library lock) that aren't comparable one-to-one.

**How their ledger format differs from ours:** ours clearly descends from theirs, since it uses the same five states and the same "a stub is not a feature" and "claim nothing" wording.

| Aspect | Paper | Reader3 Pro |
|---|---|---|
| Row ID | None; rows are named by capability | `F-NNN`, permanent and never reused |
| States | 5 | The same 5 plus `deprecated`, `superseded → F-NNN` and `removed` (rows are retired, never deleted) |
| Columns | Capability, State, Where, How to confirm | A summary table plus a section per row: What, Routes, Code, Tests, Confirm, Tracked, Evidence, Limits |
| Tests / evidence | No per-row tests or evidence columns; evidence lives in the audit narratives | Required `Tests` and `Evidence` (PR/SHA/`baseline`) |
| Absent rows | Free; they include competitor-derived wishes | Must carry a `Tracked` debt or plan link: "not a roadmap" |
| Competitor matrix | Yes: 10 readers, three buckets (table stakes, contested, differentiators) | None |
| Prioritisation | Implicit, through the matrix buckets and "first-ranked gap" prose; no MoSCoW labels | None in the ledger; it lives in `docs/plans/` |
| Audit log | Long dated narrative passes with a table per failure type | Short entries: Scope / Found / Not audited |
| Coverage check | `LEDGER_UNCOVERED`: every registry name in the app must have a row | Every route in `routes.snapshot` must be claimed by a row |
| Publication | Private (gitignored); the gate skips on a clone | Tracked in the repo; CI enforces `--check` for drift |
| HTML | Generated from the Markdown; search plus state chips | Generated `ledger-data` JSON block; dashboard |

## 5. Notes and uncertainties

- The ledger snapshot is **15 days older** than HEAD. Its AI section, the Look up row and the Absent rows for neural voice and library search are all overtaken; the "Now" notes above come from commit subjects and file presence, not from running the app.
- MoSCoW is sourced only from the course notes' bullet list. How xiaolai applies it (to which features, and with what "Won't") is **not in anything I read**; the course audio probably holds it but I did not listen to it.
- The homepage https://paper.one could not be loaded from this machine, so nothing here is sourced from it.
- The 10 comparator columns are self-described in the ledger as "2026-08-21 research … not re-checked", with the circle row's cells "placed from general knowledge".
- The commit count of 500 is a lower bound (only 5 API pages fetched).
- The iOS/Android state is from the README ("compositions exist") and the ledger ("phone runs its own shell: Partial; a phone reading a book: Absent"). No mobile release artifacts were seen.
