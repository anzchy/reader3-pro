"""011 欠账 #40 的回归闸：`web/routers/**` 里的 `router` 必须带类型标注。

## 这条闸在防什么

011 把 `server.py` 的路由拆进 `web/routers/**`，拆法制造了一个循环导入：
`routers/*.py` 走 `from .. import server as _server`（这是打桩接缝的铁律，见
`tests/unit/test_server_patch_seam_ownership.py` 的 a12 / a15 两道静态闸），而
`server.py` 在文件底部反过来 import 这十个 router 模块。**循环是有意的，不拆。**

代价落在 mypy 上：在循环内部它推不出 `router = APIRouter()` 的类型，于是 `server.py`
里每一句 `app.include_router(_x_router.router)` 都报
`Cannot determine type of "router"  [has-type]`。实测 `master` 是
`Success: no issues found in 27 source files`，而 011 的 `eb8b60b` 是
`Found 10 errors in 1 file` —— 引入者是 `2c109c6`（WI-4/3 搬 library 组）。

**此前没有任何日常闸看得见它。** `.github/workflows/tests.yml:75` 的 mypy 步骤确实没有
`continue-on-error`，但那个 workflow 只认 `release.published` / `push.tags: v*` /
`workflow_dispatch`，所以这颗哑弹要等到发版当天才炸；011 的九条退出门槛里也没有一条
提到类型检查。这个文件就是补上那个洞。

## 为什么是两层闸，不是一层

`test_every_router_module_annotates_its_router` 是 AST 静态闸，零秒，而且说得出**是哪个
文件**忘了标注 —— 它防的是这一个具体形状的回潮。

`test_mypy_is_clean_on_src` 真跑一次 mypy，**这条才是权威判据**：标注写对了、循环里却冒出
下一个类型错时，AST 那条照样绿。代价实测：冷跑 15.07s（`--cache-dir` 指向空目录），
热跑 0.47s（`.mypy_cache` 命中）—— 日常紧循环里是后者。

两条都留着的理由是它们失效的方式不一样：AST 闸永远能跑（不依赖 mypy 装没装），mypy 闸
覆盖面更宽但依赖工具链。少了 AST 那条，将来某天 mypy 从 dev 组里掉出去，这个洞会无声
重开；少了 mypy 那条，闸就只认得见昨天那个 bug。
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTERS_DIR = REPO_ROOT / "src" / "reader3_app" / "web" / "routers"

# 写死这十个名字是故意的：发现逻辑自己坏掉时（走错目录、AST 形状变了），
# 一个「零个文件全部通过」的空闸和一个真通过的闸在输出上完全同形。
EXPECTED_ROUTER_MODULES = {
    "health.py",
    "library.py",
    "notes.py",
    "reader.py",
    "search.py",
    "settings.py",
    "ai/chat.py",
    "ai/conversations.py",
    "ai/rag.py",
    "ai/summary.py",
}


def _router_assignment(source: str) -> Optional[Tuple[str, Optional[str]]]:
    """模块级 `router = APIRouter(...)` 的形状。

    返回 `(kind, annotation)`：`kind` 是 ``"annotated"`` 或 ``"bare"``，
    `annotation` 是标注里那个名字（`APIRouter`）或 ``None``。
    模块里没有这样的赋值就返回 ``None`` —— 那不是 router 模块（例如 `__init__.py`）。

    只看**模块级**语句：函数体里造的临时 router 与循环导入无关，不是本闸的对象。
    """
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == "router":
                return ("annotated", ast.unparse(node.annotation))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "router":
                    return ("bare", None)
    return None


def _discover() -> List[str]:
    """返回相对 routers/ 的路径，只含真的声明了模块级 router 的文件。"""
    found = []
    for path in sorted(ROUTERS_DIR.rglob("*.py")):
        if _router_assignment(path.read_text(encoding="utf-8")) is not None:
            found.append(path.relative_to(ROUTERS_DIR).as_posix())
    return found


def test_the_gate_sees_every_router_module() -> None:
    """自检：发现逻辑必须刚好命中这十个模块，不多不少。

    多出来 ⇒ 有新 router 模块进来了，把它加进 EXPECTED 并确认它也带标注。
    少了 ⇒ 要么模块被删了（同样改 EXPECTED），要么发现逻辑坏了 —— 后者会让下面那条
    参数化闸退化成「零个参数、全部通过」，而那和真通过在输出上同形。
    """
    assert ROUTERS_DIR.is_dir(), f"routers 目录找不到：{ROUTERS_DIR}"
    discovered = set(_discover())
    assert discovered == EXPECTED_ROUTER_MODULES


@pytest.mark.parametrize("rel", _discover())
def test_every_router_module_annotates_its_router(rel: str) -> None:
    """`router = APIRouter()` 在循环导入里推不出类型，必须写成 `router: APIRouter = APIRouter()`。"""
    shape = _router_assignment((ROUTERS_DIR / rel).read_text(encoding="utf-8"))
    assert shape is not None, rel
    kind, annotation = shape
    assert kind == "annotated", (
        f"{rel} 的模块级 router 没有类型标注。routers/ 与 server.py 之间是循环导入，"
        f"mypy 在循环里推不出 APIRouter，结果会变成 server.py 上一条 "
        f'Cannot determine type of "router" [has-type]。写成 router: APIRouter = APIRouter()。'
    )
    assert annotation == "APIRouter", f"{rel} 标注的是 {annotation}，不是 APIRouter"


def test_the_gate_still_has_teeth_on_a_fabricated_offender() -> None:
    """定向破坏：伪造一个没标注的模块，判定函数必须认出来。

    没有这一条，上面那条参数化闸「全绿」既可能是十个文件都标注了，也可能是
    `_router_assignment` 变成了永远返回 annotated 的常量函数。
    """
    offender = "from fastapi import APIRouter\n\nrouter = APIRouter()\n"
    assert _router_assignment(offender) == ("bare", None)

    fixed = "from fastapi import APIRouter\n\nrouter: APIRouter = APIRouter()\n"
    assert _router_assignment(fixed) == ("annotated", "APIRouter")

    not_a_router_module = "from fastapi import APIRouter\n\ndef make():\n    router = APIRouter()\n    return router\n"
    assert _router_assignment(not_a_router_module) is None


def _render_mypy_failure(stdout: str, stderr: str) -> str:
    """把 mypy 的输出整理成失败信息，**并且去掉它最后那句汇总行**。

    去掉不是为了好看，是为了不喂坏 tdd-guardian 的收据。`lib/exec.js` 的 pytest 解析器
    用 `/(\\d+) errors?/i` 在**整段 lane 输出**上搜一次（而不是只看 pytest 的汇总行），
    命中 mypy 的 `Found 10 errors in 1 file` 就会当成「10 个 pytest error」加进计数。
    实测本文件首版记出来的红收据是「21 of 1566 tests failed」，而同一条 lane 命令
    手跑两次都是 **11 failed / 1543 passed / 2 skipped**。

    这里有两条泄漏路径，两条都要堵，**第二条才是主因**：

    1. 断言信息本身嵌了那句汇总行 —— 本函数负责滤掉（`Found ` / `Success: ` 开头的行）。
    2. **pytest 自己的断言解释行。** 写成 `assert proc.returncode == 0` 时，pytest 会打出
       ``where 1 = CompletedProcess(args=[...], stdout='...Found 10 errors in 1 file...')``
       —— 把整段被捕获的 stdout 顺着 repr 带进 lane 输出。只堵第一条时数字一点没变，
       就是因为这一条还开着。调用点因此先把退出码绑到局部变量再断言。

    判红本身没被影响（两次都是 assertion-failure），但收据里的数字是假的，而收据存在的
    意义就是留下可信的数字。逐条错误行全部保留 —— 它们的形状是 `path:line: error: ...`，
    `error` 前面没有数字，不会命中那条正则。
    """
    lines = [ln for ln in stdout.strip().splitlines()
             if not ln.startswith("Found ") and not ln.startswith("Success: ")]
    body = "\n".join(lines)
    tail = "\n--- stderr ---\n" + stderr.strip() if stderr.strip() else ""
    return f"mypy 判红，共 {len(lines)} 行（汇总行已略去，原因见 _render_mypy_failure）：\n{body}{tail}"


@pytest.mark.slow
def test_mypy_is_clean_on_src() -> None:
    """权威判据：`mypy src/` 必须干净。

    走 `sys.executable -m mypy` 而不是 `uv run mypy`：后者默认会重新解析并同步依赖，
    在测试里跑它既慢又可能改动 `.venv`。配置全部来自 `pyproject.toml` 的 `[tool.mypy]`，
    所以 cwd 必须是仓库根。

    mypy 缺席时这里**故意硬红而不是 skip**：它在 `[dependency-groups] dev` 里，
    lane 命令跑的是 `uv run pytest`（会同步 dev 组），缺了说明环境不对；skip 掉的话，
    这道闸会在没人注意的情况下变成零。
    """
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", "src/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert "No module named mypy" not in proc.stderr, (
        "mypy 没装。它在 [dependency-groups] dev 里，用 `uv sync --all-groups` 装齐，"
        "不要把这条测试 skip 掉。"
    )
    # 先绑局部变量再断言：直接写 `assert proc.returncode == 0` 会让 pytest 把整个
    # CompletedProcess（含被捕获的 mypy stdout）repr 进输出，理由见 _render_mypy_failure。
    returncode = proc.returncode
    assert returncode == 0, _render_mypy_failure(proc.stdout, proc.stderr)
