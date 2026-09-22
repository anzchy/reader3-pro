"""WI-30 — ``server.py`` 的两处出网点必须走 WI-11 那道闸。

WI-11 把五家 provider 的出网收进了 ``ai/providers/_http.post_json``，闸就装在那一处：
**scheme 白名单**（``ALLOWED_SCHEMES``）＋ **不跟随 30x 的 opener**（``_NoRedirectHandler``）。
``server.py`` 有两处留在闸外，直接 ``urllib.request.urlopen``：

1. ``_http_get_json`` —— ollama 探活/列模型，URL 来自 ``PUT /api/settings`` 可编辑的 ``base_url``；
2. ``api_ai_question`` 里嵌套的 ``worker_ollama`` —— 流式 ``/api/chat``，URL 同源。

于是 ``ai/74``（已标 fixed(WI-11)）那个洞在这两处仍然开着：``file://`` 让 urlopen 读本机文件、
把内容顺着响应路径回传给浏览器。``except Exception`` 只把**抛出来**的那条路径转成
``{"error": ...}``，成功读到文件的那条路径它一个字都拦不住——所以本模块的 load-bearing 断言
是「**目标文件的内容没有出现在任何返回值或异常消息里**」，不是「抛了 ValueError」。
只断异常类型的话，一个「先读文件再抛」的实现会全绿。

流式那一口**不能**用 ``post_json`` 顶替：``post_json`` 把整个 body 读完才返回，
拿它替 ``worker_ollama`` 会把流式退化成阻塞，顺手毁掉 WI-21/WI-22 钉住的两条性质。
所以 W4 单独钉「response 在 body 读完之前就已经交到调用方手里」。

隔离：本模块**不发任何真实网络请求**。三道围栏，故意冗余——
``_cwd`` 把相对路径关进 tmp_path；``_no_real_sockets`` 让 urllib 底下的 socket 直接抛；
需要走完整条 handler 链的用例patch ``AbstractHTTPHandler.do_open``（即 ``_NoRedirectHandler``
**下面**那一层），这样判断跟不跟随 30x 的是真的处理器链，不是 mock。

断言档位（见 tests/unit/conftest.py）：L2 返回值，L3 出网调用的可观察终态。
"""

from __future__ import annotations

import asyncio
import email.message
import json
import socket
import urllib.request
from pathlib import Path
from typing import Any, List

import pytest

#: 够独特，在任何字符串里出现都是实锤而不是巧合。
SECRET = "S3CR3T-OLLAMA-VALUE-MUST-NOT-LEAK"


def load_http():
    """在用例**内部**导入，不在模块顶层。

    顶层 ``from ... import _http`` 在被测符号还不存在时会把红跑成 pytest **collection
    error**：零条用例执行，据此录下的红收据证明不了任何断言被求值过。
    """
    from reader3_app.ai.providers import _http

    return _http


def require(name: str):
    """取出 ``_http`` 上的新出网口；不存在时以 **AssertionError** 报红。

    ``getattr`` 直接失败会抛 AttributeError，那是「模块坏了」的形状，与「规格没被满足」
    在收据里是两回事。这里把它翻译成一条计数得到的断言失败。
    """
    _http = load_http()
    fn = getattr(_http, name, None)
    assert fn is not None, (
        f"ai/providers/_http.{name} 还不存在：server.py 的出网点没有可复用的闸口，"
        "只能继续直接 urlopen"
    )
    return fn


# --------------------------------------------------------------------------
# 围栏
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """任何被诱发的相对路径都落在 tmp_path，绝不落进仓库或真实 books/、config/。"""
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _no_real_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    """本模块任何一条用例都不许开 TCP 连接。

    ``socket.create_connection`` 在 import 时就被 ``http.client.HTTPConnection`` 抓成了
    类属性，patch 模块级名字会漏掉它；``socket.socket.connect`` 每条路径都要经过。
    """

    def _boom(*args: Any, **kwargs: Any):
        raise AssertionError("本模块的某条用例试图打开真实 socket")

    monkeypatch.setattr(socket.socket, "connect", _boom)


@pytest.fixture
def leak_root(tmp_path: Path) -> Path:
    """一棵**能被拼接命中**的假目录树，装的是合法 JSON。

    靶子不能只是 ``secret.json``：``api_ollama_status`` 拼的是 ``root + "/api/version"``，
    如果 root 指向一个文件，拼出来的路径根本不存在，urlopen 会抛 FileNotFoundError——
    那样这条用例就算没有白名单也是绿的，钉不住任何东西。所以按 ollama 的真实路径形状
    造 ``leak/api/version``，让「没有白名单」这件事真的能把内容读出来。
    """
    root = tmp_path / "leak"
    (root / "api").mkdir(parents=True)
    (root / "api" / "version").write_text(json.dumps({"version": SECRET}), encoding="utf-8")
    (root / "api" / "chat").write_text(
        json.dumps({"model": "m", "message": {"content": SECRET}, "done": True}) + "\n",
        encoding="utf-8",
    )
    (root / "secret.json").write_text(json.dumps({"api_key": SECRET}), encoding="utf-8")
    return root


# --------------------------------------------------------------------------
# 假响应
# --------------------------------------------------------------------------


class _FakeResponse:
    """够 urllib 的 processor 链用的 ``http.client.HTTPResponse``。"""

    def __init__(self, *, code: int = 200, body: bytes = b"{}", headers: dict[str, str] | None = None):
        self.code = code
        self.status = code
        self.msg = "Fake"
        self.reason = "Fake"
        self._body = body
        self._headers = email.message.Message()
        for k, v in (headers or {}).items():
            self._headers[k] = v
        self.url = "http://fake.invalid/"

    def info(self) -> email.message.Message:
        return self._headers

    @property
    def headers(self) -> email.message.Message:
        return self._headers

    def read(self, *_a: Any) -> bytes:
        return self._body

    def close(self) -> None:
        return None

    def geturl(self) -> str:
        return self.url

    def getcode(self) -> int:
        return self.code

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_a: Any) -> bool:
        return False


class _LazyStreamResponse(_FakeResponse):
    """逐行发的响应：``read()`` 一旦被调用就留下痕迹。

    这就是 W4 的量具。「流式」在这里的可判定形式是：调用方拿到 response 的那一刻，
    body 还没被读完——``read_called is False`` 且 ``remaining() > 0``。
    """

    def __init__(self, lines: List[bytes]):
        super().__init__(code=200, body=b"".join(lines))
        self._lines = list(lines)
        self.served = 0
        self.read_called = False
        self.closed = False

    def readline(self, *_a: Any) -> bytes:
        if self.served >= len(self._lines):
            return b""
        line = self._lines[self.served]
        self.served += 1
        return line

    def read(self, *_a: Any) -> bytes:
        self.read_called = True
        rest = b"".join(self._lines[self.served :])
        self.served = len(self._lines)
        return rest

    def remaining(self) -> int:
        return len(self._lines) - self.served

    def close(self) -> None:
        self.closed = True

    def __exit__(self, *_a: Any) -> bool:
        self.close()
        return False


def _fence_the_handler_chain(monkeypatch: pytest.MonkeyPatch, response_factory) -> List[str]:
    """把 ``do_open``（``_NoRedirectHandler`` 正**下面**那一层）换掉，返回请求日志。

    patch ``build_opener`` 就只测到 mock 自己了；patch 到这一层，30x 跟不跟随
    仍然由真实的处理器链决定。``getproxies`` 一并清空——开发机上设了 http_proxy
    的话，ProxyHandler 会把日志里的 URL 改掉。
    """
    log: List[str] = []

    def fake_do_open(self: Any, http_class: Any, req: Any, **kwargs: Any):
        log.append(req.full_url)
        return response_factory(req)

    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})
    monkeypatch.setattr(urllib.request.AbstractHTTPHandler, "do_open", fake_do_open)
    return log


# --------------------------------------------------------------------------
# W1 —— file:// 在出网前被拒，且文件内容一个字都没读出来。 L3 / S2
# --------------------------------------------------------------------------


def test_w1_get_json_拒掉_file_url_且不泄漏文件内容(leak_root: Path) -> None:
    """load-bearing：断的是**内容没出来**，不只是抛了异常。

    一个「先 urlopen 读到内容、再因为别的原因抛」的实现能骗过 ``pytest.raises``，
    骗不过下面这两条——返回值必须压根不存在，异常消息里也不许带上文件内容。
    """
    get_json = require("get_json")
    url = f"file://{leak_root}/secret.json"

    returned: Any = None
    raised: BaseException | None = None
    try:
        returned = get_json(url, timeout_s=2)
    except BaseException as e:  # noqa: BLE001 - 类型在下面无条件断言
        raised = e

    assert SECRET not in repr(returned), f"get_json 把本地文件的内容读出来了：{returned!r}"
    assert SECRET not in str(raised), f"文件内容顺着异常消息漏了出来：{raised}"
    assert returned is None, f"get_json 对 file:// 返回了 {returned!r} 而不是拒绝"
    assert isinstance(raised, ValueError), f"get_json 抛的是 {raised!r}，不是 ValueError"
    assert url in str(raised), f"错误消息没写清楚被拒的是哪个 URL：{raised}"


def test_w1_post_stream_拒掉_file_url_且不泄漏文件内容(leak_root: Path) -> None:
    """流式那一口同样在闸内。``file://`` 对 POST 一样有效：urllib 的 FileHandler
    根本不看 data，照样把文件交回来。"""
    post_stream = require("post_stream")
    url = f"file://{leak_root}/secret.json"

    leaked: Any = None
    raised: BaseException | None = None
    try:
        with post_stream(url, payload={"model": "m"}, timeout_s=2) as resp:
            leaked = resp.read()
    except BaseException as e:  # noqa: BLE001 - 类型在下面无条件断言
        raised = e

    assert SECRET not in repr(leaked), f"post_stream 把本地文件的内容读出来了：{leaked!r}"
    assert SECRET not in str(raised), f"文件内容顺着异常消息漏了出来：{raised}"
    assert leaked is None, f"post_stream 对 file:// 交出了 {leaked!r} 而不是拒绝"
    assert isinstance(raised, ValueError), f"post_stream 抛的是 {raised!r}，不是 ValueError"
    assert url in str(raised), f"错误消息没写清楚被拒的是哪个 URL：{raised}"


# --------------------------------------------------------------------------
# W2 —— 整条路：settings 里的 base_url → 路由响应。 L3 / S3
# --------------------------------------------------------------------------


def test_w2_ollama_status_整条路都不泄漏本地文件内容(
    leak_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``base_url`` 是用户经 ``PUT /api/settings`` 可编辑的，所以这条路从设置一直通到浏览器。

    只 patch ``load_ai_settings`` / ``get_provider_base_url`` 两个入口，路由体内的
    ``_ollama_root_base_url``、``_http_get_json`` 和 ``except Exception`` 全部按原样跑——
    要钉的正是「异常分支拦不住成功读到文件的那条路径」。

    2026-09-19（011 WI-4）：``api_ollama_status`` 搬到了 ``web/routers/settings.py``，
    所以调用点从 ``server.`` 改到 ``routers.settings.``。**两处 monkeypatch 仍然打在
    ``server`` 上，一个字没改**——这不是将就，这正是本次搬家要的结果：路由体里写的是
    ``_server.load_ai_settings(...)``，属性在调用时才解析，所以打在 server 上的桩照样
    生效。如果哪天这条测试要改 patch 目标才能绿，那说明接缝被旁路了，别改它，去看搬家。
    """
    from reader3_app.web import server
    from reader3_app.web.routers import settings as settings_router

    monkeypatch.setattr(server, "load_ai_settings", lambda *a, **kw: {})
    monkeypatch.setattr(server, "get_provider_base_url", lambda *a, **kw: f"file://{leak_root}")

    result = asyncio.run(settings_router.api_ollama_status())
    payload = json.dumps(result, ensure_ascii=False, default=str)

    assert SECRET not in payload, (
        f"GET /api/ollama/status 把本机文件的内容回给了浏览器：{payload}"
    )
    assert result["running"] is False, (
        f"一个 file:// 的 base_url 被当成了「ollama 正在运行」：{payload}"
    )


# --------------------------------------------------------------------------
# W3 —— 30x 不跟随。 L3 / S2
# --------------------------------------------------------------------------


def test_w3_get_json_不跟随_30x(monkeypatch: pytest.MonkeyPatch) -> None:
    """urllib 默认跟随重定向，并且跨 host 保留 ``Authorization``。
    白名单拦得住第一跳，拦不住第二跳，所以第二跳必须由处理器链拒掉。"""
    get_json = require("get_json")

    first = "http://first.invalid/api/version"
    second = "http://second.invalid/collect"

    log = _fence_the_handler_chain(
        monkeypatch,
        lambda req: _FakeResponse(code=302, body=b"", headers={"Location": second}),
    )

    raised: BaseException | None = None
    try:
        get_json(first, timeout_s=5)
    except BaseException as e:  # noqa: BLE001 - 下面无条件断言
        raised = e

    assert log == [first], f"302 被跟随了，实际发出的请求是 {log}"
    assert raised is not None, "get_json 在 302 上正常返回了，而不是拒绝跟随"


def test_w3_post_stream_不跟随_30x(monkeypatch: pytest.MonkeyPatch) -> None:
    post_stream = require("post_stream")

    first = "http://first.invalid/api/chat"
    second = "http://second.invalid/collect"

    log = _fence_the_handler_chain(
        monkeypatch,
        lambda req: _FakeResponse(code=302, body=b"", headers={"Location": second}),
    )

    raised: BaseException | None = None
    try:
        with post_stream(first, payload={"model": "m"}, timeout_s=5) as resp:
            resp.readline()
    except BaseException as e:  # noqa: BLE001 - 下面无条件断言
        raised = e

    assert log == [first], f"302 被跟随了，实际发出的请求是 {log}"
    assert raised is not None, "post_stream 在 302 上正常返回了，而不是拒绝跟随"


def test_w3_正常_200_两个口都仍然工作(monkeypatch: pytest.MonkeyPatch) -> None:
    """禁跟随不能是靠「把所有请求都弄坏」实现的。"""
    get_json = require("get_json")
    post_stream = require("post_stream")

    _fence_the_handler_chain(
        monkeypatch, lambda req: _FakeResponse(code=200, body=b'{"version": "0.1.0"}')
    )
    assert get_json("https://ok.invalid/api/version", timeout_s=5) == {"version": "0.1.0"}

    _fence_the_handler_chain(
        monkeypatch, lambda req: _LazyStreamResponse([b'{"done": true}\n'])
    )
    with post_stream("https://ok.invalid/api/chat", payload={"a": 1}, timeout_s=5) as resp:
        assert resp.readline() == b'{"done": true}\n'


# --------------------------------------------------------------------------
# W4 —— 流式口仍然是流式。 L3 / S2
# --------------------------------------------------------------------------


def test_w4_post_stream_在_body_读完之前就把_response_交出来(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """把 ``post_stream`` 换成 ``post_json``（读完整个 body 再交出）必须让这条变红。

    ``worker_ollama`` 逐行读 ollama 的 NDJSON，每读到一行就往 SSE 队列推一个 chunk，
    并且在每行**之前**检查 ``stop_event``。一个先把 body 读完的实现会让第一个 chunk
    等到整段回答生成完才出现，也让断连之后 worker 再也停不下来——即 WI-21/WI-22
    钉住的那两条性质。所以这里断的是**交出的时点**，不是交出的内容。
    """
    post_stream = require("post_stream")

    lines = [b'{"message": {"content": "a"}}\n', b'{"message": {"content": "b"}}\n', b'{"done": true}\n']
    stream = _LazyStreamResponse(lines)
    _fence_the_handler_chain(monkeypatch, lambda req: stream)

    cm = post_stream("http://ollama.invalid/api/chat", payload={"model": "m"}, timeout_s=5)
    assert hasattr(cm, "__enter__") and hasattr(cm, "__exit__"), (
        f"post_stream 没有交出一个上下文管理器，而是 {cm!r}；调用方无法在读完之前拿到 response"
    )

    with cm as resp:
        assert stream.read_called is False, (
            "post_stream 在把 response 交给调用方之前就 read() 了整个 body："
            "流式退化成了阻塞，第一个 chunk 要等整段回答生成完"
        )
        assert stream.remaining() == 3, f"body 在交出前已经被消费了 {3 - stream.remaining()} 行"

        first = resp.readline()
        assert first == lines[0], f"逐行读拿到的第一行是 {first!r}"
        assert stream.remaining() == 2, "第一行读到的时候，后面两行还没被消费——这就是流式"

    assert stream.closed, "post_stream 出块时没有关掉 response"
