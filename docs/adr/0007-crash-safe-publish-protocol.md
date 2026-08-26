# ADR-0007: 书目录的崩溃安全发布协议——staging → 读回校验 → 逐路径原子换，marker 最后换；读取判三态，`corrupt` 大声失败不回退

| 字段 | 值 |
|---|---|
| Status | Accepted |
| Decision date | 2026-08-17（`plan-tech-stack-migration.md` 「两文件提交协议（canonical，全仓库唯一定义处）」段落首次出现于 commit `5d43c80`） |
| Recorded date | 2026-08-25 |
| Record type | Prospective |
| Original rationale known | Yes |
| Confidence | High |
| Current compliance | Partial（`book.pkl`＋`book.epub`＋`images/` 三产物的 staging／校验／原子换／rename-only 回滚已在 007 落地；`manifest.json`＋`chapters.jsonl` 两文件提交与三态读取状态机是 012 的范围，尚未实现） |
| Evidence | `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:328-343`（两文件提交协议八步）、`:345-362`（两条协议缺口）、`:364-379`（三态读取＋pickle 日落分界）；`src/reader3_app/reader3.py:178-191`（模块级 docstring，一书两类文件／staging／marker-last 的问题陈述）、`:448-514`（`_commit_staged_artifacts`，marker-last 与逆序 undo 的实现）、`:435-445`（`_restore`，rename 非 copy）、`:673-680`（`process_epub` 里 `book.pkl` 在 staging 内也最后写）；commit `7a807c9`（P0-1 修复，`src/reader3_app/reader3.py` +405 行，新增 `tests/unit/test_process_epub_commit.py` 646 行 ／ `tests/unit/test_process_epub_staging.py` 245 行 ／ `tests/unit/test_save_to_pickle_and_main.py` 229 行，共 10 个文件、2011 行新增）；commit `5d43c80`（staging 清理误删同名真书库的修复，`_is_own_staging_name`，新增 `tests/unit/test_process_epub_staging.py` 43 行）；`docs/plans/20260816-tech-stack-migration/tasks/007-hygiene-and-contracts.md:83-90`（P0-1 的症状与「顺序照 Phase 3」的引用） |
| Confirmation | `uv run pytest tests/unit/test_process_epub_commit.py tests/unit/test_process_epub_staging.py`——`test_book_pkl_is_the_last_path_committed`（`test_process_epub_commit.py:119`）、`test_crash_before_marker_keeps_old_pkl_loadable_and_rerun_converges`（`:269`）、`test_user_data_and_marker_survive_every_replace_crash_point`（`:300`）、`test_a_failed_commit_is_the_identity_even_when_an_artifact_was_absent`（`:359`）、`test_an_unrepairable_commit_failure_is_reported_and_does_not_mask_its_cause`（`:406`）、`test_reprocess_leaves_all_four_user_paths_bytewise_and_inode_identical`（`test_process_epub_staging.py:101`）。三态读取（`missing`/`corrupt`/`valid`）与 manifest+jsonl 提交协议目前**没有**对应测试——它们是 012 待实现的范围，见下方 Migration Strategy |

## Context and Problem Statement

一本书的产物要从内存态发布进 `books/{book_id}_data/`，而这个目录还同时住着用户不可再生的数据（`notes.json`、`ai_meta.json`、`chroma_db/`）。P0-1 暴露的原始实现在写任何东西之前对整个目录 `shutil.rmtree()`，进程在写一半时被杀，或磁盘写满，都会把用户数据和半成品产物混在一起，且没有任何手段区分「这本书没问题」和「这本书写坏了」。012 计划把 `book.pkl` 换成 `manifest.json` + `chapters.jsonl` 两个文件，进一步引入了 pickle 时代不存在的失败态：**manifest 已落盘、chapters 只写了一半**——manifest 本身格式完好，任何「文件在不在／JSON 解不解得开」的检查都会误判它健康。不定协议，重写整本书这条路径会在每一次崩溃、每一次磁盘写满时把用户数据置于风险中。

`reader3.py:178-191` 的模块级 docstring 把这个问题陈述钉在代码里：目录里的文件分「可再生」（`book.pkl`／`book.epub`／`images/`，由重新处理 EPUB 重建）与「用户拥有」（`notes.json`／`ai_meta.json`／`ai_conversations/`／`chroma_db/`，重新处理必须是它们的恒等映射）两类；因此一切生成产物先在**同级 staging 目录**里构建、经读回校验，再逐路径换入，`book.pkl` 作为每个读取端判定「这本书存不存在」的 commit marker，写入 staging 时最后落盘、换入时也最后换——一次中途死掉的运行，留下的只能是旧书或新书，绝不是两者的混合，也绝不会碰到用户拥有的那一半字节。

## Decision Drivers

- 目录内产物（`book.pkl`／`manifest.json`+`chapters.jsonl`／`book.epub`／`images/`）与用户产物（`notes.json`／`ai_meta.json`／`chroma_db/`）共享同一目录，协议必须只触碰前者，绝不枚举或改写后者。
- 进程可能在任意字节被杀（`SIGKILL`、断电），协议必须保证崩溃后目录处于「旧的完整」或「新的完整」两态之一，不允许第三态。
- `os.replace` 只在**同一文件系统**内对普通文件原子；跨设备会退化成拷贝，协议因此要求 staging 与目标同父目录。
- 读取端必须能区分「这本书还没迁移」（正常）与「这本书迁移坏了」（异常），否则用户会在毫无提示的情况下拿到截断内容。
- 单人维护、无运维团队盯盘：一旦出现协议本身之外的不一致（磁盘损坏、外部程序改文件），必须让人看见，而不是被静默兜底吸收。

## Considered Options

1. **staging 目录 + 读回校验 + 逐路径原子换，marker 最后换**（选定）——所有新产物先在同级 `.staging-{pid}` 目录里生成并 fsync，读回校验通过后，被替换的旧产物先 rename 进 staging（记 undo），新产物 rename 进位，最后才换 marker 文件（`book.pkl`，未来是 `manifest.json`）；marker 换成功之前任何异常都按相反顺序把已换的产物 rename 回去。代价：staging 目录在提交窗口内让该书占用双倍磁盘。
2. **直接原地写 + 写完再校验**——为什么不：进程在覆盖到一半时被杀，目录里留下的是新旧字节交错的半成品，且没有任何标记表明这一状态，读取端和下一次写入都拿不到「回滚」的机会，只能继续读到损坏数据。
3. **写临时文件后 copy 覆盖到位**——为什么不：`shutil.copy2` 不是原子操作，`copy` 在磁盘写满时可能中途失败并留下截断的目标文件；本协议的回滚同样禁止用 copy 顶替 rename——`git show 7a807c9` 的提交信息记录了原实现里 `shutil.copy2` 被 `try/except Exception` 包着只打警告，会发布一本没有 `book.epub` 的书，这正是「copy 非原子」在生产路径上真实炸过的例子。

## Decision Outcome

**两文件提交协议（`manifest.json` + `chapters.jsonl`，012 待落地，八步全部要走且顺序不可换）：**

1. 写 `chapters.jsonl.tmp`（与目标同目录，保证 `os.replace` 原子）
2. `flush()` + `os.fsync(f.fileno())`——数据落盘，不只是落 page cache
3. 边写边记每章 `offset_bytes`／`length_bytes`／内容 hash；写完再记全文件 `size_bytes` 与 `sha256`
4. 写 `manifest.json.tmp`，把第 3 步的数字全部嵌入
5. `flush()` + `fsync()` manifest.tmp
6. **在任何 `os.replace` 之前**做一次全量回读校验：按 manifest 里的 offset 逐章 seek `chapters.jsonl.tmp`，每章 JSON 解得开、`id`/`order` 对得上、hash 相符；校验失败就删两个 tmp 文件退出，目录里旧状态一字节不动
7. `os.replace("chapters.jsonl.tmp", "chapters.jsonl")` → `os.fsync(dirfd)`
8. `os.replace("manifest.json.tmp", "manifest.json")` → `os.fsync(dirfd)`——**manifest 是 commit marker，必须最后一个换**

顺序的全部意义在第 7、8 步：chapters 先就位、manifest 后就位，「manifest 指向半写文件」在任何崩溃点上都不可能出现；反过来的残留是良性的——只有 chapters 没有 manifest，读取状态机判 `missing`，走旧格式，孤儿 tmp 文件下次运行覆盖即可。

**三产物场景的两条协议缺口（P0-1 在 007 撞出来，已落地于 `reader3.py:448-514`）：** 上面八步是按「一个数据文件 + 一个 marker」写的，但 P0-1 真正要原子换掉的是**三件产物**（`book.pkl` + `book.epub` + `images/`），012 之后仍是三件（`manifest.json` + `chapters.jsonl` + `images/`）。这两条同样适用：

- **缺口 1（目录产物）：** `os.replace` 覆盖已存在的普通文件是原子的，但目标是**非空目录**时直接 `OSError: ENOTEMPTY`。`images/` 是目录，唯一可行的补法是**先把旧目录 rename 到一边，再把新目录 rename 进来**，旧目录的落脚点必须与 `output_dir` 同文件系统（放在 staging 内即可），否则 rename 退化成跨设备拷贝。
- **缺口 2（marker 之外的一致性）：** marker 之外只有一件产物时，「marker 最后换」等价于「marker 在时其余都在」；三件产物时它只挡住一个方向，挡不住**新 `book.epub` + 新 `images/` 挨着旧 marker**——marker 尚未翻，读取侧判为一致，实际拿到的是旧结构配新资源。协议必须补上失败路径的对称要求：**换 marker 之前的任何一步失败，都要把已经换进去的产物按相反顺序退回原样。**

落地形态（`_commit_staged_artifacts`，49 条测试覆盖，含三轮故障注入）：逐件把 live 产物 rename 进 staging（同时记 undo 记录；产物原本不存在时记 `(None, live)`——漏了这条就只会「恢复存在过的」而不会「移除新加的」）→ 新 `book.epub`、新 `images/` rename 就位 → `fsync(dirfd)` → **最后**换 `book.pkl`（marker）→ `fsync(dirfd)`；marker 换成功之前的任何异常（含 `KeyboardInterrupt`，捕 `BaseException`）都倒序走 undo；undo 本身失败只打 warning 到 stderr 并继续抛原异常——此时目录确实可能不一致，必须让人看见。配套两条测试性质，Phase 3／012 重跑时照抄：**回滚必须是 rename 不是 copy**（快照记 `inode` 与 `mtime_ns`，拷回一份字节相同的文件判 fail）；**「保住用户数据」不许退化成「什么都没改」**（同时断言用户子树逐字节不变 **且** 新增文件集合恰好等于该次重新生成的那几件产物）。`--migrate`（存量迁移）不适用本节——它只新增 manifest+chapters，不替换任何既有产物，走八步原文即可。

**读取状态机（三态，禁止二态）：** `storage_format(book_id)` 不能只回答「新格式还是旧格式」，因为那把「没迁移」和「迁移坏了」归成同一件事：

| 状态 | 判定 | 处置 |
|---|---|---|
| `missing` | `manifest.json` 不存在 | 读 `book.pkl`。双写期与未迁移存量书的**正常**状态，不告警 |
| `corrupt` | manifest 存在，但 JSON 解不开／格式版本不认识／`sha256` 或 `size_bytes` 与 `chapters.jsonl` 对不上 | **大声失败**：抛错、写日志、UI 出 DEG-S1–DEG-S4 横幅。**不静默回退 pkl** |
| `valid` | manifest 存在且自洽 | 读新格式 |

`corrupt` 不回退，是因为上面的提交协议已经排掉了「写坏」这条路径——协议走完还 corrupt，意味着磁盘损坏、外部程序改文件、或协议本身有 bug，这三种都需要人看见；静默回退 pkl 只会把它们藏到 pkl 也被删掉的那一天。这条同时划清了 pickle 日落的两个时间窗：**双写期**（移除 pkl 写入路径之前）里 pkl 是与新格式同期产出的对等产物，不是遗留数据，`missing` 走 pkl 属正常流程，不需要环境变量；**停写 pkl 之后**，目录里还剩的 pkl 才是真正的遗留数据，`missing` 走 pkl 才需要 `READER3_ALLOW_PICKLE=1` 显式开启并每次启动告警。

**明确不做：** 不引入校验和以外的完整性机制（签名、多副本）；不允许任何路径把 `corrupt` 兜底为「当作 `missing` 处理」；协议不覆盖跨文件系统的 `books/` 部署（那退化为拷贝语义，见 Negative）。

## Consequences

### Positive
- 协议排掉了「manifest 指向半写文件」这一类失败态，让 `corrupt` 状态成为一个真正意义上的信号（磁盘/外部/协议 bug），而不是「正常写入过程中的噪音」。
- rename-only 的回滚可用 inode／mtime_ns 断言机器验证，不依赖人工判断「内容看起来对不对」。
- 用户产物（`notes.json`／`ai_meta.json`／`chroma_db/`）从未被协议触碰，重新处理一本书不再是数据丢失事件。

### Negative
- 提交窗口内同一目录承受**双倍磁盘峰值**（旧产物 + staging 中的新产物同时存在），书越大、图片越多，峰值越明显。
- 协议依赖**同一文件系统**上 `os.replace`/rename 的原子性；`books/` 若被挂到网络盘或跨设备符号链接，rename 退化成拷贝，协议的核心保证不再成立——这是本协议**明确不覆盖**的场景，不是遗漏。
- `corrupt` 大声失败意味着一本书写坏后用户会看到明确错误（DEG-S1–DEG-S4 横幅），而不是被静默跳过或退回旧版本——这是有意选择的行为，不是需要修的 bug（对应 AGENTS.md 里异常分档「不可恢复的错误必须让人看见」的同一原则）。
- 每新增一类需要崩溃安全发布的产物（未来若再拆分文件），都要重新走一遍「缺口 1／缺口 2」的分析，协议本身不会自动推广到新形状的产物集合。

### Neutral
- `--migrate`（存量迁移命令）不受本协议的三产物缺口约束——它只新增 `manifest.json`+`chapters.jsonl`，不替换任何既有产物，因此走两文件提交的八步原文即可，不需要 rename-aside/undo 那一层。
- 协议本身不判定「什么样的内容算校验通过」（例如 chapter 顺序是否合理、spine 是否为空）——那属于各产物自身的校验器（`_validate_staged_artifacts`，`reader3.py:369-426`），本 ADR 只约束落盘顺序与失败时的回滚方式。

## Migration Strategy

**现状（Full 的部分）：** `book.pkl`＋`book.epub`＋`images/` 三产物的 staging／读回校验／逐路径原子换／marker-last／rename-only 回滚已在 007（commit `7a807c9`、`5d43c80`）落地，`reader3.py:448-514` 是唯一实现，49 条测试（含三轮故障注入：`os.replace` × 四种目录形态、`os.fsync`、seeded replace）覆盖。

**缺口（012 要补的部分）：** `manifest.json` + `chapters.jsonl` 两文件提交（八步协议）、`storage_format()` 三态判定函数、`book_store.py` 的格式无感封装、`READER3_ALLOW_PICKLE` 环境变量与停写 pkl 的时间窗切换，目前均未实现——代码里没有 `manifest.json`／`book_store.py` 的任何引用。012 落地时的棘轮是**崩溃注入测试**：在提交协议第 7 步之后、第 8 步之前中断，重启后该书仍能正常打开（状态判为 `missing`，走 pkl），且下一次迁移能干净地重跑；`--migrate` 需另一条测试证明 `notes.json`/`ai_meta.json`/`chroma_db/` 三者字节不变且 `book_fingerprint(book_id)` 不变。012 合入后本 ADR 的 Current compliance 应更新为 Full，或被一份专门记录 manifest+jsonl 格式决定的新 ADR supersede。

## Revisit When

- 012（存储格式迁移分支）合入：核对 `manifest.json`+`chapters.jsonl` 提交协议与三态读取是否按本文所写的八步/三态实现，更新 Current compliance。
- `books/` 目录需要支持跨卷或网络盘部署：本协议对 rename 原子性的依赖需要重新设计（例如改用两阶段提交 + 显式 fsync 屏障，或放弃跨卷部署这一需求）。

## Related

- ADR-0001（文件系统即数据库——本协议是「文件系统即数据库」模型下写入侧的一致性保证）
- ADR-0009（`manifest.json` + `chapters.jsonl` 格式本身、双写与日落——本协议写入侧的两文件提交在 012 服务于该格式）；`corrupt` 大声失败对应 AGENTS.md「异常处理规则（三档）」里「不可恢复错误必须可见」一档，那不是 ADR
- ADR-0012（`safe_pickle.py` 的受限反序列化，是本协议读取侧对 `book.pkl` 的配套：协议保证磁盘上的字节不是半写的，`safe_pickle` 保证半写之外的「格式错误但语法合法」的流也不会被当作可信代码执行）
- 本文取代的原定义处：`docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:328-343`（两文件提交协议八步）、`:345-362`（两条协议缺口）、`:364-379`（三态读取＋pickle 日落分界）——2026-08-26 已替换为指向本 ADR 的一行链接（标题保留以保住锚点），§4 回滚条目与附录 A 的 A2 条款改为引用本 ADR
