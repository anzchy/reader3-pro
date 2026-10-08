from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional, cast
from uuid import UUID, uuid4, uuid5


AnnotationType = Literal["marker", "wavy", "underline", "note"]
MarkerColor = Literal["yellow", "green", "pink", "blue"]
#: 一条标注在「当前书指纹」下的解析状态（012 WI-2b.1，ADR-0019）。
#: resolved / ambiguous / unmatched 由 :func:`match_resolution` 判出；accepted 只能由
#: 用户处置（accept_binding）写入，匹配器永远不会给出它。
Resolution = Literal["resolved", "ambiguous", "unmatched", "accepted"]
RESOLUTIONS: frozenset[str] = frozenset({"resolved", "ambiguous", "unmatched", "accepted"})

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

    # 012 WI-2b.1 (ADR-0019): additive, every default a constant -- annotations_version()
    # hashes to_dict(), so a synthesized default would move the ETag on every load.
    resolution: Resolution = "resolved"
    bound_fingerprint: Optional[str] = None
    evaluated_fingerprint: Optional[str] = None
    chapter_href: str = ""

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
            "resolution": self.resolution,
            "bound_fingerprint": self.bound_fingerprint,
            "evaluated_fingerprint": self.evaluated_fingerprint,
            "chapter_href": self.chapter_href,
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

        012 WI-2b.1 的四个新字段（D-5，ADR-0019）：坏值一律**确定地**降级，绝不抛、
        绝不丢记录。

        - `resolution` 缺失或为 `null` → `"resolved"`（旧记录都是在当时那份正文上
          建的）；不在四值集合里的任何值（含大小写不同、非 str）→ `"unmatched"`——
          坏值必须挡住指纹推进，而不是放行。
        - `bound_fingerprint` / `evaluated_fingerprint` 非 str → `None`。
        - `chapter_href` 非 str → `""`。
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
            resolution=_coerce_resolution(data.get("resolution")),
            bound_fingerprint=_str_or_none(data.get("bound_fingerprint")),
            evaluated_fingerprint=_str_or_none(data.get("evaluated_fingerprint")),
            chapter_href=_str_or_empty(data.get("chapter_href")),
        )


def _coerce_resolution(value: object) -> Resolution:
    if value is None:
        return "resolved"
    if isinstance(value, str) and value in RESOLUTIONS:
        return cast(Resolution, value)
    return "unmatched"


def _str_or_none(value: object) -> Optional[str]:
    return value if isinstance(value, str) else None


def _str_or_empty(value: object) -> str:
    return value if isinstance(value, str) else ""


def _strip_ws(text: str) -> str:
    """去掉全部 ``str.isspace`` 字符（M-1）。不是 ``_collapse_ws``：那个折成一个空格。"""
    return "".join(text.split())


def match_resolution(chapter_text: str, prefix: str, quote: str, suffix: str) -> Resolution:
    """在一章正文里严格判定一条标注的位置（012 WI-2b.1，Q15 M-1 … M-7，ADR-0019）。

    - M-1 两侧都去掉全部空白（``"".join(s.split())``），DOM 文本与抽取文本的空白差异
      因此不影响判定；零宽空格不是空白，照原样参与比较。
    - M-2 needle = prefix + quote + suffix，**先拼接再去空白**。
    - M-3 去空白后 quote 为空 → ``"unmatched"``。
    - M-4 用逐位前进的 ``find`` 数**可重叠**的出现次数（不是 ``str.count``），数到 2 即停。
    - M-5 0 → ``"unmatched"``，1 → ``"resolved"``，≥2 → ``"ambiguous"``。
    - M-6 prefix 与 suffix 都空时 needle 就是 quote，同样要求恰好一次。
    - M-7 严格：needle 一次都没有时**不**退回只找 quote。

    纯函数：无副作用、无缓存。永远不会返回 ``"accepted"``。
    """
    if not _strip_ws(quote):
        return "unmatched"
    haystack = _strip_ws(chapter_text)
    needle = _strip_ws(prefix + quote + suffix)
    count = 0
    start = 0
    while count < 2:
        found = haystack.find(needle, start)
        if found < 0:
            break
        count += 1
        start = found + 1
    if count == 0:
        return "unmatched"
    if count == 1:
        return "resolved"
    return "ambiguous"

