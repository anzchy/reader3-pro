# 009-e2e-annotations —— 任务

- **状态**: **✅ 两道门全部达成，009 收工。** G1 于 2026-09-05 随 PR #20 合入 `master`（Phase 4A 解锁），**G2 于 2026-09-06 达成**（PR #21 合入后连绿三次，~~`suite_hash` 冻结在 `2747100dadf6`~~，`soak-log.md` 首行落账）（⬛ 2026-09-30：`2747100dadf6` 自 2026-09-21 起作废；现行冻结值只在 [`soak-log.md`](./soak-log.md) 表头定义，此处不复述）。见下面的「合入记录」与 §8。~~**soak 计数从今天起跑，但 Phase 3 还要等跨度**——≥10 次 / ≥5 个工作日~~（⬛ 2026-09-29：已被迁移计划 §7 批次规则取代：一批 = 同一 `commit` / `suite_hash` / 浏览器 / `os` / 依赖锁上恰好 10 次全量首次通过，无日历跨度），进度以 `soak-log.md` 表头为准。
- **对应阶段**: Phase 1b（Playwright E2E）起写，后续阶段逐组激活
- **进入条件**: Phase 0 的 0.3（`--port` + `/api/health`）与 0.5（`data-testid` 全量补齐）完成。见 `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md` §6
- **退出条件**: **两道门，分开记，见 §8**——**G1 用例完成门**（`baseline-1b` 写完并绿、其余组以 skip 形态写完并 review）与 **G2 基线稳定门**（零 flaky ＋ 台账开张 ＋ `suite_hash` 冻结）。**不再要求「主 CI 绿灯」**——CI 已统一为仅发版触发，改基说明见迁移计划 §7 的 soak 小节。其余组各自在所属阶段的出口生效，见 §0.5
- **下游**: Phase 4A 的进入条件是 **G1**；**Phase 3 的 soak 计数从 G2 达成之日起才开始数**（~~次数、跨度~~批次规则（⬛ 2026-09-28）、台账字段、清零规则的唯一定义处是迁移计划 §7 的 soak 小节，本文件不复述）。**本分支还要建 `soak-log.md` 台账**——改基之后 soak 数的是它，没有它就没法计数
- **契约**: K1–K6 见 `docs/plans/20260817-frontend-ui-refactor/contracts/annotation-host-contracts.md`；降级状态 DEG-S1–DEG-S5 见 `docs/plans/20260817-frontend-ui-refactor/spec-frontend-design.md` §6.4

> **引用规则**：用**符号名**与 **testid** 定位，不写代码行号。

### ✅ 合入记录（本文是这条事实的唯一定义处）

**009 已于 2026-09-05 合入 `master`，G1 达成，Phase 4A（013）解锁。** 别处提到「009 是否在主干上」
一律链回这一节，不要重述数字。

| 事实 | 值 | 复核命令 |
|---|---|---|
| PR | [#20](https://github.com/anzchy/reader3-pro/pull/20)，39 commits / 77 files / +23791 −364 | `gh pr view 20` |
| 合并 commit | `b0b4a3a`（`Merge pull request #20 from anzchy/009-e2e-annotations`） | `git show --no-patch --format='%h %p %s' master` |
| 分支领先量 | **0** —— 分支上的东西一件不落全在主干 | `git rev-list --count master..009-e2e-annotations` |
| 合入前门禁 | 本地 tdd-guardian 三条 lane 在 `f227878` 全绿：unit **1043 passed**、e2e **73 passed + 17 skipped**（57.5s）、packaging **1 passed**；覆盖率门禁 PASS（lines 79.94% ≥ 70、branches 67.70% ≥ 52） | `.claude/tdd-guardian/state.json` |
| 三个 lint | `lint_e2e_groups` / `lint_e2e_selectors` / `lint_testid_naming` 全部 rc=0；三分律 66 + 17 + 7 = 90 | `uv run python scripts/lint_e2e_groups.py` |
| `suite_hash` | `e7e0f9626df5`，**合入前后一致**（合并没有改动覆盖面里的任何文件） | 取法见 `soak-log.md` 表头 |

> **PR 页面上没有绿灯，这是设计如此，不是坏了。** 与 008 同规矩：`tests.yml` / `lint.yml`
> 只在发版与 `workflow_dispatch` 时触发，都不设 required check；日常门禁在本地 tdd-guardian，
> 上表「合入前门禁」就是这次合入的实际凭据。
>
> **G1 的三条判据逐条落实**（§8 的原文）：`baseline_1b` 在本地 e2e lane 绿并由
> `soak_run.py`（不带 `--append`）演示出一次可记账的绿（`66 passed, 24 deselected`、
> `verdict: green（可记账：是）`）；选择器 lint 零 class/结构选择器；其余各组以 skip 形态写完
> **并通过 review**——review 那一句的实际议程是 2026-09-05 审计在验收组挑出的三条 High
> （#53 / #54 / #56），已在合入前修毕并各自做了反事实对照，记录在
> `.cc-suite/audits/audit-20260905-010655-findings.md` 的 Wave 4 一节。
>
> **合入不等于 G2——这句话在 2026-09-05 写下时是对的，2026-09-06 兑现。** 当天 `suite_hash`
> 仍是 pre-freeze、`soak-log.md` 零数据行；起跑 G2 的顺序被 §8 与欠账 #22 定死：
> **先修 #22，再冻结起跑**。#22 已于 2026-09-06 在分支 `016` 结清（PR
> [#21](https://github.com/anzchy/reader3-pro/pull/21)，合并 commit `770e5ca`），
> 同批把审计 #51 的证据重做也一并做掉——两次改动各让哈希变一次
> （`e7e0f9626df5` → `8f39737ca0c6` → `2747100dadf6`），都发生在冻结之前，因此都是免费的。
> 合入之后当天连跑三次全绿，首行落账，G2 达成。**这条顺序至此全部兑付。**
>
> 分支 `009-e2e-annotations` 合入后**保留未删**（001–008 同样都还在远端）。

---

> **008 留给本分支的一个必做动作 —— ✅ 2026-08-31 已结清（`36a6ac2`）**：
> `.claude/tdd-guardian/config.json` 里 `e2e` lane 的 `gateOn` 曾是**空的**——008 打开本地
> 门禁时，空的 e2e 目录会让每一次 push 永远 `never passed`，逼所有人常年挂
> `TDD_GUARD_BYPASS`。harness spike 那个 commit 已把它改回 `["push"]`。
> 恢复条件的唯一定义处是那条 lane 自己的 `description`，本文不复述。

> **跨计划**：[前端计划](../../20260817-frontend-ui-refactor/README.md)的测试矩阵**引用本文的用例 ID**（`R-1`…`R-6` / `W-1`…`W-10` / `K-1`…`K-6` / `X-1` / `X-2`）与 §0.5 的激活分组，**不重写这些用例**。前端矩阵新增的是本文范围之外的东西：按钮态、面板互斥与焦点、键盘与 a11y、数据态、响应式、主题解析。两边出现冲突时，标注 E2E 的用例定义以本文为准。

---

### 现状实测（2026-08-26，基于 `master` 的 `3de878c`，本节是这几个数字的唯一定义处）

本文的骨架写在 008 开工之前。008 合入之后，仓库里多了一套测试底座、多了一层请求守卫，
也多了几处骨架没预料到的东西。下表是把骨架的每一条前提拿到今天的代码上重测的结果。

**先看第一行**：它推翻的是 §1 的一条基础设施要求，不是一个数字。

| 事实 | 原稿写的 | 实测（2026-08-26） | 差在哪 |
|---|---|---|---|
| **E2E 运行器** | §1 要求配 `webServer`，并在其中传 `--port` | 这个仓库用 `pytest-playwright` 0.9.0 ＋ `playwright` 1.62.0；`e2e` lane 是 `uv run pytest tests/e2e --browser chromium` | **`webServer` 是 `@playwright/test`（Node）的配置键，在这个栈里根本不存在。** 起服务只能是 pytest fixture（`live_server`）。§1 那一行要按 fixture 重写，不能照抄 |
| 起服务的配方 | 无（当作待建） | **已有可搬的现成实现**：`scripts/smoke_installed_wheel.py` 做的正是「挑空闲端口 → `reader3-server --port` → `READER3_BOOKS_DIR` 指向 tmp → 轮询 `/api/health` 到 200（上限 60s）→ 收尾 drain 子进程输出」。008 建的 | `live_server` 是把它搬进 fixture，不是从零发明 |
| 两套语料（English ＋ CJK） | §1 要求建 | **已有**：`tests/fixtures/epub_corpus.py` 的 `build_epub2` / `build_epub3`（英文）与 `build_cjk`（书名 `咖啡館の夜`，检索词 `咖啡`）。同文件另有 diacritics、缺 TOC、畸形 TOC、spine-toc 迷宫、超大章等十余个 builder | 语料从「要建」降级为「挑一个用」 |
| 0.3 前置（`--port` ＋ `/api/health`） | 「已完成」 | 属实。`/api/health` 路由在 `server.py`；端口优先级 `--port` > `READER3_PORT` > 8123，写在 `main()` 的 docstring 里 | 无 |
| 0.5 前置（testid 全量补齐） | 「已完成」 | 数量属实（2026-08-31 更新）：模板共 138 处（`library.html` 63 / `reader.html` 69 / `settings.html` 6 / **`library_classic.html` 0**）；`scripts/lint_testid_naming.py` 全绿，279 个唯一名 0 违规。原记录为 136 处 / 221 个名，[ADR-0014](../../../adr/0014-bounded-testid-enumeration.md) 落地后 +2 / +58 | `library_classic.html` 一个都没有。它由 `READER3_LIBRARY_UI=classic` 才走到，**E2E 不要碰它**，要碰先补 |
| ~~**testid 唯一性**~~ | §1「只允许 `data-testid` 与 ARIA role/name」 | ✅ **2026-08-31 解除**。原卡点：`library.html` 的 `lib-modal` ×4、`lib-modal-close` ×4、`lib-modal-primary` ×3、`lib-modal-cancel` ×2，`reader.html` 的 `rd-sheet-close` ×2，`getByTestId()` strict 模式必抛 | [ADR-0014](../../../adr/0014-bounded-testid-enumeration.md) 判定弹层/面板是编译期可枚举的有界集合，19 处改成逐个唯一的字面量，判别位 `data-modal` / `data-sheet` 删除；`scripts/lint_testid_naming.py` 新增同文件内唯一性检查（带豁免登记），今后重名会当场 fail。**§1 的选择器政策现已可满足** |
| ~~K1 的七个宿主 id~~ | 契约 | ✅ **2026-08-31 解除**。原卡点：七个中 `anno-color-row`、`note-tooltip` 两个没有 testid | [ADR-0014](../../../adr/0014-bounded-testid-enumeration.md) 补上 `rd-anno-colors` 与 `rd-note-tooltip`（纯增量，`id=` 一个没动——`annotations.js:415,420` 走 `getElementById`）。七个宿主现在全都能用 testid 定位 |
| K4 的六个事件名 | 契约 | 六个全在，全带 `reader3:` 前缀：`annotations:updated` ×5、`escape` ×3、`content:click` ×3、`chapter:change` ×3、`content:rendered` ×2、`ai:ask` ×2 | 无。（裸 grep `escape` 会得到 43，撞的是 `Escape` 键名和 `escapeHtml`；数事件名必须连前缀一起匹配） |
| `applyThemeSettings`（R-6 的前提） | 「今天就存在」 | 属实：定义在 `epub-renderer.js`，`reader.html` 里调用 | 无 |
| **请求守卫**（008 新增，骨架没有） | 无 | `RequestGuardMiddleware`：Host 白名单（默认含 `127.0.0.1` / `localhost` / `[::1]`）→ 令牌 → 非安全方法的 Origin/`Sec-Fetch-Site` 检查。`/api/health` 与 `/static/` 豁免令牌；`READER3_TOKEN` 不设即整条令牌闸关闭，默认不设 | **e2e 起服务时不要设 `READER3_TOKEN`**：前端 fetch 至今不带令牌（`server.py` 头部注释写明），设了等于让页面上每个写操作 401。同源浏览器流量不受 Origin 闸影响，所以写路径用例不需要额外铺垫 |
| `tests/e2e/` | —— | ~~目录在，一个文件都没有~~ → **2026-09-02 复测**：根目录已有 `conftest.py` ＋ **两个**测试模块，`--collect-only` 收 **7 items**（`test_harness_smoke.py` 1 条、`test_testid_dom_uniqueness.py` **6 条**，后者 5 条起浏览器） | **两个模块都没有组 marker**。分组约定必须承认「第三类：显式白名单」，且任何 `-m "not baseline_1b"` 形态的守卫都会真的执行它们——见 §0.5 |
| `e2e` lane 的 `gateOn` | 「现在是空的」 | ~~仍是 `[]`~~ → **已是 `["push"]`**（`36a6ac2`） | 无。头部那条必做动作已结清 |
| `soak-log.md` | G2 的产物 | 不存在 | 无 |
| `BOOKS_DIR` | —— | 仍是模块级常量，import 时读一次 | 每个 worker 要自己的书库副本，就必须配自己的**服务进程**：换环境变量重启，不能运行时改 |

复核命令（数字对不上时先跑这一组，再改上面的表）：

```bash
# 运行器与浏览器
uv run python -c "import importlib.metadata as m; print(m.version('playwright'), m.version('pytest-playwright'))"
uv run pytest tests/e2e --collect-only -q

# testid：总数、重名、命名 lint
for f in src/reader3_app/web/templates/*.html; do
  printf '%-24s %s\n' "$(basename "$f")" "$(grep -c 'data-testid=' "$f")"
done
for f in src/reader3_app/web/templates/*.html; do
  grep -o 'data-testid="[^"]*"' "$f" | sort | uniq -c | awk -v n="$(basename "$f")" '$1>1 {print n, $0}'
done
uv run python scripts/lint_testid_naming.py

# K4 六个事件名（连前缀一起匹配，别裸 grep escape）
grep -rhoE "reader3:[a-z:]+" src/reader3_app/web/static src/reader3_app/web/templates | sort | uniq -c | sort -rn

# 请求守卫与令牌默认值
grep -n "READER3_TOKEN" src/reader3_app/web/server.py
```

#### harness spike 的结论（2026-08-26，本节是这两个数字的唯一定义处）

上表列的是「前提对不对」，这一小节是「跑起来行不行」——spike 只回答这一个问题，
不写用例清单、不建分组、不建台账。产物是 `tests/e2e/conftest.py` 的 `live_server`
fixture 与 `tests/e2e/test_harness_smoke.py` 里的**一条** smoke（进 epub.js 的 iframe
读第一章正文；挑 iframe 而不是「首页 200」，是因为将来所有写路径都要穿过它，进不去
的话整份骨架都得重写）。

| 问题 | 答案 |
|---|---|
| Playwright 在这个仓库能不能稳定起来 | **能**。连跑 5 次 5 绿，0 flaky。chromium 1234（`playwright` 1.62.0 自带的那版）本机已装，不用额外 `playwright install` |
| 一次冷启动多久 | **服务端 0.31s**（5 次全部 0.31s，没有抖动）；**整条 lane 端到端 2.0–3.0s**，含造合成 epub、`process_epub`、起服务、拉浏览器、跑那条 smoke |

两个副作用，都是骨架里点过名的：`e2e` lane 的 `gateOn` 已按头部那条必做动作改回
`["push"]`；`scripts/smoke_installed_wheel.py` 里 60s 的启动超时被原样搬进 fixture——
实测只用 0.31s，但那是本机热缓存，CI 冷机上留足余量比调紧它划算。

> 这些数字属于 2026-08-26 的 `3de878c`，**不是契约**。会变的是数字，不会变的是三条结论：
> ①「起服务」在这个栈里没有配置键，只有 fixture；② 选择器政策卡在 testid 重名上，不是卡在数量上；
> ③ 前端不带令牌，所以 e2e 的服务必须裸跑。数字对不上时按上面的命令重测，别照着旧数字写用例。

---

## 0. 这套 E2E 为什么不能按常规写

标注的六个接触面里 **四个坏了不报错**（K1 缺元素 → `init()` 静默 return；K3 祖先链有包含块制造者 → 浮层可见但位置错；K4 事件名拼错 → 监听方永不触发；K6 上下文读不到 → 回退解析出错误章号）。**「跑完没报错」在这里等于没测。**

由此三条写作纪律，贯穿下面所有用例：

| 纪律 | 反例（不接受） | 正例 |
|---|---|---|
| **往返断言** | 断言 `POST /api/notes/*` 发生过 | 落库 → **刷新页面** → 高亮回到同一段文字上 |
| **几何断言** | `expect(toolbar).toBeVisible()` | 工具条矩形与选区矩形（换算到视口坐标后）相对位置在容差内 |
| **降级正向证据** | 断言「没有出现错误横幅」 | **主动制造** stale，断言横幅出现且文案匹配 |

> 上游技术栈计划原写「断言 `POST /api/notes/*` → 刷新 → 断言 iframe 内重现 `<mark>`」。**后半句才是门槛**；前半句留作失败时的诊断信息，不单独构成通过条件。

### 第四条纪律：特征化用例的可失败性证据（2026-09-02 立）

**009 的每一条用例都是特征化用例**——被测行为早已上线数月，所以**红根本不可得**。
`tdd-guardian` 的红收据在这里必然记成 `green` 并判 `SEPARATION-BROKEN`，成因是
「实现早于规格」而非「实现改了规格」。**这是预期状态，不是缺陷。**

由此定下：

- **不得靠破坏生产代码去伪造一次红。** 伪造的收据比没有收据更坏——它把「这条断言证明过
  自己会红」这个结论，安在了一次人为制造的失败上。
- 替代证据是**定向破坏**，每条用例至少一次，且必须留档三样：**破坏点**（改了哪个函数的哪一行）、
  **失败输出**（实际断言消息，不是「红了」三个字）、**还原核验**（`git diff --quiet <生产文件>`）。
- 破坏必须逐条打靶，不能一次空转全部函数了事——那只证明「不是空断言」，
  证明不了每条判据各自咬住了什么。

WI-4 的实录（四次，全部已还原）：

| 破坏点 | 结果 | 它证明了哪条判据不是摆设 |
|---|---|---|
| `createAnnotation` 首行 `return` | 3 红 | 往返链整体 |
| `handleAction` 的 `toggleAnnotation("wavy")` 改成 `("underline")` | wavy 红、underline 绿 | `type` 判据真在区分两个等价类，不是恒真 |
| 渲染时 `text.slice(r.start, r.end - 1)` | 3 红 | DOM 侧的逐字往返 |
| `createAnnotation` 里重复一次 POST（相隔 7ms） | **先 2 红 1 绿**，补断言后 3 红 | 「恰好 1 条」——见下 |

⚠️ 第四次破坏抓出了一个真漏洞，记在这里因为它会复现：**「轮询到期望值就返回」的等待函数，
天然会把中间态当成终态。** 原写法 `_wait_for_notes(..., 1)` 一观察到 `len == 1` 就返回，
两次写相隔 7ms、轮询间隔 50ms，于是有一定概率正好卡在窗口里；DOM 侧也兜不住，因为两条
**完全重合**的标注在 `render()` 分段时合并成一个 `<mark>`，strict 模式看不出重复。
结果是「一次点击写两条」这条缺陷**概率性漏检**——而不确定性正是 G2 要清零的东西。
修法是在往返收尾处**再断一次终态**（刷新已完成，第二次写必然已落盘）。
凡用「轮询到期望值」等异步落库的用例，都要照此补终态断言。

### 第五条纪律：守恒断言的基准必须是字面量（2026-09-03 立）

**不变式断言的「动作前」那一侧，必须是写死在用例里的字面量，不能是运行期读回来的值。**

反例：`seed_notes` 让 `id` 取随机 uuid、`created_at` 取 `now()`，用例再读回来存进
`before`，最后断 `after["id"] == before["id"]`。这句**永远绿**——它拿运行期读到的值比
运行期读到的值，两边同源。哪怕实现把整条记录换成别的东西，只要换得一致，它照样绿。

正例（WI-5 的 W-7）：`W7_TARGET_ID = "wi5-w7-target-note"`、
`created_at = "2026-01-01T00:00:00+00:00"` 都写死。「id 变成了别的」于是在失败消息里是一个
人能一眼认出的字面量，而不是两串都不认识的 uuid。

这条与前四条同属一类，**违反它不会红，会静默全绿**——这正是它必须进纪律、不能留在某个
文件的注释里的原因：留在注释里就只有读那个文件的人知道。

### 第六条纪律：静默失效的规则必须机器可查（2026-09-03 立）

**一条「漏写了也不会红」的规则，写在散文里等于没写。** 波次之间不传递记忆——写用例的是
不同的 agent，它看不见上一波的对话，也不保证读过本文。所以每条这类规则都要落成一种不靠
记忆的机制，强度从高到低：

1. 签名强制（让它不可能忘）
2. 忘了立刻响，且消息指对地方
3. **机器可查**（lint 或契约测试）
4. 写进派活简报
5. 写进本文的散文 ← **最弱，最容易漂**

已经落到 3 级的两条：

| 规则 | 机制 | 查它的东西 |
|---|---|---|
| 多标注用例必须断旁观条守恒 | 共用函数 `helpers.assert_bystanders_unchanged` ＋ 契约测试 | `tests/unit/test_e2e_bystander_discipline.py`：凡传 `expected_count > 1` 的模块必须调用它至少一次；逃生口是行尾 `# bystanders: n/a —— <理由>` |
| 选择器只许 `data-testid` 与 ARIA | lint 脚本 | `scripts/lint_e2e_selectors.py` |

⚠️ **共用函数是「机器可查」的前提，不是顺手的重构。** 各用例就地写一行
`assert after_bystander == before_bystander` 在语义上完全等价，但**它是 grep 不到的**——
没有一个共用的名字，第 3 级机制就写不出来，规则只能退回第 5 级。

---

## 0.5 用例分组与激活阶段

> **为什么需要分组**：本文最初把全部用例塞进 Phase 1b 的退出门槛，这构成一个**依赖环**——
>
> - K-1 的「响亮失败」与 K-6 的「`Reader3Ctx` 缺失时抛错」是 **4B.1 才产生的行为**（见[前端计划](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md)的 4B.1 契约产出表 K1/K6 行，K6 明写「本次拆分中唯一**故意的行为变更**」）；
> - DEG-S1–DEG-S4 的横幅要到 **Phase 3 / 4A.4** 才存在（本文 §5 注已承认这点）；
> - 而 Phase 3 的进入条件含 1b 的 soak 门槛，Phase 4A 的进入条件是 1b 绿灯，Phase 4B 的进入条件是 Phase 3 + 4A.4。
>
> 于是「1b 全绿」要求先有 4B.1 和 Phase 3 的产物，而它们又都排在 1b 之后。**按原文的顺序跑不通。**
>
> 修法不是删用例，而是把「**写下来**」与「**计入门槛**」分开：用例照写，但每组只在其被测行为存在的那个阶段才激活并计入退出条件。

| 组 | 内容 | 激活阶段 | 计入 1b 退出门槛 | 计入 Phase 3 soak |
|---|---|---|:--:|:--:|
| **`baseline-1b`** | §2 读路径 R-1…R-5 ＋ **R-6a**、§3 写路径 W-1…W-4 ＋ **W-5a** ＋ W-6…W-10、§4 的 K-1a / K-2 / K-3 / K-6a（K-4 / K-5 是 R-4 / R-5＋W-1 的别名，不另计）、§6 X-1 / X-2 | Phase 1b | ✅ | ✅ |
| **`acceptance-4b1`** | §4 的 K-1（响亮失败）与 K-6 的抛错断言，＋ §3 的 **W-5b**（改色保 id），＋ §2 的 **R-6b**（CFI 侧，2026-09-03 从 R-6 拆入）。**共 8 条**（原 5 条），见下方「条数」小节 | 4B.1 | ❌ | ❌ |
| **`acceptance-p3`** | §5 的 DEG-S1–DEG-S4，**朴素横幅形态** | Phase 3 出口 | ❌ | ❌ |
| **`acceptance-4a4`** | §5 的 DEG-S1–DEG-S4，**设计规格形态**（只改 testid 映射，断言语义不变） | 4A.4 | ❌ | ❌ |
| **`acceptance-2a`** | DEG-S5 写冲突（本文 §7 已列为不在 1b） | Phase 2a | ❌ | ❌ |

**落地方式**：用 pytest marker（`@pytest.mark.baseline_1b` 等），CI 按组选择。未激活的组以 `skip` 而非删除的形式存在，理由是它们必须在写的时候就被 review——**一条到期才第一次被人读的断言，等于没写。**

**第三类：显式白名单（2026-09-02 补）。** 上表隐含过一个前提——「`tests/e2e/` 根目录下除 `conftest.py` 外只有 `test_harness_smoke.py`」。这个前提**在 009 开工前就不成立**了：`tests/e2e/test_testid_dom_uniqueness.py`（ADR-0014 的运行期唯一性护栏）同样住在根目录，同样没有组 marker。所以分组不是二分而是**三分**，每个 collected item 恰好落进其一：

1. 携带五个组 marker 之一（marker 与所在目录一一对应）；
2. 其模块名在 `UNGROUPED_E2E_MODULES` 白名单里；
3. 以上皆非 ⇒ **违规**。

白名单是唯一的豁免口径，且**每一项都必须在某次收集里真的贡献 item**——悬空条目等于给下一个模块预开的门。这条划分律由 `scripts/lint_e2e_groups.py` 执行，不靠人眼。

**五个组目录里放什么（2026-09-02 实测订正）。** 生成计划的 WI-1 验收原文是「每个目录有 `__init__.py` **或**明确的 `conftest.py` 归属」。两条路**都不通**，落地用的是第三条 `.gitkeep`：

- `__init__.py` —— 会把 pytest prepend 模式的 `sys.path` 插入点从 `tests/e2e/` 上移到 `tests/`，`test_harness_smoke.py` 与 `test_testid_dom_uniqueness.py` 的 `from conftest import BOOK_ID`（裸模块名）当场 ImportError。这一条矩阵已记为用例。
- `conftest.py` —— **实测同样炸**：子目录 conftest 以同一个顶层模块名 `conftest` 被导入，会在 `sys.modules` 里顶掉 `tests/e2e/conftest.py`，报 `ImportError: cannot import name 'BOOK_ID' from 'conftest' (tests/e2e/baseline_1b/conftest.py)`。

所以这两个选项不是「不等价」而是「都不可用」。后果要记在这里：**哪个组将来真需要自己的 fixture，得先把那两处裸 import 改成显式包路径**，否则动一下就红。测得的细节写在 `scripts/lint_e2e_groups.py` 的「目录布局」一节。

**条数（口径，不写死数字）。** `EXPECTED_E2E_ITEMS = EXPECTED_BASELINE_ITEMS + EXPECTED_ACCEPTANCE_ITEMS + 白名单模块在本次收集里的 item 数`。今天的实测值是 `61 + 14 + 7 = 82`。三个分量里：

- `EXPECTED_ACCEPTANCE_ITEMS` = **14**（原记 11）。差额来自 `acceptance-4b1` 由 2 变 5：W-5 拆 a/b 的裁决（2026-09-01）把 W-5b 放进该组 ⇒ 3；而 `toggleMarkerAnnotation` 与 `toggleAnnotation` 是**两份独立实现**，W-5b 必须在 `{marker, wavy, underline}` 上参数化 ⇒ **5**。
- **这三个数字只允许在 `scripts/lint_e2e_groups.py` 定义/派生一次**，验收条、守卫脚本、台账产物一律 import。写死字面量的代价已经付过一次：把 `test_testid_dom_uniqueness.py` 漏算成 76，会让 WI-1 的条数断言**在写第一行 009 代码之前就红**。

**4B.1 的连带成本（本来就存在，只是没被记过）**：那个 commit 要处理的不是「解开 1 条 skip + 改判 W-5a-②」，而是「解开 **3** 条 skip + 改判 W-5a-② 与 W-5a-③ 的两个参数」。反过来，**W-5a-⓪（同色重按 = 差集删除）在 4B.1 之后应当保持绿**——若顺手把候选集从「选区命中」放宽成「整章同 type 同 color」，它会红，**那是正确的红**，修法是改回实现。

### `baseline-1b` 对 K1 / K6 / W-5 的现状特征化

这三处在 1b 阶段仍要有护栏，只是断言的是**今天的行为**，不是 4B.1 之后的行为：

| 项 | `baseline-1b` 断言（现状特征化） | `acceptance-4b1` 断言（行为变更后） |
|---|---|---|
| **K1** | 七个宿主元素在模板中齐备，标注 UI 正常 init（**前置条件成立**的正向证据） | 移除 `annotation-toolbar` 后重载 → 明确 `console.error` 且降级标记置位 |
| **K6** | 在 `/read/{bookId}/{chapterIndex}` 创建标注，`notes.json` 的 `chapter_index` 等于 URL 里那个数 | 删掉 `location.pathname` 回退后，`window.Reader3Ctx` 缺失时**抛错**而非静默猜测 |
| **W-5** | 见 §3 的 W-5a——色板点击只换「下一次用的颜色」，重按 marker 得到**两条并存**的标注，重按 wavy / underline 则**标注没了**（订正见 §3 W-5a 下方） | 见 §3 的 W-5b——「改色」成为一个真操作：颜色变、`id` 不变 |

K1 的 baseline 条是有价值的：它会在**任何人改模板删掉那七个 id 之一时**变红，而这正是 4B.2 外壳重写最可能干的事——不必等到 4B.1 才有护栏。

**W-5 为什么也落在这里（2026-09-01 裁定）**：本文原先把 W-5 写成「刷新后颜色为 green，且**标注 id 不变**」——那不是今天的行为，是期望的行为。按这个写法，1b 的门槛里会混进一条只有等 4B.1 改完生产代码才可能绿的用例，和 R13 修掉的那个依赖环是同一个形状。裁定采用与 K1 / K6 相同的处理：**W-5a 特征化今天的三岔行为并计入 1b 门槛，W-5b 承载期望行为并挂 `acceptance-4b1`**；期望行为本身的落地在[前端计划](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md)的 WI-14 定义，本文不复述。

---

## 0.6 剩余 WI 的波次编排（2026-09-02 立）

> 本节只管**执行编排**——哪些 WI 可以同时开工、哪些必须独占。它不改任何一条用例的内容，
> 也不改 §0.5 的分组与激活。WI 的定义在 `.claude/tdd-guardian/tests-20260901-224500.md`
> （矩阵，最高权威）与 `.claude/tdd-guardian/plan-20260901-122813.md`（生成计划，最低权威，
> 已知在 WI-6 一处过期）；本节只引用编号，不复述内容。
>
> **进度（2026-09-03）**：Wave 0 / 1 / 2 / 3 已完成，**WI-1…WI-9、WI-11、WI-12 已落地**。
> 写路径 W-1…W-10 全部就位；契约 K-1a / K-2 / K-6a 与读路径 R-1…R-3 本波补齐。
> `baseline_1b` **46 / 61 条**（`tests/e2e` 全量 53 条，24.51s 全绿）。**下一波是 Wave 4**
> （WI-13、WI-14、WI-15）。

### 为什么并行是可行的

一个前提在 WI-1 就已经铺好，值得写下来，否则下一个人会以为它是巧合：

**`EXPECTED_BASELINE_ITEMS = 61` 是目标值，不是运行计数。**「实际收集到的条数 == 61」这条断言被
推迟到 WI-17。如果每个 WI 都要把常量往上加一次，`scripts/lint_e2e_groups.py` 就成了 13 条 WI 的
串行写入点，并行当场作废。**这个推迟是并行的前提，不要在中途"顺手"把它提前。**

反过来，仍然存在三处真正的串行写入点，波次编排就是围绕它们排的：

| 共享写入点 | 谁会碰 | 处理 |
|---|---|---|
| `tests/e2e/helpers.py` | 每一条写路径 WI | **Wave 0 一次性上收**，之后每波至多授权一个 WI 改它 |
| `tests/e2e/conftest.py` | WI-16（桩 provider 的 server env） | WI-16 独占一波 |
| `.claude/tdd-guardian/state.json` / `receipts.json` | 每一次 `record` / `verify` / 跑 lane | **写用例并行，跑门禁串行**——见下方纪律 3 |

### 波次表

| 波 | WI | 并行度 | 为什么这么排 |
|---|---|:--:|---|
| ~~**Wave 0**~~ ✅ | helper 上收（无 WI 编号） | 1 | 见下 |
| ~~**Wave 1**~~ ✅ | WI-5 | 1（探针） | 见下 |
| ~~**Wave 2**~~ ✅ | WI-6、WI-7、WI-8 | 3 | 写路径收尾。三条各建自己的模块，互不相干；WI-8 要的 CJK 语料（`build_cjk` / `cjk_data`）在 WI-3 已经进 conftest，所以它不碰共享文件 |
| ~~**Wave 3**~~ ✅ | WI-9、WI-11、WI-12 | 3 | 契约（K-2/K-6a、K-1a）＋ 读路径基础（R-1…R-3）。都只读标注，不改写路径 |
| ~~**Wave 4**~~ ✅ | WI-13、WI-14、WI-15 | 3 | R-4/R-5、R-6、X-2。同上。2026-09-04 `f518be3` 收口 |
| ~~**Wave 5**~~ ✅ | WI-10 | 1（独占） | 见下。2026-09-04 收口：K-3a×3 / K-3b / K-3b′ / K-3c 六条，`baseline_1b` 收到 61 条（与常量 61 相等是巧合——常量是矩阵预估且已含 X-1，见 soak-log）；欠账 #25 的 helper 上收同批兑付 |
| ~~**Wave 6**~~ ✅ | WI-16 | 1（独占） | 2026-09-04 收口：X-1a / X-1a′ / X-1b / X-1c 四条 ＋ 桩契约 unit 用例 3 条，`baseline_1b` **65 条**，22 个用例编号全部落地。 唯一要改 `tests/e2e/conftest.py` 的一条（桩 provider 的 server env）。conftest 是 session 级 fixture 的定义处，改它会影响同时在跑的每一条用例 |
| ~~**Wave 7**~~ ✅ | WI-17 | 1（独占） | 2026-09-04 收口，**八波编排到此结束**：验收组 skip 用例 **17 条**（4b1 8 / p3 4 / 4a4 4 / 2a 1）＋ `lint_e2e_groups.py` 分组存量守卫 ＋ `soak_run.py` ＋ 共用 DEG 断言体。常量由预估改实测：`EXPECTED_BASELINE_ITEMS` 61 → **65**、`EXPECTED_ACCEPTANCE_ITEMS` 派生 **17**、`EXPECTED_UNGROUPED_ITEMS` **7**，派生总数 **89** ＝ 实测收集数（欠账 #2 / #14 结清）。**本波第一次录到真红**（37/99 失败，`assertion-failure`），verify 判 **SEPARATION-HELD**——前六波是特征化用例，红在结构上不可得，这是全支唯一一次断言先于实现的直接证据 |

**Wave 0 为什么必须先于一切**：`_open_reader` 与 `_wait_for_notes` **今天已经在两个模块里各有一份**
（`baseline_1b/test_harness_helpers.py` 与 `baseline_1b/test_write_create_annotations.py` 各自都定义了这两个私有函数）。两份的时候还只是
重复；三个 agent 同时开工就会变成三份各自漂移的版本，而合并时**只会留下一份，另外两条用例静默改变
了它们等待的对象**。所以 Wave 0 把这四个私有 helper（另两个是 `_assert_roundtrip`、
`_clear_selection_and_drain`）上收进 `tests/e2e/helpers.py`，串行落地，再开扇出。

**Wave 1 为什么只放 WI-5**：它是第一条走**编辑态**（`editingNoteId`）的用例，而 WI-4 已实测出那条
路上有一个自持的选区循环——`handleRenditionSelection` 自己做 `removeAllRanges(); addRange(range)`，
重新触发 `selectionchange`，在 `select_in_frame` 返回后约 250ms 把 `editingNoteId` 清空。创建路径
免疫（点击落在 ~30ms），**编辑态不免疫**。如果 WI-5 需要为此新增一个共享的 drain/settle helper，
那么后面每一条碰编辑态的用例都需要它。让 WI-5 单独跑一波，就是让这个"需不需要"在扇出之前有答案。

**Wave 5 为什么独占**：WI-10 是几何断言（浮层坐标系）。CPU 争用会让坐标测量产生**假红**，而这一条
的交付物恰恰是「零 flaky」。**用一条会被并发污染的用例去证明零 flaky，是自相矛盾的。**

### 执行纪律

1. **并行上限 3。** 本机 10 核；一个 Playwright chromium 实例连带服务进程约占 2 核，再多会让本来
   就贴着超时阈值的等待逻辑（`SELECTION_TIMEOUT_MS = 8000`、`NOTES_WAIT_S = 8.0`）开始假红。
2. **共享文件授权制。** `tests/e2e/helpers.py`、`tests/e2e/conftest.py`、`scripts/lint_e2e_groups.py`
   在一波之内**至多一个 WI 被授权改**，其余 WI 只读。派活时要在 prompt 里写明这条，不能指望 agent
   自己推断。
3. **写用例并行，跑门禁串行。** `.claude/tdd-guardian/state.json` 与 `receipts.json` 是全局可变
   状态，多个 agent 同时 `record` / `verify` 会互相覆盖，且覆盖是静默的。红收据要一条一条录；每波
   结束后由主 agent **串行跑一次** `e2e` lane，而不是每个 agent 各跑各的。
4. **每波收口三件事**：(a) 更新 `soak-log.md` 的 `suite_hash` 变更史（新模块进索引就会变，pre-freeze
   期间这不清零任何计数，因为还没开始数）；(b) 跑一次选择器 lint 与分组 lint；(c) 人工核对本波内
   跨 WI 的交叉引用（见下）。
5. **WI-5 与 WI-6 的旁观者是同一个构造。** 矩阵已定：两者的 bystander 都是 `quote="One"`，**两份
   docstring 必须互相点名**。它们分处 Wave 1 与 Wave 2，所以 WI-6 能看见 WI-5 的文件，而 WI-5 看不见
   WI-6 的——WI-5 那一侧的交叉引用只能按矩阵里的路径写，并在 Wave 2 收口时核对回来。

### 跨波欠账

**一笔欠账 = 前一波留下、必须由后一波兑付的东西。** 单开一张表，是因为这类东西的失效方式
是「没人记得」而不是「测出来是错的」——散落在各波的说明文字里没人会回头读（§0 第六条纪律）。

派活时由主 agent 把「兑付方」是本波的行**逐条抄进简报**；每波收口时核对「验收怎么查」那一列。
兑付完的行不删，把状态改成已结清并写上结清的 commit——删掉的话，下一个人会重新问一遍为什么。

| # | 欠什么 | 欠账方 | 兑付方 | 验收怎么查 | 状态 |
|---|---|---|---|---|---|
| 1 | W-5a-⓪ 的 docstring 要写一条指回 W-7 的反向指针（W-7 那一侧已写好，按用例号 ＋ WI 号引用，没猜文件名） | WI-5 | **WI-6（Wave 2）** | `grep -l "test_w7_editing_a_note" tests/e2e/baseline_1b/` 能命中 WI-6 的模块 | **已结清**（WI-6 的 `test_write_recolor_and_delete.py` 命中） |
| 2 | `EXPECTED_BASELINE_ITEMS = 61` 的「实测 == 61」断言（全程刻意不逐 WI 递增，否则 `lint_e2e_groups.py` 会变成 13 路串行写点） | §0.6 的并行前提 | **WI-17（Wave 7）** | 断言存在且实测条数等于常量 | **已结清（2026-09-04）**：常量改成实测的 **65**，断言在 `scripts/lint_e2e_groups.py` 的条数轴上，实测不等即 rc=1 并把两个数都印进消息。定向破坏 1 号（移走一个 3 条的验收模块）证明它会红 |
| 3 | `soak-log.md` 的 `suite_hash` 变更史每波追加一行，写清作废原因 | 每一波 | **下一波收口时** | 变更史首行的哈希 == 当前实测值 | 滚动 |
| 4 | W-7 改用 `assert_bystanders_unchanged` 之后**没跑过 e2e** | 2026-09-03 | 同日结清 | `uv run pytest tests/e2e --browser chromium` == 21 passed | **已结清**（21 passed / 14.07s） |
| 5 | 生产模板仍硬依赖 Google Fonts CDN：`reader.html` 与 `library.html` 的 `<head>` 各有一组指向 `fonts.googleapis.com` / `fonts.gstatic.com` 的阻塞式 `<link>`。对一个**本地自托管的离线阅读器**来说，断网或够不到该域时首屏字体直接降级。e2e 已由 `context` 网关掐掉，**生产未修**——已知代价、显式推迟，不是遗漏 | 2026-09-03 | ~~**待定**（需先决定自托管字体 vs 接受降级）~~ ⬛ 2026-10-02 维护者裁定：→ **014 WI-18**——产品方向已由其验收 c「全仓库无远程字体」定为自托管，本条按默认确认。`library.html` 的 CDN 已随 `4ec22db`（013 WI-13）删去；余 `reader.html:11-13` 与 `static/js/epub-renderer.js:197`（向 iframe 注入字体 link） | `tests/unit/test_frontend_external_hosts.py` 的 `EXPECTED_EXTERNAL_HOSTS` 变成空集且仍绿（该用例两个方向都红：新增未登记的域红，白名单留下已无人使用的域也红——所以兑付时删模板必须同步删登记） | 未结清 |
| 6 | **`cfi` 永远是 `null`，全部锚定实际走纯文本路径。** `epub-renderer.js` 在 `rendition.on("rendered", (section, contents) => …)` 里把第二个实参当 `Contents` 存进 `currentContents`，但 epub.js 传的是 **view**。`IframeView` 有 `.document`，所以样式注入、点击、翻页全都照常工作，缺陷被完全掩盖——唯独没有 `cfiFromRange`，于是 `annotations.js` 里 `typeof contents.cfiFromRange === "function"` 这个卫语句**永假**，`cfi` 恒为 `null`。**这是生产缺陷，不是测试问题**，需单开工作项 | WI-7（2026-09-03 发现） | ~~**待定**（前端计划，需自己的工作项）~~ ⬛ 2026-10-02 维护者裁定：→ **014 WI-15**（K5 把 `getContents()` 改成显式接口，与 WI-14 拆分同做；WI-18 验收 8「C：CFI 往返」隐含依赖它）。绊线 `baseline_1b/test_write_overlap_and_disambiguation.py:616` 翻转属冻结集改动，与 #15 / #24 / #69 同一次 `suite_hash` 变更 | 经 UI 创建的标注 `cfi != None`；WI-7 模块里那条 `cfi is None` 的绊线用例转为断反面 | 未结清 |
| 7 | 矩阵 §WI-7 的 Gap 7「经 UI 创建的标注一律带 CFI」**已被证伪**（见第 6 行）。三处提法需订正：矩阵该条、以及任何以「有 CFI 兜底」为前提的锚定论述 | WI-7 | **兑付第 6 行的同一个工作项**（⬛ 2026-10-02 维护者裁定：即 **014 WI-15**） | 全仓 grep 不到「一律带 CFI」这类未加限定的提法 | 未结清 |
| 8 | `AnnotationRenderer.render()` 的 CFI 分支**零覆盖**——因第 6 行它今天是死代码。补它需要第 5 条用例，会让 `EXPECTED_BASELINE_ITEMS = 61` 变动，因此不能在 Wave 2 里就地补 | WI-7 | ~~WI-17（Wave 7）~~ → ~~**改派 011 / 014，与欠账 #6 同一次兑付**~~ ⬛ 2026-10-02 维护者裁定：已由 017 WI-5 ＋ 023 兑付，见状态列 | 该分支有用例覆盖，且常量与实测条数同步更新 | ~~**未结清（2026-09-04 改派）**~~ ⬛ **已结清（2026-10-02 维护者裁定，核实于 `94dd1e0`）**：`baseline_1b/test_stored_cfi_must_agree_with_quote.py:223` `test_cfi与quote对得上时仍然优先按cfi重锚` 直接种入 `cfi`，删掉 CFI 分支即红——由 `e591aa6`（017 WI-5）新增、`9d504bd`（023 #65）移入 `baseline_1b`；`EXPECTED_BASELINE_ITEMS = 132` 与实测同步（`scripts/lint_e2e_groups.py:240`）。验收两条都满足；R-6b 余下 3 条 skip 归 #6。以下为原状态文字：WI-17 付不了它。前置条件写明「必须排在第 6 行修完之后」，而欠账 #6（`cfi` 恒为 null）是生产缺陷，009 全程 `src/` 一行未动（§0.5：1b 是安全网，不是行为变更窗口）。**在 cfi 真的写得进去之前，为死代码补的用例只会锁死死代码的形状。** R-6b 的 3 条 skip 用例已在 `acceptance_4b1` 就位，等的就是这次兑付 |
| 9 | **改色 wavy / underline 会静默丢数据**（删成功、建失败、剩 0 条），根因与复现见 §3 W-5a 下方的订正段。W-5a-③ 今天把这个行为特征化下来了，**但没修** | WI-6（2026-09-03 发现） | **4B.1 / 前端 WI-14**，且应排在 W-5b 解 skip 之前 | 改色后选区上仍有且只有 1 条标注；W-5a-③ 转红即为正确的红，改法是删掉该用例而非改断言 | **已结清（2026-09-21）**，但**兑付方不是原定的 4B.1，是 011 自己**——提前了一个里程碑，理由见下条。**根因（实测，不是推断）**：`render()` 走 `clearExistingAnnotationMarks()` ＋ `normalize()`，把相邻文本节点并回一个，活 Range 的两个端点于是**落到同一个偏移上**。节点本身还在索引里，所以 #44 那道「端点还锚不锚在文本节点上」的闸（`rangeAnchoredIn`）**看不见这件事**——它问的是「还在不在」，不是「还有没有宽度」。塌成一点 ⇒ `quote` 为空串 ⇒ `createAnnotation` 的空 quote 闸拒发 ⇒ 删掉的那条没有替代品。**#44 的上浮回落修不掉它，两种机制是两回事**（上浮 = `replaceChild` 摘掉含端点的节点，端点按 DOM 规范浮到父元素，`offsetFromNode` 走元素分支静默返回**错**偏移而不是 `null`）。一次中间态的误判：我曾报过「修 #44 顺带修好了 #9」，**是错的**——`_is_notes_post()` 不看状态码，当时的 `TimeoutError` 意思是「那次 POST 压根没发出去」，不是「状态码变了」。用一条复刻 W-5a-③ 的探针实测推翻：`DELETE 204`、**无 POST**、console `createAnnotation: 算出空 quote，拒发 {s: 14, e: 14}`、盘上 0 条。**修法**：`annotations.js` 的 `resolveOffsets` 增加一条**塌陷回落**——算出的 `start === end` 且偏移快照仍是一段真区间时，回落到快照，并 `console.warn`。**修后实测**：`DELETE 204 → POST 201`，盘上 1 条，`quote='Alpha prose'`、`position=3`、`color=green`、**id 变新**，console 有 `活选区已塌成一个点，回落到偏移快照 {start: 3, end: 14}`。**代价（明账，不含混）**：W-5a-③ 的期望值从挂了 18 天的偏差值 `0` 改回矩阵原文的 `1`，测试改名为 `test_w5a3_recolor_then_repress_replaces_with_a_new_id`——这**动了冻结集**，`suite_hash` `2747100dadf6` → `1e868c7bf811`，**soak 计数 10 → 0，机制挑战闸三项（含已 PASS 的 CPU 压力项）一并作废**。维护者明确选了「全修，接受清零」而不是撤掉修复保住计数。**遗留的一半**：这只做到「删了再建一条新的（id 变）」，**没做到原地改色保 id**——那要 `PUT` 收 `color`（见欠账 #29），仍归 4B.1 / WI-14，`acceptance_4b1` 的 W-5b 因此**正确地保持 skip**，到期门槛＝WI-14 交付日 |
| 10 | `live_server` 的 `stdout=subprocess.PIPE` 从不在运行期 drain。管道满 64 KiB 后 uvicorn 卡死在 `write()`，此后每条 `page.goto` 都 30 秒超时。**建账起就潜伏，Wave 2 把套件涨到 35 条才引爆**（实测一轮写 74194 字节） | WI-1（建账时引入） | 2026-09-03 同日结清 | `uv run pytest tests/e2e --browser chromium` 全绿 | **已结清**（改为日志落文件；35 passed / 19.01s，修前 6 failed / 187.12s）。**但这条判据不是回归闸，且当时只修了发作的那一处——见 #32** |
| 11 | **`rd-page-prev` / `rd-page-next` 是死表面**：`reader.html` 的基础样式里就是 `.nav-zone-left, .nav-zone-right { display: none; }`（注释写着 keyboard-only navigation），且全仓 live 的 `js/*.js` 无任何绑定——唯一绑定在 `reader.html` **不加载**的 legacy `js/pagination.js` 里。有 testid 却点不动，点它只会等到 actionability 超时。**这不是测试问题**：一个带 testid、带 `title`、占 120px 宽度变量的元素永久不可达，要么补上绑定，要么连同 testid 一起删 | WI-9 / WI-12（2026-09-03 各自独立撞上） | ~~**待定**（前端计划；`rd-page-*` 的去留是产品决定，不是测试决定）~~ ⬛ 2026-10-02 维护者裁定：→ **014 WI-17**（拥有 `rd-page-next/prev` 并让翻页可用）。产品决定按默认确认为 WI-16 验收 9 已写的「零 `nav-zone-*` 字符串、`rd-page-*` 保留并带 `aria-label`」 | 要么它可点且翻页，要么模板里不再有这两个 testid（届时 `lint_testid_naming.py` 的计数会变） | 未结清 |
| 12 | **站内导航时 URL 落后于渲染**：`syncLocationToUrl()` 跑在 epub.js 的 `rendered` 回调里，所以点完 `rd-chapter-next` 或 TOC 行的那一刻，地址栏仍是旧章号。**任何先断 URL 的用例都在读陈旧状态**。WI-12 的定向破坏 D4′ 实测：把 URL 期望改成隔壁章号，两个站内分支照样绿；调换成「先断正文、再断 URL」后同一发子弹三条全红 | WI-12（2026-09-03 发现） | **无需修**——这是契约不是缺陷，欠的是**把它写进 helpers 的等待原语**，见第 13 行 | 全仓不存在「点击后立即同步读 `page.url`」的写法 | 记录在案 |
| 13 | **三个本波产出的 helper 该上收到 `helpers.py`**：`_pathname_is`（等解析后的 pathname 而非 URL glob——TOC 行是 `<a href="#">`，导航后 URL 带尾随 `#`，`wait_for_url` 的 glob 永不匹配、白烧 30s，WI-9 为此花了一轮 spike）；`_reader_frame`（`open_reader` 去掉 `goto` 的那一半，凡「点进来」或站内导航的用例都要，重新 `goto` 会把被测的导航冲掉）；`_scan_annotations` / `_mark_id_union`（与 `test_write_overlap_and_disambiguation.py` 的 `_scan_marks` **已经重复**，两处都刻意在 evaluate 里读 `dataset.annotationIds` 以绕开选择器 lint 的误报——这个取舍该编码一次，不该每模块重新发现一遍） | Wave 3 | **下一个被授权改 `helpers.py` 的 WI**（§0.6 纪律 2：一波至多一个） | `grep -c "def _scan_marks\|def _scan_annotations" tests/e2e/baseline_1b/*.py` == 0 | **已结清**（Wave 3.5：`reader_frame` / `pathname_is` / `scan_marks` / `mark_id_union` 已上收，验收 grep 为 0） |
| 14 | **R-6 拆 a/b 之后 `acceptance-4b1` 由 5 条变 8 条**，`EXPECTED_ACCEPTANCE_ITEMS` 因此从 14 变 17。**本波不改常量**——理由同第 2 行，逐 WI 递增会把 `lint_e2e_groups.py` 变成串行写点。R-6a 在 `baseline-1b` 里仍是三条，`EXPECTED_BASELINE_ITEMS = 61` 不受影响 | Wave 4 前的 R-6 裁定（2026-09-03） | **WI-17（Wave 7）**，与第 2 行同一次落地 | `EXPECTED_ACCEPTANCE_ITEMS == 17` 且四个 acceptance 目录实测合计等于它 | **已结清（2026-09-04）**：`EXPECTED_ACCEPTANCE_ITEMS = sum(EXPECTED_ACCEPTANCE_PER_DIR.values())` **派生**而非字面量，逐目录 8/4/4/1 各自单独校验、实测合计 17 |
| 15 | **字号 ± 与段落间距 ± 四个按钮没有 testid**，R-6a 只能靠 ARIA 可访问名定位。**可访问名不是中文 `title`，是按钮的文本内容 `−`（U+2212）与 `+`**——accname 计算里 contents（2F）先于 title（2I）。本行原先写作「靠中文 `title` 的可访问名（`减小字号` / `放大字号`）」，那是错的，2026-09-04 由 WI-14 实测订正：`name="减小字号"` 匹配 **0** 个、`name="−"` 匹配 **1** 个，两个容器里都是这样。订正后真正的脆点有两条，且都跟原先写的不是一回事：**(a)** 中文文案怎么改都不会断，改**字形**（`−` 换成 ASCII `-` 或 `–`）当场断，且断时报的仍是「找不到元素」而不是「字形改了」；**(b)** 四个按钮的可访问名两两重名（两个 `−`、两个 `+`），所以**必须**用 `rd-pref-size` / `rd-pref-leading` 限定作用域——不限定就解析到 2 个节点、触发 strict mode 违规。这是**正确性要求**，不是写法讲究。 | Wave 4 派活前的实测（2026-09-03）；名字来源于 2026-09-04 订正 | ~~**4A**（给四个按钮补 testid，与 ADR-0014 的命名规则一致）~~ ⬛ 2026-10-02 维护者裁定：→ **014 WI-18**（4A 即 013，已合入未付）。WI-18 的 testid 清单今天只列 `rd-pref-size-inc/-dec`，须补上行距那一对；R-6a 改走 `get_by_test_id` 属冻结集改动，与 #6 / #24 / #69 同一次 `suite_hash` 变更 | R-6a 改用 `get_by_test_id`，全仓不再有按 `−` / `+` 字形定位的用例 | 未结清 |
| 16 | **一次页面加载会跑两遍 `loadAndRender()`**：`annotations.js` 在 `onContentsReady` 里当场调一次，同时又监听 `reader3:content:rendered`（由 `epub-renderer.js` 必发）触发一个 80ms 去抖的第二次。第二遍先 `clearExistingAnnotationMarks()` → `parent.normalize()`，再重建**数量完全相同**的 `<mark>`，所以「等 `<mark>` 数量到位」这个判据在结构上看不见它。夹在两遍之间装上的 live range 会被 `normalize()` 就地折叠成空 range，`getExistingAnnotationIds` 于是一条都匹配不到。**这是本模块约四成 flaky 的唯一根因**，一次解释了 `test_w5a0` / `test_w5a2` / `test_w5a3` 四个 ID 的三种不同表象 | Wave 3.5 收口时诊断出（2026-09-03） | **无需修**——加载期这是有界瞬态（80ms ＋ 一次 fetch），真实用户选不进这个窗口；欠的是**把它写进等待判据**，已由 `_open_ch0` 的 `wait_for_load_state("networkidle")` 兑付 | `tests/e2e` 连续 9 轮全绿（含 2 轮 CPU 打满），模块单跑 8/8 绿 | **记录在案**（测试侧已挡住） |
| 17 | **同一双重重绘模式也出现在写入路径，那一侧疑似能伤到真人。** `createAnnotation` / `deleteAnnotations` 各自都已经 `await loadAndRender()`，紧接着 dispatch `reader3:annotations:updated`，而该事件同样被 `scheduleRefresh` 监听 ⇒ 80ms 后再跑一遍多余的 `loadAndRender()`。加载期那一遍只是测试隐患，写入期这一遍意味着**用户在 ~150ms 内连按两个工具栏按钮，第二次操作的 live range 可能被第一次的尾随重绘折叠**——即欠账 #9 那条数据丢失路径的一个真实世界变体。**未验证**，Wave 3.5 只是读代码时注意到，没有去复现 | Wave 3.5 收口时注意到（2026-09-03） | ~~**待定**（前端计划；与欠账 #9 同一批人，建议同一个工作项一起看）~~ ⬛ 2026-10-02 维护者裁定：→ **014 WI-15**（事件契约），与搬动这段代码的 WI-14 一起做；先在冻结集外写复现用例 | 连按两次工具栏按钮后标注数量与颜色都符合预期，且网络日志里没有 `quote: ""` 的 400 | 未结清 |
| 18 | **`collections_service._NAME_RE` 把连字符判成范围端点**：模式写作 `r"^[A-Za-z0-9 _\\-\\.&()]+$"`，raw string 里每个 `\\` 是一个**字面反斜杠**，于是 `\\-\\` 被解析成「从 `\\` 到 `\\`」的**字符范围**，连字符当场失去字面身份。后果两个方向都错：`"sci-fi"` 这类再普通不过的集合名**建不出来**（用户可见），而 `"a\\b"` 反倒放行。实测复现：`_NAME_RE.match("a-b")` 为假、`_NAME_RE.match("a\\b")` 为真 | WI-15（2026-09-04 发现，主控独立复验） | ~~**011 后端重构**（`collections_service` 归后端）~~ ⬛ 2026-10-02 维护者裁定：→ **backend sweep 小分支（编号待分配；在 012 开分支之后开，合入不得早于 012 开分支）**。011 已合入（PR #22）未付：`collections_service.py:27` `_NAME_RE` 在 `94dd1e0` 上仍是原样 | 连字符名可建、反斜杠名被拒，且有单测把两个方向都钉住 | 未结清 |
| 19 | **K4 的 `reader3:chapter:change` 这根线今天可以单独剪断，而全套件没有一条会红。**`scheduleRefresh` 被冗余接在**三个**事件上（`reader3:content:rendered` / `reader3:chapter:change` / `reader3:annotations:updated`），外加一路独立的 `Reader3Epub.onContentsReady` 回调；剪掉任意一根，换章重绘照常发生。**这同时证伪了覆盖矩阵 §WI-13 写下的自检预言**（原文预测「注释掉该监听 ⇒ 翻章后没有任何 `<mark>` ⇒ 红」）——WI-13 用带计数器的 `page.route` 确认改写确实生效、目标串确实被替换，模块仍 `3 passed`。所以 R-4 护住的是「换章会重绘」这个**可观测行为**，不是 K4 点名的那根线。谁要靠 009 挡住 K4 回归，得另外写一条直接断事件派发的用例 | WI-13（2026-09-04 实测证伪） | **WI-17（Wave 7）** 或 K4 的兑付方，需先决定「护行为」是否已经够（可能够，那就把矩阵的预言删掉而不是加用例） | 要么有一条用例在该监听被剪断时转红，要么矩阵里那句自检预言被删除并写明理由 | **已结清（2026-09-04，取后一支）**：矩阵 `tests-20260901-224500.md` §WI-13 的那句预言已划掉并附证伪记录。**不补用例是有意的**——R-4 护的是「换章会重绘」这个可观测行为；断言某一根具体监听存在，等于把一处冗余布线钉成规格，011 / 014 重写外壳时它只会变成假警报。K4 那根线的回归防护归 K4 自己的兑付方，写一条直接断事件派发的用例 |
| 20 | **`findAndGo()` 在 `Reader3Epub.displaySectionIndex` 缺失时回退到 `window.location.href`**，于是一个彻底坏掉的站内导航器会**降级成一次看起来完全正确的整页加载**。WI-13 的定向破坏 D5 实测：删掉 `displaySectionIndex` 之后，`<mark>` 数量、文本、id 集合、以及 `pathname_is` **四项全绿**，只有事先埋在 `window` 上的哨兵变量抓到了降级。**这是契约不是缺陷**（回退本身是好设计），欠的是**任何做站内导航的用例都必须带这个哨兵**，否则它以为自己在测站内导航，其实测的是整页加载 | WI-13（2026-09-04 发现） | **无需修**——欠的是写法，已由 R-4 的哨兵示范 | 全仓不存在「声称测站内导航但没有哨兵」的用例 | 记录在案 |
| 21 | **主题四态（白/黄/护眼/夜间）是死的**：`rd-pref-theme-paper` / `-sepia` / `-green` / `-night` 四个 `<div class="theme-option">` 全仓**没有任何监听器**——`src/reader3_app/web/static/` 下 grep 不到 `theme-option`、`selectTheme`、`data-theme`，模板里也没有内联 `onclick`；CSS 自带 `cursor: not-allowed`，注释写着 `/* Theme selector (UI only for v1) */`。**与欠账 #11（`rd-page-*`）同型**：testid 存在会让人以为背后有行为，R-6a 因此只能断言「点了主题之后标注还在」，而不能断言「主题变了」 | WI-14（2026-09-04 实测，主控独立复验 grep 为空） | ~~**4A / 前端计划**：要么接上行为，要么把四个 testid 删掉——留着裸 testid 是在骗后来的用例作者~~ ⬛ 2026-10-02 维护者裁定：→ **014 WI-18**，按默认确认「接上行为」（其规格已是含 `auto` 的五项 radiogroup）。原地接线不碰冻结集；改名 / 删 testid 或让元素不可点才会动 R-6a | 四个主题可点且生效，或四个 testid 从模板消失 | 未结清 |
| 22 | **字号 / 段落间距的改动传到 iframe 里晚一拍，第一次点击对正文毫无效果（用户可见）**：四个按钮的处理器都是先 `applySettings()` 后 `saveSettings()`，而 `applySettings()` → `Reader3Epub.applyThemeSettings()` → `buildContentCss()` → `getFontSettings()` **是从 `localStorage` 读的**，此刻 `saveSettings()` 还没写。外层 `documentElement` 的 CSS 变量当场就对，只有 iframe 内容拿到上一次的值。实测（间距基线 1.9 × 17px = 32.3px）：`−` 第一次 → 32.3px（纹丝不动）、`−` 第二次 → 30.6px、`+` 第一次 → 28.9px、`+` 第二次 → 30.6px——每一步都恰好落后一拍。修法是把两行调个个儿，或让 `applyThemeSettings` 收参数而不是回读 `localStorage` | WI-14（2026-09-04 实测，主控独立复验调用链） | **009 合并后的一条独立小分支**（2026-09-04 裁定，记在[进度盘](../../20260824-frontend-backend-plan-progress.md)；不插进 009，§0.5 不开行为变更窗口）。前端计划 §6.1 落 WI-18，届时只需复核 | 点一次 `+`，iframe 内 `--reader-font-size` 当场变；R-6a 的步进断言不再需要点两次 | **✅ 2026-09-06 结清**（分支 `016-settings-apply-order`）。**修法不是调换那两行**：病根是 `epub-renderer.js` 自己回读 localStorage，顺序只是它的第一个后果；第二个后果是边界校验只在 `reader.html` 里，越界值只被外层挡住（实测：面板 17px、正文 99px、行高 891px）。生产侧改成把校验过的值经 `applyThemeSettings({fontSize, lineHeight})` 传下去，两个后果一起消失，顺序怎么摆都绿——所以**没有**动那两行，动了反而是一处测不出来的改动。钉住它的是 R-6a（刺激收成一步）与新增的 R-6c（面板与 iframe 必须同源）；`baseline_1b` 66→67、`suite_hash` `e7e0f9626df5`→`8f39737ca0c6` |
| 23 | **多选模式没有视觉反馈**：`library.js` 的 `setSelectMode` 往 `<body>` 上加的类叫 `select-mode`，而样式表里写的是 `.selection-mode .select-checkbox { opacity: 1 }`——**两个名字对不上**，于是进入多选模式后复选框仍是 `opacity: 0`，只有 `.book-card:hover` 那条兜底规则能让鼠标悬停时露出来。键盘用户与触屏用户因此完全看不到自己已经进了多选模式 | WI-15（2026-09-04 发现，主控独立复验两处类名） | **前端计划 WI-13**（4A.4 书库页切片；改一个类名即可，但哪个名字是设计想要的归那边裁定，见其 §6.1）（⬛ 2026-10-02 维护者裁定：兑付方无误，已付，见状态列） | 进入多选模式后不悬停也能看到复选框 | ~~未结清~~ ⬛ **已结清（2026-10-02 维护者裁定，核实于 `94dd1e0`）**：`4ec22db`（013 WI-13）后 `frontend/src/library/index.ts:276` `classList.toggle("select-mode", on)` 与 `frontend/src/library/index.css:507` `.select-mode .select-checkbox` 名字对上。无用例钉可见性（`shell_4a/test_library_functional.py:56` 用 `include_hidden=True`）；若要护栏，加进 014 WI-16b |
| 24 | **阅读器左栏的「回书架」链接没有 testid**，只有 `title="Back to Library"`（`reader.html` 的 `<a href="/" class="rt-btn">`）。X-2a 的往返因此只能靠英文 title 的可访问名，**与欠账 #15 同一脆弱类**：合规、lint 拦不到、改文案即断 | WI-15（2026-09-04） | ~~**4A**（补 testid，命名按 ADR-0014）~~ ⬛ 2026-10-02 维护者裁定：→ **014 WI-16**（定义 `rd-header-back`；4A 即 013，已合入未付）。X-2a 改走 testid 属冻结集改动，与 #6 / #15 / #69 同一次 `suite_hash` 变更 | X-2a 改用 `get_by_test_id` | 未结清 |
| 25 | **Wave 4 又攒下一批该上收的 helper，且 `_open_ch0` 已经重复三份**（`test_write_recolor_and_delete.py`、WI-14 的 baseline 模块、WI-14 的 acceptance 模块）——它同时**背着欠账 #16 的等待纪律**，复制一份就多一处会悄悄退化的等待；WI-13 的 `_settled(page, frame, expected_marks)` 是同一条纪律的又一次转写。连带待上收：`_open_font_popover`、`_content_style`、`_assert_corpus_unchanged`，以及 WI-15 的 `_assert_visible_book_ids` / `_read_collections` / `_collections_file` / `_delete_collections_with_prefix` / `_http_json`。**另需写进 §0.6 的不是 helper 而是一条纪律**：共享 worktree 的并行波次里，定向破坏一律走 `page.route` 改写响应体，**绝不原地改 `src/`**——Wave 4 里 WI-14 的 S1 破坏被并跑的 WI-13 当场撞见（WI-13 处置正确：不碰，自己全程走 `page.route`） | Wave 4（2026-09-04） | **Wave 5 的 WI-10**（下一个被授权写 `helpers.py` 的工作项；共享文件授权制见 §0.6） | `grep -c "def _open_ch0\|def _settled" tests/e2e/baseline_1b/*.py tests/e2e/acceptance_4b1/*.py` 为 0。**纪律那一半已结清**：009 里已无并行波次（Wave 5/6/7 全独占），真正的消费者是 011/013/014，所以它已上收进[迁移计划 §5 的工程实践表](../plan-tech-stack-migration.md)，不留在本表 | **已结清**（Wave 5 / WI-10，2026-09-04：十一个 helper 进 `helpers.py`，七个模块切换调用点，验收 grep 为 0。唯一非纯改名的是 `assert_corpus_unchanged`——四个模块各查各的字面量，抽成 `assert_corpus_unchanged(*checks)`，期望值与消息逐字留在各模块的 `CORPUS_CHECKS`，基准仍是字面量） |
| 26 | **未建索引的书，AI 提问只在「整句是正文子串」时才能回答**：`ai/rag.py` 的 `_keyword_fallback` 用 `text.lower().find(query.lower())` 拿**整个提问**当子串找，不分词。实测 `'Alpha prose'` 200、`'Alpha 这一章讲了什么？'` 400（`This book is not indexed for semantic retrieval yet`）。用户在没跑 `--index` 的书上问任何自然语言问题都会被拒，而错误文案只说「没建索引」，不说「换个问法」。这是降级路径的可用性缺陷，不是 bug；009 只特征化（X-1 的提问因此取 `"Alpha prose"`） | WI-16（2026-09-04 实测） | ~~**011**（`rag.py` 属后端重构范围；改法是分词后任一关键词命中即回退，或至少把 400 文案改成可操作的）~~ ⬛ 2026-10-02 维护者裁定（产品决定取默认）：未建索引的回退**按关键词匹配**——分词后任一关键词命中即回答，零命中的 400 改成可操作文案（「建索引，或换含正文关键词的问法」）。拆两半：`rag.py` 半边 → **backend sweep 小分支（编号待分配；在 012 开分支之后开，合入不得早于 012 开分支）**（`rag.py:20` 经 `vector_search` 的 `_load_book` 取书，012 WI-7 会改它，按 WI-7 排先后）；「X-1 可改回矩阵原问题」一句触及 `baseline_1b`，→ **014** 的冻结集改动 | 未建索引的书上，含正文关键词的自然语言提问返回 200 SSE；X-1 的 `QUESTION` 届时可改回矩阵原句并保持绿 | 未结清 |
| 27 | **验收组的 17 条 skip 用例引用了 18 个今天还不存在的 testid**：`rd-degrade-s1` / `-s1-action` / `-s1-excerpt` / `rd-degrade-s3` / `rd-note-stale-badge` / `lib-degrade-s2` / `-s2-action` / `-s2-reindex` / `lib-degrade-s3` / `-s3-action` / `-s3-list` / `-s3-toggle` / `lib-status-stale` / `lib-storage-format-badge` / `rd-conflict-dialog` / `-keep-mine` / `-take-remote` / `-close`。另有一个非 testid 的待定名 `DEGRADED_ATTR = "data-annotation-degraded"`（挂在 `rd-shell` 上）。**`rd-conflict-dialog-close` 不是待实现项**——2a 的用例断言它必须**不存在**（Modal 通式 `*-close` 的反例），实现方照着清单批量加 testid 时最容易顺手把它也加上，那会让那条用例转红 | WI-17（2026-09-04 清点） | ~~**010 / 013 / 014**，各自落自己那一组~~ ⬛ 2026-10-02 维护者裁定：010 / 013 已合入，余下的 → **014 WI-16**（阅读页 DEG-S1）＋ **014 WI-16b**（书库侧）；后端信号来自 012 #54 / #55 与 018 #56 / #58。`rd-conflict-dialog*` 三个已由 `cc6bb18`（011 WI-5b）落地，`rd-degrade-s1/-s3`、`lib-degrade-s2/-s3` 已在 `degrade-banner.ts`（`d2f02c7`，阅读页入口未挂载）；`lib-status-stale` 在 D12 改名 `lib-book-grid-status-*` 后是否作废由 WI-16b 定；`acceptance_p3/test_deg_states_plain.py` 的 skip 理由仍写「012 落地」，WI-16b 知悉 | 对应用例的 `skip` 摘掉后转绿，且 `rd-conflict-dialog-close` 仍不存在 | 未结清 |
| 28 | **两张 `DEG_TESTIDS` 表必须是裸赋值，不能加类型注解**：`tests/unit/test_e2e_group_guard.py` 的 `_testid_table_keys()` 只 walk `ast.Assign`，加了 `: Dict[str, str]` 就变成 `ast.AnnAssign`，守卫**静默失明**（不是报错，是查不到表、当成两组用例没有共用键集）。该文件已入红收据 `009-WI-17` 按行冻结，本波因此改的是被测模块而不是断言——两个 DEG 模块各留了四行注释说明「不加注解是有意的」。`tests/unit/test_deg_assertions_shared.py` 已同时认 `Assign` / `AnnAssign`，所以只差守卫这一处 | WI-17（2026-09-04） | **下一个有正当理由动 `test_e2e_group_guard.py` 的人**（改它要重录红证） | `_testid_table_keys()` 两种赋值形态都认，两张表可以加回注解 | 未结清 |
| 29 | **`PUT /api/notes/{book}/{ch}/{id}` 今天只收 `note_text`**（`UpdateAnnotationRequest` 就这一个字段，`notes_service.update_annotation` 也只写它，空 `note_text` 直接 400）。W-5b 要求的「原地改色」因此在服务端就走不通——这是 W-5b 挂 skip 背后的**第三个阻塞点**，此前只记了欠账 #9 与两条前端分支 | 修 #54 时读 `src/` 发现（2026-09-05） | **4B.1**（要动 `src/`，009 无 `src/` 窗口） | `UpdateAnnotationRequest` 有承载颜色的字段，且 `test_w5b_recolor_keeps_id.py` 解 skip 后那条 PUT 不再 400 | 待兑付 |
| 30 | **`acceptance_4b1` 每个模块只允许一个 skip 构造**（`lint_e2e_groups.py` 的静态 skip 轴），因此 R-6b 的主题参数排除只能写成数据字段 `excluded_because`，不能用 `pytest.param(marks=pytest.mark.skip(...))`。这条约束今天没有定义处，只活在 lint 的实现里 | 修 #53 时撞上（2026-09-05） | **#22 或 4B.1**（择一，写进 `lint_e2e_groups.py` 的文档串即可） | `lint_e2e_groups.py` 里能 grep 到这条规则的成文理由，而不是只有实现 | 待兑付 |
| 31 | **§7 承诺过的「发版关门检查里跑一次 `baseline-1b` 全量」从来没建出来。** 核查 `.github/workflows/`：`tests.yml` 101 行只有 `unit` 一个 job（`:43`），`lint.yml` 79 行只有 `contracts`（`:36`）和 `wheel`（`:59`）；全仓 CI 没有 Playwright、没有 e2e lane、没有 `baseline-1b`。本地 `.claude/tdd-guardian/config.json` 的 e2e lane `gateOn: ["push"]`（`:29`），跑的是同一台开发机的同一个运行剖面。后果：soak 那 10 次绿里，**「环境多样性」那一半没有任何补偿**——这是已知缺口，不是已生效的控制。**方向已于 2026-09-19 裁定：建 job，不删承诺。** 形状是往 `tests.yml` 里加第二个 job，**跟着现有的 `on:` 走，不新增触发器**——两个 workflow 今天都只认 `release.published` / `push.tags: v*` / `workflow_dispatch`（`tests.yml:31-36`、`lint.yml:23-28`，2026-08-23 定的口径），所以日常 commit 与 PR 一律不跑，日常门禁仍归本地 tdd-guardian 的三条 lane。**台账「环境多样性」那一半不靠发版填**：实测发版间隔可达八个月（`v1.4.0` 2025-12-28 → `v1.5.0` 2026-08-26），一年一两次填不满十行；靠手点 `gh workflow run tests.yml` 补行，而 `workflow_dispatch` 正是 `lint.yml:19` / `tests.yml:23` 早就写下的补偿手段，复用它，不发明新机制 | [§7 soak 门槛](../plan-tech-stack-migration.md)（2026-08-16 立下承诺，2026-09-18 核出未兑付） | ~~**待定**（做的人与落在哪个 WI 未定；**方向不再待定**——2026-09-19 已定为「建 job」，见左栏）~~ → **[018 WI-7](./018-library-routes.md)**（收尾对账；⬛ 2026-09-30 改：job 本身 2026-09-20 已建成，见状态列，WI-7 只做对账与合并头上的一次 CI 核验，2026-09-26 裁定 D1 并入 018） | 两条都要。**(a)** `grep -rn "playwright\|tests/e2e" .github/workflows/` 命中一个真的 `run:` 步骤——今天该命令只回 1 行（`lint.yml:48`，选择器 lint 的步骤名），`playwright` 零命中。**(b)** 该 job **在一次 `workflow_dispatch` 或 tag 触发上见过红**，光有 job 定义不算兑付（闸空转与闸通过在输出上同形）。**(b) 这一条 2026-09-19 订正过**：原文写的是「在一次**真实 PR** 上见过红」，而本仓 workflow 仅发版触发、**PR 上永远不会跑**，照字面这笔账结不了——「见过红才算兑付」的要求保留，换的只是载体 | **已结清**（2026-09-20）。**(a)**：`.github/workflows/tests.yml` 加了第二个 job `e2e`（9 步），触发器一个没加，跑 `scripts/soak_run.py`（要 67/67，不是「没红」）＋ `-m "not baseline_1b"` 余下各组；`uv sync --frozen --all-groups` 锁 lock，另有一步专记 Chromium 版本；`--append` 刻意不给。**(b)**：`gh workflow run tests.yml --ref 011-backend-refactor` 手点两次，[35499892289](https://github.com/anzchy/reader3-pro/actions/runs/35499892289)（`a73b4a5`）与 [35500630451](https://github.com/anzchy/reader3-pro/actions/runs/35500630451)（`4f5121d`）**两次都红**——字面意义上的「见过红」。环境层两次全绿，红的是 lane 本身。**这条账结清不等于闸通过**：机制挑战闸第 1 项由此从「未验证」变成**验证为 FAIL**，结果见 [`soak-log.md` §机制挑战闸执行记录](./soak-log.md)，后续红由 #44 / #45 / #46 接手。首次真跑还暴露了 job 自己的一个缺陷（红了却说不出是谁红的，明细 log 进了 `tempfile.mkdtemp()`），已于 `4f5121d` 修 |
| 32 | **欠账 #10 的结清判据不是回归闸，而且同一个缺陷类在第二个现场活着。** #10（`:367`）2026-09-03 当日结清，判据是 `uv run pytest tests/e2e --browser chromium` 全绿——对一条**载荷相关**的缺陷用一条载荷相关的判据，等于没建闸：[soak-log.md](./soak-log.md) 记 Wave 2 那段自己写着「21 条时写不满 64 KiB 所以从没发作」，也就是说只要用例数退回 27 条以下，把 `stdout` 改回 `PIPE` 这条判据照样全绿。核查时在 `scripts/smoke_installed_wheel.py` 找到第二个现场：它起的也是 `reader3-server`，`stdout=subprocess.PIPE` 由 `1392b1f`（2026-08-23）带进来，**比 #10 建账还早**；`21b3a86`（2026-08-24）改过紧挨着的 `terminate()→kill()` 那几行也没看出来。潜伏原因同样是载荷：该脚本只打 4 个路由（`smoke_installed_wheel.py:212-217`），远写不满 65536 字节，而 e2e 全量 35 条实测要写 74194 字节。该行存活 **26 天**，其中 **15 天是在这个缺陷类已经被命名、被写进台账之后** | #10 的结清方（2026-09-03 只修了发作的那一处，没做同类现场走查） | **WI-T7（011）**，2026-09-18 | `tests/unit/test_service_subprocess_pipe_capacity.py`：AST 走查全仓，凡 `subprocess.Popen` 起 `reader3-server` 类长命服务且 `stdout=PIPE` 即红。它自带三条自检——认得出三个已知现场（`test_the_gate_recognises_every_known_service_launch`）、不误杀 `soak_run.py:322`（那处 `PIPE` 下一行就 `communicate(timeout=)` 全程 drain）、以及对伪造现场必红（`test_the_gate_still_has_teeth_on_a_fabricated_offender`）。没有这三条，闸空转和闸通过在输出上同形 | **已结清**：`smoke_installed_wheel.py` 改为 `stdout=log_fh`、失败路径读日志尾巴而不是 `communicate()`；unit lane 1247 → **1256 passed / 2 skipped**（46.36s）。**判据从「跑一遍全绿」换成了「这一类写法在仓里不存在」——后者不随用例数变化** |
| 33 | `smoke_installed_wheel.py` 的 `log_tail()` 是 `main()` 里的闭包，**没有任何测试走到它**。它只在三条失败路径上被调用（进程早退、启动超时、路由非 200），而冒烟绿的时候这三条都不执行。这正是 `21b3a86`（2026-08-24，提交标题：「wheel smoke 守卫抓到 bug 的那一刻会死锁，而不是报告」）那次的同一个形状：**报错路径的 bug 只在报错时暴露，而平时没人报错** | WI-T7 自己（2026-09-18 引入 `log_tail()` 时就没给它测试，已当场记账，不是事后发现） | ~~**待定**（提出来的修法是把 `log_tail` 提成模块级函数收一个 `(fh, path, limit)`，这样能用真文件直接测；要不要为一个冒烟脚本付这个结构成本，是维护者的选择）~~ ⬛ 2026-10-02 维护者裁定：付，按原修法 → **backend sweep 小分支（编号待分配；在 012 开分支之后开，合入不得早于 012 开分支）**（`scripts/smoke_installed_wheel.py:173` 仍是 `main()` 内闭包） | `grep -n "def log_tail" scripts/smoke_installed_wheel.py` 命中的是模块级定义而不是 `main()` 内的缩进闭包，且 `tests/unit/` 下有一条用真文件断言「尾巴被截到 limit 且返回的是文件末尾那段」的用例 | 未结清 |
| 34 | **`test_an_unmeasurable_critical_path_fails_the_gate` 自 2026-09-19 起是「因为另一个原因」绿的。** 它的配置用顶层 `"branch": 60`，而该写法现在判配置错误（G11），于是它在量任何东西之前就退非零了——断言 `code != 0` 照样成立，但它宣称钉的语义（**设了门槛却量不到 ⇒ 拦**）不再由它证明。**今天不缺防护**：那条语义已由新增的 G10 用规范的嵌套写法重新钉住，且断的是失败原因而不只是退出码。缺的是这条用例的**名字与它实际走的路径对不上**——留着它，下一个读的人会以为不可测那条路有两重保险，实际只有一重。**不就地改是有意的**：它的每一行都在红收据 `WI-T8` 里，改它就是实现在改自己的规格 | WI-T8（2026-09-19 落 Q2「顶层门槛键判配置错误」时当场记账，不是事后发现） | ~~**待定**（下一个有正当理由动 `tests/unit/test_coverage_gate_failclosed.py` 的人；改它要重录红证）~~ ⬛ 2026-10-02 维护者裁定：→ **backend sweep 小分支（编号待分配；在 012 开分支之后开，合入不得早于 012 开分支）**（`:295` 的用例仍用顶层 `"branch": 60`；删掉并在 G10 注明、或改嵌套形，均须重录红证） | `tests/unit/test_coverage_gate_failclosed.py` 里不再存在「名字说 unmeasurable、实际走配置错误分支」的用例——要么把它的配置改成嵌套写法并与 G10 分工写明，要么删掉它并在 G10 的注释里记一句为什么 | 未结清 |
| 35 | **全库搜索每本书都无条件反序列化一遍正文，只为取 `title` / `author`。** `search_library()`（`src/reader3_app/search_service.py:620`）在 `for book_id in book_ids:` 里**先**调 `load_book_cached(book_id, books_dir)` 拿元数据，**再**谈索引——所以索引缓存无论扩到多大都省不掉这次读盘，`011-iso-*.json` 三份实测 `unpickle_grand_total` 恒为 **95**，WI-8 把 `load_book_index` 上限 4 → 12 一次也没省下。**这一条不属于 C5**：C5（`plan-tech-stack-migration.md:764`）白纸黑字只讲书库首页元数据，同段还写着「C1 说的跨库搜索是低频操作」，把它并进 C5 等于让它消失在一个不覆盖它的完成勾里。它是 **C1 性能目标的剩余部分**，也是门槛 #7 未全额兑付的那一半 | 011 / WI-8（2026-09-20 做隔离基准时钉死） | **012**（`load_book_metadata()` 落地时一并改，与 C5 同一批但各自验收）；~~012 开工时重新裁定优先级~~ ⬛ 2026-10-02 维护者裁定（[012 §6 Q10](./012-storage-format.md)）：**012 出口必需**（门槛 7），Wave A 内 WI-4 之后做（WI-5）；**不阻塞开工**。WI-5 同时须把 bench 合成书库改按新格式落盘，否则门槛 7 过不了 | `scripts/bench.py` 的 `05_library_search_1/2/3` 三步里 `unpickle` 不再每轮 +20；或全仓 grep 不到「为取元数据而 `load_book_cached`」的写法 | **未结清**（2026-09-20 立账。裁定见 [011 §8 门槛 #7](./011-backend-refactor.md)：不阻塞 011 合并） |
| 36 | **重试只覆盖非流式路径；流式与探活两个出网口在闸外。** WI-6 把重试放进 `server._call_provider`（ADR-0006 的唯一 LLM 出口），六个非流式调用点全部受益。但 ollama 的流式 chat 走 `server._egress_post_stream` → `ai/providers/_http.post_stream`，`server._http_get_json`（探活 / 模型列表）走 `_http.get_json`，**两条都不经过 `_call_provider`**。后果对用户是可见的不一致：`max_retries` 填成 10，非流式问答在 503 上重试三轮，流式问答一次就断。**不就地修是有意的**：SSE 已经把前半段正文推给客户端了，重试会让用户看到重复的文本；要接通必须先定「已推出的 chunk 怎么办」——丢弃并让前端重绘，还是只在**零 chunk 已推出**时才允许重试。那是产品语义决策，不是实现细节 | 011 / WI-6（2026-09-20 落地时当场记账，不是事后发现） | ~~**待定**（做的人未定；先决条件是上面那条语义裁定，不是代码）~~ ⬛ 2026-10-02 维护者裁定（产品决定取默认）：**流式只在推出第一个 chunk 之前重试**，已推出文字后照今天的方式失败；**探活不重试**（2–4s 探活有意 `max_retries=0`，`web/routers/settings.py:346-349`），这半按设计结案。流式半 → **012 之后**的 backend sweep（编号待分配）：`web/routers/ai/chat.py` 在 012 文件集内且已到体量上限（546 / 550），逻辑须落在 `server.py` | `grep -n "max_retries" src/reader3_app/web/server.py` 能在流式分支里命中；且有一条用例断言「流式请求在第一个 chunk 推出之前失败会重试、之后失败不会」 | 未结清（⬛ 2026-10-02：探活半按设计结案，流式半仍未结清） |
| 37 | **服务端缺可选依赖时返 400，语义上是错的。** `routers/search.py:206-207` 把 `_require_semantic_deps()` 的 `RuntimeError` 映射成 `HTTPException(400)`。400 的含义是「你的请求有问题」，而这里是**服务端**没装 `[semantic]`——客户端把请求改成什么样都没用。正确的码是 503（暂时不可用、可通过装 extra 恢复）或 501。**011 窗口内不改**：ADR-0011 冻结「Phase 2 不得改变任何响应形状」，状态码是响应形状里最硬的那一项，`tests/contract` 有用例钉着 400 | 011 / WI-7（2026-09-20 拆 `[semantic]` 时核出） | **012 或冻结解除后的第一个有正当理由动 `routers/search.py` 的 WI** | `POST /api/index/{id}` 在依赖缺失时返 503（或 501）而不是 400，且 `tests/contract` 里对应的断言与 `routes.snapshot` 一并更新 | 未结清 |
| 38 | **`Retry-After` 响应头拿不到，退避只能盲猜。** WI-6 的退避是 `uniform(0, min(cap, base·2^n))`，对 429 而言这是在猜；服务端通常会用 `Retry-After` 明说该等多久。拿不到的原因在 `_http.post_json`（`ai/providers/_http.py:165`）：它的返回契约是 `Tuple[int, Dict[str, Any]]`，成功路径与 `except urllib.error.HTTPError` 路径（`:192-195`）**都只取 status 与 body，headers 整个丢掉**。要接通必须改这个函数的返回契约，而它是五家 provider 共用的唯一出网口——改它是五处调用点一起动的事，不是一行 | 011 / WI-6（2026-09-20 当场记为非目标） | ~~**待定**~~ ⬛ 2026-10-02 维护者裁定：→ **backend sweep 小分支（编号待分配；在 012 开分支之后开，合入不得早于 012 开分支）**；最小形状是在 `ProviderHTTPError` 上加可选 `retry_after`，不改 `post_json` 的元组契约 | `post_json` 能把 `Retry-After` 交到 `_call_provider`，且有一条用例断言「服务端给了 `Retry-After: 3` 时退避不短于 3 秒、且仍受 cap 约束」 | 未结清 |
| 39 | **`jupyter` 与 `ipywidgets` 在运行时依赖里，而全仓零处代码引用它们。** `pyproject.toml` 的 `[project] dependencies` 含 `jupyter>=1.1.1` 与 `ipywidgets>=8.1.8`；`grep -rn "ipywidgets\|IPython\|jupyter" --include="*.py" src/ tests/ scripts/` 命中 **0 处**；唯一使用者是 `demo/explore_book.ipynb`。传递闭包实测 **jupyter 100 个包、ipywidgets 21 个包**（`uv tree --package <名> --depth 25` 去重计数），而整个非语义核心（fastapi ＋ uvicorn ＋ jinja2 ＋ beautifulsoup4 ＋ ebooklib）加起来才约 30 个。这与 #37 所在的 WI-7 是同一类缺陷，而且更纯粹——WI-7 那两个包至少支撑着一个已发布的功能，这两个只支撑一个 demo notebook | 011 / WI-7 核查时顺带量到（2026-09-20）；**本身不在 WI-7 范围内，未擅自扩范围** | ~~**待定**（修法已经清楚：同 WI-7 的形状，挪进 `[project.optional-dependencies].demo`，并把 `"reader3[demo]"` 加进 `[dependency-groups] dev` 以保本地与 CI 环境不变。没有做是因为它改变 `uv sync`（无 extra）装出来的东西，而这会影响到每一个下游使用者，该由维护者拍板而不是顺手带过）~~（⬛ 2026-10-02 维护者裁定（产品决定取默认）：**移出运行时依赖**，按上述修法挪进 `demo` extra，dev 组经 `reader3[demo]` 保留，并扩 pyproject 静态检查 → **backend sweep 小分支（编号待分配；在 012 开分支之后开，合入不得早于 012 开分支）**；与 012 WI-11 的 `pyproject.toml` 版本号改动至多是文本冲突） | `[project] dependencies` 里没有 `jupyter` / `ipywidgets`，且 WI-7 那条 pyproject 静态闸把这两个名字也纳入断言 | 未结清 |
| 40 | **011 分支把 `mypy` 从绿弄成了红，而九道出口闸没有一道看得见它。** 实测：`master` 上 `mypy src/` 是 `Success: no issues found in 27 source files`；本分支 `3265cf4`（WI-6 之前）与 `eb8b60b` 上都是 `Found 10 errors in 1 file`，全部是 `src/reader3_app/web/server.py` 的 `Cannot determine type of "router" [has-type]`。病因是 router 拆分引入的循环导入：`routers/*.py` 用 `from .. import server as _server`，而 `server.py` 在文件底部 import 这十个 router 模块；循环里 mypy 推不出 `router = APIRouter()` 的类型。引入者 `2c109c6`（011 WI-4/3 搬 library 组）。**它是一颗发版才引爆的哑弹**：`.github/workflows/tests.yml:75` 的 mypy 步骤没有 `continue-on-error`，而该 workflow 只认 `release.published` / `push.tags: v*` / `workflow_dispatch`，所以日常一次都不会响。**修法已在沙盒工作树里验证**：给十个 router 模块写成 `router: APIRouter = APIRouter()`，`mypy src/` 转绿（`Success: no issues found in 41 source files`），每文件一行、零运行时影响 | 011 / WI-4/3（`2c109c6`）；2026-09-20 做 WI-7 复核时核出，此前账本与任务书里 grep 不到 "mypy" 一个字 | **011 自己**（它把绿弄红的，不该让 012 或发版的人接） | `uv run mypy src/` 在本分支回到 `Success`；且 011 的出口闸表里有一条闸看着它，而不是只靠 CI 在发版那天才说话 | **已结清**（2026-09-20）：十个 router 模块改成 `router: APIRouter = APIRouter()`，`uv run mypy src/` → `Success: no issues found in 41 source files`；新增 `tests/unit/test_router_type_annotations.py` **13 条**把它钉在**日常** lane 上（不只是发版那天）——一层 AST 静态闸（零秒，说得出是哪个文件忘了标注，自带定向破坏与「刚好十个模块」的自检），一层真跑 `mypy src/`（权威判据，热跑 0.47s / 冷跑 15.07s）。unit lane 1541 → **1554 passed, 2 skipped**；`routes.snapshot` 零 diff；红收据 `DEBT-40` verify = SEPARATION-HELD |
| 41 | **tdd-guardian 的红收据计数会被 lane 输出里任何一句「N errors」污染。** `lib/exec.js:148`（⬛ 2026-10-02 指针订正：已装的 0.10.1 在 `scripts/tdd-guardian/lib/exec.js:108-111`，0.8.1–0.9.2 同；`failed` / `passed` / `skipped` 三条正则同样不锚定，也会被污染，不止 `errors`）的 pytest 解析器用 `/(\d+) errors?/i` 在**整段 lane 输出**上搜一次，而不是只看 pytest 自己那行汇总。实测：`test_mypy_is_clean_on_src` 失败时，pytest 的断言解释行会打出 ``where 1 = CompletedProcess(args=[...], stdout='...Found 10 errors in 1 file...')``，于是收据把「11 of 1556 tests failed」记成「**21 of 1566**」——failed 与 total 各被加了 10。判红结论没错（仍是 `assertion-failure`），但**收据存在的意义就是留下可信的数字**，而那两个数字是假的且没有任何提示。本仓已就地绕开（`test_router_type_annotations.py` 里先把退出码绑成局部变量再断言，并滤掉 mypy 的汇总行，滤法与理由写在 `_render_mypy_failure` 的 docstring 里），但绕开只保住了这一个文件：以后任何一条失败信息里带「N errors」的用例都会重新把计数弄假 | 2026-09-20 做欠账 #40 时撞上；**病灶不在本仓**，在 `~/.claude/plugins/cache/xiaolai/tdd-guardian/0.9.1/scripts/tdd-guardian/lib/exec.js` | ~~**待定**（上游修法是把那条正则锚到 pytest 的汇总行上；本仓这边能做的是一条闸：凡断言信息或 `CompletedProcess` repr 会流进 lane 输出的用例，都不许带「N errors」字样。要不要为一个外部插件的解析 bug 在本仓立闸，由维护者定）~~ ⬛ 2026-10-02 维护者裁定（产品决定取默认）：**本仓不立闸**，按外部问题结案，向上游提 issue（把正则锚到 pytest 汇总行）。理由：它只污染收据**计数**，不影响红 / 绿判定，受影响的那一个文件已绕开 | 造一条失败信息里含「3 errors」的用例，`record` 出来的 failed 数比手跑 pytest 的多 3 —— 这条账结清的标志是该复现不再成立 | ~~未结清~~ ⬛ **已结案（外部，2026-10-02 维护者裁定）**：本仓不付；上游 issue 待提。复现仍成立（0.10.1 未修），见欠什么列的指针订正 |
| 42 | **机制挑战闸第 3 项（随机化收集顺序）首轮 FAIL，`baseline_1b` 里有一条真 flaky。** `pytest-random-order 1.2.0`、`--random-order-bucket=global`、seed 1001/2002/3003：前两个 67 passed（54.59s / 56.00s），**seed 3003 首次 1 failed, 66 passed（63.33s）**。红的是 `test_kernel_actions_and_url.py::test_k2_note_action_opens_the_editor_and_the_save_lands_a_note_record[chromium]`，抛在 `tests/e2e/helpers.py:823`：`8.0s 内 notes.json 没有稳定到 1 条，实际 0 条：[]`；隔离前置 `read_notes(...) == []` 过了，不是脏数据。**分类**：seed 3003 原样重放两次全绿（54.75s / 53.14s）⇒ 同顺序两绿一红 ⇒ **flaky，不是顺序依赖**；按 §7 纪律 2「重试只分类不翻盘」，本项仍判不过。**病因查不下去，见 #43** | 2026-09-20 跑机制挑战闸时首次暴露（此前 10 次 soak 全绿，说明它的复现率低于 1/10 个 lane） | **待定**——修法取决于 #43 补出的证据；**注意代价不对称**：落在 `helpers.py` / `baseline_1b/**` 的修法会把 soak 计数 **10 → 0**，落在 `src/` 的不会 | 三个 seed（含 3003）各跑一次，**首次**全绿；或 #43 补的可观测性把这次红归因到一个具名原因上并修掉 | 未结清（**阻塞 Phase 3 / 012**） ⬛ **已结清（2026-09-21），判据原文兑付，但结清的不是那条 flaky。** 对新冻结值 `1e868c7bf811` 重跑：seed 1001/2002/3003 **各首跑一次，三个全绿**（`68 passed, 24 deselected`，55.23s / 55.64s / 54.89s）——判据写的就是这句，逐字满足，机制挑战闸第 3 项判 **PASS**。**先证明随机化真生效**再认绿：K-2 在收集列表里的位次，不加 `--random-order` 时 7，三个 seed 下 13 / 68 / 39，两两 `diff` 差 108–114 行 / 共 136 行。**但 2026-09-20 对那条红的归因（『flaky，不是顺序依赖』）只对了一半，另一半现在被推翻了：它跟 seed 无关，跟 CPU 负载有关。**seed 3003 原样重放 8 次，rep1/rep2 红（2 failed / 4 failed，75.30s / 88.19s，当时我另起了 4 个并发 `--collect-only`，是我引入的混杂）、rep3–8 六连绿（55.61–56.85s）。顺着负载这条线，seed 3003 ＋ 10 个忙等进程**当场复现**，失败签名与 2026-09-20 那条**逐字相同**：`test_k2_type_actions_create_an_annotation_of_that_type[chromium-underline]`，`tests/e2e/helpers.py:823`，`8.0s 内 notes.json 没有稳定到 1 条，实际 0 条：[]`。决定性的对照是**自然顺序**（`soak_run.py:149` 的 `LANE_ARGS` 逐字）＋ 同样压力跑三次：**两红**（rep1 K-2 delete ＋ W-2/W-3 underline；rep2 W-9b ＋ W-5a-③ underline）。自然顺序在同样负载下红得一样勤 ⇒ **顺序不是自变量，负载才是**，第 3 项要照的「用例间顺序依赖」这一类缺陷并不存在。**所以这条 flaky 没修，只是不再归本项管**：它每次红的用例都不一样，横跨 4 个文件，全在「写/改/删一条标注后等 `notes.json`」这条路径上，是**整条写路径在 CPU 争用下的一类失败**，归 #43；而「一次首绿不足以判压力类的闸」归新开的 #48 |
| 43 | **笔记写入路径上有六个把失败吞掉的出口，前五个的可观察结果与 #42 那次红逐字相同。** `src/reader3_app/web/static/js/annotations.js`：`:1145` `!currentRange \|\| !contentEl` → `return`；`:1150` 拿不到 `bookId`/`chapterIndex` → `return`；`:1158` `offsetFromNode` 返回 `null`（iframe 重渲染后 range 指向旧文档）→ `return`；`:58` `fetch(...).catch(() => null)` 把网络层失败变成 `null`；`:1200` 拿到 `resp` 后**从不检查 status**，4xx/5xx 与 200 走同一条路；`:1105` 空文本 → `return`（良性，形状相同）。前三个只写 `console.log`，而 e2e 不捕获浏览器 console；第四、五个连 log 都算不上诊断信息。**同一个文件 `:69` 就有现成的 `showToast()`，写路径一次都没调用。** 后果有两层：用户按了 Save、面板关了、盘上没有，且**全程没有任何提示**；以及 #42 那条 flaky **无法归因**——既不能说「8s 等太短」（按前五条任意一条，请求可能根本没发出去，等 80s 也是 0 条），也不能说产品有保存竞态（没有证据） | 2026-09-20 查 #42 时核出。**分两批，责任不同**：`:1145` / `:1150` / `:1158` / `:1105` 四条静默 `return` 与「不看 status」这一条，追到 `20b1f05`（2025-12-27），**早于 011**；而 `:58` 的 `fetch(...).catch(() => null)` 是 **011 WI-5b（`cc6bb18`，2026-09-20）新加的**——`git show cc6bb18` 可见改前是裸 `const resp = await fetch(...)`。改前网络层失败会抛未处理的 promise rejection（同样没人看，但至少不是「被当成成功」），改后它被折成 `null` 一路走到 `:1200` 那个从不检查的分支。这一条与欠账 #40 同形：**011 自己弄出来的，不该留给 012** | **待定**。两件事，代价差很远：**(i)** 失败出口改成 `showToast()` ＋ `console.error`，`resp.ok` 为假时同样报——纯 `src/`，不碰冻结集；**(ii)** e2e 侧把浏览器 console 接进失败输出——这要动 `tests/e2e/conftest.py`，**在冻结集里，会清零**，所以别顺手做，要单独决策 | (i)：拔掉服务端或让 POST 返 500，按 Save 后界面上**看得见**一句失败提示，且 `console.error` 里有具体哪一条出口 | 未结清 ⬛ **2026-09-21 添一条新证据，把触发条件钉死了：CPU 争用，且可按需复现。** 查机制挑战闸第 3 项时拆变量拆出来的（完整数据在 [`soak-log.md`](./soak-log.md) 第 2/3 项那节）：本机 16 次 `baseline_1b`，**无压力 9 跑 0 红**（54.89–56.85s），**10 个忙等进程压着 5 跑 3 红**，**并发混杂 2 跑 2 红**。红的用例**每次都不一样**——K-2 create（underline）、K-2 delete、W-2/W-3（underline）、W-9b、W-5a-③（underline），横跨 4 个文件，全部挂在 `wait_for_notes` / `wait_for_note_text` 那一族 8s 等待上。**这把 #43 从「一条 flaky 查不出病因」升级成「一个共同表象」**（不是「一类已定位的故障」——见本行末尾的修正）：不是某条用例不稳，是整条写路径在争用下会静默丢写，而六个吞掉失败的出口正好让人分不清丢在哪一步。**注意别把耗时当判别器**：有压力那 5 跑里绿的两跑是 71.16s 和 56.88s，跨了整个区间，红绿在耗时上不可分；唯一稳的相关是「有没有负载」。**这条证据不改 #43 的修法，只抬高它的优先级**——(i) 那半（`showToast` ＋ `console.error` ＋ `resp.ok`，纯 `src/`，不清零）现在有了一个**确定性的复现手段**去验收：压着 10 个忙等进程跑 `baseline_1b`，红的时候界面上/`console.error` 里必须指名是六个出口里的哪一个 ⬛ **同日修正一处措辞，它原本把推断写成了事实。** 上一段初稿写「不是某条用例不稳，是整条写路径在争用下会静默丢写」，证据撑不住：五条红确实全挂在 `wait_for_notes` / `wait_for_note_text` 这一族 8s 等待上，但那是**一个共享的 helper**，于是「同一个 helper」与「同一个根因」在这批数据里**是混杂的**。共享等待器自身有缺陷、调度延迟、请求失败、覆盖写，四种机制都能长出一模一样的表象。**成立的是「值得按一类问题去查」，不成立的是「已知是一类产品故障」。** 这正是 #43 存在的理由——在可观测性补上之前，这个区分做不了 |
| 44 | **机制挑战闸第 1 项 FAIL：`baseline_1b` 在干净 Linux 上两次都红。** run 35500630451（`4f5121d`）红的是 `tests/e2e/baseline_1b/test_write_overlap_and_disambiguation.py::test_w8a_two_overlapping_annotations_both_persist_and_render[chromium]`：`8.0s 内 notes.json 没有稳定到 2 条，实际 1 条`，盘上那条是 A（marker），**没落的是第二条（wavy）**；A 的 `assert_roundtrip`（含一次刷新）已经过了。run 35499892289（`a73b4a5`）也红 1 条，**但那条是哪个用例永久丢失**——job 当时没给 `--log-dir`，明细随 runner 一起没了（已于 `4f5121d` 修），所以不假设两次是同一条。**与 #42 同家族**：都是「一次笔记写入静默地没发生」，只能靠 `wait_for_notes` 超时观察到。**但不要当成同一个 bug**：W-8a 的第二条是在一次**全新页面加载之后**建的（`test_write_overlap_and_disambiguation.py:421` 又 `open_reader` 了一遍），所以对 K-2 成立的「重绘让旧 range 失效」这个解释**对它不直接成立**；六个出口里具体是哪一个，在 #43 补出可观测性之前仍然是猜 | 2026-09-20 首次真跑 CI 时暴露；本地 10 次 soak ＋ 三个随机 seed 全没照出来 | **待定**，但依赖 #43 先行 | `gh workflow run tests.yml` 跑出 **67/67 首次通过**（重试通过不算，§7 纪律 2） | 未结清（**阻塞 Phase 3 / 012 —— 现在是唯一确定性的那条**）。⬛ 2026-09-20 第三跑（run 35512654210 @ `5056614`）再红一次，失败签名与 `4f5121d` **逐字相同**（同一用例、同一断言、同样落了 A 没落 B，A 这次的 quote 是 `Alpha pro`）。计数要诚实：**按用例名确认 2/2**（`a73b4a5` 那跑的名字永久丢失），**按 `1 failed / 66 passed` 的形状确认 3/3**。三跑三红意味着它在 CI 上**不是 flaky 而是确定性的**——这比 flaky 好查，但也意味着它不会自己好。#45 结清后，它是第 1 项转绿路上唯一确定性的阻塞（另有 #46 那条 flaky）。失败明细这次没丢，在 `e2e-logs` 产物里：`gh run download 35512654210 -n e2e-logs` ⬛ **2026-09-21 根因定位并修复，但判据未满足，故仍不结清。** 根因**不是**六个静默出口里的任何一个，是第七个、此前没人列出来的：`replaceChild` 把含 Range 端点的文本节点摘掉时，**按 DOM 规范那个端点不会失效**，它浮到父元素上、offset 变成被摘节点的下标；`offsetFromNode` 于是走**元素分支**，静默返回一个**错**偏移而不是 `null`。所以 #43 列的「`offsetFromNode` 返回 `null` → return」这条**照不出它**——我最初也是这么判的，被一条捕获 console 的探针当场推翻。这正好解释了为什么本地 10 次 soak ＋ 三个随机 seed 都没照出来（时序窗口），而干净 CI 三跑三红（机器慢，窗口大）。**修法**：`annotations.js` 记一份偏移快照（`rememberRange` / `offsetsForRange` / `offsetsUsable`，后者按 `chapterIndex` 校验，因为 `currentRange` 换章时从不置空），并在 `resolveOffsets` 里加一道**上浮回落**——端点不再锚在索引内的文本节点上（`rangeAnchoredIn` 为假）就回落到快照；同时补 `resp.ok` 检查与 `showToast`（顺手还了 #43 的 (i) 一部分）。**回归测试**：`test_w8a_selection_survives_rerender.py`，2026-09-21 从 `tests/e2e/` 根目录**迁入 `baseline_1b/`**（兑付了 #44 落地时记下的那笔 parked 白名单欠账，`EXPECTED_BASELINE_ITEMS` 67→68、`EXPECTED_UNGROUPED_ITEMS` 8→7、`tests/e2e` 全量仍 92）。两次定向破坏证明它有牙：`rangeAnchoredIn` 直接 `return true` ⇒ 红；快照偏移 +1 ⇒ 红在 `quote='rose', position=10`。**本地实测**：`baseline_1b` **68 passed / 55.08s**，e2e lane **76 passed, 16 skipped, 0 failed / 66.21s**（修前是 `2 failed, 74 passed, 16 skipped`）。**为什么仍判未结清**：验收判据写死了「`gh workflow run tests.yml` 跑出**首次**全绿」，而 CI 尚未在这份代码上跑过；且判据里的 67 现在应读作 **68**。全部证据来自本地 macOS，而这条缺陷的全部历史都是「本地照不出来」 ⬛ **已结清（2026-09-21），判据原文逐条兑付。** run [35584711194](https://github.com/anzchy/reader3-pro/actions/runs/35584711194) @ `176c8cb`，`workflow_dispatch`，e2e job 实测 `68 passed, 24 deselected in 76.03s`、`verdict: green`、`suite_hash 1e868c7bf811`、`linux-6.17.0-1022-azure`。**判据里的「67」按本次冻结读作 68**，那是同一件事：全量首次通过。**「首次」是核过的**：`attempt=1`，且 `tests.yml` / `soak_run.py` / `pyproject.toml` 全文 grep `reruns` / `retry` 零命中 —— 没有重试插件在背后兜底，按 §7 纪律 2 够格判绿。**这是本仓第一次在干净 Linux 上把 `baseline_1b` 跑全绿**；前三跑三红且失败签名逐字相同（确定性，非 flaky），所以这一跑不是运气变好，是上浮机制真的被修掉了。连带：机制挑战闸第 1 项对新冻结值 **PASS**（0/3 → 1/3），详见 [`soak-log.md` 机制挑战闸节](./soak-log.md)。**没有顺带证明的事**：第 3 项那条 seed 3003 的红挂在 K-2 上，是**另一条用例**，机制仍未测 |
| 45 | **unit lane 里有一条用例依赖浏览器，在没装 Chromium 的机器上必红。** `tests/unit/test_e2e_group_guard.py::test_positive_selection_of_acceptance_groups_yields_exactly_the_skipped_count` 会 shell out 去跑 `pytest tests/e2e -m "acceptance_4b1 or …"`；**WI-5b（`cc6bb18`）激活 `acceptance_2a` 之后**，那个子进程不再是整组 skip，而是**真的去启浏览器**，于是 `playwright._impl._errors.Error: BrowserType.launch: Executable doesn't exist at …/chromium_headless_shell-1234/…`，子进程退出码 1，oracle 判红。CI 两次都红，**确定性的，不是 flaky**。本地照不出来是因为开发机装着 Chromium。**后果不止于 CI 红**：它意味着 unit lane 的「快、无浏览器依赖」这条性质已经被悄悄破坏了，而本仓的日常门禁正是靠 unit lane 挂在 `commit` 上撑着的 | **011 / WI-5b（`cc6bb18`）**——激活 `acceptance_2a` 的人。与 #40、#43 同形：011 自己弄出来的 | **011 自己** | `uv run pytest tests/unit tests/contract` 在一台**没装 Playwright 浏览器**的机器上全绿（等价判据：`PLAYWRIGHT_BROWSERS_PATH=/nonexistent uv run pytest tests/unit/test_e2e_group_guard.py` 绿）；且闸仍有牙——把某个已激活组改回「带生效 skip」时它照样红 | **已结清**（2026-09-20）。**修法**：那个子进程从**真跑**换成 `--setup-plan` ＋ 逐 item 探针。setup-plan 解析整条 fixture 闭包但**不执行 fixture 函数体、不执行用例体**，于是「不起服务、不起浏览器」重新成立——不是新机制，同文件 `:1251` 的 `test_acceptance_wiring_resolves_without_the_module_level_skip` 早就在用它。探针把逐 item 的 setup 阶段结果**写文件**（不走 stdout，避开 pytest 的输出捕获），补上 setup-plan 下「已激活组那一条既不计 passed 也不计 skipped、只看 summary 数字就无人观察」这个缺口。`src/` **一行未动**（#45 不是产品缺陷）；改的是 `tests/unit/test_e2e_group_guard.py` 与新建的 `tests/unit/test_unit_lane_has_no_browser_dependency.py`（lane 级不变式，1 条，嵌套子进程带 420s 显式上限）。**判据原文实测**：`PLAYWRIGHT_BROWSERS_PATH=/nonexistent uv run pytest tests/unit tests/contract -q` → **`1555 passed, 2 skipped in 48.41s`**（修前 `1 failed`）；等价判据两文件 **`40 passed / 11.46s`**（修前 `1 failed, 38 passed`）；lane 全量含覆盖率 `1555 passed / 2 skipped / 57.45s`，`ruff check` 两文件 rc=0。**牙两个方向都称过**（判据后半句）：给**已激活**的 `acceptance_2a` 加一条生效 skip ⇒ 转红且点名该 nodeid；摘掉**未激活** `acceptance_p3` 的 skip ⇒ 转红且点名那四条 DEG。两次定向破坏后均以 `git diff --exit-code` 证明**逐字节还原**，`tests/e2e/` 与 8 条冻结路径全程零改动，**soak 计数不受影响**。**代价记明，不含混**：原断言 `passed == n_activated` 证明的「DEG-S5 **真的跑过并通过**」**不再由 unit lane 证明**，改由 e2e lane 承担（`75 passed / 16 skipped`，那条就在里面）——这是刻意的 **lane 归位**（「一条浏览器用例通不通得过」不该是 commit 时的性质），已写进该用例 docstring，不是疏忽。**结清 ≠ 闸第 1 项转绿**：CI 侧仍有 #44（`baseline_1b` 的 W-8a）与 #46（Q4 租约 flaky），且 **CI 尚未重跑**，本次全部证据来自本地模拟无浏览器环境 ⬛ **2026-09-20 CI 侧确认死透**：run 35512654210 @ `5056614`，unit job 的 FAILED 行里不再有 `test_e2e_group_guard`，`1 failed, 1554 passed, 2 skipped in 93.14s`，唯一的红是 #46；总数 1557 与本地 `1555 passed / 2 skipped` 逐字对上。结清那天缺的正是这半个证明（当时全部证据来自本地模拟的无浏览器环境），现在补齐了。 |
| 46 | **`test_Q4_worker停不下来时仍释放租约并留ERROR` 的前提断言含一个未写明的时间假设。** `tests/unit/test_ai_queue_lease.py`：假 worker 用 `stuck_delay=3.0`，而收尾断的是 `assert not stuck_stream.exited`（「前提没成立：假 worker 本应无视停止事件，但它停了」）——这要求整段 scenario 在 **3 秒内**跑完。慢 runner 上跑不完，假 worker 自己醒了，前提自毁。CI 两次：**第一次红、第二次绿 ⇒ flaky**。用例 docstring 写着「断言里不出现任何秒数」，立意是对的，但 `stuck_delay=3.0` 把秒数挪进了 fixture，假设仍在，只是看不见了 | 2026-09-20 首次真跑 CI 时暴露；**不是 011 引入的**，在 `tests/unit/` 里，**不在冻结集**，改它不清零 | **待定**。修法方向：让假 worker 阻塞在一个**显式 event** 上而不是 sleep，由用例末尾主动放行——这样「它本应还没停」就成了构造保证，而不是赌机器够快 | 在 CPU 压满的机器上连跑 10 次 `uv run pytest tests/unit/test_ai_queue_lease.py -k Q4` 全绿 | 未结清（与 #44 并列挡着闸第 1 项）。⬛ 2026-09-20 第三跑再红一次 ⇒ **三跑里两红一绿，flaky 判定不变**，挂点仍是前提断言「假 worker 本应无视停止事件，但它停了」。#45 结清后它从「三条红之一」升格为「两条红之一」，分量变重了：闸第 1 项要的是**首次** 67/67 全绿，一条 flaky 足以让它永远赌不过去 ⬛ **已结清（2026-09-21）**。**修法就是本行「修法方向」那一条，照做**：`_FakeOllamaStream` 的 `stuck_delay: float` 换成 `stuck_gate: threading.Event \| None`，`readline` 改成 `self.stuck_gate.wait()`（**不带 timeout**），Q4 整段包进 `try:` / `finally: stuck_gate.set()` 保证不泄漏线程。于是「假 worker 本应还没停」从**赌机器够快**变成**构造保证**：在用例主动放行之前，它在任何速度的机器上都停不下来，墙钟再慢也改变不了这个事实。同批加了一条盯着这条性质的守卫 `test_假流的卡住由放行闸决定而不由墙钟决定`，免得后人把 `wait()` 改回 `sleep()`。**判据实测**：`uv run pytest tests/unit/test_ai_queue_lease.py -k Q4` **连跑 10 次全绿**（0.47–0.82s/次）；叠 12 个 CPU 烧核进程再连跑 10 次，**仍全绿**（0.49–0.78s/次，收尾 load average 3.79）。**这两组数据的证明力要说清**：它们是支持性证据，不是主证据——主证据是「断言依赖的不再是时间」这个结构性事实，因为本机跑得太快，10 次全绿本来也不足以证伪一个只在慢 runner 上发作的时间假设。**不在冻结集**（`tests/unit/`），本次修改不影响 `suite_hash`。**结清 ≠ 闸第 1 项转绿**：CI 尚未在这份代码上跑过 ⬛ **2026-09-21 CI 侧确认死透**：run 35584711194 @ `176c8cb`，unit job `1556 passed, 2 skipped in 96.74s`，**0 failed** —— 这也是「CI 上 unit lane 全绿」第一次真的发生（此前最好的一次是 `1 failed, 1554 passed`，唯一那条红就是本条）。本地那 20 次绿当时只算支持性证据，现在主证据到位了：慢 runner 上也不再赌 |
| 47 | **`scripts/soak_run.py` 在设了 `FORCE_COLOR` 的 shell 里完全跑不起来 —— 而它正是挡着 Phase 3 的那把工具。** `parse_summary`（`scripts/soak_run.py:217`；⬛ 2026-10-02 指针订正：今在 `:229-237`，正则 `_SUMMARY_LINE_RE` 在 `:206-207`）用 `_SUMMARY_LINE_RE.match(raw.strip())` 逐行匹配 summary，**匹配不了带 ANSI 色码的行**。pytest 被 `capture_output=True` 捕获时本来会自动关色，但 `FORCE_COLOR` 会覆盖这个判断，于是每一次都 `SummaryParseError: 输出里找不到 pytest 的 summary 行`。**方向是安全的**（响亮地炸，而不是悄悄记一条错的台账行），但后果是**那台机器上一行都追不了**，而 §7 的跨度条款要的恰恰是「每天真的追一行」。**同源风险**：同一个 `parse_summary` 也是 CI e2e job（`tests.yml` 的 `e2e`）判 67/67 的唯一依据 | 2026-09-20 改 #45 时撞见：同一棵树、同一条 lane，几分钟内从 `1555 passed` 变成 `7 failed`，唯一差别是 shell 中途多了 `FORCE_COLOR=3`。**已隔离证明为环境性**：`env -u FORCE_COLOR uv run pytest tests/unit/test_soak_run.py -q` → `46 passed in 9.34s`，带着则 `7 failed, 39 passed`。台账已有的 10 行全部产自没有该变量的 shell，**历史数据不受影响** | ~~**待定**（不是 011 的账；`soak_run.py` 归 008 一脉）~~ ⬛ 2026-10-02 维护者裁定：→ **backend sweep 小分支（编号待分配；在 012 开分支之后开，合入不得早于 012 开分支）**（`parse_summary` 剥 ANSI 和 / 或给被调 pytest 传 `--color=no`，加 ANSI 夹具用例；`FORCE_COLOR=3` 下 `tests/unit/test_soak_run.py` 在 `94dd1e0` 上复现 7 红）。`soak_run.py` 是判读工具：有批次在判读时不得合入 | `FORCE_COLOR=3 uv run pytest tests/unit/test_soak_run.py -q` 全绿；且 `FORCE_COLOR=3 uv run python scripts/soak_run.py`（不带 `--append`）能跑出 verdict 而不是 `SummaryParseError` | 未结清 |
| 48 | **机制挑战闸第 2 项（CPU 压力）的通过条件是 n=1，而它测的是一个分布——那个 PASS 是抛硬币抛出来的。** 2026-09-21 对新冻结值 `1e868c7bf811` 重跑第 2 项：10 个忙等进程（= `sysctl -n hw.ncpu`），load 压前 13.60、lane 结束 **92.34**，`68 passed, 24 deselected in 71.16s`，`verdict: green`——按[迁移计划 §7 纪律 2](../plan-tech-stack-migration.md)「**首次**通过」，这是字面 PASS。**但同一天用同样的压力源、同样的命令又跑了三次自然顺序，两次红**（`soak_run.py:149` 的 `LANE_ARGS` 与这三次逐字相同，所以它们是同一个实验的第 2–4 个样本）：rep1 `2 failed`（K-2 delete ＋ W-2/W-3 underline，73.93s）、rep2 `3 failed`（W-9b ＋ W-5a-③ underline，77.50s）、rep3 `68 passed`（56.88s）。**四跑两红。** 第 2 项要证明的性质是「这套用例在 CPU 争用下仍然稳」，这条性质**实测为假**；拿一次首绿去认证一条已被证伪的性质，就是这份台账反复警告的「把数字擦亮」。**根子在规则本身**：§7 纪律 2 写死了「首次通过」，却**没定义「一次尝试 = 跑几遍」**——对干净 Linux 那项，一次 CI run 就是一次尝试，没有歧义；对本质上在测**分布**的压力项，n=1 的尝试不构成证据 | 2026-09-21 重跑第 3 项时顺带拆出来的对照组。规则洞本身追到 §7 写就之日 | **§7 的正文**（改通过条件），加 `soak-log.md` 的第 2 项记录 | §7 第 2 项通过条件改成「**连续 k 次**（建议 k=5）在压力下全绿，首轮即须成立」并重跑；或先还 #43 的 (i)，让压力下的红能指名道姓，再回来重跑本项 | 未结清（**阻塞 Phase 3 / 012 —— 三项里现在只剩它挡着**）。第 2 项在此之前记作**未过**，不认那个字面 PASS ⬛ **2026-09-21 经一轮外部复核后，建议从「把 k 改成 5」改成「先不定 k，改定处置规则」。** 原建议（连续 5 次）**被算术否掉**：零失败、n 次固定抽样时失败率的 95% 上界是 `1 − 0.05^(1/n)`，**n=5 时是 45.1%**，即 k=5 只能把失败率排除到 45% 以上——比 n=1 的 95% 好，但远不足以支撑「压力下仍然稳」这句话。（n=10 → 25.9%，n=30 → 9.5%，n=60 → 4.9%。）**三处自我修正，一并记下**：**(a)** 我说过「p≈0.6 连 k=2 都过不去」，**错**——`0.4² = 16%`，仍有六分之一的机会蒙过去。**(b)** 我说过「45% 失败率的套件可以合法通过 k=5」，字面真但**误导**：这种套件通过五跑的概率是 `0.55⁵ = 5.0%`，那正是这道检验的错误放行率，不是「轻松过」。**(c)** 上界公式要求**预先固定 n**；「跑到连续 N 次绿为止」是另一种停止规则，那个置信保证**不成立**（只要单次成功概率大于零，一直重跑几乎必然凑出任意长的连绿）。本仓的 §7 纪律 2「首轮即须成立」恰好堵了这个洞，但**必须写明是预先固定的 N**，不能只写「连续 N 次」。**修正后的建议**：**(1)** 第 2 项 2026-09-21 那次首绿，**按 §7 原文记作 PASS 不动**——事后加跑次数去倒改历史判决，本身就违反纪律 2；但**另记一句**：该 PASS 已不足以支撑稳定性结论，理由是同实验另三跑两红。这比此前写的「建议不认」更干净，它把「过没过这条规则」和「这条规则能不能认证我们要的性质」分开了。**(2)** **现在**就按失败**性质**定处置规则，而不是等跑得动了再挑 k（「看着结果挑验收标准」会让验收失去意义）：确认丢写／错写／失败却显示保存成功 ⇒ 阻塞；确认只是超过 8s 但最终落盘正确 ⇒ 按可接受的保存延迟决定改产品还是改测试（**不能因为 `helpers.py` 在冻结集里就默认产品必须迁就 8 这个偶然数字**）；到调查上限仍无法归因 ⇒ 记「未解决」并显式接受风险，**不得写成「稳定性通过」**。**(3)** 先还 #43 的 (i)，且**只在 `src/` 侧**就够做这个三分——POST 发没发、什么状态码，从另一端回答了同一个问题，**不必动冻结集里的 `helpers.py`**。**(4)** 预算：人工 ≤4 小时 ＋ 无人值守 ≤1 小时；压力下那 5 跑是**诊断预算不是验收**，五跑全绿只说明本轮没抓到。**现在不值得跑 30 或 60 次**——缺的是失败机制的信息，继续堆同样不可归因的超时，边际价值很低。**§7 的条文仍未改**，等这条建议被裁定 ⬛ **2026-09-23 实测裁定：第 2 项 FAIL，不再是「建议不认」。** 同压力源、同命令连跑 7 次，**6 红 1 绿**（唯一的绿是第 4 跑）。**两套规则下都是 FAIL，所以不必先裁定上面 (1) 的条文之争**——按 §7 原文「首次通过」，第 1 跑就红；按本条原建议「连续 5 次全绿」，更不可能。这一点是刻意的：动 §7 条文的人恰好是没过这道闸的人，**在能不动条文就得出结论时就别动它**。**归因**：6 条红**全部**落在 `helpers.py` 的 `assert_roundtrip` 8s 等待族，红的用例每次不同、断言每次相同。**一个必须写明的排除**：其中 W-8a 是 #44 修好的那条，看见它红很容易推成「上浮回归了」——查日志，断言是「8.0s 内 `notes.json` 没有稳定到 1 条」（超时族），**不是 offset 错**，与 #44 无关。**load 量级不是判别量**：唯一那次绿的 load 是全场最高的 176.16，红的都落在 23–30——**有没有压力**相关，**压力多大**不相关。（前 5 跑我没传 `--log-dir`，dry run 的日志写进临时目录被清掉，失败用例名当场丢了；第 6、7 跑补跑才取回来。方法失误，记在此处。）**处置**：上面 (3) 现在可以执行了——`window.Reader3NotesDiag` **已经存在**（`src/reader3_app/web/static/js/annotations.js:147-206`，有界 FIFO，`record` / `entries` 冻结在 `window` 上），即 #43 的 (i) **已交付**。故 (2) 的三分**不必动冻结集**：写一条**新的、非冻结的** e2e，压力下复现这族红、红时用 `page.evaluate` dump 缓冲，按「POST 没发/非 2xx ⇒ 产品缺陷，修 `src/` 不清零」与「POST 回 201 只是盘上没赶上 ⇒ 改冻结的 `helpers.py`，清零 ＋ 三闸作废」二分。**只有落到后者才谈得上付清零那一刀。** 预算照上面 (4)。七跑的数据、逐跑表与推理写在 [`soak-log.md`](./soak-log.md)，此处不重述 ⬛ **已结清（2026-09-24，维护者裁定，moot）。** 2026-09-23 的归因实验判定压力下那族红是测试夹具自伤（`helpers.py` 的 8s 墙钟轮询在跑时浏览器的写请求出不了门，服务端每条毫秒级 2xx，没有一例谎报成功），维护者据此把第 2 项**降为不阻塞的记录项**（不删）。一道只记录、不放行的闸不需要「一次尝试 = 跑几遍」的定义，本条随之失去对象。**§7 的通过条件文字没改，只是不再作放行判据**；若日后第 2 项恢复阻塞，这个洞随之复活，须先补。裁定正文在[迁移计划 §7「机制挑战闸」](../plan-tech-stack-migration.md)，归因证据在 [`soak-log.md`](./soak-log.md) 的「第 2 项归因」一节；剩下的夹具缺陷转入 #49 |
| 49 | **`tests/e2e/helpers.py` 的 `notes.json` 等待是 8s 同步墙钟轮询，轮询期间浏览器的写请求出不了门——测试夹具自己把被测请求摁住 8 秒，再判它超时。** 机制挑战闸第 2 项（CPU 压力）的红全部落在这一族（`wait_for_notes` / `wait_for_note_text`，经 `assert_roundtrip`）。2026-09-23 的 v6 归因臂：7 条慢请求上线前排队 **8007–8151ms**（紧簇在这个轮询的超时点上），服务端全部 25 条 0–11ms、状态 2xx，产品侧无一例吞掉的失败。**这是推断到实测之间差的最后一步**：确认它要换掉轮询后在同一压力臂上看红是否消失，而那必须动冻结集 | 2026-09-23 机制挑战闸第 2 项归因（`helpers.py` 冻结时就带着它；平时的运行剖面照不出来，只在 2 倍超订的 CPU 压力下显形） | ⬛ **2026-09-30 维护者裁定：在冻结集欠账窗口付（018 之前；窗口的分支号开窗时在迁移计划 §9 分配，顺序见[看板「现在该做什么」](../../20260824-frontend-backend-plan-progress.md#现在该做什么)）**，与 #50、017 审计 #10、#62 同一窗口。下面是原兑付方文字，留作历史：~~**延后，不主动付**~~（2026-09-24 维护者裁定）。代价：`helpers.py` 在冻结集里，动一个字节 ⇒ `suite_hash` 变 ⇒ soak 计数清零、三项机制闸按 §7 纪律 4 全部重跑（⬛ 2026-09-28：批次规则下代价降为「在新 `suite_hash` 上重跑一批 ＋ 机制闸第 3 项重跑」，012 门槛 F 同日放宽，本条因此**现在可付**，见 [012 §2.3](./012-storage-format.md)；下面两个触发时机仍是「最晚何时付」）。**触发兑付的两个时机，先到者为准**：(a) 冻结集下一次**不得不**重置（为别的理由改 `baseline_1b/**` / `conftest.py` / `helpers.py` / fixtures 时，顺手一并付）；(b) 笔记保存代码（`annotations.js` 的写路径）被改动时——那时这族等待是唯一的回归网，不能带着自伤上阵。修法方向：轮询期间驱动浏览器（`page.wait_for_*`，或轮询里插 `page.wait_for_timeout`），或者干脆不用墙钟轮询盘，改成等那条在途的写请求（`page.expect_response` 之类）再读盘。**不要只把 8s 调大**——那只是把一个偶然数字换成另一个 | 改完后在同一压力配方（`ncpu` 个忙等，见 [`soak-log.md`](./soak-log.md) 的证据目录）下跑 `baseline_1b` 与 v6 归因臂同样次数：不再出现「上线前排队 ≈8s」的慢请求簇；并把机制挑战闸第 2 项**重跑一次记档**（只记录，它已不阻塞）；第 1、3 项与 soak 计数按清零规则重来（⬛ 2026-09-28：读作「在新 `suite_hash` 上重跑一批，第 3 项对新值重跑，第 1 项在最终候选 `commit` 上过」） | ~~未结清（**不阻塞 Phase 3**；等上面两个触发时机）~~ ⬛ **部分结清**（`019-frozen-set-debts`，`40a0fce`，2026-09-30）。**已付**：两个等待改为轮询间隔里 `page.wait_for_timeout(50)` 泵浏览器（签名加必填 `page=`，49 个调用点同步），8s 上限没动。**推断到实测的那一步已走完，且不靠压力**：新用例 `tests/e2e/test_disk_poll_pumps_inflight_write.py` 对旧 sleep 体在无压力机器上确定性红（`8.0s 内 notes.json 没有稳定到 1 条，实际 0 条：[]`），换泵后绿。同一压力配方 6 跑 0 红，`/api/notes` 上线前排队 max 13 ms（v6 为 8007–8151 ms）；第 2 项记录性重跑绿——数据与口径只在 [`soak-log.md`](./soak-log.md) 本日一节。**未付**（本条验收的后半句）：新 `suite_hash` 上的第一批、第 3 项对新值重跑、第 1 项在最终候选 `commit` 上重过——合入后按[迁移计划 §7「012 开工核验」](../plan-tech-stack-migration.md)进行，那时本条改「已结清」 |
| 50 | **`createAnnotation` 的 POST 请求失败没有接到诊断环上——四个写请求发起点里唯一漏掉的一个，「建」失败时环是空的，和「建成功」不可区分。** `src/reader3_app/web/static/js/annotations.js:1680` 的 POST（经 `notesWriteWithResync`，`:1677`）拿到 `!resp \|\| !resp.ok` 时只走裸 `console.error` ＋ `showToast`（`:1686–1694`），不调 `reportNotesWriteFailure`。另外三个发起点都接上了：`deleteAnnotations` 的 DELETE（`:1136`）、改正文的 PUT（`:1359`）、「保留我的」的 PUT（`:1444`）。同一函数里两道**请求前**守卫也是同形（`:1604` 偏移快照不可用、`:1625` 空 quote，都是 `console.error` ＋ `showToast` ＋ `return`），而函数开头那两道（`:1585` / `:1594`）已经接上——一并收口。这是 #44 时期补的（那会儿环还不存在），后来没迁过去；它是 #43 (i) 的真实缺口 | 2026-09-23 机制挑战闸第 2 项归因时发现（本轮结论不受影响：浏览器侧请求台账不依赖环）。在 `src/`，**不在冻结集**，改它不清零 | ~~**待定**~~（改的是笔记保存代码，按 #49 的触发条件 (b)，**与 #49 同批付**最省：两处一起改、一起在压力臂下验）⬛ **2026-09-30 维护者裁定：在冻结集欠账窗口付（018 之前，与 #49 同窗口，顺序见[看板「现在该做什么」](../../20260824-frontend-backend-plan-progress.md#现在该做什么)）**。本条在 `src/`、不在冻结集，放进窗口是因为它是 #49 的触发条件 (b) | 让 `createAnnotation` 的 POST 请求失败（网络层 `null` 与非 2xx 两种）各往环里恰好记一条（`op` 取 `create`，带 `status`），两道请求前守卫也记（`requested: false`）；单测或 e2e 各构造一次：请求被拒 ⇒ `window.Reader3NotesDiag.entries()` 非空且指名 `create` | ~~未结清~~ ⬛ **已结清**（`019-frozen-set-debts`，`d259f6f`，2026-09-30）：三个出口都改走 `reportNotesWriteFailure`——POST 失败 `op: "create"`（带 `status`；网络层 `null` 时 `status: null`），两道请求前守卫 `op: "create-no-offsets"` / `"create-empty-quote"`、`requested: false`。守卫的 `op` 没取 `create`：取同名会让「请求发了被拒」与「请求根本没发」在环里不可区分，而分开它们正是 #43 (i) 的用意。e2e 在 `tests/e2e/test_notes_write_failure_is_attributable.py`（W1-C11/C12/C13、W6-C6～C8；W1-C8 的旧断言「建失败走裸 `console.error`」随本条反转） |
| 51 | **provider 保存没有服务端版本校验，旧标签页静默覆盖新配置（FB-S09 的后端半条）。** `PUT /api/settings/providers/{name}`（`src/reader3_app/web/routers/settings.py:198`）是 load → patch → save，请求里没有 revision / ETag，服务端无从分辨「基于旧值的写」。前端半条已由 013 兑付：保存失败时设置页可见报错，由 `tests/e2e/shell_4a/test_settings_rows.py::test_provider_save_failure_is_visible` 守着——**本行只剩服务端那一半**。加法式做（可选 revision 字段或 `If-Match`，不带就照旧），否则撞 [ADR-0011](../../../adr/0011-api-v1-freeze.md) 的「不改语义」 | 013 / WI-12（2026-09-24 用户裁定 D8；2026-09-25 裁定 R1 立账） | **018-library-routes**（⬛ 2026-09-30 由 012 改为 018：[012 §6 D1](./012-storage-format.md)（2026-09-26）裁定本条不依赖新存储格式，改写见 [018 WI-1](./018-library-routes.md)） | 两个客户端基于同一 revision 先后保存同一 provider：第二次返回 409 且 `config/ai_settings.json` 保持第一次的内容；不带 revision 的旧客户端行为不变（契约测试） | **已结清（2026-10-01，`2d5f96f`，[018 WI-3](./018-library-routes.md)；经 PR #33 合入 master `c08317b`）**：四个写入端认可选 `If-Match`，过期 → 409 且文件保留先写者——`tests/unit/test_settings_revision_loop.py::test_concurrent_conditional_writes_with_the_same_tag_admit_exactly_one`（真线程池 ＋ 屏障）与 `tests/contract/test_settings_revision.py::test_issue_51_second_stale_save_is_refused`；不带 `If-Match` 照旧由同文件 `test_writer_precondition_table` 的无头行与 `test_star_and_matching_equal_unconditional` 守着；前端 409 可见由 `tests/e2e/shell_4a/test_settings_rows.py::test_provider_save_conflict_is_visible`（真第二写手）守着，013 的 `test_provider_save_failure_is_visible` 未改仍绿 |
| 52 | **没有批量重建索引路由。** 冻结 API 里只有单本的 `POST /api/index/{book_id}`，设置页的 `set-modal-reindex-primary` 因此只显示「暂不支持」、发 0 个请求（[前端计划 WI-12 验收 2 / FB-S05](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md)，裁定 D11） | 013 / WI-12（2026-09-25 用户裁定 D11；同日裁定 R1 立账） | **012-storage-format** | 路由进 `tests/contract/routes.snapshot`（ADR-0011 的新增流程）；对 N 本书发一次请求，N 本的 `/api/index/{id}/status` 都进入重建；前端把「暂不支持」换回真实请求时 FB-S05 的 reindex 半条全量验收 | 未结清（2026-09-25 立账） |
| 53 | **没有书库导出路由。** 冻结 API 只有 `GET /api/settings/export`（设置）与单条会话导出，`set-export-json` 因此只显示「暂不支持」、发 0 个请求（[FB-S06](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md)，裁定 D11） | 013 / WI-12（2026-09-25 用户裁定 D11；同日裁定 R1 立账） | **018-library-routes**（~~**012-storage-format**：导出内容取决于 012 的存储格式，[ADR-0009](../../../adr/0009-book-format-manifest-jsonl.md)~~ ⬛ 2026-09-30：此理由与 [018 WI-6](./018-library-routes.md)「与存储格式无关」（导出只经 `book_store` 读）矛盾，以 018 为准；~~兑付方值本身留待 018 WI-1 与 `test_track_d_ledger.py` 同批改写~~ 兑付方值已于 2026-09-30 由 [018 WI-1](./018-library-routes.md) 与 `test_track_d_ledger.py` 同批改为 018） | 路由进快照；导出体非空且是合法 JSON；FB-S06 的 `set-export-json` 半条全量验收 | 未结清（2026-09-25 立账） |
| 54 | **DEG-S3 的数据面不存在：页面拿不到「是否在 pickle 回退」与未迁移书目清单。** 前端计划 WI-4（DEG-S3）第 1–7 条的服务端半边；朴素横幅已在 [Phase 3 验收](../plan-tech-stack-migration.md)里，本行只管 014 重做形态需要的**两页都能取到**的数据（模板上下文或 API 字段，二选一，加法式） | 013 / WI-13（2026-09-25 用户裁定 D12；同日裁定 R2 立账） | **012-storage-format** | `READER3_ALLOW_PICKLE=1` 下书库页与阅读器页都能取到未迁移书目（书名与 `storage_format()` 一致），未设时取不到；`tests/fixtures/track_d_pinned_014.json` 里引 `012 debt #54` 的钉条由 014 WI-16b（[前端计划的书库 WI](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md)，2026-09-25 由 WI-16 移交）删除时，其测试能在真实数据上跑 | 未结清（2026-09-25 立账） |
| 55 | **DEG-S4 的路由不存在：书卡拿不到 `storage_format`，迁移没有 HTTP 进度，失败项没有逐条重试路由。** 前端计划 WI-5（DEG-S4）第 1–6 条与 FD-05 的服务端半边。`reader3 --migrate` 只是 CLI；逐条重试要求请求体带单本书 id | 013 / WI-13（2026-09-25 用户裁定 D12；同日裁定 R2 立账） | **012-storage-format** | 路由进快照；书库数据每本带 `storage_format`；迁移中进度两次采样不同；对单个失败项重试只发一条请求、请求体书 id 等于该项 | 未结清（2026-09-25 立账） |
| 56 | **没有客户端书目列表路由：书库今天由 Jinja 服务端渲染，没有可失败、可观察 `aria-busy` 的列表请求。** 前端计划 WI-8 第 4 条（FD-20）、FD-03、WI-13 验收 7 的「加载失败」分支、Track-D 第 34 条与 C13.06（`lib-load-failed` / `lib-load-retry`）都卡在这里；WI-4 第 6 条要比对的 `/api/library` 返回值也是它（冻结 API 只有 `/api/library/stats`） | 013 / WI-13（2026-09-25 用户裁定 D12；同日裁定 R2 立账） | **018-library-routes**（⬛ 2026-09-30 由 012 改为 018：[012 §6 D1](./012-storage-format.md)（2026-09-26）裁定本条不依赖新存储格式，改写见 [018 WI-1](./018-library-routes.md)；路由只经 `book_store` 读，不等 012 换格式） | 路由进快照；返回条数等于书库目录数；书名与 `load_book_metadata()` 一致 | 未结清（2026-09-25 立账） |
| 57 | **没有上传 / 导入路由。** 书库的 `lib-add-books` / `lib-choose-files` / `lib-dropzone`（[FB-L01–03](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md)）没有可调的接口；导入今天只有 CLI `reader3 <file.epub>`。新路由写的是书目录，必须走 [ADR-0007](../../../adr/0007-crash-safe-publish-protocol.md) 的发布协议与 ADR-0009 的新格式 | 013 / WI-13（2026-09-25 用户裁定 R3） | **012-storage-format** | 路由进快照；上传一本 EPUB 后书库出现该书且按新格式落盘；非 EPUB 返回 4xx 且不留半成品目录 | 未结清（2026-09-25 立账） |
| 58 | **没有删书路由（FB-L18 的后端半条）。** 删书今天只能手删 `books/{id}_data/`，页面上造不出「A 标签页删书」这个前提。**陈旧写本身服务端已会拒**：`_validate_book_id`（`src/reader3_app/web/server.py:469`）每次现列目录，已删的书对 `POST /api/index/{book_id}` 返回 404（2026-09-25 核过，不另立账）。新路由须同时让 `load_book_cached` 的 `lru_cache` 失效，否则删掉的书还能被读 | 013 / WI-13（2026-09-25 用户裁定 R3） | **018-library-routes**（⬛ 2026-09-30 由 012 改为 018：[012 §6 D1](./012-storage-format.md)（2026-09-26）裁定本条不依赖新存储格式，改写见 [018 WI-1](./018-library-routes.md)） | 路由进快照；删除后同进程内对该书的读与 `POST /api/index/{id}` 都返回 404（缓存不掩盖）；[FB-L18](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md) 的前端半条由此可测 | 未结清（2026-09-25 立账） |
| 59 | **`process_epub` 重导入被杀会留下新旧混版，且旧版随后被删。** `reader3._commit_staged_artifacts` 先换 `book.epub` 与 `images/`、最后才换 marker `book.pkl`，回滚只在内存里；在两者之间 `SIGKILL` → 目录里是新图片 ＋ 旧 `book.pkl`，三态判为 `valid`（不是 `corrupt`）。随后 `_clear_staging_dirs` 把死进程的 staging 当无主清掉——那里放着唯一一份旧产物。2026-09-26 由 Codex 在审 018 锁原型时发现，原型「SIGKILL：导入提交中途」剧本复现 | 已上线代码（`reader3.py`，先于 007） | 最小修复：reader-a3 会话（~~分支待按 §9 分配~~ ⬛ 2026-09-30：已由无编号修复分支 PR #26 付清最小修复，合并 commit `d212202`，见状态列）；**新落盘协议不在最小修复内**，归 [012 §6 Q2](./012-storage-format.md) | 子进程重导入，在两次替换之间 `SIGKILL`；重启后该书要么完整旧版、要么完整新版，staging 清理不删掉唯一副本 | **部分结清**（PR #26，合并 commit `d212202`；`0d49403` ＋ `b8e0353`）：已**不再删掉唯一的旧副本**——`_clear_staging_dirs` 先分类全部残留，发现未落地的提交（staging 里有 `book.pkl` ＋ 顶层 `*.superseded`）即拒绝并打印手工恢复步骤；无法检查的残留一律拒绝；回滚没做完时保留 staging。**未结清的一半转 [012 §6 Q2](./012-storage-format.md)**：混版本身仍会出现且被读成 `valid`；回滚未能丢弃一个「此前不存在」的新产物时，书混版但无损失、下一次运行也不拒绝——要落盘 marker 才能识别。约束：这套拒绝依赖今天的 staging 命名（自名 `*.staging-*` 目录、`book.pkl`、`*.superseded`），012 的新协议要么沿用、要么显式退役 |
| 60 | **集合的读—改—写没有锁，并发更新会丢。** `collections_service` 的 `update_collection_books` / `delete_collection` 各自 load → 改 → save，无进程内锁、无 `flock`；两个请求交错，后写的覆盖先写的。018 WI-5 的删书第 3 步要在同一把全局集合锁下改集合 | 已上线代码（`collections_service.py`） | reader-a3 会话（~~分支待按 §9 分配~~ ⬛ 2026-09-30：已由无编号修复分支 PR #26 付清，合并 commit `d212202`，见状态列）；018 WI-5 依赖它 | 两个进程并发往同一集合加不同的书，两本都在；并发删集合与改集合不产生半写文件 | **已结清**（PR #26，合并 commit `d212202`；`bcc6501` ＋ `4d3c5ac`）：create / rename / delete / `update_collection_books` 整段读—改—写持每路径 `threading.Lock` ＋ `library_collections.json.lock` 的 `flock LOCK_EX`；原子写改 `mkstemp` ＋ `fsync` ＋ `os.replace` ＋ 目录 `fsync`；路由的 remove 过滤移进锁内。测试 `tests/unit/test_collections_concurrency.py`、`tests/contract/test_collections_books_route_race.py`。018 WI-5 第 3 步用的就是这把锁 |
| 61 | **`BookUuidResolver` 不查盘就返回缓存的 folder ↔ uuid。** `ai/books.py` 的解析器扫描一次后只读内存映射；手删书目录再重导入同一 EPUB（新 `book_uuid`）后，它仍给出旧 uuid，对话挂到错的身份上。018 WI-5 删书会主动失效它，但手删 / 外部改动路径仍需它自己校验 | 已上线代码（`ai/books.py`） | reader-a3 会话（~~分支待按 §9 分配~~ ⬛ 2026-09-30：已由无编号修复分支 PR #26 付清，合并 commit `d212202`，见状态列） | 解析 → 手删并重导入 → 再解析，得到新 uuid；不因每次解析全量扫盘 | **已结清**（PR #26，合并 commit `d212202`；`9b62afb` ＋ `476f84d`）：正向命中重读 `ai_meta.json` 校验，不符即丢弃陈旧映射、登记盘上的 uuid；目录不在 → `FileNotFoundError`；读不出 → 原样上抛、不铸新 uuid（ADR-0003）；反向命中与 scan 后的命中同样校验。测试 `tests/unit/test_book_uuid_resolver_staleness.py`、`tests/contract/test_book_uuid_staleness_routes.py`。解析器作用域若要改写 ADR-0003 的表述，另开 supersede，不在本行 |
| 62 | **PR #28 的回归用例 `tests/e2e/test_selection_toolbar_stays_closed.py` 落在白名单、不在 `baseline_1b/`。** 它护的是 K2 copy 的 soak 抖动（关掉的选区工具条被 epub.js 下一拍 `selected` 重开），内容上属 K-2 家族；当时为不改 `suite_hash` 把它挂进 `scripts/lint_e2e_groups.py` 的 `UNGROUPED_E2E_MODULES`，白名单注释里写明到期条件：「下一次本来就要动 `baseline_1b/` 的改动里一并迁入，同批撤条目并给 `EXPECTED_BASELINE_ITEMS` 加上去」。该条件此前只写在代码注释里，没有任何欠账表记它 | PR #28（`26bce1d`，合并 commit `865e7eb`，2026-09-28）；2026-09-30 规划文档审计 #23 补立账 | **冻结集欠账窗口**（018 之前，与 #49 / #50、017 审计 #10 同窗口；顺序见[看板「现在该做什么」](../../20260824-frontend-backend-plan-progress.md#现在该做什么)） | 模块迁入 `tests/e2e/baseline_1b/` 并带 `baseline_1b` marker；`scripts/lint_e2e_groups.py` 的白名单撤掉该条目，`EXPECTED_UNGROUPED_ITEMS` −8、`EXPECTED_BASELINE_ITEMS` ＋8（8 = 4 条关闭路径 × 2 个时机，以迁入时 `--collect-only` 实测为准），`tests/unit/test_e2e_group_guard.py` 的独立 oracle（`CANONICAL_*` 与白名单集合）同步；`uv run python scripts/lint_e2e_groups.py` rc=0 | ~~未结清（2026-09-30 立账）~~ ⬛ **已结清**（`019-frozen-set-debts`，`fa3ac17`，2026-09-30）：迁入 `tests/e2e/baseline_1b/` 并加 marker，白名单撤条目；`--collect-only` 实测 baseline 68 → **76**、白名单 72 → **64**、e2e 总数 265 不变（白名单的 72 含同窗口 #49 / #50 新加的 9 条，故迁前不是立账时写的 63）；`test_e2e_group_guard.py` 的 `CANONICAL_*` 与白名单集合同步，`.github/workflows/tests.yml` 的 baseline 计数同步；lint rc=0。改了冻结集，`suite_hash` 的结算见 [`soak-log.md`](./soak-log.md) 本日一节 |
| 63 | **首个 `relocated` 事件的 `displayed.total` 是在主题 CSS 与字体重排之前算的，首屏的章内总页数和百分比是陈旧值。** `src/reader3_app/web/static/js/epub-renderer.js` 的 `relocated` 处理器（`:316`）把这份快照交给 pill，`getDebugState()` 也读同一份缓存（`rendition.location`）；所以底部进度 pill 与 `progress.sectionPage.total` / `sectionPercent` 在下一次导航之前都报陈旧的总页数和百分比。实测：[020](../../20260928-debug-state-getter.md) WI-2 的 E2，视口 640×360、`repeat_data` 第 0 章，翻一页前后 `{page:1,total:3}` → `{page:2,total:4}`，2026-09-30 连跑 3/3 次一致。**成因是推断，未打点**：没有在首个 `relocated` 与样式注入、字体加载之间打时间戳核对 | 已上线代码（`epub-renderer.js`，先于 020）；020 WI-2（2026-09-30）实测发现，协调者裁定选项 A：E2 不再断言「total 不变」（`tests/e2e/test_debug_state.py` E2 的注释记了这一裁定）；2026-10-01 立账 | **014 WI-19**（进度口径重定义，见 [plan-frontend-ui-refactor.md](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md) WI-19） | 修复后 E2 能重新加上「翻页前后 `sectionPage.total` 不变」的断言并通过；或者首个 `relocated` 的 `total` 等于重排完成后的 `total` | 未结清（2026-10-01 立账） |
| 64 | **书锁被独占持有期间，阅读器把「笔记暂取不到」画成「这本书没有笔记」。** 018 WI-2 之后，import / delete（独占）在场时两条 notes GET 路由（章级 `/api/notes/{book_id}/{chapter_index}` 与书级 `/api/notes/{book_id}`）都在 2 秒预算内返回 409 ＋ `Retry-After`（reindex 为共享锁，不挡 GET）。前端不看状态码：`annotations.js` 的 `loadAndRender`（约 :526-531）在 `!resp.ok` 时照样 `render([])`，把页面上的划线全部清掉；`notes-panel.js` 的 `loadAndRender`（约 :84-104）显示空态「你可以在这里记录本书的想法、划线、书签」与「共0条笔记」。**数据是安全的**：`rememberNotesEtag` 跳过非 2xx，不会拿错版本去写；每一次写都是单条增 / 删 / 改，由服务端在锁内并入整份文件，客户端没有「整份覆盖」的路径。缺的只是显示——用户会以为标注丢了 | 018 WI-2 R5 核查（2026-09-30） | **014-ts-frontend-reader** | 两处 `loadAndRender` 在 `!resp.ok` 时保留上一次的渲染（可选再给一条可重试的 toast），不清空、不显示空态；各配一条 Vitest：GET 回 409 ＋ `Retry-After` 时既有划线 / 笔记列表原样保留 | 未结清（2026-09-30 立账） |
| 65 | **四条白名单的到期条件在 019 上触发了，但没有执行。** `scripts/lint_e2e_groups.py` 的 `UNGROUPED_E2E_MODULES` 里，`test_notes_write_failure_is_attributable.py`、`test_stored_cfi_must_agree_with_quote.py`、`test_conflict_resolution_single_flight.py`、`test_conflict_settled_text_keeps_its_base_etag.py` 这四条的注释写的到期条件都是「下一次本来就要动 `baseline_1b/` 的改动里一并迁入」。`019-frozen-set-debts` 就是这样一次改动，但四条既没迁入，也没另立推迟 | `019-frozen-set-debts`（`3522dfe`）；2026-09-30 分支审计（Codex #4）立账 | **012 开工核验前的冻结集准备**：在 master 上宣布第一个批次（即 012 开工前那一批）之前迁入，让同一个批次一并覆盖 | 四个模块迁入 `tests/e2e/baseline_1b/` 并带 marker；白名单撤掉这四条，`EXPECTED_UNGROUPED_ITEMS` / `EXPECTED_BASELINE_ITEMS` 按迁入时 `--collect-only` 的实测值调整；`tests/unit/test_e2e_group_guard.py` 的 oracle 同步；`uv run python scripts/lint_e2e_groups.py` rc=0 | ~~未结清（2026-09-30 立账，明确推迟）~~ ⬛ **已结清**（`023-frozen-set-prep`，`9d504bd`，2026-10-01；经 PR #34 合入 master `cc8ad27`，2026-10-02）：四个模块迁入 `tests/e2e/baseline_1b/`（git 记为 rename） 并带 `pytestmark = pytest.mark.baseline_1b`，白名单撤掉这四条；`--collect-only` 实测各 45 / 3 / 4 / 4 条，baseline 76 → **132**、白名单 68 → **12**、e2e 总数 270 不变（变基到 018 合并后的 `c08317b` 重数）；`test_e2e_group_guard.py` 的 `CANONICAL_*` 与白名单集合同步；lint rc=0（`baseline_1b 132/132`、`白名单 12/12`）。**`tests/e2e/notes_conflict_support.py` 有意一并迁入**：两个冲突用例从它导入，它在 `HASH_COVERED_PATHS` 之外就是冻结集的一个洞（改它不动 `suite_hash`、却能改变 baseline 行为），迁入后由 `baseline_1b/` 覆盖。`tests/unit/test_e2e_disk_poll_waits_for_response.py` 的守卫规则随之修订（`9d504bd`）：原「登记表永不伸进冻结的 baseline」改为「登记的 `baseline_1b` 站点须在当前 HEAD 原样过审」，并有一条合成的冻结路径坏样本钉住规则会咬人。`.github/workflows/tests.yml` 的 e2e 名称与注释改为不带条数。改了冻结集，`suite_hash` 的结算见 [`soak-log.md`](./soak-log.md) |
| 66 | **always-dump 的 fetch 台账丢掉了 reload 之前的请求。** `scripts/e2e_diag_dump.py` 只记录最后一个文档的 fetch 台账。跨导航的用例（例如 recolor 类）dump 出来只剩 reload 后的两条 GET，之前的 DELETE / POST 写请求都不在里面，拿它做延迟证据时就少了一段 | `019-frozen-set-debts`（#49 的诊断 dump）；2026-09-30 分支审计（Codex #2）立账 | 同 #65（012 开工核验前的冻结集准备） | 跨导航用例的 dump 里保留每个文档各自的 fetch 台账快照，reload 之前的写请求可以查到；用一个会 reload 的用例实跑一次，确认 dump 里有 DELETE / POST | ~~未结清（2026-09-30 立账）~~ ⬛ **已结清**（`023-frozen-set-prep`，`9d504bd`，2026-10-01；经 PR #34 合入 master `cc8ad27`，2026-10-02）。**先实跑复现**（`f621175`，`E2E_DIAG_ALWAYS=1`、`-k w5a0`，3 passed）：三个参数的 dump 里 `fetch` / `late_fetch` 都只有两条 GET，POST、POST、DELETE 全丢——立账的读码结论成立，成因是台账活在每个文档自己的 JS realm 里。**修法**：注入脚本把每个顶层文档的台账另镜像进 sessionStorage 的单键 `__r3_diag_fetch_ledger`（段数组 `{doc, url, entries}`，按 doc id 只替换自己那段，从不 `clear` / `key` / `length`，存储失败不改变 fetch 结果），dump 增 `fetch_docs` / `late_fetch_docs`，`fetch` 不变。**修后实跑**（`9d504bd`，同一命令）：每个参数 4 段，前三段依次带 POST 201、POST 201、DELETE 204，第 4 段两条 GET 与 `fetch` 一致。判据钉在 `tests/unit/test_e2e_diag_dump_fetch_ledger.py`（node + jsdom，N1 对旧脚本红）。真浏览器路径未进 lane；证据 = 上述 w5a0 前后两次实跑（`f621175` / `9d504bd`）；node 单测钉住持久化逻辑 |
| 67 | **冻结集里的两处 Low 级措辞问题。** 第一处，`tests/e2e/baseline_1b/test_write_recolor_and_delete.py` 的「证伪记录见 019 WI-3 EV-3」是悬空指针：EV-3 只存在于没进版本库的 `.claude/tdd-guardian` 矩阵里，应改为指向 [017 审计 #10 的兑付记录](./017-audit-followup.md)（commit `789602c`）。第二处，同一文件 w5a3 的「本条断四件事」已经过时，因为后来又加了两条 DOM 断言 | `019-frozen-set-debts`（`789602c`）；2026-09-30 分支审计（Opus #14 / #15）立账 | 同 #65（012 开工核验前的冻结集准备）：这两处在冻结集里，与 #65 同一次改动顺带修掉，不单独改 `suite_hash` | 指针指向版本库里真实存在的记录；断言计数与用例实际断言的数目一致 | ~~未结清（2026-09-30 立账）~~ ⬛ **已结清**（`023-frozen-set-prep`，`9d504bd`，2026-10-01；经 PR #34 合入 master `cc8ad27`，2026-10-02）：EV-3 指针改指 [017 审计 #10 的兑付记录](./017-audit-followup.md)（`789602c`）；w5a3「本条断四件事」改为「六件事」，补列第 5、6 件（重载后 `<mark>` 文字等于 `CH0_QUOTE`、其 id 集合恰为盘上 `survivor` 的 id）。只动 docstring：去掉 docstring 后的 AST 与 `f621175` 逐字相同 |
| 68 | **`wait_for_note_text` 在第 160 泵恰好落盘时误报超时。** `tests/e2e/helpers.py:837` 起：轮询循环结束后的最后一次重读只检查该条是否还在，不检查 `note_text` 是否已等于期望值，于是写入恰好落在最后一泵时，函数读到了新文本却仍抛「没有变成 …」。019 的 WI-6 用例只断言消息前缀，钉不住这一支。顺带一条 Low：`src/reader3_app/web/static/js/annotations.js:1659` 的 `create-empty-quote` 守卫改走 `reportNotesWriteFailure` 后，原 `console.error` 带的 `{ s, e, offsets }` 上下文丢了（019 只按裁定恢复了 `:1635` `create-no-offsets` 的 `detail`） | `019-frozen-set-debts` CP3 修复轮（`d31f53d`）读代码发现，未实跑复现；2026-10-01 协调者回写立账 | 同 #65（012 开工核验前的冻结集准备）：`helpers.py` 在冻结集里，与 #65 同一次改动修掉；Low 那条不在冻结集，可随任何碰 `annotations.js` 写路径的分支顺带 | 最后一次重读命中期望文本时返回该条而不是抛错，并有一条落在最后一泵的单元用例钉住；`create-empty-quote` 的 console 负载带回 `detail` | ⬛ **部分结清**（`023-frozen-set-prep`，`9d504bd`，2026-10-01；经 PR #34 合入 master `cc8ad27`，2026-10-02）。**High 半已结清**：`wait_for_note_text` 死线后重读若 `note_text` 已等于期望值即返回该条；`tests/unit/test_e2e_disk_poll_pumps_the_browser.py` 的判据按 helper 分阈值（`wait_for_notes` 159、`wait_for_note_text` 160），第 160 泵落盘返回、161 / 从不落盘仍抛原消息，旧形状与「重读无条件返回」两个变体都被杀（改前 5 红，改后 36 绿）。**Low 半仍未结清**：`annotations.js:1659` `create-empty-quote` 的 `detail` 未带回（不在冻结集，随碰该写路径的分支顺带）。**相邻的开放缺口（本条不修）**：~~`wait_for_notes` 的最后一次重读同样不检查条数~~（⬛ 2026-10-02 订正：`wait_for_notes` **根本没有**死线后重读——`tests/e2e/helpers.py:825-834` 循环一退出就拿循环内最后一次的 `seen` 抛错），写恰好落在第 160 泵时仍会误报超时（上述判据的 159 阈值就是在钉这个现状）；~~责任方待协调者指定~~ 已立账 [#69](#跨波欠账)，兑付方 014 |
| 69 | **`wait_for_notes` 在第 160 泵恰好落盘时误报超时，且超时消息贴的是前一泵的旧样子。** `tests/e2e/helpers.py:825-834`：循环里先读盘、再 `page.wait_for_timeout(50)`，死线在泵之后才判；循环一退出就拿循环内最后一次的 `seen` 抛错，**没有死线后重读**。于是写恰好落在最后一泵时，盘上已是 `count` 条，函数却报「没有稳定到 N 条，实际 M 条」，M 与贴出的条目都是那一泵之前的。与 #68 High 半同形，#68 只修了 `wait_for_note_text`，这一支是有意不修：`tests/unit/test_e2e_disk_poll_pumps_the_browser.py:179` 用 `LAST_OBSERVABLE_WRITE = {"wait_for_notes": 159, …}` 把现状钉成规格（:172-174 的注释说「死线后重读只用来写消息」，与代码不符——根本没有那次重读；#68 状态栏「最后一次重读同样不检查条数」同误）。真实墙钟下窗口约为 8s 预算末尾的一泵（≈50ms），只有本来就慢到 8s 的写才撞得上，Low；但误报方向是把「刚好赶上」报成「没写」，且消息与 `wait_for_note_text`「超时诊断读的是当下」的约定不一致 | `023-frozen-set-prep`（`9d504bd`，修 #68 时协调者裁定不修、当场钉住现状）；2026-10-02 欠账分诊立账 | **014**，与 #6（`cfi` 绊线翻转）/ #15（R-6a 改 testid）/ #24（X-2a 改 testid）同一次冻结集改动顺带付——一次 `suite_hash` 变更、一批重跑；`test_e2e_disk_poll_pumps_the_browser.py:172-174` 那段错误注释（023 原文）也由这次改动改掉。不归 012：012 §2.3 把冻结集改动列为不做，§5「冻结集诱惑」点名 `helpers.py`；也不为它单开窗口（改 `helpers.py` 必改 `suite_hash`，为一条 Low 重跑一批不值） | `wait_for_notes` 死线后重读一次：条数等于 `count` 即返回这次读到的列表，否则用**这次重读**的结果写超时消息；`test_e2e_disk_poll_pumps_the_browser.py` 的 `LAST_OBSERVABLE_WRITE["wait_for_notes"]` 改为 160、删掉 :172-174「故意不对称」的注释；第 160 泵落盘返回、161 / 从不落盘仍抛原消息前缀；`suite_hash` 的变更按 [`soak-log.md`](./soak-log.md) 结算 | 未结清（2026-10-02 立账） |
| 70 | **从已有 `mark` 重开工具栏后 Add Note 存不下来。** `src/reader3_app/web/static/js/annotations.js` `onAnnotationClick`（`:805` 附近）用 `range.selectNodeContents(mark)` 建选区并 `rememberRange`：起止容器是 `<mark>` 元素而不是其文本节点，经 `resolveOffsets` 换算后起止偏移相等（或只差一个字符），于是 Add Note → Save 要么被 `create-empty-quote` 守卫拦下（2026-10-03，2/2，诊断环 `requested:false`，POST 没发出），要么存成只引用首字符的 `type: note`（2026-10-01，2/2，两本书）。用户看到的是「没取到选中的文字，请重新选中再试」或一条引文只有一个字的笔记。账本 F-018 的 Confirm 已改成「Marker 后换一句再 Add Note」，不再要求这条路径；但从 mark 重开工具栏仍是产品提供的入口 | `025-verify-control` 实跑 F-018 Confirm 立账（2026-10-01 首见，2026-10-03 定位根因） | **014**（`annotations.js` 拆分时顺带：建区改用 mark 的首尾文本节点，或直接取 `mark` 上记的 `start_offset` / `end_offset`）——~~由维护者确认~~ ⬛ 2026-10-06 维护者确认归 014 | 点击已有 `mark` → Add Note → 填字 → Save 后，`notes.json` 多一条 `type: note` 且 `quote` 与该 mark 的 `quote` 逐字相同；诊断环没有 `create-empty-quote` | 未结清（2026-10-03 立账） |
| 71 | **排队中的 AI 请求在客户端断线后把该书 × provider 的队列卡死，之后同书同 provider 的提问与总结全部 504。** `src/reader3_app/ai/queue.py` `_PerKeyQueue.enter`（`:77-81`）只 `except Exception` 后 `_remove` 再抛；而 `_wait_turn`（`:123-124`）在排队期间查到 `request.is_disconnected()` 抛的是 `asyncio.CancelledError`（`BaseException`），接不住，条目留在 deque 里。它轮到队头时没有人 `exit`，后面每个请求都等到死线，`run()` / `acquire()`（`:154-156`、`:202-204`）一律 504 "AI request timed out"，直到服务器重启。活跃流上的 Stop 不受影响：`run()` 的 `finally` 总会 `q.exit(item)`。复现：`control.py` 用后台 `ai ask … --gate hold &` 占住队列，再在 UI 发问并在排队中点 Stop，随后该书任何提问都 504 | `025-verify-control` 实跑 F-013 Confirm 立账（2026-10-04 发现并复现一次，根因读代码定位；见 F-013 特性文件「Queue-wedge bug」与账本 2026-10-04 审计条） | **下一个 AI 相关分支**（⬛ 2026-10-06 维护者裁定；进入 §9 分配时把分支号填回本格）。改法：`enter` 的 `except Exception` 改为 `except BaseException`（或并列接 `asyncio.CancelledError`），`_remove` 后照旧再抛 | 排队中的请求断线后，同书同 provider 的下一次 `POST /api/ai/ask` 正常返回而不是 504；单元用例进 `tests/unit/test_ai_queue_budget.py` 同类：两个请求进同一队列，取消第二个的等待任务，`exit` 第一个后第三个 `enter` 立即 ready，deque 里没有死条目 | 未结清（2026-10-06 立账） |

#### 欠账 4 的根因订正（2026-09-03）

原记录把根因写成「本机 swap 11.1G/12G，chromium 在重度换页下加载不动」。**这是错的**，
连同当时那条看起来很有力的隔离证据一起错——「stash 掉全部改动、在 HEAD 上一样红」只证明了
**不是改动引起的**，它对「是内存引起的」一点支持都没有，我当时把这两件事混为一谈了。

实际根因：**chromium 够不到 `fonts.googleapis.com`**。两个模板的 `<head>` 里有阻塞渲染的
字体 `<link>`，该请求 30 秒超时 → 整页 `load` 事件永不到达 → 每条要开页面的用例各挂 30 秒
（16 × 30s ≈ 545s，与实测的 545.03s 吻合）。

排查中被证伪的两条，记下来是因为它们各自都长得很像根因：

* **内存**：chromium 冷启动实测 0.26s，`goto about:blank` 0.01s。浏览器毫无问题。
* **磁盘**：清出 44 GB（可用 25Gi → 69Gi）之后，故障**一模一样**。

最误导人的一步是用 `curl` 测那个域，得到「可达、0.7s」。**`curl` 走环境变量 `http_proxy`
（:7890），chromium 走系统代理（:10808），两条路不是同一条。**下次测「浏览器能不能连上某个
域」，必须用浏览器测：`page.goto(那个 URL)`，不要用 curl 代打。

⚠️ **取 `suite_hash` 前必须先 `git add`。** 那条命令读的是**索引**不是工作区，新用例文件在
`git add` 之前对 `git ls-files -s` 根本不存在。WI-4、Wave 0、WI-5 三次都先拿到过一个「没变」
的旧值。定义处在 `soak-log.md`，这里只是提醒。

### 时间形状

七波，其中四波是单条。乐观情况下的关键路径是
`Wave 0 → WI-5 → max(WI-6,7,8) → max(WI-9,11,12) → max(WI-13,14,15) → WI-10 → WI-16 → WI-17`，
即 **8 个串行段**，而不是 13 条 WI 逐条排队。并行省下的是中间三波的 6 条，**换来的代价是每波收口的
串行门禁**——这笔交易只有在每波真的能一次绿的前提下才划算，所以纪律 2 与 3 不是可选项。

---

## 1. 基础设施

| 项 | 要求 |
|---|---|
| ~~`webServer`~~ → `live_server` fixture | ⚠️ **本行的形式已被现状实测推翻**：`webServer` 是 `@playwright/test` 的配置键，本仓库用的是 `pytest-playwright`，没有这个键。**要求本身不变**——起自己的服务实例、端口由 `--port` 指定（**不得用 8123**，会撞开发者本地与 CI 并发）、就绪探针 `GET /api/health`——变的是承载它的东西：一个 pytest fixture，配方照搬 `scripts/smoke_installed_wheel.py` |
| **图书目录隔离** | `READER3_BOOKS_DIR` 指向 tmp 目录，测试前从 fixture 拷入。**任何用例都不得读写开发者真实的 `books/`**——本套用例会创建和删除标注。⚠️ `server.py` 在**模块导入时**把它读成模块级常量，因此必须在**服务进程启动前**置入环境变量，运行期改无效 |
| 选择器 | **只允许 `data-testid` 与 ARIA role/name**。禁止 class、`nth-child`、层级结构选择器。CI lint 强制（0.5 的产出）。✅ 2026-08-31：`lib-modal` 一族与 `rd-sheet-close` 的同模板重名已由 [ADR-0014](../../../adr/0014-bounded-testid-enumeration.md) 消除，命名 lint 现在会拦住重名复活，这条政策全面可满足 |
| iframe 语料 | 至少两本：一本英文短篇、一本 CJK。CJK 那本用来卡 quote/prefix/suffix 的多字节边界。**已有，不必新建**：`tests/fixtures/epub_corpus.py` 的 `build_epub2` / `build_epub3` 与 `build_cjk` |
| 并发 | 每个 worker **一个独立服务进程 + 一份独立 books 目录副本**（因为上面那条：目录是进程级常量，同一进程内无法按用例切换），`notes.json` 不共享 |

**iframe 内建选区的标准路径**（Selection 不能跨 browsing context，所以必须在 child frame 内做）：

```
child frame 内 document.createRange() → 写入 iframe 的 Selection
  → 在 iframe document 上派发 mouseup
  → 点外层工具条（testid 定位）
  → 断言往返
```

真实鼠标拖选只保留 **1 条 smoke**，其余走上面这条程序化路径——拖选在 CI 上是头号 flaky 源，而 flaky 会把 soak 门槛的计数清零。

这条路径上有两处**实测**得来的坑，实现在 `tests/e2e/helpers.py` 的 `select_in_frame`，写在这里是因为
每条写路径用例都压在它上面：

* **「断言往返」比的是 Range 语义，不是 `Selection.toString()`。** 生产端落库的 `quote` 来自
  `buildTextIndex(...).text.slice(s, e)`（`annotations.js:990`），而 `buildTextIndex` 是纯
  `text += node.nodeValue` 的 Text 节点拼接（:54-76）；复制/AI 那条路径取
  `currentRange.toString()`（:1038）。**两条生产路径都不经过 `Selection.toString()`。**
  后者走渲染文本序列化，**跨块级边界会插换行**：实测 `quote="neAlpha"`（横跨 `<h1>` 与 `<p>`）
  从 Selection 读回来是 `'ne\nAlpha'`。所以逐字判据落在 `range.toString()` 上，Selection 侧只用来
  证明「选区确实装进去了」。（矩阵 §WI-3 的第一定律原本把判据写成 `getSelection().toString() == quote`，
  与它自己的跨块参数值互斥，2026-09-02 已裁定改为本条。）
* **`onSelection` 的 120ms 去抖挡的是 mouseup，不是 selectionchange。** `lastSelectionAt` 在
  `handleRenditionSelection`（:722，epub.js 的 `selected` 回调）里赋值，不在 `onSelection` 里；
  于是紧跟在 epub.js 自己的 `selected` 之后到达的 mouseup 会被 :695 的守卫直接丢掉。
  更麻烦的是 `handleRenditionSelection` 自己会 `removeAllRanges(); addRange(range)`，**再次触发
  `selectionchange`**，形成约 250ms 周期的自持循环。可用的做法是：先 `removeAllRanges()` 停掉循环 →
  等到 `Date.now() - lastSelectionAt >= 120` → 在**同一个同步回合**里 `addRange` ＋ 派发 mouseup。
  ⚠️ 循环会在 `select_in_frame` 返回后约 250ms **重新起来**，届时 `currentRange` 被重置、
  `editingNoteId` 被置空——W-4 / W-7 这类「建好选区后还要再操作一步」的用例必须把后续动作压在这个窗口内，
  或在动作前重新建选区。

---

## 2. 读路径用例

| # | 用例 | 关键断言 |
|---|---|---|
| R-1 | 书库 → 打开书 → 阅读器渲染 | iframe 内有正文文本节点，非空白页 |
| R-2 | 章节导航（Prev / Next / TOC 点击） | 落到正确 spine index，URL 形状符合 K6 |
| R-3 | 既有标注恢复 | 预置 `notes.json` → 打开章节 → `<mark>` 出现在**预期的那段文字**上（比对 `textContent`，不是数量） |
| R-4 | 翻章后重绘 | 换章 → 新章高亮数量正确 **且** 旧章高亮不残留（K4 的可失败断言） |
| R-5 | 阅读页内搜索 | 命中高亮出现——**K5 的第二个消费方是 `search.js`**，这条用例是它唯一的护栏 |
| R-6a | **改主题/字号/行距后既有标注仍锚定同一段文字**（`baseline-1b`） | 设计规格 §6.0 判定标准的**断言 C**，只取其文本侧：预置标注 → 打开章节 → 逐项切换主题、字号、行距 → 每次 `<mark>` 覆盖的 `textContent` 不变 |
| R-6b | 同上的 **CFI 侧**（`acceptance-4b1`，skip 形态） | 每次切换后用 `window.ePub.CFI` 重解析存储的 CFI，`range.toString()` 等于存储的 `quote`。⚠️ 今天 `cfi` 恒为 `null`，该断言无对象——拆分理由见下 |

> **R-6 为什么必须存在**：设计规格 §6.0 从一开始就写着「Phase 1b 的 E2E 必须覆盖『改栏宽后既有标注仍能正确高亮』」，但本文此前**没有对应用例**——一条只写在设计文档里、没有落到用例表的门槛等于没有。
>
> **参数会随功能增长**：主题、字号、行距三项**今天就存在**（`reader.html` 的 Font Settings + `applyThemeSettings()`），所以 R-6a 属 `baseline-1b`。D5 的**正文栏宽**要到 4B.3 才有，届时它作为 R-6a 的**第四个参数**加入，而不是新开一组；**4B.3 的退出门槛需包含「R-6a 的栏宽参数已启用并绿灯」**。

> **R-6 为什么在 2026-09-03 拆成 a / b（Wave 4 派活前的裁定）**：本条与矩阵 §WI-14 都写于
> 09-01，那时 Input 还写着「预置一条标注**含 `cfi`**——本条与 W-8b/R-3/R-4 相反，它测的正是
> CFI 路径在重排后的稳定性」。**两天后 WI-7 把这个前提证伪了**：欠账 #6 实测 `cfi` 恒为
> `null`（`currentContents` 存的是 view 不是 `Contents`，`cfiFromRange` 永不存在），欠账 #8
> 据此认定 `AnnotationRenderer.render()` 的 CFI 分支是死代码。矩阵没人回头调和这两处。
>
> **技术上这条仍跑得起来**——`seed_notes` 能手写一个 CFI 进 `notes.json`，`ePub.CFI` 是独立
> 解析器、多半解得开。**问题是它跑起来在特征化什么**：一条生产永远不会产生的记录，走一条
> 生产永远不会执行的分支。按 §0.5 的定性，那不是安全网，是在写期望行为——**期望行为归
> `acceptance-4b1`**，和 W-5b 一个去处、一个理由。
>
> **拆法照 W-5 的成例**：文本侧（断言 b）留 `baseline-1b`，走今天真实生效的纯文本锚定路径，
> **这条才是护住迁移的那条**；CFI 侧（断言 a）以 skip 形态写进 `acceptance-4b1`，与欠账 #6
> 的修复同期解开。**条目数不变**：R-6a 仍是「主题 / 字号 / 行距」三个参数项、三条，WI-14 在
> 矩阵里的配额（3 条）不动；`acceptance-4b1` 由 5 条涨到 8 条，那笔账归 WI-17，见欠账 #14。

> **R-6a 的三个参数在生产里的真实抓手（2026-09-03 实测，覆盖矩阵 §WI-14 的记法）**：
>
> - **主题**四态有 testid：`rd-pref-theme-paper` / `-sepia` / `-green` / `-night`。先点
>   `rd-rail-font` 开面板。
> - **字号 ± 与间距 ± 没有 testid**，只有 `id` 与中文 `title`，只能靠 `get_by_role` 的可访问名。
>   矩阵写的名字**三个里错了三个**，以模板为准：字号是 `减小字号` / **`放大字号`**（不是「增大字号」），
>   间距是 `减小间距` / `增大间距`。
> - 容器 testid 是 `rd-pref-size` 与 **`rd-pref-leading`**，但后者在 UI 上的标签是**「段落间距」**
>   而非「行距」。用例命名与 docstring 用「间距」，别沿用矩阵的「行距」——名字对不上时，
>   下一个人会去找一个不存在的控件。
> - 这条脆弱性登记为欠账 #15：`get_by_role` 不经过选择器字符串，lint 不拦，**合规但脆**，
>   中文文案一改本条即断。

> **R-2 / R-4 可用的导航机制（2026-09-02 实测，覆盖此前的记法）**：
>
> - `rd-chapter-prev` / `rd-chapter-next` 虽然是 `<a href>`，但 `epub-renderer.js` 给它们绑了 `click` ＋ `preventDefault()` → `displaySectionIndex`，**今天是站内导航**，不是整页跳转。R-2 可以用。
> - **R-4 仍然不用它们**，理由变了：`href` 是兜底，事件链一旦坏掉浏览器会整页加载，用例**假绿**。R-4 走 TOC 行（`findAndGo`）或键盘 `ArrowDown`（`handleNavKey`）。
> - **`rd-page-prev` / `rd-page-next` 完全不可用**，任何机制清单里都不许出现：`.nav-zone-left/right` 的 CSS 是 `display: none`（注释写明 keyboard-only），且只有 legacy `js/pagination.js` 绑定它们，而 `reader.html` **不加载那个文件**。Playwright 点 `display:none` 元素会在 actionability 上超时。



---

## 3. 写路径用例（本文的重点）

> 组：**`baseline-1b`**。4B.1 的退出门槛写的是「`baseline-1b` **零改动**全绿」。**这条只有在写路径被覆盖时才成立**——`commands.ts` 那六个方法（`toggleMarkerAnnotation` / `toggleAnnotation` / `deleteCurrentAnnotation` / `saveNote` / `deleteAnnotations` / `createAnnotation`）恰恰是最容易漏的一层：读侧渲染肉眼可见，写侧只在刷新后才暴露。

**每条用例的收尾动作统一为：刷新页面 → 断言高亮/笔记回到同一段文字上。** 没有这一步的用例不算数。

| # | 用例 | 补充断言 |
|---|---|---|
| W-1 | 创建 **marker** | 刷新后 `<mark>` 覆盖的 `textContent` 与选中文本一致 |
| W-2 | 创建 **wavy** | 同上，且样式类型正确 |
| W-3 | 创建 **underline** | 同上 |
| W-4 | 创建 **note**（含笔记正文） | 刷新后 tooltip / Notes 面板能读回笔记文本 |
| W-5a | **色板换色后重按同一动作**（yellow → green），`baseline-1b` | 特征化今天的三岔行为：①点色板只调 `setSelectedColor`，已有标注**不动**；②随后重按 marker 走 `toggleMarkerAnnotation`，旧黄条**保留**、另加一条绿的，两条 id 各自独立；③重按 wavy / underline 走 `toggleAnnotation`，**删成功但建失败，选区上一条不剩**（订正见下）。三支各断一次，刷新后仍成立 |
| W-5b | **改色**（yellow → green），`acceptance-4b1`、**以 skip 形态写** | 刷新后颜色为 green，且**标注 id 不变**（改色不是删了重建）。⚠️ 该行为 4B.1 才实现，不计入 1b 门槛 |
| W-6 | **删除** | 刷新后该段文字上无 `<mark>`；`notes.json` 里对应条目消失；**其他标注不受影响** |
| W-7 | **笔记编辑保存**（打开已有笔记 → 改文本 → 保存） | 刷新后读回新文本；这条走 `note-editor` → `commands.saveNote` 的完整链 |
| W-8 | 重叠标注 | 在已有标注上再划一段重叠区域，两条都能刷新后恢复 |
| W-9 | CJK 书上重复一遍 W-1 与 W-7 | quote/prefix/suffix 的多字节边界 |
| W-10 | 同章重复文本消歧 | 章内出现两处相同文字，标注第二处，刷新后落在**第二处**（prefix/suffix 生效） |

**W-5 拆成 a / b 的理由**见 §0.5 的现状特征化小节；期望行为的落地定义在[前端计划](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md)的 WI-14。

**W-5a-③ 的记述订正（2026-09-03，WI-6 实测）。** 上表原写「先删后建，id 变了」，**这是错的，
今天的实际行为是删成功、建失败、选区上一条不剩**——一次静默的用户数据丢失。10/10 稳定复现，
不是竞态。链路：`toggleAnnotation` 的异色分支 `await deleteAnnotations(anyIds)`；
`deleteAnnotations` 在删完之后 `await renderer.loadAndRender()`；`render()` 调
`clearExistingAnnotationMarks()`，后者对拆过的文本节点调 `parent.normalize()`，把仍被
`this.currentRange` 引用的那几个节点合并掉，**选区就地塌成空**；执行流继续落到
`createAnnotation`，此时 `quote` 已是空串，服务端的 `quote is required` 返回 **400**。
净效果 `DELETE 204 → POST 400 → |S'| == 0`。

订正只改「今天是什么」，不改裁决：W-5a 仍特征化今天的行为并计入 1b 门槛，W-5b 仍承载期望行为。
**但连带成本比原记的大**——4B.1 兑付时要修的不只是「改色应保 id」，而是先修掉这条数据丢失；
见欠账表第 9 行。

**W-6 的反向断言不可省**：删除是唯一会破坏用户数据的操作，"删对了一条"和"顺手删掉了别的"在 UI 上看不出来。

**W-6 断言的是文件形状，注意 `notes.json` 是一个「对象」**：`notes_service.save_annotations` 写的是 `{"schema_version": …, "book_id": …, "annotations": [...]}`。任何「删完后仍是合法 JSON **数组**」的措辞按字面实现都会**稳定假红**——断的是顶层对象结构 ＋ `annotations` 列表的内容。

---

## 4. K1–K6 各一条能失败的断言

| 契约 | 用例 | 组 | 断言 |
|---|---|---|---|
| **K1** | K-1a | `baseline-1b` | 七个宿主元素齐备且标注 UI 正常 init（前置条件的正向证据） |
| **K1** | K-1b | `acceptance-4b1` | 用 `page.evaluate` 移除 `annotation-toolbar` 后重载标注 UI → 断言控制台出现明确 `console.error` 且降级标记置位。**不能只断言"工具条不见了"**——契约的价值在于把静默变响亮。⚠️ 该行为 4B.1 才实现，不计入 1b 门槛 |
| **K2** | K-2 | `baseline-1b` | 工具条每个 `data-action` 逐个点一遍，断言**结果**（标注真的产生/删除/改色），不是断言按钮存在。「改色」今天是什么语义见 §3 的 W-5a，这里不复述 |
| **K3** | K-3 | `baseline-1b` | ①三个浮层各跑 `containingBlockAncestor(el) === null`；②工具条矩形与选区矩形相对位置在容差内。判据与参考实现见契约文件。**落地（2026-09-04，`tests/e2e/baseline_1b/test_kernel_overlay_geometry.py`，6 条）**：K-3a×3 先断浮层自身 `position: fixed` 再断祖先链（矩阵 R1）；K-3b X 轴精确 `X_TOL = 2`、Y 轴 `Y_TOL = 20` 且运行期元断言 `Y_TOL < frame_box.y`（矩阵 R2）；K-3b′ 差分 `MIN_DELTA_X = 60 / MIN_DELTA_Y = 40`；K-3c `GAP_TOL = 6`。**两处实测订正**：(a) 三个浮层是 `<body>` 的直接子元素，祖先链 = `BODY → HTML`，`rd-shell` 是兄弟——生成计划里「给 `rd-shell` 加 `transform` 后本用例必红」的纸面配方对着真实 DOM 是 6/6 绿，破坏点必须是 `<body>`（实证 3 红）；(b) `smoke_data` 上 `Alpha prose` 的选区中心 x ≈ 130 落在 clamp 带内，几何三条改用 `repeat_data`。实测 `frame_box = {x: 0, y: 40, w: 1280, h: 640}` |
| **K4** | R-4 | `baseline-1b` | 见读路径 R-4（翻章后新章高亮正确、旧章不残留） |
| **K5** | R-5 + W-1 | `baseline-1b` | `search.js` 与 `annotations.js` 两个消费方各至少一条 |
| **K6** | K-6a | `baseline-1b` | 在 `/read/{bookId}/{chapterIndex}` 上创建标注，断言 `notes.json` 里的 `chapter_index` **等于 URL 里那个数** |
| **K6** | K-6b | `acceptance-4b1` | 删掉 `location.pathname` 回退后：`window.Reader3Ctx` 缺失时**抛错**而非静默猜测。⚠️ 该行为 4B.1 才实现，不计入 1b 门槛 |

---

## 5. DEG-S1–DEG-S4 降级状态各一条正向证据

> **组：`acceptance-p3`（朴素形态）→ `acceptance-4a4`（设计规格形态）。整节都不计入 Phase 1b 的退出门槛**，因为横幅本身要到 Phase 3 / 4A.4 才存在。用例在 1b 阶段就写好并挂 skip，到期解开。

每条都要**主动制造**降级条件，再断言 UI 明确显示——「没有横幅」不是证据。

| 状态 | 制造方式 | 断言 |
|---|---|---|
| **DEG-S1** 标注 stale | 改写 `notes.json` 里的 spine 指纹使其与当前书不匹配 | 阅读器顶部横幅出现，文案匹配；Notes 面板逐条标记 |
| **DEG-S2** 索引 stale | 使 chroma 指纹不匹配 | 书卡第五态 + 搜索面板顶部提示 |
| **DEG-S3** pickle 回退告警 | `READER3_ALLOW_PICKLE=1` 启动 | 书库与阅读器都出现全局告警条 |
| **DEG-S4** 存储格式/迁移进度 | 准备一本旧格式书 | 书卡上 `storage_format` 标记正确 |

> DEG-S1–DEG-S4 的**落地阶段**是 Phase 3（先以朴素横幅落到 Jinja 模板）与 Phase 4A.4（按设计规格重做）。本文的用例随之分两批写：Phase 3 出口时对朴素形态断言，4A.4 改版后只改 testid 映射、断言语义不变。
>
> **DEG-S5（notes 写冲突）不在 1b**——它依赖 Phase 2a 的乐观并发，届时随 2a 一起补。

---

## 6. 其他

| # | 用例 | 说明 |
|---|---|---|
| X-1 | AI SSE 流式 | 首 token 到达 + 流正常结束 + 中断可恢复。**落地（2026-09-04，`tests/e2e/baseline_1b/test_other_ai_streaming.py`，4 条 ＋ `tests/unit/test_ai_stub_contract.py` 3 条）**：桩是 **ollama 形状**的进程内 NDJSON 服务（`tests/fixtures/ai_stub.py`），因为 `server.py` 只有 `worker_ollama` 逐块推、其余 provider 整段一个 `chunk`；沙箱 `ai_settings.json` 由 function 级 fixture 写/删，`_server_env` 未动。X-1a′ 用 `threading.Event` 握手把「首块已渲染 happens-before 末块发出」变成可判定，三个超时常量 `5 < 15 < 30` 写成模块级断言。**两处实测订正**：(a) `rag.py` 的 `_keyword_fallback` 是**整句子串匹配**而非分词命中——矩阵给的提问 `"Alpha 这一章讲了什么？"` 对未建索引的书返回 400 普通 JSON（在任何 SSE 帧之前），提问必须是正文逐字子串（`"Alpha prose"`）；(b) `done` 后 `renderAll()` 在同一消息节点里追加 `div.ai-citations`，快照不能读 `lastElementChild.innerText`，改读该节点自己的文本节点，引用页脚在 X-1b 单独断 |
| X-2 | 书库导航与集合切换 | 4A.4 切页时的护栏 |

---

## 7. 不在 1b 范围

- 迁移相关的 iframe 标注 E2E —— 属 **Phase 3 出口**（真实 `--migrate` 前后标注不漂移），在 `specs/012-storage-format/` 里
- DEG-S5 写冲突 UI —— 随 Phase 2a
- 视觉回归 / 截图对比 —— 本套只测行为
- 性能基准 —— 属 Phase 1a

---

## 8. 退出门槛

> ⚠️ **2026-08-24：本节拆成两道门。** 起因是 Codex 复核指出「009 阻塞 Phase 3」其实是**两件不同的事**
> 被记在了一行里：**用例写完了没有**，和**基线稳不稳**。两者的完成时间可以差很远，把它们混记会产生一个
> 具体的误判——用例刚写完就以为可以开始数 soak，而此时 `suite_hash` 还在天天变，按 §7 的清零规则那些
> 绿一次都不算数。**分开记之后，「soak 从哪天开始数」有了确定答案：G2 达成那天。**
>
> 下游也随之分开：**Phase 4A 要的是 G1**（有一套能跑的 E2E 就够了），~~**Phase 3 要的是 G2 之后再连绿十次**~~（⬛ 2026-09-28 起为批次规则，见[迁移计划 §7](../plan-tech-stack-migration.md#7-阶段门槛表)）。

### G1 —— 用例完成门

- **`baseline-1b` 组**在**本地 `e2e` lane**（`gateOn: push`）绿灯，并往 `soak-log.md` 记账（原写「主 CI（非 nightly）」，随 CI 改为仅发版触发而改基——见迁移计划 §7）
- 选择器 lint 通过：全套用例（含尚未激活的组）零 class / 结构选择器
- 其余各组**用例已写完并通过 review**，以 skip 形态存在——写完是 1b 的门槛，跑绿不是

**G1 达成即解锁 Phase 4A。** 它不解锁 soak 计数。

> **2026-09-04 澄清「并往 `soak-log.md` 记账」这一句，因为它和台账自己的表头相互矛盾。** 台账写着
> 「soak 计数从 **G2 达成之日**开始，首行落账之前本文件不构成对 G2 的任何宣称」；G1 这条却要求写一行。
> 照字面同时满足两者是不可能的。**裁定取「不落账」**：G1 要的是**演示得出一次可记账的绿**——
> `soak_run.py` 不带 `--append` 跑完打印出 `verdict: green（可记账：是）` 与那一行台账文本，产物落在
> 运行日志里。真往台账写第一行的动作留给 G2 那天，因为写下去就等于启动了 §7 的清零时钟，而
> `suite_hash` 此刻仍是 pre-freeze。**这句话的原意是「证明 runner 与判据都通了」，不是「开始计数」。**

### G2 —— 基线稳定门

- **零 flaky**：`baseline-1b` 连续 3 次全量运行无偶发失败才算达标。理由见 soak 门槛——一条会偶发失败的 E2E 当不了 Phase 3 数据迁移的验收基准，~~而 flaky 会让计数反复清零~~（⬛ 2026-09-28 起为批次规则，见[迁移计划 §7](../plan-tech-stack-migration.md#7-阶段门槛表)）
- **「绿」的判据（2026-09-02 补，缺这条则整道门可被零成本绕过；2026-09-04 订正 `deselected` 一项）**：一次运行记为绿，**当且仅当** `passed == EXPECTED_BASELINE_ITEMS` 且 `skipped == failed == errors == 0` 且 `deselected == EXPECTED_ACCEPTANCE_ITEMS + EXPECTED_UNGROUPED_ITEMS`。
  - **订正的原文是「`deselected == 0`」，它在 Wave 7 之后是一条无法满足的判据。** soak 发的是 `-m baseline_1b`，验收目录与白名单模块**必然**被筛掉；写这条时 `tests/e2e` 整棵树都是 baseline，deselect 数恰好为 0，于是把一个巧合写成了规格。Wave 7 落地 24 条非 baseline item 之后，`soak_run.py` 真跑一次得到 `65 passed, 24 deselected` → 判红且不可记账——**这道门变成了永远开不出绿灯的门，而失败形态是「台账永远为空」，恰好和「还没开始数」长得一模一样。**
  - 订正后本意不变，反而更强：合法值不是「随便多少」，是**恰好等于那些本就不该被选中的条**。多筛一条（有 baseline 用例被漏跑）与少筛一条（有验收用例漏挂分组标记）**都判红**，两个方向各有一条用例钉住。派生自 `lint_e2e_groups.py` 的两个常量，不写字面量 24。
  - 为什么必须写死分母：「无偶发失败」只约束**失败数**，「全量运行」只约束**调用形态**，两者都不约束**实际执行了几条**。一个挂了 `@pytest.mark.skip` 的模块照样算「全量运行、0 failed」——于是给一条不稳的 baseline 用例挂 skip，就成了让 G2 变绿的**零成本、且在台账上无痕**的手段（`result` 列只有 pass/fail）。
  - `soak-log.md` 的 `result` 列**由 `scripts/soak_run.py` 按上述条件判定，人工不得改写**（这是对表头的说明，不增列；八列字段的定义仍在迁移计划 §7）。
- **commit 级护栏（与上一条是两个触发频率）**：soak runner 只在 G2 跑三次，而「往 `conftest.py` 的 fixture 里加一句 `except Exception: pytest.skip(...)`」这类改动**每次 push 都在生效**。因此追加一条常设约束：**`baseline_1b` 的收集可达链（`tests/e2e/conftest.py`、`tests/e2e/helpers.py`、`tests/e2e/baseline_1b/**`）内不得出现任何 skip 构造，函数体与异常处理器里的一并计入。** 这条今天在代码里成立；写进本节是为了让它被破坏时是一次**有意的违约**，而不是一次顺手的防御性提交。
- 单次全量运行时长记录在案（后续 soak 期间要跑十次以上，时长本身就是可行性约束；⬛ 2026-09-28 起按批次跑，见迁移计划 §7）
- **`soak-log.md` 已建，八列字段齐全**（字段定义在迁移计划 §7 的「台账字段（canonical）」，本文不重述），表头写明 `suite_hash` 的取法命令与当前值，**以及 §7 记在取法命令旁的那条代价**——`tests/fixtures/epub_corpus.py` 在覆盖范围内，因此一次纯单测目的的构造器改动也会~~清零 soak 计数~~（⬛ 2026-09-28 起为批次规则，见[迁移计划 §7](../plan-tech-stack-migration.md#7-阶段门槛表)）
- **`suite_hash` 进入冻结状态**——从这一刻起再改 `baseline-1b` 的用例或 harness，~~soak 计数从零重来~~（⬛ 2026-09-28 起为批次规则，见[迁移计划 §7](../plan-tech-stack-migration.md#7-阶段门槛表)）。所以 G2 的真实含义是「**你愿意为这套用例的当前形态背书**」，不是「它今天碰巧绿了」

**G2 达成之日 = soak 计数第 1 行的日期。** ~~Phase 3 从这里开始数 ≥10 次 / ≥5 个工作日。~~（⬛ 2026-09-29：已被迁移计划 §7 批次规则取代，Phase 3 要的是一批 10 次，见 §7。）

> **✅ 2026-09-06 达成。** 逐条判据的实测值记在
> [`soak-log.md`](./soak-log.md) 的「G2 达成记录」一节——**那里是唯一定义处**，本节不重述数字。
> 三次全量运行 `result` 全绿、`suite_hash` / `browser` / `os` 三次一致，~~`suite_hash` 冻结在
> `2747100dadf6`~~。（⬛ 2026-09-30：那是 2026-09-06 的冻结值，2026-09-21 起作废——见下方 ⬛ 2026-09-21 一段；现行值只在 [`soak-log.md`](./soak-log.md) 表头定义，此处不复述。）
>
> **门开了，但下游只解锁了「开始数」这一件事。** Phase 3 要的是 ~~≥10 次 **且** ≥5 个工作日~~（⬛ 2026-09-28 起为批次规则，见下方 ⬛ 2026-09-29 注），
> 今天只有 3 次、跨度 0（三行同落在一个周日）。**跨度是唯一补不回来的那一半**：连跑十次
> 也换不来第五个工作日。当前进度以 `soak-log.md` 表头为准，不要在别处复述。
> （⬛ 2026-09-29：已被迁移计划 §7 批次规则取代——跨度取消、旧行不计入任何批次；本段是 2026-09-06 的历史。）
>
> **「commit 级护栏」这条从今天起是常设约束，不是一次性检查**：`tests/e2e/conftest.py`、
> `tests/e2e/helpers.py`、`baseline_1b/**` 里不得出现任何 skip 构造。它每次 push 都在生效，
> 而 soak runner 只在跑的时候看一眼——两个触发频率，别把后者当成前者的替代。
>
> **⬛ 2026-09-21：计数清零一次，`suite_hash` 重新冻结在 `1e868c7bf811`。** G2 **没有**因此
> 作废——G2 是「你愿意为这套用例的当前形态背书」这个动作，它在 2026-09-06 做过了，
> 现在只是对一套新形态重新背书一次。作废的是它下游的两样东西：攒到 10 行的 soak 绿账，
> 以及机制挑战闸三项（含已 PASS 的 CPU 压力项，按[迁移计划 §7 纪律 4](../plan-tech-stack-migration.md)）。
> 改的是覆盖面里的两个文件：W-5a-③ 因 [欠账 #9](#跨波欠账) 修好而**改判**（期望终态
> 0 → 1，挂了 18 天的明账偏差被注销），以及 #44 的回归用例从白名单**迁入** `baseline_1b/`。
> `EXPECTED_BASELINE_ITEMS` 67 → **68**。理由、账单与「为什么不选保住计数的那条路」
> 记在 [`soak-log.md`](./soak-log.md) 变更史第一条，**那里是唯一定义处**。

### 其余各组的门槛归属

| 组 | 归属阶段的退出门槛 |
|---|---|
| `acceptance-4b1` | 4B.1 退出门槛（见[前端计划](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md)） |
| `acceptance-p3` | Phase 3 出口 |
| `acceptance-4a4` | 4A.4 出口 |
| `acceptance-2a` | Phase 2a 出口 |

**一个不成组的例外**：R-6 属 `baseline-1b`，但它的**栏宽参数**要到 4B.3 才有对象可测。这是往既有用例上加参数，不是新开一组，因此不进上表；它的门槛写在[前端计划](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md)的 4B.3 工作项退出门槛里。

> **不要把未激活组的 skip 当成永久豁免。** 每个阶段的出口 checklist 里都要有一行「本阶段应激活的组已解开 skip 且绿灯」，否则 skip 会一路带到 Phase 5。

## 原定从 008 转交的两条，已在 008 内结清（2026-08-26 收回）

这两条一度判为「在 008 修是修错地方」并转交 009。当天晚些时候两条都在 008 拿到了
**不依赖时序、也不依赖 012 fixture** 的做法，于是收回：`.cc-suite/audits/audit-008-tests-findings.md`
里 tests/19 与 tests/23 的状态已从 `transferred → 009` 改为 `fixed (WI-14)`。

**009 不再欠这两条。** 下面留的是「008 钉住了什么」与「009 仍可加什么」的边界，
避免 009 重复做一遍，也避免以为已经全覆盖了。

### 原 tests/19：SSE 增量性

008 已钉住：`test_流式提问是边生成边推送而不是攒够一次性吐`（`tests/contract/test_scenarios.py`）。
用握手代替掐表——假 provider 交出第 i 行的前提是第 i-1 个 chunk 已经发出去，所以「攒够
一次性吐」的实现必然红，而判定里没有任何墙上时钟。它手搓 ASGI scope 直接驱动 app：
starlette 的 `_TestClientTransport.handle_request` 以 `raw_kwargs = {"stream": io.BytesIO()}`
起手，整段响应体落完才把 `httpx.Response` 交出来，所以 `client.stream()` + `iter_text()`
看到的先后是 TestClient 的，不是应用的。变异证据：把 chunk 攒到 `done` 再冲，新用例红，
原 `test_流式提问按meta_chunk_done的顺序推事件` 全绿。

009 仍可加（可选，非欠账）：**首字延迟**是浏览器侧的用户可感属性，008 那条证明的是
「服务端是增量发的」，不是「前端是增量渲染的」。要覆盖后者，就在 Playwright 里断言
DOM 增量更新次数 > 1。

### 原 tests/23：受损书目录的降级

008 已钉住：`tests/contract/test_degraded_bookdir_and_images.py` 覆盖缺 `book.epub` 的
书目录——library 页仍渲染，取 epub 得 404 而不是 500（MUTANT-M 精确 1 红）；顺带覆盖
「点名一个目录当图片」得 404 而不是 500。

009 仍可加（可选，非欠账）：`book.pkl` **损坏**（而非缺失）这一态没覆盖，它要等 012 的
ADR-0007 三态读定下来；届时在 E2E 里补 reader 页的降级表现。
