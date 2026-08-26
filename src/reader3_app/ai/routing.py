from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from ..reader3 import Book


# CJK-ish code point ranges, including the extension planes. A character in one of
# these is worth far more tokens per character than Latin text is, and this is a
# Chinese-first reader -- getting it wrong is not a rounding error, it is a factor
# of 2-4 on every budgeting decision below.
_CJK_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x2E80, 0x2EFF),  # CJK Radicals Supplement
    (0x3000, 0x303F),  # CJK Symbols and Punctuation (，。「」……)
    (0x3040, 0x30FF),  # Hiragana + Katakana
    (0x3100, 0x312F),  # Bopomofo
    (0x3130, 0x318F),  # Hangul Compatibility Jamo
    (0x31C0, 0x31EF),  # CJK Strokes
    (0x3200, 0x32FF),  # Enclosed CJK Letters and Months
    (0x3400, 0x4DBF),  # Extension A
    (0x4E00, 0x9FFF),  # Unified Ideographs
    (0xAC00, 0xD7AF),  # Hangul Syllables
    (0xF900, 0xFAFF),  # Compatibility Ideographs
    (0xFE30, 0xFE4F),  # CJK Compatibility Forms
    (0xFF00, 0xFF60),  # Fullwidth Forms
    (0x20000, 0x2A6DF),  # Extension B
    (0x2A700, 0x2EBEF),  # Extensions C-F
    (0x2F800, 0x2FA1F),  # Compatibility Ideographs Supplement
    (0x30000, 0x3134F),  # Extension G
    (0x31350, 0x323AF),  # Extension H
)

# Chars per token, by class. Deliberately not a real tokenizer (constitution #2),
# and a real tokenizer would not help anyway: every provider splits differently,
# so the useful property here is "conservative and cheap", not "exact".
_CJK_CHARS_PER_TOKEN = 1.5
_OTHER_CHARS_PER_TOKEN = 4.0


# Counting per character in Python costs ~0.9s on a million-character book, and this
# runs twice per AI request (stats, then context assembly). The same count through a
# compiled character class stays in C.
_CJK_RE = re.compile(
    "[" + "".join(f"\\U{lo:08x}-\\U{hi:08x}" for lo, hi in _CJK_RANGES) + "]"
)


def estimate_tokens(text: str) -> int:
    """Class-segmented heuristic (no tokenizer dependency).

    CJK runs at ~1.5 chars/token, everything else at ~4. The old flat ``len // 4``
    under-counted a Chinese book by 2-4x, which is exactly the direction that turns
    a routing decision into a provider-side ``prompt is too long``.
    """
    t = str(text or "")
    if not t:
        return 1
    cjk = len(_CJK_RE.findall(t))
    other = len(t) - cjk
    return max(1, int(cjk / _CJK_CHARS_PER_TOKEN + other / _OTHER_CHARS_PER_TOKEN))


def _parse_token_count_from_model(model: str) -> Optional[int]:
    m = (model or "").strip().lower()
    if not m:
        return None
    # Common patterns:
    # - "...-1m" or "...-2m"
    # - "...128k" / "...32k"
    # - "...:32k" (some tags)
    m1 = re.search(r"(^|[^0-9])([12])m($|[^0-9])", m)
    if m1:
        return int(m1.group(2)) * 1_000_000
    m2 = re.search(r"(^|[^0-9])(\d{2,3})k($|[^0-9])", m)
    if m2:
        return int(m2.group(2)) * 1000
    return None


def provider_context_window(provider_name: str, model_name: str) -> int:
    provider = (provider_name or "").strip().lower()
    model = (model_name or "").strip().lower()

    parsed = _parse_token_count_from_model(model)
    if parsed:
        return parsed

    # Conservative defaults if the model name doesn't encode context window.
    if provider == "gemini":
        if "gemini-1.5-pro" in model or "gemini-1.5" in model:
            return 2_000_000
        return 1_000_000
    if provider == "anthropic":
        # Production Claude models are 200K. The 1M window is a gated beta on specific
        # Sonnet builds, and reaching it requires the model name to say so (handled by
        # _parse_token_count_from_model above, e.g. "...-1m").
        # Default DOWN: there is no context-length fallback anywhere in this codebase.
        # Over-shooting here does not degrade to RAG excerpts, it becomes a hard 400
        # "prompt is too long" from the provider with nothing to catch it.
        return 200_000
    if provider in ("openai", "openrouter"):
        # Many OpenAI-ish models are 128k-class; keep conservative.
        return 128_000
    if provider == "ollama":
        # Local models vary a lot; keep conservative.
        return 8192
    return 128_000


@dataclass(frozen=True)
class RoutingDecision:
    mode: str  # "full_book" | "multi_chapter" | "rag"
    provider_context_window: int
    book_tokens: int
    max_chapter_tokens: int
    budget_tokens: int


def book_token_stats(book: Book) -> Tuple[int, int]:
    # Sum per chapter rather than estimating one joined mega-string: segmented
    # estimation only means anything if the segments are estimated separately.
    book_tokens = 0
    max_chapter = 0
    for ch in getattr(book, "spine", []) or []:
        txt = str(getattr(ch, "text", "") or "")
        if txt:
            t = estimate_tokens(txt)
            book_tokens += t
            max_chapter = max(max_chapter, t)
    return book_tokens, max_chapter


def choose_routing(
    *,
    provider_ctx_window: int,
    book_tokens: int,
    max_chapter_tokens: int,
) -> RoutingDecision:
    ctx = max(1, int(provider_ctx_window))
    if book_tokens and book_tokens < int(ctx * 0.5):
        return RoutingDecision(
            mode="full_book",
            provider_context_window=ctx,
            book_tokens=book_tokens,
            max_chapter_tokens=max_chapter_tokens,
            budget_tokens=int(ctx * 0.5),
        )
    if max_chapter_tokens and max_chapter_tokens < int(ctx * 0.3):
        return RoutingDecision(
            mode="multi_chapter",
            provider_context_window=ctx,
            book_tokens=book_tokens,
            max_chapter_tokens=max_chapter_tokens,
            budget_tokens=int(ctx * 0.3),
        )
    return RoutingDecision(
        mode="rag",
        provider_context_window=ctx,
        book_tokens=book_tokens,
        max_chapter_tokens=max_chapter_tokens,
        budget_tokens=0,
    )


def _chapter_title(book: Book, chapter_order: int) -> str:
    spine = getattr(book, "spine", []) or []
    if chapter_order < 0 or chapter_order >= len(spine):
        return f"Section {chapter_order + 1}"
    return str(getattr(spine[chapter_order], "title", "") or f"Section {chapter_order + 1}")


def build_full_book_context(book: Book, *, budget_tokens: int) -> str:
    # Include chapters until token budget.
    out: List[str] = []
    used = 0
    spine = getattr(book, "spine", []) or []
    for i, ch in enumerate(spine):
        txt = str(getattr(ch, "text", "") or "")
        if not txt:
            continue
        t = estimate_tokens(txt)
        if used and used + t > budget_tokens:
            break
        out.append(f"[{i + 1}] {_chapter_title(book, i)}\n{txt}")
        used += t
    return "\n\n".join(out).strip()


def build_multi_chapter_context(
    book: Book,
    *,
    chapter_orders: Sequence[int],
    budget_tokens: int,
) -> Tuple[str, List[int]]:
    out: List[str] = []
    used = 0
    used_chapters: List[int] = []
    for order in chapter_orders:
        txt = ""
        spine = getattr(book, "spine", []) or []
        if 0 <= int(order) < len(spine):
            txt = str(getattr(spine[int(order)], "text", "") or "")
        if not txt:
            continue
        t = estimate_tokens(txt)
        if used and used + t > budget_tokens:
            break
        out.append(f"[{int(order) + 1}] {_chapter_title(book, int(order))}\n{txt}")
        used += t
        used_chapters.append(int(order))
    return "\n\n".join(out).strip(), used_chapters


def unique_chapter_orders_from_passages(passages: Iterable[dict], *, limit: int = 6) -> List[int]:
    seen = set()
    out: List[int] = []
    for p in passages or []:
        try:
            order = int(p.get("chapter_order"))  # type: ignore[call-arg]
        except Exception:  # noqa: BLE001 - 第 3 档：跳过一条 chapter_order 形状不对的检索结果，只影响这次上下文里少一章；类型待收窄为 (TypeError, ValueError)
            continue
        if order in seen:
            continue
        seen.add(order)
        out.append(order)
        if len(out) >= max(1, int(limit)):
            break
    return out
