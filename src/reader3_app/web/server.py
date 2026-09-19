import os
import contextlib
import hmac
import logging
import time
import json
import asyncio
import threading
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

# 不再 import safe_pickle：反序列化只经 book_store（011 §4）。占位保留行号：server.py:49/104 被 EXPECTED_CAPTURES 钉着。
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


@app.get("/settings", response_class=HTMLResponse)
async def settings_view(request: Request):
    return templates.TemplateResponse(request, "settings.html", {})

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



class AIMessage(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str
    conversation_id: Optional[str] = None
    metadata: Optional[dict] = None


class AISummaryRequest(BaseModel):
    provider: str
    model: Optional[str] = None
    max_tokens: int = 2000


class AIQuestionRequest(BaseModel):
    question: str
    provider: str
    model: Optional[str] = None
    conversation_history: list[AIMessage] = Field(default_factory=list)
    rag_k: int = 5
    max_tokens: int = 1000


class AIRagRequest(BaseModel):
    book_uuid: str
    query: str
    k: int = 5
    min_similarity: float = 0.5


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
):
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

def _sse_event(event: str, data: Any) -> bytes:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


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


async def _stop_stream_worker(
    *,
    label: str,
    stop_event: Optional[threading.Event] = None,
    thread: Optional[threading.Thread] = None,
    task: "Optional[asyncio.Task]" = None,
    timeout_s: Optional[float] = None,
) -> bool:
    """取消一个流式 worker 并**等它真的停下**，最多等 ``AI_WORKER_STOP_TIMEOUT_S``。

    为什么要等：调用方紧接着就会释放队列租约，而释放租约的含义是「这本书可以开始
    下一个请求了」。不等就放，下一个「本该串行」的请求会和上一个还活着的 worker
    并发打同一个 provider——串行语义于是只是个说法。

    **等不到怎么办：仍然释放租约，只留一条 ERROR。** 这个取舍是刻意的，两害相权：

    * 租约永久泄漏 = 这本书的 AI 问答**功能性死亡**，之后每一个请求都排在一个永不
      结束的请求后面，且只有重启才能恢复；
    * 一个跑飞的 worker = 多一次 provider 调用的开销和一个线程。ollama 线程是
      ``daemon=True``，进程退出时会被回收；非流式 task 已经 cancel 过，它下一个
      await 点就会退出。

    后者可观测（这条 ERROR 就是），前者不可观测且不可恢复。所以宁可漏 worker，
    不可漏租约。

    返回 worker 是否在上界内停住——调用方不看返回值，返回值是给测试和以后的调用方的。
    """
    bound = AI_WORKER_STOP_TIMEOUT_S if timeout_s is None else timeout_s

    if stop_event is not None:
        stop_event.set()

    if task is not None:
        if not task.done():
            task.cancel()
        await asyncio.wait({task}, timeout=max(0.0, bound))
        if not task.done():
            ai_logger.error(
                "%s worker did not stop within %.1fs after cancellation; "
                "releasing the AI queue lease anyway (a leaked lease would block this book permanently)",
                label,
                bound,
            )
            return False
        return True

    if thread is not None:
        if thread.is_alive():
            await run_in_threadpool(thread.join, max(0.0, bound))
        if thread.is_alive():
            ai_logger.error(
                "%s worker thread did not stop within %.1fs after the stop event was set; "
                "releasing the AI queue lease anyway (a leaked lease would block this book permanently)",
                label,
                bound,
            )
            return False
        return True

    return True


@app.get("/api/health")
async def api_health():
    """就绪探针。009 的 Playwright `webServer` 与 Phase 5 的 `reader3 launch` 都用它。

    **故意不碰磁盘**：不扫 books/、不读 settings、不加载任何 book.pkl。探针要在
    书库为空甚至目录不存在时也能答 200，否则 webServer 只会报「服务没起来」，
    而真实原因是探针自己在一个空目录上 500 了。
    """
    return {"status": "ok", "version": _package_version()}


@app.get("/api/settings")
async def api_get_settings():
    settings = load_ai_settings()
    return _public_settings_response(settings)


class UpdateSettingsRequest(BaseModel):
    default_provider: Optional[str] = None
    preferences: Optional[dict] = None


@app.put("/api/settings")
async def api_put_settings(body: UpdateSettingsRequest):
    settings = load_ai_settings()
    updated = dict(settings or {})
    if body.default_provider is not None:
        provider = str(body.default_provider or "").strip().lower()
        if provider and provider not in SUPPORTED_AI_PROVIDERS:
            raise HTTPException(status_code=400, detail="Invalid default_provider")
        updated["default_provider"] = provider or updated.get("default_provider") or "anthropic"
    if body.preferences is not None:
        # 现存 → 补丁，同 /api/settings/import。**不要**从 default_settings_dict()
        # 重新起头：settings 已经过 _merge_defaults，默认值就在里面，再引一次默认
        # 只会把用户存过的其它偏好按出厂值写回磁盘——前端发一个 {"theme": "dark"}
        # 就够把落盘模式、会话上限一起重置掉。
        existing_prefs = settings.get("preferences") if isinstance(settings.get("preferences"), dict) else {}
        prefs_patch = body.preferences if isinstance(body.preferences, dict) else {}
        merged = dict(existing_prefs)
        merged.update({k: v for k, v in prefs_patch.items() if v is not None})
        updated["preferences"] = merged

    save_ai_settings(updated)
    return _public_settings_response(load_ai_settings())


@app.get("/api/settings/providers")
async def api_list_settings_providers():
    providers = []
    defaults = default_settings_dict()
    default_providers = defaults.get("providers") or {}
    for name in ("anthropic", "openai", "gemini", "ollama", "openrouter"):
        if name not in SUPPORTED_AI_PROVIDERS:
            continue
        p = default_providers.get(name) or {}
        providers.append(
            {
                "name": name,
                "display_name": {
                    "anthropic": "Anthropic Claude",
                    "openai": "OpenAI",
                    "gemini": "Google Gemini",
                    "ollama": "Ollama (Local)",
                    "openrouter": "OpenRouter",
                }.get(name, name),
                "description": {
                    "ollama": "Local AI provider via Ollama (offline-capable)",
                    "openrouter": "Unified API for many models/providers",
                }.get(name, ""),
                "default_base_url": str(p.get("base_url") or _provider_default_base_url(name) or "").strip(),
                "default_model": str(p.get("model_name") or "").strip(),
                "supported_features": {
                    "streaming": True,
                    "function_calling": False,
                    "vision": False,
                },
                "documentation_url": {
                    "anthropic": "https://docs.anthropic.com",
                    "openai": "https://platform.openai.com/docs",
                    "gemini": "https://ai.google.dev",
                    "ollama": "https://ollama.com",
                    "openrouter": "https://openrouter.ai/docs",
                }.get(name, ""),
            }
        )
    return {"providers": providers}


@app.get("/api/settings/providers/{provider_name}")
async def api_get_provider(provider_name: str):
    name = (provider_name or "").strip().lower()
    if name not in SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not found")
    settings = load_ai_settings()
    return _public_provider_config(name, settings=settings)


def _settings_export_payload(settings: dict) -> dict:
    exported: dict = {
        "default_provider": str(settings.get("default_provider") or "anthropic").strip().lower(),
        "preferences": settings.get("preferences") if isinstance(settings.get("preferences"), dict) else {},
        "providers": {},
    }
    providers = settings.get("providers") if isinstance(settings.get("providers"), dict) else {}
    for name, cfg in providers.items():
        if not isinstance(cfg, dict):
            continue
        safe_cfg = dict(cfg)
        safe_cfg.pop("api_key", None)
        exported["providers"][str(name).strip().lower()] = safe_cfg
    return exported


@app.get("/api/settings/export")
async def api_settings_export():
    settings = load_ai_settings()
    return _settings_export_payload(settings)


@app.post("/api/settings/import")
async def api_settings_import(body: dict):
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")

    existing = load_ai_settings()
    updated = dict(existing or {})

    if "default_provider" in body:
        dp = str(body.get("default_provider") or "").strip().lower()
        if dp and dp in SUPPORTED_AI_PROVIDERS:
            updated["default_provider"] = dp

    if isinstance(body.get("preferences"), dict):
        prefs_default = (default_settings_dict().get("preferences") or {}).copy()
        prefs_default.update(existing.get("preferences") if isinstance(existing.get("preferences"), dict) else {})
        prefs_default.update({k: v for k, v in body.get("preferences").items() if v is not None})
        updated["preferences"] = prefs_default

    existing_providers = existing.get("providers") if isinstance(existing.get("providers"), dict) else {}
    merged_providers = dict(existing_providers)
    incoming_providers = body.get("providers") if isinstance(body.get("providers"), dict) else {}
    for name, patch in incoming_providers.items():
        pname = str(name or "").strip().lower()
        if pname not in SUPPORTED_AI_PROVIDERS:
            continue
        base = dict(merged_providers.get(pname) or {})
        if isinstance(patch, dict):
            for key in ("enabled", "model_name", "base_url", "timeout", "timeout_s", "max_retries"):
                if key in patch:
                    base[key] = patch.get(key)
        # API keys are never imported.
        merged_providers[pname] = base
    updated["providers"] = merged_providers

    save_ai_settings(updated)
    return _public_settings_response(load_ai_settings())


class UpdateProviderRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None
    enabled: Optional[bool] = None
    timeout: Optional[int] = None
    max_retries: Optional[int] = None


@app.put("/api/settings/providers/{provider_name}")
async def api_put_provider(provider_name: str, body: UpdateProviderRequest):
    name = (provider_name or "").strip().lower()
    if name not in SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not found")

    patch: dict[str, Any] = {}
    if body.api_key is not None:
        patch["api_key"] = body.api_key
    if body.base_url is not None:
        patch["base_url"] = str(body.base_url or "").strip()
    if body.model_name is not None:
        patch["model_name"] = str(body.model_name or "").strip()
    if body.enabled is not None:
        patch["enabled"] = bool(body.enabled)
    if body.timeout is not None:
        patch["timeout_s"] = int(body.timeout)
        patch["timeout"] = int(body.timeout)
    if body.max_retries is not None:
        patch["max_retries"] = int(body.max_retries)

    settings = load_ai_settings()
    updated = _settings_update_provider(name, settings=settings, patch=patch)
    save_ai_settings(updated)
    return _public_provider_config(name, settings=load_ai_settings())


@app.delete("/api/settings/providers/{provider_name}", status_code=204)
async def api_delete_provider(provider_name: str):
    name = (provider_name or "").strip().lower()
    if name not in SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not found")
    settings = load_ai_settings()
    providers = dict(settings.get("providers") or {})
    providers.pop(name, None)
    settings["providers"] = providers
    save_ai_settings(settings)
    return None


class TestProviderRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None


@app.post("/api/settings/providers/{provider_name}/test")
async def api_test_provider(provider_name: str, body: TestProviderRequest):
    name = (provider_name or "").strip().lower()
    if name not in SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not found")

    settings = load_ai_settings()
    provider_cfg = get_provider_settings(name, settings=settings)
    stored_base_url = get_provider_base_url(name, settings=settings) or provider_cfg.base_url or ""
    requested_base_url = str(body.base_url or "").strip() if body.base_url is not None else None
    base_url = stored_base_url if requested_base_url is None else requested_base_url
    model = str(body.model_name or "").strip() if body.model_name is not None else provider_cfg.model_name

    # 换了 endpoint 就必须自带 key（finding web/C2）。
    #
    # 这条路由没有鉴权（web/C1），所以「请求只给 base_url、key 从盘上取」等于：
    # 本机任意进程、或者一个做 DNS rebinding 的网页，只要 POST 一次就能让服务器
    # 把用户存着的真 key 发到它指定的地址去。回落必须在**发请求之前**断掉——
    # 挪到发完之后再报 400，状态码看着一样，key 已经出去了。
    if requested_base_url is not None and requested_base_url.rstrip("/") != stored_base_url.rstrip("/") and not body.api_key:
        raise HTTPException(
            status_code=400,
            detail=(
                "This request supplies a different base_url than the one in settings, so it must "
                "also supply its own api_key. The stored API key is never sent to an endpoint "
                "chosen by the request."
            ),
        )

    api_key = body.api_key if body.api_key is not None else get_provider_api_key(name, settings=settings)

    if _provider_requires_api_key(name) and not api_key:
        raise HTTPException(status_code=401, detail="API key not configured")

    system = "You are a connectivity test. Reply with a single word: OK."
    messages = [{"role": "user", "content": "OK"}]

    started = time.perf_counter()
    try:
        resp = await run_in_threadpool(
            _call_provider,
            name,
            api_key=api_key,
            base_url=base_url,
            model=model,
            system=system,
            messages=messages,
            max_tokens=16,
            timeout_s=min(10, provider_cfg.timeout_s),
        )
    except Exception as e:  # noqa: BLE001 - 第 2 档：连通性自测的返回值就是 success/message，失败原因原样交给前端
        return {
            "success": False,
            "provider": name,
            "message": str(e),
            "details": {"model": model, "latency_ms": int((time.perf_counter() - started) * 1000)},
        }

    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "success": True,
        "provider": name,
        "message": "OK",
        "details": {"model": resp.model, "latency_ms": latency_ms},
    }


@app.get("/api/ollama/status")
async def api_ollama_status():
    settings = load_ai_settings()
    base_url = get_provider_base_url("ollama", settings=settings) or get_provider_settings("ollama", settings=settings).base_url or "http://localhost:11434"
    root = _ollama_root_base_url(base_url)
    try:
        info = _http_get_json(root + "/api/version", timeout_s=2)
        return {"running": True, "base_url": root, "version": info.get("version")}
    except Exception as e:  # noqa: BLE001 - 第 2 档：ollama 探活的返回值就是 running/error，失败原因原样交给前端
        return {"running": False, "base_url": root, "error": str(e)}


@app.get("/api/ollama/models")
async def api_ollama_models():
    settings = load_ai_settings()
    base_url = get_provider_base_url("ollama", settings=settings) or get_provider_settings("ollama", settings=settings).base_url or "http://localhost:11434"
    root = _ollama_root_base_url(base_url)
    try:
        tags = _http_get_json(root + "/api/tags", timeout_s=4)
        models = tags.get("models") if isinstance(tags, dict) else None
        if not isinstance(models, list):
            models = []
        out = []
        for m in models:
            if not isinstance(m, dict):
                continue
            out.append(
                {
                    "name": str(m.get("name") or ""),
                    "size": m.get("size"),
                    "modified_at": m.get("modified_at"),
                    "details": m.get("details") or {},
                }
            )
        return {"models": out, "base_url": root}
    except Exception as e:  # noqa: BLE001 - 第 2 档：HTTP 边界，转译成 503 且 detail 带上原因
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/api/ai/conversations/{book_uuid}")
async def api_ai_list_conversations(book_uuid: str, provider: Optional[str] = None):
    try:
        book_folder = book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，解析不出 book_uuid 即「这本书不存在」→404；类型待收窄为 (KeyError, ValueError)
        raise HTTPException(status_code=404, detail="Book not found")
    settings = load_ai_settings()
    threads = list_disk_conversations_combined(
        BOOKS_DIR,
        book_folder=book_folder,
        book_uuid=str(book_uuid),
        provider=provider,
        project_conversations_root=_project_conversations_root(settings),
    )
    return {"book_uuid": str(book_uuid), "provider": (provider or "").strip().lower() or None, "conversations": threads}


@app.get("/api/ai/conversations/{book_uuid}/{conversation_id}")
async def api_ai_get_conversation(book_uuid: str, conversation_id: str):
    try:
        book_folder = book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，解析不出 book_uuid 即「这本书不存在」→404；类型待收窄为 (KeyError, ValueError)
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        settings = load_ai_settings()
        thread = load_disk_conversation_combined(
            BOOKS_DIR,
            book_folder=book_folder,
            book_uuid=str(book_uuid),
            conversation_id=conversation_id,
            project_conversations_root=_project_conversations_root(settings),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    except Exception as e:  # noqa: BLE001 - 第 2 档：HTTP 边界，转译成 400 且 detail 带上原因
        raise HTTPException(status_code=400, detail=str(e))
    return thread.to_dict()


class SaveConversationRequest(BaseModel):
    provider: str
    model: Optional[str] = None
    created_at: Optional[str] = None
    last_updated: Optional[str] = None
    messages: list[AIMessage] = Field(default_factory=list)


@app.put("/api/ai/conversations/{book_uuid}/{conversation_id}")
async def api_ai_put_conversation(book_uuid: str, conversation_id: str, body: SaveConversationRequest):
    try:
        book_folder = book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，解析不出 book_uuid 即「这本书不存在」→404；类型待收窄为 (KeyError, ValueError)
        raise HTTPException(status_code=404, detail="Book not found")
    provider = (body.provider or "").strip().lower()
    if provider not in SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    msgs: list[DiskConversationMessage] = []
    for m in body.messages or []:
        role = (m.role or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        msg_id = str(m.id or "").strip()
        if not msg_id:
            continue
        msgs.append(
            DiskConversationMessage(
                id=msg_id,
                role=role,
                content=str(m.content or ""),
                timestamp=str(m.timestamp or ""),
                metadata=dict(m.metadata or {}),
            )
        )

    thread = DiskConversationThread(
        schema_version=1,
        book_uuid=str(book_uuid),
        book_folder=book_folder,
        conversation_id=str(conversation_id),
        provider=provider,
        model=str(body.model or ""),
        created_at=str(body.created_at or ""),
        last_updated=str(body.last_updated or ""),
        messages=msgs,
    )
    try:
        settings = load_ai_settings()
        save_disk_conversation_multi(
            BOOKS_DIR,
            thread=thread,
            project_conversations_root=_project_conversations_root(settings),
            storage_mode=_conversation_disk_storage_mode(settings),
        )
    except Exception as e:  # noqa: BLE001 - 第 2 档：HTTP 边界，转译成 400 且 detail 带上原因
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@app.delete("/api/ai/conversations/{book_uuid}/{conversation_id}", status_code=204)
async def api_ai_delete_conversation(book_uuid: str, conversation_id: str):
    try:
        book_folder = book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，解析不出 book_uuid 即「这本书不存在」→404；类型待收窄为 (KeyError, ValueError)
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        settings = load_ai_settings()
        delete_disk_conversation_multi(
            BOOKS_DIR,
            book_folder=book_folder,
            book_uuid=str(book_uuid),
            conversation_id=conversation_id,
            project_conversations_root=_project_conversations_root(settings),
        )
    except Exception as e:  # noqa: BLE001 - 第 2 档：HTTP 边界，转译成 400 且 detail 带上原因
        raise HTTPException(status_code=400, detail=str(e))
    return None


def _conversation_to_text(thread: dict) -> str:
    lines = []
    msgs = thread.get("messages") if isinstance(thread.get("messages"), list) else []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        label = "User" if role == "user" else "Assistant"
        content = str(m.get("content") or "").rstrip()
        lines.append(f"{label}: {content}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _conversation_to_markdown(thread: dict) -> str:
    book_uuid = str(thread.get("book_uuid") or "").strip()
    provider = str(thread.get("provider") or "").strip()
    model = str(thread.get("model") or "").strip()
    conv_id = str(thread.get("conversation_id") or "").strip()
    created_at = str(thread.get("created_at") or "").strip()
    last_updated = str(thread.get("last_updated") or "").strip()

    out = [
        "# AI Conversation",
        "",
        f"- book_uuid: `{book_uuid}`",
        f"- conversation_id: `{conv_id}`",
        f"- provider: `{provider}`",
        f"- model: `{model}`",
        f"- created_at: `{created_at}`",
        f"- last_updated: `{last_updated}`",
        "",
        "---",
        "",
    ]
    msgs = thread.get("messages") if isinstance(thread.get("messages"), list) else []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        title = "User" if role == "user" else "Assistant"
        ts = str(m.get("timestamp") or "").strip()
        content = str(m.get("content") or "").rstrip()
        out.append(f"## {title}")
        if ts:
            out.append(f"- time: `{ts}`")
            out.append("")
        out.append(content or "")
        out.append("")
    return "\n".join(out).strip() + "\n"


@app.get("/api/ai/conversations/{book_uuid}/{conversation_id}/export")
async def api_ai_export_conversation(book_uuid: str, conversation_id: str, format: str = "json"):
    try:
        book_folder = book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，解析不出 book_uuid 即「这本书不存在」→404；类型待收窄为 (KeyError, ValueError)
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        settings = load_ai_settings()
        thread = load_disk_conversation_combined(
            BOOKS_DIR,
            book_folder=book_folder,
            book_uuid=str(book_uuid),
            conversation_id=conversation_id,
            project_conversations_root=_project_conversations_root(settings),
        ).to_dict()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    except Exception as e:  # noqa: BLE001 - 第 2 档：HTTP 边界，转译成 400 且 detail 带上原因
        raise HTTPException(status_code=400, detail=str(e))

    fmt = str(format or "json").strip().lower()
    if fmt == "json":
        return thread
    if fmt in ("text", "txt"):
        body = _conversation_to_text(thread)
        return Response(content=body, media_type="text/plain; charset=utf-8")
    if fmt in ("md", "markdown"):
        body = _conversation_to_markdown(thread)
        return Response(content=body, media_type="text/markdown; charset=utf-8")
    raise HTTPException(status_code=400, detail="Invalid format (use json|text|md)")


def _summary_prompt(summary_type: str) -> str:
    st = (summary_type or "full").strip().lower()
    if st not in {"overview", "highlights", "background", "full"}:
        st = "full"
    if st == "overview":
        return "只生成 overview（2-3 段），其余字段可以留空。"
    if st == "highlights":
        return "只生成 highlights（5-10 条要点，每条 1-2 句），其余字段可以留空。"
    if st == "background":
        return "只生成 background（2-4 段：作者/时代/意义/背景），其余字段可以留空。"
    return "生成 overview（2-3 段）、highlights（5-10 条）、background（2-4 段）。"


def _parse_summary_payload(text: str, *, summary_type: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {"overview": "", "highlights": [], "background": ""}
    payload: Any = None
    try:
        payload = json.loads(raw)
    except ValueError as e:
        # 第 3 档：模型直接回散文是预期的降级路径，不是错误——但它得留痕，
        # 否则「为什么这本书的 highlights 永远是空的」无从查起。
        # 只吞 JSONDecodeError（ValueError 子类）：RecursionError / MemoryError
        # 这类「不是散文，是出事了」的失败必须冒上去，不然用户拿到的是一段被
        # 当成 overview 的括号。字段组装也因此移出 try——它出错是我们的 bug。
        ai_logger.debug("summary reply is not JSON (summary_type=%s): %s", summary_type, e)

    if isinstance(payload, dict):
        overview = str(payload.get("overview") or "")
        background = str(payload.get("background") or "")
        highlights_raw = payload.get("highlights") or []
        highlights = [str(x) for x in highlights_raw] if isinstance(highlights_raw, list) else []
        return {"overview": overview, "highlights": highlights, "background": background}
    if payload is not None:
        ai_logger.debug(
            "summary reply parsed as %s, not an object (summary_type=%s)",
            type(payload).__name__,
            summary_type,
        )

    st = (summary_type or "full").strip().lower()
    if st == "highlights":
        lines = [ln.strip(" \t-•*") for ln in raw.splitlines() if ln.strip()]
        highlights = [ln for ln in lines if ln][:10]
        return {"overview": "", "highlights": highlights, "background": ""}
    if st == "background":
        return {"overview": "", "highlights": [], "background": raw}
    return {"overview": raw, "highlights": [], "background": ""}


@app.post("/api/ai/rag/retrieve")
async def api_ai_rag_retrieve(body: AIRagRequest):
    try:
        book_folder = book_uuid_resolver.folder_for_book_uuid(body.book_uuid)
    except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，解析不出 book_uuid 即「这本书不存在」→404；类型待收窄为 (KeyError, ValueError)
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        passages, retrieval_time_ms = await run_in_threadpool(
            retrieve_passages,
            book_folder,
            books_dir=BOOKS_DIR,
            query=body.query,
            k=body.k,
            min_similarity=body.min_similarity,
        )
        return {"passages": passages, "retrieval_time_ms": retrieval_time_ms}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/ai/summary/{book_uuid}")
async def api_ai_summary(
    request: Request,
    book_uuid: str,
    body: AISummaryRequest,
    summary_type: str = "full",
    force_regenerate: bool = False,  # cache is frontend-side for v1
):
    try:
        book_folder = book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，解析不出 book_uuid 即「这本书不存在」→404；类型待收窄为 (KeyError, ValueError)
        raise HTTPException(status_code=404, detail="Book not found")

    provider_name, api_key, base_url, model, timeout_s = _get_provider_runtime(body.provider, body.model)
    queue_key = f"{book_uuid}:{provider_name}"

    async def _do() -> dict:
        book = await run_in_threadpool(load_book_cached, book_folder)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

        ctx_window = provider_context_window(provider_name, model)
        book_tokens, max_chapter_tokens = await run_in_threadpool(book_token_stats, book)
        decision = choose_routing(
            provider_ctx_window=ctx_window,
            book_tokens=book_tokens,
            max_chapter_tokens=max_chapter_tokens,
        )
        ai_logger.debug(
            "summary routing book_uuid=%s provider=%s model=%s mode=%s book_tokens=%s ctx_window=%s",
            str(book_uuid),
            provider_name,
            model,
            decision.mode,
            int(book_tokens),
            int(ctx_window),
        )

        try:
            passages, retrieval_time_ms = await run_in_threadpool(
                retrieve_passages,
                book_folder,
                books_dir=BOOKS_DIR,
                query="Summarize the entire book: main ideas, structure, themes, and key takeaways.",
                k=12,
                min_similarity=0.35,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))
        routing_meta: dict[str, Any] = {"mode": decision.mode, "provider_context_window": int(ctx_window)}
        if decision.mode == "full_book":
            context = await run_in_threadpool(build_full_book_context, book, budget_tokens=decision.budget_tokens)
        elif decision.mode == "multi_chapter":
            orders = unique_chapter_orders_from_passages(passages, limit=8)
            context, used_orders = await run_in_threadpool(
                build_multi_chapter_context, book, chapter_orders=orders, budget_tokens=decision.budget_tokens
            )
            routing_meta["chapters"] = used_orders
        else:
            context = "\n\n".join([f"[{p['chapter_order'] + 1}] {p['chapter_title']}\n{p['text']}" for p in passages])
        system = (
            "你是 Reader3 的 AI 阅读助手。默认用中文回答（如果用户明确用英文提问，则用英文）。"
            "请基于提供的书籍内容生成总结。"
            "严格输出 JSON，且仅输出 JSON。"
            "JSON 格式：{"
            '"overview": string, '
            '"highlights": string[], '
            '"background": string'
            "}。"
            + _summary_prompt(summary_type)
        )
        user = f"书籍内容（用于总结）：\n{context}\n"
        try:
            resp = await run_in_threadpool(
                _call_provider,
                provider_name,
                api_key=api_key,
                base_url=base_url,
                model=model,
                system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=body.max_tokens,
                timeout_s=timeout_s,
            )
        except Exception as e:
            if decision.mode in ("full_book", "multi_chapter"):
                ai_logger.debug(
                    "summary fallback to rag book_uuid=%s provider=%s error=%s",
                    str(book_uuid),
                    provider_name,
                    str(e),
                )
                rag_context = "\n\n".join([f"[{p['chapter_order'] + 1}] {p['chapter_title']}\n{p['text']}" for p in passages])
                rag_user = f"书籍片段（用于总结）：\n{rag_context}\n"
                resp = await run_in_threadpool(
                    _call_provider,
                    provider_name,
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    system=system,
                    messages=[{"role": "user", "content": rag_user}],
                    max_tokens=body.max_tokens,
                    timeout_s=timeout_s,
                )
                routing_meta["mode"] = "rag_fallback"
            else:
                raise
        payload = _parse_summary_payload(resp.text, summary_type=summary_type)
        return {
            "book_uuid": str(book_uuid),
            "content": payload,
            "provider": provider_name,
            "model": resp.model,
            "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "token_count": resp.token_count,
            "from_cache": False,
            "metadata": {
                "retrieval_time_ms": retrieval_time_ms,
                "finish_reason": resp.finish_reason,
                "routing": routing_meta,
            },
        }

    return await ai_queue.run(
        queue_key,
        request=request,
        timeout_s=float(timeout_s),
        request_label="summary",
        fn=_do,
    )


@app.post("/api/ai/question/{book_uuid}")
async def api_ai_question(request: Request, book_uuid: str, body: AIQuestionRequest, stream: bool = False):
    try:
        book_folder = book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，解析不出 book_uuid 即「这本书不存在」→404；类型待收窄为 (KeyError, ValueError)
        raise HTTPException(status_code=404, detail="Book not found")

    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    if len(question) > 1000:
        raise HTTPException(status_code=400, detail="question too long (max 1000 chars)")

    provider_name, api_key, base_url, model, timeout_s = _get_provider_runtime(body.provider, body.model)
    queue_key = f"{book_uuid}:{provider_name}"

    if stream:
        # 租约的**唯一**释放点在这个栈上（下面 push_async_callback 注册的
        # ``_release_lease``）。以前这里是三处散落的显式 release，各自兜一种具体
        # 异常——而 acquire 到 return 之间的那一大段还会抛别的：任何一种没被点名的
        # 异常都带着租约逃走，那条队列于是永久 active（C4）。
        #
        # 为什么必须是栈而不是一个 try/finally：租约的生命周期跨越「函数返回」这
        # 条界——正常路径上它要活到 SSE 流结束为止。``pop_all()`` 把待办的释放动作
        # **移交**给生成器；移交发生在最后一步，在那之前的任何异常都由这里的
        # ``async with`` 收尾，移交之后这里关的是一个空栈。
        #
        # 后压进去的回调先跑（LIFO），所以生成器里压的「停 worker」一定跑在
        # 「放租约」之前——顺序即语义：租约放掉就等于允许下一个请求开始。
        lease_stack = contextlib.AsyncExitStack()
        async with lease_stack:
            lease = await ai_queue.acquire(
                queue_key,
                request=request,
                timeout_s=float(timeout_s),
                request_label="question",
            )

            async def _release_lease() -> None:
                await ai_queue.release(lease)

            lease_stack.push_async_callback(_release_lease)

            book = await run_in_threadpool(load_book_cached, book_folder)
            if not book:
                raise HTTPException(status_code=404, detail="Book not found")

            try:
                passages, retrieval_time_ms = await run_in_threadpool(
                    retrieve_passages,
                    book_folder,
                    books_dir=BOOKS_DIR,
                    query=question,
                    k=body.rag_k,
                    min_similarity=0.35,
                )
            except RuntimeError as e:
                raise HTTPException(status_code=400, detail=str(e))

            ctx_window = provider_context_window(provider_name, model)
            book_tokens, max_chapter_tokens = await run_in_threadpool(book_token_stats, book)
            decision = choose_routing(
                provider_ctx_window=ctx_window,
                book_tokens=book_tokens,
                max_chapter_tokens=max_chapter_tokens,
            )
            ai_logger.debug(
                "question routing book_uuid=%s provider=%s model=%s mode=%s book_tokens=%s ctx_window=%s stream=1",
                str(book_uuid),
                provider_name,
                model,
                decision.mode,
                int(book_tokens),
                int(ctx_window),
            )
            if decision.mode == "full_book":
                context = await run_in_threadpool(build_full_book_context, book, budget_tokens=decision.budget_tokens)
            elif decision.mode == "multi_chapter":
                orders = unique_chapter_orders_from_passages(passages, limit=8)
                context, _used = await run_in_threadpool(
                    build_multi_chapter_context, book, chapter_orders=orders, budget_tokens=decision.budget_tokens
                )
            else:
                context = "\n\n".join([f"[{p['chapter_order'] + 1}] {p['chapter_title']}\n{p['text']}" for p in passages])
            history = (body.conversation_history or [])[-50:]
            chat_history = []
            for m in history:
                role = (m.role or "").strip().lower()
                if role not in ("user", "assistant"):
                    continue
                content = (m.content or "").strip()
                if not content:
                    continue
                chat_history.append({"role": role, "content": content})

            system = (
                "你是 Reader3 的 AI 阅读助手。"
                "只基于提供的书籍内容回答与书相关的问题；如果内容不足以回答，请明确说明需要更多上下文。"
                "回答要清晰、简洁。"
            )
            user = f"书籍内容（用于回答）：\n{context}\n\n问题：{question}\n"

            message_id = str(__import__("uuid").uuid4())
            started = time.perf_counter()
            answer_parts: list[str] = []
            conversation_id = _conversation_id_from_history(history)

            async def event_gen(lease_stack: contextlib.AsyncExitStack):
                q: asyncio.Queue[dict] = asyncio.Queue()
                loop = asyncio.get_running_loop()
                stop_event = threading.Event()

                def push(evt: dict) -> None:
                    _push_event(q, evt)

                def worker_ollama() -> None:
                    url = _ollama_root_base_url(base_url or "http://localhost:11434") + "/api/chat"
                    chat_messages = []
                    if system:
                        chat_messages.append({"role": "system", "content": system})
                    chat_messages.extend([*chat_history, {"role": "user", "content": user}])
                    payload = {
                        "model": model,
                        "messages": chat_messages,
                        "stream": True,
                        "options": {"num_predict": max(64, min(int(body.max_tokens), 4096))},
                    }
                    model_out = model
                    finish_reason = "stop"
                    try:
                        # post_stream 交出的是**还没读**的 response：下面这个循环仍然逐行读，
                        # 每行之前检查 stop_event。换成 post_json 就等于先把整段回答读完
                        # 再开始推 chunk，断连之后也停不下来。
                        with _egress_post_stream(url, payload=payload, timeout_s=int(timeout_s)) as resp:
                            while True:
                                # 客户端走了或者超时了：别再往一个没人读的队列里推，
                                # 也别继续跟 provider 说话。检查放在读之前，所以
                                # 「停」最迟在下一行数据到达时生效。
                                if stop_event.is_set():
                                    return
                                line = resp.readline()
                                if not line:
                                    break
                                raw = line.strip()
                                if not raw:
                                    continue
                                try:
                                    obj = json.loads(raw.decode("utf-8", errors="replace") or "{}")
                                except Exception:  # noqa: BLE001 - 第 3 档：ollama 流里解析不了的一行直接跳过，下一行还会来；终止条件是 done 事件，不是这一行
                                    continue
                                if not isinstance(obj, dict):
                                    continue
                                if obj.get("model"):
                                    model_out = str(obj.get("model") or model_out)
                                msg = obj.get("message")
                                if isinstance(msg, dict):
                                    delta = msg.get("content")
                                    if delta:
                                        loop.call_soon_threadsafe(push, {"type": "chunk", "delta": str(delta)})
                                if obj.get("done") is True:
                                    finish_reason = str(obj.get("done_reason") or finish_reason)
                                    break
                        loop.call_soon_threadsafe(push, {"type": "done", "model": model_out, "finish_reason": finish_reason})
                    except Exception as e:  # noqa: BLE001 - 第 2 档：worker 线程的最外层，失败经 error 事件送到客户端，痕迹在 SSE 流里
                        if stop_event.is_set():
                            # 已经被叫停了：这个异常多半就是叫停造成的（连接被拆、
                            # 循环已关）。往一个没人读的队列里推 error 只会在
                            # worker 线程里再抛一次，那次没人接得住。
                            return
                        loop.call_soon_threadsafe(push, {"type": "error", "message": str(e)})

                async def worker_non_stream() -> None:
                    try:
                        resp = await run_in_threadpool(
                            _call_provider,
                            provider_name,
                            api_key=api_key,
                            base_url=base_url,
                            model=model,
                            system=system,
                            messages=[*chat_history, {"role": "user", "content": user}],
                            max_tokens=body.max_tokens,
                            timeout_s=timeout_s,
                        )
                    except Exception as e:  # noqa: BLE001 - 第 2 档：worker 协程的最外层，失败经 error 事件送到客户端，痕迹在 SSE 流里
                        await q.put({"type": "error", "message": str(e)})
                        return
                    await q.put({"type": "chunk", "delta": resp.text})
                    await q.put({"type": "done", "model": resp.model, "finish_reason": resp.finish_reason})

                # 租约从 handler 那边**移交**到这里；出这个 with 块就是放租约，
                # 无论是正常 return、客户端断连、超时，还是生成器被 aclose()。
                async with lease_stack:
                    yield _sse_event(
                        "meta",
                        {
                            "message_id": message_id,
                            "retrieval_sources": passages,
                            "metadata": {"retrieval_time_ms": retrieval_time_ms, "provider": provider_name},
                        },
                    )

                    # 停 worker 的回调**后**压栈，所以它**先**跑（LIFO）：租约必须
                    # 在 worker 真的停下之后才放，否则下一个「本该串行」的请求会
                    # 和上一个还活着的 worker 并发打同一个 provider（C5）。
                    if provider_name == "ollama":
                        thread = threading.Thread(target=worker_ollama, daemon=True)
                        thread.start()
                        lease_stack.push_async_callback(
                            _stop_stream_worker,
                            label="ollama question stream",
                            stop_event=stop_event,
                            thread=thread,
                        )
                    else:
                        task = asyncio.create_task(worker_non_stream())
                        lease_stack.push_async_callback(
                            _stop_stream_worker,
                            label="question stream",
                            stop_event=stop_event,
                            task=task,
                        )

                    while True:
                        if request is not None and await request.is_disconnected():
                            yield _sse_event("error", {"message": "Client disconnected"})
                            return
                        if time.monotonic() >= lease.deadline:
                            yield _sse_event("error", {"message": "AI request timed out"})
                            return
                        try:
                            evt = await asyncio.wait_for(q.get(), timeout=0.5)
                        except asyncio.TimeoutError:
                            continue

                        et = str(evt.get("type") or "")
                        if et == "chunk":
                            delta = str(evt.get("delta") or "")
                            answer_parts.append(delta)
                            yield _sse_event("chunk", {"delta": delta})
                            continue
                        if et == "done":
                            generation_time_ms = int((time.perf_counter() - started) * 1000)
                            if conversation_id:
                                ts = __import__("datetime").datetime.utcnow().isoformat() + "Z"
                                answer_text = "".join(answer_parts)
                                await run_in_threadpool(
                                    _save_conversation_snapshot,
                                    book_uuid=str(book_uuid),
                                    book_folder=book_folder,
                                    conversation_id=conversation_id,
                                    provider=provider_name,
                                    model=str(evt.get("model") or model),
                                    history=history,
                                    assistant_message=DiskConversationMessage(
                                        id=message_id,
                                        role="assistant",
                                        content=answer_text,
                                        timestamp=ts,
                                        metadata={
                                            "retrieval_sources": passages,
                                            "provider": provider_name,
                                        },
                                    ),
                                )
                            yield _sse_event(
                                "done",
                                {
                                    "model": str(evt.get("model") or model),
                                    "finish_reason": str(evt.get("finish_reason") or "stop"),
                                    "metadata": {
                                        "retrieval_time_ms": retrieval_time_ms,
                                        "generation_time_ms": generation_time_ms,
                                        "provider": provider_name,
                                    },
                                },
                            )
                            return
                        if et == "error":
                            yield _sse_event("error", {"message": str(evt.get("message") or "AI request failed")})
                            return

            # pop_all() 之后本层的 lease_stack 是空的，上面那个 async with 关它是
            # 个 no-op —— 租约的收尾责任已经在生成器手上。这一步必须是本分支的
            # 最后一步：在它之前抛的任何异常都还由这里负责释放。
            return StreamingResponse(event_gen(lease_stack.pop_all()), media_type="text/event-stream")

    async def _do() -> dict:
        book = await run_in_threadpool(load_book_cached, book_folder)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

        try:
            passages, retrieval_time_ms = await run_in_threadpool(
                retrieve_passages,
                book_folder,
                books_dir=BOOKS_DIR,
                query=question,
                k=body.rag_k,
                min_similarity=0.35,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))
        ctx_window = provider_context_window(provider_name, model)
        book_tokens, max_chapter_tokens = await run_in_threadpool(book_token_stats, book)
        decision = choose_routing(
            provider_ctx_window=ctx_window,
            book_tokens=book_tokens,
            max_chapter_tokens=max_chapter_tokens,
        )
        ai_logger.debug(
            "question routing book_uuid=%s provider=%s model=%s mode=%s book_tokens=%s ctx_window=%s stream=0",
            str(book_uuid),
            provider_name,
            model,
            decision.mode,
            int(book_tokens),
            int(ctx_window),
        )

        routing_meta: dict[str, Any] = {"mode": decision.mode, "provider_context_window": int(ctx_window)}
        if decision.mode == "full_book":
            context = await run_in_threadpool(build_full_book_context, book, budget_tokens=decision.budget_tokens)
        elif decision.mode == "multi_chapter":
            orders = unique_chapter_orders_from_passages(passages, limit=8)
            context, used_orders = await run_in_threadpool(
                build_multi_chapter_context, book, chapter_orders=orders, budget_tokens=decision.budget_tokens
            )
            routing_meta["chapters"] = used_orders
        else:
            context = "\n\n".join([f"[{p['chapter_order'] + 1}] {p['chapter_title']}\n{p['text']}" for p in passages])

        history = (body.conversation_history or [])[-50:]
        anthropic_history = []
        for m in history:
            role = (m.role or "").strip().lower()
            if role not in ("user", "assistant"):
                continue
            content = (m.content or "").strip()
            if not content:
                continue
            anthropic_history.append({"role": role, "content": content})

        system = (
            "你是 Reader3 的 AI 阅读助手。"
            "只基于提供的书籍内容回答与书相关的问题；如果内容不足以回答，请明确说明需要更多上下文。"
            "回答要清晰、简洁。"
        )
        user = f"书籍内容（用于回答）：\n{context}\n\n问题：{question}\n"

        started = time.perf_counter()
        try:
            resp = await run_in_threadpool(
                _call_provider,
                provider_name,
                api_key=api_key,
                base_url=base_url,
                model=model,
                system=system,
                messages=[*anthropic_history, {"role": "user", "content": user}],
                max_tokens=body.max_tokens,
                timeout_s=timeout_s,
            )
        except Exception as e:
            if decision.mode in ("full_book", "multi_chapter"):
                ai_logger.debug(
                    "question fallback to rag book_uuid=%s provider=%s error=%s",
                    str(book_uuid),
                    provider_name,
                    str(e),
                )
                rag_context = "\n\n".join([f"[{p['chapter_order'] + 1}] {p['chapter_title']}\n{p['text']}" for p in passages])
                rag_user = f"书籍片段（用于回答）：\n{rag_context}\n\n问题：{question}\n"
                resp = await run_in_threadpool(
                    _call_provider,
                    provider_name,
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    system=system,
                    messages=[*anthropic_history, {"role": "user", "content": rag_user}],
                    max_tokens=body.max_tokens,
                    timeout_s=timeout_s,
                )
                routing_meta["mode"] = "rag_fallback"
            else:
                raise
        generation_time_ms = int((time.perf_counter() - started) * 1000)

        msg_id = str(__import__("uuid").uuid4())
        conversation_id = _conversation_id_from_history(body.conversation_history or [])
        if conversation_id:
            ts = __import__("datetime").datetime.utcnow().isoformat() + "Z"
            await run_in_threadpool(
                _save_conversation_snapshot,
                book_uuid=str(book_uuid),
                book_folder=book_folder,
                conversation_id=conversation_id,
                provider=provider_name,
                model=resp.model,
                history=(body.conversation_history or [])[-50:],
                assistant_message=DiskConversationMessage(
                    id=msg_id,
                    role="assistant",
                    content=resp.text,
                    timestamp=ts,
                    metadata={
                        "retrieval_sources": passages,
                        "provider": provider_name,
                    },
                ),
            )
        return {
            "answer": resp.text,
            "message_id": msg_id,
            "retrieval_sources": passages,
            "metadata": {
                "token_count": resp.token_count,
                "model": resp.model,
                "finish_reason": resp.finish_reason,
                "retrieval_time_ms": retrieval_time_ms,
                "generation_time_ms": generation_time_ms,
                "provider": provider_name,
                "routing": routing_meta,
            },
        }

    return await ai_queue.run(
        queue_key,
        request=request,
        timeout_s=float(timeout_s),
        request_label="question",
        fn=_do,
    )

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
from .routers import notes as _notes_router  # noqa: E402
from .routers import search as _search_router  # noqa: E402

app.include_router(_library_router.router)
app.include_router(_reader_router.router)
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
