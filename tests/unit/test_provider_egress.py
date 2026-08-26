"""WI-11 — the provider egress surface: an arbitrary ``base_url`` must not be able
to walk off with the user's API key.

Four findings collapse into one story (`ai/74`, `ai/70`, `ai/75`, `web/C2`). The
half of it that lives below the HTTP boundary is specified here; the route half
is in ``tests/contract/test_provider_test_route.py``.

**No test in this module is allowed to touch the network.** Three fences enforce
that, and they are deliberately redundant because a single missed seam here bills
a real API key or leaks the developer's ``/etc/passwd`` into a test log:

1. ``_no_real_sockets`` (autouse) makes ``socket.socket.connect`` raise. Nothing
   below urllib can reach a host even if a test forgets to patch its own seam.
2. The cases that must prove "we never went out" patch ``urlopen`` *and*
   ``build_opener`` into one shared log, so a provider that still calls the old
   private ``_post_json`` is caught the same as one that calls the new shared one.
3. ``E3`` patches ``AbstractHTTPHandler.do_open`` — the seam directly *below* the
   redirect handler — precisely so the real handler chain is exercised. Patching
   ``build_opener`` there would have tested nothing but the mock.

Nothing here opens ``file:///etc/passwd``. The whole point of E1/E2 is that the
URL is rejected *before* any opener is constructed, so the assertion is about the
absence of a call, not about what the call returned.

Assertion levels (see tests/unit/conftest.py): L2 return value, L3 observable
end state of the outgoing call.
"""

from __future__ import annotations

import email.message
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

import pytest

from reader3_app.ai.providers.gemini import gemini_generate_content
from reader3_app.ai.providers.ollama import ollama_chat_completions
from reader3_app.ai.providers.openai import openai_chat_completions
from reader3_app.ai.providers.openrouter import openrouter_chat_completions

DEFAULT_FOR_TESTS = "https://api.example.test/v1"

#: Distinctive enough that finding it in a URL is unambiguous evidence, not a
#: coincidental substring.
SENTINEL_KEY = "SENTINEL-KEY"


def load_http():
    """Import the shared HTTP module *inside* the test, not at module scope.

    A module-level ``from ... import _http`` before the module exists turns the
    red run into a pytest **collection error**: zero tests run, and a receipt
    recorded off that proves no assertion was ever evaluated. Imported here, the
    absence shows up as a counted test failure, which is what a red is supposed
    to be.
    """
    from reader3_app.ai.providers import _http

    return _http


@pytest.fixture(autouse=True)
def _cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Any relative path a test provokes lands in tmp_path, never in the repo."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _no_real_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Last-ditch fence: no test in this module may open a TCP connection.

    ``socket.create_connection`` is captured as a class attribute by
    ``http.client.HTTPConnection`` at import time, so patching the module-level
    name would miss it. ``socket.socket.connect`` is reached by every path.
    """

    def _boom(*args: Any, **kwargs: Any):
        raise AssertionError("a test in this module tried to open a real socket")

    monkeypatch.setattr(socket.socket, "connect", _boom)


class _FakeResponse:
    """Enough of ``http.client.HTTPResponse`` for urllib's processor chain."""

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


def _trap_every_opener(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every attempt to leave the process, whichever seam it uses.

    Both ``urlopen`` (what the four duplicated ``_post_json`` bodies call today)
    and ``build_opener`` (what the shared one must call) feed one list, so this
    trap keeps working across the refactor instead of going quietly vacuous.
    """
    log: list[str] = []

    def fake_urlopen(req: Any, *a: Any, **kw: Any) -> _FakeResponse:
        log.append(getattr(req, "full_url", str(req)))
        return _FakeResponse()

    class _RecordingOpener:
        def open(self, req: Any, *a: Any, **kw: Any) -> _FakeResponse:
            log.append(getattr(req, "full_url", str(req)))
            return _FakeResponse()

    def fake_build_opener(*handlers: Any) -> _RecordingOpener:
        log.append("<build_opener>")
        return _RecordingOpener()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)
    return log


# --------------------------------------------------------------------------
# E1 — validated_url rejects scheme by scheme.  L2 / S1
# --------------------------------------------------------------------------

REJECTED = [
    "file:///etc/passwd",
    # A file: URL *with* a host. Added while implementing: deleting the scheme
    # whitelist left every other case above still caught by the no-host check,
    # so the guard this item exists for had no test that could see it go.
    "file://localhost/etc/passwd",
    "ftp://x/",
    "gopher://x",
    "javascript:alert(1)",
    "http://",
    "",
    "   ",
    "/relative",
]


@pytest.mark.parametrize("bad", REJECTED, ids=lambda s: repr(s))
def test_e1_validated_url_拒绝非_http_scheme(bad: str) -> None:
    """A rejection must name the value it rejected — a bare "invalid URL" leaves
    the user re-reading their settings file with no idea which field is wrong."""
    _http = load_http()
    with pytest.raises(ValueError) as excinfo:
        _http.validated_url(bad, default=DEFAULT_FOR_TESTS)
    assert repr(bad) in str(excinfo.value), (
        f"the ValueError for {bad!r} does not quote the rejected value: {excinfo.value}"
    )


ACCEPTED = [
    ("http://localhost:11434", "http://localhost:11434"),
    ("https://api.openai.com/v1", "https://api.openai.com/v1"),
    ("https://x.example:8443/v1/", "https://x.example:8443/v1"),
]


@pytest.mark.parametrize(("given", "expected"), ACCEPTED, ids=lambda s: str(s))
def test_e1_validated_url_放行_http_和_https(given: str, expected: str) -> None:
    _http = load_http()
    assert _http.validated_url(given, default=DEFAULT_FOR_TESTS) == expected


def test_e1_validated_url_缺省值只在_None_时生效() -> None:
    """``None`` means "the caller has nothing configured"; ``""`` means "the
    caller configured something empty", and those are not the same fact."""
    _http = load_http()
    assert _http.validated_url(None, default=DEFAULT_FOR_TESTS) == DEFAULT_FOR_TESTS


# --------------------------------------------------------------------------
# E2 — every provider goes through the gate.  L3 / S2
# --------------------------------------------------------------------------

COMMON = dict(model="m-1", system="sys", messages=[{"role": "user", "content": "hi"}], max_tokens=64, timeout_s=5)

# anthropic_messages is deliberately absent: it takes no ``base_url`` at all, so
# there is no request-controlled URL to gate. If it ever grows one, add it here.
GATED_PROVIDERS: list[tuple[str, Callable[..., Any]]] = [
    ("openai", lambda url: openai_chat_completions(api_key="k", base_url=url, **COMMON)),
    ("openrouter", lambda url: openrouter_chat_completions(api_key="k", base_url=url, **COMMON)),
    ("ollama", lambda url: ollama_chat_completions(base_url=url, **COMMON)),
    ("gemini", lambda url: gemini_generate_content(api_key="k", base_url=url, **COMMON)),
]


@pytest.mark.parametrize(("name", "call"), GATED_PROVIDERS, ids=[n for n, _ in GATED_PROVIDERS])
def test_e2_五家_provider_都在出网前拒掉_file_url(
    name: str, call: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The load-bearing assertion is the *empty log*, not the exception type.

    ``pytest.raises`` alone would stay green if the guard moved to after the
    request was sent, and it would go red for the wrong reason if the error type
    changed. Both assertions below run unconditionally.
    """
    log = _trap_every_opener(monkeypatch)

    raised: BaseException | None = None
    try:
        call("file:///etc/passwd")
    except BaseException as e:  # noqa: BLE001 - the type is asserted below, unconditionally
        raised = e

    assert log == [], f"{name} reached the network with a file:// base_url: {log}"
    assert isinstance(raised, ValueError), f"{name} raised {raised!r} instead of ValueError"
    assert "file:///etc/passwd" in str(raised), f"{name}'s error does not name the rejected URL: {raised}"


@pytest.mark.parametrize(("name", "call"), GATED_PROVIDERS, ids=[n for n, _ in GATED_PROVIDERS])
def test_e2_带_host_的_file_url_也在出网前被拒(
    name: str, call: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """``file://localhost/etc/passwd`` parses with a host, so only the scheme
    whitelist can stop it. Without this case the whitelist could be deleted and
    the whole module would stay green."""
    log = _trap_every_opener(monkeypatch)

    raised: BaseException | None = None
    try:
        call("file://localhost/etc/passwd")
    except BaseException as e:  # noqa: BLE001 - asserted unconditionally below
        raised = e

    assert log == [], f"{name} reached the network with a file:// base_url: {log}"
    assert isinstance(raised, ValueError), f"{name} raised {raised!r} instead of ValueError"


# --------------------------------------------------------------------------
# E3 — a 30x must not carry Authorization to a second hop.  L3 / S2
# --------------------------------------------------------------------------


def test_e3_重定向不会把_authorization_带到第二跳(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch below the redirect handler so the real chain decides.

    urllib follows redirects by default and (on this interpreter) keeps the
    ``Authorization`` header across hosts, so a "legitimate" endpoint can bounce
    the request — key attached — anywhere it likes.
    """
    _http = load_http()

    first = "http://first.invalid/v1/chat/completions"
    second = "http://second.invalid/collect"

    log: list[str] = []

    def fake_do_open(self: Any, http_class: Any, req: Any, **kwargs: Any) -> _FakeResponse:
        log.append(req.full_url)
        return _FakeResponse(code=302, body=b"", headers={"Location": second})

    # build_opener() constructs a ProxyHandler from the environment; a developer
    # with http_proxy set would otherwise see a different URL in the log.
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})
    monkeypatch.setattr(urllib.request.AbstractHTTPHandler, "do_open", fake_do_open)

    raised: BaseException | None = None
    try:
        _http.post_json(
            first,
            payload={"model": "m"},
            headers={"Authorization": f"Bearer {SENTINEL_KEY}"},
            timeout_s=5,
        )
    except BaseException as e:  # noqa: BLE001 - asserted unconditionally below
        raised = e

    assert log == [first], f"the 302 was followed: requests made were {log}"
    assert raised is not None, "post_json returned normally on a 302 instead of refusing it"


def test_e3_正常_200_仍然读得到响应体(monkeypatch: pytest.MonkeyPatch) -> None:
    """The redirect ban must not have been implemented by breaking every request."""
    _http = load_http()

    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})
    monkeypatch.setattr(
        urllib.request.AbstractHTTPHandler,
        "do_open",
        lambda self, http_class, req, **kw: _FakeResponse(code=200, body=b'{"ok": true}'),
    )

    status, body = _http.post_json(
        "https://ok.invalid/v1/chat/completions", payload={"a": 1}, headers={}, timeout_s=5
    )
    assert (status, body) == (200, {"ok": True})


def test_e3_http_错误码原样交回调用方而不是抛出(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each provider parses its own error body (their four shapes differ), so the
    shared POST must hand 4xx/5xx back rather than raising — otherwise WI-12's
    per-provider error parsing has nothing to parse."""
    _http = load_http()

    def raise_http_error(self: Any, http_class: Any, req: Any, **kw: Any):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many", email.message.Message(), None)

    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})
    monkeypatch.setattr(urllib.request.AbstractHTTPHandler, "do_open", raise_http_error)

    status, body = _http.post_json("https://ok.invalid/v1", payload={}, headers={}, timeout_s=5)
    assert status == 429
    assert isinstance(body, dict)


# --------------------------------------------------------------------------
# E4 — the Gemini key leaves the URL.  L3 / S2
# --------------------------------------------------------------------------


def test_e4_gemini_的_key_不进_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key in the query string is written to every access log on the path."""
    captured: dict[str, Any] = {}

    def fake_post_json(url: str, *, payload: Any, headers: Any, timeout_s: int):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        return 200, {"candidates": [{"content": {"parts": [{"text": "OK"}]}, "finishReason": "STOP"}]}

    from reader3_app.ai.providers import gemini

    monkeypatch.setattr(gemini, "post_json", fake_post_json)

    gemini.gemini_generate_content(
        api_key=SENTINEL_KEY,
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-1.5-pro",
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=64,
        timeout_s=5,
    )

    url = captured["url"]
    assert SENTINEL_KEY not in url, f"the API key is in the request URL: {url}"
    assert "key=" not in url, f"the request URL still carries a key query parameter: {url}"
    assert captured["headers"]["x-goog-api-key"] == SENTINEL_KEY


# --------------------------------------------------------------------------
# Extra — estimate_tokens moved, not changed.
# --------------------------------------------------------------------------


def test_estimate_tokens_按原样搬家() -> None:
    """The four copies were ``max(1, len(text) // 4)`` with 0 for empty. This
    pins that behaviour so the de-duplication is provably a *move*.

    Its CJK ratio is wrong (`ai/45`), and fixing it here is explicitly WI-24's
    job: mixing the fix in would make this item's mutation evidence unreadable.
    """
    _http = load_http()
    assert _http.estimate_tokens("") == 0
    assert _http.estimate_tokens("abcd") == 1
    assert _http.estimate_tokens("a") == 1
    assert _http.estimate_tokens("x" * 400) == 100
