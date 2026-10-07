"""Shared helpers for the 018 WI-6 export tests (matrix §0.2, `tests-20261003-125654-wi6.md`).

Nothing here imports ``reader3_app.web.routers.library_export`` or the export-only
conversation reader at import time. ``xe()`` and ``cr()`` are called inside a test, and
when the target does not exist yet they fail the test with a plain ``RED:`` message,
never an ``ImportError`` / ``AttributeError`` (the red-receipt classifier reads those as
environment failures). Every wrapper helper resolves its target through ``_require``
*before* it patches, so a missing name is a ``RED:`` failure too.

Every patch these helpers install goes through the ``monkeypatch`` handle the caller
passes in (a fixture's or a ``monkeypatch.context()`` one), so it is undone with it.
"""

from __future__ import annotations

import contextlib
import functools
import importlib
import importlib.util
import inspect
import json
import os
import shutil
import stat
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import pytest

# --------------------------------------------------------------------------- lazy handles

XE_MODULE = "reader3_app.web.routers.library_export"

#: The export-only reader's name in ``reader3_app.ai.conversations`` (a proposal of the
#: matrix; only this constant changes if the implementer picks another name).
#: Contract: ``read_conversation_threads(directory: str) -> tuple[list[dict], list[str]]``
#: -- (raw thread dicts, unreadable file stems).
EXPORT_READER = "read_conversation_threads"

EXPORT_ROUTE = "/api/library/export"
LIBRARY_ROUTE = "/api/library"
EXPORT_FILENAME = "reader3-library.json"
CONTENT_DISPOSITION = f'attachment; filename="{EXPORT_FILENAME}"'
INCLUDE_DETAIL = 'include must be "conversations"'

#: The WI-4 entry fields (``GET /api/library``), and the readable export entry's keys.
LIBRARY_KEYS = frozenset({"book_id", "title", "authors", "cover_url", "book_uuid"})
EXPORT_KEYS = LIBRARY_KEYS | {"annotations", "component_errors"}


def xe():
    """``reader3_app.web.routers.library_export``, imported lazily (inside tests only)."""
    if importlib.util.find_spec(XE_MODULE) is None:
        pytest.fail("RED: library_export is not implemented", pytrace=False)
    return importlib.import_module(XE_MODULE)


def cr() -> Callable[..., Any]:
    """The export-only conversation reader, resolved lazily."""
    from reader3_app.ai import conversations

    fn = getattr(conversations, EXPORT_READER, None)
    if fn is None:
        pytest.fail(f"RED: conversations.{EXPORT_READER} is not implemented", pytrace=False)
    return fn


def _require(module: Any, name: str) -> Callable[..., Any]:
    fn = getattr(module, name, None)
    if fn is None:
        pytest.fail(f"RED: {module.__name__}.{name} is not implemented", pytrace=False)
    return fn


# --------------------------------------------------------------------------- requests


def export(client: Any, include: Optional[str] = None, *, raw_query: Optional[str] = None) -> Any:
    """``GET /api/library/export``; asserts 200 *before* anything reads the body."""
    if raw_query is not None:
        url = f"{EXPORT_ROUTE}?{raw_query}"
    elif include is not None:
        url = f"{EXPORT_ROUTE}?include={include}"
    else:
        url = EXPORT_ROUTE
    r = client.get(url)
    assert r.status_code == 200, (r.status_code, r.text[:300])
    return r


def library(client: Any) -> Any:
    """``GET /api/library``; asserts 200 first."""
    r = client.get(LIBRARY_ROUTE)
    assert r.status_code == 200, (r.status_code, r.text[:300])
    return r


def entry_of(body: Dict[str, Any], book_id: str) -> Dict[str, Any]:
    hits = [e for e in body["books"] if e.get("book_id") == book_id]
    assert len(hits) == 1, (book_id, [e.get("book_id") for e in body["books"]])
    return hits[0]


def by_cid(threads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(threads, key=lambda t: str(t.get("conversation_id")))


def cids(threads: List[Dict[str, Any]]) -> List[str]:
    return [t["conversation_id"] for t in threads]


def project(entry: Dict[str, Any]) -> Dict[str, Any]:
    """The WI-4 fields of a readable export entry."""
    return {k: entry[k] for k in LIBRARY_KEYS if k in entry}


# --------------------------------------------------------------------------- settings / rehoming


def settings_factory(prefs: Dict[str, Any]) -> Callable[..., Dict[str, Any]]:
    """A ``load_ai_settings`` stand-in that reads ``prefs`` at call time."""

    def _settings(*_a: Any, **_kw: Any) -> Dict[str, Any]:
        from reader3_app.ai.config import default_settings_dict

        settings = default_settings_dict()
        settings["preferences"] = {**(settings.get("preferences") or {}), **prefs}
        return settings

    return _settings


def clear_caches() -> None:
    from reader3_app import search_service
    from reader3_app.web import server

    server.load_book_cached.cache_clear()
    search_service.load_book_cached.cache_clear()
    server._stats_cache.clear()


def rehome(mp: pytest.MonkeyPatch, books_dir: Path, prefs: Dict[str, Any]) -> None:
    """Point the running app at ``books_dir`` (one hypothesis example's own tree)."""
    from reader3_app.ai.books import BookUuidResolver
    from reader3_app.web import server

    mp.setattr(server, "BOOKS_DIR", str(books_dir))
    mp.setattr(server, "book_uuid_resolver", BookUuidResolver(str(books_dir)))
    mp.setattr(server, "load_ai_settings", settings_factory(prefs))
    clear_caches()


# --------------------------------------------------------------------------- spies and wrappers


def _positional(real: Callable[..., Any], args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Tuple[Any, ...]:
    """The call's arguments in parameter order, however the caller spelled them."""
    try:
        bound = inspect.signature(real).bind(*args, **kwargs)
    except (TypeError, ValueError):
        return tuple(args) + tuple(kwargs.values())
    return tuple(bound.arguments.values())


def counting(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    name: str,
    pred: Callable[..., bool] = lambda *a: True,
) -> List[Tuple[Any, ...]]:
    """Wrap ``module.name``: delegate, and record the (normalised) args when ``pred`` holds."""
    real = _require(module, name)
    calls: List[Tuple[Any, ...]] = []

    @functools.wraps(real)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        norm = _positional(real, args, kwargs)
        if pred(*norm):
            calls.append(norm)
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper)
    return calls


def vanish_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    name: str,
    target_dir: Path,
    *,
    when: str = "before",
    only_if: Optional[Callable[..., bool]] = None,
    raise_: Optional[Callable[[], BaseException]] = None,
    nth: int = 1,
) -> List[Tuple[Any, ...]]:
    """Wrap ``module.name`` to delete ``target_dir`` (a real ``rmtree``) around one call.

    ``when="before"``: remove, then delegate (or raise ``raise_()`` instead of delegating).
    ``when="after"``: delegate, then remove. Fires at most once: on the ``nth`` call for
    which ``only_if(*args)`` holds (every call matches when ``None``). Returns the args of
    the call on which it fired (the positive control).
    """
    real = _require(module, name)
    fired: List[Tuple[Any, ...]] = []
    matched: List[int] = []

    @functools.wraps(real)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        norm = _positional(real, args, kwargs)
        if fired or not (only_if is None or only_if(*norm)):
            return real(*args, **kwargs)
        matched.append(1)
        if len(matched) < nth:
            return real(*args, **kwargs)
        fired.append(norm)
        if when == "before":
            shutil.rmtree(target_dir, ignore_errors=True)
            if raise_ is not None:
                raise raise_()
            return real(*args, **kwargs)
        result = real(*args, **kwargs)
        shutil.rmtree(target_dir, ignore_errors=True)
        return result

    monkeypatch.setattr(module, name, wrapper)
    return fired


def raising_for(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    name: str,
    pred: Callable[..., bool],
    exc: Callable[[], BaseException],
) -> List[Tuple[Any, ...]]:
    """Wrap ``module.name``: raise ``exc()`` on calls where ``pred`` holds, delegate otherwise."""
    real = _require(module, name)
    fired: List[Tuple[Any, ...]] = []

    @functools.wraps(real)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        norm = _positional(real, args, kwargs)
        if pred(*norm):
            fired.append(norm)
            raise exc()
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper)
    return fired


def same_dir(a: Any, b: Any) -> bool:
    return os.path.realpath(str(a)) == os.path.realpath(str(b))


# --------------------------------------------------------------------------- filesystem


def stat_tree(path: Any) -> Optional[Dict[str, Tuple[str, Optional[bytes], int, int]]]:
    """``relpath -> (kind, bytes | None, st_mtime_ns, st_mode)`` for every file and directory
    below ``path`` (``.locks`` included; the root itself excluded); ``None`` if absent."""
    root = Path(path)
    if not root.exists():
        return None
    out: Dict[str, Tuple[str, Optional[bytes], int, int]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            p = os.path.join(dirpath, d)
            st = os.lstat(p)
            out[os.path.relpath(p, root)] = ("dir", None, st.st_mtime_ns, st.st_mode)
        for f in filenames:
            p = os.path.join(dirpath, f)
            st = os.lstat(p)
            data = Path(p).read_bytes() if stat.S_ISREG(st.st_mode) else None
            out[os.path.relpath(p, root)] = ("file", data, st.st_mtime_ns, st.st_mode)
    return out


def without(tree: Optional[Dict[str, Any]], prefixes: List[str]) -> Optional[Dict[str, Any]]:
    """``tree`` minus every path equal to or below one of ``prefixes``."""
    if tree is None:
        return None
    return {
        k: v for k, v in tree.items() if not any(k == p or k.startswith(p + os.sep) for p in prefixes)
    }


def walk_keys(obj: Any) -> Iterator[str]:
    """Every dict key at any depth."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_keys(v)


def notes_json(book_dir: Any, payload: bytes) -> Path:
    path = Path(book_dir) / "notes.json"
    path.write_bytes(payload)
    return path


def notes_record(folder: str, quote: str = "seeded quote", *, n: int = 0) -> Dict[str, Any]:
    from reader3_app.models.annotations import Annotation

    return Annotation(
        id=f"note-{folder}-{n}",
        book_id=folder,
        chapter_index=0,
        quote=quote,
        created_at="2026-09-01T00:00:00+00:00",
    ).to_dict()


def valid_notes(folder: str, count: int = 1) -> bytes:
    records = [notes_record(folder, f"quote {i}", n=i) for i in range(count)]
    return json.dumps({"schema_version": 1, "annotations": records}).encode("utf-8")


@contextlib.contextmanager
def deny(path: Any) -> Iterator[Path]:
    """``chmod 0`` for the duration; the original mode is restored on exit."""
    p = Path(path)
    mode = stat.S_IMODE(os.lstat(p).st_mode)
    os.chmod(p, 0)
    try:
        yield p
    finally:
        os.chmod(p, mode)


EACCES_SKIP = pytest.mark.skipif(os.geteuid() == 0, reason="root ignores mode bits")
