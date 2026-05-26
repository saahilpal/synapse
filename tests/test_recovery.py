from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from synapse.config import RuntimeProfile, SynapseSettings
from synapse.indexer.engine import SynapseRuntime


@pytest.fixture
def settings(tmp_path: Path) -> SynapseSettings:
    repo = tmp_path / "repo"
    repo.mkdir()

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
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


def test_database_recovery_on_corruption(settings: SynapseSettings) -> None:
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    # Verify we indexed some files
    status = runtime.status()
    assert status.files > 0

    # Intentionally corrupt the database file
    db_path = settings.sqlite_path
    assert db_path is not None
    db_path.write_text("THIS IS NOT A SQLITE FILE - TOTAL CORRUPTION")

    # Run recover check (this simulates synapse recover/daemon recovery)
    is_wiped = runtime.store.recover_if_corrupted()
    assert is_wiped is True
    assert not db_path.exists()

    # Re-bootstrap and verify it is healthy
    runtime.bootstrap(force=True)
    status2 = runtime.status()
    assert status2.files > 0
    assert runtime.store.integrity_check() == "ok"
