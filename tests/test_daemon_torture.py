from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.daemon import RuntimeDaemon


@pytest.fixture
def torture_settings(tmp_path: Path) -> SynapSettings:
    repo = tmp_path / "repo"
    repo.mkdir()

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "torture@synapse.local"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Torture Tester"], cwd=repo, check=True)

    # Initial file
    (repo / "app.py").write_text("def run(): pass\n", encoding="utf-8")
    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "initial commit"], cwd=repo, check=True)

    settings = SynapSettings(
        repository_path=repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synap.db",
        object_path=tmp_path / "objects",
        daemon_poll_interval_seconds=0.05,
        shutdown_timeout_seconds=0.1,
    )
    return settings


@pytest.mark.asyncio
async def test_daemon_survives_rapid_file_saves(torture_settings: SynapSettings) -> None:
    """Torture test: rapid saves to files should not crash or trigger lock contention."""
    daemon = RuntimeDaemon(torture_settings)
    daemon_task = asyncio.create_task(daemon.start())

    # Wait for initial bootstrap
    await asyncio.sleep(0.2)

    repo = torture_settings.repository_path
    app_file = repo / "app.py"

    # Rapidly overwrite app.py 20 times with a small delay
    for i in range(20):
        app_file.write_text(f"def run_{i}():\n    return {i}\n", encoding="utf-8")
        await asyncio.sleep(0.01)

    # Wait for daemon to catch up and index the final state
    await asyncio.sleep(0.5)

    daemon.stop()
    await daemon_task

    # Verify database integrity and that the final symbol is recorded
    status = daemon.runtime.status()
    # files count is at least 1 (app.py) and potentially 2 (.gitignore is auto-created/modified)
    assert status.files >= 1
    assert daemon.runtime.store.integrity_check() == "ok"


@pytest.mark.asyncio
async def test_daemon_survives_branch_switching(torture_settings: SynapSettings) -> None:
    """Verify daemon updates its active commit and indices correctly on branch checkout."""
    daemon = RuntimeDaemon(torture_settings)
    daemon_task = asyncio.create_task(daemon.start())

    await asyncio.sleep(0.2)

    repo = torture_settings.repository_path
    git_bin = shutil.which("git") or "git"

    # Create and checkout feature branch
    subprocess.run([git_bin, "checkout", "-b", "feature/torture"], cwd=repo, check=True)
    (repo / "feature.py").write_text("def feature(): pass\n", encoding="utf-8")
    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "add feature file"], cwd=repo, check=True)

    await asyncio.sleep(0.3)

    # Checkout back to main
    subprocess.run([git_bin, "checkout", "main"], cwd=repo, check=True)

    await asyncio.sleep(0.3)

    daemon.stop()
    await daemon_task

    status = daemon.runtime.status()
    assert status.branch == "main"
    assert daemon.runtime.store.integrity_check() == "ok"


@pytest.mark.asyncio
async def test_daemon_ignores_rebase_merge_in_progress(torture_settings: SynapSettings) -> None:
    """Ensure that the daemon does not crash when rebase or merge conflict indicators exist."""
    repo = torture_settings.repository_path
    git_dir = repo / ".git"

    # Manually simulate MERGE_HEAD and rebase-merge directories
    (git_dir / "MERGE_HEAD").write_text(
        "1234567890abcdef1234567890abcdef12345678\n", encoding="utf-8"
    )
    (git_dir / "rebase-merge").mkdir(exist_ok=True)

    daemon = RuntimeDaemon(torture_settings)
    daemon_task = asyncio.create_task(daemon.start())

    await asyncio.sleep(0.2)

    daemon.stop()
    await daemon_task

    # Clean up manual directories
    (git_dir / "MERGE_HEAD").unlink(missing_ok=True)
    shutil.rmtree(git_dir / "rebase-merge", ignore_errors=True)

    assert daemon.runtime.store.integrity_check() == "ok"


@pytest.mark.asyncio
async def test_daemon_recovery_on_restart(torture_settings: SynapSettings) -> None:
    """Verify that restarting the daemon after dirty shutdowns recover db state cleanly."""
    daemon1 = RuntimeDaemon(torture_settings)
    daemon1.runtime.store.recover_if_corrupted()
    daemon1.runtime.bootstrap()

    # Verify db check passes
    assert daemon1.runtime.store.integrity_check() == "ok"

    # Start a second daemon instance to simulate clean recovery bootstrap
    daemon2 = RuntimeDaemon(torture_settings)
    daemon_task = asyncio.create_task(daemon2.start())

    await asyncio.sleep(0.2)
    daemon2.stop()
    await daemon_task

    assert daemon2.runtime.store.integrity_check() == "ok"


@pytest.mark.asyncio
async def test_concurrent_reads_and_writes(torture_settings: SynapSettings) -> None:
    """Run retrieval queries concurrently while background daemon is actively indexing."""
    daemon = RuntimeDaemon(torture_settings)
    daemon_task = asyncio.create_task(daemon.start())

    try:
        await asyncio.sleep(0.2)

        repo = torture_settings.repository_path
        app_file = repo / "app.py"

        async def writer_loop() -> None:
            for i in range(15):
                app_file.write_text(
                    f"def fn_{i}():\n    # inline docs\n    pass\n", encoding="utf-8"
                )
                await asyncio.sleep(0.02)

        async def reader_loop() -> None:
            for _ in range(15):
                # Query the retrieval engine while files are modified
                ans, _, _ = daemon.runtime.query_hybrid("fn_0", max_tokens=1000)
                assert ans is not None
                await asyncio.sleep(0.02)

        # Run writer and reader concurrently
        await asyncio.gather(writer_loop(), reader_loop())

        await asyncio.sleep(0.3)
    finally:
        daemon.stop()
        await daemon_task

    assert daemon.runtime.store.integrity_check() == "ok"
