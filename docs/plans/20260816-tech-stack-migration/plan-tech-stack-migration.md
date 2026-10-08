# Reader3 Pro 技术栈迁移 —— 唯一实施指南

- **日期**: 2026-08-15 起草 · 2026-08-16 合流排序 · 2026-08-17 拆分前端 · 2026-08-17 两份计划合并
- **状态**: 提议（待批准）
- **决策来源**: Claude（Fable 5）全仓库分析 + Codex（gpt-5.6-sol）独立推演，两方独立收敛于同一结论
- **Codex 会话**: `/cc-suite:continue 01a00400-4fa0-7d60-9cb9-4a82c843cf0f`（任务 `consult-mstytiy0-43aczt`）

> ### 本文是什么
>
> **技术栈迁移的唯一计划文档。** 此前这半边是两份：`plan-tech-stack-migration.md`（做什么）与
> `plan-ui-migration-sequencing.md`（什么顺序做）。两份文档反复互相引用「本文不权威，见对方 §X」，
> 读一遍要来回跳七八次，而"做什么"和"什么顺序做"在实施时从来不分开看。**2026-08-17 合并为本文，
> `plan-ui-migration-sequencing.md` 已删除**，它的全部内容在这里，章节编号（§3 合同 / §4 汇合点 /
> §6 阶段分解 / §7 门槛表 / §9 分支编号 / §9.1 依赖图）**原样保留**，外部引用不必改。

> ### 权威范围
>
> **本文权威**：
> - 技术栈选型（§1.1、§10）、各阶段**做什么**（§6）、明确不做的事（§11）、风险（§8）
> - **顺序**——阶段划分、并行/串行关系、耦合点（§2）、四份合同（§3）、阶段门槛（§7）、**分支编号**（§9）、依赖图（§9.1）
> - 附录 A 的 A1–A5 / B1–B4 / C1–C5 架构与性能决策，附录 B 的 R1–R15 处置台账
>
> **本文不权威**（**只索引不复述**——凡是能在下表里找到家的事实，本文只写一句话加链接）：
>
> | 需要知道 | 去哪里 |
> |---|---|
> | 双层 token、`data-testid` 前缀方案、组件清单、逐页规格、**iframe 边界（§6.0）**、**降级状态 DEG-S1–DEG-S5（§6.4）**、响应式、可访问性 | [`spec-frontend-design.md`](../20260817-frontend-ui-refactor/spec-frontend-design.md) |
> | **前端全部工作项 WI-1–WI-20 与前端测试矩阵**、`annotations.js` 八模块拆分 | [`20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md`](../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md) |
> | **标注宿主契约 K1–K6** | [`contracts/annotation-host-contracts.md`](../20260817-frontend-ui-refactor/contracts/annotation-host-contracts.md) |
> | 原型的性质、**原型 → 生产的翻译规则**、文档分工总表 | [`designs/reader-pro-next/README.md`](../../../designs/reader-pro-next/README.md) |
> | 现状审计（是什么样）＋ 已拍板的五条产品决策 | [`designs/reader-pro-next/spec/reader-pro-spec.md`](../../../designs/reader-pro-next/spec/reader-pro-spec.md) |
> | 原型相对现状补齐了什么、还差什么 | [`designs/reader-pro-next/spec/reader-pro-next-parity.md`](../../../designs/reader-pro-next/spec/reader-pro-next-parity.md) |
> | **Phase 1b E2E 用例清单**（读路径 / 写路径 / K1–K6 / DEG-S1–DEG-S4） | [`tasks/009-e2e-annotations.md`](./tasks/009-e2e-annotations.md) |
> | **Phase 0 八项的逐项验收、合入记录**与哪几项适合交给 `/tdd-guardian:workflow` | [`tasks/007-hygiene-and-contracts.md`](./tasks/007-hygiene-and-contracts.md) |
> | **覆盖率门槛策略**、42 条路由契约的三层组织、异常处理规则 | [`tasks/008-test-safety-net.md`](./tasks/008-test-safety-net.md) |
>
> 之所以立"只索引不复述"这条规矩：此前三份计划各自复述对方的内容，其中三处代码行号引用在
> 2026-08-16 复核时已全部失效，`annotations.js` 的模块划分与 `data-testid` 的统计数字在两处出现不一致。
> **每条事实只有一个家。** 要改上面任何一项，改它的权威文档，不要在这里加一份副本。
> **本文不写代码行号**——行号会漂移，用符号名。

---

## 1. TL;DR

### 1.1 最终决策

| 维度 | 决策 |
|---|---|
| 后端 | **保留 Python 3.10+ + FastAPI + uv**，不迁移 TypeScript |
| ML/RAG | 保留 sentence-transformers + 嵌入式 ChromaDB，改为可选依赖组 |
| 前端 | **迁移到严格 TypeScript + Vite 多页构建**，不引入 SPA 框架 |
| 存储 | 文件系统优先不变；**`book.pkl` → 版本化 JSON/JSONL 格式** |
| 测试 | pytest + Playwright（+ 后续 Vitest），GitHub Actions CI |
| 桌面化 | **暂不做 Electron/Tauri**；用 `reader3 launch` + PWA/app 窗口替代；将来确需分发时选 Electron（非 Tauri） |

> 一句话：语言不是瓶颈，工程化才是。全栈 TS 重写估算 8–16 全职工程周且最终退化为 "Node 编排 + Python worker" 三运行时架构；Electron 是在为不存在的分发需求付 500MB+ 的税。

> 📸 **现状证据**：[`designs/reader-pro-next/spec/screenshots/`](../../../designs/reader-pro-next/spec/screenshots/) —— 22 张实测截图（2026-08-15），对应 `reader-pro-spec.md` §14。其中 §7.4b（端口硬编码）与 §7.4c（进度不一致）两条修订直接由这次复核发现。

### 1.2 顺序总览

**先把合同钉死，再让三条线分头跑；它们在 Phase 3 三路汇合，而 Phase 3 与 Phase 4B 必须串行。**

```
Phase 0  合同 + P0 止血  ← 所有事情的前置
   │
   ├──────────────────────────────┬───────────────────────────┐
   ↓                              ↓                           ↓
Phase 1a Python 测试 + CI      Track D 设计补齐            （0.5 完成即可开工）
（阻塞所有后端改动）            DEG-S1–DEG-S5 + 合同对账            Phase 1b Playwright E2E
   ↓                              （阻塞 Phase 3）            （阻塞 4A；经 soak 阻塞 Phase 3）
Phase 2a router + book_store         │                           │
   ↓                                 │                           ├──────────┐
Phase 2b 性能                        │                           │          │
   ↓                                 ↓                           ↓          │
Phase 3  JSONL + 指纹 + generation swap  ←── 三路汇合 ───────────┘          │
   │                                                                        │
   │        ┌───────────────────────────────────────────────────────────────┘
   │        ↓
   │   Phase 4A 前端底座与非阅读页（settings → library）
   │        │        ※ 完全不碰 annotations.js 与 reader.html
   └────┬───┘
        ↓
   Phase 4B 阅读器（拆分 → 外壳重写 → 主题面板 → 进度收敛）
        ↓
   Phase 5  launch + PWA
```

**唯一的强制串行**：`Phase 3` 与 `Phase 4B` 都改动标注锚定的上下游，必须一前一后，**且 Phase 3 在前**（§4）。

**唯一的汇合点**：`Phase 3` 同时等 2b、Track D、1b 的 soak——完整依赖图见 §9.1。

**最容易做错的事**：把原型当成待移植的代码。它是可执行的规格——翻译规则见 `designs/reader-pro-next/README.md`。

---

## 2. 两条线在哪里真的耦合

大部分"前后端耦合"的担心在本项目里不成立——API 形状在 Phase 2a（纯重构）里不变，前端不依赖 Python 内部结构。真正的耦合只有五处：

| # | 耦合点 | 方向 | 后果 |
|---|---|---|---|
| C1 | **`data-testid` 契约** | 设计 → 后端测试 | Phase 1b 的 E2E 用什么选择器，决定 Phase 4 改布局时 E2E 是否整套报废。testid 必须**早于** 1b 写完 |
| C2 | **标注锚定** | Phase 3 ↔ Phase 4B | Phase 3 改锚定依赖的**数据**（spine 指纹、章节内容 hash），Phase 4B 改锚定依赖的**宿主 DOM**（工具条、面板）。同期动两边出问题无法归因，而标注是用户产生的、错了不能重新生成的数据 |
| C3 | **降级状态** | 后端 → 前端 | 指纹不匹配时 notes/索引分级降级，五个状态（设计规格 §6.4 的 DEG-S1–DEG-S5）**原型里一个都没有**。没有 UI 就等于静默失败 |
| C4 | **API 形状演进** | 后端 → 前端 | Phase 3 给响应加字段。坚持**加法式演进**则前端永不阻塞；一旦改名或改语义，两条线立刻锁死 |
| C5 | **阅读进度单一数据源** | 行为变更 | 三个消费方跨 4A 与 4B 两个阶段，必须先定义再分头消费 |

除此之外前后端**没有**硬依赖。这就是为什么下面的顺序可以让两条线大段并行。

> ⚠️ 本节的 C1–C5 是**耦合点**编号，与附录 A「性能」节的 C1–C5 是两套不相干的编号，别串。

---

## 3. 开工前必须冻结的四份合同

四份合同都很便宜，但任何一份晚定，后面都是成建制返工。

| # | 合同 | 内容在哪 | 冻结时点 |
|---|---|---|---|
| **合同 1** | `data-testid` | 命名与前缀方案：设计规格 §4；实测对账（138 个站点，**0 个合规**）：同 §4.1；逐条新旧映射与回贴清单：[`contracts/testid-rename-map.md`](./contracts/testid-rename-map.md) | Phase 0.5 ✅ |
| **合同 2** | Design token | 双层体系与全部取值：设计规格 §3。剩余两项待定见下 | Phase 4A.1 |
| **合同 3** | API 形状 v1 | Phase 1a 的 42 路由契约测试即其可执行形式 | Phase 1a |
| **合同 4** | 消息表 key | 英文为默认 locale（D-2）；key 命名建议 `{page}.{region}.{element}`，与 testid 同构便于对照。原型英文文案即 `en` 初值 | Phase 4A |

**合同 1 的顺序要点**：testid **先在原型里定名，再回贴现有 Jinja 模板**，不能反过来。理由见设计规格 §4.1。这是整套迁移的 strangler-fig 接缝——testid 是唯一横跨新旧两套实现的不变量。

**合同 2 尚未收口的两项**（其余已于 2026-08-16 并入设计规格 §3）：

| 冲突 | 二选一 | 建议 | 落点 |
|---|---|---|---|
| 标注暗色变体 | 规格的 `--p-hl-*-dk` 四个显式值 vs 原型的 `color-mix(… 45%, transparent)` | 取显式值——`color-mix` 在旧 Safari 上要 fallback，而这是标注可读性 | Track D |
| 原型的单层 token 名 | `--canvas` / `--surface` / `--text` / `--anno-*` / `--page-*` 映射到规格的两层 | 以规格的两层为准，一次性映射 | 4A.1 |

> 这两项的**实测结论与收口方案**在前端计划的 WI-7 / WI-10 里（第一项实测后发现是 **alpha 问题不是颜色问题**，九处而非八处）。本表只持有「它们尚未冻结」这个顺序事实。

**合同 3 的规则**：正文已迁至 [ADR-0011](../../adr/0011-api-v1-freeze.md)（唯一定义处）。

---

## 4. 汇合点：为什么 Phase 3 必须在 Phase 4B 之前

Phase 3（存储格式 + 指纹）与 Phase 4B（阅读器外壳重写）都在标注锚定周围施工：Phase 3 改锚定**依赖的数据**，Phase 4B 改锚定**依赖的宿主 DOM**。两者同期进行时，"标注恢复到错误位置"这类问题**无法归因**。方向由两条论证定：

1. **测试可信度**：先重写阅读器则标注 E2E 也随之重写，然后在一套刚出生、尚未被时间检验的测试下迁移用户数据。反过来则是在一套~~已经跑绿一段时间的~~**已经在冻结条件下对候选版本跑满一批的** E2E 下迁移。这条要能兑现，前提是~~**真的等它跑绿一段时间**~~**真的在同一 `commit` / `suite_hash` / 运行剖面上首次通过恰好 10 次全量（一批）**——见 §7 的 soak 门槛（⬛ 2026-09-28 由日历等待改为批次规则）。
2. **已点名的失败模式**：「等价性测试通过，但真实标注已经坏了」要求迁移验收必须跑真实 iframe 标注 E2E。那条 E2E 只有在阅读器 DOM 还没变的时候才是"真实"的基准。

> **原本还有第三条「不可逆性」，已删除——它站不住。** Phase 3 迁移的是 `book.pkl → manifest.json + chapters.jsonl`，属**派生数据**：源头 `book.epub` 就在同一目录且不在变更范围内，`notes.json` / `ai_meta.json` / `chroma_db/` 同样不动；叠加计划已有的双写 + 回退读，回滚动作就是删掉两个新文件。Phase 3 是**可逆**的。
>
> **但"删掉两个新文件"是必要不充分的**，两点补充：(1) 删之前必须确认 `book.pkl` 存在且读得开——`--migrate` 原地读写、不删任何既有文件，正是这个前提的保证条款；(2) 一旦走到 Phase 3 里"稳定一个大版本后移除 pickle 写入路径"那一步，pkl 不再新增，此后新处理的书**没有可回退的对象**，回滚动作变成「按 `book.epub` 重新摄取」——而摄取路径会 `rmtree`，所以那时的回滚同样受"原地"约束。可逆性是有保质期的，别把它当成永久属性。写入顺序本身的保证见 §6 Phase 3 的「两文件提交协议」。
>
> 这条是 2026-08-16 eng-review 里 Codex 反向挑战本排序时暴露的：它据此主张把 Phase 3 挪到 4B 之后，前提被源码核验证伪，**排序维持不变，但论据换成上面两条**。
>
> 辩论的副产品是一条真的不可逆风险，与格式无关：`reader3.py` 在写入前 `shutil.rmtree(output_dir)`，而 `notes.json` / `ai_meta.json` / `chroma_db/` 全在 `output_dir` 里。因此 **`reader3 --migrate` 必须原地读写，禁止复用摄取路径**——已写进 §6 Phase 3 的验收。

**但这不意味着前端要干等**——Phase 4A 完全不碰 `annotations.js` 与 `reader.html`，可与后端线全程并行。

---

## 5. 采用的工程实践

| 实践 | 在本项目的落点 |
|---|---|
| Contract-first | §3 的四份合同先于任何实现 |
| Characterization tests before refactor | Phase 1a/1b 先固化现状行为，再动结构 |
| Strangler fig（逐页替换） | Phase 4 按页垂直切片，testid 作为跨新旧的不变量 |
| Branch by abstraction | `book_store.py` 的粒度接口先定契约，pkl / JSONL 两套实现藏在后面 |
| Expand–migrate–contract | API 加法式演进（合同 3）；存储双写 + 回退读 + `--migrate` |
| 脆弱子系统一次只动一个变量 | Phase 3 与 Phase 4B 严格串行（§4） |
| 垂直切片优于水平分层 | 每页一个 PR 含 markup + TS + CSS，而不是"先全站改 CSS 再全站改 JS" |
| 并行代理共用 worktree 时，破坏性验证只走网络层 | 定向破坏（sabotage）一律用 `page.route` 改写响应体，**绝不原地改 `src/`**——共享 worktree 里那等于污染并跑的同伴。009 Wave 4 实测撞到过一次（一个 agent 的 `src/` 破坏被另一个当场看见），详情记在 [`tasks/009` 跨波欠账 #25](./tasks/009-e2e-annotations.md) |

---

## 6. 分阶段实施计划

本节同时持有每个阶段**做什么**与**怎么分解、谁能并行**。门槛在 §7，依赖图在 §9.1。

### Phase 0 —— 合同与止血（目标：一周内，每项独立 PR）

评审补入的两个 P0 与几项便宜但会阻塞后面的前置工作。每项独立 PR。

| 编号 | 内容 |
|---|---|
| 0.1 | P0-1：`process_epub()` 的 `shutil.rmtree` 会连 `notes.json` 一起删 |
| 0.2 | P0-2：wheel 打包漏 `static/js` / `static/css` / vendor |
| 0.3 | `--port` / `READER3_PORT` ＋ 新增 `GET /api/health` |
| 0.4 | 四个落后 JS 文件 IIFE 化，`escapeHtml` 全局覆盖修正 |
| 0.5 | **testid 定名：先改原型，再回贴模板**；规则写入 CI lint（**两条不同的 lint**，见下） |
| 0.6 | 事实性修复：`.gitignore` 冲突标记、版本号、`ai_settings.example.json` |
| 0.7 | 删除死代码 `SearchIndex` / `BookIndex.from_book_pkl` / `SearchIndex.build_from_library`（A5 的「第四处」），使 `book_store.py` 的合并范围收敛到三处 |
| 0.8 | **token 悬空引用 lint**：`var(--x)` 里的 `x` 必须有定义，**`var(--x, fallback)` 带 fallback 也算违规**（与 0.5 的两条 lint 是**第三条**，管的是 CSS 变量不是 testid） |

各项的具体内容：

- **0.1 P0-1**：`process_epub()` 里的 `shutil.rmtree(output_dir)` 会连同 `notes.json` 一起删除——改为写 staging 目录 + 校验 + 原子切换
- **0.2 P0-2**：`pyproject.toml` 的 `"static/*"` 非递归，打出的 wheel 缺 `static/js` / `static/css` / vendor
- **0.3 端口可配置 ＋ 健康探针**：`run_server()` 硬编码 `port=8123`，无 env / CLI 覆盖。加 `READER3_PORT` env + `--port` CLI（CLI 优先）。这在截图复核中已造成实际阻塞：为采集 classic UI 必须绕过 `reader3-server` 入口直接调 uvicorn。对 Phase 1b 的影响更直接——Playwright 要起自己的实例，固定端口会与开发者本地的 8123 冲突，CI 并发跑也会抢端口。
  同时新增 **`GET /api/health`**：Phase 1b 的 Playwright 需要就绪探针，没有它只能轮询 HTML 页面，慢且易误判。两行代码，放在这里最省事（Phase 5 的 `reader3 launch` 直接复用）
- **0.4 四个落后 JS 文件 IIFE 化**（`search.js` / `ai.js` / `settings.js` / `library-search.js`），`escapeHtml` 全局覆盖修正——见附录 A 的 B1
- **0.5 `data-testid` 全量补齐**，命名与前缀方案见设计规格 §4，改名顺序「先原型、后模板」见设计规格 §4.1。规则写入 CI lint：**E2E 只允许 `data-testid` 与 ARIA role/name**，禁止 class 选择器、`nth-child`、层级结构选择器。契约是「重设计可任意改 class / 嵌套 / 标签，**不得改 testid**」
- **0.6 事实性修复**（**三项都归这里**，Phase 2 不再重复）：`.gitignore` 末尾遗留的 merge 冲突标记、`pyproject.toml` 版本号对齐 git tag、`ai_settings.example.json` 补齐 openai / openrouter provider。三项都只改常量与示例文件，不碰运行时行为，所以放在 Phase 0。**`max_retries` 不在此列**——删它或接通它都是行为变更，见 Phase 2
- **0.7 删除死代码** `SearchIndex` / `BookIndex.from_book_pkl` / `SearchIndex.build_from_library`（零调用方，且是附录 A 的 A5 里那个带裸 `pickle.load` 的「第四处」）——先删再谈合并，否则 `book_store.py` 会把一个静默失败分支收编成现役设计。**只删这两个符号，`BookIndex` / `ChapterIndex` dataclass 是活的**
- **0.8 token 悬空引用 lint**，见下方专门说明

> **0.5 是两条 lint，不是一条。** 计划此前只写了前者，后者一直没有归宿：
>
> | lint | 约束谁 | 规则 |
> |---|---|---|
> | **选择器 lint** | 测试代码（`tests/e2e/`） | 只允许 `data-testid` 与 ARIA role/name；禁止 class 选择器、`nth-child`、层级结构选择器 |
> | **命名 lint** | 模板与原型（`templates/*.html`、`designs/reader-pro-next/`） | 每个 `data-testid` 必须匹配**下方的 canonical 正则**（前缀方案见设计规格 §4） |
>
> 只有前者不足以保住契约：选择器 lint 全绿，模板里照样可以新增 `reader-search-hit` 这种名字，命名方案随即失守。命名 lint 必须**显式点名设计规格 §4.1 那 24 个带 `reader-` / `library-` 前缀的 testid**——它们形似合规，批量改名时最容易被当成「已经对了」跳过，而正则会把它们判为不合规，正是要的效果。138 个站点全部需要改名，lint 的初始状态就是「138 条违规」，改完归零。（此前记的 134 少算了 `Sheet` 的四个 `testId=` prop——只 grep `data-testid=` 的口径看不见它们。对账见 [`contracts/testid-rename-map.md`](./contracts/testid-rename-map.md) §1。）

#### canonical 正则（唯一定义处已迁至 `scripts/lint_testid_naming.py`）

正则的唯一定义处是 `scripts/lint_testid_naming.py` 的 `CANONICAL` 常量，裁决见 [ADR-0013](../../adr/0013-testid-invariant.md)；本文不再保留副本（此前这里的代码块与上表并存，表格里 `|` 被转义成 `\|`，曾是复制错源的来源——正是把定义处挪进可执行文件的原因）。配置或对照时从该文件 import / 复制。

> **0.8 为什么值得单列一条。** CSS 自定义属性引用不存在的名字**不报错**——`var(--typo)` 静默回落到继承值，页面照常渲染，只是颜色变成了别的东西。降级横幅正是最不能出这个错的地方（长得像普通提示 = 降级没被看见）。设计规格里实测到过三处：§6.4 引用的 `--r3-warn` / `--r3-danger` 从未定义（Codex 复审 #8），§6.2 引用的 `--r3-sidebar-w` / `--r3-right-w` 从未定义，`--r3-text-quiet` 只在三个阅读主题里被赋值、`:root` 无定义。**三处都已在 007 修掉**，但没有 lint 就会再长出来。
>
> **fallback 也算违规**，因为 fallback 恰好是这条 lint 要防的那个故障的伪装：`var(--r3-error, #ccc)` 在 token 缺失时不会露馅，横幅照常渲染成一个灰色的普通提示——比静默回落更难被发现，因为它看起来是「有人考虑过」。要 fallback 就先把 token 定义出来。
>
> 实现见 `scripts/lint_token_refs.py`（约 100 行，含扫描集与自述）：收集所有 `--x:` 定义与所有 `var(--x)` 引用，求差集。定义在别处（如浏览器内置或第三方）的走 `scripts/token_ref_whitelist.txt`。
>
> **扫描集是 `static/**` 下的全部 `.css`，不只是 `static/css/`。** 本行此前写作 `static/css/`，实施时发现那样会漏掉 `static/` 顶层的 `dedao-theme.css`（620 个 `--dedao-*`，全仓库最大的一坨 token）、`library.css`、`ai.css`、`search.css`、`settings.css` 五个文件——正好是悬空引用最可能藏身的地方。同理，规格侧除 `spec-frontend-design.md` 外也扫 `plan-frontend-ui-refactor.md` 的 CSS 块。落地实测：22 个来源、271 个定义、1119 处引用，悬空 0、带 fallback 0。
>
> **扫描范围会再扩一次，且已有归属。** 上面五处都是**现状**的样式所在地；`{前端源码根}`（Vite ＋ TS 的新目录，013 建）落地后，本 lint 必须同时扫它，否则 013／014 迁进去的样式全部脱离本 lint。前端计划有三条验收依赖它在源码根下生效（`plan-frontend-ui-refactor.md` 的 WI-7 验收 3、WI-10、WI-16），**扩范围这件事由该计划的 WI-9 验收 12 交付**，改动落回本行。此前两边都默认对方会做。**已落地（013 WI-9 批次 C）：** 源码根即 `frontend/src/`，`scripts/lint_token_refs.py` 的 `SCAN_GLOBS` 已加入 `frontend/src/**/*.css` 与 `frontend/src/**/*.ts`，由 `tests/unit/test_token_ref_scan_covers_fe_root.py` 钉住。

**验收**: 两个 P0 修复并人工 smoke；`--port` 与 `/api/health` 可用；testid 在原型与模板两侧一致且三条 lint 生效。完整门槛见 §7。

> testid 必须早于 Phase 1b 动笔。本计划已把「Phase 1b 的标注 E2E 绿灯」写为 Phase 4A 的前置条件，却没有规定 E2E 用什么定位元素；若用 class 或结构选择器，Phase 4 的任何布局改动都会推翻整套 E2E。这是全篇最便宜也最容易漏的一条。

### 并行区间（Phase 0 之后）

三条线**开工时**彼此不阻塞——但它们**不是各自跑到底**：三条线全都是 Phase 3 的前置，Phase 3 是一个三路汇合点。完整依赖图见 §9.1。

- **线 1 后端**：`1a → 2a → 2b → 3`。1a 是全局阻塞（也在这里冻结合同 3 与性能基准）。
- **线 2 E2E**：`1b`。依赖 0.3（端口/健康探针）与 0.5（testid）。用例清单见 [`tasks/009-e2e-annotations.md`](./tasks/009-e2e-annotations.md)——**必须含写路径**，否则 4B.1 的「零改动全绿」门槛是空的。
  **1b 阻塞两处，不是一处**：直接阻塞 4A，同时通过 §7 的 soak 门槛阻塞 Phase 3。它不阻塞 2a / 2b，但"不阻塞后端"是错的说法——2b 做完之后，Phase 3 还要等 1b ~~攒够 10 次连绿、跨度 5 个工作日~~在候选版本上跑通一批 10 次（⬛ 2026-09-28 改为批次规则，见 §7）。
- **线 3 Track D 设计**：产出 = 设计规格 §6.4 的 DEG-S1–DEG-S5 落进原型（本轨最大的一块）＋ loading 骨架屏 ＋ §3 合同 2 剩余两项。任务清单见 [前端计划](../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md) 的 WI-1 – WI-8。
  **Track D 阻塞 Phase 3**：Phase 3 要求 DEG-S1–DEG-S4 在 UI 里可见（见下方 Phase 3 验收），DEG-S1–DEG-S5 的原型是 Track D 的产出。
  **§4.1 的 testid 批量改名不属于本轨，属于 0.5。** 此处原先把它记成 Track D 的产出并注明「喂给 0.5」，是**重复记账**——0.5 的验收本来就是「134 条违规归零」，而它写死的顺序「先改原型、再回贴模板」里，改原型那一半就是同一件事。两处都声称拥有它，会读出一个假依赖环：0.5 → Phase 0 完成 → Track D → 0.5。Track D 与 testid 的真实关系只有一条：**本轨新建的元素按 canonical 正则命名**。

> **这三条线为什么值得单独盯**：单人维护者按状态切换时，最容易发生的失败是"后端一路推到 Phase 3 门口，才发现 1b 的 soak 计时还没开始、DEG-S1–DEG-S5 的原型还没画"。~~soak 是**日历时间**，补不回来——1b 必须尽早开始连绿，不能留到 2b 做完再启动。~~
> （⬛ 2026-09-28：日历跨度已取消，一批只要 10–15 分钟，soak 不再是补不回来的日历时间；「1b 必须尽早」
> 现在只剩一条理由——G2 与冻结要先成立，批次才有东西可跑。判据见 §7。）

> **单人维护者说明**：这里的"并行"不是要同时开三个窗口，而是三条线之间无阻塞，可按状态自由切换、随时暂停。

### Phase 1 —— 建立安全网（最高优先级，其他阶段的前置条件）

任何迁移动作之前先做。没有特征化测试，迁移成本"不可知"。拆为 **1a**（Python 单测 + CI，全局阻塞）与 **1b**（Playwright E2E，仅阻塞 4A 与经 soak 阻塞 Phase 3）。

**Phase 1a**

- [ ] 引入 pytest + dev 依赖组（`uv add --dev pytest ruff mypy`）
- [ ] 单测覆盖：EPUB 摄取（`process_epub`）、JSON 持久化（notes/collections/conversations）、Unicode 搜索偏移映射（`_normalize_with_map`）、AI 路由（`choose_routing`/`estimate_tokens`）、API 契约（FastAPI TestClient）
- [ ] Fixture EPUB 语料：EPUB2 / EPUB3 / CJK 内容 / 变音符 / 含图片 / 畸形或缺失 TOC / 空书
- [ ] ruff + mypy 配置写入 `pyproject.toml`；异常处理三级规则（见附录 A 的 B2）
- [ ] GitHub Actions：lint + type-check + pytest
- [ ] **性能基准记录在案**，含「首页冷启动 TTFB × 书库规模」；需要 20 本规模的合成书库 fixture

**Phase 1b**

- [ ] Playwright E2E：书库导航、epub.js 渲染、iframe 内标注**创建与恢复**、AI SSE 流式。**完整用例清单见 [`tasks/009-e2e-annotations.md`](./tasks/009-e2e-annotations.md)**——含写路径（四类型创建 / 改色的现状特征化 **W-5a**（真正的改色 W-5b 归 4B.1，2026-09-01 拆分） / 删除 / 笔记保存）、K1–K6 与 DEG-S1–DEG-S4 的正向证据，以及「断言刷新后高亮回到同一段文字」这条统一收尾
- [ ] E2E 必须进**本地 tdd-guardian 的 `e2e` lane**（`gateOn: push`），不得挂成「想起来才跑」的旁路任务——Phase 4A 的前置条件依赖它，soak 也数它（改基见 §7）

**验收**: 测试门禁生效——**本地 tdd-guardian 门禁**，不是 GitHub 的 required check（CI 仅发版触发，改基说明见 §7 的 soak 门槛小节）；核心路径（摄取/搜索/笔记/路由）有回归保护。完整门槛见 §7。

### Phase 2 —— Python 内部重构（不改行为）

拆为 **2a**（结构，纯重构）与 **2b**（性能）。**性能工作单列 2b**：塞进 2a 会让结构变化与缓存算法变化混淆；塞进 Phase 3 会让序列化格式、加载策略、搜索性能三者同变，等价性证明失去可信度。

**Phase 2a**

- [x] `web/server.py`（**2,905 行**——本行原写「~2,400 行」，写于 2026-08-16；2026-09-19 `wc -l` 实测 `master` 为 2,905。011 分支上是 2,979，多出的 74 行全部来自 `1be7387` 一个 commit，**不是拖延期间的自然增生**）拆分为 FastAPI routers 六组：
  - `routers/library.py`（library + collections + stats）
  - `routers/reader.py`（阅读页 + book.epub + 图片资源）
  - `routers/notes.py`
  - `routers/search.py`（搜索 + 语义索引）
  - ~~`routers/ai.py`（对话 + RAG + 摘要 + 问答）~~ → **`routers/ai/` 子包**（下一条）
  - `routers/settings.py`
  - ✅ **2026-09-19 兑付**（011 WI-4，七个 commit `6afc3fb` → `a61f6c7`）。`server.py` 2,979 → **942 行**，
    43 条路由全部搬完，`routes.snapshot` 零 diff。**落地形状与本表原文有两处出入，照记**：
    （1）`ai` 按裁定 A 拆成子包四个文件（`chat.py` 547 / `conversations.py` 236 / `summary.py` 213 / `rag.py` 37），
    所以「六组」在**实现文件**这一层是七个上下；（2）另有 `routers/health.py` 34 与共用模型 `web/schemas.py` 50。
    `api_ai_question` 那 433 行**一行没变**——下降的是单文件行数，不是复杂度。
    验收七条全兑付，含 `baseline_1b` 67 passed 且 `suite_hash` 仍为 `2747100dadf6`；
    见 [`tasks/011-backend-refactor.md`](./tasks/011-backend-refactor.md) §5 完成记录。
  - ⚠️ **2026-09-19 实测：`ai` 这一组过不了下面「每个 router < 500 行」的门槛，且不是靠搬家能解决的。**
    `/api/ai/*` 八条路由合计 708 行，其中 `api_ai_question` **一个函数就是 433 行**（`web/server.py:2454-2886`，
    9 条顶层语句 ＋ 6 个嵌套闭包：`event_gen` 174 / `_do` 139 / `worker_ollama` 55 / `worker_non_stream` 18 / `push` 2 /
    `_release_lease` 2）。它独占的模块级 helper 还有 `_stop_stream_worker` 60 行（调用点只有 `:2662`、`:2670`，都在这个函数里）。
    **433 ＋ 60 ＝ 493，再加 import 与 `APIRouter` 声明就越线**——即「把这条路由单独放一个文件、别的什么都不放」仍然不达标。
    三条候选路线与取舍记在 [`tasks/011-backend-refactor.md`](./tasks/011-backend-refactor.md) §5。
    **已裁定（2026-09-19）：走 A ＋ 一条具名、可到期、机器执行的豁免**（`chat.py` ≤ 550，到期条件
    「最大顶层函数 ≤ 400 行」），条款 canonical 在任务书 §5，本表不重述。
- [x] 新建共享 `book_store.py` —— **已兑付**（`1be7387`，011 WI-3）。**本条原文的三个部分在 2026-09-07 实测时全不成立**，兑付的是订正后的范围：`_Reader3Unpickler` 早在 007/008 期间就收敛成了 `safe_pickle.Reader3Unpickler`，不存在三份重复；`vector_search.py` 直接调 `safe_pickle.load_book_file`，**根本没有 loader、不在合并范围内**。真正重复的是两个**同名不同签名**的 `load_book_cached`（`server.py` 与 `search_service.py`，各挂一个 `lru_cache(maxsize=10)`，同一本书在进程里躺两份）。推导与「同名是陷阱，不只是重复」见 [`tasks/011-backend-refactor.md`](./tasks/011-backend-refactor.md) §0.2，本表不重述
  - [x] **同时解决缓存失效** —— 同一个 commit 兑付。key 里带上 `mtime_ns` ＋ `size`，重新处理一本书之后服务端不再供旧 `Book`
- [ ] chromadb + sentence-transformers 移入可选依赖组 `[project.optional-dependencies] semantic`（与 README"语义依赖可选"的描述对齐）。2026-09-19 复核：**未做**，`pyproject.toml` 里没有 `[project.optional-dependencies]` 这个表，两者都还在主 `dependencies`
  - **阶段归属订正**：本条列在 Phase 2a 下，而 [`tasks/011-backend-refactor.md`](./tasks/011-backend-refactor.md) §7 把它（WI-7）划进「收尾与 Phase 2b」。**以 §8 的退出门槛表为准**——Phase 2a 那一行只列了三项，本条不在其中，**所以它不拦 2a 关门**。两处措辞此后不再各写各的
- [x] 修复 `ai/config.py` 设置写入改为原子替换 —— **已兑付**（`0e103ab`，008 期间，早于 011 开工）。落地写法与本条原文有一处**刻意偏离**：临时文件名走 `tempfile.mkstemp(dir=同目录)` 而不是仓库别处那种固定的 `f"{path}.tmp"`，因为这个文件装明文 API key，权限位得由 `mkstemp` 保证（理由写在 `ai/config.py:163-167`）
- [ ] **notes 乐观并发控制**：notes 是 load→modify→save 全覆盖，`os.replace` 只保证单次写入原子，不防两个并发请求互相覆盖——自托管单用户开两个标签页即可触发。加 revision/ETag（或 per-file lock），冲突时返回 409 而非静默丢写。前端侧的冲突 UI 是设计规格 §6.4 的 **DEG-S5**
- [ ] **`max_retries` 定性**：这个配置项能在设置页填、能存进 `ai_settings.json`、能从 `GET /api/settings` 读回、`settings.js` 也在渲染它——但**全链路没有任何 provider 消费它**。删掉它还是接通它，二选一。留在 Phase 2 而不是 Phase 0，是因为两种选法都是行为变更：接通改的是重试语义，删掉改的是设置页可见字段
- [x] 路由启发式修正 —— **已兑付**（`105bbbb`，008 期间）。`ai/routing.py:38-39` 的 `_CJK_CHARS_PER_TOKEN = 1.5` / `_OTHER_CHARS_PER_TOKEN = 4.0`，以及 `:99-102` 那句 "Default DOWN" 注释与 `return 200_000`
- [ ] 修订 `CLAUDE.md` § Constitution Principles（原 `.specify/memory/constitution.md` 已随 spec-kit 工具链于 2026-08-16 删除，CLAUDE.md 的摘要版成为唯一权威）：保留简单性原则，修订已过时的实现禁令（"除 FastAPI/BeautifulSoup 外不加抽象"已不能描述含 Chroma、5 provider、异步队列、42 路由的系统）；"测试可选"条款删除
  - ⚠️ **2026-09-19 实测：只兑付了一半，仍然欠着。** 已兑付的部分：spec-kit 那段说明在位（`CLAUDE.md:118-119`），"测试可选"条款全文搜索 **0 命中**，确已删除。**未兑付的部分正是本条点名要改的那句**——`CLAUDE.md:122` 今天仍逐字写着「YAGNI - no abstractions beyond FastAPI/BeautifulSoup」，一字未动。`tasks/011-backend-refactor.md` §0.1 那张实测表把本条整条记成 ✅，**那一格是错的**，已同步订正
  - 这一格现在不是纯记账问题：`CLAUDE.md:122` ＋ ADR-0008 正是「`api_ai_question` 能不能抽出一层 service」这道题的约束条件（见上面 `routers/ai.py` 那条 ⚠️）。**先裁 router 拆法，再决定要不要动这一条**——反过来做就成了为一次重构去改宪法

**Phase 2b**

- [ ] C1 跨库搜索缓存颠簸（weighted LRU，key 纳入 mtime/指纹）
- [ ] C2 `_normalize_with_map()` 换 `array('I')`，须做差分测试
- [ ] C5 书库首页只读元数据，不反序列化正文——**落点待裁决**，见附录 B 文末 UNRESOLVED DECISIONS

**验收**: Phase 1 测试全绿（行为不变的证明）；`server.py` 每个 router < 500 行。完整门槛见 §7。
> 2026-09-19：「每个 router < 500 行」已由 `scripts/check_router_size.py` 机器执行并接入 `lint.yml`
> （`a61f6c7`）。**它的范围有个边界**：量的是「`routers/` 下每个文件」∪「`web/` 下声明路由的模块」，
> 而 `server.py` 已不再声明任何路由，因此掉出了这道闸——它剩下的 942 行共享工具不受上限约束。
> 是否另立一条 `web/*.py` 上限留给 Phase 2b 裁，见任务书 §5 完成记录。

### Phase 3 —— 存储去 pickle 化

目标格式（`manifest.json` + `chapters.jsonl`）、双写与日落规则、`reader3 --migrate` 的硬约束（原地读写、禁止复用摄取路径、不得改变 `book_fingerprint()`）的正文已迁至 [ADR-0009](../../adr/0009-book-format-manifest-jsonl.md)（唯一定义处）；写入协议与读取三态见 [ADR-0007](../../adr/0007-crash-safe-publish-protocol.md)。本节只留任务清单，不复述约束：

- [ ] 版本化中立格式落地（ADR-0009 Decision Outcome）
- [ ] `book_fingerprint()`（A1）落地，写进 manifest；notes / chroma meta 各存所绑定的指纹（[012 WI-2](./tasks/012-storage-format.md)；⬛ 2026-10-02 补入，012 §6 Q9 裁定其为本阶段隐含必需项）
- [ ] 摄取时双写；读取按三态（ADR-0007）
- [ ] `book_store.py` 封装格式判断，调用方无感知
- [ ] `reader3 --migrate <book_id>`，遵守 ADR-0009 的硬约束与配套断言
- [ ] Chroma 索引重建改为 **generation swap**（见附录 A「其余未讨论但会咬人的问题」）
- [ ] 稳定一个大版本后移除 pickle 写入路径（版本号见 ADR-0009 Migration Strategy）
- [ ] **降级状态在 UI 里可见**：A1 的分级降级（notes stale / 索引 stale）与 A2 的 pickle 回退告警一旦无 UI，就是静默的用户数据损坏。设计规格 §6.4 的 **DEG-S1–DEG-S4** 必须在本阶段可见——哪怕先落成现有 Jinja 模板里的朴素横幅，Phase 4 再按规格重做

#### 两文件提交协议（唯一定义处已迁至 ADR-0007）

> `manifest.json` + `chapters.jsonl` 的八步写入顺序、marker-last 的意义，正文已迁至 [ADR-0007](../../adr/0007-crash-safe-publish-protocol.md)（唯一定义处）。§4 的回滚条目、附录 A 的 A2 条款与 `tasks/007` P0-1 只引用该 ADR，不复述步骤。
>
> ⬛ 2026-10-02：提交点与崩溃恢复（本节与下面「两条协议缺口」）已由 [ADR-0016](../../adr/0016-generation-directory-publish.md) 取代（`gen/{g}/` ＋ 根 `manifest.json` 单指针）；三态读取仍在 ADR-0007。

##### 两条协议缺口（Phase 0 的 P0-1 实施中撞出来，已在 `reader3.py` 落地）

缺口 1（`os.replace` 换不动目录产物）、缺口 2（三件产物时 marker-last 不够）及 `_commit_staged_artifacts` 的落地形态与两条测试性质，正文已迁至 [ADR-0007](../../adr/0007-crash-safe-publish-protocol.md)（唯一定义处）。

#### 读取状态机（三态，禁止二态）

三态判定表（missing / corrupt / valid）、`corrupt` 不回退的理由、以及 A2 环境变量只管「停写 pkl 之后」时间窗的澄清，正文已迁至 [ADR-0007](../../adr/0007-crash-safe-publish-protocol.md)（唯一定义处）。

**`--migrate` 不得改变 `book_fingerprint()`。** 规则与配套断言已迁至 [ADR-0009](../../adr/0009-book-format-manifest-jsonl.md)（唯一定义处，Migration Strategy 一节）。

**进入条件**: Phase 2b 完成 **且** Track D 完成 **且** 1b 的标注 E2E 达到 **soak 门槛**——~~次数、跨度与**计数基准**三项~~批次规则（⬛ 2026-09-28 取代次数与跨度）与**计数基准**的唯一定义处是 §7，本行不复述（2026-08-24 改基：数的是本地全量运行，不再是主 CI）。三路汇合，见 §9.1。

**验收**: 新处理的书完全不依赖 pickle 即可阅读/搜索/标注；存量书可一键迁移；**`--migrate` 原地读写，有一条测试证明迁移后 `notes.json` / `ai_meta.json` / `chroma_db/` 三者字节不变、且 `book_fingerprint(book_id)` 不变**；**有一条崩溃注入测试**：在提交协议第 7 步之后、第 8 步之前中断，重启后该书仍能正常打开（状态判为 `missing`，走 pkl），且下一次迁移能干净地重跑；**重写整本书的路径（非 `--migrate`）另需覆盖「两条协议缺口」那两条**——回滚是 rename 不是 copy（断言 inode）、中断后不留下新产物挨着旧 marker；DEG-S1–DEG-S4 在当时的 UI 里可见；**并跑至少一条真实 iframe 标注迁移 E2E**（理由见附录 A 的「最可能的失败模式」）。

### Phase 4 —— 前端 TypeScript 化（增量，非大爆炸）

> **两个前提**：(1) 本阶段与前端重设计是**同一块地**，CSS 与 markup 一次到位，不做两遍；(2) 阶段拆为 4A（底座 + 非阅读页）与 4B（阅读器）。**Phase 3 必须早于 4B**（§4）。
>
> 计划原文隐含假设「UI 是完好的，只需 TS 化」——**该假设不成立**。`#font-settings-popup` 里 12 个控件（主题 ×4、字号 ±、行距 ±、字体 ×4）全部没有事件处理器，字号显示恒为 `17`、行距恒为 `1.9`；全仓库 `*.css` 对 `prefers-color-scheme` / `data-theme` 零命中，「夜间」主题没有可切换的对象。因此 Phase 4 除 TS 化之外还含**新功能**（阅读设置面板）。

> **📦 本阶段的清单整体在前端计划里。** 工具链与底座、逐页垂直切片、`annotations.js` 八模块拆分、阅读设置面板、进度单一数据源、清理项——全部展开在
> [`20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md`](../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md)
> 的 `### WI-N:` 工作项里，每项带验收判据与测试矩阵。本节只持有**顺序**、**与后端打包耦合的两条**，以及范围边界。

#### Phase 4A —— 前端底座与非阅读页

进入条件：`1b` 的 `baseline-1b` 组绿灯（**本地 lane，不是主 CI**——改基见 §7）。与 `2a / 2b / 3` 并行。

子阶段 **4A.0 → 4A.1 → 4A.3 → 4A.2 → 4A.4**（工具链 → token 与主题基础设施 → 共享模块 → settings 试点 → library ＋ 删除 Classic）。**每个子阶段做什么、验收什么，展开在
[前端计划](../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md) 的 WI-9 – WI-13 里**；本文只持有顺序与门槛（§7）。

> **为什么把主题基础设施提前到 4A.1**：token 与 `data-theme` 是全站的，settings 与 library 也要用。放到最后意味着前两页先用旧色、再回头改一遍。拆开之后「主题**能力**」在 4A.1，「阅读主题**面板**」在 4B.3。

> **每页切片的内部顺序**：markup（testid 已由 0.5 冻结）→ TS 模块 → 新 CSS，一个 PR 两个 commit。E2E 全程不改——它就是这次切换正确性的证明。

#### Phase 4B —— 阅读器

进入条件：**Phase 3 完成** 且 **4A.4 完成**（工具链已在两页上验证过）。

四个子阶段 4B.1–4B.4 的任务展开在 [前端计划](../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md) 的 WI-14 – WI-19。顺序上只有一条硬约束：**4B.1（`annotations.js` 拆分）必须在 4B.2（外壳重写）之前**——外壳重写会移动工具条 DOM，而工具条 UI 目前就长在 `annotations.js` 里；先拆分，外壳就只与一个有文档的模块边界打交道，而不是散落在 1127 行里的七个 `getElementById` 和一处隐式的 `position: fixed` 假设。

外壳与标注之间只有六个接触面（K1–K6），**其中四条坏了不报错**。契约与验收见 [`annotation-host-contracts.md`](../20260817-frontend-ui-refactor/contracts/annotation-host-contracts.md)。

#### 与后端耦合的两条（留在本计划）

- [ ] epub.js / JSZip 从 vendored 改为 npm 依赖后，`pyproject.toml` 的 `package-data` 必须跟着改——vendored 文件从 `static/js/vendor/` 换成 Vite 产物，0.2 修好的非递归 glob 会再次失配
- [ ] Vite 产物 `static/dist/` **提交进 git**（决策：不在 CI 里现构建）。它是 wheel 内容测试的对象——`008-test-safety-net` 的打包测试要断言 `dist/` 进了 wheel

**范围边界**：`reader.html` 的重设计**只覆盖外壳**（工具栏 / TOC / 笔记 / 搜索 / AI / 标注工具条 / 章节导航），**绝不触碰 epub.js iframe 内部 DOM**。理由与附录 A 的「最可能的失败模式」一致。完整判据见设计规格 §6.0（三重断言 A/B/C）。

**明确不做**: 不引入 React/Vue/Svelte——现有 UI 不需要客户端路由或全局 SPA 状态，TS 模块以小得多的架构扰动解决全部现存问题。**原型用 React 18 + 浏览器内 Babel，那是可执行规格的实现手段，不是生产选型**。

**验收**（本计划侧）: wheel 内容测试通过；每页切换后 E2E **零改动**全绿。其余验收见前端计划。

### Phase 5 —— 启动体验与（远期）桌面化

**本计划侧（Python CLI）**

- [ ] 新增 `reader3 launch` 命令：起 FastAPI → 轮询健康检查（复用 0.3 的 `/api/health`）→ 打开 PWA / Chrome `--app=http://127.0.0.1:8123` 窗口 / 默认浏览器 → 启动失败清晰报错（含端口冲突处理）
- [ ] **仅当**确证有非技术用户需要安装包时：单平台 Electron PoC——PyInstaller Python sidecar、首次使用语义搜索时下载模型（不打包数百 MB 模型）、OS 应用数据目录（弃用仓库相对路径）、sidecar 生命周期/崩溃恢复、签名与公证

**前端侧（在前端计划）**：PWA manifest + service worker（可安装、独立窗口、版本切换不撕裂）见
[`plan-frontend-ui-refactor.md`](../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md) 的 WI-20。

**验收**: 双击/单命令即可进入阅读，无需手动起服务开浏览器。

---

## 7. 阶段门槛表

| 阶段 | 进入条件 | 退出条件 |
|---|---|---|
| Phase 0 ✅ | — | **门槛已全部满足，阶段于 2026-08-24 关闭**（合入记录见 [`tasks/007-hygiene-and-contracts.md`](./tasks/007-hygiene-and-contracts.md) 的「合入记录」，本表不重述）。P0-1/P0-2 修复并人工 smoke（**六项 checklist 的正文在 [`tasks/007-hygiene-and-contracts.md`](./tasks/007-hygiene-and-contracts.md) §8.1**，本文只引用不重述）；`--port` 与 `/api/health` 可用；testid 在原型与模板两侧一致；**两条 lint 都在 CI 里生效**——选择器 lint（约束 `tests/e2e/`）与命名 lint（约束模板与原型，正则以 §6 步骤 0.5 的 **canonical 代码块**为准，违规数归零）；**0.8 的 token 悬空引用 lint 在 CI 里生效且为 0**。三条 lint 落在 `.github/workflows/lint.yml` 的同一个 job 里，分三步跑 |
| Phase 1a | Phase 0 | 测试门禁生效（**本地 tdd-guardian**，非 required check——见本节 soak 小节的改基说明）；42 路由契约测试通过；**API v1 形状冻结**；性能基准记录在案 |
| Phase 1b | 0.3 + 0.5 | **本行的展开（G1/G2 两道门）在 [`tasks/009-e2e-annotations.md`](./tasks/009-e2e-annotations.md) §8，本表不重述**。**`baseline-1b` 组**在**本地 `e2e` lane** 绿灯并入 `soak-log.md` 台账（原写「主 CI（非 nightly）」，2026-08-24 随 CI 改为仅发版触发而改基，见本节 soak 小节）；**用例覆盖写路径**（四类型创建 / 改色的现状特征化 **W-5a**（W-5b 归 4B.1）/ 删除 / 笔记保存，断言为刷新后回到同一段文字）；K2–K5 与 K1/K6 的**现状特征化**条各一条正向证据；连续 3 次全量运行零 flaky；其余组**用例写完并 review**，以 skip 形态存在。⚠️ K1/K6 的新行为与 DEG-S1–DEG-S4 的横幅**不在本阶段门槛内**——它们要到 4B.1 / Phase 3 / 4A.4 才存在，写进 1b 会形成依赖环。分组见 [`tasks/009-e2e-annotations.md`](./tasks/009-e2e-annotations.md) §0.5 |
| Track D | Phase 0 | DEG-S1–DEG-S5 设计完成并回写设计规格 §6.4；合同 2 剩余两项收口；loading 骨架屏补齐 |
| Phase 2a | 1a | ~~**每个声明路由的模块 < 500 行，唯一具名例外 `routers/ai/chat.py` ≤ 560 行**~~ → **已兑付 `a61f6c7`**，例外上限按实测（547 行）回写为 **≤ 550**（2026-09-19 裁定，判据与到期条件在 [`tasks/011-backend-refactor.md`](./tasks/011-backend-refactor.md) §5，本表不重述）；~~**该门槛须由 `scripts/check_router_size.py` 机器执行**——在此之前它只是散文~~ → **已接入 `.github/workflows/lint.yml`**（同一个 commit，见 §5 完成记录；注意 `server.py` 已掉出该闸范围）；~~`book_store` **三处** loader 合并~~ → **已兑付 `1be7387`**，且实际合并的是**两个同名不同签名的 `load_book_cached`**，不是原文写的「三处 `_Reader3Unpickler`」（`vector_search.py` 没有 loader；依据见 [`tasks/011-backend-refactor.md`](./tasks/011-backend-refactor.md) §0.2）；**notes 乐观并发落地**（WI-5，未做）；行为不变由 1a 证明 |
| Phase 2b | 2a | 跨库搜索性能相对基准可量化改善；`_normalize_with_map` 差分测试通过 |
| Phase 3 | 2b + Track D **且 soak 门槛达标**（⬛ 2026-09-28 起 = 一批冻结条件下的 10 次全量首次通过，判据见本节 soak 小节；三路汇合，见 §9.1） | 新书完全不依赖 pickle；存量可一键迁移；**`--migrate` 原地读写，不复用摄取路径**；**DEG-S1–DEG-S4 在当时的 UI 里可见**——即 **`acceptance-p3` 组解开 skip 并绿灯**（朴素横幅形态）；真实 iframe 标注迁移 E2E 通过 |
| Phase 4A | **1b 的 G1**（用例完成门；不必等 G2/soak） | wheel 内容测试通过；settings 与 library 切换后 `baseline-1b` **零改动**全绿；**4A.4 另需 `acceptance-4a4` 组解开 skip 并绿灯**（DEG-S1–DEG-S4 改版形态）；Classic 已删除 |
| Phase 4B | Phase 3 **且** 4A.4 | 拆分后 `baseline-1b` 全绿，**唯一具名例外 W-5a**（它特征化的旧改色行为正是 4B.1 要换掉的，删除流程见[前端计划](../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md) WI-14 验收第 6 条）；**4B.1 另需 `acceptance-4b1` 组解开 skip 并绿灯**（组内容定义在 [009 §0.5](tasks/009-e2e-annotations.md)，本表不复述——这些行为本阶段才产生）；各模块 ≤400 行；依赖方向机器可验（`dependency-cruiser` 四条规则，见[前端计划](../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md) 的 WI-14）；**iframe 内部改动不超出设计规格 §6.0 允许的范围**（判据以 §6.0「判定标准（canonical）」为准的**三重断言 A/B/C**，本表不复述）；**三个浮层过 `containingBlockAncestor() === null`，且工具条位置用矩形几何断言**（4B.2 硬门槛，K3）；**K1–K6 各有一条能失败的断言**；进度值全站一致 |
| Phase 5 | 4B | 单命令进入阅读；PWA 版本切换不撕裂 |

### soak 门槛（Phase 3 专用）

§4 论证 1 的原话是「在一套**已经跑绿一段时间**的 E2E 下迁移」。这句话不量化就是空话——一套只跑过一次的 E2E 和一套跑绿两周的 E2E，保护力不是一个量级，而本仓库今天**零 CI 历史**。

> **⬛ 2026-09-28 维护者裁定：本小节的判据换成下面的「批次规则」六条，取代 R9 的数值裁定。**
> 日历跨度（≥5 个工作日）**取消**；「连续绿 ≥10 次」改为**一个批次恰好 10 次全量**，批次钉死同一
> `commit` / `suite_hash` / 浏览器 / `os` / 依赖锁；「只对受影响用例 burn-in」的作用域清零方案**否决**。
> 这是**取代**，不是悄悄放宽：R9 评审后维护者亲自裁定维持的「≥10 次 / ≥5 个工作日」（见「GSTACK REVIEW
> REPORT」的 R9 行，那一行作为历史原样保留）自本日起失效。为什么改、调研了什么、Codex 评审意见、
> 丢掉了什么保护，全部记在 [`review-soak-gate-20260928.md`](./review-soak-gate-20260928.md)——那份是
> **评审与证据记录，不是定义处**；**判据的唯一定义处是本小节**。
> [ADR-0010](../../adr/0010-test-and-ci-topology.md) 第 56 行仍引用旧数值：ADR 已 Accepted、不改正文，
> 且它自己声明 soak 规则定义在本节、不在 ADR 覆盖范围内——**以本节为准**。

~~**Phase 3 开工前，`baseline-1b` 组必须连续绿 ≥ 10 次，且跨度 ≥ 5 个工作日。**~~（⬛ 2026-09-28 被下方批次规则取代）

**Phase 3 开工前，`baseline-1b` 须在一个冻结批次里全量首次通过恰好 10 次。** 六条，全部二值可判：

1. **批次。** Phase 3 开工前，声明一个批次（批次 ID 写进台账，形式见下方「台账字段」），在**同一
   `commit`、同一 `suite_hash`、同一 Chromium 构建、同一 `os`、同一依赖锁**上，用
   `scripts/soak_run.py --append` 连续跑 `baseline_1b` 全量**恰好 10 次**。每次须**首次**通过全部预期用例
   （条数以 `EXPECTED_BASELINE_ITEMS` 为准）：无 skip / xfail / 条数偏差 / 重试。每次保留日志。
   **不再有日历跨度要求。**
   （⬛ 2026-09-30：放行 012 的那一批必须跑在 012 开分支的那个 `commit` 上，见下方「[012 开工核验](#012-开工核验2026-09-30-维护者裁定)」。）
2. **红灯。** 批次中任一次红：入账、批次终止。按 [012 门槛 R](./tasks/012-storage-format.md) 的口径查根因
   （产品缺陷 / 测试缺陷 / 环境）并修复，定向复核后**从第 1 次重开新批次**。环境故障或不完整运行不计数，
   但同样终止批次、入账、查明后再开。**不得跳过任何一次尝试去挑 10 次绿。**
3. **何时重开批次。** 批次内 `commit`、`suite_hash`、浏览器、`os`、依赖锁任何一项不同，就不是同一批——
   二值可判，无需判断「改动大不大」。定向重复（如 `pytest --count`）只用于归因，**不抵扣**全量次数。
4. **机制挑战闸钉到候选版本。** 最终候选 `commit` 须在干净 Linux CI 上全项首次通过（阻塞）；当前
   `suite_hash` 须完成 3 个可复现 seed 的随机收集顺序挑战（阻塞）。CPU 压力照 2026-09-24 裁定只记录不阻塞。
   三项都不计入那 10 次。条文与纪律见下方「机制挑战闸」小节。
   （⬛ 2026-09-30：「最终候选 `commit`」＝ 012 开分支的那个 `commit`，第 1 项与新批次同在其上，见「[012 开工核验](#012-开工核验2026-09-30-维护者裁定)」。）
5. **界定：一批 10/10 证明了什么、没证明什么。** 见紧下方的界定段——它原是 2026-09-18 补的「证明了什么、
   没证明什么」，2026-09-28 并入本条，推理保留，按批次规则订正了哪几条理由仍然成立。
6. **过渡。** 新规则只适用于生效后声明的批次；[`soak-log.md`](./tasks/soak-log.md) 的旧行逐行原样保留，
   **不追认任何旧行**。**先完成 2026-09-27 那次红灯的归因，再开第一批。**

> **规则 5 的展开：这道门槛证明了什么、没证明什么（2026-09-18 补；2026-09-28 并入规则 5 并订正）。**
> 一批 10/10 证明的是：**该候选版本（一个 `commit` ＋ 一个 `suite_hash`）在该运行剖面下成功了 10 次**。
> 它**不给 flaky 率上界**——10 次全绿时，单跑失败率的 95% 上界仍约 26–30%，而各跑之间相关（同机、同日、
> 同缓存）时更弱；它**也不证明迁移安全**：Phase 3 仍须独立满足原地迁移、用户数据字节不变、真实 iframe
> 标注迁移 E2E、提交点前后的真 SIGKILL 崩溃注入矩阵（见 [012 出口闸](./tasks/012-storage-format.md)）。
>
> 2026-09-18 原文给过三条「不构成统计上界」的理由，批次规则之后逐条看：
>
> 1. ~~**被测对象在变。** 下方「三类清零触发器」明写「**明确不清零的：生产代码变（`commit` 变）**」——十次运行测的不是同一份生产代码，一个固定的失败概率 p 在这里根本不存在。~~
>    ⬛ 2026-09-28：**已由规则 3 堵上**——批次内 `commit` 唯一。
> 2. ~~**运行剖面也在变。** 依赖版本不进 `suite_hash`（[`soak-log.md`](./tasks/soak-log.md) 表头明写把 `pyproject.toml` 排除在外），所以十次之间依赖可以漂。~~
>    ⬛ 2026-09-28：**已由规则 1 / 3 堵上**——依赖锁在批次内固定（`uv.lock` 与 `package-lock.json` 都进版本库，
>    `commit` 固定即锁固定）。`suite_hash` 仍不含 `pyproject.toml`，这一点不变。
> 3. **可选停止（optional stopping）。** 原规则是红了清零重计，但**不要求根因修复**。只要单轮通过概率大于零，无限重试最终几乎必然攒出 10 连绿——最后那 10 次是**事后选出的窗口**，不是预先指定的样本。
>    ⬛ 2026-09-28：**被规则 2 收窄，未消除**——红必查根因、不得跳过尝试，但「一批接一批跑到有一批全绿」
>    在形式上仍是可选停止。
>
> 因此本节**不给任何数值化的失败率估计**（上面那个 26–30% 是「即便 i.i.d. 也只能说到这里」的上限说明，
> 不是估计）。审计阶段曾按二项模型算过一个，**已撤回**：它的独立同分布前提不成立，写出去只是虚假精确性。
> 这道门槛买的是**流程纪律**（冻结的候选版本 ＋ 红必查根因），不是统计推断。
> ~~**数值与判据不因此变动**——≥10 次 / ≥5 个工作日、跨度按台账首行与第十行的日期算，一个字不动；这里加的只是界定。~~（⬛ 2026-09-28 被批次规则取代）

**术语注（2026-09-28）**：业界「soak test」指长时耐久 / 负载测试；本门槛实为 **burn-in**（对一个冻结候选
版本重复跑满 N 次）。名字保留——`soak_run.py`、`soak-log.md` 与本小节标题都不改名，避免连锁改动。

**丢掉的保护，如实写下（2026-09-28）**：「时间维度的不稳定」（缓存、时区、依赖漂移）不再有专门的门槛覆盖，
作为**已知剩余风险**接受。理由：改基到本地单机后，这一半保护本来就只剩日历时间（见下方 2026-08-24 改基段）；
环境多样性由机制挑战闸的干净 Linux CI 那一项承担。

> **数的不再是主 CI 的运行，是本地全量运行——2026-08-24 改基。** 起因是全仓 CI 统一改为**仅发版触发**（`release.published` ＋ `push.tags`，日常 push 不跑）。原文数「主 CI 连绿 10 次」在那条策略下等于要求 5 个工作日内发 10 次版：**门槛不是变严了，是变得不可达**。
>
> ~~**数值一个不动**——≥10 次 / ≥5 个工作日是 R9 评审后用户亲自裁定维持的（见「GSTACK REVIEW REPORT」的 R9 行），改基不碰它。~~（⬛ 2026-09-28：数值已被本小节开头的批次规则取代，见那里的裁定注。）换的只有计数基准：
>
> - 每次 `baseline-1b` 全量运行往 **`soak-log.md`** 追一行，字段见下方「台账字段（canonical）」。~~跨度按台账首行与第十行的日期算。~~（⬛ 2026-09-28 跨度取消）该台账由 009 建，它是 `baseline-1b` 的产物之一。
> - ~~「连续」的清零规则不变：中途任何一次红清零重计，flaky 与 broken 仍不做区分。~~（⬛ 2026-09-28：改为批次规则 2 / 3——红终止批次且必查根因。）
>
> **必须写明丢了什么**：本地计数丢掉的是「**独立、干净环境**」这一性质。而依赖漂移、时区、缓存这三类，正是上面「跨度条款」想逼出来的东西——它们恰恰在同一台机器上最不容易复现。所以改基之后，跨度条款只剩「日历时间」这一半效力，「环境多样性」那一半没有了。改基本身是**已知代价，不是疏漏**。
> （⬛ 2026-09-28：剩下的「日历时间」那一半随跨度条款一并取消，作为已知剩余风险接受，见本小节开头「丢掉的保护」。）
>
> **但原文在这里承诺过一项补偿：在发版关门检查中对 `baseline-1b` 做一次全量运行。该补偿至今没有建出来。**（**⚠️ 本段是 2026-09-18 的核查快照，已过期：2026-09-20 以 `tests.yml` 的 `e2e` job 兑付，见 [`tasks/009` 欠账 #31](./tasks/009-e2e-annotations.md)。它提供的是独立的干净 Linux 信号，结果记进 `soak-log.md` 的机制挑战闸表，**不进 soak 台账**——一行 linux 记录按下方清零规则第 2 条会把计数清零（⬛ 2026-09-28 批次规则 3：读作「不是同一批」，混进批次窗口即判 FAIL）。**）2026-09-18 在 `e7c4890` 上逐文件复核：
>
> - `.github/workflows/tests.yml`（101 行）只有一个 job：`unit`（`:43`）。步骤是 ruff / mypy / `pytest tests/unit tests/contract` / 覆盖率门禁，**不起浏览器**。
> - `.github/workflows/lint.yml`（79 行）两个 job：`contracts`（`:36`）、`wheel`（`:59`）。
> - 全仓 workflow **没有任何一步跑 Playwright、e2e lane 或 `baseline-1b`**。`grep -rn e2e .github/workflows/` 命中 **4 行、分属两件事**，都不是在跑它：`lint.yml:20/48–49` 的 `scripts/lint_e2e_selectors.py`（静态选择器 lint，`:20` 是讲它的注释），以及 `tests.yml:19` 的一句注释——那句讲的是**本地** tdd-guardian 三条 lane 的触发时机（`.claude/tdd-guardian/config.json` 里 e2e lane 的 `gateOn: ["push"]`），不是 CI job。
>
> 所以如实的陈述是：**在那道发版关门检查真的建出来之前，「环境多样性」那一半没有任何补偿**——十次绿全部来自同一台开发机的同一个运行剖面。**这是一个已知缺口，不是一项已生效的控制**，读到这里的人不要把它当成已有的保护。已记入[`tasks/009` 跨波欠账 #31](./tasks/009-e2e-annotations.md)——**2026-09-19 已定方向：建 CI e2e job，本段承诺不删。** 该 job 跟着现有的「仅发版 ＋ `workflow_dispatch`」触发口径走，不新增触发器；兑付方（谁做、落在哪个 WI）仍是**待定**。形状、验收改动与「靠手点 dispatch 补台账行」的理由都记在那一行，此处不重述。

> 数的只是 `baseline-1b`。其余组在 Phase 3 之前尚未激活（它们测的行为还不存在），把它们算进来就会让 soak 门槛永远无法达标——分组定义见 [`tasks/009-e2e-annotations.md`](./tasks/009-e2e-annotations.md) §0.5。

- ~~「连续」指中途任何一次红都清零重计——flaky 与 broken 在这里不做区分，一条会偶发失败的 E2E 当不了数据迁移的验收基准。~~（⬛ 2026-09-28 被批次规则 2 取代：红仍然终止批次、flaky 与 broken 仍不靠重跑翻盘，但红必查根因后才重开。）
- ~~跨度条款是为了逼出**时间维度**的不稳定（缓存、时区、依赖漂移、并发），这类问题在同一天连跑十次是照不出来的。~~（⬛ 2026-09-28 跨度条款取消，这类不稳定作为已知剩余风险接受，见本小节开头。）
- 这道门槛只卡 Phase 3。Phase 4A 不受影响，可继续并行推进。

#### 台账字段（canonical）＋ 什么会让计数作废

> **本小节 2026-08-24 补，起因是 Codex 复核指出「10 次绿」在原规则下可以由互不可比的十次拼出来。**
> 原文只定义了「红清零」，没定义**被测对象变了算不算清零**。于是下面这条路径是合法的：跑三次绿 →
> 改掉两条 flaky 断言 → 再跑七次绿 → 宣布达标。**十次绿里没有任何两次测的是同一套东西**，而门槛
> 想买的恰恰是「同一套东西稳定了一段时间」。这是规则漏洞，不是执行者的问题。

> **⬛ 2026-09-28 起本小节按批次语义读**（批次规则见本小节上方「soak 门槛」开头）。「计数作废」
> 现在的意思是「**不是同一批**」：一批要么 10/10 全绿、同一 `commit` / `suite_hash` / 浏览器 / `os` / 依赖锁，
> 要么不算。下面八列不变；多出的只有**批次 ID**：
>
> - **批次 ID** —— 每批开跑前在 `soak-log.md` 表头的「批次声明」里写一行：批次 ID、起始 `ts_utc`、
>   以及该批钉死的 `commit` / `suite_hash` / `browser` / `os`。一批的数据行 = 声明起始时刻起的前 10 行。
>   **暂不做成第九列**：八列同时是代码契约——`scripts/soak_run.py` 的 `CANONICAL_COLUMNS` 按八列写行，
>   `tests/unit/test_soak_log_contract.py` 断言表头逐字等于这八列。加列连同「核对 10 条同批记录」的判决命令
>   是一项实现工作（走 tdd-guardian），见 [评审记录 §5 末尾](./review-soak-gate-20260928.md)；落地之前以表头声明为准。
> - **依赖锁** 不单设列：`uv.lock` 与 `package-lock.json` 都进版本库，`commit` 固定即锁固定。

**台账字段**——`soak-log.md` 每行八列，缺一列该行不计数：

| 列 | 含义 | 怎么取 |
|---|---|---|
| `ts_utc` | UTC 时间戳 | `date -u +%Y-%m-%dT%H:%M:%SZ` |
| `commit` | 被测生产代码的 sha | `git rev-parse --short HEAD` |
| `result` | `green` / `red` | e2e lane 退出码 |
| `duration_s` | 单次全量时长（秒） | 运行器输出 |
| `suite_hash` | **`baseline-1b` 组用例 ＋ harness 配置的内容哈希** | 见下方口令，**这一列是 ① 的执行机制** |
| `browser` | 浏览器标识与版本，如 `chromium-1140` | `npx playwright --version` ＋ 浏览器构建号 |
| `os` | 运行平台，如 `darwin-25.3.0` | `uname -sr` |
| `log` | 该次运行的日志/报告路径 | 运行器产物目录 |

**三类清零触发器，全部二值可判，不需要任何人判断「这次改动算不算大」：**

> ⬛ 2026-09-28：三类触发器现在读作「**不是同一批**」（批次规则 3）——第 1、2 类使当前批次失效、须在新值上
> 另开一批；第 3 类终止批次、查根因后重开（批次规则 2）。另**新增第 4 类：`commit` 变了**，见列表后的订正。
> 下面的原文保留，「清零」一词按此读。

1. **`suite_hash` 变了** —— 清零。哈希覆盖 `baseline-1b` 组的用例文件、Playwright 配置、以及该组用到的 fixtures——**`tests/fixtures/epub_corpus.py` 在覆盖范围内**（2026-09-01 裁定）。**改一条断言、修一条 flaky、动一次 webServer 探针，都从零重数。**

   > **`epub_corpus.py` 为什么纳入，代价是什么。** 它是 `build_epub2` / `build_epub3` / `build_cjk` 三个构造器的所在地，`baseline-1b` 的每一条用例都读它造出来的书。改一个字符，全组用例的被测输入就变了——把它排除在外，等于允许「不动用例、只动语料」地重塑十次运行的含义，而门槛正是为了防这个。
   >
   > **代价是实的，不藏**：这个文件同时被 `tests/unit` 用着，因此**一次纯单测目的的构造器改动也会清零 soak 计数**。这是「宁可多清零，不可假计数」的一侧误差，接受。代价必须写进 `soak-log.md` 的表头，和取哈希的命令写在一起——否则第十次运行前一天有人为了一条单测加个 `build_epub2(lang=...)` 参数，计数归零时没人知道为什么。
2. **`browser` 或 `os` 变了** —— 清零。浏览器升级换的是被测运行时。
3. **任意一次 `red`** —— 清零（原有规则，不变）。

~~**明确不清零的：生产代码变（`commit` 变）**。那正是这道门槛要观察的信号——E2E 在一份持续演进的代码上连续保持绿，才是它的全部意义。~~同理，**其余 skip 分组的用例怎么改都不清零**，它们不在 `suite_hash` 的覆盖范围里。

> **⬛ 2026-09-28 订正：`commit` 变了 ⇒ 不是同一批（第 4 类触发器）。上面那句被划掉的原文反转。**
> 原文让 `commit` 在十次之间自由变，是因为一轮计数要攒数周、跨 5 个工作日，钉死 `commit` 就等于冻结全部开发。
> 批次规则下一批只要 10–15 分钟（68 条、单跑约 1 分钟），**钉死 `commit` 几乎不花钱**，换来的是
> 「十次测的是同一份候选代码」——原文界定段理由 1（被测对象在变）由此堵上。「E2E 在持续演进的代码上保持绿」
> 这层观察并没有丢：它由每次 push 触发的本地 `e2e` lane 与每一批的红灯归因承担，只是不再由「十次拼在一起」来证明。
> 开发期间生产代码照改；改了之后，Phase 3 要的是**在最终候选 `commit` 上重跑一批**。

> **这条规则很严，严是故意的，但它必须留一个出口，否则会重蹈「改基前不可达」的覆辙。** 出口就是
> 上面那句「其余分组随便改」：soak 期间你仍然可以推进 009 的其他组、可以推进 011、可以改生产代码。
> **被冻的只有 `baseline-1b` 这一组的用例本身**——而它到那时本来就该是冻结状态：1b 的出口条件已经
> 要求它「连续 3 次全量运行零 flaky」，还在频繁修改它，说明 1b 根本没出门。
>
> **已知代价，写下来**：如果 soak 期间发现 `baseline-1b` 有条用例写错了，你只有两个选择——带着错误
> 用例跑完十次，或者改掉它并从零重数。**没有第三条路，也不应该有**：能被「就改这一点点」绕过的门槛
> 不是门槛。
>
> ⬛ 2026-09-28：这段代价按批次规则变小了——「改掉它并从零重数」现在是「改掉它，在新 `suite_hash` 上
> 重开一批」，约 10–15 分钟，外加机制挑战闸第 3 项（随机收集顺序）对新 `suite_hash` 重跑（批次规则 4）。
> 「没有第三条路」照旧：带错用例跑，或改掉并重开一批。

**`suite_hash` 的取法**（一条命令，写进 `soak-log.md` 表头，运行器直接调）：

```bash
# baseline-1b 组用例 + harness 配置 + fixtures 的内容哈希，前 12 位
{ git ls-files -s \
    tests/e2e/baseline-1b playwright.config.* tests/e2e/fixtures \
    tests/fixtures/epub_corpus.py \
  | git hash-object --stdin; } | cut -c1-12
```

> 路径以 009 落地时的实际目录为准；**若目录名不同，改的是这条命令，不是规则**。命令本身连同它算出的
> 第一个哈希值一起写进 `soak-log.md` 的表头，这样台账自带复核方式。表头还要抄上上面那条代价——
> **`epub_corpus.py` 被单测改动也会清零**——它是这条命令唯一一个「不属于 e2e 目录、却在覆盖范围内」
> 的路径，不写下来就会被当成误加进去的。

> 来源：2026-08-16 eng-review 的 Outside Voice。Codex 主张把 Phase 3 整体挪到 4B 之后，理由之一是「Phase 1 的测试尚无 CI 历史，保护力未经检验」。排序未采纳（见 §4），但这半句成立，转为本门槛。

#### 012 开工核验（2026-09-30 维护者裁定）

> **⬛ 2026-09-30 维护者裁定：012 开工一律要在最终候选 `commit` 上跑一批新的。本段是这条规则的唯一定义处**，
> 012 §1 / §4 门槛 F、进度盘、`soak-log.md` 表头与 `plan-and-branch-map` skill 都只链接到这里。
>
> **起因（定义缺口）**：批次规则 1 / 3 把一批钉在一个 `commit` 上（上方订正注：「Phase 3 要的是**在最终候选
> `commit` 上重跑一批**」），而 [012 门槛 F](./tasks/012-storage-format.md) 只比 `suite_hash`。两者合读，
> 「在旧 `commit` 上通过的一批 ＋ `suite_hash` 没变」是否放行 012，条文给不出唯一答案。本裁定取严的一侧：
> 一批只要 10–15 分钟，而从 B1 的 `commit` 到 012 开工之间还要合入冻结集欠账窗口与 `018` 两批生产代码。
>
> **核验内容**，全部落在 **012 将要开分支的那一个确切 `commit`**（下称「最终候选」）上：
>
> 1. **新批次，无条件。** 在最终候选上声明并跑一批 10/10（批次规则 1–3），**不论 `suite_hash` 自上一次通过批次以来变没变**。
>    更早通过的批次（含 B1）照旧是通过的记录，但**不再单独放行 012**。
> 2. **机制闸第 1 项**（干净 Linux CI）在**同一个** `commit` 上首次通过（批次规则 4，本裁定把「最终候选」钉成这一批的 `commit`）。
> 3. **机制闸第 3 项**只在 `suite_hash` 自它上一次通过以来变了时重跑（纪律 4 不变）。第 2 项照 2026-09-24 裁定只记录。
> 4. **012 门槛 F** 拿 012 开工 `commit` 的 `suite_hash` 与**第 1 条那一批**的 `suite_hash` 比。
>
> 四项全过，012 才能开分支；任何一项之后又有新 `commit` 进了 `master` 而 012 要从新 `commit` 开，四项在新 `commit` 上重做。
> 核验在执行顺序里的位置归[进度盘](../20260824-frontend-backend-plan-progress.md)；结果只记在 [`soak-log.md`](./tasks/soak-log.md)。
>
> **连带**：[018 §4 门槛 10](./tasks/018-library-routes.md)（「合入后在 `master` 上跑一次 `--append`」）被本裁定取代——
> 单独一行本来就不计入任何批次，它想证明的「合入头没把 `baseline_1b` 弄红」由第 1 条那一批覆盖。

#### 机制挑战闸（Phase 3 阻塞项——第 2 项自 2026-09-24 起除外；三项都不计入那 10 次）

> **2026-09-18 补。** 上面那段「证明了什么、没证明什么」划出了 soak 计数的边界：它是**一个本地运行剖面**
> 下的记录。这一小节补的是另一半——在**冻结的 `suite_hash`** 上主动改变条件各跑一次，看这套用例是不是
> 只在那一个剖面下才绿。**三项全是阻塞性的**：任何一项不过，Phase 3 不开工。
> （⬛ 2026-09-24：**第 2 项已经维护者裁定降为不阻塞的记录项**，第 1、3 项照旧阻塞——裁定见纪律 3 下方，不是悄悄放松。）

| 场景 | 固定什么 | 通过条件 | 失败后果 |
|---|---|---|---|
| 干净 Linux / CI 环境 | 锁定 lock 文件与 Chromium 版本，两者连同结果一并记录 | 全项**首次**通过 | **阻塞 Phase 3** |
| CPU 压力下 | 压力生成命令与持续时间写进文档，可原样复现 | 全项**首次**通过（**2026-09-24 起只记录，不作放行判据**） | ~~阻塞 Phase 3~~ → **不阻塞**（2026-09-24 维护者裁定降级，见纪律 3 下方）；结果照记、照分类 |
| 随机化 pytest 的收集顺序 | 记录插件版本与**可复现的 seed** | 3 个 seed 全绿 | **阻塞 Phase 3**；失败 seed 必须可复现 |

四条纪律，缺任意一条这张表都会退化成没人看的死栏位：

1. **这三次不计入那 10 次。** 它们**改变了抽样条件**——干净环境、CPU 压力、收集顺序都不是 soak 计数的那个运行剖面。混进去等于拿不同条件下的运行拼出一个「连续」，正是上方「台账字段（canonical）」要堵的同一个洞。
2. **重试通过 ≠ 绿。** 通过条件写死为「**首次**通过」。重试只能用来**分类**（flaky 还是 broken），不能用来翻盘。Playwright 自己也把「首次失败、重试通过」标成 flaky 而非 passed，这里取同一口径。
3. **失败会阻塞，不是「记录下来就算」。** 三项各自独立阻塞 Phase 3 开工——一道不挡人的闸等于没有闸。**唯一的例外是第 2 项，它是被维护者明文裁掉阻塞的（2026-09-24，见紧下方），不是被执行者悄悄放宽的**；第 1、3 项仍按本条阻塞。
4. **何时重跑**：`suite_hash` 变了，或 harness 变了。与 soak 计数的清零触发器同源，不另立判据。

> **⬛ 2026-09-28（批次规则 4）：阻塞的两项钉到候选版本上。** 第 1 项（干净 Linux）须对 **Phase 3 的最终候选
> `commit`**——即通过的那一批所跑的 `commit`——首次通过；第 3 项（随机收集顺序，3 个可复现 seed）须对**当前
> `suite_hash`** 成立。所以第 1 项的重跑时机比纪律 4 多一条：**候选 `commit` 变了就要重跑**（第 3 项仍按纪律 4，
> 只跟 `suite_hash` 走）。此前对 `1e868c7bf811` 的第 1 项 PASS 跑在更早的 `commit` 上，**不自动覆盖**最终候选。
> 第 2 项（CPU 压力）的 2026-09-24 裁定不变。三项都不计入那 10 次（纪律 1 不变）。
> ⬛ 2026-09-30：「通过的那一批」读作 012 开工时在最终候选上新跑的那一批，见上方「[012 开工核验](#012-开工核验2026-09-30-维护者裁定)」。

> **⬛ 2026-09-24 维护者裁定：第 2 项（CPU 压力下）降为不阻塞的记录项。不删。**
> 压力生成命令与复现方法原样保留、照样可跑；跑出的结果照记进 soak-log、照分类，只是不再挡 Phase 3。
>
> **理由。** 第 2 项要证明的性质是「产品在 CPU 争用下不撒谎」——不把一次失败的写入显示成成功。
> 2026-09-23 的归因实验已经从另一端证明了这一点：压力下那族红是**测试夹具自伤**——冻结的
> `tests/e2e/helpers.py` 用 8 秒墙钟轮询 `notes.json`，轮询期间浏览器的写请求出不了门，
> 轮询一超时请求才上线，服务端毫秒级回 2xx；产品侧没有一例被吞掉的失败。而这个压力剖面
> （`ncpu` 个忙等压在 `ncpu` 核上 ＝ 2 倍超订）量的是浏览器在超订下的调度，不是产品。
> 剩下的缺陷在冻结集里，修它就清零 soak 计数；这笔修复立为
> [009 欠账 #49](./tasks/009-e2e-annotations.md)，等冻结集下一次不得不重置、或笔记保存代码被改动时
> 一并付，付时把第 2 项重跑一次记档。**这是降级，不是通过**——本闸从未判第 2 项 PASS。
> 证据、逐跑表与推理的唯一定义处是 [`tasks/soak-log.md` 的「第 2 项归因」一节](./tasks/soak-log.md)，此处不重述。
>
> **连带后果**：soak 计数~~（≥10 次 / ≥5 个工作日）~~一字不动，**仍阻塞 Phase 3**；台账**不清零**
> （`helpers.py` 一个字节没动）；[009 欠账 #48](./tasks/009-e2e-annotations.md)（「一次尝试 = 跑几遍」）随之失去对象，已结清。
>
> ⬛ 2026-09-28：括号里的数值已被本节 soak 小节开头的批次规则取代（soak 仍阻塞 Phase 3）。**#49 的前提随之变了**：
> 「修它就清零 soak 计数」的代价原是数周积累，批次规则下只是在新 `suite_hash` 上重开一批（约 10–15 分钟）
> 外加第 3 项对新 `suite_hash` 重跑，[012 门槛 F](./tasks/012-storage-format.md) 也同日放宽——**#49 现在可以付了**。
> 这里只记「可付」，不改 #49 的兑付安排；排期仍以 009 欠账表为准。

> **「全项」是多少条，本文不写死。** 原文写的是「67/67」；2026-09-21 冻结集改判后 baseline_1b 变成 68 条，
> 那两个 67 当场烂掉。数的唯一派生处是 `scripts/lint_e2e_groups.py` 的 `EXPECTED_BASELINE_ITEMS`
> （`scripts/soak_run.py` 也从那里取），当期值见 [`tasks/soak-log.md`](./tasks/soak-log.md)。
> 这里只定性质：**一条不少，且首次就绿**。

> **⚠️ 第 2 项的通过条件有一个已知的洞，尚未修补：「首次通过」没有定义「一次尝试 = 跑几遍」。**
> 干净 Linux 那项一次 CI run 就是一次尝试，没歧义；但 CPU 压力这项本质上测的是**分布**，n=1 的尝试不构成证据——
> 2026-09-21 实测：同压力源、同命令（`soak_run.py` 的 `LANE_ARGS`）四跑两红，而其中首跑恰好是绿的。
> 建议改成「**连续 k 次**（k=5）压力下全绿，首轮即须成立」。**这个改动没有替维护者做**：
> 动的是一道正挡着 Phase 3 的闸的通过条件，且动它的人刚好是没过这道闸的人。立为
> [009 欠账 #48](./tasks/009-e2e-annotations.md)，在它裁定之前，第 2 项按本文现有条文是字面 PASS、
> 按 soak 台账的建议记作**未过**——两者的差别就是这个洞。
>
> **⬛ 2026-09-24：这个洞随第 2 项降级而失去对象，#48 已结清（moot）。** 一道只记录、不放行的闸
> 不需要「首次通过」的精确定义。**若日后第 2 项恢复阻塞，这个洞随之复活，须先补上再谈判决。**

> **为什么写「随机化收集顺序」而不是「换随机种子」**：后者太含糊——若被测系统根本不消费那个随机源，换了等于没换，这一栏的信息量是零。这里要照的是**用例间顺序依赖**这一类缺陷，所以判据落在 pytest 的收集顺序上，并要求 seed 可复现、失败能原样重放。

> **执行结果不在这里。** 本小节是判据的定义处；三项各跑了什么、结果如何、失败 seed 是哪个，唯一定义在 [`tasks/soak-log.md` §机制挑战闸执行记录](./tasks/soak-log.md)。**2026-09-21 起以「对新冻结值 `1e868c7bf811` 的重跑」为准**（旧结果随 `suite_hash` 变更按纪律 4 全部作废）：
> 第 1 项干净 Linux **PASS**、第 3 项随机顺序 **PASS**、第 2 项 CPU 压力 2026-09-23 实测 FAIL 后于
> **2026-09-24 经维护者裁定降为不阻塞的记录项**（见纪律 3 下方的裁定）——
> **机制挑战闸不再阻塞 Phase 3 / 012；soak 计数那道门槛仍然阻塞**（进度只在 soak-log 里现算，本文不写）。
> ⬛ 2026-09-28：按批次规则 4，第 1 项须对最终候选 `commit` 重新首次通过——上面的 PASS 跑在更早的 `commit` 上，
> 到第一批通过时要对那一批的 `commit` 再跑一次；第 3 项只要 `suite_hash` 仍是 `1e868c7bf811` 就继续有效。

---

## 8. 风险与对应

| 风险 | 对应 |
|---|---|
| 迁移引入回归（尤其标注锚定与搜索高亮） | Phase 1 安全网先行；`annotations.js` 放在最后迁移 |
| 存量书库 pkl 不兼容 | 双写 + 回退读取 + `--migrate` 命令，跨版本过渡 |
| **有人直接把原型 React 代码搬进生产** | 翻译规则写死在 `designs/reader-pro-next/README.md`，并在原型显眼处标注其性质 |
| **testid 定名拖到 1b 之后** | 头号返工源。0.5 是 Phase 0 的硬门槛，不得顺延 |
| **Phase 3 与 4B 抢跑** | §4 的串行是硬约束；4B 的进入条件写死为"Phase 3 完成" |
| **外壳重写静默打断标注** | K1–K6 各配一条**能失败**的断言，而不是断言"元素存在"。K3（`position: fixed` 被祖先 transform 击穿）与 K6（URL 回退解析出错章号）最隐蔽 |
| **降级状态没有 UI** | 写成 Phase 3 的退出门槛，先用朴素横幅落到旧模板，Phase 4 再按设计重做 |
| **API 悄悄改形状导致两条线互锁** | 合同 3 的加法式演进；契约测试是可执行的护栏 |
| Vite 构建破坏"无构建即改即用"的开发体验 | `vite dev` 提供 HMR，比现状更好；产物提交策略已定（提交 dist，见附录 A 的 A3） |
| Chroma 相似度换算假设（`1 − L2` clamp）与实际距离度量不符 | Phase 1 补一条针对已知语料的检索质量测试固化现状 |
| **文档互相复述导致漂移** | 本文顶部的权威范围表；每条事实只有一个家；**任何文档都不写代码行号** |
| 单人维护者时间碎片化 | 三条线开工时互不阻塞；每个子阶段独立可交付、可暂停。**但三条线都在 Phase 3 汇合**（§9.1），碎片化的代价会在那里一次性结算 |
| **1b / Track D 被排到后端线之后** | 二者都是 Phase 3 的前置，~~且 1b 的 soak 是**日历时间**、补不回来~~（⬛ 2026-09-28 日历跨度已取消，见 §7）。§9.1 把它们标为「Phase 0 一结束就动」 |

---

## 9. 里程碑与分支（唯一真相源）

沿用 `{number}-{short-name}` 惯例。**这是全仓库分支编号的唯一定义处。** 拆分成前后端两份计划、又把后端两份合并成本文之后，**编号表仍然只有这一份**，前端计划引用本表、不另建编号。

「归属」列指该分支的**任务展开写在哪个计划里**：**A** = 本文件夹 `20260816-tech-stack-migration/`；**B** = [`20260817-frontend-ui-refactor/`](../20260817-frontend-ui-refactor/README.md)。

| 里程碑 | 内容 | 分支 | 归属 |
|---|---|---|---|
| M0 | Phase 0 合同与止血 | `007-hygiene-and-contracts` | A（0.4 / 0.5 / 0.8 同时是 B 的前置契约） |
| M1 | Phase 1a 测试 + CI + API 冻结 | `008-test-safety-net` | A |
| M1b | Phase 1b Playwright E2E | `009-e2e-annotations` | A（B 的测试矩阵引用其用例 ID） |
| MD | Track D 设计补齐（仅改 `designs/` 与规格） | `010-design-degradation-states` | **B**（WI-1 – WI-8） |
| M2 | Phase 2a + 2b | `011-backend-refactor` | A |
| M3 | Phase 3 存储迁移 | `012-storage-format` | A |
| M4a | Phase 4A 底座 + settings + library | `013-ts-frontend-shell` | **B**（WI-9 – WI-13） |
| M4b | Phase 4B 阅读器 ＋ 书库侧延后验收 | `014-ts-frontend-reader` | **B**（WI-14 – WI-19，含插入项 WI-16b） |
| M5 | Phase 5 launch + PWA | `015-launch-experience` | A（`reader3 launch`；⬛ 2026-10-02：[任务文件](./tasks/015-launch-experience.md)已写，§6 全部裁定（Q16 归 WI-20），分支未开；数据家规则见 [ADR-0017](../../adr/0017-data-home-resolution.md)，Proposed）＋ **B**（PWA，WI-20） |
| M1b-债 | 欠账 #22 字号/间距慢一拍（合入 009 后、冻结 G2 前的一条独立小分支） | `016-settings-apply-order` | A（兑付记在 [`tasks/009` 欠账表 #22](./tasks/009-e2e-annotations.md)，不另开 task 文件） |
| M2-债 | 011 合入后的全量审计欠账：44 条 findings 中判为 must / should 的 22 条 | `017-audit-followup` | A（任务展开写在 [`tasks/017-audit-followup.md`](./tasks/017-audit-followup.md)） |
| M4a-债 | 013 延后的后端半边中**不依赖 012 存储格式**的四条（#51 / #56 / #58 / #53）＋ 每书写协调契约 ＋ 009 欠账 #31 收尾对账（job 已于 2026-09-20 建成并结清；018 只核验合并头与改掉过期措辞） | `018-library-routes` | A（[任务文件](./tasks/018-library-routes.md)，2026-09-26 评审通过；🚧 2026-09-30 分支已开、进行中；⬛ 2026-10-02：WI-1 – WI-3 已合入（PR #33，`c08317b`），~~WI-4 – WI-8 未做~~，合入记录见任务文件 §8；⬛ 2026-10-07：✅ 已合入，第二段 WI-4 – WI-8 为 PR #37，合并 commit `74384b1`，分支尖 `b6025ba`；兑付 009 #53 / #56 / #58，立 009 #72 / #73；分拆裁定见 [`tasks/012` §6 D1](./tasks/012-storage-format.md)） |
| M1b / M2-债 | 冻结集欠账窗口：009 #49 / #50 / #62 ＋ 017 finding #10（2026-09-30 分配；兑付记在 009 / 017 各自的表上，不另开 task 文件） | `019-frozen-set-debts` | A |
| ⟂ | `Reader3Epub.getDebugState()` 只读状态观测面（2026-09-30 分配） | `020-debug-state` | 独立计划 [`20260928-debug-state-getter.md`](../20260928-debug-state-getter.md) |
| ⟂ | E2E 互斥锁改为 fcntl 包装：e2e lane 的 `command` 经 `scripts/e2e_lock.py` 运行，进程退出即由内核释放，不再手删 mkdir 锁（2026-10-01 分配；不碰冻结集，不另开 task 文件） | `021-e2e-lock` | A |
| ⟂ | 功能台账 Summary 表 Evidence 列校验：`scripts/build_feature_ledger.py` 解析了该列却从不校验，补上校验并按规则 7 订正不合格行（2026-10-01 分配；只碰该脚本、其单测与台账数据，不碰冻结集，不另开 task 文件） | `022-ledger-evidence` | A |
| M1b-债 | 012 开工核验前的冻结集准备：009 欠账 #65 / #66 / #67 / #68（2026-10-01 分配；本轮冻结集唯一 owner；兑付记在 009 欠账表，不另开 task 文件；合入排在 `018` 之后，rebase 时重数分组常量；⬛ 2026-10-02：✅ 已合入，PR #34，合并 commit `cc8ad27`，兑付见 009 欠账表 #65–#68） | `023-frozen-set-prep` | A |
| ⟂ | 012 Q2 提交机制原型：持久化恢复日志 vs generation 目录 ＋ 指针原子换，崩溃注入对比，顺带给 Q8 建议（2026-10-01 分配；产物只在 `tasks/evidence/q2-commit-prototype/`，不进 `src/`，不写裁定格与 ADR，不另开 task 文件；⬛ 2026-10-02：✅ 已合入，PR #35，合并 commit `94dd1e0`；裁定见 [012 §6 Q2](./tasks/012-storage-format.md) 与 ADR-0016） | `024-q2-commit-prototype` | A |
| ⟂ | `verify-reader3` 的控制 CLI 与 Feature Map：`.claude/skills/verify-reader3/scripts/control.py`（仅标准库，每条命令输出一个 JSON 信封）取代三个 shell 脚本，按 `F-NNN` 建 `references/features/`；沙箱内活体验证，不读真实 `books/` 与 `config/ai_settings.json`（2026-10-02 分配；只碰该技能目录、`tests/unit` 下它的单测、`.gitignore` 一行与台账 F-018 的 Confirm 措辞；不进 `src/`，不碰冻结集，不另开 task 文件；⬛ 2026-10-06：✅ 已合入，PR #36，合并 commit `55da172`，分支尖 `b133ea1`；立账 009 #70 / #71，台账 F-018 与 2026-10-03 / 2026-10-04 审计条） | `025-verify-control` | A |

M1b 与 MD 可与 M1/M2 交错推进；M4a 可与 M2/M3 交错推进；**M3 与 M4b 严格串行**。

`016` 不是新里程碑，是 M1b 的欠账兑付：它必须排在 **009 合入之后、G2 冻结之前**，因为修好 #22 会让 `baseline_1b` 的 R-6a 转红、`suite_hash` 再变一次——顺序理由见 [进度盘](../20260824-frontend-backend-plan-progress.md)。**已于 2026-09-06 合入（PR #21，合并 commit `770e5ca`），当天冻结 G2，这条顺序兑付完毕。**

`017` 与 `016` 同类：不是新里程碑，是 **M2 的欠账兑付**。011 于 2026-09-22 合入 master
（PR #22，合并 commit `4128221`）之后对该 PR 做了一次全量审计，44 条 findings 按
[`audit-findings-triage`](../../../.claude/skills/audit-findings-triage/SKILL.md) 复核并分桶，
must / should 两桶共 22 条落在本分支。**它从 `master` 开、不回 011**——分支已经合了，
再往上加提交只会让 master 与它分叉。分桶结果与逐条理由在 `.cc-suite/audits/` 下的 findings 文件里，
而那个目录在 `.gitignore:62` 上、不进版本库，所以**能进仓库的那一份事实写在
[`tasks/017-audit-followup.md`](./tasks/017-audit-followup.md)**，不要只依赖 findings 文件。

`018` 同类：不是新里程碑，是 **M4a（013）延后到后端的欠账兑付**。2026-09-26 用户裁定 D1
（Fable 子代理裁定 ＋ Codex 复核后的修正版）把原本全部挂给 012 的 #51–#53、#56–#58 拆开：
**不依赖新存储格式**的 #51 / #56 / #58 / #53 连同一份每书写协调契约进 `018`，~~**在 soak 等待期内、
012 之前**~~**在 012 之前**做完并合入，012 在它之上开工（⬛ 2026-09-30：soak 已改批次规则、不再有「等待期」；
018 排在冻结集欠账窗口之后，执行顺序只在[进度盘](../20260824-frontend-backend-plan-progress.md)）；**验收写死要新格式**的 #57（上传后按新格式落盘）与
**要 generation swap** 的 #52 留在 012 的末波。裁定理由与逐条依赖核对只写在
[`tasks/012` §6 D1](./tasks/012-storage-format.md)。~~`018` 的合入同样不得动冻结集 8 条路径——
它跑在 `master` 上，改一个字节就清零 soak。~~（⬛ 2026-09-28：随 012 门槛 F 放宽，018 碰冻结集不再禁止，
代价是 012 开工前要在新 `suite_hash` 上重跑一批；判据见本文 §7 与 [012 §4 门槛 F](./tasks/012-storage-format.md)。）兑付方改写是 [018 WI-1](./tasks/018-library-routes.md)（一个 commit）；~~在它合入之前 009 表仍写 012，以本段为准。~~（⬛ 2026-09-30：已由 [018 WI-1](./tasks/018-library-routes.md) 改完，009 表四行兑付方列写 `018-library-routes`。）

**后端分支**的任务清单放在本文件夹的 `tasks/{分支名}.md`，不写进本文。今天存在~~七个~~八个（⬛ 2026-10-02：加 015 的 CLI 半边）：
[`007-hygiene-and-contracts.md`](./tasks/007-hygiene-and-contracts.md)、
[`008-test-safety-net.md`](./tasks/008-test-safety-net.md)、
[`009-e2e-annotations.md`](./tasks/009-e2e-annotations.md)、
[`011-backend-refactor.md`](./tasks/011-backend-refactor.md)、
[`012-storage-format.md`](./tasks/012-storage-format.md)（~~骨架，2026-09-26~~ ~~⬛ 2026-09-30：评审进行中，Q7+ 待裁；分支未开~~ ⬛ 2026-10-02：评审完成，Q1–Q13 全部裁定；分支未开）、
[`017-audit-followup.md`](./tasks/017-audit-followup.md)、
[`018-library-routes.md`](./tasks/018-library-routes.md)（~~骨架，2026-09-26~~ ~~⬛ 2026-09-30：评审通过、待开工~~ 🚧 2026-09-30：分支已开、进行中；⬛ 2026-10-02：WI-1 – WI-3 已合入 PR #33，余下 WI-4 – WI-8）、
[`015-launch-experience.md`](./tasks/015-launch-experience.md)（⬛ 2026-10-02：只写 CLI 半边；评审完成，§6 全部裁定，Q16 归 WI-20；分支未开）。

> ⬛ 2026-09-30：**冻结集欠账窗口**（009 #49 / #50、017 finding #10、009 欠账表中 PR #28 遗留那一行；排在 `018` 之前，
> 理由与位置见[进度盘](../20260824-frontend-backend-plan-progress.md)）走一条 016 式的小分支，~~**编号在它开分支时才在上表分配**，
> 此前任何文件都不得写死编号。~~（⬛ 2026-09-30 同日：与 debug-state 一起在一个 `master` 提交里分配，窗口 = `019-frozen-set-debts`，debug-state = `020-debug-state`，见上表。）它同 016 一样是欠账兑付、不是新里程碑，兑付记在 009 / 017 各自的表上，不另开 task 文件。

**前端分支（010 / 013 / 014 与 015 的 PWA 部分）不再有独立任务文件**——它们的工作项以
`### WI-N:` 的形式直接写在 [前端计划正文](../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md) 里，
这样 `/tdd-guardian:workflow` 能把整份计划当成单一输入来跑。

~~其余一个（015 的后端部分）**故意还没写**。~~（⬛ 2026-10-02：已写，见上列。下面的理由保留作来历。）评审第 9 条要求补齐骨架，
处置方式是**领先一个分支即时补**，不是现在一次写完：骨架的价值来自它写下的
事实（哪些代码还在、哪些已经被上一个分支改掉了），而 011 的事实要等 008 落地才成立。
提前写只会得到一份开工时已经过期的清单。开某个分支前补它自己那份。

**补任务文件时有一条固定动作**：去 [`tasks/009-e2e-annotations.md`](./tasks/009-e2e-annotations.md) 的跨波欠账表里，把**兑付方指向该分支**的行抄成开工项。009 做 E2E 特征化时实测撞出的生产缺陷都记在那张表上，而那份文件会随 009 合并进入归档——不在开分支时主动去取，这些账就丢了。今天指向 **011** 的有一行：**#18**（`collections_service._NAME_RE` 把连字符判成字符范围端点，导致 `sci-fi` 这类集合名建不出来、而带反斜杠的名字反被放行）。指向前端计划的五行已由 [前端计划 §6.1](../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md) 接走。指向 **012** 的~~今天有九行~~（⬛ 2026-09-30：018 WI-1 改写后剩五行——#35 / #52 / #54 / #55 / #57；下列原文保留作来历）原有九行：**#35**，以及 2026-09-25 按用户裁定 R1–R3 立账的 **#51–#58**（013 延后的后端半边：provider 保存版本校验、批量重建索引、书库导出、DEG-S3 / DEG-S4 数据面、客户端书目列表、上传、删书）——内容只在那张表里，开 012 时照表抄。**其中 #51 / #53 / #56 / #58 已于 2026-09-26 裁定改由 `018` 兑付**（见上文 `018` 段），~~表上的兑付方列待 018 开工时同批改写~~（⬛ 2026-09-30：表上的兑付方列已由 [018 WI-1](./tasks/018-library-routes.md) 同批改写）。

> **「领先一个分支」按依赖顺序数，不按编号顺序数。** Track D（010）先于 011 成文，是因为
> §9.1 把 Track D 与 1b 标为「Phase 0 一结束就动」——它们是 Phase 3 的前置，
> 而 1b 那份等待是 soak 的日历时间（⬛ 2026-09-28 日历跨度已取消，这半句理由随之失效，见 §7）。另外「事实会过期」这条理由对 Track D 恰好不成立：
> 它只改 `designs/` 与设计规格，不读一行生产代码，它的事实不随 007 / 008 漂移。

### 9.1 依赖图（canonical）

§6「并行区间」讲的是**能同时开工的三条线**，本表讲的是**每个阶段真正等谁**。两者视角不同，冲突时以本表为准。

| 阶段 | 前置（全部满足才能进） | 它阻塞谁 |
|---|---|---|
| Phase 0 | — | 全部 |
| Phase 1a | 0 | 2a |
| Phase 1b | 0.3 + 0.5 | 4A（要 **G1**）；**Phase 3**（要 **G2** 之后~~再连绿十次~~再跑通一批 10 次，⬛ 2026-09-28 批次规则见 §7） |
| Track D | 0 | **Phase 3**（DEG-S1–DEG-S5 原型） |
| Phase 2a | 1a | 2b |
| Phase 2b | 2a | Phase 3 |
| M4a-债（`018`） | 2b（`book_store` 的元数据接缝）＋ 4A 已合入；**不等 soak** | ~~Phase 3 的末波（#55 的载体是 018 的书目列表路由 #56，#57 要用 018 的每书写锁），不挡 Phase 3 开工~~ **Phase 3 开工**——018 是 012 的进入条件（[012 §1](./tasks/012-storage-format.md)）；末波的 #55 / #57 另依赖它的 #56 与每书写锁（⬛ 2026-09-30） |
| **Phase 3** | **2b ＋ Track D ＋ 1b 的 soak**（从 **G2** 起算）——三路汇合；⬛ 2026-09-30 补：＋ **`018` 已合入** ＋ **[012 开工核验](#012-开工核验2026-09-30-维护者裁定)**（最终候选上的新批次与机制闸） | 4B |
| Phase 4A | 1b 的 **G1** | 4B（其中 4A.4 项） |
| Phase 4B | Phase 3 ＋ 4A.4 | 5 |
| Phase 5 | 4B | — |

关键路径：`0 → 1a → 2a → 2b → 3 → 4B → 5`。1b 与 Track D 不在关键路径上，**但它们的完成时间必须早于 2b 结束**，否则 Phase 3 干等——~~而 1b 那份等待是 soak 的日历时间，无法压缩~~（⬛ 2026-09-28：日历跨度取消，soak 变成一批 10–15 分钟，本身不再是长等待；1b 仍须早于 2b 结束，因为批次要跑在已冻结的 `baseline-1b` 上）。结论是：**1b 与 Track D 要在 Phase 0 一结束就动，不能排到 2a/2b 之后**。

> **「就动」不等于「排在 008 前面」。** 2026-08-24 与 Codex 复核后确定的实际开工顺序，以及为什么
> soak 应当与 011 同期跑而不是抢在它前面，定义在
> [`docs/plans/20260824-frontend-backend-plan-progress.md`](../20260824-frontend-backend-plan-progress.md)。
> 本表定义的是**依赖**（谁等谁），那份文档定义的是**顺序**（先做谁），两者不冲突：顺序必须满足依赖，
> 但依赖不唯一决定顺序。

---

## 10. 决策依据

三条依据（后端留 Python、前端迁 TypeScript、暂不做 Electron/Tauri）的正文——含 Python 生态绑定对照表、前端病灶清单、桌面壳的体积与引擎论证——已迁至 [ADR-0008](../../adr/0008-tech-stack-boundary.md)（唯一定义处）；其中「语义嵌入 / 向量库」两行的展开另见 [ADR-0004](../../adr/0004-chromadb-minilm-vector-search.md)。下面三个小标题只为保住既有锚点。

### 10.1 为什么后端留在 Python

→ [ADR-0008](../../adr/0008-tech-stack-boundary.md) Considered Options 2（全栈 TypeScript 重写，为什么不）。

### 10.2 为什么前端迁 TypeScript

→ [ADR-0008](../../adr/0008-tech-stack-boundary.md) Decision Drivers 与 Considered Options 3。

### 10.3 为什么暂不做 Electron/Tauri

→ [ADR-0008](../../adr/0008-tech-stack-boundary.md) Considered Options 4–5（Electron / Tauri）。

---

## 11. 明确不做的事（Non-goals）

- ❌ 后端迁移 TypeScript / Node / Bun → [ADR-0008](../../adr/0008-tech-stack-boundary.md)
- ❌ 现阶段 Electron 或 Tauri → [ADR-0008](../../adr/0008-tech-stack-boundary.md)
- ❌ 引入 SPA 框架或客户端路由 → [ADR-0008](../../adr/0008-tech-stack-boundary.md)
- ❌ 引入 SQL 数据库 → [ADR-0001](../../adr/0001-filesystem-as-database.md)
- ❌ 更换嵌入模型或向量库 → [ADR-0004](../../adr/0004-chromadb-minilm-vector-search.md)

每条的理由只在对应 ADR 里写一次，本节不复述。

---

*本计划由两次独立分析（Claude 三路并行子代理全仓库勘察 + Codex 只读仓库推演）交叉验证后综合而成；分歧点（Tauri vs Electron）已按更强论证方（Codex）修正。本文只做顺序与接口，不重开任何已定技术选型。*

---

# 附录 A —— 2026-08-15 工程评审原文

> **本节以下是评审原文与当时的落地记录，逐字保留、不追改。**
> 因此其中的文件路径、已删除的 `tasks/010-*.md` / `tasks/014-*.md`、以及裸写的 `S1`–`S5` 降级态编号
> 都停留在写作当时的形态。三点换算：
> **(1)** 文中的「合流计划」「主计划」在 2026-08-17 合并后都指**本文**（章节号原样有效）；
> **(2)** 降级状态现行编号为 `DEG-S1`–`DEG-S5`，定义在 [`spec-frontend-design.md` §6.4](../20260817-frontend-ui-refactor/spec-frontend-design.md)；
> **(3)** 已删除任务文件的内容现落在前端计划的 `### WI-N:` 里，对照见 [`README.md`](./README.md) 的「权威范围」表。

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
→ 改为 staging 目录 + 完整校验 + 原子切换，manifest 作为 commit marker（步骤见 [ADR-0007](../../adr/0007-crash-safe-publish-protocol.md)——那是唯一定义处，Phase 0 先按同一顺序落 staging 切换；⬛ 2026-10-02 起 012 的提交协议改由 [ADR-0016](../../adr/0016-generation-directory-publish.md) 定义）。**列入 Phase 0。**
✅ **已完成**（`7a807c9`，分支 `007-hygiene-and-contracts`）。实施中发现八步协议覆盖不了三件产物，两条缺口已回写进该小节的「两条协议缺口」——Phase 3 动这块之前先读那里。缓存失效不在本项修复范围内，归 Phase 2a 的 `book_store.py`。

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

Phase 1b 从 Phase 1 中拆出并降级为「仅阻塞 Phase 4」，使 Phase 2/3 不被 E2E 拖住；同时 Phase 4 的前置条件明确写为「1b 的标注 E2E 必须绿灯」——该条原文要求「在主 CI 里、不得放 nightly」，2026-08-24 随 CI 改为仅发版触发而改基为本地 lane ＋ `soak-log.md` 台账，见 §7。

### 架构决策（A1–A5）

- **A1 隐式契约显式化**：`manifest.json` 记录 `spine_fingerprint`。指纹须涵盖原 EPUB hash、spine href/order、每个 XHTML 的**原始内容** hash 与~~解析器版本~~ `EXTRACTOR_VERSION`（⬛ 2026-10-01，[012 §6 Q13](./tasks/012-storage-format.md)：标注相关输出——每个 spine 项的 `text` 与 spine href/order——经评审的改动才 bump；金样测试须能发现已知改动，但不是唯一判据；0 = 未知旧提取器，不代表等价）——只 hash `chapter.text`（`extract_plain_text()` 的空白折叠产物）检测不到影响 CFI 的 HTML 结构变化。`notes.json` 与 chroma `meta.json` 各自存所绑定的指纹。
  （⬛ 2026-10-01，Q13）**指纹随每个 generation 存储并从那里读取**，按该 generation 记录的产物校验，绝不用当前提取器重算。
  **指纹不匹配按消费方分级降级，不阻断 `load_book()`**：notes 不匹配 → ~~停止套用标注并返回 stale~~（⬛ 2026-10-01，Q13）逐条标注的解析状态：重导入后唯一匹配的标注 resolved，歧义 / 无匹配的保留旧绑定、警告可见；书级 notes 指纹只在全部 resolved 或用户显式处置后前移；chroma 不匹配 → 索引标记 stale 提示重建。坏索引不得导致书打不开。
- **A2 pickle 读取回退**：默认关闭、退出机制与「双写期 / 停写 pkl 之后」两个时间窗的分界，正文已迁至 [ADR-0009](../../adr/0009-book-format-manifest-jsonl.md)（唯一定义处）；三态判定见 [ADR-0007](../../adr/0007-crash-safe-publish-protocol.md)。
- **A3 `static/dist/` 提交进 git**，Node/Vite 仅作构建期工具。须配 lockfile、固定 Node/Vite 版本、可重复构建 CI 检查，以及 wheel 内容测试（见 P0-2）。
- **A4 PWA 缓存策略写死**：HTML 与 `/api/*` 一律 network-first 不缓存；只缓存内容哈希过的 `dist/` 资源与 vendor bundle；SW 内嵌 build version。**`skipWaiting()` + `clients.claim()` + activate 立即清旧缓存三者同用会撕裂版本**——仍打开的旧页面加载旧 hash chunk 会失败；改为保留前一代缓存（清 N-2），或强制提示并刷新全部 client。
- **A5 `book_store.py` 先定接口契约再写实现**：
  `load_book(book_id) -> Book`、`load_book_metadata(book_id)`、`load_chapter(book_id, order)`、`iter_chapters(book_id)`、`chapter_count(book_id)`、`book_fingerprint(book_id) -> ~~str~~ str | None`、`storage_format(book_id) -> Literal["missing","corrupt","valid"]`。

  （⬛ 2026-10-08，012 §6 Q15 / WI-2a R2）`book_fingerprint` 返回 `str | None`：`None` = manifest 缺失（只有 pkl 的旧书）或损坏；损坏时每本书只记**一条** WARNING（不是每次调用一条）。`None` 的含义是「无法判断」——不算 stale，绝不阻断 `load_book()`。「corrupt 大声失败」归 WI-3 的三态读取（`storage_format`），不归指纹这一层。

  > ⚠️ **2026-09-23 订正：此处此前写的是 `Literal["json","pkl"]`，与上面 A2 那条（「三态判定见 ADR-0007」）自相矛盾，两行只隔四行。** [ADR-0007](../../adr/0007-crash-safe-publish-protocol.md)（**Accepted**）的「读取状态机」小节粗体裁定 `missing` / `corrupt` / `valid` **三态、禁止二态**，并点名否掉「只回答新格式还是旧格式」——理由是二态把「没迁移」和「迁移坏了」归成同一件事，而后者必须大声失败、不许静默回退 pkl。二态签名正是它点名的那个 bug，故按 ADR-0007 订正。
  >
  > 同一处错误也在 [ADR-0009](../../adr/0009-book-format-manifest-jsonl.md) 的 Neutral 小节里（它引的就是本行），一并订正。**没有写 supersede ADR**：ADR-0009 的 Status 是 `Proposed`、Current compliance 是 `None`，它是待定稿不是已生效裁定，与 Accepted 的 ADR-0007 之间不构成「两份裁定冲突」，直接订正即可。发现路径是 `010` 退出门槛 D-6（书卡的 `storage_format` 角标该渲染几个值），记于 [`plan-frontend-ui-refactor.md`](../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md) 的 2026-09-23 实测小节。
  >
  > **`storage_format()` 的三态不等于书卡角标的取值域**：角标问的是「旧格式还是新格式」，而 `corrupt` 是健康度不是格式。角标自己的取值域由 `010` 另行定义，不要直接把这三个值渲染上去。
  只暴露全量 `load_book()` 会让 Phase 3 的 JSONL 随机读取与 Phase 2b 的性能优化无处落脚——JSONL 将退化为「换扩展名的 pickle」。`manifest.json` 为每章记录 `offset_bytes` / `length_bytes` / hash，`chapters.jsonl` 二进制 seek 读取；书库页只读 manifest，单章阅读只读一行。
  **合并范围（2026-09-07 实测订正，此前写的「三处 `_Reader3Unpickler` / cached-loader」三个部分全不成立）**：
  今天的答案是 **两处同名 loader ＋ 一处建在其上的 index 缓存**——
  `server.load_book_cached(book_id)` 与 `search_service.load_book_cached(book_id, books_dir)`
  **同名不同签名**，各挂一个 `lru_cache(maxsize=10)`，同一本书在进程里躺两份且失效时机互不相干；
  第三处是 `search_service.load_book_index`（`maxsize=4`），它**建在** `search_service.load_book_cached` 之上，
  不是第三份独立 loader。**`vector_search.py` 不在合并范围内**——它直接调 `safe_pickle.load_book_file`，没有 `lru_cache`。
  **`_Reader3Unpickler` 这一半的工作早已做完**：受限 unpickler 在 007/008 期间就收敛成了 `safe_pickle.Reader3Unpickler`。
  > 计划没写出来的那条收益：同名是**陷阱**，不只是重复。测试里 `monkeypatch.setattr(server, "load_book_cached", …)`
  > 出现 6 次，只换掉 `server` 那一份，`search_service` 那一份纹丝不动——合并让「打了桩」与「真的被打了桩」重新变成同一件事。
  **已于 `1be7387`（011 WI-3）兑付**，key 里带上 `mtime_ns` ＋ `size`。推导全文见 [`tasks/011-backend-refactor.md`](./tasks/011-backend-refactor.md) §0.2。
  > **原文写的是「四处」。第四处已于 2026-08-16 删除，不进 `book_store.py`。** 那是 `SearchIndex` / `BookIndex.from_book_pkl` / `SearchIndex.build_from_library`——001-search-features 的 T027/T029/T030 产物，实现了没接线，`search_library()` 后来走的是 per-book `load_book_index` 那条路，全仓库零调用方。它带两处分歧：用**裸 `pickle.load`，没有 `_Reader3Unpickler` shim**（另外三处都有），且包在 `except Exception: failed.append(book_id)` 里——一本 legacy `__main__.Book` 的 pkl 在阅读器里能开，在这个索引里会**无声消失**；同时它整段复制了 `load_book_index` 的 `BookIndex` 构造体。把它搬进 `book_store.py` 等于把一个静默失败分支洗成「现役设计」，故直接删除。
  >
  > 删除边界：只删 `SearchIndex` 类与 `BookIndex.from_book_pkl` 这个 classmethod。**`BookIndex` / `ChapterIndex` 两个 dataclass 是活的**——`load_book_index()` 构造它们，`search_book` / `search_library` / 章内定位三条路径都在用。`search_service.py` 773 → 734 行。
  缓存改为**自定义 weighted LRU**（按估算常驻字节淘汰，key 纳入 mtime/指纹）——`functools.lru_cache` 无法表达按字节淘汰。

### 代码质量决策（B1–B4）

- **B1** `escapeHtml` 是**活的全局覆盖**，非 DRY 问题。`reader.html` 先载 `search.js`（定义 `escapeHtml(text)`）后载 `ai.js`（定义 `escapeHtml(str)`），后者静默覆盖前者，`search.js` 里 `renderResults()` 的调用点执行的是 ai.js 的实现，两者在 falsy 输入上语义不同（`String(text)` vs `String(str || "")`），而这是宪法第 4 条管辖的 XSS 出口。
  → Phase 0 将 `search.js` / `ai.js` / `settings.js` / `library-search.js` 四个文件包进 IIFE（仓库另外八个 JS 文件本就是 IIFE，这四个是落后者），falsy 语义统一为 `String(v ?? "")`。
  **附带发现（正面）**：真正的跨文件全局契约只有 `window.Reader3Epub` 一个（`epub-renderer.js` 定义，annotations.js / search.js 经 `?.` 消费）；`annotations.js` 的 `getReaderContext` 在 IIFE 内不构成冲突。ES module 化的爆炸半径远小于「5818 行裸 JS」的直觉。
- **B2** 67 处 `except Exception`、4 处裸 `pass`。Phase 1a 开头先写死三级规则：外部数据读取可降级但必须 `logging.warning` 带上下文；数据完整性校验禁止捕获必须上抛；禁止裸 `pass`。ruff 开 `BLE`/`S110`，存量入白名单逐步清理。已知四处（`_parse_summary_payload()`、`api_ai_question()` 内的 `push()` 闭包、`ai/books.ensure_book_uuid()`、`ai/conversations.list_conversations_combined()`）在 Phase 1a 修（**不放 Phase 0**——这是行为变更，需与测试同步）。
- **B3** Phase 2 对 Python 写了「不改行为」，Phase 4 对 JS 无对称约束。补上该约束，并把第 5 步拆为 **5a**（纯 JS 拆 `annotations.js`，不动一行逻辑，验收：1b 标注 E2E 全绿）与 **5b**（拆出的文件逐个转 TS，同一套 E2E 再全绿）。⚠️ 本条原写的 anchoring/renderer/ui 三分法已被证伪，实际划分见 `tasks/014-ts-frontend-reader.md`。CFI/DOM Range 这类脆弱代码，多一个 PR 的成本远低于混在一起后的调试成本。
- **B4** 42 处 `console.log`（annotations.js 33 / epub-renderer.js 9）换成 `debug.ts` 分层，由 `localStorage["reader3.debug"]` 控制（默认关），ESLint 开 `no-console` 放行 warn/error。

### 性能（C1–C5，计划原本无此章节）

- **C1 [P1]** `search_library()` 对库内每本书调 `load_book_cached()`（`lru_cache(maxsize=10)`）+ `load_book_index()`（`lru_cache(maxsize=4)`）。每次 miss 是全书反序列化 + 全书归一化。
  **阈值订正（2026-08-16）**：原文写「库超 10 本即颠簸」，看的是 `load_book_cached` 的 `maxsize=10`。真正的约束是 `load_book_index` 的 **`maxsize=4`** ——**第 5 本就开始颠簸**，不是第 11 本。且 `load_book_index(book_id, books_dir, *, case_sensitive)` 把 `case_sensitive` 编进了 key，同一本书大小写敏感/不敏感各占一格，**有效容量再折半到 2 本**。→ **Phase 2b**。
  一个错的阈值比没有阈值更糟：它会被当成性能测试的判据，然后永远不触发，最后得出「C1 不存在」的结论。
  **兑付情况（2026-09-20，011 WI-8 `a4e5f49`）：`maxsize` 4 → 12（`case_sensitive` 入 key ⇒ 有效容量 6 本），
  key 纳入 `(st_mtime_ns, st_size)`。但 C1 的性能目标 ✗ 没兑付** —— `bench/011-iso-*.json` 三份逐提交隔离实测，
  全库搜索的 `unpickle_grand_total` 恒为 **95**，扩容一次读盘都没省。原因是 `search_library()`
  （`search_service.py:620`）为取 `title`/`author` 无条件先反序列化整本书，索引缓存命中与否轮不到它。
  **这一条不是 C5**（C5 只管书库首页），剩余部分立为欠账 #35，兑付方 012。见 [011 §8 门槛 #7 的裁定](tasks/011-backend-refactor.md)。
- **C2 [P1]** `_normalize_with_map()` 的 `List[int]` 是每字符一个 Python int：300 万字符 → 300 万元素 list（粗估 >100 MB）。换 `array('I')` 约 12 MB，且仍支持 `index_map[i]` 下标，**不改变** `highlight_ranges_for_chapter()` 的偏移语义。稀疏 breakpoint 表示留到第二阶段（casefold 扩张与 combining mark 删除的错误风险高）。→ **Phase 2b**，须做差分测试。
  **✅ 已兑付（2026-09-20，011 WI-9 `b69a568`）**：`array("I")`（无符号，偏移恒非负；与原文写的 `'I'` 一致）。
  逐提交隔离实测 `after_library_search_bytes` **237.7 → 114.1 MiB**、`after_huge_search_bytes`
  **331.7 → 195.4 MiB**，spread 0.0/0.1%。偏移语义未变，差分测试在 `tests/unit/test_normalize_index_map_container.py`。
  稀疏 breakpoint 表示仍未做，也仍然没有需求。
- **C3 [P2]** 三处 `lru_cache` 的 key 均不含 mtime/指纹，重新处理同名书后进程继续返回旧 `Book`/`BookIndex` 直到重启。→ **Phase 2a**（并入 weighted LRU）。
  **✅ 已兑付，但「三处」这个数今天是错的**：`src/` 里只剩两处 `lru_cache`
  （`book_store.py:66` maxsize=10、`search_service.py:319` maxsize=12），第三处随 011 WI-1…WI-5 的合并消失了。
  两处的 key 都已含 `(st_mtime_ns, st_size)` —— `book_store` 由 WI-3 兑付，`load_book_index` 由 WI-8（`a4e5f49`）兑付。
  **weighted LRU 没有做**，裁定是在 011 里用 vanilla `@lru_cache`（ADR-0008 的简单性边界），详见 011 §7 的 WI-8 完成记录。
- **C4 [P2]** JSONL 若 `load_book()` 仍整份读完，相比 pickle 只是换扩展名——pickle 对 dataclass 图通常更快，JSON 需先建 dict/list 再构造 dataclass，瞬时内存更高。收益完全取决于 A5 的粒度接口 + manifest 字节偏移是否落实。
- **C5 [P1，2026-08-16 eng-review 新增]** **书库首页把每本书的正文全部反序列化了一遍。** `library_view` 遍历 `books/*_data/`，对每个目录调 `load_book_cached()` ——只为读书名、作者、封面这几个字段，却把整本书的 spine 与全文 text 都拉进内存。`lru_cache(maxsize=10)` 意味着第 11 本起每次刷新首页都是冷读。
  这是**全站访问频次最高的路径**（每次进站必走），而 C1 说的跨库搜索是低频操作 —— C1–C4 一个字没提它，优先级排反了。
  修法与 A5 的粒度接口天然对齐：`load_book_metadata(book_id)` 只读 `manifest.json`，不碰 `chapters.jsonl`。
  ⏳ **落点待裁决**：严格说它依赖 Phase 3 的 `manifest.json` 才成立；放 Phase 2b 需要先出一个过渡版（例如单独缓存一份轻量书目 JSON）。见附录 B 文末 UNRESOLVED DECISIONS。

性能工作**单列 Phase 2b**：塞进 Phase 2 会让结构变化与缓存算法变化混淆；塞进 Phase 3 会让序列化格式、加载策略、搜索性能三者同变，等价性证明失去可信度。

**Phase 1a 须先记录基准**：冷启动、二次相同查询、峰值 RSS、反序列化次数、归一化次数，**外加「首页冷启动 TTFB × 书库规模」**（C5 的判据，且它比跨库搜索更贴近真实使用）。

> **基准需要一个 20 本的合成书库 fixture。** 本仓库 `books/` 目前只有 1 本，C1–C5 的全部结论都是**推断而非实测** —— 单本库里 `maxsize=4` 与 `maxsize=10` 表现完全一致，颠簸根本不会发生。fixture 用小体量 EPUB 复制改名即可（重点是**本数**，不是字数），另留 1–2 本大部头覆盖 C2 的 300 万字符路径。

### 测试（详见 Test Plan 工件）

零测试、零 CI、无既有约定。覆盖率目标：Phase 1a 全项目 70% line / 60% branch；Phase 2 将改动的模块 ≥85% branch；`book_store` / `_normalize_with_map` / notes 持久化 / AI routing ≥90% branch；此后新增或修改行 90% diff coverage。

计划原列的七类 fixture 不足，须补四组：spine/TOC 结构（多 anchor 指同一 XHTML、`linear="no"`、TOC 指向不存在文件、同 href 不同 fragment）、Unicode（NFC/NFD、`ß→ss` casefold 扩张、土耳其语 `İ`、非 BMP 与 ZWJ emoji）、标注锚定（quote 跨 text node / 跨段落 / 章内重复靠 prefix-suffix 消歧、CFI 失效回退、重叠标注、stale/orphan）、规模与失败（300 万字符 fixture、非法 ZIP、缺 container）。

> **偏移单位必须写进 API 契约**：Python 按 Unicode code point，DOM/JS 按 UTF-16 code unit。当前前端自行重算范围掩盖了差异，Phase 4 合并共享 TS 模块时极易错误复用服务端 `ranges`。

42 条路由用三层组织（`app.routes` 清单快照 + 六组表驱动契约 + 少量领域场景），避免 42 份复制粘贴；复用或校正既有 `specs/*/contracts/*.yaml`。

iframe 标注 E2E 可行：Selection 本就不能跨 browsing context，实际需求是「iframe 内建选区 → 操作外层工具栏」。路径为 child frame 内 `document.createRange()` → 写入 iframe Selection → iframe document 上派发 `mouseup` → 点外层工具栏 → 断言 `POST /api/notes/*` → 刷新 → 断言 iframe 内重现 `<mark>`。`window.Reader3Epub` 已提供所需可测性桥。真实鼠标拖选只保留一条 smoke。

> **2026-08-16 修正**：这条链里**只有最后一段构成通过条件**——「刷新后 `<mark>` 回到同一段文字上」。断言 `POST` 发生过属于 wiring-only，仅留作失败时的诊断信息。见 `docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §0。

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

---

# 附录 B —— 2026-08-16 三份计划并审原文

> **本节以下是评审原文与当时的落地记录，逐字保留、不追改。** 换算规则同附录 A 开头三条：
> 文中的「本文」「主计划」指合并前的 `plan-ui-migration-sequencing.md`，合并后即**本文**（§4 / §6 / §7 / §8 / §9.1 等章节号原样有效）；
> 「技术栈计划」指合并前的另一半，现在也是本文（其 Phase / A1–A5 / B1–B4 / C1–C5 等标签原样有效）。

## GSTACK REVIEW REPORT

**审查对象**：三份计划并审 —— 本文（顺序）、`20260815-plan-tech-stack-migration.md`（架构）、`20260815-spec-frontend-design.md`（设计），外加对其事实性断言的源码核验。
**审查日期**：2026-08-16 ｜ **分支**：`master` ｜ **Outside Voice**：Codex（`codex exec`，read-only）

**流程偏差（先说清）**：本技能规定每条发现用 AskUserQuestion 逐条 STOP 确认。本次会话以「执行 1-4，然后继续 eng-review」恢复且要求不再提问，故所有需要用户拍板的项改为汇总到文末 **UNRESOLVED DECISIONS**，不在中途打断。

---

### 1. 架构（Architecture）

#### A-1 [CRITICAL] 4B.1 的模块划分漏掉整条标注写入路径 —— 置信度 **9/10**

`docs/plans/20260816-tech-stack-migration/tasks/014-ts-frontend-reader.md` 的七模块表把 `interactions.ts` 描述为：

> `constructor`（减去七行 `qs()`）`init` `onAnnotationClick` `getExistingMarkerIds` `onSelection` … `copySelection` `askAi` ＋ `initAnnotations`

逐符号核对 `annotations.js`：`AnnotationUI` 有 **30 个方法**，上游计划记为 24。差额六个是 `toggleMarkerAnnotation` / `toggleAnnotation` / `deleteCurrentAnnotation` / `saveNote` / `deleteAnnotations` / `createAnnotation`，约 174 行，构成从 `handleAction`（已指派 `interactions.ts`）到三处 `fetch`（已指派 `notes-api.ts`）之间的完整写入链。七个模块的行数估算合计 1055，文件实际 1127 —— 差额与这六个方法吻合。

按行号区间机械切分会把它们塞进 `note-editor.ts`，于是 `createAnnotation`（marker / wavy / underline / note **四种类型共用的唯一写入口**）住进一个叫「笔记编辑器」的模块，同时 `notes-api.ts` 与 `note-editor.ts` 双双声称拥有那三处 `fetch`。

**裁定：采用方案 (a)，新增第八个模块 `commands.ts`**，依赖方向 `interactions → commands → notes-api` 单向。Codex 独立给出同一结论，并点名两个落选项的失败模式：(b) 折进 `notes-api` 是**层级塌缩**，传输层被 UI 状态与渲染污染，最终长成 god service；(c) 只做文件切分不做职责切分是**装饰性模块化**，667 行的隐式耦合与过宽的可变权限原样保留，拿不到单测边界。

> `tasks/014-ts-frontend-reader.md` 的「⚠️ 待评审」块与 `contracts/annotation-host-contracts.md` 均指向本报告，**此项就此关闭**。

#### A-2 [HIGH] K5 冻结范围只覆盖「今天这个消费者用到的」成员 —— **8/10**

K5 冻结 `window.Reader3Epub` 9 个成员中的 5 个。被略过的 4 个里，`applyThemeSettings` 与 `displaySectionIndex` 在 `reader.html` 里都有活的调用点，且 4B.3（阅读设置面板）明确依赖前者。照现状写，**4B.3 没有一条被许可的路径**。

**裁定：冻结契约必须枚举边界的全部活成员。** Codex 给出的规则比「全都写上」更好用 —— 每个对外可调用成员必须落到三类处置之一：**(1)** 纳入契约并写明签名与行为；**(2)** 显式标记 deprecated 并指定移除阶段；**(3)** 通过**收窄契约名义**排除在外（把 K5 从「`Reader3Epub` 公开面」改叫「标注依赖子集」），而不是默默不提。

默默不提是最差的一种：读者无法区分「没用到」和「不许用」。

#### A-3 [MEDIUM] A5 的「四处合并」里有一处是死代码，应删不应并 —— **9/10**

技术栈计划 A5 写：

> 合并范围为**四处** `_Reader3Unpickler` / cached-loader 定义：`server.py` 一处、`search_service.py` 两处、`vector_search.py` 一处

第四处 —— `SearchIndex`、`BookIndex.from_book_pkl`、`SearchIndex.build_from_library` —— 全仓库 grep 确认**从未被调用**，唯一提及在 `specs/_archive/001-search-features/` 的文档里。它来自 001 的 T027/T029/T030：实现了但没接线，`search_library()` 后来走的是 per-book `load_book_index` 这条路。

它还带着两处分歧：用**裸 `pickle.load`，没有 `_Reader3Unpickler` shim**（另外三处都有），且包在 `except Exception: failed.append(book_id)` 里 —— 一本 legacy `__main__.Book` 的 pkl 在阅读器里能开，在这个索引里会**无声消失**；同时它整段复制了 `load_book_index` 的 `BookIndex` 构造体。

**裁定：Phase 0 删除，A5 改为三处合并。** 把死代码搬进新的 `book_store.py` 等于把一个静默失败分支洗成「现役设计」。

> **2026-08-16 已执行**（用户裁决：删）。删除范围只有 `SearchIndex` 类与 `BookIndex.from_book_pkl` 这个 classmethod——**`BookIndex` / `ChapterIndex` 两个 dataclass 是活的**，`load_book_index()` 构造它们，三条搜索路径都在用；照字面「删掉 BookIndex」会打断整个关键词搜索。`search_service.py` 773 → 734 行，模块与 `server.py` 导入通过，单本书 `load_book_index` 冒烟正常。A5 已改写为「三处」，Phase 2a 退出条件同步。

#### A-4 [MEDIUM] K3 的前置条件在生产侧成立，但没人把它写成 4B.2 的门槛 —— **8/10**

K3 说 `position: fixed` 的浮层要求祖先链无 `transform` / `filter` / `backdrop-filter` / `contain` / `will-change: transform`。核验现状：`annotation-toolbar` / `note-editor` / `note-tooltip` 三个浮层今天都是 `<body>` **直接子元素**，条件天然满足 —— 也正因为天然满足，没人意识到它是个条件。而原型里 `.page-flow` 自己就带 `will-change: transform`；4B.2 重写外壳时把浮层挪进任何一个页面容器，K3 立刻失效，**而且是"元素可见、位置错了"这种 E2E 照样绿的失效**。

**裁定：4B.2 增加硬门槛** —— 三个浮层保持 `<body>` 直接子元素（或 `<dialog>` top-layer），并加一条断言：浮层祖先链上不存在会创建 containing block 的属性。

#### A-5 [LOW] K1 爆炸半径低估 —— **7/10**

契约文件已按核验结果改正（`init()` 的 `if (!this.contentEl || !this.toolbar) return;` 先行短路，缺任一元素**整个标注 UI 静默不启动**，而非仅缺失那一块降级）。此处仅记录，无待办。

---

### 2. 代码质量（Code Quality）

#### Q-1 [HIGH] testid 是 0 → 134，不是「成本很低」—— **9/10**

> 【0.5 落地后回填】实际是 138 个站点，不是 134——差的四个是 `Sheet` 的 `testId=` prop。结论不变，方向也不变。对账见 [`contracts/testid-rename-map.md`](./contracts/testid-rename-map.md) §1。

设计规格 §4.1 现已记录：原型 134 个唯一 testid，**0 个合规**；其中 24 个带 `reader-` / `library-` 前缀的**比裸名更危险**，批量改名时容易被当成「已经对了」而跳过。

补一条核验结果：**生产侧 `templates/` 与 `static/` 里 `data-testid` 出现次数为 0**。现有可用锚点是 `id=`（library.html 77、reader.html 66、settings.html 13、library_classic.html 9），但 id 是**样式与 JS 的活引用**，不是测试契约 —— 把它当 testid 用，等于让测试锁死实现细节，而这正好是 strangler-fig 接缝最不该有的性质。

所以合同 1 的真实工作量是**两侧各一遍**：原型 134 个改名 + 生产模板从 0 新增。计划里「现有稳定 id 可直接映射，成本很低」的判断偏乐观。顺序（先原型后模板）已在 §3 与设计规格 §4.1 定死，方向是对的。

#### Q-2 [MEDIUM] 行号治理已落地，但 `tests/conftest.py` 自己还留着一处漂移行号 —— **9/10**

三份计划已统一改用符号名定位（步骤 4 的产出）。但 `tests/conftest.py` 的 docstring 里写着 `reader3.py:187`，而 `shutil.rmtree(output_dir)` 实际在 **:188** —— 一个测试基建文件在还没有任何测试的时候，就已经攒下一处失效引用。这是「谁都别写行号」这条规矩的活教材，顺手改掉。

> **2026-08-16 补正**：本条开头那句「三份计划已统一改用符号名」当时只对了一半——正文与 A5 已改，**附录仍留着七八处行号**（`search.js:369-370`、`server.py:1836` / `:2092`、`ai/books.py:57` 等），设计规格里还有三处。已在 R8 一并扫干净。

#### Q-3 [LOW] B1 / B2 / B4 核验通过 —— **8/10**

`escapeHtml` 的活全局覆盖、67 处 `except Exception`、42 处 `console.log`（annotations.js 33 + epub-renderer.js 9，正确排除了 pagination.js 的 2 处 —— 该文件是待删死代码）三项均与源码一致。计划在这一节是可信的。

---

### 3. 测试（Tests）

#### T-1 [CRITICAL] 整套计划的承重墙目前是零 —— **9/10**

`tests/` 现状：只有 `conftest.py`（39 行，一份描述三条泳道的 docstring）、四个空目录（`contract/` `e2e/` `fixtures/` `unit/`）、一个 `.DS_Store`，以及一个**源文件已不存在**的 `test_probe_tmp.cpython-310` pyc。`.github/workflows` 不存在。**零测试，零 CI。**

这不是新发现 —— 技术栈计划自己写着「零测试、零 CI、无既有约定」。但它是排序结论的地基：§4 论证「Phase 3 要在一套已经跑绿一段时间的 E2E 下做」这句话，今天字面上还没有任何东西支撑。**Phase 1 不是一个阶段，是这份计划能不能成立的前提。**

配套一条：那个 stale pyc 说明 `tests/` 曾经跑过一次又被删干净。Phase 0 应把 `tests/**/__pycache__` 与 `.DS_Store` 进 `.gitignore`，避免它们跟着首个测试 PR 一起进仓库。

#### T-2 [HIGH] 标注契约的失败模式是静默的，E2E 必须正向断言 —— **9/10**

K1–K6 六份契约里 **4 份的违约不产生任何 console 报错**：K1 缺元素 → `init()` 静默 return；K3 祖先链有 transform → 浮层可见但位置错；K4 事件名拼错 → 监听方永不触发；K6 上下文读不到 → 走 `location.pathname` 回退（4B.1 已定改为抛错）。

这决定了 1b 的 E2E 不能写成「无报错即通过」。三条具体要求：

1. **位置断言而非可见性断言** —— K3 只有量选区矩形与浮层矩形的相对位置才测得出；`toBeVisible()` 在错位时照样绿。
2. **端到端往返断言** —— 划词 → 工具条 → 落库 → 刷新 → 高亮回到同一段文字上。只断言 `fetch` 被调用过属于 wiring-only。
3. **降级路径要有正向证据** —— S1–S4 每个状态各一条：制造 stale，断言横幅出现且文案匹配。

#### T-3 [MEDIUM] 4B.1 的门槛依赖 1b 覆盖了写入路径 —— **8/10**

门槛写的是「1b 的标注 E2E **零改动**全绿」。这条只有在 1b 的用例覆盖了 A-1 里那六个写入方法时才成立 —— 而它们恰恰是最容易被漏掉的一层（读侧渲染肉眼可见，写侧只在刷新后才暴露）。1b 的用例清单里必须显式包含：四种类型各创建一次、改色、删除、笔记编辑保存。

---

### 4. 性能（Performance）

#### P-1 [HIGH] 性能章节漏了最热的那条路由 —— **9/10**

C1–C4 覆盖了跨库搜索、`index_map` 内存、缓存失效、JSONL 粒度，唯独没有 `GET /`。核验 `server.py` 的 `library_view`：书库首页对 `books/` 下**每一个** `*_data` 目录调 `load_book_cached(item)` —— 也就是**把每本书的全文反序列化一遍，只为读出 title 和挑一张封面**。`load_book_cached` 是 `@lru_cache(maxsize=10)`，所以 11 本以上每次首页刷新都是全库重读；即便在 10 本以内，冷启动后的第一次首页访问也要把整个书库解一遍 pickle。

这条与 C4 是同一枚硬币：A5 的 `manifest.json` 一旦落地，首页就该**只读 manifest**，一行正文都不碰。**建议列为 C5，落 Phase 2b**，并在 Phase 1a 的基准里加一项「首页冷启动 TTFB × 书库规模」。

#### P-2 [MEDIUM] C1 的颠簸阈值算错了 —— **9/10**

C1 说：

> 库超 10 本即每次跨库搜索都颠簸缓存

事实要素是对的（两个 cache、10 与 4），结论偏了：`search_library()` 的每本书循环里同时调 `load_book_cached`（maxsize=**10**）与 `load_book_index`（maxsize=**4**），**约束项是小的那个**，所以颠簸从**第 5 本**开始，不是第 11 本。而且 `load_book_index` 的 cache key 含 `case_sensitive`，同一本书在两种大小写模式下占两个槽 —— 用户切一次大小写开关，有效容量再砍半。

修法不变（weighted LRU），但触发点比计划以为的早一倍多，P1 的定级是合适的。

#### P-3 [LOW] 所有性能结论都是推演，当前库只有 1 本书 —— **8/10**

`books/` 下现有 1 个 `*_data` 目录。上述阈值没有一条是实测出来的。Phase 1a 的基准建设必须先造出 20 本规模的合成书库，否则 Phase 2b 的「优化前后」两侧都测不出差别。

---

### Outside Voice —— Codex

`codex exec --sandbox read-only`，就三个问题独立作答（未读仓库，仅凭结构化描述推理）。

| 问题 | Codex 结论 | 本报告处置 |
|---|---|---|
| Q1 写入路径归属 | 选 (a) `commands.ts`；(b) = layer collapse / god service，(c) = cosmetic modularization | **采纳**，见 A-1 |
| Q2 冻结范围 | 枚举全部活成员；给出三类处置规则（纳入 / deprecate / 收窄契约名义） | **采纳且升级**，Codex 的规则比原问题的二选一更好，见 A-2 |
| Q3 Phase 3 位置 | **反对**现有顺序，主张 `… → 4A → 4B → Phase 3 → Phase 5` | **部分采纳**，见下 |

**Q3 的分歧值得展开。** Codex 的论证是：不要把「不可逆的持久化变更」和「风险最高的 UI 重写」摞在一起，而 Phase 1 的测试尚无 CI 历史，保护力未经检验。

**它的前提在本仓库不成立。** Phase 3 迁移的是 `book.pkl → manifest.json + chapters.jsonl` —— 这是**派生数据**，源头 `book.epub` 就躺在同一个目录里，没有被 Phase 3 触碰；`notes.json` / `ai_meta.json` / `chroma_db/` 也都在格式变更范围之外。叠加计划已有的**双写 + 回退读**，Phase 3 的回滚动作就是「删掉两个新文件」。它不是不可逆的。

所以：**顺序维持不变，但本文 §4 的论证 1（不可逆性）站不住，应当改写。** 支撑这个顺序的是论证 2 与 3 —— 阅读器一重写，标注 E2E 随之重写，届时是在一套刚出生的测试下动用户数据；而「等价性测试通过、真实标注已坏」这个已点名的失败模式，要求验收基准跑在**还没被改过**的阅读器 DOM 上。这两条与 Codex 的顾虑不冲突。

**Codex 真正有价值的那半句是「CI 历史尚无，保护力未经检验」** —— 对此的正确回应不是换顺序，而是加一道门槛：**Phase 3 开工前，1b 的标注 E2E 需在 CI 上连续绿 ≥ 10 次且跨 ≥ 5 个工作日**。一套跑过一次的 E2E 和一套跑绿两周的 E2E，不是同一个东西。

**另有一条真实的不可逆风险被这场辩论翻出来**：`reader3.py` 在写入任何内容前 `shutil.rmtree(output_dir)`，而 `notes.json` / `ai_meta.json` / `chroma_db/` 全在里面。它跟 Phase 3 的格式无关，但一旦 `reader3 --migrate` 复用摄取路径，就会在迁移时抹掉用户标注。**`--migrate` 必须原地读写，禁止走摄取路径** —— 这条要写进 Phase 3 的验收。

---

### 不在本次范围内（NOT in scope）

- **技术选型本身**：后端留 Python、不上 SPA 框架、不做 Electron/Tauri、不换嵌入模型与向量库 —— 均为已定项，未重开。
- **视觉设计评审**：配色、排版、组件形态属 `/plan-design-review` 与 `/design-review`，本次只看它们对实施顺序造成的约束。
- **原型代码质量**：`designs/reader-pro-next/` 是可执行规格，不是待移植代码（见其 README），未按生产标准审。
- **AI / RAG 子系统**：三份计划都没打算动它，本次未核验 `ai/` 下的任何实现。
- **未运行任何测试**：仓库零测试，无可运行项；所有结论来自静态核验与源码阅读。

### 已经存在的东西（What already exists）

盘点一遍，免得把已有的当作待建：

| 已有 | 位置 | 状态 |
|---|---|---|
| 完整的标注实现（四类型、CFI + quote/prefix/suffix 锚定、重叠渲染） | `static/js/annotations.js` 1127 行 | 可用，未拆分，零测试 |
| epub.js 集成与分页 | `static/js/epub-renderer.js` | 可用，`window.Reader3Epub` 9 个成员 |
| 42 条 API 路由 | `web/server.py` | 可用，无契约测试 |
| 关键词 + 语义搜索、RAG、多 provider AI | `search_service.py` / `vector_search.py` / `ai/` | 可用 |
| 三页 UI + classic library | `templates/` 4 个模板 | 可用，`data-testid` 为 0 |
| 高保真目标原型（三屏 + 错误态） | `designs/reader-pro-next/` | 可跑，testid 已按 canonical 正则改名（221 个唯一名，0 违规） |
| K1–K6 宿主契约 | `contracts/annotation-host-contracts.md` | 已成文，本报告后需改 K5 |
| 双层 token 体系、逐页规格、S1–S5 降级态 | 设计规格 §3 / §5–6 | 已成文，两项 token 待收口 |
| 测试基建 | `tests/` | **只有 conftest.py 骨架，零用例，零 CI** |

### 待办（TODOS，按依赖排序）

见下一节「实施任务」。

### 失败模式（Failure modes）

按「会不会被现有验收挡住」排序 —— 越靠前的越容易溜过去。

| # | 失败模式 | 为什么会溜过去 | 挡它的东西 |
|---|---|---|---|
| 1 | 4B.2 把浮层挪进带 `transform` 的容器，工具条定位错乱 | 元素可见、无报错，`toBeVisible()` 绿 | R5 的位置断言 |
| 2 | 4B.1 按行号切分，写入链落进 `note-editor.ts` | 拆分后行为不变，E2E 全绿 | R1 的 `commands.ts` + 依赖方向检查 |
| 3 | Phase 3 等价性测试通过，真实标注已错位 | 等价性只比对文本，不比对锚定 | 真实 iframe 标注迁移 E2E（计划已有） |
| 4 | `--migrate` 走摄取路径，`rmtree` 抹掉 `notes.json` | 迁移「成功」，数据在别处丢 | R10 的原地读写约束 |
| 5 | testid 批量改名时跳过那 24 个「看起来已经对了」的 | 前缀正确，命名规则不对 | R11 的机器校验（正则 + CI） |
| 6 | 死代码 `SearchIndex` 被搬进 `book_store.py` | 搬运本身不会失败 | R4 的先删后并 |
| 7 | 首页在 20 本书时变慢，但没人测过 | 开发者本地只有 1 本书 | R7 的合成书库基准 |

### 关键路径与并行（Diagram）

```
Phase 0 ─┬─ R1 R2 R3 (契约收口，纯文档)   ─────────────┐
         ├─ R4 删死代码                                │
         ├─ R8 conftest 行号 + gitignore               │
         └─ R11 testid 校验脚本                        │
                                                       ▼
Phase 1a ── R7 合成书库 + 基准 ──┬─ 单测四类（可四路并行）
                                 └─ 42 路由契约测试
                                       │
Phase 1b ── R12 标注 E2E（含写入路径 + 位置断言 + S1–S4）
                                       │
                          ┌────────────┴────────────┐
                          ▼                         ▼
                 Phase 2a → 2b (R6 首页只读 manifest)   Phase 4A（不碰 annotations.js）
                          │                         │
                          ▼                         ▼
                 [R9 soak 门槛: E2E 连绿 ≥10 次 / ≥5 天]
                          │
                 Phase 3 (R10 --migrate 原地读写)
                          │
                          ▼
                 Phase 4B ── 4B.1 (R1) → 4B.2 (R5) → 4B.3 → 4B.4
                          │
                          ▼
                 Phase 5
```

关键路径：`Phase 1a → 1b → 2a → 2b → soak → Phase 3 → 4B`。Phase 4A 全程可与后端线并行，是唯一真正的并行收益点。

### worktree 并行

| worktree | 内容 | 与谁冲突 |
|---|---|---|
| `007-hygiene-and-contracts` | R1 R2 R3 R4 R8 R11 —— 契约文档 + 删死代码 + 基建 | R4 动 `search_service.py`，与后续 2a 有重叠，先落 |
| `008-test-safety-net` 四路 | 搜索偏移 / 摄取 / 持久化 / AI routing 四类单测互不相干 | 各自新建文件，零冲突 |
| `009-e2e-annotations` | R12 | 只加 `tests/e2e/`，零冲突 |
| `010-design-degradation-states` | 两项 token 收口 + S1–S5 | 只改 `designs/` 与规格，零冲突 |
| `011-backend-refactor` | R6 R7 + `book_store.py` | 与 `007` 在 `search_service.py` 上冲突，必须在其后 |
| `013-ts-frontend-shell` | Phase 4A | 不碰 `annotations.js` / `reader.html`，可与 `011` / `012` 全程并行 |

不能并行的两对：`012-storage-format` 与 `014-ts-frontend-reader`（§4 的严格串行）；`014` 内部 4B.1 → 4B.2（拆分必须先于外壳移动 DOM）。

### 实施任务（Implementation Tasks）

| ID | 任务 | 落点 | 阶段 | 优先级 |
|---|---|---|---|---|
| **R1** ✅ | 4B.1 采用方案 (a)，新增 `commands.ts` 承载六个写入方法；写死 `interactions → commands → notes-api` 单向依赖；删除 tasks.md 的「⚠️ 待评审」块 | `tasks/014-ts-frontend-reader.md` | Phase 0 | P0 |
| **R2** ✅ | K5 扩展到 `Reader3Epub` 全部 9 个成员，每个落到「纳入 / deprecate+移除阶段 / 收窄契约名义」三类之一；`applyThemeSettings` 与 `displaySectionIndex` 纳入 | `docs/plans/20260817-frontend-ui-refactor/contracts/annotation-host-contracts.md` | Phase 0 | P0 |
| **R3** ✅ | K1 补一句：缺任一元素 → `init()` 静默 return → 整个标注 UI 不启动（已改，本项为复核） | 同上 | Phase 0 | P2 |
| **R4** ✅ | 删除死代码 `SearchIndex` / `BookIndex.from_book_pkl` / `SearchIndex.build_from_library`；技术栈计划 A5 改为「三处合并」 | `search_service.py` + A5 | Phase 0 | P1 |
| **R5** ✅ | 4B.2 增加门槛：三浮层保持 `<body>` 直接子元素（或 `<dialog>` top-layer）；E2E 断言祖先链无 containing-block 属性、且浮层矩形与选区矩形相对位置正确 | `tasks/014-ts-frontend-reader.md` + 本文 §7 | Phase 0（写门槛）/ 4B.2（执行） | P0 |
| **R6** ✅ | 新增 **C5**：`library_view` 改为只读 `manifest.json`，不反序列化正文 | 技术栈计划 §性能 + Phase 2b | Phase 2b | P1 |
| **R7** ✅ | C1 阈值订正为「第 5 本」并说明 `case_sensitive` 进 key 使有效容量再半；Phase 1a 基准加「首页冷启动 TTFB × 书库规模」；造 20 本合成书库 fixture | 技术栈计划 §性能 + Phase 1a | Phase 1a | P1 |
| **R8** ✅ | 修 `tests/conftest.py` 的 `reader3.py:187` → 改用符号名；删除 stale pyc 与 `tests/.DS_Store`；`.gitignore` 清掉残留冲突标记（~~加 `tests/**/__pycache__` 与 `.DS_Store`~~ —— 本建议有误，见落地记录） | `tests/` + `.gitignore` | Phase 0 | P2 |
| **R9** ✅ | 本文 §4 论证 1（不可逆性）改写为「派生数据 + 双写回退 ⇒ 可逆，真正的理由是论证 2 与 3」；§7 增加 soak 门槛：Phase 3 开工前 1b E2E 在 CI 连绿 ≥10 次且跨 ≥5 个工作日 | 本文 §4 / §7 | Phase 0 | P1 |
| **R10** ✅ | Phase 3 验收增加：`reader3 --migrate` 原地读写，**禁止**复用摄取路径（`shutil.rmtree` 会抹掉 `notes.json` / `ai_meta.json` / `chroma_db/`） | 技术栈计划 Phase 3 | Phase 0（写约束）/ Phase 3（执行） | P0 |
| **R11** ✅ | testid 命名的机器校验：一条正则 + CI 检查，覆盖原型 138 个站点与生产模板新增项；显式点名那 24 个带前缀但不合规的，防止被当成「已经对了」跳过 | `designs/` + CI | Phase 0.5 | P1 |
| **R12** ✅ | 1b 用例清单显式包含写入路径：四类型各创建一次、改色、删除、笔记保存；断言方式为「刷新后高亮回到同一段文字」而非「fetch 被调用」；S1–S4 各一条正向证据 | `tasks/009-e2e-annotations.md` | Phase 1b | P0 |

JSONL 工件：`docs/plans/20260816-tech-stack-migration/eng-review-tasks.jsonl`

---

### 落地记录（2026-08-16，本报告发出后当场执行）

用户裁决：**维持 Phase 3 在 4B 之前**（不采纳 Codex 的重排）、**维持 soak 门槛数值**（≥10 次 / ≥5 个工作日）；其余 must fix / should fix 按建议执行。R1–R12 **十二项全部执行完毕**，分三批：第一批五项（R1/R2/R3/R9/R10）、第二批两项 P0（R5/R12）、第三批五项 P1–P2（R4/R6/R7/R8/R11）。R4 的代码删除动作已于同日按用户裁决执行。

| 任务 | 改了哪里 |
|---|---|
| **R1** | `tasks/014-ts-frontend-reader.md`：七模块 → 八模块，新增 `commands.ts`（175 行，六个写入方法）；「⚠️ 待评审」块替换为裁定记录含两个落选方案的失败模式；退出门槛新增**依赖方向机器可验**（`dependency-cruiser` / ESLint `import/no-restricted-paths`，不靠人盯） |
| **R2** | `docs/plans/20260817-frontend-ui-refactor/contracts/annotation-host-contracts.md` K5：先立三类处置规则，再全量枚举 9 个成员 —— **7 个纳入**，`book` 与 `getContentDocument()` 标 deprecate 并定于 4B.2 结束移除（两者实测零消费方）。`4B.3` 的 K5 待评审注记同步改为「已确认纳入」 |
| **R9** | 本文 §4 删除论证 1 并记录其被证伪的经过；§7 新增 **soak 门槛**小节 |
| **R10** | 技术栈计划 Phase 3：`--migrate` 硬约束写进任务项，验收新增「迁移后 `notes.json` / `ai_meta.json` / `chroma_db/` 三者字节不变」的测试；本文 §7 门槛表同步 |
| **R3** | 复核确认，无改动 |
| **R5** | K3 的挂载规则从「必须挂在 `.reader-shell` 直下」改为**属性判据 + 两种安全挂法**（`<body>` 直接子元素 / `<dialog>` top layer），并补 `containingBlockAncestor()` 参考实现；属性清单补齐 `perspective` 与 `will-change: filter\|perspective`。`tasks/014-ts-frontend-reader.md` 4B.2 新增「硬约束 2」与退出门槛（结构断言 + 几何断言，三个浮层各一遍）；本文 §7 Phase 4B 行同步 |
| **R12** | 新建 `docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md`：读路径 5 条、**写路径 10 条**、K1–K6 各一条能失败的断言、S1–S4 各一条正向证据；统一收尾动作为「刷新后断言高亮回到同一段文字」。本文 §6/§7、技术栈计划 Phase 1 均改为引用它 |
| **R4** | **代码已删**（用户裁决）：`search_service.py` 移除 `SearchIndex` 类与 `BookIndex.from_book_pkl`，773 → 734 行；`BookIndex` / `ChapterIndex` 两个 dataclass 保留（活代码）。技术栈计划 A5 改写为「合并范围为**三处**」并把删除理由与边界收进引用块；Phase 0 新增 0.7、Phase 2a 退出条件「四处 → 三处」、审查发现表的「四处」标注为已消解 |
| **R6** | 技术栈计划性能章节新增 **C5**（置于 C4 之后，章节标题改为 C1–C5）：`library_view` 为读元数据反序列化了全书正文，是全站最高频路径，而 C1 的跨库搜索是低频路径——**优先级排反了**；修法与 A5 的 `load_book_metadata()` 同源。落点阶段待裁决 |
| **R7** | C1 阈值订正：原文按 `load_book_cached` 的 `maxsize=10` 写「库超 10 本」，真正的约束是 `load_book_index` 的 **`maxsize=4`**（第 5 本就开始颠簸），且 `case_sensitive` 编进了 `lru_cache` key，**有效容量再折半到 2 本**。Phase 1a 基准加「首页冷启动 TTFB × 书库规模」，并要求造 20 本合成 fixture |
| **R8** | `tests/conftest.py` docstring 去掉 `reader3.py:187` 改用符号名；删除 stale pyc（含一个源文件已不存在的 `test_probe_tmp`）与 `tests/.DS_Store`；`.gitignore` 清掉残留的 merge 冲突标记 |
| **R11** | 本文 §6 步骤 0.5 新增两条 lint 的对照表（**选择器 lint 约束测试代码，命名 lint 约束模板与原型**，此前只有前者），命名 lint 给出正则（现已收敛为 §6 步骤 0.5 的 canonical 代码块，见下方 R13）并要求显式点名设计规格 §4.1 那 24 个带前缀但不合规的 testid；§7 Phase 0 退出条件改为「两条 lint 都在 CI 里生效」 |

### 第二轮 Codex 评审的落地记录（2026-08-16 晚）

评审报告全文见 [`review-codex.md`](./review-codex.md)（`gpt-5.6-sol` / `xhigh` / read-only，threadId `01a0094b-e03a-7243-8d66-77706193c9b3`）。共 19 条发现，以下三条已落地。

| 任务 | 落地内容 |
|---|---|
| **R13**（原报告第 4 条，CRITICAL） | **修复 R12 引入的依赖环。** R12 把 K1/K6 的新行为与 S1–S4 的横幅写进了 Phase 1b 的退出门槛，但这些行为分别要到 4B.1 / Phase 3 / 4A.4 才存在，而那些阶段又都以 1b 通过为前置——按原文的顺序跑不通。修法是把「写下来」与「计入门槛」分开：`tasks/009-e2e-annotations.md` 新增 **§0.5 用例分组与激活阶段**（`baseline-1b` / `acceptance-4b1` / `acceptance-p3` / `acceptance-4a4` / `acceptance-2a` 五组），§4 契约表加「组」列并把 K-1 / K-6 各拆成 baseline 现状特征化条与 4B.1 行为变更条，§5 整节移出 1b 门槛，§8 退出门槛重写为「仅 `baseline-1b`」；`tasks/014-ts-frontend-reader.md` 4B.1 / 4B.2 门槛改为「`baseline-1b` 零改动全绿 ＋ `acceptance-4b1` 解开 skip」；本文 §7 的 Phase 1b / 3 / 4A / 4B 四行与 soak 门槛同步 |
| **R14**（原报告第 16 条，MEDIUM） | **命名 lint 正则不可直接复制。** 原文三处（§6 步骤 0.5 的表格、§7 Phase 0 行、R11 记录）都把正则写成 `^(lib\|rd\|set)-…`——Markdown 表格单元格里 `\|` 是必需的转义，但复制进 lint 配置就变成匹配**字面反斜杠加竖线**，永远不命中，lint 会全绿而命名方案毫无约束。§6 步骤 0.5 新增 **canonical 正则代码块**（`^(?:lib\|rd\|set)-[a-z0-9]+(?:-[a-z0-9]+)*$`，非捕获组），其余三处一律改为引用它。同时 `tasks/014-ts-frontend-reader.md` 4B.1 的依赖校验从「ESLint 或 dependency-cruiser 二选一」**定为 `dependency-cruiser`**，并补齐四条规则：`no-circular`（原文缺失）、`commands-no-upward`、**`interactions-no-bypass`**（原文只禁反向 import，挡不住 `interactions` 直连 `notes-api` 这种正向绕过，而那恰是最省事的走法）、`notes-api-leaf` |
| **R15**（原报告第 2 条，MEDIUM） | **R4 删掉的代码，001 的设计文档仍在要求实现。** 运行时代码的删除边界是对的（`src/` 已零引用），但 `specs/_archive/001-search-features/` 四份文档仍把 `SearchIndex` / `from_book_pkl()` / `build_from_library()` 列为待办——任何人照 tasks.md 往下做都会把死代码重新引入。`tasks.md` 的 T027 / T029 / T030 标注为 SUPERSEDED 并划除（T028 与 `BookIndex` dataclass 本身保留，是活代码），`data-model.md`（文首 ＋ §4）、`research.md`（Indexing Strategy 节）、`plan.md`（宪法门槛清单）各加醒目说明并指向 per-book 的 `load_book_index()` |

> 其余 16 条尚未处理，其中三条 HIGH 值得优先看：**第 14 条**（`manifest.json` + `chapters.jsonl` 是两文件提交却没有事务协议，崩溃会留下 manifest 指向半写文件）、**第 15 条**（iframe 门槛「`textContent` 与偏移不变」是必要非充分条件，包裹/拆分文本节点可保持扁平文本相同却改变 DOM path，不足以保护 CFI）、**第 18 条**（§6 说 1b 与 Track D 不阻塞任何人，§7 却让 Phase 3 同时依赖二者——M3 实为三路汇合点）。另有**第 1 条**指出「`commands.ts` 不得碰 DOM」与「纯拆分」无法同时机械满足，已作为未裁决项记入 `tasks/014-ts-frontend-reader.md`。

---

**执行 R2 时抓到一条新事实**：`search.js` 也消费 K5（`getContentRoot` / `onContentsReady`），而契约表原先只写了 annotations。这意味着 **K5 的爆炸半径比 4B.1 大** —— 改接口会同时打断阅读页内搜索。已写进契约与 4B.1 的 K5 产出行。这条正是 Codex「枚举全部活成员」那条规则的直接产物：不逐个核对消费方，就发现不了。

**执行 R5 时抓到一条**：契约里 K3 原写「三个浮层必须挂在 `.reader-shell` 直下」，而生产今天三个浮层都是 `<body>` 直接子元素——**契约在用原型的实现描述规范**，照它改反而会把浮层从合规位置挪进一个只是恰好干净的容器。已改为属性判据（谁都不许在祖先链上造包含块）+ 两种默认安全的挂法。顺带补齐了原清单漏掉的 `perspective` 与 `will-change: filter|perspective`。

**执行 R12 时抓到两条**：(1) 技术栈计划给的 iframe E2E 路径以「断言 `POST /api/notes/*`」收尾，**照字面写就是 wiring-only**——已在原文加修正注，并把「刷新后 `<mark>` 回到同一段文字」定为唯一的通过条件；(2) `server.py` 的 `BOOKS_DIR` 是**模块导入时**读取的进程级常量，所以 E2E 的图书目录隔离必须做到「每 worker 一个服务进程」，运行期换 env 无效——这套用例会真删标注，隔离没做对就是拿开发者自己的书库当靶子。

**执行 R8 时发现我自己的建议有一半是错的**：R8 原本建议给 `.gitignore` 补 `tests/**/__pycache__` 与 `.DS_Store`。`git check-ignore -v` 证明两者**早已被覆盖**——根级的 `__pycache__/`（第 2 行）与 `.DS_Store`（第 13 行）不带前导斜杠，gitignore 语义下匹配任意深度。那些 pyc 之所以在仓库里，是**在规则生效前就被提交过**，加规则治不了已跟踪文件，删文件才治。R8 真正有内容的只剩「删 stale 文件」与「conftest 去行号」两半。

**执行 R7 时抓到一条**：C1 的阈值看错了缓存。这条比它看起来严重——阈值一旦写进 Phase 1a 的性能基准，就成了验收判据；「库超 10 本才颠簸」在一个 `maxsize=4` 的缓存上永远不会触发，跑出来的结论会是「C1 不存在」。**一个错的阈值比没有阈值更糟。** 顺带暴露一个更基础的问题：`books/` 现在只有 1 本书，C1–C5 的全部结论都是**推断而非实测**——单本库里 `maxsize=4` 与 `maxsize=10` 表现完全一致。20 本合成 fixture 因此不是锦上添花，是这几条结论能否被验证的前提。

**顺带清理**：三份计划＋设计规格里剩余的代码行号引用（`search.js:369-370`、`epub-renderer.js:367`、`server.py:1836` / `:2092`、`ai/books.py:57`、`ai/conversations.py:331`、`reader.html:1551-1595`、`toolbar.js:113-114` / `:44-60` 等）全部换成符号名。其中 `routing.py:47` 已经漂了——那行现在是 gemini 分支，Anthropic 的 1M 在 `:51`。「谁都别写行号」这条规矩在两天内自证了两次。

---

### 结论

| 项 | 值 |
|---|---|
| 审查轮次 | 1（三份计划并审 + 源码核验 + Outside Voice） |
| 状态 | **PASS WITH CHANGES** |
| 发现 | 13 条 —— CRITICAL 2 / HIGH 4 / MEDIUM 4 / LOW 3 |
| 已在审查中关闭 | A-1（模块划分选 (a)）、A-2（K5 全量枚举） |
| Outside Voice | Codex，3 问 3 答；Q1/Q2 采纳，Q3 前提被源码证伪、部分采纳 |
| 待办 | R1–R12 **全部闭合** |

**VERDICT: PASS WITH CHANGES** —— 三份计划的事实基础经核验总体可靠，阶段顺序经 Outside Voice 挑战后依然成立（但支撑它的论证要换一条）。开工前必须先落 R1 / R2 / R5 / R10 / R12 五项 P0：前两项解开 4B.1 与 4B.3 的死锁，后三项堵住三个「验收会通过、东西已经坏了」的口子。**五项已于 2026-08-16 全部写入计划**，同日 R4 / R6 / R7 / R8 / R11 五项 P1–P2 也一并落地（见上「落地记录」）。R4 的死代码已实际删除。开工前只剩两个待裁决项（见下），均不阻塞 Phase 0 动工。

**UNRESOLVED DECISIONS:**

- **R6 / C5 首页只读 manifest 的落点** —— C5 已写入性能章节（附录 A），但阶段未定。严格说它依赖 Phase 3 的 `manifest.json` 才成立，放 Phase 2b 需要先出一个过渡版（例如单独缓存一份轻量书目 JSON）。放 2b 并加过渡版／推迟到 Phase 3 一并做，二选一。
- **合同 2 的两项 token 尚未收口** —— 标注暗色变体取显式 `--p-hl-*-dk` 还是 `color-mix`；原型单层 token 名如何映射到规格两层。§3 已给建议与落点（Track D / 4A.1），但仍需你拍板才算冻结。
