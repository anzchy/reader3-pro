"""018 WI-3 / WI-2: ETag on the settings GETs, If-Match on the four settings writers.

Matrix cases R3-2-01 .. R3-2-11, R3-2-14 .. R3-2-16, R3-2-18, R3-2-20
(``.claude/tdd-guardian/tests-20261001-114124.md``). R3-2-12, -13, -19, -21 live in
``tests/unit/test_settings_revision_loop.py`` (they need ``httpx.ASGITransport`` or
their own settings directory). R3-2-17 is the existing route-inventory test plus
``scripts/check_router_size.py``, run unchanged.

Every case runs under the ``world`` fixture, which redirects load / save / the
settings transaction to ``world.settings_path`` (a tmp file seeded with the
anthropic key ``sk-fixture-not-a-real-key``).

The expected ETag is computed from the bytes on disk with the same in-process
HMAC key (``ai_config.settings_revision``). That is not a tautology: the test reads
the file itself, independently of the handler.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional, Tuple

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from reader3_app.ai import config as ai_config
from reader3_app.web import server

#: The fixed 409 body text. A client cannot learn the current revision from it.
CONFLICT_DETAIL = "Settings were changed elsewhere since this page loaded them. Reload and try again."

ETAG_RE = re.compile(r'^"[0-9a-f]{64}"$')

SEEDED_KEY = "sk-fixture-not-a-real-key"
LOSER_KEY = "sk-loser-submitted-key"

PROVIDERS = ("anthropic", "openai", "gemini", "ollama", "openrouter")

#: name -> (method, url, json body)
WRITERS: Dict[str, Tuple[str, str, Optional[dict]]] = {
    "put_settings": ("PUT", "/api/settings", {"preferences": {"theme": "dark"}}),
    "import": ("POST", "/api/settings/import", {"preferences": {"theme": "dark"}}),
    "put_provider": ("PUT", "/api/settings/providers/ollama", {"model_name": "m-new"}),
    "delete": ("DELETE", "/api/settings/providers/openai", None),
}
SUCCESS_STATUS = {"put_settings": 200, "import": 200, "put_provider": 200, "delete": 204}

GETS: Dict[str, Tuple[str, str, Optional[dict]]] = {
    "get_settings": ("GET", "/api/settings", None),
    "get_provider": ("GET", "/api/settings/providers/anthropic", None),
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def etag_of(path: Path) -> str:
    raw = path.read_bytes() if path.exists() else None
    return '"' + ai_config.settings_revision(raw) + '"'


def absent_etag() -> str:
    return '"' + ai_config.settings_revision(None) + '"'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fmode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def call(client: TestClient, method: str, url: str, body: Optional[dict], if_match: Optional[str] = None):
    headers = {} if if_match is None else {"If-Match": if_match}
    if body is None:
        return client.request(method, url, headers=headers)
    return client.request(method, url, json=body, headers=headers)


def run_writer(client: TestClient, writer: str, if_match: Optional[str] = None, body: Optional[dict] = None):
    method, url, default_body = WRITERS[writer]
    return call(client, method, url, default_body if body is None else body, if_match)


def provider_from(body: dict, name: str) -> dict:
    return next(p for p in body["providers"] if p["name"] == name)


def default_model(name: str) -> str:
    return str(ai_config.default_settings_dict()["providers"][name]["model_name"])


def assert_writer_effect(client: TestClient, writer: str) -> None:
    body = client.get("/api/settings").json()
    if writer in ("put_settings", "import"):
        assert body["preferences"]["theme"] == "dark"
    elif writer == "put_provider":
        assert provider_from(body, "ollama")["model_name"] == "m-new"
    else:
        assert provider_from(body, "openai")["model_name"] == default_model("openai")


def make_stale(client: TestClient) -> str:
    """A real historic revision: the ETag of a GET before an unconditional write."""
    stale = client.get("/api/settings").headers.get("etag")
    assert stale is not None and ETAG_RE.match(stale), f"GET carried no strong ETag: {stale!r}"
    r = client.put("/api/settings", json={"preferences": {"theme": "light"}})
    assert r.status_code == 200
    return stale


def unquote(tag: str) -> str:
    return tag.strip('"')


# --------------------------------------------------------------------------
# R3-2-01 .. R3-2-04: GET handlers carry the file revision
# --------------------------------------------------------------------------


@pytest.mark.parametrize("url", ["/api/settings", "/api/settings/providers/anthropic"])
def test_gets_carry_the_file_revision(world, url: str) -> None:
    path = world.settings_path
    resp = world.client.get(url)
    assert resp.status_code == 200
    etag = resp.headers.get("etag")
    assert etag is not None and ETAG_RE.match(etag)
    assert etag == etag_of(path)

    settings = ai_config.load_ai_settings(str(path))
    if url == "/api/settings":
        expected = server._public_settings_response(settings)
    else:
        expected = server._public_provider_config("anthropic", settings=settings)
    assert resp.json() == json.loads(json.dumps(expected))


def test_get_etag_follows_hand_edits(world) -> None:
    path = world.settings_path
    e1 = world.client.get("/api/settings").headers.get("etag")
    with open(path, "ab") as f:
        f.write(b" ")
    e2 = world.client.get("/api/settings").headers.get("etag")
    assert e1 is not None and e2 is not None
    assert e1 != e2
    assert e2 == etag_of(path)


def test_get_on_absent_file_creates_only_the_lock(world) -> None:
    path = world.settings_path
    path.unlink()
    r1 = world.client.get("/api/settings")
    r2 = world.client.get("/api/settings/providers/ollama")
    assert r1.status_code == 200 and r2.status_code == 200
    defaults = ai_config.default_settings_dict()
    assert r1.json() == json.loads(json.dumps(server._public_settings_response(defaults)))
    assert r2.json() == json.loads(json.dumps(server._public_provider_config("ollama", settings=defaults)))
    assert r1.headers.get("etag") == absent_etag()
    assert r2.headers.get("etag") == absent_etag()
    assert not path.exists()
    listing = os.listdir(path.parent)
    assert ".ai_settings.lock" in listing
    assert "ai_settings.json" not in listing
    assert not any(name.endswith(".tmp") for name in listing)


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a 0000 file")
def test_unreadable_file_keeps_the_named_500(world) -> None:
    path = world.settings_path
    before = path.read_bytes()
    old_mode = fmode(path)
    os.chmod(path, 0)
    try:
        client = TestClient(server.app, base_url="http://127.0.0.1", raise_server_exceptions=False)
        r_get = client.get("/api/settings")
        r_put = client.put("/api/settings/providers/ollama", json={"model_name": "m-new"})
    finally:
        os.chmod(path, old_mode)
    assert r_get.status_code == 500
    assert "ai_settings.json" in r_get.json()["detail"]
    assert r_put.status_code == 500
    assert "ai_settings.json" in r_put.json()["detail"]
    assert path.read_bytes() == before


# Review fix-up M1: the lock file cannot be created (config/ not writable).
# The two GETs fall back to an unlocked read and still carry the ETag of the
# bytes they read; writers keep failing with a 500 that names the lock path.
LOCK_FAILURES = ["dir_0500", "open_raises"]


@pytest.mark.parametrize("mechanism", LOCK_FAILURES)
def test_unlockable_config_dir_keeps_gets_and_names_the_lock_for_writers(world, monkeypatch, mechanism: str) -> None:
    path = world.settings_path
    lock = path.parent / ".ai_settings.lock"
    before = path.read_bytes()
    expected_etag = '"' + ai_config.settings_revision(before) + '"'
    client = TestClient(server.app, base_url="http://127.0.0.1", raise_server_exceptions=False)

    if mechanism == "dir_0500":
        if os.geteuid() == 0:
            pytest.skip("root ignores directory write permission")
        assert not lock.exists()
        old_mode = fmode(path.parent)
        os.chmod(path.parent, 0o500)
    else:
        real_open = os.open

        def refusing_open(file: Any, flags: int, *a: Any, **kw: Any) -> int:
            if os.path.basename(os.fspath(file)) == ".ai_settings.lock":
                raise PermissionError(13, "Permission denied", os.fspath(file))
            return real_open(file, flags, *a, **kw)

        monkeypatch.setattr(os, "open", refusing_open)

    try:
        r_get = client.get("/api/settings")
        r_get_provider = client.get("/api/settings/providers/anthropic")
        r_put = client.put("/api/settings/providers/ollama", json={"model_name": "m-new"})
        r_put_cond = client.put(
            "/api/settings", json={"preferences": {"theme": "dark"}}, headers={"If-Match": expected_etag}
        )
    finally:
        if mechanism == "dir_0500":
            os.chmod(path.parent, old_mode)
        else:
            monkeypatch.setattr(os, "open", real_open)

    settings = ai_config.load_ai_settings(str(path))
    assert r_get.status_code == 200
    assert r_get.headers.get("etag") == expected_etag
    assert r_get.json() == json.loads(json.dumps(server._public_settings_response(settings)))
    assert r_get_provider.status_code == 200
    assert r_get_provider.headers.get("etag") == expected_etag
    assert r_get_provider.json() == json.loads(json.dumps(server._public_provider_config("anthropic", settings=settings)))

    for resp in (r_put, r_put_cond):
        assert resp.status_code == 500
        detail = resp.json()["detail"]
        assert ".ai_settings.lock" in detail or "ai_settings.json" in detail
        assert str(lock) in detail
    assert path.read_bytes() == before


def test_malformed_if_match_with_a_space_is_400_and_writes_nothing(world) -> None:
    path = world.settings_path
    before = path.read_bytes()
    resp = world.client.put("/api/settings", json={"preferences": {"theme": "dark"}}, headers={"If-Match": '"a b"'})
    assert resp.status_code == 400
    assert resp.json() == {"detail": "Malformed If-Match header"}
    assert path.read_bytes() == before


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a 0000 file")
def test_unreadable_file_under_if_match_is_the_named_500_not_400_or_409(world) -> None:
    path = world.settings_path
    before = path.read_bytes()
    old_mode = fmode(path)
    os.chmod(path, 0)
    try:
        client = TestClient(server.app, base_url="http://127.0.0.1", raise_server_exceptions=False)
        resp = client.put(
            "/api/settings/providers/ollama", json={"model_name": "m-new"}, headers={"If-Match": '"' + "0" * 64 + '"'}
        )
    finally:
        os.chmod(path, old_mode)
    assert resp.status_code == 500
    assert "ai_settings.json" in resp.json()["detail"]
    assert path.read_bytes() == before


# --------------------------------------------------------------------------
# R3-2-05 .. R3-2-11: writers and the If-Match precondition
# --------------------------------------------------------------------------


@pytest.mark.parametrize("cond", ["matching", "stale", "absent", "star", "weak", "malformed"])
@pytest.mark.parametrize("writer", list(WRITERS))
def test_writer_precondition_table(world, writer: str, cond: str) -> None:
    client, path = world.client, world.settings_path
    stale = make_stale(client)
    current = etag_of(path)
    assert stale != current
    header = {
        "matching": current,
        "stale": stale,
        "absent": None,
        "star": "*",
        "weak": "W/" + current,
        "malformed": unquote(current),
    }[cond]

    sha_before, mode_before = sha(path), fmode(path)
    resp = run_writer(client, writer, header)

    if cond in ("matching", "absent", "star"):
        assert resp.status_code == SUCCESS_STATUS[writer]
        assert resp.headers.get("etag") == etag_of(path)
        assert_writer_effect(client, writer)
    elif cond in ("stale", "weak"):
        assert resp.status_code == 409
        assert resp.json() == {"detail": CONFLICT_DETAIL}
        assert sha(path) == sha_before and fmode(path) == mode_before
    else:
        assert resp.status_code == 400
        assert sha(path) == sha_before and fmode(path) == mode_before


@pytest.mark.parametrize("writer", list(WRITERS))
def test_conflict_body_leaks_nothing(world, writer: str) -> None:
    client, path = world.client, world.settings_path
    stale = make_stale(client)
    bodies: Dict[str, Optional[dict]] = {
        "put_settings": None,
        "import": {"preferences": {"theme": "dark"}, "providers": {"anthropic": {"api_key": LOSER_KEY}}},
        "put_provider": {"model_name": "m-new", "api_key": LOSER_KEY},
        "delete": None,
    }
    cur_hex = unquote(etag_of(path))
    stale_hex = unquote(stale)
    resp = run_writer(client, writer, stale, body=bodies[writer])

    assert resp.status_code == 409
    assert set(resp.json()) == {"detail"}
    for needle in (SEEDED_KEY, LOSER_KEY, cur_hex, stale_hex):
        assert needle not in resp.text
    assert resp.headers.get("etag") is None
    for name, value in resp.headers.multi_items():
        assert cur_hex not in value, name
        assert stale_hex not in value, name
        assert "sk-" not in value, name


PRECEDENCE_ROWS = [
    # id, method, url, body, condition, status, detail (exact) or None, detail it must NOT be
    ("put_provider_bad_body_stale", "PUT", "/api/settings/providers/ollama", {"timeout": "abc"}, "stale", 422, None, None),
    ("put_unknown_provider_stale", "PUT", "/api/settings/providers/bogus", {}, "stale", 404, "Provider not found", None),
    ("put_unknown_provider_malformed", "PUT", "/api/settings/providers/bogus", {}, "malformed", 404, None, None),
    ("delete_unknown_provider_stale", "DELETE", "/api/settings/providers/bogus", None, "stale", 404, None, None),
    ("bogus_default_malformed", "PUT", "/api/settings", {"default_provider": "bogus"}, "malformed", 400, None, "Invalid default_provider"),
    ("bogus_default_stale", "PUT", "/api/settings", {"default_provider": "bogus"}, "stale", 409, None, None),
    ("bogus_default_matching", "PUT", "/api/settings", {"default_provider": "bogus"}, "matching", 400, "Invalid default_provider", None),
    ("import_list_body_stale", "POST", "/api/settings/import", [], "stale", 422, None, None),
]


@pytest.mark.parametrize(
    "method,url,body,cond,status,detail,not_detail",
    [row[1:] for row in PRECEDENCE_ROWS],
    ids=[row[0] for row in PRECEDENCE_ROWS],
)
def test_precondition_precedence(world, method, url, body, cond, status, detail, not_detail) -> None:
    client, path = world.client, world.settings_path
    stale = make_stale(client)
    current = etag_of(path)
    header = {"stale": stale, "matching": current, "malformed": unquote(current)}[cond]
    sha_before = sha(path)

    headers = {"If-Match": header}
    resp = client.request(method, url, headers=headers) if body is None else client.request(method, url, json=body, headers=headers)

    assert resp.status_code == status
    if detail is not None:
        assert resp.json()["detail"] == detail
    if not_detail is not None:
        assert resp.json().get("detail") != not_detail
    assert sha(path) == sha_before


def test_empty_model_name_is_not_rewritten_as_400(world) -> None:
    path = world.settings_path
    seed, seed_mode = path.read_bytes(), fmode(path)
    client = TestClient(server.app, base_url="http://127.0.0.1", raise_server_exceptions=False)

    def restore() -> None:
        path.write_bytes(seed)
        os.chmod(path, seed_mode)

    restore()
    r1 = client.put("/api/settings/providers/ollama", json={"model_name": "   "})
    with open(path, encoding="utf-8") as f:
        disk1 = json.load(f)

    restore()
    r2 = client.put("/api/settings/providers/ollama", json={"model_name": "   "}, headers={"If-Match": etag_of(path)})
    with open(path, encoding="utf-8") as f:
        disk2 = json.load(f)

    assert r1.status_code == r2.status_code
    assert r1.status_code != 400
    assert disk1 == disk2


def test_issue_51_second_stale_save_is_refused(world) -> None:
    client, path = world.client, world.settings_path
    ra = client.get("/api/settings/providers/ollama").headers.get("etag")
    rb = client.get("/api/settings/providers/ollama").headers.get("etag")
    assert ra is not None and ra == rb
    r = ra

    a = client.put("/api/settings/providers/ollama", json={"model_name": "from-A"}, headers={"If-Match": r})
    assert a.status_code == 200
    assert a.headers.get("etag") is not None and a.headers.get("etag") != r
    bytes_a = path.read_bytes()

    b = client.put("/api/settings/providers/ollama", json={"model_name": "from-B"}, headers={"If-Match": r})
    assert b.status_code == 409
    assert path.read_bytes() == bytes_a
    assert client.get("/api/settings/providers/ollama").json()["model_name"] == "from-A"


# R3-2-10 ------------------------------------------------------------------

CONDS = ("absent", "star", "current", "historic")
INDEX = st.integers(min_value=0, max_value=1000)
OP = st.one_of(
    st.tuples(st.just("put_provider"), st.sampled_from(PROVIDERS), st.text("abc", min_size=1, max_size=3), st.sampled_from(CONDS), INDEX),
    st.tuples(st.just("put_prefs"), st.sampled_from(("light", "dark")), st.sampled_from(CONDS), INDEX),
    st.tuples(st.just("delete"), st.sampled_from(PROVIDERS), st.sampled_from(CONDS), INDEX),
    st.just(("hand_edit",)),
)


def _projection(client: TestClient) -> Tuple[Dict[str, str], str]:
    body = client.get("/api/settings").json()
    return ({p["name"]: p["model_name"] for p in body["providers"]}, body["preferences"]["theme"])


def _hand_edit(path: Path) -> None:
    if not path.exists():
        return
    st_ = os.stat(path)
    data = path.read_bytes()
    if data.endswith(b" "):
        data = data[:-1] + b"\t"
    elif data.endswith(b"\t"):
        data = data[:-1] + b" "
    else:
        data = data + b" "
    with open(path, "r+b") as f:
        f.write(data)
        f.truncate()
    os.utime(path, ns=(st_.st_atime_ns, st_.st_mtime_ns))


@hsettings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(ops=st.lists(OP, min_size=1, max_size=8))
def test_precondition_and_chaining_law(world, ops: List[tuple]) -> None:
    client, path = world.client, world.settings_path
    seed = world.__dict__.setdefault("_seed_bytes", path.read_bytes())
    path.write_bytes(seed)
    os.chmod(path, 0o600)

    models, theme = _projection(client)
    seen: List[str] = []

    for op in ops:
        pre = client.get("/api/settings")
        current = pre.headers.get("etag")
        assert current is not None and current == etag_of(path)

        if op[0] == "hand_edit":
            _hand_edit(path)
            after = client.get("/api/settings").headers.get("etag")
            assert after == etag_of(path)
            assert after != current
            seen.extend([current, after])
            continue

        cond, index = op[-2], op[-1]
        if cond == "absent":
            header: Optional[str] = None
        elif cond == "star":
            header = "*"
        elif cond == "current":
            header = current
        else:
            header = seen[index % len(seen)] if seen else current
        fresh = cond in ("absent", "star") or header == current
        sha_before, mode_before = sha(path), fmode(path)

        if op[0] == "put_provider":
            _, name, model, _, _ = op
            resp = call(client, "PUT", f"/api/settings/providers/{name}", {"model_name": model}, header)
        elif op[0] == "put_prefs":
            _, new_theme, _, _ = op
            resp = call(client, "PUT", "/api/settings", {"preferences": {"theme": new_theme}}, header)
        else:
            _, name, _, _ = op
            resp = call(client, "DELETE", f"/api/settings/providers/{name}", None, header)

        if fresh:
            assert resp.status_code in (200, 204), (op, resp.status_code, resp.text)
            next_etag = client.get("/api/settings").headers.get("etag")
            assert resp.headers.get("etag") == next_etag == etag_of(path)
            if op[0] == "put_provider":
                models[op[1]] = op[2]
            elif op[0] == "put_prefs":
                theme = op[1]
            else:
                models[op[1]] = default_model(op[1])
            assert _projection(client) == (models, theme)
            seen.extend([current, str(resp.headers.get("etag"))])
        else:
            assert resp.status_code == 409, (op, resp.status_code, resp.text)
            assert sha(path) == sha_before and fmode(path) == mode_before
            assert _projection(client) == (models, theme)
            seen.append(current)

    assert _projection(client) == (models, theme)


@pytest.mark.parametrize("writer", list(WRITERS))
def test_star_and_matching_equal_unconditional(world, writer: str) -> None:
    path = world.settings_path
    seed, seed_mode = path.read_bytes(), fmode(path)
    outcomes = []
    for cond in ("absent", "star", "matching"):
        path.write_bytes(seed)
        os.chmod(path, seed_mode)
        header = {"absent": None, "star": "*", "matching": etag_of(path)}[cond]
        resp = run_writer(world.client, writer, header)
        body: Any = resp.json() if resp.content else b""
        outcomes.append((resp.status_code, body, sha(path)))
    assert outcomes[0] == outcomes[1] == outcomes[2]


# --------------------------------------------------------------------------
# R3-2-14 .. R3-2-16
# --------------------------------------------------------------------------


def test_absent_file_first_write_then_stale(world) -> None:
    client, path = world.client, world.settings_path
    path.unlink()
    e0 = client.get("/api/settings/providers/ollama").headers.get("etag")
    assert e0 == absent_etag()

    first = client.put("/api/settings/providers/ollama", json={"model_name": "first"}, headers={"If-Match": e0})
    assert first.status_code == 200
    assert path.exists() and fmode(path) == 0o600
    e1 = first.headers.get("etag")
    assert e1 != e0 and e1 == etag_of(path)

    second = client.put("/api/settings/providers/ollama", json={"model_name": "second"}, headers={"If-Match": e0})
    assert second.status_code == 409
    with open(path, encoding="utf-8") as f:
        assert json.load(f)["providers"]["ollama"]["model_name"] == "first"

    path.unlink()
    star = client.put("/api/settings/providers/ollama", json={"model_name": "starred"}, headers={"If-Match": "*"})
    assert star.status_code == 200


def _repo_fingerprint(repo_root: Path) -> tuple:
    settings = repo_root / "config" / "ai_settings.json"
    lock = repo_root / "config" / ".ai_settings.lock"
    s = (True, hashlib.md5(settings.read_bytes()).hexdigest(), fmode(settings)) if settings.exists() else (False, None, None)
    lk = (True, os.stat(lock).st_ino) if lock.exists() else (False, None)
    return (s, lk)


def test_settings_routes_never_touch_the_repo_config(world, repo_root: Path) -> None:
    client, path = world.client, world.settings_path
    before = _repo_fingerprint(repo_root)
    for method, url, body in GETS.values():
        assert call(client, method, url, body).status_code == 200
    for name in WRITERS:
        assert run_writer(client, name).status_code == SUCCESS_STATUS[name]
        assert run_writer(client, name, etag_of(path)).status_code == SUCCESS_STATUS[name]
    assert _repo_fingerprint(repo_root) == before
    assert (path.parent / ".ai_settings.lock").exists()


@pytest.mark.parametrize("writer", list(WRITERS))
def test_writers_keep_0600(world, writer: str) -> None:
    path = world.settings_path
    os.chmod(path, 0o644)
    resp = run_writer(world.client, writer, etag_of(path))
    assert resp.status_code == SUCCESS_STATUS[writer]
    assert fmode(path) == 0o600


# --------------------------------------------------------------------------
# R3-2-18: every settings I/O happens inside the request's single hold
# --------------------------------------------------------------------------

SCOPE_IDS = ["get_settings-no_if_match", "get_provider-no_if_match"] + [
    f"{w}-{c}" for w in WRITERS for c in ("no_if_match", "matching")
]


@pytest.mark.parametrize("case", SCOPE_IDS)
def test_every_settings_io_happens_inside_the_requests_single_hold(world, monkeypatch, case: str) -> None:
    route, cond = case.split("-")
    path = world.settings_path
    lock = path.parent / ".ai_settings.lock"
    state = SimpleNamespace(entries=0, active=False, records=[])

    real_txn = server.ai_settings_transaction
    real_load = server.load_ai_settings
    real_save = server.save_ai_settings

    @contextlib.contextmanager
    def instrumented(*a: Any, **kw: Any) -> Iterator[Any]:
        state.entries += 1
        with real_txn(*a, **kw) as h:
            state.active = True
            try:
                yield h
            finally:
                state.active = False
        if path.exists():
            with open(path, "ab") as f:
                f.write(b" ")

    def probe() -> bool:
        try:
            fd = os.open(lock, os.O_RDWR)
        except FileNotFoundError:
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            blocked = False
            fcntl.flock(fd, fcntl.LOCK_UN)
        except BlockingIOError:
            blocked = True
        finally:
            os.close(fd)
        return blocked

    def spy_load(*a: Any, **kw: Any) -> Any:
        blocked = probe()
        raw = path.read_bytes() if path.exists() else None
        state.records.append(("load", state.active, blocked, ai_config.settings_revision(raw)))
        return real_load(*a, **kw)

    def spy_save(*a: Any, **kw: Any) -> Any:
        blocked = probe()
        result = real_save(*a, **kw)
        state.records.append(("save", state.active, blocked, ai_config.settings_revision(path.read_bytes())))
        return result

    monkeypatch.setattr(server, "ai_settings_transaction", instrumented)
    monkeypatch.setattr(server, "load_ai_settings", spy_load)
    monkeypatch.setattr(server, "save_ai_settings", spy_save)

    header = etag_of(path) if cond == "matching" else None
    if route in GETS:
        method, url, body = GETS[route]
        resp = call(world.client, method, url, body, header)
        expected_status = 200
    else:
        resp = run_writer(world.client, route, header)
        expected_status = SUCCESS_STATUS[route]

    assert resp.status_code == expected_status
    assert state.entries == 1
    loads = [r for r in state.records if r[0] == "load"]
    saves = [r for r in state.records if r[0] == "save"]
    assert len(loads) >= 1
    if route in WRITERS:
        assert len(saves) >= 1
    for record in state.records:
        assert record[1] is True, record
        assert record[2] is True, record

    etag = resp.headers.get("etag")
    if route in WRITERS:
        assert etag == '"' + saves[-1][3] + '"'
    else:
        assert etag == '"' + loads[0][3] + '"'
    assert etag != etag_of(path)


# --------------------------------------------------------------------------
# R3-2-20: same-size hand edit with restored mtime
# --------------------------------------------------------------------------


@pytest.mark.parametrize("writer", list(WRITERS))
def test_same_size_hand_edit_with_restored_mtime_is_detected(world, writer: str) -> None:
    client, path = world.client, world.settings_path
    e_old = client.get("/api/settings").headers.get("etag")
    st_ = os.stat(path)
    data = path.read_bytes()
    assert data.count(b"sk-fixture-not-a-real-key") == 1
    with open(path, "r+b") as f:
        f.write(data.replace(b"sk-fixture-not-a-real-key", b"sk-fixture-not-a-real-kez"))
    os.utime(path, ns=(st_.st_atime_ns, st_.st_mtime_ns))
    now = os.stat(path)
    assert now.st_size == st_.st_size
    assert now.st_mtime_ns == st_.st_mtime_ns
    assert now.st_ino == st_.st_ino
    edited, mode_before = path.read_bytes(), fmode(path)

    e_new = client.get("/api/settings").headers.get("etag")
    assert e_new != e_old
    assert e_new == etag_of(path)

    resp = run_writer(client, writer, e_old)
    assert resp.status_code == 409
    assert resp.json() == {"detail": CONFLICT_DETAIL}
    assert path.read_bytes() == edited
    assert fmode(path) == mode_before
