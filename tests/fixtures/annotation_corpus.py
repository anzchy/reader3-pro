"""Group 3: the chapter texts that make annotation anchoring hard.

An annotation is stored as ``quote`` plus 50 characters of ``prefix`` and
``suffix`` -- never as a DOM path -- so re-anchoring it is a text search, and
every way a text search can go wrong is a way a user's highlight can land on the
wrong words or vanish. The cases here are the ones that actually do it:

    split_nodes       the quote crosses an inline element boundary
    cross_paragraph   the quote crosses a block boundary
    repeated          the quote occurs three times; only context disambiguates
    overlapping       two annotations whose ranges intersect
    stacked           four annotation types over the identical range
    long_context      prefix/suffix longer than the 50-character field
    stale_text        the chapter was re-processed and the quote is gone
    stale_spine       the spine was reordered and chapter_index now points elsewhere

``text`` is what ``reader3.extract_plain_text`` must produce from ``html``. It
is spelled out rather than computed because the whole point of these cases is
where the character offsets fall: if whitespace collapsing ever changes, every
offset in this file moves and the test must say so rather than recompute
agreement with itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

BOOK_ID = "anchor_fixture_data"


@dataclass(frozen=True)
class AnchorCase:
    key: str
    html: str  # inner HTML of the chapter body
    text: str  # the plain text reader3 extracts from it
    annotations: Tuple[Dict[str, object], ...] = ()
    note: str = ""


def _ann(
    *,
    quote: str,
    prefix: str = "",
    suffix: str = "",
    ann_id: str = "",
    ann_type: str = "marker",
    color: str = "yellow",
    chapter_index: int = 0,
) -> Dict[str, object]:
    return {
        "id": ann_id or f"ann-{quote[:8]}-{ann_type}",
        "book_id": BOOK_ID,
        "chapter_index": chapter_index,
        "type": ann_type,
        "color": color,
        "quote": quote,
        "prefix": prefix,
        "suffix": suffix,
    }


# --- the quote crosses an inline element boundary --------------------------

SPLIT_NODES = AnchorCase(
    key="split_nodes",
    html="<p>She called it the <em>living</em> room, mostly.</p>",
    text="She called it the living room, mostly.",
    annotations=(_ann(quote="the living room", prefix="She called it ", suffix=", mostly."),),
    note="'the living room' exists in no single DOM text node.",
)

# --- the quote crosses a block boundary ------------------------------------

CROSS_PARAGRAPH = AnchorCase(
    key="cross_paragraph",
    html="<p>The door was open.</p><p>Nobody was inside.</p>",
    text="The door was open. Nobody was inside.",
    annotations=(_ann(quote="open. Nobody", prefix="The door was ", suffix=" was inside."),),
    note="Spans two <p> elements, so a Range built inside one of them cannot hold it.",
)

# --- the same quote three times, disambiguated only by context -------------

REPEATED_QUOTE = "The bell rang."
REPEATED_OCCURRENCES = 3

REPEATED = AnchorCase(
    key="repeated",
    html=(
        "<p>The bell rang. It was late. The bell rang. It was cold. "
        "The bell rang. It was over.</p>"
    ),
    text="The bell rang. It was late. The bell rang. It was cold. The bell rang. It was over.",
    annotations=(
        _ann(
            quote=REPEATED_QUOTE,
            prefix="It was late. ",
            suffix=" It was cold.",
            ann_id="ann-second-bell",
        ),
    ),
    note="Only the prefix picks the second occurrence out of three identical ones.",
)

# --- two annotations whose ranges intersect --------------------------------

OVERLAPPING = AnchorCase(
    key="overlapping",
    html="<p>The quick brown fox jumps over the lazy dog.</p>",
    text="The quick brown fox jumps over the lazy dog.",
    annotations=(
        _ann(quote="quick brown fox", prefix="The ", suffix=" jumps", ann_id="ann-left"),
        _ann(
            quote="brown fox jumps",
            prefix="quick ",
            suffix=" over",
            ann_id="ann-right",
            ann_type="underline",
            color="green",
        ),
    ),
    note="'brown fox' belongs to both ranges, so the renderer must nest, not replace.",
)

# --- four types stacked on one identical range -----------------------------

STACKED_QUOTE = "lazy dog"

STACKED = AnchorCase(
    key="stacked",
    html="<p>The quick brown fox jumps over the lazy dog.</p>",
    text="The quick brown fox jumps over the lazy dog.",
    annotations=tuple(
        _ann(
            quote=STACKED_QUOTE,
            prefix="over the ",
            suffix=".",
            ann_id=f"ann-stacked-{t}",
            ann_type=t,
            color=c,
        )
        for t, c in (("marker", "yellow"), ("underline", "green"), ("wavy", "pink"), ("note", "blue"))
    ),
    note="Identical span, four types: the four must all survive a save/load round trip.",
)

# --- context longer than the 50-character field ----------------------------

LONG_PREFIX = "".join(f"{i % 10}" for i in range(80))
LONG_SUFFIX = "".join(f"{(i + 3) % 10}" for i in range(80))

LONG_CONTEXT = AnchorCase(
    key="long_context",
    html=f"<p>{LONG_PREFIX}MIDDLE{LONG_SUFFIX}</p>",
    text=f"{LONG_PREFIX}MIDDLE{LONG_SUFFIX}",
    annotations=(_ann(quote="MIDDLE", prefix=LONG_PREFIX, suffix=LONG_SUFFIX, ann_id="ann-long"),),
    note=(
        "Annotation truncates to 50 characters. Which 50 is the whole point: the "
        "half adjacent to the quote is the half that disambiguates."
    ),
)

# --- stale: the chapter text changed under a stored annotation -------------

STALE_TEXT_BEFORE = REPEATED
STALE_TEXT_AFTER = AnchorCase(
    key="stale_text_after",
    html=(
        "<p>The bell tolled. It was late. The bell tolled. It was cold. "
        "The bell tolled. It was over.</p>"
    ),
    text=(
        "The bell tolled. It was late. The bell tolled. It was cold. "
        "The bell tolled. It was over."
    ),
    annotations=REPEATED.annotations,
    note="Same annotations, re-processed chapter: every quote is now unfindable.",
)

# --- stale: the spine was reordered under a stored chapter_index -----------

#: Two spine orders for one book. The annotation stores ``chapter_index=1``,
#: which names "Beta" before the reorder and "Alpha" after it -- an annotation
#: that silently moves to a different chapter rather than becoming orphaned,
#: which is the worse of the two failures because nothing looks wrong.
SPINE_ORDER_BEFORE: Tuple[str, ...] = ("Alpha chapter body.", "Beta chapter body.", "Gamma chapter body.")
SPINE_ORDER_AFTER: Tuple[str, ...] = ("Gamma chapter body.", "Alpha chapter body.", "Beta chapter body.")

STALE_SPINE_ANNOTATION: Dict[str, object] = _ann(
    quote="Beta chapter body.",
    ann_id="ann-stale-spine",
    chapter_index=1,
)

ALL_CASES: Tuple[AnchorCase, ...] = (
    SPLIT_NODES,
    CROSS_PARAGRAPH,
    REPEATED,
    OVERLAPPING,
    STACKED,
    LONG_CONTEXT,
    STALE_TEXT_AFTER,
)

BY_KEY: Dict[str, AnchorCase] = {c.key: c for c in ALL_CASES}


def occurrences(haystack: str, needle: str) -> int:
    """Non-overlapping occurrence count, the way a naive re-anchor would search."""
    return haystack.count(needle)


def span_of(case: AnchorCase, quote: str, *, occurrence: int = 0) -> Tuple[int, int]:
    """Character span of the ``occurrence``-th ``quote`` in ``case.text``."""
    start = -1
    for _ in range(occurrence + 1):
        start = case.text.index(quote, start + 1)
    return start, start + len(quote)


def build_chapter_epub(path, cases: Tuple[AnchorCase, ...] = ALL_CASES):
    """One EPUB whose chapters are these cases, in order, for end-to-end use."""
    from epub_zip import Doc, EpubSpec, NavPoint, write_raw_epub

    docs = tuple(
        Doc(f"c{i}", f"text/{c.key}.xhtml", c.html, title=c.key)
        for i, c in enumerate(cases, start=1)
    )
    nav = tuple(NavPoint(c.key, f"text/{c.key}.xhtml") for c in cases)
    return write_raw_epub(
        path,
        EpubSpec(
            title="Anchoring Corpus",
            identifier="urn:uuid:reader3-anchors",
            docs=docs,
            nav=nav,
        ),
    )
