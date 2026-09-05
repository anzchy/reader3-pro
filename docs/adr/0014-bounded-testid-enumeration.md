# ADR-0014: 有界元素集合的每个成员各有唯一 `data-testid` 字面量，`data-modal` / `data-sheet` 判别位删除；`[data-testid][data-*]` 复合选择器只留给无界 id

| 字段 | 值 |
|---|---|
| Status | Accepted |
| Decision date | 2026-08-31 |
| Recorded date | 2026-08-31 |
| Record type | Prospective |
| Original rationale known | Yes |
| Confidence | High |
| Current compliance | None——决定与实现同批落地于 `009-e2e-annotations`，见 Migration Strategy |
| Evidence | `docs/adr/0013-testid-invariant.md:36`（复合形态被列入允许的选择器）、`:43`（Positive 宣称 `Modal` 必填 prop 已「从源头消除多个弹层撞同一个 testid 的可能」）；`docs/plans/20260817-frontend-ui-refactor/spec-frontend-design.md:704-711`（§4 规则 5 的有界/无界两行，及「无界那一行不违反规则 2」）；`docs/plans/20260816-tech-stack-migration/contracts/testid-rename-map.md:340-353`（§8.2 判别位表，含 `data-modal`/`data-sheet`/`data-file-href` 三行）、`:315`（§8.1 计数口径「同名元素各占一个名字」）；`docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md:399,409,423,438`（WI-6：`Modal` 的 `data-testid` 改必填、**各调用点各自的 testid**、验收 8 禁止 `data-testid="modal"` 默认值）；`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md:35,36,148`（实测重名清单与「对弹层这一族不可满足」的记录）；`scripts/lint_testid_naming.py:42`（`CANONICAL`）、`:45`（`PROP_LITERAL_RE`，大小写敏感）、`:46`（`ATTR_EXPR_RE`）、`:47`（`TESTID_TABLE_RE`）；`designs/reader-pro-next/settings.jsx:164`（`name={confirm}` 是运行期变量）、`:79-80`（`set-provider-result` 的互斥双分支）；`designs/reader-pro-next/components.jsx:68-100`（`SHARED_TESTIDS` 三档）、`:162-167`（判别位约定的原定义处注释）；`designs/reader-pro-next/reader.jsx:59-64`（`RD_ANNO_COLOR_TESTID` 有界表范例）、`:199-200,211`（`Sheet` 的 `data-sheet`） |
| Confirmation | `python3 scripts/lint_testid_naming.py`——本 ADR 为其新增**同文件内字面量唯一性**检查（原脚本只校验形状不校验唯一性，见 `009-e2e-annotations.md:35`）；`python3 scripts/lint_e2e_selectors.py`——本 ADR 把复合形态从「任意 `data-*`」收紧为一张闭合清单；两者由 `.github/workflows/lint.yml` 的 `contracts` job 在发版时跑 |

## Context and Problem Statement

ADR-0013 允许 `tests/e2e/` 用 `[data-testid="…"][data-*="…"]` 复合形态定位，`testid-rename-map.md` §8.2 据此把同页并存的四个 `<dialog>` 处理成「共用 `lib-modal` 字面量 ＋ `data-modal` 携带弹层名」。落到生产模板上，这产生了 Playwright strict 模式下不可用的 DOM：`library.html` 有 `lib-modal` ×4、`lib-modal-close` ×4、`lib-modal-primary` ×3、`lib-modal-cancel` ×2，`reader.html` 有 `rd-sheet-close` ×2，而 `getByTestId()` 命中多个元素直接抛（`009-e2e-annotations.md:35,148` 已把这一族记为「选择器政策不可满足」）。009 分支要写标注 E2E，第一个选择器就落在这些名字上。

问题不是「复合形态该不该存在」——无界 id（书、集合、笔记、会话）确实只能这么写——而是**弹层与面板被放错了行**：它们是编译期可枚举的有界集合，规格 §4 规则 5 对有界集合的规定是逐个枚举成字面量、放进 `const` 表，而不是共用一个字面量再加判别位。§8.2 为自己辩护时只论证了「不违反规则 2」（选择器**形态**合法），从未论证「属于规则 5 的哪一行」（**分类**）；原文写的是「做法与 §5.2 无界 id 那一行同构」——形似被当成了同类。

## Decision Drivers

- **009 是硬阻塞**：五个重名在去重之前，标注 E2E 的第一个选择器就写不出来，而 009 是 Phase 4 合并的门槛。
- **内部已不自洽**：WI-6 已裁定 `Modal` 的 `data-testid` 改为必填 prop、且是「**各调用点各自的 testid**」（`plan-frontend-ui-refactor.md:423`）。也就是说 `data-modal` 唯一的卖点——「E2E 选择器一字不变」——在 014 落地时本来就会死。现在改与将来改，选择器都要重写一次；差别只在 009 能不能先写。
- **命名 lint 查不出重名**：`CANONICAL` 只管形状（`scripts/lint_testid_naming.py:42`），唯一性无人守。判别位方案把「唯一性」这个不变量整个交给人工，而它恰恰是 strict 模式唯一在乎的东西。
- **改动窗口现在最便宜**：`tests/e2e/` 目前只有 `conftest.py` 和 `test_harness_smoke.py`，后者唯一的选择器是 `[data-testid="rd-viewport"] iframe`。`data-modal`/`data-sheet` 无任何 JS、CSS、测试消费者（三次独立 grep 核实），删除与改名的运行期风险为零。
- **复合形态本身仍有不可替代的用途**：`data-book-id` 这类真无界 id 无法枚举。要保留的是这条规则的**适用范围**，不是这条规则。

## Considered Options

1. **有界集合逐个枚举成唯一字面量，删除 `data-modal`/`data-sheet`；复合形态收紧为一张闭合的无界属性清单**（选定）——见 Decision Outcome。代价：19 个 testid 改名 ＋ 两份原型组件重写，见 Negative。
2. **保留判别位，改用 `locator()` 写复合选择器绕开 `getByTestId()` 的 strict**——为什么不：strict 是 Playwright 的 locator 层默认行为，`locator('[data-testid="lib-modal"][data-modal="add-books"]')` 同样在解析到多元素时抛；能绕开的只有 `.first()`/`.nth()`，而 `.nth()` 已被 `lint_e2e_selectors.py` 明令拦截（重排即失效）。这条路要么绕不开，要么要先拆掉一条现存 lint。
3. **保留判别位，只给生产模板临时改名，原型不动**——为什么不：直接违反 ADR-0013 的「先原型定名、再回贴模板」顺序（`0013:36`），且 014 落地时原型侧仍要再改一次，等于把同一处改两遍并在中间维持两侧不一致。
4. **给 `Modal` / `Sheet` 加 `closeTestId` 这类新字面量 prop**——为什么不：两条硬约束否掉它。`settings.jsx:164` 传的是 `name={confirm}`（`confirm ∈ {reindex, conversations, cache}`，运行期变量），调用点根本写不出字面量；且 `PROP_LITERAL_RE`（`:45`）大小写敏感只认 `testId`，`closeTestId="…"` 会整个绕过命名 lint 的扫描。

## Decision Outcome

**取值有界（编译期可枚举）的同类元素，每个成员各有自己唯一的 `data-testid` 字面量**——这是规格 §4 规则 5 有界那一行的原文要求，弹层（`Modal` / `ConfirmModal`）与面板（`Sheet`）属于这一行，此前被错放进无界那一行。相应地：`data-modal` 与 `data-sheet` 两个判别位**删除**，不再是契约的一部分。

派生名一律由**标识符含 `TESTID` 的静态 `const` 表**承载（`MODAL_TESTIDS`、`RD_SHEET_TESTIDS`），不通过新增 prop、不通过字符串拼接——前者绕过命名 lint 的 `PROP_LITERAL_RE`，后者被 `ATTR_EXPR_RE` 判违规；`const` 表命中 `TESTID_TABLE_RE`（`:47`）这条现成扫描形态，不用改 lint 就被覆盖。`Modal` / `ConfirmModal` 的 prop 由 `page` ＋ `name` 收敛为单个 `modal`，值是表的键；`Sheet` 的 `testId` prop 与四个调用点不变，内部由字面量改为查表。这满足 WI-6 验收 8（源码里不存在 `data-testid="modal"` 默认值，`plan-frontend-ui-refactor.md:438`），且把 WI-6「各调用点各自的 testid」提前到 009 兑现。

命名规则两条：**Modal 族**宿主 `{lib|rd|set}-modal-{name}`，子元素按 `-close` / `-cancel` / `-primary` / `-body` 后缀派生；**例外**是契约或计划已为该宿主保留名字的用保留名当宿主（唯一一例：`rd-note-editor`，计划 8 处已用此名，模板已有子元素 `rd-note-editor-input`）。**Sheet 族**的 `data-sheet` 值本来就是该面板自己的 testid，宿主名不变，子元素派生 `-close` / `-resizer`。

`[data-testid="…"][data-*="…"]` 复合形态**继续允许，但收紧为一张闭合清单**——只有下列携带用户数据 id 的属性可以作为判别位，新增需改 lint 并说明为何该取值集合无法枚举：`data-book-id`、`data-collection-id`、`data-note-id`、`data-annotation-id`、`data-conversation-id`、`data-provider`、`data-section`、`data-file-href`。清单取自实测（`src/reader3_app/web` ＋ `designs/reader-pro-next` 全量 grep），不是照抄计划。

`scripts/lint_testid_naming.py` **新增同文件内字面量唯一性检查**。这只是唯一性的静态近似——真正要保证的是渲染后 DOM 里的唯一性，静态扫描证明不了（同一字面量可能出现在互斥分支里，也可能跨文件汇入同一页）。因此**明确不做**：不声称 lint 能证明 DOM 唯一性；已知的合法同名（`settings.jsx:79-80` 的 `set-provider-result` 两行是 `test === "ok"` / `test === "fail"` 互斥分支，至多渲染一个）以显式豁免登记，不靠合并分支来迎合 lint。

**明确不做**：不动 ADR-0013 的其余任何部分——testid 作为唯一接缝、先原型后模板的顺序、canonical 正则的唯一定义处、三条 lint 的分工，全部照旧。本 ADR 只取代 §「复合形态适用于哪些元素」这一个子命题。

## Consequences

### Positive
- 009 的第一个阻塞解除：`getByTestId()` 对弹层与面板一族可用，`009-e2e-annotations.md:35,148` 两处「不可满足」的记录可以关闭。
- 同批补上 009 记录的第二个阻塞（`:36`）：`anno-color-row` 与 `note-tooltip` 两个 K1 宿主此前无 testid，现补为 `rd-anno-colors` 与 `rd-note-tooltip`。两者只由 `annotations.js` 经 `getElementById` 取用（`:415`、`:420`），加 testid 是纯增量。
- 唯一性从「人工遵守」升级为「有静态近似在守」，虽不完备，但重名批量复发这一类会被拦下。
- WI-6 的组件改动提前兑现，014 落地时 `Modal` 已经是目标形态，少一次改。

### Negative
- **19 个 testid 改名 ＋ 2 个新增**，两份原型的 `Modal`/`ConfirmModal`/`Sheet` 需重写；`testid-rename-map.md` 的 §3 表、§8.1 计数、§8.2 全节都要跟着改。这是判别位方案省下的成本被延后到今天一次付清。
- **静态唯一性检查会漏报也会误报**：跨文件汇入同一页的重名它看不见（`library.html` 与 `library.js` 各发一个同名 testid 就漏），互斥分支的合法同名它会误判并需要豁免登记。豁免清单本身成为需要维护的东西，且豁免登记多了会稀释这条检查的意义。
- **`SHARED_TESTIDS` 被拆散**：三档各删 5 个键后，弹层名字不再集中在一处，而是散在 `MODAL_TESTIDS` 里按弹层组织。想知道「set 页有哪些 chrome 元素」需要看两张表。
- **ADR-0013 的 Positive 第三条自此失真**：它宣称必填 prop「从源头消除多个弹层撞同一个 testid 的可能」，而当时生产模板正有 13 处重名——该句描述的是 014 落地后的将来态，被写成了现在态。旧文按规则不改正文，这个失真会留在那里，只能靠 Status 里的指针提醒读者。

### Neutral
- `data-file-href` 留在闭合清单里，但它当前只有 1 处使用（`testid-rename-map.md:340-353` 的 §8.2 表第三行）。§8.2 这一节因此不整节删除——标题保留、`data-file-href` 那一行保留，删掉的是 `data-modal` / `data-sheet` 两行及其辩护段落。
- `plan-frontend-ui-refactor.md:1132` 用的是 `rd-panel-toc` / `rd-panel-notes` / `rd-panel-search` / `rd-panel-ai`，与模板和契约里已落地的 `rd-toc-panel` / `rd-notes-panel` / `rd-search-panel` / `rd-ai-panel` 不一致。落地名是权威，计划文档是离群值——这不是本 ADR 的决定，只是随本批一并订正计划侧那 4 处提法。
- 原型侧四个 `Sheet` 都有关闭按钮，模板侧只有两个（`rd-toc-panel`、`rd-notes-panel` 在生产模板里没有关闭按钮）。`RD_SHEET_TESTIDS` 按原型的四个键建表，模板侧回贴两个；这是既有的「221 vs 152」覆盖缺口的一部分（ADR-0013 Negative 第二条），不因本 ADR 扩大。

## Migration Strategy

Current compliance 是 None——决定与实现同批落地在 `009-e2e-annotations` 分支上，顺序是：

1. 本 ADR ＋ ADR-0013 的 Status 指针 ＋ `docs/adr/README.md` 索引行（同一 commit）。
2. 「搬，不抄」：`testid-rename-map.md` §8.2 的 `data-modal`/`data-sheet` 两行与辩护段落、§3 表里 5 行 modal 记录、`spec-frontend-design.md` §4 规则 5 表下补一行分类判据、`components.jsx:162-167` 的注释——原定义处换成指向本文的一行链接，标题保留以保住锚点。
3. 实现（走 `/tdd-guardian:workflow`）：两个模板改名 19 处 ＋ 新增 2 处、两份原型改表、两条 lint 改规则。
4. `009-e2e-annotations.md` 的 `:35`、`:36`、`:148` 记录阻塞解除。

棘轮是新增的唯一性检查本身：它进 `lint_testid_naming.py` 之后，同一文件内的重名不会静默复发。跨文件与互斥分支这两个洞由豁免清单显式记账，不假装被覆盖。

## Revisit When

- 出现第一个「有界集合大到不宜逐个枚举」的实例（例如某天要为 50 个动态 tab 各起一名）：本 ADR 的「有界即枚举」需要一个规模上限，或需要承认某些有界集合应当按无界处理。
- 唯一性豁免清单超过 3 条：说明静态近似与真实需求偏离太远，该换成渲染后 DOM 的运行期断言（例如在 E2E harness 里扫一遍页面查重），而不是继续加豁免。
- 014 合入、`Modal` 的 TS 实现落地后：确认 `MODAL_TESTIDS` 表是否仍是承载派生名的最优形态，还是 TS 的类型系统能提供更强的保证（例如把表键约束成联合类型）。

## Related

- **ADR-0013**——本文取代其 Decision Outcome 中「复合形态适用于哪些元素」这一个子命题；其余部分（唯一接缝、先原型后模板、canonical 正则定义处、三条 lint 分工）全部继续有效。0013 的 Status 已加指针。
- 原定义处：`docs/plans/20260816-tech-stack-migration/contracts/testid-rename-map.md` §8.2——`data-modal` / `data-sheet` 两行及其辩护段落已删除并改为指向本文的链接，`data-file-href` 一行保留在原处。
- 原定义处：`designs/reader-pro-next/components.jsx:162-167` 的判别位约定注释——已改为一行链接。
- `docs/plans/20260817-frontend-ui-refactor/spec-frontend-design.md:704-711` §4 规则 5——两行表保留在原处（它仍是有界/无界二分的唯一定义处），表下补一行分类判据指向本文。
- `docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md` WI-6——其「`Modal` 各调用点各自的 testid」（`:423`）与本文一致；本文把该要求提前到 009 兑现，WI-6 落地时只需确认而非重做。
