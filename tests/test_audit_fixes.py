from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synap_git.api.app import create_app
from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.git.state import GitChangeKind, GitRepository, GitState
from synap_git.indexer.engine import SynapRuntime


def test_path_traversal_protection(tmp_path: Path) -> None:
    # Set up settings
    settings = SynapSettings(
        repository_path=tmp_path,
        state_path=tmp_path / ".synap",
        profile=RuntimeProfile.TEST,
    )
    runtime = SynapRuntime(settings)
    runtime.initialize_storage()

    # Write a test wiki file
    wiki_dir = settings.state_path / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "safe.md").write_text("Hello safe wiki", encoding="utf-8")

    # Write an unsafe file outside the wiki dir
    (tmp_path / "unsafe.md").write_text("Secret content", encoding="utf-8")

    app = create_app(runtime)
    client = TestClient(app)

    # Test safe request
    res = client.get("/wiki/safe")
    assert res.status_code == 200
    assert res.json()["content"] == "Hello safe wiki"

    # Test path traversal request (should return 403)
    res_unsafe = client.get("/wiki/..%2Funsafe")
    assert res_unsafe.status_code == 403
    assert "Path traversal detected" in res_unsafe.text


def test_double_revert_classification(tmp_path: Path) -> None:
    # Test git revert vs double-revert message classification

    prev = GitState(
        repository_path=tmp_path,
        is_repository=True,
        head_commit="abcdef",
        branch="main",
    )

    # Case 1: Simple Revert Message
    curr_revert = GitState(
        repository_path=tmp_path,
        is_repository=True,
        head_commit="123456",
        branch="main",
        commit_message='Revert "feat: something"',
    )
    change1 = GitRepository.classify(prev, curr_revert)
    assert change1.kind == GitChangeKind.REVERT

    # Case 2: Double Revert Message
    curr_double_revert = GitState(
        repository_path=tmp_path,
        is_repository=True,
        head_commit="789012",
        branch="main",
        commit_message='Revert "Revert "feat: something""',
    )
    change2 = GitRepository.classify(prev, curr_double_revert)
    assert change2.kind == GitChangeKind.COMMIT


def test_credentials_permissions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Mock fallback credential loading
    monkeypatch.setenv("HOME", tmp_path.as_posix())
    settings = SynapSettings(
        repository_path=tmp_path,
        profile=RuntimeProfile.TEST,
    )

    cred_dir = tmp_path / ".synap"
    cred_dir.mkdir(parents=True, exist_ok=True)
    cred_file = cred_dir / "credentials"
    cred_file.write_text("SYNAP_ANTHROPIC_API_KEY=testkey\n", encoding="utf-8")

    # Set permissions:
    if sys.platform != "win32":
        # Group/others have permissions (unsafe)
        cred_file.chmod(0o644)
        assert settings._get_fallback_credential("SYNAP_ANTHROPIC_API_KEY") is None

        # Owner-only permissions (safe)
        cred_file.chmod(0o600)
        assert settings._get_fallback_credential("SYNAP_ANTHROPIC_API_KEY") == "testkey"
    else:
        # On Windows permission checking is skipped, should load successfully
        assert settings._get_fallback_credential("SYNAP_ANTHROPIC_API_KEY") == "testkey"


def test_doctor_git_and_gh_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil
    import subprocess

    from typer.testing import CliRunner

    from synap_git.cli.main import app

    # Create a temp git repository
    repo = tmp_path / "repo"
    repo.mkdir()

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    (repo / ".gitignore").write_text(".synap/\n", encoding="utf-8")

    runner = CliRunner()

    # Initialize synapse so doctor database checks pass
    init_res = runner.invoke(app, ["init", repo.as_posix(), "--skip-llm", "--quiet"])
    assert init_res.exit_code == 0, init_res.output

    # Store reference to original which
    original_which = shutil.which

    # 1. Test when gh is mock-installed
    def mock_which_installed(cmd: str) -> str | None:
        if cmd == "gh":
            return "/usr/local/bin/gh"
        if cmd == "git":
            return git_bin
        return original_which(cmd)

    monkeypatch.setattr(shutil, "which", mock_which_installed)
    res_installed = runner.invoke(app, ["doctor", repo.as_posix()])
    assert res_installed.exit_code == 0, res_installed.output
    assert "GitHub CLI (gh) installed" in res_installed.output

    # 2. Test when gh is missing (optional warning)
    def mock_which_missing(cmd: str) -> str | None:
        if cmd == "gh":
            return None
        if cmd == "git":
            return git_bin
        return original_which(cmd)

    monkeypatch.setattr(shutil, "which", mock_which_missing)
    res_missing = runner.invoke(app, ["doctor", repo.as_posix()])
    assert res_missing.exit_code == 0, res_missing.output
    assert "gh missing (optional)" in res_missing.output


def test_database_connection_synchronous_pragma(tmp_path: Path) -> None:
    settings = SynapSettings(
        repository_path=tmp_path,
        state_path=tmp_path / ".synap",
        profile=RuntimeProfile.TEST,
    )
    runtime = SynapRuntime(settings)
    runtime.initialize_storage()

    with runtime.store.connect() as conn:
        sync_mode = conn.execute("PRAGMA synchronous").fetchone()[0]
        # NORMAL maps to 1 in SQLite
        assert sync_mode == 1, f"Expected synchronous mode 1 (NORMAL), got {sync_mode}"
