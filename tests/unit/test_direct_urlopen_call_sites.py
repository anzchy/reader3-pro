"""An exact lock on who in ``src/`` still calls ``urllib.request.urlopen`` directly.

WI-11 pulled the five providers' hand-copied ``_post_json`` bodies into
``ai/providers/_http.post_json``, which is where the scheme allowlist and the
no-redirect opener live. Anything that reaches the network *around* that
function gets neither.

Two call sites did not come along: ``server._http_get_json`` and the inline
Ollama streaming loop inside ``api_ai_question``. Closing them is not this work
item's job -- the plan defers it ("另行处理") to after WI-11, and no work item
owns it yet. What this test does is make the gap *countable*, so that it stays
exactly two lines wide and nobody widens it by accident.

Hence a set comparison against ``(relative path, call count)`` rather than a
per-file allow/deny. A path-only allowlist would let a third ``urlopen`` land in
``server.py`` -- the very file already permitted -- and stay green, which is the
likeliest way this regresses. Counting makes that red.

Why AST and not grep: ``_http.py`` mentions ``urlopen`` twice in prose, once in
the module docstring and once in a comment above ``ALLOWED_SCHEMES``. A regex
lock would count those as call sites, and would then have to be loosened with an
exception for the one file whose whole purpose is to be the single exit. The
scanner is pinned against exactly that trap below.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pytest

#: ``(path relative to the repo root, number of direct urlopen calls)``.
#:
#: **Empty since WI-30.** It used to hold ``("src/reader3_app/web/server.py", 2)``
#: -- the two call sites that WI-11 left outside the gate:
#:   * ``_http_get_json`` -- the Ollama version/model-list probe.
#:   * ``api_ai_question`` -> ``event_gen`` -> ``worker_ollama`` -- the Ollama
#:     streaming loop, which is also why ``tests/contract/conftest.py`` could not
#:     honestly claim to have stubbed every egress point.
#: WI-30 moved both behind ``ai/providers/_http``: the probe onto ``get_json``
#: and the streaming loop onto ``post_stream`` (a context manager, so the caller
#: keeps reading line by line -- ``post_json`` would have read the whole body and
#: turned the stream into a blocking call). Both go through the same
#: ``ALLOWED_SCHEMES`` check and the same ``_NoRedirectHandler`` as ``post_json``.
#:
#: The allowlist is now a *no direct egress anywhere* lock. To add an entry you
#: must first justify why it does not belong behind ``ai/providers/_http``.
EXPECTED_DIRECT_URLOPEN_CALL_SITES: Set[Tuple[str, int]] = set()


def count_direct_urlopen_calls(source: str, filename: str) -> int:
    """Number of ``Call`` nodes whose callee is spelled ``urlopen``.

    Covers both ``urllib.request.urlopen(...)`` (an ``Attribute`` callee) and a
    bare ``urlopen(...)`` after ``from urllib.request import urlopen`` (a
    ``Name`` callee). Comments and string literals are not nodes, so they cannot
    be counted -- which is the whole reason this is not a regex.
    """
    tree = ast.parse(source, filename=filename)
    total = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "urlopen":
            total += 1
        elif isinstance(func, ast.Name) and func.id == "urlopen":
            total += 1
    return total


def python_sources(repo_root: Path) -> List[Path]:
    return sorted(
        p
        for p in (repo_root / "src").rglob("*.py")
        if "__pycache__" not in p.parts
    )


def scan(repo_root: Path) -> Dict[str, int]:
    found: Dict[str, int] = {}
    for path in python_sources(repo_root):
        n = count_direct_urlopen_calls(path.read_text(encoding="utf-8"), str(path))
        if n:
            found[path.relative_to(repo_root).as_posix()] = n
    return found


@pytest.fixture(autouse=True)
def _cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Read-only test, but the lane's rule is absolute: never run from the repo root."""
    monkeypatch.chdir(tmp_path)


def test_z2_direct_urlopen_call_sites_match_the_allowlist_exactly(repo_root: Path) -> None:
    """L2 - the set of ``(file, count)`` pairs is frozen; a new call site or a
    third call in an already-listed file both break the equality."""
    found = set(scan(repo_root).items())

    assert found == EXPECTED_DIRECT_URLOPEN_CALL_SITES, (
        "direct urllib.request.urlopen call sites changed.\n"
        f"  expected: {sorted(EXPECTED_DIRECT_URLOPEN_CALL_SITES)}\n"
        f"  found:    {sorted(found)}\n"
        "New network egress must go through ai/providers/_http.post_json, which "
        "is where the scheme allowlist and the no-redirect opener are enforced."
    )


def test_z2_scanner_does_not_count_the_word_urlopen_in_comments_or_strings(
    repo_root: Path,
) -> None:
    """L2 - guards the scanner itself, without which the lock above is worthless.

    ``_http.py`` is the adversarial case that already exists in the tree: it says
    "urlopen" twice in prose and calls it zero times, because it goes through
    ``opener.open``. A regex-based lock would report 2 here and would then be
    "fixed" by exempting the file, defeating the point.
    """
    http_module = repo_root / "src" / "reader3_app" / "ai" / "providers" / "_http.py"
    source = http_module.read_text(encoding="utf-8")

    assert "urlopen" in source, "fixture assumption: _http.py still mentions urlopen in prose"
    assert count_direct_urlopen_calls(source, str(http_module)) == 0

    synthetic = (
        '"""urlopen appears in this docstring."""\n'
        "# and urlopen appears in this comment\n"
        'NOTE = "urlopen(never_called)"\n'
        "def f():\n"
        "    return opener.open(req)\n"
    )
    assert count_direct_urlopen_calls(synthetic, "<synthetic>") == 0
    assert count_direct_urlopen_calls("urllib.request.urlopen(req)\n", "<synthetic>") == 1
    assert count_direct_urlopen_calls("urlopen(req)\n", "<synthetic>") == 1


def test_z2_scan_actually_reads_the_package(repo_root: Path) -> None:
    """L2 - a scan of zero files would satisfy any allowlist that happened to be empty."""
    sources = python_sources(repo_root)
    names = {p.relative_to(repo_root).as_posix() for p in sources}

    assert len(sources) >= 10
    assert "src/reader3_app/web/server.py" in names
    assert "src/reader3_app/ai/providers/_http.py" in names
    assert not any("__pycache__" in p.parts for p in sources)
