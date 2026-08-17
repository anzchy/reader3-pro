# 前端 UI 重构计划（2026-08-17）

把 Reader3 Pro 的前端从「Jinja 模板 ＋ 五千行原生 JS」重做成 TypeScript ＋ Vite 多页、带完整设计系统与降级状态的界面，并给全部交互配上可失败的测试。

本文是**唯一的前端工作项来源**。这份计划下面**没有 `tasks/` 目录**——所有工作项都写在本文第 4 节的 `### WI-N:` 标题里，一条一条按顺序读、按顺序做。

---

## 0. 怎么跑

工作项用 `### WI-N:` 的 H3 标题标记，编号从 WI-1 到 WI-20 连续，`/tdd-guardian:workflow` 的 plan 阶段直接抽取这些标题。测试矩阵在第 5 节，按 WI 归属分组。

分批跑，一次一个 Track。下面这一整行就是要粘进去的内容，**它自己一行、前后没有任何标记符号**，整行选中复制即可：

/tdd-guardian:workflow 按 docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md 执行前端重构的 Track D 部分，范围是 WI-1 到 WI-8，测试矩阵见该文档第 5 节对应小节，断言目标一律用 data-testid 或 ARIA role 加 name，禁止 class 选择器和 nth-child，每个工作项的验收标准必须逐条二元判定

换 Track 时，把上面那行里的「Track D 部分，范围是 WI-1 到 WI-8」整段替换成下面对应的一段（引号不要带进去）：

- Track 4A —— 「4A 前端外壳部分，范围是 WI-9 到 WI-13」
- Track 4B —— 「4B 阅读器部分，范围是 WI-14 到 WI-19」
- Phase 5 —— 「发布体验部分，范围是 WI-20」

调用串里不要出现反引号、美元括号、分号、双与号、双竖线、尖括号和竖线——工作流的输入契约会直接拒绝。上面那行已经按这个约束写过，别自己往里加符号。

---

## 1. 事实基线

动手之前必须认下面这些事实，否则会把「现状」当成「目标」实现。

### 1.1 原型是目标形态，截图不是

`designs/reader-pro-next/` 里的 `index.html` / `*.jsx` 是**目标形态的可执行规格**——DOM 结构、类名、token 值、交互状态机、a11y 实现、空态与错误文案，全部按它翻译。

`designs/reader-pro-next/spec/screenshots/` 下的 **22 张 PNG 是现状 UI 的取证**，记录的是重构**之前**长什么样。它们**不是设计目标，也不是验收依据**。任何一条验收标准都不许写成「与截图一致」。

原型用 React 18 ＋ 浏览器内 Babel，那是**可执行规格的实现手段，不是生产选型**。生产端是 TypeScript ＋ Vite 多页、不引框架：原型里的 React state 在生产端翻译成「一个显式状态对象 ＋ 每页一个 render 函数」。

### 1.2 不可移植的三件事

| 项 | 原型做法 | 生产做法 | 为什么不能照搬 |
|---|---|---|---|
| 分页 | CSS multicolumn ＋ 普通 DOM 上 `translateX` | epub.js `flow: paginated`，内容在 iframe 里 | 宿主完全不同。`usePagination` 只能当**行为参考**，不是实现参考 |
| 标注锚定 | `{paragraph, start, end}` 字符偏移 | 现有 CFI ＋ `quote` / `prefix` / `suffix` | **永远不要**用原型的偏移方案替换现有锚定。已存标注会全部失锚 |
| 数据流 | `data.jsx` 同步本地状态、零网络 | 真实 `fetch` ＋ SSE | 原型每个面板都缺 loading / error / empty；**加载骨架从来没做过** |

⚠️ **偏移单位陷阱**：原型的字符偏移是 UTF-16 code unit，`search_service.py` 的偏移是 Unicode code point。两端任何一次对齐都要显式转换，不能默认相等。

有一条**反向可移植**：原型为了渲染重叠标注，把段落文本在所有边界处切开再拼，而不是用 `Range.surroundContents()`（跨元素会抛）。这个做法落到 WI-14 的 `renderer.ts`。

### 1.3 已经做完的事，不要写回 TODO

| 事实 | 状态 | 出处 |
|---|---|---|
| **0.1** 重新处理 EPUB 不再删光标注 | **已完成** | [`tasks/007-hygiene-and-contracts.md`](../20260816-tech-stack-migration/tasks/007-hygiene-and-contracts.md) |
| **0.7** 删死代码（`SearchIndex` / `BookIndex.from_book_pkl` / `SearchIndex.build_from_library`） | **已完成** | 同上。⚠️ `BookIndex` / `ChapterIndex` 两个 dataclass **仍是活代码，不要动** |
| **0.6** 事实性修复 | **部分完成**——`.gitignore` 合并冲突标记已修；版本号对齐与示例配置补齐**未做** | 同上 |
| **0.2 / 0.3 / 0.4 / 0.5 / 0.8** | **未开始** | 同上 |

**三处 token 悬空引用是 007 已经修好的**，本计划只消费结果、不重做：

| 悬空引用 | 修法 |
|---|---|
| `--r3-warn` / `--r3-danger` | 重命名为 `--r3-warning` / `--r3-error`，并补齐四个同名 `-subtle` 底色 |
| `--r3-sidebar-w` / `--r3-right-w` | 补定义（否则 `grid-template-columns` 整条失效，三栏塌成默认布局） |
| `--r3-text-quiet` | 补 `:root` 下的定义（它是 chrome 轴的角色色，此前只在阅读主题块里出现过） |

⚠️ **对比度不达标的是浅色档的 500**，不是夜间档——白底上绿 2.28 / 琥珀 2.15 / 红 3.76 / 青 3.68，已按实测改成浅色 700 档、夜间 400 档。这一点在旧记录里被写反过，不要沿用错的版本。

0.8 要做的是**不让悬空引用再长出来**（lint 本身），不是再修一遍这三处。

### 1.4 现状 UI 的实测缺陷（必须修，且必须有断言）

设计规格 §1 / §1.5 记录的实测结论，逐条对应到下面的 WI：

- **D1–D4**：字体面板是纯装饰（点了不生效）、全站没有夜间模式、`settings.html` 在设计系统之外、完全没有响应式。
- **D5**：正文没有最大宽度限制，1440×900 下一行 180 字符。
- **D6**：面板覆盖并挡住工具栏——TOC 或 Notes 打开时点 `#reader-search-toggle` 会超时，因为 `toolbar.js` 的 `closeAllPanels()` 只关搜索和 AI。
- **D7**：同一时刻两个互相矛盾的进度值（26% 与 20%），且只有封面的 spine 0 显示 100%。

原型自身实测出的三个翻页缺陷（`designs/reader-pro-next/README.md`），带进生产端当 4B 的测试用例：

1. 连续翻页只前进一步——处理器读的是上一次渲染的页码，epub.js `rendition.next()` 是异步的，快速按键在陈旧状态上排队。
2. 跨章快翻会跳两章——必须锁到重新测量完成。
3. 向前跨章落到新章第 1 页，导致上一章永远读不到——向前跨章必须落到**最后一页**。缺陷 3 **在当前生产端是否存在尚未验证**，先在 `baseline-1b` 里加一条 E2E 定性。

### 1.5 移动端存在功能性不可达

390×844 实测四处（设计规格 §7）：书库右栏在 `x=390, width=249` 完全够不着；左栏未渲染导致 `#collections-create` 够不着；AI 面板仍是桌面双栏、`Background` 被裁掉；设置页 ollama 行 `Enabled` 溢出。这不是「样式不好看」，是**功能不可达**。

---

## 2. 权威范围

同一个事实只有一处定义。本文件夹是这些事实的 canonical 定义点：

| 事实 | 唯一定义处 |
|---|---|
| 双层 design token（Tier 1 `--p-*` → Tier 2 `--r3-*`）与**两根主题轴**（chrome `data-theme` × reading `data-reading-theme`） | `spec-frontend-design.md` §3.3 |
| 八个基础组件的规格与变体 | `spec-frontend-design.md` §5 |
| 设置页 / 书库页 / 阅读器逐页规格 | `spec-frontend-design.md` §6.1 / §6.2 / §6.3 |
| 降级状态 DEG-S1–DEG-S5 的定义、色彩语义、可关闭性 | `spec-frontend-design.md` §6.4 |
| 响应式断点与移动端实测失败项 | `spec-frontend-design.md` §7 |
| a11y 六项 | `spec-frontend-design.md` §8 |
| iframe 边界的 A/B/C 三重断言（含 `bodySignature`） | `spec-frontend-design.md` §6.0 |
| 标注宿主契约 K1–K6 | `contracts/annotation-host-contracts.md` |
| **前端工作项 WI-1–WI-20 与前端测试矩阵** | **本文第 4 / 5 节** |

下面这些**不由本计划定义**，只引用：

| 事实 | 定义在 |
|---|---|
| 分支编号分配（全仓库唯一真相源） | [`20260816-tech-stack-migration/plan-tech-stack-migration.md` §9](../20260816-tech-stack-migration/plan-tech-stack-migration.md) |
| Phase 依赖图、各 Phase 进入 / 退出门槛、soak 门槛 | 同上 §9.1 / §7 |
| `data-testid` 命名 canonical 正则、三条 lint 的边界 | 同上 §6（0.5、0.8） |
| Playwright E2E 用例 ID（`R-1`…`R-6` / `W-1`…`W-10` / `K-1`…`K-6` / `X-1` / `X-2`）与激活分组 | [`tasks/009-e2e-annotations.md`](../20260816-tech-stack-migration/tasks/009-e2e-annotations.md) |
| API v1 冻结清单、覆盖率门槛数值 | [`tasks/008-test-safety-net.md`](../20260816-tech-stack-migration/tasks/008-test-safety-net.md) |
| 两文件提交协议、读取状态机三态 | [`plan-tech-stack-migration.md`](../20260816-tech-stack-migration/plan-tech-stack-migration.md) Phase 3 |

**testid 命名**：canonical 正则在 0.5，写在技术栈迁移计划的代码块里——**从代码块里复制，不要从 Markdown 表格里复制**（表格里 `|` 被转义成 `\|`）。本计划涉及的所有新建元素一律 `lib-` / `rd-` / `set-` 三前缀之一。原型现有 134 个 testid **零个合规**，其中 24 个带 `reader-` / `library-` 前缀的**看起来像合规但不是**。重命名本身归 0.5，本计划只负责新元素首次就写对。

**分支落点**：Track D → `010-design-degradation-states`；WI-9–WI-13 → `013-ts-frontend-shell`；WI-14–WI-19 → `014-ts-frontend-reader`；WI-20 → `015-launch-experience`。编号来源见上表第一行。

---

## 3. 前置契约

三项在 `007-hygiene-and-contracts` 实施、**本计划只消费不重述**：

- **0.4** `escapeHtml` 收敛 —— 决定 WI-11 里 `escape.ts` 的形状。
- **0.5** canonical testid 正则 ＋ 选择器 lint ＋ 命名 lint —— 是本计划全部测试矩阵的选择器基础。
- **0.8** token 悬空引用 lint —— 是 DEG-S1–DEG-S5 横幅不静默失色的保证（`var(--x, fallback)` 有 fallback 也算违规）。

WI-1 到 WI-20 全部以这三项落地为前置，下面各 WI 的「前置 WI」一栏不再重复写。

**源码根目录**：TypeScript 源码放哪里由 WI-9 定，构建产物固定落 `src/reader3_app/web/static/dist/` 且**提交进 git**。下文用 `{前端源码根}` 指代 WI-9 确定的那个目录。

### 3.1 降级状态是两次交付，不是一次

| 形态 | 谁交付 | 门槛 |
|---|---|---|
| **朴素形态** | `012-storage-format` 自己写，落到现有 Jinja 模板 | Phase 3 的退出门槛只要求 DEG-S1–DEG-S4 **可见** |
| **重做形态** | 本计划 WI-1–WI-6 定义，WI-13 / WI-16 落地 | 按设计规格 §6.4 全套 |

012 写朴素横幅时**直接抄 WI-2–WI-5 的文案与状态定义**——两次交付的文案和触发条件必须是同一份，只有视觉表现不同。所以 Track D 的文案与状态定义要在 012 开工前定下来，哪怕组件还没建。

### 3.2 原型现有的降级只有 collection 级

原型只做了 collection 级别的 `stale`（`.stale-dot` ＋ 清理确认弹窗），**书籍级与全局级一个都没有**。没有 UI 就等于静默失败——这是本计划做 DEG-S1–DEG-S5 的全部理由。原型那个 collection 级 `stale` 可以当视觉参考，但它的粒度不对，不能直接复用。

---

## 4. 工作项

### WI-1: DegradeBanner 基础组件

**范围**：`{前端源码根}/components/degrade-banner.*`（组件本体 ＋ 样式）；`designs/reader-pro-next/components.jsx` 只作参考，不改。

**前置 WI**：无（Track D 的第一项）。

**做什么**：建一个所有降级横幅共用的基础组件，五个状态在它上面派生。

- `tone` 两档：`warn`（DEG-S1 / DEG-S2 / DEG-S4）、`danger`（DEG-S3 / DEG-S5）。
- `dismissible` 布尔，关闭状态存 `sessionStorage`；**DEG-S5 不接受这个属性**。
- 自带 `role="status"` ＋ `aria-live="polite"`。**不许复用原型的 `LiveRegion`**——那个是 sr-only 的，只能播报、不能当可见横幅用。
- 内容用 children 插槽，不是 `primaryLabel` 字符串——各状态的操作按钮数量和形态不一样。
- **testid 逐状态给**，不是共用一个 `degrade-banner`：`rd-degrade-s1` / `lib-degrade-s2` / …。`acceptance-p3` 要断言「出现的是哪一个状态」，共用 testid 断不出来。

**硬约束（对比度实测）**：四个 `-subtle` 底色对页面底只有 1.10–1.22:1（浅色）/ 1.15–1.32:1（夜间）。**只有底色的横幅在视觉上等于不存在**——必须同时有边框或图标，边框用该状态的前景色本身（不新增 border token）。

**涉及 testid**：`rd-degrade-s1`、`lib-degrade-s2`、`lib-degrade-s3` / `rd-degrade-s3`、`lib-degrade-s4`、以及各自的主操作按钮 `*-action` 与关闭按钮 `*-dismiss`。

**涉及降级状态**：全部五条的载体。

**验收标准**：

1. 渲染 `tone="warn"` 与 `tone="danger"`，两者的 `border-color` 计算值不同，且都不等于 `transparent`。
2. 组件根元素的 `role` 属性等于 `status`，`aria-live` 属性等于 `polite`。
3. 页面内不存在两个 `aria-live` 区域同时承载同一条降级文案（即横幅不经由 `LiveRegion` 二次播报）。
4. `dismissible=true` 时点关闭按钮后组件从 DOM 移除，且 `sessionStorage` 里出现对应键；同一会话内重新挂载不再出现。
5. `dismissible=false` 时不渲染关闭按钮（查询关闭按钮 testid 返回 0 个元素）。
6. 五个状态各自渲染出的根元素 testid 互不相同。
7. token 悬空 lint（0.8）在本组件样式文件上通过。

---

### WI-2: DEG-S1 标注 stale

**范围**：阅读器顶部横幅；Notes 面板逐条 stale 标记；「查看原文摘录」入口。

**前置 WI**：WI-1。

**做什么**：`notes.json` 指纹与当前 spine 指纹不匹配时，标注停止套用，但**一条都不删**。

- 横幅文案必须明说「标注暂停套用，**未删除**」。少了「未删除」三个字，用户会以为数据没了。
- 「查看原文摘录」入口不依赖 CFI——用 `Annotation` 的 `quote` / `prefix` / `suffix` 三个字段拼出摘录。CFI 在 stale 场景下正是失效的那个东西。
- Notes 面板每一条 stale 标注单独挂 stale 角标，不是只在面板顶部放一条汇总。

**涉及 testid**：`rd-degrade-s1`、`rd-degrade-s1-excerpt`（查看原文摘录）、`rd-note-stale-badge`（逐条角标）。

**涉及降级状态**：DEG-S1。

**验收标准**：

1. 构造指纹不匹配的 `notes.json`，加载阅读器后 `rd-degrade-s1` 可见。
2. 该横幅的可见文本同时包含「暂停套用」与「未删除」。
3. 同一场景下 `GET /api/notes/{book_id}` 返回的标注条数与断言前一致（**一条不少**）。
4. 正文里不存在任何标注渲染标记（标注套用确实停了）。
5. 点 `rd-degrade-s1-excerpt` 后出现的摘录文本包含该标注的 `quote` 字段原文。
6. 摘录渲染路径不读取 `cfi` 字段（把 `cfi` 置空后第 5 条仍通过）。
7. Notes 面板里每条 stale 标注都有一个 `rd-note-stale-badge`，数量等于 stale 标注条数。

---

### WI-3: DEG-S2 索引 stale 与状态枚举收敛

**范围**：书卡状态角标；搜索面板顶部提示条与重建按钮；`STATUS_META` 及其全部消费点。

**前置 WI**：WI-1。

**做什么**：给索引状态加第五态，并把两处**已经写错的** fallback 一起修掉。

`STATUS_META` 现在四态：`not_indexed` / `indexing` / `indexed` / `error`。指纹不匹配是第五态。

两个陷阱：

- **testid 不能拼字符串**。原型写的是 `data-testid={"status-" + props.status}`，违反设计规格 §4 规则 5（testid 的值必须是**字符串字面量**）。改成五个字面量的静态映射表。「加个 lint 例外」这条路**不成立**——lint 例外会让整条命名约束失效。
- **没有 fallback，且现有两处 fallback 都是错的**。`reader.jsx` 直接 `window.STATUS_META[indexStatus].label` 取值，遇到未知状态直接抛；`StatusPill` 的 `|| STATUS_META.not_indexed` **本身就是 bug**——把未知状态显示成「未索引」，用户会去点「开始索引」。正确做法是收敛成一个共用的 `statusMeta(s)`，未知状态返回中性的 `unknown`（灰点、「状态未知」），不冒充任何已知态。

**改动顺序**：先改 `STATUS_META` 与所有消费点，**再**让任何一端发出新状态值。消费方先行的枚举扩展，反过来会在两次部署之间炸掉。

搜索面板顶部的提示条用 **WI-1 的 `DegradeBanner`**，不是复用原型那个 `index-banner`——后者硬编码了「Semantic index」文案、住在搜索抽屉里，只能当视觉参考。

**涉及 testid**：`lib-status-not-indexed` / `lib-status-indexing` / `lib-status-indexed` / `lib-status-error` / `lib-status-stale` / `lib-status-unknown`（六个字面量）、`lib-degrade-s2`、`lib-degrade-s2-reindex`。

**涉及降级状态**：DEG-S2。

**验收标准**：

1. 源码里不存在对 `data-testid` 属性的字符串拼接或模板插值（命名 lint 通过，且无 lint 例外条目）。
2. 六个状态值分别渲染出六个互不相同的 testid。
3. 传入一个不在枚举内的状态值：不抛异常，渲染出 `lib-status-unknown`，其可见文本为「状态未知」，且**不等于**「未索引」的文案。
4. 未知状态下不渲染「开始索引」操作按钮。
5. `statusMeta` 只有一处定义，`reader` 与 `library` 两侧都从它取值（源码内该符号的定义处计数等于 1）。
6. 指纹不匹配时搜索面板顶部出现 `lib-degrade-s2`，且它的根元素带 WI-1 的边框（`border-color` 非 `transparent`）。
7. 点 `lib-degrade-s2-reindex` 触发重建请求一次；重复快点两次只发出一次请求。

---

### WI-4: DEG-S3 pickle 回退全局告警

**范围**：全局 chrome（书库与阅读器都要显示）；未迁移书目清单的展开与折叠。

**前置 WI**：WI-1。

**做什么**：`READER3_ALLOW_PICKLE=1` 启动时，两个页面都显示 danger 档告警条，点击展开未迁移书目清单。

这是五条里**唯一的全局降级**。原型没有共享的顶部 chrome——要么建一个，要么接受两个挂载点。选哪个都行，但**必须两页都出现**，不能只做书库。

清单要能折叠，且有条数上限——未迁移的书可能有几十本，全展开会把页面顶掉。

**涉及 testid**：`lib-degrade-s3` / `rd-degrade-s3`、`lib-degrade-s3-toggle`、`lib-degrade-s3-list`、`lib-degrade-s3-more`（超过上限时的「还有 N 本」）。

**涉及降级状态**：DEG-S3。

**验收标准**：

1. `READER3_ALLOW_PICKLE=1` 时，书库页与阅读器页**都**能查到对应的 s3 testid 元素且可见。
2. 未设该环境变量时两页都查不到（元素数为 0）。
3. 该横幅的 `tone` 解析为 danger（前景色计算值等于 `--r3-error` 的解析值）。
4. 默认折叠：`lib-degrade-s3-list` 初始不可见；点 `lib-degrade-s3-toggle` 后可见，再点恢复不可见。
5. 未迁移书目超过上限时渲染 `lib-degrade-s3-more`，其文本包含剩余条数；不超过时该元素不存在。
6. 展开后列表里每一项的文本等于对应书的书名（与 `/api/library` 返回值逐条比对）。

---

### WI-5: DEG-S4 存储格式与迁移进度

**范围**：书卡上的 `storage_format` 角标；迁移进行中的进度显示；失败项逐条重试。

**前置 WI**：WI-1、WI-3。

**做什么**：给每张书卡加存储格式角标，并在 `--migrate` / `--migrate-all` 期间显示进度与失败项。

**关键区分**：`storage_format` 角标和索引状态 `StatusPill` 是**两个独立维度**。一本书完全可以「已索引 ＋ 旧格式」。两者不能合并成一个角标，也不能让其中一个覆盖另一个。

失败项**每条自己的 testid ＋ 自己的重试按钮**——批量失败里只能整批重试等于逼用户重跑已成功的部分。

**涉及 testid**：`lib-storage-format-badge`、`lib-degrade-s4`、`lib-degrade-s4-progress`、`lib-migrate-failed-item`、`lib-migrate-retry`。

**涉及降级状态**：DEG-S4。

**验收标准**：

1. 一本「已索引 ＋ 旧格式」的书，其书卡上 `lib-status-indexed` 与 `lib-storage-format-badge` **同时可见**。
2. 存储格式为新格式时 `lib-storage-format-badge` 不渲染（元素数为 0），或渲染出与旧格式不同的文本——两者取其一，实现选定后测试固定断言该行为。
3. 迁移进行中 `lib-degrade-s4-progress` 的文本随进度变化至少更新一次（两次采样值不同）。
4. 三项失败时页面上有 3 个 `lib-migrate-failed-item`，每个内部各有 1 个 `lib-migrate-retry`。
5. 点其中一个 `lib-migrate-retry` 只对该项发出重试请求（请求体里的书 id 等于该项对应的书 id），其余两项不发请求。
6. 重试成功后该项从失败列表移除，剩余 2 个 `lib-migrate-failed-item`。

---

### WI-6: DEG-S5 写冲突对话框

**范围**：新增 `ConflictDialog`；`Modal` 的 `data-testid` 改为必填 prop。

**前置 WI**：WI-1。

**做什么**：notes 乐观并发失败时弹出「保留我的 / 采用远端」二选一，**不得静默丢写**。这是五条里唯一会真正丢用户数据的降级。

**为什么不能复用 `Modal`**：原型的 `Modal` 有三条互不相关的关闭路径——硬编码的 `×` 按钮（testid `modal-close`）、`.overlay` 上的 `onMouseDown`、`useFocusTrap(ref, true, onClose)` 里的 Esc。它还硬编码了 `role="dialog"` 和 `data-testid="modal"`。冲突对话框需要的是**零关闭路径**，改造 `Modal` 会同时破坏它现有的全部用法。

裁定：**新建 `ConflictDialog`**，`role="alertdialog"`，两个按钮是**仅有的**出口。同时把 `Modal` 的 `data-testid` 从硬编码改成**必填 prop、无默认值**——硬编码的 `modal` 会让多个弹层撞同一个 testid。

三个落地细节：

- **不要改 focus trap 这个 hook**。给它传 `undefined` 当 `onClose`，Esc 会被吞掉且什么都不做——这正是想要的行为。改 hook 会影响所有用它的组件。
- **用 `div` 不用原生 `<dialog>`**。设计规格 §5 写的是保留 `<dialog>`，但原型已经是 `div.overlay`；且原生 `<dialog>` 的 Esc 发生在浏览器层，要靠 `cancel` 事件 ＋ `preventDefault()` 才拦得住，而「关不掉」正是 `ConflictDialog` 的全部意义。**这里按 `div` 实现，并把这条差异写回设计规格 §5。**
- **不许有死路**。远端数据取不到时，降级成「保留我的」单选项，**不是**把两个按钮都禁用——两个都禁用等于对话框既关不掉又点不动。

**涉及 testid**：`rd-conflict-dialog`、`rd-conflict-keep-mine`、`rd-conflict-take-remote`；`Modal` 各调用点各自的 testid。

**涉及降级状态**：DEG-S5。

**验收标准**：

1. `ConflictDialog` 根元素 `role` 属性等于 `alertdialog`。
2. 对话框内查询关闭按钮 testid 返回 0 个元素。
3. 按 Esc 后对话框仍在 DOM 中且可见。
4. 点击遮罩区域后对话框仍在 DOM 中且可见。
5. 焦点在对话框打开后落到对话框内部，Tab 循环不会离开对话框（连按 N＋1 次 Tab 后 `document.activeElement` 仍在对话框子树内）。
6. 点「保留我的」发出一次带本地版本的写请求，随后对话框消失；点「采用远端」发出一次拉取并覆盖本地，随后对话框消失。
7. 远端不可达时只渲染 `rd-conflict-keep-mine`，且它的 `disabled` 属性为假。
8. `Modal` 不传 `data-testid` 时构建期或运行期报错（类型必填 ＋ 运行时断言），源码里不存在 `data-testid="modal"` 这个默认值。
9. 冲突场景下用户的本地改动在任一分支后都不丢：断言写请求的 body 或最终 `GET /api/notes` 结果里包含本地文本。

---

### WI-7: 契约 2 收口——高亮色改 RGB 三元组

**范围**：`{前端源码根}` 下的 token 定义与九处 `color-mix` 使用点；**夜纸**（reading 轴 `night`，以及 `auto`@dark chrome）下的高亮呈现方式。

> `--r3-hl-*` 属 **reading 轴**，不属 chrome 轴——高亮是画在纸上、在 iframe 里的（§11-R7 规则 3）。下文的「夜间」一律指夜纸，不指界面暗色。

**前置 WI**：无（可与 WI-1 并行；WI-10 消费它的产物）。

**做什么**：这条契约**是 alpha 问题，不是颜色问题**。

九处 `color-mix`（不是八处）：`.anno-chip.is-*` ×4 用 35%、`.marker.is-*` ×4 用 45%、`.anno.is-note` ×1 用 18%，全是 `color-mix(in srgb, X N%, transparent)`——在 sRGB 里这就是纯 alpha。所以「chip 档该定什么显式颜色值」是个**假问题**。

裁定：**存 RGB 三元组，alpha 留在使用点**。

```css
--p-hl-yellow-rgb: 251 191 36;
--p-hl-yellow: rgb(var(--p-hl-yellow-rgb));
.anno-chip.is-yellow { background: rgb(var(--r3-hl-yellow-rgb) / .35); }
.marker.is-yellow    { background: rgb(var(--r3-hl-yellow-rgb) / .45); }
```

落选方案与理由：`color-mix()` 就是要被删掉的那个东西；`rgb(from var(--x) r g b / .35)` 是相对颜色语法，支持度比 `color-mix` 还差；8 位十六进制要手调 16 个值。三元组 ＋ 斜杠 alpha 从 Safari 12.1 / Chrome 65 起可用，零 fallback。

**夜间必须保留 alpha**。45% 合成 vs 100% 实色，正文对比度实测：黄 6.63 → **3.02** ✗、绿 7.45 → **3.94** ✗、粉 8.42 → 5.06、蓝 8.03 → 4.74。

更硬的结论：paper-night 底 L=0.0075、正文 `#c2ccdb` L=0.5977 —— 「块对页面 ≥3:1」要求 L≥0.1224，「正文对块 ≥4.5:1」要求 L≤0.0939，**解集为空**。所以夜间高亮**必须有非背景提示**（下划线 / 左侧竖条 / 波浪线）。浅色不受影响（45% 黄压白仍有 9.95）。

另有 D-5 遗留：`.anno.is-note` 用的 18% `--blue-500` 在 D-5 之后是品牌色，会和选区、focus ring 撞色，一并换掉。

**涉及 testid**：无新增（本项改的是 token 与样式）。

**涉及降级状态**：无。

**验收标准**：

1. 全仓库 CSS 里 `color-mix(` 出现次数为 0。
2. 九个原使用点全部改为 `rgb(var(--r3-hl-*-rgb) / <alpha>)` 形式，alpha 值分别为 .35（4 处）、.45（4 处）、.18（1 处，且底色不再是品牌蓝）。
3. token 悬空 lint（0.8）通过，`--r3-hl-*-rgb` 全部有定义。
4. **亮纸**（`paper` / `sepia` / `green` ＋ `auto`@light）下 marker 四色合成后与该纸墨色的对比度均 ≥4.5:1（用计算值断言，不靠肉眼）。
5. **夜纸**（`night` ＋ `auto`@dark）下四色 marker 元素**除背景外**还带至少一个非背景视觉提示：断言其 `text-decoration-line` 非 `none`，或 `border-left-width` 大于 0。
6. 夜纸下 marker 的背景色 alpha 通道不等于 1。
7. `.anno.is-note` 的解析背景色不等于 `--r3-accent` 的解析色。

---

### WI-8: Skeleton 加载骨架

**范围**：新增 `Skeleton` 组件；书库卡片与统计数字的加载态。

**前置 WI**：无。

**做什么**：原型 README 明说加载骨架从来没做过，设计规格 §5 也把 `Skeleton` 标为不存在。建出来，用在书库卡片与统计数字上。

- 必须尊重 `prefers-reduced-motion`——开了就是静态的，不能有动画。
- **不给 testid**。它是过渡态，断言它的存在会引入时序 flake。断言它**之后**的东西：数据到了之后卡片出现。

**涉及 testid**：无（刻意不给）。

**涉及降级状态**：无。

**验收标准**：

1. 组件源码内不含 `data-testid` 属性。
2. `prefers-reduced-motion: reduce` 下，骨架元素的 `animation-name` 计算值为 `none`（或 `animation-duration` 为 0s）。
3. 未开 reduced-motion 时 `animation-name` 不为 `none`。
4. 书库首屏在数据返回前，`lib-book-grid` 内的骨架占位数量大于 0；数据返回后骨架数量为 0 且书卡数量等于返回条数。
5. 测试矩阵中不存在任何以骨架为断言目标的用例（人工核对第 5 节，此条为文档级验收）。

---

### WI-9: 4A.0 工具链

**范围**：Vite 多页配置、TypeScript 配置、`dependency-cruiser` 配置、三条 lint 的接入、`static/dist/` 的提交策略。

**前置 WI**：无（4A 的第一项）。

**做什么**：把构建链搭起来，并把 0.5 / 0.8 的三条 lint 接进同一条命令。

- Vite 多页：书库 / 阅读器 / 设置三个入口。
- 产物落 `src/reader3_app/web/static/dist/`，**提交进 git**（决策：不在 CI 里现构建）。
- `dependency-cruiser` 先接进来，规则在 WI-14 填。
- Node 与 Vite 版本固定，带 lockfile。

**跨计划**：`pyproject.toml` 的 `package-data` 要跟着改——vendored 文件从 `static/js/vendor/` 换成 Vite 产物，0.2 修好的非递归 glob 会再次失配。wheel 内容测试断言 `dist/` 进了 wheel，归 `008-test-safety-net`。这两条的实施在技术栈迁移那侧，本 WI 只负责不把它们漏掉。

**涉及 testid**：无。

**涉及降级状态**：无。

**验收标准**：

1. 干净克隆后一条命令完成构建，`static/dist/` 下三个入口的产物都存在。
2. 连续两次构建的产物字节一致（可重复构建）。
3. 选择器 lint、命名 lint、token 悬空 lint 三条能在一条命令里全部跑起来，任一违规使该命令非零退出。
4. `dependency-cruiser` 可执行且在零规则下通过。
5. `pyproject.toml` 的 `package-data` 覆盖 `static/dist/` 下的递归路径（构造一个深层子目录文件，断言它进了 wheel）。

---

### WI-10: 4A.1 token 与主题层

**范围**：双层 token 定义文件；**两根主题轴**（chrome 明暗 ＋ 阅读纸色）的 CSS 与 FOUC inline script。

**前置 WI**：WI-7、WI-9。

**做什么**：落地设计规格 §3 的双层 token——Tier 1 调色板 `--p-*`，Tier 2 语义 `--r3-*`，**组件只许引用 Tier 2**。同时把 WI-7 的 RGB 三元组落进来，并补上现状完全没有的暗色模式（D2）。

主题是**两根互不重定义的轴**（裁决 §11-R7，契约唯一定义处是设计规格 §3.3）：

| 轴 | 属性（都 stamp 在 `<html>`） | 取值 | 拥有的 token |
|---|---|---|---|
| chrome | `data-theme` | 属性缺席＝跟随系统 / `light` / `dark` | 除下一行外的全部 `--r3-*` |
| reading | `data-reading-theme` | `auto`（默认）/ `paper` / `sepia` / `green` / `night` | `--r3-page-bg` / `-ink` / `-quiet`、`--r3-hl-*`（含 `-rgb`） |

三条必须落对的实现细节：

- 阅读 token 只许写成 `html[data-reading-theme="x"] .reader-shell { }`。**作用域靠选择器保证，不靠挂载点**——书库页没有 `.reader-shell`，纸色天然不外泄。
- **`auto` 没有 CSS 规则**，它就是「不覆盖 chrome 给的 `--r3-page-*` / `--r3-hl-*`」。谁把它当漏写补上，两根轴就又合成一根了。
- 另四种纸色是**绝对值**，在 light / dark chrome 下逐字相同。

**本 WI 还交付 FOUC inline script**（三个页面模板 `<head>` 共用一段同步脚本）：读两个 localStorage key，往 `<html>` 上 stamp 两个属性。三条易错点：

- 属性 stamp 在 `<html>`，**不是** `.reader-shell`——脚本执行时 `<body>` 尚未解析，该元素不存在。
- `auto` **也要写出属性**（`data-reading-theme="auto"`），它靠「没有 CSS 覆盖规则」生效，不靠属性缺席。
- chrome 的 `system` 反过来——**必须移除** `data-theme`，因为跟随系统靠 `@media` 命中 `:not([data-theme="light"])`。

**涉及 testid**：无新增（chrome 切换控件本身在 WI-12 / WI-13 落地）。

**涉及降级状态**：无（但 DEG 横幅的四个 `-subtle` 底色在此层解析）。

**验收标准**：

1. 组件样式文件里对 `--p-*` 的直接引用次数为 0（只许引 `--r3-*`）。
2. token 悬空 lint 通过：**chrome 2 × reading 5 = 10 种**属性组合下（chrome 只有 light / dark 两个有效解析，`system` 不是第三种视觉），`getComputedStyle` 解析全部 `--r3-*` 均非空字符串。
3. 切到 dark chrome 后 `body` 背景色计算值改变，且 `--r3-text` 与 `--r3-bg` 对比度 ≥4.5:1；**且此断言与 `data-reading-theme` 取何值无关**（跑满 5 个值结果一致）。
4. `--r3-warning` / `--r3-error` 及四个 `-subtle` 在 10 种组合下都有定义。
5. WI-7 的 `--r3-hl-*-rgb` 在 10 种组合下都解析为三个数字。
6. **纸色绝对性**：`paper` / `sepia` / `green` / `night` 四值下解析出的 `--r3-page-bg` / `-ink` / `-quiet` / `--r3-hl-*`，在 light chrome 与 dark chrome 下**逐字相等**。
7. **`auto` 是跟随的那一个**：`auto` 下解析出的 `--r3-page-bg` 在 light 与 dark chrome 下**不相等**，且分别等于该 chrome 下 `:root` 声明的值。
8. **不外泄**：书库页与设置页在 `data-reading-theme` 取任一值时，`body` 的 `background-color` 计算值不变。
9. **FOUC**：三个页面首帧（`DOMContentLoaded` 前采样）`<html>` 上两个属性已按存储值 stamp；`colorScheme=system` 时 `data-theme` 属性**不存在**；`reader3.reader.theme` 缺席时 `data-reading-theme` 为 `"auto"`。
10. CSS 里不存在 `[data-reading-theme="auto"]` 选择器（`auto` 必须靠没有规则实现，写了就是把两根轴又合成一根）。

---

### WI-11: 4A.3 共享模块

**范围**：`{前端源码根}/shared/escape.ts`、`toast.ts`、`dom.ts`、`debug.ts`。

**前置 WI**：WI-9。

**做什么**：把散在各处的公共工具收成共享模块。

- `escape.ts` 的形状由 **0.4 的 `escapeHtml` 收敛结论**决定，本 WI 不另作裁定。
- `showToast` / `elementDebugInfo` / `getEventTargetElement` 从 `annotations.js` 移出来落这里——WI-14 的八模块行数合计约 1085、文件实际 1127，差额就是这三个。
- 设计规格 §5 标注 `Toast` 组件**不存在**，本 WI 要把它建出来。
- 42 处 `console.log`（`annotations.js` 33 ＋ `epub-renderer.js` 9）换成 `debug.ts` 分层，由 `localStorage["reader3.debug"]` 控制、默认关；ESLint 开 `no-console` 但放行 warn / error。

**涉及 testid**：`rd-toast` / `lib-toast`（Toast 容器）。

**涉及降级状态**：无。

**验收标准**：

1. 源码内 `console.log(` 出现次数为 0，`no-console` 规则开启且构建通过。
2. `localStorage["reader3.debug"]` 未设置时 `debug.*` 调用不产生任何控制台输出；设置后产生输出。
3. `escape.ts` 只导出 0.4 结论里确定的那一组函数（函数名逐个比对）。
4. Toast 挂载后 N 毫秒自动消失，且同时最多存在一个 Toast 容器元素。
5. `showToast` / `elementDebugInfo` / `getEventTargetElement` 在 `{前端源码根}/reader/` 下的定义处计数为 0（确实移走了）。

---

### WI-12: 4A.2 设置页切片

**范围**：`templates/settings.html` → TS 页面；设置页四个分区；破坏性操作确认。

**前置 WI**：WI-9、WI-10、WI-11。

**做什么**：把设置页搬进设计系统（D3：现状 `settings.html` 完全在设计系统之外）。

设计规格 §6.1 的四个分区照做。破坏性操作（清缓存 / 清会话 / 重建索引）必须走 `<dialog>` 确认，**不要用 `confirm()`**。

移动端 390×844 下 ollama 行的 `Enabled` 溢出（§7 实测第四项）在这一项修掉。

**第 3 分区「外观」是新增的**，只放 **chrome 轴**：界面明暗三选一（跟随系统 / 浅色 / 深色）＋ 界面语言。**这里没有纸色**——纸色是另一根轴，控件在 WI-18 的阅读设置面板里（§11-R7）。三选一写 `reader3.ui.colorScheme`，`system` 时**移除** `<html data-theme>`；token 与 FOUC 脚本由 WI-10 提供，本 WI 只挂控件。

**涉及 testid**：`set-appearance-scheme-system` / `-light` / `-dark`、`set-provider-*`、`set-data-cache`、`set-data-conversations`、`set-data-reindex`、`set-export-json`、`set-export-settings`、`set-rag-chunks`、`set-rag-context`、`set-rag-embedding`、`set-confirm-dialog`、`set-confirm-ok`、`set-confirm-cancel`。

**涉及降级状态**：无。

**验收标准**：

1. 源码内 `confirm(` 与 `alert(` 出现次数为 0。
2. 点任一破坏性操作后 `set-confirm-dialog` 可见；点 `set-confirm-cancel` 后请求数为 0；点 `set-confirm-ok` 后对应请求发出 1 次。
3. 设置页所有 testid 匹配 canonical 正则且以 `set-` 开头（命名 lint 通过）。
4. 390×844 下 ollama 行的 `Enabled` 控件 `getBoundingClientRect().right` ≤ 视口宽度。
5. 设置页样式文件对 `--p-*` 的直接引用次数为 0。
6. 「外观」分区恰有三个明暗选项，`role="radiogroup"` ＋ 同时 `aria-checked="true"` 的数量为 1；无存储值时选中 `set-appearance-scheme-system`。
7. 选中 `system` 后 `<html>` 上**不存在** `data-theme` 属性；选 `light` / `dark` 后属性值等于所选，且 `reader3.ui.colorScheme` 同步。三次切换都**不触碰** `data-reading-theme`。
8. 「外观」分区内不存在任何纸色控件（`rd-pref-theme-*` 在设置页命中数为 0）。

---

### WI-13: 4A.4 书库页切片

**范围**：`templates/library.html` → TS 页面；三栏网格；DEG-S2 / DEG-S3 / DEG-S4 重做版；**删除 `library_classic.html` 与 `READER3_LIBRARY_UI=classic` 分支**。

**前置 WI**：WI-3、WI-4、WI-5、WI-8、WI-9、WI-10、WI-11。

**做什么**：书库页按设计规格 §6.2 重做——三栏网格、每栏 `min-width: 0`。

Track D 交付的是**朴素形态**（Phase 3 的门槛只要求「可见」，哪怕落到现有 Jinja 模板的朴素横幅）；本 WI 交付的是**重做形态**。这是两次交付，不是一次。DEG-S2 / DEG-S3 / DEG-S4 的重做落这里，DEG-S1 落 WI-16，DEG-S5 的 UI 落 Phase 2a。

移动端 390×844 的两处不可达（右栏 `x=390, width=249` 够不着；左栏未渲染导致 `#collections-create` 够不着）在这一项修掉。

书卡进度值与 WI-19 对齐（同一个计算口径）。

**Header 新增界面明暗切换按钮**（chrome 轴三态循环 跟随系统 → 浅色 → 深色，与 WI-12 设置页那组是**同一个状态**、同一个 key）。**不是纸色切换**——书库页没有纸（§11-R7）。

**删除动作**：`library_classic.html` 与它的环境变量分支。**执行删除前须单独确认**。

**涉及 testid**：`lib-theme-toggle`、`lib-book-grid`、`lib-book-card`、`lib-sidebar`、`lib-collections-create`、`lib-search-input`、`lib-filter`、`lib-sort`、`lib-view-grid`、`lib-view-list`、`lib-bulk-bar`、`lib-select-all`、`lib-select-none`、`lib-bulk-index`、`lib-bulk-collection`、`lib-empty`、`lib-filter-empty`、`lib-dropzone`、`lib-add-books`，以及 WI-3 / WI-4 / WI-5 的全部降级 testid。

**涉及降级状态**：DEG-S2、DEG-S3、DEG-S4（重做形态）。

**验收标准**：

1. 三栏容器每一栏的 `min-width` 计算值为 `0px`。
2. 390×844 下 `lib-collections-create` 可见且 `getBoundingClientRect()` 完全落在视口内；右栏内容同样落在视口内。
3. 1440×900 下三栏都可见。
4. `library_classic.html` 文件不存在，源码内 `READER3_LIBRARY_UI` 出现次数为 0。
5. 书卡显示的进度值与 WI-19 定义的计算口径逐本一致（同一本书两处取值相等）。
6. 书库页所有 testid 以 `lib-` 开头且匹配 canonical 正则。
7. 空库、筛选无结果、加载失败三种状态各自渲染对应 testid，且三者互斥（同一时刻只有一个可见）。
8. `lib-theme-toggle` 连点三次回到初始态；`aria-label` 随态更新；三态与设置页「外观」互通（在设置页选 `dark` 后回书库，按钮显示 `dark`）。

---

### WI-14: 4B.1 annotations.js 八模块拆分

**范围**：`static/js/annotations.js`（1127 行）→ `{前端源码根}/reader/` 下八个模块。

**前置 WI**：WI-9、WI-11。

**做什么**：**零行为变更**的结构拆分，唯一的例外是 K6（见 WI-15）。

| 模块 | 迁入符号 | 约行数 | 承载契约 |
|---|---|---:|---|
| `context.ts` | `getReaderContext` | 15 | K6。**删掉 `location.pathname` 兜底** |
| `notes-api.ts` | 四处 `/api/notes` fetch | 60 | 无。Phase 2a 的 DEG-S5 乐观并发**唯一落点** |
| `anchoring.ts` | `buildTextIndex` `offsetFromNode` `findRange` `buildSegments` `rangeFromCfi` | 110 | **无契约就是重点**——变成可单测的纯函数 |
| `renderer.ts` | `clearExistingAnnotationMarks` `dedupeAnnotationMeta` `segmentStyle` `applySegments` `class AnnotationRenderer` ＋ 从 `AnnotationUI` 搬来的三个读侧方法 | 250 | K5 ＋ K4 写侧 |
| `overlays.ts` | `qs` `clamp` `offsetRect` ＋ 构造函数里抓七个元素那段、`openToolbarAt` `closeSelectionToolbarIfOpen` `setSelectedColor` `syncSelectedColor` `closeNoteEditorIfOpen` `onHover` `showTooltip` `hideTooltip` | 150 | **K1 ＋ K3 ⚠️ 风险集中模块** |
| `note-editor.ts` | 打开与填充表单 | 45 | 无。保存走 `commands` |
| `commands.ts` | `toggleMarkerAnnotation` `toggleAnnotation` `deleteCurrentAnnotation` `saveNote` `deleteAnnotations` `createAnnotation` | 175 | 严格单向 `interactions → commands → notes-api`，不反向 import、不直接碰 DOM |
| `interactions.ts` | 构造函数减去七行 `qs()`、`init` `onAnnotationClick` `getExistingMarkerIds` `onSelection` `handleRenditionSelection` `handleSelectionRange` `handleAction` `getExistingAnnotationIds` `copySelection` `askAi` ＋ `initAnnotations` | 280 | K2 ＋ K4 消费侧 |

合计约 1085，与 1127 的差额是 `showToast` / `elementDebugInfo` / `getEventTargetElement`，它们去 WI-11。

**`commands.ts` 为什么必须存在**：`AnnotationUI` 有 **30 个方法**，上游计划记的是 24。多出来的六个构成从 `handleAction` 到三处 `fetch` 之间的完整写入链，此前无人认领；按行号机械切分会把它们塞进 `note-editor.ts`，于是 `createAnnotation`（marker / wavy / underline / note 四种类型**共用的唯一写入口**）住进一个叫「笔记编辑器」的模块。落选方案：折进 `notes-api.ts` 是**层级塌缩**，传输层被 UI 状态污染，长成 god service；只切文件不切职责是**装饰性模块化**，隐式耦合原样保留，拿不到单测边界。

**四条 `dependency-cruiser` 规则**：

- `no-circular`
- `commands-no-upward`：`commands.ts` 不许 import `interactions.ts` / `overlays.ts` / `note-editor.ts`
- **`interactions-no-bypass`**：`interactions.ts` 不许 import `notes-api.ts`。只禁反向 import 拦不住**正向绕过**，而正向绕过才是最省事、最可能被写出来的捷径
- `notes-api-leaf`：`notes-api.ts` 不许 import 同目录任何模块（`import type` 放行）

**未裁决项（原样带过来，不在本 WI 解决）**：「`commands.ts` 不得碰 DOM」**不是机器可验的**，与「纯拆分」冲突（Codex 评审第 1 条）。要机器可验就得引入 `SelectionSnapshot` ＋ 注入端口，那已经不是纯拆分。本 WI 按人工评审执行这条，并在 PR 描述里显式列出 `commands.ts` 里所有触碰 DOM 的位置。

**涉及 testid**：无新增（零行为变更）。

**涉及降级状态**：无。

**验收标准**：

1. `static/js/annotations.js` 不再存在，八个模块文件全部存在。
2. 四条 `dependency-cruiser` 规则全部启用且通过；人为加一条反向 import 后该命令非零退出（规则确实生效）。
3. `baseline-1b` 全部用例零改动通过。
4. iframe 边界三重断言 A/B/C 全部通过（定义见 `spec-frontend-design.md` §6.0）。
5. 八个模块的导出符号并集等于原 `annotations.js` 的对外符号集合，无遗漏无新增（K6 的兜底删除除外）。
6. `anchoring.ts` 的五个函数有纯函数单测，且这些单测不依赖 DOM 或网络。
7. PR 描述里列出了 `commands.ts` 中所有触碰 DOM 的位置（文档级验收）。

---

### WI-15: 4B.1 K1–K6 契约交付物

**范围**：与 WI-14 同一批文件；`static/search.js` 的 K5 消费点。

**前置 WI**：WI-14。

**做什么**：六个契约各自的显式交付物。

- **K1**：`OVERLAY_IDS` 常量表 ＋ 初始化时校验，缺失元素 `console.error`（不是静默返回 `null`）。
- **K2**：`data-action` / `data-color` 的联合类型。
- **K3**：`offsetRect()` 随 `overlays.ts` 一起移动，并加注释说明它返回的是**视口坐标**。
- **K4**：六个事件名改成常量。
- **K5**：`window.Reader3Epub` 写成显式接口，9 个成员里 **7 个纳入**（`rendition`、`getContents()`、`getContentRoot()`、`getFrameElement()`、`onContentsReady(cb)`、`applyThemeSettings()`、`displaySectionIndex(i)`），2 个标 `@deprecated`（`getContentDocument()`、`book`），在 WI-16 结束时删除。⚠️ **`search.js` 也是 K5 的消费方**，消费 `getContentRoot` 与 `onContentsReady`，不是只有 `annotations.js`。
- **K6**：删掉 `location.pathname` 兜底并改为抛错。这是 WI-14 **唯一有意的行为变更**。

六个契约里四个现在是**静默失败**的。

**涉及 testid**：无新增。

**涉及降级状态**：无。

**验收标准**：

1. 删掉页面上任一个覆盖层元素后初始化，控制台出现 `error` 级输出且内容包含缺失元素的 id；不出现未捕获异常。
2. `data-action` / `data-color` 传入枚举外的值时构建期报类型错误（构造一个反例断言 `tsc` 非零退出）。
3. `offsetRect` 的定义处带视口坐标说明注释（源码级人工验收，写进 PR 描述）。
4. 源码内六个事件名的字符串字面量出现次数各为 1（只在常量定义处）。
5. `Reader3Epub` 接口声明的成员数为 9，其中 2 个带 `@deprecated` 标记。
6. `search.js` 对 `getContentRoot` / `onContentsReady` 的调用在类型检查下通过（它被纳入 TS 的类型覆盖范围）。
7. 构造一个无法解析 book id 的场景，`getReaderContext` **抛错**而不是返回兜底值；断言抛出的错误类型或消息。
8. 源码内 `location.pathname` 在 `context.ts` 中出现次数为 0。

---

### WI-16: 4B.2 阅读器外壳重写与三覆盖层几何门槛

**范围**：`templates/reader.html` → TS 页面；工具栏；面板互斥与焦点；三个覆盖层的挂载点；DEG-S1 重做形态。

**前置 WI**：WI-2、WI-10、WI-14、WI-15。

**做什么**：按设计规格 §6.3 重做阅读器外壳。

- **工具栏** 6 个 SVG 按钮 ＋ 新增 active 态，z-index 高于所有面板（修 D6：现状 `closeAllPanels()` 只关搜索和 AI，TOC / Notes 打开时点搜索按钮会超时）。
- **面板互斥**：单一 `activePanel` 状态。≥1280px 用 push 布局，<1280px 用 overlay。
- **焦点**：打开时焦点移入、Esc 关闭并**归还焦点**、Tab 在面板内循环。现状 `resetFocusAfterClose()` 只做了 blur。
- **导航区**：**删除隐形 nav-zone**，改显式 `‹` / `›` 翻页按钮（带 `aria-label`），`<768px` 隐藏（该档由工具栏翻页）。章节导航（跳 spine）与页内翻页在语义上必须可区分。裁决见规格 §11-R2——原先的「`<1024px` 禁用」是用视口宽度代理触屏，代理是错的。
- **标注工具栏** 7 个操作 ＋ 4 个颜色，中文文案，`aria-pressed`，Delete 单独隔开。
- **DEG-S1 重做形态**落这里。
- WI-15 里标 `@deprecated` 的两个成员在本 WI 结束时删除。

**K3 硬约束（覆盖层挂载点）**：只允许两种挂载——`<body>` 直接子元素（生产现状，零改动即合规），或 `<dialog>` ＋ `showModal()` 进 top layer。挂在 `.reader-shell` 里不是禁止，但**每次都要证明**。`.page-flow` 已经带着 `will-change: transform`，就是那个反面教材。

**涉及 testid**：`rd-toolbar`、`rd-toolbar-toc`、`rd-toolbar-notes`、`rd-toolbar-search`、`rd-toolbar-ai`、`rd-toolbar-settings`、`rd-toolbar-back`、`rd-panel-toc`、`rd-panel-notes`、`rd-panel-search`、`rd-panel-ai`、`rd-anno-toolbar`、`rd-anno-copy`、`rd-anno-note`、`rd-anno-ask`、`rd-anno-delete`、`rd-anno-color-yellow` / `-green` / `-pink` / `-blue`、`rd-note-editor`、`rd-note-tooltip`、`rd-degrade-s1`、`rd-page-prev`、`rd-page-next`。

**涉及降级状态**：DEG-S1（重做形态）。

**验收标准**：

1. TOC 或 Notes 面板打开状态下点 `rd-toolbar-search`：搜索面板在超时前打开，且原面板关闭（`rd-panel-toc` 不可见）。
2. 任意时刻可见的面板数 ≤1（对四个面板 testid 逐一取可见性求和）。
3. 面板打开后 `document.activeElement` 在该面板子树内；按 Esc 后面板关闭且 `document.activeElement` 回到触发它的工具栏按钮。
4. 面板打开后连按 N＋1 次 Tab，`document.activeElement` 始终在该面板子树内。
5. 1440×900 下打开面板，正文容器的 `getBoundingClientRect().width` 变小（push 布局）；1279×800 下打开面板，正文宽度不变（overlay 布局）。
6. **每个用例的 `afterEach`**（或一条专门的结构测试）断言 `rd-anno-toolbar`、`rd-note-editor`、`rd-note-tooltip` 三者的 `containingBlockAncestor(el) === null`。**不是只在 happy path 上验一次。**同时按 Codex #3 补齐属性集合——独立的 `translate` / `rotate` / `scale`、`content-visibility`，以及 `will-change` 里的 `contain` / `content-visibility` / `backdrop-filter` / `translate` / `rotate` / `scale`，旧 Safari 另查 `webkitBackdropFilter`；每一种制造属性各有一条参数化断言（人为加上该属性后 `containingBlockAncestor` 必须返回非 `null`）。补齐后的集合写回 `contracts/annotation-host-contracts.md` 的 K3。
7. **几何断言**：`rd-anno-toolbar` 的矩形相对选区矩形水平居中，误差 ≤N px；垂直方向贴着选区边缘，误差 ≤N px。`toBeVisible()` / `toBeAttached()` **不算数**，不许当替代。
8. `rd-note-editor` 与 `rd-note-tooltip`（经 hover 触发）同样满足第 6、7 条。
9. 全页面不存在隐形翻页热区元素（按 `.nav-zone-left` / `.nav-zone-right` 查询返回 0 个）；`rd-page-prev` / `rd-page-next` 存在且各有非空 `aria-label`；767×800 下两者均不可见。
10. 标注工具栏 4 个颜色按钮的 `aria-pressed` 在选中时为 `true`、未选中为 `false`，同时为 `true` 的数量 ≤1。
11. `rd-anno-delete` 与其余六个操作之间存在视觉分隔（其 `margin-left` 或分隔元素存在，计算值断言）。
12. 源码内 `getContentDocument` 与 `Reader3Epub.book` 的引用次数为 0。
13. `baseline-1b` 全部用例通过；A/B/C 三重断言通过。

---

### WI-17: 4B.2 翻页三缺陷

**范围**：分页与章节切换逻辑；`epub-renderer.js` 的翻页路径。

**前置 WI**：WI-16。

**做什么**：修掉原型实测出的三个翻页缺陷（见 §1.4）。生产端是 epub.js iframe 分页，不是原型的 multicolumn，但三个缺陷的成因（异步 ＋ 陈旧状态）在两边一致。

缺陷 3 在当前生产端是否存在**尚未验证**——先在 `baseline-1b` 里加一条 E2E 把现状定性，再决定是回归修复还是新功能。

**涉及 testid**：`rd-page-next`、`rd-page-prev`、`rd-page-indicator`、`rd-chapter-next`、`rd-chapter-prev`、`rd-chapter-count`。

**涉及降级状态**：无。

**验收标准**：

1. 章内连续快速触发 3 次「下一页」（间隔小于一次渲染耗时），最终页码等于起始页码 ＋3。
2. 章末连续快速触发 2 次「下一页」，最终停在下一章而不是下下章（章节索引等于起始 ＋1）。
3. 章首触发「上一页」，落到上一章的**最后一页**：断言页码等于上一章总页数，且不等于 1。
4. 第 3 条对应的用例先以现状运行一次并记录结果（现状定性），记录写进 `baseline-1b`。
5. 翻页锁生效期间重复触发不产生额外的 `rendition` 调用（调用计数断言）。
6. `rd-page-indicator` 的值在每次翻页后与实际渲染页一致（连续 5 次翻页逐次断言）。

---

### WI-18: 4B.3 阅读设置面板与 D5 栏宽

**范围**：阅读设置面板；`themes.override` 注入路径；字体清单。

**前置 WI**：WI-15、WI-16。

**做什么**：设计规格 §6.3 的阅读设置表：

| 项 | 范围 | 默认 | 存储 | 作用域 |
|---|---|---|---|---|
| 主题（纸色） | auto / paper / sepia / green / night | **auto** | `localStorage["reader3.reader.theme"]` | 值全局，视觉仅 `.reader-shell` ＋ iframe |
| 字号 | 14–24px，步长 1 | 17 | `localStorage["reader3.reader.fontSize"]` | 仅 iframe |
| 行高 | 1.4–2.4，步长 0.1 | 1.9 | `localStorage["reader3.reader.lineHeight"]` | 仅 iframe |
| 字体 | system / serif 二选一 | system | `localStorage["reader3.reader.fontFamily"]` | 仅 iframe |

> **纸色的白档叫 `paper`，不是 `white`**；key 命名空间是 `reader3.<区域>.<camelCase>`。两条都是规格 §11-R5 的裁决，理由是生产已发货 `reader3.library.rightPanelCollapsed`。
>
> **这一栏不是界面明暗。** 界面明暗是另一根轴（`data-theme`，控件在 header 与设置页「外观」分区，见 WI-13），存在 `reader3.ui.colorScheme` 里。本表只管纸色。裁决见规格 §11-R7，契约唯一定义处是 §3.3。
>
> **默认 `auto` 而不是 `paper`**：`auto` = 跟随界面明暗（light chrome → 白纸，dark chrome → 深纸），实现是「没有覆盖规则」而不是一段 JS 解析。绝对白纸配深界面是刺眼的开箱体验。

**主题选择器五个选项**（`auto` 排第一），用 `role="radiogroup"` ＋ `aria-checked` ＋ 方向键；字号行高到边界时按钮 `disabled`。

**iframe 注入与宿主 CSS 必须同源**：一份 TS 常量 `READING_THEMES: Record<ReadingTheme, {bg, ink, quiet, hl}>` 同时喂给样式表和 `themes.override()`。**不许**从宿主页 `getComputedStyle` 反解颜色再注进 iframe——`auto` 会让这条路径依赖 chrome 的最终解析状态。`auto` 在常量表里按当前 chrome 取 light / dark 两组之一。

**D5 栏宽**（正文 45–75 字符）：`max-width: 38rem`、`margin-inline: auto`、`text-align: start`、内边距 `clamp(16px, 5vw, 64px)`，在 1440×900 与 390×844 两处都要验。走 `applyThemeSettings`（已在 K5 冻结面里确认）经 `themes.override` 注入。

**删掉三个未授权的商业中文字体。** 字体一律收敛成 `system` / `serif` **两值**（Codex #7）；`serif` 的资产归属**实施时二选一**：self-host 思源宋体（开源许可，需把字体文件纳入构建），或在资产落地前直接用系统 serif fallback。选定哪个都行，但必须落到验收第 10 条里，不许两种说法并存。

**旧偏好迁移（Codex #10）**：现状**已经**实现了字号与行距，偏好存在 `reader3-font-settings` 这个 JSON key 里。直接换新 key 会把用户偏好重置。必须做一次性迁移：读 legacy JSON → 范围校验（越界的钳到合法区间，不是丢弃）→ 写入新 key → 写迁移完成标记 → 之后不再读 legacy。**迁移不为主题写任何值**——legacy 里没有主题，`reader3.reader.theme` 缺席即 `auto`，这正是我们要的默认。

**涉及 testid**：`rd-rail-font`、`rd-font-popover`、`rd-pref-theme-auto` / `-paper` / `-sepia` / `-green` / `-night`、`rd-pref-size`、`rd-pref-size-inc`、`rd-pref-size-dec`、`rd-pref-leading`、`rd-pref-font-system`、`rd-pref-font-serif`。

**涉及降级状态**：无。

**验收标准**：

1. 主题容器 `role` 为 `radiogroup`，**五个**选项各有 `aria-checked`，同时为 `true` 的数量恰为 1；无任何存储值时为 `true` 的是 `rd-pref-theme-auto`。
2. 焦点在主题组内按右方向键，选中项前移一个并且 `aria-checked` 随之更新。
3. 字号为 14 时减号按钮 `disabled` 为真、加号为假；字号为 24 时相反。
4. 改字号后刷新页面，`localStorage["reader3.reader.fontSize"]` 与实际渲染字号一致。
5. 主题存 `localStorage["reader3.reader.theme"]`，且切换后书库页也读到同一个值（值是全局的）；但书库页 `body` 的 `background-color` 在五个值下**计算结果不变**（视觉只作用于 `.reader-shell`）。字号只影响 iframe 内文本，iframe 外元素字号不变。
6. 1440×900 与 390×844 下，正文一行的字符数落在 45–75 之间（取样连续 3 行）。
7. 正文容器 `max-width` 计算值等于 `38rem` 的像素值，`margin-inline` 左右相等，`text-align` 为 `start`。
8. **A/B/C 三重断言在栏宽注入路径上全部通过**——**C（CFI 往返解析到同一段引文）才是真正要证的那条**，因为栏宽改变的是「标注落在第几屏」。
9. E2E 用例 `R-6` 的栏宽参数启用且通过。
10. 源码与样式内三个商业中文字体名出现次数为 0；字体选项**恰好两个**（`system` / `serif`），且 `serif` 的解析 `font-family` 与实施时选定的那一种一致（self-host 思源宋体则断言 `@font-face` 存在且字体文件在产物里；系统 fallback 则断言 `@font-face` 数量为 0）。
11. `baseline-1b` 零改动通过。
12. 只存在 legacy `reader3-font-settings` 时加载阅读器：新 key 被写出，值等于 legacy 里的值，且实际渲染字号与行高等于 legacy 值（**偏好没被重置**）。
13. legacy 值越界（例如字号 99）时钳到合法区间（24），不抛错、不回落默认值。
14. 迁移完成标记存在后再次加载：不再读 legacy key（把 legacy 改成另一个值，断言渲染不变）；且 `reader3.reader.theme` **未被写入**，选中项仍是 `auto`。
15. 切纸色时 `<html>` 的 `data-reading-theme` 被改写（`auto` 也写出属性，不是移除），`data-theme` **不被触碰**；反过来切界面明暗时 `data-reading-theme` 不被触碰。
16. `auto` 下切换界面明暗，iframe 内正文背景色随之改变；`paper` 下切换界面明暗，iframe 内正文背景色**不变**。
17. 注入 iframe 的颜色来自共享常量 `READING_THEMES`，源码内不存在「宿主页 `getComputedStyle` 取色 → 注入 iframe」的调用路径。

---

### WI-19: 4B.4 进度单一真相源

**范围**：阅读器页脚进度；Notes 面板进度；与 WI-13 书卡进度对齐。

**前置 WI**：WI-13、WI-16。

**做什么**：修 D7——现状同一时刻有两个互相矛盾的进度值（26% 与 20%），且只有封面的 spine 0 显示 100%。

页脚与 Notes 面板收敛到同一个计算函数，并与 WI-13 已经改过的书卡口径一致。**非正文 spine 项不进分母**。

**涉及 testid**：`rd-progress`、`rd-notes-progress`、`lib-book-progress`。

**涉及降级状态**：无。

**验收标准**：

1. 同一本书同一位置，`rd-progress` 与 `rd-notes-progress` 的文本值相等。
2. 该值与书库页 `lib-book-progress` 相等（同一本书跨页取值比对）。
3. 进度计算函数在源码内的定义处计数为 1。
4. 只有封面的 spine 0 处进度不等于 100%（断言小于 100）。
5. 一本含 N 个正文 spine 项与 M 个非正文项的书，读到最后一个正文项末尾时进度等于 100%。
6. 分母不含非正文项：构造 M 变化而 N 不变的两本书，同一正文位置的进度值相等。

---

### WI-20: Phase 5 前端侧——PWA

**范围**：`manifest.json`（PWA）、service worker、离线壳。

**前置 WI**：WI-12、WI-13、WI-16。

**做什么**：给三个页面配 PWA manifest 与 service worker。

⚠️ **命名撞车**：PWA 的 `manifest.json` 与存储格式的 `manifest.json`（两文件提交协议）是**完全不同的两个东西**。放置路径与文档引用都要显式区分，不要只写「manifest」。

`reader3 launch` 的 CLI 部分不在本计划，在技术栈迁移那侧。

**涉及 testid**：无。

**涉及降级状态**：无。

**验收标准**：

1. 三个页面都能拿到 PWA manifest，且 manifest 里 `start_url` / `display` / `icons` 齐备。
2. service worker 注册成功，离线状态下书库页仍能渲染出壳（不是浏览器默认错误页）。
3. 离线状态下数据请求失败时页面显示错误态而不是空白（对应 testid 可见）。
4. 文档与源码里 PWA manifest 的路径与存储格式 manifest 的路径不同，且两者在本计划与技术栈迁移计划里各自被显式限定（文档级验收）。

---

## 5. 测试矩阵

### 5.0 通则（对所有用例生效）

**断言目标的选法**，按优先级：

1. `data-testid`（首选）。
2. 没有 testid 时用 ARIA `role` ＋ accessible name。
3. **class 选择器与 `nth-child` 一律禁止**——这是 0.5 选择器 lint 的机器约束，写了就过不了 lint。

**执行器**：Python `pytest-playwright`（Codex #13 的裁定）。**不要写 Node Playwright Test 的 `webServer` 语法**，用 pytest 的 session fixture 起子进程、先设 `READER3_BOOKS_DIR`、分配空闲端口。初版主 CI 单 worker。

**分组**：本矩阵新增的用例挂到 009 已定义的同一套 pytest marker——`acceptance-p3` / `acceptance-4a4` / `acceptance-4b1` / `acceptance-2a`，未激活的分组以 `skip` 存在，不删。009 已定义的 `R-1`…`R-6` / `W-1`…`W-10` / `K-1`…`K-6` / `X-1` / `X-2` **不重写**；两边冲突时以 009 为准。

**「可失败」的定义**：每条用例都必须能因为被测行为的缺失而变红。验证方式是反向注入——把被测属性 / 行为人为去掉，用例必须失败。下面这些**不算断言**，不许单独使用：

- `toBeVisible()` / `toBeAttached()` / 「元素存在」
- 「没有抛异常」
- 截图比对

**不测的东西**：WI-8 的 Skeleton 是过渡态，**矩阵里没有任何一条以骨架为断言目标**——断言它之后的东西。

**testid 前缀**：书库 `lib-`、阅读器 `rd-`、设置 `set-`。canonical 正则在 0.5，从代码块复制、不要从表格复制。

---

### 5.1 按钮与可点击元素

#### 5.1.0 八态通则

每个可点击元素都按这八条过一遍。不适用的那几条要在实现里显式说明「为什么不适用」，不能默认跳过。

| 状态 | 断言方式 | 预期 |
|---|---|---|
| default | 计算样式取 `background-color` / `color` | 与该变体的 token 解析值相等 |
| hover | `hover()` 后取计算样式 | 至少一个视觉属性与 default 不同 |
| focus-visible | 键盘 `Tab` 聚焦后取 `outline-width` / `outline-color` | 宽度 2px、颜色等于 `--r3-focus-ring` 解析值。**用鼠标点击聚焦时不显示**（两次采样对比） |
| active | `mouse.down()` 保持时取计算样式 | 与 hover 态不同 |
| disabled | `disabled` 属性或 `aria-disabled` | 点击不发出任何网络请求（请求计数为 0），且不改变页面状态 |
| loading | 触发后立即采样 | 按钮进入不可再次触发状态，且有可感知的 loading 指示（`aria-busy="true"`） |
| 防抖 / 幂等 | 100ms 内连点 3 次 | 网络请求恰好 1 次；若语义上必须每次都发（如翻页），则断言最终状态等于「点 3 次」的正确结果 |
| 数据已陈旧时点击 | 先让后端数据变更，再点旧页面上的按钮 | 不静默成功。要么刷新后再操作，要么弹冲突提示；**绝不能拿陈旧 id 写入** |

#### 5.1.1 书库页

| 用例 ID | 归属 WI | 断言目标 | 预期结果 |
|---|---|---|---|
| FB-L01 | WI-13 | `lib-add-books` | 八态全过；loading 期间 `aria-busy="true"`；连点 3 次只开一次文件选择 |
| FB-L02 | WI-13 | `lib-choose-files` | 同上；无文件选中时取消不产生请求 |
| FB-L03 | WI-13 | `lib-dropzone`（role=button） | 键盘 Enter 与鼠标点击行为一致；拖入非 EPUB 时显示错误态而不是静默忽略 |
| FB-L04 | WI-13 | `lib-collections-create` | 名称为空时 `disabled` 为真；连点 3 次只创建 1 个集合（幂等） |
| FB-L05 | WI-13 | `lib-select-all` / `lib-select-none` | 点 all 后选中数等于当前可见书数；点 none 后为 0；筛选状态下 all 只选可见项 |
| FB-L06 | WI-13 | `lib-toggle-selection` | 单卡选中态 `aria-pressed` 翻转；再点回退 |
| FB-L07 | WI-13 | `lib-bulk-index` | 选中 0 本时 `disabled` 为真；选中 N 本时请求体含 N 个 id；连点 3 次只发 1 次 |
| FB-L08 | WI-13 | `lib-bulk-collection` | 同上；目标集合未选时 `disabled` 为真 |
| FB-L09 | WI-13 | `lib-view-grid` / `lib-view-list` | 两者 `aria-pressed` 恰有一个为 `true`；切换后书卡容器的 `display` 计算值改变 |
| FB-L10 | WI-13 | `lib-filter` / `lib-sort` | 改变后书卡顺序或数量实际变化（取前 3 张卡的书名序列比对） |
| FB-L11 | WI-13 | `lib-search-input` ＋ `lib-search-clear` | 输入后 300ms 内只发 1 次请求（防抖）；clear 后输入框为空且结果区回到初始态 |
| FB-L12 | WI-3 | `lib-degrade-s2-reindex` | 连点 3 次只发 1 次重建请求；重建中按钮 `aria-busy="true"` |
| FB-L13 | WI-5 | `lib-migrate-retry` | 只对本项发请求；重试中该项 `disabled`，其余项不受影响 |
| FB-L14 | WI-4 | `lib-degrade-s3-toggle` | 折叠 / 展开来回 3 次状态正确；`aria-expanded` 同步翻转 |
| FB-L15 | WI-13 | `lib-book-card`（role=button） | Enter 与 Space 都能进入阅读器；`aria-label` 含书名 |
| FB-L16 | WI-13 | `lib-refresh-stats` | 连点 3 次只发 1 次；陈旧数据点击后统计数字被替换而不是叠加 |
| FB-L17 | WI-13 | `lib-nav-settings` / `lib-nav-library` | 当前页对应项 `aria-current="page"`，另一项没有 |
| FB-L18 | WI-13 | **陈旧数据写入** | 在 A 标签页删掉一本书，B 标签页点该书的 `lib-bulk-index`：不静默成功，显示错误或刷新提示 |
| FB-L19 | WI-13 | `lib-theme-toggle` | 三态循环，连点 3 次回到初始态；`aria-label` 随态更新；与设置页「外观」共用 `reader3.ui.colorScheme`（设置页选 `dark` 后回书库，按钮显示 `dark`） |

#### 5.1.2 阅读器

| 用例 ID | 归属 WI | 断言目标 | 预期结果 |
|---|---|---|---|
| FB-R01 | WI-16 | `rd-toolbar-toc` / `-notes` / `-search` / `-ai` / `-settings` / `-back` | 六个按钮八态全过；每个都有 `aria-label`（不是 `title`）；active 态 `aria-pressed` 正确 |
| FB-R02 | WI-17 | `rd-page-prev` / `rd-page-next` | **不做防抖去重**——连点 3 次必须前进 3 页（见 FR-01）。首页时 prev 的行为按 FR-03 |
| FB-R03 | WI-17 | `rd-chapter-prev` / `rd-chapter-next` | 首章 prev、末章 next 时 `disabled` 为真且不发请求 |
| FB-R04 | WI-16 | `rd-anno-copy` / `-note` / `-ask` / `-delete` | 七个操作八态全过；`rd-anno-delete` 与其余项有视觉分隔；未选中标注时 delete `disabled` |
| FB-R05 | WI-16 | `rd-anno-color-yellow` / `-green` / `-pink` / `-blue` | `aria-pressed` 同时为 `true` 的数量 ≤1；连点同一颜色 3 次只发 1 次写请求 |
| FB-R06 | WI-16 | `rd-note-editor` 的保存按钮 | 内容为空时 `disabled`；保存中 `aria-busy`；连点 3 次只创建 1 条笔记 |
| FB-R07 | WI-16 | `rd-notes-copy-all` / `rd-notes-export` | 零标注时 `disabled` 为真；有标注时导出内容条数等于标注数 |
| FB-R08 | WI-16 | `rd-note-jump` | 点击后正文滚动到该标注位置（断言标注元素进入视口，不是断言它存在） |
| FB-R09 | WI-16 | `rd-note-delete` | 删除后该条从面板消失且 `GET /api/notes` 的条数减 1；连点 3 次只删 1 条 |
| FB-R10 | WI-16 | `rd-search-input` ＋ `rd-search-mode` | 输入防抖 1 次请求；切换关键词 / 语义模式后结果集变化 |
| FB-R11 | WI-16 | `rd-ai-send` / `rd-ai-stop` | 空输入时 send `disabled`；发送后 send 变 `disabled`、stop 可用；stop 后流终止且不再追加文本 |
| FB-R12 | WI-16 | `rd-ai-new` / `rd-ai-clear` / `rd-ai-history` / `rd-ai-export` | 八态全过；`rd-ai-clear` 走确认弹层，不用 `confirm()` |
| FB-R13 | WI-18 | `rd-pref-size-inc` / `-dec` | 14 时 dec `disabled`、24 时 inc `disabled`（边界两端各断言一次） |
| FB-R14 | WI-18 | `rd-pref-theme-*` ×5（含 `-auto`） | 恰有一个 `aria-checked="true"`；无存储值时是 `-auto`；方向键可移动选中项 |
| FB-R15 | WI-18 | `rd-pref-font-system` / `-serif` | 恰好两个选项；切换后 iframe 内正文 `font-family` 计算值改变 |
| FB-R16 | WI-16 | `rd-toc-row` | 点击后跳到对应章节（断言 spine index 变化，不是断言元素存在） |
| FB-R17 | WI-16 | `rd-sheet-close` | 关闭后焦点归还到打开它的按钮 |
| FB-R18 | WI-6 | `rd-conflict-keep-mine` / `rd-conflict-take-remote` | 两者都不是 `disabled`（除非远端不可达，此时只渲染前者）；点击后对话框消失 |
| FB-R19 | WI-16 | **陈旧数据写入** | A 标签页删掉某标注，B 标签页对它点 `rd-anno-delete`：不静默成功，走 DEG-S5 或明确错误 |

#### 5.1.3 设置页

| 用例 ID | 归属 WI | 断言目标 | 预期结果 |
|---|---|---|---|
| FB-S01 | WI-12 | `set-provider-toggle` | `role="switch"` ＋ `aria-checked` 正确翻转；键盘 Space 可切换 |
| FB-S02 | WI-12 | `set-provider-save` | 必填项为空时 `disabled`；保存中 `aria-busy`；连点 3 次只发 1 次 |
| FB-S03 | WI-12 | `set-provider-test` | 测试中 `disabled`；成功 / 失败分别渲染 `set-provider-result` 的两种态，文案不同 |
| FB-S04 | WI-12 | `set-provider-refresh-models` | 连点 3 次只发 1 次；失败时下拉保持原值而不是清空 |
| FB-S05 | WI-12 | `set-data-cache` / `set-data-conversations` / `set-data-reindex` | 三个破坏性操作**都**先弹 `set-confirm-dialog`；cancel 后请求数为 0 |
| FB-S06 | WI-12 | `set-export-json` / `set-export-settings` | 导出内容非空且是合法 JSON；导出中按钮 `disabled` |
| FB-S07 | WI-12 | `set-rag-chunks` / `set-rag-context` / `set-rag-embedding` | 越界输入被钳到合法区间而不是保存越界值；保存后刷新仍是钳后的值 |
| FB-S08 | WI-12 | `set-provider-key` | 输入框 `type="password"`；保存后重新加载页面，返回值不含明文 key |
| FB-S09 | WI-12 | **陈旧数据写入** | A 标签页改了 provider 配置，B 标签页用旧值点 `set-provider-save`：不静默覆盖 |
| FB-S10 | WI-12 | `set-appearance-scheme-system` / `-light` / `-dark` | `role="radiogroup"`，恰有一个 `aria-checked="true"`，无存储值时是 `-system`；选 `system` 时 `<html>` 上**没有** `data-theme` 属性，选另两个时属性值等于所选；三次切换都不触碰 `data-reading-theme` |

---

### 5.2 面板与浮层

| 用例 ID | 归属 WI | 断言目标 | 预期结果 |
|---|---|---|---|
| FP-01 | WI-16 | `rd-panel-toc` / `-notes` / `-search` / `-ai` | 任意时刻四者可见数 ≤1（逐个取可见性求和） |
| FP-02 | WI-16 | `rd-toolbar-search`（TOC 已打开） | 搜索面板在超时前打开、TOC 关闭。**这是 D6 的回归用例**，现状会超时 |
| FP-03 | WI-16 | `rd-toolbar-notes`（AI 已打开） | 同上，四个面板两两组合各跑一次（12 条参数化） |
| FP-04 | WI-16 | 分层 Escape | 标注工具栏 ＋ 笔记编辑器同时打开时按 Esc：先关编辑器，工具栏仍在；再按 Esc 关工具栏；再按 Esc 关面板 |
| FP-05 | WI-16 | 焦点陷阱 | 面板打开后连按 N＋1 次 Tab，`document.activeElement` 始终在该面板子树内（`element.contains` 断言） |
| FP-06 | WI-16 | 反向焦点陷阱 | 同上，连按 N＋1 次 Shift+Tab |
| FP-07 | WI-16 | 焦点归还 | Esc 关闭后 `document.activeElement` 等于触发它的工具栏按钮 |
| FP-08 | WI-16 | 遮罩点击关闭 | 点面板外遮罩区域关闭面板；**`rd-conflict-dialog` 除外**（见 FG-16） |
| FP-09 | WI-16 | 滚动锁 | 覆盖式面板打开时 `body` 的 `overflow` 计算值为 `hidden`，页面滚动位置在关闭后恢复到打开前的值 |
| FP-10 | WI-16 | `containingBlockAncestor` | **每个用例的 `afterEach`** 对 `rd-anno-toolbar` / `rd-note-editor` / `rd-note-tooltip` 断言返回 `null` |
| FP-11 | WI-16 | `containingBlockAncestor` 参数化 | 人为给祖先加 `transform` / `filter` / `backdrop-filter` / `perspective` / `contain: layout` / `contain: paint` / `contain: strict` / `contain: content` / `will-change: transform` / `will-change: filter` / `will-change: perspective` / `translate` / `rotate` / `scale` / `content-visibility` / `will-change: contain` / `will-change: content-visibility` / `will-change: backdrop-filter` / `will-change: translate` / `will-change: rotate` / `will-change: scale`：每种都必须返回**非 `null`**（21 条参数化，Codex #3） |
| FP-12 | WI-16 | 覆盖层几何 | `rd-anno-toolbar` 相对选区矩形水平居中误差 ≤N px、垂直贴边误差 ≤N px。`toBeVisible()` 不算 |
| FP-13 | WI-16 | 覆盖层几何 | `rd-note-editor` 同 FP-12 |
| FP-14 | WI-16 | 覆盖层几何 | `rd-note-tooltip`（hover 触发）同 FP-12 |
| FP-15 | WI-12 | `set-confirm-dialog` | Esc 可关闭、遮罩点击可关闭、焦点陷阱与归还同 FP-05/07 |
| FP-16 | WI-13 | 书库右栏抽屉（`768–1279px`） | 打开 / 关闭状态下 `aria-expanded` 同步；抽屉打开时焦点移入 |
| FP-17 | WI-16 | `prefers-reduced-motion` | 开启后面板 `transition-duration` 计算值为 `0s`（a11y 契约第 5 条） |

---

### 5.3 键盘与可访问性

对齐 `spec-frontend-design.md` §8 六条契约，逐条转成断言。

| 用例 ID | 归属 WI | 契约 | 断言目标 | 预期结果 |
|---|---|---|---|---|
| FA-01 | WI-10 | §8-1 焦点可见 | 三页全部可交互元素 | 逐个 Tab 聚焦，`outline-width` 为 2px 且 `outline-color` 等于 `--r3-focus-ring` 解析值；`outline: none` 且无替代的元素数为 0 |
| FA-02 | WI-10 | §8-1 | 同上 | 鼠标点击聚焦时**不显示**焦点环（同一元素两次采样，键盘态与鼠标态的 `outline-width` 不同） |
| FA-03 | WI-10 | §8-2 对比度 | **六组纸/墨**：四种绝对纸色 ＋ `auto` 在 light / dark chrome 下解析出的两组 | 正文 ≥4.5:1、大字 ≥3:1，计算值断言（sepia 与 green 单独各一条）。**与 chrome 无关，不乘 10** |
| FA-04 | WI-10 | §8-2 | 四组状态色 × chrome 明暗 | 全部 ≥4.5:1；亮色档单独断言（原 500 档只有 2.15–3.76:1）。状态色属 chrome 轴，**与纸色无关** |
| FA-05 | WI-18 | §8-3 键盘可达 | `rd-pref-theme-*` / `rd-pref-font-*` | `role="radio"` ＋ 可聚焦（`tabIndex` ≥ -1 且能被 Tab 到）；现状是裸 `div`，完全不可聚焦 |
| FA-06 | WI-18 | §8-3 | `rd-pref-theme-*` 容器 | `role="radiogroup"`；方向键左右各移动一位并循环；Home / End 跳首尾 |
| FA-07 | WI-12 | §8-3 | `set-provider-toggle` | `role="switch"` ＋ `aria-checked`；Space 切换、Enter 不误触发第二次 |
| FA-08 | WI-13 | §8-3 | `lib-book-card` | `role="button"` ＋ Enter 与 Space 都可激活；`aria-label` 含书名 |
| FA-09 | WI-16 | §8-4 动态区域 | 搜索结果容器 | `aria-live="polite"`；结果更新后该区域文本变化被断言到（不是只断言属性存在） |
| FA-10 | WI-16 | §8-4 | AI 流式输出容器 | `aria-live="polite"`；流式追加时不重复播报已有内容（断言 `aria-atomic` 为 `false`） |
| FA-11 | WI-3 | §8-4 | 索引进度 | `aria-live="polite"`；进度变化时文本更新 |
| FA-12 | WI-1 | §8-4 | 降级横幅 | 横幅自带 `role="status"` ＋ `aria-live="polite"`；页面上承载同一条文案的 `aria-live` 区域数为 1（**不经 `LiveRegion` 二次播报**） |
| FA-13 | WI-16 | §8-5 | `prefers-reduced-motion` | 面板动效 `transition-duration` 为 `0s`；WI-8 骨架 `animation-name` 为 `none` |
| FA-14 | WI-16 | §8-6 | 阅读器工具栏 6 个图标按钮 | 每个都有非空 `aria-label`；源码内这些按钮的 `title` 属性不再作为唯一可访问名 |
| FA-15 | WI-16 | Tab 顺序 | 阅读器主界面 | Tab 序列等于视觉顺序（工具栏 → 正文 → 页脚），断言聚焦元素 testid 的序列 |
| FA-16 | WI-13 | Tab 顺序 | 书库三栏 | 序列为 左栏 → 中栏 → 右栏，逐个断言 |
| FA-17 | WI-16 | 快捷键冲突 | 焦点在 `rd-search-input` / `rd-ai-input` / `rd-note-editor` 内 | 按翻页键、主题切换键等全局快捷键**不触发全局行为**，字符正常输入到输入框（断言输入框 `value` 增长且页码不变） |
| FA-18 | WI-16 | 快捷键冲突 | 焦点在正文 | 同样按键**触发**全局行为（FA-17 的对照组，确保快捷键没被整体禁掉） |
| FA-19 | WI-6 | 语义 | `rd-conflict-dialog` | `role="alertdialog"`，且它不是 `role="dialog"` |
| FA-20 | WI-13 | 语义 | 书库页 | 页面存在恰好一个 `role="main"`；标题层级从 `h1` 起且不跳级 |

---

### 5.4 数据态

八种数据态，逐页逐面板跑一遍。**loading 骨架本身不断言**（WI-8），断言的是骨架之后的结果。

| 用例 ID | 归属 WI | 场景 | 断言目标 | 预期结果 |
|---|---|---|---|---|
| FD-01 | WI-13 | 空库 | `lib-empty` | 可见，且 `lib-book-card` 数量为 0；`lib-filter-empty` 不可见 |
| FD-02 | WI-13 | 筛选零结果 | `lib-filter-empty` | 可见，且 `lib-empty` 不可见（两者互斥） |
| FD-03 | WI-13 | 加载失败 | 书库错误态 testid | 可见且含重试入口；点重试重新发请求 |
| FD-04 | WI-13 | 三态互斥 | 空 / 零结果 / 错误 | 任意时刻三者可见数 ≤1 |
| FD-05 | WI-13 | 部分失败 | 批量索引 10 本失败 3 本 | 成功 7 本正常显示，3 个 `lib-migrate-failed-item`，**不是整批回滚也不是整批标成功** |
| FD-06 | WI-13 | 超长文本 | 书名 500 字符 | 卡片不撑破容器（卡片 `getBoundingClientRect().width` ≤ 网格列宽），文本截断或换行 |
| FD-07 | WI-13 | 超长文本 | 集合名 200 字符 | 侧栏不出现横向滚动（`document.body.scrollWidth` ≤ 视口宽） |
| FD-08 | WI-16 | 空章节 | 只有封面的 spine 0 | 正文区渲染封面，进度不等于 100%（与 FR-07 呼应） |
| FD-09 | WI-16 | 零标注 | Notes 面板 | `rd-notes-empty` 可见；`rd-notes-copy-all` / `rd-notes-export` 为 `disabled` |
| FD-10 | WI-16 | 搜索零结果 | `rd-search-empty` | 可见；结果列表元素数为 0 |
| FD-11 | WI-16 | 搜索失败 | `rd-search-failed` | 可见且有重试；不是显示成「零结果」 |
| FD-12 | WI-16 | 网络中断 | 面板加载中拔网 | 显示错误态，恢复后重试成功；**不是无限 loading** |
| FD-13 | WI-16 | SSE 流断 | AI 回答中途断流 | 已收到的内容保留，显示「连接中断」并给重试；不是清空已有文本 |
| FD-14 | WI-16 | SSE 流断 | 断流后点 `rd-ai-stop` | 不抛未捕获异常，按钮回到可发送态 |
| FD-15 | WI-16 | 超长文本 | AI 单条回答 50000 字符 | 消息容器 `overflow-x` 为 `auto` 或文本换行，`body.scrollWidth` ≤ 视口宽 |
| FD-16 | WI-16 | 超长文本 | 标注引文 5000 字符 | `rd-note-editor` 与 Notes 条目都不撑破容器 |
| FD-17 | WI-12 | 加载失败 | provider 模型列表拉取失败 | 下拉保持原值 ＋ 显示错误提示；不是清空成空下拉 |
| FD-18 | WI-12 | 空 | 未配置任何 provider | 设置页显示引导态而不是空白 |
| FD-19 | WI-3 | 部分失败 | 批量索引部分成功 | 成功项 `lib-status-indexed`、失败项 `lib-status-error`，两者同时存在 |
| FD-20 | WI-13 | 首屏顺序 | 数据返回前后 | 返回前 `lib-book-card` 数为 0，返回后等于接口条数（**不断言骨架**） |

---

### 5.5 降级状态 DEG-S1–DEG-S5

逐条从 `spec-frontend-design.md` §6.4 转成可断言用例。一条不少、一条不加。

| 用例 ID | 归属 WI | 状态 | 断言目标 | 预期结果 |
|---|---|---|---|---|
| FG-01 | WI-2 | DEG-S1 | `rd-degrade-s1` | 指纹不匹配时可见；匹配时元素数为 0 |
| FG-02 | WI-2 | DEG-S1 | `rd-degrade-s1` 文本 | 同时包含「暂停套用」与「未删除」两个词 |
| FG-03 | WI-2 | DEG-S1 | `GET /api/notes` | 该场景下标注条数与降级前相等（一条不删） |
| FG-04 | WI-2 | DEG-S1 | 正文 | 标注渲染标记数为 0（确实停止套用） |
| FG-05 | WI-2 | DEG-S1 | `rd-degrade-s1-excerpt` | 点击后摘录文本包含该标注的 `quote` 原文；把 `cfi` 置空后仍通过（不依赖 CFI） |
| FG-06 | WI-2 | DEG-S1 | `rd-note-stale-badge` | 数量等于 stale 标注条数（逐条标记，不是只有汇总） |
| FG-07 | WI-3 | DEG-S2 | `lib-status-stale` | 第五态渲染出独立 testid，与其余四态互不相同 |
| FG-08 | WI-3 | DEG-S2 | `lib-status-unknown` | 传枚举外的值：不抛异常，文本为「状态未知」且**不等于**「未索引」文案 |
| FG-09 | WI-3 | DEG-S2 | 未知态下的操作区 | 不渲染「开始索引」按钮（避免误导用户点它） |
| FG-10 | WI-3 | DEG-S2 | `lib-degrade-s2` | 搜索面板顶部可见，含「结果可能不全」语义，带 `lib-degrade-s2-reindex` |
| FG-11 | WI-4 | DEG-S3 | `lib-degrade-s3` ＋ `rd-degrade-s3` | `READER3_ALLOW_PICKLE=1` 时**两页都**可见；未设时两页元素数均为 0 |
| FG-12 | WI-4 | DEG-S3 | `lib-degrade-s3-list` | 默认折叠；toggle 后展开；列表项文本逐条等于未迁移书名 |
| FG-13 | WI-4 | DEG-S3 | `lib-degrade-s3-more` | 超上限时存在且含剩余条数；不超时元素数为 0 |
| FG-14 | WI-5 | DEG-S4 | `lib-storage-format-badge` ＋ `lib-status-indexed` | 「已索引 ＋ 旧格式」的书上**两者同时可见**（两个独立维度） |
| FG-15 | WI-5 | DEG-S4 | `lib-degrade-s4-progress` | 迁移中两次采样文本不同（进度确实在动）；失败 3 项则 `lib-migrate-failed-item` 数为 3 |
| FG-16 | WI-6 | DEG-S5 | `rd-conflict-dialog` | Esc 后仍可见；遮罩点击后仍可见；对话框内关闭按钮元素数为 0 |
| FG-17 | WI-6 | DEG-S5 | 两个出口 | 点「保留我的」/「采用远端」各自发出正确请求后对话框消失；两条路径下本地文本都不丢 |
| FG-18 | WI-6 | DEG-S5 | 远端不可达 | 只渲染 `rd-conflict-keep-mine` 且它不是 `disabled`（**不许两个都禁用造成死路**） |
| FG-19 | WI-1 | 通用-1 色彩 | 五个横幅 | warn 三条解析为 `--r3-warning`、danger 两条解析为 `--r3-error`；没有一条解析为 `--r3-accent` |
| FG-20 | WI-1 | 通用-1 边框 | 五个横幅 | `border-color` 非 `transparent` 且等于该状态前景色（只有淡底不算数，1.10–1.32:1 等于看不见） |
| FG-21 | WI-1 | 通用-2 a11y | 五个横幅 | 四条横幅 `role="status"` ＋ `aria-live="polite"`；DEG-S5 为 `role="alertdialog"` |
| FG-22 | WI-1 | 通用-3 可关闭 | DEG-S1–S4 | 关闭后 `sessionStorage` 出现对应键，同会话内重挂不再出现；DEG-S5 无关闭按钮 |
| FG-23 | WI-1 | 通用-4 testid | 五个状态 | 容器与主操作按钮各有 testid，五个容器 testid 互不相同（共用 testid 断不出「是哪一态」） |
| FG-24 | WI-13 | 通用-5 朴素优先 | Phase 3 门槛 | DEG-S1–S4 在朴素形态下**可见**即算过（此条在 012 分支上跑，本计划只登记） |

---

### 5.6 阅读器专项

#### 5.6.1 三个原型实测缺陷

| 用例 ID | 归属 WI | 缺陷 | 断言目标 | 预期结果 |
|---|---|---|---|---|
| FR-01 | WI-17 | 连翻只进一步 | `rd-page-indicator` | 章内间隔小于一次渲染耗时连触发 3 次「下一页」，末页码等于起始 ＋3 |
| FR-02 | WI-17 | 跨章跳两章 | 章节索引 | 章末快速连触发 2 次「下一页」，章节索引等于起始 ＋1（不是 ＋2） |
| FR-03 | WI-17 | 向前跨章落错页 | `rd-page-indicator` | 章首触发「上一页」，落到上一章**最后一页**：页码等于上一章总页数且不等于 1 |
| FR-04 | WI-17 | 现状定性 | FR-03 的现状运行 | 先按现状跑一次并把结果记进 `baseline-1b`（缺陷 3 是否存在于生产端尚未验证） |
| FR-05 | WI-17 | 翻页锁 | `rendition` 调用计数 | 锁生效期间重复触发不增加调用次数 |
| FR-06 | WI-17 | 指示器一致 | `rd-page-indicator` | 连续 5 次翻页，每次的显示值等于实际渲染页 |

#### 5.6.2 K1–K6 各一条可失败断言

**「元素存在」不算断言。** 每条都要能因契约被破坏而变红。

| 用例 ID | 归属 WI | 契约 | 断言目标 | 预期结果（可失败点） |
|---|---|---|---|---|
| FR-K1 | WI-15 | K1 覆盖层 DOM id | 控制台输出 | 删掉 `OVERLAY_IDS` 里任一元素后初始化：出现 `error` 级输出且内容含缺失元素 id，同时**不出现未捕获异常**。现状是静默返回 `null` |
| FR-K2 | WI-15 | K2 `data-action` / `data-color` | `tsc` 退出码 | 构造一个枚举外取值的调用，类型检查**非零退出**。运行时另断言未知 action 不静默吞掉 |
| FR-K3 | WI-15 | K3 覆盖层挂载 | `containingBlockAncestor` | 见 FP-10 / FP-11：三覆盖层每个用例 `afterEach` 返回 `null`；21 种制造属性各自返回非 `null` |
| FR-K4 | WI-15 | K4 事件名 | 事件监听计数 | 六个事件各触发一次，对应处理器各被调用恰好 1 次；把常量改成别的字符串后用例变红 |
| FR-K5 | WI-15 | K5 `window.Reader3Epub` | 接口成员 | 7 个纳入成员逐个实际调用并断言返回值形状；2 个 `@deprecated` 成员在 WI-16 后引用数为 0。**`search.js` 对 `getContentRoot` / `onContentsReady` 的调用同样纳入类型检查** |
| FR-K6 | WI-15 | K6 `getReaderContext` | 抛错 | 构造无法解析 book id 的场景：**抛错**并断言错误类型或消息；`context.ts` 内 `location.pathname` 出现次数为 0 |

#### 5.6.3 iframe 边界三重断言

| 用例 ID | 归属 WI | 断言 | 预期结果 |
|---|---|---|---|
| FR-A | WI-14 / WI-16 / WI-18 | A：`body.textContent` 的 UTF-16 序列 | 重构前后完全相等 |
| FR-B | 同上 | B：`bodySignature(body)` 结构签名 | 重构前后完全相等（实现见 `spec-frontend-design.md` §6.0） |
| FR-C | 同上 | C：CFI 往返 | 解析回同一段引文。**WI-18 的栏宽注入路径上，C 才是真正要证的那条**——栏宽改变的是「标注落在第几屏」 |

---

### 5.7 响应式

三档断点（`spec-frontend-design.md` §7），桌面与移动各跑一遍。验收标准是「**每个功能在每档下都可达**」，不只是「不横向滚动」。

| 用例 ID | 归属 WI | 视口 | 断言目标 | 预期结果 |
|---|---|---|---|---|
| FV-01 | WI-13 | 1440×900 | 书库三栏 | 三栏都可见；每栏 `min-width` 计算值为 `0px` |
| FV-02 | WI-13 | 1024×800 | 书库右栏 | 折叠为抽屉，`lib-right-toggle` 可点且点后抽屉可见 |
| FV-03 | WI-13 | 390×844 | `lib-collections-create` | 可见且 `getBoundingClientRect()` 完全落在视口内（**实测失效项 2** 的回归） |
| FV-04 | WI-13 | 390×844 | 书库右栏内容 | 矩形完全落在视口内（现状 `x=390, width=249`，**实测失效项 1** 的回归） |
| FV-05 | WI-13 | 390×844 | 搜索结果面板 | 执行搜索后结果面板可见且可滚动（现状搜索执行了但结果看不见） |
| FV-06 | WI-13 | 390×844 | 书卡网格 | 列数为 2 |
| FV-07 | WI-16 | 390×844 | AI 面板 | 单栏布局；`Background` 按钮矩形完全落在视口内；头部按钮不折两行（**实测失效项 3** 的回归） |
| FV-08 | WI-12 | 390×844 | `set-provider-toggle` 所在行 | `Enabled` 控件 `getBoundingClientRect().right` ≤ 视口宽（**实测失效项 4** 的回归） |
| FV-09 | WI-16 | 1440×900 | 阅读器面板 | push 布局：面板打开后正文容器宽度变小 |
| FV-10 | WI-16 | 1023×800 | 阅读器面板 | overlay 布局：面板打开后正文容器宽度不变 |
| FV-11 | WI-16 | 三档 | 翻页控件 | 隐形热区（`.nav-zone-*`）查询返回 0 个；`rd-page-prev` / `rd-page-next` 各有非空 `aria-label`；767×800 下两者不可见（规格 §11-R2） |
| FV-12 | WI-16 | 390×844 | 阅读器工具栏 | 位于视口底部（`getBoundingClientRect().bottom` 接近视口高）；面板全屏 |
| FV-13 | WI-18 | 1440×900 | 正文行宽 | 连续取 3 行，每行字符数落在 45–75 |
| FV-14 | WI-18 | 390×844 | 正文行宽 | 同上 |
| FV-15 | WI-13 / WI-16 / WI-12 | 三档 × 三页 | `document.body.scrollWidth` | 均 ≤ 视口宽（任何断点下 `body` 都不横向滚动，9 条参数化） |
| FV-16 | WI-13 | 三档 × 三页 | 表格与代码块 | `overflow-x` 计算值为 `auto` |

---

### 5.8 主题与 token 解析

主题是**两根轴**（chrome `data-theme` × reading `data-reading-theme`，裁决见规格 §11-R7，契约唯一定义处是 §3.3）。
组合矩阵 = chrome 2 种有效解析（light / dark；`system` 是解析策略不是第三种视觉）× reading 5 值 = **10 种**。

> **但不是所有断言都乘 10。** 纸色与高亮是绝对值，只有 `auto` 跟 chrome 走：
> 「墨压纸」四条、「高亮压纸」的组合都与 chrome 无关；真正要跑满 10 遍的只有**悬空检查**与**接缝**。下表逐条注明各自的规模。

| 用例 ID | 归属 WI | 断言目标 | 预期结果 |
|---|---|---|---|
| FT-01 | WI-10 | 全部 `--r3-*` | **10 种组合**（chrome light/dark × reading auto/paper/sepia/green/night）下 `getComputedStyle` 解析均非空字符串（**悬空 `var(--x)` 会解析成空串**） |
| FT-02 | WI-10 | 组件样式文件 | 对 `--p-*` 的直接引用次数为 0（组件只许引 Tier 2） |
| FT-03 | WI-10 | `--r3-warning` / `--r3-error` ＋ 四个 `-subtle` | 10 种组合下都有定义 |
| FT-04 | WI-7 | `--r3-hl-*-rgb` | 10 种组合下都解析为三个数字 |
| FT-05 | WI-7 | 全仓库 CSS | `color-mix(` 出现次数为 0 |
| FT-06 | WI-7 | 九个原使用点 | 形如 `rgb(var(--r3-hl-*-rgb) / α)`，α 分别为 .35（4 处）、.45（4 处）、.18（1 处） |
| FT-07 | WI-7 | 亮纸 marker 四色 | `paper` / `sepia` / `green` ＋ `auto`@light 四种纸下，合成后与该纸墨色对比度均 ≥4.5:1（计算值断言，**不乘 chrome**） |
| FT-08 | WI-7 | 夜纸 marker 四色 | `night` ＋ `auto`@dark 两种纸下，背景 alpha 不等于 1，**且**带非背景提示：`text-decoration-line` 非 `none` 或 `border-left-width` 大于 0（黄 3.02 / 绿 3.94 实色不达标，且 paper-night 下解集为空） |
| FT-09 | WI-7 | `.anno.is-note` | 解析背景色不等于 `--r3-accent` 解析色（D-5 之后品牌蓝会与选区、focus ring 撞色） |
| FT-10 | WI-10 | chrome 轴 | `data-theme="dark"` 下 `body` 背景色计算值与 light 不同；`--r3-text` 对 `--r3-bg` ≥4.5:1。**跑满 5 个 reading 值，结果必须一致**（chrome 不受纸色影响） |
| FT-11 | WI-18 | 两轴持久化 | 两个 key 两个属性：切纸色写 `reader3.reader.theme` ＋ `<html data-reading-theme>`（`auto` 也写出属性），不动 `data-theme`；切界面明暗写 `reader3.ui.colorScheme` ＋ `<html data-theme>`（`system` 是**移除**属性），不动 `data-reading-theme`。各自刷新后与渲染一致 |
| FT-12 | WI-18 | 字号作用域 | 改字号只影响 iframe 内文本，iframe 外元素字号不变（**仅 iframe** 作用域） |
| FT-13 | WI-10 | token 悬空 lint | 0.8 的 lint 在全部样式文件上通过；`var(--x, fallback)` 有 fallback 也算违规 |
| FT-14 | WI-10 | 纸色绝对性 | `paper` / `sepia` / `green` / `night` 下解析的 `--r3-page-*` 与 `--r3-hl-*`，在 light 与 dark chrome 下**逐字相等** |
| FT-15 | WI-10 | `auto` 是唯一的跟随档 | `auto` 下 `--r3-page-bg` 在 light 与 dark chrome 下**不相等**，且各自等于该 chrome 的 `:root` 声明值；CSS 里不存在 `[data-reading-theme="auto"]` 选择器（**它靠没有规则实现**） |
| FT-16 | WI-10 | 纸色不外泄 | 书库页与设置页 `body` 的 `background-color` 计算值，在 `data-reading-theme` 取五个值时全部相同 |
| FT-17 | WI-10 | FOUC | 首帧（`DOMContentLoaded` 前）`<html>` 上两个属性已按存储值 stamp 完毕；无 `.reader-shell` 存在时 inline script 不抛错 |

---

### 5.9 矩阵与 009 的边界

| 归 009 | 归本矩阵 |
|---|---|
| 标注读路径 `R-1`…`R-6` | 按钮八态 |
| 标注写路径 `W-1`…`W-10` | 面板互斥、焦点陷阱与归还 |
| 宿主契约 `K-1`…`K-6` 的用例定义 | 键盘与 a11y（§8 六条） |
| 跨端 `X-1` / `X-2` | 数据态八种 |
| `baseline-1b` 的组成与 soak 门槛 | 降级状态 DEG-S1–DEG-S5 |
| —— | 响应式三档 |
| —— | 主题 × token 解析 |

本矩阵的 `FR-K1`…`FR-K6` 是对 009 的 `K-1`…`K-6` 的**补强**（把「元素存在」换成可失败断言），不是替代。两边冲突时以 009 为准。

---

## 6. 从 Codex 评审继承的未决项

`review-codex.md` 的台账留在技术栈迁移文件夹（一次评审的记录不拆开），其中五条属于前端范围，在此继承：

| # | 严重度 | 问题 | 本计划的落点 |
|---|---|---|---|
| **#3** | HIGH | K3 的 `containingBlockAncestor()` 会漏报：没查独立的 `translate` / `rotate` / `scale`、`content-visibility`，`will-change` 的取值集合也漏了 `contain` / `content-visibility` / `backdrop-filter` / `translate` / `rotate` / `scale`。这些属性同样能建立 fixed containing block | **未决**。补齐属性集合、为每种制造属性建参数化浏览器断言、旧 Safari 另查 `webkitBackdropFilter`——落 **WI-16 验收第 6 条**，属性集合补进 `contracts/annotation-host-contracts.md` K3 |
| **#7** | MEDIUM | 「四字体」与设计规格的 `system` / `serif` 二选一冲突；思源宋体同时被称作「待删商业字体」和「可 self-host 开源字体」 | **已在 WI-18 统一为 `system` / `serif` 两值**。仍未决的是 serif 的资产归属：self-host 思源宋体，还是在资产落地前退回系统 serif——**WI-18 实施时必须二选一并写进验收第 10 条** |
| **#10** | MEDIUM | 现状已经实现了字号 / 行距并存在 `reader3-font-settings`，计划却称控件全无处理器，还改成新的 localStorage key；没定义一次性迁移，会**重置用户偏好** | **落 WI-18 验收第 12–14 条**：legacy JSON 读取 ＋ 范围校验 ＋ 写新 key ＋ 迁移完成标记 ＋ 回归测试 |
| **#13** | HIGH | E2E 执行器混了两套模型：仓库装的是 Python `pytest-playwright`，009 却在用 Node Playwright Test 的 `webServer` 概念并要求每 worker 一服务，当前没有可执行拓扑 | **裁定归 A 的 `tasks/009-e2e-annotations.md`**（用例定义以那边为准）。本计划的测试矩阵一律按 **Python runner** 书写，不写 Node `webServer` 语法 |
| **#19** | HIGH | 4A.2 先迁 settings、4A.3 才建共享模块，会被迫先写临时代码再重构 | **已处置**：4A 顺序改为 `4A.0 → 4A.1 → 4A.3 → 4A.2 → 4A.4`，对应 WI-9 → WI-10 → WI-11 → WI-12 → WI-13，共享模块在设置页之前 |

评审原文里的裸 `S1`–`S5` 与已删除的 `tasks/014` 路径按当时原样保留，不追改。
