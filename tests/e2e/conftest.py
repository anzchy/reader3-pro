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
from typing import Iterator

import pytest

# 冷启动要 import fastapi + ebooklib + chromadb 依赖链，机器慢时几秒起步。
STARTUP_TIMEOUT_S = 60

BOOK_ID = "smoke_data"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _server_env(books_dir: Path) -> dict[str, str]:
    """开发者 shell 里的 reader3 配置一律不继承。

    `READER3_TOKEN` 会 401 掉所有写操作，`READER3_LIBRARY_UI=classic` 会换掉整个
    模板（那份模板一个 testid 都没有）。让测试的结果取决于跑它的人的 shell，是
    flaky 的第一来源。
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("READER3_")}
    env["READER3_BOOKS_DIR"] = str(books_dir)
    return env


@pytest.fixture(scope="session")
def e2e_books_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """一本合成的 EPUB 2 书，落在 tmp 下的书库里。

    绝不指向真实 `books/`：`process_epub()` 会对输出目录动 staging 与 rmtree。
    """
    from epub_corpus import build_epub2  # tests/fixtures 已在 sys.path 上

    from reader3_app.reader3 import process_epub

    root = tmp_path_factory.mktemp("e2e")
    books = root / "books"
    books.mkdir()
    epub_path = root / "smoke.epub"
    build_epub2(epub_path)
    process_epub(str(epub_path), str(books / BOOK_ID))
    return books


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
