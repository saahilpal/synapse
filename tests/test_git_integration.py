from __future__ import annotations

from pathlib import Path

import pytest

from synapse.git import GitChangeKind, GitRepository


def test_git_repository_detects_commit(tmp_path: Path) -> None:
    git = pytest.importorskip("git")
    repo = git.Repo.init(tmp_path, initial_branch="main")
    actor = git.Actor("Synapse Test", "synapse@example.invalid")
    (tmp_path / "README.md").write_text("# Test\n", encoding="utf-8")
    repo.index.add(["README.md"])
    repo.index.commit("initial", author=actor, committer=actor)

    reader = GitRepository(tmp_path)
    first = reader.state()
    (tmp_path / "README.md").write_text("# Test\n\nMore\n", encoding="utf-8")
    repo.index.add(["README.md"])
    repo.index.commit("second", author=actor, committer=actor)
    second = reader.state()

    assert first.branch == "main"
    assert reader.classify(first, second).kind is GitChangeKind.COMMIT
