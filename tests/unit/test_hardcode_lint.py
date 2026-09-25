"""013 WI-9 A9.11a–e: the token hardcode lint (§9.3) and its fingerprint ratchet.

`node scripts/lint_hardcode.mjs --root <dir> [--json]` runs stylelint +
`stylelint-declaration-strict-value` + `postcss-html` over
`frontend/src/**/*.css`, `templates/*.html` and the live `static/**/*.css`, adds a
`--r3-*`-only namespace rule, and compares the violation fingerprints
(`file:selector:property`, no line numbers) with `scripts/hardcode_baseline.json`
(`{file: ["selector:property", ...]}`): anything new fails, anything stale fails.

`--json` prints `{"new": [...], "stale": [...], "suppressions": [...], "fingerprints": [...]}`
with full `file:selector:property` strings, so the ratchet is asserted on the exact set.

Seeds go into a tmp copy of `frontend/src` (C9.12 / C9.41 / C9.13) or a tmp root (C9.14).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import contract_lints as cl


@pytest.fixture()
def fe(tmp_path: Path) -> Path:
    return cl.copy_frontend_src(tmp_path / "root")


def _assert_seed_red_then_green(root: Path, rel: str, css: str, prop: str) -> None:
    seed = cl.write(root, rel, css)
    rc, report = cl.hardcode_json(root)
    assert rc != 0, report
    name = Path(rel).name
    assert any(name in f and f.endswith(f":{prop}") for f in report["new"]), report["new"]
    seed.unlink()
    rc, report = cl.hardcode_json(root)
    assert rc == 0, report


# ---------------------------------------------------------------------------
# today's tree
# ---------------------------------------------------------------------------
def test_real_tree_passes_with_recorded_baseline() -> None:
    proc = cl.run_hardcode(cl.REPO_ROOT)
    assert proc.returncode == 0, cl.fh.describe(proc)


def test_real_tree_is_not_an_empty_run() -> None:
    rc, report = cl.hardcode_json(cl.REPO_ROOT)
    assert rc == 0, report
    files = {f.split(":", 1)[0] for f in report["fingerprints"]}
    # the templates' inline blocks and the live static css are the bulk of the baseline
    # (013 WI-13: library.html has no inline styles left, so it no longer contributes)
    assert {
        "src/reader3_app/web/templates/reader.html",
        "src/reader3_app/web/static/dedao-theme.css",
    } <= files, sorted(files)
    assert report["new"] == [] and report["stale"] == [] and report["suppressions"] == []


def test_fingerprints_equal_baseline_on_real_tree() -> None:
    rc, report = cl.hardcode_json(cl.REPO_ROOT)
    baseline = cl.read_baseline(cl.REPO_ROOT)
    as_set = {f"{k}:{e}" for k, v in baseline.items() for e in v}
    assert set(report["fingerprints"]) == as_set


# ---------------------------------------------------------------------------
# C9.12: A9.11a / b / c
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("css", "prop"),
    [
        (".x{color:#ff0000;}", "color"),  # A9.11a
        (".x{border-radius:23px;}", "border-radius"),  # A9.11b
        (".x{color:var(--dedao-orange);}", "color"),  # A9.11c
    ],
    ids=["a-hex", "b-radius", "c-dedao-namespace"],
)
def test_seeded_counter_examples_fail_then_pass(fe: Path, css: str, prop: str) -> None:
    _assert_seed_red_then_green(fe, "frontend/src/seed.css", css, prop)


# ---------------------------------------------------------------------------
# C9.41: every §9.3 class, and the namespace rule is an allowlist
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("css", "prop"),
    [
        (".x{gap:8px}", "gap"),
        (".x{padding:13px}", "padding"),
        (".x{margin:7px}", "margin"),
        (".x{padding-top:3px}", "padding-top"),
        (".x{font-size:15px}", "font-size"),
        (".x{line-height:1.37}", "line-height"),
        (".x{width:237px}", "width"),
        (".x{min-height:41px}", "min-height"),
        (".x{z-index:30}", "z-index"),
        (".x{transition-duration:.2s}", "transition-duration"),
        (".x{opacity:.6}", "opacity"),
        (".x{background:rgba(0,0,0,.1)}", "background"),
        (".x{border:1px solid #eee}", "border"),
        (".x{color:var(--legacy-orange)}", "color"),
        (".x{color:var(--p-blue-500)}", "color"),
    ],
)
def test_every_value_class_is_caught(fe: Path, css: str, prop: str) -> None:
    _assert_seed_red_then_green(fe, "frontend/src/components/seed.css", css, prop)


@pytest.mark.parametrize(
    "css",
    [
        ".x{gap:var(--r3-space-2)}",
        ".x{padding:0 var(--r3-space-2)}",
        ".x{width:100%;height:50%;margin:0;opacity:1;opacity:0}",
        ".x{height:auto;line-height:normal;font-size:inherit}",
        ".x{border:1px solid var(--r3-border)}",
    ],
)
def test_legitimate_values_pass(fe: Path, css: str) -> None:
    cl.write(fe, "frontend/src/components/ok.css", css)
    rc, report = cl.hardcode_json(fe)
    assert rc == 0, report


# ---------------------------------------------------------------------------
# C9.13: fingerprint ignores line moves, includes the file
# ---------------------------------------------------------------------------
@settings(max_examples=8, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(pad=st.lists(st.sampled_from(["", "/* note */", "   "]), min_size=1, max_size=50))
def test_fingerprint_ignores_line_position(tmp_path_factory, pad) -> None:
    root = tmp_path_factory.mktemp("c913")
    cl.write(root, "frontend/src/a.css", "\n".join(pad) + "\n.x{color:#123456}\n")
    cl.write_baseline(root, {"frontend/src/a.css": [".x:color"]})
    rc, report = cl.hardcode_json(root)
    assert rc == 0, report
    assert report["fingerprints"] == ["frontend/src/a.css:.x:color"]


def test_fingerprint_includes_the_file(tmp_path: Path) -> None:
    cl.write(tmp_path, "frontend/src/a.css", ".x{}\n")
    cl.write(tmp_path, "frontend/src/b.css", ".x{color:#123456}\n")
    cl.write_baseline(tmp_path, {"frontend/src/a.css": [".x:color"]})
    rc, report = cl.hardcode_json(tmp_path)
    assert rc != 0
    assert report["new"] == ["frontend/src/b.css:.x:color"]
    assert report["stale"] == ["frontend/src/a.css:.x:color"]
    proc = cl.run_hardcode(tmp_path)
    assert "frontend/src/b.css:.x:color" in proc.stdout


def test_selector_includes_at_rule_context(tmp_path: Path) -> None:
    cl.write(tmp_path, "frontend/src/a.css", "@media (max-width: 767px) {\n  .x { gap: 8px; }\n}\n")
    cl.write_baseline(tmp_path, {})
    rc, report = cl.hardcode_json(tmp_path)
    assert rc != 0
    assert report["new"] == ["frontend/src/a.css:@media (max-width: 767px) .x:gap"]


def test_template_style_block_and_attribute_are_scanned(tmp_path: Path) -> None:
    cl.write(
        tmp_path,
        f"{cl.TEMPLATES_REL}/t.html",
        '<html><head><style>\n.y { z-index: 9; }\n</style></head><body><p style="gap: 3px"></p></body></html>\n',
    )
    cl.write_baseline(tmp_path, {})
    rc, report = cl.hardcode_json(tmp_path)
    assert rc != 0
    assert sorted(report["new"]) == sorted(
        [f"{cl.TEMPLATES_REL}/t.html:.y:z-index", f"{cl.TEMPLATES_REL}/t.html:[style]:gap"]
    )


# ---------------------------------------------------------------------------
# C9.14: A9.11e — file-granular whitelist, no suppression anywhere
# ---------------------------------------------------------------------------
def test_real_baseline_is_file_granular_and_suppression_free() -> None:
    baseline = cl.read_baseline(cl.REPO_ROOT)
    assert baseline, "baseline must record today's violations"
    for key, entries in baseline.items():
        assert re.fullmatch(r"[^:*?\[\]]+", key), key
        assert (cl.REPO_ROOT / key).is_file(), key
        assert isinstance(entries, list) and entries == sorted(set(entries)), key
    raw = (cl.REPO_ROOT / cl.HARDCODE_BASELINE_REL).read_text(encoding="utf-8")
    # 只查抑制指令本身：`:disabled` / `.disabled` 是真实选择器，会出现在指纹里。
    assert "stylelint-disable" not in raw


@pytest.mark.parametrize(
    ("rel", "body", "needles"),
    [
        (".stylelintrc.json", json.dumps({"ignoreFiles": ["frontend/src/library/**"]}), [".stylelintrc.json", "ignoreFiles"]),
        (
            "stylelint.config.mjs",
            'export default { overrides: [{ files: ["frontend/src/settings/**"], '
            'rules: { "scale-unlimited/declaration-strict-value": null } }] };\n',
            ["stylelint.config.mjs", "overrides"],
        ),
        (".stylelintignore", "frontend/src/shared/\n", [".stylelintignore"]),
        ("frontend/src/x.css", "/* stylelint-disable */\n.x{}\n", ["frontend/src/x.css", "stylelint-disable"]),
        ("frontend/src/y.ts", "// stylelint-disable-next-line\nexport {};\n", ["frontend/src/y.ts", "stylelint-disable"]),
        (
            "package.json",
            json.dumps({"name": "x", "stylelint": {"ignoreFiles": ["frontend/**"]}}),
            ["package.json", "ignoreFiles"],
        ),
    ],
    ids=["s1-ignoreFiles", "s2-overrides", "s3-stylelintignore", "s4-disable-css", "s4-disable-ts", "pkg-key"],
)
def test_suppression_seeds_fail(fe: Path, rel: str, body: str, needles) -> None:
    cl.write(fe, rel, body)
    rc, report = cl.hardcode_json(fe)
    assert rc != 0, report
    assert any(all(n in s for n in needles) for s in report["suppressions"]), report["suppressions"]


def test_glob_whitelist_entry_fails(fe: Path) -> None:
    cl.write_baseline(fe, {"frontend/src/**": [".x:gap"]})
    rc, report = cl.hardcode_json(fe)
    assert rc != 0, report
    assert any("frontend/src/**" in s for s in report["suppressions"]), report


@pytest.mark.parametrize(
    ("rel", "body"),
    [
        (".stylelintrc.json", json.dumps({"ignoreFiles": ["frontend/src/library/**"]})),
        (".stylelintignore", "frontend/src/library/\n"),
        ("frontend/src/library/seed.css", "/* stylelint-disable */\n"),
    ],
    ids=["ignoreFiles", "stylelintignore", "disable-comment"],
)
def test_suppression_does_not_hide_the_violation(fe: Path, rel: str, body: str) -> None:
    """The ratchet runs with its own inline config and `ignoreDisables`: a seeded
    suppression is reported *and* inert — the violation behind it is still found."""
    cl.write(fe, rel, body)
    seed = fe / "frontend/src/library/seed.css"
    prior = seed.read_text(encoding="utf-8") if seed.exists() else ""
    cl.write(fe, "frontend/src/library/seed.css", prior + "\n.x{gap:8px}\n")
    rc, report = cl.hardcode_json(fe)
    assert rc != 0
    assert "frontend/src/library/seed.css:.x:gap" in report["new"], report


# ---------------------------------------------------------------------------
# 013 WI-12 A12.9 / C12.10: the settings page is off the whitelist
# ---------------------------------------------------------------------------
def test_whitelist_excludes_settings() -> None:
    baseline = cl.read_baseline(cl.REPO_ROOT)
    settings_keys = sorted(k for k in baseline if Path(k).name in ("settings.html", "settings.css"))
    assert settings_keys == [], f"settings entries still whitelisted: {settings_keys}"
    rc, report = cl.hardcode_json(cl.REPO_ROOT)
    assert rc == 0, report
    settings_hits = sorted(f for f in report["fingerprints"] if "/settings" in f.split(":", 1)[0])
    assert settings_hits == [], settings_hits
