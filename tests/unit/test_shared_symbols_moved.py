"""013 WI-11 A11.5 (C11.04): `showToast` / `elementDebugInfo` / `getEventTargetElement` live in
`frontend/src/shared/`, exactly once each, and nowhere under `frontend/src/reader/`.

The "exactly one in shared" half exists because "0 under reader/" is vacuous in 013 (the reader
TS entry is still a stub). Seeded trees with 0 and 2 definitions must both be red.

Also pins two Toast facts that are about the source rather than behaviour: the dwell never
derives from `--r3-duration-*` (A11.4 / spec §5.3), and the old inline `zIndex = "2000"` did
not travel with the move (spec §5.3 hard constraint).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FE_SRC = ROOT / "frontend" / "src"
SYMBOLS = ("showToast", "elementDebugInfo", "getEventTargetElement")
HOMES = {
    "showToast": "shared/toast.ts",
    "elementDebugInfo": "shared/dom.ts",
    "getEventTargetElement": "shared/dom.ts",
}


def _definition_re(name: str) -> re.Pattern[str]:
    return re.compile(
        rf"\bfunction\s+{name}\b|\b(?:const|let|var)\s+{name}\s*=|\b{name}\s*:\s*(?:function\b|\()"
    )


def definition_sites(fe_src: Path, name: str) -> list[str]:
    rx = _definition_re(name)
    sites: list[str] = []
    for path in sorted(fe_src.glob("**/*.ts")):
        sites += [path.relative_to(fe_src).as_posix()] * len(rx.findall(path.read_text(encoding="utf-8")))
    return sites


def moved_problems(fe_src: Path) -> list[str]:
    problems: list[str] = []
    for name in SYMBOLS:
        sites = definition_sites(fe_src, name)
        in_reader = [s for s in sites if s.startswith("reader/")]
        in_shared = [s for s in sites if s.startswith("shared/")]
        if in_reader:
            problems.append(f"{name}: defined under reader/ at {in_reader}")
        if in_shared != [HOMES[name]]:
            problems.append(f"{name}: expected exactly one definition at {HOMES[name]}, found {in_shared}")
    return problems


@pytest.mark.parametrize("name", SYMBOLS)
def test_zero_definitions_under_reader(name: str) -> None:
    assert [s for s in definition_sites(FE_SRC, name) if s.startswith("reader/")] == []


@pytest.mark.parametrize("name", SYMBOLS)
def test_exactly_one_definition_in_shared(name: str) -> None:
    assert [s for s in definition_sites(FE_SRC, name) if s.startswith("shared/")] == [HOMES[name]]


def test_real_tree_has_no_problems() -> None:
    assert moved_problems(FE_SRC) == []


GOOD = {
    "shared/toast.ts": "export function showToast(m: string) {}\n",
    "shared/dom.ts": "export function elementDebugInfo(e: Element) {}\nexport function getEventTargetElement(t: unknown) {}\n",
}


@pytest.mark.parametrize(
    ("extra", "drop", "red"),
    [
        ({}, (), False),
        ({}, ("shared/toast.ts",), True),  # seed 0: showToast missing
        ({"reader/annotations.ts": "function showToast(m: string) {}\n"}, (), True),  # seed 2, one in reader
        ({"shared/other.ts": "const getEventTargetElement = (t: unknown) => null;\n"}, (), True),  # seed 2 in shared
    ],
    ids=["seed-1-green", "seed-0-red", "seed-reader-red", "seed-2-shared-red"],
)
def test_check_on_seeded_trees(tmp_path: Path, extra: dict[str, str], drop: tuple[str, ...], red: bool) -> None:
    for rel, body in {**GOOD, **extra}.items():
        if rel in drop:
            continue
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(body, encoding="utf-8")
    assert bool(moved_problems(tmp_path)) is red


def test_toast_dwell_is_not_derived_from_duration_tokens() -> None:
    text = (FE_SRC / "shared" / "toast.ts").read_text(encoding="utf-8")
    assert "--r3-dwell-toast" in text
    assert "--r3-duration-" not in text


def test_toast_has_no_inline_z_index_or_constant_timeout() -> None:
    text = (FE_SRC / "shared" / "toast.ts").read_text(encoding="utf-8")
    assert not re.search(r"zIndex|z-index", text)
    # setTimeout's delay must be the read token value, never a numeric literal.
    for m in re.finditer(r"setTimeout\((.*?)\)\s*;", text, re.S):
        assert not re.search(r",\s*\d+\s*$", m.group(1)), m.group(0)
