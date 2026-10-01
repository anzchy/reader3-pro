"""Subprocess entry point so a crash can be a real os._exit(137) mid-publish.

    python -S -c "import sys; from proto.cli import main; sys.exit(main(sys.argv[1:]))" \
        <publish|recover> <a|b|i> <dir> [tag] [images 0|1]
"""
from __future__ import annotations

from typing import List

from . import common as c
from .fake_index import publish_index, recover_index
from .mech_a_journal import publish_a, recover_a
from .mech_b_generation import publish_b, recover_b


def main(argv: List[str]) -> int:
    op, mech, path = argv[0], argv[1], argv[2]
    if mech == "i":
        publish_index(path, argv[3]) if op == "publish" else recover_index(path)
        return 0
    if op == "publish":
        contents = c.book_contents(argv[3], images=argv[4] == "1")
        (publish_a if mech == "a" else publish_b)(path, contents)
    else:
        (recover_a if mech == "a" else recover_b)(path)
    return 0
