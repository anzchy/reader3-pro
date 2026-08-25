# ADR-0000: 采用 ADR 记录架构决策，并规定它与 CLAUDE.md / docs/*.md / docs/plans/ 的分工

| 字段 | 值 |
|---|---|
| Status | Accepted |
| Decision date | 2026-08-25 |
| Recorded date | 2026-08-25 |
| Record type | Prospective |
| Original rationale known | Yes |
| Confidence | High |
| Current compliance | Full |
| Evidence | `CLAUDE.md`「Two folders may split one effort, but never one fact」；`docs/plans/20260816-tech-stack-migration/README.md` 权威范围表与「015 合入后整体归档或删除」；`docs/plans/20260817-frontend-ui-refactor/README.md` 同；`specs/_archive/README.md`（spec-kit 退役原因） |
| Confirmation | none（人工）：`docs/adr/README.md` 索引行数 = 目录下 `NNNN-*.md` 文件数。接入 `lint.yml` 的机器检查待办 |

## Context and Problem Statement

reader3-pro 的决策理由记录得很密，但放在三种**寿命不对**的容器里：

- **会被删除的文档。** 两个 `docs/plans/` 文件夹都在自己的 README 里声明「015 合入后整体归档或删除」。而「两文件提交协议（canonical，全仓库唯一定义处）」「读取状态机三态」「保留 Python 不迁 TS 的完整成本分析」只存在于那里。015 合入那天，这些理由随文件夹一起消失。
- **没有索引的 docstring、`pyproject.toml` 注释、workflow 头部。** 写得很好（很多条连「别删」「这次偏离是故意的」都写了），但只有碰巧打开那个文件的人看得到。
- **哪里都没记。** 最老的一批结构性决定——pickle、文件系统即数据库、双重身份、`lru_cache(10)`、epub.js、ChromaDB + MiniLM——只有现状，没有原因。

同时仓库有一条比一般项目更硬的文档规则：**每条事实只有一个家**（`CLAUDE.md`：「restating is how the two copies drift apart」）。任何新增的记录形态如果复述既有段落，就违反了这条规则。

所以问题不是「要不要补历史」，而是：**在 plans/ 被删除之前，把仍会约束未来的那一小撮决定，搬进一个不会被删、且不与既有文档重复的地方。**

## Decision Drivers

- plans/ 文件夹的既定生命周期：015 合入后删除，不可更改（那是两个 README 各自的权威事实）。
- 「每条事实只有一个家」规则：新容器必须**取代**旧定义处，不能并存。
- 单人维护、LLM 大量参与编码：约束必须能被 LLM 在改代码前读到，且短。
- 仓库已经有大量**机器执行的确认**（`routes.snapshot`、`check_coverage_gate.py`、`lint_testid_naming.py`、回滚测试、egress 测试），ADR 应该指向它们，而不是另写一遍文字。
- 不能回到 spec-kit 那种「文档与代码分叉后文档说谎」的状态（`specs/_archive/README.md` 记录了它为什么被退役）。

## Considered Options

1. **`docs/adr/` 作为「幸存者层」**（选定）——只收「plans/ 删除后仍需要有人知道的约束」；每写一条就让它成为唯一定义处，原处改成链接。代价：写入时必须同步改原处，一次 commit 动两个文件。
2. **把 canonical 段落留在 plans/，只在归档时整体搬**——为什么不：归档时一次性搬 ~20 段，没有人会逐条补「考虑过的方案 / 负面后果 / Revisit When」；结果是一堆没有理由的 Overview，不是 ADR。
3. **全部写进 CLAUDE.md**——为什么不：CLAUDE.md 是给 LLM 的约束摘要，每次会话都会被读取；塞进理由、方案和后果会让它膨胀到失去摘要的作用。
4. **不引入 ADR，靠 git log**——为什么不：本仓库的 commit subject 是「Implement X」式的，`357fe2a`（换成 epub.js）什么理由都没写；git log 只能定日期，不能定理由。

## Decision Outcome

引入 `docs/adr/`，按 MADR 变体模板（`template.md`）记录。四种文档的分工固定如下：

| 位置 | 职责 | 写什么 | 不写什么 |
|---|---|---|---|
| `CLAUDE.md` / `AGENTS.md` | 给 LLM 和人的**约束摘要** | 一行规则 + `→ ADR-000n` | 理由、方案、后果 |
| `docs/*.md` | **Architecture Overview**：现在是什么样 | 数据位置、文件布局、环境变量 | 为什么 |
| `docs/plans/` | **RFC + 台账 + 排序**，随 015 归档 | 方案比较过程、TODOS、处置台账、执行顺序 | 需要长期存活的约束 |
| `docs/adr/` | **幸存者层**：仍约束未来的决定 | 决定、驱动、方案、后果、确认、重访条件 | 过程、台账 |

**准入判据**（两条都满足才写 ADR）：

1. 5 问打分 ≥ 2：半年后有人问为什么 · 影响多模块或公开接口 · 有 ≥2 个合理方案 · 回滚成本高 · 涉及安全/性能/可靠性；
2. 它的唯一定义处目前在一份会被删除的文档里，**或者**根本没有定义处（只有现状）。

第二条把大多数候选筛掉：`pyproject.toml` 注释、docstring、lint 脚本、`routes.snapshot`、tdd-guardian config 都是长寿容器，理由留在原地即可。

**明确不做：**
- 不回填全部历史。首批 13 份（0001–0013）覆盖今天仍在生效、且定义处将消失或不存在的决定；其余的按「改到哪里补到哪里」，在对应分支的第一个 commit 里建 Proposed。
- 不把 TODOS、ET、R1–R15、Codex 处置台账搬进 ADR——那是过程记录，随 plans/ 归档。
- 不为「正在退出」的状态写 ADR（例如 `lru_cache(10)`）；它作为替代者那份 ADR 的 Context 出现。

## Consequences

### Positive
- plans/ 归档不再丢失理由。
- 「唯一定义处」规则得到延续而不是被破坏：ADR 是搬家，不是复印。
- Retrospective ADR 强制区分 Observed State / Original Rationale / Current Assessment，不再有人把今天的推断写成当年的理由。

### Negative
- 每写一份 ADR 就要同步改原定义处，一次 commit 至少动两个文件；忘了改就是两份漂移。
- 首批 13 份里有 5 份（0001–0005）的原始理由是 `Unknown`——它们的价值在于阻止误改，不在于解释历史，读者可能失望。
- 又多了一个「改代码前要读」的地方。缓解：CLAUDE.md 的原则表逐条指向 ADR，LLM 不需要遍历目录。
- 索引（`README.md`）目前靠人工维护；机器检查未接入。

### Neutral
- `template.md` 里的九个元数据字段是本仓库的扩展，不是 MADR 标准。
- ADR 编号与分支编号无关；分支编号仍只在 `plan-tech-stack-migration.md` §9 分配。

## Revisit When

- 出现第二位常驻贡献者（约束摘要与理由的读者变了）。
- 015 合入、plans/ 归档之日：核对是否有 canonical 段落漏搬。
- `docs/adr/` 超过 30 份：说明准入判据第二条被绕过了，收紧。

## Related

- 首批：ADR-0001 … ADR-0013，索引见 `README.md`。
- `CLAUDE.md`「Constitution Principles」逐条指向对应 ADR。
- 方法来源：`~/Documents/07_图书馆/生成式AI-产品开发/adr-best-practices-new-and-existing-projects.md` §一（5 问）、§三（存量项目六原则）、§六（反模式）。
