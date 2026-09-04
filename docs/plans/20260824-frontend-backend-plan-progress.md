# 前后端计划执行进度看板

> **建于 2026-08-24，起因是 007 合入后「下一步做什么」没有唯一答案。**
> 依赖图（谁等谁）一直有定义，但**顺序**（先做谁）没有——依赖图允许多种合法顺序，
> 它们的代价并不相同。本文把顺序定下来，并附上裁定理由，免得每次开新分支都重推一遍。

---

## 0. 权威范围

**本文定义的事实（别处不得重述，只能链接过来）：**

| # | 事实 |
|---|---|
| P-1 | **分支的实际执行顺序**，以及每一步为什么排在那个位置 |
| P-2 | **009 harness spike** 这个动作的存在与位置（它不是任何计划里的既有工作项） |
| P-3 | **soak 与 011 同期跑**的裁定，及其已知代价 |

**本文只镜像、不定义的事实**（下表的「状态」列是镜像，权威在右列；两边不一致时**以右列为准**，并回来修本文）：

| 事实 | 唯一定义处 |
|---|---|
| 分支编号、归属哪份计划 | [`plan-tech-stack-migration.md` §9](20260816-tech-stack-migration/plan-tech-stack-migration.md) |
| 每个分支的完成状态 | [`plan-and-branch-map` skill](../../.claude/skills/plan-and-branch-map/SKILL.md) 的里程碑表（2026-09-01 `d11da98` 从 `CLAUDE.md` 搬出，按需加载） |
| 每个分支内部的逐项 ✅ | `20260816-tech-stack-migration/tasks/{分支}.md`（后端）／前端计划 §4 的 `### WI-N:`（前端） |
| 阶段进入／退出门槛 | [`plan-tech-stack-migration.md` §7](20260816-tech-stack-migration/plan-tech-stack-migration.md) |
| 依赖图（谁等谁） | 同上 §9.1 |
| soak 次数、跨度、台账字段、清零规则 | 同上 §7 的 soak 小节 |
| **当前对外发布版本** | `pyproject.toml` 的 `version` ＋ 同名 git tag（两者必须一致）；发版本身只在下面 §4 记一笔，**不进状态板**——发版与分支顺位是两条互不从属的轴 |

---

## 1. 状态板

**图例**：✅ 完成并合入 · 🔨 分支上完工、未合入 · 🚧 进行中 · ⬜ 未开工（有计划）· ⬛ 未开工（计划都还没写）

| 顺位 | 分支 | 阶段 | 计划归属 | 状态 | 展开在哪 |
|---|---|---|---|---|---|
| **0** | `007-hygiene-and-contracts` | Phase 0 | 后端 | **✅** 2026-08-24 合入（PR #18） | [tasks/007](20260816-tech-stack-migration/tasks/007-hygiene-and-contracts.md) |
| **1** | `008-test-safety-net` | Phase 1a | 后端 | **✅** 2026-08-26 合入（PR #19） | [tasks/008](20260816-tech-stack-migration/tasks/008-test-safety-net.md) |
| **1.5** | *(009 harness spike)* | — | — | **✅** 2026-08-26 完成（`36a6ac2` 落在 `master`，lint 收尾 `7ed87e1`） | 本文 §2 的 P-2 |
| **2** | `009-e2e-annotations` | Phase 1b | 后端 | **🚧** 2026-09-04：Wave 0–5 完成。写路径 W-1…W-10、读路径 R-1…R-6a、核心 K-1a/K-2/K-3/K-6a、书架往返 X-2a/b/c 全部落地，`baseline_1b` **61 / 61 条**（`tests/e2e` 全量 71 条 = 68 passed + 3 skipped，约 53s）。`src/` 一行未动。剩 Wave 6（WI-16，X-1 AI 流式）与 Wave 7（WI-17，skip 形态 ＋ 分组守卫），G1 在 Wave 7 之后 | [tasks/009](20260816-tech-stack-migration/tasks/009-e2e-annotations.md) |
| **3** | `011-backend-refactor` | Phase 2a+2b | 后端 | **⬛** 计划未写（故意，见[迁移计划 §9](20260816-tech-stack-migration/plan-tech-stack-migration.md)） | — |
| **⟂** | `010-design-degradation-states` | Track D | **前端** | **⬜** WI-1 – WI-8 已定义 | [前端计划 §4](20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md) |
| **4** | `012-storage-format` | Phase 3 | 后端 | **⬛** 计划未写 | — |
| **5** | `013-ts-frontend-shell` | Phase 4A | **前端** | **⬜** WI-9 – WI-13 已定义 | 前端计划 §4 |
| **6** | `014-ts-frontend-reader` | Phase 4B | **前端** | **⬜** WI-14 – WI-19 已定义 | 前端计划 §4 |
| **7** | `015-launch-experience` | Phase 5 | 后端 ＋ **前端** | **⬛ / ⬜** CLI 侧未写；PWA 侧是 WI-20 | 前端计划 §4 |

**⟂ = 可随时插入**，不占顺位。

### 现在该做什么

> **在 `009-e2e-annotations` 上开 Wave 6：WI-16（X-1 AI SSE 流式，含桩 provider），独占。**
> 它是唯一被授权改 `tests/e2e/conftest.py` 的一条（桩 provider 的 server env）；conftest 是
> session 级 fixture 的定义处，改它会影响同时在跑的每一条用例，所以不并行。`acf7ccf` 已把
> 服务子进程的 AI 配置路径钉在沙箱内，WI-16 在此之上接桩即可。
>
> **Wave 5 已于 2026-09-04 收口**：K-3 六条落地，`baseline_1b` 到达 **61 / 61**。两处实测订正
> 写进了 tasks/009 §4 的 K-3 行：三个浮层是 `<body>` 的直接子元素而非 `rd-shell` 的后代，
> 「给 `rd-shell` 加 transform 必红」这个纸面配方不成立、要加在 `<body>` 上；`smoke_data`
> 的选区中心 x ≈ 130 落在 clamp 带内，几何三条改用 `repeat_data`。欠账 #25 的 helper 上收
> 同批兑付。
>
> **009 合并之后先插一条小分支修欠账 #22**（2026-09-04 裁定）。字号 / 段落间距的第一次点击对正文毫无效果——`applySettings()` 跑在 `saveSettings()` 之前，而 `buildContentCss()` 回读 `localStorage`。**用户可见、改动两行**，不值得等整个 4B.3（前端计划 WI-18）。放在 009 之后而不是插进 009，是因为 009 是安全网分支、不改行为（`tasks/009` §0.5）；分支号按 [§9 的规则](20260816-tech-stack-migration/plan-tech-stack-migration.md) 在开分支当天分配，现在不预留。修完 `R-6a` 的 `stimulus_moves` 守卫会红，那是**正确的红**。
>
> 波次编排的唯一定义处是 [tasks/009 §0.6](20260816-tech-stack-migration/tasks/009-e2e-annotations.md)，
> 本文不复述编排理由，只记进度与下一步。
>
> **两个数不要混。** `baseline_1b` 有 **22 个用例编号**（§2 的 R-1…R-6、§3 的 W-1…W-10、
> §4 的 K-1a/K-2/K-3/K-6a、§6 的 X-1/X-2）和 **61 个参数化条目**（`EXPECTED_BASELINE_ITEMS`，
> 定义在 `scripts/lint_e2e_groups.py`）。进度按条目计：**55 / 61**。
> 「实测 == 61」这条断言被**故意**推迟到 WI-17——每个 WI 都去加一次常量，那个脚本就成了
> 13 条 WI 的串行写入点，并行当场作废。不要顺手把它提前。
>
> **已完成**（Wave 0–4）：基础设施与台账（五个 marker 家族、`soak-log.md`）、harness 自测、
> **全部写路径** W-1…W-10、核心路径 K-1a/K-2/K-6a、**全部读路径** R-1…R-6a、书架往返与集合
> X-2a/b/c，以及 Wave 3.5 的 helper 上收（`reader_frame` / `pathname_is` / `scan_marks` /
> `mark_id_union`，兑付欠账 #13）。R-6b 的三条以 skip 形态落在 `acceptance_4b1`，等欠账 #6。
> `suite_hash` 现为 `b509a1235914`，处于 **pre-freeze**——**G2 的 soak 计数尚未开始，首行
> 落账之前台账不构成对 G2 的任何宣称。**
>
> **Wave 4 实测订正了欠账 #15，也记下三处生产行为。** 字号 / 间距 ± 按钮的可访问名是按钮
> **文本** `−`（U+2212）与 `+`，不是中文 `title`（accname 里 contents 先于 title），且四个按钮
> 两两重名，所以限定容器是正确性要求而非讲究。新记欠账：主题四态是死表面（#21）、字号与
> 间距传到 iframe 里**晚一拍**导致第一次点击对正文毫无效果（#22，用户可见）、多选模式类名
> 与样式表对不上（#23）。
>
> **Wave 3.5 顺带清掉了一处挡在 Wave 4 前面的 flaky。** 该模块修前约四成概率红，根因是一次
> 页面加载会跑**两遍** `loadAndRender()`，第二遍的 `normalize()` 会折叠测试刚装上的选区。
> 判据由「等 `<mark>` 数量」换成「等网络静默」后，全量连绿 9 轮（末两轮 CPU 打满）。
> **这必须先清**：Wave 4 要同时开三个 agent，并行只会加剧争用，三份验证跑各自随机见红。
> 代价是全量耗时 24.51s → 约 42s。详见欠账 #16 / #17。
>
> **Wave 4 的三条**同样只加用例、无共享写入点：WI-13（R-4/R-5）、WI-14（R-6）、WI-15（X-2）。
> 纪律 3 仍然生效——写用例可以并行，**跑门禁必须串行**（`state.json` 与 `receipts.json`
> 是全局可变状态）。
>
> **Wave 2 撞出两个生产缺陷，都只记录未修**（1b 是安全网，不是行为变更窗口）：`cfi` 恒为
> `null`（锚定实际 100% 走文本路径），以及**改色 wavy/underline 会静默丢数据**。两条都在
> tasks/009 的欠账表里（#6、#9），兑付方是 4B.1 / 前端 WI-14。**#9 会挡住 W-5b 解 skip**，
> 排 4B.1 时要把它算进去。
>
> **Wave 3 又撞出两条，同样只记录未修**：`rd-page-prev` / `rd-page-next` 是**死表面**
> （基础样式即 `display: none`，唯一绑定在 `reader.html` 不加载的 legacy `js/pagination.js` 里，
> 点它只会等到 actionability 超时）；以及**站内导航时 URL 落后于渲染**（`syncLocationToUrl()`
> 跑在 epub.js 的 `rendered` 回调里，先断 URL 的用例读到的是陈旧状态——WI-12 的定向破坏实测
> 到了这一点）。两条落在 tasks/009 欠账表 #11、#12，配套的 helper 上收欠账是 #13。

---

## 2. 执行顺序（P-1 / P-2 / P-3，本文定义）

### 顺序

```
007 ✅
 └─> 008 ─────────────────┐
      └─ 009 harness spike │
           └─> 009 ────────┤
                 └─ G2 达成，soak 开始计数 ──┐
                                            │
             011 ────────────────────────────┤  ← soak 与 011 同期跑
                                            │
010 （纯文档，任意低能耗 session 插入）───────┤
                                            ▼
                                          012 ─> 013 ─> 014 ─> 015
```

> `013` 可与 `011`／`012` 交错（它要的是 1b 的 **G1**，不是 soak）。
> **`012` 与 `014` 严格串行**，不可交错——这条是依赖图的硬约束，不是本文的选择。

### 为什么 008 在 009 前面（P-1）

三个候选顺序，全部满足依赖图，代价不同：

| | 主张 | 结论 |
|---|---|---|
| **A** | 009 先跑，因为 soak 是唯一买不回来的日历时间 | **否决** |
| **B** | 008 先跑，因为 009 太大、且没有单测网就写 E2E 等于用没验过的脚手架保护重构 | 部分成立 |
| **C** | 008 先，009 紧随，**soak 与 011 同期跑** | **采纳** |

**否决 A 的决定性理由**（不是「011 反正要几周」那个估算，那个只是辅助）：

> soak 门槛的原文出处是 §4 论证 1——「在一套**已经跑绿一段时间**的 E2E 下迁移」。
> 要迁移的是 **011 之后**的代码。把 soak 整段排在 011 前面，攒到的是「011 之前那套后端很稳」
> 的证据，而 Phase 3 要动的根本不是它。**A 的前提在这里被掏空。**
>
> 换个说法：**soak 不是一段可以预付的等待，它是对某一份特定代码的观察。预付了不算数。**

辅助理由（来自 Codex，2026-08-24 复核）：008 小得多且直接开关键路径；单人 part-time 做完
`008 → 011` 极可能是数周量级，远超 soak 的 5 个工作日下限，**所以 soak 初期根本不是约束**。

### 为什么要插一个 009 harness spike（P-2）

**这是 A 和 C 都缺的东西，两边的最强反对意见都指向它**：009 是全程序最大的一块，
而它变绿需要多久是**全程序最大的未知**。把这个未知留到第二顺位才暴露，是不必要的风险。

> **spike 的范围**：只建 Playwright ＋ ~~`webServer` 探针~~ **拉真服务的 fixture**
> （打 `/api/health`，0.3 已交付）＋ **一条** smoke。
> **不写用例清单，不建分组，不建台账。**
> **它要回答的唯一问题**：Playwright 在这个仓库能不能稳定起来、单次冷启动多久。
>
> **落点**：~~`008` 分支上，或紧随其后的一次独立小提交~~ → 008 于 2026-08-26 合入之后，
> 落点相应改成 **`master` 上的一次独立小提交**。**不占顺位，不算 009 开工。**

> ⚠️ **`webServer` 这个写法在 2026-08-26 被实测推翻。** 它是 `@playwright/test`（Node）的
> 配置键，本仓库用的是 `pytest-playwright`，**没有这个东西**。实际形式是一个拉子进程的
> pytest fixture（`tests/e2e/conftest.py` 的 `live_server`）——之所以必须是子进程而不是
> `TestClient`，是因为 `BOOKS_DIR` 在 `server.py` 里是 import 期读的模块级常量。
> **裁定本身（「插一个 spike」）不受影响，被推翻的只是它的形式**；原词划掉留在上面，
> 是为了让下次读到的人知道这里踩过一次。

> **✅ 已完成（2026-08-26，落在 `master` 的 `36a6ac2`，lint 收尾 `7ed87e1`）。**
> 回答是「能起，而且很快」。冷启动与端到端 lane 的耗时见
> [tasks/009 的「harness spike 的结论」](20260816-tech-stack-migration/tasks/009-e2e-annotations.md)——
> 那里是这两个数字的唯一定义处，本文不重述。
>
> **spike 的额外产出**：它顺带证伪了 009 骨架 §1 的一条基础设施前提，并撞出两类硬阻塞
> （见上面的「现在该做什么」）。**这正是插 spike 的理由在事后被兑现**——把「009 变绿要多久」
> 这个最大未知留到第二顺位才暴露，暴露出来的会是同样两条，只是那时已经开工了。

### soak 与 011 同期跑：已知代价（P-3）

**接受，写下来，不当它不存在：**

> `011` 是全程序里最可能把 `baseline-1b` 弄红的东西，而清零规则是
> 「任何一次红清零重计，flaky 与 broken 不做区分」。**让 soak 与 011 重叠，等于把计数窗口
> 放进了最容易被清零的时段。**
>
> **这不是疏漏，是选择**：被 011 弄红的那次红是**真实信号**——它说明重构改变了可观测行为，
> 而 2a 的退出门槛写着「行为不变」。清零在这里是门槛在正常工作，不是门槛在添乱。
>
> **代价的量化下限**：最坏情况下 soak 要重数若干轮，Phase 3 因此推迟。
> **缓解手段只有一个**：011 分小步走，每步跑一次 `baseline-1b`，让红出现得早、范围小。

---

## 3. 怎么自己核对状态（不要信本文，去数）

```bash
# 某个分支开了没有
git branch -a | grep 009-e2e-annotations

# 某个分支合入 master 了没有（输出 0 = 已全部在主干上）
git rev-list --count master..008-test-safety-net

# 后端分支的逐项进度——**记账形式因分支而异，别套错配方**：
#   007 / 008 用 checkbox（008 有 10 条）
grep -c '^\- \[x\]' docs/plans/20260816-tech-stack-migration/tasks/008-test-safety-net.md
grep -c '^\- \[ \]' docs/plans/20260816-tech-stack-migration/tasks/008-test-safety-net.md
#   009 的用例表没有状态列，checkbox 数恒为 0——对 009 跑上面两条会得到 0 / 0，
#   那是「配方不适用」，不是「没进度」。009 的进度按 pytest item 数：
uv run pytest tests/e2e --collect-only -q -m baseline_1b -p no:cacheprovider | tail -1   # 分子；分母 61 在 scripts/lint_e2e_groups.py
grep -c '^| ~~\*\*Wave' docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md  # 已收口的波次数（共 8 波：0–7）
grep -c '未结清' docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md          # 跨波欠账未结清行数

# 前端工作项清单
grep -n '^### WI-' docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md

# soak 进度（台账建起来之后）
grep -cE '^\| 20[0-9]{2}-' docs/plans/20260816-tech-stack-migration/tasks/soak-log.md 2>/dev/null || echo '台账尚未建立（009 的 G2 产物）'   # 数据行数；0 = 已建账未开始计数

# CI 最近一次运行（CI 仅在发版与手动 workflow_dispatch 时触发）
gh run list --limit 5
```

---

## 4. 决策记录

| 日期 | 决策 | 依据 |
|---|---|---|
| 2026-08-24 | Phase 0 关闭，007 合入 `master`（PR #18，合并 commit `3f63135`） | [tasks/007 的「合入记录」](20260816-tech-stack-migration/tasks/007-hygiene-and-contracts.md) |
| 2026-08-24 | 采纳顺序 C：008 → 009 → 011，soak 与 011 同期 | 本文 §2 |
| 2026-08-24 | 新增 009 harness spike，落在 008 上 | 本文 §2（P-2） |
| 2026-08-24 | soak 台账扩到八列；新增 `suite_hash` / `browser` / `os` 三类清零触发器 | [§7 的「台账字段（canonical）」](20260816-tech-stack-migration/plan-tech-stack-migration.md) |
| 2026-08-24 | 009 的退出条件拆成 G1（用例完成）/ G2（基线稳定）两道门；soak 从 G2 起算 | [tasks/009 §8](20260816-tech-stack-migration/tasks/009-e2e-annotations.md) |
| 2026-08-26 | 008 分支上完工：十条退出门槛全达成 | [tasks/008 §9](20260816-tech-stack-migration/tasks/008-test-safety-net.md) |
| 2026-08-26 | 网建好之后对它自己做审计，71 条 High 结清（69 修 / 2 误报）**在 008 分支内**修完，不再转交 009 | [tasks/008 §8.5](20260816-tech-stack-migration/tasks/008-test-safety-net.md) ／ `.claude/tdd-guardian/dispatch-order.md` |
| 2026-08-26 | Phase 1a 关闭，008 合入 `master`（PR #19，合并 commit `8a9b3aa`） | [tasks/008 的「合入记录」](20260816-tech-stack-migration/tasks/008-test-safety-net.md) |
| 2026-08-26 | **顺位 1.5 的 harness spike 完成**（`36a6ac2`，lint 收尾 `7ed87e1`）：Playwright 在本仓库能稳定起来，冷启动与 lane 耗时均在可接受范围 | [tasks/009 的「harness spike 的结论」](20260816-tech-stack-migration/tasks/009-e2e-annotations.md) |
| 2026-08-26 | spike 证伪 009 骨架 §1 的 `webServer` 前提，改为拉子进程的 `live_server` fixture；**本文 §2 的 P-2 同步更正** | 本文 §2（P-2）／[tasks/009 的「现状实测」](20260816-tech-stack-migration/tasks/009-e2e-annotations.md) |
| 2026-08-26 | spike 撞出 009 的两类硬阻塞（testid 重名 · K1 两个宿主无 testid），**列为 009 开工的头两件事，排在写用例之前** | 同上「现状实测」／本文 §1「现在该做什么」 |
| 2026-08-26 | 发布 **v1.5.0**（tag `v1.5.0`，`881b7f9`）——007＋008 两阶段成果的第一次对外发版 | [Release v1.5.0](https://github.com/anzchy/reader3-pro/releases/tag/v1.5.0)／`pyproject.toml` |
| 2026-08-31 → 09-01 | **ADR-0014** 立项并落地（`9ce4397` → `c127b17`）：有界集合各持唯一 testid，复合选择器收回给无界 id 独用；009 的两类硬阻塞由此解除，唯一性检查进真浏览器（`225966c`） | [ADR-0014](../adr/0014-bounded-testid-enumeration.md)／[tasks/009 的「现状实测」](20260816-tech-stack-migration/tasks/009-e2e-annotations.md) |
| 2026-09-01 | **W-5 拆成 W-5a / W-5b**（`1b3d9be`）：1b 只特征化今天的三岔行为，真正的改色归 4B.1 以 skip 形态写；`tests/fixtures/epub_corpus.py` 纳入 `suite_hash` 覆盖面 | [tasks/009 §3 / §8](20260816-tech-stack-migration/tasks/009-e2e-annotations.md)／[迁移计划 §7](20260816-tech-stack-migration/plan-tech-stack-migration.md) |
| 2026-09-02 | 1b 基础设施落地（`0e411f8`）：五个组 marker ＋ `--strict-markers`、组目录用 `.gitkeep`、`soak-log.md` 建账（pre-freeze）、`select_in_frame` 标准路径；**G2 补「绿」的判据**（`passed == EXPECTED_BASELINE_ITEMS` 且其余四计数为 0）与 commit 级禁 skip 护栏 | [tasks/009 §0.5 / §1 / §8](20260816-tech-stack-migration/tasks/009-e2e-annotations.md) |
| 2026-09-03 | 009 剩余 WI 按 **八波编排**（Wave 0–7，`d0335a5` 起）：并行上限 3、共享文件授权制、写用例并行跑门禁串行；跨波欠账单开一张表 | [tasks/009 §0.6](20260816-tech-stack-migration/tasks/009-e2e-annotations.md) |
| 2026-09-03 | **R-6 拆成 R-6a / R-6b**（`4ed7dff`）：`cfi` 今天恒为 `null`（欠账 #6），CFI 侧锚定归 4B.1 以 skip 形态写 | [tasks/009 §0.5 / §2](20260816-tech-stack-migration/tasks/009-e2e-annotations.md) |
| 2026-09-04 | Wave 4 收口（`f518be3`）：`baseline_1b` 55 / 61 条。撞出的五条生产缺陷（#15 / #21 / #22 / #23 / #24）**只记录不修**，兑付方写进前端计划 §6.1；#18（集合名连字符）指向 011 | [tasks/009 跨波欠账](20260816-tech-stack-migration/tasks/009-e2e-annotations.md)／[前端计划 §6.1](20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md) |
| 2026-09-04 | **009 合并后先插一条小分支修欠账 #22**（用户可见、两行改动），不插进 009；分支号开分支当天分配（`f27cf5c`） | 本文 §1「现在该做什么」 |
| 2026-09-04 | 「定向破坏只走 `page.route`，绝不原地改 `src/`」从 009 欠账 #25 上收为工程实践，消费者是 011/013/014（`f27cf5c`） | [迁移计划 §5 工程实践表](20260816-tech-stack-migration/plan-tech-stack-migration.md) |

> **来源**：2026-08-24 与 Codex（`gpt-5.6-terra`）的一次定向复核。Codex 选 C 并提出五条风险，
> 其中三条经核对成立并已回写（见上表后两行）；两条不成立——它担心 010 的九条门槛「形式完成、
> 实际无用」，但 D-3/D-4/D-5/D-6 定义的正是 Phase 3 消费的 DEG-S1–S4，且 Phase 3 出口写死
> 「`acceptance-p3` 组解开 skip 并绿灯」；它担心 4A.4 的验收主观，但该出口同样写死为
> 「`acceptance-4a4` 组解开 skip 并绿灯」，是二值的。**记在这里，免得下次复核重提。**
