# Git Worktree Workflow (This Repo)

`git worktree` lets you work on multiple branches at the same time without repeatedly switching branches (and without cloning the repo multiple times). This repo uses separate branches for different feature tracks (e.g. `001-search-features`, `002-ai-assistant`, `003-add-book-notes`), which makes worktrees especially useful.

## When To Use It

- You want to implement code on one branch while writing specs/docs on other branches.
- You want to keep “dirty” working directories isolated (no accidental cross-branch edits).
- You frequently rebase/merge from `master` and don’t want to interrupt other work.

## Recommended Layout

Keep your main repo and worktrees side-by-side:

```bash
cd /path/to/reader3-pro
mkdir -p ../reader3-pro-wt
```

Create one worktree per branch:

```bash
git fetch origin
git worktree add ../reader3-pro-wt/001 001-search-features
git worktree add ../reader3-pro-wt/002 002-ai-assistant
git worktree add ../reader3-pro-wt/003 003-add-book-notes
```

List worktrees:

```bash
git worktree list
```

## Daily Workflow (Professional Routine)

1. Open 2–3 terminals (or editor windows), one per worktree:
   - `../reader3-pro-wt/001`: implementation + running the app
   - `../reader3-pro-wt/002`: specs/plans/contracts for AI assistant
   - `../reader3-pro-wt/003`: specs for book notes
2. Start each session with:

```bash
git fetch origin
```

3. Sync with `master` (choose one approach):
   - Rebase (cleaner history): `git rebase origin/master`
   - Merge (safer/less rewriting): `git merge origin/master`

4. Commit and push in the worktree you changed:

```bash
git status
git add -A
git commit -m "docs: update 002 spec"
git push
```

## Creating A New Branch Worktree

Create a new branch from `origin/master` and mount it immediately:

```bash
git fetch origin
git worktree add -b 004-my-feature ../reader3-pro-wt/004 origin/master
```

Notes:
- One branch can only be checked out in **one** worktree at a time.
- If you need a second workspace, create a second branch (e.g. `004-my-feature-wip`).

## Removing Worktrees (Clean Up)

```bash
git worktree remove ../reader3-pro-wt/003
git worktree prune
```

Avoid deleting the folder manually; if you do, run `git worktree prune` afterwards.

## Troubleshooting

- “Branch already checked out”: that branch is mounted in another worktree. Use `git worktree list` to find it.
- Stale metadata after deleting folders: run `git worktree prune`.
- Unclear which branch a folder is on:
  - `git -C ../reader3-pro-wt/002 branch --show-current`

## Using Claude Code / Codex Effectively With Worktrees

Best practice is **one agent session per worktree**:

- In the `001` session: restrict changes to implementation files (`server.py`, `reader3.py`, `templates/`, `static/`).
- In the `002`/`003` sessions: restrict changes to `specs/002-ai-assistant/**` or `specs/003-add-book-notes/**`.

This keeps diffs reviewable and prevents “spec edits leaking into implementation commits” (and vice versa).

