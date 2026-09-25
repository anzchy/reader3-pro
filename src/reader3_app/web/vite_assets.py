"""Stylesheet links for the committed Vite build (013 WI-10).

The templates link the built CSS of their page entry through ``vite_css(page)``: the
hashed file names change on every rebuild, so they come from ``dist/manifest.json``, not
from the template. ``vite_js(page)`` adds the entry's module script (013 WI-12: settings is the
first page whose JS is the TS entry).

Order matters for the cascade and is fixed here: the CSS of the chunks an entry imports
(the shared token layer -- palette, scales, the plugin-generated theme blocks) comes
before the entry's own CSS.

The manifest is re-read when its mtime changes, so a rebuild under a running server is
picked up without a restart. A missing or malformed manifest, or an unknown page, raises:
the dist is committed, so either is a packaging bug, not a state to degrade around.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from markupsafe import Markup

DIST_DIR = Path(__file__).resolve().parent / "static" / "dist"
MANIFEST_PATH = DIST_DIR / "manifest.json"
URL_BASE = "/static/dist/"

#: Page name -> Vite entry source (frontend/vite.config.ts ENTRIES).
ENTRY_SOURCES: Dict[str, str] = {
    "library": "src/library/index.ts",
    "reader": "src/reader/index.ts",
    "settings": "src/settings/index.ts",
}


@dataclass(frozen=True)
class _Cached:
    mtime_ns: int
    manifest: Dict[str, dict]


_lock = threading.Lock()
_cache: Optional[_Cached] = None


def _load_manifest(path: Path = MANIFEST_PATH) -> Dict[str, dict]:
    global _cache
    mtime_ns = path.stat().st_mtime_ns
    with _lock:
        if _cache is None or _cache.mtime_ns != mtime_ns:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError(f"{path}: manifest is not a JSON object")
            _cache = _Cached(mtime_ns, data)
        return _cache.manifest


def css_files(page: str, manifest: Dict[str, dict]) -> Tuple[str, ...]:
    """The dist-relative CSS files for ``page``: imported chunks first (depth-first), then the entry."""
    if page not in ENTRY_SOURCES:
        raise KeyError(f"unknown Vite page entry {page!r}")
    out: List[str] = []
    seen: set = set()

    def visit(key: str) -> None:
        if key in seen:
            return
        seen.add(key)
        chunk = manifest.get(key)
        if chunk is None:
            raise KeyError(f"manifest has no chunk {key!r}")
        for imported in chunk.get("imports", []):
            visit(imported)
        for css in chunk.get("css", []):
            if css not in out:
                out.append(css)

    visit(ENTRY_SOURCES[page])
    return tuple(out)


def vite_css(page: str) -> Markup:
    """``<link rel="stylesheet">`` tags for one page entry, in cascade order."""
    links = [
        f'<link rel="stylesheet" href="{escape(URL_BASE + css, quote=True)}">'
        for css in css_files(page, _load_manifest())
    ]
    return Markup("\n".join(links))


def vite_js(page: str) -> Markup:
    """The ``<script type="module">`` tag of one page entry (013 WI-12).

    Imported chunks are pulled in by the entry itself, so one tag is all a page needs.
    """
    if page not in ENTRY_SOURCES:
        raise KeyError(f"unknown Vite page entry {page!r}")
    manifest = _load_manifest()
    chunk = manifest.get(ENTRY_SOURCES[page])
    if chunk is None or not chunk.get("file"):
        raise KeyError(f"manifest has no entry chunk for {page!r}")
    src = escape(URL_BASE + chunk["file"], quote=True)
    return Markup(f'<script type="module" src="{src}"></script>')
