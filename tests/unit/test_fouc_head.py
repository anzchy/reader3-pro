"""013 WI-10 C10.23 (A10.9 structural half, D7): the served `<head>` carries ONE classic
inline FOUC stamp, before the first stylesheet, identical on all three pages.

Why a unit case on top of the e2e timing cases (`tests/e2e/shell_4a/test_fouc.py`): a
`defer` or `type=module` stamp also runs before DOMContentLoaded, so the DCL sample
alone cannot see the regression; this case pins the shape that makes the stamp run
before `<body>` is parsed.

For each page served by the real app (FastAPI `TestClient`, a tmp library with one
synthetic book):
    * exactly one `<script>` in `<head>` whose body mentions `reader3.ui.colorScheme`;
    * no `src`, no `defer` / `async`, `type` absent or `text/javascript`;
    * it precedes the first `<link rel="stylesheet">` among the head's children;
    * sha256(body) is the committed `FOUC_SHA256` of `scripts/lint_inline_html.py` --
      so the three pages carry the same bytes (ruling D7: the exemption is keyed on it).

Seeded copies of `library.html` (stamp turned into a module; stamp moved after the
first stylesheet link) are served through the same app and must be reported.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
from pathlib import Path
from typing import Iterator, List, Tuple

import pytest
from bs4 import BeautifulSoup, Tag
from epub_corpus import build_epub2
from fastapi.testclient import TestClient
from jinja2 import ChoiceLoader, FileSystemLoader

from reader3_app.reader3 import process_epub
from reader3_app import search_service
from reader3_app.ai.books import BookUuidResolver
from reader3_app.web import server

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "src" / "reader3_app" / "web" / "templates"
LINT = REPO / "scripts" / "lint_inline_html.py"
BOOK_ID = "fouc_head_data"
STAMP_MARKER = "reader3.ui.colorScheme"


def _fouc_sha() -> frozenset:
    spec = importlib.util.spec_from_file_location("lint_inline_html_for_fouc", LINT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.FOUC_SHA256


def fouc_findings(html: str, expected_sha: frozenset) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    head = soup.head
    if head is None:
        return ["no <head>"]
    children = [c for c in head.children if isinstance(c, Tag)]
    stamps = [c for c in children if c.name == "script" and STAMP_MARKER in (c.string or "")]
    nested = [s for s in head.find_all("script") if STAMP_MARKER in (s.string or "") and s not in stamps]
    problems: List[str] = []
    if nested:
        problems.append("a stamp script is nested, not a direct child of <head>")
    if len(stamps) != 1:
        return problems + [f"expected exactly 1 stamp script in <head>, found {len(stamps)}"]
    stamp = stamps[0]
    if stamp.has_attr("src"):
        problems.append("stamp has src")
    for attr in ("defer", "async"):
        if stamp.has_attr(attr):
            problems.append(f"stamp has {attr}")
    if stamp.get("type") not in (None, "text/javascript"):
        problems.append(f"stamp type={stamp.get('type')!r}")
    links = [
        i for i, c in enumerate(children) if c.name == "link" and "stylesheet" in (c.get("rel") or [])
    ]
    if not links:
        problems.append("no stylesheet link in <head>")
    elif children.index(stamp) > links[0]:
        problems.append("stamp comes after the first stylesheet link")
    body = stamp.string or ""
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if sha not in expected_sha:
        problems.append(f"stamp sha256 {sha} is not the committed FOUC_SHA256")
    return problems


def _clear_caches() -> None:
    server.load_book_cached.cache_clear()
    search_service.load_book_cached.cache_clear()
    server._stats_cache.clear()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    books = tmp_path / "books"
    books.mkdir()
    epub = tmp_path / "book.epub"
    build_epub2(epub)
    process_epub(str(epub), str(books / BOOK_ID))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(server, "BOOKS_DIR", str(books))
    monkeypatch.setattr(server, "book_uuid_resolver", BookUuidResolver(str(books)))
    monkeypatch.delenv("READER3_TOKEN", raising=False)
    monkeypatch.delenv("READER3_ALLOWED_HOSTS", raising=False)
    _clear_caches()
    try:
        with TestClient(server.app, base_url="http://127.0.0.1") as c:
            yield c
    finally:
        _clear_caches()


PAGES: Tuple[Tuple[str, str], ...] = (
    ("library", "/"),
    ("reader", f"/read/{BOOK_ID}/0"),
    ("settings", "/settings"),
)


def _get(client: TestClient, path: str) -> str:
    resp = client.get(path)
    assert resp.status_code == 200, f"GET {path} -> {resp.status_code}"
    return resp.text


def test_each_page_has_one_classic_stamp_before_the_first_stylesheet(client: TestClient) -> None:
    expected = _fouc_sha()
    assert len(expected) == 1, "FOUC_SHA256 must hold exactly the one stamp hash (ruling D7)"
    findings = {name: fouc_findings(_get(client, path), expected) for name, path in PAGES}
    assert findings == {name: [] for name, _ in PAGES}


def _stamp_block(text: str) -> str:
    m = re.search(r"<script>[^<]*" + re.escape(STAMP_MARKER) + r"[^<]*</script>\s*", text)
    assert m, "library.html has no inline stamp to seed from"
    return m.group(0)


@pytest.mark.parametrize("seed", ["module", "after_link"])
def test_seeded_bad_stamp_is_reported(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seed: str
) -> None:
    if seed == "after_link":
        # SEPARATION-BROKEN (013 WI-13, coordinator-approved): this seed used to move the stamp
        # after the first literal `<link rel="stylesheet">` in the library.html *source*. Since
        # WI-13 the stylesheet links are emitted by `{{ vite_css('library') }}`, so the source
        # holds none and the seed could not be built for any implementation. The seed now works
        # on the *rendered* page (where the links do exist): the unseeded render must be clean,
        # and moving the stamp after the first rendered link must be reported as exactly that.
        rendered = _get(client, "/")
        assert fouc_findings(rendered, _fouc_sha()) == [], "the unseeded library page is not clean"
        stamp = _stamp_block(rendered)
        without = rendered.replace(stamp, "", 1)
        link = re.search(r'<link rel="stylesheet"[^>]*>', without)
        assert link, "the rendered library page has no stylesheet link"
        mutated_render = without[: link.end()] + "\n" + stamp + without[link.end():]
        assert mutated_render != rendered
        findings = fouc_findings(mutated_render, _fouc_sha())
        assert "stamp comes after the first stylesheet link" in findings, (
            f"seed {seed!r} was not reported: {findings}"
        )
        return
    source = (TEMPLATES / "library.html").read_text(encoding="utf-8")
    block = _stamp_block(source)
    if seed == "module":
        mutated = source.replace(block, block.replace("<script>", '<script type="module">', 1), 1)
    assert mutated != source
    seeded_dir = tmp_path / "seeded_templates"
    seeded_dir.mkdir()
    (seeded_dir / "library.html").write_text(mutated, encoding="utf-8")
    env = server.templates.env
    monkeypatch.setattr(env, "loader", ChoiceLoader([FileSystemLoader(str(seeded_dir)), env.loader]))
    findings = fouc_findings(_get(client, "/"), _fouc_sha())
    assert findings, f"seed {seed!r} was not reported"
