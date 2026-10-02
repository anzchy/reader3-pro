# ADR-0017: 书库与设置文件由一个「数据家」解析器统一定位——显式路径优先，首次运行绑定，之后与 cwd 无关

| 字段 | 值 |
|---|---|
| Status | Proposed——维护者 2026-10-02 裁定（015 §6 Q6，经 reader-delegator 转达；子问题 a–f 同日裁定，a、e 照起草推荐，b、c、d、f 按 Codex 修订，下文已是裁定后的文字）；在 `015-launch-experience` **CLI 半边**合入的同一 PR 里转 Accepted（[015 §4 门槛 9](../plans/20260816-tech-stack-migration/tasks/015-launch-experience.md#4-出口闸)） |
| Decision date | 2026-10-02 |
| Recorded date | 2026-10-02 |
| Record type | Prospective |
| Original rationale known | Yes——「书库与设置文件随 cwd 走」的现状没有找到当年的理由（Unknown）；本决定的理由见下 |
| Confidence | Medium——规则与子问题均已裁，尚无实现 |
| Current compliance | None——见 Migration Strategy |
| Evidence | 以符号定位（在 `master` `babaf59` 上核对，行号会漂）：`web.server.BOOKS_DIR`（读 `READER3_BOOKS_DIR`，缺省 cwd 相对 `books`，**导入时** `os.makedirs`）；`ai.config.DEFAULT_SETTINGS_PATH`（读 `READER3_AI_SETTINGS`，缺省 cwd 相对 `config/ai_settings.json`，导入时求值）；`reader3.main`（调用时读 `READER3_BOOKS_DIR`）；`docs/storage-and-data-locations.md`「Browser storage」（浏览器数据按 origin 隔离）；`tests/e2e/conftest.py` 的 `_server_env`（剥掉全部 `READER3_*` 后显式注入两条路径）；`scripts/smoke_installed_wheel.py`（只注入 `READER3_BOOKS_DIR`）；`.gitignore` 的 `/config/ai_settings.json` 一行（worktree 里的设置文件只能是手工拷入的，子问题 b.2）；`pyproject.toml` `[project.scripts]`（`reader3-server = "reader3_app.web.server:main"`，子问题 a） |
| Confirmation | 计划中：`tests/unit/test_data_home.py`（解析表驱动，含候选校验、worktree 拒绝、并发首跑、失败命令不留绑定、绑定读时校验）、`tests/unit/test_data_home_import_order.py`（三个入口——`reader3.main`、`launch.main`、`reader3-server` 薄包装——解析完成时 `reader3_app.web.server` 与 `reader3_app.ai.config` 不在 `sys.modules`）、packaging lane 的已安装 wheel 冒烟（015 WI-7） |

## Context and Problem Statement

- **Observed State**：书库目录与 AI 设置文件的缺省值都是**相对当前工作目录**的路径，且在模块导入时求值；`web.server` 导入时还会 `os.makedirs` 书库目录。四个入口——`reader3 <epub>`、`reader3 --index`、`reader3-server`、`/settings`（经 `reader3-server`）——各自按自己的 cwd 解析。
- **问题**：`reader3 launch`（015）是第一个被设计成「在哪都能一条命令进入阅读」的入口。照现状，在家目录下跑它会悄悄建一个空的 `~/books`、打开一个空书库，并在用户去 `/settings` 填 key 时**再造一份含明文 API key 的设置文件**。症状（书没了、key 要重填）不指向病因（cwd 不对）。
- **Original Rationale**：Unknown（cwd 相对缺省是项目最早的写法，未见记录）。
- **Current Assessment**（推断）：对「在仓库根目录 `uv run`」的开发者无害；对任何其他启动方式都是数据「丢失」的错觉加上密钥文件扩散。

## Decision Drivers

1. 同一位用户的四个入口必须看到**同一个**书库和**同一份**设置文件，与从哪个目录启动无关。
2. 不得静默迁移、合并或另起一个替代书库——现有用户的书库不能在其眼里「消失」。
3. 显式配置（环境变量、命令行）必须继续生效：e2e、CI、wheel 冒烟和多书库用户都靠它。
4. 设置文件含明文 API key：路径越少越好，且解析过程不得打印其内容。
5. 解析必须早于 `web.server` / `ai.config` 的导入，否则导入期的 `makedirs` 与缺省值已经生效。

## Considered Options

1. **一个解析器 ＋ 首次运行绑定，缺省 `~/Reader3/`**（选定）——代价：多一个绑定文件和一套首次运行判定；`reader3 <epub>` 在仓库外运行的行为改变。
2. **保持 cwd 相对，只打印绝对路径**（015 任务书 rev 0 的原推荐）——为什么不：打印不阻止事故，只让事后能查；`launch` 的复用判定也会因 cwd 不同而得出「不是同一实例」的结论，用户被迫记住从哪个目录启动。
3. **OS 应用数据目录**（`~/Library/Application Support/Reader3`、`%APPDATA%`、`$XDG_DATA_HOME`）——为什么不：维护者裁定数据要**可见**；书库是用户会手动浏览、备份、删书的目录（CLAUDE.md「Delete a book: Remove its directory」）。
4. **每次运行都按 cwd 探测、不记绑定**——为什么不：换个目录启动结果就变，正是要消灭的问题。

## Decision Outcome

新增一个只依赖标准库的模块（建议名 `reader3_app.data_home`），提供唯一的解析函数，产出 `DataHome(books_dir, settings_path, source)`（全部绝对路径；`source` ∈ `explicit` / `binding` / `first-run-cwd` / `first-run-default`）。规则按优先级：

1. **显式路径胜出**：`READER3_BOOKS_DIR`、`READER3_AI_SETTINGS` 与命令行同义参数，逐项独立生效。**所有需要的路径都已显式给出时，解析器不读也不写绑定文件**——绑定里记住的端口（f）因此也不被参考（e2e、CI、现有单测都落在这一条）。
2. **已有绑定**：绑定文件存在且通过读时校验（c），未显式给出的路径取绑定值，与 cwd 无关。校验失败 → 停止并指名文件，**不回退到 cwd**。
3. **首次运行（无绑定）**：
   - cwd 下有现成的书库/设置对，且**通过候选校验**（b），且 `~/Reader3/` 下没有 → 选定 cwd 下那一对的**绝对路径**；
   - **cwd 位于 `.claude/worktrees/` 下的 git worktree 里** → 不自动选定，停止，要求显式路径或手写绑定（b）；
   - 两处都没有 → 选定 `~/Reader3/books` 与 `~/Reader3/config/ai_settings.json`；
   - **两处（或更多）都像书库** → 停止，非零退出，列出候选，要求显式路径或手写绑定。不猜。
4. 选定路径在服务启动前打印（绝对路径 ＋ `source`），**从不打印设置文件内容**。
5. 解析器自身不建书库、不迁移、不合并、不删任何东西；建目录仍归后续代码（今天的 `makedirs`），且只在解析之后发生。
6. **首次选定只在命令自身校验通过后落盘**（d）：每个入口都解析，但绑定在命令完成自己的校验（EPUB 路径存在、索引目标存在、端口可用或可复用……）之后、第一次数据副作用之前才写；写法是排他创建（c）。失败的命令不留下任何永久的全局选择。

**入口与导入顺序**：解析器在入口函数的第一行运行，把结果写进 `os.environ` 的两个变量（仅当它们没被显式设置），**然后**才惰性导入 `web.server` / `ai.config`。因此：

- `reader3.main`（导入 / 索引）：解析放在 argparse 之后、任何惰性导入之前；`reader3.py` 顶层今天不导入 `web.server` / `ai.config`，满足条件。
- `reader3 launch`：同上，且 `launch` 模块顶层不得导入 `web.server`。
- `reader3-server`：`server.main` 在 `server.py` 里，到它运行时 `server` 已导入、`makedirs` 已执行——所以脚本入口改指一个薄包装（例如 `reader3_app.launch:serve_main`），**脚本名不变**（`pyproject.toml` `[project.scripts]` 只改右边的目标）。薄包装所在模块**顶层不得导入 `web.server` 或 `ai.config`**，导入顺序测试覆盖它（a）。
- **单纯 `import reader3_app.web.server`（TestClient、单测）不触发解析器**：导入期行为一字不变。

**明确不做**：不改 `READER3_*` 环境变量的语义；不做书库迁移或合并工具；不支持多个命名书库（「profile」）；不把绑定写进仓库；不把设置文件挪进书库目录。

### 子问题裁定（2026-10-02；a、e 照起草推荐，b、c、d、f 按 Codex 修订）

- **a. `reader3-server` 走解析器** → **是**。否则它是另一个家；`launch` 复用判定会因身份不同而拒绝，安全但令人困惑。薄包装顶层不导入 `web.server` / `ai.config`，并进导入顺序测试。代价：`scripts/smoke_installed_wheel.py` 今天只注入 `READER3_BOOKS_DIR`、不注入 `READER3_AI_SETTINGS`，按规则 1 会去读写绑定，其 CLI 与服务两段都须改为两条都显式注入或隔离 `HOME`（该脚本不在冻结集；CI 跑它，改动要在 CI 上验）；e2e 显式注入两条路径，不受影响。
- **b. 「cwd 下有现成的书库/设置对」的判据** → 信号：`./books` 下至少一个 `*_data` 目录，**或** `./config/ai_settings.json` 存在。只命中其一时，另一项仍取 cwd 下的同名相对位置（两者作为一对选定，不拆到两个家）。`~/Reader3/` 同理判定。修订：
  1. **选定前校验候选**：每个被当作信号的 `*_data` 目录必须像一本真书（含可识别的书文件——012 前是 `book.pkl`，012 后按 ADR-0009 的 manifest；具体判据随 012 落地时的格式写进实现）；设置文件必须是合法 JSON。信号存在但校验失败 → 停止并指名该文件，不当作「空」退回 `~/Reader3/`。
  2. **worktree 不自动选定**：cwd 位于 `.claude/worktrees/` 下的 git worktree 里时，即使通过校验也**从不**自动选定，停止并要求显式路径或手写绑定。现实陷阱：开发者在一个复制过 `config/ai_settings.json`（被 `.gitignore` 忽略）的 worktree 里第一次 `uv run reader3 x.epub`，会把全局的家绑到这个用完即删的 worktree。
- **c. 绑定文件** → 位置 `$XDG_CONFIG_HOME/reader3/binding.json`（缺省 `~/.config/reader3/binding.json`，macOS 同路径），`0600`；测试用 `READER3_BINDING` 覆盖路径。不放在 `~/Reader3/` 里：绑定可能指向别处，把指针放进其中一个候选家会让「多个候选」判定自相干扰。修订：
  1. **首次写是排他创建**（`O_CREAT | O_EXCL`，或在锁下创建后重读）。两个并发首跑：后到者重读到已存在的绑定——选定相同则照用，**选定不同则拒绝**并说明冲突，不覆盖。之后的更新（只有 f 的端口字段）用临时文件 ＋ `os.replace`，同 `ai.config` 的写法。
  2. **读时校验**：schema（已知字段、类型、绝对路径）、权限（`0600`，宽于此即拒绝并提示 `chmod 600`）、所指路径存在。任一失败 → 停止，指名文件与原因，**不回退到 cwd**。
- **d. 谁写绑定** → 四个入口都解析同一个家；但首次选定**只在命令自身校验通过之后、第一次数据副作用之前**落盘（规则 6）。例：`reader3 nope.epub`（文件不存在）、`reader3 --index 不存在的书`、端口被别的实例占着而拒绝的 `launch`——都**不留下绑定**。
- **e. 改绑** → 不提供命令（YAGNI）。文档写明安全步骤：先停掉服务；查看并编辑绑定文件（位置见 c；`reader3 launch` 启动时也会打印它所用的绑定路径）；编辑后的内容按 c.2 校验，**校验失败即停止，不静默回退**；刻意删除绑定会让下一次运行重新走首次选定。
- **f. 记住的端口**（015 Q2「记住显式选择的端口」）存在同一绑定文件的 `port` 字段；只有成功就绪或成功复用的 `reader3 launch --port N` 写它，`READER3_PORT` 不写（环境变量是一次性的），拒绝路径不写。优先级：`--port` > `READER3_PORT` > 绑定 `port` > 8123。修订：**端口记忆只对由绑定管理的启动生效**——数据路径全部显式时（规则 1）绑定既不读也不写，记住的端口也就不参考、不更新；这类启动的端口只看 `--port` > `READER3_PORT` > 8123。

## Consequences

### Positive
- 从任何目录 `reader3 launch`、`reader3 <epub>`、`reader3 --index` 都落到同一个书库和同一份设置文件。
- 设置文件（明文 API key）只有一份，位置可打印、可预期。
- `launch` 的实例身份（015 Q2）有了稳定输入：同一用户的两次启动算出同一身份。

### Negative
- **行为改变**：在仓库外、不设 `READER3_BOOKS_DIR` 运行 `reader3 <epub>` 的用户，书进 `~/Reader3/books`（或绑定处），不再进 cwd 下的 `books/`。需要在发布说明里写明。
- 多一个用户可见的状态文件（绑定），坏了要有清晰报错（不可读 → 停止并指名文件，不回退到 cwd——回退就是静默换家）。
- 首次运行判定在「两处都像书库」、候选校验失败、cwd 在 `.claude/worktrees/` 下、或并发首跑选定不同时会拦住用户，要求一次手动选择。开发者在 worktree 里首次跑 CLI 必须显式给路径（或已有绑定）——这是刻意的摩擦。
- 绑定读时校验更严（权限宽于 `0600` 也拒绝）：手改绑定后忘了 `chmod` 的用户会被拦下，报错须给出修复命令。
- 单测若调用入口函数而未显式设两条路径，会读写真实绑定——须在 `tests/unit/conftest.py`（不在冻结集）加一道 autouse 栅栏，把 `READER3_BINDING` 指到临时目录；今天已有三道同类栅栏。

### Neutral
- `docs/storage-and-data-locations.md` 的「Server-side settings file」与书库路径描述须改写为指向本 ADR。
- CLAUDE.md 「Core Commands」里 `uv run reader3 ./books/<file.epub>` 在仓库根目录仍成立（首次运行绑定 cwd 的现成书库）。
- 书锁目录 `books/.locks/`（ADR-0015）跟着书库走，因此也随绑定统一——两个入口不再可能各持一套锁目录。

## Migration Strategy

现状：四个入口 cwd 相对，导入期求值。目标：一个解析器，入口函数第一行运行。由 `015-launch-experience` CLI 侧一个 WI 完成（[015 WI-2](../plans/20260816-tech-stack-migration/tasks/015-launch-experience.md#wi-2-数据家解析器)）。棘轮：导入顺序测试（解析完成时 `web.server` / `ai.config` 未导入）＋ 解析表驱动测试 ＋ 已安装 wheel 冒烟在隔离 `HOME` 下首跑落到 `~/Reader3/`。

## Revisit When

- 出现「一个用户多个书库」的明确需求（profile）。
- 桌面壳（ADR-0008 Revisit 条件满足）——安装包可能要求 OS 应用数据目录。
- 设置文件改为 OS 钥匙串存 key（届时设置路径的意义改变）。

## Related

- [ADR-0001](0001-filesystem-as-database.md)（文件系统即数据库）——本文决定「那个文件系统在哪」；不改 ADR-0001 的任何一条。
- [ADR-0015](0015-per-book-write-coordination.md)（每书写协调）——锁目录随书库走。
- [ADR-0011](0011-api-v1-freeze.md)（API v1 冻结）——无关路由；015 的实例身份字段是另一处加法改动。
- [ADR-0008](0008-tech-stack-boundary.md)（桌面化不做）——Revisit 条件之一。
- [ADR-0012](0012-security-boundaries.md)（请求边界）——`/api/health` 令牌豁免与 Host 闸，015 实例身份传哈希不传路径的前提。
- [`015-launch-experience.md`](../plans/20260816-tech-stack-migration/tasks/015-launch-experience.md)：§2.3（`launch` 的 origin 与端口优先级，含本文 f 的端口记忆一级）、WI-2（落点与验收种子）、WI-5（端口记忆的写入时机）、§6 Q6 / Q14（本文的裁定来源）。
- [`docs/storage-and-data-locations.md`](../storage-and-data-locations.md)：「Server-side settings file」与书库路径描述在 015 实施分支（WI-7）改为指向本文；在那之前它描述的是今天的 cwd 相对行为。
