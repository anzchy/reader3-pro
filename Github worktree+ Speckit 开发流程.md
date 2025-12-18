

下面把 **Claude Code 的 git worktree 并行会话**（你给的链接）和 **GitHub Spec Kit（specify-cli + /speckit.\*）的 specs 文件夹**串起来，给一套“每个 branch 对应一个 feature spec 目录（spec/plan/tasks 等 Markdown）+ 并行开发”的实操流程。

------

## 0) 概念对齐：worktree 解决“并行隔离”，Spec Kit 解决“规格资产化”

- **git worktree**：同一 repo 同时检出多个分支到不同目录；每个目录文件状态隔离，适合开多个 Claude Code 会话并行推进。([Claude Code](https://code.claude.com/docs/zh-CN/common-workflows))
- **Spec Kit**：在你的工作区落地一套规格驱动流程；你在 AI 助手里用 `/speckit.constitution / specify / plan / tasks / implement`，产物会写到仓库里的 `specs/<id>-<slug>/`（含 `spec.md / plan.md / tasks.md` 等），并随 git 版本化。([GitHub](https://github.com/github/spec-kit))
- Spec Kit 明确支持 **Claude Code / Codex CLI / Gemini CLI**（都能跑 /speckit.*）。([GitHub](https://github.com/github/spec-kit))

------

## 1) 一次性初始化（只做一遍，建议在 main）

### 1.1 安装并初始化 Spec Kit 到现有项目

Spec Kit 的 README 推荐用 `uv` 安装 `specify-cli`，并在已有项目里 `specify init`：([GitHub](https://github.com/github/spec-kit))

```bash
# 安装（推荐持久安装）
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git

# 在现有仓库初始化（示例：以 claude 作为 agent）
specify init . --ai claude
# 或：specify init --here --ai claude
```

初始化后，你仓库里会出现类似结构（重点：`.specify/` 和 `specs/` 目录、模板、脚本等）：([GitHub](https://github.com/github/spec-kit))

```text
.specify/
  memory/constitution.md
  scripts/...
  templates/...
specs/
  001-<feature>/
    spec.md
    plan.md
    tasks.md   # 后续生成
```

把这些初始化产物 **commit 到 main**，后面每个 feature 分支都能复用。

------

## 2) “每个分支一个新功能 spec 目录”的并行 worktree 工作流（Step-by-step）

> 目标：你同时做 Feature A、Feature B；每个 feature = 一个分支；每个分支里都有自己的 `specs/<id>-<slug>/spec.md plan.md tasks.md ...`；每个分支各用一个 worktree 目录 + 一个 AI 会话。

### 2.1 创建并行 worktrees（每个 worktree 一个分支）

Claude Code 官方示例就是 `git worktree add ... -b <branch>`，然后进入该目录跑 `claude`。([Claude Code](https://code.claude.com/docs/zh-CN/common-workflows))

```bash
git checkout main
git pull

mkdir -p .worktrees

# Feature A
git worktree add .worktrees/feat-001 -b feat/001-email-login main

# Feature B
git worktree add .worktrees/feat-002 -b feat/002-billing main
```

现在你会有两个隔离目录：

- `.worktrees/feat-001`（branch: feat/001-email-login）
- `.worktrees/feat-002`（branch: feat/002-billing）

各开一个终端窗口（或 IDE 窗口）进入对应目录。

------

## 3) 在每个 worktree 里跑 Speckit：生成 specs// 下的 spec/plan/tasks

### 3.1 在 worktree 里启动 AI 助手（Claude/Codex/Gemini 都行）

Spec Kit 的说明是：在项目目录启动你的 AI assistant，然后就能用 `/speckit.*`。([GitHub](https://github.com/github/spec-kit))
Claude Code 的并行会话建议：每个 worktree 单独跑一个 `claude`，互不干扰。([Claude Code](https://code.claude.com/docs/zh-CN/common-workflows))

**以 Feature A 为例：**

```bash
cd .worktrees/feat-001
claude
```

### 3.2 在 Claude Code 里按流程跑（会把文件写进本分支）

1. 建立项目原则（只需要第一次；也可以在 main 做完后不重复）

```text
/speckit.constitution ...
```

([GitHub](https://github.com/github/spec-kit))

1. 创建该功能的规格目录与 spec.md（重点：会落到 `specs/<id>-<slug>/spec.md`）

```text
/speckit.specify <描述你要做的功能（what/why）>
```

([GitHub](https://github.com/github/spec-kit))

1. 生成技术方案 plan（会生成 `plan.md`，并可能带 research/quickstart/contracts 等）([GitHub](https://github.com/github/spec-kit))

```text
/speckit.plan <你的技术栈/架构约束>
```

1. 生成任务拆解 tasks.md（Spec Kit 会从 plan 生成 tasks；tasks 里包含依赖顺序、文件路径、TDD 顺序、并行标记等）([GitHub](https://github.com/github/spec-kit))

```text
/speckit.tasks
```

1. 执行实现（按 tasks 系统化实现）([GitHub](https://github.com/github/spec-kit))

```text
/speckit.implement
```

------

## 4) “并行分支 + specs 目录”最容易踩坑：编号冲突怎么解决

因为每个分支里都会产生 `specs/<id>-<slug>/...`，并行时如果两条分支都用 `001-*`，合并回 main 会冲突。

实操里我建议二选一：

### A) 用“唯一 ID”，别用全局递增号

例如：`specs/gh-<issue_id>-<slug>/` 或 `specs/20251218-<slug>/`。这样并行永不冲突（最省心）。

### B) 仍用 001/002，但要“先占号再开工”

在 main 上先建一个占位目录（或用团队约定的登记文件），push 后再分支并行，确保每个 feature 拿到不同号。

> Spec Kit 自带脚本目录里包含 `create-new-feature.sh` 等脚本（可用于自动化“新功能目录”的创建/编号管理），你也可以直接读脚本逻辑并改成适合你团队的“占号规则”。([GitHub](https://github.com/github/spec-kit))

------

## 5) 你要的“worktree + 多模型分工”如何落地（推荐映射）

Spec Kit 已标注支持 **Claude Code、Codex CLI、Gemini CLI**。([GitHub](https://github.com/github/spec-kit))
你可以把分工映射到 worktree：

- **worktree A（feat/001…）**：Claude Code 负责 `/speckit.implement` 与代码改动
- **worktree B（feat/002… 或 docs/…）**：Codex CLI 负责补写/整理 `spec.md / plan.md / tasks.md / quickstart.md`（只动 specs 目录）
- **worktree C（review/…）**：Gemini CLI 读取 `git diff` + specs，输出 review 结论并补 docs

这样每个 AI 会话上下文天然隔离（Claude 文档强调 worktree 的隔离优势）。([Claude Code](https://code.claude.com/docs/zh-CN/common-workflows))

------

如果你愿意，我可以按你仓库当前约定（比如你到底想 `specs/` 放在根目录还是 `spec/`；分支命名规则；是否要“文档分支与代码分支分离”）给你一份**可直接复制到 README 的团队规范**，并附上：

- “创建新 feature：一条命令生成 worktree + 创建 specs 目录 + 打开对应 AI”的脚本范式
- 防止 specs 编号冲突的自动检查（pre-commit / CI）