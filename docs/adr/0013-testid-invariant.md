# ADR-0013: `data-testid` 是新旧两套 UI 之间唯一的不变量——命名先在原型定、再回贴到 Jinja 模板；E2E 选择器只许 testid 与 ARIA；三条零依赖 lint 守它

| 字段 | 值 |
|---|---|
| Status | Accepted——但 Decision Outcome 里「`[data-testid="…"][data-*="…"]` 复合形态适用于哪些元素」这一个子命题已由 [ADR-0014](0014-bounded-testid-enumeration.md) 取代（2026-08-31）：有界集合改为逐个枚举唯一字面量，复合形态只留给无界 id。本文其余部分全部继续有效，正文按规则不改。 |
| Decision date | 2026-08-17（`git log -S'testid' -- plan-tech-stack-migration.md` 最早命中 `5d43c80`；`testid` 契约随两份计划合并进入现文件，两条 lint 的落地在 007，commit `308a9b3`，2026-08-23） |
| Recorded date | 2026-08-25 |
| Record type | Prospective |
| Original rationale known | Yes |
| Confidence | High |
| Current compliance | Full |
| Evidence | `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:127`（strangler-fig 接缝陈述）、`:201`（0.5 全量补齐 ＋ E2E 只许 testid/ARIA）、`:210-211`（两条 lint 的表格）、`:215-223`（canonical 正则段落——唯一真相源，正文不复述）；`docs/plans/20260817-frontend-ui-refactor/spec-frontend-design.md:690-703`（§4 五条规则）、`:720-722`（`lib-`/`rd-`/`set-` 前缀表）、`:726,737`（§4.1 对账：138 站点、24 个形似合规、改名后 0 违规）；`docs/plans/20260816-tech-stack-migration/contracts/testid-rename-map.md:1-9`（权威范围声明）、`:16-38`（§1 134→138 计数订正）、`:308-331`（§8.1 回贴清单，152/221）、`:364-397`（§8.3 贴不上的 69 个及分类）；`docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md:398,406,408,437`（WI-6：`Modal` 的 `data-testid` 改为必填 prop、无默认值）；`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md:4,78`（E2E 进入条件依赖 0.5；选择器规则复述）；`scripts/lint_e2e_selectors.py:1-25`；`scripts/lint_testid_naming.py:1-23,40-48`；`.github/workflows/lint.yml:36-57`（`contracts` job，三步分开跑） |
| Confirmation | `python3 scripts/lint_e2e_selectors.py`（选择器 lint：`tests/e2e/` 只许 `[data-testid="…"]` 及可选 `[data-*="…"]` 复合、ARIA 走 Playwright 的 `get_by_*` API，不经过被扫的字符串）；`python3 scripts/lint_testid_naming.py`（命名 lint：`templates/*.html` 与 `designs/reader-pro-next/` 里每个 testid 必须匹配 `CANONICAL` 正则）；两者由 `.github/workflows/lint.yml` 的 `contracts` job 在**发版**（`push.tags` / `release.published` / `workflow_dispatch`）时跑，**不是每次 push**——见 Negative |

## Context and Problem Statement

Phase 4（`docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md` 的 4A/4B）要把 `templates/*.html` + 原生 JS 逐页替换成 `designs/reader-pro-next/` 里定型的 TS/JSX 实现，替换期间两套 DOM 同时存在，标注 E2E（009 分支）必须在整个替换过程里保持可信。若 E2E 用 class 或 DOM 结构定位元素，Phase 4 的任何布局改动都会推翻整套 E2E——而那套 E2E 正是 Phase 4 合并的门槛。不做决定的后果是：testid 命名各写各的、E2E 选择器悄悄退回 class，改版一次挂一次，无法用同一份测试证明"新旧实现行为一致"。

## Decision Drivers

- Phase 4 是逐页 strangler-fig 替换（`plan-tech-stack-migration.md:167`），新旧 DOM 会长期共存，需要一个跨两侧都稳定的锚点。
- 迁移正确性要用同一份 E2E 在替换前后各跑一遍来证明；换一套测试等于放弃这个证明。
- `designs/reader-pro-next/` 原型先于生产模板拿到新设计的全部元素（主题切换、降级状态等），生产模板反过来推导会漏项。
- CI 只在发版时跑（`lint.yml:10`），日常靠开发者本地手跑零依赖脚本；契约必须能被脚本机械核验，不能停留在"人工遵守"。
- `zh-CN` 已裁定为唯一交付 locale（`spec-frontend-design.md:27`），文案会持续变动，不能承担定位职责。

## Considered Options

1. **`data-testid` 作为唯一接缝，先原型后模板，三条 lint 守正则与选择器**（选定）——见 Decision Outcome。代价：改名成本与 69 个故意留空的覆盖缺口，见 Negative。
2. **用 CSS class 或 DOM 结构做选择器**——为什么不：Phase 4（含 013 的 shell、014 的阅读器）要整体重写 DOM 与样式，`plan-frontend-ui-refactor.md` 的组件清单（`Button` 七套收敛为 `.r3-btn` 等）本身就是这次要动的东西；class 必然变，选择器 lint 存在的唯一理由就是拦住这条路（`lint_e2e_selectors.py:9-11`）。
3. **用文本内容选择**——为什么不：`spec-frontend-design.md:27` 已裁定 `zh-CN` 为唯一交付语言且无第二 locale，但文案本身仍会随迭代改动（该文件 `:5` 记录了一次语言判定的推翻）；用会变的文案做定位锚点，稳定性还不如 class。
4. **不做跨实现的 E2E，新旧各写一套**——为什么不：迁移正确性的论证依赖"同一份 E2E 在替换前后都跑绿"（`plan-tech-stack-migration.md` §4 的两条论证之一）；新旧各写一套等于放弃这个论证，"标注恢复到错误位置"这类问题会失去唯一的检测手段。

## Decision Outcome

`data-testid` 是 Phase 4 替换期间新旧两套 UI 之间**唯一**允许变化边界之外的锚点：命名规则（`{page}-{region}-{element}`，前缀 `lib-`/`rd-`/`set-`，见 `spec-frontend-design.md:690-722`）**先在 `designs/reader-pro-next/` 原型里定名，再回贴到 `templates/*.html` 与生成 DOM 的 JS**，不能反过来（`plan-tech-stack-migration.md:127`）。`tests/e2e/` 的选择器**只允许** `data-testid`（含 `[data-testid="…"][data-*="…"]` 复合形态）与 ARIA role/name，禁止 class、`nth-child`、层级结构选择器（`plan-tech-stack-migration.md:201`）。命名的 canonical 正则**唯一定义处是 `scripts/lint_testid_naming.py`**（见该文件 `CANONICAL` 常量），本文与 `plan-tech-stack-migration.md:219-221` 的代码块都不重复它。三条零依赖 lint 挂在同一个 CI job（`lint.yml:36-57`）：`lint_e2e_selectors.py` 管谁在用 testid，`lint_testid_naming.py` 管谁在发 testid，`lint_token_refs.py` 是同批引入、同样零依赖、同一 job 里跑的第三条，但它管的是 CSS 自定义属性悬空引用，与 testid 契约是两回事，本 ADR 不覆盖它的决定理由。**明确不做**：不规定 testid 是否在生产构建中剥离（见 Negative）；不为 `library_classic.html` 回贴 testid（该文件随 004 之后的 UI 一起删除，见 `testid-rename-map.md` §8.4）。

## Consequences

### Positive
- Phase 4 每页替换后，同一份 E2E 不改代码即可验证新旧行为一致；`plan-tech-stack-migration.md:406` 明确把"E2E 全程不改"列为切片验收的一部分。
- 命名 lint 显式点名 24 个 `reader-`/`library-` 前缀的形似合规名（`lint_testid_naming.py` 的模块 docstring），防止批量改名时被当成"已经对了"漏改。
- `Modal` 的 `data-testid` 从硬编码 `"modal"` 改为必填 prop、无默认值（`plan-frontend-ui-refactor.md:408,437`），从源头消除多个弹层撞同一个 testid 的可能。

### Negative
- **221 个名字的改名成本**：原型侧从 134/138（0 合规）改到 221（0 违规），且需要维护 `testid-rename-map.md` 这份新旧对照表（119 条字面量 + 15 条跨页共享 chrome 裂成 45 个新名 + 4 条 `Sheet` 的 `testId` prop + 表达式站点枚举）；该表本身成为长期需要跟随改名同步的文档。
- **回贴有洞：221 个原型 testid 里只有 152 个（68.8%）回贴到了现有实现**（`testid-rename-map.md:331`），意味着当前这套跑在旧模板上的 E2E 对剩下 69 个不具备覆盖能力。69 个贴不上的分四类（`testid-rename-map.md:364-397`）：(1) 三页共有的新 chrome（主题切换、topbar 等旧 UI 根本没有）；(2) 各页新增的功能性元素（书库拖拽上传、阅读器快捷追问、设置页 RAG 相关控件等，旧 UI 无对应实现）；(3) 交互形态不同不可硬贴（如两个按钮 vs 一个切换按钮、按钮组 vs `<select>`）；(4) 两个枚举缺项（`rd-pref-theme-auto`、`lib-book-status-*` 的 loading/unknown 两态）。这个覆盖缺口要到 013/014 把对应元素建出来才能补上。
- **testid 是否在生产构建中剥离——未决**。计划与前端规格均未讨论 `data-testid` 属性对生产 DOM 体积与可见结构的影响，`strip` 相关检索在两个计划文件夹下均无命中；这意味着 221 个语义化名字（如 `rd-notes-export`、`lib-collection-rename-input`）目前预期会原样出现在发布产物里，暴露了部分内部功能命名，但这是否可接受、是否需要构建期剥离，本 ADR 不做裁决。
- CI 的 `contracts` job 只在发版触发（`lint.yml:10,24-28`），不是每次 push 的护栏；日常 push 之间新增的 testid 违规不会被自动拦下，只能靠开发者本地手跑 `lint_e2e_selectors.py` / `lint_testid_naming.py`，或等到发版那天一次性堆积暴露。

### Neutral
- `Modal` 组件的 `data-testid` 是必填 prop、无默认值（`plan-frontend-ui-refactor.md:408`），后续任何复用 `Modal` 的调用点忘记传值会在构建期或运行期报错（`:437`），而不是静默复用旧的 `"modal"`。
- 命名正则的唯一定义处是 `scripts/lint_testid_naming.py`（`CANONICAL` 常量）；`plan-tech-stack-migration.md` §6 原来的代码块与脚本头部注释曾互相声称对方是"唯一真相源"，2026-08-26 两处均已改为指向脚本常量与本 ADR。

## Revisit When

- 014 合入且 Classic UI（`library_classic.html`）删除后：strangler-fig 接缝完成使命，届时评估是否把 testid 契约放宽为一般测试约定（不再要求"先原型后模板"的顺序，也不再需要维护新旧对照表）。
- 出现第二个前端实现（例如再次并行两套 UI）：需要重新确认"只许 testid/ARIA"的选择器规则与命名 lint 是否照搬，或要为多实现场景另加规则。
- 生产构建的 testid 剥离问题被显式提出讨论时：本 ADR 的 Negative 里"未决"一条需要收口为一次新决定（新 ADR 或本文更新）。

## Related

- ADR-0002（epub.js iframe 渲染）——其 Related 已把 ADR-0013 列为"标注/CFI 与前端外壳相关的后续决定"之一；两文一并核对时应互相确认引用方向。
- ADR-0008、ADR-0010、ADR-0011——编号预留于 `docs/adr/0000-use-adrs.md`「首批 0001–0013」，成文时点若涉及 testid 契约的上下游细节，链接回本文而不复述。
- 原定义处：`docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:215-223`（canonical 正则代码块及其"唯一真相源"声明）——本 ADR 决定唯一定义处改为 `scripts/lint_testid_naming.py` 的 `CANONICAL` 常量；该处已于 2026-08-26 改为一行链接，代码块删除。
- 原定义处：`scripts/lint_testid_naming.py:40-41` 的头部注释原写"唯一真相源是 plan-tech-stack-migration.md"，2026-08-26 已改为自认唯一真相源并指向本 ADR。
