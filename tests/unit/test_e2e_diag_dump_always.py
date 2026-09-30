"""019 WI-2（决定 D2）：`scripts/e2e_diag_dump.py` 的 opt-in 常开 dump（`E2E_DIAG_ALWAYS=1`）。

原插件只在 call 阶段**失败**时 dump。一轮全绿的压力臂于是拿不到任何 start→reqStart 数据，
「慢请求簇没了」就只能靠「没有失败」来撑——那是无观测的通过。常开模式让每条带 `page`
的用例都 dump 一份 fetch / perf 台账。

律（有限域上的全函数）：某节点写 dump 文件 **当且仅当**
`rep.when == "call"` 且（`rep.failed` 或 `os.environ.get("E2E_DIAG_ALWAYS") == "1"`）且该 item
有 `page` funcarg。开关必须在**钩子执行时**读（不能像 `_OUT` 那样在 import 时定死），
否则同一进程里无法逐例改变它。

矩阵：`.claude/tdd-guardian/tests-20260930-111704.md` §WI-2 的 WI2-U13 / WI2-U14。
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_DUMP_PATH = REPO_ROOT / "scripts" / "e2e_diag_dump.py"
_spec = importlib.util.spec_from_file_location("reader3_e2e_diag_dump_under_test", _DUMP_PATH)
assert _spec and _spec.loader, f"无法按路径加载 {_DUMP_PATH}"
diag = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = diag
_spec.loader.exec_module(diag)

FLAG = "E2E_DIAG_ALWAYS"
WHENS = ("setup", "call", "teardown")
OUTCOMES = ("passed", "failed", "skipped")
FLAGS: tuple[Optional[str], ...] = (None, "1", "0", "")


class FakeDiagPage:
    url = "http://127.0.0.1:1/read/x/0"

    def evaluate(self, _script: str, *_args: Any) -> Any:
        return []


def _drive(item: Any, when: str, outcome: str) -> None:
    rep = SimpleNamespace(
        when=when,
        failed=outcome == "failed",
        passed=outcome == "passed",
        skipped=outcome == "skipped",
    )
    gen = diag.pytest_runtest_makereport(item, None)
    next(gen)
    with pytest.raises(StopIteration):
        gen.send(SimpleNamespace(get_result=lambda: rep))


def _set_flag(monkeypatch: pytest.MonkeyPatch, flag: Optional[str]) -> None:
    if flag is None:
        monkeypatch.delenv(FLAG, raising=False)
    else:
        monkeypatch.setenv(FLAG, flag)


def test_wi2_u13_write_iff_call_and_failed_or_flag_is_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = set()
    observed = set()
    for i, (when, outcome, flag) in enumerate(itertools.product(WHENS, OUTCOMES, FLAGS)):
        out = tmp_path / f"d{i}"
        monkeypatch.setattr(diag, "_OUT", out)
        _set_flag(monkeypatch, flag)
        node = f"tests/e2e/x.py::t[{when}-{outcome}-{flag}]"
        item = SimpleNamespace(nodeid=node, funcargs={"page": FakeDiagPage()})
        _drive(item, when, outcome)

        combo = (when, outcome, flag)
        if when == "call" and (outcome == "failed" or flag == "1"):
            expected.add(combo)
        files = sorted(out.glob("*.json")) if out.exists() else []
        if files:
            observed.add(combo)
            assert len(files) == 1, f"{combo} 写了 {len(files)} 份"
            record = json.loads(files[0].read_text(encoding="utf-8"))
            assert {"test", "fetch", "perf", "diag", "url"} <= set(record), record
            assert record["test"] == node
    # 自检：call×failed 在 4 种开关下各一行，再加 call×passed / call×skipped 在 flag="1" 下各一行。
    assert len(expected) == 4 + 2, expected
    assert observed == expected, (
        f"多写：{sorted(observed - expected, key=str)}；漏写：{sorted(expected - observed, key=str)}"
    )


def test_wi2_u14_items_without_page_are_never_dumped_even_with_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "d"
    monkeypatch.setattr(diag, "_OUT", out)
    monkeypatch.setenv(FLAG, "1")
    item = SimpleNamespace(nodeid="tests/e2e/x.py::no_page", funcargs={})
    _drive(item, "call", "passed")
    assert not out.exists() or list(out.glob("*.json")) == []
