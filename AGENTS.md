# Repository Guidelines

## Project Structure

- `src/reader3_app/reader3.py`: EPUB ingestion + conversion into `books/<book_id>_data/` (pickled `Book` in `book.pkl`, original `book.epub`, extracted `images/`).
- `src/reader3_app/web/server.py`: FastAPI app (library + reader UI, plus JSON APIs) on `http://127.0.0.1:8123`.
- `src/reader3_app/web/templates/`: Jinja2 templates (`library.html`, `reader.html`, `settings.html`).
- `src/reader3_app/web/static/`: UI assets (search, settings, AI assistant JS/CSS).
- `src/reader3_app/search_service.py`: Library + in-book search (query parsing, highlighting, API helpers).
- `src/reader3_app/vector_search.py`: Vector/RAG indexing and retrieval (ChromaDB).
- `src/reader3_app/notes_service.py`: Per-book notes/annotations persistence (`notes.json`) + helpers.
- `src/reader3_app/models/`: Shared dataclasses/models (e.g. annotations schema).
- `src/reader3_app/ai/`: AI assistant orchestration (providers, routing, RAG, disk conversations).
- `config/`: Runtime settings (notably `config/ai_settings.json` is gitignored; see `config/ai_settings.example.json`).
- `books/`: Local library root; processed books live in `books/<book_id>_data/` (may contain `book.pkl`, `book.epub`, `images/`, `ai_conversations/`, `chroma_db/`, `notes.json`).
- `docs/plans/{date}-{topic}/`: One self-contained body of planning work — plan, design spec, interface contracts, review record, work items. Two active efforts, two halves of one program: `docs/plans/20260816-tech-stack-migration/` (backend, test net, CI, **branch numbering**) and `docs/plans/20260817-frontend-ui-refactor/` (design system, degradation states, frontend TDD matrix). Start at either `README.md`. Their 「权威范围」 tables do not overlap — each fact is defined in exactly one of them.
- `specs/_archive/`: Historical spec-kit records for already-shipped features. **Frozen — the code is authoritative. Never implement from here.** See `specs/_archive/README.md`.
- `docs/`: Data locations, settings, and persistence details.
- Generated/ignored (see `.gitignore`): `books/*_data/`, `.venv/`, `conversations/`, and typically `*.epub`.

## Build, Test, and Development Commands

This repo uses `uv` for dependency management and execution.

- Install deps: `uv sync`
- Process a book (creates `books/<book>_data/`): `uv run reader3 path/to/book.epub`
- Index a processed book for vector/RAG search: `uv run reader3 --index <book_id>` (e.g. `dracula_data`)
- Run the web server: `uv run reader3-server`

If you need a clean re-process, delete the corresponding `books/*_data/` folder and rerun `reader3`.

You can override the default `books/` directory via `READER3_BOOKS_DIR`.

## Coding Style & Naming

- Python: 4-space indentation, keep functions small and readable, prefer explicit names over abbreviations.
- Types/data: extend the existing `@dataclass` models (`Book`, `ChapterContent`, `TOCEntry`) instead of introducing parallel structures.
- Files: keep modules focused (`reader3_app/reader3.py` for parsing, `reader3_app/web/server.py` for web). Template changes belong in `reader3_app/web/templates/`.

## 异常处理规则（三档）

三档规则的每一档都能被 ruff 二值判定——判定不了的规则是装饰，不是规则。配置在
`pyproject.toml` 的 `[tool.ruff]`，执行者是 `BLE001`（blind-except）与 `S110`（try-except-pass）。

**第 1 档 · 不许吞（默认）**
业务逻辑里异常一律向上传播，`except Exception` 禁止。判定：`BLE001`。
判断标准只有一句：**这个失败发生时，用户或运维需要知道吗？** 需要就不能吞。

**第 2 档 · 捕获并转译（仅边界层）**
只有三类边界可以捕获——HTTP handler、外部 API 调用、文件 I/O。且必须同时满足：

1. 捕获**具体的**异常类型（`OSError` / `ValueError` / `json.JSONDecodeError` / …），不是 `Exception`；
2. 转成对调用方有意义的错误——`HTTPException`，或一个明确的返回值；
3. **留下可观测痕迹**——log，或响应体里的 error 字段。

「捕获了但什么都没留下」等价于第 1 档的违规，哪怕它写在边界层。

**第 3 档 · 显式吞掉（例外，逐条说明）**
只有在「失败无所谓」且**能说出为什么无所谓**时才许可。必须写成
`# noqa: BLE001 - <理由>`，且至少 log 到 debug 级。裸 `except: pass` 一律禁止（`S110`）。

理由要真的是理由。「历史代码」不是理由；「这里失败只影响一次缓存预热，下次请求会重试」是理由。
写不出理由的地方，说明它其实该修。存量里这样的站点写成
`# noqa: BLE001 - FIXME(<分支号>): 无正当理由——<它错在哪>`，一句 `grep "FIXME(" src/`
就能把待办捞出来。**这类标记不是豁免，是欠条**：它标的地方 ruff 不再报，但它欠的债
记在那个分支名下。

**存量与新增**
008 分支立规则时全项目有 66 处 `except Exception`，本分支只修四处点名站点
（`_parse_summary_payload`、`api_ai_question` 的 `push` 闭包、`ai/books.ensure_book_uuid`、
`ai/conversations.list_conversations_combined`）。**剩下的存量用 `# noqa` 加理由逐条豁免，
随各自模块的重构分批清；新增代码不许豁免。** 一次性动全部 62 处会把「建安全网」变成
「大规模行为变更」，而安全网还没建好。

## API v1 冻结（008 起生效）

**`tests/contract/routes.snapshot` 是 v1 的定义处。** 它由 `app.routes` 生成，
`tests/contract/test_route_inventory.py` 拿运行时的路由集合与它比对。别处（文档、
计划、本文件）都不重复那份清单——重复的清单只会漂移，然后没人知道哪份是真的。

冻结的意义不在于「不许改」，在于**改了要有人知道**。Phase 4 的 TypeScript 前端
（013 / 014）是照着这份 v1 写的；前端重写期间后端 API 不动，两边才能并行推进而
不互相踩。一次没人注意到的路由改动，代价是前端在另一条分支上静默地对着不存在的
契约编码。

之后任何路由的增、删、改，两步都要做：

1. **先改快照**，并让改动出现在同一个 commit 里——快照变红说明「有人动了 API」，
   快照跟着代码一起改说明「这是故意的」。这一步的全部作用就是把前者变成后者；
2. **在 PR 描述里写明破坏性与迁移路径**，收件人是 013 / 014 那两条分支上的人。

> 快照测试比的是**集合**，不是数量。断言「有 43 条路由」的测试，在同一个 commit
> 里删一条加一条时会绿——那正是最需要被看见的一类改动。

## Testing Guidelines

**测试安全网建于 008 分支**（`docs/plans/20260816-tech-stack-migration/tasks/008-test-safety-net.md`）。
它不产出用户可见的变化，唯一的产出是「改坏了会有人告诉你」。

三条 lane 与它们的门禁时机、覆盖率阈值，**唯一定义处是 `.claude/tdd-guardian/config.json`**。
本文件不重述那些命令和数字——两份阈值只有一种结局。目录划分是：

| 目录 | lane | 大致内容 |
|---|---|---|
| `tests/unit` | unit | 纯函数、异常契约、fixture 自检 |
| `tests/contract` | unit | FastAPI `TestClient` 打真实路由树，三层路由契约 |
| `tests/integration` | packaging | 打 wheel、装进干净 venv、起真服务 |
| `tests/e2e` | e2e | Playwright（009 接手，现在是空的） |
| `tests/fixtures` | —— | 语料构造器，不含用例 |

CI 见 `.github/workflows/tests.yml`：**仅发版触发，且不设 required check**。日常门禁
在本地 tdd-guardian，代价写在那份任务书的 §7 里（`--no-verify` 绕得过；它从不在干净
环境里跑）。

**写测试时的判准只有一句：把被测代码改坏，这条测试会不会红？** 断言「函数被调用过」
的测试在重构把返回值丢掉之后依然是绿的；断言「那个值真的传到了响应体里」的不会。
前者是接线，不是测试。

> ⚠️ **测试永远不许指向真实的 `books/`。** `process_epub()` 会先对输出目录
> `shutil.rmtree()` 再写入——一次跑偏就抹掉用户真实的批注、AI 会话与向量索引。
> 一律用 `tmp_path`，并按 `tests/contract/conftest.py` 头部列的三处替换点隔离外部世界。

手动验证（改了 UI 或 EPUB 解析时仍然要做）：

1. Running `uv run reader3 <epub>` and confirming `books/*_data/book.pkl` and `books/*_data/images/` are created.
2. Running `uv run reader3-server` and exercising library + reader flows in the browser.
3. Using the acceptance criteria in the owning plan folder when implementing a planned feature: backend branches use `docs/plans/20260816-tech-stack-migration/tasks/{branch}.md`; frontend branches (010 / 013 / 014 / PWA) have **no task files** — their work items and acceptance criteria are the `### WI-N:` sections of `docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md`. Do not take acceptance criteria from `specs/_archive/` — those describe work that already shipped (or was abandoned).

## Commit & Pull Request Guidelines

Git history currently contains only `init commit`, so no strict convention exists. Use:

- Short, imperative commit messages (e.g., “Add in-book search UI”).
- One logical change per commit when possible.
- Prefer Conventional Commits (`feat:`, `fix:`, `chore:`, `test:`, `docs: ...`, `refactor: ...`); keep commits scoped and readable.
- Note which tests were run and call out follow-ups or known gaps.

For PRs: include a clear description, link the relevant plan/task document under `docs/plans/`, and add screenshots or Markdown diffs for UI/output changes.

## Security & Data Notes

- `book.pkl` is loaded via `pickle`; only process trusted EPUBs and avoid accepting untrusted uploads without hardening.
- Don’t commit generated `*_data/` outputs or large binaries unless explicitly intended.

## Documentation Rule (Technical Details)

- When adding/changing any “record-like” behavior (data storage locations, new persisted files/folders, new env vars, new endpoints that persist state), update the technical docs:
  - `docs/technical-detail.md`
  - and the relevant page(s) under `docs/`
