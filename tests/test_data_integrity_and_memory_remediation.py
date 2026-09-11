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
