# 017-audit-followup — 011 合入后的审计欠账

> **归属**：[§9 编号表](../plan-tech-stack-migration.md#9-里程碑与分支唯一真相源) 的 **M2-债**。
> 不是新里程碑，是 011 的欠账兑付，与 `016` 同类。
> **基线**：从 `master` 的 `4128221` 开出（011 的合并提交）。**不回 `011-backend-refactor`**——
> 那条分支已经合了，再往上加提交只会让 master 与它分叉。

## 1. 这条分支买什么

011（PR #22）合入后，对 `e7c48900..4af73cc` 的 76 个代码文件做了一次全量审计
（`/cc-suite:audit pr #22 --full`，gpt-6-astra / high，9 个批次）。原始 44 条 findings 及逐条
复核证据在 `.cc-suite/audits/audit-20260922-230920-findings.md`；**那个目录在 `.gitignore:62`
上，不进版本库**，所以能进仓库的那一份事实是本文件。

分桶按 [`audit-findings-triage`](../../../.claude/skills/audit-findings-triage/SKILL.md)：先复核
severity（Codex 给的是主张不是判决），再按「正常单进程是否可达 / 是否把本分支自己宣称的保证证伪 /
修复要不要动冻结集」三轴分桶。结果：

| 桶 | 条数 | 本分支做不做 |
|---|---|---|
| `must` | 4 | ✅ |
| `must-pending-repro` | 2 | ✅（第一步是复现，结果决定升降） |
| `should` | 16 | ✅ |
| `could` | 19 | ❌ 留作后续，不在本分支 |
| `wont` | 3 | ❌ 见 §5，各有理由 |

**本分支范围 = must + should = 22 条**，展开成下面 15 个工作项。

## 2. 工作项

每项的「验收」必须是可执行的断言，不是「看起来对了」。标 🔴 的是产品缺陷，标 🧪 的是
「测试在实现坏掉时也能通过」——后者同样是缺陷，因为 011 宣称这些行为「已经有测试盯着」。

### WI-1 🔴 打断 routers 的导入环（#7、#20，must）

`routers/{notes,library,health,search,settings}` 都先 `import server`，而 `server` 立刻去取那个
尚未初始化完的模块的 `.router`。

**验收**
- 全新进程里 `python -c "import reader3_app.web.routers.notes"`（notes / library / health /
  search / settings 五个各一次）rc=0，不抛 `AttributeError: partially initialized module`。
- `python -m reader3_app.web.server` 不在 startup 之前就炸。
- `uv run pytest tests/unit/test_exception_summary_payload.py` 单独跑 rc=0（现在是 collection 报错，rc=2）。
- 上述三条各有一条常驻测试盯着，且测试必须**起新进程**——同一进程里的导入顺序会把问题盖住。
- `routers/` 导入铁律不变：`from .. import server as _server` 然后 `_server.X`。

### WI-2 🔴 给 AI 重试循环装上截止时间与取消（#2，must）

`server.py:643-704` `_call_provider`：每次尝试都拿到完整 `timeout_s`，循环既无请求级 deadline
也无取消信号。实测 504 返回之后，第 2、3 次尝试照发——多付钱，且会和下一个排队请求重叠。

**验收**
- 单元回归：请求被取消 / 超时之后，**不得有新的尝试开始**。桩 provider 记录调用次数，断言次数。
- 传输超时按剩余预算收窄，不是每次都给满。
- 退避等待可被打断（不是裸 `time.sleep(backoff)` 睡到底）。
- `chat.py` 与 `summary.py` 两条调用路径都覆盖到。

### WI-3 🔴 先复现再修「旧记录 ETag 不稳定」（#6，must-pending-repro）

`models/annotations.py:84` 在 `created_at` 缺失时填 `now()`，而 ETag 的 hash 含 `created_at`。
若属实，缺时间戳的旧笔记每次加载 ETag 都不同，紧跟着的条件更新必然 409——**旧笔记没法编辑**。

**验收**
- **第一步是复现**：构造一条无 `created_at` 的 `notes.json` 记录，连续两次读取，断言 ETag 相同。
- 复现成功 ⇒ 让归一化确定化，且**不得改写已持久化的时间戳**；再补一条「无 `created_at` 记录的
  条件更新成功」的用例。
- 复现失败 ⇒ 把复现过程与结论记在本文件，findings 降为 `should`，本分支不再修它。两种结果都算完成。

### WI-4 🔴 GET 的孤儿刷新要进锁（#1，should）

`routers/notes.py:91` 在不持 `_book_write_lock` 的情况下整份写回。跨进程（CLI 写入或第二个
worker）时，GET 能用旧快照覆盖掉一次已经提交成功的 `If-Match` PUT。

**验收**
- 读 / 刷新 / 写回三步在 `notes_service` 的同一把锁内完成。
- 确定性单元回归：GET 的孤儿刷新不得覆盖已提交的条件写。用事件同步，不用 sleep。

### WI-5 🔴 先复现再修「快照恢复仍存旧 CFI」（#3，must-pending-repro；顺带覆盖 #9）

`annotations.js:1514` 即便走了 `resolveOffsets`（:1433）的快照回退分支，`cfi` 仍由那个已失效的
`currentRange` 生成；渲染又优先用 CFI（:486-516）⇒ 正确存下的 quote 可能渲染成空高亮。

**验收**
- **第一步是复现**：在**新的、非冻结**的 e2e 模块里断言恢复出来的标注渲染文本**恰好**等于
  `NEW_QUOTE`，且 reload 之后仍然如此。
- 复现成功 ⇒ 用恢复出的 offsets 重建 Range 再生成 CFI，或在快照路径上干脆不写 CFI。
- 这条同时把 #9 要求的「渲染文本断言」买到手，**而冻结的 `baseline_1b` 一个字节不动**。

### WI-6 🔴 冲突解决同时只许有一个在飞（#5，must）

`resolveConflict()`（:1261）在「保留我的」PUT 还没回来时，两个按钮都还能点。点「采用远端」会
立刻 settle，而那个在飞的 PUT 回来后仍会 `settleConflict(c, c.localText)`，把用户最后的选择反掉。

**验收**
- 提交期间两个按钮都 disabled；属于已过期 conflict 实例的回调被丢弃；重复点击不能把已解决的
  冲突重新打开。
- e2e 落在非冻结模块。

### WI-7 🔴 编辑器正文和它的 base ETag 必须绑在一起（#4，should）

`:1297`「采用远端」把 A1 放进 textarea，而 `loadAndRender()` 把全局 ETag 更新成了 A2 的——
之后保存就是「A1 的正文配 A2 的令牌」，绕过冲突检测。

**验收**
- 要么同时采纳当前正文与当前令牌，要么保留所显示版本的令牌，使后续修改仍然会冲突。
- 单元或 e2e 断言：第三次远端编辑发生后保存，必须 409，不得静默覆盖。

### WI-8 异常策略与写入契约文档（#32、#33，should）

- **#32**：`_provider_retry_budget()`（`server.py:633`）新增了 `except Exception  # noqa: BLE001`。
  `AGENTS.md:68-72` 允许既有豁免、**明确禁止新增**。改成捕获具体的配置读取／解析异常，
  让真正的编程错误照常抛出。
- **#33**：可选 `If-Match`、书级 ETag、409 载荷（含 `annotation: null`）只存在于代码与计划文档里。
  按仓库的文档同步规则写进 `docs/technical-detail.md`；顺带改掉 `routers/notes.py` 开头那句
  「路由体未变」——它现在是假的。

**验收**：`rg 'noqa: BLE001' src/` 不含本次新增的那一处；技术文档里能查到 409 载荷形状。

### WI-9 🧪 AI 队列租约测试（#13、#14，should）

- **#13**：Q4 的 `stuck_gate` 并不保证 worker 已经进到第二次 `readline()`。用「阻塞读已进入」
  事件同步；清理时释放 gate 并 join worker。
- **#14**：把 gate 换成可观测的——记录 `wait()` 进入与其 timeout 参数。**验收判据**：把实现换成
  无条件 `sleep(3)`、完全无视 gate，这条测试必须变红（现在它会绿）。

### WI-10 🧪 egress 两处证据要分阶段（#16、#18，should）

- **#16**：断言 status 200、provider 恰好被调用两次、`answer == "fallback"`、以及既有的
  `rag_fallback` 路由元数据，然后再清 ledger。
- **#18**：C11／C14 必须要求「探针体通过 **且** 恰好一次 teardown 错误 **且** setup 零错误」；
  C14 的 disarmed 对照现在整个跳过了 fixture 执行，要让它真的跑。

### WI-11 🧪 覆盖率闸门每个指标都要有失败用例（#17，should）

`test_coverage_gate_failclosed.py` 的 G12 用 100% 覆盖只校验输出文案。内存里把 `lines` /
`statements` 改成无条件接受，22 条断言全绿，同时放行 `book_store.py` 的 0%。

**验收**：`lines` 与 `statements` 各有低于门槛的参数化用例，失败信息必须点名指标、实际值、门槛值。

### WI-12 🧪 并发测试去抖、去挂（#23、#24，should）

- **#23**：反向对照靠「保存屏障两秒超时」推进，不能证明第二个写者已过锁外预检。改用显式事件；
  正向用例也用事件确立争用，不拿耗时当证据。
- **#24**：worker 是非 daemon 线程，`:582` 断言一响就跳过 `barrier.abort()`，死锁回归会把
  pytest 挂住。改成子进程跑 + 父进程强制超时与回收；`barrier.abort()` 进 `finally`。

### WI-13 🧪 两条「实现坏了也能过」的护栏（#21、#29，should）

- **#21**：`_BLOCK_TAIL_RE` 只看尾部序列。在 `saveNote` 的上报调用前插一句 `return;`，整条护栏
  测试照样全绿——它自称能查死代码。改成拒绝上报之前出现可执行语句（尤其是提前 return），
  并补针对检查器本身的变异用例。
- **#29**：子进程 rc=0 且没出现 `BrowserType.launch`，并不证明测试跑过。注入 `1 skipped` 的子进程
  结果，这条测试照样通过。改成要求恰好 1 passed、0 skipped/xfail，并加一条 skipped 的负对照。

### WI-14 🧪 子进程要有超时；语义依赖要逐个缺（#19、#25，should）

- **#19**：`test_book_store.py:686` 的 `subprocess.run()` 无 timeout，导入死锁会把测试挂到天荒地老。
  加有限超时，`TimeoutExpired` 时打印捕获输出。
- **#25**：所有依赖失败用例都停在 `import chromadb`。只屏蔽 `sentence_transformers` 时
  `_require_semantic_deps()` 会通过，然后构造 embedding 时抛 `ValueError`——而 CLI 新加的
  `except RuntimeError` 接不住。逐个依赖单独测，含构造器路径，并断言 CLI/HTTP 的实际出口。

### WI-15 🧪 e2e 先等响应再轮询磁盘（#8 的非冻结调用点，should）

`wait_for_notes()` 用 Python `time.sleep` 轮询，期间 Playwright 的同步 route 回调跑不了——
正确的产品行为也会超时。这正是 #43 那族 flake 的机制。

**范围**：`tests/e2e/test_notes_write_failure_is_attributable.py:1283` 与
`tests/e2e/acceptance_2a/test_deg_s5_write_conflict.py:203` 两处。
**冻结的 `baseline_1b/test_w8a_selection_survives_rerender.py:132` 不动**（见 §5）。

**验收**：这两处先用 Playwright 等到相关写请求的响应，再轮询磁盘。

## 3. 退出门槛

全部满足才算完，缺一条就不是完成：

1. **22 条逐条有交代**：findings 文件里 `Status` 从 `open` 改为 `fixed` / `not-fixed`，附证据
   （命令、行号、或复现结论）。WI-3 / WI-5 两条 `must-pending-repro` 的复现结论必须写进本文件。
2. **三条 lane 全绿**，都带 `env -u FORCE_COLOR`（欠账 #47）：
   - `unit`：`uv run pytest tests/unit tests/contract --cov=...`
   - `e2e`：`uv run pytest tests/e2e --browser chromium`
   - `packaging`：`uv run pytest tests/integration -m slow`
3. **冻结集零改动**：对下列 8 条路径 `git diff --stat master... -- <paths>` 输出为空，
   `suite_hash` 仍是 `1e868c7bf811`、23 个 blob：
   `tests/e2e/baseline_1b/**`、`tests/e2e/conftest.py`、`tests/e2e/helpers.py`、
   `tests/e2e/test_harness_smoke.py`、`tests/fixtures/{epub_corpus,epub_zip,ai_stub}.py`、
   `tests/conftest.py`。
4. **`uv run python scripts/lint_e2e_groups.py` rc=0**，且 `EXPECTED_BASELINE_ITEMS` **仍是 68**
   ——它一动就说明碰了冻结集。新增 e2e 文件会改变 `tests/e2e` 的收集总数，`scripts/lint_e2e_groups.py`
   的常量与 `tests/unit/test_e2e_group_guard.py` 的独立 oracle 两边都要同步（两者都不在冻结集里）。
5. **每个修复都有一条先红后绿的测试**。红必须是断言失败，不是导入错误或零用例。
6. **不得设 `TDD_GUARD_BYPASS`**。
7. **CI 全绿**（`tests.yml` 与 `lint.yml`），然后开 PR 到 `master`。

## 4. 硬约束

- **ADR-0008 技术栈边界**：不得引入 JS 测试运行器（package.json / vitest / jest / npm 依赖一律不行）。
  JS 行为的唯一测法仍是 Playwright e2e。
- **冻结集只读**。动一个字节，soak 计数清零、三道机制闸全部作废（当前计数与冻结值只在
  [`soak-log.md`](./soak-log.md) 里定义，别在别处复述）。
- **soak 不在本分支跑**：011 §8 门槛 4 规定分支上不得追加 soak 行。
- `designs/reader-pro-next/*.jsx` 与 `.mcp.json` 是既有脏文件，别碰、别提交。
- 包管理 `uv run`；所有 lane 加 `env -u FORCE_COLOR`。

## 5. 明确不做的，以及为什么

**`wont`（3 条）**
- **#9、#10** —— 修复要改 `tests/e2e/baseline_1b/**`，会把 soak 清零、三道机制闸作废。
  **替代覆盖**：#9 想要的渲染文本断言已折进 **WI-5**，写在新的非冻结 e2e 模块里。
  #10（重新着色后空高亮也能过）暂时**没有替代覆盖**——这是一个已知的、写在纸面上的洞，
  不是「已经盖住了」。等下一次冻结集重置时一并买。
- **#22** —— `disputed`。`If-Match` 上剥掉 `W/` 是有意设计，`normalize_etag` 的 docstring
  （`notes_service.py:300`）写着。RFC 9110 §13.1.1 要求强比较，但这条路径上没有任何东西会产生
  弱令牌。若将来引入会弱化令牌的代理，重开此条。

**`could`（19 条）** —— lint／扫描器精度（#11、#12、#27、#28、#35、#36、#43、#44）、
测试覆盖缺口（#15、#26、#40、#41）、小改动（#30、#31）、注释与文档同事实不符（#34、#37、#38、
#39、#42）。都不影响行为，留作后续。不在本分支做，**也不表示它们被否决**。

## 6. 风险

- **WI-1 是本分支风险最高的一项**：改 app 组装顺序会碰到每一条路由。缓解是先把「新进程导入」
  测试写出来当红灯，再动结构；`tests/contract/` 的路由快照（`routes.snapshot`）必须一字不变。
- **WI-5 / WI-6 要新增 e2e 文件**，会改变 `tests/e2e` 收集总数 ⇒ 记得同步门槛 4 里那两个常量。
- **WI-12 把并发用例改成子进程**会拉长 unit lane 时间；若超过 `timeoutMs: 600000` 要重新计时。
