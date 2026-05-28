from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from synap_git.cli.main import app
from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime


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


def test_wiki_and_usage_cli(temp_repo: Path) -> None:
    runner = CliRunner()

    # 1. Initialize synapse
    init_res = runner.invoke(app, ["init", temp_repo.as_posix(), "--skip-llm", "--quiet"])
    assert init_res.exit_code == 0, init_res.output

    # 2. Check usage show initially (should be empty/no calls)
    usage_res = runner.invoke(app, ["usage", "show", temp_repo.as_posix()])
    assert usage_res.exit_code == 0
    assert "No LLM calls recorded yet" in usage_res.output

    # 3. Manually add an LLM call to database
    settings = SynapSettings(repository_path=temp_repo, profile=RuntimeProfile.TEST)
    runtime = SynapRuntime(settings)
    runtime.initialize_storage()
    runtime.store.put_llm_call(
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=100,
        output_tokens=50,
        purpose="retrieval",
    )

    # 4. Check usage show again with standard terminal columns to avoid truncation
    usage_res2 = runner.invoke(app, ["usage", "show", temp_repo.as_posix()], env={"COLUMNS": "120"})
    assert usage_res2.exit_code == 0
    assert "openai" in usage_res2.output
    assert "gpt-4o-mini" in usage_res2.output
    assert "retrieval" in usage_res2.output

    # 5. Clear usage
    clear_res = runner.invoke(app, ["usage", "clear", temp_repo.as_posix()])
    assert clear_res.exit_code == 0
    assert "cleared" in clear_res.output

    usage_res3 = runner.invoke(app, ["usage", "show", temp_repo.as_posix()])
    assert "No LLM calls recorded" in usage_res3.output

    # 6. Check wiki list initially (should be empty or none)
    wiki_res = runner.invoke(app, ["wiki", "list", temp_repo.as_posix()])
    assert wiki_res.exit_code == 0
    assert "No wiki documentation" in wiki_res.output

    # 7. Manually write a wiki file to state dir
    wiki_dir = runtime.settings.state_path / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    wiki_file = wiki_dir / "main.py.md"
    wiki_file.write_text("# Main Wiki Page\nDetailed documentation.", encoding="utf-8")

    # 8. Check wiki list again
    wiki_res2 = runner.invoke(app, ["wiki", "list", temp_repo.as_posix()])
    assert wiki_res2.exit_code == 0
    assert "main.py.md" in wiki_res2.output

    # 9. Show wiki
    show_res = runner.invoke(app, ["wiki", "show", "main.py.md", temp_repo.as_posix()])
    assert show_res.exit_code == 0
    assert "Main Wiki Page" in show_res.output
    assert "Detailed documentation" in show_res.output
