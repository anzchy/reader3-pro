# 015-launch-experience —— 任务（CLI 侧）

- **状态**: 📝 **任务书已写，§6 全部裁定**（Q16 归 WI-20，不在本文裁）。~~草稿，评审中~~（⬛ 2026-10-02：起草于 `master` `94dd1e0`；同日 rev 1 按 Q2 / Q6 裁定改写，Q7 随之推翻；rev 2 按 Q14 / Q15 与 ADR 子问题 a–f 的裁定（含 Codex 修订）改写；同日落地到 `master`，基点记为 `babaf59`——`94dd1e0..babaf59` 只改了两份 soak 单测，`src/`、`pyproject.toml`、`scripts/`、`frontend/` 零改动，下文的符号引用不受影响；数据家 ADR 同时落地为 [ADR-0017](../../../adr/0017-data-home-resolution.md)，Proposed；rev 3 同日按 Codex 计划评审（NEEDS REVISION，16 条）与维护者裁定 D2 / D3 改写：origin 规则迁入 ADR-0017 g，入口分段顺序、绑定发布协议与读时校验补进 ADR-0017，WI-3 构建身份、WI-4 生命周期重写，范围限 POSIX——符号在 `fa9a4fe` 上复核）。分支**未开**，没有一项已实施
- **对应阶段**: M5 / Phase 5（[§9 编号表](../plan-tech-stack-migration.md)：「A（`reader3 launch`）＋ **B**（PWA，WI-20）」）。本文只写归属 **A** 的那一半
- **计划文件夹**: [`20260816-tech-stack-migration/`](../plan-tech-stack-migration.md)（归属 **A**）
- **上游**: `014-ts-frontend-reader`（Phase 4B，[§9.1](../plan-tech-stack-migration.md) Phase 5 的唯一前置）；间接经 014 依赖 `012-storage-format`
- **下游**: 无（§9.1 Phase 5 行「它阻塞谁」为 —）。合入后迁移计划文件夹整体归档（[README](../README.md)「`015-launch-experience` 合入 master 之后」）
- **节奏**: WI 按号串行。WI-2（数据家）先于一切起服务的 WI：它决定服务看到哪个书库，也是 WI-3 实例身份的输入

> **权威范围**：本文**定义**的只有三件事——015 CLI 侧的工作项切分与先后约束、每个 WI 的验收占位、015 CLI 侧的出口闸与合入记录。
> 以下一律**只链接不复述**（「搬，不抄」）：数据家解析规则、入口分段顺序与绑定文件 → **[ADR-0017](../../../adr/0017-data-home-resolution.md)**（下文简称「数据家 ADR」）；
> **`reader3 launch` 打开的 origin（规范形、端口优先级与端口记忆）→ 数据家 ADR 子问题 g**（⬛ 2026-10-02 自本文 §2.3 迁入：本文件夹随 015 归档，这条规则要活得比它久）；
> PWA manifest、service worker、离线壳与缓存契约 → [前端计划 WI-20](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md#wi-20-phase-5-前端侧pwa)；
> `/api/health` 的来历 → [007 步骤 0.3](./007-hygiene-and-contracts.md)；桌面壳「不做」→ [ADR-0008](../../../adr/0008-tech-stack-boundary.md)，其触发条件「仅当确证有非技术用户需要安装包时」→ [迁移计划 Phase 5](../plan-tech-stack-migration.md#phase-5--启动体验与远期桌面化)（ADR-0008 的 Revisit 一节**没有**这一条）；
> 请求边界（Host 白名单、令牌、`/api/health` 令牌豁免）→ 代码 `web.server.RequestGuardMiddleware`（及 `_allowed_hosts` / `_token_exempt`；[ADR-0012](../../../adr/0012-security-boundaries.md) 记的是 unpickler / 路径 / 凭据文件三条，不含它）；每书写协调 → [ADR-0015](../../../adr/0015-per-book-write-coordination.md)；
> `--migrate` / `--migrate-all` → [012 WI-6](./012-storage-format.md)；API 冻结 → [ADR-0011](../../../adr/0011-api-v1-freeze.md)；
> 分支编号 → [§9](../plan-tech-stack-migration.md)；执行顺序 → [进度盘](../../20260824-frontend-backend-plan-progress.md)。
>
> **引用规则**：用**符号名**定位，不写代码行号（同 011 / 012 / 018）。下文每个符号都在 `babaf59` 上核对过；行号会漂，开工当天按 §1 的复核清单重查。

---

## 1. 进入条件

| 条件 | 状态 | 在哪查 |
|---|---|---|
| 014 已合入（Phase 4B 关闭） | ⬜ | [§9.1](../plan-tech-stack-migration.md) Phase 5 行；[进度盘 §1](../../20260824-frontend-backend-plan-progress.md) |
| 本任务书评审通过 | ✅ 2026-10-02 | 本文 §6 全部裁定（Q16 归 WI-20，不计入） |
| 数据家 ADR 已落地（Proposed 即可，编号已分配） | ✅ 2026-10-02 | [ADR-0017](../../../adr/0017-data-home-resolution.md)（Proposed） |
| 开工当天复核「领先一个分支即时补」的事实 | ⬜ | 本节下方清单 |

- **按依赖图，本分支在 014 之后开**（§9.1：Phase 5 ← 4B；§7 门槛表 Phase 5 行进入条件「4B」）。
- **CLI 侧能不能提前？** 代码层面，`reader3 launch` 只依赖已合入的东西：007 的 `resolve_port` / `/api/health`、`reader3_app.reader3.main`。它不读 014 的任何产物。但有两条理由**不建议**擅自提前，是否提前留给 §6 Q1 裁：
  1. 012 WI-6 要改同一个 `main()` 的 argparse（`--migrate` / `--migrate-all`），WI-2 也要在同一个 `main()` 里插入数据家解析——在 012 合入前开 015 等于在同一个函数上排两条并行分支；
  2. Phase 5 的出口判据之一「PWA 版本切换不撕裂」（§7 Phase 5 行）有一半落在 CLI（WI-3 / WI-5 的实例身份），另一半落在 WI-20 的缓存清理（§2.3 末行），要对着 014 之后的前端产物验。
- **开工当天必须复核的事实**（本文写于 012 / 014 都未开的时候，按 [§9「领先一个分支即时补」](../plan-tech-stack-migration.md) 的理由，下列每条都可能已过期）：
  - `reader3_app.reader3.main` 在 012 WI-6 之后的 argparse 形状（`launch` 的分派位置与数据家解析的插入点依赖它，WI-1 / WI-2）；
  - `reader3_app.reader3` 顶层是否仍不导入 `web.server` / `ai.config`（WI-2 的导入顺序前提）；
  - `server.BOOKS_DIR` 是否仍在导入时 `os.makedirs`、`ai.config.DEFAULT_SETTINGS_PATH` 是否仍在导入时求值（WI-2）；
  - `server.main` / `resolve_port` / `DEFAULT_HOST` / `DEFAULT_PORT` 是否仍是 007 的形状；
  - `/api/health` 的响应体形状（WI-3）。注意 ADR-0011 写明冻结**随 014 合入解除**，所以按 Q1 推荐在 014 之后开工时冻结已不约束本分支；§4 门槛 5 的「只加不改」是本文自愿保留的纪律，不是冻结的要求；
  - 单元 lane 的出网栅栏与 `real_loopback_socket` 豁免名单（`EXPECTED_EXEMPTIONS`）的形状（WI-4 / WI-5 的测试要进这张名单）；
  - 浏览器侧是否已有覆盖**首次加载 `/`** 的认证（今天没有：`RequestGuardMiddleware` 只认 `X-Reader3-Token` 头或 `?token=`，页面里的 `fetch` 不带令牌；§6 Q8 按 D3 在此之前一律拒绝）；
  - WI-20 最终把 service worker 与 PWA manifest 挂在哪个路径、缓存清理规则如何裁（§2.3）。
- **009 跨波欠账表里兑付方指向 015 的行**：开工当天照 [§9 的固定动作](../plan-tech-stack-migration.md) 抄。起草时（`94dd1e0`）**为零**；落地时在 `babaf59` 上复核，仍为零。

---

## 2. 范围 / 非范围

### 2.1 范围

| 项 | 来源 | WI |
|---|---|---|
| `reader3 launch` 子命令的入口与参数面 | [Phase 5 本计划侧第 1 条](../plan-tech-stack-migration.md) | WI-1 |
| 数据家解析器：导入 / 索引 / 设置 / launch（及 `reader3-server`，§6 Q14）共用一个书库与一份设置文件，启动前打印 | §6 Q6 裁定（2026-10-02）；规则定义在 [ADR-0017](../../../adr/0017-data-home-resolution.md) | WI-2 |
| `/api/health` 新增一个不透明的实例身份字段 | §6 Q2 裁定（Q7 随之推翻） | WI-3 |
| 起服务 → 轮询 `/api/health` → 启动失败清晰报错 | Phase 5 本计划侧第 1 条 | WI-4 |
| 端口冲突：身份相同才复用，否则拒绝；记住显式端口 | 同上「含端口冲突处理」；§6 Q2 裁定；§7 Phase 5「PWA 版本切换不撕裂」的 CLI 半边 | WI-5 |
| 打开窗口：Chromium 系 `--app=` 窗口 / 默认浏览器 / 不开 | 同上「打开 PWA / Chrome `--app=` 窗口 / 默认浏览器」 | WI-6 |
| 已安装 wheel 冒烟 ＋ 文档 ＋ 功能台账回写 | Phase 5 验收「单命令即可进入阅读」 | WI-7 |

### 2.2 非范围

- **PWA 的一切**：PWA manifest、service worker、离线壳、缓存白名单、版本清理——[WI-20](../../20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md#wi-20-phase-5-前端侧pwa)。本分支不写一个 PWA 字节
- **桌面壳 PoC**（Phase 5 本计划侧第 2 条，「**仅当**确证有非技术用户需要安装包时」）：触发条件未满足，不做。触发条件的定义处是[迁移计划 Phase 5](../plan-tech-stack-migration.md#phase-5--启动体验与远期桌面化) 本计划侧第 2 条；「不做」本身是 [ADR-0008](../../../adr/0008-tech-stack-boundary.md)
- **Windows**：本分支只支持 POSIX（macOS / Linux）。`reader3.py`、`book_lock.py`、`ai/config.py`、`collections_service.py` 顶层都 `import fcntl`，今天的 CLI 在 Windows 上导入即失败；绑定锁同样用 `fcntl`（数据家 ADR「明确不做」）
- **`--migrate` / `--migrate-all` / 未迁移清单**：[012 WI-6](./012-storage-format.md)。`launch` **不**隐式触发迁移（ADR-0009 的迁移是显式命令）
- **书库迁移 / 合并 / 改绑命令**：数据家 ADR「明确不做」。WI-2 只解析和绑定，从不搬数据
- **后台守护进程 / `reader3 stop` / 开机自启 / 结束或替换占端口的进程**：§6 Q5 与 Q2 裁定
- **改动 HTTP 路由集合**：`routes.snapshot` 零改动（§4 门槛 5）。WI-3 只给已有的 `GET /api/health` 加一个字段——按 ADR-0011，快照只管路由集合，响应字段归 layer-2 契约测试。WI-20 若需要新路由，归 WI-20（§2.3）
- **冻结集 8 条路径**：不碰（§4 门槛 F）。e2e harness 显式注入 `READER3_BOOKS_DIR` / `READER3_AI_SETTINGS`，按数据家规则 1 不读不写绑定，所以冻结的 `tests/e2e/conftest.py` 不需要改

### 2.3 CLI ↔ PWA 接缝

origin 规则（规范形、端口优先级、端口记忆、从不自动换端口及其理由）已迁至[数据家 ADR 子问题 g](../../../adr/0017-data-home-resolution.md)（⬛ 2026-10-02）。两半之间只有下面五个接触面：

| 接触面 | 归属 | 定义处 | 另一半怎么用它 |
|---|---|---|---|
| origin | **015 CLI** | 数据家 ADR g | `start_url` / `scope` 写相对路径 `/`；WI-20 验收不需要知道端口 |
| service worker 与 PWA manifest 的 URL、作用域，以及为此可能需要的服务端路由或响应头 | **WI-20** | 前端计划 WI-20 | `launch` 不认识它们；`--browser app` 打开的就是 origin 根路径 |
| 进程生命周期（起、等就绪、停）与「复用已在跑的服务」 | **015 CLI** | 本文 WI-4 / WI-5 | PWA 独立窗口关闭不停服务；服务停了，PWA 显示 WI-20 验收 3 的离线错误态 |
| 实例一致性：`launch` 复用的服务 = 同一书库、同一设置文件、同一认证模式、同一构建 | **015 CLI** | 本文 WI-3 / WI-5 | 只保证页面背后是对的那个服务 |
| **浏览器侧版本切换**：WI-20 在 `activate` 里删除所有版本不等的缓存，与 Phase 5 出口「PWA 版本切换不撕裂」及迁移计划 A4（`skipWaiting()` ＋ `clients.claim()` ＋ activate 立即清旧缓存三者同用会撕裂版本）相冲突 | **WI-20** | 前端计划 WI-20（冲突由协调方记在那里） | **Phase 5 验收前必须裁定**。本文只引用；§4 门槛 8 只验 CLI 半边，M5 整体关闭要等这一条也过 |

- **提给 WI-20 的观察（不在本文裁）**：Vite 的 `base` 是 `/static/dist/`，service worker 若放在那下面，默认最大作用域就是 `/static/dist/`，管不到三个页面——要么服务端在根路径提供 SW，要么加 `Service-Worker-Allowed` 响应头，两者都是后端改动，归 WI-20。同目录下已有一个 Vite **构建 manifest**（`manifest.json`），是第三个叫 manifest 的东西；WI-3 的构建身份也读它（只读字节，不改名不改位置）。

### 2.4 与 012 / 018 的交互

- **012**：`launch` 与 012 WI-6 共用 `reader3_app.reader3.main`。WI-1 的分派放在 argparse **之前**（只认第一个参数恰为 `launch`），不改 012 加的任何 flag；`reader3 launch --migrate` 之类组合直接报用法错。WI-2 的数据家解析插在 `main` 的 argparse 之后、任何惰性导入之前，**对 `--migrate*` 同样生效**（迁移的也必须是同一个家）。`launch` 打开的库里有未迁移的书时，由 012 的 DEG-S4 横幅 / 路由处理，`launch` 不提示、不迁移。
- **018 / ADR-0015**：`launch` 起的服务里每个写手已经按 ADR-0015 持书锁；`launch` 本身**不取任何书锁**。锁目录 `books/.locks/` 跟着书库走——WI-2 之前，从另一个 cwd 跑 `reader3 --index` 的进程用的是另一套锁目录，与服务根本不协调；WI-2 之后两边落到同一个书库、同一个锁目录。这是对 018 契约前提的一处**加强**，不改 ADR-0015 的文字。

---

## 3. 工作项

测试矩阵统一待 `/tdd-guardian:design-tests`；下面的「验收」是种子，不是矩阵。**实施一律走 `/tdd-guardian:workflow`**。

| WI | 标题 | 依赖 | 主要测试 lane |
|---|---|---|---|
| WI-1 | `reader3 launch` 入口与参数面 | — | unit |
| WI-2 | 数据家解析器（导入顺序 ＋ 首次绑定 ＋ 打印） | WI-1 | unit |
| WI-3 | `/api/health` 实例身份字段 | WI-2 | unit ＋ contract |
| WI-4 | 起服务 ＋ 就绪探测 ＋ 启动失败报错 | WI-3 | unit（真起服务，`real_loopback_socket`） |
| WI-5 | 端口冲突：身份复用 / 拒绝 / 记住端口 | WI-4 | unit（`real_loopback_socket`） |
| WI-6 | 打开窗口（`--app` / 默认浏览器 / 不开） | WI-4 | unit（打开器可注入） |
| WI-7 | 已安装 wheel 冒烟 ＋ 文档 ＋ 台账 | WI-1 – WI-6 | packaging |

> **S3 跨 WI**：数据家 ADR 规则 6 的 S3（自持端口 socket）在 WI-2 就要有——WI-2 只实现「绑定并持有，被占即报错退出」，WI-5 再在「被占」处插入健康判定分流。凡依赖分流结果的验收（拒绝的 `launch` 不留绑定、复用）都在 WI-5，不在 WI-2。

> **单元 lane 的出网栅栏**：`tests/unit/conftest.py` 的第三道 autouse 栅栏拦截一切真实 TCP `connect`；真要连回环的测试须带 `@pytest.mark.real_loopback_socket`，而豁免名单由 `tests/unit/test_egress_backstop_unit.py` 的 `EXPECTED_EXEMPTIONS` 锁死。WI-4 / WI-5 的真起服务用例都要进这张名单——**每加一条是一次刻意编辑**，矩阵设计时把用例数压到最少（能用注入探针的就不真连）。
>
> **不加 e2e**（推荐，§6 Q10）：`launch` 的行为在进程、端口与文件系统层，浏览器里看到的页面与 `reader3-server` 起的完全一样，已由 e2e lane 覆盖。若评审要求加，新模块须登记进 `scripts/lint_e2e_groups.py`（018 门槛 6 的同一套规矩）。

### WI-1: `reader3 launch` 入口与参数面

- **目标**: `reader3 launch [--port N] [--browser {app,default,none}] [--timeout S]` 可用；`reader3 <file.epub>` 与 `reader3 --index <book_id>`（以及 012 加的 flag）的**参数面**不变（它们看到哪个书库由 WI-2 改变）
- **涉及文件 / 入口点**:
  - `pyproject.toml` `[project.scripts]`：`reader3` 不改（不新增 `reader3-launch`，§6 Q9）；`reader3-server` 的目标是否改指薄包装见 WI-2 / §6 Q14
  - `src/reader3_app/reader3.py` `main`：在 `argparse.ArgumentParser` 之前，`argv[0] == "launch"` 即转交 `reader3_app.launch.main(argv[1:])`。今天 positional `epub`（`nargs="?"`）会把 `launch` 当成 EPUB 路径，报 `File not found.`——这条现状先用一条特征化测试钉住，再改
  - 新模块 `src/reader3_app/launch.py`（WI-1、WI-4 – WI-6）。**顶层不得导入 `reader3_app.web.server` 或 `reader3_app.ai.config`**（WI-2 的导入顺序前提）；不在 `web/` 下，不声明路由
  - `--port` 解析**复用** `server._parse_port` / `resolve_port` 的同一份代码——但 `launch` 不能在顶层导入 `server`，所以把这两个纯函数搬进一个不依赖 `server` 的模块（例如 `reader3_app.ports`），`server` 改为从那里导入；端口优先级的扩展（加「绑定里记住的端口」一级）只在那里改一次
- **验收（种子）**:
  - `reader3 launch --help` rc=0，列出三个参数；`reader3 --help` 提到 `launch`
  - `reader3 ./launch`（当前目录真有一个叫 `launch` 的文件）仍按 EPUB 路径处理；只有**裸的** `launch` 是子命令（§6 Q9 的边界）
  - `reader3 launch --port abc` 与 `READER3_PORT=abc reader3 launch` 的报错与 `reader3-server` 同文、rc=2（同一个 `_parse_port`）
  - `reader3 launch --index x` / `--migrate x` → 用法错，rc=2，不起服务
  - `server.resolve_port` / `_parse_port` 的现有测试零改动全绿（搬家不改行为）
  - 测试矩阵：待 /tdd-guardian:design-tests

### WI-2: 数据家解析器

- **目标**: 按[数据家 ADR](../../../adr/0017-data-home-resolution.md)的规则，为 `reader3 launch`、`reader3 <epub>`、`reader3 --index`、012 的 `--migrate*`、设置页（经服务进程）解析出**同一个**书库目录与**同一份**设置文件，并在启动前打印。规则（含规则 3 首跑全表、规则 6 入口分段顺序 S1–S5）、绑定文件的位置 / 发布协议 / 读时校验 / schema **只在 ADR 里定义**，本 WI 只写落点与验收
- **涉及文件**:
  - 新模块 `src/reader3_app/data_home.py`：**只依赖标准库**（绑定锁用 `fcntl`，POSIX，§2.2）；一个解析函数，产出 `DataHome(books_dir, settings_path, source)`，全部绝对路径；外加绑定文件的读写（含 WI-5 的端口记忆字段）
  - `src/reader3_app/reader3.py` `main`：argparse 之后按 ADR 规则 6 走 S1（解析）→ S2（命令自身校验）→ S4（写绑定）→ S5（写环境变量、进原有分支）；`main` 今天就在调用时读 `READER3_BOOKS_DIR`，下游代码不改
  - `src/reader3_app/launch.py`：同上，多 S3（WI-5）；S5 才惰性 `import reader3_app.web.server`
  - **`reader3-server` 薄包装**（§6 Q14）：`[project.scripts]` 的 `reader3-server` 改指例如 `reader3_app.launch:serve_main`，**脚本名不变**。它走同一套 S1–S5，**不调用 `server.main()`**——`server.main` 在 `server` 导入（导入期 `makedirs`）之后才 `resolve_port`、再让 `uvicorn.run` 自己绑端口，顺序正是规则 6 要消灭的。端口被占时 `serve_main` 报错退出（不复用：它没有窗口可开）。薄包装所在模块**顶层不得导入 `web.server` 或 `ai.config`**。单纯 `import reader3_app.web.server`（TestClient、全部现有单测与契约测试）**不触发解析器**，导入期行为一字不变
  - `tests/unit/conftest.py`（不在冻结集）：加第四道 autouse 栅栏——删除继承的 `XDG_CONFIG_HOME`，把 `HOME` 与 `READER3_BINDING` 指到每个测试的临时目录；同步更新该文件头部「三道栅栏」的说明。没有它，任何未显式设所需路径的入口测试都会读写真实用户的绑定。`tests/conftest.py` 冻结，不能放那里——与第三道栅栏同一个理由，`tests/contract/conftest.py` 若有入口测试也照抄注册
- **验收（种子）**:
  - **导入顺序**：在子进程里跑到 S4 结束后断言 `reader3_app.web.server` 与 `reader3_app.ai.config` 都不在 `sys.modules`；`launch.main`、`serve_main`、`reader3.main` 各一条；另加一条：在全新子进程里只 `import` 薄包装所在模块，断言这两个模块仍不在 `sys.modules`（顶层导入约束）
  - **分段顺序**：在 S2 注入失败（EPUB 不存在、索引目标不存在、`--port abc`）→ rc≠0，绑定不存在，**没有新建任何目录**，`web.server` 未导入。端口被占而拒绝的那一条依赖 S3，归 WI-5
  - **规则表驱动**（每行一个隔离 `HOME` ＋ 临时 cwd）：ADR 规则 3 的表**每行一条**（含「只有 `~/Reader3/` 有书库」「cwd 就是 `~/Reader3/`」两行）；规则 1：`reader3.main` 只显式 `READER3_BOOKS_DIR` → 不读不写绑定，`launch` 两条都显式 → 同；部分显式且无绑定 → 缺的一半按规则 3 取、**不写绑定**；有绑定 → 换 cwd 结果不变
  - **候选校验**（ADR b.1）：cwd 下一个不含书文件的 `*_data` 目录、或一份坏 JSON 的 `config/ai_settings.json` → 非零退出并指名该文件，**不写绑定**，也**不**退回 `~/Reader3/`
  - **worktree 拒绝**（b.2）：cwd 是 `.claude/worktrees/<name>/` 下的 git worktree，且其中有通过校验的书库/设置对 → 非零退出、要求显式路径或手写绑定，**不写绑定**
  - **并发首跑**（c.1）：两个子进程在同一隔离 `HOME` 下同时首跑（用屏障对齐到取锁前一刻）——选定相同 → 两者 rc=0、绑定一份、内容即该选定；选定不同（不同 cwd）→ 恰一者成功，另一者 rc≠0 且说明冲突，绑定内容是成功者的选定，**未被覆盖**
  - **发布崩溃注入**（c.1）：在 `mkstemp` 之后、`os.replace` 之前杀掉进程 → `binding.json` 不存在，下一次运行照常首跑并成功（残留临时文件不影响）；在 `os.replace` 之后杀 → 绑定完整可读。任何时刻并发读者读到的要么是「无绑定」，要么是完整合法的绑定
  - **首跑 → 停 → 再跑，中间不存设置**（c.2）：首跑选定 `~/Reader3/`，起服务后停掉，不打开 `/settings`；第二次运行 `source == "binding"`、rc=0、算出的 `instance_id` 与第一次相同（设置文件此时仍不存在）
  - **绑定读时校验**（c.2 / c.3）：坏 JSON、未知键、缺键、相对路径、`schema` 大于 1、权限宽于 `0600`、`books_dir` 不存在、`settings_path` 存在但是目录——每种各一行 → 非零退出并指名文件与原因（权限一行须含 `chmod 600` 修复命令），**不回退到 cwd**；`settings_path` 不存在且父目录也不存在 → 合法
  - **不搬数据**：S1 与所有拒绝路径跑完后，所选与未选候选目录的文件清单与 mtime 都不变；成功的 `reader3 <epub>` 只在所选书库下新增那一本书的 `{name}_data/`（及 ADR-0015 的锁目录），所选家之外不新建任何东西。（真实导入 / 索引会改书库，「mtime 不变」只对解析与拒绝路径断言）
  - **打印**：输出含两条绝对路径、`source` 与绑定文件路径；设置文件存在时输出中**不出现其任何内容**（往设置文件里放一个哨兵 key，断言 stdout / stderr 不含它）
  - **跨入口一致**：同一隔离 `HOME` 下，先在目录 A 跑 `reader3 <epub>`，再在目录 B 调 `launch` 的解析阶段，两次解析结果相等，且 B 下没有新建 `books/`
  - 现有调用 `reader3.main` 的单测（都显式设了 `READER3_BOOKS_DIR`，按规则 1 即「所需路径全显式」）零改动全绿
  - 测试矩阵：待 /tdd-guardian:design-tests

### WI-3: `/api/health` 实例身份字段

- **目标**: `GET /api/health` 的响应体新增**恰好一个**字段（建议名 `instance_id`，§6 Q15），值是一个不透明的哈希，输入为：解析后的书库目录绝对路径、设置文件绝对路径、认证模式（`READER3_TOKEN` 是否启用，**不含令牌本身**）、构建身份。**传哈希不传路径**：`/api/health` 令牌豁免，路径进响应体等于把本地用户名与目录结构交给任何能访问该端口的东西
- **实例身份的语义**（维护者裁定 D2，2026-10-02）：**「同一个安装」**。身份在进程启动时算一次，**进程生命周期内固定**；构建变了必须重启，不热更新。注意 `web.vite_assets._load_manifest` 按 mtime 重读 Vite manifest（重建后运行中的服务会换用新资源），但身份**不**跟着变——于是重建后 `launch` 用磁盘上的新构建算出的值与运行中的旧值不等，按 WI-5 拒绝复用并提示重启。这是安全方向的结果，接受
- **涉及文件**:
  - `src/reader3_app/data_home.py`：一个纯函数 `instance_identity(books_dir, settings_path, auth_enabled, build_id) -> str`，返回 SHA-256 覆盖规范化 JSON 的**完整** 64 位十六进制摘要（不截断）。两条路径进哈希前在函数内部一律 `os.path.realpath`——规范化归这个函数，不归调用方。`launch` 与服务**调同一个函数**，两边算法不会漂
  - `src/reader3_app/web/routers/health.py` / `server.py`：服务启动时算一次并缓存；`/api/health` 只读缓存值——**探针仍不碰磁盘**（`tests/contract/test_health_route.py` 模块的硬要求）
  - 构建身份（§6 Q15 修订 1–2，按 D2 重写）：标识**整个被服务的安装**，由三部分组成，启动时算一次：
    1. **源码指纹**，按安装方式二选一：
       - **可编辑安装**（`importlib.metadata.distribution("reader3")` 的 `direct_url.json` 里 `dir_info.editable` 为真）：`git rev-parse HEAD` ＋ 脏标志（`git status --porcelain` 非空即脏），git 一律以**包自身的源码位置**为锚（`git -C <reader3_app 包目录>`），**从不**用用户的 cwd。不能用 `RECORD`：可编辑安装的 `RECORD` 只列 `.pth`、启动脚本与 dist-info 自身（本仓 `.venv` 实测：`direct_url.json` 为 `{"dir_info":{"editable":true}}`，`RECORD` 里没有任何 `reader3_app/` 文件）
       - **wheel 安装**（非可编辑）：已安装分发 `RECORD` 文件字节的哈希（逐文件列出包内全部 Python、模板与静态文件的哈希）
       - **拿不到**（无分发元数据，例如 `PYTHONPATH=src` 直接跑；可编辑但包目录不在 git 里或没有 `git`）→ 构建身份记为「未知」，`launch` **拒绝复用**任何实例（含另一个同样「未知」的），按 WI-5 的「另一个 reader3 实例」路径报错
    2. `_package_version()`：取已安装分发的元数据版本——`uv run` 下的可编辑安装今天答 `1.5.0`（`.venv` 实测），只有完全没有分发元数据时才是 `0+unknown`。两种情况它都不随提交变化，单靠它分不清两次构建（§6 Q11 因此被本 WI 吸收）
    3. Vite 构建 manifest（`static/dist/manifest.json`）字节的哈希；**不存在时**以固定标记 `absent` 参与哈希。它只让「有 / 无 manifest」两种构建身份不同；manifest 缺失时页面能不能用是另一回事——`_load_manifest` 对缺失文件直接 `stat()` 抛错，`GET /` 会 500——由 WI-4 的「可用」判定拦住，不在身份里处理
  - 脏工作树的已知局限：脏标志只说「脏」，不说脏在哪；同一 HEAD 上两份不同的未提交改动算出同一个指纹。接受——只发生在开发者手里，最坏结果是复用了一个代码略旧的本地实例，不涉及数据家（数据家另有两个独立输入）
  - `tests/contract/test_health_route.py`：**同一个 commit** 里加 `instance_id` 的断言，既有三条用例零改动。这就是 ADR-0011 意义上的「快照步骤」：**`routes.snapshot` 不变**——ADR-0011 的快照只比路由集合，响应字段归 layer-2 契约测试；冻结期允许加字段，不允许改名改语义
- **验收（种子）**:
  - 响应体键集合恰为 `{status, version, instance_id}`；`instance_id` 是 64 位小写十六进制串（完整 SHA-256）
  - **区分性**（性质测试，在**规范化后的**输入上陈述）：`(realpath(books_dir), realpath(settings_path), auth_enabled, build_id)` 四元组相等 ⇔ 值相等（跨进程、跨 cwd）；四元组任一分量改变 → 值改变
  - **路径规范化**：同一目录经符号链接、相对路径、尾斜杠三种写法传入 → 规范化后四元组相同 → 值相同（这是上一条的特例，不是例外）
  - **构建身份随安装变**：可编辑——在一个临时 git 仓库里，改一个 Python 文件并提交 → 变；只改不提交 → 脏标志翻转、变；**从另一个 git 仓库的 cwd 里调用 → 不变**（锚在包目录）；wheel——伪造一个 `RECORD` 改一行哈希 → 变；manifest 删除 → 变且 `/api/health` 照常 200
  - **未知 → 拒绝复用**：注入「无分发元数据」与「可编辑但无 git」两种环境 → 构建身份为「未知」，WI-5 对同端口的同数据家实例也拒绝复用
  - **进程内固定**：起服务后改一个被跟踪的文件并提交 → `/api/health` 的 `instance_id` 不变；`launch` 对它拒绝复用，消息提示重启
  - 响应体不含书库路径、设置路径、用户名或令牌的任何子串（把这些值做成哨兵断言）
  - 书库目录不存在时仍 200（现有 `test_不依赖书库目录` 零改动全绿）；两次请求之间删掉书库目录，`instance_id` 不变（证明不是每次请求重算）
  - 测试矩阵：待 /tdd-guardian:design-tests

### WI-4: 起服务 ＋ 就绪探测 ＋ 启动失败报错

- **目标**: 前台起服务（同进程 `uvicorn.Server`，§6 Q4），用 S3 已持有的 socket，**「活着」且「可用」**之后才宣布就绪并进入 WI-6 开窗口；生命周期、取消与退出码按下表，一个不漏
- **涉及文件**: `src/reader3_app/launch.py`；S5 之后惰性引用 `server.app`、`server.DEFAULT_HOST`、`web.vite_assets`
- **复用**：`/api/health` 是 007 为「Phase 5 的 `reader3 launch`」预留的探针（`routers/health.py` 与 `server.py` 令牌豁免注释都写明了这个用途），它故意不碰磁盘、对空库也答 200——所以它只能证明「活着」，证明不了「可用」
- **共用的健康判定**：WI-4 与 WI-5 调**同一个**判定函数（例如 `classify_health(resp, expected_id)`），返回 `match` / `other-reader3` / `foreign`：`match` ＝ HTTP 200、JSON 对象、`status == "ok"`、`instance_id == expected_id`；`other-reader3` ＝ 前三条成立而 `instance_id` 缺失或不等；其余皆 `foreign`。两处不得各写一份
- **`--timeout S`**：缺省 **30** 秒；必须是 `0 < S ≤ 600` 的数，否则用法错 rc=2（与 `--port abc` 同形）。它约束从 STARTING 到 READY 的总时长；每次探测请求另有 2 秒单次上限，所以一个接受连接却永不应答的探针也不能把总时长拖过 `S`
- **状态**（失败一律一行人话、无 traceback，同 `reader3` 其余出口的 `SystemExit(msg)` 形状）：

  | 状态 | 进入条件 | 失败 / 取消 → 去向 |
  |---|---|---|
  | S1–S4 | 数据家 ADR 规则 6；S3 绑不上端口 → 交 WI-5 | 各自的拒绝，rc 见下 |
  | PREFLIGHT | S5 导入之后、起服务之前：`vite_assets._load_manifest()` 成功，且 `ENTRY_SOURCES` 里每个页面的 `css_files` 能解析 | 「前端构建缺失或损坏」＋ manifest 路径，rc=1，不起服务 |
  | STARTING | `uvicorn.Server.serve(sockets=[S3 的 socket])` 运行中；lifespan startup（含 `_startup_scan_books`）未完成 | lifespan 失败（`started` 始终为假、`serve` 返回）→ rc=1；超时 → 停服务，rc=1 |
  | ALIVE | 健康判定为 `match` | 超时 → 停服务，rc=1 |
  | USABLE | `GET /` 答 200（证明模板与 Vite 资源可用；`/` 渲染 `vite_css('library')`） | 非 200 → 「服务已起但阅读器不可用」＋ 状态码，停服务，rc=1 |
  | READY | 打印「Reader3 is ready at http://127.0.0.1:{port}/」，调打开器（WI-6） | — |
  | STOPPING | READY 之后收到 SIGINT / SIGTERM，或 READY 之前被取消 | 关停有界（5 秒宽限，超过即放弃等待并以既定退出码退出） |

- **退出码**：0 ＝ READY 之后由用户停止、或成功复用（WI-5）；1 ＝ 一切运行期失败（数据家拒绝、端口拒绝、PREFLIGHT / lifespan / 超时 / 不可用）；2 ＝ 用法错；130 ＝ READY 之前被 SIGINT / SIGTERM 取消。**rc=0 不是自动的**：uvicorn 0.38 的 `Server.capture_signals` 在主线程里接管信号、关停后 `signal.raise_signal` 把捕获的信号重新抛出，进程会以 `KeyboardInterrupt` / 默认 SIGTERM 处置结束——`launch` 必须自己拥有信号处置（例如在工作线程里跑 `serve`，uvicorn 在非主线程不装处理器），由测试锁住退出码。S3 自持 socket 也意味着 uvicorn 自己的绑定失败分支（`create_server` 抛 `OSError` → `sys.exit(1)`）走不到
- **验收（种子）**:
  - 空闲端口 ＋ `--browser none`：就绪后打印就绪行；之后 `GET /` 得 200
  - **lifespan 卡住**：注入一个 startup 永不返回的 app → `--timeout 1` 后 rc=1，端口重新可绑，总耗时 < 1 ＋ 5 秒宽限
  - **lifespan 失败**：注入一个 startup 抛错的 app → rc=1，一行摘要，无 traceback
  - **探针挂起**：注入一个接受连接但永不应答 `/api/health` 的 app → rc=1，且总耗时受 `--timeout` 约束
  - **身份不等**：注入一个答 200 但 `instance_id` 不同的探针 → 视为未就绪（不对别人的服务宣布就绪）；`status != "ok"` 同
  - **不可用**：manifest 缺失 → PREFLIGHT 拒绝，rc=1，消息含 manifest 路径；manifest 在但 `/` 答 500（注入）→ rc=1
  - **信号**：READY 之后 SIGINT → rc=0、端口释放；READY 之前 SIGINT → rc=130、端口释放；SIGTERM 同两条
  - `--timeout 0` / `-1` / `abc` / `601` → rc=2，不起服务
  - 就绪前绝不调用打开器（打开器可注入，断言调用次数为 0）
  - 真连回环的用例进 `EXPECTED_EXEMPTIONS`（见 §3 表下注）
  - 测试矩阵：待 /tdd-guardian:design-tests

### WI-5: 端口冲突：身份复用 / 拒绝 / 记住端口

- **目标**: S3 绑不上目标端口时**不悄悄换端口、不结束或替换任何进程**（§6 Q2 裁定），按 WI-4 的共用健康判定分三路：

  | 占用者 | 判定 | 行为 |
  |---|---|---|
  | 同一实例 | `match`（期望值是 `launch` 用自己解析出的数据家、认证模式与构建身份算出的值），且 `GET /` 答 200 | **复用**：不起新服务，只做 WI-6 开窗口，rc=0；打印「已在运行，复用」 |
  | 另一个 reader3 实例 | `other-reader3`；或 `match` 但 `GET /` 非 200 | **拒绝**：rc=1。说明「端口上是另一个 Reader3 实例（书库、设置文件、认证模式或构建不同；构建刚变过的话请重启它）」或「实例在但阅读器不可用」，打印本次的数据家路径供对照，并给出两条出路：停掉那个进程；或 `--port N` / `READER3_PORT` |
  | 别的东西 / 不应答 | `foreign`，或连不上却绑不了 | **拒绝**：rc=1，指名端口与同样两条出路 |

- **端口记忆**：写入时机与条件见数据家 ADR f，端口优先级见 ADR g——本 WI 只实现
- **涉及文件**: `src/reader3_app/launch.py`；`src/reader3_app/data_home.py`（绑定文件读写）
- **验收（种子）**:
  - 先用 `reader3-server`（同一隔离数据家、同一构建）在空闲端口起一个实例 → `reader3 launch --port 同一个 --browser none` rc=0、进程内没有创建 `uvicorn.Server`、打印「复用」
  - **四个身份输入各自换一个**（另一个书库目录、另一份设置文件、设了 `READER3_TOKEN`、另一个构建身份）各起一个占位实例 → 每种都 rc=1，消息含两条出路；**这是「版本相同但书库不同」的假成功不再发生的证明**
  - 端口被一个不说 HTTP 的 socket 占着 → rc=1，消息含端口号与 `--port`
  - 端口被一个答 404 的 HTTP 服务占着 → rc=1，同上
  - **拒绝的 `launch` 不留绑定**（自 WI-2 移来：依赖 S3）：无绑定时，端口被另一个实例占着而拒绝 → rc=1，绑定文件不存在，所选书库目录未被创建
  - 任何拒绝路径上**没有任何 `bind` 到其他端口**，也**没有任何对外发信号**（打桩 `os.kill` 断言零调用）
  - 端口记忆：`launch --port N` 后再跑不带 `--port` 的 `launch` → 用 `N`；`READER3_PORT=M launch` 之后再跑不带参数的 → 仍用 `N`；拒绝路径**不**写端口；**全显式路径**（两个 `READER3_*` 都设）下：绑定里记着 `N` 时不带 `--port` 的 `launch` 用 8123 而不是 `N`，带 `--port K` 成功后绑定文件字节不变
  - 真连回环的用例进 `EXPECTED_EXEMPTIONS`；占位实例优先用注入的假探针，四路身份拒绝里只留一条真起服务
  - 测试矩阵：待 /tdd-guardian:design-tests

### WI-6: 打开窗口

- **目标**: `--browser app`（默认，§6 Q10）：找到 Chromium 系浏览器（Chrome / Chromium / Edge）就以 `--app=<origin>/` 起一个独立窗口；找不到退回默认浏览器并说一句为什么。`default`：`webbrowser.open`。`none`：只打印 URL
- **涉及文件**: `src/reader3_app/launch.py`（浏览器探测表按平台：macOS `open -na <App> --args --app=…`，Linux PATH 上的可执行名；**不做 Windows**，§2.2——探测表是常量，可注入）
- **打开的 URL 只有一个来源**：数据家 ADR g 的 origin 规范形 ＋ `/`。`launch` 不往 URL 上挂任何查询参数（`?token=` 见 §6 Q8）
- **验收（种子）**:
  - 打开器注入后：`app` 模式且探测表命中 → 调用参数里恰好一个 `--app=http://127.0.0.1:{port}/`；未命中 → 退回 `webbrowser.open` 且 stderr 有一句说明
  - `none` 模式：零次调用
  - 复用路径（WI-5）也走同一个打开器，参数相同
  - 打开器自身抛错不让服务退出：服务照跑，stderr 打印 URL 让用户手动打开
  - 测试矩阵：待 /tdd-guardian:design-tests

### WI-7: 已安装 wheel 冒烟 ＋ 文档 ＋ 台账

- **目标**: 证明「装好就能 `reader3 launch`」在真 wheel 上成立，不只是在源码树里
- **涉及文件**:
  - packaging lane（`tests/integration`，`-m slow`）：在现有已安装 wheel 冒烟的同一套 venv 里加一条——沙箱环境（见下）、空 cwd，`reader3 launch --port <空闲> --browser none`，等就绪行，`GET /` 200，断言书库落在 `$HOME/Reader3/books`，SIGINT，rc=0
  - `scripts/smoke_installed_wheel.py`（不在冻结集）：`_clean_env` 今天只剥 `PYTHONPATH`、其余全继承，只隔离 `HOME` 挡不住继承来的 `XDG_CONFIG_HOME` / `READER3_BINDING` / `READER3_AI_SETTINGS`。改为先剥掉**全部** `READER3_*` 与 `XDG_*`，再注入沙箱里的 `HOME`、`XDG_CONFIG_HOME`、`READER3_BINDING` 与本用例需要的路径（数据家 ADR a）
  - 文档（实施分支里改；任务书落地时不碰）：`CLAUDE.md`「Core Commands」；`docs/storage-and-data-locations.md`（书库与设置文件的位置改为指向数据家 ADR，**并新增「改绑数据家」一节**写 ADR e 的安全步骤）；`docs/technical-detail.md`「Recent updates」加一条（数据家、绑定文件位置、`reader3 launch`，按该文件的 Update Rule）；**发布说明**写在合入 PR 描述里（仓库没有 CHANGELOG）：仓库外跑 `reader3 <epub>` 的书改落 `~/Reader3/books` 或绑定处（ADR Negative 第一条）、绑定文件位置、改绑步骤的链接、仅 POSIX
  - `docs/feature-ledger.md`：合入后的回写里新增或修改 `cli: reader3` 所在的行（台账规则：只记已合入的），`python3 scripts/build_feature_ledger.py` 重建 html
- **验收（种子）**:
  - packaging lane 绿，新用例在**未装 `[semantic]` extra** 的 venv 上也绿（`launch` 不得在导入期拉 ML 依赖）
  - 冒烟结束后沙箱之外没有任何新文件（断言真实 `~/.config/reader3/`、`$XDG_CONFIG_HOME/reader3/` 与 `~/Reader3/` 未被创建或修改）；父进程预先设了 `XDG_CONFIG_HOME` 与 `READER3_BINDING` 指向哨兵目录时同样成立
  - 台账 `--check` rc=0
  - 测试矩阵：待 /tdd-guardian:design-tests

---

## 4. 出口闸

全部满足才算完。「证据位置」在核验时填，现在全部是占位。

| # | 门槛 | 判据 | 证据位置 |
|---|---|---|---|
| 1 | 全部 lane 在合并头上绿 | `.claude/tdd-guardian/config.json` 里**每一条** lane（不写死条数），带 `env -u FORCE_COLOR`；`/tdd-guardian:gate push` | _待填_ |
| 2 | 类型检查 | `uv run mypy src/` 干净 | _待填_ |
| 3 | lint | `uv run ruff check src/ tests/ scripts/` 干净（不跑 `ruff format`）；`scripts/lint_*.py` 全部 rc=0 | _待填_ |
| 4 | router 体量 | `python3 scripts/check_router_size.py` rc=0（`launch.py` / `data_home.py` 不声明路由；`health.py` 只多一个字段） | _待填_ |
| 5 | 路由集合零改动 ＋ health 只加不改 | `tests/contract/routes.snapshot` 在 `master...HEAD` 上 diff 为空；`test_health_route.py` 既有用例零改动，只新增 `instance_id` 的断言，且与字段在同一个 commit（ADR-0011 加法规则） | _待填_ |
| 6 | 现有 CLI 参数面不变 | `reader3 <epub>`、`reader3 --index`、012 的 `--migrate*`、`resolve_port` 的单元测试零改动全绿（WI-1 / WI-2） | _待填_ |
| 7 | Phase 5 验收「单命令进入阅读」 | WI-7 的已安装 wheel 冒烟绿 ＋ 维护者在一台真机（macOS 或 Linux）上的人工 smoke，**全部五步**记 §8（每步一张截图或一段终端输出，证据形状同 007 §8.1）：① 在仓库以外的任意目录 `reader3 launch`，输出含数据家路径与就绪行，窗口自动打开；② 在窗口里打开一本书、翻到第二章（书库至少一本书；空库先 `reader3 <epub>` 导入一本）；③ 关闭窗口，终端里服务仍在；④ 另开终端、换一个目录再 `reader3 launch` → 打印「复用」、窗口回到同一 origin，上次的阅读位置 / 偏好仍在；⑤ 回到第一个终端 Ctrl-C → rc=0，端口释放。空库 200 ＋ 一张截图**不算**「进入阅读」 | _待填_ |
| 8 | 「版本切换不撕裂」的 CLI 半边 | WI-5 的四路身份拒绝测试绿；§8 写一行指向 WI-20 缓存清理裁定的证据（§2.3 末行；未裁则 M5 不关闭，本分支仍可合入） | _待填_ |
| 9 | 数据家 ADR | [ADR-0017](../../../adr/0017-data-home-resolution.md) ~~已在 `docs/adr/` 落地~~（⬛ 2026-10-02 已落地，Proposed）；本分支合入的同一 PR 里：Status 转 Accepted、`Current compliance` 更新、`Confirmation` 由「计划中」改指 WI-2 的真实测试文件 | _待填_ |
| 10 | 出网豁免名单 | `EXPECTED_EXEMPTIONS` 的增量恰为 WI-4 / WI-5 新增的真连回环用例，逐条在 PR 描述里列出 | _待填_ |
| 11 | 合入前 CI 全绿 | PR 上 `tests.yml` 与 `lint.yml` 全绿后才合入 | _待填_ |
| F | 冻结区零字节改动 | 冻结集 8 条路径 `git diff --stat master... -- <paths>` 为空（清单定义处：`soak-log.md`「`suite_hash` 的取法」与 `scripts/soak_run.py` 的 `HASH_COVERED_PATHS`） | _待填_ |
| R | 红灯必查根因 | 同 018 §4 门槛 R | _待填_ |

- 不得设 `TDD_GUARD_BYPASS`。
- 015 的 PWA 半边有自己的验收（WI-20 第 1–8 条），**不在本表**；M5 整体关闭要两边都过，汇总写在进度盘，不写在这里。

---

## 5. 风险

- **悄悄换端口**：最省事的实现是「8123 被占就挑一个空闲端口」，它会把用户的对话、偏好和已安装的 PWA 全部「弄丢」（数据家 ADR g）。缓解：WI-5 拒绝路径 ＋「任何路径都不绑第二个端口」的断言 ＋ 端口记忆。
- **复用了一个服务着另一个书库的实例**（rev 0 只比版本号时的假成功）：缓解：WI-3 实例身份 ＋ WI-5 四路拒绝测试。
- **解析器晚于 `server` 导入**：导入期 `makedirs` 会在错误的地方建空书库，而且普通测试看不出来。缓解：WI-2 的导入顺序测试约束 `launch.py` / `data_home.py` / `reader3.py` 的顶层导入。
- **测试或冒烟写真实用户的绑定**：任何未显式设所需路径的入口测试都会；只隔离 `HOME` 不够，继承来的 `XDG_CONFIG_HOME` / `READER3_BINDING` 照样指向真实位置。缓解：`tests/unit/conftest.py` 第四道栅栏（删 `XDG_CONFIG_HOME`）；WI-7 剥全部 `READER3_*` / `XDG_*` 再注入，及「沙箱之外无新文件」断言。
- **行为改变冲击现有用户**：在仓库外不设环境变量跑 `reader3 <epub>` 的人，书将进绑定处而不是 cwd。缓解：首次运行优先绑定 cwd 的现成书库；发布说明写明；数据家 ADR 的 Negative 已记。
- **`instance_id` 被当作指纹（接受的残余风险，§6 Q15 修订 5）**：值**不是秘密**。能读到 `/api/health` 的本机进程可以离线枚举猜测的路径（常见用户名 × `~/Reader3`、仓库位置等）并比对哈希，从而确认书库位置。限制它的是：端口只绑 `127.0.0.1`、Host 闸（`web.server.RequestGuardMiddleware`）挡掉 DNS rebinding——所以只有**本机进程**能问到这个值，而本机进程本来就能直接列目录。据此接受、不加盐；加盐的代价见 §6 Q15。
- **构建身份误判**：只比版本与前端产物会把「同版本同 dist、不同 Python 或模板」的两个 worktree 判成同一构建；对可编辑安装取 `RECORD` 也一样（它不列包内文件）。缓解：WI-3 按安装方式取指纹（可编辑 → 锚在包目录的 git HEAD ＋ 脏标志；wheel → `RECORD`）；拿不到即拒绝复用。
- **重建后复用旧进程**：身份进程内固定，而 `vite_assets` 会热读新 manifest。缓解：重建后 `launch` 算出的新值与旧进程不等 → 拒绝并提示重启（WI-3 / WI-5，D2）。
- **「活着」当「可用」**：`/api/health` 不碰磁盘，manifest 缺失时它照样 200 而 `/` 500。缓解：WI-4 的 PREFLIGHT ＋ USABLE 两态；WI-5 复用前同样要求 `GET /` 200。
- **开发者在 worktree 里首跑把全局的家绑走**：缓解：数据家 ADR b.2——`.claude/worktrees/` 下从不自动选定；WI-2 worktree 拒绝测试。
- **出网豁免名单膨胀**：WI-4 / WI-5 每加一条真连回环用例就在栅栏上开一个洞。缓解：注入探针优先，§4 门槛 10 逐条列出。
- **`launch` 被解析成 EPUB 路径**：今天的 argparse 就是这样。缓解：WI-1 先特征化再分派。
- **与 012 WI-6 改同一个 `main()`**：缓解：分派放在 argparse 之前、解析插在 argparse 之后，不碰 012 的 flag；开工当天复核（§1）。
- **令牌模式下 UI 打不开**：缓解：§6 Q8（D3：在有覆盖首次加载 `/` 的浏览器认证之前一律拒绝）。
- **导入期拉 ML 依赖**：缓解：WI-7 的无 extra venv 冒烟。

---

## 6. 开放问题

按「挡住实施的先后」排序。**⚑ = 真正有后果的取舍**（定了之后改的代价高，或直接影响用户数据）；其余有明显默认值。

| Q | 问题 | 挡哪个 WI | 推荐 / 裁定 | ⚑ | 状态 |
|---|---|---|---|---|---|
| Q1 | CLI 侧能否在 014 合入前开 | 开工时间 | **裁定：不提前**，按 §9.1 在 014 之后开。若裁定提前，改的是 §9.1 与进度盘，不是本文 | ⚑ | ✅ 已裁（2026-10-01 决定 B：按推荐） |
| Q2 | 端口被占时怎么办 | WI-3 / WI-5 | **已裁（2026-10-02，维护者，经 reader-delegator 转达）**：只有 `/api/health` 返回的不透明实例身份（书库目录 ＋ 设置路径 ＋ 认证模式 ＋ 构建身份的哈希；传哈希不传路径）匹配时才复用；否则拒绝，说明不匹配并给出出路（停掉对方，或 `--port` / `READER3_PORT`）；从不结束或替换进程；从不悄悄换端口；记住显式选择的端口 | ⚑ | ✅ 已裁 |
| Q3 | origin 规范形用 `127.0.0.1` 还是 `localhost` | WI-5 / WI-6 / 数据家 ADR g | **`127.0.0.1`**：与 `server.DEFAULT_HOST`、e2e、CLAUDE.md、存储文档一致；现有用户的浏览器数据已经在这个 origin 下 | ⚑ | ✅ 已裁（2026-10-01 决定 B：按推荐） |
| Q4 | 同进程 `uvicorn.Server` 还是子进程 `reader3-server` | WI-4 | **同进程**：一个进程、Ctrl-C 自然传到、不会留孤儿 |  | ✅ 已裁（2026-10-01 决定 B：按推荐） |
| Q5 | 前台还是后台守护（含 `reader3 stop`） | WI-4 | **前台**：关终端即停。YAGNI |  | ✅ 已裁（2026-10-01 决定 B：按推荐） |
| Q6 | 数据目录的位置与解析 | WI-2 | **已裁（2026-10-02）**：服务导入与建目录之前解析出**一个**数据家，launch / 导入 / 索引 / 设置共用；显式 env / CLI 路径胜出；首次运行若 cwd 有现成书库/设置对则绑定其绝对路径，否则缺省 `~/Reader3/`（维护者选：可见，不用 OS 应用数据目录）；之后与 cwd 无关；多个候选则停下要求显式路径；启动前打印选定路径；从不静默迁移、合并或另建替代书库。规则记入 [ADR-0017](../../../adr/0017-data-home-resolution.md)（⬛ 2026-10-02 落地，Proposed） | ⚑ | ✅ 已裁（ADR 子问题 a–f 于 2026-10-02 裁定，b / c / d / f 经 Codex 修订） |
| Q7 | `/api/health` 要不要加字段 | WI-3 | **被 Q2 裁定推翻**：恰好加一个不透明身份字段（加法，ADR-0011 允许）。`routes.snapshot` 不变；契约测试同 commit 更新（§4 门槛 5） |  | ✅ 随 Q2 |
| Q8 | 设了 `READER3_TOKEN` 时 `launch` 怎么办 | WI-4 / WI-6 | **拒绝并说明**（令牌模式今天只适合 CLI / 反代，UI 带不上令牌）。~~开工当天若前端已带令牌，改为放行~~（⬛ 2026-10-02 维护者裁定 D3：「前端 `fetch` 带上令牌」不够——**一直拒绝，直到有一套也覆盖首次加载 `/` 的浏览器认证**；放行要另行裁定）；**不**把令牌挂在 URL 上（会进浏览器历史）。认证模式是身份输入之一，开关令牌会让复用失败——这是期望行为 |  | ✅ 已裁（2026-10-01 决定 B；2026-10-02 D3 收紧放行条件） |
| Q9 | 子命令 `reader3 launch` 还是新入口点 `reader3-launch` | WI-1 | **子命令**；只在第一个参数**恰为** `launch` 时分派，`./launch` 仍是文件 |  | ✅ 已裁（2026-10-01 决定 B：按推荐） |
| Q10 | `--browser` 默认值；要不要 e2e | WI-6 / WI-7 | 默认 **`app`**（找不到 Chromium 系就退回默认浏览器）；**不加 e2e** |  | ✅ 已裁（2026-10-01 决定 B：按推荐） |
| Q11 | ~~源码树里版本号恒为 `0+unknown`~~ 版本号不随提交变化，怎么比 | WI-3 | （⬛ 2026-10-02 更正前提：`uv run` 下的可编辑安装答 `1.5.0`，只有无分发元数据时才是 `0+unknown`，见 WI-3 第 2 部分。结论不变）**被 WI-3 吸收**：不再单比版本号；构建身份的组成见 WI-3（源码指纹 ＋ 版本号 ＋ Vite manifest，Q15 修订 1–2） |  | ✅ 2026-10-01 按 rev 0 推荐裁定，随即被 Q2 裁定吸收 |
| Q12 | 桌面壳 PoC 的触发条件在哪里看 | — | 不在本文：触发条件定义在[迁移计划 Phase 5](../plan-tech-stack-migration.md#phase-5--启动体验与远期桌面化) 本计划侧第 2 条（⬛ 2026-10-02 更正：~~ADR-0008 Revisit 一节~~没有这一条；ADR-0008 只记「不做」）；本分支不做任何准备工作 |  | ✅ 已裁（2026-10-01 决定 B：按推荐） |
| Q13 | service worker 作用域所需的路由或响应头归谁 | — | 归 **WI-20**（§2.3 第 2 行与观察） |  | ✅ 已裁（2026-10-01 决定 B：按推荐） |
| Q14 | `reader3-server` 是否也走数据家解析器 | WI-2 / WI-7 | **裁定：是**（= 数据家 ADR 子问题 a）：否则它是另一个家，`launch` 会因身份不同拒绝复用它。代价：`reader3-server` 的脚本目标改指薄包装（脚本名不变）；wheel 冒烟要隔离 `HOME` 或两条路径都显式注入。**修订**：薄包装所在模块顶层不得导入 `web.server` / `ai.config`，并纳入导入顺序测试（WI-2） | ⚑ | ✅ 已裁（2026-10-02，Codex 修订） |
| Q15 | 实例身份字段名与是否加盐 | WI-3 | **裁定：字段名 `instance_id`，不加盐**，输入为规范化 JSON。加盐要一个 `launch` 与服务都能读到的秘密，而显式注入路径的服务（e2e、CI）按规则 1 不读绑定，算不出同一个值。**修订**：(1) 构建身份标识整个被服务的构建——源码指纹（wheel 取已安装分发 `RECORD` 的哈希；可编辑取 git HEAD ＋ 脏标志；⬛ 2026-10-02 按 D2 细化：可编辑以 `direct_url.json` 的 `dir_info.editable` 判定、git 锚在包目录而非 cwd，身份进程内固定、构建变即须重启，见 WI-3）＋ 版本号 ＋ Vite manifest；拿不到指纹即拒绝复用；(2) manifest 缺失以 `absent` 标记参与哈希，不报错；(3) 一律用**完整** SHA-256 十六进制摘要，不截断；(4) 两个进程以同一函数内的 `realpath` 规范化路径；(5) 值不是秘密，本机进程可离线比对猜测的路径，由回环绑定 ＋ Host 闸限定为本机进程——作为残余风险接受（§5） |  | ✅ 已裁（2026-10-02，Codex 修订） |
| Q16 | 浏览器侧版本切换：WI-20 activate 清旧缓存 vs Phase 5「不撕裂」与迁移计划 A4 | — | **归 WI-20**，Phase 5 验收前必须裁定（§2.3 末行；协调方记在前端计划）。本文只引用 | ⚑ | 不在本文裁 |

数据家 ADR 的子问题（a 谁走解析器 = Q14；b cwd 书库判据与候选校验、worktree 不自动选定；c 绑定文件位置、发布协议、读时校验与 schema；d 绑定在命令自身校验之后才落盘；e 改绑的安全步骤；f 端口记忆只对绑定管理的启动生效；g origin，自本文 §2.3 迁入）已于 2026-10-02 全部裁定（a、e 照推荐，b、c、d、f 经 Codex 修订；同日计划评审后 c 由排他创建改为锁 ＋ 临时文件 ＋ `os.replace`，并补规则 1「所需路径」、规则 3 全表、规则 6 分段顺序），裁定文字定义在 [ADR-0017](../../../adr/0017-data-home-resolution.md) 的「子问题裁定」一节，不在此复述；对应测试落在 WI-2 / WI-5 的验收种子。

---

## 7. 欠账

本分支新立的欠账（兑付方指向后续分支的）。继承来的欠账不在这里，在 [009 表](./009-e2e-annotations.md#跨波欠账)（起草时指向 015 的行为零）。

| # | 欠什么 | 欠账方 | 兑付方 | 验收怎么查 | 状态 |
|---|---|---|---|---|---|
| — | _待实施时填_ | | | | |

---

## 8. 合入记录

_待填_：PR、合并 commit、合并头上各 lane 的结果、门槛 7 的人工 smoke 截图、门槛 8 两边证据链接、门槛 9 的 ADR-0017 转 Accepted 记录、门槛 10 的豁免清单。

### 红灯记录（门槛 R）

| 时间 | commit | 失败用例 | 根因 | 处置 commit |
|---|---|---|---|---|
