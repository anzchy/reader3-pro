# 前端 UI 重构（2026-08-17）

这个文件夹装的是**前端那一半规划**：把 Reader3 Pro 的界面从「Jinja 模板 ＋ 五千行原生 JS」重做成 TypeScript ＋ Vite 多页、带完整设计系统、五条降级状态和可失败测试的前端。设计规格、标注宿主契约、全部工作项、前端测试矩阵**都在这里**。

对应分支：`010-design-degradation-states`、`013-ts-frontend-shell`、`014-ts-frontend-reader`，以及 `015-launch-experience` 里的 PWA 部分。

> **另一半在哪**：后端分层、存储格式、测试网与 CI、分支编号分配在
> [`docs/plans/20260816-tech-stack-migration/`](../20260816-tech-stack-migration/README.md)。
> 两个文件夹的「权威范围」表**不重叠**，合起来才是全集。

## 先读哪个

| 顺序 | 文件 | 读它是为了 |
|---:|---|---|
| 1 | [`plan-frontend-ui-refactor.md`](./plan-frontend-ui-refactor.md) | **入口**。事实基线（§1）、WI-1–WI-20 工作项（§4）、前端测试矩阵（§5）、`/tdd-guardian:workflow` 的调用方式（§0） |
| 2 | [`spec-frontend-design.md`](./spec-frontend-design.md) | 设计规格：现状实测 D1–D7、双层 token、八个基础组件、逐页规格、降级状态 DEG-S1–DEG-S5、响应式、a11y |
| 3 | [`contracts/annotation-host-contracts.md`](./contracts/annotation-host-contracts.md) | 标注宿主契约 K1–K6：`annotations.js` 对 DOM、事件、`window.Reader3Epub` 的六条隐式依赖 |
| — | [`../../../designs/reader-pro-next/README.md`](../../../designs/reader-pro-next/README.md) | 可运行原型 ＋ 原型到生产的翻译规则（哪些可移植、哪些不可移植） |

**这里没有 `tasks/` 目录。** 前端不再按分支拆任务文件——所有工作项都在 `plan-frontend-ui-refactor.md` §4 的 `### WI-N:` 标题里，`/tdd-guardian:workflow` 直接读那些标题。原先的 `tasks/010-design-degradation-states.md` 与 `tasks/014-ts-frontend-reader.md` 已整条改组进 WI，内容一条不丢。

## 权威范围

同一个事实只有一处定义，其他地方一律链接过去、不复述——复述会漂移。本文件夹是这些事实的 canonical 定义点：

| 事实 | 唯一定义处 |
|---|---|
| 双层 design token（Tier 1 `--p-*` → Tier 2 `--r3-*`）、三阅读主题、明暗 | `spec-frontend-design.md` §3 |
| 八个基础组件的规格与变体（含 `Toast` / `Skeleton` 尚不存在这一事实） | `spec-frontend-design.md` §5 |
| 设置页 / 书库页 / 阅读器的逐页规格 | `spec-frontend-design.md` §6.1 / §6.2 / §6.3 |
| **降级状态 DEG-S1–DEG-S5** 的定义、色彩语义、可关闭性、testid 要求 | `spec-frontend-design.md` §6.4 |
| iframe 边界的 **A/B/C 三重断言**（含 `bodySignature` 实现） | `spec-frontend-design.md` §6.0 |
| 响应式断点与移动端功能性不可达的实测结论 | `spec-frontend-design.md` §7 |
| a11y 六项 | `spec-frontend-design.md` §8 |
| **标注宿主契约 K1–K6** | `contracts/annotation-host-contracts.md` |
| **前端工作项 WI-1–WI-20** | `plan-frontend-ui-refactor.md` §4 |
| **前端测试矩阵**（按钮态 / 面板与焦点 / 键盘与 a11y / 数据态 / 降级 / 响应式 / 主题解析） | `plan-frontend-ui-refactor.md` §5 |
| `annotations.js` 八模块拆分表与四条依赖规则 | `plan-frontend-ui-refactor.md` WI-14 |

## 编号约定

**降级状态一律写作 `DEG-S1`…`DEG-S5`。** 加前缀是为了和 `/tdd-guardian:workflow` 的规格层级编号 `S1`–`S6` 区分——两套编号原先都叫 `S1`，同一份计划里同时出现会指错对象。完整声明见 `spec-frontend-design.md` §6.4。

技术栈迁移文件夹里的 GSTACK 评审原文与 `eng-review-tasks.jsonl` 保留写作当时的裸编号，**不追改**。

## 不由本计划定义的事实

引用，不重述：

| 事实 | 定义在 |
|---|---|
| **分支编号分配（全仓库唯一真相源）** | [`20260816-tech-stack-migration/plan-tech-stack-migration.md` §9](../20260816-tech-stack-migration/plan-tech-stack-migration.md) |
| Phase 依赖图、各 Phase 进入 / 退出门槛、soak 门槛 | 同上 §9.1 / §7 |
| `data-testid` 命名 canonical 正则、三条 lint（选择器 / 命名 / token 悬空）的边界 | 同上 §6（0.5、0.8） |
| Playwright E2E 用例 ID 与激活分组 | [`tasks/009-e2e-annotations.md`](../20260816-tech-stack-migration/tasks/009-e2e-annotations.md) |
| API v1 冻结清单、覆盖率门槛数值 | [`tasks/008-test-safety-net.md`](../20260816-tech-stack-migration/tasks/008-test-safety-net.md) |
| 两文件提交协议、读取状态机三态 | [`plan-tech-stack-migration.md`](../20260816-tech-stack-migration/plan-tech-stack-migration.md) Phase 3 |
| 第二轮 Codex 评审台账（一次评审的记录不拆开） | [`review-codex.md`](../20260816-tech-stack-migration/review-codex.md)，其中五条前端项在 `plan-frontend-ui-refactor.md` §6 继承 |

> **下一个该开哪条分支**，看 [`../20260824-frontend-backend-plan-progress.md`](../20260824-frontend-backend-plan-progress.md)——执行顺序的唯一定义处。

`007-hygiene-and-contracts` 的 **0.4 / 0.5 / 0.8 三项是本计划的前置契约**，在那条分支上实施，本计划只消费。**✅ 三项已交付并随 007 于 2026-08-24 合入 `master`，前置全部解除**（合入记录见[那边的「合入记录」一节](../20260816-tech-stack-migration/tasks/007-hygiene-and-contracts.md)，本文不重述）。

## 不在这个文件夹里的东西

- [`designs/reader-pro-next/`](../../../designs/reader-pro-next/README.md) —— 前端原型。它是**可运行的**（`index.html` ＋ `*.jsx`，React 18 ＋ 浏览器内 Babel），是目标形态的可执行规格，所以留在 `designs/` 下而不是计划文件夹里。⚠️ 它的 `spec/screenshots/` 里 22 张 PNG 记录的是**现状 UI**，不是设计目标，**任何验收标准都不许写成「与截图一致」**
- `specs/_archive/` —— 已发布功能的历史 spec-kit 记录，**冻结，代码是权威**，不要照着实施

## 这件事做完之后

`015-launch-experience` 合入 master 之后，这个文件夹整体归档或删除。它描述的是「还没做的事」，不是「做过什么的记录」——后者去看代码和 git 历史。
