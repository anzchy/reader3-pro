# Reader3 Pro 前端设计规格

- **日期**: 2026-08-15（2026-08-16 修订）
- **状态**: 提议（待批准）
- **范围**: `settings.html` / `library.html` / `reader.html` **外壳**三页

> ### 权威范围
>
> **本文权威**：双层 token 体系（§3）、`data-testid` 命名（§4）、组件清单（§5）、逐页规格（§6）、**iframe 边界与其例外（§6.0）**、降级状态设计（§6.4）、响应式断点（§7）、可访问性契约（§8）。
>
> **本文不权威**：实施顺序、阶段划分、分支编号 —— 见 [`plan-ui-migration-sequencing.md`](./plan-ui-migration-sequencing.md)。技术栈选型与后端架构 —— 见 [`plan-tech-stack-migration.md`](./plan-tech-stack-migration.md)。原型 → 生产的翻译规则 —— 见 [`designs/reader-pro-next/README.md`](../../../designs/reader-pro-next/README.md)。
>
> 要改上面任何一项，改它的权威文档，不要在这里加一份副本。
- **参考**: `designs/reader-pro-next/spec/reader-pro-spec.md`（现状实现审计，**设计风格基准**）、`docs/design-reference/feeddock-frontend-spec.md`（结构模板）、`lightwhale-website-analysis/`（视觉方向）
- **现状证据**: [`designs/reader-pro-next/spec/screenshots/`](../../../designs/reader-pro-next/spec/screenshots/) —— 11 个界面 × 桌面/移动双视口共 22 张实测截图（2026-08-15），对应 spec §14；由此新增的缺陷见 §1.5（D5–D7）与 spec §14.1（G-10–G-17）

---

## 0. 语言（已确认 2026-08-16）

**en 为主语言，zh-CN 为次。** 见 `designs/reader-pro-next/spec/reader-pro-spec.md` §0.3 决策 D-2。

原假设是 zh-CN 为主，依据是 `reader.html` 已全中文（"主题"/"当前字号"/"点评此书"/"复制全部笔记"）且设计参考（得到、语鲸）均为中文产品。该假设**未被采纳**——`library.html` 与 `annotation-toolbar` 本就是英文，原型已按英文全量落地。

落地方式：第 5 节文案以英文为准；Phase 4A 建立类型化消息表，`en` 为默认 locale，`zh-CN` 后补。同一 app 三种语言策略的问题由消息表统一收口。

---

## 1. 现状审计：四个必须先决策的缺陷

设计之前必须先拍板的，不是配色，是这四件事。

### D1 🔴 字体设置面板是纯装饰，零功能

`reader.html` 的 `#font-settings-popup` 面板包含：

| 控件 | DOM | 处理器 |
|---|---|---|
| 主题 ×4（白色/黄色/护眼/夜间） | `.theme-option` 裸 `<div>`，无 id 无 data 属性 | **无** |
| 字号 ± | `#font-size-increase` / `#font-size-decrease` | **无** |
| 段落间距 ± | `#line-height-increase` / `#line-height-decrease` | **无** |
| 字体 ×4（系统/得到今楷/汉仪旗黑/思源宋体） | `.font-option` 裸 `<div>` | **无** |

全仓库 `grep` 确认：`toolbar.js` 只负责这个面板的**开/关**（`RightToolbar` 的 outside-click `ignoreSelectors` 与 `#reader-font-toggle` 绑定），面板内 12 个控件没有任何一个被绑定。字号显示恒为 `17`，间距恒为 `1.9`。

> **这不是"视觉需要 polish"，是阅读器最高频的控件根本不存在。** 任何 reader 的设计规格如果绕过它，做出来还是个假面板。

**决策**：本规格把阅读设置定义为**功能规格**（§6.3），并把它和 §3 的暗色模式统一到一个 `data-reading-theme` 契约上。字体 ×4 中的三款中文商业字体（得到今楷/汉仪旗黑/思源宋体）**未授权且未打包，删掉**，只保留 系统黑体 / 思源宋体（可 self-host 的开源字体）二选一。

### D2 🔴 暗色模式在全站不存在

`grep "prefers-color-scheme|data-theme"` 在 `*.css` 全仓库 **0 命中**。`dedao-theme.css` 的 `:root` 是 60 个**字面量** token（`--dedao-bg: #f5f5f5`），字面量 token 结构上无法主题化。所以"夜间"按钮即使接上也没有可切的东西。

**决策**：§3 引入双层 token（palette → semantic），暗色模式只重定义 semantic 层。

### D3 🟠 `settings.html` 完全在设计系统之外

76 行、独立 `settings.css`（189 行）、不引 `dedao-theme.css`、全英文、无返回按钮以外的导航。是全站唯一没有品牌一致性的页面。

**决策**：作为 §3 token 体系的**试点页**先落地——风险最低，且能在铺开到 library 之前验证整套 token。

### D4 🟠 响应式基本不存在

全站 9 条 `@media`（reader 3 / dedao-theme 2 / library 2 / search 1 / library 1），`settings.css` 与 `css/` 下 5 个文件 **0 条**。`reader.html` 的 `.nav-zone-left/right` 是覆盖左右两侧的点击翻页热区——在触屏上会直接吞掉滚动和选词，而选词是标注功能的入口。

**决策**：§7 定义三档断点，并规定 `nav-zone` 在 `<1024px` 一律禁用。

### 1.5 浏览器实测补充的三个缺陷（D5–D7）

D1–D4 来自读代码。以下三条来自 2026-08-15 的真实浏览器复核，截图证据见 [`designs/reader-pro-next/spec/screenshots/`](../../../designs/reader-pro-next/spec/screenshots/) 与 spec §14.1。它们同样属于"设计前必须拍板"，因为每一条都改变某一页的规格。

#### D5 🔴 正文没有最大宽度约束

`06-reader-desktop.png`：1440×900 下正文横贯整个视口，单行约 180 字符。`dedao-theme.css` 定义了 `--dedao-content-max: 768px`，但它没有被应用到 epub.js 的 viewport 上。移动端（`06-reader-mobile.png`）则是两端对齐在 285px 栏宽下产生明显字间空隙。

> 这是本次审计里对**阅读体验**影响最大的一条——比配色、比暗色模式都大。一个阅读器的正文行长失控，等于核心功能失效。

**决策**：§6.3 增加正文栏宽为**一等规格项**：目标行长 45–75 字符，通过 epub.js `themes.override` 注入 `max-width` + `margin: auto`，并与阅读设置的字号联动。两端对齐改为左对齐（`text-align: start`）。**注意这需要写入 iframe 内部样式，是 §6.0 范围边界的一个显式例外**，见下方修订。

#### D6 🟠 面板是覆盖式的，且会互相堆叠并阻断工具栏

`07`/`08`/`10` 三张桌面截图显示：TOC、Notes、AI 面板都**盖在正文上**而不是挤压布局，读者一打开目录就看不见正文。更严重的是实测中 TOC/Notes 打开时点击 `#reader-search-toggle` 直接**超时**——遮罩拦截了工具栏点击，而 `toolbar.js:closeAllPanels()` 只关闭 search 与 AI 两个面板。

**决策**：§6.3 定义**单一面板栈**契约——同一时刻至多一个 reader 面板可见，打开任一面板前先关闭其余全部；工具栏永远位于面板之上且可点击。≥1280px 时面板改为挤压布局（正文栏同步收窄），<1280px 保持覆盖。

#### D7 🟠 阅读进度有两个互相矛盾的数值

`08-reader-notes-desktop.png` 一屏之内同时出现「已读到 26%」（Notes 面板）与「当前阅读至 20%」（页脚）。另外打开 spine 0（纯封面页）时页脚显示「当前阅读至 100%」。

**决策**：进度是**单一数据源**，由 epub.js 的 location 计算，所有消费方（页脚、Notes 面板、书库卡片）读同一个值。封面等非正文 spine 项不计入进度分母。这条属于逻辑缺陷，实现归 migration plan Phase 4，本规格只锁定"同屏不得出现两个进度数字"这一验收条件。

---

## 2. 页面清单与路由

| 页面 | URL | 模板 | 本次范围 |
|---|---|---|---|
| 书库 | `/` | `library.html` | 全量重设计 |
| 阅读器 | `/read/{book_id}/{chapter_index}` | `reader.html` | **仅外壳**，见 §6.0 边界 |
| 设置 | `/settings` | `settings.html` | 全量重设计（试点） |
| ~~经典书库~~ | `READER3_LIBRARY_UI=classic` | `library_classic.html` | **删除**，不设计 |

---

## 3. 设计 Token 体系

### 3.1 结构：双层

现状 `--dedao-*` 是单层字面量，无法主题化（D2）。改为：

```
Tier 1  Palette（原始值，与主题无关）      --p-*
   ↓
Tier 2  Semantic（角色，逐主题重定义）     --r3-*
   ↓
组件 CSS 只允许引用 Tier 2
```

`--dedao-*` 保留为指向 Tier 2 的**弃用别名**，让现有 3205 行 CSS 在迁移期继续工作；Phase 4 结束时删除。

> **规则**：任何新写的 CSS 引用 `--p-*` 或 `--dedao-*` 都是错的。只引用 `--r3-*`。

### 3.2 Tier 1 — Palette

> **已确认 2026-08-16**：品牌色由暖橙 `#ff6b00` 改为蓝色 `#3b82f6`（决策 D-5，见 spec §0.3）。
> 因此原 `--p-blue-500` 作为 status/info 与品牌撞色，info 改用青色以保持可区分。
> 纸色以原型实测值为准（原规格的 sepia/green/night 三值已被原型对比后调整）。

```css
:root {
  /* Brand — 蓝，D-5 确认；与下方 status 的 info 刻意不同色相 */
  --p-blue-50:#eff6ff;  --p-blue-400:#60a5fa; --p-blue-500:#3b82f6;
  --p-blue-600:#2563eb; --p-blue-950:#172554;

  /* Neutral — 中性灰阶，替代散落的 #333/#666/#999/#ccc */
  --p-gray-0:#ffffff;  --p-gray-50:#fafafa;  --p-gray-100:#f5f5f5;
  --p-gray-200:#eeeeee; --p-gray-300:#e5e5e5; --p-gray-400:#cccccc;
  --p-gray-500:#999999; --p-gray-600:#666666; --p-gray-700:#4a4a4a;
  --p-gray-800:#333333; --p-gray-900:#1f2d3d; --p-gray-950:#17222e;

  /* Reading surfaces — 四个阅读主题的纸色，取原型实测值 */
  --p-paper-white:#ffffff; --p-paper-sepia:#f6ecd8;
  --p-paper-green:#dcece0; --p-paper-night:#10151f;

  /* Status — 每色三档：700 亮色前景 / 400 夜间前景 / 100 亮色淡底。
     原先每色只有 500 一档，亮色下四个全部不达 4.5:1，见 §3.3 下方实测表 */
  --p-green-100:#dcfce7; --p-green-400:#4ade80; --p-green-700:#15803d;
  --p-amber-100:#fef3c7; --p-amber-400:#fbbf24; --p-amber-700:#b45309;
  --p-red-100:#fee2e2;   --p-red-400:#f87171;   --p-red-700:#b91c1c;
  --p-cyan-100:#e0f2fe;  --p-cyan-400:#22d3ee;  --p-cyan-700:#0e7490;
  /* 夜间淡底：100 档在深底上是白块，四个深色调另取（手调，不在 Tailwind 阶上） */
  --p-green-950:#14321f; --p-amber-950:#3a2a08;
  --p-red-950:#3b1717;   --p-cyan-950:#10283d;

  /* Annotation — 亮/暗两组，暗色下原色在深底上刺眼 */
  --p-hl-yellow:#fbbf24; --p-hl-green:#4ade80;
  --p-hl-pink:#f87171;   --p-hl-blue:#60a5fa;
  --p-hl-yellow-dk:#8a6d1f; --p-hl-green-dk:#2f6b3d;
  --p-hl-pink-dk:#7d3b3b;   --p-hl-blue-dk:#2f5580;
}
```

> ⚠️ 现有 `--dedao-highlight-red` 与数据模型的 `MarkerColor` 枚举（`yellow|green|pink|blue`）**对不上**——CSS 叫 red，数据叫 pink。以数据模型为准，统一为 `pink`。

### 3.3 Tier 2 — Semantic（组件唯一可用层）

```css
:root {                      /* 亮色为默认 */
  --r3-bg:            var(--p-gray-100);   /* 页面底 */
  --r3-surface:       var(--p-gray-0);     /* 卡片 */
  --r3-surface-raised:var(--p-gray-0);     /* 弹层/抽屉 */
  --r3-surface-sunken:var(--p-gray-50);    /* 输入框/代码块 */
  --r3-surface-hover: var(--p-gray-200);

  --r3-text:          var(--p-gray-800);
  --r3-text-muted:    var(--p-gray-600);
  --r3-text-subtle:   var(--p-gray-500);
  --r3-text-disabled: var(--p-gray-400);
  --r3-text-on-accent:var(--p-gray-0);
  --r3-text-quiet:    var(--p-gray-500);   /* 此前只在阅读主题里出现，:root 无定义 */

  --r3-border:        var(--p-gray-300);
  --r3-border-subtle: #f0f0f0;
  --r3-border-strong: var(--p-gray-400);

  --r3-accent:        var(--p-blue-500);
  --r3-accent-hover:  var(--p-blue-600);
  --r3-accent-subtle: var(--p-blue-50);
  --r3-focus-ring:    var(--p-blue-500);

  /* 状态色两个角色：前景 ＋ 淡底。边框不另设 token——前景色直接当边框，
     压在自己的淡底上 4.5–5.3:1，已过 WCAG 1.4.11 的 3:1 */
  --r3-success:var(--p-green-700); --r3-warning:var(--p-amber-700);
  --r3-error:var(--p-red-700);     --r3-info:var(--p-cyan-700);
  --r3-success-subtle:var(--p-green-100); --r3-warning-subtle:var(--p-amber-100);
  --r3-error-subtle:var(--p-red-100);     --r3-info-subtle:var(--p-cyan-100);

  --r3-hl-yellow:var(--p-hl-yellow); --r3-hl-green:var(--p-hl-green);
  --r3-hl-pink:var(--p-hl-pink);     --r3-hl-blue:var(--p-hl-blue);

  --r3-shadow-sm:0 1px 3px rgb(0 0 0 / .05);
  --r3-shadow-md:0 2px 10px rgb(0 0 0 / .05);
  --r3-shadow-lg:0 4px 20px rgb(0 0 0 / .10);
}

:root[data-reading-theme="night"] {
  /* --r3-bg / --r3-surface / --r3-text 刻意不在这里定义：下面那组阅读主题里
     同选择器的 night 规则会覆盖它们，写在这里是永远生效不了的死值 */
  --r3-surface-raised:#242424; --r3-surface-sunken:#141414;
  --r3-surface-hover:#2a2a2a;
  --r3-text-muted:#8f8f8f;
  --r3-text-subtle:#6b6b6b; --r3-text-disabled:#4a4a4a;
  --r3-border:#2f2f2f; --r3-border-subtle:#242424; --r3-border-strong:#3f3f3f;
  --r3-accent:var(--p-blue-400);   /* D-5 改蓝后同步；原值 #ff8534 是暖橙时代的残留 */
  --r3-accent-subtle:var(--p-blue-950);
  --r3-success:var(--p-green-400); --r3-warning:var(--p-amber-400);
  --r3-error:var(--p-red-400);     --r3-info:var(--p-cyan-400);
  --r3-success-subtle:var(--p-green-950); --r3-warning-subtle:var(--p-amber-950);
  --r3-error-subtle:var(--p-red-950);     --r3-info-subtle:var(--p-cyan-950);
  --r3-hl-yellow:var(--p-hl-yellow-dk); --r3-hl-green:var(--p-hl-green-dk);
  --r3-hl-pink:var(--p-hl-pink-dk);     --r3-hl-blue:var(--p-hl-blue-dk);
  --r3-shadow-sm:0 1px 3px rgb(0 0 0 / .4);
  --r3-shadow-md:0 2px 10px rgb(0 0 0 / .4);
  --r3-shadow-lg:0 4px 20px rgb(0 0 0 / .6);
}

/* 阅读主题只改正文表面，不改 app chrome；ink/quiet 取原型实测值 */
:root[data-reading-theme="sepia"] { --r3-bg:#ece0c8; --r3-surface:var(--p-paper-sepia); --r3-text:#4a3b28; --r3-text-quiet:#8a7455; }
:root[data-reading-theme="green"] { --r3-bg:#cfe2d4; --r3-surface:var(--p-paper-green); --r3-text:#24382a; --r3-text-quiet:#5b7563; }
:root[data-reading-theme="night"] { --r3-bg:#080b12; --r3-surface:var(--p-paper-night); --r3-text:#c2ccdb; --r3-text-quiet:#7e8ca3; }
```

**状态色实测对比度**（2026-08-16，WCAG 2.1 相对亮度公式）——这四组不是挑好看的，是挑过线的：

| 角色 | 亮色前景 / 白面 | 同前景 / 自己的淡底 | 夜间前景 / 纸夜底 |
|---|---|---|---|
| success | `#15803d` **5.02** | 4.57 | `#4ade80` **10.49** |
| warning | `#b45309` **5.02** | 4.51 | `#fbbf24` **10.95** |
| error | `#b91c1c` **6.47** | 5.30 | `#f87171` **6.61** |
| info | `#0e7490` **5.36** | 4.67 | `#22d3ee` **10.11** |

> **被换掉的 500 单档在亮色下全线不合格**：green-500 2.28、amber-500 2.15、red-500 3.76、cyan-600 3.68，全部低于 §8 要求的 4.5:1。夜间反而都过（4.86–8.51）。**这是个亮色缺陷，不是暗色缺陷**——与直觉相反，所以之前没人查。
>
> **淡底不能独自表达状态。** 四个 `-subtle` 压在页面底上只有 1.10–1.22:1（亮色）、1.15–1.32:1（夜间）。只染一层底色的横幅在两个主题下都近乎看不见。**横幅必须同时有边框或图标**，边框直接用状态前景色。

> `paper`（默认）不设 `data-reading-theme`，直接继承 `:root` 的 light/dark semantic 值。上面三个主题的 `--r3-bg` 是纸色的略暗衬底，由纸色派生。

**跟随系统**：`data-reading-theme` 未设置时，`@media (prefers-color-scheme: dark)` 套用 night 的 semantic 值。用户显式选择后写入 `localStorage.reader3_reading_theme` 并 stamp 到 `<html>`，显式选择优先。

> **闪白（FOUC）**：主题必须在首屏绘制前生效。`<head>` 内嵌一段同步 inline script 读 `localStorage` 并 stamp `data-reading-theme`，**不能**等 `defer` 的 JS。这条容易漏，漏了每次刷新都白闪一下。

### 3.4 间距 / 圆角 / 字阶

间距沿用现值（4/8/16/24/32/48），重命名为 `--r3-space-{xs,sm,md,lg,xl,2xl}`。圆角沿用（4/6/8/12/full）。

布局宽度（§6.2 的三栏 Grid 引用，此前未定义）：

```css
--r3-sidebar-w:232px;  /* 书库左栏，取原型 --sidebar-width */
--r3-right-w:336px;    /* 书库右栏，取原型 --insights-width */
--r3-right-w-collapsed:48px;
```

字阶是**新增**——现状没有字号 token，全站硬编码 px：

```css
--r3-text-xs:12px;  --r3-text-sm:13px; --r3-text-base:14px;
--r3-text-md:16px;  --r3-text-lg:18px; --r3-text-xl:22px; --r3-text-2xl:28px;
--r3-leading-tight:1.4; --r3-leading-normal:1.6; --r3-leading-reading:1.9;
```

**字体**：`--r3-font-sans` 沿用系统栈。`--r3-font-serif` 现在指向 Google Fonts 的 `Noto Serif SC`——**这是个离线故障点**（自托管应用连外网 CDN，断网即回退且首屏跳字）。改为 self-host 思源宋体子集，或直接回退到系统 `PingFang SC` / `Songti SC`。

---

## 4. 可测试性契约（`data-testid`）

**这是本规格与 migration plan 之间最关键的一条接口。**

Plan 的 Phase 1b 会写 Playwright E2E 并作为 Phase 4 的合并门槛。如果 E2E 用 class 或 DOM 结构做选择器，本规格的任何布局改动都会推翻 E2E。

**规则（须写入 Phase 0）**：

1. 每个交互元素、每个可断言区域必须有 `data-testid`。
2. E2E **只允许**用 `data-testid` 和 ARIA role/name 定位。禁止 class 选择器、禁止 `nth-child`、禁止层级结构选择器。
3. `data-testid` 命名 `{page}-{region}-{element}`，一经确定不随视觉改动而变。
4. 重设计可以任意改 class、改嵌套、改标签——但**不得改 testid**。
5. testid 的值必须是**字符串字面量**，不得由变量拼接或模板插值产生（原型的 `data-testid={"status-" + props.status}` 是错的，改静态映射表）。两条理由：命名 lint 扫的是字面量，拼出来的它看不见；且 testid 契约的价值有一半在**可 grep**——一个在仓库里搜不到的 testid，E2E 挂了没人找得到它是谁发的。

命名约定：

| 页面 | 前缀 | 示例 |
|---|---|---|
| 书库 | `lib-` | `lib-book-card` / `lib-sidebar-collection` / `lib-toolbar-sort` |
| 阅读器 | `rd-` | `rd-toolbar-toc` / `rd-anno-color-yellow` / `rd-notes-panel` |
| 设置 | `set-` | `set-provider-row` / `set-save-prefs` |

> 现状许多元素已有稳定 `id`（`#chat-send-btn`、`#reader-toc-toggle`），可直接映射为 testid，成本很低。**但必须在 Phase 1b 写 E2E 之前完成**，否则就是返工。

### 4.1 与原型的对账（2026-08-16 实测）

原型 `designs/reader-pro-next/` 现有 **134 个唯一 `data-testid`，其中符合上表前缀方案的：0 个。**

> ⚠️ 容易看错的一点：有 24 个 testid 带 `reader-` / `library-` 前缀，形似合规，实则是**另一套**命名（页面全称而非 `rd-` / `lib-`）。它们比裸名更危险——批量改名时容易被当成"已经对了"而跳过。**134 个全部需要改名。**

已经出现的漂移：同一个概念"一条搜索命中"，在书库是 `search-hit`，在阅读器是 `reader-search-hit`；而 `search-empty` / `search-loading` / `search-failed` 三个裸名被阅读器占用了——书库搜索一旦补上空态就会撞名。

**改名方向**：先改**原型**，再回贴到现有 Jinja 模板，不能反过来。理由：

- E2E 必须活过整个替换过程，而替换之后的 DOM 就是原型的 DOM；
- 从现有模板反推，新设计独有的元素（主题切换、阅读主题选择、章节首尾禁用态、§6.4 的五个降级状态）拿不到 testid；
- 随 Classic 一起删掉的元素会白拿 testid。

这就是整套迁移的 strangler-fig 接缝：**testid 是唯一横跨新旧两套实现的不变量。**

---

## 5. 组件清单

跨页共用，实现为独立 CSS 模块 + （Phase 4 后）TS 组件。

| 组件 | 现状 | 变更 |
|---|---|---|
| `Button` | `.toolbar-btn` / `.mini-btn` / `.btn` / `.rt-btn` / `.nav-btn` / `.ai-btn` / `.drawer-btn` **七套** | 收敛为 `.r3-btn` + `--primary/--danger/--ghost/--icon` 修饰符 |
| `Badge / Pill` | `.badge` / `.status-pill` / `.chunk-pill` | 收敛为 `.r3-badge` + 状态色修饰符 |
| `Modal` | `<dialog class="modal">` ×5，结构一致 | 保留 `<dialog>`（原生 a11y 好），抽 `.r3-modal` |
| `Drawer / Panel` | `#reader-search-drawer` / `#reader-ai-panel` / `#toc-mode` / `#notes-mode` 各写一套 | 统一 `.r3-panel` + 进出场动效 + 焦点陷阱 |
| `FormField` | `.form-field`/`.form-label`/`.form-error` | 保留，补 `aria-describedby` 绑定 |
| `EmptyState` | 仅 library 有 `.empty-state` | 抽为共用；search / chat / notes 结果为空时统一使用 |
| `Toast` | **不存在**，现用 `.status` `<span>` 就地显示 | 新增；破坏性操作反馈需要它 |
| `Skeleton` | **不存在**，现为 `-` 或 `Loading...` 文本 | 新增；书库卡片与统计数字用骨架屏 |

> ⚠️ **`Modal` 一行的"保留 `<dialog>`"说的是现有 Jinja 模板；原型 `components.jsx` 的 `Modal` 是 `div.overlay` ＋ `role="dialog"`，已经不是原生 `<dialog>` 了。** 两边选型未收敛。这条差异在 §6.4 的 S5 上会咬人（原生 `<dialog>` 的 Esc 关闭要靠 `cancel` 事件 `preventDefault()` 才拦得住，div 版只要不接 Esc 即可），由 Track D 裁定并回写本表。

---

## 6. 逐页规格

### 6.0 阅读器的范围边界（硬约束）

> **`reader.html` 的重设计只覆盖"外壳"，绝不触碰 iframe 内部。**

| 归本规格管 | **不归本规格管** |
|---|---|
| 右侧工具栏、TOC 面板、笔记面板 | epub.js iframe 内的正文 DOM |
| 搜索抽屉、AI 面板、字体设置面板 | 正文排版（走 epub.js `themes.override`） |
| 标注工具条、笔记编辑器、tooltip（**iframe 外**） | `<mark>` 的插入位置与锚定逻辑 |
| 章节导航、进度指示、翻页热区 | CFI / text-offset 计算 |

理由：标注锚定依赖 iframe 内 DOM 结构与空白，migration plan 评审已把"逐章文本相等但标注已错位"列为最可能的失败模式。**iframe 内的任何改动都属于 Phase 4B 的行为变更范畴，不属于设计。**

例外只有一类，且边界严格：**通过 `themes.override()` 注入 iframe 的纯 CSS 属性，不改 DOM 结构、不改文本节点、不改空白**。落在这一类里的只有两项：

1. §6.3 的阅读主题（背景/前景色）。
2. **D5 的正文栏宽**（`max-width` / `margin` / `text-align` / `font-size` / `line-height`）。

#### 判定标准（canonical，全仓库唯一定义处）

> **本小节是 iframe 边界判据的唯一定义处。** 主计划 §7 的 Phase 4B 门槛、`docs/plans/20260816-tech-stack-and-ui-changes/tasks/014-ts-frontend-reader.md` §4B.2、技术栈计划 Phase 4 的主题项**只引用本小节，不复述判据**——复述会漂移。

原判据是「`document.body.textContent` 与所有文本节点的偏移量逐字节不变」。这条**必要但不充分**，且"逐字节"对 JS DOMString 不是可执行定义：

- **不充分**：把一个文本节点包进 `<span>`，或把它拆成两个相邻文本节点，扁平文本与偏移量完全不变，但 **CFI 变了**——CFI 编码的是 DOM path 上的子节点序号，不是扁平文本位置。标注的 CFI 路会静默锚错，而 text-offset 路照常工作，于是两路不一致且只有 CFI 那路坏。
- **不可执行**："逐字节"取决于编码；JS 字符串是 UTF-16 code unit 序列，没有"字节"这个层级。

改为**三重断言，全部通过才算落在允许范围内**：

**A — 文本序列不变**

```js
// JS 的 === 就是 UTF-16 code unit 序列比较，这一条本身即精确定义
before.body.textContent === after.body.textContent
```

**B — body 结构签名不变**（这条是 A 补不上的那半）

```js
// 捕获元素嵌套、子节点序号、文本节点切分点与长度 —— 即 CFI 依赖的全部信息
function bodySignature(body) {
  const parts = [];
  (function walk(node, path) {
    const kids = node.childNodes;
    for (let i = 0; i < kids.length; i++) {
      const n = kids[i];
      if (n.nodeType === 1) {            // ELEMENT_NODE
        parts.push(`${path}/${i}:${n.tagName}`);
        walk(n, `${path}/${i}`);
      } else if (n.nodeType === 3) {     // TEXT_NODE
        parts.push(`${path}/${i}:#text(${n.data.length})`);
      }
    }
  })(body, '');
  return parts.join('|');
}
```

签名**只覆盖 `<body>`**：`themes.override()` 注入的是 `<head>` 里的 `<style>`，不进 body；把 head 算进签名会让每次主题切换都判失败。签名**不含属性**：CSS 类与 style 属性的变化不影响 CFI，允许。

**C — CFI 往返解析到同一段文字**（唯一直接证明目标属性的断言）

取一条既有标注的 CFI，在改动前后各解析一次，`range.toString()` 必须等于存储的 `quote`。A 与 B 是静态护栏，C 是真正的证明——A、B 只能说明"没做已知会破坏 CFI 的事"，C 说明"CFI 确实没坏"。

**落点分工**：A + B 是**机械门槛**，对每一次 `themes.override()` 改动都要跑（结构测试，不需要完整 E2E）；C 是 **E2E**，见 `docs/plans/20260816-tech-stack-and-ui-changes/tasks/009-e2e-annotations.md` 的 R-6。

不满足任何一条的改动，一律划归 Phase 4B 的行为变更，不属于设计。

> ⚠️ 即便如此，栏宽变化会改变**分页位置**。CFI 锚定理论上不受影响（CFI 基于 DOM 路径而非视觉位置），但这要被**断言**，不能被假定——即上面的断言 C。
>
> 落点：断言 C 由 `docs/plans/20260816-tech-stack-and-ui-changes/tasks/009-e2e-annotations.md` **R-6** 承担。R-6 在 Phase 1b 覆盖今天已存在的三个参数（主题 / 字号 / 行距）；**栏宽是 D5 的产物，要到 4B.3 才存在**，届时作为 R-6 的第四个参数加入，并计入 4B.3 的退出门槛。本节此前写的是"Phase 1b 的 E2E 必须覆盖改栏宽后…"——那在顺序上不可能成立，栏宽那时还没做。

### 6.1 设置页（试点，先做）

**布局**：单栏居中，`max-width: 720px`，页头用与 library 一致的 `header`（现在只有一个 `← Back to Library` 文字链，导航不一致）。

**分区**（沿用现有四段，重新组织）：

1. **AI 偏好** — 默认 provider（下拉）、流式开关、时间戳开关。删除 `Auto suggested questions (future)`——不做的功能不该占一行 UI。
2. **服务商** — `#settings-providers` 动态渲染。每个 provider 一张卡：名称 + 启用开关 + API key（`type=password`，已配置显示 `••••••••` + "已配置"徽章）+ 模型 + 测试连接按钮。**新增连接状态指示**（未配置 / 已配置 / 测试通过 / 测试失败）。
3. **外观**（**新增分区**）— 阅读主题四选一 + 界面语言。与 §6.3 的 reader 面板共用同一份状态。
4. **数据** — 清空对话 / 清空摘要 / 导出 / 导入。**破坏性操作必须二次确认**：现在 `Clear conversations` 是点了就执行，无确认。用 `<dialog>` 确认（**不要用 `confirm()`**——浏览器模态会阻塞，且不可测）。

**状态**：加载中（骨架）/ 保存中（按钮 disabled + spinner）/ 保存成功（Toast，2s 自动消失）/ 保存失败（就地错误 + 保留用户输入）。

**安全**：API key 永不回显（后端已保证不返回明文，前端不得把已填 key 写进可读 DOM）。

### 6.2 书库页

**布局**：三栏 CSS Grid，`grid-template-columns: var(--r3-sidebar-w) 1fr var(--r3-right-w)`，中栏 `1fr` 且 `min-width: 0`（现状缺这条，长书名会把网格撑破）。

| 区域 | 变更 |
|---|---|
| Header | 保留 logo + 导航 + 主操作。**新增**阅读主题切换按钮（与 reader 一致，避免只有 reader 能切） |
| 左栏 Types | 保留。`PDF` 项 `disabled` 但仍显示计数——要么实现要么删，不留死项 |
| 左栏 Collections | 保留。`.collection-actions`（Clean / Delete）现在常驻显示，噪音大 → 改为 hover / focus-within 显示，键盘可达 |
| 工具栏 | 搜索、排序、视图切换、多选。图标现在是 emoji（`🔍` `▦` `✓`）→ 换 SVG，与 reader 的 SVG 图标风格统一 |
| 书卡网格 | **重点**。封面比例锁定 `2:3`（`aspect-ratio`），无封面用书名首字生成占位（现在是空白 div）；标题 2 行截断，作者 1 行 |
| 列表视图 | 保留表格。补 `<caption class="sr-only">` 与排序列的 `aria-sort` |
| 右栏三 Tab | Dashboard / Chat / Search。Chat 的 `All books` / `Collection` 两个 disabled 的 "Coming soon" → **删掉**，不做的不占位 |
| 模态 ×5 | 统一 `.r3-modal` |

**状态**：书库为空（现有 `.empty-state`，保留并美化）/ 加载中（书卡骨架，替代当前每张卡上的 `Loading...` pill）/ 索引进行中（卡片角标 + 顶部进度）/ 索引失败（现有 errors modal）。

### 6.3 阅读器外壳

**阅读设置面板（D1，从零实现）**

统一为一个 `data-reading-theme` 契约，同时驱动 **app chrome**（§3.3 semantic token）和 **iframe 正文**（epub.js `themes.override`）：

| 控件 | 值域 | 持久化 | 作用域 |
|---|---|---|---|
| 主题 | `white` / `sepia` / `green` / `night` | `localStorage.reader3_reading_theme` | 全局（chrome + iframe） |
| 字号 | 14–24px，步长 1，默认 17 | `localStorage.reader3_font_size` | 仅 iframe |
| 行距 | 1.4–2.4，步长 0.1，默认 1.9 | `localStorage.reader3_line_height` | 仅 iframe |
| 字体 | `system` / `serif` **（二选一）** | `localStorage.reader3_font_family` | 仅 iframe |

- 四个 `.theme-option` / 两个 `.font-option` 必须带 `data-value`，用 `role="radiogroup"` + `aria-checked`，键盘方向键可切（现在是裸 `<div>`，鼠标键盘都不可用）。
- 字号/行距按钮到达边界时 `disabled`，并显示实际值（现在恒为 17 / 1.9）。
- 删除 得到今楷 / 汉仪旗黑 / 思源宋体 三项商业字体——未授权、未打包、点了没反应。

**正文栏宽（D5，一等规格项）**

| 项 | 规格 |
|---|---|
| 目标行长 | 45–75 字符（中文 22–36 全角字） |
| 实现 | `themes.override()` 注入 `max-width: 38rem; margin-inline: auto;`，`rem` 随字号联动 |
| 对齐 | `text-align: start`（现状两端对齐，窄屏产生字间空隙 rivers） |
| 左右留白 | 最小 `clamp(16px, 5vw, 64px)`，保证工具栏不压正文 |
| 验收 | 1440×900 与 390×844 两档下，任取一段测量行长均落在区间内 |

**右侧工具栏**：保留 6 个 SVG 按钮（返回 / 目录 / 搜索 / AI / 字体 / 笔记）。**新增**：当前激活面板的按钮需要选中态（现在打开 TOC 后工具栏无任何反馈）。工具栏 `z-index` 必须高于所有面板与遮罩，且任何面板打开时都保持可点击。

**面板互斥（D6）**：TOC / 笔记 / 搜索 / AI / 字体 五个面板同时只允许一个打开。`toolbar.js` 现在只处理了 search 与 ai 两个的互斥（`closeAllPanels` 只关这两个），TOC 和 notes 可以和它们叠加。统一到一个 `activePanel` 状态。

> 这不只是视觉问题：实测中 TOC 或 Notes 打开后，点击 `#reader-search-toggle` 会**超时失败**——遮罩吃掉了工具栏点击，用户必须先手动关闭当前面板。属于功能性阻断。

**面板布局模式**：`≥1280px` 面板为推挤布局（正文栏同步收窄并保持居中），`<1280px` 为覆盖式。现状在所有宽度下都是覆盖，桌面端打开目录即完全看不见正文。

**焦点管理**：面板打开时焦点移入、`Esc` 关闭并归还焦点、面板内 Tab 循环。现有 `toolbar.js` 的 `resetFocusAfterClose()` 只做了 blur，没有归还——键盘用户关闭面板后焦点掉到 body。

**翻页热区**：`.nav-zone-left/right` 在 `≥1024px` 保留，`<1024px` **必须禁用**（D4——会吞掉选词，而选词是标注入口）。

**章节导航**：`Previous` / `Section N of M` / `Next` 与页内翻页热区语义不同（前者跳 spine，后者翻页）。视觉上必须区分，并在 `.nav-indicator` 旁同时显示页内进度。

**标注工具条**：7 个动作（Copy / Marker / Wavy / Underline / Delete / Add Note / Ask AI）+ 4 个颜色。文案改中文（§0）；颜色按钮补 `aria-pressed`；`Delete` 与其余动作之间加分隔，避免误触。

### 6.4 降级状态（S1–S5）

技术栈迁移引入了五条降级路径，**现状 UI 与原型里一个都没有**——原型只做了 collection 级别的 `stale`，书籍级与全局级全缺。没有 UI 就等于静默失败。

| # | 状态 | 触发 | UI 规格 | 落在哪一页 |
|---|---|---|---|---|
| **S1** | 标注 stale | `notes.json` 的指纹 ≠ 当前 spine 指纹 | 阅读器顶部横幅 + Notes 面板逐条标记。文案必须明说「标注暂停套用，**未删除**」，并给一个「查看原文摘录」入口 | 阅读器（§6.3） |
| **S2** | 索引 stale | chroma 指纹不匹配 | 书卡第**五**态（`STATUS_META` 现在只有四态）+ 搜索面板顶部「索引已过期，结果可能不全」提示条与重建按钮 | 书库（§6.2）＋ 搜索面板 |
| **S3** | pickle 回退告警 | `READER3_ALLOW_PICKLE=1` 启动 | 全局告警条（书库与阅读器都显示），点击展开未迁移书目清单 | 全局 chrome |
| **S4** | 存储格式 / 迁移进度 | `--migrate` / `--migrate-all` | 每本书卡上的 `storage_format` 角标；迁移中显示进度与失败项，失败项可单独重试 | 书库（§6.2） |
| **S5** | 多标签页写冲突 | notes 并发覆盖（乐观并发失败） | 冲突提示 + 「保留我的 / 采用远端」二选一，**不得静默丢写**。这是唯一一条会真正丢用户数据的降级 | 阅读器（§6.3） |

设计要求（五条通用）：

1. **色彩语义**：S1/S2/S4 用 `--r3-warning`，S3/S5 用 `--r3-error`；底色用同名 `-subtle`，边框用前景色本身（§3.3 已验 ≥4.5:1，不另设 border token）。**只有底色的横幅不算数**——淡底与页面底只差 1.1–1.3:1，必须同时有边框或图标。一律不用 `--r3-accent`（品牌蓝），避免与普通提示混淆。
2. **可访问性**：横幅与提示条挂 `role="status"` + `aria-live="polite"`；S5 的冲突对话框用 `role="alertdialog"`，因为它需要用户决策。
3. **可关闭性**：S1/S2/S3/S4 允许本次会话内关闭（`sessionStorage`），**S5 不可关闭**——必须做出选择。
4. **testid**：五个状态各自的容器与主操作按钮都要有 testid（§4），否则 E2E 无法断言"降级可见"。
5. **朴素优先**：Phase 3 的退出门槛只要求 S1–S4 **可见**，哪怕是先落到现有 Jinja 模板的朴素横幅；Phase 4 再按本节重做。

---

## 7. 响应式

现状全站 9 条 `@media`，等同桌面专用（D4）。三档：

| 断点 | 书库 | 阅读器 |
|---|---|---|
| `≥1280px` 桌面 | 三栏全展开 | 正文居中，面板为侧栏推挤布局 |
| `768–1279px` 平板 | 右栏折叠为抽屉（已有 `#right-collapse-toggle`），左栏保留 | 面板改为覆盖式抽屉；**翻页热区禁用** |
| `<768px` 移动 | 单栏，左栏与右栏均为抽屉，书卡网格降为 2 列 | 工具栏移到底部；面板全屏；热区禁用 |

规则：布局用 Grid/Flex + `min-width:0`，尺寸用相对单位；表格与代码块自带 `overflow-x:auto`；`body` 任何断点下都不得横向滚动。

**390×844 实测已确认的四处失效**（截图见 §0 的现状证据链接）：

| 现象 | 证据 | 后果 |
|---|---|---|
| 书库右栏定位在视口之外且无法召回 | `.library-right` 实测 `x=390, width=249`；`#right-collapse-toggle` 点击后位置不变 | Dashboard / Chat / Search **移动端完全不可用**。搜索确实执行了（496 结果）但结果面板看不见 |
| 书库左栏不渲染，且创建集合的入口在其中 | `#collections-create` 位于隐藏侧栏 | 移动端**无法创建/切换集合** |
| AI 面板在 390px 下仍是桌面双栏 | History 列固定约 140px，`Background` 按钮被裁出视口，头部按钮折两行 | 面板不可用 |
| 设置页 ollama 行 `Enabled` 文字溢出卡片 | `settings.css` 零 `@media` | 视觉破损 |

这四条把 D4 从"响应式不完善"升级为"**移动端存在功能性不可达**"——不是 polish，是缺失。三档断点必须以"每个功能在每档下都可达"为验收标准，而不只是"不横向滚动"。

---

## 8. 可访问性契约

1. 焦点可见：所有可交互元素 `:focus-visible` 显示 `--r3-focus-ring` 2px 轮廓。现状多处 `outline:none` 无替代。
2. 对比度：正文 ≥ 4.5:1，大字 ≥ 3:1，**四个阅读主题各自验证**（sepia 与 green 底色最容易不达标）。§3.3 的四组状态色同标准，**亮色档最容易漏**——原先的 500 档在白底上只有 2.15–3.76:1，已按实测换成 700 档。
3. 键盘可达：§6.3 的 `.theme-option` / `.font-option` 现在是裸 `<div>`，完全不可聚焦——必须改 `role="radio"` + `tabindex`。
4. 动态区域：搜索结果、AI 流式输出、索引进度用 `aria-live="polite"`（`#aria-live` 已存在，扩大使用）。
5. 尊重 `prefers-reduced-motion`：面板动效降级为瞬时。
6. 图标按钮一律有 `aria-label`（现状 reader 工具栏用 `title`，屏幕阅读器支持不可靠）。

---

## 9. 本规格各节落在哪个阶段

阶段划分与分支编号的权威在 `20260816-plan-ui-migration-sequencing.md` §9；本表只说明**本规格的产出**被哪个阶段消费。

| 本规格产出 | 消费阶段 |
|---|---|
| §4 `data-testid` 契约 | **Phase 0**（必须早于 Phase 1b 写 E2E，否则返工） |
| §3 token 体系 | Phase 4A.1（全站一次到位，`data-theme` 基础设施同批） |
| §6.1 设置页 | Phase 4A.2 —— 它是 Vite/TS 工具链的**试点**，属于 Phase 4A 内部，**不独立于 Phase 4** |
| §6.2 书库页 | Phase 4A.4（CSS 提取即本次重设计，不做两遍） |
| §6.0 iframe 边界 | 约束 Phase 4B.1 / 4B.2 的改动范围 |
| §6.3 阅读器外壳 | Phase 4B.2 |
| §6.3 阅读设置面板（D1）＋ 正文栏宽（D5） | Phase 4B.3 |
| §6.4 S1 / S5 | S1 → Phase 4B.2；S5 → Phase 2a（与 notes 乐观并发同批） |
| §6.4 S2 / S3 / S4 | Phase 4A.4；Phase 3 退出门槛要求它们**先以朴素形态可见** |
| §7 响应式（D4） | 随各页垂直切片一同落地，不单独成阶段 |
| §8 可访问性 | 同上，每页切片的验收项 |

---

## 10. 明确不做

- ❌ 引入 React/Vue/Svelte（与 migration plan 一致）
- ❌ 触碰 epub.js iframe 内部 DOM（§6.0）
- ❌ 打包商业中文字体（授权 + 体积）
- ❌ 重新设计 `library_classic.html`（删除）
- ❌ 移动端手势（滑动翻页、长按菜单）——本轮只保证不破坏，不新增
- ❌ 完整 i18n 框架——只做一份类型化消息表（与 plan Phase 4 一致）
