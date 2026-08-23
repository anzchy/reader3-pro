# Reader3 Pro 前端设计规格

- **日期**: 2026-08-15（2026-08-16 修订）
- **修订**: 2026-08-20 —— 补 §3.5 层级（z-index）与动效 token、§3.4 控件尺寸档（含 rail / header / 搜索命中底色三个悬空值）、§5 与 §11 的 `Modal` 选型裁决
- **修订**: 2026-08-23 —— §0 语言改判为 `zh-CN` 唯一交付语言（推翻 2026-08-16 的「en 为主」，§6.1 删掉界面语言控件、§10 同步）；§6.3 的存储 key 证据由「唯一一个」更正为实测 9 个 key 全表（R5 结论不变）
- **状态**: 已批准
- **范围**: `settings.html` / `library.html` / `reader.html` **外壳**三页

> ### 权威范围
>
> **本文权威**：双层 token 体系（§3）、`data-testid` 命名（§4）、组件清单与 `Button` 变体集（§5 / §5.1）、逐页规格（§6）、**iframe 边界与其例外（§6.0）**、降级状态设计（§6.4）、响应式断点（§7）、可访问性契约（§8）、**原型冲突裁决（§11）**。
>
> **本文不权威**：实施顺序、阶段划分、分支编号、技术栈选型与后端架构 —— 见 [`plan-tech-stack-migration.md`](../20260816-tech-stack-migration/plan-tech-stack-migration.md)。原型 → 生产的翻译规则 —— 见 [`designs/reader-pro-next/README.md`](../../../designs/reader-pro-next/README.md)。
>
> 要改上面任何一项，改它的权威文档，不要在这里加一份副本。
- **参考**: `designs/reader-pro-next/spec/reader-pro-spec.md`（现状实现审计，**设计风格基准**）、`docs/design-reference/feeddock-frontend-spec.md`（结构模板）、`lightwhale-website-analysis/`（视觉方向）
- **现状证据**: [`designs/reader-pro-next/spec/screenshots/`](../../../designs/reader-pro-next/spec/screenshots/) —— 11 个界面 × 桌面/移动双视口共 22 张实测截图（2026-08-15），对应 spec §14；由此新增的缺陷见 §1.5（D5–D7）与 spec §14.1（G-10–G-17）

---

## 0. 语言（2026-08-23 改判）

> **本节是「界面文案用哪种语言」这一事实在全仓库的唯一定义处。** 其余文档一律链接到这里，不重述结论、也不重述理由——包括 [`designs/reader-pro-next/spec/reader-pro-spec.md`](../../../designs/reader-pro-next/spec/reader-pro-spec.md) §0.3 的 D-2，它已就地标注为被推翻并指回本节。
>
> 引用方向此前是**反过来**的：本节援引 designs 那边的 D-2 作为定义处。本次一并调转，理由是语言直接决定 §5 的组件文案与 §6 的逐页规格，属于本文的权威范围（见开头「权威范围」），而 designs 那份是**现状快照 ＋ 早期产品答复**，不是目标形态的权威。

**`zh-CN` 是唯一交付语言。** 所有面向用户的界面文案一律中文，模板 `<html lang="zh-CN">`。不存在第二个 locale，也不提供语言切换入口（§6.1 因此删掉「界面语言」控件）。

### 被推翻的旧结论（2026-08-16）

原文摘要：「**en 为主语言，zh-CN 为次**」。当时的理由是 `library.html` 与 `annotation-toolbar` 本就是英文、原型已按英文全量落地；落地方式为「第 5 节文案以英文为准；Phase 4A 建立类型化消息表，`en` 为默认 locale，`zh-CN` 后补」；权威指向 `designs/reader-pro-next/spec/reader-pro-spec.md` §0.3 的 D-2。**该结论于 2026-08-23 由仓库所有者推翻。**

推翻理由：

1. **旧理由问的是「现状里哪一半更多」，而不是「交付给谁」。** 现状本来就是混排——designs spec §14.1 的 G-16 实测记录：工具栏 `aria-label` 是英文（`Table of Contents` / `Notes`），字号面板与 Notes 页脚是中文（`放大字号` / `点评此书`），Settings 页全英文（同 §1 的 D3）。往任何一侧收敛都要改掉另一半，「英文的更多」不构成选英文的依据。
2. **两侧的改动量不对称，且贵的那侧是英文。** 收敛到中文要改的是 settings 页与 library 工具栏——低频、且 settings 本来就要在 §6.1 重做一遍；收敛到英文要改的是 `reader.html` 里每次阅读都要碰的那批控件（"主题" / "当前字号" / "点评此书" / "复制全部笔记"）。
3. **「`zh-CN` 后补」在只有一个交付者的项目里等于永不发生**，等于长期停在 G-16 的混排状态。
4. **旧结论已经在本规格内部制造了矛盾**：§6.3 的标注工具条写「文案改中文（§0）」，援引 §0 却说的是 §0 的反面。改判后这句与本节一致。

副作用：D-2 曾以「`html lang="en"` 由此成为准确标记」为由关闭 designs spec §13 的语言标记问题。该问题**重新打开**，并以本节的 `<html lang="zh-CN">` 收口。

### 消息表保留，语言能力没有被砍

§10「明确不做」里的「不做完整 i18n 框架，只做一份类型化消息表」**仍然成立**。文案集中在一份类型化消息表里，只是这张表当前只有 `zh-CN` 一个 locale。将来要加 `en`，是**往表里加一列数据**，不是重构——所以本次删掉的是「语言选择器」这一个空操作控件，不是多语言的落地能力。

---

## 1. 现状审计：四个必须先决策的缺陷

设计之前必须先拍板的，不是配色，是这四件事。

### D1 🔴 阅读设置面板 12 个控件里 8 个是纯装饰（含全部 4 个主题）

> ⚠️ **本节于 2026-08-23 按实测重写。原文写的是「纯装饰，零功能……面板内 12 个控件没有任何一个被绑定，字号显示恒为 `17`，间距恒为 `1.9`」——那三句都是错的。**
> 错因值得记下来：原文的证据是「全仓库 `grep` 确认」，但实际只查了 `toolbar.js`。**接线代码在 `templates/reader.html` 尾部一段独立的内联 IIFE 里**（以 `STORAGE_KEY = 'reader3-font-settings'` 开头），而重写时这段会随模板一起没掉——`reader3-font-settings` 的迁移归属见 §6.3 存储键表的注（WI-18）。**要清理的东西，恰好也是最容易在盘点时漏掉的东西。**
>
> 顺带纠一句本规格别处可能被误读的话：**「消灭内联脚本」不是一条无差别禁令**。§3.3「两个 key、两个属性、一段 inline script」明确要求保留**恰好一段** `<head>` 内的同步 inline script（FOUC stamp），因为它必须早于首屏绘制、等不了 `defer`。该消灭的是这类**接线逻辑**藏在模板尾部的写法，不是 inline script 这个形式本身。

`reader.html` 的 `#font-settings-popup` 面板包含 12 个控件，**8 个未接线、4 个可用**：

| 控件 | DOM | 处理器 | 实测 |
|---|---|---|---|
| 主题 ×4（白色/黄色/护眼/夜间） | `.theme-option` 裸 `<div>`，带 `data-testid`，无 id | **无** | ❌ 全仓库 `static/` ＋ `templates/` 零 listener。`.is-active` 硬写在第一项上，点击不动 |
| 字体 ×4（系统/得到今楷/汉仪旗黑/思源宋体） | `.font-option` 裸 `<div>`，带 `data-testid` | **无** | ❌ 同上 |
| 字号 ± | `#font-size-increase` / `#font-size-decrease` | **有** | ✅ `click` listener ＋ 边界 `disabled` ＋ 显示值 `textContent` 更新 ＋ 落 `localStorage` ＋ 经 `Reader3Epub.applyThemeSettings()` 注入 iframe |
| 段落间距 ± | `#line-height-increase` / `#line-height-decrease` | **有** | ✅ 同上，步长 0.1（`Math.round(x*10)/10` 消浮点误差） |

`toolbar.js` 只负责这个面板的**开/关**（`RightToolbar` 的 outside-click `ignoreSelectors` 与 `#reader-font-toggle` 绑定），面板内控件一个都不归它——这一句原文是对的。

> **结论方向不变，理由要换。** 面板不是「零功能」，但**阅读主题四选一完全不可点**，而它是这个面板里最要紧的一个控件（纸色决定整屏观感）。四款字体同理。**8 / 12 不可用，且不可用的那 8 个恰好是有视觉后果的那 8 个**——用户点了没反应，比控件不存在更糟。
>
> **对 §6.3 与 WI-18 的直接后果：那不是从零实现，是带迁移义务的重写。** 已经工作的两个控件有既有持久化格式——`localStorage["reader3-font-settings"]` 存的是 `{fontSize, lineHeight}` 一个 JSON 对象，且 `static/js/epub-renderer.js` 的 `getFontSettings()` 会读它。重写时**必须迁移老用户已保存的值**，不能直接换 key 了事（迁移归属见 §6.3 的存储 key 表）。

> ✅ **本节此前记的那处「行距值域未裁差异」已于 2026-08-23 收口。** 规格那一处是无出处的笔误（`git log -S` 全历史查不到任何「改成该值」的提交，初版即如此且不带理由句，`designs/` 全域也无第二出处），已就地改成与生产、原型一致的值。**值域、步长、默认值的唯一定义处是 §6.3 的控件表，本节不复述数值**；裁法与依据见 §2.1.4 C5。
>
> 错因留一句，因为它与上面那段是同一种病：**规格初版的那张表是凭印象写的，不是逐项核过代码的**——同一版里存储 key 还写成 `reader3_line_height`（下划线），是后来 §11-R5 判掉的第三套命名。盘点表比盘点代码更容易「看起来核过了」。

**决策**：本规格把阅读设置定义为**功能规格**（§6.3）。它的「纸色」与 §3 的界面明暗是**两根独立的轴**（`data-reading-theme` 与 `data-theme`，裁决见 §11-R7），不是一个契约。字体 ×4 中的三款中文商业字体（得到今楷/汉仪旗黑/思源宋体）**未授权且未打包，删掉**，只保留 系统黑体 / 思源宋体（可 self-host 的开源字体）二选一。

### D2 🔴 暗色模式在全站不存在

`grep "prefers-color-scheme|data-theme"` 在 `*.css` 全仓库 **0 命中**。`dedao-theme.css` 的 `:root` 是 60 个**字面量** token（`--dedao-bg: #f5f5f5`），字面量 token 结构上无法主题化。所以"夜间"按钮即使接上也没有可切的东西。

**决策**：§3 引入双层 token（palette → semantic），暗色模式只重定义 semantic 层。

### D3 🟠 `settings.html` 完全在设计系统之外

76 行、独立 `settings.css`（189 行）、不引 `dedao-theme.css`、全英文、无返回按钮以外的导航。是全站唯一没有品牌一致性的页面。

**决策**：作为 §3 token 体系的**试点页**先落地——风险最低，且能在铺开到 library 之前验证整套 token。

### D4 🟠 响应式基本不存在

全站 9 条 `@media`（reader 3 / dedao-theme 2 / library 2 / search 1 / library 1），`settings.css` 与 `css/` 下 5 个文件 **0 条**。`reader.html` 的 `.nav-zone-left/right` 是覆盖左右两侧的点击翻页热区——在触屏上会直接吞掉滚动和选词，而选词是标注功能的入口。

**决策**：§7 定义三档断点（`1280` / `768`）。`nav-zone` 隐形热区**整体删除**、改显式翻页按钮——用视口宽度判断触屏是错的代理，见 §6.3 与 §11-R2。

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

### 2.1 原型 `designs/reader-pro-next/` 的权威范围

原型不是效果图，也不是一份等着被移植的代码。**它是本规格的一部分**：下面「委托清单」里的事实由原型定义，本规格不复述；「保留清单」里的事实由本规格定义，原型不得另立。两张清单不重叠，任何一个事实只落在其中一张里。

这一节存在的理由很具体：在它之前，原型与规格对同一批事实各写各的、都没声明谁是权威，于是 §11 里攒下了 R1–R8 八条事后裁决。**事后裁决的成本是两边都已经按各自的版本写了半年**（R7 那条尤其明显：spec 与 plan 各按单轴/双轴模型写了半年才发现）。划清权威范围是为了让第九条冲突不再发生，而不是为了追认前八条。

#### 2.1.1 委托清单——原型是权威的事实

下表每一行都是**实际读过原型源码后列出的具体条目**，不是类别。「定义处」列写符号名或 CSS 类名，不写行号。

| # | 委托的事实 | 定义处（原型内符号 / 类名） | 本规格如何引用 | 边界 |
|---|---|---|---|---|
| **P1** | 三页外壳的 DOM 结构与 class 名 | `.library-shell` / `.sidebar-slot` / `.library-main` / `.insights-slot` / `.reader-shell` / `.reader-header` / `.reader-stage` / `.page-flow` / `.reader-rail` / `.reader-sheet` / `.chapter-nav` | §6 只写「哪个区域负责什么」，不画 DOM 树 | 结构委托，**颜色/间距/圆角不委托**（§3） |
| **P2** | 面板单开互斥的状态机 | `reader.jsx` 的 `ReaderScreen` 里的 `activePanel` ＋ `togglePanel` | §6.3「面板互斥（D6）」引用它 | 委托「一个 `activePanel` 变量」这个形态；「哪五个面板」由 §6.3 定 |
| **P3** | 分层 `Escape` 的**顺序** | `ReaderScreen` 的 Escape 处理：编辑中 → 选区工具条 → 字体弹层 → 面板 | §6.3「焦点管理」引用它 | 顺序委托；「必须归还焦点」是 §8 的要求，不委托 |
| **P4** | 焦点陷阱与焦点归还的实现手法 | `useFocusTrap`，4 个调用点：`Modal` / `Sheet` / `FontPopover` / `AnnotationToolbar` | §8 第 1 条与 §6.3「焦点管理」引用它 | **`Modal` 的容器选型不委托**——已由 §11.2 裁给原生 `<dialog>` |
| **P5** | 书库选择模式 ＋ 批量操作条 | `app.jsx` 的 `LibraryScreen` 选择态与批量条 | §6.2「工具栏」行引用它 | 全部委托 |
| **P6** | 移动抽屉 ＋ 遮罩的开合行为 | `.sidebar-slot.is-open` / `.insights-slot.is-open` / `.drawer-scrim.is-open` | §7 只定断点数值，抽屉行为引用本条 | 行为委托，**断点阈值不委托**（§7，见 §11-R1） |
| **P7** | 侧栏拖拽改宽 | `reader.jsx` 的 `Sheet` 内的 resizer，范围 320–800px | §6.3「面板布局模式」引用它 | 含 320/800 两个端点值 |
| **P8** | 搜索结果的折叠/展开条数 | `components.jsx` 的 `SearchPanel`：折叠 3 条、展开 10 条 | §6.2 右栏 Search tab 引用它 | 含这两个数字 |
| **P9** | 翻页守卫：用 ref 而非 state 判断当前页 | `reader.jsx` 的 `turn()` | §6.3「翻页热区」段引用它 | 委托的是「不能读陈旧 state」这个约束，不是 React 的写法 |
| **P10** | 三条翻页行为 | `README.md`「三条值得带进生产的行为」：连续翻页只前进一步；跨章快翻不跳两章；正向跨章落在第 1 页而非最后一页 | §6.3「章节导航」引用它 | 全部委托。这三条本规格从未写过，只在原型里存在 |
| **P11** | 空态的三段式结构 | `.empty-symbol` ＋ `.empty-title` ＋ `.empty-copy`；两个书库空态 `lib-empty`（书库为空）与 `lib-filter-empty`（筛选无结果） | §5 的 `EmptyState` 行与 §6.2「状态」行引用它 | **结构委托，文案不委托**——原型全英文，交付语言按 §0 为 `zh-CN` |
| **P12** | 阅读器致命错误屏 | `reader.jsx` 的 `rd-error`（EPUB 缺失） | §6.3 引用它 | 同 P11：结构委托，文案不委托 |
| **P13** | 行内状态行的四种用法 | `.state-line`（中性，2 处）/ `.state-line.is-error`（2 处）/ `.state-line.is-ok`（1 处） | §5 与 §6.1「状态」行引用它 | 委托「行内、不打断布局」这个形态。**`is-ok` 不等于 Toast**，见 §5.3 |
| **P14** | 阅读器搜索面板的五相位 | `reader.jsx` 的 `ReaderSearchPanel`：`idle` / `loading` / `error` / `empty` / `done` | §6.3 引用它 | 五个相位名与各自的可见形态都委托 |
| **P15** | 书卡与书表的字段集 | `BookCard` / `BookTable` / `CoverImage` / `StatusPill` | §6.2「书卡网格」「列表视图」两行引用它 | 字段集委托；**封面 2:3 比例与标题截断行数不委托**（§6.2 已定，见 C6） |
| **P16** | `data-testid` 的**取值集合** | 五页 JSX 内 169 个 `data-testid` 站点、**221 个唯一名**（前缀分布：`lib-` 83、`rd-` 104、`set-` 34）；集中定义处 `SHARED_TESTIDS` / `LIB_BOOK_STATUS_TESTID` 及 `reader.jsx` 的五张 `*_TESTID` 字面量表 | §4 引用它 | **命名规则与正则不委托**（§4 ＋ 迁移计划 §6 step 0.5）。委托的是「哪些元素需要 testid、各自叫什么」 |
| **P17** | 可访问性的**实现手法** | `Toggle` 的 `role="switch"`；书卡的 `role="button"` ＋ 键盘激活；rail 按钮的 `aria-pressed`；`.page-arrow` 的 `aria-label` | §8 引用它 | §8 定**标准**，原型定**做法**。标准与做法冲突时按 §2.1.3 规则 1 |

> **委托不等于照抄。** 上表每一行委托的都是**目标形态里仍然成立的那一部分**。原型里同一个文件的其余部分（颜色、字号、时长、图标、文案）落在保留清单里，翻译时必须按 §3–§8 替换。判断某处属于哪一类，用 §2.1.3 的规则，不用直觉。

#### 2.1.2 保留清单——本规格独有，原型不得定义

| # | 事实 | 唯一定义处 | 原型现状（说明它为什么不是权威） |
|---|---|---|---|
| **S1** | 双层 token 结构与全部取值 | §3.1 / §3.2 / §3.3 | 原型自有一套 `--surface` / `--border` / `--radius-*` 命名，与 Tier 2 不同名也不同值 |
| **S2** | z-index 九档与完整偏序 | §3.5.1 | 原型 13 处、10 个不同值，全部待 snap；逐值映射表归 [前端计划](./plan-frontend-ui-refactor.md) WI-10 §10.1.1 |
| **S3** | 三档时长 ＋ 三条缓动 | §3.5.2 | 原型 9 条 `transition` 用 4 个时长值（120/140/180/240ms），全部不在三档内；另有 1 个非标缓动 |
| **S4** | `prefers-reduced-motion` 的落地形式 | §3.5.3 | 原型用全局 `0.01ms !important` 覆盖，且它的两条无限动画在这种写法下**并没有停**（见 C11） |
| **S5** | 响应式断点数值 | §7 | 已由 §11-R1 裁决，原型已改为 1279/767 |
| **S6** | `data-testid` 命名规则与正则 | §4 ＋ [迁移计划](../20260816-tech-stack-migration/plan-tech-stack-migration.md) §6 step 0.5 | 原型 2026-08-23 改名前 138 个站点 **0 个合规** |
| **S7** | 降级状态 DEG-S1–DEG-S5 | §6.4 | 原型只有 collection 级的 `.stale-dot` 一处，书籍级与全局级全缺 |
| **S8** | 可访问性六条契约 | §8 | 见 S6 与 P17 的边界 |
| **S9** | `Modal` 选型 | §11.2 | 原型仍是 `div.overlay` ＋ `role="dialog"`，三条关闭路径 |
| **S10** | 交付语言 | §0 | 原型 UI 文案全英文 |
| **S11** | 两根主题轴、挂载点、存储 key 命名 | §3.3 ＋ §6.3 ＋ §11.1 ＋ §11-R5 | 原型把「跟随」藏进 `paper`，纸色挂 `.reader-shell`，key 写 `r3-theme` |
| **S12** | 阅读设置的值域与默认值 | §6.3 | 原型 4 种字体、行距步长 0.05、默认 18/1.85，与 §6.3 不同（C4 / C5）。**行距值域两边现已一致**——那是 C5 把规格改对的结果，不是原型取得了权威：唯一定义处仍是 §6.3 |
| **S13** | 图标形态（SVG） | §6.2 ＋ §6.3 | 原型 `<svg>` **0 命中**，图标全部是 emoji 与文字符号 |
| **S14** | `Skeleton` 与 `Toast` 的解剖 | §5.2 / §5.3（本轮新增） | 原型 `skeleton` / `toast` 各 **0 命中**。**这两处不许拿原型当参考**——它没有可参考的东西 |

> 保留清单的判据只有一条：**跨页或跨组件的事实归规格**。token、层级、动效、命名、语言、可访问性标准都是「改一处、全站变」的量，它们必须有一个定义处；单页或单组件的结构与交互不是，它们可以由最接近实现的那份文档定义，而原型就是那份文档。

#### 2.1.3 判决规则（可执行）

遇到原型与本规格不一致时，按顺序执行：

1. **事实在保留清单（§2.1.2）里 → 规格赢。** 原型就地改，裁决记入 §11，规格一个字不动。
2. **事实在委托清单（§2.1.1）里 → 原型赢。** 规格删掉复述，改写成「见原型的 `<符号名>`」。
3. **两张清单都没有 → 这是清单缺陷，不是冲突。** 先按 §2.1.2 末尾那条判据归类：跨页/跨组件的（token、层级、命名、可访问性标准、语言）补进保留清单；单页/单组件的结构与交互补进委托清单。**归类完成后回到第 1 或第 2 条**，不允许绕过归类直接裁。
4. **事实落在 [前端计划](./plan-frontend-ui-refactor.md) §1.2 的三条不可移植项里 → 两边都不是权威，生产代码是权威。** 原型此处只作行为参考。三条见下方硬约束二。
5. **每条裁决必须同时落成三处**：§11 加一行、输的一方就地改、赢的一方删掉重复表述。**不允许「两边都留着，注明以某某为准」**——那不是裁决，那是第二份定义，而第二份定义就是 R1–R8 的成因。

**硬约束一：截图不是验收基准。**

`designs/reader-pro-next/spec/screenshots/` 下有 **22 张 PNG**，是 11 个界面 × 1440×900 与 390×844 两档视口，采集于 2026-08-15。它们拍的是**当时的生产 UI**，不是原型，更不是目标形态——`reader-pro-spec.md` 开篇即声明「描述 2026-08-15 仓库中的实际前端实现……不是重设计提案」。

三条实测事实说明它们为什么不能当基准：

- 22 行说明里有 **9 行**自带 ⚠️ 缺陷标注，且这 9 行正是 §1 的 D4–D7 与 §7「390×844 实测已确认的四处失效」的证据来源。
- 其中 **2 张**（`11-library-classic-desktop.png` / `11-library-classic-mobile.png`）拍的是经典书库，而 §2 已判定它**删除、不设计**。
- `06-reader-desktop.png` 的说明写「正文占满 1440px，单行约 180 字符」——这正是 D5 要修掉的东西。

因此：**任何验收条目不得写「与截图一致」或「对照截图核对」。** 截图的用途只有一个——作为 §1 缺陷清单与 §7 失效清单的证据留档。一个通过了本规格验收的界面，**必然**与这 22 张截图不一致；写「与截图一致」等于把验收标准倒过来指向缺陷。

**硬约束二：三条不可移植项排除在委托之外。**

[前端计划](./plan-frontend-ui-refactor.md) §1.2 列出三条，本节把它们从委托清单里显式排除：

| 不可移植项 | 原型的做法 | 为什么不委托 | 原型还剩什么用 |
|---|---|---|---|
| **分页** | CSS 多列 ＋ `translateX` 位移，`usePagination` | 生产走 epub.js `flow: paginated`，分页发生在 iframe **内部**，宿主页拿不到列宽与页数。照搬会撞上 §6.0 的 iframe 边界 | `usePagination` 只作**行为参考**：P9 的翻页守卫与 P10 的三条翻页行为从它身上提取，实现另写 |
| **标注锚定** | `{paragraph, start, end}` 三元组，UTF-16 偏移 | 生产用 CFI ＋ `quote`/`prefix`/`suffix`。**永远不要**用原型的偏移方案替换现有锚定——已存标注会全部失锚，且这是 §6.0 判据 C（CFI 往返）要防的那种失败 | 只剩一条**反向**可借鉴：分段渲染（`segmentParagraph`）优于 `Range.surroundContents()`，见 README |
| **数据流与加载态** | 每个面板都缺 loading / error / empty；**加载骨架从来没做过** | 没有可委托的东西。`Skeleton` 与 `Toast` 在原型里 **0 命中** | 无。这两个组件的解剖见 §5.2 / §5.3，**不参照原型** |

#### 2.1.4 2026-08-23 实测发现的冲突与逐条裁决

下表每条都经过实测。「需同步改的位置」列只标位置，改动本身归各文档的负责人。

| # | 事实 | 原型 | 规格 / 计划 | 裁决 | 依据 | 需同步改的位置 |
|---|---|---|---|---|---|---|
| **C1** | 阅读器工具栏按钮数与返回键位置 | rail 4 个（目录/搜索/笔记/AI）＋ `Aa` 字体按钮；返回在页头（`rd-header-back`） | §6.3「保留 6 个 SVG 按钮（返回/目录/搜索/AI/字体/笔记）」 | **原型赢** | §6.3 同一句要求「当前激活面板的按钮需要选中态」。返回**没有激活态**——它是导航，按下即离开本页。把它混进一组带 `aria-pressed` 的按钮里，要么它得假装有 `aria-pressed="false"`（撒谎），要么这组按钮的 ARIA 就不齐（半套）。原型把返回放进页头正是绕开了这个 | §6.3「右侧工具栏」段 |
| **C2** | 图标形态 | `<svg>` **0 命中**，全部 emoji 与文字符号（`≡` `⌕` `✎` `☀` `☾` `◐` `📚`） | §6.2 要求「换 SVG，与 reader 的 SVG 图标风格统一」 | **规格赢**（S13） | emoji 的字形随平台变、不能继承 `currentColor`、在 `aria-hidden` 之外还会被部分屏幕阅读器读成表情名 | §6.2 那句的**理由**要改：「与 reader 的 SVG 风格统一」——统一的对象是**生产**的 reader 工具栏，不是原型；原型这边一个 SVG 都没有 |
| **C3** | 标注工具条颜色按钮的选中态 | 颜色点只有 `aria-label`，无 `aria-pressed` | §6.3 要求「颜色按钮补 `aria-pressed`」 | **规格赢**（S8） | 四个颜色是互斥选择，没有选中态时键盘用户听不出当前色 | 原型 `AnnotationToolbar` |
| **C4** | 阅读字体档数 | `READING_FONTS` **4 项** | §6.3「`system` / `serif` 二选一」 | **规格赢**（S12） | §6.3 已写明删除得到今楷 / 汉仪旗黑 / 思源宋体三项商业字体（未授权、未打包、点了没反应）。原型的 4 档是那三项的残留形态 | 原型 `READING_FONTS` |
| **C5** | 行距值域与步长 | `min=1.5 max=2.5 step=0.05` | §6.3 原写「1.4–2.4，步长 0.1」 | **拆两半（2026-08-23 复裁）：步长规格赢（0.1）；值域改规格为 1.5–2.5** | 依据仍是 §11.1 末尾那条原则（「改默认值会让老用户的阅读版式无故位移」），但**本条初裁把它用反了**：初裁写「1.4 与 2.4 在 1.5–2.5 里不可达」，那是用结论证明前提——该问的是**已存的值在新值域里可不可达**。生产能存下的只有 1.5 / 1.6 / … / 2.5 这 11 个值：取 1.5–2.5 则零钳位、零位移；取 1.4–2.4 则 2.5 越界须钳到 2.4，位移的恰是把行距调到最大的用户，而 1.4 一档**零存量**。另有一层佐证：`git log -S` 全历史查不到任何「改成 1.4–2.4」的提交，规格初版即如此且不带理由句，`designs/` 全域无第二出处——是笔误，不是设计变更。步长维持 0.1（生产与规格本就一致，原型的 0.05 是孤例；且 0.1 是 0.05 的整数倍，生产存的 11 个值在原型滑杆上全部可选中，步长之争不影响迁移） | §6.3 控件表 ＋ §1 D1 的注（两处已改）＋ 原型 `FontPopover` 的 `step`（**未改，属原型侧**）＋ 计划 `WI-18`（逐列副本已删）与 §5.1.2 新增用例 `FB-R13a` |
| **C6** | 书卡标题截断 | `.book-title` 无 `line-clamp`（**0 命中**），只设了 `font-size: 14px; line-height: 1.35` | §6.2「标题 2 行截断，作者 1 行」 | **规格赢** | §6.2 同一行还要求中栏 `min-width: 0`，两条是同一个失败模式的两半（长书名撑破网格）。只加 `min-width:0` 而不截断，长标题会把卡片撑高、网格行高参差 | 原型 `.book-title` |
| **C7** | 设置页分区 | 四块：`AI providers` / `Retrieval` / `Data` / `Export`，**没有外观分区** | §6.1 四段：AI 偏好 / 服务商 / 外观 / 数据 | **规格赢** | 不只是译名差异，是结构差异：§11-R7 裁定两根主题轴之后，chrome 明暗的控件**必须**有个家，§6.1 把它放在「外观」；原型没有这一段，等于双轴裁决在原型里没有落点。`Export` 在 §6.1 里并进「数据」 | 原型 `settings.jsx` 的四个分区 |
| **C8** | 书卡状态 testid 前缀 | `LIB_BOOK_STATUS_TESTID` 生成 `lib-book-status-*` | [前端计划](./plan-frontend-ui-refactor.md) WI-3 与 §5.5 矩阵 FG-07 / FG-08 写 `lib-status-*` | **原型赢**（P16） | testid 取值集合已委托给原型。且 `book-status` 比 `status` 更能与索引任务状态、连接状态区分——`lib-status-*` 在同一个页面上会有第二个消费者 | 计划 WI-3 与 §5.5 矩阵的 FG-07 / FG-08 两行 |
| **C9** | `StatusPill` 的未知状态兜底 | `STATUS_META[status] \|\| STATUS_META.not_indexed` | 规格未写 | **不委托**（清单缺陷，按规则 3 归入保留清单） | 这是 bug 不是设计：DEG-S2 引入书卡**第五态**之后，未知状态会被静默显示成「未索引」——一个正常态。降级状态的全部价值就是让失败可见，用一个正常态兜底等于把 DEG-S2 关掉 | 原型 `StatusPill`；§6.2「书卡网格」行补一句「未知状态必须显式渲染，不得回落到任何已知态」 |
| **C10** | `Modal` 容器 | `div.overlay` ＋ `<section role="dialog" aria-modal="true">`，三条关闭路径 | §11.2 原生 `<dialog>` ＋ `showModal()` | **规格赢**（S9，已裁未落） | 理由完整见 §11.2 | 原型 `components.jsx` 的 `Modal` |
| **C11** | `prefers-reduced-motion` 实现 | 全局块用 `0.01ms !important` 覆盖 `animation-duration` 与 `transition-duration` | §3.5.3 单点重定义三个 token ＋ 例外清单（条数以该节为准，本行不复述） | **规格赢**（S4） | 原型那种写法对它自己的两条无限动画**无效**：`spin 700ms linear infinite` 与 `blink 1s infinite` 被压到 `0.01ms` 之后不是停下，是**转得更快**（周期变短、循环不变）。这正是 §3.5.3 例外 1 说的「置 0 不等于关掉」，必须 `animation: none` ＋ 静态形态 | 原型的 `@media (prefers-reduced-motion: reduce)` 块 |
| **C12** | 降级信息的播报方式 | 全文件 `aria-live` **仅 1 处**，在 sr-only 的 `LiveRegion` 里 | [前端计划](./plan-frontend-ui-refactor.md) WI-1：横幅自带 `role="status"` ＋ `aria-live="polite"`，**不许复用 `LiveRegion`** | **计划赢**（S7 / S8） | sr-only 的播报器只能播报、不能当可见横幅用。§6.4 要求的是「看得见 ＋ 听得见」，复用 `LiveRegion` 只满足后一半 | 无（原型没有降级横幅，不存在要改的东西） |
| **C13** | 22 张截图里有 2 张拍的是已判删除的经典书库 | — | §2 表：`library_classic.html` **删除，不设计** | **§2 不变，截图归档保留** | 截图是现状证据，证据不因目标形态删掉某页而失效。但它反过来证明了硬约束一：一份现状证据里有 2/22 拍的是不存在于目标形态的页面 | 无 |

> **C1、C8 是本批唯二判给原型的。** 其余 11 条全判给规格或计划，原因不是规格更权威，而是这 11 条**全部落在保留清单里**——它们跨页、跨组件，或者属于可访问性与语言。这个分布本身说明 §2.1.1 / §2.1.2 的切分是有效的：真正需要逐条裁的冲突，几乎都发生在保留清单的边界上。

---

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
  --p-gray-500:#999999; --p-gray-550:#707070; --p-gray-600:#666666;
  --p-gray-700:#4a4a4a; --p-gray-800:#333333; --p-gray-900:#1f2d3d;
  --p-gray-950:#17222e;

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

  /* Annotation — 亮/暗两组，暗色下原色在深底上刺眼。
     **存 RGB 三元组，alpha 留在使用点**（裁决见 plan WI-7；本节是这一族的唯一定义处）。
     三元组是本体，`--p-hl-*` 由它派生，供不需要 alpha 的场合直接用。 */
  --p-hl-yellow-rgb:251 191 36;  --p-hl-green-rgb:74 222 128;
  --p-hl-pink-rgb:248 113 113;   --p-hl-blue-rgb:96 165 250;
  --p-hl-yellow-dk-rgb:138 109 31; --p-hl-green-dk-rgb:47 107 61;
  --p-hl-pink-dk-rgb:125 59 59;    --p-hl-blue-dk-rgb:47 85 128;
  --p-hl-yellow:rgb(var(--p-hl-yellow-rgb)); --p-hl-green:rgb(var(--p-hl-green-rgb));
  --p-hl-pink:rgb(var(--p-hl-pink-rgb));     --p-hl-blue:rgb(var(--p-hl-blue-rgb));
  --p-hl-yellow-dk:rgb(var(--p-hl-yellow-dk-rgb)); --p-hl-green-dk:rgb(var(--p-hl-green-dk-rgb));
  --p-hl-pink-dk:rgb(var(--p-hl-pink-dk-rgb));     --p-hl-blue-dk:rgb(var(--p-hl-blue-dk-rgb));
}
```

> ⚠️ 现有 `--dedao-highlight-red` 与数据模型的 `MarkerColor` 枚举（`yellow|green|pink|blue`）**对不上**——CSS 叫 red，数据叫 pink。以数据模型为准，统一为 `pink`。

### 3.3 Tier 2 — Semantic（组件唯一可用层）

**两根轴，不是一根**（裁决见 §11-R7）。界面外观与阅读画布是两个状态域，各自拥有一组 token，谁也不重定义谁：

| 轴 | 属性（都 stamp 在 `<html>`） | 取值 | 拥有的 token |
|---|---|---|---|
| **chrome** | `data-theme` | 属性缺席＝跟随系统 / `light` / `dark` | `bg`、`surface*`、`text*`、`border*`、`accent*`、`focus-ring`、四组状态色 ＋ `-subtle`、`shadow-*` |
| **reading** | `data-reading-theme` | `auto`（默认）/ `paper` / `sepia` / `green` / `night` | `page-bg`、`page-ink`、`page-quiet`、`hl-*` |

三条硬规则：

1. **两个属性都挂 `<html>`，作用域由选择器保证，不由挂载点保证。** 阅读 token 只许写成 `html[data-reading-theme="x"] .reader-shell { }`。书库页没有 `.reader-shell`，纸色天然不外溢——而 `.reader-shell` 在 FOUC 的 inline script 执行时还不存在，属性挂不上去。
2. **`auto` 之外的四种纸色是绝对值**，在 light / dark chrome 下完全相同。`auto` 是**唯一**跟随 chrome 的值，且它有名字——不许把「跟随界面」藏在 `paper` 里（原型犯的就是这个错，见 §11-R7）。
3. **`--r3-hl-*` 归 reading 轴**，因为高亮画在纸上、在 iframe 里，跟界面明暗无关。`auto` 下由 chrome 决定，所以 chrome 轴里也有一份——那是 `auto` 的取值，不是 chrome 自己的角色。

```css
/* ── 轴 1：chrome ───────────────────────────────────── */
:root {                      /* 亮色 chrome 为默认 */
  --r3-bg:            var(--p-gray-100);   /* 页面底 */
  --r3-surface:       var(--p-gray-0);     /* 卡片 */
  --r3-surface-raised:var(--p-gray-0);     /* 弹层/抽屉 */
  --r3-surface-sunken:var(--p-gray-50);    /* 输入框/代码块 */
  --r3-surface-hover: var(--p-gray-200);

  --r3-text:          var(--p-gray-800);
  --r3-text-muted:    var(--p-gray-600);
  --r3-text-subtle:   var(--p-gray-550);   /* 不是 gray-500——见下方对比度表 */
  --r3-text-disabled: var(--p-gray-400);   /* 1.47:1，WCAG 1.4.3 豁免，别"修" */
  --r3-text-on-accent:var(--p-gray-0);

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

  /* 搜索命中底色。属 chrome 轴，与 --r3-hl-* 是两个角色，见下方说明 */
  --r3-search-hit:#fde68a;

  /* reading 轴 auto 档的取值——不是 chrome 自己的角色，见上面规则 3 */
  --r3-page-bg:#ffffff; --r3-page-ink:#1f2937; --r3-page-quiet:#64748b;
  --r3-hl-yellow-rgb:var(--p-hl-yellow-rgb); --r3-hl-green-rgb:var(--p-hl-green-rgb);
  --r3-hl-pink-rgb:var(--p-hl-pink-rgb);     --r3-hl-blue-rgb:var(--p-hl-blue-rgb);
  --r3-hl-yellow:rgb(var(--r3-hl-yellow-rgb)); --r3-hl-green:rgb(var(--r3-hl-green-rgb));
  --r3-hl-pink:rgb(var(--r3-hl-pink-rgb));     --r3-hl-blue:rgb(var(--r3-hl-blue-rgb));

  --r3-shadow-sm:0 1px 3px rgb(0 0 0 / .05);
  --r3-shadow-md:0 2px 10px rgb(0 0 0 / .05);
  --r3-shadow-lg:0 4px 20px rgb(0 0 0 / .10);
}

/* dark chrome 的两个入口：显式选择、以及未显式选 light 时跟随系统。
   两块内容**必须逐字相同**——生产里用一个 CSS 自定义属性块生成两次，
   不许手抄两遍。中性色取原型实测值（偏蓝，不是中性灰） */
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { /* ↓ 同下 */ } }
:root[data-theme="dark"] {
  --r3-bg:#0b1220;             /* 原型 --canvas */
  --r3-surface:#131c2e;        /* 原型 --surface */
  --r3-surface-raised:#1c2740; --r3-surface-sunken:#182335;
  --r3-surface-hover:#182335;
  --r3-text:#e2e8f0; --r3-text-muted:#94a3b8;
  --r3-text-subtle:#7a8aa2; --r3-text-disabled:#475569;
  --r3-border:#263349; --r3-border-subtle:#1c2740; --r3-border-strong:#35476a;
  --r3-accent:var(--p-blue-400);   /* D-5 改蓝后同步；原值 #ff8534 是暖橙时代的残留 */
  --r3-accent-subtle:var(--p-blue-950);
  --r3-success:var(--p-green-400); --r3-warning:var(--p-amber-400);
  --r3-error:var(--p-red-400);     --r3-info:var(--p-cyan-400);
  --r3-success-subtle:var(--p-green-950); --r3-warning-subtle:var(--p-amber-950);
  --r3-error-subtle:var(--p-red-950);     --r3-info-subtle:var(--p-cyan-950);
  --r3-search-hit:#7c5f12;         /* 原型暗色 --highlight */
  /* auto 档在 dark chrome 下的取值 */
  --r3-page-bg:#131c2e; --r3-page-ink:#dbe3ef; --r3-page-quiet:#93a3bb;
  --r3-hl-yellow-rgb:var(--p-hl-yellow-dk-rgb); --r3-hl-green-rgb:var(--p-hl-green-dk-rgb);
  --r3-hl-pink-rgb:var(--p-hl-pink-dk-rgb);     --r3-hl-blue-rgb:var(--p-hl-blue-dk-rgb);
  --r3-hl-yellow:rgb(var(--r3-hl-yellow-rgb)); --r3-hl-green:rgb(var(--r3-hl-green-rgb));
  --r3-hl-pink:rgb(var(--r3-hl-pink-rgb));     --r3-hl-blue:rgb(var(--r3-hl-blue-rgb));
  --r3-shadow-sm:0 1px 3px rgb(0 0 0 / .4);
  --r3-shadow-md:0 2px 10px rgb(0 0 0 / .4);
  --r3-shadow-lg:0 4px 20px rgb(0 0 0 / .6);
}

/* ── 轴 2：reading（只作用于 .reader-shell 内） ─────────
   auto 故意没有规则——它就是「不覆盖 chrome 给的 page-* 与 hl-*」。
   别把它当漏写补上，补上就又变成一根轴了。 */
html[data-reading-theme="paper"] .reader-shell { --r3-page-bg:var(--p-gray-0);      --r3-page-ink:#1f2937; --r3-page-quiet:#64748b; }
html[data-reading-theme="sepia"] .reader-shell { --r3-page-bg:var(--p-paper-sepia); --r3-page-ink:#4a3b28; --r3-page-quiet:#7a6449; }
html[data-reading-theme="green"] .reader-shell { --r3-page-bg:var(--p-paper-green); --r3-page-ink:#24382a; --r3-page-quiet:#506856; }
html[data-reading-theme="night"] .reader-shell { --r3-page-bg:var(--p-paper-night); --r3-page-ink:#c2ccdb; --r3-page-quiet:#7e8ca3; }

/* 高亮跟纸走，不跟 chrome 走：三种亮纸用亮色高亮，夜纸用暗色高亮 */
html[data-reading-theme="paper"] .reader-shell,
html[data-reading-theme="sepia"] .reader-shell,
html[data-reading-theme="green"] .reader-shell {
  --r3-hl-yellow-rgb:var(--p-hl-yellow-rgb); --r3-hl-green-rgb:var(--p-hl-green-rgb);
  --r3-hl-pink-rgb:var(--p-hl-pink-rgb);     --r3-hl-blue-rgb:var(--p-hl-blue-rgb);
  --r3-hl-yellow:rgb(var(--r3-hl-yellow-rgb)); --r3-hl-green:rgb(var(--r3-hl-green-rgb));
  --r3-hl-pink:rgb(var(--r3-hl-pink-rgb));     --r3-hl-blue:rgb(var(--r3-hl-blue-rgb));
}
html[data-reading-theme="night"] .reader-shell {
  --r3-hl-yellow-rgb:var(--p-hl-yellow-dk-rgb); --r3-hl-green-rgb:var(--p-hl-green-dk-rgb);
  --r3-hl-pink-rgb:var(--p-hl-pink-dk-rgb);     --r3-hl-blue-rgb:var(--p-hl-blue-dk-rgb);
  --r3-hl-yellow:rgb(var(--r3-hl-yellow-rgb)); --r3-hl-green:rgb(var(--r3-hl-green-rgb));
  --r3-hl-pink:rgb(var(--r3-hl-pink-rgb));     --r3-hl-blue:rgb(var(--r3-hl-blue-rgb));
}
```

> **`--p-paper-white` 现在只有 `paper` 一档在用**（`auto` 直接吃 chrome 的 `#ffffff`）。两者同值不是巧合，是 `auto` 在亮色下**就该**长得像 `paper`——区别只在切到 dark chrome 时 `paper` 不动、`auto` 跟着走。

> **`--r3-hl-*-rgb` 与 `--r3-hl-*` 必须在四个块里各写一遍，不能只在 `:root` 派生一次。** 自定义属性的值在**声明它的那个元素上**就完成 `var()` 代换；写成 `:root { --r3-hl-yellow: rgb(var(--r3-hl-yellow-rgb)) }` 之后，`.reader-shell` 里再改 `--r3-hl-yellow-rgb` 不会反向影响已经算好的 `--r3-hl-yellow`，夜纸的高亮会静默停在亮色上。四个块（`:root`、`[data-theme=dark]`、三种亮纸、夜纸）各自成对声明，是为了避开这个代换时机。
>
> **本节 ＋ §3.2 是 `--p-hl-*-rgb` / `--r3-hl-*-rgb` 这一族的唯一定义处。** plan 的 WI-7 只引用它、不重述值——那边负责的是**九处使用点的 alpha**（.35 / .45 / .18），不负责 token 本身长什么样。
>
> **`--r3-search-hit` 不是第五个 `--r3-hl-*`，别合并。** 取原型 `--highlight`（亮 `#fde68a` / 暗 `#7c5f12`），原型里它唯一的用途就是搜索结果的 `<mark>`（`index.html:170`）。两者角色不同：
>
> | | `--r3-search-hit` | `--r3-hl-*` |
> |---|---|---|
> | 语义 | 搜索命中的**临时**底 | 用户标注的**持久**底 |
> | 生命周期 | 随查询词变化，退出搜索即消失 | 写进 `notes.json`，跨会话存在 |
> | 取值 | 一个，不分颜色 | 四个，对应 `MarkerColor` 枚举 |
> | 所属轴 | chrome（搜索命中出现在书库列表、TOC、笔记面板——都在 iframe 外） | reading（高亮画在纸上，见规则 3） |
>
> 合并的诱惑在于「亮色下 `#fde68a` 和 `--p-hl-yellow` 看着差不多」。但一旦合并，用户把标注色改成绿之后搜索命中会跟着变绿，而搜索命中在书库页也要用——那里根本没有 reading 轴。

**文字色实测对比度**（2026-08-23，WCAG 2.1 相对亮度公式；每格取**该角色在本主题下最差的底**，不是最好看的那个底）：

| 角色 | 门槛 | 亮色 chrome（最差底 `--r3-bg` `#f5f5f5`） | 暗色 chrome（最差底 `--r3-surface-sunken` `#182335`） |
|---|---|---|---|
| `--r3-text` | 4.5 | `#333333` **11.59** | `#e2e8f0` **12.80** |
| `--r3-text-muted` | 4.5 | `#666666` **5.27** | `#94a3b8` **6.15** |
| `--r3-text-subtle` | 4.5 | `#707070` **4.54** ← 原 `#999999` 只有 **2.61** | `#7a8aa2` **4.50** ← 原 `#64748b` 只有 **3.32** |
| `--r3-text-disabled` | **豁免** | `#cccccc` 1.47 | `#475569` 2.08 |

| 阅读轴角色 | 门槛 | 纸底 | ink | quiet |
|---|---|---|---|---|
| `auto` / 亮 chrome | 4.5 | `#ffffff` | `#1f2937` **14.68** | `#64748b` **4.76** |
| `auto` / 暗 chrome | 4.5 | `#131c2e` | `#dbe3ef` **13.17** | `#93a3bb` **6.65** |
| `paper` | 4.5 | `#ffffff` | `#1f2937` **14.68** | `#64748b` **4.76** |
| `sepia` | 4.5 | `#f6ecd8` | `#4a3b28` **9.20** | `#7a6449` **4.78** ← 原 `#8a7455` 只有 **3.80** |
| `green` | 4.5 | `#dcece0` | `#24382a` **10.22** | `#506856` **4.95** ← 原 `#5b7563` 只有 **4.11** |
| `night` | 4.5 | `#10151f` | `#c2ccdb` **11.27** | `#7e8ca3` **5.37** |

> **`--r3-text-disabled` 的 1.47 / 2.08 是合规的，不是缺陷。** WCAG 2.1 SC 1.4.3 明文豁免"失效（inactive）的用户界面组件"。把它调到 4.5:1 会让禁用态看起来跟可用态一样，反而破坏可达性。**任何自动对比度检查在这两个值上报出的问题都要按"已知豁免"关掉**，别顺手"修"。
>
> **门槛为什么一律写 4.5 而不是大字的 3:1。** §3.4 的字阶最大只到 `xl` 22px 常规字重——AA 的"大字"定义是 ≥18.66px **粗体** 或 ≥24px，本设计一个都够不着。所以 UI 里**没有**能吃 3:1 的文字，只有非文字元素（边框、图标、焦点环）走 1.4.11 的 3:1。
>
> **亮色下 muted 与 subtle 只差 0.73，肉眼几乎分不出——这是 4.5:1 硬门槛的必然结果，不是取值没调好。** 白底上 4.5:1 把可用的中性灰压死在 `#767676`–`#000` 这一段；原型之所以能在亮色下拉开 `--muted` `#64748b`（5.1）与 `--quiet` `#94a3b8`（2.5）的差距，纯粹是因为后者不合规。**要在亮色下表达第三层级，用字号、字重、留白，别再往上调灰度**——调不动了。暗色底反过来宽松，`6.15` vs `4.50` 是真能看出来的差。
>
> **`--p-gray-500` `#999999` 现在没有任何 `--r3-*` 角色引用它。** 保留是因为它仍是 legacy `--dedao-light` 的迁移落点。**但它 2.61:1，只能用于非文字（分隔线、装饰图形），一旦出现在 `color:` 上就是缺陷。**
>
> **删掉的 `--r3-text-quiet`。** 它曾是第六个文字色 token，全仓库 `var()` 消费者为 **0**；亮色下与 `--r3-text-subtle` 同取 `--p-gray-500`（完全同值），暗色下 `#93a3bb` 与 `--r3-text-muted` `#94a3b8` 的对比度差 **0.01**——两个主题下都是重复角色。阅读轴上"安静文字"这个角色由 `--r3-page-quiet` 承担（五个主题都有定义）。它是 §11-R7 拆两根轴之前的残留，已于 2026-08-23 删除。

**状态色实测对比度**（2026-08-16，WCAG 2.1 相对亮度公式）——这四组不是挑好看的，是挑过线的：

| 角色 | 亮色前景 / 白面 | 同前景 / 自己的淡底 | 夜间前景 / 纸夜底 |
|---|---|---|---|
| success | `#15803d` **5.02** | 4.57 | `#4ade80` **10.49** |
| warning | `#b45309` **5.02** | 4.51 | `#fbbf24` **10.95** |
| error | `#b91c1c` **6.47** | 5.30 | `#f87171` **6.61** |
| info | `#0e7490` **5.36** | 4.67 | `#22d3ee` **10.11** |

> **被换掉的 500 单档在亮色下全线不合格**：green-500 2.28、amber-500 2.15、red-500 3.76、cyan-600 3.68，全部低于 §8 要求的 4.5:1。夜间反而都过（4.86–8.51）。**这是个亮色缺陷，不是暗色缺陷**——与直觉相反，所以之前没人查。
>
> **淡底不能独自表达状态。** 只染一层底色的横幅在两个主题下都近乎看不见。**横幅必须同时有边框或图标**，边框直接用状态前景色（前景色对淡底 4.51–5.30:1，见上表第二列，够用）。

**四个 `-subtle` 底色对承载面的对比度**（2026-08-23 由本节 token 字面值重算，WCAG 2.1 相对亮度公式）。横幅可能压在页面底上，也可能压在卡片上，所以两个承载面各给一列：

| 淡底 token | 亮色取值 | 对 `--r3-bg` `#f5f5f5` | 对 `--r3-surface` `#ffffff` | 夜间取值 | 对 `--r3-bg` `#0b1220` | 对 `--r3-surface` `#131c2e` |
|---|---|---|---|---|---|---|
| `--r3-success-subtle` | `#dcfce7` | 1.01 | 1.10 | `#14321f` | 1.34 | 1.22 |
| `--r3-warning-subtle` | `#fef3c7` | 1.02 | 1.11 | `#3a2a08` | 1.35 | 1.23 |
| `--r3-error-subtle` | `#fee2e2` | 1.12 | 1.22 | `#3b1717` | 1.18 | 1.07 |
| `--r3-info-subtle` | `#e0f2fe` | 1.05 | 1.15 | `#10283d` | 1.24 | 1.13 |

> **十六个值全部落在 1.01–1.35，连非文字元素的 3:1 门槛都不到一半。** 结论对承载面的选择不敏感——**换哪个底都一样看不见**，所以「必须有边框或图标」这条硬约束不依赖于横幅最终压在什么上面。
>
> ⚠️ **本表取代了原先的两个区间值（亮 1.10–1.22、夜 1.15–1.32，记于 2026-08-16）。那两个区间按现行 token 值复算不出来：** 亮色的 1.10–1.22 只在对**白面**测时成立，而它当时的说明文字写的是「压在**页面底**上」——`--r3-bg` 亮色是 `#f5f5f5` 不是 `#ffffff`，标签与数值对不上；夜间的 1.15–1.32 对本节任何一个承载面都复算不出（最接近的 `--r3-bg` 是 1.18–1.35）。**差异不影响任何结论**（两套数都远低于 3:1），但旧数无法复现，故整体换成可复算的逐行值，并写明测量对象。

**两个 key、两个属性、一段 inline script**：

| 轴 | key | 取值 | 默认 | 属性写法 |
|---|---|---|---|---|
| chrome | `localStorage["reader3.ui.colorScheme"]` | `system` / `light` / `dark` | `system` | `system` → **移除** `data-theme`；否则 `data-theme="light\|dark"` |
| reading | `localStorage["reader3.reader.theme"]` | `auto` / `paper` / `sepia` / `green` / `night` | `auto` | 始终写 `data-reading-theme="<值>"`，`auto` 也写 |

> **闪白（FOUC）**：两个属性都必须在首屏绘制前生效。`<head>` 内嵌**一段**同步 inline script 读两个 key 并 stamp 到 `<html>`，**不能**等 `defer` 的 JS。三处容易错：
> 1. 属性挂 `<html>`，**不是** `.reader-shell`——inline script 跑的时候 `<body>` 还没解析，那个元素不存在。
> 2. `auto` 也要 stamp。属性缺席与 `auto` 在 CSS 上等价，但选择器状态、`data-testid` 断言和 `aria-checked` 都要一个具体值；缺席是「没读到 localStorage」的信号，两者不能混。
> 3. chrome 的 `system` 反过来——**必须**移除属性，因为跟随系统靠的是 `@media` 命中 `:not([data-theme="light"])`。

**visual 组合矩阵是 2 × 4 = 8 种**（chrome 有效结果只有 light / dark 两种，`system` 是解析策略不是第三种外观；reading 的 `auto` 解析成两端之一，不产生第五种纸）。但**不是所有断言都乘 8**：纸色与高亮是绝对值，正文对比度 4 条、高亮压纸 4×4=16 条，都与 chrome 无关；真正要跑满 8 遍的只有**接缝**——阅读器工具条 / 页边 / 弹层压在纸上的那圈边界。

### 3.4 间距 / 圆角 / 字阶

间距沿用现值（4/8/16/24/32/48），重命名为 `--r3-space-{xs,sm,md,lg,xl,2xl}`；圆角**取原型实测值**并命名（原型 `--radius-{sm,md,lg}` 一一对应）。本节此前写的「沿用 4/6/8/12」是**现状生产**的值，不是目标值——目标是原型。

这两族此前只有散文，没有可照抄的字面量；`plan §9.3` 的 token 硬编码 lint 第 5、6 两类（裸 `padding`/`margin`/`gap`、裸 `border-radius`）以它们为唯一合法出口，所以必须写成 CSS：

```css
--r3-space-xs:  4px;
--r3-space-sm:  8px;
--r3-space-md: 16px;
--r3-space-lg: 24px;
--r3-space-xl: 32px;
--r3-space-2xl:48px;

--r3-radius-sm:    6px;
--r3-radius-md:   10px;
--r3-radius-lg:   16px;
--r3-radius-full:999px;
```

> **间距阶只有这六档，圆角只有这四档，没有第七个和第五个。** `plan §9.2` 实测现状里有 `12` / `14` / `23` / `999` 四种离档圆角——`999` 对应 `--r3-radius-full`，其余三种在迁移时各自 snap 到 `sm` / `md` / `lg`，snap 之后不许再回头加档。要加档就要先说明它承担的是哪个新角色。

布局宽度（§6.2 的三栏 Grid 引用，此前未定义）：

```css
--r3-sidebar-w:232px;  /* 书库左栏，取原型 --sidebar-width */
--r3-right-w:336px;    /* 书库右栏，取原型 --insights-width */
--r3-right-w-collapsed:48px;
--r3-rail-w:56px;      /* 阅读器右侧竖排工具栏宽，取原型 --rail-width */
--r3-header-h:60px;    /* 页头高，取原型 --header-height */
```

`--r3-rail-w` 与 `--r3-header-h` 是**补的悬空值**：原型 `index.html` 定义了 `--rail-width: 56px` 与 `--header-height: 60px` 并在 12 处引用（rail 宽、`.reader-sheet.is-right` 的右偏移、以及 `calc(100vh - var(--header-height))` 这类高度算式），本节此前只收了三个书库宽度，翻译到生产时这两个会没有对应 token、退化成硬编码 px。

**控件尺寸档**（下面 §5.1 的 `.r3-btn` 引用）：

```css
--r3-control-h:     34px;  /* 默认档按钮 / 输入框 / select 高 */
--r3-control-h-sm:  28px;  /* --sm 档 */
--r3-control-px:    14px;  /* 控件左右内边距 */
--r3-control-gap:    6px;  /* 控件内图标与文字间距 */
```

> **控件高度与内边距不属于间距阶，这四个值故意不落在 4/8/16/24/32/48 上。** 间距阶量的是**元素之间**的距离，控件尺寸量的是**控件自身**的盒子——后者由字号 ＋ 行高 ＋ 上下内边距 ＋ 边框倒推而来（14px 字 × 1.4 行高 ≈ 20px，＋ 上下各 6px ＋ 2px 边框 = 34px），跟布局节奏无关。硬把 34 抬到 32 或压到 40 会改变按钮与同行输入框的对齐，是为了对齐一张与它无关的表而制造视觉回归。
>
> **反过来也一样：不许拿 `--r3-space-*` 表达控件高度。** `--r3-space-xl` 恰好是 32px，离 34 很近，但它是间距角色；有人为了「统一」把按钮高改成 `var(--r3-space-xl)` 之后，任何一次间距阶调整都会顺带改掉全站按钮高度。


字阶是**新增**——现状没有字号 token，全站硬编码 px：

```css
--r3-font-size-2xs:11px; --r3-font-size-xs:12px;  --r3-font-size-sm:13px; --r3-font-size-base:14px;
--r3-font-size-md:16px;  --r3-font-size-lg:18px;  --r3-font-size-xl:22px; --r3-font-size-2xl:28px;
--r3-leading-tight:1.4; --r3-leading-normal:1.6; --r3-leading-reading:1.9;
```

**`--r3-font-size-2xs:11px` 是补的**（裁决见 §11-R4）。原字阶只有 7 档、最小 12px，是在没测原型的情况下写的：原型实际用了 **12 个字号字面量**，其中 **44 处在 14px 以下**、只有 7 处等于 14px。强行把 11px 抬到 12px 会压掉徽章／eyebrow 与次级元数据之间的层级。

原型字面量按下表 snap，**这是唯一的映射，实施时不得再自行取整**：

| 原型值 | 用量 | → token（`--r3-font-size-` 前缀省略） | 说明 |
|---|---|---|---|
| 10px | 1 | `2xs` 11px | `.stale-dot` |
| 11px | 7 | `2xs` 11px | eyebrow / 状态 pill / 计数 |
| 11.5px | 9 | `xs` 12px | 次级元数据 |
| 12px | 8 | `xs` 12px | — |
| 12.5px | 12 | `sm` 13px | 作者行 / 笔记正文 / TOC |
| 13px | 15 | `sm` 13px | — |
| 13.5px | 1 | `base` 14px | `.msg-body` |
| 14px | 7 | `base` 14px | — |
| 15px | 2 | `md` 16px | `.modal-title` / `.settings-title` |
| 17px | 1 | `lg` 18px | `.empty-title` |
| 20px | 1 | `xl` 22px | `.stat-value` |
| 15px / 26px（图标位） | 3 | — | `.btn-icon` / `.rail-button` / `.page-arrow` 的 `font-size` 是**字形图标的尺寸**，随图标改 SVG 一并消失，不进字阶 |

> 上表有三处会产生可见位移：15→16、17→18、20→22。这是把设计收进字阶的代价，接受。`17px` 与阅读器正文默认字号（§6.3，14–24px 可调）无关——那是 iframe 内的正文，不走 UI 字阶。

> ⚠️ **字阶叫 `--r3-font-size-*`，不叫 `--r3-text-*`。** `--r3-text` / `--r3-text-muted` / `--r3-text-subtle` / `--r3-text-disabled` / `--r3-text-on-accent` 在 §3.3 里**已经是五个文字颜色 token**；字阶再占 `--r3-text-` 前缀，同一个前缀就同时表示颜色和字号，`--r3-text-sm` 与 `--r3-text-subtle` 靠肉眼分不出角色。**跨角色禁令**：任何 token 前缀只承担一个角色——颜色是 `--r3-text-*`，字号是 `--r3-font-size-*`，行高是 `--r3-leading-*`，间距是 `--r3-space-*`，控件尺寸是 `--r3-control-*`。把字号 token 用在 `color` 上、或把颜色 token 用在 `font-size` 上，都是错误，而不是风格问题。

**字体**：`--r3-font-sans` 沿用系统栈。`--r3-font-serif` 现在指向 Google Fonts 的 `Noto Serif SC`——**这是个离线故障点**（自托管应用连外网 CDN，断网即回退且首屏跳字）。改为 self-host 思源宋体子集，或直接回退到系统 `PingFang SC` / `Songti SC`。

### 3.5 层级（z-index）与动效

#### 3.5.1 z-index：9 档有序枚举

现状实测（2026-08-20，`grep -roE 'z-index: *[0-9]+' src/`）：**生产 CSS** 里散着 **19 个不同的 z-index 字面量**——

```
1  2  10  20  30  40  45  50  60  90  100  950  1000  1001  1100  1200  1300  1350  1400
```

跨三个数量级，且**没有一个是 token**。`45` 与 `1350` 这种值只有一种来源：某个层压不住另一个，就地 +5。这种写法的失败模式不是"层错了"，是**层对了但没人知道为什么对**——下一次谁再 +5 就又翻过去。

> **上面这次实测只覆盖 `src/`。** 原型 `designs/reader-pro-next/index.html` 另有一套自己的阶梯——13 处、10 个不同值（`2 5 30 40 50 55 60 90 100 200`），与生产的 19 个只有部分重合。**两套都要 snap 到下面这 9 档**，但原型侧的逐值映射表归 [前端计划](./plan-frontend-ui-refactor.md) 的 **WI-10 §10.1.1** 维护，**本节不抄那张表**——抄进来就是第二份，跟 §3.4 字阶那张 snap 表不同（那张表的定义处就在本文）。本节只负责定义档位本身。

归成 9 档。`sticky` 及以上每档相隔 100——留这个空隙是为了将来插一档时不用给其余八档重编号：

```css
--r3-z-base:      0;    /* 常规文档流 */
--r3-z-raised:   10;    /* 卡片内抬升：角标、hover 覆盖、拖拽把手 */
--r3-z-sticky:  100;    /* 页内粘性：页头、栏目头 */
--r3-z-panel:   200;    /* 侧栏 / 抽屉 / TOC / 笔记 / 搜索 / AI 面板 */
--r3-z-overlay: 300;    /* 面板遮罩 */
--r3-z-toolbar: 400;    /* 阅读器右侧竖排工具栏 */
--r3-z-popover: 500;    /* 标注工具栏、气泡、下拉、tooltip */
--r3-z-toast:   600;    /* 全局 Toast */
--r3-z-skip:    700;    /* 跳转链接（skip link）—— 键盘逃生口，聚焦时必须压过一切 */
```

**四条硬规则：**

1. **完整偏序：`base < raised < sticky < panel < overlay < toolbar < popover < toast < skip`。** 这是全站层叠关系的**唯一**定义，也是它的**机器可验形式**——散文里的「必须高于」测不了，token 的数值大小关系测得了。这条偏序里有两段是被具体故障逼出来的，不是排版审美：
   - **`toolbar > overlay > panel`** —— 即 §6.3「右侧工具栏」那条要求（工具栏必须高于所有面板与遮罩、任何面板打开时都保持可点击）。D6 记录的实测故障（TOC / Notes 打开后点击 `#reader-search-toggle` 直接超时，遮罩吃掉了点击）就是这段被违反的样子。§6.3 那句已改为引用本表，两处不再各说各的。
   - **`skip > toast`** —— 见规则 2。

   本文其余各节（§6.3、§6.4、§8）**一律不重述任何一段大小关系**，需要时引用本条。
2. **`--r3-z-skip` 是最高档，且是唯一允许高于 `--r3-z-toolbar` 的元素。** 三点理由：
   - **不能并进 `--r3-z-toast`。** 同值时叠放顺序由 DOM 顺序决定，而 skip-link 按定义在文档**最前**、Toast 容器通常挂在**最后**——并档的结果就是 Toast 稳定盖住 skip-link。这是**无障碍回归**（键盘用户的逃生口被一条自动出现的提示挡住），不是理论隐患，所以它必须靠数值而不是靠 DOM 顺序赢。
   - **占最高档不影响任何常规层叠**，因为它平时不可见：原型 `index.html:178-183` 的写法是 `position: absolute; top: -48px` 移出视口，`:focus { top: 12px }` 才落下来。一个只在聚焦瞬间存在的元素，无论排多高都碰不到别的层。
   - **例外仅此一个。** 除 skip-link 外，任何元素都不许高于 `--r3-z-toolbar`——工具栏之上只剩 `popover` / `toast` / `skip` 三档，各有明确归属，没有"再高一点"的空位。
3. **`Modal` 不占任何一档。** 见 §11.2 的裁决：`<dialog>.showModal()` 把元素放进 **top layer**，位于所有 z-index 之上，`z-index` 对它**无效**。给 `.r3-modal` 写 `z-index: 9999` 是死代码，且会误导后来者以为 modal 参与这套排序。非模态弹层（下拉、气泡、标注工具条）不走 `<dialog>`，它们归 `--r3-z-popover`。
4. **组件 CSS 里出现裸 `z-index: <数字>` 一律违规。** 只许 `z-index: var(--r3-z-*)`。需要新层级时**改这张表**（`sticky` 以上每档相隔 100，插一档不动其他值），不许在使用点自行加数。这条可被 lint 机械执行：扫组件 CSS 里 `z-index:` 后不跟 `var(--r3-z-` 的行。

> 迁移期例外只有一条：`--dedao-*` 时代的旧 CSS 在被重写之前保留原字面量，不逐个改。新写的、改过的、以及 Phase 4 重写过的文件一律按本表。

#### 3.5.2 动效：三档时长 ＋ 三条缓动

现状实测（同日，扫 `src/` 的 `transition` 声明）：**7 个不同的时长字面量**——`0.15s` / `0.2s` / `150ms` / `160ms` / `180ms` / `300ms` / `500ms`。其中 `0.15s` 与 `150ms` 是同一个值的两种写法，`160ms` / `180ms` 与 `150ms` 肉眼不可分辨。

但关键事实是：`dedao-theme.css:93-95` **已经有** `--dedao-transition-{fast,normal,slow}` = `150ms` / `300ms` / `500ms` 三档，且全站大量引用。所以三档**是沿用，不是新发明**，映射 1:1 无损：

| 现有 token | 现值 | → 新 token | 新值 |
|---|---|---|---|
| `--dedao-transition-fast` | `150ms ease` | `--r3-duration-fast` | `150ms` |
| `--dedao-transition-normal` | `300ms ease` | `--r3-duration-normal` | `300ms` |
| `--dedao-transition-slow` | `500ms ease` | `--r3-duration-slow` | `500ms` |

唯一的变化是**把缓动从时长里拆出来**：现值把 `ease` 焊死在 token 里，导致想换缓动就得换时长档。拆开后时长与缓动可自由组合。

```css
--r3-duration-fast:   150ms;  /* 悬停、按下、focus ring、颜色过渡 */
--r3-duration-normal: 300ms;  /* 面板/抽屉滑入滑出、横幅出现、翻页 */
--r3-duration-slow:   500ms;  /* 主题切换、整页态变化 */
--r3-ease-standard:   cubic-bezier(0.2, 0, 0, 1);   /* 进出场通用 */
--r3-ease-decelerate: cubic-bezier(0, 0, 0, 1);     /* 入场 */
--r3-ease-accelerate: cubic-bezier(0.3, 0, 1, 1);   /* 出场 */
```

游离的 `0.2s`（＝200ms）/ `160ms` / `180ms` 一律 snap 到 `fast`，`0.15s` 统一写成 `150ms`。**这几处不产生可感知差异**：最大偏移是 200ms → 150ms 的 50ms，且落在同一个"快速反馈"知觉区间内。与 §3.4 字阶 snap 的三处（15→16 / 17→18 / 20→22 有可见位移、需要接受代价）不同，动效这边**没有代价**。

#### 3.5.3 `prefers-reduced-motion`：单点降级

§8 第 5 条要求「尊重 `prefers-reduced-motion`：面板动效降级为瞬时」。**那条要求的落地形式就是下面这段，两处不是两套要求。**

```css
@media (prefers-reduced-motion: reduce) {
  :root {
    --r3-duration-fast:   0ms;
    --r3-duration-normal: 0ms;
    --r3-duration-slow:   0ms;
  }
}
```

**组件一律不自己处理 `prefers-reduced-motion`。** 只要组件的 `transition-duration` / `animation-duration` 全部引用这三个 token，这一处重定义就覆盖全站；组件里再写一遍 `@media (prefers-reduced-motion)` 是重复且必然漂移的。

> 三个已知的例外不受这一处重定义管辖，因为它们都不是"时长为 0 就等于关掉"。**前两个必须在本块里自己处理；第三个恰恰相反——它必须不出现在本块里。**
>
> 1. **无限循环动画**——生产现有三条：`dedao-theme.css` 的 `dedao-pulse 2s`、`dedao-skeleton-loading 1.5s`、`dedao-spin 0.8s`。它们的时长本来就不在上面三档里（它们不是过渡），置 0 也不等于关掉。这类必须 `animation: none` 并改用静态形态（静止的骨架块、文字状态）。
> 2. **`scroll-behavior: smooth`**（`css/reader.css:33`，TOC 点击跳章）——它不读 duration token，要单独在同一个 `@media` 块里改成 `auto`。
> 3. **停留时长**——弹出式提示从挂载到自动消失之间的那一段（`--r3-dwell-toast`，取值与裁决理由见 §5.3，本条不重述）。它是**阅读时长**不是动画时长：置 0 不是"没有动效"，是"消息没送达"，而需要减少动效的用户往往需要**更多**而不是更少的时间。它是独立 token，**定义在本 `@media` 块之外，本块不重定义它**——和例外 1 的循环周期（`--r3-skeleton-cycle`，§5.2）是同一条道理的两次应用，两者都不许写成 `--r3-duration-*` 的倍数。
>
> 除这三类外，出现在组件 CSS 里的 `@media (prefers-reduced-motion)` 都应被删掉，改为引用 token。

---

## 4. 可测试性契约（`data-testid`）

**这是本规格与 migration plan 之间最关键的一条接口。**

Plan 的 Phase 1b 会写 Playwright E2E，它是 Phase 4A 的进入条件（**不是 GitHub 的 required check**——CI 仅发版触发，见迁移计划 §7）。如果 E2E 用 class 或 DOM 结构做选择器，本规格的任何布局改动都会推翻 E2E。

**规则（须写入 Phase 0）**：

1. 每个交互元素、每个可断言区域必须有 `data-testid`。
2. E2E **只允许**用 `data-testid` 和 ARIA role/name 定位。禁止 class 选择器、禁止 `nth-child`、禁止层级结构选择器。
3. `data-testid` 命名 `{page}-{region}-{element}`，一经确定不随视觉改动而变。
4. 重设计可以任意改 class、改嵌套、改标签——但**不得改 testid**。
5. testid 的值必须是**字符串字面量**，不得由变量拼接或模板插值产生（原型的 `data-testid={"status-" + props.status}` 是错的，改静态映射表）。两条理由：命名 lint 扫的是字面量，拼出来的它看不见；且 testid 契约的价值有一半在**可 grep**——一个在仓库里搜不到的 testid，E2E 挂了没人找得到它是谁发的。

   规则 5 只覆盖了**取值有界**的情形。0.5 落地时补上无界的一半（2026-08-23）：

   | 取值 | 做法 | E2E 怎么定位 |
   |---|---|---|
   | **有界**（枚举：状态、颜色、主题、tab……） | 逐个枚举成字面量，放进一张 `const` 表，`data-testid={表[key]}`。**表的标识符里要带 `TESTID`**——命名 lint 靠这个约定找到表内的字面量 | `[data-testid="rd-anno-color-yellow"]` |
   | **无界**（来自用户数据的 id：书、集合、笔记、会话、章节、provider） | **同类元素共用一个字面量 testid**，id 由**另一个** `data-*` 属性携带（`data-book-id` / `data-note-id` / `data-provider` …） | `[data-testid="lib-book-card"][data-book-id="…"]` |

   无界那一行不违反规则 2：`data-*` 属性选择器既不是 class、不是 `nth-child`、也不是层级结构选择器，
   重设计改不动它。把 id 拼进 testid 才是违规——那样每本书都会造出一个 grep 不到的新 testid。

   逐条落地见 [`contracts/testid-rename-map.md` §5](../20260816-tech-stack-migration/contracts/testid-rename-map.md)。

命名约定：

| 页面 | 前缀 | 示例 |
|---|---|---|
| 书库 | `lib-` | `lib-book-card` / `lib-sidebar-collection` / `lib-toolbar-sort` |
| 阅读器 | `rd-` | `rd-toolbar-toc` / `rd-anno-color-yellow` / `rd-notes-panel` |
| 设置 | `set-` | `set-provider-row` / `set-save-prefs` |

> 现状许多元素已有稳定 `id`（`#chat-send-btn`、`#reader-toc-toggle`），可直接映射为 testid，成本很低。**但必须在 Phase 1b 写 E2E 之前完成**，否则就是返工。

### 4.1 与原型的对账（2026-08-16 实测）

原型 `designs/reader-pro-next/` 现有 **134 个唯一 `data-testid`，其中符合上表前缀方案的：0 个。**

> **2026-08-23 改名落地后的订正：真实数是 138，不是 134。** 差的 4 个不是新元素，是口径差——
> 原先只清点了 `data-testid="…"` 属性，漏掉了 `Sheet` 组件的 `testId="…"` **prop** 形式
> （`toc-panel` / `notes-panel` / `reader-search-panel` / `ai-panel`），它在组件内部转成 `data-testid`，
> 在浏览器里同样是一个 testid。**命名 lint 因此必须同时扫 `testId="…"`。**
> 下面那 24 个的数字反而一直是对的：23 个在属性里，第 24 个（`reader-search-panel`）正是漏掉的 prop 之一。
> 全部新旧对照见 [`contracts/testid-rename-map.md`](../20260816-tech-stack-migration/contracts/testid-rename-map.md)。

> ⚠️ 容易看错的一点：有 24 个 testid 带 `reader-` / `library-` 前缀，形似合规，实则是**另一套**命名（页面全称而非 `rd-` / `lib-`）。它们比裸名更危险——批量改名时容易被当成"已经对了"而跳过。**138 个站点全部需要改名。**（已于 2026-08-23 在 007 的 0.5 里改完：原型 221 个唯一名全部合规。）

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
| `Button` | `.toolbar-btn` / `.mini-btn` / `.btn` / `.rt-btn` / `.nav-btn` / `.ai-btn` / `.drawer-btn` **七套** | 收敛为 `.r3-btn` ＋ 下方 5 个修饰符（§5.1） |
| `Badge / Pill` | `.badge` / `.status-pill` / `.chunk-pill` | 收敛为 `.r3-badge` + 状态色修饰符 |
| `Modal` | `<dialog class="modal">` ×5，结构一致 | **原生 `<dialog>` ＋ `showModal()`**（已裁决，见 §11.2），抽 `.r3-modal`；原型的 `div[role=dialog]` 改掉 |
| `Drawer / Panel` | `#reader-search-drawer` / `#reader-ai-panel` / `#toc-mode` / `#notes-mode` 各写一套 | 统一 `.r3-panel` + 进出场动效 + 焦点陷阱 |
| `FormField` | `.form-field`/`.form-label`/`.form-error` | 保留，补 `aria-describedby` 绑定 |
| `EmptyState` | 仅 library 有 `.empty-state` | 抽为共用；search / chat / notes 结果为空时统一使用 |
| `Toast` | **有一个不合规实现**：`static/js/annotations.js` 的 `showToast()`，1 处调用，停留 1400ms 硬编码，`zIndex` 内联写死 `2000`，颜色写死。（设置页的 `.status` `<span>` 是**另一回事**——那是行内状态位，5 处，属 `EmptyState`／行内错误的邻居，不是 Toast 的替代品） | 重写；解剖见 §5.3 |
| `Skeleton` | **有定义但零使用**：`dedao-theme.css` 的 `.dedao-skeleton` ＋ `@keyframes dedao-skeleton-loading 1.5s infinite`，全仓库使用点 **0**（是死 CSS，且 §3.5.3 把它列为待处理的三条无限动画之一）。加载态现为 `-` 或 `Loading...` 文本（`library.html` 2 处） | 重写；解剖见 §5.2 |

> ✅ **`Modal` 选型已裁决（2026-08-20，§11.2）：原生 `<dialog>` ＋ `showModal()`，`div[role=dialog]` 落选。** 现有 Jinja 模板的 5 个 `<dialog class="modal">` **不动**（它们本来就是对的），要改的是原型 `components.jsx` 里那个 `div.overlay` ＋ `role="dialog"`。DEG-S5 的「不可 Esc 关闭」不构成反对理由——`<dialog>` 的 `cancel` 事件可取消，一行 `preventDefault()` 即禁掉 Esc。完整理由见 §11.2。
>
> 三条派生约束：
>
> 1. **`.r3-modal` 不设 `z-index`**（§3.5.1 规则 3，top layer 在所有 z-index 之上，写了也无效）。
> 2. **遮罩用 `::backdrop`**，不再手写 `div.overlay`——手写遮罩就是原型那条路，会把 modal 拖回 z-index 体系里。
> 3. **非模态弹层不用 `<dialog>`**：下拉、气泡、标注工具条走普通元素 ＋ `--r3-z-popover`。`<dialog>` 只用于真正的模态（需要阻断背景交互的那种）。

### 5.1 `Button` 的 canonical 变体集（裁决见 §11-R3）

`.r3-btn` 为基类：描边中性、`height: var(--r3-control-h)`、`padding: 0 var(--r3-control-px)`、`gap: var(--r3-control-gap)`、`border-radius: var(--r3-radius-sm)`。修饰符只有五个：

| 修饰符 | 用途 | 原型对应 | 备注 |
|---|---|---|---|
| `--primary` | 主操作，每屏至多一个 | `.btn-primary` | 实底品牌蓝 |
| `--danger` | 破坏性操作 | `.btn-danger-solid` | **改名**：`-solid` 是实现细节，不进变体名 |
| `--ghost` | 无边框低强度操作 | 现有 **12 个裸类**（`.text-button` / `.link-button` / `.collapse-button` / `.row-more` / tab 类…） | 原型没有统一 ghost，全是就地写的 `border:0; background:none` |
| `--icon` | 纯图标方形按钮 | `.btn-icon` | 必带 `aria-label`（§8 第 6 条） |
| `--sm` | 尺寸档，`height: var(--r3-control-h-sm)` | `.btn-sm`（10 处） | **本规格此前漏了尺寸档**，补上；可与上面四个叠加 |

> **上面四个尺寸值本轮从裸 px 改为 token 引用，视觉零变化。** `34` / `14` / `6` / `28` 一个都没动，只是搬进 §3.4 的控件尺寸档。此前它们是本节仅存的四个裸 px——同一行的 `border-radius: var(--r3-radius-sm)` 说明作者知道该怎么写，只是当时 §3.4 没有可引用的控件尺寸 token，于是就地写了字面量。**它们不该被 snap 到间距阶**，理由见 §3.4 控件尺寸档下方那条。

**`.btn-secondary` 删除。** 原型里它的全部声明是 `background: var(--surface)`，而基类 `.btn` 已经是同一个值——**它是空操作**，24 处引用降级为裸 `.r3-btn`，零视觉变化。

**状态**：基类必须实现 `default` / `hover` / `active` / `disabled` 四态 ＋ 全局 `:focus-visible`；`loading` 态由 §5 的 `Skeleton`／spinner 承担，不做成按钮修饰符。原型目前只有 `hover` 与 `disabled`，`active` 缺失。

---

### 5.2 `Skeleton`

`.r3-skeleton` 为基类：`background` 是一条横向扫光渐变（`--r3-surface-sunken` → `--r3-border` → `--r3-surface-sunken`，`background-size: 200% 100%`），`animation: r3-skeleton-sweep var(--r3-skeleton-cycle) linear infinite`，`border-radius: var(--r3-radius-sm)`。**基类不设宽高**——尺寸一律由使用点的布局给（Grid/Flex 的 `1fr`、父容器的 `aspect-ratio`、或一个 `width: 60%`）。

这三个颜色是生产已有的 `.dedao-skeleton` 逐个翻译过来的（原写 `--dedao-bg` / `--dedao-border` / `--dedao-bg`），**视觉零变化**。扫光周期 `1500ms` 同样取自生产已有的 `@keyframes dedao-skeleton-loading 1.5s`。之所以能照搬，是因为那段 CSS **定义处 1 个、使用处 0 个**——它是一段从来没上过屏的死代码，把它接上使用点就是本组件要做的事。

| 修饰符 | 用途 | 形状 | 用在哪 |
|---|---|---|---|
| `--line` | 单行文字占位 | 高 `calc(var(--r3-font-size-base) * var(--r3-leading-tight))`，`border-radius: var(--r3-radius-sm)` | 书名、作者、统计数字、设置项标签 |
| `--block` | 矩形块占位 | `border-radius: var(--r3-radius-md)`，比例由父容器 `aspect-ratio` 给 | 书卡封面位、provider 卡整体 |
| `--circle` | 圆形占位 | `border-radius: var(--r3-radius-full)`，宽高相等 | 图标位、状态点 |

**只有这三个修饰符。** 不设 `--w-25 / --w-50 / --w-75` 这类宽度档——宽度是布局的事，做成修饰符会在书卡、统计区、设置卡三个地方各长出一套，而它们本来就该由各自的容器决定。这与 §5.1 里 `.r3-btn` 只留五个修饰符是同一条纪律。

**三处使用点**（组合而成，不是新修饰符）：

| 使用点 | 组合 | 替代的现状 |
|---|---|---|
| 设置页加载中（§6.1） | 每张 provider 卡 = 1×`--line`（卡标题）＋ 3×`--line`（启用开关 / API key / 模型三行） | 现状是整页空白直到数据返回；`settings.js` 出错时才写一行文本 |
| 书库书卡加载中（§6.2） | 1×`--block`（封面，父容器 `aspect-ratio: 2/3`）＋ 2×`--line`（标题两行）＋ 1×`--line`（作者，宽 60%） | `library.html` 里 **2 处** `<span class="status-pill is-loading">Loading...</span>`。§6.2「状态」行已经写明骨架是来替代它的 |
| 书库右栏统计数字（§6.2） | 4×`--line`，各自宽度由统计项自身的列宽给 | 现状四个数字位在数据到达前是 `-` |

**动效**：扫光周期引用 `--r3-skeleton-cycle`，缓动写 `linear`（扫光是匀速循环，三条缓动都是给进出场用的，套在无限循环上会产生周期性的停顿感）。

> **`--r3-skeleton-cycle` 必须是一个独立 token，不许写成 `--r3-duration-*` 的倍数。** §3.5.3 把三个 duration token 在 `prefers-reduced-motion` 下重定义为 `0ms`；任何从它们派生的时间量都会跟着变成 0。对过渡而言这是正确的（0ms 就是关掉动画），但**对「一段时间的长度」而言这是错的**。§3.5.3 例外 1 已经把这个道理写了一半——「无限循环动画的时长本来就不在上面三档里（它们不是过渡）」——本条只是把它落成一个具体 token，并且把它**定义在 `@media (prefers-reduced-motion)` 块之外**。同一条原则在 §5.3 的 Toast 停留时长上再用一次。

**`prefers-reduced-motion` 下的形态**（§3.5.3 例外 1）：

```css
@media (prefers-reduced-motion: reduce) {
  .r3-skeleton { animation: none; background: var(--r3-surface-sunken); }
}
```

这是本组件**唯一**允许自带 `@media (prefers-reduced-motion)` 的地方，理由就是 §3.5.3 例外 1：无限循环动画置 0 不等于关掉。把渐变一并换成纯色是必须的——留着 `background-size: 200%` 的渐变而只停掉动画，会得到一块左半深右半浅的静止色块，比纯色更像渲染故障。

**可访问性裁决：`aria-hidden` 与 `aria-busy` 都用，但挂在不同元素上。**

| 属性 | 挂在哪 | 值 | 理由 |
|---|---|---|---|
| `aria-hidden="true"` | **骨架元素自己**（每个 `.r3-skeleton`） | 恒为 `true` | 它没有可读内容。不挂的话屏幕阅读器会在书卡网格里遍历出一串空节点，用户听到的是「空 空 空 空」 |
| `aria-busy` | **承载骨架的容器**（书卡网格 `lib-book-grid`、provider 卡列表、统计区） | 加载中 `true`，数据到达后 `false` | `aria-busy` 的语义是「这个区域正在更新，先别播报中间态」。它必须挂在**会被更新的那个容器**上——骨架自己在数据到达时就消失了，挂在它身上的状态没有「变成 false」的时刻 |

两者**不是二选一**：它们回答的是两个不同的问题——`aria-hidden` 回答「这个节点要不要进无障碍树」，`aria-busy` 回答「这个区域现在处于什么状态」。

反过来，三种做法**明确禁止**：

1. **不给骨架 `role="status"` 或 `aria-live`。** 那会让每次加载都播报一次空内容。
2. **不给骨架 `role="progressbar"`。** 骨架不表示进度，没有 `aria-valuenow` 可填；一个永远读不出百分比的进度条比没有更糟。
3. **不用 `alt="加载中"` 之类的替代文本。** 加载状态由容器的 `aria-busy` 表达，在每个占位块上重复一遍等于把「加载中」念 4 遍。

**原型对应**：**无。** `skeleton` 在 `designs/reader-pro-next/` 的五个源文件与 `index.html` 里合计 **0 命中**——原型 README 明说「加载骨架从来没做过」。本节**不参照原型**，参照的是生产那段零使用的 `.dedao-skeleton`。

> **硬约束：本组件不进任何时序断言，这条约束本身也是规格的一部分。**
>
> 三处已生效的要求指向同一件事：[前端计划](./plan-frontend-ui-refactor.md) 的 **WI-8** 明写「**不给 testid**。它是过渡态，断言它的存在会引入时序 flake。断言它**之后**的东西」；同一份计划 **§5.0** 明写「WI-8 的 Skeleton 是过渡态，**矩阵里没有任何一条以骨架为断言目标**」；**退出门槛 D-9** 要求该计划第 5 节里 `骨架` / `skeleton` 作为断言目标出现的命中数为 **0**。
>
> 落到本组件上是三条：
>
> 1. `.r3-skeleton*` 的任何元素**不得带 `data-testid`**。
> 2. 任何验收条目**不得以「骨架出现」为断言目标**。要断言加载态，断容器的 `aria-busy` 从 `true` 翻到 `false`；要断言加载完成，断数据到达后的书卡数量等于返回条数。这两条都不需要给骨架任何标识，也不需要 class 选择器。
> 3. **样式契约也不在运行时断言。** `prefers-reduced-motion` 下骨架不动这件事，落成 **CSS 源码 / 构建产物断言**——产物里必须含 `@media (prefers-reduced-motion: reduce)` 下 `.r3-skeleton { animation: none }` 这条规则（WI-8 验收 2 / 3）。
>
>    这条此前写的是「样式契约在同一帧内可判，所以可以在 E2E 里断」。**那是错的，而且错得不显眼**：同一帧内可判的前提是**手上得有那一帧**——要读到骨架的计算样式，骨架必须正在屏幕上，也就是必须抢在数据返回之前抓住它。**在 E2E 里，「读骨架的静态样式」和「断言骨架出现」是同一个时序赌局**，区别只在于前者看起来不像时序断言。而 [前端计划](./plan-frontend-ui-refactor.md) §5.1–§5.9 的全部 `F*` 行都是 `pytest-playwright` E2E（见 §5.0 的执行器表），这个赌局是真的。
>
>    落成源码断言反而**更强**：它每次都跑，不依赖抓没抓到加载窗口；而一条抓不到骨架的 E2E 断言会静默地什么都没验——绿灯，零保证。这也正是计划 §5.0 已有的纪律：「某个 class 不该再存在」这类断言一律落到源码 / 构建产物的字符串上，不用运行时查询。
>
> **结论：骨架在运行时一条断言都没有——时序的没有，样式的也没有。** 无障碍保证一条不少，只是换了个每次都跑的地方兑现。

---

### 5.3 `Toast`

`.r3-toast` 为基类：`position: fixed`、屏幕底部居中、`padding: var(--r3-space-sm) var(--r3-space-md)`、`gap: var(--r3-space-sm)`、`border-radius: var(--r3-radius-md)`、`box-shadow: var(--r3-shadow-lg)`、`z-index: var(--r3-z-toast)`（该档在 §3.5.1 的偏序里的位置由那一节定义，本节不复述数值关系）。结构是「图标 ＋ 一行文案」，**不含关闭按钮**（理由见下方停留时长段）。

| 修饰符 | 用途 | 前景色 | 底色 | 用在哪 |
|---|---|---|---|---|
| `--success` | 操作已完成 | `--r3-success` | `--r3-success-subtle` | 设置保存成功（§6.1）、集合创建/重命名成功、批量索引已提交 |
| `--error` | 操作已失败，**且用户无需动作** | `--r3-error` | `--r3-error-subtle` | 复制到剪贴板失败、后台任务提交失败 |
| `--info` | 中性告知 | `--r3-info` | `--r3-info-subtle` | 「AI 面板未启用」这类提示（生产现有的唯一一处 toast 调用） |

边框统一 `1px solid currentColor`，`color` 由修饰符设定——与 §5.4 的降级横幅同一套写法，理由也同一条：§3.3 实测四个 `-subtle` 压在页面底上只有 1.10–1.22:1（亮色）、1.15–1.32:1（夜间），**只染底色的容器在两个主题下都近乎看不见**。三个修饰符都**不许写十六进制字面量**，只引用 §3.3 的语义色。

**停留时长裁决：`4000ms`，且必须是它自己的 token，不许从 `--r3-duration-slow` 派生。**

同一个数字目前有三个互相冲突的取值：

| 出处 | 值 | 表达形式 |
|---|---|---|
| 本规格 §6.1 设置页「状态」一行，原写「保存成功（Toast，2s 自动消失）」 | 2000ms | 散文里的裸常数。**已随本节收口改掉**：§6.1 现在写「停留时长见 §5.3，此处不写秒数」，不再自带秒数 |
| [前端计划](./plan-frontend-ui-refactor.md) §5.0 的 `N` 求值表 ＋ WI-11 验收 4 | 4000ms | 原写 `--r3-duration-slow` × 8，从 `getComputedStyle` 读值再乘。**已随本节收口改掉**：两处现在都读 `--r3-dwell-toast`，且 WI-11 新增验收 4a 作为回归护栏 |
| 生产 `static/js/annotations.js` 的 `showToast` | 1400ms | `setTimeout(…, 1400)` 硬编码 |

**取 4000ms**（计划那一侧的值），理由不是「计划比规格新」，而是这两条：

1. **两个候选值都是 `--r3-duration-slow` 的整数倍**（2000 = 4×500，4000 = 8×500），所以争的不是「能不能用 token 表达」，是**倍数该取几**。倍数只能按「读得完吗」来定，不能按「谁先写的」来定。
2. **两种取值的失败模式一个是静默的、一个是可见的。** Toast 是 §6.1 破坏性操作（清空对话 / 清空摘要）在确认对话框关闭之后**唯一**的反馈。用户的视线此刻还停在对话框刚消失的位置，要先注意到屏幕底部出现了东西、再移过去读完。2000ms 对「已保存」这种 3 个字的文案刚好够，对「已清空 12 条对话」就不够了——而**文案变长不会有任何测试失败**，它会安静地变成一个读不完的提示。4000ms 的失败模式只是「稍微碍眼」，是看得见的。**在两个失败模式之间选，永远选看得见的那个。**

**但表达形式必须改（已改，诊断保留在此备查）。** 计划 §5.0 原先的求值规则是「从 `getComputedStyle` 读 `--r3-duration-slow` 再乘 8，断言也用同一个算式」，这条规则在 `prefers-reduced-motion` 下会坏掉：§3.5.3 把 `--r3-duration-slow` 重定义为 `0ms`，于是 `0 × 8 = 0`——**开了减少动效的用户看不到任何 toast**，而 WI-11 验收 4 因为「断言用同一个算式」会照常通过。这是一个测试判不出来的功能性缺失，且它精准命中减少动效的那批用户。**「断言用同一个算式」这条纪律本身没错——同源才不会漂——错的是同源到了错的源上，所以收口只换基、不动纪律。**

根因是把两种不同的时间量挂在了同一族 token 上：`--r3-duration-*` 是**动画时长**，减少动效时归零是它的设计意图；停留时长是**阅读时长**，减少动效**不该缩短**它（需要减少动效的用户往往需要**更多**而不是更少的时间）。

因此：

```css
--r3-dwell-toast: 4000ms;   /* 定义在 @media (prefers-reduced-motion) 块之外 */
```

与 §5.2 的 `--r3-skeleton-cycle` 是同一条原则的两次应用：**不是过渡的时间量，不许挂在过渡时长档上。** 这条原则本身登记在 §3.5.3 的例外清单里——本 token 是那份清单的**例外 3**，`--r3-skeleton-cycle` 是例外 1。

进出场动效则相反，它**就是**过渡，照常引用三档：入场 `var(--r3-duration-normal) var(--r3-ease-decelerate)`，出场 `var(--r3-duration-normal) var(--r3-ease-accelerate)`。减少动效下这两个自动变 0ms（§3.5.3 单点降级），toast 直接出现和直接消失，停留 4000ms 不变——这正是想要的行为。

**可访问性裁决：永远 `polite`，永远不用 `role="alert"`，与降级横幅靠「谁需要动作」区分。**

| | `Toast`（本节） | `DegradeBanner`（§5.4） |
|---|---|---|
| `role` | **不设 `role`** | `status` |
| `aria-live` | `polite`，挂在**常驻的容器**上 | `polite`，挂在横幅自己身上 |
| `aria-atomic` | `true`（整条重播，不是逐词） | 不设 |
| 是否需要用户动作 | **否**。需要动作的东西不许用 Toast | 是，每条都带主操作按钮 |
| 生命周期 | 4000ms 后自动消失 | 直到状态解除或用户关闭 |

三条推论：

1. **`--error` 修饰符也用 `polite`，不用 `role="alert"`。** `role="alert"` 隐含 `aria-live="assertive"`，会打断屏幕阅读器当前正在念的句子。一个打断了用户、然后在 4000ms 后消失的提示，代价是用户丢了自己的阅读位置却换不回可回溯的信息——比不播报更糟。
2. **需要用户动作的失败不许用 Toast。** §6.1 已经把这条写进了状态清单：「保存失败（就地错误 ＋ 保留用户输入）」——表单保存失败走行内错误，不走 Toast。降级路径走 §5.4 的横幅。`--error` 修饰符只负责**已经发生且无需处理**的失败通知。这条不是风格偏好，它是 Toast 能安全地 `polite` ＋ 自动消失的前提。
3. **`aria-live` 挂在常驻容器上，不挂在 toast 元素上。** 一个刚插入 DOM 就带着 `aria-live` 的元素，播报行为在各屏幕阅读器上不一致；标准做法是容器先在 DOM 里就位并带上 `aria-live`，随后往里插内容。

**堆叠裁决：最多一条，新的替换旧的，不堆叠。**

新 toast 到达时替换容器内的现有内容并**重置停留计时**。四条理由：

1. **堆叠会移动点击目标。** toast 固定在底部居中，堆叠意味着每插入一条，已有的那条向上位移一个高度——而它下方或旁边可能正好是用户要点的东西。
2. **`aria-atomic="true"` 的容器每插入一条就重播全部内容。** n 条堆叠 = O(n²) 次播报。要避免这个就得给每条单独一个 live region，那又回到推论 3 禁止的那种写法。
3. **这个应用产生不了并发 toast。** 生产现存的 toast 调用点是 **1 个**；§6.1 新增保存成功、§6.2 新增批量操作反馈——三者都由单次用户手势触发，不可能同时在屏。堆叠是在解决一个本应用没有的问题（宪法原则 2，YAGNI）。
4. **替换让「最多一条」和「最多一个容器」变成同一个断言**，一次查询就能判——而 WI-11 验收 4 现在要断的正是「同时最多存在一个 Toast 容器元素」。

因为最多一条且必然在 4000ms 内消失，**基类不含关闭按钮**：一个按钮的存在会让用户以为需要处理它，而 Toast 的定义就是不需要处理。

**定位**：`bottom: var(--r3-space-lg)`（24px），横向居中。生产 `showToast` 现在写的是 `bottom: 26px`——差 2px，取整到间距阶，视觉上不可分辨。

`<768px` 档上 §7 要求「工具栏移到底部」，toast 必须落在工具栏**之上**而不是盖住它，偏移量应写成 `calc(var(--r3-space-lg) + <底部工具栏高度>)`。**§3.4 目前没有这个 token**——它只定义了桌面档竖排工具栏的宽度 `--r3-rail-w`，没有移动档底部工具栏的高度。这是本节唯一一处无法用现有 token 表达的量，见末尾 M-5。在 §3.4 补上之前，不许在这里写裸 px。

**原型对应**：**无。** `toast` 在原型五个源文件与 `index.html` 里合计 **0 命中**。原型的保存反馈走的是 `settings.jsx` 里的 sr-only `LiveRegion` ＋ 一行 `.state-line.is-ok`——**那是行内状态行，不是 Toast**（§2.1.1 的 P13 委托的是行内状态行的形态，不含本组件）。原型 README 已明说这两个组件「**不要拿原型当参考**，照搬会倒退」。

> **硬约束：`z-index` 只许写 `var(--r3-z-toast)`。** §3.5.1 规则 4 禁止组件 CSS 出现裸 `z-index: <数字>`，而生产的 `showToast` 恰好是全仓库唯一一个**内联 JS 赋值**的 z-index（`el.style.zIndex = "2000"`）——它躲过了 §3.5.1 那次基于 CSS 的实测。本组件替换它时这个值必须消失，不能搬进新代码。

---

### 5.4 `DegradeBanner`

`.r3-degrade-banner` 为基类，是 DEG-S1 / DEG-S2 / DEG-S3 / DEG-S4 四个降级状态**共用**的载体（DEG-S5 不是横幅，见下方专段）。

```css
.r3-degrade-banner {
  display: flex;
  gap: var(--r3-space-sm);
  align-items: flex-start;
  padding: var(--r3-space-sm) var(--r3-space-md);
  border: 1px solid currentColor;          /* ← 基类固定，修饰符不许改 */
  border-radius: var(--r3-radius-md);
  font-size: var(--r3-font-size-sm);
  line-height: var(--r3-leading-normal);
}
```

| 修饰符 | 承载的状态 | `color` | `background` |
|---|---|---|---|
| `--warn` | DEG-S1 / DEG-S2 / DEG-S4 | `var(--r3-warning)` | `var(--r3-warning-subtle)` |
| `--danger` | DEG-S3 / DEG-S5 | `var(--r3-error)` | `var(--r3-error-subtle)` |

tone 与状态的映射由 §6.4 设计要求 1 定义，本表只是把它落成 CSS，**不复述理由**。两个修饰符**只改 `color` 与 `background` 两个属性**，一个都不多。

**结构：四个槽，其中三个必填。**

```
.r3-degrade-banner
├── .r3-degrade-banner__icon       ← 必填，且由组件自己渲染（调用方不可传、不可关）
├── .r3-degrade-banner__body       ← 必填（children 插槽）
│   ├── .r3-degrade-banner__title
│   └── .r3-degrade-banner__copy
├── .r3-degrade-banner__actions    ← 必填，至少一个 .r3-btn
└── .r3-degrade-banner__dismiss    ← 选填，仅 dismissible=true 时渲染
```

正文用 children 插槽而不是 `title` / `copy` 两个字符串属性——四个状态的正文形态不一样（DEG-S1 要嵌一个「查看原文摘录」入口，DEG-S4 要显示进度与失败项），字符串属性表达不了。操作区同理，用 children 而不是 `primaryLabel`。

**§6.4 那条「只有底色的横幅不算数……必须同时有边框或图标」在本组件里结构上无法违反**，靠的是两处设计而不是靠一条约定：

1. **图标槽由组件自己渲染，不接受调用方覆盖。** 图标由 `tone` 决定（`warn` 一个、`danger` 一个），组件的 props 里**没有** `icon` 这个键，也没有 `hideIcon`。调用方能传的只有 children 和 `dismissible`——**没有任何一条路径能让图标缺席**。
2. **边框写在基类上，且色值来自 `currentColor`。** 修饰符只改 `color` 和 `background`，`border-width` 与 `border-style` 在基类里，改不到。想去掉边框只能改基类——而基类是全部四个状态共用的，改它会同时打掉四个，不可能被当成某一个状态的局部调整偷偷做掉。

`currentColor` 还顺带解决了 §6.4 的另一半要求「边框用前景色本身（不另设 border token）」：边框色与图标色天生同源，**不可能**出现「边框用了状态色但图标是灰的」这种半吊子形态。这不是一条需要 review 去抓的规范，它是 CSS 继承的机械结果。

**状态**：

| 状态 | 表现 |
|---|---|
| `default` | 常态显示，整条横幅**不可交互**（只有内部的按钮可交互）。不设 hover 态——横幅不是按钮 |
| `dismissed` | `dismissible=true` 且用户点了关闭：**从 DOM 移除**，不是 `display: none`。留在 DOM 里的 `role="status"` 元素即使不可见也可能被辅助技术遍历到 |
| 粘性 | 只有 DEG-S3（全局告警条，书库与阅读器都显示）需要粘在页头下方，用 `--r3-z-sticky`。其余三条在文档流内，**不设 `z-index`** |

**可访问性**：横幅自带 `role="status"` ＋ `aria-live="polite"`（[WI-1](./plan-frontend-ui-refactor.md) 已定）。三条推论：

1. **不复用原型的 `LiveRegion`。** 那是个 sr-only 元素，只能播报、不能当可见横幅用；§6.4 要的是「看得见 ＋ 听得见」，复用它只满足后一半。
2. **横幅不得抢焦点。** `role="status"` 的语义就是「不打断」。一条在阅读中途出现的横幅把焦点抢走，会打断正在读的用户——这恰好是 DEG-S5 要做而其余四条不许做的事（见下）。
3. **同一条文案不许出现在两个 live region 里。** 横幅自己是 live region，就不能再往 sr-only 播报器里写一遍，否则屏幕阅读器读两遍（WI-1 验收 3 断的就是这个）。

**testid**：五个状态各自的容器、主操作按钮、关闭按钮的**具体名字**见 [WI-1](./plan-frontend-ui-refactor.md) 的 testid 清单，本节不复述。命名规则见 §4。

**关闭态持久化**：`sessionStorage["reader3.degrade.<状态 id>"]`，`<状态 id>` 取小写状态号（`s1` / `s2` / `s3` / `s4`）。key 的命名空间规则见 §6.3 的 R5 段，本节不复述。

> **一个状态一个键，不按页面拆。** DEG-S3 在书库和阅读器两处显示、有两个 testid（`lib-degrade-s3` / `rd-degrade-s3`），但**只写一个键** `reader3.degrade.s3`——在书库关掉之后进阅读器又弹一次，用户会认为关闭按钮坏了。降级状态是**进程级事实**（是不是以 pickle 回退模式启动了），不是页面级事实，它的关闭态也该是进程级的。

**文案**（示例，语言按 §0 一律中文；每条文案必须满足的内容要求见 §6.4 的表，本节不复述）：

| 状态 | 标题 | 正文要点 | 主操作 |
|---|---|---|---|
| DEG-S1 | 标注已暂停套用 | 本书内容有更新，N 条标注暂停套用，**未删除** | 查看原文摘录 |
| DEG-S2 | 索引已过期，结果可能不全 | 这本书自上次建索引后有改动 | 重建索引 |
| DEG-S3 | 正在以兼容模式读取旧格式书库 | N 本书尚未迁移到新存储格式 | 查看未迁移书目 |
| DEG-S4 | N 本书正在迁移存储格式 | 进度与失败项；失败项可单独重试 | 重试失败项 |

#### DEG-S5 为什么不是这个组件的第五个实例

DEG-S5（多标签页写冲突）由 `ConflictDialog`（[WI-6](./plan-frontend-ui-refactor.md)）承担，不是 `DegradeBanner` 的一个 tone。它与另外四条**共享**的只有视觉语义那一层：

- tone 归 `danger`（与 DEG-S3 同档），`color: var(--r3-error)` ＋ `background: var(--r3-error-subtle)` ＋ `border: 1px solid currentColor`；
- 图标必填，同样由组件自己渲染，同样不可关；
- 文案语言（§0）与 testid 命名规则（§4）。

**不共享的六条，每一条都是结构性的：**

| # | 项 | 另外四条 | DEG-S5 | 为什么必须不同 |
|---|---|---|---|---|
| 1 | 容器 | 文档流内的横幅 | 原生 `<dialog>` ＋ `showModal()`（§11.2） | 它必须阻断背景交互——用户在做出选择前继续编辑，会产生第二次冲突 |
| 2 | z-index | DEG-S3 用 `--r3-z-sticky`，其余不设 | **不占任何一档** | `showModal()` 把元素放进 top layer，`z-index` 对它无效（§3.5.1 规则 3） |
| 3 | `role` | `status` | `alertdialog`（§6.4 设计要求 2） | 它需要用户**决策**，不是通知 |
| 4 | `aria-live` | `polite` | **不写** | `showModal()` 转移焦点时对话框即被播报；再加 `aria-live` 会重复播报一次 |
| 5 | 可关闭性 | `dismissible` 布尔 | **props 里没有这个键** | WI-1 已定「DEG-S5 不接受这个属性」。做成「传 `false`」是不够的——那样「传 `true`」在类型上仍然合法，只靠 review 拦。**没有这个键，可关闭在类型层面就不可表达** |
| 6 | 会话持久化 | 写 `sessionStorage["reader3.degrade.s<n>"]` | **不写任何键** | 它没有「本次会话内不再显示」这个态。写了键就意味着存在一条能让它不出现的路径，而 §6.4 要求「不得静默丢写」 |

关闭路径必须是**零条**：`cancel` 事件 `preventDefault()` 禁掉 Esc、不挂 backdrop 点击监听、不渲染 `×` 按钮。出口恰好两个——「保留我的修改」与「采用远端版本」，两者都必须真正落盘。这是五条降级里**唯一一条会真正丢用户数据**的（§6.4），所以它是唯一一条不给用户「先放着不管」这个选项的。

组件在两个出口中的任何一个执行完成之前，必须保持用户的编辑内容在内存里存活；远端不可达时也不许变成死路（两个出口都要有可用的结果，哪怕是「先保留在本地、稍后重试」）。

**原型对应**：**几乎没有。** 原型里唯一的降级 UI 是 `CollectionRow` 上的 `.stale-dot`——collection 级别的一个小圆点，书籍级与全局级全缺（§6.4 已记）。原型全文件 `aria-live` 只有 **1 处**，在 sr-only 的 `LiveRegion` 里，不是可见横幅。本节**不参照原型**。

---

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

> **本小节是 iframe 边界判据的唯一定义处。** 主计划 §7 的 Phase 4B 门槛、[前端计划](./plan-frontend-ui-refactor.md) 的 WI-14 / WI-16 / WI-18、技术栈计划 Phase 4 的主题项**只引用本小节，不复述判据**——复述会漂移。

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

**落点分工**：A + B 是**机械门槛**，对每一次 `themes.override()` 改动都要跑（结构测试，不需要完整 E2E）；C 是 **E2E**，见 `docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` 的 R-6。

不满足任何一条的改动，一律划归 Phase 4B 的行为变更，不属于设计。

> ⚠️ 即便如此，栏宽变化会改变**分页位置**。CFI 锚定理论上不受影响（CFI 基于 DOM 路径而非视觉位置），但这要被**断言**，不能被假定——即上面的断言 C。
>
> 落点：断言 C 由 `docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` **R-6** 承担。R-6 在 Phase 1b 覆盖今天已存在的三个参数（主题 / 字号 / 行距）；**栏宽是 D5 的产物，要到 4B.3 才存在**，届时作为 R-6 的第四个参数加入，并计入 4B.3 的退出门槛。本节此前写的是"Phase 1b 的 E2E 必须覆盖改栏宽后…"——那在顺序上不可能成立，栏宽那时还没做。

### 6.1 设置页（试点，先做）

**布局**：单栏居中，`max-width: 720px`，页头用与 library 一致的 `header`（现在只有一个 `← Back to Library` 文字链，导航不一致）。

**分区**（沿用现有四段，重新组织）：

1. **AI 偏好** — 默认 provider（下拉）、流式开关、时间戳开关。删除 `Auto suggested questions (future)`——不做的功能不该占一行 UI。
2. **服务商** — `#settings-providers` 动态渲染。每个 provider 一张卡：名称 + 启用开关 + API key（`type=password`，已配置显示 `••••••••` + "已配置"徽章）+ 模型 + 测试连接按钮。**新增连接状态指示**（未配置 / 已配置 / 测试通过 / 测试失败）。
3. **外观**（**新增分区**）— **界面明暗**三选一（跟随系统 / 浅色 / 深色，`data-theme` 轴，见 §3.3）。**没有「界面语言」控件**：交付语言只有 `zh-CN` 一个（§0），只有一个 locale 时语言选择器是**空操作**——与第 1 分区删掉 `Auto suggested questions (future)` 同一条理由，不做的功能不该占一行 UI。消息表本身保留（§10），将来加 `en` 是往表里加一列数据；控件要不要加回来，届时按 §0 重新裁决，不是现在预留一个不通电的下拉框。**这里也没有纸色**：阅读主题属于另一根轴，控件在 §6.3 的阅读设置面板里，两者不共用状态（裁决见 §11-R7）。
4. **数据** — 清空对话 / 清空摘要 / 导出 / 导入。**破坏性操作必须二次确认**：现在 `Clear conversations` 是点了就执行，无确认。用 `<dialog>` 确认（**不要用 `confirm()`**——浏览器模态会阻塞，且不可测）。

**状态**：加载中（骨架）/ 保存中（按钮 disabled + spinner）/ 保存成功（Toast，停留时长见 §5.3，此处不写秒数）/ 保存失败（就地错误 + 保留用户输入）。

**安全**：API key 永不回显（后端已保证不返回明文，前端不得把已填 key 写进可读 DOM）。

### 6.2 书库页

**布局**：三栏 CSS Grid，`grid-template-columns: var(--r3-sidebar-w) 1fr var(--r3-right-w)`，中栏 `1fr` 且 `min-width: 0`（现状缺这条，长书名会把网格撑破）。

| 区域 | 变更 |
|---|---|
| Header | 保留 logo + 导航 + 主操作。**新增**界面明暗切换按钮（`data-theme` 轴三态循环：跟随系统 → 浅色 → 深色）。**不是**纸色切换——书库页没有纸，纸色轴在这里无意义（§11-R7） |
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

`data-reading-theme` 只驱动**阅读画布**——纸色、正文墨色、高亮色，宿主页与 iframe 两侧同步。**它不碰 app chrome**，界面明暗是另一根轴（`data-theme`，裁决见 §11-R7），控件在设置页 §6.1 的「外观」分区，不在这个面板里。

| 控件 | 值域 | 持久化 | 作用域 |
|---|---|---|---|
| 主题 | `auto`（默认）/ `paper` / `sepia` / `green` / `night` | `localStorage["reader3.reader.theme"]` | 阅读画布（`.reader-shell` ＋ iframe） |
| 字号 | 14–24px，步长 1，默认 17 | `localStorage["reader3.reader.fontSize"]` | 仅 iframe |
| 行距 | 1.5–2.5，步长 0.1，默认 1.9 | `localStorage["reader3.reader.lineHeight"]` | 仅 iframe |
| 字体 | `system` / `serif` **（二选一）** | `localStorage["reader3.reader.fontFamily"]` | 仅 iframe |

> **上表是这四个控件的值域、步长、默认值、存储 key、作用域的唯一定义处**（S12）。计划、原型、测试矩阵一律引用它，**不得复述数值**——行距那 0.1 的偏差能在两个文件里并存，正是因为 `WI-18` 抄了一份。
>
> **行距值域已于 2026-08-23 裁决为 1.5–2.5**（原写 1.4–2.4，是无出处的笔误，裁法见 §2.1.4 C5）。定论的不是「生产与原型二比一」，而是**迁移无损**：现行生产能存下的只有 1.5 / 1.6 / … / 2.5 这 11 个值，值域取 1.5–2.5 则一个都不用钳；取 1.4–2.4 则 2.5 越界、必须钳到 2.4，让把行距调到最大的老用户版式当场位移——而 1.4 这一档**零存量**。这与 §11.1 末尾裁掉原型默认值 `leading: 1.85` 是同一条原则（不许让老用户的阅读版式无故位移），只是那次的结论是保规格、这次是改规格。步长 0.1 不变。
>
> **步长 0.1 与消浮点误差的写法是绑定的。** 生产 `reader.html` 用 `Math.round(x * 10) / 10` 消掉 `1.7000000000000002` 这类残差；WI-18 重写时必须一起搬，改步长就得改这个乘数。守卫用例见 [计划](./plan-frontend-ui-refactor.md) §5.1.2 的 `FB-R13a`。
>
> **本表四个 key 全是新的，四个都要迁移，不是新建。** 现状是 `localStorage["reader3-font-settings"]` 一个 JSON 对象存 `{fontSize, lineHeight}`（主题与字体则根本没存过，因为那 8 个控件没接线——见 §1 D1）。WI-18 必须把老对象拆进 `reader3.reader.fontSize` / `reader3.reader.lineHeight` 后再删旧 key，否则所有老用户的字号行距一次性回默认值。

> **key 命名空间是 `reader3.<区域>.<camelCase>`**（裁决见 §11-R5）。理由是生产**已经**在用这一套，而且不是孤例——2026-08-23 对 `src/reader3_app/web/static/` ＋ `templates/`（排除 `vendor/`）逐个调用点实测，现存 **9 个**前端存储 key：
>
> | # | key | 存储 | 定义处 |
> |---|---|---|---|
> | 1 | `reader3.library.viewMode` | localStorage | `static/library.js` 的 `VIEW_MODE_STORAGE_KEY` |
> | 2 | `reader3.library.bulkIndexingActive` | localStorage | `static/library.js` 的 `BULK_INDEX_STORAGE_KEY` |
> | 3 | `reader3.library.rightPanelCollapsed` | localStorage | `static/library.js`，字面量就地写死（无常量） |
> | 4 | `reader3.ai.model.{bookUuid}.{provider}` | localStorage | `static/ai.js` 的 `modelStorageKey()` |
> | 5 | `reader3.ai.activeConversation.{bookUuid}.{provider}` | localStorage | `static/ai.js` 的 `activeConversationStorageKey()` |
> | 6 | `reader3.search.library` | sessionStorage | `static/library-search.js` 的 `sessionKey()` |
> | 7 | `reader3.search.reader.{bookId}` | sessionStorage | `static/search.js` 的 `sessionKey(bookId)` |
> | 8 | `reader3-ai-panel-width` | localStorage | `templates/reader.html` 内联脚本的 `STORAGE_KEY`（AI 面板宽度） |
> | 9 | `reader3-font-settings` | localStorage | `templates/reader.html` 内联脚本的 `STORAGE_KEY`（字体设置，legacy；`static/js/epub-renderer.js` 也读它） |
>
> **前 7 个已经在用点号约定，后 2 个是短横线遗留，7 : 2。** 所以 R5 不是「照着一个孤例推广」，而是**把既定惯例写成规则、并顺手收编那 2 个遗留**——这让裁决站在多数既成事实上，而不是站在一个样本上。本节此前写的证据是「`reader3.library.rightPanelCollapsed` 是全仓库现存的唯一一个前端存储 key」，那句话是错的，已按上表更正；裁决结论不变。
>
> **两个遗留 key 的迁移归属**：都在 `templates/reader.html` 的内联脚本里，随阅读器重写改名——`reader3-ai-panel-width` 归 [WI-16](./plan-frontend-ui-refactor.md)（4B.2 阅读器外壳重写），`reader3-font-settings` 归 [WI-18](./plan-frontend-ui-refactor.md)（4B.3 阅读设置面板）。第 9 个不是纯改名：它存的是一个 `{fontSize, lineHeight}` 对象（写在 `reader.html` 内联脚本的 `saveSettings()`，读在 `static/js/epub-renderer.js` 的 `getFontSettings()`），而上表把这两个值拆成了 `reader3.reader.fontSize` 与 `reader3.reader.lineHeight` 两个 key——WI-18 要处理这个拆分，不能只换字符串。
>
> `vendor/epub.min.js` 里的 `_localforage_support_test` 是第三方库的能力探针，**不是我们的 key**，不计入上表——记在这里免得后来者重数一遍又数出 10 个。
>
> 本规格此前写的 `reader3_reading_theme`（下划线）与原型的 `r3-theme`（短横）都是各自发明的第三套，作废。DEG 横幅的会话内关闭态同规则：`sessionStorage["reader3.degrade.<状态 id>"]`。
>
> **主题值域是 `paper`，不是 `white`。** 本表此前写 `white`、D1 的现状表写「白色」，指的是同一个东西。以 `paper` 为准——这个字符串要写进 `localStorage` 和 `data-reading-theme`，不能有第二个拼法。
>
> **默认是 `auto`，不是 `paper`**（裁决见 §11-R7）。`auto` = 跟随界面明暗：light chrome 下就是白纸，dark chrome 下跟着变深。`paper` 是**绝对白**，在 dark chrome 下依然是白纸——两者在亮色下看起来一样，区别只在切暗时。这个「跟随」行为必须有自己的名字，藏进 `paper` 会让 `paper` 一个值同时表示绝对色和相对色（原型正是这么写的，见 §11-R7）。

- **五个** `.theme-option` / 两个 `.font-option` 必须带 `data-value`，用 `role="radiogroup"` + `aria-checked`，键盘方向键可切（现在是裸 `<div>`，鼠标键盘都不可用）。
- 字号/行距按钮到达边界时 `disabled`，并显示实际值。**这两条现状已经做到了**（D1 实测），本规格对它们的要求是**不许在重写中丢掉**，不是新增；连同 `localStorage["reader3-font-settings"]` 里已保存的用户值一起迁移。**「不许丢掉」需要有用例守着**：字号是 [计划](./plan-frontend-ui-refactor.md) §5.1.2 的 `FB-R13`，行距是 `FB-R13a`。
- 删除 得到今楷 / 汉仪旗黑 / 思源宋体 三项商业字体——未授权、未打包、点了没反应。

**正文栏宽（D5，一等规格项）**

| 项 | 规格 |
|---|---|
| 目标行长 | 45–75 字符（中文 22–36 全角字） |
| 实现 | `themes.override()` 注入 `max-width: 38rem; margin-inline: auto;`，`rem` 随字号联动 |
| 对齐 | `text-align: start`（现状两端对齐，窄屏产生字间空隙 rivers） |
| 左右留白 | 最小 `clamp(16px, 5vw, 64px)`，保证工具栏不压正文 |
| 验收 | 1440×900 与 390×844 两档下，任取一段测量行长均落在区间内 |

**右侧工具栏**：rail 上 **5 个** SVG 按钮——4 个面板键（目录 / 搜索 / 笔记 / AI）＋ 字体键（`Aa`）；**返回不在 rail 上，在页头**（`rd-header-back`）。**新增**：当前激活面板的按钮需要选中态（现在打开 TOC 后工具栏无任何反馈）。

> **返回为什么必须挪出这一组**（裁决 §2.1.4 C1）：本段同时要求「激活面板的按钮需要选中态」，而返回**没有激活态**——它是导航，按下即离开本页。把它留在一组带 `aria-pressed` 的按钮里，要么它得假装 `aria-pressed="false"`（撒谎），要么这组按钮的 ARIA 就只有半套。此前本段写「保留 6 个（含返回）」，与自己的下一句冲突。工具栏用 `z-index: var(--r3-z-toolbar)`，该档按 §3.5.1 定义即高于 `--r3-z-panel` 与 `--r3-z-overlay`，任何面板打开时都保持可点击。**层级关系只在 §3.5.1 定义一次，本节不复述数值。**

**面板互斥（D6）**：TOC / 笔记 / 搜索 / AI / 字体 五个面板同时只允许一个打开。`toolbar.js` 现在只处理了 search 与 ai 两个的互斥（`closeAllPanels` 只关这两个），TOC 和 notes 可以和它们叠加。统一到一个 `activePanel` 状态。

> 这不只是视觉问题：实测中 TOC 或 Notes 打开后，点击 `#reader-search-toggle` 会**超时失败**——遮罩吃掉了工具栏点击，用户必须先手动关闭当前面板。属于功能性阻断。

**面板布局模式**：`≥1280px` 面板为推挤布局（正文栏同步收窄并保持居中），`<1280px` 为覆盖式。现状在所有宽度下都是覆盖，桌面端打开目录即完全看不见正文。

**焦点管理**：面板打开时焦点移入、`Esc` 关闭并归还焦点、面板内 Tab 循环。现有 `toolbar.js` 的 `resetFocusAfterClose()` 只做了 blur，没有归还——键盘用户关闭面板后焦点掉到 body。

**翻页热区：删除，改显式按钮**（裁决见 §11-R2）。

现状 `.nav-zone-left/right` 是覆盖左右两侧的**隐形**点击区，D4 记录的问题是它在触屏上吞掉选词、而选词是标注入口。原先的规格写「`≥1024px` 保留、`<1024px` 禁用」，用视口宽度当触屏的代理——这个代理是错的（1280px 的触屏笔电照样吞选词），而且与 §7 表里「`768–1279px` 禁用」自相矛盾。

目标形态不保留隐形热区：翻页由**显式的 `‹` / `›` 按钮**承担，带 `aria-label`，`<768px` 隐藏（此档改用工具栏翻页）。原型 `reader.jsx` 的 `.page-arrow` 已经是这个形态，本条是把规格对齐到它，不是新设计。

隐形热区一旦删除，「宽度 vs 触屏」这个判定就不再需要——**没有热区可吞选词**。

**章节导航**：`Previous` / `Section N of M` / `Next` 与页内翻页热区语义不同（前者跳 spine，后者翻页）。视觉上必须区分，并在 `.nav-indicator` 旁同时显示页内进度。

**标注工具条**：7 个动作（Copy / Marker / Wavy / Underline / Delete / Add Note / Ask AI）+ 4 个颜色。文案改中文（§0）；颜色按钮补 `aria-pressed`；`Delete` 与其余动作之间加分隔，避免误触。

### 6.4 降级状态（DEG-S1–DEG-S5）

> **编号约定（2026-08-17 起生效）**：降级状态一律写作 `DEG-S1`…`DEG-S5`。加 `DEG-` 前缀是为了和 `/tdd-guardian:workflow` 的规格层级编号 `S1`–`S6` 区分开——两套编号原先都叫 `S1`，在同一份计划里同时出现会指错对象。本仓库内凡出现裸 `S1`–`S5` 且语境是降级态的，均指本表；`20260816-tech-stack-migration/` 的 GSTACK 评审原文与 `eng-review-tasks.jsonl` 保留写作当时的裸编号，不追改。

技术栈迁移引入了五条降级路径，**现状 UI 与原型里一个都没有**——原型只做了 collection 级别的 `stale`，书籍级与全局级全缺。没有 UI 就等于静默失败。

| # | 状态 | 触发 | UI 规格 | 落在哪一页 |
|---|---|---|---|---|
| **DEG-S1** | 标注 stale | `notes.json` 的指纹 ≠ 当前 spine 指纹 | 阅读器顶部横幅 + Notes 面板逐条标记。文案必须明说「标注暂停套用，**未删除**」，并给一个「查看原文摘录」入口 | 阅读器（§6.3） |
| **DEG-S2** | 索引 stale | chroma 指纹不匹配 | 书卡第**五**态（`STATUS_META` 现在只有四态）+ 搜索面板顶部「索引已过期，结果可能不全」提示条与重建按钮 | 书库（§6.2）＋ 搜索面板 |
| **DEG-S3** | pickle 回退告警 | `READER3_ALLOW_PICKLE=1` 启动 | 全局告警条（书库与阅读器都显示），点击展开未迁移书目清单 | 全局 chrome |
| **DEG-S4** | 存储格式 / 迁移进度 | `--migrate` / `--migrate-all` | 每本书卡上的 `storage_format` 角标；迁移中显示进度与失败项，失败项可单独重试 | 书库（§6.2） |
| **DEG-S5** | 多标签页写冲突 | notes 并发覆盖（乐观并发失败） | 冲突提示 + 「保留我的 / 采用远端」二选一，**不得静默丢写**。这是唯一一条会真正丢用户数据的降级 | 阅读器（§6.3） |

设计要求（五条通用）：

1. **色彩语义**：DEG-S1/DEG-S2/DEG-S4 用 `--r3-warning`，DEG-S3/DEG-S5 用 `--r3-error`；底色用同名 `-subtle`，边框用前景色本身（§3.3 已验 ≥4.5:1，不另设 border token）。**只有底色的横幅不算数**——四个淡底对承载面的实测值见 §3.3 的淡底对比度表（全部远低于 3:1），必须同时有边框或图标。一律不用 `--r3-accent`（品牌蓝），避免与普通提示混淆。
2. **可访问性**：横幅与提示条挂 `role="status"` + `aria-live="polite"`；DEG-S5 的冲突对话框用 `role="alertdialog"`，因为它需要用户决策。
3. **可关闭性**：DEG-S1/DEG-S2/DEG-S3/DEG-S4 允许本次会话内关闭（`sessionStorage`），**DEG-S5 不可关闭**——必须做出选择。
4. **testid**：五个状态各自的容器与主操作按钮都要有 testid（§4），否则 E2E 无法断言"降级可见"。
5. **朴素优先**：Phase 3 的退出门槛只要求 DEG-S1–DEG-S4 **可见**，哪怕是先落到现有 Jinja 模板的朴素横幅；Phase 4 再按本节重做。

---

## 7. 响应式

现状全站 9 条 `@media`，等同桌面专用（D4）。三档：

| 断点 | 书库 | 阅读器 |
|---|---|---|
| `≥1280px` 桌面 | 三栏全展开 | 正文居中，面板为侧栏推挤布局 |
| `768–1279px` 平板 | 右栏折叠为抽屉（已有 `#right-collapse-toggle`），左栏保留 | 面板改为覆盖式抽屉 |
| `<768px` 移动 | 单栏，左栏与右栏均为抽屉，书卡网格降为 2 列 | 工具栏移到底部；面板全屏；翻页箭头隐藏 |

> **断点数值是 canonical 的：`1280px` / `768px`。** 原型 `index.html` 原写 `1024px` / `720px`——**两个 `@media` 里的行为与上表逐条一致，只有阈值不同**（≤1024 收右栏、≤720 收左栏并降列）。已按本表把原型改为 `max-width: 1279px` / `767px`，见 §11-R1。

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
2. 对比度：正文 ≥ 4.5:1，大字 ≥ 3:1，**六组纸/墨各自验证**——四种绝对纸色（paper / sepia / green / night）＋ `auto` 在 light 与 dark chrome 下解析出的两组（sepia 与 green 底色最容易不达标）。这六组与 chrome 无关，**不乘 8**。§3.3 的四组状态色同标准，**亮色档最容易漏**——原先的 500 档在白底上只有 2.15–3.76:1，已按实测换成 700 档。
3. 键盘可达：§6.3 的 `.theme-option` / `.font-option` 现在是裸 `<div>`，完全不可聚焦——必须改 `role="radio"` + `tabindex`。
4. 动态区域：搜索结果、AI 流式输出、索引进度用 `aria-live="polite"`（`#aria-live` 已存在，扩大使用）。
5. 尊重 `prefers-reduced-motion`：面板动效降级为瞬时。**落地形式见 §3.5.3 的单点降级**（一处把三个 duration token 重定义为 `0ms`，组件不各自处理）——这一条与 §3.5.3 是同一条要求的两面，不是两套。
6. 图标按钮一律有 `aria-label`（现状 reader 工具栏用 `title`，屏幕阅读器支持不可靠）。

---

## 9. 本规格各节落在哪个阶段

阶段划分与分支编号的权威在 [`20260816-tech-stack-migration/plan-tech-stack-migration.md`](../20260816-tech-stack-migration/plan-tech-stack-migration.md) §9；本表只说明**本规格的产出**被哪个阶段消费。

| 本规格产出 | 消费阶段 |
|---|---|
| §4 `data-testid` 契约 | **Phase 0**（必须早于 Phase 1b 写 E2E，否则返工） |
| §3 token 体系 | Phase 4A.1（全站一次到位，`data-theme` 基础设施同批） |
| §6.1 设置页 | Phase 4A.2 —— 它是 Vite/TS 工具链的**试点**，属于 Phase 4A 内部，**不独立于 Phase 4** |
| §6.2 书库页 | Phase 4A.4（CSS 提取即本次重设计，不做两遍） |
| §6.0 iframe 边界 | 约束 Phase 4B.1 / 4B.2 的改动范围 |
| §6.3 阅读器外壳 | Phase 4B.2 |
| §6.3 阅读设置面板（D1）＋ 正文栏宽（D5） | Phase 4B.3 |
| §6.4 DEG-S1 / DEG-S5 | DEG-S1 → Phase 4B.2；DEG-S5 → Phase 2a（与 notes 乐观并发同批） |
| §6.4 DEG-S2 / DEG-S3 / DEG-S4 | Phase 4A.4；Phase 3 退出门槛要求它们**先以朴素形态可见** |
| §7 响应式（D4） | 随各页垂直切片一同落地，不单独成阶段 |
| §8 可访问性 | 同上，每页切片的验收项 |

---

## 10. 明确不做

- ❌ 引入 React/Vue/Svelte（与 migration plan 一致）
- ❌ 触碰 epub.js iframe 内部 DOM（§6.0）
- ❌ 打包商业中文字体（授权 + 体积）
- ❌ 重新设计 `library_classic.html`（删除）
- ❌ 移动端手势（滑动翻页、长按菜单）——本轮只保证不破坏，不新增
- ❌ 完整 i18n 框架——只做一份类型化消息表（与 plan Phase 4 一致）。该表当前只有 `zh-CN` 一个 locale（§0），加第二个 locale 是往表里加一列数据，不在本轮范围
- ❌ 界面语言切换器——只有一个 locale 时它是空操作，已从 §6.1 的「外观」分区删除

---

## 11. 裁决记录

**权威范围现已由 §2.1 划定**，本节是它之前（以及边界上）积下的逐条裁决记录。R1–R8 记于 2026-08-17，C1–C13 记于 2026-08-23（见 §2.1.4）。两批的处理方式相同：**输的一方就地改掉，不留第二份**。

| # | 事实 | 原型 | 本规格（原） | 裁决 | 依据 |
|---|---|---|---|---|---|
| **R1** | 响应式断点 | `1024` / `720` | `1280` / `768` | **规格赢** | 两个 `@media` 的**行为**与 §7 表逐条一致，分歧只在阈值。`1280` 与面板推挤模式同源；`768` 是平板／手机的通行分界 |
| **R2** | 翻页热区 | 无热区，显式 `.page-arrow` 按钮（带 `aria-label`） | 隐形 `.nav-zone`，按宽度禁用 | **原型赢** | 用视口宽度代理触屏是错的（触屏笔电照吞选词），且规格 §7 与 §6.3 自相矛盾（<1280 vs <1024）。删掉热区，判定条件一并消失 |
| **R3** | 按钮变体 | `primary`/`secondary`/`danger-solid`/`sm`/`icon` | `primary`/`danger`/`ghost`/`icon` | **合并** | `.btn-secondary` 全部声明是 `background: var(--surface)`，与基类 `.btn` 同值——**空操作**，删除；`--sm` 原型 10 处在用，规格漏了，补；`ghost` 原型散在 12 个裸类里，规格是对的，保留 |
| **R4** | 字阶 | 12 个字面量（11–26px，含 11.5/12.5/13.5） | 7 档，最小 12px | **合并** | 规格的分档结构对，但没测原型：44 处用量在 14px 以下。补 `2xs:11px` 成 8 档，其余不动，原型按 §3.4 映射表 snap |
| **R5** | 存储 key 命名 | `r3-theme` | `reader3_reading_theme` | **都输，取生产** | 生产现存 9 个前端存储 key，7 个已是点号形式，点号命名空间是既成事实。统一 `reader3.<区域>.<camelCase>`，并收编 2 个短横线遗留。**全表与迁移归属只在 §6.3 定义一次，本行不复述** |
| **R6** | 圆角值 | `6/10/16` | 「沿用 4/6/8/12」 | **原型赢** | 规格写的是**现状生产**的值，而目标形态是原型。§3.4 已改为 6/10/16 |

### 11.1 R7 —— 主题是一根轴还是两根（**已裁决 2026-08-17：两根**）

这条是核对 R5 时发现的，比 R1–R6 任何一条都深，单独走了一轮独立评审（OpenAI Codex，session `01a00ed1`）。

**冲突原貌：**

| | 本规格（原 §3.3） | 原型 |
|---|---|---|
| 轴数 | **一根**：`data-reading-theme` ∈ {unset=paper, sepia, green, night} | **两根**：`<html data-theme>` ∈ {light, dark, system} 管 app chrome；`.reader-shell[data-reading-theme]` ∈ {paper, sepia, green, night} 管纸色 |
| 挂载点 | `<html>`（`:root[...]`） | 纸色挂 `.reader-shell`，**不是 `<html>`** |
| night 与 chrome 的关系 | night 顺带重定义 chrome 的 semantic token | 互不相干：可以「chrome 亮色 ＋ 正文 night」 |
| 跟随系统 | `data-reading-theme` 未设时看 `prefers-color-scheme` | 显式第三值 `system` |

**裁决：两根轴，但两边都要改。** 最终形态写在 §3.3，摘要：

| | 结论 | 谁输了 |
|---|---|---|
| 轴数 | **两根**（原型对） | 规格 |
| 挂载点 | **两个属性都挂 `<html>`**，作用域靠选择器 `html[data-reading-theme=x] .reader-shell` | 原型（挂 `.reader-shell` 上，FOUC 时该元素不存在） |
| 纸色值 | 四种**绝对值**，另立 `auto` 表示「跟随界面」 | 原型（把「跟随」藏在 `paper` 里，`--page-bg: var(--surface)`） |
| 默认纸色 | **`auto`** | 规格（原写 `paper`；绝对白纸配 dark chrome 是刺眼的开箱体验） |
| 跨轴组合 | **全部允许，不做联动**，2×4 = 8 种 | — |
| chrome 中性色 | 取原型实测值（偏蓝 `#0b1220` / `#131c2e`…） | 规格（原写中性灰 `#242424` / `#141414`，是「night 纸色」思路的残留） |

**决定性依据不是「白天浅色界面读夜间纸」这个用例**（它是真需求，但不足以定架构），而是这三条：

1. **单轴下书库页和设置页拿不到暗色模式。** §1-D2 要修的缺陷是「暗色模式在**全站**不存在」，而单轴的开关叫 `data-reading-theme`——书库页没有正文。要么书库跟着 sepia 变米黄（荒谬），要么书库根本没有暗色（没修 D2）。单轴修不了自己声称要修的缺陷。
2. **plan 的验收标准早就是按双轴写的。** WI-10 写「三个阅读主题与全站明暗是**两个维度**」「明暗 × 三阅读主题的每一种组合」「六种组合」，FT-01 写「明暗 × 白 / 米 / 绿 / 夜 每种组合」。这些句子在单轴下不成立——单轴里「明暗」就是那根轴本身，不存在「夜间 × sepia」。spec 与 plan 各按各的模型写了半年，是双轴那一边先被当成事实用起来的。
3. **单轴已经在自己身上撞过一次死值。** 原 §3.3 有一整段注释解释「`--r3-bg` 刻意不在 night 块里定义，否则会被下面同选择器的 night 规则覆盖成死值」。需要写注释提醒自己别踩的分层，是分层错了。原型在双轴下也撞了一次同类死值（dark chrome 的 `--page-*` 被四条 reading 规则全覆盖，`index.html:96`），但那是 `paper` 相对化引起的，改成绝对值后自动消失。

**Codex 的独立结论一致**（选 B、纸色绝对化、属性都挂 `<html>`、全组合允许、iframe 用共享常量注入不反解 computed style），只在一处被推翻：它建议 `paper` 改绝对色、需要跟随时**另外新增** `auto`。本规格把 `auto` 直接定为**默认**——否则新用户在系统深色下开箱就是白纸配深界面。`auto` 的实现是「没有覆盖规则」，不是一段 JS 解析。

**遗留给实施的两条**：

- **iframe 注入必须与 CSS 同源。** 一份 TS 常量 `READING_THEMES: Record<ReadingTheme, {bg, ink, quiet, hl}>`，同时喂给样式表和 `themes.override()`。**不许**从宿主页 `getComputedStyle` 反解颜色再注进 iframe——`auto` 会让这条路径依赖 chrome 的最终解析状态，是最容易在暗色下出错的写法。
- **老用户会看到变化。** 现状生产无主题、正文恒为 `#333` 白底。默认 `auto` 意味着系统深色的用户升级后阅读器直接变深。这是 D2 要修的东西，不是回归，但要写进发布说明。迁移逻辑不为主题写任何值——**key 缺席即 `auto`**。

顺带记两条小的：原型 `prefs` 默认是 `size: 18` / `leading: 1.85`，规格 §6.3 写 17 / 1.9。**规格赢**——17 / 1.9 与现状生产显示的值一致，改默认值会让老用户的阅读版式无故位移。原型的默认 `readingTheme: "paper"` 按上面的裁决改为 `auto`。

**已裁决但尚未落到原型的**（原型仍带旧值，见其 README「已被裁决推翻」表）：R3 的 ghost 收敛、R4 的字阶 snap、以及图标改 SVG。三项都是 WI-10 / WI-11 的实施内容，目标值已由本节锁死。

### 11.2 R8 —— `Modal` 选型（**已裁决 2026-08-20：原生 `<dialog>`**）

这是本计划**唯一被 GSTACK VERDICT 点名的阻塞项**，此前一直挂在 Track D 名下写着「尚未裁决」。现裁决如下，理由完整记在这里以便复查。

| | 原生 `<dialog>` ＋ `showModal()` | `div` ＋ `role="dialog"` |
|---|---|---|
| 现有 Jinja 模板 | ✅ 5 个 `<dialog class="modal">` 已经是这个 | — |
| 原型 `components.jsx` | — | ✅ `div.overlay` ＋ `role="dialog"` |
| **裁决** | **赢** | 落选 |

**理由（五条，第 1 条是推翻性的）：**

1. **`div` 方案的唯一动机建立在一个错误前提上。** 当初选 `div` 的理由是「DEG-S5 冲突对话框必须不能被 Esc 与遮罩点击关闭」（§6.4 设计要求第 3 条：DEG-S5 不可关闭，必须做出选择），而 §5 原注以为原生 `<dialog>` 拦不住 Esc。**拦得住**：
   - Esc —— `<dialog>` 的 `cancel` 事件**是可取消的**，`dialog.addEventListener('cancel', e => e.preventDefault())` 一行即禁掉 Esc 关闭。
   - 遮罩点击 —— 原生 `<dialog>` 点 `::backdrop` **本来就不关闭**。现在满世界见到的「点遮罩关闭」是手写代码额外加上去的（比较 `event.target === dialog` 再 `close()`），**不加就没有**。

   两条要求在 `<dialog>` 上都能满足，而且是"不写代码"就满足其一。动机没了，`div` 方案就只剩成本。
2. **`showModal()` 把元素放进 top layer，脱离任何祖先的 `position` / `transform` / `filter` 包含块。** 这正好解掉 [`contracts/annotation-host-contracts.md`](./contracts/annotation-host-contracts.md) K3 记录的最高危隐患——`position: fixed` 的浮层被祖先链上的包含块制造者击穿，表现为「元素可见、位置错了」这种 E2E 照样绿的失效。前端计划 WI-14 的 K3 硬约束把 `<dialog>` ＋ `showModal()` 列为**两种默认安全的挂法之一**。`div` 方案要自己处理这件事，且处理不当不报错。
3. **四项 a11y 行为浏览器白送，`div` 方案要各写一遍并各测一遍**：焦点陷阱（Tab 不出 dialog）、兄弟节点自动 `inert`（背景不可点、不进 tab 序、对屏幕阅读器隐藏）、`::backdrop` 伪元素、以及多层 dialog 的 Esc 分层（最上层先关）。这四项每一项都是"写错了不报错、只是残疾"的类型，正好是 §8 契约里最难用 E2E 兜住的部分。
4. **顺带解掉一个 z-index 层级。** top layer 在所有 z-index 之上，Modal 因此**不占 §3.5.1 的任何一档**——9 档枚举里没有 modal 这一行不是漏写。`div` 方案则必须占一档，而且要占在 `--r3-z-toast` 之上还是之下会变成一个真问题（Toast 弹在 modal 上方还是被盖住）。
5. **支持度不构成风险。** Chrome 37（2014-08）/ Firefox 98（2022-03）/ Safari 15.4（2022-03）—— 自 2022-03 起为 Baseline widely available，`::backdrop` 与 `inert` 同期。**零 fallback、零 polyfill**。本项目是自托管应用，目标浏览器就是用户自己的现代浏览器。

**落地边界（写进实施）：**

- **只有真正的模态用 `<dialog>`** —— 需要阻断背景交互的那种：§6.1 的破坏性操作二次确认、§6.2 的 5 个模态、§6.4 的 DEG-S5 冲突对话框（后者另加 `role="alertdialog"`，见 §6.4 设计要求第 2 条）。
- **非模态弹层不用 `<dialog>`**：下拉、气泡、标注工具条、tooltip 走普通元素 ＋ `--r3-z-popover`。`<dialog>` 不带 `showModal()`（即 `show()`）也能非模态显示，但那样既拿不到 top layer 也拿不到焦点陷阱，等于只借了个标签名——不要这么用。
- **DEG-S5 的两条禁用是显式代码**，不是默认行为的副产品：`cancel` 事件 `preventDefault()`，且**不要**添加遮罩点击关闭的监听器。这两行要有注释说明它们是 §6.4 第 3 条的实现，否则后来者会当成漏写补上。
- **原型 `components.jsx` 的 `Modal` 改为原生 `<dialog>`**，与 R3 / R4 / 图标改 SVG 同属"已裁决但尚未落到原型"，归 WI-10 / WI-11。
