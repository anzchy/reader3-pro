"""C14 在 contract 半边的探针 —— 与 tests/unit/test_egress_teardown_probe.py 同形。

两份而不是一份，因为两处 conftest 的注册**方式不一样**：`tests/unit/conftest.py` 直接
挂 `egress_guard.no_real_egress`，而 `tests/contract/conftest.py` 走的是
``yield from egress_guard.no_real_egress(request, egress_violations)``。那个 ``yield from``
是承重的：写成 ``next(gen); yield`` 也一样能跑完 setup、一样让 C1-C10 全绿，但生成器
再也不会被 resume，于是 teardown 里那行 ``assert egress_violations == []`` 一辈子不执行——
contract 这半边每一次被吞掉的出网都会静悄悄地通过。一行编辑，没有可见的论据，
关掉半条 lane 的记账。只有从这边也放一条探针，那一行才有收据。

约束与 unit 那份完全相同：**不要**加 ``@pytest.mark.real_loopback_socket``，也**不要**在
用例体里读或 clear ``egress_violations``——那正是要留给 teardown 的唯一一条路。
"""

from __future__ import annotations

import os
import socket

import pytest

#: 与 tests/unit/test_egress_backstop_unit.py 的 BLOCKED_ADDR 同一个地址（TEST-NET-3，
#: RFC 5737，保证不可路由）。驱动断言它出现在子进程的红里，所以这个字面量是量具的一部分。
BLOCKED_ADDR = "203.0.113.1"

PROBE_ENV = "READER3_EGRESS_TEARDOWN_PROBE"

#: 只在武装时跳过的那一条。**不是 ``pytestmark``**：整模块 skip 会把 autouse 围栏
#: 一起跳掉，于是 C14 的「未武装」对照根本没让围栏跑过——一道「每轮都在 teardown 判红」
#: 的坏闸在那个对照里照样 rc=0（模块都 skip 了），C14 于是保持全绿（审计 #18）。
_ARMED_ONLY = pytest.mark.skipif(
    os.environ.get(PROBE_ENV) != "1",
    reason=f"C14 探针：只在 {PROBE_ENV}=1 时武装（普通 lane 运行里它就是这一条 skip）",
)


@_ARMED_ONLY
def test_the_probe_swallows_its_own_egress_and_leaves_no_trace_in_the_body() -> None:
    """连出去、吞掉、返回。用例体里不留任何证据——只剩 teardown 那一条路。"""
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect((BLOCKED_ADDR, 80))
    except BaseException:  # noqa: BLE001 - 故意吞掉：这就是被建模的场景
        pass
    finally:
        s.close()


def test_the_fence_really_runs_here_and_stays_green_without_egress() -> None:
    """**永远跑**的一条：不出网，围栏照样 setup + teardown 走一遍，且必须保持绿。

    017 WI-10（审计 #18）：C14 的「未武装」对照原来只证明了「这个模块被 skip 了」。
    skip 掉的模块连 autouse 围栏都不会装，于是那个对照对「围栏坏没坏」完全瞎——
    一道每轮都在 teardown 判红的闸，在那个对照里也是 rc=0。对照要成立，必须有一条
    **真的把围栏跑完**的用例，而且它不出网，所以它必须绿。

    顺带断一件 setup 阶段的事实：围栏确实**装在了本模块上**。本文件没有
    ``real_loopback_socket`` 豁免（那是 C14 武装那一半的前提），所以
    ``socket.socket.connect`` 此刻应当是闸体里那个 ``_boom``，不是 stdlib 那个。
    这里只看名字、不去真连——真连会记一笔账，把本条自己的 teardown 也判红。
    """
    installed = getattr(socket.socket.connect, "__qualname__", "")
    assert installed.endswith("no_real_egress.<locals>._boom"), (
        f"socket.socket.connect 现在是 {installed!r}，不是闸体里那个 _boom。"
        "围栏没装在本模块上——那么 C14 武装那一半测到的红就与这两处 conftest 的注册无关，"
        "而「注册真的走到了 teardown」正是 C14 唯一要证的事"
    )
