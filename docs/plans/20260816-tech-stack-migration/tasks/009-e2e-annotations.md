# 009-e2e-annotations —— 任务

- **对应阶段**: Phase 1b（Playwright E2E）起写，后续阶段逐组激活
- **进入条件**: Phase 0 的 0.3（`--port` + `/api/health`）与 0.5（`data-testid` 全量补齐）完成。见 `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md` §6
- **退出条件**: **两道门，分开记，见 §8**——**G1 用例完成门**（`baseline-1b` 写完并绿、其余组以 skip 形态写完并 review）与 **G2 基线稳定门**（零 flaky ＋ 台账开张 ＋ `suite_hash` 冻结）。**不再要求「主 CI 绿灯」**——CI 已统一为仅发版触发，改基说明见迁移计划 §7 的 soak 小节。其余组各自在所属阶段的出口生效，见 §0.5
- **下游**: Phase 4A 的进入条件是 **G1**；**Phase 3 的 soak 计数从 G2 达成之日起才开始数**（次数、跨度、台账字段、清零规则的唯一定义处是迁移计划 §7 的 soak 小节，本文件不复述）。**本分支还要建 `soak-log.md` 台账**——改基之后 soak 数的是它，没有它就没法计数
- **契约**: K1–K6 见 `docs/plans/20260817-frontend-ui-refactor/contracts/annotation-host-contracts.md`；降级状态 DEG-S1–DEG-S5 见 `docs/plans/20260817-frontend-ui-refactor/spec-frontend-design.md` §6.4

> **引用规则**：用**符号名**与 **testid** 定位，不写代码行号。

> **008 留给本分支的一个必做动作**：`.claude/tdd-guardian/config.json` 里 `e2e` lane 的
> `gateOn` 现在是**空的**——008 打开本地门禁时，空的 e2e 目录会让每一次 push 永远
> `never passed`，逼所有人常年挂 `TDD_GUARD_BYPASS`。**加第一条 e2e 用例和 `live_server`
> fixture 的那个 commit，必须在同一个 commit 里把 `gateOn` 改回 `["push"]`。**
> 恢复条件的唯一定义处是那条 lane 自己的 `description`，本文不复述。

> **跨计划**：[前端计划](../../20260817-frontend-ui-refactor/README.md)的测试矩阵**引用本文的用例 ID**（`R-1`…`R-6` / `W-1`…`W-10` / `K-1`…`K-6` / `X-1` / `X-2`）与 §0.5 的激活分组，**不重写这些用例**。前端矩阵新增的是本文范围之外的东西：按钮态、面板互斥与焦点、键盘与 a11y、数据态、响应式、主题解析。两边出现冲突时，标注 E2E 的用例定义以本文为准。

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
| **`baseline-1b`** | §2 读路径 R-1…R-6、§3 写路径 W-1…W-10、§4 的 K-2 / K-3 / K-4 / K-5、§6 X-1 / X-2 | Phase 1b | ✅ | ✅ |
| **`acceptance-4b1`** | §4 的 K-1（响亮失败）与 K-6 的抛错断言 | 4B.1 | ❌ | ❌ |
| **`acceptance-p3`** | §5 的 DEG-S1–DEG-S4，**朴素横幅形态** | Phase 3 出口 | ❌ | ❌ |
| **`acceptance-4a4`** | §5 的 DEG-S1–DEG-S4，**设计规格形态**（只改 testid 映射，断言语义不变） | 4A.4 | ❌ | ❌ |
| **`acceptance-2a`** | DEG-S5 写冲突（本文 §7 已列为不在 1b） | Phase 2a | ❌ | ❌ |

**落地方式**：用 pytest marker（`@pytest.mark.baseline_1b` 等），CI 按组选择。未激活的组以 `skip` 而非删除的形式存在，理由是它们必须在写的时候就被 review——**一条到期才第一次被人读的断言，等于没写。**

### `baseline-1b` 对 K1 / K6 的现状特征化

这两条契约在 1b 阶段仍要有护栏，只是断言的是**今天的行为**，不是 4B.1 之后的行为：

| 契约 | `baseline-1b` 断言（现状特征化） | `acceptance-4b1` 断言（行为变更后） |
|---|---|---|
| **K1** | 七个宿主元素在模板中齐备，标注 UI 正常 init（**前置条件成立**的正向证据） | 移除 `annotation-toolbar` 后重载 → 明确 `console.error` 且降级标记置位 |
| **K6** | 在 `/read/{bookId}/{chapterIndex}` 创建标注，`notes.json` 的 `chapter_index` 等于 URL 里那个数 | 删掉 `location.pathname` 回退后，`window.Reader3Ctx` 缺失时**抛错**而非静默猜测 |

K1 的 baseline 条是有价值的：它会在**任何人改模板删掉那七个 id 之一时**变红，而这正是 4B.2 外壳重写最可能干的事——不必等到 4B.1 才有护栏。

---

## 1. 基础设施

| 项 | 要求 |
|---|---|
| `webServer` | Playwright 起自己的实例，端口由 `--port` 指定（**不得用 8123**，会撞开发者本地与 CI 并发），就绪探针用 `GET /api/health` |
| **图书目录隔离** | `READER3_BOOKS_DIR` 指向 tmp 目录，测试前从 fixture 拷入。**任何用例都不得读写开发者真实的 `books/`**——本套用例会创建和删除标注。⚠️ `server.py` 在**模块导入时**把它读成模块级常量，因此必须在 `webServer` 启动前置入环境变量，运行期改无效 |
| 选择器 | **只允许 `data-testid` 与 ARIA role/name**。禁止 class、`nth-child`、层级结构选择器。CI lint 强制（0.5 的产出） |
| iframe 语料 | 至少两本：一本英文短篇、一本 CJK。CJK 那本用来卡 quote/prefix/suffix 的多字节边界 |
| 并发 | 每个 worker **一个独立服务进程 + 一份独立 books 目录副本**（因为上面那条：目录是进程级常量，同一进程内无法按用例切换），`notes.json` 不共享 |

**iframe 内建选区的标准路径**（Selection 不能跨 browsing context，所以必须在 child frame 内做）：

```
child frame 内 document.createRange() → 写入 iframe 的 Selection
  → 在 iframe document 上派发 mouseup
  → 点外层工具条（testid 定位）
  → 断言往返
```

真实鼠标拖选只保留 **1 条 smoke**，其余走上面这条程序化路径——拖选在 CI 上是头号 flaky 源，而 flaky 会把 soak 门槛的计数清零。

---

## 2. 读路径用例

| # | 用例 | 关键断言 |
|---|---|---|
| R-1 | 书库 → 打开书 → 阅读器渲染 | iframe 内有正文文本节点，非空白页 |
| R-2 | 章节导航（Prev / Next / TOC 点击） | 落到正确 spine index，URL 形状符合 K6 |
| R-3 | 既有标注恢复 | 预置 `notes.json` → 打开章节 → `<mark>` 出现在**预期的那段文字**上（比对 `textContent`，不是数量） |
| R-4 | 翻章后重绘 | 换章 → 新章高亮数量正确 **且** 旧章高亮不残留（K4 的可失败断言） |
| R-5 | 阅读页内搜索 | 命中高亮出现——**K5 的第二个消费方是 `search.js`**，这条用例是它唯一的护栏 |
| R-6 | **改主题/字号/行距后既有标注仍锚定同一段文字** | 设计规格 §6.0 判定标准的**断言 C**。预置标注 → 记录其 CFI → 逐项切换主题、字号、行距 → 每次都重新解析同一条 CFI，`range.toString()` 等于存储的 `quote`；同时 `<mark>` 覆盖的 `textContent` 不变 |

> **R-6 为什么必须存在**：设计规格 §6.0 从一开始就写着「Phase 1b 的 E2E 必须覆盖『改栏宽后既有标注仍能正确高亮』」，但本文此前**没有对应用例**——一条只写在设计文档里、没有落到用例表的门槛等于没有。
>
> **参数会随功能增长**：主题、字号、行距三项**今天就存在**（`reader.html` 的 Font Settings + `applyThemeSettings()`），所以 R-6 属 `baseline-1b`。D5 的**正文栏宽**要到 4B.3 才有，届时它作为 R-6 的**第四个参数**加入，而不是新开一组；**4B.3 的退出门槛需包含「R-6 的栏宽参数已启用并绿灯」**。



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
| W-5 | **改色**（yellow → green） | 刷新后颜色为 green，且**标注 id 不变**（改色不是删了重建） |
| W-6 | **删除** | 刷新后该段文字上无 `<mark>`；`notes.json` 里对应条目消失；**其他标注不受影响** |
| W-7 | **笔记编辑保存**（打开已有笔记 → 改文本 → 保存） | 刷新后读回新文本；这条走 `note-editor` → `commands.saveNote` 的完整链 |
| W-8 | 重叠标注 | 在已有标注上再划一段重叠区域，两条都能刷新后恢复 |
| W-9 | CJK 书上重复一遍 W-1 与 W-7 | quote/prefix/suffix 的多字节边界 |
| W-10 | 同章重复文本消歧 | 章内出现两处相同文字，标注第二处，刷新后落在**第二处**（prefix/suffix 生效） |

**W-6 的反向断言不可省**：删除是唯一会破坏用户数据的操作，"删对了一条"和"顺手删掉了别的"在 UI 上看不出来。

---

## 4. K1–K6 各一条能失败的断言

| 契约 | 用例 | 组 | 断言 |
|---|---|---|---|
| **K1** | K-1a | `baseline-1b` | 七个宿主元素齐备且标注 UI 正常 init（前置条件的正向证据） |
| **K1** | K-1b | `acceptance-4b1` | 用 `page.evaluate` 移除 `annotation-toolbar` 后重载标注 UI → 断言控制台出现明确 `console.error` 且降级标记置位。**不能只断言"工具条不见了"**——契约的价值在于把静默变响亮。⚠️ 该行为 4B.1 才实现，不计入 1b 门槛 |
| **K2** | K-2 | `baseline-1b` | 工具条每个 `data-action` 逐个点一遍，断言**结果**（标注真的产生/删除/改色），不是断言按钮存在 |
| **K3** | K-3 | `baseline-1b` | ①三个浮层各跑 `containingBlockAncestor(el) === null`；②工具条矩形与选区矩形相对位置在容差内。判据与参考实现见契约文件 |
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
| X-1 | AI SSE 流式 | 首 token 到达 + 流正常结束 + 中断可恢复 |
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

### G2 —— 基线稳定门

- **零 flaky**：`baseline-1b` 连续 3 次全量运行无偶发失败才算达标。理由见 soak 门槛——一条会偶发失败的 E2E 当不了 Phase 3 数据迁移的验收基准，而 flaky 会让计数反复清零
- 单次全量运行时长记录在案（后续 soak 期间要跑十次以上，时长本身就是可行性约束）
- **`soak-log.md` 已建，八列字段齐全**（字段定义在迁移计划 §7 的「台账字段（canonical）」，本文不重述），表头写明 `suite_hash` 的取法命令与当前值
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
