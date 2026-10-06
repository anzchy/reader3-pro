"""Loopback-only HTTP. One accepted base URL shape: `http://127.0.0.1:<port>`.

`http.client` never reads proxy variables, so a developer's `HTTP_PROXY` cannot redirect
a request. Every request revalidates its base URL before any socket work.
"""

import http.client
import re

from verify_control.paths import GuardRefusal

_URL = re.compile(r"http://127\.0\.0\.1:([1-9][0-9]{0,4})", re.ASCII)


def validate_base_url(obj):
    """Return the port of a canonical loopback base URL, else raise refused_url."""
    if isinstance(obj, str):
        m = _URL.fullmatch(obj)
        if m is not None:
            port = int(m.group(1))
            if 1 <= port <= 65535:
                return port
    raise GuardRefusal("refused_url", f"base_url {obj!r} is not http://127.0.0.1:<port>")


def request(base_url, method, path, *, headers=None, body=None, timeout):
    """Return (status, body_bytes, headers_dict). The client closes the connection."""
    port = validate_base_url(base_url)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(method, path, body=body, headers=dict(headers or {}))
        resp = conn.getresponse()
        data = resp.read()
        return resp.status, data, dict(resp.getheaders())
    finally:
        conn.close()
