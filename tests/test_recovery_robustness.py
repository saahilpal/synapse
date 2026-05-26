from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from synapse.config import RuntimeProfile, SynapseSettings
from synapse.indexer.engine import SynapseRuntime


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        [git_bin, "config", "user.email", "recovery@synapse.local"], cwd=repo, check=True
    )
    subprocess.run([git_bin, "config", "user.name", "Recovery Tester"], cwd=repo, check=True)

    # Base python files
    (repo / "main.py").write_text("def hello(): pass\n", encoding="utf-8")
    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "initial commit"], cwd=repo, check=True)

    return repo


def test_wal_corruption_recovery(temp_repo: Path, tmp_path: Path) -> None:
    """Intentionally corrupt sqlite db-wal or db-shm files and verify recover_if_corrupted wipes and heals."""
    settings = SynapseSettings(
        repository_path=temp_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synapse.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    # Verify db exists and is healthy
    assert settings.sqlite_path is not None
    assert settings.sqlite_path.exists()
    assert runtime.store.integrity_check() == "ok"

    # Write corrupt data directly to WAL file if it exists, otherwise just corrupt the DB file
    wal_path = Path(f"{settings.sqlite_path}-wal")
    with runtime.store.connect() as conn:
        conn.execute("CREATE TABLE foo (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO foo VALUES (1)")

    # Corrupt DB file
    settings.sqlite_path.write_text("NOT A DATABASE", encoding="utf-8")
    if wal_path.exists():
        wal_path.write_text("CORRUPT WAL", encoding="utf-8")

    # Call recover_if_corrupted
    wiped = runtime.store.recover_if_corrupted()
    assert wiped is True

    # Re-bootstrap and check it is healthy
    runtime.bootstrap(force=True)
    assert runtime.store.integrity_check() == "ok"


def test_malformed_trace_handling(temp_repo: Path, tmp_path: Path) -> None:
    """Verify that a corrupted or malformed trace JSON file does not crash the system when read."""
    settings = SynapseSettings(
        repository_path=temp_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synapse.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    trace_file = temp_repo / ".synapse" / "trace_latest.json"
    trace_file.parent.mkdir(parents=True, exist_ok=True)

    # 1. Non-JSON data
    trace_file.write_text("Not valid JSON content string {[[", encoding="utf-8")
    latest = runtime.trace_store.get_latest()
    assert "error" in latest or latest.get("trace_id") == "error"

    # 2. JSON list instead of dict
    trace_file.write_text("[]", encoding="utf-8")
    latest2 = runtime.trace_store.get_latest()
    assert "error" in latest2 or "Invalid trace structure" in latest2.get("error", "")

    # 3. None/Null values
    trace_file.write_text("null", encoding="utf-8")
    latest3 = runtime.trace_store.get_latest()
    assert "error" in latest3 or "Invalid trace structure" in latest3.get("error", "")


def test_malformed_gitignore_handling(temp_repo: Path, tmp_path: Path) -> None:
    """Verify that a malformed or unparseable .gitignore file does not crash RepositoryScanner."""
    # Write invalid regex/glob patterns to .gitignore
    (temp_repo / ".gitignore").write_text("[[[invalid-glob-pattern***\n", encoding="utf-8")

    settings = SynapseSettings(
        repository_path=temp_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synapse.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapseRuntime(settings)

    # Re-bootstrap. It should not raise PatternError or any re.error
    runtime.bootstrap(force=True)
    status = runtime.status()
    assert status.files >= 1
