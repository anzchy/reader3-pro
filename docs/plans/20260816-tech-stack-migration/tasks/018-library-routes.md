# 018-library-routes —— 任务

- **状态**: 🚧 **进行中，首段已合入**（⬛ 2026-10-02 回写：WI-1 – WI-3 随 PR #33 于 2026-10-01 合入 `master`，合并 commit `c08317b`，见 §8；**WI-4 – WI-8 未做**，PR 正文明写「WI-4 – WI-8 不在本 PR」。§4 出口闸按整个分支计，尚未全部满足）。~~🚧 **进行中**~~（⬛ 2026-09-30 分支从 `master` 开出，与 `019` 并行，先做 WI-1 / WI-2，调度见[进度盘「现在该做什么」第 2 步](../../20260824-frontend-backend-plan-progress.md#现在该做什么)）。~~评审通过、待开工~~（任务书 2026-09-26 评审通过，§6 Q1–Q12 全部裁定）。~~分支**未开**，没有一项已实施。~~2026-09-28 批次规则取消 soak 等待期后，本分支是挡在 012 前面的关键路径（顺序见 [进度盘 §2](../../20260824-frontend-backend-plan-progress.md)；⬛ 2026-09-30：排在冻结集欠账窗口之后开工，WI-8 规则同日订正，见 §6 Q10）
- **对应阶段**: M4a-债（013 延后到后端的欠账兑付之一部分，[§9 编号表](../plan-tech-stack-migration.md)）。不是新里程碑，与 016 / 017 同类
- **计划文件夹**: [`20260816-tech-stack-migration/`](../plan-tech-stack-migration.md)（归属 **A**）
- **上游**: `013`（✅ 已合入）、`017`（✅ 已合入）；从 `master` 开
- **下游**: `012-storage-format` 在本分支之上开工（WI-6 / WI-7 / WI-12 / WI-13 持本分支的锁，WI-5 / WI-10 建在本分支的列表路由上）；014 WI-16b 里等 #56 / #58 的各项等本分支。顺序的定义处是 [进度盘 §2](../../20260824-frontend-backend-plan-progress.md)
- **节奏**: WI 严格按号串行；WI-1 是**单个 commit**；路由新增与 `routes.snapshot` 同 commit

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
- **契约**（§6 Q2 / Q3 / Q12 已裁定，2026-09-26）。[ADR-0015](../../../adr/0015-per-book-write-coordination.md) 已按本段成稿（Proposed）；Proposed 期间**本段是定义处**，改契约先改这里再同步 ADR；ADR 转 Accepted 的那个 commit 把本段换成一行链接:
  1. **锁文件位置**：`books/.locks/{book_folder}.lock`，在书目录**之外**，**建了就永不 unlink**（在线删锁文件本身就重新引入 inode 分裂；`.locks/` 累积是设计，回收只许停机时做）。理由：锁在书目录里时，删书的 `rmtree` 把它 unlink，随后 `makedirs` 建出新 inode——两个进程各持一把「同名」独占锁；首次导入时还得先建出空书目录，整个构建期书库里有坏条目，被杀即永久留下（原型「Q2 锁在目录里」「首次导入·锁在目录里」两剧本）。书库枚举不收它，靠的是**只收 `_data` 后缀**（`search_service.py`、`routers/library.py`、`ai/books.py` 三处），不是「点目录隐藏」——这条枚举规则 ADR-0015 里写成一处定义
  2. **分层，不合并**：书锁有**共享 / 独占**两种模式（`LOCK_SH` / `LOCK_EX`）。改目录结构的写手（import / delete / migrate / 上传 / 墓碑清扫）持**独占**；只写自己那份文件的写手（notes / reindex / ai_meta / conversations）持**共享**，再取各自的**资源锁**。**固定顺序：书锁 → 资源锁**，反序即 AB-BA 死锁（原型「Q3 反例」）。~~`notes.json.lock` 等资源锁可留在书目录内——共享持有者在时没人能 `rmtree` 它。~~ ⬛ 2026-10-01 订正（审计 #3 / #4 / #43 修复轮）：reindex / ai_meta / conversations 的资源锁在 `books/.locks/{resource}/{book_folder}.lock`（书目录之外、建了永不 unlink、不在书目录里建任何东西），统一由 `book_lock.resource_lock` 实现，与书锁共用同一个截止时间；**notes 例外，保留书目录内的 `notes.json.lock`**——共享持有者在时没人能 `rmtree` 它，挪位置只改语义不得收益。合并成一把独占锁被否决：重建（分钟级）期间每次划线要么挂起、要么 409（原型「Q3 合并」两剧本）
  3. **锁包住服务层整次操作**，不是只包 HTTP handler——CLI `reader3 --index`（`reader3.py` 的 `--index` 分支）与路由走同一把锁
  4. **拒绝语义**：独占写手**非阻塞**获取，拿不到 → HTTP **409** / CLI 非零退出码并说明持有者类别。共享写手**限时等待**：`flock` 阻塞模式没有超时，所以用 `LOCK_NB` 轮询，**一个 2 秒总预算**（`time.monotonic` 截止时刻）覆盖进程内层、书锁、资源锁三层，不许逐层重新计时；超时 → 409 ＋ `Retry-After`，前端保留未保存的内容；等待不得阻塞事件循环。⬛ 2026-10-01 订正（审计 #42 / #20 修复轮）：**截止规则**——一层只在成功那一刻 `now < deadline` 才算拿到；在截止时刻或之后才拿到的那一层被释放并拒绝（已拿到的各层一并释放），截止时刻已到的请求一层都不尝试；持有者类别的读取记在同一个截止时间上（等空记录的窗口为 `min(0.1 s, 剩余时间)`），拒绝不晚于截止时刻。只想「不等」的调用方（页面渲染与启动扫描解析 uuid）传预算 `SHORT_BUDGET_S`（= 一个轮询间隔），由 `acquire` 在真正取锁时起算
  5. **不复活**：持锁后、写之前，**在锁内**复核书目录存在（`_validate_book_id` 枚举到取锁之间有窗口）；除 import 外任何写手**不得** `makedirs` 书目录本身——`notes_service._book_write_lock` 与 `save_annotations` 里的 `makedirs`、`vector_search._client_and_collection` 在**读路径**上的 `makedirs` 都要改成「断言父目录存在」。⬛ 2026-10-01 订正（审计 #44 / #45 / #48 修复轮）：只断言不够——`PersistentClient(path)` 会把消失的 `chroma_db` 连同书目录一起建回来，无锁的「先查后开」有窗口。读路径改为：无锁预检（没有 `chroma_db` → 未索引，不取锁）→ 以持有者类别 `search` 短预算（`SHORT_BUDGET_S`）取**共享**书锁 → 锁内复核 `chroma_db` → 打开并 `get_collection` → 放锁，查询本身不持锁；取锁拿不到（独占的 import / delete 在进行）按「未索引」处理；只有 chromadb 的集合不存在（1.3.x 为 `NotFoundError`）映射为「未索引」，其余错误原样抛出。`search` 进入持有者类别封闭列表（`book_lock.CATEGORIES`）
  6. **身份复核（防 ABA）**：共享写手在请求开始时记下书的 `book_uuid`，拿到锁后复核；不一致 → 409（书已换代——同名的书存在，但不是请求开始时那一本，所以不是 404）。只查存在性挡不住「等锁期间书被删、同一 EPUB 又被导入」——醒来的笔记请求会写进新书（Codex 在原型上复现）
  7. **进程内层**：不能照搬 notes 的整段 `threading.Lock`（会把共享持有者串行化）——要真正的读写语义；同一调用栈重复取书锁 → 抛错（thread-local 检测）；**禁止共享→独占升级**（`flock` 的模式转换是先放再取，中间可被插入），写手开工前定死模式；不许用 dup / 继承的 fd 冒充线程互斥（`flock` 按 open file description 计）
  8. **崩溃**：`flock` 随进程死亡释放；锁文件残留不等于被持有
  9. **适用范围**：单进程 uvicorn（`server.py` 入口）＋ 本地 POSIX 文件系统。多 worker 下进程内缓存（`_stats_cache`、`BookUuidResolver`、`_BOOK_THREAD_LOCKS`）只清得到一个 worker；NFS / SMB 上 `flock` 无保证——都写进 ADR-0015 的「不保证」一节
- **原型**：`018-lock-protocol.PROTOTYPE.html`（纯 JS 状态模型 ＋ 剧本），存于一次性分支 `prototype/018-book-lock`，不进 `master`。它是裁定的推演依据，不是规格——规格以本段为准
- **涉及文件**: 新模块 `src/reader3_app/book_lock.py`、`notes_service.py`、`ai/books.py`、`ai/conversations.py`、`vector_search.py`、`web/routers/search.py`（`api_index_book` 持锁）、`reader3.py`（`process_epub` 持锁）；[`docs/adr/0015-per-book-write-coordination.md`](../../../adr/0015-per-book-write-coordination.md)（Proposed，已成稿）
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
- **ADR-0015**：已过 [ADR-0000](../../../adr/0000-use-adrs.md) 准入（§6 Q11），Proposed 稿已成。实现若推翻契约某项，先改本段再同步 ADR。ADR-0001 的 Revisit When（`_book_write_lock` 多进程）即此次重访。**本分支合入时 ADR 转 Accepted、本段换链接**（门槛 7）

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
- **建在接缝上**: 数据只取自 `book_store.load_book_metadata()`（今天是全量读后投影出 `book_id` / `title` / `authors`）。012 WI-5 换它的函数体、012 WI-10 在每项上加 `storage_format`——本路由不得绕过接缝直读 `book.pkl`，否则 012 换实现时它不跟着变
- **字段集**（§6 Q6）: `book_id`、`title`、`authors`、`cover_url`、`book_uuid`。`cover_url` 是 URL 不是字节，`book_uuid` 取自 `ai_meta.json`（读不出 → `null`，按 ADR-0003 不覆写）。`chapter_count`、`storage_format` 留给 012——**不在本 WI 为此扩接缝**，扩了就是替 012 定格式。损坏条目给**显式错误态**（`{"book_id": ..., "error": "unreadable"}` 一类），不静默跳过、不让整张列表 500
- **涉及文件**: 新 router 模块 `web/routers/library_books.py`（列表 ＋ 删书；§6 Q4；`library.py` 已 333 行）、`web/server.py`（`include_router`）、`tests/contract/routes.snapshot`、`tests/unit/test_book_store_metadata_seam.py`。**不为 012 的 #55 / #57 预留位置**——它们到时自己按体量选模块
- **接缝守卫测试**: `test_no_production_call_site_uses_the_new_seam_yet` 有两条断言——(a)「只有 `book_store.py` 提到 `load_book_metadata`」本 WI 起**必然**不成立，改写为「调用方白名单 = {本路由模块}」；(b)「`library_view` 仍 `load_book_cached(item)`」**保留**，它是 012 WI-5 的活
- **验收补充（种子）**: 一本 `book.pkl` 损坏的书不让整张列表 500，它以显式错误态出现在列表里（契约测试写死形状）；返回顺序确定；墓碑目录与 `.locks/` 不出现在列表里
- 测试矩阵：待 /tdd-guardian:design-tests

### WI-5: 欠账 #58 —— 删书路由（WI-2 之后）

- **目标 / 验收**: 见 [#58 行](./009-e2e-annotations.md#跨波欠账)（删后读与 `POST /api/index` 都 404；FB-L18 可测）
- **#58 行里有一句已过期**：它要求「失效 `load_book_cached` 的 lru_cache」。011 之后 `load_book_cached` 以 `(st_mtime_ns, st_size)` 为 key、每次调用先 `os.stat`，删掉的书不会从缓存里被读出来。**真正要处理的是别处**：`server._stats_cache`（5 秒 TTL 的书库统计）、搜索索引缓存、会复活目录的写手（WI-2 不复活规则）
- **边界**（沿 [ADR-0012](../../../adr/0012-security-boundaries.md) 的思路；ADR-0012 **不**定义大小上限与 409，那些由本 WI 自定）:
  - `book_id` 过 `safe_book_folder` ＋ `_validate_book_id`（枚举目录成员）
  - **删除顺序**（§6 Q8 已裁定）:
    1. 非阻塞取该书**独占**锁；拿不到 → 409
    2. **锁内**复核书目录存在；不存在 → 404
    3. 在全局集合锁下把该书从 `library_collections.json` 的所有集合里移除（集合锁即 [009 #60](./009-e2e-annotations.md#跨波欠账) 已合入的那把：`library_collections.json.lock`）
    4. 书目录**原子改名**为墓碑 `books/.{book_folder}.deleted-{pid}/`，`fsync` 父目录——**这是提交点**：之前崩溃，书完好；之后崩溃，书已不在库里
    5. 失效三处进程内缓存：`server._stats_cache`、搜索索引缓存、`ai/books.py` 的 `BookUuidResolver` 映射（[009 #61](./009-e2e-annotations.md#跨波欠账) 已让它命中时查盘，但删书仍主动失效，免得多一次扫描）
    6. 仅当请求带 `delete_conversations=true`（默认 `false`）才删该书按 `book_uuid` 存的对话；否则对话保留为孤儿。确认对话框问用户——归 014 WI-16b
    7. `rmtree` 墓碑
    8. 放锁
  - **墓碑清扫**：服务启动时、以及每次删书开始前扫 `books/.*.deleted-*/`；对每个墓碑**取得并持有**对应书的独占锁再 `rmtree`，拿不到就跳过（「探测后即释放」再删是错的——探测与删除之间别人可以拿到锁，Codex 在原型上复现）。读侧照旧按 `_data` 后缀过滤，所以没清掉的墓碑只占空间，不出现在书库里
  - 第 3 步落在提交点之前，崩在 3 与 4 之间 → 书还在、集合里没了它：可接受（用户可重加），反过来（书没了、集合里还挂着）才是读侧必须容忍的情形——集合读取跳过不存在的 `book_folder`
  - **删后再导入同一 EPUB = 新书**（§6 Q12）：新 `book_uuid`，旧对话不重新挂上，集合成员不恢复（第 3 步已移除）
  - **409**：该书的锁被他人持有（导入 / 重建 / 迁移 / 上传进行中）。**404**：书不存在
- **涉及文件**: `web/routers/library_books.py`、`web/server.py`（`_stats_cache`）、`search_service.py`、`ai/books.py`（`BookUuidResolver`）、`collections_service.py`、`ai/conversations.py`、WI-2 的锁模块、`tests/contract/routes.snapshot`
- **e2e**: 删书测试**不得**改动 `baseline_1b` 共用的会话语料库——用自己的库目录与自己起的服务（`tests/fixtures/deg_assertions.py` 的起服务形状），不在任何分组目录里放 `conftest.py`
- **验收补充（种子）**: 删书与单本重建并发 → 一方 409，且不出现「删掉的目录被重建出来」；删后 `/api/library/stats` 立即反映；删后该书不再出现在 WI-4 的列表里、不在任何集合里；`delete_conversations` 缺省时对话文件原样保留，为 `true` 时删掉；删后重导入同一 EPUB 得到新 `book_uuid`；在提交点前后各注入一次 `SIGKILL`，重启后书库分别是「书完好」与「书不在、墓碑被清扫」
- 测试矩阵：待 /tdd-guardian:design-tests

### WI-6: 欠账 #53 —— 书库导出

- **目标 / 验收**: 见 [#53 行](./009-e2e-annotations.md#跨波欠账)（路由进快照；非空合法 JSON；FB-S06 半边）
- **schema**（§6 Q7 已裁定）: 每本书导出 **metadata**（WI-4 的字段集）＋ **annotations**（`notes.json` 的内容）；**对话只在 `?include=conversations` 时带**；**不导出章节正文**（EPUB 本身才是正文的来源，导出不是备份）。整库导出；单本导出不在本 WI
- **模块**: 新 router `web/routers/library_export.py`（§6 Q4）
- **与存储格式无关**: 导出只经 `book_store` 读，所以 012 换格式后本路由不改；012 门槛 13 验的正是「导出不把 `corrupt` 当 `valid`」。#53 兑付方列原写的「内容依赖 012 存储格式」由 WI-1 改掉
- **边界**: 整库导出可能很大——流式还是一次成型、有无大小上限、临时文件是否 `mkstemp`，本 WI 自定（ADR-0012 没有现成规则）
- **涉及文件**: `web/routers/library_export.py`、`web/server.py`（`include_router`）、`frontend/src/settings/index.ts`（`wireExport` 的 `set-export-json`）、`tests/contract/routes.snapshot`
- **验收补充（种子）**: 缺省请求的输出里没有对话、没有章节正文；`?include=conversations` 时带；损坏的书以 WI-4 的错误态出现，不让整次导出失败
- 测试矩阵：待 /tdd-guardian:design-tests

### WI-7: 欠账 #31 —— CI e2e job 收尾对账（最后做）

- **先说清楚这条账的现状**：#31 **已于 2026-09-20 结清**（[#31 行](./009-e2e-annotations.md#跨波欠账) 状态列）。`tests.yml` 的 `e2e` job 已存在（干净 ubuntu、`uv sync --frozen`、记 Chromium 版本、`soak_run.py --log-dir soak-ci-logs` 要 68/68、再跑 `-m "not baseline_1b"`）；机制挑战闸第 1 项已在它上面 PASS（[`soak-log.md` 机制挑战闸执行记录](./soak-log.md)，run 35584711194）。**本 WI 不建 job**
- **「补 soak 的环境多样性那一半」这个说法不成立**：CI 的运行**不进 soak 台账**，这是写定的——
  - `tests.yml` 的 `e2e` job 头注释：结果记进机制挑战闸表，「不往 soak 台账追行」，「不传 `--append`」
  - [§7 清零规则](../plan-tech-stack-migration.md) 第 2 条：`browser` 或 `os` 变了就清零。CI 行的 `os` 是 `linux-*`、本地是 `darwin-*`，混进去每换一次就清零一次（⬛ 2026-09-28 批次规则 3：读作「就不是同一批」——一行 linux 混进批次窗口，该批判 FAIL）
  - 所以「环境多样性」由 CI job 以**独立信号**的形式提供（每次跑都是一次干净 Linux 的 68/68 首次通过核验），不是填台账的行
- **目标**:
  1. **对账**：修掉仍把 #31 写成「没建」「待定」的地方——009 #31 行兑付方列（WI-1 已改）、§7「该补偿至今没有建出来」一段（**§7 不归本文改**，见本 WI 末尾）、`tests.yml` 的 `e2e` job 头注释里「一个触发器都不新增」「日常 commit 与 PR 一律不跑」两句（2026-09-23 已加 `pull_request → master`，文件头注释已更新，job 注释没跟上；`.github/workflows/` 不在冻结集）
  2. **核验**：在本分支的**合并头**上手点一次 `gh workflow run tests.yml --ref <合并头所在 ref>`，`e2e` job 绿且 `attempt=1`；本分支 PR 上 `pull_request` 触发的那一次同样要绿（门槛 R 适用）
  3. **记录**：两次运行的 run id、commit、Chromium 版本记进 `soak-log.md` 新开的「CI 运行记录」一节（§6 Q9；**不是** soak 台账），本文 §8 只放链接
- **不做**: 不改 `tests.yml` 的触发器与步骤；`soak_run.py` 的硬拦截是 WI-8，不在本 WI
- **§7 / §9 的措辞归协调者改**：本 WI 只列需改之处，不动 `plan-tech-stack-migration.md`

### WI-8: `soak_run.py --append` 硬拦截

- **目标**: 把「soak 台账只收 `master` 上、工作站上的行」从流程约束变成机器拦截（§6 Q10）。`--append` 时：环境变量 `GITHUB_ACTIONS` 存在 → 拒绝；~~当前分支不是 `master` → 拒绝~~；都以非零退出码并说明原因。不带 `--append` 的核验跑法不受影响
  - ⬛ 2026-09-30 订正（§6 Q10）：第二条改为 **`git merge-base --is-ancestor HEAD origin/master` 不成功 → 拒绝**。原判据「当前分支是 `master`」会拒掉正确流程——批次按 `soak-log.md` 表头在被测 SHA 的**干净 detached worktree** 里跑，那里没有分支名。新判据下，`master` 上某个 SHA 的 detached worktree 放行，未合入的特性分支 SHA 拒绝。`origin/master` 解析不出来时怎么报错交给 design-tests，不是新规则
- **涉及文件**: `scripts/soak_run.py`（不在冻结集——冻结集是 `HASH_COVERED_PATHS` 所列 8 条路径，本脚本不在其中；改它不改 `suite_hash`，开工当天复核）、它的单元测试
- **验收（种子）**: ~~三种情形各一条测试——CI 环境 ＋ `--append` → 拒绝；非 `master` ＋ `--append` → 拒绝；`master` ＋ 非 CI ＋ `--append` → 放行~~（用假 git / 假环境，不真跑 soak）
  - ⬛ 2026-09-30 按订正后的规则，至少四条：CI 环境 ＋ `--append` → 拒绝；`HEAD` 不是 `origin/master` 的祖先（未合入的特性分支 SHA）＋ `--append` → 拒绝；`master` 分支上 ＋ 非 CI ＋ `--append` → 放行；**`master` 上某个 SHA 的 detached worktree ＋ `--append` → 放行**
- 测试矩阵：待 /tdd-guardian:design-tests

---

## 4. 出口闸

全部满足才算完。「证据位置」在核验时填，现在全部是占位。

| # | 门槛 | 判据 | 证据位置 |
|---|---|---|---|
| 1 | 全部 lane 在合并头上绿 | `.claude/tdd-guardian/config.json` 里**每一条** lane（不写死条数），带 `env -u FORCE_COLOR`；`/tdd-guardian:gate push` | _待填_ |
| 2 | 类型检查 | `uv run mypy src/` 干净 | _待填_ |
| 3 | lint | `uv run ruff check src/ tests/ scripts/` 干净（不跑 `ruff format`）；`scripts/lint_*.py` 全部 rc=0 | _待填_ |
| 4 | router 体量 | `python3 scripts/check_router_size.py` rc=0（新路由不许挤爆 500 行） | _待填_ |
| 5 | 路由快照同 commit | 每个新增 / 改动路由的 commit 里同时改了 `tests/contract/routes.snapshot`，diff 只有新增行（WI-3 若给已有路由加头 / 字段，只许加法）；PR 描述写明破坏性与迁移路径（ADR-0011） | _待填_ |
| 6 | e2e 分组登记 | 新增的每条 e2e 都登记进 `scripts/lint_e2e_groups.py`（验收目录进 `EXPECTED_ACCEPTANCE_PER_DIR`，或模块进 `UNGROUPED_E2E_MODULES` 并同步 `EXPECTED_UNGROUPED_ITEMS`；新分组还要进 `pyproject.toml` markers 与 `tests/unit/test_e2e_group_guard.py` 的钉死副本）；合入前在分支上跑一次 `soak_run.py`（只核验、不 `--append`）确认 deselected 精确相等 | _待填_ |
| 7 | 锁契约 | WI-2 验收的跨进程互斥、`SIGKILL` 释放、各写手不复活目录、共享写手 2 秒内 409、ABA 身份复核、交叉获取抛错六类测试齐全；ADR-0015 在本分支合入的同一 PR 里由 Proposed 转 **Accepted**（§6 Q11） | _待填_ |
| 8 | 每条欠账一个 commit 结清 | 009 表 #51 / #56 / #58 / #53 / #31 各行状态改为已结清并附 commit | _待填_ |
| 9 | #31 的 CI 核验 | 合并头上至少一次 `workflow_dispatch` 的 `tests.yml` 运行，`e2e` job 绿、`attempt=1`；PR 的 `pull_request` 运行同样绿。run id 按 WI-7 的记录位置落档 | _待填_ |
| 10 | ~~合入后 soak 一次~~（⬛ 2026-09-30 被 [plan §7「012 开工核验」](../plan-tech-stack-migration.md#012-开工核验2026-09-30-维护者裁定) 取代：012 开工要在它开分支的那个 `commit` 上新跑一批，合入头红不红由那一批覆盖；本门槛不再单独要求，原文保留） | 合入后在 `master` 上跑一次 `soak_run.py --append`，green，`suite_hash` 仍是冻结值；这一行记进台账（~~它是正常计数行，commit 变不清零~~ ⬛ 2026-09-29：批次规则下单独一行不计入任何批次，只证明合入头没把 `baseline_1b` 弄红；012 开工要的批次见 [012 §4 门槛 F](./012-storage-format.md)） | _待填_ |
| F | ~~**冻结区零字节改动**~~（⬛ 2026-09-28 随 [012 门槛 F](./012-storage-format.md) 放宽：冻结区可以改，但改了就须在合并头的新 `suite_hash` 上重跑一批并通过，否则 012 开工时对不上最后一次通过批次；仍应避免无谓改动。下面原判据保留作「没动冻结区」时的核对方式。⬛ 2026-09-30：012 开工一律新跑一批，见 [plan §7「012 开工核验」](../plan-tech-stack-migration.md#012-开工核验2026-09-30-维护者裁定)；本门槛只剩「别无谓动冻结区」的约束） | 下列 8 条路径 `git diff --stat master... -- <paths>` 为空，`suite_hash` 与 [`soak-log.md`](./soak-log.md) 表头冻结值一致：`tests/e2e/baseline_1b/**`、`tests/e2e/conftest.py`、`tests/e2e/helpers.py`、`tests/e2e/test_harness_smoke.py`、`tests/fixtures/epub_corpus.py`、`tests/fixtures/epub_zip.py`、`tests/fixtures/ai_stub.py`、`tests/conftest.py`。路径清单的定义处是 `soak-log.md`「`suite_hash` 的取法」与 `scripts/soak_run.py` 的 `HASH_COVERED_PATHS`，冲突以那里为准 | _待填_ |
| R | **红灯必查根因** | 分支存续期间，`baseline_1b` 与 e2e lane（含 CI `e2e` job）**每一次**红都在 §8「红灯记录」追一行：时间、commit、失败用例、根因（产品缺陷 / 测试缺陷 / 环境）、处置 commit。**不允许以「重跑变绿」结案**。表为空或每行根因齐全才算过 | _待填_ |
| 11 | 合入前 CI 全绿 | PR 上 `pull_request` 触发的 `tests.yml`（`unit` ＋ `e2e`）与 `lint.yml` 全绿后才合入（PR 先开，CI 才会跑——不是「CI 绿后开 PR」） | _待填_ |

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
- **router 体量**：列表 ＋ 删书 ＋ 导出塞进 `library.py`（已 333 行）会逼近 500。缓解：新 router 模块（§6 Q4），012 的 #55 / #57 还要往这里加。
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
| Q8 | 删书对集合 / 对话的处置；墓碑清理时机 | WI-5 | 集合成员在提交点前移除；对话**删时问**——`delete_conversations` 参数默认 `false`，确认框归 014 WI-16b（维护者取舍）；墓碑在启动与每次删书前清扫，清扫持锁。见 WI-5 | ✅ 已裁定 |
| Q9 | CI 运行记录落在哪 | WI-7 | `soak-log.md` 新开「CI 运行记录」一节；本文 §8 只放链接 | ✅ 已裁定 |
| Q10 | `soak_run.py --append` 硬拦截 | WI-8 | 要：`GITHUB_ACTIONS` 或~~非 `master`~~ 即拒绝，独立小 WI。⬛ 2026-09-30 订正：第二条改为「`git merge-base --is-ancestor HEAD origin/master` 不成功即拒绝」——`master` SHA 的 detached worktree 放行、未合入的特性分支 SHA 拒绝；测试须含「detached worktree ＋ `--append` → 放行」。条文见 WI-8 | ✅ 已裁定（2026-09-30 订正） |
| Q11 | ADR-0015 是否过 ADR-0000 准入 | WI-2 收尾 | 过（跨模块、长期、多个写手共同遵守）；契约正文搬进 ADR，合入即 Accepted（门槛 7） | ✅ 已裁定 |
| Q12 | 删后再导入同一 EPUB 算同一本书还是新书（原型暴露：集合按目录名引用会悄悄挂回，对话按 `book_uuid` 引用挂不回，两种引用不一致） | WI-5 | **新书**：什么都不挂回。集合成员在删书时移除（WI-5 第 3 步），对话随新 `book_uuid` 自然不挂回；写手等锁醒来按 `book_uuid` 复核（WI-2 契约项 6）（维护者取舍） | ✅ 已裁定 |

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

### 🟡 合入记录：第一段（WI-1 – WI-3）（本文是这条事实的唯一定义处）

⬛ 2026-10-02 回写。**018 的 WI-1 – WI-3 已于 2026-10-01 合入 `master`；WI-4 – WI-8 不在这次合入里，018 尚未关闭。** 别处提到「018 是否在主干上」一律链回本节。

| 事实 | 值 | 复核命令 |
|---|---|---|
| PR | [#33](https://github.com/anzchy/reader3-pro/pull/33)，25 commits；标题「018: 书库路由 WI-1–WI-3——每书写锁（ADR-0015）、设置版本校验（#51）与审计修复三轮」 | `gh pr view 33` |
| 合并 commit | `c08317b`（2026-10-01 22:43 +0800，`Merge pull request #33 from anzchy/018-library-routes`），第一父 `f621175` | `git log -1 c08317b` |
| 合并前最后一个 commit | `42c0728`（§7.1 修复轮 2 / 3 记录）；分支领先量 0 | `git rev-list --count master..018-library-routes` |
| 交付 | WI-1（兑付方改写，`865d068`）；WI-2（每书写锁 `book_lock`，`48bdfa4`，及 §7.1 三轮审计修复）；WI-3（#51 设置写入版本校验，`2d5f96f`） | `git log c08317b^1..c08317b^2 --oneline` |
| 未交付 | WI-4（#56 列表路由）、WI-5（#58 删书）、WI-6（#53 导出）、WI-7（#31 收尾对账）、WI-8（`--append` 硬拦截）——`src/` 里没有对应路由，`routes.snapshot` 无新增，`scripts/soak_run.py` 无 `GITHUB_ACTIONS` / `is-ancestor` 判据 | `grep -n "@router" src/reader3_app/web/routers/library.py` |
| 本地 lane（在 `42c0728` 上，PR 正文，协调者独立复跑） | unit ＋ contract 3107 passed / 2 skipped / 1 xfailed；fe 279；e2e 254 passed / 16 skipped；packaging 11 | — |
| CI（PR 上） | 全绿：tests run `36854855076`、lint run `36854855032` | `gh pr checks 33` |
| 冻结集 | 8 条路径零改动，`suite_hash` 不变（PR 正文） | — |
| ADR-0015 | 门槛 7 要求「合入同一 PR 里转 Accepted」——PR #33 合入时仍是 Proposed；2026-10-02 由合入回写转 Accepted（锁契约已在 `master` 上，删书接入随 WI-5） | `sed -n 5p docs/adr/0015-per-book-write-coordination.md` |

### 红灯记录（门槛 R）

分支存续期间 `baseline_1b` / e2e lane / CI `e2e` job 的每一次红追一行。「重跑变绿」不是根因。

| 时间（UTC） | commit | 失败用例 | 根因类别 | 根因 | 处置 commit |
|---|---|---|---|---|---|
