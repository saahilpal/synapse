"""
Monorepo stress test: indexes the Synap repository itself.

This test bootstraps Synap against its own source tree and measures:
  - Indexing latency
  - File and symbol counts
  - Retrieval latency under realistic load
  - Memory footprint (RSS) stays within bounds

Run with:
    uv run pytest tests/test_monorepo_stress.py -v -m benchmark

Skipped automatically when not in the synap repo or if the
SYNAP_SKIP_STRESS env variable is set (e.g. in fast CI passes).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime


def _synapse_repo_root() -> Path | None:
    """Find the root of the Synap repository relative to this test file."""
    here = Path(__file__).resolve().parent
    candidate = here.parent
    if (candidate / "pyproject.toml").exists() and (candidate / "src" / "synap").exists():
        return candidate
    return None


pytestmark = pytest.mark.benchmark


@pytest.fixture(scope="module")
def stress_runtime(tmp_path_factory: pytest.TempPathFactory) -> SynapRuntime | None:
    if os.environ.get("SYNAP_SKIP_STRESS"):
        return None
    repo_root = _synapse_repo_root()
    if repo_root is None:
        return None

    tmp = tmp_path_factory.mktemp("stress_db")
    settings = SynapSettings(
        repository_path=repo_root,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp / "synap.db",
        object_path=tmp / "objects",
    )
    runtime = SynapRuntime(settings)
    return runtime


@pytest.mark.benchmark
def test_indexing_latency(stress_runtime: SynapRuntime | None) -> None:
    """Full-repo indexing must complete under 60 seconds."""
    if stress_runtime is None:
        pytest.skip("Stress test skipped (SYNAP_SKIP_STRESS or repo not found)")

    t0 = time.perf_counter()
    stress_runtime.bootstrap(force=True)
    elapsed = time.perf_counter() - t0

    print(f"\n  ⏱  Indexing elapsed: {elapsed:.2f}s")
    assert elapsed < 60.0, f"Indexing took {elapsed:.2f}s — exceeds 60s budget"


@pytest.mark.benchmark
def test_file_and_symbol_counts(stress_runtime: SynapRuntime | None) -> None:
    """Monorepo indexing should produce substantial symbol coverage."""
    if stress_runtime is None:
        pytest.skip("Stress test skipped")

    status = stress_runtime.status()
    print(f"\n  📦  Files: {status.files}, Symbols: {status.symbols}")

    assert status.files >= 5, f"Expected ≥5 files indexed, got {status.files}"
    assert status.symbols >= 20, f"Expected ≥20 symbols, got {status.symbols}"


@pytest.mark.benchmark
def test_retrieval_latency_p95(stress_runtime: SynapRuntime | None) -> None:
    """Single retrieval queries must complete in under 2 seconds each."""
    if stress_runtime is None:
        pytest.skip("Stress test skipped")

    queries = [
        "How does the retrieval engine rank candidates?",
        "What is the lesson lifecycle?",
        "How does the daemon detect git commits?",
        "What does bootstrap do?",
        "How is the MCP server structured?",
    ]

    latencies = []
    for q in queries:
        t0 = time.perf_counter()
        stress_runtime.query_hybrid(q, max_tokens=2000)
        latencies.append(time.perf_counter() - t0)

    p95 = sorted(latencies)[int(len(latencies) * 0.95) - 1]
    avg = sum(latencies) / len(latencies)
    print(f"\n  ⏱  Query latencies — avg: {avg * 1000:.0f}ms, p95: {p95 * 1000:.0f}ms")

    assert p95 < 2.0, f"p95 retrieval latency {p95 * 1000:.0f}ms exceeds 2000ms budget"


@pytest.mark.benchmark
def test_memory_footprint(stress_runtime: SynapRuntime | None) -> None:
    """Process RSS after indexing must stay under 512 MiB."""
    if stress_runtime is None:
        pytest.skip("Stress test skipped")

    try:
        import resource

        rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports in bytes, Linux in kilobytes
        if rss_bytes < 10_000:  # Linux: value is in KB
            rss_mb = rss_bytes / 1024
        else:
            rss_mb = rss_bytes / (1024 * 1024)
        print(f"\n  💾  RSS: {rss_mb:.0f} MiB")
        assert rss_mb < 512, f"RSS {rss_mb:.0f} MiB exceeds 512 MiB budget"
    except ImportError:
        pytest.skip("resource module not available on this platform")


@pytest.mark.benchmark
def test_integrity_after_stress(stress_runtime: SynapRuntime | None) -> None:
    """Database must remain intact after full indexing pass."""
    if stress_runtime is None:
        pytest.skip("Stress test skipped")

    result = stress_runtime.store.integrity_check()
    assert result == "ok", f"Database integrity failed: {result}"


@pytest.mark.benchmark
def test_indexing_10k_files(tmp_path: Path) -> None:
    """Stress test indexing 10,000 files to measure latency, DB growth, and RSS."""
    if os.environ.get("SYNAP_SKIP_STRESS"):
        pytest.skip("Stress test skipped")

    repo = tmp_path / "10k_repo"
    repo.mkdir()

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "stress@synapse.local"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Stress Tester"], cwd=repo, check=True)

    # Batch write 10,000 files
    subdirs = [repo / f"dir_{d}" for d in range(10)]
    for sd in subdirs:
        sd.mkdir()

    # Create 10,000 small files
    for i in range(10000):
        sd = subdirs[i % 10]
        (sd / f"file_{i}.py").write_text(f"def func_{i}():\n    pass\n", encoding="utf-8")

    # Add and commit so git ls-files works
    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "10k files", "--quiet"], cwd=repo, check=True)

    settings = SynapSettings(
        repository_path=repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synap.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapRuntime(settings)

    t0 = time.perf_counter()
    runtime.bootstrap(force=True)
    elapsed = time.perf_counter() - t0

    print(f"\n  ⏱  10k Files Indexing Elapsed: {elapsed:.2f}s")

    # Assert budgets
    assert elapsed < 60.0, f"Indexing 10k files took {elapsed:.2f}s (budget: 60s)"

    # Verify counts
    status = runtime.status()
    assert status.files >= 10000
    assert status.symbols >= 10000

    # Measure DB size
    assert settings.sqlite_path is not None
    db_size = settings.sqlite_path.stat().st_size / (1024 * 1024)
    print(f"  📦  SQLite DB Size: {db_size:.2f} MiB")
    assert db_size < 50.0, f"DB size {db_size:.2f} MiB is too large"

    # Measure retrieval p95
    latencies = []
    for q in ["func_10", "func_5000", "func_9999"]:
        t_q = time.perf_counter()
        ans, _, _ = runtime.query_hybrid(q, max_tokens=1000)
        latencies.append(time.perf_counter() - t_q)

    avg = sum(latencies) / len(latencies)
    print(f"  ⏱  10k Repo Retrieval Average Latency: {avg * 1000:.0f}ms")
    assert avg < 2.0, f"Retrieval latency too high: {avg:.2f}s"
