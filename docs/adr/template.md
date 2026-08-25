# ADR-NNNN: <标题——用陈述句写出决定本身，例如「书的持久化格式从 pickle 迁到 manifest + jsonl」>

| 字段 | 值 |
|---|---|
| Status | Proposed · Accepted · Deprecated · Superseded by ADR-XXXX |
| Decision date | YYYY-MM-DD——决定**实际做出**的日期；查不到就写 `unknown（首次出现于 commit xxxxxxx）` |
| Recorded date | YYYY-MM-DD——本文写下的日期 |
| Record type | Prospective（先定后做）· Retrospective（先做后记） |
| Original rationale known | Yes · Partial · No |
| Confidence | High · Medium · Low——对「本文对理由的描述是否准确」的信心 |
| Current compliance | Full · Partial · None——代码今天符合本决定到什么程度 |
| Evidence | `文件:行号`、commit、文档章节，逗号分隔。每一条都必须是写本文时**亲自核对过**的 |
| Confirmation | 指向一条**机器执行**的确认：测试文件、lint 脚本、CI 步骤的路径。没有就写 `none（人工）` |

## Context and Problem Statement

两到五句。这个决定回答的是什么问题；不做决定会发生什么。
Retrospective 记录在这里区分三种东西，**不许混写**：

- **Observed State**：今天代码里看得见的事实（带 Evidence）。
- **Original Rationale**：当年为什么这样做。有出处就引出处；没有就写 `Unknown`。**禁止把今天的推断写成当年的理由。**
- **Current Assessment**：以今天的眼光看这个决定是否仍然成立、代价如何。这是推断，标明是推断。

## Decision Drivers

三到六条。真正推动决定的力量：约束、成本、风险、已有承诺。不写「简洁」「可维护」这类放之四海皆准的词。

## Considered Options

至少两个。每个一句话说清它是什么，一句话说它的主要代价。被否决的方案写「为什么不」，不写「因为不好」。

1. **方案 A**（选定）——…
2. **方案 B**——…为什么不：…
3. **方案 C**——…为什么不：…

## Decision Outcome

一段话，陈述句。选了什么，边界在哪，哪些**明确不做**。

## Consequences

### Positive
### Negative
**必须非空。** 没有负面后果的决定不需要 ADR。
### Neutral
派生出来的、需要别人知道的约束（例如「因此 X 文件成为死文件」「因此桌面壳只能选 Electron」）。

## Migration Strategy

Current compliance ≠ Full 时必填：现状与目标的差在哪，谁在哪个分支把差补上，用什么棘轮防止倒退。Full 时删掉本节。

## Revisit When

具体触发条件，不写「视情况」。例：「出现第二位贡献者」「epub.js 上游一年无发布」「014 合入（冻结解除）」。

## Related

- 上下游 ADR
- CLAUDE.md / AGENTS.md 里指向本文的那一行
- 本文取代的原定义处（`docs/plans/...` 的章节），以及那里现在留下的链接

---

<!--
写 ADR 的硬规则（来自 docs/adr/0000-use-adrs.md，此处只是提醒）：
1. 搬，不抄。本文成为唯一定义处的那一刻，原定义处只留一行链接。
2. 不编历史。Original rationale 查不到就写 Unknown。
3. 每条 Evidence 写本文时亲自打开核对；行号会漂。
4. Negative 非空；Confirmation 优先指向机器检查；Revisit When 必须是可触发的条件。
5. Accepted 不等于永远正确。改决定写新 ADR 并 supersede，不改旧文。
-->
