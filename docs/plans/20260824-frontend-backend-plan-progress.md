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
| **2** | `009-e2e-annotations` | Phase 1b | 后端 | **✅ 已合入 `master`**（2026-09-05，PR #20，合并 commit `b0b4a3a`），**G1 达成 → Phase 4A 解锁**。`baseline_1b` **66 条**全绿，验收三组 **17 条** skip 形态就位，`tests/e2e` 全量 **90 条**（73 passed + 17 skipped，约 58s）。三条 lint rc=0；unit + contract **1043 条**绿；覆盖率 lines 79.94% / branches 67.70%。`src/` 净改动 3 文件 +69/−35，**已全部有测试钉住**（#60 由 X-2d 收口，见 tasks/009 合入记录）。**G2 已于 2026-09-06 达成**（连绿三次，`suite_hash` 冻结在 `2747100dadf6`，台账首行落账；「先修 #22 再冻结」的顺序照办） | [tasks/009](20260816-tech-stack-migration/tasks/009-e2e-annotations.md) |
| **2.5** | `016-settings-apply-order` | M1b 欠账兑付 | 后端 | **✅ 已合入 `master`**（2026-09-06，PR #21，合并 commit `770e5ca`）。欠账 **#22** 已修（`applyThemeSettings` 收参数，渲染器不再回读 localStorage），并修掉同一病根的第二个入口（越界值只被外层挡住：面板 17px / 正文 **99px**、行高 **891px**）；审计 **#51** 的可失败性证据改用 `page.route` 重做，`src/` 一行未动。`baseline_1b` **67 条**、`tests/e2e` **91 条**、三条 lint rc=0；`suite_hash` `e7e0f9626df5` → `8f39737ca0c6` → **`2747100dadf6`**。**这是 G2 冻结前的最后一次覆盖面变更，冻结值即此** | [tasks/009 欠账 #22](20260816-tech-stack-migration/tasks/009-e2e-annotations.md) |
| **3** | `011-backend-refactor` | Phase 2a+2b | 后端 | **🚧 进行中**（2026-09-07 开工，2026-09-18 复核；分支上 **5 个提交**，已 rebase 到 `master`、0 behind）。**Phase 2a，未进 2b。** **已完成 WI-0（a＋b 两层接缝守卫）／ WI-2（`bench.py`）／ WI-3（`book_store.py`）**；另有**两项计划外**：`0c1c8a2`（`criticalPaths` 的 7 条逐文件下限从来没生效过）、`0be2370`（WI-T7 长命服务管道容量闸，见 §4 决策行）。**未做：WI-1 / WI-4 / WI-5 / WI-6 / WI-7 / WI-8 / WI-9。**对照[迁移计划的 Phase 2a 清单](20260816-tech-stack-migration/plan-tech-stack-migration.md)八项：4 项完成 / 4 项待做，**而完成的 4 项里有 3 项（`ai/config.py` 原子写、CJK/Anthropic 路由启发式、CLAUDE.md 宪法修订）是 011 开工前就已完成的**——011 自己推进的 Phase 2a 项目前只有 `book_store.py` 一项，WI-0 与 WI-2 是前置工装、不在那张清单上。**剩下的重头是 WI-4 拆 router**：`src/reader3_app/web/` 下至今没有 `routers/`，`server.py` 实测 **2979 行**（计划 `:275` 写的 `~2,400 行` 已烂，涨了约 24%，而拆分门槛是每个 router < 500 行）。**⚠️ 本格此前长期停在「⬜ 任务书已写」，与实际差 5 个提交**；按 §0 的规则权威在 `plan-and-branch-map` 的里程碑表，**那边 `SKILL.md:78` 今天仍写着 `Tasks drafted`，同样过期，需要一并修**——SKILL.md 自己的 `:89` 正好记着 009 当年「六个提交还读作 Tasks drafted」是同一个毛病。实测发现计划的 Phase 2a 清单**九项里三项已完成**（`ai/config.py` 原子写、CJK/Anthropic 路由启发式、CLAUDE.md 宪法修订）**、一项前提失效**（`_Reader3Unpickler` 早已收敛进 `safe_pickle`，`vector_search.py` 根本没有 loader —— 真正要合的是两个**同名不同签名**的 `load_book_cached`）。顺序：**WI-0 打桩接缝守卫必须先于任何一行路由搬家**（70 处 `monkeypatch.setattr(server, …)`，拆分后会静默失效，而 `server._call_provider` 是本进程通往 LLM 的唯一出口）→ WI-1 对齐权威文件 → WI-2 修坏掉的 `bench.py` → WI-3 `book_store.py` → WI-4 按关切拆 router。**`max_retries` 的「删或接」被 ADR-0011 削成只剩「接」**（删它 = 改响应形状 = Phase 2 窗口内非法）；**C5 裁决推迟到 012**。全部 WI **零触碰**冻结的 8 条路径，soak 计数不受影响 | [tasks/011](20260816-tech-stack-migration/tasks/011-backend-refactor.md) |
| **⟂** | `010-design-degradation-states` | Track D | **前端** | **⬜** WI-1 – WI-8 已定义 | [前端计划 §4](20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md) |
| **4** | `012-storage-format` | Phase 3 | 后端 | **⬛** 计划未写 | — |
| **5** | `013-ts-frontend-shell` | Phase 4A | **前端** | **⬜** WI-9 – WI-13 已定义 | 前端计划 §4 |
| **6** | `014-ts-frontend-reader` | Phase 4B | **前端** | **⬜** WI-14 – WI-19 已定义 | 前端计划 §4 |
| **7** | `015-launch-experience` | Phase 5 | 后端 ＋ **前端** | **⬛ / ⬜** CLI 侧未写；PWA 侧是 WI-20 | 前端计划 §4 |

**⟂ = 可随时插入**，不占顺位。

### 现在该做什么

> **当前位置：顺位 3 / `011-backend-refactor` / Phase 2a。** 顺位 0–2.5 全部在 `master` 上；
> 顺位 4 之后（`012` / `013` / `014` / `015`）与 ⟂ 的 `010` **一个分支都还没开**。
>
> **⚠️ 本节此前写死过派生值，已在 2026-09-19 整段重写。** 原文是「今天 3 次、跨度 0 ——最早解锁
> **2026-09-11**」。那两个数与那个日期全部到期变烂，而且后者会把读到的人引向「还要再等」这个
> 错误结论。`soak-log.md` 表头早在 `16f7c1f` 就改成了**只留算法、不留当时的那个答案**，本节
> 当时漏改。**下面一律给命令，不给数。**
>
> **每天要做的一件事：往 soak 台账追一行。** `uv run python scripts/soak_run.py --append`，约 57 秒。
> 忘一天不清零，只是把日历那一半往后推。**次数好补，跨度补不回来。**
>
> **Phase 3 今天没有解锁，而卡住它的不是次数。** 三件事要分开看：
>
> 1. **次数与跨度**——判据是 ≥10 次且 ≥5 个工作日，跨度按台账首行与第十行算，唯一定义处是
>    [迁移计划 §7](20260816-tech-stack-migration/plan-tech-stack-migration.md)。**怎么数**见
>    [`soak-log.md`](20260816-tech-stack-migration/tasks/soak-log.md) 表头的两条命令，本文不复述、不抄结果。
> 2. **这批数据买到了什么，没买到什么（2026-09-18 复核）**——字面判据满足了，但要知道分布：
>    用 `grep -E '^\| 20[0-9]{2}-' …/soak-log.md | cut -c3-12 | sort | uniq -c` 数**不同日历日**。
>    复核当天的实况是 10 行只落在 **3 个不同日历日**上，其中 6 行是五分钟内连跑出来的。
>    §7 自己写着跨度条款的目的是「逼出时间维度的不稳定……这类问题在同一天连跑十次是照不出来的」
>    ——**所以次数这一栏是过了，它想买的东西只买到一半**。补法是往后每天真的追一行，让不同日历日涨上去。
> 3. **三条机制挑战闸（§7 `:501-503`，全部阻塞 Phase 3，且不计入那 10 次）：复核时 0 / 3。**
>    干净 Linux/CI 环境 · CPU 压力下 · 随机化 pytest 收集顺序。
>    **其中第一条今天做不了**——全仓 workflow 没有任何一步跑 Playwright，已立
>    [跨波欠账 #31](20260816-tech-stack-migration/tasks/009-e2e-annotations.md)，兑付方**待定**，
>    先要裁的是「建一个 CI e2e job」还是「显式接受缺口、把 §7 那句承诺删掉」。
>    **这条裁决挡着两样东西**：机制挑战闸的第一项，以及那 10 次绿的证明力补全。
>
> **一句话：想让 Phase 3 动起来，该做的不是再跑十次 soak，是去做那三条闸、并裁掉 #31。**
>
> **冻结生效中，代价自 2026-09-06 起是实的。** `suite_hash` 冻结在 `2747100dadf6`。再动
> `baseline_1b/**` / `tests/e2e/conftest.py` / `helpers.py` / `test_harness_smoke.py` /
> 那四个 fixture 里的**任何一个字节**（连 docstring 都算，#51 那次就是现成例子），
> 台账全部作废、从零重数。**011 / 013 随便改，那些不在覆盖面里**——这正是 P-3 采纳 C 方案
> （soak 与 011 同期跑）能成立的原因。
>
> <details><summary>起跑之前的那场权衡（已兑现，留档）</summary>
>
> 起跑前这里写过一句「起跑早比起跑晚划算，前提是你确实不打算再改这套用例了」，括号里补的是
> 「已知会碰它的只有欠账 #22 那条小分支（改的是 `src/`，不碰用例）」。
>
> **⚠️ 那个括号是错的，2026-09-04 当天订正。** #22 **一定会碰用例**，而且碰的正是 `baseline_1b` 里的文件：R-6a 为绕开
> 这个「慢一拍」缺陷，把「一档」的刺激构造成了**两步**（`−` 再 `+`），两步之后 iframe 停在「差一档」
> 的位置，`stimulus_moves=True` 因此成立。缺陷一修，两步就回到原值、`moved` 变 False、**那条守卫转红**
> ——这是模块 docstring「实测订正三」与本文 2026-09-04 那条决策行早就写明的「正确的红」，我此前把它
> 漏读成了「不碰用例」。改 `test_read_presentation_anchoring.py` 就是改覆盖面内的文件，**suite_hash
> 变、soak 计数按 §7 清零**。
>
> **所以顺序是被这条事实定死的：先修 #22，再冻结起跑。** 反过来做，等于先花 ≥5 个工作日攒计数，
> 再用一次两行的修复把它清零。
>
> **这条顺序 2026-09-06 全部照办**：009 合入（PR #20）→ 016 修 #22 与 #51（PR #21）→ 连绿三次
> → 首行落账、冻结。#22 的真修法与「两行修复」的预估不同（渲染器回读 localStorage，不是
> `applySettings` 的调用顺序），但顺序的结论不变，因为它照样要改 `baseline_1b` 里的文件。
>
> </details>
>
> **G1 同时解锁了 013（Phase 4A）**——它要的是 G1 不是 soak，可与 011 / 012 交错。**G1 于 2026-09-05 达成，至今 `013-ts-frontend-shell` 分支仍未创建、零提交**（`git branch -a | grep 013-ts-frontend-shell` 无输出）。同样零提交的还有 ⟂ 的 `010`——它是纯文档，本可在任意低能耗 session 插入。**这两条支线被解锁之后一直空着，是当前进度里最便宜的一块未动产。**
>
> **Wave 7 已于 2026-09-04 收口，八波编排结束**：验收组 17 条 skip 用例（4b1 8 / p3 4 / 4a4 4 /
> 2a 1）、`lint_e2e_groups.py` 分组守卫、`soak_run.py`、共用 DEG 断言体。常量全部由预估改实测并
> 相互派生（65 / 17 / 7，合计 89 = 实测收集数），欠账 #2 与 #14 结清。**本波录到全支唯一一次真红**
> （99 条里 37 条失败，`assertion-failure`），verify 判 `SEPARATION-HELD`；前六波是特征化用例，
> 红在结构上不可得，只能靠定向破坏作证。**并修掉了 G2 判据里的一处死锁**（见下面 2026-09-04 的
> 决策行），那处不修，soak 会永远开不出绿灯，且失败形态与「还没开始数」完全同形。
>
> **Wave 6 已于 2026-09-04 收口**：X-1 四条落地，桩是 ollama 形状（只有它在服务端逐块推），
> X-1a′ 用握手把「浏览器先渲染出首块、上游才发末块」变成可判定的因果断言。两处实测订正写进了
> 任务书 §6 X-1 行：未建索引的书走**整句子串匹配**（新欠账 #26，指向 011），以及 `done` 后
> 引用页脚追加在同一节点里。
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
> 定义在 `scripts/lint_e2e_groups.py`）。进度按条目计：**实测 65**（Wave 6 后，22 个编号全部落地）。
> **61 是 09-01 矩阵按 41 个测试函数推算的预估，已把 X-1 算在内**；各模块参数化条数在实现中漂移，
> Wave 5 收到 61 只是碰巧等于常量，不是「收齐」。把常量改成实测值并加「实测 == 常量」断言被
> **故意**推迟到 WI-17——每个 WI 都去加一次常量，那个脚本就成了 13 条 WI 的串行写入点，
> 并行当场作废。不要顺手把它提前。
>
> **已完成**（Wave 0–4）：基础设施与台账（五个 marker 家族、`soak-log.md`）、harness 自测、
> **全部写路径** W-1…W-10、核心路径 K-1a/K-2/K-6a、**全部读路径** R-1…R-6a、书架往返与集合
> X-2a/b/c，以及 Wave 3.5 的 helper 上收（`reader_frame` / `pathname_is` / `scan_marks` /
> `mark_id_union`，兑付欠账 #13）。R-6b 的三条以 skip 形态落在 `acceptance_4b1`，等欠账 #6。
> `suite_hash` 当时为 `b509a1235914`，处于 pre-freeze。（**这是 Wave 4 当天的快照，不是现值**：
> 此后经 Wave 5–7 与两次冻结前修复，已于 2026-09-06 冻结在 `2747100dadf6`。
> 现值与变更史的唯一定义处是 [`soak-log.md`](20260816-tech-stack-migration/tasks/soak-log.md) 表头。）
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
uv run pytest tests/e2e --collect-only -q -m baseline_1b -p no:cacheprovider | tail -1   # 应为 65/89（24 deselected）
uv run python scripts/lint_e2e_groups.py   # rc=0 才算数；它把三条轴（划分律／条数／skip）一次跑完，
                                           # 常量 65 / 17 / 7 与派生总数 89 都在它的摘要行里，别再手抄分母
grep -c '^| ~~\*\*Wave' docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md  # 已收口的波次数（共 8 波：0–7）
grep -c '未结清' docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md          # 跨波欠账未结清行数

#   011 既没有 checkbox 也没有 pytest item 数可数——**它的完成状态今天只能从 git log 反推**，
#   因为任务书里只有 WI-2 写了「完成记录」段，WI-0 / WI-3 的代码在分支上但文档里没有对应记录。
#   这是已知缺口（该由 WI-1 一并补上），在补上之前用下面这三条，别指望读任务书能读出进度：
git log --oneline master..011-backend-refactor          # 分支上的提交，逐条对回 WI 号
ls src/reader3_app/web/routers/ 2>/dev/null || echo 'routers/ 不存在 = WI-4 未开始'
wc -l src/reader3_app/web/server.py                     # 拆分门槛是每个 router < 500 行，这是分母

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
| 2026-09-04 | **G2 的「绿」判据订正：`deselected == 0` → `deselected` 恰好等于验收 ＋ 白名单条数（派生，非字面量）**。原文把一个巧合写成了规格——写它时 `tests/e2e` 整棵树都是 baseline，`-m baseline_1b` 恰好 deselect 0 条；Wave 7 落地 24 条非 baseline item 后，soak 真跑必判红，**这道门变成永远开不出绿灯的门，且失败形态与「还没开始数」同形** | [tasks/009 §8 G2](20260816-tech-stack-migration/tasks/009-e2e-annotations.md) |
| 2026-09-04 | **G1 的「并往 `soak-log.md` 记账」取「不落账」解**。该句与台账表头「首行落账之前不构成对 G2 的任何宣称」直接冲突，照字面无法同时满足。G1 要的是**演示得出一次可记账的绿**（`soak_run.py` 不带 `--append`），真写第一行留给 G2 那天——写下去就启动了 §7 的清零时钟 | 同上 §8 G1 |
| 2026-09-04 | **欠账 #19 取「删预言」而非「补用例」**：K4 的 `reader3:chapter:change` 监听可单独剪断而全套件不红（`scheduleRefresh` 冗余接在三个事件 ＋ 一路回调上）。断言某一根具体监听存在等于把冗余布线钉成规格，011 / 014 重写外壳时只会变成假警报。矩阵里那句自检预言已划掉并附证伪记录 | tasks/009 欠账 #19 |
| 2026-09-04 | **欠账 #8（CFI 分支零覆盖）由 WI-17 改派 011 / 014**，与欠账 #6 同一次兑付。它的前置是「#6 修完之后」，而 #6 是生产缺陷、009 全程不动 `src/`——**在 cfi 真的写得进去之前，为死代码补的用例只会锁死死代码的形状** | tasks/009 欠账 #8 |
| 2026-09-04 | 「定向破坏只走 `page.route`，绝不原地改 `src/`」从 009 欠账 #25 上收为工程实践，消费者是 011/013/014（`f27cf5c`） | [迁移计划 §5 工程实践表](20260816-tech-stack-migration/plan-tech-stack-migration.md) |
| 2026-09-18 | **soak 门槛三项复核裁定（R9 之后的再确认）**：① **撤回「`6/35` → 15.3%」这个数**——它拿 Wave 2 的 `live_server` 管道死锁算出「本门槛有约 1/6 概率放过同量级缺陷」，**观察单位错了**：台账 `355afedd106b` 条目原话是「修前 `6 failed, 29 passed in 187.12s`」，那是**一轮运行里 35 条用例中 6 条红**，不是 35 次运行里 6 次红；且该故障是确定性阈值（服务端一轮写 74194 字节 > macOS 管道容量 65536 字节），记录自己写着「**用例数是引爆它的量而不是它的因**」，不是每轮 17.1% 的随机失败。该概率论证作废。② **维持 ≥10 / ≥5 不改，跨度算法也不改**——Codex 建议改成「至少在 5 个不同工作日各有一次成功」，否决：它声称「成本不变」是错的（现规则按台账首行与第十行算，第十行今天落地即成立；改成它那样最少还要 5 个工作日，对一个自 09-07 起已空转 11 天的项目是实打实的日程成本），且该数值是 R9 的用户裁定项。③ **拒绝「持续 flake 记录管线」**——Codex 建议每次 push 自动落结构化 flake 记录并按最近 20 次判定，否决：它依赖**尚不存在的 CI e2e**（全仓 workflow 无任何一步跑 Playwright，见依据列 §7），且对 6–10 小时/周的单人项目过重；采纳的是它另外两层——流程闸（跑完 10 次）＋ **机制挑战闸**（§7 新增，三项阻塞 Phase 3） | [迁移计划 §7](20260816-tech-stack-migration/plan-tech-stack-migration.md)／[`soak-log.md`](20260816-tech-stack-migration/tasks/soak-log.md) |
| 2026-09-18 | **`011` rebase 到 `master`**（`6459af7` → `1be7387`）。此前 `master` 上的三条 docs 提交没有带到分支上，而全仓**没有任何先例**——历次分支的 merge-base 显示 `master` 在它们存活期间从未前进过，所以「照旧」在这里没有可照的旧。选 rebase 不选 merge 的理由：分支当时未推、零文件重叠、且不想给一条纯文档同步留一个合并提交。**两路独立验证**：旧尖→新尖的 diff 恰好等于 `master` 那三条（10 文件 / 111 insertions）；分支自身净 patch 的 `shasum` rebase 前后一致（`99ba7061…`）。**⚠️ 前提此后失效**：`origin/011-backend-refactor` 已于 2026-09-18 20:46 被推送，再 rebase 就是 force-push，代价不同了 | 本文 §2 顺序图的 011 那一行 |
| 2026-09-18 | **计划外 `0c1c8a2`：`criticalPaths` 的 7 条逐文件覆盖率下限从来没生效过。** `.claude/tdd-guardian/config.json` 里写的是裸 `"branch": N`，而 `coverage.js` 读的是 `thresholds.branches`——配置解析不到，7 条下限一条都没参与判定，门禁长期报绿。修后加到 8 条并做了双向验证（把某条地板抬到 99 → 当场 FAIL） | `011` 分支 `0c1c8a2` |
| 2026-09-18 | **计划外 WI-T7：给「长命服务不得把 stdout 接进管道」建类级闸。** 起因是核查发现[欠账 #10](20260816-tech-stack-migration/tasks/009-e2e-annotations.md) 虽标「已结清」，但结清判据是 `pytest tests/e2e` 全绿——**一条载荷相关的判据守一条载荷相关的缺陷，等于没建回归闸**；且同类缺陷在 `scripts/smoke_installed_wheel.py` 有**第二个现场**，由 `1392b1f`（2026-08-23）带进来、比 #10 建账还早，只因该脚本只打 4 个路由、写不满 65536 字节而一直没发作。闸走 AST，判据是「起 `reader3-server` 类长命服务 ＋ `stdout=PIPE`」而非「用了 PIPE」（`soak_run.py:322` 用 PIPE 但全程 `communicate` drain，必须放过）。**红收据判 `SEPARATION-BROKEN`**：绿之后主动移除了 9 行已录断言——初版把参数化钉成 `(文件, 行号)`，该设计在同一个工作项里就烂了一次，改为只钉文件。新记欠账 **#32**（本条的账）与 **#33**（`log_tail()` 无测试，未结清） | `011` 分支 `0be2370`；tasks/009 欠账 #32 / #33 |
| 2026-09-18 | **欠账 #31 落号**：§7 承诺过的「发版关门检查跑一次 `baseline-1b` 全量」从来没建出来，逐文件复核 `.github/workflows/` 证实全仓无 Playwright / 无 e2e job。**兑付方写「待定」是刻意的**——先要裁的不是谁做，而是「建 CI e2e job」还是「显式接受缺口并从 §7 删掉该承诺」。**此裁决未做，它挡着机制挑战闸的第一项** | `master` `8fcc940`；[迁移计划 §7](20260816-tech-stack-migration/plan-tech-stack-migration.md) |
| 2026-09-19 | **本看板整体对账**：顺位 3 由「⬜ 任务书已写」改为「🚧 进行中」并写入实测；「现在该做什么」整段重写、删掉写死的派生值（3 次 / 跨度 0 / 2026-09-11）；§3 补 011 的核对配方。**遗留一处未修**：权威侧 `SKILL.md:78` 仍写 `Tasks drafted`，按 §0 的规则应以它为准，所以本看板现在「对得比权威准」——需要同步修那一行，否则下次复核会按规则把本文改回错的 | 本文 §0 / §1 |

> **来源**：2026-08-24 与 Codex（`gpt-5.6-terra`）的一次定向复核。Codex 选 C 并提出五条风险，
> 其中三条经核对成立并已回写（见上表后两行）；两条不成立——它担心 010 的九条门槛「形式完成、
> 实际无用」，但 D-3/D-4/D-5/D-6 定义的正是 Phase 3 消费的 DEG-S1–S4，且 Phase 3 出口写死
> 「`acceptance-p3` 组解开 skip 并绿灯」；它担心 4A.4 的验收主观，但该出口同样写死为
> 「`acceptance-4a4` 组解开 skip 并绿灯」，是二值的。**记在这里，免得下次复核重提。**
