from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from synapse.cli.main import app


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "you@example.com"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Your Name"], cwd=repo, check=True)

    (repo / "main.py").write_text("def hello(): pass")
    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "initial"], cwd=repo, check=True)

    return repo


def test_checkpoint_cli_lifecycle(temp_repo: Path) -> None:
    runner = CliRunner()

    # 1. Initialize synapse
    init_res = runner.invoke(app, ["init", temp_repo.as_posix(), "--skip-llm", "--quiet"])
    assert init_res.exit_code == 0, init_res.output

    # 2. List checkpoints (should be empty initially)
    list_res = runner.invoke(app, ["checkpoint", "list", temp_repo.as_posix()])
    assert list_res.exit_code == 0
    assert "No checkpoints found" in list_res.output

    # 3. Create a checkpoint
    create_res = runner.invoke(
        app,
        [
            "checkpoint",
            "create",
            "--doing",
            "Refactoring main logic",
            "--files",
            "main.py,helper.py",
            "--next-step",
            "Test everything",
            "--blockers",
            "None",
            temp_repo.as_posix(),
        ],
    )
    assert create_res.exit_code == 0
    assert "Checkpoint" in create_res.output
    assert "created" in create_res.output

    # 4. List checkpoints (should show our checkpoint now)
    list_res2 = runner.invoke(app, ["checkpoint", "list", temp_repo.as_posix()])
    assert list_res2.exit_code == 0
    assert "Refactoring" in list_res2.output

    # 5. Restore/View latest checkpoint
    restore_res = runner.invoke(app, ["checkpoint", "restore", "latest", temp_repo.as_posix()])
    assert restore_res.exit_code == 0
    assert "Refactoring main logic" in restore_res.output
    assert "main.py, helper.py" in restore_res.output
    assert "Test everything" in restore_res.output
