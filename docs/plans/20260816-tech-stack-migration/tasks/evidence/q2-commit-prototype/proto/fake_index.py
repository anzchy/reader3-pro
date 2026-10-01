"""A fake WI-7 index driven by the same generation_core as mechanism B.

<root>/collections/<g>/{chunks.jsonl, collection.json} + <root>/index_meta.json
(pointer: {"generation": g, "fingerprint": ..., "chunk_count": n}).
Stands in for Chroma's reader3_book_<generation> collections; no Chroma involved.
"""
from __future__ import annotations

import json
import os
from typing import Tuple

from . import common as c
from .generation_core import GenSpec, publish_generation, recover_generations

POINTER = "index_meta.json"
GENS = "collections"


def _spec(fingerprint: str, n_chunks: int = 5) -> GenSpec:
    def s1(ctx: dict) -> None:
        lines = [json.dumps({"i": i, "fp": fingerprint}) for i in range(n_chunks)]
        c.write_bytes(os.path.join(ctx["gen_dir"], "chunks.jsonl"), ("\n".join(lines) + "\n").encode())

    def s2(ctx: dict) -> None:
        c.fsync_path(os.path.join(ctx["gen_dir"], "chunks.jsonl"))

    def s3(ctx: dict) -> None:
        path = os.path.join(ctx["gen_dir"], "collection.json")
        c.write_bytes(path, json.dumps({"name": f"reader3_book_{ctx['generation']}"}).encode())
        c.fsync_path(path)

    def pointer(ctx: dict) -> bytes:
        return json.dumps({"generation": ctx["generation"], "fingerprint": fingerprint,
                           "chunk_count": n_chunks}, sort_keys=True).encode()

    def validate(gen_dir: str, data: bytes) -> None:
        meta = json.loads(data)
        rows = c.read_bytes(os.path.join(gen_dir, "chunks.jsonl")).decode().splitlines()
        if len(rows) != meta["chunk_count"] or any(json.loads(r)["fp"] != meta["fingerprint"] for r in rows):
            raise c.ReadbackError("chunk count / fingerprint mismatch")

    return GenSpec("i", POINTER, GENS, (s1, s2, s3), pointer, validate)


def publish_index(root: str, fingerprint: str) -> int:
    return publish_generation(root, _spec(fingerprint))


def recover_index(root: str) -> None:
    recover_generations(root, _spec("-"))


def classify_index(root: str) -> Tuple[str, int]:
    """(fingerprint the query side would hit | 'missing' | 'corrupt', residue)."""
    path = os.path.join(root, POINTER)
    if not os.path.lexists(path):
        gens = os.path.join(root, GENS)
        return "missing", len(os.listdir(gens)) if os.path.isdir(gens) else 0
    try:
        meta = json.loads(c.read_bytes(path))
        _spec(meta["fingerprint"]).validate(os.path.join(root, GENS, str(meta["generation"])), c.read_bytes(path))
    except (OSError, ValueError, KeyError):
        return "corrupt", 0
    extra = set(os.listdir(os.path.join(root, GENS))) - {str(meta["generation"])}
    extra |= set(os.listdir(root)) - {POINTER, GENS}
    return meta["fingerprint"], len(extra)
