"""WI-17 · Unit A —— `scripts/lint_e2e_groups.py` 的**执行体**：三分划分律 ＋ skip 轴 ＋ 条数守卫。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` 的 `## WI-17:` 一节（Unit A 的七条）。
任务书：`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §0.5
（三分划分律、目录布局、条数口径）、§0.6 跨波欠账 **#2**（「实测 == 常量」）与 **#14**
（acceptance 由 14 变 17）、§8 G2 的 commit 级护栏（`baseline_1b` 可达链零 skip）。

**三条 Law，各自对应一类「零成本零信号」的破坏：**

1. **划分守卫的可失败性**——对合法目录树守卫必须绿；对「少一条 / 多一条 / marker 错 /
   文件跑错目录 / skip 标记缺失」任一变异必须红。没有守卫时，删掉一条 skip 用例是
   零成本且零信号的（§8：「不要把未激活组的 skip 当成永久豁免」）。
2. **`tests/e2e` 的每一个 collected item 都必须被归属**——恰好一个组 marker，或其模块在
   显式白名单 `UNGROUPED_E2E_MODULES` 里。没有第三种状态。Round 1 默认「根目录只有 smoke」，
   于是 `test_testid_dom_uniqueness.py` 落在一切断言之外（Gap C）。
3. **`baseline_1b` 的收集可达链上零 skip 构造**——包括 fixture 体、辅助函数体、
   `try/except` 处理器里的（Gap D）。一句
   `except Exception: pytest.skip(...)` 写进 `tests/e2e/conftest.py` 的 `live_server`，
   后果是 65 条 baseline 全部 skipped、push gate 全绿。判据必须 `ast.walk` 整个模块，
   不是扫 `Module.body`：那句 skip 在 AST 里的深度是 5。

**本文件的两个域，不可互相替代**：真实仓库树（本条 1/2/4/5/6/7）与 `tmp_path` 上的
合成树（本条 3）。合成树对「真实仓库里多了一个没人管的模块」是盲的，那是真树划分律的
职责；真树对「守卫会不会在变异上红」是盲的（真树今天合法，永远只能证明绿），那是合成
树的职责。Gap C 的事故正发生在真树上，而当时合成树的性质全绿。

**成本模型**：本文件的子进程一律 `--collect-only` 或纯 skip 执行——不起服务、不起
浏览器、不加载 epub.js。真树收集只跑**一次**（`_real_items()` 记忆化），三条断言共用同一次
结果；跑三次既慢又可能因中途改文件而不自洽。

**红收据说明**：本文件在 `scripts/lint_e2e_groups.py` 只有常量、四个 acceptance 目录
还是 `.gitkeep` 的状态下写成并录红——执行体缺失时以 `assert hasattr(...)` 的断言失败
呈现，不是 ImportError；真树条数在 14 条 skip 用例落地前也是断言失败。

------------------------------------------------------------------------------
定向破坏实录（§0 第四条纪律；破坏点全在 `tests/e2e/` 的**临时副本**或工作树，`src/` 一字未动）
------------------------------------------------------------------------------
见文末 `SABOTAGE_LOG`——实现落地后回填，不改本文件任何断言行。
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable, Dict, FrozenSet, List, Set, Tuple

import pytest

from test_soak_log_contract import (  # type: ignore[import-not-found]
    covered_paths,
    hash_command_block,
    read_soak_log,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
GROUPS_LINT_PATH = SCRIPTS_DIR / "lint_e2e_groups.py"
SOAK_RUN_PATH = SCRIPTS_DIR / "soak_run.py"
E2E_DIR = REPO_ROOT / "tests" / "e2e"
E2E_REL = "tests/e2e"
UNIT_DIR = REPO_ROOT / "tests" / "unit"

ACCEPTANCE_DIRS: Tuple[str, ...] = (
    "acceptance_4b1",
    "acceptance_p3",
    "acceptance_4a4",
    "acceptance_2a",
)
GROUP_MARKERS: Tuple[str, ...] = ("baseline_1b", *ACCEPTANCE_DIRS)

#: 矩阵条件 3：skip reason 里必须出现激活阶段标识。与守卫脚本各写一份是刻意的——
#: 本文件是守卫的**独立 oracle**，不从被测脚本 import 判据。
PHASE_TOKEN_RE = re.compile(r"4B\.1|P3|4A\.4|2a")

#: 每个组目录的 skip reason 必须点名**自己**的激活阶段。p3 的 token 是字面 `P3`。
PHASE_TOKEN_FOR_DIR: Dict[str, str] = {
    "acceptance_4b1": "4B.1",
    "acceptance_p3": "P3",
    "acceptance_4a4": "4A.4",
    "acceptance_2a": "2a",
}

#: 共享断言主体模块的裸模块名与期望落点（矩阵 Unit A 第八条的条 (3)）。
SHARED_DEG_MODULE = "deg_assertions"
SHARED_DEG_MODULE_PATH = REPO_ROOT / "tests" / "fixtures" / "deg_assertions.py"

#: 跨模块调用集里**不计**的来源：测试框架自身。`conftest` 不在名单里——它只导出常量，
#: 常量不会出现在「被调用的名字」集合里，天然被过滤。
EXCLUDED_IMPORT_PREFIXES = ("pytest", "playwright", "typing", "pathlib", "dataclasses", "__future__")

SUMMARY_TOKEN_RE = re.compile(
    r"(\d+) (passed|failed|errors?|skipped|deselected|xfailed|xpassed)"
)


# --------------------------------------------------------------------------
# 加载被测脚本（按路径；`scripts/` 不是包）
# --------------------------------------------------------------------------
_MODULE_CACHE: Dict[str, ModuleType] = {}


def _load(path: Path, name: str) -> ModuleType:
    if name in _MODULE_CACHE:
        return _MODULE_CACHE[name]
    assert path.exists(), f"{path} 不存在"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"无法从 {path} 加载"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    _MODULE_CACHE[name] = module
    return module


def _guard() -> ModuleType:
    """`scripts/lint_e2e_groups.py`，并断言执行体齐全。

    WI-1 只放了常量；执行体缺失在这里是一条**断言失败**而不是 AttributeError——
    这是本文件录红时的形态。
    """
    mod = _load(GROUPS_LINT_PATH, "lint_e2e_groups_guard_under_test")
    missing = [
        attr
        for attr in (
            "EXPECTED_BASELINE_ITEMS",
            "EXPECTED_ACCEPTANCE_PER_DIR",
            "EXPECTED_ACCEPTANCE_ITEMS",
            "EXPECTED_UNGROUPED_ITEMS",
            "UNGROUPED_E2E_MODULES",
            "collect_items",
            "partition_violations",
            "count_violations",
            "skip_axis_violations",
            "check_tree",
        )
        if not hasattr(mod, attr)
    ]
    assert not missing, (
        f"scripts/lint_e2e_groups.py 缺少 {missing}。WI-1 只放常量，划分律的执行体是 WI-17 的交付"
        "（任务书 §0.5：「这条划分律由 scripts/lint_e2e_groups.py 执行，不靠人眼」）。"
    )
    return mod


def _soak() -> ModuleType:
    assert SOAK_RUN_PATH.exists(), f"{SOAK_RUN_PATH} 不存在——soak 计数守卫（矩阵 Unit A 第五 / 六条）是 WI-17 的交付"
    return _load(SOAK_RUN_PATH, "soak_run_under_test")


_REAL_ITEMS: List[object] = []


def _real_items() -> List[object]:
    """真树的一次收集，全文件共用（矩阵：「全表只跑这一次收集」）。"""
    if not _REAL_ITEMS:
        _REAL_ITEMS.extend(_guard().collect_items(REPO_ROOT))
    return _REAL_ITEMS


def _module_of(item: object) -> str:
    return str(getattr(item, "module"))


def _markers_of(item: object) -> FrozenSet[str]:
    return frozenset(getattr(item, "markers"))


def _group_markers_of(item: object) -> Set[str]:
    return set(_markers_of(item)) & set(GROUP_MARKERS)


def _parse_summary_tokens(out: str) -> Dict[str, int]:
    counts = {k: 0 for k in ("passed", "failed", "errors", "skipped", "deselected")}
    tail = [ln for ln in out.splitlines() if " in " in ln and ("passed" in ln or "skipped" in ln or "failed" in ln or "error" in ln or "no tests ran" in ln)]
    assert tail, f"输出里找不到 pytest 的 summary 行：\n{out}"
    for n, key in SUMMARY_TOKEN_RE.findall(tail[-1]):
        if key.startswith("error"):
            key = "errors"
        if key in counts:
            counts[key] = int(n)
    return counts


# --------------------------------------------------------------------------
# Case 1：真实目录树上四个 acceptance 组的条数与 marker 正确（success / S2 / L1）
# --------------------------------------------------------------------------
def test_real_tree_acceptance_dir_counts_and_markers_match_constants() -> None:
    """四个目录各自的 item 数 == `EXPECTED_ACCEPTANCE_PER_DIR[dir]`，且每条恰好带自己目录的 marker。

    删掉一条 skip 用例——那个零成本零信号的动作——本条就是给它装信号的。
    """
    g = _guard()
    items = _real_items()

    per_dir: Dict[str, List[object]] = {
        d: [it for it in items if _module_of(it).startswith(f"{E2E_REL}/{d}/")]
        for d in ACCEPTANCE_DIRS
    }
    for d in ACCEPTANCE_DIRS:
        expected = g.EXPECTED_ACCEPTANCE_PER_DIR[d]
        assert len(per_dir[d]) == expected, (
            f"{E2E_REL}/{d}/ 实测收集到 {len(per_dir[d])} 条，常量期望 {expected} 条。"
            f"逐条：{[getattr(it, 'nodeid') for it in per_dir[d]]}"
        )
        for it in per_dir[d]:
            assert _group_markers_of(it) == {d}, (
                f"{getattr(it, 'nodeid')} 携带的组 marker 是 {sorted(_group_markers_of(it))}，"
                f"它住在 {d}/ 下，应当恰好是 {{{d!r}}}"
            )

    total = sum(len(v) for v in per_dir.values())
    assert total == g.EXPECTED_ACCEPTANCE_ITEMS, (
        f"四个 acceptance 目录合计 {total} 条，常量 EXPECTED_ACCEPTANCE_ITEMS = "
        f"{g.EXPECTED_ACCEPTANCE_ITEMS}（欠账 #14 要求两者相等）"
    )

    # 守卫脚本本身对真树退出码 0（矩阵 Expected output 第一句）。
    proc = subprocess.run(
        [sys.executable, str(GROUPS_LINT_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"`python scripts/lint_e2e_groups.py` 对真实仓库树退出码 {proc.returncode}：\n"
        + proc.stdout
        + proc.stderr
    )


# --------------------------------------------------------------------------
# Case 2：收集结果是一个划分（property / S4 / L1）
# --------------------------------------------------------------------------
def test_real_tree_collection_is_a_partition_and_counts_match() -> None:
    g = _guard()
    items = _real_items()
    assert items, "tests/e2e 一条都没收到——零用例是失败，不是通过（policy-core 第 1 条）"

    whitelist: Set[str] = set(g.UNGROUPED_E2E_MODULES)

    # (1) 划分：恰好一个组 marker，或模块在白名单里。双 marker 也红。
    strays = [
        f"{getattr(it, 'nodeid')}  markers={sorted(_group_markers_of(it))}"
        for it in items
        if not (len(_group_markers_of(it)) == 1 or Path(_module_of(it)).name in whitelist)
    ]
    assert not strays, (
        "以下 item 既不恰好带一个组 marker、其模块又不在 UNGROUPED_E2E_MODULES 里——"
        "第三种状态不存在：\n  " + "\n  ".join(strays)
    )
    doubles = [getattr(it, "nodeid") for it in items if len(_group_markers_of(it)) >= 2]
    assert not doubles, f"以下 item 同时带多个组 marker（两道门槛都会误报）：{doubles}"

    # (2) 白名单不得空转。
    contributed = {Path(_module_of(it)).name for it in items if not _group_markers_of(it)}
    dangling = sorted(whitelist - contributed)
    assert not dangling, (
        f"白名单里的模块在这次收集里一条 item 都没贡献（悬空 = 给下一个模块预开的门）：{dangling}"
    )

    # (3) 条数：baseline == 常量；acceptance == 常量；白名单 == 常量；派生总数 == 全量。
    n_baseline = sum(1 for it in items if "baseline_1b" in _markers_of(it))
    n_acceptance = sum(1 for it in items if _group_markers_of(it) & set(ACCEPTANCE_DIRS))
    n_ungrouped = sum(1 for it in items if not _group_markers_of(it))
    assert n_baseline == g.EXPECTED_BASELINE_ITEMS, (
        f"带 baseline_1b 的 item 实测 {n_baseline} 条，常量 {g.EXPECTED_BASELINE_ITEMS}（欠账 #2：实测 == 常量）"
    )
    assert n_acceptance == g.EXPECTED_ACCEPTANCE_ITEMS, (
        f"带 acceptance marker 的 item 实测 {n_acceptance} 条，常量 {g.EXPECTED_ACCEPTANCE_ITEMS}"
    )
    assert n_ungrouped == g.EXPECTED_UNGROUPED_ITEMS, (
        f"白名单模块贡献 {n_ungrouped} 条，常量 {g.EXPECTED_UNGROUPED_ITEMS}"
    )
    assert len(items) == g.EXPECTED_E2E_ITEMS, (
        f"tests/e2e 全量 {len(items)} 条，派生值 EXPECTED_E2E_ITEMS = {g.EXPECTED_E2E_ITEMS}"
    )

    # 守卫自己的划分函数对真树给零违规——它与上面的独立 oracle 必须同解。
    assert g.partition_violations(items, ungrouped_modules=whitelist) == []


# --------------------------------------------------------------------------
# Case 3：对生成的变异目录树，守卫必红（property / S6 / L1）
# --------------------------------------------------------------------------
_PYTEST_INI = (
    "[pytest]\n"
    "addopts = --strict-markers\n"
    "markers =\n"
    + "".join(f"    {m}: synthetic\n" for m in GROUP_MARKERS)
)


def _skip_module(group: str, phase: str, *, n_tests: int = 1, skipped: bool = True, extra: str = "") -> str:
    marks = [f"pytest.mark.{group}"]
    if skipped:
        marks.append(f'pytest.mark.skip(reason="激活阶段 {phase}；到期动作：删本行")')
    body = "import pytest\n\npytestmark = [" + ", ".join(marks) + "]\n\n"
    for i in range(n_tests):
        body += f"def test_{group}_{i}():\n    assert 1 == 1\n\n"
    return body + extra


def _base_spec() -> Dict[str, str]:
    spec: Dict[str, str] = {
        "pytest.ini": _PYTEST_INI,
        f"{E2E_REL}/conftest.py": "import pytest\n\n\ndef helper_in_conftest():\n    return 1\n",
        f"{E2E_REL}/helpers.py": "def shared_helper():\n    return 1\n",
        f"{E2E_REL}/test_harness_smoke.py": "def test_smoke():\n    assert True\n",
        f"{E2E_REL}/baseline_1b/test_b.py": (
            "import pytest\n\npytestmark = pytest.mark.baseline_1b\n\n"
            "def test_b0():\n    assert True\n\n\ndef test_b1():\n    assert True\n"
        ),
    }
    for d in ACCEPTANCE_DIRS:
        spec[f"{E2E_REL}/{d}/test_{d}.py"] = _skip_module(d, PHASE_TOKEN_FOR_DIR[d])
    return spec


BASE_EXPECTED = dict(
    expected_baseline=2,
    expected_per_dir={d: 1 for d in ACCEPTANCE_DIRS},
    expected_ungrouped=1,
    ungrouped_modules={"test_harness_smoke.py"},
)


def _write_tree(root: Path, spec: Dict[str, str]) -> None:
    for rel, content in spec.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


Mutation = Callable[[Dict[str, str]], None]


def _m_one_fewer(spec: Dict[str, str]) -> None:
    del spec[f"{E2E_REL}/acceptance_p3/test_acceptance_p3.py"]


def _m_one_more(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/acceptance_p3/test_acceptance_p3.py"] = _skip_module("acceptance_p3", "P3", n_tests=2)


def _m_wrong_marker(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/acceptance_p3/test_acceptance_p3.py"] = _skip_module("acceptance_4a4", "P3")


def _m_file_in_wrong_dir(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/acceptance_4a4/test_strayed_p3.py"] = _skip_module("acceptance_p3", "P3")


def _m_skip_missing(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/acceptance_p3/test_acceptance_p3.py"] = _skip_module("acceptance_p3", "P3", skipped=False)


def _m_double_marker(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/baseline_1b/test_b.py"] = (
        "import pytest\n\npytestmark = [pytest.mark.baseline_1b, pytest.mark.acceptance_2a]\n\n"
        "def test_b0():\n    assert True\n\n\ndef test_b1():\n    assert True\n"
    )


def _m_dangling_whitelist(spec: Dict[str, str]) -> None:
    del spec[f"{E2E_REL}/test_harness_smoke.py"]


def _m_skip_in_baseline_body(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/baseline_1b/test_b.py"] = (
        "import pytest\n\npytestmark = pytest.mark.baseline_1b\n\n"
        "def test_b0():\n    try:\n        x = 1\n    except Exception as e:\n"
        "        pytest.skip(f'flaky today: {e}')\n    assert x == 1\n\n\n"
        "def test_b1():\n    assert True\n"
    )


def _m_skip_in_conftest_fixture(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/conftest.py"] = (
        "import pytest\n\n\n@pytest.fixture(scope='session')\ndef live_server():\n"
        "    try:\n        proc = object()\n    except Exception as e:\n"
        "        pytest.skip(f'e2e server unavailable: {e}')\n    yield proc\n"
    )


def _m_reason_without_phase(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/acceptance_p3/test_acceptance_p3.py"] = (
        "import pytest\n\npytestmark = [pytest.mark.acceptance_p3, pytest.mark.skip(reason='later')]\n\n"
        "def test_acceptance_p3_0():\n    assert True\n"
    )


def _m_function_level_skip(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/acceptance_p3/test_acceptance_p3.py"] = (
        "import pytest\n\npytestmark = pytest.mark.acceptance_p3\n\n"
        "@pytest.mark.skip(reason='激活阶段 P3；到期动作：删本行')\n"
        "def test_acceptance_p3_0():\n    assert True\n"
    )


def _m_collect_ignore(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/acceptance_2a/deg_helpers_2a.py"] = "collect_ignore = ['test_acceptance_2a.py']\n"


def _m_unregistered_root_module(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/test_nobody_owns_me.py"] = "def test_orphan():\n    assert True\n"


MUTANTS: List[Tuple[str, Mutation, Tuple[str, ...]]] = [
    ("one-fewer", _m_one_fewer, ("acceptance_p3",)),
    ("one-more", _m_one_more, ("acceptance_p3",)),
    ("wrong-marker", _m_wrong_marker, ("test_acceptance_p3.py",)),
    ("file-in-wrong-dir", _m_file_in_wrong_dir, ("test_strayed_p3.py",)),
    ("skip-missing", _m_skip_missing, ("test_acceptance_p3.py", "skip")),
    ("double-marker", _m_double_marker, ("test_b.py",)),
    ("dangling-whitelist", _m_dangling_whitelist, ("test_harness_smoke.py",)),
    ("skip-in-baseline-body", _m_skip_in_baseline_body, ("test_b.py:", "skip")),
    ("skip-in-conftest-fixture", _m_skip_in_conftest_fixture, ("conftest.py:", "skip")),
    ("reason-without-phase", _m_reason_without_phase, ("test_acceptance_p3.py", "reason")),
    ("function-level-skip", _m_function_level_skip, ("test_acceptance_p3.py", "pytestmark")),
    ("collect-ignore", _m_collect_ignore, ("deg_helpers_2a.py", "collect_ignore")),
    ("unregistered-root-module", _m_unregistered_root_module, ("test_nobody_owns_me.py",)),
]


def test_guard_is_green_on_a_legal_synthetic_tree(tmp_path: Path) -> None:
    """对照支：合法树 ⇒ 零违规。没有这一支，一个「永远红」的守卫在下面全部变异上也全绿。"""
    g = _guard()
    _write_tree(tmp_path, _base_spec())
    violations = g.check_tree(tmp_path, **BASE_EXPECTED)
    assert violations == [], "合法的合成树被守卫判红：\n  " + "\n  ".join(violations)


@pytest.mark.parametrize("name,mutate,tokens", MUTANTS, ids=[m[0] for m in MUTANTS])
def test_guard_is_red_on_every_mutant_tree(
    tmp_path: Path, name: str, mutate: Mutation, tokens: Tuple[str, ...]
) -> None:
    """每一种变异都让守卫非空返回，且消息**点名**偏差项（文件 / 目录 / 关键字）。

    `return []` 式守卫（永远通过）在任一变异上红——本条正是为了杀掉那个实现。
    「只数文件个数不看 marker」在 wrong-marker / double-marker 上红；
    「不检查 skip 标记」在 skip-missing / function-level-skip 上红；
    「只扫 Module.body」在 skip-in-baseline-body / skip-in-conftest-fixture 上红。
    """
    g = _guard()
    spec = _base_spec()
    mutate(spec)
    _write_tree(tmp_path, spec)
    violations = g.check_tree(tmp_path, **BASE_EXPECTED)
    assert violations, f"变异 {name} 没有让守卫变红——守卫对这类破坏是盲的"
    joined = "\n".join(violations)
    for token in tokens:
        assert token in joined, (
            f"变异 {name} 让守卫红了，但消息没有点名 {token!r}，读的人无从知道错在哪：\n{joined}"
        )


# --------------------------------------------------------------------------
# Case 4：skip 轴的静态性质（property / S4 / L1）——本文件是守卫的独立 oracle
# --------------------------------------------------------------------------
_SKIP_CALLS = {"skip", "importorskip", "xfail"}
_SKIP_MARKS = {"skip", "skipif", "xfail"}


def _dotted(node: ast.AST) -> str:
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _skip_constructs(path: Path) -> List[str]:
    """`ast.walk` 整个模块：凡解析为 pytest.skip/importorskip/xfail 调用、或 pytest.mark.skip/skipif/xfail 属性链，一律计入。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _dotted(node.func) in {f"pytest.{c}" for c in _SKIP_CALLS}:
            hits.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}  {_dotted(node.func)}(")
        elif isinstance(node, ast.Attribute) and _dotted(node) in {f"pytest.mark.{m}" for m in _SKIP_MARKS}:
            hits.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}  {_dotted(node)}")
    return hits


def _module_level_skip_marks(path: Path) -> List[ast.Call]:
    """模块级 `pytestmark = [...]` 里的 `pytest.mark.skip(...)` 调用。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls: List[ast.Call] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            continue
        values = node.value.elts if isinstance(node.value, (ast.List, ast.Tuple)) else [node.value]
        for v in values:
            if isinstance(v, ast.Call) and _dotted(v.func) == "pytest.mark.skip":
                calls.append(v)
    return calls


def _domain_r_files() -> List[Path]:
    files = [E2E_DIR / "conftest.py", E2E_DIR / "helpers.py"]
    files += sorted((E2E_DIR / "baseline_1b").rglob("*.py"))
    return [f for f in files if f.is_file()]


def test_baseline_reachable_chain_has_zero_skip_constructs() -> None:
    """条件 1 ＋ 5：域 R（conftest / helpers / baseline_1b/**）里零 skip 构造，函数体与异常处理器一并计入。"""
    hits: List[str] = []
    for f in _domain_r_files():
        hits += _skip_constructs(f)
    assert not hits, (
        "baseline_1b 的收集可达链上出现了 skip 构造——每一条都是把计入门槛的用例悄悄摘掉：\n  "
        + "\n  ".join(hits)
    )
    # 守卫自己的静态检查与本 oracle 同解。
    assert _guard().skip_axis_violations(REPO_ROOT) == []


def test_every_acceptance_module_skips_only_via_module_level_pytestmark_with_phase_reason() -> None:
    """条件 2 ＋ 3 ＋ 4：四个 acceptance 目录里每个 `test_*.py` 恰好一个模块级 skip、带激活阶段 reason；目录内无 collect_ignore。"""
    problems: List[str] = []
    seen_any = False
    for d in ACCEPTANCE_DIRS:
        for f in sorted((E2E_DIR / d).rglob("*.py")):
            text = f.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(f))
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id in {"collect_ignore", "collect_ignore_glob"} for t in node.targets
                ):
                    problems.append(f"{f.relative_to(REPO_ROOT)}:{node.lineno}  collect_ignore（比 skip 更隐蔽的消失方式）")
            if not f.name.startswith("test_"):
                if _skip_constructs(f):
                    problems.append(f"{f.relative_to(REPO_ROOT)}: 非用例模块里出现 skip 构造")
                continue
            seen_any = True
            marks = _module_level_skip_marks(f)
            if len(marks) != 1:
                problems.append(f"{f.relative_to(REPO_ROOT)}: 模块级 pytestmark 里的 pytest.mark.skip 有 {len(marks)} 个，应恰好 1 个")
                continue
            reason = next((kw.value for kw in marks[0].keywords if kw.arg == "reason"), None)
            reason_text = reason.value if isinstance(reason, ast.Constant) and isinstance(reason.value, str) else ""
            if not reason_text.strip():
                problems.append(f"{f.relative_to(REPO_ROOT)}: skip 没有非空 reason")
            elif PHASE_TOKEN_FOR_DIR[d] not in reason_text:
                problems.append(
                    f"{f.relative_to(REPO_ROOT)}: skip reason 没有点名本组的激活阶段 {PHASE_TOKEN_FOR_DIR[d]!r}：{reason_text!r}"
                )
            elif not PHASE_TOKEN_RE.search(reason_text):
                problems.append(f"{f.relative_to(REPO_ROOT)}: reason 不含任何激活阶段标识：{reason_text!r}")
            # 模块级那一个之外，整个模块不得再有任何 skip 构造（函数级 skip 挪到模块级是条件 2 的反例）。
            others = [h for h in _skip_constructs(f) if not h.endswith(f":{marks[0].lineno}  pytest.mark.skip")]
            others = [h for h in others if f":{marks[0].lineno}  " not in h]
            if others:
                problems.append(f"{f.relative_to(REPO_ROOT)}: 模块级 pytestmark 之外还有 skip 构造：{others}")
    assert seen_any, "四个 acceptance 目录里一个 test_*.py 都没有——14 条 skip 用例是 WI-17 的交付"
    assert not problems, "skip 轴静态性质被破坏：\n  " + "\n  ".join(problems)


# --------------------------------------------------------------------------
# Case 5：四个 acceptance 组正向选中后全部 skip（guard / S3 / L1）
# --------------------------------------------------------------------------
def test_positive_selection_of_acceptance_groups_yields_exactly_the_skipped_count() -> None:
    """`-m "acceptance_4b1 or …"` ⇒ 退出码 0、skipped == EXPECTED_ACCEPTANCE_ITEMS、passed == failed == errors == 0。

    `errors == 0` 是核心：一条 skip 用例里的 NameError / 不存在的 import / 写错的 fixture 名，
    只有到期解开那天才第一次暴露——本条让它今天就暴露。skip 的判定发生在收集之后、用例体之前，
    不起服务、不起浏览器。
    """
    g = _guard()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            E2E_REL,
            "-m",
            " or ".join(ACCEPTANCE_DIRS),
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    out = proc.stdout + proc.stderr
    counts = _parse_summary_tokens(out)
    assert proc.returncode == 0, f"正选四个 acceptance 组时退出码 {proc.returncode}：\n{out}"
    assert counts["errors"] == 0, f"有 collection error——某条 skip 用例 import 不进来：\n{out}"
    assert counts["passed"] == 0, f"有 acceptance 用例真的跑起来并通过了（skip 被解开而阶段未到？）：\n{out}"
    assert counts["failed"] == 0, f"有 acceptance 用例真的跑起来并失败了：\n{out}"
    assert counts["skipped"] == g.EXPECTED_ACCEPTANCE_ITEMS, (
        f"skipped == {counts['skipped']}，期望 EXPECTED_ACCEPTANCE_ITEMS == {g.EXPECTED_ACCEPTANCE_ITEMS}：\n{out}"
    )


# --------------------------------------------------------------------------
# Case 6：四个 acceptance 目录与共享断言模块全在 suite_hash 覆盖之外（guard / S3 / L1）
# --------------------------------------------------------------------------
def test_acceptance_dirs_and_shared_deg_module_are_outside_suite_hash() -> None:
    covered = [c.rstrip("/") for c in covered_paths(hash_command_block(read_soak_log()))]

    def is_covered(rel: str) -> bool:
        return any(c == rel or rel.startswith(c + "/") or c.startswith(rel + "/") for c in covered)

    leaked = [f"{E2E_REL}/{d}" for d in ACCEPTANCE_DIRS if is_covered(f"{E2E_REL}/{d}")]
    assert not leaked, f"这些 acceptance 目录落进了 suite_hash 覆盖面（改一条 DEG 断言就清零 soak）：{leaked}"
    shared_rel = SHARED_DEG_MODULE_PATH.relative_to(REPO_ROOT).as_posix()
    assert not is_covered(shared_rel), (
        f"共享断言模块 {shared_rel} 在 suite_hash 覆盖面内——它只被未激活的组依赖，不该清零 soak"
    )


# --------------------------------------------------------------------------
# Case 7：acceptance_p3 与 acceptance_4a4 的断言主体是同一个函数集合（property / S4 / L1）
# --------------------------------------------------------------------------
def _cross_module_calls(path: Path) -> Dict[str, str]:
    """{被调用的跨模块函数名: 它 import 自哪个模块}。只认 `from X import name` 且 `name(...)` 真的被调用。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in EXCLUDED_IMPORT_PREFIXES:
                continue
            for alias in node.names:
                imported[alias.asname or alias.name] = node.module
    called: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called.add(node.func.id)
    return {n: m for n, m in imported.items() if n in called}


def _testid_table_keys(path: Path) -> Set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "DEG_TESTIDS" for t in node.targets):
            assert isinstance(node.value, ast.Dict), f"{path.name} 的 DEG_TESTIDS 不是字典字面量"
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    raise AssertionError(f"{path.relative_to(REPO_ROOT)} 没有模块级 `DEG_TESTIDS = {{...}}`")


def _resolve_bare_module(name: str) -> Path:
    for root in (E2E_DIR, REPO_ROOT / "tests" / "fixtures", REPO_ROOT / "tests"):
        cand = root / f"{name}.py"
        if cand.is_file():
            return cand
    raise AssertionError(f"解析不到共享模块 {name!r}（搜索了 tests/e2e、tests/fixtures、tests）")


def test_p3_and_4a4_share_the_same_assertion_body_function_set() -> None:
    p3_files = sorted((E2E_DIR / "acceptance_p3").glob("test_*.py"))
    a4_files = sorted((E2E_DIR / "acceptance_4a4").glob("test_*.py"))
    assert p3_files and a4_files, "两个 DEG 目录里都得有用例模块（WI-17 交付）"

    P: Dict[str, str] = {}
    for f in p3_files:
        P.update(_cross_module_calls(f))
    Q: Dict[str, str] = {}
    for f in a4_files:
        Q.update(_cross_module_calls(f))

    # (1) 集合相等，且非空。相等而不是「交集非空」：交集非空对「各自还有一半私有断言」是盲的。
    assert set(P), "acceptance_p3 没有调用任何跨模块函数——断言主体没有抽出去"
    assert set(P) == set(Q), (
        f"两组的跨模块调用集不相等：只在 p3 的 {sorted(set(P) - set(Q))}，只在 4a4 的 {sorted(set(Q) - set(P))}"
    )

    # (2) 每个共享函数在两组里 import 自同一个模块，且所有 m(f) 相同。
    sources = {P[f] for f in P} | {Q[f] for f in Q}
    for f in P:
        assert P[f] == Q[f], f"{f} 在 p3 来自 {P[f]!r}，在 4a4 来自 {Q[f]!r}——两份同名函数"
    assert sources == {SHARED_DEG_MODULE}, (
        f"共享断言主体应当只来自 {SHARED_DEG_MODULE!r} 一个模块，实际来自 {sorted(sources)}"
    )

    # (3) 共享模块位于两个 acceptance 目录之外。
    shared = _resolve_bare_module(SHARED_DEG_MODULE)
    assert shared == SHARED_DEG_MODULE_PATH, f"共享模块解析到 {shared}，期望 {SHARED_DEG_MODULE_PATH}"
    for d in ACCEPTANCE_DIRS:
        assert (E2E_DIR / d) not in shared.parents, f"共享模块落进了 {d}/"

    # (4) 两组 testid 映射表的键集合相同——值不同是设计使然，键不同就是语义漂移。
    assert len(p3_files) == 1 and len(a4_files) == 1, (
        "DEG 四条应各自集中在一个模块里（p3 一个、4a4 一个），映射表一个目录一份"
    )
    p3_keys = _testid_table_keys(p3_files[0])
    a4_keys = _testid_table_keys(a4_files[0])
    assert p3_keys == a4_keys, (
        f"testid 映射表的键集合不同：只在 p3 的 {sorted(p3_keys - a4_keys)}，只在 4a4 的 {sorted(a4_keys - p3_keys)}"
    )
    assert p3_keys, "映射表是空的"

    # (5) 每个共享函数都有 e2e 之外的消费者：至少被 tests/unit 下某个文件点名（否则它在解 skip 之前是死代码）。
    unit_sources = "\n".join(p.read_text(encoding="utf-8") for p in sorted(UNIT_DIR.glob("*.py")) if p != Path(__file__))
    unreferenced = sorted(f for f in P if not re.search(rf"\b{re.escape(f)}\b", unit_sources))
    assert not unreferenced, (
        f"这些共享函数没有任何 tests/unit 下的用例点名它们，在 skip 解开之前没人跑过：{unreferenced}"
    )


# --------------------------------------------------------------------------
# 定向破坏实录（实现落地后回填；只增文本，不改上面的断言行）
# --------------------------------------------------------------------------
SABOTAGE_LOG = """
（实现落地后回填）
"""


# --------------------------------------------------------------------------
# 定向破坏实录（WI-17，2026-09-04）
#
# 本块是**追加**的，不是就地回填：本文件已入红收据 `009-WI-17`（lane unit，
# kind=assertion-failure），按行冻结，改动任何既有行都会把「先写测试」的证据变成一次
# 无法核对的声明。因此上面那个占位 `SABOTAGE_LOG` 原样保留，这里重新绑定同名常量
# ——Python 取最后一次绑定，读到的就是下面这份实录。
#
# 破坏一律在仓库副本上做（scratchpad 下 rsync 一份完整树，排除 .git/.venv/books），
# 用 `python scripts/lint_e2e_groups.py <副本根>` 打靶；真实树全程未改，
# `git diff --quiet -- src/` 通过。每次破坏后都还原并 `diff -q` 与真实树逐字节比对，
# 再重跑守卫确认回到全绿。
# --------------------------------------------------------------------------
SABOTAGE_LOG = """
副本基线（未破坏）：
  分组守卫：收集 89 条；baseline_1b 65/65；acceptance_4b1 8/8；acceptance_p3 4/4；
  acceptance_4a4 4/4；acceptance_2a 1/1；白名单 7/7；派生总数 89
  分组守卫通过：划分律成立、条数与常量相等、skip 轴静态性质成立。  rc=0

破坏 1 —— 删掉一条 skip 形式用例
  破坏点：移走 tests/e2e/acceptance_4b1/test_w5b_recolor_keeps_id.py（该模块 3 条 item）。
  结果：rc=1。摘要行降为「acceptance_4b1 5/8」，并报：
    [条数] tests/e2e/acceptance_4b1/ 实测 5 条，期望 8 条
      （少了 = 有人删了一条 skip 用例；多了 = 常量没跟着改，改常量要写理由）
  ——目录名与「实测/期望」两个数都在消息里，定位不用猜。
  还原核验：移回原路径，`diff -q` 与真实树一致；重跑 rc=0，8/8 恢复。

破坏 2 —— 往 baseline_1b 的用例函数体里塞一条 skip
  破坏点：在 tests/e2e/baseline_1b/test_kernel_overlay_geometry.py 第 351 行、
  函数 test_k3a_overlay_is_fixed_and_has_no_containing_block_ancestor 的**函数体第一行**
  插入 `pytest.skip("SABOTAGE：临时掏空 baseline")`。选函数体而不是模块顶层，正是为了打
  文件头点名的那个洞：只扫 Module.body 的写法看不见它，收集数还是 89，门槛却已被掏空。
  结果：rc=1（注意条数轴全绿 —— 65/65、89 条，只有 skip 轴响），报：
    [skip 轴·域 R] tests/e2e/baseline_1b/test_kernel_overlay_geometry.py:351
      pytest.skip("SABOTAGE：临时掏空 baseline")
      baseline_1b 的收集可达链上不得有任何 skip 构造（函数体、fixture 体、异常处理器里的
      一并计入）——它会把计入门槛的用例悄悄摘掉
  ——文件名与行号都在消息里。
  还原核验：copy 回备份，`diff -q` 与真实树一致；重跑 rc=0。

破坏 3 —— 让一个白名单条目贡献零条 item
  破坏点：把 tests/e2e/test_harness_smoke.py 改名为 test_harness_smoke_renamed_sabotage.py
  （文件仍在、item 仍被收集，只是白名单里那个名字对不上了）。
  结果：rc=1，三处违规同时响，互相印证：
    [划分律] tests/e2e/test_harness_smoke_renamed_sabotage.py::test_playwright_reaches_epubjs_iframe_content[chromium]
      没有组 marker，且模块不在 UNGROUPED_E2E_MODULES 白名单里——第三种状态不存在
    [白名单] test_harness_smoke.py 在本次收集里一条 item 都没贡献
      （悬空条目 = 给下一个没人管的模块预开的门）
    [条数] 白名单模块实测贡献 6 条，期望 EXPECTED_UNGROUPED_ITEMS = 7
  ——悬空白名单这一条正是要证的那条：名字留在清单里、却不再对应任何 item 时会红。
  还原核验：改回原名，`diff -q` 与真实树一致；重跑 rc=0，白名单 7/7。

结论：条数轴、skip 轴、划分律 ＋ 白名单不空转三条轴各自被单独打红过，失败消息都点到了
文件/目录与期望值。三次破坏全部还原并逐字节核验，真实树 `git status --short` 只剩本次
WI-17 的预期文件，`git diff --quiet -- src/` 通过。
"""
