"""WI-3 —— 出网闸里**只有子解释器才够得着**的两条：C11（teardown 真的判红）与 C12
（单独跑 `tests/contract` 仍然能收集）。

**lane 归属改判（2026-09-07，第二次）**：这两条现在**不挂** `slow`，落在 unit lane
（`uv run pytest tests/unit tests/contract`，gate 在 taskCompleted ＋ commit）。

第一次裁决把它们放进 packaging lane（push 门），依据是「两个子解释器 ~1.5-3s，把 commit
门从 ~4s 顶到 ~8s」。**那个 ~4s 是错的**：unit lane 实测 ~44s（1245 条，带 coverage），
这两条实测 1.88s，边际成本 ~4% 而不是翻倍。依据错了，结论跟着改。

改判的第二个理由与成本无关：C12 守的是「单独跑 `tests/contract` 目录仍然能收集」，
C11 守的是共享闸体里那行 teardown 断言——两条都是**测试设施自身**的正确性，与
「装轮子、拿最新依赖装一遍」没有任何关系。把它们寄放在 packaging lane 里，只能靠一句
「别当成过期的打包测试删掉」的注释护住；那是把错配记录下来，不是解决它。

**C11 / C12 / C14 三条互不替代**：C11 证明 `tests/unit/egress_guard.py` 里那行 teardown
断言存在（合成树 import 的就是**同一个文件**，不是抄件）；C14
（`tests/unit/test_egress_backstop_unit.py::test_the_lane_conftest_itself_reddens_at_teardown`）
拿真的两处 conftest 各跑一条子解释器探针，证明注册**真的走到**那一行——它不是
「只看注册的收据」，早先本文件这么写是不准确的；C12 守的是收集路径。三条各守一个失效形态。

**为什么是子解释器而不是 `pytester`**：`pytester` 需要在 rootdir 的 conftest 里写
`pytest_plugins`（`tests/conftest.py` 是冻结路径），另一条路 `-p pytester` 要动 `addopts`——
而 `pyproject.toml:98-109` 明文写着「不要加会撑大这条 lane 的 addopts」，`--strict-markers`
是唯一一条记录在案的例外。于是沿用本仓库已有的子解释器写法
（`tests/unit/test_soak_run.py:288-313`）。
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
UNIT_DIR = REPO_ROOT / "tests" / "unit"

BLOCKED_ADDR = "203.0.113.1"

#: 子进程上限。无超时的 subprocess.run 会把这道 commit 门挂成「测试还在跑」而不是失败。
CLI_TIMEOUT_S = 180.0

_SUMMARY_TOKEN_RE = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|deselected)")


def summary_counts(out: str) -> Dict[str, int]:
    """从 pytest 最后一行摘要里读计数。

    teardown 里的断言失败是 ``ERROR at teardown of …``，摘要写 ``1 passed, 1 error``，
    **不是** ``1 failed``。断 ``"1 failed" in out`` 会因为错误的理由拿到红，而「修法」
    多半是把断言挪进用例体——那样这条用例就没了。所以失败**和**错误都要解析，断它们的和。
    """
    for line in reversed([ln for ln in out.strip().splitlines() if ln.strip()]):
        pairs = _SUMMARY_TOKEN_RE.findall(line)
        if pairs and " in " in line:
            return {
                (kind.rstrip("s") if kind.startswith("error") else kind): int(n)
                for n, kind in pairs
            }
    return {}


def failed_or_errored(out: str) -> int:
    counts = summary_counts(out)
    return counts.get("failed", 0) + counts.get("error", 0)


def collected_count(out: str) -> int:
    m = re.search(r"(\d+)\s+tests?\s+collected", out)
    if m:
        return int(m.group(1))
    return sum(1 for line in out.splitlines() if "::" in line)


def run_child(cmd: List[str], *, cwd: Path, timeout: float = CLI_TIMEOUT_S
              ) -> "subprocess.CompletedProcess[str]":
    """带超时的 ``subprocess.run``（tests/unit/test_soak_run.py:75-86 的写法）。"""
    env = dict(os.environ)
    env.pop("READER3_EGRESS_TEARDOWN_PROBE", None)
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=str(cwd), env=env
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - 只在子进程挂死时走到
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        pytest.fail(f"子进程超过 {timeout:g}s 没退出：{cmd}\n--- stdout ---\n{out}\n--- stderr ---\n{err}")


# --------------------------------------------------------------------------
# C11 —— teardown 那行断言真的能让一轮 pytest 变红。 L4 / S2
# --------------------------------------------------------------------------

_CHILD_PYTEST_INI = "[pytest]\naddopts = -p no:cacheprovider\n"

_CHILD_CONFTEST = '''\
"""合成树的 conftest：装的是 tests/unit/egress_guard.py **那一份**闸体。

如果这里抄一份，C11 证的就是抄件的性质，跟 lane 真正跑的那道闸无关——共享模块
因此是强制的，不是整洁偏好。
"""

import sys

import pytest

sys.path.insert(0, {unit_dir!r})

import egress_guard


@pytest.fixture
def egress_violations(request):
    return egress_guard.egress_violations(request)


@pytest.fixture(autouse=True)
def _no_real_egress(request, egress_violations):
    yield from egress_guard.no_real_egress(request, egress_violations)
'''

_CHILD_DIRTY = '''\
import socket


def test_dirty_swallows_the_connect():
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect(("203.0.113.1", 80))
    except BaseException:
        pass
    finally:
        s.close()
'''

_CHILD_CLEAN = '''\
def test_clean_does_no_networking():
    assert 1 + 1 == 2
'''


def _build_child_tree(tmp_path: Path) -> Path:
    (tmp_path / "pytest.ini").write_text(_CHILD_PYTEST_INI, encoding="utf-8")
    (tmp_path / "conftest.py").write_text(
        _CHILD_CONFTEST.format(unit_dir=str(UNIT_DIR)), encoding="utf-8"
    )
    (tmp_path / "test_dirty.py").write_text(_CHILD_DIRTY, encoding="utf-8")
    (tmp_path / "test_clean.py").write_text(_CHILD_CLEAN, encoding="utf-8")
    return tmp_path


def test_the_teardown_assertion_actually_fails_the_run(tmp_path: Path) -> None:
    """一条**吞掉**闸的异常、从不碰记账 list 的用例，仍然让整轮变红；同一轮里干净的
    兄弟用例保持绿。

    C1-C10 全都在用例体里读完就 ``clear()``，C8 还断它是空的——把
    ``no_real_egress`` 最后那行 ``assert egress_violations == []`` 删掉，它们**一条都不会红**。
    这条是那一行唯一的收据。

    干净的那一半不是凑数：没有它，第一条断言会被一道「每轮都判红」的闸满足。
    """
    tree = _build_child_tree(tmp_path)
    base = [sys.executable, "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider"]

    dirty = run_child(base + ["."], cwd=tree)
    clean = run_child(base + ["test_clean.py"], cwd=tree)

    assert dirty.returncode != 0, (
        "吞掉异常的用例让整轮 pytest 退了 0——teardown 那条断言要么不存在，"
        "要么读的不是 _boom 写的那个 list。C1-C10 全都在用例体里 clear 过，"
        f"把这行删掉它们一条都不会红：\n{dirty.stdout[-2000:]}\n{dirty.stderr[-2000:]}"
    )
    # 017 WI-10（审计 #18）：原来这里是 `failed_or_errored(...) == 1`，把三种结局算成
    # 同一个 1——「用例体自己红了」（1 failed）、「setup 就炸了、体根本没跑」（error at
    # setup）、以及唯一想要的「体通过、teardown 判红」。前两种下最后那行 assert 一次都
    # 没求值，而这条用例存在的全部理由就是求值它。所以阶段与主体都要点名。
    dirty_counts = summary_counts(dirty.stdout)
    assert dirty_counts.get("failed", 0) == 0, (
        f"脏那轮有 failed（摘要={dirty_counts}）：用例体自己红了，teardown 那行没轮到求值。"
        f"这条要的是「体通过、收尾判红」：\n{dirty.stdout[-2000:]}"
    )
    assert dirty_counts.get("passed") == 2, (
        f"脏那轮 passed={dirty_counts.get('passed')}，期望 2（脏的那条自己是通过的，红在 "
        f"teardown；干净的那条本来就通过）：\n{dirty.stdout[-2000:]}"
    )
    assert dirty_counts.get("error") == 1, (
        f"脏那轮 error 数不是 1（摘要={dirty_counts}）。注意 teardown 断言在 pytest "
        f"眼里是 error 不是 failed：\n{dirty.stdout[-2000:]}"
    )
    assert "ERROR at teardown of test_dirty_swallows_the_connect" in dirty.stdout, (
        f"红的不是**那条脏用例的 teardown**。阶段错了这条就没有意义：setup 阶段的 error "
        f"同样计入 1 个 error，而那时用例体一行都没执行：\n{dirty.stdout[-2000:]}"
    )
    assert "ERROR at setup of" not in dirty.stdout, (
        f"出现了 setup 阶段的 error——闸是在装的时候炸的，不是在结账的时候："
        f"\n{dirty.stdout[-2000:]}"
    )
    assert BLOCKED_ADDR in dirty.stdout, (
        f"红了，但失败信息里没有地址，定位不到是谁在出网：\n{dirty.stdout[-2000:]}"
    )
    assert clean.returncode == 0 and summary_counts(clean.stdout).get("passed") == 1, (
        f"干净的用例也被 teardown 判红：\n{clean.stdout[-2000:]}\n{clean.stderr[-2000:]}"
    )
    assert "ERROR at" not in clean.stdout, (
        f"干净那轮出现了 error：一道没有出网也判红的闸，会让脏那轮的红不可归因："
        f"\n{clean.stdout[-2000:]}"
    )


# --------------------------------------------------------------------------
# C12 —— 单独跑 `pytest tests/contract` 仍然收集得起来。 L2 / S1
# --------------------------------------------------------------------------


def test_the_contract_directory_still_collects_on_its_own() -> None:
    """`tests/contract/conftest.py` 从 `tests/unit/egress_guard.py` import 闸体。

    `tests/unit/` 只有在 `tests/unit` 也被收集时才会进 sys.path——lane 命令两个目录一起跑，
    所以这个洞在别的任何一条用例眼里都不存在。单独跑 contract 目录是**记录在案的开发者
    调用方式**，它一旦 `ModuleNotFoundError: egress_guard` 就是整目录报废。
    """
    proc = run_child(
        [
            sys.executable, "-m", "pytest", "tests/contract",
            "--collect-only", "-q", "-p", "no:cacheprovider",
        ],
        cwd=REPO_ROOT,
    )

    assert proc.returncode == 0, (
        "单独跑 tests/contract 时收集失败——tests/unit/ 只有在 tests/unit 被收集时才会进 sys.path，"
        f"contract 的 conftest 必须自己显式插一条路径：\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
    )
    assert collected_count(proc.stdout) >= 1, (
        f"收集到 0 条——退出码 0 在这里不等于健康：\n{proc.stdout[-2000:]}"
    )
    assert "ModuleNotFoundError" not in proc.stderr and "egress_guard" not in proc.stderr, (
        f"收集期报了 egress_guard 相关的问题：\n{proc.stderr[-2000:]}"
    )
