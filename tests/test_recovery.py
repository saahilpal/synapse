from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime


@pytest.fixture
def settings(tmp_path: Path) -> SynapSettings:
    repo = tmp_path / "repo"
    repo.mkdir()

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "you@example.com"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Your Name"], cwd=repo, check=True)

    (repo / "main.py").write_text("def hello(): pass")
    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "initial"], cwd=repo, check=True)

    return SynapSettings(
        repository_path=repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synap.db",
        object_path=tmp_path / "objects",
    )


def test_database_recovery_on_corruption(settings: SynapSettings) -> None:
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    # Verify we indexed some files
    status = runtime.status()
    assert status.files > 0

    # Intentionally corrupt the database file
    db_path = settings.sqlite_path
    assert db_path is not None
    db_path.write_text("THIS IS NOT A SQLITE FILE - TOTAL CORRUPTION")

    # Run recover check (this simulates synap recover/daemon recovery)
    is_wiped = runtime.store.recover_if_corrupted()
    assert is_wiped is True
    assert not db_path.exists()

    # Re-bootstrap and verify it is healthy
    runtime.bootstrap(force=True)
    status2 = runtime.status()
    assert status2.files > 0
    assert runtime.store.integrity_check() == "ok"


def test_recover_if_corrupted_never_wipes_on_locked_database(settings: SynapSettings) -> None:
    """Ensure recover_if_corrupted never deletes DB on transient locks or busy states."""
    import sqlite3

    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    db_path = settings.sqlite_path
    assert db_path is not None
    assert db_path.exists()

    # Acquire an exclusive lock with another connection
    lock_conn = sqlite3.connect(db_path)
    lock_conn.execute("PRAGMA locking_mode = EXCLUSIVE")
    lock_conn.execute("BEGIN EXCLUSIVE")

    try:
        # Attempt recovery while database is locked
        is_wiped = runtime.store.recover_if_corrupted()
        assert is_wiped is False
        assert db_path.exists(), "Database must NEVER be deleted when locked!"
    finally:
        lock_conn.rollback()
        lock_conn.close()

    # Database must still be completely healthy
    assert runtime.store.integrity_check() == "ok"


def test_recover_if_corrupted_never_wipes_on_transient_error(
    settings: SynapSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure recover_if_corrupted never deletes DB on simulated OperationalError or TimeoutError."""
    import sqlite3

    runtime = SynapRuntime(settings)
    runtime.bootstrap()
    db_path = settings.sqlite_path
    assert db_path is not None

    def mock_connect_locked(*args: object, **kwargs: object) -> sqlite3.Connection:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(sqlite3, "connect", mock_connect_locked)
    is_wiped = runtime.store.recover_if_corrupted()
    assert is_wiped is False
    assert db_path.exists()

    def mock_connect_busy(*args: object, **kwargs: object) -> sqlite3.Connection:
        raise sqlite3.OperationalError("database table is locked: symbols")

    monkeypatch.setattr(sqlite3, "connect", mock_connect_busy)
    is_wiped = runtime.store.recover_if_corrupted()
    assert is_wiped is False
    assert db_path.exists()

    def mock_connect_timeout(*args: object, **kwargs: object) -> sqlite3.Connection:
        raise TimeoutError("connection timed out")

    monkeypatch.setattr(sqlite3, "connect", mock_connect_timeout)
    is_wiped = runtime.store.recover_if_corrupted()
    assert is_wiped is False
    assert db_path.exists()
