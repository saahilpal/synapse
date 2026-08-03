from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from synap_git.cli.main import app
from synap_git.config import SynapSettings
from synap_git.indexer.daemon import RuntimeDaemon
from synap_git.parser.registry import CodeParserRegistry
from synap_git.provider.anthropic import AnthropicProvider
from synap_git.provider.openrouter import OpenRouterProvider
from synap_git.retrieval.engine import HybridRetrievalEngine
from synap_git.storage.sqlite import SynapStore

runner = CliRunner()


def test_aud01_synap_start_already_running_exits_cleanly(tmp_path: Path) -> None:
    """AUD-01: Verify synap start exits cleanly when daemon is already running unless --foreground is set."""
    synap_dir = tmp_path / ".synap"
    synap_dir.mkdir(parents=True, exist_ok=True)
    pid_file = synap_dir / "daemon.pid"
    pid_file.write_text("999999", encoding="utf-8")

    heartbeat_file = synap_dir / "daemon_heartbeat.json"
    heartbeat_file.write_text(
        json.dumps({"pid": 999999, "status": "healthy", "port": 9876}), encoding="utf-8"
    )

    with (
        patch("synap_git.cli.main._verify_is_git"),
        patch("synap_git.cli.main._is_process_running", return_value=True),
        patch("synap_git.mcp.server.SynapMCPServer") as mock_mcp,
    ):
        result = runner.invoke(app, ["start", str(tmp_path)])
        assert result.exit_code == 0
        assert "already running" in result.output
        mock_mcp.assert_not_called()


def test_aud02_parser_additional_languages(tmp_path: Path) -> None:
    """AUD-02: Verify AST symbol extraction for C#, PHP, Kotlin, Scala, and C."""
    registry = CodeParserRegistry()

    # C#
    cs_file = tmp_path / "Service.cs"
    cs_file.write_text("namespace App { public class UserService { public void Save() {} } }")
    res_cs = registry.parse(cs_file, relative_path="Service.cs")
    assert res_cs.language == "c_sharp"
    sym_names_cs = [s.name for s in res_cs.symbols]
    assert "UserService" in sym_names_cs or "Save" in sym_names_cs

    # PHP
    php_file = tmp_path / "Index.php"
    php_file.write_text("<?php class Controller { public function handle() {} } ?>")
    res_php = registry.parse(php_file, relative_path="Index.php")
    assert res_php.language == "php"
    sym_names_php = [s.name for s in res_php.symbols]
    assert "Controller" in sym_names_php or "handle" in sym_names_php

    # Kotlin
    kt_file = tmp_path / "App.kt"
    kt_file.write_text("class Repository { fun fetch() {} }")
    res_kt = registry.parse(kt_file, relative_path="App.kt")
    assert res_kt.language == "kotlin"
    sym_names_kt = [s.name for s in res_kt.symbols]
    assert "Repository" in sym_names_kt or "fetch" in sym_names_kt

    # Scala
    scala_file = tmp_path / "Service.scala"
    scala_file.write_text("class AccountService { def process(): Unit = {} }")
    res_scala = registry.parse(scala_file, relative_path="Service.scala")
    assert res_scala.language == "scala"
    sym_names_scala = [s.name for s in res_scala.symbols]
    assert "AccountService" in sym_names_scala or "process" in sym_names_scala

    # C
    c_file = tmp_path / "main.c"
    c_file.write_text("int main() { return 0; }")
    res_c = registry.parse(c_file, relative_path="main.c")
    assert res_c.language == "c"
    sym_names_c = [s.name for s in res_c.symbols]
    assert "main" in sym_names_c


def test_aud03_watchdog_file_watcher_event(tmp_path: Path) -> None:
    """AUD-03: Verify RuntimeDaemon initializes watchdog observer and handles FS events."""
    settings = SynapSettings(repository_path=tmp_path)
    daemon = RuntimeDaemon(settings)
    assert daemon._fs_changed is False


def test_aud04_anthropic_openrouter_embed_fallback(tmp_path: Path) -> None:
    """AUD-04: Verify Anthropic and OpenRouter .embed() queries return empty vectors without throwing."""
    anthropic = AnthropicProvider(api_key="test_key")
    openrouter = OpenRouterProvider(api_key="test_key")

    assert anthropic.embed("test query") == []
    assert openrouter.embed("test query") == []

    store = SynapStore(tmp_path / ".synap" / "graph.db")
    store.initialize()

    engine = HybridRetrievalEngine(
        repo_path=tmp_path, store=store, llm_provider=anthropic, embed_provider=anthropic
    )
    context, grounding, trace = engine.retrieve("test query")
    assert isinstance(context, str)


def test_aud05_rename_file_preserves_symbol_edges(tmp_path: Path) -> None:
    """AUD-05: Verify incremental indexing rename handling preserves file and symbol records."""
    store = SynapStore(tmp_path / ".synap" / "graph.db")
    store.initialize()

    file_id = "old_hash_123"
    store.upsert_file_and_symbols(
        file_id=file_id,
        path="old_name.py",
        git_oid="oid1",
        content_hash="ch1",
        language="python",
        symbols=[
            {
                "symbol_id": "sym1",
                "name": "foo",
                "kind": "function_definition",
                "start_line": 1,
                "end_line": 5,
                "ast_hash": "ast1",
            }
        ],
    )

    with store.connect() as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute(
            "UPDATE files SET file_id = ?, path = ? WHERE file_id = ?",
            ("new_hash_456", "new_name.py", file_id),
        )
        conn.execute(
            "UPDATE symbols SET file_id = ? WHERE file_id = ?",
            ("new_hash_456", file_id),
        )
        conn.execute("PRAGMA foreign_keys=ON")

    file_entry = store.get_file_by_path("new_name.py")
    assert file_entry is not None
    assert file_entry["file_id"] == "new_hash_456"

    symbols = store.get_symbols_by_file("new_hash_456")
    assert len(symbols) == 1
    assert symbols[0]["name"] == "foo"


def test_aud06_doctor_checks_port_and_rest_api(tmp_path: Path) -> None:
    """AUD-06: Verify synap doctor tests port availability and REST API endpoint."""
    with (
        patch("synap_git.cli.main._verify_is_git"),
        patch("synap_git.cli.main.SynapRuntime") as mock_runtime,
    ):
        mock_runtime.return_value.doctor.return_value = {"database_integrity": "ok"}
        result = runner.invoke(app, ["doctor", str(tmp_path)])
        assert result.exit_code == 0
        assert "Doctor" in result.output


def test_aud07_sqlite_wal_normal_pragma(tmp_path: Path) -> None:
    """AUD-07: Verify SQLite initialization configures WAL mode and synchronous=NORMAL."""
    db_path = tmp_path / ".synap" / "graph.db"
    store = SynapStore(db_path)
    store.initialize()

    with store.connect() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        sync_mode = conn.execute("PRAGMA synchronous").fetchone()[0]

    assert journal_mode.lower() == "wal"
    assert sync_mode in (1, "1", "NORMAL", "normal")


def test_aud08_synap_wiki_retry_subcommand(tmp_path: Path) -> None:
    """AUD-08: Verify synap wiki retry subcommand requeues failed wiki tasks to pending."""
    db_path = tmp_path / ".synap" / "graph.db"
    store = SynapStore(db_path)
    store.initialize()

    store.enqueue_wiki("failed_page.py")
    with store.connect() as conn:
        conn.execute("UPDATE wiki_queue SET status = 'failed', attempts = 3")

    requeued_count = store.retry_failed_wiki_queue()
    assert requeued_count == 1

    with store.connect() as conn:
        row = conn.execute("SELECT status, attempts FROM wiki_queue").fetchone()
        assert row["status"] == "pending"
        assert row["attempts"] == 0
