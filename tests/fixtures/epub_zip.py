"""A raw EPUB zip writer, for the structures ``ebooklib.epub.EpubBook`` cannot express.

``epub_builder.build_epub`` goes through ebooklib's *writer*, which is a
well-behaved producer: it will not emit a TOC entry pointing at a file that does
not exist, a spine item marked ``linear="no"``, an EPUB 2 package with only an
NCX, or a zip missing ``container.xml``. Those are exactly the inputs a reader
has to survive, so the corpus that carries them has to be assembled at the zip
level instead.

Everything here writes bytes verbatim. No consistency check is performed on
purpose: a builder that quietly repaired a malformed manifest would turn every
"the reader survives bad input" case downstream into a test of well-formed input.
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping, Optional, Sequence, Tuple, Union

MIMETYPE = "application/epub+zip"

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="{opf_path}" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


@dataclass(frozen=True)
class Doc:
    """One XHTML document in the manifest.

    ``in_spine=False`` puts a document in the manifest only -- the shape a TOC
    entry needs in order to point at something real that is nonetheless
    unreachable by linear reading. ``linear=False`` emits ``linear="no"``.
    """

    doc_id: str
    name: str  # href relative to the OPF directory
    body: str  # inner HTML of <body>, inserted verbatim
    title: str = ""
    lang: str = "en"
    in_spine: bool = True
    linear: bool = True
    #: When set, this is written to the zip instead of the wrapped ``body``.
    #: The escape hatch for documents that are not valid UTF-8 or not XHTML.
    raw_bytes: Optional[bytes] = None


@dataclass(frozen=True)
class NavPoint:
    """One TOC entry. ``href`` may dangle, and may be ``None``."""

    title: str
    href: Optional[str]
    children: Tuple["NavPoint", ...] = ()


@dataclass(frozen=True)
class Img:
    item_id: str
    name: str  # href relative to the OPF directory
    payload: bytes
    media_type: str = "image/png"


@dataclass(frozen=True)
class EpubSpec:
    title: str = "Raw Test Book"
    language: str = "en"
    authors: Tuple[str, ...] = ("Ada Tester",)
    identifier: str = "urn:uuid:reader3-raw-0001"
    version: str = "2.0"  # "2.0" -> NCX only; "3.0" -> nav document
    opf_path: str = "OEBPS/content.opf"
    docs: Tuple[Doc, ...] = ()
    nav: Tuple[NavPoint, ...] = ()
    images: Tuple[Img, ...] = ()
    #: EPUB 2 writes an NCX, EPUB 3 a nav document. Both are overridable so a
    #: fixture can ship an EPUB 3 with a legacy NCX, or a book with no TOC at all.
    with_ncx: Optional[bool] = None
    with_nav_doc: Optional[bool] = None
    #: Extra members appended verbatim, and members to leave out entirely.
    extra_files: Mapping[str, bytes] = field(default_factory=dict)
    omit_container: bool = False


def _xhtml(doc: Doc) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{doc.lang}" lang="{doc.lang}">\n'
        f"<head><title>{doc.title or doc.doc_id}</title>"
        '<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/></head>\n'
        f"<body>{doc.body}</body>\n"
        "</html>\n"
    )


def _opf(spec: EpubSpec, *, with_ncx: bool, with_nav_doc: bool) -> str:
    creators = "".join(f"    <dc:creator>{a}</dc:creator>\n" for a in spec.authors)

    manifest = []
    if with_ncx:
        manifest.append(
            '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        )
    if with_nav_doc:
        manifest.append(
            '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
            'properties="nav"/>'
        )
    for d in spec.docs:
        manifest.append(
            f'    <item id="{d.doc_id}" href="{d.name}" media-type="application/xhtml+xml"/>'
        )
    for im in spec.images:
        manifest.append(
            f'    <item id="{im.item_id}" href="{im.name}" media-type="{im.media_type}"/>'
        )

    spine_items = []
    for d in spec.docs:
        if not d.in_spine:
            continue
        linear = "" if d.linear else ' linear="no"'
        spine_items.append(f'    <itemref idref="{d.doc_id}"{linear}/>')

    spine_attr = ' toc="ncx"' if with_ncx else ""
    modified = (
        '    <meta property="dcterms:modified">2026-08-24T00:00:00Z</meta>\n'
        if spec.version.startswith("3")
        else ""
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" '
        f'version="{spec.version}">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:opf="http://www.idpf.org/2007/opf">\n'
        f'    <dc:identifier id="BookId">{spec.identifier}</dc:identifier>\n'
        f"    <dc:title>{spec.title}</dc:title>\n"
        f"    <dc:language>{spec.language}</dc:language>\n"
        f"{creators}{modified}"
        "  </metadata>\n"
        "  <manifest>\n" + "\n".join(manifest) + "\n  </manifest>\n"
        f"  <spine{spine_attr}>\n" + "\n".join(spine_items) + "\n  </spine>\n"
        "</package>\n"
    )


def _ncx(spec: EpubSpec) -> str:
    counter = [0]

    def points(nav: Sequence[NavPoint], depth: int) -> str:
        out = []
        for np in nav:
            counter[0] += 1
            src = f'<content src="{np.href}"/>' if np.href is not None else "<content/>"
            inner = points(np.children, depth + 1) if np.children else ""
            out.append(
                f'{"  " * (depth + 2)}<navPoint id="np{counter[0]}" playOrder="{counter[0]}">'
                f"<navLabel><text>{np.title}</text></navLabel>{src}{inner}</navPoint>"
            )
        return "\n" + "\n".join(out) + "\n" if out else ""

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
        f'  <head><meta name="dtb:uid" content="{spec.identifier}"/></head>\n'
        f"  <docTitle><text>{spec.title}</text></docTitle>\n"
        f"  <navMap>{points(spec.nav, 0)}  </navMap>\n"
        "</ncx>\n"
    )


def _nav_doc(spec: EpubSpec) -> str:
    def items(nav: Sequence[NavPoint]) -> str:
        out = []
        for np in nav:
            sub = f"<ol>{items(np.children)}</ol>" if np.children else ""
            if np.href is None:
                out.append(f"<li><span>{np.title}</span>{sub}</li>")
            else:
                out.append(f'<li><a href="{np.href}">{np.title}</a>{sub}</li>')
        return "".join(out)

    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops">\n'
        "<head><title>Contents</title></head>\n"
        '<body><nav epub:type="toc" id="toc"><ol>'
        f"{items(spec.nav)}"
        "</ol></nav></body>\n"
        "</html>\n"
    )


def write_raw_epub(path: Union[str, os.PathLike], spec: EpubSpec) -> Path:
    """Assemble ``spec`` into a zip at ``path`` with no validation whatsoever."""
    with_ncx = spec.with_ncx if spec.with_ncx is not None else not spec.version.startswith("3")
    with_nav_doc = (
        spec.with_nav_doc if spec.with_nav_doc is not None else spec.version.startswith("3")
    )
    opf_dir = os.path.dirname(spec.opf_path)

    members: Dict[str, bytes] = {}
    if not spec.omit_container:
        members["META-INF/container.xml"] = CONTAINER_XML.format(
            opf_path=spec.opf_path
        ).encode("utf-8")
    members[spec.opf_path] = _opf(spec, with_ncx=with_ncx, with_nav_doc=with_nav_doc).encode(
        "utf-8"
    )
    if with_ncx:
        members[os.path.join(opf_dir, "toc.ncx")] = _ncx(spec).encode("utf-8")
    if with_nav_doc:
        members[os.path.join(opf_dir, "nav.xhtml")] = _nav_doc(spec).encode("utf-8")
    for d in spec.docs:
        payload = d.raw_bytes if d.raw_bytes is not None else _xhtml(d).encode("utf-8")
        members[os.path.join(opf_dir, d.name)] = payload
    for im in spec.images:
        members[os.path.join(opf_dir, im.name)] = im.payload
    members.update(spec.extra_files)

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        # The mimetype member must come first and be stored, not deflated.
        zf.writestr(zipfile.ZipInfo("mimetype"), MIMETYPE, compress_type=zipfile.ZIP_STORED)
        for name, payload in members.items():
            zf.writestr(name.replace(os.sep, "/"), payload)
    return out
