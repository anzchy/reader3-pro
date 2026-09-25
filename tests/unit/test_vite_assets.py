"""013 WI-10: `vite_css(page)` links the committed build's CSS in cascade order.

Added after the implementation (post-hoc coverage of the template helper, not part of
the recorded red): the shared token-layer chunk precedes the entry's own stylesheet,
every linked file exists in the committed dist, and bad inputs raise instead of emitting
a page with no tokens.
"""

from __future__ import annotations

import re

import pytest

from reader3_app.web import vite_assets as va


@pytest.mark.parametrize("page", sorted(va.ENTRY_SOURCES))
def test_links_exist_and_theme_chunk_comes_first(page: str) -> None:
    html = str(va.vite_css(page))
    hrefs = re.findall(r'<link rel="stylesheet" href="([^"]+)">', html)
    assert len(hrefs) >= 2, html
    for href in hrefs:
        assert href.startswith(va.URL_BASE)
        assert (va.DIST_DIR / href[len(va.URL_BASE):]).is_file(), href
    dark = re.compile(r"prefers-color-scheme:\s*dark")
    theme = [h for h in hrefs if dark.search((va.DIST_DIR / h[len(va.URL_BASE):]).read_text(encoding="utf-8"))]
    assert theme == hrefs[:1], "the token/theme CSS must be the first stylesheet linked"


def test_imports_precede_entry_and_dedupe() -> None:
    manifest = {
        "src/reader/index.ts": {"imports": ["_a.js", "_b.js"], "css": ["entry.css"]},
        "_a.js": {"imports": ["_b.js"], "css": ["a.css"]},
        "_b.js": {"css": ["b.css"]},
    }
    assert va.css_files("reader", manifest) == ("b.css", "a.css", "entry.css")


def test_unknown_page_and_missing_chunk_raise() -> None:
    with pytest.raises(KeyError):
        va.css_files("nope", {})
    with pytest.raises(KeyError):
        va.css_files("library", {"src/library/index.ts": {"imports": ["_gone.js"]}})


# ---------------------------------------------------------------------------
# 013 WI-12: `vite_js(page)` loads the page entry's JS (written before the helper, red first)
# ---------------------------------------------------------------------------
MODULE_SCRIPT_RE = re.compile(r'<script type="module" src="([^"]+)"></script>')


def _vite_js():
    fn = getattr(va, "vite_js", None)
    assert fn is not None, "vite_assets.vite_js is not defined"
    return fn


@pytest.mark.parametrize("page", sorted(va.ENTRY_SOURCES))
def test_vite_js_is_one_module_script_for_the_entry(page: str) -> None:
    html = str(_vite_js()(page))
    srcs = MODULE_SCRIPT_RE.findall(html)
    assert len(srcs) == 1 and MODULE_SCRIPT_RE.fullmatch(html.strip()), html
    manifest = va._load_manifest()
    assert srcs[0] == va.URL_BASE + manifest[va.ENTRY_SOURCES[page]]["file"]
    assert (va.DIST_DIR / srcs[0][len(va.URL_BASE):]).is_file(), srcs[0]


def test_vite_js_unknown_page_raises() -> None:
    fn = _vite_js()
    with pytest.raises(KeyError):
        fn("nope")


def test_vite_js_is_a_template_global() -> None:
    from reader3_app.web import server

    fn = _vite_js()
    assert server.templates.env.globals.get("vite_js") is fn


# ---------------------------------------------------------------------------
# 013 final review (RV-9): coverage gaps. The module caches the parsed manifest globally
# (keyed by mtime); every test below starts and ends with that cache empty, so a seeded
# manifest can never leak into another test or the real one into these.
# ---------------------------------------------------------------------------
@pytest.fixture
def fresh_manifest_cache(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(va, "_cache", None)
    yield
    va._cache = None


def test_manifest_that_is_not_an_object_raises(tmp_path, fresh_manifest_cache) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="not a JSON object"):
        va._load_manifest(path)
    assert va._cache is None, "a rejected manifest must not be cached"


@pytest.mark.parametrize(
    "manifest",
    [
        pytest.param({}, id="entry-chunk-missing"),
        pytest.param({"src/settings/index.ts": {"file": ""}}, id="entry-file-empty"),
        pytest.param({"src/settings/index.ts": {"css": ["x.css"]}}, id="entry-file-absent"),
    ],
)
def test_vite_js_without_an_entry_file_raises(monkeypatch, fresh_manifest_cache, manifest) -> None:
    monkeypatch.setattr(va, "_load_manifest", lambda *a, **k: manifest)
    with pytest.raises(KeyError, match="no entry chunk"):
        va.vite_js("settings")


def test_css_shared_by_two_chunks_is_linked_once_at_its_first_depth_first_position(fresh_manifest_cache) -> None:
    manifest = {
        "src/library/index.ts": {"imports": ["_a.js", "_b.js"], "css": ["entry.css", "shared.css"]},
        "_a.js": {"imports": ["_c.js"], "css": ["a.css"]},
        "_b.js": {"css": ["shared.css", "b.css"]},
        "_c.js": {"css": ["shared.css", "c.css"]},
    }
    assert va.css_files("library", manifest) == ("shared.css", "c.css", "a.css", "b.css", "entry.css")
