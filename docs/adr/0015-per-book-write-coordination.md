# ADR-0015: 每本书一把书目录之外的 SH/EX 书锁，改结构的写手独占、只写自家文件的写手共享后再取资源锁

| 字段 | 值 |
|---|---|
| Status | Proposed——在 `018-library-routes` 合入的同一 PR 里转 Accepted（018 §4 门槛 7） |
| Decision date | 2026-09-26 |
| Recorded date | 2026-09-26 |
| Record type | Prospective |
| Original rationale known | Yes |
| Confidence | Medium——契约经逻辑原型推演、Codex 与独立 Fable 子代理分别裁定，尚未有实现与跨进程测试 |
| Current compliance | None——见 Migration Strategy |
| Evidence | `src/reader3_app/notes_service.py:68`（`_book_write_lock`：进程内 `threading.Lock` ＋ `flock` 阻塞锁，锁文件在书目录内）、`:94` 与 `:224`（持锁路径上 `os.makedirs` 书目录）；`src/reader3_app/vector_search.py:124-126`（`_client_and_collection` 在**读**路径上 `makedirs`）；`src/reader3_app/ai/books.py:109`（`ai_meta.json` 写入前 `makedirs`）、`:214`（`BookUuidResolver`）、`:225`；`src/reader3_app/ai/conversations.py:244`；`src/reader3_app/search_service.py:255`、`src/reader3_app/web/routers/library.py:42`（书库枚举只收 `_data` 后缀）；`src/reader3_app/reader3.py:708`（CLI `--index` 分支，不经 HTTP）；`src/reader3_app/web/server.py:291`（`_stats_cache`）、`:469`（`_validate_book_id`）；`docs/plans/20260816-tech-stack-migration/tasks/018-library-routes.md` §6（Q2 / Q3a / Q3b / Q8 / Q12 裁定）；原型 `018-lock-protocol.PROTOTYPE.html`（分支 `prototype/018-book-lock`） |
| Confirmation | none（人工）——018 WI-2 落地后改指向其跨进程测试文件 |

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
2. **两种模式**：改目录结构的写手（import、delete、migrate、上传、墓碑清扫）持**独占**；只写自家文件的写手（notes、reindex、`ai_meta`、对话）持**共享**，再取自己的**资源锁**。顺序固定为**书锁 → 资源锁**。资源锁可以留在书目录里——有共享持有者时没人能 `rmtree` 它
3. **范围**：锁包住服务层的整次操作，HTTP 路由与 CLI（`reader3 --index`）走同一把
4. **拒绝**：独占写手非阻塞获取，拿不到 → HTTP 409 / CLI 非零退出码，说明持有者类别。共享写手以 `LOCK_NB` 轮询，**一个 2 秒的 `time.monotonic` 总预算覆盖所有层**，超时 → 409 ＋ `Retry-After`；等待不阻塞事件循环
5. **不复活**：拿到锁后、写之前，在锁内复核书目录存在；除 import 外任何写手不得 `makedirs` 书目录本身——包括读路径
6. **身份复核**：共享写手在请求开始时记下 `book_uuid`（[ADR-0003](0003-dual-book-identity.md)），拿到锁后复核，不一致 → 409（书已换代）。删后再导入同一 EPUB 是**新书**
7. **进程内层**：真正的读写语义，不把共享持有者串行化；同一调用栈重复取书锁 → 抛错；**禁止共享→独占升级**；不用 dup / 继承的 fd 冒充线程互斥
8. **删书**：独占锁 → 锁内复核 → 从集合移除 → 改名为墓碑并 `fsync` 父目录（提交点）→ 失效进程内缓存 → 按请求删对话 → `rmtree` 墓碑 → 放锁。墓碑清扫**持有**对应书的独占锁再删，不是「探测后即释放」。步骤的定义处是 018 WI-5

**不保证**（明确不做）：

- 多 worker 部署：进程内缓存（`_stats_cache`、`BookUuidResolver`、`_BOOK_THREAD_LOCKS`）只在本进程失效
- NFS / SMB 等网络文件系统：`flock` 语义不可靠
- ChromaDB 自身的多进程访问（上游不支持）；向量**查询**不持书锁
- `FileResponse` 流式返回期间书被删：读到半截即失败，不做快照
- 对话「both」存储模式的两次发布之间的一致性——需要 revision，另案处理
- `_BOOK_THREAD_LOCKS` 注册表只增不减

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

- `018-library-routes` WI-2 实现锁模块并接入 notes、reindex（HTTP 与 CLI）、`ai_meta`、对话、向量；WI-5 接入删书
- 012 的写手（`--migrate`、generation swap、批量重建、上传、`process_epub`）在 012 接入（012 §4 门槛 14）
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
