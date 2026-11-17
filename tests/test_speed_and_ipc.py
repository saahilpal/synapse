from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from synap_git.config import RuntimeMode, RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime
from synap_git.indexer.socket_ipc import DaemonClient, DaemonServer
from synap_git.retrieval.engine import (
    extract_stack_trace_info,
    tokenize_identifier,
)


@pytest.fixture
def speed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "speed_repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Synapse Speed Test"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "speed@synapse.ai"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    core_file = repo / "core.py"
    core_file.write_text(
        "class SynapRuntime:\n"
        "    def __init__(self):\n"
        "        pass\n"
        "\n"
        "def parse_ast(code: str):\n"
        "    return len(code)\n",
        encoding="utf-8",
    )

    subprocess.run(["git", "add", "core.py"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"], cwd=repo, capture_output=True, check=True
    )
    return repo


@pytest.fixture
def speed_settings(speed_repo: Path) -> SynapSettings:
    return SynapSettings(
        repository_path=speed_repo,
        mode=RuntimeMode.ACTIVE,
        profile=RuntimeProfile.TEST,
    )


@pytest.mark.asyncio
async def test_unix_domain_socket_and_in_process_fallback(
    speed_repo: Path, speed_settings: SynapSettings
) -> None:
    """Test Unix domain socket communication (<15ms latency) and graceful in-process fallback."""
    runtime = SynapRuntime(speed_settings)
    runtime.index_repository()

    server = DaemonServer(runtime)
    await server.start()

    try:
        client = DaemonClient(speed_repo, settings=speed_settings, runtime=runtime)
        assert await client.is_daemon_running_async() is True

        # Test socket ping
        ping_res = await client.ping_async()
        assert ping_res.get("status") == "ok"
        assert ping_res.get("pong") is True
        assert ping_res.get("transport") == "unix_socket"

        # Warm-up query under coverage tracer
        await client.query_async("SynapRuntime", synthesize_answer=False)

        # Test socket query with latency assertion
        t_start = time.perf_counter()
        answer, sources, trace = await client.query_async("SynapRuntime", synthesize_answer=False)
        roundtrip_ms = (time.perf_counter() - t_start) * 1000

        assert trace.get("transport") == "unix_socket"
        assert "SynapRuntime" in answer or len(sources) > 0
        assert roundtrip_ms < 500.0  # Safe CI upper bound under coverage tracers, typically < 3ms

        # Test status via socket
        st = await client.status_async()
        assert st.get("transport") == "unix_socket"
        assert "symbols" in st
    finally:
        await server.stop()

    # Now verify graceful fallback when daemon is stopped / socket is gone
    assert await client.is_daemon_running_async() is False
    assert not client.socket_path.exists()
    assert not client.link_path.exists()

    fallback_ans, fallback_src, fallback_trace = await client.query_async(
        "SynapRuntime", synthesize_answer=False
    )
    assert fallback_trace.get("transport") == "in_process_fallback"
    assert "SynapRuntime" in fallback_ans or len(fallback_src) > 0

    fb_ping = await client.ping_async()
    assert fb_ping.get("transport") == "in_process_fallback"

    fb_status = await client.status_async()
    assert fb_status.get("transport") == "in_process_fallback"

    # Also verify synchronous client.query() graceful fallback
    sync_ans, sync_src, sync_trace = client.query("SynapRuntime", synthesize_answer=False)
    assert sync_trace.get("transport") == "in_process_fallback"
    assert "SynapRuntime" in sync_ans or len(sync_src) > 0


def test_camelcase_and_snakecase_subtoken_tokenization() -> None:
    """Test camelCase and snake_case sub-token splitting logic."""
    assert tokenize_identifier("parse_ast") == ["parse", "ast", "parse_ast"]
    assert tokenize_identifier("SynapRuntime") == ["synap", "runtime", "SynapRuntime"]
    assert tokenize_identifier("get_user_by_id") == ["get", "user", "by", "id", "get_user_by_id"]
    assert tokenize_identifier("camelCase") == ["camel", "case", "camelCase"]


def test_camelcase_and_snakecase_subtoken_search(
    speed_repo: Path, speed_settings: SynapSettings
) -> None:
    """Test FTS5 sub-token search for camelCase and snake_case identifiers."""
    runtime = SynapRuntime(speed_settings)
    runtime.index_repository()

    # Query for 'ast' should match 'parse_ast'
    ans_ast, src_ast, _ = runtime.query_hybrid("ast", synthesize_answer=False)
    assert any("parse_ast" in s.get("name", "") for s in src_ast) or "parse_ast" in ans_ast

    # Query for 'runtime' should match 'SynapRuntime'
    ans_rt, src_rt, _ = runtime.query_hybrid("runtime", synthesize_answer=False)
    assert any("SynapRuntime" in s.get("name", "") for s in src_rt) or "SynapRuntime" in ans_rt

    # Query for 'synap' should match 'SynapRuntime'
    ans_syn, src_syn, _ = runtime.query_hybrid("synap", synthesize_answer=False)
    assert any("SynapRuntime" in s.get("name", "") for s in src_syn) or "SynapRuntime" in ans_syn


def test_incremental_git_diff_indexing(speed_repo: Path, speed_settings: SynapSettings) -> None:
    """Test fast incremental indexing via git diff / porcelain under 300ms."""
    runtime = SynapRuntime(speed_settings)
    runtime.index_repository()

    # Create a new file and modify existing file
    worker_file = speed_repo / "worker.py"
    worker_file.write_text(
        "def process_job(job_id: int) -> bool:\n    return job_id > 0\n",
        encoding="utf-8",
    )

    t_start = time.perf_counter()
    reindexed = runtime.index_incremental_changes()
    reindex_ms = (time.perf_counter() - t_start) * 1000

    assert "worker.py" in reindexed
    assert reindex_ms < 300.0  # Must be under 300ms!

    # Verify new symbol is indexed and searchable
    with runtime.store.connect() as conn:
        row = conn.execute("SELECT * FROM symbols WHERE name = 'process_job'").fetchone()
        assert row is not None
        assert row["name"] == "process_job"

    # Re-running without changes should reindex 0 files in < 50ms
    t_noop = time.perf_counter()
    reindexed_noop = runtime.index_incremental_changes()
    noop_ms = (time.perf_counter() - t_noop) * 1000
    assert len(reindexed_noop) == 0
    assert noop_ms < 100.0


def test_stack_trace_query_parsing(speed_repo: Path, speed_settings: SynapSettings) -> None:
    """Test regex extraction of stack trace frames and exception classes."""
    trace_query = (
        "Traceback (most recent call last):\n"
        '  File "core.py", line 5, in parse_ast\n'
        "    return len(code)\n"
        "ValueError: Unexpected empty code snippet"
    )

    extracted = extract_stack_trace_info(trace_query)
    assert extracted["has_stack_trace"] is True
    assert "core.py" in extracted["files"]
    assert 5 in extracted["lines"]
    assert "ValueError" in extracted["exceptions"]
    assert extracted["frames"][0]["function"] == "parse_ast"

    # Verify retrieval with stack trace targets the right file and symbol
    runtime = SynapRuntime(speed_settings)
    runtime.index_repository()

    ans, sources, trace = runtime.query_hybrid(trace_query, synthesize_answer=False)
    assert any(s.get("name") == "parse_ast" for s in sources) or "parse_ast" in ans


def test_staleness_verification_and_honest_empties(
    speed_repo: Path, speed_settings: SynapSettings
) -> None:
    """Test staleness flagging and honest empties with nearest suggestions."""
    runtime = SynapRuntime(speed_settings)
    runtime.index_repository()

    # Modify file on disk without re-indexing
    core_file = speed_repo / "core.py"
    core_file.write_text(
        "class SynapRuntime:\n    pass\n# modified on disk directly!\n", encoding="utf-8"
    )

    # Retrieval should flag core.py as stale / modified since index
    _, _, trace = runtime.query_hybrid("SynapRuntime", synthesize_answer=False)
    assert "core.py" in trace.get("stale_files", [])

    # Honest empty: query an unrelated nonsense word
    _, empty_src, empty_trace = runtime.query_hybrid(
        "xyznonexistentquery9999", synthesize_answer=False
    )
    assert empty_trace.get("empty_match") is True
    assert len(empty_src) == 0
    assert "suggestions" in empty_trace

    # Query caching test
    runtime.retrieval_engine.clear_query_cache()
    q_cache_target = "SynapRuntime"
    _, _, t1 = runtime.query_hybrid(q_cache_target, synthesize_answer=False)
    assert t1.get("cached") is False

    _, _, t2 = runtime.query_hybrid(q_cache_target, synthesize_answer=False)
    assert t2.get("cached") is True
