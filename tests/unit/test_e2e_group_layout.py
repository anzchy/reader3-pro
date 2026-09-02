"""WI-1：marker 家族注册 + `tests/e2e/` 分组目录布局的两个前置条件。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` 的 `## WI-1:` 一节。
被测对象是 **pytest 的配置行为**，不是 toml 的内容——所以两条用例都真的起一个
`--collect-only` 子进程，断的是收集器怎么反应。放 e2e lane 只会把一次 chromium
启动的成本买给一条配置断言，故落 unit lane。

**子进程一律带 `--collect-only`**：本文件不执行任何 e2e 用例，因此不会起服务、
不会拉浏览器，也绝不会碰开发者真实的 `books/`（`tests/conftest.py` 顶部那条
`shutil.rmtree()` 警告说的就是这个）。

**本 WI 不断的东西**：`EXPECTED_BASELINE_ITEMS`(61) 与 `EXPECTED_ACCEPTANCE_ITEMS`(14)
这两段。矩阵第二条用例的 Expected output 写的是三段等式，但 61 条 baseline 和 14 条
acceptance 的用例文件在 WI-1 阶段一个都还没写，那段等式此刻不可能绿。三段等式整体
由 **WI-17 的划分律用例**承担；WI-1 只记录它的两个前置条件——marker 拼错必须响亮，
目录布局不能打断既有 import——外加**从没被记录过的根目录基线**
（`EXPECTED_UNGROUPED_ITEMS`，任务书 §0.5「需要回写」第 5 条）。

同理，矩阵第一条用例的对照支原文含「`-m baseline_1b` 收集条数 > 0」。五个组目录在
WI-1 结束时还是空的，这半句同样移交 WI-17；这里保留的是它可判定的那一半——**已注册的
marker 不得被 `--strict-markers` 拒绝**，它在「只注册了拼错的那个」或「漏注册一个」时
照样红。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GROUPS_LINT_PATH = REPO_ROOT / "scripts" / "lint_e2e_groups.py"
E2E_DIR = REPO_ROOT / "tests" / "e2e"

# 五个组 marker 与它们的目录一一对应（任务书 §0.5 的表是唯一定义处，此处只列名字）。
GROUP_MARKERS = [
    "baseline_1b",
    "acceptance_4b1",
    "acceptance_p3",
    "acceptance_4a4",
    "acceptance_2a",
]

# pytest 的退出码：5 = 一条都没收到。整个 WI-1 要抓的就是「拼错的 marker 选中空集
# 然后安静地通过」，所以「非零」还不够——必须不是 5，也不是「无人 deselect」的 0。
NO_TESTS_COLLECTED = 5


def _collect_e2e(*extra_args: str) -> subprocess.CompletedProcess:
    """在仓库根跑一次只读收集，返回退出码与合并后的输出。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/e2e", "--collect-only", "-q", *extra_args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return proc


def _output(proc: subprocess.CompletedProcess) -> str:
    return proc.stdout + proc.stderr


def _load_groups_lint() -> ModuleType:
    """从路径加载 `scripts/lint_e2e_groups.py`（脚本不是包，照 `scripts/` 下的先例）。

    这里先 `assert` 存在再加载，是刻意的：这几个数字**只允许在那一个文件里定义/派生
    一次**（任务书 §0.5），所以「定义处不存在」本身就是一条规格失败，不该退化成一个
    看不出所以然的 ImportError。
    """
    assert GROUPS_LINT_PATH.exists(), (
        f"{GROUPS_LINT_PATH} 不存在。分组条数的常量只允许在这一个文件里定义/派生一次"
        "（任务书 §0.5），验收条、守卫脚本、台账产物一律 import。"
    )
    spec = importlib.util.spec_from_file_location("lint_e2e_groups_under_test", GROUPS_LINT_PATH)
    assert spec is not None and spec.loader is not None, f"无法从 {GROUPS_LINT_PATH} 加载"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_typo_marker_selector_fails_collection_instead_of_selecting_zero() -> None:
    """拼错的 marker 必须让收集**响亮地失败**，而不是选中零条再以退出码 0 通过。

    点名的失败模式：policy-core 完成门槛第 1 条「lane discovered zero tests is a
    failure」。`-m baseline_1b_typo` 在不加 `--strict-markers` 时的输出是
    「no tests collected (7 deselected)」——一次 soak 数空集就是这么发生的。
    """
    proc = _collect_e2e("-m", "baseline_1b_typo")
    out = _output(proc)

    assert proc.returncode != 0, (
        "拼错的 marker 让 `--collect-only` 以退出码 0 通过了。输出：\n" + out
    )
    assert proc.returncode != NO_TESTS_COLLECTED, (
        "拼错的 marker 只是「选中空集」（退出码 5），没有被拒绝——"
        "这正是 soak 数空集的发生方式，不是响亮失败。输出：\n" + out
    )
    assert "baseline_1b_typo" in out, (
        "失败信息里没有点名那个拼错的 marker，读日志的人无从知道错在哪。输出：\n" + out
    )


@pytest.mark.parametrize("marker", GROUP_MARKERS)
def test_registered_group_marker_is_accepted_by_strict_markers(marker: str) -> None:
    """对照支：五个已注册的组 marker 都不得被 `--strict-markers` 拒绝。

    它在「只注册了拼错的那个」「五个里漏注册一个」时红。
    「收集条数 > 0」那一半移交 WI-17——组目录在 WI-1 结束时还是空的。
    """
    proc = _collect_e2e("-m", marker)
    out = _output(proc)

    assert "not found in `markers` configuration option" not in out, (
        f"已注册的组 marker `{marker}` 被 --strict-markers 拒绝了，说明它没进 "
        f"[tool.pytest.ini_options].markers。输出：\n{out}"
    )
    assert proc.returncode in (0, NO_TESTS_COLLECTED), (
        f"`-m {marker}` 的退出码是 {proc.returncode}，既不是「收到了」也不是"
        f"「组目录还空着」。输出：\n{out}"
    )


def test_group_subdirs_do_not_break_bare_conftest_imports() -> None:
    """建了五个分组子目录之后，`tests/e2e` 仍能一次收齐，裸 import 仍可解析。

    点名的失败模式：`test_harness_smoke.py` 用的是 `from conftest import BOOK_ID`
    （裸模块名），它依赖 pytest 的 prepend 模式把「第一个不含 `__init__.py` 的上层
    目录」插进 `sys.path`。**在 `tests/e2e/` 自身加 `__init__.py` 会把插入点上移到
    `tests/`，那两个裸 import 当场 ImportError**。WI-1 的验收原文写的是「每个目录有
    `__init__.py` **或**明确的 `conftest.py` 归属」——两种写法在这里不等价，这条用例
    就是那个不等价的记录。`test_testid_dom_uniqueness.py` 是要保护的第二个消费方。
    """
    groups = _load_groups_lint()

    # 五个组目录必须存在，且四个 acceptance 目录在 baseline_1b/ 之外——同目录会让它们
    # 被迁移计划 §7 的 suite_hash 覆盖，改一条 DEG 断言就把 soak 计数清零。
    for marker in GROUP_MARKERS:
        group_dir = E2E_DIR / marker
        assert group_dir.is_dir(), f"分组目录缺失：{group_dir}"
        assert group_dir.parent == E2E_DIR, (
            f"{group_dir} 不是 tests/e2e 的直接子目录；acceptance 组一旦落进 "
            "baseline_1b/ 就会被 suite_hash 覆盖"
        )

    # `tests/e2e/` 自身与任何组目录都不得有 `__init__.py`。
    for candidate in [E2E_DIR, *(E2E_DIR / m for m in GROUP_MARKERS)]:
        assert not (candidate / "__init__.py").exists(), (
            f"{candidate}/__init__.py 会把 sys.path 插入点上移，"
            "`from conftest import BOOK_ID` 当场 ImportError"
        )

    proc = _collect_e2e()
    out = _output(proc)

    assert "ImportError" not in out and "ModuleNotFoundError" not in out, (
        "收集期出现了 import 失败：\n" + out
    )
    assert proc.returncode == 0, f"`tests/e2e --collect-only` 退出码 {proc.returncode}：\n{out}"

    # 白名单模块在**同一次收集**里贡献的 item 数。常量从唯一定义处 import，不写字面量。
    # 另外两段（EXPECTED_BASELINE_ITEMS / EXPECTED_ACCEPTANCE_ITEMS）由 WI-17 的划分律
    # 用例承担：那 61 + 14 条用例文件在 WI-1 阶段一条都还没写。
    per_module: dict[str, int] = {name: 0 for name in groups.UNGROUPED_E2E_MODULES}
    for line in out.splitlines():
        head = line.split("::", 1)[0].strip()
        if "::" not in line or not head.startswith("tests/e2e/"):
            continue
        name = Path(head).name
        if name in per_module:
            per_module[name] += 1

    assert sum(per_module.values()) == groups.EXPECTED_UNGROUPED_ITEMS, (
        f"根目录白名单模块贡献了 {sum(per_module.values())} 条，期望 "
        f"{groups.EXPECTED_UNGROUPED_ITEMS} 条。逐模块：{per_module}\n收集输出：\n{out}"
    )


def test_mistyped_marker_decorator_is_rejected_by_strict_markers(tmp_path: Path) -> None:
    """`--strict-markers` 的那一半：**写在装饰器上**的拼错 marker 必须让收集失败。

    这条是实现期补的（红收据之后新增，不改任何已记录的断言）。补它的理由：一个拼错的
    `@pytest.mark.baselinne_1b` 不会报错，只是让那条用例**不属于任何组**——于是
    `-m baseline_1b` 少收一条而没人知道。`-m` 表达式那一半由本文件第一条用例覆盖
    （靠 `tests/conftest.py` 的 `pytest_configure` 校验），装饰器这一半只有
    `addopts = "--strict-markers"` 能覆盖。没有这条，把 `--strict-markers` 从
    `addopts` 里删掉，全仓仍然绿。

    被测模块写在 `tmp_path` 下（不在仓库里，收集器不会把它带进任何 lane），用
    `-c pyproject.toml` 显式指定配置文件，好让仓库的 `addopts` / `markers` 生效。
    """
    probe = tmp_path / "test_strict_marker_probe.py"
    probe.write_text(
        "import pytest\n\n\n@pytest.mark.baseline_1b_typo\ndef test_probe():\n    assert True\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(REPO_ROOT / "pyproject.toml"),
            "--collect-only",
            "-q",
            str(probe),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    out = proc.stdout + proc.stderr

    assert proc.returncode != 0, (
        "装饰器上拼错的 marker 被静默接受了——那条用例会不属于任何组，"
        "而 `-m baseline_1b` 只是少收一条，没有任何信号。输出：\n" + out
    )
    assert "not found in `markers` configuration option" in out, (
        "收集失败了，但不是 --strict-markers 报的。输出：\n" + out
    )
