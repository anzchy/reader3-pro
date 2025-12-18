from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    model: str
    finish_reason: str
    token_count: Optional[int] = None

