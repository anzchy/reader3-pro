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
import importlib.util
import inspect
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

import pytest
from hypothesis import HealthCheck, given, settings
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


@settings(
    deadline=None,
    max_examples=60,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(n=st.integers(1, 150) | st.integers(170, 400))
def test_wi2_u3_budget_is_exactly_8s_of_pumps(
    monkeypatch: pytest.MonkeyPatch, n: int
) -> None:
    books_dir = Path(tempfile.mkdtemp(prefix="wi2u3-"))
    with monkeypatch.context() as mp:
        clock = FakeClock()
        mp.setattr(
            helpers, "time", SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep)
        )
        fp = _page_seeding(clock, books_dir, n, [_rec("only")])
        if n <= 150:
            got = helpers.wait_for_notes(books_dir, BOOK, 1, page=fp)
            assert [r["id"] for r in got] == ["only"]
            assert len(fp.waits) == n
        else:
            with pytest.raises(AssertionError) as exc:
                helpers.wait_for_notes(books_dir, BOOK, 1, page=fp)
            assert str(exc.value).startswith("8.0s 内 notes.json 没有稳定到 1 条，实际 0 条："), (
                str(exc.value)
            )
            assert len(fp.waits) <= 161, f"8.0s 的预算泵了 {len(fp.waits)} 次（每次 50ms）"


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
