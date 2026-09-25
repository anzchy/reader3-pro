"""013 WI-9 A9.6 / A9.6a1 / A9.6a2 / A9.6a3 / A9.6c / A9.6-src: the inline-HTML lint.

`scripts/lint_inline_html.py --root <dir>` scans `<root>/src/reader3_app/web/templates/*.html`:

* **style count** = for every `<style>` block, `end_line - start_line` of the block (the
  plan's §9.1 / a1 unit: reader 1403, library 1075, library_classic 10), floored at 1 so a
  one-line `<style>…</style>` still counts, **plus** one per `style=` attribute (a1 / c).
* **script count** = `<script>` elements without `src` (the `src` bullet under #6), minus at
  most one per template whose body's sha256 is the registered FOUC hash (D7, a3).

Both are compared with `scripts/inline_html_allowlist.json` for **equality**: above the
entry fails (`3 > 2`), below it fails too (the entry must be lowered in the same change —
an entry with slack is a licence to grow back). Unlisted templates are allowed 0.
Cases: C9.07, C9.08 (D7-B), C9.09, C9.10, C10.24 (D7-B rows).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import contract_lints as cl

TEMPLATES = cl.REPO_ROOT / cl.TEMPLATES_REL

#: PLAN :812 (a1) — `<style` lines + `style="` attributes, measured 2026-08-23, re-measured
#: 2026-09-24 on the unmodified templates.
#: 013 WI-13 deleted `library_classic.html` together with its allowlist entry (was 13).
#: 013 WI-12 moved settings.html's 2 inline styles into the settings entry CSS (entry removed; 0 = unlisted).
#: 013 WI-13 moved library.html's 1077 inline style lines into the library entry CSS (entry
#: removed; 0 = unlisted). SEPARATION-BROKEN by design: the fixture tracks the allowlist.
INITIAL_STYLE = {"reader.html": 1405}
#: PLAN :813 (a2) — non-`src`, non-FOUC inline scripts. library/settings are 0.
INITIAL_SCRIPT = {"reader.html": 3}

FOUC_BODY = "\n  (function(){var d=document.documentElement;d.dataset.theme='light';})();\n"


@pytest.fixture(scope="module")
def lint():
    return cl.load(cl.INLINE_LINT, "lint_inline_html_under_test")


def _tree(root: Path, templates: dict, style=None, script=None) -> Path:
    for name, body in templates.items():
        cl.write(root, f"{cl.TEMPLATES_REL}/{name}", body)
    cl.write(
        root,
        cl.INLINE_ALLOWLIST_REL,
        json.dumps({"style": style or {}, "script": script or {}}, indent=2) + "\n",
    )
    return root


def _page(inner: str) -> str:
    return f"<!doctype html>\n<html>\n<head>\n<title>t</title>\n</head>\n<body>\n{inner}\n</body>\n</html>\n"


# ---------------------------------------------------------------------------
# C9.07 / C9.08: the committed allowlist records today's measured values exactly
# ---------------------------------------------------------------------------
def test_initial_style_allowlist_covers_all_four_templates(lint) -> None:
    data = json.loads((cl.REPO_ROOT / cl.INLINE_ALLOWLIST_REL).read_text(encoding="utf-8"))
    assert data["style"] == INITIAL_STYLE
    measured = {p.name: lint.count_template(p.read_text(encoding="utf-8"))[0] for p in sorted(TEMPLATES.glob("*.html"))}
    assert {k: v for k, v in measured.items() if v} == INITIAL_STYLE


def test_initial_script_allowlist(lint) -> None:
    data = json.loads((cl.REPO_ROOT / cl.INLINE_ALLOWLIST_REL).read_text(encoding="utf-8"))
    assert data["script"] == INITIAL_SCRIPT
    measured = {p.name: lint.count_template(p.read_text(encoding="utf-8"))[1] for p in sorted(TEMPLATES.glob("*.html"))}
    assert measured == {"reader.html": 3, "library.html": 0, "settings.html": 0}


def test_real_tree_passes(lint) -> None:
    rc, out = cl.call_main(lint, ["--root", str(cl.REPO_ROOT)])
    assert rc == 0, out


def test_allowlist_file_has_only_the_two_sections(lint) -> None:
    data = json.loads((cl.REPO_ROOT / cl.INLINE_ALLOWLIST_REL).read_text(encoding="utf-8"))
    assert set(data) == {"style", "script"}
    for section in data.values():
        assert all(isinstance(v, int) and v > 0 for v in section.values()), section


# ---------------------------------------------------------------------------
# C9.10: tolerance 0 in both directions
# ---------------------------------------------------------------------------
def test_over_allowlist_fails_with_tolerance_zero(lint, tmp_path: Path) -> None:
    two = _page('<p style="a"></p>\n<p style="b"></p>')
    _tree(tmp_path, {"settings.html": two}, style={"settings.html": 2})
    rc, out = cl.call_main(lint, ["--root", str(tmp_path)])
    assert rc == 0, out

    three = _page('<p style="a"></p>\n<p style="b"></p>\n<p style="c"></p>')
    _tree(tmp_path, {"settings.html": three}, style={"settings.html": 2})
    rc, out = cl.call_main(lint, ["--root", str(tmp_path)])
    assert rc == 1, out
    assert cl.lines_matching(out, ["settings.html", "3 > 2"]), out


def test_below_allowlist_fails_until_entry_lowered(lint, tmp_path: Path) -> None:
    _tree(tmp_path, {"settings.html": _page('<p style="a"></p>')}, style={"settings.html": 2})
    rc, out = cl.call_main(lint, ["--root", str(tmp_path)])
    assert rc == 1, out
    assert cl.lines_matching(out, ["settings.html", "1 < 2"]), out


def test_unlisted_template_is_allowed_zero(lint, tmp_path: Path) -> None:
    _tree(tmp_path, {"library.html": _page("<style>.a{}</style>")})
    rc, out = cl.call_main(lint, ["--root", str(tmp_path)])
    assert rc == 1, out
    assert cl.lines_matching(out, ["library.html", "1 > 0"]), out


def test_entry_for_missing_template_is_dangling(lint, tmp_path: Path) -> None:
    _tree(tmp_path, {"settings.html": _page("")}, style={"library_classic.html": 13})
    rc, out = cl.call_main(lint, ["--root", str(tmp_path)])
    assert rc == 1, out
    assert cl.lines_matching(out, ["library_classic.html", "no such template"]), out


def test_no_templates_at_all_is_a_failure(lint, tmp_path: Path) -> None:
    _tree(tmp_path, {})
    rc, out = cl.call_main(lint, ["--root", str(tmp_path)])
    assert rc != 0, out


# ---------------------------------------------------------------------------
# counting unit (a1 / c / src bullet)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("markup", "style", "script"),
    [
        ("<style>\n.a{}\n.b{}\n</style>", 3, 0),  # end_line - start_line
        ("<style>.a{}</style>", 1, 0),  # one-line block still counts
        ("<STYLE media='x'>.a{}</STYLE>", 1, 0),
        ('<div style="color:red"></div>', 1, 0),
        ("<div style='color:red'></div>", 1, 0),
        ('<div\n  class="x"\n  style = "a"></div>', 1, 0),
        ('<div data-style="a"></div>', 0, 0),
        ("<script>var a = 1;</script>", 0, 1),
        ('<script type="module">var a = 1;</script>', 0, 1),
        ('<script src="/a.js"></script>', 0, 0),
        ("<script defer src='/a.js'></script>", 0, 0),
        ('<script>el.style = "x"; el.style.color = "red";</script>', 0, 1),
    ],
)
def test_count_unit(lint, markup: str, style: int, script: int) -> None:
    assert lint.count_template(_page(markup)) == (style, script)


# ---------------------------------------------------------------------------
# C9.09: counting is additive under injection
# ---------------------------------------------------------------------------
_BASE_TEXTS = {p.name: p.read_text(encoding="utf-8") for p in sorted(TEMPLATES.glob("*.html"))}
_SPAN_RE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.S | re.I)
_ANCHOR_RE = re.compile(r"<(?:div|body|main|header|section|nav|aside|button|p)\b", re.I)


def _safe_offsets(text: str) -> list:
    spans = [m.span() for m in _SPAN_RE.finditer(text)]
    return [m.start() for m in _ANCHOR_RE.finditer(text) if not any(a <= m.start() < b for a, b in spans)]


_OFFSETS = {name: _safe_offsets(text) for name, text in _BASE_TEXTS.items()}


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    name=st.sampled_from(sorted(_BASE_TEXTS)),
    k_style=st.integers(0, 5),
    k_attr_dq=st.integers(0, 3),
    k_attr_sq=st.integers(0, 2),
    k_src=st.integers(0, 3),
    k_inline=st.integers(0, 3),
    data=st.data(),
)
def test_counting_is_additive_under_injection(lint, name, k_style, k_attr_dq, k_attr_sq, k_src, k_inline, data) -> None:
    text = _BASE_TEXTS[name]
    offsets = _OFFSETS[name]
    assert offsets, f"{name}: no injection points"
    base_style, base_script = lint.count_template(text)
    pieces = (
        ["<style>.q{}</style>"] * k_style
        + ['<i style="x"></i>'] * k_attr_dq
        + ["<i style='x'></i>"] * k_attr_sq
        + ['<script src="/q.js"></script>'] * k_src
        + ["<script>var q = 1;</script>"] * k_inline
    )
    chosen = sorted((data.draw(st.sampled_from(offsets)) for _ in pieces), reverse=True)
    mutated = text
    for off, piece in zip(chosen, pieces):
        mutated = mutated[:off] + piece + mutated[off:]
    assert lint.count_template(mutated) == (base_style + k_style + k_attr_dq + k_attr_sq, base_script + k_inline)


# ---------------------------------------------------------------------------
# D7 / a3: FOUC exemption by body sha256 (C10.24 under D7-B)
# ---------------------------------------------------------------------------
def _fouc_hash() -> str:
    return hashlib.sha256(FOUC_BODY.encode("utf-8")).hexdigest()


@pytest.mark.parametrize(("fouc_copies", "expected"), [(0, 1), (1, 1), (2, 2)])
def test_fouc_exempt_at_most_once_per_template(lint, fouc_copies: int, expected: int) -> None:
    head = "".join(f"<script>{FOUC_BODY}</script>\n" for _ in range(fouc_copies))
    text = _page(head + "<script>var other = 1;</script>")
    assert lint.count_template(text, frozenset({_fouc_hash()}))[1] == expected


def test_fouc_one_byte_different_is_counted(lint) -> None:
    near = FOUC_BODY.replace("light", "lighT")
    assert lint.count_template(_page(f"<script>{near}</script>"), frozenset({_fouc_hash()}))[1] == 1
    assert lint.count_template(_page(f"<script>{FOUC_BODY}</script>"), frozenset({_fouc_hash()}))[1] == 0


def test_fouc_exempt_through_cli(lint, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(lint, "FOUC_SHA256", frozenset({_fouc_hash()}))
    page = _page(f"<script>{FOUC_BODY}</script>")
    _tree(tmp_path, {"settings.html": page, "library.html": page})
    rc, out = cl.call_main(lint, ["--root", str(tmp_path)])
    assert rc == 0, out

    _tree(tmp_path, {"settings.html": _page(f"<script>{FOUC_BODY} </script>"), "library.html": page})
    rc, out = cl.call_main(lint, ["--root", str(tmp_path)])
    assert rc == 1, out
    assert cl.lines_matching(out, ["settings.html", "script", "1 > 0"]), out


def test_fouc_registration_is_at_most_one_hash(lint, tmp_path: Path, monkeypatch) -> None:
    assert len(lint.FOUC_SHA256) <= 1
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in lint.FOUC_SHA256)
    monkeypatch.setattr(lint, "FOUC_SHA256", frozenset({"a" * 64, "b" * 64}))
    _tree(tmp_path, {"settings.html": _page("")})
    rc, out = cl.call_main(lint, ["--root", str(tmp_path)])
    assert rc != 0, out
    assert "FOUC" in out
