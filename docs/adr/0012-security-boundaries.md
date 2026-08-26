# ADR-0012: 三条安全边界——`book.pkl` 的 unpickler 无回退加载器；path 校验只在拼路径前挡一次；凭据文件用 `mkstemp` 而不是仓库 `.tmp` 约定

| 字段 | 值 |
|---|---|
| Status | Accepted |
| Decision date | unknown（008 分支，尚未提交——`safe_pickle.py`、`safe_paths.py` 是未跟踪新文件；`ai/config.py` 里 `mkstemp` 那段是已跟踪文件的未提交修改；`git log -S'mkstemp' -- src/reader3_app/ai/config.py` 无任何提交命中，见 `git status`） |
| Recorded date | 2026-08-25 |
| Record type | Retrospective |
| Original rationale known | Yes |
| Confidence | High |
| Current compliance | Full |
| Evidence | `src/reader3_app/safe_pickle.py:1-25`（模块 docstring）、`:32-65`（allow-list 三块）、`:71-78`（`find_class`）；`src/reader3_app/safe_paths.py:1-32`（整份文件）；`src/reader3_app/web/server.py:714-730`（`read_chapter` docstring 与调用点）、`:772-778`（`_validate_book_id`）；`src/reader3_app/notes_service.py:29-35`（`_notes_path` docstring）；`src/reader3_app/vector_search.py:47-53`（`BookVectorIndex.__init__`）；`src/reader3_app/ai/books.py:26-32`（`_safe_folder_name`）；`src/reader3_app/ai/conversations.py:24-26`（`_safe_folder_name`）；`src/reader3_app/ai/config.py:154-176`（`save_ai_settings` 的 `mkstemp` 与「纵深防御」注释）；`src/reader3_app/notes_service.py:208-214`（`add_annotation` 引用同一理由）；仓库既有 `.tmp` 约定见 `src/reader3_app/reader3.py:355`、`ai/conversations.py:246,266`、`collections_service.py:74`；`CLAUDE.md:180`（Path Security 原则）；`AGENTS.md:40-64`（异常三档） |
| Confirmation | `tests/unit/test_safe_pickle.py`（P0-P4，含 `test_call_sites_import_safe_pickle_and_define_no_unpickler`）；`tests/unit/test_safe_book_folder.py`（T1-T5，`escape_lab` 承重资产比对）；`tests/contract/test_read_chapter_traversal.py`（P1/P2，`_call_asgi` 绕过 httpx 的 dot-segment 归一化）；`tests/unit/test_ai_settings_no_key_loss.py`；`tests/unit/test_notes_concurrent_write.py` |

## Context and Problem Statement

008 分支在同一批改动里新增/改写了三处安全相关代码，各自的取舍在 docstring 或注释里写得很完整，但互相不知道对方存在，也没有任何索引把它们并到一起看。三条各自读起来都像一处「没跟仓库其他地方对齐」的孤立写法——不回退的 unpickler、只有一个校验函数的路径闸门、明明有 `.tmp` 约定却改用 `mkstemp`——这正是它们最容易被新人（或未来的重构）当成「不一致」顺手统一掉的地方。

- **Observed State**：`safe_pickle.Reader3Unpickler.find_class` 是纯 allow-list，拒绝时 `raise`，没有 `super().find_class(...)` 兜底（`safe_pickle.py:71-78`）；`safe_paths.safe_book_folder` 是四个服务模块（`notes_service`、`vector_search`、`ai.books`、`ai.conversations`）拼路径前共用的唯一校验（`safe_paths.py:18-32`），`web/server.py` 的路由层另有一套基于枚举目录的 `_validate_book_id`（`server.py:772-778`），两者是两层不同的闸——见下方 Neutral；`ai/config.py:save_ai_settings` 用 `tempfile.mkstemp(dir=directory)` 而不是仓库里 `reader3.py:355`、`ai/conversations.py:246,266`、`collections_service.py:74` 那种固定的 `f"{path}.tmp"`（`config.py:163-169`），`notes_service.py:add_annotation` 采用同一手法并在注释里点名引用 `config.py` 作为先例（`notes_service.py:208-213`）。
- **Original Rationale**：三处都写在代码本身里，不是推断。

  1. **unpickler 无回退**（`safe_pickle.py:1-25`）：「Three modules … each carried a copy of a restricted unpickler *followed by* `f.seek(0); pickle.load(f)`. That fallback ran on any stream the restricted pass refused, which is precisely the set of streams worth refusing. The restriction was decorative.」（`:6-9`）「A `book.pkl` that genuinely cannot be read is a broken book, and saying so is better than executing it.」（`:14-15`）
  2. **单闸门在拼路径之前**（`safe_paths.py:1-10`）：「旧判据 `os.path.basename(x) == x` 放行了 `""`、`"."`、`".."` 三个值……于是 `os.path.join(books_dir, name)` 逃出库根……`notes_service` 与 `vector_search` 则一次校验都没有。」「调用点必须先过这个闸门再碰磁盘，否则「先写后抛」的实现照样毁数据。」（`notes_service.py:29-35` 逐字重复这条：「校验在拼路径之前，也就在任何读写之前。」）
  3. **凭据文件用 `mkstemp`**（`config.py:165-168`）：「这次偏离仓库既有写法是故意的，不是不一致：这个文件装的是凭据，两个并发写手（两个标签页同时保存设置）抢同一个固定 tmp 名本身就是一条凭据损坏路径，而 `mkstemp` 只多一行。顺带的好处：`mkstemp` 建文件时就是 0600。」`notes_service.py:208-213` 用英文复述同一理由并显式挂靠：「same reasoning as `ai/config.py:save_ai_settings` … A hard-coded temp name is shared state: two writers open *one inode* … whichever renames first publishes an interleaving … the other's `os.replace` fails with ENOENT, having dropped the annotation it was asked to persist.」
- **Current Assessment**（推断）：三条理由今天读起来依然成立，且三条有一个共同结构——**都是刻意的窄化，而不是遗漏**：unpickler 少做一件事（不兜底）换掉了「装饰性的校验」；path 校验只加一个函数、只做一类判断（拒绝分隔符与 `.`/`..`），不试图做更多；`mkstemp` 只多一行就换来了并发安全 + 0600 权限，覆盖面刻意限定在「凭据/标注」这两类不可再生数据。三者的成本都很低、收益都很具体，唯一的共同代价是：读代码的人看不到这份索引就会觉得它们「不统一」。这正是本 ADR 要解决的问题。

## Decision Drivers

- `pickle.load` 对任意来源的字节流是任意代码执行；`book.pkl` 是用户可控输入（换书、换来源都可能落一份精心构造的文件）。
- 宪法第 5 条（`CLAUDE.md:180`，Path Security）要求 book id 在拼路径前必须校验，但没有规定「校验发生在几处、以什么形式存在」——008 分支之前，四个服务模块里两个用了会放行 `.`/`..` 的旧判据，两个完全没有校验（`safe_paths.py:3-6`）。
- `AGENTS.md:40-64` 的异常三档规则要求「用户或运维需要知道吗」是判断能不能吞异常的唯一标准；一份读不懂的 `book.pkl`、一份读不懂的凭据文件，答案都是「需要知道」，不能静默降级为空。
- `ai_settings.json`（API key）和 `notes.json`（标注）都是不可再生数据：前者丢了要用户重新输入密钥，后者丢了是用户读书时留下的、无法凭空找回的笔记。
- 008 分支的准入判据（ADR-0000 §准入判据）：三条各自读起来都会被后来者当成「不一致」去统一，这正是「唯一定义处即将消失或不存在」的第二类候选——原理由分散在三个 docstring 里，没有索引就等于没有。

## Considered Options

**1. `book.pkl` 反序列化**
1. **allow-list 无回退，拒绝即 `raise`**（选定）——`find_class` 只认四个 dataclass 与一份内置类型白名单，其余一律抛 `pickle.UnpicklingError`。
2. **allow-list 拒绝后回退到 `pickle.load`**（原三份重复实现的写法）——为什么不：`safe_pickle.py:6-9` 已经指出，回退恰好只在「被拒绝的流」上触发，也就是「最值得拒绝的那一类」反而被无条件执行，校验形同虚设。
3. **彻底不读 pickle，等 012 换格式再统一处理**——为什么不：`012-storage-format`（见 ADR-0009）尚未落地前，`book.pkl` 是唯一的持久化格式，不读就是不能启动；`safe_pickle.py:20-24` 明确把「替换 pickle」列为本模块故意不做的事，留给 012 决定。

**2. book id 路径校验**
1. **服务层单一闸门 `safe_book_folder`，在 `os.path.join` 之前调用**（选定）——四个模块共用同一份判据与同一个 `ValueError` 文案。
2. **各服务模块各自写自己的 `basename`/正则校验**（008 分支之前的实际状态）——为什么不：`safe_paths.py:3-6` 记录了后果——两个模块的判据放行 `"."`/`".."`，两个模块完全没有校验；四条各自维护，改一处判据不会自动传播到另外三处，`tests/unit/test_safe_book_folder.py` 的 T2-T5 就是照着这四个真实漏洞逐一写的回归测试。

**3. 凭据文件原子写**
1. **`tempfile.mkstemp(dir=同目录)`**（选定）——kernel 保证的唯一文件名 + 隐式 `O_EXCL` + 创建时即 `0600`。
2. **统一成仓库既有的 `f"{path}.tmp"` + `os.replace`**——为什么不：`config.py:166-168` 点名这条路径的失效模式——两个并发写手（两个浏览器标签页同时保存设置）会抢同一个固定 tmp 文件名，一方的半截 JSON 覆盖另一方，这本身就是一条凭据损坏路径；`mkstemp` 换掉这个共享状态只多付一行代码。

## Decision Outcome

三条边界都保持现状（Full compliance，无需改动）：`safe_pickle.Reader3Unpickler` 是 `book.pkl` 唯一允许的加载器，且没有、也不应该有回退到 `pickle.load` 的路径；`safe_paths.safe_book_folder` 是 `notes_service`、`vector_search`、`ai.books`、`ai.conversations` 四个服务模块共用的唯一 book id 校验闸门，调用点必须在任何磁盘 I/O（包括 `os.path.join` 之后的进一步操作）之前调用它；`ai/config.py:save_ai_settings` 与 `notes_service.py:add_annotation` 对各自的凭据/标注文件使用 `tempfile.mkstemp`，与仓库其余原子写站点（`reader3.py`、`ai/conversations.py`、`collections_service.py`）的固定 `f"{path}.tmp"` 约定并存，这是记录在案的刻意分叉，不是待统一的技术债。**明确不做**：不把 `web/server.py` 路由层的 `_validate_book_id`（基于枚举目录）与服务层的 `safe_book_folder`（基于字符校验）合并成一套——两者是两层独立的闸，服务在下一节 Neutral 里说明；不在本 ADR 里评估或替换 pickle 本身，那是 012 的范围。

## Consequences

### Positive
- `book.pkl` 的反序列化面从「四份各写各的、其中至少一份会兜底执行任意代码」收敛成一份可审计、可测试的 allow-list（`tests/unit/test_safe_pickle.py` 的 P4 直接断言三个调用点都 import 同一份 `safe_pickle` 且不再各自定义 unpickler）。
- 服务层四个模块第一次有了共同、且经过回归测试覆盖的路径校验闸门；`tests/unit/test_safe_book_folder.py` 的 T2/T4 断的是磁盘状态而非「抛没抛」，堵住了「先写后抛」这类看似修好实则没修的实现。
- 凭据和标注两类不可再生数据的原子写不再有「两个写手抢同一个 tmp 文件名」的窗口，且 `mkstemp` 顺带把凭据文件的权限收紧到 `0600`。

### Negative
- `ALLOWED_READER3_CLASSES`／`ALLOWED_BUILTINS` 要随 `reader3.py` 里的 `Book` 系列 dataclass 手动演进：给 `Book` 加一个字段而忘了同步 allow-list，后果不是「新字段读不出来」而是**整本书读不出来**（`Reader3Unpickler` 直接 `raise`）——这是刻意的大声失败，但对不知道这层耦合的贡献者是一处容易踩的坑。
- `safe_book_folder` 是服务层的单点：闸门本身的 bug（例如漏掉某个分隔符变体）会同时影响 `notes_service`、`vector_search`、`ai.books`、`ai.conversations` 四个模块，不再是「一个模块的漏洞」而是「一类模块的漏洞」——集中带来的是可审计性，代价是攻击面也集中了。
- `mkstemp` 与仓库其余四处的 `f"{path}.tmp"` 约定并存，是本 ADR 存在的直接原因：不知道这份索引的人打开 `config.py` 或 `notes_service.py`，第一反应大概率是「这里该统一成仓库约定」，一旦真的改掉，就重新打开了两个并发写手互相覆盖 tmp 文件的窗口。

### Neutral
- `/api/*` 系列路由本身仍然没有本机鉴权（同 ADR-0006 的 Neutral 段）——这三条边界防的是「跨越目录/执行任意代码/丢数据」，不防「本机上能发 HTTP 请求的任何进程都能调用这些路由」；这是先于本 ADR 存在的前提缺口，不在本决定的解决范围内。
- 路由层的 `_validate_book_id`（`server.py:772-778`，basename + 对 `list_book_ids(BOOKS_DIR)` 的枚举成员校验）与服务层的 `safe_book_folder`（字符级拒绝，不做枚举）是两层独立的闸，分别服务两类不同的调用方——前者挡 HTTP 请求里的 `book_id` 路径参数，后者挡任何直接调用服务函数的调用方（CLI、脚本、011 重构后可能出现的新调用图）。两者互不知道对方存在，这是有意的纵深防御分层，不是重复。
- `012-storage-format`（见 ADR-0009）把持久化格式从 pickle 换成 manifest + jsonl 之后，`safe_pickle` 作为遗留 reader 会继续存在，直到 pickle 写路径被彻底移除为止；那之前它不是可以顺手删掉的死代码。

## Revisit When

- `012-storage-format` 分支移除 `book.pkl` 的写路径：`safe_pickle` 从「唯一加载器」退化为「遗留格式的兼容加载器」，需要新写一份 ADR 把本文件对应段落 supersede，而不是原地改。
- `reader3_app.reader3.Book`／`BookMetadata`／`ChapterContent`／`TOCEntry` 四个 dataclass 任一新增字段：`tests/unit/test_safe_pickle.py::test_all_four_dataclasses_are_on_the_allow_list` 应当第一时间抓住 allow-list 是否需要同步更新。
- `/api/*` 引入本机鉴权：届时「服务层单闸门只挡跨目录、不挡本机滥用」这条前提改变，需要重新评估三条边界是否还需要维持现在的形态。

## Related

- ADR-0000（`docs/adr/0000-use-adrs.md`）——本文件遵循的记录规则与四层文档分工。
- ADR-0006（`docs/adr/0006-provider-egress-single-gate.md`）——`/api/*` 无鉴权这条前提缺口的另一处体现，两份 ADR 各自记录自己那一半，不复述对方。
- ADR-0007、ADR-0009——同批（首批 0001–0013）收录的相邻决定，见 `docs/adr/README.md` 索引；ADR-0009 是 pickle 迁 manifest + jsonl 的存储格式决定，`safe_pickle` 的退役时机由它触发。
- `CLAUDE.md:180`「Path Security」——约束摘要保留，理由与后果的唯一定义处现为本文件。
