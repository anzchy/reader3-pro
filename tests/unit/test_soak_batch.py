"""`scripts/soak_run.py` 的批次判决：WI-1 · 批次声明解析（纯函数）。

矩阵：`.claude/tdd-guardian/tests-20260929-013056.md` `## WI-1` 的 D1–D8，以及文末两节绑定裁定
（Q1：ASCII `|` 的候选行 fail closed）。计划：`.claude/tdd-guardian/plan-20260929-013056.md` `### WI-1:`。

批次声明写在台账表头（`> - `B1`｜`起始 ts`｜`commit`｜`suite_hash`｜`browser`｜`os``），
不是表的第九列。语法严格、fail closed：任一候选行不合形状、或 ID 重复，整次解析抛
`BatchDeclarationError`——B2 的一个笔误挡住 B1 的判决，是刻意的。

`tests/unit/test_soak_run.py` 有红收据且只许追加，本文件不碰它；模块用独立名字
`soak_run_under_test_batch` 按路径加载。只读真台账，不写。
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Optional, Tuple

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from test_soak_log_contract import first_table, split_row  # type: ignore[import-not-found]

REPO_ROOT = Path(__file__).resolve().parents[2]
SOAK_RUN_PATH = REPO_ROOT / "scripts" / "soak_run.py"
REAL_LEDGER = REPO_ROOT / "docs" / "plans" / "20260816-tech-stack-migration" / "tasks" / "soak-log.md"

_CACHE: Dict[str, ModuleType] = {}


def _soak() -> ModuleType:
    name = "soak_run_under_test_batch"
    if name in _CACHE:
        return _CACHE[name]
    spec = importlib.util.spec_from_file_location(name, SOAK_RUN_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # 先登记再执行：`from __future__ import annotations` 下的 @dataclass 要经 sys.modules 解析注解。
    sys.modules[name] = module
    spec.loader.exec_module(module)
    _CACHE[name] = module
    return module


def _api():  # type: ignore[no-untyped-def]
    mod = _soak()
    missing = [a for a in ("parse_batch_declarations", "BatchDeclaration", "BatchDeclarationError") if not hasattr(mod, a)]
    assert not missing, f"scripts/soak_run.py 缺少 {missing}（WI-1 的交付）"
    return mod.parse_batch_declarations, mod.BatchDeclaration, mod.BatchDeclarationError


def _real_text() -> str:
    return REAL_LEDGER.read_text(encoding="utf-8")


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)  # type: ignore[misc]


def _render(fields: List[str], sep: str = "｜", trailing: str = "") -> str:
    return "> - " + sep.join(f"`{f}`" for f in fields) + trailing


B1_FIELDS = ["B1", "2026-09-28T15:13:15Z", "9be446c", "1e868c7bf811", "chromium-1234", "darwin-25.3.0"]
B1_LINE = _render(B1_FIELDS)
B0_LINE = _render(["B0", "2026-09-27T00:00:00Z", "d3ceaf4", "1e868c7bf811", "chromium-1234", "darwin-25.3.0"])
#: 真台账里已判过的批次，按声明顺序（只许追加；再判一批就在这里追加，不改前面的）。
HISTORICAL_BATCH_IDS: List[str] = ["B1", "B2"]
#: 合成「第二批」的 ID。原先用 `B2`，真台账 2026-10-01 声明了真 `B2` 后两者撞名（D1c 守着这条）。
SYNTH_ID = "Z2"
# 抄自 2026-09-29 真台账表头的近似行（D2 语料，也是 D3 的噪声源）。表头改写后不必同步——真台账由 D1 直接覆盖。
# 真台账表头里的近似行，逐字抄来（D2 语料，也是 D3 的噪声源）。
FORMAT_DESCRIPTION_LINE = (
    "> 每批开跑前在下面追一行声明，格式：`批次 ID｜起始 ts_utc｜commit｜suite_hash｜browser｜os`。依赖锁不单列——"
)
NEAR_MISS_LINES: List[str] = [
    FORMAT_DESCRIPTION_LINE,
    "> - ~~**次数**：`grep -cE '^\\| 20[0-9]{2}-' docs/plans/20260816-tech-stack-migration/tasks/soak-log.md`~~",
    "> - ~~**跨度**：先取首行与第十行的 `ts_utc` ——",
    ">   `grep -E '^\\| 20[0-9]{2}-' docs/plans/20260816-tech-stack-migration/tasks/soak-log.md | sed -n '1p;10p'`；~~",
    "> - **本批的行**：取批次声明里的起始 `ts_utc`，数它起的前 10 行 ——",
    ">   `grep -E '^\\| 20[0-9]{2}-' docs/plans/20260816-tech-stack-migration/tasks/soak-log.md | awk -v s='<起始 ts_utc>' '$2>=s' | head -10`",
    "> - **是否同批且全绿**：把上一条的输出接到",
    ">   `awk '{print $4, $6, $10, $12, $14}' | sort | uniq -c`（依次是 commit / result / suite_hash / browser / os）。",
    ">   ——在 `9be446c` 的干净 detached worktree 里跑（被测树与该 SHA 逐字节一致；本声明所在的 commit 只改台账）；",
    ">   行用 `--ledger` 写回主工作区，10 次跑完前不提交。",
    ">   **判定：通过**——上面的核对命令输出恰好一行 `10 9be446c green 1e868c7bf811 chromium-1234 darwin-25.3.0`",
    "> - `B9` 只有一个反引号记号，没有任何分隔符",
]


def _insert_after_b1_block(text: str, line: str) -> str:
    """把 `line` 插在 B1 声明及其续行之后（第一条不以 `>   ` 开头的行之前）。"""
    lines = text.split("\n")
    idx = next(i for i, raw in enumerate(lines) if raw.startswith("> - `B1`"))
    j = idx + 1
    while j < len(lines) and lines[j].startswith(">   "):
        j += 1
    return "\n".join(lines[:j] + [line] + lines[j:])


# ---------------------------------------------------------------------------
# D1 · 真台账恰好给出 B1
# ---------------------------------------------------------------------------


# 2026-10-02 改写：原先断「恰好声明 B1」，`B2` 一追加就红——那是把「截至 09-29 的台账」当成了永久不变量。
# 台账只许追加，所以钉的是**已判过的历史前缀**：声明顺序以 `HISTORICAL_BATCH_IDS` 开头、`B1` 逐字段不变；
# 之后再追加的批次不影响本用例。强度没降：B1 每个字段照旧逐一比对，另把 B2 也钉进历史前缀（D1b）。
def test_d1_real_ledger_declares_historical_batches_first_b1_exact() -> None:
    parse, BatchDeclaration, _ = _api()
    result = parse(_real_text())
    assert list(result)[: len(HISTORICAL_BATCH_IDS)] == HISTORICAL_BATCH_IDS, (
        f"真台账的批次声明应当以 {HISTORICAL_BATCH_IDS} 开头（只许追加），得到 {list(result)}"
    )
    d = result["B1"]
    expected = BatchDeclaration(
        "B1", _utc(2026, 9, 28, 15, 13, 15), "9be446c", "1e868c7bf811", "chromium-1234", "darwin-25.3.0"
    )
    for name in ("batch_id", "start_ts", "commit", "suite_hash", "browser", "os"):
        assert getattr(d, name) == getattr(expected, name), f"字段 {name}：{getattr(d, name)!r} ≠ {getattr(expected, name)!r}"
    assert d == expected
    assert d.start_ts.tzinfo is not None, "start_ts 必须带 UTC 时区（Q3）"
    assert d.start_ts.utcoffset().total_seconds() == 0


def test_d1b_real_ledger_b2_exact() -> None:
    parse, BatchDeclaration, _ = _api()
    d = parse(_real_text())["B2"]
    assert d == BatchDeclaration(
        "B2", _utc(2026, 10, 1, 16, 56, 16), "94dd1e0", "abfc0cc9c59e", "chromium-1234", "darwin-25.3.0"
    )


def test_d1c_synthetic_batch_id_is_not_declared_in_real_ledger() -> None:
    """合成批次（C2–C4、D5、D6）用的 ID 若与真台账撞名，插进去就成了「重复声明」，用例会因错的理由红/绿。"""
    parse, _, _ = _api()
    assert SYNTH_ID not in parse(_real_text()), f"合成批次 ID {SYNTH_ID!r} 已被真台账占用，换一个"


# ---------------------------------------------------------------------------
# D2 · 表头里的近似行都不是声明
# ---------------------------------------------------------------------------


def test_d2_near_miss_lines_are_not_declarations() -> None:
    parse, _, _ = _api()
    assert parse("\n".join(NEAR_MISS_LINES)) == {}


# ---------------------------------------------------------------------------
# D3 · 往返律：生成的声明 ＋ 穿插噪声 → 原样解析回来
# ---------------------------------------------------------------------------

_HEX = "0123456789abcdef"
_FREE_TEXT = st.text(
    alphabet=st.characters(blacklist_characters="`｜|\n\r", blacklist_categories=("Cs",)),
    min_size=1,
    max_size=20,
).filter(lambda s: not s[0].isspace())


@st.composite
def _declarations(draw):  # type: ignore[no-untyped-def]
    _, BatchDeclaration, _ = _api()
    ids = draw(
        st.lists(st.from_regex(r"[A-Za-z0-9_-]{1,12}", fullmatch=True), min_size=1, max_size=6, unique=True)
    )
    out = []
    for bid in ids:
        ts = draw(
            st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2099, 12, 31, 23, 59, 59), timezones=st.just(timezone.utc))
        ).replace(microsecond=0)
        commit = draw(st.text(alphabet=_HEX, min_size=7, max_size=40))
        suite_hash = draw(st.text(alphabet=_HEX, min_size=12, max_size=12))
        browser = draw(_FREE_TEXT)
        os_ = draw(_FREE_TEXT)
        out.append(BatchDeclaration(bid, ts, commit, suite_hash, browser, os_))
    return out


_NOISE = st.one_of(
    st.sampled_from(NEAR_MISS_LINES),
    st.text(alphabet=st.characters(blacklist_characters="\n", blacklist_categories=("Cs",)), max_size=30).filter(
        lambda s: not s.startswith(">")
    ),
)


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(decls=_declarations(), data=st.data())
def test_d3_round_trip_with_interleaved_noise(decls, data) -> None:  # type: ignore[no-untyped-def]
    parse, _, _ = _api()
    lines: List[str] = []
    for d in decls:
        lines.extend(data.draw(st.lists(_NOISE, max_size=5)))
        trailing = " " * data.draw(st.integers(0, 3))
        lines.append(
            _render(
                [d.batch_id, d.start_ts.strftime("%Y-%m-%dT%H:%M:%SZ"), d.commit, d.suite_hash, d.browser, d.os],
                trailing=trailing,
            )
        )
    lines.extend(data.draw(st.lists(_NOISE, max_size=5)))
    assert parse("\n".join(lines)) == {d.batch_id: d for d in decls}


# ---------------------------------------------------------------------------
# D4 · 不合形状的候选行抛错，且报出那一行
# ---------------------------------------------------------------------------


def _b2(**over: str) -> List[str]:
    f = {
        "id": "B2",
        "ts": "2026-09-29T00:00:00Z",
        "commit": "9be446c",
        "hash": "1e868c7bf811",
        "browser": "chromium-1234",
        "os": "darwin-25.3.0",
    }
    f.update(over)
    return [f["id"], f["ts"], f["commit"], f["hash"], f["browser"], f["os"]]


MALFORMED: Dict[str, str] = {
    "duplicate_id": _render(_b2(id="B0")),
    "five_fields": _render(_b2()[:5]),
    "seven_fields": _render(_b2() + ["extra"]),
    "ts_space": _render(_b2(ts="2026-09-28 15:13:15")),
    "ts_no_z": _render(_b2(ts="2026-09-28T15:13:15")),
    "ts_feb_30": _render(_b2(ts="2026-02-30T00:00:00Z")),
    "hash_7_hex": _render(_b2(hash="1e868c7")),
    "hash_11_hex": _render(_b2(hash="1e868c7bf81")),
    "hash_13_hex": _render(_b2(hash="1e868c7bf811a")),
    "hash_upper": _render(_b2(hash="1E868C7BF811")),
    "commit_6_hex": _render(_b2(commit="9be446")),
    "commit_41_hex": _render(_b2(commit="a" * 41)),
    "commit_non_hex": _render(_b2(commit="9be446g")),
    "id_with_space": _render(_b2(id="B 2")),
    "empty_os": _render(_b2(os="")),
    "empty_browser": _render(_b2(browser="")),
    "trailing_text": _render(_b2(), trailing=" 终止"),
    "one_ascii_pipe": "> - `B2`｜`2026-09-29T00:00:00Z`|`9be446c`｜`1e868c7bf811`｜`chromium-1234`｜`darwin-25.3.0`",
}


@pytest.mark.parametrize("case", sorted(MALFORMED))
def test_d4_malformed_candidate_raises_naming_line(case: str) -> None:
    parse, _, BatchDeclarationError = _api()
    mutated = MALFORMED[case]
    text = "\n".join([B0_LINE, B1_LINE, mutated])
    with pytest.raises(BatchDeclarationError) as ei:
        parse(text)
    assert mutated.strip() in str(ei.value), f"错误信息里应当带出那一行：{ei.value}"
    if case == "duplicate_id":
        assert "B0" in str(ei.value)


# ---------------------------------------------------------------------------
# D5 · B2 不合形状挡住 B1（全局严格）
# ---------------------------------------------------------------------------


def test_d5_malformed_b2_blocks_b1() -> None:
    parse, _, BatchDeclarationError = _api()
    bad = f"> - `{SYNTH_ID}`｜`2026-09-29T00:00:00Z`｜`9be446c`｜`1e868c7bf811`｜`chromium-1234`"
    text = _insert_after_b1_block(_real_text(), bad)
    with pytest.raises(BatchDeclarationError):
        parse(text)


# ---------------------------------------------------------------------------
# D6 · 全 ASCII 分隔符的声明 fail closed（Q1）
# ---------------------------------------------------------------------------


def test_d6_all_ascii_pipe_declaration_fails_closed() -> None:
    parse, _, BatchDeclarationError = _api()
    ascii_line = f"> - `{SYNTH_ID}`|`2026-09-29T00:00:00Z`|`9be446c`|`1e868c7bf811`|`chromium-1234`|`darwin-25.3.0`"
    text = _insert_after_b1_block(_real_text(), ascii_line)
    with pytest.raises(BatchDeclarationError) as ei:
        parse(text)
    assert ascii_line.strip() in str(ei.value)


# ---------------------------------------------------------------------------
# D7 · 字段形状的闭区间边界都接受
# ---------------------------------------------------------------------------

BOUNDARY: Dict[str, List[str]] = {
    "commit_7": ["a", "2026-09-29T00:00:00Z", "abcdef0", "1e868c7bf811", "chromium-1234", "darwin-25.3.0"],
    "commit_40": ["x-Y_9", "2026-09-29T00:00:00Z", "0123456789abcdef0123456789abcdef01234567", "1e868c7bf811", "c", "o"],
    "browser_one_char": ["B3", "2026-09-29T00:00:00Z", "9be446c", "1e868c7bf811", "c", "darwin-25.3.0"],
    "ts_year_end": ["B4", "2026-12-31T23:59:59Z", "9be446c", "1e868c7bf811", "chromium-1234", "darwin-25.3.0"],
}


@pytest.mark.parametrize("case", sorted(BOUNDARY))
def test_d7_boundary_shapes_accepted(case: str) -> None:
    parse, BatchDeclaration, _ = _api()
    f = BOUNDARY[case]
    result = parse(_render(f))
    ts = datetime.strptime(f[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert result == {f[0]: BatchDeclaration(f[0], ts, f[2], f[3], f[4], f[5])}


# ---------------------------------------------------------------------------
# D8 · 声明是不可变记录
# ---------------------------------------------------------------------------


def test_d8_declaration_is_frozen_dataclass() -> None:
    parse, _, _ = _api()
    d = parse(_real_text())["B1"]
    assert dataclasses.is_dataclass(d)
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.commit = "x"  # type: ignore[misc]


# ===========================================================================
# WI-2 · 台账行读取 ＋ 批次判决（纯函数）
#
# 矩阵：`## WI-2` 的 R1–R3、V1–V11，文末绑定裁定 Q2 / Q3 / Q4 / Q6，以及第二轮 V12。
# 行的读取以 `test_soak_log_contract.first_table` / `split_row` 为预言机，不拿实现自己的解析器对账。
# 合成行一律渲染成 Markdown 表再经 `ledger_rows` 读回——测试不依赖 `LedgerRow` 的构造签名。
# ===========================================================================

HEADER_LINE = "| ts_utc | commit | result | duration_s | suite_hash | browser | os | log |"
SEP_LINE = "|---|---|---|---|---|---|---|---|"
COLUMNS = ("ts_utc", "commit", "result", "duration_s", "suite_hash", "browser", "os", "log")
PRE_BATCH_COMMITS = {"baddc61", "4178b8a", "8e1cf48", "d3ceaf4"}


def _api2():  # type: ignore[no-untyped-def]
    mod = _soak()
    missing = [a for a in ("ledger_rows", "batch_verdict", "BatchVerdict", "LedgerRow", "BATCH_SIZE") if not hasattr(mod, a)]
    assert not missing, f"scripts/soak_run.py 缺少 {missing}（WI-2 的交付）"
    return mod


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _table(cells_rows: List[List[str]]) -> str:
    body = ["| " + " | ".join(c) + " |" for c in cells_rows]
    return "\n".join(["# 台账", "", HEADER_LINE, SEP_LINE, *body, "", "---", ""])


def _rows(cells_rows: List[List[str]]):  # type: ignore[no-untyped-def]
    return _api2().ledger_rows(_table(cells_rows))


def _b1_decl():  # type: ignore[no-untyped-def]
    parse, _, _ = _api()
    return parse(_real_text())["B1"]


def _real_cells() -> List[List[str]]:
    return [split_row(ln) for ln in first_table(_real_text())[1]]


#: B1 判定时（2026-09-29）台账的行数与各行 ts。台账只许追加，这一段永远是真台账的前缀。
B1_ERA_ROWS = 14
B1_ERA_TS: List[str] = [
    "2026-09-23T10:51:23Z",
    "2026-09-25T22:31:21Z",
    "2026-09-27T04:00:05Z",
    "2026-09-28T04:00:05Z",
    "2026-09-28T15:14:07Z",
    "2026-09-28T15:15:03Z",
    "2026-09-28T15:15:59Z",
    "2026-09-28T15:16:56Z",
    "2026-09-28T15:17:51Z",
    "2026-09-28T15:18:46Z",
    "2026-09-28T15:19:41Z",
    "2026-09-28T15:20:37Z",
    "2026-09-28T15:21:32Z",
    "2026-09-28T15:22:26Z",
]


def _b1_era_cells() -> List[List[str]]:
    """真台账的前 `B1_ERA_ROWS` 行（B1 判定时的快照），先核对它确实还是那一段前缀。"""
    cells = _real_cells()
    assert [c[0] for c in cells[:B1_ERA_ROWS]] == B1_ERA_TS, "真台账的历史前缀被改动过——台账只许追加"
    return cells[:B1_ERA_ROWS]


def _mk(decl, n: int, start: Optional[datetime] = None, first_offset_s: int = 52) -> List[List[str]]:  # type: ignore[no-untyped-def]
    """合成一批与声明完全吻合的绿行：自 `start + first_offset_s` 起每 55 秒一行。"""
    base = decl.start_ts if start is None else start
    out = []
    for i in range(n):
        ts = base + timedelta(seconds=first_offset_s + 55 * i)
        out.append([_fmt(ts), decl.commit, "green", "55.00", decl.suite_hash, decl.browser, decl.os, f"logs/{i}.log"])
    return out


def _verdict(decl, cells_rows: List[List[str]]):  # type: ignore[no-untyped-def]
    return _api2().batch_verdict(decl, _rows(cells_rows))


def _col(name: str) -> int:
    return COLUMNS.index(name)


# ---------------------------------------------------------------------------
# R1 · 真台账的行
# ---------------------------------------------------------------------------


def test_r1_real_ledger_rows() -> None:
    mod = _api2()
    text = _real_text()
    rows = mod.ledger_rows(text)
    # 2026-10-02：原先钉总数 == 14、末行 == B1 末行；B2 追加后总数是 24。台账只许追加，所以改钉历史前缀：
    # 前 14 行的 ts 逐条不变（含首行、红行、B1 末行），总数只要求不少于它；与 first_table 逐行一致照旧。
    assert len(rows) == len(first_table(text)[1]) >= B1_ERA_ROWS
    assert [r.ts_utc for r in rows[:B1_ERA_ROWS]] == B1_ERA_TS
    assert rows[0].ts_utc == "2026-09-23T10:51:23Z"
    assert rows[B1_ERA_ROWS - 1].ts_utc == "2026-09-28T15:22:26Z"
    assert rows[2].result == "red"
    assert rows[2].commit == "8e1cf48"
    assert [list(r.cells) for r in rows] == _real_cells()


# ---------------------------------------------------------------------------
# R2 · 与契约解析器在生成文档上一致（预言机等价）
# ---------------------------------------------------------------------------

_CELL = st.text(
    alphabet=st.characters(blacklist_characters="|\n\r", blacklist_categories=("Cs",)), max_size=12
)
_PROSE = st.text(
    alphabet=st.characters(blacklist_characters="|\n\r", blacklist_categories=("Cs",)), min_size=1, max_size=30
)


def _render_cells(cells: List[str]) -> str:
    return "| " + " | ".join(cells) + " |"


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_r2_ledger_rows_agrees_with_first_table(data) -> None:  # type: ignore[no-untyped-def]
    mod = _api2()
    lines: List[str] = list(data.draw(st.lists(_PROSE, max_size=4)))
    lines += [HEADER_LINE, SEP_LINE]
    lines += [_render_cells(r) for r in data.draw(st.lists(st.lists(_CELL, min_size=8, max_size=8), max_size=15))]
    if data.draw(st.booleans()):
        lines.append("")
        lines += [_render_cells(r) for r in data.draw(st.lists(st.lists(_CELL, min_size=8, max_size=8), min_size=1, max_size=4))]
    if data.draw(st.booleans()):
        lines += ["", "---", "", "| a | b |", "|---|---|", "| x | y |"]
    text = "\n".join(lines)
    got = mod.ledger_rows(text)
    assert [list(r.cells) for r in got] == [split_row(ln) for ln in first_table(text)[1]]


# ---------------------------------------------------------------------------
# R3 · 表边界
# ---------------------------------------------------------------------------


def test_r3a_header_and_separator_only() -> None:
    assert list(_api2().ledger_rows("\n".join([HEADER_LINE, SEP_LINE]))) == []


def test_r3b_row_after_blank_line_is_outside_the_table() -> None:
    row = _render_cells(_mk(_b1_decl(), 1)[0])
    assert list(_api2().ledger_rows("\n".join([HEADER_LINE, SEP_LINE, "", row]))) == []


def test_r3c_second_table_after_rule_is_ignored() -> None:
    decl = _b1_decl()
    first = _mk(decl, 2)
    second = _mk(decl, 3, start=decl.start_ts + timedelta(days=1))
    text = "\n".join(
        [HEADER_LINE, SEP_LINE, *map(_render_cells, first), "", "---", "", HEADER_LINE, SEP_LINE, *map(_render_cells, second)]
    )
    assert [list(r.cells) for r in _api2().ledger_rows(text)] == first


# ---------------------------------------------------------------------------
# V1 · 真台账 ＋ 真 B1 → 通过
# ---------------------------------------------------------------------------


def test_v1_real_ledger_real_b1_passes() -> None:
    mod = _api2()
    text = _real_text()
    v = mod.batch_verdict(_b1_decl(), mod.ledger_rows(text))
    assert mod.BATCH_SIZE == 10
    assert v.passed is True, v.reason
    assert len(v.rows) == 10
    assert v.rows[0].ts_utc == "2026-09-28T15:14:07Z"
    assert v.rows[-1].ts_utc == "2026-09-28T15:22:26Z"
    assert not {r.commit for r in v.rows} & PRE_BATCH_COMMITS


def test_v1b_real_ledger_real_b2_passes() -> None:
    mod = _api2()
    parse, _, _ = _api()
    v = mod.batch_verdict(parse(_real_text())["B2"], mod.ledger_rows(_real_text()))
    assert v.passed is True, v.reason
    assert len(v.rows) == 10
    assert v.rows[0].ts_utc == "2026-10-01T16:57:14Z"
    assert v.rows[-1].ts_utc == "2026-10-01T17:14:08Z"
    assert {r.commit for r in v.rows} == {"94dd1e0"}


def test_v1_verdict_is_frozen_dataclass() -> None:
    mod = _api2()
    v = mod.batch_verdict(_b1_decl(), mod.ledger_rows(_real_text()))
    assert dataclasses.is_dataclass(v)
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.passed = False  # type: ignore[misc]
    assert dataclasses.is_dataclass(v.rows[0])
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.rows[0].cells = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# V2 · 穷举单字段扰动（10 个位置 × 5 列）
# ---------------------------------------------------------------------------

PERTURB = {
    "commit": "deadbee",
    "suite_hash": "000000000000",
    "browser": "chromium-9999",
    "os": "linux-6.1.0",
    "result": "red",
}


@pytest.mark.parametrize(
    "pos,column", [(p, c) for p in range(10) for c in sorted(PERTURB)], ids=[f"pos{p}-{c}" for p in range(10) for c in sorted(PERTURB)]
)
def test_v2_single_field_perturbation_fails_naming_row_and_column(pos: int, column: str) -> None:
    decl = _b1_decl()
    # 2026-10-02：原先 `_real_cells()` 且断 `len == 14`；B2 追加后改取 B1 判定时的 14 行快照（前缀已核对），
    # 第 4 行起的 10 行仍是 B1 的窗口，扰动与判据一字未改。
    cells = _b1_era_cells()
    assert len(cells) == B1_ERA_ROWS
    target = cells[4 + pos]
    declared = "green" if column == "result" else getattr(decl, column)
    assert target[_col(column)] == declared
    target[_col(column)] = PERTURB[column]
    v = _verdict(decl, cells)
    assert v.passed is False
    for piece in (target[0], column, PERTURB[column], declared, str(pos + 1)):
        assert piece in v.reason, f"判决理由缺 {piece!r}：{v.reason}"


# ---------------------------------------------------------------------------
# V3 · 蜕变律：前缀 / 后缀行不改判决
# ---------------------------------------------------------------------------

_ID_COMMIT = st.text(alphabet=_HEX, min_size=7, max_size=7)
_ID_HASH = st.text(alphabet=_HEX, min_size=12, max_size=12)
_ID_LABEL = st.sampled_from(["chromium-1234", "chromium-9999", "darwin-25.3.0", "linux-6.1.0", "x"])


@st.composite
def _foreign_row(draw, ts: datetime) -> List[str]:  # type: ignore[no-untyped-def]
    return [
        _fmt(ts),
        draw(_ID_COMMIT),
        draw(st.sampled_from(["green", "red"])),
        "1.00",
        draw(_ID_HASH),
        draw(_ID_LABEL),
        draw(_ID_LABEL),
        "logs/x.log",
    ]


def _signature(v) -> tuple:  # type: ignore[no-untyped-def]
    return (v.passed, v.reason, [r.ts_utc for r in v.rows])


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_v3_prefix_and_suffix_rows_never_change_the_verdict(data) -> None:  # type: ignore[no-untyped-def]
    decl = _b1_decl()
    start = decl.start_ts
    base_a = _mk(decl, 10)
    base_b = _mk(decl, 10)
    k = data.draw(st.integers(0, 9))
    col = data.draw(st.sampled_from(sorted(PERTURB)))
    base_b[k][_col(col)] = PERTURB[col]

    gaps = data.draw(st.lists(st.integers(1, 10**6), max_size=20))
    prefix_ts = []
    t = start
    for g in gaps:
        t = t - timedelta(seconds=g)
        prefix_ts.append(t)
    prefix = [data.draw(_foreign_row(ts)) for ts in reversed(prefix_ts)]

    suffix_ts = data.draw(
        st.lists(
            st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2099, 12, 31), timezones=st.just(timezone.utc)),
            max_size=20,
        )
    )
    suffix = [data.draw(_foreign_row(ts.replace(microsecond=0))) for ts in suffix_ts]

    for base in (base_a, base_b):
        assert _signature(_verdict(decl, prefix + base + suffix)) == _signature(_verdict(decl, base))
    assert _verdict(decl, base_a).passed is True
    assert _verdict(decl, base_b).passed is False


# ---------------------------------------------------------------------------
# V4 · 窗口大小与起点边界
# ---------------------------------------------------------------------------


def test_v4a_zero_rows_is_incomplete() -> None:
    decl = _b1_decl()
    before = _mk(decl, 3, start=decl.start_ts - timedelta(hours=1))
    v = _verdict(decl, before)
    assert v.passed is False
    assert "incomplete" in v.reason and "0/10" in v.reason


def test_v4b_nine_rows_is_incomplete() -> None:
    decl = _b1_decl()
    v = _verdict(decl, _mk(decl, 9))
    assert v.passed is False
    assert "incomplete" in v.reason and "9/10" in v.reason


def test_v4c_exactly_ten_passes() -> None:
    decl = _b1_decl()
    v = _verdict(decl, _mk(decl, 10))
    assert v.passed is True, v.reason
    assert len(v.rows) == 10


def test_v4d_eleventh_red_row_is_ignored() -> None:
    decl = _b1_decl()
    cells = _mk(decl, 11)
    cells[10][_col("result")] = "red"
    cells[10][_col("commit")] = "deadbee"
    v = _verdict(decl, cells)
    assert v.passed is True, v.reason
    assert len(v.rows) == 10
    assert cells[10][0] not in [r.ts_utc for r in v.rows]


def test_v4e_row_at_exact_start_is_included() -> None:
    decl = _b1_decl()
    v = _verdict(decl, _mk(decl, 10, first_offset_s=0))
    assert v.passed is True, v.reason
    assert v.rows[0].ts_utc == _fmt(decl.start_ts)


def test_v4f_row_one_second_before_start_is_excluded() -> None:
    decl = _b1_decl()
    early = _mk(decl, 1, first_offset_s=-1)
    v = _verdict(decl, early + _mk(decl, 10))
    assert v.passed is True, v.reason
    assert len(v.rows) == 10
    assert early[0][0] not in [r.ts_utc for r in v.rows]


def test_v4g_non_chronological_row_after_tenth_is_ignored() -> None:
    decl = _b1_decl()
    late = _mk(decl, 1, first_offset_s=-60)
    v = _verdict(decl, _mk(decl, 10) + late)
    assert v.passed is True, v.reason
    assert len(v.rows) == 10
    assert late[0][0] not in [r.ts_utc for r in v.rows]


# ---------------------------------------------------------------------------
# V5 · 窗口内穿插的外来行在其位置判败（不许「先按身份过滤再取 10」）
# ---------------------------------------------------------------------------


def test_v5_interleaved_foreign_row_fails_at_its_position() -> None:
    decl = _b1_decl()
    cells = _mk(decl, 11)
    cells[3][_col("commit")] = "baddc61"
    v = _verdict(decl, cells)
    assert v.passed is False
    for piece in ("4", cells[3][0], "commit", "baddc61", "9be446c"):
        assert piece in v.reason, f"判决理由缺 {piece!r}：{v.reason}"


# ---------------------------------------------------------------------------
# V6 · 两处违规，报较早的那一处
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arrangement", ["red3-os7", "os3-red7"])
def test_v6_earlier_offender_is_named(arrangement: str) -> None:
    decl = _b1_decl()
    cells = _mk(decl, 10)
    first, second = (("result", "red"), ("os", "linux-6.1.0"))
    if arrangement == "os3-red7":
        first, second = second, first
    cells[2][_col(first[0])] = first[1]
    cells[6][_col(second[0])] = second[1]
    v = _verdict(decl, cells)
    assert v.passed is False
    assert cells[2][0] in v.reason
    assert cells[6][0] not in v.reason


# ---------------------------------------------------------------------------
# V7 · 任何位置的不可解析 ts 都 fail closed（Q2）
# ---------------------------------------------------------------------------

BAD_TS = "2026-09-28 15:16:00"


@pytest.mark.parametrize("placement", ["before", "inside", "after"])
def test_v7_unparseable_ts_anywhere_fails(placement: str) -> None:
    decl = _b1_decl()
    good = _mk(decl, 10)
    bad = _mk(decl, 1)[0]
    bad[0] = BAD_TS
    if placement == "before":
        cells = [bad] + good
    elif placement == "inside":
        cells = good[:5] + [bad] + good[5:]
    else:
        cells = good + [bad]
    v = _verdict(decl, cells)
    assert v.passed is False
    assert BAD_TS in v.reason


# ---------------------------------------------------------------------------
# V8 · 窗口内少一列的行判败
# ---------------------------------------------------------------------------


def test_v8_row_without_eight_cells_fails() -> None:
    decl = _b1_decl()
    cells = _mk(decl, 10)
    cells[5] = cells[5][:7]
    rows = _rows(cells)
    assert len(rows[5].cells) == 7
    v = _api2().batch_verdict(decl, rows)
    assert v.passed is False
    assert cells[5][0] in v.reason


# ---------------------------------------------------------------------------
# V9 · 窗口内时序倒退的行判败
# ---------------------------------------------------------------------------


def test_v9_non_chronological_row_inside_window_fails() -> None:
    decl = _b1_decl()
    good = _mk(decl, 10)
    late = _mk(decl, 1, first_offset_s=-60)[0]
    v = _verdict(decl, good[:5] + [late] + good[5:])
    assert v.passed is False
    assert late[0] in v.reason


# ---------------------------------------------------------------------------
# V10 · 纯函数、确定性
# ---------------------------------------------------------------------------


def test_v10_pure_and_deterministic() -> None:
    mod = _api2()
    decl = _b1_decl()
    rows = mod.ledger_rows(_real_text())
    decl_copy = copy.deepcopy(decl)
    rows_copy = copy.deepcopy(rows)
    first = mod.batch_verdict(decl, rows)
    second = mod.batch_verdict(decl, rows)
    assert decl == decl_copy
    assert rows == rows_copy
    assert first == second


# ---------------------------------------------------------------------------
# V11 · 违规行优先于 incomplete（Q6）
# ---------------------------------------------------------------------------


def test_v11_offending_row_beats_incomplete() -> None:
    decl = _b1_decl()
    cells = _mk(decl, 5)
    cells[2][_col("result")] = "red"
    v = _verdict(decl, cells)
    assert v.passed is False
    assert cells[2][0] in v.reason
    assert "result" in v.reason
    assert "incomplete" not in v.reason


# ---------------------------------------------------------------------------
# V12 · 同一行多列不符时，按台账列序报第一列（Q4：commit, result, suite_hash, browser, os）
# ---------------------------------------------------------------------------


def test_v12a_commit_reported_before_result() -> None:
    decl = _b1_decl()
    cells = _mk(decl, 10)
    cells[1][_col("commit")] = "deadbee"
    cells[1][_col("result")] = "red"
    v = _verdict(decl, cells)
    assert v.passed is False
    for piece in ("commit", "deadbee", "9be446c"):
        assert piece in v.reason, f"判决理由缺 {piece!r}：{v.reason}"
    assert "red" not in v.reason


def test_v12b_result_reported_before_os() -> None:
    decl = _b1_decl()
    cells = _mk(decl, 10)
    cells[1][_col("result")] = "red"
    cells[1][_col("os")] = "linux-6.1.0"
    v = _verdict(decl, cells)
    assert v.passed is False
    assert "result" in v.reason
    assert "linux-6.1.0" not in v.reason


# ===========================================================================
# WI-3 · `--verdict BATCH_ID` CLI（真子进程）
#
# 矩阵：`## WI-3` 的 C1–C5（含 C3(e)）。每个子进程都走 `_run()`：照抄 `test_soak_run._run`，
# `timeout=CLI_TIMEOUT_S`，超时时带着已捕获的输出 `pytest.fail`——unit lane 不许无界子进程。
# 读-only 定律：PASS / FAIL / 未知 ID / 声明不合形状，台账字节不变、不建 log 目录、不调 git / pytest。
# ===========================================================================

CLI_TIMEOUT_S = 60.0

# 2026-10-02：三条合成声明的 ID 由 `B2` 改为 `SYNTH_ID`——真台账已声明真 `B2`，再插一条 `B2` 就成了重复声明，
# C2 / C4「fail」会因「重复」而不是「4178b8a 不符」判败（后者恰好还是 rc=1，红不出来）。变量名随之去掉 B2。
SYNTH_EARLY_LINE = _render([SYNTH_ID, "2026-09-23T00:00:00Z", "baddc61", "1e868c7bf811", "chromium-1234", "darwin-25.3.0"])
D5_MALFORMED_SYNTH = f"> - `{SYNTH_ID}`｜`2026-09-29T00:00:00Z`｜`9be446c`｜`1e868c7bf811`｜`chromium-1234`"
D6_ASCII_SYNTH = f"> - `{SYNTH_ID}`|`2026-09-29T00:00:00Z`|`9be446c`|`1e868c7bf811`|`chromium-1234`|`darwin-25.3.0`"


def _run(cmd: List[str], *, timeout: float = CLI_TIMEOUT_S, **kwargs: object) -> "subprocess.CompletedProcess[str]":
    """带超时的 `subprocess.run`；超时时把已捕获的输出一并报出来再 fail（照抄 `test_soak_run._run`）。"""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)  # type: ignore[arg-type]
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        pytest.fail(f"子进程超过 {timeout:g}s 没退出：{cmd}\n--- stdout ---\n{out}\n--- stderr ---\n{err}")


def _cli(*args: str, env: Optional[Dict[str, str]] = None) -> "_Proc":
    return _Proc(_run([sys.executable, str(SOAK_RUN_PATH), *args], cwd=str(REPO_ROOT), env=env))


def _ledger_copy(tmp_path: Path, extra_line: Optional[str] = None, name: str = "soak-log.md") -> Path:
    text = _real_text()
    if extra_line is not None:
        text = _insert_after_b1_block(text, extra_line)
    target = tmp_path / name
    target.write_bytes(text.encode("utf-8"))
    return target


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_shim(tmp_path: Path) -> Tuple[Dict[str, str], Path]:
    """PATH 最前面放一个假 `git`：被调用就留下标记文件并以 1 退出。只观察「有没有调 git」。"""
    shim = tmp_path / "shim"
    shim.mkdir()
    marker = tmp_path / "git-called"
    git = shim / "git"
    git.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n", encoding="utf-8")
    git.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = f"{shim}{os.pathsep}{env.get('PATH', '')}"
    return env, marker


def _combined(proc: "_Proc") -> str:
    return proc.stdout + proc.stderr


class _Proc:
    """子进程结果的瘦包装：`repr` 不带 stderr。

    红收据的分类器按正则把 lane 输出里的 `unrecognized arguments` 判为 runner-error；
    `CompletedProcess` 的 repr 会把子进程 argparse 的报错原样带进断言内省，误伤真红。
    """

    def __init__(self, proc: "subprocess.CompletedProcess[str]") -> None:
        self.returncode = proc.returncode
        self.stdout = proc.stdout
        self.stderr = proc.stderr

    def __repr__(self) -> str:
        return f"_Proc(returncode={self.returncode})"


# ---------------------------------------------------------------------------
# C1 · 真台账（默认路径）`--verdict B1` 通过
# ---------------------------------------------------------------------------


def test_c1_real_ledger_verdict_b1_passes() -> None:
    proc = _cli("--verdict", "B1")
    assert proc.returncode == 0, proc.stdout
    assert proc.stdout.startswith("PASS B1 10/10"), proc.stdout
    assert "2026-09-28T15:14:07Z" in proc.stdout
    assert "2026-09-28T15:22:26Z" in proc.stdout
    assert "Traceback" not in _combined(proc)


# ---------------------------------------------------------------------------
# C2 · 加一条 2026-09-23 起的合成批次：它判败在 4178b8a；B1 不受影响（蜕变）
# ---------------------------------------------------------------------------


def test_c2_early_synthetic_batch_fails_at_4178b8a_and_b1_unaffected(tmp_path: Path) -> None:
    ledger = _ledger_copy(tmp_path, SYNTH_EARLY_LINE)
    b2 = _cli("--verdict", SYNTH_ID, "--ledger", str(ledger))
    assert b2.returncode == 1, b2.stdout
    assert b2.stdout.startswith(f"FAIL {SYNTH_ID}"), b2.stdout
    assert "重复" not in b2.stdout, b2.stdout
    assert "2026-09-25T22:31:21Z" in b2.stdout
    assert "4178b8a" in b2.stdout
    assert "2026-09-27T04:00:05Z" not in b2.stdout

    b1 = _cli("--verdict", "B1", "--ledger", str(ledger))
    assert b1.returncode == 0, b1.stdout
    assert b1.stdout.startswith("PASS B1 10/10"), b1.stdout


# ---------------------------------------------------------------------------
# C3 · 未知 ID / 重复 / 不合形状 / 台账缺失：退出码恰为 1，并点名原因
# ---------------------------------------------------------------------------


def test_c3a_unknown_id(tmp_path: Path) -> None:
    proc = _cli("--verdict", "B9", "--ledger", str(_ledger_copy(tmp_path)))
    assert proc.returncode == 1, proc.stdout
    assert "Traceback" not in _combined(proc)
    assert "B9" in _combined(proc)


def test_c3b_duplicate_b1(tmp_path: Path) -> None:
    proc = _cli("--verdict", "B1", "--ledger", str(_ledger_copy(tmp_path, B1_LINE)))
    assert proc.returncode == 1, proc.stdout
    out = _combined(proc)
    assert "Traceback" not in out
    assert "B1" in out
    assert B1_LINE.strip() in out


def test_c3c_malformed_b2_blocks_b1(tmp_path: Path) -> None:
    proc = _cli("--verdict", "B1", "--ledger", str(_ledger_copy(tmp_path, D5_MALFORMED_SYNTH)))
    assert proc.returncode == 1, proc.stdout
    out = _combined(proc)
    assert "Traceback" not in out
    assert D5_MALFORMED_SYNTH.strip() in out


def test_c3d_missing_ledger(tmp_path: Path) -> None:
    proc = _cli("--verdict", "B1", "--ledger", str(tmp_path / "absent.md"))
    assert proc.returncode == 1, proc.stdout
    out = _combined(proc)
    assert "Traceback" not in out
    assert "absent.md" in out


def test_c3e_ascii_pipe_b2_is_malformed_not_unknown(tmp_path: Path) -> None:
    unknown = _cli("--verdict", "B9", "--ledger", str(_ledger_copy(tmp_path, name="plain.md")))
    proc = _cli("--verdict", SYNTH_ID, "--ledger", str(_ledger_copy(tmp_path, D6_ASCII_SYNTH)))
    assert proc.returncode == 1, proc.stdout
    out = _combined(proc)
    assert "Traceback" not in out
    assert D6_ASCII_SYNTH.strip() in out
    # 若这一行被当成非候选静默跳过，输出会与「未知 ID」同形——那正是 Q1 要堵的。
    assert proc.stdout != unknown.stdout.replace("B9", SYNTH_ID)


# ---------------------------------------------------------------------------
# C4 · `--verdict` 只读：每种结局都不写台账、不建 log 目录、不调 git / pytest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case,batch_id,extra_line,want_rc",
    [
        ("pass", "B1", None, 0),
        ("fail", SYNTH_ID, SYNTH_EARLY_LINE, 1),
        ("unknown", "B9", None, 1),
        ("malformed", "B1", D5_MALFORMED_SYNTH, 1),
    ],
    ids=["pass", "fail", "unknown", "malformed"],
)
def test_c4_verdict_is_read_only(
    tmp_path: Path, case: str, batch_id: str, extra_line: Optional[str], want_rc: int
) -> None:
    ledger = _ledger_copy(tmp_path, extra_line)
    before = _sha(ledger)
    env, marker = _git_shim(tmp_path)
    log_dir = tmp_path / "logs-never"
    t0 = time.monotonic()
    proc = _cli("--verdict", batch_id, "--ledger", str(ledger), "--log-dir", str(log_dir), env=env)
    wall = time.monotonic() - t0
    assert proc.returncode == want_rc, f"{case}: {proc.stdout}"
    assert _sha(ledger) == before
    assert not log_dir.exists()
    assert not marker.exists(), f"{case}: --verdict 调了 git"
    assert "[soak] 运行" not in proc.stdout
    assert wall < 10.0, f"{case}: --verdict 用了 {wall:.1f}s，像是跑了 pytest"


# ---------------------------------------------------------------------------
# C5 · `--verdict` 与 `--append` / `--parse-summary` 同用即拒绝
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("conflict", ["--append", "--parse-summary"])
def test_c5_verdict_with_conflicting_flag_refused(tmp_path: Path, conflict: str) -> None:
    ledger = _ledger_copy(tmp_path)
    before = _sha(ledger)
    env, marker = _git_shim(tmp_path)
    extra: List[str] = [conflict]
    if conflict == "--parse-summary":
        green = tmp_path / "green.txt"
        green.write_text(f"{_soak().EXPECTED_BASELINE_ITEMS} passed in 12.5s\n", encoding="utf-8")
        extra.append(str(green))
    proc = _cli("--verdict", "B1", "--ledger", str(ledger), *extra, env=env)
    assert proc.returncode != 0, proc.stdout
    out = _combined(proc)
    assert "--verdict" in out
    assert conflict in out
    assert _sha(ledger) == before
    assert not marker.exists()


# ===========================================================================
# WI-4 · 全树干净度过滤（纯函数 `dirty_entries`）+ git 薄包装 `dirty_worktree`
#
# 矩阵：`## WI-4` 的 P1–P4（含 RM/CM）与 G1–G6（含 `git mv` + 编辑）；绑定裁定 Q5：返回
# git 在 `-z` 下报的原样路径（不加引号），重命名/复制返回**新**路径，顺序即 porcelain 顺序。
# 豁免：文件按全等匹配；目录按 `/` 段边界匹配（`soak-logs/x` 是，`soak-logs-evil/x` 不是）；
# 重命名/复制只有新旧两条路径都豁免才算豁免。真 git 用例全部在 tmp 仓库里跑，身份用 `-c`
# 传，不写全局配置。
# ===========================================================================

P_EXEMPT_FILES = ["docs/l/soak-log.md"]
P_EXEMPT_DIRS = [".claude/soak-logs"]


def _dirty_entries():  # type: ignore[no-untyped-def]
    mod = _soak()
    assert hasattr(mod, "dirty_entries"), "scripts/soak_run.py 缺少 dirty_entries（WI-4 的交付）"
    return mod.dirty_entries


def _dirty_worktree():  # type: ignore[no-untyped-def]
    mod = _soak()
    assert hasattr(mod, "dirty_worktree"), "scripts/soak_run.py 缺少 dirty_worktree（WI-4 的交付）"
    return mod.dirty_worktree


def _p(porcelain: str) -> List[str]:
    return list(_dirty_entries()(porcelain, P_EXEMPT_FILES, P_EXEMPT_DIRS))


# ---------------------------------------------------------------------------
# P1 · porcelain -z 表：每种状态
# ---------------------------------------------------------------------------

P1_RECORDS: List[Tuple[str, List[str]]] = [
    ("", []),
    (" M a.py\0", ["a.py"]),
    ("M  a.py\0", ["a.py"]),
    ("MM a.py\0", ["a.py"]),
    (" D gone.py\0", ["gone.py"]),
    ("?? tests/conftest.py\0", ["tests/conftest.py"]),
    ("R  new.py\0old.py\0", ["new.py"]),
    ("?? 测试 文件.py\0", ["测试 文件.py"]),
]


@pytest.mark.parametrize("porcelain,want", P1_RECORDS + [
    ("".join(r for r, _ in P1_RECORDS), [p for _, w in P1_RECORDS for p in w]),
])
def test_p1_every_status_kind(porcelain: str, want: List[str]) -> None:
    assert _p(porcelain) == want


# ---------------------------------------------------------------------------
# P2 · 豁免边界
# ---------------------------------------------------------------------------


def test_p2_exemption_boundaries() -> None:
    records = [
        " M docs/l/soak-log.md",
        "?? docs/l/soak-log.md",
        "MM docs/l/soak-log.md",
        "?? docs/l/soak-log.md.bak",
        "?? .claude/soak-logs/x.log",
        "?? .claude/soak-logs/a/b.log",
        "?? .claude/soak-logs-evil/x.log",
        "?? .claude/soak-log",
    ]
    porcelain = "".join(r + "\0" for r in records)
    assert _p(porcelain) == ["docs/l/soak-log.md.bak", ".claude/soak-logs-evil/x.log", ".claude/soak-log"]


# ---------------------------------------------------------------------------
# P3 · 重命名/复制：两条路径都豁免才豁免；RM/CM 也带 orig 尾巴
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "porcelain,want",
    [
        ("R  .claude/soak-logs/b.log\0.claude/soak-logs/a.log\0 M z.py\0", ["z.py"]),
        ("R  .claude/soak-logs/b.log\0src/x.py\0 M z.py\0", [".claude/soak-logs/b.log", "z.py"]),
        ("R  src/x.py\0.claude/soak-logs/a.log\0 M z.py\0", ["src/x.py", "z.py"]),
        ("C  .claude/soak-logs/c.log\0tests/conftest.py\0 M z.py\0", [".claude/soak-logs/c.log", "z.py"]),
        ("RM c.py\0a.py\0 M z.py\0", ["c.py", "z.py"]),
        ("CM d.py\0a.py\0 M z.py\0", ["d.py", "z.py"]),
    ],
)
def test_p3_rename_exempt_only_if_both_paths_are(porcelain: str, want: List[str]) -> None:
    out = _p(porcelain)
    assert out == want
    assert out[-1] == "z.py"


# ---------------------------------------------------------------------------
# P4 · 过滤定律（生成的 porcelain）
# ---------------------------------------------------------------------------

P4_XY = [" M", "M ", "MM", "A ", " D", "D ", "??", "R ", "C ", "RM", "CM"]
_P4_SEG = st.text(alphabet="abcxyz019._ -测试文件", min_size=1, max_size=6).filter(
    lambda s: s not in (".", "..") and not s.startswith(" ") and not s.endswith(" ")
)
_P4_PLAIN = st.lists(_P4_SEG, min_size=1, max_size=3).map("/".join)
_P4_PATH = st.one_of(
    _P4_PLAIN,
    _P4_PLAIN.map(lambda p: f".claude/soak-logs/{p}"),
    _P4_PLAIN.map(lambda p: f".claude/soak-logs-evil/{p}"),
    st.just("docs/l/soak-log.md"),
    st.sampled_from(["docs/l/soak-log.md.bak", "docs/l/soak-log.mdx", "docs/l/soak-log.md/x"]),
)
_P4_EXEMPT_PATH = st.one_of(
    st.just("docs/l/soak-log.md"),
    _P4_PLAIN.map(lambda p: f".claude/soak-logs/{p}"),
)


@st.composite
def _p4_record(draw, path_st=_P4_PATH, xy_st=st.sampled_from(P4_XY)):  # type: ignore[no-untyped-def]
    xy = draw(xy_st)
    paths = [draw(path_st)]
    if xy[0] in "RC":
        paths.append(draw(path_st))
    return (xy, tuple(paths))


def _p4_render(records: List[Tuple[str, Tuple[str, ...]]]) -> str:
    return "".join(f"{xy} " + "\0".join(paths) + "\0" for xy, paths in records)


def _p4_oracle_exempt(path: str) -> bool:
    return path in P_EXEMPT_FILES or any(path == d or path.startswith(d + "/") for d in P_EXEMPT_DIRS)


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    records=st.lists(_p4_record(), min_size=0, max_size=15),
    inserted=st.lists(_p4_record(path_st=_P4_EXEMPT_PATH), min_size=1, max_size=5),
    data=st.data(),
)
def test_p4_filter_law(records, inserted, data) -> None:  # type: ignore[no-untyped-def]
    out = _p(_p4_render(records))
    # (a) 精确过滤：新路径、输入顺序、两条路径都豁免才豁免
    assert out == [paths[0] for _, paths in records if not all(_p4_oracle_exempt(p) for p in paths)]
    # (b) 子集
    all_paths = {p for _, paths in records for p in paths}
    assert all(p in all_paths for p in out)
    # (c) 蜕变：任意位置插入纯豁免记录，输出不变（与 oracle 无关）
    mixed = list(records)
    for rec in inserted:
        mixed.insert(data.draw(st.integers(min_value=0, max_value=len(mixed))), rec)
    assert _p(_p4_render(mixed)) == out


# ---------------------------------------------------------------------------
# G1–G6 · `dirty_worktree` 走真 git
# ---------------------------------------------------------------------------

_GIT_ID = ["-c", "user.email=soak@test.invalid", "-c", "user.name=soak-test", "-c", "commit.gpgsign=false"]


def _child_env() -> Dict[str, str]:
    """`os.environ` 的副本，去掉 `GITHUB_ACTIONS` 与一切 `GIT_*`（同 `test_soak_run._clean_env`）。

    WI-8：`--append` 闸门在 CI（`GITHUB_ACTIONS` 存在）里一律拒绝落账，子进程不能继承外层的值；
    `GIT_*` 则是 commit 钩子里会漏进来的 `GIT_DIR` / `GIT_INDEX_FILE`，会把夹具的 git 指到别的仓库。
    """
    return {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS" and not k.startswith("GIT_")}


def _g(repo: Path, *args: str) -> None:
    proc = _run(["git", *_GIT_ID, *args], cwd=str(repo), env=_child_env())
    assert proc.returncode == 0, f"git {args} 失败：{proc.stderr}"


def _publish(repo: Path) -> None:
    """把 HEAD 推到 `origin` 的 master 再 fetch：WI-8 的 `--append` 闸门要求 HEAD 是 origin/master 的祖先。"""
    _g(repo, "push", "-q", "origin", "HEAD:refs/heads/master")
    _g(repo, "fetch", "-q", "origin")


def _add_origin(repo: Path, bare: Path) -> None:
    """给 `repo` 配一个本地裸仓库 `origin` 并发布 HEAD，使 origin/master == HEAD（WI-8 闸门放行）。
    不依赖 init.defaultBranch：推送目标显式写成 refs/heads/master。"""
    _g(bare.parent, "init", "-q", "--bare", str(bare))
    _g(repo, "remote", "add", "origin", str(bare))
    _publish(repo)


def _merged_repo(tmp_path: Path) -> Path:
    """一个 origin/master == HEAD 的临时仓库，交给隐藏开关 `--ancestry-repo` 让 WI-8 闸门放行。"""
    repo = (tmp_path / "ancestry-repo").resolve()
    repo.mkdir()
    _g(repo, "init", "-q")
    (repo / "README.md").write_text("# ancestry\n", encoding="utf-8")
    _g(repo, "add", "-A")
    _g(repo, "commit", "-q", "-m", "init")
    _add_origin(repo, (tmp_path / "ancestry-origin.git").resolve())
    return repo


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    repo = (tmp_path / "repo").resolve()
    repo.mkdir()
    _g(repo, "init", "-q")
    (repo / "a.py").write_text("a = 1\nprint(a)\n", encoding="utf-8")
    (repo / "b.py").write_text("b = 2\nprint(b)\n", encoding="utf-8")
    (repo / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    (repo / "docs" / "l").mkdir(parents=True)
    (repo / "docs" / "l" / "soak-log.md").write_text("# ledger\n", encoding="utf-8")
    _g(repo, "add", "-A")
    _g(repo, "commit", "-q", "-m", "init")
    return repo


def _dw(repo: Path, ledger: Optional[Path] = None, log_dir: Optional[Path] = None) -> List[str]:
    ledger = ledger if ledger is not None else repo / "docs" / "l" / "soak-log.md"
    log_dir = log_dir if log_dir is not None else repo / ".claude" / "soak-logs"
    return list(_dirty_worktree()(repo, ledger, log_dir))


def test_g1_clean_repo(tmp_repo: Path) -> None:
    assert _dw(tmp_repo) == []


def _append(path: Path, line: str = "x = 3\n") -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _write(path: Path, text: str = "stray\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _g2_untracked_conftest(r: Path) -> None:
    _write(r / "conftest.py")


def _g2_staged(r: Path) -> None:
    _append(r / "a.py")
    _g(r, "add", "a.py")


def _g2_unstaged(r: Path) -> None:
    _append(r / "b.py")


def _g2_mv(r: Path) -> None:
    _g(r, "mv", "a.py", "c.py")


def _g2_mv_edit(r: Path) -> None:
    _g(r, "mv", "a.py", "c.py")
    _append(r / "c.py")


def _g2_rm(r: Path) -> None:
    (r / "b.py").unlink()


def _g2_non_ascii(r: Path) -> None:
    _write(r / "测试.py")


def _g2_deep(r: Path) -> None:
    _write(r / "deep" / "er" / "x.py")


@pytest.mark.parametrize(
    "mutate,want",
    [
        (_g2_untracked_conftest, ["conftest.py"]),
        (_g2_staged, ["a.py"]),
        (_g2_unstaged, ["b.py"]),
        (_g2_mv, ["c.py"]),
        (_g2_mv_edit, ["c.py"]),
        (_g2_rm, ["b.py"]),
        (_g2_non_ascii, ["测试.py"]),
        (_g2_deep, ["deep/er/x.py"]),
    ],
    ids=["untracked-conftest", "staged", "unstaged", "git-mv", "git-mv-edit-RM", "rm", "non-ascii", "deep"],
)
def test_g2_every_dirt_kind_reported_exactly(tmp_repo: Path, mutate, want: List[str]) -> None:  # type: ignore[no-untyped-def]
    mutate(tmp_repo)
    assert _dw(tmp_repo) == want


def test_g2_mv_edit_really_produces_rm_record(tmp_repo: Path) -> None:
    """RM 参数在真 git 上确实产生 `RM` 记录（P3 的 RM 行不是臆造）。"""
    _g2_mv_edit(tmp_repo)
    proc = _run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=str(tmp_repo))
    assert proc.stdout.startswith("RM c.py\0a.py\0"), repr(proc.stdout)


def test_g3a_in_tree_ledger_and_log_dir_exempt(tmp_repo: Path) -> None:
    _append(tmp_repo / "docs" / "l" / "soak-log.md", "| row |\n")
    _write(tmp_repo / ".claude" / "soak-logs" / "r1.log")
    _write(tmp_repo / ".claude" / "soak-logs" / "sub" / "r2.log")
    assert _dw(tmp_repo) == []


def test_g3b_prefix_sibling_not_exempt(tmp_repo: Path) -> None:
    _write(tmp_repo / ".claude" / "soak-logs-evil" / "x.log")
    assert _dw(tmp_repo) == [".claude/soak-logs-evil/x.log"]


def test_g3c_ledger_outside_cwd_gives_no_exemption(tmp_repo: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    other = tmp_path_factory.mktemp("other")
    outside = other / "docs" / "l" / "soak-log.md"
    _write(outside, "# other ledger\n")
    _append(tmp_repo / "docs" / "l" / "soak-log.md", "| row |\n")
    assert _dw(tmp_repo, ledger=outside) == ["docs/l/soak-log.md"]


def test_g3d_log_dir_outside_cwd_gives_no_exemption(tmp_repo: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("logs-elsewhere") / ".claude" / "soak-logs"
    _write(tmp_repo / ".claude" / "soak-logs" / "x.log")
    assert _dw(tmp_repo, log_dir=outside) == [".claude/soak-logs/x.log"]


def test_g4_gitignored_not_reported(tmp_repo: Path) -> None:
    _write(tmp_repo / "ignored" / "stray.py")
    assert _dw(tmp_repo) == []


def test_g5_hostile_filename_verbatim_not_executed(tmp_repo: Path) -> None:
    _write(tmp_repo / "$(touch PWNED).py")
    assert _dw(tmp_repo) == ["$(touch PWNED).py"]
    assert not (tmp_repo / "PWNED").exists()


def test_g6_not_a_repo_fails_loudly(tmp_path: Path) -> None:
    not_repo = tmp_path / "not-a-repo"
    not_repo.mkdir()
    with pytest.raises((subprocess.CalledProcessError, RuntimeError)):
        _dw(not_repo, ledger=not_repo / "soak-log.md", log_dir=not_repo / "logs")


# ===========================================================================
# WI-5 · `--append` 接上全树干净度检查
#
# 矩阵：`## WI-5` 的 E1（纯 helper `effective_log_dir`）与 A1–A6（含 A3b、A3c）；A3c 采用
# 「Adversary round 2 amendments」的判据修正：主跑断言 `"[soak] 运行" in stdout`（只在前置检查
# 放行之后打印），不再断 `rc != 2`。子进程跑的是**拷进 tmp git 仓库**的 `scripts/soak_run.py`
# ＋ `scripts/lint_e2e_groups.py`（`REPO_ROOT` 由 `__file__` 派生，所以前置检查看的是 tmp 仓库）；
# 台账放在**另一个** tmp 目录（仓库外，`--allow-synthetic-append` 才收），带台账表头那段真
# hash-recipe fenced 块，好让 `suite_hash` 在 tmp 仓库里取得到。
# ===========================================================================


def _effective_log_dir():  # type: ignore[no-untyped-def]
    mod = _soak()
    assert hasattr(mod, "effective_log_dir"), "scripts/soak_run.py 缺少 effective_log_dir（WI-5 的交付）"
    return mod.effective_log_dir


# ---------------------------------------------------------------------------
# E1 · 每种参数形状下的有效 log 目录
# ---------------------------------------------------------------------------


def test_e1_effective_log_dir_for_each_argument_shape() -> None:
    import shutil
    import tempfile

    soak = _soak()
    eld = _effective_log_dir()
    parse = soak._build_parser().parse_args

    assert eld(parse(["--append"]), True) == soak.DEFAULT_LOG_DIR
    assert eld(parse(["--append", "--log-dir", "/x/logs"]), True) == Path("/x/logs")
    assert eld(parse(["--log-dir", ".claude/tdd-guardian/soak-logs"]), False) == Path(".claude/tdd-guardian/soak-logs")

    d = eld(parse(["--parse-summary", "f.txt", "--append"]), False)
    try:
        resolved = Path(d).resolve()
        tmp_root = Path(tempfile.gettempdir()).resolve()
        assert tmp_root == resolved or tmp_root in resolved.parents, f"{resolved} 不在 {tmp_root} 下"
        repo = Path(soak.REPO_ROOT).resolve()
        assert repo != resolved and repo not in resolved.parents, f"临时 log 目录落进了仓库：{resolved}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# A1–A6 · `main --append` 的前置检查接线（真子进程 ＋ 真 git）
# ---------------------------------------------------------------------------


def _hash_recipe_block() -> str:
    import re

    blocks = re.findall(r"^```bash[^\n]*\n.*?^```[^\n]*\n", _real_text(), re.S | re.M)
    picked = [b for b in blocks if "git ls-files" in b]
    assert len(picked) == 1, f"真台账里含 git ls-files 的 fenced bash 块应恰好 1 个，实际 {len(picked)}"
    return picked[0]


def _synthetic_ledger(directory: Path) -> Path:
    from test_soak_run import CANONICAL_COLUMNS  # type: ignore[import-not-found]

    ledger = directory / "soak-log.md"
    ledger.write_text(
        "# ledger\n\n| "
        + " | ".join(CANONICAL_COLUMNS)
        + " |\n|"
        + "---|" * len(CANONICAL_COLUMNS)
        + "\n\n---\n\n"
        + _hash_recipe_block(),
        encoding="utf-8",
    )
    return ledger


def _copy_scripts(dest: Path) -> Path:
    import shutil

    (dest / "scripts").mkdir(parents=True)
    for name in ("soak_run.py", "lint_e2e_groups.py"):
        shutil.copy2(REPO_ROOT / "scripts" / name, dest / "scripts" / name)
    return dest / "scripts" / "soak_run.py"


class _ScriptRepo:
    def __init__(self, repo: Path, script: Path, ledger: Path, green: Path) -> None:
        self.repo = repo
        self.script = script
        self.ledger = ledger
        self.green = green

    def base(self) -> List[str]:
        return [
            sys.executable,
            str(self.script),
            "--parse-summary",
            str(self.green),
            "--append",
            "--allow-synthetic-append",
            "--ledger",
            str(self.ledger),
        ]

    def run(self, argv: List[str]) -> "_Proc":
        # WI-8：去掉 GITHUB_ACTIONS / GIT_*，CI 上跑本文件时 `--append` 闸门才不会一律拒绝。
        return _Proc(_run(argv, cwd=str(self.repo), env=_child_env()))

    def rows(self) -> List[str]:
        return first_table(self.ledger.read_text(encoding="utf-8"))[1]


@pytest.fixture
def tmp_script_repo(tmp_path: Path) -> _ScriptRepo:
    repo = (tmp_path / "repo").resolve()
    repo.mkdir()
    _g(repo, "init", "-q")
    script = _copy_scripts(repo)
    (repo / "README.md").write_text("# tmp\n", encoding="utf-8")
    # 与真仓库 .gitignore 第 2 行一致：脚本按路径加载 lint_e2e_groups 会写 scripts/__pycache__/。
    (repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    _g(repo, "add", "-A")
    _g(repo, "commit", "-q", "-m", "init")
    # WI-8：`--append` 闸门以脚本所在仓库（这里即 repo）为准，要求 HEAD 是 origin/master 的祖先。
    _add_origin(repo, (tmp_path / "origin.git").resolve())
    outside = (tmp_path / "outside").resolve()
    outside.mkdir()
    ledger = _synthetic_ledger(outside)
    green = outside / "green.txt"
    green.write_text(f"{_soak().EXPECTED_BASELINE_ITEMS} passed in 12.5s\n", encoding="utf-8")
    return _ScriptRepo(repo, script, ledger, green)


def _cells(row: str) -> Dict[str, str]:
    from test_soak_run import CANONICAL_COLUMNS  # type: ignore[import-not-found]

    cells = [c.strip() for c in split_row(row)]
    assert len(cells) == len(CANONICAL_COLUMNS), row
    return dict(zip(CANONICAL_COLUMNS, cells))


def _logs(directory: Path) -> List[Path]:
    return sorted(directory.glob("*.log")) if directory.is_dir() else []


def test_a1_clean_tree_append_succeeds(tmp_script_repo: _ScriptRepo) -> None:
    r = tmp_script_repo
    proc = r.run(r.base() + ["--log-dir", str(r.repo.parent / "logs")])
    assert proc.returncode == 0, _combined(proc)
    rows = r.rows()
    assert len(rows) == 1, rows
    cells = _cells(rows[0])
    assert cells["result"] == "green"
    assert cells["duration_s"] == "12.5"


def _a2_untracked_conftest(r: Path) -> str:
    _write(r / "conftest.py")
    return "conftest.py"


def _a2_staged_outside_covered(r: Path) -> str:
    _append(r / "scripts" / "lint_e2e_groups.py", "# edit\n")
    _g(r, "add", "scripts/lint_e2e_groups.py")
    return "scripts/lint_e2e_groups.py"


def _a2_unstaged_readme(r: Path) -> str:
    _append(r / "README.md", "more\n")
    return "README.md"


def _a2_deleted(r: Path) -> str:
    (r / "README.md").unlink()
    return "README.md"


@pytest.mark.parametrize(
    "make_dirty",
    [_a2_untracked_conftest, _a2_staged_outside_covered, _a2_unstaged_readme, _a2_deleted],
    ids=["untracked-conftest", "staged-outside-covered", "unstaged-readme", "deleted"],
)
def test_a2_dirt_outside_exemptions_refuses_without_writing(tmp_script_repo: _ScriptRepo, make_dirty) -> None:  # type: ignore[no-untyped-def]
    r = tmp_script_repo
    soak = _soak()
    name = make_dirty(r.repo)
    before = r.ledger.read_bytes()
    logs = r.repo.parent / "logs"
    proc = r.run(r.base() + ["--log-dir", str(logs)])
    assert proc.returncode == soak.EXIT_UNRECORDABLE, _combined(proc)
    assert name in proc.stdout, proc.stdout
    assert "worktree" in proc.stdout and "--ledger" in proc.stdout, proc.stdout
    assert "Traceback" not in _combined(proc)
    assert r.ledger.read_bytes() == before
    assert _logs(logs) == []


def test_a3_absolute_in_tree_log_dir_does_not_block_run_two(tmp_script_repo: _ScriptRepo) -> None:
    r = tmp_script_repo
    logs = r.repo / ".claude" / "tdd-guardian" / "soak-logs"
    argv = r.base() + ["--log-dir", str(logs)]
    first = r.run(argv)
    assert first.returncode == 0, _combined(first)
    second = r.run(argv)
    assert second.returncode == 0, _combined(second)
    assert len(r.rows()) == 2
    assert len(_logs(logs)) == 2


def test_a3b_relative_in_tree_log_dir_does_not_block_run_two(tmp_script_repo: _ScriptRepo) -> None:
    r = tmp_script_repo
    rel = ".claude/tdd-guardian/soak-logs"
    argv = r.base() + ["--log-dir", rel]
    first = r.run(argv)
    assert first.returncode == 0, _combined(first)
    status = _run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=str(r.repo))
    assert any(ln.startswith("?? ") and ln.endswith(".log") and rel in ln for ln in status.stdout.splitlines()), (
        status.stdout
    )
    second = r.run(argv)
    assert second.returncode == 0, _combined(second)
    assert len(r.rows()) == 2
    assert len(_logs(r.repo / rel)) == 2


def test_a3c_earlier_log_under_default_dir_does_not_block_real_append(tmp_script_repo: _ScriptRepo) -> None:
    r = tmp_script_repo
    soak = _soak()
    _write(r.repo / ".claude" / "tdd-guardian" / "soak-logs" / "earlier.log", "run 1\n")
    before = r.ledger.read_bytes()
    argv = [sys.executable, str(r.script), "--append", "--ledger", str(r.ledger)]

    main_run = r.run(argv)
    assert "[soak] 运行" in main_run.stdout, _combined(main_run)
    assert "拒绝落账" not in main_run.stdout, main_run.stdout
    assert "earlier.log" not in main_run.stdout, main_run.stdout
    assert r.ledger.read_bytes() == before

    _write(r.repo / "stray.txt")
    control = r.run(argv)
    assert control.returncode == soak.EXIT_UNRECORDABLE, _combined(control)
    assert "stray.txt" in control.stdout, control.stdout
    assert r.ledger.read_bytes() == before


def test_a4_dry_run_with_stray_file_prints_hint(tmp_script_repo: _ScriptRepo) -> None:
    r = tmp_script_repo
    _write(r.repo / "stray.txt")
    before = r.ledger.read_bytes()
    argv = [sys.executable, str(r.script), "--parse-summary", str(r.green), "--ledger", str(r.ledger)]
    proc = r.run(argv)
    assert proc.returncode == 0, _combined(proc)
    assert "stray.txt" in proc.stdout, proc.stdout
    assert "dry run" in proc.stdout, proc.stdout
    assert r.ledger.read_bytes() == before


def test_a5_no_precheck_is_unchanged(tmp_script_repo: _ScriptRepo) -> None:
    r = tmp_script_repo
    _write(r.repo / "conftest.py")
    proc = r.run(r.base() + ["--no-precheck", "--log-dir", str(r.repo.parent / "logs")])
    assert proc.returncode == 0, _combined(proc)
    assert len(r.rows()) == 1


def test_a6_precheck_that_cannot_run_is_environment_error(tmp_path: Path) -> None:
    soak = _soak()
    not_repo = (tmp_path / "not-a-repo").resolve()
    script = _copy_scripts(not_repo)
    outside = (tmp_path / "outside").resolve()
    outside.mkdir()
    ledger = _synthetic_ledger(outside)
    green = outside / "green.txt"
    green.write_text(f"{soak.EXPECTED_BASELINE_ITEMS} passed in 12.5s\n", encoding="utf-8")
    before = ledger.read_bytes()
    argv = [
        sys.executable,
        str(script),
        "--parse-summary",
        str(green),
        "--append",
        "--allow-synthetic-append",
        "--ledger",
        str(ledger),
        # WI-8：脚本所在目录不是仓库，闸门会先以「解析不出 origin/master」拒绝；指一个已合入的仓库
        # 让闸门放行，前置检查（仍对 not_repo 跑）才是这里要测的那一步。
        "--ancestry-repo",
        str(_merged_repo(tmp_path)),
    ]
    proc = _Proc(_run(argv, cwd=str(not_repo), env=_child_env()))
    assert proc.returncode == soak.EXIT_ENVIRONMENT, _combined(proc)
    assert "前置检查" in proc.stdout, proc.stdout
    assert "Traceback" not in _combined(proc)
    assert ledger.read_bytes() == before


# ===========================================================================
# soak-WI-7 · 评审批次修复（只追加用例，不改任何已记红的断言）
#
# 1. 日志目录豁免 fail closed：只豁免日志目录下**未跟踪**（`??`）且以 `.log` 结尾的条目；
#    日志目录与 `HASH_COVERED_PATHS` 任一条互相包含、或目录下有 git 跟踪的 `*.py`，则整体不豁免。
# 2. C5 加强：退出码恰为 1、打印拒绝文案、不是 argparse 的 usage 报错。
# 3. `dirty_entries` 的 fail-closed 分支与无尾 NUL 输入。
# 4. V7 变体：形状对、日历不存在的 ts。
# 7. `git status` 超时 ⇒ 「前置检查无法执行」，退出码 3。
# ===========================================================================


# ---------------------------------------------------------------------------
# P5 / P6 · 不合形状的记录抛 RuntimeError；无尾 NUL 的输入照常解析
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("porcelain", ["M a.py\0", "R  new.py\0"], ids=["xy-without-space", "rename-missing-orig"])
def test_p5_malformed_record_raises(porcelain: str) -> None:
    with pytest.raises(RuntimeError):
        _p(porcelain)


@pytest.mark.parametrize(
    "porcelain,want",
    [
        (" M a.py\0?? b.py", ["a.py", "b.py"]),
        ("?? .claude/soak-logs/x.log", []),
        ("R  new.py\0old.py", ["new.py"]),
    ],
    ids=["two-records", "single-exempt", "rename-orig-last"],
)
def test_p6_input_without_trailing_nul(porcelain: str, want: List[str]) -> None:
    assert _p(porcelain) == want


# ---------------------------------------------------------------------------
# G7 · 日志目录豁免 fail closed（真 git）
# ---------------------------------------------------------------------------

G7_LOGS = ".claude/soak-logs"


def _commit_all(repo: Path, msg: str = "more") -> None:
    _g(repo, "add", "-A")
    _g(repo, "commit", "-q", "-m", msg)


def test_g7a_modified_tracked_log_is_dirty(tmp_repo: Path) -> None:
    _write(tmp_repo / G7_LOGS / "old.log", "run 0\n")
    _commit_all(tmp_repo)
    _append(tmp_repo / G7_LOGS / "old.log", "tampered\n")
    assert _dw(tmp_repo) == [f"{G7_LOGS}/old.log"]


def test_g7b_tracked_logs_plus_new_untracked_logs_stay_exempt(tmp_repo: Path) -> None:
    _write(tmp_repo / G7_LOGS / "old.log", "run 0\n")
    _commit_all(tmp_repo)
    _write(tmp_repo / G7_LOGS / "new.log", "run 1\n")
    _write(tmp_repo / G7_LOGS / "sub" / "deeper.log", "run 2\n")
    assert _dw(tmp_repo) == []


@pytest.mark.parametrize("name", ["conftest.py", "evil.py", "notes.txt"])
def test_g7c_untracked_non_log_under_log_dir_is_dirty(tmp_repo: Path, name: str) -> None:
    _write(tmp_repo / G7_LOGS / name)
    assert _dw(tmp_repo) == [f"{G7_LOGS}/{name}"]


@pytest.mark.parametrize(
    "log_dir",
    ["tests/e2e", "tests", "tests/e2e/baseline_1b/logs"],
    ids=["equals-suite-dir", "contains-covered", "inside-covered"],
)
def test_g7d_log_dir_overlapping_covered_paths_gets_no_exemption(tmp_repo: Path, log_dir: str) -> None:
    _write(tmp_repo / log_dir / "r.log", "run\n")
    assert _dw(tmp_repo, log_dir=tmp_repo / log_dir) == [f"{log_dir}/r.log"]


def test_g7e_log_dir_holding_tracked_python_gets_no_exemption(tmp_repo: Path) -> None:
    _write(tmp_repo / "tools" / "helper.py", "x = 1\n")
    _commit_all(tmp_repo)
    _write(tmp_repo / "tools" / "r.log", "run\n")
    assert _dw(tmp_repo, log_dir=tmp_repo / "tools") == ["tools/r.log"]
    # 控制组：同样的未跟踪 log 放在一个不含跟踪 .py 的目录里，照常豁免。
    _write(tmp_repo / "plain-logs" / "r.log", "run\n")
    assert "plain-logs/r.log" not in _dw(tmp_repo, log_dir=tmp_repo / "plain-logs")


# ---------------------------------------------------------------------------
# A7 · `--append --log-dir tests/e2e` 不能洗白套件里的野 conftest（真子进程）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("suite_tracked", [True, False], ids=["tracked-suite", "untracked-suite"])
def test_a7_log_dir_on_suite_does_not_hide_stray_conftest(tmp_script_repo: _ScriptRepo, suite_tracked: bool) -> None:
    r = tmp_script_repo
    soak = _soak()
    if suite_tracked:
        _write(r.repo / "tests" / "e2e" / "test_harness_smoke.py", "def test_ok():\n    assert True\n")
        _commit_all(r.repo)
        _publish(r.repo)  # WI-8：新提交也得在 origin/master 上，闸门才放行
    _write(r.repo / "tests" / "e2e" / "conftest.py", "import os\n")
    before = r.ledger.read_bytes()
    proc = r.run(r.base() + ["--log-dir", "tests/e2e"])
    assert proc.returncode == soak.EXIT_UNRECORDABLE, _combined(proc)
    assert "tests/e2e/conftest.py" in proc.stdout, proc.stdout
    assert r.ledger.read_bytes() == before


def test_a7b_default_log_dir_with_earlier_logs_still_appends(tmp_script_repo: _ScriptRepo) -> None:
    r = tmp_script_repo
    rel = ".claude/tdd-guardian/soak-logs"
    _write(r.repo / rel / "tracked-earlier.log", "run 0\n")
    _commit_all(r.repo)
    _publish(r.repo)  # WI-8：新提交也得在 origin/master 上，闸门才放行
    _write(r.repo / rel / "untracked-earlier.log", "run 1\n")
    proc = r.run(r.base() + ["--log-dir", rel])
    assert proc.returncode == 0, _combined(proc)
    assert len(r.rows()) == 1


def test_a7c_modified_tracked_log_blocks_append(tmp_script_repo: _ScriptRepo) -> None:
    r = tmp_script_repo
    soak = _soak()
    rel = ".claude/tdd-guardian/soak-logs"
    _write(r.repo / rel / "tracked-earlier.log", "run 0\n")
    _commit_all(r.repo)
    _publish(r.repo)  # WI-8：新提交也得在 origin/master 上，闸门才放行
    _append(r.repo / rel / "tracked-earlier.log", "rewritten\n")
    before = r.ledger.read_bytes()
    proc = r.run(r.base() + ["--log-dir", rel])
    assert proc.returncode == soak.EXIT_UNRECORDABLE, _combined(proc)
    assert f"{rel}/tracked-earlier.log" in proc.stdout, proc.stdout
    assert r.ledger.read_bytes() == before


# ---------------------------------------------------------------------------
# C5b · 冲突参数：恰为 1、打印拒绝文案、不是 argparse usage 报错
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("conflict", ["--append", "--parse-summary"])
def test_c5b_verdict_conflict_is_our_refusal_not_argparse(tmp_path: Path, conflict: str) -> None:
    ledger = _ledger_copy(tmp_path)
    extra: List[str] = [conflict]
    if conflict == "--parse-summary":
        green = tmp_path / "green.txt"
        green.write_text(f"{_soak().EXPECTED_BASELINE_ITEMS} passed in 12.5s\n", encoding="utf-8")
        extra.append(str(green))
    proc = _cli("--verdict", "B1", "--ledger", str(ledger), *extra)
    assert proc.returncode == 1, _combined(proc)
    out = _combined(proc)
    assert "拒绝" in out and "只读判决" in out, out
    assert "usage:" not in proc.stderr


# ---------------------------------------------------------------------------
# V7b · 形状合法、日历不存在的 ts（2 月 30 日）在窗口内 ⇒ FAIL
# ---------------------------------------------------------------------------


def test_v7b_impossible_calendar_date_inside_window_fails() -> None:
    decl = _b1_decl()
    good = _mk(decl, 10)
    bad = _mk(decl, 1)[0]
    bad[0] = "2026-02-30T00:00:00Z"
    v = _verdict(decl, good[:5] + [bad] + good[5:])
    assert v.passed is False
    assert "2026-02-30T00:00:00Z" in v.reason


# ---------------------------------------------------------------------------
# T1 / T2 · `git status` 挂死 ⇒ 超时 ⇒ 前置检查无法执行（退出码 3）
# PATH 最前放一个 `exec sleep` 的假 git；超时是模块常量，测试把它调小。
# ---------------------------------------------------------------------------


def _sleepy_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shim = tmp_path / "sleepy-shim"
    shim.mkdir()
    git = shim / "git"
    git.write_text("#!/bin/sh\nexec sleep 5\n", encoding="utf-8")
    git.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim}{os.pathsep}{os.environ.get('PATH', '')}")


def test_t1_git_status_timeout_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _soak()
    assert hasattr(mod, "GIT_PRECHECK_TIMEOUT_S"), "scripts/soak_run.py 缺少 GIT_PRECHECK_TIMEOUT_S"
    monkeypatch.setattr(mod, "GIT_PRECHECK_TIMEOUT_S", 0.3)
    repo = tmp_path / "repo"
    repo.mkdir()
    _sleepy_git(tmp_path, monkeypatch)
    t0 = time.monotonic()
    with pytest.raises(RuntimeError, match="超时"):
        mod.dirty_worktree(repo, repo / "soak-log.md", repo / "logs")
    assert time.monotonic() - t0 < 3.0


def _sleepy_precheck_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """只让前置检查的 git（`status` / `ls-files`）挂死；WI-8 闸门的 `rev-parse` / `merge-base`
    由 shim 自己作答（放行），其余子命令转给真 git。审计 20261007 #24（FX37-10）：以前闸门的
    两条 git 也走真 git，却同样受 0.3 s 的 `GIT_PRECHECK_TIMEOUT_S` 约束，慢机器上闸门先超时，
    这条测的「前置检查超时」就落空了。"""
    real_git = shutil.which("git")
    assert real_git is not None, "PATH 上找不到 git"
    shim = tmp_path / "sleepy-precheck-shim"
    shim.mkdir()
    git = shim / "git"
    git.write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do\n'
        '  case "$a" in\n'
        "    status|ls-files) exec sleep 5 ;;\n"
        "    rev-parse) echo 0123456789abcdef0123456789abcdef01234567; exit 0 ;;\n"
        "    merge-base) exit 0 ;;\n"
        "  esac\n"
        "done\n"
        f'exec "{real_git}" "$@"\n',
        encoding="utf-8",
    )
    git.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim}{os.pathsep}{os.environ.get('PATH', '')}")


def test_t2_main_maps_git_timeout_to_environment_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _soak()
    assert hasattr(mod, "GIT_PRECHECK_TIMEOUT_S"), "scripts/soak_run.py 缺少 GIT_PRECHECK_TIMEOUT_S"
    monkeypatch.setattr(mod, "GIT_PRECHECK_TIMEOUT_S", 0.3)
    outside = tmp_path / "outside"
    outside.mkdir()
    ledger = _synthetic_ledger(outside)
    green = outside / "green.txt"
    green.write_text(f"{mod.EXPECTED_BASELINE_ITEMS} passed in 12.5s\n", encoding="utf-8")
    before = ledger.read_bytes()
    # WI-8：闸门在 CI 里拒绝、且要 HEAD 在 origin/master 上——去掉 GITHUB_ACTIONS，并用隐藏开关
    # `--ancestry-repo` 指一个已合入的临时仓库（夹具要在装 shim 之前建好）。
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    ancestry = _merged_repo(tmp_path)
    _sleepy_precheck_git(tmp_path, monkeypatch)
    rc = mod.main(
        ["--parse-summary", str(green), "--append", "--allow-synthetic-append", "--ledger", str(ledger),
         "--log-dir", str(tmp_path / "logs"), "--ancestry-repo", str(ancestry)]
    )
    out = capsys.readouterr().out
    assert rc == mod.EXIT_ENVIRONMENT, out
    assert "前置检查" in out, out
    assert ledger.read_bytes() == before
