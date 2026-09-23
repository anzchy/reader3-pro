"""011 WI-7 —— `chromadb` / `sentence-transformers` 必须是**可选** extra。

验收原文：「不装 ``[semantic]`` 时 ``import reader3_app`` 与全部非语义路由正常，
语义路由给出可读的降级提示而不是 ``ImportError`` 堆栈。」

这份文件把那句话拆成两半，分别用两种证据钉住：

**半句一：缺依赖时不许炸。** ``_require_semantic_deps`` 已经把 ``ImportError``
转成 ``RuntimeError``，HTTP 边界（``web/routers/search.py``）已经把 ``RuntimeError``
转成 400。缺的那一处是 CLI：``reader3 --index <book>`` 直到本工作项之前都是一个
裸 traceback。C1/C3/C4/C5/C6 分别钉住 **转译层、HTTP 层、纯读盘路径、import 本身、
CLI**——它们互相看不见对方的失败，所以不能合并。

**半句二：拆分本身不许被无声撤销。** C7/C8/C9 是**静态闸**：直接读
``pyproject.toml``。理由是别的测试都看不见这件事——将来某次 ``uv add chromadb``
把包加回主依赖，上面所有用例照常绿（依赖装着，什么都不会红），而本工作项的成果
已经没了。没有这三条，这次拆分是不设防的。

**怎么模拟「没装依赖」**：往 ``sys.meta_path`` 头上插一个只认这几个包名的 finder，
``find_spec`` 直接抛 ``ImportError``。monkeypatch 在 teardown 自动还原。不动环境
变量、不动 ``sys.path``、不真卸包——真卸包会毁掉本机 1.3 GB 的 venv，而且无法在一个
测试的生命周期内还原。

**为什么不是 ``monkeypatch.setitem(sys.modules, "chromadb", None)``**（更短、也同样
有语言层面的保证）：那条路径抛的是 ``ModuleNotFoundError``，字样会跟着失败用例的
traceback 打进 lane 的 stdout；而 tdd-guardian 的红收据把 ``ModuleNotFoundError``
当成「环境坏了」的特征串，于是这份**真实的断言失败**会被判成 runner-error，红收据
录不进去（实测如此，不是推测）。finder 抛的 ``ImportError`` 消息由这里自己决定，
不撞那张表。两者对被测代码是同一件事：``_require_semantic_deps`` 的 ``except`` 收
到的都是 ``ImportError``（``ModuleNotFoundError`` 本来就是它的子类），而 finder 这层
恰好就是真的没装包时失败的那一层。

Assertion levels（本 lane 既有约定，见 tests/unit/conftest.py）:
    L2 返回值 / 单个字段（C1、C2、C4、C6、C7、C8、C9）
    L3 跨层可观察的端到端状态（C3 走真实路由树，C5 走一个全新解释器）
"""

from __future__ import annotations

import importlib.util
import os
import pickle
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Tuple

import pytest
from fastapi.testclient import TestClient

from reader3_app import reader3, vector_search
from reader3_app.vector_search import BookVectorIndex
from reader3_app.web import server

BOOK_ID = "semantic_optional_data"

#: 两个可选包的**顶级**名字。挡顶级包就够：`chromadb.utils.embedding_functions`
#: 的 import 会先去找 `chromadb`，在那一步就失败。
BLOCKED_ROOTS = ("chromadb", "sentence_transformers")

#: 缺依赖的补救文案必须指向 extra 的装法。`uv add` 会把包加回**主依赖**，正好撤销
#: 本工作项——一条会撤销修复的指引比没有指引更糟，所以它是显式的黑名单。
FORBIDDEN_HINT = "uv add"

#: finder 抛出的消息。刻意不含 "No module named" / "Cannot find module" 这类串：
#: 见模块 docstring 里关于红收据分类的那段。
BLOCK_MESSAGE = "simulated absent optional dependency: {name} (the 'semantic' extra is absent here)"


class _AbsentPackageFinder:
    """``sys.meta_path`` 上的一个拦截器：指定的几个顶级包一律当作没装。"""

    def __init__(self, roots: tuple) -> None:
        self.roots = roots

    def find_spec(self, fullname: str, path=None, target=None):  # noqa: ANN001 - 签名由 import 协议定
        if fullname.split(".")[0] in self.roots:
            raise ImportError(BLOCK_MESSAGE.format(name=fullname), name=fullname)
        return None


@pytest.fixture
def deps_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """让 ``import chromadb`` / ``import sentence_transformers`` 抛 ``ImportError``。"""
    # 已经被别的用例 import 进来的话，finder 根本不会被问到——先把缓存拿掉。
    for name in list(sys.modules):
        if name.split(".")[0] in BLOCKED_ROOTS:
            monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, "meta_path", [_AbsentPackageFinder(BLOCKED_ROOTS), *sys.meta_path])


def _seed_book_dir(books_dir: Path) -> Path:
    """一个**最小**的已处理书目录。

    ``book.pkl`` 的内容无所谓：本文件的每一条路径要么在读它之前就已经因为缺依赖
    失败（``index_book`` 先 ``_prepare_deps`` 再 ``_load_book``），要么根本不读它
    （``status()`` 只读 ``index_meta.json``）。只有 ``list_book_ids`` 要求这个文件
    存在，所以它必须存在、但不必可读。
    """
    book_dir = books_dir / BOOK_ID
    book_dir.mkdir(parents=True, exist_ok=True)
    with open(book_dir / "book.pkl", "wb") as f:
        pickle.dump({"not": "a real Book"}, f)
    return book_dir


# ---------------------------------------------------------------------------
# C1 / C2 —— 转译层：ImportError 不许漏出去，文案不许把依赖加回主表
# ---------------------------------------------------------------------------


def test_c1_缺依赖时抛RuntimeError而不是ImportError(deps_blocked: None) -> None:
    """``_require_semantic_deps`` 是唯一的 import 点，也是唯一的转译点。

    调用方（``index_book`` → 路由 → CLI）一路只认 ``RuntimeError``。这里漏出
    ``ImportError`` 就等于验收里那个「``ImportError`` 堆栈」。
    """
    with pytest.raises(RuntimeError) as excinfo:
        vector_search._require_semantic_deps()

    assert not isinstance(excinfo.value, ImportError)


def test_c1b_原始ImportError留在__cause__里(deps_blocked: None) -> None:
    """转译不等于丢证据：`raise ... from e` 让真出问题时还查得到是哪个包。"""
    with pytest.raises(RuntimeError) as excinfo:
        vector_search._require_semantic_deps()

    assert isinstance(excinfo.value.__cause__, ImportError), (
        f"__cause__ 应该是原始 ImportError，实际是 {excinfo.value.__cause__!r}"
    )


def test_c2_文案不含uv_add且指向semantic_extra(deps_blocked: None) -> None:
    """``uv add chromadb sentence-transformers`` 会把两个包写回 ``[project] dependencies``。

    照着做的人会「修好」语义搜索，同时无声撤销本工作项。文案必须给的是 extra 的
    装法（``reader3[semantic]`` 或 ``--extra semantic``）。
    """
    with pytest.raises(RuntimeError) as excinfo:
        vector_search._require_semantic_deps()

    msg = str(excinfo.value)
    assert FORBIDDEN_HINT not in msg, f"文案把依赖指回了主表：{msg!r}"
    assert re.search(r"reader3\[semantic\]|--extra semantic|extra\s+[\"'`]?semantic", msg), (
        f"文案没给出 extra 的装法：{msg!r}"
    )


# ---------------------------------------------------------------------------
# C3 / C4 —— HTTP 边界
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.chdir(tmp_path)
    books_dir = tmp_path / "books"
    _seed_book_dir(books_dir)
    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))
    # TestClient 不进 with：lifespan 只在 __enter__ 时跑，不进就没有 startup 扫库。
    yield TestClient(server.app, base_url="http://127.0.0.1")


def test_c3_POST_index_缺依赖回400与可读文案(client: TestClient, deps_blocked: None) -> None:
    """语义路由的降级：400 + 一句人能读懂的话，不是 500，更不是 traceback。

    500 在这里是错的答案——缺一个可选依赖不是服务端故障，而是一个用户自己能修的
    配置问题，状态码必须让前端能把它当成「可补救」来渲染。
    """
    resp = client.post(f"/api/index/{BOOK_ID}", json={"force_reindex": False})

    assert resp.status_code == 400, f"期望 400，实际 {resp.status_code}: {resp.text[:400]}"
    detail = resp.json().get("detail", "")
    assert "Traceback" not in detail
    assert FORBIDDEN_HINT not in detail
    assert re.search(r"reader3\[semantic\]|--extra semantic|extra\s+[\"'`]?semantic", detail), (
        f"400 的 detail 没给出补救动作：{detail!r}"
    )


def test_c4_GET_index_status_缺依赖照常工作(client: TestClient, deps_blocked: None) -> None:
    """防回归：``status()`` 是纯读盘，永远不该需要语义依赖。

    将来谁把 ``_require_semantic_deps()`` 挪进 ``BookVectorIndex.__init__``（或者
    挪进 ``status()``），这条会红——而首页、书库统计、关键词搜索的索引徽标全都走
    这条路径，它们在没装 extra 的机器上必须照常出结果。
    """
    resp = client.get(f"/api/index/{BOOK_ID}/status")

    assert resp.status_code == 200, f"纯读盘路径不该受依赖影响，实际 {resp.status_code}: {resp.text[:400]}"
    body = resp.json()
    assert body["status"] == "not_indexed"
    assert body["book_id"] == BOOK_ID


def test_c4b_is_indexed与status在缺依赖时都不抛(tmp_path: Path, deps_blocked: None) -> None:
    """同一条性质在对象层再钉一次：路由可能被改写，这两个方法的契约不该跟着动。"""
    books_dir = tmp_path / "books"
    _seed_book_dir(books_dir)
    idx = BookVectorIndex(BOOK_ID, books_dir=str(books_dir))

    assert idx.is_indexed() is False
    assert idx.status()["status"] == "not_indexed"


# ---------------------------------------------------------------------------
# C5 —— import 本身
# ---------------------------------------------------------------------------


def test_c5_缺依赖时三个模块的全新import正常(tmp_path: Path) -> None:
    """验收的前半句：``import reader3_app`` 不能需要 chromadb。

    这条**必须**在一个全新解释器里跑。当前进程早就 import 过这三个模块了，
    在进程内再 ``import`` 一次只会命中 ``sys.modules``，证明不了任何事。
    子进程有显式 timeout（本 lane 的规矩：允许有界子解释器，不允许无界的）。
    """
    code = (
        "import sys\n"
        "ROOTS = ('chromadb', 'sentence_transformers')\n"
        "class Blocker:\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if fullname.split('.')[0] in ROOTS:\n"
        "            raise ImportError('simulated absent optional dependency: ' + fullname)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Blocker())\n"
        "import reader3_app\n"
        "import reader3_app.vector_search\n"
        "import reader3_app.web.server\n"
        "assert 'chromadb' not in sys.modules, 'chromadb 被真的 import 进来了'\n"
        "assert 'sentence_transformers' not in sys.modules\n"
        "print('IMPORTS-OK')\n"
    )
    env = dict(os.environ)
    env["READER3_BOOKS_DIR"] = str(tmp_path / "books")
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )

    assert proc.returncode == 0, f"全新 import 失败：\n{proc.stdout[-2000:]}\n{proc.stderr[-4000:]}"
    assert "IMPORTS-OK" in proc.stdout


# ---------------------------------------------------------------------------
# C6 —— CLI
# ---------------------------------------------------------------------------


def test_c6_CLI_index_缺依赖抛SystemExit而不是裸traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deps_blocked: None
) -> None:
    """``reader3 --index <book>`` 是这次唯一真正缺失的那一处降级。

    ``main()`` 里其它每一个失败出口都是 ``raise SystemExit(msg)``（书没找到、
    没给参数、文件不存在）；只有 ``index_book()`` 的 ``RuntimeError`` 一路穿到
    顶层，在终端上打成一屏 traceback。用户看到的第一行不该是 ``Traceback``。
    """
    monkeypatch.chdir(tmp_path)
    books_dir = tmp_path / "books"
    _seed_book_dir(books_dir)
    monkeypatch.setenv("READER3_BOOKS_DIR", str(books_dir))

    with pytest.raises(SystemExit) as excinfo:
        reader3.main(["--index", BOOK_ID])

    msg = str(excinfo.value)
    assert "Semantic search dependencies" in msg or "semantic" in msg.lower(), (
        f"SystemExit 的消息得是那条可读文案，实际是 {msg!r}"
    )
    assert FORBIDDEN_HINT not in msg
    assert "Traceback" not in msg


def test_c6b_CLI_缺依赖不漏RuntimeError(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deps_blocked: None
) -> None:
    """``SystemExit`` 而不是 ``RuntimeError``：前者 argparse 风格地退出，后者打堆栈。"""
    monkeypatch.chdir(tmp_path)
    books_dir = tmp_path / "books"
    _seed_book_dir(books_dir)
    monkeypatch.setenv("READER3_BOOKS_DIR", str(books_dir))

    with pytest.raises(BaseException) as excinfo:  # noqa: PT011 - 就是要看到底抛的是哪个类型
        reader3.main(["--index", BOOK_ID])

    assert isinstance(excinfo.value, SystemExit), f"抛的是 {type(excinfo.value).__name__}，不是 SystemExit"


# ---------------------------------------------------------------------------
# C7 / C8 / C9 —— 静态闸：pyproject.toml 的形状
# ---------------------------------------------------------------------------


def _load_pyproject_tables(text: str) -> Optional[Dict[str, List[str]]]:
    """把 pyproject 里我们关心的三个依赖数组读出来；读不出来返回 ``None``。

    py3.11+ 有 ``tomllib``；本项目 ``requires-python >= 3.10``，3.10 上没有它。
    退路是 ``tomli``（本 lane 的 venv 里由 pytest/coverage/mypy 在 py<3.11 上传递
    带进来，见 uv.lock 的 marker）。两者都没有时返回 ``None``，调用方退化成文本
    解析——**代价**：文本解析只认「一个数组字面量、每行一个元素」这一种写法，
    有人把 dependencies 改成行内数组或多行字符串拼接它就会误判。所以它只是兜底，
    不是首选。
    """
    try:
        import tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:
            return None

    data = tomllib.loads(text)
    project = data.get("project", {})
    return {
        "dependencies": list(project.get("dependencies", []) or []),
        "semantic": list((project.get("optional-dependencies", {}) or {}).get("semantic", []) or []),
        "dev": list((data.get("dependency-groups", {}) or {}).get("dev", []) or []),
    }


def _text_array(text: str, header: str, key: str) -> List[str]:
    """兜底解析：从 ``header`` 小节里取出名为 ``key`` 的数组字面量的元素。"""
    items: List[str] = []
    in_section = False
    collecting = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and not line.startswith("[["):
            in_section = line == header
            collecting = False
            continue
        if not in_section or line.startswith("#"):
            continue
        if not collecting:
            if "=" in line and line.split("=", 1)[0].strip() == key:
                collecting = True
                rest = line.split("=", 1)[1].strip()
                items.extend(re.findall(r'"([^"]+)"', rest))
                if rest.endswith("]"):
                    break
            continue
        if line.startswith("]"):
            break
        items.extend(re.findall(r'"([^"]+)"', line))
    return items


def _fallback_tables(text: str) -> Dict[str, List[str]]:
    return {
        "dependencies": _text_array(text, "[project]", "dependencies"),
        "semantic": _text_array(text, "[project.optional-dependencies]", "semantic"),
        "dev": _text_array(text, "[dependency-groups]", "dev"),
    }


def _req_name(requirement: str) -> str:
    """``"chromadb>=1.3.7"`` → ``"chromadb"``；``"reader3[semantic]"`` → ``"reader3"``。"""
    name = re.split(r"[\[<>=!~;\s]", str(requirement).strip(), maxsplit=1)[0]
    return name.lower().replace("_", "-")


def _req_extras(requirement: str) -> List[str]:
    m = re.search(r"\[([^\]]*)\]", str(requirement))
    return [e.strip().lower() for e in m.group(1).split(",")] if m else []


@pytest.fixture(scope="module")
def pyproject_tables(request: pytest.FixtureRequest) -> Dict[str, List[str]]:
    root = Path(request.config.rootpath)
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    parsed = _load_pyproject_tables(text)
    return parsed if parsed is not None else _fallback_tables(text)


SEMANTIC_PACKAGES = ("chromadb", "sentence-transformers")


@pytest.mark.parametrize("package", SEMANTIC_PACKAGES)
def test_c7_语义依赖不在主dependencies里(pyproject_tables: Dict[str, List[str]], package: str) -> None:
    """留在主表里，``pip install reader3`` 就还是要拖 torch —— 拆分等于没做。"""
    names = [_req_name(d) for d in pyproject_tables["dependencies"]]
    assert package not in names, f"{package} 还在 [project] dependencies 里：{pyproject_tables['dependencies']}"


@pytest.mark.parametrize("package", SEMANTIC_PACKAGES)
def test_c8_语义依赖在semantic_extra里(pyproject_tables: Dict[str, List[str]], package: str) -> None:
    """是移进 extra，不是删除：``uv sync --extra semantic`` 之后语义搜索必须能用。"""
    names = [_req_name(d) for d in pyproject_tables["semantic"]]
    assert package in names, (
        f"{package} 不在 [project.optional-dependencies].semantic 里：{pyproject_tables['semantic']}"
    )


def test_c9_dev组自引用semantic_extra(pyproject_tables: Dict[str, List[str]]) -> None:
    """``dev = ["reader3[semantic]", ...]`` 是承重的一行。

    少了它，下一次 ``uv sync`` 会把开发机上的 chromadb / torch / transformers 卸掉，
    于是**所有**语义相关的开发与测试在本地静默失去依赖。
    """
    dev = pyproject_tables["dev"]
    self_refs = [d for d in dev if _req_name(d) == "reader3"]
    assert self_refs, f"[dependency-groups] dev 里没有 reader3 的自引用：{dev}"
    assert any("semantic" in _req_extras(d) for d in self_refs), (
        f"dev 组引用了 reader3 但没带 [semantic] extra：{self_refs}"
    )


def test_c9b_解析走的是真TOML而不是兜底(pyproject_tables: Dict[str, List[str]]) -> None:
    """记录代价：本 lane 上 ``tomllib``/``tomli`` 有一个就够。

    两个都没有时上面三条走文本兜底，仍然能判，但对 pyproject 的写法更挑剔。
    这条不要求兜底路径消失，只要求它在**本 lane 上没被用到**——真用上了就说明
    环境变了，届时该知道上面三条的判定强度也跟着降了。
    """
    text = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    assert _load_pyproject_tables(text) is not None, (
        "tomllib 与 tomli 都不可用，静态闸退化成了文本解析"
    )


# ---------------------------------------------------------------------------
# C10 / C11 / C12 —— 017 WI-14（审计 #25）：三种依赖不全，走的是三条路
# ---------------------------------------------------------------------------
#
# 上面 C1–C6 的 `deps_blocked` 把**两个**包一起挡掉，于是每一条都停在同一个地方：
# `_require_semantic_deps()` 里的 `import chromadb`。那证明的是「两个都没装时不许炸」，
# 不是「依赖不全时不许炸」——而这两句话在代码上不是一回事。
#
# `chromadb` 装着、`sentence-transformers` 没装时（`uv sync --extra semantic` 装到一半被
# 打断、或有人手工 `pip uninstall sentence-transformers`），`_require_semantic_deps()`
# **通过**：`SentenceTransformerEmbeddingFunction` 只是个类对象，import 它不需要底层包。
# 失败推迟到构造那一刻，抛的是 `ValueError`。2026-09-23 实测：
#
#     B) _prepare_deps raised ValueError : The sentence_transformers python package is not
#        installed. Please install it with `pip install sentence_transformers`
#
# CLI 的 `except RuntimeError` 接不住它（裸 traceback），HTTP 落到兜底的 `except Exception`
# 给 500。修法在 `vector_search._build_embedding_function`；这里三种形态各自把 CLI 与 HTTP
# 的**实际出口**钉住。

#: 补救文案的黑名单。除了 `uv add`（会把包写回主依赖），还要挡 chromadb 自己那句
#: `pip install sentence_transformers`——它把包装在 extra 之外，同样撤销 011 WI-7。
FORBIDDEN_HINTS = ("uv add", "pip install sentence_transformers", "pip install chromadb")

#: （形态名，要挡的顶级包，预期在哪一层失败）。第三列是这一族的要害：没有它，三条用例
#: 可能全都停在 `_require_semantic_deps`，「逐个依赖单独测」就成了三份同样的测试。
_DEP_SCENARIOS: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    ("两个都没装", ("chromadb", "sentence_transformers"), "import"),
    ("只缺chromadb", ("chromadb",), "import"),
    ("只缺sentence_transformers", ("sentence_transformers",), "construct"),
)

_SCENARIO_PARAMS = [
    pytest.param(roots, stage, id=name) for name, roots, stage in _DEP_SCENARIOS
]


@pytest.fixture
def block_roots(monkeypatch: pytest.MonkeyPatch) -> Callable[[Tuple[str, ...]], None]:
    """按需屏蔽任意一组顶级包（`deps_blocked` 的可参数化版本）。"""

    def _block(roots: Tuple[str, ...]) -> None:
        for name in list(sys.modules):
            if name.split(".")[0] in roots:
                monkeypatch.delitem(sys.modules, name, raising=False)
        monkeypatch.setattr(sys, "meta_path", [_AbsentPackageFinder(roots), *sys.meta_path])

    return _block


def _skip_if_unconstructible(roots: Tuple[str, ...]) -> None:
    """「只缺 X」这种形态，前提是**另一个**包真的装着。

    没装 `[semantic]` extra 的机器上 `只缺sentence_transformers` 不可构造：那里 chromadb
    本来就没有，屏蔽与否都停在 import。跳过并说明，而不是让它变成一条名不副实的绿。
    """
    for pkg in ("chromadb", "sentence_transformers"):
        if pkg in roots:
            continue
        if importlib.util.find_spec(pkg) is None:
            pytest.skip(f"本机没装 {pkg}：屏蔽 {roots} 构造不出这一形态（需要 `[semantic]` extra）")


@pytest.mark.parametrize(("roots", "stage"), _SCENARIO_PARAMS)
def test_c10_三种依赖不全都在预期的那一层变成RuntimeError(
    tmp_path: Path,
    block_roots: Callable[[Tuple[str, ...]], None],
    monkeypatch: pytest.MonkeyPatch,
    roots: Tuple[str, ...],
    stage: str,
) -> None:
    """既断**抛什么**，也断**在哪一层抛**。

    只断 `RuntimeError` 的话，三条用例可能全都停在 `_require_semantic_deps`——那样「逐个
    依赖单独测」就是三份同样的测试，而审计 #25 指的恰恰是第三种形态走的是另一条路。所以
    这里正面观察构造器有没有被调用：`import` 形态下它必须**没被调到**（import 就先失败了），
    `construct` 形态下它必须**被调到**且由它抛。
    """
    _skip_if_unconstructible(roots)

    calls: List[str] = []
    real_builder = vector_search._build_embedding_function

    def _spy(factory: object):  # noqa: ANN202 - 透传真实实现，只记一笔
        calls.append("called")
        return real_builder(factory)

    monkeypatch.setattr(vector_search, "_build_embedding_function", _spy)
    block_roots(roots)

    books_dir = tmp_path / "books"
    _seed_book_dir(books_dir)
    idx = BookVectorIndex(BOOK_ID, books_dir=str(books_dir))

    with pytest.raises(RuntimeError) as excinfo:
        idx._prepare_deps()

    if stage == "import":
        assert calls == [], (
            f"屏蔽 {roots} 时 import 就该失败，构造器不该被调到——这一形态与 `construct` "
            "形态没有区分开，那么这一族的三条用例是重复的"
        )
    else:
        assert calls == ["called"], (
            f"屏蔽 {roots} 时 `_require_semantic_deps()` 应当通过、由构造器失败，"
            f"实际构造器调用记录为 {calls}——审计 #25 的那条路径没有被走到"
        )
        assert isinstance(excinfo.value.__cause__, (ImportError, ValueError)), (
            f"构造失败的原文该留在 __cause__ 里，实际是 {excinfo.value.__cause__!r}"
        )

    msg = str(excinfo.value)
    for bad in FORBIDDEN_HINTS:
        assert bad not in msg, f"补救文案把依赖指到了 extra 之外（{bad!r}）：{msg!r}"
    assert re.search(r"reader3\[semantic\]|--extra semantic|extra\s+[\"'`]?semantic", msg), (
        f"补救文案没给出 extra 的装法：{msg!r}"
    )


@pytest.mark.parametrize(("roots", "stage"), _SCENARIO_PARAMS)
def test_c11_三种依赖不全下CLI都以SystemExit收场(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    block_roots: Callable[[Tuple[str, ...]], None],
    roots: Tuple[str, ...],
    stage: str,
) -> None:
    """断的是 CLI 的**实际出口**，不是「某个函数抛了 RuntimeError」。

    `reader3.main()` 只 `except RuntimeError`。构造器那条路原本抛 `ValueError`，于是这一
    形态下用户拿到的是一屏裸 traceback——`main()` 里其它每一个失败出口都是 `SystemExit(msg)`。
    """
    _skip_if_unconstructible(roots)
    block_roots(roots)

    monkeypatch.chdir(tmp_path)
    books_dir = tmp_path / "books"
    _seed_book_dir(books_dir)
    monkeypatch.setenv("READER3_BOOKS_DIR", str(books_dir))

    with pytest.raises(BaseException) as excinfo:  # noqa: PT011 - 就是要看到底抛的是哪个类型
        reader3.main(["--index", BOOK_ID])

    assert isinstance(excinfo.value, SystemExit), (
        f"屏蔽 {roots} 时 CLI 抛的是 {type(excinfo.value).__name__}，不是 SystemExit"
        "——用户看到的第一行会是 `Traceback`"
    )
    msg = str(excinfo.value)
    assert "Traceback" not in msg
    for bad in FORBIDDEN_HINTS:
        assert bad not in msg, f"CLI 文案把依赖指到了 extra 之外（{bad!r}）：{msg!r}"
    assert re.search(r"reader3\[semantic\]|--extra semantic|extra\s+[\"'`]?semantic", msg), (
        f"CLI 文案没给出 extra 的装法：{msg!r}"
    )


@pytest.mark.parametrize(("roots", "stage"), _SCENARIO_PARAMS)
def test_c12_三种依赖不全下POST_index都回400(
    client: TestClient,
    block_roots: Callable[[Tuple[str, ...]], None],
    roots: Tuple[str, ...],
    stage: str,
) -> None:
    """400 而不是 500：缺一个可选依赖是用户自己能修的配置问题，不是服务端故障。

    构造器那条路原本落到兜底的 `except Exception` 给 500，前端据此没法把它渲染成「可补救」。
    """
    _skip_if_unconstructible(roots)
    block_roots(roots)

    resp = client.post(f"/api/index/{BOOK_ID}", json={"force_reindex": False})

    assert resp.status_code == 400, (
        f"屏蔽 {roots} 时期望 400，实际 {resp.status_code}: {resp.text[:400]}"
    )
    detail = resp.json().get("detail", "")
    assert "Traceback" not in detail
    for bad in FORBIDDEN_HINTS:
        assert bad not in detail, f"400 的 detail 把依赖指到了 extra 之外（{bad!r}）：{detail!r}"
    assert re.search(r"reader3\[semantic\]|--extra semantic|extra\s+[\"'`]?semantic", detail), (
        f"400 的 detail 没给出补救动作：{detail!r}"
    )


# ---------------------------------------------------------------------------
# C13 —— 转译收得窄：只有「依赖不全」才改说法
# ---------------------------------------------------------------------------


def test_c13_构造器转译只收依赖不全不收别的毛病() -> None:
    """`_build_embedding_function` 的捕获是 `(ImportError, ValueError)`，不是 `Exception`。

    这条边界有代价，所以要钉：把捕获放宽成 `Exception`，模型名写错、权重下载失败、磁盘满
    ——全都会被说成「依赖没装，去装 extra」，而照着那句话做的人装完发现还是不行，且真正的
    原因已经被换掉了。窄捕获的代价在另一侧：将来 chromadb 换个异常类型来表示「包没装」，
    这里会漏。那一侧由 C10 的 `只缺sentence_transformers` 形态盯着——它跑的是真 chromadb。

    直接喂假 factory，不碰真依赖：这条要问的是「转译的边界画在哪」，不是「真依赖什么行为」。
    """

    def _missing_package(model_name: str):  # noqa: ANN202, ARG001
        raise ValueError("The sentence_transformers python package is not installed.")

    with pytest.raises(RuntimeError) as excinfo:
        vector_search._build_embedding_function(_missing_package)
    assert re.search(r"reader3\[semantic\]|--extra semantic|extra\s+[\"'`]?semantic", str(excinfo.value))

    class _ModelDownloadFailed(OSError):
        pass

    def _bad_model(model_name: str):  # noqa: ANN202, ARG001
        raise _ModelDownloadFailed("could not download weights for 'typo-model-name'")

    with pytest.raises(_ModelDownloadFailed) as oops:
        vector_search._build_embedding_function(_bad_model)
    assert "typo-model-name" in str(oops.value), (
        "模型下载失败被转译成了「依赖没装」——真正的原因被换掉了，照着新文案做的人修不好"
    )
