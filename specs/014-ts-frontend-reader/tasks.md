# 014-ts-frontend-reader —— 任务

- **对应阶段**: Phase 4B（阅读器）
- **进入条件**: Phase 3 完成 **且** 4A.4 完成。见 `docs/plans/20260816-plan-ui-migration-sequencing.md` §6 与 §7
- **契约**: K1–K6 见 `specs/007-hygiene-and-contracts/contracts/annotation-host-contracts.md`（唯一真相源，本文只引用编号）
- **设计**: 阅读器外壳规格见 `docs/plans/20260815-spec-frontend-design.md` §6.0 / §6.3

> **引用规则**：本文用**符号名**定位代码，不写行号。行号会漂移——上游计划里三处行号引用在 2026-08-16 复核时已全部失效。

---

## 4B.1 —— `annotations.js` 拆分（纯拆分不改逻辑）

`annotations.js` 约 1127 行，整份包在一个 IIFE 内。必须在外壳重写**之前**做：外壳重写会移动工具条 DOM，而工具条 UI 目前就长在这个文件里。拆完之后外壳只与 `overlays.ts` 打交道。

### 为什么不是上游计划的三分法

原 plan 写的是拆成 `anchoring` / `renderer` / `ui` 三块。**这个三分法在代码面前不成立**：

- `getReaderContext()` 被 `AnnotationRenderer` 与 `AnnotationUI` **同时**使用；
- 四个 `/api/notes` 的 `fetch` 也横跨两个类。

二者都不能塞进任何一边，必须各自独立成模块。同时 `AnnotationUI` 单类约 667 行，拆完仍超过 ≤400 行上限，需要再分。

### 八模块划分

| 模块 | 来源符号 | 约 | 契约 | 说明 |
|---|---|---|---|---|
| `context.ts` | `getReaderContext` | 15 | **K6** | 被 renderer 与 ui 共用，故独立。拆分时删掉 `location.pathname` 回退分支 |
| `notes-api.ts` | 四处 `/api/notes` 的 `fetch` | 60 | — | 同样横跨两类。也是 Phase 2a 的 S5 乐观并发（ETag/revision）唯一落点 |
| `anchoring.ts` | `buildTextIndex` `offsetFromNode` `findRange` `buildSegments` `rangeFromCfi` | 110 | 无 | 纯文本/Range 计算，不写 DOM、不碰全局。**不拥有任何契约正是目的**——它由此变成可单测的纯函数集 |
| `renderer.ts` | `clearExistingAnnotationMarks` `dedupeAnnotationMeta` `segmentStyle` `applySegments` `class AnnotationRenderer` ＋ 读侧三方法 `setCurrentAnnotations` `getAnnotationMetaFromMark` `getAnnotationMetaForRange` | 250 | **K5**、**K4**（重绘侧） | iframe 内部的高亮绘制。读侧三方法从 `AnnotationUI` 移过来：它们解析的 `data-annotation-ids` / `data-annotation-meta` 正是本模块写出去的，读写同源才不会漂移 |
| `overlays.ts` | `qs` `clamp` `offsetRect` ＋ **构造函数里抓七个宿主元素的那段** `openToolbarAt` `closeSelectionToolbarIfOpen` `setSelectedColor` `syncSelectedColor` `closeNoteEditorIfOpen` `onHover` `showTooltip` `hideTooltip` | 150 | **K1**、**K3** ⚠️ | **风险浓缩模块**。三个浮层的抓取与定位全在这里；4B.2 重写外壳时唯一需要盯的就是它。七行 `qs()` 要从 `AnnotationUI` 构造函数里**摘出来**放进本模块的 init，构造函数其余部分留在 `interactions.ts`——否则 K1 的归属名实不符 |
| `note-editor.ts` | `openNoteEditorWithExisting` `openNoteEditor` | 45 | — | 笔记编辑 UI。**只管打开与填充表单，不负责保存**——保存走 `commands.ts` |
| `commands.ts` | `toggleMarkerAnnotation` `toggleAnnotation` `deleteCurrentAnnotation` `saveNote` `deleteAnnotations` `createAnnotation` | 175 | — | **标注写入链**。四种类型（marker / wavy / underline / note）共用的唯一写入口在此。依赖方向严格单向：`interactions → commands → notes-api`，`commands.ts` 不得反向 import `interactions.ts`，也不得直接碰 DOM |
| `interactions.ts` | `constructor`（减去七行 `qs()`）`init` `onAnnotationClick` `getExistingMarkerIds` `onSelection` `handleRenditionSelection` `handleSelectionRange` `handleAction` `getExistingAnnotationIds` `copySelection` `askAi` ＋ `initAnnotations` | 280 | **K2**、**K4**（消费侧） | 事件委托与选区处理，兼做编排入口。`handleAction` 把意图翻译成 `commands.ts` 的调用，自己不写库 |

行数为估算，用来验证「每块 ≤400 行」可达，不是硬指标。八块合计约 1085，`annotations.js` 实际 1127——差额是 `showToast` / `elementDebugInfo` / `getEventTargetElement` 三个杂项（见下）。

`showToast` / `elementDebugInfo` / `getEventTargetElement` 三个杂项归入 4A.3 的共享模块或就近落地。

### 为什么有 `commands.ts` 这一层（已裁定，2026-08-16）

2026-08-16 逐符号核对 `AnnotationUI`：实际 **30 个方法**，上游计划记为 24。差额六个**恰好构成完整的写入链**，而上游的七模块表未指派它们：

```
toggleMarkerAnnotation   →  deleteAnnotations / createAnnotation
toggleAnnotation         →  deleteAnnotations / createAnnotation
deleteCurrentAnnotation  →  deleteAnnotations
saveNote                 →  createAnnotation
deleteAnnotations        （含 fetch）
createAnnotation         （含 fetch）
```

入口 `handleAction` 在 `interactions.ts`，出口三处 `fetch` 在 `notes-api.ts`——**中间这一段原本无主**。按行号区间机械切分会把它们冲进 `note-editor.ts`，于是 `createAnnotation`（四种标注类型共用的唯一写入口）住进一个叫「笔记编辑器」的模块，同时 `notes-api.ts` 与 `note-editor.ts` 双双声称拥有那三处 `fetch`。

**裁定：新增第八个模块 `commands.ts`**（eng-review 2026-08-16，Codex 独立同结论；见 `docs/plans/20260816-plan-ui-migration-sequencing.md` 的 GSTACK REVIEW REPORT A-1）。这六个方法是**应用命令**——它们协调 UI 意图、状态、渲染与持久化，三样都沾，所以哪一层都装不下，必须自成一层。得到的测试接缝是干净的三段：`interactions` 翻译事件 / `commands` 执行标注工作流 / `notes-api` 只管 HTTP。

两个落选方案的失败模式，写在这里以免日后重开：

- **(b) 并入 `notes-api.ts`** —— **层级塌缩**。传输层被 UI 状态与渲染耦合污染，最终长成 god service。
- **(c) 不拆 `AnnotationUI`，只做文件切分** —— **装饰性模块化**。667 行的隐式耦合、过宽的可变权限原样保留，拿不到单测边界，等于白拆。

### 每份契约在 4B.1 的产出

全部为"拆分即完成"，不改行为（K6 除外）。契约正文见 `specs/007-hygiene-and-contracts/contracts/annotation-host-contracts.md`。

| 契约 | 4B.1 必须产出 |
|---|---|
| **K1** | 七个 id 提为 `overlays.ts` 的 `OVERLAY_IDS` 常量表；init 时逐个校验，缺任一个 `console.error` 并标记降级 |
| **K2** | `data-action` / `data-color` 合法取值提为 `interactions.ts` 的联合类型；目标选择器写成常量并注释「按钮必须是 `<button>`」 |
| **K3** | `offsetRect()` 移入 `overlays.ts` 并注释它产出**视口坐标**；祖先链零 transform 的前置条件写成模块头注释 |
| **K4** | 六个事件名提为常量，派发与订阅两侧都改用常量 |
| **K5** | `window.Reader3Epub` **7 个纳入成员**写成 `renderer.ts` 顶部的显式 interface，签名不变；`book` 与 `getContentDocument()` 加 `@deprecated` 并注明 4B.2 结束时移除。⚠️ `search.js` 也消费 K5（`getContentRoot` / `onContentsReady`），改接口会同时打断阅读页内搜索 |
| **K6** | 删除 `location.pathname` 回退分支，读不到 `window.Reader3Ctx` 直接抛错。本次拆分中唯一**故意的行为变更** |

### 4B.1 退出门槛

- 1b 的标注 E2E **零改动**全绿（拆分不改行为，测试不该动）。前提：1b 的用例已覆盖写入路径——四类型各创建一次、改色、删除、笔记保存，断言方式为「刷新后高亮回到同一段文字」而非「`fetch` 被调用过」
- 各模块 ≤400 行
- K1–K6 六项产出全部落地
- **依赖方向机器可验**：`commands.ts` 不 import `interactions.ts` / `note-editor.ts` / `overlays.ts`；`notes-api.ts` 不 import 除类型外的任何本目录模块。用 ESLint `import/no-restricted-paths` 或 `dependency-cruiser` 落成 CI 检查，不靠人盯
- `anchoring.ts` 有单测覆盖（它现在是纯函数，这是顺手拿到的收益）

---

## 4B.2 —— 阅读器外壳垂直切片

- **硬约束 1**：绝不触碰 epub.js iframe 内部 DOM。边界判定标准以 `docs/plans/20260815-spec-frontend-design.md` §6.0 为准（含其允许的 `themes.override` 例外与"文本节点偏移逐字节不变"的判据）。
- **硬约束 2（K3 浮层挂载）**：见下。
- 落 S1（标注 stale 横幅），设计见 spec §6.4。
- 落三条翻页行为（见 `designs/reader-pro-next/README.md` 的「原型验证出来的三条行为」）。

### 硬约束 2 —— 三个浮层的挂载位置（K3）

外壳重写唯一一处**会静默打断标注**的改动就是把浮层挪进新的页面容器。`annotation-toolbar` / `note-editor` / `note-tooltip` 用 `position: fixed` + 视口坐标定位；祖先链上任何一个包含块制造者都会让它们**照常出现但位置错**，而 `toBeVisible()` 照样绿。

- **允许的挂法只有两种**：`<body>` 直接子元素（生产现状，零改动即合规），或 `<dialog>` + `showModal()` 走 top layer。挂进 `.reader-shell` 之类的页面容器**不是禁止，但要靠断言逐次证明**——容器今天干净不代表明天干净。
- 属性判据与 `containingBlockAncestor()` 参考实现见 [`annotation-host-contracts.md`](../007-hygiene-and-contracts/contracts/annotation-host-contracts.md) K3，**不在本文复述**。
- 新外壳若为翻页动画给容器加了 `transform` / `will-change`，**先确认浮层不在其下**再加。原型的 `.page-flow` 就带 `will-change: transform`，是这条风险的现成样板。

### 4B.2 退出门槛

- **结构断言**：三个浮层各跑一次 `containingBlockAncestor(el) === null`。这条必须在**每个** E2E 用例的 `afterEach` 或一条独立的结构测试里跑，不能只在 happy path 跑一次
- **几何断言**：iframe 内划词后，工具条矩形与选区矩形（已换算到视口坐标）的相对位置落在容差内——横向与选区中心对齐 ±N px、纵向紧贴选区上/下沿。**禁止**用 `toBeVisible()` / `toBeAttached()` 充当本条
- 上面两条对 `note-editor` 与 `note-tooltip` 同样各来一遍（tooltip 走 hover 触发）
- 1b 的标注 E2E **零改动**全绿（与 4B.1 同一条门槛）
- iframe 内部改动不超出 spec §6.0 允许范围（`document.body.textContent` 与所有文本节点偏移逐字节不变）

## 4B.3 —— 阅读设置面板

四主题 × 四字体 × 字号 × 行距。`data-reading-theme` 同时驱动 app chrome 与 iframe 正文。

**依赖 `applyThemeSettings`**——已确认纳入 K5 冻结面（7 个成员之一），4B.3 有合法路径。

同时落 spec §1.5 的 **D5（正文栏宽）**：`max-width` / `margin` / `text-align` / `font-size` / `line-height`，走 `themes.override`，属 spec §6.0 明列的两类例外之一。

删除三款未授权商业中文字体选项。

## 4B.4 —— 阅读进度单一数据源

行为变更。页脚与 Notes 面板在此收敛，与 4A.4 已改的书库卡片对齐。封面等非正文 spine 项不计入分母。
