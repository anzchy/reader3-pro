"""The eleven-group EPUB corpus (tasks/008-test-safety-net.md §3).

Seven original classes -- EPUB2, EPUB3, CJK, diacritics, illustrated, malformed
or missing TOC, empty book -- plus four groups named by the engineering review:
spine/TOC structure, Unicode, annotation anchoring, and scale/failure. Unicode
lives in ``unicode_corpus`` and annotation anchoring in ``annotation_corpus``,
because those two are *text* corpora that several layers consume; only the ones
that have to be a real EPUB on disk are here.

Every builder returns the path it wrote. The property each one claims is
asserted in ``tests/unit/test_fixture_epub_corpus.py`` and nowhere else -- a
corpus entry whose distinguishing feature quietly disappears (an EPUB3 fixture
that degrades to EPUB2, a "duplicate anchor" book whose anchors are no longer
duplicated) would leave every downstream case green while testing nothing.

Two builders here produce input that current production code cannot process at
all. They are kept, and the failure is pinned as the *current* behaviour --
see the module docstring of the test file for which ones and why.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Iterator, Tuple, Union

from epub_zip import Doc, EpubSpec, Img, NavPoint, write_raw_epub

PathLike = Union[str, "os.PathLike[str]"]

PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def _png(tag: bytes) -> bytes:
    return PNG_HEADER + tag * 4


# --- 1. EPUB 2: NCX only, no nav document ---------------------------------

EPUB2_TITLE = "Nineteen Twenty Two"


def build_epub2(path: PathLike) -> Path:
    """EPUB 2.0.1: navigation lives in ``toc.ncx``, there is no nav document."""
    return write_raw_epub(
        path,
        EpubSpec(
            title=EPUB2_TITLE,
            version="2.0",
            identifier="urn:uuid:reader3-epub2",
            docs=(
                Doc("c1", "text/one.xhtml", "<h1>One</h1><p>Alpha prose.</p>"),
                Doc("c2", "text/two.xhtml", "<h1>Two</h1><p>Beta prose.</p>"),
            ),
            nav=(
                NavPoint("One", "text/one.xhtml"),
                NavPoint("Two", "text/two.xhtml"),
            ),
        ),
    )


# --- 2. EPUB 3: nav document only, no NCX ---------------------------------

EPUB3_TITLE = "Three Point Oh"


def build_epub3(path: PathLike) -> Path:
    """EPUB 3.0: navigation lives in ``nav.xhtml``; the legacy NCX is absent.

    ``epub_builder.build_epub`` cannot express this -- ebooklib's writer always
    emits both -- so the "EPUB3-only" half of the corpus has to be raw.
    """
    return write_raw_epub(
        path,
        EpubSpec(
            title=EPUB3_TITLE,
            version="3.0",
            identifier="urn:uuid:reader3-epub3",
            docs=(
                Doc("c1", "text/one.xhtml", "<h1>One</h1><p>Alpha prose.</p>"),
                Doc("c2", "text/two.xhtml", "<h1>Two</h1><p>Beta prose.</p>"),
            ),
            nav=(
                NavPoint("One", "text/one.xhtml"),
                NavPoint("Two", "text/two.xhtml"),
            ),
        ),
    )


# --- 3. CJK ----------------------------------------------------------------

CJK_TITLE = "咖啡館の夜"
CJK_SENTENCES: Tuple[str, ...] = (
    "他在咖啡館裡等了很久。",
    "彼女は喫茶店で本を読んでいた。",
    "커피를 마시며 기다렸다.",
)
#: A CJK term that is a *substring* of a longer word, which is what makes
#: whitespace-free languages behave differently from Latin ones under search.
CJK_SEARCH_TERM = "咖啡"


def build_cjk(path: PathLike) -> Path:
    return write_raw_epub(
        path,
        EpubSpec(
            title=CJK_TITLE,
            language="zh",
            authors=("測試 作者",),
            identifier="urn:uuid:reader3-cjk",
            docs=tuple(
                Doc(f"c{i}", f"text/c{i}.xhtml", f"<p>{s}</p>", lang="zh")
                for i, s in enumerate(CJK_SENTENCES, start=1)
            ),
            nav=tuple(
                NavPoint(f"第{i}章", f"text/c{i}.xhtml")
                for i in range(1, len(CJK_SENTENCES) + 1)
            ),
        ),
    )


# --- 4. Diacritics ---------------------------------------------------------

#: Each pair is (as it appears in the book, the ASCII spelling a reader types).
#: `Straße` is here rather than in the Unicode group because it is the one
#: diacritic-adjacent case where casefold *lengthens* the string, which is what
#: makes `_normalize_with_map`'s index map non-trivial.
DIACRITIC_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("café", "cafe"),
    ("naïve", "naive"),
    ("Ångström", "Angstrom"),
    ("Łódź", "Łodz"),
    ("Straße", "Strasse"),
)


def build_diacritics(path: PathLike) -> Path:
    body = "".join(f"<p>The word {word} appears here.</p>" for word, _ in DIACRITIC_PAIRS)
    return write_raw_epub(
        path,
        EpubSpec(
            title="Diacritics",
            identifier="urn:uuid:reader3-diacritics",
            docs=(Doc("c1", "text/c1.xhtml", body),),
            nav=(NavPoint("Words", "text/c1.xhtml"),),
        ),
    )


# --- 5. Illustrated, with the path shapes that actually collide ------------

#: Two distinct images that share a basename but sit in different directories,
#: one whose name needs sanitising, and one referenced through a URL-encoded
#: relative src. Every one of these is a real EPUB idiom.
COLLIDING_IMAGES = (
    Img("i1", "images/a/pic.png", _png(b"AAA")),
    Img("i2", "images/b/pic.png", _png(b"BBB")),
    Img("i3", "images/sp ace.png", _png(b"CCC")),
)


def build_illustrated(path: PathLike) -> Path:
    body = (
        "<p>Plate one:</p><img src='../images/a/pic.png' alt='a'/>"
        "<p>Plate two:</p><img src='../images/b/pic.png' alt='b'/>"
        "<p>Plate three:</p><img src='../images/sp%20ace.png' alt='c'/>"
        "<p>Illustrated body text.</p>"
    )
    return write_raw_epub(
        path,
        EpubSpec(
            title="Illustrated",
            identifier="urn:uuid:reader3-illustrated",
            docs=(Doc("c1", "text/c1.xhtml", body),),
            nav=(NavPoint("Plates", "text/c1.xhtml"),),
            images=COLLIDING_IMAGES,
        ),
    )


# --- 6. Malformed / missing TOC -------------------------------------------


def build_missing_toc_epub2(path: PathLike) -> Path:
    """EPUB 2 whose ``navMap`` is empty: the case ``get_fallback_toc`` is for."""
    return write_raw_epub(
        path,
        EpubSpec(
            title="No Contents (EPUB2)",
            version="2.0",
            identifier="urn:uuid:reader3-notoc2",
            docs=(Doc("c1", "text/c1.xhtml", "<p>Only prose.</p>"),),
            nav=(),
        ),
    )


def build_missing_toc_epub3(path: PathLike) -> Path:
    """EPUB 3 whose nav ``<ol>`` is empty. Same intent, different container."""
    return write_raw_epub(
        path,
        EpubSpec(
            title="No Contents (EPUB3)",
            version="3.0",
            identifier="urn:uuid:reader3-notoc3",
            docs=(Doc("c1", "text/c1.xhtml", "<p>Only prose.</p>"),),
            nav=(),
        ),
    )


#: The href a malformed TOC points at that no manifest item provides.
DANGLING_HREF = "text/nope.xhtml"


def build_malformed_toc(path: PathLike) -> Path:
    """A TOC that lies in three different ways at once.

    An entry pointing at a file that is not in the archive, an entry pointing at
    a manifest item that is not in the spine, and an entry with no ``src`` at
    all -- so a consumer that maps TOC to spine by index, rather than by href,
    silently mis-navigates instead of failing.
    """
    return write_raw_epub(
        path,
        EpubSpec(
            title="Lying Contents",
            identifier="urn:uuid:reader3-badtoc",
            docs=(
                Doc("c1", "text/c1.xhtml", "<p>Real chapter.</p>"),
                Doc("c2", "text/aside.xhtml", "<p>Manifest only.</p>", in_spine=False),
            ),
            nav=(
                NavPoint("Real", "text/c1.xhtml"),
                NavPoint("Gone", DANGLING_HREF),
                NavPoint("Aside", "text/aside.xhtml"),
                NavPoint("Headless", None),
            ),
        ),
    )


# --- 7. Empty books, kept as two distinct fixtures -------------------------
#
# "A book with no documents" and "a book whose documents are empty" fail in
# different places -- the first never produces a spine entry at all, the second
# produces spine entries whose text is "". Merged into one fixture, whichever
# failure came first would hide the other.


def build_no_documents(path: PathLike) -> Path:
    """A well-formed archive with an empty spine: no ITEM_DOCUMENT anywhere."""
    return write_raw_epub(
        path,
        EpubSpec(
            title="Nothing At All",
            identifier="urn:uuid:reader3-nodocs",
            docs=(),
            nav=(NavPoint("Ghost", DANGLING_HREF),),
        ),
    )


def build_empty_chapters(path: PathLike) -> Path:
    """Spine entries exist; every one of them has an empty body."""
    return write_raw_epub(
        path,
        EpubSpec(
            title="Blank Pages",
            identifier="urn:uuid:reader3-blank",
            docs=(
                Doc("c1", "text/c1.xhtml", ""),
                Doc("c2", "text/c2.xhtml", "   "),
            ),
            nav=(NavPoint("Blank", "text/c1.xhtml"),),
        ),
    )


# --- 8. Group 1: spine / TOC structure ------------------------------------

#: The single spine file that three TOC entries point into, with three
#: different fragments. Anchors are the reason a TOC entry is not a chapter.
MAZE_SHARED_FILE = "text/chap1.xhtml"
MAZE_ANCHORS: Tuple[str, ...] = ("", "sec-a", "sec-b")
#: In the spine, absent from the TOC. A consumer that renders "the TOC" as the
#: reading order drops this chapter entirely.
MAZE_UNLISTED_FILE = "text/chap3.xhtml"
#: ``linear="no"``: in the spine, but not part of linear reading order.
MAZE_NONLINEAR_FILE = "text/back.xhtml"


def build_spine_toc_maze(path: PathLike) -> Path:
    """Every spine/TOC divergence the review named, in one book.

    Three TOC entries into one file at different fragments; a spine chapter no
    TOC entry mentions; a TOC entry for a manifest-only file; a dangling TOC
    entry; a three-level nest; and a ``linear="no"`` spine item.
    """
    return write_raw_epub(
        path,
        EpubSpec(
            title="The Maze",
            identifier="urn:uuid:reader3-maze",
            docs=(
                Doc(
                    "c1",
                    MAZE_SHARED_FILE,
                    "<h1>One</h1><p id='sec-a'>Alpha.</p><p id='sec-b'>Beta.</p>",
                ),
                Doc("c2", "text/chap2.xhtml", "<p>Gamma.</p>"),
                Doc("c3", MAZE_UNLISTED_FILE, "<p>Delta, unlisted.</p>"),
                Doc("c4", MAZE_NONLINEAR_FILE, "<p>Backmatter.</p>", linear=False),
                Doc("c5", "text/aside.xhtml", "<p>Manifest only.</p>", in_spine=False),
            ),
            nav=(
                NavPoint(
                    "Part I",
                    MAZE_SHARED_FILE,
                    (
                        NavPoint(
                            "Section A",
                            f"{MAZE_SHARED_FILE}#sec-a",
                            (NavPoint("Subsection A1", f"{MAZE_SHARED_FILE}#sec-b"),),
                        ),
                        NavPoint("Section B", "text/chap2.xhtml"),
                    ),
                ),
                NavPoint("Dangling", DANGLING_HREF),
                NavPoint("Aside", "text/aside.xhtml"),
            ),
        ),
    )


# --- 9. Group 4: scale and failure ----------------------------------------

#: §6 wants a chapter around three million characters. It is *generated*, never
#: committed: a three-megabyte blob in git would be paid for on every clone, by
#: everyone, forever, to serve one benchmark.
HUGE_CHAPTER_CHARS = 3_000_000

_HUGE_SENTENCE = (
    "The lamp guttered and the shadow of the mast swung across the deck once more. "
)


def huge_chapter_text(chars: int = HUGE_CHAPTER_CHARS, *, needle: str = "") -> str:
    """Roughly ``chars`` characters of prose, optionally with ``needle`` at the end.

    Deterministic and cheap: one sentence repeated, so the cost is the
    allocation rather than the generation. Placing ``needle`` last is what makes
    a search over this text measure the full scan and not an early exit.
    """
    body = _HUGE_SENTENCE * (chars // len(_HUGE_SENTENCE) + 1)
    body = body[:chars]
    return body + needle if needle else body


def iter_huge_chapter_text(
    chars: int = HUGE_CHAPTER_CHARS, *, block: int = 1 << 16
) -> Iterator[str]:
    """The same prose in bounded blocks, for writing without materialising it."""
    written = 0
    chunk = _HUGE_SENTENCE * (block // len(_HUGE_SENTENCE) + 1)
    while written < chars:
        take = min(block, chars - written)
        yield chunk[:take]
        written += take


def build_huge_epub(
    path: PathLike, *, chars: int = HUGE_CHAPTER_CHARS, needle: str = "SENTINEL"
) -> Path:
    """One book, one chapter, ``chars`` characters. Written, then deleted by the test."""
    return write_raw_epub(
        path,
        EpubSpec(
            title="The Long One",
            identifier="urn:uuid:reader3-huge",
            docs=(Doc("c1", "text/c1.xhtml", f"<p>{huge_chapter_text(chars, needle=needle)}</p>"),),
            nav=(NavPoint("The Long One", "text/c1.xhtml"),),
        ),
    )


def write_not_a_zip(path: PathLike) -> Path:
    """A file with an ``.epub`` name and no zip structure at all."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"%PDF-1.4\nthis was never an epub\n")
    return out


def write_truncated_epub(path: PathLike, *, source: PathLike) -> Path:
    """The first half of a real EPUB: valid prefix, no central directory."""
    data = Path(source).read_bytes()
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data[: len(data) // 2])
    return out


def build_without_container(path: PathLike) -> Path:
    """A valid zip holding a valid OPF, with ``META-INF/container.xml`` removed."""
    return write_raw_epub(
        path,
        EpubSpec(
            title="No Container",
            identifier="urn:uuid:reader3-nocontainer",
            docs=(Doc("c1", "text/c1.xhtml", "<p>Unreachable prose.</p>"),),
            nav=(NavPoint("One", "text/c1.xhtml"),),
            omit_container=True,
        ),
    )


#: Latin-1 bytes in a document declared UTF-8, plus two bytes that are not
#: valid in any single-byte-to-UTF-8 reading. `café` is spelled with a bare
#: 0xE9 so the corruption lands inside a word a reader would search for.
BAD_ENCODING_BYTES = (
    b"<html><body><p>caf\xe9 in the rue de l'\xc9glise \xff\xfe</p></body></html>"
)


def build_bad_encoding(path: PathLike) -> Path:
    return write_raw_epub(
        path,
        EpubSpec(
            title="Mojibake",
            identifier="urn:uuid:reader3-badenc",
            docs=(Doc("c1", "text/c1.xhtml", "", raw_bytes=BAD_ENCODING_BYTES),),
            nav=(NavPoint("One", "text/c1.xhtml"),),
        ),
    )


def zip_names(path: PathLike) -> Tuple[str, ...]:
    with zipfile.ZipFile(path) as zf:
        return tuple(zf.namelist())
