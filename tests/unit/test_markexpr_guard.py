"""`-m` 表达式里的未知 marker 必须响，**括号不能把它藏起来**。

`tests/conftest.py` 的 `pytest_configure` 是 `--strict-markers` 的另一半：后者只校验
**贴在用例上**的 marker，前者校验 `-m` 表达式里的名字。这一半的价值全在「空集不是绿」
——一条 `-m baseline_1b_typo` 选中零条用例、退出 5，输出读起来和「这一组本来就是空的」
一模一样，而那个数会被抄进 soak 台账。

**本文件存在的直接理由（2026-09-05 审计 · HIGH）**：原实现在取标识符之前先用
`re.compile(r"\\([^()]*\\)")` 把**每一对括号连同内容**都抹掉。那条正则本意是抹掉
pytest 8 的 marker 关键字实参（`-m "mark(name='x')"` 里的 `name='x'` 不是 marker 名），
但它分不清「实参表」与「布尔分组」：

    -m "(baseline_1b_typo)"     → 整个表达式被抹成空 → 零个标识符 → 校验通过
    -m "not (typo)"             → 同上
    -m "a and (typo or b)"      → `a and` 幸存，括号里的 typo 连同 b 一起消失

于是「加一对括号」就是这道闸的通行证，而加括号恰恰是人写复合表达式时的本能。三条形态
逐条钉在下面的参数表里。

**测的是真 `Config`，不是替身。** 用例通过 `pytestconfig` 拿到本次运行**真实的**
`pytest.Config`（`getini("markers")` 里是 pyproject 里那六个 marker 加上各插件在自己
`pytest_configure` 里注册的那些），只把 `option.markexpr` 换掉，再直接调被测钩子。
自造一个 fake config 的话，「已注册 marker 从哪来」这半条契约就测不到了。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_CONFTEST = REPO_ROOT / "tests" / "conftest.py"


def _load_root_conftest():
    """按绝对路径加载 `tests/conftest.py`。

    不能 `import conftest`：conftest 不在 `sys.path` 上，而且本仓库有三个同名文件
    （`tests/`、`tests/unit/`、`tests/e2e/`）。按路径加载消除歧义——与
    `test_e2e_server_env_isolation.py` 同款理由。
    """
    spec = importlib.util.spec_from_file_location("_root_conftest_under_test", ROOT_CONFTEST)
    assert spec is not None and spec.loader is not None, f"无法从 {ROOT_CONFTEST} 加载"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_root_conftest()


def _configure(mod, config: pytest.Config, markexpr: str) -> None:
    """用真实 config、指定的 `-m` 表达式跑一次被测钩子。"""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config.option, "markexpr", markexpr, raising=False)
        mod.pytest_configure(config)


# --------------------------------------------------------------------------- 绕过

BYPASSES = [
    "(baseline_1b_typo)",
    "not (typo)",
    "a and (typo or b)",
    "(not slow) and (typo)",
    "((typo))",
    "not (slow and (typo or slow))",
]


@pytest.mark.parametrize("markexpr", BYPASSES)
def test_grouping_parentheses_do_not_hide_an_unknown_marker(mod, pytestconfig, markexpr):
    """审计 HIGH：分组括号里的未知 marker 必须照样被点名。

    断言里不只要求「抛了」，还要求**报错文案点到那个名字**：一句泛泛的
    「表达式有问题」会让人去数括号，而错的是拼写。
    """
    with pytest.raises(pytest.UsageError) as excinfo:
        _configure(mod, pytestconfig, markexpr)
    message = str(excinfo.value)
    assert "typo" in message, (markexpr, message)


def test_the_bypass_costs_a_silently_empty_run(mod, pytestconfig):
    """把上面那组的后果写成一条独立断言：`-m "(baseline_1b_typo)"` 与 `-m baseline_1b_typo`
    必须是**同一个**结果。裸名字那条今天就是红的（旧实现也拦得住），加了括号那条曾经是绿的
    ——两者出现分歧，正是「加一对括号即通行证」这个缺陷的定义。
    """
    for markexpr in ("baseline_1b_typo", "(baseline_1b_typo)"):
        with pytest.raises(pytest.UsageError) as excinfo:
            _configure(mod, pytestconfig, markexpr)
        assert "baseline_1b_typo" in str(excinfo.value), markexpr


# --------------------------------------------------------------------------- 合规形态


@pytest.mark.parametrize(
    "markexpr",
    [
        "baseline_1b",
        "not slow",
        "baseline_1b or acceptance_p3",
        "(baseline_1b or acceptance_4b1) and not slow",
        "not (slow)",
        "not (baseline_1b and slow)",
    ],
)
def test_registered_markers_survive_boolean_grouping(mod, pytestconfig, markexpr):
    """修法不能靠「凡有括号一律报错」：布尔分组是合法语法，必须原样通过。

    这一组是上面那组的对照支——没有它，「把 `(` 直接判成非法字符」也能让绕过用例全绿。
    """
    _configure(mod, pytestconfig, markexpr)


def test_marker_keyword_arguments_are_not_marker_names(mod, pytestconfig):
    """pytest 8+ 的 `-m "mark(name='x')"`：`name` 是关键字实参，不是 marker 名。

    这是那条正则**本来**要解决的问题，修法不能把它丢掉。
    """
    _configure(mod, pytestconfig, "slow(reason='x')")


def test_plugin_registered_markers_are_known(mod, pytestconfig):
    """插件在自己的 `pytest_configure` 里注册的 marker 也算已知。

    `only_browser` 来自 pytest-playwright，不在 pyproject 的 markers 表里。本条与钩子的
    `trylast` 是同一件事的两面：已知集合取自 `config.getini("markers")`，而插件是在
    configure 期往那里追加的。
    """
    if "only_browser" not in {
        line.split(":", 1)[0].split("(", 1)[0].strip() for line in pytestconfig.getini("markers")
    }:
        pytest.skip("本次运行没有装载 pytest-playwright，没有可用的插件 marker 做样本")
    _configure(mod, pytestconfig, "only_browser")


@pytest.mark.parametrize("markexpr", ["", "   ", None])
def test_absent_markexpr_is_a_no_op(mod, pytestconfig, markexpr):
    """没传 `-m` 时（`markexpr` 是空串或 None）什么都不做。"""
    _configure(mod, pytestconfig, markexpr)


# --------------------------------------------------------------------------- 语法与提取


@pytest.mark.parametrize("markexpr", ["(", "baseline_1b and", "not )", "a and (b"])
def test_malformed_expression_fails_as_a_usage_error(mod, pytestconfig, markexpr):
    """畸形表达式必须以 `UsageError` 收场，而不是让 `SyntaxError` 逃出钩子。

    钩子里逃出去的 `SyntaxError` 在 pytest 里表现为 INTERNALERROR + 一屏 traceback；
    `UsageError` 是「你命令行写错了」这件事的正确形状。
    """
    with pytest.raises(pytest.UsageError):
        _configure(mod, pytestconfig, markexpr)


@pytest.mark.parametrize(
    "markexpr,expected",
    [
        ("baseline_1b", {"baseline_1b"}),
        ("(baseline_1b_typo)", {"baseline_1b_typo"}),
        ("not (typo)", {"typo"}),
        ("a and (typo or b)", {"a", "typo", "b"}),
        ("slow(reason='x')", {"slow"}),
        ("not (slow and (a or b))", {"slow", "a", "b"}),
        ("", set()),
    ],
)
def test_marker_names_extraction_is_exhaustive(mod, markexpr, expected):
    """直接钉住提取函数本身：短路求值取不到的分支也必须被看见。

    提取走的是 pytest 自己的表达式解析器（`Expression.compile`），本条是它的合同：
    哪天那个内部接口变了形状、提取悄悄退化成「什么都没找到」，红的是这里——而不是某次
    soak 里一组静默的空集。
    """
    assert mod._marker_names(markexpr) == expected


def test_extraction_failing_closed_is_not_silent(mod, pytestconfig):
    """提取机制一旦失效，必须**失败关闭**：报错，而不是「零个未知名字 ⇒ 通过」。

    模拟法是把编译结果换成一个没有可读代码对象的替身——这正是「pytest 换了内部实现」
    在本地表现出来的样子。
    """

    class _Opaque:
        pass

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mod, "_compile_markexpr", lambda _expr: _Opaque())
        with pytest.raises(pytest.UsageError) as excinfo:
            _configure(mod, pytestconfig, "baseline_1b")
    assert "marker" in str(excinfo.value).lower(), str(excinfo.value)
