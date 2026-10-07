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
| 真失败（`failed > 0`，无 skip/deselect/error，`passed + failed == 期望`） | red | **是** | §7 批次规则 2：任意一次 red 终止当前批次。真红不进台账，批次规则就失效 |
| skipped / deselected / errors 非零、条数不符、一条没跑 | red | **否**，退出码 2 | 这不是「一次全量运行」；记成红会让一次没跑完的运行终止批次，记成绿是假绿 |

矩阵原文「其余四种不写台账并以非零退出码结束」对应第三态。

**`suite_hash` 覆盖了哪些路径，仍以台账表头那个 fenced bash 块为准**（`tests/unit/
test_soak_log_contract.py` 也从那里解析）。但**本脚本不再把那个块交给 `bash -c` 执行**：
台账是一份可编辑的 Markdown，`bash -c <从 Markdown 抠出来的字符串>` 等于「改一行文档就能在
soak 运行器里执行任意命令」，而校验只看输出末 12 位像不像哈希，任何前置副作用都照单全收。
改法见 `parse_hash_recipe()`：把那个块**解析**成一条定死形状的配方（`{ git ls-files -s <八条
路径> | git hash-object --stdin; } | cut -c1-12`），逐段比对管道形状、逐条比对路径白名单
（`HASH_COVERED_PATHS`），然后以**参数列表**分别调 `git ls-files -s` 与 `git hash-object
--stdin`，全程无 shell。取值与旧实现逐字节相同（`91de0e171b5c`）。

`HASH_COVERED_PATHS` 是白名单，**不是覆盖面的第二个定义处**：覆盖面仍由台账表头定义，这里是
第二把钥匙。要给哈希加一条路径，台账与这份白名单必须一起改，否则本脚本会大声拒绝——
「改覆盖面」是一次应当留下两处签名的动作。

**`--append` 前要求整棵工作树干净**（`dirty_worktree()`：`git status --porcelain=v1 -z
--untracked-files=all`，豁免台账本身，以及有效 log 目录下**未跟踪的 `*.log`**——且该目录与哈希覆盖
路径互不包含、目录下没有 git 跟踪的 `*.py`，否则不豁免；规则见 `dirty_worktree()`），任何一条脏条目
都拒绝落账，退出码 2。只查覆盖路径不够：`git ls-files -s` 读的是索引，改了没 add 的断言不会体现在哈希里；
而覆盖路径之外的野文件（根目录一个 `conftest.py`、一处改过的 lint 脚本）照样能改变那次运行，
哈希却一字不变——这两条都是批次规则要堵的假绿路径（台账表头「取哈希前必须先确认工作树干净」
一节）。开发中的工作树本来就脏，正确做法是在干净的 detached worktree 里跑、`--ledger` 指回
主仓库的台账。dry run 只打印提示；`--no-precheck` 只在 `--parse-summary` 模式下生效。

**pytest 的退出码是判据的一部分**（`classify_exit_code()`）。只看 summary 文本会把「打印完
`65 passed` 之后 plugin/atexit 炸了」记成绿：那一行是真的，那次运行不是。规则——`rc == 0` 才
可能绿；`rc == 1` 只在 summary 自洽地报了 failed/errors 时接受（那是该终止批次的真红）；其余任何
退出码（含 2 中断、3 internal error、5 no tests collected、124 本脚本的超时）一律判为
**不可记账的环境错误**，退出码 3。

**`--parse-summary` 与 `--append` 互斥**：解析模式下这份 summary 不是本脚本跑出来的，没有退出
码、没有 collect-only 分母、log 产物落在临时目录。允许它落账，就等于允许
`echo "65 passed in 1s" | soak_run.py --parse-summary - --append` 往 canonical 台账写一行带真
commit、真 suite_hash 的绿——零条用例的绿。单测要验证落账路径时走
`--allow-synthetic-append`，它**只接受仓库之外的临时台账**，碰 canonical 台账照样拒绝。

**`log` 列的产物**里要有 `--collect-only` 的条数（台账「两条纳入/排除口径」第 2 条的补偿手段：
`pyproject.toml` 被排除在哈希外，marker 定义被改动时哈希不变，分母写进 log 产物才有据可查）。
文件名带随机后缀并以 `O_EXCL` 独占创建：秒级时间戳 ＋ commit 在同一秒的两次运行上会撞名，
撞名意味着两行台账指着同一份产物、其中一份的证据已被覆盖。撞上就拒绝，不覆盖。

**用法**：

    uv run python scripts/soak_run.py                 # 真跑一次 baseline，打印那一行与判定，不写台账
    uv run python scripts/soak_run.py --append        # 同上，且可记账时把行插到分隔行正下方
    uv run python scripts/soak_run.py --parse-summary out.txt [--ledger X --no-precheck]
                                                      # 不跑 lane，只解析一份 summary（单测喂合成输入用）
    uv run python scripts/soak_run.py --verdict B1 [--ledger X]
                                                      # 只读：按台账表头的批次声明判一批，打印一行
                                                      # `PASS B1 10/10（首 ts – 末 ts）` 或 `FAIL B1: <理由>`

退出码：0 = green；1 = red 且已（或可）记账；2 = 不可记账（拒绝）；3 = 环境/解析错误
（含：台账/log 写入失败、pytest 退出码与 summary 不自洽、套件超时、`--parse-summary --append`）。

`--verdict` 自成一套、只有两档：0 = PASS；1 = 其余一切（FAIL、未知批次 ID、声明重复或不合形状、
台账缺失或读不了、与 `--append` / `--parse-summary` 同用）。它在参数解析后立刻分派，
不取哈希、不做前置检查、不跑 pytest、不建 log 目录、不调 git——只读台账。

argparse 自己的用法错误（如 `--verdict` 后面没给值、未知参数）在进入上面任何一套之前就以
**退出码 2** 结束并打印 `usage:`——那是 argparse 退出的，不是本脚本判的；`--verdict` 的
「只有 0 / 1 两档」只对参数解析成功之后的路径成立。
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import hashlib
import importlib.util
import json
import logging
import os
import platform
import re
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

try:  # POSIX only；本仓库的 lane 全在 macOS / Linux 上跑。
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

LOGGER = logging.getLogger("soak_run")

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
LEDGER_PATH = REPO_ROOT / "docs" / "plans" / "20260816-tech-stack-migration" / "tasks" / "soak-log.md"
DEFAULT_LOG_DIR = REPO_ROOT / ".claude" / "tdd-guardian" / "soak-logs"

#: 退出码。文件头 docstring 是定义处，这里是它的可引用形式。
EXIT_GREEN = 0
EXIT_RED_RECORDABLE = 1
EXIT_UNRECORDABLE = 2
EXIT_ENVIRONMENT = 3

#: 全量 baseline 实测约 58s（台账 Wave 6 一行）。给到 30 分钟 ＝ 约 30×，够慢机器 ＋ 首次装浏览器，
#: 又远小于「一个挂死的 lane 把 G2 那天整台机器占住」。超时按 `RC_TIMEOUT` 归入环境错误，不记账。
SUITE_TIMEOUT_S = 1800.0
#: 借 GNU `timeout(1)` 的约定：124 = 因超时被杀。pytest 自己不会返回它，所以不会与真实退出码混淆。
RC_TIMEOUT = 124

#: 前置检查里每一次 git 调用（`git status`、`git ls-files`）的上限。挂死的 git（锁住的索引、
#: 网络文件系统）超时即视为「前置检查无法执行」，退出码 3——绝不因为等不到就当干净放行。
GIT_PRECHECK_TIMEOUT_S = 60.0

#: 台账被并发追加时等锁的上限。超过就报错退出，绝不「等不到锁就直接写」。
LEDGER_LOCK_TIMEOUT_S = 30.0

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

#: `suite_hash` 允许覆盖的路径白名单，**顺序敏感**，必须与台账表头那条命令逐字、同序相等。
#: 这不是覆盖面的定义处（定义处是台账表头），是执行前的第二把钥匙——见文件头 docstring。
HASH_COVERED_PATHS: Tuple[str, ...] = (
    "tests/e2e/baseline_1b",
    "tests/e2e/conftest.py",
    "tests/e2e/helpers.py",
    "tests/e2e/test_harness_smoke.py",
    "tests/fixtures/epub_corpus.py",
    "tests/fixtures/epub_zip.py",
    "tests/fixtures/ai_stub.py",
    "tests/conftest.py",
)

#: `cut -c1-12`：台账里所有历史值都是 12 位，`test_soak_log_contract` 也按 12 位断形状。
HASH_TRUNCATE = 12

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
    # 真失败且其余全为 0、条数对得上 ⇒ 是一次应当终止批次的 red，必须进台账。
    return Verdict("red", full_run, reasons)


# ---------------------------------------------------------------------------
# 跑 lane
# ---------------------------------------------------------------------------


def _kill_process_group(proc: "subprocess.Popen[str]") -> None:
    """杀**整个进程组**，不是只杀 pytest 自己。

    e2e lane 底下挂着 uvicorn 子进程与 playwright 的 node driver。只 `proc.kill()` 会留下
    一串孤儿进程继续占端口，下一次 soak 起服务时以「端口占用」的形态失败——一次挂死污染
    后面每一次运行。所以 `run_pytest` 用 `start_new_session=True` 把它们圈进一个新会话，
    超时时对整组发 SIGKILL。
    """
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, OSError) as exc:  # 进程已退出 / 平台不支持
        LOGGER.debug("取不到进程组（pid=%s）：%r", proc.pid, exc)
    else:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError) as exc:
            LOGGER.debug("killpg(%s) 失败：%r", pgid, exc)
    with contextlib.suppress(ProcessLookupError):
        proc.kill()


def run_pytest(args: Sequence[str], cwd: Path, timeout: float = SUITE_TIMEOUT_S) -> Tuple[int, str, float]:
    """真 subprocess 跑 `python -m pytest <args>`，返回 (退出码, 合并输出, 时长秒)。

    **必须有超时**：一个挂死的浏览器、一次服务端 teardown 卡住、一个自旋的 plugin，都会让
    soak 运行器无限期地停在这里——没有输出、没有退出码、也没有台账行，与「今天还没跑」完全同形。
    超时返回 `RC_TIMEOUT`，由 `classify_exit_code()` 归入不可记账的环境错误。
    """
    started = time.monotonic()
    proc = subprocess.Popen(  # noqa: S603 - 参数全是本模块常量，无 shell
        [sys.executable, "-m", "pytest", *args],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        out, _ = proc.communicate()
        out = (out or "") + f"\n[soak] 套件超时（{timeout:g}s），已 SIGKILL 整个进程组\n"
        rc = RC_TIMEOUT
    return rc, out or "", time.monotonic() - started


def classify_exit_code(rc: int, summary: Summary) -> Optional[str]:
    """pytest 的退出码与 summary 是否自洽。返回 None ＝ 自洽；返回字符串 ＝ 不可记账的理由。

    只读 summary 文本是不够的：`65 passed in 58s` 打印之后，一个 atexit 钩子、一个 teardown
    异常、一个 `pytest_sessionfinish` 里的 `session.exitstatus = 3` 都能让进程以非零码收场，
    而那一行 summary 仍然是真的。把它记成绿，等于用一行日志替代了一次运行的结论。
    """
    if rc == RC_TIMEOUT:
        return f"pytest 因超时（{SUITE_TIMEOUT_S:g}s）被杀，退出码记作 {RC_TIMEOUT}：这次运行没有跑完，既非绿也非该清零的红"
    if rc == 0:
        if summary.failed or summary.errors:
            return (
                f"pytest 退出码 0，但 summary 报 failed={summary.failed} errors={summary.errors}："
                "退出码与 summary 不自洽，两者必有一个是假的"
            )
        return None
    if rc == 1:
        if summary.failed or summary.errors:
            return None
        return (
            "pytest 退出码 1（测试失败），但 summary 里 failed == errors == 0："
            "退出码与 summary 不自洽，这次运行的结论不可信"
        )
    return (
        f"pytest 退出码 {rc}（既不是 0 也不是 1）：中断 / internal error / 用法错误 / 零收集之类，"
        "无论 summary 印了什么，这都不是一次可计数的全量运行"
    )


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


class HashRecipeError(RuntimeError):
    """台账里的哈希命令不是那条定死形状的配方——多了一段管道、换了一个工具、动了路径清单。"""


@dataclass(frozen=True)
class HashRecipe:
    """从台账表头解析出来的 `suite_hash` 配方。**没有一段是自由文本**，全部是校验过的枚举值。"""

    paths: Tuple[str, ...]
    truncate: int


def hash_command_from_ledger(ledger_text: str) -> str:
    """台账表头里含 `git ls-files` 的那个 fenced bash 块——`suite_hash` 覆盖面的定义处。"""
    blocks = re.findall(r"^```bash[^\n]*\n(.*?)^```", ledger_text, re.S | re.M)
    candidates = [b for b in blocks if "git ls-files" in b]
    if len(candidates) != 1:
        raise HashRecipeError(f"台账里含 `git ls-files` 的 fenced bash 块应恰好 1 个，实际 {len(candidates)} 个")
    return candidates[0]


#: 允许出现在配方里的路径形状。排掉 `-foo`（会被 git 当选项）、`..`、`$`/反引号/分号之类。
_SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")


def _tokenize_block(block: str) -> List[str]:
    """去注释、接续行、把 `{` `}` `|` `;` 拆成独立 token。**归一化到此为止，不做任何求值。**"""
    body = "\n".join(ln for ln in block.splitlines() if not ln.strip().startswith("#"))
    body = body.replace("\\\n", " ")
    for sym in ("{", "}", "|", ";"):
        body = body.replace(sym, f" {sym} ")
    return body.split()


def parse_hash_recipe(ledger_text: str) -> HashRecipe:
    """把台账表头那个 bash 块**解析**成配方；形状不符即抛，绝不执行。

    旧实现是 `subprocess.run(["bash", "-c", block])`——块的内容来自一份人人可编辑的 Markdown，
    校验又只看输出末 12 位像不像十六进制，于是任何前置命令（`rm -rf`、外传、改索引再算哈希）
    都能一边生效一边产出一个合法的值。这里换成白名单解析：管道形状逐 token 比对，路径逐条
    比对 `HASH_COVERED_PATHS`，取值阶段走参数列表、无 shell。
    """
    tokens = _tokenize_block(hash_command_from_ledger(ledger_text))
    head = ["{", "git", "ls-files", "-s"]
    if tokens[: len(head)] != head:
        raise HashRecipeError(f"配方开头必须是 `{{ git ls-files -s`，实际：{tokens[:len(head)]}")
    rest = tokens[len(head) :]
    if "|" not in rest:
        raise HashRecipeError("配方里 `git ls-files -s` 之后找不到管道符")
    cut = rest.index("|")
    paths = rest[:cut]
    tail = rest[cut:]
    expected_tail = ["|", "git", "hash-object", "--stdin", ";", "}", "|", "cut", f"-c1-{HASH_TRUNCATE}"]
    if tail != expected_tail:
        raise HashRecipeError(
            "配方的管道段必须逐字是 "
            f"`{' '.join(expected_tail)}`，实际：`{' '.join(tail)}`"
        )
    bad = [p for p in paths if not _SAFE_PATH_RE.match(p) or ".." in p.split("/")]
    if bad:
        raise HashRecipeError(f"配方里的路径形状不合法（只允许仓库内的相对路径）：{bad}")
    if tuple(paths) != HASH_COVERED_PATHS:
        raise HashRecipeError(
            "台账里的覆盖路径与 soak_run.HASH_COVERED_PATHS 不一致——覆盖面要改，两处必须一起改：\n"
            f"  台账：{paths}\n  白名单：{list(HASH_COVERED_PATHS)}"
        )
    return HashRecipe(paths=tuple(paths), truncate=HASH_TRUNCATE)


def hash_covered_paths(ledger_text: str) -> List[str]:
    """配方覆盖的路径清单（校验过的）。"""
    return list(parse_hash_recipe(ledger_text).paths)


def suite_hash(ledger_text: str, cwd: Path) -> str:
    """`git ls-files -s <paths> | git hash-object --stdin | cut -c1-12`，两步都走参数列表，无 shell。

    两处 `text=False` 是刻意的：`git hash-object` 哈希的是**字节**，文本模式的换行翻译会
    在有 `\\r` 的环境下改掉输入，值就不再与台账里那条命令逐字节相同。
    """
    recipe = parse_hash_recipe(ledger_text)
    listing = subprocess.run(  # noqa: S603 - 参数列表；paths 已过白名单
        ["git", "ls-files", "-s", "--", *recipe.paths],
        cwd=str(cwd),
        capture_output=True,
        check=True,
    ).stdout
    digest = subprocess.run(  # noqa: S603
        ["git", "hash-object", "--stdin"],
        cwd=str(cwd),
        input=listing,
        capture_output=True,
        check=True,
    ).stdout
    value = digest.decode("ascii", "replace").strip()[: recipe.truncate]
    if not re.fullmatch(r"[0-9a-f]{%d}" % recipe.truncate, value):
        raise HashRecipeError(f"suite_hash 形状不合法：{value!r}")
    return value


def _is_exempt(path: str, exempt_files: Sequence[str], exempt_dirs: Sequence[str]) -> bool:
    """文件全等；目录按 `/` 段边界——`soak-logs/x` 算，`soak-logs-evil/x` 不算。"""
    if path in exempt_files:
        return True
    return any(path == d or path.startswith(d + "/") for d in exempt_dirs)


def dirty_entries(
    porcelain_z: str,
    exempt_files: Sequence[str],
    exempt_dirs: Sequence[str],
    untracked_log_dirs: Sequence[str] = (),
) -> List[str]:
    """解析 `git status --porcelain=v1 -z --untracked-files=all`，返回不被豁免覆盖的每一条。

    返回形式（Q5）：git 在 `-z` 下报的原样路径（不加引号，非 ASCII 原样）；重命名/复制返回
    **新**路径；顺序即 porcelain 顺序。重命名/复制的记录是 `XY NEW\\0ORIG\\0`——X 为 `R`/`C`
    就带 orig 尾巴，不管 Y 是空格还是 `M`（`RM`/`CM` = 改名后又在工作树里改过）。
    重命名/复制只有新旧两条路径都豁免才算豁免：把非豁免文件挪进日志目录不能把它洗白。
    记录不合形状直接抛 `RuntimeError`——宁可拒绝落账，也不把看不懂的输出当干净。

    `untracked_log_dirs`：只豁免其下 `??`（未跟踪）且以 `.log` 结尾的条目——改过的已跟踪 log、
    野 `.py`、任何非 log 文件照报。`exempt_dirs` 保留「任何状态都豁免」的旧口径，供纯函数单测用；
    `dirty_worktree` 不再把日志目录放进 `exempt_dirs`。
    """
    tokens = porcelain_z.split("\0")
    if tokens and tokens[-1] == "":
        tokens.pop()
    out: List[str] = []
    i = 0
    while i < len(tokens):
        rec = tokens[i]
        i += 1
        if len(rec) < 4 or rec[2] != " ":
            raise RuntimeError(f"git status 的记录不合 porcelain v1 形状：{rec!r}")
        xy, path = rec[:2], rec[3:]
        paths = [path]
        if xy[0] in "RC":
            if i >= len(tokens):
                raise RuntimeError(f"重命名/复制记录缺原路径：{rec!r}")
            paths.append(tokens[i])
            i += 1
        if xy == "??" and path.endswith(".log") and _is_exempt(path, (), untracked_log_dirs):
            continue
        if not all(_is_exempt(p, exempt_files, exempt_dirs) for p in paths):
            out.append(path)
    return out


def _rel_inside(path: Path, cwd: Path) -> Optional[str]:
    """`path` 在 `cwd` 树内 ⇒ 相对 posix 路径；树外（或就是树根本身）⇒ None，即不豁免。"""
    try:
        rel = path.resolve().relative_to(cwd.resolve())
    except ValueError:
        return None
    s = rel.as_posix()
    # 日志目录就是仓库根时 rel 是 "."——豁免它等于豁免整棵树，fail closed：不豁免。
    return None if s in ("", ".") else s


def _overlaps(a: str, b: str) -> bool:
    """两条仓库相对 posix 路径相等或一条在另一条之内（按 `/` 段边界）。"""
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _git_precheck(args: Sequence[str], cwd: Path) -> bytes:
    """前置检查专用的 git 调用：参数列表、无 shell、带超时。超时 ⇒ `RuntimeError`（退出码 3 那条路）。"""
    try:
        return subprocess.run(  # noqa: S603
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            check=True,
            timeout=GIT_PRECHECK_TIMEOUT_S,
        ).stdout
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"git {' '.join(args)} 超时（>{GIT_PRECHECK_TIMEOUT_S:g}s），前置检查无法执行") from exc


def log_dir_exemptible(rel_log_dir: str, cwd: Path) -> bool:
    """日志目录能不能拿到（仅限未跟踪 `*.log` 的）豁免。

    日志目录豁免必须 fail closed，否则 `--append --log-dir tests/e2e` 就能把套件里改过的文件
    或一个野 `conftest.py` 整个藏起来。规则三条，任一不满足即**整体不豁免**：
    1. 只豁免目录下**未跟踪**（`??`）且以 `.log` 结尾的条目——本脚本只往里写 `*.log`；已跟踪
       log 被改、目录里冒出 `.py` 或别的文件，一律照报（见 `dirty_entries`）。
       默认目录 `.claude/tdd-guardian/soak-logs` 本身有已跟踪的历史 log，这条规则让它照常可用：
       历史 log 不改就不出现在 `git status` 里，新 log 是未跟踪的 `*.log`。
    2. 目录与 `HASH_COVERED_PATHS` 任一条相等或互相包含（`tests`、`tests/e2e`、
       `tests/e2e/baseline_1b/x`）——覆盖面里的任何东西都不许靠日志目录洗白。
    3. 目录下有 git 跟踪的 `*.py`（`git ls-files -z -- <dir>`）——那是代码目录，不是日志目录。
    """
    if any(_overlaps(rel_log_dir, p) for p in HASH_COVERED_PATHS):
        return False
    tracked = _git_precheck(["--literal-pathspecs", "ls-files", "-z", "--", rel_log_dir], cwd)
    names = tracked.decode("utf-8", errors="surrogateescape").split("\0")
    return not any(n.endswith(".py") for n in names)


def dirty_worktree(cwd: Path, ledger: Path, log_dir: Path) -> List[str]:
    """整棵工作树的脏条目（去掉台账本身与日志目录）。

    薄包装：豁免集合由 `resolve()` + `relative_to(cwd)` 决定——台账/日志目录在树外就没有
    豁免（按相对名字转移豁免会让树外台账洗白树内同名文件）。git 用参数列表调用，不经 shell；
    `-z` 免掉非 ASCII 路径的八进制引号，`--untracked-files=all` 防止一个野文件藏在折叠的
    `?? dir/` 后面。gitignore 掉的文件 git 不报，这里也不算（计划里的既定取舍）。
    git 失败（不是仓库等）抛 `CalledProcessError`，超时抛 `RuntimeError`，绝不返回 `[]`——
    失败不能开门。日志目录的豁免口径见 `log_dir_exemptible()`。
    """
    exempt_files = [r for r in (_rel_inside(ledger, cwd),) if r is not None]
    porcelain = _git_precheck(["status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd)
    rel_log = _rel_inside(log_dir, cwd)
    log_dirs = [rel_log] if rel_log is not None and log_dir_exemptible(rel_log, cwd) else []
    return dirty_entries(porcelain.decode("utf-8", errors="surrogateescape"), exempt_files, (), log_dirs)


def browser_label() -> str:
    """`chromium-<build>`：从 playwright 的 browsers.json 读构建号，不起浏览器。

    两级退化（构建号 → 包版本 → `chromium-unknown`）都**只捕获具体异常并留下 debug 痕迹**
    （AGENTS.md 异常三档的第 3 档：失败无所谓要说得出为什么，且至少 log 到 debug）。
    为什么无所谓：`browser` 这一列的用途是「换了浏览器就不是同一批」，取不到精确构建号会让这条
    判据变迟钝，但**不会**让一次运行被误判成绿；反过来，为一列标签取不到就中断落账，会把一次
    真跑出来的绿丢掉。宽 `except Exception` 不行的理由也在这里——它会把 `KeyboardInterrupt`
    以外的一切（包括 playwright 内部的真 bug）压成一句 `chromium-unknown`。
    """
    try:
        import playwright  # type: ignore[import-not-found]

        package_file = playwright.__file__
        if package_file is None:
            raise AttributeError("playwright.__file__ 是 None（namespace package？）")
        raw = (Path(package_file).parent / "driver" / "package" / "browsers.json").read_text(encoding="utf-8")
        for b in json.loads(raw).get("browsers", []):
            if b.get("name") == "chromium":
                return f"chromium-{b.get('revision')}"
        LOGGER.debug("browsers.json 里没有名为 chromium 的条目")
    except (ImportError, AttributeError, OSError, json.JSONDecodeError, TypeError) as exc:
        LOGGER.debug("读 playwright browsers.json 失败，退化到包版本：%r", exc)

    try:
        from importlib.metadata import PackageNotFoundError, version

        return f"chromium-playwright{version('playwright')}"
    except (ImportError, PackageNotFoundError) as exc:
        LOGGER.debug("取 playwright 包版本失败，退化到 chromium-unknown：%r", exc)
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


class LedgerWriteError(RuntimeError):
    """台账 / log 产物写不下去。**不是**「这次运行红了」，所以退出码是 3 而不是 1。"""


def ledger_lock_path(ledger: Path) -> Path:
    """台账的互斥锁文件。**放在系统临时目录，不放台账旁边**——一个 `soak-log.md.lock`
    落在 `docs/plans/**` 里会变成一条未跟踪文件，污染 `git status`，而锁只需要在一台机器上
    对同一个台账路径唯一。按解析后的绝对路径取摘要作键。
    """
    key = hashlib.sha256(str(ledger.resolve()).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"soak-ledger-{key}.lock"


@contextlib.contextmanager
def _ledger_lock(ledger: Path, timeout: Optional[float] = None) -> Iterator[None]:
    """对台账取排他锁（`flock`）。取不到就抛，绝不「等不到就直接写」。

    `timeout=None` 时在**调用期**读 `LEDGER_LOCK_TIMEOUT_S`（不是把它绑成默认参数）：
    单测要验证「锁被别人拿着时会拒绝」，得能把这个上限调到 1 秒，否则那条用例要等 30 秒。
    """
    if fcntl is None:  # pragma: no cover - 非 POSIX
        yield
        return
    limit = LEDGER_LOCK_TIMEOUT_S if timeout is None else timeout
    lock = ledger_lock_path(ledger)
    fd = os.open(str(lock), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        deadline = time.monotonic() + limit
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                if time.monotonic() >= deadline:
                    raise LedgerWriteError(
                        f"等台账锁超过 {limit:g}s（{lock}）：另一个 soak 正在写 {ledger}，本次拒绝落账"
                    ) from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _atomic_write_text(target: Path, text: str) -> None:
    """同目录临时文件 → flush ＋ fsync → `os.replace`。中途断电/被杀也不会留下半个台账。"""
    directory = target.parent
    fd, tmp_name = tempfile.mkstemp(dir=str(directory), prefix=target.name + ".", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():  # mkstemp 建的是 0600；换掉一份 0644 的台账不该顺手改权限
            os.chmod(tmp, stat.S_IMODE(target.stat().st_mode))
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    dir_fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def append_row(ledger: Path, row: str) -> None:
    """把一行插到**第一张表的分隔行正下方**（已有数据行之后、空行之前），中间不留空行。

    契约测试只解析文件里第一张表的连续块，一个空行就把后面的行踢出解析范围——
    `pre-freeze` 检查会对它视而不见并照常报绿。

    **读—改—写全程持锁，落盘走原子替换。** 台账就是 G2 的证据本身：两次 soak 撞在一起时，
    无锁的「读全文 → 插一行 → 覆写」会让后写的那份直接盖掉先写的那一行——丢掉的可能正是一次
    该终止批次的 red，而丢失在台账上无痕（第三行永远是第三行）。
    """
    with _ledger_lock(ledger):
        lines = ledger.read_text(encoding="utf-8").splitlines()
        start = next((i for i, ln in enumerate(lines) if ln.strip().startswith("|")), None)
        if start is None or start + 1 >= len(lines):
            raise LedgerWriteError(f"{ledger} 里找不到台账表（表头行 + 分隔行）")
        sep = lines[start + 1]
        if not (sep.strip().startswith("|") and "-" in sep):
            raise LedgerWriteError(f"{ledger} 第一张表的第二行不是分隔行：{sep!r}")
        end = start + 2
        while end < len(lines) and lines[end].strip().startswith("|"):
            end += 1
        lines.insert(end, row)
        _atomic_write_text(ledger, "\n".join(lines) + "\n")


def build_log_path(log_dir: Path, ts: str, commit: str, token: Optional[str] = None) -> Path:
    """独占创建一份 log 产物并返回它的路径。撞名即抛，**绝不覆盖**。

    旧命名只有秒级时间戳 ＋ commit：同一秒里跑两次（重试、并行）就是同一个文件名，后一次
    静默覆盖前一次，而两行台账都指着它——其中一行的证据已经不存在了，台账上照样无痕。
    """
    tail = token if token is not None else f"{time.monotonic_ns() % 1_000_000_000:09d}-{secrets.token_hex(3)}"
    path = log_dir / f"{ts.replace(':', '')}-{commit}-{tail}.log"
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError as exc:
        raise LedgerWriteError(f"log 产物撞名，拒绝覆盖既有证据：{path}") from exc
    os.close(fd)
    return path


# ---------------------------------------------------------------------------
# 批次声明
# ---------------------------------------------------------------------------

#: 起始 ts 的唯一格式。先用正则钉死位数（`strptime` 的 `%m` 会收一位数的月），再交 `strptime` 验日期真实性。
BATCH_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_BATCH_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_BATCH_ID_RE = re.compile(r"[A-Za-z0-9_-]+")
_BATCH_COMMIT_RE = re.compile(r"[0-9a-f]{7,40}")
_BATCH_HASH_RE = re.compile(r"[0-9a-f]{12}")

#: 候选行：`> -` 项目符号后紧跟一个反引号记号，且行内出现分隔符（全角 `｜` 或 ASCII `|`）。
#: ASCII `|` 也算候选（裁定 Q1）：只认全角的话，一行打错分隔符的声明会被**静默忽略**，而不是报错。
_BATCH_CANDIDATE_RE = re.compile(r"^>\s*-\s*`[^`]*`")
#: 完整声明：六个反引号字段、全角 `｜` 分隔，字段 6 之后只许空白。注解（「终止」「判定」）写续行。
_BATCH_DECL_RE = re.compile(r"^>\s*-\s*" + "｜".join([r"`([^`]*)`"] * 6) + r"\s*$")


class BatchDeclarationError(ValueError):
    """批次声明不合形状或 ID 重复。整次解析失败——B2 的笔误挡住 B1 的判决，是刻意的 fail closed。"""


@dataclass(frozen=True)
class BatchDeclaration:
    """台账表头「批次声明」的一行。批次身份的唯一来源（表里没有批次列）。"""

    batch_id: str
    start_ts: datetime  # UTC-aware
    commit: str
    suite_hash: str
    browser: str
    os: str


def _parse_batch_ts(value: str, line: str) -> datetime:
    if not _BATCH_TS_RE.fullmatch(value):
        raise BatchDeclarationError(f"起始 ts 须为 `{BATCH_TS_FORMAT}`，得到 {value!r}：{line}")
    try:
        parsed = datetime.strptime(value, BATCH_TS_FORMAT)
    except ValueError as exc:
        raise BatchDeclarationError(f"起始 ts 不是真实时刻 {value!r}：{line}") from exc
    return parsed.replace(tzinfo=timezone.utc)


def parse_batch_declarations(text: str) -> Dict[str, BatchDeclaration]:
    """从台账全文解析批次声明，返回 `{批次 ID: 声明}`（按出现顺序）。纯函数，不读盘。

    严格、fail closed：任一候选行不能完整匹配六字段语法、任一字段形状不对、或 ID 重复，
    都对**整次**解析抛 `BatchDeclarationError`，信息里带出那一行。
    只按 `\\n` 切行：`str.splitlines` 还会在 `\\x85`、`\\u2028` 等字符上断行，把一行声明劈成两半。
    """
    out: Dict[str, BatchDeclaration] = {}
    for raw in text.split("\n"):
        line = raw.rstrip("\r")
        if not _BATCH_CANDIDATE_RE.match(line) or ("｜" not in line and "|" not in line):
            continue
        shown = line.strip()
        m = _BATCH_DECL_RE.match(line)
        if m is None:
            raise BatchDeclarationError(f"批次声明须为六个反引号字段、全角 `｜` 分隔、其后无文字：{shown}")
        batch_id, ts, commit, suite_hash_, browser, os_ = m.groups()
        if not _BATCH_ID_RE.fullmatch(batch_id):
            raise BatchDeclarationError(f"批次 ID 只许 `[A-Za-z0-9_-]`，得到 {batch_id!r}：{shown}")
        start_ts = _parse_batch_ts(ts, shown)
        if not _BATCH_COMMIT_RE.fullmatch(commit):
            raise BatchDeclarationError(f"commit 须为 7–40 位小写十六进制，得到 {commit!r}：{shown}")
        if not _BATCH_HASH_RE.fullmatch(suite_hash_):
            raise BatchDeclarationError(f"suite_hash 须为 12 位小写十六进制，得到 {suite_hash_!r}：{shown}")
        if not browser.strip():
            raise BatchDeclarationError(f"browser 不能为空：{shown}")
        if not os_.strip():
            raise BatchDeclarationError(f"os 不能为空：{shown}")
        if batch_id in out:
            raise BatchDeclarationError(f"批次 ID {batch_id!r} 重复声明：{shown}")
        out[batch_id] = BatchDeclaration(batch_id, start_ts, commit, suite_hash_, browser, os_)
    return out


# ---------------------------------------------------------------------------
# 批次判决
# ---------------------------------------------------------------------------

#: 一批的行数。「连续 10 次全量绿」里的 10。
BATCH_SIZE = 10

#: 判决逐列核对的顺序＝台账列序（裁定 Q4）。一行多列不符时只报第一列。
_VERDICT_COLUMNS: Tuple[str, ...] = ("commit", "result", "suite_hash", "browser", "os")


@dataclass(frozen=True)
class LedgerRow:
    """台账第一张表的一条数据行，单元格原样保留（可能不足八列，由判决报错而不是这里吞掉）。"""

    cells: Tuple[str, ...]

    def _cell(self, name: str) -> str:
        i = CANONICAL_COLUMNS.index(name)
        return self.cells[i] if i < len(self.cells) else ""

    @property
    def ts_utc(self) -> str:
        return self._cell("ts_utc")

    @property
    def commit(self) -> str:
        return self._cell("commit")

    @property
    def result(self) -> str:
        return self._cell("result")

    @property
    def duration_s(self) -> str:
        return self._cell("duration_s")

    @property
    def suite_hash(self) -> str:
        return self._cell("suite_hash")

    @property
    def browser(self) -> str:
        return self._cell("browser")

    @property
    def os(self) -> str:
        return self._cell("os")

    @property
    def log(self) -> str:
        return self._cell("log")


@dataclass(frozen=True)
class BatchVerdict:
    """一批的判决。`rows` 是窗口里选中的行（至多 `BATCH_SIZE` 条）；表完整性失败时为空。"""

    passed: bool
    reason: str
    rows: Tuple[LedgerRow, ...]


def _split_ledger_row(line: str) -> Tuple[str, ...]:
    """与契约测试 `split_row` 同口径：去掉首尾空管道，逐格 strip。"""
    cells = line.strip().split("|")
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return tuple(c.strip() for c in cells)


def ledger_rows(text: str) -> List[LedgerRow]:
    """读台账**第一张表**的数据行（表头 ＋ 分隔行之后的连续 `|` 块）。纯函数，不读盘。

    与 `append_row` 和契约测试 `first_table` 同一条规则：空行即表尾，其后的 `|` 行不算。
    按 `str.splitlines` 切行——契约解析器就是这么切的，两者必须逐行一致。
    """
    block: List[str] = []
    for line in text.splitlines():
        if line.strip().startswith("|"):
            block.append(line)
        elif block:
            break
    out: List[LedgerRow] = []
    for line in block[2:]:
        cells = _split_ledger_row(line)
        if cells:
            out.append(LedgerRow(cells))
    return out


def _parse_row_ts(value: str) -> Optional[datetime]:
    if not _BATCH_TS_RE.fullmatch(value):
        return None
    try:
        return datetime.strptime(value, BATCH_TS_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def batch_verdict(decl: BatchDeclaration, rows: Sequence[LedgerRow]) -> BatchVerdict:
    """按声明判一批。纯函数，不改入参。

    - 表完整性（Q2）：**每一条**数据行的 `ts_utc` 都必须可解析，不论在不在窗口里。
    - 窗口：第一条 `ts_utc >= 起始 ts` 的行起、按台账顺序的前 `BATCH_SIZE` 条。只往后看——
      起始之前的行不算；第十条之后的行不看。窗口内的外来行不跳过（不许「先按身份过滤再取 10」）。
    - 窗口内逐行：时序倒退到起始之前、不足八列、或 commit / result / suite_hash / browser / os
      与声明不符（result 须为 green），即判败，只报第一处（Q4 列序、Q6 优先于 incomplete）。
    - 无违规且不足 `BATCH_SIZE` 条：`incomplete: N/10`。
    """
    parsed: List[datetime] = []
    for i, row in enumerate(rows, start=1):
        ts = _parse_row_ts(row.ts_utc)
        if ts is None:
            return BatchVerdict(False, f"台账第 {i} 条数据行的 ts_utc 无法解析：{row.ts_utc!r}", ())
        parsed.append(ts)

    first = next((i for i, ts in enumerate(parsed) if ts >= decl.start_ts), len(rows))
    window = tuple(rows[first : first + BATCH_SIZE])
    start_shown = decl.start_ts.strftime(BATCH_TS_FORMAT)
    expected = {
        "commit": decl.commit,
        "result": "green",
        "suite_hash": decl.suite_hash,
        "browser": decl.browser,
        "os": decl.os,
    }
    for pos, (row, ts) in enumerate(zip(window, parsed[first:]), start=1):
        where = f"批次 {decl.batch_id} 第 {pos}/{BATCH_SIZE} 行 {row.ts_utc}"
        if ts < decl.start_ts:
            return BatchVerdict(False, f"{where}：时序倒退，早于起始 {start_shown}", window)
        if len(row.cells) != len(CANONICAL_COLUMNS):
            return BatchVerdict(
                False, f"{where}：应为 {len(CANONICAL_COLUMNS)} 列，实有 {len(row.cells)} 列", window
            )
        for column in _VERDICT_COLUMNS:
            observed = getattr(row, column)
            if observed != expected[column]:
                return BatchVerdict(
                    False, f"{where}：{column} 为 {observed!r}，声明为 {expected[column]!r}", window
                )
    if len(window) < BATCH_SIZE:
        return BatchVerdict(False, f"incomplete: {len(window)}/{BATCH_SIZE}", window)
    return BatchVerdict(
        True, f"{BATCH_SIZE}/{BATCH_SIZE}（{window[0].ts_utc} – {window[-1].ts_utc}）", window
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--append", action="store_true", help="可记账时把行追加进台账（默认只打印）")
    p.add_argument("--ledger", type=Path, default=LEDGER_PATH, help="台账路径（单测用 tmp 副本）")
    p.add_argument("--parse-summary", type=Path, default=None, help="不跑 lane，只解析这份 summary 文本（`-` = stdin）")
    p.add_argument("--no-precheck", action="store_true", help="跳过「整棵工作树干净」的前置检查（只在 --parse-summary 下有意义）")
    p.add_argument("--log-dir", type=Path, default=None, help="log 产物目录（默认 .claude/tdd-guardian/soak-logs/）")
    p.add_argument(
        "--allow-synthetic-append",
        action="store_true",
        help=(
            "仅供单测：允许 --parse-summary 的合成结果落进一个**仓库之外的临时台账**。"
            "对 canonical 台账与仓库内的任何路径一律拒绝"
        ),
    )
    p.add_argument("--verdict", default=None, metavar="BATCH_ID", help="只读：判台账里这一批是否通过，打印一行 PASS / FAIL")
    # 仅供单测：`--append` 闸门查这个仓库而不是 REPO_ROOT。准入见 ancestry_repo_refusal()。
    p.add_argument("--ancestry-repo", type=Path, default=None, help=argparse.SUPPRESS)
    p.add_argument("--expected", type=int, default=EXPECTED_BASELINE_ITEMS, help=argparse.SUPPRESS)
    # 默认值故意是 None 而不是常量：deselected 该是多少，是 LANE_ARGS 这次调用形态的性质。
    # --parse-summary 模式下这份 summary 不是本脚本跑出来的，脚本无从知道对面用了什么 -m，
    # 套用 24 会把一份合法的全量 summary 误判成红。见 main() 里的落地。
    p.add_argument("--expected-deselected", type=int, default=None, help=argparse.SUPPRESS)
    return p


def synthetic_append_refusal(ledger: Path, allowed: bool) -> Optional[str]:
    """`--parse-summary` ＋ `--append` 的准入判定。返回 None ＝ 放行，返回字符串 ＝ 拒绝理由。

    合成 summary 落账的三条硬性拒绝：没开 `--allow-synthetic-append`、台账是 canonical 那一份、
    台账在仓库里。第三条不是洁癖——`--ledger docs/.../soak-log.md.bak` 一样是「仓库里多了一份
    看起来像台账的绿」，而 G2 的读者未必分得清哪一份是真的。
    """
    if not allowed:
        return (
            "`--parse-summary` 与 `--append` 互斥：这份 summary 不是本脚本跑出来的，没有退出码、"
            "没有 collect-only 分母，log 产物还落在临时目录——允许它落账，"
            "`echo \"N passed in 1s\" | soak_run.py --parse-summary - --append` 就能给 canonical "
            "台账添一行带真 commit、真 suite_hash 的绿，而一条用例都没跑过。"
            "单测要验证落账路径请用 --allow-synthetic-append（只接受仓库外的临时台账）。"
        )
    resolved = ledger.resolve()
    if resolved == LEDGER_PATH.resolve():
        return f"--allow-synthetic-append 不接受 canonical 台账：{resolved}"
    if resolved == REPO_ROOT.resolve() or REPO_ROOT.resolve() in resolved.parents:
        return f"--allow-synthetic-append 只接受仓库之外的临时台账，这个在仓库里：{resolved}"
    return None


#: 闸门的 git 调用里要剔掉的环境变量：commit 钩子里跑时外层会漏进它们，git 就会无视 cwd、
#: 去查别的仓库（R1）。审计 20261007 #12（FX37-10）：只剔三个不够——`GIT_OBJECT_DIRECTORY` /
#: `GIT_COMMON_DIR` / `GIT_CONFIG_*` 等同样能把 `rev-parse` / `merge-base` 引到别的对象库或配置。
#: 这里是 `git rev-parse --local-env-vars` 的全集，外加它不列的 `GIT_NAMESPACE` /
#: `GIT_INTERNAL_SUPER_PREFIX`；`GIT_CONFIG_KEY_<n>` / `GIT_CONFIG_VALUE_<n>` 按前缀另剔。
_GATE_DROPPED_GIT_ENV: Tuple[str, ...] = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_CONFIG",
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_PARAMETERS",
    "GIT_DIR",
    "GIT_GRAFT_FILE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_INTERNAL_SUPER_PREFIX",
    "GIT_NAMESPACE",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_OBJECT_DIRECTORY",
    "GIT_PREFIX",
    "GIT_REPLACE_REF_BASE",
    "GIT_SHALLOW_FILE",
    "GIT_WORK_TREE",
)
_GATE_DROPPED_GIT_ENV_PREFIXES: Tuple[str, ...] = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")


def _gate_git(args: Sequence[str], repo: Path, env: Dict[str, str]) -> "subprocess.CompletedProcess[str]":
    """闸门专用的 git 调用：参数列表、无 shell、`cwd=repo`、不 check。超时在**调用期**读
    `GIT_PRECHECK_TIMEOUT_S`（单测会把它调小）。`TimeoutExpired` / `OSError` 交给调用方。"""
    return subprocess.run(  # noqa: S603
        ["git", *args],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        timeout=GIT_PRECHECK_TIMEOUT_S,
    )


def append_gate_refusal(env: Mapping[str, str], repo: Path) -> Optional[Tuple[int, str]]:
    """`--append` 的硬性闸门（018 第二段 WI-8）。返回 None ＝ 放行，否则 (退出码, 拒绝理由)。

    律：落账 ⇒ 不在 CI 里 ∧ HEAD 是 `origin/master` 的祖先。依次判：
    1. `GITHUB_ACTIONS` **存在**于 env（空串也算）→ 2。
    2. `origin/master` 解析不成提交 → 3，提示 `git fetch origin master`。
    3. `git merge-base --is-ancestor HEAD origin/master`：0 放行；1 → 2 并点名 HEAD 短 SHA；
       其余退出码（≥128：unborn HEAD 等）、超时、`OSError`（路径不存在、找不到 git）→ 3。
    任何一条都不抛——闸门失败不能开门，也不能让调用方以 traceback 收场。
    """
    if "GITHUB_ACTIONS" in env:
        return (
            EXIT_UNRECORDABLE,
            "GITHUB_ACTIONS 已设置：CI 里不落 soak 台账——CI 跑的是未合并的合并提交，"
            "且 runner 不是批次声明里的那台机器。",
        )
    git_env = {
        k: v
        for k, v in env.items()
        if k not in _GATE_DROPPED_GIT_ENV and not k.startswith(_GATE_DROPPED_GIT_ENV_PREFIXES)
    }
    timeout = GIT_PRECHECK_TIMEOUT_S
    try:
        resolved = _gate_git(["rev-parse", "--verify", "--quiet", "origin/master^{commit}"], repo, git_env)
    except subprocess.TimeoutExpired:
        return (EXIT_ENVIRONMENT, f"git rev-parse origin/master 超时（>{timeout:g}s，{repo}），无法确认 HEAD 已合入，拒绝落账")
    except OSError as exc:
        return (EXIT_ENVIRONMENT, f"无法在 {repo} 里执行 git：{exc}；无法确认 HEAD 已合入，拒绝落账")
    if resolved.returncode != 0:
        return (
            EXIT_ENVIRONMENT,
            f"{repo} 里解析不出 origin/master（没有 remote 或从没 fetch 过）：先 `git fetch origin master` 再落账",
        )
    try:
        ancestry = _gate_git(["merge-base", "--is-ancestor", "HEAD", "origin/master"], repo, git_env)
    except subprocess.TimeoutExpired:
        return (EXIT_ENVIRONMENT, f"git merge-base 超时（>{timeout:g}s，{repo}），无法确认 HEAD 已合入，拒绝落账")
    except OSError as exc:
        return (EXIT_ENVIRONMENT, f"无法在 {repo} 里执行 git merge-base：{exc}")
    if ancestry.returncode == 0:
        return None
    if ancestry.returncode != 1:
        detail = (ancestry.stderr or "").strip()
        return (
            EXIT_ENVIRONMENT,
            f"git merge-base --is-ancestor HEAD origin/master 失败（退出码 {ancestry.returncode}，{repo}）：{detail}",
        )
    try:
        short = _gate_git(["rev-parse", "--short", "HEAD"], repo, git_env)
        head = short.stdout.strip() if short.returncode == 0 and short.stdout.strip() else "HEAD"
    except (subprocess.TimeoutExpired, OSError) as exc:
        LOGGER.debug("取 HEAD 短 SHA 失败：%r", exc)
        head = "HEAD"
    return (
        EXIT_UNRECORDABLE,
        f"HEAD {head} 不是 origin/master 的祖先：未合并的提交不许写 soak 行——"
        "合入 master 后在 origin/master 上的 detached worktree 里再跑。",
    )


def ancestry_repo_refusal(args: argparse.Namespace) -> Optional[str]:
    """隐藏测试开关 `--ancestry-repo` 的准入：只在 `--parse-summary` ＋ `--append` ＋
    `--allow-synthetic-append` ＋ 仓库外临时台账时生效，其余一律拒绝（给真跑或 canonical
    落账指一个「友好」仓库，等于把闸门绕开）。"""
    honoured = (
        args.parse_summary is not None
        and args.append
        and synthetic_append_refusal(args.ledger, args.allow_synthetic_append) is None
    )
    if honoured:
        return None
    return (
        "--ancestry-repo 只在 --parse-summary ＋ --append ＋ --allow-synthetic-append ＋ 仓库外临时台账时有效"
        "（仅供单测）；其余形态一律拒绝"
    )


def effective_log_dir(args: argparse.Namespace, real_append: bool) -> Path:
    """本次运行的 log 目录，三选一：显式 `--log-dir` 原样返回；真跑 ＋ 落账用 `DEFAULT_LOG_DIR`；
    其余（parse 模式、dry run）一律新建临时目录，免得单测或一次试跑往 `.claude/` 下留文件。

    `main()` 在前置检查**之前**算一次，同一个值既交给 `dirty_worktree` 做豁免、也交给 log 写入——
    两处各算一遍，批次的第 2 次运行就会被第 1 次留下的 log 挡住。相对路径不在这里解析。
    """
    if args.log_dir is not None:
        return Path(args.log_dir)
    if real_append:
        return DEFAULT_LOG_DIR
    return Path(tempfile.mkdtemp(prefix="soak-"))


EXIT_VERDICT_PASS = 0
EXIT_VERDICT_FAIL = 1


def run_verdict(batch_id: str, ledger: Path) -> int:
    """`--verdict` 的全部动作：读台账 → 解析声明 → 判一批 → 打印一行。只读，不碰 git / pytest。"""
    try:
        text = ledger.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"FAIL {batch_id}: 读不了台账 {ledger}：{exc}")
        return EXIT_VERDICT_FAIL
    try:
        decls = parse_batch_declarations(text)
    except BatchDeclarationError as exc:
        print(f"FAIL {batch_id}: 批次声明解析失败（{ledger}）：{exc}")
        return EXIT_VERDICT_FAIL
    decl = decls.get(batch_id)
    if decl is None:
        known = "、".join(decls) or "（无）"
        print(f"FAIL {batch_id}: 台账里没有批次 {batch_id} 的声明（已声明：{known}）")
        return EXIT_VERDICT_FAIL
    v = batch_verdict(decl, ledger_rows(text))
    if v.passed:
        print(f"PASS {batch_id} {v.reason}")
        return EXIT_VERDICT_PASS
    print(f"FAIL {batch_id}: {v.reason}")
    return EXIT_VERDICT_FAIL


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    ledger: Path = args.ledger

    # ---- `--verdict`：只读判决，最先分派——在取哈希、前置检查、pytest、log 目录之前 ----
    if args.verdict is not None:
        conflicts = [flag for flag, on in (("--append", args.append), ("--parse-summary", args.parse_summary is not None)) if on]
        if conflicts:
            print(f"[soak] 拒绝：`--verdict` 是只读判决，不能与 {' / '.join(conflicts)} 同用")
            return EXIT_VERDICT_FAIL
        return run_verdict(args.verdict, ledger)

    # ---- 隐藏测试开关的准入：先于合成拒绝（否则 canonical / 仓库内台账会以 3 而不是 2 收场） ----
    if args.ancestry_repo is not None:
        flag_refusal = ancestry_repo_refusal(args)
        if flag_refusal is not None:
            print(f"[soak] 拒绝：{flag_refusal}")
            return EXIT_UNRECORDABLE

    # ---- 最先做的判定：合成 summary 不许落进 canonical 台账（见 synthetic_append_refusal） ----
    if args.parse_summary is not None and args.append:
        refusal = synthetic_append_refusal(ledger, args.allow_synthetic_append)
        if refusal is not None:
            print(f"[soak] 拒绝：{refusal}")
            return EXIT_ENVIRONMENT

    # ---- `--append` 闸门：CI 里不落账，HEAD 不在 origin/master 上不落账（与 --no-precheck 无关） ----
    if args.append:
        gate_repo = args.ancestry_repo if args.ancestry_repo is not None else REPO_ROOT
        gate = append_gate_refusal(os.environ, gate_repo)
        if gate is not None:
            gate_code, gate_msg = gate
            print(f"[soak] 拒绝落账（退出码 {gate_code}）：{gate_msg}")
            return gate_code

    if not ledger.is_file():
        print(f"台账不存在：{ledger}")
        return EXIT_ENVIRONMENT
    ledger_text = ledger.read_text(encoding="utf-8")
    # `suite_hash` 的取法只在 canonical 台账的表头定义一次。`--ledger` 指向别处（单测的 tmp 副本）
    # 且那份里没有命令块时，命令仍从 canonical 台账读——写到哪里可以换，取法不能有第二份。
    if "git ls-files" not in ledger_text and LEDGER_PATH.is_file():
        hash_source_text = LEDGER_PATH.read_text(encoding="utf-8")
    else:
        hash_source_text = ledger_text

    # ---- 有效 log 目录：先于前置检查算一次，豁免与写入用同一个值（见 effective_log_dir） ----
    real_append = args.append and args.parse_summary is None
    try:
        log_dir = effective_log_dir(args, real_append)
    except OSError as exc:
        print(f"[soak] 无法准备 log 目录：{exc}")
        return EXIT_ENVIRONMENT

    # ---- 前置检查：整棵工作树必须干净（真跑时强制；parse 模式可跳） ----
    if args.parse_summary is None or not args.no_precheck:
        try:
            dirty = dirty_worktree(REPO_ROOT, ledger, log_dir)
        except (RuntimeError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            print(f"无法执行前置检查：{exc}")
            return EXIT_ENVIRONMENT
        if dirty and args.append:
            print(
                "拒绝落账：工作树不干净（台账与本次 log 目录之外有改动或未跟踪文件），"
                "这次运行测的不是 suite_hash 与 commit 所指的那份代码："
            )
            for entry in dirty:
                print(f"  {entry}")
            print(
                "请在干净的 detached worktree 里跑：`git worktree add --detach <dir> HEAD`，"
                "然后在 <dir> 里执行 `python scripts/soak_run.py --append --ledger <主仓库的 soak-log.md 绝对路径>`。"
            )
            return EXIT_UNRECORDABLE
        if dirty:
            print("提示：工作树不干净（dry run，不落账，仅打印；--append 时会被拒绝）：")
            for entry in dirty:
                print(f"  {entry}")

    # ---- 取 summary：真跑 or 解析 ----
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"[soak] 无法准备 log 目录：{exc}")
        return EXIT_ENVIRONMENT
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        commit = _git(["rev-parse", "--short", "HEAD"], REPO_ROOT)
    except subprocess.CalledProcessError:
        commit = "unknown"

    if args.parse_summary is not None:
        try:
            text = (
                sys.stdin.read()
                if str(args.parse_summary) == "-"
                else args.parse_summary.read_text(encoding="utf-8")
            )
        except OSError as exc:
            print(f"[soak] 读不到 --parse-summary 指的文件：{exc}")
            return EXIT_ENVIRONMENT
        collect_line = "(parse-summary 模式：未做 --collect-only)"
        wall = None
        rc: Optional[int] = None
    else:
        collect_line = collect_only_count(REPO_ROOT)
        print(f"[soak] {collect_line}")
        print(f"[soak] 运行：python -m pytest {' '.join(LANE_ARGS)}")
        rc, text, wall = run_pytest(LANE_ARGS, REPO_ROOT)

    try:
        summary = parse_summary(text)
    except SummaryParseError as exc:
        print(f"解析失败：{exc}")
        if rc is not None:
            print(f"[soak] （pytest 退出码 {rc}）")
        return EXIT_ENVIRONMENT
    if args.expected_deselected is not None:
        expected_deselected = args.expected_deselected
    else:
        # 真跑 = 本脚本发的 `-m baseline_1b`，必然筛掉验收目录与白名单；解析别人的 summary 则不设此预期。
        expected_deselected = 0 if args.parse_summary is not None else EXPECTED_NONBASELINE_ITEMS
    v = verdict(summary, args.expected, expected_deselected)
    # 退出码与 summary 不自洽 ⇒ 不可记账的环境错误。判在这里、印在下面：log 产物照写，
    # 因为「summary 是绿的但进程死了」正是最需要留证据的一种失败。
    env_problem = classify_exit_code(rc, summary) if rc is not None else None

    try:
        log_path = build_log_path(log_dir, ts, commit)
        log_path.write_text(
            f"# soak run {ts} @ {commit}\n# collect-only: {collect_line}\n# summary: {summary.line}\n"
            f"# pytest rc: {rc}\n"
            f"# verdict: {v.result} recordable={v.recordable}\n"
            + (f"# env-problem: {env_problem}\n" if env_problem else "")
            + "".join(f"# reason: {r}\n" for r in v.reasons)
            + "\n"
            + text,
            encoding="utf-8",
        )
    except (OSError, LedgerWriteError) as exc:
        print(f"[soak] 写 log 产物失败，本次不落账：{exc}")
        return EXIT_ENVIRONMENT

    if env_problem is not None:
        print(f"[soak] summary: {summary.line}")
        print(f"[soak] 拒绝记账（环境错误，退出码 {EXIT_ENVIRONMENT}）：{env_problem}")
        print(f"[soak] 产物：{log_path}")
        return EXIT_ENVIRONMENT

    try:
        hash_value = suite_hash(hash_source_text, REPO_ROOT)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"取 suite_hash 失败：{exc}")
        return EXIT_ENVIRONMENT

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
        return EXIT_UNRECORDABLE
    if args.append:
        # 写不进去**不是**「这次运行红了」。让 OSError 逃出去会以退出码 1 收场，而 1 在本脚本的
        # 契约里恰好是「red 且已记账」——调用方会把一次没写成的绿当成一次记过账的红。
        try:
            append_row(ledger, row)
        except (OSError, LedgerWriteError) as exc:
            print(f"[soak] 写台账失败，本次未落账（退出码 {EXIT_ENVIRONMENT}，不是一次 red）：{exc}")
            return EXIT_ENVIRONMENT
        print(f"[soak] 已追加到 {ledger}（分隔行正下方，无空行）")
    else:
        print("[soak] dry run：未写台账（加 --append 才写）")
    return EXIT_GREEN if v.result == "green" else EXIT_RED_RECORDABLE


if __name__ == "__main__":
    sys.exit(main())
