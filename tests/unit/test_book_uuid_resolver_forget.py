"""018 WI-5a: ``BookUuidResolver.forget_folder`` (matrix cases U-1, U-2).

``forget_folder`` is looked up with ``getattr`` at call time so the file collects
before it exists.
"""

from __future__ import annotations

from delete_world import U, V, make_book, new_world, seat_resolver, server_module, tree_bytes, warm


def test_u1_forget_folder_drops_both_directions_only_for_that_folder(tmp_path):
    """U-1: forget a_data twice, then an unknown folder -> only b_data remains, no error, no disk I/O."""
    from reader3_app.ai.books import BookUuidResolver

    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U)
    make_book(w.books, "b_data", book_uuid=V)
    resolver = BookUuidResolver(str(w.books))
    warm(resolver, "a_data", U)
    warm(resolver, "b_data", V)
    before = tree_bytes(w.books)
    forget = getattr(resolver, "forget_folder")

    forget("a_data")
    forget("a_data")
    forget("never_data")

    assert resolver._folder_to_uuid == {"b_data": V}
    assert resolver._uuid_to_folder == {V: "b_data"}
    assert tree_bytes(w.books) == before


def test_u2_lookup_after_delete_raises_book_gone_and_does_not_recreate(tmp_path, monkeypatch):
    """U-2: after ``delete_book`` the seated resolver answers BookGone and does not recreate the folder."""
    from reader3_app.book_lock import BookGone

    server_module()
    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U)
    resolver = seat_resolver(monkeypatch, w.books)
    warm(resolver, "a_data", U)

    w.delete(mode=False)

    try:
        resolver.book_uuid_for_folder("a_data")
    except FileNotFoundError as exc:
        assert type(exc) is BookGone, f"expected BookGone, got {type(exc).__name__}: {exc}"
    else:
        raise AssertionError("book_uuid_for_folder answered for a deleted folder")
    assert not (w.books / "a_data").exists()
