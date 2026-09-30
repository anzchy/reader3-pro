# 017-audit-followup — 011 合入后的审计欠账

> **归属**：[§9 编号表](../plan-tech-stack-migration.md#9-里程碑与分支唯一真相源) 的 **M2-债**。
> 不是新里程碑，是 011 的欠账兑付，与 `016` 同类。
> **基线**：从 `master` 的 `4128221` 开出（011 的合并提交）。**不回 `011-backend-refactor`**——
> 那条分支已经合了，再往上加提交只会让 master 与它分叉。
> **状态**：**✅ 已合入 `master`（2026-09-23，PR #23），M2-债关闭。** 见下面的「合入记录」。
> 这不撤销 011 的 ⚠️（门槛 #7，剩余一半是 009 欠账 #35，落在 012）。

### ✅ 合入记录（本文是这条事实的唯一定义处）

**017 已于 2026-09-23 合入 `master`。** 别处提到「017 是否在主干上」一律链回这一节，不要重述数字。
本节 2026-09-30 补写（此前合入后没有回写，审计 #2 查出）；下表每一行都是当天按「复核命令」重查的。

| 事实 | 值 | 复核命令 |
|---|---|---|
| PR | [#23](https://github.com/anzchy/reader3-pro/pull/23)，19 commits / 52 files / +5542 −248，合入时间 2026-09-23T07:45:42Z | `gh pr view 23 --json commits,additions,deletions,changedFiles,mergedAt` |
| 合并 commit | `6df5026`（`017 审计收口：22 条 must + should 逐条有交代，冻结集零改动`），父提交 `4128221`（011 的合并提交，即本分支基线）＋ `83b7ed1`（分支头） | `git show -s --format='%h %p %s' 6df5026` |
| 合并 commit 与分支头的树 | **同一棵树**（`50c204e`）——合并没有引入分支头之外的任何改动 | `git rev-parse 6df5026^{tree} 83b7ed1^{tree}` |
| 分支领先量 | **0** | `git rev-list --count master..017-audit-followup` |
| 合入前门禁 | 本地三条 lane 与门槛 1–6 在 `255b63a` 核验，结果见 [§3.1](#31-核验结果2026-09-23255b63a) | —— |
| CI | **只在 `255b63a` 上有运行**：`lint.yml` 35827418587 ✅、`tests.yml` 35827429249 ✅（`workflow_dispatch`，明细见 [§3.2](#32-ci-与-pr门槛-7)）。**分支头 `83b7ed1` 与合并 commit `6df5026` 上都没有任何 CI 运行**，PR #23 页面上也没有 check | `gh run list --commit <完整 sha>` 对两者均返回 `[]` |

> **为什么认 `255b63a` 的 CI，而不是说「合并头 CI 绿」。** `255b63a..83b7ed1` 只有一个 commit
> （`83b7ed1`），diff 只碰本文件（+65 −3），不碰任何代码、测试或 workflow；合并 commit 又与 `83b7ed1`
> 同树。所以 `255b63a` 上的两条绿**在内容上**覆盖了合入的东西——但字面上合并头没有跑过 CI，这里照实记，
> 不写成「合并头 CI 绿」。PR 页面没有 check 是因为 `pull_request → master` 触发器是合入**之后**
> 才加的（`58ef602`，2026-09-24），当时两条 workflow 只认发版与 `workflow_dispatch`。
>
> 分支 `017-audit-followup` 合入后远端**保留未删**（远端头仍是 `83b7ed1`）。

## 1. 这条分支买什么

011（PR #22）合入后，对 `e7c48900..4af73cc` 的 76 个代码文件做了一次全量审计
（`/cc-suite:audit pr #22 --full`，gpt-6-astra / high，9 个批次）。原始 44 条 findings 及逐条
复核证据在 `.cc-suite/audits/audit-20260922-230920-findings.md`；**那个目录在 `.gitignore:62`
上，不进版本库**，所以能进仓库的那一份事实是本文件。

分桶按 [`audit-findings-triage`](../../../../.claude/skills/audit-findings-triage/SKILL.md)：先复核
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

### WI-1 ✅ 打断 routers 的导入环（#7、#20，must）

`routers/{notes,library,health,search,settings}` 都先 `import server`，而 `server` 立刻去取那个
尚未初始化完的模块的 `.router`。

**验收**
- 全新进程里 `python -c "import reader3_app.web.routers.notes"`（notes / library / health /
  search / settings 五个各一次）rc=0，不抛 `AttributeError: partially initialized module`。
- `python -m reader3_app.web.server` 不在 startup 之前就炸。
- `uv run pytest tests/unit/test_exception_summary_payload.py` 单独跑 rc=0（现在是 collection 报错，rc=2）。
- 上述三条各有一条常驻测试盯着，且测试必须**起新进程**——同一进程里的导入顺序会把问题盖住。
- `routers/` 导入铁律不变：`from .. import server as _server` 然后 `_server.X`。

**✅ 已修（2026-09-23，`5e60bd8`）**。#7 与 #20 原样成立。

`routers/__init__.py` 的 docstring 写着「绑模块、不绑属性，顺带解决了循环导入」——前半句
对，后半句是错的：它只管住了 router 这一侧，而 `server.py` 在文件末尾要取
`routers.X.router` 这个**属性**。于是谁先被导入就决定成败，六个顶层 router 全中：

```
python -c "import reader3_app.web.routers.notes"
AttributeError: partially initialized module 'reader3_app.web.server' has no attribute 'router'
```

`python -m reader3_app.web.server` 也走不到自己的参数解析。平时看不见，是因为 console
脚本和绝大多数测试都从 `server` 进。

**修法**：把 `from .. import server as _server` 挪到每个 router 的**文件末尾**，在 `router`
与所有路由定义完之后。先用 AST 确认十个模块里没有任何模块级 `_server` 引用，所以挪下去是
安全的；打桩接缝不受影响——`_server.X` 仍是调用时解析属性。顺带把那两段声称「环已解开」的
注释改成实话：**改的是导入位置，不是说法**。

**红→绿：22 failed / 1 passed → 23 passed**。每个模块起**独立子进程**先导入它自己，再断言
整个 app 装配得出来（`/api/health` 在路由表里、`len(app.routes) > 40`）——堵掉「try/except
把 AttributeError 吞掉」这种假绿。另有一条守卫比对模块清单与 `server.py` 的 include 列表，
新增 router 漏配会红。

### WI-2 ✅ 给 AI 重试循环装上截止时间与取消（#2，must）

`server.py:643-704` `_call_provider`：每次尝试都拿到完整 `timeout_s`，循环既无请求级 deadline
也无取消信号。实测 504 返回之后，第 2、3 次尝试照发——多付钱，且会和下一个排队请求重叠。

**验收**
- 单元回归：请求被取消 / 超时之后，**不得有新的尝试开始**。桩 provider 记录调用次数，断言次数。
- 传输超时按剩余预算收窄，不是每次都给满。
- 退避等待可被打断（不是裸 `time.sleep(backoff)` 睡到底）。
- `chat.py` 与 `summary.py` 两条调用路径都覆盖到。

**✅ 已修（2026-09-23，`cb7c2e6`）**。#2 原样成立。

`ai_queue.run()` 到点会 cancel 掉等结果的协程并给客户端 504，但 `_call_provider` 跑在
`run_in_threadpool` 的线程里——**取消一个等它的协程停不下那个线程**。客户端断连同理：连接
已经拆了，钱还在烧，而且新一轮请求可能和它并发打同一个 provider。

**修法**：`_call_provider` 新增两个**可选**参数，两个都不传 = 今天的行为逐字不变（R17 那条
护栏专门盯着这一点，因为一旦默认值成了真值，6 个调用点和全部既有打桩会一起改行为）。
- `deadline`：`time.monotonic()` 的**绝对时刻**。它同时收住单次调用的传输超时
  （`_provider_attempt_timeout_s`，下界 1 秒）和退避时长——不收的话「总预算」只是个说法，
  一次 30 秒的 connect 就能把 2 秒的剩余预算整个盖过去。
- `should_stop`：返回 bool 的可调用对象。

退避改成**边睡边看**（`PROVIDER_RETRY_STOP_POLL_S` = 0.05s）：只在进入退避前查一次，等于给
跑飞的重试一整个 8 秒窗口去发下一次请求。停下来时抛的仍是**最后那个异常对象本身**
（R4／ADR-0011：`str(e)` 是 SSE 与自测响应的内容）；一次都还没发就到点，才抛我们自己的
`TimeoutError`。`routers/settings.py` 的连通性自测豁免：它显式 `max_retries=0`。

**红→绿：6 failed / 1 passed → 45 passed**。R14–R20 守「收到预算之后的行为」；另新增
`test_provider_call_budget_wiring.py` 用 AST 扫 `routers/` 下每一处出口**有没有带预算出门**
——删掉某个调用点的 `deadline=`，R14–R20 一条都不会红。定向破坏验证过（`summary.py:165`
缺 ⇒ 1 failed），已还原。

### WI-3 ✅ 先复现再修「旧记录 ETag 不稳定」（#6，must-pending-repro）

`models/annotations.py:84` 在 `created_at` 缺失时填 `now()`，而 ETag 的 hash 含 `created_at`。
若属实，缺时间戳的旧笔记每次加载 ETag 都不同，紧跟着的条件更新必然 409——**旧笔记没法编辑**。

**验收**
- **第一步是复现**：构造一条无 `created_at` 的 `notes.json` 记录，连续两次读取，断言 ETag 相同。
- 复现成功 ⇒ 让归一化确定化，且**不得改写已持久化的时间戳**；再补一条「无 `created_at` 记录的
  条件更新成功」的用例。
- 复现失败 ⇒ 把复现过程与结论记在本文件，findings 降为 `should`，本分支不再修它。两种结果都算完成。

**复现结论（2026-09-23，必须写在这里）——复现成功，#6 维持 `must`。**

构造一条无 `created_at` 的 `notes.json` 记录连读两次，两次 ETag **不同**；紧跟的条件更新
以 `NotesVersionConflict` 挂掉。成因比 #6 说的还宽一格——`Annotation.from_dict` 对缺字段的
兜底是「现编一个」，而 `annotations_version()`（对外的 ETag）哈希的正是每条 `to_dict()` 后的
规范 JSON，`id` 和 `created_at` 都在里面：

```
id=str(data.get("id") or str(uuid4()))
created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat())
```

```
GET  → ETag: X       （这次 load 现编了一个时间戳）
PUT  If-Match: X     → 写锁里重新 load，算成 Y ≠ X → 409
```

客户端拿 409 里带回的「当前版本」重试，下一次 load 又是一个新值：**它永远追不上**，这本书
从此一个字也写不进去，界面上只剩一个点什么都没用的冲突对话框。

**✅ 已修（`bf09174`）**。规范化改成确定值，且只在**反序列化**这一侧：
- `created_at` 缺失 → `""`。不知道就说不知道，不要补一个「刚刚」。它只作排序次级键
  （`routers/notes.py:125` `:186`），`web/server.py:921` 早就在用同一个值。
- `id` 缺失 → 对「序号 ＋ 本条记录的规范 JSON」取 `uuid5`。**只取内容不够**：两条逐字节
  相同的无 id 记录会塌成同一个 id，而 delete 按 `a.id != note_id` 过滤，删一条会把两条
  一起删掉；序号把它们分开。

新建标注走 `Annotation(...)` 构造器，`default_factory` 逐字不变——本次改动碰不到它。

**红→绿**：`test_notes_legacy_record_etag_stability.py`（新，10 例）红 **6 failed / 4 passed**
（L3 真的以 `NotesVersionConflict` 挂掉，就是那条死循环），绿 **10 passed**；
unit lane **1601 passed, 2 skipped**，TOTAL 83%；ruff 干净；冻结集 8 条路径 diff 为空。

### WI-4 ✅ GET 的孤儿刷新要进锁（#1，should）

`routers/notes.py:91` 在不持 `_book_write_lock` 的情况下整份写回。跨进程（CLI 写入或第二个
worker）时，GET 能用旧快照覆盖掉一次已经提交成功的 `If-Match` PUT。

**验收**
- 读 / 刷新 / 写回三步在 `notes_service` 的同一把锁内完成。
- 确定性单元回归：GET 的孤儿刷新不得覆盖已提交的条件写。用事件同步，不用 sleep。

**✅ 已修（2026-09-23，`d071b53`）**。#1 原样成立。

`GET /api/notes/{book_id}` 与它的章级兄弟**看上去是读，实际上会写盘**：孤儿刷新发现某条标注
在正文里找不到了，就标成 `orphaned` 并重写整份 `notes.json`。那是一次货真价实的
load → 改 → save，和 add/delete/update 一模一样，唯独它不进 `_book_write_lock`：

```
GET  load → [ann1 活, ann2 "旧"]          （不在锁里）
PUT  load → 改 ann2 → save → 200 OK       （在锁里，If-Match 也对得上）
GET  save → [ann1 orphaned, ann2 "旧"]    （把 T0 的快照拍下去）
```

PUT 提交的那一版无声消失，而客户端手里拿着一个 **200**。011 WI-5a 的乐观并发看不见这件事
——比较只在写口里做，**而这个写者不是写口**。这是它所依赖的前提上的一个后门。

**修法**：`notes_service.refresh_annotations_and_version()` 把 load → 让调用者改 → 改了才
save **整段**放进同一把书级锁。**load 也搬进锁里是关键**：只包 save 仍然会拿锁外读到的陈旧
快照去覆盖。`routers/notes.py` 里 `_refresh_orphaned_annotations` 拆成纯内存的 `_mark_orphans`
（在锁里跑，不许碰盘）＋ 一次服务层事务；两条 GET 的 ETag 改用事务返回的版本，不再在锁外
重算一遍。响应体一个字段都没动（ADR-0011）。

**红→绿**：`test_notes_get_refresh_lock.py`（新，7 例＝4 交错 ＋ 3 护栏）在「refresh 算完、
save 未落盘」处下闸做确定交错，两个世界靠**不对称**判定——无锁时写者 B 毫秒级跑完被盖掉，
有锁时 B 堵在队里、等不到。红 **4 failed / 3 passed**（`assert '…旧正文' == '…提交成功的正文'`），
绿 **7 passed**；把锁去掉重跑，那 4 条如数变红。`fired == 1` 是**守卫的守卫**：谁把存盘挪回
路由的导入绑定（即绕开锁的那个改法），闸插不进去，测试会红着说「我没插进去」而不是悄悄变绿。
unit lane **1608 passed, 2 skipped**，TOTAL 83%；ruff 干净；冻结集 8 条路径 diff 为空。

### WI-5 ✅ 先复现再修「快照恢复仍存旧 CFI」（#3，must-pending-repro；顺带覆盖 #9）

`annotations.js:1514` 即便走了 `resolveOffsets`（:1433）的快照回退分支，`cfi` 仍由那个已失效的
`currentRange` 生成；渲染又优先用 CFI（:486-516）⇒ 正确存下的 quote 可能渲染成空高亮。

**验收**
- **第一步是复现**：在**新的、非冻结**的 e2e 模块里断言恢复出来的标注渲染文本**恰好**等于
  `NEW_QUOTE`，且 reload 之后仍然如此。
- 复现成功 ⇒ 用恢复出的 offsets 重建 Range 再生成 CFI，或在快照路径上干脆不写 CFI。
- 这条同时把 #9 要求的「渲染文本断言」买到手，**而冻结的 `baseline_1b` 一个字节不动**。

**复现结论（2026-09-23，必须写在这里）——#3 的现场只对了一半。**

推断本身成立，但 `annotations.js` 里那段算 `cfi` 的代码**一次都没执行过**：写侧取的是
`window.Reader3Epub.getContents()`，而 `epub-renderer.js:378` 把它实现成返回 epub.js 的
**View**，不是 `Contents`。View 上没有 `cfiFromRange`，于是
`typeof contents.cfiFromRange === "function"` 恒假、`cfi` 恒为 `null`。浏览器里实测：
View 原型链上只有 `highlight/mark/locationOf/…`，真正的 `Contents` 挂在 `view.contents`
上，它才有 `cfiFromRange` 与 `range`。所以**这套 UI 新建的标注从来不带 cfi**，
「快照回落写下一条陈旧 cfi」今天无法当场发生。

于是缺陷分两层，**能当场咬人的是第二层**：

- *潜伏的*（写侧）：哪天有人把 `getContents()` 接到真 `Contents` 上、或换一版 epub.js，
  那条「拿失效 Range 算 cfi」的路当天就活过来。
- *现役的*（读侧）：`render()`（:489-516）对带 `cfi` 的标注**无条件优先**用 CFI 重锚，
  `rangeFromCfi` 只要解析得出来就用，从不与 `quote` 对照。一条指向别处或塌成一点的
  `cfi`——旧数据、别的客户端写的、将来那条潜伏路径写的——当场让用户看见一道划在错地方
  的线，或者一道空的，而盘上 `quote` 完全正确。**这一层实测复现，见下。**

**修法：一条对称的规矩，两侧各执行一次**——*一条 `cfi` 只有在它和 `quote` 对得上时，
才值得写、才值得信*。读侧新增 `cfiRangeAgreesWithQuote()`，解析出来的 Range 与 `quote`
不一致（含塌成零宽）就退回文本匹配；写侧在算 `cfi` 之前先要求活 Range 取出来的文字
**正是**要存的那段 `quote`，否则不写（即 #3 给的第二条处方）。

**实测**（`tests/e2e/test_stored_cfi_must_agree_with_quote.py`，3 条，非冻结白名单模块）：
修复前 2 红 1 绿——「cfi 指向别处」屏幕上罩住的是 `'Alph'` 而不是 `'prose'`；
「cfi 塌成一点」罩住的是空串。修复后 3 绿。护栏那条（`repeat_data` 同句重复 25 遍，
cfi 指第 21 次、文本匹配必落第 1 次）在把 CFI 分支整个失效时当场红（偏移 1596 → 36），
所以「删掉 CFI 重锚」换不到绿。

**新欠账（本分支不做，单独立项）**：`getContents()` 返回 View 导致 CFI 写路径全程是
死代码。接通它意味着每条新标注都带 cfi，渲染从「文本匹配 ＋ 相邻段合并」整体切到
「一条标注一个 mark」，重叠标注、`data-annotation-ids`、孤儿判定全部换一条路——而
`baseline_1b` 是冻结的，兜不住这个代价。

### WI-6 ✅ 冲突解决同时只许有一个在飞（#5，must）

`resolveConflict()`（:1261）在「保留我的」PUT 还没回来时，两个按钮都还能点。点「采用远端」会
立刻 settle，而那个在飞的 PUT 回来后仍会 `settleConflict(c, c.localText)`，把用户最后的选择反掉。

**验收**
- 提交期间两个按钮都 disabled；属于已过期 conflict 实例的回调被丢弃；重复点击不能把已解决的
  冲突重新打开。
- e2e 落在非冻结模块。

**✅ 已修（2026-09-23）**。#5 原样成立，一条不用改。

**修成了三层，方向不同，谁也替不了谁**：

1. `setConflictBusy(true/false)` 把两个出口一起 `disabled`（＋ 对话框 `aria-busy`）——
   给人看的那一层。
2. `resolveConflict()` 开头的 `conflictSubmitting` 单飞守卫——`disabled` 是一条 DOM 属性，
   一次重绘、或任何绕过按钮直接调公开的 `Reader3AnnotationUI.resolveConflict(...)` 的路径
   都能越过它；守卫在函数里，越不过去。**「采用远端」也一并拒**：它不发请求，却会当场把
   冲突收掉，正是这一下让在飞的写回来时反转用户的选择。
3. PUT 回来之后的身份核对 `this.pendingConflict !== c`——前两层挡「新的调用进不来」，
   这一层挡「回来的这一次还算不算数」。不算数时**只记账不收尾**：那次写可能已经落地
   （盘上确实是本地那版），拒绝的是替它宣告收尾、拿过期的 `localText` 盖掉用户此刻正在
   编辑的那一格。

两种拒绝都走 `reportNotesWriteFailure`（`conflict-busy` / `conflict-stale`），于是各自
在诊断环 ＋ console ＋ toast 三处留痕——它们都不改屏幕，只看 DOM 分不出「守卫挡住了」
和「代码压根没跑到」。

**测试**：新增 `tests/e2e/test_conflict_resolution_single_flight.py`，4 条，按「拆掉一层、
看下一层接不接得住」排：第 1 条只用第 1 层；第 2 条**在页面里把 `disabled` 抹掉**再点，
断第 2 层（顺带钉住「在飞期间无论点几次，发出去的写恰好一次」）；第 3 条把
`pendingConflict` 换掉并在编辑器里放哨兵，断第 3 层；第 4 条是退化护栏——没有并发干扰时
照旧写盘、收尾、把按钮放开，否则「全程 disabled、永不收尾」也能让前三条全绿。
三层逐一注掉验证过：每次**只红对应的那一条**。

**冲突是真的，被桩住的只有「写请求什么时候回来」**：409 由服务端乐观并发真发出来，
`_install_put_gate()` 只是在页面里把发往 notes 的 PUT 扣在半空——不把那次写停住，
「在飞期间点另一个按钮」这件事根本没有时间发生。另有一处稳定化手脚必须写明：
`_pin_if_match()` 把那次保存的 `If-Match` 钉成旁路写之前读到的版本。原因是客户端的版本号
**事件驱动**刷新（三个事件 → 80ms 去抖 → 重新 GET），旁路写之后若恰好落下一次刷新，
冲突就造不出来——实测连跑两遍，一遍造出来了，一遍四条全卡在「对话框没出现」。钉之前先
记下客户端自己带的那个值并断言它非空，所以「客户端确实在参与乐观并发」没有被糊掉；
而「它带的对不对」本来就是 `acceptance_2a/test_deg_s5_write_conflict.py` 的判据。

**红→绿**：红 3 失败 1 通过（通过的那条正是退化护栏，它本来就该绿）；绿 4 passed。
全量 e2e **120 passed, 16 skipped**；unit **1608 passed, 2 skipped**；
`scripts/lint_e2e_groups.py` rc=0（收集 136；`baseline_1b` 68/68；白名单 51/51）；
八条冻结路径 `git diff --stat master` 为空。

### WI-7 ✅ 编辑器正文和它的 base ETag 必须绑在一起（#4，should）

`:1297`「采用远端」把 A1 放进 textarea，而 `loadAndRender()` 把全局 ETag 更新成了 A2 的——
之后保存就是「A1 的正文配 A2 的令牌」，绕过冲突检测。

**验收**
- 要么同时采纳当前正文与当前令牌，要么保留所显示版本的令牌，使后续修改仍然会冲突。
- 单元或 e2e 断言：第三次远端编辑发生后保存，必须 409，不得静默覆盖。

**改法**：`notesEtag` 跟着**读**走，屏幕上那一版跟着**收尾**走，两者会分家——所以给
「正在编辑的这一版是从哪个版本长出来的」单独记一个 `notesEditBaseEtag`（`annotations.js`
模块级，配 `setNotesEditBase()`）。收尾时钉：「采用远端」钉 409 体里报来的那一版（正文
就是从那儿来的，为此 `openConflictFromResponse` 把 `remoteEtag` 一并记进 `pendingConflict`），
「保留我的」钉自己那次写回来的那一版（正文就是那次写上去的）。钉必须发生在
`settleConflict()` 里的 `loadAndRender()` **之前**——那次读正是把全局版本换掉的地方。
`saveNote()` 的编辑分支改用 `notesWriteHeaders(..., { useEditBase: true })`，优先带这枚钉子。

两条配套规则，缺一枚钉子就会从「修好一个洞」变成「换一个洞」：
- **只被自己提交成功的写推进**：`rememberNotesEtag(resp, { isOurWrite: true })`（编辑写、
  `notesWriteWithResync` 的建／删）同时推进钉子；读路径（`loadAndRender()`）一律不碰。
  否则客户端自己删掉另一条标注就会让下一次保存误撞 409。
- **`editingNoteId` 与钉子成对赋值**：谁让编辑分支变得可达，谁就得说清基准是哪一版。
  两处成对点是 `openNoteEditorWithExisting()`（新一轮编辑 → 钉子清空，回落全局值）与
  `settleConflict()`（收尾 → 钉住收尾那一版）。关编辑器那处**不再**清：`editingNoteId`
  一清，编辑分支就不可达，钉子读不到——加一句谁都不盯着的清空只是多一行无人负责的代码。

**测试**：新增 `tests/e2e/test_conflict_settled_text_keeps_its_base_etag.py`，4 条。第 1 条
就是验收那句话：409 之后、点「采用远端」之前第三方再写一版 R2，收尾把 R1 放进编辑器，
此后保存**必须** 409——判据两条，看得见的（对话框再开一次且摆出 R2，用户第一次有机会
看见它）与盘上的（R2 还在，没被盖掉）。第 2 条钉「跟着自己的写前进」：保留我的成功之后
紧接着再保存一次不许误冲突（把两支都钉成 409 体里那一版是最顺手的写法，它能让第 1 条
变绿，却会让这里每次保存都撞上自己刚写出去的版本）。第 4 条钉「随编辑会话结束而消失」：
收掉冲突、关编辑器、别处再写一版、催一次刷新等它落地，重新点开这条笔记保存——必须成功，
否则一次冲突之后整页的笔记编辑全废。第 3 条是退化护栏：没有第三方时收尾之后照旧保存成功，
否则「所有保存一律 409」也能让第 1 条变绿。三条边界逐一破坏验证过：**每次只红对应的那一条**。

**共用夹具搬了家**：造冲突、扣住写的那些手脚从 WI-6 的模块里抽进
`tests/e2e/notes_conflict_support.py`（文件名不以 `test_` 开头，不贡献 item，分组守卫
的三个数不受影响），两个模块共用；判据一条都没搬，仍各自留在自己的测试文件里。
新增 `install_notes_get_counter()`：只**数**「notes 的 GET 回来了几次」，用例据此等收尾
那次读落地之后再保存——不等的话保存可能抢在读前面发出去，撞不撞 409 由时序决定，红绿都不作数。
`pin_if_match()` 那道稳定化手脚照旧（理由见 WI-6）。

**红→绿**：红 1 失败 3 通过（失败的正是验收那条——缺陷态下保存被静默收下，对话框根本
没出现；通过的三条都是护栏，它们本来就该绿）；绿 4 passed。全量 e2e
**124 passed, 16 skipped**；unit **1608 passed, 2 skipped**（coverage TOTAL 83%）；
`scripts/lint_e2e_groups.py` rc=0（收集 140；`baseline_1b` 68/68；白名单 55/55）；
选择器 lint 0 违规；八条冻结路径 `git diff --stat master` 为空。

### WI-8 ✅ 异常策略与写入契约文档（#32、#33，should）

- **#32**：`_provider_retry_budget()`（`server.py:633`）新增了 `except Exception  # noqa: BLE001`。
  `AGENTS.md:68-72` 允许既有豁免、**明确禁止新增**。改成捕获具体的配置读取／解析异常，
  让真正的编程错误照常抛出。
- **#33**：可选 `If-Match`、书级 ETag、409 载荷（含 `annotation: null`）只存在于代码与计划文档里。
  按仓库的文档同步规则写进 `docs/technical-detail.md`；顺带改掉 `routers/notes.py` 开头那句
  「路由体未变」——它现在是假的。

**验收**：`rg 'noqa: BLE001' src/` 不含本次新增的那一处；技术文档里能查到 409 载荷形状。

**#32 的改法**：异常元组是**照着调用链数出来的**，不是猜的宽口径——`_read_settings_file` 已经把
`json.JSONDecodeError` 与 `OSError` 包成了 `AiSettingsError`，`get_provider_settings` 自己会因为
缺 `model_name` 或 `int()` 解析失败抛 `ValueError`／`TypeError`。于是 `except` 收窄成这四类，并在
注释里逐条写明它们各自从哪来。`AttributeError`／`KeyError`／`NameError` **故意不收**：那是编程错误
的签名，吞掉它正是 #32 反对的事。

**#32 的测试**：`tests/unit/test_provider_retry.py` 新增两条——R10c（配置坏成别的类型时照样退化成
0 次重试，`ValueError`／`TypeError` 各跑一遍）、R10d（查配置时的 `AttributeError` 必须**原样**抛出，
断言 `excinfo.value is boom`，且请求一次都没发出去）。R10d 在收窄之前是红的，这正是它存在的理由。

**#33 的落址**：`docs/technical-detail.md` 是索引（Contents／Recent updates／Update Rule），契约本身
不该写在索引里。所以写进 `docs/storage-and-data-locations.md` §「Book notes & annotations (003)」下新开的
「Write contract: optimistic concurrency (011 WI-5a)」，那里已经是笔记落盘格式的定义处；
`technical-detail.md` 只加一行指路，`routers/notes.py` 的头注释也改成指向那里而不是复述。
顺带补上「Related API endpoints」里**一直缺席**的 `PUT /api/notes/{book_id}/{chapter_index}/{note_id}`。

**「路由正文一字未改」那句**：没有删，而是限定到它当初描述的那一步（011 WI-4 的搬家），并明写
此后 011 WI-5a 与 017 WI-3／WI-4 都改过路由正文。删掉会丢掉「搬家那次确实没动逻辑」这条信息，
那是当初写它的全部用意。

**红→绿**：R10d 先红（`DID NOT RAISE`）→ 收窄 `except` 后
`uv run pytest tests/unit/test_provider_retry.py tests/unit/test_provider_call_budget_wiring.py -q` **50 passed**；
`ruff check src/` 干净；`grep 'noqa: BLE001' src/reader3_app/web/server.py` 只剩两处既有豁免（:314、:439）。

### WI-9 ✅ AI 队列租约测试（#13、#14，should）

- **#13**：Q4 的 `stuck_gate` 并不保证 worker 已经进到第二次 `readline()`。用「阻塞读已进入」
  事件同步；清理时释放 gate 并 join worker。
- **#14**：把 gate 换成可观测的——记录 `wait()` 进入与其 timeout 参数。**验收判据**：把实现换成
  无条件 `sleep(3)`、完全无视 gate，这条测试必须变红（现在它会绿）。

**改法**：两条审计其实共用一个缺口——「卡住」这件事**只能从外面按时长观察**。裸
`threading.Event` 给不出「有人真的进来等了」这个正面事件，于是 #13 只能赌时序、#14 只能断时长。
新增 `_ObservableGate` 把三件事记下来：进没进过 `wait()`（`wait_until_entered()`）、进去时带的
timeout 实参（`wait_timeouts`，必须是 `[None]`）、谁在里面等（`waiter_thread`，收尾 join 用）。

**#13 的两半**：
- *同步*：`_disconnect_after_first_chunk()` 新增可选的 `before_disconnect` 钩子。Q4 在断连**之前**
  等 worker 真的进到闸里。拿到第一个 chunk 不等于 worker 已经开始读第二行——它还可能卡在
  `call_soon_threadsafe` 到下一次循环顶之间（`routers/ai/chat.py:248-253`），那一瞬翻起 stop_event
  的话 worker 会在循环顶上**干净地 return**，Q4 的前提当场自毁。这不是把窗口调大，是取消窗口。
- *收尾*：放行之后 **join** 那个线程并断言它真的结束了。join 结果先收集、出了 `finally` 再断——
  在 `finally` 里 assert 会把 try 体里真正的失败盖掉。

**#14 的验收判据照着原文做了**：把假流的阻塞换成无条件 `time.sleep(3)`、完全不碰闸（M1）——
- 打在**改之前**的文件上：**7 passed**（全绿，正是审计说的「现在它会绿」）；
- 打在**改之后**的文件上：**2 failed / 5 passed**，红的是 `test_假流的卡住由放行闸决定而不由墙钟决定`
  与 `test_Q4_...`。同一个变异同时钉住两条审计：#14 要的正面证据，和 #13 那个「worker 必须已经
  进到第二次 readline」的前提。

**#13 收尾那一半单独有变异盯着**：拿掉 Q4 `finally` 里的 `stuck_gate.set()`（M2）⇒ join 超时 ⇒
`AssertionError: 收尾之后 worker 线程的状态: [True]（期望 [False]）`，**1 failed / 6 passed**，
只红 Q4 一条。

**绿**：`uv run pytest tests/unit/test_ai_queue_lease.py -q` **7 passed**；
unit lane **1610 passed, 2 skipped**（TOTAL 83%）；`ruff check tests/` 干净。

**一处说清楚的局限**：「断连早于 worker 进闸」这个竞态本身**无法在不改产品代码的前提下确定性地
复现**——那个窗口是纯调度（`call_soon_threadsafe` 到下一次 `stop_event.is_set()` 之间几微秒）。
所以这里不假造一次红，而是把前提从「赌它成立」换成「等到它成立，等不到就红且说得清原因」。

### WI-10 ✅ egress 两处证据要分阶段（#16、#18，should）

- **#16**：断言 status 200、provider 恰好被调用两次、`answer == "fallback"`、以及既有的
  `rag_fallback` 路由元数据，然后再清 ledger。
- **#18**：C11／C14 必须要求「探针体通过 **且** 恰好一次 teardown 错误 **且** setup 零错误」；
  C14 的 disarmed 对照现在整个跳过了 fixture 执行，要让它真的跑。

**#16 的改法**：C4 原来只看 ledger 里记了什么，没人问过那次请求到底成没成。四条断言补在
`recorded.clear()` **之前**（顺序是审计点的名）：`status_code == 200`、
`calls == ["anthropic", "anthropic"]`、`answer == "fallback"`、
`metadata.routing.mode == "rag_fallback"`。两次变异各钉一条：让兜底那次调用抛异常 ⇒ status
断言变红；把兜底返回的正文改成 `"MUTATION-M2"` ⇒ `AssertionError: answer 是 'MUTATION-M2'…`。

**#18 的改法**：`failed_or_errored(out) == 1` 把**三种结局**算成同一个 1——「用例体自己红了」
（1 failed）、「setup 就炸了、体一行没跑」（error at setup）、以及唯一想要的「体通过、teardown
判红」。前两种下最后那行 `assert egress_violations == []` **一次都没被求值**，而这两条用例存在
的全部理由就是求值它。C11 与 C14 的驱动器都换成点名阶段与主体：`failed == 0`、`passed ==` 预期
条数、`error == 1`、`"ERROR at teardown of <探针体名>" in stdout`、`"ERROR at setup of" not in
stdout`；干净／disarmed 那轮另加 `"ERROR at" not in stdout`——一道没出网也判红的闸，会让脏那轮
的红不可归因。

**C14 的 disarmed 对照原来是假的**：模块级 `pytestmark = skipif` 会把 autouse fixture 一起跳过，
于是「没装闸所以不红」和「装了闸但闸坏了」在它眼里一模一样。改成把 skipif 降成**单条**装饰器，
另加一条**永远运行**的用例，直接断言此刻 `socket.socket.connect.__qualname__` 收尾于
`no_real_egress.<locals>._boom`——闸装没装从此是正面事实，不是缺省推断。

**红→绿**（C11 的变异 M2，一道「只抛不记」的闸 ＋ 一条不吞异常的脏用例）：脏那轮
`1 failed / 1 passed / 0 error`，`failed_or_errored` 算出来**正好是 1**，旧断言全绿——尽管
teardown 那行从头到尾没被求值。新断言在 `failed == 0` 上变红，报文里带着摘要
`{'failed': 1, 'passed': 1, 'error': 1}`。

**绿**：`tests/unit/test_egress_backstop_subprocess.py` **2 passed**；
`tests/unit/test_egress_backstop_unit.py` **27 passed**；探针实测行为与断言逐字对上——
disarmed `1 passed, 1 skipped`，armed `2 passed, 1 error` 且
`ERROR at teardown of test_the_probe_swallows_its_own_egress_and_leaves_no_trace_in_the_body`。
unit lane **1612 passed, 2 skipped**（TOTAL 83%；较 WI-9 的 1610 多出的两条，正是两个探针模块里那条「闸真的装上了」的常驻用例）；`ruff check tests/` 干净。

### WI-11 ✅ 覆盖率闸门每个指标都要有失败用例（#17，should）

`test_coverage_gate_failclosed.py` 的 G12 用 100% 覆盖只校验输出文案。内存里把 `lines` /
`statements` 改成无条件接受，22 条断言全绿，同时放行 `book_store.py` 的 0%。

**验收**：`lines` 与 `statements` 各有低于门槛的参数化用例，失败信息必须点名指标、实际值、门槛值。

**改法**：这个文件此前**只有 `branches`** 有过一条真的低于门槛的用例（G9）。`lines` /
`statements` 从头到尾只出现在「满分照样放行」和 G12 那两行 `"lines" in out and "statements"
in out` 里——后者查的是**文案**，不是判决。新增 G14：逐指标参数化（两项在 `METRICS` 里**共用
同一对计数键** `covered_lines` / `num_statements`，唯一的区别就是键名那一步查表，合成一条就分
不出「两项都判了」和「判了一项、另一项名字写错但恰好没人看」），配 90% 门槛、喂 12% 实测，断
退出码非零并**三样都要**：点名指标、实际值 `12.00`、门槛值 `90`——少任何一样，看报告的人都得
回去读脚本才知道该改什么。另配一条边界对照：恰好踩在 90% 上必须**通过**；没有它，「一律判
FAIL」也能让上面两条变绿，而那是一道谁都过不去的闸。

**红→绿**：第一次变异（两项直接 `continue`）太粗——它把 `checked` 也清成 0，于是撞上「一条门
槛都没配」那道无关的闸，改之前的 22 条里就有 2 条变红，不构成审计说的那个局面。换成 M2：照常
`checked += 1`、照常打印 PASS，只把判决翻掉。结果与审计原文逐字对上——**改之前 22 passed 全绿**，
而 `book_store.py` 的 12% 一路放行；**改之后 2 failed / 24 passed**，红的恰好是新增那两条。

**绿**：`tests/unit/test_coverage_gate_failclosed.py` **26 passed**（原 22 ＋ 新 4）；
真实配置下 `uv run python scripts/check_coverage_gate.py` 仍 **PASS**（rc=0）；`ruff` 干净。

### WI-12 ✅ 并发测试去抖、去挂（#23、#24，should）

- **#23**：反向对照靠「保存屏障两秒超时」推进，不能证明第二个写者已过锁外预检。改用显式事件；
  正向用例也用事件确立争用，不拿耗时当证据。
- **#24**：worker 是非 daemon 线程，`:582` 断言一响就跳过 `barrier.abort()`，死锁回归会把
  pytest 挂住。改成子进程跑 + 父进程强制超时与回收；`barrier.abort()` 进 `finally`。

**#23 的改法**：争用从「等 2 秒，然后假定对方应该就位了」换成**正面观察**。新增
`ObservableBookLock`（`tests/fixtures/notes_concurrency.py`）：`__enter__` 先做一次非阻塞
`acquire`，拿不到就先把 `someone_is_waiting` 立起来、**再**去阻塞——非阻塞失败那一刻，锁
**确实**被别人持有，这是事实不是推断。它按 `os.path.abspath(_lock_path(...))` 塞进
`_BOOK_THREAD_LOCKS`，产品代码一行没动。正向用例里第一个进到 `save_annotations` 的写者等的
就是这个事件，等到了才往下写。

反向对照的会合点从 `save`（锁**内**）搬到了**锁外的预检点**。老写法那个屏障在正确实现下
根本不可达——第二个写者正卡在锁上——于是它只能靠超时往下走，而它要证明的唯一一件事恰恰是
「第二个写者已经过了锁外预检」。新的会合点一定可达，所以「屏障没破」本身就是那句话的证据。

**#24 的改法**：整场编排搬进 `multiprocessing` 子进程（spawn），父进程 `join(60s)` 之后
`kill()`。**线程留着没换成两个进程**：这两条用例问的是「一个服务进程里的两个请求」，判决点
是 `_book_write_lock` 里那把 `threading.Lock`；跨进程那一半已由 `test_notes_concurrent_write.py`
用 flock 守着，换成两个进程等于把问题换掉。子进程内部收尾一律进 `finally`。

**红→绿，三次变异**：
- **M1**（把 `_require_version` 挪到锁外，即审计描述的那种坏实现）⇒
  `AssertionError: 期望一胜一冲突，实得 ['ok', 'ok']`。核心判断仍然有牙。
- **M2**（把装锁的键改错一个字，于是那把可观测锁**根本没装上**）⇒
  `没有观察到第二个写者在等这把书级锁……实得证据：{'second_writer_blocked_on_the_lock': False}`。
  新加的证据断言不是装饰：一个从头到尾没发生过争用的编排，现在会红而不是安静变绿。
- **M3**（子进程里造一场真正的死锁：等一个永不到来的事件，等待上限拉到一小时）⇒ 父进程在
  硬上限处判红并 `kill()`，**5.37s 退出**，pytest 正常结束。老写法在这里是**挂住**——而挂住的
  CI 没有人读得懂。

**顺带**：正向那条用例的耗时从「2 秒屏障超时」降到毫秒级——它本来就不该为等待付钱。
反向对照原来要付两次超时（≈4s），现在一次都不付。

**绿**：`test_notes_optimistic_concurrency.py` ＋ `test_notes_concurrent_write.py`
**26 passed in 4.59s**；`ruff check tests/` 干净；冻结集 8 条路径 `git diff` 为空
（`tests/fixtures/notes_concurrency.py` 不在冻结集里——冻的是 `epub_corpus` / `epub_zip` /
`ai_stub` 三个）。

### WI-13 ✅ 两条「实现坏了也能过」的护栏（#21、#29，should）

- **#21**：`_BLOCK_TAIL_RE` 只看尾部序列。在 `saveNote` 的上报调用前插一句 `return;`，整条护栏
  测试照样全绿——它自称能查死代码。改成拒绝上报之前出现可执行语句（尤其是提前 return），
  并补针对检查器本身的变异用例。
- **#29**：子进程 rc=0 且没出现 `BrowserType.launch`，并不证明测试跑过。注入 `1 skipped` 的子进程
  结果，这条测试照样通过。改成要求恰好 1 passed、0 skipped/xfail，并加一条 skipped 的负对照。

**先复现，再改**。#21：在 `annotations.js:1427` 的 `reportNotesWriteFailure({op:
"save-empty-text"…})` 前插一句 `return;`，那条上报从此是死代码——
`test_notes_failure_guards_instrumented.py` 实测 **1 passed**。#29：写一个整条 `pytest.skip`
的子进程，退出码 **0**、输出里没有 `BrowserType.launch`——旧的两条断言一条也拦不住。两个洞
同形：**都在用否定去推一个正面事实**。「上报是活代码」不等于「块尾有上报」，「那条用例跑过
并通过」也不等于「没红、没见浏览器」。

**#21 的改法**：`_check_guard` 在算出 `inner` 之后多一段——上报调用之前的文本必须是纯空白，
否则报「`runs 'return;' before reporting`」并把拦下的那段原样抄进失败信息。判据取「上报必须
是块里的第一条语句」，而不是逐个点名 `return` / `throw` / `break`：后者要求我预先想全所有能让
下一行变成死代码的写法，而这正是 #21 已经证明想不全的那件事。注释不受影响——`_views` 早把它们
抹成了空格。代价写明：以后若真有登记位需要先算一个值再上报，这里会红，那是 fail-closed 的一侧。

**#21 的变异用例**：新增 10 条，喂合成 JS 走完整条真路径（`_views` → `_slice_function` →
`_check_guard`）。不在真文件上注入，是因为八个登记位共用两个逐字相同的守卫条件，在那上面动手
会同时惊动别的登记位，红的原因就说不清了。一条阳性对照（正确写法必须判绿）、一条注释边界
（注释不是可执行语句，不许被误伤）、八条破坏写法各自要求失败信息里出现指定字样——**红得对不对
和红不红一样重要**，否则某一条红可能是别的判据顺手撞出来的。

**#29 的改法**：判据搬进 `_lane_problems(returncode, out)`，读 pytest 摘要计数，要求**恰好
1 passed**，且 skipped / xfailed / xpassed / failed / error / deselected 全为 0；摘要行解析
不出来也判红（fail-closed）。单拎成函数是为了让它**可被打**——不然要证明这套判据有效，唯一
的办法就是去破坏被守护的那条真用例。

**#29 的负对照**：5 条，每条都真跑一个子进程，**不用手搓字符串**——手搓 `"1 skipped in 0.01s"`
只能证明解析器认得我写的那行字。四条坏结局（整条 skip、xfail、跑一条跳一条、跑了两条）
**逐条都满足旧的两条断言**，所以它们是 #29 的复现而不是「随便一个红」；第五条是阳性对照。
「跑一条跳一条」只有「逐种结局单独点名」那段拦得住（passed 确实是 1），「跑了两条」只有
「恰好 1」那段拦得住——两段判据各有一条对照盯着。「一条都没收集到」刻意不在这一族里：pytest
对空收集给 rc=5，压根满足不了旧断言的前提，放进来只会把主张稀释成「某些坏结果会红」；那条
分支另由 `test_the_verdict_refuses_output_it_cannot_parse` 单独盯着。

**红→绿，四次变异**：
- **M1**（`annotations.js` 里在上报前插 `return;`）⇒ 红，`guard block at line 1427 runs
  'return;' before reporting`。改之前这同一个变异是 **1 passed**。
- **M2**（把新加的 head 判据整条摘掉，等价于回到审计之前的检查器）⇒ **恰好 2 failed**
  （`early_return_before_the_report`、`early_throw_before_the_report`），其余 9 条全绿。变异用例
  打的是它该打的那段，没有株连。
- **M3**（head 判据改成看**原始**源码而不是 `no_comments`）⇒ **恰好 1 failed**
  （`the_checker_ignores_comments_before_the_report`）。注释边界那条不是摆设。
- **M4**（#29 的四条坏结局子进程）⇒ 逐条被 `_lane_problems` 判红，且理由里点名了对应的那一种
  结局；阳性对照判绿。

**绿**：`test_notes_failure_guards_instrumented.py` **11 passed in 0.15s**（原 1 条）；
`test_unit_lane_has_no_browser_dependency.py` **7 passed in 1.83s**（原 1 条）；unit lane
**1632 passed, 2 skipped in 68.84s**（WI-12 后是 1616，+16 正是新增条数）；`ruff check` 干净。
本项只动 `tests/unit/` 两个文件，`annotations.js` 与冻结集 8 条路径 `git diff` 均为空，
`tests/e2e` 收集数不变。

### WI-14 ✅ 子进程要有超时；语义依赖要逐个缺（#19、#25，should）

- **#19**：`test_book_store.py:686` 的 `subprocess.run()` 无 timeout，导入死锁会把测试挂到天荒地老。
  加有限超时，`TimeoutExpired` 时打印捕获输出。
- **#25**：所有依赖失败用例都停在 `import chromadb`。只屏蔽 `sentence_transformers` 时
  `_require_semantic_deps()` 会通过，然后构造 embedding 时抛 `ValueError`——而 CLI 新加的
  `except RuntimeError` 接不住。逐个依赖单独测，含构造器路径，并断言 CLI/HTTP 的实际出口。

**#19 的改法**：`IMPORT_PROBE_TIMEOUT_S = 60.0`，超时走 `pytest.fail` 并把
`TimeoutExpired.stdout` / `.stderr` 原样打出来。这一条正是为了在 import 期抓问题而存在，而
import 期最难看的那种问题——模块级取锁、`__init__` 里起线程再 join——表现就是**卡住**，不是
报错；无上限的 `subprocess.run()` 会把它呈现成「unit lane 还在跑」。变异（子进程先打一行
`PROBE-STARTED` 再 `sleep(3600)`，上限调到 3s）⇒ **3.19s 判红**，失败信息里带着那行
`PROBE-STARTED`。改之前这个变异是**挂住**。

**#25 是产品缺陷，不只是测试缺口**，先复现再改。`chromadb` 装着、`sentence-transformers`
没装时（`uv sync --extra semantic` 装到一半被打断，或手工 `pip uninstall`），
`_require_semantic_deps()` **通过**——`SentenceTransformerEmbeddingFunction` 只是个类对象，
import 它不需要底层包——失败推迟到构造那一刻，实测：

```
A) _require_semantic_deps OK -> _ProtocolMeta
B) _prepare_deps raised ValueError : The sentence_transformers python package is not installed.
   isinstance RuntimeError: False
```

于是 CLI 的 `except RuntimeError` 漏成裸 traceback，HTTP 落到兜底的 `except Exception` 给
**500**——而缺一个可选依赖是用户自己能修的配置问题，500 让前端没法把它渲染成「可补救」。
本文件此前把 `_require_semantic_deps()` 描述成「唯一的 import 点，也是唯一的转译点」，
第二个半句是错的。

**改法**：新增 `vector_search._build_embedding_function()`，把构造期的
`(ImportError, ValueError)` 转译成 RuntimeError，原文留 `__cause__`。补救文案抽成
`_EXTRA_HINT` 一处定义。**捕获刻意收窄**，不是 `Exception`：模型名写错、权重下载失败是别的
毛病，把它们也说成「依赖没装」会把人指向错误的修法。chromadb 那句
`pip install sentence_transformers` 刻意不转给用户——它把包装在 extra 之外，正是 011 WI-7
要防的那件事，所以黑名单从 `uv add` 扩成三条。

**测试**：C10/C11/C12 各按三种形态参数化（两个都没装 / 只缺 chromadb / 只缺
sentence-transformers），分别断 `_prepare_deps` 的异常类型、**CLI 的实际出口**（SystemExit
而非 traceback）、**HTTP 的实际状态码**（400 而非 500）。C10 还正面观察构造器**有没有被调到**
——不然三条用例可能全停在 `_require_semantic_deps`，「逐个依赖单独测」就成了三份同样的测试。
「只缺 X」形态在没装 `[semantic]` extra 的机器上不可构造，`_skip_if_unconstructible()` 跳过
并说明，不让它变成名不副实的绿。C13 单独钉转译的边界（喂假 factory，不碰真依赖）。

**红→绿，两次变异**：
- **M1**（撤掉构造器转译，回到审计之前）⇒ **恰好 3 failed**，全是 `只缺sentence_transformers`
  那一支（C10/C11/C12 各一），其余 21 条全绿。新增的形态打的正是它该打的那条路。
- **M2**（捕获放宽成 `except Exception`）⇒ **恰好 1 failed**（C13）。窄捕获不是摆设。

**绿**：`test_semantic_extra_optional.py` **25 passed in 1.48s**（原 15）；
`test_book_store.py` **21 passed in 0.38s**；unit lane **1642 passed, 2 skipped in 64.10s**
（WI-13 后是 1632，+10 正是新增条数）；`ruff check` 干净；冻结集 8 条路径 `git diff` 为空。

### WI-15 ✅ e2e 先等响应再轮询磁盘（#8 的非冻结调用点，should）

`wait_for_notes()` 用 Python `time.sleep` 轮询，期间 Playwright 的同步 route 回调跑不了——
正确的产品行为也会超时。这正是 #43 那族 flake 的机制。

**范围**：`tests/e2e/test_notes_write_failure_is_attributable.py:1283` 与
`tests/e2e/acceptance_2a/test_deg_s5_write_conflict.py:203` 两处。
**冻结的 `baseline_1b/test_w8a_selection_survives_rerender.py:132` 不动**（见 §5）。

**验收**：这两处先用 Playwright 等到相关写请求的响应，再轮询磁盘。

**机制**：`wait_for_notes()` / `wait_for_note_text()` 整个窗口里一次都没调进 Playwright，而
同步 Playwright 的 route 回调是 Python 函数，只在主协程调进 Playwright 时才被派发。
`tests/e2e/conftest.py` 给每个 context 都挂了一道 `**/*` 的出网闸，于是**每一个**请求都要过
这样一个回调。点完按钮直接轮盘 ⇒ 这次写卡在回调上跑不动，轮询等满超时，**产品行为完全
正确也会红**；谁先被调度是随机的，这就是「红出来的用例每次不同、却全挂在同一族断言上」。

**实际范围比点名的两处多两处**。用 `ast` 扫这两个文件，18 处盘上轮询里有 16 处的最近一次
点击没被响应等待裹住。**没有**全改：其中多数中间隔着 `_wait_until` / `expect(...)` /
`settle_marks` 这类**会泵事件**的等待，够不够取决于那个等待的条件与这次写的关系，逐个判定是
#8 之外的工作。改的是点名的两处，**加上 `_run_conflict_round()` 里同形且同样无遮挡的另外
两处**（`:217` A 改 A1、`:316` 清场删除）——同一个函数里三处一模一样、只修一处讲不通。

**`:264` 刻意不改，并写进豁免表**：那一处前面是 `dialog.get_by_test_id(branch.exit_testid)`，
而「采用远端」那一支按契约**一个字节都不往服务端写**（同函数 (d) 段正是断言它没有写）。给它
挂 `expect_response` 会在那一支上等到超时——那是把一条真实的分支语义改成挂死，不是修好。

**冻结的 `baseline_1b/test_w8a_selection_survives_rerender.py:132` 是同一个毛病，不动**；
护栏有一条用例专门钉「登记表里不许出现冻结路径」。

**改法**：
- `test_notes_write_failure_is_attributable.py` W4-C3：把删除点击裹进
  `page.expect_response(method == "DELETE" and other_id in r.url)`。这里**必须点名
  `other_id`**：紧随其后的 `_wait_until` 只等到**失败**那条的诊断条目，对成功那条什么都没说。
- `test_deg_s5_write_conflict.py`：新增 `_click_awaiting_write()`，三处调用点各换一处。
  谓词**刻意不写死方法名**（`method in WRITE_METHODS`）——写死成 POST/PUT 只会在实现换方法时
  把一条真断言变成挂死。两处都用 `try/except PlaywrightError -> AssertionError`，照
  `test_notes_write_failure_is_attributable.py:1968` 已有的先例。

**护栏**：新增 `tests/unit/test_e2e_disk_poll_waits_for_response.py`（unit lane，14 条）。用
`ast` 而不是字符串匹配：登记函数里每一次盘上轮询之前，最近的那个「点击步骤」必须裹在
`with ...expect_response(...)` 里。三处静默失效各有一条用例挡着——函数被改名、轮询被换名字
（「一处受检的轮询都没有」判**红**，不判绿）、以及**封装说了不算**：`_click_awaiting_write`
这种名字被当成等待用时，检查器会去读它的定义，确认体内真的有 `.click()` 裹在
`expect_response` 里，否则登记一个名字就能绕过整条护栏。豁免表另有两条用例钉「豁免的点击在
源码里真的存在」与「每条豁免都写了理由」。

**红→绿**：护栏先写，对着未改的源码 ⇒ **2 failed**，失败信息逐行点名那 4 处
（`attributable:1283`、`deg_s5:203/:217/:316`），`:264` 正确地没有被点名。改完 ⇒ **14 passed**。
强化过检查器（认封装）之后**重新**对着两份原始源码跑了一遍，仍是 1 + 3 = 4 处判红——红不是
只在弱版本检查器下成立。检查器自身另有 7 条变异用例，每条都要求红**且理由对**。

**绿**：两个 e2e 文件 **38 passed in 45.34s**（`--browser chromium`）；
`scripts/lint_e2e_groups.py` **rc=0**，收集 **140** 条、`baseline_1b` **68/68**（新护栏落在
unit lane，e2e 收集数不变）；unit lane **1656 passed, 2 skipped in 66.88s**（WI-14 后是
1642，+14 正是新增条数）；冻结集 8 条路径 `git diff --stat master...` 为空，`suite_hash`
仍是 `1e868c7bf811`、23 个 blob。

### WI-16 ✅ 预算归队列所有，叫停要先于放行（CI `lint.yml` 红）

**不是审计条目，是 §3 门槛 7 自己逼出来的。** `4d65265` 上 `lint.yml` 红在 router 体量闸：
`FAIL src/reader3_app/web/routers/ai/chat.py 583 行 > 550`。

**上限没动，也动不了**：`scripts/check_router_size.py` 那条具名豁免的 docstring 写着
「只许下调，不许上调」，而 `tests/unit/test_router_size_gate.py` 末尾的
`assert only.max_lines <= 550, "011 §5：N 只许下调，不许上调"` 把这句话钉成了机器约束。
另一头也有界：`min_function_lines=400`，`api_ai_question` 掉到 400 行以下豁免就该删掉。
所以只能找**本来就该删**的东西，不能为压线而搬。

**三种压线的捷径都否掉了，各有理由**：搬走 `_stop_stream_worker`——豁免自己的正文说它不可
搬走，R1 正是为堵这个而把 `routers/` 下每个 `.py` 都纳入测量；用一个 `_ask()` 闭包合并
chat 的两处 `_call_provider`——`tests/unit/test_provider_call_budget_wiring.py` 断言
`len(sites) >= 5`，全仓正好 6 处，合并后**恰好压在地板上**，等于给下一个人埋一个雷；
删 `_stop_stream_worker` 那 19 行理由 docstring——纯粹的散文损失。

**真正该删的那块，同时是一个设计缺陷。** WI-2 让路由自己算 deadline、自己开
`provider_stopped` 旗，两处路由各抄一份：

1. **deadline 抄的是近似值**。路由算 `time.monotonic() + timeout_s`，队列算
   `item.enqueued_at + timeout_s`——**判 504 的是后者**。WI-2 自己的注释承认「只差一次进队
   的毫秒级开销」，但差多少不是重点：同一个事实有两个来源，只有一个作数。
2. **旗翻得太晚**。路由的 `finally: provider_stopped.set()` 跑在 `run()` 返回**之后**，而
   `run()` 的 `finally` 已经先做了 `await q.exit(item)`——**下一个请求已获准开跑，上一个的
   provider 线程还没收到叫停**，两个「本该串行」的调用同时打同一个 provider。顺序即语义，
   这个窗口才是审计 #2 要关的东西；WI-2 关了一半。

**改法**：`ai/queue.py` 新增 `QueueBudget`（`deadline` ＋ `threading.Event`），由 `run()`
构造并传给 `fn`；叫停翻在 `q.exit()` **之前**。用 `threading.Event` 而不是 `asyncio.Event`，
因为读它的 `_call_provider` 跑在 `run_in_threadpool` 的线程里——`set()` 从事件循环线程调用、
`is_set()` 从工作线程读，只有 `threading.Event` 两边都安全。

**顺带把三处「抄，不搬」收成指针**（CLAUDE.md：复述是两份副本走散的方式）：WI-1 的 13 行块
在 **10 个路由**里逐字重复，内容本就定义在 `routers/__init__.py` 的 docstring；WI-2 的 7 行块
在 2 个路由里重复，内容定义在 `_call_provider` 的 docstring；`chat.py` 的模块 docstring 复述
豁免的数字，**而且已经过期**——上限下调到 550 之后它还写着 560，文件里躺着两个互相矛盾的
上限。这正是「复述」的代价，不是假想的。再去掉 `chat.py` 里流式与非流式各抄一份的 system
prompt 与历史过滤（`routing_meta` 那处已经这么分叉过一次）。

**红→绿**：先只加 `QueueBudget` 并**故意**把 `set()` 留在 `q.exit()` 之后 ⇒ `test_B3` 四个
参数化全红（「队列放行下一个请求的那一刻，上一个请求的叫停旗还没翻」），**4 failed, 2 passed**。
把 `set()` 挪到 `q.exit()` 之前 ⇒ **6 passed**。红是断言失败，不是导入错误——第一版拿到的
`ImportError: cannot import name 'QueueBudget'` 不算数，先把类加上才取到真红。

**绿**：`check_router_size.py` **PASS**，`chat.py` **546 行**（master 是 547——本分支交还时
比接手时还小 1 行，且留了 4 行余量）；`ruff` 干净；unit lane **1662 passed, 2 skipped in
64.52s**（WI-15 后是 1656，+6 正是新增条数）；packaging **1 passed, 1 deselected**；
e2e **124 passed, 16 skipped**；`lint_e2e_groups.py` rc=0，收集 140、`baseline_1b` **68/68**；
冻结集 8 条路径 `git diff` 为空。

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

### 3.1 核验结果（2026-09-23，`255b63a`）

| # | 门槛 | 结果 |
|---|---|---|
| 1 | 22 条逐条有交代 | ✅ findings 文件里 22 条全部 `fixed`，`Round` 列带 WI 与 commit；两条 `must-pending-repro` 的复现结论写在 WI-3 / WI-5 段内 |
| 2 | 三条 lane 全绿 | ✅ unit **1662 passed, 2 skipped**（TOTAL 83%）；e2e **124 passed, 16 skipped**（`--browser chromium`）；packaging **1 passed, 1 deselected** |
| 3 | 冻结集零改动 | ✅ 8 条路径 `git diff --stat master...` 输出为空；`suite_hash` = `1e868c7bf811`、**23** 个 blob |
| 4 | 分组守卫 | ✅ `lint_e2e_groups.py` rc=0；收集 **140**、`baseline_1b` **68/68**、白名单 55/55；`EXPECTED_BASELINE_ITEMS` 仍是 **68** |
| 5 | 每个修复先红后绿 | ✅ 16 个工作项各自记了红的**条数与断言**；没有一条的红是导入错误或零用例 |
| 6 | 未设 `TDD_GUARD_BYPASS` | ✅ 分支 diff 里 0 处出现，进程环境里也没有 |
| 7 | CI 全绿后开 PR | 见下方 §3.2 |

**三条 lane 的命令全部带 `env -u FORCE_COLOR`**（欠账 #47）。

**注意 soak 计数**：本分支自始至终没往 `soak-log.md` 添行（011 §8 门槛 4：分支上不落账）。
冻结集一个字节没动，所以计数与三道机制闸的状态**不受本分支影响**。

### 3.2 CI 与 PR（门槛 7）

| 工作流 | Run | commit | 结论 |
|---|---|---|---|
| `lint.yml` | [35827418587](https://github.com/anzchy/reader3-pro/actions/runs/35827418587) | `255b63a` | ✅ success |
| `tests.yml` | [35827429249](https://github.com/anzchy/reader3-pro/actions/runs/35827429249) | `255b63a` | ✅ success |

**前一轮（`4d65265`）`lint.yml` 是红的**，红在 router 体量闸上，`tests.yml` 同一 commit 绿。
修它的过程是 **WI-16**；这里不复述理由。两条工作流在 `255b63a` 上重新派发后同时转绿，
`tests.yml` 里的 `e2e baseline_1b（干净 Linux ＋ 冻结 lock，68/68 首次通过）` 一并通过。

## 4. 硬约束

- **ADR-0008 技术栈边界**：不得引入 JS 测试运行器（package.json / vitest / jest / npm 依赖一律不行）。
  JS 行为的唯一测法仍是 Playwright e2e。
- **冻结集只读**。动一个字节，~~soak 计数清零、三道机制闸全部作废~~（⬛ 2026-09-28 起为批次规则，见[迁移计划 §7](../plan-tech-stack-migration.md#7-阶段门槛表)）（当前计数与冻结值只在
  [`soak-log.md`](./soak-log.md) 里定义，别在别处复述）。
- **soak 不在本分支跑**：011 §8 门槛 4 规定分支上不得追加 soak 行。
- `designs/reader-pro-next/*.jsx` 与 `.mcp.json` 是既有脏文件，别碰、别提交。
- 包管理 `uv run`；所有 lane 加 `env -u FORCE_COLOR`。

## 5. 明确不做的，以及为什么

**`wont`（3 条）**
- **#9、#10** —— 修复要改 `tests/e2e/baseline_1b/**`，~~会把 soak 清零、三道机制闸作废~~（⬛ 2026-09-28 起为批次规则，见[迁移计划 §7](../plan-tech-stack-migration.md#7-阶段门槛表)）。
  **替代覆盖**：#9 想要的渲染文本断言已折进 **WI-5**，写在新的非冻结 e2e 模块里。
  #10（重新着色后空高亮也能过）暂时**没有替代覆盖**——这是一个已知的、写在纸面上的洞，
  不是「已经盖住了」。~~等下一次冻结集重置时一并买。~~（⬛ 2026-09-30：#10 不再「等下一次重置」，改为有主、有验收的欠账，见下条；§1 分桶表的 `wont` 计数保留 017 当时的结论）
- **#10 的兑付（2026-09-30 维护者裁定）**：
  - **兑付方**：冻结集欠账窗口（与 009 欠账 #49 / #50 同一窗口；它排在哪、分支号何时分配，见
    [看板「现在该做什么」](../../20260824-frontend-backend-plan-progress.md#现在该做什么)，此处不复述）。
  - **验收**：`tests/e2e/baseline_1b/` 里有一条用例，**在重新着色留下空高亮时断言失败**——即对「改色后
    该标注的高亮元素存在且渲染文本非空」下断言；按 009 §0 第四条纪律留可失败性证据（定向破坏让
    重新着色产出空高亮，该用例红，且红是断言失败）。改的是冻结集，soak 与机制闸的代价按
    [迁移计划 §7](../plan-tech-stack-migration.md#7-阶段门槛表) 结算。
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
