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

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
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
def live_server(e2e_books_dir: Path) -> Iterator[str]:
    """起服务，等 `/api/health`，产出 base URL。

    端口是内核分配的空闲口，**不是 8123**：8123 上多半坐着开发者自己的服务，撞上
    去的表现是用例读到别人的书库，而不是一个干脆的报错。
    """
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    exe = Path(sys.executable).parent / "reader3-server"
    started = time.monotonic()
    server = subprocess.Popen(
        [str(exe), "--port", str(port)],
        env=_server_env(e2e_books_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = started + STARTUP_TIMEOUT_S
        ready = False
        while time.monotonic() < deadline:
            if server.poll() is not None:
                out, _ = server.communicate(timeout=10)
                pytest.fail(f"服务进程启动即退出（{server.returncode}）：\n{out}")
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
            out, _ = server.communicate(timeout=10)
            pytest.fail(f"{STARTUP_TIMEOUT_S}s 内没等到 /api/health：\n{out}")
        elapsed = time.monotonic() - started
        print(f"\n[e2e] 服务冷启动 {elapsed:.2f}s → {base}")
        yield base
    finally:
        # 先让进程退出再读 stdout：`.read()` 等的是 EOF，EOF 要等进程退出才来。
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)
