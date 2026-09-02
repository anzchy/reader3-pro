"""`soak-log.md` 表头的**台账契约**（009 WI-2）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` 的 `## WI-2:` 一节，四条 unit 用例。

**为什么给一份 Markdown 写单测。** 因为这里被断的不是文风，是两条**可判定的集合关系**：
`suite_hash` 的覆盖面必须 (a) 罩住冻结套件真正 import 的每一个文件，(b) 与四个尚未激活的
acceptance 目录不相交。(a) 破了就是「假绿」——套件变了而哈希没变，十次绿里混进了测别的东西
的那几次；(b) 破了就是「误清零」——一个还没激活的组改一行，把 soak 计数打回零。两者都不是
读者复核表头时能稳定看出来的，所以写成用例。

**本文件只解析文档，不执行 `suite_hash` 命令，也不比对它的输出。**
矩阵第四条明写了理由：断言「表头记的值 == 现在跑命令算出来的值」会让每一次**合法的**套件改动
都红一条与它无关的用例（change-tax 反模式），而「冻结」的语义本来就是「这个值不随之后的改动走」。
复算是 review 动作，写在表头里由人执行。

本文件不碰 `books/`，不写任何文件，只读仓库里的两份 Markdown 与 `tests/e2e/` 下的源码。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = REPO_ROOT / "docs" / "plans" / "20260816-tech-stack-migration" / "tasks"
SOAK_LOG = TASKS_DIR / "soak-log.md"
TESTS_ROOT = REPO_ROOT / "tests"
BASELINE_DIR = TESTS_ROOT / "e2e" / "baseline_1b"

# 迁移计划 §7「台账字段（canonical）」的八列，**顺序敏感**。这里是抄写处，不是定义处；
# 定义处是 docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md §7。
CANONICAL_COLUMNS: List[str] = [
    "ts_utc",
    "commit",
    "result",
    "duration_s",
    "suite_hash",
    "browser",
    "os",
    "log",
]

# 四个尚未激活的 acceptance 组目录（相对仓库根）。它们必须**在 suite_hash 覆盖之外**。
ACCEPTANCE_DIRS: List[str] = [
    "tests/e2e/acceptance_2a",
    "tests/e2e/acceptance_4a4",
    "tests/e2e/acceptance_4b1",
    "tests/e2e/acceptance_p3",
]

# 裁决 (2) 的代价必须在表头可定位：前两个是共享方（代价的来源），第三个是被显式排除的那个。
REQUIRED_COST_TOKENS: List[str] = [
    "tests/fixtures/epub_corpus.py",
    "tests/unit/test_fixture_epub_corpus.py",
    "pyproject.toml",
]

# 指向迁移计划 §7 的链接（断的是**指针**，不是规则文本——规则的唯一定义处在 §7）。
PLAN_LINK_RE = re.compile(r"\]\((?P<target>[^)\s]*plan-tech-stack-migration\.md#[^)\s]+)\)")

# 表头记录的当前 suite_hash。故意用宽松的字符类捕获，再单独断形状：
# 写成 `abc`（3 位）时本用例要报「形状不合法」，而不是报「解析不到」。
CURRENT_HASH_RE = re.compile(r"当前\s*`suite_hash`\s*值\s*[：:]\s*`(?P<value>[^`]+)`")

HASH_SHAPE_RE = re.compile(r"^[0-9a-f]{12}$")


# --------------------------------------------------------------------------
# 解析辅助
# --------------------------------------------------------------------------
def read_soak_log() -> str:
    """读 `soak-log.md`。文件不存在时给出 AssertionError 而不是 OSError。"""
    assert SOAK_LOG.is_file(), (
        f"台账文件不存在：{SOAK_LOG}\n"
        "WI-2 的产物就是它；没有它，下面每一条断言都无从谈起。"
    )
    return SOAK_LOG.read_text(encoding="utf-8")


def split_row(line: str) -> List[str]:
    """把一行 Markdown 表格切成单元格（去掉首尾空管道）。"""
    cells = line.strip().split("|")
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [c.strip() for c in cells]


def first_table(text: str) -> Tuple[List[str], List[str]]:
    """返回文件里**第一张** Markdown 表格的 (表头单元格, 数据行原文)。

    「第一张」是本契约的一部分：台账表必须是文件里的第一张表，这样解析无歧义。
    """
    lines = text.splitlines()
    block: List[str] = []
    for line in lines:
        if line.strip().startswith("|"):
            block.append(line)
        elif block:
            break
    assert len(block) >= 2, (
        "在 soak-log.md 里找不到一张 Markdown 表格（至少要有表头行 + 分隔行）。"
    )
    header = split_row(block[0])
    sep = split_row(block[1])
    assert all(set(c) <= set("-: ") and "-" in c for c in sep), (
        f"第二行不是 Markdown 表格分隔行，实际解析到：{sep}"
    )
    data_rows = [ln for ln in block[2:] if split_row(ln)]
    return header, data_rows


def hash_command_block(text: str) -> str:
    """取出装 `suite_hash` 取法命令的那个 fenced bash 块（必须恰好一个）。"""
    blocks = re.findall(r"^```bash[^\n]*\n(.*?)^```", text, re.S | re.M)
    candidates = [b for b in blocks if "git ls-files" in b]
    assert len(candidates) == 1, (
        f"表头里含 `git ls-files` 的 fenced bash 块应恰好 1 个，实际 {len(candidates)} 个。"
        " 多于一个则「哪条是取哈希的命令」不再可判定。"
    )
    return candidates[0]


def covered_paths(block: str) -> List[str]:
    """从命令里正则抽出 `git ls-files -s` 后面的路径列表。"""
    body = "\n".join(
        ln for ln in block.splitlines() if not ln.strip().startswith("#")
    )
    body = body.replace("\\\n", " ")
    m = re.search(r"git\s+ls-files\s+-s\s+(?P<paths>.*?)\|", body, re.S)
    assert m is not None, (
        "在 fenced bash 块里找不到 `git ls-files -s <paths> |` 形状的命令：\n" + block
    )
    tokens = m.group("paths").split()
    paths = [t for t in tokens if not t.startswith("-")]
    assert paths, "`git ls-files -s` 后面没有解析出任何路径。"
    return paths


def _is_covered(rel: str, covered: Iterable[str]) -> bool:
    for c in covered:
        c = c.rstrip("/")
        if rel == c or rel.startswith(c + "/"):
            return True
    return False


def _resolve_module(dotted: str, from_path: Path) -> Optional[Path]:
    """把一个 import 目标解析成 `tests/` 下的文件路径；解析不到（三方库、stdlib）返回 None。

    **搜索序必须与 pytest 的实际 `sys.path` 同序，否则解析出来的是另一个文件。**
    实测（在 `tests/e2e/baseline_1b/` 下的用例里 print `conftest.__file__`）：

        sys.path[:4] = [tests/e2e/baseline_1b, tests/e2e, tests/fixtures, tests]
        conftest -> tests/e2e/conftest.py
        helpers  -> tests/e2e/helpers.py

    早先这里把 `REPO_ROOT, TESTS_ROOT` 排在前面，于是裸名 `conftest` 被解析成
    `tests/conftest.py`——**不是** pytest 实际导入的那个。后果不是「多报一个文件」这么轻：
    守卫会点着一个与该 import 无关的文件报错，读的人照着它去改哈希命令，而真正被 import
    的 `tests/e2e/conftest.py` 是否在覆盖里，全凭运气。它今天恰好在，所以这个错误
    表现为「结论碰巧对、理由是假的」——比直接报错更难发现。

    搜索根按导入方所在目录起算，再依次是 e2e / fixtures / tests / 仓库根。
    点分路径（`from tests.fixtures.epub_corpus import ...`）由最后两个根兜住。
    """
    parts = dotted.split(".")
    roots = [
        from_path.parent,
        TESTS_ROOT / "e2e",
        TESTS_ROOT / "fixtures",
        TESTS_ROOT,
        REPO_ROOT,
    ]
    for root in roots:
        base = root.joinpath(*parts)
        for cand in (base.with_suffix(".py"), base / "__init__.py"):
            if cand.is_file():
                try:
                    cand.relative_to(TESTS_ROOT)
                except ValueError:
                    continue
                return cand
    return None


def _import_targets(path: Path) -> Set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    targets: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # 相对 import：以模块所在目录上溯 level-1 层为基点。
                base_dir = path.parent
                for _ in range(node.level - 1):
                    base_dir = base_dir.parent
                try:
                    prefix = ".".join(base_dir.relative_to(REPO_ROOT).parts)
                except ValueError:
                    continue
                head = f"{prefix}.{node.module}" if node.module else prefix
                targets.add(head)
                for alias in node.names:
                    targets.add(f"{head}.{alias.name}")
            elif node.module:
                targets.add(node.module)
                for alias in node.names:
                    targets.add(f"{node.module}.{alias.name}")
    return targets


def baseline_import_closure() -> Set[str]:
    """`tests/e2e/baseline_1b/**` 每个模块的 import 传递闭包，限定在 `tests/` 下。

    **闭包有两个来源，缺一不可。** 一是 AST 追出来的 import 图；二是**祖先 conftest**
    ——`tests/conftest.py` 与 `tests/e2e/conftest.py` 由 pytest 按目录层级自动加载，
    **没有任何一条 import 语句指向它们**，纯 AST 追踪永远看不见。而它们照样是套件的一部分：
    `tests/conftest.py` 里那个 `pytest_configure` 钩子（校验 `-m` 表达式里的 marker）
    直接决定 baseline 能不能被选中，改它就是改 suite。漏了这一支，`suite_hash` 会对
    「改了根 conftest」这件事无动于衷——正是本条要拦的假绿形态。
    """
    seen: Set[Path] = set()
    queue: List[Path] = sorted(BASELINE_DIR.rglob("*.py")) if BASELINE_DIR.is_dir() else []
    # 祖先 conftest：从 baseline 目录上溯到 tests/ 为止，存在即入队。
    probe = BASELINE_DIR
    while True:
        cand = probe / "conftest.py"
        if cand.is_file():
            queue.append(cand)
        if probe == TESTS_ROOT or TESTS_ROOT not in probe.parents:
            break
        probe = probe.parent
    closure: Set[str] = set()
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        closure.add(current.relative_to(REPO_ROOT).as_posix())
        for dotted in _import_targets(current):
            resolved = _resolve_module(dotted, current)
            if resolved is not None and resolved not in seen:
                queue.append(resolved)
    return closure


def plan_link_lines(text: str) -> Dict[str, str]:
    """返回 {行原文: 该行指向 §7 的链接 target}。"""
    out: Dict[str, str] = {}
    for line in text.splitlines():
        m = PLAN_LINK_RE.search(line)
        if m:
            out[line] = m.group("target")
    return out


# --------------------------------------------------------------------------
# Case 1: 八列列名与迁移计划 §7 的 canonical 列表逐字相等（success / S2 / L1）
# --------------------------------------------------------------------------
def test_ledger_columns_match_plan_section7_verbatim_and_in_order():
    header, _ = first_table(read_soak_log())
    # 列表等值比较：不是 set 比较，也不是 `all(c in header)` —— 后两种写法对「少一列」是盲的。
    assert header == CANONICAL_COLUMNS, (
        "台账表头必须与迁移计划 §7 的 canonical 八列逐字相等且同序。\n"
        f"期望：{CANONICAL_COLUMNS}\n实际：{header}"
    )


# --------------------------------------------------------------------------
# Case 2: 哈希命令覆盖 baseline 的 import 闭包，且与四个 acceptance 目录不相交
#         （property / S4 / L1）
# --------------------------------------------------------------------------
def test_hash_command_covers_baseline_import_closure():
    covered = covered_paths(hash_command_block(read_soak_log()))
    closure = baseline_import_closure()
    missing = sorted(rel for rel in closure if not _is_covered(rel, covered))
    assert not missing, (
        "以下文件被 `tests/e2e/baseline_1b/**` 直接或间接 import，却不在 `suite_hash`"
        " 的覆盖路径里——改了它们 suite 变了而哈希不变，就是「假绿」：\n  "
        + "\n  ".join(missing)
        + f"\n哈希命令当前覆盖：{covered}"
    )


def test_hash_command_is_disjoint_from_the_four_acceptance_groups():
    covered = [c.rstrip("/") for c in covered_paths(hash_command_block(read_soak_log()))]
    leaked = sorted(
        d
        for d in ACCEPTANCE_DIRS
        if any(c == d or c.startswith(d + "/") or d.startswith(c + "/") for c in covered)
    )
    assert not leaked, (
        "以下 acceptance 组目录落进了 `suite_hash` 的覆盖范围——它们尚未激活，"
        "改动它们不应清零 soak 计数：\n  " + "\n  ".join(leaked)
    )


# --------------------------------------------------------------------------
# Case 3: 表头把两条纳入/排除口径的**代价**写成可定位的事实（guard / S3 / L1）
# --------------------------------------------------------------------------
def test_header_names_the_shared_and_excluded_files_by_path():
    text = read_soak_log()
    absent = [tok for tok in REQUIRED_COST_TOKENS if tok not in text]
    assert not absent, (
        "表头必须逐字点名这些文件，否则「改一条纯单测也会清零 soak」这个已知成本就被藏起来了：\n  "
        + "\n  ".join(absent)
    )


def test_three_reset_triggers_are_pointers_to_plan_section7():
    text = read_soak_log()
    linked = plan_link_lines(text)
    assert len(linked) == 3, (
        "指向迁移计划 §7 的链接应恰好出现在 3 行上（三类清零触发器各一行，"
        "作为**指针**而非规则复述）。实际 "
        f"{len(linked)} 行：\n  " + "\n  ".join(linked)
    )
    anchors = {t.split("#", 1)[1] for t in linked.values()}
    assert len(anchors) == 1, f"三条指针应指向同一个 §7 锚点，实际：{sorted(anchors)}"

    predicates = {
        "suite_hash 变了": lambda ln: "`suite_hash`" in ln,
        "browser/os 变了": lambda ln: "`browser`" in ln and "`os`" in ln,
        "任意一次 red": lambda ln: "`red`" in ln,
    }
    matched: Dict[str, List[str]] = {}
    for name, pred in predicates.items():
        hits = [ln for ln in linked if pred(ln)]
        assert len(hits) == 1, (
            f"清零触发器「{name}」应恰好由 1 行带 §7 链接的条目承载，实际 {len(hits)} 行：{hits}"
        )
        matched[name] = hits
    flat = [hits[0] for hits in matched.values()]
    assert len(set(flat)) == 3, (
        f"三类触发器必须落在三行不同的条目上，实际：{flat}"
    )


# --------------------------------------------------------------------------
# Case 4: 冻结前的行被标注为不计数，且记录值形状合法（boundary / S2 / L1）
# --------------------------------------------------------------------------
def test_recorded_suite_hash_has_legal_shape():
    text = read_soak_log()
    m = CURRENT_HASH_RE.search(text)
    assert m is not None, (
        "表头里找不到「当前 `suite_hash` 值：`<12 位十六进制>`」这行——"
        "台账少了它就不自带复核方式。"
    )
    value = m.group("value")
    assert HASH_SHAPE_RE.match(value), (
        f"表头记录的 suite_hash 形状不合法（期望 12 位小写十六进制）：{value!r}"
    )


def test_rows_predating_the_freeze_are_marked_pre_freeze():
    text = read_soak_log()
    m = CURRENT_HASH_RE.search(text)
    assert m is not None, "表头里找不到当前 `suite_hash` 值，无法判定哪些行产生于冻结之前。"
    frozen = m.group("value")

    header, rows = first_table(text)
    idx = header.index("suite_hash") if "suite_hash" in header else None
    assert idx is not None, f"表头没有 suite_hash 列：{header}"

    unmarked: List[str] = []
    for line in rows:
        cells = split_row(line)
        if len(cells) <= idx:
            continue
        cell = cells[idx].strip("`* ")
        if cell and cell != frozen and "pre-freeze" not in line.lower():
            unmarked.append(line)
    assert not unmarked, (
        "以下数据行的 suite_hash 与表头记录的冻结值不同，却没有标注 `pre-freeze`——"
        "那正是「拿冻结前的绿充数」：\n  " + "\n  ".join(unmarked)
    )


def test_no_ledger_row_strays_outside_the_table():
    """脱离表体的数据行 = 一条谁也检查不到的记账。

    `first_table()` 只收**第一个连续**的 `|` 行块，这是它能无歧义定位台账表的前提，
    不打算改。代价是：数据行与表之间只要隔一个空行，它就整个掉出解析范围——而
    `pre-freeze` 那条检查恰恰是逐行扫 `first_table()` 的返回值，看不见的行它一条都
    判不了，于是「拿冻结前的绿充数」这个它专门要拦的形态，反而从它眼皮底下走掉，
    七条用例照常全绿。实测过：把一行 `990bfff749ef` 的绿记录放在表下方的注释之后，
    全绿。

    文档那条注释原本写的就是「追加到上表下方」，等于在教人踩这个坑，现已改口径；
    但注释是给人看的，拦不住手滑。这条用例拦的是后果本身，与注释怎么写无关。

    只认「八格」这一形态：文件里另有一张两列的索引态实测表，是正当内容，不该被误伤。
    """
    text = read_soak_log()
    lines = text.splitlines()

    # 复刻 first_table 的取块口径——两处必须同款，否则「块内 / 块外」的划分会有缝。
    start = next((i for i, ln in enumerate(lines) if ln.strip().startswith("|")), None)
    assert start is not None, "soak-log.md 里一张 Markdown 表都没有。"
    end = start
    while end < len(lines) and lines[end].strip().startswith("|"):
        end += 1

    strays = [
        f"第 {i + 1} 行：{lines[i].strip()}"
        for i in range(end, len(lines))
        if lines[i].strip().startswith("|") and len(split_row(lines[i])) == len(CANONICAL_COLUMNS)
    ]
    assert not strays, (
        "以下八列的数据行落在台账表之外，解析器看不见它们，`pre-freeze` 检查也就判不了——\n  "
        + "\n  ".join(strays)
        + "\n把它们移回分隔行正下方，中间不要留空行。"
    )
