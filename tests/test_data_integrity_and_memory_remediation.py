from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from synap_git.cli.main import app
from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.git import GitChangeKind, GitRepository
from synap_git.indexer.engine import SynapRuntime
from synap_git.mcp.server import SynapMCPServer
from synap_git.storage.sqlite import SynapStore


def test_git_state_populates_message_and_parents(tmp_path: Path) -> None:
    """Verify that git state populates commit message and parent hashes."""
    git = pytest.importorskip("git")
    repo = git.Repo.init(tmp_path, initial_branch="main")
    actor = git.Actor("Synap Test", "synapse@example.invalid")

    f = tmp_path / "file1.txt"
    f.write_text("v1\n", encoding="utf-8")
    repo.index.add(["file1.txt"])
    c1 = repo.index.commit("Commit one description", author=actor, committer=actor)

    f.write_text("v2\n", encoding="utf-8")
    repo.index.add(["file1.txt"])
    c2 = repo.index.commit("Commit two description", author=actor, committer=actor)

    git_repo = GitRepository(tmp_path)
    state = git_repo.state(force=True)

    assert state.head_commit == c2.hexsha
    assert state.commit_message == "Commit two description"
    assert len(state.commit_parent_hashes) == 1
    assert state.commit_parent_hashes[0] == c1.hexsha


def test_git_classify_revert_message(tmp_path: Path) -> None:
    """Verify that GitRepository.classify detects Revert commits by commit message."""
    git = pytest.importorskip("git")
    repo = git.Repo.init(tmp_path, initial_branch="main")
    actor = git.Actor("Synap Test", "synapse@example.invalid")

    f = tmp_path / "code.py"
    f.write_text("initial\n", encoding="utf-8")
    repo.index.add(["code.py"])
    repo.index.commit("initial", author=actor, committer=actor)

    git_repo = GitRepository(tmp_path)
    s1 = git_repo.state(force=True)

    f.write_text("reverted content\n", encoding="utf-8")
    repo.index.add(["code.py"])
    repo.index.commit('Revert "Feature X broken"', author=actor, committer=actor)
    s2 = git_repo.state(force=True)

    change = GitRepository.classify(s1, s2)
    assert change.kind == GitChangeKind.REVERT


def test_enqueue_wiki_ignores_assets_and_lockfiles(tmp_path: Path) -> None:
    """Verify that enqueue_wiki skips assets, svg, lockfiles, and minified bundles."""
    store = SynapStore(tmp_path / "synap.db")
    store.initialize()

    store.enqueue_wiki("icon.svg")
    store.enqueue_wiki("package-lock.json")
    store.enqueue_wiki("bundle.min.js")
    store.enqueue_wiki("types.d.ts.typed")
    store.enqueue_wiki("src/valid_code.py")

    with store.connect() as conn:
        rows = conn.execute("SELECT file_path FROM wiki_queue").fetchall()
        enqueued = [r["file_path"] for r in rows]

    assert enqueued == ["src/valid_code.py"]


def test_mcp_restore_checkpoint_by_id(tmp_path: Path) -> None:
    """Verify that restore_checkpoint looks up the specific checkpoint by ID."""
    settings = SynapSettings(
        repository_path=tmp_path,
        state_path=tmp_path / ".synap",
        profile=RuntimeProfile.TEST,
    )
    runtime = SynapRuntime(settings)
    runtime.initialize_storage()

    # Create two checkpoints
    runtime.store.put_checkpoint("cp-1", "main", "c1", "Task one", "[]", "step1", "none")
    runtime.store.put_checkpoint("cp-2", "main", "c2", "Task two", "[]", "step2", "none")

    server = SynapMCPServer(runtime)
    res1 = server.facade.restore_checkpoint("cp-1")
    assert res1["checkpoint_id"] == "cp-1"
    assert res1["doing"] == "Task one"

    res2 = server.facade.restore_checkpoint("cp-2")
    assert res2["checkpoint_id"] == "cp-2"
    assert res2["doing"] == "Task two"


def test_repair_preserves_l3_memory(tmp_path: Path) -> None:
    """Verify that synap repair preserves lessons, checkpoints, and decisions."""
    git = pytest.importorskip("git")
    repo = git.Repo.init(tmp_path, initial_branch="main")
    actor = git.Actor("Synap Test", "synapse@example.invalid")

    (tmp_path / "main.py").write_text("def test(): pass\n", encoding="utf-8")
    repo.index.add(["main.py"])
    repo.index.commit("initial", author=actor, committer=actor)

    settings = SynapSettings(
        repository_path=tmp_path,
        state_path=tmp_path / ".synap",
        profile=RuntimeProfile.TEST,
    )
    runtime = SynapRuntime(settings)
    runtime.initialize_storage()

    # Seed L3 memory
    runtime.store.put_checkpoint(
        "cp-preserved", "main", "c1", "Preserved Task", "[]", "next", "none"
    )
    with runtime.store.connect() as conn:
        conn.execute(
            """
            INSERT INTO lessons (lesson_id, branch, revert_commit, reverted_from, what_failed, why_failed, files_affected, status, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'approved', ?, ?)
            """,
            ("les-1", "main", "rev1", "from1", "what", "why", "[]", 100, 200),
        )

    # Run repair via CLI
    runner = CliRunner()
    result = runner.invoke(app, ["repair", tmp_path.as_posix(), "--yes"])
    assert result.exit_code == 0

    # Verify L3 survived
    with runtime.store.connect() as conn:
        cp = conn.execute(
            "SELECT * FROM checkpoints WHERE checkpoint_id = 'cp-preserved'"
        ).fetchone()
        assert cp is not None, "Checkpoint should be preserved during repair"
        assert cp["doing"] == "Preserved Task"

        les = conn.execute("SELECT * FROM lessons WHERE lesson_id = 'les-1'").fetchone()
        assert les is not None, "Lesson should be preserved during repair"
        assert les["status"] == "approved"


def test_store_memory_deduplication(tmp_path: Path) -> None:
    """Verify that repeated store_memory calls with the same key update rather than duplicate."""
    store = SynapStore(tmp_path / "synap.db")
    store.initialize()

    # Store fact repeatedly with same key
    store.store_memory("mem-1", "cache_strategy", "lru", "LRU cache")
    store.store_memory("mem-2", "cache_strategy", "fifo", "FIFO cache")
    store.store_memory("mem-3", "cache_strategy", "arc", "Adaptive Replacement Cache")

    # Store another distinct fact
    store.store_memory("mem-4", "db_port", "5432", "Postgres port")

    # Check that cache_strategy only has 1 record (the latest)
    memories = store.get_recent_memory("cache_strategy")
    assert len(memories) == 1
    assert memories[0]["id"] == "mem-3"
    assert memories[0]["payload"] == "arc"

    # Check total memory count is 2 (not 4)
    all_mem = store.get_recent_memory()
    assert len(all_mem) == 2

    with store.connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM agent_memory WHERE context_key = 'cache_strategy'"
        ).fetchone()[0]
        assert count == 1
        indexes = [
            r[1]
            for r in conn.execute(
                "SELECT type, name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        ]
        assert "idx_agent_memory_key_unique" in indexes


def test_atomic_wiki_dequeue_concurrency(tmp_path: Path) -> None:
    """Verify that concurrent workers using BEGIN IMMEDIATE + UPDATE RETURNING * never duplicate tasks."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    store = SynapStore(tmp_path / "synap.db")
    store.initialize()

    # Enqueue 40 tasks
    num_tasks = 40
    for i in range(num_tasks):
        store.enqueue_wiki(f"src/file_{i}.py")

    claimed_task_ids: list[str] = []

    def worker_loop() -> list[str]:
        worker_claimed: list[str] = []
        w_store = SynapStore(tmp_path / "synap.db")
        while True:
            task = w_store.dequeue_wiki()
            if not task:
                break
            worker_claimed.append(task["task_id"])
            time.sleep(0.001)  # tiny yield to maximize thread contention
        return worker_claimed

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker_loop) for _ in range(8)]
        for f in futures:
            claimed_task_ids.extend(f.result())

    # Every task was claimed exactly once
    assert len(claimed_task_ids) == num_tasks
    assert len(set(claimed_task_ids)) == num_tasks, (
        "Duplicate task claims detected under concurrency!"
    )


def test_linear_migration_ladder_v1_to_v6_covering_indexes(tmp_path: Path) -> None:
    """Verify linear user_version migration ladder from v1 through v6 with covering indexes."""
    required_indexes = [
        "idx_edges_src_tgt",
        "idx_edges_tgt_src",
        "idx_symbols_start_end",
        "idx_checkpoints_branch_created",
        "idx_agent_memory_key_unique",
    ]

    for start_ver in [1, 2, 3, 4, 5]:
        db_file = tmp_path / f"test_mig_v{start_ver}.db"
        store = SynapStore(db_file)
        # Initialize initial structure
        store.initialize()

        # Artificially roll back version to test ladder
        with store.connect() as conn:
            conn.execute(f"PRAGMA user_version = {start_ver}")

        # Re-initialize should migrate to TARGET_VERSION = 6
        store.initialize()

        with store.connect() as conn:
            final_version = conn.execute("PRAGMA user_version").fetchone()[0]
            assert final_version == 6, f"Expected version 6 after migration from {start_ver}"

            index_rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
            installed_indexes = {r[0] for r in index_rows}
            for idx in required_indexes:
                assert idx in installed_indexes, (
                    f"Missing covering index {idx} migrating from v{start_ver}"
                )
