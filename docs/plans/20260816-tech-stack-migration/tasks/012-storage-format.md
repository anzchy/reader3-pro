# 012-storage-format —— 任务

- **状态**: ~~评审进行中：D1、Q1–Q6 已裁定，Q7+ 待裁（§6）~~ ⬛ 2026-10-02：评审完成——D1、Q1–Q13 全部裁定（§6）；分支未开（⬛ 2026-09-30，原「骨架，待审（2026-09-26）」）。本文只做开工前的范围与闸门登记，没有一项已实施
- **对应阶段**: Phase 3「存储去 pickle 化」＝ 里程碑 **M3**（[§9 编号表](../plan-tech-stack-migration.md)）
- **计划文件夹**: [`20260816-tech-stack-migration/`](../plan-tech-stack-migration.md)（归属 **A**）
- **上游**: [`018-library-routes`](./018-library-routes.md)（[§9](../plan-tech-stack-migration.md) 的 M4a-债）先于本分支合入，本分支在它之上开工；顺序的定义处是 [进度盘 §2](../../20260824-frontend-backend-plan-progress.md)
- **下游**: M3 与 M4b（`014`）**严格串行**（[§9.1](../plan-tech-stack-migration.md)）。014 WI-16b 的外部前置写的是「债 #54–#58」，D1 之后拆成两家：**等 012** 的是 #54、#55、#57；**等 018** 的是 #56、#58（#53 的前端半边是 FB-S06，不在 WI-16b）
- **节奏**: 按 Wave 推进，Wave 内按**依赖**顺序（通常即编号顺序；例外写在 §3 表里——Wave C 是 WI-9 → WI-10 → WI-8 → WI-11，因为 WI-8 依赖 WI-9 / WI-10）；行为变更各自独立 commit，路由新增与 `routes.snapshot` 同 commit

> **权威范围**：本文**定义**的只有四件事——012 的工作项切分、每个 WI 的验收占位、012 的出口闸与合入记录、D1 的裁定理由（§6）。
> 以下一律**只链接不复述**（「搬，不抄」）：写入协议（提交点与崩溃恢复）→ [ADR-0016](../../../adr/0016-generation-directory-publish.md)；三态读取 → [ADR-0007](../../../adr/0007-crash-safe-publish-protocol.md)；
> 目标格式、双写/日落、`--migrate` 硬约束 → [ADR-0009](../../../adr/0009-book-format-manifest-jsonl.md)；
> API 冻结规则 → [ADR-0011](../../../adr/0011-api-v1-freeze.md)；soak 判据 → [§7](../plan-tech-stack-migration.md)；
> soak 当期计数 → [`soak-log.md`](./soak-log.md)；欠账正文 → [009 跨波欠账表](./009-e2e-annotations.md#跨波欠账)；
> 分支编号 → [§9](../plan-tech-stack-migration.md)；执行顺序 → [进度盘](../../20260824-frontend-backend-plan-progress.md)；
> DEG-S1–S4 文案与状态定义 → [前端计划 WI-2–WI-5](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md) 与 [设计规格 §6.4](../../20260817-frontend-ui-refactor/spec-frontend-design.md)。
>
> **引用规则**：用**符号名**定位，不写代码行号（同 011）。

---

## 1. 进入条件

三路汇合，定义在 [§9.1](../plan-tech-stack-migration.md)，本节只记每一路的状态去哪里查：

| 路 | 状态 | 在哪查 |
|---|---|---|
| Phase 2b（011） | ✅ 已合入 | [011 §8 合入记录](./011-backend-refactor.md)（#7 仍是 ⚠️，剩余一半即本文 WI-5） |
| Track D（010） | ✅ 已合入 | [进度盘 §1 状态板](../../20260824-frontend-backend-plan-progress.md) |
| **soak 门槛** | ~~⏳ **仍阻塞开工**~~ ~~⬛ 2026-09-29：批次次数已满足（判决见 [`soak-log.md` 批次声明](./soak-log.md)）；开工时还须 §4 门槛 F（开工 `suite_hash` ＝ 最后一次通过批次的）成立~~ ⬛ 2026-09-30：⏳ **仍阻塞**——已通过的批次不单独放行 012，开工要在本分支将开的那个 `commit` 上新跑一批 10/10，见 [plan §7「012 开工核验」](../plan-tech-stack-migration.md#012-开工核验2026-09-30-维护者裁定) | 判据：[§7 soak 门槛](../plan-tech-stack-migration.md)；~~次数与跨度现算~~批次判决（⬛ 2026-09-28 批次规则）：`uv run python scripts/soak_run.py --verdict <批次 ID>`，批次声明在 [`soak-log.md` 表头](./soak-log.md)。**本文不写派生数与日期** |
| 机制挑战闸 | ~~不再阻塞（第 1、3 项 PASS；~~ ⬛ 2026-09-28 批次规则 4：**第 1 项仍阻塞**，须在最终候选 `commit` 上首次通过（此前的 PASS 跑在更早的 `commit` 上，不自动覆盖）；第 3 项对当前 `suite_hash` 成立；第 2 项经维护者裁定降为记录项，**是降级不是通过**。⬛ 2026-09-30：「最终候选」＝ 新批次所在的那个 `commit`；第 3 项仅在 `suite_hash` 变了时重跑，见 [012 开工核验](../plan-tech-stack-migration.md#012-开工核验2026-09-30-维护者裁定) | 裁定：[§7 机制挑战闸](../plan-tech-stack-migration.md)；执行记录：[`soak-log.md`](./soak-log.md) |
| **018 已合入** | ~~⏳ 未开（[任务书](./018-library-routes.md) 评审通过、待开工；⬛ 2026-09-30：排在冻结集欠账窗口之后，顺序见[进度盘](../../20260824-frontend-backend-plan-progress.md)）~~ ~~⬛ 2026-10-02：🟡 **部分**——018 的 WI-1 – WI-3 已随 PR #33 合入（合入记录见 [018 §8](./018-library-routes.md)），所以**每书锁已在 `master` 上**；WI-4 – WI-8（含 #56 列表路由）**未合入**。012 能否在 018 余下各项合入之前开分支，尚未裁定（[进度盘](../../20260824-frontend-backend-plan-progress.md)第 2 步）~~ ⬛ 2026-10-07：✅ **已合入**——018 第二段 WI-4 – WI-8 随 PR #37 合入 `master`，合并 commit `74384b1`（两段合入记录见 [018 §8](./018-library-routes.md)）；每书锁与 #56 列表路由都在 `master` 上，上面那条未裁定项随之失效 | 每书写协调契约（锁，[018 WI-2](./018-library-routes.md)）是 WI-6、WI-7、WI-12、WI-13 的前置；#56 列表路由（018 WI-4）是 WI-5、WI-10 的前置。状态看 [进度盘 §1](../../20260824-frontend-backend-plan-progress.md) |

- **soak 未达标时 012 允许的**（⬛ 2026-09-29：批次次数已满足，这条现在读作「进入条件未全部满足时」）：写本任务书、评审、`/tdd-guardian:design-tests` 出测试矩阵、裁定开放问题（§6）。**012 不允许的**：开 012 分支写生产代码。
  这条只管 012——`018-library-routes` 按 D1 裁定**就在 soak 等待期内做**（⬛ 2026-09-29：等待期已不存在，018 仍排在 012 之前），不受这条约束（~~它仍不得碰冻结集，见 §4 门槛 F~~ ⬛ 2026-09-28：门槛 F 已放宽，它碰冻结集的代价是 012 开工前要在新 `suite_hash` 上重跑一批，见 §4 门槛 F）。
- **`soak_run.py --append` 只在 `master` 上跑**。分支上的运行只做核验、不进台账（[017 §4](./017-audit-followup.md) 引 011 §8 门槛 4）。
  ⬛ 2026-09-29：`--append` 现要求**整棵工作树**干净，所以批次在被测 `master` SHA 的干净 detached worktree 里跑、用 `--ledger` 写回主工作区台账（做法见 [`soak-log.md` 表头](./soak-log.md)「追加前的干净检查」）。
- ~~每天那一行怎么追~~（⬛ 2026-09-29：批次规则下不再是「每天一行」）：[进度盘「现在该做什么」](../../20260824-frontend-backend-plan-progress.md)。

---

## 2. 范围 / 非范围

### 2.1 范围（Phase 3 核心，来自 [§6 Phase 3 任务清单](../plan-tech-stack-migration.md)）

- 版本化中立格式落地；摄取双写；三态读取；`book_store` 格式封装（含 `book_store` 之外今天直读 `book.pkl` 的几处，见 WI-4 / WI-7）
- `reader3 --migrate <book_id>`（硬约束见 ADR-0009）
- Chroma 索引重建改 generation swap，**查询侧同步跟随 active generation**（[附录 A「其余未讨论但会咬人的问题」](../plan-tech-stack-migration.md)）
- pickle 写路径日落**计划**（版本号钉死、回填 ADR-0009；真正移除在「稳定一个大版本后」）
- DEG-S1–DEG-S4 朴素 Jinja 横幅（`acceptance_p3` 解 skip）
- 欠账 **#35**（`load_book_metadata()` 改读 manifest，退役 011 门槛 #7 的 ⚠️）
- 欠账 **#54 / #55**（DEG-S3 / DEG-S4 数据面——朴素横幅本身就要这份数据，与核心同批）
- 欠账 **#57 / #52**（末波 Wave D，理由见 §2.2）

### 2.2 欠账归属（D1 已裁定，2026-09-26）

> ✅ **D1 已定**：原挂在 012 的 #51–#53、#56–#58 拆成两家。裁定全文与来源在 §6 D1 行，这里只写结论：
>
> - **进 `018-library-routes`**（编号与里程碑见 [§9](../plan-tech-stack-migration.md)，顺序见 [进度盘](../../20260824-frontend-backend-plan-progress.md)）：**#51、#56、#58、#53**，外加一份新前置——**每书写协调契约**（定义见 [018 WI-2](./018-library-routes.md)）。018 在 soak 等待期内、012 之前做完。
> - **留在 012**：**#57**（上传）与 **#52**（批量重建索引），作为末波 Wave D。两条都有 012 独有的硬依赖：#57 的验收写死「按新格式落盘」→ 依赖 WI-3；#52 依赖 WI-7 的 generation swap。
> - 012 另外保留：Phase 3 核心 + #35 + #54 / #55（§2.1）。
>
> **兑付方改写**：是 [018 WI-1](./018-library-routes.md)（一个 commit）。~~在它合入之前 009 表对这四行仍写 012，以 [§9 的 018 段](../plan-tech-stack-migration.md) 为准。~~ ⬛ 2026-09-30：已由 [018 WI-1](./018-library-routes.md) 改完——009 表这四行的兑付方列写 `018-library-routes`，Track-D 台账校验同批泛化为「`012|018 debt #N`，前缀恰等于兑付方分支号」。
>
> **前端半边跟着路由走**：`frontend/src/settings/index.ts` 里批量重建（`wireDataActions` 的 `reindex`）与导出书库（`wireExport` 的 `set-export-json`）今天都只显示「暂不支持」、发 0 个请求。#52 的前端半边随 012（WI-12）换回真实请求；#51 / #53 / #56 / #58 的前端半边归属定义在 [018 §2.3](./018-library-routes.md)。

### 2.3 非范围

- 真正移除 pickle 写入路径与 runtime fallback（ADR-0009：稳定一个大版本后）
- DEG-S1–S4 的重做形态（014 / 前端计划 WI-16b）；DEG-S5（011 已交付）
- `notes.json` / `ai_meta.json` / `chroma_db/` 自身的格式变更（ADR-0009「明确不做」）
- ~~冻结集内的任何改动（§4 门槛 F）——包括 009 欠账 #49 / #50~~
  ⬛ 2026-09-28：门槛 F 放宽后，冻结集改动不再是「数周计数清零」的代价，只是「开工前在新 `suite_hash` 上重跑一批」。
  **009 欠账 #49（`helpers.py` 的 8 秒墙钟轮询）因此现在就可以付**——本文只记这一点，不把它收进 012 的范围；
  兑付与排期仍以 [009 欠账表](./009-e2e-annotations.md#跨波欠账) 为准。#50 不在冻结集（`createAnnotation` 在 `src/`），不受此影响
  ⬛ 2026-09-30：#49 / #50 排进 018 之前的冻结集欠账窗口，仍不属于 012，顺序见[进度盘](../../20260824-frontend-backend-plan-progress.md)
- **#51 / #53 / #56 / #58 与每书写协调契约本身**（归 [018](./018-library-routes.md)，§2.2）。012 只**使用** 018 的锁，不重新定义它
- 009 表与 Track-D 台账的兑付方改写（[018 WI-1](./018-library-routes.md)）

---

## 3. 工作项

测试矩阵统一待 `/tdd-guardian:design-tests`；下面的「验收」是种子，不是矩阵。

| Wave | WI | 走 workflow |
|---|---|---|
| A 格式与读写 | WI-1 – WI-5 | ✅（~~WI-1 的字段冻结部分是文档，待裁，§6 Q7~~ ⬛ 2026-10-02：§6 Q7 裁定字段冻结在代码里、由快照测试守，整条 WI-1 都走 workflow） |
| B 迁移与索引 | WI-6、WI-7 | ✅ |
| C 可见性与日落 | WI-8 – WI-11，**做的顺序 WI-9 → WI-10 → WI-8 → WI-11** | WI-8/9/10 ✅；WI-11 ❌（文档 + 版本号） |
| D 末波欠账 | WI-12（#52）、WI-13（#57） | ✅ |

> **编号说明**：WI-1 – WI-11 与 D1 前的草稿同号。草稿里暂定的 WI-12 – WI-17 **整组作废**：#51 / #53 / #56 / #58 移去 018，
> 留下的两条重新编号为 **WI-12 = #52**、**WI-13 = #57**。引用旧号的地方以本表为准。

### WI-1: 版本化中立格式落地（写入器 + 八步提交）

- **目标**: `manifest.json` + `chapters.jsonl` 写入器，按 ADR-0007 八步落盘；冻结字段集合与格式版本号（⬛ 2026-10-02：落盘步骤改按 [ADR-0016](../../../adr/0016-generation-directory-publish.md) 的 `gen/{g}/` ＋ 单指针第 0–8 步）
- **字段冻结的定义处**（⬛ 2026-10-02，§6 Q7）：格式模块里的 `BookManifest` 与 `FORMAT_VERSION`，由 manifest schema 快照测试冻结；ADR-0009 只写版本规则并链接到符号，不列字段。运行中代码遇到更高的 `FORMAT_VERSION` → `corrupt`
- **涉及文件**: ~~`src/reader3_app/reader3.py`（新写入函数，与 `save_to_pickle` 并列）；可能新增 `src/reader3_app/book_format.py`（待裁，§6 Q8）~~ ⬛ 2026-10-02（§6 Q8）：**新增 `src/reader3_app/book_format.py`**（格式、`BookManifest`、回读、三态分类、generation 发布 / 恢复 / GC）；`reader3.py` 的 `process_epub` 调它；`save_to_pickle` 留在 `reader3.py` 直到 pkl 日落
- **依赖**: ADR-0007（八步）、ADR-0009（Decision Outcome）、ADR-0003（`book_uuid` 是否并入 manifest，§6 Q3）
- **验收（种子）**:
  - （⬛ 2026-10-02，§6 Q7）改字段而不改快照 → unit lane 红；manifest 的 `FORMAT_VERSION` 高于代码所知 → 判 `corrupt`，不判 `valid`
  - （⬛ 2026-10-02，§6 Q8）原型的 `_remove_legacy` 不移植：发布不删任何已有文件；GC 比原型严格（ADR-0016 修订 3），各有一条断言
  - 八步每一步前后注入中断，目录状态只落在 `missing` 或 `valid`，永不 `corrupt`
  - 第 6 步回读校验失败 → 两个 tmp 删除、目录旧状态逐字节不变
  - 每章可按 manifest 的 `offset_bytes` / `length_bytes` seek 读出且 hash 相符
  - 测试矩阵：待 /tdd-guardian:design-tests

### WI-2: `book_fingerprint()` 落地（A1）

- **目标**: 实现 [附录 A 的 A1](../plan-tech-stack-migration.md) 指纹（原 EPUB hash、spine href/order、XHTML 原始内容 hash、~~解析器版本~~ `EXTRACTOR_VERSION`），写进 manifest；`notes.json` / chroma meta 各存所绑定的指纹。⬛ 2026-10-01（§6 Q13）：另加**逐条标注的解析状态**与重导入后的 **rebind 读改写**
- **涉及文件**: `book_store.py`、`reader3.py`、`notes_service.py`（⬛ 2026-10-01，Q13：rebind 读改写）、`vector_search.py`（`_stale_reason`）；⬛ 2026-10-01（§6 Q13）：`models/annotations.py`（`Annotation` 上的解析状态字段）、`web/routers/notes.py`。`notes.json` / API 的新字段按 ADR-0011 走加法式
- **依赖**: WI-1；ADR-0005 Revisit When（指纹与运行时重匹配并存还是取代，§6 Q4）；§6 Q13（bump 规则与 rebind）；ADR-0015（rebind 的锁顺序）
- **验收（种子）**:
  - 同一 EPUB 重处理两次指纹相等；改一个 XHTML 字节指纹变；只改空白折叠结果不影响 `chapter.text` 却改了 HTML 时指纹**必须**变
  - 指纹不匹配**不阻断** `load_book()`（A1 分级降级）
  - `NOTES_FINGERPRINT_KEY` 与 `tests/fixtures/deg_assertions.py` 的约定一致（键名若改，改那一处）
  - （⬛ 2026-10-01，§6 Q13）金样测试能发现一处已知的投影改动（每个 spine 项的 `text` 或 spine href/order）
  - （同上）`EXTRACTOR_VERSION = 0` 的书经 `--migrate` 原样带过，指纹不变
  - （同上）重导入后，唯一匹配的标注被 resolved
  - （同上）quote 在新章里出现两次的标注保留旧绑定、警告可见，书级指纹**不**前移；用户显式处置后前移
  - （同上）rebind 在 import 释放 EX 之后运行，按 SH 书锁 → notes 锁取锁，锁内重读当前 generation（并发测试）
  - 测试矩阵：待 /tdd-guardian:design-tests（含「无歧义匹配」的操作定义，Q13 留给矩阵）
- **WI-2a 遗留**（⬛ 2026-10-09，`ab48d54` 评审的 Low 项；不改代码，只记录）：
  - 指纹输入非法时抛 `ManifestError`（该类原义是「manifest 字节不是 manifest」），spine 为 `None` 时抛 `TypeError`；今天无此调用方
  - WI-4 / WI-7 之前，被索引的文本取自平铺的 `book.pkl`，索引记下的指纹取自 manifest 当前 generation，两者可能不同代
  - `GET /api/index/{id}/status` 透传 meta，因此多出 `book_fingerprint` 键（ADR-0011 加法）——012 合入 PR 正文的 API 一节注明
  - `book_store._FINGERPRINT_WARNED` 无上界、无重置钩子（实际以书数为界）
  - `reader3.fingerprint_components` 复制了章节循环的选取逻辑，由 R3-02 锁步测试钉住；WI-3 合并为同一迭代器
  - `tests/unit/test_extractor_projection_golden.py:292` 的字符串里有一个字面零宽空格，宜改写成转义
  - V7-06 按 logger 名（`reader3_app.book_store`）过滤日志，改 logger 名会无谓变红
  - `book_store.book_fingerprint` 的 `NotADirectoryError` 分支、`notes_service._existing_fingerprint` 的 `OSError` 分支无专门用例（行覆盖靠共用的 `except`）
  - `tests/e2e/acceptance_p3/test_deg_states_plain.py:27` 的注释仍说 `_stale_reason` 不看指纹——归 WI-8
- 本 WI 是否算 Phase 3 清单的隐含项：~~待裁，§6 Q9。~~ ⬛ 2026-10-02：是（§6 Q9 裁定），已补进 [Phase 3 任务清单](../plan-tech-stack-migration.md)。

### WI-3: 摄取双写 + 三态读取

- **目标**: `process_epub` 同时产出 pkl 与新格式；`storage_format()` 返回 `missing` / `corrupt` / `valid`（ADR-0007 读取状态机）
- **涉及文件**: `reader3.py`（`process_epub`、`_commit_staged_artifacts`、`_validate_staged_artifacts`）、`book_store.py`
- **依赖**: WI-1；ADR-0007「三产物场景的两条协议缺口」（⬛ 2026-10-02 已由 [ADR-0016](../../../adr/0016-generation-directory-publish.md) 取代：generation 布局下两条缺口在结构上不存在，下面第 1 条种子改为验证「每个钩子点只见旧／新、未引用代被回收、根目录用户数据不动」）
- **验收（种子）**:
  - 重写整本书的路径覆盖两条缺口：**回滚是 rename 不是 copy**（断言 `inode` 与 `mtime_ns`）；**中断后不留新产物挨着旧 marker**
  - 「保住用户数据」不退化成「什么都没改」：用户子树逐字节不变 **且** 新增文件集合恰好等于本次产物
  - `corrupt` 大声失败、不回退 pkl；`missing` 走 pkl、不告警
  - **损坏的 `book.pkl`** 在 `missing` 态下的阅读页表现有断言（[009 原 tests/23 附注](./009-e2e-annotations.md)：这一态等 012 定三态后补）
  - （⬛ 2026-10-08，§6 Q15 / WI-2a R6）章节循环跳过 spine 项（idref 悬空、非文档项）时 `order` 会出现空洞（`tests/unit/test_reader3_fingerprint.py` R3-04 实测 `[0, 2]`），而 `book_format._validate_inputs` 要求 `order == i`：本 WI 须二选一（重编号或放宽校验），且指纹组件的 `(href, order)` 与章节保持同步（R3-02 钉住）；R3-13（未接入 `process_epub`）在本 WI 按规则 12 翻转并写明理由
  - 测试矩阵：待 /tdd-guardian:design-tests
- 双写期产物是 pkl + manifest + chapters + `book.epub` + `images/`，全部写进 `gen/{g}/`，根 `manifest.json` 一次 `os.replace` 是唯一提交点——见 [ADR-0016](../../../adr/0016-generation-directory-publish.md)（§6 Q2，2026-10-02 裁定 B）。今天 `_commit_staged_artifacts` 最后一步 rename 的是 `book.pkl`（A 形状，012 退役）。

### WI-4: `book_store.py` 封装格式判断（含 `book_store` 之外的存储泄漏）

- **目标**: 按 A5 接口（`load_book` / `load_chapter` / `iter_chapters` / `chapter_count` / `book_fingerprint` / `storage_format`）封装，调用方无感知；缓存 key 覆盖新格式文件的 stat。
  **不止 `book_store.py` 本身**——今天有几处绕过它、直接以 `book.pkl` 为准，不收进来，新格式的书就在这些地方「不存在」或「永不失效」：
  - `search_service.list_book_ids`：书目枚举只收含 `book.pkl` 的目录（经 `_book_pkl_path`）
  - `search_service.load_book_index`：搜索缓存的 freshness 只 stat `book.pkl`
  - `web/routers/library.py` 的 `library_view`：按 `_data` 目录扫、逐本 `load_book_cached` 取标题
  - `vector_search.BookVectorIndex._load_book` 的直读留给 WI-7（与索引改造同批）
- **涉及文件**: `book_store.py`、`search_service.py`（`list_book_ids`、`load_book_index`）、`web/routers/reader.py`、`web/routers/library.py`；018 的列表 / 删书 / 导出路由若有同类直读，一并收口。⬛ 2026-10-02（§6 Q8）：`book_store` 新增 `resolve_generation(book_id)`（每次请求读一次指针），`storage_format` 调 `book_format` 的分类
- **依赖**: WI-1、WI-3；`tests/unit/test_server_patch_seam_ownership.py` 的接缝规则
- **验收（种子）**:
  - 同一本书在 `valid` 与 `missing` 两态下，经 `book_store` 读出的章节文本、标题、spine 顺序逐项相等
  - republish 为新格式后缓存失效（沿用 011 WI-3 的 freshness 断言形状）——**搜索缓存同样失效**（`load_book_index` 不再只看 pkl 的 stat）
  - 只有新格式、没有 `book.pkl` 的书出现在 `list_book_ids` 里
  - `src/` 下除 `book_store.py`、`reader3.py`（写入端与 legacy loader）外 grep 不到 `_book_pkl_path` / `"book.pkl"` 的读路径
  - `book_store` 仍不 import `reader3_app.web`
  - （⬛ 2026-10-09，§6 Q15 / WI-2b R-5）凡产出 `Book` 的加载路径都给 `Book.book_fingerprint` 赋值：新格式读到的书取 manifest 里的值，pkl-only 的取 `None`——否则 notes 被 rebind 盖上指纹后，ADR-0019 的跳过规则会让该书永久不判孤儿
  - 测试矩阵：待 /tdd-guardian:design-tests

### WI-5: 欠账 #35 —— `load_book_metadata()` 改读 manifest

- **目标**: 替换 `load_book_metadata()` 的函数体（接缝已由 011 留好，调用方不变）；`search_library` 与书库页改走它。
  018 的书目列表路由（#56）已经建在这条接缝上，本 WI 换的是它底下的实现，路由本身不动
- **涉及文件**: `book_store.py`、`search_service.py`（`search_library`）、`web/routers/library.py`；⬛ 2026-10-02（§6 Q10）：`tests/fixtures/synthetic_library.py`（及 `scripts/bench.py` 的 `_write_huge_book`）——bench 书库须按新格式落盘
- **依赖**: WI-4；018 已合入（#56 路由存在）；[011 §8 门槛 #7 裁定](./011-backend-refactor.md)（本 WI 是该裁定唯一的复审点）
- **验收（种子）**:
  - `tests/unit/test_book_store_metadata_seam.py` 的投影性质不改一字仍绿
  - `scripts/bench.py` 的 `05_library_search_1/2/3` 三步 `unpickle` 不再每轮 +20（[#35 验收列](./009-e2e-annotations.md#跨波欠账)）
  - 全仓 grep 不到「为取元数据而 `load_book_cached`」
  - 018 的列表路由返回的书名在本 WI 前后逐项相等（[#56 验收列](./009-e2e-annotations.md#跨波欠账)「书名与 `load_book_metadata()` 一致」换了实现仍成立）
  - （⬛ 2026-10-02，§6 Q10）`scripts/bench.py` 的合成书库按新格式落盘（或双写）——否则那些书判 `missing` 回退 pkl，C1 计数照旧，门槛 7 过不了
  - 测试矩阵：待 /tdd-guardian:design-tests
- #35 的优先级：~~待裁，§6 Q10。~~ ⬛ 2026-10-02（§6 Q10）：012 出口必需（门槛 7），Wave A 内 WI-4 之后做，不阻塞开工。~~#56 兑付方列的「与 #35 同批」一句不在本文改，由 [018 WI-1](./018-library-routes.md) 改。~~ ⬛ 2026-09-30：该句已由 [018 WI-1](./018-library-routes.md) 删去，#56 兑付方改为 018。

### WI-6: `reader3 --migrate <book_id>`

- **目标**: 原地读写、不复用摄取路径、专用 legacy loader、不改指纹（ADR-0009 Migration Strategy）
- **涉及文件**: `reader3.py`（`main` 的 argparse）、`book_store.py`
- **依赖**: WI-1、WI-2、WI-3；**018 的每书写协调契约**（迁移持该书的锁，与 import / delete / reindex 互斥）；（⬛ 2026-10-08，§6 Q15 / WI-2a R1）迁移的书计算指纹所需的逐项 XHTML 原始字节从该书 `book.epub` 的 zip 里取（不是从 pkl 的清洗后 HTML），`extractor_version` 按 Q13 ③ 带 0；（⬛ 2026-10-09，WI-2b R-5）迁移后的书首次加载时经 WI-4 的加载路径取得 `Book.book_fingerprint`
- **验收（种子）**:
  - 迁移后 `notes.json` / `ai_meta.json` / `chroma_db/` 三者**字节不变**，且 `book_fingerprint(book_id)` 前后相等
  - **崩溃注入**：八步第 7 步之后、第 8 步之前中断 → 重启后该书能打开（判 `missing`，走 pkl），下一次迁移干净重跑
  - **真实 iframe 标注迁移 E2E** 至少一条（[附录 A「最可能的失败模式」](../plan-tech-stack-migration.md)）：迁移前后同一标注恢复到同一段文字；比对 metadata、spine order/id/href、TOC 树、content hash、text hash
  - 不需要 `READER3_ALLOW_PICKLE=1` 即可迁移
  - 迁移进行中对同一本书删书 / 重建索引被锁挡住（按 018 契约的拒绝语义），且迁移不会把已删的目录重新建出来
  - 测试矩阵：待 /tdd-guardian:design-tests
- **`--migrate-all` 与未迁移库存清单也在本 WI**（§6 Q5）：WI-11 的「N+1 停写 pkl」以它们已发布为前提。验收补充：`--migrate-all` 逐本持锁、一本失败不中断其余、结束时打印未迁移清单；清单可单独查询（不迁移只列）

### WI-7: Chroma 索引重建改 generation swap（写侧 + 查询侧）

- **目标**: 新建 `reader3_book_<generation>` → 写满 → 校验 chunk count 与指纹 → 原子更新 `index_meta.json` 的 active collection → 删旧 generation。
  **这不是只改 `index_book` 内部**：今天 `index_book(force_reindex=True)` 在 upsert 之前就 `shutil.rmtree` 整个 `chroma_db/`（先毁后建），而 `_client_and_collection` 打开的是固定名 `COLLECTION_NAME`——
  查询、状态、删除走的都是它。generation 一旦按名字区分，**查询侧必须按 `index_meta.json` 的 active generation 选集合**，否则翻完指针后查询仍打在旧名（或空集合）上。
  另：`_load_book` 直接 `load_book_file(<book_dir>/book.pkl)`，改走 `book_store`（WI-4 留到这里）
- **涉及文件**: `vector_search.py`（`index_book`、`_client_and_collection`、`_load_book`、`_stale_reason`）；`book_format.py`（⬛ 2026-10-02，§6 Q8：import 其通用 generation 核心）；`web/routers/search.py`（单本重建路由 `api_index_book` 的错误映射若变）
- **依赖**: WI-2（指纹）、WI-4；ADR-0004；018 的每书写协调契约（重建持该书的锁）
- **验收（种子）**:
  - embedding 中途失败 / 进程退出 → 旧 generation 仍可查询，`index_meta.json` 未翻
  - 成功后旧 generation 被删；`index_meta.json` 指纹 = 当前书指纹
  - 翻指针后第一次查询命中新 generation（chunk 内容可区分新旧）；旧 generation 被删后查询不报错
  - 只有 `book.pkl` 被删、只剩新格式的书可以建索引
  - （⬛ 2026-10-08，§6 Q15 / WI-2a R3）012 之前建的索引 `index_meta.json` 没有 `book_fingerprint` 键，2a 起按「无法判断」不判 stale；本 WI 的重建写入指纹后这个缺口收口——加一条断言：无键旧 meta 经一次重建后带上当前书指纹，此后指纹不一致能判出 stale
  - 测试矩阵：待 /tdd-guardian:design-tests

### WI-8: DEG-S1–DEG-S4 朴素 Jinja 横幅

- **目标**: 现有模板里可见的朴素横幅；文案与触发条件**照抄**前端计划 WI-2–WI-5（[§3.1 两次交付](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md)）
- **涉及文件**: `web/templates/library.html`、`web/templates/reader.html`、`web/routers/library.py`、`web/routers/reader.py`；`tests/e2e/acceptance_p3/test_deg_states_plain.py`（删 skip 行）；`scripts/lint_e2e_groups.py` 的 `ACTIVATED_ACCEPTANCE_DIRS`；⬛ 2026-10-02（§6 Q11）：`tests/fixtures/deg_assertions.py`（`judge_deg_s4` 接受 010 的旧格式角标文案「旧格式」，去掉「须含 `pkl`」的要求；改正 `:116` 引着作废 `Literal["json", "pkl"]` 签名的陈旧注释）与 `tests/unit/test_deg_assertions_shared.py`（`:225` 「只写『旧格式』应失败」那条随之翻转）。两文件都不在冻结集（`soak_run.py` 的 `HASH_COVERED_PATHS`），改它们不需重跑批次；须在本 WI 解 skip 之前落。⬛ 2026-10-02 补：`tests/e2e/acceptance_p3/test_deg_states_plain.py` 的 `test_deg_s4_legacy_book_card_shows_storage_format_badge`（`:144-153`）文档串同样把判据写成「角标含 `pkl`」/「不含 `pkl`」，随 `judge_deg_s4` 一并改；`acceptance_p3/` 也不在冻结集
- **依赖**: WI-2、WI-3、WI-9、WI-10；设计规格 §6.4
- **验收（种子）**:
  - `-m acceptance_p3` 四条解 skip 并首次即绿，条数不变
  - 横幅由**主动制造**的降级条件触发（009 §0 第三条纪律），testid 与 `DEG_TESTIDS` 映射表逐个核对
  - `corrupt` 态在阅读页可见（ADR-0007 Negative）
  - 测试矩阵：待 /tdd-guardian:design-tests

### WI-9: 欠账 #54 —— DEG-S3 数据面

- **目标 / 验收**: 见 [#54 行](./009-e2e-annotations.md#跨波欠账)，不复述。加法式（ADR-0011）
- **涉及文件**: `web/routers/library.py`、`web/routers/reader.py`、`book_store.py`
- **依赖**: WI-3；`tests/fixtures/track_d_pinned_014.json`（014 WI-16b 删钉条时要能在真实数据上跑）
- 测试矩阵：待 /tdd-guardian:design-tests

### WI-10: 欠账 #55 —— DEG-S4 路由（书卡 `storage_format` / 迁移进度 / 单项重试）

- **目标 / 验收**: 见 [#55 行](./009-e2e-annotations.md#跨波欠账)。路由进 `routes.snapshot`
- **载体**: #55 验收要「书库数据每本带 `storage_format`」——书库数据的载体是 018 的书目列表路由（#56）。本 WI 在那条路由的每项上**加字段**（加法式），不另起列表
- **涉及文件**: `web/routers/library.py`（或 018 落的列表 router；新路由受 `check_router_size.py` 约束）
- **依赖**: **018 的 #56 列表路由已合入**；WI-3（三态）；WI-6（迁移进度要有 HTTP 可观察的迁移）。
  草稿曾把本 WI 排在 #56（旧 WI-15）之前，顺序是倒的；#56 移去 018 后该倒置自然消失
- 书卡角标取值域：~~待裁，§6 Q11。~~ ⬛ 2026-10-02（§6 Q11）：定义处是[前端计划 WI-5「角标的取值域」](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md)表（二值；`valid` / `corrupt` 不渲染），本 WI 照它实现、不复述。
- 测试矩阵：待 /tdd-guardian:design-tests

### WI-11: pickle 写路径日落计划

- **目标**: 钉死「停写 pkl」与「删 runtime fallback」两个版本号，写进~~代码/CHANGELOG~~代码常量（⬛ 2026-10-02，§6 Q12：`PICKLE_WRITE_SUNSET_VERSION` / `PICKLE_FALLBACK_REMOVAL_VERSION`，不建 CHANGELOG）并回填 ADR-0009；`READER3_ALLOW_PICKLE` 的开关语义按 ADR-0007 两个时间窗实现
- **涉及文件**: `docs/adr/0009-book-format-manifest-jsonl.md`、~~CHANGELOG（待裁，§6 Q12）~~ `src/reader3_app/book_format.py`（两个常量，⬛ 2026-10-02）、`pyproject.toml`（版本号）
- **依赖**: WI-3
- **验收**: ADR-0009 Decision Outcome 的「版本号未钉死」一句被替换为具体号；ADR-0009 Status → Accepted（其 Revisit When 第一条）；（⬛ 2026-10-02，§6 Q12）启动告警文案里的两个版本号来自常量（有测试断言）
- 不走 workflow（文档 + 版本号）

**Wave D（末波欠账）**

> 目标与验收的**定义处**是 [009 跨波欠账表](./009-e2e-annotations.md#跨波欠账) 对应行；本文只写依赖、012 独有的约束与验收补充。

### WI-12: 欠账 #52 —— 批量重建索引路由

- **目标 / 验收**: 见 [#52 行](./009-e2e-annotations.md#跨波欠账)。路由进快照（ADR-0011 新增流程，§6 Q1）
- **涉及文件**: `web/routers/search.py`（单本路由 `api_index_book` 旁，或新 router）；`frontend/src/settings/index.ts`（`wireDataActions` 的 `reindex` 由「暂不支持」换回真实请求——#52 的前端半边随本 WI）
- **依赖**: **WI-7**（批量必须走 generation swap；在今天「先 rmtree 再建」的实现上做批量，一次失败就是一本书没有索引，N 本就是 N 倍）；018 的每书锁
- **本 WI 须先定的三件事**（验收种子）:
  - **逐本进度**：N 本书各自的 `/api/index/{id}/status` 可观察，进度不是一个总百分比
  - **失败处理**：遇到失败是停还是继续——须裁定并写进契约测试；无论哪种，**已成功的书不回滚、失败的书旧 generation 仍可查询**（不累积损坏）
  - **重叠规则**：批量进行中再发一次批量、或对其中一本发单本重建 / 删书，按 018 锁的语义拒绝或排队，不得两路同时写同一本
  - 测试矩阵：待 /tdd-guardian:design-tests

### WI-13: 欠账 #57 —— 上传 / 导入路由

- **目标 / 验收**: 见 [#57 行](./009-e2e-annotations.md#跨波欠账)。验收写死「上传后书库出现该书**且按新格式落盘**」——这就是它留在 012 的原因
- **不是新增义务的部分**：`process_epub` 今天已经 stage → validate → commit（ADR-0007）。本 WI 不是「让上传走 ADR-0007」，而是在已有协议上补三件事：
  1. **新格式产出**：依赖 WI-3 双写——今天的 commit marker 仍是 `book.pkl`（`_commit_staged_artifacts` 最后一步），不满足 #57 验收
  2. **每书锁**：用 [018 WI-2](./018-library-routes.md) 的契约（`_staging_dir_is_owned` 为什么不能充当锁，写在那里）
  3. **上传边界**（沿 [ADR-0012](../../../adr/0012-security-boundaries.md) 的思路，新外部输入面）：临时文件用 `mkstemp`、有大小上限、目标书目录名过 `safe_book_folder`；同名书的 staging 仍被活进程持有时返回 **409**（以 `_staging_dir_is_owned` 判定；真正的互斥来自 018 的锁）（⬛ 2026-10-02：[ADR-0016](../../../adr/0016-generation-directory-publish.md) 退役同级 staging 与 `_staging_dir_is_owned`，409 的判定须改走 018 书锁，具体形式由本 WI 定）
- **涉及文件**: `web/routers/library.py`（或新 router）、`reader3.py`（`process_epub` 的调用方式，不改协议本身）
- **依赖**: **WI-3**；018 的每书写协调契约；ADR-0012
- **验收补充（种子）**: 非 EPUB / 超上限返回 4xx 且不留半成品目录与 staging；上传与同一本书的删书并发时，不出现「删掉的目录被上传重新建出」
- 测试矩阵：待 /tdd-guardian:design-tests

---

## 4. 出口闸

全部满足才算完。「证据位置」在核验时填，现在全部是占位。

| # | 门槛 | 判据 | 证据位置 |
|---|---|---|---|
| 1 | 新书不依赖 pickle | 删掉 `book.pkl` 后新处理的书可阅读 / 搜索 / 标注 / 建索引（含 WI-4 的枚举与缓存、WI-7 的 `_load_book`） | _待填_ |
| 2 | `--migrate` 保住用户数据 | WI-6 验收第 1 条（三件字节不变 + 指纹不变） | _待填_ |
| 3 | 崩溃注入矩阵 | **每个写手 × 每个提交点**都有注入测试，不只 `--migrate`：WI-1 八步发布（WI-1 验收）、WI-3 双写、WI-6 `--migrate`（WI-6 验收第 2 条）、WI-7 generation swap、WI-12 批量重建、WI-13 上传。每一格两种注入都要有：**进程内抛异常**（monkeypatch 提交点）与**真杀进程**（子进程跑写手，在提交点前后 `SIGKILL`——`finally` / 上下文管理器在这里不会执行，异常注入测不到这一类）。每格三条断言：① 书目录三态只落 `missing` 或 `valid`，永不 `corrupt`；② 注入点在提交点**之前** → 旧版本完整可读，注入点在提交点**之后** → 新版本完整可读（阅读 / 搜索 / 标注 / 语义查询）；任何一格都不出现新旧混合（例如新 `images/` ＋ 旧 `book.pkl`，见 [009 #59](./009-e2e-annotations.md#跨波欠账)），索引不出现「写侧已换、查询侧打空」；③ 不做人工清理直接重跑写手，收敛到与未中断一次跑完**相同**的结果（残留 staging 被 `_staging_dir_is_owned` 判为无主并清掉；⬛ 2026-10-02 起改为：未被 `manifest.json` 引用的 `gen/*` 按 [ADR-0016](../../../adr/0016-generation-directory-publish.md) 的安全 GC 回收）。矩阵写成一张表放进测试模块 docstring，缺格即不过 | _待填_ |
| 4 | 两条协议缺口 | WI-3 验收第 1、2 条（inode 断言；无新产物挨旧 marker）（⬛ 2026-10-02：缺口已由 [ADR-0016](../../../adr/0016-generation-directory-publish.md) 取代，此闸改验 WI-3 依赖行所述的等价断言） | _待填_ |
| 5 | 真实 iframe 标注迁移 E2E | WI-6 验收第 3 条 | _待填_ |
| 6 | DEG-S1–S4 可见 | `acceptance_p3` 解 skip 全绿；`lint_e2e_groups.py` rc=0 且 `ACTIVATED_ACCEPTANCE_DIRS` 含 `acceptance_p3` | _待填_ |
| 7 | 退役 011 门槛 #7 的 ⚠️ | bench C1：`05_library_search_*` 不再每轮 +20（#35） | _待填_ |
| 8 | 路由改动全部加法式 | `routes.snapshot` 的 diff 只有新增行，与代码同 commit；PR 描述写明破坏性与迁移路径（ADR-0011） | _待填_ |
| 9 | 全部 lane 在合并头上绿 | `.claude/tdd-guardian/config.json` 里**每一条** lane（不写死条数），带 `env -u FORCE_COLOR`；`/tdd-guardian:gate push` | _待填_ |
| 10 | 打包 | `packaging` lane（`tests/integration -m slow`）与 `lint.yml` 的 `wheel` job 绿 | _待填_ |
| 11 | 类型检查 | `uv run mypy src/` 干净（011 门槛 10 的闸仍在 unit lane） | _待填_ |
| 12 | router 体量 | `python3 scripts/check_router_size.py` rc=0（新路由不许挤爆 500 行） | _待填_ |
| 13 | 018 路由跨存储态 | 双写落地后，018 的列表 / 删书 / 导出三条路由在 **legacy（只有 pkl）/ 新格式 / 双写 / `corrupt`** 四种书目录上都有集成测试：列表不漏新格式书、不因 `corrupt` 书整页失败；删书对四态都删干净且缓存（含搜索缓存）不掩盖；导出不把 `corrupt` 当 `valid` | _待填_ |
| 14 | 每书锁被 012 的写手遵守 | `--migrate`（WI-6）、generation swap 重建（WI-7）、批量重建（WI-12）、上传（WI-13）都持 018 的锁；与删书并发的测试证明不会重建已删目录、不会发布进正在删除的目录 | _待填_ |
| 15 | Wave D 两条欠账 | WI-12 的逐本进度 / 失败处理 / 重叠规则有契约测试；WI-13 的新格式落盘与上传边界有测试；设置页 `reindex` 不再显示「暂不支持」 | _待填_ |
| 16 | e2e 分组与 soak 计数 | 新增的每条 e2e 都登记进 `scripts/lint_e2e_groups.py` 的分组（验收目录进 `EXPECTED_ACCEPTANCE_PER_DIR`，或模块进 `UNGROUPED_E2E_MODULES` 并同步 `EXPECTED_UNGROUPED_ITEMS`）；`scripts/soak_run.py` 由此派生 `EXPECTED_NONBASELINE_ITEMS`，`verdict` 要求 `-m baseline_1b` 的 deselected **恰好**等于它——漏登记一条，合入后下一次 soak 就判 red | _待填_ |
| F | ~~**冻结区零字节改动**~~ → **开工 `suite_hash` ＝ 最后一次通过批次的 `suite_hash`**（⬛ 2026-09-28 维护者裁定放宽，见本表下方注） | ~~下列 8 条路径 `git diff --stat master... -- <paths>` 为空，`suite_hash` 与 [`soak-log.md`](./soak-log.md) 表头冻结值一致：`tests/e2e/baseline_1b/**`、`tests/e2e/conftest.py`、`tests/e2e/helpers.py`、`tests/e2e/test_harness_smoke.py`、`tests/fixtures/epub_corpus.py`、`tests/fixtures/epub_zip.py`、`tests/fixtures/ai_stub.py`、`tests/conftest.py`。~~ **新判据**：012 开工 commit 算出的 `suite_hash` 与 [`soak-log.md`](./soak-log.md) 最后一次 10/10 通过批次所跑的 `suite_hash` 逐字相同；分支上若动了下列 8 条冻结路径，合入前须在合并头的新 `suite_hash` 上重跑一批并通过（批次规则见 [§7](../plan-tech-stack-migration.md)）：`tests/e2e/baseline_1b/**`、`tests/e2e/conftest.py`、`tests/e2e/helpers.py`、`tests/e2e/test_harness_smoke.py`、`tests/fixtures/epub_corpus.py`、`tests/fixtures/epub_zip.py`、`tests/fixtures/ai_stub.py`、`tests/conftest.py`。路径清单的定义处是 `soak-log.md`「`suite_hash` 的取法」与 `scripts/soak_run.py` 的 `HASH_COVERED_PATHS`，冲突以那里为准 | _待填_ |
| R | **红灯必查根因** | 分支存续期间，`baseline_1b` 与 e2e lane **每一次**红都在 §8「红灯记录」追一行：时间、commit、失败用例、根因（产品缺陷 / 测试缺陷 / 环境）、处置 commit。**不允许以「重跑变绿」结案**——重跑只用来复现，不用来消红。根因归「测试缺陷」且落在冻结集的，按 [§7](../plan-tech-stack-migration.md) ~~清零规则~~批次规则 2 / 3（⬛ 2026-09-28：批次终止，修复后在新 `suite_hash` 上重开一批）处理并如实记账，不得绕开。表为空或每行根因齐全才算过 | _待填_ |
| 17 | 欠账回写 | 009 表里兑付方为 012 的每一行（#35、#52、#54、#55、#57——届时 018 那一批已把另外四行改走）状态改为已结清（附 commit）或写明转出去向（那四行由 [018 WI-1](./018-library-routes.md) 改走、由 018 结清） | _待填_ |
| 18 | ADR 回写 | ADR-0009 → Accepted、compliance 更新；ADR-0007 compliance 更新；[ADR-0016](../../../adr/0016-generation-directory-publish.md) → Accepted、compliance 与 Confirmation 更新 | _待填_ |
| 19 | 合入前 CI 全绿 | PR 上 `pull_request` 触发的 `tests.yml` 与 `lint.yml` 全绿后才合入（PR 先开，CI 才会跑） | _待填_ |

- 不得设 `TDD_GUARD_BYPASS`。
- **⬛ 2026-09-28 维护者裁定：门槛 F 放宽。** 原文「冻结区零字节改动」的目的是保护数周积累的 soak 计数；
  [§7](../plan-tech-stack-migration.md) 改为批次规则后，重开一批只要 10–15 分钟，这份保护不再值那个代价。
  新判据只要求「开工时的 `suite_hash` 与最后一次通过批次一致」——冻结路径**可以改**，但**任何改动都需要一批新的 10 次**
  （外加机制挑战闸第 3 项对新 `suite_hash` 重跑，§7 批次规则 4）。连带：009 欠账 #49 现在可付（见 §2.3）。
  评审记录：[`review-soak-gate-20260928.md`](../review-soak-gate-20260928.md) §6 问题 2。
- **⬛ 2026-09-30：门槛 F 的「最后一次通过批次」收紧为「本分支开分支的那个 `commit` 上新跑的那一批」**——不论 `suite_hash` 变没变，都要新跑一批；机制闸第 1 项在同一 `commit` 上首次通过，第 3 项只在 `suite_hash` 变了时重跑。唯一定义处：[plan §7「012 开工核验」](../plan-tech-stack-migration.md#012-开工核验2026-09-30-维护者裁定)。
- **门槛 3 与 R 为什么是硬门槛**（2026-09-26 加，出自「跳过 soak 的代价评估」）：本分支引入的缺陷——崩溃安全发布、每书锁、generation swap、删书与写手并发——**天然是间歇性的**，表现与 flaky 测试无法区分。soak 证明的只是基线~~在一个本地剖面下攒到了 10 次绿~~（⬛ 2026-09-28：候选版本在一个本地剖面下跑通了一批 10 次）不是 flaky 率上界（[§7](../plan-tech-stack-migration.md) 批次规则 5）；所以「红了就重跑」会把真竞态藏进重跑里。门槛 R 管的是判读纪律，门槛 3 让崩溃安全不再只靠 E2E 当判官。
- `EXPECTED_BASELINE_ITEMS` 不许变——它一变就说明碰了冻结集。（⬛ 2026-09-28：门槛 F 放宽后碰冻结集本身不再禁止，但这条仍成立——改它等于改 `baseline_1b` 的条数，属于冻结集改动，须按门槛 F 新判据重跑一批。）（门槛 16 改的是验收 / 白名单两个常量，不是这一个。）
- #51 / #53 / #56 / #58 的兑付不在本表：它们的出口闸在 [018 §4](./018-library-routes.md)。门槛 13 / 14 只验「012 的改动没把 018 的路由与锁弄坏」；018 若按其 WI-6 挂起条款把 #53 转出，门槛 13 的「导出」一格标注不适用。

---

## 5. 风险

- **标注静默错位**：逐章文本相等 ≠ CFI 路径不变（附录 A「最可能的失败模式」）。缓解：WI-6 的 iframe E2E 是硬门槛，不是可选项。
- **指纹口径漂移**：WI-2 的指纹若把解析器版本算进去，任何 `reader3.py` 改动都会让全库标注判 stale。~~解析器版本号的 bump 规则：待裁，§6 Q13。~~ ⬛ 2026-10-01：缓解是 [§6 Q13](#6-开放问题) 裁定（指纹按 generation 存储、不重算；`EXTRACTOR_VERSION` 只在经评审的标注相关输出改动时 bump）。残余风险：解析器修复要等显式重导入才到达已在盘上的书——**已接受**。
- **双写期 marker 语义**：已裁定（§6 Q2 → [ADR-0016](../../../adr/0016-generation-directory-publish.md)）；pkl 写在每一代内部，「新 pkl 挨着旧 manifest」在 generation 布局下不可达。余下风险是漏改一处平铺路径站点（站点清单与 WI-4 grep 门见 ADR-0016）。
- **012 的写手漏持锁**：本分支新增三个写手（`--migrate`、generation swap 重建、上传）外加批量重建，任何一个不持 018 的每书锁，就会与删书竞争——把已删目录重新建出来，或把产物发布进正在删除的目录。缓解：所有写手只用 018 的契约，门槛 14 用并发测试证明。锁本身的失败模式（锁文件位置、不复活规则、与 notes 锁的顺序）归 [018 §5](./018-library-routes.md)。
- **索引查询侧漏改**：generation swap 只改写侧、`_client_and_collection` 仍开固定名集合，结果是「重建成功、查询打空」。缓解：WI-7 把查询侧写进目标，验收第 3 条可区分新旧 chunk。
- **存储泄漏在 `book_store` 之外**：`list_book_ids`、`load_book_index` 的 freshness、`_load_book` 直读 pkl——漏一处，新格式书就在那条路径上「不存在」或缓存永不失效。缓解：WI-4 验收的 grep 条。
- **soak 收集计数**：新 e2e 没登记分组，`soak_run.py` 的 deselected 精确比对就对不上，合入后 master 上下一次 soak 判 red（~~不是清零台账，但会让「全绿」断档~~ ⬛ 2026-09-28：会终止当时的批次，须查根因后重开，推迟 014）。缓解：门槛 16；合入前在分支上跑一次 `soak_run.py`（只核验、不 `--append`）。
- **冻结集诱惑**：`acceptance_p3` 的 fixture 在 `tests/fixtures/deg_assertions.py`（不在冻结集），但 e2e 的 `conftest.py` / `helpers.py` 在——任何「顺手改一下 helper」都会~~清零 soak~~让最后一次通过的批次不再覆盖当前套件、须重跑一批（⬛ 2026-09-28 门槛 F 放宽：代价变小，但仍不是零）。
- **router 体量**：`library.py` 已不小，#55 / #57 的新路由（加上 018 已加的）可能逼出新 router 模块。
- **磁盘峰值**：双写期 + staging 期间每本书约三份数据（ADR-0007 / ADR-0009 Negative）；generation swap 期间索引也是两份。

---

## 6. 开放问题

| Q | 问题 | 依据 | 状态 |
|---|---|---|---|
| D1 | #51–#53、#56–#58 的归属 | §2.2 | ✅ **已裁定（2026-09-26，用户裁定）**。来源：Fable 子代理裁定 ＋ Codex 复核（线程 `01a0daf3-7dd9-7120-aee4-d7e834502adb`）后的修正版。**结论**：#51 / #56 / #58 / #53 ＋ 每书写协调契约进新分支 `018-library-routes`（[§9](../plan-tech-stack-migration.md) M4a-债），soak 等待期内、012 之前做完；018 内 #58 只在锁落地之后落，#53 只在导出 schema（metadata / content / annotations 的覆盖面）定下之后落，否则在 018 内延后并写明 owner——**不回 012**。012 留 #57、#52 作末波。**理由**：#57 的验收写死新格式落盘，依赖 WI-3；#52 依赖 WI-7，且今天的单本重建是先毁后建、查询开固定集合名，批量叠在上面会放大损坏；其余四条不依赖新存储格式，放在 012 里只会让 M3→M4b 的串行链平白变长。**兑付方改写**：[018 WI-1](./018-library-routes.md) |
| Q1 | **ADR-0011 是否允许 012 新增路由？** | ADR-0011 Decision Outcome（`docs/adr/0011-api-v1-freeze.md:36`） | ✅ **已关（2026-09-26）**：允许。同一段写明「任何路由的增删改，两步都要做：先在同一个 commit 里改快照，再在 PR 描述里写明破坏性与迁移路径」——新增路由走这个流程即合规；「Phase 3 只能新增字段，不得改名、不得改语义、不得改默认值」约束的是**已有**路由的响应形状，不禁止新增路由。013 的 D11–D13 把冻结当作不加路由的理由，是 013 自己的范围决定，不是 ADR 的要求。落到本文即 §4 门槛 8 |
| Q2 | 双写期的 commit marker 是 `book.pkl` 还是 `manifest.json`？ADR-0007 写「012 之后仍是三件（`manifest.json` + `chapters.jsonl` + `images/`）」，没覆盖 pkl 与新格式**并存**的双写期 | ADR-0007 三产物缺口一节 | ✅ **机制已裁定（2026-10-02）：B**——每次发布写 `gen/{g}/`，根 `manifest.json` 一次 `os.replace` 是唯一提交点；A（平铺＋journal）否决。规范与四条修订见 [ADR-0016](../../../adr/0016-generation-directory-publish.md)；证据 [`evidence/q2-commit-prototype/REPORT.md`](./evidence/q2-commit-prototype/REPORT.md)，外部评审 2026-10-02。以下为 2026-09-26 的前序裁定（其「机制未定」部分已被上句取代）：marker 是 **`manifest.json`**，最后落。**机制未定**，由一个 WI-1 前的原型定：持久化恢复日志（Codex 的提议）还是 generation 目录 ＋ 单个指针原子换（协调者倾向，与 WI-7 的 generation swap 同构）。二者都要让「多个产物」变成「一个提交点」——今天 `_commit_staged_artifacts` 逐个替换、只有内存里的回滚，被杀即混版（[009 #59](./009-e2e-annotations.md#跨波欠账)）。无论选哪个都要写**取代 ADR-0007 的新 ADR**（其「跨设备 rename 降级为复制」一句顺带更正）；恢复必须先于 staging 清理。**PR #26 之后的现状**（[009 #59](./009-e2e-annotations.md#跨波欠账) 部分结清）：残留检测只能拒绝、不能恢复，且依赖今天的 staging 命名——新协议须沿用或显式退役；「回滚未能丢弃此前不存在的新产物」这一混版今天识别不了，新协议的落盘 marker 要覆盖它。来源：Codex（线程 `01a0dc02-d308-78f1-8750-8bcb9dacec06`）＋ Fable 子代理，维护者确认 |
| Q3 | `book_uuid` 是否并入 `manifest.json` | ADR-0009 Neutral、ADR-0003 Revisit When | ✅ **已裁定（2026-09-26）**：**不并入**，只留在 `ai_meta.json`。manifest 是可由 EPUB 重建的派生物，uuid 是身份；并进去后重建即换身份，或者重建要特意保留它——两份就会漂。018 Q12「删后重导入 = 新书」与此一致 |
| Q4 | 指纹比对与 ADR-0005 运行时文本重匹配：并存还是取代 | ADR-0005 Revisit When | ✅ **已裁定（2026-09-26）**：**并存**。指纹相等 → 跳过重匹配（快路径）；不等 → 走 ADR-0005 重匹配，**不**据此作废标注 |
| Q5 | `--migrate-all` / 未迁移清单归 WI-6、WI-11 还是后续版本 | ADR-0009 Decision Outcome | ✅ **已裁定（2026-09-26）**：都进 **WI-6**（见该 WI）。停写 pkl 之前用户必须有一条命令迁完整库 |
| Q6 | 日落版本号：ADR-0009 写「当前 `pyproject.toml` 版本 `1.4.0`」，今天是 `1.5.0`——ADR 的基线已过期，日落号要按哪个起算 | ADR-0009 Decision Outcome、`pyproject.toml` | ✅ **已裁定（2026-09-26，维护者）**：按 **minor** 节奏，从 **N = 发布 012 的那一版**（大概率 1.6.0）起算：N 双写；N+1 停写 pkl（前提：`--migrate-all` 已随某一版发布）；N+2 删 runtime fallback。ADR-0009 写「从 N 起算」，不写字面版本号；WI-11 在发版时把 N 填成实数 |
| Q7 | WI-1 的「字段冻结」是文档：写在 ADR-0009、`BookManifest` 的 docstring，还是 WI-1 自带的格式说明——哪一处是定义处 | WI-1、§3 分组表 | ✅ **已裁定（2026-10-02，维护者，按 reader-a4 建议）**：字段集合的定义处是**代码**——格式模块（Q8）里的 `BookManifest` dataclass 与 `FORMAT_VERSION` 常量，由 manifest schema 快照测试冻结；ADR-0009 只写版本规则（加可选字段不 bump；删 / 改名 / 改语义必 bump）并链接到符号，不列字段。附带裁定：**manifest 的 `FORMAT_VERSION` 高于运行中代码所知的版本 → 判 `corrupt`**，绝不静默判 `valid`。依据：ADR-0009 今天只在散文里点名字段（`docs/adr/0009-book-format-manifest-jsonl.md:33`）且 Accepted 后不可改；原型先例 `evidence/q2-commit-prototype/proto/common.py:19`、`:243`；落到 WI-1 |
| Q8 | 是否新增 `src/reader3_app/book_format.py`，还是写入器留在 `reader3.py` 与 `save_to_pickle` 并列 | WI-1 涉及文件 | ~~⏳ 待裁（同上）。owner：Q2 原型出结果时；最迟 012 开工核验前。⬛ 2026-10-02：触发条件已到——原型建议新增 `book_format.py`（[REPORT §10](./evidence/q2-commit-prototype/REPORT.md)），仍待维护者裁~~ ✅ **已裁定（2026-10-02，维护者，按 reader-a4 建议）**：**新增 `src/reader3_app/book_format.py`**，拥有格式、manifest、回读、三态分类与 generation 发布 / 恢复 / GC（通用 generation 核心作为文件内独立一节，WI-7 真正 import 之前不拆第三个模块）；`reader3.py` 只留 EPUB 解析并调用它，`save_to_pickle` 留到 pkl 日落。两处**不照搬原型**：原型的 `_remove_legacy`（`proto/mech_b_generation.py:20-22`）不移植（ADR-0016 修订 4，非破坏）；GC 比原型的 `_gc`（`proto/generation_core.py:94-102`）严格（修订 3）。依据：`reader3.py` 已 981 行；读侧与索引侧只需格式代码、不该 import 解析器；原型的无解析器部分 269 行（[REPORT](./evidence/q2-commit-prototype/REPORT.md)）。落到 WI-1 / WI-4 / WI-7 |
| Q9 | 今天 `src/` 里**没有** `book_fingerprint`（grep 零命中），而 Phase 3 验收把它当已有函数用——WI-2 是否算 Phase 3 清单的隐含项 | WI-2 | ✅ **已裁定（2026-10-02，维护者，按 reader-a4 建议）**：**是**，WI-2 是 Phase 3 的必需隐含项，留在 Wave A；已在 [Phase 3 任务清单](../plan-tech-stack-migration.md)补一行指向 WI-2。依据：`git grep book_fingerprint -- src` 零命中，而 Phase 3 验收「`book_fingerprint(book_id)` 不变」、A5 接口、DEG-S1/S2 的 stale 触发、WI-7「校验 chunk count 与指纹」都离不开它；只 hash EPUB 的桩违背 A1 hash 原始 XHTML 的理由。清单漏列是列表缺口，不是范围决定 |
| Q10 | #35 兑付方列写「012 开工时重新裁定优先级」——裁定后回写该格 | WI-5、[009 欠账表](./009-e2e-annotations.md#跨波欠账) | ✅ **已裁定（2026-10-02，维护者，按 reader-a4 建议）**：#35 **012 出口必需**（门槛 7），Wave A 内 WI-4 之后做（WI-5），**不阻塞开工**；已回写 [#35 兑付方列](./009-e2e-annotations.md#跨波欠账)。附带：WI-5 须把 bench 合成书库改按新格式落盘——今天 `scripts/bench.py:222-236` 经 `tests/fixtures/synthetic_library.py:115` 直接 pickle（`--huge` 那本另由 `bench.py:277` 直写），012 之后这些书判 `missing` 回退 pkl，`05_library_search_*` 照旧每轮 +20，门槛 7 过不了；`synthetic_library.py` 不在冻结集，改它不需重跑批次 |
| Q11 | 书卡角标取值域不是 `storage_format()` 三态（[A5 订正注](../plan-tech-stack-migration.md)），由 010 定义——核对 010 的定义处 | WI-10 | ✅ **已裁定（2026-10-02，维护者，按 reader-a4 建议）**：核对完毕，定义处是[前端计划 WI-5「角标的取值域」](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md)（二值：`valid` → 无角标；`missing` → 角标「旧格式」；`corrupt` → 无角标、书进 `lib-migrate-failed-item`），012 照它实现、不复述。附带发现 fixture 冲突：`tests/fixtures/deg_assertions.py` 的 `judge_deg_s4` 要求旧格式角标含 `pkl`，`tests/unit/test_deg_assertions_shared.py:225` 断言只写「旧格式」**应失败**，`deg_assertions.py:116` 的注释还引着已作废的 `Literal["json", "pkl"]` 签名——按 010 对齐 fixture，归 WI-8（见其涉及文件）。两文件都不在冻结集 |
| Q12 | 仓库根今天**没有** CHANGELOG，ADR-0009 却要求写进「代码/CHANGELOG」——新建还是只写代码常量 | WI-11 | ✅ **已裁定（2026-10-02，维护者，按 reader-a4 建议）**：**只写代码常量**，不建 CHANGELOG——格式模块里的 `PICKLE_WRITE_SUNSET_VERSION` / `PICKLE_FALLBACK_REMOVAL_VERSION`，ADR-0009 要求的启动告警打印它们，ADR-0009 链接到符号；面向用户的说明走发版 tag 消息。依据：仓库根无 `CHANGELOG*`，`git grep CHANGELOG` 只命中 ADR-0009 与本文；已发的 tag（`v1.0.0`–`v1.5.0`）从未用过 CHANGELOG；常量是唯一被读取的那一份（Q6 的 N / N+1 / N+2），另写 CHANGELOG 是第二份不被读的副本 |
| Q13 | 解析器版本号的 bump 规则（WI-2 指纹若含解析器版本，任何 `reader3.py` 改动都会让全库标注判 stale） | WI-2、§5 指纹口径漂移 | ~~⏳ 待裁（同上）。owner：WI-2 开工前~~ ✅ **已裁定（2026-10-01，维护者，reader-a4 草案经 Codex 修订；修订处以 Codex 为准）**：① **指纹随每个 generation 存储**（写在该代 manifest 里）并从那里读取，按该代记录的产物校验，**绝不用当前提取器重算**。② **`EXTRACTOR_VERSION` 在标注相关输出（每个 spine 项的 `text` ＋ spine `(href, order)`）有经评审的改动时 bump**；`tests/fixtures/epub_corpus` 上的金样测试须能发现**已知**改动，但**不是唯一判据**——语料没覆盖到的改动评审者也可以 bump（草案里「bump 了却没改输出 → 红」那一腿因此删去）。③ **`EXTRACTOR_VERSION = 0` = 未知旧提取器**，不证明等价；`--migrate` 从 pkl 复制已解析投影、**不重解析**，保留其指纹（版本 0），合 ADR-0009 迁移硬约束。④ **重导入逐条评估标注**，要求**无歧义**匹配；歧义或未解决的标注**保留旧绑定、警告保持可见**。逐条的解析状态是必需的，逐条存指纹可选。⑤ **书级 notes 指纹只在全部标注 resolved、或用户显式处置之后前移**（取代草案「重匹配后整书 rebind」——今天后端接受章节内任意位置的 quote（`server._annotation_matches_chapter_text`），前端 `findRange` 回退到首个出现处，孤儿不再复评（`routers/notes.py`），整书 rebind 会在标注仍错位时清掉 DEG-S1）。⑥ **rebind 是 notes 读改写**：import 释放 EX 之后，先取 SH 书锁、再取 notes 锁（ADR-0015 顺序），锁内重读当前 generation，原子保存完整 payload。⑦ **接受的代价**：解析器修复不会修好已在盘上的书，要显式重导入。「无歧义匹配」的操作定义（例如 prefix＋quote＋suffix 经同样的空白折叠后在新章 `text` 中恰好出现一次）留给 design-tests 矩阵；后端评估不能原样复用 `_annotation_matches_chapter_text`。来源：reader-a4 的 Q7–Q13 准备稿 Q13 修订节（工作区产物，未入库）＋ Codex 复核 §1。落到 [PLAN A1](../plan-tech-stack-migration.md)、WI-2、§5 |
| Q14 | WI-1：起点为 `corrupt` 的书再发布时，是拒绝还是修复 | ADR-0016 第 0 步、ADR-0007 三态、Q7 附带裁定 | ✅ **已裁定（2026-10-08，用户，经 reader-delegator 转达）**：**按版本拆分**。① **拒绝、零写入**（`BookCorrupt`）：可读的 `format_version` 高于 `FORMAT_VERSION`（合 Q7 附带裁定，新版本的书不能被旧代码改写）；实现另把三种「无法安全修复」的形状并入此类——`manifest.json` 是目录、`gen` 是符号链接或不是目录、`manifest.json.tmp` 是目录（最后一种 GC 也只跳过、不删）。② **其余 corrupt 起点修复**（版本 ≤ 当前、不可解析、缺版本字段、产物缺失或尺寸不符）：在 EX 锁内**跳过 GC**，写 `gen/{max(盘上规范代号, 可读 manifest.generation)+1}/`，经第 1–8 步提交，覆盖旧的 `manifest.json.tmp`；既有 `gen/*` 与根目录封闭清单内的用户数据逐字节不动，残留等到书恢复 `valid` 后的下一次 GC 再回收。验收：`tests/unit/test_book_format_publish.py`（每种 corrupt 形状修复到 `valid` ＋ 用户数据不变 ＋ 残留保留；高版本零写入拒绝），`tests/unit/test_book_format_crash_matrix.py` 场景 S5（修复路径的进程内注入与真 SIGKILL）。落到 WI-1 |
| Q15 | WI-2：「无歧义匹配」的操作定义、标注解析与 `_mark_orphans` 的关系、WI-2 是否拆分 | Q4、Q13、ADR-0005、`server._annotation_matches_chapter_text`（`server.py:538-554`）、`routers/notes.py:77-150`、前端 `findRange`（`annotations.js:268-282`） | ✅ **已裁定（2026-10-08，用户确认；依据 Codex ＋ Fable 两路评审，协调者综合）**。**匹配（新匹配器，不复用 `_annotation_matches_chapter_text`；旧匹配原样不动）**：M-1 两边都用 `"".join(s.split())` 去掉**全部**空白——前端 DOM 文本 `word1` 与后端 `get_text(separator=' ')` 的 `word 1` 在跨行内标签处必然不一致，只折叠不去除会让严格规则成批误判；M-2 草堆 = **锁内**当前 generation 里**同一 `chapter_index`** 那一章的 `text`（不走按 mtime/size 缓存的 `load_book_cached`）；M-3 针 = 先拼接 `prefix + quote + suffix` 再整体去空白；M-4 用 `find` 逐位前进数**可重叠**出现次数，数到 2 即短路，不用 `str.count`；M-5 恰 1 次 → `resolved`，≥ 2 → `ambiguous`，0 → `unmatched`，去空白后 quote 为空 → `unmatched`；M-6 prefix 与 suffix 皆空时针退化为 quote，仍须恰 1 次；M-7 `ambiguous` / `unmatched` 不改任何旧绑定字段，只写解析状态；每条标注持久化**绑定的指纹**与**评估时的指纹**。**严格（④）**：针计数为 0 即 `unmatched`，quote 本身唯一也**不**算 `resolved`。**范围（⑤）**：v1 只看同一 `chapter_index`；「按 href 跟随」记遗留。`Annotation` 新增加法字段 `chapter_href`，创建时由后端从 `book.spine[chapter_index]` 取，旧数据为空、`from_dict` 给常量默认——日后「跟随」不依赖上一代 manifest。**`_mark_orphans`（⑥）**：notes 绑定的指纹 ≠ 当前书的指纹（`Book` 须带出指纹）时整段跳过——不判孤儿、不过滤，与 Q4「指纹不等时重匹配不得判失效」对齐，并堵住 GET 在 notes 锁前取 `Book`（`routers/notes.py:140`）、并发导入后拿旧书粘性误判的竞态（补并发测试）。**不做** Q4 的「指纹相等即跳过重匹配」快路径（会破坏 `test_scenarios.py:112-135`）。已是孤儿的旧记录不复活、不计入「全部 resolved」。新写一份短 ADR（下一空号，Proposed，随 012 合入翻转）记 Q4 ＋ Q13 ＋ 本跳过规则，作 ADR-0005 的**扩展**而非取代（ADR-0005:65），ADR-0005 状态行加带日期的注并同步索引——随 WI-2b 首个 commit。**拆分**：WI-2a（指纹）/ WI-2b（逐条解析状态 ＋ rebind ＋ 处置路由 ＋ ADR）；导入后的 rebind 钩子挂到 **WI-3** 验收项。附加：每次保存 notes 都保留顶层 `book_fingerprint`（键名 = `NOTES_FINGERPRINT_KEY`）；2a 给 manifest 加**必需**字段、**不**升 `FORMAT_VERSION`（`book_format.py` 模块注释只豁免可选字段，理由「格式尚未发布」写进 commit message 与代码注释）；原始 XHTML 的 sha256 ≠ `ChapterIndexEntry.sha256`，迁移书从 `book.epub` 的 zip 取原始字节（记为 WI-6 依赖）；处置路由（接受当前绑定 / 删除）新开、不复用 PUT（PUT 的 `note_text` 必填），带 `If-Match` 与 `book_uuid` 快照，与 `routes.snapshot` 同一 commit；「接受当前绑定」对 `unmatched` 标注的含义写明：跳过结束后下一次 GET 可能将其判为孤儿；`resolution` / `chapter_href` 进 `to_dict` 会使现有 ETag 整体变一次——接受，在 commit message 注明。**遗留**：后端判 `resolved` 不等于前端高亮落在正确位置（`findRange` 精确 `indexOf`、失败退回首个出现处）——在 [009 欠账表](./009-e2e-annotations.md#跨波欠账) 新立一条，兑付方 014。落到 WI-2a / WI-2b / WI-3 / WI-6 <br>**WI-2a 细则（2026-10-08，协调者裁定）**：R1 字段名全线 `book_fingerprint`；manifest 只存摘要 ＋ `extractor_version`（摘要输入**仍含**原 EPUB sha256，只是不另存——它就是 `book.epub` 产物条目的 sha256；逐项原始 hash 推后，日后作可选字段加入不 bump）；必填新字段不 bump `FORMAT_VERSION`，理由「format not yet released — no v1 manifest exists outside this branch」写进代码注释与 commit message。R2 `book_store.book_fingerprint(book_id, books_dir) -> str | None`：missing（只有 pkl）与 corrupt 都返回 None，corrupt 每本书只记一条 WARNING；None =「无法判断」：不判 stale、不阻断 `load_book`、不推进 notes 指纹；「corrupt 大声失败」归 WI-3 的三态读取。A5 签名已在附录 A 带日期注订正。R3 012 之前的 chroma meta 无指纹键 → 不判 stale（WI-7 验收收口）。R4 指纹不一致是**软 stale**：`status()` 保持原 `status` 值（不改成 `not_indexed`，C9），只加 `stale: true` ＋ `stale_reason: "fingerprint"`，`semantic_search` 照常返回（DEG-S2「结果可能不全」）；既有原因仍是硬 stale、照旧拒绝查询，两者并存以硬为准。R5 notes 的首次盖指纹推到 2b；2a 只保住已有的顶层键。R6 指纹的 spine 项与章节循环完全一致，`order` = spine 下标；order 空洞的冲突写进 WI-3 验收。R7 金样 `tests/unit/snapshots/extractor_projection.json`，只能手动 `--regenerate`，测试不得自动重生成。指纹组件取 `item.content` 原始字节（不是 `get_content()`，后者经 lxml 重新序列化），由 zip 级对照测试钉住。 |

---

## 7. 欠账

本分支新立的欠账（兑付方指向后续分支的）。继承来的欠账不在这里，在 [009 表](./009-e2e-annotations.md#跨波欠账)。

| # | 欠什么 | 欠账方 | 兑付方 | 验收怎么查 | 状态 |
|---|---|---|---|---|---|

---

## 8. 合入记录

_未合入。合入后本节是「012 是否在主干上」的唯一定义处，格式照 [011 §8 合入记录](./011-backend-refactor.md)。_

### 红灯记录（门槛 R）

分支存续期间 `baseline_1b` / e2e lane 的每一次红追一行。「重跑变绿」不是根因。

| 时间（UTC） | commit | 失败用例 | 根因类别 | 根因 | 处置 commit |
|---|---|---|---|---|---|
