# ADR-0016: 书目录发布改为「每次发布写一个 `gen/{g}/`，根 `manifest.json` 一次 `os.replace` 是唯一提交点」；GC 延后一代，迁移不删平铺文件

| 字段 | 值 |
|---|---|
| Status | Proposed——维护者 2026-10-02 批准（外部评审 2026-10-02：Codex ＋ 独立 Fable 评审）；在 `012-storage-format` 合入的同一 PR 里转 Accepted（012 §4 门槛 18）。取代 [ADR-0007](0007-crash-safe-publish-protocol.md) 的**提交点与崩溃恢复**部分；ADR-0007 的读取三态与 pickle 日落两时间窗继续有效 |
| Decision date | 2026-10-02 |
| Recorded date | 2026-10-02 |
| Record type | Prospective |
| Original rationale known | Yes |
| Confidence | Medium——机制经 024 原型（1567/1567 崩溃格点、liveview、模拟 EXDEV）验证，并经 Codex 与独立 Fable 评审；尚未集成进 `src/`，真实跨卷 EXDEV 未跑 |
| Current compliance | None——见 Migration Strategy |
| Evidence | 原型证据 [`REPORT.md`](../plans/20260816-tech-stack-migration/tasks/evidence/q2-commit-prototype/REPORT.md) §3（B 的 b1–b10 步表）、§5.1（liveview：A 在 S1/S2 的 36 个钩子点里 16 个读成 `corrupt`，B 只有 `missing`/`old`/`new`）、§5.5（EXDEV 与 ADR-0007 的「退化为拷贝」错误、替换措辞）、§6 F1/F3、§7（半生目录与书库扫描）、§8（所有权与锁）、§9（推荐 B）、§10（Q8：`book_format.py`）；原型 `evidence/q2-commit-prototype/proto/mech_b_generation.py`（`_remove_legacy`、`recover_b` 的平铺删除——本文**否决**这两处）、`proto/generation_core.py`；以符号定位（行号以 `94dd1e0` 核对，会漂）：`reader3._commit_staged_artifacts`（`reader3.py:613`，A 形状：逐件 rename-aside 再换 marker）、`reader3._staging_dir`（`:207`，同级 `<book>_data.staging-<pid>`）、`process_epub` 取 EX 书锁（`:743`）；`book_store._load_book_for_stat`／`load_book_cached`（`book_store.py:66-89`，键为 `(book_id, books_dir, st_mtime_ns, st_size)`，今天**无** `st_ino`）；`book_lock.CATEGORIES`（无 `migrate`／`gc` 类别）；`tests/contract/routes.snapshot:44-45`（`/read/{book_id}/book.epub`、`/read/{book_id}/images/{image_name}`）；`012-storage-format.md` §6 Q2 |
| Confirmation | none（人工）——目标棘轮由 012 落地，见 Migration Strategy 末段 |

## Context and Problem Statement

[ADR-0007](0007-crash-safe-publish-protocol.md) 的提交协议是按「平铺产物 ＋ marker 最后换」写的：每件产物在书目录根上各自 rename-aside、换入，最后换 marker。012 起一本书的可再生产物变成 `manifest.json` ＋ `chapters.jsonl` ＋ `book.epub` ＋ `images/`（双写期另有 `book.pkl`），012 §6 Q2（2026-09-26）已定 marker 是 `manifest.json`，但把「多件产物怎样收成**一个**提交点」留给原型。[ADR-0015](0015-per-book-write-coordination.md) 让读者**不取锁**；在这个前提下，平铺布局在发布窗口里必然把新旧混合或缺件的状态暴露给并发读者（REPORT §5.1：A 在 S1/S2 的 36 个钩子点中 16 个读成 `corrupt`，另有 `pkl-only-new` 与存量书瞬时 `missing`）。今天的 `_commit_staged_artifacts` 已经是这个形状，只能在崩溃**之后**拒绝，挡不住窗口内的读者。另外 ADR-0007 四处写「跨设备 `os.replace` 退化为拷贝」，是事实错误（REPORT §5.5、F3）。

## Decision Drivers

- 读者不取锁（ADR-0015）：提交必须对无锁读者呈快照一致——任何时刻只看得见旧的完整版本或新的完整版本。
- 产物集合含目录（`images/`）且会继续变：提交点的数量不能随产物件数增长（A 每次发布 2＋2×现有产物次 rename，S1 下 10 次；B 恒为 1 次，REPORT §5.5）。
- 崩溃恢复要能机器判定、不依赖「事务身份」比较（REPORT F1：A 用 manifest 内容判「已提交」，内容相同的重发布会被误判前滚，留下 `corrupt`）。
- 书目录里同住不可再生的用户数据（ADR-0001／ADR-0007 Context），发布与恢复绝不能枚举或改写它们。
- 012 WI-7 的向量索引同样需要「整代换入」，最好与书共用一个核心（REPORT §5.4、§10）。
- 存量书（`book.pkl` 平铺）必须可迁移且可回退到旧二进制，迁移不能是删除事件。

## Considered Options

1. **B：generation 目录 ＋ 单指针**（选定）——每次发布在书目录内新建 `gen/{g}/` 写全部可再生产物，读回校验与 fsync 后，`os.replace("manifest.json.tmp", "manifest.json")` 一次翻指针。代价：约十处平铺路径要改为经指针解析；保留上一代占双倍磁盘；GC 与在途读者之间有一个以保留期为界的 TOCTOU 窗口。
2. **A：平铺 ＋ journal**——沿用 ADR-0007 的逐件 rename-aside，以 journal（含 `txid`）判前滚／回滚。为什么不：无锁读者在发布窗口里看到 `corrupt`／缺件／`pkl-only-new`（REPORT §5.1、F2），这是平铺布局固有的并发暴露，不是可修的 bug；10 个 EXDEV 面；需要 per-transaction 身份才能避开 F1；WI-7 仍要另做一套指针换代。今天的 `_commit_staged_artifacts` 就是 A 的形状，只能在崩溃后拒绝。
3. **维持 ADR-0007 现状、只补 `manifest.json`**——为什么不：即 A 去掉 journal，F1 与窗口暴露都在，且多产物下「marker 最后换」只挡一个方向（ADR-0007 缺口 2）。

## Decision Outcome

**提交协议（取代 ADR-0007 Decision Outcome 第 1–8 步与「三产物场景的两条协议缺口」）。** 发布全程持 ADR-0015 的 EX 书锁。步骤与 ADR-0007 的对应关系（细节见 REPORT §3「B」表）：

| 步 | 动作 | 对应 ADR-0007 |
|---|---|---|
| 0 | 断言 `os.stat(<book>/gen).st_dev == os.stat(<book>).st_dev`（`gen/` 尚不存在时以书目录自身为准），不等即拒绝发布、目录不动 | 新增（见下「EXDEV」） |
| 1 | `g = max(现存 gen/* 的编号, manifest.generation) + 1`；`mkdir gen/{g}`，写 `chapters.jsonl`（边写边记 offset／length／hash） | 1 ＋ 3 |
| 2 | fsync `chapters.jsonl` | 2 |
| 3 | 把 `book.epub`、`images/`、双写期的 `book.pkl` 写进 `gen/{g}/`，fsync | （2） |
| 4–5 | 写并 fsync `<book>/manifest.json.tmp`，其中含 `generation = g` 与各产物的 `size_bytes`／`sha256` | 4–5 |
| 6 | 对 `gen/{g}` 全量读回校验；失败则 rmtree `gen/{g}`、unlink tmp、抛错，旧状态一字节不动 | 6 |
| 7 | fsync `gen/{g}` 树、`gen/`、书目录——持久化屏障，**取代** ADR-0007 第 7 步（不再有 chapters 的 replace） | 7 |
| **8** | `os.replace("manifest.json.tmp", "manifest.json")` → fsync 书目录。**唯一提交点** | 8 |

原型的 b9（提交后立刻 GC 其余各代）由下文「GC」取代；b10 与 `recover_b` 第 4 步（删除平铺遗留文件）由下文「迁移」**否决**。

**四条规范性修订（2026-10-02 裁定）：**

1. **缓存与路由。**
   - 阅读页每次响应**只解析一次** g，向页面嵌入 `/read/{id}/g/{g}/book.epub` 与 `/read/{id}/g/{g}/images/{name}`；同一页面内的 epub.js（整包一次 arraybuffer XHR，无 Range）与封面从同一代取。
   - 旧路由 `/read/{id}/book.epub`、`/read/{id}/images/{name}` 保留为**别名**，每次请求经指针解析到当前代（书库页 `cover_url`、旧章节视图 HTML 里相对的 `images/…` 都走别名）。
   - **不用 immutable 缓存**：删书后再导入，generation 从 1 重新计数（ADR-0015 第 6 条：删＋导是一本新书），`/g/1/` 会指向不同字节。一律 ETag／Last-Modified（由所服务文件的 stat 派生）＋ `Cache-Control: no-cache`。
   - 新的图片路由用 `_validate_book_id` 校验书 id（今天的别名路由只做裸 `basename`，`reader.py:114`）。
   - generation、`gen/` 路径与提交时间**不进** `book_fingerprint`；批注（`chapter_index`／`quote`／`cfi`）不受影响。
   - 两条新路由按 [ADR-0011](0011-api-v1-freeze.md) 新增：同一 commit 更新 `tests/contract/routes.snapshot`。
2. **根目录用户数据的封闭清单。** `notes.json`、`notes.json.lock`、`ai_meta.json`、`ai_conversations/`、`chroma_db/`（含 `index_meta.json`）永远住在书目录根上，永不进入任何一代，永不被 GC。发布与恢复**只许枚举** `gen/*` 与 `manifest.json`／`manifest.json.tmp`，不得 `listdir` 书目录根再按排除法删除。WI-7 的索引换代是 `chroma_db/` 内部的另一套协议；generation 核心可以共用（REPORT §10），两者的指针与目录互不相交。
3. **安全 GC。**
   - **删除前校验**（只 stat，不读内容）：`manifest.json` 能解析、`format_version` 认识、`generation` 是 int、`gen/{g}` 是目录、manifest 记录的每件产物存在且大小与记录相符。任一不成立 → 该书判 `corrupt`（ADR-0007 三态，本文把这几条并入 `corrupt` 的判定），**什么都不删**，大声记日志。
   - **保留**：静止时最多 2 代（当前＋上一代），瞬时最多 3 代（另加构建中的一代或崩溃遗留的孤儿代）。凡不是当前代的 `gen/x`——包括比当前更新的崩溃孤儿——都按同一规则回收。
   - **何时删上一代**：(a) 下一次发布开始时，在 EX 锁内；或 (b) 启动／CLI 清扫，以**非阻塞** EX 取锁（`BookLockBusy` 即跳过该书），且仅当 `manifest.json` 的 mtime 早于 `RETAIN_S = 300` 秒。清扫**不得 `makedirs`**（ADR-0015 第 5 条）。
   - **不做**「`FileNotFoundError` 重试一次」：跨过一次 GC 的在途读者拿到 404。
   - 发布与恢复都持 EX 锁。ADR-0015 的 `book_lock.CATEGORIES` 是封闭清单，今天没有 `migrate`／`gc`：012 为 `--migrate` 与清扫各加一个持有者类别（命名归 012）。
   - **恢复**即 GC：校验通过后删除所有非当前代、unlink `manifest.json.tmp`；没有前滚／回滚判断。`manifest.json` 不存在时所有 `gen/*` 都是未引用的，可删（半生首发、迁移中崩溃）；`manifest.json` 存在但校验失败时一律不删（REPORT §3 `recover_b` 第 1 步的「读不懂就抛错」）。
4. **非破坏迁移。**
   - `--migrate` 以**拷贝**构建 `gen/1`（平铺 `book.epub`、`images/`、`book.pkl` 拷进去，再写 `chapters.jsonl`），走上表第 0–8 步提交；平铺文件**一个不动**。拷贝只用于填充一个尚未被引用的代，提交仍然是那一次 `os.replace`——这与「禁止用拷贝顶替 rename」不冲突。
   - 对存量书**重新导入**同样只新建一代、不删平铺文件。平铺文件的删除等日落步骤，那一步需要单独裁定。
   - 接受的代价：旧二进制看到的是陈旧的平铺版本。
   - 本条取代原型 b10 与 `recover_b` 的平铺删除。
   - **子裁定（双写期 pkl 的位置）**：双写期 `book.pkl` 写在**每一代内部**（`gen/{g}/book.pkl`），不写平铺。后果：012 下新发布的书没有降级路径（旧二进制看不到它）；只有迁移来的书保留一份平铺 pkl。平铺 pkl 何时删与日落一起定。

**本文同时确定的实现约束：**

- **缓存键**：`book_store` 的缓存对 manifest 书以 `manifest.json` 的 `(st_ino, st_mtime_ns, st_size)` 为键（`os.replace` 换指针必换 inode），对平铺书仍以 `book.pkl` 的 stat 为键；永不以 g 单独作键（g 会因删＋导复用）。
- **必须改为经指针解析的平铺路径站点**（以 `94dd1e0` 核对，行号会漂；012 WI-4 统一收进 `book_store`／`book_format`）：
  - `web/routers/reader.py`：`serve_epub`（`:24-31`，路径 `:28`）、阅读页 `images_dir`（`:80`）、`epub_available`（`:90`）、`epub_url`（`:98`）、`serve_image`（`:113-125`，路径 `:117`）；
  - `web/routers/library.py`：书库扫描（`:43`）、封面 `images`（`:49`）、`cover_url`（`:63`，保留走别名）；
  - `book_store.py`：`_book_pkl_path`（`:57`／`:63`）及上述缓存键；
  - `search_service.py`：`list_book_ids`（`:250-262`，`book.pkl` 判定在 `:259`）、`load_book_index` 的 stat（`:393`）；
  - `vector_search.py`：`_load_book`（`:112-114`）；
  - `reader3.py`：`--index` 入口对 `book.pkl` 的检查（`:930`）；`save_to_pickle`（`:901-911`，写平铺 `book.pkl`）；
  - `ai/books.py`：`BookUuidResolver.scan`（`:251-255`，另一处 `_data` 扫描）。
  - **棘轮**：WI-4 加一道 grep 门——`src/` 里除 `book_store`／`book_format` 外，出现 `"book.pkl"`、`"book.epub"`、`"images"` 与书目录拼接的路径即失败（白名单显式列出别名路由与迁移读平铺的那一处）。
- **扫描规则**（REPORT §7）：一个 `*_data` 目录既无 `manifest.json` 也无平铺 `book.pkl` 就**不是书**，静默跳过；`gen/` 单独存在**永远不是**书的证据。有 `manifest.json` 则要么 `valid`、要么大声 `corrupt`，不跳过。`_validate_book_id` 经 `list_book_ids` 判定，因此新图片路由的校验依赖 WI-4 先把 `list_book_ids` 改成这条规则。
- **`epub_available`**：manifest 书为「当前代 `gen/{g}/book.epub` 存在」；平铺书为「平铺 `book.epub` 存在」。只在解析出 g 的那一次响应里求值，与嵌入的 URL 同代。
- **EXDEV**：`rename(2)`／`os.replace` 只在同一文件系统内成立；跨设备时它**不退化为拷贝**，而是直接抛 `OSError(EXDEV)`（会退化为拷贝的是 `shutil.move`，本协议禁用它）。协议因此要求 generation 建在书目录**内部**（`<book>_data/gen/`），并在第 1 步之前断言 `st_dev` 相等，不等即拒绝发布、目录不动。跨卷部署下发布失败而不损坏，不是静默降级。（替换措辞取自 REPORT §5.5；本条更正 ADR-0007 第 25、52、67、78 行。）
- **退役同级 staging**：不再创建 `<book>_data.staging-<pid>`；pid／flock 所有权探测（`_acquire_staging_lock`、`_staging_dir_is_owned`、`_pid_is_running`）删除——EX 书锁下不存在「别人的在途运行」（REPORT §8）。**012 前遗留的同级 staging**（本文补充，裁定未明示）：保留只读的旧格式分类器（`_is_own_staging_name` ＋ `_parked_asides` 的判定）到日落，在 EX 锁内处理——纯残骸删除；含未落地提交（parked aside 未归位）或无法判定的遗留则拒绝发布并给出人工恢复步骤，不自动处理。
- **无锁读者的解析**：读一次 `manifest.json` 得 g，再打开 `gen/{g}/…`。解析与打开之间的 TOCTOU 窗口以保留期为界：g 被删除至少要求「之后又有一次发布开始」或「提交已逾 `RETAIN_S`」；跨过的读者得到 404／`FileNotFoundError`，不重试、不回退平铺。
- **manifest 的 `chapters[].order`**（2026-10-09 裁定 Q15/R6）：`order` 是该文档条目在原 EPUB spine 里的原始下标，非负、严格递增，但可以有空洞（被跳过的非文档或缺失的 spine 条目不占号），任何地方都不重新编号；条目在 `chapters[]` 里的位置才是阅读下标，与 `Book.spine[i]` 对齐。

**明确不做：** 不用 immutable 缓存；不在 GC 校验里读内容或算哈希（只 stat）；不自动删除平铺遗留文件（等日落裁定）；不为跨过 GC 的读者做重试；不为 `FileResponse` 提供快照（ADR-0015 的非保证不变）；不改 ADR-0007 的读取三态与 pickle 日落两时间窗——只把上面的 generation 校验条件并入 `corrupt`。

## Consequences

### Positive
- 无锁读者只可能看到 `missing`／旧／新三者之一（REPORT §5.1 liveview 0 个瞬态）。
- 每次发布恰好一次 rename：一个 EXDEV 面，无前滚／回滚判断，无 per-artifact × existed 表，无事务身份陷阱（F1 结构性消失）。
- 恢复退化为「删除未被指针引用的代」，「之前不存在的产物」这一类问题在结构上不存在。
- 书与 WI-7 索引共用一个 generation 核心。共用的是核心，不是锁：书的代由导入方持 EX 锁发布与回收；索引的代在根 sidecar `chroma_db/` 内，由重建索引方持它自己的锁（ADR-0015 的 SH 书锁 ＋ 资源锁）发布与回收——「回收在**写方的锁**内」，不另取 EX。

### Negative
- 静止时保留上一代：每本书常态约两倍可再生产物磁盘；迁移来的书在日落前另有一份平铺副本（最多约三倍）。
- 012 下新发布的书没有降级路径；只有迁移来的书保留平铺 pkl，且旧二进制看到的是它的陈旧版本。
- 约十处平铺路径站点必须改走指针；漏一处就会静默读到平铺旧版本或 404。
- 跨过一次 GC 的在途读者得到 404（不重试）。
- 新增两条公开路由，需按 ADR-0011 更新路由快照。

### Neutral
- `book_lock.CATEGORIES`（ADR-0015 封闭清单）要为迁移与清扫各加一个类别。
- 同级 staging 与 `_commit_staged_artifacts` 的 rename-aside／undo 在 012 后成为只读遗留处理。
- ADR-0007 Neutral 中「`--migrate` 只新增两文件、走八步原文」的说法由本文第 4 条取代。
- `book_format.py`（REPORT §10）是 Q8 的推荐落点；Q8 本身仍待维护者裁定，本文不裁。

## Migration Strategy

**现状：** `src/` 里没有 `gen/`、`manifest.json` 或 `st_dev` 检查；`_commit_staged_artifacts` 是 A 形状；`book_store` 缓存键无 `st_ino`；全部平铺路径站点仍直读书目录根。

**补差：** 全部由 `012-storage-format` 落地——WI-1 实现上表第 0–8 步与恢复（含旧 staging 分类器）；WI-4 把站点收进 `book_store`／`book_format` 并加 grep 门、改缓存键与扫描规则；`--migrate` 按第 4 条；两条新路由与 `routes.snapshot` 同一 commit；清扫入口与 `CATEGORIES` 新类别。

**目标棘轮（012 内落地后改写 Confirmation）：** 崩溃注入矩阵（每个钩子点只允许 `missing`／旧／新）；liveview 无锁读者快照一致性测试；GC 校验失败时零删除；根目录封闭清单在发布／恢复／GC 后 inode 与内容不变；`st_dev` 不等时拒绝发布；删＋导后 `/g/1/` 的 ETag 变化；WI-4 的 grep 门。原型测试名见 REPORT §4–§5。

## Revisit When

- 012 合入：核对实现与本文一致，Status 转 Accepted，Current compliance 更新，Confirmation 改指真实测试。
- 平铺遗留文件的日落步骤提出裁定：本文第 4 条的「不删」与平铺 pkl 的去留随之改写。
- 出现真实 EXDEV（第二卷上的 `books/` 部署）或真实跨卷测试失败。
- 保留期造成的磁盘占用被报告为问题，或 `RETAIN_S` 被证明短于真实读者窗口（出现可复现的 404）。

## Related

- [ADR-0007](0007-crash-safe-publish-protocol.md)：被本文部分取代（提交点、缺口 1／2、同级 staging、拷贝说法）；读取三态与 pickle 日落继续有效
- [ADR-0009](0009-book-format-manifest-jsonl.md)：格式本身、双写与日落；其中写入顺序与 `--migrate` 的落盘方式以本文为准
- [ADR-0015](0015-per-book-write-coordination.md)：EX 书锁、无锁读者、不 `makedirs`、删＋导即新书
- [ADR-0011](0011-api-v1-freeze.md)：新增路由的快照规则
- [ADR-0001](0001-filesystem-as-database.md)：文件系统即数据库
- [`012-storage-format.md`](../plans/20260816-tech-stack-migration/tasks/012-storage-format.md) §6 Q2（裁定行留一行链接到本文）、Q8
- 证据：[`evidence/q2-commit-prototype/REPORT.md`](../plans/20260816-tech-stack-migration/tasks/evidence/q2-commit-prototype/REPORT.md)；外部评审 2026-10-02（Codex、独立 Fable）
