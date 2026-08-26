# ADR-0003: 一本书有两个身份——目录名走文件路径，`book_uuid` 走 AI 会话；`ai_meta.json` 读不懂就降级为 `uuid=None`，绝不覆盖原文件

| 字段 | 值 |
|---|---|
| Status | Accepted |
| Decision date | 身份拆分：unknown（首次出现于 commit `e897b67`，2025-12-18）；损坏降级规则：2026-08-24（commit `26420fa`） |
| Recorded date | 2026-08-25 |
| Record type | Retrospective |
| Original rationale known | Partial（身份拆分本身 Unknown；损坏降级规则的理由在代码与提交信息里完整） |
| Confidence | Medium |
| Current compliance | Full |
| Evidence | `CLAUDE.md:147-151`；`src/reader3_app/ai/books.py:21-23`（`BookIdentity`）、`:39-73`（`_read_ai_meta` 的读—抛规则）、`:122-169`（`_mint_first_uuid` 的并发防护）、`:200-212`（`ensure_book_uuid`）、`:214-272`（`BookUuidResolver` 双向索引）；`src/reader3_app/safe_paths.py:18-27`（`safe_book_folder`）；`src/reader3_app/web/server.py:366-389`（`_book_uuid_or_none`）；`src/reader3_app/web/templates/reader.html:1706`、`library.html:1305`（`or ''`）；commit `e897b67`（2025-12-18，`book_uuid` 首次出现）；commit `26420fa`（2026-08-24，损坏降级规则引入）；`tests/contract/test_degradation_book_uuid.py:1-23`；`tests/unit/test_book_uuid_race.py`；`docs/storage-and-data-locations.md:35-36,62-63`（`localStorage` / 项目根镜像目录均以 `book_uuid` 命名）；`docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:311-323`（Phase 3 明确不动 `ai_meta.json`） |
| Confirmation | `uv run pytest tests/unit/test_exception_book_uuid.py tests/unit/test_ai_meta_no_key_loss.py tests/unit/test_book_uuid_race.py tests/contract/test_degradation_book_uuid.py`——四份文件均已核实存在，且都在 `.claude/tdd-guardian/config.json` 的 `unit` lane 里，gate 于 `commit` / `taskCompleted` |

## Context and Problem Statement

一本书要被两类不同的东西定位：文件系统操作（读 `book.pkl`、`notes.json`）需要一个能拼路径的名字；AI 会话需要一个跨重命名、跨迁移都稳定的键。这两种需求今天用两个不同的字段满足。

- **Observed State — 两个字段**：`books/{book_folder}/` 是目录名，任何服务函数拼路径都用它（`src/reader3_app/ai/books.py:35` `_ai_meta_path`）。`book_folder/ai_meta.json` 里存一个 `book_uuid`，AI 会话、`/api/ai/*` 路由、`localStorage` 里的模型选择全部以它为键（`CLAUDE.md:147-151`）。`BookIdentity` dataclass 把两者绑在一起返回（`src/reader3_app/ai/books.py:21-23`）。
- **Observed State — 双向索引与并发防护**：`BookUuidResolver`（`src/reader3_app/ai/books.py:214-272`）在内存里维护 `_folder_to_uuid` 与 `_uuid_to_folder` 两张互逆的表，`scan()` 在服务启动时全量建表，单本书解析走 `book_uuid_for_folder` / `folder_for_book_uuid` 的懒加载路径。首次生成 `book_uuid` 走 `_mint_first_uuid()`，用 `os.link` 的 create-if-absent 语义防止两个并发请求各自铸出不同 uuid 再互相覆盖（`src/reader3_app/ai/books.py:122-169`，`tests/unit/test_book_uuid_race.py`）。
- **Observed State — 校验各管一段**：`book_folder` 一侧的校验是独立的一层，`safe_book_folder()` 拒绝空串、`.`、`..`、路径分隔符与 NUL 字节（`src/reader3_app/safe_paths.py:18-27`），与 `book_uuid` 一侧「必须能被 `UUID()` 解析」的校验彼此不知道对方存在——两套规则各自演化，没有共享的「book id 校验」抽象。
- **Observed State — 损坏降级**：当 `ai_meta.json` 存在但解析不出合法 `book_uuid`（损坏、非法 JSON、`book_uuid` 不是字符串或不是合法 UUID）时，`server._book_uuid_or_none()` 捕获异常、记警告、返回 `None`，**原文件一个字节不改**（`src/reader3_app/web/server.py:366-389`）；两个模板必须把 `None` 渲染成空串而不是字符串 `"None"`，否则前端会拿着 `"None"` 当 uuid 发请求（`reader.html:1706`、`library.html:1305`）。
- **Observed State — book_uuid 的辐射范围**：不止后端路由，浏览器 `localStorage` 里 `reader3.ai.model.{book_uuid}.{provider}`、`reader3.ai.activeConversation.{book_uuid}.{provider}` 两个键，以及可选的 `conversations/{book_uuid}/` 项目根镜像目录，全部以 `book_uuid` 而非 `book_folder` 命名（`docs/storage-and-data-locations.md:35-36,62-63`）——这是双身份代价最直接的体现：一旦 `book_uuid` 变了，这些客户端状态就跟着孤立。
- **Original Rationale**：身份拆分本身——为什么不直接用目录名做 AI 会话的键——查不到设计讨论。`book_uuid` 第一次出现在 commit `e897b67`（2025-12-18，「多会话＋磁盘持久化」功能提交），提交信息与同批 spec 变更只描述了「conversations 存到磁盘、按 book_uuid 分文件」这一实现事实，没有一句解释为什么不直接用 `book_folder` 当键。**Unknown。**
- **Original Rationale（损坏降级规则）**：完整可查。commit `26420fa` 说明旧行为是 `ensure_book_uuid()` 读不懂 `ai_meta.json` 就静默生成新 uuid 并覆盖原文件，导致用户全部 AI 会话失联且原值已被删除；新行为改为捕获并转译（`server.py:366-389` 称为「第 2 档」），让异常止步于调用点、原文件保持不动，因为直接让异常传上去会变成「一本书的元数据坏掉 → 整个书库首页 500」，用户连能修它的界面都进不去。
- **Current Assessment**（推断）：拆分本身现在看是合理的——目录名要保持人可读、要跟 `uv run reader3` 的产物命名习惯一致（`{book_name}_data`），而 AI 会话需要一个重命名/移动目录都不失效的键，两者用同一个字段无法同时满足。但这是今天的复盘，不是当年的决定理由。

> 「错误处理不该比错误本身更糟。」——`src/reader3_app/web/server.py:373`

## Decision Drivers

- AI 会话（`/api/ai/conversations/{book_uuid}/...`）必须在用户重命名或移动 `books/{book_folder}/` 之后依然可解析，纯文件名做不到这一点。
- 目录名要保持人可读，并且要与 `uv run reader3 ./books/<file.epub>` 产出 `{book_name}_data` 目录的既有约定兼容。
- `ai_meta.json` 是这本书唯一的会话索引来源，损坏时「让用户能看见并修复它」比「静默丢弃或让整站崩溃」重要（commit `26420fa`）。
- 宪法第 5 条（Path Security）要求所有 book id 在拼路径前经过校验——`book_folder` 一侧已由 `safe_book_folder()` 兜底，`book_uuid` 一侧的校验是 `UUID(str(book_uuid))` 类型转换（`src/reader3_app/ai/books.py:255`）。
- 首次生成 `book_uuid` 的路径必须在并发请求下收敛到同一个值：两个 uvicorn worker 或一次服务启动扫描与一次首次 API 调用同时命中同一本新书，谁都不能让对方的 uuid 失效（`tests/unit/test_book_uuid_race.py` docstring）。
- 前端已有依赖 `book_uuid` 是否为空判断「该书 AI 功能是否可用」的既有分支（`library-chat.js` 的 `if (!this.bookUuid)`），降级规则必须保证这条分支被正确触发，而不是引入第三种状态。

## Considered Options

1. **双身份：目录名管文件路径，`book_uuid` 管会话**（选定）——两套映射由 `BookUuidResolver` 双向维护（`book_uuid_for_folder` / `folder_for_book_uuid`），损坏时降级为 `None` 而不覆盖。代价：两个键要保持一致，`ai_meta.json` 成为额外的一份需要维护的状态；每新增一处按 book id 拼路径或建索引的代码，都要想清楚它该用哪一个键，用错了不会在类型层面报错——两者都是 `str`。
2. **只用目录名做一切键，取消 `book_uuid`**——为什么不（推断，非当年记录）：用户改名或移动 `books/{book_folder}/` 会让所有历史 AI 会话与该书失联，因为磁盘上的会话文件、`localStorage` 里的模型偏好全部以旧名字为键，重命名当场变成一次不可逆的数据丢失事件；没有一个当年的讨论记录印证这是被考虑过又否决的方案，这里只是复盘时能想到的最直接的替代设计。
3. **只用 `book_uuid`，连目录也按 uuid 命名**——为什么不（推断，非当年记录）：目录名会变成不可读的十六进制字符串，与 `uv run reader3 ./books/dracula.epub` 生成 `dracula_data` 这个可读产物名的既有约定直接冲突，用户在文件系统里找书、用命令行工具直接操作 `books/` 目录时会失去唯一的直觉线索；同样没有查到当年的讨论记录，标记为推断。

## Decision Outcome

保留双身份：`book_folder`（目录名）承担一切文件路径拼接，`book_uuid`（`ai_meta.json` 里的字符串，规范化为 `str(UUID(...))`）承担一切 AI 会话与前端偏好的键。两者由 `BookUuidResolver` 维护双向映射并在启动时 `scan()`。**明确不做**：不为「目录名与 `book_uuid` 不一致」设计自动修复或对账机制——两者本就是两套独立索引，允许分别演化。当 `ai_meta.json` 缺失、格式不合法 JSON、不是对象、`book_uuid` 字段存在但不是字符串或不是合法 UUID 时，`_book_uuid_or_none()` 捕获 `(OSError, ValueError)`、记服务端 warning、返回 `None`，调用方渲染成该书 AI 功能不可用（404 / 前端隐藏入口），**绝不**据此重新生成并覆盖 `ai_meta.json`。

同样明确不做的是「跨书合并」与「uuid 重新绑定」：`ensure_book_uuid()` 只有铸造一条路径，没有替换已有值的入口，这一点不在本决定的范围内改变。

## Consequences

### Positive
- AI 会话在用户重命名或移动书籍目录后依然可通过 `book_uuid` 解析（只要 `ai_meta.json` 本身随目录一起移动）。
- `ai_meta.json` 损坏是可逆的：原文件不会被覆盖，人工修复后即可恢复全部会话，这是相对「静默重新生成 uuid」的根本改进（commit `26420fa`）。
- 降级路径有三处独立可观测证据（服务端 warning、AI 端点 404、前端提示分支），不是静默失败。
- 首次铸造 `book_uuid` 的并发冲突有专门测试兜底（`tests/unit/test_book_uuid_race.py`），两个同时到达的请求保证返回同一个 uuid，不会有客户端拿着一个日后解析不到的值。

### Negative
- 两个键要维护一致：目录名与 `ai_meta.json` 里的 `book_uuid` 分别存在，除 `BookUuidResolver.scan()` 建立的内存映射外没有持续一致性校验。
- `ai_meta.json` 损坏或缺失时，用户看到的是「这本书的 AI 会话消失了」，而不是一条解释性的错误——降级是有意为之，但普通用户看不出原因，只有查服务端日志才知道。
- 若 012 分支（`012-storage-format`）的 `manifest.json` 未来吸收 `book_uuid` 字段，`ai_meta.json` 会退化为一个兼容层，双身份的「第二套索引」职责就要在两个文件间重新划分。
- `book_uuid` 一旦写入 `ai_meta.json` 就不可再生成第二个：`ensure_book_uuid()` 找到已有值直接返回，没有「重新绑定」或「合并两本书」的操作路径，误建的重复书目前只能靠人工编辑 JSON 文件解决。

### Neutral
- `BookUuidResolver` 的内存映射只在进程内有效、只在 `scan()` 或懒加载时刷新；多进程（多个 uvicorn worker）各自维护一份独立缓存，一致性只靠磁盘上的 `ai_meta.json` 与 `_mint_first_uuid()` 的 `os.link` 原子性保证，不靠进程间共享状态。
- `book_folder` 与 `book_uuid` 的校验规则相互独立、互不复用（`safe_book_folder()` vs. `UUID(str(...))`），因此新增一类 book id 校验规则时要记得两处都要改，本文件不改变这一点。

## Revisit When

- 012 分支（`012-storage-format`）冻结 `manifest.json` 字段集合时——需要明确决定 `book_uuid` 是否迁入 `manifest.json`，还是继续留在 `ai_meta.json` 独立存在（目前 Phase 3 计划明确排除 `ai_meta.json` 于格式变更范围之外，见 `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:311-323`）。
- 出现跨机器同步需求（例如多设备共享同一书库）：届时目录名与 `book_uuid` 谁是「真身份」需要重新评估，因为两台机器上同一本书的目录名可能不同但 `book_uuid` 应当相同。

## Related

- ADR-0000（`docs/adr/0000-use-adrs.md`）——本文件遵循的记录规则与四层文档分工。
- ADR-0001、ADR-0009——同批（首批 0001–0013）收录的相邻决定，见 `docs/adr/README.md` 索引。
- `CLAUDE.md:147-151`「Book Identity System」——约束摘要保留，理由与后果的唯一定义处现为本文件。
- `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:311-323` —— Phase 3（012 分支）关于 `ai_meta.json` 不在存储格式变更范围内的记录；本文件是「为什么双身份」的唯一定义处，那里不复述。
- `docs/storage-and-data-locations.md` —— 「现在是什么样」的现状文档，记录 `book_uuid` 出现的每一处存储位置；本文件只回答「为什么」，两者不重复彼此的内容。
