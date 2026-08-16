# 010-design-degradation-states —— 任务

- **对应阶段**: Track D（设计补齐）
- **进入条件**: Phase 0 完成。见 `docs/plans/20260816-tech-stack-and-ui-changes/plan-ui-migration-sequencing.md` §9.1
- **退出条件**: S1–S5 设计完成并回写设计规格 §6.4；合同 2 剩余两项收口；loading 骨架屏补齐。见合流计划 §7
- **下游**: **Phase 3**（技术栈计划 Phase 3 的退出门槛要求 S1–S4 在 UI 里可见，S1–S5 的原型是本轨产出）；Phase 4A.4 与 4B.2 消费改版形态
- **改动范围**: **只改 `designs/reader-pro-next/` 与 `spec-frontend-design.md`**。不碰 `src/`、不碰 `templates/`、不碰 `static/`

> **引用规则**：用**符号名**与 **CSS 选择器**定位，不写代码行号。

---

## 0. 这个分支的性质

**纯设计分支，没有一项适合交给 `/tdd-guardian:workflow`。** 产出是原型 JSX、CSS 与规格文本，没有可先写的失败测试——"横幅长得对不对"不是断言能回答的问题。S1–S5 的**可测试性**由本轨产出的 testid 承接，真正的断言写在 009 的 `acceptance-p3` / `acceptance-4a4` 两组里，那是别的分支的事。

本轨唯一的机器可验项是 §5 的 testid 命名 lint，而那条 lint 属于 0.5，已在 007。

**这个分支为什么排在 011 前面**：它不在关键路径上，但它是 Phase 3 的前置。§9.1 写得很清楚——「1b 与 Track D 要在 Phase 0 一结束就动，不能排到 2a/2b 之后」。后端一路推到 Phase 3 门口才发现 S1–S5 还没画，是这份计划点名的失败模式。

---

## 1. 原型现状实测（2026-08-16）

补齐 S1–S5 之前先知道手里有什么。**五个状态一个都没有**，但可复用的地基不是零：

| 已有 | 位置 | 能不能直接用 |
|---|---|---|
| `LiveRegion` | `components.jsx`，`role="status"` + `aria-live="polite"`，testid `live-region` | **只能当播报器**。它是 `sr-only`，没有视觉形态。S1–S4 要求的是**看得见的横幅**，这个组件满足不了 |
| `index-banner` | `reader.jsx` 的搜索面板内，testid `reader-index-status` | 视觉上最接近横幅，但**长在搜索抽屉里**、写死了「Semantic index」文案，不是通用组件。可以当视觉参考，不能当基座 |
| collection 级 `stale` | `components.jsx` 的 `.stale-dot` ＋ `app.jsx` 的清理确认框 | 唯一的 stale 先例，**只到集合粒度**。书籍级与全局级全缺 |
| `Modal` | `components.jsx`，testid `modal` | **不能承载 S5**，理由见 §2.5 |
| `STATUS_META` | `components.jsx`，四态（`not_indexed` / `indexing` / `indexed` / `error`） | S2 要加第五态，但它有两个坑，见 §2.2 |

**缺的是一个通用横幅组件。** S1 / S2 / S3 / S4 四条都要它，各自手搓会得到四种间距、四种关闭行为、四种 `aria` 写法。本轨第一件事是把它建起来，而不是从 S1 开始逐条画。

---

## 2. S1–S5 逐条

五条的触发、UI 规格、落点见设计规格 §6.4 的表——**本文不复述那张表**。这里只写那张表没说、而实施时必须先定的事。

### 2.0 先建 `DegradeBanner`（四条的共同基座）

一个组件，四条复用。必须一次定死的：

- **tone 取值**：`warn` / `danger` 两档。S1/S2/S4 用 warn，S3/S5 用 danger（规格 §6.4 设计要求 1）
- **可关闭性**：`dismissible` 布尔。S1–S4 为 true 且写 `sessionStorage`，S5 不走这个组件（它是对话框）
- **可访问性**：`role="status"` + `aria-live="polite"` 挂在组件上，**不复用 `LiveRegion`**——那个是 `sr-only` 播报器，两者职责不同，混用会得到一个既看得见又被朗读两遍的东西
- **主操作插槽**：S2 要「重建索引」、S3 要「展开清单」、S4 要「重试失败项」。三个形状不同，用 children 而不是 `primaryLabel` 字符串

**testid**：容器与主操作按钮各一个，且必须**按状态区分**（`rd-degrade-s1` 而不是共用一个 `degrade-banner`），否则 009 的 `acceptance-p3` 断言不出「出现的是 S1 不是 S3」。

> **⚠️ 色彩 token 在规格里对不上号，本轨要顺手修。** §6.4 设计要求 1 写的是 `--r3-warn` 与 `--r3-danger`，而 §3.3 定义的实际名字是 **`--r3-warning`** 与 **`--r3-error`**——`--r3-warn` / `--r3-danger` 在全规格里不存在。照 §6.4 抄会得到两个未定义变量，CSS 静默回落到继承色，横幅看起来像普通提示。**改 §6.4 去对齐 §3.3**，不要反过来：§3.3 的名字已经被 §3.2 的 palette 层引用。
>
> **同时缺一层底色 token。** §3.3 的 `--r3-warning` / `--r3-error` 是**前景色**，横幅还需要一个淡底。§3.3 里只有 `--r3-accent-subtle` 一个 subtle 变体，warning / error 没有对应的。原型侧已经有 `--danger-bg` / `--success-bg` / `--info-bg` 三个，说明这个需求是真的。**本轨给 §3.3 补 `--r3-warning-subtle` 与 `--r3-error-subtle`**，否则实施者只能硬编码颜色，两层 token 体系在第一个消费者身上就破了。
>
> **夜间态要一并验。** `:root[data-reading-theme="night"]` 那个块重定义了 accent、hl-*、border、shadow，**唯独没有重定义 `--r3-success` / `--r3-warning` / `--r3-error` / `--r3-info`**。amber-500 与 red-500 压在 `#0f0f0f` 上是否满足 §8 要求的 4.5:1，没人量过。量一遍；不达标就在 night 块里补覆盖。

### 2.1 S1 标注 stale（阅读器）

- 文案必须明说「标注暂停套用，**未删除**」——这是规格 §6.4 已定的，照做。理由值得写进设计注释：用户看到高亮消失的第一反应是数据没了，而这条降级恰恰是为了**不删**才存在的
- 「查看原文摘录」入口：摘录数据就是 `Annotation` 的 `quote` / `prefix` / `suffix` 三个字段，它们与 CFI 无关，指纹变了照样读得出。设计上按什么形态展示（内联展开 / 侧栏 / 弹层）本轨拍板
- Notes 面板逐条标记：面板里每条笔记加一个 stale 角标，与横幅是同一状态的两种粒度

### 2.2 S2 索引 stale（书库 ＋ 搜索面板）

书卡第五态。`STATUS_META` 加一项，**两个坑**：

1. **`StatusPill` 的 testid 是拼出来的**——`data-testid={"status-" + props.status}`。加第五态会凭空多出一个 testid，而 0.5 的命名 lint 扫的是**字面量**，拼接的扫不到。两条出路：改成静态映射表（推荐，lint 能看见），或者在 lint 里给这个组件开一条显式例外并写明五个值。**别默认选第二条**——例外一开，以后每个动态 testid 都有先例。
2. **`reader.jsx` 的搜索面板对 `window.STATUS_META[indexStatus]` 取值没有兜底**。后端一旦先于原型发出第五态，这里直接抛。加第五态时**先改 `STATUS_META`、再改任何发出方**，并顺手补一个 `|| STATUS_META.not_indexed` 兜底——`StatusPill` 里已经有这个兜底，搜索面板漏了。

搜索面板顶部的「索引已过期」提示条走 §2.0 的 `DegradeBanner`，不要复用现有的 `index-banner`（那个是常态展示，不是降级）。

### 2.3 S3 pickle 回退告警（全局 chrome）

- 唯一一条**全局**降级：书库与阅读器都要显示。设计上要定它挂在哪——原型的两个页面外壳没有共享的顶部条，本轨要么建一个，要么接受两处各挂一次
- 「点击展开未迁移书目清单」：清单可能很长（全库），要定折叠形态与上限
- tone 是 danger。它不是「有个东西过期了」，它是「你正在用一个已知不安全的反序列化路径」

### 2.4 S4 存储格式 / 迁移进度（书库）

- 书卡 `storage_format` 角标：与 S2 的 `StatusPill` 是**两个独立维度**（索引状态 × 存储格式），别塞进同一个 pill。一本书可以「已索引 ＋ 旧格式」
- 迁移中的进度与失败项：失败项要能**单独重试**，所以每项要有自己的 testid 与按钮，不能只给一个总的「重试」

### 2.5 S5 多标签页写冲突（阅读器）

**这是唯一一条会真正丢用户数据的降级，也是现有 `Modal` 承载不了的一条。**

`Modal` 有三条互不相干的关闭路径，全都绕过「必须做出选择」：

1. header 里写死的 `×` 按钮（testid `modal-close`）
2. `.overlay` 的 `onMouseDown` 背景点击关闭
3. `useFocusTrap(ref, true, onClose)` 的 Esc

加上它把 `role="dialog"` 和 `data-testid="modal"` 都**写死在组件里**——`role` 改不成 S5 要求的 `alertdialog`，testid 也没法与其它弹层区分。

**裁定：S5 不复用 `Modal`，新建 `ConflictDialog`。** 三条关闭路径一条都不给，`role="alertdialog"`，两个按钮（「保留我的」/「采用远端」）是仅有的出口。顺带把 `Modal` 的 `data-testid` 改成可传入——写死一个 `modal` 意味着 E2E 分不清是哪个弹层，这个坑不只 S5 会踩。

> S5 的后端侧（notes 乐观并发、409）在 Phase 2a，与本轨无依赖：本轨只产出 UI 与文案。规格 §9 也是这么分的（S5 → Phase 2a）。

---

## 3. 合同 2 收口（剩余两项）

合流计划 §3 列的两项，实测后发现状态不一样：

| 项 | 规格侧 | 原型侧 | 本轨要做的 |
|---|---|---|---|
| 标注暗色变体 | **已完成**——§3.3 的 night 块已经取了 `--p-hl-*-dk` 四个显式值 | **未改**，仍是 `color-mix` | 只剩原型侧，见下 |
| 原型单层 token 名映射到两层 | 规格已定两层 | 原型仍是 `--canvas` / `--surface` / `--text` / `--anno-*` / `--page-*` | **不在本轨**，落点是 4A.1（合流计划 §3 已这么写） |

**暗色变体这项比合流计划记的要多一层。** 原型里 `color-mix` 有**八处、两个百分比**：`.anno-chip.is-*` 四条用 35%，`.marker.is-*` 四条用 45%。而规格的解决方案只给了**每色一个** `-dk` 值。也就是说「取显式值」这个裁决落到原型上时，chip 那一档没有对应的值——要么再定四个更淡的显式值，要么裁定 chip 与 marker 同色。**本轨拍这个板，并把结果写回 §3.2**，否则 4A.1 落 token 时会自己发明一个。

理由重申一遍（合流计划 §3）：`color-mix` 在旧 Safari 上要 fallback，而这是标注可读性，不是装饰。

---

## 4. loading 骨架屏

原型 README 自己记着：「每个面板需要 loading / error / empty 三态。原型只做了 empty 与 error，**loading 骨架屏未建**」。规格 §5 的组件清单也把 `Skeleton` 标为**不存在**，现状是 `-` 或 `Loading...` 文本。

- 建一个 `Skeleton` 组件，书库卡片与统计数字先用上（§5 点名的两处）
- **尊重 `prefers-reduced-motion`**（§8 要求 5）：骨架屏的微光动效在 reduced-motion 下必须静止，否则它是全站最大的一处持续动画
- 骨架屏**不需要 testid**——它是过渡态，E2E 断言它反而会引入时序 flaky。要断言的是它之后的内容

---

## 5. testid 不在本轨（一处记账已修正）

合流计划 §6「线 3 Track D」原先把「§4.1 的 testid 批量改名」列为本轨产出并注明「喂给 0.5」。**那是重复记账**：0.5 自己的验收就是「134 条违规 → 归零」，且顺序写死为「先改原型、再回贴模板」——改原型那一半就是 0.5 的前半程。两处都声称拥有同一件事，会得到一个假的依赖环（0.5 → Phase 0 完成 → Track D → 0.5）。

**已于 2026-08-16 从 §6 删除该括号。** 本轨与 testid 的真实关系只有一条：**本轨新建的元素要按 canonical 正则命名**——`DegradeBanner` 五个容器、S4 的每项重试按钮、`ConflictDialog` 的两个选择按钮、`Skeleton`（不需要）。正则在合流计划 §6 的 canonical 代码块里，**从代码块复制**。

---

## 6. 退出门槛

- [ ] `DegradeBanner` 建成，S1–S4 四条各自在原型里可见、可截图
- [ ] `ConflictDialog` 建成，三条关闭路径均不存在，`role="alertdialog"`
- [ ] `Modal` 的 `data-testid` 改为可传入
- [ ] `STATUS_META` 第五态落地，`StatusPill` 的 testid 改静态映射，搜索面板补兜底
- [ ] S1–S5 全部回写设计规格 §6.4（表格与五条设计要求同步更新）
- [ ] §6.4 的 `--r3-warn` / `--r3-danger` 改为 `--r3-warning` / `--r3-error`
- [ ] §3.3 补 `--r3-warning-subtle` / `--r3-error-subtle`，night 块的四个状态色验过 4.5:1（不达标则补覆盖）
- [ ] 原型八处 `color-mix` 换成显式值，chip 档的取值已裁决并写回 §3.2
- [ ] `Skeleton` 建成并用在书库卡片与统计数字，`prefers-reduced-motion` 下静止
- [ ] 本轨新建元素的 testid 全部匹配 canonical 正则
- [ ] `src/` / `templates/` / `static/` 零改动（`git diff --stat` 证明）

---

## 7. 下游谁消费什么

| 本轨产出 | 谁消费 | 什么时候 |
|---|---|---|
| S1–S4 的**朴素形态** | Phase 3 退出门槛 | 落到现有 Jinja 模板即可，不要求按本轨设计做完 |
| S2 / S3 / S4 的**改版形态** | Phase 4A.4 | 009 的 `acceptance-4a4` 组解 skip |
| S1 的改版形态 | Phase 4B.2 | |
| S5 的 UI 与文案 | Phase 2a（后端 409 落地时一并接上） | |
| `--r3-*-subtle` 与 chip 档取值 | Phase 4A.1 落 token | |
| `Skeleton` | 各页垂直切片 | |

> **朴素形态与改版形态是两次交付，不是一次。** Phase 3 只要求「看得见」，规格 §6.4 设计要求 5 说的就是这个。本轨产出的是改版形态；朴素形态由 012 自己用横幅糊一版。本轨**不负责**写那一版，但要保证 012 抄得到文案与状态定义。
