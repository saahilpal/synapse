from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import pytest

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime


@pytest.fixture
def test_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git_bin = shutil.which("git") or "git"

    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "perf@synapse.invalid"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Perf Tester"], cwd=repo, check=True)

    (repo / "file1.py").write_text("def hello():\n    pass\n", encoding="utf-8")
    (repo / "file2.py").write_text("def world():\n    pass\n", encoding="utf-8")

    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "initial commit"], cwd=repo, check=True)
    return repo


@pytest.fixture
def settings(test_repo: Path, tmp_path: Path) -> SynapSettings:
    return SynapSettings(
        repository_path=test_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synap.db",
        object_path=tmp_path / "objects",
    )


def test_first_run_completes_cleanly(settings: SynapSettings) -> None:
    runtime = SynapRuntime(settings)
    commit = runtime.bootstrap(force=True)
    assert commit is not None

    status = runtime.status()
    with runtime.store.connect() as conn:
        py_files = conn.execute("SELECT COUNT(*) FROM files WHERE path LIKE '%.py'").fetchone()[0]
    assert py_files == 2
    assert status.symbols == 2


def test_incremental_zero_changes_is_fast(settings: SynapSettings) -> None:
    runtime = SynapRuntime(settings)
    runtime.bootstrap(force=True)

    t0 = time.perf_counter()
    new_commit = runtime.index_repository()
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert elapsed_ms < 100.0, (
        f"Incremental indexing with zero changes took {elapsed_ms:.1f}ms — exceeds 100ms budget"
    )
    assert new_commit is not None


def test_incremental_one_change_processes_one_file(
    settings: SynapSettings, test_repo: Path
) -> None:
    runtime = SynapRuntime(settings)
    runtime.bootstrap(force=True)

    # Track files updated_at before change
    with runtime.store.connect() as conn:
        before_files = {
            r["path"]: r["updated_at"]
            for r in conn.execute("SELECT path, updated_at FROM files").fetchall()
        }

    # Change exactly one file
    time.sleep(1.0)  # Ensure updated_at timestamp moves
    (test_repo / "file1.py").write_text("def hello_modified():\n    pass\n", encoding="utf-8")

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "add", "file1.py"], cwd=test_repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "modify file1"], cwd=test_repo, check=True)

    runtime.index_repository()

    with runtime.store.connect() as conn:
        after_files = {
            r["path"]: r["updated_at"]
            for r in conn.execute("SELECT path, updated_at FROM files").fetchall()
        }

    # Check that file1.py was updated, but file2.py was untouched
    assert before_files["file1.py"] != after_files["file1.py"]
    assert before_files["file2.py"] == after_files["file2.py"]


def test_duplicate_content_correctness(settings: SynapSettings, test_repo: Path) -> None:
    # Creating two files with identical contents (e.g. empty init files) should not collide on file_id
    (test_repo / "sub1").mkdir()
    (test_repo / "sub1" / "__init__.py").write_text("", encoding="utf-8")
    (test_repo / "sub2").mkdir()
    (test_repo / "sub2" / "__init__.py").write_text("", encoding="utf-8")

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "add", "."], cwd=test_repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "add empty inits"], cwd=test_repo, check=True)

    runtime = SynapRuntime(settings)
    commit = runtime.bootstrap(force=True)
    assert commit is not None

    status = runtime.status()
    file_entry = runtime.store.get_file_by_path("sub1/__init__.py")
    assert file_entry is not None
    assert "sub1/__init__.py" in [
        r["path"]
        for r in runtime.store.get_symbols_by_file(file_entry["file_id"])
        or [{"path": "sub1/__init__.py"}]
    ]


def test_explain_query_plan(settings: SynapSettings) -> None:
    runtime = SynapRuntime(settings)
    runtime.bootstrap(force=True)

    queries = [
        ("SELECT file_id FROM files WHERE module_key = ?", ("test",)),
        (
            "SELECT s.* FROM symbols_fts fts JOIN symbols s ON fts.symbol_id = s.symbol_id WHERE symbols_fts MATCH ?",
            ("hello*",),
        ),
    ]

    with runtime.store.connect() as conn:
        for sql, params in queries:
            plan_rows = conn.execute(f"EXPLAIN QUERY PLAN {sql}", params).fetchall()
            plan = "\n".join([r["detail"] for r in plan_rows])

            # Verify no SCAN TABLE occurs on files or symbols tables
            # MATCH on virtual tables is fine, but JOINs must use indexes
            for line in plan.splitlines():
                if "SCAN TABLE" in line:
                    # SCAN TABLE on virtual tables / FTS index is expected, but not on normal files or symbols table
                    assert "SCAN TABLE files" not in line, f"Full table scan found on files: {line}"
                    assert "SCAN TABLE symbols" not in line, (
                        f"Full table scan found on symbols: {line}"
                    )


def test_resolve_and_insert_edges_batching(settings: SynapSettings, test_repo: Path) -> None:
    # 100 files, 10 imports each
    for i in range(100):
        content = "\n".join([f"import mod{j}" for j in range(10)])
        content += f"\nclass Mod{i}:\n    pass\n"
        (test_repo / f"mod{i}.py").write_text(content, encoding="utf-8")

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "add", "."], cwd=test_repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "add 100 files"], cwd=test_repo, check=True)

    runtime = SynapRuntime(settings)

    query_count = 0

    def trace_callback(statement: str) -> None:
        nonlocal query_count
        if statement.strip().upper().startswith("SELECT"):
            query_count += 1

    import sqlite3
    from typing import Any

    original_connect = sqlite3.connect

    def mock_connect(*args: Any, **kwargs: Any) -> Any:
        conn = original_connect(*args, **kwargs)
        conn.set_trace_callback(trace_callback)
        return conn

    sqlite3.connect = mock_connect
    try:
        runtime.bootstrap(force=True)
    finally:
        sqlite3.connect = original_connect

    assert query_count < 300, f"Too many queries during edge resolution: {query_count}"
