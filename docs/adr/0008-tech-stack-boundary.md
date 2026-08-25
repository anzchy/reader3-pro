# ADR-0008: 技术栈边界——后端留 Python，前端迁 TypeScript 但不引框架，桌面壳不做

| 字段 | 值 |
|---|---|
| Status | Accepted |
| Decision date | 2026-08-17 |
| Recorded date | 2026-08-25 |
| Record type | Prospective |
| Original rationale known | Yes |
| Confidence | High |
| Current compliance | Partial（后端 Full；前端 None——现状仍是 vanilla ES6 + 无模块系统 + 手工 vendor，013/014 迁移完成前不变，见 Migration Strategy） |
| Evidence | `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:48-57`（TL;DR 决策表与「三运行时架构」一句话结论）、`:614-647`（§10 决策依据）、`:651-657`（§11 明确不做的事）；`docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md:1939`（不引前端框架，原型 React 只是规格载体）；`designs/reader-pro-next/README.md:54-61`（「原型的性质」：可执行规格，不移植）；`pyproject.toml:1-16`（仅 Python 依赖：fastapi/chromadb/sentence-transformers/ebooklib，无 `package.json`）；`src/reader3_app/web/static/`（12 个 `.js` 文件全部 `window.*` 全局挂载，无 `import`/`export`；`vendor/epub.min.js` 225.7K ＋ `vendor/jszip.min.js` 95.3K 手工 vendor）；`docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md:152,546,1873`（`static/dist/` 提交进 git、不在 CI 现构建）；`src/reader3_app/web/server.py:287-295`（`READER3_LIBRARY_UI` 开关与 `library_classic.html` 回退）；`CLAUDE.md`「Frontend Development」小节（列出的静态资源仍是当前 vanilla 结构） |
| Confirmation | `scripts/lint_testid_naming.py`（testid 命名棘轮，013/014 迁移期间前后端 UI 并存时的唯一不变量，见 ADR-0013）；`tests/contract/routes.snapshot` ＋ `tests/contract/test_route_contracts.py`（路由/响应契约不因本决定改变的快照）；`scripts/check_wheel_contents.py`（wheel 内容对账，防止前端构建产物缺失或路径漂移） |

## Context and Problem Statement

007–015 这一整轮迁移开工前，必须先定死语言与框架边界，否则后续每个阶段（存储格式、CI、annotations.js 拆分）都可能被「要不要顺手换个语言/框架」的争论拖住。本决定回答三个独立但绑在一起问的问题：后端语言、前端语言与是否上框架、是否需要桌面壳。三者共享同一组证据（Python ML 生态强绑定、vanilla JS 的病灶、包体成本），拆成三份 ADR 会让读者反复核对同一批数字，所以合写一份。

- **Observed State**：后端 100% Python（`pyproject.toml`），前端 100% vanilla ES6（`static/` 下 12 个 `.js` 文件，无 `import`/`export`），无桌面壳代码。
- **Original Rationale**：见下方 Decision Drivers 与 Considered Options，出处是 `plan-tech-stack-migration.md` §10（Claude 全仓库分析 + Codex 独立推演交叉验证，`/plan-eng-review` 于 2026-08-18 复核通过，见该文档附录 A「APPROVE WITH CHANGES」结论，`:812`）。
- **Current Assessment**：后端结论至今未受挑战。前端结论尚未被 013/014 的实际实现验证——「TS + Vite 多页解决现有病灶」是一个预测，不是既成事实，故 Current compliance 记 Partial 而非 Full。

## Decision Drivers

- 核心价值链三个环节强绑定 Python 生态：语义嵌入（sentence-transformers 本地多语言模型）、向量库（ChromaDB `PersistentClient` 进程内嵌入式）、EPUB 解析（ebooklib + BeautifulSoup 的 spine/TOC 回退逻辑）。
- 现有 ~5,800 行 vanilla JS 的病灶（SSE 解析器重复两份、`escapeHtml()` 四处重复、`annotations.js` 1,127 行巨石文件）全部源于「无模块系统 + 无类型」，语言问题，不是框架问题。
- 现有 UI 不需要客户端路由或全局共享状态（`reader.html` 换章仍走整页导航），引入 SPA 框架的收益为零、代价是新增一整套心智模型。
- 本项目是自托管单用户工具，无桌面分发需求；Python 后端不会消失，桌面壳只能是「壳 + PyInstaller sidecar」，架构复杂度翻倍而非简化。
- 包体真实瓶颈是 Python ML 栈（本机 venv 实测 ~1.1GB，Torch 单项 368MB），不在壳的选择上——Tauri 的小壳省不掉这一块，也就抵消了它相对 Electron 的唯一优势。
- 已验证可复用的 Python 侧基础设施（原子写模式 `collections_service._atomic_write_json()`、`ai/books.ensure_book_uuid()`、路径安全校验 `_validate_book_id_path_safe()`）全栈重写会连带丢弃，重建它们本身就是 8–16 人周估算的一部分，不是外加成本。

## Considered Options

1. **后端留 Python 3.10+ / FastAPI / uv；前端迁严格 TypeScript + Vite 多页构建，不引框架；暂不做桌面壳**（选定）——构建产物仍是静态文件，`StaticFiles` 挂载方式不变，部署零改动。

2. **全栈 TypeScript 重写**——为什么不：估算 8–16 个全职工程周，且最终退化为「Node 编排 + Python worker」三运行时架构（ML/RAG 栈离不开 Python，Node 只能反过来调用 Python 子进程）。当前真正的问题——零测试、零 CI、pickle 序列化、三处重复的 loader/unpickler、2400 行 `server.py`——没有一个是换语言能解决的。核心价值链三个环节强绑定 Python 生态，逐环节的迁移代价：

   | 能力 | 现状 | TS 替代 | 迁移代价 |
   |---|---|---|---|
   | 语义嵌入 | sentence-transformers（本地多语言模型） | transformers.js（ONNX/WASM，性能与模型覆盖差一档；量化模型无法保证 embedding 一致，需全量重建索引） | 高 |
   | 向量库 | ChromaDB `PersistentClient`（进程内嵌入式） | Chroma JS SDK 仅为 HTTP client，必须外置 Chroma server；或换 LanceDB/sqlite-vec 重写 | 中-高 |
   | EPUB 解析 | ebooklib + BeautifulSoup（spine/TOC 回退/图片重写/文本抽取） | Node 库存在但整套摄取管线需带 fixture 语料做行为对等验证（EPUB2/3、CJK、畸形 TOC） | 高 |
   | 搜索偏移映射 | `search_service.py` 的 Unicode casefold + 仅限拉丁文的变音符剥离 + 偏移回映 | JS Unicode 细节差异会导致高亮/标注错位 | 中 |

3. **前端保持 vanilla JS，不做 TS 化**——为什么不：无模块系统 + 无类型是病灶本身，不是可以绕过的表象。

   - SSE 解析器在 `ai.js` 与 `library-chat.js` 复制两份。
   - `escapeHtml()` 在 ai.js / search.js / library-search.js / settings.js 四处重复。
   - IndexedDB 样板在 `ai.js` 与 `settings.js` 重复。
   - `annotations.js` 1,127 行巨石文件把 CFI 解析、文本锚定、工具栏 UI、笔记编辑器混在一起。
   - `pagination.js`（336 行）为死代码；`library.css`/`ai.css` 疑似孤儿文件；reader.html / library.html 各含 1,000+ 行内联 CSS。

   继续用 vanilla JS 等于放弃编译期检查这些重复与耦合的唯一低成本手段。

4. **引入 React/Vue/Svelte 等 SPA 框架**——为什么不：现有 UI 不需要客户端路由或全局 SPA 状态，TS 模块化能以小得多的架构扰动解决全部现存病灶；原型（`designs/reader-pro-next/`）虽然用 React 18 + 浏览器内 Babel 写成，但它是「可执行的规格」，用来验证交互、状态机与视觉，不是要移植的生产代码——生产实现按 TypeScript + Vite 多页构建，无框架。

5. **桌面化选 Tauri（而非 Electron）**——为什么不：epub.js 的 iframe 渲染、Selection API、CFI 标注对浏览器引擎高度敏感，Tauri 在 macOS/Linux 下用系统 WebKit 会把跨引擎差异打在阅读器最脆弱的部位（详见 ADR-0002 记录的 iframe 渲染边界）；Electron 统一 Chromium 是刚需（Codex 修正意见，已采纳）。且这一层选择目前不需要立即回答——近期用 `reader3 launch` 命令（起服务 → 健康检查 → 打开 PWA/Chrome `--app` 无边框窗口）零成本获得 90% 桌面感，桌面壳本身列为 Non-goal。

## Decision Outcome

| 维度 | 决策 |
|---|---|
| 后端 | 保留 Python 3.10+ / FastAPI / uv，不迁移 TypeScript/Node/Bun |
| 前端 | 迁移到严格 TypeScript + Vite 多页构建，不引入 SPA 框架或客户端路由 |
| 桌面化 | 暂不做 Electron 或 Tauri；用 `reader3 launch` + PWA/`--app` 窗口替代；将来若确有分发需求，只在 Electron 与 Tauri 之间选 Electron |
| 原型 | `designs/reader-pro-next/` 的 React 代码自始至终只是可执行规格，从未打算移植；013/014 按规格重写为无框架 TS |

**明确不做**：后端迁移 TypeScript/Node/Bun；引入 SPA 框架或客户端路由；现阶段做 Electron 或 Tauri；把原型 React 代码移植进生产。

## Consequences

### Positive
- 后端零改动即保住 Python ML 生态（sentence-transformers 本地嵌入、ChromaDB 进程内向量库、ebooklib EPUB 解析）的全部能力，不必为迁移承担对等验证成本。
- TS + ES modules + Vite 直接对症前端病灶（重复代码、无类型），构建产物仍是静态文件，`FastAPI StaticFiles` 挂载方式不变，部署零改动。
- 不引框架、不做桌面壳，省下两笔当前没有回报的投入（SPA 状态管理的学习/维护成本、桌面打包与跨引擎兼容性维护）。
- 决策边界一次性定死，Phase 1–5（`plan-tech-stack-migration.md` §6）的每个阶段不必反复重新论证语言/框架选型，只需引用本文。

### Negative
- 仓库长期维持两种语言两套工具链（Python `uv`/`pytest`/`ruff`/`mypy` 与 TS `Vite`/`tsc`/`vitest`），CI 与 lint 各自独立配置，没有共享的类型系统跨越前后端边界。
- 013/014 迁移期间新旧两套前端 UI 并存（vanilla JS 现状与 TS 新实现），期间行为一致性只靠 `data-testid` 命名棘轮兜底，一旦有人绕过命名规则改 testid，回归会在两套 UI 之间静默漂移（见 ADR-0013）。
- Python 的 ML 依赖（Torch 368MB，venv 实测 ~1.1GB）使任何桌面打包方案体积都偏大；这是拒绝立即做桌面壳的直接原因之一，但也意味着这笔成本被推迟而非消除——一旦确有分发需求，第一步就要面对这个数字。
- `READER3_LIBRARY_UI=classic` 环境变量开关（`server.py:287`）没有到期条件；013 删除 `library_classic.html` 时若忘记同步移除这个分支，会留下一个引用不存在模板的死开关。
- 「TS + Vite 解决前端病灶」这一半的结论尚未被生产实现验证——013/014 完成前，本文对前端部分的 Confidence 实质上依赖预测而非既成事实，一旦迁移中发现病灶未如预期收敛，需要回来修订本文而非默认它自证成立。

### Neutral
- 前端框架选型与桌面壳选型是两次独立的「不做」，共享同一条驱动（避免为不存在的需求预先付架构复杂度的税），但触发条件不同：框架的触发条件见 Revisit When 第二条，桌面壳的触发条件见第一、三条。
- `designs/reader-pro-next/` 的 React 原型代码本身不受本决定约束——它是规格文档的一部分，不是待迁移的生产代码，013/014 按 `designs/reader-pro-next/README.md`「原型 → 生产的翻译规则」转译，不做逐行迁移。
- 本文合并了三个原本可能拆成三份 ADR 的问题（后端语言、前端语言与框架、桌面壳）——三者共享同一批证据（Python 生态绑定、vanilla JS 病灶、包体成本），拆开会造成证据重复引用，故合写一份，是记录形式上的选择，不改变决策本身的独立性。

## Migration Strategy

现状（Observed State）：后端已是目标形态，Current compliance = Full，不需要迁移。前端仍是 vanilla ES6 + IIFE 全局挂载 + 手工 vendor（`epub.min.js`/`jszip.min.js`），无 `package.json`、无 TS 工具链，Current compliance = None。

目标形态由 013（TS shell + settings + library）→ 014（TS reader）两个分支分两步补齐，工作项定义在 `docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md` §4 的 WI-9 至 WI-19。构建产物固定落 `src/reader3_app/web/static/dist/` 并提交进 git（不在 CI 里现构建），`pyproject.toml` 的 `package-data` 需覆盖该目录的递归路径，由 `scripts/check_wheel_contents.py` 做机器确认。

每一步的棘轮（防止迁移期间行为悄悄漂移）：
1. **E2E 不变**——009 建立的 Playwright 用例覆盖读路径/写路径/K1–K6/DEG-S1–DEG-S4，013/014 期间必须保持绿。
2. **testid lint 不变**——`scripts/lint_testid_naming.py` 保证新旧两套 UI 共享同一套 `data-testid` 命名（ADR-0013），这是迁移期间唯一被允许依赖的跨实现不变量。

013 落地时，`READER3_LIBRARY_UI=classic` 开关与 `library_classic.html` 应随之删除（Consequences/Negative 第四条），否则这条 Migration Strategy 视为未完成。

## Revisit When

- Python ML 栈的打包体积问题被解决（例如出现可行的模型量化/裁剪方案，把 venv 体积压到桌面分发可接受的量级）——重新评估是否值得做 Electron 壳。
- 出现第二位常驻前端贡献者——「不引框架」的驱动之一是单人维护心智负担，多人协作下这个假设需要重新核算。
- FastAPI 或 uv 停止维护（无安全更新、无社区活跃度）——后端留 Python 的前提是这两个依赖健康。

## Related

- ADR-0002（epub.js iframe 渲染边界）——本决定选 Electron 而非 Tauri 的理由直接引用该 ADR 记录的 iframe/WebView 敏感性。
- ADR-0004、ADR-0013（编号预留于 `docs/adr/0000-use-adrs.md`「首批 0001–0013」，标注/CFI 与前端外壳相关的后续决定；本文撰写时二者尚未成文）——testid 命名棘轮是本文 Migration Strategy 的核心确认手段，其唯一定义处将落在 ADR-0013。
- 本文取代的原定义处：`docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md` §10「决策依据」（`:614-647`）与 §11「明确不做的事」中与语言/框架/桌面壳相关的三条（`:653-655`；`:656-657` 的 SQL 数据库、嵌入模型/向量库更换两条不属本文范围，仍留在原处）。两处已于 2026-08-26 改为指向本文的链接（§10 三个小标题保留以保住锚点）。
- `docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md:1939`（「引入前端框架」否决项）与 `designs/reader-pro-next/README.md:54-61`（原型性质）——原型/框架相关的论述保留在原处，本文只引用，不迁移，因为它们各自还承载迁移侧与设计侧的其他上下文。
