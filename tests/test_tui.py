from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from synap_git.cli.tui import SynapInteractiveREPL
from synap_git.storage.global_memory import GlobalMemoryStore


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "test_repo"
    r.mkdir()
    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=r, check=True, capture_output=True)
    subprocess.run(
        [git_bin, "config", "user.email", "test@example.com"],
        cwd=r,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [git_bin, "config", "user.name", "Tester"], cwd=r, check=True, capture_output=True
    )
    (r / "main.py").write_text("def hello(): pass\n", encoding="utf-8")
    subprocess.run([git_bin, "add", "."], cwd=r, check=True, capture_output=True)
    subprocess.run([git_bin, "commit", "-m", "init"], cwd=r, check=True, capture_output=True)
    return r


def test_tui_commands_lifecycle(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Use isolated global DB
    test_global_db = repo / ".synap" / "global_tui.db"
    monkeypatch.setattr(GlobalMemoryStore, "DEFAULT_DB_PATH", test_global_db)

    repl = SynapInteractiveREPL(repo_path=repo)

    # 1. /init
    assert repl.execute_command("/init") is True

    # 2. /status (slash and non-slash)
    assert repl.execute_command("/status") is True
    assert repl.execute_command("status") is True

    # 3. /help
    assert repl.execute_command("/help") is True

    # 4. /remember and /forget
    assert repl.execute_command("/remember db_timeout Connection timeout set to 5000ms") is True
    rec = repl.runtime.store.get_recent_memory(context_key="db_timeout")
    assert len(rec) == 1
    assert "5000ms" in rec[0]["payload"]

    assert repl.execute_command("/forget db_timeout") is True
    rec_after = repl.runtime.store.get_recent_memory(context_key="db_timeout")
    assert len(rec_after) == 0

    # 5. /find
    assert repl.execute_command("/find hello") is True

    # 6. /wiki
    assert repl.execute_command("/wiki status") is True

    # 7. /global and /ingest
    gstore = GlobalMemoryStore(db_path=test_global_db)
    added = gstore.add_memory(
        context_key="editor_tabs",
        content="Indent with 4 spaces",
        category="style",
        summary="4 spaces",
    )
    assert repl.execute_command("/global") is True
    assert repl.execute_command(f"/ingest {added['global_id']}") is True
    ingested = repl.runtime.store.get_recent_memory(context_key="editor_tabs")
    assert len(ingested) == 1

    # 8. /model
    assert repl.execute_command("/model probe") is True
    assert repl.execute_command("/model set ollama:llama3") is True

    # 9. /skill
    assert repl.execute_command("/skill export") is True
    assert (repo / "SKILL.md").exists()

    # 10. /doctor
    assert repl.execute_command("/doctor") is True
    assert repl.execute_command("/doctor --fix") is True

    # 11. Empty or unknown command
    assert repl.execute_command("") is True
    assert repl.execute_command("/unknown_command_xyz") is True

    # 12. /exit and /quit
    assert repl.execute_command("/exit") is False
    assert repl.execute_command("/quit") is False
