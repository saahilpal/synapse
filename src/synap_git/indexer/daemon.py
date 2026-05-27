from __future__ import annotations

import asyncio
import signal
import time
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

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
    """Long-running background daemon hosting watcher and Diagnostic UI in one process."""

    def __init__(self, settings: SynapSettings) -> None:
        self.settings = settings
        self.runtime = SynapRuntime(settings)
        self.git = GitRepository(settings.repository_path)
        self.logger = get_logger("daemon")
        self._stop_event = asyncio.Event()
        self._last_git_state: GitState | None = None
        self._running = False
        self._port = 9876
        self._last_metrics_time: float = 0.0
        self._last_cpu_time: float = 0.0

    async def start(self) -> None:
        self.runtime.initialize_storage()
        self._uptime_start = time.time()
        self._recovery_attempts = 0

        # Retrieve initial git state safely
        try:
            self._last_git_state = self.git.state()
        except Exception:
            self._last_git_state = None

        # Find an available port for UI hosting to avoid port conflicts
        self._port = self._find_free_port(9876)

        # Start FastAPI Diagnostic UI via Uvicorn in the same async loop
        import contextlib

        from uvicorn import Config, Server

        from synap_git.api.app import create_app

        config = Config(
            app=create_app(self.runtime),
            host="127.0.0.1",
            port=self._port,
            log_level="warning",
            loop="asyncio",
        )
        self._ui_server = Server(config)

        # Patch uvicorn's signal capturing to allow our daemon to control signal handling
        @contextlib.contextmanager
        def dummy_capture_signals() -> Generator[None, None, None]:
            yield

        self._ui_server.capture_signals = dummy_capture_signals  # type: ignore[method-assign]

        # Initial bootstrap
        await asyncio.to_thread(self.runtime.bootstrap)

        self._running = True
        self._write_heartbeat(status="healthy")
        self._install_signal_handlers()

        # Launch Uvicorn in background
        server_task = asyncio.create_task(self._ui_server.serve())

        try:
            await self._poll_git_loop()
        finally:
            self._running = False
            self.logger.info("daemon_shutting_down")
            self._ui_server.should_exit = True

            # Allow uvicorn to shut down gracefully if it's running
            if self._ui_server.started:
                try:
                    await asyncio.wait_for(
                        server_task, timeout=self.settings.shutdown_timeout_seconds
                    )
                except (TimeoutError, asyncio.CancelledError):
                    self.logger.warning("daemon_uvicorn_graceful_shutdown_failed")

            if not server_task.done():
                server_task.cancel()
                try:
                    await server_task
                except (asyncio.CancelledError, Exception):
                    pass

            self._delete_heartbeat()
            self.logger.info("daemon_stopped")

    def stop(self) -> None:
        self._stop_event.set()

    def health(self) -> DaemonHealth:
        status = self.runtime.status()
        return DaemonHealth(
            running=self._running,
            active_commit=status.active_commit,
            branch=status.branch,
        )

    def _find_free_port(self, start_port: int) -> int:
        import socket

        port = start_port
        while port < start_port + 100:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", port))
                    return port
                except OSError:
                    port += 1
        raise OSError("No free ports available in range.")

    def _get_process_metrics(self) -> dict[str, Any]:
        import os
        import sys

        # Memory (RAM)
        try:
            import resource

            max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if sys.platform != "darwin":
                max_rss *= 1024
            ram_mb = max_rss / (1024 * 1024)
        except Exception:
            ram_mb = 0.0

        # CPU usage
        try:
            now_time = time.time()
            t = os.times()
            now_cpu_time = t.user + t.system

            if hasattr(self, "_last_metrics_time") and hasattr(self, "_last_cpu_time"):
                time_diff = now_time - self._last_metrics_time
                cpu_diff = now_cpu_time - self._last_cpu_time
                if time_diff > 0:
                    cpu_percent = (cpu_diff / time_diff) * 100.0
                else:
                    cpu_percent = 0.0
            else:
                cpu_percent = 0.0

            self._last_metrics_time = now_time
            self._last_cpu_time = now_cpu_time
        except Exception:
            cpu_percent = 0.0

        return {
            "cpu_percent": round(cpu_percent, 1),
            "ram_mb": round(ram_mb, 1),
        }

    def _write_heartbeat(self, status: str = "healthy", last_error: str | None = None) -> None:
        import json
        import os
        from datetime import UTC, datetime

        try:
            heartbeat_file = self.settings.repository_path / ".synap" / "daemon_heartbeat.json"
            heartbeat_file.parent.mkdir(parents=True, exist_ok=True)

            uptime = int(time.time() - self._uptime_start) if hasattr(self, "_uptime_start") else 0

            try:
                status_info = self.runtime.status()
                indexed_files = status_info.files
                memory_nodes = status_info.symbols
            except Exception:
                indexed_files = 0
                memory_nodes = 0

            metrics = self._get_process_metrics()

            branch = "unknown"
            active_commit = "unknown"
            if self._last_git_state:
                branch = getattr(self._last_git_state, "effective_branch", "unknown")
                active_commit = getattr(self._last_git_state, "head_commit", "unknown")

            data = {
                "pid": os.getpid(),
                "timestamp": datetime.now(UTC).isoformat(),
                "status": status,
                "port": getattr(self, "_port", 9876),
                "uptime_seconds": uptime,
                "recovery_attempts": getattr(self, "_recovery_attempts", 0),
                "last_error": last_error,
                "branch": branch,
                "active_commit": active_commit,
                "cpu_percent": metrics.get("cpu_percent", 0.0),
                "ram_mb": metrics.get("ram_mb", 0.0),
                "indexed_files": indexed_files,
                "memory_nodes": memory_nodes,
            }
            heartbeat_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            self.logger.error("daemon_write_heartbeat_error", error=str(e))

    def _delete_heartbeat(self) -> None:
        heartbeat_file = self.settings.repository_path / ".synap" / "daemon_heartbeat.json"
        if heartbeat_file.exists():
            try:
                heartbeat_file.unlink()
            except Exception:
                pass

        # Cleanup process PID lockfile as well
        pid_file = self.settings.repository_path / ".synap" / "daemon.pid"
        if pid_file.exists():
            try:
                pid_file.unlink()
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

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.settings.daemon_poll_interval_seconds,
                )
                break  # Stop event was set, exit loop
            except TimeoutError:
                pass  # Normal poll interval elapsed, continue loop

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop)
            except NotImplementedError:
                continue
