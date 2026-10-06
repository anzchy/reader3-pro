"""`ui inert`: did an action cause any API request, URL change or attribute change?

Wrapper form clicks `[data-testid="ID"]`; the passthrough form (`-- <browse args>`) runs
any browse command except `eval`. The action is bracketed by two loopback probes,
`GET /api/health?verify-marker=<uuid4>-begin|end`, and the server's own access log between
them is the evidence (`--mechanism network` falls back to `$B network`). The command is ok
whenever the measurement completed; only `--expect` turns a verdict into a failure.
"""

import http.client
import json
import math
import os
import re
import time
import uuid

from verify_control import access_log, browse, http_client
from verify_control.envelope import TRY_PREFIX, failure, success
from verify_control.instance_common import Fail, fail, load, resolve, run, setup

CMD = "ui inert"
TESTID = re.compile(r"[A-Za-z0-9_-]+", re.ASCII)
MARKER_POLL_S = 0.05
DEFAULT_SETTLE_S = 1.0
NOT_FOUND = "Element not found:"


def valid_testid(s):
    return isinstance(s, str) and TESTID.fullmatch(s) is not None


def compute_inert(requests, url_before, url_after, attrs_before, attrs_after):
    return requests == [] and url_before == url_after and attrs_before == attrs_after


def _usage(message):
    return failure(CMD, "usage", message, TRY_PREFIX + "ui inert --help")


def _parse(ns):
    """(testid, action, expect, settle, mechanism) or a usage envelope."""
    action = list(ns.action or [])
    if (ns.testid is None) == (not action):
        return _usage("give exactly one of --testid ID or `-- <browse args>`")
    if ns.testid is not None and not valid_testid(ns.testid):
        return _usage(f"--testid must match [A-Za-z0-9_-]+, got {ns.testid!r}")
    if ns.expect not in (None, "inert", "active"):
        return _usage(f"--expect must be inert or active, got {ns.expect!r}")
    settle = DEFAULT_SETTLE_S
    if ns.settle is not None:
        try:
            settle = float(ns.settle)
        except ValueError:
            settle = -1.0
        if not math.isfinite(settle) or settle < 0:
            return _usage(f"--settle must be a non-negative number of seconds, got {ns.settle!r}")
    mech = ns.mechanism or "access_log"
    if mech not in ("access_log", "network"):
        return _usage(f"--mechanism must be access_log or network, got {ns.mechanism!r}")
    return ns.testid, action, ns.expect, settle, mech


def _browse(args, what, *, passthrough=False):
    try:
        return browse.run(args, passthrough=passthrough)
    except browse.BrowseError as exc:
        raise fail(CMD, exc.code, f"{what}: {exc.message}", "doctor") from None


def _attrs(testid):
    sel = f'[data-testid="{testid}"]'
    out = browse.unwrap(_browse(["attrs", sel], f"reading attributes of {sel} failed")).strip()
    if out.startswith(NOT_FOUND):
        raise fail(CMD, "testid_not_found",
                   f"no element with data-testid={testid!r} on this page ({sel}); check which page the "
                   "browser is on and that the element is rendered", "reader state")
    try:
        d = json.loads(out)
    except ValueError:
        d = None
    if not isinstance(d, dict):
        raise fail(CMD, "browse_failed", f"reading attributes of {sel} failed: {out[:200]!r}", "doctor")
    return d


def _log_size(log):
    try:
        return os.path.getsize(log)
    except OSError:
        return 0


def _read_from(log, offset):
    try:
        with open(log, "rb") as f:
            f.seek(offset)
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _mark(base_url, log, offset, u, which):
    """Send one marker probe and wait until the server has logged it."""
    path = f"/api/health?verify-marker={u}-{which}"
    try:
        http_client.request(base_url, "GET", path, timeout=5)
    except (OSError, http.client.HTTPException) as exc:
        raise fail(CMD, "marker_missing", f"the {which} marker request {path} failed: {exc}", "doctor") from None
    needle = f"verify-marker={u}-{which}"
    deadline = time.monotonic() + browse.knob("VERIFY_READER3_MARKER_WAIT_S", 2)
    while True:
        if needle in _read_from(log, offset):
            return
        if time.monotonic() >= deadline:
            raise fail(CMD, "marker_missing",
                       f"the {which} marker {u} was not logged in {log}; is the server's access log enabled?",
                       "doctor")
        time.sleep(MARKER_POLL_S)


def _instance():
    repo, _, ptr = setup(CMD)

    class _NS:
        state = None

    sp = resolve(CMD, _NS, ptr)
    if sp is None or not os.path.lexists(sp):
        raise fail(CMD, "no_instance", "no running instance is recorded", "up")
    return load(CMD, sp, repo)


def _measure(testid, action, settle, mech, s):
    base_url, log = s["base_url"], s["log"]
    sel = f'[data-testid="{testid}"]' if testid is not None else None
    url_before = _browse(["url"], "reading the page URL failed").strip()
    attrs_before = _attrs(testid) if testid is not None else None
    u = str(uuid.uuid4())
    offset = _log_size(log)
    if mech == "network":
        _browse(["network", "--clear"], "clearing the browse network log failed")
    else:
        _mark(base_url, log, offset, u, "begin")
    if testid is not None:
        _browse(["click", sel], f"clicking [data-testid={testid}] failed")
    else:
        _browse(action, f"browse {' '.join(action)} failed", passthrough=True)
    time.sleep(settle)
    url_after = _browse(["url"], "reading the page URL failed").strip()
    attrs_after = _attrs(testid) if testid is not None else None
    if mech == "network":
        requests = access_log.parse_browse_network(_browse(["network"], "reading the network log failed"), base_url)
        writes = [r for r in requests if r["method"] != "GET"]
    else:
        _mark(base_url, log, offset, u, "end")
        try:
            sl = access_log.slice_between(_read_from(log, offset).splitlines(), u)
        except access_log.AccessLogError as exc:
            raise fail(CMD, exc.code, exc.message, "doctor") from None
        requests, writes = sl["requests"], sl["writes"]
    return {
        "testid": testid, "requests": requests, "writes": writes,
        "url_before": url_before, "url_after": url_after, "url_changed": url_before != url_after,
        "attrs_before": attrs_before, "attrs_after": attrs_after,
        "inert": compute_inert(requests, url_before, url_after, attrs_before, attrs_after),
        "mechanism": mech,
    }


def cmd_inert(ns):
    def body():
        parsed = _parse(ns)
        if isinstance(parsed, dict):
            return parsed
        testid, action, expect, settle, mech = parsed
        if action:
            try:
                browse.check_subcommand(action[0], passthrough=True)
            except browse.BrowseRefused as exc:
                return failure(CMD, exc.code, exc.message, TRY_PREFIX + "ui inert --help")
        data = _measure(testid, action, settle, mech, _instance())
        if expect is not None and data["inert"] != (expect == "inert"):
            got = "inert" if data["inert"] else "active"
            raise Fail(failure(CMD, "unexpected_inertness", f"expected {expect}, measured {got}",
                               TRY_PREFIX + "ui inert --help", data=data))
        return success(CMD, data)

    return run(CMD, body)
