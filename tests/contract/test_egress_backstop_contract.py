"""WI-3 —— contract lane 那一半的出网闸自检（C2、C4）。

`tests/unit` 和 `tests/contract` 是**同一条 lane**（`uv run pytest tests/unit tests/contract`）
但是**两个 fixture 根**：能一处注册管两边的地方是 `tests/conftest.py`，而它是冻结路径
（动一个字节就重置 soak 台账；当前 suite_hash 见 `soak-log.md`，那里是唯一定义处——
此处此前抄过一个值，2026-09-21 它烂了）。所以闸体单一来源在
`tests/unit/egress_guard.py`，**注册**在两处 conftest 各写一遍——C2 钉的正是「contract
这一处也真的注册了」。

模块名刻意跟 unit 那边不同（`..._contract.py` / `..._unit.py`）：两个目录都没有
`__init__.py`，同名模块在 pytest 默认的 prepend import 模式下会直接以
`import file mismatch` 收集失败。这不是风格选择，是收集错误。

本 lane 需要**零条**豁免：整条 lane 走 TestClient / httpx 的 ASGI transport，不开真 socket。

断言档位：L4 故障注入。
"""

from __future__ import annotations

import os
import socket
from typing import Any, List, Tuple

import pytest

from conftest import FAKE_MODEL, World  # type: ignore[import-not-found]

BLOCKED_ADDR = "203.0.113.1"


def load_guard():
    """在用例**内部**导入。闸还不存在时，顶层 import 会把红跑成 collection error。"""
    try:
        import egress_guard  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - 只在闸还没落地时走到
        raise AssertionError(
            "tests/unit/egress_guard.py 还不存在，或者 tests/contract/conftest.py 没有把 "
            "tests/unit/ 显式插进 sys.path——单独跑 `pytest tests/contract` 时没有任何东西"
            "会把那个目录放上去（C12 钉的就是这件事）"
        ) from None
    return egress_guard


def violations(request: pytest.FixtureRequest) -> List[Tuple[str, str, str]]:
    try:
        return request.getfixturevalue("egress_violations")
    except pytest.FixtureLookupError as exc:  # pragma: no cover
        raise AssertionError(
            "egress_violations fixture 在 contract 这一侧没被注册："
            "闸体是单一来源了，注册仍然是两份，而这条用例钉的就是注册"
        ) from exc


# --------------------------------------------------------------------------
# C2 —— contract lane 自检：同一道闸，同样的行为。 L4 / S1
# --------------------------------------------------------------------------


def test_a_routable_connect_is_blocked_and_recorded(request: pytest.FixtureRequest) -> None:
    guard = load_guard()
    recorded = violations(request)

    code = getattr(socket.socket.connect, "__code__", None)
    assert code is not None and os.path.realpath(code.co_filename) == os.path.realpath(
        guard.__file__
    ), (
        "contract 这一侧装的是 conftest 里另抄的一份 _boom（或者压根没装）："
        f"co_filename={code and code.co_filename}。C11 在子解释器里证的不是它"
    )

    s = socket.socket()
    s.settimeout(0.5)
    try:
        with pytest.raises(AssertionError) as exc:
            s.connect((BLOCKED_ADDR, 80))
    finally:
        s.close()

    assert BLOCKED_ADDR in str(exc.value), f"异常消息里没有地址：{exc.value}"
    assert len(recorded) == 1, f"闸抛了但没记：{recorded}"
    assert BLOCKED_ADDR in recorded[0][1], f"记下来的地址是 {recorded[0][1]}"
    recorded.clear()


# --------------------------------------------------------------------------
# C4 —— 真实的工作线程路径：吞异常的是**生产代码**，并且断言地址。 L4 / S1
# --------------------------------------------------------------------------


def test_egress_from_a_real_threadpool_worker_is_recorded_with_its_address(
    world: World, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """出网发生在 ``run_in_threadpool`` 派发出去的 worker 里，异常被路由自己的
    ``except Exception`` 吞掉——这正是「必须记账、不能只靠抛」的那条路径。

    注入点是 ``server._call_provider``（打桩名单上的名字，WI-2 的锁断的是集合不是计数，
    所以不受影响）。第一次调用去连 203.0.113.1：闸记一笔并抛 AssertionError，
    ``server.py`` 的 full_book 回退分支把它吞掉并重试；第二次调用正常返回，路由 200。
    吞异常的是生产代码，不是本用例——C3 已经覆盖了「用例自己吞」那一种。

    地址那条断言不是装饰：「一条记录 + 非主线程」恰好也是 WI-0 要防的那个生产态——
    ``_call_provider`` 被 re-export 之后 8 处桩一个都拦不住，路由去拨真正的
    api.anthropic.com，一条记录、工作线程。没有地址断言，那时这条用例仍然是绿的。
    """
    from reader3_app.ai.providers.types import ProviderResponse
    from reader3_app.web import server

    load_guard()
    recorded = violations(request)

    calls: List[str] = []

    def _connecting_provider(provider_name: str, **kwargs: Any) -> ProviderResponse:
        calls.append(provider_name)
        if len(calls) == 1:
            s = socket.socket()
            s.settimeout(0.5)
            try:
                s.connect((BLOCKED_ADDR, 80))
            finally:
                s.close()
        return ProviderResponse(
            text="fallback", model=FAKE_MODEL, finish_reason="stop", token_count=1
        )

    monkeypatch.setattr(server, "_call_provider", _connecting_provider)

    resp = world.client.post(
        f"/api/ai/question/{world.book_uuid}",
        json={"question": "Ozymandias", "provider": "anthropic"},
    )

    assert len(recorded) == 1, (
        f"路由线程里的出网没有留下记录，HTTP 返回 {resp.status_code} {resp.text[:200]}——"
        "路由的 except Exception 把闸的 AssertionError 吞了，而这正是"
        "「必须记账、不能只靠抛」的理由"
    )
    assert BLOCKED_ADDR in recorded[0][1], (
        f"记到了一条出网，但地址是 {recorded[0][1]}，不是本用例注入的 {BLOCKED_ADDR}。"
        "「一条 + 非主线程」正好也是 WI-0 要防的那个生产态：_call_provider 被 re-export "
        "之后桩拦不住，路由去拨真正的 api.anthropic.com，一条记录、工作线程——"
        "那时这条用例仍然是绿的"
    )
    assert recorded[0][0] != "MainThread", (
        f"这条本该跑在工作线程上，实际记到 {recorded[0][0]}"
    )

    # 017 WI-10（审计 #16）：上面三条只证明「闸记下了那次出网」，对**这条路径本身**
    # 一个字都没证。而这条用例的全部价值在于「吞异常的是生产代码」——那句话只有在
    # full_book 回退分支真的跑完、并且真的换成 RAG 重发了一次的时候才成立。
    # 少了下面这四条，一个 500、一次调用、或者压根没走回退的实现照样全绿：闸那边
    # 一样只会记到一次出网。四条各证一个阶段，别合并：
    resp_body = resp.json() if resp.status_code == 200 else {}
    assert resp.status_code == 200, (
        f"路由没有 200，而是 {resp.status_code} {resp.text[:200]}。"
        "「生产代码吞掉了闸的 AssertionError 并重试」这句话的可观测形式就是这个 200——"
        "非 200 说明异常一路抛了出去，那和本用例要证的性质相反"
    )
    assert calls == ["anthropic", "anthropic"], (
        f"provider 被调用了 {len(calls)} 次（{calls}），期望恰好两次。"
        "一次＝没重试（那第一次的异常去哪了？），三次以上＝回退分支自己也在转圈"
    )
    assert resp_body.get("answer") == "fallback", (
        f"answer 是 {resp_body.get('answer')!r}，不是第二次调用返回的 'fallback'。"
        "200 只说明没抛，这一条才说明返回的确实是**重试那次**的结果"
    )
    assert resp_body.get("metadata", {}).get("routing", {}).get("mode") == "rag_fallback", (
        f"routing.mode 是 {resp_body.get('metadata', {}).get('routing', {}).get('mode')!r}，"
        "不是 'rag_fallback'。走的不是 full_book → RAG 那条回退分支，"
        "那这次出网就不是本用例描述的那一次"
    )

    recorded.clear()
