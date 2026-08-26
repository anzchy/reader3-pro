"""WI-22 —— 重活不许占着 asyncio 事件循环。

`server.py` 里有四类同步重活直接跑在 `async def` handler 体内：向量索引
（`index_book`，分钟级 CPU 密集）、索引查看（`status()`）、库搜索（会 unpickle
每一本 `book.pkl`）、书内搜索，以及 RAG 检索一类的上下文构造。它们跑在事件循环
线程上时，**整个进程在此期间答不了任何一个请求**——包括 `/api/health`，而 009 的
Playwright `webServer` 和 `reader3 launch` 都在轮询它。

本文件的断言落点，以及为什么不落在别处：

* **不断源码里出现了 `run_in_threadpool`**。那是接线断言：换个等价写法（比如
  `asyncio.to_thread`）就假绿，而把 `await` 漏掉、或者包了一层却仍在循环里调用，
  它一样是绿的。这里断的是**可观测的偏序**：重活还没返回时，`/api/health` 已经
  答完了。
* **不断任何挂钟耗时**。CI 上的挂钟阈值是 flake 之源。顺序用一个 list 记，
  `order[0] == "health"` 就是全部的判据。
* 除了顺序，还额外断一条**更强、且不受响应回程调度影响**的证据：假重活在自己
  那段阻塞 `sleep` **结束的瞬间**给 `order` 拍一张快照。事件循环没被占住时，
  health 必然已经落在快照里；被占住时，health 连跑都没跑过，不可能在快照里。
  两条一起断，是为了让「撤掉 threadpool」这条变异必然变红，而不是碰运气红。

怎么造并发（本仓的既有路数）：

* **没有 `pytest-asyncio`，本文件也不许引**。同步测试函数内部用
  `asyncio.run(...)` 驱动，整体套 `asyncio.wait_for(..., HARD_BOUND_S)`——
  「实现挂死」于是表现为 `asyncio.TimeoutError`，与断言变红
  （`AssertionError`）在输出里一眼可分。同 `tests/unit/test_ai_queue_lease.py`。
* **不用 `TestClient`**：它是同步的，发不出并发请求。用 httpx 0.28 的
  `ASGITransport`（0.28 删掉了 `AsyncClient(app=...)` 这个快捷参数）。
* 起跑对齐**不用 sleep 猜**：假重活进入阻塞前置一个 `threading.Event`，health
  那一侧轮询这个 event，确认重活**真的已经开始阻塞**之后才发请求。否则在阻塞
  版本里 health 可能抢在重活开始之前答完，测试就会假绿。

隔离约定（`tests/unit/conftest.py` 那两条 autouse 围栏之外还要自己做的）：

* `server.BOOKS_DIR` 与 `server.book_uuid_resolver.books_dir` 都指向 `tmp_path`，
  且 `monkeypatch.chdir(tmp_path)`。真实 `books/` 一个字节都不许碰。
* 不加载真实 embedding 模型：`server.BookVectorIndex` 整个换成假类。
* 不发真实网络请求、不读真实 `config/ai_settings.json`：本文件命中的路由都不碰
  provider。
* `base_url="http://127.0.0.1"`——WI-27 的 `RequestGuardMiddleware` 白名单里没有
  `testserver`；httpx 默认不发 `Origin`，POST 因此不需要额外头。
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator, List

import httpx
import pytest

from reader3_app.ai.books import BookUuidResolver
from reader3_app.search_service import SearchQuery, SearchResult, SearchResultSet, SearchMode, SearchScope
from reader3_app.web import server

BOOK_ID = "loopblock_sample_data"
BOOK_UUID = "44444444-5555-4666-8777-888888888888"

#: 假重活占住 CPU 的时长。只需要远大于一次 `/api/health` 的往返（本地 <2ms），
#: 不参与任何断言——断言只看顺序。
BLOCK_S = 0.2

#: 等「重活确实开始阻塞」的上界。到点还没开始就照发 health，让断言而不是超时来
#: 报告问题。
START_WAIT_S = 5.0

#: 每个异步用例的硬上界。超过它是「实现挂住」，不是某条断言不成立。
HARD_BOUND_S = 20.0


# --------------------------------------------------------------------------
# 环境
# --------------------------------------------------------------------------


class Env:
    def __init__(self, books_dir: Path) -> None:
        self.books_dir = books_dir
        self.order: List[str] = []
        self.started = threading.Event()
        #: 阻塞结束那一刻的 order 快照（见文件头）。
        self.snapshot_at_unblock: List[List[str]] = []

    def blocking(self, result: Any) -> Callable[..., Any]:
        """造一个同步阻塞的假重活：置起跑标志 → 占住 CPU → 拍快照 → 返回 result。"""

        def _work(*_args: Any, **_kwargs: Any) -> Any:
            self.started.set()
            time.sleep(BLOCK_S)
            self.snapshot_at_unblock.append(list(self.order))
            return result

        return _work


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    books_dir = tmp_path / "books"
    (books_dir / BOOK_ID).mkdir(parents=True)
    # list_book_ids() 只要求 book.pkl 存在；本文件没有任何用例真的去反序列化它。
    (books_dir / BOOK_ID / "book.pkl").write_bytes(b"never-unpickled-by-this-file")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))

    resolver = BookUuidResolver(books_dir=str(books_dir))
    # 预置映射，folder_for_book_uuid() 因此不会走 scan()。
    resolver._uuid_to_folder[BOOK_UUID] = BOOK_ID
    resolver._folder_to_uuid[BOOK_ID] = BOOK_UUID
    monkeypatch.setattr(server, "book_uuid_resolver", resolver)

    monkeypatch.delenv("READER3_TOKEN", raising=False)
    monkeypatch.delenv("READER3_ALLOWED_HOSTS", raising=False)

    # 捕获真身：有用例会把 `server.load_book_cached` 换成假件，而本 fixture 的
    # 收尾跑在 monkeypatch 撤销**之前**，直接按名字取会取到那个没有 cache_clear
    # 的假件。
    real_load_book_cached = server.load_book_cached
    real_load_book_cached.cache_clear()
    try:
        yield Env(books_dir)
    finally:
        real_load_book_cached.cache_clear()


@contextlib.asynccontextmanager
async def _client():
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        yield client


def _run(coro_factory) -> Any:
    """跑一个异步用例并给它硬上界。超时 = 实现挂住，不是断言不成立。"""

    async def bounded():
        return await asyncio.wait_for(coro_factory(), timeout=HARD_BOUND_S)

    return asyncio.run(bounded())


async def _race_health(env: Env, fire) -> tuple[httpx.Response, httpx.Response]:
    """并发发起「重活请求」与 `/api/health`，返回 (重活响应, health 响应)。

    health 一侧先等重活**确实进入阻塞**再发，否则在阻塞版本里它可能抢跑，测试
    就会以「碰巧先答」的方式假绿。
    """
    async with _client() as client:

        async def heavy() -> httpx.Response:
            resp = await fire(client)
            env.order.append("heavy")
            return resp

        async def health() -> httpx.Response:
            deadline = time.monotonic() + START_WAIT_S
            while not env.started.is_set() and time.monotonic() < deadline:
                await asyncio.sleep(0.005)
            resp = await client.get("/api/health")
            env.order.append("health")
            return resp

        return await asyncio.gather(heavy(), health())


def _assert_health_won(env: Env, heavy_resp: httpx.Response, health_resp: httpx.Response) -> None:
    assert heavy_resp.status_code == 200, heavy_resp.text
    assert health_resp.status_code == 200, health_resp.text
    assert health_resp.json()["status"] == "ok"
    assert env.started.is_set(), "假重活从未被调用——路由或 monkeypatch 接错了"
    assert env.order[0] == "health", (
        f"/api/health 被重活挡住了：完成顺序是 {env.order}。"
        " 重活仍然跑在事件循环线程上。"
    )
    assert env.snapshot_at_unblock == [["health"]], (
        f"重活结束时 order 快照是 {env.snapshot_at_unblock}，期望 [['health']]。"
        " health 在重活占住 CPU 的那段时间里根本没能跑。"
    )


# --------------------------------------------------------------------------
# T1 —— 承重：索引进行中，/api/health 仍然应答
# --------------------------------------------------------------------------

INDEX_STATUS_PAYLOAD = {
    "book_id": BOOK_ID,
    "indexed": True,
    "chunk_count": 41,
    "model": "paraphrase-multilingual-MiniLM-L12-v2",
    "message": "Indexed 41 chunks",
}


def _install_fake_index(env: Env, monkeypatch: pytest.MonkeyPatch, *, block: str) -> None:
    """换掉 `server.BookVectorIndex`：不加载任何真实 embedding 模型。

    block="index_book" 时 index_book 阻塞、status() 秒回，block="status" 反之。
    """

    blocking_call = env.blocking(INDEX_STATUS_PAYLOAD)

    class FakeIndex:
        def __init__(self, book_id: str, books_dir: str = "") -> None:
            self.book_id = book_id
            self.books_dir = books_dir

        def index_book(self, force_reindex: bool = False) -> dict:
            if block == "index_book":
                return blocking_call()
            return INDEX_STATUS_PAYLOAD

        def status(self) -> dict:
            if block == "status":
                return blocking_call()
            return INDEX_STATUS_PAYLOAD

    monkeypatch.setattr(server, "BookVectorIndex", FakeIndex)


def test_T1_索引进行中_health_仍然应答(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """承重断言：`POST /api/index/{book}` 跑满 200ms 期间，`/api/health` 照样答。"""
    _install_fake_index(env, monkeypatch, block="index_book")

    async def fire(client: httpx.AsyncClient) -> httpx.Response:
        return await client.post(f"/api/index/{BOOK_ID}", json={"force_reindex": False})

    heavy_resp, health_resp = _run(lambda: _race_health(env, fire))

    _assert_health_won(env, heavy_resp, health_resp)
    # 长请求仍然同步返回索引结果（不改成后台作业）。
    assert heavy_resp.json() == INDEX_STATUS_PAYLOAD


# --------------------------------------------------------------------------
# T2 —— 库搜索进行中，/api/health 仍然应答
# --------------------------------------------------------------------------

LIBRARY_HIT = SearchResult(
    book_id=BOOK_ID,
    book_title="Loop Block Sample",
    book_author="A. Tester",
    chapter_title="Chapter One",
    chapter_order=0,
    occurrence_index=0,
    match_text="needle",
    context_before="a ",
    context_after=" in the haystack",
    position=2,
    relevance_score=0.5,
    match_explanation=None,
    mode="keyword",
)


def _library_result_set() -> SearchResultSet:
    query = SearchQuery(term="needle", mode=SearchMode.KEYWORD, scope=SearchScope.ALL_BOOKS)
    return SearchResultSet(
        query=query,
        results=[LIBRARY_HIT],
        total_matches=1,
        searched_books=1,
        failed_books=[],
        unindexed_books=[],
        is_truncated=False,
        execution_time_ms=12.5,
        grouped_by_book={BOOK_ID: [LIBRARY_HIT]},
        index_status_by_book={BOOK_ID: "keyword"},
    )


def _book_result_set() -> SearchResultSet:
    query = SearchQuery(
        term="needle",
        mode=SearchMode.KEYWORD,
        scope=SearchScope.CURRENT_BOOK,
        max_results=1000,
        book_id=BOOK_ID,
    )
    return SearchResultSet(
        query=query,
        results=[LIBRARY_HIT],
        total_matches=1,
        searched_books=1,
        execution_time_ms=7.5,
    )


def test_T2_库搜索进行中_health_仍然应答(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "search_library", env.blocking((_library_result_set(), [BOOK_ID])))

    async def fire(client: httpx.AsyncClient) -> httpx.Response:
        return await client.get("/api/search/library", params={"q": "needle"})

    heavy_resp, health_resp = _run(lambda: _race_health(env, fire))

    _assert_health_won(env, heavy_resp, health_resp)
    assert heavy_resp.json()["total_matches"] == 1


def test_T2b_书内搜索进行中_health_仍然应答(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "search_book", env.blocking(_book_result_set()))

    async def fire(client: httpx.AsyncClient) -> httpx.Response:
        return await client.get(f"/api/search/{BOOK_ID}", params={"q": "needle"})

    heavy_resp, health_resp = _run(lambda: _race_health(env, fire))

    _assert_health_won(env, heavy_resp, health_resp)
    assert heavy_resp.json()["total_matches"] == 1


def test_T2c_索引查看进行中_health_仍然应答(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_index(env, monkeypatch, block="status")

    async def fire(client: httpx.AsyncClient) -> httpx.Response:
        return await client.get(f"/api/index/{BOOK_ID}/status")

    heavy_resp, health_resp = _run(lambda: _race_health(env, fire))

    _assert_health_won(env, heavy_resp, health_resp)
    assert heavy_resp.json() == INDEX_STATUS_PAYLOAD


def test_T2d_RAG检索进行中_health_仍然应答(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """C7 的第一组：`POST /api/ai/rag/retrieve` 里的 `retrieve_passages`。

    这条路由不碰 provider，是三组 C7 里唯一能单独钉住的一组。
    """
    monkeypatch.setattr(server, "retrieve_passages", env.blocking(([], 3.25)))

    async def fire(client: httpx.AsyncClient) -> httpx.Response:
        return await client.post(
            "/api/ai/rag/retrieve",
            json={"book_uuid": BOOK_UUID, "query": "needle", "k": 4, "min_similarity": 0.35},
        )

    heavy_resp, health_resp = _run(lambda: _race_health(env, fire))

    _assert_health_won(env, heavy_resp, health_resp)
    assert heavy_resp.json() == {"passages": [], "retrieval_time_ms": 3.25}


# --------------------------------------------------------------------------
# T3 —— 四处 handler 的返回值与改动前逐字一致（回归保护）
# --------------------------------------------------------------------------

EXPECTED_LIBRARY_RESPONSE = {
    "query": {"term": "needle", "mode": "keyword", "scope": "all_books"},
    "results": [LIBRARY_HIT.__dict__],
    "grouped_by_book": {BOOK_ID: [LIBRARY_HIT.__dict__]},
    "book_order": [BOOK_ID],
    "book_metadata": {
        BOOK_ID: {"book_id": BOOK_ID, "title": "Loop Block Sample", "author": "A. Tester"}
    },
    "index_status_by_book": {BOOK_ID: "keyword"},
    "total_matches": 1,
    "searched_books": 1,
    "failed_books": [],
    "unindexed_books": [],
    "is_truncated": False,
    "execution_time_ms": 12.5,
    "status_message": "Found 1 results across 1 books",
}

EXPECTED_BOOK_SEARCH_RESPONSE = {
    "query": {
        "term": "needle",
        "mode": "keyword",
        "scope": "current_book",
        "case_sensitive": False,
        "max_results": 1000,
        "book_id": BOOK_ID,
    },
    "results": [LIBRARY_HIT.__dict__],
    "total_matches": 1,
    "searched_books": 1,
    "failed_books": [],
    "unindexed_books": [],
    "is_truncated": False,
    "execution_time_ms": 7.5,
    "status_message": "Found 1 results",
}


def test_T3_库搜索响应结构逐字不变(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "search_library", lambda *a, **kw: (_library_result_set(), [BOOK_ID]))

    async def scenario():
        async with _client() as client:
            return await client.get("/api/search/library", params={"q": "needle"})

    resp = _run(scenario)
    assert resp.status_code == 200
    assert resp.json() == EXPECTED_LIBRARY_RESPONSE


def test_T3_书内搜索响应结构逐字不变(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "search_book", lambda *a, **kw: _book_result_set())

    async def scenario():
        async with _client() as client:
            return await client.get(f"/api/search/{BOOK_ID}", params={"q": "needle"})

    resp = _run(scenario)
    assert resp.status_code == 200
    assert resp.json() == EXPECTED_BOOK_SEARCH_RESPONSE


def test_T3_索引与索引查看响应结构逐字不变(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_index(env, monkeypatch, block="none")

    async def scenario():
        async with _client() as client:
            posted = await client.post(f"/api/index/{BOOK_ID}", json={"force_reindex": True})
            got = await client.get(f"/api/index/{BOOK_ID}/status")
            return posted, got

    posted, got = _run(scenario)
    assert posted.status_code == 200
    assert posted.json() == INDEX_STATUS_PAYLOAD
    assert got.status_code == 200
    assert got.json() == INDEX_STATUS_PAYLOAD


def test_T3_索引失败仍然转译成_400_和_500(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """异常转译也是「返回值」的一部分：搬进线程池不许把它搬丢。"""

    class ExplodingIndex:
        mode = "runtime"

        def __init__(self, book_id: str, books_dir: str = "") -> None:
            pass

        def index_book(self, force_reindex: bool = False) -> dict:
            if ExplodingIndex.mode == "runtime":
                raise RuntimeError("index unavailable")
            raise ValueError("something else broke")

        def status(self) -> dict:
            if ExplodingIndex.mode == "runtime":
                raise RuntimeError("index unavailable")
            raise ValueError("something else broke")

    monkeypatch.setattr(server, "BookVectorIndex", ExplodingIndex)

    async def scenario():
        async with _client() as client:
            ExplodingIndex.mode = "runtime"
            post_400 = await client.post(f"/api/index/{BOOK_ID}", json={"force_reindex": False})
            get_400 = await client.get(f"/api/index/{BOOK_ID}/status")
            ExplodingIndex.mode = "other"
            post_500 = await client.post(f"/api/index/{BOOK_ID}", json={"force_reindex": False})
            get_500 = await client.get(f"/api/index/{BOOK_ID}/status")
            return post_400, get_400, post_500, get_500

    post_400, get_400, post_500, get_500 = _run(scenario)
    assert post_400.status_code == 400 and post_400.json()["detail"] == "index unavailable"
    assert get_400.status_code == 400 and get_400.json()["detail"] == "index unavailable"
    assert post_500.status_code == 500 and post_500.json()["detail"] == "something else broke"
    assert get_500.status_code == 500 and get_500.json()["detail"] == "something else broke"


def test_T3_库搜索的坏参数仍然是_400(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    def must_not_run(*_a: Any, **_kw: Any):
        raise AssertionError("参数校验必须发生在重活之前")

    monkeypatch.setattr(server, "search_library", must_not_run)

    async def scenario():
        async with _client() as client:
            bad_mode = await client.get("/api/search/library", params={"q": "x", "mode": "nope"})
            bad_sort = await client.get("/api/search/library", params={"q": "x", "sort_by": "nope"})
            return bad_mode, bad_sort

    bad_mode, bad_sort = _run(scenario)
    assert bad_mode.status_code == 400
    assert bad_sort.status_code == 400


# --------------------------------------------------------------------------
# T2e / T2f —— C7 的第三组（非流式问答）里的检索与整本反序列化
#
# 这两条是**变异扫描发现的洞**：M6/M7 两条变异（撤掉 question 分支的
# `retrieve_passages` / `load_book_cached` 的 threadpool）一条测试都没红，
# 说明 C7 的另外两组当时没有任何断言盖住。补在这里，红是用变异复验的：
# 撤掉这两处的 threadpool，下面两条必红（见实施报告）。
# --------------------------------------------------------------------------


class _FakeProviderResponse:
    text = "answer body"
    token_count = 11
    model = "fake-model"
    finish_reason = "stop"


def _install_fake_ai(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """把非流式问答路径上除「被测那一处重活」以外的一切都换成瞬时假件。

    不碰真实 provider、不读真实 settings、不加载真实 book.pkl。
    `server.ai_queue` 换成新实例：它是模块级单例，队列字典按 key 常驻。
    """
    from reader3_app.ai.queue import AIRequestQueueManager

    monkeypatch.setattr(server, "ai_queue", AIRequestQueueManager(max_pending=10))
    monkeypatch.setattr(
        server,
        "_get_provider_runtime",
        lambda provider=None, model=None: ("anthropic", "fake-key", "", "fake-model", 10.0),
    )
    monkeypatch.setattr(server, "_call_provider", lambda *a, **kw: _FakeProviderResponse())
    monkeypatch.setattr(server, "book_token_stats", lambda book: (120, 60))
    monkeypatch.setattr(server, "build_full_book_context", lambda book, **kw: "CTX")
    monkeypatch.setattr(server, "build_multi_chapter_context", lambda book, **kw: ("CTX", [0]))


def _fire_question(client: httpx.AsyncClient) -> Any:
    return client.post(
        f"/api/ai/question/{BOOK_UUID}",
        params={"stream": "false"},
        json={"question": "who is the narrator?", "provider": "anthropic", "rag_k": 3},
    )


def test_T2e_问答里的RAG检索进行中_health_仍然应答(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_ai(env, monkeypatch)
    monkeypatch.setattr(server, "load_book_cached", lambda folder: object())
    monkeypatch.setattr(server, "retrieve_passages", env.blocking(([], 4.0)))

    heavy_resp, health_resp = _run(lambda: _race_health(env, _fire_question))

    _assert_health_won(env, heavy_resp, health_resp)
    assert heavy_resp.json()["answer"] == "answer body"


def test_T2f_整本反序列化进行中_health_仍然应答(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """`load_book_cached` 在缓存未命中时会 unpickle 整本书——同属重活。"""
    _install_fake_ai(env, monkeypatch)
    monkeypatch.setattr(server, "retrieve_passages", lambda *a, **kw: ([], 4.0))
    monkeypatch.setattr(server, "load_book_cached", env.blocking(object()))

    heavy_resp, health_resp = _run(lambda: _race_health(env, _fire_question))

    _assert_health_won(env, heavy_resp, health_resp)
    assert heavy_resp.json()["answer"] == "answer body"


def test_T2g_流式问答里的RAG检索进行中_health_仍然应答(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """C7 的第二组：`?stream=true` 分支在 SSE 开流**之前**那一段也是重活。

    这条同样是变异扫描补出来的（M6 当时一条都没红）。它只发请求、只断顺序，
    不碰 WI-21 那套租约栈的结构。
    """
    _install_fake_ai(env, monkeypatch)
    monkeypatch.setattr(server, "load_book_cached", lambda folder: object())
    monkeypatch.setattr(server, "retrieve_passages", env.blocking(([], 4.0)))

    def fire(client: httpx.AsyncClient) -> Any:
        return client.post(
            f"/api/ai/question/{BOOK_UUID}",
            params={"stream": "true"},
            json={"question": "who is the narrator?", "provider": "anthropic", "rag_k": 3},
        )

    heavy_resp, health_resp = _run(lambda: _race_health(env, fire))

    _assert_health_won(env, heavy_resp, health_resp)
    assert "answer body" in heavy_resp.text


# --------------------------------------------------------------------------
# T2h / T2i / T2j —— 书籍分词与上下文构造（C7 的另外三个函数）
#
# 这三条同样是变异扫描逼出来的：M9（把 3 处 `book_token_stats` 与 3 处
# `build_full_book_context` 的 threadpool 全撤掉）曾经一条都没红。
#
# 手法与 T2f 逐字相同——`book_token_stats` / `build_full_book_context` /
# `build_multi_chapter_context` 都是 `server` 的模块级名字，`run_in_threadpool`
# 之后仍在调用点从模块 global 查名，monkeypatch 照样生效。阻塞的是假件，不是
# 真的分词，unit lane 不会因此变成重活。
#
# 分支要逼准：`choose_routing` 是真货，用真的 `provider_context_window` 算出
# ctx 再喂进去，让 routing 落到 full_book / multi_chapter，别让被测函数根本没被
# 调到还一路绿（`_assert_health_won` 里的 `env.started.is_set()` 会挡住这种情况，
# 响应里的 routing.mode 再钉一道）。
# --------------------------------------------------------------------------

#: `_install_fake_ai` 固定用 anthropic + "fake-model"，这里用同一对参数问真值。
_CTX = server.provider_context_window("anthropic", "fake-model")


def _install_fast_upstream(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """把「目标之前的那几处重活」全换成瞬时假件，只留目标一个阻塞点。"""
    monkeypatch.setattr(server, "load_book_cached", lambda folder: object())
    monkeypatch.setattr(server, "retrieve_passages", lambda *a, **kw: ([], 4.0))


def test_T2h_书籍分词进行中_health_仍然应答(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_ai(env, monkeypatch)
    _install_fast_upstream(env, monkeypatch)
    monkeypatch.setattr(server, "book_token_stats", env.blocking((120, 60)))

    heavy_resp, health_resp = _run(lambda: _race_health(env, _fire_question))

    _assert_health_won(env, heavy_resp, health_resp)
    assert heavy_resp.json()["answer"] == "answer body"


def test_T2i_全书上下文构造进行中_health_仍然应答(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_ai(env, monkeypatch)
    _install_fast_upstream(env, monkeypatch)
    # book_tokens < ctx*0.5 → 真 choose_routing 判 full_book，才会走到被测函数。
    monkeypatch.setattr(server, "book_token_stats", lambda book: (120, 60))
    monkeypatch.setattr(server, "build_full_book_context", env.blocking("CTX"))

    heavy_resp, health_resp = _run(lambda: _race_health(env, _fire_question))

    _assert_health_won(env, heavy_resp, health_resp)
    assert heavy_resp.json()["metadata"]["routing"]["mode"] == "full_book"


def test_T2j_多章上下文构造进行中_health_仍然应答(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_ai(env, monkeypatch)
    _install_fast_upstream(env, monkeypatch)
    # book_tokens >= ctx*0.5 且 max_chapter < ctx*0.3 → 真 choose_routing 判 multi_chapter。
    monkeypatch.setattr(server, "book_token_stats", lambda book: (_CTX, int(_CTX * 0.1)))
    monkeypatch.setattr(server, "build_multi_chapter_context", env.blocking(("CTX", [0, 1])))

    heavy_resp, health_resp = _run(lambda: _race_health(env, _fire_question))

    _assert_health_won(env, heavy_resp, health_resp)
    assert heavy_resp.json()["metadata"]["routing"]["mode"] == "multi_chapter"
    assert heavy_resp.json()["metadata"]["routing"]["chapters"] == [0, 1]


# --------------------------------------------------------------------------
# T2k / T2l —— 另外两组（总结、流式问答）上的同三处重活
#
# 逐组变异（M9a/M9b/M10a/M10b）证明 T2h–T2j 只钉住了**非流式问答**那一组：
# 同样的三个函数在 `/api/ai/summary` 与 `?stream=true` 两组里各有一份拷贝，
# 撤掉它们的 threadpool 曾经一条都不红。三组是复制粘贴出来的三份代码，任何
# 一份漏包都是同一个 bug 的完整复发，所以三组都要有自己的断言。
# --------------------------------------------------------------------------

_HEAVY_TARGETS = (
    "load_book_cached",
    "retrieve_passages",
    "book_token_stats",
    "build_full_book_context",
    "build_multi_chapter_context",
)


def _install_blocking_target(env: Env, monkeypatch: pytest.MonkeyPatch, target: str) -> None:
    """只让 `target` 阻塞，并把 routing 逼到会调到它的那条分支上。"""
    if target == "load_book_cached":
        monkeypatch.setattr(server, "load_book_cached", env.blocking(object()))
    elif target == "retrieve_passages":
        monkeypatch.setattr(server, "retrieve_passages", env.blocking(([], 4.0)))
    elif target == "book_token_stats":
        monkeypatch.setattr(server, "book_token_stats", env.blocking((120, 60)))
    elif target == "build_full_book_context":
        # book_tokens < ctx*0.5 → full_book
        monkeypatch.setattr(server, "book_token_stats", lambda book: (120, 60))
        monkeypatch.setattr(server, "build_full_book_context", env.blocking("CTX"))
    elif target == "build_multi_chapter_context":
        # book_tokens >= ctx*0.5 且 max_chapter < ctx*0.3 → multi_chapter
        monkeypatch.setattr(server, "book_token_stats", lambda book: (_CTX, int(_CTX * 0.1)))
        monkeypatch.setattr(server, "build_multi_chapter_context", env.blocking(("CTX", [0, 1])))
    else:  # pragma: no cover - 参数写错时立刻炸，别静默少测一处
        raise AssertionError(f"unknown target {target}")


@pytest.mark.parametrize("target", _HEAVY_TARGETS)
def test_T2k_总结路径上的重活不占事件循环(env: Env, monkeypatch: pytest.MonkeyPatch, target: str) -> None:
    _install_fake_ai(env, monkeypatch)
    _install_fast_upstream(env, monkeypatch)
    _install_blocking_target(env, monkeypatch, target)

    def fire(client: httpx.AsyncClient) -> Any:
        return client.post(
            f"/api/ai/summary/{BOOK_UUID}",
            params={"summary_type": "full"},
            json={"provider": "anthropic", "max_tokens": 200},
        )

    heavy_resp, health_resp = _run(lambda: _race_health(env, fire))

    _assert_health_won(env, heavy_resp, health_resp)
    assert heavy_resp.json()["book_uuid"] == BOOK_UUID


@pytest.mark.parametrize("target", _HEAVY_TARGETS)
def test_T2l_流式问答路径上的重活不占事件循环(env: Env, monkeypatch: pytest.MonkeyPatch, target: str) -> None:
    _install_fake_ai(env, monkeypatch)
    _install_fast_upstream(env, monkeypatch)
    _install_blocking_target(env, monkeypatch, target)

    def fire(client: httpx.AsyncClient) -> Any:
        return client.post(
            f"/api/ai/question/{BOOK_UUID}",
            params={"stream": "true"},
            json={"question": "who is the narrator?", "provider": "anthropic", "rag_k": 3},
        )

    heavy_resp, health_resp = _run(lambda: _race_health(env, fire))

    _assert_health_won(env, heavy_resp, health_resp)
    assert "answer body" in heavy_resp.text
