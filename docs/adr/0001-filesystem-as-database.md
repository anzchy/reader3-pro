# ADR-0001: 文件系统即数据库——每本书一个 `books/{name}_data/` 目录，不引入 SQL

| 字段 | 值 |
|---|---|
| Status | Accepted |
| Decision date | 2025-12-17（首次出现于 commit `58531b9`，提交信息仅为「init commit」） |
| Recorded date | 2026-08-25 |
| Record type | Retrospective |
| Original rationale known | Partial |
| Confidence | Medium |
| Current compliance | Full |
| Evidence | `CLAUDE.md:178`、`CLAUDE.md:144-148`、`CLAUDE.md:284`、`src/reader3_app/web/server.py:386-390`、`src/reader3_app/web/server.py:469-472`、`src/reader3_app/web/server.py:332-335`、`docs/storage-and-data-locations.md:101-107`、`docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:651`、`:656`、`:291`、`docs/plans/20260816-tech-stack-migration/baseline-performance-008.md:87`、`src/reader3_app/notes_service.py:44-83`（工作区未提交改动，`git diff --stat HEAD` 确认）、git log `58531b9`（2025-12-17，`reader3.py` 首次出现） |
| Confirmation | `tests/contract/test_startup_lifespan.py`（断言启动扫描覆盖每一个 `*_data` 目录）、`tests/unit/test_safe_book_folder.py`（断言路径校验不逃逸出库根）、`tests/unit/test_notes_concurrent_write.py`（断言并发写不丢标注） |

## Context and Problem Statement

Reader3 Pro 是自托管单用户工具：一本书处理完之后，它的一切派生数据（`book.pkl`、`book.epub`、`images/`、`notes.json`、`ai_meta.json`、`chroma_db/`）要放在哪、用什么机制保证一致性。不做这个决定，`server.py` 就没有稳定的方式去枚举库里有哪些书、给每本书分配身份、按书隔离并发写入。

**Observed State**：今天的实现是「一书一目录」——`books/{book_id}_data/`（`book_id` 即处理后的文件夹名，例如 `dracula_data`）。目录内平铺：

- `book.pkl` —— 解析后的 spine + 元数据（`docs/storage-and-data-locations.md:105`）
- `book.epub` —— 原始 EPUB 副本，供 epub.js 渲染（`:106`）
- `images/` —— 抽取出的插图（`:107`）
- `notes.json` —— 标注（schema 见同文档 §「Book notes & annotations」）
- `ai_meta.json` —— 稳定的 `book_uuid`（`CLAUDE.md:144-148`）
- `chroma_db/` —— 按需生成的向量索引（同文档 §「RAG index」）

库首页启动时扫描 `BOOKS_DIR` 下所有 `*_data` 子目录来枚举「有哪些书」（`server.py:386-390`），启动生命周期钩子对同一批目录跑 `book_uuid_resolver.scan()` 以补全 UUID 映射（`server.py:332-335`）；所有按 `book_id` 定位文件的路由都先做「必须以 `_data` 结尾 + `os.path.basename` 恒等」校验，拒绝路径穿越（`server.py:469-472`）。没有 SQL、没有单一索引文件——文件系统的目录列表本身就是「有哪些书」这个查询的答案，一本书的这六类文件之间也没有外键，靠约定的文件名共处同一目录来关联。

**Original Rationale**：Unknown。`reader3.py` 与这套目录布局在 `58531b9`（2025-12-17，提交信息仅为「init commit」）首次出现，此前无 PR 记录、无设计讨论文档留存；此后的历次改动（如 `9115db9` 把书移到 `books/` 前缀下）都是路径调整，不是对「要不要用数据库」这一问题的重新表态。CLAUDE.md 把它写成 Constitution Principle 3「Filesystem IS the database」（`CLAUDE.md:178`），但该文件本身不记来源，只记结论。

**Current Assessment**（2026-08，`plan-tech-stack-migration.md` §11 的重新评估，非当年理由）：该文档把「引入 SQL 数据库」列入明确不做的事，理由原文是「文件系统即数据库的宪法原则保留」（`plan-tech-stack-migration.md:656`），即 2026-08 的迁移计划复核后选择维持现状，而不是重新论证。本 ADR 把这条「维持」記為 2025-12-17 决定的延续，而非独立的新决定。

## Decision Drivers

- 自托管单用户场景：没有多用户并发写同一本书的常态需求，SQL 的事务/隔离级别买不到与之匹配的收益。
- 书籍本身就是文件（EPUB、图片、pickle）；把它们的元数据也存成文件，避免「一部分数据在文件里、一部分在数据库里」的双写口径。
- 可调试性：任何一本书的状态可以用 `ls`/`cat` 直接查看和修改，不需要额外工具连数据库。
- 部署零依赖：不需要额外安装、迁移、备份一个数据库进程；`uv run reader3-server` 一条命令起服务，不需要先跑数据库迁移脚本。
- 路径安全模型天然对齐：只要每本书是独立目录，「校验 book id 是否落在库根之内」就退化成一次 `os.path.basename` 恒等比较加 `_data` 后缀检查（`server.py:469-472`），不需要 ORM 层再单独设一道防线。
- YAGNI（CLAUDE.md 宪法第 2 条「Simplicity Over Engineering」的直接推论）。

## Considered Options

1. **一书一目录 `books/{name}_data/`**（选定）——每本书的全部派生数据平铺在自己的文件夹里，文件夹名即主键之一。
2. **单一 SQLite 数据库**——所有书的元数据、标注、会话集中存一个 `.db` 文件。为什么不：`plan-tech-stack-migration.md` §11 明确否决，理由是「文件系统即数据库的宪法原则保留」（`plan-tech-stack-migration.md:656`）——即维持简单性优先于获得事务与索引能力；引入后还需要处理二进制资源（EPUB、图片）到底存文件还是存 BLOB 的新分歧。
3. **单一 JSON 索引文件**（如 `library_index.json` 汇总所有书的元数据）——为什么不：每次任意一本书的元数据变化都要重写整个索引文件，写放大随书库增长线性上升；且索引文件与各书目录的实际内容仍可能不同步，多了一个一致性来源而不是少了一个。

## Decision Outcome

维持「一书一目录、文件系统即数据库」：书的身份是目录名（`book_folder`）加目录内 `ai_meta.json` 里的稳定 UUID（`book_uuid`，见 CLAUDE.md「Book Identity System」，`CLAUDE.md:144-148`）；库的「查询」用目录扫描实现（`server.py:386-390`、`:332-335`）；路径校验是唯一的准入闸（`server.py:469-472`）。明确不做：不引入 SQL 数据库；不引入跨书事务；不为「更换存储引擎」单开工作量——012 分支要做的是同一目录布局下的文件格式迁移，见下方 Neutral。

## Consequences

### Positive
- 零外部依赖，`cp -r books/foo_data other_place/` 就是完整备份/迁移；删除一本书就是移除它的目录（CLAUDE.md「Troubleshooting」`:284` 把这写成标准操作：「Delete a book: Remove its `books/{bookname}_data/` directory」）。
- 单本书状态可用标准文件工具审查，天然对齐宪法第 6 条「Explicit Over Implicit」。
- 每本书的失败是独立的：一本书的 `book.pkl` 损坏不影响其他书可读（对照单一数据库文件损坏即全库不可用）。
- 库的「查询」不需要维护 schema：新增一种派生文件（例如按需生成的 `chroma_db/`）只是在目录里多放一个文件夹，不需要迁移脚本。

### Negative
- **无跨书事务**：不存在任何机制保证「同时改两本书的元数据」是原子的；今天没有任何功能需要这个能力，但如果将来出现（例如批量重排书架顺序），要么接受非原子，要么在应用层自己实现两阶段写。
- **单本书内的并发写此前完全无保护**：`notes_service.py` 是 load→modify→save 全量覆盖，`os.replace` 只保证单次写入原子，不防两个并发请求互相覆盖丢标注；自托管单用户开两个浏览器标签页即可触发（历史状态，`plan-tech-stack-migration.md:291` TODO 项记录了这个已知缺陷，并提出「加 revision/ETag，冲突时返回 409」或「per-file lock」两种修法）。工作区当前改动（未提交，`git diff --stat HEAD` 可见 223 行新增）选择了后者：`notes_service.py:44-83` 的 `_book_write_lock` 用 `threading.Lock` + `fcntl.flock` 把整段 load-modify-save 串行化，而不是走 409 乐观并发路线——即该 TODO 的解法与其原文列出的两个选项之一相符，但不是 409 那一支。这仍然只是「同一本书内的写串行化」，不是数据库级隔离。
- **书库大了要付目录扫描的开销**：`baseline-performance-008.md:87` 实测 20 本书时 `book_uuid_resolver.scan()` 中位数 4.6 ms（4.3–5.9 ms，±34.1%），该文档同时指出冷启动成本 86% 在 Python import 上、与书库规模无关——但这是 20 本书的读数，没有测过书库变大一个数量级之后扫描是否仍是可忽略量。

### Neutral
- 012 分支（`012-storage-format`）计划把单本书的持久化格式从 pickle 换成 manifest + jsonl（见 ADR-0009），但不改变「一书一目录」这层布局——目录仍是 `books/{name}_data/`，变的只是目录里那份主文件的格式。
- `book_uuid_resolver.scan()` 与「目录即索引」是同一决定的两个面：前者解决身份稳定性，本 ADR 只覆盖存储布局本身；身份系统的取舍见 ADR-0003。

## Revisit When

- 出现多用户或跨设备同步需求（当前架构假设单机单用户，任何形式的共享写入都需要重新评估文件系统方案是否够用）。
- 书库规模让目录扫描成为可测量瓶颈——`baseline-performance-008.md:87` 目前只有 20 本书、4.6 ms 的读数；需要在更大书库（如三位数以上）下补一次同口径基准，若中位数进入个位数百毫秒区间即触发重新评估。
- `_book_write_lock`（`notes_service.py:44`）的 `fcntl.flock` 方案在多进程部署（而非当前的单进程 `uv run reader3-server`）下被证明不够，需要重新论证要不要上数据库级别的并发控制。

## Related

- ADR-0003（书的双重身份：`book_folder` + `book_uuid`）
- ADR-0007（发布协议）
- ADR-0009（pickle 迁 manifest + jsonl 的存储格式决定；本 ADR 只覆盖目录布局，不覆盖单书内的文件格式）
- `CLAUDE.md`「Constitution Principles」第 3 条「File-Based State Management」→ 本文
- 原定义处：`docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md` §11「明确不做的事」中「❌ 引入 SQL 数据库」一行（`:656`）——2026-08-26 已改为指向本 ADR 的链接
