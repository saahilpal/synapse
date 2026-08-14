from __future__ import annotations

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from synap_git.cli.main import app

runner = CliRunner()


def test_index_and_sync_cli(tmp_path: Path) -> None:
    # Setup temporary git repo
    subprocess.run(["git", "init", "-b", "main", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    test_file = tmp_path / "main.py"
    test_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"], cwd=tmp_path, check=True, capture_output=True
    )

    # 1. Run synap index
    res = runner.invoke(app, ["index", str(tmp_path), "--skip-llm"])
    assert res.exit_code == 0
    assert "Indexing complete" in res.stdout or "files" in res.stdout

    # 2. Run synap sync
    res_sync = runner.invoke(app, ["sync", str(tmp_path), "--skip-llm"])
    assert res_sync.exit_code == 0
    assert "Indexing complete" in res_sync.stdout or "files" in res_sync.stdout

    # 3. Test JSON output
    res_json = runner.invoke(app, ["index", str(tmp_path), "--skip-llm", "--json"])
    assert res_json.exit_code == 0
    assert '"state": "indexed"' in res_json.stdout
