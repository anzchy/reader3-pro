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

import importlib.util
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
E2E_CONFTEST = REPO_ROOT / "tests" / "e2e" / "conftest.py"
REAL_AI_SETTINGS = REPO_ROOT / "config" / "ai_settings.json"


def _load_server_env():
    """直接按路径加载 e2e conftest，取出 `_server_env`。

    不能 `import conftest`：pytest 的 conftest 不在 `sys.path` 上，而且 unit lane
    与 e2e lane 各有一个同名文件。按绝对路径加载消除这个歧义。
    """
    spec = importlib.util.spec_from_file_location("_e2e_conftest", E2E_CONFTEST)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._server_env


def test_ai_settings_path_is_pinned_into_the_sandbox(tmp_path, monkeypatch):
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
    上面三条照样绿，而 READER3_LIBRARY_UI=classic 会换掉整个模板。
    """
    server_env = _load_server_env()
    monkeypatch.setenv("READER3_TOKEN", "sekrit")
    monkeypatch.setenv("READER3_LIBRARY_UI", "classic")
    monkeypatch.setenv("READER3_BOOKS_DIR", "/definitely/not/here")

    books = tmp_path / "books"
    books.mkdir()
    env = server_env(books)

    assert "READER3_TOKEN" not in env, "READER3_TOKEN 穿透了——所有写操作会 401"
    assert "READER3_LIBRARY_UI" not in env, "READER3_LIBRARY_UI 穿透了——会换掉整个模板"
    assert env["READER3_BOOKS_DIR"] == str(books), (
        f"READER3_BOOKS_DIR 没有被沙箱值覆盖：{env.get('READER3_BOOKS_DIR')}"
    )
