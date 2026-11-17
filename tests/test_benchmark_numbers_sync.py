from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NUMBERS_PATH = REPO_ROOT / "bench" / "numbers.json"
README_PATH = REPO_ROOT / "README.md"
SKILL_PATH = REPO_ROOT / "src" / "synap_git" / "resources" / "SKILL.md"


def test_numbers_json_exists_and_valid() -> None:
    """Verify that bench/numbers.json exists and is valid JSON."""
    assert NUMBERS_PATH.exists(), f"Benchmark results file not found at {NUMBERS_PATH}"
    data = json.loads(NUMBERS_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "numbers.json must be a JSON object"


def test_numbers_json_schema() -> None:
    """Verify that bench/numbers.json adheres to the authoritative benchmark schema."""
    data = json.loads(NUMBERS_PATH.read_text(encoding="utf-8"))

    # Required top-level fields
    required_keys = [
        "version",
        "timestamp",
        "tokenizer",
        "repositories",
        "total_queries",
        "metrics_overall",
        "budget_evaluation",
        "by_category",
        "by_repo",
        "results",
    ]
    for key in required_keys:
        assert key in data, f"Missing required key in numbers.json: {key}"

    assert data["tokenizer"] == "o200k_base"
    assert isinstance(data["repositories"], list)
    assert len(data["repositories"]) >= 1
    assert isinstance(data["total_queries"], int)
    assert data["total_queries"] > 0

    # Overall metrics schema
    m = data["metrics_overall"]
    assert 0.0 <= m["recall_at_5"] <= 1.0, f"recall_at_5 out of bounds: {m['recall_at_5']}"
    assert 0.0 <= m["recall_at_10"] <= 1.0, f"recall_at_10 out of bounds: {m['recall_at_10']}"
    assert 0.0 <= m["mrr"] <= 1.0, f"mrr out of bounds: {m['mrr']}"
    assert 0.0 <= m["ndcg_at_10"] <= 1.0, f"ndcg_at_10 out of bounds: {m['ndcg_at_10']}"
    assert m["latency_p50_ms"] >= 0.0, f"latency_p50_ms negative: {m['latency_p50_ms']}"
    assert m["latency_p95_ms"] >= m["latency_p50_ms"], "latency_p95_ms should be >= p50"

    # Budget evaluation schema
    be = data["budget_evaluation"]
    for budget_key in ["500", "1500", "4000"]:
        assert budget_key in be, f"Missing budget level {budget_key} in budget_evaluation"
        b_entry = be[budget_key]
        assert "synapse" in b_entry
        assert "naive" in b_entry
        assert "token_savings_pct" in b_entry
        assert 0.0 <= b_entry["synapse"]["recall"] <= 1.0
        assert 0.0 <= b_entry["naive"]["recall"] <= 1.0

    # Category schema
    bc = data["by_category"]
    assert isinstance(bc, dict)
    assert len(bc) > 0
    for cat_name, cat_data in bc.items():
        assert "count" in cat_data
        assert 0.0 <= cat_data["recall_at_5"] <= 1.0
        assert 0.0 <= cat_data["mrr"] <= 1.0
        assert cat_data["latency_p50_ms"] >= 0.0


def test_documentation_sync_with_benchmark_numbers() -> None:
    """Verify that any benchmark numbers mentioned in README.md or SKILL.md match numbers.json."""
    data = json.loads(NUMBERS_PATH.read_text(encoding="utf-8"))
    overall = data["metrics_overall"]

    doc_files = [README_PATH, SKILL_PATH]
    for doc in doc_files:
        if not doc.exists():
            continue
        content = doc.read_text(encoding="utf-8")

        # Check Recall@5 citations: e.g. "Recall@5: 42.5%" or "Recall@5 of 42%"
        r5_matches = re.findall(r"Recall@5(?::|\s+of)?\s*(\d+(?:\.\d+)?)%?", content, re.IGNORECASE)
        for m in r5_matches:
            val = float(m)
            # If formatted as percentage (e.g. 42.5), convert to ratio
            if val > 1.0:
                val /= 100.0
            assert abs(val - overall["recall_at_5"]) <= 0.05, (
                f"Recall@5 in {doc.name} ({val}) does not match numbers.json ({overall['recall_at_5']})"
            )

        # Check MRR citations: e.g. "MRR: 0.65" or "MRR of 0.65"
        mrr_matches = re.findall(r"MRR(?::|\s+of)?\s*(\d+(?:\.\d+)?)", content)
        for m in mrr_matches:
            val = float(m)
            assert abs(val - overall["mrr"]) <= 0.05, (
                f"MRR in {doc.name} ({val}) does not match numbers.json ({overall['mrr']})"
            )

        # Check nDCG@10 citations
        ndcg_matches = re.findall(r"nDCG(?:@10)?(?::|\s+of)?\s*(\d+(?:\.\d+)?)", content)
        for m in ndcg_matches:
            val = float(m)
            assert abs(val - overall["ndcg_at_10"]) <= 0.05, (
                f"nDCG@10 in {doc.name} ({val}) does not match numbers.json ({overall['ndcg_at_10']})"
            )


def test_cli_bench_quick_execution() -> None:
    """Test that synap bench runs and generates valid JSON output programmatically."""
    from synap_git.cli.bench import run_benchmark

    res = run_benchmark(
        repo_paths=[REPO_ROOT],
        commits_per_repo=3,
        budgets=[500, 1500],
        quick=True,
        quiet=True,
    )

    assert "metrics_overall" in res
    assert "budget_evaluation" in res
    assert res["total_queries"] > 0
