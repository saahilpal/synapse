#!/usr/bin/env python3
"""
Baseline Grounding and Retrieval Benchmark Runner for Synapse (synap-git).

Evaluates baseline retrieval quality, latency, and token efficiency
across 6 realistic developer query categories:
  1. Symbol lookup
  2. Navigation ("Where is X")
  3. Architecture ("How does X work")
  4. Stack traces / Error debugging
  5. Past decisions & Memory
  6. Recent changes & Git conventions
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime


@dataclass
class QueryResult:
    id: str
    category: str
    query: str
    latency_ms: float
    tokens_used: int
    retrieved_count: int
    top_sources: list[dict[str, Any]]
    hit_at_1: bool
    hit_at_3: bool
    hit_at_5: bool
    symbol_hit_at_1: bool
    symbol_hit_at_3: bool
    symbol_hit_at_5: bool
    file_hit_at_1: bool
    file_hit_at_3: bool
    file_hit_at_5: bool
    reciprocal_rank: float
    symbol_reciprocal_rank: float
    file_reciprocal_rank: float
    matched_target: str | None


@dataclass
class LatencyMetrics:
    min: float
    p50: float
    p90: float
    p95: float
    max: float
    mean: float


@dataclass
class TokenMetrics:
    min: int
    avg: float
    max: int


@dataclass
class OverallMetrics:
    total_queries: int
    hit_rate_at_1: float
    hit_rate_at_3: float
    hit_rate_at_5: float
    mrr: float
    symbol_hit_rate_at_1: float
    symbol_hit_rate_at_3: float
    symbol_hit_rate_at_5: float
    symbol_mrr: float
    file_hit_rate_at_1: float
    file_hit_rate_at_3: float
    file_hit_rate_at_5: float
    file_mrr: float
    latency_ms: LatencyMetrics
    token_usage: TokenMetrics


@dataclass
class CategoryMetric:
    count: int
    hit_rate_at_1: float
    hit_rate_at_3: float
    hit_rate_at_5: float
    mrr: float
    symbol_hit_rate_at_3: float
    file_hit_rate_at_3: float
    latency_p50_ms: float
    latency_p95_ms: float
    avg_tokens: float


def percentile(data: list[float], p: float) -> float:
    """Calculate percentile value from sorted or unsorted list."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return d0 + d1


def evaluate_query(
    runtime: SynapRuntime,
    item: dict[str, Any],
    max_tokens: int = 1000,
) -> QueryResult:
    query = str(item["query"])
    expected_symbols = set(item.get("expected_symbols", []))
    expected_paths = set(item.get("expected_paths", []))

    t0 = time.perf_counter()
    answer, sources, trace = runtime.query_hybrid(
        query, max_tokens=max_tokens, synthesize_answer=False
    )
    t1 = time.perf_counter()
    latency_ms = (t1 - t0) * 1000.0

    tokens_used = int(trace.get("tokens_used", 0))

    # Rank retrieved sources
    first_hit_rank: int | None = None
    first_sym_hit_rank: int | None = None
    first_file_hit_rank: int | None = None
    matched_target: str | None = None

    for rank_idx, s in enumerate(sources, start=1):
        s_name = str(s.get("name", ""))
        s_path = str(s.get("source_path", s.get("path", "")))

        is_sym_match = bool(expected_symbols and s_name in expected_symbols)
        is_file_match = bool(
            expected_paths
            and any(
                exp == s_path
                or s_path.endswith("/" + exp)
                or exp.endswith("/" + s_path)
                or (exp in s_path and len(exp) > 3)
                for exp in expected_paths
            )
        )

        if is_sym_match and first_sym_hit_rank is None:
            first_sym_hit_rank = rank_idx
        if is_file_match and first_file_hit_rank is None:
            first_file_hit_rank = rank_idx

        if (is_sym_match or is_file_match) and first_hit_rank is None:
            first_hit_rank = rank_idx
            matched_target = f"symbol:{s_name}" if is_sym_match else f"path:{s_path}"

    hit_at_1 = first_hit_rank is not None and first_hit_rank <= 1
    hit_at_3 = first_hit_rank is not None and first_hit_rank <= 3
    hit_at_5 = first_hit_rank is not None and first_hit_rank <= 5

    sym_hit_at_1 = first_sym_hit_rank is not None and first_sym_hit_rank <= 1
    sym_hit_at_3 = first_sym_hit_rank is not None and first_sym_hit_rank <= 3
    sym_hit_at_5 = first_sym_hit_rank is not None and first_sym_hit_rank <= 5

    file_hit_at_1 = first_file_hit_rank is not None and first_file_hit_rank <= 1
    file_hit_at_3 = first_file_hit_rank is not None and first_file_hit_rank <= 3
    file_hit_at_5 = first_file_hit_rank is not None and first_file_hit_rank <= 5

    rr = 1.0 / first_hit_rank if first_hit_rank else 0.0
    sym_rr = 1.0 / first_sym_hit_rank if first_sym_hit_rank else 0.0
    file_rr = 1.0 / first_file_hit_rank if first_file_hit_rank else 0.0

    top_sources = [
        {
            "rank": idx + 1,
            "name": s.get("name", ""),
            "path": s.get("source_path", s.get("path", "")),
            "kind": s.get("kind", ""),
            "reason": s.get("reason", ""),
        }
        for idx, s in enumerate(sources[:5])
    ]

    return QueryResult(
        id=str(item["id"]),
        category=str(item["category"]),
        query=query,
        latency_ms=latency_ms,
        tokens_used=tokens_used,
        retrieved_count=len(sources),
        top_sources=top_sources,
        hit_at_1=hit_at_1,
        hit_at_3=hit_at_3,
        hit_at_5=hit_at_5,
        symbol_hit_at_1=sym_hit_at_1,
        symbol_hit_at_3=sym_hit_at_3,
        symbol_hit_at_5=sym_hit_at_5,
        file_hit_at_1=file_hit_at_1,
        file_hit_at_3=file_hit_at_3,
        file_hit_at_5=file_hit_at_5,
        reciprocal_rank=rr,
        symbol_reciprocal_rank=sym_rr,
        file_reciprocal_rank=file_rr,
        matched_target=matched_target,
    )


def run_benchmark(
    repo_path: Path,
    dataset_path: Path,
    output_path: Path,
    max_tokens: int = 1000,
    warmup: bool = True,
) -> dict[str, Any]:
    print("=== Synapse Baseline Retrieval Benchmark ===")
    print(f"Repository: {repo_path.resolve()}")
    print(f"Dataset:    {dataset_path.resolve()}")
    print(f"Max Tokens: {max_tokens}")

    # Load dataset
    with dataset_path.open("r", encoding="utf-8") as f:
        dataset: list[dict[str, Any]] = json.load(f)

    # Initialize Runtime
    settings = SynapSettings(
        repository_path=repo_path,
        profile=RuntimeProfile.TEST,
    )
    runtime = SynapRuntime(settings)
    runtime.initialize_storage()

    # Optional warmup
    if warmup:
        print("Warming up retrieval caches...")
        runtime.query_hybrid("warmup query", max_tokens=200, synthesize_answer=False)

    print(f"Running evaluation on {len(dataset)} queries across categories...")
    results: list[QueryResult] = []

    for i, item in enumerate(dataset, start=1):
        res = evaluate_query(runtime, item, max_tokens=max_tokens)
        results.append(res)
        status = "HIT" if res.hit_at_3 else "MISS"
        match_str = f"({res.matched_target})" if res.matched_target else ""
        print(
            f"[{i:02d}/{len(dataset):02d}] [{status:4s}] {item['category']:16s} | {item['query'][:40]:40s} | {res.latency_ms:6.2f}ms | {res.tokens_used:4d} tok {match_str}"
        )

    # Compute overall metrics
    n = len(results)
    latencies = [r.latency_ms for r in results]
    tokens = [r.tokens_used for r in results]

    overall_metrics = OverallMetrics(
        total_queries=n,
        hit_rate_at_1=sum(1 for r in results if r.hit_at_1) / n,
        hit_rate_at_3=sum(1 for r in results if r.hit_at_3) / n,
        hit_rate_at_5=sum(1 for r in results if r.hit_at_5) / n,
        mrr=sum(r.reciprocal_rank for r in results) / n,
        symbol_hit_rate_at_1=sum(1 for r in results if r.symbol_hit_at_1) / n,
        symbol_hit_rate_at_3=sum(1 for r in results if r.symbol_hit_at_3) / n,
        symbol_hit_rate_at_5=sum(1 for r in results if r.symbol_hit_at_5) / n,
        symbol_mrr=sum(r.symbol_reciprocal_rank for r in results) / n,
        file_hit_rate_at_1=sum(1 for r in results if r.file_hit_at_1) / n,
        file_hit_rate_at_3=sum(1 for r in results if r.file_hit_at_3) / n,
        file_hit_rate_at_5=sum(1 for r in results if r.file_hit_at_5) / n,
        file_mrr=sum(r.file_reciprocal_rank for r in results) / n,
        latency_ms=LatencyMetrics(
            min=round(min(latencies), 2),
            p50=round(percentile(latencies, 50), 2),
            p90=round(percentile(latencies, 90), 2),
            p95=round(percentile(latencies, 95), 2),
            max=round(max(latencies), 2),
            mean=round(sum(latencies) / n, 2),
        ),
        token_usage=TokenMetrics(
            min=min(tokens),
            avg=round(sum(tokens) / n, 2),
            max=max(tokens),
        ),
    )

    # Compute per-category metrics
    categories = sorted({r.category for r in results})
    category_metrics: dict[str, CategoryMetric] = {}

    for cat in categories:
        cat_results = [r for r in results if r.category == cat]
        cn = len(cat_results)
        cat_latencies = [r.latency_ms for r in cat_results]
        cat_tokens = [r.tokens_used for r in cat_results]

        category_metrics[cat] = CategoryMetric(
            count=cn,
            hit_rate_at_1=sum(1 for r in cat_results if r.hit_at_1) / cn,
            hit_rate_at_3=sum(1 for r in cat_results if r.hit_at_3) / cn,
            hit_rate_at_5=sum(1 for r in cat_results if r.hit_at_5) / cn,
            mrr=sum(r.reciprocal_rank for r in cat_results) / cn,
            symbol_hit_rate_at_3=sum(1 for r in cat_results if r.symbol_hit_at_3) / cn,
            file_hit_rate_at_3=sum(1 for r in cat_results if r.file_hit_at_3) / cn,
            latency_p50_ms=round(percentile(cat_latencies, 50), 2),
            latency_p95_ms=round(percentile(cat_latencies, 95), 2),
            avg_tokens=round(sum(cat_tokens) / cn, 2),
        )

    # Assemble report
    report: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": {
            "recall_at_1": round(overall_metrics.hit_rate_at_1, 4),
            "recall_at_3": round(overall_metrics.hit_rate_at_3, 4),
            "recall_at_5": round(overall_metrics.hit_rate_at_5, 4),
            "mrr": round(overall_metrics.mrr, 4),
            "latency_p50_ms": overall_metrics.latency_ms.p50,
            "latency_p95_ms": overall_metrics.latency_ms.p95,
            "avg_tokens": overall_metrics.token_usage.avg,
        },
        "overall_metrics": asdict(overall_metrics),
        "category_metrics": {k: asdict(v) for k, v in category_metrics.items()},
        "queries": [asdict(r) for r in results],
    }

    # Save to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\nSaved benchmark results to {output_path.resolve()}")

    # Print summary table
    print("\n" + "=" * 78)
    print("                      BASELINE BENCHMARK SUMMARY")
    print("=" * 78)
    print(f"Total Queries:        {n}")
    print(f"Recall@1 (Hit@1):     {overall_metrics.hit_rate_at_1 * 100:6.2f}%")
    print(f"Recall@3 (Hit@3):     {overall_metrics.hit_rate_at_3 * 100:6.2f}%")
    print(f"Recall@5 (Hit@5):     {overall_metrics.hit_rate_at_5 * 100:6.2f}%")
    print(f"MRR:                  {overall_metrics.mrr:6.4f}")
    print(f"Symbol Hit@3:         {overall_metrics.symbol_hit_rate_at_3 * 100:6.2f}%")
    print(f"File Hit@3:           {overall_metrics.file_hit_rate_at_3 * 100:6.2f}%")
    print(f"Latency (p50):        {overall_metrics.latency_ms.p50:6.2f} ms")
    print(f"Latency (p95):        {overall_metrics.latency_ms.p95:6.2f} ms")
    print(f"Average Tokens:       {overall_metrics.token_usage.avg:6.2f}")
    print("-" * 78)
    print(
        f"{'Category':20s} | {'Count':5s} | {'Hit@1':6s} | {'Hit@3':6s} | {'MRR':6s} | {'p50 (ms)':8s}"
    )
    print("-" * 78)
    for cat, m in category_metrics.items():
        print(
            f"{cat:20s} | {m.count:5d} | {m.hit_rate_at_1 * 100:5.1f}% | {m.hit_rate_at_3 * 100:5.1f}% | {m.mrr:6.4f} | {m.latency_p50_ms:8.2f}"
        )
    print("=" * 78 + "\n")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Synapse Baseline Retrieval Benchmark Runner")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(),
        help="Repository root path (default: current directory)",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/benchmark_dataset.json"),
        help="Benchmark evaluation dataset JSON path",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/baseline_results.json"),
        help="Output JSON file for benchmark results",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1000,
        help="Max tokens per retrieval query",
    )
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="Skip cache warmup query",
    )

    args = parser.parse_args()
    run_benchmark(
        repo_path=args.repo,
        dataset_path=args.dataset,
        output_path=args.output,
        max_tokens=args.max_tokens,
        warmup=not args.no_warmup,
    )


if __name__ == "__main__":
    main()
