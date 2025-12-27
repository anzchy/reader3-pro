from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4


AnnotationType = Literal["marker", "wavy", "underline", "note"]
MarkerColor = Literal["yellow", "green", "pink", "blue"]


@dataclass
class Annotation:
    id: str = field(default_factory=lambda: str(uuid4()))
    book_id: str = ""
    chapter_index: int = 0

    type: AnnotationType = "marker"
    color: Optional[MarkerColor] = "yellow"

    quote: str = ""
    prefix: str = ""
    suffix: str = ""
    position: Optional[int] = None
    cfi: Optional[str] = None

    note_text: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    orphaned: bool = False

    def __post_init__(self) -> None:
        if not self.book_id:
            raise ValueError("book_id is required")
        if self.chapter_index < 0:
            raise ValueError("chapter_index must be >= 0")
        if not self.quote:
            raise ValueError("quote is required")

        if self.type in ("marker", "note") and self.color is None:
            self.color = "yellow"
        if self.type in ("wavy", "underline"):
            self.color = None

        if len(self.prefix) > 50:
            self.prefix = self.prefix[-50:]
        if len(self.suffix) > 50:
            self.suffix = self.suffix[:50]

        if self.position is not None and self.position < 0:
            self.position = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "book_id": self.book_id,
            "chapter_index": self.chapter_index,
            "type": self.type,
            "color": self.color,
            "quote": self.quote,
            "prefix": self.prefix,
            "suffix": self.suffix,
            "position": self.position,
            "cfi": self.cfi,
            "note_text": self.note_text,
            "created_at": self.created_at,
            "orphaned": self.orphaned,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Annotation:
        return cls(
            id=str(data.get("id") or str(uuid4())),
            book_id=str(data.get("book_id") or ""),
            chapter_index=int(data.get("chapter_index") or 0),
            type=data.get("type") or "marker",
            color=data.get("color"),
            quote=str(data.get("quote") or ""),
            prefix=str(data.get("prefix") or ""),
            suffix=str(data.get("suffix") or ""),
            position=data.get("position"),
            cfi=data.get("cfi"),
            note_text=data.get("note_text"),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            orphaned=bool(data.get("orphaned") or False),
        )
