"""Each EPUB corpus entry proves the property it is named for.

A fixture that stops being what it claims does not fail -- it goes on being
used, and every case built on it passes for the wrong reason. So each builder
in ``epub_corpus`` is pinned here against the one thing it exists to provide:
the EPUB3 book really has no NCX, the "duplicate anchor" book really has three
TOC entries into one file, the colliding-image book really collides.

Three entries currently make production code fail. They are kept exactly as
they are, and the failure is pinned as the *current* behaviour with the reason
spelled out at the case:

    build_missing_toc_epub2   TypeError out of parse_toc_recursive
    build_no_documents        ArtifactValidationError, empty spine
    write_not_a_zip / write_truncated_epub / build_without_container
                              raw ebooklib / zipfile exceptions

None of these is what the code intends to do; weakening the fixture until they
pass would delete the only evidence that Phase 2 has something to fix.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Iterator, List

import ebooklib
import pytest
from ebooklib import epub

import epub_corpus as ec
from bookdir import staging_leftovers
from reader3_app.reader3 import ArtifactValidationError, TOCEntry, process_epub


def flatten(entries: List[TOCEntry], depth: int = 1) -> Iterator[tuple]:
    for e in entries:
        yield depth, e
        yield from flatten(e.children, depth + 1)


# --- 1 & 2: the two EPUB versions differ in where navigation lives ---------


def test_epub2_fixture_has_an_ncx_and_no_nav_document(tmp_path: Path, books_dir: Path):
    """L2 - the EPUB2 entry must not quietly acquire an EPUB3 nav document."""
    path = ec.build_epub2(tmp_path / "epub2.epub")
    names = ec.zip_names(path)

    assert "OEBPS/toc.ncx" in names
    assert "OEBPS/nav.xhtml" not in names
    assert epub.read_epub(str(path)).version == "2.0"

    book = process_epub(str(path), str(books_dir / "epub2_data"))
    assert book.metadata.title == ec.EPUB2_TITLE
    assert [t.file_href for t in book.toc] == ["text/one.xhtml", "text/two.xhtml"]


def test_epub3_fixture_has_a_nav_document_and_no_ncx(tmp_path: Path, books_dir: Path):
    """L2 - and the EPUB3 entry must not quietly fall back to an NCX.

    ebooklib prefers the NCX whenever one exists, so an EPUB3 fixture that also
    shipped a toc.ncx would exercise the EPUB2 code path under an EPUB3 name.
    """
    path = ec.build_epub3(tmp_path / "epub3.epub")
    names = ec.zip_names(path)

    assert "OEBPS/nav.xhtml" in names
    assert "OEBPS/toc.ncx" not in names
    assert epub.read_epub(str(path)).version == "3.0"

    book = process_epub(str(path), str(books_dir / "epub3_data"))
    assert book.metadata.title == ec.EPUB3_TITLE
    assert [t.file_href for t in book.toc] == ["text/one.xhtml", "text/two.xhtml"]


# --- 3: CJK ----------------------------------------------------------------


def test_cjk_fixture_keeps_every_sentence_and_a_substring_term(
    tmp_path: Path, books_dir: Path
):
    """L2 - CJK survives the pickle round trip, and the search term really is a substring."""
    path = ec.build_cjk(tmp_path / "cjk.epub")
    book = process_epub(str(path), str(books_dir / "cjk_data"))

    assert book.metadata.title == ec.CJK_TITLE
    assert book.metadata.language == "zh"
    assert [c.text for c in book.spine] == list(ec.CJK_SENTENCES)

    # The term is a substring of a word, never a whitespace-delimited token --
    # which is the whole reason CJK needs its own corpus entry.
    hits = [s for s in ec.CJK_SENTENCES if ec.CJK_SEARCH_TERM in s]
    assert len(hits) == 1
    assert f" {ec.CJK_SEARCH_TERM} " not in hits[0]


# --- 4: diacritics ---------------------------------------------------------


def test_diacritic_fixture_words_are_all_non_ascii_and_differ_from_their_ascii_form(
    tmp_path: Path, books_dir: Path
):
    """L2 - a pair whose two halves were equal would test nothing."""
    for word, ascii_form in ec.DIACRITIC_PAIRS:
        assert word != ascii_form
        assert not word.isascii()

    path = ec.build_diacritics(tmp_path / "diacritics.epub")
    book = process_epub(str(path), str(books_dir / "diacritics_data"))
    text = book.spine[0].text
    for word, _ in ec.DIACRITIC_PAIRS:
        assert word in text


# --- 5: illustrated --------------------------------------------------------


def test_illustrated_fixture_images_really_collide_on_their_sanitised_name(
    tmp_path: Path, books_dir: Path
):
    """L3 - two distinct images, one surviving file.

    Characterisation, not approval. ``_build_into_staging`` keys the on-disk
    name off ``os.path.basename``, so ``images/a/pic.png`` and
    ``images/b/pic.png`` are written to the same path and the second silently
    destroys the first -- and both <img> tags are then rewritten to point at
    the survivor. A book with per-chapter ``image1.png`` files loses all but
    one of them.
    """
    payloads = {img.name: img.payload for img in ec.COLLIDING_IMAGES}
    assert payloads["images/a/pic.png"] != payloads["images/b/pic.png"]

    path = ec.build_illustrated(tmp_path / "illustrated.epub")
    out = books_dir / "illustrated_data"
    book = process_epub(str(path), str(out))

    on_disk = sorted(p.name for p in (out / "images").iterdir())
    assert on_disk == ["pic.png", "space.png"]
    assert (out / "images" / "pic.png").read_bytes() == payloads["images/b/pic.png"]

    # Both source paths map to the one survivor, and so does the bare basename.
    assert book.images["images/a/pic.png"] == "images/pic.png"
    assert book.images["images/b/pic.png"] == "images/pic.png"
    # The URL-encoded src resolved, and the space was sanitised out of the name.
    assert book.images["images/sp ace.png"] == "images/space.png"
    assert book.spine[0].content.count('src="images/pic.png"') == 2
    assert 'src="images/space.png"' in book.spine[0].content


# --- 6: malformed / missing TOC -------------------------------------------


def test_epub2_with_an_empty_navmap_currently_crashes_process_epub(
    tmp_path: Path, books_dir: Path
):
    """L4 - pinned bug, not a passing case.

    ebooklib's ``_parse_ncx`` returns a bare ``Link`` (not a list) when the
    navMap has no children, and ``parse_toc_recursive`` iterates whatever it is
    handed. So ``get_fallback_toc`` -- the entire "TOC is missing" recovery
    path -- is unreachable for EPUB 2, which is the version that most often
    ships an empty navMap.
    """
    path = ec.build_missing_toc_epub2(tmp_path / "notoc2.epub")
    out = books_dir / "notoc2_data"

    with pytest.raises(TypeError, match="'Link' object is not iterable"):
        process_epub(str(path), str(out))

    assert staging_leftovers(out) == []


def test_epub3_with_an_empty_nav_list_does_reach_the_fallback_toc(
    tmp_path: Path, books_dir: Path, capsys
):
    """L2 - the sibling case, and the contrast that makes the bug above legible."""
    path = ec.build_missing_toc_epub3(tmp_path / "notoc3.epub")
    book = process_epub(str(path), str(books_dir / "notoc3_data"))

    assert "Warning: Empty TOC" in capsys.readouterr().out
    assert [c.href for c in book.spine] == ["text/c1.xhtml"]
    # The fallback enumerates ITEM_DOCUMENTs, which includes the nav document
    # itself -- so the reader offers a "Nav" chapter that is not in the spine.
    assert [t.file_href for t in book.toc] == ["nav.xhtml", "text/c1.xhtml"]


def test_malformed_toc_fixture_carries_all_three_kinds_of_lie(
    tmp_path: Path, books_dir: Path
):
    """L2 - dangling href, out-of-spine href, and no href at all."""
    path = ec.build_malformed_toc(tmp_path / "badtoc.epub")
    book = process_epub(str(path), str(books_dir / "badtoc_data"))

    spine_hrefs = {c.href for c in book.spine}
    toc_hrefs = [t.file_href for t in book.toc]

    assert ec.DANGLING_HREF in toc_hrefs
    assert ec.DANGLING_HREF not in spine_hrefs
    assert ec.DANGLING_HREF not in ec.zip_names(path)

    assert "text/aside.xhtml" in toc_hrefs
    assert "text/aside.xhtml" not in spine_hrefs
    assert "OEBPS/text/aside.xhtml" in ec.zip_names(path)

    # A navPoint with no <content src> survives as an entry with an empty href,
    # so it is indistinguishable from a section heading downstream.
    headless = [t for t in book.toc if t.title == "Headless"]
    assert len(headless) == 1
    assert headless[0].href == ""


# --- 7: the two kinds of empty book ---------------------------------------


def test_book_with_no_documents_is_refused_before_anything_is_published(
    tmp_path: Path, books_dir: Path
):
    """L4 - validation catches the empty spine and nothing lands on disk."""
    path = ec.build_no_documents(tmp_path / "nodocs.epub")
    out = books_dir / "nodocs_data"

    with pytest.raises(ArtifactValidationError, match="empty spine"):
        process_epub(str(path), str(out))

    assert not out.exists()
    assert staging_leftovers(out) == []


def test_book_with_empty_chapters_publishes_spine_entries_holding_empty_text(
    tmp_path: Path, books_dir: Path
):
    """L2 - kept separate from the case above: this one succeeds, and must."""
    path = ec.build_empty_chapters(tmp_path / "blank.epub")
    out = books_dir / "blank_data"
    book = process_epub(str(path), str(out))

    assert len(book.spine) == 2
    assert [c.text for c in book.spine] == ["", ""]
    assert (out / "book.pkl").is_file()


# --- 8: group 1, spine / TOC structure ------------------------------------


def test_maze_has_three_toc_entries_into_one_spine_file_at_three_anchors(
    tmp_path: Path, books_dir: Path
):
    """L2 - the "many TOC entries, one file" property, stated as anchors."""
    path = ec.build_spine_toc_maze(tmp_path / "maze.epub")
    book = process_epub(str(path), str(books_dir / "maze_data"))

    into_shared = [e for _, e in flatten(book.toc) if e.file_href == ec.MAZE_SHARED_FILE]
    assert [e.anchor for e in into_shared] == list(ec.MAZE_ANCHORS)
    assert len({e.href for e in into_shared}) == 3

    # One spine entry, three ways in.
    assert [c.href for c in book.spine].count(ec.MAZE_SHARED_FILE) == 1


def test_maze_nests_three_levels_deep(tmp_path: Path, books_dir: Path):
    """L2 - a flattened TOC would still satisfy the anchor test above."""
    path = ec.build_spine_toc_maze(tmp_path / "maze.epub")
    book = process_epub(str(path), str(books_dir / "maze_data"))

    assert max(depth for depth, _ in flatten(book.toc)) == 3
    titles_by_depth = {depth: e.title for depth, e in flatten(book.toc)}
    assert titles_by_depth[3] == "Subsection A1"


def test_maze_has_a_spine_chapter_no_toc_entry_mentions(tmp_path: Path, books_dir: Path):
    """L2 - the chapter a TOC-driven reader would drop."""
    path = ec.build_spine_toc_maze(tmp_path / "maze.epub")
    book = process_epub(str(path), str(books_dir / "maze_data"))

    toc_files = {e.file_href for _, e in flatten(book.toc)}
    spine_files = [c.href for c in book.spine]

    assert ec.MAZE_UNLISTED_FILE in spine_files
    assert ec.MAZE_UNLISTED_FILE not in toc_files


def test_maze_keeps_the_non_linear_spine_item_as_an_ordinary_chapter(
    tmp_path: Path, books_dir: Path
):
    """L2 - characterisation: ``linear="no"`` is parsed and then discarded.

    ``process_epub`` unpacks ``item_id, linear = spine_item`` and never reads
    ``linear`` again, so backmatter the publisher excluded from linear reading
    order becomes a Next-button destination like any other chapter. Recorded
    here so Phase 2 changing it is a visible decision.
    """
    path = ec.build_spine_toc_maze(tmp_path / "maze.epub")
    raw = epub.read_epub(str(path))
    assert ("c4", "no") in raw.spine

    book = process_epub(str(path), str(books_dir / "maze_data"))
    non_linear = [c for c in book.spine if c.href == ec.MAZE_NONLINEAR_FILE]
    assert len(non_linear) == 1
    assert non_linear[0].order == 3


# --- 9: group 4, scale and failure ----------------------------------------


def test_huge_chapter_text_is_generated_at_the_requested_size_and_not_committed(
    repo_root: Path,
):
    """L2 - three million characters, produced on demand, absent from the repo."""
    text = ec.huge_chapter_text(ec.HUGE_CHAPTER_CHARS, needle="SENTINEL")
    assert len(text) == ec.HUGE_CHAPTER_CHARS + len("SENTINEL")
    assert text.endswith("SENTINEL")
    # Placed last so a search over it cannot exit early.
    assert text.index("SENTINEL") == ec.HUGE_CHAPTER_CHARS

    streamed = "".join(ec.iter_huge_chapter_text(50_000))
    assert streamed == ec.huge_chapter_text(50_000)

    # The corpus ships the generator, never the bytes.
    fixtures = repo_root / "tests" / "fixtures"
    assert not any(p.suffix == ".epub" for p in fixtures.rglob("*"))
    assert max(p.stat().st_size for p in fixtures.glob("*.py")) < 100_000


def test_build_huge_epub_actually_produces_a_readable_book_of_that_size(tmp_path: Path):
    """上一条只验了字符串助手，`build_huge_epub` 自己一次都没被调用过。

    它是 §6 那条「三百万字符」基准的**唯一**输入源。而 `scripts/bench.py:580` 是
    它唯一的调用点，bench 不在任何 lane 里——所以在这条用例之前，把它改成产出
    一章空文本、或者产出一个根本打不开的 zip，整个测试套件不会有一个字变红，
    而基准会安静地开始测量一本空书，把「快了 40 倍」当成好消息报上来。

    这里用一个**小**尺寸：要守的是「产出物是本能读的书，且尺寸随参数走」，
    不是重跑一遍三百万字符的分配。
    """
    chars = 20_000
    out = ec.build_huge_epub(tmp_path / "huge.epub", chars=chars, needle="NEEDLE-Z")

    assert out.is_file() and zipfile.is_zipfile(out), "产出物不是个可打开的 epub"

    book = epub.read_epub(str(out))
    docs = [d for d in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)]
    bodies = "".join(d.get_content().decode("utf-8", "replace") for d in docs)

    assert "NEEDLE-Z" in bodies, "needle 没进正文——搜索基准会提前命中空气"
    # 尺寸随参数走：断一个区间而不是等值，因为正文外还包着 XHTML 骨架。
    assert chars <= len(bodies) < chars * 2, (
        f"正文长度 {len(bodies)} 与请求的 {chars} 不成比例——"
        "基准测的就不再是它自称在测的那条路径了"
    )

    doubled = ec.build_huge_epub(tmp_path / "huge2.epub", chars=chars * 2, needle="NEEDLE-Z")
    doubled_bodies = "".join(
        d.get_content().decode("utf-8", "replace")
        for d in epub.read_epub(str(doubled)).get_items_of_type(ebooklib.ITEM_DOCUMENT)
    )
    assert len(doubled_bodies) > len(bodies) * 1.5, (
        "chars 翻倍没让正文明显变长——一个忽略 chars 的实现会让整条 scale 基准失去意义"
    )


@pytest.mark.parametrize(
    "make, expected",
    [
        pytest.param(
            lambda tmp: ec.write_not_a_zip(tmp / "broken.epub"),
            epub.EpubException,
            id="not-a-zip",
        ),
        pytest.param(
            lambda tmp: ec.write_truncated_epub(
                tmp / "trunc.epub", source=ec.build_epub2(tmp / "full.epub")
            ),
            epub.EpubException,
            id="truncated",
        ),
        pytest.param(
            lambda tmp: ec.build_without_container(tmp / "nocontainer.epub"),
            KeyError,
            id="no-container-xml",
        ),
    ],
)
def test_damaged_archives_fail_before_the_output_directory_is_touched(
    make, expected, tmp_path: Path, books_dir: Path
):
    """L4 - pinned behaviour: three damaged archives, three unrelated exception types.

    ``EpubException`` for a bad zip, a bare ``KeyError`` for a missing
    ``container.xml``. Nothing in ``process_epub`` narrows either, so a caller
    cannot tell "this file is not an EPUB" from a programming error. The
    invariant that does hold, and that this asserts, is that the failure
    happens before any directory is created.
    """
    path = make(tmp_path)
    out = books_dir / "damaged_data"

    with pytest.raises(expected):
        process_epub(str(path), str(out))

    assert not out.exists()
    assert staging_leftovers(out) == []


def test_bad_encoding_is_silently_replaced_rather_than_reported(
    tmp_path: Path, books_dir: Path
):
    """L2 - pinned behaviour: undecodable bytes become U+FFFD inside a real word.

    Two things conspire. ``EpubHtml.get_content()`` re-serialises the document
    through lxml, which substitutes U+FFFD for bytes it cannot decode -- so
    ``reader3.py``'s ``decode('utf-8', errors='ignore')`` never sees the raw
    bytes and its error policy is dead code. The result is a chapter whose text
    reads ``caf�``: the book indexes, renders, and is unsearchable for the
    word it contains.
    """
    path = ec.build_bad_encoding(tmp_path / "badenc.epub")
    book = process_epub(str(path), str(books_dir / "badenc_data"))

    text = book.spine[0].text
    assert "�" in text
    assert text.startswith("caf�")
    assert "café" not in text


def test_every_corpus_archive_is_a_zip_whose_first_member_is_the_mimetype(
    tmp_path: Path,
):
    """L2 - the raw writer must still produce EPUBs, not merely zips.

    ``mimetype`` first and stored is the one structural rule an EPUB reader may
    check before parsing anything; a builder that lost it would be producing a
    different kind of malformed input than the one each case claims.
    """
    builders = (
        ec.build_epub2,
        ec.build_epub3,
        ec.build_cjk,
        ec.build_diacritics,
        ec.build_illustrated,
        ec.build_missing_toc_epub2,
        ec.build_missing_toc_epub3,
        ec.build_malformed_toc,
        ec.build_no_documents,
        ec.build_empty_chapters,
        ec.build_spine_toc_maze,
        ec.build_bad_encoding,
    )
    for i, build in enumerate(builders):
        path = build(tmp_path / f"corpus{i}.epub")
        with zipfile.ZipFile(path) as zf:
            first = zf.infolist()[0]
            assert first.filename == "mimetype"
            assert first.compress_type == zipfile.ZIP_STORED
            assert zf.read("mimetype") == b"application/epub+zip"

    # The container-less entry is the deliberate exception, and only there.
    nocontainer = ec.build_without_container(tmp_path / "nc.epub")
    assert "META-INF/container.xml" not in ec.zip_names(nocontainer)


def test_the_corpus_covers_every_item_type_the_pipeline_branches_on(
    tmp_path: Path,
):
    """L2 - illustrated books really carry ITEM_IMAGE, empty ones really do not."""
    illustrated = epub.read_epub(str(ec.build_illustrated(tmp_path / "i.epub")))
    empty = epub.read_epub(str(ec.build_no_documents(tmp_path / "e.epub")))

    assert len([i for i in illustrated.get_items() if i.get_type() == ebooklib.ITEM_IMAGE]) == 3
    assert [i for i in empty.get_items() if i.get_type() == ebooklib.ITEM_DOCUMENT] == []
