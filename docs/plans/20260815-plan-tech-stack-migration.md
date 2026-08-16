# Reader3 Pro 技术栈演进综合计划

- **日期**: 2026-08-15
- **状态**: 提议（待批准）
- **决策来源**: Claude（Fable 5）全仓库分析 + Codex（gpt-5.6-sol）独立推演，两方独立收敛于同一结论
- **Codex 会话**: `/cc-suite:continue 01a00400-4fa0-7d60-9cb9-4a82c843cf0f`（任务 `consult-mstytiy0-43aczt`）

> ### 权威范围
>
> **本文权威**：技术栈选型（§1/§2）、各阶段**做什么**（§3 的任务内容）、明确不做的事（§4）、风险（§5）、以及文末 GSTACK REVIEW REPORT 的 A1–A5 / B1–B4 / C1–C5 架构与性能决策。
>
> **本文不权威**：
> - **实施顺序、阶段划分、门槛、分支编号** → [`20260816-plan-ui-migration-sequencing.md`](./20260816-plan-ui-migration-sequencing.md)。本文正文按 Phase 组织只是为了归类任务，**顺序以合流计划为准**，冲突时以它为准。
> - **UI 设计、token、testid 命名、逐页规格、iframe 边界、降级状态** → [`20260815-spec-frontend-design.md`](./20260815-spec-frontend-design.md)。
> - **原型 → 生产的翻译规则** → [`designs/reader-pro-next/README.md`](../../designs/reader-pro-next/README.md)。
> - **标注宿主契约 K1–K6** → [`docs/contracts/annotation-host-contracts.md`](../contracts/annotation-host-contracts.md)。
> - **`annotations.js` 的模块划分** → [`specs/014-ts-frontend-reader/tasks.md`](../../specs/014-ts-frontend-reader/tasks.md)。
>
> 要改上面任何一项，改它的权威文档，不要在这里加一份副本。**本文不写代码行号**——行号会漂移，用符号名。

---

## 1. 最终决策（TL;DR）

| 维度 | 决策 |
|---|---|
| 后端 | **保留 Python 3.12 + FastAPI + uv**，不迁移 TypeScript |
| ML/RAG | 保留 sentence-transformers + 嵌入式 ChromaDB，改为可选依赖组 |
| 前端 | **迁移到严格 TypeScript + Vite 多页构建**，不引入 SPA 框架 |
| 存储 | 文件系统优先不变；**`book.pkl` → 版本化 JSON/JSONL 格式** |
| 测试 | pytest + Playwright（+ 后续 Vitest），GitHub Actions CI |
| 桌面化 | **暂不做 Electron/Tauri**；用 `reader3 launch` + PWA/app 窗口替代；将来确需分发时选 Electron（非 Tauri） |

> 一句话：语言不是瓶颈，工程化才是。全栈 TS 重写估算 8–16 全职工程周且最终退化为 "Node 编排 + Python worker" 三运行时架构；Electron 是在为不存在的分发需求付 500MB+ 的税。

> 📸 **现状证据**：[`designs/reader-pro-next/spec/screenshots/`](../../designs/reader-pro-next/spec/screenshots/) —— 22 张实测截图（2026-08-15），对应 `reader-pro-spec.md` §14。其中 §7.4b（端口硬编码）与 §7.4c（进度不一致）两条修订直接由这次复核发现。

## 2. 决策依据

### 2.1 为什么后端留在 Python

核心价值链三个环节 Python 生态强绑定：

| 能力 | 现状 | TS 替代 | 迁移代价 |
|---|---|---|---|
| 语义嵌入 | sentence-transformers（本地多语言模型） | transformers.js（ONNX/WASM，性能与模型覆盖差一档；量化模型无法保证 embedding 一致，需全量重建索引） | 高 |
| 向量库 | ChromaDB `PersistentClient`（进程内嵌入式，`vector_search.py`） | Chroma JS SDK 仅为 HTTP client，必须外置 Chroma server；或换 LanceDB/sqlite-vec 重写 | 中-高 |
| EPUB 解析 | ebooklib + BeautifulSoup（spine/TOC 回退/图片重写/文本抽取，`reader3.py`） | Node 库存在但整套摄取管线需带 fixture 语料做行为对等验证（EPUB2/3、CJK、畸形 TOC） | 高 |
| 搜索偏移映射 | `search_service.py` 的 Unicode casefold + 仅限拉丁文的变音符剥离 + 偏移回映 | JS Unicode 细节差异会导致高亮/标注错位 | 中 |

当前真正的问题（零测试、零 CI、pickle 序列化、三处重复的 loader/unpickler、2400 行 server.py）**没有一个是换语言能解决的**。

### 2.2 为什么前端迁 TypeScript

现有 ~5,800 行 vanilla JS 的病灶全部源于"无模块系统 + 无类型"：

- SSE 解析器在 `ai.js` 与 `library-chat.js` 复制两份
- `escapeHtml()` 四处重复（ai.js / search.js / library-search.js / settings.js）
- IndexedDB 样板在 `ai.js` 与 `settings.js` 重复
- `annotations.js` 1,127 行巨石文件（CFI 解析 + 文本锚定 + 工具栏 UI + 笔记编辑器混杂）
- `pagination.js`（336 行）为死代码；`library.css`/`ai.css` 疑似孤儿文件
- reader.html / library.html 各含 1,000+ 行内联 CSS

TS + ES modules + Vite 正好对症；构建产物仍是静态文件，FastAPI `StaticFiles` 挂载方式不变，部署零改动。

### 2.3 为什么暂不做 Electron/Tauri

- 本项目是自托管单用户工具，无分发需求；Python 后端无法消失，只能 PyInstaller sidecar，架构复杂度翻倍。
- 包体瓶颈在 Python ML 栈（本机 venv 实测 ~1.1GB，Torch 单项 368MB），不在壳；Tauri 的小壳省不掉这块。
- **将来若确需桌面分发，选 Electron 而非 Tauri**（Codex 修正意见，已采纳）：epub.js 的 iframe 渲染、Selection API、CFI 标注对浏览器引擎高度敏感，Tauri 在 macOS/Linux 用 WebKit 会把跨引擎差异打在阅读器最脆弱的部位；Electron 统一 Chromium 是刚需。
- 近期体验替代方案：`reader3 launch` 命令（起服务 → 健康检查 → 打开 PWA/Chrome `--app` 无边框窗口），零成本获得 90% 桌面感。

## 3. 分阶段实施计划

> 阶段的**先后关系、门槛与分支编号**见合流计划 §6–§9。本节只写每个阶段**做什么**。

### Phase 0 — 合同与止血

评审补入的两个 P0 与三项便宜但会阻塞后面的前置工作。每项独立 PR。

- [ ] **P0-1**：`process_epub()` 里的 `shutil.rmtree(output_dir)` 会连同 `notes.json` 一起删除——改为写 staging 目录 + 校验 + 原子切换
- [ ] **P0-2**：`pyproject.toml` 的 `"static/*"` 非递归，打出的 wheel 缺 `static/js` / `static/css` / vendor
- [ ] **端口可配置**：`run_server()` 硬编码 `port=8123`，无 env / CLI 覆盖。加 `READER3_PORT` env + `--port` CLI（CLI 优先）。这在截图复核中已造成实际阻塞：为采集 classic UI 必须绕过 `reader3-server` 入口直接调 uvicorn。对 Phase 1b 的影响更直接——Playwright 要起自己的实例，固定端口会与开发者本地的 8123 冲突，CI 并发跑也会抢端口
- [ ] **新增 `GET /api/health`**：Phase 1b 的 Playwright `webServer` 需要就绪探针，没有它只能轮询 HTML 页面，慢且易误判。两行代码，放在这里最省事（Phase 5 的 `reader3 launch` 直接复用）
- [ ] **四个落后 JS 文件 IIFE 化**（`search.js` / `ai.js` / `settings.js` / `library-search.js`），`escapeHtml` 全局覆盖修正——见 B1
- [ ] **`data-testid` 全量补齐**，命名与前缀方案见设计规格 §4，改名顺序「先原型、后模板」见合流计划 §4.1。规则写入 CI lint：**E2E 只允许 `data-testid` 与 ARIA role/name**，禁止 class 选择器、`nth-child`、层级结构选择器。契约是「重设计可任意改 class / 嵌套 / 标签，**不得改 testid**」
- [ ] 事实性修复：`.gitignore` 末尾遗留的 merge 冲突标记、`pyproject.toml` 版本号对齐 git tag、`ai_settings.example.json` 补齐 openai / openrouter provider
- [ ] **删除死代码** `SearchIndex` / `BookIndex.from_book_pkl` / `SearchIndex.build_from_library`（零调用方，且是 A5 里那个带裸 `pickle.load` 的「第四处」）——先删再谈合并，否则 `book_store.py` 会把一个静默失败分支收编成现役设计。**只删这两个符号，`BookIndex` / `ChapterIndex` dataclass 是活的**

**验收**: 两个 P0 修复并人工 smoke；`--port` 与 `/api/health` 可用；testid 在原型与模板两侧一致且 lint 生效。

> testid 必须早于 Phase 1b 动笔。本计划已把「Phase 1b 的标注 E2E 在主 CI 绿灯」写为 Phase 4 的前置条件，却没有规定 E2E 用什么定位元素；若用 class 或结构选择器，Phase 4 的任何布局改动都会推翻整套 E2E。这是全篇最便宜也最容易漏的一条。

### Phase 1 — 建立安全网（最高优先级，其他阶段的前置条件）

任何迁移动作之前先做。没有特征化测试，迁移成本"不可知"。

- [ ] 引入 pytest + dev 依赖组（`uv add --dev pytest ruff mypy`）
- [ ] 单测覆盖：EPUB 摄取（`process_epub`）、JSON 持久化（notes/collections/conversations）、Unicode 搜索偏移映射（`_normalize_with_map`）、AI 路由（`choose_routing`/`estimate_tokens`）、API 契约（FastAPI TestClient）
- [ ] Fixture EPUB 语料：EPUB2 / EPUB3 / CJK 内容 / 变音符 / 含图片 / 畸形或缺失 TOC / 空书
- [ ] Playwright E2E（= Phase 1b）：书库导航、epub.js 渲染、iframe 内标注**创建与恢复**、AI SSE 流式。**完整用例清单见 [`specs/009-e2e-annotations/tasks.md`](../../specs/009-e2e-annotations/tasks.md)**——含写路径（四类型创建 / 改色 / 删除 / 笔记保存）、K1–K6 与 S1–S4 的正向证据，以及「断言刷新后高亮回到同一段文字」这条统一收尾
- [ ] ruff + mypy 配置写入 `pyproject.toml`
- [ ] GitHub Actions：lint + type-check + pytest（Playwright 可 nightly）

**验收**: CI 绿灯成为合并门槛；核心路径（摄取/搜索/笔记/路由）有回归保护。

### Phase 2 — Python 内部重构（不改行为）

- [ ] `web/server.py`（~2,400 行）拆分为 FastAPI routers 六组：
  - `routers/library.py`（library + collections + stats）
  - `routers/reader.py`（阅读页 + book.epub + 图片资源）
  - `routers/notes.py`
  - `routers/search.py`（搜索 + 语义索引）
  - `routers/ai.py`（对话 + RAG + 摘要 + 问答）
  - `routers/settings.py`
- [ ] 新建共享 `book_store.py`：合并 `server.py` / `search_service.py` / `vector_search.py` 三处重复的 `_Reader3Unpickler` 与 `lru_cache` loader（消除同一本书 3 份内存缓存与漂移风险）。粒度接口与「为什么是三处不是四处」见 A5
- [ ] chromadb + sentence-transformers 移入可选依赖组 `[project.optional-dependencies] semantic`（与 README"语义依赖可选"的描述对齐）
- [ ] 修复 `ai/config.py` 设置写入改为原子替换（`.tmp` + `os.replace`，与 notes/collections 一致）
- [ ] **notes 乐观并发控制**：notes 是 load→modify→save 全覆盖，`os.replace` 只保证单次写入原子，不防两个并发请求互相覆盖——自托管单用户开两个标签页即可触发。加 revision/ETag（或 per-file lock），冲突时返回 409 而非静默丢写。前端侧的冲突 UI 是设计规格 §6.4 的 **S5**
- [ ] 修复事实性问题：
  - `pyproject.toml` 版本 0.1.0 → 与 git tag v1.4.0 对齐
  - `.gitignore` 末尾遗留的 merge 冲突标记（`<<<<<<< Updated upstream`）
  - `ai_settings.example.json` 补齐 openai / openrouter provider
  - 删除或接通从未被使用的 `max_retries` 配置项
- [ ] 路由启发式修正：`estimate_tokens()` 对 CJK 按 ~1.5 字符/token 估算；Anthropic 默认上下文窗口 1M → 200k
- [ ] 修订 `CLAUDE.md` § Constitution Principles（原 `.specify/memory/constitution.md` 已随 spec-kit 工具链于 2026-08-16 删除，CLAUDE.md 的摘要版成为唯一权威）：保留简单性原则，修订已过时的实现禁令（"除 FastAPI/BeautifulSoup 外不加抽象"已不能描述含 Chroma、5 provider、异步队列、42 路由的系统）；"测试可选"条款删除

**验收**: Phase 1 测试全绿（行为不变的证明）；`server.py` 每个 router < 500 行。

### Phase 3 — 存储去 pickle 化

pickle 是实际的迁移阻塞点与安全隐患（`pickle.load` 对不可信输入等于任意代码执行；现有 `_Reader3Unpickler` 只是兼容 shim，非受限反序列化器）。

- [ ] 设计版本化中立格式：
  ```
  books/{book_id}_data/
  ├── manifest.json      # 元数据 + 格式版本 + spine/TOC 结构
  ├── chapters.jsonl     # 每行一章：{id, href, title, content, text, order}
  ├── book.epub
  ├── images/
  ├── notes.json
  ├── ai_meta.json
  └── chroma_db/
  ```
- [ ] 摄取时双写（新格式 + book.pkl）；读取优先新格式，pkl 的地位见下方「读取状态机」
- [ ] `book_store.py` 封装格式判断，调用方无感知
- [ ] **落地下方的「两文件提交协议」与「读取状态机」**——`manifest.json` + `chapters.jsonl` 是一次**两文件提交**，没有协议就会出现 manifest 指向半写 chapters 的状态
- [ ] 提供 `reader3 --migrate <book_id>` 将存量书库转换为新格式。
      **硬约束：`--migrate` 原地读写，禁止复用摄取路径。** 摄取路径在写入任何内容前 `shutil.rmtree(output_dir)`（见 A1），而 `notes.json` / `ai_meta.json` / `chroma_db/` 全在 `output_dir` 里——`--migrate` 一旦借道摄取，就会在"迁移成功"的同时抹掉用户标注、AI 会话与向量索引。实现上 `--migrate` 只允许：读 `book.pkl`（或 `book.epub`）→ 写 `manifest.json` + `chapters.jsonl` → 校验 → 结束，全程不删任何既有文件
- [ ] 稳定一个大版本后移除 pickle 写入路径
- [ ] **降级状态在 UI 里可见**：A1 的分级降级（notes stale / 索引 stale）与 A2 的 pickle 回退告警一旦无 UI，就是静默的用户数据损坏。设计规格 §6.4 的 **S1–S4** 必须在本阶段可见——哪怕先落成现有 Jinja 模板里的朴素横幅，Phase 4 再按规格重做

#### 两文件提交协议（canonical，全仓库唯一定义处）

> **本小节是 `manifest.json` + `chapters.jsonl` 写入顺序的唯一定义处。** 合流计划 §4 的回滚条目、A2 的 pickle 回退条款只引用本小节，不复述步骤。

把一本书的存储从一个文件（`book.pkl`）拆成两个，就引入了一个 pickle 时代不存在的失败态：**manifest 已落盘、chapters 只写了一半**。此时 `manifest.json` 里的 `offset_bytes` / `length_bytes` 指向文件尾之后，`load_chapter()` seek 过去读到的是截断数据或空串——而 `manifest.json` 本身格式完好，任何「文件在不在 / JSON 解不解得开」的检查都会判它健康。摄取、`--migrate`、未来任何重写存储的路径都必须走同一套顺序：

1. 写 `chapters.jsonl.tmp`（同目录，保证与目标同一文件系统，`os.replace` 才是原子的）
2. `f.flush()` + `os.fsync(f.fileno())` — 数据落到盘，不只是落到 page cache
3. 边写边记录每章的 `offset_bytes` / `length_bytes` / 内容 hash；写完再记全文件 `size_bytes` 与 `sha256`
4. 写 `manifest.json.tmp`，把第 3 步的全部数字嵌进去
5. `flush()` + `fsync()` manifest.tmp
6. **在任何 `os.replace` 之前**做一次全量回读校验：按 manifest 里的 offset 逐章 seek `chapters.jsonl.tmp`，每章 JSON 解得开、`id`/`order` 对得上、hash 相符。校验失败就删两个 tmp 文件退出，目录里的旧状态一个字节没动
7. `os.replace("chapters.jsonl.tmp", "chapters.jsonl")` → `os.fsync(dirfd)`
8. `os.replace("manifest.json.tmp", "manifest.json")` → `os.fsync(dirfd)` — **manifest 是 commit marker，必须最后一个换**

顺序的全部意义在第 7、8 步：chapters 先就位、manifest 后就位，于是"manifest 指向半写文件"在任何时刻的崩溃点上都不可能出现。反过来的残留是良性的——只有 `chapters.jsonl` 没有 `manifest.json`，读取状态机判定为 `missing`，走旧格式；孤儿 tmp 文件下次运行覆盖即可。

#### 读取状态机（三态，禁止二态）

`storage_format(book_id)` 不能只回答"新格式还是旧格式"，因为那把"没迁移"和"迁移坏了"归成了同一件事：

| 状态 | 判定 | 处置 |
|---|---|---|
| `missing` | `manifest.json` 不存在 | 读 `book.pkl`。这是双写期与未迁移存量书的**正常**状态，不告警 |
| `corrupt` | manifest 存在，但 JSON 解不开 / 格式版本不认识 / `sha256` 或 `size_bytes` 与 `chapters.jsonl` 对不上 | **大声失败**：抛错、写日志、UI 出 S1–S4 横幅。**不静默回退 pkl** |
| `valid` | manifest 存在且自洽 | 读新格式 |

`corrupt` 之所以不回退，是因为上面的提交协议已经排掉了"写坏"这条路径——协议走完还 corrupt，意味着磁盘损坏、外部程序改文件、或者协议本身有 bug。这三种都需要人看见。静默回退 pkl 只会把它们藏到 pkl 也被删掉的那一天。

这同时消掉了 A2 与本阶段的一处表面矛盾：A2 说 pickle 回退"默认关闭，需显式 `READER3_ALLOW_PICKLE=1`"，本阶段又说"读取优先新格式，回退 pkl"。两句话说的不是同一个时间窗——

- **双写期**（移除 pkl 写入路径之前）：pkl 是与新格式**同期产出的对等产物**，不是遗留数据。`missing` 走 pkl 属正常流程，**不需要环境变量**。
- **停写 pkl 之后**：目录里还剩的 pkl 才是真正的遗留数据，`missing` 走 pkl 才需要 `READER3_ALLOW_PICKLE=1` 显式开启并每次启动告警。

**`--migrate` 不得改变 `book_fingerprint()`。** A1 的指纹涵盖原 EPUB hash、spine href/order、每个 XHTML 原始内容 hash、解析器版本——纯粹的存储格式转换一样都不碰。若迁移后指纹变了，A1 的分级降级会立刻生效，**全库用户标注一次性判 stale**。因此 Phase 3 的验收里那条"`notes.json` 三者字节不变"的测试要再加一句断言：迁移前后 `book_fingerprint(book_id)` 相等。

**进入条件**: Phase 2b 完成 **且** 1b 的标注 E2E 在主 CI 连绿 ≥10 次、跨度 ≥5 个工作日（soak 门槛，见合流计划 §7）。

**验收**: 新处理的书完全不依赖 pickle 即可阅读/搜索/标注；存量书可一键迁移；**`--migrate` 原地读写，有一条测试证明迁移后 `notes.json` / `ai_meta.json` / `chroma_db/` 三者字节不变、且 `book_fingerprint(book_id)` 不变**；**有一条崩溃注入测试**：在提交协议第 7 步之后、第 8 步之前中断，重启后该书仍能正常打开（状态判为 `missing`，走 pkl），且下一次迁移能干净地重跑；S1–S4 在当时的 UI 里可见；**并跑至少一条真实 iframe 标注迁移 E2E**（理由见下文「最可能的失败模式」）。

### Phase 4 — 前端 TypeScript 化（增量，非大爆炸）

> **两个前提**：(1) 本阶段与前端重设计是**同一块地**，CSS 与 markup 一次到位，不做两遍；(2) 阶段拆为 4A（底座 + 非阅读页）与 4B（阅读器），拆法与顺序见合流计划 §6。**Phase 3 必须早于 4B**。
>
> 计划原文隐含假设「UI 是完好的，只需 TS 化」——**该假设不成立**。`#font-settings-popup` 里 12 个控件（主题 ×4、字号 ±、行距 ±、字体 ×4）全部没有事件处理器，字号显示恒为 `17`、行距恒为 `1.9`；全仓库 `*.css` 对 `prefers-color-scheme` / `data-theme` 零命中，「夜间」主题没有可切换的对象。因此 Phase 4 除 TS 化之外还含**新功能**（阅读设置面板）。

**工具链与底座**

- [ ] 引入 Node LTS + `package.json` + Vite + 严格 `tsconfig`（`strict: true`），仅作为构建期工具
- [ ] Vite 多页构建：`library` / `reader` / `settings` 三入口；产物输出到 `static/dist/`，Jinja 模板只换 `<script>` 引用
- [ ] epub.js / JSZip 从 vendored 改为 npm 依赖（版本可追踪）
- [ ] 双层 token 落地 + `data-theme` 主题基础设施 + `<head>` 内嵌同步 inline script 读 `localStorage` 并 stamp 主题，避免首屏闪白。现有 `--dedao-*` 降级为弃用别名，Phase 4 结束时删除
- [ ] 共享模块：`api.ts`（fetch 封装 + 错误处理）、`sse.ts`（统一 SSE 解析器）、`escape.ts`、`idb.ts`（IndexedDB 封装）、`debug.ts`、`messages.ts`
- [ ] 建立 `en` / `zh-CN` 类型化消息表（简单 TS 对象即可，无需 i18n 框架），替代硬编码中英混排。**英文为默认 locale**（决策 D-2）；消息表用于收敛现有中英混排，而非立刻交付双语

**逐页垂直切片**（由低风险到高风险；每页一个 PR 含 markup + TS + CSS）

- [ ] `settings` 页 —— 试点，无 JS 耦合，用来验证工具链与 testid 不变量
- [ ] `library` 页（含 `library-search` / `library-chat`，chat 复用共享 `sse.ts` 消灭复制）**＋ 删除 Classic Library**：删除 `library_classic.html`、`READER3_LIBRARY_UI=classic` 分支及其未初始化的搜索表单（决策 D-4）
- [ ] reader 面板类：`toolbar` / `toc-panel` / `notes-panel` / `search`
- [ ] **最后**：`annotations.js` 与 `epub-renderer.js` 桥接层

**`annotations.js` 的拆分**

先纯拆分不改逻辑，再逐个转 TS（B3）。⚠️ 原文写的 `anchoring` / `renderer` / `ui` 三分法**在代码面前不成立**——`getReaderContext()` 与四处 `/api/notes` 的 `fetch` 横跨 `AnnotationRenderer` 与 `AnnotationUI` 两个类，无法归入任何一边；且 `AnnotationUI` 单类就超过 ≤400 行上限。**实际划分见 [`specs/014-ts-frontend-reader/tasks.md`](../../specs/014-ts-frontend-reader/tasks.md)**，外壳与标注之间的六份契约见 [`annotation-host-contracts.md`](../contracts/annotation-host-contracts.md)。

**阅读设置面板（新增功能）**

- [ ] 四主题 × 字体 × 字号 × 行距，统一 `data-reading-theme` 契约：同时驱动 app chrome（semantic token）与 iframe 正文（epub.js `themes.override`）。**注入 iframe 的 CSS 属性范围以设计规格 §6.0「判定标准（canonical）」为准**——判据是**三重断言 A/B/C**（文本序列 ＋ body 结构签名 ＋ CFI 往返），本文不复述；`max-width` / `margin` / `text-align` / `font-size` / `line-height` 均在允许之列
- [ ] 删除三款未授权且未打包的商业中文字体选项

**行为变更（不得混入设计工作）**

- [ ] **阅读进度单一数据源**：实测同屏出现两个矛盾进度值（Notes 面板「已读到 26%」vs 页脚「当前阅读至 20%」），且打开纯封面 spine 0 时页脚显示「当前阅读至 100%」。收敛为单一数据源（epub.js location 计算），页脚 / Notes 面板 / 书库卡片读同一个值，封面等非正文 spine 项不计入分母

**清理**

- [ ] 删除死代码：`js/pagination.js`、reader.html 中 `.book-content` 遗留 CSS、确认后删除孤儿 `library.css` / `ai.css`
- [ ] 内联 CSS **按设计规格重写**（不是机械外移）：`library.html` 1075 行 + `reader.html` 1403 行内联 CSS 在重设计中本就要重写，先外移再重写等于做两遍。把 CSS 提取当作重设计的**产物**，不是它前面的独立任务
- [ ] 清理 `annotations.js` 33 处 + `epub-renderer.js` 9 处 `console.log`，换成 `debug.ts` 分层
- [ ] （可选）Vitest 覆盖共享模块与锚定逻辑

**范围边界**：`reader.html` 的重设计**只覆盖外壳**（工具栏 / TOC / 笔记 / 搜索 / AI / 标注工具条 / 章节导航），**绝不触碰 epub.js iframe 内部 DOM**。理由与下文「最可能的失败模式」一致。完整判据见设计规格 §6.0。

**明确不做**: 不引入 React/Vue/Svelte——现有 UI 不需要客户端路由或全局 SPA 状态，TS 模块以小得多的架构扰动解决全部现存问题。

**验收**: 无重复工具函数；`annotations` 拆为 ≤400 行的模块；每页切换后 E2E **零改动**全绿；Playwright 全绿。

### Phase 5 — 启动体验与（远期）桌面化

- [ ] 新增 `reader3 launch` 命令：起 FastAPI → 轮询健康检查 → 打开 PWA / Chrome `--app=http://127.0.0.1:8123` 窗口 / 默认浏览器 → 启动失败清晰报错（含端口冲突处理）
- [ ] 添加 PWA manifest + service worker（可安装、独立窗口）
- [ ] **仅当**确证有非技术用户需要安装包时：单平台 Electron PoC——PyInstaller Python sidecar、首次使用语义搜索时下载模型（不打包数百 MB 模型）、OS 应用数据目录（弃用仓库相对路径）、sidecar 生命周期/崩溃恢复、签名与公证

**验收**: 双击/单命令即可进入阅读，无需手动起服务开浏览器。

## 4. 明确不做的事（Non-goals）

- ❌ 后端迁移 TypeScript / Node / Bun（8–16 全职工程周，收益为零，架构更复杂）
- ❌ 现阶段 Electron 或 Tauri（无分发需求；若未来需要，选 Electron 保 Chromium 一致性）
- ❌ 引入 SPA 框架或客户端路由
- ❌ 引入 SQL 数据库（文件系统即数据库的宪法原则保留）
- ❌ 更换嵌入模型或向量库（改动即全量重建索引 + 检索质量对等验证，无收益不动）

## 5. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 迁移引入回归（尤其标注锚定与搜索高亮） | Phase 1 安全网先行；`annotations.js` 放在最后迁移 |
| 存量书库 pkl 不兼容 | 双写 + 回退读取 + `--migrate` 命令，跨版本过渡 |
| Vite 构建破坏"无构建即改即用"的开发体验 | `vite dev` 提供 HMR，比现状更好；产物提交策略可选（提交 dist 或 CI 构建） |
| 单人维护者时间碎片化 | 每 Phase 独立可交付、可暂停；Phase 之间无硬耦合（仅 Phase 1 是全局前置） |
| Chroma 相似度换算假设（`1 − L2` clamp）与实际距离度量不符 | Phase 1 补一条针对已知语料的检索质量测试固化现状 |

## 6. 里程碑与分支

见合流计划 [`20260816-plan-ui-migration-sequencing.md`](./20260816-plan-ui-migration-sequencing.md) **§9**，它是分支编号的唯一真相源。

> 本节此前列过一份 `007-test-safety-net` … `011-launch-experience` 的编号表，与合流计划 §9 的编号**冲突**（同一个编号指向不同工作）。已删除，避免两套编号并存。

---

*本计划由两次独立分析（Claude 三路并行子代理全仓库勘察 + Codex 只读仓库推演）交叉验证后综合而成；分歧点（Tauri vs Electron）已按更强论证方（Codex）修正。*

## GSTACK REVIEW REPORT

| Runs | Status | Findings |
|---|---|---|
| plan-eng-review · 2026-08-15 · master · Opus 5 + codex-cli 0.145.0 | DONE_WITH_CONCERNS | 2 × P0 · 8 × P1 · 9 × P2 · 2 × P3 |

> ⚠️ 本报告内的**代码行号是 2026-08-15 的快照**，2026-08-16 复核时已有多处漂移。行号只作为当时的证据留档，不要按它跳转——用符号名。此后新增的文档一律不写行号。

### 计划本身的事实性错误（已核实）

| 计划所述 | 实际 |
|---|---|
| Python 3.12（CLAUDE.md 同误） | `pyproject.toml:6` 为 `>=3.10`，本地 venv 亦为 3.10。CI 主矩阵须用 3.10 |
| 重复 loader「三处」 | 审查时为**四处**——漏了 `search_service.py` 里 `BookIndex.from_book_pkl` 的裸 `pickle.load`。该处已于 2026-08-16 作为死代码删除，**「三处」现在是对的**（见 A5） |

计划其余的事实主张全部核实通过：`server.py` 2412 行 / 42 路由、`escapeHtml` 四份副本、SSE 解析器与 IndexedDB 样板重复、`js/pagination.js` 336 行零模板引用、`library.css`/`ai.css` 孤儿、`annotations.js` 1127 行 / 33 处 `console.log`、`.gitignore` 冲突标记未解、`ai_settings.example.json` 缺 openai/openrouter、`max_retries` 全链路未消费、`provider_context_window()` 的 Anthropic 默认窗口 1M、零测试零 CI。

### 🔴 P0 — 计划完全未提及，且是今天就存在的损坏

**P0-1 数据丢失：重新处理一本书会静默删光该书全部用户标注。**
`reader3.py` 的 `process_epub()` 在写入任何内容前 `shutil.rmtree(output_dir)`，而 `output_dir` 即 `books/{name}_data/`，`notes.json` / `ai_meta.json` / `chroma_db/` 均在其中。无警告、无备份。叠加缓存不失效（三处 `lru_cache` 的 key 均不含 mtime），服务器还会继续供着旧 `Book`。
→ 改为 staging 目录 + 完整校验 + 原子切换，manifest 作为 commit marker（步骤见 Phase 3 的「两文件提交协议」——那是唯一定义处，Phase 0 先按同一顺序落 staging 切换）。**列入 Phase 0。**

**P0-2 发布损坏：打出的 wheel 阅读器不可用。**
`pyproject.toml:34` 的 `"static/*"` 是 setuptools 非递归 glob，`static/js/`、`static/css/`、`static/vendor/` 三个子目录均未打包——`epub.min.js`、`annotations.js`、`reader.css` 全部缺失。本地 `uv run` 走源码树因而不可见。
→ 必须先于 Phase 4「dist 提交进 git」修复，否则 dist 提交了也发不出去。

### 阶段重排（原 5 阶段 → 8 阶段）

```
Phase 0  卫生 + P0（独立 commit + 六项人工 smoke checklist，当天合入）
   ↓
Phase 1a Python 单测 + 42 路由契约 + CI + 异常处理三级规则 + 迁移基准   ← 全局阻塞
   ↓
Phase 1b Playwright E2E（含 iframe 标注）                              ← 仅阻塞 Phase 4
   ↓
Phase 2a router 拆分 + book_store（含粒度接口）纯重构
   ↓
Phase 2b 跨库搜索性能（新增）
   ↓
Phase 3  事务化 JSONL 迁移 + 指纹 + Chroma generation swap
   ↓
Phase 4  前端 TS（5a 拆分 / 5b 转换，两个 PR）
   ↓
Phase 5  launch + PWA
```

Phase 1b 从 Phase 1 中拆出并降级为「仅阻塞 Phase 4」，使 Phase 2/3 不被 E2E 拖住；同时 Phase 4 的前置条件明确写为「1b 的标注 E2E 必须在**主 CI** 里绿灯，不得放在 nightly」。

### 架构决策（A1–A5）

- **A1 隐式契约显式化**：`manifest.json` 记录 `spine_fingerprint`。指纹须涵盖原 EPUB hash、spine href/order、每个 XHTML 的**原始内容** hash 与解析器版本——只 hash `chapter.text`（`extract_plain_text()` 的空白折叠产物）检测不到影响 CFI 的 HTML 结构变化。`notes.json` 与 chroma `meta.json` 各自存所绑定的指纹。
  **指纹不匹配按消费方分级降级，不阻断 `load_book()`**：notes 不匹配 → 停止套用标注并返回 stale；chroma 不匹配 → 索引标记 stale 提示重建。坏索引不得导致书打不开。
- **A2 pickle 读取回退**保留但默认关闭，需显式 `READER3_ALLOW_PICKLE=1`，pkl 文件不删除。**须补退出机制**：写明停止 pkl 写入的版本号、删除 runtime fallback 的版本号、启用时每次启动明确告警、提供 `--migrate-all` 与未迁移库存清单；`--migrate` 使用专用 legacy loader，不要求用户先开全局环境变量。
  > **环境变量只管停写 pkl 之后的时间窗**，双写期的 pkl 是对等产物不是遗留数据，无需开关；三态判定与两个时间窗的分界见 Phase 3 的「读取状态机」。
- **A3 `static/dist/` 提交进 git**，Node/Vite 仅作构建期工具。须配 lockfile、固定 Node/Vite 版本、可重复构建 CI 检查，以及 wheel 内容测试（见 P0-2）。
- **A4 PWA 缓存策略写死**：HTML 与 `/api/*` 一律 network-first 不缓存；只缓存内容哈希过的 `dist/` 资源与 vendor bundle；SW 内嵌 build version。**`skipWaiting()` + `clients.claim()` + activate 立即清旧缓存三者同用会撕裂版本**——仍打开的旧页面加载旧 hash chunk 会失败；改为保留前一代缓存（清 N-2），或强制提示并刷新全部 client。
- **A5 `book_store.py` 先定接口契约再写实现**：
  `load_book(book_id) -> Book`、`load_book_metadata(book_id)`、`load_chapter(book_id, order)`、`iter_chapters(book_id)`、`chapter_count(book_id)`、`book_fingerprint(book_id) -> str`、`storage_format(book_id) -> Literal["json","pkl"]`。
  只暴露全量 `load_book()` 会让 Phase 3 的 JSONL 随机读取与 Phase 2b 的性能优化无处落脚——JSONL 将退化为「换扩展名的 pickle」。`manifest.json` 为每章记录 `offset_bytes` / `length_bytes` / hash，`chapters.jsonl` 二进制 seek 读取；书库页只读 manifest，单章阅读只读一行。
  **合并范围为三处** `_Reader3Unpickler` / cached-loader：`server.py` 一处、`search_service.py` 一处（`load_book_cached` + `load_book_index`）、`vector_search.py` 一处（2026-08-16 复核；原文写的行号已漂移，故改用符号定位）。
  > **原文写的是「四处」。第四处已于 2026-08-16 删除，不进 `book_store.py`。** 那是 `SearchIndex` / `BookIndex.from_book_pkl` / `SearchIndex.build_from_library`——001-search-features 的 T027/T029/T030 产物，实现了没接线，`search_library()` 后来走的是 per-book `load_book_index` 那条路，全仓库零调用方。它带两处分歧：用**裸 `pickle.load`，没有 `_Reader3Unpickler` shim**（另外三处都有），且包在 `except Exception: failed.append(book_id)` 里——一本 legacy `__main__.Book` 的 pkl 在阅读器里能开，在这个索引里会**无声消失**；同时它整段复制了 `load_book_index` 的 `BookIndex` 构造体。把它搬进 `book_store.py` 等于把一个静默失败分支洗成「现役设计」，故直接删除。
  >
  > 删除边界：只删 `SearchIndex` 类与 `BookIndex.from_book_pkl` 这个 classmethod。**`BookIndex` / `ChapterIndex` 两个 dataclass 是活的**——`load_book_index()` 构造它们，`search_book` / `search_library` / 章内定位三条路径都在用。`search_service.py` 773 → 734 行。
  缓存改为**自定义 weighted LRU**（按估算常驻字节淘汰，key 纳入 mtime/指纹）——`functools.lru_cache` 无法表达按字节淘汰。

### 代码质量决策（B1–B4）

- **B1** `escapeHtml` 是**活的全局覆盖**，非 DRY 问题。`reader.html` 先载 `search.js`（定义 `escapeHtml(text)`）后载 `ai.js`（定义 `escapeHtml(str)`），后者静默覆盖前者，`search.js` 里 `renderResults()` 的调用点执行的是 ai.js 的实现，两者在 falsy 输入上语义不同（`String(text)` vs `String(str || "")`），而这是宪法第 4 条管辖的 XSS 出口。
  → Phase 0 将 `search.js` / `ai.js` / `settings.js` / `library-search.js` 四个文件包进 IIFE（仓库另外八个 JS 文件本就是 IIFE，这四个是落后者），falsy 语义统一为 `String(v ?? "")`。
  **附带发现（正面）**：真正的跨文件全局契约只有 `window.Reader3Epub` 一个（`epub-renderer.js` 定义，annotations.js / search.js 经 `?.` 消费）；`annotations.js` 的 `getReaderContext` 在 IIFE 内不构成冲突。ES module 化的爆炸半径远小于「5818 行裸 JS」的直觉。
- **B2** 67 处 `except Exception`、4 处裸 `pass`。Phase 1a 开头先写死三级规则：外部数据读取可降级但必须 `logging.warning` 带上下文；数据完整性校验禁止捕获必须上抛；禁止裸 `pass`。ruff 开 `BLE`/`S110`，存量入白名单逐步清理。已知四处（`_parse_summary_payload()`、`api_ai_question()` 内的 `push()` 闭包、`ai/books.ensure_book_uuid()`、`ai/conversations.list_conversations_combined()`）在 Phase 1a 修（**不放 Phase 0**——这是行为变更，需与测试同步）。
- **B3** Phase 2 对 Python 写了「不改行为」，Phase 4 对 JS 无对称约束。补上该约束，并把第 5 步拆为 **5a**（纯 JS 拆 `annotations.js`，不动一行逻辑，验收：1b 标注 E2E 全绿）与 **5b**（拆出的文件逐个转 TS，同一套 E2E 再全绿）。⚠️ 本条原写的 anchoring/renderer/ui 三分法已被证伪，实际划分见 [`specs/014-ts-frontend-reader/tasks.md`](../../specs/014-ts-frontend-reader/tasks.md)。CFI/DOM Range 这类脆弱代码，多一个 PR 的成本远低于混在一起后的调试成本。
- **B4** 42 处 `console.log`（annotations.js 33 / epub-renderer.js 9）换成 `debug.ts` 分层，由 `localStorage.reader3_debug` 控制（默认关），ESLint 开 `no-console` 放行 warn/error。

### 性能（C1–C5，计划原本无此章节）

- **C1 [P1]** `search_library()` 对库内每本书调 `load_book_cached()`（`lru_cache(maxsize=10)`）+ `load_book_index()`（`lru_cache(maxsize=4)`）。每次 miss 是全书反序列化 + 全书归一化。
  **阈值订正（2026-08-16）**：原文写「库超 10 本即颠簸」，看的是 `load_book_cached` 的 `maxsize=10`。真正的约束是 `load_book_index` 的 **`maxsize=4`** ——**第 5 本就开始颠簸**，不是第 11 本。且 `load_book_index(book_id, books_dir, *, case_sensitive)` 把 `case_sensitive` 编进了 key，同一本书大小写敏感/不敏感各占一格，**有效容量再折半到 2 本**。→ **Phase 2b**。
  一个错的阈值比没有阈值更糟：它会被当成性能测试的判据，然后永远不触发，最后得出「C1 不存在」的结论。
- **C2 [P1]** `_normalize_with_map()` 的 `List[int]` 是每字符一个 Python int：300 万字符 → 300 万元素 list（粗估 >100 MB）。换 `array('I')` 约 12 MB，且仍支持 `index_map[i]` 下标，**不改变** `highlight_ranges_for_chapter()` 的偏移语义。稀疏 breakpoint 表示留到第二阶段（casefold 扩张与 combining mark 删除的错误风险高）。→ **Phase 2b**，须做差分测试。
- **C3 [P2]** 三处 `lru_cache` 的 key 均不含 mtime/指纹，重新处理同名书后进程继续返回旧 `Book`/`BookIndex` 直到重启。→ **Phase 2a**（并入 weighted LRU）。
- **C4 [P2]** JSONL 若 `load_book()` 仍整份读完，相比 pickle 只是换扩展名——pickle 对 dataclass 图通常更快，JSON 需先建 dict/list 再构造 dataclass，瞬时内存更高。收益完全取决于 A5 的粒度接口 + manifest 字节偏移是否落实。
- **C5 [P1，2026-08-16 eng-review 新增]** **书库首页把每本书的正文全部反序列化了一遍。** `library_view` 遍历 `books/*_data/`，对每个目录调 `load_book_cached()` ——只为读书名、作者、封面这几个字段，却把整本书的 spine 与全文 text 都拉进内存。`lru_cache(maxsize=10)` 意味着第 11 本起每次刷新首页都是冷读。
  这是**全站访问频次最高的路径**（每次进站必走），而 C1 说的跨库搜索是低频操作 —— C1–C4 一个字没提它，优先级排反了。
  修法与 A5 的粒度接口天然对齐：`load_book_metadata(book_id)` 只读 `manifest.json`，不碰 `chapters.jsonl`。
  ⏳ **落点待裁决**：严格说它依赖 Phase 3 的 `manifest.json` 才成立；放 Phase 2b 需要先出一个过渡版（例如单独缓存一份轻量书目 JSON）。见合流计划文末 UNRESOLVED DECISIONS。

性能工作**单列 Phase 2b**：塞进 Phase 2 会让结构变化与缓存算法变化混淆；塞进 Phase 3 会让序列化格式、加载策略、搜索性能三者同变，等价性证明失去可信度。

**Phase 1a 须先记录基准**：冷启动、二次相同查询、峰值 RSS、反序列化次数、归一化次数，**外加「首页冷启动 TTFB × 书库规模」**（C5 的判据，且它比跨库搜索更贴近真实使用）。

> **基准需要一个 20 本的合成书库 fixture。** 本仓库 `books/` 目前只有 1 本，C1–C5 的全部结论都是**推断而非实测** —— 单本库里 `maxsize=4` 与 `maxsize=10` 表现完全一致，颠簸根本不会发生。fixture 用小体量 EPUB 复制改名即可（重点是**本数**，不是字数），另留 1–2 本大部头覆盖 C2 的 300 万字符路径。

### 测试（详见 Test Plan 工件）

零测试、零 CI、无既有约定。覆盖率目标：Phase 1a 全项目 70% line / 60% branch；Phase 2 将改动的模块 ≥85% branch；`book_store` / `_normalize_with_map` / notes 持久化 / AI routing ≥90% branch；此后新增或修改行 90% diff coverage。

计划原列的七类 fixture 不足，须补四组：spine/TOC 结构（多 anchor 指同一 XHTML、`linear="no"`、TOC 指向不存在文件、同 href 不同 fragment）、Unicode（NFC/NFD、`ß→ss` casefold 扩张、土耳其语 `İ`、非 BMP 与 ZWJ emoji）、标注锚定（quote 跨 text node / 跨段落 / 章内重复靠 prefix-suffix 消歧、CFI 失效回退、重叠标注、stale/orphan）、规模与失败（300 万字符 fixture、非法 ZIP、缺 container）。

> **偏移单位必须写进 API 契约**：Python 按 Unicode code point，DOM/JS 按 UTF-16 code unit。当前前端自行重算范围掩盖了差异，Phase 4 合并共享 TS 模块时极易错误复用服务端 `ranges`。

42 条路由用三层组织（`app.routes` 清单快照 + 六组表驱动契约 + 少量领域场景），避免 42 份复制粘贴；复用或校正既有 `specs/*/contracts/*.yaml`。

iframe 标注 E2E 可行：Selection 本就不能跨 browsing context，实际需求是「iframe 内建选区 → 操作外层工具栏」。路径为 child frame 内 `document.createRange()` → 写入 iframe Selection → iframe document 上派发 `mouseup` → 点外层工具栏 → 断言 `POST /api/notes/*` → 刷新 → 断言 iframe 内重现 `<mark>`。`window.Reader3Epub` 已提供所需可测性桥。真实鼠标拖选只保留一条 smoke。

> **2026-08-16 修正**：这条链里**只有最后一段构成通过条件**——「刷新后 `<mark>` 回到同一段文字上」。断言 `POST` 发生过属于 wiring-only，仅留作失败时的诊断信息。见 `specs/009-e2e-annotations/tasks.md` §0。

工件：`~/.gstack/projects/anzchy-reader3-pro/jackcheng-master-eng-review-test-plan-20260815-151717.md`
任务：`~/.gstack/projects/anzchy-reader3-pro/tasks-eng-review-20260815-151717.jsonl`（30 项）

### 最可能的失败模式

**「等价性测试通过，但真实标注已经坏了」。**
`--migrate` 只断言新旧 loader 的逐章 `text` 相等，而用户实际阅读与 CFI 锚定来自原始 EPUB 在 epub.js iframe 中的 DOM。`chapter.text` 是 `extract_plain_text()` 的空白折叠产物；annotations 则从 iframe text node 计算 quote / prefix / suffix / CFI（`annotations.js` 的 `createAnnotation()`）。两者不是同一份东西。因此完全可能出现：逐章文本相等 ✓ 指纹相等 ✓ 单测全绿 ✓ 但 spine href/order、DOM 空白或 CFI 路径已变 → 标注恢复到错误的重复文本，或彻底消失。**且标注是用户产生的数据，错了不能重新生成。**
→ 迁移验收必须比对 metadata、spine order/id/href、TOC 树、content hash、text hash，**并跑至少一条真实 iframe 标注迁移 E2E**。

### 其余未讨论但会咬人的问题

- **多标签页丢写**：notes 是 load→modify→save 全覆盖（`notes_service.py` 的 `add_annotation()` → `save_annotations()`），`os.replace` 只保证单次写入原子，不防两个并发请求互相覆盖。自托管单用户开两个标签页即可触发。需 per-file lock 或 revision/ETag 乐观并发控制。
- **Chroma 无事务**：原建议的「先删 collection 再写」会在 embedding 失败、磁盘满或进程退出时留下空的或半成品索引。改为 **generation swap**：新建 `reader3_book_<generation>` → 完整写入 → 校验 chunk count 与指纹 → 原子更新 `index_meta.json` 的 active collection → 成功后删旧 generation。
- **发布包验证**：CI 不能只检查 git 中有 dist，须实际 `uv build`、解包 wheel、断言 templates / dist / js / css / vendor 全部存在。

### 明确不在本次评审范围

后端语言选型（已定 Python，不重开）· 嵌入模型与向量库更换 · SPA 框架引入 · SQL 数据库 · Electron/Tauri 立即实施 · UI 视觉设计（属 `/plan-design-review`）· 产品优先级与排期（属 `/plan-ceo-review`）· 具体 provider 的 prompt 质量。

### 已经存在、不必重建的东西

原子写模式（`collections_service._atomic_write_json()`、`notes_service.save_annotations()`、`ai/books.ensure_book_uuid()`、`ai/conversations.save_conversation()`）—— Phase 2 修 `ai/config.py` 时照抄即可 · 路径安全校验 `_validate_book_id_path_safe()`· `window.Reader3Epub` 桥接层已提供 E2E 所需的全部钩子 · `specs/*/contracts/*.yaml` 契约文件 · 八个已 IIFE 化的 JS 文件 · `_Reader3Unpickler` 的模块重映射逻辑（迁移期的 legacy loader 直接复用）。

### 并行化策略

Phase 0 与 Phase 1a 的 fixture 语料建设可并行（不同文件）。Phase 1a 内的四类单测（搜索偏移 / 摄取 / 持久化 / AI routing）互不相干，可四个 worktree 并行。Phase 1b 与 Phase 2a 可并行（1b 只阻塞 Phase 4）。Phase 2b 必须在 2a 之后（依赖 `book_store` 的粒度接口）。Phase 3 必须在 2b 之后。Phase 4 的 5a/5b 严格串行。

### VERDICT

**APPROVE WITH CHANGES** — 计划的技术判断（后端不迁 TS、不上 SPA 框架、不做 Electron/Tauri、pickle 是真实阻塞点）全部成立，证据基础扎实。但在实施前必须：(1) 补入两个 P0；(2) 按上述 8 阶段重排；(3) 采纳 A5 的粒度接口契约与 A1 的分级降级；(4) 将 Chroma 改为 generation swap。其中 (3) 与 (4) 是 Codex 标记的阻塞项——不修则 JSONL 迁移收益归零且索引重建不具崩溃一致性。

NO UNRESOLVED DECISIONS
