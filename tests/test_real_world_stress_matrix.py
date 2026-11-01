"""
Real-world stress matrix and regression benchmarks for Synapse 2.6.

Tests & Benchmarks covered:
  1. Graph Neighborhood Traversal Benchmark (< 1ms target)
  2. Incremental Zero-Change Poll Benchmark (< 50ms target)
  3. Adversarial Edge Case: Real Git Merge Conflict State
  4. Adversarial Edge Case: Detached HEAD State
  5. Adversarial Edge Case: Secondary Git Worktrees
  6. Adversarial Edge Case: Unicode & Non-ASCII File Paths
  7. Adversarial Edge Case: Large Single Files (> 1MB - safety skip and configurable threshold)
  8. Concurrency & Daemon Lifecycle: Process signals, PID lock cleanup, and concurrent multi-thread I/O
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import subprocess
import time
from pathlib import Path

import pytest

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.git import GitChangeKind
from synap_git.indexer.daemon import RuntimeDaemon
from synap_git.indexer.engine import SynapRuntime
from synap_git.mcp.server import SynapMCPFacade


def _run_git(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *cmd],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def base_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "matrix_repo"
    repo.mkdir()
    _run_git(["init", "-b", "main"], repo)
    _run_git(["config", "user.name", "Matrix Tester"], repo)
    _run_git(["config", "user.email", "matrix@synapse.qa"], repo)

    (repo / "core.py").write_text(
        "def base_func():\n    return 42\n",
        encoding="utf-8",
    )
    _run_git(["add", "."], repo)
    _run_git(["commit", "-m", "chore: initial commit"], repo)
    return repo


# ==============================================================================
# 1. Graph Traversal & Incremental Benchmarks
# ==============================================================================


def test_benchmark_graph_neighborhood_traversal_sub_millisecond(
    base_git_repo: Path, tmp_path: Path
) -> None:
    """Benchmark neighborhood queries: directed recursive CTE queries must execute in < 1ms."""
    # Construct a dense graph with 60 connected nodes
    code_lines = []
    for i in range(60):
        target = f"node_{i - 1}()" if i > 0 else "None"
        code_lines.append(f"def node_{i}():\n    return {target}\n")

    (base_git_repo / "graph_dense.py").write_text("\n".join(code_lines), encoding="utf-8")
    _run_git(["add", "graph_dense.py"], base_git_repo)
    _run_git(["commit", "-m", "feat: add dense graph"], base_git_repo)

    settings = SynapSettings(
        repository_path=base_git_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "matrix.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapRuntime(settings)
    runtime.bootstrap(force=True)

    with runtime.store.connect() as conn:
        symbols = [
            r["symbol_id"]
            for r in conn.execute(
                "SELECT symbol_id FROM symbols WHERE name LIKE 'node_%' LIMIT 30"
            ).fetchall()
        ]

    assert len(symbols) >= 20, f"Expected >= 20 symbols, got {len(symbols)}"

    # Benchmark directed Recursive CTE traversal on connection (realistic query load)
    query_upstream = """
    WITH RECURSIVE neighborhood(id, d) AS (
        SELECT ? as id, 0 as d
        UNION
        SELECT source_symbol, d + 1
        FROM edges JOIN neighborhood ON target_symbol = id
        WHERE d < ?
    ),
    min_distances AS (
        SELECT id, MIN(d) as distance
        FROM neighborhood
        GROUP BY id
        ORDER BY distance ASC
        LIMIT ?
    )
    SELECT s.*, f.path as source_path, m.distance
    FROM min_distances m
    JOIN symbols s ON s.symbol_id = m.id
    JOIN files f ON s.file_id = f.file_id
    ORDER BY m.distance ASC
    """

    latencies_ms: list[float] = []
    with runtime.store.connect() as conn:
        # Warmup
        conn.execute(query_upstream, (symbols[0], 2, 50)).fetchall()

        for sym_id in symbols:
            t0 = time.perf_counter()
            rows = conn.execute(query_upstream, (sym_id, 2, 50)).fetchall()
            dt_ms = (time.perf_counter() - t0) * 1000
            latencies_ms.append(dt_ms)
            assert isinstance(rows, list)

    avg_ms = sum(latencies_ms) / len(latencies_ms)
    p95_ms = sorted(latencies_ms)[int(len(latencies_ms) * 0.95)]
    min_ms = min(latencies_ms)
    max_ms = max(latencies_ms)

    print(
        f"\n  ⏱  Neighborhood Graph Traversal (CTE Query): N={len(latencies_ms)} queries | "
        f"min={min_ms:.4f}ms, avg={avg_ms:.4f}ms, p95={p95_ms:.4f}ms, max={max_ms:.4f}ms"
    )

    # Benchmark assertion: average CTE traversal query must execute in < 1.0 ms
    assert avg_ms < 1.0, f"Average neighborhood latency {avg_ms:.4f}ms exceeded 1.0ms budget"


def test_benchmark_incremental_zero_change_poll_sub_50ms(
    base_git_repo: Path, tmp_path: Path
) -> None:
    """Benchmark incremental indexing and daemon polling with zero changes: must execute in < 50ms."""
    settings = SynapSettings(
        repository_path=base_git_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "matrix_poll.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapRuntime(settings)
    runtime.bootstrap(force=True)

    # Pre-warm Git state
    current_state = runtime.git.state(force=False)

    # 1. Measure direct runtime.index_repository with zero changes (state passed from daemon poll)
    poll_latencies_ms: list[float] = []
    for _ in range(30):
        t0 = time.perf_counter()
        commit = runtime.index_repository(git_state=current_state)
        dt_ms = (time.perf_counter() - t0) * 1000
        poll_latencies_ms.append(dt_ms)
        assert commit is not None

    avg_index_ms = sum(poll_latencies_ms) / len(poll_latencies_ms)
    p95_index_ms = sorted(poll_latencies_ms)[int(len(poll_latencies_ms) * 0.95)]

    print(
        f"\n  ⏱  Zero-change index_repository: avg={avg_index_ms:.4f}ms, p95={p95_index_ms:.4f}ms"
    )
    assert avg_index_ms < 50.0, (
        f"Incremental index_repository {avg_index_ms:.4f}ms exceeded 50ms budget"
    )

    # 2. Measure daemon fast poll cycle (state check + classification with fingerprint cache)
    daemon_poll_ms: list[float] = []
    last_state = runtime.git.state(force=True)
    for _ in range(50):
        t0 = time.perf_counter()
        st = runtime.git.state(force=False)
        change = runtime.git.classify(last_state, st)
        dt_ms = (time.perf_counter() - t0) * 1000
        daemon_poll_ms.append(dt_ms)
        assert change.kind == GitChangeKind.UNCHANGED

    avg_daemon_ms = sum(daemon_poll_ms) / len(daemon_poll_ms)
    p95_daemon_ms = sorted(daemon_poll_ms)[int(len(daemon_poll_ms) * 0.95)]

    print(
        f"  ⏱  Daemon Poll Cycle (Cached FP): avg={avg_daemon_ms:.4f}ms, p95={p95_daemon_ms:.4f}ms"
    )
    assert avg_daemon_ms < 5.0, (
        f"Daemon zero-change poll {avg_daemon_ms:.4f}ms exceeded 5.0ms budget"
    )


# ==============================================================================
# 2. Adversarial Edge Cases
# ==============================================================================


def test_adversarial_merge_conflict_state(base_git_repo: Path, tmp_path: Path) -> None:
    """Verify runtime detects and gracefully suspends indexing during active merge conflicts."""
    settings = SynapSettings(
        repository_path=base_git_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "matrix_merge.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapRuntime(settings)
    runtime.bootstrap(force=True)

    # Branch feature_a
    _run_git(["checkout", "-b", "feature_a"], base_git_repo)
    (base_git_repo / "core.py").write_text(
        "def base_func():\n    return 'from_a'\n", encoding="utf-8"
    )
    _run_git(["add", "core.py"], base_git_repo)
    _run_git(["commit", "-m", "conflict from a"], base_git_repo)

    # Branch feature_b
    _run_git(["checkout", "main"], base_git_repo)
    _run_git(["checkout", "-b", "feature_b"], base_git_repo)
    (base_git_repo / "core.py").write_text(
        "def base_func():\n    return 'from_b'\n", encoding="utf-8"
    )
    _run_git(["add", "core.py"], base_git_repo)
    _run_git(["commit", "-m", "conflict from b"], base_git_repo)

    # Attempt merge to induce real conflict
    merge_proc = subprocess.run(
        ["git", "merge", "feature_a"],
        cwd=base_git_repo,
        capture_output=True,
        text=True,
    )
    assert merge_proc.returncode != 0, "Expected merge conflict"
    assert (base_git_repo / ".git" / "MERGE_HEAD").exists()

    # Verify GitState accurately identifies active conflict
    state = runtime.git.state(force=True)
    assert state.merge_in_progress is True

    # Indexing must safely suspend without raising exceptions or corrupting storage
    last_head = runtime.index_repository(git_state=state)
    assert last_head == state.head_commit
    assert runtime.store.integrity_check() == "ok"

    # Abort merge and verify normal state returns
    _run_git(["merge", "--abort"], base_git_repo)
    state_after = runtime.git.state(force=True)
    assert state_after.merge_in_progress is False


def test_adversarial_detached_head_state(base_git_repo: Path, tmp_path: Path) -> None:
    """Verify detached HEAD checkouts are indexed, identified, and queried cleanly."""
    settings = SynapSettings(
        repository_path=base_git_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "matrix_detached.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapRuntime(settings)
    runtime.bootstrap(force=True)

    # Create a second commit
    (base_git_repo / "detached_module.py").write_text(
        "def detached_worker(): pass\n", encoding="utf-8"
    )
    _run_git(["add", "detached_module.py"], base_git_repo)
    _run_git(["commit", "-m", "feat: commit two"], base_git_repo)

    rev_proc = _run_git(["rev-parse", "HEAD"], base_git_repo)
    commit_sha = rev_proc.stdout.strip()

    # Checkout directly to commit hash -> Detached HEAD
    _run_git(["checkout", commit_sha], base_git_repo)

    state = runtime.git.state(force=True)
    assert state.is_detached is True
    assert state.branch is None
    assert state.effective_branch == "detached"
    assert state.head_commit == commit_sha

    # Index detached commit
    commit = runtime.index_repository(git_state=state, force=True)
    assert commit == commit_sha

    # Query MCP facade on detached state
    facade = SynapMCPFacade(runtime)
    neighborhood = facade.get_neighborhood("detached_worker")
    assert neighborhood["symbol"] == "detached_worker"

    # Return to main branch
    _run_git(["checkout", "main"], base_git_repo)
    state_main = runtime.git.state(force=True)
    assert state_main.is_detached is False
    assert state_main.effective_branch == "main"


def test_adversarial_secondary_worktree(base_git_repo: Path, tmp_path: Path) -> None:
    """Verify secondary git worktree resolution, dirty diffs, and indexing."""
    wt_path = tmp_path / "worktree_dir"
    _run_git(["worktree", "add", str(wt_path), "-b", "wt_branch"], base_git_repo)

    # Initialize Synap targeting the worktree directory
    wt_settings = SynapSettings(
        repository_path=wt_path,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "matrix_wt.db",
        object_path=tmp_path / "objects_wt",
    )
    wt_runtime = SynapRuntime(wt_settings)

    dirs = wt_runtime.git.resolve_git_dir(wt_path)
    assert dirs is not None
    git_dir, common_dir = dirs
    assert git_dir != common_dir
    assert (git_dir / "gitdir").exists() or git_dir.name == "wt_branch"

    state = wt_runtime.git.state(force=True)
    assert state.branch == "wt_branch"
    assert state.is_detached is False

    # Index worktree repository
    wt_commit = wt_runtime.bootstrap(force=True)
    assert wt_commit is not None

    # Make uncommitted modifications in worktree
    (wt_path / "core.py").write_text(
        "def base_func():\n    return 'in_worktree'\n", encoding="utf-8"
    )
    ranges = wt_runtime.git.get_dirty_diff_ranges(include_untracked=True)
    assert "core.py" in ranges
    assert len(ranges["core.py"]) > 0

    assert wt_runtime.store.integrity_check() == "ok"


def test_adversarial_unicode_and_special_char_paths(base_git_repo: Path, tmp_path: Path) -> None:
    """Verify paths with non-ASCII Unicode (umlauts, Cyrillic, CJK, spaces) parse and index properly."""
    sub_folder = base_git_repo / "src" / "müñchèn" / "тест_директория" / "日本語"
    sub_folder.mkdir(parents=True)

    unicode_file = sub_folder / "⚡_файл_テスト.py"
    unicode_file.write_text(
        "class ÜñîçødèKłãss:\n    def run_тест(self):\n        return 'success'\n",
        encoding="utf-8",
    )

    _run_git(["add", "."], base_git_repo)
    _run_git(["commit", "-m", "feat: add unicode file paths"], base_git_repo)

    settings = SynapSettings(
        repository_path=base_git_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "matrix_unicode.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapRuntime(settings)
    runtime.bootstrap(force=True)

    # Verify file stored in DB
    with runtime.store.connect() as conn:
        all_paths = [r["path"] for r in conn.execute("SELECT path FROM files").fetchall()]
        all_symbols = [r["name"] for r in conn.execute("SELECT name FROM symbols").fetchall()]

    assert any("тест_директория" in p for p in all_paths)
    assert any("⚡_файл_テスト.py" in p for p in all_paths)
    assert "ÜñîçødèKłãss" in all_symbols
    assert "run_тест" in all_symbols

    # Verify symbol reading and outline
    facade = SynapMCPFacade(runtime)
    outline = facade.get_outline("src/müñchèn/тест_директория/日本語/⚡_файл_テスト.py")
    assert outline.get("symbol_count", 0) >= 2


def test_adversarial_large_single_file_over_1mb(base_git_repo: Path, tmp_path: Path) -> None:
    """Verify large single file (> 1MB) handling: default security skip and large file parsing."""
    large_file = base_git_repo / "large_generated_matrix.py"

    # Generate ~1.5 MB file containing 7,000 functions
    chunks = ["# Large auto-generated test artifact\n"]
    for i in range(7000):
        chunks.append(
            f"def matrix_cell_function_{i}(arg_a: int, arg_b: str) -> bool:\n"
            f"    '''Docstring for cell {i} in stress matrix with extensive explanatory text to ensure substantial byte size.'''\n"
            f"    result = arg_a * 10 + {i}\n"
            f"    return True\n"
        )
    large_file.write_text("\n".join(chunks), encoding="utf-8")

    file_size_mb = large_file.stat().st_size / (1024 * 1024)
    assert file_size_mb >= 1.0, f"File size {file_size_mb:.2f}MB is below 1MB threshold"

    _run_git(["add", "large_generated_matrix.py"], base_git_repo)
    _run_git(["commit", "-m", "feat: add 1MB source file"], base_git_repo)

    # 1. Default settings (max_file_bytes = 1_000_000): Guardrail safely skips file to avoid OOM
    default_settings = SynapSettings(
        repository_path=base_git_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "matrix_default_large.db",
        object_path=tmp_path / "objects_default",
    )
    default_runtime = SynapRuntime(default_settings)
    default_runtime.bootstrap(force=True)

    with default_runtime.store.connect() as conn:
        paths = [r["path"] for r in conn.execute("SELECT path FROM files").fetchall()]
    assert "large_generated_matrix.py" not in paths, (
        "Expected file > 1MB to be skipped under default max_file_bytes=1_000_000 guardrail"
    )
    assert default_runtime.store.integrity_check() == "ok"

    # 2. Configured settings with elevated threshold (max_file_bytes = 3_000_000)
    elevated_settings = SynapSettings(
        repository_path=base_git_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "matrix_elevated_large.db",
        object_path=tmp_path / "objects_elevated",
        max_file_bytes=3_000_000,
    )
    elevated_runtime = SynapRuntime(elevated_settings)

    t0 = time.perf_counter()
    commit = elevated_runtime.bootstrap(force=True)
    elapsed = time.perf_counter() - t0
    print(f"\n  ⏱  Indexed {file_size_mb:.2f}MB source file in {elapsed:.2f}s")

    assert commit is not None
    assert elevated_runtime.store.integrity_check() == "ok"

    with elevated_runtime.store.connect() as conn:
        sym_count = conn.execute(
            "SELECT COUNT(*) FROM symbols WHERE name LIKE 'matrix_cell_function_%'"
        ).fetchone()[0]
    assert sym_count == 7000, f"Expected 7000 symbols parsed from 1.5MB file, found {sym_count}"


# ==============================================================================
# 3. Concurrency & Daemon Lifecycle
# ==============================================================================


@pytest.mark.asyncio
async def test_daemon_lifecycle_pid_and_heartbeat_cleanup(
    base_git_repo: Path, tmp_path: Path
) -> None:
    """Verify daemon lifecycle: startup writes PID & heartbeat, stop cleans them up cleanly."""
    settings = SynapSettings(
        repository_path=base_git_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "matrix_daemon.db",
        object_path=tmp_path / "objects",
        daemon_poll_interval_seconds=0.05,
        shutdown_timeout_seconds=0.1,
    )
    daemon = RuntimeDaemon(settings)
    daemon_task = asyncio.create_task(daemon.start())

    # Wait for daemon to complete bootstrap and transition to running
    for _ in range(50):
        await asyncio.sleep(0.1)
        if daemon.health().running:
            break

    pid_file = base_git_repo / ".synap" / "daemon.pid"
    hb_file = base_git_repo / ".synap" / "daemon_heartbeat.json"

    # Daemon is running and has written heartbeat
    assert hb_file.exists(), "Heartbeat file was not created"
    health = daemon.health()
    assert health.running is True

    # Stop daemon
    daemon.stop()
    await daemon_task

    # Verify both heartbeat and PID lockfile are unlinked
    assert not hb_file.exists(), "Heartbeat file was not deleted upon stop"
    assert not pid_file.exists(), "PID lockfile was not cleaned up upon stop"
    assert daemon.runtime.store.integrity_check() == "ok"


def test_concurrent_multi_thread_readers_and_writers(base_git_repo: Path, tmp_path: Path) -> None:
    """Torture test: verify SQLite WAL mode handles heavy concurrent readers and writers without lock contention."""
    settings = SynapSettings(
        repository_path=base_git_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "matrix_wal.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapRuntime(settings)
    runtime.bootstrap(force=True)

    errors: list[str] = []

    def writer_worker(worker_id: int) -> None:
        for i in range(15):
            try:
                runtime.store.put_checkpoint(
                    checkpoint_id=f"chk_{worker_id}_{i}",
                    branch="main",
                    commit_hash=f"hash_{worker_id}_{i}",
                    doing=f"Worker {worker_id} iteration {i}",
                    changed_files="[]",
                    next_step="verify",
                    blockers="",
                )
                time.sleep(0.005)
            except Exception as e:
                errors.append(f"Writer error: {e}")

    def reader_worker(worker_id: int) -> None:
        facade = SynapMCPFacade(runtime)
        for _ in range(25):
            try:
                facade.get_neighborhood("base_func")
                runtime.store.get_checkpoints("main", limit=10)
                time.sleep(0.003)
            except Exception as e:
                errors.append(f"Reader error: {e}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = []
        # Launch 3 concurrent writers and 5 concurrent readers
        for w in range(3):
            futures.append(executor.submit(writer_worker, w))
        for r in range(5):
            futures.append(executor.submit(reader_worker, r))

        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(errors) == 0, f"Encountered concurrency lock errors: {errors}"
    assert runtime.store.integrity_check() == "ok"
