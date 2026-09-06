# 009-e2e-annotations —— 任务

- **状态**: **✅ 已合入 `master`（2026-09-05，PR #20），G1 达成、Phase 4A 解锁。**见下面的「合入记录」。**G2 仍未起跑**——那是另一道门，见 §8。
- **对应阶段**: Phase 1b（Playwright E2E）起写，后续阶段逐组激活
- **进入条件**: Phase 0 的 0.3（`--port` + `/api/health`）与 0.5（`data-testid` 全量补齐）完成。见 `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md` §6
- **退出条件**: **两道门，分开记，见 §8**——**G1 用例完成门**（`baseline-1b` 写完并绿、其余组以 skip 形态写完并 review）与 **G2 基线稳定门**（零 flaky ＋ 台账开张 ＋ `suite_hash` 冻结）。**不再要求「主 CI 绿灯」**——CI 已统一为仅发版触发，改基说明见迁移计划 §7 的 soak 小节。其余组各自在所属阶段的出口生效，见 §0.5
- **下游**: Phase 4A 的进入条件是 **G1**；**Phase 3 的 soak 计数从 G2 达成之日起才开始数**（次数、跨度、台账字段、清零规则的唯一定义处是迁移计划 §7 的 soak 小节，本文件不复述）。**本分支还要建 `soak-log.md` 台账**——改基之后 soak 数的是它，没有它就没法计数
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
> **合入不等于 G2。** `suite_hash` 仍是 pre-freeze，`soak-log.md` 零数据行。起跑 G2 的顺序被
> §8 与欠账 #22 定死：**先修 #22，再冻结起跑**（#22 已于 2026-09-06 在分支 `016` 结清，
> 这条顺序至此兑付完毕）——R-6a 的两步刺激在「字号/间距慢一拍」修好后
> 会转红，必须改 `baseline_1b` 里的文件，哈希还要再变一次。
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
| 5 | 生产模板仍硬依赖 Google Fonts CDN：`reader.html` 与 `library.html` 的 `<head>` 各有一组指向 `fonts.googleapis.com` / `fonts.gstatic.com` 的阻塞式 `<link>`。对一个**本地自托管的离线阅读器**来说，断网或够不到该域时首屏字体直接降级。e2e 已由 `context` 网关掐掉，**生产未修**——已知代价、显式推迟，不是遗漏 | 2026-09-03 | **待定**（需先决定自托管字体 vs 接受降级） | `tests/unit/test_frontend_external_hosts.py` 的 `EXPECTED_EXTERNAL_HOSTS` 变成空集且仍绿（该用例两个方向都红：新增未登记的域红，白名单留下已无人使用的域也红——所以兑付时删模板必须同步删登记） | 未结清 |
| 6 | **`cfi` 永远是 `null`，全部锚定实际走纯文本路径。** `epub-renderer.js` 在 `rendition.on("rendered", (section, contents) => …)` 里把第二个实参当 `Contents` 存进 `currentContents`，但 epub.js 传的是 **view**。`IframeView` 有 `.document`，所以样式注入、点击、翻页全都照常工作，缺陷被完全掩盖——唯独没有 `cfiFromRange`，于是 `annotations.js` 里 `typeof contents.cfiFromRange === "function"` 这个卫语句**永假**，`cfi` 恒为 `null`。**这是生产缺陷，不是测试问题**，需单开工作项 | WI-7（2026-09-03 发现） | **待定**（前端计划，需自己的工作项） | 经 UI 创建的标注 `cfi != None`；WI-7 模块里那条 `cfi is None` 的绊线用例转为断反面 | 未结清 |
| 7 | 矩阵 §WI-7 的 Gap 7「经 UI 创建的标注一律带 CFI」**已被证伪**（见第 6 行）。三处提法需订正：矩阵该条、以及任何以「有 CFI 兜底」为前提的锚定论述 | WI-7 | **兑付第 6 行的同一个工作项** | 全仓 grep 不到「一律带 CFI」这类未加限定的提法 | 未结清 |
| 8 | `AnnotationRenderer.render()` 的 CFI 分支**零覆盖**——因第 6 行它今天是死代码。补它需要第 5 条用例，会让 `EXPECTED_BASELINE_ITEMS = 61` 变动，因此不能在 Wave 2 里就地补 | WI-7 | ~~WI-17（Wave 7）~~ → **改派 011 / 014，与欠账 #6 同一次兑付** | 该分支有用例覆盖，且常量与实测条数同步更新 | **未结清（2026-09-04 改派）**：WI-17 付不了它。前置条件写明「必须排在第 6 行修完之后」，而欠账 #6（`cfi` 恒为 null）是生产缺陷，009 全程 `src/` 一行未动（§0.5：1b 是安全网，不是行为变更窗口）。**在 cfi 真的写得进去之前，为死代码补的用例只会锁死死代码的形状。** R-6b 的 3 条 skip 用例已在 `acceptance_4b1` 就位，等的就是这次兑付 |
| 9 | **改色 wavy / underline 会静默丢数据**（删成功、建失败、剩 0 条），根因与复现见 §3 W-5a 下方的订正段。W-5a-③ 今天把这个行为特征化下来了，**但没修** | WI-6（2026-09-03 发现） | **4B.1 / 前端 WI-14**，且应排在 W-5b 解 skip 之前 | 改色后选区上仍有且只有 1 条标注；W-5a-③ 转红即为正确的红，改法是删掉该用例而非改断言 | 未结清 |
| 10 | `live_server` 的 `stdout=subprocess.PIPE` 从不在运行期 drain。管道满 64 KiB 后 uvicorn 卡死在 `write()`，此后每条 `page.goto` 都 30 秒超时。**建账起就潜伏，Wave 2 把套件涨到 35 条才引爆**（实测一轮写 74194 字节） | WI-1（建账时引入） | 2026-09-03 同日结清 | `uv run pytest tests/e2e --browser chromium` 全绿 | **已结清**（改为日志落文件；35 passed / 19.01s，修前 6 failed / 187.12s） |
| 11 | **`rd-page-prev` / `rd-page-next` 是死表面**：`reader.html` 的基础样式里就是 `.nav-zone-left, .nav-zone-right { display: none; }`（注释写着 keyboard-only navigation），且全仓 live 的 `js/*.js` 无任何绑定——唯一绑定在 `reader.html` **不加载**的 legacy `js/pagination.js` 里。有 testid 却点不动，点它只会等到 actionability 超时。**这不是测试问题**：一个带 testid、带 `title`、占 120px 宽度变量的元素永久不可达，要么补上绑定，要么连同 testid 一起删 | WI-9 / WI-12（2026-09-03 各自独立撞上） | **待定**（前端计划；`rd-page-*` 的去留是产品决定，不是测试决定） | 要么它可点且翻页，要么模板里不再有这两个 testid（届时 `lint_testid_naming.py` 的计数会变） | 未结清 |
| 12 | **站内导航时 URL 落后于渲染**：`syncLocationToUrl()` 跑在 epub.js 的 `rendered` 回调里，所以点完 `rd-chapter-next` 或 TOC 行的那一刻，地址栏仍是旧章号。**任何先断 URL 的用例都在读陈旧状态**。WI-12 的定向破坏 D4′ 实测：把 URL 期望改成隔壁章号，两个站内分支照样绿；调换成「先断正文、再断 URL」后同一发子弹三条全红 | WI-12（2026-09-03 发现） | **无需修**——这是契约不是缺陷，欠的是**把它写进 helpers 的等待原语**，见第 13 行 | 全仓不存在「点击后立即同步读 `page.url`」的写法 | 记录在案 |
| 13 | **三个本波产出的 helper 该上收到 `helpers.py`**：`_pathname_is`（等解析后的 pathname 而非 URL glob——TOC 行是 `<a href="#">`，导航后 URL 带尾随 `#`，`wait_for_url` 的 glob 永不匹配、白烧 30s，WI-9 为此花了一轮 spike）；`_reader_frame`（`open_reader` 去掉 `goto` 的那一半，凡「点进来」或站内导航的用例都要，重新 `goto` 会把被测的导航冲掉）；`_scan_annotations` / `_mark_id_union`（与 `test_write_overlap_and_disambiguation.py` 的 `_scan_marks` **已经重复**，两处都刻意在 evaluate 里读 `dataset.annotationIds` 以绕开选择器 lint 的误报——这个取舍该编码一次，不该每模块重新发现一遍） | Wave 3 | **下一个被授权改 `helpers.py` 的 WI**（§0.6 纪律 2：一波至多一个） | `grep -c "def _scan_marks\|def _scan_annotations" tests/e2e/baseline_1b/*.py` == 0 | **已结清**（Wave 3.5：`reader_frame` / `pathname_is` / `scan_marks` / `mark_id_union` 已上收，验收 grep 为 0） |
| 14 | **R-6 拆 a/b 之后 `acceptance-4b1` 由 5 条变 8 条**，`EXPECTED_ACCEPTANCE_ITEMS` 因此从 14 变 17。**本波不改常量**——理由同第 2 行，逐 WI 递增会把 `lint_e2e_groups.py` 变成串行写点。R-6a 在 `baseline-1b` 里仍是三条，`EXPECTED_BASELINE_ITEMS = 61` 不受影响 | Wave 4 前的 R-6 裁定（2026-09-03） | **WI-17（Wave 7）**，与第 2 行同一次落地 | `EXPECTED_ACCEPTANCE_ITEMS == 17` 且四个 acceptance 目录实测合计等于它 | **已结清（2026-09-04）**：`EXPECTED_ACCEPTANCE_ITEMS = sum(EXPECTED_ACCEPTANCE_PER_DIR.values())` **派生**而非字面量，逐目录 8/4/4/1 各自单独校验、实测合计 17 |
| 15 | **字号 ± 与段落间距 ± 四个按钮没有 testid**，R-6a 只能靠 ARIA 可访问名定位。**可访问名不是中文 `title`，是按钮的文本内容 `−`（U+2212）与 `+`**——accname 计算里 contents（2F）先于 title（2I）。本行原先写作「靠中文 `title` 的可访问名（`减小字号` / `放大字号`）」，那是错的，2026-09-04 由 WI-14 实测订正：`name="减小字号"` 匹配 **0** 个、`name="−"` 匹配 **1** 个，两个容器里都是这样。订正后真正的脆点有两条，且都跟原先写的不是一回事：**(a)** 中文文案怎么改都不会断，改**字形**（`−` 换成 ASCII `-` 或 `–`）当场断，且断时报的仍是「找不到元素」而不是「字形改了」；**(b)** 四个按钮的可访问名两两重名（两个 `−`、两个 `+`），所以**必须**用 `rd-pref-size` / `rd-pref-leading` 限定作用域——不限定就解析到 2 个节点、触发 strict mode 违规。这是**正确性要求**，不是写法讲究。 | Wave 4 派活前的实测（2026-09-03）；名字来源于 2026-09-04 订正 | **4A**（给四个按钮补 testid，与 ADR-0014 的命名规则一致） | R-6a 改用 `get_by_test_id`，全仓不再有按 `−` / `+` 字形定位的用例 | 未结清 |
| 16 | **一次页面加载会跑两遍 `loadAndRender()`**：`annotations.js` 在 `onContentsReady` 里当场调一次，同时又监听 `reader3:content:rendered`（由 `epub-renderer.js` 必发）触发一个 80ms 去抖的第二次。第二遍先 `clearExistingAnnotationMarks()` → `parent.normalize()`，再重建**数量完全相同**的 `<mark>`，所以「等 `<mark>` 数量到位」这个判据在结构上看不见它。夹在两遍之间装上的 live range 会被 `normalize()` 就地折叠成空 range，`getExistingAnnotationIds` 于是一条都匹配不到。**这是本模块约四成 flaky 的唯一根因**，一次解释了 `test_w5a0` / `test_w5a2` / `test_w5a3` 四个 ID 的三种不同表象 | Wave 3.5 收口时诊断出（2026-09-03） | **无需修**——加载期这是有界瞬态（80ms ＋ 一次 fetch），真实用户选不进这个窗口；欠的是**把它写进等待判据**，已由 `_open_ch0` 的 `wait_for_load_state("networkidle")` 兑付 | `tests/e2e` 连续 9 轮全绿（含 2 轮 CPU 打满），模块单跑 8/8 绿 | **记录在案**（测试侧已挡住） |
| 17 | **同一双重重绘模式也出现在写入路径，那一侧疑似能伤到真人。** `createAnnotation` / `deleteAnnotations` 各自都已经 `await loadAndRender()`，紧接着 dispatch `reader3:annotations:updated`，而该事件同样被 `scheduleRefresh` 监听 ⇒ 80ms 后再跑一遍多余的 `loadAndRender()`。加载期那一遍只是测试隐患，写入期这一遍意味着**用户在 ~150ms 内连按两个工具栏按钮，第二次操作的 live range 可能被第一次的尾随重绘折叠**——即欠账 #9 那条数据丢失路径的一个真实世界变体。**未验证**，Wave 3.5 只是读代码时注意到，没有去复现 | Wave 3.5 收口时注意到（2026-09-03） | **待定**（前端计划；与欠账 #9 同一批人，建议同一个工作项一起看） | 连按两次工具栏按钮后标注数量与颜色都符合预期，且网络日志里没有 `quote: ""` 的 400 | 未结清 |
| 18 | **`collections_service._NAME_RE` 把连字符判成范围端点**：模式写作 `r"^[A-Za-z0-9 _\\-\\.&()]+$"`，raw string 里每个 `\\` 是一个**字面反斜杠**，于是 `\\-\\` 被解析成「从 `\\` 到 `\\`」的**字符范围**，连字符当场失去字面身份。后果两个方向都错：`"sci-fi"` 这类再普通不过的集合名**建不出来**（用户可见），而 `"a\\b"` 反倒放行。实测复现：`_NAME_RE.match("a-b")` 为假、`_NAME_RE.match("a\\b")` 为真 | WI-15（2026-09-04 发现，主控独立复验） | **011 后端重构**（`collections_service` 归后端） | 连字符名可建、反斜杠名被拒，且有单测把两个方向都钉住 | 未结清 |
| 19 | **K4 的 `reader3:chapter:change` 这根线今天可以单独剪断，而全套件没有一条会红。**`scheduleRefresh` 被冗余接在**三个**事件上（`reader3:content:rendered` / `reader3:chapter:change` / `reader3:annotations:updated`），外加一路独立的 `Reader3Epub.onContentsReady` 回调；剪掉任意一根，换章重绘照常发生。**这同时证伪了覆盖矩阵 §WI-13 写下的自检预言**（原文预测「注释掉该监听 ⇒ 翻章后没有任何 `<mark>` ⇒ 红」）——WI-13 用带计数器的 `page.route` 确认改写确实生效、目标串确实被替换，模块仍 `3 passed`。所以 R-4 护住的是「换章会重绘」这个**可观测行为**，不是 K4 点名的那根线。谁要靠 009 挡住 K4 回归，得另外写一条直接断事件派发的用例 | WI-13（2026-09-04 实测证伪） | **WI-17（Wave 7）** 或 K4 的兑付方，需先决定「护行为」是否已经够（可能够，那就把矩阵的预言删掉而不是加用例） | 要么有一条用例在该监听被剪断时转红，要么矩阵里那句自检预言被删除并写明理由 | **已结清（2026-09-04，取后一支）**：矩阵 `tests-20260901-224500.md` §WI-13 的那句预言已划掉并附证伪记录。**不补用例是有意的**——R-4 护的是「换章会重绘」这个可观测行为；断言某一根具体监听存在，等于把一处冗余布线钉成规格，011 / 014 重写外壳时它只会变成假警报。K4 那根线的回归防护归 K4 自己的兑付方，写一条直接断事件派发的用例 |
| 20 | **`findAndGo()` 在 `Reader3Epub.displaySectionIndex` 缺失时回退到 `window.location.href`**，于是一个彻底坏掉的站内导航器会**降级成一次看起来完全正确的整页加载**。WI-13 的定向破坏 D5 实测：删掉 `displaySectionIndex` 之后，`<mark>` 数量、文本、id 集合、以及 `pathname_is` **四项全绿**，只有事先埋在 `window` 上的哨兵变量抓到了降级。**这是契约不是缺陷**（回退本身是好设计），欠的是**任何做站内导航的用例都必须带这个哨兵**，否则它以为自己在测站内导航，其实测的是整页加载 | WI-13（2026-09-04 发现） | **无需修**——欠的是写法，已由 R-4 的哨兵示范 | 全仓不存在「声称测站内导航但没有哨兵」的用例 | 记录在案 |
| 21 | **主题四态（白/黄/护眼/夜间）是死的**：`rd-pref-theme-paper` / `-sepia` / `-green` / `-night` 四个 `<div class="theme-option">` 全仓**没有任何监听器**——`src/reader3_app/web/static/` 下 grep 不到 `theme-option`、`selectTheme`、`data-theme`，模板里也没有内联 `onclick`；CSS 自带 `cursor: not-allowed`，注释写着 `/* Theme selector (UI only for v1) */`。**与欠账 #11（`rd-page-*`）同型**：testid 存在会让人以为背后有行为，R-6a 因此只能断言「点了主题之后标注还在」，而不能断言「主题变了」 | WI-14（2026-09-04 实测，主控独立复验 grep 为空） | **4A / 前端计划**：要么接上行为，要么把四个 testid 删掉——留着裸 testid 是在骗后来的用例作者 | 四个主题可点且生效，或四个 testid 从模板消失 | 未结清 |
| 22 | **字号 / 段落间距的改动传到 iframe 里晚一拍，第一次点击对正文毫无效果（用户可见）**：四个按钮的处理器都是先 `applySettings()` 后 `saveSettings()`，而 `applySettings()` → `Reader3Epub.applyThemeSettings()` → `buildContentCss()` → `getFontSettings()` **是从 `localStorage` 读的**，此刻 `saveSettings()` 还没写。外层 `documentElement` 的 CSS 变量当场就对，只有 iframe 内容拿到上一次的值。实测（间距基线 1.9 × 17px = 32.3px）：`−` 第一次 → 32.3px（纹丝不动）、`−` 第二次 → 30.6px、`+` 第一次 → 28.9px、`+` 第二次 → 30.6px——每一步都恰好落后一拍。修法是把两行调个个儿，或让 `applyThemeSettings` 收参数而不是回读 `localStorage` | WI-14（2026-09-04 实测，主控独立复验调用链） | **009 合并后的一条独立小分支**（2026-09-04 裁定，记在[进度盘](../../20260824-frontend-backend-plan-progress.md)；不插进 009，§0.5 不开行为变更窗口）。前端计划 §6.1 落 WI-18，届时只需复核 | 点一次 `+`，iframe 内 `--reader-font-size` 当场变；R-6a 的步进断言不再需要点两次 | **✅ 2026-09-06 结清**（分支 `016-settings-apply-order`）。**修法不是调换那两行**：病根是 `epub-renderer.js` 自己回读 localStorage，顺序只是它的第一个后果；第二个后果是边界校验只在 `reader.html` 里，越界值只被外层挡住（实测：面板 17px、正文 99px、行高 891px）。生产侧改成把校验过的值经 `applyThemeSettings({fontSize, lineHeight})` 传下去，两个后果一起消失，顺序怎么摆都绿——所以**没有**动那两行，动了反而是一处测不出来的改动。钉住它的是 R-6a（刺激收成一步）与新增的 R-6c（面板与 iframe 必须同源）；`baseline_1b` 66→67、`suite_hash` `e7e0f9626df5`→`8f39737ca0c6` |
| 23 | **多选模式没有视觉反馈**：`library.js` 的 `setSelectMode` 往 `<body>` 上加的类叫 `select-mode`，而样式表里写的是 `.selection-mode .select-checkbox { opacity: 1 }`——**两个名字对不上**，于是进入多选模式后复选框仍是 `opacity: 0`，只有 `.book-card:hover` 那条兜底规则能让鼠标悬停时露出来。键盘用户与触屏用户因此完全看不到自己已经进了多选模式 | WI-15（2026-09-04 发现，主控独立复验两处类名） | **前端计划 WI-13**（4A.4 书库页切片；改一个类名即可，但哪个名字是设计想要的归那边裁定，见其 §6.1） | 进入多选模式后不悬停也能看到复选框 | 未结清 |
| 24 | **阅读器左栏的「回书架」链接没有 testid**，只有 `title="Back to Library"`（`reader.html` 的 `<a href="/" class="rt-btn">`）。X-2a 的往返因此只能靠英文 title 的可访问名，**与欠账 #15 同一脆弱类**：合规、lint 拦不到、改文案即断 | WI-15（2026-09-04） | **4A**（补 testid，命名按 ADR-0014） | X-2a 改用 `get_by_test_id` | 未结清 |
| 25 | **Wave 4 又攒下一批该上收的 helper，且 `_open_ch0` 已经重复三份**（`test_write_recolor_and_delete.py`、WI-14 的 baseline 模块、WI-14 的 acceptance 模块）——它同时**背着欠账 #16 的等待纪律**，复制一份就多一处会悄悄退化的等待；WI-13 的 `_settled(page, frame, expected_marks)` 是同一条纪律的又一次转写。连带待上收：`_open_font_popover`、`_content_style`、`_assert_corpus_unchanged`，以及 WI-15 的 `_assert_visible_book_ids` / `_read_collections` / `_collections_file` / `_delete_collections_with_prefix` / `_http_json`。**另需写进 §0.6 的不是 helper 而是一条纪律**：共享 worktree 的并行波次里，定向破坏一律走 `page.route` 改写响应体，**绝不原地改 `src/`**——Wave 4 里 WI-14 的 S1 破坏被并跑的 WI-13 当场撞见（WI-13 处置正确：不碰，自己全程走 `page.route`） | Wave 4（2026-09-04） | **Wave 5 的 WI-10**（下一个被授权写 `helpers.py` 的工作项；共享文件授权制见 §0.6） | `grep -c "def _open_ch0\|def _settled" tests/e2e/baseline_1b/*.py tests/e2e/acceptance_4b1/*.py` 为 0。**纪律那一半已结清**：009 里已无并行波次（Wave 5/6/7 全独占），真正的消费者是 011/013/014，所以它已上收进[迁移计划 §5 的工程实践表](../plan-tech-stack-migration.md)，不留在本表 | **已结清**（Wave 5 / WI-10，2026-09-04：十一个 helper 进 `helpers.py`，七个模块切换调用点，验收 grep 为 0。唯一非纯改名的是 `assert_corpus_unchanged`——四个模块各查各的字面量，抽成 `assert_corpus_unchanged(*checks)`，期望值与消息逐字留在各模块的 `CORPUS_CHECKS`，基准仍是字面量） |
| 26 | **未建索引的书，AI 提问只在「整句是正文子串」时才能回答**：`ai/rag.py` 的 `_keyword_fallback` 用 `text.lower().find(query.lower())` 拿**整个提问**当子串找，不分词。实测 `'Alpha prose'` 200、`'Alpha 这一章讲了什么？'` 400（`This book is not indexed for semantic retrieval yet`）。用户在没跑 `--index` 的书上问任何自然语言问题都会被拒，而错误文案只说「没建索引」，不说「换个问法」。这是降级路径的可用性缺陷，不是 bug；009 只特征化（X-1 的提问因此取 `"Alpha prose"`） | WI-16（2026-09-04 实测） | **011**（`rag.py` 属后端重构范围；改法是分词后任一关键词命中即回退，或至少把 400 文案改成可操作的） | 未建索引的书上，含正文关键词的自然语言提问返回 200 SSE；X-1 的 `QUESTION` 届时可改回矩阵原句并保持绿 | 未结清 |
| 27 | **验收组的 17 条 skip 用例引用了 18 个今天还不存在的 testid**：`rd-degrade-s1` / `-s1-action` / `-s1-excerpt` / `rd-degrade-s3` / `rd-note-stale-badge` / `lib-degrade-s2` / `-s2-action` / `-s2-reindex` / `lib-degrade-s3` / `-s3-action` / `-s3-list` / `-s3-toggle` / `lib-status-stale` / `lib-storage-format-badge` / `rd-conflict-dialog` / `-keep-mine` / `-take-remote` / `-close`。另有一个非 testid 的待定名 `DEGRADED_ATTR = "data-annotation-degraded"`（挂在 `rd-shell` 上）。**`rd-conflict-dialog-close` 不是待实现项**——2a 的用例断言它必须**不存在**（Modal 通式 `*-close` 的反例），实现方照着清单批量加 testid 时最容易顺手把它也加上，那会让那条用例转红 | WI-17（2026-09-04 清点） | **010 / 013 / 014**，各自落自己那一组 | 对应用例的 `skip` 摘掉后转绿，且 `rd-conflict-dialog-close` 仍不存在 | 未结清 |
| 28 | **两张 `DEG_TESTIDS` 表必须是裸赋值，不能加类型注解**：`tests/unit/test_e2e_group_guard.py` 的 `_testid_table_keys()` 只 walk `ast.Assign`，加了 `: Dict[str, str]` 就变成 `ast.AnnAssign`，守卫**静默失明**（不是报错，是查不到表、当成两组用例没有共用键集）。该文件已入红收据 `009-WI-17` 按行冻结，本波因此改的是被测模块而不是断言——两个 DEG 模块各留了四行注释说明「不加注解是有意的」。`tests/unit/test_deg_assertions_shared.py` 已同时认 `Assign` / `AnnAssign`，所以只差守卫这一处 | WI-17（2026-09-04） | **下一个有正当理由动 `test_e2e_group_guard.py` 的人**（改它要重录红证） | `_testid_table_keys()` 两种赋值形态都认，两张表可以加回注解 | 未结清 |
| 29 | **`PUT /api/notes/{book}/{ch}/{id}` 今天只收 `note_text`**（`UpdateAnnotationRequest` 就这一个字段，`notes_service.update_annotation` 也只写它，空 `note_text` 直接 400）。W-5b 要求的「原地改色」因此在服务端就走不通——这是 W-5b 挂 skip 背后的**第三个阻塞点**，此前只记了欠账 #9 与两条前端分支 | 修 #54 时读 `src/` 发现（2026-09-05） | **4B.1**（要动 `src/`，009 无 `src/` 窗口） | `UpdateAnnotationRequest` 有承载颜色的字段，且 `test_w5b_recolor_keeps_id.py` 解 skip 后那条 PUT 不再 400 | 待兑付 |
| 30 | **`acceptance_4b1` 每个模块只允许一个 skip 构造**（`lint_e2e_groups.py` 的静态 skip 轴），因此 R-6b 的主题参数排除只能写成数据字段 `excluded_because`，不能用 `pytest.param(marks=pytest.mark.skip(...))`。这条约束今天没有定义处，只活在 lint 的实现里 | 修 #53 时撞上（2026-09-05） | **#22 或 4B.1**（择一，写进 `lint_e2e_groups.py` 的文档串即可） | `lint_e2e_groups.py` 里能 grep 到这条规则的成文理由，而不是只有实现 | 待兑付 |

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
> 下游也随之分开：**Phase 4A 要的是 G1**（有一套能跑的 E2E 就够了），**Phase 3 要的是 G2 之后再连绿十次**。

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

- **零 flaky**：`baseline-1b` 连续 3 次全量运行无偶发失败才算达标。理由见 soak 门槛——一条会偶发失败的 E2E 当不了 Phase 3 数据迁移的验收基准，而 flaky 会让计数反复清零
- **「绿」的判据（2026-09-02 补，缺这条则整道门可被零成本绕过；2026-09-04 订正 `deselected` 一项）**：一次运行记为绿，**当且仅当** `passed == EXPECTED_BASELINE_ITEMS` 且 `skipped == failed == errors == 0` 且 `deselected == EXPECTED_ACCEPTANCE_ITEMS + EXPECTED_UNGROUPED_ITEMS`。
  - **订正的原文是「`deselected == 0`」，它在 Wave 7 之后是一条无法满足的判据。** soak 发的是 `-m baseline_1b`，验收目录与白名单模块**必然**被筛掉；写这条时 `tests/e2e` 整棵树都是 baseline，deselect 数恰好为 0，于是把一个巧合写成了规格。Wave 7 落地 24 条非 baseline item 之后，`soak_run.py` 真跑一次得到 `65 passed, 24 deselected` → 判红且不可记账——**这道门变成了永远开不出绿灯的门，而失败形态是「台账永远为空」，恰好和「还没开始数」长得一模一样。**
  - 订正后本意不变，反而更强：合法值不是「随便多少」，是**恰好等于那些本就不该被选中的条**。多筛一条（有 baseline 用例被漏跑）与少筛一条（有验收用例漏挂分组标记）**都判红**，两个方向各有一条用例钉住。派生自 `lint_e2e_groups.py` 的两个常量，不写字面量 24。
  - 为什么必须写死分母：「无偶发失败」只约束**失败数**，「全量运行」只约束**调用形态**，两者都不约束**实际执行了几条**。一个挂了 `@pytest.mark.skip` 的模块照样算「全量运行、0 failed」——于是给一条不稳的 baseline 用例挂 skip，就成了让 G2 变绿的**零成本、且在台账上无痕**的手段（`result` 列只有 pass/fail）。
  - `soak-log.md` 的 `result` 列**由 `scripts/soak_run.py` 按上述条件判定，人工不得改写**（这是对表头的说明，不增列；八列字段的定义仍在迁移计划 §7）。
- **commit 级护栏（与上一条是两个触发频率）**：soak runner 只在 G2 跑三次，而「往 `conftest.py` 的 fixture 里加一句 `except Exception: pytest.skip(...)`」这类改动**每次 push 都在生效**。因此追加一条常设约束：**`baseline_1b` 的收集可达链（`tests/e2e/conftest.py`、`tests/e2e/helpers.py`、`tests/e2e/baseline_1b/**`）内不得出现任何 skip 构造，函数体与异常处理器里的一并计入。** 这条今天在代码里成立；写进本节是为了让它被破坏时是一次**有意的违约**，而不是一次顺手的防御性提交。
- 单次全量运行时长记录在案（后续 soak 期间要跑十次以上，时长本身就是可行性约束）
- **`soak-log.md` 已建，八列字段齐全**（字段定义在迁移计划 §7 的「台账字段（canonical）」，本文不重述），表头写明 `suite_hash` 的取法命令与当前值，**以及 §7 记在取法命令旁的那条代价**——`tests/fixtures/epub_corpus.py` 在覆盖范围内，因此一次纯单测目的的构造器改动也会清零 soak 计数
- **`suite_hash` 进入冻结状态**——从这一刻起再改 `baseline-1b` 的用例或 harness，soak 计数从零重来。所以 G2 的真实含义是「**你愿意为这套用例的当前形态背书**」，不是「它今天碰巧绿了」

**G2 达成之日 = soak 计数第 1 行的日期。** Phase 3 从这里开始数 ≥10 次 / ≥5 个工作日。

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
