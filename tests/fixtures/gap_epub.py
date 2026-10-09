"""A minimal EPUB3 builder for spine-gap books (012 WI-4c.2, matrix F-3).

Stdlib ``zipfile`` only and nothing imported from ``epub_corpus.py`` / ``epub_zip.py`` (both frozen under
``suite_hash``); this module is new and not in ``HASH_COVERED_PATHS``.

``build_gap_epub(path, items)`` writes ``mimetype`` (stored, first), ``META-INF/container.xml``,
``OEBPS/content.opf`` (manifest plus spine built from ``items``) and ``OEBPS/nav.xhtml``. Each item is a
:class:`GapItem` ``(id, href, media_type, body, props, linear, in_manifest)``:

- ``body`` is a marker string; the builder wraps it in a document of the item's media type
  (XHTML, HTML, or SVG ``<text>``).
- ``props`` is the manifest ``properties`` attribute (``""`` for none). ``"cover"`` is what makes ebooklib
  0.20.0 load an ``application/xhtml+xml`` item as ``EpubCoverHtml`` (not a document), whatever its id.
- ``linear=False`` writes ``linear="no"`` on the itemref.
- ``in_manifest=False`` writes the itemref only (a dangling idref) and no manifest item or file.
"""

from __future__ import annotations

import zipfile
from html import escape
from pathlib import Path
from typing import NamedTuple, Sequence, Union

OPF_DIR = "OEBPS"


class GapItem(NamedTuple):
    id: str
    href: str
    media_type: str
    body: str
    props: str = ""
    linear: bool = True
    in_manifest: bool = True


XHTML = "application/xhtml+xml"
HTML = "text/html"
SVG = "image/svg+xml"

_CONTAINER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
    f'  <rootfiles><rootfile full-path="{OPF_DIR}/content.opf" media-type="application/oebps-package+xml"/>'
    "</rootfiles>\n</container>\n"
)


def _document(item: GapItem) -> str:
    marker = escape(item.body)
    if item.media_type == SVG:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="50">'
            f'<text x="0" y="20">{marker}</text></svg>\n'
        )
    if item.media_type == HTML:
        return f"<!DOCTYPE html>\n<html><head><title>{item.id}</title></head><body><p>{marker}</p></body></html>\n"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
        f"<head><title>{item.id}</title></head>\n<body><h1>{item.id}</h1><p>{marker}</p></body>\n</html>\n"
    )


def _nav(items: Sequence[GapItem]) -> str:
    links = "".join(
        f'<li><a href="{escape(i.href)}">{escape(i.id)}</a></li>'
        for i in items
        if i.in_manifest and i.media_type == XHTML and "cover" not in i.props.split()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
        "<head><title>Navigation</title></head>\n"
        f'<body><nav epub:type="toc" id="toc"><ol>{links}</ol></nav></body>\n</html>\n'
    )


def _opf(items: Sequence[GapItem], title: str) -> str:
    manifest = ['    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>']
    for i in items:
        if not i.in_manifest:
            continue
        props = f' properties="{i.props}"' if i.props else ""
        manifest.append(f'    <item id="{i.id}" href="{escape(i.href)}" media-type="{i.media_type}"{props}/>')
    no_linear = ' linear="no"'
    spine = [f'    <itemref idref="{i.id}"{"" if i.linear else no_linear}/>' for i in items]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        '    <dc:identifier id="bookid">urn:uuid:4c2a0000-0000-4000-8000-000000000012</dc:identifier>\n'
        f"    <dc:title>{escape(title)}</dc:title>\n"
        "    <dc:language>en</dc:language>\n"
        '    <meta property="dcterms:modified">2026-10-09T00:00:00Z</meta>\n'
        "  </metadata>\n"
        "  <manifest>\n" + "\n".join(manifest) + "\n  </manifest>\n"
        "  <spine>\n" + "\n".join(spine) + "\n  </spine>\n"
        "</package>\n"
    )


def build_gap_epub(path: Union[str, Path], items: Sequence[GapItem], *, title: str = "Gap Book") -> Path:
    """Write the EPUB to ``path`` and return it."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", _CONTAINER, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr(f"{OPF_DIR}/content.opf", _opf(items, title), compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr(f"{OPF_DIR}/nav.xhtml", _nav(items), compress_type=zipfile.ZIP_DEFLATED)
        for i in items:
            if i.in_manifest:
                zf.writestr(f"{OPF_DIR}/{i.href}", _document(i), compress_type=zipfile.ZIP_DEFLATED)
    return out
