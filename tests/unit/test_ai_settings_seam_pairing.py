"""018 WI-3 / WI-1: the settings seam-pairing law (matrix R3-1-19, R3-1-20).

Law: every test module that redirects ``server.load_ai_settings`` or
``server.save_ai_settings`` **and** drives an in-scope settings route also
redirects ``server.ai_settings_transaction``. Otherwise the request reads and
writes a tmp file while it locks -- and computes the ETag of -- the developer's
real ``config/``: an ETag that describes the wrong file and a lock file planted
in the working tree.

The plan's "patches save => patches transaction" is too weak:
``test_ai_settings_no_key_loss.py`` A6 patches **only** ``load_ai_settings`` and
calls ``GET /api/settings``. So the predicate is "load *or* save".

Scope and its two deliberate approximations:

* Patch sites are found with the registry lock's own extractor
  (``extract_patch_targets``), so the spellings it knows -- aliases, multi-line,
  string targets, ``mp.setattr`` -- count here too. A ``setattr`` whose target
  is unresolvable but whose attribute is one of the three names is also counted
  (channel 3), so a bare snippet without its import is still judged.
* ``tests/contract/conftest.py``'s ``world`` fixture serves every module in that
  directory, so each ``tests/contract/*.py`` is treated as carrying the
  conftest's patches, and the conftest is treated as driving every route its
  directory drives.

A test that builds its own server namespace without ``setattr`` is invisible to
this scan; WI-2's runtime fence (R3-2-15) is the backstop for that.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, Set, Tuple

from test_server_patch_seam_registry_complete import extract_patch_targets, iter_test_files

TRANSACTION = "ai_settings_transaction"
LOAD_SAVE = frozenset({"load_ai_settings", "save_ai_settings"})
SEAM_NAMES = frozenset(LOAD_SAVE | {TRANSACTION})

#: The in-scope settings routes; f-string placeholders are rendered as ``{}``.
ROUTE_RE = re.compile(r"^/api/settings(/import|/providers/(\{\}|[a-z_]+))?$")

CONTRACT_DIR = "tests/contract"
CONTRACT_CONFTEST = "tests/contract/conftest.py"
LANE_DIRS = ("tests/unit", CONTRACT_DIR)


def patched_server_names(source: str, filename: str) -> Set[str]:
    """Server-namespace names this module patches (channel 1), plus seam names on an unresolvable target."""
    sites, _non_literal, unresolvable = extract_patch_targets(source, filename, SEAM_NAMES)
    names = {site.name for site in sites}
    names |= {u.attr for u in unresolvable if u.attr in SEAM_NAMES}
    return names


def _render_joined(node: ast.JoinedStr) -> str:
    parts = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        else:
            parts.append("{}")
    return "".join(parts)


def exercises_settings_route(source: str) -> bool:
    """True if any string constant or f-string in the module is exactly an in-scope route."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            if ROUTE_RE.fullmatch(_render_joined(node)):
                return True
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if ROUTE_RE.fullmatch(node.value):
                return True
    return False


def selected(patched: Set[str], drives_route: bool) -> bool:
    """The module redirects settings I/O and drives a settings route."""
    return bool(patched & LOAD_SAVE) and drives_route


def offending(patched: Set[str], drives_route: bool) -> bool:
    return selected(patched, drives_route) and TRANSACTION not in patched


def scan(repo_root: Path) -> Tuple[Set[str], Dict[str, Set[str]]]:
    """Return (selected modules, {offending module: missing names}) over the lane's test tree."""
    per_file: Dict[str, Tuple[Set[str], bool]] = {}
    for path in iter_test_files([repo_root / d for d in LANE_DIRS]):
        rel = path.relative_to(repo_root).as_posix()
        source = path.read_text(encoding="utf-8")
        per_file[rel] = (patched_server_names(source, rel), exercises_settings_route(source))

    contract = {rel for rel in per_file if rel.startswith(CONTRACT_DIR + "/")}
    conftest_patched = per_file.get(CONTRACT_CONFTEST, (set(), False))[0]
    contract_drives = any(per_file[rel][1] for rel in contract)

    chosen: Set[str] = set()
    bad: Dict[str, Set[str]] = {}
    for rel, (patched, drives) in per_file.items():
        if rel in contract:
            patched = patched | conftest_patched
            if rel == CONTRACT_CONFTEST:
                drives = drives or contract_drives
        if selected(patched, drives):
            chosen.add(rel)
        if offending(patched, drives):
            bad[rel] = {TRANSACTION}
    return chosen, bad


# --------------------------------------------------------------------------
# R3-1-19 -- S4: the pairing holds across the test tree
# --------------------------------------------------------------------------


def test_settings_route_tests_redirect_the_transaction(repo_root: Path) -> None:
    _chosen, bad = scan(repo_root)
    assert bad == {}, (
        "these modules redirect load/save_ai_settings and drive a settings route, but do not "
        "redirect server.ai_settings_transaction to the same path -- the request would lock "
        f"and hash the real config/: { {k: sorted(v) for k, v in bad.items()} }"
    )


# --------------------------------------------------------------------------
# R3-1-20 -- S2: the scan is not vacuous
# --------------------------------------------------------------------------


def test_pairing_scan_sees_the_known_redirecting_modules(repo_root: Path) -> None:
    chosen, _bad = scan(repo_root)
    known = {
        CONTRACT_CONFTEST,
        "tests/unit/test_settings_no_preference_loss.py",
        "tests/unit/test_ai_settings_no_key_loss.py",
    }
    assert known <= chosen, f"the scan missed {sorted(known - chosen)}; selected={sorted(chosen)}"

    synthetic = 'monkeypatch.setattr(server, "save_ai_settings", f)\nclient.put("/api/settings", json={})\n'
    patched = patched_server_names(synthetic, "<synthetic>")
    drives = exercises_settings_route(synthetic)
    assert offending(patched, drives), (patched, drives)
