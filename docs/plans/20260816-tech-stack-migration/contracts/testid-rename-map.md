# testid 新旧对照表（Phase 0.5 产出）

> **权威范围**：本文是 0.5 批量改名的**唯一**新旧对照记录。
> 命名方案本身（前缀、`{page}-{region}-{element}` 格式、字面量规则）定义在
> [`spec-frontend-design.md` §4](../../20260817-frontend-ui-refactor/spec-frontend-design.md)，本文不重述；
> canonical 正则定义在 [`plan-tech-stack-migration.md` §6 步骤 0.5 的代码块](../plan-tech-stack-migration.md)，本文不重述。
> 本文只回答一个问题：**原型里那个旧名，现在叫什么。**

改名已落地于 `designs/reader-pro-next/`（`app.jsx` / `components.jsx` / `reader.jsx` / `settings.jsx`）。
生产模板 `src/reader3_app/web/templates/*.html` 与生成 DOM 侧的回贴**也已完成**（2026-08-23，随 007 于
2026-08-24 合入 `master`）：模板侧现有 126 个唯一 testid，反向新造为 0，两条 lint 违规数归零。迁移计划
§7 Phase 0 的「testid 在原型与模板两侧一致」一条**已满足**。

---

## 1. 计数对账：为什么是 138，不是 134

规格 §4.1 与迁移计划 §6 都写「134 个唯一 testid，0 个合规」。**落地实测是 138。**
差的 4 个不是新增的元素，是**统计口径**的差：原先的清点只扫了 `data-testid="…"` 属性字面量，
漏掉了 `Sheet` 组件的 `testId="…"` **prop** 形式——它在组件内部转成 `data-testid`，
在浏览器里同样是一个 testid，只是源码里长得不一样。

| 分类 | 数量 | 说明 |
|---|---|---|
| `data-testid="…"` 字面量 | 119 | §2 逐条列出 |
| 跨页共享 chrome（组件内一处，三页各渲染一次） | 15 | §3；改名后一名变三名 |
| `Sheet` 的 `testId="…"` prop | 4 | §4；**原 134 计数漏掉的就是这 4 个** |
| **合计** | **138** | 改名后全部匹配 canonical 正则 |

那 24 个带 `reader-` / `library-` 前缀、形似合规实则不合规的（规格 §4.1 的警告项），
落在 **23 个字面量 ＋ 1 个 `testId` prop（`reader-search-panel`）**。
也就是说 24 这个数字一直是对的，134 这个数字才是漏的——两处口径原本就不一致，本次改名把它对齐到 138。

改名后实测：**唯一 testid 名 221 个，不合规 0 个。**
221 > 138 是因为 15 个共享 chrome 一名裂成三名（+30），以及表达式站点改成静态映射表后
每个枚举值都成了一个独立的字面量（如 `rd-pref-theme-auto` … `rd-pref-theme-night` 五个）。

---

## 2. 字面量对照表（119 条）

⚠️ 一列标 ⚠️ 的，是规格 §4.1 点名的「带 `reader-` / `library-` 前缀、形似合规」那一类。

### 2.1 `app.jsx` —— 书库外壳（22 条）

| 旧名 | 新名 | |
|---|---|---|
| `library-shell` | `lib-shell` | ⚠️ |
| `library-main` | `lib-main` | ⚠️ |
| `library-filter` | `lib-toolbar-filter` | ⚠️ |
| `library-sort` | `lib-toolbar-sort` | ⚠️ |
| `view-grid` | `lib-toolbar-view-grid` |  |
| `view-list` | `lib-toolbar-view-list` |  |
| `toggle-selection` | `lib-toolbar-select-mode` |  |
| `bulk-bar` | `lib-bulk-bar` |  |
| `select-all` | `lib-bulk-select-all` |  |
| `select-none` | `lib-bulk-select-none` |  |
| `bulk-collection` | `lib-bulk-collection` |  |
| `bulk-index` | `lib-bulk-index` |  |
| `library-empty` | `lib-empty` | ⚠️ |
| `filter-empty` | `lib-filter-empty` |  |
| `book-grid` | `lib-book-grid` |  |
| `collection-name-input` | `lib-collection-name-input` |  |
| `collection-rename-input` | `lib-collection-rename-input` |  |
| `add-to-collection-select` | `lib-add-to-collection-select` |  |
| `index-errors` | `lib-index-errors` |  |
| `retry-index` | `lib-index-retry` |  |
| `dropzone` | `lib-add-dropzone` |  |
| `choose-files` | `lib-add-choose-files` |  |

### 2.2 `components.jsx` —— 书库专属组件（31 条）

| 旧名 | 新名 | |
|---|---|---|
| `collection-menu` | `lib-sidebar-collection-menu` |  |
| `library-sidebar` | `lib-sidebar` | ⚠️ |
| `scope-all` | `lib-sidebar-scope-all` |  |
| `scope-epub` | `lib-sidebar-scope-epub` |  |
| `scope-pdf` | `lib-sidebar-scope-pdf` |  |
| `create-collection` | `lib-sidebar-create-collection` |  |
| `book-table` | `lib-book-table` |  |
| `panel-dashboard` | `lib-panel-dashboard` |  |
| `refresh-stats` | `lib-panel-refresh-stats` |  |
| `index-remaining` | `lib-panel-index-remaining` |  |
| `open-index-errors` | `lib-panel-open-index-errors` |  |
| `panel-chat` | `lib-panel-chat` |  |
| `chat-scope` | `lib-chat-scope` |  |
| `chat-thread` | `lib-chat-thread` |  |
| `chat-input` | `lib-chat-input` |  |
| `chat-stop` | `lib-chat-stop` |  |
| `chat-send` | `lib-chat-send` |  |
| `msg-streaming` | `lib-chat-msg-streaming` |  |
| `panel-search` | `lib-panel-search` |  |
| `search-clear` | `lib-search-clear` |  |
| `library-search-input` | `lib-search-input` | ⚠️ |
| `library-search-mode` | `lib-search-mode` | ⚠️ |
| `library-search-sort` | `lib-search-sort` | ⚠️ |
| `library-search-case` | `lib-search-case` | ⚠️ |
| `search-index-warning` | `lib-search-index-warning` |  |
| `library-search-results` | `lib-search-results` | ⚠️ |
| `search-hit` | `lib-search-hit` |  |
| `insights-collapsed` | `lib-insights-collapsed` |  |
| `expand-insights` | `lib-insights-expand` |  |
| `insights` | `lib-insights` |  |
| `collapse-insights` | `lib-insights-collapse` |  |

### 2.3 `reader.jsx` —— 阅读器（55 条）

| 旧名 | 新名 | |
|---|---|---|
| `sheet-resizer` | `rd-sheet-resizer` |  |
| `sheet-close` | `rd-sheet-close` |  |
| `toc-filter` | `rd-toc-filter` |  |
| `notes-review` | `rd-notes-review` |  |
| `notes-export` | `rd-notes-export` |  |
| `notes-empty` | `rd-notes-empty` |  |
| `notes-copy-all` | `rd-notes-copy-all` |  |
| `review-list` | `rd-notes-review-list` |  |
| `reader-index-status` | `rd-search-index-status` | ⚠️ |
| `index-book` | `rd-search-index-book` |  |
| `reader-search-input` | `rd-search-input` | ⚠️ |
| `reader-search-mode` | `rd-search-mode` | ⚠️ |
| `search-loading` | `rd-search-loading` |  |
| `search-failed` | `rd-search-failed` |  |
| `search-empty` | `rd-search-empty` |  |
| `reader-search-results` | `rd-search-results` | ⚠️ |
| `reader-search-hit` | `rd-search-hit` | ⚠️ |
| `ai-history` | `rd-ai-history` |  |
| `ai-new` | `rd-ai-new` |  |
| `ai-clear` | `rd-ai-clear` |  |
| `ai-export` | `rd-ai-export` |  |
| `ai-export-menu` | `rd-ai-export-menu` |  |
| `ai-history-list` | `rd-ai-history-list` |  |
| `ai-empty` | `rd-ai-empty` |  |
| `ai-thread` | `rd-ai-thread` |  |
| `ai-streaming` | `rd-ai-streaming` |  |
| `ai-input` | `rd-ai-input` |  |
| `ai-stop` | `rd-ai-stop` |  |
| `ai-send` | `rd-ai-send` |  |
| `font-popover` | `rd-font-popover` |  |
| `pref-size` | `rd-pref-size` |  |
| `pref-leading` | `rd-pref-leading` |  |
| `annotation-toolbar` | `rd-anno-toolbar` |  |
| `anno-copy` | `rd-anno-copy` |  |
| `anno-note` | `rd-anno-note` |  |
| `anno-ask` | `rd-anno-ask` |  |
| `anno-delete` | `rd-anno-delete` |  |
| `note-editor-quote` | `rd-note-editor-quote` |  |
| `note-editor-input` | `rd-note-editor-input` |  |
| `reader-error` | `rd-error` | ⚠️ |
| `reprocess-book` | `rd-error-reprocess` |  |
| `reader-shell` | `rd-shell` | ⚠️ |
| `reader-header` | `rd-header` | ⚠️ |
| `reader-back` | `rd-header-back` | ⚠️ |
| `page-indicator` | `rd-page-indicator` |  |
| `reader-stage` | `rd-stage` | ⚠️ |
| `page-prev` | `rd-page-prev` |  |
| `reader-viewport` | `rd-viewport` | ⚠️ |
| `page-next` | `rd-page-next` |  |
| `chapter-nav` | `rd-chapter-nav` |  |
| `chapter-prev` | `rd-chapter-prev` |  |
| `chapter-count` | `rd-chapter-count` |  |
| `chapter-next` | `rd-chapter-next` |  |
| `reader-rail` | `rd-rail` | ⚠️ |
| `rail-font` | `rd-rail-font` |  |

### 2.4 `settings.jsx` —— 设置页（11 条）

| 旧名 | 新名 | |
|---|---|---|
| `settings-screen` | `set-screen` |  |
| `provider-refresh-models` | `set-provider-refresh-models` |  |
| `ollama-hint` | `set-provider-ollama-hint` |  |
| `rag-chunks` | `set-rag-chunks` |  |
| `rag-context` | `set-rag-context` |  |
| `rag-embedding` | `set-rag-embedding` |  |
| `data-reindex` | `set-data-reindex` |  |
| `data-conversations` | `set-data-conversations` |  |
| `data-cache` | `set-data-cache` |  |
| `export-json` | `set-export-json` |  |
| `export-settings` | `set-export-settings` |  |

---

## 3. 跨页共享 chrome（15 条 → 45 个新名）

`TopBar` / `Modal` / `ConfirmModal` / `LiveRegion` 这四个组件在书库、阅读器、设置三页各渲染一次，
而命名方案只有 `lib-` / `rd-` / `set-` 三个前缀，**没有「共享」这一档**。

裁决（2026-08-23）：**按宿主页前缀**。组件内部不写死 testid，调用点传 `page` prop，
组件从 `components.jsx` 的静态表 `SHARED_TESTIDS` 里取。canonical 正则不动。
表里全是字符串字面量，命名 lint 扫得到、仓库里 grep 得到——正是规格 §4 规则 5 说的「改静态映射表」。

`-` 表示该组件在那一页不渲染这个元素（例如「Back to Library」只在设置页有）。

| 旧名（组件内写死） | 书库 | 阅读器 | 设置 |
|---|---|---|---|
| `live-region` | `lib-live-region` | `rd-live-region` | `set-live-region` |
| `brand` | `lib-brand` | `rd-brand` | `set-brand` |
| `theme-toggle` | `lib-theme-toggle` | `rd-theme-toggle` | `set-theme-toggle` |
| `topbar` | `lib-topbar` | `rd-topbar` | `set-topbar` |
| `mobile-menu` | `lib-topbar-mobile-menu` | — | — |
| `nav-library` | `lib-topbar-nav-library` | — | `set-topbar-nav-library` |
| `nav-settings` | `lib-topbar-nav-settings` | — | `set-topbar-nav-settings` |
| `mobile-insights` | `lib-topbar-mobile-insights` | — | — |
| `add-books` | `lib-topbar-add-books` | — | — |
| `back-to-library` | — | — | `set-topbar-back-to-library` |
| `modal` | `lib-modal` | `rd-modal` | `set-modal` |
| `modal-close` | `lib-modal-close` | `rd-modal-close` | `set-modal-close` |
| `modal-cancel` | `lib-modal-cancel` | `rd-modal-cancel` | `set-modal-cancel` |
| `modal-primary` | `lib-modal-primary` | `rd-modal-primary` | `set-modal-primary` |
| `confirm-body` | `lib-confirm-body` | `rd-confirm-body` | `set-confirm-body` |

---

## 4. `Sheet` 的 `testId` prop（4 条）

`Sheet`（reader.jsx:190）把 `testId` prop 透传成 `data-testid`。源码里是 prop 不是属性，
所以只扫 `data-testid=` 的清点看不见它们。**命名 lint 必须同时扫 `testId="…"`。**

| 旧名 | 新名 | 调用点 | |
|---|---|---|---|
| `toc-panel` | `rd-toc-panel` | reader.jsx | |
| `notes-panel` | `rd-notes-panel` | reader.jsx | |
| `reader-search-panel` | `rd-search-panel` | reader.jsx | ⚠️ |
| `ai-panel` | `rd-ai-panel` | reader.jsx | |

---

## 5. 表达式站点：26 处，两种处理

规格 §4 规则 5 禁止拼接 testid。原型里有 26 处表达式形式的 `data-testid={…}`。
按**取值集合是否有界**分两类处理——这是本次改名新增的约定，已回写进规格 §4 规则 5。

### 5.1 取值有界（枚举）→ 静态映射表

值集合写死在源码里，逐个枚举成字面量，放进一张 `const` 表，`data-testid={表[key]}`。
约定：**每张这种表的标识符里都带 `TESTID`**，命名 lint 靠这个约定找到表内的字面量。

| 表 | 文件 | 枚举值 → testid |
|---|---|---|
| `SHARED_TESTIDS` | components.jsx:68 | 见 §3 |
| `LIB_BOOK_STATUS_TESTID` | components.jsx:343 | `not_indexed` / `indexing` / `indexed` / `error` → `lib-book-status-*` |
| `LIB_CHAT_MSG_TESTID` | components.jsx:350 | `user` / `assistant` → `lib-chat-msg-*` |
| `LIB_PANEL_TAB_TESTID` | components.jsx:355 | `dashboard` / `chat` / `search` → `lib-panel-tab-*` |
| `RD_ANNO_TYPE_TESTID` | reader.jsx:53 | `marker` / `wavy` / `underline` → `rd-anno-type-*` |
| `RD_ANNO_COLOR_TESTID` | reader.jsx:59 | `yellow` / `green` / `pink` / `blue` → `rd-anno-color-*` |
| `RD_RAIL_TESTID` | reader.jsx:66 | `toc` / `search` / `notes` / `ai` → `rd-rail-*` |
| `RD_AI_QUICK_TESTID` | reader.jsx:73 | `summary` / `highlights` / `background` → `rd-ai-quick-*` |
| `RD_PREF_FONT_TESTID` | reader.jsx:79 | `system` / `kai` / `hei` / `song` → `rd-pref-font-*` |
| `RD_PREF_THEME_TESTID` | reader.jsx:86 | `auto` / `paper` / `sepia` / `green` / `night` → `rd-pref-theme-*` |

被这条替换掉的旧写法，典型是 `data-testid={"status-" + props.status}`（规格 §4 规则 5 点名的那个）。

### 5.2 取值无界（用户数据 id）→ 字面量 testid ＋ 另一个 `data-*` 携带 id

书、集合、笔记、会话、章节、provider 的 id 来自数据，不能枚举。
这类元素给一个**固定的字面量 testid**（同类元素共享），再用**另一个** `data-*` 属性携带 id。
E2E 定位写作 `[data-testid="lib-book-card"][data-book-id="…"]`——
选择器 lint 允许，因为它没用 class、没用 `nth-child`、没用层级结构。

| 元素 | testid（字面量） | 携带 id 的属性 | 位置 |
|---|---|---|---|
| 集合行 | `lib-sidebar-collection` | `data-collection-id` | components.jsx:262 |
| 集合行菜单开关 | `lib-sidebar-collection-menu-toggle` | `data-collection-id` | components.jsx:273 |
| 集合行菜单 | `lib-sidebar-collection-menu` | `data-collection-id` | components.jsx:280 |
| 书卡（网格） | `lib-book-card` | `data-book-id` | components.jsx:403 |
| 书行（列表） | `lib-book-row` | `data-book-id` | components.jsx:449 |
| 书库聊天引用 | `lib-chat-citation` | `data-section` | components.jsx:572 |
| 搜索结果展开 | `lib-search-show-more` | `data-book-id` | components.jsx:654 |
| 目录行 | `rd-toc-row` | `data-section` | reader.jsx:242 |
| 笔记条目 / 跳转 / 删除 | `rd-notes-item` / `rd-notes-jump` / `rd-notes-delete` | `data-note-id` | reader.jsx:305–309 |
| 会话条目 | `rd-ai-conversation` | `data-conversation-id` | reader.jsx:477 |
| 阅读器 AI 引用 | `rd-ai-citation` | `data-section` | reader.jsx:506 |
| 标注 span | `rd-anno-span` | `data-anno-id` | reader.jsx:957 |
| provider 卡片及其 6 个控件 ＋ 2 处结果 | `set-provider-card` / `-toggle` / `-model` / `-url` / `-key` / `-save` / `-test` / `-result` | `data-provider` | settings.jsx:24–80 |

`Toggle`（components.jsx:130–131）除既有的 `data-testid` 透传外，新增 `data-provider` 透传，
供 §5.2 的 provider 开关使用。

---

## 6. 命名 lint 要按这张表怎么扫

（lint 实现见 `scripts/lint_testid_naming.py`；本节只记它必须覆盖的形态，避免实现漏掉。）

1. `data-testid="字面量"` —— 值必须匹配 canonical 正则。
2. `testId="字面量"` —— 同上（§4 的四个就是从这里漏掉的）。
3. 标识符含 `TESTID` 的 `const` 表内的字符串字面量 —— 同上（§5.1 的十张表）。
4. `data-testid={表达式}` —— 表达式内**不得**出现 `+` 或模板字面量。这是规则 5 的机器化形式。
5. 那 24 个带 `reader-` / `library-` 前缀的旧名要被判为**不合规**——正则天然做到（`reader-` 不在
   `lib|rd|set` 里），但 lint 的自述与测试用例里要显式点名，防止后来者以为它们是白名单。

---

## 7. 与其他文档的关系

| 文档 | 它定义什么 | 本文不重述 |
|---|---|---|
| [`spec-frontend-design.md` §4 / §4.1](../../20260817-frontend-ui-refactor/spec-frontend-design.md) | 前缀方案、格式、五条规则、24 个危险项的警告 | ✔ |
| [`plan-tech-stack-migration.md` §6 步骤 0.5](../plan-tech-stack-migration.md) | canonical 正则、两条 lint 的分工、Phase 0 退出条件 | ✔ |
| [`tasks/007-hygiene-and-contracts.md`](../tasks/007-hygiene-and-contracts.md) | 0.5 的验收 | ✔ |
| 本文 | **旧名 → 新名的逐条映射**，及表达式站点的处理方式 | — |


---

## 8. 回贴到现有实现

前七节讲的是**原型这一侧**的名字。0.5 的验收要求「testid 在原型与模板两侧一致」，所以这一节
记录另一侧：221 个原型名里哪些回贴到了现有的 Jinja 模板与生成 DOM 的 JS，哪些贴不上、为什么。

### 8.1 覆盖清单

表里数的是**唯一名字**，不是属性个数——`data-modal` / `data-sheet` 那几组同名元素各占一个名字
（见 §8.2）。属性个数：library.html 63、reader.html 67、settings.html 6。

| 文件 | 回贴的 testid 数 | 性质 |
|---|---:|---|
| `web/templates/library.html` | 54 | 静态标记 |
| `web/templates/reader.html` | 66 | 静态标记 |
| `web/templates/settings.html` | 6 | 静态标记 |
| `web/static/settings.js` | 9 | 生成 DOM（provider 卡片模板串） |
| `web/static/library.js` | 5 | 生成 DOM（索引状态药丸 ＋ 分组行） |
| `web/static/search.js` | 4 | 生成 DOM（阅读器内搜索状态与命中） |
| `web/static/library-search.js` | 2 | 生成 DOM（跨书命中 ＋ Show more） |
| `web/static/library-chat.js` | 2 | 生成 DOM（消息角色） |
| `web/static/ai.js` | 2 | 生成 DOM（会话历史行 ＋ 引用） |
| `web/static/js/annotations.js` | 1 | 生成 DOM（`<mark>`） |
| `web/static/js/notes-panel.js` | 2 | 生成 DOM（空态 ＋ 笔记条目） |
| **合计（去重）** | **152 / 221** | — |

**反向为 0**：现有实现里出现的 152 个 testid，全部是原型里已有的名字，没有一个是就地发明的。
这条比「152/221」更重要——它是「两侧一致」的实质含义。剩下的 69 个见 §8.3。

生成 DOM 里的 testid 同样只写字面量。有界枚举照 §5.1 落成静态映射表，identifier 含 `TESTID`：
`library.js` 的 `LIB_BOOK_STATUS_TESTID`、`library-chat.js` 的 `LIB_CHAT_MSG_TESTID`，两者与
`components.jsx` 里的同名表逐键对齐。

### 8.2 判别位：`data-modal` / `data-sheet` / `data-file-href`

原型任一时刻只挂一个 Modal、一个 Sheet；现有模板把四个 `<dialog>` 和四个抽屉**常驻 DOM**。
于是 `lib-modal-primary`、`rd-sheet-close` 这类名字在旧模板里会命中多个元素，Playwright 的
strict 模式会直接报错。做法与 §5.2 无界 id 那一行同构——testid 保持字面量，判别位另开
一个 `data-*`：

| 判别位 | 用在哪 | 取值 | E2E 写法 |
|---|---|---|---|
| `data-modal` | `Modal` / `ConfirmModal` 的外框、关闭、取消、主按钮、confirm 正文 | `create-collection`、`add-books`、`note-editor`… | `[data-testid="lib-modal-primary"][data-modal="create-collection"]` |
| `data-sheet` | `Sheet` 的 resizer 与关闭按钮 | `rd-toc-panel`、`rd-search-panel`… 即 Sheet 自己的 testid | `[data-testid="rd-sheet-close"][data-sheet="rd-ai-panel"]` |

两个判别位在**原型与模板两侧都加**，E2E 的选择器在迁移前后一字不变。它们不违反设计规格
§4 规则 2：`data-*` 属性选择器既不是 class、不是 `nth-child`、也不是层级结构选择器。

一处**名字对齐**：原型原来写 `data-anno-id`，生产的 `annotations.js` 一直用
`data-annotation-id`。改原型（1 处）而不是改生产代码。

一处**判别位两侧不同，登记在案**：`rd-toc-row` 在原型上配 `data-section`（章节序号），旧模板的
`render_toc` 宏配的是既有的 `data-file-href`（文件名）。旧 TOC 结构里拿不到 spine 序号，硬造一个
会是假的。testid 本身两侧一致，判别位等 WI-14 用 TS 阅读器替掉这个宏时统一；在那之前，针对模板
的 E2E 写 `[data-testid="rd-toc-row"][data-file-href="…"]`（选择器 lint 放行，它只要求每一段都是
`data-*` 且至少有一个 `data-testid`）。

### 8.3 贴不上的 69 个：原型有、旧 UI 没有

绝大多数是**新设计新增的元素**，不是漏贴。旧 UI 里根本没有这个东西，凭空造一个只为承接 testid，
既是白做也会误导 E2E。它们由 013 / 014 建出来时一并带上名字。按页分：

- **三页共有的 chrome（旧 UI 没有）**：`{lib,rd,set}-topbar-*`、`{lib,rd,set}-theme-toggle`、
  `rd-header`、`rd-brand`、`set-brand`、`rd-live-region`、`set-live-region`、
  `{lib,rd,set}-confirm-body`、`{rd,set}-modal*`。书库的 `lib-live-region` 已有，另两页没有。
- **书库**：`lib-add-dropzone`、`lib-add-choose-files`（旧「添加书籍」弹层不是拖拽上传）、
  `lib-collection-rename-input`（旧 UI 没有重命名）、`lib-filter-empty`、`lib-insights-collapsed`、
  `lib-insights-expand`、`lib-index-retry`、`lib-panel-index-remaining`、
  `lib-panel-open-index-errors`、`lib-search-index-warning`、`lib-chat-citation`
  （旧书库对话不渲染引用）、`lib-chat-msg-streaming`（旧实现直接往助手消息节点里追加，没有独立的流式节点）。
- **阅读器**：`rd-ai-empty`、`rd-ai-streaming`（同上）、`rd-ai-history`（旧面板的会话列表常驻，
  没有开合按钮，只有 `rd-ai-history-list`）、`rd-ai-quick-*`（旧 UI 没有快捷追问）、
  `rd-note-editor-quote`、`rd-notes-review-list`、`rd-notes-export`、`rd-error-reprocess`、
  `rd-search-index-book`（旧搜索抽屉只有索引状态文字，没有「建索引」按钮）。
- **设置页**：`set-rag-*`、`set-data-reindex`、`set-export-json`、`set-provider-ollama-hint`。

三处是**形态不同**而非缺失，单列出来免得后来者以为是漏贴：

| 原型 | 旧 UI | 为什么不硬贴 |
|---|---|---|
| `lib-toolbar-view-grid` ＋ `lib-toolbar-view-list`（两个按钮） | `#view-toggle-btn` 一个切换按钮 | 一个元素挂不了两个 testid；挂其中一个会让另一个的 E2E 永远选不到 |
| `lib-sidebar-collection-menu[-toggle]`（菜单） | 分组行上常驻的 Clean / Delete 迷你按钮 | 交互形态不同，E2E 步骤不可能一样 |
| `rd-ai-export-menu`（一组按钮） | `#reader-ai-export-format` 一个 `<select>` | 同上：click 与 select 不是一回事 |

还有两个**枚举缺项**：`rd-pref-theme-auto`（旧 UI 只有白/黄/护眼/夜间四档，没有跟随系统）；
`lib-book-status-*` 少了 loading / unknown 两态（原型没有对应元素），故 `library.js` 在这两态下
`removeAttribute("data-testid")`，而不是造名字。

`rd-notes-jump` / `rd-notes-delete` 也在缺失名单里：旧笔记条目整块可点，没有拆出跳转与删除两个
按钮。这条与上表同类。

### 8.4 `library_classic.html` 不回贴

按设计规格 §4.1，Classic 书库会随 004 之后的 UI 一起删掉。给要删的元素发 testid 是白拿，
所以这个模板一个都不贴——命名 lint 仍然扫它（贴了就得合规），只是它现在是 0 条。
