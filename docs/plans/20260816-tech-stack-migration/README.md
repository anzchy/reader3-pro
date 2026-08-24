# 技术栈迁移（2026-08-16）

这个文件夹装的是**后端与工程基建那一半规划**：把 Reader3 Pro 的后端从「单文件 FastAPI + pickle」演进到分层结构与可迁移存储格式，把测试网与 CI 建起来，并给前端重构准备好契约与门槛。计划、评审记录、后端各分支任务清单**全部在这里**，不散落到 `specs/` 或 `docs/contracts/`。

对应分支区间：`007-hygiene-and-contracts` → `015-launch-experience`（其中 010 / 013 / 014 的前端部分归另一份计划，见下）。

> **另一半在哪**：前端 UI 重构（设计规格、组件、降级状态、`annotations.js` 拆分、前端 TDD 测试矩阵）已拆到
> [`docs/plans/20260817-frontend-ui-refactor/`](../20260817-frontend-ui-refactor/README.md)。
> 两个文件夹的权威范围**不重叠**——本文的「权威范围」表和那边的表合起来才是全集。

## 先读哪个

| 顺序 | 文件 | 读它是为了 |
|---:|---|---|
| 1 | [`plan-tech-stack-migration.md`](./plan-tech-stack-migration.md) | **唯一计划**。技术栈选型（§1.1、§10）、三条工作线怎么合流（§2–§5）、每个 Phase 做什么（§6）、门槛表（§7）、分支编号分配（§9）、依赖图（§9.1）、两轮评审原文与 A1–A5 / B1–B4 / C1–C5 / R1–R15（附录 A、B） |
| 2 | [`review-codex.md`](./review-codex.md) | 第二轮 Codex 评审原文 ＋ 文首的落地记录表（哪几条已处置、落在哪、现落在哪个文件夹） |
| — | [`eng-review-tasks.jsonl`](./eng-review-tasks.jsonl) | 第一轮工程评审 R1–R12 的处置台账，全部 `done`；其中 R1/R2/R3/R5/R12 的落点已随拆分迁到前端计划 |

> **2026-08-17：本文件夹此前有两份计划**——`plan-ui-migration-sequencing.md`（什么顺序做）与
> `plan-tech-stack-migration.md`（做什么）。二者已合并为后者一份，前者**已删除**，章节编号原样保留
> （§3 合同 / §4 汇合点 / §6 阶段分解 / §7 门槛表 / §9 分支编号 / §9.1 依赖图），旧引用按同一编号跳转即可。

前端设计规格与标注宿主契约不在本文件夹，见
[`20260817-frontend-ui-refactor/spec-frontend-design.md`](../20260817-frontend-ui-refactor/spec-frontend-design.md)
与
[`20260817-frontend-ui-refactor/contracts/annotation-host-contracts.md`](../20260817-frontend-ui-refactor/contracts/annotation-host-contracts.md)。

## 权威范围

同一个事实**只有一处定义**，其他地方一律链接过去、不复述——复述会漂移。本文件夹是这些事实的 canonical 定义点：

| 事实 | 唯一定义处 |
|---|---|
| 两文件提交协议（`manifest.json` ＋ `chapters.jsonl`） | `plan-tech-stack-migration.md` Phase 3 |
| 读取状态机三态（missing / corrupt / valid） | `plan-tech-stack-migration.md` Phase 3 |
| `data-testid` 命名正则（canonical 代码块） | `plan-tech-stack-migration.md` §6（0.5） |
| 三条 lint 的约束边界（选择器 / 命名 / token 悬空） | `plan-tech-stack-migration.md` §6（0.5、0.8） |
| Phase 依赖图与关键路径 | `plan-tech-stack-migration.md` §9.1 |
| 每个 Phase 的进入 / 退出门槛、soak 门槛 | `plan-tech-stack-migration.md` §7 |
| **分支编号分配（全仓库唯一真相源）** | `plan-tech-stack-migration.md` §9 |
| Playwright E2E 用例清单与激活分组 | `tasks/009-e2e-annotations.md` |
| API v1 冻结清单、覆盖率门槛数值 | `tasks/008-test-safety-net.md` |

前端计划**引用**上面这些定义，不重述。反过来，双层 token、组件清单、逐页规格、iframe 边界的 A/B/C 三重断言、降级状态 DEG-S1–DEG-S5、标注宿主契约 K1–K6 一律由前端计划定义，本文件夹只链接。

> **下一个该开哪条分支**，看 [`../20260824-frontend-backend-plan-progress.md`](../20260824-frontend-backend-plan-progress.md)——执行顺序的唯一定义处。本文件夹定义依赖，那份定义顺序。

## `tasks/`

一个分支一个文件，`tasks/{分支名}.md`。**只放后端与工程基建分支**；前端分支不再有独立任务文件，它们的工作项写在前端计划正文的 `### WI-N:` 里。

- [`tasks/007-hygiene-and-contracts.md`](./tasks/007-hygiene-and-contracts.md) —— Phase 0 七项止血，含逐项验收与哪几项适合交给 `/tdd-guardian:workflow`。其中 0.4 / 0.5 / 0.8 产出的是**前端计划的前置契约**。**✅ 八项全部完成，分支已于 2026-08-24 合入 `master`**——合入记录（PR / 合并 commit / CI 首跑）定义在该文件的「合入记录」一节
- [`tasks/008-test-safety-net.md`](./tasks/008-test-safety-net.md) —— Phase 1a 的测试网：覆盖率门槛策略、42 条路由契约、异常处理规则、性能基准、CI
- [`tasks/009-e2e-annotations.md`](./tasks/009-e2e-annotations.md) —— Phase 1b 的 E2E 用例清单（读路径 / 写路径 / K1–K6 / DEG-S1–DEG-S4），含 `baseline-1b` 与按阶段激活的 acceptance 分组。前端计划的测试矩阵**引用本文的用例 ID**，不重写用例

011 / 012 / 015 **故意还没写**——骨架**领先一个分支即时补**，且「领先一个」按
**依赖顺序**数而非编号顺序，理由见
[`plan-tech-stack-migration.md` §9](./plan-tech-stack-migration.md#9-里程碑与分支唯一真相源)。
这是 Codex 评审第 9 条的处置方式。

## 不在这个文件夹里的东西

- [`docs/plans/20260817-frontend-ui-refactor/`](../20260817-frontend-ui-refactor/README.md) —— 前端 UI 重构计划：设计规格、标注宿主契约、`### WI-N:` 工作项、前端 TDD 测试矩阵。分支 010 / 013 / 014 与 015 的 PWA 部分归那边
- [`designs/reader-pro-next/`](../../../designs/reader-pro-next/README.md) —— 前端原型。它是**可运行的**（自带 `.vmark/` 工具链和 22 张截图），不是计划文档，所以留在 `designs/` 下。原型 → 生产的翻译规则、现状审计、parity 清单都在那边
- `specs/_archive/` —— 已发布功能的历史 spec-kit 记录，**冻结，代码是权威**，不要照着实施

## 这件事做完之后

后端里程碑全部落地、`015-launch-experience` 合入 master 之后，这个文件夹整体归档或删除。它描述的是「还没做的事」，不是「做过什么的记录」——后者去看代码和 git 历史。
