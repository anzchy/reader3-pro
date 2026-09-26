# 018-library-routes —— 任务

- **状态**: 骨架，待审（2026-09-26）。分支**未开**；本文只做开工前的范围与闸门登记，没有一项已实施
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
> soak 判据与清零规则 → [§7](../plan-tech-stack-migration.md)；soak 当期计数与机制挑战闸记录 → [`soak-log.md`](./soak-log.md)；
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
| 本任务书评审通过 | ⏳ 待审 | 本文 §6 的 TODO(审) 至少关掉「阻塞 WI-1 / WI-2」两档 |

- **不等 soak**（D1）。本分支在 soak 等待期内做完并合入；代价是它**不得碰冻结集**（§4 门槛 F）——它合进 `master`，改一个字节就清零 soak 计数。
- **`soak_run.py --append` 只在 `master` 上跑**。分支上的运行只做核验、不进台账（[017 §4](./017-audit-followup.md)）。这是流程约束，`scripts/soak_run.py` 本身**不检查分支**（它只在覆盖路径有未进索引的改动时拒绝 `--append`）。

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

- 冻结集 8 条路径的任何改动（§4 门槛 F）——包括 009 欠账 #49 / #50
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
| WI-6 | #53 书库导出（前后端） | **导出 schema 裁定**（§6 Q7）、WI-4 | ✅ / 挂起 |
| WI-7 | #31 CI e2e job 收尾对账 | 合并头存在（最后做） | ❌（文档 ＋ 一次 CI 运行） |

> WI-3 / WI-4 不依赖 WI-2，但**仍排在它之后**（D1 定的顺序）：锁的形状先定，后面每条路由都知道自己要不要持锁。

### WI-1: 兑付方改写（一批，单个 commit）

- **目标**: 把 D1 的结论落进所有机器可查的地方，**一次改完**：拆开改会有一个 commit 让 Track-D 台账测试红（钉条写 018，校验还只认 012，或反过来）
- **涉及文件**:
  - `docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md`：#51 / #53 / #56 / #58 四行的兑付方列改 `018-library-routes`；#56 行删掉「与 #35 同批」；#53 行「内容依赖 012 存储格式」的理由改写（导出走 `book_store`，与格式无关——见 WI-6）；#31 行的兑付方列「待定」改为已兑付的实际去向（见 WI-7）
  - `tests/unit/test_track_d_ledger.py`：`DEBT_012_RE` 与 `debt_citation_problems` **泛化，不放宽**——接受 `012 debt #N` 或 `018 debt #N`，且断言「钉条引用的分支号 = 欠账表该行兑付方列的分支号」（今天只查 `"012" in owner`）；硬编码 `012 debt #N` 的用例与 `test_cited_debt_ids_must_resolve_to_012_rows` 同步改名改义
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
- **须定的契约项**（写进 ADR-0015 草案）:
  1. **锁文件位置**：书目录**之外**（默认提议 `books/.locks/{book_folder}.lock`，§6 Q2）。理由：锁文件在书目录里时，删书的 `rmtree` 会把它 unlink，随后任何 `makedirs` 建出的是新 inode——两个进程各持一把「同名」锁；首次导入时书目录还不存在，锁无处可放
  2. **粒度与层次**：进程内注册表 ＋ 跨进程 `flock`（与 notes 同构）；与 notes 锁的关系——合并，还是固定获取顺序（先书锁后 notes 锁）（§6 Q3）
  3. **拒绝语义**：长写手（import / delete / reindex / migrate / 上传）**非阻塞**获取，拿不到 → HTTP **409** / CLI 非零退出码并说明持有者类别；短写手（notes / ai_meta / conversations）是否阻塞等待、等多久（§6 Q3）
  4. **不复活规则**：持锁的写手在写之前必须确认书目录仍存在；除 import 外任何写手**不得** `makedirs` 书目录本身
  5. **崩溃**：`flock` 随进程死亡释放；锁文件残留不等于被持有
- **涉及文件**: 新模块（位置 TODO(审)，候选 `src/reader3_app/book_lock.py`）、`notes_service.py`、`ai/books.py`、`ai/conversations.py`、`vector_search.py`、`web/routers/search.py`（`api_index_book` 持锁）、`reader3.py`（`process_epub` 持锁）；`docs/adr/0015-*.md`（草案，**开工时写，不是现在**）
- **验收（种子）**:
  - 两个**进程**对同一本书同时取长写锁：恰好一个成功，另一个得到可判别的拒绝（不是超时、不是异常栈）
  - 持锁进程被 `SIGKILL` 后锁立即可取
  - 删书进行中，notes / ai_meta / conversations / vector 写手都**不会**把书目录重新建出来（每个写手一条测试）
  - 同一本书的 notes 并发写仍不丢（沿用 notes 现有并发测试，不改一字仍绿）
  - 测试矩阵：待 /tdd-guardian:design-tests
- **ADR-0015**：按 [ADR-0000](../../../adr/0000-use-adrs.md) 的准入（五问 ≥2 ＋ 定义处在可归档文档里或不存在）先过一遍再写；过了，本 WI 的「须定的契约项」整段搬进 ADR、这里留链接

### WI-3: 欠账 #51 —— provider 保存版本校验（后端 ＋ FB-S09 客户端半边）

- **目标 / 验收**: 见 [#51 行](./009-e2e-annotations.md#跨波欠账)（同 revision 两个客户端 → 第二个 409 且文件保留第一个；不带 revision 的客户端行为不变；加法式）。本文只补约束
- **今天的事实**: `ai_settings.json` 有四个写入端——`PUT /api/settings`、`POST /api/settings/import`、`PUT /api/settings/providers/{provider_name}`、`DELETE /api/settings/providers/{provider_name}`；`save_ai_settings` 已是 `mkstemp` ＋ `os.replace` 原子写。处理函数都是 `async def` 且读—改—写之间没有 `await`，所以**单进程内**事实上串行，**跨进程**没有任何协调
- **须定**: revision 的取值（文件内容 hash / `st_mtime_ns` / 文件内单调计数，§6 Q5）；四个写入端里哪几个校验（至少 provider PUT）；比对与写入要在同一把跨进程锁里（这是全局配置锁，**不是** WI-2 的每书锁）
- **涉及文件**: `web/routers/settings.py`、`ai/config.py`（`load_ai_settings` / `save_ai_settings`）；`frontend/src/settings/index.ts`（provider 保存的 `requestJson` 带 revision、409 走可见错误）；`tests/contract/routes.snapshot`（若加 `If-Match` 头或响应字段，按 ADR-0011 同 commit）
- **验收补充（种子）**: 409 的响应体不回显任何 key（ADR-0012 / 「API key 不回浏览器」）；前端 409 可见错误有 Vitest ＋ 一条 e2e；013 的 `test_provider_save_failure_is_visible` 不改仍绿
- 测试矩阵：待 /tdd-guardian:design-tests

### WI-4: 欠账 #56 —— 客户端书目列表路由

- **目标 / 验收**: 见 [#56 行](./009-e2e-annotations.md#跨波欠账)（路由进快照；条数 = 书库目录数；书名 = `load_book_metadata()`）
- **建在接缝上**: 数据只取自 `book_store.load_book_metadata()`（今天是全量读后投影出 `book_id` / `title` / `authors`）。012 WI-5 换它的函数体、012 WI-10 在每项上加 `storage_format`——本路由不得绕过接缝直读 `book.pkl`，否则 012 换实现时它不跟着变
- **字段集**: 今天接缝只给三项。014 WI-16b 书卡要的其余字段（封面、章节数、进度……）是否本路由给、从哪取——§6 Q6；**不在本 WI 为此扩接缝**，扩了就是替 012 定格式
- **涉及文件**: 新 router 模块（候选 `web/routers/library_books.py`，§6 Q4；`library.py` 已 333 行）、`web/server.py`（`include_router`）、`tests/contract/routes.snapshot`、`tests/unit/test_book_store_metadata_seam.py`
- **接缝守卫测试**: `test_no_production_call_site_uses_the_new_seam_yet` 有两条断言——(a)「只有 `book_store.py` 提到 `load_book_metadata`」本 WI 起**必然**不成立，改写为「调用方白名单 = {本路由模块}」；(b)「`library_view` 仍 `load_book_cached(item)`」**保留**，它是 012 WI-5 的活
- **验收补充（种子）**: 一本 `book.pkl` 损坏的书不让整张列表 500（跳过并标记，或整体降级——须写进契约测试）；返回顺序确定
- 测试矩阵：待 /tdd-guardian:design-tests

### WI-5: 欠账 #58 —— 删书路由（WI-2 之后）

- **目标 / 验收**: 见 [#58 行](./009-e2e-annotations.md#跨波欠账)（删后读与 `POST /api/index` 都 404；FB-L18 可测）
- **#58 行里有一句已过期**：它要求「失效 `load_book_cached` 的 lru_cache」。011 之后 `load_book_cached` 以 `(st_mtime_ns, st_size)` 为 key、每次调用先 `os.stat`，删掉的书不会从缓存里被读出来。**真正要处理的是别处**：`server._stats_cache`（5 秒 TTL 的书库统计）、搜索索引缓存、会复活目录的写手（WI-2 不复活规则）
- **边界**（沿 [ADR-0012](../../../adr/0012-security-boundaries.md) 的思路；ADR-0012 **不**定义大小上限与 409，那些由本 WI 自定）:
  - `book_id` 过 `safe_book_folder` ＋ `_validate_book_id`（枚举目录成员）
  - 删除形状：持 WI-2 的锁 → 先把书目录**原子改名**成枚举不到的墓碑名 → 失效缓存 → `rmtree` 墓碑 → 放锁。半路崩溃留下的是墓碑，不是半本书；墓碑的清理时机 TODO(审)
  - **409**：该书的锁被他人持有（导入 / 重建 / 迁移 / 上传进行中）。**404**：书不存在
- **须裁定**（§6 Q8）: 删书时项目根下的 `library_collections.json` 里的集合成员、项目根按 `book_uuid` 存的对话——一并删、保留为孤儿、还是标记
- **涉及文件**: WI-4 的 router 模块、`web/server.py`（`_stats_cache`）、`search_service.py`、WI-2 的锁模块、`tests/contract/routes.snapshot`
- **e2e**: 删书测试**不得**改动 `baseline_1b` 共用的会话语料库——用自己的库目录与自己起的服务（`tests/fixtures/deg_assertions.py` 的起服务形状），不在任何分组目录里放 `conftest.py`
- **验收补充（种子）**: 删书与单本重建并发 → 一方 409，且不出现「删掉的目录被重建出来」；删后 `/api/library/stats` 立即反映；删后该书不再出现在 WI-4 的列表里
- 测试矩阵：待 /tdd-guardian:design-tests

### WI-6: 欠账 #53 —— 书库导出（schema 定下之后；否则挂起）

- **目标 / 验收**: 见 [#53 行](./009-e2e-annotations.md#跨波欠账)（路由进快照；非空合法 JSON；FB-S06 半边）
- **前置**: 导出 schema 的覆盖面——metadata / content / annotations 各含什么、是否带对话（§6 Q7）。**schema 没定，本 WI 不开工**
- **与存储格式无关**: 导出只经 `book_store` 读，所以 012 换格式后本路由不改；012 门槛 13 验的正是「导出不把 `corrupt` 当 `valid`」。#53 兑付方列原写的「内容依赖 012 存储格式」由 WI-1 改掉
- **边界**: 整库导出可能很大——流式还是一次成型、有无大小上限、临时文件是否 `mkstemp`，本 WI 自定（ADR-0012 没有现成规则）
- **涉及文件**: WI-4 的 router 模块、`frontend/src/settings/index.ts`（`wireExport` 的 `set-export-json`）、`tests/contract/routes.snapshot`
- **挂起条款**: 本分支合入前 schema 仍未裁定 → 本 WI 挂起，在 §7 立一行：兑付方写**具体的分支号（§9 分配）或具名维护者**，**不得写 012、不得写「待定」**；009 #53 行同步指过去；012 门槛 13 的「导出」一格随之标注不适用
- 测试矩阵：待 /tdd-guardian:design-tests

### WI-7: 欠账 #31 —— CI e2e job 收尾对账（最后做）

- **先说清楚这条账的现状**：#31 **已于 2026-09-20 结清**（[#31 行](./009-e2e-annotations.md#跨波欠账) 状态列）。`tests.yml` 的 `e2e` job 已存在（干净 ubuntu、`uv sync --frozen`、记 Chromium 版本、`soak_run.py --log-dir soak-ci-logs` 要 68/68、再跑 `-m "not baseline_1b"`）；机制挑战闸第 1 项已在它上面 PASS（[`soak-log.md` 机制挑战闸执行记录](./soak-log.md)，run 35584711194）。**本 WI 不建 job**
- **「补 soak 的环境多样性那一半」这个说法不成立**：CI 的运行**不进 soak 台账**，这是写定的——
  - `tests.yml` 的 `e2e` job 头注释：结果记进机制挑战闸表，「不往 soak 台账追行」，「不传 `--append`」
  - [§7 清零规则](../plan-tech-stack-migration.md) 第 2 条：`browser` 或 `os` 变了就清零。CI 行的 `os` 是 `linux-*`、本地是 `darwin-*`，混进去每换一次就清零一次
  - 所以「环境多样性」由 CI job 以**独立信号**的形式提供（每次跑都是一次干净 Linux 的 68/68 首次通过核验），不是填台账的行
- **目标**:
  1. **对账**：修掉仍把 #31 写成「没建」「待定」的地方——009 #31 行兑付方列（WI-1 已改）、§7「该补偿至今没有建出来」一段（**§7 不归本文改**，见本 WI 末尾）、`tests.yml` 的 `e2e` job 头注释里「一个触发器都不新增」「日常 commit 与 PR 一律不跑」两句（2026-09-23 已加 `pull_request → master`，文件头注释已更新，job 注释没跟上；`.github/workflows/` 不在冻结集）
  2. **核验**：在本分支的**合并头**上手点一次 `gh workflow run tests.yml --ref <合并头所在 ref>`，`e2e` job 绿且 `attempt=1`；本分支 PR 上 `pull_request` 触发的那一次同样要绿（门槛 R 适用）
  3. **记录**：两次运行的 run id、commit、Chromium 版本记进哪里——§6 Q9（默认提议：`soak-log.md` 机制挑战闸执行记录表旁的「CI 运行记录」，**不是** soak 台账）
- **不做**: 不给 `soak_run.py` 加分支检查或 CI 环境检查（§6 Q10 若裁定要加，另立工作项并走 workflow）；不改 `tests.yml` 的触发器与步骤
- **§7 / §9 的措辞归协调者改**：本 WI 只列需改之处，不动 `plan-tech-stack-migration.md`

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
| 7 | 锁契约 | WI-2 验收的跨进程互斥、`SIGKILL` 释放、各写手不复活目录三类测试齐全；ADR-0015 草案已提交（或 §6 记明未过准入的理由） | _待填_ |
| 8 | 每条欠账一个 commit 结清 | 009 表 #51 / #56 / #58 / #53 / #31 各行状态改为已结清并附 commit；#53 若挂起，按 WI-6 挂起条款转出，不是「已结清」 | _待填_ |
| 9 | #31 的 CI 核验 | 合并头上至少一次 `workflow_dispatch` 的 `tests.yml` 运行，`e2e` job 绿、`attempt=1`；PR 的 `pull_request` 运行同样绿。run id 按 WI-7 的记录位置落档 | _待填_ |
| 10 | 合入后 soak 一次 | 合入后在 `master` 上跑一次 `soak_run.py --append`，green，`suite_hash` 仍是冻结值；这一行记进台账（它是正常计数行，commit 变不清零） | _待填_ |
| F | **冻结区零字节改动** | 下列 8 条路径 `git diff --stat master... -- <paths>` 为空，`suite_hash` 与 [`soak-log.md`](./soak-log.md) 表头冻结值一致：`tests/e2e/baseline_1b/**`、`tests/e2e/conftest.py`、`tests/e2e/helpers.py`、`tests/e2e/test_harness_smoke.py`、`tests/fixtures/epub_corpus.py`、`tests/fixtures/epub_zip.py`、`tests/fixtures/ai_stub.py`、`tests/conftest.py`。路径清单的定义处是 `soak-log.md`「`suite_hash` 的取法」与 `scripts/soak_run.py` 的 `HASH_COVERED_PATHS`，冲突以那里为准 | _待填_ |
| R | **红灯必查根因** | 分支存续期间，`baseline_1b` 与 e2e lane（含 CI `e2e` job）**每一次**红都在 §8「红灯记录」追一行：时间、commit、失败用例、根因（产品缺陷 / 测试缺陷 / 环境）、处置 commit。**不允许以「重跑变绿」结案**。表为空或每行根因齐全才算过 | _待填_ |
| 11 | CI 全绿后开 PR | `tests.yml`（`unit` ＋ `e2e`）、`lint.yml` | _待填_ |

- 不得设 `TDD_GUARD_BYPASS`。
- `EXPECTED_BASELINE_ITEMS` 不许变——它一变就说明碰了冻结集。
- **012 的门槛 13 / 14 仍归 012**：「018 的路由跨四种存储态」与「012 的写手持 018 的锁」要等 012 的格式与写手存在才能验，本表不收。

---

## 5. 风险

- **删书复活目录**：任何写手在删书之后 `makedirs` 书目录（notes、ai_meta、conversations、vector 今天都会建），删掉的书以残缺形态「回来」。缓解：WI-2 不复活规则 ＋ 每个写手一条并发测试（门槛 7）。
- **锁文件放在书目录里**：`rmtree` 会 unlink 锁文件，随后新建的是新 inode，两个进程各持一把「同名」锁、互斥失效。缓解：锁放书目录之外（WI-2 契约项 1）。
- **与 notes 锁死锁**：新书锁与现有 `notes_service._book_write_lock` 两把锁若获取顺序不一，可死锁。缓解：§6 Q3 定合并或固定顺序，并有一条交叉获取的测试。
- **e2e 污染共享语料**：删书测试若动了 `baseline_1b` 用的会话库，会让 soak 在 `master` 上变红（清零）。缓解：WI-5 的独立库 ＋ 独立服务；不在分组目录放 `conftest.py`（裸 `from conftest import BOOK_ID` 会断）。
- **soak 收集计数**：新 e2e 漏登记分组，合入后下一次 soak 的 deselected 对不上就判 red。缓解：门槛 6。
- **冻结集诱惑**：共享 fixture 想放 `tests/e2e/conftest.py` 或改 `helpers.py`——那两个都在冻结集里。缓解：新 fixture 放 `tests/fixtures/` 下的非冻结模块。
- **把 CI 行当 soak 行**：有人照 #31 行旧措辞「手点 dispatch 补台账行」去 `--append`，一次就按清零规则第 2 条清零。`soak_run.py` 不拦这件事。缓解：WI-7 对账掉旧措辞；§6 Q10。
- **router 体量**：列表 ＋ 删书 ＋ 导出塞进 `library.py`（已 333 行）会逼近 500。缓解：新 router 模块（§6 Q4），012 的 #55 / #57 还要往这里加。
- **#51 只修一个写入端**：四个写入端只让 provider PUT 做校验，其余三个仍可静默覆盖。缓解：§6 Q5 明确裁定覆盖面，并在契约测试里写出没覆盖的那几个的行为。

---

## 6. 开放问题

按「挡住实施的先后」排序：先挡的在上。

| Q | 问题 | 挡哪个 WI | 依据 | 状态 |
|---|---|---|---|---|
| Q1 | WI-1 泛化后的台账校验形状：正则 `\b(012\|018) debt #(\d+)\b` ＋「分支号 = 兑付方列分支号」是否即为「泛化不放宽」的判据；前端计划里中文的「012 债 #N」是否也纳入机器校验 | WI-1 | `test_track_d_ledger.py` 的 `DEBT_012_RE` / `debt_citation_problems` | TODO(审) |
| Q2 | 锁文件位置：`books/.locks/{book_folder}.lock`（默认提议）还是别处；`books/` 下的点目录会不会被任何枚举逻辑误收 | WI-2 | WI-2 契约项 1 | TODO(审) |
| Q3 | 书锁与 notes 锁：合并为一把，还是保留两把并固定顺序；短写手阻塞等待还是非阻塞 409 | WI-2 | `notes_service._book_write_lock` | TODO(审) |
| Q4 | 新 router 模块名与是否为 012 的 #55 / #57 预留位置 | WI-4 | `check_router_size.py`；012 §5 router 体量 | TODO(审) |
| Q5 | #51 revision 的取值与覆盖面（四个写入端全做还是只做 provider PUT）；用 `If-Match` 头还是 body 字段 | WI-3 | #51 验收列「可选 revision 或 If-Match」 | TODO(审) |
| Q6 | #56 列表每项的字段集：只给接缝的三项，还是为 014 书卡多给；多给的从哪取而不越过 012 的格式边界 | WI-4 | `BookMetadataView`；前端计划 WI-16b | TODO(审) |
| Q7 | #53 导出 schema：metadata / content / annotations / 对话各含什么，整库还是可选单本 | WI-6（不定即挂起） | D1 条件；#53 验收列 | TODO(审) |
| Q8 | 删书对项目根数据的处置：`library_collections.json` 的集合成员、按 `book_uuid` 存的对话；墓碑的清理时机 | WI-5 | ADR-0003（`book_uuid`）；ADR-0001 | TODO(审) |
| Q9 | CI 运行记录落在哪：`soak-log.md` 机制挑战闸表旁新开一节，还是本文 §8 | WI-7 | WI-7 目标 3 | TODO(审) |
| Q10 | `soak_run.py` 是否加硬拦截（`--append` 时检测 `GITHUB_ACTIONS` / 非 `master` 即拒绝）。今天这两条都只是流程约束 | 不挡（可后做） | WI-7「不做」 | TODO(审) |
| Q11 | ADR-0015 是否过 ADR-0000 准入；不过则契约正文留在本文 WI-2 | WI-2 收尾 | ADR-0000 | TODO(审) |

---

## 7. 欠账

本分支新立的欠账（兑付方指向后续分支的）。继承来的欠账不在这里，在 [009 表](./009-e2e-annotations.md#跨波欠账)。

| # | 欠什么 | 欠账方 | 兑付方 | 验收怎么查 | 状态 |
|---|---|---|---|---|---|

---

## 8. 合入记录

_未合入。合入后本节是「018 是否在主干上」的唯一定义处，格式照 [011 §8 合入记录](./011-backend-refactor.md)。_

### 红灯记录（门槛 R）

分支存续期间 `baseline_1b` / e2e lane / CI `e2e` job 的每一次红追一行。「重跑变绿」不是根因。

| 时间（UTC） | commit | 失败用例 | 根因类别 | 根因 | 处置 commit |
|---|---|---|---|---|---|
