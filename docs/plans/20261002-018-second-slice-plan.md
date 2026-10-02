# 018 第二段（WI-4 – WI-8）执行计划

- **状态**: 草案；§6 开放问题已于 2026-10-02 由维护者裁定（Q-B 按推荐，其余按默认），2026-10-02 Codex 计划评审 NEEDS REVISION，本版逐条处置（§8；H1 由维护者裁定，落为 [ADR-0018](../adr/0018-project-root-conversations-take-book-lock.md)，Proposed），复审后开工
- **日期**: 2026-10-02
- **基线**: `master` `fa9a4fe`（相对 `babaf59` 只改了 `docs/` 与一个 skill，`src/` / `tests/` / `scripts/` 零差异，下文行号仍有效）。分支 `018-library-routes` 停在 `42c0728`，没有领先 commit，落后 `master` 10 个（`command git log master..018-library-routes` 为空，`command git rev-list --count 018-library-routes..master` = 10），开工时先 fast-forward 到 `master`
- **定义处**: WI-4 – WI-8 的目标、涉及文件、验收种子、出口闸、裁定**只在** [`tasks/018-library-routes.md`](20260816-tech-stack-migration/tasks/018-library-routes.md)；执行顺序**只在** [进度盘](20260824-frontend-backend-plan-progress.md)；锁契约**只在** [ADR-0015](../adr/0015-per-book-write-coordination.md)（已 Accepted；project-root 对话例外由 [ADR-0018](../adr/0018-project-root-conversations-take-book-lock.md) 取代，Proposed）。本文只回答**怎么做好**，不复述上面这些
- **为什么现在做**: 012 的 WI-5 / WI-10 建在 #56 列表路由上，014 WI-16b 等着 #56 / #58，而每书锁（`book_lock`）合入 `master` 以后还没有一条路由持**独占**锁（删书是第一个；共享锁已经在用：`api_index_book` 经 `BookVectorIndex.index_book` 的 `writer_scope`（`vector_search.py:322`），notes / 对话 / `ai_meta` 的写路由同理）。维护者 2026-10-02 定的顺序是：先做完本段（018 WI-4 – WI-8）→ 再跑 [012 开工核验](20260816-tech-stack-migration/plan-tech-stack-migration.md#012-开工核验2026-09-30-维护者裁定) → 再开 012

> 引用规则沿用任务书（用符号名定位）。本文的 `file:line` 是 2026-10-02 在 `babaf59` 上 grep 到的（`fa9a4fe` 上代码相同），只用来证明「现状」，行号会漂，执行时以符号为准。

---

## 1. 现状核对（2026-10-02，`babaf59` ＝ `fa9a4fe` 的代码）

### 1.1 已有、可直接用的

| 东西 | 位置 | 对本段的意义 |
|---|---|---|
| 元数据接缝 `load_book_metadata` | `src/reader3_app/book_store.py:150`（函数体 `:176` 仍是全量读后投影）；`BookMetadataView` 只有 `book_id` / `title` / `authors`（`:115`） | WI-4 的唯一数据来源。`cover_url` 和 `book_uuid` 不在这个 view 里，见 §3 WI-4 |
| 书锁 API | `book_lock.acquire(books_dir, folder, *, mode, holder, deadline, budget)`（`book_lock.py:306`）、`writer_scope`（`:538`）、`read_book_uuid`（`:517`）、`CATEGORIES`（`:62`，已经有 `delete`） | WI-5 用 `acquire(mode="exclusive", holder="delete")`；独占写手不等待，拿不到直接拒绝 |
| 锁异常到 HTTP 的映射 | `web/book_lock_http.py`：`BookLockBusy` 映射成 409 ＋ `Retry-After`，`BookChanged` 映射成 409，`BookGone` 映射成 404（`:20-41`）；在 `server.py:341` 安装 | 删书路由抛异常就行，状态码不用自己拼 |
| 现成的独占写手可以照抄 | `reader3.py:743`（`process_epub`，`mode="exclusive", holder="import"`） | WI-5 的取锁形状照这里写 |
| 书库枚举 | `search_service.list_book_ids`（`:250-262`，只收 `_data` 后缀**且**有 `book.pkl` 的目录）；`_validate_book_id`（`server.py:492`）经它判断 404 | WI-4 的条数、WI-5 的 404 都以它为准 |
| uuid 批量解析 | `server._book_uuids_or_none`（`server.py:475`），`library_view` 在线程池里调它（`routers/library.py:76`） | WI-4 的 `book_uuid` 字段直接复用，不另写 |
| 封面挑选 | `library_view` 里内联实现（`routers/library.py:47-63`，直接读 `images/` 目录，没有经过 `Book`） | WI-4 的 `cover_url` 要用同一套规则 |
| 集合锁 | `collections_service._collections_write_lock`（`:84`，`library_collections.json.lock`） | WI-5 第 3 步用；**没有**「把一本书从所有集合里移除」的函数（`:171-254` 只有按集合操作的函数），要新加 |
| 统计缓存 | `server._stats_cache`（`server.py:291`）；`api_library_stats`（`routers/library.py:317`）在事件循环里同步算完再写回（`:335`），没有代次 | WI-5 第 5 步失效它；只清字典挡不住「删书前开始的计算在删后写回旧值」，见 §3 WI-5 |
| 项目级对话根 | `server._project_conversations_root`（`server.py:1009`）：`dirname(BOOKS_DIR)` ＋ `conversation_project_root_dir`（默认 `conversations`，`ai/config.py:42`），只收相对、不含 `..` 的路径，否则返回 `None`；可以是指向别的卷的符号链接 | Q-B 的搬家目标；不能写死 `conversations/` |
| chromadb 进程内 system 缓存 | `SharedSystemClient._identifier_to_system`（chromadb 1.3.7，`api/shared_system_client.py:14`；公开的只有清全部的 `clear_system_cache`，`:90`）；`BookVectorIndex._drop_index_for_rebuild` 的 docstring（FX-1-18）记录了「rmtree 后同路径再开 client 拿到死句柄」 | WI-5 删掉 `chroma_db` 后，同一进程里「重导入 → 索引」会撞上它 |
| 加书进集合 | `api_collections_update_books`（`routers/library.py:179`）在集合锁**外**用 `_validate_book_id` 验书，`update_collection_books`（`collections_service.py:254`，锁在 `:261`）锁内不再验 | 与删书交错时，成员可能在删书移除之后才落下，同名重导入继承它（违反 Q12），见 §3 WI-5 |
| 路由冻结 | `tests/contract/routes.snapshot` 共 64 行，`test_route_inventory.py:54` 做集合比对；[ADR-0011](../adr/0011-api-v1-freeze.md) Accepted：「改快照与改路由同一 commit」 | 新路由与快照必须在同一 commit |
| router 规矩 | `routers/__init__.py` docstring 要求 `from .. import server as _server` 写在**文件末尾**；`tests/unit/test_router_import_independence.py:39` 的 `ROUTER_MODULES` 要与 `server.py:1157-1183` 的 include 列表一致 | 每加一个 router 模块要改三处 |
| SIGKILL 注入范式 | `tests/unit/test_process_epub_sigkill_recovery.py:100-155`（子解释器给 rename / rmtree 挂钩子，再给自己发真 SIGKILL） | WI-5 的提交点前后崩溃测试照这个写 |
| 等着用的前端 | `frontend/src/settings/index.ts:700-703` `wireExport`：`set-export-json` 只显示「导出书库 JSON 暂不支持」；e2e `tests/e2e/shell_4a/test_settings_rows.py:272-275`（在 `test_key_never_echoed_and_exports` 里）钉住了「暂不支持、0 个请求」。书库页 `frontend/src/library/index.ts:114` 读的是服务端渲染出来的 `.book-card[data-book-id]`，不调列表 API | FB-S06 属于本段（WI-6）；书库页改成从服务端取书目属于 014 WI-16b |

### 1.2 缺的（用 grep 核过：`src/` / `tests/` / `scripts/` 里都没有）

- `library_books` / `library_export` 模块、`delete_conversations`、墓碑 `.deleted-` 一律零命中。`routes.snapshot` 里与书库相关的只有 `GET /api/library/stats`（`:29`）
- `load_book_metadata` 在 `src/` 里只有定义处提到（`book_store.py:109` 的注释、`:150` 的定义）
- `scripts/soak_run.py` 里没有 `GITHUB_ACTIONS` 和 `is-ancestor`；`--append` 目前只要求工作树干净（`:1148`）
- `soak-log.md` 里还没有「CI 运行记录」一节
- `BookUuidResolver` 只有私有方法 `_forget`（`ai/books.py:296`），没有公开的失效入口

### 1.3 任务书的漂移：开工当天改进任务书（本文不改）

| # | 位置 | 任务书原文 | 实际情况 → 修正 |
|---|---|---|---|
| D1 | WI-2「契约」整段、§4 门槛 7 | 「ADR 转 Accepted 的那个 commit 把本段换成一行链接」 | ADR-0015 已经 Accepted（`0015…md:5`），但 WI-2 的契约正文还原样留在任务书里，等于两处定义。→ 把契约正文换成一行链接到 ADR-0015（「搬，不抄」） |
| D2 | WI-4 涉及文件、§5 router 体量 | `library.py` 已 333 行 | 现在是 339 行。→ 改数字，或者干脆删掉这个数字（`check_router_size.py` 才是判据） |
| D3 | WI-4 接缝守卫测试 | 只点名 `test_no_production_call_site_uses_the_new_seam_yet` | 测试在 `tests/unit/test_book_store_metadata_seam.py:490`，断言 (a) 在 `:526`，(b) 在 `:530`，与任务书一致。但还漏了两处：`book_store.py:109-111` 的注释「Nothing consumes the seam in this branch」也要改；测试名里的 `_yet` 改写后含义会变 → 建议改名为 `test_seam_callers_are_the_allowlist` |
| D4 | WI-4 / WI-5 / WI-6 | 没有写路由路径 | 前端计划把列表路由叫 `/api/library`（`plan-frontend-ui-refactor.md:432`、`:1321`），删书和导出的路径没人定过。→ 见 §6 Q-A |
| D5 | WI-5 第 6 步、§6 Q8、ADR-0015 Neutral | 「对话保留为孤儿」 | 默认存储模式是 `per_book`（`ai/config.py:41`、`server.py:1003`），对话放在 `{book}/ai_conversations/`（`ai/conversations.py:45-47`），**就在书目录里面**。第 7 步 `rmtree` 墓碑会连对话一起删掉，`delete_conversations=false` 的保留承诺在默认模式下做不到。→ 见 §6 Q-B（**冲突，要裁定**） |
| D6 | WI-5 第 5 步 | 「失效 `BookUuidResolver` 映射」 | 没有公开 API（见 1.2）。→ 涉及文件里补上「`BookUuidResolver` 加一个公开的 `forget_folder`」 |
| D7 | WI-5 第 3 步 | 「在全局集合锁下移除」 | 要新加一个函数，比如 `collections_service.remove_book_everywhere`。→ 写进涉及文件 |
| D8 | WI-7 目标 1 | 「`tests.yml` 的 `e2e` job 头注释两句没跟上」，§7「该补偿至今没有建出来」 | 两处都已经修了：`tests.yml:154-156` 现在写的是「也跑在每个向 `master` 开的 PR 上」；plan §7 那段（`plan-tech-stack-migration.md:502`）已经标注「本段是…快照，已过期」。→ WI-7 只剩「核验 ＋ 记录」两项，目标 1 标成已完成 |
| D9 | WI-6 验收 | 没提到旧 e2e | `test_key_never_echoed_and_exports` 的最后三行（`test_settings_rows.py:272-275`）断言的是「暂不支持」。WI-6 要把它**反过来**，这是有意地重新判一条测试，不是放宽。→ 写进 WI-6 验收 |
| D10 | WI-5 墓碑清扫 | glob `books/.*.deleted-*/` | 合法的书目录名可以以点开头、并且以 `_data` 结尾（比如 EPUB 叫 `.x.deleted-1.epub`），会被这个 glob 误收。`reader3.py:282-299` 的 `_is_own_staging_name` 为同类问题吃过亏。→ 判据改成严格正则 `^\.(?P<folder>.+_data)\.deleted-(?P<pid>\d+)(-[0-9a-f]+)?$`，并且要求目录名**不以 `_data` 结尾** |
| D11 | 头部「节奏」 | 「WI 严格按号串行」 | 本段让 WI-8 第一个做（§2）。WI-8 只碰 `scripts/soak_run.py` 与它的单测，与 WI-4 – WI-7 无共享文件。→ 「节奏」加一句例外：「WI-8 可提前，其余按号」 |
| D12 | WI-5 删除顺序、墓碑清扫 | 第 4 步改名即提交点；清扫只看墓碑 | 只有墓碑时，「提交点后、对话搬走前」崩溃会让清扫把对话连同墓碑删掉，`delete_conversations` 的选择丢了。→ 第 4 步之前加「写删除意图文件并 `fsync`」；第 5 – 7 步收进一个幂等的终结器，请求与清扫共用；清扫也在每次导入（`process_epub`）取锁前跑。细节见 §3 WI-5，涉及文件补 `reader3.py` |
| D13 | WI-5 第 3 步、§6 Q12 | 集合成员在提交点前移除 | 加书进集合在集合锁外验书（§1.1），能在第 3 步之后落下。→ 终结器再移除一次（幂等），加书改为在集合锁内复核书目录；涉及文件补 `web/routers/library.py`。第 3 步保留（ADR-0015 第 8 条的顺序不变） |
| D14 | WI-5 第 5 步 | 三处进程内缓存 | 漏了 chromadb 的进程内 system 缓存（§1.1）。→ 第 5 步加「退役该书 `chroma_db` 路径的 chromadb system」，涉及文件补 `vector_search.py` |
| D15 | WI-5 验收「删书与单本重建并发 → 一方 409」 | 一方 409 | 只对一种次序成立：重建先持共享锁 → 删书 409；删书先持独占锁 → 重建在 2 秒预算内等到删书结束，锁内复核得 `BookGone` → 404（删书超过 2 秒才是 409）。→ 两种次序分别写 |
| D16 | WI-5 第 6 步、Q8 | 「对话保留为孤儿」 | 按 Q-B 与 [ADR-0018](../adr/0018-project-root-conversations-take-book-lock.md) 改写；涉及文件里的 `ai/conversations.py` 范围扩到 `save_project_conversation` 与 `save_conversation_multi` |
| D17 | WI-7 目标 2 / 3、§4 门槛 9 | 合并头上 dispatch；记录进 `soak-log.md` | 记录 commit 本身会移动合并头。→ 记录挪到合入后的回写 commit（§7），PR 头即被 dispatch 的那个 SHA，见 §3 WI-7 |
| D18 | WI-8 涉及文件 | 只有 `soak_run.py` 和它的单测 | `test_soak_run.py` 里已有的 `--append` 子进程用例（`:219`、`:226`、`:904`，都在 `cwd=REPO_ROOT` 下跑）在 CI（`GITHUB_ACTIONS`）和未合入的分支 SHA 上会被新拦截拒掉。→ 验收补「这些用例在两种环境下仍绿」，见 §3 WI-8 |
| D19 | WI-6 验收、§6 Q-G | 「损坏的书以 WI-4 的错误态出现」 | 没说书中途消失、`notes.json` 坏、对话文件坏各怎么办。→ 按 §3 WI-6 的分部件策略写进验收 |

---

## 2. 切分与顺序

```
WI-4 (#56 列表) ──► WI-5 (#58 删书) ──► WI-6 (#53 导出 + FB-S06)
                                               │
WI-8 (--append 硬拦截，独立) ──────────────────┤
                                               ▼
                                     WI-7 (#31 对账，最后做；要用到最终头)
```

- **WI-4 → WI-5 → WI-6 必须串行**：三者都改 `routes.snapshot`、`server.py` 的 include 列表和 `ROUTER_MODULES`，WI-5 / WI-6 复用 WI-4 的错误态和字段集。并行做只会在这三个文件上撞车。
- **WI-8 和谁都不冲突**：只碰 `scripts/soak_run.py` 和 `tests/unit/test_soak_run.py`。建议**第一个做**，当热身，同时让后面的 lane 运行都带上它。这与任务书「WI 严格按号串行」相悖，例外记在 D11。
- **commit 粒度**：每个 WI 一个 red commit（测试）＋ 一个 green commit（实现，路由和快照同在这个 commit）；WI-5 的 green 可以拆成几个 commit，但**`DELETE` 路由（router、`include_router`、`ROUTER_MODULES`、`routes.snapshot` 那一行）只在最后一个 commit 出现**，那时意图文件、终结器、清扫、缓存失效、chromadb 退役、项目级对话加锁都已就位；之前的 commit 只加 HTTP 够不着的服务层函数和它们的测试。任何中间 SHA 上都不存在「有提交点、没有恢复」的可调用路由。门槛 8 要求「每条欠账一个 commit 结清」：009 表的状态改动随该 WI 最后一个 commit 一起提交。
- **建议用一个实施会话，不开两个**。理由：(1) 主线是严格串行的；(2) WI-8 大约 50 行改动，为它开 `/coordinate` 平行会话，分配、检查点、合并的成本比活本身还大；(3) 一个会话里 WI-5 能直接看到 WI-4 的错误态形状，不用靠文档转述。
- **WI-8 要不要单独拆一个 PR：不拆**。它是 018 自己的范围（§6 Q10），拆出去要在 §9 新分配编号，还要多跑一轮 CI。它跟着本段合入还有一个好处：012 开工核验的那一批 `--append` 是它上线后第一次真跑，正好在开 012 之前就用上了。代价是 PR 里混了一个与书库无关的 commit，PR 描述里分节写清楚即可。

---

## 3. 逐 WI 执行要点

> 测试矩阵按 [任务书 §3](20260816-tech-stack-migration/tasks/018-library-routes.md#3-工作项) 的规定交给 `/tdd-guardian:design-tests`，再经 `tdd-spec-adversary` 攻一轮。下面只写**怎么证明测试能咬人**和**容易出错的地方**。

### WI-8：`--append` 硬拦截（[定义](20260816-tech-stack-migration/tasks/018-library-routes.md#wi-8-soak_runpy---append-硬拦截)）

- **测试**: 单元测试放在 `tests/unit/test_soak_run.py`。git 用一个真的临时仓库，造出 `origin/master` 和一个分叉 commit，比打桩 `subprocess` 更可信；`GITHUB_ACTIONS` 用 `monkeypatch.setenv` 设置。
- **红灯检查**: 把新判据整段注释掉，四条用例里「拒绝」那两条必须红；把 `is-ancestor` 换成「分支名等于 master」，「detached worktree → 放行」那条必须红。
- `origin/master` 解析不出来时（没 fetch、没有 remote）的默认处理：拒绝，并提示先 `git fetch origin master`。宁可误拒，不可误收。
- **判定的位置**：放在 `main` 里现有的「合成 summary 不许落进 canonical 台账」判定**之后**（`:454`、`:482`、`:512` 三条拒绝用例断的是它的退出码和措辞），在 `--no-precheck` 分支**之前**、与它无关——`--no-precheck` 只跳过工作树检查，跳不过本拦截。红灯检查加一条：把拦截挪进 `if args.parse_summary is None or not args.no_precheck:` 块里，「`--no-precheck` ＋ `--append` 在 CI 环境下 → 拒绝」必须红。
- **已有子进程用例**（D18）：`_synthetic_append_argv` 的三处调用（`:219`、`:226`、`:904`）今天在真仓库、真环境里跑。改法交给 design-tests，约束三条：(1) 子进程的 env 显式去掉 `GITHUB_ACTIONS`；(2) git 判据走一个可注入的仓库（临时 git 仓库，造出 `origin/master` 祖先关系），不读真仓库的分支状态；(3) 这个注入口只在台账是仓库外临时文件时生效（复用 `synthetic_append_refusal` 的判据），不能被用来往 canonical 台账写。验证：整份 `test_soak_run.py` 分别在 `GITHUB_ACTIONS=true` 下、以及在一个未合入 SHA 的 detached worktree 里各跑一次，全绿。

### WI-4：#56 列表路由（[定义](20260816-tech-stack-migration/tasks/018-library-routes.md#wi-4-欠账-56--客户端书目列表路由)）

- **测试**: 契约测试放在 `tests/contract/`，新建 `test_library_books_route.py`，用 `contract/conftest.py` 的临时书库。损坏条目用**真的损坏 `book.pkl`**，不打桩 `server.load_book_cached`。原因：新路由走的是 `book_store.load_book_metadata`，它在 `book_store` 内部解析 `load_book_cached`（见 `test_server_patch_seam_ownership.py:233-245` 的注释），打桩 server 那一侧拦不到，测试会假绿。
- **红灯检查**: 让路由跳过损坏条目（不输出错误态），条数断言必须红；让路由直接读 `book.pkl` 绕开接缝，改写后的接缝守卫测试必须红（白名单只放新模块）。
- **字段从哪来**: `title` / `authors` 来自 `load_book_metadata`；`book_uuid` 用 `_server._book_uuids_or_none`，放进线程池跑；`cover_url` 把 `library.py:47-63` 的挑选逻辑**抽成一个函数**，`library_view` 和新路由共用（默认放在 `book_store`，见 §6 Q-C），保证与服务端渲染的书库页逐字节一致。条数以 `list_book_ids` 为准。书在枚举之后消失（`FileNotFoundError` / `BookGone`）按 Q-G 跳过，WI-6 用同一条规则（§3 WI-6）。
- **快照**: 新路由、`routes.snapshot` 加一行、`ROUTER_MODULES`、`server.py` 的 include 列表，四处放在同一个 green commit。`test_route_contracts.py:214` 的 `LIBRARY_CASES` 加 200 那一行。

### WI-5：#58 删书（[定义](20260816-tech-stack-migration/tasks/018-library-routes.md#wi-5-欠账-58--删书路由wi-2-之后)，锁规则见 [ADR-0015](../adr/0015-per-book-write-coordination.md) 第 1、2、4、8 条与 [ADR-0018](../adr/0018-project-root-conversations-take-book-lock.md)）

- **锁怎么用**: 一次删书在线程池里只取一次 `acquire(mode="exclusive", holder="delete")`，取不到就抛 `BookLockBusy`，HTTP 层按已有映射回 409。锁内复核书目录：不在就抛 `BookGone`，回 404。提交点与终结器都在这一次持锁里完成。删书过程中**不再**取任何别的书锁；集合锁属于全局资源，按「书锁 → 资源锁」的顺序在书锁之内取。
- **清扫在取目标锁之前**（任务书「每次删书开始前」，D12）：先跑清扫，清扫对每个墓碑**各取各的**独占锁（按墓碑名解析出的书目录名），处理完即放；然后才取本次删书的目标锁。这样同名墓碑与本次目标不会在同一调用栈里重复取同一把锁（ADR-0015 第 7 条）。同一个清扫函数还在 `_startup_scan_books`（`server.py:344-349`）和 `process_epub` 取锁之前（`reader3.py:743` 之前）各调一次，后者保证同名重导入之前，上一本的终结器一定跑完（Q12）。
- **状态机**（D12；提交点仍是一次 rename，ADR-0015 第 8 条的顺序不变，只是第 5 – 7 步收进终结器）:
  1. 锁内复核后、提交点前，在 `books/` 下写**删除意图文件** `.{folder}.deleted-{pid}-{8hex}.intent.json`（`mkstemp` ＋ `fsync` ＋ `os.replace` ＋ `fsync` 父目录），内容：`delete_conversations`、`book_uuid`（`read_book_uuid`，可为 `None`）、删时解析出的项目级对话根的绝对路径。根解析为 `None`（`conversation_project_root_dir` 配成了绝对路径或 `..`）且 `delete_conversations=false`、书里又有 `ai_conversations/` → 提交点前 500，书完好，意图文件删掉
  2. 集合移除（任务书第 3 步，保留）
  3. 提交点：书目录 rename 为同后缀的墓碑 `.{folder}.deleted-{pid}-{8hex}`，`fsync` 父目录
  4. **终结器** `finalize_tombstone(墓碑, 意图)`，每一步幂等、可从任何一步重入：(a) 再做一次集合移除（D13）；(b) 失效进程内缓存：`_stats_cache` ＋ 代次加一、`BookUuidResolver` 的新公开 `forget_folder`（D6）、退役该路径的 chromadb system（D14）；(c) 对话（见下）；(d) `rmtree` 墓碑；(e) 最后删意图文件
  - 清扫的判定：墓碑 ＋ 意图 → 跑终结器；只有意图、没有墓碑 → 提交点前崩溃，书完好，删意图文件；只有墓碑、没有意图（不应出现）→ 按 `delete_conversations=false` 跑终结器，宁可多留不可多删。D10 的正则不匹配 `.intent.json` 结尾的名字，两类文件各有各的正则
- **对话（Q-B ＋ ADR-0018）**，按**磁盘上实际有什么**决定，不看当前存储模式（模式可能在建对话之后改过）:
  - `delete_conversations=true`：删墓碑里的 `ai_conversations/`（随 `rmtree`）＋ 意图里那个根下的 `{book_uuid}/`
  - `false`：把墓碑里 `ai_conversations/*.json` **逐个文件**发布到 `{意图里的根}/{该文件自己的 book_uuid 字段}/`（字段缺失时退回意图里的 `book_uuid`；两者都没有 → 按 Q-B 丢弃并记日志）。每个文件：目标里没有 → 在目标目录 `mkstemp` 写入、`fsync`、`os.replace`、`fsync` 目录；目标里已有（`both` 模式必然如此）→ 只在源的 `last_updated` 严格更新时覆盖，否则保留目标——与读路径 `_dedupe_conversation_list` 的取舍一致，用户看到的历史不变。不用目录 rename：它既合并不了已存在的 `{uuid}/`，跨卷时又会 `EXDEV`（根可以是指向别的卷的符号链接，§1.1）；逐文件复制发布对同卷、跨卷一样成立。(c) 全部成功之前，(d) 不许 `rmtree`
  - **迟到写入**：项目级写手按 ADR-0018 持该书共享锁并在锁内复核书目录。提交点之后书目录已不在，任何迟到的项目级保存（含 `both` 模式）都得 `BookGone` → 404，`{root}/{book_uuid}/` 不会在 `delete_conversations=true` 之后被重建；终结器还没跑完（崩溃后、清扫前）时同样如此
  - **「按 `book_uuid` 找得到」指的是磁盘**：保留下来的对话在 `{配置的根}/{book_uuid}/{conversation_id}.json`。现有的 HTTP 读路由（`api_ai_list_conversations` / `api_ai_get_conversation`，`routers/ai/conversations.py:31`、`:48`）先经 `book_uuid_resolver.folder_for_book_uuid` 解析活书，删书后对孤儿一律 404。本段不加孤儿的 HTTP 入口（§6 Q-H），WI-6 的导出也只覆盖活书
- **提交点之后的失败**（Q-F 补充）：提交点一过，删书在用户看来已经发生——终结器任何一步失败都只记日志、留下墓碑 ＋ 意图交给下一次清扫，响应仍是 204。客户端重试 `DELETE` 得 404，应按「已删」处理（014 WI-16b 的确认框据此写）。提交点之前的失败（409 / 404 / 500）书完好，可原样重试
- **统计缓存的代次**：`server` 加一个整数代次。`api_library_stats` 在开始计算前读代次，写回前若代次已变就不写缓存（本次结果照常返回）；删书在终结器 (b) 里清字典并把代次加一。只清字典挡不住「删书前开始的计算在删后写回旧值」
- **chromadb 退役**：把该书 `chroma_db` 路径对应的 system 从 `SharedSystemClient._identifier_to_system` 里拿掉并 `stop()`；这是 chromadb 1.3.7 的私有属性，所以同时加一条测试钉住它的存在（升级时先红在这里）。退而求其次是公开的 `clear_system_cache()`（清全部，别的书下次打开时重建 system），实现时按真测试选，不靠推理
- **加书进集合**（D13）：`update_collection_books` 接受一个「书目录存在」判据，在集合锁**内**对每个 `add` 复核；不在 → 404。锁序不变：加书只取集合锁，删书取书锁 → 集合锁，没有环。加书的复核要么落在终结器 (a) 之前（成员随后被移除），要么落在提交点之后（看不到目录 → 404）
- **测试分层**:
  - 单元测试 `tests/unit/test_library_delete.py`：状态机顺序、意图文件、终结器每一步的幂等重入、清扫三种判定、D10 正则、`delete_conversations` 两个取值 × 磁盘上（只有 per-book / 只有项目级 / 两边都有且新旧不同）三种布局、根是跨卷符号链接（用 `os.replace` 打桩出 `EXDEV` 证明不走目录 rename）、统计代次的重叠（计算里放一个 barrier，删书在 barrier 处插入，断言缓存里不是旧值）
  - 跨进程测试，沿用 `test_book_lock_cross_process.py` 的 `Holder` 范式，**两种次序**分别写（D15）：重建先持共享锁 → 删书 409、书完好；删书先持独占锁 → 重建等待后 404、目录不被重建出来。另加：删书持锁时项目级对话保存 409；删书（`true`）后项目级保存 404 且 `{root}/{book_uuid}/` 不存在；`both` 模式两次写入之间（钩子停在 per-book 写完处）删书拿不到独占锁
  - 竞态测试：加书进集合与删书交错（钩子停在集合锁外的验书之后），断言删后集合里没有它；随后同名重导入，新书不在任何集合里（Q12）
  - chromadb 真测试（不打桩）：同一进程里索引 → 删书 → 同名重导入 → 索引 → 查询，全部成功
  - SIGKILL 测试：照 `test_process_epub_sigkill_recovery.py:100-155`，杀在：意图写入前、意图写入后提交点前、提交点后终结器前、对话搬家进行中（第 k 个文件之后）、搬家完成 `rmtree` 前、`rmtree` 进行中；每个点 × `delete_conversations` 两个取值，重启跑清扫后断言：提交点前的点书完好且无残留意图；提交点后的点书不在、墓碑与意图都清掉、`false` 时每个对话文件都在根下、`true` 时根下没有该 uuid
  - 契约测试：在 `LIBRARY_CASES` 里加 204 / 404 / 400 / 409 四行
- **红灯检查**（每条至少一个变异）: 把提交点的 rename 换成直接 `rmtree`，「提交点前崩溃 → 书完好」必须红；不写意图文件（清扫一律当 `false`），「`true` ＋ 提交点后崩溃 → 根下没有该 uuid」必须红；清扫在对话搬完之前 `rmtree`，「`false` ＋ 搬家中崩溃」必须红；终结器去掉 (a)，集合竞态测试必须红；去掉统计代次判断，重叠测试必须红；去掉 chromadb 退役，真测试必须红；项目级写手去掉 `writer_scope`，迟到写入测试必须红；清扫改成「先探测锁、放掉、再删」，Codex 那个剧本必须红；清扫的 glob 换回 `.*.deleted-*`，D10 的那个合法书目录被删，必须红。
- **e2e：本段不加**。删书的 UI 属于 014 WI-16b，本段的验收在契约测试和跨进程测试这一层就能闭合。这样门槛 6（e2e 分组登记）对 WI-5 不适用，也从根上避开了 [任务书 §5](20260816-tech-stack-migration/tasks/018-library-routes.md#5-风险) 的「e2e 污染共享语料」风险。如果维护者坚持要一条 e2e，就照任务书 WI-5 的 e2e 条款：独立书库、独立服务（参照 `tests/fixtures/deg_assertions.py:297` 的 `pickle_fallback_server`），新 fixture 放进非冻结的 `tests/fixtures/` 模块。
- **墓碑名**: `.{folder}.deleted-{pid}-{随机 8 位十六进制}`。只用 pid 不够：同一个服务进程里「删书 → 重新导入 → 再删」时，如果上一次的墓碑还没清完，第二次 rename 会撞名（见 §6 Q-D）。

### WI-6：#53 导出 ＋ FB-S06（[定义](20260816-tech-stack-migration/tasks/018-library-routes.md#wi-6-欠账-53--书库导出)）

- **测试**: 契约测试放在 `tests/contract/test_library_export_route.py`，覆盖：缺省请求不带对话也不带正文；`?include=conversations` 时带对话；损坏的书以 WI-4 的错误态出现；响应里不出现 API key（复用 `test_settings_rows.py` 的 secret 扫描思路）。Vitest 新建 `frontend/tests/settings/export.test.ts`，覆盖：导出中按钮 `disabled`、失败时可见。e2e 只**原地反转** `test_key_never_echoed_and_exports` 的最后三行（D9），断言变成「发出 1 个请求，下载的内容是合法 JSON」。这样 `shell_4a` 的条数不变，`lint_e2e_groups.py` 不用动。
- **红灯检查**: 让路由在缺省请求下也带上对话，第一条必须红；前端恢复「暂不支持」，反转后的 e2e 必须红。
- **边界的默认做法**（任务书说「本 WI 自定」）: 一次性 `JSONResponse` 加 `Content-Disposition: attachment`，不做流式，不设大小上限。单用户、本地部署，按宪法第 2 条 YAGNI。读侧不取锁，与 ADR-0015 / ADR-0016「读者不取锁」一致。
- **一个响应形状、分部件的失败策略**（D19）：每本书一条，条目就是 WI-4 的列表条目（含其错误态）再加 `annotations`，`?include=conversations` 时再加 `conversations`；条目里加一个 `component_errors` 列表（字段名由 design-tests 定，语义如下）。
  - 书在枚举之后消失（`FileNotFoundError` / `BookGone`，任何部件读到一半都算）→ **整条跳过**，与 Q-G、WI-4 同一条规则，不出错误态
  - `book.pkl` 读不出 → 整条是 WI-4 的错误态，其余部件不读
  - `notes.json` 坏（`load_annotations` 抛 `NotesFileError`，`notes_service.py:16`）→ 书照常导出，`annotations` 为 `null`，`component_errors` 记 `annotations`
  - 对话文件坏：今天的 `_list_conversations_from_dir` 会**静默跳过**坏文件（那里有 FIXME(011)）。导出不能沿用这个静默——读对话时把读不出的 `conversation_id` 收集起来记进 `component_errors`，读得出的照常导出
  - 整次导出只在枚举本身失败时 500

### WI-7：#31 收尾对账（[定义](20260816-tech-stack-migration/tasks/018-library-routes.md#wi-7-欠账-31--ci-e2e-job-收尾对账最后做)）

- 按 D8，只剩「核验 ＋ 记录」。门槛 1 / 9 要的是**合并头**，不是「最后一个代码 commit」（D17）：
  1. 分支冻结：PR 头 `H = $(command git rev-parse 018-library-routes)`，此后不再推任何 commit（包括记录）
  2. `gh workflow run tests.yml --ref 018-library-routes`，然后 `gh run view <id> --json headSha` 必须等于 `H`（dispatch 跑的是触发那一刻的分支头，不核对就可能跑在别的 SHA 上）；`e2e` job 绿且 `attempt=1`。PR 上 `pull_request` 那次运行的 `headSha` 也必须是 `H`
  3. 合并用 `gh pr merge --merge --match-head-commit H`，分支头若被动过就拒绝合并；动过了就回到第 1 步
  4. run id、`H`、Chromium 版本记进 `soak-log.md` 新开的「CI 运行记录」一节——放在**合入后的回写 commit** 里（§7），不进 PR，所以不移动合并头
- **绝不** `--append`（[coordinate-bindings](../../.claude/skills/coordinate-bindings/SKILL.md) EXTRA_ORDERS 第 3 条；WI-8 合入后由机器拦截）。

### 贯穿全段的约束

- **冻结集零改动**: 8 条路径以 `scripts/soak_run.py:154-163` 的 `HASH_COVERED_PATHS` 为准。最诱人的两个陷阱：往 `tests/fixtures/epub_corpus.py` 里加一本测试书，或者往 `tests/e2e/conftest.py` 里加 fixture，两者都在冻结集里。每个 CP 跑一次 `command git diff --stat master... -- <8 条路径>`，结果必须为空。说明一下代价：023 已经把 `suite_hash` 改成了 `abfc0cc9c59e`，我在 `soak-log.md` 里没有找到第 3 项对这个值的通过记录，所以 012 开工核验本来就要跑「新批次 ＋ 第 3 项」。本段碰了冻结集也不会**多出**一道流程，但会让 B2 不再能作对照、多一份风险。所以规矩不变：零改动。
- **共享 e2e 语料**: 本段只有 WI-6 原地改了一条 `shell_4a` 测试，不新增 e2e，`baseline_1b` 一个字节不碰。
- **前端**: 本段只做 FB-S06（`frontend/src/settings/index.ts` 的 `wireExport`）。书库页从服务端取书目、删书按钮和确认框，属于 014 WI-16b（[任务书 §2.3](20260816-tech-stack-migration/tasks/018-library-routes.md#23-前端半边归属本节是定义处)）。

---

## 4. 闸与检查点

出口闸以 [任务书 §4](20260816-tech-stack-migration/tasks/018-library-routes.md#4-出口闸) 为准，本文不复述。lane 定义见 `.claude/tdd-guardian/config.json`：commit 闸是 `unit`（`tests/unit tests/contract` ＋ 覆盖率）和 `fe-unit`（`npm test`）；push 闸是 `e2e`（`scripts/e2e_lock.py` 包装，`BUSY` = 75 表示环境繁忙，不代表代码有问题）和 `packaging`。

| CP | 时点 | 要过的 | 对应 §4 门槛 |
|---|---|---|---|
| CP0 | 开工前 | 分支 fast-forward 到 `master`；§1.3 的漂移已改进任务书；§6 的开放问题已裁定；基线 commit 闸绿 | — |
| CP1 | 写第一行生产代码之前 | WI-8 / WI-4 / WI-5 / WI-6 的测试矩阵（`design-tests` ＋ adversary）已入库或在 tdd-guardian 产物里；red commit 已提交，并且确实是红的 | 7 的删书部分（矩阵里要能看到「不复活」「409」「两种次序」「每个崩溃点 × 两个取值」） |
| CP2 | WI-5 green 之后（中点） | commit 闸绿；`mypy`、`ruff`、`check_router_size.py` rc=0；冻结集 diff 为空；`routes.snapshot` 的 diff 只有新增行；由 `checkpoint-verifier` 在这个 SHA 上独立重跑 | 2、3、4、5、F |
| CP3 | 准备合并 | push 闸绿（`e2e` ＋ `packaging`）；WI-7 的两次 CI 都绿且 `headSha` 都是冻结的 PR 头（§3 WI-7）；009 表 #53 / #56 / #58 / #31 已结清；红灯表为空或每一行根因齐全；PR 描述写明 ADR-0011 的破坏性（加法式、无破坏）；`soak_run.py` 只核验、不 `--append`，deselected 精确相等 | 1、5、6、8、9、R、11 |

门槛 10 已经被开工核验取代，不再单独做。门槛 7 的 ADR 转正已经完成，本段只需要把 ADR-0015 的 compliance 改成 Full（见 §7）。

---

## 5. 风险（只列任务书 §5 之外的）

- **默认模式下的对话误删**（D5）：照任务书原文实现，用户在默认配置下删一本书，会连对话一起丢掉，和「默认保留」的承诺相反。Q-B 已裁定（2026-10-02，锁内搬到项目级目录），WI-5 的测试矩阵必须含「默认模式删书后对话文件在 `{配置的根}/{book_uuid}/` 下」一条（是磁盘上找得到，不是 HTTP，见 §3 WI-5）。
- **清扫和新书抢锁**：删书 → 同名重新导入 → 启动时清扫旧墓碑，清扫要持新书那把独占锁。大的墓碑 `rmtree` 期间，新书上的共享写手（比如保存笔记）会在 2 秒预算内拿到 409。按 ADR-0015 这是可以接受的拒绝，但前端要能保住未保存的内容（这本来就是契约第 4 条的要求）。
- **chromadb 私有属性**：退役用的是 `SharedSystemClient._identifier_to_system`（§3 WI-5），chromadb 升级可能改掉它。钉它的测试会先红；退路是 `clear_system_cache()`。
- **012 的 GC 清扫入口和 018 的墓碑清扫各写一份**：[ADR-0016](../adr/0016-generation-directory-publish.md)「安全 GC」(b) 也是「启动时 ＋ 非阻塞独占锁 ＋ 拿不到就跳过」。本段把清扫写成一个函数（比如 `library_sweep.sweep_on_startup`），在 `server._startup_scan_books`（`server.py:344-349`）、每次删书取锁前、`process_epub` 取锁前调用，012 往里面加 GC 一步，不另起入口。

---

## 6. 开放问题（⬛ 2026-10-02 维护者裁定：Q-B 采用推荐默认，Q-A、Q-C – Q-G 一律采用推荐默认；Q-H 是评审后新增，待裁定）

> 下表「推荐默认」一列即为裁定结果。Q-B 改变了任务书 Q8 的实际语义，开工当天随 §1.3 的漂移一并写进任务书 Q8。

| Q | 问题 | 推荐默认 | 理由 |
|---|---|---|---|
| **Q-A** | 三条路由的路径 | `GET /api/library`；`DELETE /api/library/{book_id}?delete_conversations=false`；`GET /api/library/export?include=conversations` | 前端计划已经用 `/api/library` 这个名字（D4）。与 `GET /api/library/stats` 方法不同或路径不同，不冲突；`book_id` 必须以 `_data` 结尾，`stats` 不可能被当成书 |
| **Q-B** | `per_book`（默认）/ `both` 模式下，`delete_conversations=false` 怎么兑现（D5） | ⬛ 评审订正（不改裁定本意）：目标是**配置的**项目级根（`server._project_conversations_root`），不是写死的 `conversations/`；逐文件复制发布而非目录 rename；按磁盘上有什么决定、不看当前模式；进意图文件、由终结器执行；项目级写手加锁见 [ADR-0018](../adr/0018-project-root-conversations-take-book-lock.md)。机制以 §3 WI-5 为准。原文：在提交点（第 4 步）**之后**、`rmtree`（第 7 步）**之前**，在锁内把墓碑里的 `ai_conversations/` 搬到项目级目录 `{project_root}/conversations/{book_uuid}/`（与 `project_root` 模式的目录布局相同，`ai/conversations.py:55-59`），没有 uuid 时就地丢弃并记日志；`project_root` 模式什么都不用做 | 这样能兑现 Q8「默认保留为孤儿」的本意，孤儿仍然只按 `book_uuid` 引用（Q12 / ADR-0015 第 6 条）。另一个选项是「`per_book` 模式下没带 `true` 就拒绝删书」，实现更简单，但会让 014 的确认框多一个分支。**这条要维护者拍板**，它改的是 Q8 的实际语义 |
| **Q-C** | 封面挑选函数放哪 | `book_store`，作为一个独立函数，**不**放进 `BookMetadataView` | ADR-0016 列出的平铺路径站点里有 `library.py:49`（封面 `images`），012 WI-4 会把这类站点收进 `book_store`，再用 grep 门挡住其他地方。现在放进 `book_store`，站点少一个；放进 view 就等于替 012 扩了接缝，任务书 WI-4 明令不许 |
| **Q-D** | 墓碑名要不要加随机后缀 | 要：`-{pid}-{8hex}`；清扫正则见 D10 | 同一进程删两次同名书会撞名；ADR-0015 第 1 条只说「墓碑 `.{id}.deleted-{pid}/`」不进书库，没有规定确切格式，属于 WI-5 自己的实现细节，不需要改 ADR |
| **Q-E** | 墓碑清扫用哪个持有者类别 | 用现有的 `delete`，不新增类别 | `CATEGORIES` 是封闭清单；012 按 ADR-0016 会加 `gc` 和 `migrate`，到时候是否把清扫并进 `gc` 由 012 决定 |
| **Q-F** | `DELETE` 成功返回什么 | 204，没有响应体 | 与 `DELETE /api/collections/{id}`（`routers/library.py:206`，`status_code=204`）保持一致。⬛ 评审补充：提交点之后的失败（终结器某步失败）仍回 204，残余交给清扫；重试得 404 即「已删」；提交点之前的失败书完好。见 §3 WI-5 |
| **Q-G** | 列表遍历时书刚好被删（`FileNotFoundError`） | 跳过这本书，不报错误态 | 它在枚举之后才消失，本来就不该再出现；错误态只留给「目录在、但读不出来」的书。⬛ 评审补充：WI-6 导出用同一条规则，`notes` / 对话的部件级失败见 §3 WI-6 |
| **Q-H**（新，未裁定） | 删书后保留的孤儿对话要不要 HTTP 入口 | 本段不做：只保证在磁盘 `{配置的根}/{book_uuid}/` 下；现有对话路由要求活书（§3 WI-5） | 014 WI-16b 的确认框只需要「保留 / 删除」两个选项，不需要浏览孤儿；需要时另开，属加法式路由 |

**和 ADR-0016 的对照**（Q2 = B，状态 Proposed，012 合入时转 Accepted）。结论：**没有冲突，删书不需要知道 `gen/` 的存在**。
- 删书是把整个 `<book>_data` 目录 rename 成墓碑，`gen/*` 和 `manifest.json` 会跟着一次性挪走，提交点仍然只有一个。墓碑和书目录在同一个父目录下，不存在 EXDEV 问题。
- ADR-0016「删后再导入，generation 从 1 重新计数」，前提正是删书把整个目录拿走。
- 无锁读者正好在删书时读，会拿到 404，这与 ADR-0016「跨过 GC 的读者拿 404、不重试」是同一种语义。
- 墓碑名不以 `_data` 结尾，按 ADR-0016 的扫描规则不会被当成书。
- 有两处需要**对齐**（不算冲突）：清扫入口和 GC 共用一个函数（§5 第 3 条），持有者类别的归属（Q-E）。
- 另外，任务书 Q8 的「对话保留」与**代码**有冲突（D5 / Q-B），与 ADR-0016 无关。ADR-0016 第 2 条的「根目录封闭清单」把 `ai_conversations/` 列为书目录里的用户数据，恰好佐证了它会随 `rmtree` 一起消失。

---

## 7. 合入时要回写的地方（只列位置）

- [任务书](20260816-tech-stack-migration/tasks/018-library-routes.md)：状态行；§8 加「第二段」合入记录；§4 证据列；§1.3 的漂移（如果开工时还没改）
- [进度盘](20260824-frontend-backend-plan-progress.md)「现在该做什么」第 2 步，以及 §1 状态板（由协调者写）
- `plan-and-branch-map` skill 的里程碑表 018 行：🚧 改成 ✅（由协调者写）
- [009 跨波欠账表](20260816-tech-stack-migration/tasks/009-e2e-annotations.md#跨波欠账)：#53 / #56 / #58 改为已结清并附 commit；#31 补上 WI-7 的 CI 记录链接（这一行已经结清，只补链接）
- [feature ledger](../feature-ledger.md)：F-035（absent 改为 accepted）、F-036（stub 改为 accepted）、F-005 的 Limits（去掉 #58 / #53）、F-042（删书接入后再评估要不要从 partial 转 accepted）、F-028（WI-8 的硬拦截）。**F-034 不动**，它是导入 #57，归 012。改完后跑 `python3 scripts/build_feature_ledger.py` 重新生成 html
- [ADR-0015](../adr/0015-per-book-write-coordination.md)：已经 Accepted，只能另开一次回写，把 Current compliance 从 Partial 改成「018 全部写手已接入，012 的写手待接入」，把 Confirmation 补上删书测试。不改决定本身
- `soak-log.md`：新开「CI 运行记录」一节（WI-7）——就在这次回写 commit 里写，不进 PR（D17）
- [ADR-0018](../adr/0018-project-root-conversations-take-book-lock.md)：Proposed 改 Accepted（**在合入 PR 里**，不等回写），Current compliance 改 Full，Confirmation 补测试路径；[ADR 索引](../adr/README.md) 0018 行同步
- [`docs/storage-and-data-locations.md`](../storage-and-data-locations.md)：「Server-side on-disk storage (conversations)」补删书时对话的去向与孤儿位置；书锁一节补墓碑、删除意图文件、project-root 对话也持书锁
- [`docs/technical-detail.md`](../technical-detail.md)：书锁那一行补 ADR-0018 链接
- [`docs/export-import.md`](../export-import.md)：加书库导出（WI-6）的入口与 schema 链接
- [012 §1](20260816-tech-stack-migration/tasks/012-storage-format.md) 的「018 已合入」一行：🟡 改为 ✅

---

## 8. 2026-10-02 Codex 计划评审处置（NEEDS REVISION → 本版）

每条都先在代码上核过（证据在 §1.1 / §1.3 / §3 引用处）。没有一条被驳回。

| 级别 | 发现 | 处置 | 落在 |
|---|---|---|---|
| Critical | 提交点后、对话搬走前崩溃，清扫把对话一起删掉 | 采纳：意图文件先于提交点落盘；一个幂等终结器，请求与清扫共用；崩溃点 × 两个取值 | D12、§3 WI-5 状态机 / SIGKILL |
| High H1 | 项目级对话写手不持锁，删后迟到写入复活 | 维护者裁定：共享书锁按书目录名，`both` 锁内写完 | [ADR-0018](../adr/0018-project-root-conversations-take-book-lock.md)、D16、§3 WI-5 |
| High | Q-B 写死 `conversations/`；`both` 下目录已存在；跨卷 | 采纳：配置的根、逐文件发布与按 `last_updated` 合并、按磁盘决定 | §1.1、§3 WI-5、§6 Q-B |
| High | 加书进集合在集合锁外验书 | 采纳：集合锁内复核 ＋ 终结器再移除 ＋ 竞态测试 | §1.1、D13、§3 WI-5 |
| High | chromadb 按路径缓存 system | 采纳：退役该路径 ＋ 真 chromadb 同进程测试 | §1.1、D14、§3 WI-5 |
| High | WI-5 拆 commit 会先暴露提交点 | 采纳：路由只在最后一个 commit | §2 |
| Medium | 「只有一方 409」不对 | 采纳：两种次序分别规定、分别测 | D15、§3 WI-5 |
| Medium | 统计计算写回旧值 | 采纳：代次 | §1.1、§3 WI-5 |
| Medium | 只在启动时清扫 | 采纳：每次删书（与导入）取锁前，墓碑各持各的锁 | §3 WI-5 |
| Medium | 已有 soak 子进程用例会被新拦截拒掉 | 采纳：受控 env ＋ 注入仓库；拦截与 `--no-precheck` 无关 | D18、§3 WI-8 |
| Medium | 「按 `book_uuid` 找得到」没有接口 | 采纳：明确是磁盘，HTTP 入口列为 Q-H | §3 WI-5、§6 Q-H |
| Medium | WI-6 与 Q-G 冲突、坏 notes / 对话未处理 | 采纳：一个形状、分部件策略 | D19、§3 WI-6 |
| Medium | Q-F 没定义提交点后失败 | 采纳：204 ＋ 清扫兜底，重试 404 即已删 | §3 WI-5、§6 Q-F |
| Medium | WI-7 dispatch 在最后代码 commit 上 | 采纳：冻结 PR 头、核 `headSha`、`--match-head-commit`、记录挪到回写 | D17、§3 WI-7 |
| Medium | WI-8 先做违反「严格按号」 | 采纳：记为例外 | D11、§2 |
| Medium | §7 漏了两份 docs | 采纳：两份都在且相关，另加 `docs/export-import.md` | §7 |
| Low | 基线过期、D3 行号、「没有路由用书锁」 | 采纳：`fa9a4fe`、落后 10、`:526` / `:530`；改为「没有路由持独占锁」 | 头部、D3 |
