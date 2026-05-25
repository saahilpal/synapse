from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic
from uuid import uuid4

from synapse.observability import get_logger


class WorkKind(StrEnum):
    INDEX_REPOSITORY = "index_repository"
    CREATE_SNAPSHOT = "create_snapshot"
    DETECT_DRIFT = "detect_drift"
    NOOP = "noop"


@dataclass(frozen=True)
class WorkItem:
    kind: WorkKind
    payload: dict[str, object] = field(default_factory=dict)
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    attempts: int = 0
    max_attempts: int = 3


@dataclass(order=True, frozen=True)
class PrioritizedWork:
    priority: int
    sequence: int
    item: WorkItem = field(compare=False)


@dataclass(frozen=True)
class QueueHealth:
    queued: int
    processed: int
    failed: int
    retried: int
    running_workers: int


WorkHandler = Callable[[WorkItem], Awaitable[None]]


class AsyncEventPipeline:
    """Bounded async work queue with retry and cancellation-safe workers."""

    def __init__(
        self,
        *,
        max_size: int,
        concurrency: int,
        retry_limit: int,
    ) -> None:
        self.queue: asyncio.PriorityQueue[PrioritizedWork] = asyncio.PriorityQueue(maxsize=max_size)
        self.concurrency = concurrency
        self.retry_limit = retry_limit
        self.handlers: dict[WorkKind, WorkHandler] = {}
        self._sequence = 0
        self._processed = 0
        self._failed = 0
        self._retried = 0
        self._tasks: list[asyncio.Task[None]] = []
        self._stopping = asyncio.Event()
        self.logger = get_logger("pipeline")

    def register(self, kind: WorkKind, handler: WorkHandler) -> None:
        self.handlers[kind] = handler

    async def enqueue(self, item: WorkItem, *, priority: int = 100) -> None:
        self._sequence += 1
        await self.queue.put(PrioritizedWork(priority=priority, sequence=self._sequence, item=item))

    async def start(self) -> None:
        self._stopping.clear()
        self._tasks = [
            asyncio.create_task(self._worker(worker_id), name=f"synapse-worker-{worker_id}")
            for worker_id in range(self.concurrency)
        ]

    async def stop(self) -> None:
        self._stopping.set()
        await self.queue.join()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    def health(self) -> QueueHealth:
        return QueueHealth(
            queued=self.queue.qsize(),
            processed=self._processed,
            failed=self._failed,
            retried=self._retried,
            running_workers=sum(1 for task in self._tasks if not task.done()),
        )

    async def _worker(self, worker_id: int) -> None:
        while not self._stopping.is_set():
            try:
                prioritized = await self.queue.get()
            except asyncio.CancelledError:
                break
            start = monotonic()
            item = prioritized.item
            try:
                handler = self.handlers[item.kind]
                await handler(item)
            except asyncio.CancelledError:
                self.queue.task_done()
                raise
            except Exception as exc:
                self._failed += 1
                if item.attempts < min(item.max_attempts, self.retry_limit):
                    self._retried += 1
                    retry = WorkItem(
                        kind=item.kind,
                        payload=item.payload,
                        correlation_id=item.correlation_id,
                        attempts=item.attempts + 1,
                        max_attempts=item.max_attempts,
                    )
                    await self.enqueue(retry, priority=prioritized.priority + 10)
                    self.logger.warning(
                        "work_retried",
                        operation="worker",
                        worker_id=worker_id,
                        work_kind=item.kind.value,
                        correlation_id=item.correlation_id,
                        error=str(exc),
                    )
                else:
                    self.logger.error(
                        "work_failed",
                        operation="worker",
                        worker_id=worker_id,
                        work_kind=item.kind.value,
                        correlation_id=item.correlation_id,
                        error=str(exc),
                    )
            else:
                self._processed += 1
                latency_ms = (monotonic() - start) * 1000
                self.logger.info(
                    "work_processed",
                    operation="worker",
                    worker_id=worker_id,
                    work_kind=item.kind.value,
                    correlation_id=item.correlation_id,
                    latency=latency_ms,
                )
            finally:
                self.queue.task_done()
