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

**取值前要求工作树对覆盖路径干净**（`git status --porcelain -- <paths>` 为空），否则拒绝落账
——`git ls-files -s` 读的是索引，改了没 add 的断言不会体现在哈希里，那正是清零规则要堵的假绿
路径（台账表头「取哈希前必须先确认工作树干净」一节）。

**pytest 的退出码是判据的一部分**（`classify_exit_code()`）。只看 summary 文本会把「打印完
`65 passed` 之后 plugin/atexit 炸了」记成绿：那一行是真的，那次运行不是。规则——`rc == 0` 才
可能绿；`rc == 1` 只在 summary 自洽地报了 failed/errors 时接受（那是该清零的真红）；其余任何
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

退出码：0 = green；1 = red 且已（或可）记账；2 = 不可记账（拒绝）；3 = 环境/解析错误
（含：台账/log 写入失败、pytest 退出码与 summary 不自洽、套件超时、`--parse-summary --append`）。
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
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

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
    # 真失败且其余全为 0、条数对得上 ⇒ 是一次应当清零计数的 red，必须进台账。
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


def dirty_covered_paths(ledger_text: str, cwd: Path) -> List[str]:
    """覆盖路径里有未 add 的改动 ⇒ 哈希记的是索引里的旧内容，不是刚跑过的那份。"""
    paths = hash_covered_paths(ledger_text)
    out = _git(["status", "--porcelain", "--", *paths], cwd)
    return [ln for ln in out.splitlines() if ln.strip()]


def browser_label() -> str:
    """`chromium-<build>`：从 playwright 的 browsers.json 读构建号，不起浏览器。

    两级退化（构建号 → 包版本 → `chromium-unknown`）都**只捕获具体异常并留下 debug 痕迹**
    （AGENTS.md 异常三档的第 3 档：失败无所谓要说得出为什么，且至少 log 到 debug）。
    为什么无所谓：`browser` 这一列的用途是「换了浏览器就清零」，取不到精确构建号会让清零
    变迟钝，但**不会**让一次运行被误判成绿；反过来，为一列标签取不到就中断落账，会把一次
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
    该清零计数的 red，而丢失在台账上无痕（第三行永远是第三行）。
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
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--append", action="store_true", help="可记账时把行追加进台账（默认只打印）")
    p.add_argument("--ledger", type=Path, default=LEDGER_PATH, help="台账路径（单测用 tmp 副本）")
    p.add_argument("--parse-summary", type=Path, default=None, help="不跑 lane，只解析这份 summary 文本（`-` = stdin）")
    p.add_argument("--no-precheck", action="store_true", help="跳过「覆盖路径工作树干净」的前置检查（只在 --parse-summary 下有意义）")
    p.add_argument("--log-dir", type=Path, default=None, help="log 产物目录（默认 .claude/tdd-guardian/soak-logs/）")
    p.add_argument(
        "--allow-synthetic-append",
        action="store_true",
        help=(
            "仅供单测：允许 --parse-summary 的合成结果落进一个**仓库之外的临时台账**。"
            "对 canonical 台账与仓库内的任何路径一律拒绝"
        ),
    )
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    ledger: Path = args.ledger

    # ---- 最先做的判定：合成 summary 不许落进 canonical 台账（见 synthetic_append_refusal） ----
    if args.parse_summary is not None and args.append:
        refusal = synthetic_append_refusal(ledger, args.allow_synthetic_append)
        if refusal is not None:
            print(f"[soak] 拒绝：{refusal}")
            return EXIT_ENVIRONMENT

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

    # ---- 前置检查：覆盖路径的工作树必须干净（真跑时强制；parse 模式可跳） ----
    if args.parse_summary is None or not args.no_precheck:
        try:
            dirty = dirty_covered_paths(hash_source_text, REPO_ROOT)
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            print(f"无法执行前置检查：{exc}")
            return EXIT_ENVIRONMENT
        if dirty and args.append:
            print("拒绝落账：suite_hash 覆盖路径里有未进索引的改动，哈希记的会是旧内容——先 git add：")
            for ln in dirty:
                print(f"  {ln}")
            return EXIT_UNRECORDABLE
        if dirty:
            print("提示：覆盖路径里有未进索引的改动（本次不落账，仅打印）：")
            for ln in dirty:
                print(f"  {ln}")

    # ---- 取 summary：真跑 or 解析 ----
    # 只有「真跑 ＋ 落账」才把产物写进仓库内的默认目录；parse 模式与 dry run 一律进临时目录，
    # 免得单测或一次试跑往 .claude/ 下留文件。
    real_append = args.append and args.parse_summary is None
    try:
        log_dir: Path = args.log_dir or (DEFAULT_LOG_DIR if real_append else Path(tempfile.mkdtemp(prefix="soak-")))
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
