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

> ⚠️ **先跑哪一批，以 §4.0 为准，不是以上面的顺序为准。** Track D（WI-1–WI-8）的验收按 §4.0 拆成两半：**定义类**在 `010` 上跑，**实现类**（57 条里的 56 条）要等 WI-9 交付源码根与 Vitest 宿主，随 4A / 4B 一并激活。所以第一行调用串在 `010` 上消费的是**定义类那一半**，它结尾那句「每个工作项的验收标准必须逐条二元判定」在 `010` 上的判定对象是 §4.0 的 **`010` 退出门槛**，不是 WI-1–WI-8 的验收清单——那份清单里只有 1 条标着 `验于 010`。
>
> **实际意义上第一个能开工的 WI 是 WI-9**（裁定见 §5.0 执行器表下方）。它之前只有文档工作，而它压着的三个非 WI 前置——007 的 0.4 / 0.5 / 0.8——**已于 2026-08-23 交付，并随 007 于 2026-08-24 合入 `master`（PR #18）——三项前置现已全部解除**，合入事实见 [`tasks/007-hygiene-and-contracts.md` 的「合入记录」](../20260816-tech-stack-migration/tasks/007-hygiene-and-contracts.md)。`master` 上现在有那三条 lint，也有回贴过的 testid。逐项状态见 §3。

> ~~此前这里写着「前置已交付，等合入」。~~ 那个口径存在的唯一理由是 007 还挂在分支上；2026-08-24 合入后作废。
>
> ~~此前这里写的是「实测三项均未开工」。~~ 该判断作于 007 收尾之前，2026-08-23 被实测推翻——007 的八项全部转 ✅，见 [`tasks/007-hygiene-and-contracts.md`](../20260816-tech-stack-migration/tasks/007-hygiene-and-contracts.md)。

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
| **0.6** 事实性修复 | **已完成**（2026-08-23 收尾：`.gitignore` 合并冲突标记、版本号对齐、示例配置补齐三项齐了） | 同上 |
| **0.2 / 0.3 / 0.4 / 0.5 / 0.8** | **已完成**（2026-08-23） | 同上 |
| 007 分支**是否已合入 `master`** | **✅ 是**（2026-08-24，PR #18）。领先量归 0，八项全在主干上 | [`tasks/007-hygiene-and-contracts.md` 的「合入记录」](../20260816-tech-stack-migration/tasks/007-hygiene-and-contracts.md) |

> ~~此前这张表把 0.2 / 0.3 / 0.4 / 0.5 / 0.8 记为「未开始」、0.6 记为「部分完成」。~~ 那是 007 收尾前的实测，2026-08-23 全部转 ✅ 后作废。此后 007 于 2026-08-24 合入 `master`，**「等合入」这个口径也随之作废**——现在它就是在主干上。

**三处 token 悬空引用是 007 已经修好的**，本计划只消费结果、不重做：

| 悬空引用 | 修法 |
|---|---|
| `--r3-warn` / `--r3-danger` | 重命名为 `--r3-warning` / `--r3-error`，并补齐四个同名 `-subtle` 底色 |
| `--r3-sidebar-w` / `--r3-right-w` | 补定义（否则 `grid-template-columns` 整条失效，三栏塌成默认布局） |
| `--r3-text-quiet` | ~~补 `:root` 下的定义~~ → **2026-08-23 直接删除**：全仓库 0 个 `var()` 消费者，两个主题下都与 `--r3-text-subtle` / `--r3-text-muted` 重复；「安静文字」在阅读轴上由 `--r3-page-quiet` 承担。见 spec §3.3 文字色实测对比度表 |

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
| `data-testid` 命名 canonical 正则 | `scripts/lint_testid_naming.py` 的 `CANONICAL`（裁决见 [`docs/adr/0013`](../../adr/0013-testid-invariant.md)） |
| 三条 lint 的边界 | 同上 §6（0.5、0.8） |
| Playwright E2E 用例 ID（`R-1`…`R-6` / `W-1`…`W-10` / `K-1`…`K-6` / `X-1` / `X-2`）与激活分组 | [`tasks/009-e2e-annotations.md`](../20260816-tech-stack-migration/tasks/009-e2e-annotations.md) |
| API v1 冻结清单、覆盖率门槛数值 | [`tasks/008-test-safety-net.md`](../20260816-tech-stack-migration/tasks/008-test-safety-net.md) |
| 两文件提交协议、读取状态机三态 | [`docs/adr/0007`](../../adr/0007-crash-safe-publish-protocol.md) |

**testid 命名**：canonical 正则的唯一定义处是 `scripts/lint_testid_naming.py` 的 `CANONICAL` 常量（[ADR-0013](../../adr/0013-testid-invariant.md)），从那里 import 或复制，不要从任何 Markdown 表格里复制。本计划涉及的所有新建元素一律 `lib-` / `rd-` / `set-` 三前缀之一。原型原有 138 个 testid 站点**零个合规**，其中 24 个带 `reader-` / `library-` 前缀的**看起来像合规但不是**。重命名本身归 0.5，**已于 2026-08-23 完成**（新旧对照见 [`contracts/testid-rename-map.md`](../20260816-tech-stack-migration/contracts/testid-rename-map.md)）；本计划只负责新元素首次就写对。

**分支落点**：Track D → `010-design-degradation-states`；WI-9–WI-13 → `013-ts-frontend-shell`；WI-14–WI-19 → `014-ts-frontend-reader`；WI-20 → `015-launch-experience`。编号来源见上表第一行。

---

## 3. 前置契约

三项在 `007-hygiene-and-contracts` 实施、**本计划只消费不重述**。三项**已于 2026-08-23 交付，并随 007 于 2026-08-24 合入 `master`**（PR #18，见 [`tasks/007-hygiene-and-contracts.md` 的「合入记录」](../20260816-tech-stack-migration/tasks/007-hygiene-and-contracts.md)）——**前置已全部解除，`master` 上就是下面这个状态**：

- **0.4** 四个落后 JS 文件（`library-search.js` / `search.js` / `ai.js` / `settings.js`）IIFE 化，顺带消掉四份互相覆盖的 `escapeHtml` 全局符号 —— **已完成，commit `f11b346`**。
  > ⚠️ **0.4 交付的是「IIFE 化 ＋ 消掉全局冲突」，不是「收敛」。** 四份 `escapeHtml` 实现今天仍是四份，只是各自关在自己的 IIFE 里不再互相覆盖。**把它们真正收敛成单一 `escape.ts` 仍是 WI-11 / ET-9 的活**，裁决（取哪派的空值语义、哪派的写法）也在 WI-11 里，不在 007。此前这里写的「0.4 `escapeHtml` 收敛 —— 决定 WI-11 里 `escape.ts` 的形状」把因果写反了，作废。
- **0.5** canonical testid 正则 ＋ 选择器 lint ＋ 命名 lint —— 是本计划全部测试矩阵的选择器基础。**已完成**：原型 221 个唯一 testid 全部合规，现有模板与生成 DOM 回贴了其中 152 个，反向新造为 0；逐条新旧映射见 [`contracts/testid-rename-map.md`](../20260816-tech-stack-migration/contracts/testid-rename-map.md)。
- **0.8** token 悬空引用 lint —— 是 DEG-S1–DEG-S5 横幅不静默失色的保证。**定义在 `plan-tech-stack-migration.md` §6 的 0.8 一节，本文件只引用，不重述条款**（含「有 fallback 也算违规」那一条——它已回写到那边的定义处）。**已完成，实测违规数 0。** 本计划对 0.8 的唯一增量是**扫描范围**要覆盖 `{前端源码根}`，由 WI-9 验收 12 落地。

**三条 lint 都接在 `.github/workflows/lint.yml` 的 `contracts` job 里，而该 workflow 于 2026-08-23 改成只在发版时触发**——`release.published` ＋ `v*` tag push ＋ 手动 `workflow_dispatch`，日常 push 与 PR 不再跑。这一点对本计划有直接后果：**WI-9 §9.3 的 token 硬编码 lint 和 WI-9 要接的其余 lint 挂的是同一个 workflow，因此它们不是每次 push 的实时护栏，攒下的违规会一次性堆到发版那天。** 实施者要么在本地随手跑（三条 lint 都是零依赖标准库脚本），要么在 Actions 页面手点 `workflow_dispatch`，不要指望 PR 上有红叉。

WI-1 到 WI-20 全部以这三项落地为前置，下面各 WI 的「前置 WI」一栏不再重复写。

**本计划另有第四条 lint，但它不属 007 契约。** token **硬编码** lint 由 WI-9 §9.3 定义并交付（接进 WI-9 验收第 3 条那同一条命令），归属在本计划这一侧——别把它记成 007 的产出，007 那边不会有人做它。它与上面的 0.8 是**方向相反的一对**：0.8 管「引用的 token 不存在」，它管「该用 token 的地方写了字面量」；定义与理由都在 §9.3，此处不重述。

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

### 4.0 Track D 的交付物分两类，落在两个分支上

> ⚠️ **照字面读，WI-1 在 `010` 上既没有目录可写，也没有执行器可跑。** 三条实测事实撞在一起：
> ① WI-1 的范围写的是 `{前端源码根}/components/degrade-banner.*`，而 `{前端源码根}` 由 **WI-9** 定（§3）；
> ② WI-1 的七条验收**全部**要查 DOM 与计算样式，而 TS 单测宿主（Vitest ＋ jsdom）今天不存在、
> 也由 **WI-9** 建（§5.0 的执行器表）；③ 分支落点把 Track D（WI-1–WI-8）放在 `010`、把 WI-9 放在
> `013`，`010` 在 `013` 之前（§2）。
>
> **不改 WI 编号、不改分支落点，改成按验收拆两半。** 口径本来就写在 §3.1 里：Track D 的文案与状态
> 定义要在 012 开工前定下来，**哪怕组件还没建**。

| 类别 | 内容 | 落在哪 | 前置 |
|---|---|---|---|
| **定义类** | 文案、状态枚举、tone 映射、testid 清单、对比度硬约束、token 取值裁定 | `010-design-degradation-states` | 无（可与 ET-1 并行） |
| **实现类** | 组件源码，以及需要 DOM／计算样式／`sessionStorage`／Vitest／lint 才能验的验收 | `013-ts-frontend-shell`；阅读器侧的随 WI-16 落 `014-ts-frontend-reader` | **WI-9**（源码根位置 ＋ Vitest ＋ jsdom 宿主） |

012 写朴素横幅时消费的正是**定义类**这一半——所以定义类不能等 WI-9，也不需要等；实现类等 WI-9，
等的是目录与执行器，不是设计结论。

**标注规则**：WI-1–WI-8 的每一条验收标准前面各带一个标记，二值判定，没有第三类：

- `【定义类·验于 010】` —— 读文档就能验（文案、枚举、清单、裁定值）。
- `【实现类·前置 WI-9·验于 013】` —— 需要跑代码才能验（DOM 查询、计算样式、存储、lint、网络）。
- `【实现类·前置 WI-9·验于 014】` —— 同上，但断言目标只存在于阅读器页（DEG-S1、DEG-S5、
  渲染出来的高亮元素），它们随 WI-16 落地。

`/tdd-guardian:workflow` 跑 `010` 那一批时，只消费带 `验于 010` 的条目；带 `前置 WI-9` 的条目在
`010` 上是**未激活**状态，不是失败状态。

#### `010` 的退出门槛

> ⚠️ **「未激活」不等于「不用做」，也不等于「`010` 没有可判的内容」。** 实测 WI-1–WI-8 共 **57** 条验收，标记分布是 `验于 010` **1** 条、`验于 013` **34** 条、`验于 014` **22** 条。（2026-08-23 随 WI-4 新增第 7 条共享模块验收，`013` 由 33 增至 34、总数由 56 增至 57；这三个数字每改一条验收就要重数一遍，否则立刻变成假数据。）也就是说照验收清单读，`010` 上只有一条可判——而那一条（WI-8 第 5 条）本身还是「人工核对」。这样一来「Track D 做完了」在 `010` 上没有定义。
>
> 定义类的内容其实是齐的，只是它们**写在各 WI 的散文段落里**（标着「定义类·验于 010」记号的那 12 处，grep 可数——**标记必须逐字一致**，WI-7 那处此前漏了「定义类·」前缀，已补齐；本句刻意不复写该记号的原样，否则它会把自己也数进去），没进验收清单，所以判不了。下面这张表把它们提成 `010` 的退出门槛。

**`010` 允许改的文件集**：`designs/`、`spec-frontend-design.md`、以及本文件。**不碰生产源码**——与 `plan-tech-stack-migration.md:527`「它只改 `designs/` 与设计规格，不读一行生产代码」对齐。各 WI 的「范围」栏里凡是 `{前端源码根}` 下的路径，都属实现类那一半，不在 `010` 上动。

| # | 来源 | 定义类交付物 | 落在哪 | 怎么判（二值） |
|---|---|---|---|---|
| D-1 | WI-1 | 四个 `-subtle` 底色对页面底的对比度实测值 ＋「淡底不能独自表达状态」硬约束 | `spec §3.3` 对比度表 | 表中四行齐全，每行给出浅色与夜间两个实测值；且四个状态样式各自都同时带边框或图标（表里逐行可查） |
| D-2 | WI-1–WI-6 | DEG-S1–DEG-S5 五组 testid 清单 | 各 WI 的「涉及 testid」栏 | 五组齐全；每个值都是字符串字面量，且匹配 canonical 正则（`^(?:lib\|rd\|set)-[a-z0-9]+(?:-[a-z0-9]+)*$`）；清单里无「等」「若干」这类开口 |
| D-3 | WI-2 | 横幅文案必须明说「标注暂停套用，**未删除**」 | WI-2「做什么」栏 | 文案字面存在，且「未删除」三字在内 |
| D-4 | WI-3 | 五态枚举（第五态定名 `stale`）与「状态未知」文案 | WI-3 | 枚举恰好五项、五个名字全部确定；未知态文案字面确定 |
| D-5 | WI-4 | 触发条件 `READER3_ALLOW_PICKLE=1` 与列表条数上限 | WI-4 | 两处都是具体值，无「待定」「按需」 |
| D-6 | WI-5 | `storage_format` 与索引状态两维度正交的裁定 | WI-5 | 正交性写明；两个维度的取值枚举各自齐全 |
| D-7 | WI-6 | 零关闭路径 ＋ 二选一文案 | WI-6 | 出口恰好两个，两条文案字面确定（**文案本身以 WI-6「做什么」栏为准，本行不重述**——此前本行写成「取远端」，与定义处的「采用远端」不一致，正是重述导致的漂移），且无第三条关闭路径 |
| D-8 | WI-7 | 三元组方案（存 `--*-rgb`、alpha 留使用点）与九处 alpha 取值 35 / 45 / 18 | `spec §3.2` ＋ `§3.3`（token 定义）＋ WI-7（使用点） | 九个使用点逐一列出选择器与 alpha，无「同上」「其余同理」；且 `--p-hl-*-rgb`（亮暗共八个）与 `--r3-hl-*-rgb`（四个，在 §3.3 的四个块里各声明一遍）在 **spec** 里有字面定义 |
| D-9 | WI-8 | 测试矩阵中不存在以骨架为断言目标的用例 | 第 5 节 | 第 5 节中 `骨架` / `skeleton` 作为**断言目标**出现的命中数为 0（可 grep，不靠人工核对）。**这不等于放弃 `prefers-reduced-motion` 下的无障碍保证**——那条落在 WI-8 验收 2 / 3 的 CSS 产物断言上，理由见 §5.0「骨架为什么连样式都不在 E2E 里断」 |

**这九项全部满足，`010` 即为做完。** WI-1–WI-8 标着 `前置 WI-9` 的那 56 条验收在 `010` 上不参与判定，它们的执行归属见 WI-13 验收 10 与 WI-16 验收 16——**那两条才是它们真正被翻牌的地方**。此前这 56 条从 `010` 的账上划掉之后，没有被记到任何别的账上，等于谁都不欠。

---

### WI-1: DegradeBanner 基础组件

**范围**（照 §4.0 拆两半，与下面「前置 WI」的拆法一致）：

- **定义类（`010`）**：`spec-frontend-design.md` §3.3 的对比度表与 tone 映射；本节 WI-1–WI-8 的 testid 清单。**不碰生产源码。**
- **实现类（`013`）**：`{前端源码根}/components/degrade-banner.*`（组件本体 ＋ 样式）。

`designs/reader-pro-next/components.jsx` 只作参考，不改。

**前置 WI**：
定义类无（Track D 的第一项）；
实现类前置 **WI-9**（源码根与 Vitest ＋ jsdom 宿主）。

**做什么**：建一个所有降级横幅共用的基础组件，五个状态在它上面派生。

- `tone` 两档：`warn`（DEG-S1 / DEG-S2 / DEG-S4）、`danger`（DEG-S3 / DEG-S5）。
- `dismissible` 布尔，关闭状态存 `sessionStorage`；**DEG-S5 不接受这个属性**。
- 自带 `role="status"` ＋ `aria-live="polite"`。**不许复用原型的 `LiveRegion`**——那个是 sr-only 的，只能播报、不能当可见横幅用。
- 内容用 children 插槽，不是 `primaryLabel` 字符串——各状态的操作按钮数量和形态不一样。
- **testid 逐状态给**，不是共用一个 `degrade-banner`：`rd-degrade-s1` / `lib-degrade-s2` / …。`acceptance-p3` 要断言「出现的是哪一个状态」，共用 testid 断不出来。

**硬约束（对比度实测）**〔**定义类·验于 010**〕：四个 `-subtle` 底色对承载面的逐行实测值**定义在 `spec-frontend-design.md` §3.3 的淡底对比度表**（此处不重述数值——2026-08-23 正是因为两处各存一份而发现旧数复算不出）。结论：全部远低于非文字元素的 3:1 门槛，且换哪个承载面都一样。**只有底色的横幅在视觉上等于不存在**——必须同时有边框或图标，边框用该状态的前景色本身（不新增 border token）。这条裁定与 tone 两档的映射（warn ＝ S1/S2/S4，danger ＝ S3/S5）是 012 朴素横幅要消费的那一半，`010` 上就要定死。

**涉及 testid**〔**定义类·验于 010**〕：`rd-degrade-s1`、`lib-degrade-s2`、`lib-degrade-s3` / `rd-degrade-s3`、`lib-degrade-s4`、以及各自的主操作按钮 `*-action` 与关闭按钮 `*-dismiss`。清单本身是文档级交付，`010` 上逐个核对拼写与前缀即可，不需要组件存在。

**涉及降级状态**：全部五条的载体。

**验收标准**：

1. 【实现类·前置 WI-9·验于 013】渲染 `tone="warn"` 与 `tone="danger"`，两者的 `border-color` 计算值不同，且都不等于 `transparent`。
2. 【实现类·前置 WI-9·验于 013】组件根元素的 `role` 属性等于 `status`，`aria-live` 属性等于 `polite`。
3. 【实现类·前置 WI-9·验于 013】页面内不存在两个 `aria-live` 区域同时承载同一条降级文案（即横幅不经由 `LiveRegion` 二次播报）。
4. 【实现类·前置 WI-9·验于 013】`dismissible=true` 时点关闭按钮后组件从 DOM 移除，且 `sessionStorage` 里出现对应键；同一会话内重新挂载不再出现。
5. 【实现类·前置 WI-9·验于 013】`dismissible=false` 时不渲染关闭按钮（查询关闭按钮 testid 返回 0 个元素）。
6. 【实现类·前置 WI-9·验于 013】五个状态各自渲染出的根元素 testid 互不相同。
7. 【实现类·前置 WI-9·验于 013】token 悬空 lint（0.8）在本组件样式文件上通过。

---

### WI-2: DEG-S1 标注 stale

**范围**：阅读器顶部横幅；Notes 面板逐条 stale 标记；「查看原文摘录」入口。

**前置 WI**：
定义类 **WI-1**（tone 映射与文案骨架）；
实现类前置 **WI-1 ＋ WI-9**（源码根与 Vitest ＋ jsdom 宿主），断言目标在阅读器页，随 WI-16 落 `014`。

**做什么**：`notes.json` 指纹与当前 spine 指纹不匹配时，标注停止套用，但**一条都不删**。

- 横幅文案必须明说「标注暂停套用，**未删除**」〔**定义类·验于 010**〕。少了「未删除」三个字，用户会以为数据没了。这句文案与下面的触发条件是 012 朴素横幅直接抄走的那一份，`010` 上定死，不等组件。
- 「查看原文摘录」入口不依赖 CFI——用 `Annotation` 的 `quote` / `prefix` / `suffix` 三个字段拼出摘录。CFI 在 stale 场景下正是失效的那个东西。
- Notes 面板每一条 stale 标注单独挂 stale 角标，不是只在面板顶部放一条汇总。

**涉及 testid**：`rd-degrade-s1`、`rd-degrade-s1-excerpt`（查看原文摘录）、`rd-note-stale-badge`（逐条角标）。

**涉及降级状态**：DEG-S1。

**验收标准**：

1. 【实现类·前置 WI-9·验于 014】构造指纹不匹配的 `notes.json`，加载阅读器后 `rd-degrade-s1` 可见。
2. 【实现类·前置 WI-9·验于 014】该横幅的可见文本同时包含「暂停套用」与「未删除」。（文案本身归上面的定义类条目，本条断的是它确实被渲染出来。）
3. 【实现类·前置 WI-9·验于 014】同一场景下 `GET /api/notes/{book_id}` 返回的标注条数与断言前一致（**一条不少**）。
4. 【实现类·前置 WI-9·验于 014】正文里不存在任何标注渲染标记（标注套用确实停了）。
5. 【实现类·前置 WI-9·验于 014】点 `rd-degrade-s1-excerpt` 后出现的摘录文本包含该标注的 `quote` 字段原文。
6. 【实现类·前置 WI-9·验于 014】摘录渲染路径不读取 `cfi` 字段（把 `cfi` 置空后第 5 条仍通过）。
7. 【实现类·前置 WI-9·验于 014】Notes 面板里每条 stale 标注都有一个 `rd-note-stale-badge`，数量等于 stale 标注条数。

---

### WI-3: DEG-S2 索引 stale 与状态枚举收敛

**范围**：书卡状态角标；搜索面板顶部提示条与重建按钮；`STATUS_META` 及其全部消费点。

**前置 WI**：
定义类 **WI-1**（tone 映射）；
实现类前置 **WI-1 ＋ WI-9**（源码根与 Vitest ＋ jsdom 宿主）。

**做什么**：给索引状态加第五态，并把两处**已经写错的** fallback 一起修掉。

`STATUS_META` 现在四态：`not_indexed` / `indexing` / `indexed` / `error`。指纹不匹配是第五态。

两个陷阱：

- **testid 不能拼字符串**。原型写的是 `data-testid={"status-" + props.status}`，违反设计规格 §4 规则 5（testid 的值必须是**字符串字面量**）。改成五个字面量的静态映射表。「加个 lint 例外」这条路**不成立**——lint 例外会让整条命名约束失效。
- **没有 fallback，且现有两处 fallback 都是错的**。`reader.jsx` 直接 `window.STATUS_META[indexStatus].label` 取值，遇到未知状态直接抛；`StatusPill` 的 `|| STATUS_META.not_indexed` **本身就是 bug**——把未知状态显示成「未索引」，用户会去点「开始索引」。正确做法是收敛成一个共用的 `statusMeta(s)`，未知状态返回中性的 `unknown`（灰点、「状态未知」），不冒充任何已知态。

**改动顺序**：先改 `STATUS_META` 与所有消费点，**再**让任何一端发出新状态值。消费方先行的枚举扩展，反过来会在两次部署之间炸掉。

搜索面板顶部的提示条用 **WI-1 的 `DegradeBanner`**，不是复用原型那个 `index-banner`——后者硬编码了「Semantic index」文案、住在搜索抽屉里，只能当视觉参考。

**涉及 testid**〔**定义类·验于 010**〕：`lib-status-not-indexed` / `lib-status-indexing` / `lib-status-indexed` / `lib-status-error` / `lib-status-stale` / `lib-status-unknown`（六个字面量）、`lib-degrade-s2`、`lib-degrade-s2-reindex`。

**五态枚举与「状态未知」文案**〔**定义类·验于 010**〕：第五态叫 `stale`、未知态叫 `unknown`、未知态文案是「状态未知」且不得等于「未索引」——这三条是 012 与本 WI 共享的定义，`010` 上定死。

**涉及降级状态**：DEG-S2。

**验收标准**：

1. 【实现类·前置 WI-9·验于 013】源码里不存在对 `data-testid` 属性的字符串拼接或模板插值（命名 lint 通过，且无 lint 例外条目）。
2. 【实现类·前置 WI-9·验于 013】六个状态值分别渲染出六个互不相同的 testid。
3. 【实现类·前置 WI-9·验于 013】传入一个不在枚举内的状态值：不抛异常，渲染出 `lib-status-unknown`，其可见文本为「状态未知」，且**不等于**「未索引」的文案。
4. 【实现类·前置 WI-9·验于 013】未知状态下不渲染「开始索引」操作按钮。
5. 【实现类·前置 WI-9·验于 013】`statusMeta` 只有一处定义，`reader` 与 `library` 两侧都从它取值（源码内该符号的定义处计数等于 1）。
6. 【实现类·前置 WI-9·验于 013】指纹不匹配时搜索面板顶部出现 `lib-degrade-s2`，且它的根元素带 WI-1 的边框（`border-color` 非 `transparent`）。
7. 【实现类·前置 WI-9·验于 013】点 `lib-degrade-s2-reindex` 触发重建请求一次；重复快点两次只发出一次请求。

---

### WI-4: DEG-S3 pickle 回退全局告警

**范围**：全局 chrome（书库与阅读器都要显示）；未迁移书目清单的展开与折叠。

**前置 WI**：
定义类 **WI-1**（danger 档 tone 映射）；
实现类前置 **WI-1 ＋ WI-9**（源码根与 Vitest ＋ jsdom 宿主）。

**做什么**：`READER3_ALLOW_PICKLE=1` 启动时，两个页面都显示 danger 档告警条，点击展开未迁移书目清单。

这是五条里**唯一的全局降级**。原型没有共享的顶部 chrome——要么建一个，要么接受两个挂载点。选哪个都行，但**必须两页都出现**，不能只做书库。

清单要能折叠，且有条数上限——未迁移的书可能有几十本，全展开会把页面顶掉。

**涉及 testid**〔**定义类·验于 010**〕：`lib-degrade-s3` / `rd-degrade-s3`、`lib-degrade-s3-toggle`、`lib-degrade-s3-list`、`lib-degrade-s3-more`（超过上限时的「还有 N 本」）。

**触发条件与条数上限**〔**定义类·验于 010**〕：触发条件是 `READER3_ALLOW_PICKLE=1`、tone 是 danger、清单默认折叠、超过上限时文案是「还有 N 本」——四条都是 012 朴素形态要照抄的定义，`010` 上定死。

**涉及降级状态**：DEG-S3。

**验收标准**：

1. 【实现类·前置 WI-9·验于 013】`READER3_ALLOW_PICKLE=1` 时，书库页与阅读器页**都**能查到对应的 s3 testid 元素且可见。（阅读器那半边随 WI-16 在 `014` 上复验。）
2. 【实现类·前置 WI-9·验于 013】未设该环境变量时两页都查不到（元素数为 0）。
3. 【实现类·前置 WI-9·验于 013】该横幅的 `tone` 解析为 danger（前景色计算值等于 `--r3-error` 的解析值）。
4. 【实现类·前置 WI-9·验于 013】默认折叠：`lib-degrade-s3-list` 初始不可见；点 `lib-degrade-s3-toggle` 后可见，再点恢复不可见。
5. 【实现类·前置 WI-9·验于 013】未迁移书目超过上限时渲染 `lib-degrade-s3-more`，其文本包含剩余条数；不超过时该元素不存在。
6. 【实现类·前置 WI-9·验于 013】展开后列表里每一项的文本等于对应书的书名（与 `/api/library` 返回值逐条比对）。
7. 【实现类·前置 WI-9·验于 013】**实现与文案各只有一份**：`{前端源码根}` 下，S3 横幅组件的**定义处**计数恰好为 **1**，其横幅文案字符串字面量的出现处计数同样恰好为 **1**；书库页与阅读器页两个挂载点**都从那一处 import**，两页各自的入口模块里该组件与该文案的本地定义处计数均为 **0**。共享模块的目录边界由 **WI-11** 给出（见 WI-11 的「范围」栏），本条不另指定目录名。
   > **为什么这条非有不可**：DEG-S3 是五条降级里**唯一的全局降级**，两页都要出现（见本 WI「做什么」）。上面第 1 条只要求「两页都能查到」——两份各自实现的横幅同样能让它转绿，然后文案在一次改动里只改一半，两页说法就此分岔。这条把「一份」变成可数的断言，堵住那条路。**落在 `013` 而不是 `014`**：按 §4.0 的规则，`014` 只收「断言目标只存在于阅读器页」的条目，而本条的断言目标是共享模块的源码定义处，两页共用；DEG-S3 的重做形态本身也归 WI-13（见 WI-13「范围」）。阅读器那半边的挂载由 WI-16 复验，与本 WI 第 1 条同一口径。

---

### WI-5: DEG-S4 存储格式与迁移进度

**范围**：书卡上的 `storage_format` 角标；迁移进行中的进度显示；失败项逐条重试。

**前置 WI**：
定义类 **WI-1、WI-3**（tone 映射与状态枚举）；
实现类前置 **WI-1、WI-3 ＋ WI-9**（源码根与 Vitest ＋ jsdom 宿主）。

**做什么**：给每张书卡加存储格式角标，并在 `--migrate` / `--migrate-all` 期间显示进度与失败项。

**关键区分**：`storage_format` 角标和索引状态 `StatusPill` 是**两个独立维度**。一本书完全可以「已索引 ＋ 旧格式」。两者不能合并成一个角标，也不能让其中一个覆盖另一个。

失败项**每条自己的 testid ＋ 自己的重试按钮**——批量失败里只能整批重试等于逼用户重跑已成功的部分。

**涉及 testid**〔**定义类·验于 010**〕：`lib-storage-format-badge`、`lib-degrade-s4`、`lib-degrade-s4-progress`、`lib-migrate-failed-item`、`lib-migrate-retry`。

**两维度独立**〔**定义类·验于 010**〕：`storage_format` 与索引状态是两个正交维度，不合并、不互相覆盖；失败项逐条重试而非整批重试。两条都是 012 朴素形态要遵守的定义。

**涉及降级状态**：DEG-S4。

**验收标准**：

1. 【实现类·前置 WI-9·验于 013】一本「已索引 ＋ 旧格式」的书，其书卡上 `lib-status-indexed` 与 `lib-storage-format-badge` **同时可见**。
2. 【实现类·前置 WI-9·验于 013】存储格式为新格式时 `lib-storage-format-badge` 不渲染（元素数为 0），或渲染出与旧格式不同的文本——两者取其一，实现选定后测试固定断言该行为。
3. 【实现类·前置 WI-9·验于 013】迁移进行中 `lib-degrade-s4-progress` 的文本随进度变化至少更新一次（两次采样值不同）。
4. 【实现类·前置 WI-9·验于 013】三项失败时页面上有 3 个 `lib-migrate-failed-item`，每个内部各有 1 个 `lib-migrate-retry`。
5. 【实现类·前置 WI-9·验于 013】点其中一个 `lib-migrate-retry` 只对该项发出重试请求（请求体里的书 id 等于该项对应的书 id），其余两项不发请求。
6. 【实现类·前置 WI-9·验于 013】重试成功后该项从失败列表移除，剩余 2 个 `lib-migrate-failed-item`。

---

### WI-6: DEG-S5 写冲突对话框

**范围**：新增 `ConflictDialog`；`Modal` 的 `data-testid` 改为必填 prop。

**前置 WI**：
定义类 **WI-1**（tone 映射与二选一文案）；
实现类前置 **WI-1 ＋ WI-9**（源码根与 Vitest ＋ jsdom 宿主），断言目标在阅读器页，随 WI-16 落 `014`。

**做什么**：notes 乐观并发失败时弹出「保留我的 / 采用远端」二选一，**不得静默丢写**。这是五条里唯一会真正丢用户数据的降级。

**为什么不能复用 `Modal`**：原型的 `Modal` 有三条互不相关的关闭路径——硬编码的 `×` 按钮（testid `modal-close`）、`.overlay` 上的 `onMouseDown`、`useFocusTrap(ref, true, onClose)` 里的 Esc。它还硬编码了 `role="dialog"` 和 `data-testid="modal"`。冲突对话框需要的是**零关闭路径**，改造 `Modal` 会同时破坏它现有的全部用法。

裁定：**新建 `ConflictDialog`**，`role="alertdialog"`，两个按钮是**仅有的**出口。同时把 `Modal` 的 `data-testid` 从硬编码改成**必填 prop、无默认值**——硬编码的 `modal` 会让多个弹层撞同一个 testid。

三个落地细节：

- **用原生 `<dialog>` ＋ `showModal()`，不用 `div[role=dialog]`**（`Modal` 选型裁决，2026-08-20，ET-17 已闭）。

  > **原来选 `div` 的理由不成立。** 当时写的是「原生 `<dialog>` 的 Esc 发生在浏览器层，要靠 `cancel` 事件 ＋ `preventDefault()` 才拦得住」——这句话本身是对的，但它推不出「所以做不到」：`<dialog>` 的 `cancel` 事件**是可取消的**，`e.preventDefault()` 就禁掉了 Esc，本 WI 验收 3 因此在 `<dialog>` 上成立。至于验收 4，**遮罩点击本来就不会关闭原生 `<dialog>`**——原型那条关闭路径是 `.overlay` 上手写的 `onMouseDown`，是额外加的行为，不是浏览器默认行为。两条要求在 `<dialog>` 上都能满足，而且**比 `div` 少写代码**：`div` 方案要手写遮罩、手写 Esc 拦截、手写焦点陷阱、手写兄弟节点 `inert`，`<dialog>` 一条都不用写。
  >
  > **两处追加的好处**：① `showModal()` 把元素提升进 **top layer**，脱离任何祖先包含块——正好解掉 K3 的 `position: fixed` 隐患，不必再证明挂载点（见 WI-16 的 K3 硬约束，`<dialog>` ＋ `showModal()` 本来就是那里列的两种合规挂载之一）；② 焦点陷阱与兄弟节点 `inert` 由浏览器提供，验收 5 不再需要手写焦点陷阱。
  >
  > 规格侧（`spec-frontend-design.md` §5 的组件表与 §10）由同一次裁决回写，本 WI 与 WI-12 用**同一个** `Modal` 组件，不是两套。
- **不要改 focus trap 这个 hook**——`ConflictDialog` 走 `showModal()`，焦点陷阱由浏览器提供，本 WI **根本不用**这个 hook；它仍服务于其余用它的组件，改它会波及那些组件。（此前这里写的「给它传 `undefined` 当 `onClose` 把 Esc 吞掉」随选型裁决作废：Esc 现在由 `cancel` 事件的 `preventDefault()` 拦。）
- **不许有死路**。远端数据取不到时，降级成「保留我的」单选项，**不是**把两个按钮都禁用——两个都禁用等于对话框既关不掉又点不动。

**涉及 testid**〔**定义类·验于 010**〕：`rd-conflict-dialog`、`rd-conflict-keep-mine`、`rd-conflict-take-remote`；`Modal` 各调用点各自的 testid。

**零关闭路径与二选一文案**〔**定义类·验于 010**〕：出口恰好两个（「保留我的」/「采用远端」）、无关闭按钮、不可 Esc、不可点遮罩关闭、远端不可达时降级成单选项而非双禁用。五条都是定义，不依赖组件存在。

**涉及降级状态**：DEG-S5。

**验收标准**：

1. 【实现类·前置 WI-9·验于 014】`ConflictDialog` 根元素 `role` 属性等于 `alertdialog`。
2. 【实现类·前置 WI-9·验于 014】对话框内查询关闭按钮 testid 返回 0 个元素。
3. 【实现类·前置 WI-9·验于 014】按 Esc 后对话框仍在 DOM 中且可见。**由 `cancel` 事件的 `preventDefault()` 保证**——断言的是行为，不是实现，选型换成 `<dialog>` 后这条断言一字不改。
4. 【实现类·前置 WI-9·验于 014】点击遮罩区域后对话框仍在 DOM 中且可见。**由原生 `<dialog>` 的默认行为保证**——`::backdrop` 上没有任何关闭逻辑，本条在 `<dialog>` 上是「不写代码即成立」。
5. 【实现类·前置 WI-9·验于 014】焦点在对话框打开后落到对话框内部，Tab 循环不会离开对话框（连按 N＋1 次 Tab 后 `document.activeElement` 仍在对话框子树内，`N` 取对话框内可聚焦元素个数，见 §5.0 占位符表）。**由 `showModal()` 的原生焦点陷阱 ＋ 兄弟节点 `inert` 保证**，不再手写。
6. 【实现类·前置 WI-9·验于 014】点「保留我的」发出一次带本地版本的写请求，随后对话框消失；点「采用远端」发出一次拉取并覆盖本地，随后对话框消失。
7. 【实现类·前置 WI-9·验于 014】远端不可达时只渲染 `rd-conflict-keep-mine`，且它的 `disabled` 属性为假。
8. 【实现类·前置 WI-9·验于 014】`Modal` 不传 `data-testid` 时构建期或运行期报错（类型必填 ＋ 运行时断言），源码里不存在 `data-testid="modal"` 这个默认值。
9. 【实现类·前置 WI-9·验于 014】冲突场景下用户的本地改动在任一分支后都不丢：断言写请求的 body 或最终 `GET /api/notes` 结果里包含本地文本。
10. 【实现类·前置 WI-9·验于 014】**证明走的是 `showModal()` 而不是手写 div**：`rd-conflict-dialog` 元素的 `tagName` 等于 `DIALOG`，且它的 `open` 属性为真。
11. 【实现类·前置 WI-9·验于 014】**证明进了 top layer**：给对话框的任一祖先加 `transform: translateZ(0)` 后，`rd-conflict-dialog` 的 `getBoundingClientRect()` 仍相对**视口**居中（左右边距之差 ≤N px，`N` ＝ 2，见 §5.0 占位符表）。这是 top layer 的行为；`div` 方案在这一条上会失败，因为祖先 `transform` 会给 `position: fixed` 造出包含块。

---

### WI-7: 契约 2 收口——高亮色改 RGB 三元组

**范围**：**生产 CSS** 里高亮与笔记 chip 的九个底色使用点（清单见下方角色表：四处改写落在 `src/reader3_app/web/static/css/annotations.css`，五处新写落在笔记面板样式；两者都随 WI-9 迁进 `{前端源码根}`）；外加 `models/annotations.py` 的 `MarkerColor` 与 token 名的一一对应校验；**夜纸**（reading 轴 `night`，以及 `auto`@dark chrome）下的高亮呈现方式。

> ⚠️ **`designs/reader-pro-next/` 不在本 WI 的范围内，本 WI 一个字都不改它。** 按 §1.1，原型是**被照抄的可执行规格**，不是交付物。本节凡是提到原型的地方，作用只有一个：**读取** 35 / 45 / 18 三个 alpha 与九个角色的清单。此前本节有多处把三元组改造写成「改原型」或「改完之后原型里 X 为 0」，那是把参考来源当成了交付目标，已按 §1.1 全部改指生产代码。
>
> `--r3-hl-*` 属 **reading 轴**，不属 chrome 轴——高亮是画在纸上、在 iframe 里的（§11-R7 规则 3）。下文的「夜间」一律指夜纸，不指界面暗色。
>
> **四个颜色名不由本 WI 定，也不许本 WI 改**：`src/reader3_app/models/annotations.py` 的 `MarkerColor`（`yellow` / `green` / `pink` / `blue`）是唯一权威，`notes.json` 里已存标注的 `color` 字段就是这四个字面量。token 名 `--r3-hl-{color}-rgb` 必须与它逐一对应；借本 WI 增、删、改名会让已存标注失配。

**前置 WI**：
裁定部分无（RGB 三元组方案与 alpha 取值可先定，可与 WI-1 并行；WI-10 消费它的产物，`--p-hl-*-rgb` / `--r3-hl-*-rgb` 的声明由 WI-10 按 spec §3.2 / §3.3 落地）；
落地部分前置 **WI-9**（源码根）——九处使用点的改写发生在 `annotations.css` 及笔记面板样式迁进 `{前端源码根}` 之后。

**做什么**：这条契约**是 alpha 问题，不是颜色问题**。

**「九处」是九个角色，不是九个字符串。** 角色清单与 alpha 取值从原型**读出来**（`designs/reader-pro-next/index.html` 的内联 `<style>`，选择器 `.note-chip.is-*` ×4 用 35%、`.anno.is-marker.is-*` ×4 用 45%、`.anno.is-note` ×1 用 18%），全是 `color-mix(in srgb, X N%, transparent)`——在 sRGB 里这就是纯 alpha。所以「chip 档该定什么显式颜色值」是个**假问题**。九个角色是：

| # | 角色 | alpha | 生产端今天的形态（实测 `static/css/annotations.css`） |
|---|---|---|---|
| 1–4 | 笔记 chip × 四色 | .35 | **不存在**——生产端全仓库 `chip` 0 命中，这四处是新写 |
| 5–8 | marker 高亮 × 四色 | .45 | `mark.annotation.annotation--marker.annotation--{color}`，写死 `rgba(…, 0.75)` 字面量，**既无 token 也不是 45%** |
| 9 | 笔记标记底色 | .18 | `mark.annotation.annotation--note` 只有 `cursor: pointer`，**根本没有底色** |

所以本 WI 在生产端是「**五处新写 ＋ 四处改写**」，不是「把九处 `color-mix` 换掉」——生产 CSS 里今天一处 `color-mix` 都没有。选择器名以**迁移后生产组件的实际类名**为准（marker 与 note 两档沿用 `annotations.css` 现有类名，chip 档随笔记面板一并新写）；原型那三组选择器只是角色的**代号**，不要照抄进生产 CSS。

> ⚠️ **不要去搜 `.anno-chip`**：这个类名在原型与生产端**均 0 命中**，是此前记错的名字。原型里 chip 档的真名是 `.note-chip`，marker 档的真名是 `.anno.is-marker`。35 / 45 / 18 三个百分比是实测值，正确，不动。

裁定：**存 RGB 三元组，alpha 留在使用点**。

**token 本身的定义在 `spec-frontend-design.md` §3.2（`--p-hl-*-rgb` 八个）与 §3.3（`--r3-hl-*-rgb` 四个 × 四块），那是唯一定义处；本 WI 只管使用点。** 此前这里贴过一份 `--p-hl-yellow-rgb: 251 191 36;` 的 CSS，而规格里当时一个 `-rgb` 都没有——两边一旦都写值就会各自漂移，且 0.8 的悬空 lint 只扫规格，扫不到这里。使用点的形态是：

```css
/* token 定义见 spec §3.2 / §3.3，由 WI-10 落地；
   下面两行是本 WI 要在生产 CSS 里产出的东西，类名以迁移后的生产组件为准 */
.note-chip.is-yellow                              { background: rgb(var(--r3-hl-yellow-rgb) / .35); }
mark.annotation.annotation--marker.annotation--yellow { background: rgb(var(--r3-hl-yellow-rgb) / .45); }
```

落选方案与理由：`color-mix()` 就是要被删掉的那个东西；`rgb(from var(--x) r g b / .35)` 是相对颜色语法，支持度比 `color-mix` 还差；8 位十六进制要手调 16 个值。三元组 ＋ 斜杠 alpha 从 Safari 12.1 / Chrome 65 起可用，零 fallback。

**夜间必须保留 alpha**。45% 合成 vs 100% 实色，正文对比度实测：黄 6.63 → **3.02** ✗、绿 7.45 → **3.94** ✗、粉 8.42 → 5.06、蓝 8.03 → 4.74。

更硬的结论：paper-night 底 L=0.0075、正文 `#c2ccdb` L=0.5977 —— 「块对页面 ≥3:1」要求 L≥0.1224，「正文对块 ≥4.5:1」要求 L≤0.0939，**解集为空**。所以夜间高亮**必须有非背景提示**（下划线 / 左侧竖条 / 波浪线）。浅色不受影响（45% 黄压白仍有 9.95）。

另有 D-5 遗留：**角色 9**（笔记标记底色）在原型里用的是 18% `--blue-500`，而 D-5 之后 `--blue-500` 是品牌色，照抄进生产 CSS 会和选区、focus ring 撞色。生产端取 `--r3-hl-*-rgb` 里的非品牌色，alpha 仍是 .18。

**涉及 testid**：无新增（本项改的是 token 与样式）。

**涉及降级状态**：无。

**验收标准**：

1. 【实现类·前置 WI-9·验于 013】**`{前端源码根}` 下的全部 `.css` 里，九个角色的底色声明中不含任何字面颜色值**：`color-mix(`、`#rrggbb` / `#rgb`、以及 `rgb(` / `rgba(` 后直接跟数字的写法，三类命中数合计为 0；九处只能是 `rgb(var(--r3-hl-*-rgb) / <alpha>)`。
   > ⚠️ **判据必须落在生产代码上，不能落在 `designs/`。** 此前这条写的是「`{前端源码根}` 下的 `.css` 里 `color-mix(` 出现次数为 0」，附注还解释它得等「原型样式抽取进源码根」才不真空——两处都把原型当成了要被改造的那份代码。实测两点推翻它：① 生产端 `src/` 下 `color-mix(` **今天就已经是 0**，九个角色里五个在生产端根本不存在、四个写的是 `rgba(255, 229, 143, 0.75)` 这类字面量，所以旧判据一行代码不动也能绿；② 九处 `color-mix` 全在 `designs/reader-pro-next/index.html` 的内联 `<style>` 里，而原型按 §1.1 **不许改也不用改**，「原型里 `color-mix` 为 0」永远不该是本 WI 的完成判据。新写法直接查生产 CSS 里有没有字面色，与角色是否存在无关，因此不再需要「和验收 2 一起判」这个附加条件。
2. 【实现类·前置 WI-9·验于 013】上表九个角色在 `{前端源码根}` 的生产 CSS 里**全部存在**（含五个新写的），且底色全部为 `rgb(var(--r3-hl-*-rgb) / <alpha>)`，alpha 分别为 .35（chip 四色）、.45（marker 四色）、.18（笔记标记 1 处，且所用 token 不是品牌蓝）。**判的是生产文件里的九条声明，不是 `designs/` 里的九条。**
3. 【实现类·前置 WI-9·验于 013】token 悬空 lint（0.8）通过，`--r3-hl-*-rgb` 全部有定义；且这四个 token 的颜色名集合与 `src/reader3_app/models/annotations.py` 的 `MarkerColor` **逐一相等**（既不多也不少，字面量比对）。
4. 【实现类·前置 WI-9·验于 014】**亮纸**（`paper` / `sepia` / `green` ＋ `auto`@light）下 marker 四色合成后与该纸墨色的对比度均 ≥4.5:1（用计算值断言，不靠肉眼）。
5. 【实现类·前置 WI-9·验于 014】**夜纸**（`night` ＋ `auto`@dark）下四色 marker 元素**除背景外**还带至少一个非背景视觉提示：断言其 `text-decoration-line` 非 `none`，或 `border-left-width` 大于 0。
6. 【实现类·前置 WI-9·验于 014】夜纸下 marker 的背景色 alpha 通道不等于 1。
7. 【实现类·前置 WI-9·验于 014】**角色 9**（生产端的笔记标记，今天是 `mark.annotation.annotation--note`）的解析背景色不等于 `--r3-accent` 的解析色。

> **定义类的那一半**〔**定义类·验于 010**〕：三元组方案（存 `--*-rgb`、alpha 留使用点）、九个角色的 alpha 取值 35/45/18、以及「夜纸必须有非背景提示」这条硬结论（paper-night 下 L≥0.1224 与 L≤0.0939 解集为空的推论），都是**裁定**，读本节就能核对，不依赖源码根存在。**角色清单从原型读，落点在生产 CSS**——这一条本身也是裁定，见本节开头的范围说明。

---

### WI-8: Skeleton 加载骨架

**范围**：新增 `Skeleton` 组件；书库卡片与统计数字的加载态。

**前置 WI**：
定义类无；
实现类前置 **WI-9**（源码根与 Vitest ＋ jsdom 宿主）。

**做什么**：原型 README 明说加载骨架从来没做过，设计规格 §5 也把 `Skeleton` 标为不存在。建出来，用在书库卡片与统计数字上。

- 必须尊重 `prefers-reduced-motion`——开了就是静态的，不能有动画。
- **不给 testid**。它是过渡态，断言它的存在会引入时序 flake。断言它**之后**的东西：数据到了之后卡片出现。

**涉及 testid**：无（刻意不给）。

**涉及降级状态**：无。

**验收标准**：

1. 【实现类·前置 WI-9·验于 013】组件源码内不含 `data-testid` 属性。
2. 【实现类·前置 WI-9·验于 013】`prefers-reduced-motion: reduce` 下骨架静止：**构建产物 CSS 中存在** `@media (prefers-reduced-motion: reduce)` 块，其中 `.r3-skeleton` 的 `animation` 为 `none`，且 `background` 换成纯色 `var(--r3-surface-sunken)`（规格 §5.2：只停动画不换底会留下一块左深右浅的静止渐变，比纯色更像渲染故障）。**这是源码 / 产物断言，不是运行时断言**——理由见 §5.0「骨架为什么连样式都不在 E2E 里断」。
3. 【实现类·前置 WI-9·验于 013】默认（未开 reduced-motion）规则里 `.r3-skeleton` 的 `animation-name` 不为 `none`。与第 2 条成对，判在同一份产物 CSS 上——两条都不进 E2E。
4. 【实现类·前置 WI-9·验于 013】书库首屏加载态**不以骨架为断言目标**：断 `lib-book-grid` 的 `aria-busy` 在数据返回前为 `true`、返回后为 `false`，且返回后书卡数量等于接口条数（矩阵对应行是 §5 的 FD-20）。**此前本条写的是「骨架占位数量大于 0」——那是在 E2E 里抢加载窗口，与本 WI 第 5 条自相矛盾**，已按规格 §5.2 的第 2 条改掉。
5. 【定义类·验于 010】测试矩阵中不存在任何以骨架为断言目标的用例：**第 5 节内 `骨架` 与 `skeleton` 出现在「断言目标」列或断言描述中的命中数为 0**（grep 可判；本 WI 是 `010` 上唯一带 `验于 010` 的验收，做成人工核对就等于 `010` 一条都判不了）。允许它们出现在「不做什么」这类否定语境里，判定时按整行语义排除，排除的行要在 PR 描述里列出。

---

### WI-9: 4A.0 工具链

**范围**：Vite 多页配置、TypeScript 配置、`dependency-cruiser` 配置、三条 lint 的接入、`static/dist/` 的提交策略、**CSS 与 HTML 的分离规则**、**旧死样式文件的清理**、**JS 单测宿主（Vitest ＋ jsdom）**、**REG-1 回归基线**。

**前置 WI**：无（4A 的第一项）。

**做什么**：把构建链搭起来，并把 0.5 / 0.8 的三条 lint 接进同一条命令。

- Vite 多页：书库 / 阅读器 / 设置三个入口。
- 产物落 `src/reader3_app/web/static/dist/`，**提交进 git**（决策：不在 CI 里现构建）。
- `dependency-cruiser` 先接进来，规则在 WI-14 填。
- Node 与 Vite 版本固定，带 lockfile。
- **`package.json` 里同时装上 Vitest ＋ jsdom**（裁决见 §5.0 的执行器表）。全仓库当前没有 `package.json`，本 WI 是它的诞生处；测试宿主与构建宿主是同一个文件里的事，不另开 WI。Vitest 复用 `vite.config.ts` 的 `resolve` / `alias`，不许维护第二套路径解析。
- **`pytest-xdist` 加进 `pyproject.toml` 的 `[dependency-groups].dev`**——§5.0 的 `pytest -n 4` 依赖它，而它今天不在依赖里（实测 `pyproject.toml` / `uv.lock` 命中均为 0）。这条属 Python 侧，但与 §5.0 的并行度裁决是同一件事，放这里一并落，避免两半分家。
- **新增第四条 lint：token 硬编码 lint**（定义见 §9.3）。它与 0.8 的 token 悬空 lint 是**一对**：悬空管「引用的 token 不存在」，硬编码管「该用 token 的地方写了字面量」。今天只有前者，所以没有任何东西阻止硬编码值长出来。
- **REG-1 回归基线在本 WI 建立并转绿**（组成见 §5.10）。这是后续所有模板改动的前置——快照必须拍在改动之前。

#### 9.1 CSS 与 HTML 必须分离（本计划的硬规则）

**模板里不许有内联 `<style>` 块。样式只许存在于独立的 `.css` 文件里，由页面入口 `import` 进来，经 Vite 产出到 `dist/`。**

这条是本次重构的前提，不是风格偏好。现状（2026-08-17 实测）是反面教材：

| 模板 | 总行数 | 其中内联 `<style>` |
|---|---:|---:|
| `reader.html` | 1997 | **1403** |
| `library.html` | 1439 | **1075** |
| `library_classic.html` | 78 | 10 |
| `settings.html` | 76 | 0 |

两个主模板 **七成以上的体积是样式**。后果已经能测出来：样式无法被 diff 审阅（改一个按钮的 PR 会显示成模板变更）、无法被 stylelint 扫、无法复用（同一个 `.rt-btn` 在模板内联块和 `css/toolbar.css` 里各有一份），也无法缓存（模板不带哈希，每次请求都重传那 1403 行）。**上一轮 UI 重写（`specs/_archive/005`）把样式内联进模板，正是下面那六个孤儿文件产生的直接原因**——旧文件没人删，因为没人发现它们已经不被加载了。

落地形态：

```
{前端源码根}/
├── styles/
│   ├── tokens.css          ← WI-10 的 Tier 1 --p-* / Tier 2 --r3-*（含生成的暗色块）
│   ├── base.css            ← reset、排版基线
│   └── components/*.css    ← 按组件切，组件只许引 Tier 2
├── library/index.ts        ← import '../styles/…' + 本页 css
├── reader/index.ts
└── settings/index.ts
```

模板只留三样东西：结构标记、`{{ }}` 数据插值、`<head>` 里那**一段 FOUC inline `<script>`**。

> ⚠️ **FOUC 脚本是唯一豁免，而且它是 `<script>` 不是 `<style>`。** WI-10 那段同步脚本必须内联（外链会在解析前造成闪烁），本规则禁的是内联**样式**，两者不要混。豁免范围就这一段，不得扩大。

#### 9.2 顺带删掉六个死样式文件 ＋ 一个死 JS

上一轮内联留下的残骸。实测确认**零调用**（模板 0 处、`server.py` 0 处、其他 JS 0 处；无 Jinja 继承链；`epub-renderer.js:176` 的 `createElement("style")` 内容来自 `buildContentCss()` 这个 JS 函数，不读文件）：

| 文件 | 行数 | 顶层 class 被活样式源覆盖率 |
|---|---:|---|
| `static/library.css` | 988 | 86/96（89%） |
| `static/ai.css` | 257 | 16/18（88%） |
| `static/css/notes-panel.css` | 119 | 13/13（**100%**） |
| `static/css/reader.css` | 98 | 4/4（**100%**） |
| `static/css/toc-panel.css` | 82 | 4/4（**100%**） |
| `static/css/toolbar.css` | 40 | 1/1（**100%**） |
| `static/js/pagination.js` | 336 | 死 JS，`CLAUDE.md:161` 自己写着 not loaded |
| **合计** | **1920** | |

仓库里剩下的引用全部在 `CLAUDE.md` 与 `specs/_archive/`（后者项目 CLAUDE.md 明文标为 frozen、never implement from），不构成调用。

> **删除前须单独确认**（同 WI-13 对 `library_classic.html` 的协议）：`library.css` 的 10 个、`ai.css` 的 2 个 class 未在活样式源里找到同名定义，删之前逐个眼过——可能是彻底废弃的选择器，也可能是重合度扫描漏掉的写法（嵌套、`:is()`）。
>
> **`search.css`（328 行）不在本 WI 删**——它当前**唯一**的加载方是 `library_classic.html`，随 WI-13 一起走，见 WI-13 验收。

**同时修文档**：`CLAUDE.md:158/161/166` 把 `library.css` / `pagination.js` / `css/reader.css` 记成活文件（`:161` 甚至自带 "not loaded by reader.html" 的自相矛盾注释）。这三行随删除一起改掉——正是这份过期文档让孤儿活了这么久。

##### 存活样式文件的去向（本节只处置死文件，活文件也得有主）

§9.2 处置六个死文件，WI-13 处置第七个（`search.css`）。`static/` 下**剩下的三个 `.css` 今天仍被模板加载**，它们不在任何删除清单里，去向必须单独写明，否则 §9.1 的「模板只剩结构」达成之后，仓库里会同时存在两套样式来源。

| 存活文件 | 今天谁加载 | 去向 | 由谁迁 |
|---|---|---|---|
| `static/dedao-theme.css` | `library.html:7`、`reader.html:7` | 拆解进 `{前端源码根}/styles/tokens.css` ＋ `base.css`；**不整体保留**——它是第三套命名（`--dedao-*`），与 §3 双层 token 冲突 | WI-10（token 层）＋ WI-13 / WI-16（各自页面残留） |
| `static/css/annotations.css` | `reader.html:8` | 迁进 `{前端源码根}/styles/components/annotations.css`，走 Tier 2 token；**内容不重写**（标注样式与 K1–K6 契约耦合，重写属行为变更） | WI-16 |
| `static/settings.css` | `settings.html:7` | 迁进 `{前端源码根}/settings/` 的入口样式，由 Vite 产出到 `dist/` | WI-12 |

> 三条都要走 §9.3 的 token 硬编码 lint——迁移不是搬运，`--dedao-*` 与裸值不能跟着走。

##### 能不能留着当 WI-10 的起点？——不能，实测六个全不合规

问过一次「这六个是否符合新 UI Spec 的风格定义」，逐条量过，答案是**零个符合**，而且它们比活样式源**更**远：

| 规格条款 | 要求 | 六个孤儿实测 |
|---|---|---|
| §3 双层 token | 组件只许引 Tier 2 `--r3-*` | **`var(--r3-` 命中 0 次**（六个文件合计） |
| §3 命名空间 | `--p-*` → `--r3-*` 两层 | 它们自带**第四套**命名：`--wr-*`（reader/toc/notes/toolbar）＋ 裸名 `--accent` `--bg` `--text` `--border` `--panel` `--muted` `--radius`（`library.css` 定义 13 个） |
| §11-R1 断点 | `1279` / `767` | `library.css` 用 `980`，其余五个**无任何断点**（不响应式） |
| §3.4 字阶 | 8 档 `11/12/13/14/16/18/22/28` | `library.css` 13 个 rem 字面量里只有 `0.75rem`(12px) 落在档上，其余 `0.78/0.82/0.86/0.88/0.92/0.95/1.05/1.2` 全部离档——正是 §11-R4 要消灭的那个病 |
| §11-R6 圆角 | `6/10/16` | 出现 `10`（合规）＋ `12` `14` `23` `999`，三个离档 |
| §3 暗色 | `:root` ＋ `[data-theme="dark"]` 双份 | `prefers-color-scheme` / `data-theme` / `data-reading-theme` 命中 **0** |
| 硬编码色 | 走 token | `library.css` 13 hex ＋ 52 rgba、`ai.css` 11 hex ＋ 23 rgba，全裸 |

两条追加发现值得单独记：

- **四个孤儿构成一个闭合死簇。** `toolbar.css` / `toc-panel.css` / `notes-panel.css` 引用 `--wr-bg` `--wr-card` `--wr-radius` `--wr-shadow` `--wr-border`，而 `--wr-*` 的**唯一**定义处是同样死掉的 `css/reader.css`。活样式源（`dedao-theme.css`、三个模板、`annotations.css`）里 `--wr-` 命中 0。也就是说**今天就算把 `toolbar.css` 挂回模板，它也是坏的**——变量无定义，全部回落到无效值。这条把「它们只是没被引用，本身还好」的假设直接证伪了。
- **`library.css` 在全局命名空间里定义裸名 token。** `--accent` / `--bg` / `--text` 这类名字没有前缀，谁在 `:root` 上再定义一次谁就赢。活样式源目前**没有**同名定义（实测四个文件均为 0），所以今天不冲突；但这正是规格要求 `--p-*` / `--r3-*` 双前缀的原因，把它当起点等于把这个雷带进新体系。

**结论：删，不留作参考。** WI-10 的 token 层是从规格 §3 新写的，不是从这六个文件演进来的；留着只会让人误以为有可复用的前作。真正值得带走的是 class **名字**（88–100% 与活样式源重合，说明命名是稳定的），而那份命名已经在活模板的内联块里，不在这六个文件里。

> ⚠️ **顺带暴露一条排期事实：整个仓库当前没有任何暗色模式实现。** 上表倒数第二行不只孤儿是 0——`dedao-theme.css` 与 `reader.html` / `library.html` 的内联块里，`prefers-color-scheme` 与 `data-theme` 的命中数**同样是 0**。WI-10 的暗色不是「把现有暗色搬过来」，是**从零建**，D6 的 Vite 插件生成的是全新声明。WI-10 排期按新建计，不按迁移计。

#### 9.3 token 硬编码 lint（本 WI 新增的第四条 lint）

0.8 的 token **悬空** lint 只管「`var(--x)` 引用的 `--x` 不存在」。它拦不住反方向的病：**该用 token 的地方直接写字面量**。实测现状（2026-08-20）说明这不是假想风险：

| 违规形态 | 现状计数 |
|---|---:|
| CSS 里的裸 hex | **100** |
| `rgba()` 字面量 | **173** |
| 不同的 `font-size` 字面量 | **29 种** |
| 不同的 `z-index` 字面量 | **19 种** |
| 不同的 transition 时长 | **7 种** |

29 种字号对 8 档字阶、19 种层级对一套 z-index token——这正是 §11-R4 要消灭的那个病，而 §9.2 已经证明它会**跨代复制**（六个孤儿里 13 个 rem 字面量只有 1 个落在档上）。

**lint 定义**：

- **名字**：token 硬编码 lint。与 token 悬空 lint 成对，接进本 WI 验收第 3 条那同一条命令。
- **扫描范围**：`{前端源码根}` 下所有 `.css` **与 `.ts`**，以及 `src/reader3_app/web/templates/*.html`。`.ts` 必须进扫描集：实测 `js/epub-renderer.js:95` 今天就硬编码着 `font-family: "Noto Serif SC", serif`、`:186` 往 iframe 注入 `<link>`（见 WI-16），这些样式字面量是从脚本里写出去的，只扫 `.css` 一行都抓不到。
- **违规项**，八类：
  1. 裸 hex（`#rgb` / `#rrggbb` / `#rrggbbaa`）；`rgb()` / `rgba()` 字面量。
  2. 裸 `z-index: <数字>`。
  3. 裸 `font-size: <数字>`。
  4. 裸 `transition-duration`，以及 `transition` 简写里的时长。
  5. **裸 `padding` / `margin` / `gap` 数值**——间距阶是 `--r3-space-*`（规格 §3.4）。
  6. **裸 `border-radius` 数值**——圆角只有 `6/10/16/full` 四档（规格 §3.4、§11-R6）。
  7. **裸 `height` / `min-height` / `width` / `min-width` 数值，以及裸 `line-height` 数值**——控件尺寸走 `--r3-control-h*`，布局宽走 `--r3-sidebar-w` / `--r3-right-w` / `--r3-rail-w` / `--r3-header-h`，行高走 `--r3-leading-*`（规格 §3.4）。
  8. 非 `0` / `1` 的裸 `opacity`（与下面豁免清单里那一项配套；此前豁免了它却没有把它列为违规，两行互相矛盾）。

> **第 5–7 类是本轮补的，不是原有清单。** 少了它们，这条 lint 的名字对不上它的作用域：§9.2 的实测把「离档圆角 `12` / `14` / `23` / `999`」当作删掉那六个死文件的**理由**之一（见上表 §11-R6 行），§3.4 更是用两整段强调「不许拿 `--r3-space-*` 表达控件高度」。如果新 lint 只管颜色与字号，那批文件删掉之后，`border-radius: 23px; padding: 13px; height: 41px` 会在 `{前端源码根}` 里原样长回来，而且是**合规地**长回来——§9.2 的论证就落空了。「100% token 化」这个目标，靠只管四类的 lint 到不了。
- **豁免清单（照抄，不扩大）**：`0`；`1px` 边框；`100%`；`50%`；纯 `0` 或 `1` 的 `opacity`；CSS reset 文件里的值；**Tier 1 Palette 定义文件本身**——`--p-*` 的定义处就是字面量该在的地方，那是唯一的字面量入口。
- **白名单机制与内联 `<style>` lint 一致：只许缩短，不许增长。** 落地时对存量文件为红，以白名单记录初值；每迁移一页就从白名单里划掉一项；最后一项划掉时**整条白名单删除**。

**白名单初值与划掉它的那条验收**（每一条都要有主，否则「只许缩短」缩不到 0）：

| 白名单初值条目 | 谁划掉 |
|---|---|
| `templates/library.html` 迁出的样式（1075 行） | WI-13 验收 9 |
| `templates/reader.html` 迁出的样式（1403 行） | WI-16 验收 15 |
| `templates/settings.html` 迁出的样式（2 处 `style="`） | **WI-12 验收 9**（本轮补） |
| `static/settings.css` → 设置页样式 | **WI-12 验收 9**（本轮补） |
| `static/dedao-theme.css` → `styles/tokens.css` ＋ `styles/base.css` | WI-10 交付 token 层，WI-13 / WI-16 各自迁走消费侧 |
| `static/css/annotations.css` → `styles/components/annotations.css` | WI-16 验收 15 同批 |
| `templates/library_classic.html` | **不划掉**——该文件由 WI-13 验收 4 整个删除，条目随文件消失（须先完成 `plan:853` 的单独确认） |

> 上表最后一行是唯一允许「条目消失但没通过 lint」的情形，因为文件本身没了。除它之外，**每一条都必须由某条验收标准显式划掉**；`static/js/epub-renderer.js` 里的两处内联样式赋值（`:95`、`:186`）随 §9.3 扫描范围含 `.ts` 一并管，归 WI-16。整条白名单的终点是 **WI-16 验收 15**。

> 豁免清单里没有「深色块」「第三方样式」这类开口。任何想加一条豁免的改动，等于把 29 种字号中的一部分永久合法化——要加就先证明它不能进 Tier 1。
>
> ⚠️ **同样不接受任何行内抑制注释**（`/* *-disable */`、`/* *-disable-next-line */`、以及所选工具的等价写法）。上一段管的是「豁免清单能不能变长」，这一段管的是「能不能绕过清单」——两件事，都要堵。理由与 §4 对 testid 命名 lint 的裁定完全一致：**「加个 lint 例外」这条路不成立，lint 例外会让整条约束失效**。工具链尚未选型（WI-9 定），所以这里禁的是**行为**不是某个具体语法：无论最终选哪个工具，它的行内抑制能力都必须在配置里关掉，并由 WI-9 验收 11 断言白名单中不含抑制条目。

**工具链裁决（2026-08-23，已问过 Codex 并综合）**：选 **stylelint ＋ `stylelint-declaration-strict-value` ＋ `postcss-html`，外面套一层自写的棘轮包装**，不自己用 Python 写 CSS 值解析。

- **为什么不自写**：0.8 那条 lint 能零依赖，是因为它的模式是 `--x:` 与 `var(--x)` 两条正则就能穷尽的。本条不是——它要判的是**复合值与简写**里的字面量（`border: 1px solid #eee`、`box-shadow`、`linear-gradient`、`transition`）。用正则做这件事等于手搓半个 PostCSS，且会长成一堆脆弱的特例。
- **为什么"多一份依赖"不是代价**：Node 工具链在本 WI 已是既定成本（`package.json` ＋ Vite ＋ Vitest ＋ jsdom，WI-14 还要 ESLint ＋ dependency-cruiser）。B 方案的零依赖优势在 ET-1 落地那一刻就归零。
- **`postcss-html` 是必需项不是可选项**：现状的大头样式在 Jinja 模板的 `<style>` 块里（`library.html` 1075 行、`reader.html` 1403 行）。不挂 `customSyntax` 就等于只扫了 `.css`，白名单的大头一行都抓不到。

**四个必须在实现时堵住的坑**（Codex 提出，全部采纳，其中第 2、4 条修正了初版设计）：

1. **`postcss-html` 看不见 JS 写出去的样式**——`el.style.x = "6px"`、`style.setProperty()`、`style.textContent`、注入的 CSS 字符串。这部分归 WI-14 的 ESLint AST 规则。⚠️ **规则的靶子是"受管属性"，不是"所有 `.style` 赋值"**：运行时几何（浮动工具条的 `top`/`left`、进度条的 `width` 百分比、`transform`）是计算值不是设计 token，禁掉它们等于逼人绕路；禁的是把 `color` / `font-size` / `padding` / `border-radius` / `z-index` / 时长这几类**写成字面量**。
2. **`declaration-strict-value` 把「任意 CSS 变量」都算合格，不区分命名空间。** 这是最要命的一条：不额外校验的话，`var(--dedao-orange)` 会**通过** lint——620 处遗留 `--dedao-*` 引用会全体显示为「已 token 化」，整条棘轮在迁移没开始时就是绿的。包装器必须自己判命名空间：**组件侧只允许 `var(--r3-*)`**；`var(--p-*)` 只在 Tier 1 里定义 `--r3-*` 时合法（这就是 §3.2 两层 token 的规矩），出现在组件里同样是违规。（该插件是否真的没有 allowlist 选项，实现时验一次；没有就在包装器里做。）
3. **简写展开不是完整 CSS 语义解析。** 开了 `expandShorthand` 之后 `background` / `transition` / `box-shadow` / 带函数或变量的复合值仍会误报漏报。**v1 只管明确的长属性**，简写按实测逐条纳入，每纳入一条先写一个「合法复合值」fixture 断言它不误报。上面第 4 类的 `transition` 简写、以及 `box-shadow`，都排在 v1 之后。
4. **棘轮比的是违规指纹集合，不是违规总数。** 只比总数会放过「删掉一处旧违规、在别处新增一处」——数字不变，债没还。基线是指纹集合，CI 断言 `实测 ⊆ 基线`；基线文件**只许删条目，不许加条目**。指纹取 `文件:选择器:属性`，**不含行号**——行号会被任何无关编辑冲掉，带行号的基线活不过一个 PR。多人协作时以目标分支的最新基线重跑再 rebase，避免两个 PR 互相覆盖基线。

**不与 0.8 的悬空 lint 合并。** 两条问的是相反的问题（「这里用没用合法 token」vs「被引用的 token 有没有定义」），而且 0.8 必须保持零依赖：它现在跑在 `.github/workflows/lint.yml` 的 `contracts` job 里，那个 job **不装任何依赖**。合并会把 Node 安装拖进最早的一条 CI。两条可以共享扫描清单，但保持两条独立的失败信息。

**跨计划**：`pyproject.toml` 的 `package-data` 要跟着改——vendored 文件从 `static/js/vendor/` 换成 Vite 产物，0.2 修好的非递归 glob 会再次失配。wheel 内容测试断言 `dist/` 进了 wheel，归 `008-test-safety-net`。这两条的实施在技术栈迁移那侧，本 WI 只负责不把它们漏掉。

**涉及 testid**：无。

**涉及降级状态**：无。

**验收标准**：

1. 干净克隆后一条命令完成构建，`static/dist/` 下三个入口的产物都存在。
2. 连续两次构建的产物字节一致（可重复构建）。
3. 选择器 lint、命名 lint、token 悬空 lint 三条能在一条命令里全部跑起来，任一违规使该命令非零退出。
4. `dependency-cruiser` 可执行且在零规则下通过。
5. `pyproject.toml` 的 `package-data` 覆盖 `static/dist/` 下的递归路径（构造一个深层子目录文件，断言它进了 wheel）。
6. **HTML／CSS 分离（§9.1）落成 lint，不靠自觉**：一条脚本扫 `src/reader3_app/web/templates/*.html`，断言 **`<style` 块与 `style="` 属性两者的出现次数合计为 0**；**内联 `<script>`（不带 `src` 的那种）**只允许出现在白名单里（`{"settings.html":0, "library.html":0, "reader.html":1}`，`reader.html` 那一处即 §9.1 豁免的 FOUC 脚本），其余一律失败。规则接进第 3 条那条命令，与三条 lint 同进退。
   - **带 `src` 的 `<script>` 不计入这条白名单。** §9.1 的目标布局是三个 Vite 入口，每个入口都要有一个带哈希的模块脚本；把它们算进计数等于禁掉入口本身——按此前那份 `{"settings.html":0, ...}` 的字面读法，设置页拿到自己的入口那一刻就永久变红。这条 lint 管的是**内联**，`src` 外链正是它想要的结果。
   - a. 该 lint 在**本 WI 落地时故意为红**（此刻 `reader.html` 1403 行、`library.html` 1075 行内联样式还在），以 xfail／allowlist 记录初值，随 WI-12 / WI-13 / WI-16 逐页转绿；**allowlist 只许缩短不许增长**，末页转绿后整条 allowlist 删除。
   - a1. **四个模板全部要进初值 allowlist，一个都不能漏。** 此前这条只点了 `reader.html` 与 `library.html` 两个，而扫描集是 `templates/*.html`（实测 4 个文件）——没登记的文件从 lint 落地那一刻起就是**无条件红**，且没有任何 WI 负责让它转绿。实测初值（2026-08-23，按 `<style` ＋ `style="` 合计）：`reader.html` 1403＋2、`library.html` 1075＋2、`settings.html` 0＋2、`library_classic.html` 10＋3。后两个的划掉方式分别是 WI-12 验收 5b（迁走两处属性）与 WI-13 验收 4（随文件删除）。
   - a2. **内联 `<script>` 那一半的初值同样按实测记。** 实测四个模板的内联 `<script>`（不带 `src`）：`reader.html` **3** 处（`:1702`、`:1747`、`:1834`）、`library.html` **0**、`settings.html` **0**、`library_classic.html` **0**。所以脚本侧的 allowlist 初值只有 `{"reader.html": 3}` 一条，由 WI-16 验收 14 收敛到 1（只剩 FOUC 那段）；另外两段的去向在那一条里一并交代。**注意目标态与初值方向相反**：`library.html` 今天是 0、目标也是 0（它的三个 `<script>` 全带 `src`），不要照旧稿写成 1。
   - b. 每个 Vite 入口都产出自己的 CSS 资产（`dist/` 下三个入口各有非空 `.css`），模板通过带哈希的 `<link>` 引用。
   - c. **`style="` 属性也算内联样式，必须一起统计。** 此前这条 lint 只数 `<style` 标签，抓不到属性形态；实测四个模板里还有 **9 处内联 `style="` 属性**（`settings.html` 2 ＋ `reader.html` 2 ＋ `library.html` 2 ＋ `library_classic.html` 3）。只数标签的话，`settings.html` 的白名单初值会被记成 0，而它实际有 2 处——那是把一条绿灯发给了违规文件。白名单机制照旧（只许缩短），初值按 `<style` ＋ `style="` 的合计记。
7. **六个死样式文件与 `pagination.js` 已删除**（§9.2）：七个路径在仓库中均不存在；**可执行代码与模板**中对这七个文件名的引用计数为 0。`CLAUDE.md` 的三行（`:158` / `:161` / `:166`）同步改掉。
   - **计数排除四类非调用位置**，否则这条验收按字面永远转不了绿：① `specs/_archive/`（frozen 历史记录）；② `docs/plans/`（**本计划 §9.2 的死文件表格本身就逐行列着这七个名字**——机械执行会要求删掉定义它自己的那张表）；③ `designs/**/spec/`（实测 `reader-pro-spec.md:312`、`:638` 两处提到 `pagination.js`，且 `:312` 恰恰是在说明「它当前未被 Reader 模板加载」，属说明性叙述）；④ `*.egg-info/`（实测 `SOURCES.txt:33`、`:38` 含 `ai.css` / `library.css`，是构建产物，随下次构建重生，删了也会回来）。
   - a. 删除前逐个眼过 `library.css` 的 10 个、`ai.css` 的 2 个未匹配 class（§9.2 的确认门槛）。**验收形式是机器可判的，不是 PR 描述**：把这 12 个 class 名落成一份清单文件随 PR 提交，断言每一个在**活样式源**（`dedao-theme.css`、`css/annotations.css`、`settings.css`、四个模板的内联块）里的命中数为 0。理由同 WI-14 验收 7 的那次改法——写进 PR 描述的是自陈，写了照样能合，第二次改动时也没人会重读。
   - b. **回归断言**：删除后 REG-1 的三页 smoke 全绿，且三页**计算样式快照零 diff**——证明这七个文件确实对渲染零贡献。这条是本次删除唯一的安全网，不得跳过。
8. **JS 单测宿主可用**：`package.json` 存在，一条命令跑 Vitest 并通过；故意写一条必失败的用例，确认它确实变红（不是空跑 0 passed）。`vitest` 与 `vite` 共用同一份 `resolve.alias`（改一处别名，两边同时生效）。
9. **`pytest-xdist` 在 dev group 中**，且 `uv run pytest -n 4 --collect-only -q` 收集到的 node ID 集合与 `-n 1` 相同（§5.0 的分发校验）。
10. **REG-1 四项全部建立且绿**（§5.10）。本条不绿则 WI-12 / WI-13 / WI-16 不得开工——它们的验收都以「与基线比对」为形式，基线不存在时那些验收是空的。
11. **token 硬编码 lint 存在且不是空跑**（§9.3）：它随第 3 条那条命令一起执行；**两个反例都要验**——
    - a. 在任一受管文件里故意写一行 `color: #ff0000;`，该命令**非零退出**；删掉后**恢复零退出**。
    - b. 再单独写一行 `border-radius: 23px;`（§9.2 实测存在的离档形态），同样**非零退出**；删掉后**恢复零退出**。**第二个反例是必需的**：只验颜色的话，§9.3 违规项第 5–7 类（间距 / 圆角 / 尺寸 / 行高）可以整条不实现，而这条验收照样通过——那正是本轮要堵的洞。
    - c. **第三个反例针对命名空间**（§9.3 坑 2）：故意写一行 `color: var(--dedao-orange);`，该命令**非零退出**。少了这一条，`declaration-strict-value` 会把 620 处遗留 `--dedao-*` 全判为合格，棘轮在迁移开工前就是绿的。
    - d. **棘轮是指纹集合不是计数**（§9.3 坑 4）：删掉基线里任一条违规、同时在另一个文件新增一条同类违规，该命令仍**非零退出**。
    - c. 白名单的初值以文件为单位记录，**且不含任何行内抑制条目**（§9.3 的行内抑制禁令）；有一条断言保证白名单条目数**只减不增**。该断言在本 WI 交付时接进第 3 条那条命令；CI 宿主由迁移侧 `008` 建，`008` 落地后同一条断言接进 CI，本 WI 不负责建 CI。
12. **0.8 的扫描范围已扩到 `{前端源码根}`**：`007` 的 token 悬空 lint 原扫描集是 `designs/reader-pro-next/`、`static/css/`、`templates/*.html` 与设计规格里的 CSS 块（见 `plan-tech-stack-migration.md:229`），**不含本 WI 新建的源码根**。本 WI 把它扩过去，并在迁移计划那一处同步登记（0.8 的定义归 007，扩范围这个动作归本 WI）。少了这一条，WI-1 验收 7、WI-7 验收 3、WI-10 验收里那些「0.8 通过」，都是在一个 lint 根本没扫的目录上宣布通过。

---

### WI-10: 4A.1 token 与主题层

**范围**：双层 token 定义文件；**两根主题轴**（chrome 明暗 ＋ 阅读纸色）的 CSS 与 FOUC inline script；`{前端源码根}/shared/theme-tokens.ts` 与生成暗色 CSS 的 Vite 插件。

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

**暗色声明只许有一个作者（D6，2026-08-17）。** 规格 §3.3 要求暗色语义 token 同时出现在两个选择器里——`@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { … } }` 与 `:root[data-theme="dark"] { … }`——两份声明体必须逐字节相同（前者管「跟随系统」，后者管「显式选深色」，缺一根轴就断）。手抄两份必然漂移。

做法：本 WI 建 `shared/theme-tokens.ts`，里面放**两张分开的表**：

```ts
export const CHROME_THEMES = { light: {...}, dark: {...} };   // 本 WI 用
export const READING_THEMES = { auto:…, paper:…, sepia:…, green:…, night:… };  // WI-18 用
```

**两张表不许合并**——合并就是把两根轴又揉成一根。一个约 30 行的 Vite 构建插件把 `CHROME_THEMES.dark` 渲染成一次 `darkDeclarations` 字符串，再把**同一个字符串**插进上面两个选择器。

> 这不是新造机器：`READING_THEMES` 这个共享常量 WI-18 验收 17 本来就要求存在（`plan:1136`），本 WI 只是把 chrome 那半边一起放进去，边际成本是那个插件。
>
> **不采用**的两条：手抄 ＋ 运行时相等性测试——保留了两个作者，只能在漂移**发生之后**报警；通用 PostCSS mixin/插件——为一条不变式引入依赖和自定义语法面。

**本 WI 还交付 FOUC inline script**（三个页面模板 `<head>` 共用一段同步脚本）：读两个 localStorage key，往 `<html>` 上 stamp 两个属性。三条易错点：

- 属性 stamp 在 `<html>`，**不是** `.reader-shell`——脚本执行时 `<body>` 尚未解析，该元素不存在。
- `auto` **也要写出属性**（`data-reading-theme="auto"`），它靠「没有 CSS 覆盖规则」生效，不靠属性缺席。
- chrome 的 `system` 反过来——**必须移除** `data-theme`，因为跟随系统靠 `@media` 命中 `:not([data-theme="light"])`。

**`--dedao-transition-*` 的替换必须成对写，不许只换时长。** 规格 §3.5.2 把三档时长与三条缓动**拆开**了——`--r3-duration-fast` 只是 `150ms`，不含 `ease`；而现状 `--dedao-transition-fast` 的值是 `150ms ease`，**时长和缓动焊在一起**。实测 `src/reader3_app/web` 下共 **43 处**引用 `var(--dedao-transition-*)`，形态如 `transition: all var(--dedao-transition-fast)`（11 处）、`transition: transform var(--dedao-transition-normal)`（7 处）等。

> ⚠️ **只把 `var(--dedao-transition-fast)` 换成 `var(--r3-duration-fast)`，缓动就没了。** 简写里省略 `transition-timing-function` 时取的是 CSS 默认的 `ease`，所以**不会**退化成 `linear`——正因为看不出来，这个错误不会被人眼发现。但它绕过了 `--r3-ease-standard` / `-decelerate` / `-accelerate` 三条缓动 token，**动效 token 只落地了一半**；而 §9.3 的硬编码 lint 只抓「写了字面量」，抓不到「缺失的 token 引用」，也不会报。
>
> 做法：43 处一律写成 `var(--r3-duration-X) var(--r3-ease-Y)`。默认配对是 `--r3-ease-standard`；**入场**用 `--r3-ease-decelerate`、**出场**用 `--r3-ease-accelerate`。

#### 10.1 原型变量 → `--r3-*` 映射表（本 WI 的交付物之一）

WI-13 / WI-16 要照抄原型 `designs/reader-pro-next/`，而原型用的是**第三套裸名变量**（43 个），与 `--r3-*` 名字完全不同（`--p-*` 是第一套、`--r3-*` 是第二套、§9.2 里那批死掉的 `--wr-*` 与裸名是第四套）。没有对照表，两个人抄同一个原型会抄出两套映射，而这种分歧要到主题切换时才暴露。

**43 个原型变量在下表里全部有归属**——要么映射到某个 `--r3-*`，要么显式标为「不进 Tier 2」并说明理由。

| 原型变量 | → | 说明 |
|---|---|---|
| `--canvas` | `--r3-bg` | |
| `--surface` | `--r3-surface` | |
| `--surface-raised` | `--r3-surface-raised` | |
| `--surface-muted` | `--r3-surface-sunken` | 原型 muted ＝**下沉面**，不是 hover 面。按名字直译会映错角色 |
| `--ink` / `--text` | `--r3-text` | 原型两个名同角色，合并为一个 |
| `--muted` | `--r3-text-muted` | |
| `--quiet` | `--r3-text-subtle` | **取值不照抄原型**：原型 `#94a3b8`（亮）/ `#64748b`（暗）均不过 4.5:1，spec §3.3 已改成 `#707070` / `#7a8aa2` |
| `--border` | `--r3-border` | |
| `--border-strong` | `--r3-border-strong` | |
| `--blue-500` | `--r3-accent` | D-5 品牌蓝 |
| `--blue-600` | `--r3-accent-hover` | |
| `--blue-50` | `--r3-accent-subtle` | |
| `--blue-100` / `--blue-200` / `--blue-700` | **不进 Tier 2** | 原型调色板的中间档，没有稳定语义角色。使用点逐处改判到 `--r3-accent*` 或状态色 |
| `--success` / `--success-bg` | `--r3-success` / `--r3-success-subtle` | |
| `--warning` / `--warning-bg` | `--r3-warning` / `--r3-warning-subtle` | |
| `--danger` / `--danger-bg` | `--r3-error` / `--r3-error-subtle` | **改名**：danger → error，与规格 §3.3 对齐（也是 §1.3 那三处悬空引用的同一次重命名） |
| `--info-bg` | `--r3-info-subtle` | 原型**没有** `--info` 前景，按规格补 `--r3-info` |
| `--highlight` | `--r3-search-hit` | **搜索命中底**，与标注高亮 `--r3-hl-*` 是不同角色，别合并；规格 §3.3 已补上这个 token（chrome 轴亮暗两块里各定义一次） |
| `--anno-yellow` / `-green` / `-pink` / `-blue` | `--r3-hl-yellow` / `-green` / `-pink` / `-blue` | WI-7 同时把它们改成 `-rgb` 三元组形式 |
| `--page-bg` / `--page-ink` / `--page-quiet` | 同名 `--r3-page-*` | 属 **reading 轴**（见上表），不属 chrome 轴 |
| `--shadow-sm` / `-md` / `-lg` | `--r3-shadow-sm` / `-md` / `-lg` | |
| `--radius-sm` / `-md` / `-lg` | `--r3-radius-sm` / `-md` / `-lg` | §3.4 已一一对应 |
| `--sidebar-width` | `--r3-sidebar-w` | |
| `--insights-width` | `--r3-right-w` | |
| `--rail-width` | `--r3-rail-w` | 规格 §3.4 已定义 `--r3-rail-w: 56px` |
| `--header-height` | `--r3-header-h` | 规格 §3.4 已定义 `--r3-header-h: 60px` |
| `--ui-font` | `--r3-font-sans` | |
| `--reading-font` | `--r3-font-serif` | ⚠️ §3.4 已裁定 Google Fonts 是离线故障点；落地时自托管或回退系统字体栈（D5 已锁定后者，见 WI-18） |

#### 10.1.1 原型 z-index → 九档枚举 snap 表（本 WI 的交付物之一）

规格 §3.5.1 的九档枚举是按 **`src/` 的 19 个字面量**归纳的。但 WI-13 / WI-16 照抄的是原型 `designs/reader-pro-next/index.html`，它另有一套阶梯——**13 处、10 个不同值**（`2 5 30 40 50 55 60 90 100 200`），与 `src/` 那套只有部分重合。规格 §3.5.1 已明写这张逐值表归本节维护、本节不与它重复；没有这张表，两个人抄同一个原型会各归各的档。

| 原型值 | 出处（`designs/reader-pro-next/index.html`） | 角色 | → token |
|---|---|---|---|
| 2 | `:397` `.selection-check` | 卡片内选择勾 | `--r3-z-raised` |
| 5 | `:543` `.page-arrow` | 翻页箭头 | `--r3-z-raised` |
| 30 | `:358` `.row-menu` | 行内下拉菜单 | `--r3-z-popover` |
| 40 | `:288` 页头 | 粘性页头 | `--r3-z-sticky` |
| 50 | `:597` `.reader-sheet` | 阅读页面板 | `--r3-z-panel` |
| 55 | `:560` 右栏 | 面板 | `--r3-z-panel` |
| 55 | `:775` 抽屉遮罩 | 遮罩 | `--r3-z-overlay` |
| 60 | `:572` `.popover` | 气泡 | `--r3-z-popover` |
| 60 | `:766` insights 抽屉 | 面板 | `--r3-z-panel` |
| 60 | `:785` sidebar 抽屉 | 面板 | `--r3-z-panel` |
| 90 | `:692` `.annotation-toolbar` | 标注工具栏 | `--r3-z-popover` |
| 100 | `:739` `.overlay` | 面板遮罩 | `--r3-z-overlay` |
| 200 | `:179` `.skip-link` | 跳转链接 | `--r3-z-skip` |

> **这张表的价值不在表本身，在下面三条翻译陷阱。照值替换会踩中前两条。**
>
> 1. **原型把不同角色塞进了同一个值。** `55` 同时是面板（`:560`）与遮罩（`:775`），`60` 同时是气泡（`:572`）与两个抽屉（`:766` / `:785`）。按值机械替换会把遮罩和面板抬到同一档，**遮罩就不遮了**。必须**按角色**替换，不能按值替换——上表的「角色」列就是替换依据，「原型值」列只是定位用。
> 2. **叠放顺序有一处反转，是有意的。** 原型里 `.overlay`(100) 高于 `.annotation-toolbar`(90)，即遮罩盖住标注工具栏；新枚举里 `--r3-z-popover`(500) 高于 `--r3-z-overlay`(300)，关系反过来。这与「`--r3-z-toolbar` 高于遮罩」是同一条设计意图，**但它是行为变化，不是等价替换**。归 WI-16 在三覆盖层几何门槛里验证：标注工具栏与面板遮罩不同时出现，所以这次反转不产生实际遮挡。
> 3. **`--r3-z-skip` 是为原型的 `.skip-link` 新开的一档。** 规格 §3.5.1 已把它定义为第 9 档 `700`（最高）。`src/` 现状里根本没有跳转链接，所以按 `src/` 归纳出的那八档漏了它——这一档的存在理由只在原型侧。

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
11. **暗色声明唯一作者**：`CHROME_THEMES.dark` 在源码内的定义处计数为 1；生成的**压缩前**样式表里两个必需选择器都在，且抽出它们的声明体后字符串**逐字节相等**；任何手写样式表里都不出现这两段暗色声明。把其中一处改掉、或再写一份定义，构建测试必须失败。
12. `theme-tokens.ts` 里 `CHROME_THEMES` 与 `READING_THEMES` 是两个独立导出，不存在把两者合并成单张表的类型或运行时结构。
13. **原型变量全覆盖**：§10.1 映射表左列的条目并集等于原型 `designs/reader-pro-next/` 里定义的 **43 个**变量，无遗漏无多余；每一条要么给出一个存在的 `--r3-*` 目标（该目标在 10 种主题组合下解析非空，即第 2 条），要么显式写着「不进 Tier 2」并附理由。断言方式是拿原型里的变量定义清单与表左列做集合比对，差集两侧都必须为空。
14. **原型 z-index 全覆盖**：§10.1.1 表覆盖原型 `designs/reader-pro-next/index.html` 的全部 **13 处** z-index，每一处都映射到九档枚举之一（无「待定」「同上」之类的空位）；且替换完成后 `{前端源码根}` 下裸 `z-index: <数字>` 的出现次数为 0——只许 `z-index: var(--r3-z-*)`（这条由 §9.3 的硬编码 lint 覆盖，本条只声明它对本 WI 的产物必须为绿）。
15. **动效 token 成对落地**：扫 `{前端源码根}` 下所有 `transition` / `transition-duration` 声明，凡该声明里出现 `var(--r3-duration-*)` 的，**同一条声明里必须同时出现 `var(--r3-ease-*)`**；违例计数断言为 0。同时源码内 `var(--dedao-transition-` 的出现次数为 0。

---

### WI-11: 4A.3 共享模块

**范围**：`{前端源码根}/shared/escape.ts`、`toast.ts`、`dom.ts`、`debug.ts`。

**前置 WI**：WI-9。（007 的 0.4 已交付，但它**不**决定 `escape.ts` 的形状，见下。）

**做什么**：把散在各处的公共工具收成共享模块。

- `escape.ts` 的形状**由本 WI 裁定**（ET-9），不由 007 的 0.4 决定——0.4 的范围止于 IIFE 化。

> ⚠️ **0.4 已交付，但它没有做收敛——收敛仍是本 WI 的活。** 0.4 于 2026-08-23 完成（commit `f11b346`，见 §3）：四个 JS 文件 IIFE 化，顶层符号不再挂 `window`，四份 `escapeHtml` 不再互相覆盖。**但它们仍然是四份实现**，只是各自关在自己的 IIFE 里。
>
> ~~此前这里写的是「0.4 是个悬空前置，本 WI 必须自带退路」，理由是 007 把 0.4 标为 ❌、卡在「没有 JS 测试宿主（要到 013 才有）」，而 013 就是 WI-9–WI-13 这批，于是成环。~~ 那个环 2026-08-23 已经解开——007 没等测试宿主就把 IIFE 化做完了。**但下面这条裁决不变，只是理由从「破环」换成「0.4 的范围本来就不含收敛」**：
>
> **裁决：`escapeHtml` 的收敛在本 WI 内完成（ET-9）。** 结论现在就能给，因为四份实现实测只有两派、且**无安全差异**：
>
> | 派 | 出处 | 写法 | 空值处理 |
> |---|---|---|---|
> | A | `library-search.js:1`、`search.js:14` | `replaceAll` 链 | `String(text)` —— `null` 渲染成字面量 `"null"` |
> | B | `ai.js:1`、`settings.js:5` | `replace(/…/g)` 链 | `String(str \|\| "")` —— `null` 渲染成空串 |
>
> 两派转义的是**同一组五个字符** `& < > " '`，`&#39;` 与 `&#039;` 是等价实体。唯一实质分歧在空值：**取 B 的空值语义**（把 `null` / `undefined` 渲染成 `"null"` 是缺陷不是特性），写法取 A 的 `replaceAll`（可读）。`escape.ts` 导出单个 `escapeHtml(value: unknown): string`。
>
> 007 的 0.4 已经收工且没有碰这个裁定，所以本 WI 是 `escapeHtml` 语义的**唯一定义处**；日后任何一侧要改，改这里，不得在 007 那边另起一份。
- `showToast` / `elementDebugInfo` / `getEventTargetElement` 从 `annotations.js` 移出来落这里——WI-14 的八模块行数合计约 1085、文件实际 1127，差额就是这三个。
- 设计规格 §5 标注 `Toast` 组件**不存在**，本 WI 要把它建出来。
- 44 处 `console.log`（`annotations.js` 33 ＋ `epub-renderer.js` 9 ＋ **`pagination.js` 2**；后者随 WI-9 §9.2 整文件删除，实际要改的是 42 处）换成 `debug.ts` 分层，由 `localStorage["reader3.debug"]` 控制、默认关；ESLint 开 `no-console` 但放行 warn / error。

**涉及 testid**：`rd-toast` / `lib-toast`（Toast 容器）。

**涉及降级状态**：无。

**验收标准**：

1. 源码内 `console.log(` 出现次数为 0，`no-console` 规则开启且构建通过。
2. `localStorage["reader3.debug"]` 未设置时 `debug.*` 调用不产生任何控制台输出；设置后产生输出。
3. `escape.ts` 只导出单个 `escapeHtml`；源码内 `escapeHtml` 的**定义**处（非引用处）计数为 1，四份旧实现（`library-search.js` `search.js` `ai.js` `settings.js`）的本地定义全部删除。
   - a. `escapeHtml(null)` 与 `escapeHtml(undefined)` 均返回空串（取 B 派语义，见上表）。
   - b. 参数化用例覆盖 `& < > " '` 五个字符各自的输出实体，逐一比对字面量。
4. Toast 挂载后 N 毫秒自动消失，且同时最多存在一个 Toast 容器元素。`N` ＝ `getComputedStyle` 读到的 `--r3-dwell-toast`（断言用同一个读值，既不写死常数、也不以任何 `--r3-duration-*` 为基），求值规则见 §5.0 占位符表，取值裁决见设计规格 §5.3。
   - a. **同一条在 `prefers-reduced-motion: reduce` 下重跑一遍**（Playwright `emulate_media(reduced_motion="reduce")`）：`--r3-dwell-toast` 的解析值与默认下**逐字相等且不为 `0ms`**，Toast 仍然停留 N 毫秒之后才消失——此时进出场过渡确实降到 `0ms`（§3.5.3 单点降级），停留不受影响。**这一子条是本验收存在的理由**：旧写法以 `--r3-duration-slow` 为基，在这里会算出 `0 × 8 = 0`，于是「Toast 一挂载就消失」和「断言期望值为 0」同时成立，测试全绿而减少动效的用户一个字都读不到。
5. `showToast` / `elementDebugInfo` / `getEventTargetElement` 在 `{前端源码根}/reader/` 下的定义处计数为 0（确实移走了）。

---

### WI-12: 4A.2 设置页切片

**范围**：`templates/settings.html` → TS 页面；设置页四个分区；破坏性操作确认。

**前置 WI**：WI-9、WI-10、WI-11。

**做什么**：把设置页搬进设计系统（D3：现状 `settings.html` 完全在设计系统之外）。

设计规格 §6.1 的四个分区照做。破坏性操作（清缓存 / 清会话 / 重建索引）必须走 `<dialog>` 确认，**不要用 `confirm()`**。

> **`Modal` 选型已于 2026-08-20 统一裁定为原生 `<dialog>` ＋ `showModal()`**（`div[role=dialog]` 落选，裁决理由见 **WI-6** 与 `spec-frontend-design.md` §5；ET-17 已闭）。本 WI 这条要求不变——它本来就写的是 `<dialog>`。要注意的是：**WI-12 与 WI-6 用的是同一个 `Modal` 组件，不是两套。** `set-confirm-dialog` 与 `rd-conflict-dialog` 的差别只在 `role`（`dialog` vs `alertdialog`）和关闭路径的数量（三条 vs 零条），底座是同一个。焦点陷阱、Esc 分层与兄弟节点 `inert` 都由 `showModal()` 提供，两边都不手写。

移动端 390×844 下 ollama 行的 `Enabled` 溢出（§7 实测第四项）在这一项修掉。

**第 3 分区「外观」是新增的**，只放 **chrome 轴**：界面明暗三选一（跟随系统 / 浅色 / 深色）。**这里没有纸色**——纸色是另一根轴，控件在 WI-18 的阅读设置面板里（§11-R7）。三选一写 `reader3.ui.colorScheme`，`system` 时**移除** `<html data-theme>`；token 与 FOUC 脚本由 WI-10 提供，本 WI 只挂控件。

> ~~此前这一分区还写着「＋ 界面语言」。~~ **2026-08-23 裁决：界面文案 zh-CN 为唯一交付语言**（此前 `spec-frontend-design.md` §0 定的「en 为主」已被推翻），**界面语言控件随之删掉**——只有一个 locale 时它是空操作。理由不在这里重述，见 `spec-frontend-design.md` §6.1（与那边删掉 `Auto suggested questions (future)` 同一条理由）。本分区因此**只有明暗三选一一组控件**，`涉及 testid` 栏里也没有语言控件的 testid。

**涉及 testid**：`set-appearance-scheme-system` / `-light` / `-dark`、`set-provider-*`、`set-data-cache`、`set-data-conversations`、`set-data-reindex`、`set-export-json`、`set-export-settings`、`set-rag-chunks`、`set-rag-context`、`set-rag-embedding`、`set-confirm-dialog`、`set-confirm-ok`、`set-confirm-cancel`。

**涉及降级状态**：无。

**验收标准**：

1. 源码内 `confirm(` 与 `alert(` 出现次数为 0。
2. 点任一破坏性操作后 `set-confirm-dialog` 可见；点 `set-confirm-cancel` 后请求数为 0；点 `set-confirm-ok` 后对应请求发出 1 次。
3. 设置页所有 testid 匹配 canonical 正则且以 `set-` 开头（命名 lint 通过）。
4. 390×844 下 ollama 行的 `Enabled` 控件 `getBoundingClientRect().right` ≤ 视口宽度。
5. 设置页样式文件对 `--p-*` 的直接引用次数为 0。
5b. `templates/settings.html` 的**内联 `<style>` 块数与 `style="` 属性数合计为 0**（§9.1 的口径；实测起点是 `<style>` 0 ＋ `style="` 2 处 ＝ **2**，在 `:62`、`:64`，其中 `:62` 带 `gap:8px`），两处都在本 WI 迁走；且该页样式经 Vite 产出到 `dist/`。只数 `<style>` 标签会把起点记成 0，等于给一个违规文件发绿灯。
6. 「外观」分区恰有三个明暗选项，`role="radiogroup"` ＋ 同时 `aria-checked="true"` 的数量为 1；无存储值时选中 `set-appearance-scheme-system`。
7. 选中 `system` 后 `<html>` 上**不存在** `data-theme` 属性；选 `light` / `dark` 后属性值等于所选，且 `reader3.ui.colorScheme` 同步。三次切换都**不触碰** `data-reading-theme`。
8. 「外观」分区内不存在任何纸色控件（`rd-pref-theme-*` 在设置页命中数为 0）。
9. **迁出的样式不许带着硬编码走**：5b 产生的设置页样式文件（含 `static/settings.css` 的迁入内容）全部通过 **§9.3 的 token 硬编码 lint**，即 `templates/settings.html` 与 `static/settings.css` 两项从该 lint 的白名单里**划掉**。设置页的 2 处 `style="` 里有 `gap:8px` 这类裸间距（`templates/settings.html:62`），正是 §9.3 第 5 类违规；只做 `<style` 归零而不过硬编码 lint，等于把它们原样搬进 `.css` 就地合法化。本条与 5b 必须同批转绿，写法与 WI-13 验收 9、WI-16 验收 15 一致。

---

### WI-13: 4A.4 书库页切片

**范围**：`templates/library.html` → TS 页面；三栏网格；DEG-S2 / DEG-S3 / DEG-S4 重做版；**删除 `library_classic.html`、`READER3_LIBRARY_UI=classic` 分支，以及随之失去唯一加载方的 `static/search.css`**。

**前置 WI**：WI-3、WI-4、WI-5、WI-8、WI-9、WI-10、WI-11。

**做什么**：书库页按设计规格 §6.2 重做——三栏网格、每栏 `min-width: 0`。

Track D 交付的是**朴素形态**（Phase 3 的门槛只要求「可见」，哪怕落到现有 Jinja 模板的朴素横幅）；本 WI 交付的是**重做形态**。这是两次交付，不是一次。DEG-S2 / DEG-S3 / DEG-S4 的重做落这里，DEG-S1 落 WI-16，DEG-S5 的 UI 落 Phase 2a。

移动端 390×844 的两处不可达（右栏 `x=390, width=249` 够不着；左栏未渲染导致 `#collections-create` 够不着）在这一项修掉。

书卡进度值与 WI-19 对齐（同一个计算口径）。

**Header 新增界面明暗切换按钮**（chrome 轴三态循环 跟随系统 → 浅色 → 深色，与 WI-12 设置页那组是**同一个状态**、同一个 key）。**不是纸色切换**——书库页没有纸（§11-R7）。

**删除动作**：`library_classic.html`、它的环境变量分支，**外加 `static/search.css`（328 行）**。**执行删除前须单独确认**。

`search.css` 今天不是死代码——它有唯一一个加载方，就是 `library_classic.html`。本 WI 删掉那个模板的同一刻，它变成孤儿。所以它**不在** WI-9 §9.2 的清理清单里（那批是已经死的），而是本 WI 自己制造、也由本 WI 负责收尾的。连同 §9.2 的 1920 行，本计划清掉的死前端代码合计 **2248 行**。

> 新书库页若仍需要搜索框样式，从规格 §6.2 新写并走 Tier 2 token——**不要**把 `search.css` 改名留用，理由同 §9.2 的合规实测。

**涉及 testid**：`lib-theme-toggle`、`lib-book-grid`、`lib-book-card`、`lib-sidebar`、`lib-collections-create`、`lib-search-input`、`lib-filter`、`lib-sort`、`lib-view-grid`、`lib-view-list`、`lib-bulk-bar`、`lib-select-all`、`lib-select-none`、`lib-bulk-index`、`lib-bulk-collection`、`lib-empty`、`lib-filter-empty`、`lib-dropzone`、`lib-add-books`，以及 WI-3 / WI-4 / WI-5 的全部降级 testid。

**涉及降级状态**：DEG-S2、DEG-S3、DEG-S4（重做形态）。

**验收标准**：

1. 三栏容器每一栏的 `min-width` 计算值为 `0px`。
2. 390×844 下 `lib-collections-create` 可见且 `getBoundingClientRect()` 完全落在视口内；右栏内容同样落在视口内。
3. 1440×900 下三栏都可见。
4. `library_classic.html` 与 `static/search.css` 两个文件均不存在；**源码与 `CLAUDE.md` 内** `READER3_LIBRARY_UI` 出现次数为 0（实测 `CLAUDE.md:35` 现有一行 `READER3_LIBRARY_UI=classic uv run reader3-server`，必须同批删掉——否则文档在教用户用一个已经不存在的开关）；全仓库对 `search.css` 的引用（含模板 `<link>`、`server.py`、文档）计数为 0。
4b. `templates/library.html` 内联 `<style>` 块数为 0（§9.1）。起点是 **1075 行**内联样式，全部迁到 `dist/` 产物；迁移后 `templates/library.html` 行数 **≤ 420 行**（实测现状 1439 行，减去 1075 行内联样式即 364 行结构，留 56 行余量。写绝对值而不是「显著低于」，是因为后者不可判——1438 也「低于 1439」）。
5. 书卡显示的进度值与 WI-19 定义的计算口径逐本一致（同一本书两处取值相等）。
6. 书库页所有 testid 以 `lib-` 开头且匹配 canonical 正则。
7. 空库、筛选无结果、加载失败三种状态各自渲染对应 testid，且三者互斥（同一时刻只有一个可见）。
8. `lib-theme-toggle` 连点三次回到初始态；`aria-label` 随态更新；三态与设置页「外观」互通（在设置页选 `dark` 后回书库，按钮显示 `dark`）。
9. **迁出的样式不许带着硬编码走**：4b 产生的那些 `.css` 文件全部通过 **§9.3 的 token 硬编码 lint**，即 `library.html` 这一项从该 lint 的白名单里**划掉**。少了这一条，4b 就只是把 1075 行硬编码从模板搬进 CSS 文件——`<style` 计数归零了，`#rrggbb` 与离档字号一个没少。本条与 4b 必须同批转绿，不许分两次。
10. **Track D 的 4A 半边在这里结账**：WI-1–WI-8 中标着 `〔实现类·前置 WI-9〕验于 013` 的**全部** 34 条验收已实际执行并全绿，条数与 §4.0 分布表一致。少了这一条，那 34 条从 `010` 的账上划走之后落不到任何账上——`010` 说「未激活」，`013` 从不提它们，等于谁都不欠。**判法**：跑一遍 §4.0 那 34 条，逐条二值记录，全绿才算本 WI 完成。

---

### WI-14: 4B.1 annotations.js 八模块拆分

**范围**：`static/js/annotations.js`（1127 行）→ `{前端源码根}/reader/` 下八个模块。

**前置 WI**：WI-9、WI-11。

**做什么**：**零行为变更**的结构拆分，例外**恰好两条**：K6（见 WI-15）与改色语义（见下）。

**例外二——改色保 id（2026-09-01 裁定）**：今天没有「改色」这个操作。色板点击只调 `setSelectedColor` 换掉「下一次要用的颜色」；随后重按 marker 走 `toggleMarkerAnnotation`，旧标注**保留**、另加一条新色的，两条并存；重按 wavy / underline 走 `toggleAnnotation`，**先删后建**，`id` 变了。三条路径没有一条是用户以为的「把这条标注改成绿色」。本 WI 把它做成一个真操作：**颜色变、`id` 不变、不产生第二条**。落点在 `commands.ts`（`toggleMarkerAnnotation` / `toggleAnnotation` 是同一个写入链的两个入口）与 `overlays.ts`（`setSelectedColor` 需要知道当前是否已选中某条标注）。用例侧的两条断言（现状 `W-5a` / 变更后 `W-5b`）定义在 [009 任务书](../20260816-tech-stack-migration/tasks/009-e2e-annotations.md) §3，本文不复述。

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
3. `baseline-1b` 全部用例零改动通过，**唯一例外是 W-5a**（见第 6 条）。这条例外必须是**具名的、事先写下的**——「拆分时顺手发现某条 baseline 不对了就改掉它」正是零行为变更门槛要防的事，只有事先点名的那一条不算。
4. iframe 边界三重断言 A/B/C 全部通过（定义见 `spec-frontend-design.md` §6.0）。
5. 八个模块的导出符号并集等于原 `annotations.js` 的对外符号集合，无遗漏无新增（K6 的兜底删除除外）。
6. `acceptance-4b1` 组的 **W-5b** 解开 skip 并绿：改色后 `notes.json` 里该条标注的 `id` 与改色前相同，且该段文字上的标注条数仍为 1。**并且先证明 W-5a 转红**——它特征化的正是本 WI 换掉的旧行为，它若还绿着，说明改色根本没做，W-5b 的绿另有来源。顺序是：跑一次拿到 W-5a 的红，再把它从 `baseline-1b` 删除（不是 skip——被替换掉的特征化没有第二次用途）。

   ⚠️ **K-1a / K-6a 不走这条路，别照抄**：它们断言的是 4B.1 之后依然成立的东西（七个宿主元素齐备、`chapter_index` 等于 URL 里那个数），4B.1 落地后仍是绿的，一条都不用动。W-5a 是本计划里**唯一**一条会被自己的行为变更打红的 baseline 用例。
7. `anchoring.ts` 的五个函数全部有单测，**按两类分别要求**（此前写「五个都做无 DOM 纯函数单测」，实测不成立——五个里只有两个是纯的）：

   | 类别 | 函数 | 签名证据 | 测试要求 |
   |---|---|---|---|
   | 纯函数 | `findRange` `buildSegments` | `annotations.js:100` `findRange(text, ann)`、`:116` `buildSegments(ranges)`——字符串与区间运算 | 单测**不依赖 DOM 或网络** |
   | DOM 适配器 | `buildTextIndex` `offsetFromNode` `rangeFromCfi` | `:54` `buildTextIndex(container)`、`:79` `offsetFromNode(nodes, targetNode, nodeOffset)`、`:242` `rangeFromCfi(cfi, contents, doc)`——收发 DOM 节点 / Range / epub.js contents | 在 DOM 环境下测，允许依赖 DOM，**不许**依赖网络 |

   拆模块时应尽量把适配器里的纯逻辑挤进第一类，但**不得**为了凑「无 DOM」而给三个适配器套一层假接口——那是把契约做成了测试的形状。
8. **`commands.ts` 不许触碰 DOM，用 lint 断言而非文档断言。** 此前这里写「PR 描述里列出所有触碰 DOM 的位置（文档级验收）」——那不是验收，是自陈；写了照样能合，也没人会在第二次改动时重读。改成 ESLint `overrides` 里对该文件单开一条：

   ```jsonc
   // .eslintrc.* — overrides 数组中
   {
     "files": ["**/reader/commands.ts"],
     "rules": {
       "no-restricted-globals": ["error",
         { "name": "document", "message": "commands.ts 是纯命令层，DOM 访问走注入的宿主接口" },
         { "name": "window",   "message": "同上" }
       ],
       "no-restricted-properties": ["error",
         { "object": "globalThis", "property": "document" },
         { "object": "globalThis", "property": "window" }
       ]
     }
   }
   ```

   验收即「`eslint` 在 CI 上通过」。这条与 WI-9 的 `dependency-cruiser` `commands-no-upward` 规则互补：后者管**模块依赖方向**，本条管**全局对象访问**——绕过依赖图直接摸 `document` 是 cruiser 看不见的。

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
- **K6**：删掉 `location.pathname` 兜底并改为抛错。这是 WI-14 两条有意的行为变更之一（另一条是改色保 id，定义在 WI-14）。

六个契约里四个现在是**静默失败**的。

**涉及 testid**：无新增。

**涉及降级状态**：无。

**验收标准**：

1. 删掉页面上任一个覆盖层元素后初始化，控制台出现 `error` 级输出且内容包含缺失元素的 id；不出现未捕获异常。
2. `data-action` / `data-color` 传入枚举外的值时构建期报类型错误（构造一个反例断言 `tsc` 非零退出）。
3. `offsetRect` 的定义处带视口坐标说明注释：**该函数定义上方连续注释块中同时出现「视口」与 `getBoundingClientRect`**（对源码做字符串断言，不靠人工阅读）。K3 的全部坑都在这个坐标系上，注释缺失一次就够下一个人踩回去。
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

- **工具栏** rail 5 个 SVG 按钮（目录 / 搜索 / 笔记 / AI ＋ 字体 `Aa`）＋ 新增 active 态，z-index 高于所有面板。**返回键不在 rail 上**，在页头 `rd-header-back`——理由见规格 §2.1.4 的 C1（返回没有激活态，混进 `aria-pressed` 组里会逼出一个假的 `aria-pressed="false"`）（修 D6：现状 `closeAllPanels()` 只关搜索和 AI，TOC / Notes 打开时点搜索按钮会超时）。
- **面板互斥**：单一 `activePanel` 状态。≥1280px 用 push 布局，<1280px 用 overlay。
- **焦点**：打开时焦点移入、Esc 关闭并**归还焦点**、Tab 在面板内循环。现状 `resetFocusAfterClose()` 只做了 blur。
- **导航区**：**删除隐形 nav-zone**，改显式 `‹` / `›` 翻页按钮（带 `aria-label`），`<768px` 隐藏（该档由工具栏翻页）。章节导航（跳 spine）与页内翻页在语义上必须可区分。裁决见规格 §11-R2——原先的「`<1024px` 禁用」是用视口宽度代理触屏，代理是错的。
- **标注工具栏** 7 个操作 ＋ 4 个颜色，中文文案，`aria-pressed`，Delete 单独隔开。
- **DEG-S1 重做形态**落这里。
- WI-15 里标 `@deprecated` 的两个成员在本 WI 结束时删除。

**K3 硬约束（覆盖层挂载点）**：只允许两种挂载——`<body>` 直接子元素（生产现状，零改动即合规），或 `<dialog>` ＋ `showModal()` 进 top layer。挂在 `.reader-shell` 里不是禁止，但**每次都要证明**。`.page-flow` 已经带着 `will-change: transform`，就是那个反面教材。

**涉及 testid**：`rd-toolbar`、`rd-toolbar-toc`、`rd-toolbar-notes`、`rd-toolbar-search`、`rd-toolbar-ai`、`rd-toolbar-settings`、`rd-header-back`、`rd-toc-panel`、`rd-notes-panel`、`rd-search-panel`、`rd-ai-panel`、`rd-anno-toolbar`、`rd-anno-copy`、`rd-anno-note`、`rd-anno-ask`、`rd-anno-delete`、`rd-anno-color-yellow` / `-green` / `-pink` / `-blue`、`rd-note-editor`、`rd-note-tooltip`、`rd-degrade-s1`、`rd-page-prev`、`rd-page-next`。

**涉及降级状态**：DEG-S1（重做形态）。

**验收标准**：

1. TOC 或 Notes 面板打开状态下点 `rd-toolbar-search`：搜索面板在超时前打开，且原面板关闭（`rd-toc-panel` 不可见）。
2. 任意时刻可见的面板数 ≤1（对四个面板 testid 逐一取可见性求和）。
3. 面板打开后 `document.activeElement` 在该面板子树内；按 Esc 后面板关闭且 `document.activeElement` 回到触发它的工具栏按钮。
4. 面板打开后连按 N＋1 次 Tab，`document.activeElement` 始终在该面板子树内；`N` 取该面板内可聚焦元素个数（见 §5.0 占位符表），不写死常数。
5. 1440×900 下打开面板，正文容器的 `getBoundingClientRect().width` 变小（push 布局）；1279×800 下打开面板，正文宽度不变（overlay 布局）。
6. **阅读器页 fixture 的 `afterEach`**（或一条专门的结构测试）断言 `rd-anno-toolbar`、`rd-note-editor`、`rd-note-tooltip` 三者的 `containingBlockAncestor(el) === null`。**不是只在 happy path 上验一次**，但也**不挂全局**——书库 / 设置页没有这三个元素（见 FP-10）。同时按 Codex #3 补齐属性集合——独立的 `translate` / `rotate` / `scale`、`content-visibility`，以及 `will-change` 里的 `contain` / `content-visibility` / `backdrop-filter` / `translate` / `rotate` / `scale`，旧 Safari 另查 `webkitBackdropFilter`；每一种制造属性各有一条参数化断言（人为加上该属性后 `containingBlockAncestor` 必须返回非 `null`）。补齐后的集合写回 `contracts/annotation-host-contracts.md` 的 K3。
7. **几何断言**：`rd-anno-toolbar` 的矩形相对选区矩形水平居中，误差 ≤N px；垂直方向贴着选区边缘，误差 ≤N px（两处 `N` 均 ＝ 2，见 §5.0 占位符表）。`toBeVisible()` / `toBeAttached()` **不算数**，不许当替代。
8. `rd-note-editor` 与 `rd-note-tooltip`（经 hover 触发）同样满足第 6、7 条。
9. 全页面不存在隐形翻页热区元素——**用源码级 lint 断言，不用 Playwright 定位器**：构建产物（`static/dist/` 下的 JS 与 CSS ＋ 三个模板）里 `nav-zone-left` / `nav-zone-right` 两个字符串出现次数为 0。用 class 选择器去断言 class 不存在，本身就违反下面「断言目标的选法」第 3 条，而且静态检查比运行时查询更可靠（运行时查不到也可能是元素恰好没渲染）。`rd-page-prev` / `rd-page-next` 存在且各有非空 `aria-label`；767×800 下两者均不可见。
10. 标注工具栏 4 个颜色按钮的 `aria-pressed` 在选中时为 `true`、未选中为 `false`，同时为 `true` 的数量 ≤1。
11. `rd-anno-delete` 与其余六个操作之间存在视觉分隔（其 `margin-left` 或分隔元素存在，计算值断言）。
12. 源码内 `getContentDocument` 与 `Reader3Epub.book` 的引用次数为 0。
13. `baseline-1b` 全部用例通过；A/B/C 三重断言通过。
14. `templates/reader.html` 内联 `<style>` 块数为 0（§9.1）。起点是 **1403 行**内联样式——全仓库最大的一块——全部迁到 `dist/` 产物；模板只剩结构标记、`{{ }}` 插值与 `<head>` 里那一段 FOUC `<script>`。本条转绿即 WI-9 验收 6a 的 allowlist 可以整条删除。
15. **迁出的样式不许带着硬编码走**：第 14 条产生的那些 `.css` 文件全部通过 **§9.3 的 token 硬编码 lint**，即 `reader.html` 这一项从该 lint 的白名单里**划掉**。1403 行是全仓库最大的一块硬编码来源；只做 `<style` 归零而不过硬编码 lint，等于把它整块搬进 `dist/` 并就地合法化。本条与第 14 条必须同批转绿。同时划掉 `static/css/annotations.css` 与 `static/js/epub-renderer.js:95` / `:186` 两处内联样式赋值。**本条转绿即 §9.3 的白名单可以整条删除**——按 §9.3 的初值表，`reader.html` 与 `annotations.css` 是最后两项（`library.html` 归 WI-13 验收 9，`settings.html` 与 `settings.css` 归 WI-12 验收 9，`library_classic.html` 随文件删除消失）。写法与第 14 条对 §9.1 allowlist 的处理对齐：**每条 lint 都要有一个明确的终点**。
16. **Track D 的 4B 半边在这里结账**：WI-1–WI-8 中标着 `〔实现类·前置 WI-9〕验于 014` 的**全部** 22 条验收已实际执行并全绿，条数与 §4.0 分布表一致。理由同 WI-13 验收 10。**判法**：逐条二值记录，全绿才算本 WI 完成。至此 §4.0 的 1 ＋ 33 ＋ 22 ＝ 56 条全部有过实际判定。

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

**做什么**：实现设计规格 [§6.3](./spec-frontend-design.md) 那张阅读设置控件表的四个控件——纸色主题 / 字号 / 行距 / 字体。

> **值域、步长、默认值、存储 key、作用域五项的唯一定义处是规格 §6.3 的控件表，本 WI 不复述数值**（S12）。施工时照那张表取值；两处若不一致，改的是本文件，不是 §6.3。
>
> 这一段此前是那张表的**逐列副本**，副本与正本在行距值域上漂了 0.1 并同时存活（T-13）。删副本是那条裁决的落点之一，**别再抄回来**。

> **纸色的白档叫 `paper`，不是 `white`**；key 命名空间是 `reader3.<区域>.<camelCase>`。两条都是规格 §11-R5 的裁决，理由是生产已发货 `reader3.library.rightPanelCollapsed`。
>
> **这一栏不是界面明暗。** 界面明暗是另一根轴（`data-theme`，控件在 header 与设置页「外观」分区，见 WI-13），存在 `reader3.ui.colorScheme` 里。规格 §6.3 那张表只管纸色。裁决见规格 §11-R7，契约唯一定义处是 §3.3。
>
> **默认 `auto` 而不是 `paper`**：`auto` = 跟随界面明暗（light chrome → 白纸，dark chrome → 深纸），实现是「没有覆盖规则」而不是一段 JS 解析。绝对白纸配深界面是刺眼的开箱体验。

**主题选择器五个选项**（`auto` 排第一），用 `role="radiogroup"` ＋ `aria-checked` ＋ 方向键；字号行高到边界时按钮 `disabled`。

**iframe 注入与宿主 CSS 必须同源**：一份 TS 常量 `READING_THEMES: Record<ReadingTheme, {bg, ink, quiet, hl}>` 同时喂给样式表和 `themes.override()`。**不许**从宿主页 `getComputedStyle` 反解颜色再注进 iframe——`auto` 会让这条路径依赖 chrome 的最终解析状态。`auto` 在常量表里按当前 chrome 取 light / dark 两组之一。

**D5 栏宽**（正文 45–75 字符）：`max-width: 38rem`、`margin-inline: auto`、`text-align: start`、内边距 `clamp(16px, 5vw, 64px)`，在 1440×900 与 390×844 两处都要验。走 `applyThemeSettings`（已在 K5 冻结面里确认）经 `themes.override` 注入。

**删掉三个未授权的商业中文字体。** 字体一律收敛成 `system` / `serif` **两值**（Codex #7）。

**`serif` 的资产归属已裁决：系统 serif 字体栈，本计划不打包任何字体文件**（D5，2026-08-17）。此前这里写的「实施时二选一」作废。锁定的栈是：

```css
--r3-font-serif:
  ui-serif, "Songti SC", STSong, "Noto Serif CJK SC",
  "Source Han Serif SC", SimSun, serif;
```

三条理由：任何有限的 CJK 子集都会在某本 EPUB 上漏字，对任意内容的阅读器是假覆盖；完整思源宋体会永久放大仓库、wheel、service worker 首次安装体积与每次升级的缓存失效量；而 WI-20 的离线壳要求（`plan:1187`）恰恰要求零字体网络请求，系统栈免费满足它。self-host 思源宋体推迟到一个**独立的、可选的字体包工作项**，不在本计划范围内。

> **⚠️ `PingFang SC` 不许进 serif 栈。** 它是黑体。`dedao-theme.css:88` 现在写的是
> `--dedao-font-serif: 'Noto Serif SC', -apple-system, 'PingFang SC', serif;`——只要
> Noto Serif SC 拉不下来（离线、超时），今天的 "serif" 模式就渲染成无衬线。这是**已发货的缺陷**，
> 不是假想风险，随本 WI 一并修掉。

**远程字体引用共 7 处，5 处不在 CSS 里**，删的时候别漏（这是把验收 10 写成全仓库 grep 的原因）：

| 位置 | 内容 |
|---|---|
| `templates/library.html:8,9,10` | `preconnect` ×2 ＋ Noto Serif SC 样式表 |
| `templates/reader.html:9,10,11` | 同样三行 |
| `js/epub-renderer.js:186` | 把同一个 `<link>` **注入 iframe 内部** |
| `js/epub-renderer.js:95` | 硬编码 `font-family: "Noto Serif SC", serif` |

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
10. **字体归属**（此前这一条写「与实施时选定的那一种一致」，D5 已锁死系统栈，下面六小条全部要过）：
    - a. 源码与样式内三个商业中文字体名出现次数为 0；字体选项**恰好两个**（`system` / `serif`）。
    - b. `--r3-font-serif` 的值逐字等于上面锁定的那个栈，且**不含 `PingFang SC`**。
    - c. **全仓库无远程字体**：`grep -rn "fonts.googleapis\|fonts.gstatic\|@font-face" src/` 返回 0。范围是整个 `src/`，**不只是 CSS**——7 处引用里有 5 处在模板和 JS 里（见上表）。
    - d. `static/dist/` 下不存在任何字体文件（`.woff` / `.woff2` / `.ttf` / `.otf` 计数为 0）。
    - e. 选中 `serif` 后 iframe 内正文的计算 `font-family` 等于该栈。
    - f. **离线可用**：拦截并 abort 全部 `font` 类型网络请求后选 `serif` 仍正常渲染；service worker 预热后按 WI-20 的离线壳重新加载，字体网络请求数为 0。
11. `baseline-1b` 零改动通过。
12. 只存在 legacy `reader3-font-settings` 时加载阅读器：新 key 被写出，值等于 legacy 里的值，且实际渲染字号与行高等于 legacy 值（**偏好没被重置**）。
13. legacy 值越界时钳到合法区间，不抛错、不回落默认值。三小条都要过：
    - a. 字号 `99` → 上界 `24`；行距 `3.0` → 上界、`1.0` → 下界（**行距两端各测一次**）。
    - b. **钳位在两条读取路径上一致。** 现状 `static/js/epub-renderer.js` 的 `getFontSettings()` 只写了 `Number(x) || 默认值`——挡 `NaN` 不挡越界，于是同一个越界值会让 iframe 按它渲染、而面板显示默认值，用户看到的当前值不是真实值、也调不回来。重写后不许再有第二套校验。
    - c. **legacy 行距为上界时原样存活、不被钳**：存 `{"fontSize":17,"lineHeight":2.5}` → 新 key 读出 `2.5`，渲染行高为 `2.5`。这一条是 T-13 值域裁决（规格 §2.1.4 C5）的守卫——它一旦红了，说明值域被改回了容不下上界的区间，全体调到最大行距的老用户会**静默位移**。
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

> ⚠️ **本 WI 比标题看起来大：它要先建一个不存在的东西。** 此前这里只定义了「同一个计算函数」，但验收第 2 条要求书库页的 `lib-book-progress` 与阅读器**跨页**相等——跨页相等需要把阅读位置**存下来**，而生产里根本没有阅读进度持久化。实测（2026-08-17）：
>
> ```
> grep -n progress src/reader3_app/web/server.py     → 0
> localStorage 里任何 reader3.*.position / .progress → 不存在
> library.js 里的书卡进度代码                        → 不存在
> ```
>
> （`library.js` 的 `setIndexProgress` 是**索引**进度条，不是阅读进度；`server.py` 里的 `position` 字段是批注排序用的。）
> 所以 WI-19 是「建功能」而不是「修 bug」，排期按此计。

**进度持久化契约**（本 WI 新增，是验收 2 / 5 / 6 的前提）：

| 项 | 定义 |
|---|---|
| 存储位置 | `localStorage["reader3.reader.position"]`，值是 `Record<bookId, {spineIndex: number, ratio: number, updatedAt: number}>` |
| 命名 | 遵循 §11-R5 的 `reader3.<区域>.<camelCase>`，**不新开命名法** |
| 写入时机 | 章节切换时，以及章内翻页后 debounce ≥1s；**不在每次 `relocated` 事件上写** |
| 读取方 | 阅读器页脚、Notes 面板、书库书卡——三处读**同一个** key，经**同一个**计算函数 |
| 多标签页 | 后写胜（`updatedAt` 较大者），不做冲突弹层。书库页监听 `storage` 事件刷新书卡；同一本书在两个标签页里读到不同位置是可接受的 |
| 缺席语义 | 该 bookId 无记录 ＝ 未读，进度显示 0%，**不是**「读到第 0 项」 |
| 不做的事 | 不上服务端、不建 API 端点、不跨设备同步。这是纯前端偏好，与 `notes.json` 的服务端持久化是两回事 |

**涉及 testid**：`rd-progress`、`rd-notes-progress`、`lib-book-progress`。

**涉及降级状态**：无。

**验收标准**：

1. 同一本书同一位置，`rd-progress` 与 `rd-notes-progress` 的文本值相等。
2. 该值与书库页 `lib-book-progress` 相等（同一本书跨页取值比对）。
3. 进度计算函数在源码内的定义处计数为 1。
4. 只有封面的 spine 0 处进度不等于 100%（断言小于 100）。
5. 一本含 N 个正文 spine 项与 M 个非正文项的书，读到最后一个正文项末尾时进度等于 100%。
6. 分母不含非正文项：构造 M 变化而 N 不变的两本书，同一正文位置的进度值相等。
7. **持久化往返**：阅读器读到某位置后刷新页面，`rd-progress` 恢复到同一值；`localStorage["reader3.reader.position"]` 里该 bookId 的记录存在且 `spineIndex` 与实际位置一致。
8. **写入节流**：章内连续翻页 10 次（间隔 <1s），该 key 的写入次数 ≤2。
9. **缺席即未读**：清空该 key 后打开书库，该书 `lib-book-progress` 显示 0%，不是「第 0 项 = 100%」也不是空白。
10. **多标签页后写胜**：两个标签页分别读到不同位置，后写的那个 `updatedAt` 更大；书库页收到 `storage` 事件后书卡取到的是 `updatedAt` 较大的那条。
11. 该 key 的读写在源码内的封装处计数为 1（三个读取方都经它，没有谁直接 `localStorage.getItem`）。

---

### WI-20: Phase 5 前端侧——PWA

**范围**：`manifest.json`（PWA）、service worker、离线壳。

**前置 WI**：WI-12、WI-13、WI-16。

**做什么**：给三个页面配 PWA manifest 与 service worker。

⚠️ **命名撞车**：PWA 的 `manifest.json` 与存储格式的 `manifest.json`（两文件提交协议）是**完全不同的两个东西**。放置路径与文档引用都要显式区分，不要只写「manifest」。

`reader3 launch` 的 CLI 部分不在本计划，在技术栈迁移那侧。

**缓存契约（白名单制，默认不缓存）。** 此前四条验收只管「离线能出壳」，不管**缓存什么**。照默认写法实现，service worker 会把批注原文、AI 问答响应、EPUB 正文全部写进 `CacheStorage` 且没有清理路径——那是把个人阅读数据留在磁盘上，而不只是一个正确性问题。

| 类别 | 策略 | 说明 |
|---|---|---|
| `static/dist/` 下的哈希产物、PWA manifest、icons | cache-first，**白名单** | 只有这一类进缓存 |
| 三个页面的 HTML 外壳 | network-first，失败回落缓存 | 离线出壳靠这条 |
| `/api/**`（含 `/api/notes/*`、`/api/ai/*` SSE、`/api/search/*`） | **network-only，一律不进缓存** | 隐私边界 |
| `/read/{book_id}/book.epub` 与 `images/` | **network-only** | 正文不落盘缓存 |

缓存名带构建版本号（例如 `reader3-v{buildHash}`）；`activate` 事件里删除所有前缀匹配但版本不等的 cache。

**涉及 testid**：无。

**涉及降级状态**：无。

**验收标准**：

1. 三个页面都能拿到 PWA manifest，且 manifest 里 `start_url` / `display` / `icons` 齐备。
2. service worker 注册成功，离线状态下书库页仍能渲染出壳（不是浏览器默认错误页）。
3. 离线状态下数据请求失败时页面显示错误态而不是空白（对应 testid 可见）。
4. PWA manifest 与存储格式 manifest 的路径不同，且都不裸称「manifest」：**两份计划与源码里 `manifest` 一词的全部出现，逐处前面带限定词（`PWA manifest` 或 `存储格式 manifest`），裸用命中数为 0**（grep 可判，排除文件路径与代码标识符本身）。
5. **白名单**：完整走一遍三个页面（含打开批注、跑一次搜索、发一次 AI 提问）后枚举 `caches.keys()` 下的全部条目，每一条的 URL 都匹配白名单（`dist/` 哈希产物 / manifest / icons / 三个 HTML 外壳）。出现任何其他 URL 即失败。
6. **`/api/**` 不进缓存**：上述流程跑完后，对 `/api/notes/*`、`/api/ai/*`、`/api/search/*` 各取一个真实请求过的 URL 调 `caches.match(url)`，全部返回 `undefined`。EPUB 正文与 `images/` 同样断言。
7. **版本清理**：以版本 A 预热缓存 → 换成版本 B 重新注册 → `activate` 后 `caches.keys()` 里不含 A 的缓存名，且页面加载到的是 B 的哈希产物（不是 A 的陈旧 bundle）。
8. **离线不泄漏**：离线状态下打开阅读器，正文与批注请求失败并显示错误态（验收 3），且**不从缓存里变出旧数据**——断言此时页面上不出现上一次在线时的批注内容。

---

## 5. 测试矩阵

### 5.0 通则（对所有用例生效）

**断言目标的选法**，按优先级：

1. `data-testid`（首选）。
2. 没有 testid 时用 ARIA `role` ＋ accessible name。
3. **class 选择器与 `nth-child` 一律禁止**——这是 0.5 选择器 lint 的机器约束，写了就过不了 lint。

**占位符 `N` 的取值（canonical，全文唯一定义处）。** 矩阵与验收里有若干条写成「连按 `N＋1` 次 Tab」「误差 ≤`N` px」「`N` 毫秒后消失」。`N` 不是待定项，是**按用例现场求值的量**——但求值规则必须在这里定死，否则每个实施者会各填一个数：

| 出现形式 | `N` 是什么 | 怎么求 |
|---|---|---|
| 连按 `N＋1` 次 Tab / Shift+Tab | 该容器内**可聚焦元素的个数** | 用例开始时枚举容器子树里的可聚焦元素并计数，不写死常数。按 `N＋1` 次的意义是「绕满一圈再多一次」，只有取实际个数才成立 |
| 几何误差 `≤N px` | **2** | 亚像素舍入与 1px 边框的合计容差。写死 2，不按元素调 |
| Toast `N` 毫秒后消失 | **`--r3-dwell-toast` 的解析值**（取值裁决在设计规格 §5.3，本表不重述秒数） | 从 `getComputedStyle` 读 `--r3-dwell-toast`，断言也用同一个读值。写死常数会变成孤儿；而**以 `--r3-duration-*` 为基更糟**——那一族在 `prefers-reduced-motion` 下是 `0ms`，算式会算出 0、断言照常通过，缺陷对它自己的测试不可见（诊断见规格 §5.3、§3.5.3 例外 3） |

> 三条都是**可执行的求值规则**，不是「实施时自定」。任何一处把 `N` 换成裸常数（几何容差的 `2` 除外），视同违反本节。

> **推论：「某个旧 class 不该再存在」不是 E2E 用例，是 lint 断言。** 用 class 选择器去证明 class 不存在，第 3 条自己就不允许；而且运行时查不到也可能只是那一帧没渲染。这类断言一律落到源码 / 构建产物的字符串计数上（例子见 WI-16 验收 9 的 `nav-zone-*`）。

**执行器：两个，分层，不可互相替代。**

| 层 | 执行器 | 管什么 | 现状 |
|---|---|---|---|
| E2E / 集成 | Python `pytest-playwright` | 本矩阵 §5.1–§5.9 的全部 `F*` 行、009 的 `R/W/K/X` | ✅ `pytest-playwright>=0.9.0` 已在 dev group |
| TS 单测 | **Vitest ＋ jsdom** | `anchoring.ts` 五函数、`escape.ts`、`theme-tokens.ts` 双表、`renderer.ts` 的 `buildSegments` | ❌ **不存在，WI-9 负责建**（见下） |

E2E 侧：**不要写 Node Playwright Test 的 `webServer` 语法**，用 pytest 的 session fixture 起子进程、先设 `READER3_BOOKS_DIR`、分配空闲端口。

> 🔴 **此前这里只写了一个执行器，那是个闭合的空指针。** 实测：仓库**没有 `package.json`**、没有 `node_modules`，两份前端文档里 `vitest` / `jest` / `jsdom` 命中数**均为 0**；全程序里唯一一次提及是 `plan-tech-stack-migration.md:54` 决策表中的括号「（+ 后续 Vitest）」——没有归属 WI、没有分支、没有验收条。
>
> 与此同时，**多条验收已经在要求 TS 单测**：WI-14 验收 6（`anchoring.ts` 五函数分两类做单测）、WI-11 验收 3（`escapeHtml` 参数化用例）、WI-10 验收 11/12（两张主题表的字节一致比对）。而 `tasks/007-hygiene-and-contracts.md:23` 把任务 0.4 卡住的理由正是「**没有 JS 测试宿主（要到 013 才有）**」——013 就是 WI-9–WI-13，可这五个 WI **没有一个**把测试宿主列为交付物。人人都指望别人建，于是没人建。
>
> **裁决：Vitest ＋ jsdom 由 WI-9 交付**，与 Vite 配置同一批（共用 `vite.config.ts` 的 resolve / alias，避免第二套路径解析）。
>
> **理由不是「WI-9 是唯一无前置的 WI」**——那句话是错的，实测声明「前置 WI：无」的有 **WI-1、WI-7、WI-8、WI-9 四个**，不是一个。真正的理由是：**WI-9 本来就要建 `package.json` 与 lockfile，测试宿主是同一个文件里加两行 devDependency 的事**，另开一个 WI 是虚假的粒度。
>
> 补一条 §4.0 之后的推论：Track D 的**实现类**验收也前置 WI-9（源码根 ＋ 执行器都由它交付），所以 WI-1 / WI-7 / WI-8 的「无前置」只对它们的**定义类**那一半成立。**WI-9 是整个前端计划实际意义上的第一个可执行 WI**——它之前能做的只有文档与裁定。

**并行度：`pytest -n 4`（xdist），per-worker 隔离。**

> ⚠️ **`pytest-xdist` 当前不是依赖。** 实测 `pyproject.toml` 与 `uv.lock` 里 `xdist` 命中数均为 **0**；dev group 只有 `hypothesis` / `mypy` / `pytest` / `pytest-cov` / `pytest-playwright` / `ruff`。`-n 4` 在 CI 上会直接 `error: unrecognized arguments: -n`。**落地时必须先把 `pytest-xdist` 加进 `[dependency-groups].dev`**，这条与并行度裁决是同一件事的两半，不要只落一半。

> ⚠️ 这一条**取代**了此前的「初版主 CI 单 worker（Codex #13 的裁定）」。取代理由：本矩阵在参数展开前有 **121 个唯一 `F*` ID**（§5.1–§5.8 共 185 行表格数据行），叠加 009 已有的套件与 §5.1.0 起的八状态乘法，每条用例都要起服务器、渲真 EPUB。串行的反馈时延不可接受，且一条 flake 的恢复成本被放大。
>
> **隔离 fixture**：端口与 `READER3_BOOKS_DIR` 都从 `PYTEST_XDIST_WORKER` 派生（无 xdist 时默认 `gw0`），每个 worker 自带服务器进程与书库目录。本地跑 `-n 1` 零配置退化。
>
> **为什么不按子系统切成四个 CI shard**（评审时的备选）：① 会引入**第二套分类法**——本矩阵已经按 pytest marker 分组（见下），新用例进了 marker 却没进 shard 就静默漏跑；② shard 之间要永久手工再平衡；③ 隔离工作量完全相同——每个 shard 同样要自带端口、进程、书库目录，那正是 xdist 的 per-worker fixture，只是粒度更粗。一个必需检查优于四个。
>
> **分发校验**（保留自该备选方案）：`-n 4` 收集到的 node ID 并集等于 `-n 1` 时的集合，且各 worker 之间两两交集为空。

**分组**：本矩阵新增的用例挂到 009 已定义的同一套 pytest marker——`acceptance-p3` / `acceptance-4a4` / `acceptance-4b1` / `acceptance-2a`，未激活的分组以 `skip` 存在，不删。009 已定义的 `R-1`…`R-6` / `W-1`…`W-10` / `K-1`…`K-6` / `X-1` / `X-2` **不重写**；两边冲突时以 009 为准。

**「可失败」的定义**：每条用例都必须能因为被测行为的缺失而变红。验证方式是反向注入——把被测属性 / 行为人为去掉，用例必须失败。下面这些**不算断言**，不许单独使用：

- `toBeVisible()` / `toBeAttached()` / 「元素存在」
- 「没有抛异常」
- 截图比对

**不测的东西**：WI-8 的 Skeleton 是过渡态，**矩阵里没有任何一条以骨架为断言目标**——断言它之后的东西。

> **骨架为什么连样式都不在 E2E 里断。** 「读骨架的 `animation-name`」看起来是个静态断言，不涉及时序——但要读到它，骨架必须正在屏幕上，也就是必须抢在数据返回之前抓住那一帧。**在 E2E 里，「读骨架的静态样式」和「断言骨架出现」是同一个时序赌局**，只是前者不像。本矩阵 §5.1–§5.9 的全部 `F*` 行都是 `pytest-playwright` E2E（见上方执行器表），所以这个赌局是真的。
>
> 因此 `prefers-reduced-motion` 下骨架静止这条无障碍保证**不落在本矩阵里**，落成 WI-8 验收 2 / 3 的 **CSS 产物断言**。这不是降级：源码断言每次都跑，而一条抓不到加载窗口的 E2E 断言会静默地什么都没验——绿灯，零保证。同一条纪律本节开头已经写过一遍（「某个旧 class 不该再存在」不是 E2E 用例，是 lint 断言）。

**testid 前缀**：书库 `lib-`、阅读器 `rd-`、设置 `set-`。canonical 正则见 `scripts/lint_testid_naming.py` 的 `CANONICAL`（[ADR-0013](../../adr/0013-testid-invariant.md)）。

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
| FB-R01 | WI-16 | rail：`rd-toolbar-toc` / `-notes` / `-search` / `-ai` / `-settings`；页头：`rd-header-back` | 六个按钮八态全过（rail 5 ＋ 页头 1）；每个都有 `aria-label`（不是 `title`）；active 态 `aria-pressed` 正确 |
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
| FB-R13a | WI-18 | `rd-pref-leading` 的加/减控件 | 下界时减 `disabled`、上界时增 `disabled`（边界两端各断言一次，端点值取规格 §6.3 控件表）；从默认值连点增**恰好 6 次**到达上界，且每一步的显示值与 `localStorage["reader3.reader.lineHeight"]` 都是 1 位小数、不出现 `1.7000000000000002` 这类浮点残差。一条用例同时钉住端点可达、步长、默认值落在步进网格上、以及 `Math.round(x * 10) / 10` 没在重写中丢掉。⚠️ 加/减两个控件的 testid 尚未进 WI-18 的 testid 清单（那里行距只有 `rd-pref-leading` 一个），补名归 §4 的 testid 账本 |
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
| FP-01 | WI-16 | `rd-toc-panel` / `rd-notes-panel` / `rd-search-panel` / `rd-ai-panel` | 任意时刻四者可见数 ≤1（逐个取可见性求和） |
| FP-02 | WI-16 | `rd-toolbar-search`（TOC 已打开） | 搜索面板在超时前打开、TOC 关闭。**这是 D6 的回归用例**，现状会超时 |
| FP-03 | WI-16 | `rd-toolbar-notes`（AI 已打开） | 同上，四个面板两两组合各跑一次（12 条参数化） |
| FP-04 | WI-16 | 分层 Escape | 标注工具栏 ＋ 笔记编辑器同时打开时按 Esc：先关编辑器，工具栏仍在；再按 Esc 关工具栏；再按 Esc 关面板 |
| FP-05 | WI-16 | 焦点陷阱 | 面板打开后连按 N＋1 次 Tab，`document.activeElement` 始终在该面板子树内（`element.contains` 断言） |
| FP-06 | WI-16 | 反向焦点陷阱 | 同上，连按 N＋1 次 Shift+Tab |
| FP-07 | WI-16 | 焦点归还 | Esc 关闭后 `document.activeElement` 等于触发它的工具栏按钮 |
| FP-08 | WI-16 | 遮罩点击关闭 | 点面板外遮罩区域关闭面板；**`rd-conflict-dialog` 除外**（见 FG-16） |
| FP-09 | WI-16 | 滚动锁 | 覆盖式面板打开时 `body` 的 `overflow` 计算值为 `hidden`，页面滚动位置在关闭后恢复到打开前的值 |
| FP-10 | WI-16 | `containingBlockAncestor` | **挂在阅读器页 fixture 的 `afterEach` 上**（不是全局），对 `rd-anno-toolbar` / `rd-note-editor` / `rd-note-tooltip` 断言返回 `null`。范围是每个**阅读器**用例，不是只在 happy path 上验一次；书库 / 设置页用例不跑这条——那三个元素在那里根本不存在，跑了要么报错要么退化成一个空分支 |
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
| FA-13 | WI-16 | §8-5 | `prefers-reduced-motion` | 面板动效 `transition-duration` 为 `0s`。**骨架的同款保证不在本行**——见 §5.0「骨架为什么连样式都不在 E2E 里断」，它落在 WI-8 验收 2 / 3 的 CSS 产物断言上 |
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
| FV-11 | WI-16 | 三档 | 翻页控件 | `rd-page-prev` / `rd-page-next` 各有非空 `aria-label`；767×800 下两者不可见（规格 §11-R2） |
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
| FT-05 | WI-7 | **`{前端源码根}` 下的生产 `.css`** | 九个角色的底色声明里字面颜色值命中数为 0（`color-mix(`、`#rrggbb`、`rgb(`／`rgba(` 后跟数字，三类合计）。**判生产代码，不判 `designs/`**——按 `color-mix(` 计数写今天就真空通过，见 WI-7 验收 1 |
| FT-06 | WI-7 | 九个角色（chip ×4、marker ×4、笔记标记 ×1，清单见 WI-7 的角色表） | 全部存在于**生产 CSS** 且形如 `rgb(var(--r3-hl-*-rgb) / α)`，α 分别为 .35（4 处）、.45（4 处）、.18（1 处）。五个新写、四个改写 |
| FT-07 | WI-7 | 亮纸 marker 四色 | `paper` / `sepia` / `green` ＋ `auto`@light 四种纸下，合成后与该纸墨色对比度均 ≥4.5:1（计算值断言，**不乘 chrome**） |
| FT-08 | WI-7 | 夜纸 marker 四色 | `night` ＋ `auto`@dark 两种纸下，背景 alpha 不等于 1，**且**带非背景提示：`text-decoration-line` 非 `none` 或 `border-left-width` 大于 0（黄 3.02 / 绿 3.94 实色不达标，且 paper-night 下解集为空） |
| FT-09 | WI-7 | 角色 9（生产端笔记标记，今天是 `mark.annotation.annotation--note`） | 解析背景色不等于 `--r3-accent` 解析色（D-5 之后品牌蓝会与选区、focus ring 撞色） |
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

### 5.10 出发点：实测覆盖率 9%，前端零覆盖

评审时实跑了一次 unit lane（`uv run pytest tests/unit tests/contract --cov=src/reader3_app`，50 passed / 1.36s），这是本计划真正的起跑线：

```
Name                                Stmts   Miss  Branch  Cover
src/reader3_app/reader3.py            349     42      98    85%   ← 唯一被测的模块
src/reader3_app/ai/books.py            97     54      24    40%
src/reader3_app/web/server.py        1369   1369     430     0%   ← 全部 API 端点
src/reader3_app/search_service.py     421    421     152     0%
src/reader3_app/collections_service.py 134    134      44     0%
src/reader3_app/vector_search.py      138    138      34     0%
src/reader3_app/notes_service.py       59     59      14     0%   ← 标注持久化
src/reader3_app/models/annotations.py  44     44      16     0%   ← Annotation dataclass
  （ai/ 下 9 个模块同为 0%）
------------------------------------------------------------
TOTAL                                3558   3208    1082     9%
```

三条从这张表直接推出的事实，排期与验收都要按它计：

1. **24 个源码模块里只有 2 个被测。** `tdd-guardian/config.json` 的阈值写着 lines 70 / branches 60，而 `coverageMode` 是 `no-decrease`——所以那两个数字今天不是门槛，只是愿景；真正生效的约束是「别往下掉」。本计划不改这个模式，但下面第 3 条是硬要求。
2. **`tests/contract/` 与 `tests/e2e/` 都是空目录。** unit lane 的命令 `pytest tests/unit tests/contract` 今天能绿，是因为 pytest 对空目录不报错。别把「contract lane 存在」读成「契约测试有人管」。
3. **WI-14 的安全网今天不存在。** 它验收 3 写「`baseline-1b` 全部用例零改动通过」，而 `baseline-1b` 属于 009、落在 `tests/e2e/`——空的。同时被它重写的 `annotations.js` 其后端 `notes_service.py` 与 `models/annotations.py` **都是 0%**。也就是说 1127 行拆八个模块这件事，**当前前后端都没有任何自动化回归保护**。

#### 覆盖版图（现状 → 本计划落点）

```
                        ┌─────────────────── 浏览器 ───────────────────┐
                        │                                              │
  templates/*.html      │  reader.html   library.html   settings.html  │
   内联样式 2478 行      │  ▓▓▓▓▓▓▓▓▓▓▓▓  ▓▓▓▓▓▓▓▓▓▓▓▓   ░░            │  ▓=内联 ░=外链
                        │       ↓              ↓            ↓          │
  static/js/*.js        │  annotations.js  library.js   settings.js    │
   ← WI-14 拆八模块      │  ░░░░░░░░░░░░░  ░░░░░░░░░░░   ░░░░░░░░░      │  ░= 0 覆盖
                        └───────────────────┬──────────────────────────┘
                                            │ HTTP
                        ┌───────────────────┴──────────────────────────┐
  web/server.py  1369 stmts │  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0%    │
  search_service  421 stmts │  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0%    │
  collections_svc 134 stmts │  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0%    │
  vector_search   138 stmts │  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0%    │
  notes_service    59 stmts │  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0%  ←─┼── WI-14/15/16 改这条链
  models/annot     44 stmts │  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0%  ←─┤
  ai/* (9 模块)   858 stmts │  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0%    │
  ai/books.py      97 stmts │  ██████████████░░░░░░░░░░░░░░░░░░ 40%    │
  reader3.py      349 stmts │  █████████████████████████████░░░ 85%    │
                        └──────────────────────────────────────────────┘

  本计划新增的两层（今天都是空的）：
    Vitest + jsdom  ──→ anchoring.ts / escape.ts / theme-tokens.ts / renderer.ts   [WI-9 建宿主]
    pytest-playwright ─→ §5.1–§5.9 的 121 条 F* ＋ 009 的 R/W/K/X                  [008 建 CI]
```

#### REG-1：前端重构的回归基线（关键要求，不可跳过）

拆 `annotations.js`、重写三个模板、删 2248 行 CSS——这三件事都是「行为应当完全不变」的改动，而当前**没有任何东西能证明它没变**。所以本计划把一条回归基线列为**关键要求**：

| 项 | 内容 |
|---|---|
| **建立时机** | WI-9 完成时（在任何模板被改动**之前**），基线必须已经绿 |
| **组成** | ① 三页 smoke（书库 / 阅读器 / 设置各自加载成功、无控制台 error）；② 每页的**计算样式快照**（对一组固定 testid 取 `getComputedStyle` 的白名单属性）；③ `notes_service.py` 的读写往返契约测试（现 0%，本条把它抬起来）；④ `models/annotations.py` 的序列化往返 |
| **判据** | WI-12 / WI-13 / WI-14 / WI-16 每一项完成后重跑，① ③ ④ 必须零改动通过；② 允许有 diff，但**每一处 diff 都要在 PR 里逐条说明是设计有意变更**，不许整体接受 |
| **不可跳过** | 这四项不接受「后面补」。理由：②的价值只在「改之前拍过一次」，事后补的快照拍的是已经改坏的状态 |

> 为什么 ② 的快照不写成「像素比对」：§5.0 已禁截图比对当断言。计算样式快照断的是**具体属性值**（`color` / `font-size` / `border-radius` / `padding` …），能指出是哪个 token 掉了，而截图只能告诉你「有东西变了」。

> REG-1 的 ③ ④ 与 008 的职责有重叠。**归属：写在 008，本计划只声明它是 WI-9 的开工前置**——一个事实一个定义处。若 008 排在本计划之后，则 ③ ④ 由 WI-9 自带最小版本（各一条往返用例），008 再扩。

---

## 6. 从 Codex 评审继承的未决项

> **本节现在有两个来源。** 6.0 是 Codex 评审（2026-08），6.1 是 009 分支做 E2E 特征化时**实测撞出来**的生产缺陷（2026-09）。两者性质相同——**别处发现、本计划兑付**，所以放在一起。

`review-codex.md` 的台账留在技术栈迁移文件夹（一次评审的记录不拆开），其中五条属于前端范围，在此继承：

| # | 严重度 | 问题 | 本计划的落点 |
|---|---|---|---|
| **#3** | HIGH | K3 的 `containingBlockAncestor()` 会漏报：没查独立的 `translate` / `rotate` / `scale`、`content-visibility`，`will-change` 的取值集合也漏了 `contain` / `content-visibility` / `backdrop-filter` / `translate` / `rotate` / `scale`。这些属性同样能建立 fixed containing block | **未决**。补齐属性集合、为每种制造属性建参数化浏览器断言、旧 Safari 另查 `webkitBackdropFilter`——落 **WI-16 验收第 6 条**，属性集合补进 `contracts/annotation-host-contracts.md` K3 |
| **#7** | MEDIUM | 「四字体」与设计规格的 `system` / `serif` 二选一冲突；思源宋体同时被称作「待删商业字体」和「可 self-host 开源字体」 | **已在 WI-18 统一为 `system` / `serif` 两值**。serif 的资产归属**已于 D5（2026-08-17）裁决：系统 serif 字体栈，本计划不打包任何字体文件**——定义处在 WI-18，此处不重述。此前这行写的「实施时必须二选一」作废 |
| **#10** | MEDIUM | 现状已经实现了字号 / 行距并存在 `reader3-font-settings`，计划却称控件全无处理器，还改成新的 localStorage key；没定义一次性迁移，会**重置用户偏好** | **落 WI-18 验收第 12–14 条**：legacy JSON 读取 ＋ 范围校验 ＋ 写新 key ＋ 迁移完成标记 ＋ 回归测试 |
| **#13** | HIGH | E2E 执行器混了两套模型：仓库装的是 Python `pytest-playwright`，009 却在用 Node Playwright Test 的 `webServer` 概念并要求每 worker 一服务，当前没有可执行拓扑 | **裁定归 A 的 `tasks/009-e2e-annotations.md`**（用例定义以那边为准）。本计划的测试矩阵一律按 **Python runner** 书写，不写 Node `webServer` 语法 |
| **#19** | HIGH | 4A.2 先迁 settings、4A.3 才建共享模块，会被迫先写临时代码再重构 | **已处置**：4A 顺序改为 `4A.0 → 4A.1 → 4A.3 → 4A.2 → 4A.4`，对应 WI-9 → WI-10 → WI-11 → WI-12 → WI-13，共享模块在设置页之前 |

评审原文里的裸 `S1`–`S5` 与已删除的 `tasks/014` 路径按当时原样保留，不追改。

### 6.1 从 009 E2E 特征化继承的生产缺陷（2026-09-04）

`009-e2e-annotations` 在写 baseline 特征化用例时实测撞出五条，**定义处是
[`tasks/009-e2e-annotations.md`](../20260816-tech-stack-migration/tasks/009-e2e-annotations.md)
的跨波欠账表**（本表只做指针与落点，不复述现象——一个事实一个定义处）。

009 是**安全网分支，不改行为**（该文件 §0.5），所以这五条一条都没在那边修。它们的兑付方是本计划。

| 009 欠账 | 严重度 | 一句话 | 本计划的落点 |
|---|---|---|---|
| **#22** | HIGH（用户可见） | 字号 / 段落间距的第一次点击对正文**毫无效果**：`applySettings()` 跑在 `saveSettings()` 之前，而 `buildContentCss()` 回读 `localStorage`，于是注进 iframe 的永远是上一档的值 | **WI-18**。两行的改法（调换顺序，或让 `applyThemeSettings` 收参数而不是回读 storage）。**注意与 #10 的 legacy key 迁移是同一段代码**，一起做。<br>⚠️ 已决定**不等本计划**：009 合并后单开一条小分支先修（见[进度盘](../20260824-frontend-backend-plan-progress.md)），本行届时改为「已由该分支兑付，WI-18 只需复核」 |
| **#21** | MEDIUM | 主题四态（白/黄/护眼/夜间）是**死表面**：四个 `rd-pref-theme-*` 上全仓没有任何监听器，CSS 自带 `cursor: not-allowed`，注释写着 `UI only for v1`。与 `rd-page-prev` / `rd-page-next`（欠账 #11）完全同型 | **WI-18**。要么接上电，要么连同 testid 一起删——留着裸 testid 会让后来的用例作者以为背后有行为。<br>接上电的那天 `R-6a` 的 `theme-four-states` 守卫**会红，那是正确的红**，改法写在该用例的 docstring 里 |
| **#23** | MEDIUM | 多选模式没有视觉反馈：`library.js` 往 `<body>` 加的类是 `select-mode`，样式表写的是 `.selection-mode`，**两个名字对不上**，复选框只在 `.book-card:hover` 时才露出来 | **WI-13**（4A.4 书库页切片）。改一个类名即可，但**哪个名字是设计想要的**属本计划裁定 |
| **#15** | LOW（测试脆性） | 字号 / 间距四个 ± 按钮没有 testid。可访问名是按钮**文本** `−`(U+2212) 与 `+`（accname 里 contents 先于 title），**不是**中文 `title`；且四个按钮两两重名，必须靠容器 testid 限定作用域才不触发 strict mode | **WI-18**，按 [ADR-0014](../../adr/0014-bounded-testid-enumeration.md) 补四个 testid。兑付后 `R-6a` 改用 `get_by_test_id` |
| **#24** | LOW（测试脆性） | 阅读器左栏「回书架」链接没有 testid，只有 `title="Back to Library"`。与 #15 同一脆弱类 | **WI-16**（4B.2 阅读器外壳重写），补 testid 时顺带 |

**这五条对本计划的净影响**：#22 / #21 落 WI-18，#23 落 WI-13，#24 落 WI-16，#15 落 WI-18；
没有一条需要新开工作项，也没有一条改变既有验收门槛——它们是**已有工作项的补充验收条件**。


---

## 7. 性能基线与预算

评审 Section 4 的实测。本节是**基线记录 ＋ 预算**，不是新工作项；每条都指向已有 WI。

### 7.1 首屏字节账（实测）

| 资产 | 字节 | 其中 | 缓存 |
|---|---:|---|---|
| `reader.html` | 63 049 | **内联 CSS 36 617（58.1%）** ＋ 内联 JS 9 995（15.9%） | ❌ 无 |
| `library.html` | 48 793 | **内联 CSS 28 064（57.5%）** | ❌ 无 |
| `settings.html` | 2 555 | 内联 0 | ❌ 无 |
| `vendor/epub.min.js` | 231 094 | — | ✅ |
| `vendor/jszip.min.js` | 97 630 | — | ✅ |
| 其余 JS＋CSS（非 vendor） | 257 450 | — | ✅ |

两个主模板加起来 **111 842 B，其中 64 681 B（57.8%）是样式**。

### 7.2 内联样式的真实成本：换章是整页跳转，且模板不带缓存头

不是「多传一次」，是**每次换章都重传**：

- `templates/reader.html:1728` —— `window.location.href = "/read/{{ book_id }}/" + idx;`
- `static/js/notes-panel.js:131` —— `window.location.href = url;`

TOC 点击与笔记跳转都是**整页导航**，走 `@app.get("/read/{book_id}/{chapter_index}")`（`server.py:488`）重渲染 Jinja 模板。而模板响应**没有任何缓存头**——`server.py` 里 `Cache-Control` / `ETag` / `max-age` 的命中数为 **0**。对比之下 `/static` 是 Starlette `StaticFiles` 挂载（`server.py:93`），默认带 `Last-Modified` ＋ `ETag`。

**所以：一本 30 章的书从头读到尾，那 36 617 B 逐字节相同的 CSS 会被传 30 次；如果它是 `/static` 下的文件，就是 1 次 ＋ 29 次 304。**

> 这条把 §9.1 的 HTML/CSS 分离从「可维护性偏好」抬成**可测的性能修复**。WI-16 验收 14 转绿即兑现，无需额外工作项。
>
> 顺带记一条**不在本计划范围**的：模板响应该带 `ETag`，换章导航该改成客户端 `rendition.display()`（`epub-renderer.js` 已有 4 处 `rendition.display/next/prev`，能力是现成的）。两条都属后端 / 阅读器行为，不属 UI 重构，**留给 011 或单独一条**，此处只记账。

### 7.3 首屏阻塞的远程字体：4 个请求，D5 之后应为 0

| 位置 | 数量 | 阻塞面 |
|---|---|---|
| `templates/library.html:8,9,10` | 3 | `<head>` 内 `<link>`，**阻塞首次绘制** |
| `templates/reader.html:9,10,11` | 3 | 同上 |
| `static/js/epub-renderer.js:186` | 1 | 注入 **iframe 内**，阻塞正文渲染 |

一个自托管、主打离线的 EPUB 阅读器，在画出第一个像素之前要先问 Google 的 CDN 要字体。D5 已裁决系统 serif 字体栈、不打包任何字体文件，**归零由 WI-18 验收 10a–10f 兑现**（其中 10a 的全仓库 grep 覆盖 `library.html` 那三条，不只阅读器）。此处只记性能账：这是当前首屏延迟里最大的一笔纯浪费。

### 7.4 CI 运行时预算

- 规模：**121 个唯一 `F*` ID**，叠加 §5.1.0 的八状态展开与 009 已有的 `R/W/K/X`。
- 并行度：`pytest -n 4`，per-worker 隔离（§5.0）。**注意 `pytest-xdist` 当前不是依赖**，WI-9 负责补。
- 服务器进程：session fixture 级，**不是每用例一个**——每 worker 一个，共 4 个。
- 参照点：当前 unit lane 50 passed / **1.36 s**。E2E 的量级完全不同（每条要起浏览器页、渲真 EPUB），**本计划不承诺具体墙钟数**——CI 还不存在（`.github/` 目录不存在），没有可外推的基线。首条流水线跑通后回填此处。

### 7.5 `dist/` 提交进 git 的代价（记账，决策不变）

决策是「产物落 `static/dist/` 并提交进 git，不在 CI 里现构建」（WI-9）。性能账：

- `.git` 当前 **22 MB**。
- 一代 `dist/` 的量级：以现有非 vendor JS＋CSS 的 **251 KB** 为代理。
- Vite 产物带内容哈希 ⇒ **每次重建都产生新 blob，旧 blob 永不回收**。100 次前端提交 ≈ 25 MB 死 blob，仓库翻倍。

决策不改（现构建会把 Node 拖进每条 CI，代价更大），但**必须带缓解**，落 WI-9：

- 前端分支**只在合并前重建一次 `dist/`**，中途提交不带产物；分支内用 `git checkout --ours` 或直接不追踪。
- 前端分支一律 **squash merge**，避免中间态产物进主干历史。
- CI 加一条 `git diff --exit-code src/reader3_app/web/static/dist/`（重建后无差异），防止源码改了忘记重建——这条同时是 WI-9 验收 2「两次构建字节一致」的运行时对应物。

### 7.6 明确**不在**本计划范围的性能项

写下来是为了别让人以为重构会顺带解决它们：

| 项 | 现状 | 为什么不在范围 |
|---|---|---|
| `vendor/` 321 KB（epub.min 231 ＋ jszip 97） | 占 JS＋CSS 总字节 **56%** | 是 epub.js 的既定成本；本计划不换渲染引擎 |
| `search_service.py` 421 stmts、`vector_search.py` 138 stmts | 0% 覆盖 | 后端，归 011 |
| `@lru_cache(maxsize=10)` 缓存 `book.pkl`（实测单本 752 KB ⇒ 上限约 7.5 MB 常驻） | 合理 | 不动 |
| 模板 `ETag` ／ 客户端换章 | 缺失（见 §7.2） | 后端 ／ 阅读器行为，留给 011 或单独一条 |

---

## 8. 本轮工程评审的产出

本节由 `/plan-eng-review`（2026-08-18）落地。上面 §1–§7 的改动是评审的**结果**；本节记录评审的**账**：
已有什么、明确不做什么、以及从四段评审里抽出来的可执行任务。

### 8.1 已经存在的东西（不要重复造）

评审时实测过的现状，写在这里是为了防止实施阶段把「已有」当成「待建」。

| 类别 | 已有 | 证据 | 状态 |
|---|---|---|---|
| Python 测试执行器 | `pytest` 9.1.1 ＋ `pytest-cov` 7.1.0 ＋ `pytest-playwright` 0.9.0 ＋ `hypothesis` | `pyproject.toml` dev group | ✅ 可直接用 |
| 测试目录骨架 | `tests/unit/`（5 个文件、50 条用例、1.36s 全绿）、`tests/fixtures/{bookdir,epub_builder}.py` | 实跑 | ✅ |
| 覆盖率配置 | `[tool.coverage.run] branch=true source=["src/reader3_app"]` | `pyproject.toml:48` | ✅ |
| TDD 门槛配置 | `.claude/tdd-guardian/config.json`：unit / e2e 两条 lane，lines 70 / branches 60，`coverageMode: no-decrease` | 同左 | ✅ 已配，但门槛高于现状 9% |
| 静态资源缓存 | `/static` 由 Starlette `StaticFiles` 托管，自带 `ETag` / `Last-Modified` | `server.py:93` | ✅ 免费拿到（模板没有，见 §7.2） |
| 书本缓存 | `@lru_cache(maxsize=10)` | `server.py:129` | ✅ 不动 |
| 原型 | React 18 ＋ 浏览器内 Babel，六屏可跑，交互状态机已验证 | `designs/reader-pro-next/` | ✅ 当**可执行规格**用，不移植 |
| 契约文档 | 标注宿主契约 K1–K6 | `contracts/annotation-host-contracts.md` | ✅ |
| SVG 图标 | 生产 `reader.html` 已在用 | — | ✅ 比原型的 emoji 先进，别倒退 |

**反过来，实测确认「不存在」的**（这些是真正的从零建）：

| 缺失 | 证据 | 归属 |
|---|---|---|
| JS/TS 测试宿主 | 无 `package.json`；`vitest\|jest\|jsdom` 全仓库 0 命中 | WI-9（本轮裁决） |
| `pytest-xdist` | `grep -c xdist pyproject.toml uv.lock` → 0, 0 | WI-9 |
| CI | `.github/` 目录不存在 | 008 |
| `tests/contract/`、`tests/e2e/` 的内容 | 目录在，是空的 | 008 / 009 |
| 暗色模式 | `prefers-color-scheme\|data-theme\|data-reading-theme` 在**全部**样式文件（含活的 `dedao-theme.css`）里 0 命中 | WI-10 —— 按**新建**排期，不按迁移排期 |
| 前端测试覆盖 | 0% | WI-9 起 |

### 8.2 明确**不在**本计划范围

性能项的清单在 §7.6，不重复。此处是全局范围边界：

| 项 | 为什么不做 | 谁做 |
|---|---|---|
| 换渲染引擎（epub.js → 别的） | 321 KB vendor 是既定成本；换引擎会同时推翻 CFI 锚定与 §6.0 三重断言 | 无人；不做 |
| 引入前端框架（React/Vue/Svelte） | migration plan 已定「TypeScript ＋ Vite 多页、无框架」；原型的 React 只是规格载体 | 无人；不做 |
| 后端分层、存储格式、API 冻结 | 归 011 / 012 / 008 | 迁移侧 |
| 分支编号分配 | 唯一分配处是 `plan-tech-stack-migration.md` §9 | 迁移侧 |
| 像素级视觉回归（截图 diff） | REG-1 用 computed-style 快照，不是截图比对——截图对字体渲染与滚动条敏感，会在 CI 上假红 | 无人；不做 |
| 服务端渲染 / 路由改造 | 换章仍走整页导航（`reader.html:1728`）；改成客户端换章是行为变更，不是重构 | 留给 011 或单开一条 |
| `specs/_archive/` 里的任何东西 | 已冻结，代码是权威 | 无人；不做 |

### 8.3 实施任务清单（ET-1 – ET-20）

从四段评审抽出、可直接开工的条目。JSONL 机读版见
`~/.gstack/projects/anzchy-reader3-pro/jackcheng-007-hygiene-and-contracts-eng-review-tasks-20260818-154636.jsonl`。
测试计划全文见同目录 `…-eng-review-test-plan-20260818-152045.md`。

| ID | 任务 | WI | 严重度 | 依赖 |
|---|---|---|---|---|
| ET-1 | 建 `package.json` ＋ Vitest ＋ jsdom 测试宿主 | WI-9 | 🔴 CRITICAL | — |
| ET-3 | REG-1 回归基线四项建立并转绿（**模板改动前**） | WI-9 | 🔴 CRITICAL | ET-1 |
| ET-2 | `pytest-xdist` 进 dev group | WI-9 | HIGH | — |
| ET-4 | 模板内联 `<style>`=0 的 lint ＋ `<script>` 白名单 | WI-9 | HIGH | ET-1 |
| ET-9 | `escapeHtml` 收敛为单一 `escape.ts` | WI-11 | HIGH | ET-1 |
| ET-12 | `library.html` 1075 行内联样式迁出 ＋ 删 `search.css` | WI-13 | HIGH | ET-3, ET-4 |
| ET-14 | `anchoring.ts` 五函数按纯函数／DOM 适配器两类做单测 | WI-14 | HIGH | ET-1 |
| ET-15 | `reader.html` 1403 行内联样式迁出 | WI-16 | HIGH | ET-3, ET-4 |
| ET-16 | 远程字体归零（7 处引用，4 处阻塞首屏） | WI-18 | HIGH | — |
| ET-17 | 裁决 `Modal` 选型 | WI-6 | — (已闭) | 2026-08-20 裁定原生 `<dialog>` ＋ `showModal()`，已回写 spec §5 组件表与 §11.2 R8 |
| ET-5 | 删六个 CSS 孤儿 ＋ `pagination.js`（1920 行） | WI-9 | MEDIUM | ET-3 |
| ET-6 | 删除前眼过 `library.css` 10 个 ＋ `ai.css` 2 个未匹配 class | WI-9 | MEDIUM | — |
| ET-8 | `dist/` 仓库增长三条缓解 | WI-9 | MEDIUM | — |
| ET-10 | 44 处 `console.log` 换 `debug.ts` 分层 | WI-11 | MEDIUM | ET-1 |
| ET-11 | `settings.html` 内联样式归零（防回潮） | WI-12 | MEDIUM | ET-4 |
| ET-13 | `commands.ts` DOM 禁令改 ESLint `no-restricted-globals` | WI-14 | MEDIUM | ET-1 |
| ET-18 | ~~定 `--r3-text-quiet` 合规值 ＋ 补 §3.3 对比度表~~ | WI-10 | — (已闭) | 2026-08-23 裁定：删 `--r3-text-quiet`；`--r3-text-subtle` 提到 `--p-gray-550` `#707070`（亮）/ `#7a8aa2`（暗），`sepia`/`green` 的 `--r3-page-quiet` 提到 `#7a6449`/`#506856`；`--r3-text-disabled` 标记为 WCAG 1.4.3 豁免。已回写 spec §3.2/§3.3/§3.4。WI-10 直接照 spec 建 token 层 |
| ET-19 | 把规格 §3.5 的 z-index 与动效 token 实现进 WI-10 的 token 层 | WI-10 | MEDIUM | **必须在 WI-10 之前**；WI-16 的三覆盖层几何门槛依赖层级 token。⚠️ 规格 §3.5 已于 2026-08-20 落地（z-index 九档有序枚举 ＋ 动效三档时长与三条缓动 ＋ `prefers-reduced-motion` 单点降级），本条不是「去写规格」，是「把已写好的 §3.5 落成 Tier 2 定义」 |
| ET-7 | 修 `CLAUDE.md:158/161/166` 过期条目 | WI-9 | LOW | ET-5 |
| ET-20 | 修 `spec:541` 的「唯一一个存储 key」错误证据 | WI-10 | LOW | — |

**关键路径**：ET-1 → {Track D 实现类, ET-3} → ET-3 → 所有模板改动。ET-3 未绿之前，
WI-12 / WI-13 / WI-16 不许开工（已写进 WI-9 验收第 10 条）。

> 此前这条路径漏了 **Track D 对 ET-1 的依赖**。按 §4.0，WI-1–WI-8 的**实现类**验收要 DOM、计算样式、
> `sessionStorage` 与 Vitest，全部依赖 ET-1 建的测试宿主——它们和 ET-3 一样挂在 ET-1 下面，不是
> 一条独立起跑的支线。
>
> **Track D 的定义类不在这条关键路径上**：文案、状态枚举、tone 映射、testid 清单、对比度硬约束、
> token 取值裁定都是文档级交付，**可与 ET-1 并行**，也正是 012 写朴素横幅时唯一要消费的那一半
> （§3.1）。把定义类挂到 ET-1 后面，等于让 012 白等一个它不需要的测试宿主。

未决项与尚未回写的编辑另见同目录 [`TODOS.md`](TODOS.md)。

---

## GSTACK REVIEW REPORT

**Skill**: `/plan-eng-review` · **分支**: `007-hygiene-and-contracts` · **日期**: 2026-08-18
**评审对象**: `spec-frontend-design.md` §1–§11 ＋ `plan-frontend-ui-refactor.md` WI-1–WI-20 ＋ 前端测试矩阵（全量）

| Run | Section | Status | Findings |
|---|---|---|---|
| 1 | Architecture | ✅ 完成 | 8（2 CRITICAL / 3 HIGH / 3 MEDIUM）—— 双轴主题作用域、`auto` 语义、FOUC 脚本豁免、token 两层、原型翻译规则 |
| 2 | Code Quality | ✅ 完成 | 6（1 HIGH / 4 MEDIUM / 1 LOW）—— 1920 行死代码、`escapeHtml` 四份实现、44 处 `console.log`、HTML/CSS 未分离、`commands.ts` 验收不可机验 |
| 3 | Tests | ✅ 完成 | 5（1 CRITICAL / 2 HIGH / 2 MEDIUM）—— TS 测试宿主是闭合空指针、`pytest-xdist` 缺失、覆盖率 9%／前端 0%、REG-1 回归基线缺失、矩阵条数记错（174 → 121） |
| 4 | Performance | ✅ 完成 | 6（2 HIGH / 3 MEDIUM / 1 LOW）—— 内联样式随整页导航重复下载、7 处远程字体阻塞首屏、`dist/` 进 git 的膨胀账、CI 运行时预算 |
| — | Outputs | ✅ 完成 | `TODOS.md`（T-1–T-10）、任务 JSONL（ET-1–ET-20）、测试计划工件、§8 三节、本报告 |

**回写**：计划 1283 → 1576 行（＋293）。新增 WI-9 §9.1／§9.2、§5.0 执行器裁决、§5.10 REG-1、§7 性能基线，
以及 WI-10/11/12/13/14/16 的验收补强。

**REGRESSION RULE**：已满足 —— REG-1 写进 §5.10，列为「不可跳过」的关键要求，并由 WI-9 验收第 10 条设为
WI-12 / WI-13 / WI-16 的开工闸门。

### VERDICT

四段评审全部完成，结构性缺陷已收口并回写。计划可进入实施，原有的一处未决裁决已于 2026-08-20 闭合。

**RESOLVED DECISIONS:**

- **`Modal` 选型（原生 `<dialog>` vs `div[role=dialog]`）**
  - **背景（评审时原文）** —— `spec-frontend-design.md:728` 仍标为「尚未裁决」。它决定焦点陷阱、Escape 分层与 `inert` 的实现方式，**阻塞 WI-12 与 WI-6**；对应任务 ET-17，背景见 `TODOS.md` T-4。
    - **当前位置** —— 上面那个行号是评审当日的原文，规格此后已增长，`spec-frontend-design.md:728` 不再是这段内容。该裁决现记在 `spec-frontend-design.md` **§11.2 R8**，按章节号找，不要按行号找。
  - **裁决（2026-08-20）** —— **用原生 `<dialog>` ＋ `showModal()`**，`div[role=dialog]` 落选。当初倾向 `div` 的理由（「`<dialog>` 的 Esc 拦不住、遮罩点击关不掉」）经核实不成立：`cancel` 事件可 `preventDefault()`，遮罩点击本就不是原生行为。`showModal()` 另外免费提供 top layer（解掉 K3 的 `position: fixed` 隐患）与原生焦点陷阱 ＋ 兄弟节点 `inert`，比 `div` 少写代码。
  - **落点** —— 裁决正文在 **WI-6** 的「三个落地细节」第二条，新增验收 10（`tagName === "DIALOG"` 且 `open` 为真）与验收 11（祖先 `transform` 下仍相对视口居中）；**WI-12** 与 WI-6 共用同一个 `Modal` 组件；ET-17 严重度改 `— (已闭)`，WI 列指向 WI-6。规格侧 §5 表与 `spec:728` 由同一次裁决回写。

**UNRESOLVED DECISIONS:** 无。
