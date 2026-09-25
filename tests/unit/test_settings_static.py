"""013 WI-12 static gates for the settings page (matrix C12.03, C12.10; A12.1, A12.5, A12.5b).

* A12.1 / C12.03: no native `confirm(` / `alert(` / `prompt(` in any settings source. The
  scanner is shown to be non-vacuous twice: it must actually read the settings entry and the
  template, and a seeded `window.confirm(...)` must be caught.
* A12.5 / C12.10: the settings stylesheets reference tokens only (`--r3-*`), never the Tier 1
  palette (`--p-*`), and carry real rules (a floor on `var(--r3-` uses), so "0 primitives" is
  not satisfied by an empty file.
* A12.5b / C12.10: `settings.html` has 0 inline styles and 0 non-FOUC inline scripts, the
  inline-HTML allowlist has no settings entry left, and the built settings entry CSS is in the
  committed dist.
* The legacy page assets are gone (the TS entry replaces them), the template loads the entry
  through `vite_js('settings')`, and there is no `set-toast` (user ruling D9).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List

import contract_lints as cl

REPO = cl.REPO_ROOT
FE_SETTINGS = REPO / "frontend" / "src" / "settings"
FE_COMPONENTS = REPO / "frontend" / "src" / "components"
TEMPLATES = REPO / cl.TEMPLATES_REL
STATIC = REPO / "src" / "reader3_app" / "web" / "static"
SETTINGS_HTML = TEMPLATES / "settings.html"

#: A call of one of the three native dialogs: bare, or through window / globalThis / self.
#: A method of some other object (`modal.confirm(`) is not a native dialog.
NATIVE_DIALOG_RE = re.compile(
    r"(?:(?<![\w$.])|(?<=window\.)|(?<=globalThis\.)|(?<=self\.))(?:confirm|alert|prompt)\s*\("
)
#: Floor on token references in the settings stylesheets: the page's rules live there now.
MIN_TOKEN_REFS = 20


def settings_sources(repo: Path = REPO) -> List[Path]:
    """Every settings source the native-dialog scan covers."""
    fe = repo / "frontend" / "src"
    static = repo / "src" / "reader3_app" / "web" / "static"
    out = sorted((fe / "settings").rglob("*.ts")) + sorted((fe / "settings").rglob("*.css"))
    out += sorted((fe / "components").glob("modal*.ts"))
    out += [p for p in (static / "settings.js", repo / cl.TEMPLATES_REL / "settings.html") if p.is_file()]
    return out


def native_dialog_hits(paths: List[Path]) -> List[str]:
    hits = []
    for p in paths:
        for m in NATIVE_DIALOG_RE.finditer(p.read_text(encoding="utf-8")):
            hits.append(f"{p.name}:{m.group(0)}")
    return hits


def settings_css_files() -> List[Path]:
    return sorted(FE_SETTINGS.rglob("*.css")) + sorted(FE_COMPONENTS.glob("modal*.css"))


# ---------------------------------------------------------------------------
# A12.1 / C12.03
# ---------------------------------------------------------------------------
def test_no_native_dialogs() -> None:
    sources = settings_sources()
    names = {p.name for p in sources}
    assert "index.ts" in names and "settings.html" in names, f"scan did not reach the page: {sorted(names)}"
    assert native_dialog_hits(sources) == []


def test_native_dialog_scan_catches_a_seed(tmp_path: Path) -> None:
    fe = tmp_path / "frontend" / "src" / "settings"
    fe.mkdir(parents=True)
    (fe / "index.ts").write_text(
        'modal.confirm(x);\nconst ok = window.confirm("Clear?");\nconfirmed(1);\n', encoding="utf-8"
    )
    hits = native_dialog_hits(settings_sources(tmp_path))
    assert hits == ["index.ts:confirm("], hits


# ---------------------------------------------------------------------------
# A12.5 / C12.10
# ---------------------------------------------------------------------------
def test_no_primitive_refs() -> None:
    files = settings_css_files()
    assert files, "no settings stylesheet found"
    text = "\n".join(p.read_text(encoding="utf-8") for p in files)
    assert "var(--p-" not in text
    refs = len(re.findall(r"var\(\s*--r3-", text))
    assert refs >= MIN_TOKEN_REFS, f"only {refs} token references in {[p.name for p in files]}"


# ---------------------------------------------------------------------------
# A12.5b / C12.10
# ---------------------------------------------------------------------------
def test_settings_inline_counts_are_zero_and_unlisted() -> None:
    lint = cl.load(cl.INLINE_LINT, "lint_inline_html_wi12")
    allow = json.loads((REPO / cl.INLINE_ALLOWLIST_REL).read_text(encoding="utf-8"))
    assert "settings.html" not in allow["style"], allow["style"]
    assert "settings.html" not in allow["script"], allow["script"]
    assert lint.count_template(SETTINGS_HTML.read_text(encoding="utf-8")) == (0, 0)


def test_settings_entry_css_is_built() -> None:
    from reader3_app.web import vite_assets as va

    manifest = json.loads(va.MANIFEST_PATH.read_text(encoding="utf-8"))
    own = manifest[va.ENTRY_SOURCES["settings"]].get("css", [])
    assert own, "the settings entry emits no CSS of its own"
    text = "".join((va.DIST_DIR / css).read_text(encoding="utf-8") for css in own)
    refs = len(re.findall(r"var\(\s*--r3-", text))
    assert refs >= MIN_TOKEN_REFS, f"the built settings CSS has {refs} token references"


# ---------------------------------------------------------------------------
# the TS entry replaces the legacy page assets
# ---------------------------------------------------------------------------
def test_legacy_settings_assets_removed() -> None:
    assert not (STATIC / "settings.js").exists()
    assert not (STATIC / "settings.css").exists()


def test_template_loads_the_ts_entry() -> None:
    html = SETTINGS_HTML.read_text(encoding="utf-8")
    assert "{{ vite_js('settings') }}" in html
    assert "{{ vite_css('settings') }}" in html
    assert "/static/settings" not in html


def test_no_settings_toast() -> None:
    """D9: the settings page reports through its own result lines, not a toast."""
    files = list(FE_SETTINGS.rglob("*")) + [SETTINGS_HTML]
    text = "\n".join(p.read_text(encoding="utf-8") for p in files if p.is_file())
    assert "set-toast" not in text
