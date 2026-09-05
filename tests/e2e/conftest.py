"""E2E lane fixtures：起一个真服务，喂一本合成书。

**为什么服务是子进程，不是 `TestClient`。** `server.py` 在**模块导入时**把
`READER3_BOOKS_DIR` 读成模块级常量 `BOOKS_DIR`。同一个 Python 进程里换环境变量
再建 `TestClient` 不会改变它——测试会安静地打到开发者真实的 `books/` 上，而这套
用例将来要创建和删除标注。隔离只能靠「换环境变量 + 换进程」。

**为什么不用 `webServer`。** 那是 `@playwright/test`（Node）的配置键；本仓库用的是
`pytest-playwright`，没有这个键。配方照搬 `scripts/smoke_installed_wheel.py`——它
已经把「挑空闲端口 → `--port` → 轮询 `/api/health` → 收尾 drain」跑通过一遍了，
差别只是那边装 wheel，这边直接用 checkout 的 venv。

**为什么不设 `READER3_TOKEN`。** 008 的 `RequestGuardMiddleware` 里，令牌闸只要开
就作用于所有非豁免路径，而前端 fetch 至今不带令牌。设了它，页面上每个写操作都是
401——这不是在测应用，是在测守卫。同源浏览器流量本来就过得了 Origin 闸。
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
from typing import Callable, Iterator, Optional, Tuple

import pytest

# `tests/conftest.py` 把 `tests/fixtures` 插进 sys.path，且 root conftest 一定先于
# 本文件被 import，所以这里可以按裸模块名取语料 builder。
from epub_corpus import (  # type: ignore[import-not-found]
    build_cjk,
    build_epub2,
    build_epub3,
    build_huge_epub,
)
# 同一机制取 AI provider 桩（WI-16 · X-1）。桩模块不 import playwright，unit lane 也能用它。
from ai_stub import (  # type: ignore[import-not-found]
    RENDER_WAIT_TIMEOUT_S,
    STUB_GATE_TIMEOUT,
    OllamaStub,
)

# 冷启动要 import fastapi + ebooklib + chromadb 依赖链，机器慢时几秒起步。
STARTUP_TIMEOUT_S = 60

BOOK_ID = "smoke_data"
# 第二本书不是凑数：library.html 的 `{% for book in books %}` 会让 `lib-book-card` /
# `lib-book-row` 这两个 testid 字面量各渲出 N 个节点，靠 `data-book-id` 区分。书库只有
# 一本时，N 恒等于 1，「同名多节点必须带判别位」那条不变式的**分支永远走不到**——用例
# 会绿，但它证明的东西比它看起来的少得多。两本书才让那条路径真的被走过一遍。
BOOK_ID_2 = "second_data"

# 三本、四本？条数不写在任何断言里，只从 `E2E_BOOKS` 派生（矩阵 §WI-3：「从 fixture
# 常量取，不写字面量 4」）。再加一本书而没更新这张表，红的应该是那条书库条数用例；
# 把 4 焊死，红的会是「再加一本书」这个动作本身，而修法与被改的东西无关。
BOOK_ID_CJK = "cjk_data"
BOOK_ID_REPEAT = "repeat_data"

# `build_huge_epub` 的正文是同一句 `_HUGE_SENTENCE` 重复 N 遍 + 末尾一个 needle，
# 正是 W-10 要的「同章重复文本 + 末次出现有唯一后文」，且是给**已有** builder 传参数，
# 不是新建 builder。
#
# 1950 不是随手取的小值：`_HUGE_SENTENCE` 长 78 字符，`1950 == 78 * 25`，所以正文恰好
# 是 25 遍完整句子 + `SENTINEL`，**末次出现不会被 `body[:chars]` 截断**。取 2000 会在
# 第 26 遍的第 50 字处截断成 `"…the mast swung" + "SENTINEL"`——仍然唯一，但形状脆且
# 难解释。选 78 的整数倍是让 W-10 的 suffix 稳定为
# `" swung across the deck once more. SENTINEL"`（42 字符 < `createAnnotation` 的
# 50 字符窗口，因此完整落库）。
REPEAT_BOOK_CHARS = 1950
REPEAT_BOOK_NEEDLE = "SENTINEL"


def _repeat_book(path: Path) -> Path:
    return build_huge_epub(path, chars=REPEAT_BOOK_CHARS, needle=REPEAT_BOOK_NEEDLE)


#: 书库的**唯一定义处**：`(书库目录名, 造 epub 的 builder)`。
#:
#: 四本各自被谁用：
#:   * `smoke_data`   EPUB2  —— smoke、W-1…W-8、K 系列的主力语料；
#:   * `second_data`  EPUB3  —— 书库多节点判别位那条分支的第二本（见 `BOOK_ID_2`）；
#:   * `cjk_data`     CJK    —— W-9 的 quote/prefix/suffix 多字节边界；
#:   * `repeat_data`  重复文本 —— W-10 的同章重复文本消歧。
E2E_BOOKS: Tuple[Tuple[str, Callable[[Path], Path]], ...] = (
    (BOOK_ID, build_epub2),
    (BOOK_ID_2, build_epub3),
    (BOOK_ID_CJK, build_cjk),
    (BOOK_ID_REPEAT, _repeat_book),
)
E2E_BOOK_IDS: Tuple[str, ...] = tuple(name for name, _ in E2E_BOOKS)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _server_env(books_dir: Path) -> dict[str, str]:
    """开发者 shell 里的 reader3 配置一律不继承。

    `READER3_TOKEN` 会 401 掉所有写操作，`READER3_LIBRARY_UI=classic` 会换掉整个
    模板（那份模板一个 testid 都没有）。让测试的结果取决于跑它的人的 shell，是
    flaky 的第一来源。

    **但剥离不是对每个变量都等于收紧。** `READER3_AI_SETTINGS` 被剥掉之后，
    `ai/config.py` 的 `DEFAULT_SETTINGS_PATH` 会回落到 `config/ai_settings.json`
    ——那是**相对路径**，在服务子进程的 cwd（Popen 不传 cwd，继承 pytest 的 cwd，
    也就是仓库根）下解析，正好落在开发者放着明文 API key 的那个文件上。同一条
    剥离规则，对 TOKEN 是关掉一个开关，对 AI_SETTINGS 是打开一个默认。

    所以这一个必须**显式注回**沙箱内的绝对路径。指向的文件不必存在：
    `load_ai_settings()` 读不到文件时返回 `default_settings_dict()`（无 key），
    这正是 e2e 想要的确定态——不带 key 的 provider 会以「未配置」干净地拒绝，
    而不是拿谁的额度去打真实 provider。

    不变式钉在 `tests/unit/test_e2e_server_env_isolation.py`。
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("READER3_")}
    env["READER3_BOOKS_DIR"] = str(books_dir)
    env["READER3_AI_SETTINGS"] = str((books_dir.parent / "ai_settings.json").resolve())
    return env


@pytest.fixture(scope="session")
def e2e_books_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """`E2E_BOOKS` 里的每一本，落在 tmp 下的书库里。

    绝不指向真实 `books/`：`process_epub()` 会对输出目录动 staging 与 rmtree。

    **为什么是四本，不是一本。** 一本时 `library.html` 的 `{% for book in books %}`
    只渲出一个 `lib-book-card`，「同名多节点必须带判别位」那条不变式的**分支永远走不到**。
    两本让那条路径被走过一遍（`BOOK_ID_2`），CJK 与重复文本那两本则分别是 W-9 与 W-10
    的语料前提——它们不是凑数，是两组用例没有它就写不出来。

    四本全用**已有** builder，一个新的都不建：语料早就在
    `tests/fixtures/epub_corpus.py` 里，重复文本本只是给 `build_huge_epub` 传了个小
    `chars`。
    """
    from reader3_app.reader3 import process_epub

    root = tmp_path_factory.mktemp("e2e")
    books = root / "books"
    books.mkdir()
    for name, build in E2E_BOOKS:
        epub_path = root / f"{name}.epub"
        build(epub_path)
        process_epub(str(epub_path), str(books / name))
    return books


def _reset_notes(books_dir: Path) -> None:
    """把每本书的 `notes.json` 复位到缺省态——**不存在**。

    缺省态是「不存在」而不是「空对象」，因为那才是 `load_annotations` 唯一会返回 `[]`
    的合法状态；写一个 `{"annotations": []}` 进去只是多了一份必须与 schema 同步演化的
    赝品。

    **可以直接写文件，不必重启服务。** `notes_service` 每次请求都读盘，进程里没有任何
    标注缓存；服务进程级的常量只有 `BOOKS_DIR` 一个，而它指向的目录没变。这条事实是
    本 fixture 能做成 function 级的全部理由——它一旦不成立（比如有人给 notes 加了
    lru_cache），复位就必须变成重启服务，而那是 session 级的代价。
    """
    for book_id in E2E_BOOK_IDS:
        book_dir = books_dir / book_id
        for name in ("notes.json", "notes.json.lock"):
            (book_dir / name).unlink(missing_ok=True)


class NotesIsolation:
    """`notes.json` 的复位闸。用例拿到它是为了在**一条用例内部**跨轮次复位。"""

    def __init__(self, books_dir: Path) -> None:
        self.books_dir = books_dir

    def reset(self) -> None:
        _reset_notes(self.books_dir)


@pytest.fixture(autouse=True)
def notes_isolation(request: pytest.FixtureRequest) -> Iterator[Optional[NotesIsolation]]:
    """function 级、autouse：用例前后各把 `notes.json` 复位一次。

    **为什么必须有。** `live_server` 与 `e2e_books_dir` 都是 session 级共享的，而 W 系列
    会创建和删除标注。没有隔离就有跨用例污染，而污染的表现正是 flaky——flaky 会把
    Phase 3 的 soak 计数清零。前后各一次而不是只做一次：只做前置，最后一条用例的残留
    会留在 tmp 里误导事后排查；只做后置，一条中途崩掉的用例会把脏状态漏给下一条。

    **为什么按 `request.fixturenames` 决定要不要动手。** autouse 会作用到 `tests/e2e/`
    下**每一条**用例，包括 `test_testid_dom_uniqueness.py` 里那条既不起服务也不起浏览器
    的纯静态用例。无条件依赖 `e2e_books_dir` 会让那条用例平白付一次「造四本书 +
    process_epub」的开销。只有真的和服务打交道的用例（间接依赖 `live_server` 或直接
    要 `e2e_books_dir` 的）才需要隔离，也才付这个钱。
    """
    wants_server = "live_server" in request.fixturenames or "e2e_books_dir" in request.fixturenames
    if not wants_server:
        yield None
        return

    books_dir: Path = request.getfixturevalue("e2e_books_dir")
    _reset_notes(books_dir)
    try:
        yield NotesIsolation(books_dir)
    finally:
        _reset_notes(books_dir)


@pytest.fixture(scope="session")
def live_server(
    e2e_books_dir: Path, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[str]:
    """起服务，等 `/api/health`，产出 base URL。

    端口是内核分配的空闲口，**不是 8123**：8123 上多半坐着开发者自己的服务，撞上
    去的表现是用例读到别人的书库，而不是一个干脆的报错。

    **为什么日志落文件，而不是 `stdout=PIPE`。** 这条服务活满整个 session，谁也不在
    运行期读它的管道。管道是有容量的（macOS 上 64 KiB），uvicorn 的 access log 写满
    之后 `write()` 就地阻塞——服务不是崩了，是**卡在写日志上**，从此不再应答任何请求。
    表现极具误导性：前若干条用例全绿，越过某一条之后，**每一条要 `page.goto` 的用例都
    30 秒超时**，而不碰网络的用例照常通过，于是红绿交错，看着像随机 flaky。
    2026-09-03 本机就这样：套件从 21 条涨到 35 条，跨过了缓冲区，第 27 条之后全线超时；
    同样这六条单独跑却是 9 passed / 7.12s。**用例数是压垮它的量，不是它的因。**
    写进文件就没有容量上限，也不需要另起线程去 drain。
    """
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    exe = Path(sys.executable).parent / "reader3-server"
    log_path = tmp_path_factory.mktemp("e2e-server") / "server.log"
    started = time.monotonic()
    log_fh = log_path.open("w", encoding="utf-8")

    def _log_tail(limit: int = 4000) -> str:
        """日志尾巴。失败信息只需要最后这一截，整份可能有几百 KB。"""
        log_fh.flush()
        text = log_path.read_text(encoding="utf-8", errors="replace")
        return text[-limit:] if len(text) > limit else text

    server = subprocess.Popen(
        [str(exe), "--port", str(port)],
        env=_server_env(e2e_books_dir),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = started + STARTUP_TIMEOUT_S
        ready = False
        while time.monotonic() < deadline:
            if server.poll() is not None:
                pytest.fail(
                    f"服务进程启动即退出（{server.returncode}）：\n{_log_tail()}"
                )
            try:
                with urllib.request.urlopen(f"{base}/api/health", timeout=2) as r:
                    if r.status == 200:
                        ready = True
                        break
            except (urllib.error.URLError, ConnectionError, OSError):
                # 还没监听。这里不区分错误类型：区分了也只有一个动作——再等。
                time.sleep(0.1)
        if not ready:
            server.kill()
            server.wait(timeout=10)
            pytest.fail(f"{STARTUP_TIMEOUT_S}s 内没等到 /api/health：\n{_log_tail()}")
        elapsed = time.monotonic() - started
        print(f"\n[e2e] 服务冷启动 {elapsed:.2f}s → {base}（日志 {log_path}）")
        yield base
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)
        log_fh.close()
        print(f"\n[e2e] 服务日志 {log_path.stat().st_size} 字节 → {log_path}")


#: 服务跑在内核分配的空闲端口上，主机名恒为这三者之一。
_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@pytest.fixture
def context(context):  # type: ignore[no-untyped-def]
    """把浏览器的出网掐掉：只放行打到被测服务的请求。

    **这不是加固，是修一个真发生过的整套挂掉。** `reader.html` 与 `library.html` 的
    `<head>` 里各有一组指向 `fonts.googleapis.com` / `fonts.gstatic.com` 的
    `<link rel="stylesheet">`。它阻塞渲染，因而也阻塞 `load`——够不到那个域的机器上，
    `page.goto(..., wait_until="load")` 会**每次都**挂满 30 秒超时，然后整条用例红。
    2026-09-03 本机就这样：16 条用例各挂 30 秒，一轮 545 秒，而同一个 commit
    二十分钟前还是 21 passed / 32s。排查时最误导人的一点是 `curl` 说这个域可达——
    curl 走的是环境变量 `http_proxy`，chromium 走的是**系统代理**，两条路不是同一条。

    **为什么按「非本机一律 abort」写，而不是把那两个字体域列进黑名单。** 黑名单只挡
    今天已知的两个域；真正要钉的不变式是「e2e 只跟被测服务说话」。往模板里新加一个
    CDN 依赖，黑名单写法会让它继续走真网络——通了就悄悄通过（于是用例的绿依赖于跑它
    的人能上外网），不通就又是一轮 30 秒 × N。白名单写法让它立刻、确定地失败在
    「资源没加载」上，而不是失败在超时上，且失败信息里带着被拦的 URL。

    **为什么是 abort 而不是 fulfill 一个空响应。** 空 CSS 也是一次成功加载，页面会
    当作字体已就位；abort 让浏览器走它本来就有的降级路径（回落到 `font-family` 列表
    里的下一个），这才是没有外网时用户真实看到的那一页。

    非 http(s) 的 scheme（`data:` / `blob:`，epub.js 渲染正文时大量使用）一律放行——
    它们根本不出网，拦它们只会把渲染打断。
    """
    blocked: set[str] = set()

    def _gate(route, request) -> None:  # type: ignore[no-untyped-def]
        parsed = urlparse(request.url)
        if parsed.scheme not in ("http", "https") or parsed.hostname in _LOCAL_HOSTS:
            route.continue_()
            return
        blocked.add(f"{parsed.scheme}://{parsed.netloc}")
        route.abort()

    context.route("**/*", _gate)
    yield context
    if blocked:
        # 只报不判：拦掉哪些外部域是**事实**，该不该有是设计决定，不该由这里替谁做。
        print(f"\n[e2e] 已拦下的外部请求域：{sorted(blocked)}")


# ---------------------------------------------------------------------------
# AI provider 桩（WI-16 · X-1 AI SSE 流式）
# ---------------------------------------------------------------------------
#
# **桩为什么是 ollama 形状，不是 openai 形状（矩阵 §A）。** `server.py` 的 `event_gen`
# 里只有 `worker_ollama` 逐块推送（逐行读 NDJSON、每行推一个 `chunk` 事件）；所有其他
# provider 走 `worker_non_stream`，把整段回答作为**单个** `chunk` 事件推出。用 openai
# 形状的桩，`rd-ai-thread` 的 DOM 更新次数恒为 1，X-1a「增量渲染」不可能绿——那不是
# 实现有问题，是用例选错了 provider。附带收益：`ollama` 不在 `_provider_requires_api_key`
# 的集合里，沙箱 settings 不必编一个假 key；`_ollama_root_base_url` 会削掉结尾的 `/v1`，
# 桩的 `base_url` 直接写 `http://127.0.0.1:{port}` 即可；`validated_url` 允许 http + 任意
# 有 host 的地址，127.0.0.1 通得过出网闸。
#
# **为什么不需要给 `live_server` 加参数、也不需要第二个服务进程。** `_server_env` 已经把
# `READER3_AI_SETTINGS` 显式注回沙箱内的绝对路径（不变式钉在
# `tests/unit/test_e2e_server_env_isolation.py`），而 `load_ai_settings()` 是**每请求读盘**。
# 所以 X-1 只需要一个 **function 级 fixture** 在用例期间写那份文件、用完删掉。其他用例
# 看到的仍是「文件不存在 ⇒ `default_settings_dict()` ⇒ 无 key ⇒ provider 以未配置干净拒绝」
# 这个确定态。
#
# **桩由服务进程调用，不由浏览器调用。** 上面 `context` fixture 掐的是浏览器出网；服务
# 子进程打 127.0.0.1 上的桩不经过它。两者互不干涉。

#: 沙箱 settings 里 ollama 的 `model_name`。任意非空串即可（`get_provider_settings` 要求非空）。
AI_STUB_MODEL = "stub-model"

#: 沙箱 settings 里 ollama 的 `timeout_s`。它同时是三样东西的上界：`worker_ollama` 每次
#: `readline()` 的 socket 超时、队列租约的 deadline（`queue.py`：`acquire` 时刻 + timeout_s）、
#: 以及 X-1c 第二次提问在队列上等前一个租约的上限。
#:
#: 序关系：必须 **> STUB_GATE_TIMEOUT**（否则桩在 gate 上阻塞的那 5s 会被服务端当成 provider
#: 读超时，SSE 推 `error`，X-1a′ 的因果链在被测代码之外就断了）；必须 **< RENDER_WAIT_TIMEOUT_S**
#: （否则 X-1c「租约没释放」这个要抓的缺陷会表现为用例等待超时，而不是「第二次拿到了
#: `Error: AI request timed out`」这条可诊断的断言失败）。这不是给用例另起的一套超时——
#: 用例只用 `ai_stub.py` 里那三个常量；这是 settings 文件里一个字段的取值，写成常量是
#: 为了让它相对那三个常量的位置可被机器检查。
AI_STUB_PROVIDER_TIMEOUT_S = 10
assert STUB_GATE_TIMEOUT < AI_STUB_PROVIDER_TIMEOUT_S < RENDER_WAIT_TIMEOUT_S


def _reset_ai_conversations(books_dir: Path) -> None:
    """删掉每本书的 `ai_conversations/`——服务端在 SSE `done` 时与前端 PUT 同步时都会往这里写。

    复位到「不存在」，理由同 `_reset_notes`：那才是 `conversations.py` 唯一会返回空列表的
    合法状态。不复位的话，下一条用例打开面板时 `restoreConversation()` 会从磁盘捞回上一条
    用例的会话，`rd-ai-thread` 里于是先有了历史消息——`lastElementChild` 仍然取得对，但
    「第二次提问是同一面板里的新问题」这句就不再是从空线程起算的了。
    """
    for book_id in E2E_BOOK_IDS:
        shutil.rmtree(books_dir / book_id / "ai_conversations", ignore_errors=True)


@pytest.fixture
def ai_stub() -> Iterator[OllamaStub]:
    """function 级：一条用例一个桩，端口由内核分配，用完关掉。

    默认 `gate_mode=False`（四块一口气写完）；要握手的用例在拿到桩之后自己置
    `stub.gate_mode = True`，用完的 gate 由用例自己 `set()`。
    """
    with OllamaStub() as stub:
        yield stub


@pytest.fixture
def ai_settings_ollama(ai_stub: OllamaStub, e2e_books_dir: Path) -> Iterator[Path]:
    """把沙箱 `ai_settings.json` 写成「default_provider=ollama、enabled、base_url=桩地址」，用完删掉。

    路径与 `_server_env` 注入的 `READER3_AI_SETTINGS` **必须是同一个文件**，否则服务端读的是
    另一份而用例毫无察觉。这里不改 `_server_env`（本波它一行不动），而是在运行期比对一次：
    两处算出来的路径不同就当场 fail。

    产出的是文件路径，方便用例在失败信息里点名它。

    前后各复位一次 `ai_conversations/`：前置清掉上一条硬崩留下的残留，后置清掉本条自己写的
    ——与 `notes_isolation` 同款理由。
    """
    settings_path = (e2e_books_dir.parent / "ai_settings.json").resolve()
    injected = Path(_server_env(e2e_books_dir)["READER3_AI_SETTINGS"])
    if injected != settings_path:
        pytest.fail(
            f"ai_settings 路径与 _server_env 注入的不一致：fixture 写 {settings_path}，"
            f"服务读 {injected}。两处必须同一个文件。"
        )
    settings = {
        "default_provider": "ollama",
        "preferences": {"streaming_enabled": True},
        "providers": {
            "ollama": {
                "enabled": True,
                "base_url": ai_stub.base_url,
                "model_name": AI_STUB_MODEL,
                "timeout_s": AI_STUB_PROVIDER_TIMEOUT_S,
                "max_retries": 0,
            }
        },
    }
    _reset_ai_conversations(e2e_books_dir)
    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        yield settings_path
    finally:
        settings_path.unlink(missing_ok=True)
        _reset_ai_conversations(e2e_books_dir)
