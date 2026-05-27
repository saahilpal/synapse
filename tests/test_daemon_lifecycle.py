from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from synap_git.cli.main import _is_process_running, app


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "you@example.com"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Your Name"], cwd=repo, check=True)

    (repo / "main.py").write_text("def hello(): pass")
    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "initial"], cwd=repo, check=True)

    return repo


def test_daemon_lifecycle_cli(
    temp_repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Setup configuration environment to avoid polluting user's local configs
    config_dir = tmp_path / ".config" / "synap"
    monkeypatch.setenv("SYNAP_CONFIG", (config_dir / "config.toml").as_posix())

    runner = CliRunner()

    # Step 1: Run setup first (we use non-interactive fallback inputs)
    setup_inputs = "ollama\nqwen2.5-coder:14b\nhttp://localhost:11434\ny\n"
    setup_res = runner.invoke(app, ["setup", temp_repo.as_posix()], input=setup_inputs)
    assert setup_res.exit_code == 0

    # Step 2: Start background daemon
    start_res = runner.invoke(app, ["start", temp_repo.as_posix()])
    assert start_res.exit_code == 0, start_res.output
    assert "Synap daemon started" in start_res.output
    assert "UI available at" in start_res.output

    # Verify daemon PID and heartbeat files exist
    pid_file = temp_repo / ".synap" / "daemon.pid"
    hb_file = temp_repo / ".synap" / "daemon_heartbeat.json"
    assert pid_file.exists()
    assert hb_file.exists()

    pid = int(pid_file.read_text().strip())
    assert _is_process_running(pid)

    # Step 3: Check status
    status_res = runner.invoke(app, ["status", temp_repo.as_posix()])
    assert status_res.exit_code == 0, status_res.output
    assert "Daemon:" in status_res.output
    assert "Running" in status_res.output
    assert "Repository:" in status_res.output
    assert "CPU:" in status_res.output
    assert "RAM:" in status_res.output

    # Step 4: Restart daemon
    restart_res = runner.invoke(app, ["restart", temp_repo.as_posix()])
    assert restart_res.exit_code == 0, restart_res.output
    assert "Restarting Synap services" in restart_res.output
    assert "Synap daemon started" in restart_res.output

    new_pid = int(pid_file.read_text().strip())
    assert _is_process_running(new_pid)

    # Allow the restarted daemon to finish bootstrapping before stopping
    time.sleep(2)

    # Step 5: Stop daemon
    stop_res = runner.invoke(app, ["stop", temp_repo.as_posix()])
    assert stop_res.exit_code == 0, stop_res.output
    assert "Synap daemon stopped successfully" in stop_res.output

    assert not pid_file.exists()
    assert not hb_file.exists()
    assert not _is_process_running(new_pid)
