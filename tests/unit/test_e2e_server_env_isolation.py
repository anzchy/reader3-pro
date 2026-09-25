"""e2e 服务子进程绝不继承开发者的真实 AI 配置。

`tests/e2e/conftest.py` 的 `_server_env()` 把 shell 里所有 `READER3_*` 一律剥掉，
再单独注回 `READER3_BOOKS_DIR`。剥离本身是对的（`READER3_TOKEN` 会 401 掉所有写
操作），但 `READER3_AI_SETTINGS` 被剥掉之后，`ai/config.py:10` 会**回落到默认值**
`config/ai_settings.json`——那是一个**相对路径**，在服务子进程的 cwd（= 仓库根）
下解析，正好落在开发者放着明文 API key 的那个文件上。

也就是说：剥离对 `READER3_TOKEN` 是「关掉一个开关」，对 `READER3_AI_SETTINGS`
却是「打开一个默认」。同一条剥离规则，两个相反的效果，这是它值得被单独钉住的
理由——读代码时 `_server_env` 看上去是纯粹在收紧。

后果不是理论上的：任何走 `/api/ai/*` 的 e2e 用例都会拿开发者本人的 key 去打真实
provider，花的是他的额度，而且请求内容会离开本机。009 的 X-1 是第一条会走到那里
的用例。

为什么这条测试在 unit lane 而不是 e2e lane：它验的是**启动前**如何构造环境，
纯函数，不需要浏览器。放进 e2e 就要先起一次服务才能测「服务不该被这样起」。
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
E2E_CONFTEST = REPO_ROOT / "tests" / "e2e" / "conftest.py"
REAL_AI_SETTINGS = REPO_ROOT / "config" / "ai_settings.json"


def _load_e2e_conftest():
    """直接按路径加载 e2e conftest。

    不能 `import conftest`：pytest 的 conftest 不在 `sys.path` 上，而且 unit lane
    与 e2e lane 各有一个同名文件。按绝对路径加载消除这个歧义。
    """
    spec = importlib.util.spec_from_file_location("_e2e_conftest", E2E_CONFTEST)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_server_env():
    return _load_e2e_conftest()._server_env


def test_ai_settings_path_is_pinned_into_the_sandbox(tmp_path):
    """`READER3_AI_SETTINGS` 必须被显式注入，且指向沙箱内。

    只断言「不等于真实路径」是不够的：变量**缺席**时也不等于真实路径，而缺席
    恰恰就是今天泄漏的形态（回落到默认值）。所以要正面断言它存在、且解析后落在
    沙箱里。
    """
    server_env = _load_server_env()
    books = tmp_path / "books"
    books.mkdir()

    env = server_env(books)

    assert "READER3_AI_SETTINGS" in env, (
        "READER3_AI_SETTINGS 没有被注入——服务子进程会回落到 config/ai_settings.json，"
        "也就是开发者存放明文 API key 的那个文件"
    )
    injected = Path(env["READER3_AI_SETTINGS"])
    assert injected.is_absolute(), (
        f"注入的必须是绝对路径：相对路径会在子进程 cwd（仓库根）下解析，绕回真实配置。实为 {injected}"
    )
    assert tmp_path in injected.resolve().parents, (
        f"AI 配置路径落在沙箱之外：{injected}（沙箱 {tmp_path}）"
    )


def test_real_ai_settings_is_unreachable_from_the_e2e_server(tmp_path):
    """把回落路径也算进来，最终解析结果不得等于仓库里的真实配置文件。

    这一条与上一条不重叠：上一条管「有没有注入」，这一条管「注入的值会不会碰巧
    仍指向真实文件」（比如有人把沙箱建在了 config/ 下面）。
    """
    server_env = _load_server_env()
    books = tmp_path / "books"
    books.mkdir()

    env = server_env(books)
    resolved = Path(env.get("READER3_AI_SETTINGS", "config/ai_settings.json"))
    if not resolved.is_absolute():
        # 复现子进程的解析规则：Popen 不传 cwd，继承 pytest 的 cwd。
        resolved = REPO_ROOT / resolved
    assert resolved.resolve() != REAL_AI_SETTINGS.resolve(), (
        f"e2e 服务会读到真实的 {REAL_AI_SETTINGS}——里面是明文 API key"
    )


def test_shell_ai_settings_is_overridden_not_inherited(tmp_path, monkeypatch):
    """shell 里已经设了 READER3_AI_SETTINGS 时，也必须被沙箱值覆盖。

    继承它一样是让测试结果取决于跑它的人的 shell——`_server_env` 的 docstring 说
    的正是这件事。
    """
    server_env = _load_server_env()
    outsider = tmp_path / "developers_own.json"
    outsider.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("READER3_AI_SETTINGS", str(outsider))

    books = tmp_path / "books"
    books.mkdir()
    env = server_env(books)

    assert "READER3_AI_SETTINGS" in env, "READER3_AI_SETTINGS 既没被继承也没被注入"
    assert Path(env["READER3_AI_SETTINGS"]) != outsider, (
        "shell 里的 READER3_AI_SETTINGS 被继承了"
    )


def test_no_other_reader3_var_leaks_through(monkeypatch, tmp_path):
    """既有保证的回归网：除显式注回的那几个，任何 READER3_* 都不得穿透。

    没有它，修这个 bug 的人可以把剥离改成白名单式的「只剥 READER3_TOKEN」，
    上面三条照样绿，而 READER3_ALLOWED_HOSTS 会让 Host 白名单拒掉 127.0.0.1 上的请求。
    （原先拿 READER3_LIBRARY_UI 举例；013 WI-13 删了那个开关，换成一个仍然存在的变量。）
    """
    server_env = _load_server_env()
    monkeypatch.setenv("READER3_TOKEN", "sekrit")
    monkeypatch.setenv("READER3_ALLOWED_HOSTS", "example.invalid")
    monkeypatch.setenv("READER3_BOOKS_DIR", "/definitely/not/here")

    books = tmp_path / "books"
    books.mkdir()
    env = server_env(books)

    assert "READER3_TOKEN" not in env, "READER3_TOKEN 穿透了——所有写操作会 401"
    assert "READER3_ALLOWED_HOSTS" not in env, "READER3_ALLOWED_HOSTS 穿透了——Host 白名单会拒掉测试服务"
    assert env["READER3_BOOKS_DIR"] == str(books), (
        f"READER3_BOOKS_DIR 没有被沙箱值覆盖：{env.get('READER3_BOOKS_DIR')}"
    )


# ---------------------------------------------------------------------------
# 启动路径本身（2026-09-05 审计 · HIGH）
# ---------------------------------------------------------------------------
#
# 上面四条全部直接调 `_server_env()`。它们证明的是「**如果**有人把 `_server_env()` 的
# 结果交给子进程，那份环境是干净的」，而**没有任何一条**证明 `live_server` 真的把它交了
# 出去。把 `subprocess.Popen(...)` 里的 `env=` 那个关键字删掉，上面四条照样全绿，服务
# 子进程却继承了开发者的整个 shell，`READER3_AI_SETTINGS` 缺席 ⇒ `ai/config.py` 回落到
# 相对路径 `config/ai_settings.json` ⇒ 读到开发者的明文 API key。那正是 acfc7ccf 修掉的
# 回归，而当时那次修复并没有留下能让它再红一次的守卫。
#
# 下面两条一起补这个洞，一行为、一结构：
#   * `test_live_server_hands_the_sanitised_env_to_the_subprocess` 真的把 `live_server`
#     这个 fixture 跑一遍（Popen 与健康探活都换成替身），检查**实际传给 Popen 的那份
#     环境**；
#   * `test_every_subprocess_launch_in_the_e2e_conftest_passes_an_env` 用 AST 扫同一个
#     文件，钉住「这里只有一处进程启动，且它带 env=」。
# 前者是主判据，后者防的是「fixture 拆包方式随 pytest 版本变了、行为条悄悄测不到东西」。


def _fixture_function(fixture):
    """从 `@pytest.fixture` 包出来的对象里取回原始函数。

    pytest 9 把 fixture 包成 `FixtureFunctionDefinition`（原函数在 `_fixture_function`），
    更早的版本直接返回被打了标记的函数。三种形态都试，一种都取不到就**失败**而不是跳过
    ——取不到意味着本条守卫失效了，那必须是红的。
    """
    for attr in ("_fixture_function", "__wrapped__"):
        candidate = getattr(fixture, attr, None)
        if callable(candidate):
            return candidate
    wrapped = getattr(fixture, "__pytest_wrapped__", None)
    if wrapped is not None and callable(getattr(wrapped, "obj", None)):
        return wrapped.obj
    if callable(fixture):
        return fixture
    raise AssertionError(
        f"取不到 live_server 的原始函数（拿到 {type(fixture)!r}）——pytest 换了 fixture 的"
        "包装形态，本条守卫已经失效，必须先修它"
    )


class _FakeProcess:
    """`Popen` 的替身：启动即就绪，terminate/wait 都是无操作。"""

    returncode = 0

    def poll(self):
        return None

    def terminate(self) -> None:
        return None

    def wait(self, timeout=None):
        return 0

    def kill(self) -> None:
        return None


class _FakeHealthResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


def test_live_server_hands_the_sanitised_env_to_the_subprocess(
    tmp_path, tmp_path_factory, monkeypatch
):
    """`live_server` 起子进程时，必须把**清洗过的环境**交给 `Popen`。

    这一条与上面四条的分工：它们管 `_server_env()` 算得对不对，这条管算出来的东西有没有
    被用上。判据落在**真正传给 Popen 的那个 dict** 上，而不是源码文本，所以「改成别的
    写法但同样清洗干净」不会误红，「忘了传 env」必红。

    shell 里预置两个 `READER3_*`：不预置的话，一台干净机器上「继承整个环境」与「传了清洗
    过的环境」这两种实现产出的 dict 里都没有 READER3_*，本条就抓不到东西。
    """
    mod = _load_e2e_conftest()
    monkeypatch.setenv("READER3_TOKEN", "sekrit")
    monkeypatch.setenv("READER3_AI_SETTINGS", str(REAL_AI_SETTINGS))

    books = tmp_path / "books"
    books.mkdir()
    recorded: dict = {}

    def fake_popen(argv, **kwargs):
        recorded["argv"] = argv
        recorded["kwargs"] = kwargs
        return _FakeProcess()

    monkeypatch.setattr(mod.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        mod.urllib.request, "urlopen", lambda *a, **kw: _FakeHealthResponse()
    )

    gen = _fixture_function(mod.live_server)(books, tmp_path_factory)
    try:
        base = next(gen)
        assert base.startswith("http://127.0.0.1:"), f"服务地址不是回环地址：{base}"
    finally:
        try:
            next(gen)
        except StopIteration:
            pass

    assert recorded, "live_server 根本没有启动子进程"
    assert "env" in recorded["kwargs"], (
        "`subprocess.Popen(...)` 没有传 `env=`——子进程继承了开发者的整个 shell。"
        f"READER3_AI_SETTINGS 于是缺席，ai/config.py 回落到相对路径 config/ai_settings.json，"
        f"服务会读到 {REAL_AI_SETTINGS}（明文 API key）。这正是 acfc7ccf 修掉的回归。"
        f" 实际传给 Popen 的关键字：{sorted(recorded['kwargs'])}"
    )

    env = recorded["kwargs"]["env"]
    assert isinstance(env, dict), f"传给 Popen 的 env 不是 dict：{type(env)!r}"

    assert "READER3_TOKEN" not in env, (
        "shell 里的 READER3_TOKEN 被传给了服务子进程——所有写操作会 401"
    )
    ai_settings = env.get("READER3_AI_SETTINGS")
    assert ai_settings, (
        "服务子进程的环境里没有 READER3_AI_SETTINGS——它会回落到 config/ai_settings.json"
    )
    resolved = Path(ai_settings)
    assert resolved.is_absolute(), f"AI 配置路径不是绝对路径：{resolved}"
    assert resolved.resolve() != REAL_AI_SETTINGS.resolve(), (
        f"服务子进程会读到真实的 {REAL_AI_SETTINGS}——里面是明文 API key"
    )
    assert tmp_path in resolved.resolve().parents, (
        f"AI 配置路径落在沙箱之外：{resolved}（沙箱 {tmp_path}）"
    )
    assert env.get("READER3_BOOKS_DIR") == str(books), (
        f"服务子进程的 READER3_BOOKS_DIR 不是沙箱书库：{env.get('READER3_BOOKS_DIR')}"
    )
    leaked = sorted(
        k for k in env
        if k.startswith("READER3_") and k not in {"READER3_BOOKS_DIR", "READER3_AI_SETTINGS"}
    )
    assert leaked == [], f"这些 READER3_* 穿透到了服务子进程：{leaked}"

    argv = recorded["argv"]
    assert "--port" in argv, f"启动命令里没有 --port，服务会去抢 8123：{argv}"


def test_every_subprocess_launch_in_the_e2e_conftest_passes_an_env():
    """结构面的同一条不变式：e2e conftest 里的每一处进程启动都必须带 `env=`。

    行为条是主判据，这条是它的备份，防两件事：一是有人**新加**第二处启动（行为条只跑
    `live_server` 一个 fixture，看不见新的那处）；二是 fixture 的拆包方式随 pytest 版本
    改变、行为条退化成测不到东西。纯静态，不起任何进程。
    """
    tree = ast.parse(E2E_CONFTEST.read_text(encoding="utf-8"))
    launches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Attribute) and node.func.attr in {"Popen", "run", "call", "check_call", "check_output"})
            or (isinstance(node.func, ast.Name) and node.func.id in {"Popen", "run"})
        )
    ]
    assert launches, (
        f"{E2E_CONFTEST} 里一处子进程启动都找不到——live_server 不再起真服务了？"
        "（那样的话本文件全部四条纯函数用例都在证明一个没人用的函数）"
    )
    missing = [node.lineno for node in launches if not any(kw.arg == "env" for kw in node.keywords)]
    assert missing == [], (
        f"tests/e2e/conftest.py 第 {missing} 行的子进程启动没有传 `env=`——"
        "子进程会继承开发者的 shell，READER3_AI_SETTINGS 缺席时回落到 "
        f"{REAL_AI_SETTINGS}（明文 API key）。"
    )
