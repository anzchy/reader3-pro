# unit lane 提速：commit 门禁的单元测试成本

> 状态：**草案（2026-10-04）**，未开分支；分支号未分配（见 WI-0）。**排在 `025-verify-control` 合入之后**：025 已把 `verify_control_live` 拆成独立的 commit 门禁 lane（`timeoutMs` 2400000）并在 CI 镜像，本计划在它之上做，不重做那次拆分。
> 出处：025 会话转来的五条提案（子代理实测，只抽查过一部分），本文逐条对代码复核、在主 checkout 重测后给出取舍（§3）。
> 本文是独立计划，不属于 `20260816-tech-stack-migration/` 或 `20260817-frontend-ui-refactor/` 的「权威范围」。lane 的定义处仍是 `.claude/tdd-guardian/config.json`，CI 镜像在 `.github/workflows/tests.yml`；本文只描述要怎么改它们，不复述 lane 定义。

## 1. 目标与非目标

**目标**：
- commit 门禁的 unit lane（`tests/unit tests/contract`，带 `--cov`）在空闲机器上 **≤ 90 s**、负载下不逼近 600 s 超时，让每次 commit 付得起，不再有人想用 `TDD_GUARD_BYPASS`。
- 去掉 unit lane 里唯一的内存尖峰（`test_xdist_collection_parity` 的嵌套整树 `pytest -n 4`，进程树峰值约 803 MB）。
- 修掉顺带发现的真缺陷：`scripts/soak_run.py` 在 `FORCE_COLOR` 环境下解析不了子 pytest 的 summary 行（F9）。

**非目标**：
- 不改 025 定下的 `verify-control` lane（命令、门禁时机、超时都是用户裁定）。它是 025 之后每次 commit 最贵的一项，但要不要动由 §6 Q1 交给用户，本文不替他决定。
- 不降低测试强度：不删用例，不改断言，不在 commit 门禁里降 Hypothesis 样本量（提案 2 不采纳，理由见 §3）。
- 不碰冻结集（`tests/conftest.py`、`tests/e2e/conftest.py`、`helpers.py`、`test_harness_smoke.py`、`baseline_1b/**`、`tests/fixtures/{ai_stub,epub_corpus,epub_zip}.py`），`suite_hash` 不变。
- 不往 `pyproject.toml` 的 `addopts` 加任何东西（`pyproject.toml:109-125` 的注释明令禁止放宽；`-n` 放进 addopts 还会传染给 `soak_run.py` 起的 e2e pytest 和所有从仓库根起的子 pytest）。
- 不处理开发机内存紧张本身。那次被杀的主因是多个 Claude 会话（约 4.9 GB）加 Spotlight 等，测试进程本身很轻（F7）。

## 2. 事实基础（2026-10-04 核对）

| # | 事实 | 证据 | 对设计的约束 |
|---|---|---|---|
| F1 | **「557 s 空闲 / 1988 s 负载、约 3758 条」测的是 025 worktree，不是 `master`。** 025 新增 13 个 `test_verify_control_*` 文件；`master` 上一个也没有。025 里 `-m "not verify_control_live"` 收 3369 条、`-m verify_control_live` 收 389 条，后者单独 725 s（负载 14–40，见 025 config 的 lane 描述） | `git ls-tree 025-verify-control tests/unit/`（13 个）；`ls tests/unit \| grep verify_control`（0 个）；025 worktree `--collect-only`（`b60f0d4`） | 原始痛点的大头已经被 025 拆走。本计划的基线必须用 025 之后的 unit lane 重算，不能沿用 557 s |
| F2 | `master` 上按 lane 命令原样跑（带 `--cov`）：**3156 passed / 2 skipped / 1 xfailed，217.8 s**（负载约 3.5）。025 留在 unit lane 的 verify_control 非 live 用例另加约 10 s。所以 025 之后的 unit lane 基线 ≈ **230 s 空闲** | `uv run pytest tests/unit tests/contract --cov=src/reader3_app ... --junitxml`（2026-10-04 22:59，`master` `22e387a`）；025 worktree `-k verify_control -m "not verify_control_live"` 9.8 s | 600 s 超时在空闲时有余量，负载下（实测放大 3–4 倍）会越界 |
| F3 | 同一 lane 加 `-n 4`：**3156 passed，77.5 s，首跑全绿；总覆盖率 86% 与串行一致** | 同上命令加 `-n 4`（2026-10-04，空闲内存 72%）；`cov.json` / `cov4.json` 的 `totals` 对比 | `-n 4` 是最大的单项收益（约 2.8 倍）。只有一次实测，稳定性要在 WI-1 用多次运行证明 |
| F4 | `pytest-xdist` 已在 dev 组（`pyproject.toml:169`，`uv.lock` 锁 3.8.0），lane 和 CI 都没用 `-n`；`addopts` 只有 `--strict-markers`（`:125`）；`coverage.run` 是 `branch = true`，`source = ["src/reader3_app"]`（`:144-147`）；Python 是 3.10（`.python-version`） | 文件本身 | `-n` 写进 lane 命令和 CI 步骤，不写 addopts。`COVERAGE_CORE=sysmon` 要 3.12+，不可用 |
| F5 | 按文件计时（串行、带 cov）：最慢的是 `test_lint_contracts_command` 17.1 s、`test_vitest_host` 13.6 s、`test_build_feature_ledger` 12.7 s、`test_e2e_group_guard` 12.6 s、`test_xdist_collection_parity` 11.7 s、`test_hardcode_lint` 10.2 s、`test_soak_batch` 9.4 s、`test_soak_run` 9.1 s、`test_process_epub_sigkill_recovery` 7.4 s、`test_e2e_lock` 7.3 s。前 10 个合计约 101 s，占全部用例时间的 48% | `lane.xml` 按模块聚合 | 提案 1 里「前十个文件约 260 s」「`build_feature_ledger` 57 s」是负载下测的，空闲值约为其 40%。另外两个最慢的（`lint_contracts_command`、`vitest_host`）不在提案 1 的候选名单里 |
| F6 | `test_build_feature_ledger.py` 不带 cov 跑 9.5 s，带 `--cov=src/reader3_app --cov=scripts --cov-branch` 跑 12.3 s；17 个 `@given` 占它 96.6% 的用例时间 | 2026-10-04 两次单文件计时；子代理 `--durations=0` | 被测的 `scripts/build_feature_ledger.py` 在 `--cov` 范围外，lane 里 coverage 对它几乎不加价。「57 s → 10 s」的预期不成立：空闲时它本来就约 10 s |
| F7 | 测试本身很轻：app import ≤ 55 MB，收集峰值 175 MB，单文件主进程 ≤ 95 MB；torch / sentence-transformers 从不加载（`vector_search.py:42-47` 在 `_require_semantic_deps()` 里懒导入）。唯一尖峰是 `test_xdist_collection_parity`：`:69` 和 `:79` 各起整树 `pytest -n {workers}`，每轮共 5 个子 pytest，进程树峰值约 803 MB | 025 会话的 `/tmp/reader3-memprobe/`（`treerss.py`、`collect.txt`）；代码复核 | `-n 4` 后 4 个 worker 合计预计 < 1 GB，WI-1 要实测。parity 测试在 `-n 4` 下还会叠加 CPU 超额（一个 worker 再起 `-n 4`） |
| F8 | 提案 4 的 books 守卫（`tests/unit/conftest.py:86-122`，session 级基线 ＋ 每条用例 teardown 一次 `shallow_tree`）在主 checkout 里每次遍历约 **0.2 ms**，`books/` 下只有 22 个条目；185 条用例的 teardown 全部低于 5 ms 的报告下限。整条 lane 约 2898 条 × 0.2 ms ≈ 0.6 s。守卫只在 `tests/unit`，`tests/contract` 没有 | 子代理只打印耗时和条目数，未读任何文件名或内容；`tests/contract/conftest.py:233-241,307` | 「每次运行几分钟」的估计不成立，**不做改动**。这个成本随 `books/` 条目数线性增长（1 万个条目约 2.5–5 min/run），记进 §5 |
| F9 | **`FORCE_COLOR=3` 下 `test_soak_run.py` 7 failed / 39 passed，去掉后 46 passed。** 根因在被测脚本，不只是测试：`scripts/soak_run.py:342` 的 `Popen` 没传 `env=`，子 pytest 继承 `FORCE_COLOR`，往管道输出 ANSI；`:205-207` 的 `_SUMMARY_LINE_RE` 锚在 `^(?:=+\s*)?`，`\x1b[32m` 开头的行匹配不上，`parse_summary()`（`:233-237`）抛 `SummaryParseError`。`test_vitest_host.py` 两种环境都是 3 passed，因为它按 JSON 报告和返回码判定，不解析 stdout | 2026-10-04 子代理两次对照运行 | 从 `FORCE_COLOR` shell 里真跑 soak 也会解析失败。025 会话看到的 `test_vitest_host` 两条失败没有复现，判为负载相关（它跑真实 `npm test`），不立项 |
| F10 | Hypothesis：28 个文件 76 个 `@given`（提案写的「34 个文件 97 个」偏多）。每个都写了显式 `@settings(max_examples=…, deadline=None)`，值从 8 到 300；全仓库没有 `register_profile`、`load_profile` 或 `HYPOTHESIS_PROFILE` | 代码复核 | 显式 `max_examples` 优先于 profile，所以光注册 profile 不会生效，必须改 76 处装饰器（或改成按比例缩放的 helper）。这是改测试强度，不是改配置 |
| F11 | `test_vector_read_path.py:38-41` 在模块顶层 import `chromadb`、`chromadb.errors`、`SharedSystemClient`，是唯一在模块级导入 chromadb/numpy 的测试文件（`test_book_resource_locks.py:404,620` 在函数内导入） | 代码复核 | 收集阶段就把 chromadb ＋ numpy 拉进进程；`-n 4` 下每个 worker 都付一遍 |
| F12 | 会读 lane 配置或 `pyproject` 的元测试：`test_vitest_host.py:44-48`（fe-unit lane 唯一且 gateOn 正确）、`test_coverage_gate_failclosed.py:240-243`、`test_e2e_group_layout.py:270-300`（`--strict-markers` 生效）、`test_xdist_collection_parity.py:86-90`（xdist 在 dev 组）、`test_semantic_extra_optional.py:374-415`。**没有一个断言 unit lane 的命令字符串** | 代码复核 | 改 lane 命令不会打红现有元测试；新 lane 要不要配元测试由 WI-2 决定 |
| F13 | 并行风险排查：没有固定端口（8123 只出现在 TestClient 的 Host 头）；e2e flock 测试把 `HOME` 和 `READER3_E2E_LOCK` 指到 tmp；session 级 fixture 只有 `repo_root`、`fixtures_dir` 和 books 基线，都不写共享状态。`test_soak_run.py:676-678` 直接写 `os.environ["GIT_INDEX_FILE"]`，在 `finally` 里还原，进程内安全。共享的仓库资源：`test_vitest_host` 在真实仓库根跑 `npm test`（`node_modules` 下的 vite 缓存），workspace 软链真实 `node_modules`（`tests/fixtures/frontend_host.py:120`） | 代码复核 | 在 xdist 下，books 基线按 worker 各算一份，语义正确。`test_vitest_host` 和 `test_lint_contracts_command` 的并发要在 WI-1 实测 |
| F14 | 冻结集与 `suite_hash`：`scripts/soak_run.py:152-162` 的 `HASH_COVERED_PATHS` 包含 `tests/conftest.py`，**不包含** `tests/unit/conftest.py` 和 `pyproject.toml`。soak 规则只约束 e2e `baseline_1b` 批次 | `soak_run.py`；`tasks/soak-log.md:189-195` | 本计划的所有改动都不改 `suite_hash`。改 `soak_run.py`（WI-3）会换 `commit`，但任何 commit 本来就开新批次，不额外增加成本 |
| F15 | 025 之后每次 commit 付的是 unit ＋ verify-control ＋ fe-unit 三条 lane。verify-control 389 条、725 s（负载 14–40），不带 `--cov`；其中有墙钟断言（`elapsed_s < 6`、`< 8`），负载重时会误红 | `git show 025-verify-control:.claude/tdd-guardian/config.json`（`b60f0d4`）lane 描述；CI 在 `tests.yml:149` 起有同名 job | 025 之后 commit 门禁的大头在 verify-control，不在 unit。见 §6 Q1 |

## 3. 五条提案的取舍

| # | 提案 | 结论 | 理由 |
|---|---|---|---|
| 1 | 把元测试和子进程测试挪出 commit 门禁的 unit lane，改用 marker 选出的独立 lane | **改后采纳 → WI-2** | 实测收益是串行约 46 s（不是 150 s），在 `-n 4` 下约 12–15 s。真正的收益是去掉 803 MB 尖峰和嵌套 `-n 4` 的 CPU 超额。名单要改：<br>• **留在 unit**：`test_unit_lane_has_no_browser_dependency`（断言的是「unit lane 无浏览器也绿」，只有放在这条 lane 里才有意义）、`test_egress_backstop_subprocess`（config 描述里点名的 C11/C12 commit 门禁兜底），两个合计 3 s；`test_router_import_independence`（守的是 `src/` 架构不变量，5.7 s）。<br>• **挪走**：守 push 期工具的 `test_e2e_lock`、`test_e2e_group_guard`、`test_soak_run`、`test_soak_batch`，以及 `test_xdist_collection_parity`。<br>门禁时机定在 **push**：这些脚本只在 push 期和 CI 运行（e2e lane、soak），它们回归时不会让任何 commit 的产品代码出错。push 门禁 ＋ CI 足够及时 |
| 2 | Hypothesis profile（commit 用 fast，CI 和夜间用全量） | **不采纳（暂缓）** | 前提不成立：「`build_feature_ledger` 57 s → 10 s」测的是负载值，空闲时它本来就约 10 s（F6）。要让 profile 生效得改 76 处显式 `max_examples`（F10），等于在 commit 门禁里降低属性测试强度；而 `-n 4` 不降强度就把整条 lane 降到约 78 s（F3）。WI-1 合入后如果 lane 仍超 §1 目标，再按 §6 Q3 重开 |
| 3 | unit lane 加 `-n 4` | **采纳 → WI-1（最高优先）** | 实测 217.8 s → 77.5 s，覆盖率一致，首跑全绿（F3）。三个待查项：books 基线按 worker 各算一份，语义正确（F13）；锁和计时测试在并行下是否会抖，由 WI-1 的多次运行验收证明；soak 规则不约束 unit lane（F14）。`-n` 写进 lane 命令和 CI，不写 addopts（F4）。用固定的 4，不用 `auto`：GitHub `ubuntu-latest` 是 4 vCPU，本地与 CI 保持一致 |
| 4 | books 守卫改成按关键文件比对，整树遍历只在 session 末做一次 | **不采纳** | 主 checkout 实测每次遍历约 0.2 ms，`books/` 只有 22 个条目，整条 lane 约 0.6 s（F8）。「几分钟」的估计建立在「每本书几千个 chroma_db 文件」的假设上，本机不成立。改动会削弱守卫：逐测试的整树比对正是为了抓到 `books/{name}_data/` 深处的破坏。成本随条目数增长这一点记进 §5 |
| 5 | dev loop 不带 `--cov`，只在 commit 带；`test_vector_read_path` 改用 `importorskip` | **拆开处理**：去 cov 的 lane 拆分**不采纳**；chromadb 改成 `importorskip` **采纳 → WI-4** | tdd-guardian 的 lane 是「一条命令对应多个 gateOn」，要让 taskCompleted 不带 cov，就得把 unit 拆成两条近乎重复的 lane，配置面变大（ADR-0008），commit 仍然付 cov。cov 加价约 25–30%（F6），在 `-n 4` 下约 15 s，不值这份复杂度。`sysmon` 要 3.12+，不可用（F4）。chromadb 改到用例里导入成本很低，`-n 4` 下省掉每个 worker 收集期的一次 chromadb ＋ numpy 导入（F11） |
| 附 | `FORCE_COLOR=3` 下 `test_soak_run` 7 条失败 | **确认，立项 → WI-3** | 已复现，根因在 `scripts/soak_run.py`，不只在测试（F9）。`test_vitest_host` 的两条失败没有复现（F9），不立项 |

## 4. 工作项

执行顺序：WI-0 → WI-1 → WI-3 → WI-2 → WI-4 → WI-5。WI-3 排在 WI-2 前面，是因为 WI-2 挪走的 lane 里就有 `test_soak_run`，先修好它的环境依赖，新 lane 一上来就是绿的。WI-1 到 WI-4 可以各自成一个 commit，分别过门禁。

### WI-0: 定义类前置：分配分支号，登记进度盘

**范围**：只改文档。
**前置 WI**：无。前置条件是 `025-verify-control` 已合入 `master`。
**做什么**：
1. 开分支当天，在 `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md` §9 取下一个空号（本文不预写数字），登记为 ⟂ 行：「unit lane 提速：`-n 4`、push 期工具测试拆 lane、soak_run 颜色修复（独立计划 `20261004-unit-lane-cost.md`；不碰冻结集，不另开 task 文件）」。
2. 在 `docs/plans/20260824-frontend-backend-plan-progress.md` 登记为可随时插入（⟂），排在 025 之后。
3. 在 `plan-and-branch-map` skill 的里程碑表加同一行。
4. 开工前用 025 合入后的 `master` 按 §2 F2 的命令重测一次基线（串行、带 cov，记录 wall time、负载和条数），写回本文 F2。025 合入时 unit lane 的内容可能已经和本文测的不同。

**验收标准**：
1. §9、进度盘、skill 里程碑表三处登记的分支号一致。
2. F2 有 025 合入后的实测基线，注明日期、commit 和负载。

---

### WI-1: unit lane 改为 `-n 4`（lane 命令 ＋ CI 镜像）

**范围**：`.claude/tdd-guardian/config.json` 的 unit lane（`command`、`probeCommand` 不变、`description`）；`.github/workflows/tests.yml` 的 unit 步骤。
**前置 WI**：WI-0。
**做什么**：
1. unit lane 命令改为 `uv run pytest tests/unit tests/contract -m "not verify_control_live" -n 4 --cov=src/reader3_app --cov-report=json:coverage-unit.json --cov-report=term`（`-m` 那段是 025 的现状，原样保留）。
2. `tests.yml` 的 unit 步骤加同一个 `-n 4`，保持「两处必须一致」。
3. lane `description` 补一句：为什么是 `-n 4`、为什么不放进 addopts（F4），并写明实测的 wall time 和负载。
4. **不改** `timeoutMs`（600000）：留着做负载下的余量。

**测试矩阵**（这是 lane 配置改动，不是产品代码；「红」是旧配置下的度量，「绿」是新配置达标）：

| 用例 | 做法 | 断言 |
|---|---|---|
| P1 正确性 | 新命令连续跑 **10 次** | 10 次全部首跑全绿；passed / skipped / xfailed 计数每次都与串行基线相同 |
| P2 覆盖率等价 | 比对串行和 `-n 4` 的 `coverage-unit.json` | `totals.percent_covered` 相差 ≤ 0.1；`scripts/check_coverage_gate.py` 两种都通过 |
| P3 负载下 | 另起 4 个 `yes > /dev/null` 占 CPU 时跑 3 次 | 全绿，wall time < 300 s（超时的一半） |
| P4 内存 | 用 `/tmp/reader3-memprobe/treerss.py`（或同等的进程树 RSS 采样）采一次 | 进程树峰值记进 description；预期 < 1 GB（WI-2 合入前 parity 测试还在，可能更高，如实记录） |
| P5 收集一致 | 现有的 `test_xdist_collection_parity` | 保持绿（它本来就在证明 `-n 4` 的切分是精确的） |
| P6 CI | push 到分支，看 `tests.yml` 的 unit job | 绿，并记录 job 时长 |

**验收标准**：
1. P1–P6 全部通过；P1 有一次红，就要先查出是哪条测试在并行下不稳、修好它（或者按 §5 用 `xdist_group` 串行化），再从头跑 10 次。不准用重跑掩盖。
2. 空闲 wall time ≤ 90 s（§1 目标）。
3. `git diff --stat` 只有 config.json 和 tests.yml（以及 P1 查出问题时修的测试文件），冻结集零改动。

---

### WI-2: push 期工具的测试拆进 `tooling_live` lane（push 门禁 ＋ CI）

**范围**：`pyproject.toml`（只加 marker 注册，不动 addopts）；`.claude/tdd-guardian/config.json`（unit lane 的 `-m` 和 `probeCommand`，新增一条 lane）；`.github/workflows/tests.yml`；以下 5 个测试文件，每个只加模块级 `pytestmark`：`tests/unit/test_xdist_collection_parity.py`、`test_e2e_group_guard.py`、`test_soak_run.py`、`test_soak_batch.py`、`test_e2e_lock.py`。
**前置 WI**：WI-1、WI-3。
**做什么**：
1. `pyproject.toml` 的 markers 里注册 `tooling_live`，说明写清：守的是 push 期 / CI 期工具（e2e 锁、e2e 分组 lint、soak 运行器、xdist 切分一致性），会起子进程或整树子 pytest，从 unit lane 里 deselect，由 `tooling-live` lane 运行。
2. 上述 5 个文件加 `pytestmark = pytest.mark.tooling_live`（整个文件归入，规则机械：是不是守 push 期工具，按文件判定，不逐条判定）。
3. unit lane 的 `-m` 改为 `"not verify_control_live and not tooling_live"`，`probeCommand` 同步改。
4. 新 lane `tooling-live`：`uv run pytest tests/unit -m tooling_live`，不带 `--cov`（被测的都是 `scripts/`，在 `--cov` 范围外），`gateOn: ["push"]`，`timeoutMs` 取 WI-2 实测的 3 倍以上。description 写明归入规则、为什么在 push、为什么不带 cov。
5. `tests.yml` 的 unit 步骤同步 `-m`；新增一个与 lane 同名、同命令的 job（参照 025 的 `verify-control` job 写法）。
6. **不挪**：`test_unit_lane_has_no_browser_dependency`、`test_egress_backstop_subprocess`、`test_router_import_independence`（§3 第 1 条的理由），以及 `test_lint_contracts_command`、`test_vitest_host`、`test_hardcode_lint`（它们守的是 commit 期契约和 fe-unit lane 配置，F12）。

**测试矩阵**：

| 用例 | 做法 | 断言 |
|---|---|---|
| T1 划分无遗漏 | 对 unit lane 的 `-m` 和 `tooling_live` 分别 `--collect-only -q` | 两边条数之和等于 `-m "not verify_control_live"` 的条数，交集为空 |
| T2 marker 落点 | `--collect-only -m tooling_live` 的 nodeid 去掉 `::` 后的文件集合 | 恰好是上面 5 个文件 |
| T3 unit lane | 新 unit lane 命令跑一次 | 全绿，wall time 比 WI-1 后进一步下降，并记录数值 |
| T4 新 lane | `tooling-live` 命令跑 3 次 | 全绿，记录 wall time 和进程树内存峰值 |
| T5 strict-markers | 现有的 `test_e2e_group_layout` | 保持绿（未注册的 marker 会被 `--strict-markers` 拒收） |
| T6 CI | push 到分支 | unit job 和新 job 都绿 |

**验收标准**：
1. T1–T6 全部通过。
2. unit lane 的进程树内存峰值不再出现约 803 MB 的尖峰（与 WI-1 的 P4 对比）。
3. 新 lane 在 config.json 和 tests.yml 里的命令逐字一致。

---

### WI-3: `soak_run.py` 在 `FORCE_COLOR` 下仍能解析 summary（缺陷修复）

**范围**：`scripts/soak_run.py`（`run_pytest()` 起子进程那段，`:336-350` 附近）；`tests/unit/test_soak_run.py`。
**前置 WI**：WI-0。
**做什么**：
1. 先写红：在 `test_soak_run.py` 里用 `monkeypatch.setenv("FORCE_COLOR", "3")` 跑现有的 `test_parser_agrees_with_real_pytest_output` 那组真实子 pytest 场景，它们应当变红，复现 F9。
2. 修复放在**来源**上：`run_pytest()` 给子进程传一份 `env`，去掉 `FORCE_COLOR`、`PY_COLORS`，并在参数里显式加 `--color=no`。不把 `_SUMMARY_LINE_RE` 改成容忍 ANSI：解析器只认干净输出，这条契约更窄，也更好测。
3. 补一个纯函数用例：`parse_summary()` 遇到 ANSI 包裹的行仍然抛 `SummaryParseError`，锁住「只认干净输出」这条契约，防止以后有人只改正则。

**测试矩阵**：

| 用例 | 输入 | 断言 |
|---|---|---|
| S1 | `FORCE_COLOR=3` ＋ 现有 5 个参数化场景（all-pass / with-skip / with-fail / with-deselect / with-error） | 解析结果与无 `FORCE_COLOR` 时完全一致 |
| S2 | `FORCE_COLOR=3` ＋ `test_zero_tests_ran_is_never_recordable`、`test_a_green_summary_from_a_process_that_died_is_not_recordable` 的场景 | 结论不变 |
| S3 | `PY_COLORS=1` | 同 S1 |
| S4 | `parse_summary("\x1b[32m2 passed\x1b[0m in 0.05s")` | 抛 `SummaryParseError` |
| S5 | 父环境的其他变量（如 `PATH`、`HOME`） | 原样透传给子进程 |

**验收标准**：
1. 在 `FORCE_COLOR=3` 的 shell 里跑 `uv run pytest tests/unit/test_soak_run.py`，全绿。
2. `uv run python scripts/soak_run.py --verdict <最近一个批次 ID>` 的输出与修改前一致（只读子命令，不追加台账）。

---

### WI-4: `test_vector_read_path` 的 chromadb 改为用例内导入

**范围**：`tests/unit/test_vector_read_path.py`。
**前置 WI**：WI-0。
**做什么**：把 `:38-41` 的模块级 `import chromadb` / `chromadb.errors` / `SharedSystemClient` 挪进用到它们的用例或 fixture，用 `pytest.importorskip("chromadb")`。断言一字不改。

**验收标准**：
1. 该文件用例数和结果不变。
2. `uv run python -X importtime -m pytest tests/unit --collect-only -q 2>&1 | grep -c chromadb` 为 0（收集阶段不再导入 chromadb）。
3. 在没装 semantic extra 的环境里，这些用例是 skip 而不是 collection error（与 `test_semantic_extra_optional.py` 的约定一致）。

---

### WI-5: 文档回写

**范围**：只改文档。
**前置 WI**：WI-1 到 WI-4 合入。
**做什么**：
1. 根 `CLAUDE.md`「Tests and Checks」：unit 那行加 `-n 4`，新增 `tooling-live` 那行（注明 push 门禁）。
2. 本文状态块改为已合入，写 PR 号和合并 commit；F2 / F3 补上合入后的实测。
3. `docs/feature-ledger.md`：本计划只改测试基础设施，不新增产品能力，**不加台账行**。如果 WI-3 的 soak 修复对应已有行的 Known limits，就在那一行里改，并重新生成 html。

**验收标准**：
1. `python3 scripts/build_feature_ledger.py --check` 通过。
2. `CLAUDE.md` 里的命令与 config.json 逐字一致。

## 5. 风险

| 风险 | 缓解 |
|---|---|
| 并行下锁和计时测试抖动（`test_book_lock*`、`test_collections_concurrency`、`test_process_epub_sigkill_recovery`、`test_event_loop_not_blocked`） | WI-1 的 P1 要求 10 次连续首跑全绿，P3 要求负载下也绿。哪条抖就修哪条，或者用 `@pytest.mark.xdist_group` 把它们收进同一个 worker（这需要 `--dist loadgroup`，命令要跟着改）。不准靠重跑过关 |
| `test_vitest_host` 在真实仓库根跑 `npm test`，并行时与 fe-unit lane 或别的 worker 争 vite 缓存 | P1/P3 观察；如果抖，把它归入 `xdist_group`，或在 WI-2 里讨论它是否属于 push 期 |
| 挪到 push 门禁的测试回归，要到 push 时才发现 | 这些都是 push 期 / CI 期工具，在 push 之前出问题也不会伤到产品代码。CI 上的同名 job 兜底 |
| books 守卫的成本随 `books/` 条目数线性增长（F8）：书库里有大的 `chroma_db/` 时，每次 teardown 都要整树遍历 | 今天约 0.6 s/run，不处理。若以后 lane 的 `--durations` 里 teardown 明显变大，再考虑提案 4 的「关键文件逐测试比对 ＋ session 末整树遍历一次」 |
| 025 合入时 unit lane 的内容变了，本文的数字随之过期 | WI-0 第 4 步重测基线 |
| `-n 4` 下一个 worker 又起嵌套 `pytest -n 4`，造成 CPU 超额 | WI-2 把 `test_xdist_collection_parity` 挪走；WI-1 到 WI-2 之间的那段时间如实记录 |
| 子 pytest 在 xdist worker 里继承 `PYTEST_XDIST_*` 环境变量后行为变化（未验证） | WI-1 的 P1 会覆盖到，因为 parity、soak_run 等起子 pytest 的测试都在 lane 里 |

## 6. 待决问题

1. **verify-control lane 要不要也动？** 025 之后，每次 commit 最贵的是它（389 条，负载下 725 s，`timeoutMs` 2400000，commit 门禁，F15），不是 unit lane。它的 commit 门禁是用户裁定的，本文不改。可选做法：(a) 保持原样；(b) 也加 `-n 4`（它的用例都起子进程，并行收益可能更大，但墙钟断言 `elapsed_s < 6 / < 8` 在并行负载下更容易误红）；(c) 改成 push 门禁。需要用户决定；选 (b) 或 (c) 的话，作为本计划的 WI-6 补写。
2. **`tooling-live` 用 push 门禁还是 commit 门禁？** 本文选 push（§3 第 1 条）。如果用户希望与 025 一样走 commit 门禁，WI-2 只需把 `gateOn` 改掉，这样拆 lane 只带来内存收益，per-commit 时间几乎不变。
3. **Hypothesis profile 什么时候重开？** 条件：WI-1 和 WI-2 合入后，unit lane 空闲时仍然超过 90 s，且 `--durations` 显示 `@given` 用例占大头。重开时用「按比例缩放的 helper ＋ CI 跑全量」，而不是删掉显式 `max_examples`。
4. **`-n 4` 还是 `-n auto`？** 本文选固定的 4（§3 第 3 条）。核数更多的开发机可能想要更大的值，但本地与 CI 不一致会让「本地绿、CI 红」更难查。
