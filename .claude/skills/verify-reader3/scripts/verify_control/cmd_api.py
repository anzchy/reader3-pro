"""`api METHOD PATH`: one request to the sandbox server.

Every guard runs before a socket opens: the state file is vetted (its base URL must be
`http://127.0.0.1:<port>`), the path must be a plain origin-relative path, headers cannot
set Host or Origin or smuggle CR/LF, and a `--json @file` must live in the sandbox or the
evidence root. `http.client` is used directly: no proxy variables, no redirects followed.
The token travels only in `X-Reader3-Token` and is never printed.
"""

import argparse
import http.client
import json
import os
import stat as stat_mod
import time

from verify_control import fs_view, http_client
from verify_control.envelope import TRY_PREFIX, failure, success
from verify_control.instance_common import fail, run
from verify_control.paths import GuardRefusal
from verify_control.registry import add

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
BODY_CAP = 65536
READ_CAP = 8 * 1024 * 1024
JSON_FILE_CAP = 8 * 1024 * 1024
KEPT_HEADERS = ("content-type", "etag", "location")
REFUSED_HEADERS = ("host", "origin")
_TCHAR = set("!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")


def _refuse(message):
    return GuardRefusal("refused_url", message)


def build_url(base_url, path):
    """`base_url + path` for a plain origin-relative ASCII path, else raise refused_url."""
    http_client.validate_base_url(base_url)
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        raise _refuse("path must start with a single '/' (origin-relative, no scheme or host)")
    if not path.isascii() or any(ord(c) <= 0x20 or ord(c) == 0x7F for c in path):
        raise _refuse("path must be printable ASCII without spaces or control characters")
    if "\\" in path or "://" in path or "@" in path.split("?", 1)[0]:
        raise _refuse("path must not carry a backslash, a scheme or userinfo")
    return base_url + path


def check_headers(raw):
    """[(name, value)] for `Name: value` strings; Host, Origin, CR/LF and controls are refused."""
    out = []
    for h in raw or []:
        if ":" not in h:
            raise _refuse("header must be 'Name: value'")
        name, value = h.split(":", 1)
        name, value = name.strip(), value.strip()
        if not name or any(c not in _TCHAR for c in name):
            raise _refuse("header name must be an HTTP token")
        if not value.isascii() or any((ord(c) < 0x20 and c != "\t") or ord(c) == 0x7F for c in value):
            raise _refuse("header value must be ASCII without CR, LF or control characters")
        if name.lower() in REFUSED_HEADERS:
            raise _refuse(f"the {name.lower()} header is fixed by the client and cannot be set")
        out.append((name, value))
    return out


class _Inline:
    def __init__(self, obj):
        self.obj = obj


def _json_arg(text):
    if text.startswith("@"):
        return text[1:]
    try:
        return _Inline(json.loads(text))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--json is not valid JSON ({exc})") from None


def _inside(real, root):
    root = os.path.realpath(str(root))
    return real == root or real.startswith(root.rstrip(os.sep) + os.sep)


def _json_file(path, sandbox, ev_root):
    """Parse a `--json @file` that lives in the sandbox or the evidence root; never open others."""
    real = os.path.realpath(os.path.abspath(path))
    if not (_inside(real, sandbox) or _inside(real, ev_root)):
        raise GuardRefusal("refused_path", "--json @file must be inside the sandbox or the evidence root")
    try:
        st = os.stat(real)
    except FileNotFoundError:
        raise fail("api", "not_found", f"--json @{path} does not exist", "fs ls .") from None
    if not stat_mod.S_ISREG(st.st_mode):
        raise fail("api", "not_a_file", f"--json @{path} is not a regular file", "fs ls .")
    if st.st_size > JSON_FILE_CAP:
        raise fail("api", "usage", f"--json @{path} is larger than {JSON_FILE_CAP} bytes", "api --help")
    with open(real, "rb") as f:
        raw = f.read(JSON_FILE_CAP + 1)
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise fail("api", "usage", f"--json @{path} is not valid JSON ({exc})", "api --help") from None


def _response(resp):
    raw = resp.read(READ_CAP + 1)
    headers = {k.lower(): v for k, v in resp.getheaders() if k.lower() in KEPT_HEADERS}
    ctype = headers.get("content-type", "").lower()
    if ("application/json" in ctype or "+json" in ctype) and len(raw) <= READ_CAP:
        try:
            return headers, json.loads(raw.decode("utf-8")), False
        except ValueError:
            pass
    return headers, raw[:BODY_CAP].decode("utf-8", "replace"), len(raw) > BODY_CAP


def _api(ns):
    method = ns.method.upper()
    if method not in METHODS:
        return failure("api", "usage", f"method {ns.method!r} is not one of {', '.join(METHODS)}", TRY_PREFIX + "api --help")
    _, ev_root, s = fs_view.instance("api", ns)
    url = build_url(s["base_url"], ns.path)
    headers = check_headers(ns.header)
    if ns.if_match is not None:
        headers += check_headers(["If-Match: " + ns.if_match])
    body = None
    if ns.json is not None:
        obj = ns.json.obj if isinstance(ns.json, _Inline) else _json_file(ns.json, s["sandbox"], ev_root)
        body = json.dumps(obj, ensure_ascii=True)
        headers.append(("Content-Type", "application/json"))
    if s.get("token"):
        headers.append(("X-Reader3-Token", s["token"]))
    if ns.dry_run:
        req = {"method": method, "url": url, "header_names": [n for n, _ in headers],
               "body": None if body is None else json.loads(body)}
        return success("api", {"dry_run": True, "request": req})
    port = http_client.validate_base_url(s["base_url"])
    t0 = time.monotonic()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=ns.timeout)
    try:
        conn.putrequest(method, ns.path, skip_accept_encoding=True)
        for name, value in headers:
            conn.putheader(name, value)
        data_bytes = body.encode("ascii") if body is not None else None
        if data_bytes is not None:
            conn.putheader("Content-Length", str(len(data_bytes)))
        conn.endheaders(data_bytes)
        resp = conn.getresponse()
        kept, parsed, truncated = _response(resp)
    except TimeoutError:
        raise fail("api", "timeout", f"no response from {url} within {ns.timeout:g}s", "doctor") from None
    except (ConnectionError, OSError) as exc:
        raise fail("api", "connect_failed", f"cannot reach {url}: {type(exc).__name__}", "doctor") from None
    except http.client.HTTPException as exc:
        raise fail("api", "bad_response", f"malformed response from {url}: {type(exc).__name__}", "doctor") from None
    finally:
        conn.close()
    data = {"status": resp.status, "headers": kept, "body": parsed, "body_truncated": truncated,
            "elapsed_ms": int((time.monotonic() - t0) * 1000),
            "expect_ok": None if ns.expect is None else resp.status == ns.expect}
    if data["expect_ok"] is False:
        raise fail("api", "unexpected_status", f"expected status {ns.expect}, got {resp.status}",
                   f"api {method} {ns.path}", data=data)
    return success("api", data)


def _positive(text):
    try:
        v = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid timeout {text!r}") from None
    if not 0 < v <= 3600:
        raise argparse.ArgumentTypeError(f"timeout {text!r} must be in (0, 3600]")
    return v


def register(subparsers):
    handlers = {}
    p = add(subparsers, "api", help="send one request to the sandbox server",
            examples=("api GET /api/health", "api GET /api/library/stats --expect 200",
                      "api POST /api/notes/smoke_data --json @req.json --if-match '\"v1\"'"),
            handlers=handlers, handler=lambda ns: run("api", lambda: _api(ns)))
    p.add_argument("method", help="HTTP method: " + ", ".join(METHODS))
    p.add_argument("path", help="request path, e.g. /api/health")
    p.add_argument("--json", type=_json_arg, help="JSON body, inline or @file (sandbox or evidence root)")
    p.add_argument("--header", action="append", help="extra 'Name: value' header (repeatable)")
    p.add_argument("--if-match", help="If-Match header value")
    p.add_argument("--expect", type=int, help="fail with unexpected_status unless the status is this")
    p.add_argument("--timeout", type=_positive, default=30.0, help="seconds (default 30)")
    p.add_argument("--dry-run", action="store_true", help="print the request; send nothing")
    p.add_argument("--state", help="state file (default: the recorded instance)")
    return handlers
