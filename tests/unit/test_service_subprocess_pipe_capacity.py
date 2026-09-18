"""长命服务子进程不得把 stdout 接到管道上——管道有容量，写满就地阻塞。

跨波欠账 #10 的真正判据。那条欠账当初的结清判据是「`pytest tests/e2e --browser
chromium` 全绿」，而台账 `tasks/soak-log.md:219` 自己写着：**21 条用例时写不满
64 KiB，所以从没发作过**。也就是说那是一条**载荷相关的判据，用来守一条载荷相关
的缺陷**——等于没有守。缺陷今天没有任何回归闸，直到这一条。

缺陷的形状：`subprocess.Popen(..., stdout=subprocess.PIPE)` 起一条**长命服务**，
运行期没有人读那个管道。管道容量有限（macOS 65536 字节），uvicorn 的 access log
写满之后 `write()` 就地阻塞——服务不是崩了，是**卡在写日志上**，此后不再应答任何
请求。表现极具误导性：前若干条用例全绿，越过某一条之后每条要 `page.goto` 的用例
都 30 秒超时，而不碰网络的用例照常通过，红绿交错看着像随机 flaky。2026-09-03 实
测：修前 `6 failed, 29 passed in 187.12s`，修后 `35 passed in 19.01s`，一轮全量
服务端写了 74194 字节——是缓冲区的 1.13 倍。**用例数是压垮它的量，不是它的因。**

于是这道闸必须钉的是一条**类级规则**，而不是某一个现场：

    凡是用 `subprocess.Popen` 起 `reader3-server` 这类长命服务的地方，
    stdout（与 stderr）不得是 `subprocess.PIPE`。

规则的主语是「起的是长命服务」，**不是「用了 PIPE」**。这个区别是本文件的全部技
术含量所在：`scripts/soak_run.py:322` 用了 `stdout=subprocess.PIPE`，但它起的是
pytest 不是服务，而且紧接着 `:329` 就 `proc.communicate(timeout=...)`，**全程在
drain**——那是管道的**合法且正确**的用法。一条写成「禁用 PIPE」的闸会当场误杀它，
逼着下一个人把正确的代码改错，或者干脆把闸关掉。所以下面专门有一条用例反向钉住
「soak_run 必须判为不在范围内」。

判别手法是 AST 而不是真起进程：真起一条服务再往里灌 64 KiB 日志来复现阻塞，需要
几十秒并且本身就会挂死；而这条缺陷是**启动参数**的性质，在源码里就能判定。同仓
`tests/unit/test_e2e_server_env_isolation.py:287` 用的是同一种手法，理由相同。
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# 扫哪些目录。只扫仓库自己的代码；.venv / node_modules / designs 里的东西不是我们
# 的启动现场，扫了只会把闸的红变成噪音。
SCAN_DIRS = ("scripts", "src", "tests")

# 「这是一条长命服务」的标记。argv 里出现这个可执行名，就是起服务。
SERVICE_MARKERS = ("reader3-server",)

# 起进程的调用名。`subprocess.Popen` / 裸 `Popen` 两种写法都认。
_POPEN_ATTRS = {"Popen"}

# 名字解析的深度上限。防环，也防一路展开到整个模块把无关字符串卷进来。
_RESOLVE_DEPTH = 6


# ---------------------------------------------------------------------------
# 分类器
# ---------------------------------------------------------------------------


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for rel in SCAN_DIRS:
        root = REPO_ROOT / rel
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if any(part in {".venv", "venv", "node_modules", "__pycache__"} for part in path.parts):
                continue
            files.append(path)
    return files


def _assignments_in(scope: ast.AST) -> dict[str, list[ast.AST]]:
    """收集一个作用域里所有 `name = <expr>`，name → 各次赋值的右值。

    只用于把 argv 里的 `Name` 展开一层层看到底。不做真正的数据流分析：多次赋值时
    **全部**算数（宁可判成服务也不要漏判——漏判就是这道闸失效）。
    """
    table: dict[str, list[ast.AST]] = {}
    for node in ast.walk(scope):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None:
            targets = [node.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and node.value is not None:
                table.setdefault(target.id, []).append(node.value)
    return table


def _reachable_strings(
    node: ast.AST,
    scopes: list[dict[str, list[ast.AST]]],
    depth: int = 0,
    seen: set[int] | None = None,
) -> set[str]:
    """从 argv 表达式出发能触到的全部字符串常量，`Name` 顺着赋值展开。

    `tests/e2e/conftest.py` 写的是 `[str(exe), "--port", str(port)]`，可执行名藏在
    上一行的 `exe = Path(sys.executable).parent / "reader3-server"` 里；
    `tests/fixtures/deg_assertions.py` 更绕一层，argv 就是个光秃秃的 `cmd`。只看
    调用点的字面量，这两处都会漏判成「不是服务」，闸随即变成空转。
    """
    if depth > _RESOLVE_DEPTH:
        return set()
    seen = set() if seen is None else seen
    if id(node) in seen:
        return set()
    seen.add(id(node))

    found: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            found.add(sub.value)
        elif isinstance(sub, ast.Name):
            for scope in scopes:
                for value in scope.get(sub.id, []):
                    found |= _reachable_strings(value, scopes, depth + 1, seen)
    return found


def _argv_expr(call: ast.Call) -> ast.AST | None:
    if call.args:
        return call.args[0]
    for kw in call.keywords:
        if kw.arg == "args":
            return kw.value
    return None


def _is_pipe(node: ast.AST) -> bool:
    """这个表达式是不是 `subprocess.PIPE`。

    `subprocess.STDOUT`（把 stderr 并进 stdout）不是管道，是复制一个已有的 fd，
    不能算进来——三个合法现场全都用它。
    """
    if isinstance(node, ast.Attribute):
        return node.attr == "PIPE"
    if isinstance(node, ast.Name):
        return node.id == "PIPE"
    return False


class ServiceLaunch:
    """一处「起长命服务」的现场。"""

    def __init__(self, path: Path, lineno: int, piped: list[str]):
        self.path = path
        self.lineno = lineno
        self.piped = piped  # 接到 PIPE 上的流名，如 ["stdout"]

    @property
    def rel(self) -> str:
        return str(self.path.relative_to(REPO_ROOT))

    def __repr__(self) -> str:  # pragma: no cover - 只在断言信息里出现
        return f"{self.rel}:{self.lineno}"


def find_service_launches(source: str, path: Path) -> list[ServiceLaunch]:
    """源码里所有「起 reader3-server 这类长命服务」的 Popen 现场。

    返回的每一项都带上「哪些流被接到了 PIPE 上」，空列表即合规。
    """
    tree = ast.parse(source)
    module_scope = _assignments_in(tree)

    # 每个函数体各建一张表：argv 里的名字绝大多数是函数局部的。
    func_scopes: list[tuple[ast.AST, dict[str, list[ast.AST]]]] = [
        (node, _assignments_in(node))
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    launches: list[ServiceLaunch] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        is_popen = (
            isinstance(node.func, ast.Attribute) and node.func.attr in _POPEN_ATTRS
        ) or (isinstance(node.func, ast.Name) and node.func.id in _POPEN_ATTRS)
        if not is_popen:
            continue

        argv = _argv_expr(node)
        if argv is None:
            continue

        scopes = [
            table
            for func, table in func_scopes
            if any(inner is node for inner in ast.walk(func))
        ]
        scopes.append(module_scope)

        strings = _reachable_strings(argv, scopes)
        if not any(
            marker == s or s.endswith("/" + marker) or marker in s
            for s in strings
            for marker in SERVICE_MARKERS
        ):
            continue

        piped = [
            kw.arg
            for kw in node.keywords
            if kw.arg in {"stdout", "stderr"} and _is_pipe(kw.value)
        ]
        launches.append(ServiceLaunch(path, node.lineno, piped))
    return launches


def _all_service_launches() -> list[ServiceLaunch]:
    found: list[ServiceLaunch] = []
    for path in _iter_python_files():
        found.extend(find_service_launches(path.read_text(encoding="utf-8"), path))
    return found


# ---------------------------------------------------------------------------
# 主判据
# ---------------------------------------------------------------------------


def test_no_long_lived_service_launch_pipes_its_output():
    """类级规则：起长命服务的地方，stdout/stderr 不得是 `subprocess.PIPE`。

    这是 #10 唯一的回归闸。它对全仓生效，所以下一处这样起服务的代码——不管落在
    tests/ 还是 scripts/——一写出来就红，而不必等到某个套件恰好写满 64 KiB。
    """
    offenders = [launch for launch in _all_service_launches() if launch.piped]
    detail = "\n".join(
        f"  - {launch.rel}:{launch.lineno} → {'、'.join(launch.piped)}=subprocess.PIPE"
        for launch in offenders
    )
    assert offenders == [], (
        "下面这些地方用 `subprocess.PIPE` 起了长命服务，运行期又没有人 drain 那个管道：\n"
        f"{detail}\n"
        "管道容量有限（macOS 65536 字节）。服务写日志写满缓冲区之后 write() 就地阻塞，"
        "从此不再应答任何请求——不是崩溃，是静默卡死，表现成「越过某条用例之后全线超时」。"
        "改法见 tests/e2e/conftest.py:238/246：在临时目录开一个 log 文件句柄，"
        "stdout=log_fh、stderr=subprocess.STDOUT，失败时读文件尾巴。"
        "写进文件没有容量上限，也不需要另起线程去 drain。"
    )


# ---------------------------------------------------------------------------
# 闸自身的两条守卫：它得认得出真现场，也不能误杀合法用法
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel",
    [
        "tests/e2e/conftest.py",
        "tests/fixtures/deg_assertions.py",
        "scripts/smoke_installed_wheel.py",
    ],
)
def test_the_gate_recognises_every_known_service_launch(rel):
    """三处已知的真服务现场都必须被认出来。

    没有这一条，上面那条主判据可以用最廉价的方式变绿：让分类器谁也认不出来，
    `offenders` 恒为空列表。闸空转和闸通过在输出上完全同形。

    **这里刻意不钉行号。** 初版钉的是 `(文件, 行号)`，理由是「现场挪了位置就该来看
    一眼」。那条理由在本仓不成立：它在诞生的同一个工作项里就烂了一次——把 `Popen`
    上方加了注释和 log 文件的开启，现场下移 22 行，断言随即转红，而它印出来的话是
    「分类器要么退化成了谁也不认」。对「有人在上面加了段注释」这个真实原因来说，
    那是最大程度的误导，而且逼着人去改一条已录红的断言。行号是坐标不是事实；这三个
    文件各自只有一处 `subprocess.Popen` 调用，所以「恰好认出一处」与原来的强度相同，
    少的只是会烂的那一半。
    """
    path = REPO_ROOT / rel
    launches = find_service_launches(path.read_text(encoding="utf-8"), path)
    assert len(launches) == 1, (
        f"{rel} 里的服务启动现场没有被认出来（找到 {launches}，期望恰好一处）。"
        "分类器要么退化成了谁也不认，要么漏掉了名字解析这一层——"
        f"{rel} 的 argv 里可执行名是通过局部变量间接给进去的。"
    )


def test_the_gate_does_not_flag_the_drained_pytest_launch_in_soak_run():
    """`scripts/soak_run.py:322` 必须判在范围之外——它是管道的**正确**用法。

    那一处 `stdout=subprocess.PIPE` 起的是 pytest 不是服务，而且下一行就
    `proc.communicate(timeout=timeout)`，**全程在 drain**，永远不会被缓冲区憋住。
    这一条与主判据方向相反，钉的是规则的**主语**：如果有人图省事把规则写成
    「禁用 subprocess.PIPE」，主判据照样绿，而这一条会红。没有它，这道闸迟早会
    把正确的代码判成错的，然后被人整个关掉。
    """
    path = REPO_ROOT / "scripts" / "soak_run.py"
    launches = find_service_launches(path.read_text(encoding="utf-8"), path)
    assert launches == [], (
        f"soak_run.py 的进程启动被误判成了长命服务：{launches}。"
        "它起的是 pytest，且 communicate() 全程在读那个管道——这是合法用法。"
        "规则的主语必须是「起的是长命服务」，不是「用了 PIPE」。"
    )


def test_the_gate_still_has_teeth_on_a_fabricated_offender():
    """给分类器喂一段现造的违规源码，它必须报出来。

    主判据一旦修绿就永远是绿的，此后它证明不了自己还有牙。这一条不依赖仓库现状：
    哪怕将来全仓一处违规都没有，它仍然在证明「真出现违规时闸会红」。
    """
    fabricated = (
        "import subprocess\n"
        "from pathlib import Path\n"
        "def launch(py, port):\n"
        "    exe = Path(py).parent / 'reader3-server'\n"
        "    return subprocess.Popen(\n"
        "        [str(exe), '--port', str(port)],\n"
        "        stdout=subprocess.PIPE,\n"
        "        stderr=subprocess.STDOUT,\n"
        "    )\n"
    )
    launches = find_service_launches(fabricated, REPO_ROOT / "fabricated.py")
    assert len(launches) == 1, f"现造的违规现场没被认出来：{launches}"
    assert launches[0].piped == ["stdout"], (
        f"认出了现场却没认出它把 stdout 接到了管道上：{launches[0].piped}"
    )


def test_the_gate_accepts_a_file_handle_on_the_same_fabricated_site():
    """同一段源码只把 stdout 换成文件句柄，就必须放行。

    与上一条成对：证明这道闸区分的是**输出去了哪里**，而不是「这行代码起了服务」。
    否则修法就只剩「别起服务了」，那不是修。
    """
    fixed = (
        "import subprocess\n"
        "from pathlib import Path\n"
        "def launch(py, port, log_fh):\n"
        "    exe = Path(py).parent / 'reader3-server'\n"
        "    return subprocess.Popen(\n"
        "        [str(exe), '--port', str(port)],\n"
        "        stdout=log_fh,\n"
        "        stderr=subprocess.STDOUT,\n"
        "    )\n"
    )
    launches = find_service_launches(fixed, REPO_ROOT / "fabricated.py")
    assert len(launches) == 1, "改用文件句柄之后，这里仍然是一处服务启动现场"
    assert launches[0].piped == [], (
        f"stdout 是文件句柄却被判成了管道：{launches[0].piped}"
    )


# ---------------------------------------------------------------------------
# smoke 脚本的收尾语义：换输出来源，但别换掉 terminate→kill
# ---------------------------------------------------------------------------


def _load_smoke():
    path = REPO_ROOT / "scripts" / "smoke_installed_wheel.py"
    spec = importlib.util.spec_from_file_location("_smoke_installed_wheel", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeServer:
    """`Popen` 的替身，记录收到过哪些收尾动作。

    `wait_raises` 为真时第一次 `wait()` 抛 `TimeoutExpired`，用来逼出 kill 分支。
    """

    def __init__(self, wait_raises: bool = False):
        self.calls: list[str] = []
        self.wait_raises = wait_raises

    def terminate(self) -> None:
        self.calls.append("terminate")

    def kill(self) -> None:
        self.calls.append("kill")

    def wait(self, timeout=None):
        self.calls.append("wait")
        if self.wait_raises:
            self.wait_raises = False
            raise subprocess.TimeoutExpired(cmd="reader3-server", timeout=timeout or 0)
        return 0

    def communicate(self, timeout=None):
        self.calls.append("communicate")
        return "", ""


def test_smoke_stop_terminates_then_kills_a_stubborn_server():
    """2026-08-24 那次修复的语义要保住：先 terminate，赖着不走就 kill。

    本工作项换的是**输出从哪来**（管道 → 文件），不是**进程怎么收**。这一条是那
    次修复的留存守卫：它在改动前后都该绿，用来证明这次改动没有顺手把它推翻。
    """
    smoke = _load_smoke()
    server = _FakeServer(wait_raises=True)
    smoke.stop_server(server)
    assert "terminate" in server.calls, f"没有先 terminate：{server.calls}"
    assert "kill" in server.calls, (
        f"服务赖着不退出时没有升级到 kill：{server.calls}——"
        "CI 会挂在这里直到整个 job 超时"
    )
    assert server.calls.index("terminate") < server.calls.index("kill"), (
        f"kill 跑在了 terminate 前面：{server.calls}"
    )


def test_smoke_never_reads_a_live_servers_pipe():
    """收尾路径不得再对进程调 `communicate()` 取输出。

    `communicate()` 之所以出现在这里，正是因为输出在管道里、非等 EOF 不可；而等
    EOF 就要等进程退出，2026-08-24 就是这样挂死的。输出改成落文件之后，这个调用
    没有任何理由再存在——留着它就是把同一个坑留在原地。
    """
    smoke = _load_smoke()
    server = _FakeServer()
    smoke.stop_server(server)
    assert "communicate" not in server.calls, (
        f"收尾时仍然在读进程的管道：{server.calls}。"
        "服务输出已经落到文件里了，失败信息该从文件尾巴读，而不是 communicate()。"
    )
