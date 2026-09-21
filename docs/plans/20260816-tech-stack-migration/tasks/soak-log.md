# `baseline_1b` soak 台账

> **状态：G2 已达成（达成之日 = 2026-09-06）。计数于 2026-09-21 清零一次，正在重数。**
> `suite_hash` **重新冻结**在 `1e868c7bf811`——覆盖面里再动一个字节，下表全部作废、从零重数。
> 前值 `2747100dadf6` 已作废；作废的理由、被作废的那 10 行、以及为什么这笔代价是有意付的，
> 写在下方「`suite_hash` 的变更史」第一条。**下表现在是空的，这是真实状态，不是漏记。**
> 一个时点上的坑同样写在那一条里：改动今天还在 `011-backend-refactor` 分支上，`master`
> 侧八条冻结路径一个字节没动，所以**正式的清零发生在 011 合入那一刻**；表提前退空，是因为
> 那 10 行已经买不到 Phase 3 的通行证了，留着只会让次数命令数出一个骗人的 10。
>
> **本表头不写派生计数，也不写派生日期——一律现算，以下方数据行为准。**
> 此前这里写死过「门槛进度 4 / ≥10 次，跨度 1 / ≥5 个工作日」与「最早解锁日期是 2026-09-11」，
> 两者都到期变烂；后者还把复核者引到过「还要再等 4 个工作日」这个错误结论上。要留的是**算法**，
> 不是**当时的那个答案**：
>
> - **次数**：`grep -cE '^\| 20[0-9]{2}-' docs/plans/20260816-tech-stack-migration/tasks/soak-log.md`
> - **跨度**：先取首行与第十行的 `ts_utc` ——
>   `grep -E '^\| 20[0-9]{2}-' docs/plans/20260816-tech-stack-migration/tasks/soak-log.md | sed -n '1p;10p'`；
>   **怎么判**不在这里，判据的唯一定义处是迁移计划 §7，本文件只说这两行怎么取。
>
> ⚠️ **次数数满 ≠ Phase 3 解锁。** §7 里另有**机制挑战闸**三项（干净 Linux / CI 环境、CPU 压力、
> 随机化 pytest 收集顺序），三项都是阻塞性的，且**不计入这里的连绿次数**——它们改变了抽样条件。
> 同一节还写了这道门槛的**证明力界定**：它证明的是冻结套件在**一个本地运行剖面**下的成功记录，
> **不构成 flaky 率的统计上界**。两处都在 [迁移计划 §7](../plan-tech-stack-migration.md)，本文件不复述。
>
> 字段定义、清零规则、门槛语义的**唯一定义处**是迁移计划 §7，本文件不复述，只做指针与执行细节
> （另见 [`009-e2e-annotations.md`](./009-e2e-annotations.md) §8）。

<!-- 数据行从 G2 达成当天开始追加，一行一次全量运行，缺一列该行不计数。
     位置有硬要求：**紧接分隔行下方，中间不留空行**。契约测试只解析文件里第一张表的
     连续块，一个空行就把后面的行踢出解析范围——`pre-freeze` 检查会对它视而不见并
     照常报绿，也就是「拿冻结前的绿充数」这条正好检查不到。
     test_no_ledger_row_strays_outside_the_table 就是拦这个的。 -->
| ts_utc | commit | result | duration_s | suite_hash | browser | os | log |
|---|---|---|---|---|---|---|---|

---

## G2 达成记录（2026-09-06）

首行落账的那次运行就是 G2 的达成时刻。为免后人只看到三行绿而不知道它凭什么算「零 flaky」，
把当天的判据与实测一次记全：

| 判据（§8 G2） | 实测 |
|---|---|
| 连续 3 次全量运行无偶发失败 | 上表三行，`result` 全 `green`，无中断、无重跑、无挑选 |
| `passed == EXPECTED_BASELINE_ITEMS` | 67 == 67 |
| `skipped == failed == errors == 0` | 三次均为 0 |
| `deselected == 验收 + 白名单` | 24 == 17 + 7，三次相同 |
| `suite_hash` 三次一致 | `2747100dadf6`，与表头冻结值逐字符相同 |
| `browser` / `os` 三次一致 | `chromium-1234` / `darwin-25.3.0` |
| 单次时长记录在案 | 56.89s / 55.69s / 56.06s（极差 1.20s，约 2%） |

三次都跑在同一个 commit `770e5ca`（PR #21 的合入提交）上。**这不是判据的一部分**——§7 明确
写着「生产代码变（`commit` 变）不清零」，那正是这道门要观察的信号；三行同 commit 只是因为
它们是同一天连着跑的。

**达成之日就是冻结之日。** 从上表首行起，`baseline_1b` 的用例与 harness 进入冻结：
改一条断言、修一条 flaky、动一次 fixture 构造器，`suite_hash` 就变，三行绿全部作废。
冻结前最后一次覆盖面改动是审计发现 #51 的证据重做（见下方变更史第一条），那次连
docstring 都算数——现在这条规则对所有人生效，包括「就改这一点点」。

**冻结之时，覆盖面内没有未处置的 open findings**：覆盖面里剩余的 10 条（#5 与 D7 家族 9 条）
已在 `.cc-suite/audits/audit-20260905-010655-findings.md` 里逐条标注 **ACCEPTED-BEFORE-FREEZE**。
要兑付它们，必须与一次 `suite_hash` 变更一起排期，代价是当时已有的绿行全部清零。

---

## `suite_hash` 的取法

**下面这段是配方的「文档」，不是被执行的代码。** 2026-09-05 之前 `scripts/soak_run.py` 会用正则
把这段围栏块抠出来交给 `bash -c` 跑——那等于「谁能改这份 Markdown，谁就能让 soak runner 执行
任意命令」，审计（gpt-5.6-sol #21）判 High。现在脚本**解析并校验**这段块：拆成 token，比对固定
的管道形状与**有序的八个路径**，任何一处对不上就抛 `HashRecipeError` 拒跑（而不是执行它）；
校验通过后由脚本自己以**参数数组**调 `git ls-files -s -- <paths>` 与 `git hash-object --stdin`，
全程不经 shell。所以：

* 改这段块**仍然**会改变脚本的行为——但只有两种结果：与 `HASH_COVERED_PATHS` 一致（照常算），
  或者拒跑。**没有第三种**，插进来的命令不会被执行。
* 八个路径在代码里也有一份（`soak_run.py` 的 `HASH_COVERED_PATHS`）。那是**第二把钥匙**，
  不是第二个定义处：两边不一致时脚本拒跑，`tests/unit/test_soak_log_contract.py` 也会红。
* 想改覆盖面，两处一起改，并在下面的变更史里记一条。

```bash
# baseline_1b 组用例 + harness 配置 + fixtures 的内容哈希，前 12 位
{ git ls-files -s tests/e2e/baseline_1b tests/e2e/conftest.py tests/e2e/helpers.py \
    tests/e2e/test_harness_smoke.py tests/fixtures/epub_corpus.py tests/fixtures/epub_zip.py \
    tests/fixtures/ai_stub.py tests/conftest.py \
  | git hash-object --stdin; } | cut -c1-12
```

当前 `suite_hash` 值：`1e868c7bf811`（2026-09-21 实测输出，非誊抄：`scripts/soak_run.py`
dry run 在 68/68 green 的那一次同时打印出来的）。
前值 `2747100dadf6` 已作废——见下方变更史第一条。

**这个值已冻结（2026-09-06 G2 达成），不再是 pre-freeze。** 上表首行落账那一刻起，
再改 `baseline_1b` 的用例或 harness，`suite_hash` 就变，已有的绿行全部作废。
下面这段历史保留原样，因为它记的是达成之前的事实——`baseline_1b` 的 22 个用例编号**今天全部落地**，
收集到 **65 条**（以下这段是 Wave 7 当天的快照，`baseline_1b` 此后增至 **67 条**、`tests/e2e`
全量增至 **91 条**，增量见变更史；此处保留原数字是因为它记的是那一天的事实）（WI-3 的 harness 自测 9 条 ＋ WI-4 的创建路径 3 条 ＋ WI-5 的笔记创建/编辑 2 条
＋ Wave 2 的 14 条 ＋ Wave 3 的 18 条 ＋ Wave 4 的 9 条 ＋ Wave 5 的 6 条 ＋ Wave 6 的 4 条；
`tests/e2e` 全量 75 条，差额是 `acceptance_4b1` 的 3 条 skip 与白名单里的 smoke、testid 唯一性）。
~~Wave 7 还要往 acceptance 目录落 skip 用例并写「实测 == 常量」的守卫，acceptance 目录不在覆盖面内，
但守卫若碰 `conftest.py` 就会再变一次。~~ **Wave 7 已收口，那个「再变一次」没有发生**：守卫写在
`scripts/lint_e2e_groups.py` 里，一次也没碰 `tests/e2e/conftest.py` / `helpers.py` / `baseline_1b/**`，
覆盖面内八个路径全部零改动，重算得到同一个 `91de0e171b5c`。写在这里是免得后来者拿今天这个值当冻结值——
**八波都收口了，它仍然是 pre-freeze**：冻结发生在 G2 落第一行账那天，不在用例写完那天。

**「61」是 2026-09-01 矩阵的预估，不是实测。** `scripts/lint_e2e_groups.py` 的 `EXPECTED_BASELINE_ITEMS`
从 WI-1 起就写着 61（矩阵按 41 个测试函数推算的 collected 数，已把 X-1 的 4 条算在内），且**故意**
不随每个 WI 递增——递增会把那个脚本变成 13 路串行写入点，波内并行当场作废。各模块的参数化条数
在实现中漂移（harness 自测 9、W-5a 8、K-2 11 等），所以 Wave 5 收到的 61 只是碰巧等于常量，
**不是「收齐」**；Wave 6 之后实测是 65。~~把常量改成实测值并加「实测 == 常量」断言归 WI-17
（跨波欠账 #2）。~~ **2026-09-04 Wave 7 已兑付**：常量改成实测的 65，条数轴断言落在
`scripts/lint_e2e_groups.py`，实测不等即 rc=1 并把两个数一起印进消息；欠账 #2 结清。

**取值前必须先 `git add`。** 上面这条命令读的是**索引**，不是工作区：新用例文件在 `git add`
之前对 `git ls-files -s` 根本不存在，改过的 `helpers.py` 也仍报旧内容。WI-4、Wave 0、WI-5 三次
都在这里先拿到过一个「没变」的旧值（本次为 `06114374b405` → `6672e32e6687`）。

值的变更史（每次改都要写清作废原因，不要只覆盖数字）：

- **`1e868c7bf811` ← 2026-09-21 修 009 欠账 #9（选区塌陷丢写）并同批兑付一笔 parked 的白名单欠账。
  前值 `2747100dadf6` 作废，连同它下面已经攒够的 **10 行绿账全部作废，计数归零**。**
  - **为什么会变**：覆盖面里动了两个文件。
    1. `tests/e2e/baseline_1b/test_write_recolor_and_delete.py` —— **改判**。W-5a-③（异色重按
       wavy／underline）此前断言的终态是 `EXPECTED_AFTER_RECOLOR_TOGGLE = 0`，即「删了，且没建成」，
       这是 2026-09-03 起挂着的一条**明账偏差**：它断的是缺陷本身，不是矩阵原文的 1。#9 修好之后
       实测 `DELETE 204 → POST 201`，替代性写入真的落盘了，于是改回矩阵原文的 **1**，并把测试从
       `..._destroys_without_replacing` 改名为 `..._replaces_with_a_new_id`。
       **是偏差被注销，不是断言被放宽**——沿革写在该文件的模块 docstring 里。
    2. `tests/e2e/baseline_1b/test_w8a_selection_survives_rerender.py` —— **迁入**。它原先住在
       `tests/e2e/` 根目录并挂在 `lint_e2e_groups.py` 的 `UNGROUPED_E2E_MODULES` 白名单里，
       是 #44 落地时记下的一笔**具名、可到期**的欠账（当时到期条件写的就是「下次 `suite_hash`
       无论如何都要变的那一批」）。这一批正是那一批，所以同批兑付，**省掉第二次清零**。
       `EXPECTED_BASELINE_ITEMS` 67 → **68**、`EXPECTED_UNGROUPED_ITEMS` 8 → **7**、
       `tests/e2e` 全量**仍是 92**（一条 item 换了住址，没有增减）。
  - **为什么这笔代价是有意付的**：备选方案是把塌陷回落撤掉、只留 #44 的上浮回落，这样 W-5a-③
    仍绿、计数保住——代价是**把一个静默的 400 重新装回去**。#9 是真实的用户数据丢失
    （异色重按 wavy／underline，先 DELETE 再重绘再新建，新建那次算出空 quote 被拒），
    而它属于 009 欠账 #43 那一族「静默退出」，正是台账把 CI flaky 归因过去的那一族。
    维护者 2026-09-21 明确选了「全修，接受清零」。
  - **这笔代价的完整账单不止 10 行绿**：按[迁移计划 §7 纪律 4](../plan-tech-stack-migration.md)
    「`suite_hash` 变了就要重跑」，**机制挑战闸三项一并作废**，包括 2026-09-20 已经 PASS 的
    那项 CPU 压力——见下方「机制挑战闸执行记录」。
  - **⏱ 生效时点有个坑，写清楚免得下一个人按错读数。** 改动今天在 `011-backend-refactor`
    上，**`master` 侧的八条冻结路径一个字节没动**（`git diff --stat master..HEAD -- <八条>`
    ＝ 2 文件 / +251 −72，全在分支侧）。按[011 §8 门槛 4 的括号](./011-backend-refactor.md)
    「台账数的是 `master` 上冻结覆盖面的稳定性」，严格读法是：**`master` 的 `suite_hash`
    今天仍是 `2747100dadf6`，那 10 行要到 011 合入才正式作废。**
    - **那为什么现在就退掉它们？** 因为它们已经**买不到任何东西**了。这道门槛存在的唯一
      用途是给 Phase 3 / 012 发通行证，而 012 跑的是**含 011 的**代码库；10 行绿量的是
      一套两文件之后不复存在的用例。留着它们、让次数命令数出 10，只会让人以为门槛这一半
      还过着。**退掉是提前认账，不是提前执行清零**——真正的清零在 011 合入那一刻自动发生，
      不需要谁再动一次手。
    - **万一 011 被放弃**，这 10 行是可复原的：原样存档在下面，且 `647ec8a` 那份文件里
      逐字都在。复原的判据是 `master` 的八条路径重算仍为 `2747100dadf6`。

    - **那 10 行不在本文件里留副本，这是刻意的。** 我原本把它们原样贴在这里存档，
      `tests/unit/test_soak_log_contract.py::test_no_ledger_row_strays_outside_the_table`
      **当场判红**——它认的是「八列形态的行出现在台账表之外」，不管缩进、不管包在不包在
      代码块里。那条闸拦的正是「一条谁也检查不到的记账」，为了存档去绕开它，是拿一道真闸
      换一份 `git` 里本来就有的副本。**取原文用这条命令**（不要手抄，手抄的副本会烂）：

      ```bash
      git show 647ec8a:docs/plans/20260816-tech-stack-migration/tasks/soak-log.md \
        | grep -E '^\| 20[0-9]{2}-[0-9]{2}-[0-9]{2}T'
      ```

      摘要（可核对，不可当数据用）：10 行全绿、全部 `suite_hash 2747100dadf6`、
      全部 `chromium-1234` / `darwin-25.3.0`，时长 55.14–62.66s；落在三个提交上——
      `770e5ca` ×3（2026-09-06）、`c1aa889` ×1（09-07）、`e7c4890` ×6（09-18）。

  - **两种 Range 破坏机制是两回事，一个修不覆盖另一个**（2026-09-21 实测）：#44／W-8a 是
    **上浮**（`replaceChild` 把含端点的节点摘掉，端点按 DOM 规范浮到父元素，`offsetFromNode`
    走元素分支静默返回**错**偏移，不是 `null`）；#9／W-5a-③ 是**塌陷**（`render()` 的
    `normalize()` 把相邻文本节点并成一个，两端点落到同一偏移，节点仍在索引里，所以上浮那道
    `rangeAnchoredIn` 闸根本不会响）。前者问「还在不在」，后者只能问「还有没有宽度」。

- **`2747100dadf6` ← 2026-09-06 审计发现 #51 重做（同分支 `016`，冻结前的最后一次）。前值
  `8f39737ca0c6` 作废。**
  - **为什么会变**：覆盖面里只动了一个文件，且只动了它的 docstring——
    `test_read_presentation_anchoring.py` 的「可失败性证据」一节。R-6a 的 S1 原先是**直接改
    `ensureContentStyles` 生产代码再还原**做的，审计判它证据强度不达标（#51，High、verified）；
    重做成 `page.route` 改写 `epub-renderer.js` 响应体，结论逐字相同，`src/` 一行未动。
    **用例逻辑与条数一个字节没改**（仍 67 条），变的全是记录。
  - **这正是「冻结之后连改 docstring 都要清零」的现成例子**：本次改动不含任何可执行语义，
    哈希照样变。放在冻结前做，是它唯一免费的时机。
  - 同批覆盖面内其余 10 条 open findings（#5 与 D7 家族 9 条）已在
    `.cc-suite/audits/audit-20260905-010655-findings.md` 里逐条标注
    **ACCEPTED-BEFORE-FREEZE**，理由与代价写在那里；要兑付它们必须与一次 suite_hash 变更
    一起排期。**冻结之时，覆盖面内没有未处置的 open findings。**

- **`8f39737ca0c6` ← 2026-09-06 欠账 #22 兑付（分支 `016-settings-apply-order`）。前值
  `e7e0f9626df5` 作废。**
  - **为什么会变**：覆盖面里只动了一个文件——`tests/e2e/baseline_1b/test_read_presentation_anchoring.py`。
    两处改动，必须同一个提交：(1) R-6a 的字号 / 间距刺激从两步（`−` 再 `+`）收回一步
    ——#22 一修，两步就回到原值、净变化为零，`stimulus_moves=True` 反而会红；(2) 新增
    R-6c 一条（`test_r6c_iframe_presentation_agrees_with_the_panel`），钉住 #22 的第二个
    入口：渲染器回读 localStorage 原始值而边界校验只在宿主页，越界值只被外层挡住。
    同波次改的 `scripts/lint_e2e_groups.py`（66→67）与 `tests/unit/test_e2e_group_guard.py`
    （66→67、90→91）**不在覆盖面八个路径里**，不影响哈希；两个 `src/` 文件同理。
  - **`baseline_1b` 67 条 / `tests/e2e` 全量 91 条**，三分律 67 + 17 + 7 = 91 成立。
  - **这次变更仍然是免费的**：台账依旧零数据行，G2 未起跑，改覆盖面不重置任何计数。
  - **「先修 #22 再冻结」这条顺序到此兑付完毕。** 上一条里预告的「哈希还要再变一次」就是
    本次。**冻结当天仍必须重算，永远不要誊抄本行的值**——G2 起跑前若再动覆盖面，本行同样作废。

- **`e7e0f9626df5` ← 2026-09-05 审计发现 #60 收口。前值 `cde2751eb133` 作废。**
  - **为什么会变**：覆盖面里只动了一个文件——`tests/e2e/baseline_1b/test_library_nav_and_collections.py`
    新增 X-2d 一条（`test_x2d_selection_marks_only_book_cards_and_rows_not_status_pills`），
    把 `library.js` 里 `syncSelectionForBookId` 的作用域语义钉住。同波次还改了
    `scripts/lint_e2e_groups.py`（`EXPECTED_BASELINE_ITEMS` 65→66）与
    `tests/unit/test_e2e_group_guard.py`（65→66、89→90），但那两个文件**不在覆盖面八个路径里**，
    不影响哈希。
  - **`baseline_1b` 66 条 / `tests/e2e` 全量 90 条**，三分律 66 + 17 + 7 = 90 成立。
  - **这次变更仍然是免费的**：台账依旧零数据行，G2 未起跑，改覆盖面不重置任何计数。
  - **它不改变「先修 #22 再冻结」的顺序**：#22 仍会动 `test_read_presentation_anchoring.py`，
    哈希还要再变一次。**冻结当天必须重算，永远不要誊抄本行的值。**

- **`cde2751eb133` ← 2026-09-05 审计修复波（commit `fd989f1`）。前值 `91de0e171b5c` 作废。**
  - **为什么会变**：覆盖面八个路径里有 **12 个文件**被 Codex 九维审计的修复动了——`tests/conftest.py`
    （marker 表达式改真解析、提取不出名字时 fail closed）、`tests/fixtures/ai_stub.py`（新增只读
    `bound_host`）、`tests/e2e/helpers.py`（`mark_id_union` 形状守卫、新增
    `wait_for_write_activity_settled`）、`tests/e2e/baseline_1b/` 下 9 个模块（空转判据补断言）。
    **每一处都是把判据改严，没有一处给 soak 放水**；但套件内容变了，`suite_hash` 就该跟着变。
  - **上一条写的「两个文件」是漏计**，写下时另外 10 个还在被并行修改。留着这句是为了记住：
    在一波并行修改**进行中**盘点覆盖面，盘出来的一定偏小。
  - **这次改动是免费的**：上表**零数据行**，没有任何计数被清零。§7 的「`suite_hash` 变了 ⇒ 清零」
    清的是已有的绿行，而现在一行都没有。**同一处改动放到 G2 开始之后做，代价是三次连绿全部作废。**
  - **这个值仍然是 pre-freeze，不是冻结值。** 冻结发生在 G2 落第一行账那天。且按任务书 §8 与
    2026-09-04 的排序裁定，**#22 会碰 `test_read_presentation_anchoring.py`（覆盖面内），所以
    这个值在 #22 收口后还会再变一次**——冻结时必须重算，不许誊抄本行。
- **`91de0e171b5c`（不变）← Wave 7（WI-17）收口。这是变更史上第一条「值没变」的记录，它本身就是证据。**
  - **为什么该不变**：本波产出全在覆盖面之外——验收目录四个（`acceptance_4b1` / `_p3` / `_4a4` / `_2a`，共 17 条 skip 用例）、`scripts/lint_e2e_groups.py` / `soak_run.py` / `e2e_group_probe.py`、`tests/fixtures/deg_assertions.py`（只进验收模块的 import 闭包，不进 baseline 的）、四个 unit 模块。覆盖面内那八个路径一个都没被碰。**`baseline_1b` 一条没加、harness 一个字没动，哈希就该纹丝不动**；它要是变了，说明有人往安全网里塞了东西。
  - **分组守卫落地**：`EXPECTED_BASELINE_ITEMS` 61 → **65**（欠账 #2）、`EXPECTED_ACCEPTANCE_ITEMS` 由 `EXPECTED_ACCEPTANCE_PER_DIR` **派生**得 17（欠账 #14）、`EXPECTED_UNGROUPED_ITEMS` **7**，派生总数 **89** ＝ 实测收集数。三分划分律（每条 item 恰好一个组标记，否则其模块须在白名单里）＋ 条数轴 ＋ skip 轴（`ast.walk` 全模块扫 skip 构造）三条轴独立成立。
  - **定向破坏 3 处，最要紧的是第 2 处**：往 `baseline_1b` 某个用例函数体第一行插 `pytest.skip(...)` —— **条数轴纹丝不动（仍 65/65、89 条），只有 skip 轴响**。这正是 §8 G2 那条「commit 级护栏」担心的形态：给一条不稳的 baseline 用例挂 skip，收集数看不出来，台账的 `result` 列也看不出来。另两处：移走一个 3 条的验收模块（条数轴报出目录名与两个数）、把白名单模块改名（划分律 / 白名单 / 条数三处互相印证，抓出「悬空白名单条目」）。三处均在 scratchpad 的仓库副本上进行，真实树 `git diff --quiet -- src/` 全程通过。
  - **`soak_run.py` 的一处死锁，本波发现并修复**：判据原文（§8 G2）写「`deselected == 0`」，而 soak 发的是 `-m baseline_1b`，Wave 7 之后必然筛掉 24 条 → 真跑得 `65 passed, 24 deselected` → **判红、拒绝记账，且失败形态与「还没开始数」完全同形**。判据改为「`deselected` 恰好等于验收 ＋ 白名单条数」（派生，非字面量 24），多筛少筛仍各自判红。修的是脚本与 §8 的定义处，**红收据 `009-WI-17` 里已记录的断言一行未改**——`test_soak_run.py` 的 `has-deselected` 合成用例（`n-1 passed, 1 deselected`）在新判据下照样红，四条新用例是纯追加。
  - **首次跑出可记账的绿**：`65 passed, 24 deselected in 48.34s`，`verdict: green（可记账：是）`，dry run 未写台账。这满足 G1 的「演示得出一次可记账的绿」（口径澄清见任务书 §8 G1 的 2026-09-04 注），**不等于 G2 开始计数**。
  - **红收据 `009-WI-17`（lane unit）记 `red`，`kind: assertion-failure`（99 条里 37 条失败），verify 判 `SEPARATION-HELD`。这是本支唯一一次真红**——前六波都是特征化用例，红在结构上不可得（§0 第四条），只能靠定向破坏作证。记录的两个文件 `test_e2e_group_guard.py` / `test_soak_run.py` 从此**只能追加**：前者的破坏实录是追加一个同名 `SABOTAGE_LOG` 重新绑定（不就地回填占位符），后者的四条新用例追加在文件尾。
- `91de0e171b5c` ← Wave 6（WI-16）一个新模块 ＋ `tests/e2e/conftest.py` 新增两个 function 级 fixture ＋ 覆盖面**新增一个文件** `tests/fixtures/ai_stub.py`。三个理由各自都足以让旧值作废。
  - **用例增量**：`baseline_1b/test_other_ai_streaming.py`（X-1a 增量渲染且每帧是前缀、X-1a′ 桩侧握手「首块渲染 happens-before 末块发送」、X-1b 终态等值 ＋ 零真实出网 ＋ 引用页脚、X-1c stop 后重发完整收到，共 **4 条**）。baseline_1b **61 → 65 条**，`tests/e2e` 全量 **71 → 75 条**（72 passed + 3 skipped），全量耗时约 53s → **约 58s**。
  - **harness**：`conftest.py` 新增 `ai_stub`（ollama 形状的进程内 NDJSON 桩，127.0.0.1 临时端口）与 `ai_settings_ollama`（在沙箱 `ai_settings.json` 写入 `default_provider=ollama` 指向桩，用完删掉，前后复位 `ai_conversations/`）。`_server_env` 一行未动，其注入的 `READER3_AI_SETTINGS` 路径与 fixture 写的文件在运行期比对相等。**桩必须是 ollama 形状**：`server.py` 只有 `worker_ollama` 逐块推送，其余 provider 走 `worker_non_stream` 把整段答案当一个 `chunk`，浏览器侧 DOM 更新恒为 1 次，X-1a 不可能绿（矩阵 §A）。
  - **覆盖面新增 `tests/fixtures/ai_stub.py`**：它进了 `baseline_1b` 的 import 闭包，`test_soak_log_contract.py` 的闭包检查会要求它出现在上面的命令里。桩自身的「gate 超时后干净收尾、不发末块、不断连接」契约由 `tests/unit/test_ai_stub_contract.py`（3 条，unit lane）钉住——X-1a′ 的失败形态（断言失败而非 timeout）全靠它。
  - **两处实测订正**（已写进任务书 §6 X-1 行）：`rag.py` 的 `_keyword_fallback` 是**整句子串匹配**，矩阵给的提问 `"Alpha 这一章讲了什么？"` 对未建索引的沙箱书返回 400，本模块提问必须是正文逐字子串（`QUESTION = "Alpha prose"`）；`done` 后 `renderAll()` 会在**同一节点**里追加 `div.ai-citations`，快照不能读 `lastElementChild.innerText`，改读该节点自己的文本节点。
  - **定向破坏 4 处**（3 处 `page.route` 改写 `ai.js`，1 处改桩的临时副本），`src/` 一行未动。关键一发：把流式分支改成 `await resp.text()` 后回放，X-1a′ 以 `assert stub.completed is True` 失败、耗时 5.06s——证明 R2 的超时序关系把失败形态钉在了「断言失败」而不是「timeout」。S3（删 `abort()`）暴露首版 X-1c 对「stop 不中止 fetch」是盲的，录红后**追加**两条断言（`gate_timed_out is False`、`completed is False`），既有断言零改动。
  - 红收据 `009-WI-16`（lane e2e）记 `green`，verify 判 `SEPARATION-BROKEN`：逐行指纹核对，新增 21 行全在 X-1c 的追加断言与 `SABOTAGE_LOG` 块内，消失的记录行 1 条（破坏表占位）。
- `39f502b41e65` ← Wave 5（WI-10）一个新模块 ＋ `helpers.py` 与七个既有模块的 helper 上收。**两个理由各自都足以让旧值作废。**
  - **用例增量**：`baseline_1b/test_kernel_overlay_geometry.py`（K-3a 三浮层 `position: fixed` ＋ 祖先链无包含块制造者 ×3、K-3b 工具条对选区的绝对对位、K-3b′ 平移协变差分、K-3c 笔记编辑器贴边，共 **6 条**）。baseline_1b **55 → 61 条**（`EXPECTED_BASELINE_ITEMS` 的分母今天第一次被实测填满；「实测 == 61」的断言仍留给 WI-17），`tests/e2e` 全量 **65 → 71 条**（68 passed + 3 skipped），全量耗时约 50s → **约 53s**。
  - **helper 上收**（兑付欠账 #25）：`open_ch0`（三份合一）/ `settle_marks` / `open_reader_settled` / `open_font_popover` / `content_style` / `assert_corpus_unchanged` / `assert_visible_book_ids` / `collections_file` / `read_collections` / `http_json` / `delete_collections_with_prefix` / `frame_box` 进 `helpers.py`，七个模块切换调用点。除 `assert_corpus_unchanged` 外全是改名；那一个是把四个模块各自的字面量绊线抽成共有形状 `assert_corpus_unchanged(*checks)`，每模块的期望值与消息文本逐字留在各自的 `CORPUS_CHECKS` 里（§0 第五条：基准仍是字面量）。
  - **两处实测订正**（已写进任务书 §4 K-3 行）：三个浮层是 `<body>` 的直接子元素，祖先链只有 `BODY → HTML`，`rd-shell` 是兄弟——「给 `rd-shell` 加 transform 必红」这个纸面配方对着真实 DOM 是 6/6 绿，破坏点必须是 `<body>`；`smoke_data` 上 `Alpha prose` 的选区中心 x ≈ 130 落在 clamp 带内（下界 220），几何三条改用 `repeat_data`（s1 `deck`#6 cx 379 / top 180，s2 `lamp`#22 cx 735 / top 406）。实测布局 `frame_box = {x: 0, y: 40, w: 1280, h: 640}`，`Y_TOL = 20 < 40` 成立。
  - **定向破坏 5 处全部走 `page.route` 改写响应体**，`src/` 一行未动（`git diff --quiet -- src/` 退出 0）。其中一发证明了 K-3b 与 K-3b′ 并存的理由：删掉 `offsetRect` 的 `frameRect.top` 项，K-3b / K-3c 的 Y 轴红，**K-3b′ 绿**（偏移在差分里抵消）。
  - 红收据 `009-WI-10`（lane e2e）记 `green`，verify 判 `SEPARATION-BROKEN`：成因是录红后回填 `SABOTAGE_LOG` 字符串（第 546–563 行），用指纹逐行核对，全部 `assert` / `pytest.fail` 行与收据一致，无断言改动。
- `b509a1235914` ← Wave 4（WI-13/14/15）四个新模块。**纯用例增量，harness、语料、helper 与生产代码全部一行未动**——`conftest.py` / `helpers.py` / `tests/fixtures/*` / `src/` 这次都没进来（共享文件授权制见 §0.6，本波无人被授权）。
  - `baseline_1b/test_read_chapter_change_and_search.py`（R-4 换章重绘 ＋ R-5 iframe 内搜索高亮 latin/cjk 各一，**3 条**）、`test_read_presentation_anchoring.py`（R-6a 主题四态 / 字号 ± / 间距 ± 三条参数化，**3 条**）、`test_library_nav_and_collections.py`（X-2a 书架⇄阅读器往返、X-2b 侧栏范围切换、X-2c 集合范围书单，**3 条**）；`acceptance_4b1/test_r6b_cfi_reanchoring.py`（R-6b 三条，模块级 skip，**3 条**）。baseline_1b **46 → 55 条**，`tests/e2e` 全量 **53 → 65 条**（62 passed + 3 skipped），全量耗时约 42s → **约 50.4s**。
  - **三路并行的一条纪律，是本波最该带走的东西**：三个 agent 共用一个 worktree，WI-14 在跑定向破坏时把 `epub-renderer.js` 就地改了，被并跑的 WI-13 当场撞见。WI-13 的处置是对的——不碰它，自己**全程用 `page.route` 改写响应体**做破坏，一次都没写 `src/`。共享 worktree 的并行波次里这应当是硬性写法（已记为欠账 #25）。
  - **本波实测订正了欠账 #15 的说法**：字号 / 间距四个 ± 按钮的可访问名是**按钮文本 `−`（U+2212）与 `+`**，不是中文 `title`——accname 里 contents（2F）先于 title（2I）。`name="减小字号"` 匹配 0 个、`name="−"` 匹配 1 个。因为四个按钮两两重名，**限定到 `rd-pref-size` / `rd-pref-leading` 是正确性要求**，不限定就触发 strict mode 违规。
  - **另有三处生产行为被实测钉住并记账**：主题四态是死表面（欠账 #21，与 #11 同型）；字号 / 间距传到 iframe 里晚一拍，第一次点击对正文毫无效果（欠账 #22，用户可见）；多选模式的类名 `select-mode` 与样式表的 `.selection-mode` 对不上，复选框不悬停就看不见（欠账 #23）。

- `d44d99459b25` ← Wave 3.5 的 helper 上收 ＋ 一处 flaky 修复。**用例条数一条没变**（`baseline_1b` 仍 46、`tests/e2e` 仍 53），所以这次作废的不是「测了什么」，而是「怎么等」。
  - **helper 上收**（兑付欠账 #13）：`reader_frame` / `pathname_is` / `scan_marks` / `mark_id_union` 从三个 `baseline_1b` 模块提进 `helpers.py`，`open_reader` 改为委托 `reader_frame`。纯搬移——`git diff -U0 -- tests/ | grep assert` 全程只有一行变化，且是 `_scan_marks` → `scan_marks` 的改名。`scan_marks` 的返回值是两种旧形态的**超集**（`text`＋`marks` 的文本节点视角，与 `texts`＋`ids`＋`html` 的 `<mark>` 元素视角），两者都返回而不是互相推导，因为一个 `<mark>` 里有多个文本节点时它们会分叉。
  - **flaky 修复**（欠账 #16）：`test_write_recolor_and_delete.py` 的 `_open_ch0` 加了 `wait_for_load_state("networkidle")` ＋ 一次重复的数量断言。修前该模块约四成概率红；修后全量连绿 9 轮（末两轮 CPU 打满）、模块单跑 8/8 绿。**没有任何断言被删改或放松**，改的只是等待判据。
  - **代价**：全量耗时 24.51s → **约 42s**。多出来的十几秒全部是等第二遍重绘落定，是买确定性的钱。
  - 生产代码一行没动（`git diff --stat -- src/ designs/ scripts/ tests/e2e/conftest.py` 为空）。

- `6fac77825ac7` ← Wave 3（WI-9/11/12）三个新模块。**纯用例增量，harness 与语料一行未动**——`conftest.py` / `helpers.py` / `tests/fixtures/*` 这次都没进来，所以作废理由只有一个，比 Wave 2 那次干净。
  - `baseline_1b/test_kernel_actions_and_url.py`（K-2 七个 `data-action` 各一条结果断言 ＋ K-6a 直接进入 ×3 ＋ 站内翻章 ×1，共 **11 条**）、`test_kernel_host_elements.py`（K-1a 宿主齐备 ＋ init 行为证据，共 **2 条**）、`test_read_paths.py`（R-1 ＋ R-2 三机制 ＋ R-3，共 **5 条**）。baseline_1b **28 → 46 条**，`tests/e2e` 全量 **35 → 53 条**，全量耗时 19.01s → **24.51s**。生产代码一行没动（`git diff --stat -- src/ designs/` 为空）。
  - **本波实测到一处与既有记述冲突的事实，记在这里因为它会影响「同一套用例」的解读**：`rd-page-prev` / `rd-page-next` 是**死表面**——`reader.html` 的基础样式里就是 `display: none`（注释写着 keyboard-only navigation），且全仓 live 的 `js/*.js` 无任何绑定，唯一绑定在 `reader.html` 根本不加载的 legacy `js/pagination.js` 里。任何点它的用例只会等到 actionability 超时。R-2 的「三种导航机制」因此实际是 `rd-chapter-next`（站内，`<a href>` 被 `preventDefault` 截住）、TOC 行 `findAndGo()`（站内）、直接 `goto`（整页），而**不是**生成的 plan 里写的 `rd-page-next`。
  - **另一处实测契约**：站内导航时 **URL 落后于渲染**。`syncLocationToUrl()` 跑在 epub.js 的 `rendered` 回调里，所以点完 `rd-chapter-next` 或 TOC 行的那一刻，地址栏还是旧章号。WI-12 的定向破坏 D4′ 就是这么发现的：把 URL 期望改成隔壁章号，两个站内分支**照样绿**——因为断言执行时 URL 确实还是旧的。调换成「先断正文、再断 URL」之后同一发子弹三条全红。**任何先断 URL 的用例都在读陈旧状态。**

- `355afedd106b` ← Wave 2（WI-6/7/8）三个新模块 ＋ `tests/e2e/conftest.py` 的服务日志改道。**两个理由各自都足以让旧值作废，这里一并记。**
  - **用例增量**：`baseline_1b/test_write_recolor_and_delete.py`（W-5a-⓪①②③ ＋ W-6，5 个 def → 8 条参数化）、`test_write_overlap_and_disambiguation.py`（W-8a/8b、W-10a/10b 共 4 条）、`test_write_cjk_boundary.py`（W-9a/9b 共 2 条）。baseline_1b **14 → 28 条**，`tests/e2e` 全量 **21 → 35 条**。生产代码一行没动（`git diff --stat` 为空）。
  - **harness 修复**：`live_server` 原先 `stdout=subprocess.PIPE` 却从不在运行期 drain。管道容量 macOS 上是 65536 字节，实测一轮全量服务端要写 **74194 字节**——越过之后 uvicorn 卡死在 `write()` 上，此后每一条要 `page.goto` 的用例都 30 秒超时。**这是一条从建账起就在的潜伏缺陷，用例数是引爆它的量而不是它的因**：21 条时写不满 64 KiB 所以从没发作，Wave 2 涨到 35 条就跨过去了。现象极具误导性——前 27 条全绿，之后红绿交错（不碰网络的用例照常过），像随机 flaky 而不像服务端卡死。改法是把 `stdout` 落到 `tmp_path_factory` 下的日志文件：文件没有容量上限，也就不需要另起线程去 drain。修前 `6 failed, 29 passed in 187.12s`，修后 `35 passed in 19.01s`。
  - 让它作废的理由与 Wave 0 那次同类但更强：不只是「用例住在哪里」变了，**「这套用例在什么条件下能跑完」**也变了——改之前，超过约 27 条的任何一轮全量都跑不到底，冻结在那个 harness 上的 soak 计数根本不可能积累起来。
- `5e3da7c797f6` ← `tests/e2e/conftest.py` 新增 `context` fixture，把浏览器的出网掐到只剩被测服务。**用例条数没变**（仍是 baseline_1b 14 条 / `tests/e2e` 21 条），断言一条没动，变的是用例在什么网络条件下跑——这恰恰是让它作废的理由：改之前，这套用例的绿依赖于跑它的人能连上 `fonts.googleapis.com`，改之后不依赖了，两次「21 passed」不是同一套条件下的同一件事。全量耗时 32s → **14.07s**，差额就是原先真的去取了那两个字体域。
- `777174826be2` ← §0 第六条纪律落地：`helpers.py` 新增 `assert_bystanders_unchanged`（旁观条守恒从「各用例就地写一行 assert」抽成共用函数），W-7 改为调用它。**用例条数没变**（仍是 14 条），断言语义也没变（整字典等值原样），变的是它住在哪里——抽出来是为了让 `tests/unit/test_e2e_bystander_discipline.py` 有一个 grep 得到的名字可查。同 Wave 0，纯搬家一样让哈希作废。
- `6672e32e6687` ← Wave 1（WI-5）：新增 `baseline_1b/test_write_note_editor.py`（W-4 / W-7 两条，12 → 14 条），同时改 `helpers.py`——`assert_roundtrip` 加 `expected_count`（默认 1，三个既有调用点行为不变）、新增 `wait_for_note_text` 与 `_pick_target`。**两个被 hash 覆盖的文件同时改**，既有条数变了、既有文件内容也变了，两个理由各自都足以让旧值作废。（同批还改了 `scripts/lint_e2e_selectors.py`，但它**不在** hash 命令的文件清单内，不构成本次作废的原因——它的影响是扫描面 14 → 20 处，记在下面一段。）
- `06114374b405` ← Wave 0 的 helper 上收：四个私有 helper 从两个 baseline 模块提进 `helpers.py`，**三个被 hash 覆盖的文件同时改**。用例条数没变（前后都是 19 条、断言集合逐条比对无增删改），变的只是它们住在哪个文件里——`suite_hash` 覆盖的是文件内容而不是用例条数，所以纯搬家一样让它作废。
- `f56131cfe4ef` ← WI-4 的 `test_write_create_annotations.py` 进索引（3 条用例）。
- `70ee84519f02` ← WI-1–WI-3 一批提交（commit `0e411f8`）。

### 与 `suite_hash` 无关但会影响「同一套用例」判断的一次改动

2026-09-03（WI-5）修了 `scripts/lint_e2e_selectors.py` 的一个盲区：正则要求引号紧跟在 `(` 后，
于是**所有 f-string 形态的 locator 实参一处都没被扫到**；而 ADR-0014 的复合选择器要插一个
运行期 id，天然全是 f-string。实测旧正则会对一个同时含 `.some-class` 与 `[data-modal="…"]`
的探针文件报「0 处违规」。补上前缀后扫描面 **14 → 20 处**，全仓仍 0 违规。

记在这里的理由：这个脚本不在 `suite_hash` 的覆盖面内，所以它变了 hash 不变——但「这套用例
被什么强度的门禁把过关」确实变了。G2 冻结后若有人回头比对，光看 hash 会以为门禁没动过。

`70ee84519f02` 取代 `235802f4647d` 的原因**正是下面那条索引态的坑本身**：算它的时候
`tests/e2e/baseline_1b/` 与 `tests/e2e/helpers.py` 还未进索引，`git ls-files -s` 对它们
静默产出空，于是那个值算的是一个不含这两者的 suite。WI-1–WI-3 一批提交后重算得到
`70ee84519f02`。**这不是命令的缺陷被触发，是它被如实执行了**——留着这段是因为它是这条坑
唯一一次有据可查的实例。

**2026-09-02 补两个路径（WI-3 落地时由守卫逼出来的，两个都不是「顺手加宽」）：**

- `tests/conftest.py` —— **没有任何 import 语句指向它**，是 pytest 按目录层级自动加载的祖先
  conftest。它里面那个 `pytest_configure` 钩子校验 `-m` 表达式里的 marker，直接决定
  `-m baseline_1b` 能不能选中东西：改它就是改 suite。纯 AST 的 import 追踪永远看不见这一支，
  所以守卫里它是**按目录结构**入闭包的，不是追出来的。
- `tests/fixtures/epub_zip.py` —— `epub_corpus.py` 的每个 builder 都经它写盘，四本语料的字节
  全由它决定。它此前逃过守卫是因为守卫的模块解析序写反了（详见
  `tests/unit/test_soak_log_contract.py` 的 `_resolve_module` docstring）：裸名 `conftest`
  被解析成 `tests/conftest.py` 而不是 pytest 实际导入的 `tests/e2e/conftest.py`，于是后者整条
  语料依赖链都没进闭包。**结论碰巧对、理由是假的**，比直接报错更难发现。

### 与迁移计划 §7 命令的三处差异（改的是命令，不是规则）

§7 明确授权「若目录名不同，改的是这条命令，不是规则」。落地差异：

- `tests/e2e/baseline-1b` → `tests/e2e/baseline_1b`（WI-1 的实际目录名用下划线）；
- `tests/e2e/fixtures` → 本仓库没有这个目录，共享语料在 `tests/fixtures/`，按 §7 的裁定纳入 `epub_corpus.py`；
- `playwright.config.*` → **本仓库从来没有这个文件**（harness 配置在 `tests/e2e/conftest.py` 里），
  所以这一项被去掉，不是漏抄。

`git ls-files` 对未进索引的路径静默产出空，因此命令在任何时点都可跑、值合法；
文件一提交就自动进哈希，不需要再改命令。

### 取哈希前必须先确认工作树干净（运行器的前置检查）

`git ls-files -s` 读的是 **git 索引**，不是工作树。2026-09-02 实测：

| 状态 | 值 |
|---|---|
| 基线 | `990bfff749ef` |
| 改了工作树、未 `git add` | `990bfff749ef` ← 内容变了，哈希没变 |
| `git add` 之后 | `0b1448c13b23` |
| 还原后 | `990bfff749ef` |

**后果**：soak 期间有人改了 `baseline_1b` 的一条断言却没 `git add` 就跑全量，`suite_hash` 不变，
那次运行会被记成「同一套东西」的第 N 次绿——正是清零规则要堵的假绿路径，而命令的实现方式在这里漏了一档。

所以**取哈希前工作树对这几个路径必须是干净的**，且这应当是 `scripts/soak_run.py` 的前置检查，
不是靠人记得：

```bash
git status --porcelain -- \
  tests/e2e/baseline_1b tests/e2e/conftest.py tests/e2e/helpers.py \
  tests/e2e/test_harness_smoke.py tests/fixtures/epub_corpus.py
# 非空 ⇒ 拒绝落账：记的会是索引里的旧内容，不是刚跑过的那份
```

---

## 三类清零触发器（指针，规则正文在迁移计划 §7）

- `suite_hash` 变了 ⇒ 清零 —— [§7 台账字段（canonical）＋ 什么会让计数作废](../plan-tech-stack-migration.md#台账字段canonical-什么会让计数作废)
- `browser` 或 `os` 变了 ⇒ 清零 —— [§7 台账字段（canonical）＋ 什么会让计数作废](../plan-tech-stack-migration.md#台账字段canonical-什么会让计数作废)
- 任意一次 `red` ⇒ 清零 —— [§7 台账字段（canonical）＋ 什么会让计数作废](../plan-tech-stack-migration.md#台账字段canonical-什么会让计数作废)

生产代码变（`commit` 列变）**不**清零；其余四个尚未激活的 acceptance 组怎么改也**不**清零——
它们不在上面那条命令的覆盖路径里。

### 冻结前的行怎么标

`suite_hash` 与本文表头记录的当前值不同的数据行，**必须在该行里显式写上 `pre-freeze`**，
它不计入 ≥10 次的分母。没有第二种标法：`result` 列只有 `green` / `red`，
拿一次冻结前的绿去凑数在台账上是无痕的，靠的就是这个标记。

**复核方式**：把上面那条命令复制出来跑一遍，输出应等于表头记的值。这是 review 动作，由人执行——
自动化用例**不**断言「表头的值 == 现在算出来的值」，那会让每一次合法的套件改动都红一条无关的用例，
而冻结的语义本来就是「这个值不随之后的改动走」。台账形状的机器可解析性由
`tests/unit/test_soak_log_contract.py` 守。

---

## 两条纳入/排除口径及其代价

### 1. `tests/fixtures/epub_corpus.py` —— **纳入**，代价是「纯单测改动也会清零」

它是 `build_epub2` / `build_epub3` / `build_cjk` 的所在地，`baseline_1b` 每一条用例读的都是它造出来的书。
不纳入，就等于允许「不动用例、只动语料」地重塑十次运行的含义。

**代价是实的，不藏**：这个文件今天有三个消费方，其中两个不在 e2e 一侧——

- `tests/unit/test_fixture_epub_corpus.py`（unit lane）
- `scripts/bench.py`（基准脚本）
- `tests/e2e/conftest.py`（e2e lane，即冻结的那一侧）

因此**一次纯单测目的的构造器改动也会把 soak 计数清零**。比如第十次运行前一天，有人为了
`tests/unit/test_fixture_epub_corpus.py` 的一条断言给 `build_epub2` 加个 `lang=` 参数——计数归零，
而归零的理由与 e2e 毫无关系。这是「宁可多清零，不可假计数」的一侧误差，接受；
写在这里是为了归零那天有人知道为什么。

### 2. `pyproject.toml` —— **排除**，代价是「marker 定义变更不触发清零」

它会因依赖升级等与被测行为无关的原因变动，纳入等于每次 bump 清零。

代价是：`pyproject.toml` 里的组 marker 定义（`baseline_1b` 等五个）如果被改动——比如某个 marker
被悄悄改名，导致一批用例不再被选中——`suite_hash` 不会变。**补偿手段**：每次运行必须把
`--collect-only` 的条数写进 `log` 列指向的产物里，并与 `scripts/lint_e2e_groups.py` 的
`EXPECTED_BASELINE_ITEMS` 对齐。分母不对，那次运行不算绿（判据见
[`009-e2e-annotations.md`](./009-e2e-annotations.md) §8 G2）。

---

## 机制挑战闸执行记录（2026-09-20）

规则正文在[迁移计划 §7「机制挑战闸」](../plan-tech-stack-migration.md)——三项各自独立**阻塞 Phase 3**，
通过条件写死为「**首次**通过」，重试只能用来**分类**。这里只记执行结果，不复述规则。

**这三次都没有写进上面的台账**，也不该写：它们改变了抽样条件，混进那 10 次等于拿不同剖面拼「连续」。
全部用 `uv run python scripts/soak_run.py`（**不带 `--append`**，只打印不落账）或直接 `pytest` 跑。
三次运行 `suite_hash` 均为**当时的**冻结值 `2747100dadf6`；该值已于 2026-09-21 作废，
因此以下全部结果均已作废，见紧跟其后的红框。

| 场景 | 结果 | 一句话 |
|---|---|---|
| 干净 Linux / CI | ❌ **FAIL（已验证）** | 真跑三次，三次都红；`baseline_1b` 每次都是 1 failed / 66 passed。第三次（2026-09-20 修完 #45 后）红的成分少了一条：unit lane 的浏览器依赖已除，只剩 #46 那条 flaky |
| CPU 压力下 | ✅ **PASS** | 10 核压满（结束时 load 20.84），67/67 **首次**通过，58.25s |
| 随机化收集顺序 | ❌ **FAIL** | seed 3003 首次红 1 条；原样重放两次全绿 ⇒ 分类为 **flaky，不是顺序依赖** |

> ### ⛔ 2026-09-21：**以下三项结果全部作废，三项都需重跑。**
>
> `suite_hash` 由 `2747100dadf6` 变为 `1e868c7bf811`（原因见上方变更史第一条）。按
> [迁移计划 §7 纪律 4](../plan-tech-stack-migration.md)「何时重跑：`suite_hash` 变了，
> 或 harness 变了。与 soak 计数的清零触发器同源」——**包括 2026-09-20 已经 PASS 的第 2 项
> CPU 压力**。它测的是「这套字节在这个剖面下首次通过」，套件的字节已经不是那套了，
> 那个 PASS 证明不了新套件的任何事。
>
> | 场景 | 2026-09-21 起的状态 | 作废掉的是什么 |
> |---|---|---|
> | 干净 Linux / CI | **需重跑**（此前 FAIL） | 下方三跑的记录保留，因为它们点出的缺陷（#45 已结、#46 已修、W-8a 已修）是真的，且**不随哈希作废** |
> | CPU 压力下 | **需重跑**（此前 PASS，作废） | 唯一一项已经过的闸，代价最实 |
> | 随机化收集顺序 | **需重跑**（此前 FAIL，seed 3003） | 那条红的机制是上浮还是塌陷**未测**，重跑正好一并回答 |
>
> **重跑前不要动上面那张汇总表、也不要动下面各项的详细记录**——它们记的是 2026-09-20
> 那天对旧套件的事实，改掉就没了。新结果另起一节。

**当前状态（2026-09-21 三项全部重跑完）：第 1 项 PASS、第 3 项 PASS、第 2 项建议记作未过
（字面首绿，但同命令同压力四跑两红，见下）。Phase 3 / 012 仍被第 2 项阻塞**，
另有 ≥10 次 / ≥5 工作日那一条也在清零后重数（上方台账现为空表）。

### ⬛ 对新冻结值 `1e868c7bf811` 的重跑：第 1 项 **PASS**（2026-09-21）

**这是本仓第一次在干净 Linux 上把 `baseline_1b` 跑全绿。** 前三跑三红，失败签名逐字相同，
是确定性的，不是 flaky；这一跑不是运气变好，是[欠账 #44](./009-e2e-annotations.md) 的
**上浮**机制被修掉了。

| 项 | 结果 | 实测 |
|---|---|---|
| 干净 Linux / CI | ✅ **PASS** | run [35584711194](https://github.com/anzchy/reader3-pro/actions/runs/35584711194) @ `176c8cb`，`workflow_dispatch`，**`attempt=1`** |
| CPU 压力下 | ⚠️ 字面首绿，**建议不认** | 同日续跑，见下一节 |
| 随机化收集顺序 | ✅ **PASS** | 同日续跑，见下一节 |

**e2e job**（`soak_run.py`，不带 `--append`）逐字：

```
[soak] 68/92 tests collected (24 deselected) in 0.98s
[soak] summary: 68 passed, 24 deselected in 76.03s
[soak] verdict: green（可记账：是）
[soak] row: | 2026-09-21T09:43:32Z | 176c8cb | green | 76.03 | 1e868c7bf811 | chromium-1234 | linux-6.17.0-1022-azure | … |
```

非 baseline 那批单独跑：`8 passed, 16 skipped, 68 deselected in 16.40s`。

**unit job**：`1556 passed, 2 skipped in 96.74s`，**0 failed** —— [欠账 #46](./009-e2e-annotations.md)
在干净 Linux 上确认死透，这也是「CI 上 unit lane 全绿」第一次真的发生
（见 [011 §8 门槛 3](./011-backend-refactor.md) 挂了两天的那条 ⚠️ 追记）。
另：`ruff` `All checks passed!`、`mypy` `Success: no issues found in 41 source files`。

**「首次通过」这四个字是核过的，不是默认的。** `attempt=1`；`tests.yml`、`soak_run.py`、
`pyproject.toml` 全文 grep `reruns` / `retry` 零命中，即没有重试插件在背后兜底。按
§7 纪律 2，这一跑够格判 PASS。

**别把这一跑的证明力扩大。** 它证明的是**这套新字节在 GitHub 的 Linux runner 上首次通过**。
第 3 项那条 seed 3003 的红挂在 `test_kernel_actions_and_url.py` 的 K-2 上，是**另一条用例**，
它的机制（上浮？塌陷？还是第三种）**一次都没测过** —— 第 3 项重跑正好一并回答这个问题。
（⬛ 当日续：答案是**三种都不是**。那条红既不是 Range 破坏也不是顺序依赖，是 CPU 争用下
写路径整体的一类失败，已在下一节复现并定位到 [009 欠账 #42 / #43](./009-e2e-annotations.md)。）
那条 `row:` 行也**没有**写进上方台账：CI 跑的是分支，按
[011 §8 门槛 4 的括号](./011-backend-refactor.md)，分支上的运行不进台账。

**2026-09-20 当天更新：第 1 项从「未验证」变成「验证为红」。** 数字没变（仍是 1/3），但性质变了——之前是一道没人跑过的闸，现在是一道**跑过、响了、并点出三个具体缺陷**的闸。这三个缺陷本地一个都照不出来，正是 §7 立这一项要买的东西。

### ⬛ 对新冻结值 `1e868c7bf811` 的重跑：第 2 / 第 3 项（2026-09-21）

两项一起跑完之后，结论跟开跑前的预期**反过来了**：预期是「压力那项好过、随机顺序那项难过」，
实测是随机顺序那项干干净净地过了，而 CPU 压力那项**只是运气好**。把变量拆开测才看出来。

| 项 | 字面结果（按 §7 纪律 2「首次通过」） | 建议怎么记 |
|---|---|---|
| CPU 压力下 | 首次通过：`68 passed, 24 deselected in 71.16s` | ❌ **不要认这个 PASS**，理由见下「一跑不足以判这一项」 |
| 随机化收集顺序 | 三个 seed 首次全绿 | ✅ **PASS**，且 2026-09-20 那条 FAIL 的**归因被推翻**（不是顺序依赖） |

#### 第 2 项 —— CPU 压力下：字面 PASS，实质是假的

压力源与 2026-09-20 同一份（10 个忙等进程 = `sysctl -n hw.ncpu` → 10）。**第一次尝试作废**：
压力进程用 `nohup … &` 在一个 shell 调用里起、lane 在下一个调用里跑，背景进程根本没活过调用边界——
压力启动前 load **3.20**、lane 结束时 **3.18**，等于没压。这正是 2026-09-20 记录里警告过的
「这个数必须记，否则『压力下通过』可能只是压力没起来」。重做时把压力与 lane 放进**同一个** shell 调用：

| | load（压前） | load（lane 结束） | 结果 |
|---|---|---|---|
| 第一次尝试（作废） | 3.20 | 3.18 | 压力没生效，结果不可用 |
| 重做 | 13.60 | **92.34** | `68 passed, 24 deselected in 71.16s`，`verdict: green`，`suite_hash 1e868c7bf811` |

71.16s 对照无压力 ~55s，慢 **29%**。按 §7 字面，这是首次通过，够格判 PASS。

**但这一项不该按这个判。** 跑第 3 项时为了排查另一件事，我用**同样的压力源**、**同样的命令**
又跑了三次自然顺序。`soak_run.py:149` 的 `LANE_ARGS` 与这三次的命令**逐字相同**
（`tests/e2e -m baseline_1b --browser chromium -q -p no:cacheprovider`），所以这是同一个实验的第 2–4 个样本：

```
nat rep1 load_start=61.80  FAILED …test_k2_delete_action_removes_the_clicked_annotation_from_disk[chromium]
                           FAILED …test_w2_w3_programmatic_selection_creates_typed_annotation[chromium-underline]
                           2 failed, 66 passed, 24 deselected in 73.93s
nat rep2 load_start=39.20  FAILED …test_w9b_cjk_note_body_survives_edit_and_reload[chromium]
                           FAILED …test_w5a3_recolor_then_repress_replaces_with_a_new_id[chromium-underline]
                           3 failed, 65 passed, 24 deselected in 77.50s
nat rep3 load_start=42.31  68 passed, 24 deselected in 56.88s
```

**同命令、同压力剖面，四跑两红。** 那个 PASS 是抛硬币抛出来的。第 2 项要证明的性质是
「这套用例在 CPU 争用下仍然稳」，这条性质**实测为假**；拿一次首绿去认证一条已被证伪的性质，
就是这份台账反复警告的那种「把数字擦亮」。

**这暴露的是 §7 本身的一个洞**：纪律 2 写死了「**首次**通过」，但**没写「一次尝试 = 跑几遍」**。
对干净 Linux 那项，一次 CI run 就是一次尝试，没有歧义；对「压力下」这种本质上在测**分布**
而不是测**某一次**的闸，n=1 的尝试不构成证据。建议把 §7 第 2 项的通过条件改成
「**连续 k 次**（建议 k=5）在压力下全绿，首轮即须成立」，然后重跑。在那之前，第 2 项记作**未过**。

#### 第 3 项 —— 随机化收集顺序：**PASS**

插件与命令与 2026-09-20 同一套（`pytest-random-order` 1.2.0，`--random-order-bucket=global`）。

| seed | 首次结果 | 耗时 |
|---|---|---|
| 1001 | ✅ `68 passed, 24 deselected` | 55.23s |
| 2002 | ✅ `68 passed, 24 deselected` | 55.64s |
| 3003 | ✅ `68 passed, 24 deselected` | 54.89s |

**先证明随机化真的生效了**，再谈绿不绿——上面第 2 项那次「压力没起来」的教训值这一步。
拿 K-2（`test_k2_note_action_opens_the_editor_and_the_save_lands_a_note_record`）当探针，
它在收集列表里的位次：不加 `--random-order` 时 **7**，三个 seed 下分别是 **13 / 68 / 39**；
两两 `diff` 的差异行数 **108–114 行 / 共 136 行**。顺序确实被打散了。

#### 第 3 项的红是怎么被排除掉的：三个 seed 全绿之后我没有直接认，而是去打它最弱的地方

seed 3003 在旧套件上是**一红两绿**，一次首绿不能证明那条 flaky 没了。原样重放 8 次：

| rep | 结果 | 耗时 |
|---|---|---|
| 1 | ❌ 2 failed, 66 passed | 75.30s |
| 2 | ❌ 4 failed, 64 passed | 88.19s |
| 3–8 | ✅ 68 passed ×6 | 55.61–56.85s |

**红的两次正好是耗时异常的两次**——而它们之所以慢，是因为我在旁边另起了 4 个并发
`--collect-only` 进程。这是我自己引入的混杂，不是干净样本，但它指了个方向：**相关的是负载，不是 seed。**
顺着查，同一个 seed 3003 ＋ 10 个忙等进程（lane 结束时 load 19.75），当场复现：

```
FAILED tests/e2e/baseline_1b/test_kernel_actions_and_url.py::test_k2_type_actions_create_an_annotation_of_that_type[chromium-underline]
E       AssertionError: 8.0s 内 notes.json 没有稳定到 1 条，实际 0 条：[]
tests/e2e/helpers.py:823: AssertionError
1 failed, 67 passed, 24 deselected in 68.69s
```

**与 2026-09-20 那条红的失败签名逐字相同**（同一族 K-2、同一个 `wait_for_notes`、同一句断言文本）。
再加上上面自然顺序 ＋ 同样压力的三跑两红，判据齐了：

- 固定 seed 3003、**低负载** ⇒ 6/6 绿
- 固定 seed 3003、**高负载** ⇒ 3/3 红（rep1、rep2、压力复现）
- **自然顺序**、高负载 ⇒ 3 跑 2 红

**自然顺序在同样负载下红得一样勤，所以顺序不是自变量，负载才是。** 第 3 项要照的缺陷类别是
「用例间顺序依赖」，三个 seed 加上这一串对照都没照出这一类，且旧那条 FAIL 的归因（当时只留下
一句「机器当时偏忙」的旁证）现在被正面推翻。按 §7 纪律 2「首次通过」，第 3 项**判 PASS**。

**别把它读成『那条 flaky 修好了』。** 它一次也没好，只是换了个变量去激它。而且这轮红出来的
用例**每次都不一样**——K-2 create（underline）、K-2 delete、W-2/W-3、W-9b、W-5a-③，横跨 4 个文件，
全在「写一条标注 / 改 / 删，然后等 `notes.json`」这条路径上。所以这不是「某一条不稳的用例」，
**共享同一个失败表象**，对应 [009 欠账 #42 / #43](./009-e2e-annotations.md)（写路径上
六个把失败吞掉的出口，e2e 因此分不出是测试侧等太短还是产品侧请求根本没发出去）。那两笔欠账没动过，
这轮给它们添了新证据：**触发条件是 CPU 争用**，而且可复现。

> **⚠️ 这一段最初写的是「是整条写路径在负载下的一类失败」，那是把推断写成了事实，已改。**
> 手上有的是**共同表象**：五条红全部挂在 `wait_for_notes` / `wait_for_note_text` 这一族 8s 等待上。
> 但那是一个**共享的 helper**，所以「同一个 helper」与「同一个根因」是混杂的——共享等待器本身有问题、
> 调度延迟、请求失败、覆盖写，四种都能长出这一模一样的表象。**「值得按一类问题去查」成立，
> 「已知是一类产品故障」证据不足。** 这条修正来自 2026-09-21 对该结论的一次外部复核。

**本轮本机 16 次 `baseline_1b` 的完整分布**（不含 CI 那次，也不含第 2 项那次作废的尝试）：

| 剖面 | 跑数 | 红 | 耗时区间 |
|---|---|---|---|
| 无压力（3 seed 首跑 ＋ seed 3003 rep3–8） | 9 | **0** | 54.89–56.85s |
| 10 忙等进程压着 | 5 | **3** | 56.88–77.50s |
| 我自己引入的并发混杂（seed 3003 rep1–2） | 2 | **2** | 75.30–88.19s |

**无压力 9/9 全绿，有负载 7 跑 5 红。** 别把耗时当判别器——有压力那 5 跑里，绿的两跑
一个 71.16s（第 2 项那次）、一个 56.88s（nat rep3），跨了整个区间，红绿在耗时上**不可分**。
唯一稳的相关是「有没有负载」，不是「跑了多久」。

### 第 1 项 —— 干净 Linux / CI：**FAIL**（2026-09-20 真跑三次，三次都红）

载体是 `.github/workflows/tests.yml` 的第二个 job `e2e`（9 步），2026-09-20 加入，同时兑付了
[009 欠账 #31](./009-e2e-annotations.md) 的两半——**包括 (b)「在一次 workflow_dispatch 上见过红」**，
而且是字面意义上的见过红。

**闸要的两个固定项（连同结果一并记录）：**

| 项 | 实测值 |
|---|---|
| Playwright | **1.62.0** |
| Chromium | **Chrome for Testing 151.0.7922.34**，revision `chromium-1234` |
| lock | `uv sync --frozen --all-groups`（lock 与 `pyproject.toml` 不一致就直接失败，不悄悄重解） |
| OS | `linux-6.17.0-1022-azure`（ubuntu-latest runner） |
| suite_hash | `2747100dadf6` —— 与冻结值一致，跑的确实是同一套用例 |

用 `scripts/soak_run.py` 而不是裸 `pytest`，因为本闸的通过条件是 **67/67**，不是「没红」。
`--append` **刻意不给**：CI 的运行剖面不属于台账，两次运行都是 dry run，台账一行没动。

#### 两次运行

| run | commit | `baseline_1b` | unit lane |
|---|---|---|---|
| [35499892289](https://github.com/anzchy/reader3-pro/actions/runs/35499892289) | `a73b4a5` | ❌ 1 failed / 66 passed / **81.89s** —— **哪条红的丢了**，见下 | ❌ 2 failed / 1552 passed |
| [35500630451](https://github.com/anzchy/reader3-pro/actions/runs/35500630451) | `4f5121d` | ❌ 1 failed / 66 passed / **83.51s** —— `test_w8a_*` | ❌ 1 failed / 1553 passed |

环境层两次全绿：`checkout@v5` / `setup-uv@v6` / `setup-python@v6` / `uv sync` / 装 Chromium
一路成功。所以红的是 lane 本身，不是 CI 配置——这个区分要留痕，否则下次有人会先去怀疑 action 版本。
顺带把 `tests.yml:26` 那句「action 版本尚未在 CI 里实跑验证过」的警告销掉了。
新冒出来的是 Node 20 弃用警告（`upload-artifact@v4`、`setup-uv@v6`），不影响结果。

#### 闸自己的一个缺陷：第一次响了却说不出是谁红的

`scripts/soak_run.py:746` 在不带 `--append` 时把明细 log 写进 `tempfile.mkdtemp()`——这是对的，
dry run 不该往仓库里拉屎——而 job 的那一步**没给 `--log-dir`**，于是明细落在 `/tmp/soak-ozvxvjvu/`
里随 runner 一起没了，控制台只剩一行 summary。artifact 那一步收的是
`.claude/tdd-guardian/soak-logs/`，**那是随 checkout 带进来的历史 log**，4193 字节全是噪声，
本次真正的明细一个字节都没收到。

**一道说不出「谁红了」的闸，等于逼人把它重跑一遍才能开始查。** 已于 `4f5121d` 修：
baseline 步骤加 `--log-dir soak-ci-logs`，artifact 改收它、不再收那份历史 log。
run 35500630451 的明细因此完整抓到。**run 35499892289 那条红是哪个用例，永久丢失**——
如实记下来，不假设它与第二次是同一条。

#### 第 2 次那条红：`test_w8a_two_overlapping_annotations_both_persist_and_render[chromium]`

```
FAILED tests/e2e/baseline_1b/test_write_overlap_and_disambiguation.py::
  test_w8a_two_overlapping_annotations_both_persist_and_render[chromium]
  - AssertionError: 8.0s 内 notes.json 没有稳定到 2 条，实际 1 条：
    [{'type': 'marker', 'quote': 'Alpha pro', 'position': 3, ...}]
```

盘上那一条是 **A（marker）**，说明第一条落了、`assert_roundtrip`（含一次刷新）也过了，
**没落的是第二条（wavy）**。

**这与第 3 项 seed 3003 那条红是同一家族**：都是「一次笔记写入静默地没发生」，
都只能通过 `wait_for_notes` 超时观察到，都拿不到任何错误信息。病因同样落在
[欠账 #43](./009-e2e-annotations.md) 那六个静默出口上。

一处不同要记下来，免得被当成同一个 bug：W-8a 的第二条是**在一次全新的页面加载之后**
建的（`test_write_overlap_and_disambiguation.py:421` 又 `open_reader` 了一遍），
所以「A 创建后 `loadAndRender()` 重绘让旧 range 失效」这个对 K-2 成立的解释，**对 W-8a 不直接成立**。
也就是说六个出口里具体是哪一个，两条用例可能不是同一个。**在 #43 补出可观测性之前，这仍然是猜。**

#### 顺带照出来的：unit lane 在干净 Linux 上是红的（本地 macOS 全绿）

本闸没被要求照这个，但它照出来了。两条，责任不同，已分别立为
[欠账 #45 / #46](./009-e2e-annotations.md)：

- `tests/unit/test_e2e_group_guard.py::test_positive_selection_of_acceptance_groups_yields_exactly_the_skipped_count`
  —— **两次都红，确定性的。** 它 shell out 去跑 `pytest tests/e2e -m "acceptance_*"`，
  而 WI-5b（`cc6bb18`）激活 `acceptance_2a` 之后，那个子进程**真的去启浏览器了**；
  unit job 不装 Chromium，于是 `BrowserType.launch: Executable doesn't exist`。
  激活之前整组 module-level skip，碰不到这条路。**一条 unit lane 的用例现在依赖浏览器。**
- `tests/unit/test_ai_queue_lease.py::test_Q4_worker停不下来时仍释放租约并留ERROR`
  —— **第一次红、第二次绿，flaky。** 挂在前提断言 `assert not stuck_stream.exited` 上：
  假 worker 用 `stuck_delay=3.0`，前提是整段 scenario 在 3 秒内跑完，慢 runner 上跑不完。

**这两条本地永远照不出来**，因为本地装着 Chromium、机器也快。它们是这道闸第一次跑就付的钱。

#### 结清动作

第 1 项转绿要两件事：**(1)** 修掉 W-8a 那条红（卡在 #43 的可观测性上）；
**(2)** 修掉 #45，让 unit lane 在没有浏览器的机器上也能绿。在那之前，本项维持 **FAIL**。

> **⬛ 2026-09-20 当天续：(2) 已兑付，(1) 没有。** #45 已修（`--setup-plan` ＋ 逐 item 探针，
> 详见 [009 台账 #45](./009-e2e-annotations.md)）：`PLAYWRIGHT_BROWSERS_PATH=/nonexistent uv run pytest
> tests/unit tests/contract -q` 实测 **`1555 passed, 2 skipped in 48.41s`**，修前是 `1 failed`。
> 牙用两次定向破坏称过，两次还原后 `git diff --exit-code` 干净，**冻结 8 路径零改动**。
> **但本项仍维持 FAIL，有两个理由，都不是形式主义**：其一，(1) 的 W-8a 一条没动；
> 其二，**CI 尚未重跑**——上面这些证据全部来自本地模拟的无浏览器环境，而本项的判据原文是
> 「**干净 Linux / CI**」，本地模拟证明不了它，且 #46 那条 flaky 仍在那边。
> 想翻盘只有一条路：`gh workflow run tests.yml` 跑出 **67/67 首次通过**。

> **⬛ 2026-09-20 第三跑：`35512654210` @ `5056614`，仍 FAIL，但红的成分从三条降到两条。**
> 这是第一次在 CI 上验 #45 的修复，结论是确定的：**unit lane 的浏览器依赖在干净 Linux 上确实死了。**
>
> | job | 结果 | 内容 |
> |---|---|---|
> | 静态检查 ＋ unit lane | ❌ | ruff ✅ / mypy ✅；`1 failed, 1554 passed, 2 skipped in 93.14s`，**唯一的红是 #46** |
> | e2e baseline_1b | ❌ | `1 failed, 66 passed, 24 deselected in 77.42s` —— **#44**，与前两跑同一条 |
>
> 三个具名结论，分开说，别混：
>
> 1. **#45 已在 CI 侧死透。** 前两跑 unit lane 的红里都有它（`a73b4a5` 2 failed、`4f5121d` 1 failed），
>    这一跑 `test_e2e_group_guard` 不再出现在 FAILED 行里，且总数 1557 与本地
>    `1555 passed / 2 skipped` 逐字对上。这是本地模拟买不到的那半个证明，现在买到了。
> 2. **#44 三跑三红，不是 flaky，是确定性的。** 失败签名逐字相同：
>    `test_w8a_two_overlapping_annotations_both_persist_and_render[chromium]` —— 「8.0s 内
>    notes.json 没有稳定到 2 条，实际 1 条」，落了 A（`marker` / `yellow` / quote `Alpha pro`）、
>    没落 B。名字在 `a73b4a5` 那跑永久丢失，所以**按名字确认的是 2/2，按 `1 failed / 66 passed`
>    的形状确认的是 3/3**——这个区别别抹掉。它现在是第 1 项转绿的**唯一确定性阻塞**。
> 3. **#46 两红一绿，仍 flaky。** `test_Q4_worker停不下来时仍释放租约并留ERROR`，挂在前提断言上：
>    「假 worker 本应无视停止事件，但它停了」。`stuck_delay=3.0` 那个隐含时间假设在慢 runner 上不成立。
>
> 固定项与前两跑一致：Chrome for Testing 151.0.7922.34（`chromium-1234`）、`linux-6.17.0-1022-azure`、
> `uv sync --frozen`、**`suite_hash` 仍是 `2747100dadf6`**。仍是 dry run，
> 台账 10 行一行没动（`[soak] dry run：未写台账`）。
>
> `4f5121d` 的 `--log-dir` 兑现了：失败用例名这次**没有丢**。但要说清它兑现到什么程度——
> 名字不在控制台里，在 `e2e-logs` 产物里（`gh run download <id> -n e2e-logs`）。
> 比「永久丢失」好，比「一眼看出」差。

### 第 2 项 —— CPU 压力下：PASS

压力源（原样可复现，不依赖任何未入库的文件）：

```bash
# 开一个终端跑压力，10 个忙等进程 = hw.ncpu（本机 sysctl -n hw.ncpu → 10），持续 240s
python3 - 10 240 <<'PY'
import multiprocessing as mp, sys, time
def burn(deadline):
    while time.monotonic() < deadline:
        pass
if __name__ == "__main__":
    n, dur = int(sys.argv[1]), float(sys.argv[2])
    d = time.monotonic() + dur
    ps = [mp.Process(target=burn, args=(d,)) for _ in range(n)]
    for p in ps: p.start()
    for p in ps: p.join()
PY

# 压力跑起来之后，在另一个终端跑（不落台账）
uv run python scripts/soak_run.py
```

实测：压力启动前 load average **3.60**，lane 结束时 **20.84**（约 2× 核数，说明压力确实生效了——
这个数必须记，否则「压力下通过」可能只是压力没起来）。结果 `67 passed, 24 deselected in 58.25s`，
`verdict: green`，`suite_hash 2747100dadf6`，退出码 0，wall 58.4s。对照无压力时的 ~54s，**慢了约 8%**。

### 第 3 项 —— 随机化收集顺序：FAIL

插件 **`pytest-random-order` 1.2.0**（2026-09-20 加进 `[dependency-groups] dev`）。命令：

```bash
uv run pytest tests/e2e -m baseline_1b --browser chromium -q -p no:cacheprovider \
  --random-order --random-order-bucket=global --random-order-seed=<SEED>
```

**为什么是 `pytest-random-order` 而不是 `pytest-randomly`**：后者装上即生效，且会重置 `random` /
numpy 的全局种子——在一个刻意冻结运行剖面的仓库里那是污染。前者不给 `--random-order*` 时完全惰性，
已实测：两次默认 `--collect-only` 输出用 `diff` 比对**逐字节相同**，加上 `--random-order` 才变。
`--random-order-bucket=global` 是全局打散（默认 `module` 只在模块内打散，照不到跨模块顺序依赖）。

| seed | 首次结果 | 耗时 |
|---|---|---|
| 1001 | ✅ 67 passed | 54.59s |
| 2002 | ✅ 67 passed | 56.00s |
| 3003 | ❌ **1 failed, 66 passed**, 24 deselected | 63.33s |

**红的那条**：`tests/e2e/baseline_1b/test_kernel_actions_and_url.py::test_k2_note_action_opens_the_editor_and_the_save_lands_a_note_record[chromium]`，
抛在 `tests/e2e/helpers.py:823`：`AssertionError: 8.0s 内 notes.json 没有稳定到 1 条，实际 0 条：[]`。
用例开头那句隔离前置 `read_notes(...) == []` **过了**，所以隔离 fixture 是好的，不是脏数据。

**分类（§7 纪律 2：重试只分类，不翻盘）**：seed 3003 原样重放两次——`67 passed` 54.75s、
`67 passed` 53.14s。**同一个 seed ⇒ 同一个收集顺序，却两绿一红**，因此这是 **flaky，不是顺序依赖**。
本闸要照的「用例间顺序依赖」那一类缺陷，三个 seed 都没有照出来。但通过条件是「**首次**通过」，
所以本项**仍然不过**，Phase 3 仍被它挡着。

seed 3003 里 K-2 前后的实际顺序（第 34–38 位），留给需要原样重放的人：
`test_harness_helpers::test_library_lists_every_book_the_corpus_fixture_builds` →
`test_kernel_overlay_geometry::test_k3a_overlay_is_fixed_and_has_no_containing_block_ancestor[tooltip]` →
**K-2** → `test_write_create_annotations::test_w1_real_mouse_drag_creates_marker_and_survives_reload` →
`test_library_nav_and_collections::test_x2d_selection_marks_only_book_cards_and_rows_not_status_pills`。

#### 这条 flaky 到底是测试侧还是产品侧——**分不出来，而且分不出来本身是缺陷**

这个区分不是学术问题，它决定代价：测试侧的修法要动 `helpers.py` / `baseline_1b/**`，两者都在冻结集里，
**改一个字节 soak 计数 10 → 0**；产品侧的修法落在 `src/`，不清零。

查下来的事实是：`saveNote()` → `createAnnotation()` 这条写路径上有**六个把失败吞掉的出口**，
1–5 每一条的可观察结果都与 seed 3003 那次红**逐字相同**（编辑器正常开、点了 Save、盘上 0 条、哪儿都不报错）：

| # | 位置 | 吞掉的是什么 |
|---|---|---|
| 1 | `static/js/annotations.js:1145` | `!currentRange \|\| !contentEl` → `return` |
| 2 | `annotations.js:1150` | 拿不到 `bookId` / `chapterIndex` → `return` |
| 3 | `annotations.js:1158` | `offsetFromNode` 返回 `null`（iframe 重渲染后 range 指向旧文档）→ `return` |
| 4 | `annotations.js:58` | `fetch(...).catch(() => null)` —— 网络层失败变成 `null` |
| 5 | `annotations.js:1200` | 拿到 `resp` 后**从不检查 status**，4xx/5xx 与 200 走同一条路 |
| 6 | `annotations.js:1105` | `text` 为空 → `return`（良性，但形状相同） |

1、2、3 只写 `console.log`，而 e2e 不捕获浏览器 console；4、5 连 log 都算不上诊断信息。
同一个文件 `:69` 就有现成的 `showToast()`，写路径一次都没调用。

六条里 `:58` 那条是 **011 WI-5b（`cc6bb18`）新加的**，其余五条追到 `20b1f05`（2025-12-27）；责任划分写在 [009 欠账 #43](./009-e2e-annotations.md)。

所以**不能**断言「8s 等太短」（测试侧）——按 1–5 任意一条，请求可能**根本没发出去**，等 80s 也是 0 条；
也**不能**断言产品有保存竞态——没有证据。旁证只有一条：红的那次 63.33s，其余各次约 54s，机器当时偏忙。

**结论与建议**：先补可观测性，再谈修。补的位置全在 `src/`，**不碰冻结集、不清零**。立为
[009 欠账 #42 / #43](./009-e2e-annotations.md)。在那之前，第 3 项维持 FAIL。
