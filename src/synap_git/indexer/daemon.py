from __future__ import annotations

import asyncio
import signal
import time
from dataclasses import dataclass

from synap_git.config import SynapSettings
from synap_git.diagnostics.logger import get_logger
from synap_git.git import GitRepository, GitState
from synap_git.indexer.engine import SynapRuntime


@dataclass(frozen=True)
class DaemonHealth:
    running: bool
    active_commit: str | None
    branch: str


class RuntimeDaemon:
    """Simplified long-running local daemon with Git-aware indexing."""

    def __init__(self, settings: SynapSettings) -> None:
        self.settings = settings
        self.runtime = SynapRuntime(settings)
        self.git = GitRepository(settings.repository_path)
        self.logger = get_logger("daemon")
        self._stop_event = asyncio.Event()
        self._last_git_state: GitState | None = None
        self._running = False

    async def start(self) -> None:
        self.runtime.initialize_storage()
        self._uptime_start = time.time()
        self._recovery_attempts = 0

        # Initial bootstrap
        await asyncio.to_thread(self.runtime.bootstrap)

        self._running = True
        self._write_heartbeat(status="healthy")
        self._install_signal_handlers()
        try:
            await self._poll_git_loop()
        finally:
            self._running = False
            self._delete_heartbeat()

    def stop(self) -> None:
        self._stop_event.set()

    def health(self) -> DaemonHealth:
        status = self.runtime.status()
        return DaemonHealth(
            running=self._running,
            active_commit=status.active_commit,
            branch=status.branch,
        )

    def _write_heartbeat(self, status: str = "healthy", last_error: str | None = None) -> None:
        import json
        import os
        import time as time_lib
        from datetime import UTC, datetime

        heartbeat_file = self.settings.repository_path / ".synap" / "daemon_heartbeat.json"
        heartbeat_file.parent.mkdir(parents=True, exist_ok=True)

        uptime = int(time_lib.time() - self._uptime_start) if hasattr(self, "_uptime_start") else 0

        data = {
            "pid": os.getpid(),
            "timestamp": datetime.now(UTC).isoformat(),
            "status": status,
            "uptime_seconds": uptime,
            "recovery_attempts": getattr(self, "_recovery_attempts", 0),
            "last_error": last_error,
            "branch": self._last_git_state.effective_branch if self._last_git_state else "unknown",
            "active_commit": self._last_git_state.head_commit
            if self._last_git_state
            else "unknown",
        }
        try:
            heartbeat_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _delete_heartbeat(self) -> None:
        heartbeat_file = self.settings.repository_path / ".synap" / "daemon_heartbeat.json"
        if heartbeat_file.exists():
            try:
                heartbeat_file.unlink()
            except Exception:
                pass

    async def _poll_git_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
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

                self._write_heartbeat(status="healthy")
            except Exception as e:
                self.logger.error("daemon_loop_error", error=str(e))
                self._recovery_attempts += 1
                self._write_heartbeat(status="degraded", last_error=str(e))

                # Database recovery if corrupted
                try:
                    is_wiped = await asyncio.to_thread(self.runtime.store.recover_if_corrupted)
                    if is_wiped:
                        self.logger.warning("daemon_rebuilding_corrupted_db")
                        await asyncio.to_thread(self.runtime.bootstrap, force=True)
                except Exception as ex:
                    self.logger.error("daemon_self_healing_failed", error=str(ex))

            await asyncio.sleep(self.settings.daemon_poll_interval_seconds)

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop)
            except NotImplementedError:
                continue
