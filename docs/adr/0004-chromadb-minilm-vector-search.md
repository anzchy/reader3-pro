# ADR-0004: 语义检索固定为嵌入式 ChromaDB + `paraphrase-multilingual-MiniLM-L12-v2`，一书一库

| 字段 | 值 |
|---|---|
| Status | Accepted |
| Decision date | 2025-12-18（`git log --format='%h %ad %s' --date=short --diff-filter=A -- vector_search.py` → commit `edb9f4a`） |
| Recorded date | 2026-08-25 |
| Record type | Retrospective |
| Original rationale known | Partial |
| Confidence | Medium |
| Current compliance | Partial |
| Evidence | `src/reader3_app/vector_search.py:13`（`MODEL_NAME`）、`:21-30`（`_require_semantic_deps` 懒加载 + 报错文案）、`:55`（`self.chroma_path` 挂在 `book_dir` 下，一书一库）、`:65`（`READER3_EMBED_MODEL` 环境变量覆盖）、`:71`（`create_collection` 未显式传 `hnsw:space`）、`:94`（`_chunk_text(chunk_size=1000, overlap=120)`）、`:191`（`similarity = max(0.0, min(1.0, 1.0 - float(dist)))`）；`pyproject.toml:9,15`（chromadb / sentence-transformers 仍在主 `dependencies`）；`specs/_archive/001-search-features/research.md:15-22,35,43-54,65-68,284-296,405`（原始选型研究）；`docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md:289,541,623,645,657`；`docs/plans/20260816-tech-stack-migration/baseline-performance-008.md:311`；`docs/models-and-caches.md`；`docs/ai-providers-and-privacy.md`；`tests/unit/test_safe_book_folder.py:242`；`tests/unit/test_safe_pickle.py:99-107,293` |
| Confirmation | `tests/unit/test_safe_book_folder.py::test_t5_book_vector_index_rejects_at_construction`（`BookVectorIndex` 构造期路径校验）；`tests/unit/test_safe_pickle.py::test_call_sites_import_safe_pickle_and_define_no_unpickler`（`vector_search.py` 在安全反序列化站点清单里）。**模型/向量库选型本身、`1-L2` 换算是否正确、检索质量**：none（人工）——plan:541 已记录为待补的检索质量测试，本文写作时尚未落地 |

## Context and Problem Statement

**Observed State**：`BookVectorIndex`（`src/reader3_app/vector_search.py`）为每本书在 `{book}_data/chroma_db/` 下起一个嵌入式 Chroma `PersistentClient`（`:55`），懒加载 `chromadb` 与 `sentence-transformers`（`:21-30`，缺依赖抛 `RuntimeError`，文案是 `uv add chromadb sentence-transformers`），embedding 模型固定为 `paraphrase-multilingual-MiniLM-L12-v2`（`:13`），可用 `READER3_EMBED_MODEL` 覆盖（`:65`）。切块 1000 字/120 重叠（`:94`）。查询时把 Chroma 返回的 `distance` 按 `1 - dist` clamp 到 `[0,1]` 当相似度（`:191`），但 `create_collection`（`:71`）没有显式传 `hnsw:space`，即用的是 chromadb 当前版本的默认距离度量。

**Original Rationale**（`specs/_archive/001-search-features/research.md`，2025-12-17，选型落地前一天）：选 ChromaDB 是因为「Zero Infrastructure: Pure Python, no external services (aligns with self-hosted requirement)」「Filesystem Integration: Persistent file-based storage matches `{bookname}_data/` pattern」，一书一库是为了「No cross-contamination between books」；选 MiniLM 多语言版是因为「50+ including English and Chinese」，同时否决了 `all-MiniLM-L6-v2`（English-only）与 `mpnet-base-v2`（768 维、慢一倍）；同一份文档否决了 FAISS（无持久层）、Qdrant Local（要 Docker/binary）、sqlite-vec（当时"newer/less tested"）、Milvus Lite（仍要独立进程）。这份文档同时写下了 `1 - distance` 的设计假设，明确写的是**余弦距离**（"Cosine distance ∈ [0, 2]"）。**但**切块参数（1000/120）为什么取这两个数字，文档未给出依据——这部分 Original rationale 是 `Unknown`，也是本文把该字段定为 `Partial` 而非 `Yes` 的原因。

**Current Assessment**：选型本身（嵌入式、零基础设施、多语言）今天仍然成立，`specs/_archive/` 里否决 FAISS/Qdrant/Milvus 的理由没有过时。但"余弦距离"这条假设已经和实现脱节——`create_collection` 未锁定 `hnsw:space`（`:71`），plan:541 已把它记为已知缺陷；这不是新发现，是 2026-08-16 复核时被指出、此后一直挂着没修。另外，`index_meta.json` 会记录建索引时用的 `model_name`（`:149,164,173`），但代码里没有任何一处把它和当前配置的 `MODEL_NAME` / `READER3_EMBED_MODEL` 做比对（`is_indexed()` 只查 `status`/`chunk_count`，`:86`）——如果有人在两次索引之间改了 `READER3_EMBED_MODEL` 又没有强制重建，查询会静默用新模型的 embedding 去查旧模型建的向量，不会报错也不会降级提示。这条是本文写作时新核实到的，原始设计文档没有提及。

原始选型对比的模型参数（`research.md:47-54`）：

| 模型 | 维度 | 语言覆盖 | 结果 |
|---|---|---|---|
| `paraphrase-multilingual-MiniLM-L12-v2`（选定） | 384 | 50+，含中英文 | F1 0.85（多语言检索） |
| `all-MiniLM-L6-v2` | 384 | 仅英文 | 否决：不满足中文需求 |
| `paraphrase-multilingual-mpnet-base-v2` | 768 | 50+ | 否决：慢一倍，"overkill for <100 books" |

## Decision Drivers

- 自托管单用户、不引入外部服务/进程的约束（研究文档的 "Zero Infrastructure" 驱动）
- 需要中英文（及其他语种）语义检索，排除英文单语模型
- 文件系统即数据库的宪法原则——索引必须能作为 `{book}_data/` 下的一个子目录随书增删，不能是外置服务
- 换模型或换向量库＝全量重建索引＋检索质量对等验证，成本随书库增长（plan:657）
- ML 依赖的包体是文档化过的成本（venv 实测 ~1.1GB，torch 单项 368MB，plan:645），推动把它移出必需依赖

## Considered Options

1. **ChromaDB `PersistentClient` + `paraphrase-multilingual-MiniLM-L12-v2`（选定）**——嵌入式进程内向量库，384 维，一书一库，无需外部服务或网络。
2. **FAISS / Qdrant Local / sqlite-vec / Milvus Lite（研究阶段即否决，research.md:65-68）**——为什么不：FAISS 无持久层要自己序列化；Qdrant Local 要 Docker/二进制；sqlite-vec 当时（2025-12）"newer/less tested"；Milvus Lite 仍要独立进程——都比嵌入式 Chroma 重。
3. **迁 TS 后换 LanceDB / sqlite-vec（现在，仅作为假设性对比，plan:623）**——为什么不：这是「若后端换语言栈」这一非当前选项下的推演，plan §10.1 已判定后端不迁 TS，因此这条路径不成立；即便成立，Chroma JS SDK 只是 HTTP client，等于额外多背一个外置 server 的运维成本。
4. **换用云端 Embedding API（如 OpenAI/其他，未被 research.md 提及，原始理由 Unknown）**——为什么不（今天的评估，非原始理由）：与选型驱动之一「Zero Infrastructure / 自托管」直接冲突；`docs/ai-providers-and-privacy.md` 描述的现状是 RAG 查询时只把 top-k 摘录发给云端 provider，若改成云端做 embedding，等于把**全书正文**在建索引时发给第三方，隐私面积远大于现状——但该文档本身没有写出一条名为"本地优先"的原则，这是本文对它的推断，不是它的原文。

## Decision Outcome

语义检索保持嵌入式 ChromaDB（`PersistentClient`，一本书一个 `chroma_db/` 目录）+ `paraphrase-multilingual-MiniLM-L12-v2`，不更换向量库、不更换默认嵌入模型（`READER3_EMBED_MODEL` 允许单机覆盖，但不改默认值）。011 起把 `chromadb`、`sentence-transformers` 从 `pyproject.toml` 的必需 `dependencies` 移入 `[project.optional-dependencies] semantic`，未装该组时语义检索不可用、关键词检索不受影响。**明确不做**：不修复 `1 - distance` 相似度换算与实际距离度量不符这条已知缺陷（留给未来一次专门的检索质量工作，见 Revisit When）；不为"语义依赖缺失"新增或复用某个具体 `DEG-S` 编号——现有 `DEG-S1`–`DEG-S5`（`docs/plans/20260817-frontend-ui-refactor/spec-frontend-design.md` §6.4）没有一个是为"依赖未安装"定义的，最接近的 `DEG-S2` 语义是"索引指纹过期"，不是"包没装"，这个映射问题本 ADR 不裁定。

## Consequences

### Positive
- 零外部服务/进程，索引随书增删，符合文件系统即数据库原则。
- 50+ 语言含中文，满足本项目双语（甚至多语）书籍的检索需求，且这条判断有原始对比数据支撑（research.md 的模型对比表）。

### Negative
- **已知缺陷未处置**：`1 - dist` clamp 的设计假设是余弦距离，但 `create_collection`（`vector_search.py:71`）没有锁定 `hnsw:space`；plan:541 已记录、未修，也没有检索质量回归测试固化现状。
- 首次使用要下载一次性 ~420MB 模型（research.md:48），叠加 chromadb 本身，是 venv 体积 ~1.1GB 的主要来源之一（plan:645）；语义检索路径的实际冷启动耗时目前**没有基准数据**——`baseline-performance-008.md:311` 明确把它排除在六项基准之外，只给出「成本在几十秒量级」的定性描述。
- 换模型或换向量库＝全量重建索引＋需要一次检索质量对等验证，成本随书库规模线性增长，这也是 plan §11 把"更换嵌入模型或向量库"列为明确不做的直接原因（plan:657）。

### Neutral
- 今天 `chromadb`、`sentence-transformers` 仍在 `pyproject.toml` 主 `dependencies`（`:9,15`），尚未移入可选组；`_require_semantic_deps` 的报错文案（`vector_search.py:27`）仍写的是 `uv add chromadb sentence-transformers`，011 落地后这条文案也要跟着改。
- 切块参数（1000 字/120 重叠）没有可查的原始依据，属于"能查到选型理由、查不到调参理由"的中间态。

## Migration Strategy

现状与目标的差：`pyproject.toml` 尚未拆出 `[project.optional-dependencies] semantic`（目标见 plan:289），因此语义检索依赖今天仍会随 `uv sync` 默认安装，"可选"只是文档意图，不是包管理器的强制状态。谁在哪个分支补：`011-backend-refactor`（截至本文写作，`docs/plans/20260816-tech-stack-migration/tasks/011-backend-refactor.md` 尚不存在，任务清单未展开）。棘轮：待 011 任务文件落地时定义（例如一条断言 `uv sync --no-extra semantic` 后关键词检索仍可用、语义检索报出面向用户的降级提示而非裸 `RuntimeError` 堆栈的测试）；011 同时需要决定"依赖缺失"用哪个 `DEG-S` 编号或是否新增编号，这一决定本 ADR 不预判。

## Revisit When

- `1 - distance` 相似度换算与实际距离度量不符这条缺陷被实际修复时——修复本身要求全量重建索引，届时应一并检查是否需要新开一份 ADR 记录换算方式的变更。
- 后端语言栈脱离 Python（当前 plan §10.1 判定不做，一旦推翻则本 ADR 的向量库/嵌入模型选型需要整体重新评估）。
- `paraphrase-multilingual-MiniLM-L12-v2` 被上游标记弃用或长期无更新。

## Related

- ADR-0001、ADR-0008（截至本文写作，`docs/adr/` 目录下尚未出现这两个文件，无法核实其内容与本文的具体关联；引用保留给首批 0001–0013 的编号占位）。
- `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md` §11「更换嵌入模型或向量库」一条、§8 风险表「Chroma 相似度换算假设」一行、§10.1 表「语义嵌入 / 向量库」两行——原定义处保留一行指向本 ADR 的链接，具体章节见该文件本次配套编辑。
