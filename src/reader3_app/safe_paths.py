"""Book folder name validation, shared by every service that builds a path from one.

宪法第 5 条：book id 必须校验。旧判据 ``os.path.basename(x) == x`` 放行了
``""``、``"."``、``".."`` 三个值——它们各自的 basename 就是自己——于是
``os.path.join(books_dir, name)`` 逃出库根，落在 ``books/`` 的父目录上。
``notes_service`` 与 ``vector_search`` 则一次校验都没有。

这里只做一件事，而且是在**拼路径之前**做：调用点必须先过这个闸门再碰磁盘，
否则「先写后抛」的实现照样毁数据。
"""

from __future__ import annotations


_SEPARATORS = ("/", "\\", "\x00")


def safe_book_folder(name: str) -> str:
    """Return ``name`` unchanged, or raise ``ValueError`` naming the rejected value.

    Rejected: the empty string, ``"."``, ``".."``, and anything containing a path
    separator or a NUL byte. Everything else — including non-ASCII book names —
    passes through untouched; validation must not rewrite the caller's id.
    """
    if not isinstance(name, str) or not name:
        raise ValueError(f"Invalid book folder name: {name!r}")
    if name in (".", ".."):
        raise ValueError(f"Invalid book folder name: {name!r}")
    for sep in _SEPARATORS:
        if sep in name:
            raise ValueError(f"Invalid book folder name: {name!r}")
    return name
