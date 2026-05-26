from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass

from synapse.config import SynapseSettings
from synapse.diagnostics.logging import get_logger
from synapse.git import GitRepository, GitState
from synapse.indexer.engine import SynapseRuntime


@dataclass(frozen=True)
class DaemonHealth:
    running: bool
    active_commit: str | None
    branch: str


class RuntimeDaemon:
    """Simplified long-running local daemon with Git-aware indexing."""

    def __init__(self, settings: SynapseSettings) -> None:
        self.settings = settings
        self.runtime = SynapseRuntime(settings)
        self.git = GitRepository(settings.repository_path)
        self.logger = get_logger("daemon")
        self._stop_event = asyncio.Event()
        self._last_git_state: GitState | None = None
        self._running = False

    async def start(self) -> None:
        self.runtime.initialize_storage()

        # Initial bootstrap
        await asyncio.to_thread(self.runtime.bootstrap)

        self._running = True
        self._install_signal_handlers()
        try:
            await self._poll_git_loop()
        finally:
            self._running = False

    def stop(self) -> None:
        self._stop_event.set()

    def health(self) -> DaemonHealth:
        status = self.runtime.status()
        return DaemonHealth(
            running=self._running,
            active_commit=status.active_commit,
            branch=status.branch,
        )

    async def _poll_git_loop(self) -> None:
        while not self._stop_event.is_set():
            state = self.git.state()
            change = self.git.classify(self._last_git_state, state)
            self._last_git_state = state

            if change.kind == "commit":
                self.logger.info("git_commit_detected")
                await asyncio.to_thread(self.runtime.handle_commit, state)
            elif change.kind in ("branch", "checkout"):
                self.logger.info("git_branch_switch_detected")
                await asyncio.to_thread(self.runtime.handle_branch_switch, state)
            elif change.kind == "merge":
                self.logger.info("git_merge_detected")
                await asyncio.to_thread(self.runtime.handle_merge, state)
            elif change.kind == "revert":
                self.logger.info("git_revert_detected")
                await asyncio.to_thread(self.runtime.handle_revert, self._last_git_state, state)
            elif change.kind not in ("initial", "unchanged"):
                self.logger.info("git_change_detected", kind=change.kind)
                await asyncio.to_thread(self.runtime.index_repository, git_state=state)

            await asyncio.sleep(self.settings.daemon_poll_interval_seconds)

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop)
            except NotImplementedError:
                continue
