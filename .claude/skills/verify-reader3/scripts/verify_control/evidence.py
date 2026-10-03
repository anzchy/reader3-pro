"""`evidence start|add|result|show`: the per-run evidence folder.

The open folder is recorded only in `<evidence root>/current.json` as `{dir, feature}`; it
outlives the sandbox (`down` never touches it). `start` always makes a new folder
`<UTC YYYYMMDD-HHMMSS>-F-NNN` (suffix `-2`, `-3`, ... on a clash), never reusing one.

`add FILE` refuses a guarded source before anything else (a `books/` root or the key file
of either checkout, plus those of the hidden `--root R`), decided by realpath and `stat`
only; then it `stat`s the source (a directory, FIFO or device is `not_a_file`); then it
copies through a non-blocking open, re-checks the inode, and creates the destination with
`O_EXCL` so nothing is ever overwritten.
"""

import argparse
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

from verify_control import instance_common, paths, procs, state
from verify_control.envelope import success
from verify_control.registry import add, group

CURRENT_NAME = "current.json"
VERDICTS = ("PASS", "FAIL", "SKIPPED", "DEVIATES")
_FEATURE_RE = re.compile(r"F-\d{3}")
_CHUNK = 1 << 16


class EvidenceError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def feature_id(value):
    if not _FEATURE_RE.fullmatch(value or ""):
        raise argparse.ArgumentTypeError(f"invalid feature id {value!r} (expected F-NNN, e.g. F-018)")
    return value


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------


def guard_root(ev_root, root):
    """RR5 for the hidden `--root R`: the evidence root must not sit in R's books roots either."""
    if root:
        paths.guard_books_dir(str(ev_root), Path(os.path.abspath(root)))


def current(ev_root):
    """`(dir Path, feature)` of the open evidence folder, or None when there is none."""
    ptr = Path(ev_root) / CURRENT_NAME
    try:
        doc = json.loads(ptr.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise EvidenceError("evidence_invalid", f"{ptr} is unreadable: {exc}") from None
    d = doc.get("dir") if isinstance(doc, dict) else None
    if not isinstance(d, str) or not os.path.isabs(d):
        raise EvidenceError("evidence_invalid", f"{ptr} does not name an evidence folder")
    if os.path.dirname(os.path.realpath(d)) != os.path.realpath(ev_root):
        raise EvidenceError("refused_path", f"{ptr} names {d}, which is not directly inside {os.path.realpath(ev_root)}")
    if not os.path.isdir(d):
        return None
    return Path(d), doc.get("feature")


def start(ev_root, feature):
    root = Path(os.path.realpath(ev_root))
    root.mkdir(parents=True, exist_ok=True)
    root = Path(os.path.realpath(root))
    base = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + feature
    n = 1
    while True:
        d = root / (base if n == 1 else f"{base}-{n}")
        try:
            os.mkdir(d)
            break
        except FileExistsError:
            n += 1
    state.atomic_write_json(root / CURRENT_NAME, {"dir": str(d), "feature": feature})
    return d


def add_file(src, evdir):
    """Copy regular file `src` into `evdir` under its basename; never overwrite. -> {name, size}."""
    try:
        st0 = os.stat(src)
    except FileNotFoundError:
        raise EvidenceError("not_found", f"{src} does not exist") from None
    if not stat.S_ISREG(st0.st_mode):
        raise EvidenceError("not_a_file", f"{src} is not a regular file")
    name = os.path.basename(os.path.normpath(src))
    fd = os.open(src, os.O_RDONLY | os.O_NONBLOCK)
    try:
        st1 = os.fstat(fd)
        if not stat.S_ISREG(st1.st_mode) or (st1.st_dev, st1.st_ino) != (st0.st_dev, st0.st_ino):
            raise EvidenceError("not_a_file", f"{src} changed while it was being opened")
        dest = os.path.join(str(evdir), name)
        try:
            out = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            raise EvidenceError("evidence_exists", f"{dest} already exists; evidence is never overwritten") from None
        size = 0
        try:
            while True:
                chunk = os.read(fd, _CHUNK)
                if not chunk:
                    break
                os.write(out, chunk)
                size += len(chunk)
        finally:
            os.close(out)
    finally:
        os.close(fd)
    return {"name": name, "size": size}


def write_result(evdir, verdict, note):
    text = f"{verdict}\n" + (f"note: {note}\n" if note is not None else "")
    target = Path(evdir) / "result.txt"
    tmp = Path(evdir) / f".result.txt.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)


def listing(evdir):
    files = []
    for name in sorted(os.listdir(evdir)):
        st_ = os.lstat(os.path.join(str(evdir), name))
        files.append({"name": name, "size": st_.st_size})
    return files


# ---------------------------------------------------------------------------
# handlers
# ---------------------------------------------------------------------------


def _setup(cmd, ns):
    repo, ev_root, _ = instance_common.setup(cmd)
    guard_root(ev_root, getattr(ns, "root", None))
    return repo, ev_root


def _need_current(cmd, ev_root):
    try:
        cur = current(ev_root)
    except EvidenceError as exc:
        raise instance_common.fail(cmd, exc.code, exc.message, "evidence show") from None
    if cur is None:
        raise instance_common.fail(cmd, "no_evidence", "no evidence folder is open", "evidence start F-NNN")
    return cur


def _start(ns):
    cmd = "evidence start"
    _, ev_root = _setup(cmd, ns)
    d = start(ev_root, ns.feature)
    return success(cmd, {"dir": str(d), "feature": ns.feature})


def _guarded(src, root):
    if paths.is_guarded_source(src):
        return True
    return bool(root) and paths.is_guarded_source(src, Path(os.path.abspath(root)))


def _add_file(cmd, ns, ev_root):
    src = ns.file
    if _guarded(src, ns.root):
        raise instance_common.fail(cmd, "refused_path", f"{src} is a protected source (a books root or the key file)",
                                   "evidence show")
    try:
        st0 = os.stat(src)
    except FileNotFoundError:
        raise instance_common.fail(cmd, "not_found", f"{src} does not exist", "evidence show") from None
    if not stat.S_ISREG(st0.st_mode):
        raise instance_common.fail(cmd, "not_a_file", f"{src} is not a regular file", "evidence show")
    evdir, _ = _need_current(cmd, ev_root)
    try:
        return add_file(src, evdir)
    except EvidenceError as exc:
        raise instance_common.fail(cmd, exc.code, exc.message, "evidence show") from None


def _screenshot_name(cmd, name):
    if name == "":
        raise instance_common.fail(cmd, "usage", "--browse-screenshot needs a name", "evidence add --help")
    if name in (".", "..") or "/" in name or "\\" in name or "\x00" in name or name != os.path.basename(name):
        raise instance_common.fail(cmd, "refused_path", f"{name!r} is not a plain file name", "evidence add --help")
    return name if name.endswith(".png") else name + ".png"


def _add_screenshot(cmd, ns, ev_root):
    fname = _screenshot_name(cmd, ns.browse_screenshot)
    evdir, _ = _need_current(cmd, ev_root)
    dest = os.path.join(str(evdir), fname)
    if os.path.lexists(dest):
        raise instance_common.fail(cmd, "evidence_exists", f"{dest} already exists", "evidence show")
    browse = paths.browse_path(os.environ)
    if not instance_common.is_exe(browse):
        raise instance_common.fail(cmd, "browse_missing", f"gstack browse not found at {browse}", "doctor")
    timeout = instance_common.knob("VERIFY_READER3_BROWSE_TIMEOUT_S", 30)
    try:
        r = procs.run([browse, "screenshot", dest], env=dict(os.environ), cwd=str(evdir), timeout=timeout)
    except OSError as exc:
        raise instance_common.fail(cmd, "browse_failed", f"browse could not start: {exc}", "doctor") from None
    if r.timed_out or r.exit != 0 or not os.path.isfile(dest):
        why = "timed out" if r.timed_out else f"exited {r.exit}"
        raise instance_common.fail(cmd, "browse_failed", f"browse screenshot {why}: {r.stderr.strip()[-300:]}",
                                   "doctor")
    return {"name": fname, "size": os.path.getsize(dest)}


def _add(ns):
    cmd = "evidence add"
    _, ev_root = _setup(cmd, ns)
    if (ns.file is None) == (ns.browse_screenshot is None):
        raise instance_common.fail(cmd, "usage", "give exactly one of FILE or --browse-screenshot NAME",
                                   "evidence add --help")
    rec = _add_screenshot(cmd, ns, ev_root) if ns.file is None else _add_file(cmd, ns, ev_root)
    evdir, _ = _need_current(cmd, ev_root)
    return success(cmd, {"dir": str(evdir), "file": rec})


def _result(ns):
    cmd = "evidence result"
    _, ev_root = _setup(cmd, ns)
    evdir, _ = _need_current(cmd, ev_root)
    write_result(evdir, ns.verdict, ns.note)
    return success(cmd, {"dir": str(evdir), "verdict": ns.verdict, "note": ns.note})


def _show(ns):
    cmd = "evidence show"
    _, ev_root = _setup(cmd, ns)
    evdir, feature = _need_current(cmd, ev_root)
    return success(cmd, {"dir": str(evdir), "feature": feature, "files": listing(evdir)})


def _wrap(cmd, fn):
    def handler(ns):
        return instance_common.run(cmd, lambda: fn(ns))

    return handler


def _root_arg(p):
    p.add_argument("--root", default=None, help=argparse.SUPPRESS)


def register(subparsers):
    handlers = {}
    ev = group(subparsers, "evidence", help="record verification evidence", subcommands=("start", "add", "result", "show"),
               examples=("evidence start F-018", "evidence add ./shot.png", "evidence result PASS", "evidence show"))
    p = add(ev, "evidence start", help="open a new evidence folder for a feature", examples=("evidence start F-018",),
            handlers=handlers, handler=_wrap("evidence start", _start))
    p.add_argument("feature", type=feature_id, help="feature id, e.g. F-018")
    _root_arg(p)
    p = add(ev, "evidence add", help="copy a file (or a browse screenshot) into the open evidence folder",
            examples=("evidence add ./shot.png", "evidence add --browse-screenshot 02-toolbar"),
            handlers=handlers, handler=_wrap("evidence add", _add))
    p.add_argument("file", nargs="?", default=None, help="regular file to copy in (never overwrites)")
    p.add_argument("--browse-screenshot", metavar="NAME", default=None,
                   help="take a gstack browse screenshot into NAME.png")
    _root_arg(p)
    p = add(ev, "evidence result", help="record the verdict in result.txt",
            examples=("evidence result PASS", 'evidence result DEVIATES --note "sub-step 3"'),
            handlers=handlers, handler=_wrap("evidence result", _result))
    p.add_argument("verdict", choices=VERDICTS, help="one of " + ", ".join(VERDICTS))
    p.add_argument("--note", default=None, help="one-line note written under the verdict")
    _root_arg(p)
    p = add(ev, "evidence show", help="show the open evidence folder", examples=("evidence show",),
            handlers=handlers, handler=_wrap("evidence show", _show))
    _root_arg(p)
    return handlers
