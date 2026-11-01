from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.git import GitChangeKind, GitRepository
from synap_git.indexer.engine import SynapRuntime


def _git(cmd: list[str], cwd: Path) -> str:
    res = subprocess.run(["git", *cmd], cwd=cwd, capture_output=True, text=True, check=True)
    return res.stdout.strip()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    _git(["init", "-b", "main"], tmp_path)
    _git(["config", "user.name", "Test Agent"], tmp_path)
    _git(["config", "user.email", "agent@synapse.invalid"], tmp_path)
    (tmp_path / "app.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    _git(["add", "app.py"], tmp_path)
    _git(["commit", "-m", "feat: initial commit"], tmp_path)
    return tmp_path


def test_worktree_detection_and_fingerprint(git_repo: Path, tmp_path: Path) -> None:
    """Verify that GitRepository resolves worktrees and correctly handles fingerprints and status."""
    wt_path = tmp_path / "worktree_feature"
    _git(["worktree", "add", str(wt_path), "-b", "feature-worktree"], git_repo)

    reader = GitRepository(wt_path)
    state = reader.state()

    assert state.is_repository is True
    assert state.branch == "feature-worktree"
    assert state.is_detached is False
    assert state.is_dirty is False

    # Make uncommitted changes in worktree
    (wt_path / "app.py").write_text("def hello():\n    return 'worktree'\n", encoding="utf-8")
    state_dirty = reader.state(force=True)
    assert state_dirty.is_dirty is True
    assert "app.py" in state_dirty.dirty_files


def test_worktree_merge_and_rebase_detection(git_repo: Path, tmp_path: Path) -> None:
    """Verify that worktree in-progress merge/rebase flags are detected from the worktree gitdir."""
    wt_path = tmp_path / "worktree_wt"
    _git(["worktree", "add", str(wt_path), "-b", "wt-merge-branch"], git_repo)

    dirs = GitRepository.resolve_git_dir(wt_path)
    assert dirs is not None
    git_dir, common_dir = dirs
    assert git_dir != common_dir
    assert git_dir.is_dir()

    # Simulate merge in progress in worktree
    merge_head = git_dir / "MERGE_HEAD"
    merge_head.write_text("0" * 40 + "\n", encoding="utf-8")

    reader = GitRepository(wt_path)
    state = reader.state(force=True)
    assert state.merge_in_progress is True


def test_detached_head_detection_and_classification(git_repo: Path) -> None:
    """Verify effective_branch, is_detached, and classify() during detached HEAD checkouts."""
    reader = GitRepository(git_repo)
    s_main = reader.state(force=True)
    assert s_main.branch == "main"
    assert s_main.is_detached is False
    assert s_main.effective_branch == "main"

    # Checkout detached commit
    commit_1 = s_main.head_commit
    assert commit_1 is not None
    (git_repo / "feature.py").write_text("X = 1\n", encoding="utf-8")
    _git(["add", "feature.py"], git_repo)
    _git(["commit", "-m", "feat: commit 2"], git_repo)

    _git(["checkout", commit_1], git_repo)
    s_detached = reader.state(force=True)
    assert s_detached.is_detached is True
    assert s_detached.branch is None
    assert s_detached.effective_branch == "detached"
    assert s_detached.head_commit == commit_1

    # Classifying branch -> detached commit must be CHECKOUT, not BRANCH
    change = reader.classify(s_main, s_detached)
    assert change.kind == GitChangeKind.CHECKOUT

    # Transitioning between detached commits must be CHECKOUT, not COMMIT
    _git(["checkout", "HEAD~0"], git_repo)
    s_detached_same = reader.state(force=True)
    change_same = reader.classify(s_detached, s_detached_same)
    assert change_same.kind == GitChangeKind.UNCHANGED


def test_get_dirty_diff_ranges_untracked_and_staged(git_repo: Path) -> None:
    """Verify get_dirty_diff_ranges captures untracked, staged, and unstaged modifications."""
    reader = GitRepository(git_repo)

    # 1. Untracked file
    (git_repo / "untracked.py").write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    diffs = reader.get_dirty_diff_ranges(include_untracked=True)
    assert "untracked.py" in diffs
    assert diffs["untracked.py"] == [(1, 3)]

    # 2. Staged modified file
    (git_repo / "app.py").write_text("def hello():\n    return 'changed'\n", encoding="utf-8")
    _git(["add", "app.py"], git_repo)
    diffs_staged = reader.get_dirty_diff_ranges(include_untracked=True)
    assert "app.py" in diffs_staged
    assert len(diffs_staged["app.py"]) > 0


def test_get_symbol_lineage_accurate_tracking(git_repo: Path) -> None:
    """Verify get_symbol_lineage tracks commit author, message, and timestamp for symbols."""
    reader = GitRepository(git_repo)

    lineage = reader.get_symbol_lineage(
        file_path="app.py",
        symbol_name="hello",
        line_range=(1, 2),
    )
    assert len(lineage) >= 1
    assert lineage[0].author_name == "Test Agent"
    assert "initial commit" in lineage[0].message.lower()


def test_cross_branch_stale_index_detection_and_ghost_cleanup(git_repo: Path) -> None:
    """Verify that switching branches updates index without stale ghost files from other branch."""
    settings = SynapSettings(repository_path=git_repo, profile=RuntimeProfile.TEST)
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    # On main: only app.py exists
    with runtime.store.connect() as conn:
        paths = [
            r["path"]
            for r in conn.execute("SELECT path FROM files").fetchall()
            if not r["path"].startswith(".")
        ]
    assert paths == ["app.py"]

    # Create and switch to feature branch with new file
    _git(["checkout", "-b", "feature-ghost"], git_repo)
    (git_repo / "ghost.py").write_text("class Ghost:\n    pass\n", encoding="utf-8")
    _git(["add", "ghost.py"], git_repo)
    _git(["commit", "-m", "feat: add ghost.py"], git_repo)

    runtime.handle_branch_switch(runtime.git.state(force=True))
    with runtime.store.connect() as conn:
        paths_feat = sorted(
            r["path"]
            for r in conn.execute("SELECT path FROM files").fetchall()
            if not r["path"].startswith(".")
        )
    assert paths_feat == ["app.py", "ghost.py"]

    # Switch back to main: ghost.py MUST NOT be present in SQLite index!
    _git(["checkout", "main"], git_repo)
    runtime.handle_branch_switch(runtime.git.state(force=True))

    with runtime.store.connect() as conn:
        paths_main = [
            r["path"]
            for r in conn.execute("SELECT path FROM files").fetchall()
            if not r["path"].startswith(".")
        ]
    assert paths_main == ["app.py"], "Stale ghost.py was not pruned on branch switch!"
