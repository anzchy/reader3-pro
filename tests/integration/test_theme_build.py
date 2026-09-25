"""013 WI-10 C10.21 (A10.11, PLAN :960): the built artefact carries exactly the two
plugin-authored dark rules, with byte-equal bodies.

C10.03 / C10.04 check the emitter as a pure function; this checks what a real Vite build
emits. The build runs unminified (`R3_BUILD_MINIFY=0`, read by `frontend/vite.config.ts`),
because a minifier may legitimately merge the two rules into one selector list -- :960
asks for the two selectors in the generated, pre-minified stylesheet.

Expected body: `emitDarkCss(CHROME_THEMES.dark)` printed by Node itself
(`--experimental-strip-types`; both modules are import-free TypeScript), not a Python
re-derivation of the tokens.

Seeds, each a rebuild in its own workspace copy:
    s1  a handwritten dark rule in a stylesheet the library entry imports
    s2  a second `CHROME_THEMES` definition file under `frontend/src`
Each must be red: the build fails, or the dark-rule count / bodies are no longer the
clean-build result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import frontend_host as fh
import pytest

pytestmark = pytest.mark.slow

BUILD_TIMEOUT_S = 300
DARK_MEDIA = "@media (prefers-color-scheme: dark)"
DARK_SYSTEM_SELECTOR = ':root:not([data-theme="light"])'
DARK_EXPLICIT_SELECTOR = ':root[data-theme="dark"]'


@dataclass(frozen=True)
class Rule:
    context: str  # enclosing at-rule prelude, "" at top level
    selector: str
    body: str  # raw text between the braces


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_rules(css: str) -> List[Rule]:
    """Innermost `{...}` blocks with their selector and enclosing at-rule (one level deep)."""
    css = re.sub(r"/\*[\s\S]*?\*/", "", css)
    rules: List[Rule] = []
    stack: List[Tuple[str, int]] = []  # (prelude, body start)
    prelude_start = 0
    has_child: List[bool] = [False]
    for i, ch in enumerate(css):
        if ch == "{":
            stack.append((_norm(css[prelude_start:i]), i + 1))
            has_child[-1] = True
            has_child.append(False)
            prelude_start = i + 1
        elif ch == "}":
            prelude, start = stack.pop()
            leaf = not has_child.pop()
            if leaf:
                context = stack[-1][0] if stack else ""
                rules.append(Rule(context=context, selector=prelude, body=css[start:i]))
            prelude_start = i + 1
        elif ch == ";" and not stack:
            prelude_start = i + 1  # a top-level statement such as @charset
    return rules


def declarations(body: str) -> List[str]:
    return [_norm(d) for d in body.split(";") if d.strip()]


def dark_rules(rules: List[Rule]) -> List[Rule]:
    return [r for r in rules if r.selector in (DARK_SYSTEM_SELECTOR, DARK_EXPLICIT_SELECTOR)]


@dataclass
class BuildResult:
    proc: object
    rules: Optional[List[Rule]]

    @property
    def ok(self) -> bool:
        return self.rules is not None


def build(ws: Path) -> BuildResult:
    env = fh.node_env()
    env["R3_BUILD_MINIFY"] = "0"
    proc = fh.run(
        ["npx", "vite", "build", "--config", "frontend/vite.config.ts"], cwd=ws, timeout=BUILD_TIMEOUT_S, env=env
    )
    if proc.returncode != 0:
        return BuildResult(proc, None)
    css_files = sorted((ws / fh.DIST_REL).rglob("*.css"))
    return BuildResult(proc, [r for p in css_files for r in parse_rules(p.read_text(encoding="utf-8"))])


def expected_dark_css(ws: Path) -> str:
    script = (
        'import { emitDarkCss } from "./frontend/theme-build.ts";'
        'import { CHROME_THEMES } from "./frontend/src/shared/theme-tokens.ts";'
        "process.stdout.write(emitDarkCss(CHROME_THEMES.dark));"
    )
    proc = fh.run(
        ["node", "--experimental-strip-types", "--no-warnings", "--input-type=module", "-e", script],
        cwd=ws,
        timeout=60,
    )
    assert proc.returncode == 0, "could not print emitDarkCss through Node\n" + fh.describe(proc)
    return proc.stdout


def assert_clean_dark_rules(result: BuildResult, expected_css: str) -> None:
    assert result.ok, "build failed\n" + fh.describe(result.proc)  # type: ignore[arg-type]
    found = dark_rules(result.rules or [])
    assert len(found) == 2, f"expected exactly 2 dark rules in the built CSS, found {len(found)}: {found}"
    by_selector = {r.selector: r for r in found}
    assert set(by_selector) == {DARK_SYSTEM_SELECTOR, DARK_EXPLICIT_SELECTOR}
    assert by_selector[DARK_SYSTEM_SELECTOR].context == DARK_MEDIA
    assert by_selector[DARK_EXPLICIT_SELECTOR].context == ""
    system, explicit = by_selector[DARK_SYSTEM_SELECTOR].body, by_selector[DARK_EXPLICIT_SELECTOR].body
    assert system == explicit, "the two dark bodies are not byte-equal in the built CSS"
    emitted = dark_rules(parse_rules(expected_css))
    assert len(emitted) == 2
    assert declarations(system) == declarations(emitted[0].body), "built dark body != emitDarkCss(CHROME_THEMES.dark)"
    assert len(declarations(system)) >= 20, "the dark body is implausibly small"


def is_red(result: BuildResult, expected_css: str) -> bool:
    try:
        assert_clean_dark_rules(result, expected_css)
    except AssertionError:
        return True
    return False


@pytest.fixture(scope="module")
def workspace_factory(tmp_path_factory: pytest.TempPathFactory):
    fh.require_node_toolchain()

    def make(name: str) -> Path:
        return fh.make_workspace(tmp_path_factory.mktemp(name))

    return make


def test_built_css_has_exactly_the_two_plugin_dark_rules(workspace_factory) -> None:
    ws = workspace_factory("clean")
    assert_clean_dark_rules(build(ws), expected_dark_css(ws))


def test_handwritten_dark_rule_is_red(workspace_factory) -> None:
    ws = workspace_factory("s1")
    expected = expected_dark_css(ws)
    lib = ws / "frontend" / "src" / "library"
    (lib / "extra.css").write_text(':root[data-theme="dark"] { --r3-text: #fff; }\n', encoding="utf-8")
    entry = lib / "index.ts"
    entry.write_text('import "./extra.css";\n' + entry.read_text(encoding="utf-8"), encoding="utf-8")
    assert is_red(build(ws), expected)


def test_second_definition_fails_the_build(workspace_factory) -> None:
    ws = workspace_factory("s2")
    expected = expected_dark_css(ws)
    (ws / "frontend" / "src" / "shared" / "theme-tokens-extra.ts").write_text(
        'export const CHROME_THEMES = { light: {}, dark: { "--r3-text": "#fff" } };\n', encoding="utf-8"
    )
    result = build(ws)
    assert is_red(result, expected)
    assert not result.ok, "a second CHROME_THEMES definition must fail the build, not only change it"
    out = result.proc.stdout + result.proc.stderr  # type: ignore[attr-defined]
    assert re.search(r"defined 2", out), fh.describe(result.proc)  # type: ignore[arg-type]
