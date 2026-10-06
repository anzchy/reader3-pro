"""Read uvicorn access lines and slice the requests between two `verify-marker` probes.

`ui inert` brackets an action with `GET /api/health?verify-marker=<uuid>-begin` and
`...-end`; what the server logged strictly between them is what the action caused.
Only `/api` and `/api/...` paths count (assets are noise), and a "write" is literally any
non-GET method, HEAD and OPTIONS included.
"""

import re

_LINE = re.compile(r'^INFO:\s+\S+ - "([A-Z]+) (\S+) HTTP/[0-9.]+" (\d{3})(?: .*)?$')
_NET = re.compile(r"^([A-Z]+) (\S+) → (\d{3}|pending)\b")
MARKER_PARAM = "verify-marker="


class AccessLogError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_access_line(line):
    """`{"method", "path", "status": int}` for a uvicorn access line, else None."""
    m = _LINE.match(line.rstrip("\r\n"))
    if m is None:
        return None
    return {"method": m.group(1), "path": m.group(2), "status": int(m.group(3))}


def is_api_path(path):
    head = path.split("?", 1)[0]
    return head == "/api" or head.startswith("/api/")


def _keep(path):
    return is_api_path(path) and MARKER_PARAM not in path


def _marker_re(uuid):
    return re.compile(r"[?&]verify-marker=" + re.escape(uuid) + r"-(begin|end)(?:&|$)")


def slice_between(lines, uuid):
    """`{"requests", "writes"}` logged strictly between this uuid's begin and end markers."""
    mre = _marker_re(uuid)
    parsed = []
    begins, ends = [], []
    for line in lines:
        rec = parse_access_line(line)
        if rec is None:
            continue
        m = mre.search(rec["path"])
        if m is not None:
            (begins if m.group(1) == "begin" else ends).append(len(parsed))
        parsed.append(rec)
    if len(begins) > 1 or len(ends) > 1:
        raise AccessLogError("marker_duplicate", f"marker uuid {uuid} appears more than once in the log")
    if not begins and not ends:
        raise AccessLogError("marker_missing", f"neither the begin nor the end marker for {uuid} is in the log")
    if not begins:
        raise AccessLogError("marker_missing", f"the begin marker for {uuid} is not in the log")
    if not ends:
        raise AccessLogError("marker_missing", f"the end marker for {uuid} is not in the log")
    if ends[0] < begins[0]:
        raise AccessLogError("marker_missing", f"the end marker for {uuid} precedes its begin marker")
    requests = [r for r in parsed[begins[0] + 1:ends[0]] if _keep(r["path"])]
    return {"requests": requests, "writes": [r for r in requests if r["method"] != "GET"]}


def parse_browse_network(text, base_url):
    """`$B network` lines for this base URL's `/api` paths: `{method, path, status|None}`."""
    base = base_url.rstrip("/")
    out = []
    for line in text.splitlines():
        m = _NET.match(line.strip())
        if m is None:
            continue
        url = m.group(2)
        if not url.startswith(base):
            continue
        path = url[len(base):]
        if path and path[0] not in "/?":
            continue
        path = path or "/"
        if not _keep(path):
            continue
        status = None if m.group(3) == "pending" else int(m.group(3))
        out.append({"method": m.group(1), "path": path, "status": status})
    return out
