"""`soak-log.md` 表头的**台账契约**（009 WI-2）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` 的 `## WI-2:` 一节，四条 unit 用例。

**为什么给一份 Markdown 写单测。** 因为这里被断的不是文风，是两条**可判定的集合关系**：
`suite_hash` 的覆盖面必须 (a) 罩住冻结套件真正 import 的每一个文件，(b) 与四个尚未激活的
acceptance 目录不相交。(a) 破了就是「假绿」——套件变了而哈希没变，十次绿里混进了测别的东西
的那几次；(b) 破了就是「误清零」——一个还没激活的组改一行，把 soak 计数打回零（2026-09-28 起按 §7 批次规则读作：
让已通过的批次无端失效、须重跑一批）。两者都不是
读者复核表头时能稳定看出来的，所以写成用例。

**本文件只解析文档，不执行 `suite_hash` 命令，也不比对它的输出。**
矩阵第四条明写了理由：断言「表头记的值 == 现在跑命令算出来的值」会让每一次**合法的**套件改动
都红一条与它无关的用例（change-tax 反模式），而「冻结」的语义本来就是「这个值不随之后的改动走」。
复算是 review 动作，写在表头里由人执行。

本文件不碰 `books/`，不写任何文件，只读仓库里的两份 Markdown 与 `tests/e2e/` 下的源码。
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

import pytest

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


# --------------------------------------------------------------------------
# `suite_hash` 配方的**逐字形状**（2026-09-05 审计 #16/#77 补）
#
# 上面两条只断了覆盖面的两条集合关系（罩住 import 闭包、与 acceptance 目录不相交）。集合关系
# 对**命令本身**是盲的：把 `git hash-object --stdin` 换成 `sha256sum`、把 `cut -c1-12` 改成
# `-c1-16`、在块里多插一行命令，两条集合关系照样全绿，而 `suite_hash` 已经不是同一个函数了——
# 冻结值与之后重算的值不可比，「同一套用例的第 N 次绿」这句话失去意义。
# 下面三组把配方的每一段都钉死：八条路径（顺序敏感）、管道的每一个 token、以及
# **运行器对不合形状的配方必须拒绝执行**（`scripts/soak_run.py` 不再把这个块交给 `bash -c`）。
# --------------------------------------------------------------------------
SOAK_RUN_PATH = REPO_ROOT / "scripts" / "soak_run.py"

#: 八条覆盖路径，**顺序敏感**，与台账表头那条命令逐字同序。
EXPECTED_HASH_PATHS: List[str] = [
    "tests/e2e/baseline_1b",
    "tests/e2e/conftest.py",
    "tests/e2e/helpers.py",
    "tests/e2e/test_harness_smoke.py",
    "tests/fixtures/epub_corpus.py",
    "tests/fixtures/epub_zip.py",
    "tests/fixtures/ai_stub.py",
    "tests/conftest.py",
]

#: 归一化之后的完整 token 流。`{ … ; }` 的花括号也在内：去掉它们，`cut` 只会作用在管道的
#: 最后一段上，值就变了。
EXPECTED_HASH_TOKENS: List[str] = [
    "{",
    "git",
    "ls-files",
    "-s",
    *EXPECTED_HASH_PATHS,
    "|",
    "git",
    "hash-object",
    "--stdin",
    ";",
    "}",
    "|",
    "cut",
    "-c1-12",
]


def normalized_hash_tokens(block: str) -> List[str]:
    """把 fenced 块归一化成 token 流：去注释、接续行，`{` `}` `|` `;` 各自成 token。

    **本文件自己实现一遍，不调 `soak_run.parse_hash_recipe`**：这里断的是「文档里写的是什么」，
    拿被测脚本的解析器去读文档，等于让实现给自己判卷——解析器把 `--stdin` 读成 `--stdin;`
    也一样能自洽。负例那几条才用运行器，断的是「运行器拒不拒」。
    """
    body = "\n".join(ln for ln in block.splitlines() if not ln.strip().startswith("#"))
    body = body.replace("\\\n", " ")
    for sym in ("{", "}", "|", ";"):
        body = body.replace(sym, f" {sym} ")
    return body.split()


def _soak_run() -> ModuleType:
    """按路径加载 `scripts/soak_run.py`（`scripts/` 不是包）。"""
    assert SOAK_RUN_PATH.is_file(), f"{SOAK_RUN_PATH} 不存在"
    name = "soak_run_for_log_contract"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SOAK_RUN_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


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


def test_hash_command_covers_exactly_the_eight_documented_paths_in_order():
    """八条路径，逐字、同序、不多不少。

    列表等值比较而不是集合比较：少一条 ＝ 那个文件改了哈希不变（假绿），多一条 ＝ 一个与
    baseline 无关的文件把计数清零（误清零；批次规则下读作「让已通过的批次无端失效」）。两侧误差各有代价，所以两侧都断。
    """
    actual = covered_paths(hash_command_block(read_soak_log()))
    assert actual == EXPECTED_HASH_PATHS, (
        "台账里 `git ls-files -s` 的路径清单与本文件记录的八条不一致。\n"
        f"期望：{EXPECTED_HASH_PATHS}\n实际：{actual}\n"
        "覆盖面要改，这里、台账、`scripts/soak_run.py` 的 HASH_COVERED_PATHS 三处一起改——"
        "改覆盖面是一次应当留下多处签名的动作。"
    )


def test_hash_command_is_the_documented_pipeline_token_for_token():
    """`{ git ls-files -s <八条> | git hash-object --stdin; } | cut -c1-12`，一个 token 都不许差。

    为什么连 `cut -c1-12` 都要断：台账里所有历史值都是 12 位，`test_recorded_suite_hash_has_legal_shape`
    也按 12 位断形状。悄悄改成 `-c1-16`，表头那条「复制出来跑一遍，输出应等于表头记的值」的
    人工复核会当场对不上，而没有任何一条用例说得出为什么。
    """
    actual = normalized_hash_tokens(hash_command_block(read_soak_log()))
    assert actual == EXPECTED_HASH_TOKENS, (
        "台账里的哈希命令不再是那条定死的管道。\n"
        f"期望：{' '.join(EXPECTED_HASH_TOKENS)}\n实际：{' '.join(actual)}"
    )


def _mutate(old: str, new: str) -> Callable[[str], str]:
    """把改写**限定在那个 fenced 块内**，块外的散文原样保留。

    直接对全文 `replace(..., 1)` 是不行的：`git ls-files -s`、`git hash-object --stdin`
    这些字符串在台账正文里也出现（讲配方为什么这么定的那几段），全文替换会先命中散文，
    块纹丝不动，负例于是什么都没测到——2026-09-05 加解释性段落时这个陷阱真的触发过。
    """

    def apply(text: str) -> str:
        block = hash_command_block(text)
        assert block in text, "hash_command_block 返回的不是台账的逐字子串，本 helper 的前提失效"
        assert old in block, f"待改写的片段不在哈希命令块里，本负例的前提已失效：{old!r}"
        return text.replace(block, block.replace(old, new, 1), 1)

    return apply


@pytest.mark.parametrize(
    "case_id,mutate",
    [
        ("extra-path", _mutate("tests/conftest.py \\", "tests/conftest.py tests/e2e/acceptance_2a \\")),
        ("dropped-path", _mutate("tests/e2e/helpers.py ", "")),
        ("reordered-paths", _mutate("tests/e2e/conftest.py tests/e2e/helpers.py", "tests/e2e/helpers.py tests/e2e/conftest.py")),
        ("hash-tool-swapped", _mutate("git hash-object --stdin", "sha256sum")),
        ("truncation-widened", _mutate("cut -c1-12", "cut -c1-16")),
        ("ls-files-unstaged", _mutate("git ls-files -s", "git ls-files")),
        ("extra-command-injected", _mutate("{ git ls-files -s", "touch /tmp/soak-pwned; { git ls-files -s")),
        ("braces-dropped", _mutate("{ git ls-files -s", "git ls-files -s")),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_the_runner_refuses_a_recipe_that_is_not_that_pipeline(case_id: str, mutate: Callable[[str], str]):
    """改过形状的配方，`scripts/soak_run.py` 必须**拒绝**——而不是照着执行再看输出像不像哈希。

    这八条是同一件事的八个面：台账是一份人人可编辑的 Markdown，旧实现把那个块原样交给
    `bash -c`，校验只看输出末 12 位是不是十六进制。于是 `extra-command-injected` 这一条
    （在块里插一行命令）在旧实现下**既会执行那行命令、又会返回一个完全合法的哈希**，
    台账上一点痕迹都没有。其余七条则是「值悄悄换了定义」：换工具、换截断长度、换路径集合、
    去掉 `-s`（改读工作区而非索引）、去掉花括号（`cut` 只作用在最后一段）。

    本条只断「拒绝」，不断具体消息文本——消息会改，拒绝不能不发生。
    """
    soak = _soak_run()
    original = read_soak_log()
    tampered = mutate(original)
    # 前提：改写必须落在**那个 fenced 块里**。台账正文里同样的字符串出现过很多次，
    # 改中了一处散文而块原封不动的话，下面的 `raises` 会以「解析器有别的毛病」的形式假绿。
    assert hash_command_block(tampered) != hash_command_block(original), (
        f"{case_id}: 改写没有落在哈希命令块里，本负例什么都没测到"
    )
    with pytest.raises(soak.HashRecipeError):
        soak.parse_hash_recipe(tampered)


def test_the_runner_accepts_the_real_ledger_recipe():
    """对称的另一半：真台账必须解析得出配方，且路径与本文件记录的八条一致。

    没有它，上面那组负例可以由一个「永远抛异常」的解析器全绿通过。
    """
    soak = _soak_run()
    recipe = soak.parse_hash_recipe(read_soak_log())
    assert list(recipe.paths) == EXPECTED_HASH_PATHS, f"运行器解析出的路径与文档不一致：{recipe.paths}"
    assert recipe.truncate == 12, f"截断长度不是 12：{recipe.truncate}"
    assert list(soak.HASH_COVERED_PATHS) == EXPECTED_HASH_PATHS, (
        f"`soak_run.HASH_COVERED_PATHS` 与台账/本文件的八条不一致：{soak.HASH_COVERED_PATHS}"
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


# 「三类清零触发器」是 §7 原文的名字；2026-09-28 起它们读作「不是同一批」（§7 批次规则 3），
# 表头那三行指针与本用例钉的形状都不变，所以用例名照旧。
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


# Case 4b: 每一行都**有账可查**——值不同于表头当前值，不等于「产生于冻结之前」（2026-10-02 改写）
#
# 原用例只读表头一个值，凡不等于它的行一律要求标 `pre-freeze`。表里只有一个 `suite_hash` 时这没问题；
# 批次规则（迁移计划 §7，2026-09-28）之后，`suite_hash` 每变一次就在新值上另开一批，旧批次的行**原样
# 保留且仍然有效**（`B1` 的 10 行至今是 `--verdict B1` 的判据）。表头一改成新值，原用例就把 `B1` 的
# 10 行和批次规则之前的 4 行全判成「拿冻结前的绿充数」——把「不是今天的值」读成了「冻结之前」。
#
# 现在一行放行，当且仅当下列之一成立：
#   (a) `suite_hash` 等于表头「当前 `suite_hash` 值」；
#   (b) 它落在某个已声明批次的**位置窗口**里（`soak_run.batch_verdict` 实际判的那至多 10 行），
#       且 commit / suite_hash / browser / os 四项与**该**声明逐字相同；
#   (c) 它的 `ts_utc` 早于**最早**一条批次声明的起始时刻（批次规则之前的行，表头写明「不计入任何批次」）；
#   (d) 行内显式标注 `pre-freeze`。
# (b) 是按位置、不是按值：**只声明一个 hash 不豁免任何行**——窗口之外再追加的同 hash 行照样判红。
# 那正是本次改写要堵的洞：若按「哈希在任一声明里出现过」放行，往 B1 之后再补一行 `1e868c7bf811`
# 的绿就能永远躲过这条检查（见下面的 4c 负例）。
#
# 声明解析与窗口取法**直接用 `scripts/soak_run.py` 的**，不在这里另写一份：这里要断的正是
# 「判决器认为属于某批的那些行」，自己再实现一遍，两边一漂移就会出现「判决器认、契约不认」的缝。
# 声明不合形状时 `parse_batch_declarations` 抛错，本用例随之红——fail closed，与 `--verdict` 同口径。
def unaccounted_rows(text: str) -> List[str]:
    """返回台账第一张表里**无账可查**的数据行原文（四条放行理由一条都不满足的行）。"""
    m = CURRENT_HASH_RE.search(text)
    assert m is not None, "表头里找不到当前 `suite_hash` 值，无法判定哪些行有账可查。"
    current = m.group("value")

    header, lines = first_table(text)
    assert "suite_hash" in header, f"表头没有 suite_hash 列：{header}"
    idx = header.index("suite_hash")

    sr = _soak_run()
    decls = sr.parse_batch_declarations(text)
    rows = sr.ledger_rows(text)
    # 两个解析器读的必须是同一组行，否则下面按下标对位就是错位。
    assert [list(r.cells) for r in rows] == [split_row(ln) for ln in lines], (
        "`soak_run.ledger_rows` 与 `first_table` 读出的数据行不一致，无法按位置对账。"
    )

    # (b)：每个声明的窗口，按对象身份映射回下标（`batch_verdict` 返回的就是传入列表里的那些对象）。
    in_batch: Set[int] = set()
    for decl in decls.values():
        verdict = sr.batch_verdict(decl, rows)
        window_ids = {id(r) for r in verdict.rows}
        for i, row in enumerate(rows):
            if id(row) not in window_ids:
                continue
            if (row.commit, row.suite_hash, row.browser, row.os) == (
                decl.commit,
                decl.suite_hash,
                decl.browser,
                decl.os,
            ):
                in_batch.add(i)

    # (c)：最早一条声明的起始时刻；没有任何声明时这一条不放行任何行。
    earliest = min((d.start_ts for d in decls.values()), default=None)

    out: List[str] = []
    for i, line in enumerate(lines):
        cells = split_row(line)
        if len(cells) <= idx:
            continue
        cell = cells[idx].strip("`* ")
        if not cell or cell == current:  # (a)
            continue
        if i in in_batch:  # (b)
            continue
        ts = sr._parse_row_ts(cells[0]) if cells else None
        if earliest is not None and ts is not None and ts < earliest:  # (c)
            continue
        if "pre-freeze" in line.lower():  # (d)
            continue
        out.append(line)
    return out


def test_every_row_is_accounted_for_by_current_hash_or_a_declared_batch():
    unmarked = unaccounted_rows(read_soak_log())
    assert not unmarked, (
        "以下数据行的 suite_hash 不等于表头当前值，又不在任何已声明批次的 10 行窗口里（或身份与该批声明不符），"
        "也不早于第一条批次声明、没有标注 `pre-freeze`——那正是「拿冻结前的绿充数」：\n  "
        + "\n  ".join(unmarked)
    )


# --------------------------------------------------------------------------
# Case 4c: 上一条的放行规则在合成台账上逐条钉死（tmp_path，不碰真台账）
# --------------------------------------------------------------------------
_SYN_OLD = "1111111111aa"  # 旧批次的 suite_hash
_SYN_NEW = "2222222222bb"  # 表头当前值
_SYN_DECL_TS = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)


def _syn_row(ts: datetime, commit: str, suite_hash: str, extra: str = "", os_: str = "darwin-25.3.0") -> str:
    return (
        f"| {ts.strftime('%Y-%m-%dT%H:%M:%SZ')} | {commit} | green | 55.00 | {suite_hash} "
        f"| chromium-1234 | {os_} | logs/{commit}-{ts:%H%M%S}.log{extra} |"
    )


def _syn_ledger(tmp_path: Path, extra_rows: List[str], decl_hash: str = _SYN_OLD) -> str:
    """一份最小合成台账：批次 `Q1` 声明在 `_SYN_OLD` 上，其后紧跟恰好 10 行吻合的窗口行，再接 `extra_rows`。"""
    decl = (
        f"> - `Q1`｜`{_SYN_DECL_TS:%Y-%m-%dT%H:%M:%SZ}`｜`abc1234`｜`{decl_hash}`｜`chromium-1234`｜`darwin-25.3.0`"
    )
    window = [_syn_row(_SYN_DECL_TS + timedelta(minutes=1 + i), "abc1234", _SYN_OLD) for i in range(10)]
    text = "\n".join(
        [
            "# 合成台账",
            "",
            decl,
            "",
            "| ts_utc | commit | result | duration_s | suite_hash | browser | os | log |",
            "|---|---|---|---|---|---|---|---|",
            *window,
            *extra_rows,
            "",
            f"当前 `suite_hash` 值：`{_SYN_NEW}`",
            "",
        ]
    )
    (tmp_path / "soak-log.md").write_text(text, encoding="utf-8")
    return (tmp_path / "soak-log.md").read_text(encoding="utf-8")


_AFTER_WINDOW = _SYN_DECL_TS + timedelta(hours=1)


def test_4c1_declared_batch_window_rows_are_accounted(tmp_path: Path):
    """(b) 正例：旧 hash 的 10 行窗口行全部放行；当前 hash 的后续行按 (a) 放行。"""
    text = _syn_ledger(tmp_path, [_syn_row(_AFTER_WINDOW, "def5678", _SYN_NEW)])
    assert unaccounted_rows(text) == []


def test_4c2_declaring_a_hash_does_not_exempt_rows_outside_its_window(tmp_path: Path):
    """要堵的洞：窗口之外再补一行与声明**完全同身份**的旧 hash 绿行——只因 hash 被声明过，不得放行。"""
    stray = _syn_row(_AFTER_WINDOW, "abc1234", _SYN_OLD)
    text = _syn_ledger(tmp_path, [stray])
    assert unaccounted_rows(text) == [stray]


def test_4c3_window_row_with_foreign_identity_is_not_accounted(tmp_path: Path):
    """(b) 要求四项身份与**该**声明相同：窗口里一行 os 不同的旧 hash 行不放行（它也不在任何别的批次里）。"""
    text = _syn_ledger(tmp_path, [])
    lines = text.split("\n")
    i = next(k for k, ln in enumerate(lines) if ln.startswith("| 2026-01-10T12:05:00Z"))
    foreign = lines[i].replace("darwin-25.3.0", "linux-6.1.0")
    lines[i] = foreign
    assert unaccounted_rows("\n".join(lines)) == [foreign]


def test_4c4_rows_before_the_earliest_declaration_are_accounted(tmp_path: Path):
    """(c)：最早一条声明之前的旧 hash 行放行（批次规则之前的行，不计入任何批次）。"""
    early = _syn_row(_SYN_DECL_TS - timedelta(days=3), "0ld0001", _SYN_OLD)
    text = _syn_ledger(tmp_path, [])
    lines = text.split("\n")
    sep = lines.index("|---|---|---|---|---|---|---|---|")
    lines.insert(sep + 1, early)
    assert unaccounted_rows("\n".join(lines)) == []


def test_4c5_explicit_pre_freeze_mark_is_accounted(tmp_path: Path):
    """(d)：窗口之外的旧 hash 行，显式标注 `pre-freeze` 即放行。"""
    stray = _syn_row(_AFTER_WINDOW, "abc1234", _SYN_OLD, extra=" pre-freeze")
    assert unaccounted_rows(_syn_ledger(tmp_path, [stray])) == []


def test_4c6_no_declarations_means_only_current_hash_or_mark(tmp_path: Path):
    """没有任何批次声明时 (b)(c) 都不放行：回到原用例的口径——值不同于当前值就必须标 `pre-freeze`。"""
    text = _syn_ledger(tmp_path, [])
    lines = [ln for ln in text.split("\n") if not ln.startswith("> - `Q1`")]
    unmarked = unaccounted_rows("\n".join(lines))
    assert len(unmarked) == 10 and all(_SYN_OLD in ln for ln in unmarked)


def test_4c7_malformed_declaration_fails_closed(tmp_path: Path):
    """声明写错时整次判定失败，而不是悄悄当作「没有声明」——与 `--verdict` 同口径。"""
    text = _syn_ledger(tmp_path, []).replace("｜`darwin-25.3.0`", "｜`darwin-25.3.0` 注记")
    with pytest.raises(_soak_run().BatchDeclarationError):
        unaccounted_rows(text)


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
