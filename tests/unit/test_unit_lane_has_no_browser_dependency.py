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
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

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


def test_group_guard_positive_selection_is_green_without_a_browser(tmp_path: Path) -> None:
    """把 `PLAYWRIGHT_BROWSERS_PATH` 指到不存在的路径，被守护的那条用例仍须绿。

    这是欠账 #45 的验收判据：**没有浏览器的机器上，unit lane 不红。**

    两个方向都断，缺一不可：

    1. `returncode == 0`——它在无浏览器环境下真的通过。
    2. 输出里**不得**出现 `BrowserType.launch`——防「它绿是因为被 skip 掉或绕过去了」
       而不是「它真的不需要浏览器」。只断退出码时，把被守护的用例整条 skip 掉也能变绿，
       而那恰恰是本条要拦的偷工。
    """
    browsers_path = tmp_path / "no-browsers"
    assert not browsers_path.exists(), (
        f"{browsers_path} 竟然存在——本条要的是一个**确实不存在**的浏览器路径"
    )

    env = dict(os.environ)
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            GUARDED_NODEID,
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_S,
    )
    out = proc.stdout + proc.stderr

    assert proc.returncode == 0, (
        f"`PLAYWRIGHT_BROWSERS_PATH={browsers_path}` 下 {GUARDED_NODEID} 退出码 "
        f"{proc.returncode}——unit lane 依赖浏览器了（欠账 #45）。子进程完整输出：\n{out}"
    )
    assert BROWSER_LAUNCH_MARKER not in out, (
        f"子进程输出里出现了 {BROWSER_LAUNCH_MARKER!r}——被守护的用例仍在拉浏览器，"
        f"它的绿不是「不需要浏览器」。子进程完整输出：\n{out}"
    )
