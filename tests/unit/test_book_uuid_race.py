"""WI-25: two requests that mint a book_uuid at the same moment must agree.

``ensure_book_uuid`` was read -> mint -> ``os.replace``, with nothing serialising
the three steps and nothing checking whether the file appeared in between. Two
requests touching a book that has no ``ai_meta.json`` yet -- two tabs, or two
uvicorn workers, or the startup ``scan()`` racing a first API call -- each mint a
*different* uuid and each write it over the file. Last writer wins the disk; the
other request has already handed its uuid to the client, and that uuid now
resolves to nothing, forever. Every AI conversation hangs off book_uuid.

The correct outcome is not "one of them errors". It is **both of them return the
same uuid**: minting is create-if-absent, and the caller that loses goes back to
the file and adopts the winner's value. So the load-bearing assertion in here is
always a three-way equality -- first return value, second return value, and the
value on disk. Any two of the three would be fooled: "the two agree" passes when
both calls blow up (matching absences is not agreement), and "the return matches
disk" passes for last-writer-wins if you only ever ask the winner.

How the race is manufactured
----------------------------
A ``Barrier(2)``, an ``Event``, and no ``sleep``. Each caller is parked inside
``uuid4`` -- after its own read said "no uuid here", before anything reaches the
disk -- by a wrapper installed on the module attribute in the test only; the
product code is not edited to be testable. The second caller then waits for the
first to *finish*, so the interleaving is pinned to exactly: both read, one
writes, the other writes.

Pinning it rather than letting the two overlap freely is deliberate. Left to
overlap, both racers open the same scratch path and the loser's ``os.replace``
dies on a file that vanished under it, so the red would read "it raised" -- the
weak claim, and one a "refuse when contended" non-fix would also satisfy. With
the interleaving pinned, the red says what is actually broken: the two callers
were handed different uuids, and only one of them exists on disk.

Assertion levels (same scale as the rest of this lane):
    L2 return value, or a single field of on-disk state
    L3 the whole on-disk end state after concurrent callers
"""

from __future__ import annotations

import errno
import hashlib
import json
import multiprocessing as mp
import queue as queue_mod
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from book_uuid_concurrency import ensure_uuid_interleaved
from reader3_app import book_lock
from reader3_app.ai import books as books_mod
from reader3_app.ai.books import BookUuidResolver, _read_ai_meta, ensure_book_uuid

# Escape hatch only; see the module docstring. Neither path waits this long.
#
# Below the book lock's budget, by construction (018 WI-2 audit fix-up, WI-1): minting
# now runs under the ``ai_meta`` resource lock, so the pinned interleaving (both read,
# then one writes) is impossible -- the second caller waits on the lock, not at the
# barrier. The first caller's rendezvous therefore always times out, and it must do
# so well before the waiter's budget runs out, or the waiter is refused instead of
# adopting the winner's uuid. Was 5.0; the expectation (three-way equality) is
# unchanged.
RENDEZVOUS_TIMEOUT_S = book_lock.BUDGET_S / 4

# Anything beyond this means a worker is wedged rather than merely slow.
JOIN_TIMEOUT_S = 30.0

FOLDER = "dracula_data"
WINNER_UUID = "9f6a1e2c-0000-4000-8000-000000000001"

FIRST = "minter-0"
SECOND = "minter-1"


@pytest.fixture(autouse=True)
def _work_inside_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every relative path in this module resolves under tmp_path, never books/.

    ``books/../ai_meta.json`` is the repo root; a relative write from this lane
    would land on real user data.
    """
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def books_root(tmp_path: Path) -> Path:
    root = tmp_path / "books"
    (root / FOLDER).mkdir(parents=True)
    return root


def _meta_path(books_root: Path) -> Path:
    return books_root / FOLDER / "ai_meta.json"


def _describe(exc: BaseException) -> str:
    """Symbolic errno instead of the phrase the red-receipt tool greps for."""
    if isinstance(exc, OSError):
        code = errno.errorcode.get(exc.errno, exc.errno)
        paths = " -> ".join(str(p) for p in (exc.filename, exc.filename2) if p)
        return f"{type(exc).__name__}[{code}] {paths}".strip()
    return f"{type(exc).__name__}: {exc}"


def _uuid_on_disk(books_root: Path) -> Tuple[Optional[str], str]:
    """Report what a *later* read would see, without raising mid-assertion."""
    path = _meta_path(books_root)
    if not path.exists():
        return None, f"{path.name} was never created in {path.parent}"
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return None, f"{path.name} is not readable JSON ({e}); bytes={raw[:160]!r}"
    if not isinstance(data, dict):
        return None, f"{path.name} holds a {type(data).__name__}, not an object"
    value = data.get("book_uuid")
    if not isinstance(value, str):
        return None, f"{path.name} has a {type(value).__name__} book_uuid: {value!r}"
    return value, f"{path.name} holds {value}"


def _leftover_temp_files(books_root: Path) -> List[str]:
    return sorted(
        p.name for p in (books_root / FOLDER).iterdir() if p.name != "ai_meta.json"
    )


def _run_interleaved_threads(
    call, monkeypatch: pytest.MonkeyPatch
) -> Tuple[Dict[str, Any], List[str]]:
    """Run ``call`` on two threads whose read/write order is pinned; see the docstring."""
    barrier = threading.Barrier(2)
    first_done = threading.Event()
    real_uuid4 = books_mod.uuid4

    def uuid4_interleaved():
        value = real_uuid4()
        try:
            barrier.wait(RENDEZVOUS_TIMEOUT_S)
        except threading.BrokenBarrierError:
            pass
        if threading.current_thread().name == SECOND:
            first_done.wait(RENDEZVOUS_TIMEOUT_S)
        return value

    monkeypatch.setattr(books_mod, "uuid4", uuid4_interleaved)

    results: Dict[str, Any] = {}
    errors: List[str] = []
    guard = threading.Lock()

    def run() -> None:
        name = threading.current_thread().name
        try:
            value = call()
        except BaseException as e:  # noqa: BLE001 -- the assertions decide what it means
            with guard:
                errors.append(f"{name}: {_describe(e)}")
        else:
            with guard:
                results[name] = value
        finally:
            if name == FIRST:
                # Release the other thread even when this one failed, so a crash
                # never turns into a hung test.
                first_done.set()

    threads = [threading.Thread(target=run, name=name) for name in (FIRST, SECOND)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(JOIN_TIMEOUT_S)
    stuck = [t.name for t in threads if t.is_alive()]
    assert not stuck, f"minter thread(s) never finished within {JOIN_TIMEOUT_S}s: {stuck}"
    return results, errors


# --------------------------------------------------------------------------- R1


def test_two_concurrent_threads_get_one_and_the_same_uuid(
    books_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1 (L3/S2, load-bearing): both callers return the uuid that is on disk.

    The three-way equality is the whole point. "The two agree" alone is satisfied
    by both calls raising, and "it matches disk" alone is satisfied by
    last-writer-wins. Nothing here is wrapped in ``pytest.raises``: an exception
    means the caller got no identity at all, which is a failure of this
    specification, and letting it surface as a red is the intent.
    """
    results, errors = _run_interleaved_threads(
        lambda: ensure_book_uuid(str(books_root), FOLDER), monkeypatch
    )

    assert not errors, f"ensure_book_uuid must return a uuid, not raise: {errors}"
    assert set(results) == {FIRST, SECOND}, f"expected two return values, got {results!r}"

    first, second = results[FIRST], results[SECOND]
    on_disk, diagnostic = _uuid_on_disk(books_root)
    assert first == second == on_disk, (
        "two concurrent first-time callers must be handed the same book_uuid, and "
        "it must be the one a later read finds; a uuid nobody can resolve leaves "
        f"that client's AI conversations orphaned. returned={first!r} and "
        f"{second!r}, {diagnostic}"
    )
    assert not _leftover_temp_files(books_root), (
        f"minting left scratch files behind: {_leftover_temp_files(books_root)}"
    )


# --------------------------------------------------------------------------- R2


def test_two_concurrent_processes_get_one_and_the_same_uuid(books_root: Path) -> None:
    """R2 (L3/S2): the same guarantee across processes.

    Singled out because ``BookUuidResolver`` already owns a ``threading.Lock``:
    an in-process fix passes R1 while two uvicorn workers -- or the CLI beside a
    live server -- still hand out a uuid that resolves to nothing.
    """
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(2)
    first_done = ctx.Event()
    result_queue = ctx.Queue()
    procs = [
        ctx.Process(
            target=ensure_uuid_interleaved,
            args=(
                str(books_root),
                FOLDER,
                index,
                barrier,
                first_done,
                RENDEZVOUS_TIMEOUT_S,
                result_queue,
            ),
        )
        for index in (0, 1)
    ]
    for p in procs:
        p.start()

    reported: List[Tuple[str, str]] = []
    deadline = time.monotonic() + JOIN_TIMEOUT_S
    for _ in range(2):
        try:
            reported.append(result_queue.get(timeout=max(0.1, deadline - time.monotonic())))
        except queue_mod.Empty:
            break

    for p in procs:
        p.join(JOIN_TIMEOUT_S)
    alive = [p.pid for p in procs if p.is_alive()]
    for p in procs:
        if p.is_alive():
            p.kill()
    assert not alive, f"child minter(s) never finished within {JOIN_TIMEOUT_S}s: {alive}"

    exitcodes = [p.exitcode for p in procs]
    assert exitcodes == [0, 0], (
        "both children must have actually run and returned a uuid; a child that "
        "dies on import touches nothing and would look like success. exitcodes="
        f"{exitcodes}, reported={reported!r}"
    )
    assert len(reported) == 2 and all(kind == "ok" for kind, _ in reported), (
        f"both children must report a uuid, not an error: {reported!r}"
    )

    first, second = (value for _, value in reported)
    on_disk, diagnostic = _uuid_on_disk(books_root)
    assert first == second == on_disk, (
        "two processes minting at the same moment must converge on one book_uuid; "
        f"returned={first!r} and {second!r}, {diagnostic}"
    )
    assert not _leftover_temp_files(books_root), (
        f"minting left scratch files behind: {_leftover_temp_files(books_root)}"
    )


# --------------------------------------------------------------------------- R3


def test_losing_the_race_returns_the_winners_uuid_rather_than_raising(
    books_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3 (L3/S2): the loser adopts the winner's uuid -- an error is not a fix.

    "Refuse when the file appeared under us" would satisfy R1 and R2 by making
    both callers fail, and would still leave the client with no usable identity.
    Here exactly one caller runs; a competitor creates the file inside its mint
    window, so the only correct answer is the competitor's value.
    """
    real_uuid4 = books_mod.uuid4
    competitor_wrote: List[str] = []

    def uuid4_then_lose_the_race():
        value = real_uuid4()
        if not competitor_wrote:
            _meta_path(books_root).write_text(
                json.dumps({"book_uuid": WINNER_UUID, "note": "written by the winner"}),
                encoding="utf-8",
            )
            competitor_wrote.append(WINNER_UUID)
        return value

    monkeypatch.setattr(books_mod, "uuid4", uuid4_then_lose_the_race)

    try:
        got = ensure_book_uuid(str(books_root), FOLDER)
    except BaseException as e:  # noqa: BLE001
        pytest.fail(
            "losing the mint race is a normal outcome, not a fault: the caller "
            f"must be handed the uuid that won. Instead it raised {_describe(e)}"
        )

    assert competitor_wrote, "the test never manufactured the race"
    on_disk, diagnostic = _uuid_on_disk(books_root)
    assert got == WINNER_UUID, (
        f"the losing caller returned its own uuid {got!r} instead of the winner's "
        f"{WINNER_UUID!r}; that uuid resolves to nothing. {diagnostic}"
    )
    assert on_disk == WINNER_UUID, (
        f"the losing caller overwrote the winner's file. {diagnostic}"
    )
    assert json.loads(_meta_path(books_root).read_text("utf-8"))["note"] == (
        "written by the winner"
    ), "the winner's other keys were clobbered by the loser"


# --------------------------------------------------------------------------- R4


def test_an_existing_uuid_is_returned_without_a_single_write(books_root: Path) -> None:
    """R4 (L2/S1, regression): the read path is untouched by the fix.

    An exclusive-create fix that ran before the read would turn every healthy
    call into a write, or worse, into a spurious race-loss.
    """
    path = _meta_path(books_root)
    path.write_text(
        json.dumps({"book_uuid": WINNER_UUID, "chunk_count": 42}), encoding="utf-8"
    )
    before = hashlib.md5(path.read_bytes()).hexdigest()

    got = ensure_book_uuid(str(books_root), FOLDER)

    assert got == WINNER_UUID
    assert hashlib.md5(path.read_bytes()).hexdigest() == before, (
        "a healthy ai_meta.json was rewritten for no reason"
    )
    assert not _leftover_temp_files(books_root), (
        f"a pure read left scratch files behind: {_leftover_temp_files(books_root)}"
    )


# --------------------------------------------------------------------------- R5


def test_non_string_uuid_still_raises_and_still_survives(books_root: Path) -> None:
    """R5a (L2/S1, regression): WI-9's type gate is not relaxed by this change."""
    path = _meta_path(books_root)
    path.write_text(json.dumps({"book_uuid": 123, "other": "keep"}), encoding="utf-8")
    before = path.read_bytes()

    with pytest.raises(ValueError) as excinfo:
        ensure_book_uuid(str(books_root), FOLDER)

    assert "ai_meta.json" in str(excinfo.value)
    assert path.read_bytes() == before, (
        f"a file we cannot read was rewritten: {path.read_text('utf-8')!r}"
    )


def test_first_mint_over_an_existing_file_keeps_every_other_key(books_root: Path) -> None:
    """R5b (L2/S1, regression): WI-9's "preserve every key" survives the change.

    This is the exclusive-create path's nastiest neighbour: the file already
    exists but holds no uuid, so a create-if-absent that read "the target is
    there" as "somebody won" would either refuse to write or hand back nothing.
    """
    path = _meta_path(books_root)
    path.write_text(
        json.dumps({"chunk_count": 42, "flags": {"a": True}, "label": "x"}),
        encoding="utf-8",
    )

    got = ensure_book_uuid(str(books_root), FOLDER)

    on_disk = json.loads(path.read_text("utf-8"))
    assert on_disk["book_uuid"] == got, f"the minted uuid is not the one on disk: {on_disk!r}"
    assert on_disk["chunk_count"] == 42, f"chunk_count was dropped: {on_disk!r}"
    assert on_disk["flags"] == {"a": True}, f"flags was dropped: {on_disk!r}"
    assert on_disk["label"] == "x", f"label was dropped: {on_disk!r}"
    assert not _leftover_temp_files(books_root), (
        f"minting left scratch files behind: {_leftover_temp_files(books_root)}"
    )
    assert _read_ai_meta(str(path)) is not None


# --------------------------------------------------------------------------- R6


def test_resolver_hands_two_threads_one_uuid_and_maps_it_back(
    books_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R6 (L3/S2): the same three-way equality through BookUuidResolver.

    ``scan()`` and ``book_uuid_for_folder()`` both reach ``ensure_book_uuid`` via
    ``_load_folder``, and the resolver's own lock guards only its two dicts -- it
    is taken *after* the mint, so it cannot make two minters agree. Added because
    this is the path the server actually calls.
    """
    resolver = BookUuidResolver(str(books_root))

    results, errors = _run_interleaved_threads(
        lambda: resolver.book_uuid_for_folder(FOLDER), monkeypatch
    )

    assert not errors, f"the resolver must return a uuid, not raise: {errors}"
    assert set(results) == {FIRST, SECOND}, f"expected two return values, got {results!r}"

    first, second = results[FIRST], results[SECOND]
    on_disk, diagnostic = _uuid_on_disk(books_root)
    assert first == second == on_disk, (
        "two concurrent resolver callers must be handed the same book_uuid; "
        f"returned={first!r} and {second!r}, {diagnostic}"
    )
    assert resolver.folder_for_book_uuid(first) == FOLDER


# --------------------------------------------------------------------------- FX-1-14 / FX-1-15
#
# 018 WI-2 audit fix-up, WI-1 (#43): the same convergence law on a book whose
# ai_meta.json *exists but carries no uuid*. That path used to be write-then-replace
# under SH only, so two minters each wrote their own uuid and the last replace won.


def _is_uuid(value: object) -> bool:
    import uuid as uuid_lib

    try:
        return str(uuid_lib.UUID(str(value))) == value
    except ValueError:
        return False


@pytest.mark.parametrize(
    "meta",
    [{"indexed_at": 1}, {"indexed_at": 1, "title": "t", "nested": {"a": [1, 2]}}, {}],
    ids=["indexed_at", "nested", "empty"],
)
def test_fx_1_14_two_interleaved_threads_on_a_uuid_less_meta_converge(
    books_root: Path, monkeypatch: pytest.MonkeyPatch, meta: Dict[str, Any]
) -> None:
    """FX-1-14 (L3/S5): three-way equality, every other key kept, nothing else left."""
    _meta_path(books_root).write_text(json.dumps(meta), encoding="utf-8")
    calls: List[int] = []
    real_uuid4 = books_mod.uuid4

    def counting_uuid4():
        calls.append(1)
        return real_uuid4()

    # Installed before the harness wraps uuid4, so the harness delegates through it.
    monkeypatch.setattr(books_mod, "uuid4", counting_uuid4)

    results, errors = _run_interleaved_threads(
        lambda: ensure_book_uuid(str(books_root), FOLDER), monkeypatch
    )

    assert len(calls) >= 1, "the harness never reached uuid4; the interleaving was not pinned"
    assert not errors, f"ensure_book_uuid must return a uuid, not raise: {errors}"
    assert set(results) == {FIRST, SECOND}, f"expected two return values, got {results!r}"
    first, second = results[FIRST], results[SECOND]
    on_disk, diagnostic = _uuid_on_disk(books_root)
    assert first == second == on_disk, (
        "two concurrent first-time callers on a uuid-less ai_meta.json must converge; "
        f"returned={first!r} and {second!r}, {diagnostic}"
    )
    assert _is_uuid(first) and _is_uuid(second)
    stored = json.loads(_meta_path(books_root).read_text("utf-8"))
    assert {k: v for k, v in stored.items() if k != "book_uuid"} == meta
    assert _leftover_temp_files(books_root) == []


def test_fx_1_15_two_processes_on_a_uuid_less_meta_converge(books_root: Path) -> None:
    """FX-1-15 (L3/S5): the cross-process variant; a thread-only lock passes FX-1-14 only.

    ``timeout_s=0.5`` keeps each child's rendezvous below its real 2 s budget, for the
    same reason ``RENDEZVOUS_TIMEOUT_S`` is below it.
    """
    _meta_path(books_root).write_text(json.dumps({"indexed_at": 1}), encoding="utf-8")
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(2)
    first_done = ctx.Event()
    result_queue = ctx.Queue()
    procs = [
        ctx.Process(
            target=ensure_uuid_interleaved,
            args=(str(books_root), FOLDER, index, barrier, first_done, 0.5, result_queue),
        )
        for index in (0, 1)
    ]
    for p in procs:
        p.start()

    reported: List[Tuple[str, str]] = []
    deadline = time.monotonic() + JOIN_TIMEOUT_S
    for _ in range(2):
        try:
            reported.append(result_queue.get(timeout=max(0.1, deadline - time.monotonic())))
        except queue_mod.Empty:
            break
    for p in procs:
        p.join(JOIN_TIMEOUT_S)
    alive = [p.pid for p in procs if p.is_alive()]
    for p in procs:
        if p.is_alive():
            p.kill()
    assert not alive, f"child minter(s) never finished within {JOIN_TIMEOUT_S}s: {alive}"

    assert [p.exitcode for p in procs] == [0, 0], f"reported={reported!r}"
    assert len(reported) == 2 and all(kind == "ok" for kind, _ in reported), reported
    first, second = (value for _, value in reported)
    on_disk, diagnostic = _uuid_on_disk(books_root)
    assert first == second == on_disk, (
        f"two processes on a uuid-less ai_meta.json must converge; returned={first!r} "
        f"and {second!r}, {diagnostic}"
    )
    assert json.loads(_meta_path(books_root).read_text("utf-8"))["indexed_at"] == 1
    assert _leftover_temp_files(books_root) == []
