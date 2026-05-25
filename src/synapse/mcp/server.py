from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synapse.runtime.service import SynapseRuntime


@dataclass(frozen=True)
class MCPToolResult:
    content: dict[str, Any]


class SynapseMCPFacade:
    """Thin MCP-facing facade over runtime queries.

    This intentionally contains no cognition logic. A future official MCP SDK adapter can
    register these methods as tools/resources without changing runtime behavior.
    """

    def __init__(self, runtime: SynapseRuntime) -> None:
        self.runtime = runtime

    def get_context(self) -> MCPToolResult:
        status = self.runtime.status()
        commits = self.runtime.list_context_commits(limit=10)
        timeline = self.runtime.timeline(branch=status.branch, limit=10)
        return MCPToolResult(
            {
                "active_context": status.active_context,
                "branch": status.branch,
                "git_commit": status.git_commit,
                "recent_context_commits": commits,
                "timeline": [event.model_dump(mode="json") for event in timeline],
            }
        )

    def list_context_commits(self, *, limit: int = 50) -> MCPToolResult:
        return MCPToolResult({"commits": self.runtime.list_context_commits(limit=limit)})

    def diff_context(self, *, left_hash: str, right_hash: str) -> MCPToolResult:
        return MCPToolResult(
            self.runtime.semantic_diff(left_hash, right_hash).model_dump(mode="json")
        )

    def impact_context(self, *, left_hash: str, right_hash: str) -> MCPToolResult:
        return MCPToolResult({"impact": self.runtime.semantic_impact(left_hash, right_hash)})

    def verify_lineage(self) -> MCPToolResult:
        return MCPToolResult({"lineage": self.runtime.lineage()})

    def search_cognition(self, *, query: str, limit: int = 20) -> MCPToolResult:
        return MCPToolResult({"results": self.runtime.search_cognition(query, limit=limit)})

    def search_memory(self, *, query: str, limit: int = 20) -> MCPToolResult:
        return self.search_cognition(query=query, limit=limit)

    def timeline(self, *, branch: str | None = None, limit: int = 50) -> MCPToolResult:
        return MCPToolResult(
            {
                "events": [
                    event.model_dump(mode="json")
                    for event in self.runtime.timeline(branch=branch, limit=limit)
                ]
            }
        )

    def assumptions(self, *, context_hash: str | None = None) -> MCPToolResult:
        return MCPToolResult(
            {
                "assumptions": [
                    assumption.model_dump(mode="json")
                    for assumption in self.runtime.assumptions(context_hash=context_hash)
                ]
            }
        )
