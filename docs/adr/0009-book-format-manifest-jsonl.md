# ADR-0009: 书的持久化格式从 `book.pkl` 迁到版本化 `manifest.json` + `chapters.jsonl`，经双写期后按版本号日落 pickle

| 字段 | 值 |
|---|---|
| Status | Proposed |
| Decision date | 2026-08-17（`docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md` 首次写入 `chapters.jsonl` 的提交 `5d43c80`） |
| Recorded date | 2026-08-25 |
| Record type | Prospective |
| Original rationale known | Yes（迁移本身的理由——见 Decision Drivers） |
| Confidence | High |
| Current compliance | None |
| Evidence | `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:304-306`、`:308-318`、`:319`、`:321`、`:322-323`、`:325`、`:381`、`:385`、`:728-729`、`:732-735`；`src/reader3_app/safe_pickle.py:1-25`；`src/reader3_app/reader3.py:675-679`（当前 pickle 写入）、`:685-693`（`save_to_pickle`）；`CLAUDE.md:24`、`:75`、`:86`（架构图与 Data Flow 仍写 `book.pkl`）、`:250`（`012-storage-format` 里程碑，Allocated）；`pyproject.toml:3`（当前版本 `1.4.0`，日落目标 major 未钉死） |
| Confirmation | none（尚不存在）。012 需要补三条，名称见 Migration Strategy：崩溃注入测试、`--migrate` 侧写数据字节不变 + `book_fingerprint` 不变测试、真实 iframe 标注迁移 E2E |

## Context and Problem Statement

Reader3 Pro 今天用 `pickle.dump`/`pickle.load` 序列化整本书（`reader3.py:675-679`）。`pickle.load` 对不可信输入等价于任意代码执行，`safe_pickle.py` 已经把「读」这一半的风险堵掉（受限 `find_class` allow-list，无 fallback），但它的文档明确说这不是终局：迁移到别的磁盘格式是 `012-storage-format` 分支的事，`safe_pickle.py` 不代它做（`src/reader3_app/safe_pickle.py:1-25`）。本文回答的问题是：那次迁移换成什么格式、以什么节奏切换、旧格式什么时候真正消失。

**Observed State（pickle 现状）**：写入端目前只有一条路径——`process_epub()` 在 staging 目录里把 `final_book` 直接 `pickle.dump` 成 `book.pkl`（`reader3.py:675-679`），再由 `save_to_pickle()`（`reader3.py:685-693`）保留为「其他代码把内存里改过的 Book 重新落盘」的受支持方式，其内部走 `_write_pickle_atomically()`（同文件 `348-366` 行，tmp + `os.replace` 保证不产出半写文件）。`CLAUDE.md` 的架构图与 Data Flow 依旧把 `book.pkl` 列为唯一持久化产物（`CLAUDE.md:24,75,86`）。读取端已经收紧（`safe_pickle.py`），但格式本身没有变。

**Original Rationale（当年为什么选 pickle）**：Unknown。按 ADR-0000 原则四，这不是一个值得单独开 ADR 去挖的问题——`reader3.py` 与 `book.pkl` 在初始提交里就已经存在，此后的历次改动都是在这个格式上打补丁（`_write_pickle_atomically`、`safe_pickle.py`），没有一次是重新论证「要不要用 pickle」。本文不补这段历史，只记录现状与要往哪走。

## Decision Drivers

- **安全面**：`pickle.load` 对不可信输入等于任意代码执行；现有 `_Reader3Unpickler`/`safe_pickle.py` 只是收紧了 `find_class`，不是把格式本身换成不可执行的数据格式（`plan-tech-stack-migration.md:306`；`safe_pickle.py:1-25`）。
- **细粒度读取**：书库首页与单章阅读今天都要经过一次全量反序列化才能拿到需要的一小部分数据（对应性能问题 C5，`plan-tech-stack-migration.md:758`）。`A5` 明确指出，如果新格式只暴露 `load_book()` 整体读取，JSONL 会「退化为换扩展名的 pickle」——必须让 `manifest.json` 记录每章 `offset_bytes`/`length_bytes`/hash，`chapters.jsonl` 按偏移 seek 读取（`plan-tech-stack-migration.md:734`）。
- **迁移不能波及同目录的用户数据**：`notes.json`、`ai_meta.json`、`chroma_db/` 与书的正文存储同放在 `{book_id}_data/` 下；摄取路径在写入前会 `shutil.rmtree(output_dir)`，任何迁移命令一旦借道摄取路径就会连带删掉标注、会话与向量索引（`plan-tech-stack-migration.md:322-323`）。
- **不能让在用的书库一次性失效**：存量 `book.pkl` 必须继续可读一段时间，新旧格式要能共存，读取失败要能明确区分「还没迁移」与「迁移后坏了」。
- **标注锚定依赖指纹稳定**：`book_fingerprint()` 是 notes/chroma 判定 stale 的唯一依据（ADR-0001 Related）；纯格式转换如果意外改变指纹，会让全库标注一次性判 stale（`plan-tech-stack-migration.md:381`）。

## Considered Options

1. **`manifest.json` + `chapters.jsonl`**（选定）——元数据/格式版本/spine·TOC 结构放 `manifest.json`，每行一章（`{id, href, title, content, text, order}`）放 `chapters.jsonl`，与 `book.epub`/`images/`/`notes.json`/`ai_meta.json`/`chroma_db/` 同目录平铺（`plan-tech-stack-migration.md:308-318`）。`manifest.json` 记录每章 `offset_bytes`/`length_bytes`/hash 支持二进制 seek，书库页只读 manifest、单章阅读只读一行（`:734`）。
2. **保留 pickle**——为什么不：`pickle.load` 对不可信输入等于任意代码执行，是「实际的迁移阻塞点与安全隐患」，现有的受限 unpickler 只是兼容 shim（`plan-tech-stack-migration.md:306`）；`safe_pickle.py` 自己也说格式层面的问题不归它管（`safe_pickle.py:15-25`）。
3. **单个 JSON 文件（整本书一个 blob）**——为什么不：只暴露整体读取会让新格式「退化为换扩展名的 pickle」，书库首页与单章阅读拿不到只读一部分数据的收益，白白继承 pickle 今天的性能问题（C5，`:758`）；`A5` 因此要求按行/按偏移可寻址（`:734`）。
4. **SQLite**——为什么不：本仓库已在 ADR-0001 否决单一数据库路线（「文件系统即数据库的宪法原则保留」，`plan-tech-stack-migration.md:656`），本 ADR 不重新论证，只维持目录布局不变、变的是目录里那份主文件的格式（ADR-0001 Neutral）。

## Decision Outcome

新处理的书写双份：`manifest.json` + `chapters.jsonl`（新格式）与 `book.pkl`（旧格式）同时产出，读取优先新格式（`plan-tech-stack-migration.md:319`）。两文件的写入顺序、崩溃安全保证、以及 `missing`/`corrupt`/`valid` 三态读取判定，是 ADR-0007 的定义范围，本文只引用、不重复。

> ⬛ **2026-10-02 指针：** 写入顺序与崩溃安全、产物落在 `gen/{g}/` 还是平铺、`--migrate` 以拷贝构建 `gen/1` 且不删平铺文件，现由 [ADR-0016](0016-generation-directory-publish.md) 定义；本文 Considered Options 1 的「同目录平铺」、下段 `--migrate` 的落盘方式、以及 Negative 与 Migration Strategy 里对 ADR-0007 两文件提交／第 7、8 步的引用，一律按 ADR-0016 读。三态读取仍归 ADR-0007。

存量书库的迁移由独立命令 `reader3 --migrate <book_id>` 提供，硬约束是**原地读写、禁止复用摄取路径**：摄取路径在写入前 `shutil.rmtree(output_dir)`，会连带抹掉 `notes.json`/`ai_meta.json`/`chroma_db/`；`--migrate` 只允许「读 `book.pkl`（或 `book.epub`）→ 写 `manifest.json` + `chapters.jsonl` → 校验 → 结束」，全程不删任何既有文件（`plan-tech-stack-migration.md:322-323`）。且 `--migrate` **不得改变** `book_fingerprint()`——指纹涵盖原 EPUB hash、spine href/order、每个 XHTML 原始内容 hash 与解析器版本，纯粹的存储格式转换一样都不该碰；指纹若变，ADR-0001 的分级降级会让全库标注一次性判 stale（`:381`）。

日落分两段，以「停写 pkl」为界：

- **双写期**（现在 → 停写 pkl 之前）：pkl 是与新格式**同期产出的对等产物**，不是遗留数据。读取端遇到 `missing`（无 `manifest.json`）状态走 pkl 是正常流程，**不需要环境变量**（`plan-tech-stack-migration.md:378-379`，转引自读取状态机小节，归属见下）。
- **稳定一个大版本后**（当前 `pyproject.toml` 版本 `1.4.0`；具体日落到哪个 major 号 plan 未钉死，留给 012 落地时定并回填本 ADR）：**移除 pickle 写入路径**——此后新处理的书不再产出 `book.pkl`（`:325`）。此后目录里剩下的 pkl 才是真正的遗留数据，读取端保留一条默认关闭的回退：显式设置 `READER3_ALLOW_PICKLE=1` 才读它，且每次启动明确告警；pkl 文件本身不删除。这条回退必须配退出机制——写明停止 pkl 写入的版本号、删除 runtime fallback 的版本号、每次启动告警、提供 `--migrate-all` 与未迁移库存清单；`--migrate` 用专用 legacy loader，不要求用户先开全局环境变量（`:728-729`）。

**明确不做**：不在 `safe_pickle.py`（unpickler 层）里做格式迁移——那是本 ADR 的职责，`safe_pickle.py` 只收紧了读取安全，两者刻意分开（`safe_pickle.py:15-25`）；不改变「一书一目录」的目录布局（ADR-0001）；不把 `notes.json`/`ai_meta.json`/`chroma_db/` 纳入本次格式变更范围；不复述两文件提交协议与三态读取判定（ADR-0007）。

## Consequences

### Positive
- 消除 `pickle.load` 对不可信/损坏输入的任意代码执行面——新格式是纯数据（JSON/JSONL），没有「反序列化即执行」的攻击面（`:306`）。
- 书库首页与单章阅读可以只读需要的字节：manifest 记录逐章偏移，不必再为了取标题或校验指纹而反序列化整本书正文，直接回应性能问题 C5（`:734`、`:758`）。
- 新格式是纯文本，可以直接 `cat`/`jq` 检查和修复，比二进制 pickle 更贴近 ADR-0001 已确立的「可调试性」路线（推断，非 plan 原文）。

### Negative
- **双写期磁盘翻倍**：每本书同时保留 `book.pkl` 与 `manifest.json` + `chapters.jsonl` 两份等价数据，直到停写 pkl 的那个大版本发布为止。
- **两条读路径长期并存**：至少一个大版本周期内，`book_store.py` 要同时维护新格式读取与 pkl 回退，任何格式相关缺陷有两处要查、两处要测。
- **迁移引入 pickle 时代不存在的失败态**（manifest 已落盘、chapters 只写了一半）——需要 ADR-0007 的两文件提交协议兜底；本 ADR 单独看是不完整的，必须与 ADR-0007 一起读。
- **旧版本用户升级后若 `--migrate` 中断**，能否安全恢复取决于 ADR-0007 的提交协议是否真的保证「协议第 7 步之后、第 8 步之前中断，重启仍可正常打开」——这条恢复路径不是本 ADR 能独立保证的。
- **`chapters.jsonl` 不支持随机访问**：一行文本文件天然只能顺序扫描，必须靠 `manifest.json` 额外记录每章 `offset_bytes`/`length_bytes`/hash 才能 seek 读取（`:734`）——多出一份需要与 `chapters.jsonl` 保持同步的偏移表，偏移算错就是静默读到别的章节。

### Neutral
- 目录布局不变：仍是 `books/{book_id}_data/` 一书一目录，变的只是目录里那份主文件的格式（ADR-0001 Neutral 已经这样定义了两者边界，且已提前指向本 ADR）。
- `storage_format(book_id) -> Literal["missing","corrupt","valid"]` 成为 `book_store.py` 公开接口契约的一部分（`plan-tech-stack-migration.md` A5）。**签名由 [ADR-0007](0007-crash-safe-publish-protocol.md) 的「读取状态机」小节定义，那里是唯一定义处，本行只引用。**

  > ⚠️ **2026-09-23 订正：本行此前写的是 `Literal["json","pkl"]`。** 那是 ADR-0007 粗体点名否掉的二态签名——它把「没迁移」（`missing`，正常，走 pkl，不告警）和「迁移坏了」（`corrupt`，必须大声失败、**不许**静默回退 pkl）归成同一件事。本 ADR 的 Consequences 本来就写着「必须与 ADR-0007 一起读」，而这一行恰好没有跟它读。**本 ADR 仍是 `Proposed`、compliance 为 `None`，尚未生效，故为直接订正而非 supersede。** 发现路径见 `docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md` 的 2026-09-23 「010 退出门槛逐条实测」小节（门槛 D-6）。
- `ai_meta.json` 里的 `book_uuid` 是否并入 `manifest.json`，留给 012 冻结字段集合时决定，不是本 ADR 现在要回答的问题（ADR-0003 Revisit When）。

## Migration Strategy

Current compliance 是 None：今天只有 pickle 写入路径（`reader3.py:675-679`、`:685-693`），`safe_pickle.py` 收紧了读取安全但没有换格式；`manifest.json`/`chapters.jsonl`/`book_store.py`/`--migrate` 均不存在。

- **分支**：`012-storage-format`（`CLAUDE.md:250`，milestone 表当前状态为 Allocated，尚未开出）。
- **棘轮**（012 验收硬门槛，来自 `plan-tech-stack-migration.md:385`，目前均不存在，按此描述补齐，文件名为占位建议）：
  1. **崩溃注入测试**：在两文件提交协议第 7 步之后、第 8 步之前中断，重启后该书仍能正常打开（状态判为 `missing`，走 pkl），且下一次迁移能干净重跑。建议 `tests/unit/test_migrate_crash_injection.py`。
  2. **迁移不动用户数据**：一条测试证明 `--migrate` 后 `notes.json`/`ai_meta.json`/`chroma_db/` 三者字节不变，且 `book_fingerprint(book_id)` 迁移前后相等。建议 `tests/contract/test_migrate_preserves_sidecar_data.py`。
  3. **真实 iframe 标注迁移 E2E**：至少一条，覆盖「逐章文本相等 ≠ DOM/CFI 路径不变」这个已点名的失败模式（`plan-tech-stack-migration.md:789`）。建议落在 `tests/e2e/`。
- **`READER3_ALLOW_PICKLE=1` 日落**：012 需要把「停止 pkl 写入的版本号」「删除 runtime fallback 的版本号」写进代码/CHANGELOG，并回填本 ADR 的 Decision Outcome（当前只知道是「一个大版本之后」，未钉死具体号）。
- **进入条件**（不是本 ADR 定义，只引用）：Phase 2b 完成且 Track D 完成且标注 E2E 达到 soak 门槛，见 `plan-tech-stack-migration.md` §7、§9.1。

## Revisit When

- **012 分支开工**：Status 由 Proposed 转 Accepted，Current compliance 从 None 开始按实际进度更新。
- **停写 pickle 的那个大版本发布后**：本文「双写期」相关的 Negative（磁盘翻倍、两条读路径并存）过期，需要更新 Consequences 或另开 ADR 记录「pkl 写路径已移除」。
- **`--migrate` 或提交协议在真实迁移中暴露出指纹会变的具体场景**（例如空白折叠算法后续改动影响 `chapter.text`）：需要重新评估 A1 指纹口径是否还能兑现「纯格式转换不变指纹」这条承诺。

## Related

- ADR-0001（文件系统即数据库；目录布局不变，本 ADR 只覆盖目录内主文件格式，ADR-0001 已在其 Related/Neutral 提前指向本文）
- ADR-0003（`book_uuid` 是否并入 `manifest.json` 留给 012 决定；`ai_meta.json` 不在本次格式变更范围内）
- ADR-0005（同批相邻决定，见 `docs/adr/README.md` 索引）
- ADR-0007（两文件提交协议——写入顺序、崩溃安全、`os.replace` 换目录的两条缺口——与 `missing`/`corrupt`/`valid` 三态读取判定的唯一定义处；本文只引用，不重复）
- ADR-0012（同批相邻决定，见 `docs/adr/README.md` 索引）
- `CLAUDE.md:24,75,86`（架构图与 Data Flow 里的 `book.pkl`，待 012 落地后改写为新格式）、`:250`（`012-storage-format` 里程碑行）
- 原定义处：`docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:304-326`（Phase 3 格式决定与双写/日落/`--migrate` 硬约束的 bullet list）、`:381`（`--migrate` 不得改变 `book_fingerprint` 的规则）、`:728-729`（附录 A A2：pickle 回退默认关闭与退出机制）——2026-08-26 已改为指向本 ADR 的链接（Phase 3 只留任务清单，`:381` 与 A2 各留一行）。
