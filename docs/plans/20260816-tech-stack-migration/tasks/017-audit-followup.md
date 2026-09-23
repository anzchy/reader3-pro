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

### WI-6 🔴 冲突解决同时只许有一个在飞（#5，must）

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
