"""013 WI-9 A9.3 / A9.6a / A9.11e (C9.06, C9.40): `npm run lint:contracts` is one command
running every contract check, OR-ed, no short-circuit.

Checks, in order: selector, naming, token-ref, inline-html, hardcode (+ its suppression
scan), allowlist-monotone, depcruise. The command prints `== <check> ==` before each and
ends with `lint:contracts: OK (…)` or `lint:contracts: FAIL <a>, <b>`; the failing set is
asserted **exactly**, so a seed that trips the wrong check (or none) is caught.

Every run is against a tmp git repo holding a copy of the scanned tree
(`contract_lints.copy_scanned_tree`), tagged `base`; seeds go in a second commit.
`--base-ref` feeds the monotone guard; without it the base is
`git merge-base HEAD origin/master`, and an unresolvable base fails closed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List

import pytest

import contract_lints as cl

SETTINGS_REL = f"{cl.TEMPLATES_REL}/settings.html"


def _append(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.write_text(p.read_text(encoding="utf-8") + text, encoding="utf-8")


def _insert_before_body_end(root: Path, rel: str, text: str) -> None:
    p = root / rel
    body = p.read_text(encoding="utf-8")
    assert "</body>" in body
    p.write_text(body.replace("</body>", text + "\n</body>", 1), encoding="utf-8")


def seed_selector(root: Path) -> None:
    cl.write(root, "tests/e2e/x_test.py", 'def test_x(page):\n    page.locator(".foo").click()\n')


def seed_naming(root: Path) -> None:
    _insert_before_body_end(root, SETTINGS_REL, '<span data-testid="reader-x"></span>')


def seed_token_ref(root: Path) -> None:
    cl.write(root, "frontend/src/tokref.css", ".t { color: var(--r3-nonexistent); }\n")


def seed_inline_html(root: Path) -> None:
    _insert_before_body_end(root, SETTINGS_REL, "<style></style>")


def seed_hardcode(root: Path) -> None:
    cl.write(root, "frontend/src/x.css", ".x { color: #ff0000; }\n")


def seed_allowlist_growth(root: Path) -> None:
    # settings 2 -> 3, with the template padded to 3 so the inline lint itself passes.
    _insert_before_body_end(root, SETTINGS_REL, '<i style=""></i>')
    cl.edit_json(root, cl.INLINE_ALLOWLIST_REL, lambda d: d["style"].__setitem__("settings.html", 3))


def seed_whitelist_growth(root: Path) -> None:
    # One extra baseline entry, with a matching violation so the ratchet itself passes.
    cl.write(root, "frontend/src/extra.css", ".x { color: #ff0000; }\n")
    cl.edit_json(root, cl.HARDCODE_BASELINE_REL, lambda d: d.__setitem__("frontend/src/extra.css", [".x:color"]))


SEEDS: Dict[str, Callable[[Path], None]] = {
    "selector": seed_selector,
    "naming": seed_naming,
    "token-ref": seed_token_ref,
    "inline-html": seed_inline_html,
    "hardcode": seed_hardcode,
    "allowlist-growth": seed_allowlist_growth,
    "whitelist-growth": seed_whitelist_growth,
}
EXPECTED: Dict[str, List[str]] = {
    "selector": ["selector"],
    "naming": ["naming"],
    "token-ref": ["token-ref"],
    "inline-html": ["inline-html"],
    "hardcode": ["hardcode"],
    "allowlist-growth": ["allowlist-monotone"],
    "whitelist-growth": ["allowlist-monotone"],
}


#: 013 WI-12 left settings.html with 0 inline styles and no allowlist entry. The C9.40 cases
#: below grow / shrink that page from a base of 2, so the scratch copy (never the real tree)
#: is padded back to 2 empty inline styles and a matching entry before the base commit.
#: `<b>` rather than `<i>`: `_set_settings` counts its own `<i style="">` padding.
BASE_SETTINGS_STYLES = 2


def _pad_settings_base(root: Path) -> None:
    p = root / SETTINGS_REL
    body = p.read_text(encoding="utf-8")
    p.write_text(body.replace("</body>", '<b style=""></b>' * BASE_SETTINGS_STYLES + "</body>", 1), encoding="utf-8")
    cl.edit_json(root, cl.INLINE_ALLOWLIST_REL, lambda d: d["style"].__setitem__("settings.html", BASE_SETTINGS_STYLES))


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = cl.copy_scanned_tree(tmp_path / "repo")
    _pad_settings_base(root)
    return cl.init_repo(root)


def test_script_is_wired_in_package_json() -> None:
    import json

    pkg = json.loads((cl.REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    assert "scripts/lint_contracts.py" in pkg["scripts"]["lint:contracts"]


def test_clean_copy_passes_and_runs_every_check(repo: Path) -> None:
    before = cl.repo_status()
    proc = cl.run_contracts(repo)
    assert proc.returncode == 0, cl.fh.describe(proc)
    assert cl.failed_checks(proc.stdout) is None
    for name in cl.CONTRACT_CHECKS:
        assert f"== {name} ==" in proc.stdout, name
    assert cl.repo_status() == before


@pytest.mark.parametrize("seed", sorted(SEEDS))
def test_each_check_fails_command(repo: Path, seed: str) -> None:
    SEEDS[seed](repo)
    cl.commit_all(repo, f"seed {seed}")
    proc = cl.run_contracts(repo)
    assert proc.returncode != 0, cl.fh.describe(proc)
    assert cl.failed_checks(proc.stdout) == EXPECTED[seed], cl.fh.describe(proc)


def test_all_seeds_report_every_check(repo: Path) -> None:
    for seed in SEEDS.values():
        seed(repo)
    cl.commit_all(repo, "all seeds")
    proc = cl.run_contracts(repo)
    assert proc.returncode != 0
    expected = sorted({c for v in EXPECTED.values() for c in v})
    assert cl.failed_checks(proc.stdout) == expected, cl.fh.describe(proc)


# ---------------------------------------------------------------------------
# C9.40: the monotone guard through the real command
# ---------------------------------------------------------------------------
def _set_settings(root: Path, n: int) -> None:
    cl.edit_json(root, cl.INLINE_ALLOWLIST_REL, lambda d: d["style"].__setitem__("settings.html", n))
    p = root / SETTINGS_REL
    body = p.read_text(encoding="utf-8")
    current = body.count('<i style=""></i>')
    p.write_text(body.replace("</body>", '<i style=""></i>' * (n - 2 - current) + "</body>", 1), encoding="utf-8")


def test_growth_names_file_and_delta(repo: Path) -> None:
    _set_settings(repo, 3)
    cl.commit_all(repo, "grow")
    proc = cl.run_contracts(repo)
    assert proc.returncode != 0
    assert cl.lines_matching(proc.stdout, ["settings.html", "2→3"]), proc.stdout


def test_extra_whitelist_entry_named(repo: Path) -> None:
    seed_whitelist_growth(repo)
    cl.commit_all(repo, "grow")
    proc = cl.run_contracts(repo)
    assert proc.returncode != 0
    assert "extra.css" in proc.stdout


def test_compares_with_merge_base_not_previous_commit(repo: Path) -> None:
    _set_settings(repo, 4)
    cl.commit_all(repo, "grow to 4")
    cl.commit_all(repo, "still 4")
    proc = cl.run_contracts(repo)
    assert proc.returncode != 0
    assert "2→4" in proc.stdout, proc.stdout


def test_shrink_passes(repo: Path) -> None:
    # lower settings to 1 (template and entry), and drop one hardcode baseline entry
    # (its violation removed from the template so the ratchet has no stale entry).
    p = repo / SETTINGS_REL
    body = p.read_text(encoding="utf-8")
    first = body.index('style="')
    tag_start = body.rindex("<", 0, first)
    tag_end = body.index(">", first)
    tag = body[tag_start : tag_end + 1]
    stripped = tag[: first - tag_start] + tag[body.index('"', first + len('style="')) + 1 - tag_start :]
    p.write_text(body[:tag_start] + stripped + body[tag_end + 1 :], encoding="utf-8")
    cl.edit_json(repo, cl.INLINE_ALLOWLIST_REL, lambda d: d["style"].__setitem__("settings.html", 1))
    proc = cl.run_hardcode(repo, "--update-baseline")
    assert proc.returncode == 0, cl.fh.describe(proc)
    cl.commit_all(repo, "shrink")
    proc = cl.run_contracts(repo)
    assert proc.returncode == 0, cl.fh.describe(proc)


def test_default_base_resolves_origin_master(tmp_path: Path, repo: Path) -> None:
    origin = tmp_path / "origin.git"
    cl.git(tmp_path, "init", "-q", "--bare", str(origin))
    cl.git(repo, "remote", "add", "origin", str(origin))
    cl.git(repo, "push", "-q", "origin", "base:refs/heads/master")
    cl.git(repo, "fetch", "-q", "origin")
    _set_settings(repo, 3)
    cl.commit_all(repo, "grow")
    proc = cl.run_contracts(repo, base_ref=None)
    assert proc.returncode != 0
    assert cl.lines_matching(proc.stdout, ["settings.html", "2→3"]), proc.stdout


@pytest.mark.parametrize("committed", [True, False], ids=["committed", "working-tree"])
def test_unresolvable_default_base_fails_closed(repo: Path, committed: bool) -> None:
    _set_settings(repo, 3)
    if committed:
        cl.commit_all(repo, "grow")
    proc = cl.run_contracts(repo, base_ref=None)
    assert proc.returncode != 0
    section = proc.stdout.split("== allowlist-monotone ==", 1)[1].split("\n== ", 1)[0]
    assert "cannot resolve base" in section.lower(), section
    assert "OK" not in section and "no growth" not in section, section
    assert "allowlist-monotone" in (cl.failed_checks(proc.stdout) or [])
