# ADR-0005: 标注锚定 = 引文 + 50 字前后文，CFI 可选优先；偏移量单位按语言分列进接口

| 字段 | 值 |
|---|---|
| Status | Accepted（2026-10-09：由 [ADR-0019](0019-annotation-resolution-under-book-fingerprint.md) 扩展——书指纹换代时的逐条解析状态、严格无歧义匹配与指纹不符时跳过孤儿判定；本文正文不变） |
| Decision date | 2025-12-19（commit `f57986c`，quote/prefix/suffix/position 首次落地）；2025-12-27（commit `2fc439c`，`cfi` 字段加入） |
| Recorded date | 2026-08-25 |
| Record type | Retrospective |
| Original rationale known | Partial |
| Confidence | Medium |
| Current compliance | Full |
| Evidence | `src/reader3_app/models/annotations.py:22-51`（`quote`/`prefix`/`suffix`/`position`/`cfi` 字段与 `__post_init__` 的 50 字截断）；`src/reader3_app/web/static/js/annotations.js:242-260`（`rangeFromCfi`）、`:342-369`（`render()` 里 CFI 优先、失败或无 CFI 落回文本匹配）、`:979-1013`（`createAnnotation()` 里 quote/prefix/suffix 始终计算，`cfi` 尝试失败即置 `null`，`position` 取 JS `idx.text` 的 UTF-16 下标）；`src/reader3_app/web/server.py:784-820`（`_annotation_matches_chapter_text` / `_refresh_orphaned_annotations`——只用 `quote`/`prefix`/`suffix` 的文本包含判断，从不读 `position`）；`docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:105`（C2：标注锚定依赖 spine 指纹与章节内容 hash，是用户数据不能重算）、`:775`（偏移单位契约：Python code point / DOM-JS UTF-16 code unit）；`docs/plans/20260816-tech-stack-migration/tasks/008-test-safety-net.md:137`（同一契约在 008 的落地要求）、`:343`（该契约钉进 `tests/fixtures/unicode_corpus.py`，归属 014）；`docs/technical-detail.md:18`（`cfi` 字段作为「可选锚点」的现状记录）；`CLAUDE.md:129-141`（Annotation model 摘要）；`tests/fixtures/annotation_corpus.py:1-20`（docstring 明写「stored as quote plus 50 characters of prefix/suffix — never as a DOM path」，并列出 `repeated`/`long_context` 等失锚场景） |
| Confirmation | `tests/unit/test_fixture_annotation_corpus.py`（quote/prefix/suffix 再锚定的语料，含跨节点、跨段落、重复文本、超 50 字前后文场景）；`tests/contract/test_scenarios.py:47-133`（`test_...会被判为孤儿并从列表消失`：prefix/suffix 落盘按 50 字截断，`orphaned` 由文本匹配判定）；`tests/unit/test_highlight_utf16_offsets.py`（code-point/UTF-16 双单位契约，目前覆盖的是搜索高亮 `highlight_ranges_for_chapter`，不是本 ADR 的 `position` 字段——见 Negative） |

## Context and Problem Statement

标注（annotation）绑定到一段正文，但正文所在的 DOM 结构、EPUB 解析产物、乃至存储格式（012 计划中）都可能随着时间变化。锚定策略决定的是：**标注恢复时，靠什么去正文里重新找到这段文字**。找错了，标注要么消失（用户看不到自己划的线），要么落到别的文字上（更糟——用户会误信一条注解贴对了位置）。这是用户产生的数据，找错了不能重新生成。

- **Observed State**：`Annotation` dataclass（`annotations.py:22-30`）同时持有 `quote`/`prefix`/`suffix`（各截到 50 字，`:45-48`）、可选的 `cfi`、和一个未加说明单位的 `position: Optional[int]`。
  前端 `render()`（`annotations.js:342-369`）对每条标注先试 `cfi`：能解析出 `Range` 就直接用；解析失败或本来就没有 `cfi`，落进 `textAnnotations` 走 quote/prefix/suffix 文本匹配。
  后端重新打开一本书时的孤儿判定（`server.py:796-820`）完全不看 `cfi` 也不看 `position`，只用 `quote`/`prefix+quote+suffix` 的字符串包含关系（`_annotation_matches_chapter_text`）。
  也就是说：**quote+context 文本匹配是唯一在两端都真正生效的重新锚定机制；CFI 是渲染期的加速路径，命中就用，不命中就等价于没有；`position` 只用于笔记面板里同章节标注的排序（`server.py:853,909` 的 `_sort_key`），从不参与孤儿判定或重新定位**。
  字段引入的顺序也说明了这个主次关系：`f57986c`（2025-12-19）落地时只有 `quote`/`prefix`/`suffix`/`position`，`cfi` 是八天后 `2fc439c`（2025-12-27）才补上的（`git show 2fc439c -- src/reader3_app/models/annotations.py` 的 diff 只加了一个字段，没动其它逻辑）。
- **Original Rationale**：Partial。`f57986c`（2025-12-19）与 `2fc439c`（2025-12-27）的提交信息都只是「Implement」式清单，没有陈述为什么选 quote+context 而不是纯位置或纯 CFI，也没说清 CFI 与文本匹配谁该优先——这部分是 **Unknown**。偏移量单位这一半是 **Known**：`plan-tech-stack-migration.md:775` 明确记录了「偏移单位必须写进 API 契约：Python 按 Unicode code point，DOM/JS 按 UTF-16 code unit」，并指出现状是前端自行重算范围掩盖了这个差异。
- **Current Assessment**（推断，非当年理由）：quote+context 文本匹配对「章节被重新处理但文字基本不变」这类改动天然健壮，代价是对重复段落不够唯一、对长依赖上下文的引文会被 50 字截断削弱区分度。CFI 更精确但脆——一旦 iframe 内部 DOM 结构变化（换渲染引擎、epub.js 升级改变生成规则）就会解析失败，此时必须有文本匹配兜底，否则标注直接从界面消失。今天的实现事实上就是这个「CFI 优先尝试、文本兜底」的形状，但这是 2026-08-25 写本文时读代码得出的观察，不是 2025-12 决定时写下的设计意图。

## Decision Drivers

- 标注是用户产生的数据，重新定位失败的代价是数据不可逆丢失或误置，不是可重试的操作。
- 正文来源（EPUB 解析、章节 HTML 空白折叠）与渲染宿主（epub.js iframe DOM）会独立变化，锚定必须能扛住至少一边变化。
- Python 与 JS/DOM 对字符串长度的计数单位不同（code point vs UTF-16 code unit），任何跨语言复用的偏移量字段都会在非 BMP 字符（emoji、CJK 扩展区）上产生位移，这是中文阅读器场景下的真实输入，不是边角情况。
- CFI 的生成与解析绑定在 epub.js 之上（见 ADR-0002），不是本仓库自控的格式。

## Considered Options

1. **quote + 50 字 prefix/suffix，CFI 可选并优先尝试**（选定）
   两套机制并存：CFI 命中给更精确的 `Range`，不命中退到文本匹配，两者都失败才判孤儿。
   代价：两套逻辑要分别维护和测试（`annotations.js` 的 `rangeFromCfi` 与 `findRange` 各自成一套），且 `position` 字段的单位语义目前没有文档化（见 Negative）。
2. **仅 CFI**——为什么不（推断，非当年论证）
   CFI 完全依赖 epub.js 生成的 iframe DOM 结构，一旦换渲染引擎或 epub.js 升级改变生成规则导致 DOM 结构变化，就会批量解析失败；这套方案没有兜底机制，标注会静默消失而不是降级到一个次优但可见的位置。
3. **仅字符偏移（`position`）**——为什么不
   012 计划要把存储格式从 pickle 换成 manifest+jsonl，任何文本清洗规则（空白折叠、Unicode 归一化）的改动都会让绝对偏移量整体漂移；且偏移量本身就横跨 Python code point 与 JS UTF-16 code unit 两种计数单位（`plan-tech-stack-migration.md:775`），纯偏移方案没有文本内容做校验，位移一旦发生是无声的——落到错误的字符上而不是报错。

## Decision Outcome

标注的权威锚定信息是 `quote` + 50 字 `prefix`/`suffix`（`annotations.py:45-48` 强制截断，`server.py` 的 `_annotation_matches_chapter_text` 是唯一读取它做判定的地方）。`cfi` 是可选的渲染期优化：存在且能解析成 `Range` 就用它跳过文本搜索；解析失败或本就没有 `cfi`，一律落到 quote/prefix/suffix 文本匹配，两者都找不到才标记 `orphaned`。`position` 目前只是前端计算并回传的辅助字段，不参与后端的重新锚定判定。任何跨 Python/JS 边界传递或消费偏移量的新代码，必须显式区分 code point（Python）与 UTF-16 code unit（DOM/JS），不得假设两者相等——这条约束今天由 `highlight_ranges_for_chapter`（搜索高亮）的 `start`/`end` 与 `start_utf16`/`end_utf16` 双字段践行，`position` 尚未获得同等待遇（见 Negative）。

## Consequences

### Positive
- 文本匹配兜底让锚定不会因为渲染引擎或 DOM 结构变化就整体失效，只会在 CFI 失效时退化成较粗的定位，而不是标注消失。
- 孤儿判定（`orphaned`）建立在同一套文本匹配上，前后端行为一致、可测试（`test_scenarios.py:47-133` 已覆盖 50 字截断与孤儿判定两条路径）。
- 偏移单位契约已经在搜索高亮路径上有先例（`highlight_ranges_for_chapter` 的 code point + UTF-16 双字段），标注要给 `position` 补齐同等契约时有现成模式可抄，不必从零设计。
- `annotation_corpus.py` 把已知会失锚的场景（跨节点、跨段落、重复引文、超长上下文、章节被重排）都固化成了 fixture，新增的存储或渲染改动一跑测试就会暴露是否破坏了这些场景。

### Negative
- **换锚定策略等价于让全库标注一次性 stale。** 文本匹配依赖 `quote`/`prefix`/`suffix` 的精确内容；012 一旦改变文本抽取或空白折叠规则，所有存量标注在迁移当天就可能批量判孤儿——这正是 `plan-tech-stack-migration.md:105/789` 点名的「用户产生、错了不能重算的数据」。这不是本 ADR 引入的新风险，而是选定这套策略之后必须长期背负的成本。
- **两种偏移单位在 API 边界必须手工转换，容易错。** `position` 由前端用 JS 字符串下标（UTF-16 code unit）计算并回传（`annotations.js:1013`），后端只用它做排序键，从不校验也不重算（见 Neutral）。今天的唯一暴露面是排序：同章节内两条标注若因非 BMP 字符导致 `position` 计算偏移，排序结果最多是「先后顺序换了」，不会指错文字——真正的风险在于这颗字段一旦被拿去做除排序外的用途（例如与搜索高亮的 code-point `start`/`end` 混用去定位文字），缺失的单位契约不会先被任何现存测试拦下来。
- **50 字上下文对重复段落不够唯一。** `annotation_corpus.py` 的 `repeated` 用例证明三次重复的引文只能靠 prefix/suffix 消歧，`long_context` 用例证明超过 50 字的必要上下文会被截断削弱区分度——两者都是已知会失锚的边界情况，不是假设。
- CFI 与文本匹配两套逻辑并存，维护面比单一机制大；CFI 优先于文本匹配的顺序本身缺乏书面理由（Original Rationale 的 Unknown 部分），修改这个优先级不会被任何现存文档判定为「违反了设计」。

### Neutral
- 012 计划的指纹机制（`book_fingerprint()`，`plan-tech-stack-migration.md:381/727`）与 `orphaned` 字段（`annotations.py:30`、`server.py:800-820`）以本 ADR 的锚定策略为前提：指纹不匹配时的分级降级，降级到的正是这里定义的「文本匹配 + orphaned」机制，不是另起一套。
- `orphaned` 字段今天已经存在并生效，但驱动它的是运行时文本重匹配（每次 `GET` 都重算），不是指纹比对。
  012 落地后两者的关系（指纹判断是否需要重匹配，还是替代重匹配）需要新决定，不在本 ADR 范围内。
- 014（`annotations.js` 拆分）不得改变本 ADR 定义的锚定语义（CFI 优先、文本兜底、50 字上下文）；拆分是文件组织重构，不是策略变更。
- `position` 由前端在创建时写入一次，之后不再被任何一端重算或校验；它在后端唯一的用途是给同章节标注排序（`server.py:853,909`），`_annotation_matches_chapter_text` 从不读它。它是排序键，不是锚定契约的一部分——这也是它至今没有配套的 code point/UTF-16 单位测试的原因：没人把它当位置去解读正文，只当成一个可比较的数字。

## Revisit When

- 012 的 `book_fingerprint()` 落地，需要裁决指纹比对与本 ADR 的运行时文本重匹配是并存还是互相取代。
- `orphaned` 字段被前端 UI 真正消费（今天只被后端过滤掉，用户侧看不到「有一条标注失锚了」的提示）——那时孤儿判定的准确性会从「静默丢失」变成「用户可见」，容错要求会变。
- epub.js 被替换（见 ADR-0002 的 Revisit When）：CFI 分支需要重新验证是否还能生成/解析。
- `position` 字段的单位契约被正式书面化或被某处代码开始跨语言消费（例如与搜索高亮的偏移量合并处理）——那时需要给它补 `_utf16` 兄弟字段或明确弃用。

## Related

- ADR-0002（epub.js iframe 渲染——CFI 锚定的 DOM 基础，本 ADR 的 CFI 分支依赖它）。
- ADR-0009（尚未落笔；编号预留见 `docs/adr/0000-use-adrs.md`「首批 0001–0013」，`docs/adr/0002-epubjs-iframe-rendering.md` 的 Related 亦将 ADR-0005 列为该编号区间的一员）。
- `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:775`（偏移单位契约，本 ADR 是其在标注场景下的落点，原文保留）；`:105/789`（标注是用户数据、指纹与锚定的分工，原文保留、不复述）。
- `docs/plans/20260816-tech-stack-migration/tasks/008-test-safety-net.md:137/343`（偏移单位契约在 008 测试网中的落地与归属，原文保留）。
- `docs/technical-detail.md:18`——本 ADR 是其「`cfi` 字段为可选锚点」这句话背后决策理由的记录来源，原句保留不改写。
