from __future__ import annotations

import pytest

from synapse.runtime.pipeline import AsyncEventPipeline, WorkItem, WorkKind


@pytest.mark.asyncio
async def test_pipeline_processes_work_items() -> None:
    seen: list[str] = []
    pipeline = AsyncEventPipeline(max_size=10, concurrency=1, retry_limit=0)

    async def handler(item: WorkItem) -> None:
        seen.append(str(item.payload["value"]))

    pipeline.register(WorkKind.NOOP, handler)
    await pipeline.start()
    await pipeline.enqueue(WorkItem(kind=WorkKind.NOOP, payload={"value": "ok"}))
    await pipeline.queue.join()
    await pipeline.stop()

    assert seen == ["ok"]
    assert pipeline.health().processed == 1
