# `Reader3Epub.getDebugState()`：只读的阅读器状态观测面

> 状态：**草案（2026-09-28）**，未开分支；~~分支号未分配（见 WI-0）~~ ⬛ 2026-09-30 分支号已分配：`020-debug-state`（迁移计划 §9 ＋ 进度盘 ⟂ 已登记，WI-0 第 1 步因此已完成）。
> 出处：[`docs/references/ui-e2e-debug-mcp-bridge-survey.md`](../references/ui-e2e-debug-mcp-bridge-survey.md) §9 的推荐方案；借鉴对象是 paper-one 的 `tauri-plugin-mcp-bridge`（[`docs/references/paper-one-cli-and-mcp-bridge.md`](../references/paper-one-cli-and-mcp-bridge.md) Part B）。
> 本文是独立计划，不属于 `20260816-tech-stack-migration/` 或 `20260817-frontend-ui-refactor/` 的「权威范围」。它会改动后者的 K5 接口计数，具体见 WI-0。

## 1. 目标与非目标

**目标**：给驱动阅读页的任何工具提供一个统一入口，调用一次 `evaluate` 就能拿到阅读器的语义状态，不需要进入 epub.js 的 iframe。适用的工具包括 pytest-playwright、gstack `/browse`、playwright-mcp、chrome-devtools-mcp。

```js
// 在任何驱动里：
JSON.stringify(window.Reader3Epub.getDebugState())
```

```bash
# gstack /browse 示例
$B goto http://127.0.0.1:8123/read/dracula_data/3
$B js "JSON.stringify(window.Reader3Epub.getDebugState())"
```

从 paper-one 借鉴的**只有一点**：bridge 能让外部读到应用自己的语义状态。它的其余部分都不照搬，包括应用内 WebSocket、MCP server、IPC 通道和编译期开关。理由见调研报告 §8–§9，简要说：本项目本来就是 CDP 能直接驱动的普通网页，再开一个端口，会扩大 [ADR-0012](../adr/0012-security-boundaries.md):67 已经承认的本机缺口。

**非目标**：
- 不新增服务端端点、端口、依赖或 MCP server。
- 不改写入路径。getter 不能触发渲染、翻页、`locations.generate()` 或事件派发。
- 不接管交互。点击、划选、写标注仍然要通过 `frame_locator` 或 `/browse frame` 进入 iframe 操作。
- 不修复现有的进度口径分歧（D7）。那是 WI-19 的事，本计划只**如实报告**现有的几种口径。

## 2. 事实基础（2026-09-28 核对）

| # | 事实 | 证据 | 对设计的约束 |
|---|---|---|---|
| F1 | `window.Reader3Epub` 目前有 9 个成员，只在 renderer 成功初始化后赋值 | `src/reader3_app/web/static/js/epub-renderer.js:375-401` | getter 挂在这个对象上。renderer 提前 `return` 时（无 `#epub-viewer`、`epubAvailable` 为假、`window.ePub` 缺失、`ePub()` 抛错，见 `:13`、`:21-38`），`Reader3Epub` 本身是 `undefined`，调用方以此判断「renderer 未初始化」 |
| F2 | 全仓库没有任何地方调用 `book.locations.generate()` | `grep -rn locations.generate src frontend/src tests` 结果为空 | epub.js 的 `start.percentage` **永远是数字 0**，不是 `undefined`。getter 不能照抄这个值。书内总进度只能如实报 `null` |
| F3 | 底部进度 pill 显示的是**章内**页码比例 `displayed.page / displayed.total`；笔记面板用的是章节序号比例 | `epub-renderer.js:235-248`；`notes-panel.js:75-78` | 这就是缺陷 D7（`plan-frontend-ui-refactor.md:90`）。getter 分字段报告两种口径，不做合并 |
| F4 | `relocated` 事件只更新 DOM 文本，不保存位置；但 epub.js 自己在派发 RELOCATED 前把位置缓存在 `rendition.location`（初值 `void 0`，只有 `start && end` 都有时才写入）。相反，`rendition.currentLocation()` **不是纯读**：它走 `manager.currentLocation()` → `paginatedLocation()`（`getBoundingClientRect`，强制 reflow）并改写 `manager.location`，manager 返回 Promise 时它返回 `undefined` | `epub-renderer.js:303`；`static/vendor/epub.min.js`（`Rendition.currentLocation` / `reportLocation`） | CFI 在调用时读缓存 `rendition.location`（评审 D3），**不调用** `currentLocation()`。首次渲染前拿到的是 `null` |
| F5 | 没有可直接计数的内存标注列表：`AnnotationRenderer.lastAnnotations` 只初始化为 `[]`，之后从未赋值 | `annotations.js:500` | 标注数量从 iframe 内的高亮 mark 上的 `data-annotation-ids`（JSON 数组，`annotations.js:484`）去重计数。字段名必须写明「本章已渲染」，因为未匹配上的孤儿标注不会产生 mark |
| F6 | `Reader3NotesDiag.entries()` 按时间正序返回最多 100 条副本，每条字段为 `{op, requested, status, ok, id, t}`。**只有写入失败才记录**（唯一调用方是 `reportNotesWriteFailure`，`annotations.js:189`）；`record` 本身是公开成员（`:202-204`），用 `?? null` 存值，**不校验类型** | `annotations.js:161-205` | 可以截取最近 N 条，但转发前要按字段收窄为原始类型（评审 D13），否则不变量 3/4 靠调用方自律。「没有新 diag 条目」= 没有新的写入失败，不能用来证明写入成功。`annotations.js` 在 renderer **之后**加载，所以必须在调用时才读 `window.Reader3NotesDiag` |
| F6b | `ctx.chapterIndex` 不是服务端初值：`rendered` 处理器每次渲染都覆写它 | `epub-renderer.js:284-286` | 要对照「请求的章节」，只能在 IIFE 开头把初值存进 `const requestedIndex`（评审 D4） |
| F6c | 章节总数的现有口径是 `ctx.totalChapters`（notes-panel `:75`、导航指示 `:201`），`book.spine.length` 只在 `:306` 的 `book.ready` 之后可用 | `epub-renderer.js:201,306`；`notes-panel.js:75` | `spineCount` 取 `ctx.totalChapters`，与 notes-panel 同源（评审 D5） |
| F6d | 视口宽度 `< 600` 时 flow 为 `scrolled-doc`，没有分页 | `epub-renderer.js:50,367` | E2E 断言翻页前必须固定视口 ≥ 600，并选一个 `displayed.total ≥ 2` 的章节（评审 D12） |
| F7 | `tests/e2e/helpers.py`、`conftest.py`、`baseline_1b/**`、`test_harness_smoke.py` 和四个 fixture 属于 soak 冻结集，~~改动任何一个字节都会清零 soak 计数~~（⬛ 2026-09-28 批次规则：改动任何一个字节，`suite_hash` 就变，已声明的批次作废、须重跑一批 10 次；一批约 10–15 分钟） | `.claude/skills/plan-and-branch-map/SKILL.md`；`tasks/soak-log.md` | **E2E 辅助函数不能写进 `helpers.py`**，这修正了调研报告 §9 的一处建议。~~改生产代码（`epub-renderer.js`）不会清零（`plan-tech-stack-migration.md:487`）~~（⬛ 2026-09-28 反转：改生产代码同样使 `commit` 变、不再是同一批；判据见迁移计划 §7「台账字段（canonical）＋ 什么会让计数作废」）。（⬛ 2026-09-30：012 开工前无论 `suite_hash` 变没变，都要在最终候选 `commit` 上新跑一批，见迁移计划 §7「012 开工核验」；所以本计划改 `epub-renderer.js` 不额外增加 soak 成本，这也是它能按 ⟂ 随时插入的依据） |
| F8 | 新增 E2E 文件要同时修改分组守卫的计数常量，否则 commit 门禁的 unit lane 会变红 | `scripts/lint_e2e_groups.py:372`（`EXPECTED_UNGROUPED_ITEMS = 63`）；`tests/unit/test_e2e_group_guard.py:194,203`（`CANONICAL_UNGROUPED_ITEMS = 63` / `CANONICAL_E2E_ITEMS = 256`）。2026-09-28 评审时核对；草案原写的 55/248 已过时（评审 D10） | WI-2 以**实现当时**的值为基准，按 `--collect-only` 实测的新增条数上调，不写死数字 |
| F9 | 014 计划把 `Reader3Epub` 固定为 9 个成员，其中 7 个纳入、2 个 `@deprecated`。**K5 的定义处**是 `contracts/annotation-host-contracts.md:112-126`（「9 个成员一个不漏」＋全量枚举），plan 里的三处是引用（评审 D11） | `docs/plans/20260817-frontend-ui-refactor/contracts/annotation-host-contracts.md:112`；`plan-frontend-ui-refactor.md:1230`（K5）、`:1245`（WI-15 验收 5）、`:1839`（FR-K5）；WI-16 验收 12（`:1287`）要求 `getContentDocument` 和 `Reader3Epub.book` 的引用数为 0 | 必须先改这三处（WI-0）。getter 的实现不能引用这两个过时成员 |
| F10 | 还没有任何 Vitest 用例覆盖 `static/js` 下的 legacy 文件；可参考的先例是用 `?raw` 读入文本、在 jsdom 里执行。fe-unit lane（`npm test`）**没有 coverage** | `frontend/tests/ledger/feature-ledger-page.test.ts`；`frontend/vitest.config.ts`；`.claude/tdd-guardian/config.json` | WI-1 的单元测试沿用这个做法，按 WI-1 写明的 harness stub `window.ePub`；覆盖率靠人工映射（评审 D9） |

## 3. 接口契约（v1）

```ts
Reader3Epub.getDebugState(opts?: { diagLimit?: number }): Reader3DebugStateV1

interface Reader3DebugStateV1 {
  v: 1;
  ready: boolean;                 // rendition.location 已写入（首次 relocated 完成）
  cfi: { start: string; end: string } | null;   // 读缓存 rendition.location，不调 currentLocation()（F4）
  section: {
    index: number | null;         // renderer 闭包内的 currentSectionIndex
    href: string | null;          // rendition.location.start.href
    requestedIndex: number | null; // IIFE 开头捕获的初始章节号，之后不变（F6b）
    spineCount: number | null;    // ctx.totalChapters（F6c）
  };
  progress: {
    sectionPage: { page: number; total: number } | null; // sectionProgressOf(location)，与底部 pill 共用
    sectionPercent: number | null;  // 同上；pill 在此为 null 时兜底显示 0，这里如实报 null
    spinePercent: number | null;    // 与 notes-panel 同口径：index / (spineCount - 1)；spineCount ≤ 1 时为 null
    bookPercent: null;              // v1 恒为 null：locations 未生成（F2），不报假 0
  };
  annotations: {
    renderedIds: number;            // 当前章 iframe 内 data-annotation-ids 去重后的 id 数
    marks: number;                  // 带 data-annotation-ids 的元素个数（≠ 标注数）
  } | null;                         // currentContents 为 null（iframe 内容未就绪）时为 null
  // 按字段收窄（F6、评审 D13）：不合规的值一律为 null；只含写入失败记录
  diag: Array<{ op: string | null; requested: boolean | null; status: number | null; ok: boolean | null; id: string | null; t: number | null }>;
  diagAvailable: boolean;          // window.Reader3NotesDiag 是否存在
  errors: string[];                // 某字段取值抛错时写入「字段名: 消息」，该字段置 null
}
```

**不变量**（每一条都要有测试覆盖）：
1. **只读**：调用前后 DOM、`location.href`、`rendition` 的位置、事件监听数都不变，也不触发任何 `reader3:*` 事件。
2. **不抛错**：任何子字段出错只写进 `errors`，函数本身总是返回一个对象。
3. **可序列化**：`JSON.parse(JSON.stringify(s))` 与 `s` 深相等。结果里不能有 DOM 节点、函数或循环引用。**由构造保证**：`diag` 每条按字段收窄（`op` 字符串截到 32 字符，`id` 字符串截到 64 字符，`status`/`t` 必须是有限数，`ok`/`requested` 必须是布尔，否则一律 `null`），外部经 `Reader3NotesDiag.record()` 写进的对象、循环引用、长串都不会原样透出。
4. **不含书籍正文**：结果里不出现 iframe 里的任何文本内容。diag 的字符串字段被截短，只能容纳标识符，装不下正文段落。
5. **`diagLimit`**：默认 20，取值截断到 [0, 100]，非有限数（含 `NaN`、字符串）按默认值处理，负数按 0 处理。返回的是最近的 N 条，按时间正序。
6. **不引用** `Reader3Epub.book` 属性或 `getContentDocument`（F9）。闭包变量（`rendition`、`currentContents`、`currentSectionIndex`、`requestedIndex`、`ctx`）都可以读。
7. **始终开启**，不放在 `localStorage["reader3.debug"]` 开关后面。理由：它是只读的；`rendition` 本来就挂在页面上，这个 getter 没有带来新能力；而且 legacy JS 引用不了 `frontend/src/shared/debug.ts`。如果评审认为要加开关，改的是 §6 的第 1 个问题，契约本身不变。
8. **不强制 reflow**：不调用 `rendition.currentLocation()`、`getBoundingClientRect` 等布局读取（F4）。

## 4. 工作项

### WI-0: 定义类前置：分配分支号，修订 K5 计数

**范围**：只改文档。
**前置 WI**：无。
**做什么**：
1. 按分支号规则，在 `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md` §9 分配编号。~~目前已分配的最大号是 `018`，建议用 `019-debug-state`。~~（⬛ 2026-09-30：看板新排的「冻结集欠账窗口」也要在开分支时从 §9 取号，两者谁先开谁拿下一个空号；本文不预写数字，开分支当天取 §9 的下一个空号，分支名形如 `0NN-debug-state`。）同时在 `docs/plans/20260824-frontend-backend-plan-progress.md` 里把它登记为可随时插入（⟂）。另一种做法是并进 `014` 作为插入 WI，见 §6 的第 2 个问题。
2. **先改定义处**（评审 D11）：`docs/plans/20260817-frontend-ui-refactor/contracts/annotation-host-contracts.md` K5（`:112-126`）把「9 个成员一个不漏」改成 10，并在全量枚举里加上 `getDebugState(opts)`：签名，一句行为说明（只读、不抛错、可序列化），链接到本计划 §3。
3. 再改引用处：`plan-frontend-ui-refactor.md` 的 K5（`:1230`）改为 10 个成员、8 个纳入，把 `getDebugState(opts)` 列进纳入清单；WI-15 验收 5（`:1245`）的数字改成 10；FR-K5（`:1839`）改成「8 个纳入成员」。这三处只改数字和链接，不复述契约（「搬，不抄」）。
4. 在 WI-19（`:1454` 起）补一句：WI-19 重新定义进度后，`getDebugState().progress.bookPercent` 要接上新口径，契约版本升到 `v: 2`。

**验收标准**：
1. §9 表里有这个新分支号，并且和进度表里的登记一致。
2. `grep -rn "9 个成员\|成员数为 9" docs/plans/20260817-frontend-ui-refactor/` 结果为 0（覆盖 `contracts/` 和 plan）。契约 K5、plan K5、WI-15 验收 5、FR-K5 四处的数字彼此一致，契约的全量枚举里有 `getDebugState`。
3. WI-19 有一条指向本计划 §3 的交叉引用。

---

### WI-1: 实现 `getDebugState()`，补 Vitest 单元测试（fe-unit lane）

**范围**：`src/reader3_app/web/static/js/epub-renderer.js`，以及新文件 `frontend/tests/legacy/epub-renderer-debug-state.test.ts`。
**前置 WI**：WI-0。
**做什么**：
1. 在 IIFE 开头、`currentSectionIndex` 初始化（`:59`）之后加 `const requestedIndex = currentSectionIndex;`（F6b）。
2. 抽出纯函数 `sectionProgressOf(location) → { page, total, percent } | null`（评审 D6）：只看 `start.displayed`，`total` 为真值且结果不是 `NaN` 时返回，否则返回 `null`。**`start.percentage` 回退不进共享函数**：它在本项目里恒为假 0（F2），getter 不能报它（U3）。`updateProgress`（`:235-248`）改为先调 `sectionProgressOf`，为 null 时再走原有的 `percentage` 回退和兜底 0%，所以 pill 的行为逐字不变（U12 锁住）。getter 只用 `sectionProgressOf`，null 就报 null。
3. 在 renderer 的 IIFE 里新增函数 `getDebugState(opts)`，按 §3 的契约逐字段取值：位置读 `rendition.location`（F4），章节数读 `ctx.totalChapters`（F6c），diag 逐字段收窄（§3 不变量 3）。每个字段各自 `try/catch`，然后挂到 `window.Reader3Epub` 上。
4. **测试 harness**（评审 D7）：沿用 F10 的先例，用 `?raw` 读入 `epub-renderer.js`，在 jsdom 里准备 `#epub-viewer`，设置 `window.Reader3Ctx`（含 `chapterIndex`、`totalChapters`），然后执行脚本。`window.ePub` 的 stub 至少要提供：
   - `book.renderTo()`：返回 rendition stub
   - `book.ready`、`book.opened`、`book.loaded.navigation`：已 resolve 的 Promise
   - `book.spine.get(i)`：返回 `{ href, index }`
   - rendition stub：`on(name, fn)` 把处理器**记进一张表**；`display`/`next`/`prev` 是计数 spy；`location` 是测试可直接赋值的普通属性
   - 测试通过记录下来的处理器触发 `rendered(section, contents)` 和 `relocated(location)`，其中 `contents.document` 是**另一个** jsdom `Document`，用来模拟 iframe
   - 若 renderer 顶层还用到其他 epub.js API，实现时照上面的方式补 stub，并在测试文件头注释里列出

**测试矩阵**（先写成红，再实现）：

| 用例 | 输入 | 断言 |
|---|---|---|
| U1 首屏前 | `rendition.location` 为 `undefined`（未触发 `relocated`） | `ready=false`，`cfi=null`，`progress.sectionPage=null`，`errors=[]` |
| U2 章内第 3/10 页 | `rendition.location.start.displayed={page:3,total:10}`，`start.cfi`/`end.cfi` 给定 | `cfi` 原样返回，`sectionPercent=30`，`sectionPage={3,10}` |
| U3 假 0 不外泄 | `start.percentage=0`，没有 `displayed` | `sectionPercent=null`，`bookPercent=null`（不是 0） |
| U4 章节口径 | 触发 `rendered`，使 `currentSectionIndex=2`；`ctx.totalChapters=5` | `spinePercent=50`，`section.index=2`，`spineCount=5` |
| U5 标注去重 | iframe body 里放 3 个 mark，`data-annotation-ids` 分别是 `["a"]`、`["a","b"]`、`["c"]` | `renderedIds=3`，`marks=3` |
| U6 坏数据 | 某个 mark 的 `data-annotation-ids` 不是合法 JSON | 不抛错；`errors` 里含 `annotations`；其他字段正常 |
| U7 diag | `window.Reader3NotesDiag.entries()` 返回 30 条，`diagLimit=5` | 返回最后 5 条，顺序为正序；`diagLimit=500` 时截断为 30 条；`window.Reader3NotesDiag` 不存在时 `diag=[]`、`diagAvailable=false` |
| U8 不变量 | 任意状态 | 调用前后 `document.body.innerHTML`、`location.href` 不变；stub 的 `display`/`next`/`prev` 调用次数为 0；若 stub 带 `currentLocation`，其调用次数为 0（不变量 8）；`JSON.parse(JSON.stringify(s))` 与 `s` 深相等 |
| U9 子字段抛错 | `rendition.location` 定义为抛错的 getter | 函数返回对象，`errors` 含 `cfi`，`cfi=null` |
| U10 renderer 未初始化 | 没有 `#epub-viewer` | `window.Reader3Epub === undefined`（锁定 F1 的语义） |
| U11 换章重新计数 | 先用含 2 个 id 的 contents 触发 `rendered`，再用含 1 个 id 的另一份 contents 触发 | 第二次调用 `renderedIds=1`，`section.index` 随之更新 |
| U12 pill 回归（D6） | `relocated` 分别给 3/10、无 `displayed` 且无 `percentage`、`displayed={page:NaN,total:10}` | pill 文本依次为 `当前阅读至 30%`、`当前阅读至 0%`、`当前阅读至 0%`（与改动前一致）；getter 对后两种报 `sectionPercent=null` |
| U13 requestedIndex 恒定（D4） | `ctx.chapterIndex=1` 启动，再触发 `rendered` 到第 3 章 | `section.requestedIndex=1`，`section.index=3` |
| U14 单章书 | `ctx.totalChapters` 为 1、0、缺失 | `spinePercent=null`，不抛错 |
| U15 contents 未就绪 | 未触发 `rendered`（`currentContents` 为 null） | `annotations=null`，`errors` 不含 `annotations` |
| U16 diagLimit 边界 | `diagLimit` 为 0、-3、`NaN`、`"5"` | 0 与 -3 → `[]`；`NaN` 与 `"5"` → 默认 20 条 |
| U17 total 为 0 | `displayed={page:0,total:0}` | `sectionPage=null`，`sectionPercent=null` |
| U18 diag 清洗（D13） | 经 `Reader3NotesDiag.record()` 写入 `op` 为对象、`id` 为 200 字符串、`status` 为 `"500"`、`ok` 为 `"yes"`，以及一个含循环引用的对象 | 对应字段分别为 `null`、64 字符、`null`、`null`；`JSON.stringify(s)` 不抛错 |

**验收标准**：
1. `npm test` 通过，并且上面每个用例都有「先红」的证据（按 tdd-guardian 收据）。
2. `grep -n "Reader3Epub.book\|getContentDocument" epub-renderer.js` 的结果中，新增代码里没有命中。
3. `npm run typecheck` 通过。
4. `Reader3Epub` 的成员数为 10，和 WI-0 改过的 K5 一致。
5. **人工覆盖映射**（评审 D9，fe-unit 没有 coverage）：在 PR 描述里列出 getter 与 `sectionProgressOf` 的每条分支，共 21 条路径，逐条写上覆盖它的用例编号（U1–U18）。有任何一条对应不上就不算通过。

---

### WI-2: E2E 验收：真实浏览器加真实书（e2e lane，只在 push 时门禁）

**范围**：新文件 `tests/e2e/test_debug_state.py`、`scripts/lint_e2e_groups.py`、`tests/unit/test_e2e_group_guard.py`。**不能碰任何 soak 冻结文件（F7）。**
**前置 WI**：WI-1。
**做什么**：
1. 新测试文件只用 `conftest.py` 已有的 fixture。需要的小工具函数写在本文件内，不要加进 `helpers.py`。
2. 用例：
   - **等待方式**（评审 D8）：每个断言前都用 `page.wait_for_function` 轮询 getter，直到满足条件（例如 `ready === true`、`renderedIds >= n`），超时 5s。失败信息里要带上最后一次 getter 的输出。不用固定 `sleep`。
   - E1：打开第 N 章，等 `ready`，然后断言 `section.index == N`、`section.requestedIndex == N`，并且 `cfi.start` 以 `epubcfi(` 开头。
   - E2（评审 D12）：先把视口设为 ≥ 600 宽（F6d，保证是 paginated flow），打开一个多页章节。先断言 `sectionPage.total >= 2` 且 `page < total`，不满足就让用例 fail 并提示换章节，不要跳过。然后翻一页，断言 `sectionPage.page` 加 1、`cfi.start` 改变。
   - E3（评审 D12）：先记下 `diag` 的条数，再划选并保存一条标注。断言三件事：`renderedIds` 加 1；`GET /api/notes/{book_id}/{chapter_index}`（`routers/notes.py:191`）返回的列表里有新标注的 id；`diag` 条数不变（没有新增写入失败）。**不要**断言「最后一条 `ok==true`」，因为 diag 只记录失败（F6）。
   - E4：整个过程中，`getDebugState` 调用前后 iframe 的 `body.innerHTML` 字节数不变。
3. 把新模块登记进 `UNGROUPED_E2E_MODULES` 并写明理由。以实现时的 `EXPECTED_UNGROUPED_ITEMS`、`CANONICAL_UNGROUPED_ITEMS`、`CANONICAL_E2E_ITEMS` 为基准（2026-09-28 的值是 63 / 63 / 256），按 `uv run pytest tests/e2e --collect-only -q` 实测的新增条数上调（F8、评审 D10）。

**验收标准**：
1. `uv run pytest tests/e2e/test_debug_state.py --browser chromium` 通过。
2. `uv run pytest tests/unit tests/contract` 通过（分组守卫为绿）。
3. `git diff --stat` 里**没有** `tests/e2e/helpers.py`、`tests/e2e/conftest.py`、`tests/e2e/baseline_1b/`、`tests/e2e/test_harness_smoke.py` 或 `tests/fixtures/`。
4. 新用例不启用 tracing，也不加全量 request 监听，以免观察者效应（`soak-log.md:884-898`）。soak 跑不包含这个文件。

---

### WI-3: 文档回写

**范围**：只改文档。
**前置 WI**：WI-2，并且已经合并到 `master`，门禁 lane 全绿。
**做什么**：
1. `docs/references/ui-e2e-debug-mcp-bridge-survey.md` §9：把「E2E helper 加进 `tests/e2e/helpers.py`」改成「写在独立模块里（soak 冻结集，F7）」，并链接到本计划。
2. `docs/feature-ledger.md` 的 F-009 行（`:95`，详情在 `:226-233`）：Evidence 补上 WI-2 的测试路径，Known limits 写明「`bookPercent` 恒为 null，等 WI-19」「`renderedIds` 只统计本章已渲染的标注」，然后运行 `python3 scripts/build_feature_ledger.py` 重新生成 HTML。
3. `CLAUDE.md` 的「Frontend Development」一节补一行：`window.Reader3Epub.getDebugState()` 是给 agent 或测试读取阅读器状态的入口，并给出 §1 的 `/browse` 用法。
4. 在本计划顶部把状态改成「已合并」，写上 PR 号和合并提交。

**验收标准**：
1. `python3 scripts/build_feature_ledger.py --check` 通过。
2. 调研报告里 `helpers.py` 的每一处出现，都不再是「在这里新增」的意思。

## 5. 风险

| 风险 | 缓解 |
|---|---|
| 014（WI-14–WI-17）把 renderer 或 `annotations.js` 迁到 TS 后，getter 丢失或行为变化 | WI-0 把它写进 K5，014 就有义务保留它。WI-1 的单元测试和 WI-2 的 E2E 是回归网 |
| 调用方把 `sectionPercent` 当成全书进度 | 字段名带 `section` 前缀；`bookPercent` 明确为 `null`；契约里用注释说明（§3） |
| 标注计数被误读为「全书标注数」 | 字段名叫 `renderedIds`；台账的 Known limits 里注明 |
| 新 E2E 意外改动冻结文件，导致 ~~soak 清零~~ `suite_hash` 变、已声明的批次作废（⬛ 2026-09-28 批次规则） | WI-2 验收 3 用 `git diff --stat` 硬性检查 |
| 以后有人在 getter 里加写操作或正文内容 | 不变量 1、4 都有单元测试（U8），能挡住回归 |
| 外部经公开的 `Reader3NotesDiag.record()` 写入非原始值，破坏序列化 | getter 逐字段收窄（不变量 3），U18 锁住 |
| getter 调用本身扰动布局（观察者效应） | 读缓存 `rendition.location`，不调 `currentLocation()`（不变量 8），U8 断言调用次数为 0 |

## 6. 待决问题

1. **开关**：保持始终开启（本计划的默认选择，理由见 §3 第 7 条），还是放到 `localStorage["reader3.debug"] === "1"` 后面？
2. **分支归属**：单独开 ~~`019-debug-state`~~ 一条小分支（~~它很小，可以在 soak 等待期间插进来~~），还是并进 `014` 作为插入 WI？本计划倾向单独开：它不依赖 014，越早合并，014 迁移时就越早有回归网。
   （⬛ 2026-09-30：2026-09-28 起已没有 soak 等待期；它按进度看板的 ⟂「可随时插入」处理，理由只剩后半句。分支号不预写，见 WI-0 第 1 步。）
3. **renderer 未初始化时是否暴露原因**：v1 用 `Reader3Epub === undefined` 表示。如果想知道具体原因（缺 EPUB、epub.js 没加载、创建失败），需要另加一个 `window.Reader3EpubStatus`。这会扩大范围，v1 不做。→ 已记入 `TODOS.md`。
4. **`bookPercent` 何时启用**：取决于 WI-19 是否调用 `locations.generate()`（有性能成本）。到时候契约升到 `v: 2`。→ 已记入 `TODOS.md`。

## GSTACK REVIEW REPORT

> `/plan-eng-review`，2026-09-28，基于 `master@b1d3c2c`。外部意见：Codex（plan review，EXIT=0）。

### 裁决

| # | 级别 | 问题 | 裁决 | 落点 |
|---|---|---|---|---|
| D3 | P1 | `currentLocation()` 会强制 reflow 并改写 manager 状态，不是纯读 | 改读缓存 `rendition.location` | F4、§3、不变量 8、U1/U8/U9 |
| D4 | P2 | `ctx.chapterIndex` 每次渲染都被覆写，不是初值 | 改为 IIFE 开头捕获的 `requestedIndex` | F6b、§3、WI-1 第 1 步、U13 |
| D5 | P2 | `spineCount` 的来源没有定 | 取 `ctx.totalChapters`，与 notes-panel 同源；不变量 6 改为只禁止 `.book` 和 `getContentDocument` | F6c、§3、不变量 6 |
| D6 | P2 | pill 和 getter 的进度公式会分叉 | 抽出纯函数 `sectionProgressOf()`（只看 `displayed`），两处共用；`percentage` 回退和兜底 0% 只留在 pill 一侧 | WI-1 第 2 步、U12、U17 |
| D7 | P1 | 单元测试的 harness 没写清，边界用例缺失 | 写明 stub 清单和事件驱动方式，补 U11–U17 | WI-1 第 4 步、U11–U17 |
| D8 | P2 | E2E 依赖异步加载，有抖动风险 | 用 `wait_for_function` 轮询，5s 超时，失败时输出最后一次 getter 结果 | WI-2 等待方式 |
| D9 | P3 | fe-unit lane 没有 coverage | 人工把 21 条路径映射到用例编号；coverage 留到 014 | WI-1 验收 5、TODOS.md |
| D10 | P2（Codex） | 守卫计数引用过时（55/248，实际是 63/256） | 改正，并改成「按实测增量上调」 | F8、WI-2 第 3 步 |
| D11 | P1（Codex） | WI-0 漏掉了 K5 的定义处 `contracts/annotation-host-contracts.md` | 定义处先改，引用处只改数字和链接 | F9、WI-0 第 2、3 步和验收 2 |
| D12 | P1（Codex） | E3 断言 `ok==true` 必然失败（diag 只记失败）；E2 缺受控状态 | E3 改为 notes API 加「diag 不增」；E2 固定视口 ≥600，并先断言多页 | F6、F6d、WI-2 E2/E3 |
| D13 | P2（Codex） | `record()` 是公开函数且不校验，不变量 3/4 靠调用方自律 | getter 内按字段收窄 | §3 类型、不变量 3/4、U18 |
| D14 | 战略（Codex） | 质疑范围过大 | 保持现范围：评审找出的 4 个坑正是 agent 临时拼状态时会反复踩的 | — |

**Codex 意见吸收情况**：共 8 条。6 条已写进 plan（D10–D13，外加 U1/U9 的写法由 D3 覆盖，`ready` 太弱的问题由 D8 覆盖）；1 条经权衡后不采纳（D14，原因见上表）；无遗留。

### 不在范围内
- 服务端端点、MCP server、WebSocket 以及任何新依赖（§1 非目标）
- 修复进度口径分歧 D7（归 WI-19）
- `bookPercent`、`Reader3EpubStatus`、fe-unit coverage：已记入 `TODOS.md`

### 已有可复用的
- `Reader3Epub` 对象（`epub-renderer.js:375-401`）
- epub.js 自带的 `rendition.location` 缓存
- `Reader3NotesDiag.entries()`
- jsdom 加 `?raw` 的测试先例（`frontend/tests/ledger/feature-ledger-page.test.ts`）
- `conftest.py` 里现成的 E2E fixture

### 失败模式

| 失败 | 有测试？ | 有处理？ | 用户可见？ |
|---|---|---|---|
| 首次渲染前被调用 | U1 | 返回 `ready=false`、`cfi=null` | 否 |
| 某个子字段抛错 | U6、U9 | 写进 `errors`，该字段置 null | 否 |
| 有人通过 `record()` 写入异常值 | U18 | 收窄为 null | 否 |
| renderer 没有初始化 | U10 | `Reader3Epub === undefined` | 否 |
| 抽出 `sectionProgressOf` 时 pill 文本回归 | U12 | 保留兜底 0% | **是**，U12 负责锁住 |

没有「无测试、无处理、又静默失败」的关键缺口。

### 并行度
按顺序执行：WI-0 → WI-1 → WI-2 → WI-3。每一步都依赖上一步的产物，不需要拆 worktree。

### 结论
**VERDICT: CLEARED — 可以进入实现**，走 `/tdd-guardian:workflow`，先完成 WI-0。

| 项 | 值 |
|---|---|
| 发现问题数 | 12（D3–D14） |
| 关键缺口 | 0 |
| 覆盖 | 21 条路径，全部映射到 U1–U18 或 E1–E4 |

NO UNRESOLVED DECISIONS
