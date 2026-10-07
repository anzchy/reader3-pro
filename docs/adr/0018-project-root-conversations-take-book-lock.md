# ADR-0018: project-root 存储的对话写手也持该书的共享书锁（按书目录名），`both` 模式的两份在同一次持锁内写完

| 字段 | 值 |
|---|---|
| Status | Accepted（2026-10-07，随 `018-library-routes` 第二段 WI-4 – WI-8 的 PR #37 转入，018 §4 出口闸 7；实现在 WI-5b `dc7dd27`）。维护者 2026-10-02 裁定（018 第二段计划评审 H1）。**只**取代 [ADR-0015](0015-per-book-write-coordination.md) Decision Outcome 第 3 条里「对话只在 per-book 存储模式下取书锁……它不取书锁是刻意的，不是遗漏」这一处例外；ADR-0015 其余条款（含「不保证」里 `both` 模式两次发布之间的一致性）继续有效。**2026-10-07 修订**（PR #37 全量审计 `audit-20261007-143200` #1，FX37-3）：单条对话的删除路径也持该书的共享书锁 ＋ `conversations` 资源锁——原「明确不做」里「删除单条对话的路径不加锁」一句收回。理由：删书的提交改名与终结器把墓碑里的对话发布进项目级目录（Q-B）之间，一次不持锁的项目级删除会先删掉项目级那份、再被终结器重新发布出来，被删的对话复活 |
| Decision date | 2026-10-02 |
| Recorded date | 2026-10-02 |
| Record type | Prospective |
| Original rationale known | Yes |
| Confidence | High——问题由 Codex 计划评审指出，并在代码上逐条核对（见 Evidence）；机制复用已有的 `writer_scope`，没有新原语 |
| Current compliance | Full——`save_project_conversation` 在 `writer_scope(..., holder="conversations")` ＋ 资源锁内写；`save_conversation_multi` 的 `both` 分支一次持锁写完两份（018 WI-5b `dc7dd27`）；`delete_conversation` / `delete_project_conversation` / `delete_conversation_multi` 在 `acquire(..., SHARED, holder="conversations")` ＋ 资源锁内删（2026-10-07 修订，FX37-3） |
| Evidence | 以符号定位（行号以 `fa9a4fe` 核对，会漂）：`ai.conversations.save_project_conversation`（`ai/conversations.py:289`，不取任何锁，`:296` 直接 `os.makedirs` 项目级 `{root}/{book_uuid}/`）；`ai.conversations.save_conversation_multi`（`:405`，`both` 模式先调 `save_conversation`——它在 `writer_scope` 内写 per-book 那份并在返回时放锁——再在锁外调 `save_project_conversation`，`:435-438`）；`book_lock.writer_scope`（`book_lock.py:538`，锁内复核书目录存在 → `BookGone`、复核 `book_uuid` → `BookChanged`）；`web.server._project_conversations_root`（`server.py:1009`，根 = `dirname(BOOKS_DIR)` 下的 `conversation_project_root_dir`，默认 `conversations`，见 `ai/config.py:42`）；ADR-0015 第 3 条（例外原文）、第 7 条（同一调用栈重复取书锁 → 抛错）、第 8 条（删书步骤）；[018 第二段计划](../plans/20261002-018-second-slice-plan.md) §6 Q-B（删书时把 per-book 对话搬进项目级目录） |
| Confirmation | `tests/unit/test_project_conversation_book_lock.py`（018 WI-5b，矩阵 B-1 – B-4）：`test_b1_project_save_runs_under_the_book_lock`（项目级写入只在持 SH 书锁 ＋ 资源锁时发生）、`test_b2_project_save_outcomes_gone_changed_busy`（书不在 → `BookGone`、换代 → `BookChanged`、EX 被占 → `BookLockBusy`）、`test_b3_both_mode_is_one_acquisition_and_project_write_is_locked`（`both` 模式只取一次书锁）、`test_b4_delete_vs_project_save_ordering`（删书后迟到的项目级写入 → `BookGone` 且不重建 `{root}/{book_uuid}/`；`both` 写入期间删书持 EX → 两份都不写）；2026-10-07 修订补 B-5 – B-7 与路由层 C-15：`test_b5_conversation_delete_waits_for_an_in_flight_book_delete`（提交改名与终结器发布之间到来的单条删除等删书做完，对话不复活）、`test_b6_orphan_conversation_stays_deletable`（书目录已不在的孤儿对话仍可删，不重建书目录）、`test_b7_conversation_delete_runs_under_the_book_lock`（两次 `os.remove` 时 EX 探针都是 busy("conversations")；EX "delete" 被占 → `BookLockBusy`，什么都不删）、`tests/contract/test_library_delete_route.py::test_c15_conversation_delete_during_a_book_delete_is_409_and_removes_nothing`（`DELETE /api/ai/conversations/...` 遇删书持锁 → 409 ＋ `Retry-After`） |

## Context and Problem Statement

ADR-0015 第 3 条让 project-root 模式的对话**不**取书锁，理由是「对话住在书目录之外，删书的 `rmtree` 碰不到它，没有复活可防」。018 第二段的两项决定让这个前提不再成立：

- 删书带 `delete_conversations=true` 时要删掉该书在项目级目录里的对话。一个不持锁的项目级写手在删书之后落盘，`os.makedirs` 会把 `{root}/{book_uuid}/` 重新建出来——被删的对话以残缺形态复活，正是 ADR-0015 想防的那一类。
- Q-B 裁定删书时把 per-book 的对话**搬进**项目级目录。搬家与一个不持锁的同名对话写入交错，就是丢更新。
- `both` 模式今天先在锁内写 per-book、放锁、再在锁外写项目级。这两步之间恰好能插进一次完整的删书：per-book 那份随墓碑消失，项目级那份在删书之后才写出来。

## Decision Drivers

- ADR-0015 第 5 条「不复活」对所有写手一视同仁；例外只在「删书碰不到」时才站得住
- 删书要能对项目级对话下手（删或搬），就必须能把项目级写手挡在门外
- 不引入新的锁原语或新的持有者类别：`conversations` 类别、`writer_scope`、`resource_lock` 都已经存在
- ADR-0015 第 7 条禁止同一调用栈重复取同一把书锁，`both` 模式不能靠「两个函数各取一次」

## Considered Options

1. **项目级写手也持该书的共享书锁，键用书目录名；`both` 模式一次持锁写完两份**（选定）
2. **只给项目级目录加一把按 `book_uuid` 的资源锁，不取书锁**——为什么不：资源锁不做书目录存在复核，挡不住删书之后的迟到写入；删书还得再取一把按 uuid 的锁，锁序多出一条边
3. **保留例外，删书后在项目级目录留一份「已删 uuid」名单，写手写前查名单**——为什么不：多一份要崩溃安全维护的持久状态，名单本身要锁，等于把锁换了个名字
4. **保留例外，接受迟到写入会复活**——为什么不：直接违反 `delete_conversations=true` 的承诺，用户删掉的对话会回来

## Decision Outcome

- `save_project_conversation` 与 `both` 模式的项目级那一份，都在 `writer_scope(books_dir, book_folder, holder="conversations", expected_book_uuid=thread.book_uuid)` 之内、再取 `resource_lock(..., category="conversations")` 后写，与 per-book 写手同一形状。书目录名取自 `thread.book_folder`。
- `both` 模式：取**一次**书锁 ＋ 资源锁，在锁内先写 per-book、再写项目级，然后放锁。不在锁外写任何一份。
- 因此书目录不在（已删）→ `BookGone`（404），书换代（同名重导入）→ `BookChanged`（409），删书持独占锁期间 → 2 秒预算后 409。项目级写手**永远不**建书目录；它仍可以建 `{root}/{book_uuid}/`，但只在复核通过之后。
- 删书带 `delete_conversations=true` 之后，该书的任何迟到项目级写入都拿到 404，不会重建 `{root}/{book_uuid}/`。
- **单条对话的删除**（2026-10-07 修订，FX37-3）：`delete_conversation`、`delete_project_conversation`、`delete_conversation_multi` 都在 `acquire(books_dir, book_folder, mode=SHARED, holder="conversations")` 之内、再取 `resource_lock(..., category="conversations")` 后删；`delete_conversation_multi` 两份一次持锁删完（ADR-0015 第 7 条）。用的是 `acquire` 而**不是** `writer_scope`：不复核书目录存在、不复核 `book_uuid`——删除不会重建任何东西，孤儿对话（删书后保留在项目级目录里的那些）必须仍然删得掉。因此删书持独占锁期间（含墓碑清扫与 `process_epub` 前的清扫，它们同样持该目录名的 EX）单条删除等待，2 秒预算后 `BookLockBusy` → 409 ＋ `Retry-After`；`delete_project_conversation` 为此增必填的 `books_dir`、`book_folder`。
- **明确不做**：`both` 模式两份之间的崩溃一致性（锁内写完第一份后进程被杀）仍按 ADR-0015「不保证」处理；项目级的**读**路径不加锁（与 ADR-0015「读者不取锁」一致）。~~删除单条对话的路径不加锁~~（2026-10-07 收回，见上一条）。

## Consequences

### Positive

- 删书对项目级对话的处置（删或搬入）不再与写手竞争；「不复活」对所有对话写手成立
- `both` 模式不再有「per-book 已随书删掉、项目级在删后才写出来」的窗口

### Negative

- project-root 模式下的对话保存从「永不被书锁挡」变成「导入 / 删书持独占锁时 2 秒后 409」，前端要像 per-book 模式一样保住未保存内容
- 书目录已经不在时，项目级保存从「照写」变成 404——项目级存储本身并不需要书目录，这是为「不复活」付的代价
- `both` 模式持锁时间变成两次写入之和

### Neutral

- 孤儿对话（删书后保留的那些）只能按 `book_uuid` 在磁盘上找到；对它们的任何写入都会因书目录不在而 404。删除不复核书目录（2026-10-07 修订），所以库函数层面孤儿仍可删；`DELETE /api/ai/conversations/{book_uuid}/...` 先经 `book_uuid` 解析书目录，解析不到即 404——这是修订前就有的路由行为，本修订不改

## Migration Strategy

- `018-library-routes` 第二段 WI-5 改 `ai/conversations.py`：`save_project_conversation` 加锁、`save_conversation_multi` 的 `both` 分支改为单次持锁；同 WI 加 Confirmation 列出的三条测试
- 棘轮沿用 ADR-0015：「各写手不复活」测试每个写手一条，项目级写手补上它那一条

## Revisit When

- 项目级对话目录被别的进程（同步服务、第二个客户端）直接写
- 对话改为不按书存放（跨书对话）
- ADR-0015 的 Revisit When 任一条触发

## Related

- [ADR-0015](0015-per-book-write-coordination.md)：本文取代其 Decision Outcome 第 3 条的 project-root 例外；其 Status 行指向本文
- [ADR-0003](0003-dual-book-identity.md)：项目级目录按 `book_uuid` 分，身份复核用的也是它
- 原讨论处：[018 第二段计划](../plans/20261002-018-second-slice-plan.md) §6 Q-B 与 §8（评审处置）
