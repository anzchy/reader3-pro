# 前端重设计 × 技术栈迁移 —— 合流实施顺序

- **日期**: 2026-08-16
- **状态**: 提议（待批准）

> ### 权威范围
>
> **本文权威**：**顺序**——阶段划分、并行/串行关系、耦合点、阶段门槛、里程碑与分支编号。
>
> **本文不权威**：任何"做什么"和"长什么样"。本文**只索引不复述**——凡是能在下表里找到家的事实，本文只写一句话加链接。
>
> 之所以立这条规矩：此前三份计划各自复述对方的内容，其中三处代码行号引用在 2026-08-16 复核时已全部失效，`annotations.js` 的模块划分与 `data-testid` 的统计数字在两处出现不一致。**每条事实只有一个家。**

| 需要知道 | 去哪里 |
|---|---|
| 技术栈选型、后端架构、存储格式、各阶段做什么、A1–A5 / B1–B4 / C1–C5 | [`20260815-plan-tech-stack-migration.md`](./20260815-plan-tech-stack-migration.md) |
| 双层 token、`data-testid` 命名、组件清单、逐页规格、**iframe 边界（§6.0）**、**降级状态 S1–S5（§6.4）**、响应式、可访问性 | [`20260815-spec-frontend-design.md`](./20260815-spec-frontend-design.md) |
| 原型的性质、**原型 → 生产的翻译规则**、文档分工总表 | [`designs/reader-pro-next/README.md`](../../designs/reader-pro-next/README.md) |
| 现状审计（是什么样）＋ 已拍板的五条产品决策 | [`designs/reader-pro-next/spec/reader-pro-spec.md`](../../designs/reader-pro-next/spec/reader-pro-spec.md) |
| 原型相对现状补齐了什么、还差什么 | [`designs/reader-pro-next/spec/reader-pro-next-parity.md`](../../designs/reader-pro-next/spec/reader-pro-next-parity.md) |
| **标注宿主契约 K1–K6** | [`docs/contracts/annotation-host-contracts.md`](../contracts/annotation-host-contracts.md) |
| **`annotations.js` 八模块拆分**与 4B 各子阶段任务 | [`specs/014-ts-frontend-reader/tasks.md`](../../specs/014-ts-frontend-reader/tasks.md) |
| **Phase 1b E2E 用例清单**（读路径 / 写路径 / K1–K6 / S1–S4） | [`specs/009-e2e-annotations/tasks.md`](../../specs/009-e2e-annotations/tasks.md) |

---

## 1. TL;DR

**先把合同钉死，再让三条线分头跑；它们在 Phase 3 三路汇合，而 Phase 3 与 Phase 4B 必须串行。**

```
Phase 0  合同 + P0 止血  ← 所有事情的前置
   │
   ├──────────────────────────────┬───────────────────────────┐
   ↓                              ↓                           ↓
Phase 1a Python 测试 + CI      Track D 设计补齐            （0.5 完成即可开工）
（阻塞所有后端改动）            S1–S5 + 合同对账            Phase 1b Playwright E2E
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
| C3 | **降级状态** | 后端 → 前端 | 指纹不匹配时 notes/索引分级降级，五个状态（设计规格 §6.4 的 S1–S5）**原型里一个都没有**。没有 UI 就等于静默失败 |
| C4 | **API 形状演进** | 后端 → 前端 | Phase 3 给响应加字段。坚持**加法式演进**则前端永不阻塞；一旦改名或改语义，两条线立刻锁死 |
| C5 | **阅读进度单一数据源** | 行为变更 | 三个消费方跨 4A 与 4B 两个阶段，必须先定义再分头消费 |

除此之外前后端**没有**硬依赖。这就是为什么下面的顺序可以让两条线大段并行。

---

## 3. 开工前必须冻结的四份合同

四份合同都很便宜，但任何一份晚定，后面都是成建制返工。

| # | 合同 | 内容在哪 | 冻结时点 |
|---|---|---|---|
| **合同 1** | `data-testid` | 命名与前缀方案：设计规格 §4；实测对账（134 个唯一 testid，**0 个合规**）：同 §4.1 | Phase 0.5 |
| **合同 2** | Design token | 双层体系与全部取值：设计规格 §3。剩余两项待定见下 | Phase 4A.1 |
| **合同 3** | API 形状 v1 | Phase 1a 的 42 路由契约测试即其可执行形式 | Phase 1a |
| **合同 4** | 消息表 key | 英文为默认 locale（D-2）；key 命名建议 `{page}.{region}.{element}`，与 testid 同构便于对照。原型英文文案即 `en` 初值 | Phase 4A |

**合同 1 的顺序要点**：testid **先在原型里定名，再回贴现有 Jinja 模板**，不能反过来。理由见设计规格 §4.1。这是整套迁移的 strangler-fig 接缝——testid 是唯一横跨新旧两套实现的不变量。

**合同 2 尚未收口的两项**（其余已于 2026-08-16 并入设计规格 §3）：

| 冲突 | 二选一 | 建议 | 落点 |
|---|---|---|---|
| 标注暗色变体 | 规格的 `--p-hl-*-dk` 四个显式值 vs 原型的 `color-mix(… 45%, transparent)` | 取显式值——`color-mix` 在旧 Safari 上要 fallback，而这是标注可读性 | Track D |
| 原型的单层 token 名 | `--canvas` / `--surface` / `--text` / `--anno-*` / `--page-*` 映射到规格的两层 | 以规格的两层为准，一次性映射 | 4A.1 |

**合同 3 的规则**：Phase 2a / 2b 不得改变任何响应形状（纯重构，契约测试即证明）；Phase 3 只能**新增**字段，不得改名、不得改语义、不得改默认值。这是 expand–migrate–contract 的标准做法，也是两条线不互相阻塞的全部秘诀。

---

## 4. 汇合点：为什么 Phase 3 必须在 Phase 4B 之前

Phase 3（存储格式 + 指纹）与 Phase 4B（阅读器外壳重写）都在标注锚定周围施工：Phase 3 改锚定**依赖的数据**，Phase 4B 改锚定**依赖的宿主 DOM**。两者同期进行时，"标注恢复到错误位置"这类问题**无法归因**。方向由两条论证定：

1. **测试可信度**：先重写阅读器则标注 E2E 也随之重写，然后在一套刚出生、尚未被时间检验的测试下迁移用户数据。反过来则是在一套已经跑绿一段时间的 E2E 下迁移。这条要能兑现，前提是**真的等它跑绿一段时间**——见 §7 的 soak 门槛。
2. **已点名的失败模式**：「等价性测试通过，但真实标注已经坏了」要求迁移验收必须跑真实 iframe 标注 E2E。那条 E2E 只有在阅读器 DOM 还没变的时候才是"真实"的基准。

> **原本还有第三条「不可逆性」，已删除——它站不住。** Phase 3 迁移的是 `book.pkl → manifest.json + chapters.jsonl`，属**派生数据**：源头 `book.epub` 就在同一目录且不在变更范围内，`notes.json` / `ai_meta.json` / `chroma_db/` 同样不动；叠加计划已有的双写 + 回退读，回滚动作就是删掉两个新文件。Phase 3 是**可逆**的。
>
> **但"删掉两个新文件"是必要不充分的**，两点补充：(1) 删之前必须确认 `book.pkl` 存在且读得开——`--migrate` 原地读写、不删任何既有文件，正是这个前提的保证条款；(2) 一旦走到技术栈计划里"稳定一个大版本后移除 pickle 写入路径"那一步，pkl 不再新增，此后新处理的书**没有可回退的对象**，回滚动作变成「按 `book.epub` 重新摄取」——而摄取路径会 `rmtree`，所以那时的回滚同样受"原地"约束。可逆性是有保质期的，别把它当成永久属性。写入顺序本身的保证见技术栈计划 Phase 3 的「两文件提交协议」。
>
> 这条是 2026-08-16 eng-review 里 Codex 反向挑战本排序时暴露的：它据此主张把 Phase 3 挪到 4B 之后，前提被源码核验证伪，**排序维持不变，但论据换成上面两条**。
>
> 辩论的副产品是一条真的不可逆风险，与格式无关：`reader3.py` 在写入前 `shutil.rmtree(output_dir)`，而 `notes.json` / `ai_meta.json` / `chroma_db/` 全在 `output_dir` 里。因此 **`reader3 --migrate` 必须原地读写，禁止复用摄取路径**——已写进技术栈计划 Phase 3 的验收。

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

---

## 6. 阶段分解

各阶段**做什么**见技术栈计划 §3；本节只给分解与并行关系。

### Phase 0 —— 合同与止血（目标：一周内，每项独立 PR）

| 编号 | 内容 |
|---|---|
| 0.1 | P0-1：`process_epub()` 的 `shutil.rmtree` 会连 `notes.json` 一起删 |
| 0.2 | P0-2：wheel 打包漏 `static/js` / `static/css` / vendor |
| 0.3 | `--port` / `READER3_PORT` ＋ 新增 `GET /api/health` |
| 0.4 | 四个落后 JS 文件 IIFE 化，`escapeHtml` 全局覆盖修正 |
| 0.5 | **testid 定名：先改原型，再回贴模板**；规则写入 CI lint（**两条不同的 lint**，见下） |
| 0.6 | 事实性修复：`.gitignore` 冲突标记、版本号、`ai_settings.example.json` |
| 0.7 | 删除死代码 `SearchIndex` / `BookIndex.from_book_pkl` / `SearchIndex.build_from_library`（A5 的「第四处」），使 `book_store.py` 的合并范围收敛到三处 |

> **0.5 是两条 lint，不是一条。** 计划此前只写了前者，后者一直没有归宿：
>
> | lint | 约束谁 | 规则 |
> |---|---|---|
> | **选择器 lint** | 测试代码（`tests/e2e/`） | 只允许 `data-testid` 与 ARIA role/name；禁止 class 选择器、`nth-child`、层级结构选择器 |
> | **命名 lint** | 模板与原型（`templates/*.html`、`designs/reader-pro-next/`） | 每个 `data-testid` 必须匹配**下方的 canonical 正则**（前缀方案见设计规格 §4） |
>
> 只有前者不足以保住契约：选择器 lint 全绿，模板里照样可以新增 `reader-search-hit` 这种名字，命名方案随即失守。命名 lint 必须**显式点名设计规格 §4.1 那 24 个带 `reader-` / `library-` 前缀的 testid**——它们形似合规，批量改名时最容易被当成「已经对了」跳过，而正则会把它们判为不合规，正是要的效果。134 个全部需要改名，lint 的初始状态就是「134 条违规」，改完归零。

#### canonical 正则（唯一真相源）

配置 lint 时**从这个代码块复制，不要从上面的表格里复制**：Markdown 表格单元格内的 `|` 必须写成 `\|`，直接复制出去会得到 `^(lib\|rd\|set)-…`，它匹配的是**字面的反斜杠加竖线**，永远不会命中任何 testid——lint 会全绿，而命名方案毫无约束。

```regex
^(?:lib|rd|set)-[a-z0-9]+(?:-[a-z0-9]+)*$
```

改用非捕获组 `(?:…)` 是因为这里只做匹配、不取分组；捕获组在部分 lint 工具里会被当作提取意图。

### 并行区间（Phase 0 之后）

三条线**开工时**彼此不阻塞——但它们**不是各自跑到底**：三条线全都是 Phase 3 的前置，Phase 3 是一个三路汇合点。完整依赖图见 §9.1。

- **线 1 后端**：`1a → 2a → 2b → 3`。1a 是全局阻塞（也在这里冻结合同 3 与性能基准）。
- **线 2 E2E**：`1b`。依赖 0.3（端口/健康探针）与 0.5（testid）。用例清单见 [`specs/009-e2e-annotations/tasks.md`](../../specs/009-e2e-annotations/tasks.md)——**必须含写路径**，否则 4B.1 的「零改动全绿」门槛是空的。
  **1b 阻塞两处，不是一处**：直接阻塞 4A，同时通过 §7 的 soak 门槛阻塞 Phase 3。它不阻塞 2a / 2b，但"不阻塞后端"是错的说法——2b 做完之后，Phase 3 还要等 1b 攒够 10 次连绿、跨度 5 个工作日。
- **线 3 Track D 设计**：产出 = 设计规格 §6.4 的 S1–S5 落进原型（本轨最大的一块）＋ §4.1 的 testid 批量改名（喂给 0.5）＋ loading 骨架屏 ＋ §3 合同 2 剩余两项。
  **Track D 阻塞 Phase 3**：Phase 3 要求 S1–S4 在 UI 里可见（技术栈计划 Phase 3 验收），S1–S5 的原型是 Track D 的产出。

> **这三条线为什么值得单独盯**：单人维护者按状态切换时，最容易发生的失败是"后端一路推到 Phase 3 门口，才发现 1b 的 soak 计时还没开始、S1–S5 的原型还没画"。soak 是**日历时间**，补不回来——1b 必须尽早开始连绿，不能留到 2b 做完再启动。

> **单人维护者说明**：这里的"并行"不是要同时开三个窗口，而是三条线之间无阻塞，可按状态自由切换、随时暂停。

### Phase 4A —— 前端底座与非阅读页

进入条件：`1b` 主 CI 绿灯。与 `2a / 2b / 3` 并行。

| 子阶段 | 内容 |
|---|---|
| 4A.0 | Vite + 严格 TS + `dist/` 提交 + CI 可重复构建校验 + wheel 内容测试 |
| 4A.1 | 两层 token 落地 + 主题基础设施 + `<head>` 内联 stamp |
| 4A.2 | `settings` 页垂直切片（试点） |
| 4A.3 | 共享模块 `api.ts` / `sse.ts` / `escape.ts` / `idb.ts` / `debug.ts` / `messages.ts` |
| 4A.4 | `library` 页垂直切片 ＋ 删除 Classic；落 S2/S3/S4 与 C5 的书库卡片侧 |

> **为什么把主题基础设施提前到 4A.1**：token 与 `data-theme` 是全站的，settings 与 library 也要用。放到最后意味着前两页先用旧色、再回头改一遍。拆开之后「主题**能力**」在 4A.1，「阅读主题**面板**」在 4B.3。

> **每页切片的内部顺序**：markup（testid 已由 0.5 冻结）→ TS 模块 → 新 CSS，一个 PR 两个 commit。E2E 全程不改——它就是这次切换正确性的证明。

### Phase 4B —— 阅读器

进入条件：**Phase 3 完成** 且 **4A.4 完成**（工具链已在两页上验证过）。

四个子阶段 4B.1–4B.4 的任务清单见 [`specs/014-ts-frontend-reader/tasks.md`](../../specs/014-ts-frontend-reader/tasks.md)。顺序上只有一条硬约束：**4B.1（`annotations.js` 拆分）必须在 4B.2（外壳重写）之前**——外壳重写会移动工具条 DOM，而工具条 UI 目前就长在 `annotations.js` 里；先拆分，外壳就只与一个有文档的模块边界打交道，而不是散落在 1127 行里的七个 `getElementById` 和一处隐式的 `position: fixed` 假设。

外壳与标注之间只有六个接触面（K1–K6），**其中四条坏了不报错**。契约与验收见 [`annotation-host-contracts.md`](../contracts/annotation-host-contracts.md)。

### Phase 5 —— launch + PWA

`reader3 launch` 复用 0.3 已加好的 `/api/health`。PWA service worker 缓存策略按 A4。

---

## 7. 阶段门槛表

| 阶段 | 进入条件 | 退出条件 |
|---|---|---|
| Phase 0 | — | P0-1/P0-2 修复并人工 smoke；`--port` 与 `/api/health` 可用；testid 在原型与模板两侧一致；**两条 lint 都在 CI 里生效**——选择器 lint（约束 `tests/e2e/`）与命名 lint（约束模板与原型，正则以 §6 步骤 0.5 的 **canonical 代码块**为准，违规数归零） |
| Phase 1a | Phase 0 | CI 绿灯成为合并门槛；42 路由契约测试通过；**API v1 形状冻结**；性能基准记录在案 |
| Phase 1b | 0.3 + 0.5 | **`baseline-1b` 组**在**主 CI**（非 nightly）绿灯；**用例覆盖写路径**（四类型创建 / 改色 / 删除 / 笔记保存，断言为刷新后回到同一段文字）；K2–K5 与 K1/K6 的**现状特征化**条各一条正向证据；连续 3 次全量运行零 flaky；其余组**用例写完并 review**，以 skip 形态存在。⚠️ K1/K6 的新行为与 S1–S4 的横幅**不在本阶段门槛内**——它们要到 4B.1 / Phase 3 / 4A.4 才存在，写进 1b 会形成依赖环。分组见 [`specs/009-e2e-annotations/tasks.md`](../../specs/009-e2e-annotations/tasks.md) §0.5 |
| Track D | Phase 0 | S1–S5 设计完成并回写设计规格 §6.4；合同 2 剩余两项收口；loading 骨架屏补齐 |
| Phase 2a | 1a | 每个 router < 500 行；`book_store` **三处** loader 合并（第四处已作为死代码删除，见 A5）；**notes 乐观并发落地**；行为不变由 1a 证明 |
| Phase 2b | 2a | 跨库搜索性能相对基准可量化改善；`_normalize_with_map` 差分测试通过 |
| Phase 3 | 2b + Track D **且 soak 门槛达标**（三路汇合，见 §9.1） | 新书完全不依赖 pickle；存量可一键迁移；**`--migrate` 原地读写，不复用摄取路径**；**S1–S4 在当时的 UI 里可见**——即 **`acceptance-p3` 组解开 skip 并绿灯**（朴素横幅形态）；真实 iframe 标注迁移 E2E 通过 |
| Phase 4A | 1b | wheel 内容测试通过；settings 与 library 切换后 `baseline-1b` **零改动**全绿；**4A.4 另需 `acceptance-4a4` 组解开 skip 并绿灯**（S1–S4 改版形态）；Classic 已删除 |
| Phase 4B | Phase 3 **且** 4A.4 | 拆分后 `baseline-1b` 全绿；**4B.1 另需 `acceptance-4b1` 组解开 skip 并绿灯**（K1 响亮失败、K6 抛错——这两条行为本阶段才产生）；各模块 ≤400 行；依赖方向机器可验（`dependency-cruiser` 四条规则，见 [`specs/014-ts-frontend-reader/tasks.md`](../../specs/014-ts-frontend-reader/tasks.md) 4B.1「依赖规则」）；**iframe 内部改动不超出设计规格 §6.0 允许的范围**（判据以 §6.0「判定标准（canonical）」为准的**三重断言 A/B/C**，本表不复述）；**三个浮层过 `containingBlockAncestor() === null`，且工具条位置用矩形几何断言**（4B.2 硬门槛，K3）；**K1–K6 各有一条能失败的断言**；进度值全站一致 |
| Phase 5 | 4B | 单命令进入阅读；PWA 版本切换不撕裂 |

### soak 门槛（Phase 3 专用）

§4 论证 1 的原话是「在一套**已经跑绿一段时间**的 E2E 下迁移」。这句话不量化就是空话——一套只跑过一次的 E2E 和一套跑绿两周的 E2E，保护力不是一个量级，而本仓库今天**零 CI 历史**。

**Phase 3 开工前，`baseline-1b` 组必须在主 CI 上连续绿 ≥ 10 次，且跨度 ≥ 5 个工作日。**

> 数的只是 `baseline-1b`。其余组在 Phase 3 之前尚未激活（它们测的行为还不存在），把它们算进来就会让 soak 门槛永远无法达标——分组定义见 [`specs/009-e2e-annotations/tasks.md`](../../specs/009-e2e-annotations/tasks.md) §0.5。

- 「连续」指中途任何一次红都清零重计——flaky 与 broken 在这里不做区分，一条会偶发失败的 E2E 当不了数据迁移的验收基准。
- 跨度条款是为了逼出**时间维度**的不稳定（缓存、时区、依赖漂移、并发），这类问题在同一天连跑十次是照不出来的。
- 这道门槛只卡 Phase 3。Phase 4A 不受影响，可继续并行推进。

> 来源：2026-08-16 eng-review 的 Outside Voice。Codex 主张把 Phase 3 整体挪到 4B 之后，理由之一是「Phase 1 的测试尚无 CI 历史，保护力未经检验」。排序未采纳（见 §4），但这半句成立，转为本门槛。

---

## 8. 风险与对应

| 风险 | 对应 |
|---|---|
| **有人直接把原型 React 代码搬进生产** | 翻译规则写死在 `designs/reader-pro-next/README.md`，并在原型显眼处标注其性质 |
| **testid 定名拖到 1b 之后** | 头号返工源。0.5 是 Phase 0 的硬门槛，不得顺延 |
| **Phase 3 与 4B 抢跑** | §4 的串行是硬约束；4B 的进入条件写死为"Phase 3 完成" |
| **外壳重写静默打断标注** | K1–K6 各配一条**能失败**的断言，而不是断言"元素存在"。K3（`position: fixed` 被祖先 transform 击穿）与 K6（URL 回退解析出错章号）最隐蔽 |
| **降级状态没有 UI** | 写成 Phase 3 的退出门槛，先用朴素横幅落到旧模板，Phase 4 再按设计重做 |
| **API 悄悄改形状导致两条线互锁** | 合同 3 的加法式演进；契约测试是可执行的护栏 |
| **三份文档互相复述导致漂移** | 本文顶部的权威范围表；每条事实只有一个家；**任何文档都不写代码行号** |
| 单人维护者时间碎片化 | 三条线开工时互不阻塞；每个子阶段独立可交付、可暂停。**但三条线都在 Phase 3 汇合**（§9.1），碎片化的代价会在那里一次性结算 |
| **1b / Track D 被排到后端线之后** | 二者都是 Phase 3 的前置，且 1b 的 soak 是**日历时间**、补不回来。§9.1 把它们标为「Phase 0 一结束就动」 |

---

## 9. 里程碑与分支（唯一真相源）

沿用 `{number}-{short-name}` 惯例。**这是全仓库分支编号的唯一定义处**——技术栈计划 §6 曾有一份冲突的编号表，已删除。

| 里程碑 | 内容 | 分支 |
|---|---|---|
| M0 | Phase 0 合同与止血 | `007-hygiene-and-contracts` |
| M1 | Phase 1a 测试 + CI + API 冻结 | `008-test-safety-net` |
| M1b | Phase 1b Playwright E2E | `009-e2e-annotations` |
| MD | Track D 设计补齐（仅改 `designs/` 与规格） | `010-design-degradation-states` |
| M2 | Phase 2a + 2b | `011-backend-refactor` |
| M3 | Phase 3 存储迁移 | `012-storage-format` |
| M4a | Phase 4A 底座 + settings + library | `013-ts-frontend-shell` |
| M4b | Phase 4B 阅读器 | `014-ts-frontend-reader` |
| M5 | Phase 5 launch + PWA | `015-launch-experience` |

M1b 与 MD 可与 M1/M2 交错推进；M4a 可与 M2/M3 交错推进；**M3 与 M4b 严格串行**。

每个分支的任务清单放在 `specs/{分支名}/tasks.md`，不写进本文。

### 9.1 依赖图（canonical）

§6「并行区间」讲的是**能同时开工的三条线**，本表讲的是**每个阶段真正等谁**。两者视角不同，冲突时以本表为准。

| 阶段 | 前置（全部满足才能进） | 它阻塞谁 |
|---|---|---|
| Phase 0 | — | 全部 |
| Phase 1a | 0 | 2a |
| Phase 1b | 0.3 + 0.5 | 4A；**Phase 3**（经 soak 门槛） |
| Track D | 0 | **Phase 3**（S1–S5 原型） |
| Phase 2a | 1a | 2b |
| Phase 2b | 2a | Phase 3 |
| **Phase 3** | **2b ＋ Track D ＋ 1b 的 soak** ——三路汇合 | 4B |
| Phase 4A | 1b | 4B（其中 4A.4 项） |
| Phase 4B | Phase 3 ＋ 4A.4 | 5 |
| Phase 5 | 4B | — |

关键路径：`0 → 1a → 2a → 2b → 3 → 4B → 5`。1b 与 Track D 不在关键路径上，**但它们的完成时间必须早于 2b 结束**，否则 Phase 3 干等——而 1b 那份等待是 soak 的日历时间，无法压缩。结论是：**1b 与 Track D 要在 Phase 0 一结束就动，不能排到 2a/2b 之后**。

---

*本文只做顺序与接口，不重开任何已定技术选型：后端留 Python、不上 SPA 框架、不做 Electron/Tauri、不换嵌入模型与向量库。*

---

## GSTACK REVIEW REPORT

**审查对象**：三份计划并审 —— 本文（顺序）、`20260815-plan-tech-stack-migration.md`（架构）、`20260815-spec-frontend-design.md`（设计），外加对其事实性断言的源码核验。
**审查日期**：2026-08-16 ｜ **分支**：`master` ｜ **Outside Voice**：Codex（`codex exec`，read-only）

**流程偏差（先说清）**：本技能规定每条发现用 AskUserQuestion 逐条 STOP 确认。本次会话以「执行 1-4，然后继续 eng-review」恢复且要求不再提问，故所有需要用户拍板的项改为汇总到文末 **UNRESOLVED DECISIONS**，不在中途打断。

---

### 1. 架构（Architecture）

#### A-1 [CRITICAL] 4B.1 的模块划分漏掉整条标注写入路径 —— 置信度 **9/10**

`specs/014-ts-frontend-reader/tasks.md` 的七模块表把 `interactions.ts` 描述为：

> `constructor`（减去七行 `qs()`）`init` `onAnnotationClick` `getExistingMarkerIds` `onSelection` … `copySelection` `askAi` ＋ `initAnnotations`

逐符号核对 `annotations.js`：`AnnotationUI` 有 **30 个方法**，上游计划记为 24。差额六个是 `toggleMarkerAnnotation` / `toggleAnnotation` / `deleteCurrentAnnotation` / `saveNote` / `deleteAnnotations` / `createAnnotation`，约 174 行，构成从 `handleAction`（已指派 `interactions.ts`）到三处 `fetch`（已指派 `notes-api.ts`）之间的完整写入链。七个模块的行数估算合计 1055，文件实际 1127 —— 差额与这六个方法吻合。

按行号区间机械切分会把它们塞进 `note-editor.ts`，于是 `createAnnotation`（marker / wavy / underline / note **四种类型共用的唯一写入口**）住进一个叫「笔记编辑器」的模块，同时 `notes-api.ts` 与 `note-editor.ts` 双双声称拥有那三处 `fetch`。

**裁定：采用方案 (a)，新增第八个模块 `commands.ts`**，依赖方向 `interactions → commands → notes-api` 单向。Codex 独立给出同一结论，并点名两个落选项的失败模式：(b) 折进 `notes-api` 是**层级塌缩**，传输层被 UI 状态与渲染污染，最终长成 god service；(c) 只做文件切分不做职责切分是**装饰性模块化**，667 行的隐式耦合与过宽的可变权限原样保留，拿不到单测边界。

> `specs/014-*/tasks.md` 的「⚠️ 待评审」块与 `contracts/annotation-host-contracts.md` 均指向本报告，**此项就此关闭**。

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
| 高保真目标原型（三屏 + 错误态） | `designs/reader-pro-next/` | 可跑，134 个 testid 待改名 |
| K1–K6 宿主契约 | `docs/contracts/` | 已成文，本报告后需改 K5 |
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
| **R1** ✅ | 4B.1 采用方案 (a)，新增 `commands.ts` 承载六个写入方法；写死 `interactions → commands → notes-api` 单向依赖；删除 tasks.md 的「⚠️ 待评审」块 | `specs/014-*/tasks.md` | Phase 0 | P0 |
| **R2** ✅ | K5 扩展到 `Reader3Epub` 全部 9 个成员，每个落到「纳入 / deprecate+移除阶段 / 收窄契约名义」三类之一；`applyThemeSettings` 与 `displaySectionIndex` 纳入 | `docs/contracts/annotation-host-contracts.md` | Phase 0 | P0 |
| **R3** ✅ | K1 补一句：缺任一元素 → `init()` 静默 return → 整个标注 UI 不启动（已改，本项为复核） | 同上 | Phase 0 | P2 |
| **R4** ✅ | 删除死代码 `SearchIndex` / `BookIndex.from_book_pkl` / `SearchIndex.build_from_library`；技术栈计划 A5 改为「三处合并」 | `search_service.py` + A5 | Phase 0 | P1 |
| **R5** ✅ | 4B.2 增加门槛：三浮层保持 `<body>` 直接子元素（或 `<dialog>` top-layer）；E2E 断言祖先链无 containing-block 属性、且浮层矩形与选区矩形相对位置正确 | `specs/014-*/tasks.md` + 本文 §7 | Phase 0（写门槛）/ 4B.2（执行） | P0 |
| **R6** ✅ | 新增 **C5**：`library_view` 改为只读 `manifest.json`，不反序列化正文 | 技术栈计划 §性能 + Phase 2b | Phase 2b | P1 |
| **R7** ✅ | C1 阈值订正为「第 5 本」并说明 `case_sensitive` 进 key 使有效容量再半；Phase 1a 基准加「首页冷启动 TTFB × 书库规模」；造 20 本合成书库 fixture | 技术栈计划 §性能 + Phase 1a | Phase 1a | P1 |
| **R8** ✅ | 修 `tests/conftest.py` 的 `reader3.py:187` → 改用符号名；删除 stale pyc 与 `tests/.DS_Store`；`.gitignore` 清掉残留冲突标记（~~加 `tests/**/__pycache__` 与 `.DS_Store`~~ —— 本建议有误，见落地记录） | `tests/` + `.gitignore` | Phase 0 | P2 |
| **R9** ✅ | 本文 §4 论证 1（不可逆性）改写为「派生数据 + 双写回退 ⇒ 可逆，真正的理由是论证 2 与 3」；§7 增加 soak 门槛：Phase 3 开工前 1b E2E 在 CI 连绿 ≥10 次且跨 ≥5 个工作日 | 本文 §4 / §7 | Phase 0 | P1 |
| **R10** ✅ | Phase 3 验收增加：`reader3 --migrate` 原地读写，**禁止**复用摄取路径（`shutil.rmtree` 会抹掉 `notes.json` / `ai_meta.json` / `chroma_db/`） | 技术栈计划 Phase 3 | Phase 0（写约束）/ Phase 3（执行） | P0 |
| **R11** ✅ | testid 命名的机器校验：一条正则 + CI 检查，覆盖原型 134 个与生产模板新增项；显式点名那 24 个带前缀但不合规的，防止被当成「已经对了」跳过 | `designs/` + CI | Phase 0.5 | P1 |
| **R12** ✅ | 1b 用例清单显式包含写入路径：四类型各创建一次、改色、删除、笔记保存；断言方式为「刷新后高亮回到同一段文字」而非「fetch 被调用」；S1–S4 各一条正向证据 | `specs/009-*/tasks.md` | Phase 1b | P0 |

JSONL 工件：`docs/plans/20260816-eng-review-tasks.jsonl`

---

### 落地记录（2026-08-16，本报告发出后当场执行）

用户裁决：**维持 Phase 3 在 4B 之前**（不采纳 Codex 的重排）、**维持 soak 门槛数值**（≥10 次 / ≥5 个工作日）；其余 must fix / should fix 按建议执行。R1–R12 **十二项全部执行完毕**，分三批：第一批五项（R1/R2/R3/R9/R10）、第二批两项 P0（R5/R12）、第三批五项 P1–P2（R4/R6/R7/R8/R11）。R4 的代码删除动作已于同日按用户裁决执行。

| 任务 | 改了哪里 |
|---|---|
| **R1** | `specs/014-*/tasks.md`：七模块 → 八模块，新增 `commands.ts`（175 行，六个写入方法）；「⚠️ 待评审」块替换为裁定记录含两个落选方案的失败模式；退出门槛新增**依赖方向机器可验**（`dependency-cruiser` / ESLint `import/no-restricted-paths`，不靠人盯） |
| **R2** | `docs/contracts/annotation-host-contracts.md` K5：先立三类处置规则，再全量枚举 9 个成员 —— **7 个纳入**，`book` 与 `getContentDocument()` 标 deprecate 并定于 4B.2 结束移除（两者实测零消费方）。`4B.3` 的 K5 待评审注记同步改为「已确认纳入」 |
| **R9** | 本文 §4 删除论证 1 并记录其被证伪的经过；§7 新增 **soak 门槛**小节 |
| **R10** | 技术栈计划 Phase 3：`--migrate` 硬约束写进任务项，验收新增「迁移后 `notes.json` / `ai_meta.json` / `chroma_db/` 三者字节不变」的测试；本文 §7 门槛表同步 |
| **R3** | 复核确认，无改动 |
| **R5** | K3 的挂载规则从「必须挂在 `.reader-shell` 直下」改为**属性判据 + 两种安全挂法**（`<body>` 直接子元素 / `<dialog>` top layer），并补 `containingBlockAncestor()` 参考实现；属性清单补齐 `perspective` 与 `will-change: filter\|perspective`。`specs/014-*/tasks.md` 4B.2 新增「硬约束 2」与退出门槛（结构断言 + 几何断言，三个浮层各一遍）；本文 §7 Phase 4B 行同步 |
| **R12** | 新建 `specs/009-e2e-annotations/tasks.md`：读路径 5 条、**写路径 10 条**、K1–K6 各一条能失败的断言、S1–S4 各一条正向证据；统一收尾动作为「刷新后断言高亮回到同一段文字」。本文 §6/§7、技术栈计划 Phase 1 均改为引用它 |
| **R4** | **代码已删**（用户裁决）：`search_service.py` 移除 `SearchIndex` 类与 `BookIndex.from_book_pkl`，773 → 734 行；`BookIndex` / `ChapterIndex` 两个 dataclass 保留（活代码）。技术栈计划 A5 改写为「合并范围为**三处**」并把删除理由与边界收进引用块；Phase 0 新增 0.7、Phase 2a 退出条件「四处 → 三处」、审查发现表的「四处」标注为已消解 |
| **R6** | 技术栈计划性能章节新增 **C5**（置于 C4 之后，章节标题改为 C1–C5）：`library_view` 为读元数据反序列化了全书正文，是全站最高频路径，而 C1 的跨库搜索是低频路径——**优先级排反了**；修法与 A5 的 `load_book_metadata()` 同源。落点阶段待裁决 |
| **R7** | C1 阈值订正：原文按 `load_book_cached` 的 `maxsize=10` 写「库超 10 本」，真正的约束是 `load_book_index` 的 **`maxsize=4`**（第 5 本就开始颠簸），且 `case_sensitive` 编进了 `lru_cache` key，**有效容量再折半到 2 本**。Phase 1a 基准加「首页冷启动 TTFB × 书库规模」，并要求造 20 本合成 fixture |
| **R8** | `tests/conftest.py` docstring 去掉 `reader3.py:187` 改用符号名；删除 stale pyc（含一个源文件已不存在的 `test_probe_tmp`）与 `tests/.DS_Store`；`.gitignore` 清掉残留的 merge 冲突标记 |
| **R11** | 本文 §6 步骤 0.5 新增两条 lint 的对照表（**选择器 lint 约束测试代码，命名 lint 约束模板与原型**，此前只有前者），命名 lint 给出正则（现已收敛为 §6 步骤 0.5 的 canonical 代码块，见下方 R13）并要求显式点名设计规格 §4.1 那 24 个带前缀但不合规的 testid；§7 Phase 0 退出条件改为「两条 lint 都在 CI 里生效」 |

### 第二轮 Codex 评审的落地记录（2026-08-16 晚）

评审报告全文见 [`20260816-review-codex-ui-migration-sequencing.md`](./20260816-review-codex-ui-migration-sequencing.md)（`gpt-5.6-sol` / `xhigh` / read-only，threadId `01a0094b-e03a-7243-8d66-77706193c9b3`）。共 19 条发现，以下三条已落地。

| 任务 | 落地内容 |
|---|---|
| **R13**（原报告第 4 条，CRITICAL） | **修复 R12 引入的依赖环。** R12 把 K1/K6 的新行为与 S1–S4 的横幅写进了 Phase 1b 的退出门槛，但这些行为分别要到 4B.1 / Phase 3 / 4A.4 才存在，而那些阶段又都以 1b 通过为前置——按原文的顺序跑不通。修法是把「写下来」与「计入门槛」分开：`specs/009-*/tasks.md` 新增 **§0.5 用例分组与激活阶段**（`baseline-1b` / `acceptance-4b1` / `acceptance-p3` / `acceptance-4a4` / `acceptance-2a` 五组），§4 契约表加「组」列并把 K-1 / K-6 各拆成 baseline 现状特征化条与 4B.1 行为变更条，§5 整节移出 1b 门槛，§8 退出门槛重写为「仅 `baseline-1b`」；`specs/014-*/tasks.md` 4B.1 / 4B.2 门槛改为「`baseline-1b` 零改动全绿 ＋ `acceptance-4b1` 解开 skip」；本文 §7 的 Phase 1b / 3 / 4A / 4B 四行与 soak 门槛同步 |
| **R14**（原报告第 16 条，MEDIUM） | **命名 lint 正则不可直接复制。** 原文三处（§6 步骤 0.5 的表格、§7 Phase 0 行、R11 记录）都把正则写成 `^(lib\|rd\|set)-…`——Markdown 表格单元格里 `\|` 是必需的转义，但复制进 lint 配置就变成匹配**字面反斜杠加竖线**，永远不命中，lint 会全绿而命名方案毫无约束。§6 步骤 0.5 新增 **canonical 正则代码块**（`^(?:lib\|rd\|set)-[a-z0-9]+(?:-[a-z0-9]+)*$`，非捕获组），其余三处一律改为引用它。同时 `specs/014-*/tasks.md` 4B.1 的依赖校验从「ESLint 或 dependency-cruiser 二选一」**定为 `dependency-cruiser`**，并补齐四条规则：`no-circular`（原文缺失）、`commands-no-upward`、**`interactions-no-bypass`**（原文只禁反向 import，挡不住 `interactions` 直连 `notes-api` 这种正向绕过，而那恰是最省事的走法）、`notes-api-leaf` |
| **R15**（原报告第 2 条，MEDIUM） | **R4 删掉的代码，001 的设计文档仍在要求实现。** 运行时代码的删除边界是对的（`src/` 已零引用），但 `specs/_archive/001-search-features/` 四份文档仍把 `SearchIndex` / `from_book_pkl()` / `build_from_library()` 列为待办——任何人照 tasks.md 往下做都会把死代码重新引入。`tasks.md` 的 T027 / T029 / T030 标注为 SUPERSEDED 并划除（T028 与 `BookIndex` dataclass 本身保留，是活代码），`data-model.md`（文首 ＋ §4）、`research.md`（Indexing Strategy 节）、`plan.md`（宪法门槛清单）各加醒目说明并指向 per-book 的 `load_book_index()` |

> 其余 16 条尚未处理，其中三条 HIGH 值得优先看：**第 14 条**（`manifest.json` + `chapters.jsonl` 是两文件提交却没有事务协议，崩溃会留下 manifest 指向半写文件）、**第 15 条**（iframe 门槛「`textContent` 与偏移不变」是必要非充分条件，包裹/拆分文本节点可保持扁平文本相同却改变 DOM path，不足以保护 CFI）、**第 18 条**（§6 说 1b 与 Track D 不阻塞任何人，§7 却让 Phase 3 同时依赖二者——M3 实为三路汇合点）。另有**第 1 条**指出「`commands.ts` 不得碰 DOM」与「纯拆分」无法同时机械满足，已作为未裁决项记入 `specs/014-*/tasks.md`。

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

- **R6 / C5 首页只读 manifest 的落点** —— C5 已写入技术栈计划性能章节，但阶段未定。严格说它依赖 Phase 3 的 `manifest.json` 才成立，放 Phase 2b 需要先出一个过渡版（例如单独缓存一份轻量书目 JSON）。放 2b 并加过渡版／推迟到 Phase 3 一并做，二选一。
- **合同 2 的两项 token 尚未收口** —— 标注暗色变体取显式 `--p-hl-*-dk` 还是 `color-mix`；原型单层 token 名如何映射到规格两层。本文 §3 已给建议与落点（Track D / 4A.1），但仍需你拍板才算冻结。
