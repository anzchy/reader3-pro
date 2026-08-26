"""WI-9: `ai_meta.json` must survive a round-trip with every key it arrived with.

`_read_ai_meta()` used to end with

    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, str):
            out[k] = v

which silently drops every non-string value. Two consequences, both silent, both
destructive:

1. **Read side.** A `book_uuid` stored as a non-string (`123`, `null`, a list)
   reads back as *absent*. `ensure_book_uuid()` therefore mints a fresh uuid and
   `os.replace()`s it over the file -- precisely the loss its own docstring
   claims to prevent. The sibling branch, "present but not parseable as a UUID",
   already raises "refusing to overwrite it"; this fork was left open.
2. **Write side.** `ensure_book_uuid()` reads the file, sets one key, and dumps
   the *whole* dict back. Because the read already discarded every non-string
   value, any such key on disk vanishes during that rewrite -- even on the
   ordinary first-run path where minting a uuid is the correct thing to do.

The rule this lane pins down: preserve every key verbatim, hard-type-check
`book_uuid` only, and never let a rewrite cost the file a key it already held.
Unknown keys with non-string values are *not* an error -- a future writer adding
`{"indexed_at": 1724...}` must not turn every read into a 500.

Assertion levels (see tests/unit/conftest.py):
    L2 return value, or a single field of on-disk state
    L3 the file's bytes before and after
"""

from __future__ import annotations

import hashlib
import contextlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from reader3_app.ai.books import _read_ai_meta, ensure_book_uuid

VALID_UUID = "9f6a1e2c-0000-4000-8000-000000000001"


def _write_meta(books_dir: Path, folder: str, payload: Any) -> Path:
    d = books_dir / folder
    d.mkdir(parents=True, exist_ok=True)
    p = d / "ai_meta.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


# --- M1 -------------------------------------------------------------------


@pytest.mark.parametrize("bad_uuid", [123, None, ["x"], {"a": 1}, True])
def test_non_string_book_uuid_raises_naming_path_and_type(
    books_dir: Path, bad_uuid: Any
) -> None:
    """L2: a `book_uuid` we cannot even treat as text is a fault, not an absence."""
    _write_meta(books_dir, "dracula_data", {"book_uuid": bad_uuid})

    with pytest.raises(ValueError) as excinfo:
        ensure_book_uuid(str(books_dir), "dracula_data")

    message = str(excinfo.value)
    assert "ai_meta.json" in message, f"the message does not name the file: {message}"
    assert type(bad_uuid).__name__ in message, (
        f"the message does not name the actual type {type(bad_uuid).__name__!r}: {message}"
    )


# --- M2 (load-bearing) ----------------------------------------------------


def test_non_string_book_uuid_is_not_overwritten_by_a_fresh_one(books_dir: Path) -> None:
    """L3: raising is not enough -- the bytes on disk must be untouched.

    M1 passes for an implementation that writes the new uuid and *then* raises.
    This one asserts the file's md5 and re-reads the stored value, so a
    write-then-raise implementation fails here.
    """
    p = _write_meta(books_dir, "dracula_data", {"book_uuid": 123, "other": "keep"})
    before_md5 = _md5(p)

    with pytest.raises(ValueError):
        ensure_book_uuid(str(books_dir), "dracula_data")

    assert _md5(p) == before_md5, "ensure_book_uuid rewrote a file it could not read"
    on_disk = json.loads(p.read_text("utf-8"))
    assert on_disk["book_uuid"] == 123, (
        f"the original book_uuid is gone from the file: {on_disk!r}"
    )
    assert on_disk["other"] == "keep"
    assert not (p.parent / "ai_meta.json.tmp").exists()


# --- M3 -------------------------------------------------------------------


def test_non_string_values_on_other_keys_are_read_back_verbatim(books_dir: Path) -> None:
    """L2: only `book_uuid` is type-checked; everything else round-trips as-is."""
    p = _write_meta(
        books_dir,
        "dracula_data",
        {"book_uuid": VALID_UUID, "chunk_count": 42, "flags": {"a": True}},
    )

    meta = _read_ai_meta(str(p))

    assert meta is not None
    assert meta["chunk_count"] == 42
    assert meta["flags"] == {"a": True}
    assert meta["book_uuid"] == VALID_UUID


# --- M4 (load-bearing) ----------------------------------------------------


def test_minting_a_first_uuid_keeps_every_pre_existing_key(books_dir: Path) -> None:
    """L3: the rewrite path must not charge the file for the keys it already had.

    No `book_uuid` on disk, so this genuinely writes -- which is exactly when the
    read-side filter used to erase `chunk_count` and `flags` from the file.
    """
    p = _write_meta(
        books_dir,
        "dracula_data",
        {"chunk_count": 42, "flags": {"a": True}, "label": "x"},
    )

    got = ensure_book_uuid(str(books_dir), "dracula_data")

    assert got == str(UUID(got))
    on_disk = json.loads(p.read_text("utf-8"))
    assert on_disk["chunk_count"] == 42, f"chunk_count was dropped by the rewrite: {on_disk!r}"
    assert on_disk["flags"] == {"a": True}, f"flags was dropped by the rewrite: {on_disk!r}"
    assert on_disk["label"] == "x", f"label was dropped by the rewrite: {on_disk!r}"
    assert on_disk["book_uuid"] == got
    assert not (p.parent / "ai_meta.json.tmp").exists()


# --- M5 -------------------------------------------------------------------


def test_valid_uuid_is_returned_without_rewriting_the_file(books_dir: Path) -> None:
    """L2/L3: regression guard -- the fix must not turn every read into a write."""
    p = _write_meta(
        books_dir,
        "dracula_data",
        {"book_uuid": VALID_UUID, "chunk_count": 42},
    )
    before_md5 = _md5(p)

    got = ensure_book_uuid(str(books_dir), "dracula_data")

    assert got == VALID_UUID
    assert _md5(p) == before_md5, "a healthy ai_meta.json was rewritten for no reason"


# --- M2b: 承重断言必须是「数据还在」，不能是「抛了没」 ----------------------


def test_m2b_falsy_non_string_uuid_survives_even_if_nothing_raises(books_dir: Path) -> None:
    """L3: M2 的红是**异常类型**不对，不是数据没了——那还不够。

    把类型闸门删掉之后，``123`` 这样的真值走到 ``(123 or "").strip()`` 上抛
    ``AttributeError``：文件是活下来了，但纯属侥幸，而 ``pytest.raises(ValueError)``
    会在断磁盘之前就先失败，于是 M2 的红说的是「抛错的类型变了」。

    假值不一样。``0``／``False`` 落到 ``(0 or "")`` 上得到空串，被当成「这本书还没有
    uuid」，于是**真的生成一个新 uuid 并整份写回**——原值当场消失且不报错。所以这里
    不断异常：吞掉任何异常，无条件比对盘上的字节。闸门在，值就还在；闸门没了，红的
    内容就是「原来的 book_uuid 不在文件里了」。
    """
    for bad in (0, False, []):
        p = _write_meta(books_dir, "dracula_data", {"book_uuid": bad, "other": "keep"})
        before = p.read_bytes()

        with contextlib.suppress(Exception):
            ensure_book_uuid(str(books_dir), "dracula_data")

        assert p.read_bytes() == before, (
            f"book_uuid={bad!r} 被静默换掉了，盘上现在是 {p.read_text('utf-8')!r}"
        )
