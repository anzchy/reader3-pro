"""012 WI-2a.3: reader3 extracts the book fingerprint components from the raw EPUB.

Matrix: ``.claude/tdd-guardian/tests-20261008-234253.md`` section "WI-2a.3" (cases R3-01 .. R3-13).

Laws (policy-core S3/S4):
- lockstep (R6): the fingerprint's ``(href, order)`` list equals the processed chapters' ``(href, order)`` list, and
  ``order`` is the spine index (R3-02, R3-03, R3-04);
- raw-bytes identity: every component sha equals the sha256 of the zip member, read with ``zipfile`` and the OPF dir
  -- an oracle that never touches ebooklib (R3-01, R3-08, R3-09);
- metamorphic: changing one XHTML member changes exactly that item's sha and the digest (R3-06), including an
  HTML-only change that leaves ``chapter.text`` identical (R3-07).

Two builds of one spec never have equal whole-file zip bytes (``writestr`` stamps the time), so no case compares
whole-file shas across builds for equality.
"""
from __future__ import annotations

import hashlib
import re
import string
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pytest
from ebooklib import epub
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import epub_corpus as ec
from epub_zip import Doc, EpubSpec, Img, NavPoint, write_raw_epub
from reader3_app import book_format, reader3

OPF_DIR = "OEBPS"  # the EpubSpec.opf_path default, shared by every corpus builder

_HEX64 = re.compile(r"[0-9a-f]{64}")


def props(max_examples: int) -> Any:
    return settings(
        deadline=None,
        max_examples=max_examples,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
    )


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def zip_member_sha(epub_path: Path, href: str) -> str:
    """The ebooklib-independent oracle: the member's bytes straight out of the zip."""
    with zipfile.ZipFile(epub_path) as zf:
        return sha(zf.read(f"{OPF_DIR}/{href}"))


@dataclass(frozen=True)
class Processed:
    epub_path: Path
    ebook: epub.EpubBook
    book: Optional[reader3.Book]  # None when process_epub refuses the book
    refusal: Optional[str]
    out_dir: Path


BUILDERS: Dict[str, Callable[[Any], Path]] = {
    "build_epub2": ec.build_epub2,
    "build_epub3": ec.build_epub3,
    "build_cjk": ec.build_cjk,
    "build_diacritics": ec.build_diacritics,
    "build_illustrated": ec.build_illustrated,
    "build_malformed_toc": ec.build_malformed_toc,
    "build_spine_toc_maze": ec.build_spine_toc_maze,
    "build_empty_chapters": ec.build_empty_chapters,
    "build_no_documents": ec.build_no_documents,
    "build_bad_encoding": ec.build_bad_encoding,
}
NAMES = sorted(BUILDERS)


def _process(epub_path: Path, out_dir: Path) -> Processed:
    ebook = epub.read_epub(str(epub_path))
    try:
        book: Optional[reader3.Book] = reader3.process_epub(str(epub_path), str(out_dir))
        refusal = None
    except reader3.ArtifactValidationError as exc:
        book, refusal = None, str(exc)
    return Processed(epub_path, ebook, book, refusal, out_dir)


@pytest.fixture(scope="module")
def processed_corpus(tmp_path_factory: pytest.TempPathFactory) -> Dict[str, Processed]:
    """Every eligible corpus builder (``build_huge_epub`` excluded), built and processed once per module."""
    root = tmp_path_factory.mktemp("fp_corpus")
    out: Dict[str, Processed] = {}
    for name, build in BUILDERS.items():
        path = build(root / "epubs" / f"{name}.epub")
        out[name] = _process(path, root / "books" / f"{name}_data")
    return out


def _one_doc_spec(body: str, *, title: str = "Raw Test Book") -> EpubSpec:
    return EpubSpec(
        title=title,
        docs=(Doc("c1", "text/c1.xhtml", body),),
        nav=(NavPoint("One", "text/c1.xhtml"),),
    )


def _components(path: Path) -> reader3.FingerprintComponents:
    return reader3.fingerprint_components(path, epub.read_epub(str(path)))


def _fingerprint(path: Path) -> tuple[str, int]:
    return reader3.compute_fingerprint(path, epub.read_epub(str(path)))


# --------------------------------------------------------------------------- R3-01 / R3-02 corpus laws


@pytest.mark.parametrize("name", NAMES)
def test_r3_01_component_sha_equals_the_zip_member_sha(processed_corpus: Dict[str, Processed], name: str) -> None:
    p = processed_corpus[name]
    comps = reader3.fingerprint_components(p.epub_path, p.ebook)

    assert comps.epub_sha256 == sha(p.epub_path.read_bytes())
    if name != "build_no_documents":
        assert len(comps.spine) >= 1, "non-vacuity: every corpus book but build_no_documents has a document"
    for href, _order, item_sha in comps.spine:
        assert item_sha == zip_member_sha(p.epub_path, href), href


@pytest.mark.parametrize("name", [n for n in NAMES if n != "build_no_documents"])
def test_r3_02_href_order_lockstep_with_processed_chapters(
    processed_corpus: Dict[str, Processed], name: str
) -> None:
    p = processed_corpus[name]
    assert p.book is not None, p.refusal
    comps = reader3.fingerprint_components(p.epub_path, p.ebook)

    assert [(h, o) for h, o, _ in comps.spine] == [(c.href, c.order) for c in p.book.spine]


# --------------------------------------------------------------------------- R3-03 / R3-04 spine selection (R6)


def test_r3_03_maze_spine_selection_mirrors_the_chapter_loop(processed_corpus: Dict[str, Processed]) -> None:
    p = processed_corpus["build_spine_toc_maze"]
    comps = reader3.fingerprint_components(p.epub_path, p.ebook)
    hrefs = [h for h, _, _ in comps.spine]

    assert hrefs == ["text/chap1.xhtml", "text/chap2.xhtml", ec.MAZE_UNLISTED_FILE, ec.MAZE_NONLINEAR_FILE]
    assert [o for _, o, _ in comps.spine] == [0, 1, 2, 3]
    assert "text/aside.xhtml" not in hrefs  # in_spine=False: manifest only
    assert ec.MAZE_NONLINEAR_FILE in hrefs  # linear="no" is included, as the chapter loop includes it


def test_r3_04_spine_gap_keeps_the_spine_index_as_order(tmp_path: Path) -> None:
    """R6 / WI-3 flag: a spine idref with no manifest item is skipped and the orders keep their gap.

    WI-3 note: ``_validate_inputs`` requires ``ch.order == i``, so this book will not publish until WI-3 resolves it.
    """
    docs = tuple(Doc(f"c{n}", f"text/c{n}.xhtml", f"<p>{n}</p>") for n in (1, 2, 3))
    base = EpubSpec(docs=docs, nav=(NavPoint("One", "text/c1.xhtml"),))
    with zipfile.ZipFile(write_raw_epub(tmp_path / "base.epub", base)) as zf:
        opf = zf.read(f"{OPF_DIR}/content.opf").decode("utf-8")
    assert opf.count('idref="c2"') == 1
    gapped = EpubSpec(
        docs=docs,
        nav=base.nav,
        extra_files={f"{OPF_DIR}/content.opf": opf.replace('idref="c2"', 'idref="ghost"').encode("utf-8")},
    )
    path = write_raw_epub(tmp_path / "gap.epub", gapped)
    p = _process(path, tmp_path / "books" / "gap_data")
    assert p.book is not None, p.refusal
    comps = reader3.fingerprint_components(path, p.ebook)

    assert [o for _, o, _ in comps.spine] == [0, 2]
    assert [h for h, _, _ in comps.spine] == ["text/c1.xhtml", "text/c3.xhtml"]
    assert [o for _, o, _ in comps.spine] == [c.order for c in p.book.spine]


def test_r3_04b_non_document_spine_item_is_excluded_and_keeps_its_gap(tmp_path: Path) -> None:
    """R6: a spine idref that resolves to a non-document item (here an image) is skipped, its index kept.

    Metamorphic half: changing only that item's bytes leaves the spine components unchanged.
    """
    docs = tuple(Doc(f"c{n}", f"text/c{n}.xhtml", f"<p>{n}</p>") for n in (1, 3))

    def build(name: str, payload: bytes) -> Path:
        spec = EpubSpec(docs=docs, nav=(NavPoint("One", "text/c1.xhtml"),), images=(Img("pic", "pic.png", payload),))
        with zipfile.ZipFile(write_raw_epub(tmp_path / f"{name}-base.epub", spec)) as zf:
            opf = zf.read(f"{OPF_DIR}/content.opf").decode("utf-8")
        assert opf.count('<itemref idref="c3"') == 1
        opf = opf.replace('<itemref idref="c3"', '<itemref idref="pic"/>\n    <itemref idref="c3"', 1)
        extra = {f"{OPF_DIR}/content.opf": opf.encode("utf-8")}
        return write_raw_epub(tmp_path / f"{name}.epub", EpubSpec(docs=docs, nav=spec.nav, images=spec.images,
                                                                  extra_files=extra))

    a, b = build("a", b"\x89PNG-one"), build("b", b"\x89PNG-two")
    book_a = epub.read_epub(str(a))
    assert [idref for idref, _ in book_a.spine] == ["c1", "pic", "c3"]
    comps_a, comps_b = reader3.fingerprint_components(a, book_a), _components(b)

    assert comps_a.spine == (
        ("text/c1.xhtml", 0, zip_member_sha(a, "text/c1.xhtml")),
        ("text/c3.xhtml", 2, zip_member_sha(a, "text/c3.xhtml")),
    )
    assert comps_b.spine == comps_a.spine
    assert comps_b.epub_sha256 != comps_a.epub_sha256


# --------------------------------------------------------------------------- R3-05 .. R3-07, R3-10 digest behaviour


def test_r3_05_same_file_fingerprinted_twice_is_equal(tmp_path: Path) -> None:
    path = ec.build_epub3(tmp_path / "e3.epub")
    first, second = _fingerprint(path), _fingerprint(path)

    assert _HEX64.fullmatch(first[0])
    assert first == second


_TEXT = st.text(alphabet=string.ascii_letters + " ", min_size=1, max_size=40)


@props(15)
@given(texts=st.lists(_TEXT, min_size=1, max_size=4), data=st.data())
def test_r3_06_one_char_change_in_one_member_changes_only_that_item(texts: list[str], data: st.DataObject) -> None:
    k = data.draw(st.integers(0, len(texts) - 1), label="k")
    pos = data.draw(st.integers(0, len(texts[k]) - 1), label="pos")
    new = data.draw(st.sampled_from([c for c in string.ascii_letters if c != texts[k][pos]]), label="new")
    mutated = list(texts)
    mutated[k] = texts[k][:pos] + new + texts[k][pos + 1:]

    def spec(bodies: list[str]) -> EpubSpec:
        docs = tuple(Doc(f"c{i}", f"text/c{i}.xhtml", f"<p>{t}</p>") for i, t in enumerate(bodies))
        return EpubSpec(docs=docs, nav=(NavPoint("One", "text/c0.xhtml"),))

    with tempfile.TemporaryDirectory() as d:
        a = write_raw_epub(Path(d) / "a.epub", spec(texts))
        b = write_raw_epub(Path(d) / "b.epub", spec(mutated))
        comps_a, comps_b = _components(a), _components(b)
        (digest_a, _), (digest_b, _) = _fingerprint(a), _fingerprint(b)

    assert len(comps_a.spine) == len(comps_b.spine) == len(texts)
    for i in range(len(texts)):
        if i != k:
            assert comps_a.spine[i] == comps_b.spine[i]
    assert comps_a.spine[k][:2] == comps_b.spine[k][:2]
    assert comps_a.spine[k][2] != comps_b.spine[k][2]
    assert digest_a != digest_b


@pytest.mark.parametrize(
    "body_b",
    ['<p class="x">alpha beta</p>', "<p><b>alpha</b> beta</p>"],
    ids=["class-attr", "bold-wrap"],
)
def test_r3_07_html_only_change_with_identical_text_changes_the_fingerprint(tmp_path: Path, body_b: str) -> None:
    a = write_raw_epub(tmp_path / "a.epub", _one_doc_spec("<p>alpha beta</p>"))
    b = write_raw_epub(tmp_path / "b.epub", _one_doc_spec(body_b))
    pa = _process(a, tmp_path / "books" / "a_data")
    pb = _process(b, tmp_path / "books" / "b_data")
    assert pa.book is not None and pb.book is not None
    comps_a = reader3.fingerprint_components(a, pa.ebook)
    comps_b = reader3.fingerprint_components(b, pb.ebook)

    # The text oracle: the case is real only if the chapter text is identical.
    assert pa.book.spine[0].text == pb.book.spine[0].text
    assert len(comps_a.spine) == len(comps_b.spine) == 1
    assert comps_a.spine[0][2] != comps_b.spine[0][2]
    assert _fingerprint(a)[0] != _fingerprint(b)[0]


def test_r3_10_epub_sha_is_part_of_the_digest(tmp_path: Path) -> None:
    """R1 note: the digest input includes the whole-EPUB sha even though only the digest is stored."""
    a = write_raw_epub(tmp_path / "a.epub", _one_doc_spec("<p>same</p>", title="Title A"))
    b = write_raw_epub(tmp_path / "b.epub", _one_doc_spec("<p>same</p>", title="Title B"))
    comps_a, comps_b = _components(a), _components(b)

    assert comps_a.epub_sha256 != comps_b.epub_sha256, "precondition: the title change must alter the EPUB bytes"
    assert len(comps_a.spine) == 1
    assert comps_a.spine == comps_b.spine
    assert _fingerprint(a)[0] != _fingerprint(b)[0]


# --------------------------------------------------------------------------- R3-08 / R3-09 raw bytes


def test_r3_08_undecodable_bytes_still_hash(processed_corpus: Dict[str, Processed]) -> None:
    p = processed_corpus["build_bad_encoding"]
    comps = reader3.fingerprint_components(p.epub_path, p.ebook)

    assert list(comps.spine) == [("text/c1.xhtml", 0, sha(ec.BAD_ENCODING_BYTES))]


def test_r3_09_item_content_trap_guard(processed_corpus: Dict[str, Processed]) -> None:
    p = processed_corpus["build_epub2"]
    comps = reader3.fingerprint_components(p.epub_path, p.ebook)
    by_href = {h: s for h, _, s in comps.spine}
    assert "text/one.xhtml" in by_href

    assert by_href["text/one.xhtml"] == zip_member_sha(p.epub_path, "text/one.xhtml")
    reserialized = sha(p.ebook.get_item_with_href("text/one.xhtml").get_content())
    assert by_href["text/one.xhtml"] != reserialized, (
        "ebooklib no longer re-serializes EpubHtml; the trap is gone. Delete this inequality, keep the equality."
    )


# --------------------------------------------------------------------------- R3-11 .. R3-13


def test_r3_11_compute_fingerprint_composes_the_pure_function(processed_corpus: Dict[str, Processed]) -> None:
    p = processed_corpus["build_epub2"]
    assert type(reader3.EXTRACTOR_VERSION) is int
    assert reader3.EXTRACTOR_VERSION >= 1
    c = reader3.fingerprint_components(p.epub_path, p.ebook)

    expected = book_format.compute_book_fingerprint(c.epub_sha256, c.spine, reader3.EXTRACTOR_VERSION)
    assert reader3.compute_fingerprint(p.epub_path, p.ebook) == (expected, reader3.EXTRACTOR_VERSION)


def test_r3_12_empty_spine_book_is_fingerprintable(processed_corpus: Dict[str, Processed]) -> None:
    p = processed_corpus["build_no_documents"]
    comps = reader3.fingerprint_components(p.epub_path, p.ebook)
    digest, version = reader3.compute_fingerprint(p.epub_path, p.ebook)

    assert tuple(comps.spine) == ()
    assert _HEX64.fullmatch(digest)
    assert version == reader3.EXTRACTOR_VERSION
    # Lockstep: the chapter loop also yields no chapters, which process_epub currently refuses as an empty spine.
    assert p.book is None
    assert p.refusal is not None and "empty spine" in p.refusal


def test_r3_13_fingerprint_is_not_wired_into_process_epub(processed_corpus: Dict[str, Processed]) -> None:
    # WI-3 flips this assertion when it wires the fingerprint into publish -- with a rule-12 reason.
    p = processed_corpus["build_epub2"]
    assert p.book is not None
    assert book_format.classify(p.out_dir, full=False) == "missing"
