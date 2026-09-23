"""WI-21 —— AI 队列的租约不许漏，也不许把 worker 丢在身后。

`/api/ai/question/{book_uuid}?stream=true` 是全仓唯一一条 **acquire/release 手工配对**
的队列路径（其余两处走 `ai_queue.run()`，那条已经带 `finally`）。两个后果：

* **C4 租约泄漏**：从 `acquire()` 到 `return StreamingResponse(...)` 之间那一大段
  ——`load_book_cached`、`retrieve_passages`、`provider_context_window`、
  `book_token_stats`、`choose_routing`、上下文构造——只有两种**具体**异常被显式
  release 兜住。任何别的异常都带着租约逃走，那条队列于是**永久 active**，这本书
  之后的每一个 AI 请求都排在一个永不结束的请求后面。
  `event_gen()` 里那个 `finally` 救不了：异常发生在 `StreamingResponse(...)`
  **之前**，生成器压根没被创建，它的 `finally` 永远不会执行。
* **C5 跑飞的 worker**：断连/超时会释放租约，却**不取消也不 join** ollama 线程或
  非流式 task。provider 那边还在跑，而下一个「本该串行」的请求已经开始了——串行
  语义在这里是假的。

本文件的断言落点，以及为什么不落在别处：

* Q1 断的是**第二个**请求，不是第一个的状态码。第一个请求 500 是**对的**，
  泄漏的证据只在后继请求身上；断 500 会让一个「500 且泄漏」的实现全绿。
* Q3 断的是**顺序**（worker 先停、租约后放），用一个记录顺序的 list，不用 wall
  clock——挂钟在 CI 上不可靠，而这里要钉的本来就是偏序不是时长。
* Q4 把「租约已释放」和「留了 ERROR」**一起**断。只断日志会被「记了日志但仍不
  释放」骗过；只断释放会让实现悄悄吞掉一个跑飞的 worker。

隔离约定（`tests/unit/conftest.py` 那两条 autouse 围栏之外还要自己做的）：

* `server.book_uuid_resolver.books_dir` 指向一个**不存在**的 tmp 路径。
  `folder_for_book_uuid()` 在缓存未命中时会 `scan()`，指向真实 `books/` 会走进
  开发者的书库；这里预先把映射塞进缓存，scan() 因此永远不会真的去列目录。
* `server.ai_queue` 每个用例换一个新的 `AIRequestQueueManager`。它是模块级单例，
  队列字典按 key 常驻，上一个用例漏掉的租约会变成下一个用例的「灵异排队」。
* `TestClient` **不进 with**（lifespan 不跑 → startup 不扫库），且
  `base_url="http://127.0.0.1"`——WI-27 的 `RequestGuardMiddleware` 白名单里没有
  `testserver`，用默认 base_url 会一路 400，而那与租约无关。
* 不发真实网络请求：非 ollama 路径 monkeypatch `server._call_provider`，
  ollama 路径 monkeypatch `server._egress_post_stream`（WI-30 之前是
  `urllib.request.urlopen`；出网收进 `_http.post_stream` 之后接缝跟着挪）。

超时的处理：本仓没有 pytest-timeout。每个异步用例的**整体**都套在
`asyncio.wait_for(..., HARD_BOUND_S)` 里，所以「实现挂住」表现为
`asyncio.TimeoutError`，与断言变红（`AssertionError`）在输出里一眼可分。

011 WI-4 之后 `api_ai_question` 搬到了 `web/routers/ai/chat.py`。这次跟着改的
**只有三处取 handler 的地方**（两处 `await ...(...)`、一处 `inspect.getsource`）；
上面那 11 处 `monkeypatch.setattr(server, ...)` 一个字没动。这不是省事，是判据：
chat.py 走的是 `from .. import server as _server` 再 `_server.X`，属性在调用时才
解析，所以打在 `server` 上的桩仍然落得到。如果哪天要把这些 setattr 的目标也改成
`chat_router` 才能绿，那说明接缝被旁路了——别改测试，去看搬家。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import pickle
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator, List

import pytest
from fastapi.concurrency import run_in_threadpool
from fastapi.testclient import TestClient
from starlette.requests import Request

from reader3_app import search_service
from reader3_app.ai.books import BookUuidResolver
from reader3_app.ai.queue import AIRequestQueueManager
from reader3_app.reader3 import Book, BookMetadata, ChapterContent, TOCEntry
from reader3_app.web import server
from reader3_app.web.routers.ai import chat as chat_router

BOOK_ID = "lease_sample_data"
BOOK_UUID = "22222222-3333-4444-8555-666666666666"

#: provider 的 timeout。租约漏掉时第二个请求会**排队等满这个时长**再 504，所以它
#: 既是「泄漏可观测」的条件，也是用例总时长的上界。别调大。
PROVIDER_TIMEOUT_S = 2.0

#: 每个异步用例的硬上界。远大于 PROVIDER_TIMEOUT_S，只用来把「挂死」和「断言红」
#: 区分开——超过它说明实现卡住了，不是某条断言不成立。
HARD_BOUND_S = 20.0

BOOK_TEXT = "LEASE-BODY-4c8ff1 the whole chapter is one sentence."


def _build_book() -> Book:
    return Book(
        metadata=BookMetadata(
            title="LEASE-TITLE-4c8ff1",
            language="en",
            authors=["Lease Fixture"],
            description="fixture",
        ),
        spine=[
            ChapterContent(
                id="item_0",
                href="chap0.html",
                title="Chapter One",
                content=f"<p>{BOOK_TEXT}</p>",
                text=BOOK_TEXT,
                order=0,
            )
        ],
        toc=[TOCEntry(title="Chapter One", href="chap0.html", file_href="chap0.html", anchor="")],
        images={},
        source_file="lease.epub",
        processed_at="2026-01-01T00:00:00+00:00",
    )


class _FakeProviderResponse:
    text = "FAKE-ANSWER-4c8ff1"
    model = "fake-model"
    finish_reason = "stop"
    token_count = 3


def _clear_caches() -> None:
    server.load_book_cached.cache_clear()
    search_service.load_book_cached.cache_clear()
    server._stats_cache.clear()


@dataclass
class LeaseEnv:
    client: TestClient
    books_dir: Path
    runtime: dict
    order: List[str] = field(default_factory=list)
    provider_call: Any = None

    @property
    def queue_key(self) -> str:
        return f"{BOOK_UUID}:{self.runtime['provider']}"

    def queue(self):
        return server.ai_queue._queues.get(self.queue_key)

    def lease_is_held(self) -> bool:
        """队列里还有人占着位子吗?

        `_active` 与 `_queue` 一起看：`_active` 是「有人在跑」，`_queue` 非空是
        「有人在排」。泄漏的形状是前者为真而没有任何请求还活着。
        """
        q = self.queue()
        if q is None:
            return False
        return bool(q._active) or bool(q._queue)

    def question_payload(self) -> dict:
        return {"question": "what happens here?", "provider": self.runtime["provider"]}

    def stream_url(self) -> str:
        return f"/api/ai/question/{BOOK_UUID}?stream=true"


@pytest.fixture
def lease_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[LeaseEnv]:
    monkeypatch.chdir(tmp_path)

    books_dir = tmp_path / "books"
    (books_dir / BOOK_ID).mkdir(parents=True)
    with open(books_dir / BOOK_ID / "book.pkl", "wb") as f:
        pickle.dump(_build_book(), f)

    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))

    # books_dir 指向不存在的路径（硬要求）；映射预先塞进缓存，folder_for_book_uuid()
    # 因此在缓存里就命中，scan() 不会被调用。
    resolver = BookUuidResolver(str(tmp_path / "no_such_books_dir"))
    resolver._uuid_to_folder[BOOK_UUID] = BOOK_ID
    resolver._folder_to_uuid[BOOK_ID] = BOOK_UUID
    monkeypatch.setattr(server, "book_uuid_resolver", resolver)

    monkeypatch.setattr(server, "ai_queue", AIRequestQueueManager(max_pending=10))

    runtime = {"provider": "anthropic", "model": "fake-model", "base_url": "", "timeout_s": PROVIDER_TIMEOUT_S}

    def fake_runtime(provider: Any = None, model: Any = None):
        return (
            runtime["provider"],
            "fake-api-key",
            runtime["base_url"],
            runtime["model"],
            runtime["timeout_s"],
        )

    monkeypatch.setattr(server, "_get_provider_runtime", fake_runtime)
    monkeypatch.setattr(server, "retrieve_passages", lambda *a, **kw: ([], 7))
    monkeypatch.setattr(server, "_call_provider", lambda *a, **kw: _FakeProviderResponse())

    monkeypatch.delenv("READER3_TOKEN", raising=False)
    monkeypatch.delenv("READER3_ALLOWED_HOSTS", raising=False)

    _clear_caches()
    try:
        yield LeaseEnv(
            client=TestClient(server.app, base_url="http://127.0.0.1"),
            books_dir=books_dir,
            runtime=runtime,
        )
    finally:
        _clear_caches()


def _record_release_order(env: LeaseEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    """把「租约释放」这一步记进 env.order，同时仍然真的释放。"""
    real_release = server.ai_queue.release

    async def recording(lease):
        env.order.append("lease-released")
        await real_release(lease)

    monkeypatch.setattr(server.ai_queue, "release", recording)


def _run(coro_factory) -> Any:
    """跑一个异步用例，并给它一个硬上界。

    超过 HARD_BOUND_S 抛 asyncio.TimeoutError —— 那是「实现挂住」，不是断言不成立。
    """

    async def bounded():
        return await asyncio.wait_for(coro_factory(), timeout=HARD_BOUND_S)

    return asyncio.run(bounded())


# --------------------------------------------------------------------------
# Q1 —— 承重：租约后的**任意**异常之后，同一本书的下一个请求仍拿得到租约
# --------------------------------------------------------------------------

def test_Q1_租约之后抛任意异常下一个同书请求仍拿得到租约(
    lease_env: LeaseEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """在 routing 处注入一个 RuntimeError —— 一种**没有**被显式 release 兜住的异常。

    第一个请求失败是预期的，`contextlib.suppress` 吞掉；这里一个字都不断它的
    状态码。500 本来就是对的，而「500 且租约泄漏」和「500 且租约已释放」在第一个
    响应上完全无法区分——证据全在第二个请求身上。
    """
    real_choose_routing = server.choose_routing
    calls = {"n": 0}

    def flaky_choose_routing(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("INJECTED-AFTER-LEASE-4c8ff1")
        return real_choose_routing(**kwargs)

    monkeypatch.setattr(server, "choose_routing", flaky_choose_routing)

    with contextlib.suppress(Exception):
        lease_env.client.post(lease_env.stream_url(), json=lease_env.question_payload())

    assert calls["n"] == 1, "注入没有生效：routing 根本没被调用，这条用例什么都没测"

    # 断的是租约状态本身，不是任何 HTTP 状态码。
    assert not lease_env.lease_is_held(), (
        "routing 抛错之后队列仍然 active：租约被那条异常带走了，"
        "这本书之后的每一个 AI 请求都会排在一个永不结束的请求后面"
    )

    started = time.monotonic()
    resp = lease_env.client.post(lease_env.stream_url(), json=lease_env.question_payload())
    elapsed = time.monotonic() - started

    assert resp.status_code == 200
    assert "event: done" in resp.text
    assert elapsed < PROVIDER_TIMEOUT_S, (
        f"第二个请求花了 {elapsed:.2f}s —— 它在排队等一个已经不存在的请求"
    )
    assert not lease_env.lease_is_held()


# --------------------------------------------------------------------------
# Q2 —— 回归保护：正常完成之后租约也要放
# --------------------------------------------------------------------------

def test_Q2_正常完成之后租约也释放(lease_env: LeaseEnv) -> None:
    """没有这条，一个「finally 里什么都不做」的实现能让 Q1 全绿。"""
    for attempt in range(2):
        started = time.monotonic()
        resp = lease_env.client.post(lease_env.stream_url(), json=lease_env.question_payload())
        elapsed = time.monotonic() - started

        assert resp.status_code == 200, f"第 {attempt + 1} 个请求: {resp.status_code}"
        assert "event: done" in resp.text
        assert elapsed < PROVIDER_TIMEOUT_S, f"第 {attempt + 1} 个请求排了 {elapsed:.2f}s"
        assert not lease_env.lease_is_held(), f"第 {attempt + 1} 个请求完成后租约没放"


# --------------------------------------------------------------------------
# 断连用例的公共装置
# --------------------------------------------------------------------------

class _ObservableGate:
    """一把闸，外加「它是怎么被等的」这件事本身。

    017 WI-9（审计 #14）：原来这里是一个裸 `threading.Event`。于是「卡住」这件事
    **只能从外面按时长观察**——测试看得见「第二次 readline 还没返回」，看不见
    「它是因为等这把闸才没返回」。两者的差别不是文字游戏：把假流的阻塞换成无条件
    `time.sleep(3)`、完全不碰闸，那条本该钉住「不许用墙钟冒充卡住」的用例照样全绿，
    因为它断的两件事（0.5s 内没返回、放行后返回了）一个 sleep 也都满足。
    守着 #46 的闸自己就是用墙钟做的。

    所以把「进了 `wait()`」和「进去时带的 timeout 实参」记下来，让它们可断：

    * `wait_until_entered()` —— 真的有人进到这把闸里等了。这是**正面**证据，
      sleep 之类根本不碰闸的实现给不出它。
    * `wait_timeouts` —— 每次 `wait()` 的 timeout 实参。必须是 `[None]`：
      一旦带上秒数，「卡住」就又变成了「最多卡这么久」，#46 原样长回来。
    * `waiter_thread` —— 谁在这把闸里等。收尾要 join 的就是它（审计 #13）；
      不留这个句柄就只能把一个阻塞中的线程丢给后面的用例。
    """

    def __init__(self) -> None:
        self._event = threading.Event()
        self._entered = threading.Event()
        self.wait_timeouts: List[Any] = []
        self.waiter_thread: threading.Thread | None = None

    def wait(self, timeout: float | None = None) -> bool:
        # 记在**阻塞之前**：等进去了才记就永远记不上，那正是要观察的那一刻。
        self.wait_timeouts.append(timeout)
        self.waiter_thread = threading.current_thread()
        self._entered.set()
        return self._event.wait(timeout)

    def set(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    def wait_until_entered(self, timeout: float) -> bool:
        """阻塞到有人进了这把闸为止。上界是防挂死的保险，不是判据。"""
        return self._entered.wait(timeout)


class _FakeOllamaStream:
    """一个**永不结束**的 ollama 响应：只有停止事件能让 worker 走出 with 块。

    没有 done 事件，所以「worker 退出了」只可能是因为它读到了停止事件——
    这正是要证的那件事。退出时往 order 里记一笔。

    **``stuck_gate`` 是「卡住」的唯一表达方式，故意不是一个秒数。** 这里原本写的是
    ``stuck_delay: float``，第二次 ``readline`` 睡够那么多秒再返回；Q4 于是暗含
    「整段 scenario 在 stuck_delay 内跑完」这个对运行器速度的假设，慢 runner 上
    假 worker 自己醒了，前提自毁（欠账 #46，三次 CI 里红了两次）。换成 Event 之后
    「卡住」不再有时长，只有状态：**没放行就是没放行**，机器快慢与它无关。
    谁把它设上，谁负责在收尾时 ``set()`` 放行**并 join 那个线程**——worker 线程是
    daemon（``routers/ai/chat.py:320``），daemon 只保证它拦不住解释器退出，不保证它
    在下一条用例开始前已经结束。放行而不 join，等于把一个刚被唤醒、还要再走一圈
    循环的线程丢给后面的用例（审计 #13）。

    闸的类型是 `_ObservableGate` 而不是 `threading.Event`：见它的 docstring。
    """

    def __init__(self, order: List[str], *, line_delay: float) -> None:
        self.order = order
        self.line_delay = line_delay
        self.stuck_gate: _ObservableGate | None = None
        self.lines_served = 0
        self.exited = False

    def __enter__(self) -> "_FakeOllamaStream":
        return self

    def __exit__(self, *exc: Any) -> bool:
        self.exited = True
        self.order.append("worker-stopped")
        return False

    def readline(self) -> bytes:
        # 第一行立刻给，后面的按 delay 给：消费者得先拿到一个 chunk 才有「断连」
        # 这个时点可言。
        if self.lines_served:
            if self.stuck_gate is not None:
                # 卡住——直到测试明确放行为止。这里**不许**出现任何超时参数：
                # 一旦有，「卡住」就又变成了「最多卡这么久」，#46 原样长回来。
                self.stuck_gate.wait()
            time.sleep(self.line_delay)
        self.lines_served += 1
        return json.dumps(
            {"model": "fake-ollama", "message": {"content": "tick"}}
        ).encode("utf-8") + b"\n"


# --------------------------------------------------------------------------
# #46 的回归闸 —— 「卡住」不许再用墙钟冒充
# --------------------------------------------------------------------------

#: 观察窗：在这段时间内第二次 readline 必须**还没**返回。
#: 这个方向对慢机器免疫——机器越慢越不可能返回，所以它不会假红。
_STUCK_OBSERVE_S = 0.5

#: 放行之后的上界。它是**防挂死的保险，不是判据**：一个已经被 set 的
#: Event，其 wait() 返回所需的时间与任何合理的调度延迟都差着几个数量级。
_STUCK_RELEASE_BOUND_S = 10.0

#: 「有人进到闸里等了」的上界。同样是**防挂死的保险，不是判据**——判据是
#: 「进没进」，不是「多快进的」：假流交出第一行之后紧接着就是第二次 readline，
#: 中间只有一次 json.dumps，与这个上界差着几个数量级。
_GATE_ENTRY_BOUND_S = 10.0


def test_假流的卡住由放行闸决定而不由墙钟决定() -> None:
    """Q4 的前提「worker 停不下来」不得依赖运行器跑多快。

    原来的写法用 ``time.sleep(stuck_delay=3.0)`` 冒充「卡住」，于是 Q4 的前提
    里藏着一句没人写出来的话：**整段 scenario 必须在 3 秒内跑完**。GitHub
    Actions 的 runner 上跑不完，假 worker 自己醒了，`assert not
    stuck_stream.exited` 于是自毁——三次 CI 里红了两次（[欠账 #46]）。

    模块 docstring 里「不用 wall clock」那条纪律当时只落实到了 Q3 的偏序断言上；
    Q4 把秒数挪进了 fixture，假设仍在，只是看不见了。这条用例钉的就是
    「那个秒数不许再长回来」：第二次 ``readline`` 必须一直阻塞到闸被放行为止。

    **017 WI-9（审计 #14）：上面这套还不够，它自己也是用墙钟做的。** 原来这条用例
    只断两件事——0.5s 内没返回、放行后返回了——而一个无条件 `time.sleep(3)`、
    从头到尾不碰闸的假流**两件都满足**：3 秒内它当然没返回，3 秒后它当然返回了，
    跟谁放不放行毫无关系。也就是说，守着「不许用墙钟冒充卡住」的这道闸，验的却
    只是墙钟本身。于是加上正面证据：那次阻塞必须**真的发生在这把闸里**，而且
    进去时不带 timeout。

    四个方向分开断，性质不同，别合并：

    * **阻塞发生在闸里** —— 正面证据。不碰闸的实现根本给不出它，`sleep` 冒充的
      「卡住」在这一条上立刻现形。这是判据。
    * **进闸时不带 timeout** —— `wait(3.0)` 也会进闸，但那是「最多卡 3 秒」，
      #46 就是这么长回来的。所以实参本身要断。这是判据。
    * **放行前一直阻塞** —— 慢机器只会让它更成立，不可能假红。这是判据。
    * **放行后能返回** —— 这个方向对慢机器敏感，所以用一个远大于任何合理调度
      延迟的上界兜底。它只是防止实现写挂时把整条 lane 吊死，不承担判断。
    """
    order: List[str] = []
    gate = _ObservableGate()
    stream = _FakeOllamaStream(order, line_delay=0.01)
    stream.stuck_gate = gate

    assert stream.readline(), "第一行必须立刻给：消费者得先拿到一个 chunk 才谈得上断连"

    returned = threading.Event()

    def _second_readline() -> None:
        stream.readline()
        returned.set()

    thread = threading.Thread(target=_second_readline, daemon=True)
    thread.start()
    try:
        assert gate.wait_until_entered(_GATE_ENTRY_BOUND_S), (
            f"第二次 readline 在 {_GATE_ENTRY_BOUND_S}s 内没有进到这把闸里等——"
            "那它是被别的什么挡住的（一个 sleep？），而那正是 #46 的形状。"
            "「卡住」必须是「在等这把闸」，不能只是「还没返回」"
        )
        assert not returned.wait(_STUCK_OBSERVE_S), (
            f"第二次 readline 在 {_STUCK_OBSERVE_S}s 内自己返回了：假流又在靠墙钟"
            "「醒过来」。这会让 Q4 的前提重新变成一场对运行器速度的赌，"
            "而那场赌在 CI 上已经输过两次（欠账 #46）"
        )
    finally:
        # 放行，别把一个永远阻塞的线程留给后面的用例。
        gate.set()

    assert returned.wait(_STUCK_RELEASE_BOUND_S), (
        f"闸放行后 {_STUCK_RELEASE_BOUND_S}s 内 readline 仍没返回：卡住的实现"
        "把自己也锁死了，这样的假流没法用来收尾"
    )
    thread.join(_STUCK_RELEASE_BOUND_S)
    assert not thread.is_alive(), "放行并 join 之后线程还活着：这样的假流会漏到下一条用例"

    assert gate.wait_timeouts == [None], (
        f"进闸时带了 timeout 实参: {gate.wait_timeouts}；带上秒数之后「卡住」就变回了"
        "「最多卡这么久」，Q4 的前提重新变成一场对运行器速度的赌——#46 就是这么来的"
    )


class _ControllableRequest(Request):
    """一个真的 starlette Request，断连时点由测试控制。

    为什么不是 TestClient：starlette 的 `_TestClientTransport.receive()` 在请求体
    读完之后会 `await response_complete.wait()` 才返回 `http.disconnect`
    （testclient.py:298-304）——也就是说**响应流完之前，TestClient 永远不会报
    断连**。流式响应中途断连在 TestClient 里根本无法表达，所以这两条用例直接
    调 handler，用一个真 Request + 自己的 receive 来给出那个时点。
    `Request.is_disconnected()` 走的是同一段代码。
    """

    def __init__(self) -> None:
        self.disconnected = False
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": f"/api/ai/question/{BOOK_UUID}",
            "raw_path": f"/api/ai/question/{BOOK_UUID}".encode(),
            "query_string": b"stream=true",
            "root_path": "",
            "headers": [(b"host", b"127.0.0.1")],
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8123),
        }
        super().__init__(scope, receive=self._receive)

    async def _receive(self) -> dict:
        if self.disconnected:
            return {"type": "http.disconnect"}
        return {"type": "http.request", "body": b"", "more_body": False}


async def _drive_until_first_chunk(agen) -> List[bytes]:
    """迭代到收到第一个 chunk 为止，把已经拿到的片段返回。"""
    seen: List[bytes] = []
    while True:
        chunk = await agen.__anext__()
        seen.append(chunk)
        if b"event: chunk" in chunk:
            return seen


async def _disconnect_after_first_chunk(
    env: LeaseEnv,
    fake_stream: _FakeOllamaStream,
    monkeypatch: pytest.MonkeyPatch,
    *,
    before_disconnect: Callable[[], Awaitable[None]] | None = None,
) -> None:
    # WI-30 把 ollama 出网从 `urllib.request.urlopen` 挪到了 `_http.post_stream`
    # （scheme 白名单 + no-redirect opener），所以注入点跟着挪。**断言一字未动**：
    # 挪的是打桩的接缝，不是被钉住的那条性质。`with fake_stream as resp` 是必要的
    # ——`__exit__` 才是往 order 里记 "worker-stopped" 的地方。
    @contextlib.contextmanager
    def _fake_post_stream(*a: Any, **kw: Any):
        with fake_stream as resp:
            yield resp

    monkeypatch.setattr(server, "_egress_post_stream", _fake_post_stream)

    request = _ControllableRequest()
    body = server.AIQuestionRequest(question="what happens here?", provider="ollama")

    response = await chat_router.api_ai_question(request, BOOK_UUID, body, stream=True)
    agen = response.body_iterator

    await _drive_until_first_chunk(agen)

    # 拿到第一个 chunk **不等于** worker 已经开始读第二行。worker 那边是
    # `call_soon_threadsafe(push, chunk)` → 回到循环 → `stop_event.is_set()` →
    # `readline()`（`routers/ai/chat.py:248-253`），而我们这边一收到 chunk 就可以
    # 断连。夹在中间那一小段里如果先翻起了 stop_event，worker 会在**循环顶上**
    # 干干净净地 return——对 Q3 来说那正是要的，对 Q4 来说前提当场自毁。
    # 需要那个时点的用例在这里给一个同步点（审计 #13）。
    if before_disconnect is not None:
        await before_disconnect()

    request.disconnected = True

    # 排空剩下的：event_gen 的 disconnect 分支在这里跑完，连同它的收尾。
    async for _ in agen:
        pass


# --------------------------------------------------------------------------
# Q3 —— 断连之后 worker 确实停了，而且是在租约释放之前停的
# --------------------------------------------------------------------------

def test_Q3_断连之后worker先停租约后放(
    lease_env: LeaseEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    lease_env.runtime["provider"] = "ollama"
    lease_env.runtime["base_url"] = "http://localhost:11434"
    _record_release_order(lease_env, monkeypatch)

    fake_stream = _FakeOllamaStream(lease_env.order, line_delay=0.02)

    _run(lambda: _disconnect_after_first_chunk(lease_env, fake_stream, monkeypatch))

    assert fake_stream.exited, (
        "客户端断连之后 ollama worker 还在跑：没人给它停止事件，也没人等它——"
        "下一个「本该串行」的请求会和它并发打同一个 provider"
    )
    assert lease_env.order == ["worker-stopped", "lease-released"], (
        f"顺序不对: {lease_env.order}；租约必须在 worker 停下之后才释放，"
        "否则下一个请求会在上一个 worker 还活着的时候开始"
    )
    assert not lease_env.lease_is_held()


# --------------------------------------------------------------------------
# Q4 —— worker 不肯停：仍然释放租约，并留下 ERROR
# --------------------------------------------------------------------------

def test_Q4_worker停不下来时仍释放租约并留ERROR(
    lease_env: LeaseEnv, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """取舍写在 Acceptance 里：租约永久泄漏比一个跑飞的线程更糟。

    两条一起断。只断日志会被「记了日志但仍不释放」骗过；只断释放会让一个
    悄悄吞掉跑飞 worker 的实现看起来完全正常。

    **017 WI-9（审计 #13）：这条用例的前提原来是赌出来的。** 「worker 停不下来」
    要成立，worker 必须已经**进到**第二次 `readline()` 里——只有进去了，它才会
    错过循环顶上那次 `stop_event.is_set()`。而原来的写法拿到第一个 chunk 就直接
    断连，中间没有任何同步：worker 若还卡在 `call_soon_threadsafe` 到下一次循环
    顶之间（纯调度，几微秒，但在有负载的 runner 上就是会发生），它会读到刚翻起的
    stop_event 然后**干净地 return**，`assert not stuck_stream.exited` 当场自毁。
    那和 #46 是同一种病：前提靠时序碰运气，红起来还不可归因。

    现在断连之前等一个**正面**事件：worker 真的在闸里等着了（`_ObservableGate`）。
    这不是把窗口调大，是把窗口取消——等不到就直接红，且红得说得清原因。

    收尾也一并改：放行之后 **join** 那个线程并断言它真的结束了。放行而不 join，
    等于把一个刚被唤醒的线程丢给后面的用例；而 join 不上就说明假流把自己锁死了，
    那是下一条用例会莫名其妙红掉的来源。
    """
    lease_env.runtime["provider"] = "ollama"
    lease_env.runtime["base_url"] = "http://localhost:11434"

    # 有界超时调小，用例才跑得快。断言里不出现任何秒数。
    monkeypatch.setattr(server, "AI_WORKER_STOP_TIMEOUT_S", 0.2, raising=False)

    # 「停不下来」用一把只有本用例能放行的闸表达，不用秒数——理由见
    # `_FakeOllamaStream` 的 docstring 与 `test_假流的卡住由放行闸决定而不由墙钟决定`。
    stuck_gate = _ObservableGate()
    stuck_stream = _FakeOllamaStream(lease_env.order, line_delay=0.02)
    stuck_stream.stuck_gate = stuck_gate

    async def _park_worker_in_the_gate() -> None:
        # 在线程里等，别把事件循环堵住：断连分支、`_stop_stream_worker` 的有界等待
        # 都还要在这个循环上跑。
        entered = await run_in_threadpool(stuck_gate.wait_until_entered, _GATE_ENTRY_BOUND_S)
        assert entered, (
            f"{_GATE_ENTRY_BOUND_S}s 内 worker 没进到第二次 readline 的闸里。"
            "这条用例的前提是「worker 已经错过了循环顶上的 stop 检查」，前提不成立时"
            "断连测到的是「一个还没起跑的 worker 被干净地叫停了」——那是 Q3 的性质，"
            "不是 Q4 的"
        )

    async def scenario() -> None:
        await _disconnect_after_first_chunk(
            lease_env, stuck_stream, monkeypatch, before_disconnect=_park_worker_in_the_gate
        )

        # 「下一个请求拿得到租约」才是「已释放」的可观测形式。
        lease = await asyncio.wait_for(
            server.ai_queue.acquire(
                lease_env.queue_key,
                request=None,
                timeout_s=PROVIDER_TIMEOUT_S,
                request_label="probe",
            ),
            timeout=PROVIDER_TIMEOUT_S + 1.0,
        )
        await server.ai_queue.release(lease)

    worker_alive_after_release: List[bool] = []
    try:
        with caplog.at_level(logging.ERROR, logger="reader3.ai"):
            _run(scenario)

        assert not stuck_stream.exited, (
            "这条用例的前提没成立：假 worker 本应无视停止事件，但它停了"
        )

        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert errors, (
            "worker 在有界超时内没停下来，却一条 ERROR 都没留：一个跑飞的 provider "
            "调用就这样无声无息了"
        )
    finally:
        # 放行并 join，别把 worker 线程堵在 readline 里留给后面的用例。
        # join 的结果先记下来、出了 finally 再断——finally 里 assert 会把 try 体里
        # 真正的失败盖掉，而那条才是要看的。
        stuck_gate.set()
        worker = stuck_gate.waiter_thread
        if worker is not None:
            worker.join(_STUCK_RELEASE_BOUND_S)
            worker_alive_after_release.append(worker.is_alive())

    assert worker_alive_after_release == [False], (
        f"收尾之后 worker 线程的状态: {worker_alive_after_release}（期望 [False]）。"
        "`[]` 是「根本没人进过闸」——前提没成立；`[True]` 是「放行了也没结束」，"
        "那个线程会带着 monkeypatch 拆掉之后的全局状态活到下一条用例里"
    )


# --------------------------------------------------------------------------
# Q5 —— 只留一处 release（验收明写：显式 release 全删，只留 finally 一处）
# --------------------------------------------------------------------------

def test_Q5_流式路径上没有散落的显式release(lease_env: LeaseEnv) -> None:
    """两套释放并存正是 C4 的成因，所以「只有一处」本身就是验收项。

    数的是 `api_ai_question` 的源码里 `ai_queue.release` 出现几次。它是结构断言，
    不是行为断言——行为由 Q1/Q2 钉住；这条钉的是「以后没人再往回加第二处」。
    """
    import inspect

    source = inspect.getsource(chat_router.api_ai_question)
    occurrences = source.count("ai_queue.release")

    assert occurrences == 1, (
        f"api_ai_question 里有 {occurrences} 处 ai_queue.release；"
        "验收要求只保留 finally/ExitStack 那一处，散落的显式 release 正是 C4 的成因"
    )


# --------------------------------------------------------------------------
# Q6 —— 非 ollama 路径的断连也要真的取消 worker（矩阵那张表没覆盖到的一半）
# --------------------------------------------------------------------------
#
# 加这一条是因为变异扫描打脸了：矩阵预测「断连路径去掉 task.cancel() / 停止事件」
# 会让 Q3 变红，但 Q3 只走 ollama 线程那一条。把非流式 worker 的 `task.cancel()`
# 去掉，Q1–Q5 **全绿**——那一半根本没人看着。
#
# 顺带查清了一件本条工作项里最容易想错的事，写在这里免得下一个人重新踩：
# 非 ollama 路径上**做不到**「等 worker 真的跑完再放租约」。worker 阻塞在
# `run_in_threadpool()` 里，这套依赖（anyio 4.11 / starlette 0.49）在 task 被
# 取消时**直接放弃那个线程**——task 立刻 done，线程照跑到底，而且我们手里根本
# 没有那个 Thread 对象可以 join。实测：1.0s 的阻塞调用，cancel 之后 task 在
# 0.1s 就 done 了，线程 1.01s 才结束。
#
# 所以这条路上可断的不是「worker 停了」，而是**「取消真的发生了」**：取消发生
# 时 task 立刻进终态，`_stop_stream_worker` 的有界等待马上返回，不会留下
# runaway 的 ERROR；**没**取消时 task 会一直挂到 provider 调用自己结束，有界
# 超时先到，于是留下一条 ERROR。Q4 钉的是「真停不下来 → 必须有 ERROR」，这条
# 钉的是反面「取消得掉 → 不许有 ERROR」，两条合起来才让那条 ERROR 有意义。


class _BlockingProviderCall:
    """一个跑得完但跑得久的 provider 调用。

    ``delay`` 必须**明显大于**测试设的 ``AI_WORKER_STOP_TIMEOUT_S``：worker 要在
    有界等待窗口里仍然「在跑」，这条用例才分得出「取消了」和「没取消」。
    """

    def __init__(self, *, delay: float) -> None:
        self.delay = delay
        self.entered = threading.Event()
        self.finished = False

    def __call__(self, *args: Any, **kwargs: Any) -> _FakeProviderResponse:
        self.entered.set()
        time.sleep(self.delay)
        self.finished = True
        return _FakeProviderResponse()


async def _disconnect_while_provider_call_is_in_flight(env: LeaseEnv) -> None:
    """在 worker **正在跑** provider 调用的时候断连。

    非 ollama 路径上第一个 chunk 要等整趟 provider 调用结束才会出现，所以 Q3 那个
    「等第一个 chunk 再断」在这里会等到 worker 都跑完了，什么也测不到。

    也不能收到 meta 就立刻断：`asyncio.create_task()` 只是排了个队，worker 协程
    要到下一个 await 点才真的开始。那一瞬断连的话 worker 会在**一行都没执行**的
    状态下被取消——测出来的是「取消一个没起跑的 task」，不是「取消一个在跑的 worker」。
    所以先把生成器推进去，等 provider 调用真的进去了，再断。
    """
    request = _ControllableRequest()
    body = server.AIQuestionRequest(question="what happens here?", provider="anthropic")

    response = await chat_router.api_ai_question(request, BOOK_UUID, body, stream=True)
    agen = response.body_iterator

    first = await agen.__anext__()
    assert b"event: meta" in first

    pending = asyncio.ensure_future(agen.__anext__())
    await run_in_threadpool(env.provider_call.entered.wait, 5.0)
    assert env.provider_call.entered.is_set(), "provider 调用没被发起，这条用例什么都没测"

    request.disconnected = True
    await pending

    async for _ in agen:
        pass


def test_Q6_非ollama路径断连时worker真的被取消(
    lease_env: LeaseEnv, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(server, "AI_WORKER_STOP_TIMEOUT_S", 0.2, raising=False)

    blocking = _BlockingProviderCall(delay=1.2)
    lease_env.provider_call = blocking
    monkeypatch.setattr(server, "_call_provider", blocking)

    with caplog.at_level(logging.ERROR, logger="reader3.ai"):
        _run(lambda: _disconnect_while_provider_call_is_in_flight(lease_env))

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not errors, (
        f"断连之后留下了 runaway 的 ERROR: {[r.getMessage() for r in errors]}；"
        "一个 cancel 得掉的 task 被当成了停不下来的 worker——说明根本没人 cancel 它"
    )
    assert not lease_env.lease_is_held()
