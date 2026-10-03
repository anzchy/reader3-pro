"""Read-only sandbox views (`fs ls|stat|cat`) and the path confinement they share.

`confine(root, rel)` is the one gate: a relative path is joined to the realpath of the
root and accepted only when its realpath is the root or under it. Symlinks that leave
the sandbox, `..` escapes and sibling-prefix names (`<sandbox>EVIL`) are all refused
before anything is opened. A refusal message never echoes the requested path.
"""

import os
import stat as stat_mod
from pathlib import Path

from verify_control.envelope import success
from verify_control.instance_common import fail, load, resolve, run, setup
from verify_control.paths import GuardRefusal

CAT_CAP = 262144


def confine(root, rel):
    """Return the realpath of `rel` under `root`, or raise refused_path."""
    if not isinstance(rel, str) or "\0" in rel or os.path.isabs(rel):
        raise GuardRefusal("refused_path", "path must be relative to the sandbox and stay inside it")
    base = os.path.realpath(str(root))
    real = os.path.realpath(os.path.join(base, rel))
    if real != base and not real.startswith(base.rstrip(os.sep) + os.sep):
        raise GuardRefusal("refused_path", "path resolves outside the sandbox; fs only reads inside it")
    return Path(real)


def instance(cmd, ns):
    """(repo, evidence root, vetted state) of the recorded instance, or a Fail."""
    repo, ev_root, ptr = setup(cmd)
    sp = resolve(cmd, ns, ptr)
    if sp is None or not os.path.lexists(sp):
        raise fail(cmd, "no_instance", "no running instance is recorded", "up")
    return repo, ev_root, load(cmd, sp, repo)


def _kind(mode):
    if stat_mod.S_ISLNK(mode):
        return "link"
    if stat_mod.S_ISDIR(mode):
        return "dir"
    if stat_mod.S_ISREG(mode):
        return "file"
    return "other"


def _target(cmd, ns):
    _, _, s = instance(cmd, ns)
    real = confine(s["sandbox"], ns.path)
    try:
        st = os.stat(real)
    except FileNotFoundError:
        raise fail(cmd, "not_found", f"{ns.path} does not exist in the sandbox", "fs ls .") from None
    return real, st


def _ls(ns):
    real, st = _target("fs ls", ns)
    if not stat_mod.S_ISDIR(st.st_mode):
        raise fail("fs ls", "not_a_directory", f"{ns.path} is not a directory", "fs stat " + ns.path)
    entries = []
    for name in sorted(os.listdir(real)):
        try:
            entries.append({"name": name, "type": _kind(os.lstat(os.path.join(real, name)).st_mode)})
        except OSError:
            entries.append({"name": name, "type": "other"})
    return success("fs ls", {"path": ns.path, "entries": entries})


def _stat(ns):
    _, st = _target("fs stat", ns)
    return success("fs stat", {
        "path": ns.path, "type": _kind(st.st_mode), "mode": format(st.st_mode & 0o777, "04o"),
        "size": st.st_size, "mtime": st.st_mtime,
    })


def _cat(ns):
    real, st = _target("fs cat", ns)
    if not stat_mod.S_ISREG(st.st_mode):
        raise fail("fs cat", "not_a_file", f"{ns.path} is not a regular file", "fs stat " + ns.path)
    fd = os.open(real, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    try:
        fst = os.fstat(fd)
        if not stat_mod.S_ISREG(fst.st_mode):
            raise fail("fs cat", "not_a_file", f"{ns.path} is not a regular file", "fs stat " + ns.path)
        chunks, got = [], 0
        while got < CAT_CAP:
            b = os.read(fd, min(65536, CAT_CAP - got))
            if not b:
                break
            chunks.append(b)
            got += len(b)
    finally:
        os.close(fd)
    data = b"".join(chunks)
    return success("fs cat", {
        "path": ns.path, "size": fst.st_size, "content": data.decode("utf-8", "replace"),
        "truncated": fst.st_size > len(data),
    })


def handler(cmd, fn):
    def h(ns):
        return run(cmd, lambda: fn(ns))

    return h


HANDLERS = {"ls": _ls, "stat": _stat, "cat": _cat}
