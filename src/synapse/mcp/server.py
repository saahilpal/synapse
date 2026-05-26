from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import FastMCP

from synapse.indexer.engine import SynapseRuntime


@dataclass(frozen=True)
class MCPToolResult:
    content: dict[str, Any]


class SynapseMCPFacade:
    """Model Context Protocol facade over the simplified Synapse runtime."""

    def __init__(self, runtime: SynapseRuntime) -> None:
        self.runtime = runtime

    def get_status(self) -> MCPToolResult:
        status = self.runtime.status()
        return MCPToolResult(status.__dict__)

    def search(self, query: str, max_tokens: int = 4000) -> MCPToolResult:
        result, ctx, debug = self.runtime.query_hybrid(query, max_tokens=max_tokens)
        return MCPToolResult({"result": result, "context": ctx, "debug": debug})

    def create_checkpoint(
        self, doing: str, changed_files: list[str], next_step: str, blockers: str
    ) -> MCPToolResult:
        import uuid

        status = self.runtime.status()
        checkpoint_id = str(uuid.uuid4())
        branch = status.branch
        commit = status.git_commit or "unknown"
        self.runtime.store.put_checkpoint(
            checkpoint_id, branch, commit, doing, json.dumps(changed_files), next_step, blockers
        )
        return MCPToolResult({"status": "success", "checkpoint_id": checkpoint_id})

    def restore_checkpoint(self, checkpoint_id: str) -> MCPToolResult:
        # Assuming checkpoint_id is just 'latest' for now to keep it simple
        status = self.runtime.status()
        cp = self.runtime.store.get_latest_checkpoint(status.branch)
        return MCPToolResult(cp or {"error": "No checkpoint found"})

    def log_decision(self, content: str, context_info: str) -> MCPToolResult:
        import uuid

        status = self.runtime.status()
        decision_id = str(uuid.uuid4())
        branch = status.branch
        commit = status.git_commit or "unknown"
        self.runtime.store.put_decision(decision_id, branch, commit, content, context_info)
        return MCPToolResult({"status": "success", "decision_id": decision_id})

    def verify_system(self) -> MCPToolResult:
        res = self.runtime.doctor()
        return MCPToolResult(res)

    def submit_lesson_analysis(self, lesson_id: str, why_failed: str) -> MCPToolResult:
        self.runtime.store.update_lesson(lesson_id, why_failed, "awaiting_approval")
        return MCPToolResult({"status": "success", "message": "Lesson awaiting approval"})


class SynapseMCPServer:
    """Exposes Synapse tools to AI agents via MCP Stdio."""

    def __init__(self, runtime: SynapseRuntime) -> None:
        self.mcp = FastMCP("Synapse Context Runtime")
        self.facade = SynapseMCPFacade(runtime)
        self._register_tools()

    def _register_tools(self) -> None:
        from synapse.diagnostics.logging import get_logger

        logger = get_logger("mcp_server")

        @self.mcp.tool()
        def get_status() -> str:
            """Get current repository indexing status and active commit."""
            start = time.monotonic()
            res = self.facade.get_status().content
            logger.info(
                "mcp_tool_invoked", tool="get_status", latency_ms=(time.monotonic() - start) * 1000
            )
            return json.dumps(res)

        @self.mcp.tool()
        def search(query: str, max_tokens: int = 4000) -> str:
            """Search the repository context for semantic and structural matches."""
            return json.dumps(self.facade.search(query, max_tokens).content)

        @self.mcp.tool()
        def create_checkpoint(
            doing: str, changed_files: list[str], next_step: str, blockers: str
        ) -> str:
            """Save the current agent's thought process and state as a checkpoint."""
            return json.dumps(
                self.facade.create_checkpoint(doing, changed_files, next_step, blockers).content
            )

        @self.mcp.tool()
        def restore_checkpoint() -> str:
            """Restore the latest checkpoint for the current branch to resume context."""
            return json.dumps(self.facade.restore_checkpoint("latest").content)

        @self.mcp.tool()
        def log_decision(content: str, context_info: str) -> str:
            """Log an architectural or technical decision to the project's decision log."""
            return json.dumps(self.facade.log_decision(content, context_info).content)

        @self.mcp.tool()
        def verify_system() -> str:
            """Verify database integrity and run internal diagnostics."""
            return json.dumps(self.facade.verify_system().content)

        @self.mcp.tool()
        def submit_lesson_analysis(lesson_id: str, why_failed: str) -> str:
            """Submit an analysis for a pending lesson (e.g., after a revert)."""
            return json.dumps(self.facade.submit_lesson_analysis(lesson_id, why_failed).content)

    async def run(self) -> None:
        await self.mcp.run_stdio_async()
