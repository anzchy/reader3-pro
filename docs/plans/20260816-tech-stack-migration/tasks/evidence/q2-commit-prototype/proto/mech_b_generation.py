"""Mechanism B: generation directory + one pointer (the root manifest.json) atomic swap.

Layout: <book>/manifest.json (pointer + commit marker, carries "generation": g)
        <book>/gen/<g>/{chapters.jsonl, book.epub, images/, book.pkl}
A legacy (unmigrated) book is flat book.pkl/book.epub/images/ with no manifest; the
first B publish over it removes those flat files only after the pointer has landed.
"""
from __future__ import annotations

import json
import os

from . import common as c
from .generation_core import GenSpec, publish_generation, read_generation, recover_generations

LEGACY = (c.EPUB, c.IMAGES, c.PKL)
step = c.stepper("b")


def _remove_legacy(book_dir: str) -> None:
    for name in LEGACY:
        c.discard(os.path.join(book_dir, name))


def _validate(gen_dir: str, pointer: bytes) -> None:
    c.validate_book(json.loads(pointer), gen_dir)


def _spec(contents: c.Contents, legacy: bool) -> GenSpec:
    def s1(ctx: dict) -> None:
        ctx["meta"] = c.write_chapters(os.path.join(ctx["gen_dir"], c.CHAPTERS), contents.chapters)

    def s2(ctx: dict) -> None:
        c.fsync_path(os.path.join(ctx["gen_dir"], c.CHAPTERS))

    def s3(ctx: dict) -> None:
        c.write_artifacts(ctx["gen_dir"], contents)
        c.fsync_tree(ctx["gen_dir"])

    def pointer(ctx: dict) -> bytes:
        return c.build_manifest(contents.tag, ctx["meta"], c.artifact_shas(contents),
                                generation=ctx["generation"])

    return GenSpec("b", c.MANIFEST, c.GEN, (s1, s2, s3), pointer, _validate,
                   _remove_legacy if legacy else None)


def publish_b(book_dir: str, contents: c.Contents) -> int:
    legacy = (os.path.lexists(os.path.join(book_dir, c.PKL))
              and not os.path.lexists(os.path.join(book_dir, c.MANIFEST)))
    if os.path.isdir(book_dir):
        recover_b(book_dir)
    return publish_generation(book_dir, _spec(contents, legacy))


def recover_b(book_dir: str) -> None:
    spec = _spec(c.book_contents(c.OLD), False)  # only pointer/gens names are used
    g = recover_generations(book_dir, spec)
    with step("r4"):
        if g is not None and any(os.path.lexists(os.path.join(book_dir, n)) for n in LEGACY):
            _remove_legacy(book_dir)  # pointer landed: flat files are unreferenced
            c.fsync_path(book_dir)


__all__ = ["publish_b", "recover_b", "read_generation"]
