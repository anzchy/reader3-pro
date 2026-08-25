# ADR-0002: 阅读器用 epub.js 在 iframe 里渲染 book.epub，永不触碰 iframe 内部 DOM；CSS 分栏分页退役

| 字段 | 值 |
|---|---|
| Status | Accepted |
| Decision date | 2025-12-28 |
| Recorded date | 2026-08-25 |
| Record type | Retrospective |
| Original rationale known | No |
| Confidence | Medium |
| Current compliance | Full |
| Evidence | `src/reader3_app/web/server.py:692-699`（`serve_epub` 路由）、`server.py:757,765`（`epub_available` / `epub_url` 注入模板）；`src/reader3_app/web/static/js/epub-renderer.js:1-38`（`window.ePub(ctx.epubUrl)` 创建 Book）；`src/reader3_app/web/static/vendor/epub.min.js`（231094 B）＋`jszip.min.js`（97630 B）＝321 KB；`src/reader3_app/web/static/js/pagination.js:1-10`（自称「Full-Screen Paginated Reader」的分页模块，共 336 行）；`src/reader3_app/web/templates/reader.html:1737-1739`（脚本加载顺序：jszip → epub.min → epub-renderer，无 `pagination.js`）、`reader.html:1464`（`.pagination-container` 仍包着 `#epub-viewer`）、`reader.html:192-208`（CSS 多栏分页规则仍在文件里）、`reader.html:1903-1908`（`window.Pagination` 分支因脚本未加载而永远走不到）；`git show --stat 357fe2a`（commit subject「feat: Implement epub.js rendering and annotation enhancements」，无理由陈述） |
| Confirmation | `tests/contract/test_route_contracts.py:278-285`（`GET /read/{book_id}/book.epub` 返回 200/`application/epub+zip`，缺书返回 404）。iframe 边界的行为级确认（A/B/C 三重断言）**尚未落地**：见 Confirmation 小节 |

## Context and Problem Statement

阅读器需要把 EPUB 正文渲染给用户，并支撑文本选区标注（`<mark>` 高亮、CFI 锚定）。今天的实现方式是：服务端原样把 `book.epub` 文件通过 HTTP 提供，前端用 epub.js 在一个 iframe 里加载并分页渲染，宿主页 JS 只通过 `window.Reader3Epub` 这一层接口与 iframe 内容交互，不直接操作 iframe 内部 DOM。commit `357fe2a`（2025-12-28）引入了这套机制，替换掉此前的 CSS 多栏分页方案；替换后的产物 `pagination.js` 留在代码库里但不再被加载。

- **Observed State**：`server.py` 有专门路由 `GET /read/{book_id}/book.epub` 原样转发 EPUB 文件（`server.py:692-699`）；`reader.html` 只加载 `epub.min.js` / `jszip.min.js` / `epub-renderer.js`（`reader.html:1737-1739`），未加载 `pagination.js`；`pagination.js` 336 行、头注释自称「Implements horizontal pagination using CSS Multi-column Layout」（`pagination.js:1-10`），是死代码；`reader.html` 仍残留 `.pagination-container` 容器（`reader.html:1464`）、CSS 多栏规则（`reader.html:192-208`）、以及一处永远走不到的 `window.Pagination` 回退分支（`reader.html:1903-1908`）。
- **Original Rationale**：Unknown。commit `357fe2a` 的 subject 与正文只写了「Implement」类信息（集成 epub.js、支持全屏分页、CFI 标注），没有陈述为什么选 epub.js 而非继续维护 CSS 多栏方案，也没有讨论过其他候选。仓库里找不到更早的设计记录。
- **Current Assessment**（今天视角，推断非当年理由）：`docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:421` 把「绝不触碰 epub.js iframe 内部 DOM」定为 Phase 4B 的硬约束，理由是「标注锚定依赖 iframe 内 DOM 结构与空白……逐章文本相等但标注已错位」是评审认定的最可能失败模式；`docs/plans/20260817-frontend-ui-refactor/spec-frontend-design.md:1048` 把这条约束进一步细化成 A（文本序列不变）/B（body 结构签名不变）/C（CFI 往返解析）三重断言。也就是说，iframe 边界今天的价值不是「渲染引擎选型」本身，而是**它是 CFI 标注锚定的地基**——这层评估是本 ADR 写作时补上的，不是 2025-12-28 决定时就有的。

## Decision Drivers

- CFI（EPUB Canonical Fragment Identifier）标注锚定依赖 epub.js 生成的 iframe 内 DOM 结构；换渲染方式会让已存标注全部失锚。
- epub.js 的 `flow: paginated` 把分页发生在 iframe 内部，宿主页拿不到列宽与页数（`spec-frontend-design.md:216`），与此前 CSS 多栏方案不兼容，二者不能共存。
- Selection API 与 iframe 渲染对浏览器引擎高度敏感，牵动未来桌面壳的引擎选型（`plan-tech-stack-migration.md:646`）。
- vendored 依赖体积：`epub.min.js` + `jszip.min.js` 共 321 KB，占前端 JS+CSS 总字节的 56%（`plan-frontend-ui-refactor.md:1893`）。
- `window.Reader3Epub` 接口的消费方不止标注：阅读页内搜索（`search.js`）同样依赖 `getContentRoot()` / `onContentsReady()` 读取 iframe 内容（`annotation-host-contracts.md:132,134,143`），接口变更的影响半径比「只影响标注」更大。

## Considered Options

1. **epub.js 渲染在 iframe 内，宿主页只通过 `window.Reader3Epub` 接口交互**（选定，2025-12-28 起）——EPUB 标准格式的开源渲染库，处理 spine/分页/CFI；代价是 321 KB vendored 体积与 iframe 边界带来的接口层开销。
2. **自解析 HTML + CSS 多栏分页（`pagination.js`）**——commit `357fe2a` 之前的实现，把 chapter HTML 直接注入宿主页并用 CSS Multi-column Layout 分页。为什么不：标注锚定用的是 `{paragraph, start, end}` 式的宿主页 DOM 定位，无法承载 EPUB 标准分页与今天的 CFI 锚定需求；该实现已被替换，`pagination.js` 现为死代码，头注释仍误导性地自称是阅读器分页模块。
3. **其它 EPUB 渲染引擎（foliate-js、Readium 等）**——为什么不：`plan-frontend-ui-refactor.md:1938`「换渲染引擎（epub.js → 别的）……321 KB vendor 是既定成本；换引擎会同时推翻 CFI 锚定与 §6.0 三重断言」「无人；不做」。换引擎的代价被评估为与重写标注系统同级，本轮工程评审明确排除。

三者的取舍在今天的评审框架下是同一条：谁掌握「文本节点在 DOM 里的精确路径」，谁就能承载 CFI；方案 2 从不掌握（宿主页拼装 HTML，路径由业务代码决定），方案 3 理论上能掌握但代价等同重写，方案 1 是唯一已验证可行且已投入使用的路径。

## Decision Outcome

维持 epub.js + iframe 渲染 `book.epub`；`window.Reader3Epub` 是宿主页与 iframe 之间唯一允许的接口（`contracts/annotation-host-contracts.md:112`，冻结面 7 个成员，见 `:140`）；`reader.html` 的重构**只覆盖外壳**（工具栏/TOC/笔记/搜索/AI/标注工具条/章节导航），**绝不触碰 iframe 内部 DOM**，唯一例外是通过 `themes.override()` 注入的纯 CSS 属性（阅读主题、正文栏宽），且必须过 A/B/C 三重断言。

**明确不做**：
- 不恢复使用 `pagination.js`——CSS 多栏方案已被 epub.js 取代，不是并行选项。
- 不在本决定范围内清理 `pagination.js` 死文件、`.pagination-container` 残留 CSS、`window.Pagination` 死分支——那是独立的遗留清理任务，本 ADR 只记录它们的存在（见 Neutral）。
- 不为「重新引入自渲染分页」保留接口或兼容层。

### Confirmation 现状

`tests/contract/test_route_contracts.py:278-285` 只确认了传输层（HTTP 层能拿到 EPUB 文件、404 语义正确），不确认 iframe 渲染或标注锚定行为。A/B/C 三重断言中，A/B 是结构测试（对每次 `themes.override()` 改动跑），C 是 E2E，落点是 `docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` 的 R-6（`:104`）——该用例**尚未实现**（009 分支未合入），今天覆盖主题/字号/行距三个参数，栏宽参数要到 4B.3 才加入。在 R-6 落地前，本决定的核心断言（「iframe 边界改动不破坏 CFI 锚定」）只有设计文档层面的判据，没有机器执行的确认。

## Consequences

### Positive
- CFI 标注锚定有稳定的 DOM 结构基础，标准 EPUB 格式的分页、spine、目录解析交给成熟库处理，不必自研。
- iframe 边界给了标注系统一个明确的「不许碰」区域，降低了外壳重构（Phase 4B）误伤标注的风险；`window.Reader3Epub` 冻结面把这条边界具体化成 7 个纳入成员（`rendition`、`getContents()`、`getContentRoot()`、`getFrameElement()`、`onContentsReady(cb)`、`applyThemeSettings()`、`displaySectionIndex(i)`）与 2 个 deprecate 成员（`getContentDocument()`、`book`），而不是一句口号（`annotation-host-contracts.md:126-140`）。

### Negative
- vendored 依赖 321 KB，占 JS+CSS 总字节 56%（`plan-frontend-ui-refactor.md:1893`），且本轮重构不换引擎意味着这项成本长期存在。
- iframe 边界导致宿主页 JS 不能直接操作正文 DOM——一切标注、搜索高亮、主题应用都必须经 `window.Reader3Epub` 这层接口，接口一旦有遗漏或误改（如冻结面外的 `getContentDocument()` / `book` 被误用），故障是静默的（`annotation-host-contracts.md` K5 表）。
- epub.js 上游活跃度是外部依赖风险：库不再维护会直接卡住标注功能的迭代，且本决定已排除更换引擎作为选项。

### Neutral
- 桌面壳只能选 Electron，不能选 Tauri：`plan-tech-stack-migration.md:646` 记「epub.js 的 iframe 渲染、Selection API、CFI 标注对浏览器引擎高度敏感……Electron 统一 Chromium 是刚需」——这是本决定的派生约束，不是本决定本身要解决的问题。
- `pagination.js`（336 行）是死文件，其头注释「Implements horizontal pagination using CSS Multi-column Layout」具有误导性——`reader.html` 未加载它，且 `.pagination-container`（`reader.html:192-208`, `:1464`）与一处 `window.Pagination` 回退分支（`:1903-1908`）是遗留残骸而非生效代码。这是文档/代码缺陷，非本决定内容，留待遗留清理任务（见 Confirmation）处理。
- iframe 内容更改必须过 A（文本序列）/B（`bodySignature` 结构签名）/C（CFI 往返解析）三重断言，判据唯一定义处是 `spec-frontend-design.md` §6.0（`:1048`），其余文档只引用不复述。

## Revisit When

- epub.js 上游连续一年无新发布（体积/维护性代价超过收益时需重新评估换引擎）。
- CFI 标注锚定被 012（存储格式迁移）或 014（TS 前端阅读器重写）替换为其它锚定机制——届时 iframe 边界存在的理由随之改变，需要新 ADR 而非修订本文。
- 013（TS 前端外壳）把前端 bundle 预算收紧到容不下 321 KB vendored 依赖。

## Related

- ADR-0005、ADR-0008、ADR-0013（标注/CFI 与前端外壳相关的后续决定，编号预留于 `docs/adr/0000-use-adrs.md`「首批 0001–0013」）
- `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:421`（iframe 边界约束）、`:646`（Electron vs Tauri 裁决）——本 ADR 是这两处约束「为什么」的记录来源之一，原文保留、不改写。
- `docs/plans/20260817-frontend-ui-refactor/spec-frontend-design.md` §6.0（`:1048`，A/B/C 三重断言的唯一定义处，本 ADR 不复述）。
- `docs/plans/20260817-frontend-ui-refactor/contracts/annotation-host-contracts.md` K5（`window.Reader3Epub` 冻结面枚举）。
- `docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` R-6（断言 C 的 E2E 落点，`:104`）。
