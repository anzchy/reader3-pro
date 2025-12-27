# Git Worktree + Speckit Workflow (This Repo)

This repo uses Spec Kit (“Speckit”, via `specify-cli` and `/speckit.*`) and a multi-branch workflow where each feature lives in:

- a **branch** (e.g. `001-search-features`, `002-ai-assistant`, `003-add-book-notes`)
- a **spec directory** under `specs/<id>-<slug>/` (e.g. `specs/002-ai-assistant/`)

`git worktree` lets you work on multiple branches at the same time (multiple working directories, one shared `.git` object database). This is the cleanest way to:

- implement code in one feature branch while writing specs/plans in another
- run multiple AI sessions (Claude Code / Codex) in parallel without cross-branch edits

---

## 0) One-Time Setup (From Scratch)

### 0.1 Clone and set up worktree base directory

```bash
git clone git@github.com:anzchy/reader3-pro.git
cd reader3-pro
mkdir -p ../reader3-pro-wt
```

### 0.2 Initialize Spec Kit (only once, commit to `master`)

If the repo does not yet have `.specify/` and `specs/`, initialize Spec Kit in `master` so all feature branches inherit the tooling.

```bash
# install the CLI (recommended)
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git

# initialize in this repo (choose your primary AI)
specify init . --ai claude
```

Commit the scaffolding (`.specify/`, templates, etc.) to `master`.

---

## 1) Recommended Worktree Layout (This Project)

Keep worktrees next to the main repo, one per branch:

```bash
git fetch origin
git worktree add ../reader3-pro-wt/master master
git worktree add ../reader3-pro-wt/001 001-search-features
git worktree add ../reader3-pro-wt/002 002-ai-assistant
git worktree add ../reader3-pro-wt/003 003-add-book-notes
git worktree list
```

Suggested mapping:

- `../reader3-pro-wt/001`: implementation-heavy work (backend/UI/search)
- `../reader3-pro-wt/002`: AI assistant specs + later implementation
- `../reader3-pro-wt/003`: book notes spec + later implementation

#### 复制 Master 分支到 001 和 002 branch 的操作步骤

你要的是：**001、002 两个分支都以 master 为起点创建**，并且分别检出到不同 worktree 目录。

直接用 `-b`（创建新分支）+ 指定起点 `master`：

```
git worktree add -b 001-search-features ../reader3-pro-wt/001 master
git worktree add -b 002-ai-assistant   ../reader3-pro-wt/002 master
```

含义：

- 从 `master` 当前指向的提交创建新分支 `001-search-features`，并检出到 `../reader3-pro-wt/001`
- 从 `master` 当前指向的提交创建新分支 `002-ai-assistant`，并检出到 `../reader3-pro-wt/002`

> 这不是“复制 master 分支本身”，而是 **从 master 的 HEAD 分叉出两个新分支**（效果等同你理解的“从 master copy 出来”）。

#### 如果分支已经存在（只想检出到 worktree）

那就去掉 `-b`：

```
git worktree add ../reader3-pro-wt/001 001-search-features
git worktree add ../reader3-pro-wt/002 002-ai-assistant
```



---

## 2) Professional Parallel Workflow (Docs vs Code, Multi-Branch)

The core rule: **one terminal/editor + one AI session per worktree**.

### 2.0 Example setup for this repo (typical)

Common parallel scenario:

- `001-search-features`: you are actively implementing/searching/running the app
- `002-ai-assistant`: you are drafting specs/plans/tasks (docs-first)
- `003-add-book-notes`: you are drafting specs (docs-first)

Worktrees keep these changes physically separated so you can commit/push/PR independently.

### 2.1 Start parallel sessions

- Terminal A: `cd ../reader3-pro-wt/001` (Codex for code)
- Terminal B: `cd ../reader3-pro-wt/002` (Claude Code for spec/plan/tasks)
- Terminal C: `cd ../reader3-pro-wt/003` (Claude Code for spec/plan/tasks)

### 2.2 Keep branches isolated by file scope

Before committing, always verify you only touched what the branch owns:

```bash
git status
git diff --name-only
```

Practical rule for this repo:

- spec-only branches should mostly touch `specs/<feature>/**`
- implementation branches can touch `server.py`, `reader3.py`, `templates/`, `static/`, etc.

---

## 3) Speckit Flow (Per Feature Branch)

Run Speckit inside the **feature branch worktree** so all generated files land on the correct branch.

Example: create the 002 AI Assistant spec set in `../reader3-pro-wt/002`.

### 3.1 Create/update the feature spec (`spec.md`)

In Claude Code or Codex (inside that worktree):

```text
/speckit.specify  (describe what/why; keep it user-facing)
```

This should create or update:

- `specs/002-ai-assistant/spec.md`

### 3.2 Produce the implementation plan

```text
/speckit.plan
```

Outputs typically include:

- `specs/002-ai-assistant/plan.md`
- optional: `research.md`, `data-model.md`, `contracts/*.yaml`, `quickstart.md`

### 3.3 Generate task breakdown

```text
/speckit.tasks
```

Outputs:

- `specs/002-ai-assistant/tasks.md` (dependency-ordered checklist)

### 3.4 Implement against tasks

```text
/speckit.implement
```

Work style:

- implement small slices
- update `tasks.md` by marking completed items `[x]`
- keep PRs reviewable

---

## 3.5 From-Zero “Step-by-Step” (New Feature in This Repo)

This is the recommended end-to-end workflow when starting a brand-new feature (example: `004-example-feature`).

### Step 1 — Reserve an ID (avoid conflicts)

On `master`, reserve a new folder name in `specs/` (or use a unique naming scheme).

```bash
cd ../reader3-pro-wt/master
git pull --rebase
mkdir -p specs/004-example-feature
git add specs/004-example-feature
git commit -m "chore(spec): reserve 004-example-feature"
git push
```

### Step 2 — Create a feature branch + worktree

```bash
cd /path/to/reader3-pro
git fetch origin
git worktree add -b 004-example-feature ../reader3-pro-wt/004 origin/master
```

### Step 3 — Spec-first in the feature worktree (Claude Code recommended)

```bash
cd ../reader3-pro-wt/004
```

In Claude Code:

- `/speckit.specify` → writes/updates `specs/004-example-feature/spec.md`
- `/speckit.plan` → writes `plan.md` (+ optional `data-model.md`, `contracts/`, `research.md`)
- `/speckit.tasks` → writes `tasks.md`

Commit the spec set early:

```bash
git add specs/004-example-feature
git commit -m "docs(spec): add 004 example feature spec set"
git push -u origin 004-example-feature
```

Optional (recommended): open a “spec-only PR” early to get alignment before implementing.

### Step 4 — Implement against `tasks.md` (Codex recommended)

In Codex (same worktree):

- `/speckit.implement` (or implement manually task-by-task)
- update `specs/004-example-feature/tasks.md` by marking `[x]`

Keep implementation commits small:

```bash
git add -A
git commit -m "feat(004): implement <small slice>"
git push
```

### Step 5 — Open PR and keep branches synced

- PR: `004-example-feature` → `master`
- During review: `git fetch origin && git rebase origin/master` (or merge) and force-push only if your repo policy allows it.

### Step 6 — Repeat in parallel (multiple features)

For `005-another-feature`, repeat Steps 1–5 in a new worktree (`../reader3-pro-wt/005`). Parallel work remains isolated.

## 4) Avoiding Specs Directory ID Conflicts

This repo currently uses sequential IDs:

- `specs/001-search-features/`
- `specs/002-ai-assistant/`
- `specs/003-add-book-notes/`

If multiple people/branches create new features in parallel, you can collide on `specs/001-*`.

Recommended options:

1. **Reserve IDs in `master` first** (create an empty `specs/004-.../` folder, commit, then branch).
2. Switch to a unique scheme (e.g. `specs/20251218-<slug>/` or `specs/gh-<issue>-<slug>/`).

---

## 5) Branch Sync + PR Workflow (Keeping `master` Clean)

Daily (per worktree):

```bash
git fetch origin
git rebase origin/master   # or: git merge origin/master
```

When ready:

```bash
git add -A
git commit -m "docs: update 002 specs"
git push
```

Then open a PR:

- `002-ai-assistant` → `master` (spec-only PR) or keep it long-lived until implementation starts
- `001-search-features` → `master` (code PR with screenshots/tests)

---

## 6) Claude Code vs Codex: Practical Division of Labor

### Claude Code (best for spec-driven writing + review)

Use in spec worktrees:

- write/iterate `spec.md` with acceptance criteria
- run `/speckit.plan` and `/speckit.tasks`
- review “alignment” between spec/plan/contracts

Guardrail prompt (recommended):

> “Only modify `specs/002-ai-assistant/**`. Do not touch implementation code in this session.”

### Codex (best for implementation + refactors + verification)

Use in implementation worktrees:

- execute `/speckit.implement`
- change Python/HTML/JS code
- run local checks (server, manual flows)
- keep commits scoped to tasks

Guardrail prompt (recommended):

> “Follow `specs/002-ai-assistant/tasks.md`. Update tasks by marking `[x]`. Don’t edit other specs.”

---

## 7) Worktree Ops Cheatsheet

Create a new branch + worktree:

```bash
git fetch origin
git worktree add -b 004-my-feature ../reader3-pro-wt/004 origin/master
```

Remove a worktree:

```bash
git worktree remove ../reader3-pro-wt/003
git worktree prune
```

Find which branch a directory is on:

```bash
git -C ../reader3-pro-wt/002 branch --show-current
```

---



## 对之前的 branch 的修改有 bug，需要 hot fix 怎么办？

不要在原来的 branch 上面做修改。

确保之前的 branch 代码已经 Pull Request 到 master。

新建 branch 譬如 007-hot-fix，新建 worktree-007，把 master 代码下载到 worktree。

然后继续写 spec，写 plan，写代码。把代码 push 到 branch 007-hot-fix。



## Troubleshooting

- “Branch already checked out”: that branch is mounted in another worktree. Use `git worktree list`.
- Deleted a worktree folder manually: run `git worktree prune`.
- Accidentally edited wrong branch: use `git diff --name-only` and move changes via `git checkout <sha> -- <path>` or cherry-pick commits.
