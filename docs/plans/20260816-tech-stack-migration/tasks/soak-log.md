# `baseline_1b` soak 台账

> **状态：建账完成，尚未开始计数。** 下表**一行都还没有**，这是正确状态——soak 计数从
> **G2 达成之日**开始（见 [`009-e2e-annotations.md`](./009-e2e-annotations.md) §8）。
> **首行落账之前，本文件不构成对 G2 的任何宣称。**
>
> 字段定义、清零规则、门槛语义的**唯一定义处**是迁移计划 §7，本文件不复述，只做指针与执行细节。

<!-- 数据行从 G2 达成当天开始追加，一行一次全量运行，缺一列该行不计数。
     位置有硬要求：**紧接分隔行下方，中间不留空行**。契约测试只解析文件里第一张表的
     连续块，一个空行就把后面的行踢出解析范围——`pre-freeze` 检查会对它视而不见并
     照常报绿，也就是「拿冻结前的绿充数」这条正好检查不到。
     test_no_ledger_row_strays_outside_the_table 就是拦这个的。 -->
| ts_utc | commit | result | duration_s | suite_hash | browser | os | log |
|---|---|---|---|---|---|---|---|

---

## `suite_hash` 的取法

```bash
# baseline_1b 组用例 + harness 配置 + fixtures 的内容哈希，前 12 位
{ git ls-files -s tests/e2e/baseline_1b tests/e2e/conftest.py tests/e2e/helpers.py \
    tests/e2e/test_harness_smoke.py tests/fixtures/epub_corpus.py tests/fixtures/epub_zip.py \
    tests/conftest.py \
  | git hash-object --stdin; } | cut -c1-12
```

当前 `suite_hash` 值：`777174826be2`（2026-09-03 实测输出，非誊抄）。

**这个值处于 pre-freeze，不是冻结值。** G2 尚未开始，baseline_1b 的 22 条用例也还没写完
（现在 `baseline_1b` 收集到 14 条：WI-3 的 harness 自测 9 条 ＋ WI-4 的创建路径 3 条 ＋ WI-5 的
笔记创建/编辑 2 条；`tests/e2e` 全量 21 条，差额是白名单里的 smoke 与 testid 唯一性），后面每落
一条用例它都会变。写在这里是免得后来者拿今天这个值当冻结值。

**取值前必须先 `git add`。** 上面这条命令读的是**索引**，不是工作区：新用例文件在 `git add`
之前对 `git ls-files -s` 根本不存在，改过的 `helpers.py` 也仍报旧内容。WI-4、Wave 0、WI-5 三次
都在这里先拿到过一个「没变」的旧值（本次为 `06114374b405` → `6672e32e6687`）。

值的变更史（每次改都要写清作废原因，不要只覆盖数字）：

- `777174826be2` ← §0 第六条纪律落地：`helpers.py` 新增 `assert_bystanders_unchanged`（旁观条守恒从「各用例就地写一行 assert」抽成共用函数），W-7 改为调用它。**用例条数没变**（仍是 14 条），断言语义也没变（整字典等值原样），变的是它住在哪里——抽出来是为了让 `tests/unit/test_e2e_bystander_discipline.py` 有一个 grep 得到的名字可查。同 Wave 0，纯搬家一样让哈希作废。
- `6672e32e6687` ← Wave 1（WI-5）：新增 `baseline_1b/test_write_note_editor.py`（W-4 / W-7 两条，12 → 14 条），同时改 `helpers.py`——`assert_roundtrip` 加 `expected_count`（默认 1，三个既有调用点行为不变）、新增 `wait_for_note_text` 与 `_pick_target`。**两个被 hash 覆盖的文件同时改**，既有条数变了、既有文件内容也变了，两个理由各自都足以让旧值作废。（同批还改了 `scripts/lint_e2e_selectors.py`，但它**不在** hash 命令的文件清单内，不构成本次作废的原因——它的影响是扫描面 14 → 20 处，记在下面一段。）
- `06114374b405` ← Wave 0 的 helper 上收：四个私有 helper 从两个 baseline 模块提进 `helpers.py`，**三个被 hash 覆盖的文件同时改**。用例条数没变（前后都是 19 条、断言集合逐条比对无增删改），变的只是它们住在哪个文件里——`suite_hash` 覆盖的是文件内容而不是用例条数，所以纯搬家一样让它作废。
- `f56131cfe4ef` ← WI-4 的 `test_write_create_annotations.py` 进索引（3 条用例）。
- `70ee84519f02` ← WI-1–WI-3 一批提交（commit `0e411f8`）。

### 与 `suite_hash` 无关但会影响「同一套用例」判断的一次改动

2026-09-03（WI-5）修了 `scripts/lint_e2e_selectors.py` 的一个盲区：正则要求引号紧跟在 `(` 后，
于是**所有 f-string 形态的 locator 实参一处都没被扫到**；而 ADR-0014 的复合选择器要插一个
运行期 id，天然全是 f-string。实测旧正则会对一个同时含 `.some-class` 与 `[data-modal="…"]`
的探针文件报「0 处违规」。补上前缀后扫描面 **14 → 20 处**，全仓仍 0 违规。

记在这里的理由：这个脚本不在 `suite_hash` 的覆盖面内，所以它变了 hash 不变——但「这套用例
被什么强度的门禁把过关」确实变了。G2 冻结后若有人回头比对，光看 hash 会以为门禁没动过。

`70ee84519f02` 取代 `235802f4647d` 的原因**正是下面那条索引态的坑本身**：算它的时候
`tests/e2e/baseline_1b/` 与 `tests/e2e/helpers.py` 还未进索引，`git ls-files -s` 对它们
静默产出空，于是那个值算的是一个不含这两者的 suite。WI-1–WI-3 一批提交后重算得到
`70ee84519f02`。**这不是命令的缺陷被触发，是它被如实执行了**——留着这段是因为它是这条坑
唯一一次有据可查的实例。

**2026-09-02 补两个路径（WI-3 落地时由守卫逼出来的，两个都不是「顺手加宽」）：**

- `tests/conftest.py` —— **没有任何 import 语句指向它**，是 pytest 按目录层级自动加载的祖先
  conftest。它里面那个 `pytest_configure` 钩子校验 `-m` 表达式里的 marker，直接决定
  `-m baseline_1b` 能不能选中东西：改它就是改 suite。纯 AST 的 import 追踪永远看不见这一支，
  所以守卫里它是**按目录结构**入闭包的，不是追出来的。
- `tests/fixtures/epub_zip.py` —— `epub_corpus.py` 的每个 builder 都经它写盘，四本语料的字节
  全由它决定。它此前逃过守卫是因为守卫的模块解析序写反了（详见
  `tests/unit/test_soak_log_contract.py` 的 `_resolve_module` docstring）：裸名 `conftest`
  被解析成 `tests/conftest.py` 而不是 pytest 实际导入的 `tests/e2e/conftest.py`，于是后者整条
  语料依赖链都没进闭包。**结论碰巧对、理由是假的**，比直接报错更难发现。

### 与迁移计划 §7 命令的三处差异（改的是命令，不是规则）

§7 明确授权「若目录名不同，改的是这条命令，不是规则」。落地差异：

- `tests/e2e/baseline-1b` → `tests/e2e/baseline_1b`（WI-1 的实际目录名用下划线）；
- `tests/e2e/fixtures` → 本仓库没有这个目录，共享语料在 `tests/fixtures/`，按 §7 的裁定纳入 `epub_corpus.py`；
- `playwright.config.*` → **本仓库从来没有这个文件**（harness 配置在 `tests/e2e/conftest.py` 里），
  所以这一项被去掉，不是漏抄。

`git ls-files` 对未进索引的路径静默产出空，因此命令在任何时点都可跑、值合法；
文件一提交就自动进哈希，不需要再改命令。

### 取哈希前必须先确认工作树干净（运行器的前置检查）

`git ls-files -s` 读的是 **git 索引**，不是工作树。2026-09-02 实测：

| 状态 | 值 |
|---|---|
| 基线 | `990bfff749ef` |
| 改了工作树、未 `git add` | `990bfff749ef` ← 内容变了，哈希没变 |
| `git add` 之后 | `0b1448c13b23` |
| 还原后 | `990bfff749ef` |

**后果**：soak 期间有人改了 `baseline_1b` 的一条断言却没 `git add` 就跑全量，`suite_hash` 不变，
那次运行会被记成「同一套东西」的第 N 次绿——正是清零规则要堵的假绿路径，而命令的实现方式在这里漏了一档。

所以**取哈希前工作树对这几个路径必须是干净的**，且这应当是 `scripts/soak_run.py` 的前置检查，
不是靠人记得：

```bash
git status --porcelain -- \
  tests/e2e/baseline_1b tests/e2e/conftest.py tests/e2e/helpers.py \
  tests/e2e/test_harness_smoke.py tests/fixtures/epub_corpus.py
# 非空 ⇒ 拒绝落账：记的会是索引里的旧内容，不是刚跑过的那份
```

---

## 三类清零触发器（指针，规则正文在迁移计划 §7）

- `suite_hash` 变了 ⇒ 清零 —— [§7 台账字段（canonical）＋ 什么会让计数作废](../plan-tech-stack-migration.md#台账字段canonical-什么会让计数作废)
- `browser` 或 `os` 变了 ⇒ 清零 —— [§7 台账字段（canonical）＋ 什么会让计数作废](../plan-tech-stack-migration.md#台账字段canonical-什么会让计数作废)
- 任意一次 `red` ⇒ 清零 —— [§7 台账字段（canonical）＋ 什么会让计数作废](../plan-tech-stack-migration.md#台账字段canonical-什么会让计数作废)

生产代码变（`commit` 列变）**不**清零；其余四个尚未激活的 acceptance 组怎么改也**不**清零——
它们不在上面那条命令的覆盖路径里。

### 冻结前的行怎么标

`suite_hash` 与本文表头记录的当前值不同的数据行，**必须在该行里显式写上 `pre-freeze`**，
它不计入 ≥10 次的分母。没有第二种标法：`result` 列只有 `green` / `red`，
拿一次冻结前的绿去凑数在台账上是无痕的，靠的就是这个标记。

**复核方式**：把上面那条命令复制出来跑一遍，输出应等于表头记的值。这是 review 动作，由人执行——
自动化用例**不**断言「表头的值 == 现在算出来的值」，那会让每一次合法的套件改动都红一条无关的用例，
而冻结的语义本来就是「这个值不随之后的改动走」。台账形状的机器可解析性由
`tests/unit/test_soak_log_contract.py` 守。

---

## 两条纳入/排除口径及其代价

### 1. `tests/fixtures/epub_corpus.py` —— **纳入**，代价是「纯单测改动也会清零」

它是 `build_epub2` / `build_epub3` / `build_cjk` 的所在地，`baseline_1b` 每一条用例读的都是它造出来的书。
不纳入，就等于允许「不动用例、只动语料」地重塑十次运行的含义。

**代价是实的，不藏**：这个文件今天有三个消费方，其中两个不在 e2e 一侧——

- `tests/unit/test_fixture_epub_corpus.py`（unit lane）
- `scripts/bench.py`（基准脚本）
- `tests/e2e/conftest.py`（e2e lane，即冻结的那一侧）

因此**一次纯单测目的的构造器改动也会把 soak 计数清零**。比如第十次运行前一天，有人为了
`tests/unit/test_fixture_epub_corpus.py` 的一条断言给 `build_epub2` 加个 `lang=` 参数——计数归零，
而归零的理由与 e2e 毫无关系。这是「宁可多清零，不可假计数」的一侧误差，接受；
写在这里是为了归零那天有人知道为什么。

### 2. `pyproject.toml` —— **排除**，代价是「marker 定义变更不触发清零」

它会因依赖升级等与被测行为无关的原因变动，纳入等于每次 bump 清零。

代价是：`pyproject.toml` 里的组 marker 定义（`baseline_1b` 等五个）如果被改动——比如某个 marker
被悄悄改名，导致一批用例不再被选中——`suite_hash` 不会变。**补偿手段**：每次运行必须把
`--collect-only` 的条数写进 `log` 列指向的产物里，并与 `scripts/lint_e2e_groups.py` 的
`EXPECTED_BASELINE_ITEMS` 对齐。分母不对，那次运行不算绿（判据见
[`009-e2e-annotations.md`](./009-e2e-annotations.md) §8 G2）。
