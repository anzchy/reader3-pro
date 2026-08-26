"""The one unpickler allowed to read ``book.pkl``, shared by every loader.

``pickle.load`` on a file the process did not write is arbitrary code
execution: the stream names a callable and its arguments, and ``load`` calls
it. Three modules — ``search_service``, ``vector_search`` and ``web/server`` —
each carried a copy of a restricted unpickler *followed by* ``f.seek(0);
pickle.load(f)``. That fallback ran on any stream the restricted pass refused,
which is precisely the set of streams worth refusing. The restriction was
decorative.

Two things changed here, and only these two:

1. **There is no fallback.** A stream the allow-list refuses raises, and the
   exception travels to the caller's boundary. A ``book.pkl`` that genuinely
   cannot be read is a broken book, and saying so is better than executing it.
2. **``find_class`` is an allow-list**, not a remap that ends in
   ``super().find_class(...)``. The old form rewrote two legacy module paths
   and then resolved anything else it was handed.

**Deliberately not done here**: replacing pickle, adding a checksum or a
signature, or touching the writer in ``reader3.py``. Those are the disk-format
decision that ``012-storage-format`` owns, and prejudging it here would cost a
migration. This module buys what one deleted line and an allow-list can buy,
and leaves the rest named rather than hidden.
"""

from __future__ import annotations

import pickle
from typing import IO, Any

#: The only classes a ``book.pkl`` may name. These are the four dataclasses
#: ``reader3.py`` serializes; nothing else in the codebase is ever pickled.
ALLOWED_READER3_CLASSES = frozenset(
    {"Book", "BookMetadata", "ChapterContent", "TOCEntry"}
)

#: Module paths that historically held those four classes. A ``book.pkl``
#: written while running ``reader3.py`` as a script names ``__main__.Book``;
#: an older packaging named ``reader3.Book``. Both are remapped, both are
#: resolved to ``reader3_app.reader3`` regardless of what those names hold now.
_LEGACY_MODULES = frozenset({"__main__", "reader3", "reader3_app.reader3"})

_TARGET_MODULE = "reader3_app.reader3"

#: Built-ins the pickle protocol itself may reach for when reconstructing the
#: containers inside a Book. Types only — no callables. ``eval``, ``exec``,
#: ``getattr`` and ``__import__`` are absent on purpose: each is a complete
#: escape from the rest of this list.
ALLOWED_BUILTINS = frozenset(
    {
        "bool",
        "bytearray",
        "bytes",
        "complex",
        "dict",
        "float",
        "frozenset",
        "int",
        "list",
        "set",
        "str",
        "tuple",
    }
)


class Reader3Unpickler(pickle.Unpickler):
    """An unpickler that resolves the four Book classes and nothing else."""

    def find_class(self, module: str, name: str) -> Any:  # type: ignore[override]
        if name in ALLOWED_READER3_CLASSES and module in _LEGACY_MODULES:
            return super().find_class(_TARGET_MODULE, name)
        if module == "builtins" and name in ALLOWED_BUILTINS:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(
            f"book.pkl names a class that is not allowed: {module}.{name}"
        )


def safe_load(f: IO[bytes]) -> Any:
    """Read one Book from an open binary stream, or raise."""
    return Reader3Unpickler(f).load()


def load_book_file(path: str) -> Any:
    """Read one Book from ``path``, or raise."""
    with open(path, "rb") as f:
        return safe_load(f)
