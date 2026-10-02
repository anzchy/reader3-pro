"""017 WI-1 —— router 模块必须能在**全新进程里被第一个导入**。

审计 #7 / #20。拆 router（011 WI-4）之后留下一个只在特定导入顺序下才现形的环：
`routers/X` 在导入期 `from .. import server as _server`，而 `server` 在文件末尾立刻取
`routers.X.router` 来 `include_router`。正常路径（console 脚本先导入 `server`）不会炸，
所以整套测试都没碰到；但**谁先导入 router 谁就死**：

    AttributeError: partially initialized module 'reader3_app.web.routers.notes'
    has no attribute 'router' (most likely due to a circular import)

`routers/__init__.py` 的 docstring 原本写着「绑模块不绑属性，顺带解决了循环导入」——
那句话当时是错的：绑模块确实解决了 router 这一侧的需求，但没解决 `server` 那一侧，
它在导入期就要 `.router` 这个**属性**。

这条账不是学术问题，它有三个实际出口，本文件逐个钉住：

1. 任何以 router 为第一个导入的进程（工具脚本、`python -c`、REPL 排查）直接崩。
2. `tests/unit/test_exception_summary_payload.py` **单独跑**时收集阶段就 rc=2；
   它在整套 lane 里是绿的，因为别的文件先把 `server` 导进来了。一条只在
   「和别人一起跑」时才绿的测试，等于没有独立的判据。
3. `python -m reader3_app.web.server` 在 startup 之前就 AttributeError。

**为什么必须起子进程**：这三条量的都是「导入顺序」，而同一个解释器里
`sys.modules` 一旦有了 `server`，问题就被永久盖住。进程内怎么写都测不出来。
每个子进程都带有限超时——本仓不允许无界子进程（审计 #19 就是这条的反例）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: `server.py` 末尾 include 的全部 router 模块。少一个，这条守卫就漏一个。
ROUTER_MODULES = [
    "reader3_app.web.routers.library",
    "reader3_app.web.routers.library_books",
    "reader3_app.web.routers.reader",
    "reader3_app.web.routers.settings",
    "reader3_app.web.routers.health",
    "reader3_app.web.routers.notes",
    "reader3_app.web.routers.search",
    "reader3_app.web.routers.ai.chat",
    "reader3_app.web.routers.ai.conversations",
    "reader3_app.web.routers.ai.rag",
    "reader3_app.web.routers.ai.summary",
]

CIRCULAR = "partially initialized module"


def _run(args: list[str], timeout: float = 90.0) -> subprocess.CompletedProcess:
    """跑一个子解释器，带有限超时。超时要把已捕获的输出带出来，否则只剩一行 timeout。"""
    try:
        return subprocess.run(
            args,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:  # pragma: no cover - 只在真卡住时走到
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = (e.stderr or b"").decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        pytest.fail(f"子进程 {timeout}s 未结束：{args}\nstdout:\n{out}\nstderr:\n{err}")


def test_the_module_list_covers_every_router_server_includes():
    """守卫的守卫：`ROUTER_MODULES` 必须和 `server.py` 末尾 include 的那批一致。

    没有这一条，将来新加的 router 会悄悄漏出量程——而漏出去的那个恰恰是没人
    单独导入过的新模块，也就是最可能带环的那个。
    """
    server_src = (REPO_ROOT / "src" / "reader3_app" / "web" / "server.py").read_text(
        encoding="utf-8"
    )
    included = set()
    for line in server_src.splitlines():
        line = line.strip()
        if line.startswith("from .routers") and " import " in line:
            head, _, tail = line.partition(" import ")
            pkg = head[len("from ") :].replace(".routers", "reader3_app.web.routers")
            name = tail.split(" as ")[0].strip().rstrip("  # noqa: E402").strip()
            included.add(f"{pkg}.{name}" if not pkg.endswith(name) else pkg)
    assert included == set(ROUTER_MODULES), (
        "server.py include 的 router 与本文件的清单不一致。\n"
        f"只在 server.py 里：{sorted(included - set(ROUTER_MODULES))}\n"
        f"只在清单里：{sorted(set(ROUTER_MODULES) - included)}"
    )


@pytest.mark.parametrize("module", ROUTER_MODULES)
def test_a_router_can_be_the_first_module_imported(module: str):
    """每个 router 单独做「进程里第一个被导入的东西」，都必须成功。"""
    proc = _run([sys.executable, "-c", f"import {module}"])
    assert proc.returncode == 0, (
        f"{module} 不能作为首个导入：rc={proc.returncode}\n{proc.stderr}"
    )
    assert CIRCULAR not in proc.stderr, f"{module} 仍有循环导入：\n{proc.stderr}"


@pytest.mark.parametrize("module", ROUTER_MODULES)
def test_importing_a_router_first_still_assembles_the_whole_app(module: str):
    """不只是「不报错」——先导 router 之后，`server.app` 的路由必须照样装齐。

    只断言 rc=0 会被一个偷懒的修法满足：把 `include_router` 整段用 try/except
    包起来，导入不炸了，应用也空了。这条用路由条数把那条路堵死。
    """
    prog = (
        f"import {module}\n"
        "from reader3_app.web import server\n"
        "paths = {r.path for r in server.app.routes}\n"
        "assert '/api/health' in paths, paths\n"
        "print(len(server.app.routes))\n"
    )
    proc = _run([sys.executable, "-c", prog])
    assert proc.returncode == 0, f"{module} 先导入后应用装配失败：\n{proc.stderr}"
    assert int(proc.stdout.strip()) > 40, (
        f"先导入 {module} 之后路由数只有 {proc.stdout.strip()}，应用没装齐"
    )


def test_the_exception_summary_payload_file_collects_on_its_own():
    """审计 #20：这个文件单独跑时收集阶段就炸，只有和别人一起跑才绿。"""
    proc = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_exception_summary_payload.py",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        timeout=180.0,
    )
    assert proc.returncode == 0, (
        "单独收集 test_exception_summary_payload.py 失败："
        f"rc={proc.returncode}\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}"
    )
    assert CIRCULAR not in (proc.stdout + proc.stderr)


def test_running_the_server_module_reaches_its_own_argument_parsing():
    """`python -m reader3_app.web.server` 不得在 startup 之前就循环导入炸掉。

    故意喂一个非法端口：这样它会走到 `resolve_port` 的报错出口然后退出，
    既证明模块完整导入了，又不会真的把 uvicorn 起起来挂住测试。
    """
    proc = _run(
        [sys.executable, "-m", "reader3_app.web.server", "--port", "not-a-port"],
        timeout=120.0,
    )
    combined = proc.stdout + proc.stderr
    assert CIRCULAR not in combined, f"`python -m` 仍有循环导入：\n{combined}"
    assert "reader3-server:" in combined, (
        f"没有走到端口解析的报错出口，实际输出：\n{combined}"
    )
