"""Lane 级不变式：unit lane 不得依赖浏览器（009 台账欠账 #45）。

本文件与 `test_e2e_group_guard.py` 的关切**不同**，所以独立成文件：那份文件守的是
`scripts/lint_e2e_groups.py` 这个被测脚本的性质（三分划分律、skip 轴、条数），本文件守的是
**「unit lane 自己能在没有浏览器的机器上跑绿」**——一条关于 lane 的性质，与任何被测脚本无关。

**为什么它需要一条用例，而不是一句约定。** `tests/unit/test_e2e_group_guard.py` 的
`test_positive_selection_of_acceptance_groups_yields_exactly_the_skipped_count` 原本安全：
它 shell out 正选四个 acceptance 组，而四个组当时**全是整组 skip**，子进程收集完就结束。
011 WI-5b（commit `cc6bb18`）激活 `acceptance_2a` 之后这个前提没了——那一组的 DEG-S5 用例
真的去 launch Chromium。没装浏览器的机器上必红，确定性，不是 flaky。
GitHub Actions run 35499892289 / 35500630451 两次都红在这一条。

**本仓 lane 级的同款守卫是 `.github/workflows/tests.yml` 的 `unit` job：它不装 Chromium，
所以那一层永久盯着这件事。** 本条是它的本地快版——让信号在 commit 时就到，而不是等到
发版手点 CI 才知道。两者不重复：CI 那层是终局判定，本条是把终局判定的反馈延迟从「一次
push 往返」压到「一次 unit lane」。

**子进程纪律**：`.claude/tdd-guardian/config.json` 的 unit lane description 明文允许
bounded child interpreters，无界的不允许。本文件的子进程一律带显式墙钟上限
（`SUBPROCESS_TIMEOUT_S`，口径同 `test_e2e_group_guard.py:103`）。

**017 WI-13（审计 #29）：`rc == 0` 加「没出现 `BrowserType.launch`」证明不了那条用例跑过。**
这两条原本自称能拦下「它绿是因为被 skip 掉了」，但一条整体 skip 的子进程恰好同时满足二者：
退出码 0，输出里自然也没有浏览器的影子。2026-09-23 用一个真 skip 的子进程实测，旧断言照样
全绿。现在改成读摘要计数，要求**恰好 1 passed，且 skipped / xfailed / xpassed / failed /
error 全为 0**——「跑过且通过」是个正面事实，只能正面观测，不能从两个否定里推出来。
`_lane_problems()` 把这套判据单独拿出来，好让一条真的 skip / xfail 子进程当负对照去打它：
没有那条负对照，这套判据是不是真的会红，本文件同样无从分辨。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 被守护的那条用例。写全 nodeid 而不是整文件：本条关心的是「那一条不需要浏览器」，
#: 把整文件拖进来只会让墙钟变长而不增加信号。
GUARDED_NODEID = (
    "tests/unit/test_e2e_group_guard.py"
    "::test_positive_selection_of_acceptance_groups_yields_exactly_the_skipped_count"
)

#: 子进程墙钟上限（秒）。口径同 `test_e2e_group_guard.py` 的 `SUBPROCESS_TIMEOUT_S`：
#: 这里是**嵌套**子进程（本条 → 被守护用例 → `tests/e2e` 的 `--setup-plan`），所以比
#: 那边的 300s 宽一档，但仍须远低于 unit lane 的 600s 上限，好让超时以红而不是挂呈现。
SUBPROCESS_TIMEOUT_S = 420

#: 浏览器真的被拉起时，Playwright 的失败信息里必然出现这个串。
BROWSER_LAUNCH_MARKER = "BrowserType.launch"

_SUMMARY_TOKEN_RE = re.compile(
    r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|deselected)"
)


def _summary_counts(out: str) -> Dict[str, int]:
    """从 pytest 最后一行摘要里读计数；读不到返回空 dict（调用方据此判红）。"""
    for line in reversed([ln for ln in out.strip().splitlines() if ln.strip()]):
        pairs = _SUMMARY_TOKEN_RE.findall(line)
        if pairs and " in " in line:
            return {
                (kind.rstrip("s") if kind.startswith("error") else kind): int(n)
                for n, kind in pairs
            }
    return {}


def _lane_problems(returncode: int, out: str) -> List[str]:
    """判据本体：一次子进程的结果算不算「那条用例真的跑了，而且在无浏览器下通过」。

    单拎出来是为了让它**可被打**——下面的负对照拿一条真 skip / 真 xfail 的子进程输出喂给
    它，要求它必须红。判据留在用例体里的话，唯一能证明它有效的办法就是去破坏被守护的那条
    真用例，而那既不可逆也说不清红的原因。

    返回问题列表而不是直接断言：负对照要读它的内容，确认红是这一条判据给的。
    """
    problems: List[str] = []
    if returncode != 0:
        problems.append(f"退出码 {returncode}，期望 0")
    if BROWSER_LAUNCH_MARKER in out:
        problems.append(f"输出里出现了 {BROWSER_LAUNCH_MARKER!r}——那条用例仍在拉浏览器")
    counts = _summary_counts(out)
    if not counts:
        problems.append("读不到 pytest 摘要行——无从判断那条用例到底跑没跑")
        return problems
    # 正面事实：恰好一条、而且是 passed。
    if counts.get("passed", 0) != 1:
        problems.append(f"passed={counts.get('passed', 0)}，期望恰好 1（摘要：{counts}）")
    # 每一种「没真跑」的结局单独点名，好让失败信息直接说出是哪一种。
    for kind in ("skipped", "xfailed", "xpassed", "failed", "error", "deselected"):
        n = counts.get(kind, 0)
        if n:
            problems.append(
                f"{kind}={n}，期望 0——它没有以「跑过且通过」的方式结束（摘要：{counts}）"
            )
    return problems


def _run_pytest(args: List[str], env: Dict[str, str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *args, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_S,
    )


def test_group_guard_positive_selection_is_green_without_a_browser(tmp_path: Path) -> None:
    """把 `PLAYWRIGHT_BROWSERS_PATH` 指到不存在的路径，被守护的那条用例仍须绿。

    这是欠账 #45 的验收判据：**没有浏览器的机器上，unit lane 不红。**

    判据见 `_lane_problems()`：退出码 0、输出里没有 `BrowserType.launch`、**而且**摘要恰好
    是 1 passed（skipped / xfailed / xpassed / failed / error / deselected 全为 0）。

    第三条是 017 WI-13 补的（审计 #29）。原本只有前两条，理由写着「防它绿是因为被 skip
    掉」——可一条整体 skip 的子进程退出码就是 0，输出里也不会有浏览器的影子，两条断言一条
    都拦不住。「那条用例真的跑了并且通过了」是个正面事实，得正面去看摘要，不能从两个否定
    里推。
    """
    browsers_path = tmp_path / "no-browsers"
    assert not browsers_path.exists(), (
        f"{browsers_path} 竟然存在——本条要的是一个**确实不存在**的浏览器路径"
    )

    env = dict(os.environ)
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)

    proc = _run_pytest([GUARDED_NODEID], env, REPO_ROOT)
    out = proc.stdout + proc.stderr

    problems = _lane_problems(proc.returncode, out)
    assert not problems, (
        f"`PLAYWRIGHT_BROWSERS_PATH={browsers_path}` 下 {GUARDED_NODEID} 没有以「跑过且通过」"
        f"结束（欠账 #45）：\n- " + "\n- ".join(problems) + f"\n子进程完整输出：\n{out}"
    )


# ---------------------------------------------------------------------------
# 017 WI-13（审计 #29）：负对照——判据自己得会红
# ---------------------------------------------------------------------------

_PASS = "def test_a():\n    assert True\n"
_SKIP = "def test_b():\n    pytest.skip('对照：这条不跑')\n"
_XFAIL = "def test_c():\n    pytest.xfail('对照：这条记为 xfail')\n"

#: （用例名，对照文件的完整正文，期望在问题里出现的字样；`None` 表示期望判绿）。
#:
#: 前四条**每一条都满足旧的两条断言**——退出码 0、输出里没有 `BrowserType.launch`——所以
#: 它们逐条都是审计 #29 的复现，而不是「随便一个红」。最后一条是阳性对照：没有它，
#: 「一律报红」也能让前四条变绿。
#:
#: 「一条都没收集到」刻意不在这里：pytest 对空收集给 rc=5，它压根满足不了旧断言的前提，
#: 放进来只会让这一族的主张从「#29 复现」稀释成「某些坏结果会红」。那条分支另由
#: `test_the_verdict_refuses_output_it_cannot_parse` 单独盯着。
_CONTROLS = (
    ("整条 skip", _SKIP, "skipped=1"),
    ("标记 xfail 后失败", _XFAIL, "xfailed=1"),
    # 只有「逐种结局单独点名」那段判据拦得住这一条：passed 确实是 1，跳掉的是另一条。
    ("跑了一条、跳了一条", _PASS + _SKIP, "skipped=1"),
    # 只有「恰好 1」那段判据拦得住这一条：没有任何一种坏结局，就是多跑了一条。
    ("跑了两条都通过", _PASS + "def test_d():\n    assert True\n", "passed=2"),
    ("真的跑了一条并通过", _PASS, None),
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [pytest.param(src, exp, id=name) for name, src, exp in _CONTROLS],
)
def test_the_lane_verdict_rejects_a_subprocess_that_never_really_ran(
    tmp_path: Path, source: str, expected: object
) -> None:
    """拿**真的**子进程输出打 `_lane_problems()`，不是拿手搓的字符串。

    手搓 `"1 skipped in 0.01s"` 只能证明解析器认得我写的那行字；真跑一遍 pytest 才能证明它
    认得 pytest **这个版本**实际吐出来的那行。审计 #29 说的就是这个差别——旧断言不是写错了，
    是它断的两件事都不是「跑过」这个事实本身。
    """
    (tmp_path / "test_control.py").write_text("import pytest\n\n\n" + source, encoding="utf-8")

    proc = _run_pytest(["test_control.py"], dict(os.environ), tmp_path)
    out = proc.stdout + proc.stderr
    problems = _lane_problems(proc.returncode, out)

    if expected is None:
        assert not problems, (
            "阳性对照被判红了——判据在拒绝一条真的跑过并通过的子进程，"
            f"那么上面那条守卫的绿就不作数：\n- " + "\n- ".join(problems) + f"\n输出：\n{out}"
        )
        return

    assert proc.returncode == 0 and BROWSER_LAUNCH_MARKER not in out, (
        "这条对照没能复现审计 #29 的前提：它必须同时满足旧的两条断言（退出码 0、无浏览器"
        f"痕迹），否则拦下它的可能是别的理由。退出码 {proc.returncode}，输出：\n{out}"
    )
    assert problems, (
        f"判据放过了一条并没有真跑（或跑了不止那一条）的子进程——这正是审计 #29 命中的那个"
        f"洞。输出：\n{out}"
    )
    assert any(str(expected) in problem for problem in problems), (
        f"红了，但理由里没有 {expected!r}，说明拦下它的是别的判据：\n- " + "\n- ".join(problems)
    )


def test_the_verdict_refuses_output_it_cannot_parse() -> None:
    """摘要行读不出来时判红，不判绿。

    这一条只能用手搓的输入：要的正是「pytest 没吐出可解析摘要」这个本地 pytest 不会产生的
    状况（升级换了摘要格式、输出被别的插件吃掉、子进程在写摘要前就被杀）。fail-closed 的
    方向在这里是唯一安全的一侧——解析不出来就当没跑过，而不是当跑过了。
    """
    problems = _lane_problems(0, "some plugin ate the summary line\n")
    assert any("读不到 pytest 摘要行" in problem for problem in problems), (
        f"无法解析的输出被判绿了：{problems}"
    )
