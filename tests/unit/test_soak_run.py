"""WI-17 · Unit A —— `scripts/soak_run.py`：soak 台账的**计数守卫**（skipped ≠ passed）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` `## WI-17:` Unit A 的第五、六条。
任务书 §8 G2「绿的判据」：一次运行记为绿，**当且仅当** `passed == EXPECTED_BASELINE_ITEMS`
且 `skipped == failed == errors == 0`，**且 `deselected` 恰好等于本次调用形态必然筛掉的条数**。
`result` 列由本脚本判定，人工不得改写。

**`deselected` 的那一档在 2026-09-04 订正过，本文件后半段（Case 5b）是它的证人。** §8 G2 的
原文写的是 `deselected == 0`，那是记录当时 `tests/e2e` 整棵树都是 baseline 的巧合：soak 真跑
发的是 `-m baseline_1b`，验收目录与白名单模块**必然**被筛掉，写死 0 会让真跑永远判红。所以
合法值按**调用形态**分两种，本文件两种都测：

* **真跑（`-m baseline_1b`）**：`deselected` 必须恰好等于 `EXPECTED_NONBASELINE_ITEMS`
  （＝验收目录 ＋ 白名单，派生自 `lint_e2e_groups.py`，不是字面量）。多筛少筛都判红。
* **`--parse-summary` 模式**：这份 summary 不是本脚本跑出来的，脚本无从知道对面用了什么 `-m`，
  所以默认不设 deselected 预期（等价于 0），由 `--expected-deselected` 显式覆盖。

「多筛少筛都是红」这条本意一字未改——变的只是那个「恰好几条」从字面量 0 变成了派生值。

**这条律没有守卫时，「把一条不稳的用例悄悄加上 `@pytest.mark.skip`」就是零成本地让 G2 变绿
的手段**：`0 failed` 照样成立，`result` 列只有 green/red，台账上无痕。

两条用例的分工（policy-core 的 mock 配对）：

* 第一条 mock 了**输入源**（合成的 summary 文本），测的是解析与判定；被 mock 的理由写在那里。
* 第二条走**真** subprocess、真 pytest、`tmp_path` 上的微型套件，证明「合成 summary 的形状
  与 pytest 真实输出一致」这个假设本身。pytest 升级改了 summary 行格式时，只有它会红——
  那是应该红的红。

**判定的三态（写进脚本 docstring，这里只钉结果）**：
`green`（可记账）、`red` 且可记账（真失败：`failed > 0`，其余全为 0，`passed + failed == 期望`——
§7 要求任意一次 red 终止批次，所以真红**必须**进台账）、`red` 且**不可记账**（skipped / deselected /
errors / 条数不符 / 一条没跑——这些不是「一次全量运行」，记进去既不是绿也不是那种该终止批次的红）。
矩阵原文「其余四种不写台账并以非零退出码结束」对应最后一态。

**本条不替代 `test_e2e_group_guard.py` 的 skip 轴静态性质**：runner 只在 G2 跑三次，
而 fixture 里那句 `pytest.skip` 每次 push 都在生效。两者触发频率差两个数量级，都要留。

不碰 `books/`；台账只写 `tmp_path` 下的副本。
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Optional, Tuple

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

#: 单测里每一次 subprocess 的上限。**不能省**：本文件所有 CLI 用例都在 unit lane（commit 门）里，
#: 而它们跑的正是被测脚本本身——`soak_run.py` 一旦回归成挂死（等一把永远拿不到的台账锁、
#: 等一个不会退出的 pytest），无超时的 `subprocess.run` 会把整道 commit 门无限期挂住，
#: 形态是「测试还在跑」而不是「测试失败」，谁都不会去看。60s 对这些秒级用例是 20× 以上的余量。
CLI_TIMEOUT_S = 60.0

_CACHE: Dict[str, ModuleType] = {}


def _run(cmd: List[str], *, timeout: float = CLI_TIMEOUT_S, **kwargs: object) -> "subprocess.CompletedProcess[str]":
    """带超时的 `subprocess.run`；超时时把已捕获的输出一并报出来再 fail。

    `TimeoutExpired` 自带 `stdout` / `stderr`（capture_output 下），但 pytest 只会印一行
    「Command ... timed out」——挂死时最该看的恰恰是它挂之前印了什么。
    """
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)  # type: ignore[arg-type]
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        pytest.fail(f"子进程超过 {timeout:g}s 没退出：{cmd}\n--- stdout ---\n{out}\n--- stderr ---\n{err}")


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
    """真失败（failed > 0、无 skip / deselect / error、passed + failed == 期望）记为 red 且**必须**进台账——§7：任意一次 red 终止批次。"""
    soak = _soak()
    n = _expected()
    v = soak.verdict(soak.parse_summary(f"{n - 2} passed, 2 failed in 100.0s"), n)
    assert v.result == "red"
    assert v.recordable is True, f"真红被拒绝记账了，清零规则就失效了：{v.reasons}"


def _synthetic_append_argv(summary_file: Path, ledger: Path) -> List[str]:
    """`--parse-summary` ＋ `--append` 的**唯一**合法形态：显式的测试开关 ＋ 仓库外的临时台账。

    这个开关是 2026-09-05 审计 #14 的产物，不是仪式感：没有它时
    `echo "65 passed in 12.5s" | soak_run.py --parse-summary - --append` 会往 canonical 台账
    写一行带真 commit、真 `suite_hash` 的绿，而一条用例都没跑过。被拒绝的那些形态由
    `test_parse_summary_plus_append_against_the_canonical_ledger_is_refused` 与两条
    `test_the_test_only_opt_in_refuses_*` 钉住；这里是被允许的那条。
    """
    return [
        sys.executable,
        str(SOAK_RUN_PATH),
        "--parse-summary",
        str(summary_file),
        "--append",
        "--allow-synthetic-append",
        "--ledger",
        str(ledger),
        "--no-precheck",
    ]


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
    proc = _run(_synthetic_append_argv(skipped, ledger), cwd=REPO_ROOT)
    assert proc.returncode != 0, "含 skipped 的运行被以退出码 0 记账了：\n" + proc.stdout + proc.stderr
    assert ledger.read_text(encoding="utf-8") == before, "含 skipped 的运行往台账写了东西"
    assert "skipped" in (proc.stdout + proc.stderr)

    green = tmp_path / "green.txt"
    green.write_text(f"{n} passed in 12.5s\n", encoding="utf-8")
    proc = _run(_synthetic_append_argv(green, ledger), cwd=REPO_ROOT)
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
    proc = _run(
        [sys.executable, str(SOAK_RUN_PATH), "--parse-summary", str(green), "--ledger", str(ledger), "--no-precheck"],
        cwd=REPO_ROOT,
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
    """`no tests ran` 不是绿、也不是那种该终止批次的红——policy-core 第 1 条：零用例是失败。"""
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

    ok = _run(base, cwd=REPO_ROOT)
    assert ok.returncode == 0, f"解析模式下的全量 summary 被判红：\n{ok.stdout}{ok.stderr}"
    assert "green" in ok.stdout, ok.stdout

    forced = _run(base + ["--expected-deselected", str(_expected_deselected())], cwd=REPO_ROOT)
    assert forced.returncode != 0, "显式给了 deselected 预期却仍判绿，说明这个开关没有接上"
    assert "deselected" in forced.stdout, forced.stdout


# ==========================================================================
# 2026-09-05 审计（gpt-5.6-sol）修复的七条行为，一条一组用例。**全部追加，不改上面任何断言。**
#
# 这一段共同的底色：`soak-log.md` 就是 G2 的证据本身（「三次连绿」除了台账没有第二处记录），
# 所以「往台账写了一行不该有的绿」与「该有的一行没写成/被覆盖掉」是同一类事故——**证据造假**，
# 而两者在台账上都无痕。下面每一条都是给一条这样的路径装信号。
# ==========================================================================
def _fresh_ledger(tmp_path: Path, name: str = "soak-log.md") -> Path:
    ledger = tmp_path / name
    ledger.write_text(
        "# ledger\n\n| " + " | ".join(CANONICAL_COLUMNS) + " |\n|" + "---|" * len(CANONICAL_COLUMNS) + "\n\n---\n",
        encoding="utf-8",
    )
    return ledger


# --------------------------------------------------------------------------
# 审计 #14（Critical）：合成 summary 不许落进 canonical 台账
# --------------------------------------------------------------------------
def test_parse_summary_plus_append_against_the_canonical_ledger_is_refused() -> None:
    """`echo "N passed in 12.5s" | soak_run.py --parse-summary - --append` 必须被拒，且不碰 canonical 台账。

    修复前实测：这条命令打印 `verdict: green（可记账：是）`，那一行带**真** commit、**真**
    `suite_hash`（`91de0e171b5c`）、真 browser/os，只有 `log` 列指着一个临时目录里的文件——
    而它会被系统回收，于是台账上留下一行连产物都查不到的绿。一条用例都没跑过。
    G2 是「三次连绿」，这条命令跑三次就是一个凭空造出来的门槛。
    """
    soak = _soak()
    n = _expected()
    canonical: Path = soak.LEDGER_PATH
    assert canonical.is_file(), f"canonical 台账不在：{canonical}"
    before = canonical.read_bytes()

    proc = _run(
        [sys.executable, str(SOAK_RUN_PATH), "--parse-summary", "-", "--append", "--no-precheck"],
        cwd=REPO_ROOT,
        input=f"{n} passed in 12.5s\n",
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == soak.EXIT_ENVIRONMENT, (
        f"合成 summary ＋ --append 应以环境错误码 {soak.EXIT_ENVIRONMENT} 被拒，实际 {proc.returncode}：\n{combined}"
    )
    assert canonical.read_bytes() == before, "canonical 台账被一份合成 summary 改写了"
    assert "--parse-summary" in combined and "--append" in combined, f"拒绝理由没点名这两个开关：\n{combined}"
    assert "可记账：是" not in combined, f"拒绝之前就已经把它判成可记账并印了出来：\n{combined}"


def test_the_test_only_opt_in_still_refuses_the_canonical_ledger() -> None:
    """`--allow-synthetic-append` 是给单测的，不是给 canonical 台账开的后门。"""
    soak = _soak()
    n = _expected()
    before = soak.LEDGER_PATH.read_bytes()
    proc = _run(
        [
            sys.executable,
            str(SOAK_RUN_PATH),
            "--parse-summary",
            "-",
            "--append",
            "--allow-synthetic-append",
            "--ledger",
            str(soak.LEDGER_PATH),
            "--no-precheck",
        ],
        cwd=REPO_ROOT,
        input=f"{n} passed in 12.5s\n",
    )
    assert proc.returncode == soak.EXIT_ENVIRONMENT, proc.stdout + proc.stderr
    assert soak.LEDGER_PATH.read_bytes() == before, "带上测试开关就把 canonical 台账写了"
    assert "canonical" in (proc.stdout + proc.stderr)


@pytest.mark.parametrize(
    "relative",
    ["docs/plans/20260816-tech-stack-migration/tasks/soak-log.md.bak", "soak-log.md", "tests/tmp-ledger.md"],
    ids=["ledger-sibling-backup", "repo-root", "under-tests"],
)
def test_the_test_only_opt_in_refuses_any_in_repo_ledger(relative: str) -> None:
    """开关只接受**仓库之外**的临时台账。纯函数判定，不落任何文件。

    为什么连 `soak-log.md.bak` 也拒：仓库里多一份长得像台账、内容是合成绿的文件，
    对 G2 的读者来说与真台账不可区分——「哪一份是真的」不该靠文件名去猜。
    """
    soak = _soak()
    why = soak.synthetic_append_refusal(REPO_ROOT / relative, True)
    assert why is not None, f"{relative} 在仓库里却被放行了"
    assert "仓库" in why or "canonical" in why, why


def test_the_test_only_opt_in_accepts_a_ledger_outside_the_repo(tmp_path: Path) -> None:
    """对称的另一半：仓库外的临时台账放行——否则上面那条「拒绝」可以由 `return \"no\"` 冒充。"""
    soak = _soak()
    assert soak.synthetic_append_refusal(_fresh_ledger(tmp_path), True) is None


# --------------------------------------------------------------------------
# 审计 #15（High）：pytest 的退出码是判据的一部分
# --------------------------------------------------------------------------
def _summary_of(soak: ModuleType, text: str) -> object:
    return soak.parse_summary(text)


@pytest.mark.parametrize(
    "case_id,rc,text,want_ok",
    [
        ("green-rc0", 0, "65 passed in 58.0s", True),
        ("fail-rc1", 1, "63 passed, 2 failed in 58.0s", True),
        ("green-rc1", 1, "65 passed in 58.0s", False),
        ("fail-rc0", 0, "63 passed, 2 failed in 58.0s", False),
        ("green-rc2-interrupted", 2, "65 passed in 58.0s", False),
        ("green-rc3-internal", 3, "65 passed in 58.0s", False),
        ("green-rc4-usage", 4, "65 passed in 58.0s", False),
        ("green-rc5-nocollect", 5, "65 passed in 58.0s", False),
    ],
    ids=lambda v: v if isinstance(v, str) else repr(v),
)
def test_the_exit_code_must_agree_with_the_summary(case_id: str, rc: int, text: str, want_ok: bool) -> None:
    """只认 summary 文本的实现在 `green-rc1` ～ `green-rc5` 五条上全绿 ⇒ 本条红。

    这五条描述的是同一件事：**进程印完那行 summary 之后死了**（plugin 的 teardown、atexit、
    `pytest_sessionfinish` 改写 exitstatus、被 Ctrl-C、collection 阶段就零条）。那一行 summary
    是真的，那次运行不是。
    """
    soak = _soak()
    problem = soak.classify_exit_code(rc, _summary_of(soak, text))
    if want_ok:
        assert problem is None, f"{case_id}: 自洽的组合被拒了：{problem}"
    else:
        assert problem is not None, f"{case_id}: 退出码 {rc} 与 summary 不自洽却被放行"
        assert str(rc) in problem, f"{case_id}: 拒绝理由里没有退出码：{problem}"


_SESSIONFINISH_CONFTEST = "def pytest_sessionfinish(session, exitstatus):\n    session.exitstatus = 3\n"


def test_a_green_summary_from_a_process_that_died_is_not_recordable(tmp_path: Path) -> None:
    """真 pytest：印出 `2 passed`，然后 `pytest_sessionfinish` 把退出码改成 3。

    这是审计 #15 的可复现形态，不是假想的——一个装在 conftest 里的钩子（或任何在收尾阶段炸掉
    的 plugin）就能造出「summary 全绿 ＋ 进程非零退出」。本条同时断两件事：
    (a) 光看 summary 的判定确实会把它判成可记账的绿（所以旧实现真的会记账）；
    (b) 加进退出码之后它被拒，且是**环境错误**而不是 red——红要终止批次，而这次运行连
        「跑完了」都不成立，不该动计数。
    """
    soak = _soak()
    suite = tmp_path / "tests_mini"
    suite.mkdir()
    (suite / "conftest.py").write_text(_SESSIONFINISH_CONFTEST, encoding="utf-8")
    (suite / "test_mini.py").write_text(_PASSING, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = -p no:cacheprovider\n", encoding="utf-8")

    rc, out, _ = soak.run_pytest([str(suite), "-q"], cwd=tmp_path)
    summary = soak.parse_summary(out)
    v = soak.verdict(summary, 2)
    assert (v.result, v.recordable) == ("green", True), f"前提不成立：单看 summary 本该是可记账的绿：{out}"
    assert rc != 0, f"前提不成立：这个套件本该以非零码退出，实际 {rc}：\n{out}"

    problem = soak.classify_exit_code(rc, summary)
    assert problem is not None, f"summary 全绿但进程以 {rc} 退出，仍被判为可记账：\n{out}"


# --------------------------------------------------------------------------
# 审计 #16（High）：suite_hash 不再把 Markdown 里的字符串交给 bash
# --------------------------------------------------------------------------
def test_suite_hash_refuses_a_tampered_recipe_instead_of_executing_it(tmp_path: Path) -> None:
    """台账是可编辑的 Markdown。往那个 fenced 块里插一行命令，旧实现会**执行**它。

    旧实现：`subprocess.run(["bash", "-c", block])`，校验只看输出末 12 位像不像十六进制——
    于是「先干点别的、再算出一个合法的哈希」是完全无痕的。本条的合成台账里插的是
    `touch <marker>`（无害的替身，形态与 `rm -rf` / 外传 / `git add` 后再算哈希一致）：
    修复前 marker 会被创建且 `suite_hash` 正常返回；修复后抛 `HashRecipeError` 且 marker 不存在。
    """
    soak = _soak()
    marker = tmp_path / "pwned"
    tampered = (
        "| ts_utc |\n|---|\n\n```bash\n"
        f"touch {marker}\n"
        "{ git ls-files -s tests/conftest.py | git hash-object --stdin; } | cut -c1-12\n"
        "```\n"
    )
    with pytest.raises(soak.HashRecipeError):
        soak.suite_hash(tampered, REPO_ROOT)
    assert not marker.exists(), f"台账里的一行 shell 被执行了：{marker} 被创建"


def _shell_reference_hash(command_block: str, cwd: Path, env: Optional[Dict[str, str]] = None) -> str:
    """把台账里那段围栏块交给 shell 跑一遍——**这正是 2026-09-05 之前生产代码干的事**。

    那条 `bash -c` 已经从 `soak_run.py` 里删掉了（审计 #21：从可变 Markdown 里正则抠命令
    再交给 shell，等于给台账的写权限配了一条任意命令执行）。它复活在这里，只在测试里，
    因为「换执行方式不许换值」这条唯一的证法就是把旧实现真跑一遍再比。
    """
    return subprocess.run(
        command_block,
        shell=True,  # noqa: S602 - 见 docstring：这是被替换掉的旧路径，测试专属
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=CLI_TIMEOUT_S,
        check=True,
        env=env,
    ).stdout.strip()


def _index_with_covered_paths_staged(tmp_path: Path) -> Dict[str, str]:
    """复制一份 git 索引并把覆盖面内八个路径 `git add` 进去，返回带 `GIT_INDEX_FILE` 的环境。

    **不动真索引**：并行的别的 agent 正在改 `tests/conftest.py` 与 `tests/fixtures/ai_stub.py`，
    在共享仓库里 `git add` 是会被看见的副作用。`GIT_INDEX_FILE` 让整套 git 命令改读副本。
    """
    alt = tmp_path / "alt-index"
    # linked worktree 里 `.git` 是文件不是目录，索引路径要问 git 本身。
    index = _run(["git", "rev-parse", "--git-path", "index"], cwd=REPO_ROOT, check=True).stdout.strip()
    alt.write_bytes((REPO_ROOT / index).read_bytes())
    env = dict(os.environ, GIT_INDEX_FILE=str(alt))
    _run(["git", "add", "--", *_soak().HASH_COVERED_PATHS], cwd=REPO_ROOT, env=env, check=True)
    return env


@pytest.mark.parametrize("stage_first", [False, True], ids=["index-as-is", "covered-paths-staged"])
def test_suite_hash_equals_the_old_shell_recipe_on_the_same_index(tmp_path: Path, stage_first: bool) -> None:
    """换掉执行方式**不许换掉值**：与台账里那段围栏块在同一索引状态下逐字节相同。

    不变量是**配方等价**，不是「等于某个字面量」。`git ls-files -s` 读的是 git 索引，
    而覆盖面内的 `tests/conftest.py` / `tests/fixtures/ai_stub.py` 会被合法地修改——
    断言「== `91de0e171b5c`」只会在下一次有人 `git add` 时变成一条骗人的红。所以这里
    两种索引状态各比一次：原样的索引，以及把八个路径都 stage 进去的索引副本。两种状态
    下新旧实现都必须给出同一个值；至于那个值是什么，是套件内容说了算，不是本用例说了算。

    参考命令**从台账 Markdown 里抠**（不是从 `HASH_COVERED_PATHS` 拼），这样连「文档写的
    和代码算的是同一条配方」也一并被证了。
    """
    soak = _soak()
    ledger_text = soak.LEDGER_PATH.read_text(encoding="utf-8")
    block = soak.hash_command_from_ledger(ledger_text)
    env = _index_with_covered_paths_staged(tmp_path) if stage_first else None

    reference = _shell_reference_hash(block, REPO_ROOT, env=env)
    if env is not None:
        os.environ["GIT_INDEX_FILE"] = env["GIT_INDEX_FILE"]
    try:
        actual = soak.suite_hash(ledger_text, REPO_ROOT)
    finally:
        os.environ.pop("GIT_INDEX_FILE", None)

    assert len(reference) == soak.HASH_TRUNCATE
    assert actual == reference, f"无 shell 的实现与文档管道不同：新 {actual} / 旧 {reference}"


# --------------------------------------------------------------------------
# 审计 #22（Medium）：台账的读—改—写必须持锁、落盘必须原子
# --------------------------------------------------------------------------
_APPEND_CHILD = """
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("soak_child", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
sys.modules["soak_child"] = mod
spec.loader.exec_module(mod)
mod.LEDGER_LOCK_TIMEOUT_S = 1.0
try:
    mod.append_row(pathlib.Path(sys.argv[2]), sys.argv[3])
except mod.LedgerWriteError as exc:
    print("REFUSED:", exc)
    sys.exit(9)
print("WROTE")
"""


def test_append_row_refuses_to_write_while_another_process_holds_the_ledger_lock(tmp_path: Path) -> None:
    """锁被别人拿着时拒写；锁一放开就写得进去。

    无锁实现的失败形态是**丢行**：两次 soak 撞在一起，各自「读全文 → 插一行 → 覆写」，后写的
    直接盖掉先写的那一行。丢掉的可能正是一次该终止批次的 red，而台账上看不出任何异样——
    第三行永远是第三行。用「别人持锁时必须拒绝」来断这件事，是因为它可判定；
    直接去赛跑两个进程只能得到一条概率性用例。
    """
    soak = _soak()
    ledger = _fresh_ledger(tmp_path)
    row = soak.format_row({c: f"{c}-locked" for c in CANONICAL_COLUMNS})
    child = tmp_path / "child.py"
    child.write_text(_APPEND_CHILD, encoding="utf-8")
    argv = [sys.executable, str(child), str(SOAK_RUN_PATH), str(ledger), row]

    import fcntl  # noqa: PLC0415 - 只有这条用例需要它

    lock_path = soak.ledger_lock_path(ledger)
    assert REPO_ROOT not in lock_path.parents, f"锁文件落在仓库里会污染 git status：{lock_path}"
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        before = ledger.read_bytes()
        blocked = _run(argv, timeout=30.0)
        assert blocked.returncode == 9, (
            "台账锁被别人持有时仍然写了进去（无锁实现在这里返回 0 并打印 WROTE）：\n"
            + blocked.stdout
            + blocked.stderr
        )
        assert ledger.read_bytes() == before, "拒绝落账却已经改了文件"
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    freed = _run(argv, timeout=30.0)
    assert freed.returncode == 0, freed.stdout + freed.stderr
    _, rows = first_table(ledger.read_text(encoding="utf-8"))
    assert rows == [row], f"锁放开后那一行没写进去：{rows}"


def test_append_row_replaces_the_ledger_atomically(tmp_path: Path) -> None:
    """落盘走「同目录临时文件 → fsync → `os.replace`」，不是就地覆写。

    判据是 **inode 变了**：就地 `write_text()` 会截断并重写同一个 inode——中途被杀就留下半份
    台账（而台账的解析器只认第一张连续表，半份文件足以让后面所有行从解析范围里消失）。
    `os.replace` 换的是目录项，读者要么看到旧的完整文件、要么看到新的完整文件。
    顺带断「不留临时文件」：留一地 `soak-log.md.xxxx.tmp` 同样是把证据搞浑。
    """
    soak = _soak()
    ledger = _fresh_ledger(tmp_path)
    row = soak.format_row({c: f"{c}-1" for c in CANONICAL_COLUMNS})
    before_inode = ledger.stat().st_ino

    soak.append_row(ledger, row)

    assert ledger.stat().st_ino != before_inode, "台账是被就地覆写的（inode 没变），不是原子替换"
    leftovers = sorted(p.name for p in tmp_path.iterdir() if p.name != ledger.name)
    assert leftovers == [], f"目录里留下了临时文件：{leftovers}"
    _, rows = first_table(ledger.read_text(encoding="utf-8"))
    assert rows == [row]


# --------------------------------------------------------------------------
# 审计 #23（Medium）：同一秒里的两次运行不许共用一个 log 文件名
# --------------------------------------------------------------------------
def test_two_runs_in_the_same_second_get_distinct_log_files(tmp_path: Path) -> None:
    """同一 `ts` ＋ 同一 commit 连取两次，必须是两个都存在的不同文件。

    旧命名是 `{秒级时间戳}-{commit}.log`：同一秒里的两次运行（重试、并行）撞名，后一次静默
    覆盖前一次，而两行台账都指着它——其中一行的 `log` 列指向的证据已经不是它自己的了。
    """
    soak = _soak()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    ts, commit = "2026-09-05T00:00:00Z", "abc1234"
    first = soak.build_log_path(log_dir, ts, commit)
    second = soak.build_log_path(log_dir, ts, commit)
    assert first != second, f"同一秒的两次运行拿到同一个 log 路径：{first}"
    assert first.exists() and second.exists(), "log 路径应被独占创建（O_EXCL），而不是只算个名字"


def test_a_log_name_collision_is_refused_rather_than_overwritten(tmp_path: Path) -> None:
    """撞上就抛，绝不覆盖既有产物——覆盖等于销毁另一行台账的证据。"""
    soak = _soak()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    ts, commit = "2026-09-05T00:00:00Z", "abc1234"
    claimed = soak.build_log_path(log_dir, ts, commit, token="fixed")
    claimed.write_text("原有证据\n", encoding="utf-8")
    with pytest.raises(soak.LedgerWriteError):
        soak.build_log_path(log_dir, ts, commit, token="fixed")
    assert claimed.read_text(encoding="utf-8") == "原有证据\n", "撞名时把既有产物覆盖了"


# --------------------------------------------------------------------------
# 审计 #24（Medium）：套件超时要杀掉整个进程组
# --------------------------------------------------------------------------
_HANGING_TEST = """
import pathlib
import subprocess
import sys
import time

PIDFILE = {pidfile!r}


def test_hangs():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    pathlib.Path(PIDFILE).write_text(str(child.pid))
    time.sleep(300)
"""


def test_run_pytest_times_out_and_kills_the_whole_process_group(tmp_path: Path) -> None:
    """挂死的套件必须被超时打断，且**孙进程**一起死。

    e2e lane 底下挂着 uvicorn 与 playwright 的 node driver。只杀 pytest 自己会留下一串孤儿
    占着端口，下一次 soak 起服务时以「端口占用」失败——一次挂死污染后面每一次运行。
    这里的孙进程是那两者的替身：它的 pid 由被测套件写在文件里，超时之后必须已经不存在。
    修复前 `run_pytest` 连 `timeout` 形参都没有，本条以 TypeError 红。
    """
    soak = _soak()
    suite = tmp_path / "tests_hang"
    suite.mkdir()
    pidfile = tmp_path / "grandchild.pid"
    (suite / "test_hang.py").write_text(_HANGING_TEST.format(pidfile=str(pidfile)), encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = -p no:cacheprovider\n", encoding="utf-8")

    started = time.monotonic()
    rc, out, duration = soak.run_pytest([str(suite), "-q"], cwd=tmp_path, timeout=6.0)
    elapsed = time.monotonic() - started

    assert rc == soak.RC_TIMEOUT, f"超时没有被归到 RC_TIMEOUT，实际 rc={rc}：\n{out}"
    assert elapsed < 60, f"超时没生效，等了 {elapsed:.1f}s"
    assert duration >= 0
    assert soak.classify_exit_code(rc, soak.Summary()) is not None, "超时必须是不可记账的环境错误"

    assert pidfile.is_file(), "被测套件没来得及写下孙进程 pid，本条的前提不成立"
    grandchild = int(pidfile.read_text().strip())
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.kill(grandchild, 0)
        except (ProcessLookupError, PermissionError):
            break
        time.sleep(0.1)
    else:
        os.kill(grandchild, 9)
        pytest.fail(f"孙进程 {grandchild} 在超时之后还活着：只杀了 pytest，没杀进程组")


# --------------------------------------------------------------------------
# 审计 #26（Medium）：写不进去 ≠ 这次运行红了
# --------------------------------------------------------------------------
def test_a_log_write_failure_exits_with_the_environment_code_not_the_red_code(tmp_path: Path) -> None:
    """产物目录不可用时退 3（环境错误），不是 1（red 且已记账），也不是一屏 traceback。

    退出码 1 在本脚本的契约里恰好是「red 且已（或可）记账」。让 `OSError` 逃出去，进程正好以 1
    收场——调用方会把一次**没写成的绿**当成一次记过账的红，而 §7 规定任意一次 red 终止批次。
    """
    soak = _soak()
    n = _expected()
    ledger = _fresh_ledger(tmp_path)
    green = tmp_path / "green.txt"
    green.write_text(f"{n} passed in 12.5s\n", encoding="utf-8")
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("我是一个文件，不是目录\n", encoding="utf-8")

    proc = _run(
        [
            sys.executable,
            str(SOAK_RUN_PATH),
            "--parse-summary",
            str(green),
            "--ledger",
            str(ledger),
            "--no-precheck",
            "--log-dir",
            str(blocker),
        ],
        cwd=REPO_ROOT,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == soak.EXIT_ENVIRONMENT, f"期望环境错误码 3，实际 {proc.returncode}：\n{combined}"
    assert "Traceback" not in combined, f"未捕获的异常逃了出去：\n{combined}"


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root 无视目录权限位")
def test_a_ledger_write_failure_exits_with_the_environment_code_not_the_red_code(tmp_path: Path) -> None:
    """台账所在目录不可写时同样退 3：可记账的绿 ＋ 写不进去 ＝ 环境错误，不是 red。"""
    soak = _soak()
    n = _expected()
    ledger_dir = tmp_path / "ledger_dir"
    ledger_dir.mkdir()
    ledger = _fresh_ledger(ledger_dir)
    before = ledger.read_bytes()
    green = tmp_path / "green.txt"
    green.write_text(f"{n} passed in 12.5s\n", encoding="utf-8")

    os.chmod(ledger_dir, 0o500)  # 可读可进入，不可写 ⇒ 同目录临时文件建不出来
    try:
        proc = _run(_synthetic_append_argv(green, ledger), cwd=REPO_ROOT)
    finally:
        os.chmod(ledger_dir, 0o700)
    combined = proc.stdout + proc.stderr
    assert proc.returncode == soak.EXIT_ENVIRONMENT, f"期望环境错误码 3，实际 {proc.returncode}：\n{combined}"
    assert proc.returncode != soak.EXIT_RED_RECORDABLE, "写台账失败被当成了一次该清零计数的 red"
    assert "Traceback" not in combined, f"未捕获的异常逃了出去：\n{combined}"
    assert ledger.read_bytes() == before
