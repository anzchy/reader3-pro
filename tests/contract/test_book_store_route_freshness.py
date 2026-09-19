"""The merged loader seen from the routes (011 §4, WI-3 — W3-C9 / W3-C10 / W3-C12).

Why these three sit in the contract lane and not next to their unit siblings:
each of them would still pass, in a unit-lane form, if `read_chapter`,
`library_view` or `api_search_book` had grown a second cache of its own over
the loader. The user-visible half of §4.2 — and conservation at a *real*
production call site — is only real one lane up, with the real router tree,
the real templates and the real filesystem.

`tests/unit/conftest.py`'s `count_unpickles` fixture is not visible from here,
and `tests/conftest.py` is a frozen `suite_hash` path. W3-C12 therefore defines
the same five-line counting passthrough at module scope below. The duplication
is deliberate: it touches no frozen path and adds no shared fixture file whose
hash someone later has to reason about.

Assertion rungs (L1-L4) and spec levels (S1-S6) follow
`.claude/tdd-guardian/tests-20260907T073506Z.md` §0.1-§0.2.
"""

from __future__ import annotations

import os
import pickle
from pathlib import Path

import pytest

from reader3_app import safe_pickle
from reader3_app.web import server
from conftest import BOOK_ID, BOOK_TITLE, UNIQUE_TERM, World, build_book

#: An explicit constant, never the clock (matrix §0.4 rule 1): a `(mtime_ns,
#: size)` key cannot see two writes inside one filesystem tick.
BASE_NS = 1_700_000_000_000_000_000

REPUBLISHED_TITLE = "The Republished Book"
LATE_TITLE = "Late Arrival"


def _republish(book_dir: Path, title: str, *, mtime_ns: int) -> None:
    """Pickle a book with `title` over `{book_dir}/book.pkl` at a forced mtime.

    Reads the stat back and asserts the forced value landed, so a filesystem
    that truncates nanoseconds fails loudly instead of letting an invalidation
    claim pass vacuously (§0.4 rule 2).
    """
    book = build_book()
    book.metadata.title = title
    path = book_dir / "book.pkl"
    with open(path, "wb") as f:
        pickle.dump(book, f)
    os.utime(path, ns=(mtime_ns, mtime_ns))
    st = os.stat(path)
    assert st.st_mtime_ns == mtime_ns, (
        f"the filesystem did not keep the forced mtime: asked {mtime_ns}, read {st.st_mtime_ns}"
    )


class _UnpickleCounter:
    """A counting passthrough over the **real** `safe_pickle.safe_load`.

    A spy, not a mock: the allow-listed unpickle still runs and its result is
    returned unchanged. Patched at `safe_pickle.safe_load` rather than at
    `book_store.load_book_file` because `load_book_file` resolves `safe_load`
    as a module global at call time, so this seam sees every read path at once
    — which is the same reason `bench.py:529` chose it (§0.5).
    """

    def __init__(self) -> None:
        self.count = 0

    def install(self, monkeypatch: pytest.MonkeyPatch) -> "_UnpickleCounter":
        real = safe_pickle.safe_load

        def counting(f):
            self.count += 1
            return real(f)

        monkeypatch.setattr(safe_pickle, "safe_load", counting)
        return self


def test_the_reader_route_serves_a_rewritten_book_without_a_restart(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L3 / S2 (W3-C9) — republish is visible through the real route, and only then.

    `baseline_1b` cannot cover this: `tests/e2e/conftest.py`'s session fixture
    publishes all four books before the server starts and never touches
    `book.pkl` again. This case and W3-C3 are the whole of the evidence for
    §4.2's sub-item (b).

    The third request is the negative control. Without it, an implementation
    that re-reads the disk on every request passes the freshness leg and the
    cache has quietly stopped being a cache; the `misses` delta of 0 is what
    tells the two apart.
    """
    first = world.client.get(f"/read/{BOOK_ID}/0")
    assert first.status_code == 200
    assert BOOK_TITLE in first.text

    _republish(world.book_dir, REPUBLISHED_TITLE, mtime_ns=BASE_NS)

    second = world.client.get(f"/read/{BOOK_ID}/0")
    assert second.status_code == 200
    assert REPUBLISHED_TITLE in second.text, (
        "the reader route is still serving the pre-republish book: the loader "
        "cache cannot see that book.pkl changed"
    )
    assert BOOK_TITLE not in second.text

    before = server.load_book_cached.cache_info().misses
    third = world.client.get(f"/read/{BOOK_ID}/0")
    after = server.load_book_cached.cache_info().misses

    assert third.text == second.text
    assert after - before == 0, (
        f"an unchanged book.pkl cost {after - before} extra misses — the loader "
        "is re-reading the disk on every request, not caching it"
    )


def test_the_homepage_lists_a_book_published_between_two_requests(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L3 / S1 (W3-C10) — D2 at the route: a memoized `None` would hide the new book.

    `library_view` re-`listdir`s on every request, so the *only* thing that can
    suppress the second book is a negative memoized inside the loader — which
    is exactly what D2 chose not to keep. Today's code fails the second half.

    The 200 on the first request is not a formality: it is this file's
    real-path anchor for W3-C5x. `library_view` calls the loader once per
    `*_data` directory with no per-row guard, so a directory whose `book.pkl`
    is absent must degrade to "not listed", never to a 500.
    """
    pending = world.books_dir / "pending_data"
    (pending / "images").mkdir(parents=True)

    first = world.client.get("/")
    assert first.status_code == 200
    assert BOOK_TITLE in first.text
    assert LATE_TITLE not in first.text

    _republish(pending, LATE_TITLE, mtime_ns=BASE_NS)

    second = world.client.get("/")
    assert second.status_code == 200
    assert BOOK_TITLE in second.text
    assert LATE_TITLE in second.text, (
        "the book published between the two requests is still invisible: the "
        "failed lookup was memoized and only a restart would clear it"
    )


@pytest.mark.parametrize("order", ["read_first", "search_first"])
def test_reading_a_chapter_and_searching_it_cost_one_unpickle(
    world: World, monkeypatch: pytest.MonkeyPatch, order: str
) -> None:
    """L3 / S2 (W3-C12) — conservation asserted across two real production call sites.

    The unit cases call the two loader names directly. `search_service.py:451`
    (`search_book`) is reached by no unit case, so nothing else in the suite
    proves the search route forwards the *same* `books_dir` string the reader
    route does. One route passing `BOOKS_DIR` and another passing
    `os.path.abspath(BOOKS_DIR)` would double every unpickle for a user who
    searches inside the book they are reading, and no unit-lane case can see it.

    The search result is inspected, not just counted. Without that, a 400 from
    a rejected query, an empty result set, or a route that never reaches
    `search_book` would satisfy `count == 1` **vacuously** — the counting law's
    cheapest false green.
    """
    counter = _UnpickleCounter().install(monkeypatch)
    server.load_book_cached.cache_clear()

    def do_read():
        resp = world.client.get(f"/read/{BOOK_ID}/0")
        assert resp.status_code == 200
        assert BOOK_TITLE in resp.text
        return resp

    def do_search():
        resp = world.client.get(f"/api/search/{BOOK_ID}?q={UNIQUE_TERM}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_matches"] >= 1, f"the search found nothing: {body}"
        hit = body["results"][0]
        context = f"{hit['context_before']}{hit['match_text']}{hit['context_after']}"
        assert UNIQUE_TERM in context, f"the hit does not carry the term: {hit}"
        return resp

    if order == "read_first":
        do_read()
        do_search()
    else:
        do_search()
        do_read()

    assert counter.count == 1, (
        f"reading a chapter and searching the same book cost {counter.count} "
        "unpickles; 2 is one cache per module, which is the defect §4 deletes"
    )
    assert server.load_book_cached.cache_info().misses == 1
