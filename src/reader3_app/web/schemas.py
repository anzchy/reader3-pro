"""跨 router 共用的请求／响应模型。

拆自 `web/server.py`（011 WI-4）。**字段一个没改**——ADR-0011 说 Phase 2 不得改变
任何响应形状，这个文件是那条约束最容易被无声违反的地方，所以它只做搬家。

为什么单独一个文件而不是塞进 `routers/ai/`：`AIMessage` 同时被 `ai/chat.py`（请求体
里的 conversation_history）和 `server` 里留下的 `_conversation_id_from_history` /
`_save_conversation_snapshot` 用；塞进任何一个 router 都会让别的 router 去 import 它，
router 之间就有了横向依赖——那正是 011 §5「不许拿 utils.py 当垃圾桶」要防的形状的近亲。

**这些模型不是打桩接缝**（不在 `test_server_patch_seam_ownership.py` 的 OWNERSHIP 名单里），
所以直接 `from ..schemas import AIMessage` 是对的，不需要走 `_server.`。
`server.py` 反向从这里 import 并保留同名，`server.AIMessage` 仍然存在且是同一个类对象。
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AIMessage(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str
    conversation_id: Optional[str] = None
    metadata: Optional[dict] = None


class AISummaryRequest(BaseModel):
    provider: str
    model: Optional[str] = None
    max_tokens: int = 2000


class AIQuestionRequest(BaseModel):
    question: str
    provider: str
    model: Optional[str] = None
    conversation_history: list[AIMessage] = Field(default_factory=list)
    rag_k: int = 5
    max_tokens: int = 1000


class AIRagRequest(BaseModel):
    book_uuid: str
    query: str
    k: int = 5
    min_similarity: float = 0.5
