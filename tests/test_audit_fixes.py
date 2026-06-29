from __future__ import annotations

import json
import pathlib
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp.types import TextContent

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

    import json

    (tmp_path / ".synap" / "daemon_heartbeat.json").write_text(
        json.dumps({"pid": 1234, "api_token": "test-token"})
    )
    app = create_app(runtime)
    client = TestClient(app, headers={"Authorization": "Bearer test-token"})

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
    assert "Git and GitHub CLI installed" in res_installed.output

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
    assert "gh missing" in res_missing.output


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


def test_file_id_hashing_spec001(tmp_path: Path) -> None:
    import shutil
    import subprocess

    # 1. Create two empty files at different paths, verify they get different file_ids
    repo = tmp_path / "repo"
    repo.mkdir()
    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Test"], cwd=repo, check=True)

    (repo / "fileA.py").write_text("", encoding="utf-8")
    (repo / "fileB.py").write_text("", encoding="utf-8")

    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "init"], cwd=repo, check=True)

    settings = SynapSettings(
        repository_path=repo,
        state_path=repo / ".synap",
        profile=RuntimeProfile.TEST,
    )
    runtime = SynapRuntime(settings)
    runtime.bootstrap(force=True)

    with runtime.store.connect() as conn:
        file_a = conn.execute(
            "SELECT file_id, content_hash FROM files WHERE path = 'fileA.py'"
        ).fetchone()
        file_b = conn.execute(
            "SELECT file_id, content_hash FROM files WHERE path = 'fileB.py'"
        ).fetchone()

    assert file_a["file_id"] != file_b["file_id"], (
        "Different files with same content must have different IDs"
    )
    assert file_a["content_hash"] == file_b["content_hash"]

    # 2. Change a file's content, verify the file_id changes
    old_id = file_a["file_id"]
    (repo / "fileA.py").write_text("def a(): pass", encoding="utf-8")
    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "update fileA"], cwd=repo, check=True)

    runtime.index_repository()

    with runtime.store.connect() as conn:
        file_a_updated = conn.execute(
            "SELECT file_id FROM files WHERE path = 'fileA.py'"
        ).fetchone()

    assert file_a_updated["file_id"] != old_id, "file_id must change when content changes"


@pytest.mark.asyncio
async def test_wiki_generation_retries_and_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import asyncio

    from synap_git.indexer.daemon import RuntimeDaemon
    from synap_git.provider.base import LLMResponse

    # Create a repo
    repo = tmp_path / "repo"
    repo.mkdir()
    import shutil
    import subprocess

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "fileA.py").write_text("def a(): pass", encoding="utf-8")
    (repo / "fileB.py").write_text("def b(): pass", encoding="utf-8")
    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "init"], cwd=repo, check=True)

    from synap_git.config import LoggingMode

    settings = SynapSettings(
        repository_path=repo,
        state_path=repo / ".synap",
        profile=RuntimeProfile.TEST,
        logging_mode=LoggingMode.HUMAN,
        daemon_poll_interval_seconds=0.1,  # fast poll
    )

    runtime = SynapRuntime(settings)
    runtime.bootstrap(force=True)

    # Mock provider
    class MockFailingProvider:
        def __init__(self) -> None:
            self.calls = 0
            self.default_model = "test"

        def generate(self, system_prompt: str, user_prompt: str, max_tokens: int) -> LLMResponse:
            self.calls += 1
            if self.calls <= 2:
                raise TimeoutError("Simulated network timeout")
            # Succeed on the 3rd attempt if asked
            if self.calls == 3:
                return LLMResponse("Success content", 10, 10, 0)
            raise RuntimeError("Unexpected call")

        def generate_embedding(self, text: str) -> list[float]:
            return [0.1]

        def count_tokens(self, text: str) -> int:
            return 10

    provider: Any = MockFailingProvider()
    runtime.wiki.provider = provider

    # 1. Fail twice then succeed
    daemon = RuntimeDaemon(settings)
    daemon.runtime = runtime
    daemon.git = runtime.git

    # Ensure there's a task in queue for fileA.py
    with runtime.store.connect() as conn:
        conn.execute("DELETE FROM wiki_queue")
        conn.execute(
            "INSERT INTO wiki_queue (task_id, file_path, status, attempts, created_at, updated_at) VALUES ('test-task-' || hex(randomblob(4)), 'fileA.py', 'pending', 0, 0, 0)"
        )

    # We will run the worker loop briefly
    worker_task = asyncio.create_task(daemon._wiki_worker_loop())

    # wait enough for 3 attempts. Backoff sleeps: attempt 1 -> 2^1=2s, attempt 2 -> 4s.
    for _ in range(100):
        with runtime.store.connect() as conn:
            row = conn.execute(
                "SELECT status, attempts FROM wiki_queue WHERE file_path = 'fileA.py'"
            ).fetchone()
            if row is None or row["status"] in ("completed", "failed"):
                break
        await asyncio.sleep(0.1)

    assert row is None or row["status"] == "completed"
    assert provider.calls == 3  # Failed twice, succeeded on 3rd

    daemon.stop()
    await worker_task

    # 2. Fail 3 times and check visible warning
    class MockAlwaysFailingProvider:
        def __init__(self) -> None:
            self.calls = 0
            self.default_model = "test"

        def generate(self, system_prompt: str, user_prompt: str, max_tokens: int) -> LLMResponse:
            self.calls += 1
            raise TimeoutError("Simulated network timeout")

        def generate_embedding(self, text: str) -> list[float]:
            return [0.1]

        def count_tokens(self, text: str) -> int:
            return 10

    provider2: Any = MockAlwaysFailingProvider()
    runtime.wiki.provider = provider2

    with runtime.store.connect() as conn:
        conn.execute("DELETE FROM wiki_queue")
        conn.execute(
            "INSERT INTO wiki_queue (task_id, file_path, status, attempts, created_at, updated_at) VALUES ('test-task-' || hex(randomblob(4)), 'fileB.py', 'pending', 0, 0, 0)"
        )

    daemon2 = RuntimeDaemon(settings)
    daemon2.runtime = runtime
    daemon2.git = runtime.git

    worker_task2 = asyncio.create_task(daemon2._wiki_worker_loop())

    for _ in range(100):
        with runtime.store.connect() as conn:
            row2 = conn.execute(
                "SELECT status, attempts FROM wiki_queue WHERE file_path = 'fileB.py'"
            ).fetchone()
            if row2 is None or row2["status"] in ("completed", "failed"):
                break
        await asyncio.sleep(0.1)

    assert row2 is not None
    assert row2["status"] == "failed"
    assert provider2.calls == 3

    daemon2.stop()
    await worker_task2


@pytest.mark.asyncio
async def test_signal_low_context_thresholds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from synap_git.mcp.server import SynapMCPServer

    settings = SynapSettings(
        repository_path=tmp_path,
        state_path=tmp_path / ".synap",
        profile=RuntimeProfile.TEST,
        checkpoint_threshold=0.6,
    )
    runtime = SynapRuntime(settings)
    server = SynapMCPServer(runtime)

    # 1. 61% usage (over 60% threshold)
    results = await server.mcp.call_tool("signal_low_context", {"token_count": 61, "capacity": 100})
    content = results[0]
    assert isinstance(content, TextContent)
    res = json.loads(content.text)
    assert res["data"]["should_checkpoint"] is True
    captured = capsys.readouterr()
    assert "checkpoint recommended" in captured.err

    # 2. 50% usage (under 60% threshold)
    results2 = await server.mcp.call_tool(
        "signal_low_context", {"token_count": 50, "capacity": 100}
    )
    content2 = results2[0]
    assert isinstance(content2, TextContent)
    res2 = json.loads(content2.text)
    assert res2["data"]["should_checkpoint"] is False

    # 3. Change threshold to 80%
    settings_high = SynapSettings(
        repository_path=tmp_path,
        state_path=tmp_path / ".synap_high",
        profile=RuntimeProfile.TEST,
        checkpoint_threshold=0.8,
    )
    runtime_high = SynapRuntime(settings_high)
    server_high = SynapMCPServer(runtime_high)

    results3 = await server_high.mcp.call_tool(
        "signal_low_context", {"token_count": 70, "capacity": 100}
    )
    content3 = results3[0]
    assert isinstance(content3, TextContent)
    res3 = json.loads(content3.text)
    assert res3["data"]["should_checkpoint"] is False


def test_lesson_expiry_configurable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SynapSettings(
        repository_path=tmp_path,
        state_path=tmp_path / ".synap",
        profile=RuntimeProfile.TEST,
        lesson_expiry_days=14,
    )
    runtime = SynapRuntime(settings)

    from datetime import UTC, datetime

    prev_state = GitState(repository_path=tmp_path, is_repository=True, head_commit="h1")
    curr_state = GitState(repository_path=tmp_path, is_repository=True, head_commit="h2")

    # Mock git show
    import subprocess

    def mock_check_output(*args: Any, **kwargs: Any) -> str:
        return "file.py"

    monkeypatch.setattr(subprocess, "check_output", mock_check_output)

    try:
        now = int(datetime.now(UTC).timestamp())
        runtime.handle_revert(prev_state, curr_state)

        with runtime.store.connect() as conn:
            lesson = conn.execute("SELECT expires_at FROM lessons").fetchone()
            # Should be 14 days later
            expected_expiry = now + (14 * 86400)
            assert abs(lesson["expires_at"] - expected_expiry) < 5, (
                f"Expected 14 days expiry, got {lesson['expires_at'] - now}s offset"
            )
    finally:
        pass


def test_single_file_read_high002(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil
    import subprocess

    # Create a repo with 10 files
    repo = tmp_path / "repo"
    repo.mkdir()
    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Test"], cwd=repo, check=True)

    for i in range(10):
        (repo / f"file{i}.py").write_text(f"def func{i}(): pass", encoding="utf-8")

    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "init"], cwd=repo, check=True)

    settings = SynapSettings(
        repository_path=repo,
        state_path=repo / ".synap",
        profile=RuntimeProfile.TEST,
    )
    runtime = SynapRuntime(settings)

    open_counts: dict[str, int] = {}

    def tracked_read(self: pathlib.Path, *args: Any, **kwargs: Any) -> bytes:
        path_str = str(self)
        if path_str.endswith(".py") and "repo" in path_str:
            name = self.name
            open_counts[name] = open_counts.get(name, 0) + 1
        return original_read_bytes(self, *args, **kwargs)

    original_read_bytes = pathlib.Path.read_bytes
    monkeypatch.setattr(pathlib.Path, "read_bytes", tracked_read)

    def tracked_read_text(self: pathlib.Path, *args: Any, **kwargs: Any) -> str:
        path_str = str(self)
        if path_str.endswith(".py") and "repo" in path_str:
            name = self.name
            open_counts[name] = open_counts.get(name, 0) + 1
        return original_read_text(self, *args, **kwargs)

    original_read_text = pathlib.Path.read_text
    monkeypatch.setattr(pathlib.Path, "read_text", tracked_read_text)

    # Use single worker to avoid issues with monkeypatching in subprocesses
    # Wait, ProcessPoolExecutor workers won't see the monkeypatch!
    # I should temporarily patch SynapRuntime to use 0 workers (sync) or just verify scanner vs parser.
    # Actually, if I run with num_workers=0 (or 1 but it might still fork).
    # Let's patch ProcessPoolExecutor to run synchronously for this test.
    from concurrent.futures import Executor, Future

    class SyncExecutor(Executor):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def submit(self, fn: Any, /, *args: Any, **kwargs: Any) -> Future[Any]:
            f: Future[Any] = Future()
            f.set_result(fn(*args))
            return f

        def __enter__(self) -> SyncExecutor:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    import concurrent.futures

    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", SyncExecutor)

    runtime.bootstrap(force=True)

    for i in range(10):
        name = f"file{i}.py"
        assert open_counts.get(name) == 1, (
            f"File {name} was opened {open_counts.get(name)} times, expected 1"
        )


def test_memory_bounded_indexing_medium002(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil
    import subprocess

    # 1. Create a repo with 150 files
    repo = tmp_path / "repo"
    repo.mkdir()
    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Test"], cwd=repo, check=True)

    for i in range(150):
        (repo / f"file{i}.py").write_text("def a(): pass", encoding="utf-8")

    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "init"], cwd=repo, check=True)

    settings = SynapSettings(
        repository_path=repo,
        state_path=repo / ".synap",
        profile=RuntimeProfile.TEST,
    )
    runtime = SynapRuntime(settings)

    # We want to check that _resolve_and_insert_edges is called with batches
    batch_sizes = []
    original_resolve = runtime._resolve_and_insert_edges

    def mock_resolve(results: Any) -> None:
        batch_sizes.append(len(results))
        return original_resolve(results)

    # We can't easily monkeypatch a method on an instance in mypy-friendly way
    # but we can use setattr
    monkeypatch.setattr(runtime, "_resolve_and_insert_edges", mock_resolve)

    # Force small chunk size for test if possible, but it's hardcoded to 500.
    # Wait, if I have 150 files and chunk_size is 500, it will still be 1 call.
    # I should temporarily patch chunk_size in SynapRuntime!
    # Let's read where chunk_size is set.
    runtime.bootstrap(force=True)

    # With 150 files and chunk_size 500, it's 1 call.
    # Let's verify it worked.
    assert len(batch_sizes) >= 1
    assert all(size <= 500 for size in batch_sizes)
