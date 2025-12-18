from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from ..reader3 import Book


def estimate_tokens(text: str) -> int:
    # Lightweight heuristic (no tokenizer dependency):
    # English-ish: ~4 chars/token; CJK tends to be closer to ~1-2 chars/token,
    # but this approximation is good enough for routing.
    t = str(text or "")
    return max(1, len(t) // 4)


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
        # Claude model families can be large-context; use the "long-context" default.
        # If the provider/model can't handle it, server-side fallback will route to RAG excerpts.
        return 1_000_000
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
    book_text_parts: List[str] = []
    max_chapter = 0
    for ch in getattr(book, "spine", []) or []:
        txt = str(getattr(ch, "text", "") or "")
        if txt:
            book_text_parts.append(txt)
            max_chapter = max(max_chapter, estimate_tokens(txt))
    book_tokens = estimate_tokens("\n\n".join(book_text_parts)) if book_text_parts else 0
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
        except Exception:
            continue
        if order in seen:
            continue
        seen.add(order)
        out.append(order)
        if len(out) >= max(1, int(limit)):
            break
    return out
