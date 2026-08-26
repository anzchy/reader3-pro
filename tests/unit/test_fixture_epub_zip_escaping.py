"""The raw EPUB writer must produce well-formed XML for hostile-but-legal text.

``epub_zip`` exists to build EPUBs that ebooklib's writer refuses to build:
dangling TOC hrefs, ``linear="no"`` spine items, a missing ``container.xml``.
That freedom is about *structure*. It is not a licence to emit broken *syntax*.

The difference matters because of how the failure presents. A corpus entry whose
title contains ``&`` produced an OPF that no XML parser accepts, so the case
named "the reader keeps CJK titles intact" silently became "the reader survives
a malformed OPF" -- still green, testing something else entirely. Nothing in the
suite would have said so.

So each interpolation point named in the finding is pinned here against one
string, ``A & B <c> "d"``, that is illegal raw in element text (``&``, ``<``)
and illegal raw in an attribute value (``&``, ``<``, ``"``):

    EpubSpec.title       -> OPF <dc:title>, NCX <docTitle><text>
    EpubSpec.authors     -> OPF <dc:creator>
    EpubSpec.identifier  -> OPF <dc:identifier>, NCX <meta content=...>
    Doc.title            -> XHTML <head><title>
    Doc.lang             -> XHTML xml:lang= and lang=
    NavPoint.title       -> NCX <navLabel><text>, nav document <a>/<span>
    NavPoint.href        -> NCX <content src=...>, nav document <a href=...>

Round-tripping, not byte-matching, is the assertion. Asserting the bytes
contain ``&amp;`` would pass just as well for a writer that double-escaped, or
that escaped the OPF and forgot the NCX. Parsing the member back and comparing
the recovered string *verbatim* to the input is the property the corpus needs.

``Doc.body`` and ``Doc.raw_bytes`` are deliberately excluded: they are the
documented escape hatch for "write these bytes verbatim", and escaping them
would delete the malformed-document corpus entries.
"""

from __future__ import annotations

import dataclasses
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

from epub_zip import Doc, EpubSpec, NavPoint, write_raw_epub

#: The exact string the work item names. Every other hostile string below is
#: this one plus a tag, so a test failure says *which* interpolation point lost.
NASTY = 'A & B <c> "d"'


def nasty(tag: str) -> str:
    return f"{NASTY} {tag}"


AUTHOR_1 = nasty("author-one")
AUTHOR_2 = nasty("author-two")
IDENTIFIER = nasty("identifier")
DOC_1_TITLE = nasty("doc-title-one")
DOC_2_TITLE = nasty("doc-title-two")
DOC_LANG = nasty("lang")
NAV_TOP_TITLE = nasty("nav-top")
NAV_CHILD_TITLE = nasty("nav-child")
NAV_NOHREF_TITLE = nasty("nav-no-href")

#: Shaped like a real href with a query string, which is how ``&`` reaches a
#: TOC entry in the wild. Both dangle on purpose -- ``NavPoint.href`` is
#: documented as allowed to point at nothing, so this stays a pure encoding
#: test rather than also asserting manifest consistency.
NAV_TOP_HREF = 'text/one.xhtml?a=1&b=2#sec "d" <c>'
NAV_CHILD_HREF = 'text/two.xhtml?x=A&y=B#<c>"d"'

XHTML_NS = "http://www.w3.org/1999/xhtml"
DC_NS = "http://purl.org/dc/elements/1.1/"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"
XML_NS = "http://www.w3.org/XML/1998/namespace"

OPF_PATH = "OEBPS/content.opf"


@pytest.fixture(autouse=True)
def _cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every path in this module is under tmp_path; never resolve against the repo."""
    monkeypatch.chdir(tmp_path)


def hostile_spec() -> EpubSpec:
    """One EPUB 2 spec carrying the hostile string at every point in the list."""
    return EpubSpec(
        title=NASTY,
        authors=(AUTHOR_1, AUTHOR_2),
        identifier=IDENTIFIER,
        version="2.0",
        opf_path=OPF_PATH,
        docs=(
            Doc("c1", "text/one.xhtml", "<p>Alpha.</p>", title=DOC_1_TITLE, lang=DOC_LANG),
            Doc("c2", "text/two.xhtml", "<p>Beta.</p>", title=DOC_2_TITLE, lang=DOC_LANG),
        ),
        nav=(
            NavPoint(
                NAV_TOP_TITLE,
                NAV_TOP_HREF,
                (NavPoint(NAV_CHILD_TITLE, NAV_CHILD_HREF),),
            ),
            NavPoint(NAV_NOHREF_TITLE, None),
        ),
    )


def member(path: Path, name: str) -> bytes:
    with zipfile.ZipFile(path) as zf:
        return zf.read(name)


def parse(label: str, data: bytes) -> ET.Element:
    """Parse, turning a syntax error into an assertion failure that shows the bytes."""
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:  # pragma: no cover - only on the mutation
        raise AssertionError(
            f"{label} is not well-formed XML: {exc}\n"
            f"----- {label} -----\n{data.decode('utf-8', 'replace')}"
        ) from exc


def test_z1_opf_parses_and_round_trips_every_metadata_string(tmp_path: Path) -> None:
    """L3 - title, authors and identifier survive the OPF verbatim."""
    path = write_raw_epub(tmp_path / "hostile2.epub", hostile_spec())
    root = parse("OPF", member(path, OPF_PATH))

    metadata = root.find("{http://www.idpf.org/2007/opf}metadata")
    assert metadata is not None

    assert metadata.findtext(f"{{{DC_NS}}}title") == NASTY
    assert [e.text for e in metadata.findall(f"{{{DC_NS}}}creator")] == [AUTHOR_1, AUTHOR_2]
    assert metadata.findtext(f"{{{DC_NS}}}identifier") == IDENTIFIER


def test_z1_ncx_parses_and_round_trips_titles_hrefs_and_identifier(tmp_path: Path) -> None:
    """L3 - the NCX is a second copy of the same strings, and a second chance to break."""
    path = write_raw_epub(tmp_path / "hostile2.epub", hostile_spec())
    root = parse("NCX", member(path, "OEBPS/toc.ncx"))

    assert root.findtext(f"{{{NCX_NS}}}docTitle/{{{NCX_NS}}}text") == NASTY

    meta = root.find(f"{{{NCX_NS}}}head/{{{NCX_NS}}}meta")
    assert meta is not None
    assert meta.get("content") == IDENTIFIER

    def walk(parent: ET.Element) -> List[Tuple[str, Optional[str]]]:
        out: List[Tuple[str, Optional[str]]] = []
        for np in parent.findall(f"{{{NCX_NS}}}navPoint"):
            label = np.findtext(f"{{{NCX_NS}}}navLabel/{{{NCX_NS}}}text")
            content = np.find(f"{{{NCX_NS}}}content")
            assert label is not None and content is not None
            out.append((label, content.get("src")))
            out.extend(walk(np))
        return out

    nav_map = root.find(f"{{{NCX_NS}}}navMap")
    assert nav_map is not None
    assert walk(nav_map) == [
        (NAV_TOP_TITLE, NAV_TOP_HREF),
        (NAV_CHILD_TITLE, NAV_CHILD_HREF),
        (NAV_NOHREF_TITLE, None),
    ]


def test_z1_xhtml_documents_parse_and_round_trip_title_and_lang(tmp_path: Path) -> None:
    """L3 - ``Doc.title`` is element text and ``Doc.lang`` is an attribute, twice over."""
    spec = hostile_spec()
    path = write_raw_epub(tmp_path / "hostile2.epub", spec)

    for doc in spec.docs:
        root = parse(doc.name, member(path, f"OEBPS/{doc.name}"))
        assert root.findtext(f"{{{XHTML_NS}}}head/{{{XHTML_NS}}}title") == doc.title
        assert root.get("lang") == DOC_LANG
        assert root.get(f"{{{XML_NS}}}lang") == DOC_LANG


def test_z1_nav_document_parses_and_round_trips_titles_and_hrefs(tmp_path: Path) -> None:
    """L3 - EPUB 3 writes the nav points a third time, into XHTML instead of NCX."""
    spec = dataclasses.replace(hostile_spec(), version="3.0")
    path = write_raw_epub(tmp_path / "hostile3.epub", spec)
    root = parse("nav.xhtml", member(path, "OEBPS/nav.xhtml"))

    def walk(ol: ET.Element) -> List[Tuple[str, Optional[str]]]:
        out: List[Tuple[str, Optional[str]]] = []
        for li in ol.findall(f"{{{XHTML_NS}}}li"):
            anchor = li.find(f"{{{XHTML_NS}}}a")
            span = li.find(f"{{{XHTML_NS}}}span")
            if anchor is not None:
                out.append((anchor.text or "", anchor.get("href")))
            else:
                assert span is not None
                out.append((span.text or "", None))
            child = li.find(f"{{{XHTML_NS}}}ol")
            if child is not None:
                out.extend(walk(child))
        return out

    top = root.find(f"{{{XHTML_NS}}}body/{{{XHTML_NS}}}nav/{{{XHTML_NS}}}ol")
    assert top is not None
    assert walk(top) == [
        (NAV_TOP_TITLE, NAV_TOP_HREF),
        (NAV_CHILD_TITLE, NAV_CHILD_HREF),
        (NAV_NOHREF_TITLE, None),
    ]
