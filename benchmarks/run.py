import sys
import time
from pathlib import Path

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime


def run_benchmark(repo_path: str) -> None:
    path = Path(repo_path)
    if not path.exists():
        print(f"Path {repo_path} does not exist.")
        return

    print(f"Benchmarking Synap on {path.name}...")

    settings = SynapSettings(
        repository_path=path,
        profile=RuntimeProfile.DEV,
    )
    runtime = SynapRuntime(settings)

    # 1. Indexing Benchmark
    start = time.perf_counter()
    runtime.bootstrap(force=True)
    indexing_time = time.perf_counter() - start

    status = runtime.status()
    print(f"Indexing complete: {status.symbols} symbols found in {indexing_time:.2f}s")

    # 2. Retrieval Benchmark
    queries = [
        "How is authentication handled?",
        "Explain the main entry point",
        "Find all API handlers",
    ]

    print("\nRunning Retrieval Benchmarks...")
    for query in queries:
        start = time.perf_counter()
        _, _, trace = runtime.query_hybrid(query)
        latency = time.perf_counter() - start
        print(
            f"Query: '{query}' | Latency: {latency * 1000:.2f}ms | Tokens: {trace['tokens_used']}"
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python benchmarks/run.py <repo_path>")
    else:
        run_benchmark(sys.argv[1])
