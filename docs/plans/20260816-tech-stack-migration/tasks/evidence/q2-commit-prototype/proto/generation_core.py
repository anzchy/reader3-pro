"""Mechanism B's generic core: build into <root>/<gens>/<g>/, then flip one pointer file.

Used twice: by the book publisher (pointer = manifest.json, gens = gen/) and by a
fake WI-7 index (pointer = index_meta.json, gens = collections/). The pointer is a
JSON object carrying ``"generation": g``; it is the commit marker and is written last.
Garbage = every generation directory the pointer does not name.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from . import common as c

Ctx = dict


@dataclass
class GenSpec:
    mech: str                                   # hook label, also step prefix ("b", "i")
    pointer: str                                # e.g. "manifest.json"
    gens: str                                   # e.g. "gen"
    build: Sequence[Callable[[Ctx], None]]      # steps 1..3, ctx["gen_dir"] already exists at 1
    make_pointer: Callable[[Ctx], bytes]        # step 4 payload, must contain "generation"
    validate: Callable[[str, bytes], None]      # step 6 readback (gen_dir, pointer bytes)
    post_commit: Optional[Callable[[str], None]] = None   # step 10, after GC


def read_generation(root: str, spec: GenSpec) -> Optional[int]:
    """None when there is no pointer. An unreadable pointer raises: never GC under it."""
    path = os.path.join(root, spec.pointer)
    if not os.path.lexists(path):
        return None
    return int(json.loads(c.read_bytes(path))["generation"])


def next_generation(root: str, spec: GenSpec) -> int:
    gens = os.path.join(root, spec.gens)
    seen = [int(n) for n in os.listdir(gens) if n.isdigit()] if os.path.isdir(gens) else []
    current = read_generation(root, spec)
    return max(seen + ([current] if current is not None else []) + [0]) + 1


def publish_generation(root: str, spec: GenSpec, ctx: Optional[Ctx] = None) -> int:
    step = c.stepper(spec.mech)
    p = spec.mech
    os.makedirs(root, exist_ok=True)
    recover_generations(root, spec)
    gens = os.path.join(root, spec.gens)
    os.makedirs(gens, exist_ok=True)
    c.assert_same_device(gens, root)
    g = next_generation(root, spec)
    ctx = dict(ctx or {}, generation=g, gen_dir=os.path.join(gens, str(g)), root=root)
    tmp = os.path.join(root, spec.pointer + ".tmp")
    committed = False
    try:
        for i, fn in enumerate(spec.build, 1):
            with step(f"{p}{i}"):
                if i == 1:
                    os.mkdir(ctx["gen_dir"])
                fn(ctx)
        with step(f"{p}4"):
            c.write_bytes(tmp, spec.make_pointer(ctx))
        with step(f"{p}5"):
            c.fsync_path(tmp)
        with step(f"{p}6"):
            spec.validate(ctx["gen_dir"], c.read_bytes(tmp))
        with step(f"{p}7"):  # durability barrier: the whole generation before the flip
            c.fsync_tree(ctx["gen_dir"])
            c.fsync_path(gens)
            c.fsync_path(root)
        with step(f"{p}8"):  # COMMIT POINT
            os.replace(tmp, os.path.join(root, spec.pointer))
            committed = True
            c.fsync_path(root)
    except BaseException:
        if not committed:
            c.discard(ctx["gen_dir"])
            c.discard(tmp)
            if read_generation(root, spec) is None:
                c.rmdir_if_empty(gens)
        raise
    with step(f"{p}9"):
        _gc(gens, g)
    if spec.post_commit is not None:
        with step(f"{p}10"):
            spec.post_commit(root)
            c.fsync_path(root)
    return g


def _gc(gens: str, keep: Optional[int]) -> None:
    if not os.path.isdir(gens):
        return
    for name in sorted(os.listdir(gens)):
        if name != str(keep):
            c.discard(os.path.join(gens, name))
    if keep is None:
        os.rmdir(gens)
    c.fsync_path(os.path.dirname(gens) if keep is None else gens)


def recover_generations(root: str, spec: GenSpec) -> Optional[int]:
    """Drop unreferenced generations and the pointer tmp. Idempotent."""
    step = c.stepper(spec.mech)
    if not os.path.isdir(root):
        return None
    with step("r1"):
        g = read_generation(root, spec)
    with step("r2"):
        _gc(os.path.join(root, spec.gens), g)
    with step("r3"):
        tmp = os.path.join(root, spec.pointer + ".tmp")
        if os.path.lexists(tmp):
            os.unlink(tmp)
            c.fsync_path(root)
    return g
