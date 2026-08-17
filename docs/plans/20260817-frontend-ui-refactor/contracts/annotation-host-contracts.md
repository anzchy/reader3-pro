# 标注宿主契约（K1–K6）

- **状态**: Phase 0 冻结，Phase 4B 验收
- **权威范围**: 本文是 K1–K6 六份契约的**唯一真相源**。任何计划文档只许引用编号，不许复述内容。
- **消费方**: [`20260816-tech-stack-migration/plan-tech-stack-migration.md`](../../20260816-tech-stack-migration/plan-tech-stack-migration.md) §7（阶段门槛）、[前端计划](../plan-frontend-ui-refactor.md) 的 **WI-14**（八模块拆分）与 **WI-15**（K1–K6 契约交付物）
- **被约束的代码**: `src/reader3_app/web/static/js/annotations.js`、`js/epub-renderer.js`、`web/templates/reader.html`

---

## 为什么需要这六份契约

阅读器外壳重写（Phase 4B）不碰 epub.js iframe 内部，标注的核心（锚定、持久化、高亮渲染）因此不受影响。外壳与标注之间只有下面六个接触面。

**危险不在"会坏"，而在六条里有四条坏了不报错**——选中文字后什么都不发生，控制台干净。所以每条契约都要配一条**能失败的断言**，而不是只断言"工具条可见"。

---

## K1 — 七个宿主 DOM id

| 项 | 内容 |
|---|---|
| 契约 | `annotation-toolbar` / `anno-color-row` / `note-editor` / `note-editor-text` / `note-editor-save` / `note-editor-cancel` / `note-tooltip` |
| 现状 | `AnnotationUI` 构造函数用 `getElementById` 逐个抓取，各 1 处 |
| 打断方式 | 改名或换结构 → 对应字段为 `null` |
| 失败是否可见 | ❌ **静默** |

**爆炸半径（2026-08-16 核实修正）**：此前记录认为影响面止于工具条定位守卫。实际上 `AnnotationUI.init()` 的**第一行**就是

```js
init() {
  if (!this.contentEl || !this.toolbar) return;
```

`annotation-toolbar` 缺失会让整个标注 UI 静默不初始化——选区、快捷键、笔记编辑器、tooltip 全部失效，而不只是工具条错位。其余六个 id 缺失则各自局部静默。

**4B.1 验收**：七个 id 提为 `overlays.ts` 顶部的 `const OVERLAY_IDS` 常量表；init 时逐个校验，缺任何一个 `console.error` 并标记降级。**把静默失败变成响亮失败**——这是本次拆分单点价值最高的一处改动。

---

## K2 — 属性委托

| 项 | 内容 |
|---|---|
| 契约 | `button[data-action]` 与 `button[data-color]`，在容器上事件委托 |
| 现状 | 工具条与色板各一处 `addEventListener("click", …)` + `e.target.closest(...)` |
| 打断方式 | 按钮换成 `<div>`、或 `data-action` 取值改名 → `closest()` 落空，点击无反应 |
| 失败是否可见 | ❌ **静默** |

**4B.1 验收**：`data-action` 与 `data-color` 的合法取值提为 `interactions.ts` 的联合类型；委托仍绑在容器上，但目标选择器写成常量并注释「按钮必须是 `<button>`」。E2E 逐个 action 点一遍并断言**结果**（批注真的产生），不是断言按钮存在。

---

## K3 — `position: fixed` 坐标系 ⚠️ 最高危

| 项 | 内容 |
|---|---|
| 契约 | 三个浮层（工具条 / 笔记编辑器 / tooltip）的祖先链上**零**「包含块制造者」：`transform` / `filter` / `backdrop-filter` / `perspective` / `contain: layout\|paint\|strict\|content` / `will-change: transform\|filter\|perspective` 中任意一项非默认值 |
| 现状 | `offsetRect()` 把 iframe 内 rect 加上 `frameEl` 的视口偏移，得到**视口坐标**直接写进 `style.left/top`；三个浮层 CSS 均为 `position: fixed` |
| 打断方式 | 任一祖先出现上述属性 → 为 `fixed` 造出新包含块 → 工具条**照常出现，但位置错** |
| 失败是否可见 | ❌ **静默**（E2E 断言"可见"会**通过**） |

### 挂载位置规则

**规范是上表那条属性条件，不是某个具体的父节点名。** 满足它的挂法有两种，任选其一：

1. **`<body>` 直接子元素** —— 生产今天就是这样（三个浮层都在 `</body>` 前平铺），零改动即合规；
2. **`<dialog>` + `showModal()`** —— top layer 完全脱离包含块链，从机制上免疫本条契约。工具条不适用（非模态），笔记编辑器可以考虑。

**挂进任何页面容器（含 `.reader-shell`）都需要下面那条断言逐次证明**——容器今天干净不代表明天干净，一次 `backdrop-filter` 毛玻璃就够了。

> 本文此前写的是「必须挂在 `.reader-shell` 直下」。那是照抄原型结构，属**用实现描述规范**：`.reader-shell` 只是恰好没有包含块属性。2026-08-16 改为属性判据 + 两种安全挂法。
>
> 原型侧满足条件同样**纯属巧合**——`.page-flow` 本身就用了 `will-change: transform`，浮层只是恰好没嵌在它里面。该注释已补进 `designs/reader-pro-next/index.html`（`.page-flow` 规则附近）。

### 机器判据

```js
// 返回第一个会为 position:fixed 造出新包含块的祖先，没有则 null
function containingBlockAncestor(el) {
  for (let p = el.parentElement; p; p = p.parentElement) {
    const s = getComputedStyle(p);
    if (s.transform !== "none") return p;
    if (s.filter !== "none") return p;
    if (s.backdropFilter && s.backdropFilter !== "none") return p;
    if (s.perspective !== "none") return p;
    if (/\b(layout|paint|strict|content)\b/.test(s.contain)) return p;
    if (/\b(transform|filter|perspective)\b/.test(s.willChange)) return p;
  }
  return null;
}
```

**4B.1 验收**：`offsetRect()` 移入 `overlays.ts` 并注释说明它产出的是**视口坐标**；前置条件写成模块头注释。`containingBlockAncestor()` 作为调试断言放进 `overlays.ts` 的 init（dev 构建下命中即 `console.error`）。

**4B.2 门槛（硬）**：见[前端计划](../plan-frontend-ui-refactor.md) **WI-16** —— 三个浮层的挂载位置在重写前后都必须过上面这条判据，且 E2E 用**矩形几何**断言而非 `toBeVisible()`。

---

## K4 — 六个自定义事件

| 项 | 内容 |
|---|---|
| 契约 | `reader3:content:rendered` / `chapter:change` / `annotations:updated` / `content:click` / `escape` / `ai:ask` |
| 现状 | `epub-renderer.js` 派发；`annotations.js`、`notes-panel.js`、`toolbar.js` 消费 |
| 打断方式 | 新外壳自己实现翻章而**不派发** `chapter:change` → 换章后高亮不重绘，旧章高亮残留或全部消失 |
| 失败是否可见 | ⚠️ 视觉可见但无报错 |

**4B.1 验收**：六个事件名提为常量，派发与订阅两侧都改用常量，杜绝字符串拼错。E2E：翻章后断言新章高亮数量正确。

---

## K5 — `window.Reader3Epub` 接口

**这是 4B.2 与 iframe 之间唯一允许的接口。**

### 冻结规则

**冻结契约必须枚举边界的全部活成员，每个成员落到且仅落到三类处置之一：**

1. **纳入** —— 写明签名与行为，冻结；
2. **deprecate** —— 显式标注，并指定移除阶段；
3. **收窄契约名义** —— 若确实不该管，就改契约的名字（例如从「`Reader3Epub` 公开面」收窄为「标注依赖子集」），而不是默默不提。

默默不提是最差的一种：读者无法区分「没用到」和「不许用」。本契约取名义 = **`Reader3Epub` 公开面**，因此 9 个成员一个不漏。

### 全量枚举（`epub-renderer.js` 的 `window.Reader3Epub =` 处，2026-08-16 逐项核实）

| 成员 | 用途 | 实测消费方 | 处置 |
|---|---|---|---|
| `rendition` | epub.js Rendition 实例 | `annotations.js` | **纳入** |
| `getContents()` | 当前 Contents | `annotations.js`（两处） | **纳入** |
| `getContentRoot()` | iframe `body` | `annotations.js`、**`search.js`** | **纳入** |
| `getFrameElement()` | iframe 元素 —— **K3 全靠它** | `annotations.js` | **纳入** |
| `onContentsReady(cb)` | 内容就绪回调 | `annotations.js`、**`search.js`** | **纳入** |
| `applyThemeSettings()` | 重新套用主题到 iframe | `reader.html` | **纳入** —— 4B.3 依赖 |
| `displaySectionIndex(i)` | 跳转到 spine 第 i 项 | `reader.html` | **纳入** —— 章节导航依赖 |
| `getContentDocument()` | iframe document | **无** | **deprecate**，4B.2 结束时移除；等价写法 `getContentRoot().ownerDocument` |
| `book` | epub.js Book 实例 | **无** | **deprecate**，4B.2 结束时移除；暴露整个 Book 实例等于没有边界 |

**冻结面 = 7 个成员**，签名与行为不变。

> **两处易被漏掉的事实**（2026-08-16 全仓 grep 核实）：
> 1. **`search.js` 也是 K5 的消费方**，不只是 annotations。改动 `getContentRoot` / `onContentsReady` 会同时打断阅读页内搜索——4B.1 只拆 `annotations.js`，但 K5 的爆炸半径比 4B.1 大。
> 2. 上游计划原本只冻结 5 个成员，漏掉 `applyThemeSettings` 与 `displaySectionIndex`；按原措辞 **4B.3 没有任何合法路径可走**。

**4B.1 验收**：把 7 个纳入项写成 `renderer.ts` 顶部的显式 interface，签名不变；两个 deprecate 项加 `@deprecated` 注释并写明移除阶段。

---

## K6 — URL 形状

| 项 | 内容 |
|---|---|
| 契约 | `/read/{bookId}/{chapterIndex}` |
| 现状 | `getReaderContext()` 优先读 `window.Reader3Ctx`，**读不到就回退解析 `location.pathname`** |
| 打断方式 | 新外壳若改成查询参数或 SPA 路由，回退分支会**静默解析出错误的 chapterIndex** → 批注存到错章 |
| 失败是否可见 | ❌ **静默，且污染用户数据**——本组最坏的结果 |

```js
function getReaderContext() {
  const ctx = window.Reader3Ctx || {};
  if (ctx.bookId && Number.isFinite(ctx.chapterIndex)) {
    return { bookId: ctx.bookId, chapterIndex: Number(ctx.chapterIndex) };
  }
  const parts = window.location.pathname.split("/").filter(Boolean);
  if (parts.length >= 3 && parts[0] === "read") {
    return { bookId: parts[1], chapterIndex: Number(parts[2]) };
  }
  return { bookId: null, chapterIndex: null };
}
```

**4B.1 验收**：**删除 `location.pathname` 回退分支**。`window.Reader3Ctx` 读不到时直接抛错，不要猜。这是 4B.1 里唯一一处**故意的行为变更**——保留它意味着 4B.2 改路由后批注静默存到错章，污染用户数据的代价远高于少一层兜底。

---

## 不受本组契约约束的部分

不必回归，省下的精力放到上面六条：

- **高亮的实际渲染** —— 作用于 `contents.document.body`，在 iframe 内；4B.2 明令不碰
- **锚定与持久化** —— CFI + quote/prefix/suffix + 后端，属 Phase 3 范畴
- **`mark.annotation` 的 data 属性** —— `data-annotation-ids` / `data-annotation-meta` / `data-note-text`，由 `annotations.js` 自产自销，全程在 iframe 内

---

## 门槛

- **Phase 0 出口**：本文冻结，六条各自的合法取值写入代码常量或注释。
- **Phase 4B 出口**：六条**各有一条能失败的断言**。尤其 K3（断言工具条坐标落在选区附近）与 K6（断言批注写入的 chapterIndex 正确）——断言"元素存在"对这两条无效。
