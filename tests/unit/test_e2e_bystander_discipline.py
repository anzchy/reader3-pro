"""凡断「同章多于一条标注」的 e2e 用例，必须显式断一次旁观条守恒。

**这条检查存在的理由是「漏写不会红」。** `assert_roundtrip(expected_count=N)` 只保证
目标条往返成功、总数是 N；同章其余条目有没有被顺手改掉，它一概不管——**而且刻意不管**，
因为对每个调用点都成立的断言等于恒真（见 `helpers.assert_roundtrip` 的 docstring）。

于是「多标注用例忘了断旁观条」是一种**静默失效**：用例照样全绿，只是少测了一整类缺陷
（服务端整章回写漏条、客户端候选集放宽误删）。静默失效的规则留在散文里没有用，必须机器可查。
任务书 §0 第五条纪律与 §0.6 的跨波欠账表都指向本文件。

放在 `tests/unit/` 而不是某个 lint 脚本里，是照 `test_e2e_group_layout.py` 的先例：
`scripts/` 下的 lint 脚本存常量，断言存这里；而且 unit lane 才是 `gateOn: commit` 的那条。

**判据为什么是 AST 而不是 `in text`（2026-09-05 审计 · HIGH）。** 原实现的检查整个是
`REQUIRED_CALL not in text`——一次对**整份文件**的裸子串搜索。它认不出这三件事的区别：

  * `from helpers import assert_bystanders_unchanged`（只是 import，没有调用）；
  * 一句 docstring 或注释里提到这个名字（本文件下面的散文就全是这种）；
  * A 用例里真调了、B 用例里漏了（同一个文件里有一处就够，整份文件一起绿）。

也就是说：**把调用删掉、把 import 留着**，这道闸照样绿。它防的恰恰是「漏写」，而漏写
最常见的形态就是复制一条既有用例、改改断言、把那一行删了——import 从来不会跟着删。
现在的判据是：解析出 AST，逐个**测试函数**看——传了 `expected_count > 1` 的那个函数
自己（或它的外层函数）里必须有一次真正的 `assert_bystanders_unchanged(...)` **调用**。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List, Optional, Tuple

E2E_ROOT = Path(__file__).resolve().parents[1] / "e2e"

#: 逃生口，形态与选择器 lint 的 `# lint-e2e-selectors: allow` 一致：必须写理由。
#: 用在「本章确实有多条，但旁观条守恒由别的判据以更强的形式覆盖」这种场合，
#: 也用在「守恒断言包在本模块自己的一个 helper 里」这种本检查看不穿的写法上。
ESCAPE_RE = re.compile(r"#\s*bystanders:\s*n/a\s*——\s*\S")

REQUIRED_CALL = "assert_bystanders_unchanged"
COUNT_KWARG = "expected_count"


def _callee_name(node: ast.Call) -> Optional[str]:
    """`f(...)` → `"f"`；`mod.f(...)` → `"f"`；其他形态（下标、lambda）→ None。"""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_multi_count(kw: ast.keyword) -> bool:
    """这个 `expected_count=` 实参是不是「多于一条」。

    字面量 > 1 是显然的一支。**非字面量（变量、表达式）也算**：读不出取值时，本检查
    宁可要求那条用例把守恒断出来——放行的代价是一个 `expected_count=N` 变量就能绕过整道闸，
    而误报的代价只是在那一行写一句逃生口理由。
    """
    value = kw.value
    if isinstance(value, ast.Constant):
        return isinstance(value.value, int) and not isinstance(value.value, bool) and value.value > 1
    return True


def _escaped(lines: List[str], node: ast.AST) -> bool:
    """调用所跨的源码行里有没有带理由的逃生口记号。"""
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start) or start
    return any(ESCAPE_RE.search(line) for line in lines[start - 1: end])


def _calls_in(node: ast.AST) -> List[ast.Call]:
    return [child for child in ast.walk(node) if isinstance(child, ast.Call)]


def violations_in(source: str, label: str = "<source>") -> List[str]:
    """返回 `source` 里所有「传了多条 `expected_count` 却没断旁观条守恒」的位置。

    作用域是**最近的那个（以及任何外层的）函数定义**：同一个文件里 A 用例断了、B 用例
    漏了，B 仍然是违规——这正是裸子串判据看不见的那一类。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover - 仓库里有语法错的用例文件本身就该红
        return [f"  {label}:{exc.lineno}  无法解析：{exc.msg}"]

    lines = source.splitlines()
    out: List[str] = []

    def visit(node: ast.AST, stack: Tuple[ast.AST, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, stack + (child,))
                continue
            if isinstance(child, ast.Call):
                kw = next((k for k in child.keywords if k.arg == COUNT_KWARG), None)
                if kw is not None and _is_multi_count(kw) and not _escaped(lines, child):
                    has_call = any(
                        _callee_name(call) == REQUIRED_CALL
                        for scope in stack
                        for call in _calls_in(scope)
                    )
                    if not has_call:
                        where = stack[-1].name if stack else "<模块级>"  # type: ignore[union-attr]
                        out.append(
                            f"  {label}:{child.lineno}  {where}() 传了 {COUNT_KWARG}"
                            f"，却没有调用 `{REQUIRED_CALL}(...)`"
                        )
            visit(child, stack)

    visit(tree, ())
    return sorted(set(out))


def test_multi_annotation_cases_assert_bystander_conservation() -> None:
    violations: List[str] = []
    for path in sorted(E2E_ROOT.rglob("*.py")):
        rel = path.relative_to(E2E_ROOT.parents[1])
        violations.extend(violations_in(path.read_text(encoding="utf-8"), str(rel)))

    assert not violations, (
        "下列用例传了 expected_count > 1，却没有在**同一个测试函数里**调用 "
        f"`{REQUIRED_CALL}(...)`：\n" + "\n".join(violations) + "\n\n"
        "`assert_roundtrip` 只管目标条与总数，同章旁观条有没有被动过它不管（刻意的）。"
        "漏断不会红，只会少测一整类缺陷——服务端整章回写漏条、客户端候选集放宽误删。\n"
        "确有理由不断的（守恒由更强的判据覆盖，或断言包在本模块自己的 helper 里），"
        "在该调用行末尾写 `# bystanders: n/a —— <理由>`。"
    )


def test_the_check_itself_can_fail() -> None:
    """本检查不是空转：违规的几种形态必须被判出来，合规的几种必须放行。"""
    compliant = (
        "def test_w7():\n"
        "    assert_roundtrip(page, d, b, q, a, expected_count=2)\n"
        "    assert_bystanders_unchanged(before, after, changed_ids={x})\n"
    )
    assert not violations_in(compliant), "合规形态被误判了"

    assert violations_in(
        "def test_w7():\n"
        "    assert_roundtrip(page, d, b, q, a, expected_count=2)\n"
    ), "违规形态没被识别出来，本检查是空转的"

    assert not violations_in(
        "def test_w7():\n"
        "    assert_roundtrip(page, d, b, q, a, expected_count=1)\n"
    ), "expected_count=1 是单条形态，不该触发"

    assert not violations_in(
        "def test_w7():\n"
        "    assert_roundtrip(page, d, b, q, a, expected_count=2)  "
        "# bystanders: n/a —— 本章两条互相重叠，守恒由 W-8 的分段断言覆盖\n"
    ), "带理由的逃生口没有放行"

    assert violations_in(
        "def test_w7():\n"
        "    assert_roundtrip(page, d, b, q, a, expected_count=2)  # bystanders: n/a\n"
    ), "逃生口没写理由，不该放行"

    assert not violations_in(
        "def test_w7():\n"
        "    # 说明：这里传 expected_count=2 是因为同章有一条旁观标注\n"
        "    pass\n"
    ), "整行注释只是谈到它，不是调用点"


def test_import_or_prose_mentioning_the_helper_is_not_a_call() -> None:
    """审计 HIGH 的三种形态：留着 import、留着注释、留着 docstring，把调用删掉。

    裸子串判据（`REQUIRED_CALL not in text`）对这三种全部放行——而「复制一条用例、
    改改断言、把守恒那行删掉」留下的正好就是这三种残骸，import 从来不会跟着删。
    """
    import_only = (
        f"from helpers import assert_roundtrip, {REQUIRED_CALL}\n\n"
        "def test_w7():\n"
        "    assert_roundtrip(page, d, b, q, a, expected_count=2)\n"
    )
    assert violations_in(import_only), "只留 import、没有调用，仍然是漏断"

    comment_only = (
        "def test_w7():\n"
        f"    # 旁观条守恒见 {REQUIRED_CALL}\n"
        "    assert_roundtrip(page, d, b, q, a, expected_count=2)\n"
    )
    assert violations_in(comment_only), "注释里提到函数名不等于调用了它"

    docstring_only = (
        "def test_w7():\n"
        f'    """本条的守恒判据是 {REQUIRED_CALL}。"""\n'
        "    assert_roundtrip(page, d, b, q, a, expected_count=2)\n"
    )
    assert violations_in(docstring_only), "docstring 里提到函数名不等于调用了它"

    name_without_call = (
        "def test_w7():\n"
        f"    checker = {REQUIRED_CALL}\n"
        "    assert_roundtrip(page, d, b, q, a, expected_count=2)\n"
    )
    assert violations_in(name_without_call), "只是引用了函数对象，没有调用它"


def test_the_scope_is_the_test_function_not_the_whole_file() -> None:
    """同一文件里 A 断了 B 没断 —— B 必须被点名。

    这是裸子串判据最隐蔽的一个洞：一个模块里只要**任何一处**出现过那个名字，整份文件的
    所有多标注用例就都免检了。而多标注用例本来就是成组出现的。
    """
    source = (
        "def test_a():\n"
        "    assert_roundtrip(page, d, b, q, a, expected_count=2)\n"
        "    assert_bystanders_unchanged(before, after, changed_ids={x})\n"
        "\n"
        "def test_b():\n"
        "    assert_roundtrip(page, d, b, q, a, expected_count=3)\n"
    )
    found = violations_in(source, "m.py")
    assert len(found) == 1, found
    assert "test_b" in found[0], found


def test_non_literal_count_still_requires_the_assertion() -> None:
    """`expected_count=N` 这种读不出取值的写法不许当作「单条」放行。

    读不出取值时本检查取严的那一支；要放行就写逃生口理由。
    """
    assert violations_in(
        "def test_w7():\n"
        "    assert_roundtrip(page, d, b, q, a, expected_count=n)\n"
    ), "非字面量的 expected_count 被当成单条放行了"

    assert not violations_in(
        "def test_w7():\n"
        "    assert_roundtrip(page, d, b, q, a, expected_count=n)\n"
        "    assert_bystanders_unchanged(before, after, changed_ids={x})\n"
    ), "非字面量 + 已断守恒，不该违规"


def test_a_method_style_call_counts() -> None:
    """`helpers.assert_bystanders_unchanged(...)` 也算调用过。"""
    assert not violations_in(
        "def test_w7():\n"
        "    assert_roundtrip(page, d, b, q, a, expected_count=2)\n"
        f"    helpers.{REQUIRED_CALL}(before, after, changed_ids={{x}})\n"
    )
