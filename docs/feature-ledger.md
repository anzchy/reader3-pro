# Feature Ledger

**Synced:** 2026-09-27 at commit `8e1cf48`

The as-built record of what Reader3 Pro **can do today**: one row per user-visible (or
operator-visible) capability, where it lives, what tests prove it, and the evidence it was
accepted. Read it at session start to rebuild "what exists" without re-deriving it from code.

It also records, with the same rigour, what the product **looks like it can do but can't**
(`stub`), what is **tracked but not built** (`absent`), and what it **exposes from a dependency
without testing** (`unknown`) — so that nobody describes the product from its surface.

**What this file is not** (「搬，不抄」 — link, don't copy):

| Question | Authority |
|---|---|
| Why is it designed this way? | [`docs/adr/`](adr/README.md) |
| What is planned / in flight, and in what order? | [`docs/plans/20260824-frontend-backend-plan-progress.md`](plans/20260824-frontend-backend-plan-progress.md) + the `plan-and-branch-map` skill |
| Which work items / tasks built it? | the plan folder's `tasks/{branch}.md` or `### WI-N:` headings |
| Open defects against a feature | the debt table in 009 (referenced here by `#N` only) |
| Route surface | [`tests/contract/routes.snapshot`](../tests/contract/routes.snapshot) (API v1 freeze, ADR-0011) |

## Rules

1. **Every status needs evidence.** `accepted` / `partial` still require acceptance: merged to
   `master` **and** its gating lanes green (`uv run pytest tests/unit tests/contract`,
   `npm test`, plus the e2e cases named in its row). Never grade work that is planned, on an
   unmerged branch, or "done but untested" as `accepted` / `partial`. `stub`, `absent` and
   `unknown` may be recorded whenever they are observed, but: a `stub` needs a `Confirm` step
   that shows the surface is inert; an `absent` row needs a `Tracked` bullet linking a debt `#N`
   or a plan / branch number. The ledger is not a roadmap — untracked wishes don't go here;
   planned work lives in `docs/plans/`.
2. **Same change as the feature.** Update the ledger in the PR / commit that lands the
   acceptance (or the plan write-back commit right after the merge) — not in a later sweep.
3. **Granularity = an independently acceptable capability.** Not a bugfix, WI, or task. A fix
   updates an existing row's `Evidence` / `Limits`; it does not add a row. A dead surface or a
   tracked gap that would otherwise hide inside another row's `Limits` gets its own `stub` /
   `absent` row, and the original `Limits` points at it (`see F-NNN`).
4. **IDs are permanent.** `F-NNN`, never renumbered or reused. Rows are never deleted: a
   retired feature becomes `deprecated`, `superseded → F-NNN`, or `removed`.
5. **Every row points at things that exist.** `Code`, `Tests` and `Routes` must name paths /
   routes that exist (routes exactly as written in `routes.snapshot`). Which bullets a row must
   carry depends on its status — see [Row grammar](#row-grammar). If a refactor moves them, fix
   the row in the same change.
6. **The HTML view is generated from this file.** [`feature-ledger.html`](feature-ledger.html) is
   a status dashboard of this ledger; its data lives in one `<script id="ledger-data">` JSON block
   that nobody edits by hand. Workflow: edit this file → bump the `**Synced:**` line → run
   `python3 scripts/build_feature_ledger.py`, which rewrites the block, in the same change. CI
   enforces it with `python3 scripts/build_feature_ledger.py --check` (validation + drift).
   On disagreement this file wins.
7. **Evidence, not assertion.** `Evidence` is a PR number, merge/squash SHA, or tag. The
   rows marked `baseline` were seeded retroactively on 2026-09-27 from code + tests at
   `8e1cf48`; they were not re-run as an acceptance pass. Replace `baseline` with real evidence
   the next time the feature is touched.

**Status values:** `accepted` (shipped, merged, gating lanes green, fully meets its scope) ·
`partial` (shipped, with a named gap in `Limits`) · `stub` (a visible surface — UI control,
route, setting, type — exists but the behaviour does not; a stub is **not** a feature and the
product must not be described as having it) · `absent` (not built, but tracked: must link a debt
`#N` or a plan) · `unknown` (inherited from a dependency, e.g. epub.js / ChromaDB / FastAPI,
never tested here — claim nothing) · `deprecated` (still present, scheduled to go) ·
`superseded → F-NNN` · `removed`.

## Row grammar

Each feature section is headed `#### F-NNN Name — status` and carries bullets written
`- **Label:** value`, with these labels, in this order:

| Label | Required for | Format |
|---|---|---|
| `What` | all | one or two sentences |
| `Routes` | optional (UI-only / internal rows omit it) | comma-separated backticked entries, each **exactly** a line of `routes.snapshot` (e.g. `` `GET /api/search/{book_id}` ``) or a CLI entry `` `cli: reader3` `` / `` `cli: reader3-server` ``. Every snapshot line and both CLI names are claimed by ≥ 1 row; a route may be claimed by several |
| `Code` | all except `absent` and `removed` | backticked paths, optionally ` · ADR-NNNN, ...` |
| `Tests` | `accepted`, `partial`; optional for `stub` / `unknown` / `deprecated` / `superseded`; omitted for `absent` and `removed` | backticked paths, optional trailing parenthetical note |
| `Confirm` | `accepted`, `partial`, `stub`, `unknown`; optional for `deprecated` / `superseded` / `removed`; omitted for `absent` | how a person verifies it by hand in the running app (`uv run reader3-server`, then what to open / click / type and what they should see) or the CLI / a curl call. For `stub`, it shows the surface and that nothing happens |
| `Tracked` | `absent` | debt `#N` and/or plan / branch number |
| `Evidence` | all except `absent` | PR #, SHA, tag, or `baseline`; a `removed` row cites the removal PR / SHA |
| `Limits` | optional | open debts `#N`, known gaps, `see F-NNN` |

`Confirm` steps use `{book_id}` for a processed book folder (e.g. `dracula_data`) and
`{book_uuid}` for the `book_uuid` in its `ai_meta.json`; the server is at `http://127.0.0.1:8123`.

## Summary

| ID | Feature | Area | Status | Evidence |
|---|---|---|---|---|
| F-001 | EPUB ingest CLI | EPUB processing | accepted | v1.0 · baseline |
| F-002 | Semantic index CLI | EPUB processing | accepted | 001/002 · baseline |
| F-003 | Crash-safe book publish | EPUB processing | partial | 007 · PR #26 |
| F-004 | Stat-keyed book cache | EPUB processing | accepted | 011 |
| F-005 | 3-pane library | Library | accepted | PR #12/#13/#14/#25 |
| F-006 | Collections | Library | accepted | 004 · PR #26 |
| F-007 | Library stats dashboard | Library | accepted | 004 · baseline |
| F-008 | Bulk index from selection | Library | accepted | 004 · baseline |
| F-009 | Paginated epub.js reader | Reader | accepted | 006 · PR #16/#17 |
| F-010 | Reader preferences | Reader | partial | 006 · PR #21 |
| F-011 | Keyword search | Search | accepted | 001 · PR #1/#2 |
| F-012 | Semantic / hybrid search | Search | accepted | 001/002 · 011/017 |
| F-013 | AI Q&A + summary | AI | accepted | 002 · PR #3–#8 |
| F-014 | Multi-provider support | AI | accepted | 002 · baseline |
| F-015 | Per-book AI request queue | AI | accepted | 011/017 |
| F-016 | Conversation threads + export | AI | accepted | 002 · baseline |
| F-017 | Library-panel chat | AI | accepted | 004/013 · PR #25 |
| F-018 | Annotations + notes | Notes | partial | 006 |
| F-019 | Note write-conflict handling | Notes | partial | 011/017 |
| F-020 | Settings page + API | Settings & UI | accepted | 002 · 013 WI-12 · PR #25 |
| F-021 | Light/dark theme (no FOUC) | Settings & UI | accepted | 013 WI-10 · PR #25 |
| F-022 | Degradation UI components | Settings & UI | partial | 013 Track D · PR #25 |
| F-023 | Request origin guard | Security | accepted | 008 · v1.5.0 |
| F-024 | Provider egress single gate | Security | accepted | ADR-0006 · baseline |
| F-025 | Safe unpickling + path safety | Security | accepted | ADR-0012 · baseline |
| F-026 | Book UUID resolution | Security | accepted | PR #26 |
| F-027 | Server runtime options + health | Infra | accepted | v1.5.0 |
| F-028 | Test net + CI | Infra | accepted | 008/009 · PR #19/#20 |
| F-029 | Repo lints | Infra | accepted | 007/013 |
| F-030 | Vite + TS frontend toolchain | Infra | accepted | 013 WI-9 · PR #25 |
| F-031 | Reader paper themes | Reader | stub | debt #21 · baseline |
| F-032 | Reader font-family picker | Reader | stub | spec D1 · baseline |
| F-033 | Page-turn click zones | Reader | stub | debt #11 · baseline |
| F-034 | In-app book import ("Add books") | Library | stub | debt #57 · baseline |
| F-035 | Book delete | Library | absent | tracked #58 |
| F-036 | Library JSON export | Settings & UI | stub | debt #53 · baseline |
| F-037 | Bulk re-index all books | Settings & UI | stub | debt #52 · baseline |
| F-038 | PDF format scope | Library | stub | 004 · baseline |
| F-039 | Library chat all-books / collection scope | AI | stub | 013 WI-13 · baseline |
| F-040 | Notes "点评此书" (review this book) | Notes | stub | baseline |
| F-041 | Interactive API docs | Infra | unknown | 008 snapshot · baseline |

## Features

Paths are written out in full from the repo root (e.g. `src/reader3_app/reader3.py`, `tests/e2e/`); nothing is abbreviated.

### EPUB processing

#### F-001 EPUB ingest CLI — accepted
- **What:** `uv run reader3 <file.epub>` parses an EPUB into `books/{name}_data/` (`book.pkl`, `book.epub`, `images/`).
- **Routes:** `cli: reader3`
- **Code:** `src/reader3_app/reader3.py`
- **Tests:** `tests/unit/test_process_epub_commit.py`
- **Confirm:** Run `uv run reader3 ./books/dracula.epub`: it prints a `--- Summary ---` block (Title, Authors, Physical Files (Spine), TOC Root Items, Images extracted), and `books/dracula_data/` then holds `book.pkl`, `book.epub` and `images/`.
- **Evidence:** v1.0 · baseline

#### F-002 Semantic index CLI — accepted
- **What:** `uv run reader3 --index <book_folder> [--force]` builds the per-book ChromaDB index.
- **Routes:** `cli: reader3`
- **Code:** `src/reader3_app/reader3.py`, `src/reader3_app/vector_search.py`
- **Tests:** `tests/unit/test_semantic_extra_optional.py`
- **Confirm:** Run `uv run reader3 --index dracula_data`: it prints `Indexed dracula_data: N chunks using paraphrase-multilingual-MiniLM-L12-v2`. Without the extra it exits with "Semantic search dependencies are not installed. Install the optional extra: `uv sync --extra semantic` …" instead of a traceback.
- **Evidence:** 001/002 · baseline
- **Limits:** requires the optional `semantic` extra (`uv sync --extra semantic`).

#### F-003 Crash-safe book publish — partial
- **What:** stage → verify → atomic swap → recovery after kill when (re)processing a book.
- **Code:** `src/reader3_app/reader3.py` · ADR-0007
- **Tests:** `tests/unit/test_process_epub_staging.py`, `tests/unit/test_process_epub_sigkill_recovery.py`
- **Confirm:** Re-run `uv run reader3 ./books/dracula.epub` over an already processed book: afterwards `ls books/` shows no leftover `dracula_data.staging-<pid>` directory and `/read/dracula_data/0` still opens. Kill-mid-run recovery is only verifiable through the tests named above.
- **Evidence:** 007 · PR #26 (`b8e0353`)
- **Limits:** ADR-0007 is Partial; debt #59 half-cleared, remainder moved to 012 Q2.

#### F-004 Stat-keyed book cache — accepted
- **What:** loaded books are cached and reloaded when `book.pkl` changes on disk.
- **Code:** `src/reader3_app/book_store.py`
- **Tests:** `tests/contract/test_book_store_route_freshness.py`
- **Confirm:** With `uv run reader3-server` running, open `/read/{book_id}/0`, re-process the same EPUB with `uv run reader3`, then reload the page: the re-processed content is served without restarting the server.
- **Evidence:** 011

### Library

#### F-005 3-pane library — accepted
- **What:** library page at `GET /` — grid/list view, sort, select mode, format counts, Dedao-style UI.
- **Routes:** `GET /`, `MOUNT /static`
- **Code:** `src/reader3_app/web/routers/library.py`, `frontend/src/library/`
- **Tests:** `tests/e2e/shell_4a/`, `tests/e2e/baseline_1b/test_library_nav_and_collections.py`
- **Confirm:** `uv run reader3-server`, open `http://127.0.0.1:8123/`: a sidebar (Types / Collections), the book grid, and a right panel with Dashboard / Chat / Search tabs. `▦` / `☰` switch grid and list, `A→Z` sorts, `✓` enters select mode and shows the bulk bar (Select all / Clear / Add to collection / Index selected).
- **Evidence:** 004 (PR #12/#13) · 005 restyle (PR #14) · TS port 013 WI-13 (PR #25)
- **Limits:** no upload/import (#57), delete (#58), export (#53) — planned in 012/018 (see F-034, F-035, F-036).

#### F-006 Collections — accepted
- **What:** create/rename/delete collections; add/remove books (`/api/collections*`).
- **Routes:** `GET /api/collections`, `POST /api/collections`, `GET /api/collections/{collection_id}`, `PUT /api/collections/{collection_id}`, `DELETE /api/collections/{collection_id}`, `POST /api/collections/{collection_id}/books`
- **Code:** `src/reader3_app/collections_service.py`, `src/reader3_app/web/routers/library.py`
- **Tests:** `tests/unit/test_collections_concurrency.py`, `tests/contract/test_collections_books_route_race.py`
- **Confirm:** On the library page click `+` next to Collections, enter a name, press Create: a toast 「已创建收藏夹「name」」 appears and the collection is listed. In select mode tick books → Add to collection → pick it: 「已加入「name」」 and its badge count rises; its Delete button removes it after the confirm prompt.
- **Evidence:** 004 · locking fix PR #26 (`4d3c5ac`)
- **Limits:** debt #18 (hyphen in names parsed as regex range).

#### F-007 Library stats dashboard — accepted
- **What:** `GET /api/library/stats?scope=` aggregates reading / indexing stats.
- **Routes:** `GET /api/library/stats`
- **Code:** `src/reader3_app/web/routers/library.py`
- **Tests:** `tests/contract/routes.snapshot`
- **Confirm:** The library's Dashboard tab shows Books / Indexed / Sections / Chunks and an indexed-percent bar; Refresh stats re-fetches. `curl 'http://127.0.0.1:8123/api/library/stats?scope=all'` returns `scope`, `books_total`, `books_indexed`, `indexed_percent`, `sections_total`, `chunks_total`, `computed_at`; `scope=bogus` returns 400 `Invalid scope`.
- **Evidence:** 004 · baseline
- **Limits:** `format:pdf` scope is a placeholder (no PDF support) (see F-038).

#### F-008 Bulk index from selection — accepted
- **What:** index several selected books from the library in one action.
- **Routes:** `POST /api/index/{book_id}`, `GET /api/index/{book_id}/status`
- **Code:** `frontend/src/library/`
- **Tests:** `tests/e2e/shell_4a/`
- **Confirm:** On the library page press `✓`, tick two books, press Index selected: their status pills move to indexed and the live region announces "Indexing finished."; a failure opens the "Indexing completed with errors" dialog. With nothing ticked, Index selected is disabled.
- **Evidence:** 004 · baseline
- **Limits:** no bulk re-index route (#52, planned in 012) (see F-037).

#### F-034 In-app book import ("Add books") — stub
- **What:** the library top bar's "+ Add books" button suggests in-app import, but it only opens a dialog telling the user to run the CLI; there is no file picker, drop zone, or upload route.
- **Code:** `src/reader3_app/web/templates/library.html`, `frontend/src/library/index.ts`
- **Confirm:** On the library page click "+ Add books" (`lib-topbar-add-books`): the "Add books" dialog says to run `uv run reader3 path/to/book.epub` and refresh; OK closes it. No file chooser opens and no request is sent.
- **Evidence:** debt #57 · baseline
- **Limits:** the upload / import route is debt #57 (012-storage-format); importing today is F-001 only.

#### F-035 Book delete — absent
- **What:** deleting a book from the app (route + library UI); today the only way is removing `books/{id}_data/` by hand.
- **Tracked:** debt #58 → 012-storage-format; frontend half FB-L18

#### F-038 PDF format scope — stub
- **What:** the library sidebar lists a PDF type and the stats API accepts `scope=format:pdf`, but no PDF can be ingested; the scope is a placeholder that always counts zero.
- **Routes:** `GET /api/library/stats`
- **Code:** `src/reader3_app/web/templates/library.html`, `src/reader3_app/web/routers/library.py`
- **Tests:** `tests/e2e/baseline_1b/test_library_nav_and_collections.py`
- **Confirm:** In the library sidebar under Types, the PDF button (`lib-sidebar-scope-pdf`) is disabled with the tooltip "PDF not supported yet" and a 0 badge; clicking it does nothing. `curl 'http://127.0.0.1:8123/api/library/stats?scope=format:pdf'` returns `books_total: 0`.
- **Evidence:** 004 · baseline

### Reader

#### F-009 Paginated epub.js reader — accepted
- **What:** full-screen paginated reader in an iframe; TOC panel, keyboard navigation, back-to-library.
- **Routes:** `GET /read/{book_id}`, `GET /read/{book_id}/{chapter_index}`, `GET /read/{book_id}/book.epub`, `GET /read/{book_id}/images/{image_name}`
- **Code:** `src/reader3_app/web/routers/reader.py`, `src/reader3_app/web/static/js/epub-renderer.js` · ADR-0002
- **Tests:** `tests/e2e/baseline_1b/test_read_paths.py`, `tests/e2e/baseline_1b/test_read_presentation_anchoring.py`
- **Confirm:** Click a book card in the library → `/read/{book_id}/0` opens paginated; `→` / `PageDown` and `←` / `PageUp` turn pages, `↓` / `↑` change section, and the progress pill reads 「当前阅读至 N%」. The rail's Table of Contents button opens the chapter list with a "Search chapters..." filter; the back arrow returns to the library.
- **Evidence:** 006 · PR #16/#17
- **Limits:** still classic JS; TS rewrite is 014. Page turning is keyboard-only (see F-033).

#### F-010 Reader preferences — partial
- **What:** font size and paragraph spacing, applied in the correct order.
- **Code:** `src/reader3_app/web/templates/reader.html`, `src/reader3_app/web/static/js/epub-renderer.js`
- **Tests:** `tests/e2e/baseline_1b/`
- **Confirm:** In the reader click the rail's "Aa" (Font Settings): 文字 `+` / `−` changes 当前字号 (default 17) and the page text size, 段落间距 `+` / `−` changes 当前间距 (default 1.9); both survive a reload (`localStorage["reader3-font-settings"]`).
- **Evidence:** 006 · apply-order fix 016 (PR #21)
- **Limits:** the four reader themes are dead (#21); page prev/next buttons are a dead surface (#11) (see F-031, F-032, F-033).

#### F-031 Reader paper themes — stub
- **What:** the reader's font popover shows four paper themes (白色 / 黄色 / 护眼 / 夜间); none has a listener, so the reading theme never changes.
- **Code:** `src/reader3_app/web/templates/reader.html`
- **Tests:** `tests/e2e/baseline_1b/test_read_presentation_anchoring.py` (pins that clicking does not break annotations; cannot assert a theme change)
- **Confirm:** In the reader open "Aa": the 主题 row shows 白色 / 黄色 / 护眼 / 夜间 greyed out with a not-allowed cursor; clicking any leaves 白色 highlighted and the page colour unchanged.
- **Evidence:** debt #21 · baseline
- **Limits:** debt #21 (wire them or drop the testids); rewrite planned in the frontend plan WI-18.

#### F-032 Reader font-family picker — stub
- **What:** the same popover offers four font families (系统字体 / 得到今楷 / 汉仪旗黑 / 思源宋体); none has a listener.
- **Code:** `src/reader3_app/web/templates/reader.html`
- **Confirm:** In the reader open "Aa": the 字体 row's four options are greyed out with a not-allowed cursor; clicking any leaves 系统字体 highlighted and the text font unchanged.
- **Evidence:** spec D1 (`docs/plans/20260817-frontend-ui-refactor/spec-frontend-design.md`) · baseline
- **Limits:** frontend plan WI-18 / FB-R15 replaces it with a two-option picker (the three commercial fonts are unlicensed and unbundled).

#### F-033 Page-turn click zones — stub
- **What:** `rd-page-prev` / `rd-page-next` ("Previous page" / "Next page") exist in the reader DOM but are `display: none` and have no listener in any loaded script.
- **Code:** `src/reader3_app/web/templates/reader.html`
- **Tests:** `tests/e2e/baseline_1b/test_read_chapter_change_and_search.py` (asserts they are never used)
- **Confirm:** In the reader, clicking the left or right page edge does nothing; in DevTools `document.querySelector('[data-testid="rd-page-prev"]')` exists but is hidden. Only the keyboard turns pages (F-009).
- **Evidence:** debt #11 · baseline
- **Limits:** debt #11 (bind them or delete them with their testids).

### Search

#### F-011 Keyword search — accepted
- **What:** in-book and whole-library search, case sensitivity, diacritic normalization (café→cafe), deep links `?q=&occurrence=`, in-chapter highlight.
- **Routes:** `GET /api/search/{book_id}`, `GET /api/search/library`, `POST /api/highlight/{book_id}/{chapter_order}`
- **Code:** `src/reader3_app/search_service.py`, `src/reader3_app/web/routers/search.py`
- **Tests:** `tests/unit/test_highlight_utf16_offsets.py`, `tests/e2e/baseline_1b/test_read_chapter_change_and_search.py`, `frontend/tests/library/search.test.ts`
- **Confirm:** In the reader click the rail's Search, leave Mode on keyword, type a word: results list; clicking one jumps to and highlights it. The library's Search tab ("Search across your library...") searches all books. `curl 'http://127.0.0.1:8123/api/search/{book_id}?q=cafe'` also matches "café".
- **Evidence:** 001 · PR #1/#2
- **Limits:** library search deserializes every book (#35, assigned to 012).

#### F-012 Semantic / hybrid search — accepted
- **What:** semantic and hybrid search modes over a per-book ChromaDB store (`paraphrase-multilingual-MiniLM-L12-v2`). Degrades cleanly when the extra isn't installed.
- **Routes:** `GET /api/search/{book_id}`, `GET /api/search/library`, `POST /api/index/{book_id}`, `GET /api/index/{book_id}/status`
- **Code:** `src/reader3_app/vector_search.py`, `src/reader3_app/web/routers/search.py` · ADR-0004
- **Tests:** `tests/unit/test_semantic_extra_optional.py`
- **Confirm:** After F-002 indexing, `curl http://127.0.0.1:8123/api/index/{book_id}/status` returns `status` and a non-zero `chunk_count`; in the reader Search drawer switch Mode to semantic or hybrid and a query returns results. Without the extra, `curl -X POST http://127.0.0.1:8123/api/index/{book_id} -H 'Content-Type: application/json' -d '{}'` returns 400 with the `uv sync --extra semantic` hint.
- **Evidence:** 001/002 · optional-extra 011/017
- **Limits:** ADR-0004 is Partial.

### AI

#### F-013 AI Q&A + summary — accepted
- **What:** streaming Q&A (SSE) and summaries; token-budget routing chooses full-book / multi-chapter / RAG, with keyword fallback when no index.
- **Routes:** `POST /api/ai/question/{book_uuid}`, `POST /api/ai/summary/{book_uuid}`, `POST /api/ai/rag/retrieve`
- **Code:** `src/reader3_app/ai/routing.py`, `src/reader3_app/ai/rag.py`, `src/reader3_app/web/routers/ai/`
- **Tests:** `tests/unit/test_routing_token_budget.py`, `tests/e2e/baseline_1b/test_other_ai_streaming.py`
- **Confirm:** With a provider enabled in `/settings`, open a book, click the rail's AI Assistant, type in "Ask about this book... (Enter to send)" and press Send: the answer streams in and Stop can cut it off. The Summary / Highlights / Background buttons each produce a summary message.
- **Evidence:** 002 · PR #3–#8
- **Limits:** questions about an unindexed book (#26).

#### F-014 Multi-provider support — accepted
- **What:** Anthropic, OpenAI, Gemini, OpenRouter, Ollama; per-provider config and "test connection".
- **Routes:** `GET /api/settings/providers`, `GET /api/settings/providers/{provider_name}`, `PUT /api/settings/providers/{provider_name}`, `DELETE /api/settings/providers/{provider_name}`, `POST /api/settings/providers/{provider_name}/test`, `GET /api/ollama/status`, `GET /api/ollama/models`
- **Code:** `src/reader3_app/ai/providers/`, `src/reader3_app/ai/config.py`, `src/reader3_app/web/routers/settings.py`
- **Tests:** `tests/unit/test_provider_retry.py`, `tests/contract/test_provider_test_route.py`
- **Confirm:** Open `/settings` → 服务商: each provider has a card with 模型, 服务地址 and (except Ollama) API 密钥; 保存 then 测试连接 reports OK or the provider's error. The Ollama card's 刷新模型 fills the model list; `curl http://127.0.0.1:8123/api/ollama/status` reports whether Ollama is running.
- **Evidence:** 002 · baseline
- **Limits:** retry only on the non-streaming path (#36).

#### F-015 Per-book AI request queue — accepted
- **What:** per-book request queue with leases and a budget, so concurrent AI calls don't pile up.
- **Routes:** `POST /api/ai/question/{book_uuid}`, `POST /api/ai/summary/{book_uuid}`
- **Code:** `src/reader3_app/ai/queue.py`
- **Tests:** `tests/unit/test_ai_queue_lease.py`, `tests/unit/test_ai_queue_budget.py`
- **Confirm:** With a provider enabled, fire a dozen concurrent `curl -X POST http://127.0.0.1:8123/api/ai/question/{book_uuid} -H 'Content-Type: application/json' -d '{"question":"hi","provider":"ollama"}' &` for one book: requests run one at a time, and those beyond 10 pending get HTTP 429 "Too many pending AI requests. Please try again." (a request that waits past its timeout gets 504).
- **Evidence:** 011/017

#### F-016 Conversation threads + export — accepted
- **What:** multiple conversation threads per book; export as json / text / md.
- **Routes:** `GET /api/ai/conversations/{book_uuid}`, `GET /api/ai/conversations/{book_uuid}/{conversation_id}`, `PUT /api/ai/conversations/{book_uuid}/{conversation_id}`, `DELETE /api/ai/conversations/{book_uuid}/{conversation_id}`, `GET /api/ai/conversations/{book_uuid}/{conversation_id}/export`
- **Code:** `src/reader3_app/ai/conversations.py`, `src/reader3_app/web/routers/ai/conversations.py`
- **Tests:** `tests/unit/test_conversation_never_silently_dropped.py`
- **Confirm:** In the reader's AI panel, New chat starts a second thread and both appear in the History list; pick MD / TXT / JSON and press Export to download the thread. `curl 'http://127.0.0.1:8123/api/ai/conversations/{book_uuid}/{conversation_id}/export?format=xml'` returns 400 "Invalid format (use json|text|md)".
- **Evidence:** 002 · baseline

#### F-017 Library-panel chat — accepted
- **What:** chat from the library's right panel, scoped to one book: pick a book, continue one of its five latest threads or start a new one, streamed over SSE.
- **Routes:** `POST /api/ai/question/{book_uuid}`, `GET /api/ai/conversations/{book_uuid}`
- **Code:** `frontend/src/library/chat.ts`
- **Tests:** `frontend/tests/library/chat.test.ts`
- **Confirm:** On the library page open the Chat tab, choose a book in "Select a book...", type in "Ask about this book..." and press Send: the reply streams into the thread (Stop cancels); "History (latest 5)" then lists the thread.
- **Evidence:** 004 · TS port 013 (PR #25)
- **Limits:** single-book scope only; the All books / Collection scopes are disabled (see F-039).

#### F-039 Library chat all-books / collection scope — stub
- **What:** the library Chat tab shows "All books" and "Collection" scope buttons, but both are disabled; only single-book chat (F-017) exists.
- **Code:** `src/reader3_app/web/templates/library.html`, `frontend/src/library/chat.ts`
- **Confirm:** On the library page open the Chat tab: "All books" and "Collection" are disabled with the tooltip "Coming soon"; clicking them does nothing and "Single book" stays active.
- **Evidence:** 013 WI-13 · baseline
- **Limits:** `spec-frontend-design.md` rules these placeholders are to be deleted rather than built.

### Notes

#### F-018 Annotations + notes — partial
- **What:** highlight / underline / wavy in colors, with attached notes; notes panel.
- **Routes:** `GET /api/notes/{book_id}`, `GET /api/notes/{book_id}/{chapter_index}`, `POST /api/notes/{book_id}/{chapter_index}`, `PUT /api/notes/{book_id}/{chapter_index}/{note_id}`, `DELETE /api/notes/{book_id}/{chapter_index}/{note_id}`
- **Code:** `src/reader3_app/notes_service.py`, `src/reader3_app/models/annotations.py`, `src/reader3_app/web/static/js/annotations.js` · ADR-0005
- **Tests:** `tests/e2e/test_notes_write_failure_is_attributable.py`, `tests/e2e/test_stored_cfi_must_agree_with_quote.py`
- **Confirm:** In the reader select a sentence: the toolbar offers color dots, Marker / Wavy / Underline, Add Note, Copy, Delete, Ask AI. Pick Marker, then Add Note → "Write your thoughts..." → Save; the rail's Notes button lists it (「共N条笔记」), it survives a reload, and `books/{book_id}_data/notes.json` holds it.
- **Evidence:** 006
- **Limits:** text-only anchoring, CFI always null (#6–#8); `PUT` accepts only `note_text` (#29). Reader-side split is 014. The notes panel's 点评此书 button is dead (see F-040).

#### F-019 Note write-conflict handling — partial
- **What:** ETag optimistic concurrency on note writes, with a conflict dialog (DEG-S5).
- **Routes:** `POST /api/notes/{book_id}/{chapter_index}`, `PUT /api/notes/{book_id}/{chapter_index}/{note_id}`, `DELETE /api/notes/{book_id}/{chapter_index}/{note_id}`
- **Code:** `src/reader3_app/web/routers/notes.py`
- **Tests:** `tests/e2e/acceptance_2a/test_deg_s5_write_conflict.py`, `tests/e2e/test_conflict_resolution_single_flight.py`
- **Confirm:** `curl -i http://127.0.0.1:8123/api/notes/{book_id}/0` shows an `ETag` header; `curl -i -X PUT http://127.0.0.1:8123/api/notes/{book_id}/0/{note_id} -H 'If-Match: "stale"' -H 'Content-Type: application/json' -d '{"note_text":"x"}'` returns 409 with the current `etag`. In the UI, editing the same note from two tabs makes the second save show the conflict dialog with 保留我的 / 采用远端.
- **Evidence:** 011/017
- **Limits:** scope of what is covered vs. deferred has not been re-audited since 017.

#### F-040 Notes "点评此书" (review this book) — stub
- **What:** the notes panel footer has a 点评此书 button (`rd-notes-review`) with no handler in any loaded script.
- **Code:** `src/reader3_app/web/templates/reader.html`, `src/reader3_app/web/static/js/notes-panel.js`
- **Confirm:** In the reader click the rail's Notes: the footer shows 点评此书 next to 复制全部笔记; clicking 点评此书 does nothing (no dialog, no request), while 复制全部笔记 works.
- **Evidence:** baseline

### Settings & UI

#### F-020 Settings page + API — accepted
- **What:** `/settings`, `GET/PUT /api/settings`, export/import without API keys; keys never returned to the browser; file written `0600`.
- **Routes:** `GET /settings`, `GET /api/settings`, `PUT /api/settings`, `GET /api/settings/export`, `POST /api/settings/import`
- **Code:** `src/reader3_app/web/routers/settings.py`, `frontend/src/settings/`
- **Tests:** `tests/unit/test_settings_file_permissions.py`, `tests/unit/test_ai_settings_no_key_loss.py`
- **Confirm:** Click Settings in the library top bar → `/settings` shows AI 偏好, 服务商, 外观, 数据, 导出与导入. Change 每次检索的片段数 and press 保存偏好: the value survives a reload. 导出设置（不含密钥） downloads JSON with no API keys, 导入设置 reads one back; `curl http://127.0.0.1:8123/api/settings` contains no key values, and `ls -l config/ai_settings.json` shows `-rw-------` after a save.
- **Evidence:** 002 · TS port 013 WI-12 (PR #25)
- **Limits:** a stale tab can silently overwrite provider settings (#51, 018). The page's 重建全部索引 and 导出书库 JSON are stubs (see F-036, F-037).

#### F-036 Library JSON export — stub
- **What:** `/settings` → 导出与导入 has a 导出书库 JSON button; there is no export route, so it only shows a "not supported" line.
- **Code:** `frontend/src/settings/index.ts`, `src/reader3_app/web/templates/settings.html`
- **Tests:** `tests/e2e/shell_4a/test_settings_rows.py` (asserts 0 requests)
- **Confirm:** On `/settings` click 导出书库 JSON: the status line reads 「导出书库 JSON 暂不支持，服务端还没有这条导出接口。」, nothing downloads, and DevTools Network shows no request.
- **Evidence:** debt #53 · ruling D11 · baseline
- **Limits:** the export route is debt #53 (012-storage-format).

#### F-037 Bulk re-index all books — stub
- **What:** `/settings` → 数据 has 重建全部索引 with a confirm dialog; the confirm only prints a "not supported" line, because no bulk re-index route exists.
- **Code:** `frontend/src/settings/index.ts`, `src/reader3_app/web/templates/settings.html`
- **Tests:** `tests/e2e/shell_4a/test_settings_confirm.py` (asserts 0 requests)
- **Confirm:** On `/settings` click 重建全部索引 → dialog 「重建全部语义索引？」 → 重建索引: the status line reads 「批量重建索引暂不支持：请在终端对每本书运行 uv run reader3 --index <书目录>。」 and no request is sent.
- **Evidence:** debt #52 · ruling D11 · baseline
- **Limits:** the route is debt #52 (012-storage-format); per-book indexing works (F-002, F-008).

#### F-021 Light/dark theme (no FOUC) — accepted
- **What:** theme tokens and resolution with no flash of unstyled content.
- **Code:** `frontend/src/shared/`
- **Tests:** `tests/e2e/shell_4a/test_theme_resolution.py`, `tests/e2e/shell_4a/test_fouc.py`
- **Confirm:** On the library page click the top-bar `◐` (`lib-theme-toggle`): it cycles 跟随系统 → 浅色 → 深色 (its aria-label changes) and the chrome recolours; `/settings` → 外观 shows the same choice. Reloading a dark page shows no light flash.
- **Evidence:** 013 WI-10 (PR #25)
- **Limits:** chrome (`data-theme`) only; the reader's paper axis is F-031.

#### F-022 Degradation UI components — partial
- **What:** degrade banner, skeleton, and toast components (Track D).
- **Code:** `frontend/src/components/`
- **Tests:** `frontend/tests/components/`, `tests/e2e/shell_4a/test_toast.py`
- **Confirm:** On the library page, creating a collection shows a toast (F-006). When any book's index status is `stale`, the Search tab shows the banner 「索引已过期，结果可能不全」 with a 重建索引 button that re-indexes the stale books.
- **Evidence:** spec 010 · implementation 013 (PR #25)
- **Limits:** DEG-S3 / DEG-S4 have no backend data yet (#54/#55, 012).

### Security

#### F-023 Request origin guard — accepted
- **What:** host allowlist (`READER3_ALLOWED_HOSTS`), optional token (`READER3_TOKEN`), cross-site request guard.
- **Code:** `src/reader3_app/web/server.py` · ADR-0012
- **Tests:** `tests/unit/test_request_origin_guard.py`
- **Confirm:** `curl -i -H 'Host: evil.example' http://127.0.0.1:8123/api/health` → 400 "Invalid host header"; `curl -i -X POST -H 'Origin: https://evil.example' -H 'Content-Type: application/json' -d '{"name":"x"}' http://127.0.0.1:8123/api/collections` → 403 "Cross-site request rejected". Started with `READER3_TOKEN=secret`, `curl -i http://127.0.0.1:8123/api/settings` → 401 until `-H 'X-Reader3-Token: secret'` is added (`/api/health` stays open).
- **Evidence:** 008 · v1.5.0
- **Limits:** the browser UI does not send the token.

#### F-024 Provider egress single gate — accepted
- **What:** every outbound provider call passes through one HTTP gate.
- **Code:** `src/reader3_app/ai/providers/_http.py` · ADR-0006
- **Tests:** `tests/unit/test_server_egress_gate.py`
- **Confirm:** `curl -X POST http://127.0.0.1:8123/api/settings/providers/ollama/test -H 'Content-Type: application/json' -d '{"base_url":"file:///etc/passwd","api_key":"x"}'` returns `"success": false` with a message that scheme `file` is not allowed; the same call without `api_key` is refused with 400 before any request leaves.
- **Evidence:** baseline

#### F-025 Safe unpickling + path safety — accepted
- **What:** restricted unpickler for `book.pkl`; book IDs validated against enumerated folders; chapter path traversal blocked.
- **Code:** `src/reader3_app/safe_pickle.py`, `src/reader3_app/safe_paths.py` · ADR-0012
- **Tests:** `tests/unit/test_safe_pickle.py`, `tests/contract/test_read_chapter_traversal.py`
- **Confirm:** `curl -i http://127.0.0.1:8123/read/no_such_book_data/0` returns 404, as does any book id that is not an enumerated `*_data` folder under the books dir. The unpickler itself is only verifiable through `tests/unit/test_safe_pickle.py`.
- **Evidence:** baseline

#### F-026 Book UUID resolution — accepted
- **What:** `book_uuid` ↔ `book_folder` resolution; cached hits re-validated against `ai_meta.json`; an unreadable file degrades to `uuid=None`.
- **Code:** `src/reader3_app/ai/books.py` · ADR-0003
- **Tests:** `tests/unit/` (`test_book_uuid_*`)
- **Confirm:** `cat books/{book_id}/ai_meta.json` shows `{"book_uuid": "…"}`; `curl http://127.0.0.1:8123/api/ai/conversations/{that uuid}` returns 200 with a `conversations` list, and a made-up UUID returns 404 "Book not found".
- **Evidence:** PR #26 (`476f84d`)

### Infra

#### F-027 Server runtime options + health — accepted
- **What:** `reader3-server --port` / `READER3_PORT`, `READER3_BOOKS_DIR`, `GET /api/health`.
- **Routes:** `cli: reader3-server`, `GET /api/health`
- **Code:** `src/reader3_app/web/server.py`, `src/reader3_app/web/routers/health.py`
- **Tests:** `tests/unit/test_resolve_port.py`, `tests/contract/test_health_route.py`
- **Confirm:** `uv run reader3-server --port 9000` (or `READER3_PORT=9000 uv run reader3-server`) listens on 9000 and `curl http://127.0.0.1:9000/api/health` returns `{"status":"ok","version":"…"}`; `READER3_BOOKS_DIR=/other/books` makes the library list that folder instead.
- **Evidence:** v1.5.0
- **Limits:** `reader3-server` has no argument parser beyond `--port`: `--help` is ignored and starts the server.

#### F-028 Test net + CI — accepted
- **What:** unit + contract lanes, API route snapshot, coverage gate, e2e baseline, soak runner; mirrored in CI.
- **Code:** `.github/workflows/tests.yml`, `scripts/soak_run.py`, `.claude/tdd-guardian/config.json` · ADR-0010, ADR-0011
- **Tests:** `tests/contract/routes.snapshot`, `tests/contract/test_route_inventory.py`, `tests/e2e/baseline_1b/`
- **Confirm:** `uv run pytest tests/unit tests/contract` and `npm test` pass on a clean checkout; adding or renaming a route without editing `tests/contract/routes.snapshot` turns `tests/contract/test_route_inventory.py` red.
- **Evidence:** 008/009 · PR #19/#20

#### F-029 Repo lints — accepted
- **What:** testid naming, e2e selectors, token/hardcode, inline HTML, router-size gates.
- **Code:** `scripts/check_router_size.py`, `.github/workflows/lint.yml` · ADR-0013, ADR-0014
- **Tests:** `tests/e2e/test_testid_dom_uniqueness.py`
- **Confirm:** `python3 scripts/check_router_size.py`, `python3 scripts/lint_testid_naming.py` and `uv run ruff check src/ tests/ scripts/` exit 0 on `master`.
- **Evidence:** 007/013

#### F-030 Vite + TS frontend toolchain — accepted
- **What:** Vite + TypeScript + Vitest; built `static/dist` shipped inside the wheel.
- **Code:** `frontend/`, `src/reader3_app/web/vite_assets.py`
- **Tests:** `tests/integration/test_frontend_build.py`, `tests/integration/test_wheel_includes_dist.py`
- **Confirm:** `npm run build` typechecks and writes `src/reader3_app/web/static/dist/manifest.json` plus hashed assets; the library page's HTML then references those hashed `/static/dist/assets/*` files.
- **Evidence:** 013 WI-9 (PR #25)

#### F-041 Interactive API docs — unknown
- **What:** FastAPI's default Swagger UI, OAuth2 redirect, OpenAPI schema and ReDoc routes are served because the app is built with FastAPI defaults; nothing here tests their behaviour.
- **Routes:** `GET /docs`, `GET /docs/oauth2-redirect`, `GET /openapi.json`, `GET /redoc`
- **Code:** `src/reader3_app/web/server.py`
- **Tests:** `tests/contract/test_route_inventory.py` (route presence only)
- **Confirm:** Open `http://127.0.0.1:8123/docs` and `/redoc`: FastAPI's generated API pages load (their UI assets come from FastAPI's default CDN, so this needs network access); `curl http://127.0.0.1:8123/openapi.json` returns the schema.
- **Evidence:** 008 route snapshot · baseline
- **Limits:** with `READER3_TOKEN` set these pages need the token, which a browser cannot send (F-023).

## Audit log

### 2026-09-27 — Format extension + surface pass (`8e1cf48`)
- **Scope:** every row F-001..F-030 re-read against code, templates and `tests/contract/routes.snapshot` to fill the new `Routes` / `Confirm` / `Tracked` bullets; the `Limits` of every row plus the 009 debt table (#11, #21, #52, #53, #57, #58) and `spec-frontend-design.md` §D1 checked for surfaces with no behaviour. Added the `stub` / `absent` / `unknown` statuses and rows F-031..F-041.
- **Found:** F-017 claimed all-books / one-book / collection scope, but only single-book chat exists (`chat.ts` header; the other two buttons are disabled "Coming soon") — `What` corrected and F-039 split out; its status stays `accepted` for the single-book scope. #57, #52 and #53 were expected to be `absent` but each has a visible UI control (Add books, 重建全部索引, 导出书库 JSON), so they are `stub`. Two dead surfaces were not in any ledger row: the font-family picker (F-032) and 点评此书 (F-040). `reader3-server --help` starts the server (noted on F-027). F-010's `Code` pointed at `static/js/`, but the font-size wiring is an inline script in `reader.html`; the path was corrected.
- **Not audited:** `Confirm` steps were derived from code and templates, not executed in a running app (only `uv run reader3 --help` was run). Lanes and e2e were not run. Whether the AI 偏好 toggles (显示消息时间, 自动推荐问题, 检索 片段数 / 上下文窗口) change behaviour was not checked. F-041 behaviour (CDN assets, offline) and epub.js / ChromaDB behaviour beyond what the rows' tests cover were not checked.

### 2026-09-27 — Baseline seed (`8e1cf48`)
- **Scope:** rows F-001..F-030 seeded retroactively from code + tests at `8e1cf48`, statuses taken from plan write-backs and the 009 debt table.
- **Found:** —
- **Not audited:** not re-run as an acceptance pass: no lane, e2e or manual check was executed for this seed; rows marked `baseline` carry no PR evidence.

## Update checklist (after a module is accepted)

1. Gating lanes green on `master` (or on the merge commit), e2e rows named in `Tests` pass.
2. New capability → append a row to **Summary** with the next free `F-NNN`, and a section under its area.
   Change to an existing capability → edit that row/section only.
3. Fill `Code` / `Tests` with paths that exist, `Evidence` with PR # and/or SHA, and `Limits`
   with any open debt `#N` (link, don't restate).
4. Fill `Routes` (exact `routes.snapshot` lines / `cli:` names) and `Confirm` (a hand check
   against the running app or CLI, derived from the real UI); an `absent` row gets `Tracked`
   instead. A new route in the snapshot must be claimed by some row.
5. A debt that closes → remove it from `Limits`; if nothing is left, flip `partial` → `accepted`.
   A `stub` / `absent` that gets built → re-grade that row in place (same ID).
6. Retire, never delete: `deprecated` / `superseded → F-NNN` / `removed`.
7. When a pass re-grades rows, append an **Audit log** entry on top (Scope / Found / Not audited),
   and bump `**Synced:**` to a date no earlier than that entry's.
8. Bump the `**Synced:**` line (date + commit), then run `python3 scripts/build_feature_ledger.py`
   to regenerate the `ledger-data` block of `feature-ledger.html`; never edit that block by hand.
   CI fails on drift via `python3 scripts/build_feature_ledger.py --check`.
