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
from synap_git.storage.global_memory import GlobalMemoryStore


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
async def test_mcp_tool_schemas_and_descriptions(mcp_server: SynapMCPServer) -> None:
    tools = await mcp_server.mcp.list_tools()
    assert len(tools) == 10

    tool_names = {t.name for t in tools}
    expected_tools = {
        "get_session_preamble",
        "search",
        "get_outline",
        "get_skeleton",
        "read_symbol",
        "create_checkpoint",
        "remember",
        "recall",
        "list_global_memories",
        "ingest_global_memory",
    }
    assert tool_names == expected_tools

    for t in tools:
        assert t.description is not None, f"Tool {t.name} has missing description."
        assert len(t.description.strip()) > 10, f"Tool {t.name} description is too short."

    # Check create_checkpoint schema defaults
    cp_tool = next(t for t in tools if t.name == "create_checkpoint")
    cp_props = cp_tool.inputSchema.get("properties", {})
    assert "doing" in cp_props
    assert "next_step" in cp_props
    assert "blockers" in cp_props
    assert "doing" in cp_tool.inputSchema.get("required", [])

    # Check search schema
    search_tool = next(t for t in tools if t.name == "search")
    s_props = search_tool.inputSchema.get("properties", {})
    assert "query" in s_props
    assert "summary_only" in s_props
    assert "query" in search_tool.inputSchema.get("required", [])


@pytest.mark.asyncio
async def test_mcp_search(mcp_server: SynapMCPServer, monkeypatch: pytest.MonkeyPatch) -> None:
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
        return "mock result", mock_sources, {"debug": True}

    monkeypatch.setattr(mcp_server.facade.runtime, "query_hybrid", mock_query)

    # 1. Default summary_only=True
    res_default = await mcp_server.mcp.call_tool("search", {"query": "parse_code"})
    data_default = _parse_res(res_default)
    assert data_default["ok"] is True
    assert data_default["data"]["total_matches"] == 1
    assert data_default["data"]["matches"][0]["symbol"] == "parse_code"

    # 2. summary_only=False
    res_full = await mcp_server.mcp.call_tool(
        "search", {"query": "parse_code", "summary_only": False}
    )
    data_full = _parse_res(res_full)
    assert data_full["ok"] is True
    assert data_full["data"]["result"] == "mock result"


@pytest.mark.asyncio
async def test_mcp_checkpoint_and_preamble(mcp_server: SynapMCPServer) -> None:
    # 1. Create Checkpoint
    res_create = await mcp_server.mcp.call_tool(
        "create_checkpoint",
        {
            "doing": "refactoring auth logic",
            "changed_files": ["auth.py"],
            "next_step": "write unit tests",
            "blockers": "none",
        },
    )
    data_create = _parse_res(res_create)
    assert data_create["ok"] is True
    assert "checkpoint_id" in data_create["data"]

    # 2. Preamble should reflect checkpoint
    res_preamble = await mcp_server.mcp.call_tool("get_session_preamble", {})
    data_preamble = _parse_res(res_preamble)
    assert data_preamble["ok"] is True
    assert data_preamble["data"]["latest_checkpoint"]["doing"] == "refactoring auth logic"
    assert "SYNAPSE STRUCTURAL PREAMBLE" in data_preamble["data"]["compact_preamble"]

    # 3. Facade restore_checkpoint should succeed
    restored = mcp_server.facade.restore_checkpoint("latest")
    assert restored["doing"] == "refactoring auth logic"


@pytest.mark.asyncio
async def test_mcp_security_redaction(mcp_server: SynapMCPServer) -> None:
    secret_key = "sk-12345678901234567890123456789012"

    # Secret should be redacted in create_checkpoint
    await mcp_server.mcp.call_tool(
        "create_checkpoint",
        {
            "doing": f"Configured API key {secret_key}",
            "changed_files": ["key.env"],
            "next_step": "deploy",
            "blockers": "none",
        },
    )
    pre = await mcp_server.mcp.call_tool("get_session_preamble", {})
    data_pre = _parse_res(pre)
    assert secret_key not in data_pre["data"]["latest_checkpoint"]["doing"]
    assert "[REDACTED]" in data_pre["data"]["latest_checkpoint"]["doing"]

    # Secret should be redacted in remember
    rem_res = await mcp_server.mcp.call_tool(
        "remember",
        {
            "key": "prod_secret",
            "content": f"Bearer {secret_key}",
            "summary": "prod token",
        },
    )
    assert _parse_res(rem_res)["ok"] is True

    rec_res = await mcp_server.mcp.call_tool("recall", {"key": "prod_secret"})
    data_rec = _parse_res(rec_res)
    assert secret_key not in data_rec["data"]["memories"][0]["payload"]
    assert "[REDACTED]" in data_rec["data"]["memories"][0]["payload"]


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
    data = _parse_res(res)
    assert data["ok"] is True
    assert data["data"]["path"] == "src/main.py"
    assert data["data"]["symbol_count"] == 1
    assert data["data"]["symbols"][0]["name"] == "process_items"


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
    data_rem = _parse_res(res_rem)
    assert data_rem["ok"] is True
    assert data_rem["data"]["key"] == "auth_policy"

    # 2. Recall by key
    res_rec = await mcp_server.mcp.call_tool("recall", {"key": "auth_policy"})
    data_rec = _parse_res(res_rec)
    assert data_rec["ok"] is True
    assert data_rec["data"]["count"] == 1
    assert "900 seconds" in data_rec["data"]["memories"][0]["payload"]

    # 3. Check preamble includes recent memories
    res_pre = await mcp_server.mcp.call_tool("get_session_preamble", {})
    data_pre = _parse_res(res_pre)
    assert data_pre["ok"] is True
    assert "recent_memories" in data_pre["data"]
    assert len(data_pre["data"]["recent_memories"]) >= 1


@pytest.mark.asyncio
async def test_mcp_skeleton(mcp_server: SynapMCPServer) -> None:
    test_file = mcp_server.facade.runtime.settings.repository_path / "sample_skel.py"
    test_file.write_text(
        "class Worker:\n    def run(self, x: int) -> str:\n        # implementation\n        return str(x * 2)\n",
        encoding="utf-8",
    )
    try:
        res_skel = await mcp_server.mcp.call_tool("get_skeleton", {"file_path": "sample_skel.py"})
        data_skel = _parse_res(res_skel)
        assert data_skel["ok"] is True
        assert "class Worker:" in data_skel["data"]["skeleton"]
        assert "def run(self, x: int) -> str:" in data_skel["data"]["skeleton"]
        assert "return str(x * 2)" not in data_skel["data"]["skeleton"]
    finally:
        test_file.unlink(missing_ok=True)


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
async def test_mcp_global_memory_tools(
    mcp_server: SynapMCPServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Use isolated global DB for testing
    test_global_db = tmp_path / "global_test.db"
    store = GlobalMemoryStore(db_path=test_global_db)
    monkeypatch.setattr(GlobalMemoryStore, "DEFAULT_DB_PATH", test_global_db)

    added = store.add_memory(
        context_key="team_style",
        content="Prefer explicit typing and pydantic models",
        category="style",
        summary="Strict typing",
        tags=["python", "types"],
    )
    gid = added["global_id"]

    # 1. list_global_memories tool
    res_list = await mcp_server.mcp.call_tool("list_global_memories", {"query": "typing"})
    data_list = _parse_res(res_list)
    assert data_list["ok"] is True
    assert data_list["data"]["count"] >= 1
    assert data_list["data"]["memories"][0]["context_key"] == "team_style"

    # 2. ingest_global_memory tool
    res_ingest = await mcp_server.mcp.call_tool("ingest_global_memory", {"global_id": gid})
    data_ingest = _parse_res(res_ingest)
    assert data_ingest["ok"] is True
    assert data_ingest["data"]["key"] == "team_style"

    # 3. Verify memory is now recalled in repository local memory
    res_recall = await mcp_server.mcp.call_tool("recall", {"key": "team_style"})
    data_recall = _parse_res(res_recall)
    assert data_recall["ok"] is True
    assert data_recall["data"]["count"] == 1
    assert "pydantic models" in data_recall["data"]["memories"][0]["payload"]


@pytest.mark.asyncio
async def test_mcp_error_responses(mcp_server: SynapMCPServer) -> None:
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
    assert mean_ms < 50.0, (
        f"Expected preamble latency < 50ms, got mean {mean_ms:.2f}ms: {durations_ms}"
    )


def test_mcp_facade_compatibility(mcp_server: SynapMCPServer) -> None:
    """Ensure SynapMCPFacade python methods continue to work for non-MCP callers."""
    status = mcp_server.facade.get_status()
    assert "branch" in status
    assert "files" in status

    cfg = mcp_server.facade.get_mcp_config(ide="cursor")
    assert cfg["command"] in ("synap", "python")
    assert "mcpServers" in cfg

    diff = mcp_server.facade.get_diff()
    assert "diff" in diff

    tests = mcp_server.facade.get_test_recommendations()
    assert "recommended_command" in tests
    assert "test_files" in tests

    blast = mcp_server.facade.get_blast_radius()
    assert "touched_symbols" in blast
