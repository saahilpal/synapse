from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass

from synapse.config import SynapseSettings
from synapse.git import GitRepository, GitState
from synapse.observability import get_logger
from synapse.runtime.pipeline import AsyncEventPipeline, WorkItem, WorkKind
from synapse.runtime.service import SynapseRuntime


@dataclass(frozen=True)
class DaemonHealth:
    running: bool
    active_context: str | None
    queue_depth: int
    processed: int
    failed: int
    branch: str


class RuntimeDaemon:
    """Long-running local daemon with startup recovery and Git-aware indexing."""

    def __init__(self, settings: SynapseSettings) -> None:
        self.settings = settings
        self.runtime = SynapseRuntime(settings)
        self.pipeline = AsyncEventPipeline(
            max_size=settings.queue_max_size,
            concurrency=settings.worker_concurrency,
            retry_limit=settings.retry_limit,
        )
        self.git = GitRepository(settings.repository_path)
        self.logger = get_logger("daemon")
        self._stop_event = asyncio.Event()
        self._last_git_state: GitState | None = None
        self._running = False
        self.pipeline.register(WorkKind.INDEX_REPOSITORY, self._handle_index_repository)
        self.pipeline.register(WorkKind.CREATE_SNAPSHOT, self._handle_create_snapshot)
        self.pipeline.register(WorkKind.DETECT_DRIFT, self._handle_detect_drift)
        self.pipeline.register(WorkKind.NOOP, self._handle_noop)

    async def start(self) -> None:
        self.runtime.initialize_storage()
        replay = self.runtime.replay()
        self.logger.info(
            "daemon_replay_complete",
            operation="startup_replay",
            result="ok" if not replay.diagnostics else "diagnostic",
            event_count=replay.event_count,
            context_count=replay.context_count,
            object_id=replay.state_hash,
        )
        if self.runtime.status().active_context is None:
            self.runtime.bootstrap()
        await self.pipeline.start()
        self._running = True
        self._install_signal_handlers()
        try:
            await self._poll_git_loop()
        finally:
            await self.pipeline.stop()
            self._running = False

    def stop(self) -> None:
        self._stop_event.set()

    def health(self) -> DaemonHealth:
        status = self.runtime.status()
        queue = self.pipeline.health()
        return DaemonHealth(
            running=self._running,
            active_context=status.active_context,
            queue_depth=queue.queued,
            processed=queue.processed,
            failed=queue.failed,
            branch=status.branch,
        )

    async def _poll_git_loop(self) -> None:
        while not self._stop_event.is_set():
            state = self.git.state()
            change = self.git.classify(self._last_git_state, state)
            self._last_git_state = state
            if change.kind.value not in {"initial", "unchanged"}:
                await self.pipeline.enqueue(
                    WorkItem(
                        kind=WorkKind.INDEX_REPOSITORY,
                        payload={"reason": f"git:{change.kind.value}"},
                    ),
                    priority=10,
                )
            await asyncio.sleep(self.settings.daemon_poll_interval_seconds)

    async def _handle_index_repository(self, item: WorkItem) -> None:
        reason = str(item.payload.get("reason", "daemon"))
        await asyncio.to_thread(self.runtime.index_repository, reason=reason)

    async def _handle_create_snapshot(self, item: WorkItem) -> None:
        _ = item
        await asyncio.to_thread(self.runtime.create_snapshot)

    async def _handle_detect_drift(self, item: WorkItem) -> None:
        _ = item
        await asyncio.to_thread(self.runtime.drift)

    async def _handle_noop(self, item: WorkItem) -> None:
        _ = item

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop)
            except NotImplementedError:
                continue
