# Reader3 Pro 前端实现规格

> 本文档描述 2026-08-15 仓库中的实际前端实现，供工程复现、维护与验收使用。它不是重设计提案，也不把尚未实现的 `specs/` 内容写成现状。

## 0. 文档约定

### 0.1 范围与来源

| 项目 | 内容 |
|---|---|
| 适用版本 | 当前 `reader3-pro` 工作区，生成日为 2026-08-15 |
| 前端形态 | FastAPI + Jinja2 服务端模板；原生 CSS/JavaScript；Reader 使用 epub.js |
| 页面范围 | Modern Library、Classic Library、Settings、Reader 及其目录、笔记、搜索、AI、批注界面 |
| 事实来源 | 当前运行结果 → 当前源码 → `specs/` 与技术文档 → README |
| 主要模板 | `src/reader3_app/web/templates/*.html` |
| 主要样式 | `src/reader3_app/web/static/*.css`、`static/css/*.css` |
| 主要交互 | `src/reader3_app/web/static/*.js`、`static/js/*.js` |
| 服务与接口 | `src/reader3_app/web/server.py`、相关 service/model 模块 |
| 格式参照 | `docs/design-reference/feeddock-frontend-spec.md`，仅参照组织方式和精度 |

本文使用下列状态标签：

- **已实现**：当前模板、样式和脚本形成可达行为。
- **代码存在但不可达**：代码或样式存在，但当前入口、DOM 或事件链无法触发。
- **文档声明**：仅见于 README、`specs/` 或技术文档，不能据此视为已实现。
- **待确认**：运行证据不足，或源码、文档之间存在冲突。
- **建议**：维护建议，不属于当前产品事实。

### 0.2 本次验证边界

仓库原始 `books/` 中只有 EPUB，没有已处理的 `books/*_data/`。为避免写入用户数据，本次把已有的 `the-art-of-spending-money.epub` 处理到隔离的 `/tmp` 目录，并以 `READER3_BOOKS_DIR` 指向该目录进行只读审计。隔离样本得到 1 本书、32 个 section、31 项 TOC、16 张图片，索引状态为 `not_indexed`。

应用初始化成功，但受执行沙箱限制，Uvicorn 绑定 `127.0.0.1:8123` 时返回 `[Errno 1] operation not permitted`。随后以同一 FastAPI 应用直接调用页面函数和只读接口，四个模板均成功渲染；Modern Library、Classic Library、Settings 和 Reader 分别得到完整 HTML。端口失败不等同于产品启动错误。

浏览器验证也受环境策略限制：`playwright-cli` 无法创建本地 daemon 监听端口，应用内浏览器禁止打开 `file://` 的直接渲染结果。因此本文没有把直接渲染伪装成真实浏览器截图；第 14 节记录未生成的截图矩阵与复现条件。

### 0.3 已确认的产品决策（2026-08-16）

本节记录产品方对 `designs/reader-pro-next/spec/reader-pro-next-parity.md` 中五个悬置问题的最终答复。**这些决策描述目标形态，不描述本文其余章节所记录的当前实现**；当两者冲突时，以本节为准，其余章节保持为现状快照。新 UI 原型 `designs/reader-pro-next/` 已按本节实现。

| # | 决策 | 影响 |
|---|---|---|
| D-1 | **保留横向分页**（epub.js `flow: paginated`），不改为垂直滚动 | Reader 正文继续以 CSS 多列分页；原型用 `column-width = viewport width` + `translateX` 复刻该模型 |
| D-2 | **英文为主语言** | 推翻本文 §0 早期的 zh-CN 假设与迁移计划 §7.5 的同一假设；G-16 的中英混排按“全部英文”收敛，`html lang="en"` 由此成为准确标记（关闭 §13 第 534 行的语言标记问题） |
| D-3 | **实现深色模式与阅读主题** | 关闭 G-03；`:root[data-theme]` 三态（light / dark / system）+ 独立的 `[data-reading-theme]`（paper / sepia / green / night）只作用于正文区 |
| D-4 | **废弃 Classic Library** | §3.3、§4.2、§6.6、G-02、G-08 与截图 `11-library-classic-*` 转为历史记录；不再修复 `library-search-*` / `library-panel-*` 的 ID 不匹配，`READER3_LIBRARY_UI=classic` 分支随迁移一并移除 |
| D-5 | **品牌色改为 `#3b82f6`** | 取代 §9 的 `#ff6b00` 及其 hover `#e65f00` / light `#fff7f0` / muted `rgba(255,107,0,.1)` 派生值 |

## 1. Route map

### 1.1 HTML、静态资源与图书资源

| Method | Route | 页面/响应 | 实现现状与依赖 |
|---|---|---|---|
| GET | `/` | Library | `READER3_LIBRARY_UI=classic` 时使用 `library_classic.html`，其他值及未设置时使用 `library.html` |
| GET | `/settings` | Settings | `settings.html`；首次加载只读取设置，不写入 |
| GET | `/read/{book_id}` | Reader | 跳入该书第 0 个 section 的阅读页 |
| GET | `/read/{book_id}/{chapter_index}` | Reader | 校验 section 下标后渲染 `reader.html` |
| GET | `/read/{book_id}/book.epub` | EPUB 二进制 | epub.js 的实际内容源；缺失时 Reader 显示降级错误文案 |
| GET | `/read/{book_id}/images/{image_name}` | 图片二进制 | 兼容已提取的 EPUB 图片 |
| GET | `/static/*` | CSS/JS/图标 | FastAPI StaticFiles 挂载 |

证据：`src/reader3_app/web/server.py` 的页面与资源路由；`src/reader3_app/web/templates/reader.html` 的 `window.Reader3Ctx`。

### 1.2 JSON/SSE API

| Domain | Method / Route | 前端用途 |
|---|---|---|
| Collections | `GET/POST /api/collections` | 列表、创建集合 |
| Collections | `GET/PUT/DELETE /api/collections/{collection_id}` | 读取、重命名、删除集合 |
| Collections | `POST /api/collections/{collection_id}/books` | 批量加入/移出图书 |
| Library | `GET /api/library/stats` | Dashboard 的 Books/Indexed/Sections/Chunks |
| Search | `GET /api/search/library` | 跨书 keyword/semantic/hybrid 搜索 |
| Search | `GET /api/search/{book_id}` | 书内搜索 |
| Search | `POST /api/highlight/{book_id}/{chapter_order}` | 计算指定 occurrence 的高亮范围 |
| Index | `POST /api/index/{book_id}` | 单书或批量索引 |
| Index | `GET /api/index/{book_id}/status` | `not_indexed/indexing/indexed/error` 状态与 chunks |
| Notes | `GET /api/notes/{book_id}` | 获取按 chapter 分组的全书批注摘要 |
| Notes | `GET/POST /api/notes/{book_id}/{chapter_index}` | 获取该章批注、在该章创建批注/笔记 |
| Notes | `PUT/DELETE /api/notes/{book_id}/{chapter_index}/{note_id}` | 更新笔记文本、删除批注 |
| Settings | `GET/PUT /api/settings` | 默认 provider 与 preferences |
| Providers | `GET/PUT/DELETE /api/settings/providers/{provider_name}` | provider 读取、更新与删除自定义配置 |
| Providers | `GET /api/settings/providers` | 可用 provider 元数据列表 |
| Providers | `POST /api/settings/providers/{provider_name}/test` | 连通性测试 |
| Settings | `GET /api/settings/export`、`POST /api/settings/import` | 不含 API key 的导出、导入 |
| Ollama | `GET /api/ollama/status`、`GET /api/ollama/models` | 本地服务状态、模型列表 |
| Conversations | `GET /api/ai/conversations/{book_uuid}` | 对话列表；可带 provider query |
| Conversations | `GET/PUT/DELETE /api/ai/conversations/{book_uuid}/{conversation_id}` | 对话读写删除 |
| Conversations | `GET /api/ai/conversations/{book_uuid}/{conversation_id}/export` | `format=json/text/md` 导出 |
| AI | `POST /api/ai/rag/retrieve` | 检索上下文 |
| AI | `POST /api/ai/summary/{book_uuid}` | Summary/Highlights/Background；类型由 `summary_type` query 指定 |
| AI | `POST /api/ai/question/{book_uuid}` | 问答；`stream=true` 时返回 SSE |

## 2. 全局 Shell、导航与行为

### 2.1 页面关系

```text
Library (/)
├─ Header: Reader3 Pro / My Library / Settings / Add books
├─ Left sidebar: Types / Collections
├─ Main: Toolbar / Grid or List / Selection controls
└─ Right panel: Dashboard / Chat / Search
   └─ Reader (/read/{book_id}/{chapter_index})
      ├─ Overlay surfaces: TOC / Notes / Search / AI（互斥）
      ├─ EPUB viewport + section navigation
      ├─ Selection annotation toolbar + note editor
      └─ Right vertical toolbar: Library / TOC / Search / AI / Font / Notes

Settings (/settings)
└─ Back to Library / Preferences / Providers / Data

Classic Library (/; env fallback)
└─ Simple book grid + legacy search surface
```

### 2.2 全局导航合同

- Library header 高度为 `--dedao-header-height: 56px`，`position: sticky; top: 0; z-index: 100`。
- Modern Library 的品牌文案为 `Reader3 Pro`，主导航文案为 `My Library` 与 `Settings`，当前项由橙色和下边线表达。
- Reader 右侧工具条第一项是返回 Library 的链接；Settings 顶部也提供返回 Library 的链接。
- 页面之间通过普通 `<a>` 导航；不是 SPA，不共享前端路由状态。
- Reader 内部 section 变化由 epub.js location 驱动，并通过 `history.replaceState` 同步 URL；不进行整页跳转。
- Modern Library 的 dialog 使用原生 `<dialog>`，关闭时恢复原焦点，并由脚本实现 Tab 焦点循环。

### 2.3 全局状态原则

- 初始加载只执行读取型请求；创建集合、索引、保存设置、创建/修改批注、发送 AI 消息必须由用户动作触发。
- Library 视图模式、右栏收起和批量索引中断标记保存在浏览器 storage；Reader 的字体数值和 AI 状态另行保存，详见第 11 节。
- 页面不提供统一 toast 系统。反馈分散为 inline text、status pill、原生 `alert/confirm`、panel error 或 dialog。
- 未发现全局 `prefers-reduced-motion` 降级规则。

## 3. Component inventory

### 3.1 Library 组件

| 组件 | 主要选择器/模板 | 内容与交互 |
|---|---|---|
| App header | `.library-header` | 品牌、导航、`Add books` |
| Type sidebar | `.library-sidebar` | All Books、EPUB、禁用的 PDF、Collections |
| Collection row | `.collection-item` | 切换 scope、清理失效书、删除集合 |
| Main toolbar | `.library-toolbar` | 标题筛选、A→Z、Grid/List、Select |
| Selection bar | `#selection-toolbar` | 数量、Select all、Clear、Add to collection、Index selected |
| Book grid/list | `#book-grid`、`#book-list` | 同一数据的卡片和表格表示 |
| Book card | `.book-card` | checkbox、封面、标题、作者、status/chunks |
| Right panel | `.library-right` | Dashboard/Chat/Search tabs；可收起 |
| Dashboard | `#library-panel-dashboard` | 统计数、索引进度、刷新 |
| Library Chat | `#library-panel-chat` | Single book scope、历史、SSE 对话、Stop |
| Library Search | `#library-panel-search` | query、mode、case、sort、分组结果 |
| Add books dialog | `#add-books-dialog` | 展示 CLI 处理方式；不是文件上传器 |
| Collection dialogs | create/add dialog | 创建集合、把 selection 加入集合 |
| Index errors dialog | index error dialog | 批量索引失败项 |
| Live region | `.sr-only[aria-live]` | selection、索引等状态播报 |

### 3.2 Reader 组件

| 组件 | 主要选择器/文件 | 内容与交互 |
|---|---|---|
| EPUB viewport | `#epub-viewer`; `js/epub-renderer.js` | epub.js rendition；桌面分页、窄屏滚动 |
| TOC mode | `#toc-mode`; `js/toc-panel.js` | 全屏目录、递归 TOC、筛选、跳转 |
| Notes mode | `#notes-mode`; `js/notes-panel.js` | 全屏笔记视图、分组、计数、复制、定位 |
| Reader Search | `#reader-search-drawer`; `search.js` | keyword/semantic/hybrid、索引、命中跳转 |
| AI panel | `#reader-ai-panel`; `ai.js` | 历史、快捷摘要、SSE、引用、导出、可调宽度 |
| Right toolbar | `.reader-toolbar`; `js/toolbar.js` | 面板互斥、字体 popup、返回 Library |
| Annotation toolbar | `#annotation-toolbar`; `js/annotations.js` | Copy/Marker/Wavy/Underline/Delete/Note/Ask AI |
| Note editor | `#note-editor` | 编辑选区笔记 |
| Chapter navigation | `.chapter-navigation` | Previous、`Section N of M`、Next |
| Reading progress | `.reading-progress` | `当前阅读至 0%` 等定位反馈 |

### 3.3 Settings 与 Classic 组件

| 页面 | 组件 | 说明 |
|---|---|---|
| Settings | Preferences section | Default provider、Streaming、timestamps、suggested questions |
| Settings | Provider cards | 展开/折叠、enabled、URL、model、timeout、retry、API key、Save/Test |
| Settings | Ollama controls | status、Refresh models、安装提示 |
| Settings | Data section | 清浏览器数据、导出/导入设置 |
| Classic | Simple book grid | 800px 容器、卡片 grid、Settings |
| Classic | Legacy search form | DOM 存在，但当前加载脚本与 ID 不匹配，见 5.2 |

## 4. Per-screen spec

### 4.1 Modern Library

**页面目标。** 浏览、筛选、阅读本地图书；查看索引覆盖；管理集合；执行跨书搜索与单书 AI 对话。

浏览器标题为 `Library - Reader3 Pro`。

**精确布局。** 桌面主区域为三列 grid：`240px 1fr 340px`，分别对应左 sidebar、main、right panel。`dedao-theme.css` 在不超过 1024px 时把 sidebar/right tokens 改为 200px/300px；页面内联响应式规则再把整体变为 `200px 1fr` 并把 300px 右栏改为 fixed overlay。

**主要结构。** 

```text
body
├─ header.library-header
└─ .library-layout
   ├─ aside.library-sidebar
   ├─ main.library-main
   │  ├─ .library-toolbar
   │  ├─ #selection-toolbar
   │  ├─ #book-grid
   │  └─ #book-list
   └─ aside.library-right
      ├─ tablist
      └─ dashboard | chat | search panel
```

**关键文案。**

- Header：`Reader3 Pro`、`My Library`、`Settings`、`Add books`。
- Types：`All Books`、`EPUB`、`PDF`；PDF 的 title 为 `PDF not supported yet`。
- 主筛选 placeholder：`Find books...`。
- Toolbar：`A → Z`、Grid、List、Select。
- 空库：`No processed books found`；`Run uv run reader3 path/to/book.epub and refresh.`
- Dashboard：`Books`、`Indexed`、`Sections`、`Chunks`、`Refresh stats`。
- Search：`Clear`、`Case`、`Mode`、`keyword`、`semantic`、`hybrid`、`Sort`。
- Chat scope：`All books`、`Collection`、`Single book`；前两项当前为 disabled/`Coming soon`。

**控件与交互。**

1. Title filter 在已加载书数组上做客户端过滤；scope 变化会清空 selection。
2. `A → Z` 只执行标题升序。重复点击不会切换降序。
3. Grid/List 切换写入 `reader3.library.viewMode`。
4. Select 模式显示每本书 checkbox 与批量工具条；支持 select all、clear、加入集合、顺序索引。
5. 单书状态按最多 20 本一批、并发 4 个请求读取，单请求超时 5 秒。
6. 批量索引逐本执行，单书请求超时 300 秒；运行时设置 `beforeunload` 防误离开。未正常完成会保留中断标记并在下次打开显示提示。
7. 集合创建、删除、加书都由显式按钮触发；删除使用原生 `confirm`。
8. 右栏收起状态写入 `reader3.library.rightPanelCollapsed`。
9. 跨书搜索输入 debounce 300ms；初次每书显示至多 3 条，`Show more` 扩至 10 条，总结果上限 100。结果按 book 分组。
10. semantic/hybrid 依赖索引；未索引时显示状态/索引入口。
11. Chat 只支持 Single book。Enter 发送，Shift+Enter 换行；流式生成期间显示 Stop 并允许 AbortController 取消。
12. 对话历史按 `created_at`、回退 `last_updated` 排序，仅展示最近 5 条。

**键盘与焦点。** 原生输入框保留默认行为；dialog 打开后聚焦内部首个可聚焦项、Tab/Shift+Tab 循环、Escape/取消关闭并恢复触发控件。Chat 使用 Enter/Shift+Enter。未实现 Grid/List 的方向键导航。

**状态。**

| 状态 | 表现 |
|---|---|
| Loading | 图书 status pill、dashboard/search/chat 各自显示 loading 文案；没有全屏 skeleton |
| Empty library | 上述 CLI 处理提示 |
| Empty collections | sidebar 保持集合标题与创建按钮，列表为空 |
| Search empty | panel 内空结果文案；保留 query 控件 |
| Indexing | status pill + selection 进度；离开页面前告警 |
| Index error | 书级 error；批量错误可进入 errors dialog |
| Disabled | PDF、All books chat、Collection chat 使用 disabled 与提示 |
| Fetch failure | 多数 dashboard/index/chat 路径有 inline error；跨书 `performSearch` 的网络异常未完整捕获 |

**响应式实现缺口。** `<=1024px` 的右栏只有添加 `.is-open` 才可见，`<=768px` 的 sidebar 同样需要 `.is-open`；当前模板和 `library.js` 没有移动端打开按钮或设置该 class 的事件链。因此平板/手机下右栏和 sidebar 实际不可达，不能把 CSS 中的 off-canvas 外观视为完整功能。

### 4.2 Classic Library

**定位。** Classic 不是并存路由，而是 `/` 的环境变量回退模式：仅当 `READER3_LIBRARY_UI=classic` 才渲染；默认是 Modern。README 把它描述为可回退界面，当前源码仍保留并可直接渲染。

**布局与文案。** 浏览器标题为 `My Library`，可见 `<h1>` 为 `Library`。`body` padding 40px，内容最大宽度 800px；书架使用 `repeat(auto-fill, minmax(250px, 1fr))`。页面提供 `Settings`；空状态为 `No processed books found. Run reader3.py on an epub first.`。

**实现缺口。** 页面使用 `library-search-*` DOM ID，但加载的 `library-search.js` 查询 `library-panel-*` ID。初始化因找不到节点而直接返回，所以 Classic 的搜索表单虽然可见，当前搜索行为不可达。这与 README 中“classic 可回退”的宽泛声明需要区分：书架可回退，搜索功能没有等价回退。

**响应式。** grid 可随宽度自动变列，但固定 40px body padding 没有移动断点；没有移动导航或专门的触控适配。

### 4.3 Settings

**页面目标。** 配置默认 AI provider、通用偏好、provider 参数和浏览器侧 AI 数据。

浏览器标题为 `Settings · Reader3 Pro`。

**布局。** 主容器最大宽度 980px，桌面 padding 为 30px/20px；section 为白底、10px radius。顶部提供返回 Library 与标题 `Settings`。

**Preferences。** 

- Default provider 下拉框。
- `Streaming enabled (when supported)`、`Show timestamps`、`Auto suggested questions (future)` 三个 checkbox；最后一项明确标记为未来能力，不应视为已工作的建议问题引擎。
- `Save preferences` 才提交 `PUT /api/settings`。

**Provider cards。** 默认 provider 初始展开，其余折叠。状态文案按实现包括 `Running`、`Not connected`、`Enabled`、`Disabled`。字段包括 enabled、base URL、model、timeout、max retries；云 provider 另有 API key。操作为 Save 与 Test。Ollama 卡提供 Refresh models 和本地安装提示。

**Data。** 两个按钮的精确文案为 `Clear conversations (IndexedDB)`、`Clear summaries (IndexedDB)`；只删除当前浏览器 origin 的 IndexedDB 数据，先弹出 confirm，不会删除服务端对话文件。配置操作为 `Export settings (no keys)`、`Import settings`。页面提示：`Clearing data only affects this browser profile. It does not touch your books on disk.`

**状态与错误。** provider、Ollama 与模型分别加载；请求失败使用卡片或页面内 status text。没有全局错误边界或 toast。

**响应式。** `settings.css` 未定义 media query。表单行允许 flex wrap，但 input/select 有 `min-width: 260px`；390px 视口下预期由自然换行承担，未形成明确移动规格，需真实浏览器复核。

### 4.4 Reader 主界面

**页面目标。** 渲染原始 EPUB，提供 section 导航、目录、书内搜索、批注/笔记和带引用的 AI 辅助阅读。

**主要 DOM。**

```text
body
├─ #toc-mode
├─ #notes-mode
├─ #reader-search-drawer
├─ #reader-ai-panel
├─ #reader
│  └─ #main
│     └─ .content-container
│        └─ .pagination-container
│           └─ #epub-viewer
├─ .chapter-nav
├─ .reading-progress
├─ .reader-toolbar
├─ #font-settings-popup
├─ #annotation-toolbar
└─ #note-editor
```

**初始上下文。** 模板注入 `window.Reader3Ctx`：`bookId`、`bookUuid`、`provider`、`chapterIndex`、`totalChapters`、`title`、`coverUrl`、`epubUrl`、`epubAvailable`。Reader 脚本应使用该对象，不重新从 DOM 猜测服务端元数据。

**关键文案。** section footer 使用 `Previous`、`Section N of M`、`Next`；初始进度为 `当前阅读至 0%`。原始 EPUB 缺失时显示：未找到原始 EPUB 文件。请删除 `books/{book_id}/` 后重新运行 `reader3` 重新处理图书。这是一条会建议删除目录的产品文案，不代表本审计执行了删除。

**加载顺序。** JSZip → epub.js → `epub-renderer.js` → `toc-panel.js` → `notes-panel.js` → `annotations.js` → `toolbar.js` → `search.js` → `ai.js`。旧 `pagination.js` 当前未被 Reader 模板加载，属于遗留实现，不是 epub.js Reader 的事实来源。

## 5. Reader 专项

### 5.1 EPUB 渲染区域

- epub.js 直接加载 `/read/{book_id}/book.epub`。
- 视口宽度 `<600px` 使用 `flow: scrolled-doc`；其他宽度使用 `flow: paginated`；`spread: none`。
- 注入 EPUB iframe 的正文基线为 `Noto Serif SC`、17px、line-height 1.9；水平 margin 在窄屏约 16px、桌面约 80px。
- rendition 的 `rendered`/`relocated` 更新 section、URL、TOC active state、progress，并发出 `reader3:chapter:change`、`reader3:content:rendered`。
- 内容点击发出 `reader3:content:click`，用于关闭浮层；Escape 发出 `reader3:escape`。
- EPUB 缺失时不尝试旧 HTML chapter 渲染，而显示错误块。

### 5.2 目录与章节导航

- TOC 由服务端 `Book.toc` 递归输出；链接最终交给 renderer 映射到 EPUB href/section。
- TOC filter 在客户端按每个 `<li>` 的直接 anchor title 匹配并切换可见性。父项不匹配但子项匹配时，父层隐藏可能连带隐藏命中子项，这是当前限制。
- Chapter footer 提供上一/下一 section；首尾对应链接处于不可用状态。
- README 声明支持方向键翻页；当前实际键盘行为由 `epub-renderer.js` 绑定，需在可启动浏览器中复核其与输入框、面板焦点的冲突规避。
- 模板保留左右 navigation zones，但当前 CSS 隐藏，不属于可点击翻页入口。

### 5.3 翻页与快捷键

| Key | 当前行为 |
|---|---|
| Left / Right | renderer 上一页/下一页；输入控件获得焦点时不应抢占，运行待确认 |
| Escape | 优先关闭 note editor → annotation toolbar → TOC → Notes → Search/AI |
| Enter | Search 执行搜索；AI 发送消息 |
| Shift+Enter | AI 输入框换行 |
| Tab | 使用浏览器默认顺序；Reader panels 没有焦点陷阱 |

### 5.4 批注、标记与笔记

- 用户在 EPUB 内容中选择文字后显示 annotation toolbar。
- 类型合同：`marker`、`wavy`、`underline`、`note`；颜色：`yellow`、`green`、`pink`、`blue`。
- 操作包括 `Copy`、`Marker`、`Wavy`、`Underline`、`Delete`、`Add Note`、`Ask AI`。
- 定位优先保存 CFI；CFI 不可用时使用 quote + prefix/suffix + position 文本回退。
- 创建、更新、删除分别调用 notes API，并写入该书 `notes.json`。
- `Ask AI` 把选区通过自定义事件送入 AI panel，不自动提交；用户仍可编辑问题。
- Notes panel 按 chapter 分组，显示总数。条目点击跳到对应 section，并以 `?note_id=` 深链定位。空状态精确文案为 `你可以在这里记录本书的想法、划线、书签`。
- Notes footer 文案为 `点评此书`、`复制全部笔记·N`。复制使用 Clipboard API；`点评此书` 当前未找到事件处理，属于可见但不可达控件。
- Notes item 被设为 `tabIndex=0`，但仅绑定 click，未见 Enter/Space 等价处理。

### 5.5 搜索与命中跳转

- 支持 `keyword`、`semantic`、`hybrid` 与 case-sensitive；Reader Search 没有 sort 控件，sort 只存在于 Library Search。
- keyword 命中跳转到 section URL，并携带 query/occurrence；随后请求 highlight contract 并在内容 DOM 标记所有命中，把选中 occurrence `scrollIntoView({behavior: 'smooth'})`。
- semantic 结果按语义位置跳转，不使用关键词 occurrence 高亮。
- 非 keyword 模式会读取/显示索引状态，并在需要时提供索引按钮。
- 当前书内搜索条件保存在 `reader3.search.reader.{book_id}` 的 sessionStorage。请求中显示 `Searching…`，HTTP 非成功响应回退为 `Search failed`，空结果为 `No results found for "{query}"`；与 Library Search 一样，`fetch()` 拒绝或 JSON 解析异常没有外层 catch。

### 5.6 AI 助手与引用

- Panel 包含 History、快捷动作 `Summary`/`Highlights`/`Background`、消息列表、composer、Stop/Send、New chat、Clear、Close。
- 问答默认使用 SSE；前端解析增量事件并允许 abort。
- RAG 返回的章节引用渲染为可导航链接；点击后进入对应 section。
- Panel 宽度可拖动并存到 `reader3-ai-panel-width`；Reader 局部变量 `--ai-panel-width` 默认为 546px，可拖动范围为 320–800px。
- 会话浏览器侧保存在 IndexedDB `reader3_ai_assistant`，同时通过 conversation API 同步服务端磁盘；两套存储的冲突策略是当前待确认项。
- Export 支持 MD/TXT/JSON。
- 具体 provider/model 由 Settings 与 `window.Reader3Ctx.provider` 决定；provider 不可用时显示错误，不静默切换。

### 5.7 字体面板

- 数值控件：font size 14–24px（默认 17）、line-height 1.5–2.5（默认 1.9），写入 `reader3-font-settings`，并应用到 rendition theme。
- 可见主题：`白色`、`黄色`、`护眼`、`夜间`；可见字体：`系统字体`、`得到今楷`、`汉仪旗黑`、`思源宋体`。
- **代码存在但不可达/未实现：** 主题与字体 family 的 DOM 存在，但脚本没有为 `.theme-option` / `.font-option` 绑定事件或保存状态；当前实际只连接 font size 与 line-height。不得据可见选项宣称支持换肤或换字体。

## 6. Library 专项

### 6.1 图书视图

- 服务端从每个有效 `*_data/book.pkl` 生成书目；卡片/list 共用同一数据。
- Grid 卡片显示封面或 placeholder、title、author、索引状态和 chunks；List 列为 `Title`、`Author`、`Chunks`、`Sections`、`Status`、`Read`。
- 封面与图书数据缺失应逐书降级，不阻断整个 Library。

### 6.2 选择与批量操作

- Select 是显式模式；离开 scope 会清空已选图书。
- Select all 只作用于当前过滤结果。
- 批量加入集合调用一次 books update；批量索引在客户端按序执行并汇总错误。
- 索引运行时刷新/关闭会触发 beforeunload；中断标记用于下次访问提示，而不是后台恢复任务。

### 6.3 集合

- 集合是 `id`、`name`、`created_at` 与 `book_ids` 列表的持久结构；删除集合不删除图书。
- name 去除首尾空格后必须为 1–60 字符，只允许 ASCII 字母数字、空格及 `_-.&()`，并按不区分大小写禁止重名。
- 集合列表会识别已经不存在的 book ID，并提供清理行为。
- 创建重名、空名、未知 ID 的错误由 API 返回并在 dialog/inline 显示。

### 6.4 索引状态

- 状态集合为 `not_indexed`、`indexing`、`indexed`、`error`。
- status response 包含 `chunk_count` 和 embedding model；本次隔离样本为 0 chunks，model 为 `paraphrase-multilingual-MiniLM-L12-v2`。
- Dashboard progress 表示 indexed books / total books，不等同于章节阅读进度。

### 6.5 跨书搜索

- query、case、mode、sort 由 Library Search panel 维护。
- 结果以图书分组；每条包含 section/snippet/score 等服务端返回信息。
- semantic/hybrid 依赖 ChromaDB 索引；keyword 不要求索引。
- Search panel 状态保存在 `reader3.search.library` 的 sessionStorage。

### 6.6 Modern / Classic 关系

| 维度 | Modern | Classic |
|---|---|---|
| 默认 | 是 | 否；仅 env 回退 |
| 布局 | 三栏 + panels | 单栏 800px + grid |
| 集合/批量索引 | 已实现 | 无 |
| Dashboard/Chat | 已实现 | 无 |
| 跨书搜索 | 已实现 | 表单可见但脚本 ID 不匹配 |
| 移动端 | 有 CSS 断点，但导航触发缺失 | 仅 grid 自适应 |

## 7. Data shapes 与 API contracts

### 7.1 前端核心对象

```text
Book summary
  id: string                 # *_data 目录标识
  book_uuid/title/author: string
  cover_url: string | null
  format: "epub"
  chapters/section_count: number
  index_status: string       # 客户端延迟请求补齐，不在初始对象内
  chunk_count: number        # 客户端延迟请求补齐，不在初始对象内

Collection
  id: string
  name: string
  created_at: ISO timestamp
  book_ids: string[]

Annotation
  id: string
  type: marker | wavy | underline | note
  color: yellow | green | pink | blue | null
  quote: string
  prefix/suffix: string
  position/cfi: optional locator
  note_text: string | null
  chapter_index: number
```

### 7.2 写入请求合同

| Contract | 必填/默认字段 |
|---|---|
| Collection create/rename | `{name: string}` |
| Collection books update | `{add: string[], remove: string[]}` |
| Create annotation | `type`, `quote`; `prefix/suffix=""`; 可选 `color/position/cfi/note_text` |
| Update annotation | `{note_text: string}`；空字符串被 API 拒绝 |
| Highlight | `search_term`; 可选 `occurrence_index`; `case_sensitive=false` |
| Index | `{force_reindex: false}` |
| Settings | 可选 `default_provider`, `preferences` |
| Provider | 可选 `api_key/base_url/model_name/enabled/timeout/max_retries` |
| Conversation | `provider`, `messages[]`; 可选 model/timestamps |
| AI RAG | `book_uuid`, `query`; `k=5`, `min_similarity=0.5` |
| AI Summary | `provider`; 可选 `model`; `max_tokens=2000` |
| AI Question | `question`, `provider`; `conversation_history=[]`, `rag_k=5`, `max_tokens=1000` |

### 7.3 前端依赖边界

- Jinja2 页面依赖 pickled `Book` 的 title/author/TOC/section 元数据；只应加载可信 EPUB 产生的 pickle。
- epub.js 依赖原始 `book.epub`；提取后的 HTML 不是当前主 Reader 的内容源。
- JSZip 与 epub.js 从仓库 `/static/vendor/` 加载；`epub-renderer.js` 还会向 EPUB iframe 注入 Google Fonts 的 `Noto Serif SC` stylesheet URL，离线/被拦截时依赖 serif fallback。
- semantic/hybrid 与 AI RAG 依赖 `chroma_db/`；未索引时必须显式呈现不可用/索引入口。
- AI provider 配置来自 `config/ai_settings.json`，前端不得把 API key写入导出文件或 DOM 可见字段值。
- 对话同时依赖浏览器 IndexedDB 与服务端磁盘 API；清浏览器数据不会清服务端。

## 8. Responsive rules

| Viewport | Library | Reader | Settings / Classic |
|---|---|---|---|
| `>1024px` | 240 / flexible / 340 三栏 | 固定侧 panel 宽度，分页 EPUB | 最大宽度容器 |
| `<=1024px` | sidebar/right tokens 为 200/300；右栏 fixed 300px，但缺 `.is-open` 触发 | TOC/Notes/Search/AI 宽 100%；reader 无 left margin | 无专门规则 |
| `<=768px` | sidebar token 改为 280；单列；sidebar fixed off-canvas 且缺打开入口；header nav 隐藏；toolbar 堆叠；右栏仍为 300px | content padding 24px；右工具条按钮 40×40、right 8px | 依赖自然换行 |
| `<600px` | 继承 768 规则 | epub.js 切 `scrolled-doc`；隐藏 nav zones/progress；纵向滚动 | 无专门规则 |

移动端实现必须按“当前结果”而非意图理解：Modern Library 的 main books 仍可见，但 sidebar 的类型/集合和 right panel 的 Dashboard/Chat/Search 缺少可达打开机制。Reader panels 虽变为全宽，但不是带 focus trap 的模态 dialog。

## 9. Design tokens

来源：`src/reader3_app/web/static/dedao-theme.css`。Reader 的部分模块另有局部值；若局部值与 token 冲突，以实际选择器计算值为准。

### 9.1 颜色

| Token family | 值 |
|---|---|
| Brand | `#ff6b00`; hover `#e65f00`; light `#fff7f0`; muted `rgba(255,107,0,.1)` |
| Text | primary `#333`; muted `#666`; light `#999`; disabled `#ccc` |
| Surface | page `#f5f5f5`; hover `#eee`; card `#fff` |
| Dark surface | `#17222e`; hover `#1f2d3d` |
| Border | `#f0f0f0`; hover `#e5e5e5`; focus orange |
| Success | `#22c55e` / bg `#dcfce7` |
| Warning | `#f59e0b` / bg `#fef3c7` |
| Error | `#ef4444` / bg `#fee2e2` |
| Info | `#3b82f6` / bg `#dbeafe` |
| Annotation | yellow `#fbbf24`; red/pink `#f87171`; green `#4ade80`; blue `#60a5fa` |

### 9.2 字体、间距与形状

| Category | Tokens/实际值 |
|---|---|
| UI sans | 系统 sans + CJK fallback |
| Reading serif | `Noto Serif SC`，正文注入基线 17px / 1.9 |
| UI line-height | 1.6 |
| Spacing | 4, 8, 16, 24, 32, 48px |
| Radius | 4, 6, 8, 12px、pill |
| Shadows | sm/md/lg 与 orange focus/brand shadow |
| Theme layout widths | sidebar 240px；right 340px；drawer 384px；theme AI token 420px；content max 768px |
| Reader local override | `#reader-ai-panel` 使用独立 `--ai-panel-width: 546px`，不采用 theme 的 420px token |
| Heights | header 56px；footer 64px；toolbar 48px |
| Motion | fast 150ms；normal 300ms；slow 500ms |

### 9.3 层级与动效

- Header 使用 z-index 100；各 Reader panel、toolbar、popup 使用局部 40/50 等值。没有集中定义的 z-index scale。
- 搜索命中使用 smooth scroll；panels、buttons 使用 150–300ms transition。
- 未发现 `prefers-reduced-motion`；系统减少动态效果时仍可能平滑滚动/动画。

## 10. Accessibility contract

### 10.1 当前已实现

- 表单控件大多有可见 label 或 `aria-label`。
- Library right tabs 使用 `role="tablist"` / `role="tab"` 与 `aria-selected`。
- 选择和索引反馈写入 `aria-live` 区域。
- 原生 Library dialogs 有焦点陷阱、Escape 关闭和焦点恢复。
- Reader annotation toolbar 使用 `role="toolbar"`；note editor 使用 `role="dialog"`。
- 面板开关同步部分 `aria-expanded` / `aria-hidden` 状态。

### 10.2 当前缺口

1. 模板 `html lang="en"`，但 Reader 大量文案是中文，语言标记不精确。
2. Reader 多个 icon-only button 只有 `title`，没有稳定的 `aria-label`/可见名合同。
3. Library tab 与 panel 缺完整 `aria-controls`、`role="tabpanel"` 关联。
4. Notes item 有 `tabIndex=0` 却没有 Enter/Space 激活等价行为。
5. TOC 使用 `href="#"` + click，面板打开后的焦点管理和关闭后恢复不完整。
6. Reader TOC/Notes/Search/AI 仅用 `aria-hidden`，没有 modal/dialog 语义、focus trap 或 body scroll lock。
7. Font theme/font option 是可点击 div 且未接线，不具按钮键盘语义。
8. Note editor 缺 `aria-modal`、可计算名称与完整焦点陷阱。
9. 40×40px Reader toolbar 触控目标低于常用 44×44px 建议值。
10. 无 skip link、无 `prefers-reduced-motion`。
11. Annotation 颜色只以英文颜色名表达，且未见完整 pressed/selected ARIA 状态。
12. Modern Library 移动端的 sidebar/right panel 无可达入口，是键盘与触控共同阻塞。

这些条目描述现状，不代表本次允许修改产品代码。

## 11. Persistence 与本地状态边界

| Location | Key/path | 内容 |
|---|---|---|
| localStorage | `reader3.library.viewMode` | grid/list |
| localStorage | `reader3.library.rightPanelCollapsed` | Library 右栏折叠 |
| localStorage | `reader3.library.bulkIndexingActive` | 中断提示标记 |
| localStorage | `reader3-font-settings` | font size、line-height |
| localStorage | `reader3-ai-panel-width` | AI panel 宽度 |
| localStorage | `reader3.ai.model.{book_uuid}.{provider}` | 书/provider 模型选择 |
| localStorage | `reader3.ai.activeConversation.{book_uuid}.{provider}` | 活动会话 ID |
| sessionStorage | `reader3.search.library` | Library 搜索条件 |
| sessionStorage | `reader3.search.reader.{book_id}` | Reader 搜索条件 |
| IndexedDB | `reader3_ai_assistant` | conversations、summaries |
| Server file | `config/ai_settings.json` | provider、默认模型、preferences、密钥 |
| Server file | `config/library_collections.json` | 集合 |
| Book dir | `book.pkl`, `book.epub`, `images/` | 图书元数据、原文件、图片 |
| Book dir | `notes.json` | annotations/notes |
| Book dir | `chroma_db/`, `ai_meta.json` | 向量索引与 AI 元数据 |
| Book dir | `ai_conversations/` | 服务端会话 |
| Optional server dir | `conversations/{book_uuid}` | 兼容/可配置会话位置 |

边界要求：浏览器“清数据”只影响当前 origin 的 IndexedDB；Library selection、打开的 panel、当前 TOC filter 等内存状态在刷新后丢失；API key 不进入 settings export。任何清理 `books/` 或索引目录的操作都不属于前端页面的隐式行为。

## 12. 状态处理总表

| Surface | Loading | Empty | Error | Disabled |
|---|---|---|---|---|
| Modern Library | book status / stats loading | 无 processed books | 单书/批量 index error | PDF |
| Collections | list loading | 无集合 | create/update/delete inline | 无 selection 时 add disabled |
| Library Search | searching | no results | HTTP error部分覆盖；network exception缺口 | semantic 未索引受限 |
| Library Chat | history/generating | 无历史/无消息 | provider/SSE inline error | All books、Collection |
| Settings | providers/models loading | provider/model empty | card/page status | provider disabled |
| Reader EPUB | 无显式 spinner；viewer 在 rendition 前为空 | 不适用 | EPUB 缺失错误块 | 首尾 Previous/Next |
| Notes | 无显式 loading；body 在返回前为空 | `你可以在这里记录本书的想法、划线、书签` | `loadAndRender` 无外层 catch，错误反馈缺失 | 无内容时 copy 直接返回；review始终可见但无 handler |
| Reader Search | searching/indexing | no results | API/index error | semantic/hybrid 未索引 |
| AI | history/generating | new conversation | provider/RAG/SSE error | provider不可用/生成期间控件 |

## 13. Known gaps、待确认与明确排除

### 13.1 已由源码确认的缺口

| ID | 缺口 | 证据/影响 |
|---|---|---|
| G-01 | Modern Library 移动 sidebar/right panel 无打开事件 | CSS 要求 `.is-open`，模板/`library.js` 没有触发器 |
| G-02 | Classic 搜索不可初始化 | 模板 `library-search-*` 与脚本 `library-panel-*` ID 不匹配 |
| G-03 | Reader 主题和字体选项 UI-only | 选项 DOM 可见但无事件/状态接线；仅字号/行距接线 |
| G-04 | `点评此书` 无 handler | Notes panel 可见按钮没有对应事件 |
| G-05 | A→Z 无排序方向切换 | `library.js` 始终升序 |
| G-06 | Library/Reader 搜索网络异常捕获不完整 | 两个 `performSearch` 的 fetch/json 外层都无完整 catch |
| G-07 | Reader panel 无完整 modal/focus contract | 只有可见/`aria-hidden` 切换 |
| G-08 | Classic/Settings 缺明确移动断点 | 依赖 grid/flex 自然换行 |
| G-09 | 无 reduced-motion 规则 | 全仓 CSS 搜索未发现 |

### 13.2 文档与实现差异

| 主题 | 实现现状 | 文档声明 / 待确认 |
|---|---|---|
| Library right width | token 为 340px | bulk indexing spec 中出现 320px；以 CSS 为当前实现 |
| Classic mode | 书架可渲染；搜索不可达 | README 将其概括为回退 UI |
| Reader content | 原始 EPUB + epub.js | 旧分页脚本仍在仓库，但模板未加载 |
| 移动 Library | main 可见，侧栏与右栏不可达 | CSS 形似已设计 off-canvas，但缺事件链 |
| AI storage | IndexedDB + server disk | 同步冲突、删除一致性未形成明确合同 |

### 13.3 待确认项

1. ~~在允许绑定 localhost 的环境中，用真实 Chrome 验证四页 computed layout、CSS error recovery 和字体加载。~~ **✅ 已完成（2026-08-15），见 §14 与 §14.1。**
2. ~~验证 390×844 下 Modern Library 的实际水平溢出，以及 off-canvas 是否存在模板外触发来源。~~ **✅ 已完成：`.library-right` 实测 `x=390, width=249`（视口 390），完全位于视口外；未发现模板外触发来源，`#right-collapse-toggle` 无效。见 G-13。**
3. 验证 Reader Left/Right 快捷键在 EPUB iframe、输入框与打开 panel 场景下的优先级。
4. 验证 notes/annotation 在 CFI 失效后的文本回退对重复 quote 的定位准确率。
5. 明确 IndexedDB 与磁盘 conversation 同 ID 冲突时的权威源和删除语义。
6. 明确 `Auto suggested questions`、主题、字体、`点评此书` 是计划功能还是应移除的占位 UI。

### 13.4 明确排除项

- 本规格不提出或实现新视觉方案、组件库、SPA 化、文件上传器或云同步。
- 不把 PDF、All books chat、Collection chat、suggested questions 写成已实现功能。
- 不把旧 `pagination.js`、历史 specs 或 FeedDock 内容当作当前 Reader 事实。
- 不规定后端未承诺的数据迁移、账号体系、权限模型或多用户协作。
- 不修改、删除或重建用户图书、索引、笔记、集合、AI 设置和对话。

## 14. 截图索引

目标目录：`designs/reader-pro-next/spec/screenshots/`。

**状态：22/22 已生成（2026-08-15）。** 采集环境：macOS + Chromium（gstack `/browse`），书库中仅 1 本已处理图书 `the-art-of-spending-money_data`（32 sections，未建索引）。Reader 截图取 spine index 8（`May I Have Your Attention Please`），因为 spine 0 是纯封面图、无法体现正文排版。Classic 行在**另起的 8124 端口**上采集（`READER3_LIBRARY_UI=classic`），采集后仅关闭自己启动的进程，用户原有 8123 服务未受影响。全程只触发读取型与可撤销 UI：未创建笔记/批注/集合，未提交任何表单，未向 AI provider 发送消息。

| Filename | Viewport | Surface/state | 实际观察 |
|---|---:|---|---|
| `01-library-desktop.png` | 1440×900 | Modern Library 默认 | 三栏完整；`Not indexed` pill；Dashboard 显示 Books 1 / Indexed 0 (0%) / Sections 32 / Chunks 0 |
| `01-library-mobile.png` | 390×844 | Modern Library 移动 | ⚠️ 左侧 collections 栏与右栏均不可达，仅剩中栏书格 |
| `02-library-selection-desktop.png` | 1440×900 | selection + bulk controls | 选中态正常，`#selected-count` = `1 selected` |
| `02-library-selection-mobile.png` | 390×844 | selection mobile | 选择模式可用；批量操作条挤压 |
| `03-library-search-desktop.png` | 1440×900 | 跨书 search | `Found 496 results across 1 books` |
| `03-library-search-mobile.png` | 390×844 | search panel 可达性 | ⚠️ **搜索已执行（496 结果）但面板不可见**，画面与 `01-library-mobile` 完全一致 |
| `04-library-collections-desktop.png` | 1440×900 | Collections / create dialog | `#create-collection-modal` 打开后取消，未提交 |
| `04-library-collections-mobile.png` | 390×844 | Collections mobile | ⚠️ 触发器 `#collections-create` 在隐藏侧栏内，**移动端无法创建集合**；此图由 `showModal()` 直接打开仅用于记录对话框布局 |
| `05-settings-desktop.png` | 1440×900 | Settings | 唯一未使用 dedao token 的页面；`GET /api/ollama/models → 503` 被静默吞掉 |
| `05-settings-mobile.png` | 390×844 | Settings | ⚠️ ollama 行 `Enabled` 文字溢出卡片右边界；`Not connected` pill 折行 |
| `06-reader-desktop.png` | 1440×900 | Reader 正文 | ⚠️ 正文占满 1440px，单行约 180 字符，`--dedao-content-max: 768px` 未生效 |
| `06-reader-mobile.png` | 390×844 | Reader 正文 | ⚠️ 两端对齐在 285px 栏宽下产生明显字间空隙（rivers） |
| `07-reader-toc-desktop.png` | 1440×900 | TOC | 面板**覆盖**正文而非挤压，当前章高亮为橙色 |
| `07-reader-toc-mobile.png` | 390×844 | TOC | 近全宽覆盖 |
| `08-reader-notes-desktop.png` | 1440×900 | Notes empty | 空态文案存在；⚠️ 面板显示「已读到 26%」而页脚同时显示「当前阅读至 20%」 |
| `08-reader-notes-mobile.png` | 390×844 | Notes empty | 全宽覆盖 |
| `09-reader-search-desktop.png` | 1440×900 | Reader Search | ⚠️ 结果区无空态文案（与 Notes 面板不一致） |
| `09-reader-search-mobile.png` | 390×844 | Reader Search | 抽屉占满视口，完全遮挡正文 |
| `10-reader-ai-desktop.png` | 1440×900 | AI panel | 实测宽约 545px，超出 `--dedao-ai-panel: 420px`；History 列约 140px，时间戳折 3 行 |
| `10-reader-ai-mobile.png` | 390×844 | AI panel | ⚠️ 390px 下仍保留桌面双栏；`Background` 按钮被裁出视口；头部按钮折两行 |
| `11-library-classic-desktop.png` | 1440×900 | Classic fallback | 完全独立的视觉语言：蓝色强调色、无封面图、不使用设计 token |
| `11-library-classic-mobile.png` | 390×844 | Classic fallback | 自然换行，无移动断点 |

### 14.1 本次截图新增的确认项

以下为 §13.1 之外、由真实浏览器实测新确认的问题，建议并入 gap 列表：

| ID | 缺口 | 证据 |
|---|---|---|
| G-10 | Reader 正文无最大宽度约束 | 1440×900 下正文横贯全宽；`--dedao-content-max: 768px` 定义了但未应用到 epub.js viewport |
| G-11 | 阅读进度存在两个互相矛盾的数值 | Notes 面板「已读到 26%」vs 页脚「当前阅读至 20%」，同屏同时可见 |
| G-12 | spine 0（纯封面）进度显示 100% | 打开第一页即显示「当前阅读至 100%」 |
| G-13 | 移动端右栏定位于视口之外且无法召回 | `.library-right` 实测 `x=390, width=249`（视口 390），`#right-collapse-toggle` 点击后不改变位置 |
| G-14 | Reader panel 互相堆叠并阻断工具栏 | TOC/Notes 打开时点击 `#reader-search-toggle` 超时；`toolbar.js:closeAllPanels()` 只关闭 search 与 AI |
| G-15 | 服务端口硬编码，无法并行运行两种 UI 模式 | `server.py:2407` `uvicorn.run(app, host="127.0.0.1", port=8123)`，无 env/CLI 覆盖 |
| G-16 | 界面语言混排 | 工具栏 `aria-label` 为英文（`Table of Contents`/`Notes`），字号面板与 Notes 页脚为中文（`放大字号`/`点评此书`）；Settings 页全英文 |
| G-17 | `/api/ollama/models` 503 被静默吞掉 | Ollama 未运行时 Settings 无任何提示，仅 console 报错（G-06 的具体实例） |

## 15. 复现与验收检查

在不受本次沙箱网络限制的本地开发环境中：

1. 保持用户 `books/` 不变；若没有 processed book，使用临时 `READER3_BOOKS_DIR` 处理一份现有 EPUB。
2. 运行 `uv run reader3-server`，确认 `http://127.0.0.1:8123` 可访问。
3. 使用独立 headed Chrome session，以 1440×900 和 390×844 逐项覆盖第 14 节。
4. 只触发读取型、空状态和可撤销的瞬时 UI；不要创建笔记、集合、批注或修改设置。
5. 切换 `READER3_LIBRARY_UI=classic` 时只关闭自己启动的服务，并使用同一临时图书目录。
6. 截图后核对页面文案、ARIA、computed breakpoint 和网络请求与本文；差异按第 0.1 节事实优先级回写。
