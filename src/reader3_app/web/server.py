import os
import contextlib
import hmac
import logging
import random
import time
import json
import asyncio
import threading
import urllib.error  # WI-6：重试要按类型分诊 URLError（含 socket timeout）；出网仍只走 ai/providers/_http
from urllib.parse import parse_qs, urlsplit
import html
import uuid
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional, cast

from fastapi import FastAPI, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, Response, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# 不再 import safe_pickle：反序列化只经 book_store（011 §4）。占位保留行号：server.py:51/107 被 EXPECTED_CAPTURES 钉着。
from .. import book_store
from ..ai.books import BookUuidResolver
from ..ai.conversations import (
    ConversationMessage as DiskConversationMessage,
    ConversationThread as DiskConversationThread,
    delete_conversation_multi as delete_disk_conversation_multi,
    list_conversations_combined as list_disk_conversations_combined,
    load_conversation_combined as load_disk_conversation_combined,
    save_conversation_multi as save_disk_conversation_multi,
)
from ..ai.config import (
    AiSettingsError,
    default_settings_dict,
    get_provider_api_key,
    get_provider_settings,
    load_ai_settings,
    save_ai_settings,
)
from ..ai.config import get_provider_base_url
# 出网只走这两个口（WI-30，finding `web/E1`）：scheme 白名单和「不跟随 30x」都装在那边，
# 而这两处的 URL 是用户经 `PUT /api/settings` 可编辑的 base_url 拼出来的。
# 流式那一口必须是 post_stream 而不是 post_json——post_json 读完整个 body 才返回，
# 会把 ollama 的 NDJSON 流退化成阻塞调用（WI-21/WI-22 的两条性质就没了）。
from ..ai.providers._http import get_json as _egress_get_json
from ..ai.providers._http import post_stream as _egress_post_stream
from ..ai.providers.anthropic import anthropic_messages
from ..ai.providers.gemini import gemini_generate_content
from ..ai.providers.ollama import ollama_chat_completions
from ..ai.providers.openai import openai_chat_completions
from ..ai.providers.openrouter import openrouter_chat_completions
from ..ai.providers.types import ProviderHTTPError
from ..ai.queue import AIRequestQueueManager
from ..ai.rag import retrieve_passages
from ..ai.routing import (
    book_token_stats,
    build_full_book_context,
    build_multi_chapter_context,
    choose_routing,
    provider_context_window,
    unique_chapter_orders_from_passages,
)
from ..reader3 import Book, BookMetadata, ChapterContent, TOCEntry
from ..search_service import (
    SearchQuery,
    SearchScope,
    SearchMode,
    list_book_ids,
    search_book,
    search_library,
    highlight_ranges_for_chapter,
)
from ..vector_search import BookVectorIndex
from ..models.annotations import Annotation
from ..notes_service import (
    NOTES_SCHEMA_VERSION,
    NotesFileError,
    add_annotation as add_note_annotation,
    delete_annotation as delete_note_annotation,
    load_annotations as load_note_annotations,
    save_annotations as save_note_annotations,
    update_annotation as update_note_annotation,
)
from .. import collections_service

app = FastAPI()

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger("reader3.search")
ai_logger = logging.getLogger("reader3.ai")

# Where are the book folders located?
BOOKS_DIR = os.environ.get("READER3_BOOKS_DIR", "books")
os.makedirs(BOOKS_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

book_uuid_resolver = BookUuidResolver(BOOKS_DIR)
ai_queue = AIRequestQueueManager(max_pending=10)

#: 断连/超时之后，等一个流式 worker 停下来的**上界**。
#:
#: 有上界是刻意的：见 ``_stop_stream_worker`` 里那段取舍。等不到就放弃等，
#: 记一条 ERROR，然后**照样**释放租约。
AI_WORKER_STOP_TIMEOUT_S = 5.0

# ---------------------------------------------------------------------------
# 请求边界的三道闸（WI-27）
#
# 为什么绑 loopback 不够：同机上任何进程都够得着 127.0.0.1:8123，浏览器里任意一个
# 标签页也算。更要命的是 **DNS rebinding**——攻击者的域名先解析到自己的 IP，页面
# 加载完再把解析改到 127.0.0.1，那个页面于是能对本服务发「同源」请求，读走书库、
# 标注、以及 provider API key。这三样都不可再生或不可撤销。
#
# 这是本批唯一一处涉及产品形态的取舍，所以写在这里而不是偷偷决定：Reader3 是自托管
# 本地阅读器，强制登录会毁掉「打开就能读」。因此只做**最小且默认开启**的一组，不引入
# 账号体系：
#
#   1. Host 校验（默认开启）——rebinding 的请求带的是攻击者的域名，这是掐死它的抓手。
#   2. 改动型请求（POST/PUT/DELETE/PATCH）的 Origin / Sec-Fetch-Site 校验——跨站一律 403。
#      **无 Origin 头的放行**是刻意的：curl 和原生客户端不发 Origin，而浏览器对跨站的
#      改动型请求**一定**会带上它，所以放行不给 rebinding 留门，拒掉却会当场弄坏本地工具链。
#   3. 可选的应用令牌——只有设了 READER3_TOKEN 才启用，默认不设，默认行为与今天完全一致。
#
# **刻意不做**：账号体系、会话 cookie、CSRF token、HTTPS 强制。前两样改产品形态，
# 后两样属于部署层，都不在 008 范围。
#
# 已知局限（说出来，不假装没有）：令牌今天保护的是 API 与页面本身，浏览器 UI 里的
# fetch 还没有把令牌带上，所以 READER3_TOKEN 目前适合 CLI / 反代场景。把令牌接进前端
# 属于 013 的活。
#
# 三个码是三种失败，不共用：400 = Host 不认（与 Starlette TrustedHostMiddleware 同义
# 同文案），401 = 令牌缺失或不对，403 = 跨站来源。

#: 覆盖用 READER3_ALLOWED_HOSTS（逗号分隔）。
#:
#: **这里刻意不含 TestClient 的默认 host ``testserver``**。它进白名单能让测试道免改，
#: 但那是拿一条只为测试存在的生产默认值换方便：单标签名可以经 DHCP 下发的搜索域或
#: 被改过的 hosts 文件解析，而白名单的整个意义就是「别信请求自称的名字」。测试改用
#: ``TestClient(..., base_url="http://127.0.0.1")``，于是它们走的是真实用户走的那条
#: 白名单，而不是一条只有测试才走得通的旁路。
DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "localhost", "[::1]")

#: 令牌豁免。``/api/health`` 是就绪探针（009 的 Playwright webServer、Phase 5 的
#: ``reader3 launch`` 都靠它判断服务起没起来），它不吐任何书库内容，豁免的代价是零，
#: 不豁免的代价是设了令牌之后启动探测全挂。``/static/`` 是本仓自带的 JS/CSS，
#: 同样不含用户数据，且页面拿不到令牌就加载不了它们。
_TOKEN_EXEMPT_PATHS = ("/api/health",)
_TOKEN_EXEMPT_PREFIXES = ("/static/",)

#: 不改状态的方法不做 Origin 校验：CSRF 的伤害面是副作用，而读取由 Host 闸和令牌管。
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _allowed_hosts() -> tuple[str, ...]:
    """每次请求现读 env，不在 import 时定死。

    定死会有两个后果：测试没法用 monkeypatch 换掉它（``server`` 早被 import 了），
    以及改一个 host 白名单要重启进程。
    """
    raw = os.environ.get("READER3_ALLOWED_HOSTS") or ""
    hosts = tuple(h.strip() for h in raw.split(",") if h.strip())
    return hosts or DEFAULT_ALLOWED_HOSTS


def _app_token() -> str:
    """空串等同于没设：``READER3_TOKEN=`` 是「我不要令牌」，不是「令牌是空串」。"""
    return (os.environ.get("READER3_TOKEN") or "").strip()


def _host_key(value: str) -> str:
    """把 Host 头或白名单条目归一成可比的键：去端口、去 IPv6 方括号、转小写。

    这一步是这里没有直接用 ``starlette.middleware.trustedhost.TrustedHostMiddleware``
    的原因：它的匹配是 ``headers["host"].split(":")[0]``，对 ``[::1]:8123`` 会得到
    ``"["``，而白名单里的 ``[::1]`` 也永远匹配不上任何东西——也就是说「用
    TrustedHostMiddleware」和「默认白名单含 [::1]」这两条要求在字面上互斥。
    状态码与响应体文案与它保持一致（400 / "Invalid host header"）。
    """
    host = (value or "").strip().lower()
    if host.startswith("["):  # [::1] 或 [::1]:8123
        end = host.find("]")
        return host[1:end] if end != -1 else host.lstrip("[")
    if host.count(":") > 1:  # 没加方括号的 IPv6 字面量
        return host
    return host.split(":", 1)[0]


def _host_is_allowed(host_header: str) -> bool:
    allowed = _allowed_hosts()
    if "*" in allowed:  # 反代/局域网自托管的逃生舱，要显式设才有
        return True
    return _host_key(host_header) in {_host_key(p) for p in allowed}


def _is_cross_site(origin: str, sec_fetch_site: str, host_header: str) -> bool:
    """判定一个改动型请求是不是从别的站点发起的。

    ``Sec-Fetch-Site`` 优先：现代浏览器一定发，且它是浏览器自己的判断，伪造不了。
    ``same-site`` 也算跨站——同站不同源（别的端口、别的子域）对一个本地服务而言
    仍然是别人。没有这个头时退回比 ``Origin`` 的 netloc 与 ``Host``：**含端口**，
    因为同机另一个端口上的应用正是这里要挡的那类邻居。
    """
    site = (sec_fetch_site or "").strip().lower()
    if site in ("cross-site", "same-site"):
        return True
    if site in ("same-origin", "none"):
        return False

    value = (origin or "").strip()
    if not value:
        return False  # curl / 原生客户端：刻意放行，见文件头
    if value.lower() == "null":
        return True  # sandbox iframe / file:// —— 来源不可判定，按跨站处理
    return urlsplit(value).netloc.strip().lower() != (host_header or "").strip().lower()


def _presented_token(scope: dict[str, Any], headers: dict[str, str]) -> str:
    header_token = headers.get("x-reader3-token")
    if header_token:
        return header_token.strip()
    # ``<img src>``、epub.js 的 iframe 加不上自定义头，只剩查询参数这条路。
    query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
    values = query.get("token") or []
    return values[0].strip() if values else ""


def _token_exempt(path: str) -> bool:
    return path in _TOKEN_EXEMPT_PATHS or path.startswith(_TOKEN_EXEMPT_PREFIXES)


class RequestGuardMiddleware:
    """纯 ASGI 中间件，不用 BaseHTTPMiddleware——本服务有 SSE 流式路由。

    顺序是有讲究的：Host 闸必须跑在**任何碰书库的东西之前**，令牌其次（认证先于
    授权），Origin 最后。作用域只限 ``http``：本服务没有 websocket 路由，往
    websocket 的 scope 上回一个 HTTP Response 是错的。
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers") or []
        }
        host_header = headers.get("host", "")

        if not _host_is_allowed(host_header):
            await PlainTextResponse("Invalid host header", status_code=400)(scope, receive, send)
            return

        token = _app_token()
        if token and not _token_exempt(scope.get("path", "")):
            # compare_digest 而不是 ==：令牌比较是逐字节的，别把长度和前缀漏给计时。
            if not hmac.compare_digest(_presented_token(scope, headers), token):
                await JSONResponse(
                    {"detail": "Missing or invalid application token"}, status_code=401
                )(scope, receive, send)
                return

        if scope.get("method", "GET").upper() not in _SAFE_METHODS:
            if _is_cross_site(
                headers.get("origin", ""), headers.get("sec-fetch-site", ""), host_header
            ):
                await JSONResponse({"detail": "Cross-site request rejected"}, status_code=403)(
                    scope, receive, send
                )
                return

        await self.app(scope, receive, send)


app.add_middleware(RequestGuardMiddleware)


_stats_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _project_root_dir_from_books_dir() -> str:
    return os.path.dirname(os.path.abspath(BOOKS_DIR))

def _collections_file_path() -> Path:
    return collections_service.collections_path(_project_root_dir_from_books_dir())

def _library_ui_mode() -> str:
    mode = (os.environ.get("READER3_LIBRARY_UI") or "modern").strip().lower()
    return mode if mode in {"modern", "classic"} else "modern"

def _library_template_name() -> str:
    if _library_ui_mode() == "classic":
        classic = TEMPLATES_DIR / "library_classic.html"
        if classic.exists():
            return "library_classic.html"
    return "library.html"

def _validate_collection_id(collection_id: str) -> str:
    try:
        return str(uuid.UUID(str(collection_id)))
    except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，转译成 400 且 detail 说明原因；类型待收窄为 ValueError
        raise HTTPException(status_code=400, detail="Invalid collection_id")

@app.exception_handler(AiSettingsError)
async def _ai_settings_error_handler(request: Request, exc: AiSettingsError) -> JSONResponse:
    """一处覆盖 load_ai_settings() 的全部 ~14 个调用点。

    坏掉的 ai_settings.json 不再被静默换成默认值（那条路会抹掉用户的 API key），
    所以任何读设置的端点现在都可能撞上 AiSettingsError。逐个 try 只会漏掉下一个
    新加的调用点；这里统一转成 500，detail 带上文件路径和怎么修——用户完全有能力
    自己修一个自己读得到的文件，前提是我们告诉他是哪个文件。
    """
    ai_logger.error("ai settings unreadable: %s", exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(NotesFileError)
async def _notes_file_error_handler(request: Request, exc: NotesFileError) -> JSONResponse:
    """一处覆盖 notes_service 的全部 6 个调用点（611 / 638 / 699 / 784 / 797 / 817）。

    读不出来的 notes.json 不再被静默换成空列表——那条路上，用户随后加的任何一条
    标注都会触发 save_annotations 整份重写，把这本书此前的标注永久抹掉，而且不报错。
    所以任何读标注的端点现在都可能撞上 NotesFileError。

    形状照抄上面的 _ai_settings_error_handler，理由也一样：逐个 try 只会漏掉下一个
    新加的调用点。detail 带上文件路径——标注是用户自己产生、错了不能重新生成的数据，
    他有能力自己修一个自己读得到的文件，前提是我们告诉他是哪个文件。
    """
    logger.error("notes file unreadable: %s", exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.on_event("startup")
async def _startup_scan_books() -> None:
    # Ensure stable UUID mapping exists for all processed books.
    book_uuid_resolver.scan()

def _share_loader_cache_surface(
    wrapper: Callable[[str], Optional[Book]]
) -> Callable[[str], Optional[Book]]:
    """Give ``wrapper`` the merged cache's own bound methods, then return it.

    ``cache_clear`` / ``cache_info`` / ``cache_parameters`` are copied off
    ``book_store.load_book_cached``, so they are the **one real cache's** own
    methods rather than forwarders onto a second one. Seven test modules and
    ``tests/contract/conftest.py`` hold at least one of the three on this name;
    ``tests/contract/test_read_chapter_traversal.py:159`` copies ``cache_clear``
    off it onto a spy.

    A decorator, and not the equivalent bare ``_share_loader_cache_surface(
    load_book_cached)`` statement below the ``def``, for two reasons. It leaves
    no window in which the module-level name exists without the surface — an
    import executed between a ``def`` and a later call statement would export a
    callable whose ``cache_clear`` raises ``AttributeError`` — and it keeps the
    surface visibly part of the definition instead of a line someone can move.

    Both shapes are legal against the import-time-capture scan in
    ``tests/unit/test_server_patch_seam_ownership.py`` (Check C), and most of
    the obvious alternatives are not. ``functools.partial(
    book_store.load_book_cached, books_dir=BOOKS_DIR)`` fails three ways: no
    ``cache_clear``, ``BOOKS_DIR`` baked at import time (five tests rebind it),
    and a module-level ``Assign`` naming ``load_book_cached`` that the scanner
    records as a ``module_assign`` capture. Assigning the three attributes at
    module level hits that last problem too. The scanner walks assignments,
    imports, signatures and decorators — it does not descend into function
    bodies, and the decorator expression here names nothing on its list.
    """
    wrapper.cache_clear = book_store.load_book_cached.cache_clear  # type: ignore[attr-defined]
    wrapper.cache_info = book_store.load_book_cached.cache_info  # type: ignore[attr-defined]
    wrapper.cache_parameters = book_store.load_book_cached.cache_parameters  # type: ignore[attr-defined]
    return wrapper


@_share_loader_cache_surface
def load_book_cached(folder_name: str) -> Optional[Book]:
    """The web layer's view of ``book_store.load_book_cached``: total, and never raising.

    ``BOOKS_DIR`` is read **here, on every call**, not captured at import. Tests
    rebind it with ``monkeypatch.setattr`` and ``server.py:104`` already
    documents what happens to a component that captured it instead.

    Deliberately **not** the same object as ``book_store.load_book_cached``
    (D5-a): six tests patch this name to intercept the eleven server-side call
    sites, three of them with a one-argument ``lambda folder: ...`` that the
    two-argument search path would ``TypeError`` on. Two names, one cache — the
    cache is shared through the surface above, the identity is not.

    Nothing is memoized in this function. The core's ``lru_cache`` is the only
    one on the path, so ``cache_info()``'s hit and miss columns describe every
    call that reaches it, and a republished ``book.pkl`` is visible on the next
    read rather than after a restart.

    Two degradation paths, and the asymmetry is the point (D1-a):

    * **Absence is silent.** A ``*_data`` directory with no ``book.pkl`` is the
      state between ``mkdir`` and the atomic publish. ``library_view`` walks
      every such directory on every homepage request, so a trace here would be
      a per-request log flood for a condition that is not an error. The old
      code was silent for the same reason, via an ``os.path.exists`` check
      before the ``try``.
    * **Everything else degrades loudly and returns ``None``.** The blind
      ``except Exception`` is deliberate and is what the ``noqa`` records.
      Narrowing it to ``(FileNotFoundError, UnpicklingError)`` — the two types
      every damage fixture in the suite produces — would leave ``library_view``
      to propagate the first ``MemoryError``, ``RecursionError`` on a deep TOC
      or ``OSError`` (EIO, ENAMETOOLONG, ENOTDIR) out of a per-row call that
      has no guard around it: one damaged book, and the whole library page
      500s. ``tests/unit/test_book_store_server_wrapper.py``'s
      ``test_the_wrapper_swallows_every_exception_class_not_just_the_two_it_has_seen``
      owns that claim; anyone deleting this ``noqa`` has to delete that test
      and argue for the 500.

    The core raises on every one of these; deciding what the *user* sees is
    this layer's job, because this is the layer with a status code to spend.
    """
    try:
        # No fallback loader: see safe_pickle. A book.pkl the allow-list refuses
        # raises here, and the handler below degrades that one book to None.
        # `book_store` is annotated `-> object`: it is deliberately ignorant of
        # `reader3.Book`, which is what keeps it importable without the web
        # layer. Re-stating the type is this layer's job, not a cast that hides
        # a doubt — every payload it can return is a `Book` or an exception.
        return cast(Book, book_store.load_book_cached(folder_name, BOOKS_DIR))
    except FileNotFoundError:
        return None
    except Exception as e:  # noqa: BLE001 - 第 2 档：坏掉的 book.pkl 只让这一本书从书库消失，其余照常；已 print 留痕（该换成 logger，见 008 报告）
        print(f"Error loading book {folder_name}: {e}")
        return None

def _book_uuid_or_none(book_folder: str) -> Optional[str]:
    """解析 book_uuid，读不出来就降级成 None 并留痕，而不是让整页 500。

    **这是第 2 档（捕获并转译），刻意不是第 1 档。** `ensure_book_uuid()` 在
    `ai_meta.json` 读不懂时抛，那是对的 —— 旧行为是静默生成新 uuid 覆盖原文件，
    用户全部 AI 会话当场失联且原值已被删除。但「抛」传到这两个调用点上就变成了
    **一本书的元数据坏掉 → 整个书库首页 500 / 该书的阅读页 500**，用户连能修它的
    界面都进不去。错误处理不该比错误本身更糟。

    降级后的可观测证据有三处，不是静默：
      1. 服务端 warning，点名是哪本书、错在哪；
      2. 该书的 AI 端点 404（明确的缺失），而不是被换上一个新 uuid（无声的数据丢失）；
      3. 前端 `library-chat.js` 已有的 `if (!this.bookUuid)` 分支会亮出提示。
         模板必须渲染成空串才能命中它 —— Jinja 把 None 渲染成字符串 "None"，
         那是个真值，会绕过整条降级路径。见 library.html / reader.html 的 `or ""`。

    **原文件一个字节都不会被改。** 这是与旧行为的根本区别：坏掉的 ai_meta.json
    仍然躺在那里，人可以修；旧代码会把它覆盖掉，谁也救不回来。
    """
    try:
        return book_uuid_resolver.book_uuid_for_folder(book_folder)
    except (OSError, ValueError) as e:
        logger.warning("cannot resolve book_uuid for %s: %s", book_folder, e)
        return None



def _validate_book_id_path_safe(book_id: str) -> str:
    safe = os.path.basename(str(book_id or ""))
    if safe != book_id:
        raise HTTPException(status_code=400, detail="Invalid book_id")
    if not safe.endswith("_data"):
        raise HTTPException(status_code=400, detail="Invalid book_id")
    return safe



def _validate_book_id(book_id: str) -> str:
    safe = os.path.basename(book_id)
    if safe != book_id:
        raise HTTPException(status_code=400, detail="Invalid book_id")
    if safe not in set(list_book_ids(BOOKS_DIR)):
        raise HTTPException(status_code=404, detail="Book not found")
    return safe


def _collapse_ws(text: str) -> str:
    return " ".join(str(text or "").split())


def _annotation_matches_chapter_text(chapter_text: str, ann: Annotation) -> bool:
    hay = _collapse_ws(chapter_text)
    if not hay:
        return False

    quote = _collapse_ws(ann.quote)
    if not quote:
        return False

    combo = _collapse_ws(f"{ann.prefix}{ann.quote}{ann.suffix}")
    if combo and combo in hay:
        return True
    return quote in hay





# 这四个模型搬去了 `web/schemas.py`（011 WI-4）。这里反向 import 并保留同名：
# `server.AIMessage` 等仍然存在、且与 router 拿到的是同一个类对象。它们不是打桩
# 接缝，所以 router 直接从 schemas 导入即可，不必走 `_server.`。
from .schemas import (  # noqa: E402
    AIMessage,
    AIQuestionRequest,
    AIRagRequest,
    AISummaryRequest,
)

SUPPORTED_AI_PROVIDERS = {"anthropic", "openai", "gemini", "ollama", "openrouter"}


def _provider_requires_api_key(provider_name: str) -> bool:
    return provider_name in {"anthropic", "openai", "gemini", "openrouter"}


def _ui_default_provider() -> str:
    settings = load_ai_settings()
    configured = str(settings.get("default_provider") or "").strip().lower()

    def provider_is_usable(name: str) -> bool:
        if name not in SUPPORTED_AI_PROVIDERS:
            return False
        provider = get_provider_settings(name, settings=settings)
        if not provider.enabled:
            return False
        if _provider_requires_api_key(name) and not get_provider_api_key(name, settings=settings):
            return False
        return True

    if configured and provider_is_usable(configured):
        return configured

    # Prefer a local/offline provider when available so the UI works out-of-the-box.
    for candidate in ("ollama", "anthropic", "openai", "gemini", "openrouter"):
        if provider_is_usable(candidate):
            return candidate

    # Fallback: return a supported provider even if it isn't usable, so the UI can still render.
    return configured if configured in SUPPORTED_AI_PROVIDERS else "anthropic"


def _get_provider_runtime(
    provider_from_request: str,
    model_from_request: Optional[str],
) -> tuple[str, Optional[str], str, str, int]:
    settings = load_ai_settings()
    provider_name = (provider_from_request or settings.get("default_provider") or "anthropic").strip().lower()
    if provider_name not in SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider_name}")

    provider = get_provider_settings(provider_name, settings=settings)
    if not provider.enabled:
        raise HTTPException(status_code=503, detail="AI provider is disabled in settings")

    api_key: Optional[str] = None
    if _provider_requires_api_key(provider_name):
        api_key = get_provider_api_key(provider_name, settings=settings)
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail=f"{provider_name} API key not configured. Create config/ai_settings.json (see config/ai_settings.example.json).",
            )

    base_url = get_provider_base_url(provider_name, settings=settings) or provider.base_url or ""
    model = (model_from_request or provider.model_name).strip()
    return provider_name, api_key, base_url, model, provider.timeout_s


#: 指数退避的底与上限（秒）。用例把这两个名字打成 0 来做到不真的睡——**刻意不另开一个
#: `sleep` 接缝**：`server` 上每多一个被打桩的名字，WI-1 的注册表就要跟着动一次，
#: 代价大于收益（tests/unit/test_provider_retry.py 的模块 docstring 记着这笔账）。
PROVIDER_RETRY_BASE_S = 0.5
PROVIDER_RETRY_CAP_S = 8.0

#: 值得再试一次的状态码：限流与服务端故障。其余 4xx（400/401/403/404/422）不在里面，
#: 因为 key 填错、模型名写错、请求体非法重试三次拿到的还是同一条错误，只是让用户多等几秒。
PROVIDER_RETRY_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

#: 会被重试循环**接住**的异常类型。窄到只有这四类是有意的：
#: 写成 `except Exception` 会连 `RedirectNotAllowed`（一次安全拒绝，不是故障）、
#: `ValueError`（base_url 非法）、`HTTPException`（我们自己抛的）一起重试，
#: 而那三样重试多少次都是同一个结果。落在这个元组外面的异常原样穿出去。
_PROVIDER_RETRY_CANDIDATES = (
    ProviderHTTPError,
    urllib.error.URLError,  # 含 socket timeout；`_http.post_json` 只接 HTTPError，这类是裸穿的
    TimeoutError,
    ConnectionError,
)


def _provider_error_is_retryable(exc: BaseException) -> bool:
    """这个异常值得再试一次吗？

    分诊靠**类型与状态码**，不靠解析错误文本——那段文本来自服务端，随时会变。
    这正是 `ProviderHTTPError` 存在的理由（见 ai/providers/types.py）。
    """
    if isinstance(exc, ProviderHTTPError):
        return exc.status in PROVIDER_RETRY_STATUS_CODES
    if isinstance(exc, urllib.error.HTTPError):
        # post_json 会把 HTTPError 压成 (status, body)，所以这条今天走不到；
        # 留着是因为流式/探活那两个出网口不经过它，将来接进来时行为要一致。
        return int(getattr(exc, "code", 0) or 0) in PROVIDER_RETRY_STATUS_CODES
    return isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError))


def _provider_retry_budget(provider_name: str, max_retries: Optional[int]) -> int:
    """这次调用允许重试几次。

    `max_retries=None` 表示「调用方没说，去 settings 里查」。**默认值是 None 而落地成 0
    的那条回退路径是承重的**：查不到、或者查这件事本身抛了，都退化成 0 次重试——
    一份读不出来的 ai_settings.json 只该让重试消失，绝不能把 LLM 调用打挂。

    走 `load_ai_settings()`（server 命名空间上的名字，registry 已登记）而不是让
    `get_provider_settings` 自己去读盘：这样 contract lane 既有的那份打桩仍然拦得住它，
    `_call_provider` 不会在测试里摸到开发者真正的 config/ai_settings.json。
    """
    if max_retries is not None:
        return max(0, min(int(max_retries), 10))
    try:
        return get_provider_settings(provider_name, settings=load_ai_settings()).max_retries
    except Exception as e:  # noqa: BLE001 - 第 3 档：读不出配置就当 0 次重试，调用照常发出；痕迹是下面这条 WARNING
        ai_logger.warning(
            "provider %s: could not read max_retries (%s: %s); continuing with no retries",
            provider_name,
            type(e).__name__,
            e,
        )
        return 0


def _call_provider(
    provider_name: str,
    *,
    api_key: Optional[str],
    base_url: str,
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    timeout_s: int,
    max_retries: Optional[int] = None,
):
    """ADR-0006 的唯一 LLM 出口，外加 WI-6 接上的重试。

    重试写在这里而不是写进 provider：六个非流式调用点全部经过这一处，写进 provider
    就是抄五份——那正是 WI-11 刚从 `_http.py` 收掉的毛病。

    **`max_retries` 默认 None（= 去 settings 查）而不是某个数**，且查不到时落到 0：
    「不传 = 今天的行为」，所以 70 处既有打桩与全部既有用例逐字不变。

    **流式路径不在这道闸上**：ollama 的流式 chat 走 `_egress_post_stream`，不经过这里，
    因此拿不到重试。那是有意的——SSE 已经把前半段正文推给客户端了，重试会让用户看到
    重复的文本。
    """
    attempts_allowed = _provider_retry_budget(provider_name, max_retries)
    attempt = 0
    while True:
        try:
            return _provider_call_once(
                provider_name,
                api_key=api_key,
                base_url=base_url,
                model=model,
                system=system,
                messages=messages,
                max_tokens=max_tokens,
                timeout_s=timeout_s,
            )
        except _PROVIDER_RETRY_CANDIDATES as e:
            if attempt >= attempts_allowed or not _provider_error_is_retryable(e):
                # 抛**最后一次**那个异常对象本身，不包一层：包一层就改了 str(e)，
                # 而它是 SSE 与自测响应的内容（ADR-0011 冻结）。
                raise
            delay = random.uniform(
                0, min(PROVIDER_RETRY_CAP_S, PROVIDER_RETRY_BASE_S * (2**attempt))
            )
            # 只记 provider 名、第几次、异常类型/状态码。**不记 api_key、不记 base_url、
            # 不记请求体**——这条日志会进用户的终端和日志文件。
            ai_logger.warning(
                "provider %s: attempt %d/%d failed (%s%s); retrying in %.2fs",
                provider_name,
                attempt + 1,
                attempts_allowed + 1,
                type(e).__name__,
                f" status={e.status}" if isinstance(e, ProviderHTTPError) else "",
                delay,
            )
            time.sleep(delay)
            attempt += 1


def _provider_call_once(
    provider_name: str,
    *,
    api_key: Optional[str],
    base_url: str,
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    timeout_s: int,
):
    """一次调用，不含重试。`_call_provider` 的分派体原样搬进来，一个字没改。"""
    if provider_name == "anthropic":
        assert api_key is not None
        return anthropic_messages(
            api_key=api_key,
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
    if provider_name == "gemini":
        assert api_key is not None
        return gemini_generate_content(
            api_key=api_key,
            base_url=base_url or "https://generativelanguage.googleapis.com",
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
    if provider_name == "ollama":
        return ollama_chat_completions(
            base_url=base_url or "http://localhost:11434",
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
    if provider_name == "openai":
        assert api_key is not None
        return openai_chat_completions(
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1",
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
    if provider_name == "openrouter":
        assert api_key is not None
        return openrouter_chat_completions(
            api_key=api_key,
            base_url=base_url or "https://openrouter.ai/api/v1",
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
    raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider_name}")


def _conversation_id_from_history(history: list[AIMessage]) -> Optional[str]:
    for m in history or []:
        cid = str(m.conversation_id or "").strip()
        if cid:
            return cid
    return None


def _save_conversation_snapshot(
    *,
    book_uuid: str,
    book_folder: str,
    conversation_id: str,
    provider: str,
    model: str,
    history: list[AIMessage],
    assistant_message: Optional[DiskConversationMessage] = None,
) -> None:
    messages: list[DiskConversationMessage] = []
    for m in history or []:
        role = str(m.role or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        msg_id = str(m.id or "").strip()
        if not msg_id:
            continue
        messages.append(
            DiskConversationMessage(
                id=msg_id,
                role=role,
                content=str(m.content or ""),
                timestamp=str(m.timestamp or ""),
                metadata=dict(m.metadata or {}),
            )
        )
    if assistant_message is not None:
        messages.append(assistant_message)
    thread = DiskConversationThread(
        schema_version=1,
        book_uuid=str(book_uuid),
        book_folder=book_folder,
        conversation_id=conversation_id,
        provider=provider,
        model=model,
        created_at="",
        last_updated="",
        messages=messages,
    )
    settings = load_ai_settings()
    save_disk_conversation_multi(
        BOOKS_DIR,
        thread=thread,
        project_conversations_root=_project_conversations_root(settings),
        storage_mode=_conversation_disk_storage_mode(settings),
    )


def _provider_default_base_url(provider_name: str) -> str:
    provider_name = (provider_name or "").strip().lower()
    if provider_name == "anthropic":
        return "https://api.anthropic.com"
    if provider_name == "openai":
        return "https://api.openai.com/v1"
    if provider_name == "gemini":
        return "https://generativelanguage.googleapis.com"
    if provider_name == "ollama":
        return "http://localhost:11434"
    if provider_name == "openrouter":
        return "https://openrouter.ai/api/v1"
    return ""


def _public_provider_config(provider_name: str, *, settings: dict) -> dict:
    provider = get_provider_settings(provider_name, settings=settings)
    base_url = get_provider_base_url(provider_name, settings=settings) or provider.base_url or _provider_default_base_url(provider_name)
    api_key_configured = False
    if _provider_requires_api_key(provider_name):
        api_key_configured = bool(get_provider_api_key(provider_name, settings=settings))
    return {
        "name": provider_name,
        "api_key_configured": api_key_configured,
        "base_url": base_url,
        "model_name": provider.model_name,
        "enabled": provider.enabled,
        "timeout": provider.timeout_s,
        "max_retries": provider.max_retries,
    }


def _public_settings_response(settings: dict) -> dict:
    provider_list = []
    for name in ("anthropic", "openai", "gemini", "ollama", "openrouter"):
        if name not in SUPPORTED_AI_PROVIDERS:
            continue
        provider_list.append(_public_provider_config(name, settings=settings))

    prefs_default = (default_settings_dict().get("preferences") or {}).copy()
    prefs = (settings.get("preferences") or {}).copy()
    prefs_default.update(prefs)
    return {
        "default_provider": str(settings.get("default_provider") or "anthropic").strip().lower(),
        "providers": provider_list,
        "preferences": prefs_default,
    }


def _conversation_disk_storage_mode(settings: dict) -> str:
    prefs = settings.get("preferences") if isinstance(settings.get("preferences"), dict) else {}
    mode = str((prefs or {}).get("conversation_disk_storage") or "per_book").strip().lower()
    if mode not in ("per_book", "project_root", "both"):
        return "per_book"
    return mode


def _project_conversations_root(settings: dict) -> Optional[str]:
    prefs = settings.get("preferences") if isinstance(settings.get("preferences"), dict) else {}
    rel = str((prefs or {}).get("conversation_project_root_dir") or "conversations").strip()
    if not rel:
        rel = "conversations"
    if os.path.isabs(rel):
        return None
    rel_norm = os.path.normpath(rel)
    if rel_norm.startswith(".."):
        return None
    return os.path.join(_project_root_dir_from_books_dir(), rel_norm)


def _settings_update_provider(
    provider_name: str,
    *,
    settings: dict,
    patch: dict,
) -> dict:
    provider_name = provider_name.strip().lower()
    if provider_name not in SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not found")

    providers = dict(settings.get("providers") or {})
    base = dict(providers.get(provider_name) or {})
    for key in ("enabled", "model_name", "base_url", "timeout", "timeout_s", "max_retries"):
        if key in patch:
            base[key] = patch.get(key)
    if "api_key" in patch:
        base["api_key"] = str(patch.get("api_key") or "").strip()
    providers[provider_name] = base
    settings["providers"] = providers
    return settings


def _http_get_json(url: str, *, timeout_s: int = 3) -> dict:
    """ollama 探活/列模型用的 GET。**闸在 `ai/providers/_http` 那一处，不在这里。**

    留着这层薄封装只是为了不动两个调用点的写法；它自己不许再出现 `urlopen`。
    `url` 是 `_ollama_root_base_url(base_url) + "/api/version"` 拼出来的，而
    `base_url` 用户经 `PUT /api/settings` 就能改成 `file:///…`（finding `web/E1`）。
    """
    return _egress_get_json(url, timeout_s=timeout_s)


def _ollama_root_base_url(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        base = "http://localhost:11434"
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base.rstrip("/")

def _ollama_openai_base_url(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        base = "http://localhost:11434"
    if base.endswith("/v1"):
        return base
    return base + "/v1"



def _push_event(queue: "asyncio.Queue[dict]", evt: dict) -> bool:
    """把一个流式事件塞进 SSE 队列，返回它有没有真的进去。

    第 2 档：这是 worker 线程与事件循环之间的边界。丢一个 chunk 等于用户的答案
    少了一截，而那截还会被当成模型的完整回答存进会话——所以只吞 QueueFull
    （唯一「不是 bug、只是背压」的情况），并且留一条 warning。其余异常
    （循环已关闭、队列不是队列）冒上去，交给调用方的错误路径。
    """
    try:
        queue.put_nowait(evt)
    except asyncio.QueueFull:
        ai_logger.warning(
            "dropped a streamed %s event: SSE queue is full, the answer will be truncated",
            str(evt.get("type") or "unknown"),
        )
        return False
    return True






DEFAULT_PORT = 8123
DEFAULT_HOST = "127.0.0.1"


def _package_version() -> str:
    """装出来的版本号；源码树里跑（没装过）时回落到 pyproject 之外的一个标记。"""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("reader3")
    except PackageNotFoundError:
        return "0+unknown"


def _parse_port(raw: str, source: str) -> int:
    """把一个字符串解成合法端口，解不动就抛。

    **不回落到默认值**是有意的：静默回落会把「你写错了」伪装成「一切正常」——
    服务照样起来，只是起在 8123 上，然后撞开发者本地那个实例。0.3 要消灭的
    正是这类症状不指向病因的失败。
    """
    try:
        port = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{source} 不是整数：{raw!r}") from None
    if not (1 <= port <= 65535):
        raise ValueError(f"{source} 超出 1–65535：{port}")
    return port


def resolve_port(argv: list[str], env: dict[str, str]) -> int:
    """端口优先级：**`--port` > `READER3_PORT` > 8123**。

    定义处见 tasks/007-hygiene-and-contracts.md 步骤 0.3。
    `--port 9000` 与 `--port=9000` 两种写法都收。
    """
    for i, arg in enumerate(argv):
        if arg == "--port":
            if i + 1 >= len(argv):
                raise ValueError("--port 缺少值")
            return _parse_port(argv[i + 1], "--port")
        if arg.startswith("--port="):
            return _parse_port(arg.split("=", 1)[1], "--port")

    raw = (env.get("READER3_PORT") or "").strip()
    if raw:
        return _parse_port(raw, "READER3_PORT")

    return DEFAULT_PORT


# ---------------------------------------------------------------------------
# 按关切拆开的 router。**必须在文件末尾 include**：router 模块在导入期会
# `from .. import server as _server` 绑定本模块对象，放在文件开头 include 会让它
# 在本模块的名字都还没定义时就被导入。绑的是模块不是属性，所以这里只要求
# 「server 这个对象已经在 sys.modules 里」，不要求它已经执行完。
# 规矩与实测依据见 `routers/__init__.py` 的 docstring。
# ---------------------------------------------------------------------------
from .routers import library as _library_router  # noqa: E402
from .routers import reader as _reader_router  # noqa: E402
from .routers import settings as _settings_router  # noqa: E402
from .routers import health as _health_router  # noqa: E402
from .routers.ai import chat as _ai_chat_router  # noqa: E402
from .routers.ai import conversations as _ai_conversations_router  # noqa: E402
from .routers.ai import rag as _ai_rag_router  # noqa: E402
from .routers.ai import summary as _ai_summary_router  # noqa: E402
from .routers import notes as _notes_router  # noqa: E402
from .routers import search as _search_router  # noqa: E402

app.include_router(_library_router.router)
app.include_router(_reader_router.router)
app.include_router(_settings_router.router)
app.include_router(_health_router.router)
app.include_router(_ai_conversations_router.router)
app.include_router(_ai_rag_router.router)
app.include_router(_ai_summary_router.router)
app.include_router(_ai_chat_router.router)
app.include_router(_notes_router.router)
app.include_router(_search_router.router)


def main() -> int:
    import sys

    import uvicorn

    try:
        port = resolve_port(sys.argv[1:], dict(os.environ))
    except ValueError as e:
        print(f"reader3-server: {e}", file=sys.stderr)
        return 2

    print(f"Starting server at http://{DEFAULT_HOST}:{port}")
    uvicorn.run(app, host=DEFAULT_HOST, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
