# 018-library-routes —— 任务

- **状态**: ✅ **已合入**（⬛ 2026-10-07 回写：第二段 WI-4 – WI-8 随 PR #37 于 2026-10-07 合入 `master`，合并 commit `74384b1`，分支尖 `b6025ba`，见 §8；§4 出口闸证据已填，门槛 7 的 ADR-0015 compliance 一项见该行注）。~~🚧 **进行中，首段已合入**~~（⬛ 2026-10-02 回写：WI-1 – WI-3 随 PR #33 于 2026-10-01 合入 `master`，合并 commit `c08317b`，见 §8；~~**WI-4 – WI-8 未做**，PR 正文明写「WI-4 – WI-8 不在本 PR」。§4 出口闸按整个分支计，尚未全部满足~~）。~~🚧 **进行中**~~（⬛ 2026-09-30 分支从 `master` 开出，与 `019` 并行，先做 WI-1 / WI-2，调度见[进度盘「现在该做什么」第 2 步](../../20260824-frontend-backend-plan-progress.md#现在该做什么)）。~~评审通过、待开工~~（任务书 2026-09-26 评审通过，§6 Q1–Q12 全部裁定）。~~分支**未开**，没有一项已实施。~~2026-09-28 批次规则取消 soak 等待期后，本分支是挡在 012 前面的关键路径（顺序见 [进度盘 §2](../../20260824-frontend-backend-plan-progress.md)；⬛ 2026-09-30：排在冻结集欠账窗口之后开工，WI-8 规则同日订正，见 §6 Q10）
- **2026-10-02 开工**：按[第二段执行计划 §1.3](../../20261002-018-second-slice-plan.md#13-任务书的漂移开工当天改进任务书本文不改) D1–D19 修正任务书（⬛ 本次修正各处以「⬛ 2026-10-02 D*n*」标注；§6 补 Q-A – Q-H 裁定）。第二段怎么做（测试分层、红灯检查、检查点）只在[执行计划](../../20261002-018-second-slice-plan.md)，本文仍是 WI-4 – WI-8 目标 / 涉及文件 / 验收 / 出口闸的定义处
- **对应阶段**: M4a-债（013 延后到后端的欠账兑付之一部分，[§9 编号表](../plan-tech-stack-migration.md)）。不是新里程碑，与 016 / 017 同类
- **计划文件夹**: [`20260816-tech-stack-migration/`](../plan-tech-stack-migration.md)（归属 **A**）
- **上游**: `013`（✅ 已合入）、`017`（✅ 已合入）；从 `master` 开
- **下游**: `012-storage-format` 在本分支之上开工（WI-6 / WI-7 / WI-12 / WI-13 持本分支的锁，WI-5 / WI-10 建在本分支的列表路由上）；014 WI-16b 里等 #56 / #58 的各项等本分支。顺序的定义处是 [进度盘 §2](../../20260824-frontend-backend-plan-progress.md)
- **节奏**: WI 严格按号串行（⬛ 2026-10-02 D11 例外：**WI-8 可提前，其余按号**——WI-8 只碰 `scripts/soak_run.py` 与它的单测，与 WI-4 – WI-7 无共享文件）；WI-1 是**单个 commit**；路由新增与 `routes.snapshot` 同 commit

> **权威范围**：本文**定义**的只有五件事——018 的工作项切分与先后约束、每个 WI 的验收占位、018 的出口闸与合入记录、
> **每书写协调契约的工作项**（契约正文落地后以 ADR-0015 为定义处，本文改为链接）、#51 / #53 / #56 / #58 的**前端半边归属**（§2.3）。
> 以下一律**只链接不复述**（「搬，不抄」）：欠账正文与验收列 → [009 跨波欠账表](./009-e2e-annotations.md#跨波欠账)；
> D1 裁定理由 → [012 §6 D1](./012-storage-format.md)；API 冻结规则 → [ADR-0011](../../../adr/0011-api-v1-freeze.md)；
> 外部输入面的边界 → [ADR-0012](../../../adr/0012-security-boundaries.md)；写入协议 → [ADR-0007](../../../adr/0007-crash-safe-publish-protocol.md)；
> soak 判据（⬛ 2026-09-28 起为批次规则）→ [§7](../plan-tech-stack-migration.md)；soak 批次状态与机制挑战闸记录 → [`soak-log.md`](./soak-log.md)；
> 分支编号 → [§9](../plan-tech-stack-migration.md)；执行顺序 → [进度盘](../../20260824-frontend-backend-plan-progress.md)；
> 014 WI-16b 的各项与延后总表 → [前端计划 §「延后项」与 WI-16b](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md)。
>
> **引用规则**：用**符号名**定位，不写代码行号（同 011 / 012）。

---

## 1. 进入条件

| 条件 | 状态 | 在哪查 |
|---|---|---|
| 013 已合入 | ✅ | [进度盘 §1 状态板](../../20260824-frontend-backend-plan-progress.md) |
| 017 已合入 | ✅ | [017 任务文件](./017-audit-followup.md)、进度盘 §1 |
| 本任务书评审通过 | ✅ 2026-09-26 | 本文 §6 全部裁定 |

- **不等 soak**（D1）。本分支~~在 soak 等待期内~~做完并合入（⬛ 2026-09-30：批次规则下已无「等待期」；009 #49 / #50 在本分支**之前**的冻结集欠账窗口里兑付，本分支的锁、删书、并发路径在修好的 harness 上测，顺序见[进度盘](../../20260824-frontend-backend-plan-progress.md)）；~~代价是它**不得碰冻结集**（§4 门槛 F）——它合进 `master`，改一个字节就清零 soak 计数。~~（⬛ 2026-09-28：soak 改为批次规则、012 门槛 F 同日放宽——碰冻结集不再禁止，代价是 012 开工前要在新 `suite_hash` 上重跑一批；仍应避免无谓改动。判据见 [§7](../plan-tech-stack-migration.md) 与 [012 §4 门槛 F](./012-storage-format.md)。）
- **`soak_run.py --append` 只在 `master` 上跑**（⬛ 2026-09-30 订正：判据是「被测 `HEAD` 是 `origin/master` 的祖先」，不是「当前分支叫 `master`」，见 WI-8 / §6 Q10）。分支上的运行只做核验、不进台账（[017 §4](./017-audit-followup.md)）。这是流程约束，`scripts/soak_run.py` 本身~~**不检查分支**~~今天还不检查（WI-8 落地后改为机器拦截）（~~它只在覆盖路径有未进索引的改动时拒绝 `--append`~~ ⬛ 2026-09-29：它现在要求**整棵工作树**干净才放行 `--append`，批次在被测 SHA 的干净 detached worktree 里跑、`--ledger` 写回主工作区台账，见 [`soak-log.md` 表头](./soak-log.md)）。

---

## 2. 范围 / 非范围

### 2.1 范围

| 项 | 欠账 / 来源 | WI |
|---|---|---|
| 兑付方改写（一批） | D1 的「未做」部分（原在 012 §2.2） | WI-1 |
| 每书写协调契约（锁）＋ ADR-0015 草案 | D1 新立的前置 | WI-2 |
| provider 保存版本校验 | 009 **#51** | WI-3 |
| 客户端书目列表路由 | 009 **#56** | WI-4 |
| 删书路由 | 009 **#58**（**WI-2 落地之后**） | WI-5 |
| 书库导出 | 009 **#53**（**导出 schema 定下之后**，否则在本分支内挂起，见 WI-6） | WI-6 |
| CI e2e job 的收尾对账 | 009 **#31**（2026-09-26 用户裁定并入） | WI-7 |

### 2.2 非范围

- 冻结集 8 条路径的任何改动（§4 门槛 F）——包括 009 欠账 #49 / #50（⬛ 2026-09-30：#49 / #50 连同 017 finding #10 在本分支**之前**的冻结集欠账窗口兑付，不归本分支；顺序见[进度盘](../../20260824-frontend-backend-plan-progress.md)）
- **#52**（批量重建索引）与 **#57**（上传）：留在 012 末波，理由见 [012 §6 D1](./012-storage-format.md)
- 新存储格式、三态读取、`load_book_metadata()` 改读 manifest（#35）：012。本分支的路由只经 `book_store` 读，不碰格式
- 014 WI-16b 的书库页 UI（等 #56 / #58 的第 8、17、19、20、24 项）：本分支只交付路由，UI 归 014
- **#31 的「建 job」本身**：已于 2026-09-20 结清（见 WI-7），本分支不重建、不换形状

### 2.3 前端半边归属（本节是定义处）

判据：**同一页面、后面没有别的分支会接**的前端半边，随路由进本分支；**有明确接手分支**的，留给它。先例是 012 §2.2 把 #52 的前端半边（设置页 `reindex`）随 012 WI-12 走。

| 欠账 | 前端半边 | 归属 | 依据 |
|---|---|---|---|
| #51 | 设置页 provider 保存：带上 revision、把 409 显示成可见错误（FB-S09 的客户端半边） | **018 WI-3** | FB-S09 被 D8 延后，013 只断言了「保存失败可见」；013 之后没有前端分支再管设置页，这半边今天**无主** |
| #53 | 设置页 `wireExport` 的 `set-export-json`（FB-S06），由「暂不支持」换回真实请求 | **018 WI-6** | 012 §2.2 已写「#53 的随 018」；D11 延后到「012 债 #53」，号跟着欠账走 |
| #56 | 书库页从服务端取书目 | **014 WI-16b**（第 8、17、19、20 项） | 延后总表与 WI-16b 已按项列出；本分支只交路由 |
| #58 | 书库页删书（FB-L18，`lib-bulk-index`） | **014 WI-16b**（第 24 项） | 同上 |

---

## 3. 工作项

测试矩阵统一待 `/tdd-guardian:design-tests`；下面的「验收」是种子，不是矩阵。**实施一律走 `/tdd-guardian:workflow`**，WI-1 也不例外（它改测试常量与 fixture）。

| WI | 标题 | 依赖 | 走 workflow |
|---|---|---|---|
| WI-1 | 兑付方改写（一个 commit） | — | ✅ |
| WI-2 | 每书写协调契约 ＋ ADR-0015 草案 | WI-1 | ✅（ADR 草案部分是文档） |
| WI-3 | #51 provider 保存版本校验（前后端） | WI-1 | ✅ |
| WI-4 | #56 书目列表路由 | WI-1 | ✅ |
| WI-5 | #58 删书路由 | **WI-2**、WI-4 | ✅ |
| WI-6 | #53 书库导出（前后端） | WI-4（schema 已裁定，§6 Q7） | ✅ |
| WI-7 | #31 CI e2e job 收尾对账 | 合并头存在（最后做） | ❌（文档 ＋ 一次 CI 运行） |
| WI-8 | `soak_run.py --append` 硬拦截 | — | ✅ |

> WI-3 / WI-4 不依赖 WI-2，但**仍排在它之后**（D1 定的顺序）：锁的形状先定，后面每条路由都知道自己要不要持锁。

### WI-1: 兑付方改写（一批，单个 commit）

- **目标**: 把 D1 的结论落进所有机器可查的地方，**一次改完**：拆开改会有一个 commit 让 Track-D 台账测试红（钉条写 018，校验还只认 012，或反过来）
- **涉及文件**:
  - `docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md`：#51 / #53 / #56 / #58 四行的兑付方列改 `018-library-routes`；#56 行删掉「与 #35 同批」；#53 行「内容依赖 012 存储格式」的理由改写（导出走 `book_store`，与格式无关——见 WI-6）；#31 行的兑付方列「待定」改为已兑付的实际去向（见 WI-7）
  - `tests/unit/test_track_d_ledger.py`：`DEBT_012_RE` 与 `debt_citation_problems` **泛化，不放宽**（§6 Q1）——正则 `\b(012|018) debt #(\d+)\b`；兑付方列按 slug 解析出分支号，要求**精确相等**（今天的 `"012" in owner` 是子串匹配，兑付方写成 `0120-x` 或叙述里顺带提到 012 都会误过）；兑付方列无法解析、或解析出的分支号不在 §9 分配表里 → 红；硬编码 `012 debt #N` 的用例与 `test_cited_debt_ids_must_resolve_to_012_rows` 同步改名改义。前端计划里中文的「012 债 #N」**不**纳入机器校验，本 WI 做一次性 grep 改完即可
  - `tests/fixtures/track_d_pinned_014.json`：引 #56 的两条钉条（`WI-4#6`、`WI-8#4`）改写为 `018 debt #56`；`WI-4#6` 里的 `012 debt #54` 不动
  - 前端计划：延后总表导言（「该号在欠账表里归 012」）、#54+#56 行、#56 行、#58 行、D13、WI-16b 外部前置「012 债 #54–#58」拆成「012 债 #54 / #55 / #57 ＋ 018 债 #56 / #58」、FB-S06（#53）、FB-S09（#51）
  - `tests/unit/test_book_store_metadata_seam.py` **不在本 WI**（归 WI-4）
- **验收（种子）**:
  - 泛化后的校验仍能抓住三种错：钉条写 `018 debt #54`（#54 归 012）→ 红；钉条写 `012 debt #56` → 红；引用不存在的号 → 红
  - `EXPECTED_*` 与钉条条数不变（18 条）；unit lane 绿
  - 全仓 `git grep -n "012 债 #5[1368]\|012 debt #5[1368]"` 只剩历史叙述（D1 前的记录），不剩现行引用
  - 测试矩阵：待 /tdd-guardian:design-tests
- 这一批原在 [012 §2.2](./012-storage-format.md) 与 [§9 的 018 段](../plan-tech-stack-migration.md) 记为「兑付方改写未做」；本 WI 合入后那两处改为链接本 WI

### WI-2: 每书写协调契约（锁）＋ ADR-0015 草案

- **目标**: 定义并实现一把**每书**写锁，供 import（`process_epub`）/ 删书 / 单本重建索引 / 012 的 `--migrate`、generation swap、批量重建、上传共用。本分支内的持锁者是删书（WI-5）与单本重建（`api_index_book`）；012 的写手在 012 里接入（012 门槛 14）
- **今天的事实**（开工当天复核）:
  - `reader3._acquire_staging_lock` 锁的是**每次运行自己的 staging 目录**，不是书；`_staging_dir_is_owned` 是**探测后即释放**，只回答「此刻有没有活的持有者」，不是互斥
  - `notes_service._book_write_lock` 已是一把两层锁（进程内 `threading.Lock` 注册表 ＋ `fcntl.flock` 阻塞锁），锁文件在书目录里（`notes.json.lock`），且会 `os.makedirs` 书目录
  - 会建书目录的写手不止 notes：`ai/books.py`（`ai_meta.json`）、`ai/conversations.py`（每书存储）、`vector_search.py`（`chroma_db/`）
  - `api_index_book` 在线程池里**同步**跑 `index_book`，所以锁能包住整次重建
- **契约**（§6 Q2 / Q3 / Q12 已裁定，2026-09-26）: ⬛ 2026-10-02 D1：ADR-0015 已 Accepted，契约正文的定义处是 [ADR-0015](../../../adr/0015-per-book-write-coordination.md)（「搬，不抄」；原第 1 – 9 条连同 2026-10-01 的订正都在那里，本文不再保留副本；下文「契约第 *n* 条 / 契约项 *n*」（*n* ≤ 7）与 ADR-0015 Decision Outcome 同号；project-root 对话例外由 [ADR-0018](../../../adr/0018-project-root-conversations-take-book-lock.md) 取代，Proposed）
- **原型**：`018-lock-protocol.PROTOTYPE.html`（纯 JS 状态模型 ＋ 剧本），存于一次性分支 `prototype/018-book-lock`，不进 `master`。它是裁定的推演依据，不是规格——规格以 ADR-0015 为准
- **涉及文件**: 新模块 `src/reader3_app/book_lock.py`、`notes_service.py`、`ai/books.py`、`ai/conversations.py`、`vector_search.py`、`web/routers/search.py`（`api_index_book` 持锁）、`reader3.py`（`process_epub` 持锁）；[`docs/adr/0015-per-book-write-coordination.md`](../../../adr/0015-per-book-write-coordination.md)（Accepted 2026-10-02）
- **验收（种子）**:
  - 两个**进程**对同一本书同时取长写锁：恰好一个成功，另一个得到可判别的拒绝（不是超时、不是异常栈）
  - 持锁进程被 `SIGKILL` 后锁立即可取
  - 删书进行中，notes / ai_meta / conversations / vector 写手（含 vector 的**读**路径）都**不会**把书目录重新建出来（每个写手一条测试）
  - 同一本书的 notes 并发写仍不丢（沿用 notes 现有并发测试，不改一字仍绿）
    - ⬛ 2026-09-30 订正：「不改一字」做不到，改了两个文件——`tests/unit/test_notes_concurrent_write.py` 的 `RENDEZVOUS_TIMEOUT_S` 由 2.0 改为 1.25，`tests/fixtures/notes_concurrency.py` 的 `ObservableBookLock` 追加 `acquire` / `release` / `locked` 垫片（纯追加，`__enter__` 一字未动）。原因：契约第 4 条的 2 秒总预算也覆盖资源锁这一层——旧测试让第一个写手在锁内恰好停 2.0 秒，第二个写手的预算与之同时耗尽，只会 409；有界等待又必须对注册表里的锁对象调 `.acquire`。被测的主张不变：同一本书两个并发写手的标注都留在盘上。变异回执：把书锁与资源锁都改成空操作，线程版与进程版两条并发写测试在 1.25 下均转红（018 WI-2 报告）
    - ⬛ 2026-09-30 订正（既有单测随契约修订，主控裁定）：WI-2 使既有单测 18 条转红，18 条全部修订。（1）书库根目录列举排除 `.locks`：3 条（`test_process_epub_commit` / `test_process_epub_staging` 各 1 条，`test_process_epub_sigkill_recovery::test_w1_c22_message_law`）；（2）第 i 类（断言与建目录无关，书目录只是附带的准备）：15 条。其中 11 条只需在 setup 里建出书目录（`test_notes_no_annotation_loss` 3、`test_fixture_annotation_corpus` 2、`test_vector_index_freshness` 5、`test_vector_index_status_consistency` 1）；另 4 条对话测试（`test_conversation_never_silently_dropped` 的 `per_book_mode_ignores_the_missing_root`×3 与 `unrecognised_mode_falls_back_to_per_book_and_says_so`）因 per-book 对话在锁内复核 `thread.book_uuid`（契约第 6 条），setup 还要写出带该 uuid 的 `ai_meta.json`；期望的文件清单仍是精确相等，显式列出 `ai_meta.json` 与对话文件两项，并新增一条断言：调用前后 `ai_meta.json` 逐字节不变；（3）按契约第 5 条反转为「拒绝、不复活」（第 ii 类）：0 条——没有一条既有测试的主张是「往不存在的书目录写能成功或会建出它」。没有一条断言被放宽；`.locks/` 里只有 `*.lock` 文件，在 `w1_c22` 里用一条正向断言钉住（契约第 1 条）
  - 重建持共享锁期间，notes 保存照常成功；独占写手在场时 notes 在 2 秒预算内 409（不是挂起）
  - ABA：notes 等锁 → 删书 → 同名重导入 → notes 醒来 → 409，新书的 `notes.json` 不变
  - 交叉获取（资源锁 → 书锁）与同栈重入都抛错，不死锁
  - 来自 PR #26 审计的两条转入项：`process_epub` 的**每书准入**（同一本书两次导入并发，今天只有各自的 staging 锁）由书锁独占覆盖；锁等待与 `run_in_threadpool` / `async` 边界——持锁的同步段不得在事件循环线程上跑，释放不得跨线程
  - 测试矩阵：待 /tdd-guardian:design-tests
- **ADR-0015**：已过 [ADR-0000](../../../adr/0000-use-adrs.md) 准入（§6 Q11），Proposed 稿已成。实现若推翻契约某项，先改本段再同步 ADR。ADR-0001 的 Revisit When（`_book_write_lock` 多进程）即此次重访。**本分支合入时 ADR 转 Accepted、本段换链接**（门槛 7）。⬛ 2026-10-02 D1：ADR-0015 已于 2026-10-02 合入回写转 Accepted，契约段已换成链接；此后改契约走 ADR 的修订流程，不再「先改本段」

### WI-3: 欠账 #51 —— provider 保存版本校验（后端 ＋ FB-S09 客户端半边）

- **目标 / 验收**: 见 [#51 行](./009-e2e-annotations.md#跨波欠账)（同 revision 两个客户端 → 第二个 409 且文件保留第一个；不带 revision 的客户端行为不变；加法式）。本文只补约束
- **今天的事实**（实施前）: `ai_settings.json` 有四个写入端——`PUT /api/settings`、`POST /api/settings/import`、`PUT /api/settings/providers/{provider_name}`、`DELETE /api/settings/providers/{provider_name}`；`save_ai_settings` 已是 `mkstemp` ＋ `os.replace` 原子写。处理函数都是 `async def` 且读—改—写之间没有 `await`，所以**单进程内**事实上串行，**跨进程**没有任何协调
- **已定**（§6 Q5；实施取值见下方「实施记录」）:
  - **revision** = `ai_settings.json` 原始字节的 sha256（可选：用进程外不可见的 key 做 keyed hash，免得 revision 本身成为「猜 key 是否变过」的探针——便宜，实施时定）。不用 `st_mtime_ns`（粒度与拷贝保留 mtime 都靠不住），不往文件里加计数字段（改了配置 schema）
  - **传法**：读响应带 `ETag`，四个写入端都认 `If-Match`（`DELETE` 没有 body，只能走头，所以统一走头）。不带 `If-Match` 的请求照旧放行（加法式）
  - **锁**：一把全局 `config/.ai_settings.lock`（`flock` 独占），比对与写入都在锁内；这**不是** WI-2 的每书锁
  - 不匹配 → 409，响应体按 #51 行，不回显任何 key
- **涉及文件**: `web/routers/settings.py`、`ai/config.py`（`load_ai_settings` / `save_ai_settings`）；`frontend/src/settings/index.ts`（provider 保存的 `requestJson` 带 revision、409 走可见错误）；`tests/contract/routes.snapshot`（若加 `If-Match` 头或响应字段，按 ADR-0011 同 commit）
- **验收补充（种子）**: 409 的响应体不回显任何 key（ADR-0012 / 「API key 不回浏览器」）；前端 409 可见错误有 Vitest ＋ 一条 e2e；013 的 `test_provider_save_failure_is_visible` 不改仍绿
- 测试矩阵：`.claude/tdd-guardian/tests-20261001-114124.md`（59 条，R3-1 … R3-4；对抗两轮共补 14 个缺口）
- **实施记录（2026-10-01）**:
  - **revision** = `HMAC-SHA256(进程启动时的 secrets.token_bytes(32), b"file:"+原始字节 | b"absent")`，强 ETag（带引号的 64 位小写十六进制）。key 不出进程，revision 不能被拿来离线猜 key；代价是服务重启后旧页面的 revision 全部失效（一次 409，刷新即好）
  - **If-Match**：强比较；逗号列表、`*` 命中；`W/` 永不命中；任何空元素或不合 RFC 7232 的写法 → 400。不匹配 → 409，`detail` 是固定句子，响应头里不带 ETag 也不带 revision
  - **锁**：`dirname(settings)/.ai_settings.lock`，0600 创建、永不删除；比对、读、写、算新 ETag 在**同一次持锁**里完成，经 `run_in_threadpool` 跑在事件循环外；两个 GET 也取这把锁，免得读到写到一半的 ETag；锁文件建不出来（`config/` 不可写）时两个 GET 退回不持锁的读，写手一律 500 并点名锁路径（终审 M1）
  - **判定顺序**：422 → 404（provider 不存在，锁外先判）→ 400 畸形 If-Match → 409 → 400 语义错误
  - **前端**：页面级唯一 revision（成功但没 ETag 时保留旧值，失败从不更新）；toggle / provider 保存 / 偏好三类写入共用一条页面级队列，revision 在请求**发出时**读取；队首失败不卡住后面的写入。导入无条件、不排队
  - e2e：`tests/e2e/shell_4a/test_settings_rows.py::test_provider_save_conflict_is_visible`（真第二写手，非 mock），`shell_4a` 108 → 109
  - 路由快照未变（只加了请求头 / 响应头，没有新路由或字段）

### WI-4: 欠账 #56 —— 客户端书目列表路由

- **目标 / 验收**: 见 [#56 行](./009-e2e-annotations.md#跨波欠账)（路由进快照；条数 = 书库目录数；书名 = `load_book_metadata()`）
- **路径**（⬛ 2026-10-02 D4 / §6 Q-A）: `GET /api/library`
- **建在接缝上**: 数据只取自 `book_store.load_book_metadata()`（今天是全量读后投影出 `book_id` / `title` / `authors`）。012 WI-5 换它的函数体、012 WI-10 在每项上加 `storage_format`——本路由不得绕过接缝直读 `book.pkl`，否则 012 换实现时它不跟着变
- **字段集**（§6 Q6）: `book_id`、`title`、`authors`、`cover_url`、`book_uuid`。`cover_url` 是 URL 不是字节，`book_uuid` 取自 `ai_meta.json`（读不出 → `null`，按 ADR-0003 不覆写）。`chapter_count`、`storage_format` 留给 012——**不在本 WI 为此扩接缝**，扩了就是替 012 定格式。损坏条目给**显式错误态**（`{"book_id": ..., "error": "unreadable"}` 一类），不静默跳过、不让整张列表 500
- **涉及文件**: 新 router 模块 `web/routers/library_books.py`（列表 ＋ 删书；§6 Q4；不往 `library.py` 里塞——体量以 `scripts/check_router_size.py` 为判据，不写死行数，⬛ 2026-10-02 D2）、`web/server.py`（`include_router`）、`tests/contract/routes.snapshot`、`tests/unit/test_book_store_metadata_seam.py`、`book_store.py`（接缝说明注释，见下；封面挑选函数，§6 Q-C）。**不为 012 的 #55 / #57 预留位置**——它们到时自己按体量选模块
- **接缝守卫测试**: `tests/unit/test_book_store_metadata_seam.py` 的 `test_no_production_call_site_uses_the_new_seam_yet` 有两条断言——(a)「只有 `book_store.py` 提到 `load_book_metadata`」本 WI 起**必然**不成立，改写为「调用方白名单 = {本路由模块}」；(b)「`library_view` 仍 `load_book_cached(item)`」**保留**，它是 012 WI-5 的活。⬛ 2026-10-02 D3：改写后名字里的 `_yet` 不再成立，测试改名为 `test_seam_callers_are_the_allowlist`；`book_store.py` 里接缝说明注释中（「Nothing consumes the seam in this branch」）同一 commit 改成「唯一消费者是 `library_books` 路由」一类的现状
- **验收补充（种子）**: 一本 `book.pkl` 损坏的书不让整张列表 500，它以显式错误态出现在列表里（契约测试写死形状）；返回顺序确定；墓碑目录与 `.locks/` 不出现在列表里
- 测试矩阵：待 /tdd-guardian:design-tests

### WI-5: 欠账 #58 —— 删书路由（WI-2 之后）

- **目标 / 验收**: 见 [#58 行](./009-e2e-annotations.md#跨波欠账)（删后读与 `POST /api/index` 都 404；FB-L18 可测）
- **路径**（⬛ 2026-10-02 D4 / §6 Q-A）: `DELETE /api/library/{book_id}?delete_conversations=false`；成功 204、无响应体（§6 Q-F）
- **机制的展开**（意图文件格式、终结器各步、对话发布、统计代次、chromadb 退役、测试分层与红灯检查）见[执行计划 §3 WI-5](../../20261002-018-second-slice-plan.md#3-逐-wi-执行要点)；下面只记定义与订正，不复述机制
- **#58 行里有一句已过期**：它要求「失效 `load_book_cached` 的 lru_cache」。011 之后 `load_book_cached` 以 `(st_mtime_ns, st_size)` 为 key、每次调用先 `os.stat`，删掉的书不会从缓存里被读出来。**真正要处理的是别处**：`server._stats_cache`（5 秒 TTL 的书库统计）、搜索索引缓存、会复活目录的写手（WI-2 不复活规则）
- **边界**（沿 [ADR-0012](../../../adr/0012-security-boundaries.md) 的思路；ADR-0012 **不**定义大小上限与 409，那些由本 WI 自定）:
  - `book_id` 过 `safe_book_folder` ＋ `_validate_book_id`（枚举目录成员）
  - **删除顺序**（§6 Q8 已裁定）:
    1. 非阻塞取该书**独占**锁；拿不到 → 409
    2. **锁内**复核书目录存在；不存在 → 404
    - ⬛ 2026-10-02 D12（插在第 2、3 步之间）：**写删除意图文件并 `fsync`**——`books/.{book_folder}.deleted-{pid}-{8hex}.intent.json`，记 `delete_conversations`、`book_uuid`（可为 `None`）、删时解析出的项目级对话根的绝对路径；根解析不出（`server._project_conversations_root` 返回 `None`）且要保留的对话存在 → 提交点前 500，书完好
    3. 在全局集合锁下把该书从 `library_collections.json` 的所有集合里移除（集合锁即 [009 #60](./009-e2e-annotations.md#跨波欠账) 已合入的那把：`library_collections.json.lock`）。⬛ 2026-10-02 D7：用新函数 `collections_service.remove_book_everywhere`（或等价物）；D13：本步保留（ADR-0015 第 8 条的顺序不变），终结器再移除一次
    4. 书目录**原子改名**为墓碑 `books/.{book_folder}.deleted-{pid}-{8hex}/`（⬛ 2026-10-02 D10 / §6 Q-D：加随机后缀，原为 `.{book_folder}.deleted-{pid}/`；与意图文件同后缀），`fsync` 父目录——**这是提交点**：之前崩溃，书完好；之后崩溃，书已不在库里
    5. 失效三处进程内缓存：`server._stats_cache`、搜索索引缓存、`ai/books.py` 的 `BookUuidResolver` 映射（[009 #61](./009-e2e-annotations.md#跨波欠账) 已让它命中时查盘，但删书仍主动失效，免得多一次扫描）。⬛ 2026-10-02：`BookUuidResolver` 经新的公开 `forget_folder` 失效（D6）；统计缓存加代次，挡住删前开始的计算在删后写回旧值；另加第四处——**退役该书 `chroma_db` 路径的 chromadb 进程内 system**（D14），否则同进程「删 → 同名重导入 → 索引」拿到死句柄
    6. ~~仅当请求带 `delete_conversations=true`（默认 `false`）才删该书按 `book_uuid` 存的对话；否则对话保留为孤儿。~~ ⬛ 2026-10-02 D5 / D16，按 §6 Q8 订正（维护者裁定 Q-B）：`delete_conversations=true`（默认 `false`）→ 删墓碑里的 `ai_conversations/`（随第 7 步）＋ 配置的项目级根下的 `{book_uuid}/`。`false` → **在独占锁内、逐个文件**把墓碑里 `ai_conversations/*.json` 发布到**配置的**项目级对话根（`server._project_conversations_root`，不是写死的 `conversations/`）下的 `{book_uuid}/`；目标已有同名文件时 `last_updated` 较新者胜；没有 `book_uuid` → 丢弃并记日志；按**磁盘上实际有什么**决定，不看当前存储模式；由终结器依意图文件执行，全部发布成功之前不许第 7 步。项目级写手按 [ADR-0018](../../../adr/0018-project-root-conversations-take-book-lock.md)（Proposed）持该书**共享**锁并锁内复核书目录，提交点后的迟到写入得 404，不会重建 `{book_uuid}/`。确认对话框问用户——归 014 WI-16b
    7. `rmtree` 墓碑；⬛ 2026-10-02 D12：最后删意图文件
    8. 放锁
  - ⬛ 2026-10-02 D12：**第 5 – 7 步收进一个幂等的终结器**（每一步可从任何一步重入：再做一次集合移除 → 失效缓存 → 对话 → `rmtree` 墓碑 → 删意图文件），删书请求与墓碑清扫共用。提交点之后终结器任何一步失败只记日志、留下墓碑 ＋ 意图给下一次清扫，响应仍是 204（§6 Q-F）
  - **墓碑清扫**：服务启动时、以及每次删书开始前扫~~`books/.*.deleted-*/`~~；对每个墓碑**取得并持有**对应书的独占锁再~~`rmtree`~~跑终结器，拿不到就跳过（「探测后即释放」再删是错的——探测与删除之间别人可以拿到锁，Codex 在原型上复现）。读侧照旧按 `_data` 后缀过滤，所以没清掉的墓碑只占空间，不出现在书库里
    - ⬛ 2026-10-02 D10：墓碑判据改为严格正则 `^\.(?P<folder>.+_data)\.deleted-(?P<pid>\d+)(-[0-9a-f]+)?$`，并要求目录名**不以 `_data` 结尾**（glob 会误收以点开头、`_data` 结尾的合法书目录）；意图文件（`.intent.json` 结尾）另有自己的正则，两类不互相匹配
    - ⬛ 2026-10-02 D12：清扫按「墓碑 ＋ 意图 → 跑终结器；只有意图 → 提交点前崩溃，书完好，删意图；只有墓碑 → 按 `delete_conversations=false` 跑终结器」判定。清扫也在每次 `process_epub` 取锁之前跑（保证同名重导入前上一本的终结器已跑完，Q12），在取本次删书的目标锁之前跑（各墓碑各持各的锁、处理完即放）。**只有一个清扫入口**，启动、删书、导入三处调同一个函数，012 的 GC 一步加在这里，不另起入口
  - ⬛ 2026-10-02 D13：加书进集合改为在**集合锁内**复核书目录存在（今天在锁外用 `_validate_book_id` 验书，能落在第 3 步之后），不在 → 404；锁序仍是「书锁 → 集合锁」，加书只取集合锁，没有环
  - 第 3 步落在提交点之前，崩在 3 与 4 之间 → 书还在、集合里没了它：可接受（用户可重加），反过来（书没了、集合里还挂着）才是读侧必须容忍的情形——集合读取跳过不存在的 `book_folder`
  - **删后再导入同一 EPUB = 新书**（§6 Q12）：新 `book_uuid`，旧对话不重新挂上，集合成员不恢复（第 3 步已移除）
  - **409**：该书的锁被他人持有（导入 / 重建 / 迁移 / 上传进行中）。**404**：书不存在
- **涉及文件**: `web/routers/library_books.py`、`web/server.py`（`_stats_cache` ＋ 代次；`_startup_scan_books` 调清扫）、`search_service.py`、`ai/books.py`（`BookUuidResolver` 加公开的 `forget_folder`，D6）、`collections_service.py`（新 `remove_book_everywhere` 或等价物，D7；`update_collection_books` 锁内复核，D13）、`ai/conversations.py`（范围扩到 `save_project_conversation` 与 `save_conversation_multi`——项目级写手持共享书锁，D16 / ADR-0018）、WI-2 的锁模块、`tests/contract/routes.snapshot`；⬛ 2026-10-02 补：`reader3.py`（`process_epub` 取锁前跑清扫，D12）、`web/routers/library.py`（`api_collections_update_books` 的复核，D13）、`vector_search.py`（chromadb system 退役，D14）
- **e2e**: 删书测试**不得**改动 `baseline_1b` 共用的会话语料库——用自己的库目录与自己起的服务（`tests/fixtures/deg_assertions.py` 的起服务形状），不在任何分组目录里放 `conftest.py`
- **验收补充（种子）**: ~~删书与单本重建并发 → 一方 409~~（⬛ 2026-10-02 D15：两种次序分别写——**重建先持共享锁** → 删书 409，书完好；**删书先持独占锁** → 重建在 2 秒预算内等到删书结束，锁内复核得 `BookGone` → 404，删书超过预算时才是 409），且不出现「删掉的目录被重建出来」；删后 `/api/library/stats` 立即反映；删后该书不再出现在 WI-4 的列表里、不在任何集合里；`delete_conversations` 缺省时对话文件~~原样保留~~保留在磁盘 `{配置的根}/{book_uuid}/` 下（默认 `per_book` 模式也一样，D5 / Q-B），为 `true` 时两处都删掉；删后重导入同一 EPUB 得到新 `book_uuid`；在提交点前后各注入一次 `SIGKILL`，重启后书库分别是「书完好」与「书不在、墓碑被清扫」（⬛ 2026-10-02 D12：崩溃点扩到意图写入前后、对话发布中途、`rmtree` 前后，每点 × `delete_conversations` 两个取值；清单见执行计划 §3 WI-5）；集合竞态：加书进集合与删书交错后，集合里没有它，同名重导入的新书不在任何集合里（D13）；同进程「索引 → 删 → 同名重导入 → 索引 → 查询」用真 chromadb 全部成功（D14）
- ~~测试矩阵：待 /tdd-guardian:design-tests~~ ⬛ 2026-10-02 协调者裁定：测试矩阵 rev 3（78 例：5a 53 / 5b 11 / 5c 14 ＋ 4 行 `LIBRARY_CASES` ＋ 1 行快照），对抗审查两轮（第 2 轮后的定稿未再受审，CP2 由评审补查 rev 3 新增例）；分三段落地 5a 服务层 → 5b 写手与入口 → 5c 路由，各一张红灯收据（W5-12）
- **⬛ 2026-10-02 协调者裁定（WI-5 实现期，Q1 – Q6、W5-7 – W5-23；与上文冲突处以本节为准）**:
  - **Q1 / W5-7 意图先于提交**：意图文件写入并 `fsync` 后才改名。**只有墓碑、没有（或损坏的）意图 → 一律保全**：墓碑原地留下、记日志，不跑终结器（取代上文 D12「只有墓碑 → 按 `false` 跑终结器」）。
  - **Q6 意图记绝对路径**：意图记删时解析出的项目级对话根（或 `null`）与集合文件 `collections_service.collections_path(dirname(books_dir))`；终结器只读意图，不导入 `web.server`、不读设置。缓存失效走调用时注册的钩子（`register_invalidator`，可注销）与代次计数。
  - **Q2 根解析不出（`None`）**：`true` → 跳过项目级一步，204，记日志；`false` 且有按书对话 → 提交点前、锁内 **409**，书不动（取代上文 D12 的 500）；没有按书对话 → 照常。
  - **Q3 `book_uuid` 畸形视为 `None`**：`false` 且有按书对话 → 提交点前 409；`true` → 丢弃并记日志。W5-9：单个对话文件自带 uuid 畸形 → 退回意图里的 uuid，Q3 的拒绝不变。
  - **Q4 失效范围（在本 WI 内）**：`search_service.load_book_index`（`cache_clear`）、`book_store.load_book_cached`、统计代次、`BookUuidResolver.forget_folder`、chromadb system 退役；其余向量侧缓存记入 Limits。提交点之后的失效放在 `finally`，终结器中途失败也不会留下「204 ＋ 旧缓存」。
  - **Q5 锁内复核**：书目录已不在 → 走现有 not-found 路径 404，集合不变。
  - **W5-8 `delete_conversations` 手工解析**：缺省 / `true` / `false`（大小写不敏感）有效，其余 400。
  - **W5-10 / W5-11 集合移除移入终结器**（提交点之后；取代上文第 3 步「提交点前移除」）；请求内清扫用 `SHORT_BUDGET_S`；`save_project_conversation` 增必填 `books_dir`，调用方随 5b 更新。
  - **W5-13 发布前全量预检**：终结器先预检全部按书对话，任一不可读 → 不发布、不清理，墓碑保全并记日志，不出现半发布状态。
  - **W5-14 保全无副作用 ＋ 同名活书**：保全的墓碑跨多次清扫零集合 / 映射 / chroma 副作用；同名活书（判据与书库列表同一谓词）存在时，终结器跳过集合移除、`forget_folder`、chroma 退役。
  - **W5-15 删书预检（仅 `false`）**：锁内、提交点前预检按书对话，任一不可读 → 409 并点名该文件，书原样在列、字节不变、无意图无墓碑；`true` 跳过预检。终结器预检（W5-13）保留为兜底。
  - **W5-16 同名活书时**：照常发布对话，再删墓碑与意图；只跳过集合移除、`forget_folder`、chroma 退役；发布或预检失败 → 按 W5-13 保全。
  - **W5-17 / W5-21「不可读」的定义** = 发布循环的校验不通过：非对象（如 `[]`）、不安全的 `conversation_id`、文件名不是 uuid、目标 uuid 解析不出、项目级根下已有的同名目标文件无法解析（W5-21）。**缺失或非字符串的 `last_updated` 算可读**，按 `""`（最旧）比较；预检绝不比现有读路径更严。
  - **W5-22 新者胜的比较键**：删除路径上 `last_updated` 非字符串 / `None` / 缺失一律按 `""`；同值时保留项目级根下已有的那份（严格 `>`）。`conversations.py:344` 的 `str(v or "")` 不改，二者的差异记入 F-005 Limits。
  - **W5-18 清扫报告**：`SweepReport` 增 `failed`；某个墓碑终结失败不挡住其余墓碑；`process_epub` 遇同名条目在 `failed` 里则拒绝导入（⬛ CP2 订正：实现与矩阵 B-9 为「任何残留同名墓碑——busy / 保全 / failed——都拒绝」，以此为准）。
  - **W5-19**：独占锁取不到立即 `BookLockBusy`、从不等待，清扫不加轮询；`SHORT_BUDGET_S` 只透传给共享锁等待。
  - **W5-20**：失效钩子注册表提供重置 / 注销接口；服务端注册调用时查找的 lambda（`book_uuid_resolver.forget_folder`），保持补丁接缝可替换。
  - **配对键**：墓碑与意图按 `(folder, pid, token)` 配对，不只按 folder；清扫在取得每个条目的锁之后重新分类（条目已配对 → 终结；已消失 → 跳过）。对话发布顺序按文件名排序。
  - **W5-23**：D-8(b) 的 `unresolvable_uuid` 一格收窄 —— 磁盘上取不到 uuid 时 true 模式不碰项目级根（`R/U` 保留、不为文件自带 uuid 建 `R/V`），并记一条点名 `book_uuid` 的 WARNING（同 F-5(c)）。矩阵原断言与 Q3 / F-5(c) 相矛盾；WI-5a 回执因此一行 SEPARATION-BROKEN，经裁定接受，仅限该行。
  - 机制细节（意图格式、终结器步骤次序、测试分层）以执行计划 §3 WI-5 与本节为准。

### WI-6: 欠账 #53 —— 书库导出

- **目标 / 验收**: 见 [#53 行](./009-e2e-annotations.md#跨波欠账)（路由进快照；非空合法 JSON；FB-S06 半边）
- **路径**（⬛ 2026-10-02 D4 / §6 Q-A）: `GET /api/library/export?include=conversations`（缺省不带对话）
- **schema**（§6 Q7 已裁定）: 每本书导出 **metadata**（WI-4 的字段集）＋ **annotations**（`notes.json` 的内容）；**对话只在 `?include=conversations` 时带**；**不导出章节正文**（EPUB 本身才是正文的来源，导出不是备份）。整库导出；单本导出不在本 WI
- **模块**: 新 router `web/routers/library_export.py`（§6 Q4）
- **与存储格式无关**: 导出只经 `book_store` 读，所以 012 换格式后本路由不改；012 门槛 13 验的正是「导出不把 `corrupt` 当 `valid`」。#53 兑付方列原写的「内容依赖 012 存储格式」由 WI-1 改掉
- **边界**: 整库导出可能很大——流式还是一次成型、有无大小上限、临时文件是否 `mkstemp`，本 WI 自定（ADR-0012 没有现成规则）
- **涉及文件**: `web/routers/library_export.py`、`web/server.py`（`include_router`）、`frontend/src/settings/index.ts`（`wireExport` 的 `set-export-json`）、`tests/contract/routes.snapshot`
- **验收补充（种子）**: 缺省请求的输出里没有对话、没有章节正文；`?include=conversations` 时带；损坏的书以 WI-4 的错误态出现，不让整次导出失败
  - ⬛ 2026-10-02 D19：**分部件的失败策略**（每条是 WI-4 的列表条目 ＋ `annotations`，带对话时再加 `conversations`，另有一个 `component_errors` 列表，字段名由 design-tests 定）——书在枚举之后消失 → **整条跳过**（§6 Q-G，与 WI-4 同一条规则）；`book.pkl` 读不出 → 整条是 WI-4 的错误态；`notes.json` 坏 → `annotations` 为 `null` 并记进 `component_errors`；对话文件坏 → 读不出的 `conversation_id` 记进 `component_errors`，**不静默跳过**；只有枚举本身失败才 500。细节见[执行计划 §3 WI-6](../../20261002-018-second-slice-plan.md#3-逐-wi-执行要点)
  - ⬛ 2026-10-02 D9：`tests/e2e/shell_4a/test_settings_rows.py` 的 `test_key_never_echoed_and_exports` 最后几行今天断言「导出书库 JSON 暂不支持、0 个请求」。本 WI **原地反转**它：发出 1 个请求，下载的内容是合法 JSON。这是有意地重新判一条测试，不是放宽；`shell_4a` 条数不变
- 测试矩阵：待 /tdd-guardian:design-tests
- **⬛ 2026-10-03 协调者裁定（WI-6 实现期，W6-1 – W6-11、R-1 – R-4；与上文冲突处以本节为准）**。来源与理由的定义处是[执行计划 §6 的 WI-6 表](../../20261002-018-second-slice-plan.md)，本节只记结论；对外行为的说明见 [`docs/export-import.md`](../../../export-import.md#library-export-018-wi-6):

  | # | 问题 | 裁定 |
  |---|---|---|
  | W6-1 | 拿 `book_uuid` 走 `_book_uuid_or_none` 会取 EX 锁并铸造 `ai_meta.json` | 导出只读：复用 `book_lock.read_book_uuid`，不取锁、不铸、不新增函数；缺失或不可读 → `null` ＋ WARNING（ADR-0003）。与 `GET /api/library` 可能在这一个字段上不同，记入 F-005 Limits |
  | W6-2 | `include=conversations` 的对话来源 | 按盘上实际存在，不看当前存储模式：总读 per-book `ai_conversations/`；项目级根可解析且 uuid 合法时再读 `{root}/{uuid}/`（默认根 `conversations/`）；按 `conversation_id` 去重，`last_updated` 严格更大者胜（非字符串按 `""` 比） |
  | W6-3 | 部件错误字段 | `component_errors`：对象列表（`component` = `annotations` / `conversations`，对话可带 `conversation_id`）；可读条目上恒有（可为空），WI-4 的错误条目上不出现 |
  | W6-4 | 项目级来源整体失败 | 照导 per-book，追加 `{"component":"conversations"}`，不静默；来源目录不存在不算错 |
  | W6-5 | 读的途中单个对话文件消失 | 书还在 → 静默略去；书目录没了 → 整条跳过（D19） |
  | W6-6 | FB-S06 按钮 | 请求默认导出（不含对话）；`include` 的 UI 开关推迟到 014 或之后 |
  | W6-7 | `include` 语法 | 同 W5-8 的严格度：恰好一个值、大小写不敏感的 `conversations`；逗号列表 / 空值 / 重复 → 400 `include must be "conversations"` |
  | W6-8 | 外壳 | `{"books":[...]}`，顺序同 `GET /api/library`（`list_book_ids`）；不加 `exported_at` / `schema_version`。一次成型的 `JSONResponse`，不流式、不设上限（上文「边界」一条由此落定） |
  | W6-9 | 对话的导出形式 | 原样导出已存 JSON 对象（无损，不经 `_parse_thread` 补时间）；`conversation_id` 非法的文件算不可读 |
  | W6-10 | 文案 | 文件名 `reader3-library.json`；成功「书库已导出。」；失败前缀「导出书库失败：」 |
  | W6-11 | 同一 `conversation_id` 两份 `last_updated` 相等 | 取项目级那份（与 W5 的 F-15「平手时既有项目级副本胜」一致），确定性输出；E21 钉死这一份 |

  CP1 确认的默认（R-1 – R-4）:
  - **R-1 畸形 uuid**：`ai_meta.json` 里的值不是合法 UUID → `book_uuid` 为 `null` ＋ WARNING，且该书的项目级来源视为不可解析（不拿它拼路径）。
  - **R-2 带对话时的 `ai_meta.json`**：存在却读不出合法 uuid → 追加 `{"component":"conversations"}`；文件不存在 → 不记错。
  - **R-3 文件名与载荷不一致**：载荷里的 `conversation_id` 与文件主名不同的情形推迟处理；身份以文件主名为准。
  - **R-4 `OSError` 的分档**：来源目录上非 `FileNotFoundError` 的 `OSError`（如无权限）→ 整源错误 `{"component":"conversations"}`；单个文件的 `OSError` → 该文件的 `{"component":"conversations","conversation_id":<主名>}`。

### WI-7: 欠账 #31 —— CI e2e job 收尾对账（最后做）

- **先说清楚这条账的现状**：#31 **已于 2026-09-20 结清**（[#31 行](./009-e2e-annotations.md#跨波欠账) 状态列）。`tests.yml` 的 `e2e` job 已存在（干净 ubuntu、`uv sync --frozen`、记 Chromium 版本、`soak_run.py --log-dir soak-ci-logs` 要 68/68、再跑 `-m "not baseline_1b"`）；机制挑战闸第 1 项已在它上面 PASS（[`soak-log.md` 机制挑战闸执行记录](./soak-log.md)，run 35584711194）。**本 WI 不建 job**
- **「补 soak 的环境多样性那一半」这个说法不成立**：CI 的运行**不进 soak 台账**，这是写定的——
  - `tests.yml` 的 `e2e` job 头注释：结果记进机制挑战闸表，「不往 soak 台账追行」，「不传 `--append`」
  - [§7 清零规则](../plan-tech-stack-migration.md) 第 2 条：`browser` 或 `os` 变了就清零。CI 行的 `os` 是 `linux-*`、本地是 `darwin-*`，混进去每换一次就清零一次（⬛ 2026-09-28 批次规则 3：读作「就不是同一批」——一行 linux 混进批次窗口，该批判 FAIL）
  - 所以「环境多样性」由 CI job 以**独立信号**的形式提供（每次跑都是一次干净 Linux 的 68/68 首次通过核验），不是填台账的行
- **目标**:
  1. ⬛ 2026-10-02 D8：**已完成**——`tests.yml` 的 `e2e` job 头注释已写明「也跑在每个向 `master` 开的 PR 上」，plan §7 那段已标注为过期快照；本 WI 只剩下面的「核验 ＋ 记录」两项。原文：**对账**：修掉仍把 #31 写成「没建」「待定」的地方——009 #31 行兑付方列（WI-1 已改）、§7「该补偿至今没有建出来」一段（**§7 不归本文改**，见本 WI 末尾）、`tests.yml` 的 `e2e` job 头注释里「一个触发器都不新增」「日常 commit 与 PR 一律不跑」两句（2026-09-23 已加 `pull_request → master`，文件头注释已更新，job 注释没跟上；`.github/workflows/` 不在冻结集）
  2. **核验**：在本分支的**合并头**上手点一次 `gh workflow run tests.yml --ref <合并头所在 ref>`，`e2e` job 绿且 `attempt=1`；本分支 PR 上 `pull_request` 触发的那一次同样要绿（门槛 R 适用）
     - ⬛ 2026-10-02 D17：「合并头」落实为**冻结的 PR 头 SHA** `H`——冻结后不再推任何 commit（含记录）；dispatch 后用 `gh run view <id> --json headSha` 核对等于 `H`，PR 上那次运行的 `headSha` 同样是 `H`；合并用 `gh pr merge --merge --match-head-commit H`，头被动过就拒绝、回到冻结一步。步骤见[执行计划 §3 WI-7](../../20261002-018-second-slice-plan.md#3-逐-wi-执行要点)
  3. **记录**：两次运行的 run id、commit、Chromium 版本记进 `soak-log.md` 新开的「CI 运行记录」一节（§6 Q9；**不是** soak 台账），本文 §8 只放链接
     - ⬛ 2026-10-02 D17：这条记录放在**合入后的回写 commit** 里，不进 PR——记录 commit 本身会移动合并头
- **不做**: 不改 `tests.yml` 的触发器与步骤；`soak_run.py` 的硬拦截是 WI-8，不在本 WI
- **§7 / §9 的措辞归协调者改**：本 WI 只列需改之处，不动 `plan-tech-stack-migration.md`

### WI-8: `soak_run.py --append` 硬拦截

- **目标**: 把「soak 台账只收 `master` 上、工作站上的行」从流程约束变成机器拦截（§6 Q10）。`--append` 时：环境变量 `GITHUB_ACTIONS` 存在 → 拒绝；~~当前分支不是 `master` → 拒绝~~；都以非零退出码并说明原因。不带 `--append` 的核验跑法不受影响
  - ⬛ 2026-09-30 订正（§6 Q10）：第二条改为 **`git merge-base --is-ancestor HEAD origin/master` 不成功 → 拒绝**。原判据「当前分支是 `master`」会拒掉正确流程——批次按 `soak-log.md` 表头在被测 SHA 的**干净 detached worktree** 里跑，那里没有分支名。新判据下，`master` 上某个 SHA 的 detached worktree 放行，未合入的特性分支 SHA 拒绝。`origin/master` 解析不出来时怎么报错交给 design-tests，不是新规则
- **涉及文件**: `scripts/soak_run.py`（不在冻结集——冻结集是 `HASH_COVERED_PATHS` 所列 8 条路径，本脚本不在其中；改它不改 `suite_hash`，开工当天复核）、它的单元测试 `tests/unit/test_soak_run.py`（⬛ 2026-10-02 D18：含其中已有的 `--append` 子进程用例的改写，见下）
- **验收（种子）**: ~~三种情形各一条测试——CI 环境 ＋ `--append` → 拒绝；非 `master` ＋ `--append` → 拒绝；`master` ＋ 非 CI ＋ `--append` → 放行~~（用假 git / 假环境，不真跑 soak）
  - ⬛ 2026-09-30 按订正后的规则，至少四条：CI 环境 ＋ `--append` → 拒绝；`HEAD` 不是 `origin/master` 的祖先（未合入的特性分支 SHA）＋ `--append` → 拒绝；`master` 分支上 ＋ 非 CI ＋ `--append` → 放行；**`master` 上某个 SHA 的 detached worktree ＋ `--append` → 放行**
  - ⬛ 2026-10-02 D18：`tests/unit/test_soak_run.py` 里已有的 `--append` 子进程用例（经 `_synthetic_append_argv` 调用、在 `cwd=REPO_ROOT` 下跑）在 `GITHUB_ACTIONS=true` 下和在未合入的 detached SHA 上**都要仍绿**。做法：子进程用受控 env（显式去掉 `GITHUB_ACTIONS`），git 判据走可注入的仓库（临时 git 仓库），且注入口**只在台账是仓库外临时文件时生效**，不能被用来往 canonical 台账写。新拦截与 `--no-precheck` 无关。见[执行计划 §3 WI-8](../../20261002-018-second-slice-plan.md#3-逐-wi-执行要点)
- 测试矩阵：待 /tdd-guardian:design-tests

---

## 4. 出口闸

全部满足才算完。~~「证据位置」在核验时填，现在全部是占位。~~ ⬛ 2026-10-07 合入回写：证据按合并头填。合并头 = 冻结的 PR 头 `b6025ba`（它已并入 master `09893a9`，与合并 commit `74384b1` 同树 `df20cf4`）；CI 三个运行与本地 push 闸的数字只在 §8「第二段」一处，下表只引用。

| # | 门槛 | 判据 | 证据位置 |
|---|---|---|---|
| 1 | 全部 lane 在合并头上绿 | `.claude/tdd-guardian/config.json` 里**每一条** lane（不写死条数），带 `env -u FORCE_COLOR`；`/tdd-guardian:gate push` | ✅ 本地 push 闸在 `b6025ba` 上全部 lane 绿（unit / verify-control / fe-unit / packaging / e2e，数字见 §8 第二段）；CI 在同一 SHA 上 `tests.yml` 的 `unit` ＋ `e2e` job 绿（run [37635190616](https://github.com/anzchy/reader3-pro/actions/runs/37635190616)、[37635220594](https://github.com/anzchy/reader3-pro/actions/runs/37635220594)） |
| 2 | 类型检查 | `uv run mypy src/` 干净 | ✅ CI `tests.yml` unit job 的 `mypy` 步在 `b6025ba` 上绿（run 37635190616）；2026-10-07 回写时在同树 `74384b1` 上复跑 `uv run mypy src/`：no issues，48 个源文件 |
| 3 | lint | `uv run ruff check src/ tests/ scripts/` 干净（不跑 `ruff format`）；`scripts/lint_*.py` 全部 rc=0 | ✅ CI `tests.yml` 的 `ruff check` 步与 `lint.yml`（run [37635190619](https://github.com/anzchy/reader3-pro/actions/runs/37635190619)）在 `b6025ba` 上绿；回写时在 `74384b1` 上复跑 `lint_e2e_selectors` / `lint_inline_html` / `lint_testid_naming` / `lint_token_refs` rc=0、`lint_e2e_groups`（经 `uv run`）rc=0；`lint_contracts` 回写 worktree 无 `node_modules`（depcruise 起不来）未复跑，以 CI 为准 |
| 4 | router 体量 | `python3 scripts/check_router_size.py` rc=0（新路由不许挤爆 500 行） | ✅ `lint.yml` run 37635190619 含 `check_router_size.py`，绿；回写时在 `74384b1` 上复跑 rc=0。新 router 是 `library_books.py` 与 `library_export.py`，未挤进 `library.py` |
| 5 | 路由快照同 commit | 每个新增 / 改动路由的 commit 里同时改了 `tests/contract/routes.snapshot`，diff 只有新增行（WI-3 若给已有路由加头 / 字段，只许加法）；PR 描述写明破坏性与迁移路径（ADR-0011） | ✅ `routes.snapshot` 对第一段合并头 `c08317b` 只增 3 行（`DELETE /api/library/{book_id}`、`GET /api/library`、`GET /api/library/export`），无删改；各随所属路由 commit（WI-4 `95eb94e`、WI-5c `642bbc5`、WI-6 `2066f29`）；PR #37 正文「API（ADR-0011）」节写明加法式、无破坏 |
| 6 | e2e 分组登记 | 新增的每条 e2e 都登记进 `scripts/lint_e2e_groups.py`（验收目录进 `EXPECTED_ACCEPTANCE_PER_DIR`，或模块进 `UNGROUPED_E2E_MODULES` 并同步 `EXPECTED_UNGROUPED_ITEMS`；新分组还要进 `pyproject.toml` markers 与 `tests/unit/test_e2e_group_guard.py` 的钉死副本）；合入前在分支上跑一次 `soak_run.py`（只核验、不 `--append`）确认 deselected 精确相等 | ✅ 第二段无新增 e2e 模块（`tests/e2e` 对 master 的 diff 只有 `shell_4a/test_settings_rows.py` 一处原地反转，条数不变）；`lint_e2e_groups.py` 在 `74384b1` 上收集 270 条、`baseline_1b` 132/132，rc=0；分支上 `soak_run.py` verify-only（不 `--append`）132 passed / 138 deselected（PR 正文，`2066f29`），CI `e2e` job 在 `b6025ba` 上同数（见 [soak-log「CI 运行记录」](./soak-log.md#ci-运行记录)） |
| 7 | 锁契约 | WI-2 验收的跨进程互斥、`SIGKILL` 释放、各写手不复活目录、共享写手 2 秒内 409、ABA 身份复核、交叉获取抛错六类测试齐全；ADR-0015 在本分支合入的同一 PR 里由 Proposed 转 **Accepted**（§6 Q11）。⬛ 2026-10-02 D1：转 Accepted 已由第一段合入回写完成（§8），WI-2 契约段已换成一行链接到 [ADR-0015](../../../adr/0015-per-book-write-coordination.md)；本门槛剩下的是删书部分的测试，以及合入时把 ADR-0015 的 compliance 改成 Full。[ADR-0018](../../../adr/0018-project-root-conversations-take-book-lock.md) 在第二段合入 PR 里由 Proposed 转 Accepted | ✅ 删书部分的锁测试齐：`tests/unit/test_library_delete.py`（D2a、FX37-11a–f）、`tests/unit/test_library_delete_sweep.py`（S2 / S3 / S4a / S4b）、`tests/unit/test_project_conversation_book_lock.py`、`tests/contract/test_library_delete_route.py`；ADR-0018 在 PR #37 内转 Accepted（`82285b3`，FX37-3 `d6c6a1c` 同 PR 修订）。⚠️ ADR-0015 compliance：本行原文要「改成 Full」，[执行计划 §7](../../20261002-018-second-slice-plan.md) 的定义是「018 全部写手已接入，012 的写手待接入」——2026-10-07 回写按后者写，标签仍为 Partial（012 写手未接入），见 [ADR-0015](../../../adr/0015-per-book-write-coordination.md) Current compliance |
| 8 | 每条欠账一个 commit 结清 | 009 表 #51 / #56 / #58 / #53 / #31 各行状态改为已结清并附 commit | ✅ 009 欠账表 #51（第一段 `2d5f96f`）/ #56（`95eb94e`）/ #58（`e2497fc` / `dc7dd27` / `642bbc5` / `31527de`）/ #53（`2066f29`）均已结清并附 commit 与合并 SHA；#31 早于 018 结清（2026-09-20），本次补 CI 记录链接——见 [009 欠账表](./009-e2e-annotations.md#跨波欠账) |
| 9 | #31 的 CI 核验 | 合并头上至少一次 `workflow_dispatch` 的 `tests.yml` 运行，`e2e` job 绿、`attempt=1`；PR 的 `pull_request` 运行同样绿。run id 按 WI-7 的记录位置落档。⬛ 2026-10-02 D17：「合并头」= 冻结的 PR 头 SHA，两次运行的 `headSha` 都等于它，合并用 `--match-head-commit`；`soak-log.md` 的记录挪到合入后的回写 commit | ✅ 冻结 PR 头 `H` = `b6025ba`：`workflow_dispatch` run [37635220594](https://github.com/anzchy/reader3-pro/actions/runs/37635220594) 与 `pull_request` run [37635190616](https://github.com/anzchy/reader3-pro/actions/runs/37635190616) 的 `headSha` 都是 `b6025ba`，`e2e` job 绿，`attempt=1`；run 细节记在 [soak-log「CI 运行记录」](./soak-log.md#ci-运行记录) |
| 10 | ~~合入后 soak 一次~~（⬛ 2026-09-30 被 [plan §7「012 开工核验」](../plan-tech-stack-migration.md#012-开工核验2026-09-30-维护者裁定) 取代：012 开工要在它开分支的那个 `commit` 上新跑一批，合入头红不红由那一批覆盖；本门槛不再单独要求，原文保留） | 合入后在 `master` 上跑一次 `soak_run.py --append`，green，`suite_hash` 仍是冻结值；这一行记进台账（~~它是正常计数行，commit 变不清零~~ ⬛ 2026-09-29：批次规则下单独一行不计入任何批次，只证明合入头没把 `baseline_1b` 弄红；012 开工要的批次见 [012 §4 门槛 F](./012-storage-format.md)） | —（已被 012 开工核验取代；合入后**未**跑 `--append`，按本行裁定不需要） |
| F | ~~**冻结区零字节改动**~~（⬛ 2026-09-28 随 [012 门槛 F](./012-storage-format.md) 放宽：冻结区可以改，但改了就须在合并头的新 `suite_hash` 上重跑一批并通过，否则 012 开工时对不上最后一次通过批次；仍应避免无谓改动。下面原判据保留作「没动冻结区」时的核对方式。⬛ 2026-09-30：012 开工一律新跑一批，见 [plan §7「012 开工核验」](../plan-tech-stack-migration.md#012-开工核验2026-09-30-维护者裁定)；本门槛只剩「别无谓动冻结区」的约束） | 下列 8 条路径 `git diff --stat master... -- <paths>` 为空，`suite_hash` 与 [`soak-log.md`](./soak-log.md) 表头冻结值一致：`tests/e2e/baseline_1b/**`、`tests/e2e/conftest.py`、`tests/e2e/helpers.py`、`tests/e2e/test_harness_smoke.py`、`tests/fixtures/epub_corpus.py`、`tests/fixtures/epub_zip.py`、`tests/fixtures/ai_stub.py`、`tests/conftest.py`。路径清单的定义处是 `soak-log.md`「`suite_hash` 的取法」与 `scripts/soak_run.py` 的 `HASH_COVERED_PATHS`，冲突以那里为准 | ✅ 8 条路径对 master 父 `09893a9` 零 diff（`git diff --stat 09893a9 74384b1 -- <8 条路径>` 为空），`suite_hash` 未变；CI `e2e` job 报 `abfc0cc9c59e`（见 soak-log「CI 运行记录」） |
| R | **红灯必查根因** | 分支存续期间，`baseline_1b` 与 e2e lane（含 CI `e2e` job）**每一次**红都在 §8「红灯记录」追一行：时间、commit、失败用例、根因（产品缺陷 / 测试缺陷 / 环境）、处置 commit。**不允许以「重跑变绿」结案**。表为空或每行根因齐全才算过 | ✅ 表非空、每行根因齐全：§8「红灯记录」5 行（1 条 e2e `baseline_1b` → 009 #72 / 014；4 条范围外的 unit / verify-control 红 → FX37-11 / 12 / 13 / 14），无一以「重跑变绿」结案 |
| 11 | 合入前 CI 全绿 | PR 上 `pull_request` 触发的 `tests.yml`（`unit` ＋ `e2e`）与 `lint.yml` 全绿后才合入（PR 先开，CI 才会跑——不是「CI 绿后开 PR」） | ✅ `b6025ba` 上 `pull_request` 触发的 `tests.yml` run [37635190616](https://github.com/anzchy/reader3-pro/actions/runs/37635190616)（`unit` ＋ `e2e`）与 `lint.yml` run [37635190619](https://github.com/anzchy/reader3-pro/actions/runs/37635190619) 全绿，attempt 1；之后于 2026-10-07T14:44:36Z 合入 |

- 不得设 `TDD_GUARD_BYPASS`。
- `EXPECTED_BASELINE_ITEMS` 不许变——它一变就说明碰了冻结集。
- **012 的门槛 13 / 14 仍归 012**：「018 的路由跨四种存储态」与「012 的写手持 018 的锁」要等 012 的格式与写手存在才能验，本表不收。

---

## 5. 风险

- **删书复活目录**：任何写手在删书之后 `makedirs` 书目录（notes、ai_meta、conversations、vector 今天都会建），删掉的书以残缺形态「回来」。缓解：WI-2 不复活规则 ＋ 每个写手一条并发测试（门槛 7）。
- **锁文件放在书目录里**：`rmtree` 会 unlink 锁文件，随后新建的是新 inode，两个进程各持一把「同名」锁、互斥失效。缓解：锁放书目录之外（WI-2 契约项 1）。
- **与 notes 锁死锁**：书锁与 notes 资源锁若获取顺序不一，可死锁。缓解：固定「书锁 → 资源锁」＋ 交叉获取抛错的测试（WI-2 契约项 2 / 7）。
- **ABA**：等锁期间书被删又被同名重导入，醒来的写手写进新书。缓解：WI-2 契约项 6 身份复核。
- **契约之外的隐患**（写进 ADR-0015 的「不保证」一节，本分支不修）：`FileResponse` 在读完前书被删；ChromaDB 不支持多进程访问，查询不持书锁；对话「both」存储模式是两次发布，需要 revision；`_BOOK_THREAD_LOCKS` 注册表只增不减；ADR-0007 里「跨设备 rename 降级为复制」一句不成立（跨设备 `rename` 直接 `EXDEV` 失败）——012 Q2 的新 ADR 取代 ADR-0007 时一并改。
- **e2e 污染共享语料**：删书测试若动了 `baseline_1b` 用的会话库，会让 soak 在 `master` 上变红（~~清零~~ ⬛ 2026-09-28：终止当时的批次）。缓解：WI-5 的独立库 ＋ 独立服务；不在分组目录放 `conftest.py`（裸 `from conftest import BOOK_ID` 会断）。
- **soak 收集计数**：新 e2e 漏登记分组，合入后下一次 soak 的 deselected 对不上就判 red。缓解：门槛 6。
- **冻结集诱惑**：共享 fixture 想放 `tests/e2e/conftest.py` 或改 `helpers.py`——那两个都在冻结集里。缓解：新 fixture 放 `tests/fixtures/` 下的非冻结模块。
- **把 CI 行当 soak 行**：有人照 #31 行旧措辞「手点 dispatch 补台账行」去 `--append`，一次就按清零规则第 2 条清零（⬛ 2026-09-28：读作让当时的批次判 FAIL）。缓解：WI-7 对账掉旧措辞；WI-8 硬拦截。
- **router 体量**：列表 ＋ 删书 ＋ 导出塞进 `library.py` 会逼近 500 行（⬛ 2026-10-02 D2：不写死当前行数，判据是 `scripts/check_router_size.py`）。缓解：新 router 模块（§6 Q4），012 的 #55 / #57 还要往这里加。
- **#51 的无条件写**：不带 `If-Match` 的旧客户端仍可覆盖（加法式的代价）。缓解：四个写入端都认 `If-Match`，本仓前端全部带上（§6 Q5）。

---

## 6. 开放问题

按「挡住实施的先后」排序：先挡的在上。全部已裁定（2026-09-26）。

裁定来源：Codex（线程 `01a0dc02-d308-78f1-8750-8bcb9dacec06`）与一个独立 Fable 子代理分别裁定，协调者综合，维护者 2026-09-26 确认；Q7 / Q8 / Q12 是维护者本人的取舍。推演依据是 WI-2 所指的原型。

| Q | 问题 | 挡哪个 WI | 裁定 | 状态 |
|---|---|---|---|---|
| Q1 | WI-1 泛化后的台账校验形状 | WI-1 | 正则 `\b(012\|018) debt #(\d+)\b` ＋ 兑付方 slug 解析出的分支号**精确相等** ＋ 无法解析 / 未分配的分支号即红；中文「012 债 #N」只做一次性 grep，不入机器校验。见 WI-1 | ✅ 已裁定 |
| Q2 | 锁文件位置；点目录会不会被枚举误收 | WI-2 | `books/.locks/{book_folder}.lock`，永不 unlink；枚举靠 `_data` 后缀，ADR-0015 写成一处定义。见 WI-2 契约项 1 | ✅ 已裁定 |
| Q3a | 书锁与 notes 锁：合并还是分层 | WI-2 | 分层：书锁 SH / EX ＋ 资源锁，固定顺序书锁 → 资源锁；锁包服务层整次操作（含 CLI `--index`）。见 WI-2 契约项 2 / 3 / 7 | ✅ 已裁定 |
| Q3b | 短写手阻塞等待还是 409 | WI-2 | `LOCK_NB` 轮询，三层共用一个 2 秒总预算，超时 409 ＋ `Retry-After`，不阻塞事件循环。见 WI-2 契约项 4 | ✅ 已裁定 |
| Q4 | 新 router 模块名；是否为 012 预留 | WI-4 | `library_books.py`（列表 ＋ 删书）、`library_export.py`（导出）；不为 012 预留 | ✅ 已裁定 |
| Q5 | #51 revision 的取值、覆盖面、传法 | WI-3 | 原始字节 sha256（实施时取了括注里的可选项：进程私有 key 的 HMAC-SHA256，见 WI-3「实施记录」）；四个写入端都认 `ETag` / `If-Match`；无条件请求放行；全局 `config/.ai_settings.lock`。见 WI-3 | ✅ 已裁定 |
| Q6 | #56 列表字段集 | WI-4 | `book_id`、`title`、`authors`、`cover_url`、`book_uuid`；损坏条目显式错误态；章节数与存储格式留给 012。见 WI-4 | ✅ 已裁定 |
| Q7 | #53 导出 schema | WI-6 | metadata ＋ annotations；对话只在 `?include=conversations`；不含章节正文；整库（维护者取舍）。见 WI-6 | ✅ 已裁定 |
| Q8 | 删书对集合 / 对话的处置；墓碑清理时机 | WI-5 | 集合成员在提交点前移除；对话**删时问**——`delete_conversations` 参数默认 `false`，确认框归 014 WI-16b（维护者取舍）；墓碑在启动与每次删书前清扫，清扫持锁。见 WI-5。⬛ **2026-10-02 维护者裁定 Q-B（执行计划 §6）**，改变「对话保留为孤儿」的实际语义：默认 `per_book` 模式下对话在书目录里，原文照做会随墓碑一起删掉。改为 `false` 时在独占锁内、逐个文件把墓碑里的 `ai_conversations/*.json` 发布到**配置的**项目级对话根（`server._project_conversations_root`）下的 `{book_uuid}/`，目标已有时 `last_updated` 较新者胜，无 uuid 丢弃并记日志，按磁盘上实际有什么决定、不看当前存储模式，由终结器依意图文件执行；项目级写手持共享书锁（[ADR-0018](../../../adr/0018-project-root-conversations-take-book-lock.md)，Proposed）。清扫也在每次导入取锁前跑（D12）。机制见[执行计划 §3 WI-5](../../20261002-018-second-slice-plan.md#3-逐-wi-执行要点) | ✅ 已裁定（2026-10-02 订正） |
| Q9 | CI 运行记录落在哪 | WI-7 | `soak-log.md` 新开「CI 运行记录」一节；本文 §8 只放链接 | ✅ 已裁定 |
| Q10 | `soak_run.py --append` 硬拦截 | WI-8 | 要：`GITHUB_ACTIONS` 或~~非 `master`~~ 即拒绝，独立小 WI。⬛ 2026-09-30 订正：第二条改为「`git merge-base --is-ancestor HEAD origin/master` 不成功即拒绝」——`master` SHA 的 detached worktree 放行、未合入的特性分支 SHA 拒绝；测试须含「detached worktree ＋ `--append` → 放行」。条文见 WI-8 | ✅ 已裁定（2026-09-30 订正） |
| Q11 | ADR-0015 是否过 ADR-0000 准入 | WI-2 收尾 | 过（跨模块、长期、多个写手共同遵守）；契约正文搬进 ADR，合入即 Accepted（门槛 7） | ✅ 已裁定 |
| Q12 | 删后再导入同一 EPUB 算同一本书还是新书（原型暴露：集合按目录名引用会悄悄挂回，对话按 `book_uuid` 引用挂不回，两种引用不一致） | WI-5 | **新书**：什么都不挂回。集合成员在删书时移除（WI-5 第 3 步），对话随新 `book_uuid` 自然不挂回；写手等锁醒来按 `book_uuid` 复核（WI-2 契约项 6）（维护者取舍） | ✅ 已裁定 |


### 6.1 第二段（WI-4 – WI-8）的裁定（⬛ 2026-10-02）

来源与理由的定义处是[执行计划 §6](../../20261002-018-second-slice-plan.md)（Q-A、Q-C – Q-G 由维护者 2026-10-02 按推荐默认裁定；Q-B 写进上表 Q8；Q-H 由协调者 2026-10-02 裁定）。本表只记结论。

| Q | 问题 | 挡哪个 WI | 裁定 | 状态 |
|---|---|---|---|---|
| Q-A | 三条路由的路径 | WI-4 / 5 / 6 | `GET /api/library`；`DELETE /api/library/{book_id}?delete_conversations=false`；`GET /api/library/export?include=conversations` | ✅ 已裁定 |
| Q-B | 默认 `per_book` / `both` 模式下 `delete_conversations=false` 怎么兑现 | WI-5 | 见上表 Q8 的订正 | ✅ 已裁定 |
| Q-C | 封面挑选函数放哪 | WI-4 | `book_store` 里一个独立函数，`library_view` 与新路由共用；**不**放进 `BookMetadataView`（不替 012 扩接缝） | ✅ 已裁定 |
| Q-D | 墓碑名要不要加随机后缀 | WI-5 | 要：`.{folder}.deleted-{pid}-{8hex}`；清扫正则见 WI-5（D10） | ✅ 已裁定 |
| Q-E | 墓碑清扫用哪个持有者类别 | WI-5 | 用现有的 `delete`，不新增类别；是否并进 012 的 `gc` 由 012 定 | ✅ 已裁定 |
| Q-F | `DELETE` 成功返回什么 | WI-5 | 204，无响应体。提交点之后的失败（终结器某步失败）仍回 204，残余交给清扫；客户端重试得 404 即「已删」；提交点之前的失败（409 / 404 / 500）书完好，可原样重试 | ✅ 已裁定 |
| Q-G | 列表遍历时书刚好被删 | WI-4 / WI-6 | 跳过这本书，不报错误态（错误态只留给「目录在、但读不出来」）；WI-6 导出同一条规则 | ✅ 已裁定 |
| Q-H | 删书后保留的孤儿对话要不要 HTTP 入口 | WI-5 | 本段**不加**孤儿对话的 HTTP 路由；孤儿只保证在磁盘 `{配置的根}/{book_uuid}/` 下找得到（现有对话读路由要求活书，对孤儿 404）；需要时另开，属加法式路由 | ✅ 已裁定（2026-10-02 协调者） |

---

## 7. 欠账

本分支新立的欠账（兑付方指向后续分支的）。继承来的欠账不在这里，在 [009 表](./009-e2e-annotations.md#跨波欠账)。

| # | 欠什么 | 欠账方 | 兑付方 | 验收怎么查 | 状态 |
|---|---|---|---|---|---|

### 7.1 审计修复轮（WI-1 / WI-2，审计 `audit-20260930-231519`）

⬛ 2026-10-01。审计对 WI-1 / WI-2 报出 51 条。**修复轮 1** 修了 23 条，逐项提交：`aa83ab8`（#3 #4 #43 #5 #6 #23 #14）、`1c6dae3`（#41 #42 #20 #46）、`f27b8a1`（#44 #45 #48）、`b7a1792`（#1 #2 #47 #49 #9 #10 #11 #15）、`53a280b`（#7）。契约变更已就地订进 WI-2 第 2 / 4 / 5 条。余下 28 条按 `audit-findings-triage` 分拣（先复核、再按「常规使用可达 / 是否证伪本分支主张 / 修法是否碰冻结集」三轴归类），结果如下：**Must 1、Should 6、Could 17、Won't 4**。Must 与 Should 在本分支 CP3 之前修完；Could 与 Won't 不修，理由各一句；没有一条转给 012（如要转，需主控裁定）。

| # | 判定 | 核实 | 一句理由 |
|---|---|---|---|
| 21 | Must | verified | SH 持有者释放时不清类别记录，导致跨进程拒绝报出 `busy:notes`，实际持有者是 reindex（主控复现）；违背 ADR-0015 第 4 条「409 说明持有者类别」。严重度 Low → Medium |
| 8 | Should | verified | N1 每次都等满 1.25 s 会合超时，2 s 预算只剩约 0.7 s，属于容易抖的测试 |
| 12 | Should | plausible | W2-15 要求 3 个败者都精确报 `busy:import`；赢家若在 flock 与写类别之间被抢占，这条就会抖 |
| 13 | Should | verified | 「把活 pid 当租约」的变异仍能过 W2-20；去掉 `_pid_alive` 的变异能活过全部锁测试 |
| 18 | Should | verified | CLI 导入被拒时打出整屏 traceback；`main` 只有 `--index` 分支转成 SystemExit。~~修法：BookLockError / BookGone 都转成一行退出~~ ⬛ 2026-10-01 coordinator ruling: misuse must not be swallowed; BookGone unreachable from process_epub——导入分支只转 `BookLockBusy`，`BookLockMisuse` 带 traceback 传播；测试矩阵 W3-04 的 BookGone 行改为「原样传播」（矩阵在 gitignore 的 tdd-guardian 产物里，不入库） |
| 33 | Should | plausible | W2-03 先起计时器再起等待线程，等待线程调度晚了，0.4 s 下界就会抖 |
| 51 | Should | verified | `books/.locks/` 与锁相关的 409 / 404 都没写进 `storage-and-data-locations.md` / `technical-detail.md`，违反文档更新规则 |
| 16 | Could | verified | 列目录时排除 `.locks`，却没有正向断言其内容；背后没有已知缺陷 |
| 17 | Could | verified | 同 #16，位于 staging 测试 |
| 22 | Could | plausible | `.locks` 里放一个符号链接就能把 `pwrite` 导向别处，但前提是攻击者已经能写 books/，属于加固 |
| 25 | Could | verified | `deadline=` 已在两个写手上有测试，另外三个 notes 写手没测，但背后没有缺陷 |
| 26 | Could | verified | `_AI_META_FILENAME` 常量重复；宽容读取是有意为之 |
| 28 | Could | verified | `DEBT_RE` 只在人为构造的输入下漏匹配，属于扫描精度问题 |
| 29 | Could | verified | `STRIKE_RE` 不跳过代码片段，同样只在人为构造的输入下出现 |
| 30 | Could | verified | `assert locks.is_dir()` 把实现顺序钉死了，无缺陷 |
| 31 | Could | plausible | 共享工厂里的 makedirs 遮住了「书不存在」这个前提，没有实际损失 |
| 32 | Could | verified | 计数断言可以去重；合成集合 007…020 是有意保留的 |
| 34 | Could | verified | `Holder.start()` 失败时不回收子进程；子进程是 daemon，书目录每个测试独立 |
| 35 | Could | verified | 多处测试辅助函数重复 |
| 36 | Could | verified | 文档串少说了被 patch 的对象 |
| 37 | Could | verified | 测试文件引用的矩阵文件没有入库 |
| 39 | Could | verified | `process_epub_run` 只是一个别名 |
| 40 | Could | verified | `_exc_name` 与 `_raised` 功能重叠 |
| 50 | Could | verified | finally 只发 go 信号，失败时不回收子进程；daemon 加 go 信号，不会挂住 |
| 19 | Won't | false | HEAD 已由 `1c6dae3` 解决（第一层轮询移进 `acquire` 外层 try，由 `registered` 守卫） |
| 24 | Won't | false | HEAD 已由 `aa83ab8` 解决（notes 改走 `resource_lock`，`_wait_or_refuse` 已删） |
| 27 | Won't | disputed | 有意为之：`index_book` 文档串说明用属性传参，以免拓宽调用形状 |
| 38 | Won't | false | HEAD 已由 `aa83ab8` 解决（`scan` 改用 `SHORT_BUDGET_S`，`test_fx_2_12` 钉住耗时） |

本节所有 SHA 都是 2026-10-01 变基到 `master` `f621175` 之后的值（修复轮 1 原记的 `d9c37c7` 等是更早一次变基前的值，已同步改写）。

**修复轮 2**（⬛ 2026-10-01，Must 1 ＋ Should 6，逐项提交，经 `/tdd-guardian:workflow`）：`3a33a5f`（#21，共享持有者释放时比较并清除自己的类别记录）、`6a71222`（#13，W2-20 改用存活 pid ＋ `_parse_category` 参数化表；去掉 `_pid_alive` 的变异 5 条失败）、`22c5b3f`（#18）、`aadc99a`（#51）、`fc40e15`（#8，`RENDEZVOUS_TIMEOUT_S = BUDGET_S * 0.5` ＋ 余量守卫）、`574b3ab`（#12）、`adfbcd9`（#33，W2-03 改断言「获取 ≥ 释放开始」）。7 条全部结清。

**修复轮 3**（⬛ 2026-10-01，tdd-guardian 终审 APPROVED WITH NOTES 的四条注记，经主控裁决后逐条提交）：
- `2227e80` 裁决 a：导入分支 except 收窄为 `BookLockBusy`（#18 的修法见上表订正）；`--index` 分支的 except 是本分支 WI-2 加的，同样收窄，只留可达的 Busy / Changed / Gone，`BookLockMisuse` 两条分支都带 traceback 传播。
- `97083c3` 裁决 b：W2-20 加「他人活 pid」（`os.getppid()`）一行；豁免自身 pid 的租约变体只在这一行失败。
- `daddca5` 裁决 c：`book_lock` 文档串与 `storage-and-data-locations.md` 写明类别记录的两条真实限制（SIGKILL 后 pid 复用；共享持有者存活时也可能报 `unknown`），Busy 行写明 EX 立即拒绝。
- `9d2dd95` 裁决 d：ADR-0015 第 4 条补一句「类别可能报 `unknown` 及原因」，状态仍为 Proposed。

---

## 8. 合入记录

~~_未合入。合入后本节是「018 是否在主干上」的唯一定义处，格式照 [011 §8 合入记录](./011-backend-refactor.md)。_~~

### ✅ 合入记录：第一段（WI-1 – WI-3）（本文是这条事实的唯一定义处）

⬛ 2026-10-02 回写。**018 的 WI-1 – WI-3 已于 2026-10-01 合入 `master`；WI-4 – WI-8 不在这次合入里~~，018 尚未关闭~~。** 别处提到「018 是否在主干上」一律链回本节。⬛ 2026-10-07：WI-4 – WI-8 已随第二段合入，018 关闭，见下方「第二段」。

| 事实 | 值 | 复核命令 |
|---|---|---|
| PR | [#33](https://github.com/anzchy/reader3-pro/pull/33)，25 commits；标题「018: 书库路由 WI-1–WI-3——每书写锁（ADR-0015）、设置版本校验（#51）与审计修复三轮」 | `gh pr view 33` |
| 合并 commit | `c08317b`（2026-10-01 22:43 +0800，`Merge pull request #33 from anzchy/018-library-routes`），第一父 `f621175` | `git log -1 c08317b` |
| 合并前最后一个 commit | `42c0728`（§7.1 修复轮 2 / 3 记录）；分支领先量 0 | `git rev-list --count master..018-library-routes` |
| 交付 | WI-1（兑付方改写，`865d068`）；WI-2（每书写锁 `book_lock`，`48bdfa4`，及 §7.1 三轮审计修复）；WI-3（#51 设置写入版本校验，`2d5f96f`） | `git log c08317b^1..c08317b^2 --oneline` |
| 未交付 | ~~WI-4（#56 列表路由）、WI-5（#58 删书）、WI-6（#53 导出）、WI-7（#31 收尾对账）、WI-8（`--append` 硬拦截）——`src/` 里没有对应路由，`routes.snapshot` 无新增，`scripts/soak_run.py` 无 `GITHUB_ACTIONS` / `is-ancestor` 判据~~ ⬛ 2026-10-07：**已全部交付**，随第二段 PR #37 合入（`74384b1`），见下方「第二段」 | `grep -n "@router" src/reader3_app/web/routers/library_books.py src/reader3_app/web/routers/library_export.py` |
| 本地 lane（在 `42c0728` 上，PR 正文，协调者独立复跑） | unit ＋ contract 3107 passed / 2 skipped / 1 xfailed；fe 279；e2e 254 passed / 16 skipped；packaging 11 | — |
| CI（PR 上） | 全绿：tests run `36854855076`、lint run `36854855032` | `gh pr checks 33` |
| 冻结集 | 8 条路径零改动，`suite_hash` 不变（PR 正文） | — |
| ADR-0015 | 门槛 7 要求「合入同一 PR 里转 Accepted」——PR #33 合入时仍是 Proposed；2026-10-02 由合入回写转 Accepted（锁契约已在 `master` 上，删书接入随 WI-5） | `sed -n 5p docs/adr/0015-per-book-write-coordination.md` |

### ✅ 合入记录：第二段（WI-4 – WI-8）（本文是这条事实的唯一定义处）

⬛ 2026-10-07 回写。**018 的 WI-4 – WI-8 已于 2026-10-07 合入 `master`，018 关闭。** 执行计划见 [`20261002-018-second-slice-plan.md`](../../20261002-018-second-slice-plan.md)。

| 事实 | 值 | 复核命令 |
|---|---|---|
| PR | [#37](https://github.com/anzchy/reader3-pro/pull/37)，30 commits；标题「018: 书库路由第二段 WI-4 – WI-8——列表 / 删书 / 导出 / --append 硬拦截（债 #56 / #58 / #53）」 | `gh pr view 37` |
| 合并 commit | `74384b1`（2026-10-07T14:44:36Z，`Merge pull request #37 from anzchy/018-library-routes`），第一父 `09893a9`，第二父 `b6025ba`；与 `b6025ba` 同树 `df20cf4` | `git cat-file -p 74384b1` |
| 合并前最后一个 commit（冻结的 PR 头 `H`） | `b6025ba`——把 master（`02be7c3` / `09893a9`）并入分支，解决 009 欠账撞号：master 的 #71 保留，本分支立的两条改为 #72 / #73；合入用 `--match-head-commit` | `git rev-list --count 74384b1^1..74384b1^2`（30） |
| 交付 | WI-8（`--append` 硬拦截，`e9cb422`）；WI-4（#56 `GET /api/library`，`95eb94e`）；WI-5（#58 删书：5a 服务层 `e2497fc`、5b 写入方 `dc7dd27`、5c 路由 `642bbc5`、CP2 修订 `31527de`；ADR-0018 转 Accepted `82285b3`）；WI-6（#53 `GET /api/library/export` ＋ 设置页按钮，`2066f29`）；WI-7（#31 CI 收尾核验，本表 CI 行）；审计修复 FX37-1 – FX37-14（`8dcfcda` / `d35b68b` / `d6c6a1c` / `bb57f6b` / `409a6fc` / `f136871` / `62fd299` / `8833ba2` / `ab242c5` / `19faeef` / `58b985f` / `802c026` / `ef05f8e` ＋ `97ce374` / `aeba027`） | `git log 74384b1^1..74384b1^2 --oneline` |
| 欠账 | 结清 009 #53 / #56 / #58（#31 补 CI 链接）；立 009 #72（程序化选区清空 `editingNoteId`，兑付方 014）、#73（孤儿对话 HTTP 不可达） | [009 欠账表](./009-e2e-annotations.md#跨波欠账) |
| 本地 push 闸（在 `b6025ba` 上，协调者） | unit 4025 passed / 3 skipped / 1 xfailed，覆盖率 lines 90.1% / branches 79.1%，276s；verify-control 390 passed，144s；fe-unit 298 passed；packaging 11 passed；e2e 254 passed / 16 skipped，160s | — |
| CI（`H` = `b6025ba`，全部 attempt 1、全绿） | `pull_request` tests run [37635190616](https://github.com/anzchy/reader3-pro/actions/runs/37635190616)（GitHub 合成合并 ref `6c9dcb5`，`headSha` `b6025ba`）；`workflow_dispatch` tests run [37635220594](https://github.com/anzchy/reader3-pro/actions/runs/37635220594)（门槛 9）；lint run [37635190619](https://github.com/anzchy/reader3-pro/actions/runs/37635190619)。浏览器、`suite_hash`、条数与耗时只记在 [soak-log「CI 运行记录」](./soak-log.md#ci-运行记录) | `gh run view 37635220594 --json headSha,attempt,conclusion` |
| 冻结集 | 8 条路径对 master 零改动，`suite_hash` 不变（`abfc0cc9c59e`） | `git diff --stat 09893a9 74384b1 -- <8 条路径>` |
| 路由 | `routes.snapshot` 只增 3 行（ADR-0011 加法式） | `git diff c08317b 74384b1 -- tests/contract/routes.snapshot` |
| 运行中验证 | verify-reader3 沙箱活体 F-035（删书 API）与 F-036（导出）均 PASS：`.claude/verify-evidence/20261007-104216-F-035`、`.claude/verify-evidence/20261007-104034-F-036`（证据目录不入库，本地留存）；台账两行随本回写转 `accepted` | — |
| ADR | ADR-0018 在 PR 内转 Accepted；ADR-0015 只改 compliance / Confirmation 记账（本回写），compliance 口径见 §4 门槛 7 注 | — |
| 红灯 | 分支存续期间 5 条，见下方「红灯记录」 | — |

### 红灯记录（门槛 R）

分支存续期间 `baseline_1b` / e2e lane / CI `e2e` job 的每一次红追一行。「重跑变绿」不是根因。

| 时间（UTC） | commit | 失败用例 | 根因类别 | 根因 | 处置 commit |
|---|---|---|---|---|---|
| 2026-10-07T06:04:15Z | `82285b3`（CI run 37579313674，`e2e baseline_1b` job，attempt 1） | `tests/e2e/baseline_1b/test_conflict_resolution_single_flight.py::test_保留我的还在飞时两个出口都不可点`（`open_conflict`：`rd-conflict-dialog` 未出现；本批首条用例） | 产品缺陷（时序暴露；非 018 引入） | 点已有 mark 打开笔记编辑器后，`onAnnotationClick` 的程序化选区经 epub.js 250ms 去抖回发 rendition `"selected"` → `handleRenditionSelection` → `handleSelectionRange` 把 `editingNoteId` 置 null（`annotations.js:997`）；保存于是走新建分支（POST 而非 PUT），`pin_if_match` 未被消费、不 409，编辑器关闭、对话框不出现。平时被加载期第二次 `loadAndRender` 重绘塌掉选区而掩盖；CI 冷启动首条用例里重绘不落在点击后 250ms 内、且点击 → 保存 >250ms 时必现。本地加延时 100% 复现（POST 409 → POST 201，pin armed、`sawClientEtag=null`）。PR #37 未触及 `annotations.js` / notes 路由；`2066f29`（与 `82285b3` 仅文档差异）在 CI run 37578140282 同码绿 | 009 欠账 #72 立账（原拟 #71，与 master 02be7c3 的 #71 撞号，合并 master 时改号），兑付方 014（维护者 2026-10-07 裁定）；冻结集不改 |
| 2026-10-07（门槛 R 范围外：unit lane，同标准记录） | `6e9761c`（CI run 37592235760，`静态检查 ＋ unit lane` job） | `tests/unit/test_event_loop_not_blocked.py::test_T2h_书籍分词进行中_health_仍然应答`（`snapshot_at_unblock == [[]]`；`order[0] == "health"` 已过） | 测试缺陷（非 018 引入，d65a536 起即有） | `Env.blocking` 先 `time.sleep(BLOCK_S=0.2)` 再拍 `order` 快照，快照断言实为隐藏的 200ms 墙钟期限（与文件自己「`BLOCK_S` 不参与任何断言」的注释相悖）；CI runner ≥~200ms 停顿即红。事件循环未被挡住（`chat.py:423` 经 `run_in_threadpool`；018 未改该路径）。本地 0/40，CI 约 1/30 | `ef05f8e`（FX37-13：快照改由 health 完成事件触发、`START_WAIT_S` 封顶；注入 0.3s 停顿旧版 21/26 红、新版全绿；去掉 threadpool 的变异仍红）＋ `97ce374`（`_package_version` 缓存） |
| 2026-10-07（门槛 R 范围外：unit lane，同标准记录） | `634e4e2`（CI run 37608731905，`静态检查 ＋ unit lane` job） | `tests/unit/test_library_delete_crash.py::test_cr1_sigkill_at_every_step_then_sweep_converges[false-rmtree_done]` / `[false-intent_removed]` / `[true-committed]`（崩溃子进程 `BookLockBusy: book busy: unknown`） | **产品缺陷（018 WI-5a e2497fc 引入，违反 W5-19）** | `delete_book` 与 `sweep` 以 `SHORT_BUDGET_S`（50ms）取**独占**锁（`library_delete.py:709` / `:651`；调用方 `server.py:378`、`reader3.py:760`）；`book_lock.acquire` 在 `:344` 定期限后 makedirs / open / flock，`:382-386`「迟到的成功按失败拒」——锁是空闲的，但获取耗时 ≥50ms 就报忙。负载下用户删书可得假 409、清扫把空闲文件夹报 busy 留下墓碑。CI 4 vCPU 同时起 22 个子进程，3 个超时；注入 60ms 停顿 100% 复现 | `58b985f`（FX37-11：独占锁一律默认预算，`sweep` 去掉 `budget` 参数；被占的锁仍立即拒、清扫仍不轮询；6 条新测试） |
| 2026-10-07（门槛 R 范围外：verify-control lane，同标准记录） | `3dc7629`（CI run 37610056856，`verify-control lane` job；同 SHA 的 dispatch run 37610063713 该 job 绿） | `tests/unit/test_verify_control_ai.py::test_wi3_c29_concurrency_really_is_n[8]`（`TypeError: '<' not supported between 'NoneType' and 'float'`） | 测试缺陷（025 `1e86c5c` 引入，经 `55da172` 合入；非 018） | 假 SSE 服务端 `end()` 先写分块终止符、`finally` 才记 `t_end`（`tests/unit/verify_control_fakes_sse.py`）；客户端见 EOF 即退出，测试读 `requests.jsonl` 时最后一条的 `t_end` 可能仍为 None。`control.py` 行为正确。注入 1s 延迟 [3]/[4]/[8] 必红 | `802c026`（FX37-12：终止符之前先在锁内记 `t_end` 并落盘） |
| 2026-10-07（门槛 R 范围外：verify-control lane，同标准记录） | `6ecf3e3`（dispatch run 37621396898，`verify-control lane` job；同 SHA 的 PR run 37621381040 该 job 绿） | `tests/unit/test_verify_control_instance.py::test_c66_real_reader3_and_server_lifecycle`（`down` 返回 `ok:true`、`signal:'TERM'`、`killed:False`） | **产品缺陷（verify-reader3 控制 CLI；025 `1e86c5c` 引入，经 `55da172` 合入；非 018）** | `procs.alive` 先 `os.kill(pid, 0)` 再 `ps -o stat=`；两步之间孤儿僵尸被收割时 `ps` 非零退出，`_ps_field` 回 None，`not "".startswith("Z")` 判为存活（`procs.py:191`）。`cmd_down` 在 `terminate` 已见死亡（故 `signal` 为 TERM）后又单独复探一次，落进该窗口即报 `killed:False`。reader3 服务端未提前退出。确定性注入（`_ps_field` 前先收割）必红；随机 0–10ms 收割 96/300；macOS 上 c66 0/30（launchd 即刻收割） | `aeba027`（FX37-14：`ps` 查不到时复探 `os.kill`；`terminate` 返回 `(signal, 已见死亡)`，`killed` / `stub_killed` 取自该观察不再复探；`test_verify_control_core.py` 两条新测试先红后绿） |
