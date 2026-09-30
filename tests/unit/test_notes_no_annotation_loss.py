"""WI-6: a `notes.json` we cannot read must never be reported as "no annotations",
because the very next `add_annotation` writes that emptiness back to disk.

`load_annotations` swallowed failures twice, and both `noqa` comments in
`notes_service.py` already said so out loud (`FIXME(012): 无正当理由`):

    * the whole file unreadable  -> `return []`
    * one record unreadable      -> `continue`

`add_annotation` is load -> append -> **save the whole file**. So either read
failure followed by a single new highlight silently and permanently erased every
annotation the user had made in that book. Annotations are not regenerable: no
re-index, no re-download, no re-parse brings them back.

The rule pinned here is the one `ensure_book_uuid` and (since WI-4)
`load_ai_settings` already follow: **user data we cannot read is not "absent"**.
A 500 is recoverable; a deleted highlight is not.

The load-bearing cases are N2 and N4, and what they assert is *the data is still
there* -- byte-for-byte -- not "an exception was raised". Reverting either
`raise` to its old silent fallback must turn those red for the data reason. A
test that only asserted "it raises" would pass against an implementation that
raised *after* clobbering the file, which is the exact failure being prevented.

Assertion levels (see tests/unit/conftest.py):
    L2 return value, or a single field of on-disk state
    L3 the file's bytes across a whole read-modify-write cycle

Every case works under ``tmp_path`` via the shared ``books_dir`` fixture; the
developer's real ``books/`` is fenced recursively by
``_never_touch_the_real_books_dir`` in ``tests/unit/conftest.py``, because a test
that leaked onto it would do the exact damage under test.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import List

import pytest

from reader3_app.models.annotations import Annotation
from reader3_app.notes_service import (
    NOTES_FILENAME,
    NOTES_SCHEMA_VERSION,
    NotesFileError,
    add_annotation,
    delete_annotation,
    load_annotations,
    save_annotations,
    update_annotation,
)

BOOK_ID = "dracula_data"

#: Appended to a *valid* notes.json. The original records stay in the file,
#: readable by a human -- which is the whole point: a person can repair this,
#: they cannot un-delete a highlight.
CORRUPTING_SUFFIX = b"\n}}] <- trailing garbage, this file is no longer JSON\n"


def _annotation(n: int) -> Annotation:
    return Annotation(
        id=f"note-{n}",
        book_id=BOOK_ID,
        chapter_index=n,
        type="marker",
        color="yellow",
        quote=f"quote number {n}",
        prefix="before ",
        suffix=" after",
        note_text=f"the user typed this by hand: {n}",
    )


@pytest.fixture
def notes_path(books_dir: Path) -> Path:
    return books_dir / BOOK_ID / NOTES_FILENAME


@pytest.fixture
def three_saved_annotations(books_dir: Path) -> List[Annotation]:
    """Three annotations written through the real writer, as a user would have."""
    anns = [_annotation(0), _annotation(1), _annotation(2)]
    # 018 WI-2 amendment: writers no longer create the book dir (contract item 5); the book exists in setup.
    (books_dir / BOOK_ID).mkdir(parents=True, exist_ok=True)
    save_annotations(str(books_dir), BOOK_ID, anns)
    return anns


def _write_raw(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _shell_with_two_good_and_one_bad() -> str:
    """A structurally valid notes.json whose middle record has no ``quote``.

    ``Annotation.__post_init__`` rejects it (``quote is required``); the old code
    hit that, ran ``continue``, and dropped the record on the floor.
    """
    good_a = _annotation(0).to_dict()
    good_b = _annotation(1).to_dict()
    bad = _annotation(9).to_dict()
    del bad["quote"]
    del bad["book_id"]
    return json.dumps(
        {"schema_version": 1, "book_id": BOOK_ID, "annotations": [good_a, bad, good_b]},
        ensure_ascii=False,
        indent=2,
    )


# --------------------------------------------------------------------------
# N1 -- whole-file corruption raises, L2 / S1
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        pytest.param('{"schema_version": 1, "annotations": [] <<<not json', id="invalid-json"),
        pytest.param('["not", "an", "object"]', id="top-level-list"),
        pytest.param('{"schema_version": 1, "annotations": "nope"}', id="annotations-not-a-list"),
    ],
)
def test_N1_坏掉的整份notes文件让load抛错而不是返回空列表(
    books_dir: Path, notes_path: Path, body: str
) -> None:
    """L2 / S1. Three ways to be unreadable; none of them means "no annotations"."""
    _write_raw(notes_path, body)

    with pytest.raises(NotesFileError) as excinfo:
        load_annotations(str(books_dir), BOOK_ID)

    # The user can repair a file only if we tell them which file.
    assert NOTES_FILENAME in str(excinfo.value)
    assert str(notes_path) in str(excinfo.value)


# --------------------------------------------------------------------------
# N2 -- LOAD-BEARING. Adding a note after whole-file corruption must not erase
#        the notes that were already there. L3 / S2
# --------------------------------------------------------------------------


def test_N2_整份坏文件之后新增一条标注不会抹掉原有的三条(
    books_dir: Path, notes_path: Path, three_saved_annotations: List[Annotation]
) -> None:
    """L3 / S2. The whole point of the work item.

    Assertions are ordered data-first on purpose: with the old
    ``except Exception: return []`` this test must fail because *the three
    annotations are gone*, not because *no exception was raised*.
    """
    with notes_path.open("ab") as f:
        f.write(CORRUPTING_SUFFIX)
    before = notes_path.read_bytes()

    fourth = _annotation(3)
    raised: BaseException | None = None
    try:
        add_annotation(str(books_dir), fourth)
    except NotesFileError as exc:
        raised = exc

    after = notes_path.read_bytes()

    assert after == before, (
        "notes.json was rewritten on top of a file we could not read -- "
        "the user's existing annotations have been destroyed"
    )
    text = after.decode("utf-8")
    for ann in three_saved_annotations:
        assert ann.id in text, f"annotation {ann.id} is no longer in notes.json"
        assert ann.quote in text, f"the text of annotation {ann.id} is gone"

    # Only once the data is proven safe does *how* we refused matter.
    assert isinstance(raised, NotesFileError), (
        f"add_annotation must surface the unreadable file, got {raised!r}"
    )


# --------------------------------------------------------------------------
# N3 -- one bad record raises too, L2 / S1
# --------------------------------------------------------------------------


def test_N3_单条坏记录也抛错而不是被静默跳过(books_dir: Path, notes_path: Path) -> None:
    """L2 / S1. A record we cannot parse is still the user's data."""
    _write_raw(notes_path, _shell_with_two_good_and_one_bad())

    with pytest.raises(NotesFileError) as excinfo:
        load_annotations(str(books_dir), BOOK_ID)

    assert str(notes_path) in str(excinfo.value)


# --------------------------------------------------------------------------
# N4 -- LOAD-BEARING. One bad record must not cost the user the good ones.
#        L3 / S2
# --------------------------------------------------------------------------


def test_N4_单条坏记录之后新增一条标注不会抹掉另外两条(
    books_dir: Path, notes_path: Path
) -> None:
    """L3 / S2. Data-first assertions, same reasoning as N2.

    With the old ``continue``, ``load_annotations`` returned the two good
    records, ``add_annotation`` appended a third, and ``save_annotations``
    rewrote the file -- with the third record simply absent, forever.
    """
    _write_raw(notes_path, _shell_with_two_good_and_one_bad())
    before = notes_path.read_bytes()

    raised: BaseException | None = None
    try:
        add_annotation(str(books_dir), _annotation(3))
    except NotesFileError as exc:
        raised = exc

    after = notes_path.read_bytes()

    assert after == before, (
        "notes.json was rewritten while one record was unreadable -- "
        "that record has now been deleted from disk"
    )
    text = after.decode("utf-8")
    for ann_id in ("note-0", "note-1"):
        assert ann_id in text, f"good annotation {ann_id} is no longer in notes.json"
    assert "note-9" in text, "the unreadable record was dropped from the file"

    assert isinstance(raised, NotesFileError), (
        f"add_annotation must surface the unreadable record, got {raised!r}"
    )


# --------------------------------------------------------------------------
# N5 -- a file that was never written is a legal empty state, L2 / S1
# --------------------------------------------------------------------------


def test_N5_文件不存在仍然返回空列表(books_dir: Path, notes_path: Path) -> None:
    """L2 / S1. "This book has no annotations yet" is not corruption.

    Raising here would trade a real bug for a fake one: every book a user has
    never highlighted would 500 on open.
    """
    assert not notes_path.exists()
    assert load_annotations(str(books_dir), BOOK_ID) == []


def test_N5b_空目录存在但没有notes文件时也返回空列表(books_dir: Path) -> None:
    """L2 / S1. Same state, reached via an existing book directory."""
    (books_dir / BOOK_ID).mkdir(parents=True)
    assert load_annotations(str(books_dir), BOOK_ID) == []


# --------------------------------------------------------------------------
# N6 -- the other two mutators do not swallow it either, L2 / S1
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(
            lambda d: delete_annotation(d, BOOK_ID, "note-0"),
            id="delete_annotation",
        ),
        pytest.param(
            lambda d: update_annotation(d, BOOK_ID, "note-0", "edited"),
            id="update_annotation",
        ),
    ],
)
def test_N6_删除和更新在坏文件上同样抛错且不改动文件(
    books_dir: Path, notes_path: Path, three_saved_annotations: List[Annotation], call
) -> None:
    """L2 / S1. Both also load -> mutate -> save the whole file."""
    with notes_path.open("ab") as f:
        f.write(CORRUPTING_SUFFIX)
    before = notes_path.read_bytes()

    raised: BaseException | None = None
    try:
        call(str(books_dir))
    except NotesFileError as exc:
        raised = exc

    assert notes_path.read_bytes() == before, "the unreadable file was overwritten"
    assert isinstance(raised, NotesFileError), f"expected NotesFileError, got {raised!r}"


# --------------------------------------------------------------------------
# N7 -- added case: the six server call sites are covered by one handler.
#        L2 / S1
# --------------------------------------------------------------------------


def test_N7_服务器注册了一个NotesFileError处理器返回500并带上文件路径() -> None:
    """L2 / S1. Not in the original matrix; added because the acceptance criterion
    is "one ``@app.exception_handler``", and six per-call-site ``try`` blocks
    would satisfy every other case here while still missing the seventh call site
    somebody adds next month.
    """
    from reader3_app.web.server import app

    handler = app.exception_handlers.get(NotesFileError)
    assert handler is not None, "no @app.exception_handler(NotesFileError) is registered"

    exc = NotesFileError("/books/dracula_data/notes.json is not valid JSON")
    response = asyncio.run(handler(None, exc))

    assert response.status_code == 500
    assert b"notes.json" in response.body, "the response must name the file to fix"


# --------------------------------------------------------------------------
# Added cases: the remaining branches of the new refusal, and the two shapes
# that are genuinely empty rather than corrupt. L2 / S1
# --------------------------------------------------------------------------


def test_N1d_文件存在但读不出来OSError也抛错(books_dir: Path, notes_path: Path) -> None:
    """L2 / S1. The acceptance criterion names OSError explicitly.

    ``notes.json`` is created as a *directory*, so ``open()`` raises
    ``IsADirectoryError``. That is portable in a way ``chmod 000`` is not --
    under a root CI user the permission bit simply does not apply.
    """
    notes_path.mkdir(parents=True)

    with pytest.raises(NotesFileError) as excinfo:
        load_annotations(str(books_dir), BOOK_ID)

    assert str(notes_path) in str(excinfo.value)


def test_N5c_文件内容是json的null时返回空列表(books_dir: Path, notes_path: Path) -> None:
    """L2 / S1. ``null`` carries no annotations and therefore loses none.

    This keeps the pre-existing ``json.load(f) or {}`` leniency rather than
    widening the refusal. The rule being enforced is "do not report user data as
    absent"; a file whose entire content is ``null`` holds no user data to
    misreport, so raising here would only cost a user an outage.
    """
    _write_raw(notes_path, "null")
    assert load_annotations(str(books_dir), BOOK_ID) == []


def test_N5d_没有annotations字段时返回空列表(books_dir: Path, notes_path: Path) -> None:
    """L2 / S1. A header-only file: written, but nothing highlighted yet."""
    _write_raw(notes_path, json.dumps({"schema_version": 1, "book_id": BOOK_ID}))
    assert load_annotations(str(books_dir), BOOK_ID) == []


# --------------------------------------------------------------------------
# WI-6b -- the residual hole in WI-6: a file written by a *future* schema.
#
# WI-6's acceptance criterion said "raise if `annotations` is not a list". A
# missing field is not "not a list": `data.get("annotations")` returns `None`
# and the normalisation two lines down turns it into `[]`. So a notes.json from
# a later schema -- one that renamed the field, which is exactly what 012 is
# scheduled to do -- reads as "this book has no annotations", and the next
# highlight saves that emptiness over it. Measured, not inferred:
#
#     load_annotations(...) -> []          # no error
#     add_annotation(...)                  # one casual new highlight
#     => the original records are gone, the file's bytes have changed
#
# `save_annotations` has always stamped `schema_version`; `load_annotations`
# has never read it. This closes that.
# --------------------------------------------------------------------------


def _future_schema_file(version: object) -> str:
    """A notes.json from a schema this code predates.

    The annotations live under ``"notes"`` rather than ``"annotations"`` on
    purpose: a future version that only *added* fields would still be read
    correctly by accident, and would prove nothing. The dangerous shape is the
    one where our field lookup comes back empty while the user's data sits
    right there in the file under another name.
    """
    return json.dumps(
        {
            "schema_version": version,
            "book_id": BOOK_ID,
            "notes": [
                {
                    "id": "keep-me",
                    "book_id": BOOK_ID,
                    "chapter_index": 7,
                    "type": "marker",
                    "color": "yellow",
                    "quote": "珍贵的原文，用户亲手划的",
                    "prefix": "before ",
                    "suffix": " after",
                    "note_text": "written by a newer reader3",
                }
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


# --------------------------------------------------------------------------
# V1 -- a file from a newer schema makes load refuse. L2 / S1
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "version",
    [
        pytest.param(2, id="next-version"),
        pytest.param(99, id="far-future-version"),
        pytest.param("2", id="version-is-a-string"),
    ],
)
def test_V1_未来版本的notes文件让load抛错(
    books_dir: Path, notes_path: Path, version: object
) -> None:
    """L2 / S1.

    A version number we cannot interpret is as unreadable as a version we know
    is too new -- ``"2"`` is not ``2``, and guessing which one the writer meant
    is how data gets overwritten. Both refuse.
    """
    _write_raw(notes_path, _future_schema_file(version))

    with pytest.raises(NotesFileError) as excinfo:
        load_annotations(str(books_dir), BOOK_ID)

    message = str(excinfo.value)
    # Which file to repair, what it says it is, and what we can actually read.
    assert str(notes_path) in message
    assert str(version) in message, "the message must quote the version found in the file"
    assert str(NOTES_SCHEMA_VERSION) in message, (
        "the message must name the version this code supports"
    )


# --------------------------------------------------------------------------
# V2 -- LOAD-BEARING. A highlight added after reading a future-schema file must
#       not destroy what that file holds. L3 / S2
# --------------------------------------------------------------------------


def test_V2_未来版本文件之后新增一条标注不会抹掉里面的数据(
    books_dir: Path, notes_path: Path
) -> None:
    """L3 / S2. The reason WI-6b exists, and the assertion that decides it.

    Data-first ordering is not stylistic here. An implementation that put the
    version check *after* the read-modify-write, or that raised only once the
    file had already been replaced, would satisfy "it raises" while doing the
    precise damage this work item is about. So the file's bytes are checked
    first, then the surviving id and quote, and only then *how* we refused.
    """
    _write_raw(notes_path, _future_schema_file(2))
    before = notes_path.read_bytes()

    raised: BaseException | None = None
    try:
        add_annotation(str(books_dir), _annotation(3))
    except NotesFileError as exc:
        raised = exc

    after = notes_path.read_bytes()

    assert after == before, (
        "notes.json written by a newer schema was rewritten by this one -- "
        "everything it held has been destroyed"
    )
    text = after.decode("utf-8")
    assert "keep-me" in text, "the annotation from the newer file is gone"
    assert "珍贵的原文，用户亲手划的" in text, "the user's highlighted text is gone"

    assert isinstance(raised, NotesFileError), (
        f"add_annotation must surface the unreadable schema version, got {raised!r}"
    )


# --------------------------------------------------------------------------
# V3 -- the gate must not break files we can genuinely read. L2 / S1
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "header",
    [
        pytest.param({}, id="no-schema_version-field"),
        pytest.param({"schema_version": 1}, id="current-version"),
        pytest.param({"schema_version": 0}, id="older-version"),
    ],
)
def test_V3_旧文件与当前版本文件不受版本闸门影响(
    books_dir: Path, notes_path: Path, header: dict
) -> None:
    """L2 / S1. The refusal is one-sided by construction.

    Every notes.json on every existing install is either unversioned or
    version 1. A gate that rejected those would turn a data-loss fix into a
    total outage, which is a worse trade than the bug.
    """
    payload = dict(header)
    payload["book_id"] = BOOK_ID
    payload["annotations"] = [_annotation(0).to_dict(), _annotation(1).to_dict()]
    _write_raw(notes_path, json.dumps(payload, ensure_ascii=False, indent=2))

    loaded = load_annotations(str(books_dir), BOOK_ID)

    assert [a.id for a in loaded] == ["note-0", "note-1"]
    assert loaded[0].quote == "quote number 0"
