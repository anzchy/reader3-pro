"""WI-6 cases for the verify-reader3 skill docs: SKILL.md, the Feature Map, the removed scripts.

Matrix: `.claude/tdd-guardian/tests-20261002-170349-WI-4-5-6.md` (WI6-C01..C11) with the
amended WI6-C01 from its addendum (`commands_checked >= 12`). WI6-C12 is added by the
implementer: the plan's "quoted-command parse" test, done in-process with a test-local
extractor so the drift invariant does not rest on `map check`'s own extractor alone.

Every case reads the real worktree files and writes nothing. H2 extraction and command
extraction are test-local; they never import `map_check`, so the oracle is not circular.
The only CLI code used in-process is `cli.build_parser()`, and it is only parsed, never
dispatched. A missing doc fails through an explicit `is_file()` assertion.
"""

from __future__ import annotations

import contextlib
import io
import re
import shlex
from pathlib import Path

import pytest

from verify_control_support import (  # noqa: F401 (autouse fixtures are imported for effect)
    REPO,
    base_env,
    real_evidence_untouched,
    reap_fakes,
    run_cli,
)
from verify_control import cli
from verify_control.registry import UsageError

SK = REPO / ".claude" / "skills" / "verify-reader3"
FEAT = SK / "references" / "features"
SKILL = SK / "SKILL.md"
README = FEAT / "README.md"
MAP_IDS = ("F-009", "F-011", "F-013", "F-018", "F-020")
FOUR = ["Sub-features", "How to get to it (user POV)", "Driving it with control.py and $B", "Gotchas"]
SEVEN = ["Launch", "Doctor", "Drive", "Evidence", "Cleanup", "Helpers", "Gotchas"]
REMOVED = ("launch.sh", "doctor.sh", "cleanup.sh")
GROUPS = {"reader", "ui", "evidence", "map", "book", "fs", "ai"}
REQUIRED_STAGE_COMMANDS = {
    "up", "doctor", "down", "reader state", "reader select", "ui inert", "api", "fs stat",
    "evidence start", "evidence result", "map check", "lane",
}
_CMD_RE = re.compile(r"(?:python3\s+)?\S*control\.py\s+(.+)")
_SPAN = re.compile(r"`([^`\n]+)`")


# ---------------------------------------------------------------------------
# test-local markdown helpers (independent of verify_control.map_check)
# ---------------------------------------------------------------------------


def _doc(path: Path) -> str:
    assert path.is_file(), f"expected doc is absent: {path.relative_to(REPO)}"
    return path.read_text(encoding="utf-8")


def _lines_with_fence(text: str):
    """`(lineno, line, in_fence)` for every line; fence delimiter lines are skipped."""
    fence = None
    for n, line in enumerate(text.split("\n"), 1):
        s = line.lstrip()
        opener = "```" if s.startswith("```") else "~~~" if s.startswith("~~~") else None
        if fence is None and opener:
            fence = opener
            continue
        if fence is not None and opener == fence:
            fence = None
            continue
        yield n, line, fence is not None


def _h2s(text: str):
    return [ln[3:].strip() for _, ln, f in _lines_with_fence(text) if not f and ln.startswith("## ")]


def _section(text: str, name: str) -> str:
    out, on = [], False
    for _, ln, f in _lines_with_fence(text):
        if not f and ln.startswith("## "):
            on = ln[3:].strip() == name
            continue
        if on:
            out.append(ln)
    return "\n".join(out)


def _quoted(text: str):
    """`(lineno, snippet)` for fenced lines and inline backtick spans."""
    for n, ln, f in _lines_with_fence(text):
        if f:
            yield n, ln.strip()
        else:
            for span in _SPAN.findall(ln):
                yield n, span.strip()


def _control_args(snippet: str):
    """argv after `control.py`, or None when the snippet is not a control.py command."""
    m = _CMD_RE.match(snippet)
    if m is None:
        return None
    return shlex.split(m.group(1), comments=True)


def _subcommand(args):
    if not args:
        return ""
    if args[0] in GROUPS and len(args) > 1:
        return f"{args[0]} {args[1]}"
    return args[0]


def _parse_problem(args):
    """None when `args` parse with the real parser, else a short reason. Never dispatches."""
    parser = cli.build_parser()
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            _, extras = parser.parse_known_args(list(args))
    except UsageError as exc:
        return "parser: " + exc.message.replace("unrecognized", "unknown")
    except SystemExit as exc:
        return None if exc.code in (0, None) else f"parser exit {exc.code}"
    if extras:
        return "unknown extra args: " + " ".join(extras)
    return None


def _all_docs():
    return [SKILL, README, *[FEAT / f"{i}.md" for i in MAP_IDS]]


# ---------------------------------------------------------------------------
# WI6-C01 real-repo map check (amended)
# ---------------------------------------------------------------------------


def test_wi6_c01_real_repo_map_check_is_clean_and_maps_the_five_rows(tmp_path):
    code, env, err = run_cli(["map", "check"], base_env(tmp_path))
    data = env["data"] or {}
    assert data.get("problems") == [], f"map problems: {data.get('problems')}"
    assert data.get("dead_commands") == [], f"dead commands: {data.get('dead_commands')}"
    assert set(MAP_IDS) <= set(data.get("mapped", [])), f"mapped: {data.get('mapped')}"
    assert data.get("commands_checked", 0) >= 12, f"commands_checked: {data.get('commands_checked')}"
    assert env["ok"] is True and env["error"] is None, env["error"]
    assert code == 0


# ---------------------------------------------------------------------------
# WI6-C02 .. C07 SKILL.md and the scripts
# ---------------------------------------------------------------------------


def test_wi6_c02_skill_md_has_exactly_the_seven_h2s_in_order():
    assert _h2s(_doc(SKILL)) == SEVEN


def test_wi6_c02_skill_md_frontmatter_is_valid():
    text = _doc(SKILL)
    lines = text.split("\n")
    assert lines[0] == "---", "SKILL.md must open with YAML front matter"
    end = lines.index("---", 1)
    front = "\n".join(lines[1:end])
    assert re.search(r"^name: verify-reader3$", front, re.M)
    assert re.search(r"^description: ", front, re.M)


def test_wi6_c03_no_reader3_library_ui_in_skill_md():
    assert "READER3_LIBRARY_UI" not in _doc(SKILL)


def test_wi6_c04_no_file_under_the_skill_references_the_removed_scripts():
    assert SK.is_dir()
    hits = {}
    for p in sorted(SK.rglob("*")):
        if not p.is_file():
            continue
        text = p.read_bytes().decode("utf-8", errors="replace")
        lines = [n for n, ln in enumerate(text.split("\n"), 1) if any(s in ln for s in REMOVED)]
        if lines:
            hits[str(p.relative_to(REPO))] = lines
    assert hits == {}


@pytest.mark.parametrize("name", REMOVED)
def test_wi6_c05_the_shell_script_is_deleted(name):
    assert not (SK / "scripts" / name).exists(), f"scripts/{name} still present"


def test_wi6_c06_skill_md_quotes_every_stage_command():
    found = set()
    for _, snippet in _quoted(_doc(SKILL)):
        args = _control_args(snippet)
        if args is not None:
            found.add(_subcommand(args))
    assert REQUIRED_STAGE_COMMANDS - found == set(), f"stage commands not quoted in SKILL.md: {sorted(REQUIRED_STAGE_COMMANDS - found)}"


@pytest.mark.parametrize("fid", MAP_IDS)
def test_wi6_c06_each_map_drives_with_control_py(fid):
    driving = _section(_doc(FEAT / f"{fid}.md"), "Driving it with control.py and $B")
    cmds = [s for _, s in _quoted(driving) if _control_args(s) is not None]
    assert cmds, f"{fid}.md Driving section quotes no control.py line"


REQUIRED_KNOWLEDGE = [
    "rd-anno-toolbar", "lib-book-card", "rd-viewport",
    "frame main",
    "Google Fonts",
    "’",
    "Real user path",
    "PASS", "FAIL", "SKIPPED", "DEVIATES",
    "--token", "server.py:138",
    "access_log",
]


@pytest.mark.parametrize("needle", REQUIRED_KNOWLEDGE)
def test_wi6_c07_skill_md_keeps_the_required_knowledge(needle):
    assert needle in _doc(SKILL)


# ---------------------------------------------------------------------------
# WI6-C08 .. C11 the Feature Map
# ---------------------------------------------------------------------------


def test_wi6_c08_f020_redirects_the_confirm_ls_to_the_sandbox_file():
    text = _doc(FEAT / "F-020.md")
    assert "control.py fs stat ai_settings.json" in _section(text, "Gotchas")
    bad = [(n, ln) for n, ln in enumerate(text.split("\n"), 1)
           if "config/ai_settings.json" in ln and "fs stat" not in ln and "sandbox" not in ln]
    assert bad == []


def test_wi6_c09_f018_carries_the_two_gotchas():
    g = _section(_doc(FEAT / "F-018.md"), "Gotchas").lower()
    assert "toolbar closes after marker" in g
    assert "fresh selection" in g
    assert "per section" in g or "per-section" in g


def test_wi6_c10_f011_uses_q_cafe_through_control_py():
    lines = _doc(FEAT / "F-011.md").split("\n")
    assert any("control.py" in ln and "q=cafe" in ln for ln in lines)


def test_wi6_c11_readme_states_the_four_h2_rule_and_lists_the_maps():
    text = _doc(README)
    for h in FOUR:
        assert h in text, f"README misses the H2 name {h!r}"
    for fid in MAP_IDS:
        assert f"{fid}.md" in text, f"README does not list {fid}.md"


@pytest.mark.parametrize("fid", MAP_IDS)
def test_wi6_c11_each_map_has_exactly_the_four_h2s_and_links_its_row(fid):
    text = _doc(FEAT / f"{fid}.md")
    assert _h2s(text) == FOUR
    first = next(ln for ln in text.split("\n") if ln.strip())
    assert first.startswith(f"# {fid}")
    assert f"[{fid}](../../../../../docs/feature-ledger.md" in text


# ---------------------------------------------------------------------------
# WI6-C12 (added) every quoted control.py line parses with the real parser
# ---------------------------------------------------------------------------


def test_wi6_c12_oracle_rejects_bad_lines():
    """Non-vacuity of the parse oracle and the extractor used below."""
    assert _parse_problem(["reader", "state", "--wiat", "15"]) is not None
    assert _parse_problem(["frobnicate"]) is not None
    assert _parse_problem(["lane", "F-011", "--runner", "pyest"]) is not None
    assert _parse_problem([]) is not None
    assert _parse_problem(["reader", "state", "--wait", "15"]) is None
    assert _control_args("control.py lane F-011") == ["lane", "F-011"]
    assert _control_args("python3 .claude/skills/verify-reader3/scripts/control.py map check  # c") == ["map", "check"]
    assert _control_args("$B js 'x'") is None


def test_wi6_c12_every_quoted_control_py_line_parses():
    dead, per_doc = [], {}
    for path in _all_docs():
        text = _doc(path)
        rel = str(path.relative_to(REPO))
        per_doc[rel] = 0
        for n, snippet in _quoted(text):
            if snippet.startswith("$B"):
                continue
            args = _control_args(snippet)
            if args is None:
                continue
            per_doc[rel] += 1
            why = _parse_problem(args)
            if why:
                dead.append(f"{rel}:{n}: {snippet} -> {why}")
    assert dead == []
    assert all(c >= 1 for c in per_doc.values()), f"docs without a control.py line: {per_doc}"
    assert sum(per_doc.values()) >= 12, f"too few control.py lines: {per_doc}"
