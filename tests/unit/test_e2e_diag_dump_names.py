"""019 WI-7（审计 #1）：`scripts/e2e_diag_dump.py` 的 dump 文件名不许撞车。

原写法 `nodeid.replace("/", "_").replace(":", "_")[:150]`：两条 nodeid 只要前 150 个字符相同
就落进同一个文件，后写的静默盖掉先写的。W6-C7 的两个参数（158 / 161 字符，共享前 152 个
字符 `…[chromium-collapsed_`）正好撞上——一轮压力臂里 `collapsed_range` 的证据会被
`collapsed_snapshot` 覆盖掉，而且没有任何报错。另有两个潜伏问题：`[:150]` 数的是字符不是
字节，150 个 CJK 字符约 450 字节，超过 NAME_MAX（APFS / ext4 都是 255）直接 `OSError`；
nodeid 里的 NUL 则是 `ValueError`。
（⬛ 2026-10-01，023 #65：该模块迁入 `tests/e2e/baseline_1b/`，两条 id 实测变为 170 / 173 字符、
共享前 164 个字符；上面 158 / 161 / 152 是迁移前的测量。U1 现场计算共享前缀并断「> 150」，同时仍钉 170 / 173 这两个实测长度——下次迁移要随之重测。）

钉住的方案（矩阵 §WI-7「Chosen scheme」）：

    prefix = 把 [A-Za-z0-9._[]-] 以外的字符换成 "_"，再截到 120 个字符
    digest = sha256(完整 nodeid 的 UTF-8).hexdigest()[:12]      # 完整，不是截断或净化后的
    filename = f"{prefix}-{digest}.json"

摘要**总是**追加（短 id 也追加），所以短 id 与长 id 截断后永远碰不到同一个名字；前缀纯
ASCII，文件名至多 138 字节。用 sha256 而不是 `hash()`：call 阶段与 teardown 阶段的两次写
必须落进同一个文件，不能随 `PYTHONHASHSEED` 变。

律：一组 nodeid 互不相同的记录写进同一目录后，文件数 == 记录数，且读回的 `test` 字段集合
等于写入集合（单射 + 守恒）；同一 nodeid 再写一次覆盖同一个文件（幂等）。

矩阵：`.claude/tdd-guardian/tests-20260930-235900.md` §WI-7（WI7-U1..U6）。
测试只驱动公开副作用：`_write(record)`（把 `diag._OUT` 换成临时目录），然后看目录。
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[2]
_DUMP_PATH = REPO_ROOT / "scripts" / "e2e_diag_dump.py"
_spec = importlib.util.spec_from_file_location("reader3_e2e_diag_dump_names_under_test", _DUMP_PATH)
assert _spec and _spec.loader, f"无法按路径加载 {_DUMP_PATH}"
diag = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = diag
_spec.loader.exec_module(diag)

# 2026-10-01 023 #65：W6-C7 所在模块从 `tests/e2e/` 根迁入 `tests/e2e/baseline_1b/`，
# 路径与下面两条 nodeid 随之改写（各长 12 个字符 `baseline_1b/`）。
_W6_C7_FILE = REPO_ROOT / "tests" / "e2e" / "baseline_1b" / "test_notes_write_failure_is_attributable.py"
_W6_C7_FUNC = "test_w6_c7_create_empty_quote_guard_reports_requested_false_and_sends_nothing"
# 2026-10-01（023 #65 迁移之后）用
# `uv run pytest tests/e2e --collect-only -q --browser chromium | grep collapsed` 实测确认的两条。
A = (
    "tests/e2e/baseline_1b/test_notes_write_failure_is_attributable.py::"
    "test_w6_c7_create_empty_quote_guard_reports_requested_false_and_sends_nothing"
    "[chromium-collapsed_range]"
)
B = (
    "tests/e2e/baseline_1b/test_notes_write_failure_is_attributable.py::"
    "test_w6_c7_create_empty_quote_guard_reports_requested_false_and_sends_nothing"
    "[chromium-collapsed_snapshot]"
)
NAME_RE = re.compile(r"^[A-Za-z0-9._\[\]-]{0,120}-[0-9a-f]{12}\.json$")
MAX_NAME_BYTES = 120 + 1 + 12 + len(".json")  # 138
#: 除代理项外的全部码位——CJK、`/`、`:`、`\`、`*`、空格、`\x00` 都在里面。
ANY_CHAR = st.characters(blacklist_categories=("Cs",))


def _write_into(out: Path, records: List[Dict[str, Any]]) -> List[str]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(diag, "_OUT", out)
        for rec in records:
            diag._write(rec)
    return sorted(os.listdir(out))


def _load_all(out: Path) -> List[Dict[str, Any]]:
    return [json.loads((out / n).read_text(encoding="utf-8")) for n in sorted(os.listdir(out))]


def _sha12(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def test_wi7_u1_two_real_w6_c7_nodeids_land_in_two_files(tmp_path: Path) -> None:
    # 023 #65 迁移后重测：158 / 161 → 170 / 173（+12 = `baseline_1b/`）。前提「共享前缀 > 150」
    # 改为现场计算，不再写死 152——下一次迁移不能悄悄把它证伪。
    assert len(A) == 170 and len(B) == 173, (len(A), len(B))
    shared = len(os.path.commonprefix([A, B]))
    assert shared > 150, f"前提：两条 id 的共享前缀必须超过 150 个字符（实为 {shared}），旧的 [:150] 才会撞车"
    assert A[:150] == B[:150], "旧方案 [:150] 下两条 id 撞成同一个名字"
    assert A[:120] == B[:120], "现方案的 120 字符前缀完全相同，两个文件名只靠摘要区分"
    names = _write_into(tmp_path, [
        {"test": A, "fetch": [], "k": "a"},
        {"test": B, "fetch": [], "k": "b"},
    ])
    assert len(names) == 2, f"两条不同的 nodeid 只落了 {len(names)} 个文件：{names}"
    assert {r["test"]: r["k"] for r in _load_all(tmp_path)} == {A: "a", B: "b"}, (
        "B 的写盖掉了 A 的证据"
    )


@settings(deadline=None, max_examples=60)
@given(
    prefix=st.text(ANY_CHAR, min_size=140, max_size=300),
    suffixes=st.sets(st.text(ANY_CHAR, min_size=1, max_size=20), min_size=2, max_size=8),
)
def test_wi7_u2_conservation_over_long_shared_prefix_id_sets(
    prefix: str, suffixes: set
) -> None:
    ids = sorted(prefix + s for s in suffixes)
    with tempfile.TemporaryDirectory(prefix="wi7u2-") as d:
        out = Path(d)
        names = _write_into(out, [{"test": nid, "i": k} for k, nid in enumerate(ids)])
        assert len(names) == len(ids), f"{len(ids)} 条不同 id 只落了 {len(names)} 个文件"
        back = {r["test"]: r["i"] for r in _load_all(out)}
        assert back == {nid: k for k, nid in enumerate(ids)}


@settings(deadline=None, max_examples=100)
@given(nodeid=st.text(ANY_CHAR, max_size=600))
@example(nodeid="章" * 150)
@example(nodeid="tests/e2e/x.py::t[\x00]")
@example(nodeid="")
@example(nodeid="../../etc/passwd")
def test_wi7_u3_every_name_is_bounded_safe_and_contained(nodeid: str) -> None:
    with tempfile.TemporaryDirectory(prefix="wi7u3-") as d:
        out = Path(d)
        names = _write_into(out, [{"test": nodeid}])
        assert len(names) == 1, names
        name = names[0]
        assert NAME_RE.match(name), f"文件名不在安全字母表 / 长度内：{name!r}"
        assert len(name.encode("utf-8")) <= MAX_NAME_BYTES, len(name.encode("utf-8"))
        assert (out / name).resolve().parent == out.resolve(), name
        assert json.loads((out / name).read_text(encoding="utf-8"))["test"] == nodeid


@settings(deadline=None, max_examples=60)
@given(nid=st.text(ANY_CHAR, max_size=400))
@example(nid=A)
@example(nid=B)
def test_wi7_u4_teardown_rewrite_overwrites_the_same_file(nid: str) -> None:
    """镜像 `_r3_diag_capture` 的 teardown 路径：同一条 record 补上 late_* 再写一次。"""
    with tempfile.TemporaryDirectory(prefix="wi7u4-") as d:
        out = Path(d)
        rec: Dict[str, Any] = {"test": nid, "fetch": []}
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(diag, "_OUT", out)
            diag._write(rec)
            rec["late_fetch"] = ["x"]
            diag._write(rec)
        names = sorted(os.listdir(out))
        assert len(names) == 1, f"同一 nodeid 的两次写分裂成了 {names}"
        assert _load_all(out) == [{"test": nid, "fetch": [], "late_fetch": ["x"]}]


def test_wi7_u5_exact_names_for_short_and_real_long_id(tmp_path: Path) -> None:
    """方案钉子：唯一一条部分复述公式的用例；U1..U4 承担行为。"""
    short = "tests/e2e/x.py::t[a-b]"
    short_dir = tmp_path / "short"
    long_dir = tmp_path / "long"
    assert _write_into(short_dir, [{"test": short}]) == [
        "tests_e2e_x.py__t[a-b]-" + _sha12(short) + ".json"
    ]
    expected_long = A.replace("/", "_").replace(":", "_")[:120] + "-" + _sha12(A) + ".json"
    assert _write_into(long_dir, [{"test": A}]) == [expected_long]
    # 摘要取自**完整** A，不是 A[:120]：两者不同，文件用的是前者。
    assert _sha12(A) != _sha12(A[:120])
    assert _sha12(A[:120]) not in os.listdir(long_dir)[0]


def _parametrize_values(fn: ast.FunctionDef, argname: str) -> Any:
    for dec in fn.decorator_list:
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and dec.func.attr == "parametrize"
            and dec.args
            and isinstance(dec.args[0], ast.Constant)
            and dec.args[0].value == argname
        ):
            return ast.literal_eval(dec.args[1])
    return None


def test_wi7_u6_literal_w6_c7_ids_still_match_the_real_test() -> None:
    assert _W6_C7_FILE.is_file(), f"W6-C7 所在文件不在 {_W6_C7_FILE}——U1 的字面量与真实路径已脱节"
    # id 里的路径与读 AST 的文件必须是同一个（023 #65 迁移时两者要一起动）。
    rel = _W6_C7_FILE.relative_to(REPO_ROOT).as_posix()
    assert A.startswith(rel + "::") and B.startswith(rel + "::"), (rel, A, B)
    tree = ast.parse(_W6_C7_FILE.read_text(encoding="utf-8"))
    fns = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == _W6_C7_FUNC]
    assert len(fns) == 1, f"{_W6_C7_FILE.name} 里找不到 {_W6_C7_FUNC}——U1 的字面量已漂移"
    assert _parametrize_values(fns[0], "route_in") == ["collapsed_range", "collapsed_snapshot"]
    assert A.endswith(f"{_W6_C7_FUNC}[chromium-collapsed_range]")
    assert B.endswith(f"{_W6_C7_FUNC}[chromium-collapsed_snapshot]")
