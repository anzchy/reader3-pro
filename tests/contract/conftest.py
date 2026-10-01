"""Fixtures for the route-contract lane.

Every test in ``tests/contract/`` drives the real ``app`` object through
``TestClient``. The router tree is real; only the *world* around it is replaced.

Three things must be replaced, and each one has a reason it cannot be skipped:

1. ``server.BOOKS_DIR`` — a module-level constant read from ``READER3_BOOKS_DIR``
   at import time, with no per-request injection point. A test that forgets it
   writes annotations into the developer's real library. See ``isolated_world``.
2. ``ai.config.load_ai_settings`` / ``save_ai_settings`` — their path is a
   *default argument*, bound when the module was imported, so patching
   ``DEFAULT_SETTINGS_PATH`` does nothing. The functions themselves are replaced
   in the server's namespace instead. A ``PUT /api/settings`` that escaped this
   would rewrite the developer's ``config/ai_settings.json``.
3. ``server._call_provider`` and ``server._http_get_json`` — two of the three
   places ``server.py`` reaches the network. Both are stubbed unconditionally so
   that no contract test can bill an API key or hang on a DNS timeout.

   The third one is *not* stubbed here: the Ollama branch of ``api_ai_question``
   goes out through ``server._egress_post_stream`` rather than
   ``_call_provider``, so a contract case that enabled the ``ollama`` provider
   and asked for ``?stream=true`` would talk to the real network, and nothing in
   this file would stop it. What keeps this lane offline is narrower than it
   looks: ``_seed_settings`` enables ``anthropic``, and every provider path other
   than Ollama streaming funnels through ``_call_provider``.

   It *is* reachable per-test, and one test uses that:
   ``test_流式提问是边生成边推送而不是攒够一次性吐`` patches
   ``server._egress_post_stream`` itself. (This paragraph used to say no
   ``monkeypatch.setattr(server, ...)`` could reach it, because the branch called
   ``urllib.request.urlopen`` inline inside the nested ``worker_ollama``. It no
   longer does.) Any *new* Ollama-streaming case must patch that name too —
   enabling the provider without patching it is the one way to make this lane
   dial out.

   ``tests/unit/test_direct_urlopen_call_sites.py`` pins the exact set of direct
   ``urlopen`` call sites so another one cannot appear unnoticed. Moving these
   behind ``ai/providers/_http.post_json`` is deferred work that no work item
   owns yet.

   This fixture on its own still only means "the AI routes return a sentinel".
   What now also holds the lane offline is a separate, unconditional fence:
   ``_no_real_egress`` below patches ``socket.socket.connect`` for every test in
   this lane, so a stub that silently stops matching production no longer buys a
   real HTTP request — it buys a failing test. Read its docstring for the four
   holes that fence does not cover.

The provider stub returns ``FAKE_ANSWER``, a string that appears nowhere else in
the codebase. Tests assert that *that exact string* comes back in the right
field of the response body. Asserting "the stub was called" would stay green
after a Phase 2 refactor dropped the field on the floor; asserting the sentinel
travelled from provider to ``answer`` would not.
"""

from __future__ import annotations

import functools
import json
import pickle
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, List, Tuple

import pytest
from fastapi.testclient import TestClient

# ``tests/unit/`` is on ``sys.path`` only when ``tests/unit`` is itself being
# collected. The lane command names both directories, so nothing here would ever
# notice -- but ``pytest tests/contract`` alone is a documented developer
# invocation, and without this line it dies at collection with
# ``ModuleNotFoundError: egress_guard``, taking the whole directory with it.
# ``tests/unit/test_egress_backstop_subprocess.py::test_the_contract_directory_still_collects_on_its_own``
# is the receipt for this one line.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))

import egress_guard  # noqa: E402  - must follow the sys.path line above

from reader3_app import search_service
from reader3_app.ai.books import BookUuidResolver
from reader3_app.ai.providers.types import ProviderResponse
from reader3_app.reader3 import Book, BookMetadata, ChapterContent, TOCEntry
from reader3_app.web import server

#: The seeded book. Ends in ``_data`` because ``_validate_book_id_path_safe``
#: rejects anything else with a 400 before it ever looks at the filesystem.
BOOK_ID = "sample_data"

#: Well-formed but absent — exercises "resource not found", not "malformed id".
MISSING_BOOK_ID = "no_such_book_data"

#: Parses as a UUID, resolves to nothing.
MISSING_UUID = "00000000-0000-4000-8000-000000000000"

#: Parses as a UUID, resolves to nothing (collections).
MISSING_COLLECTION_ID = "11111111-1111-4111-8111-111111111111"

#: A word that occurs in chapter 0 and nowhere else, so a keyword search hit is
#: evidence the chapter text was really indexed rather than a lucky substring.
UNIQUE_TERM = "Ozymandias"

#: Returned by the stubbed provider. Asserted verbatim in AI response bodies.
FAKE_ANSWER = "SENTINEL-ANSWER-c0ffee"

FAKE_MODEL = "sentinel-model-v1"

CHAPTER_0_TITLE = "Chapter One"
CHAPTER_1_TITLE = "Chapter Two"

#: Rendered into the library and reader templates; asserted in the HTML.
BOOK_TITLE = "The Sentinel Book"
BOOK_AUTHOR = "Percy Sentinel"


def build_book() -> Book:
    """A two-chapter book, small enough to pickle fast and distinctive enough to assert on."""
    return Book(
        metadata=BookMetadata(
            title=BOOK_TITLE,
            language="en",
            authors=[BOOK_AUTHOR],
            description="A fixture book.",
        ),
        spine=[
            ChapterContent(
                id="item_0",
                href="chap0.html",
                title=CHAPTER_0_TITLE,
                content=f"<p>I met a traveller who spoke of {UNIQUE_TERM}, king of kings.</p>",
                text=f"I met a traveller who spoke of {UNIQUE_TERM}, king of kings.",
                order=0,
            ),
            ChapterContent(
                id="item_1",
                href="chap1.html",
                title=CHAPTER_1_TITLE,
                content="<p>Round the decay of that colossal wreck.</p>",
                text="Round the decay of that colossal wreck.",
                order=1,
            ),
        ],
        toc=[
            TOCEntry(title=CHAPTER_0_TITLE, href="chap0.html", file_href="chap0.html", anchor=""),
            TOCEntry(title=CHAPTER_1_TITLE, href="chap1.html", file_href="chap1.html", anchor=""),
        ],
        images={},
        source_file="sample.epub",
        processed_at="2026-01-01T00:00:00+00:00",
    )


def _seed_book_dir(books_dir: Path) -> Path:
    out = books_dir / BOOK_ID
    (out / "images").mkdir(parents=True)
    with open(out / "book.pkl", "wb") as f:
        pickle.dump(build_book(), f)
    # serve_epub only checks existence; the bytes are never parsed server-side.
    (out / "book.epub").write_bytes(b"PK\x03\x04 not-a-real-zip")
    (out / "images" / "cover.jpg").write_bytes(b"\xff\xd8\xff\xe0 jpeg-ish")
    return out


def _seed_settings(config_dir: Path) -> Path:
    """Enable anthropic with a fake key so ``_get_provider_runtime`` reaches the stub.

    Without a key that call raises 503 before ``_call_provider``, and every AI
    contract case would collapse into the same "provider not configured" test.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "ai_settings.json"
    path.write_text(
        json.dumps(
            {
                "default_provider": "anthropic",
                "providers": {
                    "anthropic": {
                        "enabled": True,
                        "model_name": "claude-fixture",
                        "api_key": "sk-fixture-not-a-real-key",
                        "timeout_s": 5,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return path


@dataclass
class World:
    """Handles onto the isolated filesystem a test may need to inspect or seed."""

    client: TestClient
    books_dir: Path
    project_root: Path
    settings_path: Path
    book_uuid: str

    @property
    def book_dir(self) -> Path:
        return self.books_dir / BOOK_ID

    @property
    def collections_path(self) -> Path:
        return self.project_root / "config" / "collections.json"


def _clear_caches() -> None:
    server.load_book_cached.cache_clear()
    search_service.load_book_cached.cache_clear()
    server._stats_cache.clear()


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    """The app, rehomed onto a throwaway project root with one book in it.

    The client is entered as a context manager, and that is not a stylistic
    choice. ``TestClient`` runs the ASGI lifespan only on ``__enter__``; a bare
    ``TestClient(app=...)`` serves requests perfectly well while never executing
    ``server._startup_scan_books``. This lane used to be built that way, so the
    startup hook could have been deleted outright with every contract test still
    green. Entering the client also runs *shutdown*, so this is a behaviour
    change for the whole lane, not a formality.

    See ``test_startup_lifespan.py`` for the observation that tells the startup
    scan apart from lazy ``book_uuid_for_folder`` resolution — this fixture
    cannot, because it resolves ``BOOK_ID`` itself a line below.
    """
    project_root = tmp_path / "project"
    books_dir = project_root / "books"
    books_dir.mkdir(parents=True)
    _seed_book_dir(books_dir)
    settings_path = _seed_settings(project_root / "config")

    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))
    # The resolver captured the old BOOKS_DIR in __init__, so patching the
    # constant alone would leave it pointing at the real library.
    monkeypatch.setattr(server, "book_uuid_resolver", BookUuidResolver(str(books_dir)))

    def _load(path: str = str(settings_path)) -> dict[str, Any]:
        from reader3_app.ai import config as ai_config

        return ai_config.load_ai_settings(str(settings_path))

    def _save(settings: dict[str, Any], path: str = str(settings_path)) -> None:
        from reader3_app.ai import config as ai_config

        ai_config.save_ai_settings(settings, str(settings_path))

    monkeypatch.setattr(server, "load_ai_settings", _load)
    monkeypatch.setattr(server, "save_ai_settings", _save)
    # Seam pairing (018 WI-3): the settings lock and revision must describe the
    # same file load/save use, or a request locks and hashes the real config/.
    from reader3_app.ai import config as _ai_config

    monkeypatch.setattr(
        server,
        "ai_settings_transaction",
        functools.partial(_ai_config.ai_settings_transaction, path=str(settings_path)),
    )

    def _stub_call_provider(provider_name: str, **kwargs: Any) -> ProviderResponse:
        return ProviderResponse(text=FAKE_ANSWER, model=FAKE_MODEL, finish_reason="stop", token_count=7)

    def _stub_http_get_json(url: str, *, timeout_s: int = 3) -> dict[str, Any]:
        raise ConnectionRefusedError(f"network is off in tests: {url}")

    monkeypatch.setattr(server, "_call_provider", _stub_call_provider)
    monkeypatch.setattr(server, "_http_get_json", _stub_http_get_json)

    _clear_caches()
    with TestClient(app=server.app, base_url="http://127.0.0.1") as client:
        book_uuid = server.book_uuid_resolver.book_uuid_for_folder(BOOK_ID)
        try:
            yield World(
                client=client,
                books_dir=books_dir,
                project_root=project_root,
                settings_path=settings_path,
                book_uuid=book_uuid,
            )
        finally:
            # Leaving a tmp_path book in the LRU would let the *next* test read a
            # book.pkl from a directory that no longer exists.
            _clear_caches()


@pytest.fixture
def client(world: World) -> TestClient:
    return world.client


# --------------------------------------------------------------------------
# The lane-wide egress backstop. Body shared with tests/unit; see egress_guard.
# --------------------------------------------------------------------------


@pytest.fixture
def egress_violations(request: pytest.FixtureRequest) -> List[Tuple[str, str, str]]:
    """This test's ledger of attempted real TCP connections."""
    return egress_guard.egress_violations(request)


@pytest.fixture(autouse=True)
def _no_real_egress(request: pytest.FixtureRequest, egress_violations):
    """No test in this lane opens a real TCP connection.

    Registered a second time here, rather than once for both directories,
    because the only shared parent is ``tests/conftest.py`` -- a frozen
    ``suite_hash`` path. The gate *body* is not duplicated: it lives in
    ``tests/unit/egress_guard.py``.

    ``yield from`` is load-bearing: it is what resumes the generator so the
    gate's teardown assertion actually runs. Egress from a ``run_in_threadpool``
    worker is swallowed by ``server.py``'s own ``except Exception`` fallback, so
    that recorded ledger is the only surviving evidence.

    Holes (same four as the unit lane): import/collection time, higher-scoped
    fixture setup, child interpreters, and ``connect_ex`` / UDP ``sendto`` /
    ``getaddrinfo``.
    """
    yield from egress_guard.no_real_egress(request, egress_violations)
