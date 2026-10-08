"""012 WI-1.6: the publisher, ``publish(book_dir, inputs, *, create=False) -> int`` (ADR-0016 steps 0-8).

Matrix: ``.claude/tdd-guardian/tests-20261008-152720.md`` section "WI-1.6" (P-01 .. P-25), plus the publish
half of G-12b, layout parity with the hand fixtures of ``test_book_format_classify.py`` /
``test_book_format_gc.py``, and a classify / GC case over a publish-built book.

Laws: user-data conservation (new root entries are a subset of ``{manifest.json, gen}``); strict monotonicity
(``g_new == max(canonical gen/* names at entry, before GC, U {readable manifest.generation}) + 1``); an atomic
outcome around the single commit ``os.replace``; determinism modulo ``generation``; retention of the previous
generation; and, on the repair path, no prior ``gen/*`` entry is deleted.

G-12b listing journal (pinned, see ``book_format_helpers.SyscallJournal``): ``os.listdir``, ``os.scandir``,
``os.walk``, ``glob.glob``, ``glob.iglob``, ``pathlib.Path.iterdir``, ``pathlib.Path.glob``,
``pathlib.Path.rglob``; every argument (path, ``PathLike``, or int fd via ``os.fstat``) resolves at call time to
``(st_dev, st_ino)``.
"""
from __future__ import annotations

import dataclasses
import errno
import hashlib
import json
import os
import random
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import assume
from hypothesis import strategies as st

import test_book_format_classify as kfix
import test_book_format_gc as gcfix
from book_format_helpers import (
    G_NEW,
    INJECTED_KINDS,
    LEGACY_FLAT,
    MANIFEST_PARSES,
    REPAIRABLE,
    USER_DATA,
    USER_ROOT_ENTRIES,
    HookRecorder,
    InjectedCrash,
    SyscallJournal,
    add_debris,
    add_orphan,
    add_parked,
    add_stale_tmp,
    assert_valid_with,
    book_path,
    build_repairable,
    canonical_gens,
    expected_gen_files,
    gen_file_set,
    install_hooks,
    make_inputs,
    root_entries,
    setup_scenario,
    snapshot,
    sub,
    without,
    write_file,
)
from reader3_app import book_format
from reader3_app.book_format import (
    CHAPTERS,
    EPUB,
    FORMAT_VERSION,
    GEN_DIR,
    IMAGES,
    MANIFEST,
    MANIFEST_TMP,
    MAX_GENERATION,
    PKL,
    PUBLISH_HOOKS,
    BookCorrupt,
    BookFormatError,
    ChapterRecord,
    CrossDeviceError,
    LegacyStagingRefused,
    PublishInputs,
    ReadbackError,
    classify,
    collect_garbage,
    manifest_from_bytes,
    publish,
    validate_stat,
)


def props(max_examples: int) -> Any:
    return settings(max_examples=max_examples, deadline=None,
                    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])


def run(book: Path, inputs: PublishInputs, rec: Optional[Callable[[str, str], None]] = None, **kw: Any) -> int:
    with pytest.MonkeyPatch.context() as mp:
        if rec is not None:
            install_hooks(mp, rec)
        return publish(book, inputs, **kw)


def user_snap(book: Path) -> dict[str, tuple[Any, ...]]:
    snap = snapshot(book)
    out: dict[str, tuple[Any, ...]] = {}
    for name in USER_ROOT_ENTRIES:
        out.update(sub(snap, name))
    return out


def legacy_snap(book: Path) -> dict[str, tuple[Any, ...]]:
    snap = snapshot(book)
    out: dict[str, tuple[Any, ...]] = {}
    for rel in LEGACY_FLAT:
        out.update(sub(snap, rel))
    out.update(sub(snap, IMAGES))
    return out


def gen_g(book: Path, g: int) -> Path:
    return book / GEN_DIR / str(g)


def only_p0_before(rec: HookRecorder) -> None:
    assert set(rec.calls) <= {("p0", "before")}, rec.calls


def books_dir(book: Path) -> Path:
    return book.parent


def no_new_gen_or_tmp(book: Path, g_new: int) -> None:
    assert not os.path.lexists(gen_g(book, g_new))
    assert not os.path.lexists(book / MANIFEST_TMP)


# =========================================================================== P-01 .. P-05p happy path

HAPPY = [("S0", 1), ("S0u", 1), ("S1", 3), ("S2", 2), ("S3", 1)]


@pytest.mark.parametrize("scenario,g_expected", HAPPY)
def test_p01_p05_happy_path_exact_layout(tmp_path: Path, scenario: str, g_expected: int) -> None:
    book = setup_scenario(scenario, tmp_path)
    before_root = root_entries(book)
    before_user = user_snap(book)
    before_legacy = legacy_snap(book) if scenario == "S3" else {}
    inputs = make_inputs("v2")

    g = publish(book, inputs, create=(scenario == "S0"))

    assert g == g_expected == G_NEW[scenario]
    m = assert_valid_with(book, "v2")
    assert m.generation == g
    assert m.format_version == FORMAT_VERSION
    assert m.metadata == inputs.metadata
    assert m.toc == inputs.toc
    assert (m.source_file, m.processed_at, m.book_version) == ("dracula.epub", "2026-10-08T00:00:00+00:00", "1")
    assert [c.id for c in m.chapters] == [c.id for c in inputs.chapters]
    assert m.images == {"images/cover.png": ("OEBPS/cover.png",), "images/图.jpg": ("OEBPS/图.jpg",)}
    files, dirs = gen_file_set(gen_g(book, g))
    assert files == expected_gen_files(inputs) == {CHAPTERS, EPUB, PKL, "images/cover.png", "images/图.jpg"}
    assert dirs == {IMAGES}
    assert {a.path for a in m.artifacts} == files
    assert (gen_g(book, g) / PKL).read_bytes() == b"PKL-v2"
    assert (gen_g(book, g) / EPUB).read_bytes() == b"EPUB-v2"
    assert (gen_g(book, g) / IMAGES / "cover.png").read_bytes() == b"PNG-v2"
    assert (gen_g(book, g) / IMAGES / "图.jpg").read_bytes() == b"JPG-v2"
    assert root_entries(book) == before_root | {MANIFEST, GEN_DIR}
    assert not os.path.lexists(book / MANIFEST_TMP)
    assert canonical_gens(book) == ({g - 1, g} if scenario in ("S1", "S2") else {g})
    assert user_snap(book) == before_user
    if scenario == "S3":
        assert legacy_snap(book) == before_legacy


@pytest.mark.parametrize("scenario", ["S0u", "S1"])
def test_p05p_publish_without_pkl(tmp_path: Path, scenario: str) -> None:
    book = setup_scenario(scenario, tmp_path)
    prev_pkl = snapshot(book).get(f"{GEN_DIR}/2/{PKL}") if scenario == "S1" else None
    inputs = make_inputs("v2", pkl=False)

    g = publish(book, inputs)

    assert classify(book, full=True) == "valid"
    assert not os.path.lexists(gen_g(book, g) / PKL)
    m = validate_stat(book)
    assert PKL not in {a.path for a in m.artifacts}
    files, _ = gen_file_set(gen_g(book, g))
    assert files == expected_gen_files(inputs) == {CHAPTERS, EPUB, "images/cover.png", "images/图.jpg"}
    if scenario == "S1":
        assert prev_pkl is not None
        assert snapshot(book).get(f"{GEN_DIR}/2/{PKL}") == prev_pkl


# =========================================================================== P-06 .. P-08


def test_p06_path_sources_equal_bytes_sources(tmp_path: Path) -> None:
    rng = random.Random(6)
    epub = bytes(rng.getrandbits(8) for _ in range(200 * 1024))
    base = make_inputs("v2")
    as_bytes = dataclasses.replace(base, epub=epub)
    src = tmp_path / "src"
    src.mkdir()
    (src / "book.epub").write_bytes(epub)
    (src / "book.pkl").write_bytes(b"PKL-v2")
    (src / "cover.png").write_bytes(b"PNG-v2")
    (src / "图.jpg").write_bytes(b"JPG-v2")
    src_before = snapshot(src)
    as_paths = dataclasses.replace(
        base, epub=src / "book.epub", pkl=str(src / "book.pkl"),
        images={"cover.png": src / "cover.png", "图.jpg": str(src / "图.jpg")},
    )
    a = tmp_path / "a" / "books" / "x_data"
    b = tmp_path / "b" / "books" / "x_data"
    a.parent.mkdir(parents=True)
    b.parent.mkdir(parents=True)

    assert publish(a, as_bytes, create=True) == 1
    assert publish(b, as_paths, create=True) == 1

    assert (a / MANIFEST).read_bytes() == (b / MANIFEST).read_bytes()
    fa, _ = gen_file_set(a / GEN_DIR / "1")
    fb, _ = gen_file_set(b / GEN_DIR / "1")
    assert fa == fb
    for rel in fa:
        assert (a / GEN_DIR / "1" / rel).read_bytes() == (b / GEN_DIR / "1" / rel).read_bytes()
    assert (b / GEN_DIR / "1" / EPUB).read_bytes() == epub
    assert snapshot(src) == src_before
    assert classify(b, full=True) == "valid"


chapter_texts = st.lists(
    st.tuples(st.text(max_size=12), st.text(max_size=80)), min_size=1, max_size=6,
)


@props(25)
@given(texts=chapter_texts)
def test_p07_determinism_modulo_generation(texts: list[tuple[str, str]]) -> None:
    chapters = tuple(
        ChapterRecord(id=f"c{i}", href=f"Text/c{i}.xhtml", title=t, content=f"<p>{x}</p>", text=x, order=i)
        for i, (t, x) in enumerate(texts)
    )
    inputs = dataclasses.replace(make_inputs("v2"), chapters=chapters)
    with tempfile.TemporaryDirectory() as d:
        fresh = book_path(Path(d) / "fresh")
        used = book_path(Path(d) / "used")
        publish(fresh, inputs, create=True)
        publish(used, make_inputs("v0"), create=True)
        g_used = publish(used, inputs)
        assert g_used == 2
        mf, mu = validate_stat(fresh), validate_stat(used)
        assert dataclasses.replace(mf, generation=0) == dataclasses.replace(mu, generation=0)
        assert mf.artifacts == mu.artifacts
        assert (fresh / GEN_DIR / "1" / CHAPTERS).read_bytes() == (used / GEN_DIR / "2" / CHAPTERS).read_bytes()
        assert classify(used, full=True) == "valid"


NONCANON_INJECT = ("tmp", "01", ".DS_Store", "x7", "+3")

op_strategy = st.one_of(
    st.just(("publish", 0)),
    st.tuples(st.just("orphan"), st.integers(1, 50)),
    st.tuples(st.just("noncanon"), st.integers(0, len(NONCANON_INJECT) - 1)),
    st.just(("tmp", 0)),
    st.tuples(st.just("crash"), st.integers(0, 40)),
)


@props(30)
@given(ops=st.lists(op_strategy, min_size=8, max_size=15))
def test_p08_monotonicity_and_invariants_over_sequences(ops: list[tuple[str, int]]) -> None:
    with tempfile.TemporaryDirectory() as d:
        book = setup_scenario("S0u", Path(d))
        users = user_snap(book)
        committed: Optional[str] = None
        noncanon: dict[str, tuple[Any, ...]] = {}
        for step, (op, arg) in enumerate(ops):
            tag = f"v{step + 1}"
            if op == "orphan":
                if os.path.isdir(book / GEN_DIR) and os.path.lexists(book / GEN_DIR / str(arg)):
                    continue
                add_orphan(book, arg)
                continue
            if op == "noncanon":
                name = NONCANON_INJECT[arg]
                (book / GEN_DIR / name).mkdir(parents=True, exist_ok=True)
                noncanon[name] = sub(snapshot(book / GEN_DIR, dir_mtimes=False), name)[name + "/"]
                continue
            if op == "tmp":
                add_stale_tmp(book)
                continue
            names_before = canonical_gens(book)
            g_prev = validate_stat(book).generation if committed else 0
            rec = HookRecorder(crash_at=arg if op == "crash" else None)
            try:
                g = run(book, make_inputs(tag), rec)
            except InjectedCrash:
                if ("p8", "after") in rec.calls:
                    committed = tag
                    g = validate_stat(book).generation
                else:
                    g = 0
            if g:
                committed = tag
                assert g == max(names_before | {g_prev}) + 1
                if rec.raised is None:
                    gens = canonical_gens(book)
                    assert len(gens) <= 2 and max(gens) == g
            if committed is None:
                assert classify(book, full=True) == "missing"
            else:
                assert_valid_with(book, committed)
            assert user_snap(book) == users
            for name, entry in noncanon.items():
                assert sub(snapshot(book / GEN_DIR, dir_mtimes=False), name)[name + "/"] == entry


# =========================================================================== P-09 .. P-11 step-0 guards


class _DevShift:
    def __init__(self, real: os.stat_result) -> None:
        self._real = real
        self.st_dev = real.st_dev + 1

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


@pytest.mark.parametrize("scenario", ["S1", "S4"])
def test_p09_cross_device_gen_refuses_before_anything(tmp_path: Path, scenario: str) -> None:
    book = setup_scenario(scenario, tmp_path)
    before = snapshot(books_dir(book))
    real_lstat = os.lstat
    gen_path = os.path.join(os.fspath(book), GEN_DIR)

    def fake_lstat(path: Any, *args: Any, **kwargs: Any) -> Any:
        st_ = real_lstat(path, *args, **kwargs)
        if not isinstance(path, int) and os.path.abspath(os.fspath(path)) == gen_path:
            return _DevShift(st_)
        return st_

    rec = HookRecorder()
    with pytest.MonkeyPatch.context() as mp:
        install_hooks(mp, rec)
        mp.setattr(os, "lstat", fake_lstat)
        with pytest.raises(CrossDeviceError) as ei:
            publish(book, make_inputs("v2"))
    assert isinstance(ei.value, OSError) and not isinstance(ei.value, BookFormatError)
    assert ei.value.errno == errno.EXDEV
    assert snapshot(books_dir(book)) == before
    only_p0_before(rec)


def _gen_link(book: Path, base: Path) -> None:
    outside = base / "outside" / "gen_copy"
    outside.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(book / GEN_DIR, outside, symlinks=True)
    shutil.rmtree(book / GEN_DIR)
    os.symlink(outside, book / GEN_DIR)


def _p10_a(base: Path) -> Path:
    book = setup_scenario("S1", base)
    _gen_link(book, base)
    return book


def _p10_b(base: Path) -> Path:
    book = setup_scenario("S0u", base)
    (book / GEN_DIR).write_bytes(b"not a directory")
    return book


def _p10_c(base: Path) -> Path:
    book = setup_scenario("S1", base)
    shutil.rmtree(book / GEN_DIR)
    (book / GEN_DIR).write_bytes(b"not a directory")
    return book


def _p10_d(base: Path) -> Path:
    book = _p10_a(base)
    add_debris(book)
    add_stale_tmp(book)
    return book


@pytest.mark.parametrize("build", [_p10_a, _p10_b, _p10_c, _p10_d], ids=["link", "file-nomanifest", "file", "link+"])
def test_p10_bad_gen_parent_refuses_with_book_corrupt(tmp_path: Path, build: Callable[[Path], Path]) -> None:
    book = build(tmp_path)
    before = snapshot(tmp_path)
    rec = HookRecorder()
    with pytest.raises(BookCorrupt) as ei:
        run(book, make_inputs("v2"), rec)
    assert not isinstance(ei.value, OSError)
    assert snapshot(tmp_path) == before
    only_p0_before(rec)


def test_p11a_debris_removed_and_g_ten(tmp_path: Path) -> None:
    book = setup_scenario("S4", tmp_path)
    debris = book.parent / f"{book.name}.staging-4242"
    assert debris.is_dir()
    assert publish(book, make_inputs("v2")) == 10
    assert not os.path.lexists(debris)
    assert_valid_with(book, "v2")


def test_p11b_parked_sibling_refuses(tmp_path: Path) -> None:
    book = setup_scenario("S1", tmp_path)
    add_parked(book)
    before = snapshot(books_dir(book))
    rec = HookRecorder()
    with pytest.raises(LegacyStagingRefused):
        run(book, make_inputs("v2"), rec)
    assert snapshot(books_dir(book)) == before
    assert not any(s.startswith("gc.") or s == "p1" for s in rec.steps())
    assert ("p0.legacy", "before") in rec.calls
    assert (gen_g(book, 1)).is_dir()


# =========================================================================== P-12 .. P-16 failures


def _flip_same_size(path: Path) -> None:
    data = bytearray(path.read_bytes())
    data[-1] ^= 0x01
    path.write_bytes(bytes(data))


def _flip_chapter1(book: Path, g: int) -> None:
    path = gen_g(book, g) / CHAPTERS
    data = bytearray(path.read_bytes())
    lines = bytes(data).split(b"\n")
    offset = len(lines[0]) + 1 + lines[1].index(b"v2")
    data[offset] = ord("x")
    path.write_bytes(bytes(data))


P12_SITES = {
    "cover": (("p3", "after"), lambda book: _flip_same_size(gen_g(book, 3) / IMAGES / "cover.png")),
    "epub": (("p3", "after"), lambda book: _flip_same_size(gen_g(book, 3) / EPUB)),
    "chapter1": (("p2", "after"), lambda book: _flip_chapter1(book, 3)),
}


@pytest.mark.parametrize("site", list(P12_SITES))
def test_p12_sha_comes_from_source_not_written_file(tmp_path: Path, site: str) -> None:
    book = setup_scenario("S1", tmp_path)
    point, action = P12_SITES[site]
    rec = HookRecorder().on(*point, lambda: action(book))
    with pytest.raises(ReadbackError):
        run(book, make_inputs("v2"), rec)
    assert point in rec.calls
    no_new_gen_or_tmp(book, 3)
    assert_valid_with(book, "v1")


def _p12b_journal(base: Path, scenario: str) -> tuple[SyscallJournal, Path, int]:
    book = setup_scenario(scenario, base)
    j = SyscallJournal()
    with pytest.MonkeyPatch.context() as mp:
        j.install(mp)
        g = publish(book, make_inputs("v2"))
    return j, book, g


def _reads(ev: Any) -> bool:
    if ev.kind == "open":
        return "r" in ev.mode or "+" in ev.mode
    return (ev.flags & os.O_ACCMODE) in (os.O_RDONLY, os.O_RDWR)


@pytest.mark.parametrize("scenario", ["S0u", "S1", "S4"])
def test_p12b_no_readback_of_new_generation_before_step6(tmp_path: Path, scenario: str) -> None:
    j, book, g = _p12b_journal(tmp_path, scenario)
    assert g == G_NEW[scenario]
    assert_valid_with(book, "v2")
    under = os.path.join(os.path.realpath(gen_g(book, g)), "")
    p6 = j.index_of("p6", "before")
    opens = [(i, ev) for i, ev in j.of("open", "os.open") if ev.path and ev.path.startswith(under)]
    before = [ev for i, ev in opens if i < p6]
    assert not [ev for ev in before if _reads(ev)], [ev.path for ev in before if _reads(ev)]
    writers = [ev for ev in before
               if (ev.kind == "open" and ev.mode in ("wb", "xb"))
               or (ev.kind == "os.open" and ev.flags & os.O_ACCMODE == os.O_WRONLY and ev.flags & os.O_CREAT)]
    assert writers and len(writers) == len(before)
    chapters = os.path.join(under, CHAPTERS)
    assert any(_reads(ev) and ev.path == chapters for i, ev in opens if i > p6)


def _p13_flip(book: Path, g: int) -> None:
    _flip_same_size(gen_g(book, g) / CHAPTERS)


def _p13_delete(book: Path, g: int) -> None:
    os.unlink(gen_g(book, g) / IMAGES / "cover.png")


def _p13_extra(book: Path, g: int) -> None:
    (gen_g(book, g) / IMAGES / "extra.png").write_bytes(b"extra")


@pytest.mark.parametrize("scenario", ["S1", "S3"])
@pytest.mark.parametrize("mutate", [_p13_flip, _p13_delete, _p13_extra], ids=["flip", "delete", "extra"])
def test_p13_step6_readback_failure_cleans_up(tmp_path: Path, scenario: str, mutate: Callable[..., None]) -> None:
    book = setup_scenario(scenario, tmp_path)
    g_new = G_NEW[scenario]
    users, legacy = user_snap(book), legacy_snap(book)
    taken: dict[str, Any] = {}
    rec = HookRecorder()
    rec.on("p1", "before", lambda: taken.setdefault("snap", snapshot(book)))
    rec.on("p5", "after", lambda: mutate(book, g_new))
    with pytest.raises(ReadbackError):
        run(book, make_inputs("v2"), rec)
    no_new_gen_or_tmp(book, g_new)
    now = snapshot(book)
    assert sub(now, MANIFEST) == sub(taken["snap"], MANIFEST)
    if scenario == "S1":
        assert sub(now, f"{GEN_DIR}/2") == sub(taken["snap"], f"{GEN_DIR}/2")
        assert_valid_with(book, "v1")
    else:
        assert classify(book, full=False) == "missing"
        assert legacy_snap(book) == legacy
    assert user_snap(book) == users


@pytest.mark.parametrize("kind", list(INJECTED_KINDS)[:3])
def test_p14_pre_commit_exception_at_every_point_leaves_old_state(tmp_path: Path, kind: str) -> None:
    dry_book = setup_scenario("S1", tmp_path / "dry")
    dry = HookRecorder()
    run(dry_book, make_inputs("v2"), dry)
    commit = dry.calls.index(("p8", "after"))
    assert commit > 10
    for idx in range(commit):
        base = tmp_path / f"run{idx}"
        book = setup_scenario("S1", base)
        users = user_snap(book)
        rec = HookRecorder(crash_at=idx, exc=INJECTED_KINDS[kind])
        with pytest.raises(BaseException) as ei:
            run(book, make_inputs("v2"), rec)
        assert rec.raised is not None
        assert ei.value is rec.raised, (idx, rec.calls[-1])
        no_new_gen_or_tmp(book, 3)
        assert_valid_with(book, "v1")
        assert user_snap(book) == users


@pytest.mark.parametrize("broken", ["rmtree", "unlink", "rmdir"])
def test_p15_cleanup_failure_still_propagates_original(tmp_path: Path, broken: str) -> None:
    book = setup_scenario("S1", tmp_path)

    def eio(*_a: Any, **_k: Any) -> None:
        raise OSError(errno.EIO, "injected cleanup EIO")

    users = user_snap(book)
    with pytest.MonkeyPatch.context() as mp:
        def crash_hook(step: str, when: str) -> None:
            if (step, when) == ("p6", "before"):
                # Break cleanup only now, so GC earlier in this publish still works.
                if broken == "rmtree":
                    mp.setattr(shutil, "rmtree", eio)
                elif broken == "unlink":
                    mp.setattr(os, "unlink", eio)
                else:
                    mp.setattr(os, "rmdir", eio)
                raise InjectedCrash()

        install_hooks(mp, crash_hook)
        with pytest.raises(InjectedCrash):
            publish(book, make_inputs("v2"))
    assert_valid_with(book, "v1")
    assert user_snap(book) == users
    residue = canonical_gens(book) - {2}
    assert residue <= {3}
    g2 = publish(book, make_inputs("v2"))
    assert user_snap(book) == users
    assert_valid_with(book, "v2")
    assert not os.path.lexists(book / MANIFEST_TMP)
    assert canonical_gens(book) == {2, g2}


def test_p16_post_commit_fsync_failure_propagates_new_state_stands(tmp_path: Path) -> None:
    book = setup_scenario("S1", tmp_path)
    real_replace, real_fsync = os.replace, os.fsync
    state = {"replaced": False, "failed": 0}

    def j_replace(src: Any, dst: Any, **kw: Any) -> None:
        real_replace(src, dst, **kw)
        state["replaced"] = True

    def j_fsync(fd: Any) -> None:
        if state["replaced"] and not state["failed"]:
            state["failed"] += 1
            raise OSError(errno.EIO, "injected fsync EIO")
        real_fsync(fd)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(os, "replace", j_replace)
        mp.setattr(os, "fsync", j_fsync)
        with pytest.raises(OSError) as ei:
            publish(book, make_inputs("v2"))
    assert ei.value.errno == errno.EIO
    assert state["failed"] == 1
    assert assert_valid_with(book, "v2").generation == 3
    assert canonical_gens(book) == {2, 3}
    assert not os.path.lexists(book / MANIFEST_TMP)


# =========================================================================== P-17 .. P-19


def test_p17_retention(tmp_path: Path) -> None:
    book = setup_scenario("S0u", tmp_path)
    assert publish(book, make_inputs("v1")) == 1
    g1 = sub(snapshot(book), f"{GEN_DIR}/1")
    assert publish(book, make_inputs("v2")) == 2
    assert canonical_gens(book) == {1, 2}
    assert sub(snapshot(book), f"{GEN_DIR}/1") == g1
    g2 = sub(snapshot(book), f"{GEN_DIR}/2")
    assert publish(book, make_inputs("v3")) == 3
    assert canonical_gens(book) == {2, 3}
    assert sub(snapshot(book), f"{GEN_DIR}/2") == g2
    assert_valid_with(book, "v3")


_RESERVED = {MANIFEST, MANIFEST_TMP, GEN_DIR}
extra_names = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-.", min_size=1, max_size=10).filter(
    lambda n: n not in (".", "..") and n.lower() not in _RESERVED and not n.lower().startswith("manifest.json")
)
root_extras = st.dictionaries(extra_names, st.tuples(st.booleans(), st.binary(max_size=40)), max_size=6)


@props(40)
@given(extras=root_extras, n_publishes=st.integers(1, 3))
def test_p18_new_root_entries_subset_of_manifest_and_gen(
    extras: dict[str, tuple[bool, bytes]], n_publishes: int
) -> None:
    with tempfile.TemporaryDirectory() as d:
        book = book_path(Path(d))
        book.mkdir()
        seen: set[str] = set()
        for name, (as_dir, data) in extras.items():
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            write_file(book / name / "inner.bin" if as_dir else book / name, data)
        before_root = root_entries(book)
        before = without(snapshot(book), ".")
        last_sha = None
        for i in range(n_publishes):
            publish(book, make_inputs(f"v{i + 1}"))
            sha = hashlib.sha256((book / MANIFEST).read_bytes()).hexdigest()
            assert sha != last_sha
            last_sha = sha
            assert root_entries(book) - before_root <= {MANIFEST, GEN_DIR}
            assert without(snapshot(book), ".", GEN_DIR, MANIFEST) == before
            assert_valid_with(book, f"v{i + 1}")


def test_p19a_absent_book_without_create(tmp_path: Path) -> None:
    book = setup_scenario("S0", tmp_path)
    before = snapshot(tmp_path)
    with pytest.raises(FileNotFoundError):
        publish(book, make_inputs("v1"))
    assert snapshot(tmp_path) == before
    assert not os.path.lexists(book)


def test_p19b_create_with_absent_parent(tmp_path: Path) -> None:
    book = tmp_path / "nope" / "books" / "x_data"
    before = snapshot(tmp_path)
    with pytest.raises(FileNotFoundError):
        publish(book, make_inputs("v1"), create=True)
    assert snapshot(tmp_path) == before


def test_p19c_create_with_parent_present(tmp_path: Path) -> None:
    book = setup_scenario("S0", tmp_path)
    assert publish(book, make_inputs("v1"), create=True) == 1
    assert_valid_with(book, "v1")
    assert root_entries(book) == {MANIFEST, GEN_DIR}


# =========================================================================== isolated corrupt-policy group


def _rewrite(book: Path, raw: bytes) -> None:
    (book / MANIFEST).write_bytes(raw)


def _doc(book: Path) -> dict[str, Any]:
    out: dict[str, Any] = json.loads((book / MANIFEST).read_bytes())
    return out


def _hv_1(book: Path) -> None:
    d = _doc(book)
    d["format_version"] = FORMAT_VERSION + 1
    _rewrite(book, json.dumps(d).encode())


def _hv_2(book: Path) -> None:
    d = _doc(book)
    d["format_version"] = FORMAT_VERSION + 1000
    _rewrite(book, json.dumps(d).encode())


def _hv_3(book: Path) -> None:
    d = _doc(book)
    d["format_version"] = FORMAT_VERSION + 1
    d["generation"] = "x"
    _rewrite(book, json.dumps(d).encode())


def _hv_4(book: Path) -> None:
    _rewrite(book, json.dumps({"format_version": FORMAT_VERSION + 1}).encode())


def _hv_5(book: Path) -> None:
    d = _doc(book)
    d["format_version"] = FORMAT_VERSION + 1
    del d["chapters"]
    d["future_field"] = {"anything": [1, 2, 3]}
    _rewrite(book, json.dumps(d).encode())


class TestPublishOverCorruptBook:
    """The only publish tests that start from a corrupt manifest / generation or an overflowing generation."""

    @pytest.mark.parametrize("mutate", [_hv_1, _hv_2, _hv_3, _hv_4, _hv_5], ids=["+1", "+1000", "gen-x", "bare", "fut"])
    def test_p20a_higher_format_version_refuses(self, tmp_path: Path, mutate: Callable[[Path], None]) -> None:
        book = setup_scenario("S4", tmp_path)
        mutate(book)
        before = snapshot(tmp_path)
        rec = HookRecorder()
        with pytest.raises(BookCorrupt):
            run(book, make_inputs("v2"), rec)
        assert snapshot(tmp_path) == before
        only_p0_before(rec)

    @pytest.mark.parametrize("shape", list(REPAIRABLE))
    def test_p20b_repair_keeps_everything(self, tmp_path: Path, shape: str) -> None:
        book = build_repairable(shape, tmp_path)
        g_expected = REPAIRABLE[shape][1]
        before = snapshot(book)
        outside_before = snapshot(tmp_path / "outside")
        before_root = root_entries(book)
        rec = HookRecorder()

        g = run(book, make_inputs("v2"), rec)

        assert g == g_expected
        assert_valid_with(book, "v2")
        after = snapshot(book)
        prior_gen = {k: v for k, v in before.items() if k.startswith(GEN_DIR + "/") and k != GEN_DIR + "/"}
        assert {k: after.get(k) for k in prior_gen} == prior_gen
        assert snapshot(tmp_path / "outside") == outside_before
        for name in USER_ROOT_ENTRIES:
            assert sub(after, name) == sub(before, name)
        assert root_entries(book) - before_root <= {MANIFEST}
        assert stat.S_ISREG(os.lstat(book / MANIFEST).st_mode)
        assert not os.path.lexists(book / MANIFEST_TMP)
        assert not any(s.startswith("gc.") for s in rec.steps())
        assert ("p0.legacy", "before") in rec.calls and ("p0.legacy", "after") in rec.calls
        for step in ("p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"):
            assert (step, "before") in rec.calls and (step, "after") in rec.calls

    @pytest.mark.parametrize("shape", list(REPAIRABLE))
    def test_p20c_repair_then_normal_publish_collects(self, tmp_path: Path, shape: str) -> None:
        book = build_repairable(shape, tmp_path)
        users = user_snap(book)
        g_repair = publish(book, make_inputs("v2"))
        repaired = sub(snapshot(book), f"{GEN_DIR}/{g_repair}")
        tmp_entry = sub(snapshot(book), f"{GEN_DIR}/tmp")
        rec = HookRecorder()

        g2 = run(book, make_inputs("v3"), rec)

        assert g2 == g_repair + 1
        assert canonical_gens(book) == {g_repair, g_repair + 1}
        assert not os.path.lexists(book / MANIFEST_TMP)
        assert sub(snapshot(book), f"{GEN_DIR}/{g_repair}") == repaired
        assert_valid_with(book, "v3")
        assert ("gc.delete", "before") in rec.calls
        assert tmp_entry and sub(snapshot(book), f"{GEN_DIR}/tmp") == tmp_entry
        assert user_snap(book) == users

    @props(40)
    @given(
        shape=st.sampled_from(sorted(REPAIRABLE)),
        canon=st.lists(st.tuples(st.integers(1, 200), st.sampled_from(["dir", "file", "link"])), max_size=6),
        noncanon=st.lists(st.sampled_from(["tmp2", "01", "+5", "７", "x"]), max_size=2, unique=True),
        readable=st.one_of(st.none(), st.integers(1, 300)),
        stale_tmp=st.booleans(),
    )
    def test_p20d_repair_g_and_conservation_property(
        self, shape: str, canon: list[tuple[int, str]], noncanon: list[str], readable: Optional[int],
        stale_tmp: bool,
    ) -> None:
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            book = build_repairable(shape, base)
            gen = book / GEN_DIR
            target = base / "outside" / "link_target"
            target.mkdir(parents=True, exist_ok=True)
            for n, kind in canon:
                p = gen / str(n)
                if os.path.lexists(p):
                    continue
                if kind == "dir":
                    p.mkdir()
                elif kind == "file":
                    p.write_bytes(b"canon file")
                else:
                    os.symlink(target, p)
            for name in noncanon:
                (gen / name).mkdir(exist_ok=True)
            gen_number: Optional[int] = None
            if shape in MANIFEST_PARSES:
                if readable is not None:
                    doc = _doc(book)
                    doc["generation"] = readable
                    _rewrite(book, json.dumps(doc, ensure_ascii=False).encode())
                gen_number = manifest_from_bytes((book / MANIFEST).read_bytes()).generation
            if stale_tmp:
                add_stale_tmp(book, b"JUNK-stale-tmp-bytes")
            on_disk = canonical_gens(book)
            # The override may re-point the manifest at an intact generation: then it is no repair start.
            assume(classify(book, full=False) == "corrupt")
            before = snapshot(book)
            users = user_snap(book)

            g = publish(book, make_inputs("v2"))

            assert g == max(on_disk | ({gen_number} if gen_number else set())) + 1
            after = snapshot(book)
            prior = {k: v for k, v in before.items() if k.startswith(GEN_DIR + "/") and k != GEN_DIR + "/"}
            assert {k: after.get(k) for k in prior} == prior
            assert_valid_with(book, "v2")
            assert user_snap(book) == users
            assert not os.path.lexists(book / MANIFEST_TMP)
            assert b"JUNK" not in (book / MANIFEST).read_bytes()

    def test_p20e_i_manifest_directory_refuses(self, tmp_path: Path) -> None:
        book = setup_scenario("S4", tmp_path)
        os.unlink(book / MANIFEST)
        write_file(book / MANIFEST / "inner.json", b"{}")
        before = snapshot(tmp_path)
        rec = HookRecorder()
        with pytest.raises(BookCorrupt):
            run(book, make_inputs("v2"), rec)
        assert snapshot(tmp_path) == before
        assert not os.path.lexists(gen_g(book, 10))
        only_p0_before(rec)

    @pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores mode 000")
    def test_p20e_ii_unreadable_manifest_repairs(self, tmp_path: Path) -> None:
        book = setup_scenario("S1", tmp_path)
        add_orphan(book, 9)
        before = snapshot(book)
        os.chmod(book / MANIFEST, 0)
        rec = HookRecorder()
        try:
            g = run(book, make_inputs("v2"), rec)
        finally:
            if os.path.lexists(book / MANIFEST):
                os.chmod(book / MANIFEST, 0o644)
        assert g == 10
        assert_valid_with(book, "v2")
        after = snapshot(book)
        for prefix in (f"{GEN_DIR}/1", f"{GEN_DIR}/2", f"{GEN_DIR}/9"):
            assert sub(after, prefix) == sub(before, prefix)
        assert stat.S_ISREG(os.lstat(book / MANIFEST).st_mode)
        assert not any(s.startswith("gc.") for s in rec.steps())

    @staticmethod
    def _overflow_a(base: Path) -> Path:
        book = setup_scenario("S5", base)
        (book / GEN_DIR / str(MAX_GENERATION)).mkdir()
        return book

    @staticmethod
    def _overflow_b(base: Path) -> Path:
        book = setup_scenario("S1", base)
        (book / GEN_DIR / str(MAX_GENERATION)).mkdir()
        return book

    @staticmethod
    def _overflow_c(base: Path) -> Path:
        book = book_path(base)
        book.mkdir()
        publish(book, make_inputs("v1"))
        os.rename(book / GEN_DIR / "1", book / GEN_DIR / str(MAX_GENERATION))
        doc = _doc(book)
        doc["generation"] = MAX_GENERATION
        _rewrite(book, json.dumps(doc, ensure_ascii=False).encode())
        assert classify(book, full=True) == "valid"
        return book

    @pytest.mark.parametrize("which", ["a", "b", "c"])
    def test_p20f_generation_overflow_refuses(self, tmp_path: Path, which: str) -> None:
        book = getattr(self, f"_overflow_{which}")(tmp_path)
        add_debris(book)
        add_stale_tmp(book)
        before = snapshot(tmp_path)
        rec = HookRecorder()
        with pytest.raises(BookCorrupt):
            run(book, make_inputs("v2"), rec)
        assert snapshot(tmp_path) == before
        only_p0_before(rec)

    def test_p20f_d_control_max_generation_exactly(self, tmp_path: Path) -> None:
        book = setup_scenario("S5", tmp_path)
        (book / GEN_DIR / str(MAX_GENERATION - 1)).mkdir()
        add_debris(book)
        add_stale_tmp(book)
        assert publish(book, make_inputs("v2")) == MAX_GENERATION
        assert_valid_with(book, "v2")
        assert manifest_from_bytes((book / MANIFEST).read_bytes()).generation == MAX_GENERATION

    def test_p21_stat_valid_content_corrupt_takes_normal_path(self, tmp_path: Path) -> None:
        book = setup_scenario("S1", tmp_path)
        _flip_same_size(gen_g(book, 2) / EPUB)
        assert classify(book, full=False) == "valid" and classify(book, full=True) == "corrupt"
        prev = sub(snapshot(book), f"{GEN_DIR}/2")
        rec = HookRecorder()
        assert run(book, make_inputs("v2"), rec) == 3
        assert_valid_with(book, "v2")
        assert canonical_gens(book) == {2, 3}
        assert sub(snapshot(book), f"{GEN_DIR}/2") == prev
        assert ("gc.delete", "before") in rec.calls


# =========================================================================== P-22 invalid inputs


def _bad_image(name: str) -> PublishInputs:
    good = make_inputs("v2")
    return dataclasses.replace(good, images={**good.images, name: b"PNG-bad"}, image_origins={})


def _dup_ids() -> PublishInputs:
    good = make_inputs("v2")
    chapters = list(good.chapters)
    chapters[1] = dataclasses.replace(chapters[1], id=chapters[0].id)
    return dataclasses.replace(good, chapters=tuple(chapters))


def _gap_order() -> PublishInputs:
    good = make_inputs("v2")
    chapters = list(good.chapters)
    chapters[2] = dataclasses.replace(chapters[2], order=3)
    return dataclasses.replace(good, chapters=tuple(chapters))


INVALID: dict[str, Callable[[], PublishInputs]] = {
    "dotdot": lambda: _bad_image("../x.png"),
    "slash": lambda: _bad_image("a/b.png"),
    "empty": lambda: _bad_image(""),
    "dup-id": _dup_ids,
    "gap-order": _gap_order,
}


@pytest.mark.parametrize("bad", list(INVALID))
def test_p22_invalid_inputs_rejected_before_any_effect(tmp_path: Path, bad: str) -> None:
    book = setup_scenario("S4", tmp_path)
    inputs = INVALID[bad]()
    before = snapshot(tmp_path)
    rec = HookRecorder()
    with pytest.raises(ValueError):
        run(book, inputs, rec)
    assert snapshot(tmp_path) == before
    assert not any(s in ("p0.legacy", "p1") or s.startswith("gc.") for s in rec.steps())


@pytest.mark.parametrize("bad", list(INVALID))
def test_p22_s0_create_invalid_inputs_never_mkdir(tmp_path: Path, bad: str) -> None:
    book = setup_scenario("S0", tmp_path)
    before = snapshot(books_dir(book))
    rec = HookRecorder()
    with pytest.raises(ValueError):
        run(book, INVALID[bad](), rec, create=True)
    assert not os.path.lexists(book)
    assert snapshot(books_dir(book)) == before
    only_p0_before(rec)


# =========================================================================== P-23 / P-23b durability audit


def _p23_s0_create(base: Path) -> Path:
    return setup_scenario("S0", base)


def _p23_eacces(base: Path) -> Path:
    book = setup_scenario("S1", base)
    add_orphan(book, 9)
    os.chmod(book / MANIFEST, 0)
    return book


AUDIT_ROWS: dict[str, Callable[[Path], Path]] = {
    "S1": lambda b: setup_scenario("S1", b),
    "S0-create": _p23_s0_create,
    "S0u": lambda b: setup_scenario("S0u", b),
    "S3": lambda b: setup_scenario("S3", b),
    "S4": lambda b: setup_scenario("S4", b),
    "R-unparse": lambda b: build_repairable("R-unparse", b),
    "R-man-link": lambda b: build_repairable("R-man-link", b),
    "R-art-missing": lambda b: build_repairable("R-art-missing", b),
    "EACCES": _p23_eacces,
}


def _ident(path: Path) -> tuple[int, int]:
    st_ = os.lstat(path)
    return (st_.st_dev, st_.st_ino)


@pytest.mark.parametrize("row", list(AUDIT_ROWS))
def test_p23_durability_ordering_every_branch(tmp_path: Path, row: str) -> None:
    if row == "EACCES" and hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root ignores mode 000")
    book = AUDIT_ROWS[row](tmp_path)
    j = SyscallJournal()
    try:
        with pytest.MonkeyPatch.context() as mp:
            j.install(mp)
            g = publish(book, make_inputs("v2"), create=(row == "S0-create"))
    finally:
        if os.path.lexists(book / MANIFEST) and not os.path.islink(book / MANIFEST):
            os.chmod(book / MANIFEST, 0o644)
    assert_valid_with(book, "v2")
    real_book = os.path.realpath(book)

    replaces = j.of("replace")
    assert len(replaces) == 1
    r_idx, r_ev = replaces[0]
    assert r_ev.src == os.path.join(real_book, MANIFEST_TMP)
    assert r_ev.path == os.path.join(real_book, MANIFEST)
    assert not j.of("rename", "link")
    manifest_path = os.path.join(real_book, MANIFEST)
    assert not [ev for _, ev in j.of("unlink", "remove", "rmdir", "rename") if ev.path == manifest_path]

    fsyncs = j.of("fsync")
    final_files = [p for p in (gen_g(book, g)).rglob("*") if p.is_file()] + [book / MANIFEST]
    for path in final_files:
        ident, size = _ident(path), os.lstat(path).st_size
        mine = [(i, ev) for i, ev in fsyncs if ev.ident == ident]
        assert mine, f"{path} never fsynced"
        last_i, last_ev = mine[-1]
        assert last_ev.size == size, path
        assert last_i < r_idx, path

    dirs = [gen_g(book, g), book / GEN_DIR, book]
    if (gen_g(book, g) / IMAGES).is_dir():
        dirs.insert(0, gen_g(book, g) / IMAGES)
    for dpath in dirs:
        ident = _ident(dpath)
        creations = [i for i, ev in enumerate(j.events) if ev.creates and ev.parent == ident]
        assert creations, dpath
        synced = [i for i, ev in fsyncs if ev.ident == ident and max(creations) < i < r_idx]
        assert synced, f"{dpath} not fsynced after its last child creation and before the commit"
    book_ident = _ident(book)
    assert any(i > r_idx and ev.ident == book_ident for i, ev in fsyncs)


def test_p24_exdev_on_commit_replace_cleans_up(tmp_path: Path) -> None:
    for scenario in ("S1", "S3"):
        book = setup_scenario(scenario, tmp_path / scenario)
        before = snapshot(book)
        real_replace, real_rename = os.replace, os.rename

        def exdev(real: Callable[..., None]) -> Callable[..., None]:
            def f(src: Any, dst: Any, **kw: Any) -> None:
                if os.path.basename(os.fspath(dst)) == MANIFEST:
                    raise OSError(errno.EXDEV, "injected EXDEV", os.fspath(dst))
                real(src, dst, **kw)
            return f

        def tripwire(*_a: Any, **_k: Any) -> None:
            raise AssertionError("shutil copy/move must never stand in for the commit")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(os, "replace", exdev(real_replace))
            mp.setattr(os, "rename", exdev(real_rename))
            for name in ("move", "copy", "copy2", "copyfile", "copytree"):
                mp.setattr(shutil, name, tripwire)
            with pytest.raises(OSError) as ei:
                publish(book, make_inputs("v2"))
        assert ei.value.errno == errno.EXDEV
        no_new_gen_or_tmp(book, G_NEW[scenario])
        after = snapshot(book)
        if scenario == "S1":
            assert_valid_with(book, "v1")
            assert sub(after, f"{GEN_DIR}/2") == sub(before, f"{GEN_DIR}/2")
            assert sub(after, MANIFEST) == sub(before, MANIFEST)
        else:
            assert classify(book, full=False) == "missing"
            assert without(after, ".", GEN_DIR) == without(before, ".", GEN_DIR)


# =========================================================================== P-25 near-miss names

NEAR_MISS = ["0400", "+400", " 400", "４００", "400\n", "09007199254740993"]


@pytest.mark.parametrize("base_kind", ["S1", "R-art-missing"])
@pytest.mark.parametrize("name", NEAR_MISS, ids=["lead0", "plus", "space", "fullwidth", "newline", "huge0"])
def test_p25_noncanonical_names_never_affect_g(tmp_path: Path, base_kind: str, name: str) -> None:
    book = setup_scenario("S1", tmp_path) if base_kind == "S1" else build_repairable(base_kind, tmp_path)
    (book / GEN_DIR / name).mkdir()
    entry = sub(snapshot(book), f"{GEN_DIR}/{name}")
    assert entry

    g = publish(book, make_inputs("v2"))

    assert g == (3 if base_kind == "S1" else 10)
    assert_valid_with(book, "v2")
    assert sub(snapshot(book), f"{GEN_DIR}/{name}") == entry
    if base_kind == "S1":
        assert not os.path.lexists(gen_g(book, 1))


# =========================================================================== G-12b publish half


@pytest.mark.parametrize("row", ["S0u", "S1", "S3", "S4", "S5", "R-unparse"])
def test_g12b_publish_never_lists_book_root(tmp_path: Path, row: str) -> None:
    book = build_repairable(row, tmp_path) if row.startswith("R-") else setup_scenario(row, tmp_path)
    root = _ident(book)
    j = SyscallJournal()
    with pytest.MonkeyPatch.context() as mp:
        j.install(mp)
        g = publish(book, make_inputs("v2"))
    assert g == (10 if row.startswith("R-") else G_NEW[row])
    assert_valid_with(book, "v2")
    listings = j.of(*SyscallJournal.LISTING)
    assert listings, "the journal saw no listing at all"
    assert not [ev.path for _, ev in listings if ev.ident == root]


# =========================================================================== hook sequence sanity


def test_hook_sequence_order_and_bracketing(tmp_path: Path) -> None:
    book = setup_scenario("S1", tmp_path)
    rec = HookRecorder()
    run(book, make_inputs("v2"), rec)
    calls = rec.calls
    assert calls[:2] == [("p0", "before"), ("p0", "after")]
    assert {s for s, _ in calls} <= set(PUBLISH_HOOKS)
    for i in range(0, len(calls), 2):
        assert calls[i][1] == "before" and calls[i + 1] == (calls[i][0], "after"), calls[i:i + 2]
    rank = {"p0": 0, "p0.legacy": 1, "gc.validate": 2, "gc.delete": 2, "gc.tmp": 2}
    ranks = [rank.get(s, 3 + PUBLISH_HOOKS.index(s)) for s, _ in calls]
    assert ranks == sorted(ranks)
    assert {"gc.validate", "gc.delete"} <= rec.steps()
    assert [s for s, w in calls if w == "before"][-6:] == ["p4", "p5", "p6", "p7", "p8", "p8.fsync"]


# =========================================================================== layout parity with hand fixtures


def _tree_bytes(root: Path) -> dict[str, Optional[bytes]]:
    out: dict[str, Optional[bytes]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for dname in dirnames:
            out[os.path.relpath(os.path.join(dirpath, dname), root) + "/"] = None
        for fname in filenames:
            p = os.path.join(dirpath, fname)
            out[os.path.relpath(p, root)] = Path(p).read_bytes()
    return out


def test_layout_parity_with_gc_fixture_single_gen(tmp_path: Path) -> None:
    hand = tmp_path / "hand" / "x_data"
    gcfix.build_book(hand, current=1, previous=(), orphans=(), tmp=False, user=False, stray=False)
    pub = book_path(tmp_path / "pub")
    publish(pub, make_inputs("v1"), create=True)
    assert root_entries(hand) == root_entries(pub) == {MANIFEST, GEN_DIR}
    assert gen_file_set(hand / GEN_DIR / "1") == gen_file_set(pub / GEN_DIR / "1")
    assert (hand / MANIFEST).read_bytes() == (pub / MANIFEST).read_bytes()
    assert (hand / GEN_DIR / "1" / CHAPTERS).read_bytes() == (pub / GEN_DIR / "1" / CHAPTERS).read_bytes()
    assert _tree_bytes(hand) == _tree_bytes(pub)


def test_layout_parity_with_gc_fixture_two_gens(tmp_path: Path) -> None:
    hand = tmp_path / "hand" / "x_data"
    gcfix.build_book(hand, current=2, previous=(1,), orphans=(), tmp=False, user=False, stray=False)
    pub = book_path(tmp_path / "pub")
    publish(pub, make_inputs("v1"), create=True)
    publish(pub, make_inputs("v2"))
    assert root_entries(hand) == root_entries(pub)
    assert canonical_gens(hand) == canonical_gens(pub) == {1, 2}
    assert _tree_bytes(hand) == _tree_bytes(pub)


@pytest.mark.parametrize("images,pkl", [(True, True), (False, True), (True, False), (False, False)])
def test_layout_parity_with_classify_fixture(tmp_path: Path, images: bool, pkl: bool) -> None:
    hand = tmp_path / "hand" / "x_data"
    kfix.build_valid(hand, g=1, images=images, pkl=pkl)
    pub = book_path(tmp_path / "pub")
    image_bytes = {n: data + b"v1" for n, data in kfix.IMAGE_FILES.items()}
    publish(pub, make_inputs("v1", images=images, pkl=pkl, image_bytes=image_bytes), create=True)
    assert root_entries(hand) == root_entries(pub)
    assert gen_file_set(hand / GEN_DIR / "1") == gen_file_set(pub / GEN_DIR / "1")
    assert (hand / MANIFEST).read_bytes() == (pub / MANIFEST).read_bytes()
    assert _tree_bytes(hand) == _tree_bytes(pub)


# =========================================================================== classify / GC over publish-built books


@pytest.mark.parametrize("scenario", ["S1", "S2"])
def test_k07_publish_built_book_classifies_valid(tmp_path: Path, scenario: str) -> None:
    book = setup_scenario(scenario, tmp_path)
    assert classify(book, full=False) == "valid"
    assert classify(book, full=True) == "valid"
    assert validate_stat(book).generation == (2 if scenario == "S1" else 1)


def test_gc_over_publish_built_book(tmp_path: Path) -> None:
    book = setup_scenario("S1", tmp_path)
    add_orphan(book, 9)
    add_stale_tmp(book)
    before = snapshot(book)
    result = collect_garbage(book)
    assert result.state == "valid"
    assert result.deleted == (f"{GEN_DIR}/1", f"{GEN_DIR}/9", MANIFEST_TMP)
    after = snapshot(book)
    assert sub(after, f"{GEN_DIR}/2") == sub(before, f"{GEN_DIR}/2")
    assert sub(after, MANIFEST) == sub(before, MANIFEST)
    for name in USER_DATA:
        assert sub(after, name) == sub(before, name)
    assert collect_garbage(book).deleted == ()
    assert_valid_with(book, "v1")


# ======================================================== WI-1.10 A1: create=True removes the book it made

import logging  # noqa: E402  (appended section; keeps the recorded import block above untouched)

from reader3_app.book_format import ManifestTocEntry, PublishInputError  # noqa: E402

_LOGGER = "reader3_app.book_format"

S0_PRE_COMMIT: list[tuple[str, str]] = [
    ("p0", "before"), ("p0", "after"), ("p0.legacy", "before"), ("p0.legacy", "after"),
    ("gc.validate", "before"), ("gc.validate", "after"),
    ("p1", "before"), ("p1", "after"), ("p2", "before"), ("p2", "after"), ("p3", "before"), ("p3", "after"),
    ("p4", "before"), ("p4", "after"), ("p5", "before"), ("p5", "after"), ("p6", "before"), ("p6", "after"),
    ("p7", "before"), ("p7", "after"), ("p8", "before"),
]
"""Every hook a fresh ``create=True`` publish reaches before the commit rename, in order (gate-3 table, S0)."""


class _At:
    """A ``_crash_point`` stand-in: at ``point`` run ``action`` (if any), then raise the injected exception."""

    def __init__(self, step: str, when: str, action: Optional[Callable[[], None]] = None,
                 exc: Callable[[], BaseException] = InjectedCrash) -> None:
        self.point = (step, when)
        self.action = action
        self.exc = exc
        self.calls: list[tuple[str, str]] = []
        self.raised: Optional[BaseException] = None

    def __call__(self, step: str, when: str) -> None:
        self.calls.append((step, when))
        if (step, when) == self.point and self.raised is None:
            if self.action is not None:
                self.action()
            self.raised = self.exc()
            raise self.raised


def _errors(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == _LOGGER and r.levelno >= logging.ERROR]


def test_wi110_a1_s0_dry_run_matches_the_pre_commit_list(tmp_path: Path) -> None:
    """A1 (determinism, S2, Level 1): the list the A1 cells walk is what a fresh create=True publish reaches."""
    rec = HookRecorder()
    run(setup_scenario("S0", tmp_path), make_inputs("v2"), rec, create=True)
    assert rec.calls[: len(S0_PRE_COMMIT)] == S0_PRE_COMMIT
    assert rec.calls[len(S0_PRE_COMMIT)] == ("p8", "after")


def test_wi110_a1_create_then_legacy_refusal_leaves_no_book(tmp_path: Path) -> None:
    """A1 (failure, S3, Level 2): a parked sibling refuses the publish, and the book this call made is gone."""
    book = setup_scenario("S0", tmp_path)
    sib = add_parked(book)
    before = snapshot(books_dir(book), dir_mtimes=False)
    sib_before = snapshot(sib)
    with pytest.raises(LegacyStagingRefused):
        publish(book, make_inputs("v1"), create=True)
    assert not os.path.lexists(book)
    assert snapshot(sib) == sib_before
    assert snapshot(books_dir(book), dir_mtimes=False) == before


@pytest.mark.parametrize("step,when", S0_PRE_COMMIT, ids=[f"{s}-{w}" for s, w in S0_PRE_COMMIT])
def test_wi110_a1_create_then_pre_commit_crash_leaves_no_book(tmp_path: Path, step: str, when: str) -> None:
    """A1 (failure, S5 over every pre-commit point, Level 2): a crash before commit removes the made book dir."""
    book = setup_scenario("S0", tmp_path)
    before = snapshot(books_dir(book), dir_mtimes=False)
    rec = _At(step, when)
    with pytest.raises(InjectedCrash) as ei:
        run(book, make_inputs("v2"), rec, create=True)
    assert ei.value is rec.raised and rec.calls[-1] == (step, when)
    assert not os.path.lexists(book)
    assert snapshot(books_dir(book), dir_mtimes=False) == before
    assert publish(book, make_inputs("v2"), create=True) == 1
    assert_valid_with(book, "v2")


def test_wi110_a1_create_then_crash_after_commit_keeps_the_book(tmp_path: Path) -> None:
    """A1 (state, S2, Level 2): after the commit nothing is rolled back; the made book stays, valid."""
    book = setup_scenario("S0", tmp_path)
    for point in (("p8", "after"), ("p8.fsync", "before"), ("p8.fsync", "after")):
        rec = _At(*point)
        with pytest.raises(InjectedCrash):
            run(book, make_inputs("v2"), rec, create=True)
        assert_valid_with(book, "v2")


def test_wi110_a1_create_on_existing_dir_is_never_removed(tmp_path: Path) -> None:
    """A1 (guard, S3, Level 2): create=True over an existing empty dir only removes what the call made: nothing."""
    book = setup_scenario("S0", tmp_path)
    book.mkdir()
    ino = os.lstat(book).st_ino
    sib = add_parked(book)
    with pytest.raises(LegacyStagingRefused):
        publish(book, make_inputs("v1"), create=True)
    assert os.path.isdir(book) and os.lstat(book).st_ino == ino and root_entries(book) == set()
    shutil.rmtree(sib)
    for point in (("p0.legacy", "after"), ("p1", "after"), ("p8", "before")):
        with pytest.raises(InjectedCrash):
            run(book, make_inputs("v1"), _At(*point), create=True)
        assert os.path.isdir(book) and os.lstat(book).st_ino == ino and root_entries(book) == set(), point


def test_wi110_a1_made_book_that_cannot_be_removed_logs_and_propagates(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A1 (failure, S3, Level 1+2): a stray file makes the rmdir fail; ERROR logged, original exception raised."""
    book = setup_scenario("S0", tmp_path)
    rec = _At("p1", "after", lambda: (book / "stray.txt").write_bytes(b"user"))
    caplog.set_level(logging.ERROR, logger=_LOGGER)
    with pytest.raises(InjectedCrash) as ei:
        run(book, make_inputs("v1"), rec, create=True)
    assert ei.value is rec.raised
    assert root_entries(book) == {"stray.txt"}
    assert (book / "stray.txt").read_bytes() == b"user"
    assert any(str(book) in m for m in _errors(caplog)), _errors(caplog)


# =========================================================================== WI-1.10 B2: input rejection


def _replace_chapter(i: int, **changes: Any) -> PublishInputs:
    good = make_inputs("v2")
    chapters = list(good.chapters)
    chapters[i] = dataclasses.replace(chapters[i], **changes)
    return dataclasses.replace(good, chapters=tuple(chapters))


def _bad_toc() -> PublishInputs:
    good = make_inputs("v2")
    entry = ManifestTocEntry(title="One", href=5, file_href="x", anchor="", children=())  # type: ignore[arg-type]
    return dataclasses.replace(good, toc=(entry,))


def _deep_toc(depth: int) -> PublishInputs:
    entry = ManifestTocEntry(title="leaf", href="c.xhtml", file_href="c.xhtml", anchor="", children=())
    for i in range(depth):
        entry = ManifestTocEntry(title=f"t{i}", href="c.xhtml", file_href="c.xhtml", anchor="", children=(entry,))
    return dataclasses.replace(make_inputs("v2"), toc=(entry,))


B2_INVALID: dict[str, Callable[[], PublishInputs]] = {
    "not-a-record": lambda: dataclasses.replace(
        make_inputs("v2"), chapters=("not a record",)),  # type: ignore[arg-type]
    "order-str": lambda: _replace_chapter(0, order="0"),
    "title-none": lambda: _replace_chapter(1, title=None),
    "origins-unknown": lambda: dataclasses.replace(
        make_inputs("v2"), image_origins={**make_inputs("v2").image_origins, "ghost.png": ("OEBPS/g.png",)}),
    "epub-int": lambda: dataclasses.replace(make_inputs("v2"), epub=123),  # type: ignore[arg-type]
    "image-int": lambda: dataclasses.replace(make_inputs("v2"), images={"cover.png": 5},  # type: ignore[dict-item]
                                             image_origins={}),
    "title-int": lambda: dataclasses.replace(
        make_inputs("v2"), metadata=dataclasses.replace(make_inputs("v2").metadata, title=1)),  # type: ignore[arg-type]
    "toc-href-int": _bad_toc,
    "toc-too-deep": lambda: _deep_toc(1000),
}


@pytest.mark.parametrize("bad", list(B2_INVALID))
def test_wi110_b2_input_rejection_is_publish_input_error_and_touches_nothing(tmp_path: Path, bad: str) -> None:
    """B2 (guard, S3, Level 1+2): each malformed input raises PublishInputError; the whole tree is unchanged."""
    book = setup_scenario("S1", tmp_path)
    inputs = B2_INVALID[bad]()
    before = snapshot(tmp_path)
    rec = HookRecorder()
    with pytest.raises(PublishInputError):
        run(book, inputs, rec)
    assert snapshot(tmp_path) == before
    assert rec.calls == []


# =========================================================================== WI-1.10 B3: step-0 shapes


@pytest.mark.parametrize("create", [False, True])
def test_wi110_b3_book_dir_is_a_regular_file(tmp_path: Path, create: bool) -> None:
    """B3 (guard, S3, Level 1+2): a regular file at book_dir raises NotADirectoryError and is left alone."""
    book = book_path(tmp_path)
    book.write_bytes(b"not a book")
    before = snapshot(tmp_path)
    with pytest.raises(NotADirectoryError):
        publish(book, make_inputs("v1"), create=create)
    assert snapshot(tmp_path) == before


def test_wi110_b3_tmp_directory_refuses_with_zero_writes(tmp_path: Path) -> None:
    """B3 (guard, S3, Level 2): manifest.json.tmp as a directory is BookCorrupt before any write."""
    book = setup_scenario("S1", tmp_path)
    write_file(book / MANIFEST_TMP / "inner.bin", b"x")
    before = snapshot(tmp_path)
    rec = HookRecorder()
    with pytest.raises(BookCorrupt):
        run(book, make_inputs("v2"), rec)
    assert snapshot(tmp_path) == before
    only_p0_before(rec)


@pytest.mark.parametrize("raw", [b"[]", b"1", b"null", b'"manifest"'], ids=["array", "int", "null", "string"])
def test_wi110_b3_non_object_manifest_is_repaired(tmp_path: Path, raw: bytes) -> None:
    """B3 (state, S2, Level 1+2): a JSON non-object manifest is a repair; no GC, prior gens kept, then valid."""
    book = setup_scenario("S1", tmp_path)
    (book / MANIFEST).write_bytes(raw)
    before = snapshot(book)
    rec = HookRecorder()
    assert run(book, make_inputs("v2"), rec) == 3
    assert not any(s.startswith("gc.") for s in rec.steps())
    assert classify(book, full=True) == "valid"
    assert_valid_with(book, "v2")
    after = snapshot(book)
    for g in ("1", "2"):
        assert sub(after, f"{GEN_DIR}/{g}") == sub(before, f"{GEN_DIR}/{g}")


# =========================================================================== WI-1.10 B8: epub=None


def test_wi110_b8_publish_without_epub(tmp_path: Path) -> None:
    """B8 (boundary, S2, Level 1+2): epub=None writes no book.epub and records none; the book is fully valid."""
    book = setup_scenario("S0", tmp_path)
    inputs = dataclasses.replace(make_inputs("v1"), epub=None)
    assert publish(book, inputs, create=True) == 1
    assert not os.path.lexists(gen_g(book, 1) / EPUB)
    m = validate_stat(book)
    assert EPUB not in {a.path for a in m.artifacts}
    assert gen_file_set(gen_g(book, 1))[0] == expected_gen_files(inputs)
    assert classify(book, full=True) == "valid"
    assert_valid_with(book, "v1")


# =========================================================================== WI-1.10 B9: seam-driven cleanup paths


def test_wi110_b9_manifest_turns_corrupt_before_gc(tmp_path: Path) -> None:
    """B9 (failure, S3, Level 1+2): corrupted between step 0 and GC; BookCorrupt, no new gen, no tmp."""
    book = setup_scenario("S1", tmp_path)
    rec = HookRecorder().on("gc.validate", "before", lambda: (book / MANIFEST).write_bytes(b"{"))
    with pytest.raises(BookCorrupt, match="turned corrupt during publish GC"):
        run(book, make_inputs("v2"), rec)
    no_new_gen_or_tmp(book, 3)
    assert canonical_gens(book) == {1, 2}


def test_wi110_b9_tmp_rewritten_before_readback(tmp_path: Path) -> None:
    """B9 (failure, S3, Level 1+2): a tmp that no longer holds the manifest fails read-back and is cleaned up."""
    book = setup_scenario("S1", tmp_path)
    rec = HookRecorder().on("p6", "before", lambda: (book / MANIFEST_TMP).write_bytes(b'{"other": 1}\n'))
    with pytest.raises(ReadbackError, match="does not hold the manifest"):
        run(book, make_inputs("v2"), rec)
    no_new_gen_or_tmp(book, 3)
    assert_valid_with(book, "v1")


def test_wi110_b9_commit_onto_a_directory_propagates_the_os_error(tmp_path: Path) -> None:
    """B9 (failure, S3, Level 1+2): a non-EXDEV commit failure is the OSError itself, never CrossDeviceError."""
    book = setup_scenario("S0u", tmp_path)

    def block() -> None:
        write_file(book / MANIFEST / "inner.bin", b"blocker")

    rec = HookRecorder().on("p8", "before", block)
    with pytest.raises(OSError) as ei:
        run(book, make_inputs("v1"), rec)
    assert not isinstance(ei.value, CrossDeviceError)
    assert ei.value.errno != errno.EXDEV
    no_new_gen_or_tmp(book, 1)
    assert not os.path.lexists(book / GEN_DIR)
    assert (book / MANIFEST / "inner.bin").read_bytes() == b"blocker"


def test_wi110_b9_tmp_already_gone_at_cleanup_is_tolerated(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """B9 (failure, S3, Level 1+2): the tmp vanished before cleanup; the injected exception still propagates."""
    book = setup_scenario("S1", tmp_path)
    rec = _At("p4", "after", lambda: os.unlink(book / MANIFEST_TMP))
    caplog.set_level(logging.ERROR, logger=_LOGGER)
    with pytest.raises(InjectedCrash) as ei:
        run(book, make_inputs("v2"), rec)
    assert ei.value is rec.raised
    no_new_gen_or_tmp(book, 3)
    assert _errors(caplog) == []
    assert_valid_with(book, "v1")


def test_wi110_b9_new_gen_already_gone_at_cleanup_is_tolerated(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """B9 (failure, S3, Level 1+2): gen/<g> vanished before cleanup; first publish also drops the empty gen/."""
    book = setup_scenario("S0u", tmp_path)
    rec = _At("p1", "after", lambda: shutil.rmtree(gen_g(book, 1)))
    caplog.set_level(logging.ERROR, logger=_LOGGER)
    with pytest.raises(InjectedCrash) as ei:
        run(book, make_inputs("v1"), rec)
    assert ei.value is rec.raised
    assert not os.path.lexists(book / GEN_DIR)
    assert _errors(caplog) == []
    assert classify(book, full=True) == "missing"


def test_wi110_b9_gen_root_that_cannot_be_removed_logs_and_propagates(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """B9 (failure, S3, Level 1+2): a stray file in a new gen/ blocks its rmdir; ERROR, original raised, file kept."""
    book = setup_scenario("S0u", tmp_path)
    rec = _At("p3", "after", lambda: (book / GEN_DIR / "stray.bin").write_bytes(b"stray"))
    caplog.set_level(logging.ERROR, logger=_LOGGER)
    with pytest.raises(InjectedCrash) as ei:
        run(book, make_inputs("v1"), rec)
    assert ei.value is rec.raised
    assert set(os.listdir(book / GEN_DIR)) == {"stray.bin"}
    assert (book / GEN_DIR / "stray.bin").read_bytes() == b"stray"
    assert not os.path.lexists(book / MANIFEST_TMP)
    assert any(str(book / GEN_DIR) in m for m in _errors(caplog)), _errors(caplog)
