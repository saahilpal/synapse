from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.git.state import GitState
from synap_git.indexer.engine import SynapRuntime, _has_conflict_markers, _parse_worker


def test_has_conflict_markers_detection() -> None:
    """Verify detection of git conflict markers in content strings."""
    clean_code = "def foo():\n    return 42\n"
    assert not _has_conflict_markers(clean_code)

    conflict_code = (
        "def foo():\n<<<<<<< HEAD\n    return 1\n=======\n    return 2\n>>>>>>> feature_branch\n"
    )
    assert _has_conflict_markers(conflict_code)

    # Partial markers or less than 7 chars should not trigger
    almost = "<<<<<< not enough markers\n"
    assert not _has_conflict_markers(almost)


def test_parse_worker_guards_conflict_markers(tmp_path: Path) -> None:
    """Verify _parse_worker returns empty symbols and syntax_error for conflicted files."""
    conflicted_file = tmp_path / "conflict.py"
    conflicted_file.write_text(
        "def hello():\n<<<<<<< HEAD\n    print('a')\n=======\n    print('b')\n>>>>>>> branch\n",
        encoding="utf-8",
    )

    result = _parse_worker((conflicted_file, "conflict.py"))
    assert result["path"] == "conflict.py"
    assert result["language"] == "unknown"
    assert result["symbols"] == []
    assert result["imports"] == []
    assert result["syntax_error"] == "conflict_markers_detected"


def test_handle_revert_deduplication(tmp_path: Path, monkeypatch: Any) -> None:
    """Verify handle_revert creates structured lessons and skips duplicate inserts for identical revert commits."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True)

    test_file = repo / "module.py"
    test_file.write_text("def fn(): pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "module.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True)

    settings = SynapSettings(
        repository_path=repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synap.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapRuntime(settings)
    runtime.initialize_storage()

    prev_state = GitState(repository_path=repo, is_repository=True, head_commit="c1111111")
    curr_state = GitState(
        repository_path=repo,
        is_repository=True,
        head_commit="c2222222",
        commit_message="Revert 'broken commit'",
    )

    def mock_check_output(*args: Any, **kwargs: Any) -> str:
        return "module.py\n"

    monkeypatch.setattr(subprocess, "check_output", mock_check_output)

    # First call: creates the structured lesson
    runtime.handle_revert(prev_state, curr_state)

    with runtime.store.connect() as conn:
        lessons = conn.execute("SELECT * FROM lessons WHERE revert_commit = 'c2222222'").fetchall()
        assert len(lessons) == 1
        assert lessons[0]["what_failed"] == "Revert 'broken commit'"
        assert lessons[0]["status"] == "pending"

    # Second call with the same commit: must be deduplicated
    runtime.handle_revert(prev_state, curr_state)

    with runtime.store.connect() as conn:
        lessons_after = conn.execute(
            "SELECT * FROM lessons WHERE revert_commit = 'c2222222'"
        ).fetchall()
        assert len(lessons_after) == 1, "Duplicate lesson should not be inserted"


def test_is_in_progress_operation_detects_merge_rebase(tmp_path: Path) -> None:
    """Verify _is_in_progress_operation guards against active merge/rebase and conflict states."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True)

    (repo / "f.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True)

    settings = SynapSettings(
        repository_path=repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synap.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapRuntime(settings)

    state = runtime.git.state(force=True)
    # Normal state should not be in progress
    assert not runtime._is_in_progress_operation(state)

    git_dir = repo / ".git"

    # Simulate MERGE_HEAD
    (git_dir / "MERGE_HEAD").write_text("abcdef\n", encoding="utf-8")
    assert runtime._is_in_progress_operation(state)
    (git_dir / "MERGE_HEAD").unlink()

    # Simulate rebase-merge
    rebase_dir = git_dir / "rebase-merge"
    rebase_dir.mkdir()
    assert runtime._is_in_progress_operation(state)
    rebase_dir.rmdir()

    # Simulate AUTO_MERGE
    (git_dir / "AUTO_MERGE").write_text("abcdef\n", encoding="utf-8")
    assert runtime._is_in_progress_operation(state)
    (git_dir / "AUTO_MERGE").unlink()
