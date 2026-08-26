# ADR-0011: API v1 冻结——`tests/contract/routes.snapshot` 是路由的唯一清单，按集合比对；Phase 2 不改响应形状，Phase 3 只许新增字段

| 字段 | 值 |
|---|---|
| Status | Accepted |
| Decision date | 2026-08-24（commit `fe8f473`，AGENTS.md 公告；同日 commit `bba0927` 落地机械执行者） |
| Recorded date | 2026-08-25 |
| Record type | Prospective |
| Original rationale known | Yes |
| Confidence | High |
| Current compliance | Full |
| Evidence | `AGENTS.md:75-95`（「API v1 冻结（008 起生效）」全段）；`tests/contract/routes.snapshot:1-14`（收录范围与集合比对说明）、正文 48 行（`grep -vc '^#'` 核实）；`tests/contract/test_route_inventory.py:1-14`（docstring，「mechanical enforcer of the v1 freeze」）、`:30-41`（`current_inventory()` 只收集 `METHOD path` 字符串）、`:54-67`（`test_路由清单与快照一致`，`set` 差集断言）；`docs/plans/20260816-tech-stack-migration/tasks/008-test-safety-net.md:141-149`（§4 三层组织）、`:307-314`（§8 API v1 冻结）；`docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:107`（C4 耦合点）、`:124`（合同 3）、`:138`（合同 3 的规则：Phase 2a/2b 不改形状，Phase 3 只加字段）；commit `fe8f473`（AGENTS.md 公告）；commit `bba0927`（48 条路由三层契约，任务书验收写 42、实测 48，集合比对让这个差异可读）；`CLAUDE.md:61-67`（Key API endpoints，冻结对象的摘要） |
| Confirmation | `uv run pytest tests/contract/test_route_inventory.py`（`test_路由清单与快照一致`、`test_快照文件本身是排好序的`、`test_每条快照行都能解析成方法和路径` 三条）；已核实存在，且在 `.claude/tdd-guardian/config.json` 的 `unit` lane 里，gate 于 `commit`／`taskCompleted` |

## Context and Problem Statement

011（后端重构）与 013/014（TypeScript 前端重写）要并行推进：011 拆 `web/server.py` 到多个 router，013/014 照着现有响应形状写新前端。两条线共享同一份 API，但没有共同的、机器可查的「今天 API 长什么样」的定义处，就没法回答一个具体问题：**011 的某次改动，是不是在前端不知情的情况下动了它正在依赖的接口？**

不做这个决定，后果是前端在另一条分支上静默地对着不存在或变了形的契约编码，问题要等到集成阶段才会暴露，那时已无法归因是哪次改动引入的（`plan-tech-stack-migration.md:107` C4）。008 分支已经把「测试永远只在改坏时才红」立成判准（`AGENTS.md`「Testing Guidelines」），所以这里要解决的不是「写一份文档说明 API 长什么样」，而是「让一次擅自改动在同一个 commit 里就红」。

## Decision Drivers

- 011 与 013/014 必须能并行推进而不互相阻塞（`plan-tech-stack-migration.md:107`「Phase 3 给响应加字段。坚持加法式演进则前端永不阻塞；一旦改名或改语义，两条线立刻锁死」）。
- 008 已经把「改坏了会不会红」立为测试判准（`AGENTS.md`「Testing Guidelines」），冻结必须落成同一类机械检查，不能只是文档约定。
- 011 拆分 router 时最容易犯的错误是路由在搬家过程中丢失或前缀写错（`test_route_inventory.py:7-10`）；需要一条能在拆分当下就报错的测试，而不是等前端联调时才发现。
- 冻结要能在 code review 里被一眼看见是「故意的」还是「意外的」（`routes.snapshot:3-4`：「这份文件是给 code review 的 diff 看的」）。

## Considered Options

1. **快照集合比对 + 冻结**（选定）——`app.routes` 生成的 `METHOD path` 集合与 `routes.snapshot` 做差集比对，改动必须同一个 commit 里更新快照。代价：每次合法的路由变更都要多改一个文件，且这个文件只挡「路由存在与否」，不挡响应体形状。
2. **不冻结，靠契约测试逐条守**——只用 `test_route_contracts.py` 的六组表驱动断言状态码与响应 schema，不设集合快照。为什么不：前端迁移期间后端若同时改动响应形状，契约测试只在事后报错（跑起来才知道哪条路由的哪个字段变了），无法在 PR diff 里事先标出「这次改动触碰了 v1 的边界」；一旦前端已经按旧形状写完代码，问题就变成两条分支上的行为都无法归因到具体哪次改动。
3. **引入 OpenAPI diff 工具**（如 `openapi-diff` 一类）比对 `/openapi.json` 的历史版本——为什么不（推断，标明）：仓库已经产出 `/openapi.json`（`routes.snapshot:42`），理论上可行；但快照文件本身已经能给出二值判定（红/绿）且零依赖，多引入一个 diff 工具只是把同一个判定换一种更重的实现方式，008 分支的判准是「够用就不加」，没有查到当时实际讨论过这个选项的记录。

## Decision Outcome

`tests/contract/routes.snapshot` 是 API v1 的唯一清单，由 `test_route_inventory.py` 用 `app.routes` 生成的集合与它做差集比对，不比对数量。任何路由的增删改，两步都要做：先在同一个 commit 里改快照，再在 PR 描述里写明破坏性与迁移路径。冻结之下 Phase 2（011 拆 router）不得改变任何响应形状（`test_route_contracts.py` 的六组表驱动契约即证明）；Phase 3（012 存储格式）只能新增字段，不得改名、不得改语义、不得改默认值。**明确不做**：不冻结路由的声明顺序（集合比对本就与顺序无关，`routes.snapshot` 本身排序只是为了让 diff 好读，由另一条测试单独守）；不冻结请求体/响应体字段的类型（那是 layer 2 契约测试的职责，不在 `routes.snapshot` 的比对范围内）；不覆盖 013/014 迁移完成之前以外的任何时间点——冻结随 014 合入解除。

## Consequences

### Positive
- 011 拆分 router 时，路由丢失或前缀写错会在本地 `commit` 门禁就变红，而不是等前端联调时才发现。
- Phase 3 的加法式演进规则把「API 会不会阻塞前端」从口头约定变成一条可执行的边界：只要 `routes.snapshot` 不变、`test_route_contracts.py` 不变，013/014 就可以确信响应形状没有变化。
- PR review 的判断成本降到看一眼 `routes.snapshot` 的 diff：加一行还是删一行、还是路径改了，一目了然（`routes.snapshot:3-4`）。

### Negative
- 011 重构期间容易「顺手」改坏接口：本地门禁在 `commit`/`taskCompleted` 触发，但 CI 只在发版时跑且不设 required check（`AGENTS.md`「Testing Guidelines」），`TDD_GUARD_BYPASS=1` 能绕过本地门禁，冻结不是不可逾越的硬约束。
- Phase 3「只许新增字段」容易堆出事实上的「v1.5」：字段只加不减、语义只能靠新字段表达，长期下去响应体会越来越臃肿，而冻结本身没有规定何时集中清理这些新增字段。
- `routes.snapshot` 按集合比对：核实 `current_inventory()`（`test_route_inventory.py:30-41`）只收集 `f"{method} {route.path}"` 字符串，装进 `set`。这意味着（a）路由的声明顺序完全不影响判定——这不是遗漏而是设计如此；但也意味着（b）请求体、查询参数、响应体字段的**类型**变化完全不在这条测试的抓取范围内，因为它们根本不出现在 `route.path` 或 `route.methods` 里。这类变化要靠 `test_route_contracts.py` 的六组表驱动契约单独守，而 AGENTS.md「API v1 冻结」段落点名的唯一机械执行者只是 `routes.snapshot` + `test_route_inventory.py`，没有把 layer 2 也纳入「冻结」这个词的范围——读者容易误以为「冻结」覆盖了形状的一切维度，实际只覆盖路由的存在性。

### Neutral
- `routes.snapshot` 全量收录 FastAPI 自带的四条文档路由（`/docs`、`/openapi.json` 等）和 `/static` 挂载点，理由是判据为「这个 ASGI app 现在对外服务哪些地址」而非「哪些地址是我们手写的」（`routes.snapshot:8-11`）；升级 FastAPI 若改了文档路由，这条测试会红一次，属预期内。
- 冻结不是永久状态，是 013/014 施工期间的临时边界；014 合入即解除，届时 v1 这个名字本身也需要重新定义（是否引入 v2、是否废弃已堆积的新增字段）。

## Revisit When

- 014（M4b，TS 前端 reader）合入 master：冻结按计划解除，写一份 superseding ADR 定义 v2 规则（是否清理 Phase 3 期间堆积的新增字段、是否需要正式的版本号前缀）。
- 出现一次不得不破坏响应形状的安全修复：这类修复允许绕开「只加不改」的规则，但必须在同一个 commit 里更新 `routes.snapshot`/契约测试并在 PR 里显式声明「这是一次经批准的破坏性变更」，而不是静默绕过。

## Related

- ADR-0000（`docs/adr/0000-use-adrs.md`）——本文遵循的记录规则与四层文档分工。
- ADR-0008、ADR-0010、ADR-0013——同批（首批 0001–0013）收录的相邻决定，见 `docs/adr/README.md` 索引（尚未建立时以文件名查找）。
- `AGENTS.md:75-95`「API v1 冻结（008 起生效）」——约束摘要保留在原地，理由、方案比较与到期条件的唯一定义处现为本文件，AGENTS.md 不重述。
- 原定义处：`docs/plans/20260816-tech-stack-migration/tasks/008-test-safety-net.md:307-314`（§8「API v1 冻结」）与 `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:138`（「合同 3 的规则」）——两处已于 2026-08-26 改为指向本 ADR 的一行链接。
