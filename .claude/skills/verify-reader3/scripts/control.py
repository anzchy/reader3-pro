#!/usr/bin/env python3
"""verify-reader3 control CLI: one command, one JSON envelope on stdout.

Run from the repo root:

    python3 .claude/skills/verify-reader3/scripts/control.py --help

Every command prints exactly one line of JSON with the keys ok, command, data and
error. The exit code is 0 on success, 2 on a usage error, 3 on a refusal and 1 on
any other failure. The package lives next to this file in ``verify_control/``.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from verify_control import cli  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(cli.main(sys.argv[1:]))
