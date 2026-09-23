from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID, uuid4, uuid5


AnnotationType = Literal["marker", "wavy", "underline", "note"]
MarkerColor = Literal["yellow", "green", "pink", "blue"]

#: 给「盘上那条记录没有 id」合成 id 用的命名空间（017 WI-3，审计 #6）。
#: 它必须是一个**写死的常量**：换一个值就等于把所有无 id 旧记录的身份换一遍，
#: 而它们的 id 正是 ETag 的一部分。
_LEGACY_ID_NAMESPACE = UUID("6f3a1c2e-9b47-5d18-8e60-0a5b2d7f4c91")


def _synthesized_legacy_id(data: dict, index: Optional[int]) -> str:
    """为一条缺 id 的旧记录算一个**确定**的 id。

    确定性是全部的意义所在：`notes_service.annotations_version()` 把 id 算进 ETag，
    所以一个每次 load 都重掷的 `uuid4()` 会让这本书的 ETag 每读一次变一次，客户端
    的 `If-Match` 永远对不上，写入永远 409（审计 #6）。

    种子里带 `index` 而不只带内容：两条逐字节相同的无 id 记录若拿到同一个 id，
    `delete_annotation_and_version` 的 `a.id != note_id` 会把两条一起删掉。
    """
    payload = {k: v for k, v in data.items() if k != "id"}
    seed = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )
    return str(uuid5(_LEGACY_ID_NAMESPACE, f"{index}:{seed}"))



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
        if self.type in ("wavy", "underline") and self.color is None:
            self.color = "yellow"

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
    def from_dict(cls, data: dict, *, index: Optional[int] = None) -> Annotation:
        """从盘上的一条记录还原一个 Annotation。

        **这是磁盘那一侧唯一的反序列化入口**，也是唯一一处会碰到「字段缺了」的地方——
        新建走的是构造器，`default_factory` 一个字段都不会缺。所以「缺了怎么办」的规矩
        只写在这里，而规矩只有一条：**补出来的值必须是确定的**。

        它必须确定，是因为 `notes_service.annotations_version()` 拿每条记录的
        `to_dict()` 去算 ETag。任何一个「现编一个」的兜底都会让同一个文件每读一次
        算出一个新版本，于是客户端原样送回的 `If-Match` 永远对不上，这本书再也写不
        进去，界面上只剩一个反复弹出、点什么都没用的冲突对话框（017 WI-3，审计 #6）。

        - `created_at` 缺失 → `""`。不知道就说不知道，不要补一个「刚刚」。它只作排序
          的次级键用（`routers/notes.py:125`、`:186`）。
        - `id` 缺失 → `_synthesized_legacy_id()`，见那里的说明。`index` 是这条记录在
          文件里的序号，由 `load_annotations` 传进来；不传时同一份内容只会得到一个
          身份，这对单条还原够用，对整份文件不够。

        已有的值原样保留——规范化只填空，不重写。
        """
        return cls(
            id=str(data.get("id") or _synthesized_legacy_id(data, index)),
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
            created_at=str(data.get("created_at") or ""),
            orphaned=bool(data.get("orphaned") or False),
        )
