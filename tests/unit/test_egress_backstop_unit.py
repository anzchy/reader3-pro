"""WI-3 —— unit lane 那道**全 lane 出网闸**的自检（C1、C3-C10、C13，以及 C14 的驱动）。

闸本身住在 `tests/unit/egress_guard.py`，由 `tests/unit/conftest.py` 与
`tests/contract/conftest.py` **各自**注册成 autouse fixture。之所以要一个独立的、可
import 的非 test 模块：`tests/unit/test_egress_backstop_subprocess.py`（C11）会在子
解释器里把**同一份**闸装进一棵合成用例树；如果那边装的是一份抄件，C11 证的就是抄件
的性质，跟 lane 真正跑的那道闸无关。

闸的形状与三个不可动摇的决定：

1. patch 的是 ``socket.socket.connect``，**不是** ``socket.create_connection``。
   ``http.client.HTTPConnection`` 在 import 期就把后者抓成了类属性
   （`tests/unit/test_server_egress_gate.py:85` 已经记过这一笔）。``create_connection``
   内部走的是 ``sock.connect(sa)``，所以被传递地覆盖到。
2. ``_boom`` 抛的是 **AssertionError**，不是 OSError 的子类。
   ``tests/fixtures/deg_assertions.py:357`` 的重试循环 catch 的是
   ``(URLError, ConnectionError, OSError)``——一个 OSError 子类会被它整个吞掉然后
   空转到超时。那个文件是冻结路径，改不了，豁免标记是那里唯一的杠杆。
3. **回环也拦**。``tests/unit/test_ai_queue_lease.py`` 把 ollama 的 base_url 指向
   ``http://localhost:11434``，靠 ``monkeypatch.setattr(server, "_egress_post_stream", …)``
   拦下来。那个桩哪天悄悄失效——正是这个工作项存在的理由——一道放行回环的闸会让它
   去拨真的本机 ``ollama serve`` 然后全绿。C5/C6 这一对是「回环也拦」从一句话变成
   一个红绿事实的地方。

自检（哪个改动让哪条变红）：

* 把 conftest 里的注册删掉 ⇒ C1 红（``connect`` 不再是 ``_boom``）。
* 把 ``_boom`` 改成「抛但不记账」 ⇒ C3、C7 红（异常在工作线程里被吞，记录是仅剩的证据）。
* 给 ``_boom`` 加一句 ``if address[0] in ("127.0.0.1", "::1"): return _ORIG_CONNECT(...)``
  ⇒ C6 红。
* 把豁免实现成「记账但不抛」 ⇒ C5 红（``socket.socket.connect is _ORIG_CONNECT`` 不成立）。
* 把 conftest 的注册从 ``yield from`` 改成手抄一份 ``_boom`` ⇒ C1/C2 里那条
  ``co_filename == egress_guard.__file__`` 红。
* 把 ``egress_guard.no_real_egress`` 最后那句 ``assert egress_violations == []`` 删掉
  ⇒ **C1-C10 一条都不会红**（它们都在用例体里 ``clear()`` 过），只有 C11（integration
  lane，子解释器）和 C14（本文件的驱动 + 探针文件）会红。这正是那两条存在的理由：
  C11 是**闸体**的收据，C14 是**注册**的收据，互相不能替代。
* 在本 lane 任何一个模块顶上写 ``pytestmark = pytest.mark.real_loopback_socket``
  ⇒ C9 红（静态等式）且 C13 红（运行时 surplus）。

断言档位（见 tests/unit/conftest.py）：L2 返回值，L4 故障注入。
"""

from __future__ import annotations

import ast
import os
import re
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: TEST-NET-3（RFC 5737）。保证不可路由，所以**闸不在的时候**这些用例是快速失败
#: （0.5s 超时）而不是挂在操作系统那个 ~75s 的 connect 超时上。挂住的红没人读。
BLOCKED_ADDR = "203.0.113.1"

MARKER_NAME = "real_loopback_socket"

#: 单测里每一次 subprocess 的上限（沿用 tests/unit/test_soak_run.py:69 的理由）：
#: 这些用例跑在 commit 门里，无超时的 subprocess.run 会把整道门挂成「还在跑」。
CLI_TIMEOUT_S = 120.0


# --------------------------------------------------------------------------
# 取被测物。两处都**不在模块顶层 import**——闸还不存在时，顶层 import 会把红跑成
# collection error（零条用例执行），据此录下的收据证明不了任何断言被求值过。
# 见 tests/unit/test_server_egress_gate.py:44 的同一条理由。
# --------------------------------------------------------------------------


def load_guard():
    """取 `tests/unit/egress_guard.py`；不存在时以 AssertionError 报红。"""
    try:
        import egress_guard  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - 只在闸还没落地时走到
        raise AssertionError(
            "tests/unit/egress_guard.py 还不存在：全 lane 出网闸没有可共享的闸体，"
            "两处 conftest 只能各抄一份，C11 在子解释器里装的也就不是 lane 真跑的那道闸"
        ) from None
    return egress_guard


def violations(request: pytest.FixtureRequest) -> List[Tuple[str, str, str]]:
    """取本 lane 闸的记账 list。

    走 ``getfixturevalue`` 而不是把 ``egress_violations`` 写进签名，是为了让「fixture
    还没注册」以**断言失败**的形状报红，而不是以 pytest 的 fixture 查找错误报红——
    后者是「跑不起来」，不是「规格没被满足」。
    """
    try:
        return request.getfixturevalue("egress_violations")
    except pytest.FixtureLookupError as exc:  # pragma: no cover - 只在闸还没落地时走到
        raise AssertionError(
            "egress_violations fixture 没被注册：两处 conftest 还没把 egress_guard 的闸接上，"
            "本 lane 的任何一条用例都可以静悄悄地出网"
        ) from exc


def guard_is_installed(guard) -> bool:
    return getattr(socket.socket.connect, "__code__", None) is not None and (
        os.path.realpath(socket.socket.connect.__code__.co_filename)
        == os.path.realpath(guard.__file__)
    )


# --------------------------------------------------------------------------
# C1 —— unit lane 自检：连出去的那一下被拦住，并且留了账。 L4 / S1
# --------------------------------------------------------------------------


def test_a_routable_connect_is_blocked_and_recorded(request: pytest.FixtureRequest) -> None:
    """断的是「没有包出去」+「留了账」，不只是「抛了个异常」。

    一个「先连上再抛」的实现会在这里表现成 0.5s 的延迟或者一个非 AssertionError 的
    失败形状；一个「抛了但不记账」的实现过不了 ``len(...) == 1``。
    """
    guard = load_guard()
    recorded = violations(request)

    assert guard_is_installed(guard), (
        "本 lane 上装着的 connect 不是 egress_guard.py 里那个 _boom："
        f"co_filename={getattr(socket.socket.connect, '__code__', None) and socket.socket.connect.__code__.co_filename}。"
        "要么闸压根没装，要么 conftest 里另抄了一份——C11 在子解释器里证的不是它"
    )

    s = socket.socket()
    s.settimeout(0.5)
    try:
        with pytest.raises(AssertionError) as exc:
            s.connect((BLOCKED_ADDR, 80))
    finally:
        s.close()

    assert BLOCKED_ADDR in str(exc.value), f"异常消息里没有地址，定位不到是谁在出网：{exc.value}"
    assert len(recorded) == 1, f"闸抛了但没记：{recorded}"
    assert BLOCKED_ADDR in recorded[0][1], f"记下来的地址是 {recorded[0][1]}"
    assert recorded[0][0] == "MainThread", f"记到的线程是 {recorded[0][0]}"
    recorded.clear()


# --------------------------------------------------------------------------
# C3 —— 工作线程里的出网，异常压根没跨过线程边界。 L4 / S1
# --------------------------------------------------------------------------


def test_a_worker_thread_connect_is_recorded_even_when_the_exception_is_swallowed(
    request: pytest.FixtureRequest,
) -> None:
    """``pytest.raises`` 表达不了这条：异常确实没到用例体里，这就是全部意义。"""
    load_guard()
    recorded = violations(request)

    def worker() -> None:
        s = socket.socket()
        s.settimeout(0.5)
        try:
            s.connect((BLOCKED_ADDR, 80))
        except BaseException:  # noqa: BLE001 - 故意吞掉：这就是被建模的场景
            pass
        finally:
            s.close()

    t = threading.Thread(target=worker, name="egress-probe")
    t.start()
    t.join(10)

    assert not t.is_alive(), "worker 线程没结束——这条用例本身在挂"
    assert len(recorded) == 1, (
        "线程里的 connect 没被记下来：异常被吞掉之后就再没有第二条证据了"
    )
    assert recorded[0][0] == "egress-probe", (
        f"记到的线程是 {recorded[0][0]}，闸只在主线程记账"
    )
    assert "worker" in recorded[0][2], f"记下来的栈里没有出网点：{recorded[0][2][-500:]}"
    recorded.clear()


# --------------------------------------------------------------------------
# C5 / C6 —— 豁免标记这一对。回环没有整体豁免。 L2 / S2
# --------------------------------------------------------------------------


@pytest.mark.real_loopback_socket
def test_a_marked_test_may_really_connect_to_loopback() -> None:
    """豁免必须是**彻底**的：装回 stdlib 的 connect，而不是换一个宽松的包装。

    只断「没抛异常」的话，一个 ``_boom`` 悄悄 return 的实现照样绿；所以这里断的是
    ``getpeername()``——真的连上了，并且对端就是本用例自己 bind 的那个端口。
    """
    guard = load_guard()

    assert socket.socket.connect is guard._ORIG_CONNECT, (
        "标了豁免却仍然装着闸的包装——豁免只是名义上的"
    )

    lst = socket.socket()
    s = socket.socket()
    try:
        lst.bind(("127.0.0.1", 0))
        lst.listen(1)
        s.settimeout(2.0)
        s.connect(lst.getsockname())
        assert s.getpeername() == lst.getsockname(), (
            f"连上了但对端不是我们自己 bind 的那个端口：{s.getpeername()} != {lst.getsockname()}"
        )
    finally:
        s.close()
        lst.close()


def test_loopback_is_not_wholesale_exempt(request: pytest.FixtureRequest) -> None:
    """与 C5 一字不差的操作，只少了那个装饰器。

    ``tests/unit/test_ai_queue_lease.py`` 把 ollama 指向 ``http://localhost:11434``，
    靠 ``monkeypatch.setattr(server, "_egress_post_stream", …)`` 拦。那个桩失效的那天，
    一道放行回环的闸会让它去拨真的本机 ollama 然后全绿——洞正开在被保护的那个名字底下。
    """
    guard = load_guard()
    recorded = violations(request)

    assert socket.socket.connect is not guard._ORIG_CONNECT, "未标记的用例上闸根本没装"

    lst = socket.socket()
    s = socket.socket()
    try:
        lst.bind(("127.0.0.1", 0))
        lst.listen(1)
        s.settimeout(2.0)
        with pytest.raises(AssertionError):
            s.connect(lst.getsockname())
    finally:
        s.close()
        lst.close()

    assert len(recorded) == 1 and "127.0.0.1" in recorded[0][1], (
        f"回环上的出网没被记账：{recorded}"
    )
    recorded.clear()


# --------------------------------------------------------------------------
# C7 —— 律：一次尝试一条记录，与线程数无关。 L4 / S5（有界穷举 3x2）
# --------------------------------------------------------------------------


@pytest.mark.parametrize("n,k", [(1, 1), (1, 3), (2, 1), (2, 3), (4, 1), (4, 3)])
def test_one_record_per_attempt_from_any_number_of_threads(
    request: pytest.FixtureRequest, n: int, k: int
) -> None:
    """守恒量就是断言本身：没有一个可以硬编码的期望值。

    一个「每线程只记第一条」的实现、一个用 ``threading.local()` 攒记录的实现、
    一个用 set 去重的实现，都会在这六个点里至少挂一个。
    """
    load_guard()
    recorded = violations(request)

    def worker() -> None:
        for _ in range(k):
            s = socket.socket()
            s.settimeout(0.5)
            try:
                s.connect((BLOCKED_ADDR, 80))
            except BaseException:  # noqa: BLE001 - 故意吞掉
                pass
            finally:
                s.close()

    threads = [threading.Thread(target=worker, name=f"egress-probe-{i}") for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)

    assert not any(t.is_alive() for t in threads), "有线程没结束——这条用例本身在挂"
    assert len(recorded) == n * k, (
        f"{n} 个线程各 {k} 次出网，只记到 {len(recorded)} 条——"
        "记账要么丢了并发写，要么每线程只记第一条"
    )
    names = {r[0] for r in recorded}
    assert len(names) == n, f"记到的线程名只有 {sorted(names)}"
    assert "MainThread" not in names, f"主线程不该出现在这里：{sorted(names)}"
    recorded.clear()


# --------------------------------------------------------------------------
# C8 —— 与既有模块级 `_no_real_sockets` 围栏共存。 L4 / S1
# --------------------------------------------------------------------------


def test_an_inner_module_fence_wins_and_the_lane_guard_comes_back(
    request: pytest.FixtureRequest,
) -> None:
    """`test_server_egress_gate.py:92` 那三处模块级围栏必须原样留着。

    如果 lane 闸在它们底下也记一笔，那三个模块会在 teardown 上无故报红；如果
    monkeypatch 的 undo 顺序不对，lane 闸会在会话中途消失。这两件事 C1-C7 都看不见。
    """
    guard = load_guard()
    recorded = violations(request)

    def inner_boom(*_a: object, **_kw: object) -> None:
        raise RuntimeError("inner")

    s = socket.socket()
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(socket.socket, "connect", inner_boom)
            with pytest.raises(RuntimeError, match="inner"):
                s.connect((BLOCKED_ADDR, 80))
            assert recorded == [], (
                "内层围栏拦下的连接被外层也记了一笔——teardown 会在一个本该绿的模块上报红"
            )
    finally:
        s.close()

    assert recorded == [], f"内层围栏退出之后外层补记了一笔：{recorded}"
    assert socket.socket.connect is not guard._ORIG_CONNECT, (
        "内层 undo 把 connect 还原到了 stdlib，lane 闸从这一刻起消失了"
    )
    assert guard_is_installed(guard), "内层围栏退出之后装回来的不是 lane 闸"


# --------------------------------------------------------------------------
# C9 —— 豁免名单锁：五种标记形状全覆盖。 L2 / S3
# --------------------------------------------------------------------------

#: 2026-09-07 实测基线。**每一条都是一个洞**，加一条就是在这道闸上开一个口子，
#: 必须是对这张表的一次刻意编辑。
#:
#: `tests/unit/test_ai_stub_contract.py` 三条：它们对 tests/fixtures/ai_stub.py 起的
#: 那个回环 HTTP stub 发真请求（`requests`）。ai_stub.py 是冻结路径，改不了。
#: `test_the_stub_listens_on_the_loopback_interface_only` 正确地不在名单里——它只读
#: `stub.bound_host`，不发请求。
#:
#: `tests/unit/test_deg_assertions_shared.py` 两条：`tests/fixtures/deg_assertions.py`
#: 起一个真的子进程 server，然后在**父进程**里 `urllib.request.urlopen` 打回环。
#: 那个文件同样冻结，而它 :357 的重试循环 catch `(URLError, ConnectionError, OSError)`
#: ——闸抛 AssertionError 正好逃得出去，所以少标一个的表现是**偶发**红。
EXPECTED_EXEMPTIONS: Set[Tuple[str, str]] = {
    (
        "tests/unit/test_ai_stub_contract.py",
        "test_gate_timeout_ends_the_body_cleanly_without_the_last_delta",
    ),
    (
        "tests/unit/test_ai_stub_contract.py",
        "test_gate_released_before_timeout_sends_the_last_delta_and_done",
    ),
    (
        "tests/unit/test_ai_stub_contract.py",
        "test_paths_other_than_api_chat_are_rejected_with_404",
    ),
    (
        "tests/unit/test_deg_assertions_shared.py",
        "test_pickle_fallback_server_boots_a_real_process_with_the_env_var_set",
    ),
    (
        "tests/unit/test_deg_assertions_shared.py",
        "test_pickle_fallback_server_raises_instead_of_skipping_when_the_process_dies",
    ),
    (
        "tests/unit/test_egress_backstop_unit.py",
        "test_a_marked_test_may_really_connect_to_loopback",
    ),
}

LANE_DIRS = ("tests/unit", "tests/contract")


def _is_marker_expr(node: ast.AST) -> bool:
    """只认 ``<something>.mark.real_loopback_socket``（可带调用括号）。

    `cfg.real_loopback_socket` 的 owner 是个 ``ast.Name``，中间没有 ``.mark.``，所以
    不算——这条就是 C9 那五个反面控制里「无关对象的同名属性」那一个的判据。
    """
    if isinstance(node, ast.Call):
        node = node.func
    if not isinstance(node, ast.Attribute) or node.attr != MARKER_NAME:
        return False
    owner = node.value
    return isinstance(owner, ast.Attribute) and owner.attr == "mark"


def _flatten_marks(node: ast.AST) -> Iterable[ast.AST]:
    if isinstance(node, (ast.List, ast.Tuple)):
        for elt in node.elts:
            yield from _flatten_marks(elt)
    else:
        yield node


def _carries_marker(node: ast.AST) -> bool:
    return any(_is_marker_expr(n) for n in _flatten_marks(node))


def _is_pytest_param(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "param"
    )


def scan_exemption_scopes(source: str, filename: str = "<src>") -> Set[str]:
    """一个源文件里所有豁免标记的**作用域名**。

    作用域列的取值：函数/异步函数装饰器 → 函数名；类装饰器 → 类名；
    模块级（或类级）``pytestmark`` → ``"<module>"``；``pytest.param(marks=…)`` → ``"<param>"``。

    纯 AST，不看文本：docstring / 注释 / 字符串字面量里出现这个名字一律不算。
    """
    tree = ast.parse(source, filename)
    found: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                if _carries_marker(dec):
                    found.add(node.name)
                for sub in ast.walk(dec):
                    if _is_pytest_param(sub):
                        for kw in sub.keywords:  # type: ignore[union-attr]
                            if kw.arg == "marks" and _carries_marker(kw.value):
                                found.add("<param>")
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "pytestmark"
                    and _carries_marker(node.value)
                ):
                    found.add("<module>")
    return found


def scan_lane_exemptions() -> Set[Tuple[str, str]]:
    found: Set[Tuple[str, str]] = set()
    for rel_dir in LANE_DIRS:
        root = REPO_ROOT / rel_dir
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            for scope in scan_exemption_scopes(path.read_text(encoding="utf-8"), rel):
                found.add((rel, scope))
    return found


POSITIVE_SHAPES: Dict[str, Tuple[str, str]] = {
    "FunctionDef": (
        "import pytest\n\n@pytest.mark.real_loopback_socket\ndef test_a():\n    pass\n",
        "test_a",
    ),
    "AsyncFunctionDef": (
        "import pytest\n\n@pytest.mark.real_loopback_socket\nasync def test_a():\n    pass\n",
        "test_a",
    ),
    "pytestmark_bare": (
        "import pytest\n\npytestmark = pytest.mark.real_loopback_socket\n\ndef test_a():\n    pass\n",
        "<module>",
    ),
    "pytestmark_list": (
        "import pytest\n\npytestmark = [pytest.mark.slow, pytest.mark.real_loopback_socket]\n"
        "\ndef test_a():\n    pass\n",
        "<module>",
    ),
    "ClassDef": (
        "import pytest\n\n@pytest.mark.real_loopback_socket\nclass TestThing:\n"
        "    def test_a(self):\n        pass\n",
        "TestThing",
    ),
    "pytest_param": (
        "import pytest\n\n@pytest.mark.parametrize(\n"
        '    "x", [pytest.param(1, marks=pytest.mark.real_loopback_socket)]\n)\n'
        "def test_a(x):\n    pass\n",
        "<param>",
    ),
}

NEGATIVE_SHAPES: Dict[str, str] = {
    "docstring": '"""real_loopback_socket 在 docstring 里"""\n\ndef test_a():\n    pass\n',
    "comment": "# real_loopback_socket 在注释里\ndef test_a():\n    pass\n",
    "str_literal": 'MARKER = "real_loopback_socket"\n\ndef test_a():\n    assert MARKER\n',
    "other_attr": "def test_a(cfg):\n    assert cfg.real_loopback_socket is None\n",
    "pytestmark_without_it": (
        "import pytest\n\npytestmark = [pytest.mark.slow]\n\ndef test_a():\n    pass\n"
    ),
}


@pytest.mark.parametrize("shape", sorted(POSITIVE_SHAPES))
def test_the_scanner_sees_every_marker_shape_pytest_honours(shape: str) -> None:
    """``get_closest_marker`` 认这五种形状，扫描器就必须也认。

    只认函数装饰器的话，任何一个模块顶上加一行 ``pytestmark = pytest.mark.real_loopback_socket``
    就能把这道闸对整个文件关掉，而这把锁仍然是绿的——而 ``pytestmark`` 在本仓库是既有惯用法
    （tests/e2e/baseline_1b/*、tests/e2e/acceptance_4b1/* 裸形式和 list 形式都在用）。
    """
    source, expected_scope = POSITIVE_SHAPES[shape]
    got = scan_exemption_scopes(source, f"<{shape}>")
    assert got == {expected_scope}, f"{shape} 形状扫出来的是 {sorted(got)}，期望 {expected_scope!r}"


@pytest.mark.parametrize("shape", sorted(NEGATIVE_SHAPES))
def test_the_scanner_does_not_count_the_word_outside_a_real_mark(shape: str) -> None:
    """扫描器读的是 AST，不是文本。一个 ``re`` 实现会在这五条里全挂。"""
    got = scan_exemption_scopes(NEGATIVE_SHAPES[shape], f"<{shape}>")
    assert got == set(), f"{shape} 被误判成了豁免：{sorted(got)}"


def test_the_exemption_set_on_the_real_tree_equals_the_locked_list() -> None:
    """静态等式：多一个是「有人在拆闸」，少一个是「名单没跟上重命名」，两边一样响。"""
    found = scan_lane_exemptions()
    surplus = sorted(found - EXPECTED_EXEMPTIONS)
    missing = sorted(EXPECTED_EXEMPTIONS - found)
    assert not surplus and not missing, (
        "豁免名单和树对不上。豁免就是洞，每加一个都必须是对 EXPECTED_EXEMPTIONS 的一次刻意编辑。\n"
        + ("  多出：" + ", ".join(f"{f}::{s}" for f, s in surplus) + "\n" if surplus else "")
        + ("  缺失：" + ", ".join(f"{f}::{s}" for f, s in missing) + "\n" if missing else "")
    )


# --------------------------------------------------------------------------
# C13 —— 运行时 oracle：pytest **真的**生效了的豁免是期望集合的子集。 L2 / S3
# --------------------------------------------------------------------------


def _expected_runtime_pairs(items) -> Set[Tuple[str, str]]:
    """把 EXPECTED_EXEMPTIONS 翻译成运行时可比的 ``(文件, 函数名)`` 对。

    R2 维护陷阱：作用域列可能是 ``"<module>"`` 或 ``"<param>"``，而运行时看到的永远是
    具体的函数名。所以比较发生在 ``(file, scope)`` 上，其中 ``<module>`` / ``<param>``
    **展开**成该文件下所有被收集到的用例——否则第一条合法的模块级 pytestmark 豁免会
    让这条无解地报 surplus，而最省事的「修法」就是把这条改弱。
    """
    file_wide = {f for f, s in EXPECTED_EXEMPTIONS if s in ("<module>", "<param>")}
    allowed = {(f, s) for f, s in EXPECTED_EXEMPTIONS if s not in ("<module>", "<param>")}
    for item in items:
        rel = Path(str(item.fspath)).resolve().relative_to(REPO_ROOT).as_posix()
        if rel in file_wide:
            allowed.add((rel, item.originalname or item.name))
    return allowed


def test_the_markers_pytest_actually_applied_are_a_subset_of_the_locked_list(
    request: pytest.FixtureRequest,
) -> None:
    """问 pytest 自己，而不是问扫描器——这是唯一骗不过的那个 oracle。

    子集而非等式：``-k`` / ``-m`` / 单文件运行时大部分期望项根本没被收集，等式会天天红，
    这道闸一天之内就会被关掉。「缺失」那一半是 C9 的活（静态，永远看得见整棵树）。
    """
    applied: Set[Tuple[str, str]] = set()
    for item in request.session.items:
        if item.get_closest_marker(MARKER_NAME):
            rel = Path(str(item.fspath)).resolve().relative_to(REPO_ROOT).as_posix()
            applied.add((rel, item.originalname or item.name))

    surplus = sorted(applied - _expected_runtime_pairs(request.session.items))
    assert not surplus, (
        f"pytest 实际生效的豁免多出：{surplus}。C9 的静态扫描没看见它们——"
        "多半是一种 C9 还不认识的标记形状（模块级 pytestmark、类装饰器、pytest.param(marks=)），"
        "先把形状加进 C9 的扫描器，再决定这条豁免该不该存在"
    )


# --------------------------------------------------------------------------
# C10 —— 被记在案的那个洞，钉住而不是只写在 docstring 里。 L2 / S2
# --------------------------------------------------------------------------


def test_connect_ex_is_a_documented_hole_and_stays_one(request: pytest.FixtureRequest) -> None:
    """`connect_ex` 不在闸内。把这件事钉成红绿事实，将来扩大覆盖面就必须是一次刻意的改动。"""
    load_guard()
    recorded = violations(request)

    lst = socket.socket()
    lst.bind(("127.0.0.1", 0))
    addr = lst.getsockname()
    lst.close()  # 端口关掉：connect_ex 立刻拿到 ECONNREFUSED，没有任何包离开本机

    s = socket.socket()
    s.settimeout(0.2)
    try:
        rc = s.connect_ex(addr)
    finally:
        s.close()

    assert rc != 0, f"connect_ex 连上了一个已经关掉的端口？rc={rc}"
    assert recorded == [], (
        "connect_ex 现在也被拦了。这不是坏事，但两处 conftest 的 docstring 说它没被拦，"
        "而 tests/fixtures/deg_assertions.py 是冻结路径——先更新 docstring 和本条，再说扩大覆盖面"
    )

    s2 = socket.socket()
    s2.settimeout(0.2)
    try:
        with pytest.raises(AssertionError):
            s2.connect(addr)
    finally:
        s2.close()

    assert len(recorded) == 1, f"同一个地址上 connect 没被拦：{recorded}"
    recorded.clear()


# --------------------------------------------------------------------------
# C14 —— **lane 自己那两处 conftest** 的注册在 teardown 上判红。 L4 / S2
# --------------------------------------------------------------------------

#: 两条探针，一处 conftest 一条。unit 那处直接挂 fixture，contract 那处走
#: ``yield from egress_guard.no_real_egress(...)``——只对 unit 放探针，contract 那半边的
#: teardown 记账就没有收据：把 ``yield from`` 改成 ``next(gen); yield`` 照样全绿。
PROBE_PATHS = (
    "tests/unit/test_egress_teardown_probe.py",
    # basename 必须唯一：pytest 默认 ``prepend`` 导入模式下，两个目录里同名的 test 模块
    # 会撞成 "import file mismatch" 而**整轮 collection 失败**，不是跳过一条。
    "tests/contract/test_egress_teardown_probe_contract.py",
)
PROBE_ENV = "READER3_EGRESS_TEARDOWN_PROBE"

_SUMMARY_TOKEN_RE = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|deselected)")


def summary_counts(out: str) -> Dict[str, int]:
    """从 pytest 的最后一行摘要里读计数。

    teardown 里的断言失败被 pytest 报成 ``ERROR at teardown of …``，摘要写的是
    ``1 passed, 1 error``，**不是** ``1 failed``。断 ``"1 failed" in out`` 的实现会因为
    错误的理由拿到红，然后靠「把断言挪进用例体」去修它——那样这条用例就没了。
    """
    for line in reversed([ln for ln in out.strip().splitlines() if ln.strip()]):
        pairs = _SUMMARY_TOKEN_RE.findall(line)
        if pairs and " in " in line:
            return {kind.rstrip("s") if kind.startswith("error") else kind: int(n) for n, kind in pairs}
    return {}


def failed_or_errored(out: str) -> int:
    counts = summary_counts(out)
    return counts.get("failed", 0) + counts.get("error", 0)


def run_child(cmd: List[str], *, cwd: Path, env: Dict[str, str] | None = None,
              timeout: float = CLI_TIMEOUT_S) -> "subprocess.CompletedProcess[str]":
    """带超时的 ``subprocess.run``（沿用 tests/unit/test_soak_run.py:75-86 的写法）。

    超时时把已捕获的输出一并报出来再 fail：挂死时最该看的恰恰是它挂之前印了什么，
    而无超时的子进程会把整道 commit 门挂成「测试还在跑」。
    """
    child_env = dict(os.environ)
    child_env.pop(PROBE_ENV, None)
    if env:
        child_env.update(env)
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=str(cwd), env=child_env
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - 只在子进程挂死时走到
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        pytest.fail(f"子进程超过 {timeout:g}s 没退出：{cmd}\n--- stdout ---\n{out}\n--- stderr ---\n{err}")


@pytest.mark.parametrize("probe_path", PROBE_PATHS)
def test_the_lane_conftest_itself_reddens_at_teardown(probe_path: str) -> None:
    """C11 只证明 ``egress_guard.py`` 里那行 teardown 断言存在；它证明不了两处 conftest
    真的走到了它。

    ``tests/unit/conftest.py`` 本来就有两处手写的 autouse 围栏（:62、:89），所以「手抄
    第三份」是最自然的写法；「``next(gen); yield`` 之后再也不 resume 那个生成器」也是。
    这两种写法都让 C11 保持绿而 lane 实际无闸——C1-C10 全都在用例体里 ``clear()`` 过，
    在它们眼里这两件事一模一样。

    未武装的那一半不是凑数：没有它，``armed.returncode != 0`` 会被一道「每轮都判红」的
    闸满足，而那种信号只会以「整个 lane 坏了」的形状出现，太晚而且读起来像环境问题。

    两处 conftest 各跑一条探针。只测 unit 那处的版本，对 ``tests/contract/conftest.py``
    的 ``yield from`` 是完全瞎的：把它改成 ``next(gen); yield``，setup 照跑、C1-C10 照绿，
    而 contract 半边的 teardown 记账被一行编辑无声关掉。
    """
    assert (REPO_ROOT / probe_path).exists(), f"{probe_path} 不存在——C14 的探针文件是本条的一半"

    cmd = [sys.executable, "-m", "pytest", probe_path, "-q", "-p", "no:cacheprovider"]
    armed = run_child(cmd, cwd=REPO_ROOT, env={PROBE_ENV: "1"})
    disarmed = run_child(cmd, cwd=REPO_ROOT)

    assert armed.returncode != 0, (
        "真 lane 的 tests/unit/conftest.py 装的闸没有在 teardown 判红。C11 只证明了 egress_guard.py "
        "里那一行存在，没证明 conftest 的注册真的走到它——C1-C10 全都在用例体里 clear 过，"
        f"这两件事在它们眼里一模一样：\n{armed.stdout[-2000:]}\n{armed.stderr[-2000:]}"
    )
    assert failed_or_errored(armed.stdout) == 1, (
        f"武装之后失败/错误数不是 1（摘要={summary_counts(armed.stdout)}）：\n{armed.stdout[-2000:]}"
    )
    assert BLOCKED_ADDR in armed.stdout, (
        f"红了，但失败信息里没有地址，定位不到是谁在出网：\n{armed.stdout[-2000:]}"
    )
    assert disarmed.returncode == 0 and "1 skipped" in disarmed.stdout, (
        f"未武装时探针本该只是一条 skip：\n{disarmed.stdout[-2000:]}\n{disarmed.stderr[-2000:]}"
    )
