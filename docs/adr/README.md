# 架构决策记录（ADR）

这里记的是**为什么**——那些改起来跨模块、回滚代价高、半年后一定有人问「当初为什么这样」的决定。`docs/plans/` 随 015 归档，这个目录不归档。分工（ADR vs CLAUDE.md vs `docs/*.md` vs `docs/plans/`）与准入标准只在 [ADR-0000](0000-use-adrs.md) 定义一次。

## 索引

| 编号 | 标题 | Status | 记录类型 | 合规 | 一句话 |
|---|---|---|---|---|---|
| [0000](0000-use-adrs.md) | 采用 ADR，并规定与 CLAUDE.md / docs 的分工 | Accepted | Prospective | Full | 五问≥2 且唯一定义处将随 plans 归档，才写 ADR |
| [0001](0001-filesystem-as-database.md) | 文件系统即数据库 | Accepted | Retrospective | Full | 一书一目录 `books/{name}_data/`，不引入 SQL |
| [0002](0002-epubjs-iframe-rendering.md) | epub.js 在 iframe 里渲染 | Accepted | Retrospective | Full | 永不触碰 iframe 内部 DOM；CSS 分栏分页退役 |
| [0003](0003-dual-book-identity.md) | 一本书两个身份 | Accepted | Retrospective | Full | 目录名走路径，`book_uuid` 走会话；`ai_meta.json` 坏了降级为 None，不覆盖 |
| [0004](0004-chromadb-minilm-vector-search.md) | 嵌入式 ChromaDB + MiniLM | Accepted | Retrospective | Partial | 一书一库；换模型＝全量重建，故不换 |
| [0005](0005-annotation-anchoring.md) | 标注锚定 | Accepted | Retrospective | Full | 引文 + 50 字前后文，CFI 可选优先；偏移单位按语言分列 |
| [0006](0006-provider-egress-single-gate.md) | provider 出网单出口 | Accepted | Retrospective | Full | `_http.py` 一个口：只许 http(s)、拒 30x、key 不下发、不发往请求方 base_url |
| [0007](0007-crash-safe-publish-protocol.md) | 书目录崩溃安全发布协议 | Accepted | Prospective | Partial | staging → 读回校验 → 原子换，marker 最后；读取三态，`corrupt` 大声失败 |
| [0008](0008-tech-stack-boundary.md) | 技术栈边界 | Accepted | Prospective | Partial | 后端留 Python，前端迁 TS 不引框架，桌面壳不做 |
| [0009](0009-book-format-manifest-jsonl.md) | 持久化格式去 pickle | Proposed | Prospective | None | `manifest.json` + `chapters.jsonl`，双写后按版本号日落 pkl |
| [0010](0010-test-and-ci-topology.md) | 测试与 CI 拓扑 | Accepted | Retrospective | Full | 门禁在本地 tdd-guardian，GitHub CI 只在发版触发 |
| [0011](0011-api-v1-freeze.md) | API v1 冻结 | Accepted | Prospective | Full | `routes.snapshot` 是唯一清单；Phase 2 不改形状，Phase 3 只许新增 |
| [0012](0012-security-boundaries.md) | 三条安全边界 | Accepted | Retrospective | Full | 受限 unpickler 无回退；路径只在拼路径前挡一次；凭据文件走 `mkstemp` |
| [0013](0013-testid-invariant.md) | `data-testid` 是新旧 UI 间唯一不变量 | Accepted | Prospective | Full | 先原型后模板；E2E 只许 testid/ARIA；三条 lint 守它 |

「合规」是 **Current compliance**：Full＝代码今天就这样；Partial＝部分落地，缺口在该文的 Migration Strategy；None＝尚未实现（Proposed 才会出现）。

## 怎么加一份

1. 先过 [ADR-0000](0000-use-adrs.md) 的准入：五问至少两个「是」，**且**这条决定的唯一定义处在一份会被归档的文档里（或根本不存在）。只满足前一半的，写进 `docs/*.md` 概览就够。
2. 复制 [`template.md`](template.md)，编号取索引里最大值 +1，文件名 `NNNN-短横线-slug.md`。
3. 填满元数据表；`Negative` 不许空，`Confirmation` 尽量给一条机器能跑的命令或测试路径，`Revisit When` 写可触发的条件。
4. 追溯性记录（Retrospective）不编历史：当年理由不知道就写 `Original rationale known: No`，把今天的评估放进 Current Assessment。
5. **搬，不抄**：同一 commit 里，把原定义处的正文换成一行指向新 ADR 的链接，标题保留以保住锚点。
6. 在上表加一行。已 Accepted 的 ADR 不改正文——要变就新开一份 supersede，旧文只改 Status。

## 核对

ADR-0000 的 Confirmation 是人工的：上表的行数应等于目录下 `NNNN-*.md` 的文件数。

```sh
test "$(grep -c '^| \[' docs/adr/README.md)" = "$(ls docs/adr/[0-9]*.md | wc -l | tr -d ' ')" && echo ok
```
