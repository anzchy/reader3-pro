# ADR-0015: 每本书一把书目录之外的 SH/EX 书锁，改结构的写手独占、只写自家文件的写手共享后再取资源锁

| 字段 | 值 |
|---|---|
| Status | Accepted（2026-10-02 合入回写：契约随 `018-library-routes` 第一段 WI-1 – WI-3 合入 `master`，PR #33，合并 commit `c08317b`；原定「合入的同一 PR 里转 Accepted」（018 §4 门槛 7）当时漏转，此处补上）。Decision Outcome 第 3 条里「对话只在 per-book 存储模式下取书锁……不是遗漏」这一处 project-root 例外已由 [ADR-0018](0018-project-root-conversations-take-book-lock.md) 取代（2026-10-02 裁定；0018 在 018 第二段合入前为 Proposed，期间代码仍按本文运行）。本文其余部分继续有效，正文按规则不改。 |
| Decision date | 2026-09-26 |
| Recorded date | 2026-09-26 |
| Record type | Prospective |
| Original rationale known | Yes |
| Confidence | High——契约经逻辑原型推演、Codex 与独立 Fable 子代理分别裁定；2026-10-02 起已有实现（`book_lock`）与跨进程测试（见 Confirmation） |
| Current compliance | Partial——锁已接入 import、notes、reindex（HTTP 与 CLI）、`ai_meta`、对话、向量读路径；删书（018 WI-5）与 012 的写手尚未接入，见 Migration Strategy |
| Evidence | 以符号定位（行号会漂）：`notes_service._book_write_lock`（018 前：进程内 `threading.Lock` ＋ `flock` 阻塞锁，锁文件在书目录内，且与 `notes_service.save_annotations` 一样在持锁路径上 `os.makedirs` 书目录）；`vector_search.BookVectorIndex._client_and_collection`（在**读**路径上 `makedirs`）；`ai.books._write_meta_to_scratch`（`ai_meta.json` 写入前 `makedirs`）、`ai.books.ensure_book_uuid`、`ai.books.BookUuidResolver`；`ai.conversations.save_conversation`；`search_service` 与 `web/routers/library.py` 的书库枚举（只收 `_data` 后缀）；`reader3.main` 的 `--index` 分支（CLI，不经 HTTP）；`web.server._stats_cache`、`web.server._validate_book_id`；`docs/plans/20260816-tech-stack-migration/tasks/018-library-routes.md` §6（Q2 / Q3a / Q3b / Q8 / Q12 裁定）；原型 `018-lock-protocol.PROTOTYPE.html`（分支 `prototype/018-book-lock`） |
| Confirmation | `tests/unit/test_book_lock_cross_process.py`（跨进程互斥、SH 兼容、持有者被 SIGKILL 即释放、拒绝带类别；018 WI-2） |

## Context and Problem Statement

[ADR-0001](0001-filesystem-as-database.md) 让一本书就是一个目录，[ADR-0007](0007-crash-safe-publish-protocol.md) 规定了单个写手怎样崩溃安全地发布。两者都没有回答**多个写手同时碰同一本书**时谁先谁后。今天唯一的协调是 notes 自己的锁，它的锁文件在书目录里，且会 `makedirs` 书目录。删书路由（009 债 #58）一旦上线，下列情形都会发生：删书的 `rmtree` 把锁文件 unlink，下一个写手建出新 inode，两个进程各持一把「同名」独占锁；删书之后 notes / `ai_meta` / 对话 / 向量写手把书目录重新建出来，书以残缺形态「复活」；等锁期间书被删、同一 EPUB 又被导入，醒来的写手写进新书（ABA）。

## Decision Drivers

- 012 还要加入更多写手：`--migrate`、generation swap、批量重建、上传。锁的形状现在不定，每条新路由都得自己猜
- 划线保存是高频交互，重建索引是分钟级操作；二者不能互相卡死
- 单人维护、单进程部署；不引入锁服务或数据库（[ADR-0008](0008-tech-stack-boundary.md)）
- `flock` 的语义：按 open file description 计，模式转换非原子，随进程死亡释放，阻塞模式没有超时

## Considered Options

1. **分层 SH/EX 书锁 ＋ 资源锁，锁文件在书目录外**（选定）
2. **把书锁与 notes 锁合并成一把独占锁**——为什么不：重建持锁分钟级，期间每次划线要么挂起、要么 409（原型「Q3 合并」两剧本）
3. **锁文件放在书目录里**——为什么不：`rmtree` 把它 unlink，互斥失效；首次导入得先建出空书目录，整个构建期书库里有坏条目，被杀即永久留下（原型「Q2 锁在目录里」「首次导入·锁在目录里」）
4. **只靠存在性复核、不加书锁**——为什么不：挡不住 ABA，也挡不住删书与重建交错

## Decision Outcome

1. **位置**：`books/.locks/{book_folder}.lock`，建了就**永不 unlink**；`.locks/` 的累积是设计，回收只许停机时做。书库枚举**只收 `_data` 后缀的目录**——这是「内部目录（`.locks/`、墓碑 `.{id}.deleted-{pid}/`）不进书库」的唯一依据，不靠点目录隐藏
2. **两种模式**：改目录结构的写手（import、delete、migrate、上传、墓碑清扫）持**独占**；只写自家文件的写手（notes、reindex、`ai_meta`、对话）持**共享**，再取自己的**资源锁**。顺序固定为**书锁 → 资源锁**。资源锁的位置是 `books/.locks/{resource}/{book_folder}.lock`（reindex、`ai_meta`、对话；与书锁同样建了就永不 unlink，且不在书目录里创建任何东西），由 `book_lock.resource_lock` 统一实现，与书锁共用同一个截止时间；**notes 例外，保留书目录内的 `notes.json.lock`**——有共享持有者时没人能 `rmtree` 它，挪位置只会改一条已有语义而无收益（018 WI-1）。书锁持有者类别是封闭列表（`book_lock.CATEGORIES`）：`import`、`delete`、`reindex`、`notes`、`ai_meta`、`conversations`、`search`；`search` 是向量读路径，只在打开 collection 的一瞬以短预算（`SHORT_BUDGET_S`）持共享、不取资源锁，拿不到即按「未索引」处理（审计 #44、#48，fix-plan WI-4）
3. **范围**：锁包住服务层的整次操作，HTTP 路由与 CLI（`reader3 --index`）走同一把。对话只在 **per-book** 存储模式下取书锁：project-root 模式的对话住在书目录**之外**，删书的 `rmtree` 碰不到它，也就没有「复活」可防；它不取书锁是刻意的，不是遗漏
4. **拒绝**：独占写手非阻塞获取，拿不到 → HTTP 409 / CLI 非零退出码，说明持有者类别；这个类别可能报成 `unknown`：它只是写在锁文件头部的尽力而为的遥测，记录为空、撕裂、指向已死 pid，或已被共享持有者释放时清掉（含同类持有者之间的竞争）都读作 `unknown`，锁本身从不据它做决定（018 修复轮 2，审计 #21）。共享写手以 `LOCK_NB` 轮询，**一个 2 秒的 `time.monotonic` 总预算覆盖所有层**，超时 → 409 ＋ `Retry-After`；等待不阻塞事件循环。**截止规则**：一层只在成功那一刻 `now < deadline` 时才算拿到——在截止时刻或之后才拿到的那一层被释放并拒绝（已拿到的各层一并释放），截止时刻已到的请求一层都不尝试；持有者类别的读取记在同一个截止时间上（等空记录的窗口是 `min(0.1 s, 剩余时间)`），拒绝不会晚于截止时刻（审计 #42、#20）。只想「不等」的调用方传预算 `SHORT_BUDGET_S`，由 `acquire` 在真正取锁时起算
5. **不复活**：拿到锁后、写之前，在锁内复核书目录存在；除 import 外任何写手不得 `makedirs` 书目录本身——包括读路径
6. **身份复核**：共享写手在请求开始时记下 `book_uuid`（[ADR-0003](0003-dual-book-identity.md)），拿到锁后复核，不一致 → 409（书已换代）。删后再导入同一 EPUB 是**新书**
7. **进程内层**：真正的读写语义，不把共享持有者串行化；同一调用栈重复取书锁 → 抛错；**禁止共享→独占升级**；不用 dup / 继承的 fd 冒充线程互斥
8. **删书**：独占锁 → 锁内复核 → 从集合移除 → 改名为墓碑并 `fsync` 父目录（提交点）→ 失效进程内缓存 → 按请求删对话 → `rmtree` 墓碑 → 放锁。墓碑清扫**持有**对应书的独占锁再删，不是「探测后即释放」。步骤的定义处是 018 WI-5

**不保证**（明确不做）：

- 多 worker 部署：进程内缓存（`_stats_cache`、`BookUuidResolver`、`_BOOK_THREAD_LOCKS`）只在本进程失效
- NFS / SMB 等网络文件系统：`flock` 语义不可靠
- ChromaDB 自身的多进程访问（上游不支持）；向量查询只在打开 collection 的一瞬持共享书锁（短预算），查询本身不持锁（fix-plan WI-4）
- `FileResponse` 流式返回期间书被删：读到半截即失败，不做快照
- 对话「both」存储模式的两次发布之间的一致性——需要 revision，另案处理
- `_BOOK_THREAD_LOCKS` 注册表只增不减
- **None==None 的 ABA 测不出**：身份复核比的是 `book_uuid`。请求开始时书还没有 uuid（`ai_meta.json` 缺失或读不出 → `None`），等锁期间书被删、同名重新导入且新书也还没有 uuid，锁内复核看到的仍是 `None`，判为同一本书。身份不扩到 inode / ctime（刻意不做）
- **首次写入 uuid 时的瞬时假 409**：请求开始时记下的是 `None`，等锁期间另一写手（如 `ensure_book_uuid`）给**同一本书**首次铸了 uuid，锁内复核看到 `None` ≠ 新 uuid，返回「书已换代」409。书其实没换；客户端重读后再写即成功

## Consequences

### Positive

- 删书、导入、迁移不会互相踩；删掉的书不会被复活
- 重建期间划线照常保存
- 012 的新写手只需声明自己是「改结构」还是「写自家文件」

### Negative

- 每个写手都要改：notes、`ai_meta`、对话、向量的 `makedirs` 全部改成「断言父目录存在」，notes 的锁要拆成书锁 ＋ 资源锁
- `.locks/` 只增不减，只能停机回收
- 共享写手在独占写手在场时会 409，前端必须保留未保存的内容并提示重试
- 单进程、本地文件系统的假设被写死；换部署形态就要重开本文

### Neutral

- 删书后集合成员被移除、对话按请求保留为孤儿——孤儿对话由 `book_uuid` 引用，永不重新挂上
- [ADR-0007](0007-crash-safe-publish-protocol.md) 的发布协议在书锁**之内**运行；它的崩溃恢复（staging 清理）也必须持书锁，否则会删掉别人的 staging

## Migration Strategy

- `018-library-routes` WI-2 实现锁模块并接入 notes、reindex（HTTP 与 CLI）、`ai_meta`、对话、向量，以及 `process_epub`（导入，持独占）；WI-5 接入删书
- 012 的写手（`--migrate`、generation swap、批量重建、上传）在 012 接入（012 §4 门槛 14）
- 棘轮：018 WI-2 的「各写手不复活」测试每个写手一条；新写手不带这条测试不得合入

## Revisit When

- 部署变成多 worker 或多机
- 书库放到网络文件系统上
- 出现第二种客户端（桌面壳、同步服务）会直接写书目录
- ChromaDB 升级后支持多进程访问

## Related

- [ADR-0001](0001-filesystem-as-database.md) 的 Revisit When「`_book_write_lock` 多进程」即本文
- [ADR-0003](0003-dual-book-identity.md)：身份复核用的 `book_uuid`
- [ADR-0007](0007-crash-safe-publish-protocol.md)：单写手的发布协议；其「跨设备 rename 降级为复制」一句不成立，由 012 Q2 的新 ADR 取代时更正
- 原定义处：`docs/plans/20260816-tech-stack-migration/tasks/018-library-routes.md` WI-2「契约」——本文 Accepted 时那里改成一行链接
