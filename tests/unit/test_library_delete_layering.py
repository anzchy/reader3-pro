"""018 WI-5a: ``library_delete`` never imports ``reader3_app.web*`` (matrix case B-6a, ruled Q6)."""

from __future__ import annotations

import json
import subprocess
import sys

from delete_world import SUBPROCESS_TIMEOUT_S, child_env, ld

CODE = (
    "import json, sys; "
    "import reader3_app.library_delete; "
    "print(json.dumps(sorted(n for n in sys.modules if n == 'reader3_app.web' or n.startswith('reader3_app.web.'))))"
)


def test_b6a_library_delete_import_graph_has_no_web():
    """B-6a: a fresh interpreter importing ``reader3_app.library_delete`` loads no ``reader3_app.web*``."""
    ld()  # red guard in the parent, before the child is spawned
    proc = subprocess.run(
        [sys.executable, "-c", CODE], capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_S, env=child_env()
    )

    assert proc.returncode == 0, proc.stderr[-3000:]
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == []
