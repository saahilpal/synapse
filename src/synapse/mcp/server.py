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
                "mcp_tool_invoked",
                tool="get_status",
                latency_ms=(time.monotonic() - start) * 1000,
            )
            return json.dumps(res)

    async def run(self) -> None:
        await self.mcp.run_stdio_async()
