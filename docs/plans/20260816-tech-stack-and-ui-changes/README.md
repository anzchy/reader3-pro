# 技术栈迁移 × 前端重设计（2026-08-16）

这个文件夹装的是**一整件规划工作**：把 Reader3 Pro 的后端从「单文件 FastAPI + pickle」演进到分层结构与可迁移存储格式，同时把前端从 vanilla JS 迁到 TypeScript 并落地新的设计规格。计划、设计规格、跨分支契约、评审记录、各分支任务清单**全部在这里**，不散落到 `specs/` 或 `docs/contracts/`。

对应分支区间：`007-hygiene-and-contracts` → `015-launch-experience`。

## 先读哪个

| 顺序 | 文件 | 读它是为了 |
|---:|---|---|
| 1 | [`plan-ui-migration-sequencing.md`](./plan-ui-migration-sequencing.md) | **入口**。三条工作线怎么合流、每个 Phase 的门槛、依赖图（§9.1）、分支编号分配（§9） |
| 2 | [`plan-tech-stack-migration.md`](./plan-tech-stack-migration.md) | 技术栈选型、后端分层、存储格式、A1–A5 / B1–B4 / C1–C5 各项做什么 |
| 3 | [`spec-frontend-design.md`](./spec-frontend-design.md) | 双层 token、`data-testid` 命名、组件清单、逐页规格、iframe 边界（§6.0）、降级状态 S1–S5（§6.4） |
| 4 | [`contracts/annotation-host-contracts.md`](./contracts/annotation-host-contracts.md) | 标注宿主契约 K1–K6——前端重构期间**不得破坏**的跨分支接口 |
| 5 | [`review-codex.md`](./review-codex.md) | 第二轮 Codex 评审原文 ＋ 文首的落地记录表（哪几条已处置、落在哪） |
| — | [`eng-review-tasks.jsonl`](./eng-review-tasks.jsonl) | 第一轮工程评审 R1–R12 的处置台账，全部 `done` |

## 权威范围

同一个事实**只有一处定义**，其他地方一律链接过去、不复述——复述会漂移。目前的 canonical 定义点：

| 事实 | 唯一定义处 |
|---|---|
| 两文件提交协议（`manifest.json` ＋ `chapters.jsonl`） | `plan-tech-stack-migration.md` Phase 3 |
| 读取状态机三态（missing / corrupt / valid） | `plan-tech-stack-migration.md` Phase 3 |
| `data-testid` 命名正则 | `plan-ui-migration-sequencing.md` §6 |
| iframe 边界判定的 A/B/C 三重断言 | `spec-frontend-design.md` §6.0 |
| Phase 依赖图与关键路径 | `plan-ui-migration-sequencing.md` §9.1 |
| 分支编号分配 | `plan-ui-migration-sequencing.md` §9 |
| 标注宿主契约 K1–K6 | `contracts/annotation-host-contracts.md` |

## `tasks/`

一个分支一个文件，`tasks/{分支名}.md`。目前写好四个：

- [`tasks/007-hygiene-and-contracts.md`](./tasks/007-hygiene-and-contracts.md) —— Phase 0 七项止血，含现状实测（0.7 已完成、0.6 部分完成）与哪几项适合交给 `/tdd-guardian:workflow`
- [`tasks/008-test-safety-net.md`](./tasks/008-test-safety-net.md) —— Phase 1a 的测试网：覆盖率门槛策略、42 条路由契约、异常处理规则、性能基准、CI
- [`tasks/009-e2e-annotations.md`](./tasks/009-e2e-annotations.md) —— Phase 1b 的 E2E 用例清单（读路径 / 写路径 / K1–K6 / S1–S4），含 `baseline-1b` 与按阶段激活的 acceptance 分组
- [`tasks/014-ts-frontend-reader.md`](./tasks/014-ts-frontend-reader.md) —— `annotations.js` 八模块拆分与 4B 各子阶段任务

010 / 011 / 012 / 013 / 015 **故意还没写**——骨架**领先一个分支即时补**，理由见
[`plan-ui-migration-sequencing.md` §9](./plan-ui-migration-sequencing.md#9-里程碑与分支唯一真相源)。
这是 Codex 评审第 9 条的处置方式。

## 不在这个文件夹里的东西

- [`designs/reader-pro-next/`](../../../designs/reader-pro-next/README.md) —— 前端原型。它是**可运行的**（自带 `.vmark/` 工具链和 24 张截图），不是计划文档，所以留在 `designs/` 下。原型 → 生产的翻译规则、现状审计、parity 清单都在那边。
- `specs/_archive/` —— 已发布功能的历史 spec-kit 记录，**冻结，代码是权威**，不要照着实施。

## 这件事做完之后

七个里程碑全部落地、`015-launch-experience` 合入 master 之后，这个文件夹整体归档或删除。它描述的是「还没做的事」，不是「做过什么的记录」——后者去看代码和 git 历史。
