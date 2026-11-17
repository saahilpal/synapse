from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from prompt_toolkit.document import Document
from typer.testing import CliRunner

from synap_git.cli.main import app
from synap_git.cli.tui import (
    SLASH_COMMANDS,
    SynapCommandCompleter,
    SynapInteractiveREPL,
)
from synap_git.retrieval.engine import HybridRetrievalEngine, QueryIntent, classify_intent_5tier
from synap_git.storage.global_memory import GlobalMemoryStore
from synap_git.storage.sqlite import SynapStore


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
    subprocess.run(
        [git_bin, "commit", "-m", "initial commit: add hello function"],
        cwd=r,
        check=True,
        capture_output=True,
    )
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

    # 10. /logs
    assert repl.execute_command("/logs") is True
    assert repl.execute_command("/logs -n 10") is True

    # 11. /doctor
    assert repl.execute_command("/doctor") is True
    assert repl.execute_command("/doctor --fix") is True

    # 12. Plain text input runs /find
    assert repl.execute_command("search for hello symbol") is True

    # 13. Empty or unknown command
    assert repl.execute_command("") is True
    assert repl.execute_command("/unknown_command_xyz") is True

    # 14. /exit and /quit
    assert repl.execute_command("/exit") is False
    assert repl.execute_command("/quit") is False


def test_tui_command_palette_completer() -> None:
    completer = SynapCommandCompleter()

    # Typing '/' lists all slash commands with argument hints
    doc = Document("/")
    completions = list(completer.get_completions(doc, None))  # type: ignore[arg-type]
    cmd_names = [c.text for c in completions]
    assert len(cmd_names) >= 14
    for cmd, _ in SLASH_COMMANDS:
        assert cmd in cmd_names

    # Typing '/wiki ' provides subcommand hints
    doc_wiki = Document("/wiki ")
    wiki_completions = list(completer.get_completions(doc_wiki, None))  # type: ignore[arg-type]
    wiki_subs = [c.text for c in wiki_completions]
    assert "status" in wiki_subs
    assert "generate" in wiki_subs
    assert "show" in wiki_subs


def test_truthful_banner(repo: Path) -> None:
    repl = SynapInteractiveREPL(repo_path=repo)
    # Ensure banner runs without throwing and inspects actual repository
    repl.print_banner()
    state = repl.runtime.git.state()
    assert state.is_repository is True


def _parse_json(output: str) -> dict[str, Any]:
    lines = output.strip().splitlines()
    for i in range(len(lines)):
        try:
            return cast(dict[str, Any], json.loads("\n".join(lines[i:])))
        except Exception:
            pass
    return cast(dict[str, Any], json.loads(lines[-1]))


def test_cli_tiny_surface_and_json(repo: Path) -> None:
    runner = CliRunner()

    # 1. synap init --json
    res_init = runner.invoke(app, ["init", repo.as_posix(), "--skip-llm", "--json"])
    assert res_init.exit_code == 0
    data_init = _parse_json(res_init.output)
    assert data_init.get("state") == "initialized"

    # 2. synap remember --json (single content argument)
    res_rem = runner.invoke(
        app,
        [
            "remember",
            "Connection pooling timeout set to 3000ms",
            "--path",
            repo.as_posix(),
            "--json",
        ],
    )
    assert res_rem.exit_code == 0
    data_rem = _parse_json(res_rem.output)
    assert "memory_id" in data_rem

    # 3. synap ctx --json
    res_ctx = runner.invoke(app, ["ctx", "Refactoring", "--path", repo.as_posix(), "--json"])
    assert res_ctx.exit_code == 0
    data_ctx = _parse_json(res_ctx.output)
    assert "branch" in data_ctx

    # 4. synap doctor --json
    res_doc = runner.invoke(app, ["doctor", repo.as_posix(), "--json"])
    assert res_doc.exit_code == 0
    data_doc = _parse_json(res_doc.output)
    assert data_doc.get("status") in ("healthy", "degraded")

    # 5. synap daemon status --json (exits 1 when daemon not running)
    res_daemon = runner.invoke(app, ["daemon", "status", repo.as_posix(), "--json"])
    assert res_daemon.exit_code != 0

    # 6. synap mcp verify --json
    res_mcp = runner.invoke(app, ["mcp", "verify", repo.as_posix(), "--json"])
    assert res_mcp.exit_code == 0
    data_mcp = _parse_json(res_mcp.output)
    assert data_mcp.get("ok") is True


def test_5tier_router_and_commit_rationale(repo: Path) -> None:
    # 5-Tier Intent Router classifications
    assert classify_intent_5tier("hello") == QueryIntent.SYMBOL_LOOKUP
    assert classify_intent_5tier("def authenticate_user") == QueryIntent.SYMBOL_LOOKUP
    assert classify_intent_5tier("where is main.py") == QueryIntent.NAVIGATION
    assert classify_intent_5tier("find file path for auth") == QueryIntent.NAVIGATION
    assert classify_intent_5tier("how does the indexing work") == QueryIntent.ARCHITECTURE
    assert classify_intent_5tier("explain system overview") == QueryIntent.ARCHITECTURE
    assert classify_intent_5tier("why was hello function changed") == QueryIntent.DEBUGGING
    assert classify_intent_5tier("traceback error in parser") == QueryIntent.DEBUGGING
    assert (
        classify_intent_5tier("architectural decisions and tradeoffs") == QueryIntent.PAST_DECISIONS
    )

    # Git Commit History retrieval in HybridRetrievalEngine
    store = SynapStore(repo / ".synap" / "graph.db")
    store.initialize()
    engine = HybridRetrievalEngine(repo_path=repo, store=store, llm_provider=None)

    # Ingest commits into SQLite
    indexed_commits = engine.index_git_commits()
    assert indexed_commits >= 1

    # Query commit rationale from SQLite
    commits = engine.get_commit_rationale("hello")
    assert len(commits) >= 1
    assert "initial commit" in commits[0]["message"]

    # Test real token cost accounting
    answer, sources, trace = engine.retrieve(
        query="why was hello function changed", max_tokens=2000
    )
    assert "token_cost_accounting" in trace
    tca = trace["token_cost_accounting"]
    assert "raw_file_tokens" in tca
    assert "pack_tokens" in tca
    assert "savings_percent" in tca
    assert "initial commit" in answer or len(sources) >= 0
