"""`scripts/check_router_size.py` 的判据必须落在模块上，且豁免必须会自己到期。

**这条门禁被写出来的原因**：「每个 router < 500 行」从 2026-08-16 写进计划
§8 到 2026-09-19 实测为止，CI 与 `scripts/` 里**没有任何一处在检查它**。
一条没人测量的门槛有两个后果，第二个更坏：没人知道达没达标（R-1/R-2 管这个），
以及**它的豁免永远不会到期**（R-5/R-6 管这个）。

所以这份测试里真正吃重的不是「大文件判红」那条，而是三条反向断言：

- **R-3**：`routers/` 下**不声明路由**的文件照样被数 —— 堵「把代码倒进
  `_helpers.py` 只为压线」。
- **R-6**：豁免的理由一旦不成立（那个大函数被分解了），门禁**转红并要求删掉
  豁免**。豁免到期不靠谁记得，靠这条断言。
- **R-7**：豁免指向的文件不存在时判 **FAIL 而不是跳过** —— 与
  `check_coverage_gate.py` 里「匹配到零个文件的 glob 判 FAIL」同一条道理：
  量不到的门槛不许假装通过。

脚本不是包，用 `importlib.util.spec_from_file_location` 从路径加载。被测的是
`check(repo_root)`，所有树都在 `tmp_path` 下现造，**绝不读仓库里真的
`src/reader3_app/web/`**（那棵树正在 WI-4 里被改，拿它当夹具等于让测试随重构漂）。
唯一的例外是 R-8，它只读真实的 `EXEMPTIONS` 常量，不读文件。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GATE_PATH = REPO_ROOT / "scripts" / "check_router_size.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("router_size_gate_under_test", GATE_PATH)
    assert spec is not None and spec.loader is not None, f"无法从 {GATE_PATH} 加载"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


def make_web_tree(root: Path) -> Path:
    """造一棵最小的 `src/reader3_app/web/`，返回 web 根。"""
    web = root / "src" / "reader3_app" / "web"
    (web / "routers").mkdir(parents=True)
    return web


def route_module(n_filler_lines: int, *, n_routes: int = 1) -> str:
    """一个声明了路由的模块，正文用注释撑到指定行数。"""
    head = ""
    for i in range(n_routes):
        head += f'@router.get("/api/x{i}")\nasync def api_x{i}():\n    return {{}}\n\n'
    filler = "\n".join(f"# filler {i}" for i in range(n_filler_lines))
    return head + filler + "\n"


def plain_module(n_filler_lines: int) -> str:
    """不声明任何路由的模块。"""
    return "\n".join(f"# filler {i}" for i in range(n_filler_lines)) + "\n"


def module_with_big_function(n_body_lines: int) -> str:
    """顶层有一个指定行数的函数，且声明了一条路由。"""
    body = "\n".join(f"    x = {i}" for i in range(n_body_lines))
    return (
        '@router.post("/api/big")\n'
        "async def api_big():\n" + body + "\n    return {}\n"
    )


# --------------------------------------------------------------------------
# R-1 / R-2：通用上限本身
# --------------------------------------------------------------------------


def test_R1_声明路由的大模块判红并报出行数(gate, tmp_path, monkeypatch):
    web = make_web_tree(tmp_path)
    (web / "server.py").write_text(route_module(700), encoding="utf-8")
    monkeypatch.setattr(gate, "EXEMPTIONS", ())

    failures = gate.check(tmp_path)

    assert len(failures) == 1, failures
    assert "server.py" in failures[0]
    # 行数与上限都要出现在消息里：只说「太大了」的门禁没法直接指导下一步
    assert "500" in failures[0]


def test_R2_刚好压线的模块放行(gate, tmp_path, monkeypatch):
    web = make_web_tree(tmp_path)
    src = route_module(1)
    # 精确造一个 500 行的文件：门槛是 `> 500` 判红，500 本身必须通过
    body = src.rstrip("\n").split("\n")
    body += [f"# pad {i}" for i in range(500 - len(body))]
    (web / "routers" / "notes.py").write_text("\n".join(body) + "\n", encoding="utf-8")
    monkeypatch.setattr(gate, "EXEMPTIONS", ())

    assert gate.check(tmp_path) == []


# --------------------------------------------------------------------------
# R-3 / R-4：判据落在模块上，不落在包上
# --------------------------------------------------------------------------


def test_R3_routers下不声明路由的文件照样被数(gate, tmp_path, monkeypatch):
    """堵「把代码倒进 `_helpers.py` 只为压线」。"""
    web = make_web_tree(tmp_path)
    (web / "routers" / "ai.py").write_text(route_module(100), encoding="utf-8")
    (web / "routers" / "_helpers.py").write_text(plain_module(900), encoding="utf-8")
    monkeypatch.setattr(gate, "EXEMPTIONS", ())

    failures = gate.check(tmp_path)

    assert len(failures) == 1, failures
    assert "_helpers.py" in failures[0], "倒进不声明路由的文件就能压线 —— 门禁被绕过了"


def test_R4_薄聚合入口救不了超标的同级文件(gate, tmp_path, monkeypatch):
    """`__init__.py` 只有几十行，不构成「ai 组达标」的证据。"""
    web = make_web_tree(tmp_path)
    (web / "routers" / "ai").mkdir()
    (web / "routers" / "ai" / "__init__.py").write_text(plain_module(20), encoding="utf-8")
    (web / "routers" / "ai" / "chat.py").write_text(route_module(800), encoding="utf-8")
    monkeypatch.setattr(gate, "EXEMPTIONS", ())

    failures = gate.check(tmp_path)

    assert len(failures) == 1, failures
    assert "chat.py" in failures[0]


def test_R4b_web下不声明路由也不在routers下的文件不被数(gate, tmp_path, monkeypatch):
    """反向闸：本门禁管的是 router 体量，不是「`web/` 下所有文件都得小」。

    没有这条，任何一个大模板助手都会被误杀，而误杀会让人把门禁关掉。
    """
    web = make_web_tree(tmp_path)
    (web / "routers" / "notes.py").write_text(route_module(50), encoding="utf-8")
    (web / "templating.py").write_text(plain_module(900), encoding="utf-8")
    monkeypatch.setattr(gate, "EXEMPTIONS", ())

    assert gate.check(tmp_path) == []


# --------------------------------------------------------------------------
# R-5 / R-6 / R-7：豁免
# --------------------------------------------------------------------------


def test_R5_具名豁免只抬高它点名的那一个文件(gate, tmp_path, monkeypatch):
    web = make_web_tree(tmp_path)
    (web / "routers" / "ai").mkdir()
    (web / "routers" / "ai" / "chat.py").write_text(
        module_with_big_function(520), encoding="utf-8"
    )
    (web / "routers" / "ai" / "summary.py").write_text(route_module(520), encoding="utf-8")
    monkeypatch.setattr(
        gate,
        "EXEMPTIONS",
        (
            gate.Exemption(
                rel_path="src/reader3_app/web/routers/ai/chat.py",
                max_lines=560,
                min_function_lines=400,
                reason="测试夹具",
            ),
        ),
    )

    failures = gate.check(tmp_path)

    assert len(failures) == 1, failures
    assert "summary.py" in failures[0], "豁免溢出到了同目录的别的文件"


def test_R6_大函数被分解之后豁免转红并要求删掉自己(gate, tmp_path, monkeypatch):
    """**到期条件。** 豁免不靠谁记得回来收，靠这条断言。"""
    web = make_web_tree(tmp_path)
    (web / "routers" / "ai").mkdir()
    # 文件仍在 560 以内不判超标，但里面最大的函数只剩 100 行 —— 开豁免的理由没了
    (web / "routers" / "ai" / "chat.py").write_text(
        module_with_big_function(100), encoding="utf-8"
    )
    monkeypatch.setattr(
        gate,
        "EXEMPTIONS",
        (
            gate.Exemption(
                rel_path="src/reader3_app/web/routers/ai/chat.py",
                max_lines=560,
                min_function_lines=400,
                reason="测试夹具",
            ),
        ),
    )

    failures = gate.check(tmp_path)

    assert len(failures) == 1, failures
    assert "到期" in failures[0]
    assert "删掉" in failures[0], "只说到期不说怎么办，下一个人还得回来读脚本"


def test_R7_豁免指向不存在的文件判红而不是跳过(gate, tmp_path, monkeypatch):
    """量不到的豁免判 FAIL —— 与 `check_coverage_gate.py` 的零匹配 glob 同理。"""
    web = make_web_tree(tmp_path)
    (web / "routers" / "notes.py").write_text(route_module(50), encoding="utf-8")
    monkeypatch.setattr(
        gate,
        "EXEMPTIONS",
        (
            gate.Exemption(
                rel_path="src/reader3_app/web/routers/ai/chat.py",
                max_lines=560,
                min_function_lines=400,
                reason="测试夹具",
            ),
        ),
    )

    failures = gate.check(tmp_path)

    assert len(failures) == 1, failures
    assert "不存在" in failures[0]


def test_R7b_web目录本身不存在时判红而不是通过(gate, tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "EXEMPTIONS", ())

    failures = gate.check(tmp_path)

    assert len(failures) == 1, failures
    assert "FAIL" in failures[0] or "找不到" in failures[0]


# --------------------------------------------------------------------------
# R-8：仓库里真的那条豁免，形状必须合法
# --------------------------------------------------------------------------


def test_R8_仓库里的豁免只有一条且上限不超过裁定值(gate):
    """011 §5 写的是「只许下调，不许上调」。这条让上调当场失败。"""
    assert len(gate.EXEMPTIONS) == 1, (
        "豁免只许有一条（011 §5「不设第二条例外」）。要加第二条，先改计划再改这里。"
    )
    only = gate.EXEMPTIONS[0]
    assert only.rel_path == "src/reader3_app/web/routers/ai/chat.py"
    # 上界跟着实测值往下走：拆完 chat.py 是 547 行，N 已从 560 下调到 550。
    # 这条断言也跟着收紧——棘轮只有在每次下调后都收一次，才真的是棘轮。
    assert only.max_lines <= 550, "011 §5：N 只许下调，不许上调"
    assert only.min_function_lines == 400
    assert only.reason.strip(), "豁免必须带理由，否则下一个人无法判断它该不该留"
