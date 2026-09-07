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
