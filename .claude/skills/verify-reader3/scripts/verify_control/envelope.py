"""The one JSON envelope every command prints: {ok, command, data, error}.

`error` is `{code, message, try}`. `try` must be a runnable command line that starts
with `TRY_PREFIX`, so an agent reading a failure always has a next step to run.
"""

import json

TRY_PREFIX = "python3 .claude/skills/verify-reader3/scripts/control.py "


def success(command, data):
    return {"ok": True, "command": command, "data": data, "error": None}


def failure(command, code, message, try_, data=None):
    if not isinstance(try_, str) or not try_.strip() or not try_.startswith(TRY_PREFIX):
        raise ValueError(f"error.try must start with {TRY_PREFIX!r}, got {try_!r}")
    return {
        "ok": False,
        "command": command,
        "data": data,
        "error": {"code": code, "message": message, "try": try_},
    }


def render(env):
    """One line of JSON plus a newline. ensure_ascii keeps U+2028/U+0085 off the wire."""
    return json.dumps(env, ensure_ascii=True) + "\n"


def exit_code(env):
    if env.get("ok"):
        return 0
    code = (env.get("error") or {}).get("code", "")
    if code == "usage":
        return 2
    if isinstance(code, str) and code.startswith("refused_"):
        return 3
    return 1


def try_cmd(tail):
    return TRY_PREFIX + tail
