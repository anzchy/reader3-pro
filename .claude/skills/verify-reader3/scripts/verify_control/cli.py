"""Argument parsing and dispatch: argv in, exactly one envelope out, an exit code back.

Commands come from the modules in `COMMAND_MODULES`; each exposes
`register(subparsers) -> {path: handler}`. Adding a command means editing its module,
never this file. `main` never calls `sys.exit` and never lets an exception escape.
"""

import argparse
import sys
import traceback

from verify_control import cmd_ai, cmd_api, cmd_books, cmd_instance, cmd_ledger, cmd_reader, evidence
from verify_control.envelope import TRY_PREFIX, exit_code, failure, render
from verify_control.registry import Parser, UsageError, examples_block

COMMAND_MODULES = (cmd_instance, cmd_books, cmd_api, cmd_ai, cmd_reader, cmd_ledger, evidence)

DESCRIPTION = """Drive a sandboxed Reader3 Pro instance for verification.

Every command prints exactly one line of JSON: {ok, command, data, error}.
Exit codes: 0 ok, 1 failure, 2 usage error, 3 refusal (error.code starts with refused_).
On failure, error.try is the next command to run."""

TOP_EXAMPLES = (
    "up --corpus smoke",
    "doctor",
    "down --dry-run",
    "book add --epub ./some.epub",
    "fs ls .",
    "api GET /api/health",
    'ai ask "Who is the narrator?" --book smoke_data',
    "reader state",
    "ui inert --testid lib-main",
    "lane F-011",
    "evidence start F-018",
    "map check",
)


def _build(handlers):
    parser = Parser(
        prog="control.py",
        description=DESCRIPTION,
        epilog=examples_block(TOP_EXAMPLES),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    sub = parser.add_subparsers(dest="_command", required=True, metavar="<command>")
    for mod in COMMAND_MODULES:
        handlers.update(mod.register(sub))
    return parser


def build_parser():
    return _build({})


HANDLERS = {}
_build(HANDLERS)


def _usage(path, message):
    tail = f"{path} --help" if path else "--help"
    return failure(path, "usage", message, TRY_PREFIX + tail)


def _dispatch(cmd, ns):
    try:
        return HANDLERS[cmd](ns)
    except KeyboardInterrupt:
        return failure(cmd, "interrupted", f"`{cmd}` was interrupted", TRY_PREFIX + "doctor")
    except Exception as exc:  # noqa: BLE001 - a crash in any handler still yields one envelope
        traceback.print_exc(file=sys.stderr)
        return failure(cmd, "internal_error", f"{type(exc).__name__}: {exc}", TRY_PREFIX + "doctor")
    except BaseException as exc:  # noqa: BLE001 - SystemExit and friends must not skip the envelope
        traceback.print_exc(file=sys.stderr)
        return failure(cmd, "internal_error", f"{type(exc).__name__}: {exc!r}", TRY_PREFIX + "doctor")


def main(argv):
    parser = build_parser()
    try:
        ns, extras = parser.parse_known_args(list(argv))
        if extras:
            raise UsageError(getattr(ns, "_cmd", ""), "unrecognized arguments: " + " ".join(extras))
    except UsageError as u:
        env = _usage(u.path, u.message)
    except SystemExit as exc:  # --help printed; argparse exits 0
        return 0 if exc.code in (0, None) else 2
    else:
        env = _dispatch(ns._cmd, ns)
    sys.stdout.write(render(env))
    sys.stdout.flush()
    return exit_code(env)
