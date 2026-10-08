"""012 WI-2a.1: the pure book fingerprint (``compute_book_fingerprint`` / ``_fingerprint_payload``).

Matrix: ``.claude/tdd-guardian/tests-20261008-234253.md`` section "WI-2a.1" (cases F1-01 .. F1-11).

Laws (policy-core S4/S5):
- determinism: a pure function of ``(epub_sha256, spine, extractor_version)``,
  blind to the spine's container type (F1-03);
- single-component sensitivity: changing any one component, or adding/removing an item, changes the digest (F1-04);
- encoding injectivity: the canonical payload decodes back to exactly its inputs (F1-05, F1-06);
- order significance: the spine is hashed positionally, never sorted (F1-07).

F1-11 (stdlib-only import) is the existing ``test_m16`` in ``test_book_format_manifest.py``, unchanged.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import pytest
from hypothesis import HealthCheck, assume, event, given, settings
from hypothesis import strategies as st

from reader3_app import book_format as bf


def props(max_examples: int) -> Any:
    return settings(
        deadline=None,
        max_examples=max_examples,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
    )


_HEX64 = re.compile(r"[0-9a-f]{64}")

A, B, C = "a" * 64, "b" * 64, "c" * 64

# --------------------------------------------------------------------------- known-answer vectors

KAT_SPINE = [("text/one.xhtml", 0, B), ("text/two.xhtml", 1, C)]
# Written out by hand from the plan's encoding (sort_keys, compact separators), not copied from the implementation.
KAT_BYTES = (
    b'{"epub_sha256":"' + b"a" * 64 + b'","extractor_version":1,"spine":'
    b'[["text/one.xhtml",0,"' + b"b" * 64 + b'"],["text/two.xhtml",1,"' + b"c" * 64 + b'"]]}'
)
KAT_DIGEST = "30e384f80b65cb713eb060905f2b65d317cfdee113d3b845bef19c999ef01e06"

KAT2_SPINE = [("text/第1章.xhtml", 0, B)]  # text/第1章.xhtml
KAT2_BYTES = (
    b'{"epub_sha256":"' + b"a" * 64 + b'","extractor_version":1,"spine":'
    b'[["text/\xe7\xac\xac1\xe7\xab\xa0.xhtml",0,"' + b"b" * 64 + b'"]]}'
)
KAT2_DIGEST = "d6a284793682f794aee974534567d1091f5c57be0f704234409efb3b7c3683a8"


def test_f1_01_known_answer_vector() -> None:
    assert hashlib.sha256(KAT_BYTES).hexdigest() == KAT_DIGEST  # the oracle is independent of the code
    assert bf._fingerprint_payload(A, KAT_SPINE, 1) == KAT_BYTES
    assert bf.compute_book_fingerprint(A, KAT_SPINE, 1) == KAT_DIGEST


def test_f1_02_non_ascii_href_is_raw_utf8_and_not_normalized() -> None:
    assert hashlib.sha256(KAT2_BYTES).hexdigest() == KAT2_DIGEST
    assert bf._fingerprint_payload(A, KAT2_SPINE, 1) == KAT2_BYTES
    assert bf.compute_book_fingerprint(A, KAT2_SPINE, 1) == KAT2_DIGEST


# --------------------------------------------------------------------------- generators

# Quote, separator, escape, NUL, combining and CJK characters: the collisions a hand-rolled join would have.
_TRICKY = [",", '"', "]", "[", "\\", "\x00", " ", ":", "{", "}", "é", "é", "第", "\U0001f600"]

st_sha = st.text("0123456789abcdef", min_size=64, max_size=64)
st_href = st.lists(st.one_of(st.sampled_from(_TRICKY), st.characters(codec="utf-8")), max_size=30).map("".join)
st_item = st.tuples(st_href, st.integers(0, 10_000), st_sha)
st_version = st.integers(0, 50)


def st_spine(min_size: int = 0) -> st.SearchStrategy[list[tuple[str, int, str]]]:
    return st.lists(st_item, min_size=min_size, max_size=8)


# --------------------------------------------------------------------------- laws


@props(200)
@given(epub=st_sha, spine=st_spine(), version=st_version)
def test_f1_03_deterministic_hex_digest_independent_of_container(
    epub: str, spine: list[tuple[str, int, str]], version: int
) -> None:
    d1 = bf.compute_book_fingerprint(epub, tuple(spine), version)
    d2 = bf.compute_book_fingerprint(str(epub), [tuple(item) for item in spine], int(version))
    assert d1 == d2
    assert _HEX64.fullmatch(d1)


@props(300)
@given(epub=st_sha, spine=st_spine(min_size=1), version=st_version, data=st.data())
def test_f1_04_any_single_component_change_changes_the_digest(
    epub: str, spine: list[tuple[str, int, str]], version: int, data: st.DataObject
) -> None:
    kind = data.draw(st.sampled_from(["epub", "href", "order", "sha", "version", "append", "remove"]), label="kind")
    event(kind)
    m_epub, m_spine, m_version = epub, list(spine), version
    i = data.draw(st.integers(0, len(spine) - 1), label="i")
    href, order, sha = spine[i]
    if kind == "epub":
        m_epub = data.draw(st_sha)
    elif kind == "href":
        m_spine[i] = (data.draw(st_href), order, sha)
    elif kind == "order":
        m_spine[i] = (href, data.draw(st.integers(0, 10_000)), sha)
    elif kind == "sha":
        m_spine[i] = (href, order, data.draw(st_sha))
    elif kind == "version":
        m_version = data.draw(st_version)
    elif kind == "append":
        m_spine.append(data.draw(st_item))
    else:
        del m_spine[i]
    assume((m_epub, m_spine, m_version) != (epub, spine, version))
    assert bf.compute_book_fingerprint(m_epub, m_spine, m_version) != bf.compute_book_fingerprint(epub, spine, version)


@props(300)
@given(epub=st_sha, spine=st_spine(), version=st_version)
def test_f1_05_payload_decodes_back_to_its_inputs(epub: str, spine: list[tuple[str, int, str]], version: int) -> None:
    payload = bf._fingerprint_payload(epub, spine, version)
    decoded = json.loads(payload.decode("utf-8"))
    assert decoded == {"epub_sha256": epub, "extractor_version": version, "spine": [[h, o, s] for h, o, s in spine]}
    assert bf.compute_book_fingerprint(epub, spine, version) == hashlib.sha256(payload).hexdigest()


_PAIRS = {
    "comma-vs-split": ([("a,b", 0, B)], [("a", 0, B), ("b", 0, B)]),
    "quote": ([('a"', 0, B)], [("a", 0, B)]),
    "nul": ([("a\x00", 0, B)], [("a", 0, B)]),
    "nfc-vs-nfd": ([("é", 0, B)], [("é", 0, B)]),
    "leading-space": ([(" a", 0, B)], [("a", 0, B)]),
    "trailing-space": ([("a ", 0, B)], [("a", 0, B)]),
    "empty-href-vs-empty-spine": ([("", 0, B)], []),
}


@pytest.mark.parametrize(("left", "right"), list(_PAIRS.values()), ids=list(_PAIRS))
def test_f1_06_adversarial_distinct_pairs_never_collide(
    left: list[tuple[str, int, str]], right: list[tuple[str, int, str]]
) -> None:
    assert left != right  # the pair really is two different inputs (NFC/NFD would look identical if typed raw)
    assert bf.compute_book_fingerprint(A, left, 1) != bf.compute_book_fingerprint(A, right, 1)


@props(150)
@given(epub=st_sha, spine=st_spine(min_size=2), version=st_version, data=st.data())
def test_f1_07_swapping_two_distinct_entries_changes_the_digest(
    epub: str, spine: list[tuple[str, int, str]], version: int, data: st.DataObject
) -> None:
    i = data.draw(st.integers(0, len(spine) - 2), label="i")
    j = data.draw(st.integers(i + 1, len(spine) - 1), label="j")
    assume(spine[i] != spine[j])
    swapped = list(spine)
    swapped[i], swapped[j] = swapped[j], swapped[i]
    assert bf.compute_book_fingerprint(epub, swapped, version) != bf.compute_book_fingerprint(epub, spine, version)


# --------------------------------------------------------------------------- boundaries and guards


def test_f1_08_empty_spine_is_fingerprintable_and_distinct_from_one_item() -> None:
    empty = bf.compute_book_fingerprint(A, [], 1)
    one = bf.compute_book_fingerprint(A, [("text/c1.xhtml", 0, B)], 1)
    assert _HEX64.fullmatch(empty)
    assert _HEX64.fullmatch(one)
    assert empty != one
    assert bf.compute_book_fingerprint(A, (), 1) == empty


_ITEM0, _ITEM1 = KAT_SPINE

_BAD: dict[str, tuple[Any, Any, Any, str]] = {
    "epub-upper": ("A" * 64, KAT_SPINE, 1, "epub_sha256"),
    "epub-63": ("a" * 63, KAT_SPINE, 1, "epub_sha256"),
    "epub-65": ("a" * 65, KAT_SPINE, 1, "epub_sha256"),
    "epub-non-hex": ("g" * 64, KAT_SPINE, 1, "epub_sha256"),
    "epub-none": (None, KAT_SPINE, 1, "epub_sha256"),
    "item-sha-upper": (A, [("text/one.xhtml", 0, "B" * 64), _ITEM1], 1, "sha256"),
    "item-sha-63": (A, [("text/one.xhtml", 0, "b" * 63), _ITEM1], 1, "sha256"),
    "order-bool": (A, [("text/one.xhtml", True, B), _ITEM1], 1, "order"),
    "order-negative": (A, [("text/one.xhtml", -1, B), _ITEM1], 1, "order"),
    "order-float": (A, [("text/one.xhtml", 1.0, B), _ITEM1], 1, "order"),
    "order-str": (A, [("text/one.xhtml", "0", B), _ITEM1], 1, "order"),
    "version-negative": (A, KAT_SPINE, -1, "extractor_version"),
    "version-str": (A, KAT_SPINE, "1", "extractor_version"),
    "version-bool": (A, KAT_SPINE, True, "extractor_version"),
    "version-float": (A, KAT_SPINE, 1.0, "extractor_version"),
    "href-none": (A, [(None, 0, B), _ITEM1], 1, "href"),
    "href-bytes": (A, [(b"text/one.xhtml", 0, B), _ITEM1], 1, "href"),
    "href-int": (A, [(1, 0, B), _ITEM1], 1, "href"),
    "item-two-tuple": (A, [("text/one.xhtml", 0), _ITEM1], 1, "spine[0]"),
}


@pytest.mark.parametrize(("epub", "spine", "version", "field"), list(_BAD.values()), ids=list(_BAD))
def test_f1_09_malformed_inputs_raise_rather_than_hash(epub: Any, spine: Any, version: Any, field: str) -> None:
    with pytest.raises(bf.BookFormatError) as ei:
        bf.compute_book_fingerprint(epub, spine, version)
    assert isinstance(ei.value, ValueError)
    assert field in str(ei.value)


def test_f1_10_extractor_version_unknown_is_zero_and_a_valid_input() -> None:
    assert bf.EXTRACTOR_VERSION_UNKNOWN == 0
    unknown = bf.compute_book_fingerprint(A, KAT_SPINE, bf.EXTRACTOR_VERSION_UNKNOWN)
    assert _HEX64.fullmatch(unknown)
    assert unknown != KAT_DIGEST
