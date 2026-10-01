"""Mechanism A: flat layout + persistent recovery journal.

Layout: <book>/{manifest.json, chapters.jsonl, book.epub, images/, book.pkl}
Staging: <book>/.staging/<txid>/  (asides under <txid>/aside/)
Journal: <book>/.publish-journal.json -- written before the first live rename,
unlinked after the manifest (commit marker) lands. Recovery reads it: live
manifest sha == journal.new_manifest_sha -> roll forward, else roll back.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

from . import common as c

STAGING = ".staging"
JOURNAL = ".publish-journal.json"
ARTIFACTS = (c.CHAPTERS, c.EPUB, c.IMAGES, c.PKL)
STAGED_NAME = {c.CHAPTERS: c.CHAPTERS + ".tmp"}
step = c.stepper("a")


def _staged(stage: str, name: str) -> str:
    return os.path.join(stage, STAGED_NAME.get(name, name))


def publish_a(book_dir: str, contents: c.Contents, embed_txid: bool = True) -> None:
    os.makedirs(book_dir, exist_ok=True)
    recover_a(book_dir)  # finish any earlier transaction before touching staging
    txid = uuid.uuid4().hex
    staging_root = os.path.join(book_dir, STAGING)
    os.makedirs(staging_root, exist_ok=True)
    c.assert_same_device(staging_root, book_dir)
    stage = os.path.join(staging_root, txid)
    os.mkdir(stage)
    manifest_tmp = os.path.join(stage, c.MANIFEST + ".tmp")
    try:
        with step("a1"):
            meta = c.write_chapters(_staged(stage, c.CHAPTERS), contents.chapters)
        with step("a2"):
            c.fsync_path(_staged(stage, c.CHAPTERS))
        with step("a3"):
            c.write_artifacts(stage, contents)
            os.mkdir(os.path.join(stage, "aside"))
            c.fsync_tree(stage)
            c.fsync_path(staging_root)
        with step("a4"):
            extra = {"txid": txid} if embed_txid else {}
            manifest_bytes = c.build_manifest(contents.tag, meta, c.artifact_shas(contents), **extra)
            c.write_bytes(manifest_tmp, manifest_bytes)
        with step("a5"):
            c.fsync_path(manifest_tmp)
        with step("a6"):
            staged_manifest = json.loads(c.read_bytes(manifest_tmp))
            c.validate_book(staged_manifest, stage, chapters_name=STAGED_NAME[c.CHAPTERS])
    except BaseException:
        c.discard(stage)
        c.rmdir_if_empty(staging_root)
        raise

    rel_stage = f"{STAGING}/{txid}"
    journal = {
        "txid": txid,
        "staging": rel_stage,
        "new_manifest_sha": c.sha256(manifest_bytes),
        "artifacts": [
            {"name": n, "live": n, "aside": f"{rel_stage}/aside/{n}",
             "existed": os.path.lexists(os.path.join(book_dir, n))}
            for n in ARTIFACTS
        ],
    }
    journal_path = os.path.join(book_dir, JOURNAL)
    aside_dir = os.path.join(stage, "aside")
    committed = False
    try:
        with step("a7"):
            tmp = os.path.join(stage, "journal.tmp")
            c.write_bytes(tmp, json.dumps(journal, sort_keys=True).encode())
            c.fsync_path(tmp)
            os.replace(tmp, journal_path)
            c.fsync_path(stage)
            c.fsync_path(book_dir)
        for e in journal["artifacts"]:
            with step(f"a8.{e['name']}"):
                if e["existed"]:
                    os.replace(os.path.join(book_dir, e["live"]), os.path.join(book_dir, e["aside"]))
                    c.fsync_path(aside_dir)
                    c.fsync_path(book_dir)
        for e in journal["artifacts"]:
            with step(f"a9.{e['name']}"):
                src = _staged(stage, e["name"])
                if os.path.lexists(src):
                    os.replace(src, os.path.join(book_dir, e["live"]))
                    c.fsync_path(stage)
                    c.fsync_path(book_dir)
        with step("a10"):  # COMMIT POINT
            os.replace(manifest_tmp, os.path.join(book_dir, c.MANIFEST))
            committed = True
            c.fsync_path(book_dir)
    except BaseException:
        if not committed:
            try:
                recover_a(book_dir)  # the same rollback code a later process would run
            except OSError as undo_error:
                print(f"WARNING: rollback incomplete ({undo_error}); journal kept, "
                      f"run recover", file=sys.stderr)
        raise
    with step("a11"):
        os.unlink(journal_path)
        c.fsync_path(book_dir)
    with step("a12"):
        c.discard(stage)
        c.rmdir_if_empty(staging_root)
        c.fsync_path(book_dir)


def _rollback(book_dir: str, journal: dict) -> None:
    """Reverse order. Idempotent: every branch re-checks what is on disk."""
    for e in reversed(journal["artifacts"]):
        with step(f"r-back.{e['name']}"):
            live = os.path.join(book_dir, e["live"])
            aside = os.path.join(book_dir, e["aside"])
            if e["existed"]:
                if os.path.lexists(aside):
                    c.discard(live)
                    os.replace(aside, live)
                    c.fsync_path(os.path.dirname(aside))
                    c.fsync_path(book_dir)
            elif os.path.lexists(live):
                c.discard(live)  # the artifact that did not exist before
                c.fsync_path(book_dir)


def recover_a(book_dir: str) -> str:
    """Return 'clean' | 'forward' | 'back'. Journal is unlinked last, then staging cleaned."""
    if not os.path.isdir(book_dir):
        return "clean"
    journal_path = os.path.join(book_dir, JOURNAL)
    outcome = "clean"
    with step("r1"):
        journal = json.loads(c.read_bytes(journal_path)) if os.path.lexists(journal_path) else None
    if journal is not None:
        manifest = os.path.join(book_dir, c.MANIFEST)
        live_sha = c.sha256(c.read_bytes(manifest)) if os.path.lexists(manifest) else None
        if live_sha == journal["new_manifest_sha"]:
            outcome = "forward"
            with step("r2"):
                pass  # asides live in staging; r4 drops them
        else:
            outcome = "back"
            _rollback(book_dir, journal)
        with step("r3"):
            os.unlink(journal_path)
            c.fsync_path(book_dir)
    with step("r4"):
        staging_root = os.path.join(book_dir, STAGING)
        if os.path.isdir(staging_root):
            for name in sorted(os.listdir(staging_root)):
                c.discard(os.path.join(staging_root, name))
            os.rmdir(staging_root)
            c.fsync_path(book_dir)
    return outcome
