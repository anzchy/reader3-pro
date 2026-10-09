"""Shared fixture module for 012 WI-4a (matrix: .claude/tdd-guardian/tests-20261009-wi4a.md, section 0).

Not a test file and not frozen. It holds the builders and spies the three WI-4a unit files share:

- ``book_obj`` / ``gen_book_pkl`` / ``flat_pkl``: real ``Book`` pickles, as a generation's declared ``book.pkl``
  (published under the EX book lock, as ``wi2b_world.publish_gen`` does) or as a flat ``book.pkl``.
- ``REFUSED_PKL`` / ``NONBOOK_PKL`` / ``flip_first_byte``: the unreadable-gen-pkl shapes.
- ``Counters`` (copied from ``test_storage_format.py``) and ``ManifestIO``: passthrough spies, literal targets.
- ``outcome``: the return value or the raised exception, so a pre-implementation red is a counted assertion.
"""

from __future__ import annotations

import dataclasses
import os
import pickle
from pathlib import Path
from typing import Any, Callable, List, Optional

import pytest
from wi2b_world import gen_inputs

from reader3_app import book_format, book_lock, safe_pickle
from reader3_app.reader3 import Book, BookMetadata, ChapterContent

G = "g_data"
LOUD_LOGGERS = {"reader3_app.book_store", "reader3_app.book_format"}
#: ``test_storage_format.BAD_IDS`` plus an absolute path.
BAD_IDS = ["", ".", "..", "../x", "a/b", "a\\b", "a\x00b", "/abs"]

#: ``Reader3Unpickler.find_class`` refuses ``os.system`` before anything executes.
REFUSED_PKL = b"cos\nsystem\n(S'true'\ntR."
#: Allowed by the allow-list, and not a ``Book``.
NONBOOK_PKL = pickle.dumps({"a": 1})


def outcome(fn: Callable[..., Any], *args: Any) -> Any:
    """``fn(*args)``'s return value, or the exception it raised (returned, not re-raised)."""
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 - the caller asserts on whatever came back
        return exc


def book_obj(title: str, texts: List[str], fp: Optional[str] = None, *, drop_fp: bool = False) -> Book:
    """A real ``Book`` whose spine carries ``texts`` (chapters ``c{i}``, as ``wi2b_world.gen_inputs`` builds)."""
    book = Book(
        metadata=BookMetadata(title=title, language="en"),
        spine=[
            ChapterContent(id=f"c{i}", href=f"Text/c{i}.xhtml", title=f"T{i}", content=f"<p>{t}</p>", text=t,
                           order=i)
            for i, t in enumerate(texts)
        ],
        toc=[],
        images={},
        source_file=f"{title}.epub",
        processed_at="2026-10-09T00:00:00+00:00",
    )
    book.book_fingerprint = fp
    if drop_fp:
        del book.book_fingerprint  # a pre-R-5 pickle: the instance carries no attribute
    return book


def gen_book_pkl(books: Any, folder: str, *, texts: List[str], fp: str, pkl: bytes, tag: str = "v1") -> int:
    """Publish one generation of ``texts`` whose declared ``book.pkl`` is ``pkl``, under the EX lock; return g."""
    inputs = dataclasses.replace(gen_inputs(texts, fp, tag), pkl=pkl)
    book_dir = Path(books) / folder
    book_dir.mkdir(parents=True, exist_ok=True)
    with book_lock.acquire(str(books), folder, mode=book_lock.EXCLUSIVE, holder="import"):
        return book_format.publish(book_dir, inputs)


def flat_pkl(books: Any, folder: str, book: Book) -> Path:
    """Write ``books/folder/book.pkl`` as ``pickle.dumps(book)``."""
    path = Path(books) / folder / "book.pkl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(book))
    return path


def flip_first_byte(path: Any) -> None:
    """Rewrite byte 0 (the PROTO opcode) to ``\\x00`` in place: same size, same inode, unpicklable."""
    with open(path, "r+b") as fh:
        fh.seek(0)
        fh.write(b"\x00")


class Counters:
    """Passthrough counters on both deserializer seams (copied from ``test_storage_format.py``)."""

    def __init__(self) -> None:
        self.paths: List[str] = []
        self.raw = 0

    @property
    def n(self) -> int:
        return max(len(self.paths), self.raw)

    def install(self, mp: pytest.MonkeyPatch) -> "Counters":
        real_file = safe_pickle.load_book_file
        real_load = safe_pickle.safe_load

        def counting_file(path: str) -> Any:
            self.paths.append(str(path))
            return real_file(path)

        def counting_load(f: Any) -> Any:
            self.raw += 1
            return real_load(f)

        mp.setattr("reader3_app.book_store.load_book_file", counting_file)
        mp.setattr("reader3_app.safe_pickle.safe_load", counting_load)
        return self


def _is_manifest(p: object) -> bool:
    return isinstance(p, (str, os.PathLike)) and os.path.basename(os.fspath(p)) == "manifest.json"


class ManifestIO:
    """Delegating spies on the root-manifest read and on ``os.lstat`` of ``manifest.json`` (DF-23)."""

    def __init__(self) -> None:
        self.calls = self.returned = self.lstats = 0

    def install(self, mp: pytest.MonkeyPatch) -> "ManifestIO":
        real_read, real_lstat = book_format._read_nofollow, os.lstat

        def read(*a: Any, **kw: Any) -> Any:  # signature-agnostic: survives the OQ-2(b) return change
            hit = _is_manifest(a[0] if a else kw.get("path"))
            self.calls += hit
            out = real_read(*a, **kw)
            self.returned += hit
            return out

        def lstat(*a: Any, **kw: Any) -> Any:
            self.lstats += _is_manifest(a[0] if a else kw.get("path"))
            return real_lstat(*a, **kw)

        mp.setattr("reader3_app.book_format._read_nofollow", read)
        mp.setattr("os.lstat", lstat)
        return self
