from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from synap_git.cli.main import app


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


def test_setup_cli_ollama_fallback(
    temp_repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Point configuration path to tmp_path to avoid modifying user's real ~/.config/synap/config.toml
    config_dir = tmp_path / ".config" / "synap"
    monkeypatch.setenv("SYNAP_CONFIG", (config_dir / "config.toml").as_posix())

    runner = CliRunner()

    # Inputs for non-TTY:
    # 1. provider: "ollama"
    # 2. model: "qwen2.5-coder:14b"
    # 3. URL: "http://localhost:11434"
    # 4. Save anyway (on connection failure): "y"
    inputs = "ollama\nqwen2.5-coder:14b\nhttp://localhost:11434\ny\n"
    res = runner.invoke(app, ["setup", temp_repo.as_posix()], input=inputs)

    assert res.exit_code == 0, res.output
    assert "Synap Initial Setup" in res.output
    assert "Connection Verification Failed" in res.output or "Connection verified" in res.output
    assert "Configuration saved" in res.output
    assert "Setup complete" in res.output

    # Verify saved configuration
    config_file = config_dir / "config.toml"
    assert config_file.exists()
    content = config_file.read_text()
    assert 'llm_provider = "ollama"' in content
    assert 'llm_model = "qwen2.5-coder:14b"' in content
    assert 'ollama_url = "http://localhost:11434"' in content


def test_setup_cli_openai_fallback(
    temp_repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Point configuration path to tmp_path to avoid modifying user's real ~/.config/synap/config.toml
    config_dir = tmp_path / ".config" / "synap"
    monkeypatch.setenv("SYNAP_CONFIG", (config_dir / "config.toml").as_posix())

    runner = CliRunner()

    # Inputs for non-TTY:
    # 1. provider: "openai"
    # 2. model: "gpt-4o"
    # 3. API key: "sk-testkey123"
    # 4. Save anyway (on connection failure): "y"
    inputs = "openai\ngpt-4o\nsk-testkey123\ny\n"
    res = runner.invoke(app, ["setup", temp_repo.as_posix()], input=inputs)

    assert res.exit_code == 0, res.output
    assert "Synap Initial Setup" in res.output
    assert "Connection Verification Failed" in res.output or "Connection verified" in res.output
    assert "Configuration saved" in res.output
    assert "Secrets saved securely" in res.output
    assert "Setup complete" in res.output

    # Verify saved configuration (only non-sensitive settings should be stored in config.toml)
    config_file = config_dir / "config.toml"
    assert config_file.exists()
    content = config_file.read_text()
    assert 'llm_provider = "openai"' in content
    assert 'llm_model = "gpt-4o"' in content
    assert "sk-testkey" not in content
