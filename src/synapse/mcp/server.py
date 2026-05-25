from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import FastMCP

from synapse.runtime.service import SynapseRuntime


@dataclass(frozen=True)
class MCPToolResult:
    content: dict[str, Any]


class SynapseMCPFacade:
    """Thin Model Context Protocol facade over Synapse context retrieval APIs.

    Provides a clean, secure boundary exposing persistence context tools to AI agents.
    """

    def __init__(self, runtime: SynapseRuntime) -> None:
        self.runtime = runtime

    def get_context(self) -> MCPToolResult:
        status = self.runtime.status()
        commits = self.runtime.list_context_commits(limit=10)
        return MCPToolResult(
            {
                "active_context": status.active_context,
                "branch": status.branch,
                "git_commit": status.git_commit,
                "recent_context_commits": commits,
            }
        )

    def list_context_commits(self, *, limit: int = 50) -> MCPToolResult:
        return MCPToolResult({"commits": self.runtime.list_context_commits(limit=limit)})

    def diff_context(self, *, left_hash: str, right_hash: str) -> MCPToolResult:
        return MCPToolResult(self.runtime.diff(left_hash, right_hash))

    def search_context(self, *, query: str, limit: int = 20) -> MCPToolResult:
        return MCPToolResult({"results": self.runtime.search_context(query, limit=limit)})

    def get_context_for_task(self, *, task_description: str, limit: int = 4000) -> MCPToolResult:
        response, sources, trace = self.runtime.query_hybrid(task_description, max_tokens=limit)
        return MCPToolResult({"response": response, "sources": sources, "trace": trace})

    def explain_structure(self, *, module_path: str) -> MCPToolResult:
        status = self.runtime.status()
        context_hash = status.active_context
        if not context_hash:
            return MCPToolResult({"error": "No active context exists."})

        prompt = (
            f"Explain the structure, functions, classes, and dependencies of module: {module_path}"
        )
        response, sources, trace = self.runtime.query_hybrid(prompt, context_hash=context_hash)
        return MCPToolResult({"explanation": response, "sources": sources, "trace": trace})

    def retrieve_related_context(self, *, stable_id: str, depth: int = 2) -> MCPToolResult:
        status = self.runtime.status()
        context_hash = status.active_context
        if not context_hash:
            return MCPToolResult({"error": "No active context exists."})

        max_depth = max(0, min(depth, 5))
        max_nodes = 500
        active_nodes, _, active_edges = self.runtime.retrieval_engine.active_context_state(
            context_hash
        )

        visited = {stable_id}
        frontier = {stable_id}
        related_edges = []

        for _ in range(max_depth):
            next_frontier = set()
            for edge in active_edges.values():
                if len(visited) >= max_nodes:
                    break
                from_id = edge["from_id"]
                to_id = edge["to_id"]
                if from_id in frontier and to_id not in visited:
                    next_frontier.add(to_id)
                    visited.add(to_id)
                    related_edges.append(edge)
                elif to_id in frontier and from_id not in visited:
                    next_frontier.add(from_id)
                    visited.add(from_id)
                    related_edges.append(edge)
            frontier = next_frontier

        related_nodes = [active_nodes[nid] for nid in visited if nid in active_nodes]
        return MCPToolResult({"nodes": related_nodes, "edges": related_edges})

    def get_temporal_changes(self, *, since_commit: str) -> MCPToolResult:
        status = self.runtime.status()
        current_context = status.active_context
        if not current_context:
            return MCPToolResult({"error": "No active context exists."})

        since_context = None
        for row in self.runtime.list_context_commits(limit=100):
            ctx_hash = str(row["context_hash"])
            if ctx_hash.startswith(since_commit):
                since_context = ctx_hash
                break

        if not since_context:
            for row in self.runtime.list_context_commits(limit=100):
                c_hash = row.get("git_commit_hash")
                if c_hash and c_hash.startswith(since_commit):
                    since_context = str(row["context_hash"])
                    break

        if not since_context:
            for row in self.runtime.event_store.list_context_rows():
                ctx_hash = str(row["context_hash"])
                c_hash = row.get("git_commit_hash")
                if ctx_hash.startswith(since_commit):
                    since_context = ctx_hash
                    break
                if c_hash and c_hash.startswith(since_commit):
                    since_context = ctx_hash
                    break

        if not since_context:
            return MCPToolResult(
                {"error": f"Commit/Context '{since_commit}' not found in context history."}
            )

        diff = self.runtime.diff(since_context, current_context)
        return MCPToolResult(diff)

    def get_valid_context_window(self, *, context_hash: str | None = None) -> MCPToolResult:
        if not context_hash:
            status = self.runtime.status()
            context_hash = status.active_context
        if not context_hash:
            return MCPToolResult({"error": "No active context exists."})

        active_nodes, active_semantics, active_edges = (
            self.runtime.retrieval_engine.active_context_state(context_hash)
        )
        return MCPToolResult(
            {
                "active_nodes": list(active_nodes.values()),
                "active_edges": list(active_edges.values()),
                "active_semantics": list(active_semantics.values()),
            }
        )


class SynapseMCPServer:
    """The actual MCP Server using FastMCP to expose tools over Stdio."""

    def __init__(self, runtime: SynapseRuntime) -> None:
        self.mcp = FastMCP("Synapse Context Runtime")
        self.facade = SynapseMCPFacade(runtime)
        self._register_tools()

    def _register_tools(self) -> None:
        import time

        from synapse.observability import get_logger

        logger = get_logger("mcp_server")

        @self.mcp.tool()
        def get_current_context() -> str:
            """Get the current repository context summary and active commit heads."""
            import json

            start = time.monotonic()
            try:
                res = self.facade.get_context().content
                logger.info(
                    "mcp_tool_invoked",
                    tool="get_current_context",
                    latency_ms=(time.monotonic() - start) * 1000,
                )
                return json.dumps(res)
            except Exception as e:
                logger.error("mcp_tool_error", tool="get_current_context", error=str(e))
                return json.dumps({"error": str(e)})

        @self.mcp.tool()
        def search_context(query: str) -> str:
            """Search the repository context using hybrid semantic + structural search."""
            import json

            start = time.monotonic()
            try:
                res = self.facade.search_context(query=query).content
                logger.info(
                    "mcp_tool_invoked",
                    tool="search_context",
                    query=query,
                    latency_ms=(time.monotonic() - start) * 1000,
                )
                return json.dumps(res)
            except Exception as e:
                logger.error("mcp_tool_error", tool="search_context", error=str(e))
                return json.dumps({"error": str(e)})

        @self.mcp.tool()
        def get_context_for_task(task_description: str) -> str:
            """Provide an AI agent with grounded, synthesized context necessary to complete a task."""
            import json

            start = time.monotonic()
            try:
                res = self.facade.get_context_for_task(task_description=task_description).content
                logger.info(
                    "mcp_tool_invoked",
                    tool="get_context_for_task",
                    latency_ms=(time.monotonic() - start) * 1000,
                )
                return json.dumps(res)
            except Exception as e:
                logger.error("mcp_tool_error", tool="get_context_for_task", error=str(e))
                return json.dumps({"error": str(e)})

        @self.mcp.tool()
        def explain_structure(module_path: str) -> str:
            """Ask Synapse to explain the structural boundaries and dependencies of a specific file/module."""
            import json

            start = time.monotonic()
            try:
                res = self.facade.explain_structure(module_path=module_path).content
                logger.info(
                    "mcp_tool_invoked",
                    tool="explain_structure",
                    module=module_path,
                    latency_ms=(time.monotonic() - start) * 1000,
                )
                return json.dumps(res)
            except Exception as e:
                logger.error("mcp_tool_error", tool="explain_structure", error=str(e))
                return json.dumps({"error": str(e)})

    async def run(self) -> None:
        await self.mcp.run_stdio_async()
