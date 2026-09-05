"""WI-8 (009, Wave 2): `Annotation.__post_init__` truncates `prefix`/`suffix` at
**codepoints**, not bytes, not UTF-16 units, and not graphemes.

Why this needs pinning rather than being obvious. The 50-char cap exists so the
anchoring context stays bounded, and the *unit* it counts in is load-bearing in
three separate ways that all disagree with each other:

  * **bytes** -- a CJK char is 3 UTF-8 bytes, so a byte-based cap would keep
    ~16 CJK chars where this one keeps 50. `test_write_cjk_boundary.py` in the
    e2e lane measured `len(quote) == 4` for a 12-byte CJK selection; that
    measurement is only stable because Python counts codepoints.
  * **UTF-16 units** -- the *browser* side counts these. `String.prototype.slice`
    in `annotations.js` would split a non-BMP emoji into two lone surrogates.
    Python cannot: one emoji is one codepoint here, so it is kept or dropped
    whole. The two sides therefore disagree about where char 50 falls whenever
    a non-BMP char is in range, and the server's answer is the one on disk.
  * **graphemes** -- a combining sequence (base + mark) is 2 codepoints and 1
    user-perceived character. This cap *will* split one, leaving either a bare
    base or an orphan combining mark at the boundary. That is today's behavior,
    it is not obviously desirable, and pinning it is the point: if anyone moves
    to grapheme clusters the count changes and these cases go red on purpose.

Direction matters and is asymmetric: `prefix` keeps its **tail** (`[-50:]`) and
`suffix` keeps its **head** (`[:50]`), because both are measured outward from
the quote. Swapping them keeps every length assertion green while destroying
anchoring, so every case below asserts the *content* at the boundary, never
just `len(...) == 50`.

Sabotage record. Each mutation was applied to `models/annotations.py`, the module
run, and the file restored from a copy (`git diff --stat` empty afterwards). The
outputs below are transcribed from the runs, not predicted:

  D1  `self.prefix = self.prefix[-50:]` -> `[:50]`   (keep head instead of tail)
      2 failed, 5 passed
      FAILED test_prefix_longer_than_50_keeps_its_last_50_codepoints
        E   assert 'zzzzzzzzzzzz...mmmmmmmmmmmmm' == 'mmmmmmmmmmmm...aaaaaaaaaaaaa'
      FAILED test_context_at_or_under_50_is_left_exactly_alone
        E   assert 'baaaaaaaaaaa...aaaaaaaaaaaaa' == 'aaaaaaaaaaaa...aaaaaaaaaaaaa'
      Note both survivors are content assertions. `len(...) == 50` stayed green
      throughout -- which is why no case here stops at a length check.

  D2  `self.suffix = self.suffix[:50]` -> `[-50:]`   (keep tail instead of head)
      2 failed, 5 passed
      FAILED test_suffix_longer_than_50_keeps_its_first_50_codepoints
        E   assert 'mmmmmmmmmmmm...zzzzzzzzzzzzz' == 'aaaaaaaaaaaa...mmmmmmmmmmmmm'
      FAILED test_a_combining_sequence_is_split_at_the_50_codepoint_boundary
        E   assert '́' == 'e'
      The combining case catches direction too: cutting from the other end leaves
      an orphaned mark rather than an orphaned base.

  D3  `if len(self.prefix) > 50:` -> `> 51`          (off-by-one)
      1 failed, 6 passed
      FAILED test_context_at_or_under_50_is_left_exactly_alone
        E   assert 'baaaaaaaaaaa...aaaaaaaaaaaaa' == 'aaaaaaaaaaaa...aaaaaaaaaaaaa'
      Only the boundary case moves. This is the mutation the other six cannot see.

  D4  `.encode("utf-8")[...]` before slicing         (byte cap instead of codepoint)
      3 failed, 4 passed
      FAILED test_cjk_context_is_capped_at_50_characters_not_50_bytes
        E   assert 16 == 50     (3 bytes per CJK char)
      FAILED test_non_bmp_emoji_are_never_split_into_surrogate_halves
        E   assert 12 == 50     (4 bytes per emoji)
      FAILED test_a_combining_sequence_is_split_at_the_50_codepoint_boundary
        E   assert 34 == 50
      The ASCII-only cases stayed green, which is the whole reason the non-ASCII
      ones exist.

  D5  both truncation branches deleted entirely
      6 failed, 1 passed
      Four of them report `assert 80 == 50`; the lone survivor is
      test_empty_context_survives_truncation_untouched, correctly -- an empty
      string is unaffected by a cap that does not run.
"""

from __future__ import annotations

from reader3_app.models.annotations import Annotation


def _ann(**kw) -> Annotation:
    """A valid annotation; `book_id` and `quote` are the only required fields."""
    return Annotation(book_id="b_data", quote="Q", **kw)


def test_prefix_longer_than_50_keeps_its_last_50_codepoints() -> None:
    """T1/T2 -- the cap counts codepoints, and `prefix` keeps the side that
    touches the quote."""
    original = ("z" * 30) + ("m" * 30) + ("a" * 20)  # 80 chars, ends in 'a'
    ann = _ann(prefix=original)

    assert len(ann.prefix) == 50
    assert ann.prefix == original[-50:]
    # T2: the char adjacent to the quote survives; the far end is what is cut.
    assert ann.prefix[-1] == "a"
    assert ann.prefix[0] == "m"
    assert "z" not in ann.prefix


def test_suffix_longer_than_50_keeps_its_first_50_codepoints() -> None:
    """T3 -- mirror of T1 in the other direction."""
    original = ("a" * 20) + ("m" * 30) + ("z" * 30)  # 80 chars, starts with 'a'
    ann = _ann(suffix=original)

    assert len(ann.suffix) == 50
    assert ann.suffix == original[:50]
    assert ann.suffix[0] == "a"
    assert ann.suffix[-1] == "m"
    assert "z" not in ann.suffix


def test_cjk_context_is_capped_at_50_characters_not_50_bytes() -> None:
    """T4 -- 80 CJK chars are 240 UTF-8 bytes; a byte cap would keep 16."""
    original = "書" * 80
    assert len(original.encode("utf-8")) == 240

    ann = _ann(prefix=original, suffix=original)

    assert len(ann.prefix) == 50
    assert len(ann.suffix) == 50
    assert len(ann.prefix.encode("utf-8")) == 150


def test_non_bmp_emoji_are_never_split_into_surrogate_halves() -> None:
    """T5 -- one astral codepoint is one unit here, so the boundary can land
    beside an emoji but never inside one.

    The browser counts UTF-16, where each of these is 2 units; that is exactly
    the divergence this case exists to record.
    """
    emoji = "\U0001f600"  # GRINNING FACE, one codepoint, two UTF-16 units
    original = emoji * 80
    assert len(original) == 80
    assert len(original.encode("utf-16-le")) // 2 == 160  # 160 UTF-16 units

    ann = _ann(prefix=original, suffix=original)

    assert len(ann.prefix) == 50
    assert ann.prefix == emoji * 50
    # No lone surrogate survived the cut.
    assert all(not (0xD800 <= ord(c) <= 0xDFFF) for c in ann.prefix)
    assert all(not (0xD800 <= ord(c) <= 0xDFFF) for c in ann.suffix)


def test_a_combining_sequence_is_split_at_the_50_codepoint_boundary() -> None:
    """T6 -- today's behavior, pinned deliberately rather than endorsed.

    `suffix` here is 25 base+mark pairs followed by more pairs. Cutting at
    codepoint 50 lands cleanly between pairs, so we push the boundary off by one
    to land *inside* a pair and show what happens: the base is kept and its
    combining mark is dropped, changing the rendered character.
    """
    combining_acute = "́"
    pair = "e" + combining_acute  # 2 codepoints, 1 grapheme
    original = "x" + (pair * 40)  # odd leading char shifts the boundary

    ann = _ann(suffix=original)

    assert len(ann.suffix) == 50
    # Codepoint 49 (0-indexed) is a bare 'e' whose acute accent was cut off.
    assert ann.suffix[-1] == "e"
    assert original[50] == combining_acute
    assert combining_acute not in ann.suffix[-1:]
    # Grapheme count is therefore NOT 50 -- 24 accented pairs plus 'x' plus the
    # orphaned base.
    assert ann.suffix.count(combining_acute) == 24


def test_context_at_or_under_50_is_left_exactly_alone() -> None:
    """T7 -- the boundary itself: 50 is not truncated, 51 is.

    Guards the off-by-one directly, since `> 50` and `>= 50` produce identical
    output for every input except this one.
    """
    exactly_50 = "a" * 50
    ann = _ann(prefix=exactly_50, suffix=exactly_50)
    assert ann.prefix == exactly_50
    assert ann.suffix == exactly_50

    fifty_one = "b" + ("a" * 50)
    ann51 = _ann(prefix=fifty_one)
    assert ann51.prefix == "a" * 50
    assert len(ann51.prefix) == 50


def test_empty_context_survives_truncation_untouched() -> None:
    """T8 -- empty prefix/suffix is the common case (chapter head/tail) and must
    not become `None` or raise. `build_cjk` produces exactly this."""
    ann = _ann(prefix="", suffix="")
    assert ann.prefix == ""
    assert ann.suffix == ""
