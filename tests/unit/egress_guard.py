"""WI-3 —— 全 lane 出网闸的**闸体**（唯一来源）。

这个模块不是测试文件，是被 `tests/unit/conftest.py`、`tests/contract/conftest.py`
以及 `tests/unit/test_egress_backstop_subprocess.py`（C11 的合成用例树）**共同 import**
的一份代码。放在这里而不是抄进两处 conftest，是因为 C11 必须在子解释器里装上
**lane 真正跑的那道闸**；装抄件的话，C11 证的是抄件的性质。

三个不可动摇的决定（每一条都有一条红绿用例钉着，见
`tests/unit/test_egress_backstop_unit.py` 的自检表）：

1. patch ``socket.socket.connect``，**不是** ``socket.create_connection``。
   ``http.client.HTTPConnection`` 在 import 期就把后者抓成了类属性
   （`tests/unit/test_server_egress_gate.py:85` 记过这一笔）；而
   ``create_connection`` 内部走 ``sock.connect(sa)``，所以被传递地覆盖到。
2. ``_boom`` 抛 **AssertionError**，不是 OSError 的子类。
   ``tests/fixtures/deg_assertions.py:357`` 的重试循环 catch
   ``(URLError, ConnectionError, OSError)``——一个 OSError 子类会被整个吞掉然后空转到
   超时。那个文件在 8 条冻结 suite_hash 路径里，改不了；豁免标记是那里唯一的杠杆。
3. **先记账，再抛**。异常在 anyio 的 ``BlockingPortal`` 线程、``run_in_threadpool``
   的 worker、``ThreadingHTTPServer`` 的 handler 里会被吞掉；生产代码自己的
   ``except Exception`` 也会（`src/reader3_app/web/server.py` 的 full_book 回退分支）。
   那些路径上，记录是**仅剩**的证据。teardown 里对这份记录的断言因此不是冗余——
   它是唯一还能让那一轮变红的东西（C11 / C14 是它的收据）。

**这道闸够不着的地方**（记在案，不是遗漏；C10 把其中一条钉成了红绿事实）：

* import / 收集期的出网——闸是 function-scoped fixture，那时还没装上；
* 更高作用域（session / module）fixture 的 setup 里的出网——同上；
* ``subprocess`` 起出去的子解释器——patch 只作用于本进程；
* ``socket.socket.connect_ex``、UDP 的 ``sendto``、``socket.getaddrinfo``——
  它们是各自独立的方法，不经过 ``connect``。

豁免：给用例标 ``@pytest.mark.real_loopback_socket``（marker 注册在
`pyproject.toml` 的 ``[tool.pytest.ini_options] markers``）。豁免是**彻底**的——
闸压根不装，``socket.socket.connect`` 保持 stdlib 原样。豁免名单本身被
`tests/unit/test_egress_backstop_unit.py` 的 ``EXPECTED_EXEMPTIONS`` 锁住：
每加一条都必须是对那张表的一次刻意编辑。
"""

from __future__ import annotations

import socket
import threading
import traceback
from typing import Iterator, List, Tuple

import pytest

#: stdlib 的 ``connect``，在**本模块 import 期**抓下来。conftest 是在收集期 import 的，
#: 那时还没有任何用例跑过，所以这里拿到的一定是没被包过的那一个。豁免路径靠
#: ``socket.socket.connect is _ORIG_CONNECT`` 被验证（C5），所以这个名字是量具的一部分。
_ORIG_CONNECT = socket.socket.connect

MARKER_NAME = "real_loopback_socket"

#: 记账 list 挂在 ``request.node.stash`` 上，而不是模块级全局：并行/重跑时每个 node
#: 各记各的，teardown 断的也就是这条用例自己的账。
_EGRESS_KEY = pytest.StashKey[list]()

#: 一条记录是 ``(线程名, repr(地址), 栈)``。
Violation = Tuple[str, str, str]


def egress_violations(request: pytest.FixtureRequest) -> List[Violation]:
    """本条用例的出网记账 list（同一个 node 上取到的永远是同一个 list 对象）。"""
    return request.node.stash.setdefault(_EGRESS_KEY, [])


def format_violations(violations: List[Violation]) -> str:
    """teardown 报红时印的东西：地址 + 线程 + 出网点的栈。

    地址必须在里面——「一条记录、非主线程」这个形状同时也是「桩失效、去拨了真的
    api.anthropic.com」的形状，没有地址就分不出是哪一个。
    """
    lines = [
        f"lane 出网闸记到 {len(violations)} 次真实 TCP 连接尝试。"
        "被吞掉的异常不会让用例变红，这份记录是仅剩的证据："
    ]
    for i, (thread_name, address, stack) in enumerate(violations, 1):
        lines.append(f"  [{i}] 地址={address} 线程={thread_name}")
        lines.append("      --- 出网点 ---")
        lines.extend(f"      {ln}" for ln in stack.rstrip().splitlines()[-12:])
    return "\n".join(lines)


def no_real_egress(
    request: pytest.FixtureRequest, egress_violations: List[Violation]
) -> Iterator[None]:
    """闸本身。两处 conftest 各用 ``yield from`` 委托给它。

    **必须用 ``yield from``**：``next(gen); yield`` 那种写法永远不会 resume 生成器，
    于是最后那句 teardown 断言一次都不会求值，而 C1-C10 全都在用例体里 ``clear()``
    过——在它们眼里两种写法一模一样。C14 就是这一行的收据。
    """
    if request.node.get_closest_marker(MARKER_NAME):
        # 豁免是彻底的：什么都不装。C5 断 ``socket.socket.connect is _ORIG_CONNECT``，
        # 所以「装一个宽松包装」这种实现在那里会红。
        yield
        return

    def _boom(self, address, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        egress_violations.append(
            (
                threading.current_thread().name,
                repr(address),
                "".join(traceback.format_stack()),
            )
        )
        raise AssertionError(
            f"unit lane 里试图打开真实 TCP 连接：{address!r}。"
            "要么某个桩失效了，要么这条用例真的需要回环——后者请标 "
            f"@pytest.mark.{MARKER_NAME} 并同步 "
            "tests/unit/test_egress_backstop_unit.py 的 EXPECTED_EXEMPTIONS"
        )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(socket.socket, "connect", _boom)
        yield

    # 用例体里被吞掉的出网到这里才结账。**不要**把这句挪进用例体：那样每一条
    # 「吞掉异常」的路径都会静悄悄地绿。
    assert egress_violations == [], format_violations(egress_violations)
