from __future__ import annotations

from pathlib import Path

import pytest

from synapse.config import RuntimeProfile, SynapseSettings
from synapse.indexer.engine import SynapseRuntime


@pytest.fixture
def settings(tmp_path: Path) -> SynapseSettings:
    repo = tmp_path / "repo"
    repo.mkdir()
    import shutil
    import subprocess

    git_bin = shutil.which("git") or "git"

    subprocess.run([git_bin, "init"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "you@example.com"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Your Name"], cwd=repo, check=True)

    (repo / "main.py").write_text("def hello(): pass")
    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "initial"], cwd=repo, check=True)
    return SynapseSettings(
        repository_path=repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synapse.db",
        object_path=tmp_path / "objects",
    )


def test_deterministic_rebuild(settings: SynapseSettings) -> None:
    runtime = SynapseRuntime(settings)

    # First build
    commit1 = runtime.bootstrap()
    assert commit1 is not None

    with runtime.store.connect() as conn:
        count1 = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        assert count1 > 0

    # Wipe and rebuild
    if settings.sqlite_path:
        settings.sqlite_path.unlink()
    runtime.store.initialize()

    commit2 = runtime.bootstrap()
    assert commit2 == commit1

    with runtime.store.connect() as conn:
        count2 = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        assert count2 == count1


def test_incremental_indexing(settings: SynapseSettings) -> None:
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    repo = settings.repository_path
    (repo / "new.py").write_text("class New: pass")

    import shutil
    import subprocess

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "new file"], cwd=repo, check=True)

    new_commit = runtime.index_repository()
    assert new_commit is not None

    with runtime.store.connect() as conn:
        symbols = [row["name"] for row in conn.execute("SELECT name FROM symbols").fetchall()]
        assert "New" in symbols
        assert "hello" in symbols
