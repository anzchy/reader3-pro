"""009 欠账 #49（019 WI-2）：盘上轮询期间必须**泵浏览器**，不许 `time.sleep`。

`helpers.wait_for_notes()` / `wait_for_note_text()` 原先用 `time.sleep(0.05)` 轮询。同步
Playwright 的 route 回调只在主线程调进 Playwright 时才被派发，而 `tests/e2e/conftest.py`
给每个 context 都挂了 `**/*` 出网闸——于是轮询窗口里那次写卡在闸的回调上跑不动，CPU
一紧就是「上线前排队 ≈8s」的慢请求簇。修法沿用 `wait_for_write_activity_settled` 的先例：
两个函数都收一个**必填、仅限关键字**的 `page`，轮询节拍改成 `page.wait_for_timeout(50)`。

矩阵：`.claude/tdd-guardian/tests-20260930-111704.md` §WI-2（WI2-U1..U11）与修订 A2（WI2-U15）。

**假对象的边界。** Playwright 的 `Page` 是假的（unit lane 没有浏览器），`helpers.time`
换成假钟（确定性）；读写盘走真的 `seed_notes` / `read_notes`，不 mock 文件系统。
真 `Page` 的那一半由 e2e lane 付：baseline_1b 的每个调用点，外加机制用例
`tests/e2e/test_disk_poll_pumps_inflight_write.py`（WI2-E2）。

假钟：`monotonic()` 由整数节拍**重算**（`T0 + ticks * 0.050`），不做浮点累加；`sleep`
一被调就抛；两次泵之间 `monotonic()` 被调超过 1000 次也抛——一个不泵的变体因此红，
而不是挂死。
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import inspect
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[2]
_HELPERS_PATH = REPO_ROOT / "tests" / "e2e" / "helpers.py"
_spec = importlib.util.spec_from_file_location(
    "reader3_e2e_helpers_pump_under_test", _HELPERS_PATH
)
assert _spec and _spec.loader, f"无法按路径加载 {_HELPERS_PATH}"
helpers = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = helpers
_spec.loader.exec_module(helpers)

#: 与 `tests/unit/test_e2e_disk_poll_waits_for_response.py` 的同名登记同一份名单。
DISK_POLLS = frozenset({"wait_for_notes", "wait_for_note_text"})

BOOK = "pump_data"
T0 = 1000.0
PUMP_S = 0.050
MAX_READS_WITHOUT_PUMP = 1000


def _rec(note_id: str, **extra: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": note_id,
        "chapter_index": 0,
        "type": "marker",
        "color": "yellow",
        "quote": f"quote {note_id}",
    }
    data.update(extra)
    return data


class FakeClock:
    def __init__(self) -> None:
        self.ticks = 0
        self._reads_since_pump = 0

    def monotonic(self) -> float:
        self._reads_since_pump += 1
        if self._reads_since_pump > MAX_READS_WITHOUT_PUMP:
            raise AssertionError("poll loop does not pump")
        return T0 + self.ticks * PUMP_S

    def sleep(self, _seconds: float) -> None:
        raise AssertionError("time.sleep called")

    def pumped(self) -> None:
        self.ticks += 1
        self._reads_since_pump = 0


class FakePage:
    """`wait_for_timeout(ms)` 记下 `ms`、推进假钟；第 `write_at` 次调用时执行 `action`。"""

    def __init__(
        self, clock: FakeClock, write_at: Optional[int], action: Callable[[], None]
    ) -> None:
        self.clock = clock
        self.write_at = write_at
        self.action = action
        self.waits: List[Any] = []

    def wait_for_timeout(self, ms: Any) -> None:
        self.waits.append(ms)
        self.clock.pumped()
        if self.write_at is not None and len(self.waits) == self.write_at:
            self.action()


def _install_clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    clock = FakeClock()
    monkeypatch.setattr(
        helpers, "time", SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep)
    )
    return clock


def _page_seeding(
    clock: FakeClock, books_dir: Path, write_at: Optional[int], records: List[Dict[str, Any]]
) -> FakePage:
    return FakePage(
        clock, write_at, lambda: helpers.seed_notes(books_dir, BOOK, records)
    )


# ---------------------------------------------------------------------------
# wait_for_notes
# ---------------------------------------------------------------------------


def test_wi2_u1_wait_for_notes_page_is_required_keyword_only(tmp_path: Path) -> None:
    param = inspect.signature(helpers.wait_for_notes).parameters.get("page")
    assert param is not None, "wait_for_notes 没有 `page` 参数"
    assert param.kind is inspect.Parameter.KEYWORD_ONLY, (
        f"`page` 必须仅限关键字，实际是 {param.kind}——位置参数会静默吞下旧调用"
    )
    assert param.default is inspect.Parameter.empty, (
        f"`page` 必须必填，实际缺省值 {param.default!r}——可选就等于允许退回 sleep"
    )
    with pytest.raises(TypeError):
        helpers.wait_for_notes(tmp_path, "b", 0)  # type: ignore[call-arg]


@pytest.mark.parametrize("n", [1, 7])
def test_wi2_u2_returns_exact_records_after_n_pumps_of_50ms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, n: int
) -> None:
    clock = _install_clock(monkeypatch)
    fp = _page_seeding(clock, tmp_path, n, [_rec("a"), _rec("b")])
    got = helpers.wait_for_notes(tmp_path, BOOK, 2, page=fp)
    assert got == helpers.read_notes(tmp_path, BOOK)
    assert [r["id"] for r in got] == ["a", "b"]
    assert fp.waits == [50] * n


def test_wi2_u3_budget_constant_is_unchanged() -> None:
    assert helpers.NOTES_WAIT_S == 8.0


# 旧的 test_wi2_u3_budget_is_exactly_8s_of_pumps 已由下方 WI6-U1 原位取代（019 WI-6）：
# 它跳过 151..169、超时只断 `<= 161`，7.6s 的变体能从它眼皮底下过去；每个样本还
# `mkdtemp` 一个不清理的目录。


# ---------------------------------------------------------------------------
# 预算边界（019 WI-6，审计 #3 / #6）：8.0s / 50ms 恰好 160 泵，死线两侧的节拍逐个钉住
# ---------------------------------------------------------------------------
#
# 矩阵：`.claude/tdd-guardian/tests-20260930-235900.md` §WI-6（WI6-U1..U6）。
# 旧的预算用例成功域止于 n=150、跳过 151..169、超时只断 `<= 161`——把死线改成 7.6s 的
# 变体（成功止于 151、超时泵 152 次）它一条都看不见。下面的期望值是**字面量**，由假钟
# 算术推出，不从 `helpers.NOTES_WAIT_S` 反算（反算就是拿被测代码给自己出答案）：
#   第 k 次迭代（ticks = k）继续 ⟺ 1000.0 + k*0.05 < 1008.0；159*0.05 → 1007.95 继续，
#   160*0.05 在 IEEE-754 里恰好舍入成 8.0 → 1008.0 < 1008.0 为假，停。
# 所以：写落在第 n 泵，`len(waits) == min(n, 160)`，且调用成功 ⟺ n ≤ 159。

EXPECTED_TIMEOUT_PUMPS = 160
LAST_OBSERVABLE_WRITE = 159
#: 死线（159/160）与 7.6s 变体死线（151/152/153）两侧的节拍，每次运行都跑，不靠搜索碰上。
BOUNDARY_EXAMPLES = (1, 150, 151, 152, 153, 158, 159, 160, 161, 169, 170, 400)
NOTES_TIMEOUT_PREFIX = "8.0s 内 notes.json 没有稳定到 1 条，实际 0 条："
TEXT_TIMEOUT_PREFIX = "8.0s 内 n1 的 note_text 没有变成 'new'，当前是 "
_DEADLINE_LINE = "deadline = time.monotonic() + NOTES_WAIT_S"


def _assert_clock_premise() -> None:
    """前提：假钟的算术真是上面推的那样；假钟一改，期望的 160 不会悄悄漂走。"""
    assert T0 + EXPECTED_TIMEOUT_PUMPS * PUMP_S == T0 + 8.0, "160 泵不再恰好落在 8.0s 上"
    assert T0 + LAST_OBSERVABLE_WRITE * PUMP_S < T0 + 8.0, "第 159 泵不再落在死线之前"


def _drive(
    name: str, fn: Callable[..., Any], books_dir: Path, write_at: Optional[int]
) -> Tuple[Any, Optional[str], List[Any]]:
    """在假钟下跑一次 `fn`，返回 (返回值, 超时消息或 None, 泵的记录)。

    `fn` 不一定是 `getattr(helpers, name)`——WI6-U5 传进来的是内存里的变体；`name`
    只决定喂哪种数据。假钟挂在 `helpers.time` 上，变体的 `__globals__` 就是模块字典，
    所以一样被它接管。
    """
    with pytest.MonkeyPatch.context() as mp:
        clock = FakeClock()
        mp.setattr(
            helpers, "time", SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep)
        )
        if name == "wait_for_notes":
            fp = _page_seeding(clock, books_dir, write_at, [_rec("only")])

            def call() -> Any:
                return fn(books_dir, BOOK, 1, page=fp)
        else:
            helpers.seed_notes(books_dir, BOOK, [_rec("n1", type="note", note_text="old")])
            fp = _page_seeding(
                clock, books_dir, write_at, [_rec("n1", type="note", note_text="new")]
            )

            def call() -> Any:
                return fn(books_dir, BOOK, "n1", "new", page=fp)

        try:
            return call(), None, fp.waits
        except AssertionError as exc:
            return None, str(exc), fp.waits


def _check_row(
    name: str, fn: Callable[..., Any], books_dir: Path, write_at: Optional[int]
) -> None:
    """一行门限律：写落在第 `write_at` 泵（None = 永远不写）。"""
    _assert_clock_premise()
    got, err, waits = _drive(name, fn, books_dir, write_at)
    if write_at is not None and write_at <= LAST_OBSERVABLE_WRITE:
        assert err is None, (
            f"{name}：写落在第 {write_at} 泵（≤ {LAST_OBSERVABLE_WRITE}）应当被看见，"
            f"却超时了，泵了 {len(waits)} 次：{err}"
        )
        assert waits == [50] * write_at, (
            f"{name}：应恰好泵 {write_at} 次、每次 50ms，实际 {len(waits)} 次：{sorted(set(waits))}"
        )
        if name == "wait_for_notes":
            assert got == helpers.read_notes(books_dir, BOOK)
            assert [r["id"] for r in got] == ["only"]
        else:
            assert got["id"] == "n1" and got["note_text"] == "new", got
        return
    assert err is not None, (
        f"{name}：写落在第 {write_at} 泵（≥ {EXPECTED_TIMEOUT_PUMPS} 或不写）不该被看见，"
        f"却在第 {len(waits)} 泵返回了 {got!r}"
    )
    assert len(waits) == EXPECTED_TIMEOUT_PUMPS, (
        f"{name}：8.0s / 50ms = {EXPECTED_TIMEOUT_PUMPS} 泵，超时时实际泵了 {len(waits)} 次"
    )
    assert waits == [50] * EXPECTED_TIMEOUT_PUMPS, sorted(set(waits))
    prefix = NOTES_TIMEOUT_PREFIX if name == "wait_for_notes" else TEXT_TIMEOUT_PREFIX
    # n = 160 时 wait_for_note_text 的消息尾巴自相矛盾（矩阵 Deferred #1，冻结文件里的事），
    # 所以只断前缀；「永远不写」那行消息里必须还是旧值。
    assert err.startswith(prefix), err
    if name == "wait_for_note_text" and write_at is None:
        assert "'note_text': 'old'" in err, err


def _budget_oracle(name: str, fn: Callable[..., Any]) -> None:
    """WI6-U2 / U4 / U5 共用的判据：死线两侧 159 / 160 与「永远不写」三行。"""
    for write_at in (LAST_OBSERVABLE_WRITE, EXPECTED_TIMEOUT_PUMPS, None):
        with tempfile.TemporaryDirectory(prefix="wi6-oracle-") as d:
            _check_row(name, fn, Path(d), write_at)


def _property_settings(fn: Callable[..., Any]) -> Callable[..., Any]:
    for n in BOUNDARY_EXAMPLES:
        fn = example(n=n)(fn)
    return settings(deadline=None, max_examples=60)(given(n=st.integers(1, 400))(fn))


@_property_settings
def test_wi6_u1_wait_for_notes_pumps_min_n_160_over_whole_domain(n: int) -> None:
    with tempfile.TemporaryDirectory(prefix="wi6u1-") as d:
        _check_row("wait_for_notes", helpers.wait_for_notes, Path(d), n)


@pytest.mark.parametrize("write_at", [159, 160, None])
def test_wi6_u2_wait_for_notes_boundary_triple(tmp_path: Path, write_at: Optional[int]) -> None:
    _check_row("wait_for_notes", helpers.wait_for_notes, tmp_path, write_at)


@_property_settings
def test_wi6_u3_wait_for_note_text_pumps_min_n_160_over_whole_domain(n: int) -> None:
    with tempfile.TemporaryDirectory(prefix="wi6u3-") as d:
        _check_row("wait_for_note_text", helpers.wait_for_note_text, Path(d), n)


@pytest.mark.parametrize("write_at", [159, 160, None])
def test_wi6_u4_wait_for_note_text_boundary_triple(
    tmp_path: Path, write_at: Optional[int]
) -> None:
    _check_row("wait_for_note_text", helpers.wait_for_note_text, tmp_path, write_at)


@pytest.mark.parametrize("name", sorted(DISK_POLLS))
def test_wi6_u5_boundary_oracle_kills_the_7_6s_mutant_in_memory(name: str) -> None:
    """差分收据：同一判据放过原函数、拒绝 7.6s 变体；变体只活在内存里。

    变体 `exec` 进一个私有命名空间（globals 是模块字典，`def` 绑进 `ns`，不绑回模块），
    helpers.py 的字节哈希与模块属性前后都断言不变——冻结文件不许在盘上动。
    """
    sha_before = hashlib.sha256(_HELPERS_PATH.read_bytes()).hexdigest()
    orig = getattr(helpers, name)
    src = inspect.getsource(orig)
    assert src.count(_DEADLINE_LINE) == 1, (
        f"{name}() 里的死线行不再是 {_DEADLINE_LINE!r}——变异成了空操作，收据作废"
    )
    mut = src.replace(_DEADLINE_LINE, _DEADLINE_LINE + " - 0.4")
    ns: Dict[str, Any] = {}
    exec(compile(mut, "<wi6-mutant>", "exec"), helpers.__dict__, ns)
    mutant = ns[name]
    assert mutant is not orig

    _budget_oracle(name, orig)
    with pytest.raises(AssertionError) as exc:
        _budget_oracle(name, mutant)
    msg = str(exc.value)
    pumps = [int(x) for x in re.findall(r"泵了 (\d+) 次", msg)]
    assert pumps and all(p != EXPECTED_TIMEOUT_PUMPS for p in pumps), (
        f"变体的失败消息里应带着它实际的泵数（≠ {EXPECTED_TIMEOUT_PUMPS}）：{msg}"
    )

    assert getattr(helpers, name) is orig, "变体绑回了模块属性"
    assert hashlib.sha256(_HELPERS_PATH.read_bytes()).hexdigest() == sha_before, (
        "helpers.py 在盘上被改了"
    )


def _mkdtemp_calls(tree: ast.AST) -> List[int]:
    offenders: List[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "mkdtemp":
            offenders.append(node.lineno)
        elif (
            isinstance(func, ast.Attribute)
            and func.attr == "mkdtemp"
            and isinstance(func.value, ast.Name)
            and func.value.id == "tempfile"
        ):
            offenders.append(node.lineno)
    return offenders


def test_wi6_u6_no_per_example_mkdtemp_left_in_module() -> None:
    """结构护栏：每个 Hypothesis 样本一个 `mkdtemp` 且从不清理，会在 /tmp 里攒垃圾。"""
    offenders = _mkdtemp_calls(ast.parse(Path(__file__).read_text(encoding="utf-8")))
    assert offenders == [], f"本模块第 {offenders} 行还在调 mkdtemp（不清理）；改用 TemporaryDirectory"


def test_wi2_u4_count_zero_with_file_absent_returns_immediately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _install_clock(monkeypatch)
    fp = _page_seeding(clock, tmp_path, None, [])
    assert helpers.wait_for_notes(tmp_path, BOOK, 0, page=fp) == []
    assert fp.waits == []


def test_wi2_u5_timeout_message_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _install_clock(monkeypatch)
    fp = _page_seeding(clock, tmp_path, 1, [_rec("lonely")])
    with pytest.raises(AssertionError) as exc:
        helpers.wait_for_notes(tmp_path, BOOK, 2, page=fp)
    msg = str(exc.value)
    assert msg.startswith("8.0s 内 notes.json 没有稳定到 2 条，实际 1 条："), msg
    assert "lonely" in msg, msg


@pytest.mark.parametrize("n", [1, 4])
def test_wi2_u15_count_decreases_to_target_after_delete_on_pump_n(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, n: int
) -> None:
    """修订 A2：盘上从 2 条删到 1 条——`>=` 的实现会在第一次读就带着 2 条返回。"""
    helpers.seed_notes(tmp_path, BOOK, [_rec("keep"), _rec("drop")])
    clock = _install_clock(monkeypatch)
    fp = _page_seeding(clock, tmp_path, n, [_rec("keep")])
    got = helpers.wait_for_notes(tmp_path, BOOK, 1, page=fp)
    assert got == helpers.read_notes(tmp_path, BOOK)
    assert [r["id"] for r in got] == ["keep"]
    assert fp.waits == [50] * n


@pytest.mark.parametrize("n", [1, 4])
def test_wi2_u15_count_zero_after_deleting_both_on_pump_n(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, n: int
) -> None:
    helpers.seed_notes(tmp_path, BOOK, [_rec("x"), _rec("y")])
    clock = _install_clock(monkeypatch)
    fp = _page_seeding(clock, tmp_path, n, [])
    assert helpers.wait_for_notes(tmp_path, BOOK, 0, page=fp) == []
    assert fp.waits == [50] * n


# ---------------------------------------------------------------------------
# wait_for_note_text
# ---------------------------------------------------------------------------


def test_wi2_u6_wait_for_note_text_page_is_required_keyword_only(tmp_path: Path) -> None:
    param = inspect.signature(helpers.wait_for_note_text).parameters.get("page")
    assert param is not None, "wait_for_note_text 没有 `page` 参数"
    assert param.kind is inspect.Parameter.KEYWORD_ONLY, f"`page` 必须仅限关键字，实际 {param.kind}"
    assert param.default is inspect.Parameter.empty, f"`page` 必须必填，实际缺省 {param.default!r}"
    with pytest.raises(TypeError):
        helpers.wait_for_note_text(tmp_path, "b", "n1", "x")  # type: ignore[call-arg]


@pytest.mark.parametrize("n", [1, 5])
def test_wi2_u7_returns_when_text_flips_on_pump_n(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, n: int
) -> None:
    helpers.seed_notes(tmp_path, BOOK, [_rec("n1", type="note", note_text="old")])
    clock = _install_clock(monkeypatch)
    fp = _page_seeding(clock, tmp_path, n, [_rec("n1", type="note", note_text="new")])
    rec = helpers.wait_for_note_text(tmp_path, BOOK, "n1", "new", page=fp)
    assert rec["id"] == "n1"
    assert rec["note_text"] == "new"
    assert fp.waits == [50] * n


def test_wi2_u8_timeout_text_mismatch_exact_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helpers.seed_notes(tmp_path, BOOK, [_rec("n1", type="note", note_text="old")])
    clock = _install_clock(monkeypatch)
    fp = _page_seeding(clock, tmp_path, None, [])
    with pytest.raises(AssertionError) as exc:
        helpers.wait_for_note_text(tmp_path, BOOK, "n1", "new", page=fp)
    msg = str(exc.value)
    assert "8.0s 内 n1 的 note_text 没有变成 'new'，当前是 " in msg, msg
    assert "'note_text': 'old'" in msg, msg
    assert fp.waits and set(fp.waits) == {50}, fp.waits


def test_wi2_u9_id_replaced_mid_poll_reports_gone_from_final_reread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helpers.seed_notes(tmp_path, BOOK, [_rec("n1", type="note", note_text="old")])
    clock = _install_clock(monkeypatch)
    fp = _page_seeding(clock, tmp_path, 3, [_rec("n2", type="note", note_text="old")])
    with pytest.raises(AssertionError) as exc:
        helpers.wait_for_note_text(tmp_path, BOOK, "n1", "new", page=fp)
    msg = str(exc.value)
    assert "已经不在 notes.json 里了" in msg, msg
    assert "n2" in msg, msg
    assert "当前是" not in msg, msg
    assert len(fp.waits) >= 3 and set(fp.waits) == {50}, fp.waits


# ---------------------------------------------------------------------------
# 结构护栏（CP1 裁定：只管这两个函数）
# ---------------------------------------------------------------------------


def _is_time_sleep(call: ast.Call) -> bool:
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "sleep"
        and isinstance(func.value, ast.Name)
        and func.value.id == "time"
    )


def _pumps_inside_loop(fn: ast.FunctionDef) -> List[int]:
    lines: List[int] = []

    def visit(node: ast.AST, in_loop: bool) -> None:
        for child in ast.iter_child_nodes(node):
            child_in_loop = in_loop or isinstance(child, (ast.While, ast.For))
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "wait_for_timeout"
                and in_loop
            ):
                lines.append(child.lineno)
            visit(child, child_in_loop)

    visit(fn, False)
    return lines


def test_wi2_u10_poll_bodies_pump_inside_loop_and_never_time_sleep() -> None:
    tree = ast.parse(_HELPERS_PATH.read_text(encoding="utf-8"))
    found = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in DISK_POLLS
    }
    assert set(found) == DISK_POLLS, f"helpers.py 里找不到 {sorted(DISK_POLLS - set(found))}"
    for name, fn in sorted(found.items()):
        sleeps = [
            n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call) and _is_time_sleep(n)
        ]
        assert sleeps == [], f"{name}() 里还有 time.sleep（第 {sleeps} 行）——它饿死出网闸回调"
        pumps = _pumps_inside_loop(fn)
        assert pumps, f"{name}() 的循环里没有 `.wait_for_timeout(...)`——轮询期间没泵浏览器"


def _call_sites_missing_page(root: Path, exclude: Path) -> List[str]:
    offenders: List[str] = []
    for path in sorted(root.rglob("*.py")):
        if path.resolve() == exclude.resolve() or "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else None
            )
            if name not in DISK_POLLS:
                continue
            if not any(kw.arg == "page" for kw in node.keywords):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} {name}()")
    return offenders


def test_wi2_u11_every_call_site_under_tests_passes_page() -> None:
    offenders = _call_sites_missing_page(REPO_ROOT / "tests", Path(__file__))
    assert offenders == [], "这些调用点没传 page=：\n" + "\n".join(offenders)


def test_wi2_u11_sweep_actually_sees_call_sites() -> None:
    """防空转：扫描得真的看见调用点（否则上一条对一个空集合恒真）。"""
    seen = 0
    for path in (REPO_ROOT / "tests" / "e2e").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                f = node.func
                nm = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
                if nm in DISK_POLLS:
                    seen += 1
    assert seen >= 40, f"只扫到 {seen} 处调用点，扫描范围不对"
