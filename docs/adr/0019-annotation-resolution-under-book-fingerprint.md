# ADR-0019: 标注在书指纹下的重新解析：逐条解析状态、严格无歧义匹配与指纹不符时跳过孤儿判定（扩展 ADR-0005）

| 字段 | 值 |
|---|---|
| Status | Proposed——在 `012-storage-format` 合入的同一 PR 里转 Accepted。**扩展**（不取代）[ADR-0005](0005-annotation-anchoring.md)：ADR-0005 的「引文 ＋ 50 字前后文、CFI 可选优先」锚定与运行时文本重匹配继续有效，本文只加「书指纹换代时怎样逐条重新判定、何时推进书级指纹、何时不判孤儿」 |
| Decision date | 2026-10-01（012 §6 Q13 ④⑤⑥）；2026-10-08（012 §6 Q15，匹配器 M-1 … M-7 与跳过规则）；2026-10-09（WI-2b 计划 D-1 … D-11 与协调者裁定） |
| Recorded date | 2026-10-09 |
| Record type | Prospective |
| Original rationale known | Yes |
| Confidence | Medium——规则经 Codex ＋ Fable 两路评审（Q13、Q15）与 WI-2b 测试矩阵两轮对抗评审；本文写下时只有字段与匹配器落地（WI-2b.1），rebind、跳过规则与处置路由尚在后续 WI |
| Current compliance | Partial——见 Migration Strategy |
| Evidence | 以符号定位（行号以 `ab48d54` 之上的 WI-2b.1 工作区核对，会漂）：`models/annotations.py` 的 `Resolution`（`:15`）、`Annotation.resolution` 等四个加法字段（`:63` 起）、`from_dict` 的 D-5 降级（`_coerce_resolution` `:161`、`_str_or_none`、`_str_or_empty`）、`match_resolution`（`:182`）；`web/server.py:542` `_annotation_matches_chapter_text`（旧匹配：quote 在章内任意处即算，本文**不改**它）；`web/routers/notes.py:77` `_mark_orphans`、`:107` `_refresh_orphaned_annotations`、`:144`／`:210` GET 在 notes 锁之前取 `Book`；`notes_service.py:250` `_existing_fingerprint`、`:268` `save_annotations`（`KEEP`／str／None 三种 `book_fingerprint`，`null` 不落盘）、`:337` `annotations_version`（只哈希 `to_dict()`）、`:422` `refresh_annotations_and_version`、`:478` `delete_annotation_and_version`（docstring `:488-492`：版本 409 先于 404）；`book_store.py:227` `book_fingerprint(book_id, books_dir)`；`web/static/js/annotations.js:268-282` `findRange`（精确 `indexOf`，失败退回 quote 首个出现处）；`tests/unit/test_notes_fingerprint_key.py:381-438`（N6-10：`save_annotations` 只许 4 个调用点）；`tests/contract/test_scenarios.py:112-135`（旧书旧 notes 的孤儿判定）；`docs/plans/20260816-tech-stack-migration/tasks/012-storage-format.md` §6 Q4、Q13、Q15 |
| Confirmation | `tests/unit/test_annotation_resolution_fields.py`（A1-01 … A1-07：四字段往返律、旧记录常量默认、D-5 降级表、降级不动点）；`tests/unit/test_annotation_matcher.py`（M1-01 … M1-13：严格匹配、可重叠计数、全 `isspace` 空白去除、对拍性质与两条蜕变关系）。跳过规则、推进规则、rebind 与处置路由的确认用例随 WI-2b.2 … 2b.6 落地，清单见 `.claude/tdd-guardian/tests-20261009-wi2b.md` |

## Context and Problem Statement

012 WI-2a 给每一代书算出 `book_fingerprint` 并写进 manifest，`notes.json` 顶层保留同名键，但「标注是对着哪一份正文做的」只有书级一个值。重新导入（解析器修复、EPUB 换版）之后，后端今天的孤儿判定（`_annotation_matches_chapter_text`）只要 quote 在章内任意处出现就算命中，前端 `findRange` 又在精确匹配失败时退回首个出现处——于是一条在新正文里出现两次的引文会被静默「贴」到第一处，用户看到的是一条贴错位置却显示正常的注解（比消失更糟，见 ADR-0005 Context）。反过来，GET 在 notes 锁**之前**取 `Book`（`routers/notes.py:144`、`:210`），一次并发导入之后拿着旧书去判孤儿，会把一条在新正文里完全匹配的标注永久标成 `orphaned`（孤儿不复评）。不做决定，指纹就只是一个写了没人读的字段。

## Decision Drivers

- 标注是用户数据、不可再生（ADR-0001、ADR-0005）：任何自动判定在拿不准时只能**保留旧绑定并可见地警告**，不能改写或丢弃。
- 012 §6 Q13 ⑤：书级 notes 指纹只能在「全部标注 resolved 或用户显式处置之后」前移；整书 rebind 会在标注仍错位时抹掉 DEG-S1 的「陈旧」提示。
- DOM 文本（前端划线时的 quote）与提取器文本（`get_text(separator=' ')`）在跨行内标签处空白必然不一致：只折叠空白不去除，严格规则会成批误判（Q15 M-1）。
- `annotations_version` 哈希 `to_dict()`：新字段的默认值必须是常量，否则同一份文件每读一次 ETag 都变（017 WI-3 审计 #6 的同一失效方式）。
- N6-10 把 `save_annotations` 的调用点钉为 4 个；新的读改写不能新增保存点。
- `test_scenarios.py:112-135`：没有指纹的旧书、旧 notes 必须照旧判孤儿。

## Considered Options

1. **逐条解析状态 ＋ 严格无歧义匹配 ＋ 指纹不符时跳过孤儿判定**（选定）——每条标注带 `resolution` 与绑定／评估两个指纹；重导入后 rebind 逐条判定；书级指纹只在全部可判定之后前移；指纹不一致时 GET 不做新的孤儿判决。代价：四个新字段、一条新路由、ETag 整体变一次。
2. **Q4 原裁定的快路径**（指纹相等即跳过重匹配）——为什么不：指纹相等时跳过会让 `test_scenarios.py:112-135` 那种「同一份正文、引文却已对不上」的记录永远不被判孤儿（Q15 明令不做）。Q4 的「并存」保留，快路径不做。
3. **重匹配后整书 rebind**（Q13 草案）——为什么不：今天的旧匹配接受章内任意位置，整书 rebind 会把仍错位的标注连同书级指纹一起「洗白」，DEG-S1 的陈旧提示随之消失（Q13 ⑤，以 Codex 修订为准）。
4. **复用 `_annotation_matches_chapter_text`**——为什么不：它只判「在不在」，不判「是否唯一」，且不去空白；Q15 明定新匹配器另写、旧匹配原样不动。
5. **新 ADR 取代 ADR-0005**——为什么不：没有指纹的存量书仍然只靠 ADR-0005 的运行时重匹配；本文只在指纹存在时叠加一层（ADR-0005 Revisit When 第一条点名的正是这次裁决）。

## Decision Outcome

**一、逐条解析状态（`models/annotations.py`，WI-2b.1，已落地）。** `Annotation` 加四个加法字段，默认值全是常量：

| 字段 | 类型 | 默认 | 含义 |
|---|---|---|---|
| `resolution` | `"resolved"`／`"ambiguous"`／`"unmatched"`／`"accepted"` | `"resolved"` | 在 `evaluated_fingerprint` 那一代正文下的判定结果；`accepted` 只由用户处置写入 |
| `bound_fingerprint` | `str` 或 `None` | `None` | 绑定字段（quote／prefix／suffix／position／cfi／chapter_index）最后一次被确认所对着的那一代 |
| `evaluated_fingerprint` | `str` 或 `None` | `None` | 最后一次被评估所对着的那一代 |
| `chapter_href` | `str` | `""` | 创建时由后端从 `book.spine[chapter_index].href` 取；本期只存不用（「按 href 跟随」是遗留） |

`from_dict` 的降级（D-5）确定、不抛、不丢记录：`resolution` 缺失或为 `null` → `"resolved"`（旧记录都是对着当时那份正文建的）；不在四值集合内的任何值（含大小写不同、非 str）→ `"unmatched"`（坏值必须挡住推进，而不是放行）；两个指纹字段非 str → `None`；`chapter_href` 非 str → `""`。

**二、严格匹配器 `match_resolution(chapter_text, prefix, quote, suffix)`（Q15 M-1 … M-7，WI-2b.1，已落地）。** 纯函数：

- M-1 两侧都用 `"".join(s.split())` 去掉**全部** `str.isspace` 字符（NBSP、全角空格、U+2028 等都算；零宽空格 U+200B 不是空白，照原样比较）。
- M-2 草堆是**锁内**读到的当前 generation 里**同一 `chapter_index`** 那一章的 `text`（不走按 stat 缓存的 `load_book_cached`）；`chapter_index` 越过章数 → `unmatched`。
- M-3 针 = `prefix + quote + suffix` **先拼接再**去空白。
- M-4 用 `find` 逐位前进数**可重叠**的出现次数，数到 2 即停；不用 `str.count`。
- M-5 恰 1 次 → `resolved`；≥ 2 → `ambiguous`；0 → `unmatched`；去空白后 quote 为空 → `unmatched`。
- M-6 prefix、suffix 皆空时针退化为 quote，仍须恰好 1 次。
- **严格（Q13 ④）**：针计数为 0 即 `unmatched`，quote 本身在章内唯一也**不**退回去只找 quote。

匹配器永远不返回 `accepted`。旧的 `_annotation_matches_chapter_text` 原样保留，继续只服务 ADR-0005 的孤儿判定。

**三、跳过规则：`fingerprints_agree(notes_fp, book_fp)`（Q15 ⑥，D-1／D-2）。** GET 的 `_mark_orphans` 只在两边一致时运行；不一致即**整段跳过**——不做新的孤儿判决、不写盘、照常 200 ＋ ETag。真值表是完整定义域：

| notes 顶层 `book_fingerprint` | `Book.book_fingerprint` | 一致？ | 结果 |
|---|---|---|---|
| 缺失或 `null` | `None` | 是（旧书旧 notes） | 照旧判孤儿（`test_scenarios.py:112-135`） |
| str `X` | str `X` | 是 | 照旧判孤儿——**没有** Q4 快路径，重匹配照跑 |
| str | `None` | 否 | 跳过 |
| 缺失或 `null` | str | 否 | 跳过 |
| str `X` | str `Y`（`X ≠ Y`） | 否 | 跳过 |
| 非 str（`123`、`{}`、`[]` …） | 任意 | 否 | 跳过，且该值逐字节原样保留 |

跳过期间，已落盘为 `orphaned: true` 的旧记录**继续隐藏**、不复活、不计入「全部 resolved」（D-2）。指纹比对在 notes 锁内读 notes 一侧，从而堵住「锁前取到旧 `Book`、并发导入 ＋ rebind 之后把新正文里匹配的标注粘性判孤儿」的竞态。

**四、推进规则（`_advance_target`，Q13 ⑤，D-4）。** 书级 notes 指纹只在下列条件全部成立时前移到当前指纹 `cur`：`cur` 是 str；notes 现有值缺失或是 str（**非 str 的现有值永不覆盖**）；每一条**未孤儿**标注的 `resolution ∈ {resolved, accepted}` **且** `bound_fingerprint == cur`。空集满足条件（删掉最后一条阻塞标注即前移）。任一不成立 → `KEEP`（原样带过现有值）。`null` 永不写入。`bound == cur` 这一条防的是「导入之后、rebind 之前」一次 DELETE 拿着旧的 `resolved` 标志把指纹推过去。推进判定在**全部 4 个保存点**（refresh、add、delete、update）锁内重算，只在本来就要保存的路径上读当前指纹（GET 无改动时不受影响）。

**五、创建时盖章（D-3）。** `add_annotation_and_version` 在锁内把新标注写成 `resolution="resolved"`、`bound_fingerprint = evaluated_fingerprint = 锁内当前指纹`（当前为 `None` 时两者都是 `None`）；`api_create_annotation` 写 `chapter_href`。新格式书、空 notes 的第一次创建因此会把 notes 顶层盖成当前指纹——否则跳过规则会让这本书永远不再判孤儿。

**六、rebind（Q13 ⑥，D-9）。** `notes_service.rebind_annotations` 是 notes 读改写：import 释放 EX 之后，经 `refresh_annotations_and_version` 的闭包先取 SH 书锁、再取 notes 锁（ADR-0015 顺序），锁内重读当前 generation，转发调用方的 `deadline`。逐条：

- 孤儿：跳过，不复活、不计数。
- `accepted` 且 `bound_fingerprint == cur`：跳过（这是 rebind 幂等的来源），计为 `accepted`。
- 其余按匹配器判定：`resolved` → 写 `resolution`、`bound_fingerprint`、`evaluated_fingerprint = cur`；`ambiguous`／`unmatched` → **只**写 `resolution` 与 `evaluated_fingerprint`（Q15 M-7）。
- rebind **从不**改 quote／prefix／suffix／position／cfi／chapter_index、`chapter_href` 与 `orphaned`。
- 当前指纹为 `None`、manifest 坏、或任一章读失败（`ChapterReadError`／`OSError`）→ 整次 rebind「无法判断」，什么都不写，返回该结果而不抛。
- 只在有标注改变、或推进目标与现存值不同时写盘；`notes.json` 不存在时什么都不建。

rebind 与处置都经由已有的 `refresh_annotations_and_version` 闭包保存，**不**新增保存点：N6-10 的 4 个调用点不变（D-6）。导入后自动触发 rebind 的钩子归 012 WI-3。

**七、处置路由 `POST /api/notes/{book_id}/{chapter_index}/{note_id}/disposition`（D-7、D-8、D-10）。** 请求体 `{"action": "accept_binding" | "delete"}`（`extra="forbid"`）。

- **`If-Match` 必填**：缺失、空串或全空白 → **428** `{"detail": "If-Match required"}`。这是本仓库第一个 428，**只限本路由**：其余 notes 路由的 `If-Match` 仍是可选的（`routers/notes.py:41-42`，011 WI-5a 为旧客户端保留的逐字节兼容）。理由：处置是用户对一条**警告**作出的显式决定，不带版本就无法确认用户看到的是哪一份状态；新路由没有旧客户端需要兼容。`If-Match: *` 不支持，按版本不符 409。
- **错误顺序**（逐级，前一级成立即返回）：422（请求体、路径整数、多余键，FastAPI 在处理器之前）→ 428 → 400 非法 book_id → 404 书不存在 → 400 `chapter_index` 越界（`>= len(spine)`）→ 404 标注不存在 → 409 `Book fingerprint unavailable`（只有 pkl、无 generation 的书，两种 action 都拒）→ 409 `Annotation orphaned`（仅 accept）→ 409 版本冲突（与 PUT 同形的 `_conflict` 载荷）。标注按 `id` 查找，路径里的 `chapter_index` 只做范围检查。**404 标注先于 409 版本**（WI-2b 协调者裁定 7），与旧 DELETE 相反（`notes_service.py:488-492` 先 409 后 404，理由见那里的 docstring）；两条路由的顺序各自以本文与那段 docstring 为准，不要「统一」其中一条。任何错误都不写盘。
- **accept_binding**：对 `ambiguous`／`unmatched` → `accepted`，两个指纹都写成当前指纹，绑定字段不动。对 `resolved`／`accepted` 是 **no-op**：不写盘，`book_fingerprint_advanced: false`，ETag 等于送来的 `If-Match`。no-op 只在整条错误阶梯之后判定，不会抢在任何守卫之前短路。
- **对 `unmatched` 执行 accept_binding 的后果**：这条标注随之可能让书级指纹前移；指纹一致后跳过规则结束，**下一次 GET 会按 ADR-0005 的旧匹配重新判孤儿，可能把它判为孤儿并从列表消失**。路由 docstring 与前端处置 UI（014）都必须把这一点告诉用户。
- **delete**：删除该条，孤儿也可删；其余记录逐字节不变；响应 `resolution: null`。
- 成功：200 ＋ ETag，响应体 `{"id", "action", "resolution", "book_fingerprint_advanced", "message"}`。`book_fingerprint_advanced` 为真当且仅当推进目标不是 `KEEP` **且**与现存值不同。新路由按 [ADR-0011](0011-api-v1-freeze.md) 加法新增，`tests/contract/routes.snapshot` 同一 commit 更新。

**明确不做**：Q4 的「指纹相等即跳过重匹配」快路径；按 `chapter_href` 跟随标注到别的章；rebind 回填旧记录的 `chapter_href`；书级 `GET /api/notes/{book_id}` 摘要加 `resolution`；`ambiguous`／`unmatched` 的前端呈现与处置 UI（014）；改动 `_annotation_matches_chapter_text` 或前端 `findRange`。

## Consequences

### Positive
- 一条在新正文里出现两次的引文不再被静默贴到第一处：它保留旧绑定、读作 `ambiguous`、在章节 GET 里可见，书级指纹不动，DEG-S1 提示保持。
- 指纹不符时 GET 不做新的孤儿判决，并发导入不再能把一条匹配的标注粘性判孤儿。
- 每个新默认值都是常量：同一份旧文件读多少次 ETag 都一样，规范化写回也不移动 ETag。
- 不新增保存点，N6-10 与 ADR-0015 的锁顺序原样成立。

### Negative
- **ETag 对存量书整体变一次**：`to_dict()` 多了四个键，`annotations_version` 随之全部改变（文件本身不必重写）。升级前打开、升级后才保存的客户端会收到一次 409，重读即可。012 合入的 commit message 与 PR 正文注明。
- 后端判 `resolved` **不等于**前端高亮落在正确位置：`findRange`（`annotations.js:268-282`）仍是精确 `indexOf` 加首个出现处回退，且不去空白。已立 [009 欠账 #74](../plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md#跨波欠账)，兑付方 014。
- 对 `unmatched` 的 accept_binding 可能在下一次 GET 被判孤儿——用户「接受」之后标注消失，必须靠 UI 文案事先说明。
- 一条路由独有 428，与其余 notes 路由的「`If-Match` 可选」不对称；读代码的人要看本文才知道为什么。
- 404 标注先于 409 版本，与旧 DELETE 的顺序相反（同上）。
- 每次保存多一次 `validate_stat`（解析 manifest），只在保存路径上；若 WI-5 的基准显示回退，再按锁持有期缓存。
- 跳过规则依赖 `Book.book_fingerprint`：凡产出 `Book` 的加载路径都必须设置它（新格式取 manifest 值，只有 pkl 的为 `None`），否则 rebind 盖过章的 notes 会让这本书永远跳过孤儿判定（012 WI-4 验收、WI-6 依赖）。

### Neutral
- `chapter_href` 本期只存不用；旧记录为 `""`。
- 今天生产上每本书都只有 pkl，`book_fingerprint` 为 `None`，跳过规则与推进规则都走旧书那一行；新行为只在带 generation 的书上出现（012 WI-3 起）。
- DEG-S1 夹具（notes 盖陈旧指纹、`Book` 只有 pkl）在本文下落入「str 对 `None`」一行，GET 跳过孤儿判定；e2e `acceptance_p3/test_deg_states_plain.py` 在 push 前须跑。

## Migration Strategy

**现状（WI-2b.1）**：四个字段、D-5 降级与 `match_resolution` 已落地；推进规则、创建盖章、跳过规则、rebind 与处置路由尚未实现。

**补差**：全部在 `012-storage-format` 分支——WI-2b.2 推进规则与创建盖章（4 个保存点）；WI-2b.3 `Book.book_fingerprint` 与跳过规则；WI-2b.4 `book_store.current_generation` 与 `rebind_annotations`；WI-2b.5 处置服务函数；WI-2b.6 处置路由与 `routes.snapshot`；WI-3 导入后 rebind 钩子；WI-4 让每条 `Book` 加载路径设置 `book_fingerprint`。012 合入时本文转 Accepted、Current compliance 改 Full。**棘轮**：N6-10（保存点仍为 4）、`test_route_inventory.py`（路由清单）、上表 Confirmation 的两份测试与 WI-2b 测试矩阵的后续用例。

## Revisit When

- 前端开始呈现 `ambiguous`／`unmatched` 或接入处置 UI（014）：那时 accept_binding 对 `unmatched` 的「下一次 GET 可能判孤儿」要变成用户可见的确认步骤，可能需要改语义。
- `findRange` 改为与本文同一套去空白、唯一性规则（009 欠账 #74 兑付）。
- 需要按 `chapter_href` 跟随标注到别的章（Q15 遗留），或 `chapter_index` 与 `manifest.chapters` 的位置对应因 WI-3 的 order 空洞处理而改变。
- 其余 notes 路由也要求 `If-Match`（那时 428 不再是本路由独有）。
- `EXTRACTOR_VERSION` 第一次 bump，真实存量书第一次经历 rebind。

## Related

- [ADR-0005](0005-annotation-anchoring.md)：本文扩展的锚定决定；其 Revisit When 第一条即本文裁决的问题，Status 行已加注。
- [ADR-0009](0009-book-format-manifest-jsonl.md)、[ADR-0016](0016-generation-directory-publish.md)：书指纹所在的 manifest 与 generation。
- [ADR-0011](0011-api-v1-freeze.md)：四个加法字段与新路由的加法规则。
- [ADR-0015](0015-per-book-write-coordination.md)：rebind 与处置的 SH 书锁 → notes 锁顺序、`deadline` 转发。
- 原定义处：`docs/plans/20260816-tech-stack-migration/tasks/012-storage-format.md` §6 Q4、Q13、Q15（随 015 归档）；WI-2b 计划与测试矩阵（`.claude/tdd-guardian/plan-20261009-wi2b.md`、`tests-20261009-wi2b.md`）。
- 009 欠账 #74（前端 `findRange` 与后端 `resolved` 的差距）。
