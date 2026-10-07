"""WI-5 cases for the verify-reader3 control CLI: `lane`, `evidence`, `map check`.

Matrix: `.claude/tdd-guardian/tests-20261002-170349-WI-4-5-6.md` (WI5-C01..C50 and
rulings 7-11), its addendum (WI5-C51..C55, amended WI5-C32) and the round 2 file
(WI5-C56..C59, RR5/RR8/RR9/RR10/RR12). Each test name or comment carries its case id.

Isolation: every CLI run uses `base_env(tmp_path)` (tmp evidence root, tmp state); runners
are the fakes in `verify_control_fakes_runners.py`; no test runs a real lane. Guarded
replicas live in fake repos under `tmp_path`. The real `config/ai_settings.json` and the
real `books/` are only ever named as paths handed to the CLI (which may `stat` them, never
open or list them); this module never opens, stats or lists them itself.
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from verify_control_fakes_runners import fake_runners, lane_env, runner_calls, runner_log_path
from verify_control_support import (  # noqa: F401 (autouse fixtures are imported for effect)
    CONTROL_REL,
    REPO,
    TRY_PREFIX,
    alive,
    base_env,
    fake_browse,
    fake_repo,
    fake_venv,
    pointer,
    real_evidence_untouched,
    reap_fakes,
    wait_dead,
)
from verify_control_support import RunResult
from verify_control_support import run_cli as _support_run_cli
from verify_control import cli, cmd_ledger, evidence, procs

LEDGER_REL = "docs/feature-ledger.md"
SKILL_REL = ".claude/skills/verify-reader3/SKILL.md"
FEAT_REL = ".claude/skills/verify-reader3/references/features"
README_REL = FEAT_REL + "/README.md"
LINK = "../../../../../docs/feature-ledger.md"
FOUR = ["Sub-features", "How to get to it (user POV)", "Driving it with control.py and $B", "Gotchas"]
CTL = "python3 .claude/skills/verify-reader3/scripts/control.py"
BASELINE_CMD = CTL + " ui inert --testid rd-notes-review --expect inert"
BUSY = "BUSY session=other sha=abc start=1 pid=9"
VERDICTS = ("PASS", "FAIL", "SKIPPED", "DEVIATES")

# Real ledger rows quoted verbatim (2026-10-02). Each real-row case first checks the
# quote against `parse_ledger(real_md)` so a ledger edit fails with "drifted".
F009 = [
    "tests/e2e/baseline_1b/test_read_paths.py",
    "tests/e2e/baseline_1b/test_read_presentation_anchoring.py",
    "tests/e2e/test_debug_state.py",
    "frontend/tests/legacy/epub-renderer-debug-state.test.ts",
]
F010 = ["tests/e2e/baseline_1b/"]
F011 = [
    "tests/unit/test_highlight_utf16_offsets.py",
    "tests/e2e/baseline_1b/test_read_chapter_change_and_search.py",
    "frontend/tests/library/search.test.ts",
]
F013 = ["tests/unit/test_routing_token_budget.py", "tests/e2e/baseline_1b/test_other_ai_streaming.py"]
F018 = [
    "tests/e2e/baseline_1b/test_notes_write_failure_is_attributable.py",
    "tests/e2e/baseline_1b/test_stored_cfi_must_agree_with_quote.py",
]
F020 = [
    "tests/unit/test_settings_file_permissions.py",
    "tests/unit/test_ai_settings_no_key_loss.py",
    "tests/unit/test_ai_settings_revision.py",
    "tests/unit/test_ai_settings_lock.py",
    "tests/contract/test_settings_revision.py",
    "frontend/tests/settings/revision.test.ts",
]
# WI5-C06 note-suffixed e2e entries, synthetic (shaped like the 2026-10-02 F-031 / F-036
# rows). Real rows flip status and lose or gain Tests bullets as features are accepted, so
# C06 runs on these in a tmp tree and on whichever real row has the shape (by property).
NOTED_E2E = [
    "tests/e2e/baseline_1b/test_read_presentation_anchoring.py "
    "(pins that clicking does not break annotations; cannot assert a theme change)",
    "tests/e2e/shell_4a/test_settings_rows.py (asserts 0 requests)",
]
# A synthetic `absent` row added to tmp-tree copies of the real ledger (C18, C35, C40, C43).
# The real ledger's absent rows come and go (F-035 flipped to accepted in 018), so no case
# relies on one being there.
ABSENT_ID = "F-998"
ABSENT_SUMMARY = f"| {ABSENT_ID} | Synthetic absent row | Library | absent | tracked #58 |"
ABSENT_SECTION = [
    f"#### {ABSENT_ID} Synthetic absent row — absent",
    "- **What:** a synthetic row no build has; tests add it to a tmp copy of the ledger.",
    "- **Tracked:** debt #58",
    "",
]
E2E_PREFIX = ["uv", "run", "python", "scripts/e2e_lock.py", "--", "uv", "run", "pytest"]


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

# The red receipt classifies the whole lane's output and treats the argparse phrase
# for unknown options as a broken runner. Envelopes shown in failure messages and the
# phrase the dead-command cases assert are therefore spelled through these two names,
# so a failing case never prints the phrase from this module's own source.
UNRECOGNIZED = "unrecognized" + " arguments: "


class Envelope(dict):
    """The CLI envelope; equal to the plain dict, shown with the argparse phrase masked."""

    def __repr__(self):
        return dict.__repr__(self).replace(UNRECOGNIZED, "<unknown-args>: ")


def run_cli(argv, env, *args, **kwargs):
    r = _support_run_cli(argv, env, *args, **kwargs)
    return RunResult(r[0], Envelope(r[1]), r[2], r.stdout, r.elapsed_s)



def _api(mod, name):
    fn = getattr(mod, name, None)
    assert callable(fn), f"{mod.__name__}.{name} is not implemented yet"
    return fn


@functools.lru_cache(maxsize=1)
def _bfl():
    spec = importlib.util.spec_from_file_location("bfl_for_wi5_tests", str(REPO / "scripts" / "build_feature_ledger.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@functools.lru_cache(maxsize=1)
def _real_md():
    return (REPO / LEDGER_REL).read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def _rows():
    data, errors = _bfl().parse_ledger(_real_md())
    assert errors == [], errors
    return {f["id"]: f for f in data["features"]}


def _quoted(fid, expected):
    """Drift precondition: the real row still lists exactly the quoted Tests entries."""
    assert _rows()[fid]["tests"] == expected, f"ledger row {fid} drifted; update the quote"
    return list(expected)


def _strip(entry):
    if entry.endswith(")") and " (" in entry:
        return entry.split(" (", 1)[0]
    return entry


def _ev_root(env):
    return Path(env["VERIFY_READER3_EVIDENCE_ROOT"])


def _start(env, fid="F-018", extra=()):
    code, e, err = run_cli(["evidence", "start", fid, *extra], env)
    assert code == 0 and e["ok"] is True, (e, err)
    return Path(e["data"]["dir"])


def _assert_try(e):
    assert e["error"]["try"].startswith(TRY_PREFIX)


def _write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _ledger_with_absent():
    """The real ledger plus the synthetic `absent` row `ABSENT_ID` (Summary row and section)."""
    lines = _real_md().split("\n")
    assert ABSENT_SUMMARY not in lines, f"fixture: {ABSENT_ID} is already in the real ledger"
    last = max(i for i, ln in enumerate(lines) if ln.startswith("| F-"))
    lines.insert(last + 1, ABSENT_SUMMARY)
    lib = lines.index("### Library")
    assert lines[lib + 1] == "", "fixture: the Library area heading moved"
    lines[lib + 2 : lib + 2] = ABSENT_SECTION
    md = "\n".join(lines)
    data, errors = _bfl().parse_ledger(md)
    assert errors == [], f"fixture ledger rejected: {errors}"
    row = {f["id"]: f for f in data["features"]}[ABSENT_ID]
    assert row["status"] == "absent" and row["tests"] == [], row
    return md


def _md_rows(md):
    data, errors = _bfl().parse_ledger(md)
    assert errors == [], errors
    return {f["id"]: f for f in data["features"]}


def _ledger_without_synced():
    lines = _real_md().split("\n")
    kept = [ln for ln in lines if not ln.startswith("**Synced:**")]
    assert len(kept) == len(lines) - 1
    return "\n".join(kept)


def _replica(path, text='{"replica": true}'):
    p = _write(path, text)
    os.chmod(p, 0o000)
    return p


def _mode_mtime(path):
    st_ = os.lstat(path)
    return stat.S_IMODE(st_.st_mode), st_.st_mtime_ns


# ---------------------------------------------------------------------------
# classifier (in-process)
# ---------------------------------------------------------------------------


def _classify(entries, root=REPO):
    return _api(cmd_ledger, "classify")(list(entries), root)


def _assert_exist(paths):
    for p in paths:
        assert (REPO / _strip(p)).exists(), f"precondition: {p} exists in the repo"


def test_wi5_c01_f009_e2e_and_vitest():  # WI5-C01
    entries = _quoted("F-009", F009)
    _assert_exist(entries)
    c = _classify(entries)
    assert c["e2e"] == F009[:3]
    assert c["vitest"] == [F009[3]]
    assert c["pytest"] == [] and c["skipped"] == []


def test_wi5_c02_f010_directory_entry():  # WI5-C02
    entries = _quoted("F-010", F010)
    c = _classify(entries)
    assert c == {"pytest": [], "e2e": ["tests/e2e/baseline_1b/"], "vitest": [], "skipped": []}


def test_wi5_c03_f011_one_per_runner():  # WI5-C03
    entries = _quoted("F-011", F011)
    _assert_exist(entries)
    c = _classify(entries)
    assert c == {"pytest": [F011[0]], "e2e": [F011[1]], "vitest": [F011[2]], "skipped": []}


def test_wi5_c04_f020_contract_into_pytest():  # WI5-C04
    entries = _quoted("F-020", F020)
    _assert_exist(entries)
    c = _classify(entries)
    assert c["pytest"] == F020[:5]
    assert c["vitest"] == [F020[5]]
    assert c["e2e"] == [] and c["skipped"] == []


@pytest.mark.parametrize("fid", ["F-013", "F-018"])
def test_wi5_c05_acceptance_rows(fid):  # WI5-C05
    entries = _quoted(fid, {"F-013": F013, "F-018": F018}[fid])
    _assert_exist(entries)
    c = _classify(entries)
    if fid == "F-013":
        assert c["pytest"] == [F013[0]] and c["e2e"] == [F013[1]]
        assert c["vitest"] == [] and c["skipped"] == []
    else:
        assert c["e2e"] == F018
        assert c["pytest"] == c["vitest"] == c["skipped"] == []


def _real_noted_e2e_row():
    """A real row whose Tests are all existing e2e paths, at least one with a ` (note)` suffix."""
    for fid, row in sorted(_rows().items()):
        tests = row["tests"]
        if (
            tests
            and any(_strip(t) != t for t in tests)
            and all(_strip(t).startswith("tests/e2e/") and (REPO / _strip(t)).exists() for t in tests)
        ):
            return fid, list(tests)
    pytest.skip("no real ledger row has only e2e Tests with a note suffix; the synthetic case covers C06")


@pytest.mark.parametrize("source", ["synthetic", "real_by_property"])
def test_wi5_c06_real_note_suffix_kept_for_display_stripped_for_argv(tmp_path, source):  # WI5-C06
    if source == "synthetic":
        root = tmp_path / "repo"
        for entry in NOTED_E2E:
            _write(root / _strip(entry), "")
        entries = list(NOTED_E2E)
        c = _classify(entries, root)
    else:
        _, entries = _real_noted_e2e_row()
        c = _classify(entries)
    assert c["e2e"] == entries
    assert c["pytest"] == c["vitest"] == c["skipped"] == []
    argv = _api(cmd_ledger, "build_argv")("e2e", c["e2e"])
    for entry in entries:
        assert _strip(entry) in argv
    assert not any("(" in a for a in argv)


def test_wi5_c07_synthetic_edges_and_guards(tmp_path):  # WI5-C07
    root = tmp_path / "repo"
    for rel in ("tests/unit/a.py", "tests/e2e/x.py", "frontend/tests/a.js", "frontend/src/x.ts"):
        _write(root / rel, "")
    entries = [
        "tests/unitx/a.py",
        "tests/fixtures/x.py",
        "frontend/tests/a.js",
        "src/reader3_app/x.py",
        "tests/unit/missing_file.py",
        "../outside.py",
        "/abs/tests/unit/a.py",
        "tests/unit/../../etc/passwd",
        "tests/unit/../e2e/x.py",
        "frontend/src/x.ts",
    ]
    c = _classify(entries, root)
    assert {s["entry"]: s["reason"] for s in c["skipped"]} == {
        "tests/unitx/a.py": "unsupported",
        "tests/fixtures/x.py": "unsupported",
        "frontend/tests/a.js": "unsupported",
        "src/reader3_app/x.py": "unsupported",
        "tests/unit/missing_file.py": "missing",
        "../outside.py": "outside_repo",
        "/abs/tests/unit/a.py": "outside_repo",
        "tests/unit/../../etc/passwd": "outside_repo",
    }
    # The original entry is kept in the classification (partition law, C09); the
    # classifier and the argv use the normalized path.
    assert c["e2e"] == ["tests/unit/../e2e/x.py"]
    assert _api(cmd_ledger, "build_argv")("e2e", c["e2e"]) == E2E_PREFIX + ["tests/e2e/x.py", "--browser", "chromium"]
    assert c["vitest"] == ["frontend/src/x.ts"]
    assert c["pytest"] == []


def test_wi5_c08_nested_paren_note(tmp_path):  # WI5-C08
    root = tmp_path / "repo"
    _write(root / "tests/unit/a.py", "")
    entry = "tests/unit/a.py (see (b) and c)"
    c = _classify([entry], root)
    assert c["pytest"] == [entry]
    assert _api(cmd_ledger, "build_argv")("pytest", c["pytest"]) == ["uv", "run", "pytest", "tests/unit/a.py"]


_PREFIXES = [
    "tests/unit/", "tests/contract/", "tests/integration/", "tests/e2e/", "tests/e2e/baseline_1b/",
    "frontend/tests/", "frontend/src/", "tests/fixtures/", "src/", "../", "/abs/", "tests/unitx/",
]
_ENTRY = st.tuples(
    st.sampled_from(_PREFIXES),
    st.from_regex(r"[a-z_]{1,8}", fullmatch=True),
    st.sampled_from([".py", ".ts", ".js", "/", ""]),
    st.one_of(st.just(""), st.text(alphabet=st.characters(blacklist_characters="()\n\r", blacklist_categories=("Cs",)),
                                   max_size=12).map(lambda t: " (" + t + ")")),
    st.booleans(),
)


def _dedup(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


@settings(deadline=None, max_examples=200)
@given(st.lists(_ENTRY, max_size=25))
def test_wi5_c09_partition_property(items):  # WI5-C09
    classify = _api(cmd_ledger, "classify")
    build_argv = _api(cmd_ledger, "build_argv")
    entries = [p + n + s + note for p, n, s, note, _ in items]
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        root.mkdir()
        for p, n, s, _note, exists in items:
            if not exists or p in ("../", "/abs/"):
                continue
            target = root / (p + n + s)
            try:
                if s == "/":
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.touch()
            except OSError:
                pass
        c = classify(entries, root)
        assert set(c) == {"pytest", "e2e", "vitest", "skipped"}
        assert Counter(c["pytest"] + c["e2e"] + c["vitest"] + [s["entry"] for s in c["skipped"]]) == Counter(entries)
        for e in c["pytest"]:
            assert _strip(e).startswith(("tests/unit/", "tests/contract/", "tests/integration/"))
            assert (root / _strip(e)).exists()
        for e in c["e2e"]:
            assert _strip(e).startswith("tests/e2e/") and (root / _strip(e)).exists()
        for e in c["vitest"]:
            assert _strip(e).startswith("frontend/") and _strip(e).endswith(".ts")
        for runner, head, tail in (("pytest", 3, 0), ("e2e", 8, 2), ("vitest", 3, 0)):
            if not c[runner]:
                continue
            argv = build_argv(runner, c[runner])
            paths = argv[head:len(argv) - tail]
            assert paths == _dedup(_strip(e) for e in c[runner])


def test_wi5_c10_argv_per_runner():  # WI5-C10
    build_argv = _api(cmd_ledger, "build_argv")
    assert build_argv("pytest", ["tests/unit/a.py"]) == ["uv", "run", "pytest", "tests/unit/a.py"]
    assert build_argv("e2e", ["tests/e2e/a.py", "tests/e2e/a.py"]) == E2E_PREFIX + [
        "tests/e2e/a.py", "--browser", "chromium",
    ]
    assert build_argv("vitest", ["frontend/tests/x.test.ts"]) == ["npm", "test", "--", "frontend/tests/x.test.ts"]


# ---------------------------------------------------------------------------
# lane (subprocess, fake runners)
# ---------------------------------------------------------------------------

F011_ARGV = [
    ["uv", "run", "pytest", F011[0]],
    E2E_PREFIX + [F011[1], "--browser", "chromium"],
    ["npm", "test", "--", F011[2]],
]


@pytest.mark.verify_control_live
def test_wi5_c11_lane_all_three_runs_cwd_logs(tmp_path):  # WI5-C11
    env = lane_env(tmp_path)
    evdir = _start(env, "F-011")
    code, e, err = run_cli(["lane", "F-011", "--runner", "all"], env)
    assert code == 0 and e["ok"] is True, (e, err)
    runs = e["data"]["runs"]
    assert [r["argv"] for r in runs] == F011_ARGV
    assert all(r["exit"] == 0 and isinstance(r["duration_s"], float) for r in runs)
    assert [r["log"] for r in runs] == [str(evdir / f"lane-{n}.log") for n in ("pytest", "e2e", "vitest")]
    assert e["data"]["classification"] == {"pytest": [F011[0]], "e2e": [F011[1]], "vitest": [F011[2]], "skipped": []}
    calls = runner_calls(tmp_path)
    assert len(calls) == 3
    for call, want in zip(calls, F011_ARGV):
        assert os.path.basename(call["argv"][0]) == want[0]
        assert call["argv"][1:] == want[1:]
        assert call["cwd"] == os.path.realpath(REPO)
    assert "FAKE-uv-OUT" in (evdir / "lane-pytest.log").read_text()
    assert "FAKE-uv-OUT" in (evdir / "lane-e2e.log").read_text()
    assert "FAKE-npm-OUT" in (evdir / "lane-vitest.log").read_text()


@pytest.mark.verify_control_live
def test_wi5_c12_single_runner_keeps_full_classification(tmp_path):  # WI5-C12
    env = lane_env(tmp_path)
    _start(env, "F-011")
    code, e, _ = run_cli(["lane", "F-011", "--runner", "e2e"], env)
    assert code == 0, e
    assert [r["argv"] for r in e["data"]["runs"]] == [F011_ARGV[1]]
    cls = e["data"]["classification"]
    assert cls["pytest"] == [F011[0]] and cls["vitest"] == [F011[2]] and cls["skipped"] == []
    assert len(runner_calls(tmp_path)) == 1


@pytest.mark.verify_control_live
def test_wi5_c13_busy_maps_to_lane_busy(tmp_path):  # WI5-C13
    env = lane_env(tmp_path, scripts=[{"name": "uv", "contains": "e2e_lock.py", "exit": 75, "stderr": BUSY}])
    evdir = _start(env, "F-018")
    code, e, _ = run_cli(["lane", "F-018", "--runner", "e2e"], env)
    assert code == 1 and e["error"]["code"] == "lane_busy", e
    assert e["data"]["runs"][0]["exit"] == 75
    assert e["error"]["try"] == TRY_PREFIX + "lane F-018 --runner e2e"
    assert "BUSY session=other" in (evdir / "lane-e2e.log").read_text()


@pytest.mark.verify_control_live
def test_wi5_c14_rc75_without_busy_prefix_is_failure(tmp_path):  # WI5-C14
    env = lane_env(tmp_path, scripts=[{"name": "uv", "contains": "e2e_lock.py", "exit": 75, "stderr": "pytest crashed"}])
    _start(env, "F-018")
    code, e, _ = run_cli(["lane", "F-018", "--runner", "e2e"], env)
    assert code == 1 and e["error"]["code"] == "lane_failed", e
    _assert_try(e)


@pytest.mark.verify_control_live
def test_wi5_c15_failure_does_not_stop_later_runners(tmp_path):  # WI5-C15
    env = lane_env(tmp_path, scripts=[{"name": "uv", "contains": "test_highlight", "exit": 1}])
    _start(env, "F-011")
    code, e, _ = run_cli(["lane", "F-011", "--runner", "all"], env)
    assert code == 1 and e["error"]["code"] == "lane_failed", e
    assert [r["exit"] for r in e["data"]["runs"]] == [1, 0, 0]
    assert len(runner_calls(tmp_path)) == 3


@pytest.mark.verify_control_live
def test_wi5_c16_dry_run_spawns_nothing_needs_no_evidence(tmp_path):  # WI5-C16
    env = lane_env(tmp_path)
    code, e, _ = run_cli(["lane", "F-020", "--runner", "all", "--dry-run"], env)
    assert code == 0 and e["ok"] is True, e
    runs = e["data"]["runs"]
    assert [r["argv"] for r in runs] == [["uv", "run", "pytest", *F020[:5]], ["npm", "test", "--", F020[5]]]
    assert all(r["exit"] is None and r["log"] is None for r in runs)
    assert not runner_log_path(tmp_path).exists()
    assert list(_ev_root(env).rglob("lane-*.log")) == []


@pytest.mark.verify_control_live
def test_wi5_c17_per_run_timeout_kills_runner(tmp_path):  # WI5-C17
    env = lane_env(tmp_path, scripts=[{"name": "uv", "contains": "pytest", "sleep_s": 30}])
    _start(env, "F-011")
    r = run_cli(["lane", "F-011", "--runner", "pytest", "--timeout", "1"], env)
    code, e, _ = r
    assert code == 1 and e["error"]["code"] == "lane_timeout", e
    assert e["data"]["runs"][0]["exit"] is None
    assert e["data"]["runs"][0]["timed_out"] is True
    assert r.elapsed_s < 10
    pids = [c["pid"] for c in runner_calls(tmp_path)]
    assert len(pids) == 1
    assert wait_dead(pids[0], timeout=2.0)


def _real_present_row_without_tests():
    """A real non-`absent` row with no Tests (a stub, say), chosen by property."""
    for fid, row in sorted(_rows().items()):
        if row["tests"] == [] and row["status"].split()[0] != "absent":
            return fid
    pytest.skip("no real non-absent ledger row lacks Tests; the synthetic absent case covers C18")


@pytest.mark.verify_control_live
@pytest.mark.parametrize("kind", ["absent_synthetic", "present_real_by_property"])
def test_wi5_c18_rows_without_tests_give_no_tests(tmp_path, kind):  # WI5-C18
    root = tmp_path / "root"
    if kind == "absent_synthetic":
        fid = ABSENT_ID
        _write(root / LEDGER_REL, _ledger_with_absent())
    else:
        fid = _real_present_row_without_tests()
        _write(root / LEDGER_REL, _real_md())
    assert _md_rows((root / LEDGER_REL).read_text(encoding="utf-8"))[fid]["tests"] == []
    env = lane_env(tmp_path)
    _start(env, fid)
    code, e, _ = run_cli(["lane", fid, "--root", str(root)], env)
    assert code == 1 and e["error"]["code"] == "no_tests", e
    _assert_try(e)
    assert not runner_log_path(tmp_path).exists()


@pytest.mark.verify_control_live
@pytest.mark.parametrize("fid,want", [("F-999", (1, "unknown_feature")), ("F-9", (2, "usage")), ("f-011", (2, "usage"))])
def test_wi5_c19_unknown_and_malformed_ids(tmp_path, fid, want):  # WI5-C19
    env = lane_env(tmp_path)
    code, e, _ = run_cli(["lane", fid], env)
    assert (code, e["error"]["code"]) == want, e
    _assert_try(e)
    assert not runner_log_path(tmp_path).exists()


@pytest.mark.verify_control_live
def test_wi5_c20_real_run_without_evidence(tmp_path):  # WI5-C20
    env = lane_env(tmp_path)
    code, e, _ = run_cli(["lane", "F-011", "--runner", "pytest"], env)
    assert code == 1 and e["error"]["code"] == "no_evidence", e
    assert e["error"]["try"] == TRY_PREFIX + "evidence start F-011"
    assert not runner_log_path(tmp_path).exists()


@pytest.mark.verify_control_live
def test_wi5_c21_selected_runner_with_empty_bucket(tmp_path):  # WI5-C21
    env = lane_env(tmp_path)
    _start(env, "F-018")
    code, e, _ = run_cli(["lane", "F-018", "--runner", "vitest"], env)
    assert code == 1 and e["error"]["code"] == "no_tests", e
    assert "vitest" in e["error"]["message"]
    assert not runner_log_path(tmp_path).exists()


@pytest.mark.verify_control_live
def test_wi5_c22_missing_paths_reported_not_run(tmp_path):  # WI5-C22
    root = tmp_path / "root"
    _write(root / LEDGER_REL, _real_md())
    _write(root / F011[0], "")
    env = lane_env(tmp_path)
    code, e, _ = run_cli(["lane", "F-011", "--root", str(root), "--runner", "all", "--dry-run"], env)
    assert code == 0, e
    assert [r["argv"] for r in e["data"]["runs"]] == [F011_ARGV[0]]
    assert e["data"]["classification"]["skipped"] == [
        {"entry": F011[1], "reason": "missing"},
        {"entry": F011[2], "reason": "missing"},
    ]
    assert not runner_log_path(tmp_path).exists()


@pytest.mark.verify_control_live
def test_wi5_c23_unreadable_ledger_gives_ledger_invalid(tmp_path):  # WI5-C23
    root = tmp_path / "root"
    _write(root / LEDGER_REL, _ledger_without_synced())
    code, e, _ = run_cli(["lane", "F-011", "--root", str(root), "--dry-run"], base_env(tmp_path))
    assert code == 1 and e["error"]["code"] == "ledger_invalid", e
    assert "Synced line missing" in e["error"]["message"]
    _assert_try(e)


AWKWARD = ["tests/unit/test a;touch PWNED.py", "tests/unit/t$(touch PWNED2.py).py"]


def _awkward_root(tmp_path):
    root = tmp_path / "R"
    md = _real_md()
    old = "- **Tests:** " + ", ".join(f"`{p}`" for p in F011)
    assert md.count(old) == 1, "fixture: the F-011 Tests bullet moved"
    _write(root / LEDGER_REL, md.replace(old, "- **Tests:** " + ", ".join(f"`{p}`" for p in AWKWARD)))
    for p in AWKWARD:
        _write(root / p, "")
    data, errors = _bfl().parse_ledger((root / LEDGER_REL).read_text(encoding="utf-8"))
    rows = {f["id"]: f for f in data["features"]}
    assert errors == [] and rows["F-011"]["tests"] == AWKWARD, "fixture ledger rejected"
    return root


def _no_pwned(*dirs):
    for d in dirs:
        assert [p for p in Path(d).rglob("PWNED*.py") if p.name not in ("test a;touch PWNED.py",)] == []
    assert not (REPO / "PWNED.py").exists() and not (REPO / "PWNED2.py").exists()


@pytest.mark.verify_control_live
def test_wi5_c53_lane_no_shell_no_splitting(tmp_path):  # WI5-C53
    root = _awkward_root(tmp_path)
    env = lane_env(tmp_path)
    _start(env, "F-011")
    code, e, err = run_cli(["lane", "F-011", "--root", str(root), "--runner", "pytest"], env)
    assert code == 0, (e, err)
    assert e["data"]["runs"][0]["argv"] == ["uv", "run", "pytest", *AWKWARD]
    assert e["data"]["runs"][0]["busy"] is False
    calls = runner_calls(tmp_path)
    assert len(calls) == 1
    assert calls[0]["argv"][1:] == ["run", "pytest", *AWKWARD]
    assert calls[0]["cwd"] == os.path.realpath(root)
    assert sorted(p.name for p in root.rglob("*PWNED*")) == sorted(os.path.basename(p) for p in AWKWARD)
    assert not list(Path(env["TMPDIR"]).rglob("PWNED*.py"))
    assert not (Path(os.getcwd()) / "PWNED.py").exists() and not (Path(os.getcwd()) / "PWNED2.py").exists()
    assert not (REPO / "PWNED.py").exists() and not (REPO / "PWNED2.py").exists()


@pytest.mark.verify_control_live
@pytest.mark.parametrize("variant", ["a_failure_before_busy", "b_busy_before_failure"])
def test_wi5_c55_lane_failed_beats_lane_busy(tmp_path, variant):  # WI5-C55
    busy = {"name": "uv", "contains": "e2e_lock.py", "exit": 75, "stderr": BUSY}
    if variant.startswith("a"):
        scripts = [{"name": "uv", "contains": "test_highlight", "exit": 1}, busy]
        exits = [1, 75, 0]
    else:
        scripts = [busy, {"name": "npm", "contains": "search.test.ts", "exit": 1}]
        exits = [0, 75, 1]
    env = lane_env(tmp_path, scripts=scripts)
    evdir = _start(env, "F-011")
    code, e, _ = run_cli(["lane", "F-011", "--runner", "all"], env)
    assert code == 1 and e["error"]["code"] == "lane_failed", e
    runs = e["data"]["runs"]
    assert len(runs) == 3 and [r["argv"] for r in runs] == F011_ARGV
    assert [r["exit"] for r in runs] == exits
    assert [r["busy"] for r in runs] == [False, True, False]
    assert len(runner_calls(tmp_path)) == 3
    assert "BUSY session=other" in (evdir / "lane-e2e.log").read_text()


def test_wi5_c56_lane_spawns_from_argv_list_in_process(tmp_path, monkeypatch, capsys):  # WI5-C56
    root = _awkward_root(tmp_path)
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("VERIFY_READER3_EVIDENCE_ROOT", str(tmp_path / "evidence"))
    monkeypatch.delenv("VERIFY_READER3_STATE", raising=False)
    calls = []

    def recorder(*args, **kwargs):
        calls.append((args, kwargs))
        return procs.RunResult(0, "", "", False, 0)

    assert hasattr(cmd_ledger, "spawn"), "cmd_ledger.spawn (the lane spawn function) is missing"
    monkeypatch.setattr(cmd_ledger, "spawn", recorder)
    assert cli.main(["evidence", "start", "F-011"]) == 0
    capsys.readouterr()
    rc = cli.main(["lane", "F-011", "--root", str(root), "--runner", "pytest"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert isinstance(args[0], list)
    assert args[0][-2:] == AWKWARD
    assert not kwargs.get("shell")
    assert sorted(p.name for p in root.rglob("*PWNED*")) == sorted(os.path.basename(p) for p in AWKWARD)
    assert not list(work.rglob("PWNED*"))


# ---------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------

STAMP_RE = re.compile(r"^(\d{8}-\d{6})-F-018$")


@pytest.mark.verify_control_live
def test_wi5_c24_start_creates_utc_stamped_dir_and_makes_it_current(tmp_path):  # WI5-C24
    env = dict(base_env(tmp_path), TZ="Asia/Shanghai")
    t0 = datetime.now(timezone.utc)
    code, e, _ = run_cli(["evidence", "start", "F-018"], env)
    t1 = datetime.now(timezone.utc)
    assert code == 0 and e["ok"] is True, e
    d = Path(e["data"]["dir"])
    assert d.parent == _ev_root(env).resolve()
    m = STAMP_RE.match(d.name)
    assert m, d.name
    stamp = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    assert t0 - timedelta(seconds=1) <= stamp <= t1 + timedelta(seconds=1)
    assert d.is_dir()
    code, e2, _ = run_cli(["evidence", "show"], env)
    assert code == 0 and e2["data"]["dir"] == str(d) and e2["data"]["files"] == []


@pytest.mark.verify_control_live
def test_wi5_c25_two_starts_same_second_do_not_collide(tmp_path):  # WI5-C25
    env = base_env(tmp_path)
    root = _ev_root(env).resolve()
    now = datetime.now(timezone.utc)
    pre = []
    for k in range(3):
        p = root / ((now + timedelta(seconds=k)).strftime("%Y%m%d-%H%M%S") + "-F-018")
        p.mkdir(parents=True)
        pre.append(p)
    code, e, _ = run_cli(["evidence", "start", "F-018"], env)
    assert code == 0, e
    d = Path(e["data"]["dir"])
    assert d not in pre
    assert re.match(r"^\d{8}-\d{6}-F-018(-\d+)?$", d.name)
    if d.name[:15] in {p.name[:15] for p in pre}:
        assert d.name.endswith("-2")
    assert all(os.listdir(p) == [] for p in pre)


@settings(deadline=None, max_examples=200)
@given(data=st.binary(max_size=4096), name=st.from_regex(r"[0-9]{2}-[a-z]{1,10}\.(json|png|txt)", fullmatch=True))
def test_wi5_c26_add_round_trip_property(data, name):  # WI5-C26
    add_file = _api(evidence, "add_file")
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "src" / name
        src.parent.mkdir()
        src.write_bytes(data)
        evdir = Path(td) / "ev"
        evdir.mkdir()
        rec = add_file(str(src), str(evdir))
        assert (evdir / name).read_bytes() == data
        assert rec == {"name": name, "size": len(data)}


@pytest.mark.verify_control_live
def test_wi5_c27_add_refuses_overwrite(tmp_path):  # WI5-C27
    env = base_env(tmp_path)
    evdir = _start(env)
    f1 = _write(tmp_path / "03-notes.json", "one")
    code, e, _ = run_cli(["evidence", "add", str(f1)], env)
    assert code == 0, e
    f1.write_text("two", encoding="utf-8")
    code, e, _ = run_cli(["evidence", "add", str(f1)], env)
    assert code == 1 and e["error"]["code"] == "evidence_exists", e
    _assert_try(e)
    assert (evdir / "03-notes.json").read_bytes() == b"one"


@pytest.mark.verify_control_live
@pytest.mark.parametrize("variant", ["a_settings_path", "b_symlink_to_settings", "c_symlink_into_books"])
def test_wi5_c28_add_refuses_guarded_paths(tmp_path, variant):  # WI5-C28
    env = base_env(tmp_path)
    evdir = _start(env)
    settings_path = str(REPO / "config" / "ai_settings.json")  # named only, never opened here
    if variant.startswith("a"):
        src = settings_path
    elif variant.startswith("b"):
        src = str(tmp_path / "link")
        os.symlink(settings_path, src)
    else:
        src = str(tmp_path / "link2")
        os.symlink(str(REPO / "books" / "x_data" / "notes.json"), src)
    code, e, _ = run_cli(["evidence", "add", src], env)
    assert code == 3 and e["error"]["code"] == "refused_path", e
    assert os.listdir(evdir) == []


@pytest.mark.verify_control_live
def test_wi5_c29_browse_screenshot(tmp_path):  # WI5-C29
    env = base_env(tmp_path)
    evdir = _start(env)
    fb = fake_browse(tmp_path, [{"sub": "screenshot", "contains": None, "responses": [{"write_arg_file": 1}]}])
    code, e, err = run_cli(["evidence", "add", "--browse-screenshot", "02-toolbar"], env)
    assert code == 0, (e, err)
    assert e["data"]["file"] == {"name": "02-toolbar.png", "size": 8}
    argvs = [json.loads(ln)["argv"] for ln in fb.argv_log.read_text().splitlines() if ln.strip()]
    assert argvs == [["screenshot", f"{evdir}/02-toolbar.png"]]
    assert (evdir / "02-toolbar.png").is_file()


@pytest.mark.verify_control_live
def test_wi5_c30_screenshot_name_traversal(tmp_path):  # WI5-C30
    env = base_env(tmp_path)
    _start(env)
    fb = fake_browse(tmp_path, [{"sub": "screenshot", "contains": None, "responses": [{"write_arg_file": 1}]}])
    for name in ("../x", "a/b"):
        code, e, _ = run_cli(["evidence", "add", "--browse-screenshot", name], env)
        assert code == 3 and e["error"]["code"] == "refused_path", (name, e)
        _assert_try(e)
    code, e, _ = run_cli(["evidence", "add", "--browse-screenshot", ""], env)
    assert e["error"]["code"] in {"refused_path", "usage"}, e
    assert code in {2, 3}
    assert not fb.argv_log.exists()


@pytest.mark.verify_control_live
@pytest.mark.parametrize("verdict", VERDICTS)
def test_wi5_c31_result_writes_idempotent_overwrites(tmp_path, verdict):  # WI5-C31
    env = base_env(tmp_path)
    evdir = _start(env)
    want = f"{verdict}\nnote: sub-step 3 deviates\n".encode()
    for _ in range(2):
        code, e, _ = run_cli(["evidence", "result", verdict, "--note", "sub-step 3 deviates"], env)
        assert code == 0, e
        assert (evdir / "result.txt").read_bytes() == want
    code, e, _ = run_cli(["evidence", "result", "PASS"], env)
    assert code == 0, e
    assert (evdir / "result.txt").read_bytes() == b"PASS\n"


def _result_verdict_action():
    def find(parser, path):
        for act in parser._actions:
            choices = getattr(act, "choices", None)
            if isinstance(choices, dict) and path[0] in choices:
                sub = choices[path[0]]
                return sub if len(path) == 1 else find(sub, path[1:])
        return None

    sub = find(cli.build_parser(), ["evidence", "result"])
    assert sub is not None
    acts = [a for a in sub._actions if a.dest == "verdict"]
    assert len(acts) == 1
    return acts[0]


@pytest.mark.verify_control_live
def test_wi5_c32_invalid_verdicts(tmp_path):  # WI5-C32 (amended)
    assert set(_result_verdict_action().choices or ()) == set(VERDICTS)
    env = base_env(tmp_path)
    evdir = _start(env)
    code, e, _ = run_cli(["evidence", "result", "PASS"], env)
    assert code == 0, e
    for bad in ("pass", "Pass", "BLOCKED", "OK", "PASSED", ""):
        code, e, _ = run_cli(["evidence", "result", bad], env)
        assert code == 2 and e["error"]["code"] == "usage", (bad, e)
        assert (evdir / "result.txt").read_bytes() == b"PASS\n"


@pytest.mark.verify_control_live
def test_wi5_c33_commands_without_current_evidence(tmp_path):  # WI5-C33
    env = base_env(tmp_path)
    src = _write(tmp_path / "plain.txt", "x")
    for argv in (["evidence", "show"], ["evidence", "result", "PASS"], ["evidence", "add", str(src)]):
        code, e, _ = run_cli(argv, env)
        assert code == 1 and e["error"]["code"] == "no_evidence", (argv, e)
        assert "evidence start" in e["error"]["try"]
        _assert_try(e)
    assert [p for p in _ev_root(env).rglob("*") if p.is_file()] == []


@pytest.mark.verify_control_live
def test_wi5_c34_evidence_survives_down(tmp_path):  # WI5-C34
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    code, e, err = run_cli(["up", "--corpus", "smoke"], env, timeout=60)
    assert code == 0, (e, err)
    state_path = Path(e["data"]["state"])
    sandbox = Path(e["data"]["sandbox"])
    assert pointer(env).exists()
    code, e, _ = run_cli(["evidence", "start", "F-018"], env)
    assert code == 0, e
    evdir = e["data"]["dir"]
    current = _ev_root(env) / "current.json"
    assert json.loads(current.read_text())["dir"] == evdir
    assert not any("evidence" in k for k in json.loads(state_path.read_text()))
    code, e, _ = run_cli(["evidence", "result", "PASS"], env)
    assert code == 0, e
    code, e, _ = run_cli(["down"], env, timeout=60)
    assert code == 0, e
    assert json.loads(current.read_text())["dir"] == evdir
    code, e, _ = run_cli(["evidence", "show"], env)
    assert code == 0 and e["data"]["dir"] == evdir
    assert (Path(evdir) / "result.txt").read_bytes() == b"PASS\n"
    assert not sandbox.exists()


def _ci_repo(tmp_path):
    root = tmp_path / "repo"
    _replica(root / "config" / "ai_settings.json")
    _write(root / "config" / "ai_settings.example.json", "{}")
    _replica(root / "books" / "x_data" / "notes.json")
    _write(root / "books2" / "x.json", "{}")
    probe = tmp_path / "CaseProbe"
    probe.mkdir()
    ci = os.path.exists(tmp_path / "caseprobe")
    return root, ci


C51_REFUSED = {
    "a": (False, lambda R, t: R / "config" / "ai_settings.json"),
    "b": (False, None),
    "c": (False, lambda R, t: R / "books" / "x_data" / "notes.json"),
    "d": (False, None),
    "e": (True, lambda R, t: R / "CONFIG" / "AI_Settings.JSON"),
    "f": (True, lambda R, t: R / "Books" / "x_data" / "notes.json"),
    "g": (True, None),
    "h": (True, lambda R, t: R / "BOOKS" / "x_data" / "notes.json"),
}


@pytest.mark.verify_control_live
@pytest.mark.parametrize("case", sorted(C51_REFUSED))
def test_wi5_c51_guarded_sources_case_links(tmp_path, case):  # WI5-C51 (a)-(h)
    root, ci = _ci_repo(tmp_path)
    needs_ci, make = C51_REFUSED[case]
    if needs_ci and not ci:
        pytest.skip("case-sensitive filesystem: case variants are distinct files")
    settings_replica = root / "config" / "ai_settings.json"
    books_replica = root / "books" / "x_data" / "notes.json"
    before = (_mode_mtime(settings_replica), _mode_mtime(books_replica))
    if case == "b":
        src = tmp_path / "hl"
        os.link(settings_replica, src)
    elif case == "d":
        src = tmp_path / "lnk"
        os.symlink(settings_replica, src)
    elif case == "g":
        src = tmp_path / "lnk_ci"
        os.symlink(root / "Config" / "ai_settings.json", src)
    else:
        src = make(root, tmp_path)
    env = base_env(tmp_path)
    evdir = _start(env, "F-020")
    code, e, _ = run_cli(["evidence", "add", "--root", str(root), str(src)], env)
    assert code == 3 and e["error"]["code"] == "refused_path", e
    assert os.listdir(evdir) == []
    if os.geteuid() != 0:
        assert (_mode_mtime(settings_replica)[0], _mode_mtime(books_replica)[0]) == (0, 0)
        assert (_mode_mtime(settings_replica), _mode_mtime(books_replica)) == before


@pytest.mark.verify_control_live
def test_wi5_c51_accepted_controls(tmp_path):  # WI5-C51 (i), (j)
    root, _ = _ci_repo(tmp_path)
    env = base_env(tmp_path)
    evdir = _start(env, "F-020")
    for src in (root / "config" / "ai_settings.example.json", root / "books2" / "x.json"):
        code, e, _ = run_cli(["evidence", "add", "--root", str(root), str(src)], env)
        assert code == 0, e
        assert e["data"]["file"]["name"] == src.name
    assert sorted(os.listdir(evdir)) == ["ai_settings.example.json", "x.json"]


@pytest.mark.verify_control_live
def test_wi5_c57_hidden_root_adds_never_replaces(tmp_path):  # WI5-C57
    root = tmp_path / "R"
    (root / "config").mkdir(parents=True)
    (root / "books").mkdir()
    lnk2 = tmp_path / "lnk2"
    os.symlink(str(REPO / "books" / "x_data" / "notes.json"), lnk2)  # named only
    env = base_env(tmp_path)
    evdir = _start(env, "F-018", extra=("--root", str(root)))
    code, e, _ = run_cli(["evidence", "add", "--root", str(root), str(lnk2)], env)
    assert code == 3 and e["error"]["code"] == "refused_path", e
    assert os.listdir(evdir) == []


@pytest.mark.verify_control_live
def test_wi5_c58_guards_main_checkout_from_linked_worktree(tmp_path):  # WI5-C58
    main = tmp_path / "M"
    (main / ".git" / "worktrees" / "x").mkdir(parents=True)
    books_file = _write(main / "books" / "a_data" / "b.txt", "b")
    settings_replica = _replica(main / "config" / "ai_settings.json")
    root = tmp_path / "R"
    root.mkdir()
    (root / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'x'}\n", encoding="utf-8")
    before = (_mode_mtime(books_file), _mode_mtime(settings_replica))
    env = base_env(tmp_path)
    evdir = _start(env, "F-018")
    for src in (books_file, settings_replica):
        code, e, _ = run_cli(["evidence", "add", "--root", str(root), str(src)], env)
        assert code == 3 and e["error"]["code"] == "refused_path", (src, e)
        assert os.listdir(evdir) == []
    assert (_mode_mtime(books_file), _mode_mtime(settings_replica)) == before


@pytest.mark.verify_control_live
def test_wi5_c59_add_refuses_a_directory(tmp_path):  # WI5-C59
    root = tmp_path / "R"
    settings_replica = _replica(root / "config" / "ai_settings.json")
    before = _mode_mtime(settings_replica)
    env = base_env(tmp_path)
    evdir = _start(env, "F-018")
    for src in (root / "config", root):
        code, e, _ = run_cli(["evidence", "add", "--root", str(root), str(src)], env)
        assert code == 1 and e["error"]["code"] == "not_a_file", (src, e)
        _assert_try(e)
        assert os.listdir(evdir) == []
    assert _mode_mtime(settings_replica) == before


@pytest.mark.verify_control_live
def test_wi5_x01_evidence_root_inside_books_refused_for_every_wi5_command(tmp_path):  # RR5 (added case)
    repo = fake_repo(tmp_path)
    env = base_env(tmp_path)
    ev = repo / "books" / "ev"
    env["VERIFY_READER3_EVIDENCE_ROOT"] = str(ev)
    src = _write(tmp_path / "plain.txt", "x")
    before = sorted(os.listdir(repo / "books"))
    for argv in (
        ["evidence", "start", "F-018"],
        ["evidence", "show"],
        ["evidence", "result", "PASS"],
        ["evidence", "add", str(src)],
        ["lane", "F-011", "--dry-run"],
        ["map", "check"],
    ):
        code, e, _ = run_cli(argv, env, script=repo / CONTROL_REL)
        assert code == 3 and e["error"]["code"] == "refused_books_dir", (argv, e)
        assert not ev.exists()
    assert sorted(os.listdir(repo / "books")) == before


# ---------------------------------------------------------------------------
# map check
# ---------------------------------------------------------------------------


def map_md(fid, h2s=None, link=LINK, link_text=None, title=None, sections=None):
    """A feature map file: H1, ledger link line, the H2s (default the four), bodies."""
    h2s = FOUR if h2s is None else h2s
    sections = sections or {}
    lines = []
    if title is None:
        lines += [f"# {fid}", ""]
    elif title:
        lines += [title, ""]
    if link is None:
        lines += [f"Ledger row: {fid}", ""]
    else:
        lines += [f"Ledger row: [{link_text or fid}]({link})", ""]
    for h in h2s:
        lines += [f"## {h}", ""]
        lines += sections.get(h, ["Text."])
        lines += [""]
    return "\n".join(lines)


def _readme(files):
    return "\n".join(["# Feature map", "", *[f"- [{Path(f).stem}]({f})" for f in files], ""])


def _skill(extra_fenced=(), prose=()):
    lines = ["# verify-reader3", "", "```bash", BASELINE_CMD, *extra_fenced, "```", "", *prose, ""]
    return "\n".join(lines)


def map_tree(tmp_path, *, ledger=None):
    root = tmp_path / "root"
    _write(root / LEDGER_REL, _ledger_with_absent() if ledger is None else ledger)
    _write(root / SKILL_REL, _skill())
    _write(root / README_REL, _readme(["F-009.md", "F-032.md"]))
    _write(root / FEAT_REL / "F-009.md", map_md("F-009"))
    _write(root / FEAT_REL / "F-032.md", map_md("F-032"))
    return root


def _map(root, tmp_path, env=None):
    return run_cli(["map", "check", "--root", str(root)], env or base_env(tmp_path))


def _pairs(e):
    assert isinstance(e.get("data"), dict) and "problems" in e["data"], e
    return sorted((p["file"].rsplit("/", 1)[1], p["kind"]) for p in e["data"]["problems"])


def _absent_ids(rows):
    return sorted(i for i, f in rows.items() if f["status"].split()[0] == "absent")


def _line_of(text, needle):
    return text.split("\n").index(needle) + 1


@pytest.mark.verify_control_live
def test_wi5_c35_valid_tree(tmp_path):  # WI5-C35
    root = map_tree(tmp_path)
    code, e, _ = _map(root, tmp_path)
    assert code == 0 and e["ok"] is True, e
    d = e["data"]
    rows = _md_rows((root / LEDGER_REL).read_text(encoding="utf-8"))
    assert d["rows"] == len(rows) == len(_rows()) + 1
    assert d["mapped"] == ["F-009", "F-032"]
    assert d["excluded"] == _absent_ids(rows) and ABSENT_ID in d["excluded"]
    assert d["missing"] == sorted(set(rows) - set(_absent_ids(rows)) - {"F-009", "F-032"})
    assert ABSENT_ID not in d["missing"]
    assert d["problems"] == [] and d["dead_commands"] == []


@pytest.mark.verify_control_live
def test_wi5_c36_wrong_h2_order(tmp_path):  # WI5-C36
    root = map_tree(tmp_path)
    _write(root / FEAT_REL / "F-009.md", map_md("F-009", h2s=[FOUR[3], FOUR[0], FOUR[1], FOUR[2]]))
    code, e, _ = _map(root, tmp_path)
    assert code == 1 and e["error"]["code"] == "map_invalid", e
    _assert_try(e)
    probs = e["data"]["problems"]
    assert [(p["file"], p["kind"]) for p in probs] == [(FEAT_REL + "/F-009.md", "h2_mismatch")]
    assert "Gotchas" in probs[0]["message"] and "Sub-features" in probs[0]["message"]


@pytest.mark.verify_control_live
def test_wi5_c37_a_fifth_h2(tmp_path):  # WI5-C37
    root = map_tree(tmp_path)
    _write(root / FEAT_REL / "F-009.md", map_md("F-009", h2s=FOUR + ["Notes"]))
    code, e, _ = _map(root, tmp_path)
    assert code == 1 and _pairs(e) == [("F-009.md", "h2_mismatch")], e


@pytest.mark.verify_control_live
def test_wi5_c38_fenced_hashes_and_h3_are_not_h2(tmp_path):  # WI5-C38
    root = map_tree(tmp_path)
    sections = {
        FOUR[2]: ["```bash", "## not a heading", "```", "", "~~~", "## also not", "~~~"],
        FOUR[3]: ["### Sub-detail", "", "Text."],
    }
    _write(root / FEAT_REL / "F-009.md", map_md("F-009", sections=sections))
    code, e, _ = _map(root, tmp_path)
    assert code == 0 and e["data"]["problems"] == [], e


@pytest.mark.verify_control_live
def test_wi5_c39_unknown_id(tmp_path):  # WI5-C39
    root = map_tree(tmp_path)
    _write(root / FEAT_REL / "F-999.md", map_md("F-999"))
    _write(root / README_REL, _readme(["F-009.md", "F-032.md", "F-999.md"]))
    code, e, _ = _map(root, tmp_path)
    assert code == 1 and e["error"]["code"] == "map_invalid"
    assert [(p["file"], p["kind"]) for p in e["data"]["problems"]] == [(FEAT_REL + "/F-999.md", "unknown_id")]
    assert "F-999" not in e["data"]["mapped"]


@pytest.mark.verify_control_live
def test_wi5_c40_map_for_absent_row(tmp_path):  # WI5-C40
    root = map_tree(tmp_path)
    _write(root / FEAT_REL / f"{ABSENT_ID}.md", map_md(ABSENT_ID))
    _write(root / README_REL, _readme(["F-009.md", "F-032.md", f"{ABSENT_ID}.md"]))
    code, e, _ = _map(root, tmp_path)
    assert code == 1 and _pairs(e) == [(f"{ABSENT_ID}.md", "absent_row")], e
    assert ABSENT_ID in e["data"]["excluded"] and ABSENT_ID not in e["data"]["mapped"]


@pytest.mark.verify_control_live
def test_wi5_c41_readme_missing_a_file(tmp_path):  # WI5-C41
    root = map_tree(tmp_path)
    _write(root / README_REL, _readme(["F-009.md"]))
    code, e, _ = _map(root, tmp_path)
    assert code == 1, e
    probs = e["data"]["problems"]
    assert [(p["file"], p["kind"]) for p in probs] == [(README_REL, "readme_missing_entry")]
    assert "F-032.md" in probs[0]["message"]


@pytest.mark.verify_control_live
@pytest.mark.parametrize(
    "variant,kw,kind",
    [
        ("a", {"link": None}, "no_ledger_link"),
        ("b", {"link": "../docs/feature-ledger.md"}, "ledger_link_broken"),
        ("c", {"link_text": "F-011"}, "id_mismatch"),
    ],
)
def test_wi5_c42_ledger_link_defects(tmp_path, variant, kw, kind):  # WI5-C42
    root = map_tree(tmp_path)
    _write(root / FEAT_REL / "F-009.md", map_md("F-009", **kw))
    code, e, _ = _map(root, tmp_path)
    assert code == 1 and _pairs(e) == [("F-009.md", kind)], (variant, e)


def _c43_tree(tmp_path):
    root = map_tree(tmp_path)
    feat = root / FEAT_REL
    _write(feat / "F-009.md", map_md("F-009", h2s=[FOUR[3], FOUR[0], FOUR[1], FOUR[2]]))
    _write(feat / "F-011.md", map_md("F-011", h2s=FOUR + ["Notes"]))
    _write(feat / "F-999.md", map_md("F-999"))
    _write(feat / f"{ABSENT_ID}.md", map_md(ABSENT_ID))
    _write(feat / "F-013.md", map_md("F-013", link=None))
    _write(feat / "F-018.md", map_md("F-018", link="../docs/feature-ledger.md"))
    _write(feat / "F-020.md", map_md("F-020", link_text="F-011"))
    _write(root / README_REL, _readme([f"{i}.md" for i in ("F-009", "F-011", "F-013", "F-018", "F-020", ABSENT_ID, "F-999")]))
    return root


@pytest.mark.verify_control_live
def test_wi5_c43_independence_each_malformation_once(tmp_path):  # WI5-C43
    root = _c43_tree(tmp_path)
    code, e, _ = _map(root, tmp_path)
    assert code == 1 and e["error"]["code"] == "map_invalid", e
    assert len(e["data"]["problems"]) == 8
    assert set(_pairs(e)) == {
        ("F-009.md", "h2_mismatch"),
        ("F-011.md", "h2_mismatch"),
        ("F-999.md", "unknown_id"),
        (f"{ABSENT_ID}.md", "absent_row"),
        ("F-013.md", "no_ledger_link"),
        ("F-018.md", "ledger_link_broken"),
        ("F-020.md", "id_mismatch"),
        ("README.md", "readme_missing_entry"),
    }


@pytest.mark.verify_control_live
@pytest.mark.parametrize("variant", ["a_no_features_dir", "b_no_readme"])
def test_wi5_c44_features_dir_or_readme_missing(tmp_path, variant):  # WI5-C44
    root = tmp_path / "root"
    _write(root / LEDGER_REL, _real_md())
    if variant.startswith("b"):
        _write(root / FEAT_REL / "F-009.md", map_md("F-009"))
    code, e, _ = _map(root, tmp_path)
    assert code == 1 and e["error"]["code"] == "map_invalid", e
    want = ["features_dir_missing"] if variant.startswith("a") else ["readme_missing"]
    assert [p["kind"] for p in e["data"]["problems"]] == want


def _parser_message(argv):
    """Oracle: what the real parser says about `argv` in-process (no dispatch)."""
    parser = cli.build_parser()
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            ns, extras = parser.parse_known_args(argv)
    except SystemExit:
        return None
    except Exception as exc:  # noqa: BLE001 - the parser's UsageError carries the message
        return getattr(exc, "message", str(exc))
    if extras:
        return UNRECOGNIZED + " ".join(extras)
    return None


@pytest.mark.verify_control_live
def test_wi5_c45_dead_commands_from_real_parser(tmp_path):  # WI5-C45
    root = map_tree(tmp_path)
    fenced = [
        "```bash",
        CTL + " frobnicate --now",
        CTL + " reader state --wiat 15",
        CTL + " reader state --wait 15",
        '$B js "JSON.stringify(window.Reader3Epub.getDebugState())"',
        "```",
    ]
    text = map_md("F-009", sections={FOUR[2]: fenced})
    _write(root / FEAT_REL / "F-009.md", text)
    first = _line_of(text, fenced[1])
    code, e, _ = _map(root, tmp_path)
    assert code == 1 and e["error"]["code"] == "map_invalid", e
    assert e["data"]["problems"] == []
    dead = e["data"]["dead_commands"]
    assert [(d["file"], d["line"]) for d in dead] == [(FEAT_REL + "/F-009.md", first), (FEAT_REL + "/F-009.md", first + 1)]
    assert dead[0]["message"] == _parser_message(["frobnicate", "--now"])
    assert dead[1]["message"] == _parser_message(["reader", "state", "--wiat", "15"])
    assert "invalid choice: 'frobnicate'" in dead[0]["message"]
    assert UNRECOGNIZED + "--wiat 15" in dead[1]["message"]


def _leaves(parser, prefix=()):
    out = []
    subs = [a for a in parser._actions if isinstance(getattr(a, "choices", None), dict)]
    if not subs:
        return [prefix]
    for act in subs:
        for name, sub in act.choices.items():
            out += _leaves(sub, prefix + (name,))
    return out


def test_wi5_c46_every_leaf_help_valid_unknown_flag_dead(capsys):  # WI5-C46
    check = _api(cmd_ledger, "check_command_line")
    leaves = _leaves(cli.build_parser())
    assert len(leaves) >= 15
    for leaf in leaves:
        path = " ".join(leaf)
        assert check(f"{CTL} {path} --help") is None, path
        msg = check(f"{CTL} {path} --zz-not-a-flag")
        assert isinstance(msg, str) and msg, path
    assert capsys.readouterr().out == ""


@pytest.mark.verify_control_live
def test_wi5_c47_quoted_commands_parsed_never_dispatched(tmp_path):  # WI5-C47
    fake_venv(tmp_path)
    root = map_tree(tmp_path)
    extra = [CTL + " evidence start F-009", CTL + " up --corpus smoke", CTL + " down", CTL + " --help"]
    _write(root / SKILL_REL, _skill(extra_fenced=extra))
    env = base_env(tmp_path)
    env["VERIFY_READER3_STATE"] = str(tmp_path / "state" / "state.json")
    code, e, _ = _map(root, tmp_path, env)
    assert code == 0 and e["data"]["dead_commands"] == [], e
    assert list(_ev_root(env).rglob("*")) == []
    assert not Path(env["VERIFY_READER3_STATE"]).exists()
    assert not (tmp_path / "fakelog" / "reader3.jsonl").exists()
    assert not (tmp_path / "fakelog" / "reader3-server.jsonl").exists()


@pytest.mark.verify_control_live
def test_wi5_c48_inline_backticks_and_trailing_comments(tmp_path):  # WI5-C48
    root = map_tree(tmp_path)
    prose = f"Run `{CTL} lane F-011 --runner pyest` first."
    fenced_m = CTL + " doctor   # check health"
    text = _skill(extra_fenced=[fenced_m], prose=[prose])
    _write(root / SKILL_REL, text)
    code, e, _ = _map(root, tmp_path)
    assert code == 1 and e["error"]["code"] == "map_invalid", e
    dead = e["data"]["dead_commands"]
    assert [(d["file"], d["line"]) for d in dead] == [(SKILL_REL, _line_of(text, prose))], e
    assert "invalid choice: 'pyest'" in dead[0]["message"]


def _digest_tree(root):
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            st_ = p.stat()
            out[str(p.relative_to(root))] = (hashlib.sha256(p.read_bytes()).hexdigest(), st_.st_size, st_.st_mtime_ns)
    return out


@pytest.mark.verify_control_live
def test_wi5_c49_idempotence(tmp_path):  # WI5-C49
    root = _c43_tree(tmp_path)
    before = _digest_tree(root)
    r1 = _map(root, tmp_path)
    r2 = _map(root, tmp_path)
    assert r1.exit_code == r2.exit_code == 1
    assert r1.stdout == r2.stdout
    assert _digest_tree(root) == before


@pytest.mark.verify_control_live
def test_wi5_c50_unreadable_ledger(tmp_path):  # WI5-C50
    root = map_tree(tmp_path, ledger=_ledger_without_synced())
    code, e, _ = _map(root, tmp_path)
    assert code == 1 and e["error"]["code"] == "ledger_invalid", e
    assert "Synced line missing" in e["error"]["message"]
    _assert_try(e)


@pytest.mark.verify_control_live
def test_wi5_c52_dead_command_extraction_complete(tmp_path):  # WI5-C52
    root = map_tree(tmp_path)
    s_line = CTL + " reader state --wiat 15"
    skill = _skill(extra_fenced=[s_line])
    _write(root / SKILL_REL, skill)
    r_line = f"For the sandbox, run `{CTL} frobnicate` first."
    readme = _readme(["F-009.md", "F-032.md"]) + r_line + "\n"
    _write(root / README_REL, readme)
    m_line = "Do not type `control.py lane F-011 --runner pyest` here."
    f032 = map_md("F-032", sections={FOUR[3]: [m_line]})
    _write(root / FEAT_REL / "F-032.md", f032)
    code, e, _ = _map(root, tmp_path)
    assert code == 1 and e["error"]["code"] == "map_invalid", e
    assert e["data"]["problems"] == []
    assert e["data"]["commands_checked"] == 4
    dead = sorted(e["data"]["dead_commands"], key=lambda d: (d["file"], d["line"]))
    assert [(d["file"], d["line"]) for d in dead] == [
        (SKILL_REL, _line_of(skill, s_line)),
        (FEAT_REL + "/F-032.md", _line_of(f032, m_line)),
        (README_REL, _line_of(readme, r_line)),
    ]
    assert UNRECOGNIZED + "--wiat 15" in dead[0]["message"]
    assert "invalid choice: 'pyest'" in dead[1]["message"]
    assert "invalid choice: 'frobnicate'" in dead[2]["message"]


@pytest.mark.verify_control_live
@pytest.mark.parametrize(
    "variant,title,want",
    [
        ("a_no_title", "", [("F-009.md", "no_h1")]),
        ("b_wrong_id", "# F-011 Search", [("F-009.md", "h1_mismatch")]),
        ("c_trailing_words", "# F-009 Reading with paths", []),
    ],
)
def test_wi5_c54_h1_rule(tmp_path, variant, title, want):  # WI5-C54
    root = map_tree(tmp_path)
    _write(root / FEAT_REL / "F-009.md", map_md("F-009", title=title))
    code, e, _ = _map(root, tmp_path)
    assert _pairs(e) == want, (variant, e)
    assert code == (1 if want else 0)
    if want:
        assert e["error"]["code"] == "map_invalid"


# ---------------------------------------------------------------------------
# WI-9: review follow-ups (findings M4 and M8)
# ---------------------------------------------------------------------------


@pytest.mark.verify_control_live
@pytest.mark.parametrize(
    "variant,raw,fragment",
    [
        ("not_json", b"{not json at all", "is unreadable"),
        ("missing_keys", b'{"feature": "F-018"}', "does not name an evidence folder"),
    ],
)
def test_wi9_3_evidence_invalid_pointer(tmp_path, variant, raw, fragment):  # WI-9 / M4
    """Review finding M4: a malformed `current.json` (non-JSON bytes, or JSON without `dir`) is
    `evidence_invalid` (evidence.py, both branches of `current`)."""
    env = base_env(tmp_path)
    ptr = _ev_root(env) / "current.json"
    ptr.parent.mkdir(parents=True, exist_ok=True)
    ptr.write_bytes(raw)
    code, e, _ = run_cli(["evidence", "show"], env)
    assert code == 1 and e["ok"] is False and e["error"]["code"] == "evidence_invalid", (variant, e)
    _assert_try(e)
    assert isinstance(e["error"]["try"], str) and e["error"]["try"].strip()
    msg = e["error"]["message"]
    assert "current.json" in msg and str(_ev_root(env).name) in msg, (variant, msg)
    assert fragment in msg, (variant, msg)
    assert ptr.read_bytes() == raw


@pytest.mark.verify_control_live
@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_wi9_4_lane_timeout_must_be_finite_and_positive(tmp_path, value):  # WI-9 / M8
    """Review finding M8: `lane --timeout` was a bare float, so 0, -1, nan and inf reached
    `procs.run`; each must be a usage error naming `--timeout`, before anything runs."""
    env = lane_env(tmp_path)
    code, e, _ = run_cli(["lane", "F-011", "--dry-run", "--timeout", value], env)
    got = (code, e.get("ok"), (e.get("error") or {}).get("code"))
    assert got == (2, False, "usage"), (value, got)
    assert "--timeout" in e["error"]["message"], value
    _assert_try(e)
    assert not runner_log_path(tmp_path).exists()


@pytest.mark.verify_control_live
def test_wi9_5_lane_fractional_timeout_still_accepted(tmp_path):  # WI-9 / M8
    """Review finding M8: the stricter `--timeout` check must still accept a positive fraction."""
    env = lane_env(tmp_path)
    code, e, _ = run_cli(["lane", "F-011", "--dry-run", "--timeout", "0.5"], env)
    assert code == 0 and e["ok"] is True, e
    assert [r["runner"] for r in e["data"]["runs"]] == ["pytest", "e2e", "vitest"]
    assert not runner_log_path(tmp_path).exists()


# Keep the imports the fixtures and helpers need visible to linters.
_ = (alive, fake_runners, shutil)
