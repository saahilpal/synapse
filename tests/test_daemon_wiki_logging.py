from __future__ import annotations

import asyncio
import json
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from synap_git.config import LoggingMode, RuntimeProfile, SynapSettings
from synap_git.diagnostics.logger import configure_logging, get_logger, stop_logging
from synap_git.indexer.daemon import RuntimeDaemon


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "hello.py").write_text("def hello() -> str:\n    return 'world'\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo, check=True)
    return repo


def _read_log_events(log_file: Path) -> list[dict[str, object]]:
    if not log_file.exists():
        return []
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    events: list[dict[str, object]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


async def _wait_for_log_event(
    log_file: Path,
    event_name: str,
    *,
    timeout: float = 1.0,
    **match_fields: object,
) -> dict[str, object]:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        for ev in _read_log_events(log_file):
            if ev.get("event") == event_name:
                if all(ev.get(k) == v for k, v in match_fields.items()):
                    return ev
        await asyncio.sleep(0.02)
    raise TimeoutError(
        f"Timed out waiting for event '{event_name}' ({match_fields}) in {log_file} within {timeout}s"
    )


@pytest.mark.asyncio
async def test_daemon_wiki_logging_events(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    synap_dir = repo / ".synap"
    log_dir = synap_dir / "logs"
    log_file = log_dir / "daemon.log"

    settings = SynapSettings(
        repository_path=repo,
        sqlite_path=synap_dir / "synapse.db",
        state_path=synap_dir,
        log_path=log_dir,
        profile=RuntimeProfile.TEST,
        logging_mode=LoggingMode.JSON,
    )
    configure_logging(settings)

    daemon = RuntimeDaemon(settings, debounce_seconds=0.05)
    daemon.runtime.initialize_storage()
    daemon.runtime.bootstrap()

    # Enqueue a valid file for wiki generation
    daemon.runtime.store.enqueue_wiki("hello.py")

    worker_task = asyncio.create_task(daemon._wiki_worker_loop())

    try:
        # 1. Assert wiki_job_started within 1 second
        job_started = await _wait_for_log_event(log_file, "wiki_job_started", timeout=1.0)
        assert job_started.get("component") == "wiki"
        assert int(str(job_started.get("total", 0))) >= 1

        # 2. Assert wiki_file_progress for hello.py within 1 second
        file_prog = await _wait_for_log_event(
            log_file, "wiki_file_progress", path="hello.py", timeout=1.0
        )
        assert file_prog.get("component") == "wiki"
        assert file_prog.get("path") == "hello.py"
        assert int(str(file_prog.get("n", 0))) >= 1
        assert int(str(file_prog.get("total", 0))) >= 1

        # 3. Assert wiki_file_done for hello.py within 1 second
        file_done = await _wait_for_log_event(
            log_file, "wiki_file_done", path="hello.py", timeout=1.0
        )
        assert file_done.get("component") == "wiki"
        assert file_done.get("path") == "hello.py"
        assert "duration" in file_done
        assert "model" in file_done

        # 4. Assert wiki_job_finished within 1 second
        job_fin = await _wait_for_log_event(log_file, "wiki_job_finished", timeout=1.0)
        assert job_fin.get("component") == "wiki"
        assert int(str(job_fin.get("processed", 0))) >= 1

        # 5. Enqueue up-to-date file to trigger wiki_file_skipped
        daemon.runtime.store.enqueue_wiki("hello.py")
        file_skipped = await _wait_for_log_event(
            log_file, "wiki_file_skipped", path="hello.py", timeout=1.0
        )
        assert file_skipped.get("component") == "wiki"
        assert file_skipped.get("path") == "hello.py"
        assert file_skipped.get("reason") in ("up_to_date", "source_file_missing")

        # 6. Enqueue file that triggers failure with secret and content simulation
        secret_key = "sk-1234567890abcdef1234567890abcdef"
        daemon.runtime.wiki.ensure_wiki_page = MagicMock(  # type: ignore[method-assign]
            side_effect=RuntimeError(f"Simulated failure with api_key={secret_key}")
        )
        (repo / "failing.py").write_text("def failing() -> None:\n    pass\n")
        daemon.runtime.store.enqueue_wiki("failing.py")

        file_failed = await _wait_for_log_event(
            log_file, "wiki_file_failed", path="failing.py", timeout=1.0
        )
        assert file_failed.get("component") == "wiki"
        assert file_failed.get("path") == "failing.py"
        error_msg = str(file_failed.get("error", ""))
        assert secret_key not in error_msg
        assert "[REDACTED]" in error_msg

        # Ensure no secrets or source code leaked in log
        raw_log = log_file.read_text(encoding="utf-8")
        assert secret_key not in raw_log
        assert "def failing() -> None:" not in raw_log

    finally:
        daemon.stop()
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        stop_logging()


@pytest.mark.asyncio
async def test_logging_components_and_thread_flushing(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_file = log_dir / "daemon.log"

    settings = SynapSettings(
        repository_path=tmp_path,
        sqlite_path=tmp_path / "synapse.db",
        state_path=tmp_path,
        log_path=log_dir,
        profile=RuntimeProfile.TEST,
        logging_mode=LoggingMode.JSON,
    )
    configure_logging(settings)

    wiki_log = get_logger("wiki")
    daemon_log = get_logger("daemon")
    indexer_log = get_logger("indexer")
    storage_log = get_logger("storage")
    cli_log = get_logger("cli")

    def background_thread_work() -> None:
        wiki_log.info("thread_wiki_action", step="background")
        daemon_log.info("thread_daemon_action", step="background")
        indexer_log.info("thread_indexer_action", step="background")
        storage_log.info("thread_storage_action", step="background")
        cli_log.info("thread_cli_action", step="background")

    # Run in background thread via asyncio.to_thread
    await asyncio.to_thread(background_thread_work)

    # Immediately check events in log (flushed immediately without waiting)
    ev_wiki = await _wait_for_log_event(log_file, "thread_wiki_action", timeout=1.0)
    assert ev_wiki.get("component") == "wiki"

    ev_daemon = await _wait_for_log_event(log_file, "thread_daemon_action", timeout=1.0)
    assert ev_daemon.get("component") == "daemon"

    ev_indexer = await _wait_for_log_event(log_file, "thread_indexer_action", timeout=1.0)
    assert ev_indexer.get("component") == "indexer"

    ev_storage = await _wait_for_log_event(log_file, "thread_storage_action", timeout=1.0)
    assert ev_storage.get("component") == "storage"

    ev_cli = await _wait_for_log_event(log_file, "thread_cli_action", timeout=1.0)
    assert ev_cli.get("component") == "cli"

    stop_logging()
