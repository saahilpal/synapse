from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mcp.types import TextContent

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime
from synap_git.mcp.server import SynapMCPServer


@pytest.fixture
def runtime(tmp_path: Path) -> SynapRuntime:
    settings = SynapSettings(
        repository_path=tmp_path,
        state_path=tmp_path / ".synap",
        profile=RuntimeProfile.TEST,
    )
    r = SynapRuntime(settings)
    r.initialize_storage()
    return r


@pytest.fixture
def mcp_server(runtime: SynapRuntime) -> SynapMCPServer:
    return SynapMCPServer(runtime)


@pytest.mark.asyncio
async def test_mcp_get_status(mcp_server: SynapMCPServer) -> None:
    results = await mcp_server.mcp.call_tool("get_status", {})
    content = results[0]
    assert isinstance(content, TextContent)
    result = json.loads(content.text)

    assert result["ok"] is True
    assert "symbols" in result["data"]


@pytest.mark.asyncio
async def test_mcp_search(mcp_server: SynapMCPServer, monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_query(query: str, max_tokens: int) -> tuple[str, str, dict[str, Any]]:
        return "mock result", "mock context", {"debug": True}

    monkeypatch.setattr(mcp_server.facade.runtime, "query_hybrid", mock_query)

    results = await mcp_server.mcp.call_tool("search", {"query": "test"})
    content = results[0]
    assert isinstance(content, TextContent)
    result = json.loads(content.text)

    assert result["ok"] is True
    assert result["data"]["result"] == "mock result"


@pytest.mark.asyncio
async def test_mcp_checkpoint_lifecycle(mcp_server: SynapMCPServer) -> None:
    # 1. Create
    results_create = await mcp_server.mcp.call_tool(
        "create_checkpoint",
        {
            "doing": "working on tests",
            "changed_files": ["tests/test_mcp.py"],
            "next_step": "finish tests",
            "blockers": "none",
        },
    )
    content_create = results_create[0]
    assert isinstance(content_create, TextContent)
    res_create = json.loads(content_create.text)
    assert res_create["ok"] is True

    # 2. Restore
    results_restore = await mcp_server.mcp.call_tool("restore_checkpoint", {})
    content_restore = results_restore[0]
    assert isinstance(content_restore, TextContent)
    res_restore = json.loads(content_restore.text)
    assert res_restore["ok"] is True
    assert res_restore["data"]["doing"] == "working on tests"


@pytest.mark.asyncio
async def test_mcp_log_decision(mcp_server: SynapMCPServer) -> None:
    results = await mcp_server.mcp.call_tool(
        "log_decision", {"content": "Use batching", "context_info": "Avoid N+1"}
    )
    content = results[0]
    assert isinstance(content, TextContent)
    res = json.loads(content.text)

    assert res["ok"] is True
    assert "decision_id" in res["data"]


@pytest.mark.asyncio
async def test_mcp_verify_system(mcp_server: SynapMCPServer) -> None:
    results = await mcp_server.mcp.call_tool("verify_system", {})
    content = results[0]
    assert isinstance(content, TextContent)
    res = json.loads(content.text)

    assert res["ok"] is True
    assert "database_integrity" in res["data"]


@pytest.mark.asyncio
async def test_mcp_memory_tools(mcp_server: SynapMCPServer) -> None:
    # Create a pending lesson via DB
    with mcp_server.facade.runtime.store.connect() as conn:
        conn.execute(
            """
            INSERT INTO lessons (lesson_id, branch, revert_commit, reverted_from, what_failed, why_failed, files_affected, status, created_at, expires_at)
            VALUES ('L1', 'main', 'h1', 'h0', 'failed', 'pending reason', '[]', 'pending', 0, 9999999999)
        """
        )

    # Test get_pending
    results_pending = await mcp_server.mcp.call_tool("get_pending_memory", {})
    content_pending = results_pending[0]
    assert isinstance(content_pending, TextContent)
    res_pending = json.loads(content_pending.text)
    assert len(res_pending["data"]["lessons"]) == 1

    # Submit analysis
    results_submit = await mcp_server.mcp.call_tool(
        "submit_lesson_analysis", {"lesson_id": "L1", "why_failed": "Updated reason"}
    )
    content_submit = results_submit[0]
    assert isinstance(content_submit, TextContent)
    res_submit = json.loads(content_submit.text)
    assert res_submit["ok"] is True

    # Approve lesson
    with mcp_server.facade.runtime.store.connect() as conn:
        conn.execute("UPDATE lessons SET status = 'approved' WHERE lesson_id = 'L1'")

    # Test get_approved
    results_approved = await mcp_server.mcp.call_tool("get_approved_memory", {})
    content_approved = results_approved[0]
    assert isinstance(content_approved, TextContent)
    res_approved = json.loads(content_approved.text)
    assert len(res_approved["data"]["lessons"]) == 1


@pytest.mark.asyncio
async def test_mcp_error_handling(mcp_server: SynapMCPServer) -> None:
    # Restore with no checkpoints should return error
    results = await mcp_server.mcp.call_tool("restore_checkpoint", {})
    content = results[0]
    assert isinstance(content, TextContent)
    res = json.loads(content.text)

    assert res["ok"] is False
    assert res["error"]["code"] == "NOT_FOUND"
