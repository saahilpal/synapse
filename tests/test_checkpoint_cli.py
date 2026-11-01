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

    # 6. Test synap context and preamble commands
    context_res = runner.invoke(app, ["context", "--path", temp_repo.as_posix()])
    assert context_res.exit_code == 0
    assert "Synapse Repository Context" in context_res.output
    assert "Refactoring main logic" in context_res.output

    context_json = runner.invoke(app, ["context", "--path", temp_repo.as_posix(), "--json"])
    assert context_json.exit_code == 0
    assert '"branch": "main"' in context_json.output

    preamble_res = runner.invoke(app, ["preamble", "--path", temp_repo.as_posix()])
    assert preamble_res.exit_code == 0
    assert "Synapse Repository Context" in preamble_res.output

    # 7. Test synap rules command
    rules_stdout = runner.invoke(app, ["rules", "--stdout"])
    assert rules_stdout.exit_code == 0
    assert "Synapse AI Agent Directives" in rules_stdout.output

    rules_write = runner.invoke(app, ["rules", "--path", temp_repo.as_posix(), "--target", "all"])
    assert rules_write.exit_code == 0
    assert (temp_repo / ".cursorrules").exists()
    assert (temp_repo / "CLAUDE.md").exists()
    assert (temp_repo / "AGENTS.md").exists()
    assert "Synapse AI Agent Directives" in (temp_repo / ".cursorrules").read_text(encoding="utf-8")

    # 8. Test synap install command
    install_res = runner.invoke(
        app, ["install", temp_repo.as_posix(), "--ide", "cursor", "--local"]
    )
    assert install_res.exit_code == 0
    assert "Synapse successfully installed" in install_res.output
    cursor_mcp = temp_repo / ".cursor" / "mcp.json"
    assert cursor_mcp.exists()
    assert "synap" in cursor_mcp.read_text(encoding="utf-8")

    # 9. Test hooks install and uninstall
    hook_install_res = runner.invoke(app, ["hooks", "install", temp_repo.as_posix()])
    assert hook_install_res.exit_code == 0
    post_commit_hook = temp_repo / ".git" / "hooks" / "post-commit"
    assert post_commit_hook.exists()
    assert "SYNAP HOOK START" in post_commit_hook.read_text(encoding="utf-8")

    hook_uninstall_res = runner.invoke(app, ["hooks", "uninstall", temp_repo.as_posix()])
    assert hook_uninstall_res.exit_code == 0
    if post_commit_hook.exists():
        assert "SYNAP HOOK START" not in post_commit_hook.read_text(encoding="utf-8")

    # 10. Test memory remember and list commands
    rem_res = runner.invoke(
        app,
        [
            "memory",
            "remember",
            "ci_pipeline",
            "CI runs pytest and ruff before deployment",
            "--path",
            temp_repo.as_posix(),
        ],
    )
    assert rem_res.exit_code == 0
    assert "Memory recorded under key 'ci_pipeline'" in rem_res.output

    list_res = runner.invoke(
        app,
        ["memory", "list", temp_repo.as_posix(), "--key", "ci_pipeline"],
    )
    assert list_res.exit_code == 0
    assert "ci_pipeline" in list_res.output

    # 11. Test new ergonomic commands: blast, hubs, outline, diff, test, explain, pack
    blast_res = runner.invoke(app, ["blast", "--path", temp_repo.as_posix()])
    assert blast_res.exit_code == 0

    hubs_res = runner.invoke(app, ["hubs", "--path", temp_repo.as_posix()])
    assert hubs_res.exit_code == 0
    assert "Architectural Hubs" in hubs_res.output

    outline_res = runner.invoke(app, ["outline", "main.py", "--path", temp_repo.as_posix()])
    assert outline_res.exit_code == 0

    diff_res = runner.invoke(app, ["diff", "--path", temp_repo.as_posix()])
    assert diff_res.exit_code == 0

    test_res = runner.invoke(app, ["test", "--path", temp_repo.as_posix(), "--dry-run"])
    assert test_res.exit_code == 0
    assert "pytest" in test_res.output

    explain_res = runner.invoke(app, ["explain", "hello", "--path", temp_repo.as_posix()])
    assert explain_res.exit_code == 0
    assert "Structural Symbol Analysis" in explain_res.output

    pack_res = runner.invoke(app, ["pack", "--path", temp_repo.as_posix(), "--max-tokens", "4000"])
    assert pack_res.exit_code == 0
    assert "Synapse Repository Context Pack" in pack_res.output
