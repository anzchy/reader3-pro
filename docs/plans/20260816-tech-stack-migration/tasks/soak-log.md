# `baseline_1b` soak 台账

> **状态：G2 已达成（达成之日 = 2026-09-06）。~~计数于 2026-09-21 清零一次，正在重数。~~**
> **⬛ 2026-09-29：批次 `B1` 已判定通过**（见下方「批次声明」）；Phase 3 还须机制挑战闸第 1 项在最终候选 `commit` 上通过（§7 批次规则 4）。
> **⬛ 2026-09-30：B1 不单独放行 012**——012 开工要在它开分支的那个 `commit` 上新跑一批，规则只在 迁移计划 §7「012 开工核验」；本台账只记结果。
> **⬛ 2026-09-28：计数规则换成批次规则**（[迁移计划 §7「soak 门槛」](../plan-tech-stack-migration.md)开头六条，维护者 2026-09-28 裁定；
> 评审记录见 [`review-soak-gate-20260928.md`](../review-soak-gate-20260928.md)）。下表现有各行**原样保留、一行不改**，
> 但**不计入任何批次**——「正在重数」那句自本日起只描述 09-21 到 09-28 的事实。~~第一批尚未声明~~（⬛ 2026-09-29：第一批 `B1` 已声明并通过），见下方「批次」。
> `suite_hash` **重新冻结**在 `1e868c7bf811`——~~覆盖面里再动一个字节，下表全部作废、从零重数。~~
> （⬛ 2026-09-29：按批次规则读——覆盖面里再动一个字节，已通过的批次就不再覆盖新 `suite_hash`，须在新值上另开一批；表中各行照旧不改。）
> （⬛ 2026-09-30：`019-frozen-set-debts` 已把它改为 `6dcbb1110288`，见变更史首条；新批次在合入后开。）
> （⬛ 2026-10-02：023（PR #34）再改为 `abfc0cc9c59e`；该值上的批次 `B2` 已判定通过（`94dd1e0`），见下方「批次声明」与变更史首条。）
> 前值 `2747100dadf6` 已作废；作废的理由、被作废的那 10 行、以及为什么这笔代价是有意付的，
> 写在下方「`suite_hash` 的变更史」第一条。
> **2026-09-23 起下表不再是空的：清零后的首行已落账**（`baddc61`，green）。此前「下表现在是空的，
> 这是真实状态，不是漏记」那句留在这里作为上下文——它描述的是 09-21 到 09-23 之间的真实状态。
> 一个时点上的坑同样写在那一条里：改动今天还在 `011-backend-refactor` 分支上，`master`
> 侧八条冻结路径一个字节没动，所以**正式的清零发生在 011 合入那一刻**；表提前退空，是因为
> 那 10 行已经买不到 Phase 3 的通行证了，留着只会让次数命令数出一个骗人的 10。
>
> **本表头不写派生计数，也不写派生日期——一律现算，以下方数据行为准。**
> 此前这里写死过「门槛进度 4 / ≥10 次，跨度 1 / ≥5 个工作日」与「最早解锁日期是 2026-09-11」，
> 两者都到期变烂；后者还把复核者引到过「还要再等 4 个工作日」这个错误结论上。要留的是**算法**，
> 不是**当时的那个答案**：
>
> - ~~**次数**：`grep -cE '^\| 20[0-9]{2}-' docs/plans/20260816-tech-stack-migration/tasks/soak-log.md`~~
> - ~~**跨度**：先取首行与第十行的 `ts_utc` ——
>   `grep -E '^\| 20[0-9]{2}-' docs/plans/20260816-tech-stack-migration/tasks/soak-log.md | sed -n '1p;10p'`；~~
>   （⬛ 2026-09-28：两条都被批次规则取代——跨度取消，次数改为按批次数，命令见下。）
> - **批次判决**：`uv run python scripts/soak_run.py --verdict <批次 ID>`（只读；退出码 0 = PASS，其余一律非 0）。
>   它取该批声明的起始 `ts_utc` 起、按台账顺序的前 10 行，要求恰好 10 行、全为 `green`、且 commit / suite_hash /
>   browser / os 与声明逐字相同；窗口内任一行不符即 FAIL，并指出第一处不符的行与列——**不跳行**。
>   声明缺失、重复或格式不合法同样 FAIL。
>
>   （⬛ 2026-09-29：下面两条人工口径被上面的 `--verdict` 取代，只留作脚本不可用时的参考，**不作判据**——
>   `sort | uniq -c` 丢了行序，窗口内夹一行别的 commit 时它看得出，但说不出是第几行。）
> - **本批的行**：取批次声明里的起始 `ts_utc`，数它起的前 10 行 ——
>   `grep -E '^\| 20[0-9]{2}-' docs/plans/20260816-tech-stack-migration/tasks/soak-log.md | awk -v s='<起始 ts_utc>' '$2>=s' | head -10`
> - **是否同批且全绿**：把上一条的输出接到
>   `awk '{print $4, $6, $10, $12, $14}' | sort | uniq -c`（依次是 commit / result / suite_hash / browser / os）。
>   输出**恰好一行、计数恰好 10、`result` 为 `green`**，且四个值与该批声明逐字相同，这一批才是 10/10。
>   出现第二行（任一次 red，或任一列不同）就不是同一批。
>
>   **怎么判**不在这里，判据的唯一定义处是迁移计划 §7，本文件只说这几行怎么取。~~「核对 10 条同批记录」的判决命令
>   将来进 `scripts/soak_run.py`，落地后以脚本为准。~~（⬛ 2026-09-29：已落地，即上面的 `--verdict`。）
>
> **追加前的干净检查（2026-09-29 起）。** `soak_run.py --append` 要求**整棵工作树**干净——含已暂存改动与未跟踪文件，
> 只豁免台账本身（须在该工作树内）与本次 log 目录下**未跟踪的 `.log` 文件**；log 目录若与 `suite_hash` 覆盖路径重叠、
> 含已跟踪的 `.py` 或就是仓库根，则不豁免任何东西。不干净即拒绝落账（退出码 2）。主工作区通常带着
> 无关改动，所以一批要在被测 SHA 的干净 detached worktree 里跑，用 `--ledger` 把行写回主工作区的台账（B1 的做法）。
>
> **批次（2026-09-28 起）。** 批次 ID 写在这里，不写成表的第九列：表头八列是 `scripts/soak_run.py` 与
> `tests/unit/test_soak_log_contract.py` 共同钉住的契约。
> 每批开跑前在下面追一行声明，格式：`批次 ID｜起始 ts_utc｜commit｜suite_hash｜browser｜os`。依赖锁不单列——
> `uv.lock` 与 `package-lock.json` 都进版本库，`commit` 固定即锁固定。`--verdict` 按严格语法解析声明：
> 六个字段各自用反引号包住、以全角 `｜` 分隔，os 之后不得再有文字（「终止」「判定」等注记写在下一行缩进的续行里）；
> commit 照抄 `soak_run.py` 打印的那一行（短 SHA 逐字比较）。任一行声明写错，所有批次的判决都 FAIL。一批的数据行 = 起始时刻起的前 10 行；
> 批次中途 red、或环境故障 / 不完整运行，都在这里给该批注一句「终止」及原因链接，下一批另起一行。
>
> **过渡规则**：2026-09-28 之前落账的各行（含 09-27 那行 red 与 09-28 那行 green）原样保留，**不追认进任何批次**。
> **第一批要等 2026-09-27 那次红灯归因完成之后才能声明**（§7 批次规则 6）。
> （⬛ 2026-09-28：**归因已完成**——产品缺陷，修复 `26bce1d`（PR #28），见下方「红灯归因记录」。第一批可以声明，
> 但必须跑在**包含 `26bce1d` 的 commit** 上；09-28 那行 green 跑在修复之前的 `d3ceaf4`，不代表修复后的代码。）
>
> 批次声明：
>
> - `B1`｜`2026-09-28T15:13:15Z`｜`9be446c`｜`1e868c7bf811`｜`chromium-1234`｜`darwin-25.3.0`
>   ——在 `9be446c` 的干净 detached worktree 里跑（被测树与该 SHA 逐字节一致；本声明所在的 commit 只改台账）；
>   行用 `--ledger` 写回主工作区，10 次跑完前不提交。
>   **判定：通过**——上面的核对命令输出恰好一行 `10 9be446c green 1e868c7bf811 chromium-1234 darwin-25.3.0`
>   （2026-09-28T15:14:07Z – 15:22:26Z，每次 68 passed，53.8–56.4s）。只满足次数；机制挑战闸第 1~~、3~~ 项仍须在最终候选上过（⬛ 2026-09-30：第 3 项只在 `suite_hash` 变了时重跑，见 迁移计划 §7「012 开工核验」）。
> - `B2`｜`2026-10-01T16:56:16Z`｜`94dd1e0`｜`abfc0cc9c59e`｜`chromium-1234`｜`darwin-25.3.0`
>   ——`suite_hash` 经 019（PR #29）与 023（PR #34）两次改覆盖面后在 master 上的首批，见下方变更史首条。
>   在 `94dd1e0`（024 合入后的 master）的干净 detached worktree 里跑；行用 `--ledger` 写回主工作区，10 次跑完前不提交。
>   **判定：通过**（⬛ 2026-10-02）——`uv run python scripts/soak_run.py --verdict B2` 输出
>   `PASS B2 10/10（2026-10-01T16:57:14Z – 2026-10-01T17:14:08Z）`（每次 132 passed、138 deselected，107.5–119.4s）。
>   只满足次数；机制挑战闸第 1 项须在最终候选 `commit` 上通过，第 3 项因 `suite_hash` 变了须重跑——都按
>   [迁移计划 §7「012 开工核验」](../plan-tech-stack-migration.md)办，本文件不复述。
>   这 10 行的 `log` 列指向跑批会话的临时目录，不随仓库保存；可复核的是行本身与上面的判决输出。
>
> ⚠️ **次数数满 ≠ Phase 3 解锁。** §7 里另有**机制挑战闸**三项（干净 Linux / CI 环境、CPU 压力、
> 随机化 pytest 收集顺序），原定三项都是阻塞性的——**2026-09-24 起第 2 项经维护者裁定降为不阻塞的记录项**，
> 第 1、3 项仍阻塞（当前状态见下方「机制挑战闸执行记录」）；三项都**不计入这里的连绿次数**——它们改变了抽样条件。
> 同一节还写了这道门槛的**证明力界定**（2026-09-28 起是批次规则第 5 条）：它证明的是该候选版本在**一个本地运行剖面**下的成功记录，
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
| 2026-09-23T10:51:23Z | baddc61 | green | 56.63 | 1e868c7bf811 | chromium-1234 | darwin-25.3.0 | .claude/tdd-guardian/soak-logs/2026-09-23T105123Z-baddc61-253060125-89fc9e.log |
| 2026-09-25T22:31:21Z | 4178b8a | green | 61.65 | 1e868c7bf811 | chromium-1234 | darwin-25.3.0 | .claude/tdd-guardian/soak-logs/2026-09-25T223121Z-4178b8a-373044625-cdfb95.log |
| 2026-09-27T04:00:05Z | 8e1cf48 | red | 94.83 | 1e868c7bf811 | chromium-1234 | darwin-25.3.0 | .claude/tdd-guardian/soak-logs/2026-09-27T040005Z-8e1cf48-760122083-28bd9f.log |
| 2026-09-28T04:00:05Z | d3ceaf4 | green | 60.72 | 1e868c7bf811 | chromium-1234 | darwin-25.3.0 | .claude/tdd-guardian/soak-logs/2026-09-28T040005Z-d3ceaf4-644042416-3516fc.log |
| 2026-09-28T15:14:07Z | 9be446c | green | 55.12 | 1e868c7bf811 | chromium-1234 | darwin-25.3.0 | .claude/tdd-guardian/soak-logs/2026-09-28T151407Z-9be446c-244729000-f79935.log |
| 2026-09-28T15:15:03Z | 9be446c | green | 54.73 | 1e868c7bf811 | chromium-1234 | darwin-25.3.0 | .claude/tdd-guardian/soak-logs/2026-09-28T151503Z-9be446c-555512666-267c8f.log |
| 2026-09-28T15:15:59Z | 9be446c | green | 56.35 | 1e868c7bf811 | chromium-1234 | darwin-25.3.0 | .claude/tdd-guardian/soak-logs/2026-09-28T151559Z-9be446c-500978291-2efb8b.log |
| 2026-09-28T15:16:56Z | 9be446c | green | 54.89 | 1e868c7bf811 | chromium-1234 | darwin-25.3.0 | .claude/tdd-guardian/soak-logs/2026-09-28T151656Z-9be446c-958374416-144a97.log |
| 2026-09-28T15:17:51Z | 9be446c | green | 54.42 | 1e868c7bf811 | chromium-1234 | darwin-25.3.0 | .claude/tdd-guardian/soak-logs/2026-09-28T151751Z-9be446c-970721333-52bc27.log |
| 2026-09-28T15:18:46Z | 9be446c | green | 54.63 | 1e868c7bf811 | chromium-1234 | darwin-25.3.0 | .claude/tdd-guardian/soak-logs/2026-09-28T151846Z-9be446c-181060250-62869a.log |
| 2026-09-28T15:19:41Z | 9be446c | green | 55.35 | 1e868c7bf811 | chromium-1234 | darwin-25.3.0 | .claude/tdd-guardian/soak-logs/2026-09-28T151941Z-9be446c-081453958-31848a.log |
| 2026-09-28T15:20:37Z | 9be446c | green | 54.12 | 1e868c7bf811 | chromium-1234 | darwin-25.3.0 | .claude/tdd-guardian/soak-logs/2026-09-28T152037Z-9be446c-769938875-8cdc18.log |
| 2026-09-28T15:21:32Z | 9be446c | green | 53.84 | 1e868c7bf811 | chromium-1234 | darwin-25.3.0 | .claude/tdd-guardian/soak-logs/2026-09-28T152132Z-9be446c-126970833-0e77bb.log |
| 2026-09-28T15:22:26Z | 9be446c | green | 53.97 | 1e868c7bf811 | chromium-1234 | darwin-25.3.0 | .claude/tdd-guardian/soak-logs/2026-09-28T152226Z-9be446c-637035250-74d0a3.log |
| 2026-10-01T16:57:14Z | 94dd1e0 | green | 111.71 | abfc0cc9c59e | chromium-1234 | darwin-25.3.0 | /private/tmp/claude-501/-Users-jackcheng-Documents-01-Coding-Front-end-projects-reader3-pro/bc5b24e0-7ce5-4a9a-a73d-be20a60170f4/scratchpad/soak-b2-logs/2026-10-01T165714Z-94dd1e0-819154958-37f45c.log |
| 2026-10-01T16:59:07Z | 94dd1e0 | green | 119.38 | abfc0cc9c59e | chromium-1234 | darwin-25.3.0 | /private/tmp/claude-501/-Users-jackcheng-Documents-01-Coding-Front-end-projects-reader3-pro/bc5b24e0-7ce5-4a9a-a73d-be20a60170f4/scratchpad/soak-b2-logs/2026-10-01T165907Z-94dd1e0-076851833-b44212.log |
| 2026-10-01T17:01:08Z | 94dd1e0 | green | 114.84 | abfc0cc9c59e | chromium-1234 | darwin-25.3.0 | /private/tmp/claude-501/-Users-jackcheng-Documents-01-Coding-Front-end-projects-reader3-pro/bc5b24e0-7ce5-4a9a-a73d-be20a60170f4/scratchpad/soak-b2-logs/2026-10-01T170108Z-94dd1e0-467569375-40835e.log |
| 2026-10-01T17:03:04Z | 94dd1e0 | green | 114.6 | abfc0cc9c59e | chromium-1234 | darwin-25.3.0 | /private/tmp/claude-501/-Users-jackcheng-Documents-01-Coding-Front-end-projects-reader3-pro/bc5b24e0-7ce5-4a9a-a73d-be20a60170f4/scratchpad/soak-b2-logs/2026-10-01T170304Z-94dd1e0-465062166-42d906.log |
| 2026-10-01T17:05:00Z | 94dd1e0 | green | 107.5 | abfc0cc9c59e | chromium-1234 | darwin-25.3.0 | /private/tmp/claude-501/-Users-jackcheng-Documents-01-Coding-Front-end-projects-reader3-pro/bc5b24e0-7ce5-4a9a-a73d-be20a60170f4/scratchpad/soak-b2-logs/2026-10-01T170500Z-94dd1e0-498198875-b057b7.log |
| 2026-10-01T17:06:48Z | 94dd1e0 | green | 109.56 | abfc0cc9c59e | chromium-1234 | darwin-25.3.0 | /private/tmp/claude-501/-Users-jackcheng-Documents-01-Coding-Front-end-projects-reader3-pro/bc5b24e0-7ce5-4a9a-a73d-be20a60170f4/scratchpad/soak-b2-logs/2026-10-01T170648Z-94dd1e0-622310583-0ec95d.log |
| 2026-10-01T17:08:38Z | 94dd1e0 | green | 108.8 | abfc0cc9c59e | chromium-1234 | darwin-25.3.0 | /private/tmp/claude-501/-Users-jackcheng-Documents-01-Coding-Front-end-projects-reader3-pro/bc5b24e0-7ce5-4a9a-a73d-be20a60170f4/scratchpad/soak-b2-logs/2026-10-01T170838Z-94dd1e0-962314541-d637e6.log |
| 2026-10-01T17:10:28Z | 94dd1e0 | green | 108.13 | abfc0cc9c59e | chromium-1234 | darwin-25.3.0 | /private/tmp/claude-501/-Users-jackcheng-Documents-01-Coding-Front-end-projects-reader3-pro/bc5b24e0-7ce5-4a9a-a73d-be20a60170f4/scratchpad/soak-b2-logs/2026-10-01T171028Z-94dd1e0-775074375-8c60c0.log |
| 2026-10-01T17:12:16Z | 94dd1e0 | green | 111.18 | abfc0cc9c59e | chromium-1234 | darwin-25.3.0 | /private/tmp/claude-501/-Users-jackcheng-Documents-01-Coding-Front-end-projects-reader3-pro/bc5b24e0-7ce5-4a9a-a73d-be20a60170f4/scratchpad/soak-b2-logs/2026-10-01T171216Z-94dd1e0-622938041-d50f57.log |
| 2026-10-01T17:14:08Z | 94dd1e0 | green | 109.97 | abfc0cc9c59e | chromium-1234 | darwin-25.3.0 | /private/tmp/claude-501/-Users-jackcheng-Documents-01-Coding-Front-end-projects-reader3-pro/bc5b24e0-7ce5-4a9a-a73d-be20a60170f4/scratchpad/soak-b2-logs/2026-10-01T171408Z-94dd1e0-236542125-6f3e09.log |

---

## CI 运行记录

⬛ 2026-10-07 新开（[018 WI-7](./018-library-routes.md) / §6 Q9）。这里记 CI `tests.yml` 的 `e2e` job 在某个**合并头**上的核验运行：run id、`headSha`、浏览器、`suite_hash` 与条数。**这些不是 soak 台账行**——`os` 是 `linux-*`，混进上方台账即不成批（迁移计划 §7 批次规则 3）；job 本身也不传 `--append`，本节由人工回写，**没有**经 `soak_run.py --append` 写入。

| 记录日 | 用途 | run | 事件 | `headSha` | attempt | 结论 | browser | `suite_hash` | `baseline_1b` | 其余 e2e | `os` |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-07 | 018 门槛 9 / 11（PR #37 冻结头 `H`） | [37635190616](https://github.com/anzchy/reader3-pro/actions/runs/37635190616) | `pull_request` | `b6025ba`（跑的是 GitHub 合成合并 ref `6c9dcb5`） | 1 | success | chromium-1234（Chrome for Testing 151.0.7922.34） | `abfc0cc9c59e` | 132 passed / 138 deselected，154.44s，green | 122 passed / 16 skipped | linux-6.17.0-1022-azure |
| 2026-10-07 | 018 门槛 9（合并头上的 dispatch） | [37635220594](https://github.com/anzchy/reader3-pro/actions/runs/37635220594) | `workflow_dispatch` | `b6025ba` | 1 | success | chromium-1234（Chrome for Testing 151.0.7922.34） | `abfc0cc9c59e` | 132 passed / 138 deselected，147.43s，green | 122 passed / 16 skipped | linux-6.17.0-1022-azure |

同一 `H` 上的 `lint.yml` 为 run [37635190619](https://github.com/anzchy/reader3-pro/actions/runs/37635190619)（success，attempt 1）。`b6025ba` 于 2026-10-07T14:44:36Z 经 `--match-head-commit` 合入 `master`，合并 commit `74384b1`（与 `b6025ba` 同树）；合入记录只在 [018 §8](./018-library-routes.md)。

---

## 红灯归因记录

每次 red 一条：失败签名、证据、根因（产品缺陷 / 测试缺陷 / 环境）、修复、确认。判据见迁移计划 §7 批次规则 2。

### 2026-09-27 `8e1cf48` red —— **产品缺陷**，修复 `26bce1d`（PR #28）（2026-09-28 维护者认可）

- **失败签名**：K2（复制动作）——剪贴板文本正确，但注释工具条在 Copy 之后 5 秒仍可见。明细见上表该行 `log`。
- **根因：两个机制，都在 `annotations.js` 的 `handleRenditionSelection`。**
  1. **自激循环**：每个 epub.js `selected` 事件都 `removeAllRanges()` ＋ `addRange()` 重写 iframe 选区；重写触发
     `selectionchange`，epub.js 约 250ms 后再发一次 `selected`。于是任何「关掉工具条但选区还在」的路径
     （Copy / Ask AI / Escape / 外层页面 mousedown）每约 250ms 被撤销一次——与「5 秒后仍可见」吻合。
  2. **尾随一拍**：K2 点 Copy 的时刻早于 epub.js 为用户自己的选区发出第一个 `selected`，这一拍把工具条重开一次。
- **修复**（`26bce1d`）：选区与目标 range 相同时不重写（`sameRange`，断开机制 1）；记住工具条关闭时的 range
  （`dismissedRange`），同一 range 的尾随 `selected` 不再重开，新的鼠标选择清掉该标记（机制 2）。只加 `sameRange` 时 8 例仍红 4 例。
- **证据**：修复前用插桩的 K2 复现了 09-27 的失败；回归测试 `tests/e2e/test_selection_toolbar_stays_closed.py`
  （4 种关闭路径 × 2 种时机）在修复前 8/8 红、修复后 8/8 绿。该文件在冻结集之外，`suite_hash` 不变（`1e868c7bf811`）。
- **确认的强度，如实写**：修复后冻结的 K2 单独跑 10/10 绿、e2e 全量 3 跑全绿——但 K2 修复前本来也多数是绿的，
  这两组只是弱证据；决定性的证据是 `before_first_tick` 那几例的「修复前必红」。~~**修复后尚无 soak 行。**~~（⬛ 2026-09-30：批次 `B1` 的 10 行全部在修复后——修复 commit `26bce1d` 是 `9be446c` 的祖先。）
- **遗留**（不影响 soak）：仅用键盘重新选中完全相同的 range 时，工具条保持关闭——未测。

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

当前 `suite_hash` 值：`abfc0cc9c59e`（⬛ 2026-10-02：`94dd1e0` 上实测，非誊抄——`soak_run.py` 为批次 `B2`
落账的 10 行逐行打印的就是它；见下方变更史首条）。
~~当前值 `1e868c7bf811`（2026-09-21 实测输出，非誊抄：`scripts/soak_run.py`
dry run 在 68/68 green 的那一次同时打印出来的）。~~（⬛ 2026-10-02：已被上一行取代；`B1` 的 10 行仍是这个值。）
（⬛ 2026-09-30：`019-frozen-set-debts` 改了覆盖面，该分支上实测为 `6dcbb1110288`，`B1` 不覆盖它；
~~本行在 master 上新值的批次声明前保持原值，见下方变更史首条。~~）
（⬛ 2026-10-02：新值上的批次 `B2` 已声明并通过，本行随之改为 `abfc0cc9c59e`。表中值不同于它的行**不因此**变成
pre-freeze：契约测试按「等于当前值 / 落在某个已声明批次的 10 行窗口内且四项身份与声明相同 / 早于第一条批次声明」
三者之一放行，见 `tests/unit/test_soak_log_contract.py` Case 4。）
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

- **`abfc0cc9c59e` ← 2026-10-01 `023-frozen-set-prep`（PR #34，覆盖面改动在 `9d504bd`）。前值 `6dcbb1110288`（019）在 master 上
  从未声明过批次；`B1` 只覆盖 `1e868c7bf811`，**不覆盖本值**。本值上的首批是 `B2`（`94dd1e0`），已判定通过。**
  - **为什么会变**：`eda9694`（019 合入）到 `94dd1e0` 之间，八条覆盖路径只被 `9d504bd` 一个提交动过
    （`git diff --name-status eda9694 94dd1e0 -- <八条>` ＝ 5 个新增、2 个修改）。按 `git ls-tree` 重算：
    `eda9694` 与 `9d504bd^` 都是 `6dcbb1110288`，`9d504bd` 与 `94dd1e0` 都是 `abfc0cc9c59e`。
    1. 009 欠账 #65：`notes_conflict_support.py` 与四个原挂在 `UNGROUPED_E2E_MODULES` 白名单里的模块
       （`test_conflict_resolution_single_flight.py`、`test_conflict_settled_text_keeps_its_base_etag.py`、
       `test_notes_write_failure_is_attributable.py`、`test_stored_cfi_must_agree_with_quote.py`）迁入 `tests/e2e/baseline_1b/`——
       支撑模块随之进覆盖面，堵上「冻结集依赖冻结集外的文件」那个洞。`EXPECTED_BASELINE_ITEMS` 76 → **132**、
       `EXPECTED_UNGROUPED_ITEMS` 68 → **12**，`tests/e2e` 全量不变。
    2. 009 欠账 #67：`tests/e2e/baseline_1b/test_write_recolor_and_delete.py` 的 W-5a-③ docstring（四件事 → 六件事，修一处悬空指针）。
    3. 009 欠账 #68：`tests/e2e/helpers.py` 的 `wait_for_note_text` 死线后重读一次，已匹配即返回。
  - 019 那条里的三处改动（#49 / #62 / 017 #10）**也在本值里**——本值是在 `6dcbb1110288` 之上再改，不是替代它。
  - `src/` 零改动；这一次清零是有意的（`9d504bd` 提交说明：「suite_hash 有意变化（一次重置，由协调者结算 soak-log）」）。
  - 表头「当前 `suite_hash` 值」随 `B2` 判定通过改为本值（2026-10-02）。机制挑战闸第 1、3 项的重跑归属见 §7「012 开工核验」，不在本文件。

- **`6dcbb1110288` ← 2026-09-30 `019-frozen-set-debts`（冻结集欠账窗口）。前值 `1e868c7bf811` 在本分支上不再是当前值；
  批次 `B1` 只覆盖前值，**不覆盖新值**。**
  - **为什么会变**：覆盖面里动了三处。
    1. `tests/e2e/helpers.py` —— 009 欠账 #49（`40a0fce`）：notes.json 轮询从同步墙钟 `time.sleep` 改为经 `page=` 传入、
       用 `page.wait_for_timeout` 泵事件；`baseline_1b/**` 的调用点随之补 `page=`。
    2. `tests/e2e/baseline_1b/test_selection_toolbar_stays_closed.py` —— 009 欠账 #62（`fa3ac17`）：从 `tests/e2e/` 挪入 `baseline_1b`。
    3. `tests/e2e/baseline_1b/test_write_recolor_and_delete.py` —— 017 发现 #10（`789602c`）：W-5a-③ 追加渲染文本与 mark id 断言。
  - **本分支上没有声明批次，也不追加台账行**。新值上的新一批、第 3 项重跑、第 1 项首跑通过，按
    迁移计划 §7「012 开工核验」在合入 master 之后做（本文件只留三条 §7 链接，见「三类清零触发器」）；
    本分支上第 2 项的记录性重跑见下方「#49 修后」一节。
  - ~~表头「当前 `suite_hash` 值」一行在合入并在新值上声明批次之前**不改**：台账各行仍是前值，改了会让它们被误判为 pre-freeze。~~
    （⬛ 2026-10-02：`6dcbb1110288` 在 master 上从未声明过批次——023 先把它改掉了；新值 `abfc0cc9c59e` 上的 `B2`
    已声明并通过，表头随之改了。「误判为 pre-freeze」那个顾虑由契约测试改按批次窗口放行来解决，见上一条。）

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

> ⬛ 2026-09-28 起本节标题与正文里的「清零」一律读作「不是同一批／批次终止」；标题保留是为了不断链。

- `commit`、`suite_hash` 或依赖锁变了 ⇒ 不是同一批（2026-09-28 前读作「清零」；`commit` 这一项是 2026-09-28 新增的）—— [§7 台账字段（canonical）＋ 什么会让计数作废](../plan-tech-stack-migration.md#台账字段canonical-什么会让计数作废)
- `browser` 或 `os` 变了 ⇒ 不是同一批（2026-09-28 前读作「清零」）—— [§7 台账字段（canonical）＋ 什么会让计数作废](../plan-tech-stack-migration.md#台账字段canonical-什么会让计数作废)
- 任意一次 `red` ⇒ 批次终止，查根因后从第 1 次重开（2026-09-28 前读作「清零」）—— [§7 台账字段（canonical）＋ 什么会让计数作废](../plan-tech-stack-migration.md#台账字段canonical-什么会让计数作废)

~~生产代码变（`commit` 列变）**不**清零；~~（⬛ 2026-09-28 反转：`commit` 变了就不是同一批，理由见 §7 同一小节的订正注。）其余四个尚未激活的 acceptance 组怎么改也**不**清零——
它们不在上面那条命令的覆盖路径里。

### 冻结前的行怎么标

`suite_hash` 与本文表头记录的当前值不同的数据行，**必须在该行里显式写上 `pre-freeze`**，
它不计入 ~~≥10 次的分母~~任何批次（⬛ 2026-09-28 批次语义）。没有第二种标法：`result` 列只有 `green` / `red`，
拿一次冻结前的绿去凑数在台账上是无痕的，靠的就是这个标记。

**复核方式**：把上面那条命令复制出来跑一遍，输出应等于表头记的值。这是 review 动作，由人执行——
自动化用例**不**断言「表头的值 == 现在算出来的值」，那会让每一次合法的套件改动都红一条无关的用例，
而冻结的语义本来就是「这个值不随之后的改动走」。台账形状的机器可解析性由
`tests/unit/test_soak_log_contract.py` 守。

---

## 两条纳入/排除口径及其代价

> ⬛ 2026-09-28 起下面两节里的「清零」「计数归零」「从零重数」一律读作「`suite_hash` 变了 ⇒ 下一批要在新值上重开（约 10–15 分钟）」；
> 代价随之从「丢掉数周计数」缩成「多跑一批」。纳入/排除的取舍本身不变。原文保留。

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

**当前状态（2026-09-24 更新）：第 1 项 PASS、第 3 项 PASS、第 2 项 2026-09-23 实测 FAIL，
2026-09-24 经维护者裁定降为不阻塞的记录项。~~机制挑战闸不再阻塞 Phase 3 / 012；soak 计数仍然阻塞。~~**
（⬛ 2026-09-28 / 09-30：这半句作废——按批次规则 4，第 1 项须在最终候选 `commit` 上重新首次通过，**仍阻塞 012**；「soak 计数」已换成批次；两者都落在 迁移计划 §7「012 开工核验」。）
（裁定见下方「第 2 项归因」一节末尾；规则正文在迁移计划 §7。）

第 2 项 2026-09-21 是「⚠️ 字面首绿，建议记作未过」；**2026-09-23 按欠账 #48 用 n=5 复跑，
7 跑 6 红，改判为实测 FAIL**——从一条建议变成一个结果。
六条红全部落在 `tests/e2e/helpers.py` 的 8 秒等待上，而该文件在冻结集里，
**由此构成一个死锁**：见下方「第 2 项复跑」一节，那里也说明了为什么现在是解开它最便宜的时刻。
（⬛ 2026-09-24：归因已做完——是测试夹具自伤，不是产品缺陷；「死锁」随第 2 项降级而解除，
见「第 2 项归因」一节。）

次数那一条另算：≥10 次 / ≥5 工作日在清零后重数，**2026-09-23 落了首行**，上方台账现为 1 行。
（⬛ 2026-09-28：这一句的规则已被批次规则取代，见表头「批次」；按批次规则 4，第 1 项须对最终候选 `commit` 重新首次通过。）

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

### ⬛ 第 2 项复跑：**FAIL**（2026-09-23，7 跑 6 红）

2026-09-21 把第 2 项判成「⚠️ 字面首绿，建议不认」并立了[欠账 #48](./009-e2e-annotations.md)：
通过条件是 n=1，而它测的是一个**分布**。本次按 #48 的建议用 n=5 重跑，另加 2 跑专为拿红掉的用例名。

跑在 `master` 的 `baddc61` 上（017 已合入），`suite_hash` 全程 `1e868c7bf811`，
10 个忙等进程（= `sysctl -n hw.ncpu`）。**压力进程与 lane 在同一个 shell 调用里起**，
load 在 **lane 结束那一刻**读、**杀压力之前**读——这两条是 2026-09-20 那次作废重做留下的纪律，
不是讲究。七跑一律不带 `--append`：机制闸不计入连绿次数。

| # | 结果 | summary | lane 结束 load |
|---|---|---|---|
| 1 | 🔴 | `1 failed, 67 passed, 72 deselected in 65.12s` | 29.86 |
| 2 | 🔴 | `2 failed, 66 passed, 72 deselected in 73.06s` | 39.96 |
| 3 | 🔴 | `2 failed, 66 passed, 72 deselected in 77.03s` | 131.74 |
| 4 | 🟢 | `68 passed, 72 deselected in 66.79s` | **176.16** |
| 5 | 🔴 | `1 failed, 67 passed, 72 deselected in 77.10s` | 161.45 |
| 6 | 🔴 | `1 failed, 67 passed, 72 deselected in 63.92s` | 23.95 |
| 7 | 🔴 | `3 failed, 65 passed, 72 deselected in 79.02s` | 30.65 |

**7 跑 6 红 ⇒ 第 2 项 FAIL。**

**这个判决不依赖 #48 是否被采纳——两套规则给同一个答案。** 这一点要单独说，因为改 §7 的条文
对「正在被这道闸挡着的人」是有利害关系的，而那个人就是跑这轮的人：

- 按 §7 现行的「**首次**通过」：第 1 跑就是红 ⇒ FAIL。
- 按 #48 建议的「连续 5 次压力下全绿」：6 红 ⇒ FAIL。

**所以本次没有动 §7 的条文，也不需要动它才能得出结论。** #48 的建议仍然成立（n=1 测不了分布），
但它现在是一条「让下一次重跑更可信」的改进，不是本次判决的前提。要不要改条文仍由维护者裁。

**别拿 load 当判别器。** 唯一那次绿（第 4 跑）恰好是全场 load **最高**的一跑（176.16），
而红掉的第 1、6、7 跑 load 只有 23–30。压力**大小**与红绿不成单调关系——这与 2026-09-21
「别把耗时当判别器」是同一类观察：负载**开没开**是相关的，开**多大**不是。

**归因：六条红是同一族断言。** 第 6、7 跑用 `--log-dir` 指到持久目录才拿到用例名——
非 `--append` 模式默认把日志写进跑完即清的临时目录，**第 1–5 跑的用例名因此丢了**，
这是本轮方法上的一处疏漏，补跑两轮才补回来。

| 用例 | 断言 |
|---|---|
| `test_k2_delete_action_removes_the_clicked_annotation_from_disk` | `8.0s 内 notes.json 没有稳定到 0 条，实际 1 条` |
| `test_k2_type_actions_create_an_annotation_of_that_type[marker]` | `8.0s 内 notes.json 没有稳定到 1 条，实际 0 条` |
| `test_k2_type_actions_create_an_annotation_of_that_type[underline]` | 同上 |
| `test_w8a_two_overlapping_annotations_both_persist_and_render` | 同上 |

四条全部经 `tests/e2e/helpers.py:986` 的 `assert_roundtrip` 落到同一个 8 秒等待上，
即 [欠账 #43](./009-e2e-annotations.md) 的家族。

**⚠️ `W-8a` 在红名单里，但它不是 [#44](./009-e2e-annotations.md) 的回归。** 这个区别必须点明：
W-8a 正是 #44 修掉的那条，看见它变红的第一反应会是「上浮又回来了」。实测断言是
`8.0s 内 notes.json 没有稳定到 1 条`，**不是**偏移错误——它走的是超时那条路，和另外三条同族。
**#44 的修复没有退化。**

#### 下一步不是付清零那一刀，是先把归因做完——而归因不用碰冻结集

两件事并排放，看起来像个死锁：

1. 挡住第 2 项的**全部**六条红，都落在 `tests/e2e/helpers.py` 的那个 8 秒等待上。
2. `helpers.py` **在冻结集里**。动它一个字节 ⇒ `suite_hash` 变 ⇒ 按
   [§7 纪律 4](../plan-tech-stack-migration.md) 台账清零、**三项机制闸一并作废**，
   包括刚过掉的第 1 项与第 3 项。

> **⚠️ 本节初稿到此为止，标题写的是「这道闸是一个死锁」，并据此建议「现在就付清零那一刀，
> 因为台账只有 1 行、现在最便宜」。那个结论是错的，当场推翻并改写。**
> 推翻它的是[欠账 #48](./009-e2e-annotations.md) 自己的处置建议第 (3) 条，以及一次核实：
> **`window.Reader3NotesDiag` 已经存在**（`annotations.js:147-206`，有界 FIFO 环形缓冲，
> `record` / `entries` 冻结在 `window` 上），即 [#43](./009-e2e-annotations.md) 的 (i) **已交付**。

死锁只在**两个分支中的一个**上成立，而今天还不知道是哪一个：

| 诊断缓冲会说什么 | 根因 | 代价 |
|---|---|---|
| POST 根本没发出去，或回了非 2xx | **产品缺陷** | 修在 `src/` 里，**冻结集一个字节不动，不清零** |
| POST 发了、回 201，只是盘上轮询没在 8s 内看到 | 测试侧等待太短 | 要改冻结的 `helpers.py` ⇒ 清零 ＋ 三闸作废 |

**这正是 #43 当初存在的全部理由**——在可观测性补上之前这个区分做不了，现在补上了，
就该先去做这个区分，而不是先付一刀不知道该不该付的代价。#48 的处置建议写得更直白：
「POST 发没发、什么状态码，从另一端回答了同一个问题，**不必动冻结集里的 `helpers.py`**」，
并且明确警告**不能因为 `helpers.py` 在冻结集里就默认产品必须迁就 8 这个偶然数字**。

**所以下一步是**：写一条**新的、非冻结的** e2e 用例（新文件不在冻结集里），在 CPU 压力下
复现这族红，红的时候用 `page.evaluate` 把 `window.Reader3NotesDiag.entries()` dump 出来，
按上表二分。预算照 #48 的原文：人工 ≤4 小时 ＋ 无人值守 ≤1 小时。

**只有落到表格第二行，才谈得上「付清零那一刀」。** 到那时「现在最便宜」这个论证才重新成立
（台账 1 行、两道闸各重跑一次即可；等攒到 9 行再改就要付 9 行 ＋ 两道闸）。
**但它是第二步，不是第一步。**

**另外别指望「先攒满 10 次再说」能绕过第 2 项。** 无压力下台账确实攒得起来（今天那行 56.63s 绿，
2026-09-21 也是无压力 9 跑 0 红），但第 2 项要的恰恰是**有压力**下的稳定——
连绿次数与机制闸是两个独立判据，**攒满 10 行不会让第 2 项变绿一度**。

### ⬛ 第 2 项归因：**测试侧**，不是产品缺陷（2026-09-23 实验，2026-09-24 裁定降级）

> **本节是上一节「下一步……先把归因做完」那条的执行结果**，正文由 `docs/plans/_pending/4-gate2-attribution.md`
> 并入（那份草稿当时写在 `010` 分支上，台账不在 010 的允许文件集里，所以先放在 `_pending/`）。
> 维护者的裁定在本节末尾；§7 条文怎么改的，唯一定义处是
> [迁移计划 §7「机制挑战闸」](../plan-tech-stack-migration.md)，此处不复述。

跑在 `010` 的 `293c68f` 上。`git diff baddc61 HEAD -- src tests scripts` 为空——
**产品与测试树与上一节那次 7 跑 6 红的实验逐字节相同**。`suite_hash` 全程 `1e868c7bf811`，
冻结集 8 条路径 vs master 零改动，`scripts/lint_e2e_groups.py` rc=0（收集 140、baseline_1b 68/68）。

**证据已入库**：[`evidence/gate2-attribution-20260923/`](./evidence/gate2-attribution-20260923/)——

| 路径 | 是什么 |
|---|---|
| `diagarm5/` | v5 臂：6 跑 3 红，`logs/run-N.log` ＋ 红那几跑的浏览器侧快照 `dumps/run-N/*.json` |
| `diagarm6/` | v6 臂（加了 `performance` 资源条目）：6 跑 6 红，11 份快照 |
| `diagarm3/` | 更早一版归因臂：5 跑 2 红（run-4、run-5），同样的目录结构 |
| `diag_loop.sh` | 归因臂的驱动脚本：同一压力配方 ＋ `-p e2e_diag_dump` |
| `pressure_run.sh` / `pressure_loop.sh` | `--tracing=retain-on-failure` 那一臂（下方「方法论」表第一行） |
| `control_loop.sh` | 无观测对照臂 |
| `fsync_probe.py` / `fsync_run.sh` | 下方「不是 fsync」那张表的探针 |
| `burn.py` | 忙等压力源 |

诊断工具本体是 [`scripts/e2e_diag_dump.py`](../../../../scripts/e2e_diag_dump.py)。
⚠️ 这些脚本里写死了原作业目录与仓库的绝对路径（例如 `fsync_run.sh` 的 `T=`），
那个作业目录已随 job 清掉——**复跑时把 `T` / 输出目录改成本证据目录或任意临时目录**。
tracing 臂与对照臂的原始输出没有入库，只有驱动脚本；下方「方法论」表里那几行的数字以本节为准。

#### 结论

上一节那张二分表（「POST 没发出去或回非 2xx ⇒ 产品缺陷」vs「发了、回了 201，只是盘上没在 8s 内
可见 ⇒ 测试侧」）**两行都不对**。实测落在它没列的第三种：

> **写请求发出去了，在 8 秒窗口里没回来，然后——它成功了。**

最干净的一例，浏览器侧时间戳（`test_w5a2_recolor_then_repress_marker_adds_a_second_one`）：

| 时刻 | 事件 |
|---|---|
| `sent: 758ms` | POST `/api/notes/smoke_data/0` 发出 |
| 失败快照 | `settled: null` —— 还悬着，断言就是在这一刻判的红 |
| teardown 快照 | **`settled: 8857ms, status: 201`** |

**这条写入成功了，只是用了 8.1 秒。** 测试的 8 秒墙钟在服务端答复之前约 0.9 秒就到期了。
两次快照的 `diag` 都是 `[]`——环是对的，因为根本没有失败可记。

第二例是**删**，形状一模一样
（`test_k2_delete_action_removes_the_clicked_annotation_from_disk`）：

| 时刻 | 事件 |
|---|---|
| `sent: 157ms` | DELETE `/api/notes/smoke_data/0/…` 发出 |
| 失败快照 | `settled: null` |
| teardown 快照 | **`settled: 8207ms, status: 204`** |

v5 臂 **6 跑 3 红**，四条红全部拿到浏览器侧快照，**形状完全一致**：

| 用例 | 方法 | sent | 失败快照 | teardown |
|---|---|---|---|---|
| `test_w5a2_recolor_then_repress_marker…` | POST | 758ms | `null` | **8857ms / 201** |
| `test_k2_delete_action_removes…` | DELETE | 157ms | `null` | **8207ms / 204** |
| `test_w4_new_note_reads_back…` | POST | 178ms | `null` | **8268ms / 201** |
| `test_w5a0_same_color_repress…[underline]` | POST | 728ms | `null` | **8749ms / 201** |

**四例全部成功**（201 ×3、204 ×1），四例的 `diag` / `late_diag` 全是 `[]`。

##### 同一份文档里，读是毫秒，写是秒——这条最要紧

`w4` 那例的完整 fetch 台账（同一个 document，同一段压力，前后差十几毫秒）：

| 请求 | sent | settled | 用时 |
|---|---|---|---|
| GET `/api/notes/smoke_data/0` | 83ms | 93ms | **10ms** |
| GET `/api/notes/smoke_data/0` | 163ms | 167ms | **4ms** |
| POST `/api/notes/smoke_data/0` | 178ms | 8268ms | **8.3s** |

`w5a0` 同形（GET 14ms / 5ms，POST 8.0s）。
**这一条否掉了「机器慢、整条链路一起饿死」的读法**——真那样的话读也该慢。
差异只出在写路径上。

> **别把「都刚好卡在 8 秒线外」读成某种机制。** 那是**截断造成的选择效应**：
> 快照只在失败时拍，而失败的定义就是「超过 8 秒」——所以凡是被拍到的请求，
> 必然 settle 在 8 秒之后。这不构成「有什么东西卡到 8 秒才放行」的证据。
> 顺带排除掉一个听上去很顺的猜想：`live_server` 是**独立子进程**
> （`conftest.py:235`，`Path(sys.executable).parent / "reader3-server"`），
> 不是 pytest 进程里的线程，所以「纯 Python 的 8 秒轮询把服务端的 GIL 饿死」
> 这条解释**不成立**。

产品一次都没有「把失败装成成功」：**没有可吞的失败**。四例全部 2xx。

#### 慢在哪：**不是 fsync**，这条排掉了

`save_annotations`（`src/reader3_app/notes_service.py:212`）是读路径没有而写路径有的那一段：
`mkstemp` → `json.dump` → `flush` → **`os.fsync`** → `os.replace`，外面还套一层
`_book_write_lock`（`threading.Lock` ＋ `fcntl.flock`）。读路径两样都没有。
所以「durable write 在 I/O 争用下出现延迟悬崖」是个很顺的故事。

**实测把它否掉了。** 同一台机器、同一压力配方（10 个忙等）、同一套系统调用序列：

| | n | p50 | p90 | p99 | max |
|---|---|---|---|---|---|
| 无压力 | 72927 | 0.14ms | 0.18ms | 0.52ms | 38ms |
| **压力下** | 83487 | **0.15ms** | **0.19ms** | **1.03ms** | **200ms** |

压力几乎没动这条曲线，最坏的一次 200 毫秒，离 8 秒差了一个半数量级。
**原子写不是那 8 秒。**（探针：[`fsync_probe.py`](./evidence/gate2-attribution-20260923/fsync_probe.py)，
写自己的临时目录，没碰 `books/`。）

#### ⚠️ 订正自己的测量：`Date.now()` 量的不是往返

上面那张表里的 `settled`，是 `fetch().then()` 的**续体真正跑到**的时刻，
不是响应到达的时刻——续体是主线程上的一个 microtask，而主线程正是被压力饿死的那一环。
所以「往返用了 8.2 秒」**说过头了**，能站住的只有：

> 从 `fetch()` 被调用，到它的续体跑起来，隔了 8.2–8.9 秒。

这和「响应很快回来了，只是 JS 晚了 8 秒才跑」在这份数据里**不可区分**。
而后者恰好能解释下方「方法论」那张观测表：凡是逼着事件泵多转的观测手段都把红压没了——
如果失败形态是「页面主线程排不上队」，那正是预期。

判别器是 `performance.getEntriesByType('resource')` 的 `responseEnd`：
它由网络栈记账，不经过 JS 主线程。v6 臂加了这一项重跑，**结论翻盘**。

#### v6 臂：6 跑 6 红，11 份快照，答案是**请求压根没上线**

`performance` 把一条请求拆成 `startTime`（请求被发起）→ `requestStart`（真正开始往外发）
→ `responseEnd`（响应收完）。把 11 份快照里的 25 条 `/api/notes` 请求全摊开：

| | n | `start → reqStart`（上线前排队） | `reqStart → respEnd`（服务端） |
|---|---|---|---|
| 慢请求 | 7 | **8007 / 8040 / 8151 ms**（min/中位/max） | **2 / 3 / 7 ms** |
| 快请求 | 18 | — | 0 / 1 / 11 ms |

**服务端在所有 25 条上都是 0–11 毫秒，一条慢的都没有。**
那 8 秒**全部**花在「请求被发起」到「请求真正上线」之间——在浏览器里，还没出门。

于是前面所有候选一起出局：不是 fsync（已单独测掉），不是服务端，不是磁盘，
不是 FastAPI，不是 `annotations.js` 的任何一行。**产品这一侧从头到尾是干净的。**

##### 而且它不是随机饿死，是**卡在 8.0 秒这个点上**

7 条慢请求的排队时间落在 **8007–8151ms**，跨度 144 毫秒。
随机的 CPU 饿死不会这样——那会给出一条向上散开的长尾。
这么紧的一簇只能是**某个 8 秒的定时器到期**，而这条链路上的 8 秒只有一个：
**测试自己那个「等 `notes.json` 稳定到 N 条，8.0 秒超时」的轮询**。
请求是在那个轮询**结束的那一刻**飞出去的，然后 3 毫秒就回来了。

**读法：`helpers.py` 的同步轮询在跑的时候，浏览器的请求发不出去；轮询一停，立刻就发。**
这是测试夹具自己把被测的写请求摁住了 8 秒，再判它超时——**自伤，不是产品缺陷**。

> 这一步是推断，不是实测。确认它只需一个实验：把那个轮询换成
> `page.wait_for_*`（会驱动浏览器）或在轮询里插 `page.wait_for_timeout(50)`，
> 再跑同一压力臂。如果红消失，读法成立。
> **但那要动冻结的 `helpers.py`**——所以它随修复一起做，立为 [009 欠账 #49](./009-e2e-annotations.md)。

> **⚠️ 撤回一个中途的读法：「动作饿死」。**
> 过程中有一例 `test_w6_delete_removes_only_the_clicked_annotation` 显示
> DELETE 直到 `8.88s` 才发出，一度被当成「浏览器主线程被饿死，卡在网络之前」的独立形态。
> **那条证据不成立，不要引用它。** 那个时间戳是 `page.on("request")` 的**Python 侧**回调
> 跑到的时刻，而 Python 侧的泵正是被饿死的那一环——浏览器很可能早就发了。
> 换成浏览器侧的 `Date.now()`（注入台账）之后，看到的是 v5 那张表：**发得很早，回得很晚**。

##### 那两条 `net::ERR_FAILED` 是烟雾弹

第一版抓到的 console 里有两条 `error: Failed to load resource: net::ERR_FAILED`，
看上去像是写请求被拒。给 `requestfailed` 加上 URL 之后真相是：

```
GET https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;500;600&display=swap
```

**是 Google Fonts 的 webfont，跟 `/api/notes` 毫无关系**（沙箱里没有外网）。
只看 console 文本会把它读成写失败，那会把归因判反。

#### ⚠️ 方法论：**任何 Playwright 侧的观测都会把这条红压掉**

这是本轮最贵的一课，比结论本身更该留痕——它让前两次尝试整个作废。

| 观测手段 | 压力下跑数 | 红 | 耗时区间 |
|---|---|---|---|
| `--tracing=retain-on-failure` | 7 | **0** | 60.4–66.0s |
| `page.on("request"/"response")` **不过滤**（每个静态资源都回调一次 Python） | 3 | **0** | 56.3–58.3s |
| 无观测（对照臂） | 4 | **4** | 63.2–77.9s |
| 只在失败时 `page.evaluate` 读一次 | 5 | **4** | 56.3–86.1s |
| `request`/`response` 过滤到 `/api/notes` | 2 | **2** | 63.8–65.5s |

**无压力档是 54.9–56.9s。** 被压掉红的那两种手段，耗时**回落到了无压力档**——
观测本身把 CPU 争用抵消掉了。机制大概是：每条事件都要跨进程回调一次 Python 客户端，
反而让事件泵转得更勤，悬着的 fetch 因此得以完成。

**推论：凡是「给 e2e 加观测来查这条 flaky」的方案，都要先证明自己没把被查的东西压掉。**
最终用的工具因此是 `page.add_init_script` 注入的**浏览器侧** fetch 台账——
整场测试零 Python 往返，只在失败那一刻 `evaluate` 一次。

工具落在 [`scripts/e2e_diag_dump.py`](../../../../scripts/e2e_diag_dump.py)，用
`PYTHONPATH=scripts pytest ... -p e2e_diag_dump` 挂上，输出目录由 `E2E_DIAG_OUT` 指定。
**它不在冻结集里，也不在 `tests/` 下**，所以 `suite_hash` 不动、收集数不变、三道闸不作废。

#### 顺带查出一笔新欠账：诊断环漏了「建」的请求失败

四个写请求发起点里，只有 `createAnnotation` 的 POST 没有接到 `reportNotesWriteFailure` 上——
「建」的请求失败时环是空的，和「建成功」不可区分。本轮结论不受影响（浏览器侧台账不依赖环），
但它是 #43 (i) 的真实缺口。行号、四个发起点对照与修法立为 [009 欠账 #50](./009-e2e-annotations.md)，此处不重述。

#### 对「要不要开始每天攒 soak」的回答（2026-09-23 原文：先别攒；**2026-09-24 已被裁定推翻**）

2026-09-23 草稿的原话：「只有落到『测试侧』那一行，才谈得上付清零那一刀。现在正是这一行。
现在清零：台账 1 行、两道已过的闸各重跑一次即可；攒到 9 行再清：赔 9 行 ＋ 同样两道闸。
**所以不要启动每日 `--append`。** 先把 `helpers.py` 的等待改掉、付掉清零，再开始攒。」

> **⬛ 2026-09-24：这条建议作废。** 它的前提是「`helpers.py` 马上要改、清零马上要付」；
> 下方裁定把那笔修复**延后**到冻结集下一次不得不重置的时候（[#49](./009-e2e-annotations.md)），
> 于是「早付早省」不再成立。**`soak_run.py --append` 现在可以在 `master` 上照常开始攒。**
> [011 §8 门槛 4](./011-backend-refactor.md) 照旧：分支上的运行不 `--append`。

#### 但「改 8 秒」不是唯一选项——这一条交维护者裁

证据同时动摇了闸本身的设定。`ncpu=10` 的机器上再压 10 个忙等进程 ＝ **2 倍超订**，
而实测表明在这种机器上，写请求在浏览器里排队约 8 秒才上线（上方 v6 表）。这时候要问的是：

**第 2 项到底想证明什么？** 如果想证明「产品在 CPU 争用下不撒谎」，那它**已经通过了**——
本轮没有一例谎报成功。如果想证明「baseline_1b 在 2 倍超订下全绿」，那要么把等待改成
不依赖墙钟（等那个在途请求，而不是轮询盘 8 秒），要么承认这个压力剖面测的是机器不是产品。

把超时从 8s 调大是最省事的一种，但它只是把同一个偶然数字换成另一个偶然数字，
而且要付清零。[欠账 #48](./009-e2e-annotations.md) 已经警告过**不能因为 `helpers.py` 在冻结集里就默认产品必须迁就 8 这个数**；
同样地，也不该默认测试必须迁就 2 倍超订。

#### ⬛ 维护者裁定（2026-09-24）：第 2 项**降为不阻塞的记录项，不删**

> 裁定正文与理由的唯一定义处是 [迁移计划 §7「机制挑战闸」纪律 3 下方](../plan-tech-stack-migration.md)。
> 这里只记它对本台账的后果：
>
> - **第 2 项不再挡 Phase 3 / 012。** 压力命令与复现方法（上方各节与本节证据目录）原样保留；
>   以后再跑照记在本文件、照分类，只是结果不再是放行判据。**本台账从未判第 2 项 PASS**，
>   2026-09-23 的 FAIL 记录原样保留。
> - **台账不清零、一行不动**：`helpers.py` 没改，`suite_hash` 仍是 `1e868c7bf811`。
> - **soak 计数门槛不受影响，仍阻塞 Phase 3。**
> - 夹具缺陷立为 [009 欠账 #49](./009-e2e-annotations.md)：等冻结集下一次不得不重置、或笔记保存代码
>   （`annotations.js`）被改动时一并付；付时把第 2 项在同一压力配方下重跑一次记档。
> - [欠账 #48](./009-e2e-annotations.md)（「一次尝试 = 跑几遍」）随之失去对象，已结清。

### ⬛ #49 修后：压力臂 6 跑 0 红，第 2 项记录性重跑绿（2026-09-30，`019-frozen-set-debts` @ `789602c`）

> **不是批次，不落台账。** 两个臂都没加 `--append`，上面的台账表一行没动；这里只记证据。
> 冻结集在本分支变了（`helpers.py`、`baseline_1b/**`），`suite_hash` **`1e868c7bf811` → `6dcbb1110288`**
> （取法同上方「`suite_hash` 的取法」，在 `789602c` 的干净索引上算）。新值上的第一批、第 3 项重跑、
> 第 1 项在最终候选 `commit` 上重过，按[迁移计划 §7「012 开工核验」](../plan-tech-stack-migration.md)在合入后进行，本节不代劳。

**修法**（[009 欠账 #49](./009-e2e-annotations.md)，`40a0fce`）：`wait_for_notes` / `wait_for_note_text`
轮询间隔从 `time.sleep(0.05)` 换成 `page.wait_for_timeout(50)`——同步 Playwright 只在主线程进 Playwright
调用时才派发 route 回调，`time.sleep` 期间 conftest 的 `**/*` 出站闸饿死，写请求出不了门。8s 上限**没动**。

**不靠压力的确定性复现**（先于压力臂，是本条从推断落到实测的那一步）：新用例
`tests/e2e/test_disk_poll_pumps_inflight_write.py` 让页面 200ms 后自己发起建标注、测试侧不做任何
Playwright 调用直接进 `wait_for_notes`。对**旧** sleep 体，它在无压力的机器上稳定红：
`AssertionError: 8.0s 内 notes.json 没有稳定到 1 条，实际 0 条：[]`（`helpers.py:825`）；换成泵之后绿。

**压力臂**（同 2026-09-23 v6 归因臂的配方：`hw.ncpu`=10 个 shell 忙等 ＋ `-p e2e_diag_dump`，6 跑）。
证据目录 [`evidence/gate2-rerun-20260930/`](./evidence/gate2-rerun-20260930/)（`diag_loop.sh` 相对 v6 版只改两处：
`cd` 到本分支 worktree、加 `export E2E_DIAG_ALWAYS=1`）。

| 跑 | 结果 | lane 结束时 load | 本跑 max(reqStart−start) |
|---|---|---|---|
| 1 | 🟢 `76 passed, 189 deselected in 66.52s` | 10.56 | 6 ms |
| 2 | 🟢 `76 passed … in 64.20s` | 12.70 | 13 ms |
| 3 | 🟢 `76 passed … in 64.09s` | 12.97 | 12 ms |
| 4 | 🟢 `76 passed … in 64.61s` | 13.42 | 5 ms |
| 5 | 🟢 `76 passed … in 64.34s` | 12.37 | 7 ms |
| 6 | 🟢 `76 passed … in 64.46s` | 13.40 | 5 ms |

压前 load 2.85。全部 `/api/notes` perf 条目（`perf` ＋ `late_perf`，`reqStart > 0`）n=1624：min 0、中位 2、
**max 13 ms**，≥1000ms 的 0 条，`reqStart == 0` 排除 0 条。对照 v6：7/25 条慢请求 **8007 / 8040 / 8151 ms**。
「上线前排队 ≈8s」的簇消失了。

**三处必须写明的口径**：
- **仪器不同。** v6 只在红时 dump，本臂 `E2E_DIAG_ALWAYS=1` 每条都 dump——v6 的 25 条来自红用例，
  本臂的 1624 条来自全部用例。两边的 max 可以并排看，比例不能直接比。
- **空洞检查的期望值订正为 75，不是 76。** 每跑恰好 75 个 dump；缺的永远是同一条
  `test_harness_helpers.py::test_notes_isolation_resets_on_setup_and_again_on_teardown`——它不要 `page`
  fixture，`scripts/e2e_diag_dump.py` 对无 `page` 的用例按设计不写。所以上限是 76 − 1 = 75，
  每跑 75 = 全覆盖，不是漏采。
- 本臂 load 峰值约 1.3× 核数，低于 v6 的 23–30；压力**有无**已被 2026-09-23 的数据证明比**大小**更相关
  （见上方「第 2 项复跑」），但这个差照记。

**第 2 项记录性重跑**（gate-2 record-only, not a batch）：`soak_run.py --log-dir evidence/gate2-rerun-20260930/soak`，
无 `--append`。压力源是本文件「第 2 项 —— CPU 压力下」那段 burn 代码，**但从文件跑**
（[`evidence/gate2-attribution-20260923/burn.py`](./evidence/gate2-attribution-20260923/burn.py)，内容相同）：
原样的 `python3 - 10 240 <<'PY'` 在本机 Homebrew Python 3.14（macOS 默认 spawn）下子进程起不来——
`FileNotFoundError: …/<stdin>`，spawn 要按文件重新导入 `__main__`。第一次尝试因此是**无压力**跑
（`76 passed in 64.37s`，load 12.41 → 5.21，一路下降），不算数，照记；第二次从文件跑：
压前 load **1.90**，lane 结束时（burn 仍在）**11.38**，`76 passed, 189 deselected in 68.98s`，
`verdict: green`，`suite_hash 6dcbb1110288`，`[soak] dry run：未写台账`。跑前跑后
`git diff --quiet -- soak-log.md` 都是 0。

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
所以本项**仍然不过**，Phase 3 仍被它挡着（⬛ 2026-09-30：历史记录——本项已于 2026-09-21 对新冻结值重跑 PASS，见上方；今天的状态以 迁移计划 §7「012 开工核验」 为准）。

seed 3003 里 K-2 前后的实际顺序（第 34–38 位），留给需要原样重放的人：
`test_harness_helpers::test_library_lists_every_book_the_corpus_fixture_builds` →
`test_kernel_overlay_geometry::test_k3a_overlay_is_fixed_and_has_no_containing_block_ancestor[tooltip]` →
**K-2** → `test_write_create_annotations::test_w1_real_mouse_drag_creates_marker_and_survives_reload` →
`test_library_nav_and_collections::test_x2d_selection_marks_only_book_cards_and_rows_not_status_pills`。

#### 这条 flaky 到底是测试侧还是产品侧——**分不出来，而且分不出来本身是缺陷**

这个区分不是学术问题，它决定代价：测试侧的修法要动 `helpers.py` / `baseline_1b/**`，两者都在冻结集里，
**改一个字节 soak 计数 10 → 0**；产品侧的修法落在 `src/`，不清零。（⬛ 2026-09-28：批次规则下读作「冻结集改一个字节 ⇒ 在新 `suite_hash` 上重开一批」。）

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

**结论与建议**：先补可观测性，再谈修。补的位置全在 `src/`，**不碰冻结集、不清零**（⬛ 2026-09-28：读作「不改 `suite_hash`」）。立为
[009 欠账 #42 / #43](./009-e2e-annotations.md)。在那之前，第 3 项维持 FAIL。（⬛ 2026-09-30：历史记录；2026-09-21 对新冻结值重跑已 PASS，见上方「对新冻结值 `1e868c7bf811` 的重跑：第 2 / 第 3 项」。）
