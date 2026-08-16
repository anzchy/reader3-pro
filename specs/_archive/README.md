# specs/_archive — 已发布功能的历史记录

**代码是唯一权威。不要从这里实施任何东西。**

本目录下的文档由已停用的 spec-kit 框架生成（`/speckit.specify` → `/speckit.plan` → `/speckit.tasks`），
描述的是 2025 年 12 月前后已经发布的功能。它们保留在仓库里只有一个用途：**回答"当时为什么这么设计"**。

## 为什么要归档

`specs/` 现在承担的是另一件事。计划文档
[`docs/plans/20260816-tech-stack-and-ui-changes/plan-ui-migration-sequencing.md`](../../docs/plans/20260816-tech-stack-and-ui-changes/plan-ui-migration-sequencing.md) §9
把 `specs/{分支名}/tasks.md` 定义为**活跃分支的任务清单**存放处。
两种文档形态相同、编号规则相同、放在同一个目录下，但生命周期相反——
一批是"已经做完的记录"，一批是"还没做的清单"。

这个混淆已经造成过实际代价：`001-search-features/tasks.md` 的 T027 至今写着 `- [ ]`，
读起来就是一条待办，而它指向的 `SearchIndex` 早已作为死代码删除。
2026-08-16 的第二轮 Codex 评审（发现 #2）正是抓到了这一点。

**本目录合计 171 条未勾选的 `- [ ]`，全部属于已发布或已被取代的功能。**

| 目录 | 未勾选条目 | 状态 |
|---|---:|---|
| `001-search-features` | 7 | ✅ 已发布。T027 / T030 已作废，T029 部分作废（详见该目录文首横幅） |
| `002-ai-assistant` | 23 | ✅ 已发布（多 provider + RAG） |
| `003-add-book-notes` | 113 | ⚠️ **从未按此设计实施**。批注功能实际由 `006-hot-fix` 落地，形态不同 |
| `004-library-bulk-indexing` | 22 | ✅ 已发布（三栏库页、集合、批量索引） |
| `005-dedao-style-ui-reorganization` | — | ✅ 已发布。无 tasks.md，只有样式指南与 HTML 原型 |
| `006-hot-fix` | 6 | ✅ 已发布（全屏分页阅读器 + 标注） |

`003` 最需要警惕：`CLAUDE.md` 长期把它标为"Spec 阶段"，但那 113 条任务描述的是一套
**没有被实现的**批注系统。照着它干活会去重建已经存在的东西。

## 现在的约定

- **一次规划工作 = 一个文件夹**：计划、设计规格、跨分支契约、评审记录、各分支任务清单
  全部放在 `docs/plans/{日期}-{主题}/` 下。当前唯一在进行的是
  [`docs/plans/20260816-tech-stack-and-ui-changes/`](../../docs/plans/20260816-tech-stack-and-ui-changes/README.md)
- 分支任务清单 → 该文件夹的 `tasks/{分支名}.md`，分支编号由其 `plan-ui-migration-sequencing.md` §9 统一分配
- `specs/` 现在只剩本 `_archive/`
- spec-kit 工具链（`.specify/`、`.claude/commands/speckit.*`）已于 2026-08-16 移除
