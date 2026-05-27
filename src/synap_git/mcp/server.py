from __future__ import annotations

import functools
import inspect
import json
import time
import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP

from synap_git.indexer.engine import SynapRuntime


class SynapMCPFacade:
    """Model Context Protocol facade over the simplified Synap runtime."""

    def __init__(self, runtime: SynapRuntime) -> None:
        self.runtime = runtime

    def get_status(self) -> dict[str, Any]:
        status = self.runtime.status()
        return status.__dict__

    def search(self, query: str, max_tokens: int = 4000) -> dict[str, Any]:
        result, ctx, debug = self.runtime.query_hybrid(query, max_tokens=max_tokens)
        return {"result": result, "context": ctx, "trace": debug}

    def create_checkpoint(
        self, doing: str, changed_files: list[str], next_step: str, blockers: str
    ) -> dict[str, Any]:
        status = self.runtime.status()
        checkpoint_id = str(uuid.uuid4())
        branch = status.branch
        commit = status.git_commit or "unknown"
        self.runtime.store.put_checkpoint(
            checkpoint_id, branch, commit, doing, json.dumps(changed_files), next_step, blockers
        )
        return {"status": "success", "checkpoint_id": checkpoint_id}

    def restore_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        status = self.runtime.status()
        cp = self.runtime.store.get_latest_checkpoint(status.branch)
        if not cp:
            raise ValueError("No checkpoint found for current branch.")
        return dict(cp)

    def log_decision(self, content: str, context_info: str) -> dict[str, Any]:
        status = self.runtime.status()
        decision_id = str(uuid.uuid4())
        branch = status.branch
        commit = status.git_commit or "unknown"
        self.runtime.store.put_decision(decision_id, branch, commit, content, context_info)
        return {"status": "success", "decision_id": decision_id}

    def verify_system(self) -> dict[str, Any]:
        res = self.runtime.doctor()
        return res

    def submit_lesson_analysis(self, lesson_id: str, why_failed: str) -> dict[str, Any]:
        self.runtime.store.update_lesson(lesson_id, why_failed, "pending", actor="mcp_agent")
        return {"status": "success", "message": "Lesson awaiting human approval"}

    def get_approved_memory(self) -> dict[str, Any]:
        lessons = self.runtime.store.get_lessons("approved")
        return {"status": "success", "lessons": lessons}

    def get_pending_memory(self) -> dict[str, Any]:
        lessons = self.runtime.store.get_lessons("pending")
        return {"status": "success", "lessons": lessons}


class SynapMCPServer:
    """Exposes Synap tools to AI agents via MCP Stdio."""

    def __init__(self, runtime: SynapRuntime) -> None:
        self.mcp = FastMCP("Synap Context Runtime")
        self.facade = SynapMCPFacade(runtime)
        self._register_tools()

    def _register_tools(self) -> None:
        from synap_git.diagnostics.logger import get_logger

        logger = get_logger("mcp_server")

        from collections.abc import Callable

        def _wrap(f: Callable[..., dict[str, Any]]) -> Callable[..., str]:
            @functools.wraps(f)
            def wrapper(*args: Any, **kwargs: Any) -> str:
                trace_id = str(uuid.uuid4())
                try:
                    status = self.facade.runtime.status()
                    dirty = status.is_dirty
                    warnings = []
                    if dirty:
                        warnings.append("Working tree is dirty. Index may be stale.")

                    start = time.monotonic()
                    data = f(*args, **kwargs)
                    duration_ms = (time.monotonic() - start) * 1000
                    logger.info(
                        "mcp_tool_invoked",
                        tool=f.__name__,
                        latency_ms=duration_ms,
                    )

                    try:
                        self.facade.runtime.trace_store.record_trace(
                            trace_type="mcp",
                            summary=f"MCP Tool Invoked: {f.__name__}",
                            details={
                                "tool": f.__name__,
                                "arguments": kwargs,
                                "duration_ms": duration_ms,
                                "success": True,
                                "trace_id": trace_id,
                                "dirty_tree": dirty,
                            },
                        )
                    except Exception:
                        pass

                    return json.dumps(
                        {
                            "ok": True,
                            "data": data,
                            "warnings": warnings,
                            "trace_id": trace_id,
                            "dirty_tree": dirty,
                        }
                    )
                except Exception as e:
                    msg = str(e)
                    code = "INTERNAL_ERROR"
                    suggestion = "Check daemon logs."

                    if "stale" in msg.lower():
                        code = "INDEX_STALE"
                        suggestion = "Run `synap reindex` or wait for daemon."
                    elif "no checkpoint" in msg.lower():
                        code = "NOT_FOUND"
                        suggestion = "Ensure checkpoints exist for this branch."

                    logger.error("mcp_tool_error", tool=f.__name__, error=msg)

                    try:
                        self.facade.runtime.trace_store.record_trace(
                            trace_type="mcp",
                            summary=f"MCP Tool Failed: {f.__name__}",
                            details={
                                "tool": f.__name__,
                                "arguments": kwargs,
                                "error": msg,
                                "success": False,
                                "trace_id": trace_id,
                            },
                        )
                    except Exception:
                        pass

                    return json.dumps(
                        {
                            "ok": False,
                            "error": {"code": code, "message": msg, "suggestion": suggestion},
                            "warnings": [],
                            "trace_id": trace_id,
                            "dirty_tree": False,
                        }
                    )

            wrapper.__signature__ = inspect.signature(f)  # type: ignore
            return wrapper

        @self.mcp.tool()
        @_wrap
        def get_status() -> dict[str, Any]:
            """Get current repository indexing status and active commit."""
            return self.facade.get_status()

        @self.mcp.tool()
        @_wrap
        def search(query: str, max_tokens: int = 4000) -> dict[str, Any]:
            """Search the repository context for semantic and structural matches."""
            return self.facade.search(query, max_tokens)

        @self.mcp.tool()
        @_wrap
        def create_checkpoint(
            doing: str, changed_files: list[str], next_step: str, blockers: str
        ) -> dict[str, Any]:
            """Save the current agent's thought process and state as a checkpoint."""
            return self.facade.create_checkpoint(doing, changed_files, next_step, blockers)

        @self.mcp.tool()
        @_wrap
        def restore_checkpoint() -> dict[str, Any]:
            """Restore the latest checkpoint for the current branch to resume context."""
            return self.facade.restore_checkpoint("latest")

        @self.mcp.tool()
        @_wrap
        def log_decision(content: str, context_info: str) -> dict[str, Any]:
            """Log an architectural or technical decision to the project's decision log."""
            return self.facade.log_decision(content, context_info)

        @self.mcp.tool()
        @_wrap
        def verify_system() -> dict[str, Any]:
            """Verify database integrity and run internal diagnostics."""
            return self.facade.verify_system()

        @self.mcp.tool()
        @_wrap
        def submit_lesson_analysis(lesson_id: str, why_failed: str) -> dict[str, Any]:
            """Submit an analysis for a pending lesson (e.g., after a revert). Lesson remains pending until human approval."""
            return self.facade.submit_lesson_analysis(lesson_id, why_failed)

        @self.mcp.tool()
        @_wrap
        def get_approved_memory() -> dict[str, Any]:
            """Retrieve APPROVED memory lessons that MUST be strictly adhered to."""
            return self.facade.get_approved_memory()

        @self.mcp.tool()
        @_wrap
        def get_pending_memory() -> dict[str, Any]:
            """Retrieve PENDING memory lessons currently awaiting human review."""
            return self.facade.get_pending_memory()

    async def run(self) -> None:
        await self.mcp.run_stdio_async()
