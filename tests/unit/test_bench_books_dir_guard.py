"""`scripts/bench.py --books-dir` 只接受基准自己造的一次性目录（audit-008 第 1 条 Critical）。

矩阵：`.claude/tdd-guardian/tests-20260824T074825Z.md` B1–B10。

被测的护栏是**所有权证明**，不是黑名单：一个路径被放行，当且仅当它的祖先链上存在
一个「名字以 mkdtemp 的 prefix 开头 **且** 内含标记文件」的目录 —— 也就是本次运行
的父进程亲手造的那个。只看名字会被一个恰好同名的真目录骗过；只看标记会被随手丢进
真书库的一个文件解开。两条一起才关得住。

`scripts/bench.py` 不是包，所以从路径加载。它顶层只 import 标准库、无模块级副作用。
本文件所有落盘一律在 `tmp_path` 下 —— 真实 `books/` 由 `tests/unit/conftest.py` 的
autouse 护栏另行把关，这里不重复实现它。
"""

from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BENCH_PATH = REPO_ROOT / "scripts" / "bench.py"


def _load_bench():
    spec = importlib.util.spec_from_file_location("bench_under_test", BENCH_PATH)
    assert spec is not None and spec.loader is not None, f"无法从 {BENCH_PATH} 加载 bench.py"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bench():
    return _load_bench()


def _tree(root: Path) -> Dict[str, Tuple[int, int, int]]:
    """整棵树 `relpath -> (st_size, st_mtime_ns, st_ino)`。

    只断「退出码非 0」的话，一个「先 rmtree 了再退出」的实现照样能过。这条 Critical
    真正要的保证是「一字节不动」，所以比的是整棵树的可观察终态。
    """
    tree: Dict[str, Tuple[int, int, int]] = {}
    if not root.exists():
        return tree
    for dirpath, dirnames, filenames in os.walk(root):
        for name in list(dirnames) + list(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            st = os.stat(full, follow_symlinks=False)
            tree[rel] = (st.st_size, st.st_mtime_ns, st.st_ino)
    return tree


@pytest.fixture
def fake_library(tmp_path: Path) -> Path:
    """一个「长得像真书库」的目录：有 book.pkl、有用户标注、有图片。

    重点在 `notes.json` —— 那正是用户产生的、错了不能重新生成的那份数据。
    """
    books = tmp_path / "books"
    (books / "sample_data" / "images").mkdir(parents=True)
    (books / "sample_data" / "book.pkl").write_bytes(b"\x80\x04\x95not-really-a-pickle")
    (books / "sample_data" / "notes.json").write_text(
        '[{"id": "n1", "quote": "irreplaceable", "note_text": "user wrote this"}]',
        encoding="utf-8",
    )
    (books / "sample_data" / "images" / "cover.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return books


# --------------------------------------------------------------------------- #
# B1 / B2 —— 破坏性防护：worker 拒绝不带标记的目录，且一字节不动
# --------------------------------------------------------------------------- #


def test_prepare_worker_refuses_unmarked_dir_and_leaves_it_byte_identical(bench, fake_library):
    before = _tree(fake_library)
    assert before, "前置条件坏了：假书库是空的，那这条测试什么也证明不了"

    with pytest.raises(SystemExit) as excinfo:
        bench.main(["--worker", "prepare", "--books-dir", str(fake_library)])

    assert excinfo.value.code not in (None, 0), (
        f"拒绝必须以非 0 退出，否则父进程的 run_worker 看不出出事了；实得 {excinfo.value.code!r}"
    )
    assert _tree(fake_library) == before


def test_ingest_worker_refuses_unmarked_dir_and_leaves_it_byte_identical(bench, fake_library):
    """`ingest` 是唯一直接调 `process_epub` 的 worker，也是 audit 复现命令点名的那个。"""
    before = _tree(fake_library)
    assert before, "前置条件坏了：假书库是空的，那这条测试什么也证明不了"

    with pytest.raises(SystemExit) as excinfo:
        bench.main(["--worker", "ingest", "--books-dir", str(fake_library)])

    assert excinfo.value.code not in (None, 0), (
        f"拒绝必须以非 0 退出，否则父进程的 run_worker 看不出出事了；实得 {excinfo.value.code!r}"
    )
    assert _tree(fake_library) == before


# --------------------------------------------------------------------------- #
# B3 / B4 —— 正例：父进程自己造的目录，以及它的 books 子目录
# --------------------------------------------------------------------------- #


def test_resolve_books_dir_accepts_scratch_created_by_parent(bench):
    stack: List[str] = []
    try:
        root = bench._new_scratch(stack)
        result = bench.resolve_books_dir(str(root))
        assert isinstance(result, Path)
        assert result == root.resolve()
    finally:
        bench._cleanup(stack)


def test_resolve_books_dir_accepts_books_subdir_of_scratch(bench):
    """六个 worker 里有五个拿到的正是这个形状（`_prepared_library` 的返回值）。

    一个只查 `path` 自身、不沿祖先链上溯的实现会把整套基准全拒掉。
    """
    stack: List[str] = []
    try:
        root = bench._new_scratch(stack)
        books = root / "books"
        books.mkdir()
        assert bench.resolve_books_dir(str(books)) == books.resolve()
    finally:
        bench._cleanup(stack)


# --------------------------------------------------------------------------- #
# B5 / B6 —— 两半各自承重
# --------------------------------------------------------------------------- #


def test_resolve_books_dir_refuses_prefix_without_marker(bench, tmp_path: Path):
    """名字对、无标记 → 拒绝。与 B3 成对：同样的名字，只差一个标记文件。"""
    impostor = tmp_path / f"{bench.SCRATCH_PREFIX}fake"
    impostor.mkdir()
    with pytest.raises(SystemExit):
        bench.resolve_books_dir(str(impostor))


def test_resolve_books_dir_refuses_marker_without_prefix(bench, tmp_path: Path):
    """有标记、名字不带前缀 → 拒绝。

    一个能被「往目录里丢个文件」解开的锁不是锁。前缀这一半挡的就是这个。
    """
    disguised = tmp_path / "books"
    disguised.mkdir()
    (disguised / bench.SCRATCH_MARKER).write_text("", encoding="utf-8")
    with pytest.raises(SystemExit):
        bench.resolve_books_dir(str(disguised))


# --------------------------------------------------------------------------- #
# B7 —— 缺参数：拒绝要给话说，不是给堆栈
# --------------------------------------------------------------------------- #


def test_worker_without_books_dir_exits_cleanly(bench):
    with pytest.raises(SystemExit):
        bench.main(["--worker", "prepare"])


# --------------------------------------------------------------------------- #
# B8 —— `_new_scratch()` 真的落了标记，且进了清理栈
# --------------------------------------------------------------------------- #


def test_new_scratch_plants_marker_under_tempdir(bench):
    stack: List[str] = []
    try:
        root = bench._new_scratch(stack)
        assert root.is_dir()
        assert (root / bench.SCRATCH_MARKER).is_file()
        assert root.name.startswith(bench.SCRATCH_PREFIX)
        # macOS 的 gettempdir() 是 /var/folders/...，而 /var 是指向 /private/var 的
        # 软链 —— 两侧都 resolve() 之后再比，否则同一个目录会判成两个。
        tmp_root = Path(tempfile.gettempdir()).resolve()
        assert tmp_root in root.resolve().parents
        # 没进 stack 的话 `_cleanup` 漏删，基准每跑一次泄一个大部头目录。
        assert [Path(p).resolve() for p in stack] == [root.resolve()]
    finally:
        bench._cleanup(stack)


# --------------------------------------------------------------------------- #
# B9 —— 拒绝消息里含被拒的那个路径
# --------------------------------------------------------------------------- #


def test_refusal_message_names_the_rejected_path(bench, fake_library):
    """用户敲错一个 `--books-dir` 时要看得见自己指到哪去了。"""
    with pytest.raises(SystemExit) as excinfo:
        bench.resolve_books_dir(str(fake_library))
    assert str(fake_library.resolve()) in str(excinfo.value)


# --------------------------------------------------------------------------- #
# B10 —— audit 复现命令逐字的那个参数
# --------------------------------------------------------------------------- #


def test_refuses_bare_relative_books_argument(bench):
    """`.cc-suite/audits/audit-008-INDEX.md` 复现命令里的字面 `--books-dir books`。

    纯校验，不写盘，也不改 cwd —— 对着复现命令本身留一条回归，比十条抽象等价类
    更难被日后改没。
    """
    with pytest.raises(SystemExit):
        bench.resolve_books_dir("books")
