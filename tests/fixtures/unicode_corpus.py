"""Group 2: Unicode inputs that make the offset contract observable.

The contract this corpus exists to guard (tasks/008-test-safety-net.md §3):
**Python counts offsets in Unicode code points; the DOM and JavaScript count
them in UTF-16 code units.** For everything in the Basic Multilingual Plane the
two numbers are equal, which is why the divergence survives so long unnoticed --
every ASCII test agrees. Only astral-plane characters (emoji, non-BMP letters)
separate them, and Phase 4 plans to feed server-computed ``ranges`` straight
into a browser ``Range``. ``ASTRAL_HAYSTACK`` below is the input that will fail
loudly on the day that happens, instead of silently highlighting the wrong words.

The remaining samples pin ``search_service._normalize_with_map``: casefold
expansion, script-dependent diacritic stripping, and combining marks. They are
characterisation, not specification -- several record behaviour that is
arguably wrong (see the test module).
"""

from __future__ import annotations

from typing import Tuple

# --- the code point / code unit divergence --------------------------------

#: A scientist ZWJ sequence (woman + ZWJ + microscope) before the match, so the
#: hit's code-point offset and its UTF-16 offset cannot agree. Two astral
#: characters means the gap is 2, not 1: an off-by-one fix would still be wrong.
ZWJ_SCIENTIST = "\U0001F469\u200d\U0001F52C"
ASTRAL_HAYSTACK = f"A {ZWJ_SCIENTIST} found the caf\u00e9 door"
ASTRAL_NEEDLE = "cafe"
#: Where the needle starts, counted each way. Asserted, not assumed.
ASTRAL_NEEDLE_CODE_POINT_START = 16
ASTRAL_NEEDLE_CODE_UNIT_START = 18

#: An astral character *inside* the match rather than before it, so a consumer
#: that only adjusts the start offset is still wrong about the end.
ASTRAL_INSIDE_HAYSTACK = "chapter \U0001D518nheimlich ending"
ASTRAL_INSIDE_NEEDLE = "\U0001D518nheimlich"

#: Non-BMP letter, emoji, variation selector and ZWJ, so a UTF-16 pair count of
#: 1, 1, 0 and 0 extra units respectively is exercised in one string.
MIXED_ASTRAL = f"\U0001D518 \U0001F600 \u2764\ufe0f {ZWJ_SCIENTIST}"


def code_unit_length(text: str) -> int:
    """UTF-16 code units in ``text`` -- what JavaScript's ``String.length`` returns.

    Encoding to UTF-16LE and halving is the same count a browser reports,
    without needing a browser to ask.
    """
    return len(text.encode("utf-16-le")) // 2


def code_unit_offset(text: str, code_point_offset: int) -> int:
    """Translate a Python offset into the JavaScript offset for the same position."""
    return code_unit_length(text[:code_point_offset])


def slice_by_code_units(text: str, start: int, end: int) -> str:
    """What ``text.substring(start, end)`` would return in a browser."""
    return text.encode("utf-16-le")[start * 2 : end * 2].decode("utf-16-le", "replace")


# --- normalisation forms ---------------------------------------------------

#: The same word composed and decomposed. Byte-different, visually identical.
NFC_CAFE = "caf\u00e9"
NFD_CAFE = "cafe\u0301"

#: A decomposed word inside a sentence: matching it yields a span that stops
#: *before* the combining acute, which is the anchoring failure this pins.
NFD_SENTENCE = "cafe\u0301 noir"

# --- casefold expansion ----------------------------------------------------

#: casefold lengthens: 'ß' -> 'ss'. Six characters in, seven out.
SHARP_S_WORD = "Straße"
SHARP_S_CASEFOLDED = "strasse"

#: Turkish dotted capital I. Python's own casefold gives 'i' + U+0307 (two
#: characters); the Latin path in _normalize_with_map strips the combining mark
#: first and gives one. The pair documents that the two disagree.
TURKISH_DOTTED_I_WORD = "İstanbul"
TURKISH_DOTLESS_I_WORD = "Iırmak"

#: Greek final sigma casefolds to the medial form, so an all-caps and a
#: mixed-case spelling of the same name converge -- but the accent on 'ύ' does
#: not, because diacritic stripping is Latin-only by design (FR-009).
GREEK_UPPER = "ΟΔΥΣΣΕΥΣ"
GREEK_MIXED = "Οδυσσεύς"

# --- combining marks on non-Latin bases ------------------------------------

#: Hiragana KA followed by a combining voiced sound mark: a combining character
#: on a base that is not Latin, so it must survive normalisation intact.
KANA_COMBINING = "\u304b\u3099\u3063\u3053\u3046"
KANA_PRECOMPOSED = "\u304c\u3063\u3053\u3046"

#: A heart with an emoji variation selector, and the same heart without it.
HEART_WITH_VS = "\u2764\ufe0f"
HEART_WITHOUT_VS = "\u2764"

#: Every sample that must round-trip through search unchanged in length.
BMP_ONLY_SAMPLES: Tuple[str, ...] = (
    NFC_CAFE,
    SHARP_S_WORD,
    TURKISH_DOTTED_I_WORD,
    GREEK_UPPER,
    KANA_COMBINING,
    HEART_WITH_VS,
)

#: Every sample where the two offset units diverge.
ASTRAL_SAMPLES: Tuple[str, ...] = (
    ASTRAL_HAYSTACK,
    ASTRAL_INSIDE_HAYSTACK,
    MIXED_ASTRAL,
    ZWJ_SCIENTIST,
)
