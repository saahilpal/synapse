from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from synap_git.diagnostics.logger import get_logger

if TYPE_CHECKING:
    from synap_git.config import SynapSettings
    from synap_git.indexer.engine import SynapRuntime


def get_socket_path(repo_path: Path) -> Path:
    """
    Get the Unix domain socket path for the repository.
    Ensures path length adheres to OS AF_UNIX limits (104 bytes on macOS).
    """
    default_sock = repo_path / ".synap" / "daemon.sock"
    if len(str(default_sock)) > 90:
        repo_hash = hashlib.sha256(str(repo_path.resolve()).encode("utf-8")).hexdigest()[:12]
        return Path(tempfile.gettempdir()) / f"synap_{repo_hash}.sock"
    return default_sock


class DaemonUnavailableError(Exception):
    """Raised when the Synapse daemon Unix domain socket is unreachable."""


class DaemonServer:
    """Asyncio Unix Domain Socket server running inside RuntimeDaemon."""

    def __init__(self, runtime: SynapRuntime, socket_path: Path | None = None) -> None:
        self.runtime = runtime
        self.repo_path = runtime.settings.repository_path
        self.socket_path = socket_path or get_socket_path(self.repo_path)
        self.link_path = self.repo_path / ".synap" / "daemon.sock"
        self._server: asyncio.Server | None = None
        self._running = False
        self.logger = get_logger("ipc_server")

    async def start(self) -> None:
        """Start listening on the Unix domain socket."""
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self.link_path.parent.mkdir(parents=True, exist_ok=True)

        for p in (self.socket_path, self.link_path):
            if p.exists() or p.is_symlink():
                try:
                    p.unlink()
                except OSError:
                    pass

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self.socket_path),
        )
        self._running = True

        # Create symlink at .synap/daemon.sock if socket_path is shortened to /tmp
        if self.socket_path != self.link_path:
            try:
                self.link_path.symlink_to(self.socket_path)
            except OSError:
                pass

        self.logger.info("ipc_server_started", socket_path=str(self.socket_path))

    async def stop(self) -> None:
        """Gracefully stop listening and clean up the socket file."""
        self._running = False
        if self._server:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None

        for p in (self.socket_path, self.link_path):
            if p.exists() or p.is_symlink():
                try:
                    p.unlink()
                except OSError:
                    pass
        self.logger.info("ipc_server_stopped")

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle incoming client requests over the domain socket."""
        try:
            while self._running and not reader.at_eof():
                line = await reader.readline()
                if not line:
                    break
                t_req_start = time.perf_counter()
                try:
                    req = json.loads(line.decode("utf-8"))
                    action = req.get("action", "")
                    params = req.get("params", {})
                    response = await self._dispatch_action(action, params)
                    latency_ms = (time.perf_counter() - t_req_start) * 1000
                    response["latency_ms"] = latency_ms
                    writer.write(json.dumps(response).encode("utf-8") + b"\n")
                    await writer.drain()
                except Exception as e:
                    latency_ms = (time.perf_counter() - t_req_start) * 1000
                    err_resp = {
                        "status": "error",
                        "error": str(e),
                        "latency_ms": latency_ms,
                    }
                    writer.write(json.dumps(err_resp).encode("utf-8") + b"\n")
                    await writer.drain()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.debug("ipc_client_handler_error", error=str(e))
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _dispatch_action(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Dispatch action to runtime in a thread to avoid blocking the event loop."""
        if action == "ping":
            return {"status": "ok", "pong": True, "pid": os.getpid()}
        elif action in ("query", "retrieve"):
            query_str = params.get("query", "")
            max_tokens = params.get("max_tokens", 4000)
            synthesize_answer = params.get("synthesize_answer", True)
            answer, sources, trace = await asyncio.to_thread(
                self.runtime.query_hybrid,
                query_str,
                max_tokens=max_tokens,
                synthesize_answer=synthesize_answer,
            )
            return {
                "status": "ok",
                "answer": answer,
                "sources": sources,
                "trace": trace,
            }
        elif action == "status":
            st = await asyncio.to_thread(self.runtime.status)
            return {"status": "ok", "result": st.__dict__}
        elif action in ("index", "reindex"):
            files = params.get("files")
            reindexed = await asyncio.to_thread(self.runtime.index_incremental_changes, files)
            return {"status": "ok", "reindexed": reindexed}
        else:
            return {"status": "error", "error": f"Unknown action: {action}"}


class DaemonClient:
    """
    Client that queries the warm background daemon over the Unix domain socket (<15ms).
    Gracefully falls back to in-process query execution if daemon socket is unavailable.
    """

    def __init__(
        self,
        repository_path: Path | str,
        settings: SynapSettings | None = None,
        runtime: SynapRuntime | None = None,
    ) -> None:
        self.repository_path = Path(repository_path)
        self.socket_path = get_socket_path(self.repository_path)
        self.link_path = self.repository_path / ".synap" / "daemon.sock"
        self._settings = settings
        self._fallback_runtime: SynapRuntime | None = runtime
        self.logger = get_logger("ipc_client")

    def _get_active_sock(self) -> Path:
        if self.socket_path.exists():
            return self.socket_path
        if self.link_path.exists():
            return self.link_path
        return self.socket_path

    def _get_runtime(self) -> SynapRuntime:
        """Lazily initialize fallback in-process runtime."""
        if self._fallback_runtime is None:
            from synap_git.config import SynapSettings
            from synap_git.indexer.engine import SynapRuntime

            settings = self._settings or SynapSettings(repository_path=self.repository_path)
            self._fallback_runtime = SynapRuntime(settings)
        return self._fallback_runtime

    def is_daemon_running(self) -> bool:
        """Check whether the daemon socket is alive and responding (synchronous)."""
        sock_p = self._get_active_sock()
        if not sock_p.exists():
            return False
        try:
            resp = self._call_socket("ping", timeout=0.1)
            return resp.get("status") == "ok" and resp.get("pong") is True
        except Exception:
            return False

    async def is_daemon_running_async(self) -> bool:
        """Check whether the daemon socket is alive and responding (asynchronous)."""
        sock_p = self._get_active_sock()
        if not sock_p.exists():
            return False
        try:
            resp = await self._call_socket_async("ping", timeout=0.2)
            return resp.get("status") == "ok" and resp.get("pong") is True
        except Exception:
            return False

    def _call_socket(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        timeout: float = 2.0,
    ) -> dict[str, Any]:
        """Send a JSON request over the domain socket synchronously."""
        sock_p = self._get_active_sock()
        if not sock_p.exists():
            raise DaemonUnavailableError(f"Socket does not exist at {sock_p}")

        req_payload = {
            "action": action,
            "params": params or {},
        }
        data = json.dumps(req_payload).encode("utf-8") + b"\n"

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(str(sock_p))
            sock.sendall(data)

            buf = bytearray()
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf.extend(chunk)
                if b"\n" in chunk:
                    break
            if not buf:
                raise DaemonUnavailableError("Empty response from daemon socket")
            line = buf.decode("utf-8").strip()
            res = json.loads(line)
            if not isinstance(res, dict):
                raise DaemonUnavailableError("Malformed response from daemon socket")
            return res
        except (TimeoutError, OSError) as e:
            raise DaemonUnavailableError(f"Failed to communicate with daemon socket: {e}") from e
        finally:
            try:
                sock.close()
            except Exception:
                pass

    async def _call_socket_async(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        timeout: float = 2.0,
    ) -> dict[str, Any]:
        """Send a JSON request over the domain socket asynchronously."""
        sock_p = self._get_active_sock()
        if not sock_p.exists():
            raise DaemonUnavailableError(f"Socket does not exist at {sock_p}")

        req_payload = {
            "action": action,
            "params": params or {},
        }
        data = json.dumps(req_payload).encode("utf-8") + b"\n"

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(sock_p)),
                timeout=timeout,
            )
            writer.write(data)
            await writer.drain()

            line = await asyncio.wait_for(reader.readline(), timeout=timeout)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

            if not line:
                raise DaemonUnavailableError("Empty response from daemon socket")
            res = json.loads(line.decode("utf-8").strip())
            if not isinstance(res, dict):
                raise DaemonUnavailableError("Malformed response from daemon socket")
            return res
        except (TimeoutError, OSError) as e:
            raise DaemonUnavailableError(f"Failed to communicate with daemon socket: {e}") from e

    def query(
        self,
        query: str,
        *,
        max_tokens: int = 4000,
        synthesize_answer: bool = True,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        """
        Query the retrieval engine with automatic daemon IPC acceleration.
        Falls back to in-process execution if socket is unavailable.
        """
        t_start = time.perf_counter()
        try:
            resp = self._call_socket(
                "query",
                {
                    "query": query,
                    "max_tokens": max_tokens,
                    "synthesize_answer": synthesize_answer,
                },
            )
            if resp.get("status") == "ok":
                trace = resp.get("trace", {})
                latency_ms = (time.perf_counter() - t_start) * 1000
                trace["ipc_roundtrip_ms"] = latency_ms
                trace["transport"] = "unix_socket"
                return resp.get("answer", ""), resp.get("sources", []), trace
        except DaemonUnavailableError as e:
            self.logger.debug("daemon_socket_unavailable_fallback_in_process", error=str(e))
        except Exception as e:
            self.logger.warning("daemon_query_socket_failed_fallback_in_process", error=str(e))

        # Graceful fallback to in-process query execution
        rt = self._get_runtime()
        answer, sources, trace = rt.query_hybrid(
            query,
            max_tokens=max_tokens,
            synthesize_answer=synthesize_answer,
        )
        latency_ms = (time.perf_counter() - t_start) * 1000
        trace["ipc_roundtrip_ms"] = latency_ms
        trace["transport"] = "in_process_fallback"
        return answer, sources, trace

    async def query_async(
        self,
        query: str,
        *,
        max_tokens: int = 4000,
        synthesize_answer: bool = True,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        """Asynchronous version of query."""
        t_start = time.perf_counter()
        try:
            resp = await self._call_socket_async(
                "query",
                {
                    "query": query,
                    "max_tokens": max_tokens,
                    "synthesize_answer": synthesize_answer,
                },
            )
            if resp.get("status") == "ok":
                trace = resp.get("trace", {})
                latency_ms = (time.perf_counter() - t_start) * 1000
                trace["ipc_roundtrip_ms"] = latency_ms
                trace["transport"] = "unix_socket"
                return resp.get("answer", ""), resp.get("sources", []), trace
        except DaemonUnavailableError as e:
            self.logger.debug("daemon_socket_unavailable_fallback_in_process", error=str(e))
        except Exception as e:
            self.logger.warning("daemon_query_socket_failed_fallback_in_process", error=str(e))

        rt = self._get_runtime()
        answer, sources, trace = await asyncio.to_thread(
            rt.query_hybrid,
            query,
            max_tokens=max_tokens,
            synthesize_answer=synthesize_answer,
        )
        latency_ms = (time.perf_counter() - t_start) * 1000
        trace["ipc_roundtrip_ms"] = latency_ms
        trace["transport"] = "in_process_fallback"
        return answer, sources, trace

    def retrieve(
        self, *args: Any, **kwargs: Any
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        """Alias for query."""
        return self.query(*args, **kwargs)

    def ping(self) -> dict[str, Any]:
        """Ping the daemon; returns status and transport used."""
        try:
            resp = self._call_socket("ping", timeout=0.5)
            resp["transport"] = "unix_socket"
            return resp
        except DaemonUnavailableError:
            return {"status": "ok", "pong": True, "transport": "in_process_fallback"}

    async def ping_async(self) -> dict[str, Any]:
        """Ping the daemon asynchronously."""
        try:
            resp = await self._call_socket_async("ping", timeout=0.5)
            resp["transport"] = "unix_socket"
            return resp
        except DaemonUnavailableError:
            return {"status": "ok", "pong": True, "transport": "in_process_fallback"}

    def status(self) -> dict[str, Any]:
        """Get repository status via daemon socket or fallback."""
        try:
            resp = self._call_socket("status", timeout=1.0)
            if resp.get("status") == "ok":
                raw_res = resp.get("result", {})
                res: dict[str, Any] = dict(raw_res) if isinstance(raw_res, dict) else {}
                res["transport"] = "unix_socket"
                return res
        except DaemonUnavailableError:
            pass
        rt = self._get_runtime()
        st = rt.status().__dict__
        st["transport"] = "in_process_fallback"
        return st

    async def status_async(self) -> dict[str, Any]:
        """Get repository status asynchronously."""
        try:
            resp = await self._call_socket_async("status", timeout=1.0)
            if resp.get("status") == "ok":
                raw_res = resp.get("result", {})
                res: dict[str, Any] = dict(raw_res) if isinstance(raw_res, dict) else {}
                res["transport"] = "unix_socket"
                return res
        except DaemonUnavailableError:
            pass
        rt = self._get_runtime()
        st = await asyncio.to_thread(rt.status)
        res_dict = st.__dict__
        res_dict["transport"] = "in_process_fallback"
        return res_dict

    def reindex(self, files: list[str] | None = None) -> list[str]:
        """Trigger incremental reindex via daemon socket or fallback."""
        try:
            resp = self._call_socket("reindex", {"files": files}, timeout=10.0)
            if resp.get("status") == "ok":
                raw_reindexed = resp.get("reindexed", [])
                if isinstance(raw_reindexed, list):
                    return [str(x) for x in raw_reindexed]
                return []
        except DaemonUnavailableError:
            pass
        rt = self._get_runtime()
        return rt.index_incremental_changes(files)
