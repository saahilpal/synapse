from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from mcp.types import TextContent

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime
from synap_git.mcp.server import SynapMCPServer


def _parse_res(res: Sequence[Any]) -> dict[str, Any]:
    content = res[0]
    assert isinstance(content, TextContent)
    return json.loads(content.text)  # type: ignore[no-any-return]


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


@pytest.mark.asyncio
async def test_mcp_get_session_preamble(mcp_server: SynapMCPServer) -> None:
    # 1. Create a checkpoint
    await mcp_server.mcp.call_tool(
        "create_checkpoint",
        {
            "doing": "init session",
            "changed_files": ["main.py"],
            "next_step": "build feature",
            "blockers": "none",
        },
    )
    # 2. Log a decision
    await mcp_server.mcp.call_tool(
        "log_decision",
        {"content": "Use FastAPI", "context_info": "High throughput"},
    )

    # 3. Request preamble
    results = await mcp_server.mcp.call_tool("get_session_preamble", {})
    content = results[0]
    assert isinstance(content, TextContent)
    res = json.loads(content.text)

    assert res["ok"] is True
    data = res["data"]
    assert "branch" in data
    assert data["latest_checkpoint"]["doing"] == "init session"
    assert len(data["recent_decisions"]) >= 1


@pytest.mark.asyncio
async def test_mcp_search_summary_only(
    mcp_server: SynapMCPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_sources = [
        {
            "symbol_id": "sym1",
            "name": "parse_code",
            "kind": "function",
            "source_path": "parser.py",
            "start_line": 10,
            "end_line": 25,
            "reason": "lexical_match",
        }
    ]

    def mock_query(
        query: str, max_tokens: int, synthesize_answer: bool = False
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        return "full text", mock_sources, {"debug": True}

    monkeypatch.setattr(mcp_server.facade.runtime, "query_hybrid", mock_query)

    results = await mcp_server.mcp.call_tool(
        "search", {"query": "parse_code", "summary_only": True}
    )
    content = results[0]
    assert isinstance(content, TextContent)
    res = json.loads(content.text)

    assert res["ok"] is True
    assert res["data"]["total_matches"] == 1
    assert res["data"]["matches"][0]["symbol"] == "parse_code"
    assert res["data"]["matches"][0]["lines"] == "10-25"


@pytest.mark.asyncio
async def test_mcp_security_redaction(mcp_server: SynapMCPServer) -> None:
    # Secret should be redacted in checkpoint
    secret_key = "sk-12345678901234567890123456789012"
    await mcp_server.mcp.call_tool(
        "create_checkpoint",
        {
            "doing": f"Using secret {secret_key}",
            "changed_files": ["key.env"],
            "next_step": "test",
            "blockers": "none",
        },
    )
    results = await mcp_server.mcp.call_tool("restore_checkpoint", {})
    content = results[0]
    assert isinstance(content, TextContent)
    res = json.loads(content.text)
    assert secret_key not in res["data"]["doing"]
    assert "[REDACTED]" in res["data"]["doing"]

    # Secret should be redacted in decision
    dec_res = await mcp_server.mcp.call_tool(
        "log_decision",
        {"content": f"Bearer token is Bearer {secret_key}", "context_info": "auth setup"},
    )
    dec_content = dec_res[0]
    assert isinstance(dec_content, TextContent)
    dec_data = json.loads(dec_content.text)
    assert dec_data["ok"] is True


@pytest.mark.asyncio
async def test_mcp_get_outline(mcp_server: SynapMCPServer) -> None:
    mcp_server.facade.runtime.store.upsert_file_and_symbols(
        file_id="fid_main",
        path="src/main.py",
        git_oid="oid123",
        content_hash="hash123",
        language="python",
        symbols=[
            {
                "symbol_id": "sym_main_func",
                "name": "process_items",
                "kind": "function",
                "start_line": 15,
                "end_line": 35,
                "ast_hash": "as123",
                "metadata": {},
            }
        ],
    )

    res = await mcp_server.mcp.call_tool("get_outline", {"file_path": "src/main.py"})
    content = res[0]
    assert isinstance(content, TextContent)
    data = json.loads(content.text)

    assert data["ok"] is True
    assert data["data"]["path"] == "src/main.py"
    assert data["data"]["symbol_count"] == 1
    assert data["data"]["symbols"][0]["name"] == "process_items"


@pytest.mark.asyncio
async def test_mcp_get_neighborhood(mcp_server: SynapMCPServer) -> None:
    mcp_server.facade.runtime.store.upsert_file_and_symbols(
        file_id="fid1",
        path="src/a.py",
        git_oid="oid1",
        content_hash="h1",
        language="python",
        symbols=[
            {
                "symbol_id": "sA",
                "name": "funcA",
                "kind": "function",
                "start_line": 1,
                "end_line": 10,
                "ast_hash": "hA",
                "metadata": {},
            },
        ],
    )
    mcp_server.facade.runtime.store.upsert_file_and_symbols(
        file_id="fid2",
        path="src/b.py",
        git_oid="oid2",
        content_hash="h2",
        language="python",
        symbols=[
            {
                "symbol_id": "sB",
                "name": "funcB",
                "kind": "function",
                "start_line": 1,
                "end_line": 10,
                "ast_hash": "hB",
                "metadata": {},
            },
        ],
    )
    with mcp_server.facade.runtime.store.connect() as conn:
        conn.execute(
            "INSERT INTO edges (edge_id, source_symbol, target_symbol, edge_type) VALUES ('e1', 'sA', 'sB', 'calls')"
        )

    res = await mcp_server.mcp.call_tool(
        "get_neighborhood", {"symbol": "funcA", "direction": "downstream"}
    )
    content = res[0]
    assert isinstance(content, TextContent)
    data = json.loads(content.text)

    assert data["ok"] is True
    assert data["data"]["neighbors_count"] >= 1
    assert any(n["name"] == "funcB" for n in data["data"]["neighbors"])


@pytest.mark.asyncio
async def test_mcp_remember_and_recall(mcp_server: SynapMCPServer) -> None:
    # 1. Remember a key/content observation
    res_rem = await mcp_server.mcp.call_tool(
        "remember",
        {
            "key": "auth_policy",
            "content": "Access tokens expire after 900 seconds. Use refresh_token endpoint.",
            "summary": "15-minute token TTL",
        },
    )
    content_rem = res_rem[0]
    assert isinstance(content_rem, TextContent)
    data_rem = json.loads(content_rem.text)
    assert data_rem["ok"] is True
    assert data_rem["data"]["key"] == "auth_policy"

    # 2. Recall by key
    res_rec = await mcp_server.mcp.call_tool("recall", {"key": "auth_policy"})
    content_rec = res_rec[0]
    assert isinstance(content_rec, TextContent)
    data_rec = json.loads(content_rec.text)
    assert data_rec["ok"] is True
    assert data_rec["data"]["count"] == 1
    assert "900 seconds" in data_rec["data"]["memories"][0]["payload"]

    # 3. Check preamble includes recent memories
    res_pre = await mcp_server.mcp.call_tool("get_session_preamble", {})
    content_pre = res_pre[0]
    assert isinstance(content_pre, TextContent)
    data_pre = json.loads(content_pre.text)
    assert data_pre["ok"] is True
    assert "recent_memories" in data_pre["data"]
    assert len(data_pre["data"]["recent_memories"]) >= 1
    assert data_pre["data"]["recent_memories"][0]["context_key"] == "auth_policy"
    assert "blast_radius" in data_pre["data"]
    assert "architectural_hubs" in data_pre["data"]


@pytest.mark.asyncio
async def test_mcp_skeleton_and_blast_radius(mcp_server: SynapMCPServer, tmp_path: Path) -> None:
    # 1. Test get_skeleton on a real python file
    test_file = mcp_server.facade.runtime.settings.repository_path / "sample_skel.py"
    test_file.write_text(
        "class Worker:\n    def run(self, x: int) -> str:\n        # implementation\n        return str(x * 2)\n",
        encoding="utf-8",
    )
    try:
        res_skel = await mcp_server.mcp.call_tool("get_skeleton", {"file_path": "sample_skel.py"})
        content_skel = res_skel[0]
        assert isinstance(content_skel, TextContent)
        data_skel = json.loads(content_skel.text)
        assert data_skel["ok"] is True
        assert "class Worker:" in data_skel["data"]["skeleton"]
        assert "def run(self, x: int) -> str:" in data_skel["data"]["skeleton"]
        assert "return str(x * 2)" not in data_skel["data"]["skeleton"]
    finally:
        test_file.unlink(missing_ok=True)

    # 2. Test get_blast_radius tool
    res_blast = await mcp_server.mcp.call_tool("get_blast_radius", {})
    content_blast = res_blast[0]
    assert isinstance(content_blast, TextContent)
    data_blast = json.loads(content_blast.text)
    assert data_blast["ok"] is True
    assert "touched_symbols" in data_blast["data"]


@pytest.mark.asyncio
async def test_mcp_new_ergonomic_tools(mcp_server: SynapMCPServer) -> None:
    # 1. create_checkpoint with omitted changed_files
    res_cp = await mcp_server.mcp.call_tool(
        "create_checkpoint",
        {"doing": "exploring architecture"},
    )
    data_cp = _parse_res(res_cp)
    assert data_cp["ok"] is True
    cp_id = data_cp["data"]["checkpoint_id"]

    # 2. list_checkpoints
    res_list = await mcp_server.mcp.call_tool("list_checkpoints", {"limit": 3})
    data_list = _parse_res(res_list)
    assert data_list["ok"] is True
    assert data_list["data"]["count"] >= 1

    # 3. restore_checkpoint by ID
    res_restore = await mcp_server.mcp.call_tool("restore_checkpoint", {"checkpoint_id": cp_id})
    data_restore = _parse_res(res_restore)
    assert data_restore["ok"] is True
    assert data_restore["data"]["doing"] == "exploring architecture"

    # 4. read_symbol on indexed file
    test_file = mcp_server.facade.runtime.settings.repository_path / "foo.py"
    test_file.write_text("def my_func():\n    return 42\n", encoding="utf-8")
    try:
        mcp_server.facade.runtime.store.upsert_file_and_symbols(
            file_id="fid_foo",
            path="foo.py",
            git_oid="oid_foo",
            content_hash="h_foo",
            language="python",
            symbols=[
                {
                    "symbol_id": "s_foo",
                    "name": "my_func",
                    "kind": "function",
                    "start_line": 1,
                    "end_line": 2,
                    "ast_hash": "h_func",
                    "metadata": {},
                }
            ],
        )
        res_sym = await mcp_server.mcp.call_tool(
            "read_symbol", {"symbol": "my_func", "file_path": "foo.py"}
        )
        data_sym = _parse_res(res_sym)
        assert data_sym["ok"] is True
        assert data_sym["data"]["name"] == "my_func"
        assert "return 42" in data_sym["data"]["code"]
    finally:
        test_file.unlink(missing_ok=True)

    # 5. get_diff and get_test_recommendations
    res_diff = await mcp_server.mcp.call_tool("get_diff", {})
    assert _parse_res(res_diff)["ok"] is True

    res_tests = await mcp_server.mcp.call_tool("get_test_recommendations", {})
    assert _parse_res(res_tests)["ok"] is True


@pytest.mark.asyncio
async def test_mcp_read_symbol_ambiguous_across_files(mcp_server: SynapMCPServer) -> None:
    repo = mcp_server.facade.runtime.settings.repository_path
    f1 = repo / "pkg1.py"
    f2 = repo / "pkg2.py"
    f1.write_text("def compute():\n    return 'from_pkg1'\n", encoding="utf-8")
    f2.write_text("def compute():\n    return 'from_pkg2'\n", encoding="utf-8")

    try:
        mcp_server.facade.runtime.store.upsert_file_and_symbols(
            file_id="fid_pkg1",
            path="pkg1.py",
            git_oid="oid1",
            content_hash="h1",
            language="python",
            symbols=[
                {
                    "symbol_id": "sym_p1",
                    "name": "compute",
                    "kind": "function",
                    "start_line": 1,
                    "end_line": 2,
                    "ast_hash": "h_c1",
                    "metadata": {},
                }
            ],
        )
        mcp_server.facade.runtime.store.upsert_file_and_symbols(
            file_id="fid_pkg2",
            path="pkg2.py",
            git_oid="oid2",
            content_hash="h2",
            language="python",
            symbols=[
                {
                    "symbol_id": "sym_p2",
                    "name": "compute",
                    "kind": "function",
                    "start_line": 1,
                    "end_line": 2,
                    "ast_hash": "h_c2",
                    "metadata": {},
                }
            ],
        )

        # 1. Ambiguous lookup without file_path should fail with AMBIGUOUS_SYMBOL
        res_ambig = await mcp_server.mcp.call_tool("read_symbol", {"symbol": "compute"})
        data_ambig = _parse_res(res_ambig)
        assert data_ambig["ok"] is False
        assert data_ambig["error"]["code"] == "AMBIGUOUS_SYMBOL"
        assert "candidates" in data_ambig["error"]
        assert "pkg1.py" in data_ambig["error"]["candidates"]
        assert "pkg2.py" in data_ambig["error"]["candidates"]

        # 2. Disambiguated lookup with file_path succeeds
        res_p1 = await mcp_server.mcp.call_tool(
            "read_symbol", {"symbol": "compute", "file_path": "pkg1.py"}
        )
        data_p1 = _parse_res(res_p1)
        assert data_p1["ok"] is True
        assert "from_pkg1" in data_p1["data"]["code"]

        res_p2 = await mcp_server.mcp.call_tool(
            "read_symbol", {"symbol": "compute", "file_path": "pkg2.py"}
        )
        data_p2 = _parse_res(res_p2)
        assert data_p2["ok"] is True
        assert "from_pkg2" in data_p2["data"]["code"]
    finally:
        f1.unlink(missing_ok=True)
        f2.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_mcp_get_mcp_config(mcp_server: SynapMCPServer) -> None:
    # 1. Retrieve config snippet
    res = await mcp_server.mcp.call_tool("get_mcp_config", {"ide": "cursor"})
    data = _parse_res(res)
    assert data["ok"] is True
    assert data["data"]["command"] == "synap"
    assert data["data"]["args"] == ["mcp", "serve"]
    assert "synap" in data["data"]["mcpServers"]
    assert data["data"]["mcpServers"]["synap"]["command"] == "synap"
    assert data["data"]["mcpServers"]["synap"]["args"] == ["mcp", "serve"]

    # 2. Export config to a file
    repo = mcp_server.facade.runtime.settings.repository_path
    export_rel = ".cursor/mcp.json"
    res_export = await mcp_server.mcp.call_tool(
        "get_mcp_config", {"ide": "cursor", "export_path": export_rel}
    )
    data_export = _parse_res(res_export)
    assert data_export["ok"] is True
    assert data_export["data"]["exported"] is True
    target_file = repo / export_rel
    assert target_file.exists()
    saved_cfg = json.loads(target_file.read_text(encoding="utf-8"))
    assert saved_cfg["mcpServers"]["synap"]["command"] == "synap"
    assert saved_cfg["mcpServers"]["synap"]["args"] == ["mcp", "serve"]


@pytest.mark.asyncio
async def test_mcp_preamble_latency_clean_indexed(tmp_path: Path) -> None:
    import subprocess
    import time

    # Initialize a clean git repo
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "hello.py").write_text("def run(): return 42\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".synap/\n.synapse/\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial clean"], cwd=tmp_path, check=True, capture_output=True
    )

    settings = SynapSettings(
        repository_path=tmp_path,
        state_path=tmp_path / ".synap",
        profile=RuntimeProfile.TEST,
    )
    r = SynapRuntime(settings)
    r.bootstrap()

    # Re-commit if bootstrap touched .gitignore
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    status_proc = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True
    )
    if status_proc.stdout.strip():
        subprocess.run(
            ["git", "commit", "-m", "clean state"], cwd=tmp_path, check=True, capture_output=True
        )

    r.index_repository()
    server = SynapMCPServer(r)

    # Warm-up call
    await server.mcp.call_tool("get_session_preamble", {})

    # Measure latency across 5 successive calls
    durations_ms: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        res = await server.mcp.call_tool("get_session_preamble", {})
        durations_ms.append((time.perf_counter() - t0) * 1000)
        assert _parse_res(res)["ok"] is True

    mean_ms = sum(durations_ms) / len(durations_ms)
    # Preamble latency MUST be < 50ms when repository is clean or already indexed
    assert mean_ms < 50.0, (
        f"Expected preamble latency < 50ms, got mean {mean_ms:.2f}ms: {durations_ms}"
    )


@pytest.mark.asyncio
async def test_mcp_tool_schemas_and_descriptions(mcp_server: SynapMCPServer) -> None:
    tools = await mcp_server.mcp.list_tools()
    assert len(tools) >= 20

    tool_names = {t.name for t in tools}
    assert "get_status" in tool_names
    assert "get_session_preamble" in tool_names
    assert "get_mcp_config" in tool_names
    assert "read_symbol" in tool_names
    assert "create_checkpoint" in tool_names
    assert "log_decision" in tool_names

    # Check descriptions are non-empty and descriptive
    for t in tools:
        assert t.description is not None, f"Tool {t.name} has missing description."
        assert len(t.description.strip()) > 10, f"Tool {t.name} has too short description."

    # Check create_checkpoint schema defaults
    cp_tool = next(t for t in tools if t.name == "create_checkpoint")
    cp_props = cp_tool.inputSchema.get("properties", {})
    assert "doing" in cp_props
    assert "changed_files" in cp_props
    # doing is required, changed_files has default/optional
    assert "doing" in cp_tool.inputSchema.get("required", [])
    assert "changed_files" not in cp_tool.inputSchema.get("required", [])

    # Check log_decision schema defaults: context_info should not be required
    ld_tool = next(t for t in tools if t.name == "log_decision")
    assert "content" in ld_tool.inputSchema.get("required", [])
    assert "context_info" not in ld_tool.inputSchema.get("required", [])


@pytest.mark.asyncio
async def test_mcp_error_responses_conform_to_fastmcp(mcp_server: SynapMCPServer) -> None:
    # 1. Invalid argument (empty doing)
    res_val = await mcp_server.mcp.call_tool("create_checkpoint", {"doing": "   "})
    data_val = _parse_res(res_val)
    assert data_val["ok"] is False
    assert data_val["error"]["code"] == "INVALID_ARGUMENT"
    assert "suggestion" in data_val["error"]

    # 2. Not found error
    res_nf = await mcp_server.mcp.call_tool("get_outline", {"file_path": "nonexistent.py"})
    data_nf = _parse_res(res_nf)
    assert data_nf["ok"] is False
    assert data_nf["error"]["code"] == "NOT_FOUND"
