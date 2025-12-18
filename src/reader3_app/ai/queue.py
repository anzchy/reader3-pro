from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Awaitable, Callable, Deque, Dict, Optional, TypeVar

from fastapi import HTTPException, Request

logger = logging.getLogger("reader3.ai.queue")

T = TypeVar("T")


@dataclass
class _QueueItem:
    ready: asyncio.Event
    enqueued_at: float
    request_label: str


@dataclass(frozen=True)
class QueueLease:
    key: str
    item: _QueueItem
    queue: "_PerKeyQueue"
    deadline: float
    request_label: str


class _PerKeyQueue:
    def __init__(self, *, max_pending: int) -> None:
        self._lock = asyncio.Lock()
        self._queue: Deque[_QueueItem] = deque()
        self._active = False
        self._max_pending = max_pending

    async def enter(self, *, request: Optional[Request], request_label: str, timeout_s: float) -> _QueueItem:
        item = _QueueItem(ready=asyncio.Event(), enqueued_at=time.monotonic(), request_label=request_label)
        deadline = time.monotonic() + max(0.1, timeout_s)

        async with self._lock:
            pending_existing = max(0, len(self._queue) - (1 if self._active else 0))
            if pending_existing >= self._max_pending:
                raise HTTPException(status_code=429, detail="Too many pending AI requests. Please try again.")

            self._queue.append(item)
            if not self._active and self._queue[0] is item:
                self._active = True
                item.ready.set()

        try:
            await self._wait_turn(item, request=request, deadline=deadline)
        except Exception:
            await self._remove(item)
            raise

        return item

    async def exit(self, item: _QueueItem) -> None:
        async with self._lock:
            if not self._queue:
                self._active = False
                return
            if self._queue[0] is item:
                self._queue.popleft()
            else:
                try:
                    self._queue.remove(item)
                except ValueError:
                    pass
            if self._queue:
                self._queue[0].ready.set()
                self._active = True
            else:
                self._active = False

    async def _remove(self, item: _QueueItem) -> None:
        async with self._lock:
            if self._queue and self._queue[0] is item:
                self._queue.popleft()
                if self._queue:
                    self._queue[0].ready.set()
                    self._active = True
                else:
                    self._active = False
                return
            try:
                self._queue.remove(item)
            except ValueError:
                pass

    async def _wait_turn(self, item: _QueueItem, *, request: Optional[Request], deadline: float) -> None:
        while True:
            if item.ready.is_set():
                return

            if request is not None and await request.is_disconnected():
                raise asyncio.CancelledError("Client disconnected while waiting in queue")

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Timed out waiting in AI request queue")

            try:
                await asyncio.wait_for(item.ready.wait(), timeout=min(0.5, remaining))
            except asyncio.TimeoutError:
                continue


class AIRequestQueueManager:
    def __init__(self, *, max_pending: int = 10) -> None:
        self._queues: Dict[str, _PerKeyQueue] = {}
        self._lock = asyncio.Lock()
        self._max_pending = max_pending

    async def run(
        self,
        key: str,
        *,
        request: Optional[Request],
        timeout_s: float,
        request_label: str,
        fn: Callable[[], Awaitable[T]],
    ) -> T:
        q = await self._get_queue(key)
        try:
            item = await q.enter(request=request, request_label=request_label, timeout_s=timeout_s)
        except TimeoutError as e:
            logger.warning("queue wait timeout key=%s label=%s", key, request_label)
            raise HTTPException(status_code=504, detail="AI request timed out") from e

        deadline = item.enqueued_at + max(0.1, float(timeout_s))
        task = asyncio.create_task(fn())
        try:
            while True:
                now = time.monotonic()
                if now >= deadline:
                    task.cancel()
                    logger.warning("timeout key=%s label=%s", key, request_label)
                    raise HTTPException(status_code=504, detail="AI request timed out")

                if request is not None and await request.is_disconnected():
                    task.cancel()
                    logger.info("client disconnected key=%s label=%s", key, request_label)
                    raise asyncio.CancelledError("Client disconnected")

                done, _pending = await asyncio.wait({task}, timeout=min(0.25, max(0.0, deadline - now)))
                if task in done:
                    return task.result()
        except asyncio.CancelledError:
            logger.info("cancelled key=%s label=%s", key, request_label)
            raise
        finally:
            if not task.done():
                task.cancel()
            await q.exit(item)

    async def acquire(
        self,
        key: str,
        *,
        request: Optional[Request],
        timeout_s: float,
        request_label: str,
    ) -> QueueLease:
        q = await self._get_queue(key)
        try:
            item = await q.enter(request=request, request_label=request_label, timeout_s=timeout_s)
        except TimeoutError as e:
            logger.warning("queue wait timeout key=%s label=%s", key, request_label)
            raise HTTPException(status_code=504, detail="AI request timed out") from e
        deadline = item.enqueued_at + max(0.1, float(timeout_s))
        return QueueLease(key=key, item=item, queue=q, deadline=deadline, request_label=request_label)

    async def release(self, lease: QueueLease) -> None:
        await lease.queue.exit(lease.item)

    async def _get_queue(self, key: str) -> _PerKeyQueue:
        async with self._lock:
            q = self._queues.get(key)
            if q is None:
                q = _PerKeyQueue(max_pending=self._max_pending)
                self._queues[key] = q
            return q
