# 018 第二段（WI-4 – WI-8）执行计划

- **状态**: 草案，待维护者确认 §6 的开放问题后开工
- **日期**: 2026-10-02
- **基线**: `master` `babaf59`。分支 `018-library-routes` 停在 `42c0728`，没有领先 commit，落后 `master` 9 个（`command git log master..018-library-routes` 为空，`git rev-list --count 018-library-routes..master` = 9），开工时先 fast-forward 到 `master`
- **定义处**: WI-4 – WI-8 的目标、涉及文件、验收种子、出口闸、裁定**只在** [`tasks/018-library-routes.md`](20260816-tech-stack-migration/tasks/018-library-routes.md)；执行顺序**只在** [进度盘](20260824-frontend-backend-plan-progress.md)；锁契约**只在** [ADR-0015](../adr/0015-per-book-write-coordination.md)（已 Accepted）。本文只回答**怎么做好**，不复述上面这些
- **为什么现在做**: 012 的 WI-5 / WI-10 建在 #56 列表路由上，014 WI-16b 等着 #56 / #58，而每书锁（`book_lock`）合入 `master` 以后还没有一条路由用到它（删书是第一个独占写手）。维护者 2026-10-02 定的顺序是：先做完本段（018 WI-4 – WI-8）→ 再跑 [012 开工核验](20260816-tech-stack-migration/plan-tech-stack-migration.md#012-开工核验2026-09-30-维护者裁定) → 再开 012

> 引用规则沿用任务书（用符号名定位）。本文的 `file:line` 是 2026-10-02 在 `babaf59` 上 grep 到的，只用来证明「现状」，行号会漂，执行时以符号为准。

---

## 1. 现状核对（2026-10-02，`babaf59`）

### 1.1 已有、可直接用的

| 东西 | 位置 | 对本段的意义 |
|---|---|---|
| 元数据接缝 `load_book_metadata` | `src/reader3_app/book_store.py:150`（函数体 `:176` 仍是全量读后投影）；`BookMetadataView` 只有 `book_id` / `title` / `authors`（`:115`） | WI-4 的唯一数据来源。`cover_url` 和 `book_uuid` 不在这个 view 里，见 §3 WI-4 |
| 书锁 API | `book_lock.acquire(books_dir, folder, *, mode, holder, deadline, budget)`（`book_lock.py:306`）、`writer_scope`（`:538`）、`read_book_uuid`（`:517`）、`CATEGORIES`（`:62`，已经有 `delete`） | WI-5 用 `acquire(mode="exclusive", holder="delete")`；独占写手不等待，拿不到直接拒绝 |
| 锁异常到 HTTP 的映射 | `web/book_lock_http.py`：`BookLockBusy` 映射成 409 ＋ `Retry-After`，`BookChanged` 映射成 409，`BookGone` 映射成 404（`:20-41`）；在 `server.py:341` 安装 | 删书路由抛异常就行，状态码不用自己拼 |
| 现成的独占写手可以照抄 | `reader3.py:744`（`process_epub`，`mode="exclusive", holder="import"`） | WI-5 的取锁形状照这里写 |
| 书库枚举 | `search_service.list_book_ids`（`:250-262`，只收 `_data` 后缀**且**有 `book.pkl` 的目录）；`_validate_book_id`（`server.py:492`）经它判断 404 | WI-4 的条数、WI-5 的 404 都以它为准 |
| uuid 批量解析 | `server._book_uuids_or_none`（`server.py:475`），`library_view` 在线程池里调它（`routers/library.py:76`） | WI-4 的 `book_uuid` 字段直接复用，不另写 |
| 封面挑选 | `library_view` 里内联实现（`routers/library.py:47-63`，直接读 `images/` 目录，没有经过 `Book`） | WI-4 的 `cover_url` 要用同一套规则 |
| 集合锁 | `collections_service._collections_write_lock`（`:84`，`library_collections.json.lock`） | WI-5 第 3 步用；**没有**「把一本书从所有集合里移除」的函数（`:171-254` 只有按集合操作的函数），要新加 |
| 统计缓存 | `server._stats_cache`（`server.py:291`） | WI-5 第 5 步失效它 |
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
| D3 | WI-4 接缝守卫测试 | 只点名 `test_no_production_call_site_uses_the_new_seam_yet` | 测试在 `tests/unit/test_book_store_metadata_seam.py:490`，断言 (a) 在 `:531`，(b) 在 `:535`，与任务书一致。但还漏了两处：`book_store.py:109-111` 的注释「Nothing consumes the seam in this branch」也要改；测试名里的 `_yet` 改写后含义会变 → 建议改名为 `test_seam_callers_are_the_allowlist` |
| D4 | WI-4 / WI-5 / WI-6 | 没有写路由路径 | 前端计划把列表路由叫 `/api/library`（`plan-frontend-ui-refactor.md:432`、`:1321`），删书和导出的路径没人定过。→ 见 §6 Q-A |
| D5 | WI-5 第 6 步、§6 Q8、ADR-0015 Neutral | 「对话保留为孤儿」 | 默认存储模式是 `per_book`（`ai/config.py:41`、`server.py:1003`），对话放在 `{book}/ai_conversations/`（`ai/conversations.py:45-47`），**就在书目录里面**。第 7 步 `rmtree` 墓碑会连对话一起删掉，`delete_conversations=false` 的保留承诺在默认模式下做不到。→ 见 §6 Q-B（**冲突，要裁定**） |
| D6 | WI-5 第 5 步 | 「失效 `BookUuidResolver` 映射」 | 没有公开 API（见 1.2）。→ 涉及文件里补上「`BookUuidResolver` 加一个公开的 `forget_folder`」 |
| D7 | WI-5 第 3 步 | 「在全局集合锁下移除」 | 要新加一个函数，比如 `collections_service.remove_book_everywhere`。→ 写进涉及文件 |
| D8 | WI-7 目标 1 | 「`tests.yml` 的 `e2e` job 头注释两句没跟上」，§7「该补偿至今没有建出来」 | 两处都已经修了：`tests.yml:154-156` 现在写的是「也跑在每个向 `master` 开的 PR 上」；plan §7 那段（`plan-tech-stack-migration.md:502`）已经标注「本段是…快照，已过期」。→ WI-7 只剩「核验 ＋ 记录」两项，目标 1 标成已完成 |
| D9 | WI-6 验收 | 没提到旧 e2e | `test_key_never_echoed_and_exports` 的最后三行（`test_settings_rows.py:272-275`）断言的是「暂不支持」。WI-6 要把它**反过来**，这是有意地重新判一条测试，不是放宽。→ 写进 WI-6 验收 |
| D10 | WI-5 墓碑清扫 | glob `books/.*.deleted-*/` | 合法的书目录名可以以点开头、并且以 `_data` 结尾（比如 EPUB 叫 `.x.deleted-1.epub`），会被这个 glob 误收。`reader3.py:282-299` 的 `_is_own_staging_name` 为同类问题吃过亏。→ 判据改成严格正则 `^\.(?P<folder>.+_data)\.deleted-(?P<pid>\d+)(-[0-9a-f]+)?$`，并且要求目录名**不以 `_data` 结尾** |

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
- **WI-8 和谁都不冲突**：只碰 `scripts/soak_run.py` 和 `tests/unit/test_soak_run.py`。建议**第一个做**，当热身，同时让后面的 lane 运行都带上它。
- **commit 粒度**：每个 WI 一个 red commit（测试）＋ 一个 green commit（实现，路由和快照同在这个 commit）；WI-5 允许拆成 2 个 green commit（锁加提交点一个，清扫与缓存失效一个）。门槛 8 要求「每条欠账一个 commit 结清」：009 表的状态改动随该 WI 最后一个 commit 一起提交。
- **建议用一个实施会话，不开两个**。理由：(1) 主线是严格串行的；(2) WI-8 大约 50 行改动，为它开 `/coordinate` 平行会话，分配、检查点、合并的成本比活本身还大；(3) 一个会话里 WI-5 能直接看到 WI-4 的错误态形状，不用靠文档转述。
- **WI-8 要不要单独拆一个 PR：不拆**。它是 018 自己的范围（§6 Q10），拆出去要在 §9 新分配编号，还要多跑一轮 CI。它跟着本段合入还有一个好处：012 开工核验的那一批 `--append` 是它上线后第一次真跑，正好在开 012 之前就用上了。代价是 PR 里混了一个与书库无关的 commit，PR 描述里分节写清楚即可。

---

## 3. 逐 WI 执行要点

> 测试矩阵按 [任务书 §3](20260816-tech-stack-migration/tasks/018-library-routes.md#3-工作项) 的规定交给 `/tdd-guardian:design-tests`，再经 `tdd-spec-adversary` 攻一轮。下面只写**怎么证明测试能咬人**和**容易出错的地方**。

### WI-8：`--append` 硬拦截（[定义](20260816-tech-stack-migration/tasks/018-library-routes.md#wi-8-soak_runpy---append-硬拦截)）

- **测试**: 单元测试放在 `tests/unit/test_soak_run.py`。git 用一个真的临时仓库，造出 `origin/master` 和一个分叉 commit，比打桩 `subprocess` 更可信；`GITHUB_ACTIONS` 用 `monkeypatch.setenv` 设置。
- **红灯检查**: 把新判据整段注释掉，四条用例里「拒绝」那两条必须红；把 `is-ancestor` 换成「分支名等于 master」，「detached worktree → 放行」那条必须红。
- `origin/master` 解析不出来时（没 fetch、没有 remote）的默认处理：拒绝，并提示先 `git fetch origin master`。宁可误拒，不可误收。

### WI-4：#56 列表路由（[定义](20260816-tech-stack-migration/tasks/018-library-routes.md#wi-4-欠账-56--客户端书目列表路由)）

- **测试**: 契约测试放在 `tests/contract/`，新建 `test_library_books_route.py`，用 `contract/conftest.py` 的临时书库。损坏条目用**真的损坏 `book.pkl`**，不打桩 `server.load_book_cached`。原因：新路由走的是 `book_store.load_book_metadata`，它在 `book_store` 内部解析 `load_book_cached`（见 `test_server_patch_seam_ownership.py:233-245` 的注释），打桩 server 那一侧拦不到，测试会假绿。
- **红灯检查**: 让路由跳过损坏条目（不输出错误态），条数断言必须红；让路由直接读 `book.pkl` 绕开接缝，改写后的接缝守卫测试必须红（白名单只放新模块）。
- **字段从哪来**: `title` / `authors` 来自 `load_book_metadata`；`book_uuid` 用 `_server._book_uuids_or_none`，放进线程池跑；`cover_url` 把 `library.py:47-63` 的挑选逻辑**抽成一个函数**，`library_view` 和新路由共用（默认放在 `book_store`，见 §6 Q-C），保证与服务端渲染的书库页逐字节一致。条数以 `list_book_ids` 为准。
- **快照**: 新路由、`routes.snapshot` 加一行、`ROUTER_MODULES`、`server.py` 的 include 列表，四处放在同一个 green commit。`test_route_contracts.py:214` 的 `LIBRARY_CASES` 加 200 那一行。

### WI-5：#58 删书（[定义](20260816-tech-stack-migration/tasks/018-library-routes.md#wi-5-欠账-58--删书路由wi-2-之后)，锁规则见 [ADR-0015](../adr/0015-per-book-write-coordination.md) 第 1、2、4、8 条）

- **锁怎么用**: 一次删书在线程池里只取一次 `acquire(mode="exclusive", holder="delete")`，取不到就抛 `BookLockBusy`，HTTP 层按已有映射回 409。锁内复核书目录：不在就抛 `BookGone`，回 404。整个第 1 – 8 步都在一次持锁里完成。删书过程中**不再**取任何别的书锁；集合锁属于全局资源，按「书锁 → 资源锁」的顺序在书锁之内取。
- **测试分层**:
  - 单元测试：新建 `tests/unit/test_library_delete.py`，覆盖删书顺序、缓存失效、清扫的正则（D10），以及 `delete_conversations` 的两个取值。
  - 跨进程测试：沿用 `tests/unit/test_book_lock_cross_process.py` 的 `Holder` 范式，验证删书与 `api_index_book` 并发时只有一方得到 409，并且目录不会被重新建出来。
  - SIGKILL 测试：照 `test_process_epub_sigkill_recovery.py:100-155`，在提交点 `rename` 之前和之后各杀一次，然后重启跑清扫。
  - 契约测试：在 `LIBRARY_CASES` 里加 404 / 400 / 409 三行。
- **红灯检查**（每条至少一个变异）: 把第 4 步的 rename 换成直接 `rmtree`，「提交点前崩溃 → 书完好」必须红；删掉 `_stats_cache` 的失效，「删后 stats 立即反映」必须红；清扫改成「先探测锁、放掉、再删」，Codex 那个剧本必须红；清扫的 glob 换回 `.*.deleted-*`，D10 的那个合法书目录被删，必须红。
- **e2e：本段不加**。删书的 UI 属于 014 WI-16b，本段的验收在契约测试和跨进程测试这一层就能闭合。这样门槛 6（e2e 分组登记）对 WI-5 不适用，也从根上避开了 [任务书 §5](20260816-tech-stack-migration/tasks/018-library-routes.md#5-风险) 的「e2e 污染共享语料」风险。如果维护者坚持要一条 e2e，就照任务书 WI-5 的 e2e 条款：独立书库、独立服务（参照 `tests/fixtures/deg_assertions.py:297` 的 `pickle_fallback_server`），新 fixture 放进非冻结的 `tests/fixtures/` 模块。
- **墓碑名**: `.{folder}.deleted-{pid}-{随机 8 位十六进制}`。只用 pid 不够：同一个服务进程里「删书 → 重新导入 → 再删」时，如果上一次的墓碑还没清完，第二次 rename 会撞名（见 §6 Q-D）。

### WI-6：#53 导出 ＋ FB-S06（[定义](20260816-tech-stack-migration/tasks/018-library-routes.md#wi-6-欠账-53--书库导出)）

- **测试**: 契约测试放在 `tests/contract/test_library_export_route.py`，覆盖：缺省请求不带对话也不带正文；`?include=conversations` 时带对话；损坏的书以 WI-4 的错误态出现；响应里不出现 API key（复用 `test_settings_rows.py` 的 secret 扫描思路）。Vitest 新建 `frontend/tests/settings/export.test.ts`，覆盖：导出中按钮 `disabled`、失败时可见。e2e 只**原地反转** `test_key_never_echoed_and_exports` 的最后三行（D9），断言变成「发出 1 个请求，下载的内容是合法 JSON」。这样 `shell_4a` 的条数不变，`lint_e2e_groups.py` 不用动。
- **红灯检查**: 让路由在缺省请求下也带上对话，第一条必须红；前端恢复「暂不支持」，反转后的 e2e 必须红。
- **边界的默认做法**（任务书说「本 WI 自定」）: 一次性 `JSONResponse` 加 `Content-Disposition: attachment`，不做流式，不设大小上限。单用户、本地部署，按宪法第 2 条 YAGNI。读侧不取锁，与 ADR-0015 / ADR-0016「读者不取锁」一致；某本书读到一半消失了，按错误态处理，不让整次导出 500。

### WI-7：#31 收尾对账（[定义](20260816-tech-stack-migration/tasks/018-library-routes.md#wi-7-欠账-31--ci-e2e-job-收尾对账最后做)）

- 按 D8，只剩两件事：在**最后一个代码 commit** 上跑 `gh workflow run tests.yml --ref 018-library-routes`，要求 `e2e` job 绿且 `attempt=1`；PR 的 `pull_request` 运行也要绿。然后在 `soak-log.md` 新开「CI 运行记录」一节，记下 run id、commit 和 Chromium 版本。
- 记录本身是一个纯文档 commit，它会改变分支头；这个 commit 由 PR 上的 `pull_request` 运行覆盖，不需要再手点一次 dispatch。
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
| CP1 | 写第一行生产代码之前 | WI-8 / WI-4 / WI-5 / WI-6 的测试矩阵（`design-tests` ＋ adversary）已入库或在 tdd-guardian 产物里；red commit 已提交，并且确实是红的 | 7 的删书部分（矩阵里要能看到「不复活」「409」两类） |
| CP2 | WI-5 green 之后（中点） | commit 闸绿；`mypy`、`ruff`、`check_router_size.py` rc=0；冻结集 diff 为空；`routes.snapshot` 的 diff 只有新增行；由 `checkpoint-verifier` 在这个 SHA 上独立重跑 | 2、3、4、5、F |
| CP3 | 准备合并 | push 闸绿（`e2e` ＋ `packaging`）；WI-7 的两次 CI 都绿；009 表 #53 / #56 / #58 / #31 已结清；红灯表为空或每一行根因齐全；PR 描述写明 ADR-0011 的破坏性（加法式、无破坏）；`soak_run.py` 只核验、不 `--append`，deselected 精确相等 | 1、5、6、8、9、R、11 |

门槛 10 已经被开工核验取代，不再单独做。门槛 7 的 ADR 转正已经完成，本段只需要把 ADR-0015 的 compliance 改成 Full（见 §7）。

---

## 5. 风险（只列任务书 §5 之外的）

- **默认模式下的对话误删**（D5）：照任务书原文实现，用户在默认配置下删一本书，会连对话一起丢掉，和「默认保留」的承诺相反。在 Q-B 裁定之前，WI-5 不得进 green。
- **清扫和新书抢锁**：删书 → 同名重新导入 → 启动时清扫旧墓碑，清扫要持新书那把独占锁。大的墓碑 `rmtree` 期间，新书上的共享写手（比如保存笔记）会在 2 秒预算内拿到 409。按 ADR-0015 这是可以接受的拒绝，但前端要能保住未保存的内容（这本来就是契约第 4 条的要求）。
- **012 的 GC 清扫入口和 018 的墓碑清扫各写一份**：[ADR-0016](../adr/0016-generation-directory-publish.md)「安全 GC」(b) 也是「启动时 ＋ 非阻塞独占锁 ＋ 拿不到就跳过」。本段把清扫写成一个函数（比如 `library_sweep.sweep_on_startup`），在 `server._startup_scan_books`（`server.py:344-348`）里调用，012 往里面加 GC 一步，不另起入口。

---

## 6. 开放问题（未裁定，各附推荐默认）

| Q | 问题 | 推荐默认 | 理由 |
|---|---|---|---|
| **Q-A** | 三条路由的路径 | `GET /api/library`；`DELETE /api/library/{book_id}?delete_conversations=false`；`GET /api/library/export?include=conversations` | 前端计划已经用 `/api/library` 这个名字（D4）。与 `GET /api/library/stats` 方法不同或路径不同，不冲突；`book_id` 必须以 `_data` 结尾，`stats` 不可能被当成书 |
| **Q-B** | `per_book`（默认）/ `both` 模式下，`delete_conversations=false` 怎么兑现（D5） | 在提交点（第 4 步）**之后**、`rmtree`（第 7 步）**之前**，在锁内把墓碑里的 `ai_conversations/` 搬到项目级目录 `{project_root}/conversations/{book_uuid}/`（与 `project_root` 模式的目录布局相同，`ai/conversations.py:55-59`），没有 uuid 时就地丢弃并记日志；`project_root` 模式什么都不用做 | 这样能兑现 Q8「默认保留为孤儿」的本意，孤儿仍然只按 `book_uuid` 引用（Q12 / ADR-0015 第 6 条）。另一个选项是「`per_book` 模式下没带 `true` 就拒绝删书」，实现更简单，但会让 014 的确认框多一个分支。**这条要维护者拍板**，它改的是 Q8 的实际语义 |
| **Q-C** | 封面挑选函数放哪 | `book_store`，作为一个独立函数，**不**放进 `BookMetadataView` | ADR-0016 列出的平铺路径站点里有 `library.py:49`（封面 `images`），012 WI-4 会把这类站点收进 `book_store`，再用 grep 门挡住其他地方。现在放进 `book_store`，站点少一个；放进 view 就等于替 012 扩了接缝，任务书 WI-4 明令不许 |
| **Q-D** | 墓碑名要不要加随机后缀 | 要：`-{pid}-{8hex}`；清扫正则见 D10 | 同一进程删两次同名书会撞名；ADR-0015 第 1 条只说「墓碑 `.{id}.deleted-{pid}/`」不进书库，没有规定确切格式，属于 WI-5 自己的实现细节，不需要改 ADR |
| **Q-E** | 墓碑清扫用哪个持有者类别 | 用现有的 `delete`，不新增类别 | `CATEGORIES` 是封闭清单；012 按 ADR-0016 会加 `gc` 和 `migrate`，到时候是否把清扫并进 `gc` 由 012 决定 |
| **Q-F** | `DELETE` 成功返回什么 | 204，没有响应体 | 与 `DELETE /api/collections/{id}`（`routers/library.py:206`，`status_code=204`）保持一致 |
| **Q-G** | 列表遍历时书刚好被删（`FileNotFoundError`） | 跳过这本书，不报错误态 | 它在枚举之后才消失，本来就不该再出现；错误态只留给「目录在、但读不出来」的书 |

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
- `soak-log.md`：新开「CI 运行记录」一节（WI-7）
- [012 §1](20260816-tech-stack-migration/tasks/012-storage-format.md) 的「018 已合入」一行：🟡 改为 ✅
