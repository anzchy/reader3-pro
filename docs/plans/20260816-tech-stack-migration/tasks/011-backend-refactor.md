# 011-backend-refactor —— 任务

- **对应阶段**: Phase 2a（结构，不改行为）＋ Phase 2b（性能）＝ 里程碑 M2
- **进入条件**: Phase 1a（008）已合入且三条 lane 常绿；Phase 1b（009）两道门已达成 —— **G2 冻结不是本分支的进入条件，是本分支的约束**，见 §0.3
- **退出条件**: 见 §8。一句话版：`server.py` 拆到每个 router < 500 行、两处 `load_book_cached` 并成一个 `book_store`、缓存能感知盘上的变化、notes 不再静默丢写，且这一切由 008 的测试与 009 的 `baseline_1b` 原样证明「行为没变」
- **下游**: Phase 2b 阻塞 Phase 3（012）；`book_store` 的粒度接口决定 012 的 `manifest.json` 能否落脚（附录 A 的 A5）
- **跨计划**: notes 乐观并发的服务端形状是[前端计划](../../20260817-frontend-ui-refactor/README.md) DEG-S5 的前置契约 —— 验收用例 `tests/e2e/acceptance_2a/test_deg_s5_write_conflict.py` **已经写好并 skip 在那里**，本分支的任务是让它能解禁，不是重写它
- **节奏**: 按 WI 顺序推进，行为变更各自独立 PR（§7）；结构变更可以合成一个 PR，但 §1 的守卫必须先于任何一行路由搬家落地

> **引用规则**：用**符号名**定位，不写代码行号。

---

## 0. 开工前必须先接受的三件事

### 0.1 计划里的 Phase 2a 已经做掉三分之一了，别重做

`plan-tech-stack-migration.md` 的 Phase 2a 清单写于 2026-08-16。此后 007/008/009 三个分支顺手做掉了其中三项，还让第四项的**前提本身**失效了。2026-09-07 逐条实测：

| 计划清单项 | 实测状态 |
|---|---|
| `web/server.py` 拆成六个 router | ❌ 未动。且它已经从计划写的「~2,400 行」长到 **2,905 行** —— 拖着不拆，分母还在涨。**2026-09-19 复核：`master` 上仍是 2,905，这 12 天没再涨**；本分支上的 2,979 全部来自 `1be7387`（WI-3 合缓存），不是自然增生。**但拆法本身出了新问题**：六组里 `ai` 那一组过不了 < 500 行的门槛，且搬家解决不了，见 §5 |
| 新建 `book_store.py`，合并「三处重复的 `_Reader3Unpickler` 与 `lru_cache` loader」 | ⚠️ **前提已变**，见 §0.2 |
| 缓存失效：三处 `lru_cache` 的 key 都不含 mtime | ❌ 未做 |
| chromadb + sentence-transformers 移入 optional `[semantic]` | ❌ 未做，两者都还在 `pyproject.toml` 的主 `dependencies` 里 |
| `ai/config.py` 设置写入改原子替换 | ✅ **已做**（`tempfile.mkstemp` + `os.replace`，且在注释里写明了为什么偏离仓库既有的 `f"{path}.tmp"` 写法：这个文件装明文 API key，临时文件的权限位得由 `mkstemp` 保证） |
| notes 乐观并发控制（revision/ETag，冲突返 409） | ❌ 未做。`notes_service.py` 里没有 revision、没有 ETag，服务端没有任何一处返 409 |
| `max_retries` 定性（删掉还是接通，二选一） | ❌ 未做，且**这道选择题已经被 ADR-0011 替我们做完了**，见 §6 |
| 路由启发式：CJK ~1.5 字符/token、Anthropic 默认窗口降到 200k | ✅ **已做**（`ai/routing.py` 的 `_CJK_CHARS_PER_TOKEN` / `_OTHER_CHARS_PER_TOKEN`，以及 Anthropic 分支上那句 "Default DOWN" 注释） |
| 修订 `CLAUDE.md` § Constitution Principles | ⚠️ **半条**（2026-09-19 订正，原记 ✅ —— **那一格是错的**）。已做：七条摘要成为唯一权威（`CLAUDE.md:116-119`），"测试可选"条款全文搜索 0 命中、确已删除。**没做的恰恰是计划点名要改的那句**：`CLAUDE.md:122` 今天仍逐字写着「YAGNI - no abstractions beyond FastAPI/BeautifulSoup」。这一格现在直接压在 §5 那道选择题上 |

~~**九项里三项已完成、一项前提失效、五项待做。**~~ **2026-09-19 重数（WI-1 落账时）：九项里四项已完成、一项半条、四项待做。**

与 2026-09-07 那次相比的三处变动，都由本次复核给出：
- `book_store` ＋ 缓存失效两项从「前提已变 / 未做」变成 **✅ 已兑付**（`1be7387`，WI-3）——它们在原表里是两行，合并成一项计。
- CLAUDE.md 那项从 ✅ 降为 **⚠️ 半条**，理由见上表。
- 新增一条原表没有的发现：`ai` 组过不了 < 500 行门槛（§5）。**它不是清单漂移，是门槛与实现对不上**，性质不同，所以单列。

WI-1 的第一件事就是把这张表回写进计划，否则下一个读计划的人（可能是三周后的你）会照着一份 30% 过期的清单开工。**本次回写已完成，见下面 §2 的完成记录。**

### 0.2 `book_store.py` 要合并的是**缓存**，不是 unpickler

计划原文说要合并「`server.py` / `search_service.py` / `vector_search.py` **三处**重复的 `_Reader3Unpickler` 与 `lru_cache` loader」。这句话今天三个部分全不成立：

- **`_Reader3Unpickler` 已经不存在了。** 受限 unpickler 早已集中成 `safe_pickle.Reader3Unpickler`，三份重复在 007/008 期间就收敛掉了。这一半的工作**已经做完**。
- **`vector_search.py` 根本没有 loader。** 它直接调 `safe_pickle.load_book_file`，没有 `lru_cache`。它不在合并范围内。
- **真正重复的是两个同名不同签名的函数。** `server.load_book_cached(book_id)` 与 `search_service.load_book_cached(book_id, books_dir)` 各自挂着 `lru_cache(maxsize=10)`，**同一本书在进程里躺两份**，且两份的失效时机互不相干 —— 这正是计划担心的「漂移风险」，只是位置和它写的不一样。

第三处相关缓存是 `search_service.load_book_index`（`maxsize=4`），它建在 `search_service.load_book_cached` 之上，并把 `case_sensitive` 编进了 key。所以 C1 说的「有效容量折半到 2 本」仍然成立，附录 B 的 C1 那段不用改。

**同名是个陷阱，不只是重复。** 测试里 `monkeypatch.setattr(server, "load_book_cached", …)` 出现 6 次 —— 它只换掉 `server` 那一份，`search_service` 那一份纹丝不动。合并的收益里有一条计划没写出来：**让「打了桩」和「真的被打了桩」重新变成同一件事。**

### 0.3 G2 冻结在头顶上，但这个分支一步都不用踩它

`suite_hash` 已冻结在 `2747100dadf6`，覆盖 8 条路径（唯一定义处：[`soak-log.md`](./soak-log.md)）。覆盖面里动一个字节，soak 台账全部作废、从零重数 ——**代价是至少 5 个工作日**。

已核实：**本任务书里没有任何一项需要改那 8 条路径中的任何一条。**

- 拆 router、抽 `book_store`、改 `pyproject.toml` 的依赖分组 → 全在 `src/`，不在覆盖面里。
- notes 乐观并发的验收用例在 `tests/e2e/acceptance_2a/`，**不在**覆盖面里（覆盖面只含 `tests/e2e/baseline_1b`）。解禁 DEG-S5 不重置计数。
- `tests/conftest.py` **在**覆盖面里。本分支若要往它加东西（§1 的 WI-0b 有这个诱惑），必须先算清楚：那一改就是从零重数。**WI-0b 因此明确落在 `tests/unit/`，不落在 `tests/conftest.py`。**

> **`baseline_1b` 本身就是「行为不变」的证明。** 拆 router 期间它必须一次不红地一直绿着 —— 它既是护栏，又在给 Phase 3 数门槛。这两件事在本分支里是同一件事。

---

## 0.4 这个分支不是一次 `/tdd-guardian:workflow` 能跑完的

| WI | 走 workflow | 为什么 |
|---|:--:|---|
| **WI-0** 打桩接缝守卫 | ✅ | 产物就是测试，且能先红后绿（在拆分前它是绿的 —— 这正是要抢在拆分前落地的理由） |
| WI-1 对齐权威文件 | ❌ | 纯文档。没有东西可以 gate |
| WI-2 修 `bench.py` | ❌ | 产物是性能工具本身，验收是「跑得起来且数出来的数不为零」，不是断言 |
| **WI-3** `book_store.py` | ✅ | 纯重构 + 缓存失效语义，红→绿边界干净 |
| WI-4 拆 router | ⚠️ **半条** | 搬家动作本身没有新测试可写，护栏是既有的 008 契约 + 009 `baseline_1b`。但 `routes.snapshot` 的集合比对会在搬错时当场红 —— 那是既有测试，不是新写的 |
| **WI-5** notes 乐观并发 | ✅ | 行为变更，409 语义可断言，且 E2E 验收用例已备好 |
| WI-6 `max_retries` | ❌ | 一行接线 + 一条配置消费断言。委托 workflow 的开销大于工作本身 |
| WI-7 语义依赖可选化 | ❌ | 产物是打包元数据，验收是「不装 `[semantic]` 时 import 不炸、装了则语义搜索可用」 |
| **WI-8/9** C1 / C2 | ✅ | C2 明确要求差分测试；C1 的 key 语义可断言 |

**别把 ❌ 的项塞进 workflow。**（同 007 §0 的老教训：`tdd-planner` 会尽职地为「改 `pyproject.toml` 的依赖分组」设计测试矩阵，然后被 `design-tests` 的 wiring-only 门槛挡下来，白跑两个 stage。）

---

## 1. WI-0 —— 打桩接缝守卫（**拆分的先决条件，不是配套**）

### 问题

测试套里有 **70 处 `monkeypatch.setattr(server, …)`，横跨 12 个测试文件、20 个属性名**：

```
9 retrieve_passages      7 book_token_stats     7 _call_provider
6 load_book_cached       5 book_uuid_resolver   5 BOOKS_DIR
3 search_library         3 load_ai_settings     3 build_multi_chapter_context
3 build_full_book_context  3 BookVectorIndex    2 search_book
2 ai_queue               2 _egress_post_stream  2 AI_WORKER_STOP_TIMEOUT_S
1 save_ai_settings       1 get_provider_base_url  1 choose_routing
1 _http_get_json         1 _get_provider_runtime
```

拆 router 会把这些名字搬到别的模块。**大声失败的那一半不可怕**：名字彻底消失时 `monkeypatch.setattr` 默认 `raising=True`，当场抛 `AttributeError`。

**可怕的是安静失败的那一半。** 拆分时为了不让全线飘红，几乎一定会在 `server.py` 留 re-export（`from .routers.ai import _call_provider`），或者让 router 反向 `from ..server import _call_provider` 在导入期绑定。这两种写法下：

> `server._call_provider` 这个名字**还在**，`monkeypatch.setattr` **不报错**，但真正执行的 router 模块持有的是它自己那份绑定 —— 桩打在了 A，代码走的是 B。测试继续绿，拦截的东西是零。

这是「patch where it's used, not where it's defined」的经典陷阱，代价在这个仓库里格外具体：`tests/contract/test_provider_test_route.py` 写着 `server._call_provider` 是**本进程通往 LLM 的唯一出口**。一次静默失效 = 一套以「零真实 egress」为存在理由的测试，拿着 `config/ai_settings.json` 里的**明文 API key** 去打真实 provider。

### 做法（两层，都在 `tests/unit/`）

**WI-0a 名字归属断言。** 建一张显式注册表：`(被打桩的名字, 拆分后应当拥有它的模块)`。对每一条断言

```
getattr(server, name) is getattr(owner_module, name)
```

拆分前它天然全绿（owner 就是 `server` 自己）；一旦某个名字变成 `server` 上的过期别名，它当场红。**这就是要抢在搬家之前落地的全部理由 —— 事后补它，它只会记录既成事实。**

**WI-0b 出口兜底。** 现在「本模块任何一条用例都不许开 TCP 连接」这道闸只在 `tests/unit/test_server_egress_gate.py` **模块作用域**里生效。把等价的守卫扩到 `tests/unit/` 与 `tests/contract/` 全域（`autouse` fixture，落在这两个目录各自的 `conftest.py`，**不动仓库根的 `tests/conftest.py`** —— 理由见 §0.3）。

WI-0b 是 layout-independent 的：无论名字搬到哪，一次真实出网都会变成一声巨响而不是一次成功的请求。**WI-0a 是braces，WI-0b 是belt。egress 这道闸值得两条都系上。**

### 验收
- 注册表覆盖上面 20 个名字中**每一个**（不是抽样）。
- 故意把某个名字改成过期别名 → WI-0a 红。这条要真的演一遍，不能只是相信它会红。
- `tests/unit/` 与 `tests/contract/` 全域内，任何一次真实 TCP 出网 → 红。
- `tests/conftest.py` 的字节数不变（`git diff --stat` 里不出现它）。

---

## 2. WI-1 —— 对齐权威文件（纯文档，先做，因为它决定后面做什么）

1. 把 §0.1 那张实测表回写进 `plan-tech-stack-migration.md` 的 Phase 2a 清单：三项标 ✅ 并注明兑付分支，`book_store` 那项按 §0.2 重写描述。
2. 附录 A 的 A5「为什么是三处不是四处」需要重写 —— 今天的答案是「**两处同名 loader ＋ 一处建在其上的 index 缓存**」，`vector_search.py` 不在内。
3. 附录 B 的 C1 **不用改**（`maxsize=4` ＋ `case_sensitive` 入 key ⇒ 有效 2 本，已复核仍然成立）。
4. `.claude/skills/plan-and-branch-map/SKILL.md` 的里程碑表：`011` 从 `Allocated` 改成 `Tasks drafted`。
5. [进度盘](../../20260824-frontend-backend-plan-progress.md) 的 M2 行同步。

> **顺带记一笔已知漂移**：`soak-log.md` 表头那行「门槛进度：N / ≥10 次」是**手工维护**的，`test_soak_log_contract.py` 里没有任何一条测试拿它跟表体行数对账。它会悄悄对不上。修法（给表头加一条与行数对账的契约测试）不在本分支范围内，记在这里免得下次靠记忆发现。

### 完成记录（2026-09-19）✅ —— 四条兑付，一条被约束挡住

| # | 状态 | 兑付内容 |
|---|---|---|
| 1 | ✅ | Phase 2a 清单回写进 `plan-tech-stack-migration.md`：`book_store` ＋ 缓存失效两项勾掉并注明 `1be7387`；`ai/config.py` 原子写注明 `0e103ab`（008 期间）；路由启发式注明 `105bbbb`（008 期间）。`book_store` 那项按 §0.2 整条重写 |
| 2 | ✅ | 附录 A 的 A5 重写为「两处同名 loader ＋ 一处建在其上的 index 缓存」，`vector_search.py` 明确移出合并范围，并把 `monkeypatch` 那条收益补进去 |
| 3 | ✅（无需改动） | 附录 B 的 C1 复核：`load_book_index` 的 `maxsize=4` ＋ `case_sensitive` 入 key ⇒ 有效容量 2 本，仍然成立。**未改一字** |
| 4 | ⛔ **未做，被约束挡住** | `.claude/skills/plan-and-branch-map/SKILL.md` 的里程碑表。本次会话明确禁止改 `.claude/` 下的任何配置，所以没动。**而且这一格已经比任务书写的更陈旧**：任务书要求「`Allocated` → `Tasks drafted`」，但 SKILL.md 今天写的已经是 `Tasks drafted`，而本分支已有 7 个 commit ——按 SKILL.md 自己定义的状态语义，它现在该是 **🚧 In progress**。**留给下一个有权改 `.claude/` 的人，一次改到位** |
| 5 | ✅ | [进度盘](../../20260824-frontend-backend-plan-progress.md) 的 011 行同步 |

**本次复核推翻了 §0.1 实测表的两格**（两格都是本文件自己写的，不是别人的）：
- `book_store` 与缓存失效：⚠️/❌ → ✅（`1be7387` 已兑付）
- `CLAUDE.md § Constitution Principles`：✅ → ⚠️ 半条（`CLAUDE.md:122` 那句禁令一字未动）

**并带出一条原表没有的发现**：六组 router 里 `ai` 组过不了 < 500 行门槛，且按职责搬家解决不了（算术见 §5）。
**这一条会改变 WI-4 的做法，所以必须在 WI-4 开工前裁定，不能边做边定。**

---

## 3. WI-2 —— 修 `scripts/bench.py`（先修仪器，再动被测物）

`scripts/bench.py` 的 `_install_unpickle_counters()` 现在**跑不起来**：

```
AttributeError: module 'reader3_app.web.server' has no attribute '_Reader3Unpickler'
```

它的 docstring 还写着「给三处 loader 各自的 `_Reader3Unpickler`」—— 那个符号在 §0.2 说的收敛里没了，插桩点跟着一起没了。

好消息是**其余部分都在**：20 本合成书库、TTFB 曲线的 `DEFAULT_SIZES = (1, 5, 10, 20)`、大部头覆盖 C2 的 300 万字符路径 —— 计划要求的「Phase 1a 须先记录基准」那套 fixture 早就建好了。坏的只有反序列化计数这一个探针。

**为什么它必须排在 WI-3 前面**：`book_store` 要把两份缓存并成一份、并给 key 加上 mtime。「反序列化次数」正是判断这次合并是变快了还是变慢了的**唯一**直接指标 —— 合并本身减少了重复读，加 mtime 校验又给每次命中加了一次 `stat`。没有这个探针，Phase 2b 的验收「相对基准可量化改善」就没有基准。

### 验收
- `python scripts/bench.py`（默认 20 本）跑通，反序列化计数**不为零**（为零说明探针挂在了不会被走到的地方，是另一种坏）。
- 把结果作为 Phase 2b 的 before 基准存档。

### 完成记录（2026-09-07）✅

产出：[`bench/011-wi2-before.json`](../bench/011-wi2-before.json) ＋ [`bench/README.md`](../bench/README.md)（repeat=5，六项指标全产出，退出码 0）。

**坏的不止一处。** 本节写的 `AttributeError` 是真的，但它只是两处独立故障里的一处：

1. 探针挂在已消失的 `mod._Reader3Unpickler` 上 → 指标 4/5 不产出。**改法**：三处 loader 今天各自 `from .safe_pickle import load_book_file`，即各有一个自己的模块级绑定，包那一份即可，per-loader 归属原样保住，用的正是 WI-0 那道守卫盯着的同一条接缝。
2. **五个 worker 的 `TestClient` 全是裸构造。** 服务端那道 Host 白名单只放行 127.0.0.1 / localhost / [::1]，而 `TestClient` 默认发 `testserver` → 每个请求 400 `Invalid host header`。指标 2 会当场炸（它自己查状态码），指标 1/3/4/5/6 **安静地量到 400 响应**。

所以本节那句「好消息是**其余部分都在**」是错的：`bench.py` 从来没有真正跑通过，`011-wi2-before.json` 是零号基准，不是「又一份」。第 2 条的教训固化成了 `expect_ok()`——非 2xx 当场炸，不让仪器坏掉的表现形式是「所有数都很漂亮地等于 0」。

**新增一个跨重构可比的口径 `safe_pickle_total`**（包 `safe_pickle.safe_load`，不问调用者是谁）。理由：WI-3 合并之后 `web.server` 那一格会掉下去，但那只说明绑定换了地方，不说明少读了一次盘。今天 100 = 40 + 60，两口径相等 ⇒ 没有第四个绕开这三个绑定的读盘点。

基线已经把 WI-3 要修的东西显出来了 —— 第 03 步「同一本书换一处 loader 再 unpickle 一遍」，第 04 步「maxsize=10 撑不住 20 本，19 本重读」。逐步明细见 `bench/README.md`。

---

## 4. WI-3 —— `book_store.py`（Phase 2a 的主体）

### 4.1 合并两份缓存

把 `server.load_book_cached(book_id)` 与 `search_service.load_book_cached(book_id, books_dir)` 并成 `book_store` 里的一个。签名以 `search_service` 那份为准（显式 `books_dir` 比隐式读模块级 `BOOKS_DIR` 更符合「Explicit Over Implicit」），`server` 侧提供参数已绑定的薄封装以免 11 处调用点全改签名。

**11 处调用点**（`server.py` 内，已核实）：8 处直接调用，3 处经 `run_in_threadpool` 传函数对象。后三处不能靠 `grep 'load_book_cached('` 找到 —— 谁要重新数一遍，记得数的是符号出现而不是调用括号。

### 4.2 缓存失效（计划里「此前无家可归」的那一项）

三处 `lru_cache` 的 key 都不含 mtime/指纹：重新处理一本同名书之后，服务端会继续供旧 `Book` 直到重启。Phase 0 的 P0-1 只保住了用户标注不被 `rmtree` 删掉，**没有**让缓存知道盘上的东西变了。

key 里纳入 `book.pkl` 的 `st_mtime_ns` + `st_size`（不做内容 hash —— 每次命中读一遍全文来算 hash，代价压过收益）。

> **注意这里没有 E2E 护栏。** `tests/e2e/conftest.py` 的 session 级 fixture 在**起服务之前**就把四本书全处理完了，此后不再动 `book.pkl`。也就是说冻结的 `baseline_1b` 里**没有任何一条用例**会走到「盘上变了、缓存该失效」这条路径。这一项的证明只能靠新写的单测，`baseline_1b` 全绿在这里**不构成证据**。

### 4.3 粒度接口（给 012 留的接缝）

按附录 A 的 A5 暴露 `load_book_metadata(book_id)` 与全量 `load_book(book_id)` 两级。**本分支只建接缝、不改存储** —— `load_book_metadata` 在 011 里可以就是「读全量再取字段」，性能收益要等 012 的 `manifest.json`。建它的意义是让 012 不必同时改存储格式**和**所有调用点。

### 验收
- 008 全部契约测试 + 009 `baseline_1b` 原样全绿（行为不变的证明）。
- 新单测：同一本书在两个模块取到**同一个对象**（`is` 断言，不是 `==`）。
- 新单测：改动 `book.pkl` 的 mtime 后，下一次读拿到新内容。
- `bench.py` 的反序列化计数相对 WI-2 基准**不上升**。

---

## 5. WI-4 —— 拆 router（**按关切拆，不按行号拆**）

计划定的六组不变：`library` / `reader` / `notes` / `search` / `ai` / `settings`。

### 一个具体的坑：AI 那一段不是一整块

`/api/ai/*` 的路由从 `/api/ai/conversations/{book_uuid}` 开始，但在它**上面**紧挨着的是 `/api/settings/*` 十条、`/api/ollama/*` 两条，再往上是一批共用的 pydantic 模型（`AIMessage`、`AISummaryRequest` …）。**按行号连片切一刀，会把 settings、ollama、AI 三件事切进同一个 `routers/ai.py`，等于把 god-module 原样下沉一层。**

- `/api/settings/*` → `routers/settings.py`
- `/api/ollama/*` → 归 `settings`（它服务的是设置页的 provider 探测），**在 PR 描述里写明这个归属判断**，因为它两边都说得通。
- 共用 pydantic 模型 → `web/schemas.py`，不塞进任何一个 router。

### 硬约束

- **ADR-0011：Phase 2 不得改变任何响应形状。** 路由的增删改必须同 commit 更新 `tests/contract/routes.snapshot`；本分支的正确 diff 是**这个文件一行都不动**。它一动就说明搬家搬丢了或前缀写错了。
- **WI-0 必须已经落地。** 见 §1。这不是建议顺序，是先决条件。
- 每个 router < 500 行（§7 的门槛）。`server.py` 在 `master` 上 2,905 行、本分支 2,979 行（2026-09-19 实测），六组均分是 484 —— 没有余量，`schemas.py` 和 `book_store.py` 分走的那部分是达标的关键。
- ⚠️ **但均分是错的模型。实测下来，`ai` 组不是「余量紧」，是根本过不去。** 见下。

### 2026-09-19 实测：`ai` 组过不了 < 500 行，且搬家解决不了

先给数，再给选项。以下都是当天对 `web/server.py`（2,979 行）做 AST 走查得到的，不是估算：

| 组 | 路由数 | 路由正文合计 |
|---|---|---|
| `ai`（`/api/ai/*` 八条） | 8 | **708** |
| `settings`（含 `/api/ollama/*` 两条与 `/api/settings/providers/*` 五条） | — | 255 |
| `notes` | — | 243 |
| `search` | — | 190 |
| `reader` | — | 138 |
| `library` | — | 134 |

**五组绰绰有余，只有 `ai` 越线，而且差得不是一点。** 越线的原因集中在一个函数上：

```
POST /api/ai/question/{book_uuid}   server.py:2454-2886   433 行   ← 一个函数
  顶层语句 9 条，其余全是嵌套闭包：
    event_gen          174    SSE 生成器
    _do                139
    worker_ollama       55    ollama 的后台线程体
    worker_non_stream   18
    push                 2
    _release_lease       2
```

它**独占**的模块级 helper：`_stop_stream_worker` 60 行（`server.py:1661`，全仓库调用点只有 `:2662` 与 `:2670`，两处都在这个函数体内）。
`_save_conversation_snapshot` 47 行（调用点 `:2700`、`:2847`，也只在它里面，但按职责归 `conversations`）。

> **决定性的那道算术**：`433 ＋ 60 ＝ 493`。**即使把这条路由单独放一个文件、别的什么都不放**，再加 import 与
> `APIRouter` 声明就越过 500。**没有任何一种「按职责搬家」能让它达标。** 差额在 10–30 行量级 —— 这个事实本身也值得记一笔：
> 门槛不是被甩开，是被擦着蹭过，说明 500 这个数在这个边界上是个任意值。

**三条候选路线**（2026-09-19 已向 Codex 求证，它的结论与代价评估记在括号里）：

- **A. `routers/ai/` 拆成子包**（`chat.py` / `conversations.py` / `summary.py` ＋ `rag.py`）。纯搬家，零行为变更，
  `baseline_1b` 风险最低。**代价：`chat.py` 仍然约 510–520 行，A 单独用并不达标**——Codex 推荐 A 时写的是
  「让 `chat.py` 严格低于 500」，那一步在上面这道算术下做不到，**这是它给的方案里唯一一处与实测冲突的地方**。
  A 要成立，必须搭配下面 C 的一条具名豁免。
- **B. 先把 SSE 机器抽成 service 层**（`ai/streaming.py`），让路由函数变薄，再做六组平拆。是唯一能靠**减少复杂度**
  而不是**切文件**达标的路线。代价：闭包捕获的是请求态，这等于在一张**不能廉价扩展的 e2e 网**下重新设计全程序
  最容易弄红的那个端点；且它正面顶上 `CLAUDE.md:122` 与 ADR-0008（见 §0.1 那一格）。Codex **明确拒绝**这条，
  理由是「把低风险搬迁升级为最高风险端点的重新设计」。
- **C. 给 `chat.py` 写一条具名豁免**（门槛改为「每个 router < 500 行，`chat.py` 例外，上限 N，理由：单个 SSE 端点 433 行」）。
  最便宜。代价：门槛开始迁就实现——**本仓库已经有好几笔欠账正是这么长出来的**。

### 裁定（2026-09-19）：走 A，配一条具名、可到期、机器执行的豁免

**采纳 A（`routers/ai/` 拆子包），并给 `chat.py` 一条豁免。** 三层理由：

1. **B 现在做是顺序错的。** 它要动的是全程序最容易把 `baseline_1b` 弄红的端点，而 e2e 网是冻结的、扩不起。
   更关键的是它正面顶上 `CLAUDE.md:122` 与 ADR-0008 —— 而那一条恰好是 §0.1 刚被降为「⚠️ 半条」的**未兑付项**。
   先改宪法再做重构，和为了做重构去改宪法，中间只隔一个顺序。**B 不是被否决，是被排到 2b 之后**，
   前置条件是 `CLAUDE.md:122` 那一格先独立结清。
2. **差额只有 10–30 行。** 493 ＋ 样板 vs 500。门槛不是被甩开，是被擦着蹭过 —— 这在报告「500 在这个边界上是个
   任意值」，不是在报告一个 god-module。为 10 行去重构全仓库最危险的端点，是让门槛驱动工程。
3. **豁免写成可证伪的，就不是钻空子。** 与本仓库那几笔「门槛迁就实现」的欠账的区别全在下面四条里。

#### 豁免条款（canonical，别处只许链接不许重述）

- **范围**：只对 `src/reader3_app/web/routers/ai/chat.py` **一个文件**。`routers/` 下其余每一个文件，
  含 `ai/__init__.py`，一律 < 500，**不设第二条例外**。
- ~~**上限 N = 560**~~ → **N = 550**（2026-09-19 回写）。原来源：不可搬走的正文实测 **493 行**
  （`api_ai_question` 433 ＋ 它独占的 `_stop_stream_worker` 60），余量 67 行留给 import、模块
  docstring、`APIRouter` 声明与路由装饰器。
  **回写记录**：`chat.py` 落地实测 **547 行**，67 行余量多估了 54。N 下调到 550 而不是钉死在 547，
  是因为这条豁免要咬的是**函数拆没拆**（到期条件），不是「谁多写了一行注释」；lint 仅发版触发，
  为一行注释在发版那天转红，代价和收益不成比例。`api_ai_question` 实测仍是 433 行，到期条件未触发。
  「只许下调不许上调」由 `tests/unit/test_router_size_gate.py` 末尾那条上界断言执行，且**每次下调后
  同步收紧**（已 560 → 550）——棘轮不跟着收，就不是棘轮。
- **到期条件（不是口头承诺，是检查器的一条断言）**：豁免的存在理由是「`chat.py` 里有一个 >400 行的单函数」。
  一旦 `api_ai_question` 被分解到最大函数 ≤400 行，**检查器必须转红并要求删掉这条豁免**。
  即：**这条豁免会自己到期，不需要谁记得回来收。**
- **机器执行是豁免成立的前提**：2026-09-19 实测，`.github/workflows/*.yml` 与 `scripts/*.py` 里
  **没有任何一处在检查这条 500 行门槛** —— 它从写下那天起就只是计划表里的一句散文。
  **一条没人测量的门槛，它的豁免也永远不会到期**，那才是真的钻空子。
  所以 WI-4 的第一步不是搬家，是 `scripts/check_router_size.py`：
  - 判据落在**每个声明了路由的模块**上，不落在包上 —— 这样「聚合入口只有几十行」自动不构成达标证据；
  - 今天对着 `server.py`（2,979 行，43 条路由）**必须是红的**，这是它的定向破坏证据，不是事后补的；
  - 它连豁免的到期条件一起断言（上一条）。

**代价照记，不粉饰**：`ai` 领域从此是一个目录而不是一个文件，计划 §6 写的「六组」在**实现文件**这一层变成七个上下；
433 行那个函数**一行没变**，复杂度没有下降，下降的只是单文件行数。这两句必须出现在 WI-4 的 PR 描述里。

#### 三件已经不是选项的事
1. **不得为了压线把代码倒进 `utils.py` 之类的筐。** 按职责拆是诚实工程，为压线而拆就是钻门禁空子。
2. **不得用「聚合入口只有几十行」充当达标证据。** 行数检查落在**每个实现文件**上，不落在 `__init__.py`。
3. **不得把「拆了文件」说成「降低了函数复杂度」。** 433 行那个函数在 A 和 C 下一行没变。

**搬家的最高风险不是行数，是 SSE 的运行时绑定**：停止信号、并发 lease、worker 引用的对象，在换了模块之后可能静默失效
——函数正文一字不动也可能坏。**廉价护栏已经存在，不用新写**：`tests/unit/test_ai_queue_lease.py` 的 Q1–Q6
（`:230`/`:277`/`:405`/`:431`/`:480`/`:569`）覆盖的正是「抛异常后下一个请求仍拿得到租约」「断连后 worker 先停租约后放」
「worker 停不下来时仍释放租约」「非 ollama 路径断连时 worker 真的被取消」。它在 unit lane 上、**不在冻结的 8 条路径里**，
每搬一步重跑一次即可。`/api/ai/*` 下**没有** stop 路由，停止走的是断连路径，Q3/Q6 正对这条。

### 归属：`POST /api/settings/providers/{name}/test` 留在 `settings`

判准是**这条接口承担的用户操作**，不是它调不调模型、也不是路径前缀 —— 它是设置页里「测一下我填的 key 对不对」，
属于配置流程。它与 `ai` 组共用 `_call_provider`（`server.py:1396`，调用点 `:1976` 在本路由内，`:2394`/`:2415` 在 summary，
`:2627`/`:2806`/`:2827` 在 question）——**共用底层调用不要求路由同组**。这条与上面 `/api/ollama/*` 归 `settings` 是同一条判准，
一并在 PR 描述里写明。

### 验收
- `routes.snapshot` 零 diff。**这个文件一动就说明搬丢了或前缀写错了。**
- 008 契约测试 + 009 `baseline_1b` 全绿。
- ~~`wc -l src/reader3_app/web/routers/*.py` 每个 < 500~~ —— **人肉 `wc -l` 不算兑付**。
  改为：`scripts/check_router_size.py` 在 CI 里绿，且它曾对着拆分前的 `server.py` 见过红。
  它同时执行上面那条豁免的**到期条件**。
  > ~~**接线时机是有意推后的，别当成漏了。**~~ —— **已兑付（`a61f6c7`，2026-09-19）。**
  > 脚本与它的 10 条单测先于搬家落地，接线推到拆分转绿的同一个 commit：CI 仅发版触发，
  > 早接上去等于让这期间每一次发版都因为一件正在做的事而失败。现已进
  > `.github/workflows/lint.yml` 的 `contracts` job，并用 `/usr/bin/python3` 裸跑验证过
  > 它仍是零依赖，那条 job「不装任何东西」的性质没丢。
- `tests/unit/test_ai_queue_lease.py` 的 Q1–Q6 在**每一步搬家之后**各跑一次，不是只在最后跑一次
  —— 它是 SSE 运行时绑定的护栏，而那是本 WI 唯一会静默坏掉的东西。

### 完成记录（2026-09-19）✅ —— 七条验收全兑付

七个 commit，一组一个，每步跑一次 contract ＋ unit ＋ Q1–Q6（P-3 缓解「分小步走」）：

| commit | 组 | 新文件（行） | `server.py` |
|---|---|---|---|
| `6afc3fb` | notes | `routers/notes.py` 263 | 2979 → 2760 |
| `e92cefe` | search | `routers/search.py` 221 | 2760 → 2574 |
| `2c109c6` | library | `routers/library.py` 333 | 2574 → 2278 |
| `a7d7a0c` | reader | `routers/reader.py` 126 | 2278 → 2178 |
| `1c7cb6a` | settings | `routers/settings.py` 348 | 2178 → 1871 |
| `bb86b0b` | 共用模型 | `web/schemas.py` 50 | 1871 → 1852 |
| `a61f6c7` | ai ＋ health ＋ 接线 | `routers/ai/{chat 547, conversations 236, summary 213, rag 37}`、`routers/health.py` 34 | 1852 → **942** |

43 条路由全部搬完，`routes.snapshot` 全程零 diff，冻结 8 路径全程零 diff。

**逐条对验收**：

| 验收项 | 状态 |
|---|---|
| `routes.snapshot` 零 diff | ✅ 七个 commit 全程未出现在 `git diff --stat` 里 |
| 008 契约测试全绿 | ✅ `tests/contract` 180 passed / 1 skipped |
| 009 `baseline_1b` 全绿 | ✅ **67 passed / 24 deselected, 56.14s**（`c0ec1cb`，见下） |
| `check_router_size.py` 在 CI 里绿 | ✅ `a61f6c7` 接进 `lint.yml` `contracts` job，12 个文件全 PASS |
| 它曾对着拆分前的 `server.py` 见过红 | ✅ 见上文「机器执行是豁免成立的前提」那条 |
| 豁免到期条件随脚本执行 | ✅ `min_function_lines=400`，`api_ai_question` 实测 433 |
| Q1–Q6 每步各跑一次 | ✅ 七步各一次，最后一次 6/6 绿 |

**`baseline_1b`（§8 门槛 4，2026-09-19 由维护者本人执行）**：

```
[soak] 67/91 tests collected (24 deselected) in 0.32s
[soak] summary: 67 passed, 24 deselected in 56.14s
[soak] verdict: green（可记账：是）
[soak] row: | 2026-09-19T04:11:13Z | c0ec1cb | green | 56.14 | 2747100dadf6 | chromium-1234 | darwin-25.3.0 | … |
[soak] dry run：未写台账（加 --append 才写）
```

三件事各自要点出来：

1. **`suite_hash` 仍是 `2747100dadf6`**，与 G2 冻结值逐字相等——WI-4 搬了 43 条路由、`src/` 动了
   16 个文件，冻结的 8 条路径**一个字节没碰**，soak 计数不受影响（§0.3 的承诺兑现）。
2. **未加 `--append`，没有写进 `soak-log.md`**，这是**对的**，不是漏了：门槛 4 的括号写明分支上的
   运行不进台账——台账数的是 `master` 上冻结覆盖面的稳定性，分支上跑它是当护栏不是攒次数。
3. 67 项对得上门槛 4 的「67 项全绿」，不是子集绿。

这次跑之前，e2e 网上一次见绿是 `6165e1b`（2026-09-06），距此 25 个 commit，中间 `src/` 改了
16 个文件 / +2769 / −2104。**contract lane 查的是路由存在性与响应形状，它不开浏览器**——模板挂载、
静态资源前缀、SSE 实际串流这三处正是换家之后最可能静默坏的地方，只有这一跑能证伪。

#### 这次搬家新开了一个门禁口子

`check_router_size.py` 量的是「`routers/` 下每个文件」∪「`web/` 下声明路由的模块」。
`server.py` 现在**一条路由都不声明**，于是掉出了这道闸的范围——它剩下的 942 行共享工具
不受 500 行上限约束。这不是 bug，是判据「落在声明了路由的模块上」的直接后果（那条判据
当初正是为了让「聚合入口只有几十行」不构成达标证据）；但它意味着 `server.py` 可以重新
长胖而没人报警。已同步写进 `routers/health.py` 的 docstring 与 `lint.yml` 的注释。
**要不要给 `web/*.py` 另立一条上限，留给 WI-8/Phase 2b 裁，本 WI 不顺手扩大范围。**

#### 11 条 B-ii 棘轮往松了走，逐名配了定向破坏

`ai` 组搬走之后，`server.py` 里读这 11 个名字的地方一处不剩，模块级解析点降为空集
（`load_book_cached` 是三项降两项）。空集会掩盖「这个名字已经没人用了」，所以逐名把
`_server.X` 换成导入期绑定跑一整条 unit lane，事后按字节还原并 `cmp` 校验（11/11 还原 OK）。
11 条**全部**红了，且红的不只是两道静态闸——每条都另有 1–14 条行为测试跟着红。
证据表落在 `tests/unit/test_server_patch_seam_ownership.py` 的棘轮表里（**不只在 commit message**），
`a61f6c7` 的 message 里有同一张表。与 WI-4 第五步的 `_http_get_json` 对照：那条破坏后**只**红
`a12`，没有行为测试跟上——它才是「只有静态闸护着」的那一类。

#### 裁定要求写进 PR 描述的两句代价，照记

1. `ai` 领域从此是一个目录而不是一个文件，§6 写的「六组」在**实现文件**这一层变成七个上下。
2. `api_ai_question` 那 **433 行一行没变**，复杂度没有下降，下降的只是单文件行数。

---

## 6. WI-5 / WI-6 —— 两项行为变更

### WI-5 notes 乐观并发

notes 是 load→modify→save 全覆盖，`os.replace` 只保证单次写入原子，**不防两个并发请求互相覆盖** —— 自托管单用户开两个标签页就能触发。加 revision（或 ETag），冲突时返 409 而不是静默丢写。

**验收用例已经写好了**：`tests/e2e/acceptance_2a/test_deg_s5_write_conflict.py` 里的 `test_deg_s5_concurrent_note_edit_shows_conflict_dialog_and_loses_nothing`，现在是 skip 状态。本 WI 的完成标志是**它能解禁并转绿**，不是重写它。前端侧的冲突 UI 是设计规格 §6.4 的 DEG-S5。

它在 `acceptance_2a/`，不在冻结覆盖面里 —— 解禁它不重置 soak 计数（§0.3）。

⚠️ **409 是新增的响应状态码。** ADR-0011 冻的是「响应形状」与「路由存在性」，`routes.snapshot` 只收 `METHOD path`，不收状态码，所以快照零 diff。但这仍然是一次对外可见的行为变更，**独立 PR，PR 描述里显式声明**。

### WI-6 `max_retries` —— 这道选择题已经不由我们做了

计划写的是「删掉它还是接通它，二选一」。**ADR-0011 已经把其中一个选项划掉了**：

> 冻结之下 Phase 2（011 拆 router）**不得改变任何响应形状**。

`max_retries` 会从 `GET /api/settings` 读回。删掉它 = 改响应形状 = 011 窗口内非法。于是只剩两条合法路径：

1. **接通它**（让 provider 真的消费这个重试次数）—— 响应形状不变，合法。
2. **整条推迟到解冻之后**（ADR-0011 随 014 合入解除）。

**推荐 1。** 理由：一个设置页能填、能存盘、能读回、前端还在渲染，但全链路无人消费的配置项，是比「多一个字段」更糟的东西 —— 它对用户撒谎。接通它是把谎话变成真话，而且不欠 ADR 任何东西。

独立 PR。验收：一条断言「provider 调用在失败后按 `max_retries` 重试」的单测（用 §1 WI-0b 的出网兜底保证它不真的打网络）。

---

## 7. WI-7 / WI-8 / WI-9 —— 收尾与 Phase 2b

**WI-7 语义依赖可选化。** `chromadb` 与 `sentence-transformers` 从主 `dependencies` 移进 `[project.optional-dependencies]` 的 `semantic` 组，与 README「语义依赖可选」的描述对齐。验收：不装 `[semantic]` 时 `import reader3_app` 与全部非语义路由正常，语义路由给出可读的降级提示而不是 `ImportError` 堆栈。

**WI-8（C1）跨库搜索缓存颠簸。** `load_book_index` 的 `maxsize=4` ＋ `case_sensitive` 入 key ⇒ 有效容量 2 本。换 weighted LRU，key 纳入 mtime/指纹（与 WI-3 的失效机制共用一套）。验收：`bench.py` 的全库搜索指标相对 WI-2 基准可量化改善。

**WI-9（C2）`_normalize_with_map` 换 `array('I')`。** 现在返回 `Tuple[str, List[int]]`，每字符一个 Python int —— 300 万字符约 >100 MB，换 `array('I')` 约 12 MB，且仍支持 `index_map[i]` 下标，**不改变** `highlight_ranges_for_chapter()` 的偏移语义。**必须做差分测试**：新旧实现对同一批语料逐字符比对 index_map（casefold 扩张与 combining mark 删除这两条路径是错误高发区，`epub_corpus.py` 里的 CJK 书是现成语料）。

**C5 明确不在 011 范围内。** 计划把它标为「落点待裁决」，理由是它严格依赖 Phase 3 的 `manifest.json`。放进 011 需要先造一个过渡版（单独缓存一份轻量书目 JSON），那是一份会在 012 里被删掉的代码。**裁决：推迟到 012，与 `manifest.json` 一起做。** 本条同时消解附录 B 文末 UNRESOLVED DECISIONS 里的这一项。

---

## 8. 退出门槛

| # | 门槛 | 复核方式 |
|---|---|---|
| 1 | 每个 `routers/*.py` < 500 行（唯一具名豁免 `ai/chat.py` ≤ 550，带到期条件） | `python3 scripts/check_router_size.py`（已接入 `lint.yml`）。**人肉 `wc -l` 不算兑付。** 注意范围：`server.py` 不再声明路由，已掉出这道闸——见 §5 完成记录「门禁口子」 |
| 2 | `tests/contract/routes.snapshot` **零 diff** | `git diff --stat` 里不出现它 |
| 3 | 008 三条 lane 全绿 | `/tdd-guardian:gate commit` |
| 4 | 009 `baseline_1b` 67 项全绿，`suite_hash` 仍是 `2747100dadf6` | `uv run python scripts/soak_run.py`（不加 `--append`，本分支上的运行**不进台账**） |
| 5 | WI-0a 注册表覆盖全部 20 个打桩名，且故意制造过期别名时**演示过它会红** | 见 §1 验收 |
| 6 | `tests/unit/` + `tests/contract/` 全域出网兜底生效 | 见 §1 验收 |
| 7 | `bench.py` 跑通，反序列化计数不为零，C1/C2 指标相对基准改善 | §3 存档的 before/after |
| 8 | DEG-S5 验收用例解禁并转绿 | `pytest tests/e2e/acceptance_2a -k deg_s5` |
| 9 | `tests/conftest.py` 未被修改 | `git diff --stat master..011-backend-refactor -- tests/conftest.py` 为空 |

> **门槛 4 的括号很重要。** 分支上的 soak 运行**不能**记进 `soak-log.md` —— 台账数的是 `master` 上冻结覆盖面的稳定性。分支上跑它是为了当护栏，不是为了攒次数。

---

## 9. 给 `/tdd-guardian:workflow` 的输入

只有四项是 test-first 形状（§0.4）：

| WI | 一句话工作项 | 必须存在的测试 |
|---|---|---|
| **WI-0** | 打桩接缝守卫（名字归属 + 出网兜底） | 归属注册表覆盖 20 个名字；过期别名场景转红；全域 TCP 出网转红 |
| **WI-3** | `book_store.py`：两份缓存合一 + mtime 入 key + 粒度接口 | 跨模块 `is` 同一对象；mtime 变化后读到新内容；`baseline_1b` 不红 |
| **WI-5** | notes 乐观并发，冲突返 409 | 并发写第二个请求得 409 且**两份内容都没丢**；DEG-S5 解禁 |
| **WI-9** | `_normalize_with_map` 换 `array('I')` | 新旧实现对 CJK / casefold / combining mark 三类语料的 index_map 逐字符差分 |

### 跑之前知道这两件事

1. **WI-0 必须第一个做完，而且要在任何一行路由搬家之前。** 它在拆分前是天然全绿的 —— 这看起来像「写了条没用的测试」，恰恰相反：它唯一的价值就是在**未来**某次搬家时变红。事后补写只能记录既成事实。
2. **`tests/conftest.py` 是雷区。** 它在 `suite_hash` 的 8 条覆盖路径里。`tdd-implementer` 想往 conftest 加 fixture 是本能反应，本分支必须拦住 —— 加在 `tests/unit/conftest.py` 或 `tests/contract/conftest.py`，代价是 0；加在根 conftest，代价是 soak 台账从零重数、Phase 3 至少推迟 5 个工作日。
