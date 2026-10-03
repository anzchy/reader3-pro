"""WI-1 core cases for the verify-reader3 control CLI.

Matrix: `.claude/tdd-guardian/tests-20261002-170349-WI-1.md`, its addendum and the
round 2 file. Each test name or comment carries its case id (WI1-Cnn).

In-process tests never connect (the lane's egress fence); anything that connects runs
as a bounded child. No test names the real `books/` or `config/`.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import http.client
import importlib.util
import io
import itertools
import json
import os
import pathlib
import re
import socket
import stat
import string
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from verify_control_support import (  # noqa: F401 (autouse fixtures are imported for effect)
    CONTROL_PY,
    REPO,
    SCRIPTS_DIR,
    TRY_PREFIX,
    alive,
    base_env,
    fake_repo,
    fake_venv,
    lstart,
    make_stub_script,
    pointer,
    real_evidence_untouched,
    reap_fakes,
    run_cli,
    run_cli_raw,
    snapshot_tree,
    spawn,
    wait_dead,
    wait_until,
)
from verify_control import cli, envelope, http_client, paths, procs, state

PKG_DIR = SCRIPTS_DIR / "verify_control"
EPOCH = "Thu Jan  1 00:00:00 1970"
TOP_LEVEL_COMMANDS = {
    "up", "doctor", "down", "book", "fs", "api", "ai", "reader", "ui", "lane", "evidence", "map",
}
ALL_COMMAND_PATHS = [
    ["up"], ["doctor"], ["down"], ["book", "add"], ["book", "index"], ["fs", "ls"], ["api"],
    ["ai", "ask"], ["reader", "state"], ["ui", "inert"], ["lane"], ["evidence", "start"], ["map", "check"],
]
SCHEMA_KEYS = {
    "sandbox", "books_dir", "ai_settings", "port", "base_url", "pid", "pid_start", "argv", "log",
    "token", "stub_pid", "stub_pid_start", "stub_port", "repo",
}
HIDDEN_KNOBS = (
    "VERIFY_READER3_HEALTH_TIMEOUT_S", "VERIFY_READER3_KILL_GRACE_S", "VERIFY_READER3_PROBE_TIMEOUT_S",
)


def _pkg_files():
    files = sorted(PKG_DIR.glob("*.py"))
    return files + [SCRIPTS_DIR / "control.py"]


def _refusal_code(exc_info):
    return getattr(exc_info.value, "code", None)


# ---------------------------------------------------------------------------
# WI1-C01, C02: run_cli helper self-test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "print('{\"ok\": true}'); print('{\"ok\": true}')",
        "print('not json')",
        "import sys; sys.stdout.write('{\"ok\": true}')",
    ],
    ids=["two-docs", "not-json", "no-newline"],
)
def test_c01_run_cli_rejects_anything_but_one_json_document(tmp_path, body):  # WI1-C01
    script = tmp_path / "two.py"
    script.write_text(body + "\n", encoding="utf-8")
    with pytest.raises(pytest.fail.Exception, match="exactly one JSON") as info:
        run_cli([], base_env(tmp_path), timeout=10, script=script)
    if "not json" in body:
        assert "not json" in str(info.value)
    else:
        assert '{"ok": true}' in str(info.value)


def test_c02_run_cli_fails_a_hung_child_and_kills_it(tmp_path):  # WI1-C02
    script = tmp_path / "hang.py"
    pid_file = tmp_path / "pid"
    script.write_text(
        "import os, sys, time\n"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        "print('BEFORE-HANG'); sys.stdout.flush()\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    with pytest.raises(pytest.fail.Exception, match="BEFORE-HANG"):
        run_cli([], base_env(tmp_path), timeout=1.0, script=script)
    pid = int(pid_file.read_text())
    assert wait_dead(pid, timeout=2.0)


# ---------------------------------------------------------------------------
# WI1-C03 .. C06: envelope
# ---------------------------------------------------------------------------


def test_c03_success_shape():  # WI1-C03
    env = envelope.success("up", {"port": 50123, "books": ["smoke_data"]})
    assert env == {"ok": True, "command": "up", "data": {"port": 50123, "books": ["smoke_data"]}, "error": None}
    out = envelope.render(env)
    assert out.count("\n") == 1 and out.endswith("\n")
    assert json.loads(out) == env
    assert envelope.exit_code(env) == 0


def test_c04_failure_shape_and_exit_codes():  # WI1-C04
    rows = [
        ("down", "refused_pid_identity"),
        ("up", "usage"),
        ("up", "server_exited"),
        ("doctor", "refused_x_unknown"),
        ("doctor", "refusedx"),
    ]
    codes = []
    for cmd, code in rows:
        env = envelope.failure(cmd, code, "msg", TRY_PREFIX + "doctor")
        assert env == {
            "ok": False,
            "command": cmd,
            "data": None,
            "error": {"code": code, "message": "msg", "try": TRY_PREFIX + "doctor"},
        }
        codes.append(envelope.exit_code(env))
    assert codes == [3, 2, 1, 3, 1]


@pytest.mark.parametrize(
    "bad_try",
    ["", "   ", "control.py up", "python3 control.py up", "python3 .claude/skills/verify-reader3/scripts/control.py"],
)
def test_c05_failure_refuses_a_non_runnable_try(bad_try):  # WI1-C05
    with pytest.raises(ValueError):
        envelope.failure("up", "server_exited", "m", bad_try)


_TRICKY = "\n\r   \x85阅读" + string.ascii_letters
_text = st.text(alphabet=st.one_of(st.sampled_from(list(_TRICKY)), st.characters(blacklist_categories=("Cs",))))
_json_value = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False, allow_infinity=False) | _text,
    lambda c: st.lists(c, max_size=4) | st.dictionaries(_text, c, max_size=4),
    max_leaves=12,
)
_try_tail = st.text(alphabet=[c for c in string.printable if c not in "\n\r\x0b\x0c"], min_size=1)


@settings(max_examples=300, deadline=None)
@given(
    ok=st.booleans(),
    command=_text,
    data=_json_value,
    code=st.one_of(st.sampled_from(["usage", "refused_books_dir", "server_exited", "not_implemented"]), _text.filter(bool)),
    message=_text,
    tail=_try_tail,
)
def test_c06_envelope_law(ok, command, data, code, message, tail):  # WI1-C06
    if ok:
        payload = data if isinstance(data, dict) else {"v": data}
        e = envelope.success(command, payload)
    else:
        payload = data if isinstance(data, dict) else None
        e = envelope.failure(command, code, message, TRY_PREFIX + tail, data=payload)
    out = envelope.render(e)
    assert len(out.splitlines()) == 1
    assert out.endswith("\n")
    assert json.loads(out) == e
    assert set(e) == {"ok", "command", "data", "error"}
    if ok:
        assert e["error"] is None
        expected = 0
    else:
        assert set(e["error"]) == {"code", "message", "try"}
        assert e["error"]["try"].startswith(TRY_PREFIX)
        expected = 2 if code == "usage" else 3 if code.startswith("refused_") else 1
    assert envelope.exit_code(e) == expected


# ---------------------------------------------------------------------------
# WI1-C07 .. C12: cli.main
# ---------------------------------------------------------------------------

USAGE_ROWS = [
    (["up", "--bogus"], "up", "--bogus", "up --help"),
    ([], "", None, "--help"),
    (["frobnicate"], "", "frobnicate", "--help"),
    (["up", "--port", "abc"], "up", "abc", "up --help"),
    (["up", "--port", "70000"], "up", "70000", "up --help"),
    (["ai", "ask"], "ai ask", None, "ai ask --help"),
    (["down", "--dry-run", "extra"], "down", None, "down --help"),
]


@pytest.mark.parametrize("argv,command,needle,try_tail", USAGE_ROWS, ids=[" ".join(r[0]) or "empty" for r in USAGE_ROWS])
def test_c07_usage_errors_become_a_usage_envelope(tmp_path, argv, command, needle, try_tail):  # WI1-C07
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    code, e, _ = run_cli(argv, env)
    assert code == 2
    assert e["ok"] is False
    assert e["error"]["code"] == "usage"
    assert e["command"] == command
    if needle:
        assert needle in e["error"]["message"]
    assert e["error"]["try"] == TRY_PREFIX + try_tail
    assert fv.calls("reader3") == [] and fv.calls("reader3-server") == []
    assert os.listdir(env["TMPDIR"]) == []
    assert not pointer(env).exists()


_unknown_token = st.text(alphabet=string.ascii_letters + string.digits + "-_", min_size=1).filter(
    lambda t: t not in TOP_LEVEL_COMMANDS and not t.startswith("-h") and t != "--help"
)
_bad_argv = st.one_of(
    st.lists(_unknown_token, min_size=1, max_size=4),
    st.builds(
        lambda path, flag: [*path, "--zz" + flag],
        st.sampled_from(ALL_COMMAND_PATHS),
        st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=8),
    ),
)


class _NoStdin:
    def read(self, *a, **k):
        raise AssertionError("stdin read")

    readline = read
    readlines = read

    def __iter__(self):
        raise AssertionError("stdin iterated")


@contextlib.contextmanager
def _tripwires(dispatched):
    def sentinel(k):
        def handler(ns):
            dispatched.append(k)
            raise AssertionError(f"dispatched {k}")

        return handler

    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(sys, "stdin", _NoStdin()))
        stack.enter_context(
            mock.patch.object(subprocess.Popen, "_execute_child", side_effect=AssertionError("spawned"))
        )
        for name in ("posix_spawn", "posix_spawnp", "fork", "system", "execv", "execve"):
            if hasattr(os, name):
                stack.enter_context(mock.patch(f"os.{name}", side_effect=AssertionError(name)))
        stack.enter_context(mock.patch.dict(cli.HANDLERS, {k: sentinel(k) for k in list(cli.HANDLERS)}))
        yield


def _main_captured(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main(list(argv))
    return rc, out.getvalue(), err.getvalue()


def test_c08_usage_totality_property(tmp_path):  # WI1-C08 (amended)
    dispatched: list = []
    with _tripwires(dispatched):
        # (w1) the sentinel is reachable
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cli.main(["doctor"])
        assert dispatched == ["doctor"]
        # (w2) the spawn tripwire sees the package's spawn path
        with pytest.raises(AssertionError, match="spawned"):
            procs.run(["true"], env={}, cwd=tmp_path, timeout=1)
        dispatched.clear()

        @settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
        @given(argv=_bad_argv)
        def prop(argv):
            rc, out, _ = _main_captured(argv)
            assert rc == 2, (argv, out)
            assert len(out.splitlines()) == 1
            doc = json.loads(out)
            assert doc["error"]["code"] == "usage"
            assert rc == envelope.exit_code(doc)
            assert dispatched == []

        prop()

    # static companion: no import binds a spawn primitive
    banned = re.compile(r"^(Popen|run|call|check_call|check_output|system|fork|forkpty|posix_spawnp?|exec\w*|spawn\w*)$")
    offenders = []
    for f in _pkg_files():
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module in ("subprocess", "os"):
                for alias in node.names:
                    if banned.match(alias.name):
                        offenders.append(f"{f.name}:{node.lineno} {alias.name}")
    assert offenders == []


HELP_GROUPS = ["up", "doctor", "down", "book", "fs", "api", "ai", "reader", "ui", "lane", "evidence", "map"]
GROUP_SUBCOMMANDS = {
    "book": ["add", "index"],
    "fs": ["ls", "stat", "cat"],
    "reader": ["state", "select"],
    "evidence": ["start", "add", "result", "show"],
    "map": ["check"],
    "ai": ["ask"],
    "ui": ["inert"],
}
HELP_ARGVS = (
    [["--help"]]
    + [[g, "--help"] for g in HELP_GROUPS]
    + [["book", "add", "--help"], ["ai", "ask", "--help"], ["evidence", "result", "--help"], ["map", "check", "--help"]]
)


@pytest.mark.parametrize("argv", HELP_ARGVS, ids=[" ".join(a) for a in HELP_ARGVS])
def test_c09_help_lists_subcommands_and_runnable_examples(tmp_path, argv):  # WI1-C09
    res = run_cli_raw(argv, base_env(tmp_path))
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert "Examples:" in out
    path = " ".join(argv[:-1])
    lines = [ln.strip() for ln in out.splitlines()]
    if path:
        assert any(ln.startswith(TRY_PREFIX + path) for ln in lines), out
    else:
        for g in HELP_GROUPS:
            assert any(ln.startswith(TRY_PREFIX + g) for ln in lines), (g, out)
    if len(argv) == 2 and argv[0] in GROUP_SUBCOMMANDS:
        for sub in GROUP_SUBCOMMANDS[argv[0]]:
            assert re.search(rf"\b{sub}\b", out), (sub, out)
    with pytest.raises(ValueError):
        json.loads(out)
    for knob in HIDDEN_KNOBS:
        assert knob not in out


# Owner tags: each later WI deletes its own rows when it implements the command.
STUB_ROWS = [
]


def test_c10_every_invocation_prints_one_envelope_matching_its_exit(tmp_path):  # WI1-C10
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    for argv, _ in STUB_ROWS + [(["up", "--bogus"], "up")]:
        code, e, _ = run_cli(argv, env)
        assert set(e) == {"ok", "command", "data", "error"}
        assert code == envelope.exit_code(e)
    code, e, _ = run_cli(["doctor"], env)
    assert (code, e["error"]["code"], e["error"]["try"]) == (1, "no_instance", TRY_PREFIX + "up")
    code, e, _ = run_cli(["down"], env)
    assert code == 0 and e["ok"] is True
    assert e["data"]["already_stopped"] is True and e["data"]["removed_sandbox"] is False
    code, e, _ = run_cli(["doctor", "--state", str(tmp_path / "missing.json")], env)
    assert (code, e["error"]["code"]) == (1, "no_instance")
    assert set(e) == {"ok", "command", "data", "error"}
    assert os.listdir(env["TMPDIR"]) == []


def _popen_with_open_stdin(argv, env):
    proc = subprocess.Popen(
        [sys.executable, str(CONTROL_PY), *argv],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=env["TMPDIR"],
        text=True,
    )
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        pytest.fail(f"{argv} blocked with stdin open (it read stdin)")
    out = proc.stdout.read()
    proc.stdin.close()
    proc.stdout.close()
    proc.stderr.close()
    return proc.returncode, out


def test_c11_no_command_reads_stdin(tmp_path):  # WI1-C11
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    for argv in (["doctor"], ["down"], ["up"]):
        rc, out = _popen_with_open_stdin(argv, env)
        assert out.count("\n") == 1 and out.endswith("\n"), out
        json.loads(out)
    code, e, _ = run_cli(["down"], env)
    assert code == 0, e
    offenders = []
    for f in _pkg_files():
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "stdin"
                and isinstance(node.value, ast.Name)
                and node.value.id == "sys"
            ):
                offenders.append(f"{f.name}:{node.lineno} sys.stdin")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "input":
                offenders.append(f"{f.name}:{node.lineno} input()")
            if isinstance(node, ast.Import) and any(a.name == "getpass" for a in node.names):
                offenders.append(f"{f.name}:{node.lineno} import getpass")
            if isinstance(node, ast.ImportFrom) and node.module == "getpass":
                offenders.append(f"{f.name}:{node.lineno} from getpass")
    assert offenders == []


def test_c12_crashing_handler_yields_internal_error():  # WI1-C12
    def raise_runtime(ns):
        raise RuntimeError("kaboom-7f3")

    with mock.patch.dict(cli.HANDLERS, {"doctor": raise_runtime}):
        rc, out, err = _main_captured(["doctor"])
    assert rc == 1
    assert len(out.splitlines()) == 1
    e = json.loads(out)
    assert e["error"]["code"] == "internal_error"
    assert "kaboom-7f3" in e["error"]["message"]
    assert e["error"]["try"].startswith(TRY_PREFIX)
    assert "Traceback" in err


@pytest.mark.parametrize("argv,command", STUB_ROWS, ids=[r[1] + ":" + " ".join(r[0]) for r in STUB_ROWS])
def test_c13_stubs_and_hooks_return_not_implemented(tmp_path, argv, command):  # WI1-C13
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    code, e, _ = run_cli(argv, env)
    assert code == 1
    assert e["error"]["code"] == "not_implemented"
    assert e["command"] == command
    assert command in e["error"]["message"]
    assert e["error"]["try"].startswith(TRY_PREFIX)
    if argv[0] == "up":
        assert fv.calls("reader3") == [] and fv.calls("reader3-server") == []
        assert os.listdir(env["TMPDIR"]) == []
        assert not pointer(env).exists()
    assert os.listdir(tmp_path / "evidence") == []


# ---------------------------------------------------------------------------
# WI1-C14, C15: guard 1
# ---------------------------------------------------------------------------


def _guard_tree(tmp_path):
    repo = tmp_path / "fakerepo"
    if repo.exists():
        return repo
    (repo / "books" / "a_data").mkdir(parents=True)
    (repo / "books2").mkdir()
    (repo / "elsewhere").mkdir()
    (repo / "link_in").symlink_to(repo / "books" / "a_data")
    (repo / "link_dir").symlink_to(repo / "books")
    (repo / "books" / "out").symlink_to(Path("..") / "elsewhere")
    (tmp_path / "repolink").symlink_to(repo)
    (tmp_path / "sbx" / "books").mkdir(parents=True)
    return repo


def _assert_refused(p, repo):
    with pytest.raises(paths.GuardRefusal) as info:
        paths.guard_books_dir(p, repo)
    assert _refusal_code(info) == "refused_books_dir"
    assert os.path.realpath(p) in str(info.value)


def test_c14_guard1_examples(tmp_path):  # WI1-C14
    repo = _guard_tree(tmp_path)
    before = snapshot_tree(tmp_path)
    refused = [
        repo / "books",
        str(repo / "books") + "/",
        repo / "books" / "a_data",
        repo / "books" / "new" / "not" / "yet",
        repo / "link_in",
        repo / "link_dir" / "z",
        tmp_path / "repolink" / "books" / "x",
        str(repo / "elsewhere") + "/../books/z",
    ]
    accepted = [
        repo / "books2",
        str(repo / "books2") + "/../books2/y",
        repo / "books" / "out",
        tmp_path / "sbx" / "books",
        repo,
    ]
    for p in refused:
        _assert_refused(str(p), repo)
    for p in accepted:
        assert paths.guard_books_dir(str(p), repo) == os.path.realpath(p)
    case_folded = repo / "BOOKS" / "z"
    if os.path.exists(repo / "BOOKS"):
        _assert_refused(str(case_folded), repo)
    else:
        assert paths.guard_books_dir(str(case_folded), repo) == os.path.realpath(case_folded)
    assert snapshot_tree(tmp_path) == before


def _guard_oracle(p, books):
    r = os.path.realpath(p)
    return any(os.path.exists(a) and os.path.samefile(a, books) for a in [r, *map(str, Path(r).parents)])


def test_c15_guard1_property(tmp_path):  # WI1-C15
    repo = _guard_tree(tmp_path)
    before = snapshot_tree(tmp_path)

    @settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        segs=st.lists(
            st.sampled_from(["books", "books2", "BOOKS", "a_data", "link_in", "link_dir", "out", "elsewhere", "..", ".", "new"]),
            min_size=1,
            max_size=6,
        )
    )
    def prop(segs):
        p = os.path.join(str(repo), *segs)
        expected = _guard_oracle(p, repo / "books")
        try:
            got = paths.guard_books_dir(p, repo)
            refused = False
        except paths.GuardRefusal as exc:
            assert exc.code == "refused_books_dir"
            refused = True
        assert refused == expected, p
        if not refused:
            assert got == os.path.realpath(p)

    prop()
    assert snapshot_tree(tmp_path) == before


# ---------------------------------------------------------------------------
# WI1-C16, C17: sandbox_deletable
# ---------------------------------------------------------------------------


def test_c16_sandbox_shape_examples(tmp_path):  # WI1-C16
    T = tmp_path / "t"
    (T / "verify-reader3.abc").mkdir(parents=True)
    (T / "notours").mkdir()
    (T / "sub" / "verify-reader3.x").mkdir(parents=True)
    (tmp_path / "victim").mkdir()
    (T / "verify-reader3.link").symlink_to(tmp_path / "victim")
    (T / "verify-reader3.f").write_text("f")
    (tmp_path / "tlink").symlink_to(T)
    before = snapshot_tree(tmp_path)
    true_rows = [T / "verify-reader3.abc", str(T / "verify-reader3.abc") + "/", tmp_path / "tlink" / "verify-reader3.abc"]
    false_rows = [
        T / "notours", T / "sub" / "verify-reader3.x", T, T / "verify-reader3.link", T / "verify-reader3.f",
        T / "verify-reader3.gone", "/", "", "verify-reader3.abc",
    ]
    assert [paths.sandbox_deletable(str(p), str(T)) for p in true_rows] == [True] * 3
    assert [paths.sandbox_deletable(str(p), str(T)) for p in false_rows] == [False] * len(false_rows)
    assert snapshot_tree(tmp_path) == before


def test_c17_sandbox_shape_property(tmp_path):  # WI1-C17
    T = tmp_path / "t"
    (T / "verify-reader3.a" / "inner").mkdir(parents=True)
    (T / "plain").mkdir()
    (T / "verify-reader3.f").write_text("f")
    (tmp_path / "victim").mkdir()
    (T / "verify-reader3.l").symlink_to(tmp_path / "victim")
    (T / "verify-reader3.ok").symlink_to(T / "verify-reader3.a")

    def oracle(p):
        if not os.path.isabs(p):
            return False
        r = os.path.realpath(p)
        rt = os.path.realpath(T)
        return (
            os.path.isdir(r)
            and os.path.basename(r).startswith("verify-reader3.")
            and os.path.samefile(os.path.dirname(r), rt)
            and r != rt
        )

    @settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        segs=st.lists(
            st.sampled_from(["verify-reader3.a", "verify-reader3.l", "verify-reader3.ok", "verify-reader3.f", "plain", "inner", "..", "."]),
            min_size=1,
            max_size=4,
        )
    )
    def prop(segs):
        p = os.path.join(str(T), *segs)
        assert paths.sandbox_deletable(p, str(T)) == oracle(p), p

    prop()


# ---------------------------------------------------------------------------
# WI1-C18, C19, C79: sandbox_env
# ---------------------------------------------------------------------------

E2E_CONFTEST = REPO / "tests" / "e2e" / "conftest.py"
# RR6 (round 2) wins over the frozen reference: server children are always offline.
OFFLINE = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}


def _server_env_ref():
    spec = importlib.util.spec_from_file_location("_e2e_conftest_vc", E2E_CONFTEST)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._server_env


def _ref(server_env, parent, sandbox):
    with mock.patch.dict(os.environ, parent, clear=True):
        want = server_env(sandbox / "books")
    return {**want, **OFFLINE}


def _sandbox(tmp_path):
    s = Path(tempfile.mkdtemp(prefix="verify-reader3.", dir=tmp_path)).resolve()
    (s / "books").mkdir()
    return s


def test_c18_sandbox_env_equals_frozen_reference(tmp_path):  # WI1-C18
    server_env = _server_env_ref()
    S = _sandbox(tmp_path)
    P = {k: os.environ[k] for k in ("PATH", "HOME", "LANG") if k in os.environ}
    P.update(
        {
            "READER3_TOKEN": "leak-token",
            "READER3_LIBRARY_UI": "classic",
            "READER3_EMBED_MODEL": "evil-model",
            "READER3_PORT": "8123",
            "READER3_BOOKS_DIR": "/definitely/not/here",
            "READER3_AI_SETTINGS": str(tmp_path / "developers_own.json"),
        }
    )
    P_copy = dict(P)
    want = _ref(server_env, P, S)
    assert procs.sandbox_env(S, parent=P) == want
    assert procs.sandbox_env(S, token="t0k", parent=P) == {**want, "READER3_TOKEN": "t0k"}
    assert sorted(k for k in want if k.startswith("READER3_")) == ["READER3_AI_SETTINGS", "READER3_BOOKS_DIR"]
    assert want["READER3_AI_SETTINGS"] == str(S / "ai_settings.json")
    assert os.path.isabs(want["READER3_AI_SETTINGS"])
    assert P == P_copy


def test_c19_sandbox_env_property(tmp_path):  # WI1-C19
    server_env = _server_env_ref()
    S = _sandbox(tmp_path)
    keys = st.one_of(
        st.builds(lambda s: "READER3_" + s, st.text(alphabet=string.ascii_uppercase + string.digits + "_", max_size=12)),
        st.text(alphabet=string.ascii_uppercase + "_", min_size=1, max_size=12),
    )
    values = st.text(alphabet=st.characters(blacklist_characters="\x00", blacklist_categories=("Cs",)), max_size=20)

    @settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(P=st.dictionaries(keys=keys, values=values, max_size=12), token=st.none() | st.text(min_size=1, alphabet=string.printable))
    def prop(P, token):
        P_copy = dict(P)
        got = procs.sandbox_env(S, token=token, parent=P)
        assert got == {**_ref(server_env, P, S), **({"READER3_TOKEN": token} if token else {})}
        for k, v in P.items():
            if not k.startswith("READER3_") and k not in OFFLINE:
                assert got[k] == v
        assert P == P_copy

    prop()


def test_c79_sandbox_env_forces_offline_in_process(tmp_path):  # WI1-C79 (in-process half)
    S = _sandbox(tmp_path)
    got = procs.sandbox_env(S, parent={"PATH": "/usr/bin", "HF_HUB_OFFLINE": "0", "TRANSFORMERS_OFFLINE": "0"})
    assert got["HF_HUB_OFFLINE"] == "1" and got["TRANSFORMERS_OFFLINE"] == "1"


# ---------------------------------------------------------------------------
# WI1-C20, C21: identity
# ---------------------------------------------------------------------------

_L = "Thu Oct  2 17:03:49 2026"
_BASE_CMD = "/v/bin/python3 /v/bin/reader3-server --port 51234"


def test_c20_identity_truth_table_through_pid_is_ours():  # WI1-C20 (amended)
    rows = []
    expected = []
    for marker_ok, port_ok, lstart_ok in itertools.product([True, False], repeat=3):
        cmd = _BASE_CMD if marker_ok else "/v/bin/python3 /v/bin/sleep --port 51234"
        rows.append((cmd, _L if lstart_ok else EPOCH, "reader3-server", 51234 if port_ok else 51235))
        expected.append(marker_ok and port_ok and lstart_ok)
    rows += [
        ("/v/bin/python3 /v/bin/reader3-server --port 8080", _L, "reader3-server", 80),  # t1
        ("/v/bin/python3 /x/reader3-server-old --port 51234", _L, "reader3-server", 51234),  # t2
        ("vim notes-reader3-server.txt --port 51234", _L, "reader3-server", 51234),  # t3
        ("/v/bin/python3 /r/verify_control/ai_stub_runner.py --state-dir D --gate", _L, "ai_stub_runner.py", None),  # t4
    ]
    expected += [False, False, False, True]
    got = []
    for cmd, lst, marker, port in rows:
        with mock.patch.object(procs, "read_identity", return_value=procs.Identity(cmd, lst)):
            got.append(procs.pid_is_ours(4242, _L, marker, port=port))
    with mock.patch.object(procs, "read_identity", return_value=None):  # t5
        got.append(procs.pid_is_ours(4242, _L, "reader3-server", port=51234))
    expected.append(False)
    assert got == expected


def test_c21_read_identity_and_pid_is_ours_on_real_processes(tmp_path):  # WI1-C21 (amended)
    p1 = spawn(["sleep", "60"], tmp_path)
    fv = fake_venv(tmp_path, server="no_listen")
    p2 = spawn([fv.bin / "reader3-server", "--port", "51234"], tmp_path)
    p3 = spawn(["sleep", "60"], tmp_path)
    p3.kill()
    p3.wait(10)
    p4 = spawn([sys.executable, make_stub_script(tmp_path)], tmp_path)
    assert wait_until(lambda: len(fv.calls("reader3-server")) == 1, timeout=10)
    ident = procs.read_identity(p1.pid)
    assert ident.lstart == lstart(p1.pid)
    assert "sleep" in ident.command
    assert procs.pid_is_ours(p2.pid, lstart(p2.pid), "reader3-server", port=51234) is True
    assert procs.pid_is_ours(p2.pid, EPOCH, "reader3-server", port=51234) is False
    assert procs.pid_is_ours(p2.pid, lstart(p2.pid), "reader3-server", port=51235) is False
    assert procs.pid_is_ours(p1.pid, lstart(p1.pid), "reader3-server", port=51234) is False
    assert procs.pid_is_ours(p4.pid, lstart(p4.pid), "ai_stub_runner.py") is True
    assert procs.read_identity(p3.pid) is None
    assert procs.pid_is_ours(p3.pid, "x", "sleep") is False
    assert hasattr(procs, "identity_matches") is False
    assert alive(p1.pid) and alive(p2.pid) and alive(p4.pid)


# ---------------------------------------------------------------------------
# WI1-C22, C23: procs.run
# ---------------------------------------------------------------------------

_GRANDCHILD = (
    "import subprocess, sys, time\n"
    "gc = subprocess.Popen(['sleep', '60'])\n"
    "open(sys.argv[1], 'w').write(str(gc.pid))\n"
    "time.sleep(60)\n"
)


def test_c22_timeout_kills_the_process_group(tmp_path):  # WI1-C22
    gc_file = tmp_path / "gc.pid"
    t0 = time.monotonic()
    res = procs.run([sys.executable, "-c", _GRANDCHILD, str(gc_file)], env=dict(os.environ), cwd=tmp_path, timeout=1.0)
    assert time.monotonic() - t0 < 5
    assert res.timed_out is True
    assert res.exit != 0
    assert wait_until(gc_file.exists, timeout=2)
    gc = int(gc_file.read_text())
    assert wait_dead(res.pid, 2.0)
    assert wait_dead(gc, 2.0)


def test_c23_run_captures_output_and_closes_stdin(tmp_path):  # WI1-C23
    code = "import sys; d=sys.stdin.read(); print('got', len(d)); print('E', file=sys.stderr); sys.exit(4)"
    res = procs.run([sys.executable, "-c", code], env=dict(os.environ), cwd=tmp_path, timeout=5)
    assert (res.exit, res.stdout, res.stderr, res.timed_out) == (4, "got 0\n", "E\n", False)


# ---------------------------------------------------------------------------
# WI1-C24 .. C26: state
# ---------------------------------------------------------------------------

_any_text = st.text(alphabet=st.one_of(st.sampled_from(list("阅读 书 ")), st.characters(blacklist_categories=("Cs",))))
_state_dict = st.builds(
    lambda paths_, port, stub_port, argv, token, base_url, pid_pair, stub_pair: {
        "sandbox": paths_[0],
        "books_dir": paths_[1],
        "ai_settings": paths_[2],
        "log": paths_[3],
        "repo": paths_[4],
        "port": port,
        "stub_port": stub_port,
        "argv": argv,
        "token": token,
        "base_url": base_url,
        "pid": pid_pair[0],
        "pid_start": pid_pair[1],
        "stub_pid": stub_pair[0],
        "stub_pid_start": stub_pair[1],
    },
    st.lists(_any_text.filter(bool), min_size=5, max_size=5),
    st.none() | st.integers(1, 65535),
    st.none() | st.integers(1, 65535),
    st.lists(_any_text, max_size=4),
    st.none() | _any_text,
    _any_text,
    st.one_of(st.tuples(st.integers(1, 2**22), _any_text), st.tuples(st.none(), st.none())),
    st.one_of(st.tuples(st.none(), st.none()), st.tuples(st.integers(1, 2**22), _any_text)),
)


def test_c24_state_round_trip(tmp_path):  # WI1-C24 (amended)
    @settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(d=_state_dict)
    def prop(d):
        path = Path(tempfile.mkdtemp(dir=tmp_path)) / "state.json"
        state.write(path, d)
        assert state.read(path) == d
        assert set(d) == SCHEMA_KEYS
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        assert os.listdir(path.parent) == ["state.json"]

    prop()

    good = {k: None for k in SCHEMA_KEYS}
    good.update({"sandbox": "/s", "books_dir": "/s/books", "ai_settings": "/s/a", "log": "/s/l", "repo": "/r",
                 "argv": [], "base_url": "http://127.0.0.1:1", "port": 1, "pid": 1, "pid_start": "x"})
    bad1 = dict(good, stub_pid=5, stub_pid_start=None)
    bad2 = {k: v for k, v in good.items() if k != "stub_pid_start"}
    for i, bad in enumerate((bad1, bad2)):
        p = tmp_path / f"bad{i}.json"
        p.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(state.StateError) as info:
            state.read(p)
        assert info.value.code == "bad_state"


def test_c25_resolution_order_and_pointer(tmp_path):  # WI1-C25
    files = {}
    for name in "ABC":
        files[name] = tmp_path / f"{name}.json"
        files[name].write_text("{}", encoding="utf-8")
    ev = tmp_path / "ev"
    ptr = ev / "instance.json"
    for a, b, c in itertools.product([0, 1], repeat=3):
        cli_state = str(files["A"]) if a else None
        env = {"VERIFY_READER3_STATE": str(files["B"])} if b else {}
        if c:
            state.write_pointer(ev, files["C"])
            assert json.loads(ptr.read_text()) == {"state": str(files["C"])}
        else:
            state.clear_pointer(ev)
        expected = files["A"] if a else files["B"] if b else files["C"] if c else None
        got = state.resolve(cli_state, env, ptr)
        assert (Path(got) if got is not None else None) == expected, (a, b, c)
    assert state.pointer_path({"VERIFY_READER3_EVIDENCE_ROOT": str(ev)}, repo=Path("/x")) == ptr
    assert state.pointer_path({}, repo=Path("/r")) == Path("/r/.claude/verify-evidence/instance.json")
    assert not Path("/r").exists()
    state.clear_pointer(ev)
    state.clear_pointer(ev)
    assert not ptr.exists()
    ev.mkdir(exist_ok=True)
    ptr.write_text("{", encoding="utf-8")
    with pytest.raises(state.StateError) as info:
        state.resolve(None, {}, ptr)
    assert info.value.code == "bad_pointer"


def test_c26_malformed_state_is_bad_state_and_untouched(tmp_path):  # WI1-C26
    env = base_env(tmp_path)
    s1 = tmp_path / "s1.json"
    s1.write_text("{", encoding="utf-8")
    s2 = tmp_path / "s2.json"
    good = {k: None for k in SCHEMA_KEYS}
    good.update({"sandbox": "/s", "books_dir": "/s/books", "ai_settings": "/s/a", "log": "/s/l", "repo": "/r",
                 "argv": [], "base_url": "http://127.0.0.1:1", "port": 1, "pid_start": "x"})
    s2.write_text(json.dumps(dict(good, pid="not-an-int")), encoding="utf-8")
    listing = sorted(os.listdir(tmp_path))
    for s in (s1, s2):
        before = (s.read_bytes(), s.stat().st_mtime_ns)
        for cmd in ("doctor", "down"):
            code, e, _ = run_cli([cmd, "--state", str(s)], env)
            assert (code, e["error"]["code"]) == (1, "bad_state"), e
        assert (s.read_bytes(), s.stat().st_mtime_ns) == before
    assert sorted(os.listdir(tmp_path)) == listing


# ---------------------------------------------------------------------------
# WI1-C27: static scan for the guarded config literal
# ---------------------------------------------------------------------------

_FORBIDDEN_CALLS = {"open", "read_text", "read_bytes", "Path", "exists", "stat", "is_file", "load", "loads"}
_READ_CALLS = {"open", "read_text", "read_bytes", "load", "loads"}


def _call_name(node):
    f = node.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def _is_str(node, value=None):
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and (value is None or node.value == value)


def _contains_config(node):
    return any(_is_str(n, "config") for n in ast.walk(node))


def _scan_config_literal(path):
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    allowed = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and _is_str(body[0].value):
                allowed.add(body[0].value)
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            if any(re.match(r".*HINT.*", n) for n in names) and node.value is not None:
                allowed.update(ast.walk(node.value))
            if path.name == "paths.py" and names == ["GUARDED_CONFIG_REL"] and isinstance(node.value, ast.Tuple):
                allowed.update(ast.walk(node.value))
        if isinstance(node, ast.keyword) and node.arg == "hint":
            allowed.update(ast.walk(node.value))
    suspects = []
    for node in ast.walk(tree):
        if _is_str(node) and "config/ai_settings.json" in node.value:
            suspects.append(node)
        elif _is_str(node, "ai_settings.json"):
            parent = parents.get(node)
            paired = False
            if isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div) and _contains_config(parent):
                paired = True
            if isinstance(parent, ast.Call) and _call_name(parent) == "join" and any(_is_str(a, "config") for a in parent.args):
                paired = True
            if isinstance(parent, ast.Tuple) and any(_is_str(a, "config") for a in parent.elts):
                paired = True
            if paired:
                suspects.append(node)
    offenders = []
    for node in suspects:
        if node not in allowed:
            offenders.append(f"{path.name}:{node.lineno} not in a docstring/hint/constant")
        p = parents.get(node)
        while p is not None:
            if isinstance(p, ast.Call) and _call_name(p) in _FORBIDDEN_CALLS:
                offenders.append(f"{path.name}:{node.lineno} inside {_call_name(p)}()")
                break
            p = parents.get(p)
    # GUARDED_CONFIG_REL: referenced only in paths.py; functions using it never read files.
    for node in ast.walk(tree):
        refs = (isinstance(node, ast.Name) and node.id == "GUARDED_CONFIG_REL") or (
            isinstance(node, ast.Attribute) and node.attr == "GUARDED_CONFIG_REL"
        )
        if refs and path.name != "paths.py":
            offenders.append(f"{path.name}:{node.lineno} references GUARDED_CONFIG_REL")
    if path.name == "paths.py":
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                uses = any(isinstance(n, ast.Name) and n.id == "GUARDED_CONFIG_REL" for n in ast.walk(fn))
                if uses:
                    for n in ast.walk(fn):
                        if isinstance(n, ast.Call) and _call_name(n) in _READ_CALLS:
                            offenders.append(f"paths.py:{n.lineno} {fn.name} calls {_call_name(n)}")
    return offenders


def test_c27_config_literal_only_in_docstrings_hints_or_the_constant():  # WI1-C27 (amended)
    offenders = []
    for f in _pkg_files():
        offenders += _scan_config_literal(f)
    assert offenders == []
    assert paths.GUARDED_CONFIG_REL == ("config", "ai_settings.json")


# ---------------------------------------------------------------------------
# WI1-C29, C80: package hygiene
# ---------------------------------------------------------------------------

REQUIRED_MODULES = {
    "__init__", "cli", "envelope", "paths", "state", "procs", "http_client", "corpus", "cmd_instance",
    "cmd_books", "cmd_api", "cmd_ai", "cmd_reader", "cmd_ledger", "evidence",
}
_BLE_LINE = re.compile(r"^\s*except\s*(\(.*\b(Base)?Exception\b.*\)|(Base)?Exception\b|\s*:)")


def _top_imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield node.lineno, a.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module


def test_c29_layout_and_language_level():  # WI1-C29
    modules = {f.stem for f in PKG_DIR.glob("*.py")}
    assert REQUIRED_MODULES <= modules
    problems = []
    for f in _pkg_files():
        src = f.read_text(encoding="utf-8")
        n_lines = len(src.splitlines())
        cap = 60 if f.name == "control.py" else 400
        if n_lines > cap:
            problems.append(f"{f.name}: {n_lines} lines > {cap}")
        tree = ast.parse(src, feature_version=(3, 10))
        for node in ast.walk(tree):
            if type(node).__name__ == "TryStar":
                problems.append(f"{f.name}:{node.lineno} except*")
            if isinstance(node, ast.Attribute) and node.attr == "UTC" and isinstance(node.value, ast.Name) and node.value.id == "datetime":
                problems.append(f"{f.name}:{node.lineno} datetime.UTC")
            if isinstance(node, ast.ImportFrom) and node.module == "datetime" and any(a.name == "UTC" for a in node.names):
                problems.append(f"{f.name}:{node.lineno} from datetime import UTC")
        for lineno, name in _top_imports(tree):
            top = name.split(".")[0]
            if top == "tomllib":
                problems.append(f"{f.name}:{lineno} tomllib")
            if top in sys.stdlib_module_names or top == "verify_control":
                pass
            elif top in ("epub_corpus", "epub_zip") and f.name == "corpus.py":
                pass
            else:
                problems.append(f"{f.name}:{lineno} non-stdlib import {name}")
            if f.name == "http_client.py" and (name == "urllib.request"):
                problems.append(f"http_client.py:{lineno} urllib.request")
        if f.name == "http_client.py":
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "urllib" and any(a.name == "request" for a in node.names):
                    problems.append(f"http_client.py:{node.lineno} from urllib import request")
        for i, line in enumerate(src.splitlines(), 1):
            if _BLE_LINE.match(line) and "# noqa: BLE001 - " not in line:
                problems.append(f"{f.name}:{i} broad except without '# noqa: BLE001 - <reason>'")
    assert problems == []


def test_c80_no_shell_anywhere():  # WI1-C80
    files = _pkg_files()
    assert len(files) >= 15
    offenders = []
    for f in files:
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg == "shell" and not (isinstance(kw.value, ast.Constant) and kw.value.value is False):
                    offenders.append(f"{f.name}:{node.lineno} shell=")
            fn = node.func
            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
                pair = (fn.value.id, fn.attr)
                if pair in {("os", "system"), ("os", "popen"), ("subprocess", "getoutput"), ("subprocess", "getstatusoutput")}:
                    offenders.append(f"{f.name}:{node.lineno} {pair[0]}.{pair[1]}")
    assert offenders == []


# ---------------------------------------------------------------------------
# WI1-C63 (a)-(c), C64 (a)-(c), C76: two protected roots
# ---------------------------------------------------------------------------


def test_c63_guard1_when_the_books_root_is_a_symlink(tmp_path):  # WI1-C63 (a)-(c)
    R = fake_repo(tmp_path)
    (R / "books").rmdir()
    (tmp_path / "ext_lib").mkdir()
    (R / "books").symlink_to(tmp_path / "ext_lib")
    (tmp_path / "ext_lib2").mkdir()
    before = snapshot_tree(tmp_path)
    # (a)
    for p in (
        tmp_path / "ext_lib" / "x",
        R / "books" / "y",
        tmp_path / "ext_lib",
        tmp_path / "ext_lib" / "new" / "deeper" / "leaf",
    ):
        _assert_refused(str(p), R)
    # (b)
    for p in (tmp_path / "ext_lib2", tmp_path / "elsewhere" / "books"):
        assert paths.guard_books_dir(str(p), R) == os.path.realpath(p)
    assert snapshot_tree(tmp_path) == before
    # (c) dangling root
    (R / "books").unlink()
    (R / "books").symlink_to(tmp_path / "ext_missing")
    before = snapshot_tree(tmp_path)
    _assert_refused(str(tmp_path / "ext_missing" / "x"), R)
    _assert_refused(str(R / "books" / "z"), R)
    p = tmp_path / "ext_missing2" / "x"
    assert paths.guard_books_dir(str(p), R) == os.path.realpath(p)
    assert snapshot_tree(tmp_path) == before


def _roots_row(tmp_path, i, M, setup):
    repo = tmp_path / f"r{i}"
    repo.mkdir()
    setup(repo)
    return repo


def test_c64_protected_books_roots_table(tmp_path):  # WI1-C64 (a)-(c)
    M = tmp_path / "main"
    M.mkdir()

    def gitfile(content, mode=None):
        def setup(repo):
            g = repo / ".git"
            if isinstance(content, bytes):
                g.write_bytes(content)
            else:
                g.write_bytes(content.encode("utf-8"))
            if mode is not None:
                os.chmod(g, mode)

        return setup

    def mk_worktree_dir(repo):
        (M / ".git" / "worktrees" / "x").mkdir(parents=True, exist_ok=True)
        gitfile(f"gitdir: {M}/.git/worktrees/x\n")(repo)

    rows = [
        ("a1", lambda r: None, 1),
        ("a2", lambda r: (r / ".git").mkdir(), 1),
        ("a3", gitfile(f"gitdir: {M}/.git/worktrees/x\n"), 2),
        ("a4", mk_worktree_dir, 2),
        ("a5", gitfile("gitdir: ../main/.git/worktrees/x\r\n"), 2),
        ("a6", gitfile(f"gitdir:   {M}/.git/worktrees/x   "), 2),
        ("a7", gitfile(""), 1),
        ("a8", gitfile("gitdir:"), 1),
        ("a9", gitfile("nonsense\n"), 1),
        ("a10", gitfile(f"gitdir: {M}/.git/modules/sub"), 1),
        ("a11", gitfile(f"gitdir: {M}/worktrees/x"), 1),
        ("a12", gitfile(b"\xff\xfe\x00gitdir"), 1),
        ("a13", lambda r: (r / ".git").symlink_to(tmp_path / "nowhere"), 1),
    ]
    if os.geteuid() != 0:
        rows.append(("a14", gitfile(f"gitdir: {M}/.git/worktrees/x", mode=0o000), 1))
    repos = {}
    for i, (rid, setup, n) in enumerate(rows):
        repo = _roots_row(tmp_path, i, M, setup)
        repos[rid] = repo
        want = [Path(os.path.abspath(repo / "books"))]
        if n == 2:
            want.append(Path(os.path.abspath(M / "books")))
        assert [Path(p) for p in paths.protected_books_roots(repo)] == want, rid
    # (b) no spawn, no argument
    with mock.patch.object(subprocess.Popen, "_execute_child", side_effect=AssertionError("spawned")), mock.patch(
        "os.posix_spawn", side_effect=AssertionError
    ):
        assert [Path(p) for p in paths.protected_books_roots(repos["a3"])] == [
            Path(os.path.abspath(repos["a3"] / "books")),
            Path(os.path.abspath(M / "books")),
        ]
        assert [Path(p) for p in paths.protected_books_roots(repos["a9"])] == [Path(os.path.abspath(repos["a9"] / "books"))]
        default = [Path(p) for p in paths.protected_books_roots()]
    assert default == [Path(p) for p in paths.protected_books_roots(REPO)]
    assert default[0] == Path(os.path.abspath(REPO / "books"))
    git = REPO / ".git"
    if git.is_file():
        first = git.read_text(encoding="utf-8").splitlines()[0]
        m = re.match(r"^gitdir:\s*(.+?)\s*$", first)
        if m and Path(m.group(1)).parent.name == "worktrees" and Path(m.group(1)).parent.parent.name == ".git":
            assert len(default) == 2
    # (c)
    (M / "books" / "tmp").mkdir(parents=True)
    (M / "books2").mkdir()
    _assert_refused(str(M / "books" / "tmp"), repos["a3"])
    assert paths.guard_books_dir(str(M / "books2"), repos["a3"]) == os.path.realpath(M / "books2")


@contextlib.contextmanager
def _open_tripwires(allow=()):
    allowed = {os.path.realpath(str(a)) for a in allow}
    real_open, real_io_open, real_os_open = builtins.open, io.open, os.open

    def check(file):
        if isinstance(file, int):
            raise AssertionError("opened fd")
        if os.path.realpath(os.fspath(file)) not in allowed:
            raise AssertionError(f"opened {file}")

    def b_open(file, *a, **k):
        check(file)
        return real_open(file, *a, **k)

    def i_open(file, *a, **k):
        check(file)
        return real_io_open(file, *a, **k)

    def o_open(file, *a, **k):
        check(file)
        return real_os_open(file, *a, **k)

    with mock.patch("builtins.open", b_open), mock.patch("io.open", i_open), mock.patch("os.open", o_open), mock.patch.object(
        pathlib.Path, "open", side_effect=AssertionError("Path.open")
    ) if not allowed else contextlib.nullcontext():
        yield


def test_c76_is_guarded_source_both_roots(tmp_path):  # WI1-C76
    R = fake_repo(tmp_path)
    M = tmp_path / "main"
    (R / ".git").write_text(f"gitdir: {M}/.git/worktrees/x\n", encoding="utf-8")
    (M / "books" / "a_data").mkdir(parents=True)
    (M / "books" / "a_data" / "b.txt").write_text("b")
    (R / "books" / "c_data").mkdir()
    (R / "config" / "ai_settings.json").write_text("r-sentinel")
    (M / "config").mkdir()
    (M / "config" / "ai_settings.json").write_text("m-sentinel")
    (R / "config" / "other.json").write_text("o")
    (tmp_path / "plain.json").write_text("p")
    (tmp_path / "sl").symlink_to(M / "config" / "ai_settings.json")
    os.link(R / "config" / "ai_settings.json", tmp_path / "hl.json")
    (tmp_path / "bl").symlink_to(M / "books" / "a_data")
    (R / "books2" / "x").mkdir(parents=True)
    sentinels = [R / "config" / "ai_settings.json", M / "config" / "ai_settings.json"]
    before = [(s.stat().st_size, s.stat().st_mtime_ns) for s in sentinels]
    true_rows = [
        M / "books" / "a_data" / "b.txt",
        R / "books" / "c_data" / "new" / "leaf",
        M / "books",
        tmp_path / "bl" / "b.txt",
        R / "config" / "ai_settings.json",
        M / "config" / "ai_settings.json",
        tmp_path / "sl",
        tmp_path / "hl.json",
    ]
    false_rows = [R / "config" / "other.json", tmp_path / "plain.json", R / "books2" / "x", tmp_path / "main" / "booksX" / "y"]
    with _open_tripwires():
        got_true = [paths.is_guarded_source(str(p), R) for p in true_rows]
        got_false = [paths.is_guarded_source(str(p), R) for p in false_rows]
        folded = paths.is_guarded_source(str(R / "BOOKS" / "z"), R)
    assert got_true == [True] * len(true_rows)
    assert got_false == [False] * len(false_rows)
    assert folded is os.path.exists(R / "BOOKS")
    assert [(s.stat().st_size, s.stat().st_mtime_ns) for s in sentinels] == before
    (M / "config" / "ai_settings.json").unlink()
    with _open_tripwires():
        assert paths.is_guarded_source(str(M / "config" / "ai_settings.json"), R) is True


# ---------------------------------------------------------------------------
# WI1-C70 (a): BaseException totality
# ---------------------------------------------------------------------------


class _Weird(BaseException):
    pass


@pytest.mark.parametrize(
    "exc,code",
    [
        (SystemExit(5), "internal_error"),
        (SystemExit(0), "internal_error"),
        (SystemExit(None), "internal_error"),
        (SystemExit("msg"), "internal_error"),
        (KeyboardInterrupt(), "interrupted"),
        (_Weird(), "internal_error"),
    ],
    ids=["exit5", "exit0", "exitNone", "exitmsg", "kbint", "weird"],
)
def test_c70a_base_exceptions_still_yield_one_envelope(exc, code):  # WI1-C70 (a)
    def raiser(ns):
        raise exc

    with mock.patch.dict(cli.HANDLERS, {"doctor": raiser}):
        try:
            rc, out, _ = _main_captured(["doctor"])
        except BaseException as e:  # noqa: BLE001 - the case asserts nothing escapes main
            pytest.fail(f"escaped: {e!r}")
    assert rc == 1
    assert len(out.splitlines()) == 1
    e = json.loads(out)
    assert e["error"]["code"] == code
    assert e["command"] == "doctor"
    assert e["error"]["try"].startswith(TRY_PREFIX)
    if isinstance(exc, SystemExit) and exc.code == 5:
        assert "SystemExit" in e["error"]["message"]


def test_c70b_sigint_during_doctor_probe_is_interrupted(tmp_path):  # WI1-C70 (b)
    import signal

    fv = fake_venv(tmp_path, probe="hang")
    env = base_env(tmp_path)
    code, up, _ = run_cli(["up"], env)
    assert code == 0, up
    try:
        c = subprocess.Popen(
            [sys.executable, str(CONTROL_PY), "doctor"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=env["TMPDIR"],
            start_new_session=True,
            text=True,
        )
        n0 = len(fv.calls("python"))
        assert wait_until(lambda: len(fv.calls("python")) > n0, timeout=10)
        os.kill(c.pid, signal.SIGINT)
        out, _ = c.communicate(timeout=5)
        assert c.returncode == 1
        assert out.count("\n") == 1
        assert json.loads(out)["error"]["code"] == "interrupted"
        assert wait_dead(fv.calls("python")[-1]["pid"], 1.0)
    finally:
        run_cli(["down"], env)


# ---------------------------------------------------------------------------
# WI1-C72: validate_base_url
# ---------------------------------------------------------------------------

URL_ACCEPTED = [("http://127.0.0.1:8123", 8123), ("http://127.0.0.1:1", 1), ("http://127.0.0.1:65535", 65535)]
URL_REFUSED = [
    "http://localhost.evil:1", "http://localhost:1", "http://10.0.0.5:1", "https://127.0.0.1:1", "http://u@127.0.0.1:1",
    "http://u:p@127.0.0.1:1", "http://127.0.0.1:1/pfx", "http://127.0.0.1:1/", "http://127.0.0.1:1?x=1",
    "http://127.0.0.1:1#f", "http://127.0.0.1", "http://127.0.0.1:", "http://127.0.0.1:0", "http://127.0.0.1:99999",
    "http://127.0.0.1:65536", "http://127.0.0.1:080", "http://127.0.0.1:+1", "http://127.0.0.1:١",
    "HTTP://127.0.0.1:1", " http://127.0.0.1:1", "http://127.0.0.1:1\n", "http://127.0.0.2:1", "http://0177.0.0.1:1",
    "http://127.1:1", "http://[::1]:1", "", None, 8123, b"http://127.0.0.1:1", True,
]


def test_c72a_validate_base_url_table():  # WI1-C72 (a)
    for u, p in URL_ACCEPTED:
        assert http_client.validate_base_url(u) == p
    for u in URL_REFUSED:
        with pytest.raises(paths.GuardRefusal) as info:
            http_client.validate_base_url(u)
        assert info.value.code == "refused_url", u


_url_like = st.one_of(
    st.text(max_size=40),
    st.builds(
        lambda s, ui, h, pt, sfx: f"{s}://{ui}{h}{pt}{sfx}",
        st.sampled_from(["http", "https", "HTTP", ""]),
        st.sampled_from(["", "u@", "u:p@"]),
        st.sampled_from(["127.0.0.1", "localhost", "127.0.0.2", "[::1]", "127.0.0.1.evil"]),
        st.one_of(
            st.just(""),
            st.integers(-5, 70000).map(lambda i: f":{i}"),
            st.text(alphabet="0123456789١+- ", max_size=6).map(lambda t: ":" + t),
        ),
        st.sampled_from(["", "/", "/x", "?a=1", "#f", " "]),
    ),
)


@settings(max_examples=500, deadline=None)
@given(u=_url_like)
def test_c72b_validate_base_url_relation(u):  # WI1-C72 (b)
    try:
        p = http_client.validate_base_url(u)
    except paths.GuardRefusal as exc:
        assert exc.code == "refused_url"
        return
    assert isinstance(p, int) and not isinstance(p, bool)
    assert 1 <= p <= 65535
    assert u == f"http://127.0.0.1:{p}"


@settings(max_examples=200, deadline=None)
@given(p=st.integers(1, 65535))
def test_c72c_canonical_urls_round_trip(p):  # WI1-C72 (c)
    assert http_client.validate_base_url(f"http://127.0.0.1:{p}") == p


def _valid_state(sandbox, port=50000, **over):
    d = {k: None for k in SCHEMA_KEYS}
    sandbox = str(sandbox)
    d.update(
        {
            "sandbox": sandbox,
            "books_dir": sandbox + "/books",
            "ai_settings": sandbox + "/ai_settings.json",
            "log": sandbox + "/server.log",
            "port": port,
            "base_url": f"http://127.0.0.1:{port}",
            "pid": 4242,
            "pid_start": EPOCH,
            "argv": [],
            "repo": "/r",
        }
    )
    d.update(over)
    return d


def _write_state_json(tmp_path, name, d):
    p = tmp_path / "states" / f"{name}.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(d), encoding="utf-8")
    return p


def test_c72d_load_refuses_url_mismatch(tmp_path):  # WI1-C72 (d)
    repo = tmp_path / "r"
    (repo / "books").mkdir(parents=True)
    sbx = Path(tempfile.mkdtemp(prefix="verify-reader3.", dir=tmp_path)).resolve()
    (sbx / "books").mkdir()
    rows = [
        _valid_state(sbx, base_url="http://127.0.0.1:50001"),
        _valid_state(sbx, port=None, base_url="http://127.0.0.1:50000"),
        _valid_state(sbx, base_url="http://127.0.0.1:50000/"),
    ]
    for i, d in enumerate(rows):
        p = _write_state_json(tmp_path, f"d{i}", d)
        with pytest.raises(paths.GuardRefusal) as info:
            state.load(p, repo=repo)
        assert info.value.code == "refused_url", d


def test_c72e_request_revalidates_before_any_network_call():  # WI1-C72 (e)
    with mock.patch("socket.getaddrinfo", side_effect=AssertionError("dns")), mock.patch(
        "socket.create_connection", side_effect=AssertionError("connect")
    ), mock.patch.object(http.client.HTTPConnection, "connect", side_effect=AssertionError("connect")):
        for u in ["http://example.invalid:80", "http://127.0.0.1:1/pfx", "http://localhost:1"]:
            with pytest.raises(paths.GuardRefusal) as info:
                http_client.request(u, "GET", "/api/health", timeout=1)
            assert info.value.code == "refused_url"


# ---------------------------------------------------------------------------
# WI1-C73 (a) and rows i-l: state.load
# ---------------------------------------------------------------------------


def test_c73a_loader_table_and_refusal_order(tmp_path):  # WI1-C73 (a)
    R = fake_repo(tmp_path)
    T = tmp_path / "t"
    T.mkdir()
    good = Path(tempfile.mkdtemp(prefix="verify-reader3.", dir=T)).resolve()
    (good / "books").mkdir()
    good2 = Path(tempfile.mkdtemp(prefix="verify-reader3.", dir=T)).resolve()
    (good2 / "books").symlink_to(R / "books")
    (tmp_path / "harmless" / "books").mkdir(parents=True)
    far = tmp_path / "elsewhere" / "verify-reader3.z"
    far.mkdir(parents=True)
    (T / "verify-reader3.l").symlink_to(good)
    (T / "plain").mkdir()
    (T / "verify-reader3.f").write_text("f")
    (T / "verify-reader3.dl").symlink_to(tmp_path / "nowhere")

    def row(name, sandbox, **over):
        return _write_state_json(tmp_path, name, _valid_state(sandbox, **over))

    paths_ = {
        "ok": row("ok", good),
        "far": row("far", far),
        "a": row("a", T / "verify-reader3.l"),
        "b": row("b", T / "plain"),
        "c": row("c", T / "verify-reader3.f"),
        "d": row("d", T / "verify-reader3.gone"),
        "e": row("e", "/"),
        "f": row("f", "verify-reader3.rel"),
        "g": row("g", ""),
        "h": row("h", good2, books_dir=str(tmp_path / "harmless" / "books")),
        "o1": row("o1", T / "plain", base_url="http://127.0.0.1:1"),
        "o2": row("o2", T / "plain", books_dir=str(R / "books" / "x")),
        "dl": row("dl", T / "verify-reader3.dl"),
    }
    expected = {
        "a": "refused_sandbox_shape", "b": "refused_sandbox_shape", "c": "refused_sandbox_shape",
        "d": "refused_sandbox_shape", "e": "refused_sandbox_shape", "f": "refused_sandbox_shape",
        "g": "refused_sandbox_shape", "h": "refused_books_dir", "o1": "refused_sandbox_shape", "o2": "refused_books_dir",
    }
    before = snapshot_tree(tmp_path)
    for name in ("ok", "far"):
        assert state.load(paths_[name], repo=R) == state.read(paths_[name]), name
    for name, code in expected.items():
        with pytest.raises(paths.GuardRefusal) as info:
            state.load(paths_[name], repo=R)
        assert info.value.code == code, name
    assert state.load(paths_["d"], repo=R, allow_missing_sandbox=True) == state.read(paths_["d"])
    for name in ("dl", "a", "b", "c", "e"):
        with pytest.raises(paths.GuardRefusal) as info:
            state.load(paths_[name], repo=R, allow_missing_sandbox=True)
        assert info.value.code == "refused_sandbox_shape", name
    assert snapshot_tree(tmp_path) == before


def test_c73_rows_i_to_l_paths_tied_to_the_sandbox(tmp_path):  # WI1-C73 rows i-l (round 2)
    R = fake_repo(tmp_path)
    M = tmp_path / "main"
    (R / ".git").write_text(f"gitdir: {M}/.git/worktrees/x\n", encoding="utf-8")
    (M / "config").mkdir(parents=True)
    replica_r = R / "config" / "ai_settings.json"
    replica_m = M / "config" / "ai_settings.json"
    for rep in (replica_r, replica_m):
        rep.write_text("sentinel")
        os.chmod(rep, 0o000)
    T = tmp_path / "t"
    T.mkdir()
    sbx = Path(tempfile.mkdtemp(prefix="verify-reader3.", dir=T)).resolve()
    (sbx / "books").mkdir()
    rows = {
        "i": _valid_state(sbx, log=str(replica_r)),
        "j": _valid_state(sbx, ai_settings=str(replica_r)),
        "k": _valid_state(sbx, log=str(replica_m), ai_settings=str(replica_m)),
        "l": _valid_state(sbx, books_dir=str(sbx) + "/../other"),
    }
    before = [(os.stat(r).st_size, os.stat(r).st_mtime_ns, stat.S_IMODE(os.stat(r).st_mode)) for r in (replica_r, replica_m)]
    try:
        for name, d in rows.items():
            p = _write_state_json(tmp_path, name, d)
            with _open_tripwires(allow=[p]):
                with pytest.raises(paths.GuardRefusal) as info:
                    state.load(p, repo=R)
            assert info.value.code == "refused_sandbox_shape", name
        after = [(os.stat(r).st_size, os.stat(r).st_mtime_ns, stat.S_IMODE(os.stat(r).st_mode)) for r in (replica_r, replica_m)]
        assert after == before
    finally:
        for rep in (replica_r, replica_m):
            os.chmod(rep, 0o600)


# Silence "imported but unused" for names some environments do not exercise.
_ = (socket,)
