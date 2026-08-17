# reader-pro-next 与现有实现的功能对齐审计

- 新 UI：`designs/reader-pro-next/`（index.html + data.jsx + components.jsx + **reader.jsx** + **settings.jsx** + app.jsx，React 18 + 浏览器内 Babel）
- 基线：`designs/reader-pro-next/spec/reader-pro-spec.md`（第 3–6 章组件与逐屏合同）
- 验证方式：源文件全文通读 + 在 `http://127.0.0.1:8125` 起静态服务后于 1440×900 与 390×844 实测

> **本文档有两轮。** §1–§5 是 2026-08-15 第一轮审计的原始记录，逐项状态为**当时**的结论，保留以备追溯。产品方于 2026-08-16 拍板了 §6 里的五个决策并要求补齐其余缺口；第二轮的补齐结果与实测证据见下面的 **§0 补齐状态总表**，与 §1–§5 冲突时以 §0 为准。§6 已改写为收口清单。

第一轮结论：信息架构与视觉层已经对齐，但交互深度只覆盖了旧 UI 的骨架；批注系统、AI 面板的会话能力、Classic 回退三块整块缺失。

第二轮结论：**P0 与 P1 全部关闭，五项决策全部落地并实测通过；剩余项都是原型形态的固有边界（无真实后端、无 epub.js iframe），不构成迁移阻塞。**

图例：✅ 已对齐 ／ 🟡 部分（有壳无里）／ ❌ 缺失 ／ ⭐ 新 UI 修复了旧实现的缺口 ／ ⚠️ 相对旧实现的倒退

---

## 0. 补齐状态总表（2026-08-16 第二轮）

### 0.1 五项产品决策的落地

| # | 决策 | 落地方式 | 实测证据 |
|---|---|---|---|
| D-1 | 保留横向分页 | `usePagination`（`reader.jsx`）用 CSS 多列复刻 epub.js：`column-width = viewport 宽`、`column-gap = 64`、`column-fill: auto`，外层 `overflow: hidden`，靠 `translateX(-page × (pageW + gap))` 翻页；页数 = `round((scrollWidth + gap) / (pageW + gap))` | `flowW 2480 = 1208 + 64 + 1208` → 恰好 2 页；`page-next` 产生 `translateX(-1272px)`，指示器 `2 / 2` |
| D-2 | 英文为主 | 全原型英文，`<html lang="en">`；已同步回写 spec §0.3 与迁移计划 §7.5 | — |
| D-3 | 做深色模式 + 阅读主题 | 两级：`:root[data-theme]`（light/dark/system 三态循环，glyph ☀/☾/◐，落 `localStorage`）+ 独立 `data-reading-theme`（**auto**/paper/sepia/green/night，2026-08-17 裁决 R7 后同挂 `<html>`、四种纸色改绝对值、默认 `auto`；契约见设计规格 §3.3）与 `[data-reading-font]`（system/kai/hei/song）只作用于正文 | 切 dark 后 `body` → `rgb(11,18,32)`、卡片 → `rgb(19,28,46)`；切 sepia 后正文 → `rgb(246,236,216)`；song 生效为 Source Han Serif SC |
| D-4 | 废弃 Classic | 原型不含 Classic 屏；spec §3.3/§4.2/§6.6、G-02、G-08 与截图 `11-library-classic-*` 转历史记录 | — |
| D-5 | 主色 `#3b82f6` | 取代 `#ff6b00` 及其 hover/light/muted 派生值 | — |

### 0.2 第一轮缺口的关闭情况

| 原缺口 | 现状 | 落点与证据 |
|---|---|---|
| 批注系统整套（P0-1） | ✅ | `AnnotationToolbar`（Copy/Marker/Wavy/Underline/Add Note/Ask AI/Delete + 4 色点）、`NoteEditor`；4 类型 × 4 色齐全。**锚定用 `{paragraph, start, end}` 字符偏移，不用 DOM Range** —— `Range.surroundContents()` 跨元素会抛错、重叠批注会互相破坏；渲染时按所有边界切分段落文本重建。实测选中文字后工具条 6 个按钮 + 4 个色点可见，施加绿色 marker 后 live region 播报 `Marker applied` |
| Notes 面板实态（P0-2） | ✅ | 按 chapter 分组（Map）、`Copy all · N` 真实计数、逐条 Go to / Delete、Export。`Review book` 不再是死控件，接了 Review modal。实测 3 组 / 4 条 |
| `data-testid` 契约（P0-3） | ✅ | 三屏关键节点全覆盖，从 0 处到 Library 单屏 43 处 |
| Settings API key + masked（P0-4） | ✅ | 4 个云 provider 各有 `type="password"` 字段；已配置时 placeholder 为 `•••••••••••••• (stored, hidden)`，**value 永远只含本次输入**，不回显服务端 key（§7.3） |
| 焦点陷阱与焦点归还（P0-5） | ✅ | `useFocusTrap` 统一给 `Modal` / `ConfirmModal` / `Sheet`：Tab 循环、Escape、卸载时把焦点还给触发控件 |
| AI 面板会话能力（P1-6） | ✅ | History（5 条）/ New chat / Clear（带确认）/ Stop / 可跳转的 RAG 引用 / Export MD·TXT·JSON（Blob）/ 宽度可拖 320–800 默认 546（含键盘调节）。实测默认 546px，2 个引用，3 个快捷动作 |
| 破坏性操作二次确认（P1-7） | ✅ | Settings Data 区三个按钮全部走 `ConfirmModal`；`(IndexedDB)` 与 `(no keys)` 文案已恢复 |
| 搜索补齐（P1-8） | ✅ | Library：Case 复选框、按 book 分组、`Show more` 3→10。实测 2 组 6 条 → 9 条，6 处 `<mark>`。Reader：未索引横幅 + `Index book` 入口，420ms debounce，`Searching…` / `Search failed` / `No results found for "{query}"` 三态实测可达 |
| Book card 四态 + List 6 列（P1-9） | ✅ | `STATUS_META` 四态（Not indexed/Indexing…/Indexed/Index error）；List 恰好 6 列。`BookCard` 改为 `role="button"`（关闭 §5 的语义问题） |
| 章节导航（P1-10） | ✅ | 恢复 `Previous` / `Section N of M` / `Next` 与首尾禁用态。实测：连点 12 次 `chapter-prev` → `Section 1 of 32` 且 `Previous` 禁用；连点 40 次 `chapter-next` → `Section 32 of 32` 且 `Next` 禁用 |
| Escape 分层关闭（P1-11） | ✅ | 按 §5.3 顺序：note editor → 选区工具条 → 字号面板 → 侧面板 |
| Index errors dialog | ✅ | 已补，数据带 `at` 时间戳 |
| 右栏桌面可收起 | ✅ | `InsightsPanel` 有 collapse/expand |
| Chat scope 的产品边界 | ✅ | 恢复 `All books — Coming soon` / `Collection — Coming soon` 两个 disabled 选项 |
| 集合管理 | ✅ | 创建 / 重命名 / 删除 / 清理失效 book ID（`Remove N missing books` + `stale-dot`）全部接上确认流 |
| TOC 多级 | ✅ | mock 数据改为真实 depth 0/1/2，19 项中 11 项位于 depth 1 |
| EPUB 缺失错误块 | ✅ | `?state=epub-missing` 可复现该屏 |
| Ollama 专属项 | ✅ | `Refresh models` 收回为 Ollama 独有；补本地安装提示；`Enabled`/`Disabled` 状态文字不再自相矛盾，且旁边是真 `role="switch"` |

### 0.3 第二轮实测中发现并修复的新缺陷

这三个是补齐过程中新写代码自身的问题，不在第一轮清单里：

| 缺陷 | 成因 | 修复 |
|---|---|---|
| 同一 tick 内连点翻页/换章只前进一步 | 事件处理器闭包捕获的是**渲染时**的 `page` / `chapterIndex`，一轮 React 渲染前的多次点击读到同一个旧值 | `usePagination` 与 `ReaderScreen` 各维护同步更新的 `pageRef` / `pagesRef` / `chapterRef`，翻页与换章一律读 ref |
| 快速连点跨章会一次跳两章 | 换章后新章的页数要等重新测量才知道，同 tick 内的下一次翻页仍在用旧章的 `pages` | 加 `staleRef` 锁：章节变化时置位，`measure()` 完成后清除；置位期间 `turn()` 直接返回 |
| 向前翻页跨章后落在新章第 1 页，导致**永远读不到上一章的内容** | 换章一律 reset 到 page 0 | 加 `landAtEndRef`：向前跨章时置位，`measure()` 据此落到 `pages - 1`。实测 Section 10 p1 → 上一页 → Section 9 **p2/2** → 上一页 → Section 9 p1/2，前后翻页完全对称 |

### 0.4 仍未关闭（均为原型固有边界，非阻塞）

| 项 | 说明 |
|---|---|
| 批量索引 `beforeunload` 保护与中断标记 | 原型无真实索引任务；规格里需保留这条状态，迁移时实现 |
| epub.js iframe 内的批注呈现约束 | 原型用普通 DOM 段落验证锚定算法与视觉；真实实现要把同一套字符偏移锚定搬进 iframe，`themes.override` 只改 CSS 变量、不改 DOM 结构 |
| SSE 流式、真实检索与真实 provider 连通 | 全部为 mock，属预期 |
| 端口硬编码 G-15 | `server.py:2407`，与原型无关，仍挂在迁移计划 §7.4b |

---

## 1. 新 UI 确实修好的旧缺口（实测确认）

| 编号 | 旧缺口 | 新 UI 表现 | 实测证据 |
|---|---|---|---|
| G-01 / G-13 | 移动端 sidebar 与右栏有 CSS 但无打开入口，右栏整体落在视口外 | TopBar 增加 `☰` 与 `◎` 两个 `mobile-only` 按钮，配 scrim + Escape 关闭 | 390px 下两栏初始 `width:0`；点 `☰` → sidebar `x:0,w:300`；点 `◎` → sidebar 归 0、insights `x:54,w:336`。**互斥且可达** |
| G-05 | `A → Z` 不能切降序 | `sortAscending` 状态，按钮在 `A → Z` / `Z → A` 间切换 | `app.jsx:79-81` |
| G-09 | 无 `prefers-reduced-motion` | 有该 media query | `index.html:1711` |
| G-10 / D5 | 正文无最大宽度，超宽屏行长失控 | `.reading-column { width: min(100%, 790px); margin: 0 auto }` | 实测 `colWidth:790, align:start` |
| G-11 / D7 | header 与 footer 显示两个互相矛盾的进度值 | header、footer、书卡统一读 `book.progress` | `app.jsx:340/378`，`components.jsx:106` |
| G-14 | 面板叠加互相遮挡、挡住工具栏 | `togglePanel` 强制单面板互斥，切字号面板会先关侧栏 | `app.jsx:329-332` |
| §5.7 死控件 | 字体面板里主题/字体族选项可见但无事件绑定 | 直接删掉，只保留真正生效的字号 + 行高 | `app.jsx:397-416` |
| — | Reader 无任何页眉，书名/位置不可见 | 新增 reader-header：返回 Library + 书名 + `Section 8 of 32 · 20%` | — |

---

## 2. Library 逐项对照

| 旧组件（spec §3.1 / §4.1 / §6） | 新 UI | 说明 |
|---|---|---|
| App header / 品牌 / My Library / Settings / Add books | ✅ | 文案一致 |
| Types：All Books / EPUB / 禁用 PDF（title `PDF not supported yet`） | ✅ | 一致 |
| Collections 列表 + 创建 | 🟡 | 只有列表和 `+`。**缺**：删除集合、清理失效 book ID、重名/空名/非法字符的 inline 报错（spec §6.3） |
| 标题筛选 `Find books...` | 🟡 | input 存在但无 `value/onChange`，不过滤 |
| A→Z 排序 | ⭐ | 见上 |
| Grid / List 切换 | 🟡 | 只切 `.is-list` class。**缺** List 的 6 列表格（Title/Author/Chunks/Sections/Status/Read，spec §6.1） |
| Select 模式 + selection bar | ✅ | 计数、Select all、Clear、Add to collection、Index selected 都在，且带 `aria-live` |
| Book card：封面/标题/作者/status/chunks | 🟡 | status pill 硬编码 `Not indexed`，**缺** `indexing` / `indexed` / `error` 四态（spec §6.4）；chunks 数未展示 |
| 右栏可收起（`rightPanelCollapsed`） | ❌ | 桌面端没有收起按钮，全文无 collapse 相关代码 |
| Dashboard：Books/Indexed/Sections/Chunks + 索引进度 + Refresh stats | ✅ | 文案略简为 `Refresh` |
| Library Chat：Single book scope、历史、SSE、Stop | 🟡 | 只有 scope 下拉 + 空态 + Send。**缺** 消息流、历史（最近 5 条）、Stop/abort；且丢掉了 `All books` / `Collection` 两个 disabled+`Coming soon` 选项，等于隐藏了产品边界 |
| Library Search：query/mode/**case**/sort/分组结果 | 🟡 | 有 mode + sort。**缺 Case 复选框**（旧 Library 有）、**缺按 book 分组**、**缺 `Show more`（3→10）**、缺 300ms debounce 语义 |
| Add books dialog | ✅ | 说明 CLI 处理方式，未伪装成上传器，正确 |
| Collection create / add dialog | ✅ | 结构对齐 |
| Index errors dialog | ❌ | 无 |
| 批量索引 beforeunload 保护 + 中断标记 | ❌ | 原型态，可接受但设计规格里要保留这条状态 |
| **Classic Library（`READER3_LIBRARY_UI=classic`）** | ❌ | 完全没有。spec §4.2/§6.6 把它定义为环境变量回退模式，需明确「新 UI 是否废弃 Classic」 |

---

## 3. Reader 逐项对照

| 旧组件（spec §3.2 / §5） | 新 UI | 说明 |
|---|---|---|
| EPUB viewport（epub.js rendition，桌面分页 / <600px 滚动） | 🟡 | 原型用静态 `<p>` 渲染，属预期。但要注意：**新 UI 是纵向滚动，旧实现是横向分页**，这是阅读模型的实质改变，必须显式确认 |
| 右侧工具栏（面板互斥、字体 popup、返回 Library） | ⭐ | 悬浮 TOC/Find/AI/Notes，互斥已修 |
| TOC 面板：递归层级 + 筛选 + 跳转 | 🟡 | 有筛选与 `is-indented`，但 mock 数据 `depth` 全为 0，多级 TOC 与「父项隐藏连带隐藏命中子项」这个已知限制都没被设计 |
| Chapter navigation：`Previous` / `Section N of M` / `Next` | ⚠️ | 降级为页眉两个 `←` `→` 图标按钮，丢掉了 `Section N of M` 这个带语义的落点文案与首尾禁用态 |
| Reading progress | ✅ | 底部胶囊 `20% read` |
| Reader Search：keyword/semantic/hybrid + case + 命中跳转 | 🟡 | mode + case 都在（正确，Reader 无 sort，符合 §5.5）。**缺**：未索引时的索引状态与「索引本书」入口、命中高亮 `<mark>` 的呈现规格、`Searching…` / `Search failed` / `No results found for "{query}"` 三态 |
| **Annotation toolbar（Copy/Marker/Wavy/Underline/Delete/Add Note/Ask AI）** | ❌ | **整块缺失**。全文只有一个 `--highlight` token，且仅用于搜索 `<mark>` |
| **Note editor** | ❌ | 缺失 |
| **4 种批注类型 × 4 种颜色（marker/wavy/underline/note × yellow/green/pink/blue）** | ❌ | 缺失。这是 spec §5.4 的核心合同，也是本项目 006 分支的主要功能 |
| Notes 面板：按 chapter 分组、总数、点击跳转、`?note_id=` 深链 | 🟡 | 只有空态。列表、分组、计数、跳转全无 |
| Notes footer `点评此书` / `复制全部笔记·N` | 🟡 | 变成 `Review book` / `Copy all · 0`。`Review book` **仍然没有行为**（G-04 未解决），只是把一个已知的死控件原样搬了过来 |
| AI 面板：History / Summary·Highlights·Background / 消息流 / composer / Stop·Send / New chat / Clear / Close | 🟡 | 只有三个快捷 chip + 空态 + composer + Send。**缺** History、New chat、Clear、Stop/abort |
| AI 引用可导航链接（RAG citations） | ❌ | 缺失 |
| AI Export MD/TXT/JSON | ❌ | 缺失 |
| AI 面板宽度可拖（320–800px，默认 546） | 🟡 | 只有固定的 `.is-wide`，无拖拽 |
| 快捷键：←/→ 翻页、Escape 分层关闭、Enter 搜索/发送、Shift+Enter 换行 | 🟡 | ←/→ 改为 `scrollBy`（配合滚动模型），并正确排除 input/textarea/select（修了 §5.3 的待确认项）。**Escape 是一次全关**，没有实现 §5.3 的分层顺序（note editor → toolbar → TOC → Notes → Search/AI）。Enter/Shift+Enter 未绑定 |
| EPUB 缺失的错误块 | ❌ | 无该状态设计 |

---

## 4. Settings 逐项对照

| 旧（spec §4.3） | 新 UI | 说明 |
|---|---|---|
| Default provider / Streaming / timestamps / Auto suggested (future) / Save preferences | ✅ | 文案与 `Future` 标记都保留，Save 有 `Saved` 反馈 |
| Provider 卡：enabled / base URL / model / timeout / max retries | 🟡 | 四个字段在。`Enabled` 只是一段静态文字（`components` 里是 `<span class="provider-toggle">Enabled`），**不是可操作开关**，且在 Disabled 的卡上也显示 `Enabled`，读起来自相矛盾 |
| 云 provider 的 **API key** 字段 | ❌ | **缺失**。Anthropic/OpenAI/Gemini/OpenRouter 在新 UI 里没有任何填 key 的地方，等于这四个 provider 不可配置。（注意 spec §7.3：key 不得写入导出文件或 DOM 可见值，设计时要一并给出 masked 展示规格） |
| Save / Test connection | ✅ | 都在 |
| Ollama 专属：status / Refresh models / 本地安装提示 | 🟡 | `Refresh models` 被放进了**所有** provider 卡（应仅 Ollama）；安装提示缺失；`Not connected` 状态色对了 |
| Data：`Clear conversations (IndexedDB)` / `Clear summaries (IndexedDB)` + **confirm** | ⚠️ | 文案去掉了 `(IndexedDB)` 这个重要限定；两个 `btn-danger` **没有二次确认**，而旧实现是有 confirm 的。破坏性操作上这是倒退 |
| `Export settings (no keys)` / `Import settings` | ⚠️ | 简化为 `Export settings`，丢掉了 `(no keys)` 这个安全承诺文案 |
| 提示语「只影响当前浏览器，不动磁盘上的书」 | ✅ | 保留 |
| 响应式 | ⭐ | 旧 `settings.css` 无任何 media query；新版进了统一设计系统 |

---

## 5. 跨页面的横切问题

| 项 | 状态 | 说明 |
|---|---|---|
| **Modal 焦点陷阱与焦点归还** | ⚠️ 倒退 | 旧 Library dialog **有** trap + Escape + 归还触发控件（spec §4.1「键盘与焦点」、§10.1）。新 `Modal` 只有 `autoFocus` 和点遮罩关闭，**没有 Tab 循环，也不把焦点还给触发按钮**。`ReaderSheet` 同样声明了 `role="dialog" aria-modal="true"` 却无 trap —— 声明比不声明更糟 |
| **`data-testid` 契约** | ❌ | 全仓 0 处匹配。设计规格 §4 把它定为 Phase 0 的阻塞项（用来把 E2E 与视觉改版解耦），迁移前必须补 |
| **深色模式 / 阅读主题** | ❌ | `prefers-color-scheme` / `data-theme` / `data-reading-theme` **全部 0 匹配**。旧实现里主题是「有 DOM 无逻辑」，新 UI 直接删了 DOM —— 忠于现状，但 D1/D2/G-03 依然没解决。若打算做，现在是唯一低成本的时机（token 层已经是两级） |
| **字体族选择** | ❌ | 同上，旧的 4 个字体选项被删除且无替代 |
| **语言** | ⚠️ 需决策 | 原型 100% 英文。设计规格 §0 与迁移计划 §7.5 里「zh-CN 为主」的假设**至今未经你确认**，而这份原型等于默默把 G-16（中英混排）朝英文方向定了。需要你一句话拍板：中文优先 / 英文优先 / i18n 双语 |
| **BookCard 语义** | 🟡 | `<article tabIndex="0">` + 自绑 Enter/Space。语义上应是 `role="button"` 或真 `<button>`，否则读屏播报为 article 而非可激活控件 |
| 主色 | ℹ️ 需确认 | `#ff6b00` → `#3b82f6`。这是品牌层决策，不是缺陷，但请确认是有意的 |
| 端口硬编码 | — | G-15（`server.py:2407`）与原型无关，仍在迁移计划 §7.4b 里挂着 |

---

## 6. 补齐优先级与收口状态

第一轮列出的清单，全部状态见 §0.2；这里只留结论。

| 批次 | 条目 | 状态 |
|---|---|---|
| **P0**（不补就无法开始迁移） | 1 批注系统整套 · 2 Notes 面板实态 · 3 `data-testid` 契约 · 4 API key + masked · 5 焦点陷阱与归还 | **5 / 5 关闭** |
| **P1**（影响可用性） | 6 AI 面板会话能力 · 7 破坏性操作二次确认 · 8 搜索补齐 · 9 四态 pill + List 6 列 · 10 章节导航 · 11 Escape 分层 | **6 / 6 关闭** |
| **P2**（需要决策） | 12 阅读模型 · 13 深色模式与阅读主题 · 14 语言 · 15 Classic Library · 16 主色 | **5 / 5 已拍板**，见 §0.1；同步回写 spec §0.3 与迁移计划 §7.5 |

迁移前仍需在真实实现里补的，只剩 §0.4 的四项（批量索引 `beforeunload`、iframe 内批注呈现、SSE 与真实 provider、端口硬编码 G-15），都不依赖设计侧再出规格。

---

## 7. 复现方式

```bash
cd designs/reader-pro-next
python3 -m http.server 8125 --bind 127.0.0.1   # file:// 会被 CORS 挡掉 jsx 加载
open http://127.0.0.1:8125/index.html
```

原型入口参数：

| URL | 屏幕 |
|---|---|
| `/index.html` | Library（默认） |
| `/index.html?screen=reader` | Reader |
| `/index.html?screen=reader&state=epub-missing` | Reader 的 EPUB 缺失错误屏 |

第一轮审计为只读。第二轮按产品方指示改写了 `designs/reader-pro-next/` 下的 6 个原型文件（新增 `reader.jsx`、`settings.jsx`），并回写了本文件、`reader-pro-spec.md` §0.3、迁移计划 §7.5。两轮均未触碰 `books/`、笔记、集合、索引与 AI 设置，也未改动 `src/` 下任何产品代码。
