"""013 WI-9 A9.7 / A9.7a (cases C9.31-C9.33): the §9.2 dead static files are gone.

013 WI-13 acceptance 4 extends it: the classic library UI (`templates/library_classic.html`,
the `READER3_LIBRARY_UI` switch in the server, and `static/search.css`, whose only loader
was the classic template) is gone too.

- C9.31 the seven paths do not exist, the reference scan of executable code and
  templates finds none of the seven basenames, and `CLAUDE.md` no longer names them;
- C9.32 the scan's exclusions are exact: a tmp tree seeded with mentions in every
  excluded location plus one template yields exactly the template;
- C9.33 the 12 class selectors that only the deleted stylesheets defined have zero
  hits in the live style sources, and the checker itself can go red.

Scope of the reference scan (plan WI-9 acceptance 7, ruling 2026-09-24). Excluded as
non-call-sites: ① `specs/_archive/`, ② `docs/` (plan tables, ADR narrative),
③ `designs/**/spec/`, ④ `*.egg-info/` (build output), plus `node_modules/`, `.claude/`
notes and `tests/`. `tests/` is excluded wholesale because test files are not
executable product code; the frozen e2e baseline keeps comments that explain why
`pagination.js` was never loaded, and those are history, not links.

Basename matching is exact on the name: `reader.css` must not match the Vite asset
`reader-C0gMwvDO.css`, and `ai.css` must not match `openai.css`.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "src" / "reader3_app" / "web"
STATIC = WEB / "static"
TEMPLATES = WEB / "templates"
CLASS_LIST = ROOT / "tests" / "fixtures" / "unmatched_classes_9_2.txt"

DEAD_PATHS = [
    "library.css",
    "ai.css",
    "css/notes-panel.css",
    "css/reader.css",
    "css/toc-panel.css",
    "css/toolbar.css",
    "js/pagination.js",
]
BASENAMES = sorted({p.rsplit("/", 1)[-1] for p in DEAD_PATHS})
_NAME_RE = re.compile(
    r"(?<![\w-])(?:" + "|".join(re.escape(b) for b in BASENAMES) + r")(?![\w-])"
)

SCAN_SUFFIXES = {
    ".py", ".js", ".cjs", ".mjs", ".ts", ".html", ".css", ".toml", ".json",
    ".yml", ".yaml", ".txt", ".cfg", ".ini",
}  # fmt: skip
_SKIP_ANYWHERE = {"node_modules", "__pycache__"}
_SKIP_AT_ROOT = {"tests", "docs"}


def _excluded_dir(rel_parts: tuple[str, ...]) -> bool:
    name = rel_parts[-1]
    if name.startswith(".") and not (len(rel_parts) == 1 and name == ".github"):
        return True  # .git, .venv, .claude, caches; .github at the root is scanned
    if name in _SKIP_ANYWHERE:
        return True
    if len(rel_parts) == 1 and name in _SKIP_AT_ROOT:
        return True
    if name.endswith(".egg-info"):
        return True
    if rel_parts[:2] == ("specs", "_archive"):
        return True
    if rel_parts[0] == "designs" and name == "spec":
        return True
    return False


def count_references(root: Path, pattern: re.Pattern[str] = _NAME_RE) -> dict[str, int]:
    """Per-file count of `pattern` (default: the seven basenames) in executable code and templates."""
    hits: dict[str, int] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath).relative_to(root)
        dirnames[:] = sorted(
            d for d in dirnames if not _excluded_dir(tuple((base / d).parts))
        )
        for fn in sorted(filenames):
            if Path(fn).suffix not in SCAN_SUFFIXES:
                continue
            path = Path(dirpath) / fn
            text = path.read_text(encoding="utf-8", errors="replace")
            n = len(pattern.findall(text))
            if n:
                hits[(base / fn).as_posix()] = n
    return hits


_STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.DOTALL | re.IGNORECASE)


def live_style_text(static: Path, templates: Path) -> str:
    """The live style sources named by acceptance 7a, concatenated."""
    parts = [
        (static / "dedao-theme.css").read_text(encoding="utf-8"),
        (static / "css" / "annotations.css").read_text(encoding="utf-8"),
    ]
    # 013 WI-12 deleted static/settings.css (its rules moved to the settings TS entry).
    if (static / "settings.css").is_file():
        parts.append((static / "settings.css").read_text(encoding="utf-8"))
    for name in ("reader.html", "library.html", "settings.html"):
        html = (templates / name).read_text(encoding="utf-8")
        parts.extend(_STYLE_BLOCK.findall(html))
    return "\n".join(parts)


def class_hits(css: str, cls: str) -> int:
    """Word-bounded class-selector hits: `.chat-msg` does not count `.chat-msg-role`."""
    return len(re.findall(r"(?<![\w-])\." + re.escape(cls) + r"(?![\w-])", css))


def _load_class_list() -> list[tuple[str, str]]:
    rows = []
    for line in CLASS_LIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        src, cls = line.split()
        rows.append((src, cls))
    return rows


# --- C9.31 -------------------------------------------------------------------


@pytest.mark.parametrize("rel", DEAD_PATHS)
def test_dead_path_absent(rel: str) -> None:
    assert not (STATIC / rel).exists(), f"static/{rel} should be deleted (§9.2)"


def test_no_references_in_executable_code() -> None:
    assert count_references(ROOT) == {}


def test_claude_md_has_no_references() -> None:
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert _NAME_RE.findall(text) == []


# --- C9.32 -------------------------------------------------------------------


def test_scan_exclusions_exact(tmp_path: Path) -> None:
    seeds = {
        # the four plan exclusions
        "specs/_archive/001/old.html": '<link href="/static/library.css">',
        "docs/plans/x/table.py": "# static/js/pagination.js",
        "designs/reader-pro-next/spec/s.js": "// pagination.js not loaded",
        "src/reader3_app.egg-info/SOURCES.txt": "src/reader3_app/web/static/ai.css",
        # the extra non-call-site exclusions
        "tests/unit/test_x.py": "# css/reader.css",
        "node_modules/pkg/index.js": "require('toolbar.css')",
        ".claude/notes.json": '{"f": "toc-panel.css"}',
        # near-misses that must not count
        "src/reader3_app/web/static/dist/assets/reader-C0gMwvDO.css": "a{}",
        "src/reader3_app/web/static/dist/manifest.json": '{"f": "assets/reader-C0gMwvDO.css"}',
        "src/reader3_app/web/static/openai.js": "load('openai.css'); load('my-library.css')",
        # the one real call site
        "src/reader3_app/web/templates/t.html": '<link href="/static/library.css">',
    }
    for rel, body in seeds.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    assert count_references(tmp_path) == {"src/reader3_app/web/templates/t.html": 1}


def test_scan_counts_nested_tests_and_docs_dirs(tmp_path: Path) -> None:
    """Only root-level `tests/` and `docs/` are exempt, not any directory so named."""
    p = tmp_path / "src" / "reader3_app" / "docs" / "x.py"
    p.parent.mkdir(parents=True)
    p.write_text("'js/pagination.js' 'css/toolbar.css'", encoding="utf-8")
    gh = tmp_path / ".github" / "workflows" / "ci.yml"
    gh.parent.mkdir(parents=True)
    gh.write_text("run: cat static/ai.css", encoding="utf-8")
    assert count_references(tmp_path) == {
        ".github/workflows/ci.yml": 1,
        "src/reader3_app/docs/x.py": 2,
    }


# --- C9.33 -------------------------------------------------------------------


def test_class_list_is_the_twelve() -> None:
    rows = _load_class_list()
    assert len(rows) == 12
    assert len({c for _, c in rows}) == 12
    assert sum(1 for s, _ in rows if s == "library.css") == 10
    assert sum(1 for s, _ in rows if s == "ai.css") == 2


@pytest.mark.parametrize("cls", [c for _, c in _load_class_list()])
def test_unmatched_class_has_no_live_hit(cls: str) -> None:
    assert class_hits(live_style_text(STATIC, TEMPLATES), cls) == 0


def test_class_checker_goes_red_on_seeded_source(tmp_path: Path) -> None:
    static, templates = tmp_path / "static", tmp_path / "templates"
    (static / "css").mkdir(parents=True)
    templates.mkdir()
    (static / "dedao-theme.css").write_text(".app-titles{} .x-app-title{}", encoding="utf-8")
    (static / "css" / "annotations.css").write_text(".chat-msg-role{}", encoding="utf-8")
    (static / "settings.css").write_text("", encoding="utf-8")
    (templates / "reader.html").write_text(
        '<div class="app-title"></div><style>.nav .app-title{color:red}</style>',
        encoding="utf-8",
    )
    (templates / "library.html").write_text(
        "<script>q('.chat-msg')</script><style>.chat-msg,.ai-msg:hover{}</style>",
        encoding="utf-8",
    )
    (templates / "settings.html").write_text("", encoding="utf-8")
    css = live_style_text(static, templates)
    # word-bounded: .app-titles / .x-app-title / class="app-title" do not count
    assert class_hits(css, "app-title") == 1
    # .chat-msg-role does not count for .chat-msg; the <script> is not a style block
    assert class_hits(css, "chat-msg") == 1
    assert class_hits(css, "ai-msg") == 1
    assert class_hits(css, "ai-citations") == 0


# --- WI-13 acceptance 4: the classic library UI --------------------------------

CLASSIC_PATHS = [
    TEMPLATES / "library_classic.html",
    STATIC / "search.css",
]
_SEARCH_CSS_RE = re.compile(r"(?<![\w-])search\.css(?![\w-])")
_ENV_SWITCH = "READER3_LIBRARY_UI"


@pytest.mark.parametrize("path", CLASSIC_PATHS, ids=lambda p: p.name)
def test_classic_ui_file_absent(path: Path) -> None:
    assert not path.exists(), f"{path.relative_to(ROOT)} should be deleted (WI-13)"


def test_no_search_css_references_in_executable_code() -> None:
    """Same scan and exclusions as C9.31; `build/` (gitignored setuptools output) is skipped too."""
    hits = {k: v for k, v in count_references(ROOT, _SEARCH_CSS_RE).items() if not k.startswith("build/")}
    assert hits == {}


def test_library_ui_env_switch_gone_from_src_and_claude_md() -> None:
    src = ROOT / "src"
    hits = {}
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != "__pycache__" and not d.endswith(".egg-info")]
        for fn in filenames:
            path = Path(dirpath) / fn
            if path.suffix in {".pyc", ".png", ".jpg", ".woff", ".woff2", ".epub"}:
                continue
            n = path.read_text(encoding="utf-8", errors="replace").count(_ENV_SWITCH)
            if n:
                hits[path.relative_to(ROOT).as_posix()] = n
    n = (ROOT / "CLAUDE.md").read_text(encoding="utf-8").count(_ENV_SWITCH)
    if n:
        hits["CLAUDE.md"] = n
    assert hits == {}


def test_server_has_no_classic_template_switch() -> None:
    from reader3_app.web import server

    assert not hasattr(server, "_library_ui_mode")
    assert not hasattr(server, "_library_template_name")


def test_search_css_scan_goes_red_on_seeded_call_site(tmp_path: Path) -> None:
    seeds = {
        "docs/plans/x/table.py": "# static/search.css",
        "src/reader3.egg-info/SOURCES.txt": "static/search.css",
        "src/reader3_app/web/static/library-search.css": "a{}",
        "src/reader3_app/web/templates/t.html": '<link href="/static/search.css">',
    }
    for rel, body in seeds.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    assert count_references(tmp_path, _SEARCH_CSS_RE) == {"src/reader3_app/web/templates/t.html": 1}
