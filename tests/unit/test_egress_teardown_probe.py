"""C14 的探针：一条**吞掉**出网异常、并且从不碰记账 list 的用例。

这个文件在普通的 lane 运行里只贡献**一条 skip**。只有把
``READER3_EGRESS_TEARDOWN_PROBE=1`` 设上，它才真的去连一个不可路由的地址，把异常吞掉，
然后什么都不做地返回——于是唯一还能让这一轮变红的东西，是 ``tests/unit/conftest.py``
注册的那道闸在 **teardown** 里的 ``assert egress_violations == []``。

驱动在 ``tests/unit/test_egress_backstop_unit.py::test_the_lane_conftest_itself_reddens_at_teardown``：
它以子进程跑本文件两次（武装 / 未武装），断言武装的那次 rc != 0 且失败+错误数为 1，
未武装的那次 rc == 0 且只有一条 skip。

**不要**给本文件加 ``@pytest.mark.real_loopback_socket``：整条用例的意义就是它**没有**
豁免。也不要在用例体里读或 clear ``egress_violations``——C1-C10 都那么做，而那正是把
teardown 那行断言遮住了整整一个工作项的原因。
"""

from __future__ import annotations

import os
import socket

import pytest

#: 与 tests/unit/test_egress_backstop_unit.py 的 BLOCKED_ADDR 同一个地址（TEST-NET-3，
#: RFC 5737，保证不可路由）。驱动断言它出现在子进程的红里，所以这个字面量是量具的一部分。
BLOCKED_ADDR = "203.0.113.1"

PROBE_ENV = "READER3_EGRESS_TEARDOWN_PROBE"

pytestmark = pytest.mark.skipif(
    os.environ.get(PROBE_ENV) != "1",
    reason=f"C14 探针：只在 {PROBE_ENV}=1 时武装（普通 lane 运行里它就是这一条 skip）",
)


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
