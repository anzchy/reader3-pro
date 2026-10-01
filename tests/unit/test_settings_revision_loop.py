"""018 WI-3 / WI-2: settings routes under real lock contention (matrix R3-2-12, -13, -19, -21).

These cases drive the real app through ``httpx.AsyncClient(transport=ASGITransport)``
(or ``TestClient`` for R3-2-19), with the real threadpool, real ``flock`` and the
real filesystem under ``tmp_path``. Load, save and the settings transaction are
bound to one tmp path with ``functools.partial`` (seam pairing, R3-1-19).

Contention is made by a test thread that opens ``.ai_settings.lock`` on its own fd
and holds ``LOCK_EX``. That holder releases on its own after ``MAX_HOLD_S`` so an
implementation that takes the lock on the event-loop thread fails an assertion
instead of hanging the loop forever.

As in ``test_event_loop_not_blocked.py``: no ``pytest-asyncio``; each async case is
run with ``asyncio.run`` under an outer ``asyncio.wait_for``.
"""

from __future__ import annotations

import asyncio
import fcntl
import functools
import hashlib
import json
import os
import stat
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional, Tuple

import httpx
import pytest
from fastapi.testclient import TestClient

from reader3_app.ai import config as ai_config
from reader3_app.web import server

CONFLICT_DETAIL = "Settings were changed elsewhere since this page loaded them. Reload and try again."

#: The holder thread gives the lock back on its own after this long.
MAX_HOLD_S = 4.0
HARD_BOUND_S = 20.0

ROUTES6: Dict[str, Tuple[str, str, Optional[dict], int]] = {
    "get_settings": ("GET", "/api/settings", None, 200),
    "get_provider": ("GET", "/api/settings/providers/anthropic", None, 200),
    "put_settings": ("PUT", "/api/settings", {"preferences": {"theme": "dark"}}, 200),
    "import": ("POST", "/api/settings/import", {"preferences": {"theme": "dark"}}, 200),
    "put_provider": ("PUT", "/api/settings/providers/ollama", {"model_name": "m-new"}, 200),
    "delete_provider": ("DELETE", "/api/settings/providers/openai", None, 204),
}


# --------------------------------------------------------------------------
# environment
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _never_touch_the_real_settings_file(repo_root: Path):
    real = repo_root / "config" / "ai_settings.json"
    lock = repo_root / "config" / ".ai_settings.lock"

    def fingerprint() -> tuple:
        s = (True, hashlib.md5(real.read_bytes()).hexdigest()) if real.exists() else (False, None)
        return (s, lock.exists())

    before = fingerprint()
    yield
    assert fingerprint() == before, f"a test touched the real settings directory: {real.parent}"


def _bind_settings(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setenv("READER3_AI_SETTINGS", str(path))
    monkeypatch.setattr(ai_config, "DEFAULT_SETTINGS_PATH", str(path))
    monkeypatch.setattr(server, "load_ai_settings", functools.partial(ai_config.load_ai_settings, path=str(path)))
    monkeypatch.setattr(server, "save_ai_settings", functools.partial(ai_config.save_ai_settings, path=str(path)))
    monkeypatch.setattr(
        server,
        "ai_settings_transaction",
        functools.partial(ai_config.ai_settings_transaction, path=str(path)),
    )
    monkeypatch.setattr(server.book_uuid_resolver, "books_dir", str(path.parent / "no-books-here"))


@pytest.fixture
def settings_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "config" / "ai_settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(ai_config.default_settings_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    os.chmod(path, 0o600)
    _bind_settings(monkeypatch, path)
    return path


def etag_of(path: Path) -> str:
    raw = path.read_bytes() if path.exists() else None
    return '"' + ai_config.settings_revision(raw) + '"'


def fmode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def on_disk(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def asgi_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://127.0.0.1")


def send(client: httpx.AsyncClient, method: str, url: str, body: Optional[dict], headers: Optional[dict] = None):
    if body is None:
        return client.request(method, url, headers=headers or {})
    return client.request(method, url, json=body, headers=headers or {})


class LockHolder:
    """Holds ``LOCK_EX`` on the settings lock from its own thread and its own fd."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self.held = threading.Event()
        self.release = threading.Event()
        self.forced = False
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            self.held.set()
            if not self.release.wait(MAX_HOLD_S):
                self.forced = True
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def __enter__(self) -> "LockHolder":
        self.thread.start()
        assert self.held.wait(5), "the test thread could not take the settings lock"
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release.set()
        self.thread.join(5)


class EntryCounter:
    """Counts calls into ``server.ai_settings_transaction`` *before* the real one runs.

    A barrier, not a guess: the scenario waits until N requests have reached the
    transaction (and so will block on the held lock) before it releases the holder.
    ``asyncio.sleep(0)`` a few times gave no such guarantee, so the first request
    could finish before the second compared, and a compare-outside-the-lock
    implementation could pass.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.count = 0
        self._guard = threading.Lock()
        real = server.ai_settings_transaction

        def counting(*a: Any, **kw: Any) -> Any:
            with self._guard:
                self.count += 1
            return real(*a, **kw)

        monkeypatch.setattr(server, "ai_settings_transaction", counting)

    async def reached(self, n: int, timeout_s: float = 5.0) -> None:
        deadline = time.monotonic() + timeout_s
        while self.count < n:
            assert time.monotonic() < deadline, f"only {self.count} of {n} requests reached the settings transaction"
            await asyncio.sleep(0.01)


# --------------------------------------------------------------------------
# R3-2-12: unconditional concurrent PUTs to different providers both persist
# --------------------------------------------------------------------------


def test_unconditional_concurrent_puts_are_conserved(settings_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Conservation under real threadpool concurrency.

    ``inside`` counts requests that are between their read (load) and their write
    (save). The spy widens that window: after a load it waits up to 0.2s for a
    second request to load too. Without the lock both load before either saves,
    one update is lost and ``max_inside == 2``.

    The handlers also re-read the settings once *after* the save, for the response
    body (R3-2-18 requires that re-read inside the hold). That load is not the
    start of a read-modify-write window, so it is not counted: a per-thread flag
    set by the save marks the next load on that thread as the response re-read.
    """
    real_load = server.load_ai_settings
    real_save = server.save_ai_settings
    state = SimpleNamespace(inside=0, max_inside=0, guard=threading.Lock(), both=threading.Event())
    local = threading.local()

    def spy_load(*a: Any, **kw: Any) -> Any:
        result = real_load(*a, **kw)
        if getattr(local, "after_save", False):
            local.after_save = False
            return result
        with state.guard:
            state.inside += 1
            state.max_inside = max(state.max_inside, state.inside)
            if state.inside >= 2:
                state.both.set()
        state.both.wait(0.2)
        return result

    def spy_save(*a: Any, **kw: Any) -> Any:
        result = real_save(*a, **kw)
        with state.guard:
            state.inside -= 1
        local.after_save = True
        return result

    monkeypatch.setattr(server, "load_ai_settings", spy_load)
    monkeypatch.setattr(server, "save_ai_settings", spy_save)

    async def scenario() -> Tuple[httpx.Response, httpx.Response]:
        async with asgi_client() as client:
            a, b = await asyncio.gather(
                client.put("/api/settings/providers/openai", json={"model_name": "o-1"}),
                client.put("/api/settings/providers/gemini", json={"model_name": "g-1"}),
            )
            return a, b

    a, b = asyncio.run(asyncio.wait_for(scenario(), HARD_BOUND_S))
    assert a.status_code == 200 and b.status_code == 200
    disk = on_disk(settings_path)
    assert disk["providers"]["openai"]["model_name"] == "o-1"
    assert disk["providers"]["gemini"]["model_name"] == "g-1"
    assert state.max_inside == 1


# --------------------------------------------------------------------------
# R3-2-13: the event loop stays responsive while the lock is contended
# --------------------------------------------------------------------------


@pytest.mark.parametrize("route", list(ROUTES6))
def test_contended_lock_does_not_block_the_loop(settings_path: Path, route: str, monkeypatch: pytest.MonkeyPatch) -> None:
    method, url, body, status = ROUTES6[route]
    before = settings_path.read_bytes()
    holder = LockHolder(settings_path.parent / ".ai_settings.lock")
    entries = EntryCounter(monkeypatch)

    async def scenario() -> Tuple[list, httpx.Response, bool, httpx.Response]:
        order: list = []
        async with asgi_client() as client:
            with holder:
                task = asyncio.create_task(send(client, method, url, body))
                task.add_done_callback(lambda _t: order.append("route"))
                await entries.reached(1)
                health = await asyncio.wait_for(client.get("/api/health"), 5)
                order.append("health")
                route_done_at_health = task.done()
                holder.release.set()
                resp = await asyncio.wait_for(task, 5)
        return order, health, route_done_at_health, resp

    order, health, route_done_at_health, resp = asyncio.run(asyncio.wait_for(scenario(), HARD_BOUND_S))
    assert not holder.forced, "the lock had to be released by timeout: the loop was blocked"
    assert health.status_code == 200
    assert route_done_at_health is False
    assert order[0] == "health"
    assert resp.status_code == status
    assert resp.headers.get("etag") == etag_of(settings_path)

    disk = on_disk(settings_path)
    if route in ("put_settings", "import"):
        assert disk["preferences"]["theme"] == "dark"
    elif route == "put_provider":
        assert disk["providers"]["ollama"]["model_name"] == "m-new"
    elif route == "delete_provider":
        assert "openai" not in disk["providers"]
        merged = ai_config.load_ai_settings(str(settings_path))
        assert merged["providers"]["openai"]["model_name"] == ai_config.default_settings_dict()["providers"]["openai"]["model_name"]
    else:
        assert settings_path.read_bytes() == before


# --------------------------------------------------------------------------
# R3-2-19: settings directory absent
# --------------------------------------------------------------------------


def test_absent_settings_directory_is_created_on_demand(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings_path = tmp_path / "absent_dir" / "nested" / "ai_settings.json"
    assert not (tmp_path / "absent_dir").exists()
    _bind_settings(monkeypatch, settings_path)
    m = os.umask(0)
    os.umask(m)

    with TestClient(server.app, base_url="http://127.0.0.1") as client:
        got = client.get("/api/settings")
        assert got.status_code == 200
        defaults = ai_config.default_settings_dict()
        assert got.json() == json.loads(json.dumps(server._public_settings_response(defaults)))
        assert got.headers.get("etag") == '"' + ai_config.settings_revision(None) + '"'
        assert settings_path.parent.is_dir()
        assert (settings_path.parent / ".ai_settings.lock").exists()
        assert not settings_path.exists()

        put = client.put("/api/settings/providers/ollama", json={"model_name": "first"})
        assert put.status_code == 200
        assert put.headers.get("etag") == etag_of(settings_path)

    assert fmode(settings_path) == 0o600
    assert fmode(settings_path.parent / ".ai_settings.lock") == 0o600
    assert stat.S_IMODE(settings_path.parent.stat().st_mode) == 0o777 & ~m


# --------------------------------------------------------------------------
# R3-2-21: overlapping conditional writes with the same tag admit exactly one
# --------------------------------------------------------------------------

OVERLAP: Dict[str, Tuple[Tuple[str, str, Optional[dict]], Tuple[str, str, Optional[dict]], Any]] = {
    "put_provider": (
        ("PUT", "/api/settings/providers/ollama", {"model_name": "A"}),
        ("PUT", "/api/settings/providers/ollama", {"model_name": "B"}),
        lambda d: d["providers"]["ollama"]["model_name"],
    ),
    "put_settings": (
        ("PUT", "/api/settings", {"preferences": {"theme": "dark"}}),
        ("PUT", "/api/settings", {"preferences": {"theme": "light"}}),
        lambda d: d["preferences"]["theme"],
    ),
    "import": (
        ("POST", "/api/settings/import", {"preferences": {"theme": "dark"}}),
        ("POST", "/api/settings/import", {"preferences": {"theme": "light"}}),
        lambda d: d["preferences"]["theme"],
    ),
    "delete": (
        ("DELETE", "/api/settings/providers/openai", None),
        ("DELETE", "/api/settings/providers/openai", None),
        None,
    ),
}
WINNER_VALUE = {
    "put_provider": ("A", "B"),
    "put_settings": ("dark", "light"),
    "import": ("dark", "light"),
}


@pytest.mark.parametrize("case", list(OVERLAP))
def test_concurrent_conditional_writes_with_the_same_tag_admit_exactly_one(
    settings_path: Path, case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    req_a, req_b, field = OVERLAP[case]
    r = etag_of(settings_path)
    holder = LockHolder(settings_path.parent / ".ai_settings.lock")
    entries = EntryCounter(monkeypatch)

    async def scenario() -> Tuple[httpx.Response, httpx.Response]:
        async with asgi_client() as client:
            with holder:
                task_a = asyncio.create_task(send(client, *req_a, headers={"If-Match": r}))
                task_b = asyncio.create_task(send(client, *req_b, headers={"If-Match": r}))
                await entries.reached(2)
                holder.release.set()
                a, b = await asyncio.wait_for(asyncio.gather(task_a, task_b), 5)
        return a, b

    a, b = asyncio.run(asyncio.wait_for(scenario(), HARD_BOUND_S))
    ok = 204 if case == "delete" else 200
    assert sorted([a.status_code, b.status_code]) == [ok, 409]

    winner, loser = (a, b) if a.status_code == ok else (b, a)
    assert loser.json() == {"detail": CONFLICT_DETAIL}
    assert winner.headers.get("etag") == etag_of(settings_path)

    if field is not None:
        value_a, value_b = WINNER_VALUE[case]
        expected = value_a if winner is a else value_b
        assert field(on_disk(settings_path)) == expected
