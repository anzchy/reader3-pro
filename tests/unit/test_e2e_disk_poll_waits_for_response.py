"""WI-15（审计 #8）：e2e 里「轮询磁盘」之前，必须先把那次写的响应等到手。

`helpers.wait_for_notes()` / `wait_for_note_text()` 是**纯 Python 的轮询**——`time.sleep`
加读文件，整个窗口里一次都没调进 Playwright。而同步 Playwright 的 route 回调是 Python
函数，只在主协程调进 Playwright 时才被派发；`tests/e2e/conftest.py` 给每个 context 都挂了
一道 `**/*` 的出网闸，于是**每一个**请求都要经过一个这样的回调。

两件事合起来就是 #43 那族 flake 的机制：点完按钮直接去轮盘，那次写会卡在出网闸的回调上
跑不动，轮询等满 8 秒超时——**产品行为完全正确也会红**。红出来的用例每次不同、但全挂在
同一族断言上，正是因为谁先被调度是随机的。

所以这条护栏盯的是一个**顺序契约**：在登记的函数里，每一次盘上轮询之前，最近的那次
`.click()` 必须裹在 `with page.expect_response(...)` 里——先让浏览器把响应交出来（这一步
会把 route 回调服务掉），再去读盘。

**为什么是登记制而不是全仓扫描**：同一个文件里还有十几处同形调用，但它们中间隔着
`_wait_until` / `expect(...)` / `settle_marks` 这类**会泵事件**的等待，够不够取决于那个
等待的条件与这次写的关系——逐个判定是 #8 之外的工作。这里只锁审计点名的调用点，以及
它们所在函数里同形且同样无遮挡的几处。新增登记项要连着判断一起写进来。

**冻结集不在登记里**：`tests/e2e/baseline_1b/test_w8a_selection_survives_rerender.py:132`
是同一个毛病，但动它一个字节就会把 soak 计数清零并使三道机制闸全部作废（见 017 任务书
§5）。这条护栏因此**不得**把 `baseline_1b/**` 扫进来。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]

#: 纯 Python、不泵事件的盘上轮询。
DISK_POLLS = frozenset({"wait_for_notes", "wait_for_note_text"})

#: 把点击裹起来、能把响应等到手的上下文管理器。
RESPONSE_WAITERS = frozenset({"expect_response", "expect_event"})

#: 「点一下并且把这次写的响应等到手」的封装。调用它等同于把点击裹进 `expect_response`——
#: 但这条等价**不白给**：下面 `_helper_is_honest()` 会去读它的定义，确认它体内真的有一个
#: `with ...expect_response(...)` 裹着 `.click()`。否则登记一个名字就能绕过整条护栏。
AWAITING_HELPERS = frozenset({"_click_awaiting_write"})


class Site(NamedTuple):
    path: str
    function: str


REGISTERED_SITES: Tuple[Site, ...] = (
    Site(
        "tests/e2e/test_notes_write_failure_is_attributable.py",
        "test_w4_c3_multi_id_partial_failure_keeps_progress_and_reports_per_id",
    ),
    Site(
        "tests/e2e/acceptance_2a/test_deg_s5_write_conflict.py",
        "_run_conflict_round",
    ),
)

#: 按契约**不发写请求**的点击——给它挂 `expect_response` 会挂死，不是修好。
#: key 是点击表达式（`ast.unparse` 之后），value 是豁免理由，两者都要在评审里看得见。
EXEMPT_CLICKS: Dict[str, str] = {
    "dialog.get_by_test_id(branch.exit_testid).click": (
        "「采用远端」那一支的语义就是放弃本地改动、一个字节都不往服务端写"
        "（同一个函数里的 (d) 段正是断言它**没有**写）。给这里挂 expect_response，"
        "在那一支上会等到超时——那是把一条真实的分支语义改成挂死，不是修好。"
        "它后面紧跟着 `expect(dialog).to_be_hidden()`，那一步会泵事件。"
    ),
}


# --------------------------------------------------------------------------
# 检查器
# --------------------------------------------------------------------------


def _called_name(node: ast.Call) -> Optional[str]:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _response_wait_spans(tree: ast.AST) -> List[Tuple[int, int]]:
    """所有 `with ...expect_response(...):` 的**函数体**行号区间。"""
    spans: List[Tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            continue
        waits = False
        for item in node.items:
            for call in ast.walk(item.context_expr):
                if isinstance(call, ast.Call) and _called_name(call) in RESPONSE_WAITERS:
                    waits = True
        if waits and node.body:
            spans.append((node.body[0].lineno, node.body[-1].end_lineno or node.body[-1].lineno))
    return spans


def _helper_is_honest(tree: ast.AST, name: str) -> bool:
    """`name` 的定义里，真的有一个 `.click()` 裹在 `with ...expect_response(...)` 里吗？"""
    node = _find_function(tree, name)
    if node is None:
        return False
    spans = _response_wait_spans(node)
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and _called_name(sub) == "click":
            if any(lo <= sub.lineno <= hi for lo, hi in spans):
                return True
    return False


def _find_function(tree: ast.AST, name: str) -> Optional[ast.AST]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def audit_source(source: str, function: str, *, label: str = "<源码>") -> List[str]:
    """返回 `function` 里违反「先等响应、再轮盘」的问题描述；合契约时返回空列表。

    空列表也可能意味着「这个函数里根本没有盘上轮询」——那是一种**静默失效**：函数被改名、
    轮询被换成别的写法，护栏就什么都不看了却依旧是绿的。所以「一条都没找到」在这里算问题，
    不算通过。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover - 只有源码本身坏掉时走到
        return [f"{label}：解析失败 {exc}"]

    node = _find_function(tree, function)
    if node is None:
        return [
            f"{label}：找不到函数 {function}()——它被改名或删掉了。护栏登记的是函数名，"
            "名字一变这条检查就什么都不看了，所以这里判红而不是静默放行。"
        ]

    spans = _response_wait_spans(node)
    polls: List[ast.Call] = []
    steps: List[ast.Call] = []
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        name = _called_name(sub)
        if name in DISK_POLLS:
            polls.append(sub)
        elif name == "click" or name in AWAITING_HELPERS:
            steps.append(sub)
    polls.sort(key=lambda c: c.lineno)
    steps.sort(key=lambda c: c.lineno)

    problems: List[str] = []
    dishonest = sorted(
        {
            name
            for step in steps
            if (name := _called_name(step)) in AWAITING_HELPERS
            and not _helper_is_honest(tree, name)
        }
    )
    for name in dishonest:
        problems.append(
            f"{label}：{name}() 被当成「点一下并等到响应」用，但它的定义里没有一个 "
            "`.click()` 裹在 `with ...expect_response(...)` 里——登记了一个名字，"
            "却没有兑现它代表的等待。"
        )

    checked = 0
    for poll in polls:
        earlier = [c for c in steps if c.lineno < poll.lineno]
        if not earlier:
            continue
        step = earlier[-1]
        expr = ast.unparse(step.func)
        if expr in EXEMPT_CLICKS:
            continue
        checked += 1
        if _called_name(step) in AWAITING_HELPERS:
            continue
        if not any(lo <= step.lineno <= hi for lo, hi in spans):
            problems.append(
                f"{label}:{poll.lineno}：`{_called_name(poll)}(...)` 之前最近的那次点击"
                f"（第 {step.lineno} 行 `{expr}()`）没有裹在 "
                "`with page.expect_response(...)` 里。盘上轮询是纯 Python 的 sleep，"
                "期间同步 route 回调（含 conftest 那道 `**/*` 出网闸）跑不了，"
                "这次写会卡在回调上直到轮询超时——产品行为正确也会红。"
            )

    if not problems and checked == 0:
        problems.append(
            f"{label}：{function}() 里一处受检的盘上轮询都没有"
            f"（认得的轮询名：{sorted(DISK_POLLS)}）。这条护栏因此什么都没判——"
            "登记项要么过期了，要么轮询换了个名字绕过了它。"
        )
    return problems


# --------------------------------------------------------------------------
# 真实调用点
# --------------------------------------------------------------------------


@pytest.mark.parametrize("site", REGISTERED_SITES, ids=lambda s: s.function)
def test_registered_e2e_sites_wait_for_the_response_before_polling_disk(site: Site) -> None:
    path = REPO_ROOT / site.path
    assert path.exists(), f"登记的 e2e 文件不在了：{site.path}"
    problems = audit_source(path.read_text(encoding="utf-8"), site.function, label=site.path)
    assert not problems, "\n".join(problems)


def test_the_guard_never_reaches_into_the_frozen_baseline() -> None:
    """动 `baseline_1b/**` 会把 soak 计数清零。这条护栏必须够不着它。"""
    reached = [s.path for s in REGISTERED_SITES if "baseline_1b" in s.path]
    assert not reached, (
        f"登记表里出现了冻结路径 {reached}——按这条护栏去改它，会把 soak 计数清零"
        "并使三道机制闸全部作废（017 任务书 §5）。"
    )


# --------------------------------------------------------------------------
# 检查器自身：它得真的分得开对与错
# --------------------------------------------------------------------------

_GOOD = '''
def round_trip(page, books_dir):
    with page.expect_response(lambda r: r.request.method == "POST"):
        page.get_by_test_id("save").click()
    wait_for_notes(books_dir, "b", 1)
'''

_CHECKER_MUTANTS: Tuple[Tuple[str, str, str], ...] = (
    (
        "点击没有裹在 expect_response 里",
        '''
def round_trip(page, books_dir):
    page.get_by_test_id("save").click()
    wait_for_notes(books_dir, "b", 1)
''',
        "没有裹在",
    ),
    (
        "裹的是点击之后的那一句、点击自己在外面",
        '''
def round_trip(page, books_dir):
    page.get_by_test_id("save").click()
    with page.expect_response(lambda r: True):
        page.get_by_test_id("noop").hover()
    wait_for_notes(books_dir, "b", 1)
''',
        "没有裹在",
    ),
    (
        "with 等的不是响应而是别的东西",
        '''
def round_trip(page, books_dir):
    with page.expect_download():
        page.get_by_test_id("save").click()
    wait_for_notes(books_dir, "b", 1)
''',
        "没有裹在",
    ),
    (
        "轮询被换了个名字绕过登记",
        '''
def round_trip(page, books_dir):
    page.get_by_test_id("save").click()
    poll_until_notes(books_dir, "b", 1)
''',
        "一处受检的盘上轮询都没有",
    ),
    (
        "封装说等了响应、体内其实没等",
        '''
def _click_awaiting_write(page, locator, what):
    locator.click()


def round_trip(page, books_dir):
    _click_awaiting_write(page, page.get_by_test_id("save"), "存")
    wait_for_notes(books_dir, "b", 1)
''',
        "没有兑现",
    ),
    (
        "封装根本没有定义（名字是登记表里的，实现不在这个文件里）",
        '''
def round_trip(page, books_dir):
    _click_awaiting_write(page, page.get_by_test_id("save"), "存")
    wait_for_notes(books_dir, "b", 1)
''',
        "没有兑现",
    ),
    (
        "函数被改名",
        '''
def renamed(page, books_dir):
    with page.expect_response(lambda r: True):
        page.get_by_test_id("save").click()
    wait_for_notes(books_dir, "b", 1)
''',
        "找不到函数",
    ),
)


_GOOD_VIA_HELPER = '''
def _click_awaiting_write(page, locator, what):
    with page.expect_response(lambda r: True):
        locator.click()


def round_trip(page, books_dir):
    page.get_by_test_id("open-editor").click()
    _click_awaiting_write(page, page.get_by_test_id("save"), "存")
    wait_for_notes(books_dir, "b", 1)
'''


@pytest.mark.parametrize(
    "source", [_GOOD, _GOOD_VIA_HELPER], ids=["直接裹住", "经由兑现了的封装"]
)
def test_the_checker_accepts_the_shape_it_is_meant_to_accept(source: str) -> None:
    assert audit_source(source, "round_trip") == []


@pytest.mark.parametrize(
    "guard_source,expected",
    [pytest.param(src, exp, id=name) for name, src, exp in _CHECKER_MUTANTS],
)
def test_the_checker_rejects_every_known_way_to_break_the_contract(
    guard_source: str, expected: str
) -> None:
    problems = audit_source(guard_source, "round_trip")
    assert problems, f"检查器放过了它：\n{guard_source}"
    assert any(expected in p for p in problems), (
        f"红了，但理由不对——期望提到 {expected!r}，实际：{problems}"
    )


def test_the_exemption_is_keyed_to_a_click_that_really_exists() -> None:
    """豁免必须对得上真实源码里的那次点击，否则它只是一条没人用的注释。"""
    source = (REPO_ROOT / "tests/e2e/acceptance_2a/test_deg_s5_write_conflict.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    exprs = {
        ast.unparse(n.func)
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and _called_name(n) == "click"
    }
    missing = [key for key in EXEMPT_CLICKS if key not in exprs]
    assert not missing, (
        f"豁免表里这些点击在源码里根本不存在：{missing}。一条对不上任何代码的豁免，"
        "只会在下次有人真的需要豁免时被误当成先例。"
    )


def test_every_exemption_carries_a_reason() -> None:
    blank = [key for key, why in EXEMPT_CLICKS.items() if not why.strip()]
    assert not blank, f"这些豁免没写理由：{blank}"
