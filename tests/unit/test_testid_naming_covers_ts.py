"""013 WI-9 A9.13 (user ruling D6; C9.16, C9.17): the naming lint scans `frontend/src/**/*.ts`.

Shape only (like the static JS): every testid literal a TS file emits must match
`CANONICAL` (lib- / rd- / set- prefixes). Four emission forms are recognised —
`setAttribute("data-testid", "…")`, `dataset.testid = "…"`, a `data-testid="…"` attribute
inside a template string, and a `const *TESTID* = {…}` table — and a testid built by `+`
or `${}` is always a violation. `static/dist/` (minified build output) is excluded.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import contract_lints as cl


@pytest.fixture(scope="module")
def lint():
    return cl.load(cl.NAMING_LINT, "lint_testid_naming_ts_under_test")


FORMS = {
    "setAttribute": 'export function f(el: HTMLElement): void {\n  el.setAttribute("data-testid", "{S}");\n}\n',
    "dataset": "export function f(el: HTMLElement): void {\n  el.dataset.testid = '{S}';\n}\n",
    "template-attr": "export const html = `<div data-testid=\"{S}\"></div>`;\n",
    "table": 'export const LIB_TESTID = {\n  a: "{S}",\n};\n',
}


def _run(lint, root: Path):
    return cl.call_main(lint, ["--root", str(root)])


def test_ts_glob_is_shape_only(lint) -> None:
    assert "frontend/src/**/*.ts" in lint.SHAPE_ONLY_SCAN_GLOBS
    assert "src/reader3_app/web/static/dist/" in lint.SHAPE_ONLY_EXCLUDE


def test_real_tree_passes(lint) -> None:
    rc, out = _run(lint, cl.REPO_ROOT)
    assert rc == 0, out


_S = st.text(
    alphabet=st.characters(blacklist_characters="\"'`\\\n\r{}$", blacklist_categories=("Cs",)), min_size=0, max_size=24
) | st.from_regex(r"(lib|rd|set|reader|library)-[a-z0-9]{1,6}(-[a-z0-9]{1,4}){0,2}", fullmatch=True)


@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(s=_S, form=st.sampled_from(sorted(FORMS)))
def test_verdict_matches_canonical_oracle(lint, tmp_path_factory, s: str, form: str) -> None:
    root = tmp_path_factory.mktemp("c916")
    cl.write(root, "frontend/src/components/x.ts", FORMS[form].replace("{S}", s))
    rc, out = _run(lint, root)
    expected = 0 if lint.CANONICAL.fullmatch(s) else 1
    assert rc == expected, f"form={form} s={s!r}\n{out}"


@pytest.mark.parametrize(
    "body",
    [
        'export function f(el: HTMLElement, kind: string): void {\n  el.dataset.testid = "lib-" + kind;\n}\n',
        'export function f(el: HTMLElement, kind: string): void {\n  el.setAttribute("data-testid", "lib-" + kind);\n}\n',
        "export function f(el: HTMLElement, kind: string): void {\n  el.dataset.testid = `lib-${kind}`;\n}\n",
        "export function f(kind: string): string {\n  return `<i data-testid=\"lib-${kind}\"></i>`;\n}\n",
    ],
    ids=["dataset-concat", "setAttribute-concat", "dataset-template", "attr-interpolated"],
)
def test_constructed_testids_are_violations(lint, tmp_path: Path, body: str) -> None:
    cl.write(tmp_path, "frontend/src/library/x.ts", body)
    rc, out = _run(lint, tmp_path)
    assert rc == 1, out
    assert "frontend/src/library/x.ts:2" in out, out


def test_dataset_from_constant_table_is_fine(lint, tmp_path: Path) -> None:
    cl.write(
        tmp_path,
        "frontend/src/library/x.ts",
        'const LIB_TESTID = {\n  ok: "lib-status-ok",\n};\n'
        "export function f(el: HTMLElement): void {\n  el.dataset.testid = LIB_TESTID.ok;\n}\n",
    )
    rc, out = _run(lint, tmp_path)
    assert rc == 0, out


def test_dist_is_excluded(lint, tmp_path: Path) -> None:
    cl.write(tmp_path, "src/reader3_app/web/static/dist/assets/x.js", 'e.setAttribute("data-testid","Bad_Name");')
    rc, out = _run(lint, tmp_path)
    assert rc == 0, out


def test_frontend_tests_are_not_emitters(lint, tmp_path: Path) -> None:
    cl.write(tmp_path, "frontend/tests/x.test.ts", 'el.dataset.testid = "Bad_Name";\n')
    rc, out = _run(lint, tmp_path)
    assert rc == 0, out
