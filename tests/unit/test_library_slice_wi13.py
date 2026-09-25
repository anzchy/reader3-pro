"""013 WI-13 (4A.4 library page slice): the static half of the acceptance.

Cases (tests artifact 2026-09-24, WI-13; ruling D12 of 2026-09-25):

* A13.4b / C13.10 -- `templates/library.html` has 0 inline style (no `<style>` block, no
  `style=` attribute) and at most 420 lines; the three legacy IIFE scripts are no longer
  loaded; the page's JS is the Vite entry.
* A13.9 -- `library.html` is struck from the inline-HTML allowlist and from the hardcode
  baseline in the same change (the migrated CSS passes the hardcode lint on its own).
* A11.3 (library half) -- the library TS has no local `escapeHtml`; it imports `@shared/escape`.
* C13.20 / Track-D WI-3 #1, #5 (library half) -- one `statusMeta` definition, in `shared/`,
  imported by the library; no testid built by concatenation or interpolation.
* C13.27 / Track-D WI-1 #7 -- the DegradeBanner stylesheet passes the 0.8 token-ref lint; a
  typo'd token in it is caught (seed).
* C13.28 / Track-D WI-8 #1-#3 -- the skeleton source carries no testid; the built CSS stops
  the skeleton under reduced motion with a solid `--r3-surface-sunken` background, and the
  default rule animates; a build without the override is caught (seed).
* Carried over from WI-11 -- the DegradeBanner and Toast styles ship in the library bundle.

Track-D tags (`[track_d_013 WI-n#m]`) sit in the docstrings; `test_track_d_ledger.py` reads them.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Dict, List

import pytest

import contract_lints as cl

# SEPARATION-BROKEN (013 WI-13 C13.34, marker only, no assertion changed): the module-level
# `pytestmark = pytest.mark.track_d_013` also selected this file's non-Track-D tests, so
# `-m track_d_013` over-collected. The marker now sits on the seven tagged tests only;
# tests/unit/test_track_d_c34_guard.py holds the selection equal to the ledger's PASS rows.
TRACK_D = pytest.mark.track_d_013

REPO = cl.REPO_ROOT
TEMPLATE = REPO / "src" / "reader3_app" / "web" / "templates" / "library.html"
FE_SRC = REPO / "frontend" / "src"
LIBRARY_SRC = FE_SRC / "library"
DIST = REPO / "src" / "reader3_app" / "web" / "static" / "dist"
MANIFEST = DIST / "manifest.json"
LEGACY_SCRIPTS = ("/static/library.js", "/static/library-chat.js", "/static/library-search.js")
LINE_BUDGET = 420


def _strip_ts_comments(text: str) -> str:
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    return re.sub(r"(^|[^:\\])//[^\n]*", r"\1", text)


def _library_ts() -> Dict[str, str]:
    return {
        p.relative_to(FE_SRC).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(LIBRARY_SRC.rglob("*.ts"))
    }


def _entry_css(entry: str) -> str:
    """The built CSS the library page links: the entry's own chunk plus its imports' chunks."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    seen: List[str] = []

    def walk(key: str) -> None:
        node = manifest[key]
        for css in node.get("css", []):
            if css not in seen:
                seen.append(css)
        for imp in node.get("imports", []):
            walk(imp)

    walk(entry)
    return "\n".join((DIST / css).read_text(encoding="utf-8") for css in seen)


# ---------------------------------------------------------------------------
# A13.4b / C13.10
# ---------------------------------------------------------------------------
def test_template_has_no_inline_style_and_fits_the_line_budget() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert len(re.findall(r"<style\b", text, re.I)) == 0, "library.html still has a <style> block"
    assert len(re.findall(r"\sstyle\s*=", text, re.I)) == 0, "library.html still has a style= attribute"
    lines = len(text.splitlines())
    assert lines <= LINE_BUDGET, f"library.html is {lines} lines (budget {LINE_BUDGET})"


def test_template_loads_the_vite_entry_not_the_legacy_scripts() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    loaded = [s for s in LEGACY_SCRIPTS if s in text]
    assert loaded == [], f"library.html still loads {loaded}"
    assert "{{ vite_js('library') }}" in text
    assert "{{ vite_css('library') }}" in text
    # every stylesheet is the built bundle: no legacy /static/*.css, no external font host
    links = re.findall(r"<link\b[^>]*>", text, re.I)
    stray = [l for l in links if "stylesheet" in l or "preconnect" in l]
    assert stray == [], f"library.html links stylesheets outside the bundle: {stray}"


# ---------------------------------------------------------------------------
# A13.9
# ---------------------------------------------------------------------------
def test_library_struck_from_inline_allowlist_and_hardcode_baseline() -> None:
    allowlist = json.loads((REPO / cl.INLINE_ALLOWLIST_REL).read_text(encoding="utf-8"))
    assert "library.html" not in allowlist["style"], allowlist["style"]
    assert "library.html" not in allowlist["script"], allowlist["script"]
    baseline = cl.read_baseline(REPO)
    assert f"{cl.TEMPLATES_REL}/library.html" not in baseline
    library_css = [k for k in baseline if k.startswith("frontend/src/library/")]
    assert library_css == [], f"the migrated library CSS is baselined instead of clean: {library_css}"


# ---------------------------------------------------------------------------
# A11.3, library half
# ---------------------------------------------------------------------------
ESCAPE_DEF_RE = re.compile(
    r"(?:function\s+escapeHtml\b|(?:const|let|var)\s+escapeHtml\s*=)"
)


def test_library_ts_has_no_local_escape_and_imports_the_shared_one() -> None:
    sources = _library_ts()
    assert sources, "no TS under frontend/src/library"
    local = [rel for rel, text in sources.items() if ESCAPE_DEF_RE.search(_strip_ts_comments(text))]
    assert local == [], f"local escapeHtml in {local}"
    importers = [rel for rel, text in sources.items() if re.search(r"from\s+[\"']@shared/escape[\"']", text)]
    assert importers, "no library module imports @shared/escape"


# ---------------------------------------------------------------------------
# C13.20 / Track-D WI-3 #1 and #5 (library half)
# ---------------------------------------------------------------------------
STATUS_META_DEF_RE = re.compile(r"(?:export\s+)?(?:const|let|var|function)\s+statusMeta\b")


def _status_meta_definitions(root: Path) -> List[str]:
    out = []
    for p in sorted(root.rglob("*.ts")):
        if STATUS_META_DEF_RE.search(_strip_ts_comments(p.read_text(encoding="utf-8"))):
            out.append(p.relative_to(root).as_posix())
    return out


@TRACK_D
def test_status_meta_single_definition_imported_by_library() -> None:
    """[track_d_013 WI-3#5/library] one statusMeta definition (in shared/), imported by the library."""
    sites = _status_meta_definitions(FE_SRC)
    assert len(sites) == 1 and sites[0].startswith("shared/"), sites
    module = sites[0][: -len(".ts")]
    importers = [
        rel for rel, text in _library_ts().items()
        if re.search(rf"import\s*\{{[^}}]*\bstatusMeta\b[^}}]*\}}\s*from\s*[\"']@{module}[\"']", text)
    ]
    assert importers, f"no library module imports statusMeta from @{module}"


def test_status_meta_scanner_counts_a_local_copy(tmp_path: Path) -> None:
    """Seed: a library-local copy makes the count 2 (the guard above is not vacuous)."""
    (tmp_path / "shared").mkdir()
    (tmp_path / "library").mkdir()
    (tmp_path / "shared" / "status-meta.ts").write_text("export const statusMeta = {};\n", encoding="utf-8")
    (tmp_path / "library" / "status.ts").write_text("const statusMeta = {};\n", encoding="utf-8")
    assert _status_meta_definitions(tmp_path) == ["library/status.ts", "shared/status-meta.ts"]


TESTID_BUILD_RES = (
    re.compile(r"setAttribute\(\s*[\"']data-testid[\"']\s*,\s*`"),
    re.compile(r"setAttribute\(\s*[\"']data-testid[\"']\s*,\s*[^)]*\+"),
    re.compile(r"dataset\.testid\s*=\s*`"),
    re.compile(r"dataset\.testid\s*=\s*[^;\n]*\+"),
    re.compile(r"data-testid=\"\$\{"),
)


@TRACK_D
def test_no_testid_concatenation_in_library_ts() -> None:
    """[track_d_013 WI-3#1] no data-testid built by concatenation or template interpolation."""
    hits = [
        (rel, rx.pattern)
        for rel, text in _library_ts().items()
        for rx in TESTID_BUILD_RES
        if rx.search(_strip_ts_comments(text))
    ]
    assert hits == [], hits
    rc, out = cl.call_main(cl.load(cl.NAMING_LINT, "lint_testid_naming_wi13"), [])
    assert rc == 0, out


# ---------------------------------------------------------------------------
# C13.27 / Track-D WI-1 #7
# ---------------------------------------------------------------------------
BANNER_CSS = FE_SRC / "components" / "degrade-banner.css"


def _token_lint(root: Path) -> int:
    module = cl.load(cl.TOKEN_REFS_LINT, "lint_token_refs_wi13")
    rc, _ = cl.call_main(module, ["--root", str(root)])
    return rc


@TRACK_D
def test_banner_css_passes_token_ref_lint_and_a_typo_is_caught(tmp_path: Path) -> None:
    """[track_d_013 WI-1#7] the DegradeBanner stylesheet passes 0.8; a typo'd token fails it."""
    assert BANNER_CSS.is_file(), f"{BANNER_CSS.relative_to(REPO)} does not exist"
    assert "var(--r3-" in BANNER_CSS.read_text(encoding="utf-8")
    assert _token_lint(REPO) == 0
    shutil.copytree(FE_SRC, tmp_path / "frontend" / "src")
    (tmp_path / "scripts").mkdir()
    shutil.copy2(REPO / "scripts" / "token_ref_whitelist.txt", tmp_path / "scripts" / "token_ref_whitelist.txt")
    assert _token_lint(tmp_path) == 0, "the copied frontend tree alone must already pass"
    seeded = tmp_path / "frontend" / "src" / "components" / "degrade-banner.css"
    seeded.write_text(seeded.read_text(encoding="utf-8") + "\n.x{color:var(--r3-warnnig)}\n", encoding="utf-8")
    assert _token_lint(tmp_path) != 0, "a typo'd token in the banner CSS was not caught"


# ---------------------------------------------------------------------------
# C13.28 / Track-D WI-8 #1-#3
# ---------------------------------------------------------------------------
SKELETON_TS = FE_SRC / "components" / "skeleton.ts"


def _rules(css: str) -> List[tuple]:
    """(media-condition | None, selector, body) for every rule, one level of @media deep."""
    css = re.sub(r"/\*[\s\S]*?\*/", "", css)
    out = []
    i = 0
    while i < len(css):
        m = re.compile(r"@media([^{]*)\{").match(css, i) if css.startswith("@media", i) else None
        if m:
            depth, j = 1, m.end()
            while depth and j < len(css):
                depth += {"{": 1, "}": -1}.get(css[j], 0)
                j += 1
            inner = css[m.end(): j - 1]
            out += [(m.group(1).strip(), s, b) for _, s, b in _rules(inner)]
            i = j
            continue
        m = re.compile(r"([^{}@]+)\{([^{}]*)\}").match(css, i)
        if m:
            out.append((None, m.group(1).strip(), m.group(2)))
            i = m.end()
            continue
        i += 1
    return out


def _decls(body: str) -> Dict[str, str]:
    out = {}
    for part in body.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def skeleton_css_problems(css: str) -> List[str]:
    problems = []
    rules = _rules(css)
    default = [_decls(b) for media, sel, b in rules if media is None and ".r3-skeleton" in sel.split(",")]
    anim = [d.get("animation-name") or d.get("animation", "") for d in default if "animation" in d or "animation-name" in d]
    if not anim or any(a.split()[0] == "none" for a in anim if a):
        problems.append(f"default .r3-skeleton animation missing or none: {anim}")
    reduced = [
        _decls(b) for media, sel, b in rules
        if media and "prefers-reduced-motion" in media and "reduce" in media and ".r3-skeleton" in sel.split(",")
    ]
    if not any(d.get("animation") == "none" or d.get("animation-name") == "none" for d in reduced):
        problems.append("no reduced-motion rule sets .r3-skeleton animation to none")
    if not any(re.fullmatch(r"var\(--r3-surface-sunken\)", d.get("background", d.get("background-color", ""))) for d in reduced):
        problems.append("the reduced-motion rule does not switch to var(--r3-surface-sunken)")
    return problems


@TRACK_D
def test_skeleton_source_has_no_testid() -> None:
    """[track_d_013 WI-8#1] the skeleton component source carries no data-testid."""
    assert SKELETON_TS.is_file(), f"{SKELETON_TS.relative_to(REPO)} does not exist"
    text = SKELETON_TS.read_text(encoding="utf-8")
    assert "testid" not in _strip_ts_comments(text).lower()


@TRACK_D
def test_built_css_stops_the_skeleton_under_reduced_motion() -> None:
    """[track_d_013 WI-8#2] the built CSS has the reduced-motion override (solid sunken surface)."""
    problems = skeleton_css_problems(_entry_css("src/library/index.ts"))
    assert not [p for p in problems if "reduced" in p], problems


@TRACK_D
def test_built_css_animates_the_skeleton_by_default() -> None:
    """[track_d_013 WI-8#3] the default .r3-skeleton rule animates (paired with #2, same build)."""
    problems = skeleton_css_problems(_entry_css("src/library/index.ts"))
    assert not [p for p in problems if "default" in p], problems


@pytest.mark.parametrize(
    ("css", "expected"),
    [
        (".r3-skeleton{animation:r3-pulse 1s infinite}", {"reduced", "surface"}),
        (".r3-skeleton{animation:none}@media (prefers-reduced-motion: reduce){.r3-skeleton{animation:none;background:var(--r3-surface-sunken)}}", {"default"}),
        (".r3-skeleton{animation:r3-pulse 1s infinite}@media (prefers-reduced-motion: reduce){.r3-skeleton{animation:none}}", {"surface"}),
        (".r3-skeleton{animation:r3-pulse 1s infinite}@media (prefers-reduced-motion:reduce){.r3-skeleton{animation:none;background:var(--r3-surface-sunken)}}", set()),
    ],
    ids=["no-override-red", "static-default-red", "gradient-left-red", "complete-green"],
)
def test_skeleton_checker_on_seeds(css: str, expected: set) -> None:
    got = set()
    for p in skeleton_css_problems(css):
        got.add("default" if "default" in p else "surface" if "surface-sunken" in p else "reduced")
    assert got == expected, skeleton_css_problems(css)


# ---------------------------------------------------------------------------
# carried over from WI-11: the banner and toast styles ship with the library page
# ---------------------------------------------------------------------------
def test_banner_and_toast_styles_ship_in_the_library_bundle() -> None:
    css = _entry_css("src/library/index.ts")
    selectors = {s for _, sel, _ in _rules(css) for s in sel.split(",")}
    for needed in (".r3-degrade-banner", ".r3-degrade-banner--warn", ".r3-degrade-banner--danger", ".r3-toast", ".r3-toast-region"):
        assert needed in selectors, f"{needed} is not in the library bundle"
