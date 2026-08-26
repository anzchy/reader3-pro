"""整个进程唯一的出网口。

WI-30（finding `web/E1`）之后「所有 provider」不再够用：`server.py` 的 ollama 探活
（`get_json`）和 ollama 流式 chat（`post_stream`）也在这里出网。它们从前留在闸外，
于是 `ai/74` 那个洞在标了 fixed 之后仍然从 `PUT /api/settings` 一路开着。
`tests/unit/test_direct_urlopen_call_sites.py` 现在锁的是「`src/` 里一次直接
`urlopen` 都没有」，所以这份文件是唯一定义 scheme 白名单与重定向策略的地方。

WI-11（findings `ai/74`、`ai/75`）：这四家 provider 从前各自抄了一份 `_post_json`，
于是「`base_url` 一路从 `PUT /api/settings` 走到 `urlopen`、没有 scheme 白名单」这件事
也有四份。finding 自己写明了后果——「一个像 #74 这样的修复要改四遍，而且不会都改到」。
所以先把出网收成一处，再在这一处上闸。

**没有收进来的东西**：每家的错误体解析仍留在各自文件里。四家的错误 JSON 形状不一样
（`error.message` / `message` / 顶层字符串），强行统一只会把 `ai/73` 那类
「解析不到就当成空回答」的 bug 藏得更深。这里只负责「把字节取回来」。
"""

from __future__ import annotations

import contextlib
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Mapping, Optional, Tuple

#: 只有这两个。`file://` 让 urlopen 去读本地文件并把内容顺着响应路径回传，
#: `ftp://`/`gopher://` 同理，`javascript:` 只是没人拦过它。
ALLOWED_SCHEMES = ("http", "https")


class RedirectNotAllowed(RuntimeError):
    """服务端回了 30x，而我们不跟。"""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """把 30x 直接抛出来，不跟随。

    urllib 默认跟随重定向，并且（在本解释器上）跨 host 时**保留 `Authorization` 头**。
    也就是说一个 host 合法、证书合法的 endpoint 只要回一个 302，就能把带着用户 API key
    的请求弹到任意第三方去——白名单拦得住第一跳，拦不住第二跳。

    而 LLM 的 chat/completions 类接口不需要重定向：正常路径上一次都不该出现 30x。
    所以这里的取舍不是「安全 vs 兼容」，是「安全 vs 无人使用的兼容」。
    """

    def _refuse(self, req: Any, fp: Any, code: int, msg: str, headers: Any) -> None:
        location = str(headers.get("location") or headers.get("uri") or "")
        # 不跟随，但把连接放掉。关不掉也不该盖住下面这条真正的错误。
        with contextlib.suppress(Exception):
            fp.close()
        raise RedirectNotAllowed(
            f"refusing to follow a {code} redirect from {req.full_url!r} to {location!r}: "
            "following it would carry the API key in this request's headers to another host"
        )

    # urllib 按 `http_error_<code>` 的方法名注册处理器，所以每个码都要挂一遍。
    http_error_301 = _refuse
    http_error_302 = _refuse
    http_error_303 = _refuse
    http_error_307 = _refuse
    http_error_308 = _refuse


def validated_url(base_url: Optional[str], *, default: str) -> str:
    """校验一个用户/请求可控的 base_url，返回去掉尾斜杠的形式。

    `None` 表示「调用方压根没配」，用 `default`；`""` 和 `"   "` 表示「配了个空的」，
    是配置错误，直接抛。这两件事不是一回事，合并它们就等于把打错的配置静悄悄换成默认值。

    抛出的 `ValueError` 一定带上被拒的原值：只说 "invalid URL" 会让用户对着一份
    settings 文件猜是哪一项。
    """
    raw = default if base_url is None else base_url
    candidate = str(raw or "").strip()
    if not candidate:
        raise ValueError(f"invalid base_url {raw!r}: it is empty; expected an http(s) URL")

    parts = urllib.parse.urlsplit(candidate)
    scheme = (parts.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ValueError(
            f"invalid base_url {raw!r}: scheme {scheme!r} is not allowed; "
            f"only {' and '.join(ALLOWED_SCHEMES)} are"
        )
    if not parts.netloc:
        raise ValueError(f"invalid base_url {raw!r}: it has no host")
    return candidate.rstrip("/")


def _checked_request_url(url: str) -> str:
    """校验一个**已经拼好**的请求 URL 的 scheme，通过则原样返回。

    与 `validated_url` 的分工：那一个校的是 provider 配置里的 `base_url`（还要有 host、
    还要处理 `None` 与空串的区别）；这一个校的是拼接之后真正要交给 opener 的那个字符串。
    白名单只有 `ALLOWED_SCHEMES` 一份——WI-11 收口要消灭的就是同一个事实有第二处定义。

    `server.py` 的两处出网点（ollama 探活、ollama 流式 chat）拼 URL 的方式是
    `_ollama_root_base_url(base_url) + "/api/version"`，中间不经过 `validated_url`，
    所以闸必须装在这一层，否则 `file:///…` 会一路走到 urllib 的 FileHandler，
    把本机文件读出来顺着响应回给浏览器（finding `web/E1`）。
    """
    candidate = str(url or "")
    scheme = (urllib.parse.urlsplit(candidate).scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ValueError(
            f"refusing to request {candidate!r}: scheme {scheme!r} is not allowed; "
            f"only {' and '.join(ALLOWED_SCHEMES)} are"
        )
    return candidate


def get_json(url: str, *, timeout_s: int) -> Dict[str, Any]:
    """GET 一份 JSON，取回已解析的 dict。

    顶层不是对象时包成 `{"data": ...}`，因为调用方（`server._http_get_json`）的签名
    一直是「返回 dict」，让一个 list 直接漏出去会把类型错误推迟到更远的地方才炸。
    """
    req = urllib.request.Request(_checked_request_url(url), method="GET")
    req.add_header("Accept", "application/json")

    opener = urllib.request.build_opener(_NoRedirectHandler())
    with opener.open(req, timeout=timeout_s) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        parsed = json.loads(body or "{}")
        if isinstance(parsed, dict):
            return parsed
        return {"data": parsed}


@contextlib.contextmanager
def post_stream(
    url: str,
    *,
    payload: Dict[str, Any],
    headers: Optional[Mapping[str, str]] = None,
    timeout_s: int,
):
    """POST 一份 JSON，把**还没读**的 response 交给调用方逐行读。

    刻意不是 `post_json`：那个会 `resp.read()` 把整个 body 读完再返回。ollama 的
    `/api/chat` 是 NDJSON 流，`worker_ollama` 每读到一行就往 SSE 队列推一个 chunk，
    并且在每行**之前**检查 `stop_event`。改成读完再交，第一个 chunk 会等到整段回答
    生成完才出现，客户端断连后 worker 也再停不下来——正是 WI-21/WI-22 钉住的两条性质。

    交出 response 而不是交出一个已解析的对象，代价是调用方要自己认 4xx：
    非 2xx 在 `HTTPErrorProcessor` 那里就变成 `HTTPError` 抛出来，不像 `post_json`
    会把错误体原样交回。流式路径上本来就没有「把错误体交给 provider 各自解析」这一步。
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(_checked_request_url(url), data=data, method="POST")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    opener = urllib.request.build_opener(_NoRedirectHandler())
    # `with` 而不是 try/finally + close()：urllib 的 response 本身就是上下文管理器，
    # 走它的 `__exit__` 才和调用方原来那句 `with urlopen(...) as resp:` 逐字等价。
    with opener.open(req, timeout=timeout_s) as resp:
        yield resp


def post_json(
    url: str,
    *,
    payload: Dict[str, Any],
    headers: Optional[Mapping[str, str]] = None,
    timeout_s: int,
) -> Tuple[int, Dict[str, Any]]:
    """POST 一份 JSON，取回 `(status, parsed_body)`。

    4xx/5xx **不抛**，原样交回调用方——每家 provider 的错误体形状不同，解析留在各自文件里。
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = int(getattr(resp, "status", None) or resp.getcode() or 0)
            # 2xx 却不是 JSON 属于真故障，让它抛。ollama 那份旧代码在这里把非 JSON 的
            # 成功响应包成 {"error": ...} 再返回 200，于是调用方读出一个空回答、
            # 什么都不报——正是 WI-12 要拆的那类沉默。
            return status, json.loads(body or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if getattr(e, "fp", None) else ""
        try:
            parsed = json.loads(body or "{}")
        except Exception:  # noqa: BLE001 - 第 2 档：错误响应体不是 JSON 时原样塞进 error.message，痕迹在返回值里
            parsed = {"error": {"message": body or str(e)}}
        if not isinstance(parsed, dict):
            parsed = {"error": {"message": body or str(e)}}
        return int(getattr(e, "code", 500) or 500), parsed


def estimate_tokens(text: str) -> int:
    """四份重复的 len/4 收成一份。

    **算法一个字没改**，包括它对 CJK 明显偏低这件事——那是 finding `ai/45`，归 WI-24。
    在这条里顺手改掉，会让本条的变异证据（删掉白名单该有哪条断言变红）说不清楚。
    """
    if not text:
        return 0
    return max(1, int(len(text) / 4))
