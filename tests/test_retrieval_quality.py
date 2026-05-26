from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from synapse.config import RuntimeProfile, SynapseSettings
from synapse.indexer.engine import SynapseRuntime


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init"], cwd=repo, check=True)
    subprocess.run(
        [git_bin, "config", "user.email", "retrieval@synapse.local"], cwd=repo, check=True
    )
    subprocess.run([git_bin, "config", "user.name", "Retrieval Tester"], cwd=repo, check=True)

    # Base python files
    (repo / "main.py").write_text("def hello(): pass\n", encoding="utf-8")
    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "initial commit"], cwd=repo, check=True)

    return repo


def test_duplicate_symbol_indexing_and_ranking(temp_repo: Path, tmp_path: Path) -> None:
    """Duplicate symbol names in different files must be indexed independently and ranked correctly."""
    # Write two files with same function name
    (temp_repo / "foo.py").write_text("def process_data():\n    return 1\n", encoding="utf-8")
    (temp_repo / "bar.py").write_text("def process_data():\n    return 2\n", encoding="utf-8")

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "add", "."], cwd=temp_repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "add duplicate symbols"], cwd=temp_repo, check=True)

    settings = SynapseSettings(
        repository_path=temp_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synapse.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    # Query for process_data
    ans, sources, trace = runtime.query_hybrid("process_data", max_tokens=1000)

    # We should have both symbols in the database
    with runtime.store.connect() as conn:
        rows = conn.execute("SELECT * FROM symbols WHERE name = 'process_data'").fetchall()
        assert len(rows) == 2

    # Both symbols should be identified as grounding sources in retrieval
    paths = [s["source_path"] for s in sources]
    assert "foo.py" in paths
    assert "bar.py" in paths


def test_circular_imports_traversal(temp_repo: Path, tmp_path: Path) -> None:
    """Circular imports between files must not cause infinite loops during structural traversal."""
    # File A imports B; File B imports A
    (temp_repo / "module_a.py").write_text(
        "import module_b\ndef func_a(): pass\n", encoding="utf-8"
    )
    (temp_repo / "module_b.py").write_text(
        "import module_a\ndef func_b(): pass\n", encoding="utf-8"
    )

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "add", "."], cwd=temp_repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "circular imports"], cwd=temp_repo, check=True)

    settings = SynapseSettings(
        repository_path=temp_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synapse.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    # Query for func_a. Neighborhood traversal will traverse to module_b via import, then back to module_a.
    # Since depth is strictly limited, it must complete successfully.
    ans, sources, trace = runtime.query_hybrid("func_a", max_tokens=1000)
    assert len(sources) > 0


def test_unicode_and_malformed_files(temp_repo: Path, tmp_path: Path) -> None:
    """Verify non-ASCII filenames and malformed text files are indexed safely or skipped."""
    # Unicode file name
    (temp_repo / "unicode_你好.py").write_text("def test_unicode(): pass\n", encoding="utf-8")

    # Malformed file (invalid UTF-8 bytes)
    malformed_path = temp_repo / "malformed.py"
    with malformed_path.open("wb") as f:
        f.write(b"def bad_utf8(): pass\n# \xff\xfe\xfd invalid bytes")

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "add", "."], cwd=temp_repo, check=True)
    subprocess.run(
        [git_bin, "commit", "-m", "unicode and malformed files"], cwd=temp_repo, check=True
    )

    settings = SynapseSettings(
        repository_path=temp_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synapse.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    # Unicode file should be indexed successfully
    status = runtime.status()
    with runtime.store.connect() as conn:
        unicode_exists = conn.execute(
            "SELECT count(*) FROM files WHERE path = 'unicode_你好.py'"
        ).fetchone()[0]
        assert unicode_exists == 1

        # Malformed invalid UTF-8 bytes file: if scanner skips it or reads with errors='ignore', it shouldn't crash
        malformed_exists = conn.execute(
            "SELECT count(*) FROM files WHERE path = 'malformed.py'"
        ).fetchone()[0]
        # Should be indexed because errors="ignore" is used or skipped safely if binary
        # Let's verify it didn't crash indexing
        assert status.files >= 3


def test_retrieval_determinism(temp_repo: Path, tmp_path: Path) -> None:
    """Verify that retrieval results are completely deterministic across identical queries."""
    (temp_repo / "calc.py").write_text(
        "def add(a, b): return a + b\ndef sub(a, b): return a - b\n", encoding="utf-8"
    )

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "add", "."], cwd=temp_repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "add calc module"], cwd=temp_repo, check=True)

    settings = SynapseSettings(
        repository_path=temp_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synapse.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    # Query 5 times
    outputs = []
    for _ in range(5):
        ans, sources, trace = runtime.query_hybrid("add", max_tokens=1000)
        outputs.append((sources, trace["elements"]))

    # All outputs must be identical in structure and ordering
    first_sources, first_elements = outputs[0]
    for other_sources, other_elements in outputs[1:]:
        assert len(first_sources) == len(other_sources)
        for s1, s2 in zip(first_sources, other_sources, strict=False):
            assert s1["symbol_id"] == s2["symbol_id"]
            assert s1["name"] == s2["name"]

        assert len(first_elements) == len(other_elements)
        for e1, e2 in zip(first_elements, other_elements, strict=False):
            assert e1["stable_id"] == e2["stable_id"]
            assert e1["score"] == e2["score"]
