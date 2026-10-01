# Coordinator Suite 使用指南（`/coordinate` + `coordinate-bindings`）

> 本文只讲**怎么用**、**为什么这么分**，并演示一次真实运行。规则的定义处是套件里的 skill 与 reference 文件，本文用相对链接指过去，不复述。两者如有出入，以 skill 文件为准。
>
> 案例数据取自 2026-09-30 Reader3 Pro 的真实并行 program（base `1836a2a`）。凡是没有真实值的地方，一律写成 `<占位>`，不编造。

---

## 目录

1. [总览](#1-总览)
2. [文件功能表](#2-文件功能表)
3. [安装](#3-安装)
4. [在 Claude Code 中启动多 session 的实操](#4-在-claude-code-中启动多-session-的实操)
5. [端到端案例：2026-09-30 program（以 020-debug-state 为主线）](#5-端到端案例2026-09-30-program以-020-debug-state-为主线)
6. [验收标准怎么写](#6-验收标准怎么写)
7. [常见坑 / FAQ](#7-常见坑--faq)
8. [与其它工具的关系](#8-与其它工具的关系)
9. [附：套件文件中发现的不一致](#9-附套件文件中发现的不一致)

---

## 1. 总览

### 1.1 它是什么

这是一套把**一个 Claude Code session 变成"协调者"（coordinator / delegator）**的工具。协调者负责驱动多个并行的**实现者（implementor）session**，每个实现者在各自的 git worktree 里工作。协调者要做的事是：拆分工作、画冲突图、下发 brief、裁决问题、独立验收 CP0–CP3、排定合并顺序、回写结果。**它自己不写代码。**

核心三原则见 [`SKILL.md`](user-level/skills/coordinate/SKILL.md) 开头：

1. **brief 就是产品。** 实现者看不到协调者的上下文，brief 里漏写的东西，对方只能靠猜。
2. **fan-out 之前一次定案。** 分支号、合并顺序、文件归属、共享资源都由协调者集中决定，实现者之间不互相协商。
3. **验证，不轻信。** 实现者的报告只是待检验的证据。每一次验收都绑定到一个 HEAD SHA。

### 1.2 为什么拆成 user-level core 和 project-level bindings

| 层 | 内容 | 理由 |
|---|---|---|
| **Core**（用户级，`~/.claude/`） | 生命周期（intake → 拆分 → fan-out → dispatch → CP → 裁决 → 合并 → 收尾）、检查点清单、brief 模板、锁协议、验证 subagent | 这些与项目无关。同一个用户在多个 repo 里遵循同一套全局规则（tdd-guardian、Codex 审议、Opus 委派） |
| **Bindings**（项目级，入库） | 本 repo 的**指针**：单元定义在哪、lane 定义在哪、冻结路径定义在哪、锁的现状、分支号怎么分、额外常驻指令、收尾回写清单 | 项目事实要随 repo 一起版本化；它**只放链接、不抄内容**，否则会和定义处漂移 |
| **每个 program 的 `protocol.md`** | 本次的 roster、脏文件、分支号、表格行分配、冲突图 | 这些是一次性事实，写进 bindings 很快就会过期 |

两份评审（Codex 与 Opus）都认同这种拆分，同时指出早期草稿有两类毛病：core 里混进了 Reader3 的专有事实，bindings 里又抄了 `config.json` 与 `plan-and-branch-map` 的内容。现在的版本已经按评审修正，例如 bindings 不再抄 lane 命令，只链接到 `config.json`。

### 1.3 目录树与安装目标

```
docs/references/coordinator-suite/          ← 本目录：套件源文件（参考副本）
├── README.md                               ← 本指南
├── user-level/
│   ├── skills/coordinate/                  → 安装到 ~/.claude/skills/coordinate/
│   │   ├── SKILL.md
│   │   └── references/
│   │       ├── checkpoints.md
│   │       ├── dispatch-template.md
│   │       ├── shared-lock.md
│   │       └── tdd-guardian.md
│   └── agents/
│       └── checkpoint-verifier.md          → 安装到 ~/.claude/agents/checkpoint-verifier.md
└── project-level/.claude/skills/coordinate-bindings/
    └── SKILL.md                            → 安装到 <repo>/.claude/skills/coordinate-bindings/SKILL.md（入库）

运行时产生（不在套件里）：
<repo>/.claude/worktrees/<branch>/          ← 每个 unit 一个 worktree
<repo>/.claude/coordination/<date>-<slug>/  ← program store：protocol.md / decisions.tsv / ledger.tsv
```

---

## 2. 文件功能表

| 文件 | 安装位置 | 何时加载 | 作用 | 不要往里放 |
|---|---|---|---|---|
| [`coordinate/SKILL.md`](user-level/skills/coordinate/SKILL.md) | `~/.claude/skills/coordinate/SKILL.md` | 只在你输入 `/coordinate` 时（`disable-model-invocation: true`） | 协调者的完整生命周期 §0–§10：加载 bindings、intake、冲突图、fan-out、dispatch、CP、裁决、升级、liveness、合并、收尾 | 任何项目路径、分支号、lane 名、冻结路径；对全局 CLAUDE.md 规则的复述（只写"遵循全局 *Orchestration* / *Decision Support*"） |
| [`references/checkpoints.md`](user-level/skills/coordinate/references/checkpoints.md) | `~/.claude/skills/coordinate/references/` | 协调者在 CP 验收时按需读 | CP0–CP3 的勾选清单 | 具体 lane 名、具体通过数（这些在 brief 的 ACCEPTANCE 与 VERIFY 里） |
| [`references/dispatch-template.md`](user-level/skills/coordinate/references/dispatch-template.md) | 同上 | dispatch、裁决回复、CP 回复时 | brief 模板（所有字段必填），以及裁决回复和 CP 判定回复的短格式 | 已填好的某次 brief（那属于 program store） |
| [`references/shared-lock.md`](user-level/skills/coordinate/references/shared-lock.md) | 同上 | 冲突图里出现无法拆开的共享资源时 | 首选 fcntl 包装器（内核自动释放）；回退方案是 mkdir 加 owner 文件，外加 6 条硬规则；"不洗权限" | 项目的锁路径、超时数值、事故史 |
| [`references/tdd-guardian.md`](user-level/skills/coordinate/references/tdd-guardian.md) | 同上 | bindings 的 GATE_SOURCE 指明 tdd-guardian 时 | CP ↔ tdd-guardian 命令的映射表 | lane 与 gate 的归属（每次从项目 config 现读）；`gateFreshnessMinutes` 推理 |
| [`checkpoint-verifier.md`](user-level/agents/checkpoint-verifier.md) | `~/.claude/agents/checkpoint-verifier.md` | 协调者用 Agent 工具按名字 `checkpoint-verifier` 调用 | 只读验证 subagent：在**自己的 detached worktree** 里 checkout 声称的 SHA，重跑 lane、审 diff，返回 `PASS / ISSUES / BLOCKED` | 项目专有命令（由调用方在 prompt 里传入）；任何写操作权限 |
| [`coordinate-bindings/SKILL.md`](project-level/.claude/skills/coordinate-bindings/SKILL.md) | `<repo>/.claude/skills/coordinate-bindings/SKILL.md`（入库） | `/coordinate` §0 **从主 checkout 读这个文件**（不是作为 skill 调用） | 7 个必需标题下的项目指针，外加"已知冲突点"种子 | 一次性事实（脏文件、本轮分支号、行分配 → `protocol.md`）；从 `config.json`、`soak-log.md` 或 `plan-and-branch-map` 抄来的内容 |

---

## 3. 安装

### 3.1 命令

在 repo 根目录执行（本任务**没有**替你执行这些命令）：

```bash
REPO=/Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro
SUITE=$REPO/docs/references/coordinator-suite

# 1) Core skill（用户级）
mkdir -p ~/.claude/skills/coordinate
cp -R "$SUITE/user-level/skills/coordinate/." ~/.claude/skills/coordinate/

# 2) 验证 subagent（用户级，必须直接放在 ~/.claude/agents/ 下，不能放进 skill 目录）
mkdir -p ~/.claude/agents
cp "$SUITE/user-level/agents/checkpoint-verifier.md" ~/.claude/agents/

# 3) Bindings（项目级，入库）
mkdir -p "$REPO/.claude/skills/coordinate-bindings"
cp "$SUITE/project-level/.claude/skills/coordinate-bindings/SKILL.md" \
   "$REPO/.claude/skills/coordinate-bindings/SKILL.md"
git -C "$REPO" add .claude/skills/coordinate-bindings/SKILL.md   # 提交时用 pathspec

# 4) 检查
ls ~/.claude/skills/coordinate ~/.claude/skills/coordinate/references ~/.claude/agents/checkpoint-verifier.md
```

装完之后在新 session 里：

- 输入 `/` 应能看到 `/coordinate`，看不到 `/coordinate-bindings`。
- 运行 `/agents` 应能看到 `checkpoint-verifier`。
- 如果没有出现，重启 session。按官方文档，skill 目录有实时变更检测，但 `agents/` 的变更可能需要重启。

> **关于 checkpoint-verifier 的路径。** 官方 subagent 文档列出的发现位置只有这几处：`.claude/agents/`、`~/.claude/agents/`、`--add-dir` 目录下的 `.claude/agents/`、插件的 `agents/`、managed settings。**skill 目录不会被扫描。** core 的 [`SKILL.md`](user-level/skills/coordinate/SKILL.md) §5 和 [`checkpoints.md`](user-level/skills/coordinate/references/checkpoints.md) 只按**名字**引用 `checkpoint-verifier` subagent，不写路径；而该 agent 的 frontmatter 是 `name: checkpoint-verifier`。所以只要按上面第 2 步装到 `~/.claude/agents/`，引用就能解析；若误放进 `~/.claude/skills/coordinate/agents/`，就**解析不到**。`model: opus` 和 `tools: Read, Grep, Glob, Bash` 都是官方支持的 frontmatter 字段。

### 3.2 两个 frontmatter 开关

| 字段 | 所在文件 | 效果（官方 skills 文档） | 为什么这样设 |
|---|---|---|---|
| `disable-model-invocation: true` | `coordinate/SKILL.md` | 只有你能调用：description **不进入**上下文，模型不会自动加载，也不会预加载进 subagent；输入 `/coordinate` 时才加载全文 | 当协调者是**角色切换**：这个 session 从此不再实现。不能让实现者 session 因为聊到"并行""分派"就误加载 |
| `user-invocable: false` | `coordinate-bindings/SKILL.md` | 只有 Claude 能调用：从 `/` 菜单隐藏，输入 `/coordinate-bindings` 也不会执行；description **始终在**上下文里 | 它是背景知识，不是动作。实际由 `/coordinate` §0 直接读文件 |

注意两个副作用：

- 因为 `disable-model-invocation: true`，core 的 description 里那些 "Use when the user says…" 触发短语**不会生效**，只有 `/coordinate` 能触发。
- 因为 `user-invocable: false`，bindings 的 description 在**每个** session 里都可见，包括实现者 session（worktree 里也有入库的副本）。这不构成危害，但 core 规定协调者必须读**主 checkout** 的那一份，并在 `protocol.md` 里记录它的 blob SHA。

### 3.3 把 bindings 移植到别的项目

1. 复制 [`coordinate-bindings/SKILL.md`](project-level/.claude/skills/coordinate-bindings/SKILL.md) 到新 repo 的 `.claude/skills/coordinate-bindings/`，保留 `user-invocable: false`。
2. 填好 7 个**必需标题**（core §0 定义；缺任何一个，协调者就不会 dispatch）：

| 标题 | 回答的问题 | Reader3 的写法（示例） |
|---|---|---|
| `DEFINITION_SITES` | 工作单元有几种形状，各自定义在哪 | 先加载 `plan-and-branch-map`；三种形状：migration task 文件 / 前端 `### WI-N` / 债务窗口或独立计划 |
| `GATE_SOURCE` | lane、命令、超时、gate 定义在哪；用什么 gate 工具 | `.claude/tdd-guardian/config.json`，外加 `CLAUDE.md` "Tests and Checks" |
| `FROZEN_SOURCE` | 冻结或独占路径定义在哪 | `tasks/soak-log.md` 表头，以及 `scripts/soak_run.py` 的 `HASH_COVERED_PATHS` |
| `LOCKS` | 共享资源、锁机制、**当前状态** | E2E：目标是 `scripts/e2e_lock.py`（**PLANNED**），过渡期用 mkdir 锁 |
| `ALLOCATION` | 分支号或 ID 怎么预留 | `plan-and-branch-map` "Branch naming"（只从迁移计划 §9 取号） |
| `EXTRA_ORDERS` | 追加在 core 默认常驻指令后面的项目指令 | 禁止 `ruff format`；改 `docs/plans/` 前先加载 skill；禁止在 unit 分支上 `soak_run.py --append` |
| `CLOSEOUT` | 合并和收尾时要回写什么 | 里程碑表与看板、feature ledger、债务表、soak log |

3. **只放链接，不抄内容。** 每一条都指向该事实唯一的定义处（文件加章节名）。bindings 里一旦出现 lane 命令、超时数值、冻结文件清单，就会与定义处漂移。Codex 评审抓到过一个实例：早期草稿抄的 unit 命令漏掉了 `--cov` 参数。
4. 可选：增加一个"Known conflict points"段，给冲突图提供种子。但**本轮**的行分配仍然写进 `protocol.md`。
5. 新项目如果没有 gate 工具，`GATE_SOURCE` 就写成"项目声明的测试命令在 X"。core §5 规定，没有 gate 工具时 CP2/CP3 跑这些命令。

---

## 4. 在 Claude Code 中启动多 session 的实操

> 本节涉及的 Claude Code 机制都已对照官方文档核实（2026-09-30），出处见第 8 节末尾。版本门槛以你本地 `claude --version` 为准。

### 4.1 前置：allocation commit 与 worktree

先由协调者在 master 上用**一个 commit** 预留全部分支号（本例是 `1836a2a`），再从这个 commit 建 worktree：

```bash
cd /Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro
BASE=1836a2a
git worktree add .claude/worktrees/019-frozen-set-debts -b 019-frozen-set-debts $BASE
git worktree add .claude/worktrees/018-library-routes   -b 018-library-routes   $BASE
git worktree add .claude/worktrees/020-debug-state      -b 020-debug-state      $BASE
git worktree list
```

为什么不用 `claude --worktree <name>`？官方文档写明，`-w` 会在 `.claude/worktrees/<name>/` 建一个**名为 `worktree-<name>` 的新分支**，基点默认取远端默认分支（`worktree.baseRef: "fresh"`），也可以取当前 `HEAD`，**但不能指定分支名或任意 SHA**。我们要的是 `0NN-name` 这种分支名，而且必须从本地未推送的 allocation commit 起步，所以用 `git worktree add`。官方文档也写了这种手动方式："Create worktrees with Git directly when you need to check out a specific existing branch"。

另外两点：

- 官方建议把 `.claude/worktrees/` 加进 `.gitignore`。本 repo 目前**没有**忽略它：`git check-ignore` 返回 1，`git status` 里也能看到 `?? .claude/worktrees/`。是否添加由你决定。
- 每个 worktree 第一次使用前，先跑 `uv sync && npm ci`，再在实现者 session 里运行 `/tdd-guardian:status`。tdd-guardian 的状态是按 worktree 分开的。

### 4.2 每个 worktree 开一个终端

| 终端 | 目录 | 启动命令 |
|---|---|---|
| T0 协调者 | repo 根（主 checkout） | `claude -n reader-delegator` |
| T1 | `.claude/worktrees/019-frozen-set-debts` | `claude -n reader-a2` |
| T2 | `.claude/worktrees/018-library-routes` | `claude -n reader-a3` |
| T3 | `.claude/worktrees/020-debug-state` | `claude -n reader-a4` |

- **命名**：`--name` / `-n` 设置 session 显示名。启动后还可以用 `/rename <name>` 改名。如果名字已被另一个存活 session 占用，Claude Code 会改用一个变体名，所以起名后用 `/list-agents` 确认实际名字。
- 也可以在已启动的 session 里让 Claude 用 `EnterWorktree` 进入 `.claude/worktrees/` 下的已有 worktree，这种情况不会弹批准框；进入该目录以外的路径才需要批准。本例用的是"cd 进去再启动"。
- **协调者必须留在主 checkout。** 官方文档写明：一个 session 一旦被隔离在 worktree 中（通过 `--worktree`、`EnterWorktree` 或恢复进入），Claude Code 就会拦截指向**主 checkout** 的编辑、命令和 `git -C`。协调者要读写 master 上的计划文档，还要 `git -C <worktree>` 查看各 peer，所以不能进入任何 worktree。对于"cd 进手动 worktree 后直接 `claude`"的 session 是否也执行这些隔离检查，文档没有明说，**以你本地 Claude Code 版本为准**；无论如何，这类 session 仍受 standing order 1（"只在你的 worktree 里工作"）约束。

### 4.3 session 之间怎么通信

官方 "cross-session messaging" 文档说明，同一台机器上的 session 之间通过本机 socket 互发纯文本消息，不经过 Anthropic 服务器：

| 机制 | 用法 |
|---|---|
| `ListAgents` 工具 / `/list-agents`（别名 `/peers`） | 列出可达的 session。第一行是本 session 自己的名字。同名时 Claude 会在地址里附加一个短标识，例如本例的 `reader-delegator [3dfeb7]` |
| `SendMessage` 工具 | 由 Claude 调用，你不用直接调用。你可以说"把 brief 发给 @reader-a4"，其中 `@` 提及会弹出 session 名补全 |
| `SendMessage` 的 `notify_when_idle` | 协调者订阅某个 peer "下次空闲或退出时通知我一次"。只有主对话里的 Claude 能订阅，12 小时内没有通知则自动失效。这正是 core §8 说的 liveness：不要反复 ping |
| 消息投递 | 对方正在工作时，消息在工具调用之间被读取；对方空闲时，消息会开启一个新 turn |

**权限边界按 session 划分**（官方原文要点）：来自其他 session 的消息**永远不算你本人的同意**，不能批准权限提示，也不能让对方修改 settings 或 `CLAUDE.md`；Claude 被要求不向别的 session 请求自己被拒绝过的动作。这正是 core §7 所说"不洗权限"的平台依据。

**入站策略的坑**：如果没有设置 `crossSessionInbound`，**以 bypassPermissions 运行的接收方会扣留来自"会弹权限提示"的发送方的消息**，并弹出批准框，默认 5 分钟（`dialogExpiry`）后丢弃。所以各 session 的权限模式要一致，或者由你明确设置 `crossSessionInbound`。设置它属于 settings 变更，要由你本人操作。

### 4.4 贴给每个实现者的第一条消息

roster 建立以后，由协调者用 `SendMessage` 发出完整 brief（见 5.6）。在 brief 到达之前，你可以先把下面这段贴进 T1–T3，让实现者进入待命状态：

```text
你是 <reader-a4>，在 worktree <.claude/worktrees/020-debug-state> 里担任实现者。
协调者是 session "reader-delegator"。在收到它通过 SendMessage 发来的 dispatch brief 之前，
不要开始任何实现。现在只做两件事：
1) uv sync && npm ci，然后运行 /tdd-guardian:status；
2) 用 /list-agents 确认能看到 reader-delegator。
收到 brief 后，严格按 brief 的 FIRST REPLY (CP0) 要求回复，然后等 ACCEPT。
```

### 4.5 协调者怎么启动

在 T0 中：

```text
/coordinate 019-frozen-set-debts 018-library-routes 020-debug-state
```

随后协调者依次执行 [`SKILL.md`](user-level/skills/coordinate/SKILL.md) 的各节：

- §0：读 bindings，并记录其 blob SHA（`git rev-parse HEAD:.claude/skills/coordinate-bindings/SKILL.md`）。
- §1：intake。
- §2：画冲突图。
- §3：建 store、确认 roster（`/list-agents`）、在每个 worktree 做 pre-flight。
- §4：dispatch。

任何一个必需标题没有解决，都不会进入 dispatch。

协调者**重启后**，先重读 `protocol.md`、`decisions.tsv`、`ledger.tsv`，运行 `git worktree list`，逐个对比 peer 的 HEAD 与它在 ledger 里的最后一行（core §3 "Coordinator resume"）。

---

## 5. 端到端案例：2026-09-30 program（以 020-debug-state 为主线）

### 5.1 Intake

- **目标**：在关键路径 019 → 018 → 012 开工核验 → 012 → 014 → 015 上推进，同时把可以随时插入（⟂）的 020 并行做完。
- **Done predicate**（示例写法）："019、020 各有一个 CP3 ACCEPT，且绑定到最终被合并的那个 SHA，并已合入 master；018 在 WI-2 处停下，拿到 ACCEPT，然后在 019 合入后 rebase。"
- **定义处**：019 没有 task 文件，它的定义处是 009/017 债务表中的行；018 是 `tasks/018-*.md`；020 是独立计划 [`docs/plans/20260928-debug-state-getter.md`](../../plans/20260928-debug-state-getter.md)。三种形状都对应 bindings 的 `DEFINITION_SITES`。
- **就绪检查**：主 checkout **不干净**，里面有用户未提交的 `011-backend-refactor.md`、`.claude/settings.json` 和 `designs/*.jsx`。这几个文件写进 `protocol.md`，任何人都不能碰。tdd-guardian config 是 enabled 状态，4 条 lane（unit、fe-unit、e2e、packaging）都可以跑。
- **Timebox**：`<与用户约定，记入 protocol.md>`。

### 5.2 Collapse check

- 020 自己的计划写明"WI-0 → WI-3 顺序执行，不需要拆 worktree"。所以 020 **内部**不再 fan-out，整体作为一个 unit。
- 三个 unit 的写入范围基本不相交，共用部分可以通过冲突图消解，因此跨 unit 的 fan-out 成立。
- 018 依赖 019（冻结集），不能整体并行。办法是只放行它的 WI-1 和 WI-2，然后 **HARD STOP**。

### 5.3 冲突图

| 冲突点 | 涉及 | 消解方式 |
|---|---|---|
| 冻结 soak 路径（`tests/e2e/baseline_1b/**`、`conftest.py`、`helpers.py`、`test_harness_smoke.py`、4 个 fixture） | 019，以及其他可能误碰的人 | **单一 owner**：只有 reader-a2（019）能改；其他 unit 在 CP2/CP3 做空 diff 检查 |
| 009 债务表 | 019 改 #49/#50/#62；018 WI-1 改 #51/#53/#56/#58 的 owner 列 | **拆分到行**：行不重叠 |
| `scripts/lint_e2e_groups.py`、`tests/unit/test_e2e_group_guard.py` 的计数常量 | 019（#62）、020（新增 E2E 文件） | **声明谁第二个合并**：019 先合，020 rebase 后**重新计数**并重跑 gate |
| E2E 的 CPU 资源（压力下会出现 #49 类假红） | 所有跑 e2e 的人，包括协调者复跑 | **加锁串行**：`mkdir ~/.cache/reader3-e2e.lock` 加 owner 文件；unit 和 fe-unit 可以并行 |
| 里程碑表与进度看板 | 协调者 | **只由协调者写**，只在分配、首个被接受的 CP（🚧）、合并（✅）、收尾这四个时刻写，使用 pathspec commit |
| 主 checkout 的用户脏文件 | 所有人 | 只读；协调者的 master commit 一律用 `git commit -- <paths>` |

**合并顺序**：019 → 020（rebase 并重新计数后合并）；018 在 019 合入后 rebase，再开始 WI-3。理由是依赖关系：018 和 012 都需要 019 改动后的冻结集。

### 5.4 Allocation commit

`1836a2a`（"计划文档：分配 019-frozen-set-debts 与 020-debug-state；登记三线并行调度…"）在迁移计划 §9 中**一次性**登记了 019 和 020，并把并行计划写进看板 §4。三个 worktree 都从这个 commit 分出。

### 5.5 Fan-out 与 program store

```text
.claude/coordination/20260930-parallel-019-018-020/
├── protocol.md
├── decisions.tsv
└── ledger.tsv
```

> 本 repo 的 `.claude/coordination/` **没有**被 git 忽略（Opus 评审已用 `git check-ignore` 证实）。在你添加忽略条目之前，协调者的所有 commit 都必须用 pathspec，保证 store 不进入提交。

**示例 `protocol.md`**：

```markdown
# Program 20260930-parallel-019-018-020

- Bindings: .claude/skills/coordinate-bindings/SKILL.md @ <blob SHA 或 hash-object + "uncommitted">
- Base: 1836a2a on master（在 §9 分配了 019 和 020）
- Timebox: <与用户约定>
- Done predicate: 019 与 020 合入 master，各自有绑定到合入 SHA 的 CP3 ACCEPT；018 停在 WI-2 并已 ACCEPT，019 合入后 rebase

## Roster
| session | id | branch | worktree | scope |
|---|---|---|---|---|
| reader-delegator | 3dfeb7 | — (master) | repo root | 协调；不实现 |
| reader-a2 | <id> | 019-frozen-set-debts | .claude/worktrees/019-frozen-set-debts | 009 #50, #49, #62; 017 #10；冻结 soak 路径的唯一 owner |
| reader-a3 | <id> | 018-library-routes | .claude/worktrees/018-library-routes | 只做 WI-1、WI-2 → HARD STOP；019 合入后 rebase，再做 WI-3 |
| reader-a4 | <id> | 020-debug-state | .claude/worktrees/020-debug-state | getDebugState WI-0..WI-2；WI-3 在合入后做 |

## Standing orders（原文粘贴进每一份 brief）
1. 只在你自己的 worktree 里工作，永不写主 checkout（里面有用户未提交的 011-backend-refactor.md、.claude/settings.json、designs/*.jsx）。
2. 不 push、不开 PR、不 merge，这些由用户做。
3. 每个 commit 以 `Claude-Session: https://claude.ai/code/session_01Kv4Z92qzXehvZkmU9p85HE` 结尾；harness 冲突在 CP0 报告。
4. 不用裸 `git stash`。
5. 实现走 /tdd-guardian:workflow；永不设 TDD_GUARD_BYPASS。
6. 每个 CP 都报告，拿到 ACCEPT 后才能越过 STOP。
7. 永不替别的 session 释放锁；所有权限拒绝都上报协调者。
8. 不跑 `ruff format`。
9. 改 docs/plans/ 前先加载 plan-and-branch-map。
10. 不在 unit 分支上跑 `scripts/soak_run.py --append`，也不宣布批次。
11. E2E 互斥（过渡期）：跑 e2e 或 `/tdd-guardian:gate push` 前先 `mkdir ~/.cache/reader3-e2e.lock` 并写 owner；失败就用 Monitor 等待，不用前台 sleep；无论成败都要释放；释放被拒绝时上报，不要让别人代劳。

## Conflict map / Merge order
（见 README 5.3 表格）  Merge: 019 → 020 (rebase + recount) ; 018 rebase after 019 → WI-3
```

### 5.6 Dispatch：020 的 brief（按 [`dispatch-template.md`](user-level/skills/coordinate/references/dispatch-template.md) 填写）

```text
TO           reader-a4        FROM reader-delegator
UNIT         020-debug-state  in worktree /Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/.claude/worktrees/020-debug-state
             (cd there; never touch the main checkout)
BASE         1836a2a on master

GOAL         给阅读页加一个只读、不抛错、可序列化的 window.Reader3Epub.getDebugState()，
             并用 Vitest 单测 + 真实浏览器 E2E 锁住 §3 契约与 8 条不变量。
DEFINITION   docs/plans/20260928-debug-state-getter.md §3（契约 v1 + 不变量 1–8）、
             §4 WI-0 / WI-1 / WI-2（含测试矩阵 U1–U18、E1–E4 与各自验收标准）
SCOPE        may write: docs/plans/20260817-frontend-ui-refactor/contracts/annotation-host-contracts.md（K5）,
                        docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md（K5 / WI-15 验收 5 / FR-K5 / WI-19 交叉引用）,
                        src/reader3_app/web/static/js/epub-renderer.js,
                        frontend/tests/legacy/epub-renderer-debug-state.test.ts,
                        tests/e2e/test_debug_state.py,
                        scripts/lint_e2e_groups.py, tests/unit/test_e2e_group_guard.py
             must not write: 冻结 soak 路径（tests/e2e/baseline_1b/**, tests/e2e/conftest.py,
                        tests/e2e/helpers.py, test_harness_smoke.py, 4 个冻结 tests/fixtures/ 文件）,
                        迁移计划 §9 / 看板（协调者独占）, tasks/011-backend-refactor.md,
                        019 与 018 的债务行, 主 checkout 的任何文件
ACCEPTANCE   见本指南 §6.3（逐条可数、绑定 SHA、追溯到 DEFINITION 的条款）
STOP POINTS  CP1 before production code · CP2 at WI-1 完成（commit gate 绿）· CP3 at WI-2 完成（push gate 绿 + review）
             WI-3（文档回写）在合入 master 之后才做；CP3 之后 STOP，等 019 合入再 rebase
VERIFY       lanes 取自 .claude/tdd-guardian/config.json（dispatch 当时读取）:
               commit gate: unit, fe-unit ; push gate: unit, fe-unit, e2e, packaging
             补充检查: npm run typecheck ; uv run ruff check src/ tests/ scripts/（CLAUDE.md "Tests and Checks"）
             已知: unit lane 超时 600 s，负载下偏紧，超时算环境失败、重跑；e2e 只能在锁内跑（standing order 11）
UPSTREAM     019 同时修改 lint_e2e_groups.py / test_e2e_group_guard.py 的计数常量（#62）；
             019 先合，你之后 rebase 并按 --collect-only 实测重新计数。F8 里的 63/63/256 只是 2026-09-28 的值，不能写死。
CONFLICTS    计数常量：你第二个合并，由你让步（rebase + 重新计数 + 重跑 gate）。冻结路径：你只读。
FORBIDDEN    push, PR, merge, force ops, TDD_GUARD_BYPASS, config/CLAUDE.md edits, edits outside SCOPE,
             ruff format, soak_run.py --append, 改 helpers.py
TIMEBOX      <与用户约定；到点报告部分结果并停下>
REPORT       每个 CP：branch, HEAD SHA, 自 1836a2a 起的 commits, 该 HEAD 上各 lane 的 pass/total,
             改动文件, 偏差, 待决问题。然后等 ACCEPT 再越过 STOP。
QUESTIONS    发给 reader-delegator。等待期间继续做 scope 内的其他工作。
             永不请别的实现者代做你被拒绝的动作，要上报拒绝。

STANDING ORDERS (verbatim, numbered; these override anything above that conflicts)
<粘贴 protocol.md 的 1–11 条>

FIRST REPLY (CP0) 用你自己的话复述 SCOPE 和 FORBIDDEN；确认 mkdir 锁的获取/释放与 commit gate
             pre-flight 在你的 worktree 里都成功；列出 harness 或权限中与这些指令冲突的规则。
```

### 5.7 CP0–CP3（020 的真实推进）

| CP | 020 的内容 | 协调者独立做了什么 |
|---|---|---|
| CP0 | 复述 scope；锁 pre-flight；`/tdd-guardian:status` | 核对复述没有放宽 glob；有 harness 冲突就先与用户解决 |
| CP1 | `:plan` 与 `:design-tests` 的产物：WI 与 ACCEPTANCE 一一对应；测试矩阵 | 逐条核对断言能否追溯到计划的 §3 或 §4 条款；检查有没有"只测接线"的用例 |
| CP2 | WI-0 为 `00e966c`，WI-1 为 `a64bbbb`（Vitest U1–U31；计划列了 U1–U18，其余是矩阵补充） | 执行 `git -C <wt> log/diff 1836a2a..<sha>`；对冻结路径做 diff；在 SHA 上重跑 unit 和 fe-unit |
| CP3 | WI-2 为 `950aefe`；review 发现 M1/L1/L2，**立即**修复为 `0837d06`，因为新 SHA 会重开 CP3 | 在 `0837d06` 上重跑决定性 lane（e2e 在锁内）；冻结路径 diff 为空；检查 trailer |

**020 在 `0837d06` 上的 lane 结果**：unit 2561 passed，fe-unit 255，e2e 244 passed / 16 skipped，packaging 11。8 个文件。状态：**等 019 合入后即可合入**。

### 5.8 裁决（真实）

| ID | 问题 | 裁决 | 依据 |
|---|---|---|---|
| K5 | 新增 E2E 文件后的计数常量 | `scripts/lint_e2e_groups.py` :140/:146 的常量上调到 8 | 计划 F8 与 WI-2 第 3 步："按实测增量上调，不写死" |
| E2 | 有一条 `total==total` 断言超出计划，并暴露出首次渲染后 total 过期的问题 | **方案 A**：从 unit 中移除这条超纲断言，缺陷登记为债务 **009 #63，owner 014 WI-19**；**计划内的测试不削弱** | core §6 "An assertion or feature outside the spec" |
| M1/L1/L2 | CP3 review 的发现 | 立即修复（`0837d06`） | CP3 清单："correctness or requirement gaps are fixed" |
| 018-单测 | 018 的 unit 有 18 个测试坏了 | 只排除 `.locks`，并正向断言它只含 `*.lock`；逐个分类：附带性依赖的测试在 setup 里加 makedirs，**声称会创建目录**的测试改为反向断言；GET-409 "no notes" 的 UX 毛病登记为 #64 | 同上，不削弱计划内断言 |

**示例 `decisions.tsv`**（制表符分隔；`ts` 只写日期，因为没有保留具体时刻）：

```tsv
ts	session	question	ruling	why	evidence	amended-where
2026-09-30	reader-a4	K5: 新 E2E 文件后分组计数常量取值	lint_e2e_groups.py :140/:146 常量上调到 8	计划 F8/WI-2 第 3 步：按 --collect-only 实测上调	950aefe diff	none: execution call
2026-09-30	reader-a4	E2: total==total 断言超纲且暴露首渲染 total 过期	方案 A：移除该断言；登记 009 #63，owner 014 WI-19；计划内测试不动	断言不可追溯到 §3/§4；缺陷真实，归债	CP3 报告	009 债务表 #63
2026-09-30	reader-a4	CP3 review M1/L1/L2	立即修复	correctness/requirement 类发现必须修	0837d06	none: execution call
2026-09-30	reader-a3	018 unit 18 个测试失败	只排除 .locks + 正向断言仅含 *.lock；按测试分类：附带性→setup makedirs，声称创建→反向断言；GET-409 登记 #64	不削弱计划内断言；不扩大排除面	<018 CP 报告>	009 债务表 #64
2026-09-30	reader-a3	commit trailer 加不上（harness 限制）	由用户在 merge commit 中补	harness 冲突属于用户决策	<CP0 报告>	none: user decision
```

**示例 `ledger.tsv`**（只有 `0837d06` 那一行的数字是真实值，其余用 `<…>` 表示本文不掌握）：

```tsv
ts	session	CP	sha	lanes(pass/total)	verdict	notes
2026-09-30	reader-a4	CP0	1836a2a	—	ACCEPT	锁 pre-flight OK；tdd-guardian status OK
2026-09-30	reader-a4	CP1	1836a2a	—	ACCEPT	矩阵可追溯到 §3/§4
2026-09-30	reader-a4	CP2	a64bbbb	unit <…>; fe-unit <…>	ACCEPT	冻结路径 diff 为空
2026-09-30	reader-a4	CP3	950aefe	<…>	FIX	review M1/L1/L2
2026-09-30	reader-a4	CP3	0837d06	unit 2561 passed; fe-unit 255; e2e 244 passed/16 skipped; packaging 11	ACCEPT	8 files；等 019 合入后 rebase+重新计数→重开 CP3
```

### 5.9 合并顺序与收尾

1. 用户合并 019（CP3 必须绑定到被合并的那个 SHA）。
2. 协调者把 020 在 `0837d06` 上的 ledger 行标记为 **superseded**，然后告诉 reader-a4 新的 master SHA 以及要重做的事：rebase，重新计算 `lint_e2e_groups.py` 和 `test_e2e_group_guard.py` 的常量，重跑全部 gate。
3. reader-a4 在 rebase 后的新 SHA 上报告 CP3 → 协调者复跑并给出 ACCEPT → 用户合并 020。
4. 020 合入后，由实现者做 WI-3（回写 feature ledger、调研报告和 `CLAUDE.md`）；协调者在里程碑表和看板上写 ✅。
5. 018 在 019 合入后 rebase，再开始 WI-3。
6. 执行收尾（bindings `CLOSEOUT`）：
   - 更新里程碑表与看板；
   - 更新 feature ledger 并运行 `build_feature_ledger.py`；
   - 债务表：关闭已偿还的行，登记 #63 和 #64（各带 owner 与位置）；
   - soak log 只按 §7 的规定处理。
7. 把反复出现的纠正**变成结构**：fcntl 锁包装器 `scripts/e2e_lock.py` 已排队，等 019 和 020 合入后单独开 tdd-guardian 分支实现。在它落地之前继续用 mkdir 锁，释放被拒时交给用户处理。

---

## 6. 验收标准怎么写

> 这一节决定了协调是否可靠。brief 里的 ACCEPTANCE 写得模糊，CP3 就只能"看起来差不多"。

### 6.1 原则

| # | 原则 | 含义 | 在 020 中的体现 |
|---|---|---|---|
| P1 | **可数或可检查，并绑定 SHA** | 每一条都能用一个命令给出是或否，结果写成"在 `<sha>` 上" | "unit 2561 passed @ `0837d06`" |
| P2 | **每条断言都追溯到 spec 条款** | 测试矩阵的每个断言都标注它来自哪一条（§3 不变量 n、WI-x 验收 m、Un） | U8 → 不变量 1、3、8；E3 → WI-2 E3 与评审 D12 |
| P3 | **区分计划内和超纲** | 超纲断言不能留在测试里；它暴露出的真实缺陷要**登记为债务，写明 owner 和位置** | `total==total` 被移除，登记为 009 #63，owner 是 014 WI-19 |
| P4 | **绝不为了变绿削弱计划内测试** | 不删、不 skip、不放宽断言；要删测试必须有裁决引用 | E2 方案 A 只移除超纲部分，计划内的 E2 保持原样；018 的"声称创建"类测试改为反向断言，而不是删除 |
| P5 | **冻结路径 diff 为空** | 非 owner 在 `BASE..SHA` 上对冻结集的 diff 必须为空 | 020 的 `git diff --stat` 里没有 `helpers.py`、`conftest.py`、`baseline_1b/` 等 |
| P6 | **lane 通过数写到具体 HEAD** | 每条 lane 都写 pass/total/skip，外加 SHA；只写"绿了"不算 | 4 条 lane 的计数都记在 `0837d06` 上 |
| P7 | **环境失败不等于代码结论** | 超时、锁忙、CPU 压力导致的假红，要在锁内重跑并记录；不能据此判 FIX，也不能据此判 PASS | unit lane 在 600 s 超时时算环境失败，重跑 |
| P8 | **新 SHA 重开 CP** | 修复、rebase 或 amend 之后，原判定失效 | `950aefe` → `0837d06`；019 合入后，020 的 CP3 要重开 |

### 6.2 每个 CP 的验收清单

权威清单在 [`checkpoints.md`](user-level/skills/coordinate/references/checkpoints.md)，CP 与 tdd-guardian 命令的映射在 [`tdd-guardian.md`](user-level/skills/coordinate/references/tdd-guardian.md)。下表是操作视图：

| CP | 实现者必须报告 | 协调者独立复跑或 diff |
|---|---|---|
| CP0 | 用自己的话复述 SCOPE 和 FORBIDDEN；锁获取/释放成功；commit gate 可运行；`/tdd-guardian:status` 的输出；harness 冲突清单 | 对照 brief 检查复述有没有放宽 glob；有权限拒绝就交给用户，不绕行 |
| CP1 | WI 清单与 ACCEPTANCE 的一一映射；测试矩阵（每行附条款引用）；发现的 spec 矛盾（以问题形式提出） | 逐条检查可追溯性；标出"只测接线"的用例和缺失的边界用例；高风险 unit 可以要求跑 `tdd-spec-adversary`；也可以调用 `checkpoint-verifier`（CP1 模式，只读计划） |
| CP2 | branch、HEAD SHA、自 BASE 起的 commits、commit-gate lane 在该 SHA 上的 pass/total、改动文件、偏差 | `git -C <wt> log --oneline BASE..SHA`；`git -C <wt> diff --stat BASE..SHA`（范围）；`git -C <wt> diff --name-only BASE..SHA -- <冻结 globs>`（应为空）；在 SHA 上重跑决定性 lane（或交给 verifier 在 detached worktree 中跑）；检查被删除或被 skip 的测试是否都有裁决 |
| CP3 | CP2 的全部内容，再加 push-gate lane 的计数（e2e 注明"在锁内跑"）、review 发现及处理、每条 ACCEPTANCE 的证据（测试名或日志行）、trailer 状态、新登记的债务（owner 与位置） | 在锁内重跑 e2e；最终冻结路径 diff；如果前序合并已经落地，用 `git merge-base` 确认已 rebase；逐条核对 ACCEPTANCE 的证据；review 发现按严重度分流（correctness 必须修，style 可选） |

协调者的命令模板（**永远用 `git -C`，不要 `cd`**）：

```bash
WT=.claude/worktrees/020-debug-state ; BASE=1836a2a ; SHA=0837d06
git -C $WT rev-parse HEAD                                   # 报告的 SHA 还是当前 HEAD 吗
git -C $WT log --oneline $BASE..$SHA
git -C $WT diff --stat $BASE..$SHA
git -C $WT diff --name-only $BASE..$SHA -- tests/e2e/baseline_1b tests/e2e/conftest.py \
    tests/e2e/helpers.py tests/e2e/test_harness_smoke.py tests/fixtures/epub_corpus.py \
    tests/fixtures/epub_zip.py tests/fixtures/ai_stub.py tests/conftest.py   # 期望：空
git -C $WT log --format='%h %(trailers:key=Claude-Session,valueonly)' $BASE..$SHA
```

冻结集以 `soak-log.md` 表头和 `HASH_COVERED_PATHS`（`scripts/soak_run.py`）为准。上面这 8 个路径抄自 2026-09-30 的定义处，仅供示意；执行时从定义处取。注意根目录的 `tests/conftest.py` 也在其中，2026-09-30 下发给各 session 的规则漏了它（事后核查三条分支均未触碰）。

### 6.3 020 的验收标准块（协调者写进 brief 的样子）

由计划 §4 的 WI-0 到 WI-2 推导，每行末尾的方括号标注它的出处：

```text
ACCEPTANCE
 WI-0（只改文档）
  A0.1  grep -rn "9 个成员\|成员数为 9" docs/plans/20260817-frontend-ui-refactor/ → 0 行          [WI-0 验收 2]
  A0.2  契约 K5、plan K5、WI-15 验收 5、FR-K5 四处数字一致；契约全量枚举含 getDebugState(opts)   [WI-0 验收 2, D11]
  A0.3  WI-19 有一条指向计划 §3 的交叉引用                                                          [WI-0 验收 3]
  A0.4  §9 与看板的登记已由 1836a2a 完成；本分支不改 §9 与看板                                      [WI-0 第 1 步; 冲突图]
 WI-1（实现 + Vitest）
  A1.1  矩阵 U1–U18 每一个都有"先红"证据（tdd-guardian 收据），并逐条标注对应的 §3 不变量或 F 条目 [WI-1 验收 1]
  A1.2  fe-unit（npm test）@<CP2 SHA>：0 failed；报告 pass/total                                   [WI-1 验收 1]
  A1.3  npm run typecheck @<SHA>：exit 0                                                            [WI-1 验收 3]
  A1.4  新增代码中 grep "Reader3Epub.book\|getContentDocument" → 0 命中                             [WI-1 验收 2, 不变量 6]
  A1.5  Reader3Epub 成员数 = 10，与 A0.2 一致                                                       [WI-1 验收 4]
  A1.6  人工覆盖映射：21 条路径 → U 编号，无未映射项（写在报告里，WI-3/PR 再用）                   [WI-1 验收 5, D9]
  A1.7  U12：pill 文本三种输入逐字与改动前一致                                                       [WI-1 第 2 步, D6]
 WI-2（E2E）
  A2.1  uv run pytest tests/e2e/test_debug_state.py --browser chromium @<SHA>，在锁内：E1–E4 全过    [WI-2 验收 1]
  A2.2  unit（含分组守卫）@<SHA>：0 failed；计数常量按 --collect-only 实测增量上调，不写死           [WI-2 验收 2, F8]
  A2.3  git diff --name-only 1836a2a..<SHA> 与冻结集的交集 = ∅                                       [WI-2 验收 3, F7]
  A2.4  新用例不开 tracing、不加全量 request 监听                                                    [WI-2 验收 4]
  A2.5  E3 断言 notes API 返回新 id 且 diag 条数不变；不断言 "ok==true"                              [WI-2 E3, D12]
 Program 级（CP3）
  AP.1  push gate @<CP3 SHA>：unit、fe-unit、e2e（在锁内）、packaging 全部 0 failed，各报 pass/total/skip
  AP.2  unit passed 数 ≥ BASE 上的基线，且每个减少都有裁决引用（不允许静默删测试）
  AP.3  review 已在新上下文中运行；correctness 和 requirement 类发现都已修复，并且修复落在同一个被验收的 SHA 上
  AP.4  每个 commit 带 Claude-Session trailer，或已列为"合并时由用户处理"
  AP.5  超纲断言：0 条留在测试里；每条被移除的超纲断言都有对应的债务行（owner 与位置）
  AP.6  019 合入后：已 rebase 到新 master，重新计数，全部 gate 在新 SHA 上重跑（旧行作废）
```

### 6.4 坏写法与好写法

| 坏 | 好 | 为什么 |
|---|---|---|
| "测试通过" | "unit ≥2561 passed @ `<sha>`，0 failed；fe-unit 255/255；e2e 在锁内 244 passed / 16 skipped；packaging 11/11" | 可数，绑定 SHA，覆盖每条 lane |
| "不要动冻结文件" | "`git diff --name-only 1836a2a..<sha>` 与 `HASH_COVERED_PATHS` 的交集为 ∅" | 一条命令就能判定 |
| "实现 getDebugState" | "§3 契约 v1 的每个字段都有对应用例（U1–U18）；不变量 1–8 都至少有一个断言引用它" | 追溯到条款 |
| "测试覆盖充分" | "21 条路径，每条对应一个 U 编号，没有未映射项" | fe-unit 没有 coverage，只能人工映射 |
| "E2E 稳定" | "E1–E4 用 `wait_for_function` 轮询，5 s 超时，失败时输出最后一次 getter 结果；不用固定 sleep" | 规定了**怎么**稳定 |
| "修掉 review 的问题" | "M1/L1/L2 的修复落在 `0837d06`，CP3 在该 SHA 上重新验收" | 新 SHA 重开 CP |
| "计数常量改对" | "按 `uv run pytest tests/e2e --collect-only -q` 实测增量上调；019 合入后重新计数" | 不写死过期的数字（63/256 已经过期） |
| "修复失败的测试" | "18 个失败逐个分类：附带性依赖→setup 里 makedirs；声称会创建→反向断言；排除面只限 `.locks`，并正向断言它只含 `*.lock`" | 禁止用扩大排除面或删测试来换绿 |
| "e2e 红了，打回" | "e2e 在锁外、CPU 压力下红了 → 判为环境问题，在锁内重跑；只有重跑仍红才判 FIX" | 环境失败不等于代码结论 |

### 6.5 回复格式

格式定义在 [`dispatch-template.md`](user-level/skills/coordinate/references/dispatch-template.md) 末尾。三种示例如下。

**ACCEPT**

```text
CP3 ACCEPT at 0837d06
VERIFIED  复跑 @0837d06: unit 2561 passed; fe-unit 255; e2e 244 passed/16 skipped（锁内）; packaging 11.
          diff 1836a2a..0837d06: 8 files，全在 SCOPE 内；冻结路径 ∅；trailer OK。
FINDINGS  —
NEXT      STOP。等 019 合入；收到新 master SHA 后 rebase，重新计数 lint_e2e_groups.py /
          test_e2e_group_guard.py 常量，重跑全部 gate，按 CP3 重新报告。WI-3 在合入之后做。
```

**FIX**

```text
CP3 FIX at 950aefe
VERIFIED  <复跑的 lane 与结果>
FINDINGS  1. [M1] getDebugState 进度字段没有逐个收窄，非有限数会破坏不变量 3 —
             证据：<test/反例> — 期望：page/total/percent 逐个 narrow，任一不合规则整组 null，并补先红用例
          2. [L1] E2E 探针先记录后判定，E1–E3 的失败会在 E4 重复报红 — 期望：先判定再记录
          3. [L2] .vitest/ 输出未被忽略 — 期望：加进 .gitignore
NEXT      修复后以新 SHA 重新报告 CP3。
```

**BLOCKED**（来自 `checkpoint-verifier`，或协调者自己判定无法得出结论）：

```text
VERDICT  BLOCKED        CP3 @ <sha>
LANES    e2e: not run: lock HELD by <owner> past stated wait
SCOPE    clean
FROZEN   clean
FINDINGS —
NOTES    不是代码结论。锁持有者 <owner> 的释放被权限拒绝 → 已上报用户；协调者不代为释放。
```

---

## 7. 常见坑 / FAQ

| 现象 | 原因 | 做法 |
|---|---|---|
| E2E 在并行时偶发变红（#49 类） | CPU 压力 | E2E 跨 worktree 串行：`mkdir ~/.cache/reader3-e2e.lock` 加 owner 文件；unit 和 fe-unit 可以并行 |
| 某个 peer 的 `rm -rf` 释放锁被拒，其他人全部卡住 | 权限按 session 划分 | **由用户手动释放**。协调者不代为释放，也不让别的 peer 去做，否则就是洗权限（[`shared-lock.md`](user-level/skills/coordinate/references/shared-lock.md) 规则 5）。根本解法是 fcntl 包装器 `scripts/e2e_lock.py`：进程一死，内核就会释放锁，也就没有"释放"这一步 |
| reader-a3 的 harness 加不上 `Claude-Session` trailer | harness 冲突 | 属于用户决策。本次由用户在 merge commit 中补上。应该在 CP0 就列出来 |
| unit lane 超时（600 s） | 机器负载高 | 算环境失败并重跑，不作为代码结论（P7）。同时避免在 e2e 跑的时候并发跑重负载任务 |
| 协调者 `cd` 进 worktree 之后，后续命令跑到了错误的目录 | Bash 的 cwd 会保持 | **一律用 `git -C <worktree>`**，协调者永远留在主 checkout |
| 协调者一旦 `EnterWorktree`，再 `git -C` 主 checkout 就被拦截 | Claude Code 的 worktree 隔离检查 | 协调者不要进入 worktree；需要在 worktree 里执行的工作交给实现者或 verifier |
| verifier 跑 lane 时和 peer 互相干扰 | 在 peer 的 live worktree 里跑，HEAD 会变，还会残留产物 | verifier 按定义用 `git worktree add --detach <tmp> <SHA>`，结束后 `remove --force` 并 `prune` |
| 实现者收不到消息，或者消息弹出批准框后 5 分钟失效 | `crossSessionInbound` 的默认行为：bypass 模式的接收方会扣留非 bypass 发送方的消息 | 各 session 使用一致的权限模式，或者由你设置 `crossSessionInbound`；用 `/list-agents` 自查 |
| `/list-agents` 不被识别 | 版本太低，不支持跨 session 消息 | 用 `claude --version` 检查（macOS 需要 v2.1.224 或以上） |
| rebase 之后沿用了旧的 ACCEPT | 忽视了"新 SHA 重开 CP" | 合并会让所有下游 ledger 行作废；重新在新 base 上验收 |
| 实现者顺手加了"更严格"的断言，然后红了 | 超纲断言 | 移除该断言；真实缺陷登记为债务并写明 owner；计划内的测试不动 |
| 把 program 事实写进了 bindings | 分层错误 | 分支号、行分配、脏文件都写进 `protocol.md`；bindings 只放指针 |
| store 或 worktree 出现在 `git status` 里 | 本 repo 没有忽略 `.claude/coordination/` 和 `.claude/worktrees/` | 协调者只用 pathspec commit；是否添加忽略条目由你决定 |

---

## 8. 与其它工具的关系

| 工具 | 关系 |
|---|---|
| **tdd-guardian** | 实现者用它实现，协调者**从不**运行 `/tdd-guardian:workflow`。CP 的映射见 [`tdd-guardian.md`](user-level/skills/coordinate/references/tdd-guardian.md)：CP0 对应 `:status`；CP1 对应 `:plan` 加 `:design-tests`（可选 `tdd-spec-adversary`）；CP2 对应 commit gate；CP3 对应 push gate 加 `:review`。lane 状态按 worktree 分开，也不入库，所以协调者的验收仍以它自己在 SHA 上的复跑为准。**Gate 完整性**：lane 状态只能由 gate 工具运行已配置的命令写入，禁止手写，也禁止从插件版本化缓存路径导入 |
| **plan-and-branch-map** | bindings 的 `DEFINITION_SITES` 与 `ALLOCATION` 都指向它。分支号只从迁移计划 §9 取；执行顺序以看板为准；里程碑状态的语义（Allocated / 🚧 / ✅）在它里面定义。改 `docs/plans/` 之前必须先加载它：[`plan-and-branch-map`](../../../.claude/skills/plan-and-branch-map/SKILL.md) |
| **Codex 审议（cc-suite）** | 遵循全局 *Decision Support* 规则：有长期代价的决策（顺序、scope 拆分、设计形态）可以提供"让 Codex 参与审议"的选项；可逆的执行决策由协调者自己定、记录、继续推进。本套件的 core/bindings 拆分本身就经过了 Codex 与 Opus 的评审 |
| **cursor pstack** | 设计来源之一。借鉴了 `poteto-mode` 的 Orchestrate playbook（"You own the program, never the code"、brief 字段、原文粘贴的常驻指令、按 SHA 记的验收台账、用副作用判断存活、升级清单）、`swarm` 的 PASS/ISSUES/BLOCKED、`show-me-your-work` 的决策 TSV。**不借鉴**的部分：云端 worker、Graphite 堆栈、自动合并、大规模调度。**我们新增**的部分：CP1（写代码前的设计检查点）、冻结路径 owner、不洗权限、锁 pre-flight、"裁决要回写到 spec"。详见设计调研 |
| **全局 CLAUDE.md 的 *Orchestration*** | 那条规则管 session **内部**的 subagent，本套件把它扩展到 **peer session**。原则相同：分析、编排、验证留在协调者手里，执行交出去 |

**本文核实所用的官方文档**（2026-09-30 抓取）：

- 跨 session 消息：<https://code.claude.com/docs/en/cross-session-messaging>
- CLI 参数（`--name/-n`、`/rename`、`--worktree/-w`、`--resume`）：<https://code.claude.com/docs/en/cli-reference>
- Worktree（`EnterWorktree`、隔离检查、手动 `git worktree add`、`.gitignore` 建议）：<https://code.claude.com/docs/en/worktrees>
- Skills（`disable-model-invocation`、`user-invocable`、存放位置）：<https://code.claude.com/docs/en/skills>
- Subagents（`~/.claude/agents/`，按 `name` 调用，`model`/`tools` 字段）：<https://code.claude.com/docs/en/sub-agents>

---

## 9. 附：套件文件中发现的不一致

1. **checkpoint-verifier 的路径**：core 只按名字引用它，装到 `~/.claude/agents/` 就能解析（见 3.1）。如果把它放进 skill 目录，就解析不到。当前源码不需要修改，但安装时要注意这一点。
2. **（已修复 2026-09-30）core 的 description 里的触发短语无效**：`disable-model-invocation: true` 下只有 `/coordinate` 能触发。description 已改为明写“只由 /coordinate 触发”。
3. **（已修复 2026-09-30）“永远用 `git -C`”没有写进 core**：core §5 已加“不要 `cd` 进 peer 的 worktree，用 `git -C` / 子 shell / verifier 的 detached worktree”。`dispatch-template.md` 里给实现者的 “cd there” 保持不变。
   同批修复：core §5 与 `dispatch-template.md` 新增 **BLOCKED** 回复（检查跑不起来：环境、锁、权限、未知 SHA；不是对代码的判定），并写明 verifier 的 PASS/ISSUES/BLOCKED 如何对应 ACCEPT/FIX/BLOCKED；core §6 新增“超时、被 kill、runner 错误、锁忙都是环境失败，既不判 FIX 也不判 PASS，重跑并记录，反复出现则把 gate 设置交用户决定”。
4. **store 和 worktree 目录没有被忽略**：core §3 已改为"用 `git check-ignore` 验证"，这是正确的。但本 repo 实测 `.claude/coordination/` 和 `.claude/worktrees/` 都没有被忽略，要么加忽略条目，要么坚持只用 pathspec commit。
5. **过渡期的锁与 `shared-lock.md` 冲突**：本轮 `protocol.md` 的 E2E 互斥使用裸 `rm -rf` 释放，违反了 `shared-lock.md` 回退方案的规则 1（"acquire、release、status、break 都放在一个入库脚本里，并预先批准"）；这次释放被拒事故正是规则 1 所预言的。bindings 的 `LOCKS` 已经如实标注为 PLANNED 或过渡期，最终修复是 `scripts/e2e_lock.py`。另外，`checkpoint-verifier` 在 mkdir 锁下同样需要释放权限，在 fcntl 包装器落地之前，verifier 复跑 e2e 也可能遇到同样的释放拒绝。
6. **bindings 的 description 在实现者 session 中始终可见**（`user-invocable: false` 的特性）；worktree 里也有入库的副本。core 要求读主 checkout 的那一份并记录 blob SHA，这能兜住版本差异，但实现者 session 理论上可能自行加载 worktree 里那份。影响很小，知道即可。
7. **repo 内的小漂移（不属于套件）**：`plan-and-branch-map` 的文件夹表仍写着"frozen-set debt window, number not yet allocated"，而同一文件的里程碑表已经写着 `019-frozen-set-debts` Allocated。收尾时由协调者一并修正。
