"""WI-6（011）—— `max_retries` 从「能填、能存、能读回，但全仓没人用」变成真的会重试。

今天 `max_retries` 是一个**对用户撒谎的配置项**：设置页有输入框（`static/settings.js:155`，
min=0 max=10）、`PUT /api/settings` 存得下、`GET /api/settings` 读得回
（`web/server.py:729`）、`ai/config.py` 解析并 clamp 到 0..10——而 `grep -rn "max_retries" src/`
的每一处命中都是「存 / 读 / 渲染」，**没有一处是「用」**。用户把它填成 3，什么都不会发生。

ADR-0011（Phase 2 冻结）把「删掉它」这条路划掉了：它会从 `GET /api/settings` 读回，
删=改响应形状。所以只剩「接通」。

## 这份文件守的三件事，按重要性排序

1. **哪些错该重试、哪些不该**。R5（4xx 只调一次）与 R6（429/503 真的重试）刻意**分开写**：
   合成一条「重试一切」的实现能在只有 R6 的世界里蒙混过关，而它的代价是用户把 key 填错时
   要多等三轮退避才看到同一条「401」。
2. **`str(e)` 一个字节都不许变**。provider 的错误串会经
   `{"type": "error", "message": str(e)}` 进 SSE 流、经 `{"success": false, "message": str(e)}`
   进连通性自测的响应体——ADR-0011 冻结之下那是响应内容。R11/R13 直接断言这件事：
   `ProviderHTTPError` 必须是 `RuntimeError` 的子类（`routers/search.py:207` 那类
   `except RuntimeError` 分支要逐字保持原状），且 `str()` 与今天的裸 `RuntimeError` 全等。
   R4 从另一头钉同一件事：重试耗尽后抛的是**最后一次那个异常对象本身**，不是包一层。
3. **查配置这件事不许把 LLM 调用打挂**。R10：settings 读不出来（抛 `AiSettingsError`）时
   退化成 0 次重试，调用照常成功。

## 为什么重试落在 `server._call_provider` 上

它是 ADR-0006 说的全进程唯一 LLM 出口，6 个非流式调用点全部经过它。写进五家 provider
里 = 抄五份，那正是 `ai/providers/_http.py` 顶部 docstring 记着的、WI-11 刚收掉的毛病。

**流式路径不在这份文件的射程内**：ollama 的流式 chat 走 `_http.post_stream`，不经过
`_call_provider`，因此拿不到重试。这是有意的——SSE 已经把前半段正文推给客户端了，
重试会让用户看到重复的文本。它是一笔登记在案的欠账，不是这里的漏测。

## 打桩写法的两条约束（不是洁癖，是两道静态闸）

* `tests/unit/test_server_patch_seam_registry_complete.py` 的 B1 是
  **`set(found) == set(OWNERSHIP)` 的等式**：树里出现一处
  `monkeypatch.setattr(server, "<没登记的名字>", …)`，它当场红。所以这里对 server 上
  **没登记**的名字（`PROVIDER_RETRY_BASE_S` / `ollama_chat_completions` …）一律通过
  **参数形式的模块句柄**去 patch（`_set_retry_constants` / `_install_ollama_stub`），走的是该模块
  docstring 里写明的通道 3「目标解析不到 + 属性名不在 registry 上 → 静默」。这正是
  `test_provider_response_parsing.py:76` 打 `post_json` 用的同一种家法。
* 属性名一律写成**字面量**。通道 2（属性名是变量）会被报出来，且真树上今天是零处。
* `load_ai_settings` 是 registry 上的名字，所以 R9/R10 用最普通的
  `monkeypatch.setattr(server, "load_ai_settings", …)`，不绕。

不睡觉的办法是把 `PROVIDER_RETRY_BASE_S` / `PROVIDER_RETRY_CAP_S` 打成 0，**不另开
`sleep` 接缝**：server 上每多一个被打桩的名字就要动 WI-1 的注册表。观测退避秒数则打
`time.sleep` 自己（目标是 `time` 模块，不是 server，两道闸都看不见它）。

断言档位（见 tests/unit/conftest.py）：L2 返回值/调用序列，L4 故障注入。
"""

from __future__ import annotations

import importlib
import random
import time
import urllib.error
from pathlib import Path
from typing import Any, Dict, List

import pytest

from reader3_app.ai.config import AiSettingsError
from reader3_app.ai.providers import anthropic as anthropic_mod
from reader3_app.ai.providers import gemini as gemini_mod
from reader3_app.ai.providers import ollama as ollama_mod
from reader3_app.ai.providers import openai as openai_mod
from reader3_app.ai.providers import openrouter as openrouter_mod
from reader3_app.ai.providers._http import RedirectNotAllowed
from reader3_app.ai.providers.types import ProviderResponse
from reader3_app.web import server

#: 这个串只出现在这份文件里，所以在返回值里看见它就是证据，不是巧合。
ANSWER_SENTINEL = "RETRY-ANSWER-SENTINEL"

OLLAMA_BASE = "http://localhost:11434"


# ==========================================================================
# 夹具与小工具
# ==========================================================================


@pytest.fixture(autouse=True)
def _cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """任何相对路径（`config/ai_settings.json` 是其中之一）都落在 tmp_path 里。"""
    monkeypatch.chdir(tmp_path)


def _require(module: Any, attr: str) -> None:
    """`monkeypatch.setattr` 之前先断言名字在：名字还不存在时要的是一条**断言失败**，
    而不是 monkeypatch 自己抛的 AttributeError——后者读起来像「测试没跑起来」。
    """
    assert hasattr(module, attr), (
        f"{getattr(module, '__name__', module)} 上还没有 {attr!r}，这条用例要打的桩落空了"
    )


def _set_retry_constants(
    monkeypatch: pytest.MonkeyPatch, mod: Any, *, base: float, cap: float
) -> None:
    """把退避的两个常量打成给定值。

    `mod` 是**形参**，属性名是**字面量**——两件事都不是洁癖：
    WI-2 那把完整性锁对「属性名是变量」的打桩点会当场报出来（通道 2，真树上零处），
    而形参形式的模块句柄走通道 3，属性名不在 registry 上就静默。见模块 docstring。
    """
    _require(mod, "PROVIDER_RETRY_BASE_S")
    _require(mod, "PROVIDER_RETRY_CAP_S")
    monkeypatch.setattr(mod, "PROVIDER_RETRY_BASE_S", base)
    monkeypatch.setattr(mod, "PROVIDER_RETRY_CAP_S", cap)


def _install_ollama_stub(monkeypatch: pytest.MonkeyPatch, mod: Any, fake: Any) -> None:
    _require(mod, "ollama_chat_completions")
    monkeypatch.setattr(mod, "ollama_chat_completions", fake)


def _install_post_json_stub(monkeypatch: pytest.MonkeyPatch, mod: Any, fake: Any) -> None:
    _require(mod, "post_json")
    monkeypatch.setattr(mod, "post_json", fake)


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> List[float]:
    """记下每一次传给 `time.sleep` 的秒数；真睡一秒都不许。"""
    recorded: List[float] = []

    def _fake_sleep(seconds: float) -> None:
        recorded.append(float(seconds))

    monkeypatch.setattr(time, "sleep", _fake_sleep)
    return recorded


def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """把退避的两个常量打成 0——用例不真的睡，靠的是这个，不是新接缝。

    刻意写成**函数而不是 fixture**：断言失败发生在用例体里才算 FAILED，落在 fixture
    里只会变成 ERROR。
    """
    _set_retry_constants(monkeypatch, server, base=0.0, cap=0.0)


def _provider_http_error(message: str, status: int) -> RuntimeError:
    """造一个带状态码的 provider HTTP 错误。

    刻意用 `importlib` + `getattr` 而不是模块级 `from … import ProviderHTTPError`：
    类还不存在时要的是一条**断言失败**，不是整个文件在收集期 ImportError 掉——后者
    连「跑过」都算不上。
    """
    types_mod = importlib.import_module("reader3_app.ai.providers.types")
    cls = getattr(types_mod, "ProviderHTTPError", None)
    assert cls is not None, (
        "ai/providers/types.py 里还没有 ProviderHTTPError。没有它，闸上拿到的是五家 provider "
        "压平出来的裸 RuntimeError，分不出 429 和 401——只能去解析服务端给的错误文本，"
        "而那段文本随时会变（WI-6 第 3 条）。"
    )
    err = cls(message, status=status)
    assert isinstance(err, RuntimeError), "它必须仍然是 RuntimeError，见 R11"
    return err


def _response() -> ProviderResponse:
    return ProviderResponse(
        text=ANSWER_SENTINEL, model="llama3", finish_reason="stop", token_count=7
    )


def _stub_provider(
    monkeypatch: pytest.MonkeyPatch, outcomes: List[Any]
) -> List[Dict[str, Any]]:
    """给 ollama 那一支装一串「第 n 次调用的结果」，返回记录调用的 list。

    列表用完之后**重复最后一项**，这样「一直失败」只要写一项。异常实例原样抛出（R4 靠
    对象同一性判分），其余原样返回。
    """
    calls: List[Dict[str, Any]] = []

    def _fake(**kwargs: Any) -> ProviderResponse:
        calls.append(kwargs)
        outcome = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    _install_ollama_stub(monkeypatch, server, _fake)
    return calls


def _call(**overrides: Any) -> ProviderResponse:
    kwargs: Dict[str, Any] = {
        "api_key": None,
        "base_url": OLLAMA_BASE,
        "model": "llama3",
        "system": "sys",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 64,
        "timeout_s": 5,
    }
    kwargs.update(overrides)
    return server._call_provider("ollama", **kwargs)


def _settings_with(max_retries: int) -> Dict[str, Any]:
    return {
        "default_provider": "ollama",
        "providers": {
            "ollama": {
                "enabled": True,
                "model_name": "llama3",
                "base_url": OLLAMA_BASE,
                "timeout_s": 5,
                "max_retries": max_retries,
            }
        },
    }


# ==========================================================================
# R1–R4：重试循环本身
# ==========================================================================


def test_R1_一次成功就只调一次而且一次都没睡(
    monkeypatch: pytest.MonkeyPatch, sleeps: List[float]
) -> None:
    _no_backoff(monkeypatch)

    calls = _stub_provider(monkeypatch, [_response()])

    resp = _call(max_retries=3)

    assert resp.text == ANSWER_SENTINEL
    assert len(calls) == 1, "成功一次就该收工；重试预算不是「至少调这么多次」"
    assert sleeps == [], "没有失败就不该有退避——一次都不许睡"


def test_R2_前两次瞬时错第三次成功则返回第三次的结果(
    monkeypatch: pytest.MonkeyPatch, sleeps: List[float]
) -> None:
    _no_backoff(monkeypatch)

    calls = _stub_provider(
        monkeypatch,
        [
            urllib.error.URLError("temporary failure in name resolution"),
            TimeoutError("timed out"),
            _response(),
        ],
    )

    resp = _call(max_retries=3)

    assert resp.text == ANSWER_SENTINEL
    assert len(calls) == 3
    assert len(sleeps) == 2, "两次失败之间各退避一次，成功那次之后不退避"


def test_R3_max_retries为0时只调一次(
    monkeypatch: pytest.MonkeyPatch, sleeps: List[float]
) -> None:
    """今天行为的回归护栏：不传 = 传 0 = 只调一次，70 处打桩与既有用例逐字不变。"""
    _no_backoff(monkeypatch)

    boom = _provider_http_error("service unavailable", 503)
    calls = _stub_provider(monkeypatch, [boom])

    with pytest.raises(RuntimeError) as excinfo:
        _call(max_retries=0)

    assert excinfo.value is boom
    assert len(calls) == 1
    assert sleeps == []


def test_R4_重试耗尽后抛的是最后一次那个异常且串与只调一次时逐字相同(
    monkeypatch: pytest.MonkeyPatch, sleeps: List[float]
) -> None:
    """包一层就等于改了 `str(e)`，而那是 SSE 与自测响应的内容（ADR-0011 冻结）。"""
    _no_backoff(monkeypatch)

    first = _provider_http_error("rate limited", 429)
    last = _provider_http_error("rate limited", 429)
    assert first is not last, "夹具前提：两次失败是两个不同的对象，否则 `is` 判不出东西"

    calls = _stub_provider(monkeypatch, [first, last])
    with pytest.raises(RuntimeError) as retried:
        _call(max_retries=1)

    assert len(calls) == 2
    assert retried.value is last, "抛的必须是最后一次那个异常对象本身，不是第一次的，也不是包一层的"

    # 只调一次就失败的那条路径，串长什么样
    once = _provider_http_error("rate limited", 429)
    _stub_provider(monkeypatch, [once])
    with pytest.raises(RuntimeError) as single:
        _call(max_retries=0)

    assert str(retried.value) == str(single.value) == "rate limited"


# ==========================================================================
# R5–R7：分诊表（哪些重试，哪些不重试）
# ==========================================================================


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_R5_其它4xx不重试只调一次(
    monkeypatch: pytest.MonkeyPatch, sleeps: List[float], status: int
) -> None:
    """key 填错、模型名写错、请求体非法——重试只是让用户多等几秒看到同一条错误。"""
    _no_backoff(monkeypatch)

    boom = _provider_http_error(f"nope ({status})", status)
    calls = _stub_provider(monkeypatch, [boom])

    with pytest.raises(RuntimeError) as excinfo:
        _call(max_retries=3)

    assert excinfo.value is boom
    assert len(calls) == 1, f"{status} 不是瞬时故障，重试三次拿到的还是 {status}"
    assert sleeps == []


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_R6_限流与服务端故障真的重试(
    monkeypatch: pytest.MonkeyPatch, sleeps: List[float], status: int
) -> None:
    _no_backoff(monkeypatch)

    calls = _stub_provider(
        monkeypatch, [_provider_http_error(f"transient ({status})", status), _response()]
    )

    resp = _call(max_retries=2)

    assert resp.text == ANSWER_SENTINEL
    assert len(calls) == 2, f"{status} 是典型的瞬时故障，第二次就该再试一遍"
    assert len(sleeps) == 1


@pytest.mark.parametrize(
    "exc",
    [
        urllib.error.URLError("connection refused"),
        TimeoutError("socket timeout"),
        ConnectionError("connection reset by peer"),
    ],
    ids=["URLError", "TimeoutError", "ConnectionError"],
)
def test_R6b_裸穿出来的网络异常也重试(
    monkeypatch: pytest.MonkeyPatch, sleeps: List[float], exc: Exception
) -> None:
    """`_http.post_json` 只接 `HTTPError`，这几类是从 `opener.open` 裸穿出来的。"""
    _no_backoff(monkeypatch)

    calls = _stub_provider(monkeypatch, [exc, _response()])

    resp = _call(max_retries=2)

    assert resp.text == ANSWER_SENTINEL
    assert len(calls) == 2
    assert len(sleeps) == 1


def test_R7_重定向拒绝不重试(
    monkeypatch: pytest.MonkeyPatch, sleeps: List[float]
) -> None:
    """`RedirectNotAllowed` 是一次**安全拒绝**，不是故障。重试它等于反复撞同一堵墙。"""
    _no_backoff(monkeypatch)

    boom = RedirectNotAllowed("refusing to follow a 302 redirect")
    calls = _stub_provider(monkeypatch, [boom])

    with pytest.raises(RedirectNotAllowed) as excinfo:
        _call(max_retries=3)

    assert excinfo.value is boom
    assert len(calls) == 1
    assert sleeps == []


@pytest.mark.parametrize(
    "exc",
    [ValueError("invalid base_url 'ftp://x'"), AssertionError("api_key is not None")],
    ids=["ValueError", "AssertionError"],
)
def test_R7b_配置错误与我们自己抛的错不重试(
    monkeypatch: pytest.MonkeyPatch, sleeps: List[float], exc: Exception
) -> None:
    _no_backoff(monkeypatch)

    calls = _stub_provider(monkeypatch, [exc])

    with pytest.raises(type(exc)) as excinfo:
        _call(max_retries=3)

    assert excinfo.value is exc
    assert len(calls) == 1
    assert sleeps == []


# ==========================================================================
# R8：退避
# ==========================================================================


def test_R8_退避有界且上界随尝试次数单调不减(
    monkeypatch: pytest.MonkeyPatch, sleeps: List[float]
) -> None:
    """指数 + full jitter：`sleep = uniform(0, min(cap, base * 2 ** attempt))`。

    把 `random.uniform` 打成「取上界」，断言的就是那条上界序列本身——否则一条随机值
    只能断言「在区间里」，而「永远返回 0」也在区间里。
    """
    base, cap = 0.5, 2.0
    _set_retry_constants(monkeypatch, server, base=base, cap=cap)
    monkeypatch.setattr(random, "uniform", lambda lo, hi: hi)

    calls = _stub_provider(monkeypatch, [_provider_http_error("busy", 503)])
    with pytest.raises(RuntimeError):
        _call(max_retries=5)

    assert len(calls) == 6, "1 次首发 + 5 次重试"
    assert len(sleeps) == 5, "最后一次失败之后不再退避——那时已经要抛了"

    bounds = [min(cap, base * (2**i)) for i in range(5)]
    assert bounds == [0.5, 1.0, 2.0, 2.0, 2.0], "夹具前提：这串上界会撞到 cap"
    assert sleeps == bounds

    assert all(0.0 <= s <= cap for s in sleeps), "full jitter 的取值必须落在 [0, cap]"
    assert all(b <= n for b, n in zip(bounds, bounds[1:])), "上界只许不减"


# ==========================================================================
# R9–R10：预算从哪里来
# ==========================================================================


def test_R9_不传max_retries时从settings里读(
    monkeypatch: pytest.MonkeyPatch, sleeps: List[float]
) -> None:
    """provider 配 3 ⇒ 一共 4 次尝试（1 首发 + 3 重试）。这才是「接通」本身。"""
    _no_backoff(monkeypatch)

    monkeypatch.setattr(server, "load_ai_settings", lambda *a, **kw: _settings_with(3))
    calls = _stub_provider(monkeypatch, [_provider_http_error("busy", 503)])

    with pytest.raises(RuntimeError):
        _call()

    assert len(calls) == 4
    assert len(sleeps) == 3


def test_R9b_settings里是0时仍然只调一次(
    monkeypatch: pytest.MonkeyPatch, sleeps: List[float]
) -> None:
    _no_backoff(monkeypatch)

    monkeypatch.setattr(server, "load_ai_settings", lambda *a, **kw: _settings_with(0))
    calls = _stub_provider(monkeypatch, [_provider_http_error("busy", 503)])

    with pytest.raises(RuntimeError):
        _call()

    assert len(calls) == 1
    assert sleeps == []


def test_R10_settings读不出来时退化为0次重试且调用照常成功(
    monkeypatch: pytest.MonkeyPatch, sleeps: List[float]
) -> None:
    """查配置这件事绝不能把 LLM 调用打挂——一份坏掉的 ai_settings.json 只该让重试没有。"""
    _no_backoff(monkeypatch)

    def _boom(*a: Any, **kw: Any) -> Dict[str, Any]:
        raise AiSettingsError("config/ai_settings.json exists but could not be parsed")

    monkeypatch.setattr(server, "load_ai_settings", _boom)
    calls = _stub_provider(monkeypatch, [_response()])

    resp = _call()

    assert resp.text == ANSWER_SENTINEL, "配置读不出来，调用还是要发出去"
    assert len(calls) == 1
    assert sleeps == []


def test_R10b_settings读不出来时失败的调用也只调一次(
    monkeypatch: pytest.MonkeyPatch, sleeps: List[float]
) -> None:
    _no_backoff(monkeypatch)

    def _boom(*a: Any, **kw: Any) -> Dict[str, Any]:
        raise AiSettingsError("config/ai_settings.json exists but could not be parsed")

    monkeypatch.setattr(server, "load_ai_settings", _boom)
    boom = _provider_http_error("busy", 503)
    calls = _stub_provider(monkeypatch, [boom])

    with pytest.raises(RuntimeError) as excinfo:
        _call()

    assert excinfo.value is boom
    assert len(calls) == 1, "读不出配置 ⇒ 退化成 0，不是退化成某个默认重试次数"


# ==========================================================================
# R11 / R13：`str(e)` 一个字节都不许变
# ==========================================================================


def test_R11_ProviderHTTPError是RuntimeError子类且str与原来逐字相同() -> None:
    """这条串会进 SSE 的 `message` 和自测响应的 `message`，ADR-0011 下属于响应内容。"""
    err = _provider_http_error("Anthropic API error (429)", 429)

    assert isinstance(err, RuntimeError), (
        "`routers/search.py:207` 那类 `except RuntimeError` 分支、以及既有用例里断言 "
        "RuntimeError 的地方，都必须逐字保持原状"
    )
    assert type(err) is not RuntimeError, "它得是个能带状态码的新类型，否则闸上还是分不出 429 和 401"
    assert err.status == 429
    assert str(err) == "Anthropic API error (429)"
    assert str(err) == str(RuntimeError("Anthropic API error (429)"))
    assert f"{err}" == "Anthropic API error (429)"


def _stub_post_json(
    monkeypatch: pytest.MonkeyPatch, module: Any, *, status: int, body: Dict[str, Any]
) -> None:
    def _fake(url: str, **kwargs: Any):
        return status, body

    _install_post_json_stub(monkeypatch, module, _fake)


#: provider 模块 -> (调用它的 thunk, 错误体, 期望的 message, 没有 message 时的回落串)
_PROVIDER_CASES: Dict[str, Any] = {
    "anthropic": (
        anthropic_mod,
        lambda: anthropic_mod.anthropic_messages(
            api_key="k", model="m", system="s", messages=[], max_tokens=64, timeout_s=5
        ),
        {"error": {"message": "overloaded_error"}},
        "overloaded_error",
        "Anthropic API error (429)",
    ),
    "openai": (
        openai_mod,
        lambda: openai_mod.openai_chat_completions(
            api_key="k",
            base_url="https://api.openai.com/v1",
            model="m",
            system="s",
            messages=[],
            max_tokens=64,
            timeout_s=5,
        ),
        {"error": {"message": "Rate limit reached"}},
        "Rate limit reached",
        "OpenAI API error (429)",
    ),
    "gemini": (
        gemini_mod,
        lambda: gemini_mod.gemini_generate_content(
            api_key="k",
            model="m",
            system="s",
            messages=[],
            max_tokens=64,
            timeout_s=5,
            base_url="https://generativelanguage.googleapis.com",
        ),
        {"error": {"message": "RESOURCE_EXHAUSTED"}},
        "RESOURCE_EXHAUSTED",
        "Gemini API error (429)",
    ),
    "ollama": (
        ollama_mod,
        lambda: ollama_mod.ollama_chat_completions(
            base_url=OLLAMA_BASE, model="m", system="s", messages=[], max_tokens=64, timeout_s=5
        ),
        {"error": "model requires more system memory"},
        "model requires more system memory",
        "Ollama API error (429)",
    ),
    "openrouter": (
        openrouter_mod,
        lambda: openrouter_mod.openrouter_chat_completions(
            api_key="k",
            base_url="https://openrouter.ai/api/v1",
            model="m",
            system="s",
            messages=[],
            max_tokens=64,
            timeout_s=5,
        ),
        {"error": {"message": "throttled upstream"}},
        "throttled upstream",
        "OpenRouter API error (429)",
    ),
}


@pytest.mark.parametrize("name", sorted(_PROVIDER_CASES))
def test_R13_五家provider抛的都是带状态码的ProviderHTTPError(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """没有这条，闸上那张分诊表在生产里永远碰不到 `ProviderHTTPError`。"""
    module, call, body, expected_message, _fallback = _PROVIDER_CASES[name]
    types_mod = importlib.import_module("reader3_app.ai.providers.types")
    cls = getattr(types_mod, "ProviderHTTPError", None)
    assert cls is not None, "ProviderHTTPError 还不存在（WI-6 第 3 条）"

    _stub_post_json(monkeypatch, module, status=429, body=body)

    with pytest.raises(RuntimeError) as excinfo:
        call()

    assert isinstance(excinfo.value, cls), f"{name} 还在抛裸 RuntimeError，状态码丢了"
    assert excinfo.value.status == 429
    assert str(excinfo.value) == expected_message, "错误串是响应内容，不许变"


@pytest.mark.parametrize("name", sorted(_PROVIDER_CASES))
def test_R13b_错误体里没有message时回落串也逐字不变(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    module, call, _body, _expected, fallback = _PROVIDER_CASES[name]

    _stub_post_json(monkeypatch, module, status=429, body={})

    with pytest.raises(RuntimeError) as excinfo:
        call()

    assert str(excinfo.value) == fallback
    assert excinfo.value.status == 429


# ==========================================================================
# R12：连通性自测显式不重试
# ==========================================================================


def test_R12_连通性自测失败时provider只被调一次(
    monkeypatch: pytest.MonkeyPatch, sleeps: List[float]
) -> None:
    """用户点「测试」就是要立刻知道通不通。

    settings 里写着 `max_retries=5`，路由仍必须只发一次请求：退避三轮会把一个 2 秒的
    失败变成 8 秒，还会把「偶发抖动」伪装成「连得通」。桩打在 provider 函数上（比
    `_call_provider` 更底层），所以这条用例看得见真实的重试循环有没有转起来，且全程不出网。
    """
    _no_backoff(monkeypatch)

    from fastapi.testclient import TestClient

    monkeypatch.setattr(server, "load_ai_settings", lambda *a, **kw: _settings_with(5))
    calls = _stub_provider(monkeypatch, [_provider_http_error("connection refused", 503)])

    with TestClient(server.app, base_url="http://127.0.0.1") as client:
        resp = client.post("/api/settings/providers/ollama/test", json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "connection refused", "失败原因原样交给前端，不许被重试逻辑改写"
    assert len(calls) == 1, "连通性自测必须显式 max_retries=0"
    assert sleeps == []
