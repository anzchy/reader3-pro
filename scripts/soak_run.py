#!/usr/bin/env python3
"""`baseline_1b` 的 soak 运行器：跑一次全量、判绿红、（显式要求时）往台账追一行。

台账：`docs/plans/20260816-tech-stack-migration/tasks/soak-log.md`。八列字段的**唯一定义处**
是迁移计划 §7「台账字段（canonical）」；「绿」的判据在任务书 009 §8 G2；本脚本不复述规则，
只执行。

**绿的判据（G2，逐字）**：一次运行记为绿，**当且仅当** `passed == EXPECTED_BASELINE_ITEMS`
且 `skipped == deselected == failed == errors == 0`。`result` 列由本脚本判定，人工不得改写。
为什么必须写死分母：「无偶发失败」只约束失败数，「全量运行」只约束调用形态，两者都不约束
**实际执行了几条**。给一条不稳的 baseline 用例挂 `@pytest.mark.skip`，`0 failed` 照样成立，
`result` 列只有 green/red——这是让 G2 变绿的零成本、台账无痕的手段。本脚本就是堵它的。

**判定的三态**（`Verdict.result` ∈ {green, red}，`Verdict.recordable` ∈ {True, False}）：

| 形态 | result | 记账 | 理由 |
|---|---|---|---|
| 全绿 | green | 是 | — |
| 真失败（`failed > 0`，无 skip/deselect/error，`passed + failed == 期望`） | red | **是** | §7：任意一次 red 清零。真红不进台账，清零规则就失效 |
| skipped / deselected / errors 非零、条数不符、一条没跑 | red | **否**，退出码 2 | 这不是「一次全量运行」；记成红会清掉一个没跑过的计数，记成绿是假绿 |

矩阵原文「其余四种不写台账并以非零退出码结束」对应第三态。

**`suite_hash` 的取法从台账表头读，不在这里第二次定义。** 表头那个含 `git ls-files` 的
fenced bash 块是唯一定义处（`tests/unit/test_soak_log_contract.py` 也从那里解析）。本脚本把它
原样交给 `bash -c` 执行。**取值前要求工作树对覆盖路径干净**（`git status --porcelain -- <paths>`
为空），否则拒绝落账——`git ls-files -s` 读的是索引，改了没 add 的断言不会体现在哈希里，
那正是清零规则要堵的假绿路径（台账表头「取哈希前必须先确认工作树干净」一节）。

**`log` 列的产物**里要有 `--collect-only` 的条数（台账「两条纳入/排除口径」第 2 条的补偿手段：
`pyproject.toml` 被排除在哈希外，marker 定义被改动时哈希不变，分母写进 log 产物才有据可查）。

**用法**：

    uv run python scripts/soak_run.py                 # 真跑一次 baseline，打印那一行与判定，不写台账
    uv run python scripts/soak_run.py --append        # 同上，且可记账时把行插到分隔行正下方
    uv run python scripts/soak_run.py --parse-summary out.txt [--append --ledger X --no-precheck]
                                                      # 不跑 lane，只解析一份 summary（单测喂合成输入用）

退出码：0 = green；1 = red 且已（或可）记账；2 = 不可记账（拒绝）；3 = 环境/解析错误。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
LEDGER_PATH = REPO_ROOT / "docs" / "plans" / "20260816-tech-stack-migration" / "tasks" / "soak-log.md"
DEFAULT_LOG_DIR = REPO_ROOT / ".claude" / "tdd-guardian" / "soak-logs"

#: 迁移计划 §7 的八列，**顺序敏感**。这里是抄写处，不是定义处。
CANONICAL_COLUMNS: Tuple[str, ...] = (
    "ts_utc",
    "commit",
    "result",
    "duration_s",
    "suite_hash",
    "browser",
    "os",
    "log",
)

#: e2e lane 上 `baseline_1b` 的调用形态。`-m baseline_1b` 是 soak 的计数基准（§7：数的只是 baseline）。
LANE_ARGS: Tuple[str, ...] = (
    "tests/e2e",
    "-m",
    "baseline_1b",
    "--browser",
    "chromium",
    "-q",
    "-p",
    "no:cacheprovider",
)


def _load_groups_constants():  # type: ignore[no-untyped-def]
    """`EXPECTED_BASELINE_ITEMS` 只在 `scripts/lint_e2e_groups.py` 定义一次；按路径加载，`scripts/` 不是包。"""
    path = SCRIPTS_DIR / "lint_e2e_groups.py"
    spec = importlib.util.spec_from_file_location("lint_e2e_groups_for_soak", path)
    assert spec is not None and spec.loader is not None, f"无法加载 {path}"
    module = importlib.util.module_from_spec(spec)
    # 先登记进 sys.modules 再执行：那边的 @dataclass 在 `from __future__ import annotations`
    # 下要经 sys.modules[cls.__module__] 解析字符串注解，不登记会在 3.10 上炸在 dataclasses.wrap。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_GROUPS = _load_groups_constants()
EXPECTED_BASELINE_ITEMS: int = int(_GROUPS.EXPECTED_BASELINE_ITEMS)
#: `-m baseline_1b` 必然 deselect 掉的那些条：验收目录 ＋ 白名单模块。派生，不写字面量——
#: 树一长它就得跟着长，写死 24 等于给下一次扩容埋一颗哑弹。
EXPECTED_NONBASELINE_ITEMS: int = int(_GROUPS.EXPECTED_ACCEPTANCE_ITEMS) + int(_GROUPS.EXPECTED_UNGROUPED_ITEMS)


# ---------------------------------------------------------------------------
# summary 解析
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"(\d+)\s+(passed|failed|errors?|skipped|deselected|xfailed|xpassed|warnings?)")
_SUMMARY_LINE_RE = re.compile(
    r"^(?:=+\s*)?(?P<body>(?:no tests ran|\d+\s+(?:passed|failed|errors?|skipped|deselected|xfailed|xpassed|warnings?)).*?)\s+in\s+(?P<secs>\d+(?:\.\d+)?)s\b"
)


class SummaryParseError(RuntimeError):
    """输出里没有 pytest 的 summary 行——runner 被 kill、OOM、或根本没跑到收尾。"""


@dataclass(frozen=True)
class Summary:
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    deselected: int = 0
    xfailed: int = 0
    xpassed: int = 0
    duration_s: float = 0.0
    ran_any: bool = False
    line: str = ""


def parse_summary(text: str) -> Summary:
    """从 pytest 输出里取**最后一行** summary（`-q` 与默认样式都认），解析各计数。"""
    chosen: Optional[re.Match[str]] = None
    for raw in text.splitlines():
        m = _SUMMARY_LINE_RE.match(raw.strip())
        if m:
            chosen = m
    if chosen is None:
        raise SummaryParseError("输出里找不到 pytest 的 summary 行（`N passed … in Xs` / `no tests ran in Xs`）：\n" + text[-2000:])
    counts: Dict[str, int] = {}
    for n, key in _TOKEN_RE.findall(chosen.group("body")):
        if key.startswith("error"):
            key = "errors"
        elif key.startswith("warning"):
            continue
        counts[key] = int(n)
    ran_any = any(counts.get(k, 0) for k in ("passed", "failed", "errors", "skipped", "xfailed", "xpassed"))
    return Summary(
        passed=counts.get("passed", 0),
        failed=counts.get("failed", 0),
        errors=counts.get("errors", 0),
        skipped=counts.get("skipped", 0),
        deselected=counts.get("deselected", 0),
        xfailed=counts.get("xfailed", 0),
        xpassed=counts.get("xpassed", 0),
        duration_s=float(chosen.group("secs")),
        ran_any=ran_any,
        line=chosen.group(0),
    )


# ---------------------------------------------------------------------------
# 判定
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Verdict:
    result: str  # "green" | "red"
    recordable: bool
    reasons: List[str] = field(default_factory=list)


def verdict(summary: Summary, expected_passed: int, expected_deselected: int = 0) -> Verdict:
    """G2 的判据。`if "failed" not in out` 式实现在 skipped / deselected / 条数不符上全绿——这里逐项拒绝。"""
    reasons: List[str] = []
    if not summary.ran_any:
        reasons.append("一条用例都没跑（no tests ran）——零用例是失败，不是通过")
    if summary.skipped:
        reasons.append(f"skipped == {summary.skipped}（≠ 0）：skipped 不是 passed，被 skip 的用例没有为门槛作证")
    # deselected 的合法值不是 0，是「恰好是那些本就不该被 baseline 选中的条」。原先写死 0 是因为
    # 记录那一刻 tests/e2e 整棵树都是 baseline；WI-17 落地验收目录后，`-m baseline_1b` 必然 deselect
    # 掉它们，写死 0 会让 soak 永远产不出一次可记账的绿。判据的本意没变：一条都不能被"多"筛掉。
    if summary.deselected != expected_deselected:
        reasons.append(
            f"deselected == {summary.deselected}，期望恰好 {expected_deselected} 条"
            "（= 验收目录 ＋ 白名单）：多筛或少筛都说明这次不是完整的 baseline 全量运行"
        )
    if summary.errors:
        reasons.append(f"errors == {summary.errors}（≠ 0）：有 collection / fixture error")
    if summary.xfailed or summary.xpassed:
        reasons.append(f"xfailed == {summary.xfailed}、xpassed == {summary.xpassed}：baseline 里不允许 xfail 构造")
    full_run = not reasons and (summary.passed + summary.failed == expected_passed)
    if summary.failed:
        reasons.append(f"failed == {summary.failed}（≠ 0）")
    if summary.passed != expected_passed and not summary.failed:
        reasons.append(
            f"passed == {summary.passed}，期望 EXPECTED_BASELINE_ITEMS == {expected_passed}：分母不对，这次运行不算绿"
        )
    elif summary.failed and summary.passed + summary.failed != expected_passed:
        reasons.append(
            f"passed + failed == {summary.passed + summary.failed}，期望 {expected_passed}：连失败在内的条数也不对"
        )
    if not reasons:
        return Verdict("green", True, [])
    # 真失败且其余全为 0、条数对得上 ⇒ 是一次应当清零计数的 red，必须进台账。
    return Verdict("red", full_run, reasons)


# ---------------------------------------------------------------------------
# 跑 lane
# ---------------------------------------------------------------------------


def run_pytest(args: Sequence[str], cwd: Path) -> Tuple[int, str, float]:
    """真 subprocess 跑 `python -m pytest <args>`，返回 (退出码, 合并输出, 时长秒)。"""
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr, time.monotonic() - started


def collect_only_count(cwd: Path) -> str:
    """`--collect-only -q` 的 summary 行（写进 log 产物：分母的证据）。"""
    _, out, _ = run_pytest(["tests/e2e", "-m", "baseline_1b", "--collect-only", "-q", "-p", "no:cacheprovider"], cwd)
    lines = [ln for ln in out.splitlines() if "collected" in ln]
    return lines[-1] if lines else out[-300:]


# ---------------------------------------------------------------------------
# 台账列的取值
# ---------------------------------------------------------------------------


def _git(args: Sequence[str], cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def hash_command_from_ledger(ledger_text: str) -> str:
    """台账表头里含 `git ls-files` 的那个 fenced bash 块——`suite_hash` 取法的唯一定义处。"""
    blocks = re.findall(r"^```bash[^\n]*\n(.*?)^```", ledger_text, re.S | re.M)
    candidates = [b for b in blocks if "git ls-files" in b]
    if len(candidates) != 1:
        raise RuntimeError(f"台账里含 `git ls-files` 的 fenced bash 块应恰好 1 个，实际 {len(candidates)} 个")
    return candidates[0]


def hash_covered_paths(block: str) -> List[str]:
    body = "\n".join(ln for ln in block.splitlines() if not ln.strip().startswith("#")).replace("\\\n", " ")
    m = re.search(r"git\s+ls-files\s+-s\s+(?P<paths>.*?)\|", body, re.S)
    if m is None:
        raise RuntimeError("哈希命令里找不到 `git ls-files -s <paths> |`")
    return [t for t in m.group("paths").split() if not t.startswith("-")]


def suite_hash(ledger_text: str, cwd: Path) -> str:
    block = hash_command_from_ledger(ledger_text)
    proc = subprocess.run(["bash", "-c", block], cwd=cwd, capture_output=True, text=True, check=True)
    value = proc.stdout.strip().splitlines()[-1].strip()
    if not re.fullmatch(r"[0-9a-f]{12}", value):
        raise RuntimeError(f"suite_hash 形状不合法：{value!r}")
    return value


def dirty_covered_paths(ledger_text: str, cwd: Path) -> List[str]:
    """覆盖路径里有未 add 的改动 ⇒ 哈希记的是索引里的旧内容，不是刚跑过的那份。"""
    paths = hash_covered_paths(hash_command_from_ledger(ledger_text))
    out = _git(["status", "--porcelain", "--", *paths], cwd)
    return [ln for ln in out.splitlines() if ln.strip()]


def browser_label() -> str:
    """`chromium-<build>`：从 playwright 的 browsers.json 读构建号，不起浏览器。"""
    try:
        import playwright  # type: ignore[import-not-found]

        data = json.loads((Path(playwright.__file__).parent / "driver" / "package" / "browsers.json").read_text())
        for b in data.get("browsers", []):
            if b.get("name") == "chromium":
                return f"chromium-{b.get('revision')}"
    except Exception:  # noqa: BLE001 - 标签取不到就退化成包版本，不让一列的装饰阻断落账
        pass
    try:
        from importlib.metadata import version

        return f"chromium-playwright{version('playwright')}"
    except Exception:  # noqa: BLE001
        return "chromium-unknown"


def os_label() -> str:
    return f"{platform.system().lower()}-{platform.release()}"


def format_row(fields: Dict[str, str]) -> str:
    """八列、canonical 顺序、单行。缺列直接抛：缺一列该行不计数，与其记一行残的不如不记。"""
    missing = [c for c in CANONICAL_COLUMNS if c not in fields]
    if missing:
        raise KeyError(f"台账行缺列：{missing}")
    cells = [str(fields[c]).replace("|", "\\|").replace("\n", " ") for c in CANONICAL_COLUMNS]
    return "| " + " | ".join(cells) + " |"


def append_row(ledger: Path, row: str) -> None:
    """把一行插到**第一张表的分隔行正下方**（已有数据行之后、空行之前），中间不留空行。

    契约测试只解析文件里第一张表的连续块，一个空行就把后面的行踢出解析范围——
    `pre-freeze` 检查会对它视而不见并照常报绿。
    """
    lines = ledger.read_text(encoding="utf-8").splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.strip().startswith("|")), None)
    if start is None or start + 1 >= len(lines):
        raise RuntimeError(f"{ledger} 里找不到台账表（表头行 + 分隔行）")
    sep = lines[start + 1]
    if not (sep.strip().startswith("|") and "-" in sep):
        raise RuntimeError(f"{ledger} 第一张表的第二行不是分隔行：{sep!r}")
    end = start + 2
    while end < len(lines) and lines[end].strip().startswith("|"):
        end += 1
    lines.insert(end, row)
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--append", action="store_true", help="可记账时把行追加进台账（默认只打印）")
    p.add_argument("--ledger", type=Path, default=LEDGER_PATH, help="台账路径（单测用 tmp 副本）")
    p.add_argument("--parse-summary", type=Path, default=None, help="不跑 lane，只解析这份 summary 文本（`-` = stdin）")
    p.add_argument("--no-precheck", action="store_true", help="跳过「覆盖路径工作树干净」的前置检查（只在 --parse-summary 下有意义）")
    p.add_argument("--log-dir", type=Path, default=None, help="log 产物目录（默认 .claude/tdd-guardian/soak-logs/）")
    p.add_argument("--expected", type=int, default=EXPECTED_BASELINE_ITEMS, help=argparse.SUPPRESS)
    # 默认值故意是 None 而不是常量：deselected 该是多少，是 LANE_ARGS 这次调用形态的性质。
    # --parse-summary 模式下这份 summary 不是本脚本跑出来的，脚本无从知道对面用了什么 -m，
    # 套用 24 会把一份合法的全量 summary 误判成红。见 main() 里的落地。
    p.add_argument("--expected-deselected", type=int, default=None, help=argparse.SUPPRESS)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    ledger: Path = args.ledger
    if not ledger.is_file():
        print(f"台账不存在：{ledger}")
        return 3
    ledger_text = ledger.read_text(encoding="utf-8")
    # `suite_hash` 的取法只在 canonical 台账的表头定义一次。`--ledger` 指向别处（单测的 tmp 副本）
    # 且那份里没有命令块时，命令仍从 canonical 台账读——写到哪里可以换，取法不能有第二份。
    if "git ls-files" not in ledger_text and LEDGER_PATH.is_file():
        hash_source_text = LEDGER_PATH.read_text(encoding="utf-8")
    else:
        hash_source_text = ledger_text

    # ---- 前置检查：覆盖路径的工作树必须干净（真跑时强制；parse 模式可跳） ----
    if args.parse_summary is None or not args.no_precheck:
        try:
            dirty = dirty_covered_paths(hash_source_text, REPO_ROOT)
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            print(f"无法执行前置检查：{exc}")
            return 3
        if dirty and args.append:
            print("拒绝落账：suite_hash 覆盖路径里有未进索引的改动，哈希记的会是旧内容——先 git add：")
            for ln in dirty:
                print(f"  {ln}")
            return 2
        if dirty:
            print("提示：覆盖路径里有未进索引的改动（本次不落账，仅打印）：")
            for ln in dirty:
                print(f"  {ln}")

    # ---- 取 summary：真跑 or 解析 ----
    # 只有「真跑 ＋ 落账」才把产物写进仓库内的默认目录；parse 模式与 dry run 一律进临时目录，
    # 免得单测或一次试跑往 .claude/ 下留文件。
    real_append = args.append and args.parse_summary is None
    log_dir: Path = args.log_dir or (DEFAULT_LOG_DIR if real_append else Path(tempfile.mkdtemp(prefix="soak-")))
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        commit = _git(["rev-parse", "--short", "HEAD"], REPO_ROOT)
    except subprocess.CalledProcessError:
        commit = "unknown"

    if args.parse_summary is not None:
        text = sys.stdin.read() if str(args.parse_summary) == "-" else args.parse_summary.read_text(encoding="utf-8")
        collect_line = "(parse-summary 模式：未做 --collect-only)"
        wall = None
    else:
        collect_line = collect_only_count(REPO_ROOT)
        print(f"[soak] {collect_line}")
        print(f"[soak] 运行：python -m pytest {' '.join(LANE_ARGS)}")
        _, text, wall = run_pytest(LANE_ARGS, REPO_ROOT)

    try:
        summary = parse_summary(text)
    except SummaryParseError as exc:
        print(f"解析失败：{exc}")
        return 3
    if args.expected_deselected is not None:
        expected_deselected = args.expected_deselected
    else:
        # 真跑 = 本脚本发的 `-m baseline_1b`，必然筛掉验收目录与白名单；解析别人的 summary 则不设此预期。
        expected_deselected = 0 if args.parse_summary is not None else EXPECTED_NONBASELINE_ITEMS
    v = verdict(summary, args.expected, expected_deselected)

    log_path = log_dir / f"{ts.replace(':', '')}-{commit}.log"
    log_path.write_text(
        f"# soak run {ts} @ {commit}\n# collect-only: {collect_line}\n# summary: {summary.line}\n"
        f"# verdict: {v.result} recordable={v.recordable}\n"
        + "".join(f"# reason: {r}\n" for r in v.reasons)
        + "\n"
        + text,
        encoding="utf-8",
    )

    try:
        hash_value = suite_hash(hash_source_text, REPO_ROOT)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"取 suite_hash 失败：{exc}")
        return 3

    fields = {
        "ts_utc": ts,
        "commit": commit,
        "result": v.result,
        "duration_s": f"{summary.duration_s:g}",
        "suite_hash": hash_value,
        "browser": browser_label(),
        "os": os_label(),
        "log": str(log_path.relative_to(REPO_ROOT)) if REPO_ROOT in log_path.parents else str(log_path),
    }
    row = format_row(fields)

    print(f"[soak] summary: {summary.line}")
    print(f"[soak] verdict: {v.result}（可记账：{'是' if v.recordable else '否'}）")
    for r in v.reasons:
        print(f"[soak]   - {r}")
    print(f"[soak] row: {row}")
    if wall is not None:
        print(f"[soak] 墙钟 {wall:.1f}s")

    if not v.recordable:
        print("[soak] 拒绝记账：这不是一次可计数的全量运行（skipped / deselected / errors / 条数不符 / 零用例）。")
        return 2
    if args.append:
        append_row(ledger, row)
        print(f"[soak] 已追加到 {ledger}（分隔行正下方，无空行）")
    else:
        print("[soak] dry run：未写台账（加 --append 才写）")
    return 0 if v.result == "green" else 1


if __name__ == "__main__":
    sys.exit(main())
