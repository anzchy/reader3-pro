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
3. ``server._call_provider`` and ``server._http_get_json`` — the only two places
   the process reaches the network. Both are stubbed unconditionally so that no
   contract test can bill an API key or hang on a DNS timeout.

The provider stub returns ``FAKE_ANSWER``, a string that appears nowhere else in
the codebase. Tests assert that *that exact string* comes back in the right
field of the response body. Asserting "the stub was called" would stay green
after a Phase 2 refactor dropped the field on the floor; asserting the sentinel
travelled from provider to ``answer`` would not.
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

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
    """The app, rehomed onto a throwaway project root with one book in it."""
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

    def _stub_call_provider(provider_name: str, **kwargs: Any) -> ProviderResponse:
        return ProviderResponse(text=FAKE_ANSWER, model=FAKE_MODEL, finish_reason="stop", token_count=7)

    def _stub_http_get_json(url: str, *, timeout_s: int = 3) -> dict[str, Any]:
        raise ConnectionRefusedError(f"network is off in tests: {url}")

    monkeypatch.setattr(server, "_call_provider", _stub_call_provider)
    monkeypatch.setattr(server, "_http_get_json", _stub_http_get_json)

    _clear_caches()
    client = TestClient(app=server.app)
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
