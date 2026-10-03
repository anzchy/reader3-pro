"""`book add|index`, `fs ls|stat|cat` and the `up --stale-index` hook.

`book add` runs `<venv>/reader3 <epub>` and `book index` runs `<venv>/reader3 --index <id>`,
both with the sandbox env (no inherited READER3_*, sandbox paths injected) and the sandbox
as cwd. `book index` never downloads a model unless `--allow-download` is given: it probes
for the semantic extra, then checks the HF cache, and only then spawns with HF forced
offline.
"""

import os
import re
import shlex
from pathlib import Path

from verify_control import corpus, fs_view, instance_doctor, paths, procs
from verify_control.envelope import TRY_PREFIX, failure, success
from verify_control.instance_common import fail, knob, run
from verify_control.paths import GuardRefusal
from verify_control.registry import add, group

SUMMARY_MARK = "--- Summary ---"
SUMMARY_FIELDS = (
    ("title", "Title: "), ("authors", "Authors: "), ("spine_files", "Physical Files (Spine): "),
    ("toc_root_items", "TOC Root Items: "), ("images_extracted", "Images extracted: "),
)
SANDBOX_KEYS = ["READER3_AI_SETTINGS", "READER3_BOOKS_DIR"]
DOWNLOAD_HINT = ("embedding model not cached; rerun with --allow-download to let the index run "
                 "download it (network), or pre-populate HF_HOME")
OFFLINE_MARK = "OfflineModeIsEnabled"
OFFLINE_HINT = ("offline mode (HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE) blocked a Hugging Face metadata lookup; "
                "the model may already be cached, so retry with --allow-download\n")
_INDEXED = re.compile(r"(\d+) chunks using (.+)", re.ASCII)
_COUNT = re.compile(r"\d+", re.ASCII)


def parse_summary(text):
    """The dict of reader3's last `--- Summary ---` block, or None if it is incomplete."""
    lines = text.split("\n")
    marks = [i for i, ln in enumerate(lines) if ln.rstrip("\r") == SUMMARY_MARK]
    if not marks:
        return None
    body = lines[marks[-1] + 1:marks[-1] + 1 + len(SUMMARY_FIELDS)]
    if len(body) < len(SUMMARY_FIELDS):
        return None
    out = {}
    for (key, prefix), line in zip(SUMMARY_FIELDS, body):
        line = line.rstrip("\r")
        if not line.startswith(prefix):
            return None
        value = line[len(prefix):]
        if key == "title":
            out[key] = value
        elif key == "authors":
            out[key] = value.split(", ") if value else []
        elif _COUNT.fullmatch(value):
            out[key] = int(value)
        else:
            return None
    return out


def parse_indexed(stdout, book_id):
    """{chunks, model} from the last `Indexed <book_id>: N chunks using M` line, or None."""
    prefix = f"Indexed {book_id}: "
    hits = [ln.rstrip("\r") for ln in stdout.split("\n") if ln.startswith(prefix)]
    if not hits:
        return None
    m = _INDEXED.fullmatch(hits[-1][len(prefix):])
    return {"chunks": int(m.group(1)), "model": m.group(2)} if m else None


def seed_stale_index(phase, ctx):
    """`up --stale-index` hook. `phase` is "preflight" (ctx is the parsed args, before anything
    is created) or "seed" (after ingest; ctx has `books_dir`). None continues; an envelope stops."""
    if phase == "preflight":
        if getattr(ctx, "corpus", None) != "smoke":
            return failure("up", "usage", "--stale-index seeds the smoke book's index; it needs --corpus smoke",
                           TRY_PREFIX + "up --corpus smoke --stale-index")
        return None
    if phase == "seed":
        corpus.seed_stale_index(Path(ctx["books_dir"]) / "smoke_data")
    return None


def _offline_from_parent(env):
    """Undo `sandbox_env`'s forced offline vars: the child gets whatever the parent had."""
    for k in procs.OFFLINE:
        if k in os.environ:
            env[k] = os.environ[k]
        else:
            env.pop(k, None)
    return env


def _tail(text, n=2000):
    return text[-n:].strip()


def _spawn(cmd, code, argv, env, sandbox, timeout_knob, default, offline_retry=None):
    """Run argv; `offline_retry` is the `try` tail for a failure caused by forced offline mode."""
    try:
        res = procs.run(argv, env=env, cwd=sandbox, timeout=knob(timeout_knob, default))
    except OSError as exc:
        raise fail(cmd, code, f"cannot run {argv[0]}: {exc}", "doctor") from None
    if res.timed_out:
        raise fail(cmd, code, f"{argv[0]} timed out; stderr: {_tail(res.stderr)}", "doctor")
    if res.exit != 0:
        msg = f"{argv[0]} exited {res.exit}: {_tail(res.stderr)}"
        if offline_retry and OFFLINE_MARK in res.stderr + res.stdout:
            raise fail(cmd, code, OFFLINE_HINT + msg, offline_retry)
        raise fail(cmd, code, msg, "doctor")
    return res


def _add(ns):
    repo, _, s = fs_view.instance("book add", ns)
    epub = os.path.realpath(ns.epub)
    if not os.path.isfile(epub):
        raise fail("book add", "epub_not_found", f"--epub {ns.epub} is not a file", "book add --epub <path.epub>")
    book_id = os.path.splitext(os.path.basename(epub))[0] + "_data"
    argv = [str(paths.venv_bin(os.environ, repo) / "reader3"), epub]
    if ns.dry_run:
        return success("book add", {"dry_run": True, "argv": argv, "env_keys": SANDBOX_KEYS, "book_id": book_id})
    env = _offline_from_parent(procs.sandbox_env(s["sandbox"]))
    res = _spawn("book add", "add_failed", argv, env, s["sandbox"], "VERIFY_READER3_INGEST_TIMEOUT_S", 600)
    summary = parse_summary(res.stdout)
    if summary is None:
        raise fail("book add", "add_failed", f"reader3 printed no complete '{SUMMARY_MARK}' block", "doctor")
    return success("book add", {"book_id": book_id, "epub": epub, "summary": summary})


def _book_dir(cmd, books_dir, book_id):
    real = fs_view.confine(books_dir, book_id)
    if os.path.dirname(str(real)) != os.path.realpath(books_dir):
        raise GuardRefusal("refused_path", "book must be one folder name inside the sandbox books dir")
    if not os.path.isfile(real / "book.pkl"):
        raise fail(cmd, "book_not_found", f"{book_id} has no book.pkl in the sandbox", "fs ls books")
    return real


def _model_cached(repo):
    hf = os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")
    name = "models--sentence-transformers--" + instance_doctor._model_name(repo)
    return os.path.isdir(os.path.join(hf, "hub", name))


def _index(ns):
    cmd = "book index"
    repo, _, s = fs_view.instance(cmd, ns)
    _book_dir(cmd, s["books_dir"], ns.book)
    allow = ns.allow_download
    argv = [str(paths.venv_bin(os.environ, repo) / "reader3"), "--index", ns.book]
    env = procs.sandbox_env(s["sandbox"])
    if allow:
        _offline_from_parent(env)
    keys = sorted(SANDBOX_KEYS + ([] if allow else list(procs.OFFLINE)))
    if ns.dry_run:
        return success(cmd, {"dry_run": True, "argv": argv, "env_keys": keys, "book_id": ns.book})
    extra, probe = instance_doctor._probe(repo, s)
    data = {"book_id": ns.book, "extra_installed": extra, "extra_probe": probe}
    if not extra:
        return success(cmd, dict(data, hint=instance_doctor.EXTRA_HINT, spawned=False))
    data["model_cached"] = _model_cached(repo)
    if not data["model_cached"] and not allow:
        return success(cmd, dict(data, skipped="model_not_cached", hint=DOWNLOAD_HINT, spawned=False))
    retry = None if allow else f"book index {shlex.quote(ns.book)} --allow-download"
    res = _spawn(cmd, "index_failed", argv, env, s["sandbox"], "VERIFY_READER3_INDEX_TIMEOUT_S", 1800, retry)
    parsed = parse_indexed(res.stdout, ns.book)
    if parsed is None:
        raise fail(cmd, "index_failed", f"reader3 printed no 'Indexed {ns.book}: N chunks using MODEL' line", "doctor")
    offline = all(env.get(k) == "1" for k in procs.OFFLINE)
    return success(cmd, dict(data, offline=offline, spawned=True, **parsed))


def register(subparsers):
    handlers = {}
    book = group(subparsers, "book", help="add or index a book in the sandbox library", subcommands=("add", "index"),
                 examples=("book add --epub ./some.epub", "book index smoke_data"))
    p = add(book, "book add", help="ingest an EPUB into the sandbox library", examples=("book add --epub ./some.epub",),
            handlers=handlers, handler=lambda ns: run("book add", lambda: _add(ns)))
    p.add_argument("--epub", required=True, help="path to the .epub file")
    p.add_argument("--state", help="state file (default: the recorded instance)")
    p.add_argument("--dry-run", action="store_true", help="print the reader3 call; run nothing")
    p = add(book, "book index", help="build the semantic index for a sandbox book",
            examples=("book index smoke_data", "book index smoke_data --allow-download"),
            handlers=handlers, handler=lambda ns: run("book index", lambda: _index(ns)))
    p.add_argument("book", help="book folder, e.g. smoke_data")
    p.add_argument("--state", help="state file (default: the recorded instance)")
    p.add_argument("--dry-run", action="store_true", help="print the reader3 call; probe and run nothing")
    p.add_argument("--allow-download", action="store_true", help="let the index run download the model")
    fs = group(subparsers, "fs", help="read-only views of the sandbox files", subcommands=("ls", "stat", "cat"),
               examples=("fs ls .", "fs stat books", "fs cat server.log"))
    for name, what in (("ls", "list a sandbox directory"), ("stat", "stat a sandbox path"), ("cat", "print a sandbox file")):
        p = add(fs, f"fs {name}", help=what, examples=(f"fs {name} .",), handlers=handlers,
                handler=fs_view.handler(f"fs {name}", fs_view.HANDLERS[name]))
        p.add_argument("path", help="path relative to the sandbox")
        p.add_argument("--state", help="state file (default: the recorded instance)")
    return handlers
