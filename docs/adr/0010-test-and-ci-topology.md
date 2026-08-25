# ADR-0010: 测试与 CI 拓扑——质量门禁在本地 tdd-guardian，GitHub CI 只在发版/tag 触发

| 字段 | 值 |
|---|---|
| Status | Accepted |
| Decision date | 2026-08-24（`d986dd8` 把 CI 改为仅发版触发，是三者中最早的一次；同日 `f6802f8` 把 `coverageMode` 切到 `absolute`、`2e8564e` 建起 `tests.yml`，均列入 Evidence） |
| Recorded date | 2026-08-25 |
| Record type | Retrospective |
| Original rationale known | Yes |
| Confidence | High |
| Current compliance | Full（例外见 Neutral：`e2e` lane 的 `gateOn` 目前是空数组，009 落地时改回 `["push"]`） |
| Evidence | `docs/plans/20260816-tech-stack-migration/tasks/008-test-safety-net.md:249,251,255-256`（门禁挪本地的决定与两条代价）、`:258-273`（`gateFreshnessMinutes` 盲窗）、`:289-303`（`e2e` `gateOn` 清空的机制与理由）、`:53-100`（`coverageMode=absolute` 的收尾裁决：`:63,68` 实测值够不着建议值、`:79,84-87`「阈值按实测地板定，不按期望定」、`:91-96` IOU 表）、`:359,367`（`branches 60→52` 是本分支唯一下调项，差额转 IOU）；`.github/workflows/tests.yml:12-28`（触发条件、不设 required check）、`:57-61`（`uv sync --frozen`，与 wheel job 刻意相反）、`:89-93`（覆盖率门禁读 `check_coverage_gate.py`，YAML 不重述数字）；`.github/workflows/lint.yml:10-20`（同口径改基）、`:73-79`（`packaging`/wheel job 故意不用 `uv.lock`，解析 latest）；`scripts/check_coverage_gate.py:1-29`（fail-closed 设计：唯一定义处、零匹配 glob 判 FAIL、配置读错一律拦）；`.claude/tdd-guardian/config.json:16-19`（unit lane `gateOn`）、`:27`（e2e `gateOn: []` 及理由）、`:38-40`（packaging `gateOn: ["push"]`）、`:46-52`（`coverageThresholds`/`coverageMode` 唯一定义处）、`:58-87`（`criticalPaths` 七条 branch 地板）；`pyproject.toml:91-105`（测试目录按 lane 切分，不用 marker 分流慢用例）；`tests/unit/test_coverage_gate_failclosed.py:1-14`（G1–G7 锁定 fail-closed 行为）；`docs/plans/20260824-frontend-backend-plan-progress.md:95`（soak 计数的语义，与本决定同源于 2026-08-24 CI 改基）；commit `1392b1f`（`--frozen` 例外的起因：starlette 1.6.0 装出来 500，只有干净环境看得见） |
| Confirmation | `python3 scripts/check_coverage_gate.py`（覆盖率门禁，读 `.claude/tdd-guardian/config.json`）；`uv run pytest tests/unit/test_coverage_gate_failclosed.py`（fail-closed 行为的机器验证）；`.github/workflows/tests.yml`（release/tag 触发，`workflow_dispatch` 手补）；`.github/workflows/lint.yml`；本地：`.claude/tdd-guardian/config.json` 驱动的 `commit`/`push`/`taskCompleted` 钩子 |

## Context and Problem Statement

reader3-pro 的质量把关同时涉及三件互相牵动的事：门禁装在哪（本地钩子还是 GitHub CI）、CI 何时跑、覆盖率阈值定义几处。008 分支把这些从「计划里的建议」定型为今天的现状，理由分散在任务文件、两个 workflow 头部注释、tdd-guardian 配置和一个校验脚本里——不合成一处，015 合入后 `docs/plans/` 归档时这些理由就随之消失。不做决定会发生的事已经真实出现过一次：007 阶段先把 CI 写成「必须绿灯才能合并」，24 小时内就发现这个约定在仅发版触发的新策略下字面上不可达。

- **Observed State**：本地 `tdd-guardian` 三条 lane 分别挂在 `taskCompleted`/`commit`（unit）、`push`（packaging）、`push`（e2e，目前为空数组，见下）。GitHub Actions（`lint.yml`、`tests.yml`）只在 `release.published` 与 `push.tags "v*"` 触发，`workflow_dispatch` 留作手动补跑，两个文件都不设 required check。覆盖率阈值的唯一定义处是 `.claude/tdd-guardian/config.json` 的 `coverageThresholds`/`coverageMode`（`absolute`），`check_coverage_gate.py` 读它、CI 与本地共用，YAML 里不出现任何数字。测试目录按 lane 切分（`tests/unit`+`tests/contract`＝unit，`tests/integration`＝packaging，`tests/e2e`＝e2e），不用 pytest marker 分流。
- **Original Rationale**：`d986dd8` 提交信息与 `tests.yml:16-19` 都写着同一句话——「一个日常不跑的 workflow 设成 required check，只会把每个 PR 卡死在 Expected — Waiting for status」，这是把门禁从 CI 挪回本地的直接触发点。覆盖率单一定义处的理由见 `check_coverage_gate.py:4-9`：CI 里没有 tdd-guardian，YAML 里再写一遍数字就有了两份互不知道对方存在的阈值，「两份阈值只有一种结局：漂移」。
- **Current Assessment**：三件事今天都有测试或脚本锁定（fail-closed 有 G1–G7，触发条件写在 workflow 文件本身），不只是文档里的意图。唯一的偏差是 `e2e` lane 的空 `gateOn`——这是过渡状态，不是当年就打算长期维持的形状（见 Neutral）。

## Decision Drivers

- 单人维护、无常驻 reviewer：required check 缺了 reviewer 就起不到「审过才能合」的作用。
- 反馈延迟与 CI 分钟成本的权衡：unit lane 本地 ~3.3 秒，把它挪到分钟级的 CI 队列换不来任何收益。
- 阈值只能有一个家，否则「本地绿、CI 红」或反过来会让人不再相信任一处（`tests.yml:79-80`）。
- fail-closed 原则：`coverageMode` 缺失、拼错、非字符串都必须拦，不能默默滑向宽松（`check_coverage_gate.py:24-28`）。
- `1392b1f` 的教训——依赖漂移只有干净环境才看得见——决定了 `packaging` lane 必须故意不用 `uv.lock`。

## Considered Options

1. **本地门禁 + CI 仅发版触发**（选定）——tdd-guardian 三条 lane 各自在 `taskCompleted`/`commit`/`push` 拦人；GitHub Actions 只在发版/打 tag 时跑，不设 required check。代价：中间攒下的依赖漂移、lint 违规都堆在发版当天才暴露。
2. **每次 push 跑 CI 并设 required check**——为什么不：`tests.yml:16-19` 记录的失败模式是反过来的教训——一条不常跑的检查设成 required 只会卡住 PR；把它反过来读同样成立，本仓库单人维护、没有常驻 reviewer，一条无人 review 的 required check 起不到 review 的作用，只是在每次 push 上多付一次 CI 分钟成本换一个形式主义的绿勾。（此为对已确认证据的合理外推，并非 T008 逐字原话——见本报告末尾核对说明。）
3. **只靠 CI，不装本地钩子**——为什么不：反馈延迟到 push 之后。unit lane 只要 ~3.3 秒（`config.json:23` 的 `timeoutMs` 留了十倍余量，实测远小于此），把这个反馈挪到 CI 队列里毫无收益，只会让人攒着一堆本地已知会红的提交再一次性推上去，`push` 时才发现。

## Decision Outcome

四件事一起定：(a) 门禁在本地——unit 挂 `taskCompleted`/`commit`，packaging 挂 `push`，e2e 设计上也挂 `push`（009 前暂空，见 Neutral）；(b) GitHub Actions 只在 `release.published`/`push.tags "v*"` 触发，`workflow_dispatch` 留手动补跑口子，两个 workflow 都不设 required check；(c) 覆盖率阈值唯一定义处是 `.claude/tdd-guardian/config.json`，`coverageMode=absolute`，`check_coverage_gate.py` 是 CI 侧唯一读取者，YAML 里不重复数字；(d) 测试目录按 lane 切分，不靠 marker 分流。明确不做：不在 CI YAML 里重复写覆盖率数字；不把 `ruff format` 并入这条安全网（是它自己的机械分支）；不在 required check 缺席的情况下把「CI 建起来了」误当成「CI 是合并门槛」。

## Consequences

### Positive
- 反馈从分钟级的 CI 队列收缩到秒级的本地钩子（unit lane ~3.3 秒）。
- 覆盖率阈值只有一处定义，CI 与本地读同一份配置，不会出现「本地 70% / CI 65%」的分裂。
- fail-closed 校验有专门测试锁定（G1–G7），配置写错不会静默滑向宽松那一侧。

### Negative
- `git commit --no-verify` 一行绕过全部本地门禁——它挡的是手滑，不是决心（`tasks/008-test-safety-net.md:255`）。
- 中间攒下的依赖漂移、lint 违规只在发版当天暴露：`lint.yml`/`tests.yml` 从「每次 push 的护栏」降级成「发版前的关门检查」，补偿手段只有 `workflow_dispatch` 手点（`lint.yml:17-20`）。
- 覆盖率 `absolute` 地板是**实测值**，不是目标值：验收时写的 `branches 60` 在真实代码上够不着（实测 54.56%），改成留 2–3 个点抖动空间后定的 `branches: 52`（`config.json:49`）；差额转成挂在 011/012 上的四张 IOU，没有清零时间表（`tasks/008-test-safety-net.md:91-96,367`）。
- 上一次绿之后到 `gateFreshnessMinutes`（15 分钟）之前有个盲窗：钩子只看「距上次绿多久」，不重新跑测试，理论上可以把测试改红再照常提交，靠「陈旧」间接拦下而非「红」直接拦下（`tasks/008-test-safety-net.md:258-267`）。

### Neutral
- `e2e` lane 的 `gateOn` 目前是空数组，不是遗漏。`tests/e2e/` 还没有用例，一条永远 `never passed` 的 lane 若挂在 `push` 上会拒绝每一次 push 且无路可走，逼所有人常年挂 `TDD_GUARD_BYPASS`（`config.json:27`；`tasks/008-test-safety-net.md:289-303`）。009 加第一条 e2e 用例和 `live_server` fixture 时，在同一个 commit 里把它改回 `["push"]`。
- Phase 3 的 E2E soak 门槛（`baseline-1b` 连续绿 ≥10 次 / 跨度 ≥5 个工作日）借用了同一次 2026-08-24 CI 改基，从数「主 CI 连绿」改成数本地全量运行，但计数对象是特定一批代码而非泛泛等待——「soak 不是一段可以预付的等待，它是对某一份特定代码的观察，预付了不算数」（`docs/plans/20260824-frontend-backend-plan-progress.md:95`）。soak 的台账字段、清零规则的完整定义在 `plan-tech-stack-migration.md` §7，不在本 ADR 覆盖范围内，本 ADR 只说明它与本决定同源。

## Revisit When

- 出现第二位常驻贡献者——required check 只有配上 reviewer 才有意义，届时应重新评估 `tests.yml`/`lint.yml` 要不要设为 required。
- GitHub Actions 分钟预算变化（额度扩大、计费模型改变），发版触发的成本前提改变。
- 009 首次让 `tests/e2e/` 有可用用例：`e2e` lane 的 `gateOn` 回填 `["push"]`，Current compliance 的例外随之清零。
- 覆盖率 IOU（`notes_service.py`/`search_service.py`/`ai/**`/总体 `branches`）任意一项清零：需要重新核对 `coverageThresholds` 的地板是否还留有下调空间。

## Related

- ADR-0000（`docs/adr/` 的分工与 Confirmation 机制）
- ADR-0011（API v1 冻结；011 拆分 `web/server.py` 会直接改变 `branches` 地板，届时的 IOU 结算与本 ADR 记的 `52` 互相印证）
- ADR-0013（testid 不变量与三条 lint——它们在 CI 里的触发时机由本 ADR 定）
- 原定义处：`docs/plans/20260816-tech-stack-migration/tasks/008-test-safety-net.md`「## 7. CI」（`:219`–`:304`）与「## 1. 先定覆盖率基线策略」下「### 收尾裁决」（`:53`–`:100`）——两段是 008 的执行台账（实测数字、当天推理），保留并各加了一行指向本 ADR 的指针（2026-08-26）；015 归档时随 `docs/plans/` 一起归档。§8「API v1 冻结」则已由 ADR-0011 接管。
