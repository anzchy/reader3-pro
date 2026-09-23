"""017 收尾 —— **「还剩多久」与「还有没有人要这个结果」是队列自己的事实，不是路由的。**

017 WI-2（审计 #2）给 `_call_provider` 接上了 `deadline` / `should_stop`，但把这两个
值的**来源**放在了路由里：每个路由自己 `threading.Event()` ＋
`time.monotonic() + timeout_s`，再用一个包住 `ai_queue.run(...)` 的 `finally` 去翻那面
旗。两个毛病，第二个才是这份文件存在的理由：

1. **同一个事实抄了四份。** 非流式那两条路由各算一份近似的 deadline（注释自己写着
   「只差一次进队的毫秒级开销」），而 `run()` 手上有精确的那一份——它就是用这一份判
   504 的。同一个数两处独立计算，迟早有一处忘了跟着改。

2. **旗翻得太晚。** 路由的 `finally` 在 `run()` **返回之后**才执行；而 `run()` 自己的
   `finally` 里已经先做完了 `q.exit(item)` —— 那一步的含义是「这本书可以开始下一个
   请求了」。于是有一个窗口：下一个请求已经获准开跑，上一个请求的 provider 线程却还
   没收到叫停，两个「本该串行」的调用同时打同一个 provider。这正是 WI-2 想消灭的那
   件事，只是换了个更小的窗口。

所以把两样都交给 `run()`：它把一个 `QueueBudget` 交给 `fn`，并在**任何**出口上先翻旗
再放行下一个请求。下面 B2/B3 钉的就是这个**偏序**（旗先翻、队列后放），用的是「队列
放行的那一刻旗是什么状态」这个可观测量，不是挂钟——挂钟在 CI 上不可靠，而这里要钉的
本来就是偏序不是时长。

本仓没有 pytest-timeout：每个用例整体套在 `asyncio.wait_for(..., HARD_BOUND_S)` 里，
「实现挂住」于是表现为 `asyncio.TimeoutError`，和断言红（`AssertionError`）一眼可分。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, List, Optional, Tuple

import pytest

from reader3_app.ai.queue import AIRequestQueueManager, QueueBudget


#: 每个用例的总上界。实现挂住时给出 TimeoutError 而不是让 lane 卡死。
HARD_BOUND_S = 10.0

#: 用例里那条「短到能等完」的预算。`run()` 的轮询步长是 0.25s，
#: 取 0.4s 能让它至少走一整圈，又不至于让 lane 变慢。
SHORT_TIMEOUT_S = 0.4


class _DisconnectingRequest:
    """一个「第 N 次问就说断了」的假 Request。

    `run()` 每圈都 `await request.is_disconnected()`；真 `Request` 要一整套 scope，
    而这里唯一被用到的就是这个方法。
    """

    def __init__(self, *, disconnect_after: int) -> None:
        self._asked = 0
        self._after = disconnect_after

    async def is_disconnected(self) -> bool:
        self._asked += 1
        return self._asked > self._after


def _manager() -> AIRequestQueueManager:
    """每个用例一个新 manager：它按 key 常驻队列，共用会串味。"""
    return AIRequestQueueManager(max_pending=10)


async def _watch_admission(mgr: AIRequestQueueManager, key: str, budget_box: List[QueueBudget],
                           seen: List[bool]) -> None:
    """在「队列放行下一个请求」的那一刻，记下旗翻了没有。

    接缝选在 `_PerKeyQueue.exit` 上：`run()` 的 `finally` 里，它是把 active 让给下一个
    排队者的那一步。在它被调用的瞬间取样，就等于问「下一个请求获准开跑时，上一个的
    provider 还收得到叫停吗」。
    """
    q = await mgr._get_queue(key)
    original = q.exit

    async def _recording_exit(item: Any) -> None:
        if budget_box:
            seen.append(budget_box[0].stopped.is_set())
        await original(item)

    q.exit = _recording_exit  # type: ignore[assignment]


# --------------------------------------------------------------------------
# B1 —— `fn` 拿到的 deadline 就是 `run()` 用来判 504 的那一个
# --------------------------------------------------------------------------


def test_B1_交给fn的deadline就是run自己用来判504的那一个() -> None:
    """断的是**同一个事实**，不是「两个数差不多」。

    下界是精确的：504 不许在预算说的时刻**之前**发生。上界留 0.5s 松弛，因为 `run()`
    的等待步长是 0.25s——松弛只吸收轮询粒度，吸收不了「路由自己另算了一份」那种量级
    的偏差（那会差出一整个 timeout_s）。
    """
    mgr = _manager()
    seen: List[QueueBudget] = []

    async def _fn(budget: QueueBudget) -> str:
        seen.append(budget)
        await asyncio.sleep(HARD_BOUND_S)  # 一定等到超时
        return "never"

    async def _drive() -> Tuple[float, Optional[int]]:
        started = time.monotonic()
        status: Optional[int] = None
        try:
            await mgr.run("b1", request=None, timeout_s=SHORT_TIMEOUT_S,
                          request_label="q", fn=_fn)
        except Exception as exc:  # HTTPException(504)
            status = getattr(exc, "status_code", None)
        return time.monotonic() - started, status

    elapsed, status = asyncio.run(asyncio.wait_for(_drive(), HARD_BOUND_S))

    assert status == 504, f"没等到 504，拿到 status={status!r}——这条用例要的是超时那个出口"
    assert seen, "`fn` 一个预算都没收到：`run()` 没把队列手上的那份事实交出来"
    budget = seen[0]

    fired_at = budget.deadline + (elapsed - SHORT_TIMEOUT_S)
    assert fired_at >= budget.deadline - 0.05, (
        "504 在预算说的时刻之前就发生了——`fn` 拿到的 deadline 比 `run()` 自己用的那个晚，"
        "于是 provider 那边以为还有时间，客户端已经拿到 504 了"
    )
    assert elapsed - SHORT_TIMEOUT_S < 0.5, (
        f"504 比预算晚了 {elapsed - SHORT_TIMEOUT_S:.3f}s——超出轮询粒度，"
        f"说明两边用的不是同一个 deadline"
    )


# --------------------------------------------------------------------------
# B2/B3 —— 旗在**任何**出口上都翻，而且翻在放行下一个请求**之前**
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exit_name",
    ["正常返回", "超时504", "客户端断连", "fn自己抛"],
)
def test_B3_每一个出口上叫停都先于放行下一个请求(exit_name: str) -> None:
    """旗必须在 `q.exit` 之前翻起来，四个出口一个都不许漏。

    只断「跑完之后旗是 set 的」会被旧写法骗过去：路由的 `finally` 也能让它最终变 True，
    只是晚了一步——晚在下一个请求已经获准开跑之后。所以这里取样的时刻是
    `q.exit` 被调用的**那一刻**，不是 `run()` 返回之后。
    """
    mgr = _manager()
    key = f"b3-{exit_name}"
    budget_box: List[QueueBudget] = []
    seen_at_admission: List[bool] = []

    request = _DisconnectingRequest(disconnect_after=1) if exit_name == "客户端断连" else None

    async def _fn(budget: QueueBudget) -> str:
        budget_box.append(budget)
        if exit_name == "正常返回":
            return "ok"
        if exit_name == "fn自己抛":
            raise RuntimeError("boom")
        await asyncio.sleep(HARD_BOUND_S)
        return "never"

    async def _drive() -> None:
        await _watch_admission(mgr, key, budget_box, seen_at_admission)
        timeout = SHORT_TIMEOUT_S if exit_name == "超时504" else HARD_BOUND_S
        try:
            await mgr.run(key, request=request, timeout_s=timeout,
                          request_label="q", fn=_fn)
        except BaseException:  # noqa: BLE001 - 四个出口里三个是异常，这条用例不关心是哪一种
            pass

    asyncio.run(asyncio.wait_for(_drive(), HARD_BOUND_S))

    assert budget_box, f"[{exit_name}] `fn` 没收到预算"
    assert seen_at_admission, (
        f"[{exit_name}] 队列一次都没放行下一个请求——`run()` 的 finally 没走到 `q.exit`，"
        f"这条用例取不到样"
    )
    assert seen_at_admission[0] is True, (
        f"[{exit_name}] 队列放行下一个请求的那一刻，上一个请求的叫停旗还没翻。"
        f"下一个请求已经获准开跑，上一个的 provider 线程还在重试——这正是审计 #2 要消灭的窗口"
    )
    assert budget_box[0].stopped.is_set(), f"[{exit_name}] 收尾之后旗仍然没翻"


# --------------------------------------------------------------------------
# B4 —— `should_stop` 是个能直接交给 `_call_provider` 的可调用对象
# --------------------------------------------------------------------------


def test_B4_should_stop是可调用的并且跟着旗走() -> None:
    """`_call_provider(should_stop=...)` 要的是一个 `() -> bool`。

    断它**跟着旗走**（翻旗前 False、翻旗后 True），而不是断它「是个函数」——后者
    一个 `lambda: False` 就能满足，而那正好是最坏的实现：永远说「不用停」。
    """
    mgr = _manager()
    seen: List[QueueBudget] = []

    async def _fn(budget: QueueBudget) -> bool:
        seen.append(budget)
        return budget.should_stop()

    async def _drive() -> bool:
        return await mgr.run("b4", request=None, timeout_s=HARD_BOUND_S,
                             request_label="q", fn=_fn)

    during = asyncio.run(asyncio.wait_for(_drive(), HARD_BOUND_S))

    assert during is False, "`fn` 还在跑的时候 should_stop() 就说要停了——那会让第一次调用就不发车"
    assert seen[0].should_stop() is True, (
        "收尾之后 should_stop() 仍然说不用停——它读的不是那面旗"
    )
