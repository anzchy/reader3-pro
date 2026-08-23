#!/usr/bin/env python3
"""把 wheel 装进干净 venv，起真服务，打四个路由——0.2 的第二重守卫。

`scripts/check_wheel_contents.py` 只回答「文件进没进 wheel」。它答不了
「装出来能不能跑」，而这两件事会分开坏：

- 2026-08-23 实测：`static/**/*` 修好之后，文件全都进了 wheel，内容检查全绿，
  但装出来 `/`、`/settings`、`/read/*` **每个 HTML 页面都 500**。原因与打包
  无关——`pyproject.toml` 的依赖没有上界，干净环境解析出 starlette **1.6.0**，
  而 `templates.TemplateResponse(name, context)` 这个旧签名在 1.x 里已被删除。
  仓库的 `uv.lock` 钉着 0.49.3，所以 `uv run` 与 CI 的 pytest 全程绿灯。

这条护栏的价值就在这个缺口上：**它是唯一一处依赖按最新版解析的地方**。
任何「依赖出大版本 → 装出来起不来／渲染不了」的问题，只有它看得见。

刻意的几个选择：

- **起真的 `reader3-server` 子进程**，不用 `fastapi.testclient`。TestClient 要
  httpx，那是间接依赖，装不装得到不该由这条护栏赌；而且真进程顺带验了 0.3 的
  `--port` 与入口点本身。
- **自己造一本合成 epub** 并用 `READER3_BOOKS_DIR` 指到临时目录。绝不读、更不写
  真的 `books/`——`process_epub()` 会在输出目录旁写 staging，让它靠近用户数据
  没有任何好处。
- **只用 stdlib 打请求**（urllib），护栏自身零依赖。
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"

# 起服务后等它监听的上限。冷启动要 import fastapi + ebooklib，机器慢时几秒。
STARTUP_TIMEOUT_S = 60


def _free_port() -> int:
    """要一个当下空闲的端口。

    不写死端口：开发者本地多半已经有个 8123 在跑，CI 上并发 job 也会撞。
    绑 0 让内核挑，关掉再交给服务用——有竞态窗口，但窗口是毫秒级，
    而写死端口是必然冲突。
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if proc.returncode != 0:
        print(f"命令失败：{' '.join(cmd)}", file=sys.stderr)
        print(proc.stdout[-2000:], file=sys.stderr)
        print(proc.stderr[-2000:], file=sys.stderr)
        raise SystemExit(1)
    return proc


def build_wheel(outdir: Path) -> Path:
    """打 wheel。清理与 check_wheel_contents.py 同理，原因见那里的注释。"""
    import shutil

    for stale in [ROOT / "build", *(ROOT / "src").glob("*.egg-info")]:
        if stale.is_dir():
            shutil.rmtree(stale)
    _run(["uv", "build", "--wheel", "-o", str(outdir)], cwd=ROOT)
    wheels = sorted(outdir.glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"期望恰好一个 wheel，实际 {len(wheels)} 个：{wheels}")
    return wheels[0]


def make_venv(venv: Path, wheel: Path) -> Path:
    """建干净 venv 并装 wheel。**不传 uv.lock**——按最新版解析正是本检查的目的。"""
    _run(["uv", "venv", str(venv)])
    _run(
        ["uv", "pip", "install", str(wheel)],
        env={**os.environ, "VIRTUAL_ENV": str(venv)},
    )
    py = venv / "bin" / "python"
    return py if py.exists() else venv / "Scripts" / "python.exe"


def build_book(py: Path, books_dir: Path, workdir: Path) -> str:
    """用 tests/fixtures 的合成 epub 造一本书，返回 book_id。"""
    epub_path = workdir / "smoke.epub"
    script = (
        "import sys; sys.path.insert(0, %r)\n"
        "from epub_builder import build_v1\n"
        "build_v1(%r)\n" % (str(FIXTURES), str(epub_path))
    )
    _run([str(py), "-c", script])
    _run(
        [str(py.parent / "reader3"), str(epub_path)],
        env={**os.environ, "READER3_BOOKS_DIR": str(books_dir)},
    )
    return "smoke_data"


def get(url: str, timeout: float = 10.0) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="reader3-wheel-smoke-") as tmp:
        work = Path(tmp)
        wheel = build_wheel(work / "dist")
        py = make_venv(work / "venv", wheel)
        books = work / "books"
        books.mkdir()
        book_id = build_book(py, books, work)

        port = _free_port()
        base = f"http://127.0.0.1:{port}"
        server = subprocess.Popen(
            [str(py.parent / "reader3-server"), "--port", str(port)],
            cwd=work,
            env={**os.environ, "READER3_BOOKS_DIR": str(books)},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            deadline = time.monotonic() + STARTUP_TIMEOUT_S
            ready = False
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    out = server.stdout.read() if server.stdout else ""
                    print("服务进程提前退出：\n" + out[-2000:], file=sys.stderr)
                    return 1
                try:
                    if get(f"{base}/api/health", timeout=2)[0] == 200:
                        ready = True
                        break
                except Exception:
                    time.sleep(0.5)
            if not ready:
                print(f"{STARTUP_TIMEOUT_S}s 内没等到 /api/health", file=sys.stderr)
                return 1

            # 四个路由，三个是模板渲染（500 的重灾区），一个是探针。
            checks = [
                ("/api/health", '"status":"ok"'),
                ("/", None),
                ("/settings", None),
                (f"/read/{book_id}/0", None),
            ]
            failures = []
            for path, needle in checks:
                status, body = get(base + path)
                if status != 200:
                    failures.append(f"{path} → {status}（前 200 字：{body[:200]!r}）")
                elif needle and needle not in body.replace(" ", ""):
                    failures.append(f"{path} → 200 但正文里找不到 {needle!r}")

            if failures:
                print("装出来的 wheel 起不来或渲染不了：", file=sys.stderr)
                for f in failures:
                    print("  - " + f, file=sys.stderr)
                out = server.stdout.read() if server.stdout else ""
                print("服务端输出尾部：\n" + out[-2000:], file=sys.stderr)
                return 1
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()

    print(
        f"\n0.2 装出来能跑：{wheel.name} 装进干净 venv（依赖按最新版解析），"
        f"/api/health、/、/settings、/read/{book_id}/0 四个路由全部 200。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
