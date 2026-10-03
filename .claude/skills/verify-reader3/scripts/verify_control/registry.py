"""Shared parser plumbing for command modules.

Each command module exposes `register(subparsers) -> {path: handler}` and builds its
parsers with `add`/`group` here. A parser error never exits: it raises `UsageError`
carrying the command path, which `cli.main` turns into a `usage` envelope.
"""

import argparse

from verify_control.envelope import TRY_PREFIX, failure


class UsageError(Exception):
    def __init__(self, path, message):
        super().__init__(message)
        self.path = path
        self.message = message


class Parser(argparse.ArgumentParser):
    vc_path = ""

    def error(self, message):
        raise UsageError(self.vc_path, message)


def examples_block(lines):
    if not lines:
        return None
    return "Examples:\n" + "\n".join("  " + TRY_PREFIX + ln for ln in lines)


def add(subparsers, path, *, help, examples=(), description=None, handlers=None, handler=None):
    """Add the leaf or group parser for `path` (space separated) and record its handler."""
    name = path.split()[-1]
    p = subparsers.add_parser(
        name,
        help=help,
        description=description or help,
        epilog=examples_block(examples),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    p.vc_path = path
    p.set_defaults(_cmd=path)
    if handler is not None and handlers is not None:
        handlers[path] = handler
    return p


def group(subparsers, path, *, help, subcommands, examples=()):
    """A group parser plus its required subparsers; returns the subparsers action."""
    g = add(subparsers, path, help=help, examples=examples)
    return g.add_subparsers(dest="_sub_" + path.replace(" ", "_"), required=True, metavar="{" + ",".join(subcommands) + "}")


def not_implemented(path, owner):
    """Handler for a command a later work item fills in."""

    def handler(ns):
        return failure(path, "not_implemented", f"`{path}` is not implemented yet ({owner})", TRY_PREFIX + "--help")

    return handler
