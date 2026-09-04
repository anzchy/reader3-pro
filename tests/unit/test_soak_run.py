"""WI-17 · Unit A —— `scripts/soak_run.py`：soak 台账的**计数守卫**（skipped ≠ passed）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` `## WI-17:` Unit A 的第五、六条。
任务书 §8 G2「绿的判据」：一次运行记为绿，**当且仅当** `passed == EXPECTED_BASELINE_ITEMS`
且 `skipped == deselected == failed == errors == 0`。`result` 列由本脚本判定，人工不得改写。

**这条律没有守卫时，「把一条不稳的用例悄悄加上 `@pytest.mark.skip`」就是零成本地让 G2 变绿
的手段**：`0 failed` 照样成立，`result` 列只有 green/red，台账上无痕。

两条用例的分工（policy-core 的 mock 配对）：

* 第一条 mock 了**输入源**（合成的 summary 文本），测的是解析与判定；被 mock 的理由写在那里。
* 第二条走**真** subprocess、真 pytest、`tmp_path` 上的微型套件，证明「合成 summary 的形状
  与 pytest 真实输出一致」这个假设本身。pytest 升级改了 summary 行格式时，只有它会红——
  那是应该红的红。

**判定的三态（写进脚本 docstring，这里只钉结果）**：
`green`（可记账）、`red` 且可记账（真失败：`failed > 0`，其余全为 0，`passed + failed == 期望`——
§7 要求任意一次 red 清零，所以真红**必须**进台账）、`red` 且**不可记账**（skipped / deselected /
errors / 条数不符 / 一条没跑——这些不是「一次全量运行」，记进去既不是绿也不是那种该清零的红）。
矩阵原文「其余四种不写台账并以非零退出码结束」对应最后一态。

**本条不替代 `test_e2e_group_guard.py` 的 skip 轴静态性质**：runner 只在 G2 跑三次，
而 fixture 里那句 `pytest.skip` 每次 push 都在生效。两者触发频率差两个数量级，都要留。

不碰 `books/`；台账只写 `tmp_path` 下的副本。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Tuple

import pytest

from test_soak_log_contract import (  # type: ignore[import-not-found]
    CANONICAL_COLUMNS,
    first_table,
    split_row,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SOAK_RUN_PATH = SCRIPTS_DIR / "soak_run.py"
GROUPS_LINT_PATH = SCRIPTS_DIR / "lint_e2e_groups.py"

_CACHE: Dict[str, ModuleType] = {}


def _load(path: Path, name: str) -> ModuleType:
    if name in _CACHE:
        return _CACHE[name]
    assert path.exists(), f"{path} 不存在——它是 WI-17 的交付（矩阵 Unit A 第五 / 六条）"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    _CACHE[name] = module
    return module


def _soak() -> ModuleType:
    mod = _load(SOAK_RUN_PATH, "soak_run_under_test_b")
    missing = [
        a
        for a in ("parse_summary", "verdict", "format_row", "append_row", "run_pytest", "EXPECTED_BASELINE_ITEMS")
        if not hasattr(mod, a)
    ]
    assert not missing, f"scripts/soak_run.py 缺少 {missing}"
    return mod


def _expected() -> int:
    groups = _load(GROUPS_LINT_PATH, "lint_e2e_groups_for_soak_test")
    return int(groups.EXPECTED_BASELINE_ITEMS)


def _counts(summary: object) -> Tuple[int, int, int, int, int]:
    return (
        int(getattr(summary, "passed")),
        int(getattr(summary, "skipped")),
        int(getattr(summary, "failed")),
        int(getattr(summary, "deselected")),
        int(getattr(summary, "errors")),
    )


# --------------------------------------------------------------------------
# Case 5：拒绝把 skipped / deselected / error / 条数不符记为绿（guard / S4 / L2）
# --------------------------------------------------------------------------
def _synthetic_cases() -> List[Tuple[str, str, str, bool, str]]:
    """(id, summary 文本, 期望 result, 期望可记账, 拒绝消息里必须点名的 token)。"""
    n = _expected()
    return [
        ("all-green", f"{n} passed in 123.4s", "green", True, ""),
        ("has-skipped", f"{n - 1} passed, 1 skipped in 100.0s", "red", False, "skipped"),
        ("has-deselected", f"{n - 1} passed, 1 deselected in 100.0s", "red", False, "deselected"),
        ("has-error", f"{n} passed, 1 error in 100.0s", "red", False, "error"),
        ("one-fewer", f"{n - 1} passed in 100.0s", "red", False, f"{n}"),
    ]


@pytest.mark.parametrize(
    "case_id,text,want_result,want_recordable,token",
    _synthetic_cases(),
    ids=[c[0] for c in _synthetic_cases()],
)
def test_verdict_refuses_to_call_a_partial_run_green(
    case_id: str, text: str, want_result: str, want_recordable: bool, token: str
) -> None:
    """五种 summary 形态，只有全绿记绿。`if "failed" not in out: pass_it()` 式实现在第 2、3、5 行全绿 ⇒ 本条红。

    输入源被 mock 成合成文本：真跑一次 baseline 是 G2 那三次的成本，拿来测「怎么读一行
    summary」是荒唐的。被 mock 的是输入，解析与判定是真的。配对的真路径用例在下面。
    """
    soak = _soak()
    n = _expected()
    summary = soak.parse_summary(text)
    v = soak.verdict(summary, n)
    assert v.result == want_result, f"{case_id}: result={v.result!r}，期望 {want_result!r}；reasons={v.reasons}"
    assert v.recordable is want_recordable, (
        f"{case_id}: recordable={v.recordable!r}，期望 {want_recordable!r}；reasons={v.reasons}"
    )
    if token:
        joined = "\n".join(v.reasons)
        assert token in joined, f"{case_id}: 拒绝理由没有点名 {token!r}：{v.reasons}"
    if case_id == "one-fewer":
        joined = "\n".join(v.reasons)
        assert str(n - 1) in joined, f"数量不符的消息应同时给出实际值 {n - 1}：{v.reasons}"


def test_a_genuine_failure_is_red_and_recordable() -> None:
    """真失败（failed > 0、无 skip / deselect / error、passed + failed == 期望）记为 red 且**必须**进台账——§7：任意一次 red 清零。"""
    soak = _soak()
    n = _expected()
    v = soak.verdict(soak.parse_summary(f"{n - 2} passed, 2 failed in 100.0s"), n)
    assert v.result == "red"
    assert v.recordable is True, f"真红被拒绝记账了，清零规则就失效了：{v.reasons}"


def test_append_only_happens_for_recordable_verdicts_via_cli(tmp_path: Path) -> None:
    """CLI 的 `--append` 只在可记账时写台账：绿写一行 `green`，含 skip 的运行不写且退出非零。

    L2：断的是 `tmp_path` 下台账文件的**内容**（写了几行、`result` 列的值），不是脚本的返回值。
    """
    _soak()
    n = _expected()
    ledger = tmp_path / "soak-log.md"
    ledger.write_text(
        "# ledger\n\n| " + " | ".join(CANONICAL_COLUMNS) + " |\n|" + "---|" * len(CANONICAL_COLUMNS) + "\n\n---\n",
        encoding="utf-8",
    )
    before = ledger.read_text(encoding="utf-8")

    skipped = tmp_path / "skipped.txt"
    skipped.write_text(f"{n - 1} passed, 1 skipped in 10.0s\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SOAK_RUN_PATH), "--parse-summary", str(skipped), "--append", "--ledger", str(ledger), "--no-precheck"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0, "含 skipped 的运行被以退出码 0 记账了：\n" + proc.stdout + proc.stderr
    assert ledger.read_text(encoding="utf-8") == before, "含 skipped 的运行往台账写了东西"
    assert "skipped" in (proc.stdout + proc.stderr)

    green = tmp_path / "green.txt"
    green.write_text(f"{n} passed in 12.5s\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SOAK_RUN_PATH), "--parse-summary", str(green), "--append", "--ledger", str(ledger), "--no-precheck"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, "全绿的运行没能记账：\n" + proc.stdout + proc.stderr
    header, rows = first_table(ledger.read_text(encoding="utf-8"))
    assert header == CANONICAL_COLUMNS
    assert len(rows) == 1, f"全绿应恰好追加一行，实际 {len(rows)} 行：{rows}"
    cells = split_row(rows[0])
    assert len(cells) == len(CANONICAL_COLUMNS), f"台账行不是 {len(CANONICAL_COLUMNS)} 列：{cells}"
    assert cells[header.index("result")] == "green", f"result 列不是 green：{cells}"
    assert cells[header.index("duration_s")] == "12.5", f"duration_s 没有取自 summary：{cells}"


def test_dry_run_prints_the_row_but_never_touches_the_ledger(tmp_path: Path) -> None:
    """不带 `--append` 时只打印行与判定，台账字节不变——默认动作必须是无副作用的。"""
    _soak()
    n = _expected()
    ledger = tmp_path / "soak-log.md"
    ledger.write_text(
        "| " + " | ".join(CANONICAL_COLUMNS) + " |\n|" + "---|" * len(CANONICAL_COLUMNS) + "\n",
        encoding="utf-8",
    )
    before = ledger.read_bytes()
    green = tmp_path / "green.txt"
    green.write_text(f"{n} passed in 12.5s\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SOAK_RUN_PATH), "--parse-summary", str(green), "--ledger", str(ledger), "--no-precheck"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert ledger.read_bytes() == before, "没有 --append 却改了台账"
    assert "green" in proc.stdout, f"dry run 没有打印判定：\n{proc.stdout}"
    assert "| green |" in proc.stdout or "| green " in proc.stdout, f"dry run 没有打印那一行台账：\n{proc.stdout}"


# --------------------------------------------------------------------------
# Case 6：对真 pytest 输出的解析正确（success / S2 / L1 + L2）——上一条的配对
# --------------------------------------------------------------------------
_PASSING = "def test_a():\n    assert True\n\n\ndef test_b():\n    assert True\n"
_WITH_SKIP = "import pytest\n\n\ndef test_a():\n    assert True\n\n\n@pytest.mark.skip(reason='x')\ndef test_b():\n    assert True\n"
_WITH_FAIL = "def test_a():\n    assert True\n\n\ndef test_b():\n    assert False\n"
_WITH_ERROR = "import pytest\n\n\n@pytest.fixture\ndef broken():\n    raise RuntimeError('boom')\n\n\ndef test_a():\n    assert True\n\n\ndef test_b(broken):\n    assert True\n"


def _run_suite(soak: ModuleType, root: Path, body: str, extra: List[str]) -> Tuple[int, str, float]:
    suite = root / "tests_mini"
    suite.mkdir(exist_ok=True)
    (suite / "test_mini.py").write_text(body, encoding="utf-8")
    (root / "pytest.ini").write_text("[pytest]\naddopts = -p no:cacheprovider\n", encoding="utf-8")
    rc, out, duration = soak.run_pytest([str(suite), "-q", *extra], cwd=root)
    return rc, out, duration


@pytest.mark.parametrize(
    "case_id,body,extra,want",
    [
        ("all-pass", _PASSING, [], (2, 0, 0, 0, 0)),
        ("with-skip", _WITH_SKIP, [], (1, 1, 0, 0, 0)),
        ("with-fail", _WITH_FAIL, [], (1, 0, 1, 0, 0)),
        ("with-deselect", _PASSING, ["-k", "test_a"], (1, 0, 0, 1, 0)),
        ("with-error", _WITH_ERROR, [], (1, 0, 0, 0, 1)),
    ],
    ids=["all-pass", "with-skip", "with-fail", "with-deselect", "with-error"],
)
def test_parser_agrees_with_real_pytest_output(
    tmp_path: Path, case_id: str, body: str, extra: List[str], want: Tuple[int, int, int, int, int]
) -> None:
    """真 subprocess、真 pytest、微型套件：解析出的 (passed, skipped, failed, deselected, errors) 与实际相符，判定与合成用例一致。"""
    soak = _soak()
    rc, out, duration = _run_suite(soak, tmp_path, body, extra)
    summary = soak.parse_summary(out)
    assert _counts(summary) == want, f"{case_id}: 解析出 {_counts(summary)}，期望 {want}。输出：\n{out}"
    assert duration >= 0 and float(getattr(summary, "duration_s")) >= 0

    v = soak.verdict(summary, 2)
    if case_id == "all-pass":
        assert (v.result, v.recordable) == ("green", True), v.reasons
    elif case_id == "with-fail":
        assert (v.result, v.recordable) == ("red", True), v.reasons
    else:
        assert (v.result, v.recordable) == ("red", False), f"{case_id}: {v.result} / {v.recordable} / {v.reasons}"


def test_zero_tests_ran_is_never_recordable(tmp_path: Path) -> None:
    """`no tests ran` 不是绿、也不是那种该清零的红——policy-core 第 1 条：零用例是失败。"""
    soak = _soak()
    suite = tmp_path / "tests_empty"
    suite.mkdir()
    (suite / "test_none.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = -p no:cacheprovider\n", encoding="utf-8")
    _, out, _ = soak.run_pytest([str(suite), "-q"], cwd=tmp_path)
    summary = soak.parse_summary(out)
    v = soak.verdict(summary, 2)
    assert v.result == "red"
    assert v.recordable is False, v.reasons


# --------------------------------------------------------------------------
# 台账行的形状与落点（与 test_soak_log_contract 的解析器同口径）
# --------------------------------------------------------------------------
def test_format_row_has_the_eight_canonical_columns_in_order() -> None:
    soak = _soak()
    fields = {
        "ts_utc": "2026-09-04T00:00:00Z",
        "commit": "abc1234",
        "result": "green",
        "duration_s": "58.1",
        "suite_hash": "91de0e171b5c",
        "browser": "chromium-1234",
        "os": "darwin-25.3.0",
        "log": "x.log",
    }
    row = soak.format_row(fields)
    cells = split_row(row)
    assert cells == [fields[c] for c in CANONICAL_COLUMNS], f"列序或列数不对：{cells}"


def test_append_row_lands_directly_under_the_separator_with_no_blank_line(tmp_path: Path) -> None:
    """插在分隔行正下方、不留空行——契约测试只解析第一张表的连续块，一个空行就把行踢出解析范围。"""
    soak = _soak()
    ledger = tmp_path / "soak-log.md"
    header = "| " + " | ".join(CANONICAL_COLUMNS) + " |"
    sep = "|" + "---|" * len(CANONICAL_COLUMNS)
    ledger.write_text(f"# t\n\n{header}\n{sep}\n\n---\n\n后文\n", encoding="utf-8")
    row1 = soak.format_row({c: f"{c}-1" for c in CANONICAL_COLUMNS})
    row2 = soak.format_row({c: f"{c}-2" for c in CANONICAL_COLUMNS})
    soak.append_row(ledger, row1)
    soak.append_row(ledger, row2)
    lines = ledger.read_text(encoding="utf-8").splitlines()
    i = lines.index(sep)
    assert lines[i + 1] == row1, f"第一行没有紧接分隔行：{lines[i + 1]!r}"
    assert lines[i + 2] == row2, f"第二行没有紧接第一行：{lines[i + 2]!r}"
    assert lines[i + 3] == "", "追加之后原有的空行应仍在表块之后"
    _, rows = first_table(ledger.read_text(encoding="utf-8"))
    assert rows == [row1, row2]


# --------------------------------------------------------------------------
# Case 5b（WI-17 收尾补记）：deselected 的合法值是「恰好那些非 baseline 条」，不是 0
#
# 上面 Case 5 的 `has-deselected` 用 `n-1 passed, 1 deselected` 表达「这次不是全量」，
# 那条断言至今成立、一字未动。但它把「0」当成了 deselected 的唯一合法值，而 `-m baseline_1b`
# 在验收目录落地后必然筛掉 24 条 —— 于是 soak 永远产不出可记账的绿（真跑复现：verdict=red、
# 理由只有 deselected 一条）。判据因此从「== 0」改成「== 期望值」，本意不变：多筛少筛都是红。
# 下面三条锁住新行为，缺一条就退回旧写法也能全绿。
# --------------------------------------------------------------------------
def _expected_deselected() -> int:
    return int(_soak().EXPECTED_NONBASELINE_ITEMS)


def test_expected_deselected_is_derived_from_the_group_constants_not_a_literal() -> None:
    """派生自 lint_e2e_groups 的两个常量。写死字面量的实现在树扩容后会悄悄放行一次残缺运行 ⇒ 本条红。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_groups_for_soak_test", REPO_ROOT / "scripts" / "lint_e2e_groups.py")
    assert spec is not None and spec.loader is not None
    groups = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = groups
    spec.loader.exec_module(groups)
    want = int(groups.EXPECTED_ACCEPTANCE_ITEMS) + int(groups.EXPECTED_UNGROUPED_ITEMS)
    assert _expected_deselected() == want, (
        f"EXPECTED_NONBASELINE_ITEMS == {_expected_deselected()}，期望 "
        f"EXPECTED_ACCEPTANCE_ITEMS + EXPECTED_UNGROUPED_ITEMS == {want}"
    )
    assert _expected_deselected() > 0, "非 baseline 条数为 0 说明验收目录没被数进来，这条判据就成了摆设"


def test_a_real_baseline_run_deselecting_exactly_the_nonbaseline_items_is_green() -> None:
    """真跑形态：`65 passed, 24 deselected`。判据写死 deselected == 0 的实现在此转红 ⇒ 本条是那个死锁的证人。"""
    soak = _soak()
    n, d = _expected(), _expected_deselected()
    v = soak.verdict(soak.parse_summary(f"{n} passed, {d} deselected in 49.4s"), n, d)
    assert v.result == "green", f"真跑形态被判 {v.result}；reasons={v.reasons}"
    assert v.recordable is True, f"真跑形态不可记账，soak 台账将永远为空；reasons={v.reasons}"


@pytest.mark.parametrize("delta", [-1, 1], ids=["deselected-one-fewer", "deselected-one-more"])
def test_a_deselected_count_off_by_one_in_either_direction_is_still_red(delta: int) -> None:
    """只放宽成「非 0 即可」的实现在这两条上全绿 ⇒ 本条红。多筛 = 有条被漏跑，少筛 = 分组标记漏挂。"""
    soak = _soak()
    n, d = _expected(), _expected_deselected()
    v = soak.verdict(soak.parse_summary(f"{n} passed, {d + delta} deselected in 49.4s"), n, d)
    assert v.result == "red", f"deselected == {d + delta} 被判绿"
    assert v.recordable is False, f"deselected == {d + delta} 被判可记账"
    assert any("deselected" in r for r in v.reasons), f"拒绝理由里没点名 deselected：{v.reasons}"


def test_parse_summary_mode_does_not_impose_the_real_runs_deselected_expectation(tmp_path: Path) -> None:
    """解析模式默认不设 deselected 预期；把常量无条件当默认值的实现会把这份全量 summary 判红 ⇒ 本条红。

    对称的另一半：不带 --parse-summary 的真跑走 EXPECTED_NONBASELINE_ITEMS，由 --expected-deselected
    显式覆盖时以显式值为准。这里只用 CLI 可观察的那一半作证，真跑一次 baseline 不属于单测的开销。
    """
    n = _expected()
    ledger = tmp_path / "soak-log.md"
    ledger.write_text(
        "| " + " | ".join(CANONICAL_COLUMNS) + " |\n|" + "---|" * len(CANONICAL_COLUMNS) + "\n", encoding="utf-8"
    )
    green = tmp_path / "green.txt"
    green.write_text(f"{n} passed in 12.5s\n", encoding="utf-8")
    base = [sys.executable, str(SOAK_RUN_PATH), "--parse-summary", str(green), "--ledger", str(ledger), "--no-precheck"]

    ok = subprocess.run(base, cwd=REPO_ROOT, capture_output=True, text=True)
    assert ok.returncode == 0, f"解析模式下的全量 summary 被判红：\n{ok.stdout}{ok.stderr}"
    assert "green" in ok.stdout, ok.stdout

    forced = subprocess.run(
        base + ["--expected-deselected", str(_expected_deselected())], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert forced.returncode != 0, "显式给了 deselected 预期却仍判绿，说明这个开关没有接上"
    assert "deselected" in forced.stdout, forced.stdout
