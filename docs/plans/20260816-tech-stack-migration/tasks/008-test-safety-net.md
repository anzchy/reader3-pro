# 008-test-safety-net —— 任务

- **对应阶段**: Phase 1a（测试安全网 · 后端）
- **进入条件**: Phase 0（007）全部合入
- **退出条件**: CI 绿灯成为合并门槛；42 条路由契约全绿；API v1 冻结；性能基准记录在案。见 `plan-ui-migration-sequencing.md` §7
- **下游**: **一切**。Phase 2 / 3 / 4 的每一次重构都靠这张网判断「有没有改坏」。没有它，后面每个阶段都是盲改
- **契约**: 本分支产出的路由契约即 API v1 冻结基线

> **这个分支不产出用户可见的变化。** 它唯一的产出是「改坏了会有人告诉你」。评价标准不是写了多少测试，而是**改坏了能不能被抓住**——所以 §1 的覆盖率策略和 §5 的异常规则比用例数量重要。

---

## 1. 先定覆盖率基线策略（这是本分支的头号决策）

**现在的配置有个坑，得先补。** `.claude/tdd-guardian/config.json` 里 `coverageMode` 是 `"no-decrease"`。它的语义是：**首次运行、以及每次切换分支**，把当时的覆盖率记为基线并直接通过；此后只在**下降**时拦截。

放在别的项目里这是个合理默认。放在这个计划里不是——因为这个计划**一个里程碑一个分支**（007 → 008 → 010 → 011 → 012 → 013 → 015）。每开一个新分支，基线就重记一次。结果是七个互不相干的「没有下降」检查，**全局地板不存在**。012 把覆盖率从 78% 做到 55%，只要它是在自己分支上一路降下去的，门禁一次都不会响。

**建议**：008 收尾时把 `coverageMode` 切成 `"absolute"`，阈值就用现在配置里已经写好的 `lines 70 / branches 60`。理由很简单——那两个数字正是 Phase 1a 的**退出目标**，在 008 之前它们够不着（所以现在用 no-decrease 是对的），在 008 之后它们必须够得着。门槛从「相对」换成「绝对」的时刻，就是目标从「够不着」变成「够得着」的时刻。

> ⚠️ 切换之前先把 007 分支上那个「PASS」看清楚：那是首次运行记基线记出来的 PASS，不是达标。别拿它当已经 70% 的证据。

**再加 `criticalPaths`**，给技术栈计划点名的高危模块单独设更严的绝对门槛（`criticalPaths` 在两种 `coverageMode` 下**都是绝对值**，不受 no-decrease 影响）：

| glob | branch | 出处 |
|---|---|---|
| `src/reader3_app/notes_service.py` | 90 | 技术栈计划「测试」节点名 |
| `src/reader3_app/ai/**` | 90 | 同上（AI routing） |
| `src/reader3_app/search_service.py` | 85 | `_normalize_with_map` 在这里 |

**`book_store.py` 现在不要配。** 它要到 011 才存在，而**匹配到零个文件的 glob 判 FAIL 而不是 PASS**——提前配上会让 008 一路红。等 011 建了这个模块，在那条分支上加。

---

## 2. 测试目录与 lane（已配好，只需核对）

`.claude/tdd-guardian/config.json` 里两条 lane 已经写好了：

| lane | 命令 | 门禁时机 | 覆盖率 |
|---|---|---|---|
| `unit` | `uv run pytest tests/unit tests/contract --cov=src/reader3_app` | `taskCompleted` / `commit` | 计入 |
| `e2e` | `uv run pytest tests/e2e --browser chromium` | `push` | 不计 |

对应四个目录：

| 目录 | 装什么 | 谁建 |
|---|---|---|
| `tests/unit/` | 纯函数与模块级 | 008 |
| `tests/contract/` | 42 条路由的请求/响应契约 | 008 |
| `tests/e2e/` | Playwright | 009 |
| `tests/fixtures/` | EPUB 语料与合成书库 | 008 |

`tests/conftest.py` 已存在，提供 `repo_root` / `fixtures_dir` / `books_dir`。**`books_dir` 是隔离用的 tmp 目录，任何写测试都必须用它**——原因见 007 的 0.1（`process_epub()` 会 `rmtree` 输出目录）。

`tests/e2e/conftest.py` 的 `live_server` fixture 还没写（这也是 e2e lane 没配 `setupCommand` 的原因），属 009。它依赖 007 的 `--port` 和 `/api/health`。

---

## 3. Fixture 语料

技术栈计划的「测试」节列了 7 组原始语料，另加 4 组：

| 组 | 覆盖什么 |
|---|---|
| **spine / TOC 结构** | 多个 TOC 条目指向同一 spine 文件但锚点不同；嵌套 TOC；spine 与 TOC 不一致 |
| **Unicode** | emoji、非 BMP 字符、组合字符、带变音符号的拉丁字母（`café` → `cafe` 归一化） |
| **标注锚定** | quote/prefix/suffix 在重复文本中的定位；重叠标注；跨元素选区 |
| **规模与失败** | 截断的 EPUB、缺 `book.epub`、损坏 `book.pkl`、空 spine |

> **偏移量单位**：Python 侧是 **Unicode code point**，DOM/JS 侧是 **UTF-16 code unit**。Unicode 组的 fixture 必须能把这个差异逼出来——emoji 和非 BMP 字符是唯一会让两者分叉的输入。这条已写进技术栈计划的 API 契约要求，测试要能守住它。

---

## 4. 42 条路由契约

`web/server.py` 现在正好 **42** 个 `@app.<method>`。技术栈计划要求分三层组织，不要写 42 个雷同的测试函数：

1. **`app.routes` 清单快照** —— 一条测试断言路由集合（路径 + 方法）整体不变。加了新路由或改了路径，这条先红。这是 API v1 冻结的机械执行者
2. **六组表驱动契约** —— 按 `/api/search/*`、`/api/ai/*`、`/api/settings/*`、`/api/library/*`、`/api/notes/*`、页面路由 分组，每组一张参数表，跑同一套断言（状态码、响应 schema、错误形状）
3. **少量领域场景** —— 只给确实有业务逻辑的端点写，比如标注的增删改查一致性、AI 会话的持久化

`specs/_archive/*/contracts/*.yaml` 里有旧的契约 YAML。**可以拿来做参考清单，但不能照着实施**——`specs/_archive/` 是冻结的历史记录，代码才是权威。用它对照「有没有漏掉某个端点」，而不是用它定义「端点应该长什么样」。

---

## 5. B2：异常处理规则

全项目 **67 处 `except Exception`**、**4 处裸 `pass`**。这既是 bug 温床，也是测试写不出来的直接原因——吞掉的异常没有可断言的行为。

**在 Phase 1a 一开始就把三档规则写下来**（写进 `AGENTS.md` 或 `CONTRIBUTING`），然后：

- ruff 开 `BLE`（`blind-except`）和 `S110`（`try-except-pass`）
- 存量用 `# noqa` 加理由逐条豁免，**新增代码不许豁免**
- 本分支只修四处点名的：`_parse_summary_payload()`、`api_ai_question()` 里的 `push()` 闭包、`ai/books.ensure_book_uuid()`、`ai/conversations.list_conversations_combined()`

> 只修四处，是因为改异常处理**是行为变更**。这也正是它不在 Phase 0 的原因：Phase 0 只做不改变行为的事。剩下 63 处随各自模块的重构分批清，别在 008 里一次性动。

同时把 ruff 与 mypy 的配置落进 `pyproject.toml`——现在 `[tool.ruff]` 和 `[tool.mypy]` 两节都不存在。

---

## 6. 性能基准

Phase 2/3 要动缓存和存储格式，没有基线就无法判断改动是优化还是劣化。技术栈计划点名六项：

| 指标 | 为什么要它 |
|---|---|
| 冷启动耗时 | Phase 5 的启动体验要拿它对照 |
| 二次相同查询耗时 | 量 `lru_cache` 的实际收益 |
| 峰值 RSS | Phase 3 换存储格式最可能在这项上退化 |
| 反序列化次数 | A5 三处 loader 合并的直接指标 |
| 归一化次数 | `_normalize_with_map` 的重复计算量 |
| 首页冷启动 TTFB × 书库规模 | 唯一能暴露 O(n) 扫描的指标 |

**需要一个 20 本书的合成书库 fixture**，外加 1–2 本大部头覆盖 C2 的三百万字符路径。合成即可，不要用真实书——测试永远不碰用户的 `books/`。

基准只记录、不设阈值门禁。性能回归门禁等有了多次运行的方差数据再谈，现在设阈值只会得到一个天天误报的 CI。

---

## 7. CI

现在**没有** `.github/workflows/`。建一个，跑：

1. `uv sync`
2. ruff + mypy
3. unit lane（含覆盖率门禁）
4. 007 的两条 testid lint
5. 007 的 wheel 打包验证（`uv build` + 解包断言）

e2e lane 留给 009 接。

**CI 绿灯成为合并门槛，这条本身就是 008 的退出条件之一**——把工作流建起来但不设为 required check，等于没建。

---

## 8. API v1 冻结

路由清单快照（§4 第 1 层）通过之后，宣布 v1 冻结。之后任何路由的增删改都必须：

- 先改快照测试（说明这是**故意的**）
- 在 PR 描述里说明破坏性与迁移路径

Phase 4 的 TypeScript 前端就是照着这份冻结的 v1 写的。冻结的意义在于：前端重写期间后端 API 不动，两边可以并行推进而不互相踩。

---

## 9. 退出门槛

- [ ] `tests/unit` / `tests/contract` / `tests/fixtures` 三个目录建好，unit lane 能跑
- [ ] 11 组 fixture 语料齐（7 组原始 + 4 组新增），Unicode 组能逼出 code point / code unit 差异
- [ ] 42 条路由三层契约全绿；路由清单快照到位
- [ ] `coverageMode` 切到 `absolute`；`lines ≥ 70` / `branches ≥ 60` 实际达标
- [ ] `criticalPaths` 三条 glob 配好并通过（`book_store` 不在其中，留给 011）
- [ ] ruff `BLE` / `S110` 生效；三档异常规则成文；四处点名站点修完
- [ ] `[tool.ruff]` / `[tool.mypy]` 进 `pyproject.toml`
- [ ] 六项性能基准记录在案；20 本合成书库 fixture 可用
- [ ] GitHub Actions 建好，**且设为 required check**
- [ ] API v1 冻结公告写进 `AGENTS.md`

---

## 10. 关于用 `/tdd-guardian:workflow` 跑这个分支

**能用，但只对 §4 和 §5 用。** 路由契约和异常处理都是「输入 → 断言输出」形状，workflow 跑得动，一组路由一发。

**不要**把 §1（覆盖率策略）、§6（性能基准）、§7（CI）交给它——前者是改配置文件，后者两个的产出是 YAML 和一份基准记录，不是通过/失败的断言。`tdd-planner` 会为它们设计测试矩阵，然后卡在 wiring-only 门槛上。

输入格式的硬约束与 007 相同：**单行纯文本，不能含反引号、`|`、`>`、`<`、`;`、`&&`、`||`、`$(` 或换行**。详见 `tasks/007-hygiene-and-contracts.md` §9。
