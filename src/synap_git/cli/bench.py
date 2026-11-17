from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import structlog
import tiktoken
import typer
from rich.console import Console
from rich.table import Table

from synap_git.config import SynapSettings
from synap_git.indexer.engine import SynapRuntime

logger = structlog.get_logger()
console = Console()

STOP_WORDS = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "aren't",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can't",
    "cannot",
    "could",
    "couldn't",
    "did",
    "didn't",
    "do",
    "does",
    "doesn't",
    "doing",
    "don't",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "hadn't",
    "has",
    "hasn't",
    "have",
    "haven't",
    "having",
    "he",
    "he'd",
    "he'll",
    "he's",
    "her",
    "here",
    "here's",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "how's",
    "i",
    "i'd",
    "i'll",
    "i'm",
    "i've",
    "if",
    "in",
    "into",
    "is",
    "isn't",
    "it",
    "it's",
    "its",
    "itself",
    "let's",
    "me",
    "more",
    "most",
    "mustn't",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "ought",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "shan't",
    "she",
    "she'd",
    "she'll",
    "she's",
    "should",
    "shouldn't",
    "so",
    "some",
    "such",
    "than",
    "that",
    "that's",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "there's",
    "these",
    "they",
    "they'd",
    "they'll",
    "they're",
    "they've",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "wasn't",
    "we",
    "we'd",
    "we'll",
    "we're",
    "we've",
    "were",
    "weren't",
    "what",
    "what's",
    "when",
    "when's",
    "where",
    "where's",
    "which",
    "while",
    "who",
    "who's",
    "whom",
    "why",
    "why's",
    "with",
    "won't",
    "would",
    "wouldn't",
    "you",
    "you'd",
    "you'll",
    "you're",
    "you've",
    "your",
    "yours",
    "yourself",
    "yourselves",
}


@dataclass
class BenchmarkQuery:
    query_id: str
    repo: str
    category: str
    query: str
    ground_truth_files: list[str]
    commit_hash: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BudgetResult:
    budget: int
    synapse_tokens: int
    synapse_recall: float
    synapse_files: list[str]
    naive_tokens: int
    naive_recall: float
    naive_files: list[str]
    token_savings_pct: float


@dataclass
class QueryEvaluationResult:
    query_id: str
    repo: str
    category: str
    query: str
    ground_truth_files: list[str]
    synapse_retrieved_files: list[str]
    recall_at_5: float
    recall_at_10: float
    mrr: float
    ndcg_at_10: float
    latency_ms: float
    budget_results: dict[str, BudgetResult]


def extract_keywords(query: str) -> list[str]:
    """Extract alphanumeric keywords of length >= 3 excluding stop words."""
    tokens = re.findall(r"[a-zA-Z0-9_\-]+", query.lower())
    filtered = [t for t in tokens if len(t) >= 3 and t not in STOP_WORDS]
    if not filtered:
        filtered = [t for t in tokens if len(t) >= 2]
    return filtered


def run_naive_agent(
    repo_path: Path,
    query: str,
    budget: int,
    enc: tiktoken.Encoding,
) -> tuple[int, list[str]]:
    """Simulate a naive agent using ripgrep for query keywords, reading whole files up to token budget."""
    keywords = extract_keywords(query)
    if not keywords:
        return 0, []

    rg_bin = shutil.which("rg")
    file_hit_counts: dict[str, int] = {}

    if rg_bin:
        for kw in keywords[:6]:  # search top keywords
            cmd = [
                rg_bin,
                "-l",
                "-i",
                "--max-count=1",
                "--glob=!.git/**",
                "--glob=!.synap/**",
                "--glob=!node_modules/**",
                "--glob=!__pycache__/**",
                "--glob=!.venv/**",
                "--glob=!.mypy_cache/**",
                "--glob=!.pytest_cache/**",
                kw,
                str(repo_path),
            ]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if proc.returncode == 0:
                    for line in proc.stdout.splitlines():
                        p_str = line.strip()
                        if p_str:
                            rel_p = str(Path(p_str).relative_to(repo_path))
                            file_hit_counts[rel_p] = file_hit_counts.get(rel_p, 0) + 1
            except Exception as e:
                logger.debug("naive_agent_rg_error", error=str(e), keyword=kw)
    else:
        # Fallback to python search if ripgrep is unavailable
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [
                d
                for d in dirs
                if d
                not in (
                    ".git",
                    ".synap",
                    "node_modules",
                    "__pycache__",
                    ".venv",
                    ".mypy_cache",
                    ".pytest_cache",
                )
            ]
            for file in files:
                if file.startswith("."):
                    continue
                full_p = Path(root) / file
                try:
                    text = full_p.read_text(encoding="utf-8", errors="ignore").lower()
                    rel_p = str(full_p.relative_to(repo_path))
                    for kw in keywords[:6]:
                        if kw in text:
                            file_hit_counts[rel_p] = file_hit_counts.get(rel_p, 0) + 1
                except Exception as e:
                    logger.debug("naive_agent_read_error", file=str(full_p), error=str(e))
                    continue

    sorted_files = sorted(file_hit_counts.items(), key=lambda x: x[1], reverse=True)

    packed_files: list[str] = []
    total_tokens = 0

    for rel_path, _ in sorted_files:
        full_path = repo_path / rel_path
        if not full_path.is_file():
            continue
        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.debug("naive_agent_read_error", file=str(full_path), error=str(e))
            continue

        file_tokens = len(enc.encode(content))
        if total_tokens + file_tokens <= budget:
            packed_files.append(rel_path)
            total_tokens += file_tokens
        else:
            remaining = budget - total_tokens
            if remaining >= 30:
                packed_files.append(rel_path)
                total_tokens += remaining
            break

    return total_tokens, packed_files


def extract_files_from_synapse_output(
    grounding_sources: list[dict[str, Any]],
    answer_content: str,
    trace: dict[str, Any] | None = None,
) -> list[str]:
    """Extract and deduplicate relative file paths from Synapse retrieval results."""
    files: list[str] = []

    for s in grounding_sources:
        p = s.get("source_path") or s.get("path")
        if p and isinstance(p, str) and p not in files:
            files.append(p)

    # Also parse Markdown headers in context: "### File: <path>"
    matches = re.findall(r"### File: ([^\n]+)", answer_content)
    for m in matches:
        cleaned = m.strip()
        if cleaned and cleaned not in files:
            files.append(cleaned)

    matches_hdr = re.findall(r"# File: ([^\s|]+)", answer_content)
    for m in matches_hdr:
        cleaned = m.strip()
        if cleaned and cleaned not in files:
            files.append(cleaned)

    # Also include files from trace elements
    if trace and "elements" in trace:
        for elem in trace["elements"]:
            if isinstance(elem, dict):
                ep = elem.get("path")
                if ep and isinstance(ep, str) and ep not in files:
                    files.append(ep)

    return files


def compute_metrics(
    retrieved_files: list[str],
    ground_truth_files: list[str],
) -> tuple[float, float, float, float]:
    """Compute Recall@5, Recall@10, MRR, and nDCG@10."""
    gt_set = set(ground_truth_files)
    if not gt_set:
        return 1.0, 1.0, 1.0, 1.0

    # Recall@5
    retrieved_5 = set(retrieved_files[:5])
    recall_5 = len(retrieved_5 & gt_set) / len(gt_set)

    # Recall@10
    retrieved_10 = set(retrieved_files[:10])
    recall_10 = len(retrieved_10 & gt_set) / len(gt_set)

    # MRR (Mean Reciprocal Rank)
    mrr = 0.0
    for idx, f in enumerate(retrieved_files, start=1):
        if f in gt_set:
            mrr = 1.0 / idx
            break

    # nDCG@10
    dcg = 0.0
    for idx, f in enumerate(retrieved_files[:10], start=1):
        rel = 1.0 if f in gt_set else 0.0
        dcg += rel / math.log2(idx + 1)

    idcg = 0.0
    for idx in range(1, min(10, len(gt_set)) + 1):
        idcg += 1.0 / math.log2(idx + 1)

    ndcg = (dcg / idcg) if idcg > 0 else 0.0

    return recall_5, recall_10, mrr, ndcg


def extract_git_queries(repo_path: Path, max_commits: int = 15) -> list[BenchmarkQuery]:
    """Extract benchmark queries from real Git commit history."""
    queries: list[BenchmarkQuery] = []
    repo_name = repo_path.name

    git_bin = shutil.which("git") or "git"
    cmd = [
        git_bin,
        "-C",
        str(repo_path),
        "log",
        f"-n{max_commits}",
        "--pretty=format:COMMIT_MARKER%n%H%n%s",
        "--name-only",
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        raw_output = proc.stdout
    except Exception as e:
        logger.warning("git_log_extraction_failed", repo=repo_name, error=str(e))
        return queries

    chunks = raw_output.split("COMMIT_MARKER\n")
    for chunk in chunks:
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        commit_hash = lines[0]
        subject = lines[1]
        touched = lines[2:]

        # Filter touched files to existing files relative to repo root
        existing_touched = [
            t for t in touched if (repo_path / t).is_file() and not t.startswith(".git")
        ]
        if not existing_touched:
            continue

        q_id = f"{repo_name}_commit_{commit_hash[:8]}"
        queries.append(
            BenchmarkQuery(
                query_id=q_id,
                repo=repo_name,
                category="git_commit",
                query=subject,
                ground_truth_files=existing_touched,
                commit_hash=commit_hash,
            )
        )

        # Generate a paraphrase query for commits with conventional commit prefix
        match = re.match(r"^[a-z]+(\([^\)]+\))?:\s*(.+)$", subject, re.IGNORECASE)
        if match:
            clean_subject = match.group(2).strip()
            if len(clean_subject) > 10:
                p_id = f"{repo_name}_paraphrase_{commit_hash[:8]}"
                queries.append(
                    BenchmarkQuery(
                        query_id=p_id,
                        repo=repo_name,
                        category="recent_change",
                        query=f"where is {clean_subject} implemented",
                        ground_truth_files=existing_touched,
                        commit_hash=commit_hash,
                    )
                )

    return queries


def get_curated_queries_for_repo(repo_path: Path) -> list[BenchmarkQuery]:
    """Provide hand-written queries per category tailored to each repository."""
    repo_name = repo_path.name
    queries: list[BenchmarkQuery] = []

    if "synapse" in repo_name.lower():
        queries.extend(
            [
                BenchmarkQuery(
                    query_id="synap_sym_1",
                    repo=repo_name,
                    category="symbol_lookup",
                    query="SynapRuntime",
                    ground_truth_files=["src/synap_git/indexer/engine.py"],
                ),
                BenchmarkQuery(
                    query_id="synap_sym_2",
                    repo=repo_name,
                    category="symbol_lookup",
                    query="RetrievalEngine",
                    ground_truth_files=["src/synap_git/retrieval/engine.py"],
                ),
                BenchmarkQuery(
                    query_id="synap_where_1",
                    repo=repo_name,
                    category="where_is_x",
                    query="where is SQLite database connection and schema initialization",
                    ground_truth_files=["src/synap_git/storage/sqlite.py"],
                ),
                BenchmarkQuery(
                    query_id="synap_where_2",
                    repo=repo_name,
                    category="where_is_x",
                    query="where is CLI argument parsing and main entry point",
                    ground_truth_files=["src/synap_git/cli/main.py"],
                ),
                BenchmarkQuery(
                    query_id="synap_how_1",
                    repo=repo_name,
                    category="how_does_x_work",
                    query="how does hybrid retrieval ranking and RRF score calculation work",
                    ground_truth_files=["src/synap_git/retrieval/engine.py"],
                ),
                BenchmarkQuery(
                    query_id="synap_how_2",
                    repo=repo_name,
                    category="how_does_x_work",
                    query="how does AST skeletonization extract signatures",
                    ground_truth_files=["src/synap_git/parser/registry.py"],
                ),
                BenchmarkQuery(
                    query_id="synap_trace_1",
                    repo=repo_name,
                    category="stack_trace",
                    query='Traceback (most recent call last):\n  File "src/synap_git/retrieval/engine.py", line 504, in retrieve\n    self.index_docs()',
                    ground_truth_files=["src/synap_git/retrieval/engine.py"],
                ),
                BenchmarkQuery(
                    query_id="synap_arch_1",
                    repo=repo_name,
                    category="architecture",
                    query="three layer context infrastructure architecture AST SQLite and wiki",
                    ground_truth_files=[
                        "AGENTS.md",
                        "README.md",
                        "src/synap_git/indexer/engine.py",
                    ],
                ),
                BenchmarkQuery(
                    query_id="synap_dec_1",
                    repo=repo_name,
                    category="past_decision",
                    query="offline-first structural context engine architectural decisions and negative constraints",
                    ground_truth_files=["DECISIONS.md", "AGENTS.md"],
                ),
                BenchmarkQuery(
                    query_id="synap_conv_1",
                    repo=repo_name,
                    category="convention",
                    query="code quality standards ruff line length and mypy strict typing",
                    ground_truth_files=["AGENTS.md", "pyproject.toml"],
                ),
            ]
        )
    elif "leetsync" in repo_name.lower():
        queries.extend(
            [
                BenchmarkQuery(
                    query_id="leet_sym_1",
                    repo=repo_name,
                    category="symbol_lookup",
                    query="github api upload and commit client",
                    ground_truth_files=["src/background/github.ts"],
                ),
                BenchmarkQuery(
                    query_id="leet_sym_2",
                    repo=repo_name,
                    category="symbol_lookup",
                    query="problem pattern list definitions",
                    ground_truth_files=["src/utils/patterns.ts"],
                ),
                BenchmarkQuery(
                    query_id="leet_where_1",
                    repo=repo_name,
                    category="where_is_x",
                    query="where is the browser extension popup user interface logic",
                    ground_truth_files=["src/popup/popup.ts"],
                ),
                BenchmarkQuery(
                    query_id="leet_where_2",
                    repo=repo_name,
                    category="where_is_x",
                    query="where is content script injected to listen to leetcode submissions",
                    ground_truth_files=["src/content/content.ts"],
                ),
                BenchmarkQuery(
                    query_id="leet_how_1",
                    repo=repo_name,
                    category="how_does_x_work",
                    query="how does markdown generation format leetcode solutions",
                    ground_truth_files=["src/utils/markdown.ts"],
                ),
                BenchmarkQuery(
                    query_id="leet_how_2",
                    repo=repo_name,
                    category="how_does_x_work",
                    query="how does monaco editor injection extract submitted code",
                    ground_truth_files=["src/injected/injectMonaco.ts"],
                ),
                BenchmarkQuery(
                    query_id="leet_trace_1",
                    repo=repo_name,
                    category="stack_trace",
                    query="Error: Failed to push to github at github.ts:45 in commitFile",
                    ground_truth_files=["src/background/github.ts"],
                ),
                BenchmarkQuery(
                    query_id="leet_arch_1",
                    repo=repo_name,
                    category="architecture",
                    query="extension architecture background service worker content script and popup",
                    ground_truth_files=["README.md", "package.json"],
                ),
                BenchmarkQuery(
                    query_id="leet_dec_1",
                    repo=repo_name,
                    category="past_decision",
                    query="restore original 18 patterns decision",
                    ground_truth_files=["src/utils/patterns.ts", "README.md"],
                ),
                BenchmarkQuery(
                    query_id="leet_conv_1",
                    repo=repo_name,
                    category="convention",
                    query="vite build configuration and typescript compiler options",
                    ground_truth_files=["vite.config.ts", "tsconfig.json"],
                ),
            ]
        )
    elif "disha" in repo_name.lower():
        queries.extend(
            [
                BenchmarkQuery(
                    query_id="disha_sym_1",
                    repo=repo_name,
                    category="symbol_lookup",
                    query="classifier gated patient evolution profile pipeline",
                    ground_truth_files=["disha_core/pep/classifier_gated.py"],
                ),
                BenchmarkQuery(
                    query_id="disha_sym_2",
                    repo=repo_name,
                    category="symbol_lookup",
                    query="exercise safety rules and validation engine",
                    ground_truth_files=[
                        "disha_core/pep/exercise_safety.py",
                        "disha_core/pep/exercise_engine.py",
                    ],
                ),
                BenchmarkQuery(
                    query_id="disha_where_1",
                    repo=repo_name,
                    category="where_is_x",
                    query="where is the health check and internal diagnostic router",
                    ground_truth_files=[
                        "disha_core/routers/health.py",
                        "disha_core/routers/internal.py",
                    ],
                ),
                BenchmarkQuery(
                    query_id="disha_where_2",
                    repo=repo_name,
                    category="where_is_x",
                    query="where are user authentication and patient onboarding endpoints",
                    ground_truth_files=[
                        "disha_core/routers/auth.py",
                        "disha_core/routers/patient.py",
                    ],
                ),
                BenchmarkQuery(
                    query_id="disha_how_1",
                    repo=repo_name,
                    category="how_does_x_work",
                    query="how does compliance ledger record patient audit events",
                    ground_truth_files=["disha_core/compliance/ledger.py"],
                ),
                BenchmarkQuery(
                    query_id="disha_how_2",
                    repo=repo_name,
                    category="how_does_x_work",
                    query="how does rate limiter protect voice and chat endpoints",
                    ground_truth_files=["disha_core/security/rate_limiter.py"],
                ),
                BenchmarkQuery(
                    query_id="disha_trace_1",
                    repo=repo_name,
                    category="stack_trace",
                    query='Traceback (most recent call last):\n  File "disha_core/pep/classifier_gated.py", line 85, in update_profile',
                    ground_truth_files=["disha_core/pep/classifier_gated.py"],
                ),
                BenchmarkQuery(
                    query_id="disha_arch_1",
                    repo=repo_name,
                    category="architecture",
                    query="disha core system architecture fastapi routers compliance and database schema",
                    ground_truth_files=["disha_core/main.py", "disha_core/db/schema.sql"],
                ),
                BenchmarkQuery(
                    query_id="disha_dec_1",
                    repo=repo_name,
                    category="past_decision",
                    query="classifier gated PEP tournament benchmark evaluation",
                    ground_truth_files=["README.md"],
                ),
                BenchmarkQuery(
                    query_id="disha_conv_1",
                    repo=repo_name,
                    category="convention",
                    query="pyproject toml dependencies and pytest configuration",
                    ground_truth_files=["pyproject.toml", "pytest.ini"],
                ),
            ]
        )

    return queries


def evaluate_query(
    runtime: SynapRuntime,
    repo_path: Path,
    b_query: BenchmarkQuery,
    budgets: list[int],
    enc: tiktoken.Encoding,
) -> QueryEvaluationResult:
    """Evaluate a single query on Synapse vs Naive Agent across budgets."""
    # 1. Main retrieval pass for ranking metrics at standard budget (4000)
    t0 = time.perf_counter()
    ans_content, sources, trace = runtime.query_hybrid(
        b_query.query, max_tokens=4000, synthesize_answer=False
    )
    latency_ms = (time.perf_counter() - t0) * 1000.0

    retrieved_files = extract_files_from_synapse_output(sources, ans_content, trace)
    r5, r10, mrr, ndcg10 = compute_metrics(retrieved_files, b_query.ground_truth_files)

    # 2. Budget evaluations (500, 1500, 4000)
    budget_results: dict[str, BudgetResult] = {}
    gt_set = set(b_query.ground_truth_files)

    for budget in budgets:
        # Synapse Pack at this budget
        s_ans, s_sources, _ = runtime.query_hybrid(
            b_query.query, max_tokens=budget, synthesize_answer=False
        )
        s_tokens = len(enc.encode(s_ans))
        s_files = extract_files_from_synapse_output(s_sources, s_ans)
        s_recall = len(set(s_files) & gt_set) / max(1, len(gt_set))

        # Naive Agent at this budget
        n_tokens, n_files = run_naive_agent(repo_path, b_query.query, budget=budget, enc=enc)
        n_recall = len(set(n_files) & gt_set) / max(1, len(gt_set))

        savings = 0.0
        if n_tokens > 0:
            savings = round(((n_tokens - s_tokens) / n_tokens) * 100.0, 1)

        budget_results[str(budget)] = BudgetResult(
            budget=budget,
            synapse_tokens=s_tokens,
            synapse_recall=round(s_recall, 4),
            synapse_files=s_files,
            naive_tokens=n_tokens,
            naive_recall=round(n_recall, 4),
            naive_files=n_files,
            token_savings_pct=savings,
        )

    return QueryEvaluationResult(
        query_id=b_query.query_id,
        repo=b_query.repo,
        category=b_query.category,
        query=b_query.query,
        ground_truth_files=b_query.ground_truth_files,
        synapse_retrieved_files=retrieved_files,
        recall_at_5=round(r5, 4),
        recall_at_10=round(r10, 4),
        mrr=round(mrr, 4),
        ndcg_at_10=round(ndcg10, 4),
        latency_ms=round(latency_ms, 2),
        budget_results=budget_results,
    )


def percentile(data: list[float], pct: float) -> float:
    """Compute percentile value for a list of numbers."""
    if not data:
        return 0.0
    s_data = sorted(data)
    idx = int(math.ceil((pct / 100.0) * len(s_data))) - 1
    idx = max(0, min(idx, len(s_data) - 1))
    return round(s_data[idx], 2)


def run_benchmark(
    repo_paths: list[Path],
    commits_per_repo: int = 15,
    budgets: list[int] | None = None,
    quick: bool = False,
    quiet: bool = False,
) -> dict[str, Any]:
    """Execute the full multi-repo benchmark suite."""
    if budgets is None:
        budgets = [500, 1500, 4000]

    enc = tiktoken.get_encoding("o200k_base")
    all_results: list[QueryEvaluationResult] = []
    repo_names: list[str] = []

    for repo_path in repo_paths:
        if not repo_path.exists() or not (repo_path / ".git").exists():
            if not quiet:
                console.print(f"[yellow]Skipping non-existent git repository: {repo_path}[/yellow]")
            continue

        repo_names.append(repo_path.name)
        if not quiet:
            console.print(f"[bold cyan]Benchmarking repository:[/bold cyan] {repo_path.name}")

        settings = SynapSettings(repository_path=repo_path)
        runtime = SynapRuntime(settings)
        runtime.initialize_storage()

        # Gather queries
        git_queries = extract_git_queries(repo_path, max_commits=commits_per_repo)
        curated_queries = get_curated_queries_for_repo(repo_path)
        queries = git_queries + curated_queries

        if quick:
            queries = queries[:5]

        for q in queries:
            try:
                res = evaluate_query(runtime, repo_path, q, budgets=budgets, enc=enc)
                all_results.append(res)
            except Exception as e:
                logger.error(
                    "query_eval_error", query_id=q.query_id, error=str(e), repo=repo_path.name
                )

    if not all_results:
        raise ValueError("No queries were successfully evaluated.")

    # 1. Overall metrics
    recalls_5 = [r.recall_at_5 for r in all_results]
    recalls_10 = [r.recall_at_10 for r in all_results]
    mrrs = [r.mrr for r in all_results]
    ndcgs = [r.ndcg_at_10 for r in all_results]
    latencies = [r.latency_ms for r in all_results]

    metrics_overall = {
        "recall_at_5": round(sum(recalls_5) / len(recalls_5), 4),
        "recall_at_10": round(sum(recalls_10) / len(recalls_10), 4),
        "mrr": round(sum(mrrs) / len(mrrs), 4),
        "ndcg_at_10": round(sum(ndcgs) / len(ndcgs), 4),
        "latency_p50_ms": percentile(latencies, 50),
        "latency_p95_ms": percentile(latencies, 95),
        "latency_mean_ms": round(sum(latencies) / len(latencies), 2),
    }

    # 2. Budget evaluation across all queries
    budget_eval: dict[str, Any] = {}
    for b in budgets:
        b_key = str(b)
        syn_toks = [r.budget_results[b_key].synapse_tokens for r in all_results]
        syn_recs = [r.budget_results[b_key].synapse_recall for r in all_results]
        nai_toks = [r.budget_results[b_key].naive_tokens for r in all_results]
        nai_recs = [r.budget_results[b_key].naive_recall for r in all_results]
        sav_pcts = [r.budget_results[b_key].token_savings_pct for r in all_results]

        avg_syn_tok = round(sum(syn_toks) / len(syn_toks), 1)
        avg_nai_tok = round(sum(nai_toks) / len(nai_toks), 1)
        savings_overall = (
            round(((avg_nai_tok - avg_syn_tok) / avg_nai_tok) * 100.0, 1)
            if avg_nai_tok > 0
            else 0.0
        )

        budget_eval[b_key] = {
            "synapse": {
                "avg_tokens": avg_syn_tok,
                "recall": round(sum(syn_recs) / len(syn_recs), 4),
            },
            "naive": {
                "avg_tokens": avg_nai_tok,
                "recall": round(sum(nai_recs) / len(nai_recs), 4),
            },
            "token_savings_pct": savings_overall,
            "avg_savings_pct": round(sum(sav_pcts) / len(sav_pcts), 1),
        }

    # 3. By Category
    categories = sorted({r.category for r in all_results})
    by_category: dict[str, Any] = {}
    for cat in categories:
        cat_results = [r for r in all_results if r.category == cat]
        c_r5 = [r.recall_at_5 for r in cat_results]
        c_r10 = [r.recall_at_10 for r in cat_results]
        c_mrr = [r.mrr for r in cat_results]
        c_ndcg = [r.ndcg_at_10 for r in cat_results]
        c_lats = [r.latency_ms for r in cat_results]
        by_category[cat] = {
            "count": len(cat_results),
            "recall_at_5": round(sum(c_r5) / len(c_r5), 4),
            "recall_at_10": round(sum(c_r10) / len(c_r10), 4),
            "mrr": round(sum(c_mrr) / len(c_mrr), 4),
            "ndcg_at_10": round(sum(c_ndcg) / len(c_ndcg), 4),
            "latency_p50_ms": percentile(c_lats, 50),
            "latency_p95_ms": percentile(c_lats, 95),
        }

    # 4. By Repo
    by_repo: dict[str, Any] = {}
    for repo_name in repo_names:
        rp_results = [r for r in all_results if r.repo == repo_name]
        if not rp_results:
            continue
        rp_r5 = rp_results
        by_repo[repo_name] = {
            "queries_evaluated": len(rp_results),
            "recall_at_5": round(sum(r.recall_at_5 for r in rp_r5) / len(rp_r5), 4),
            "recall_at_10": round(sum(r.recall_at_10 for r in rp_r5) / len(rp_r5), 4),
            "mrr": round(sum(r.mrr for r in rp_r5) / len(rp_r5), 4),
            "ndcg_at_10": round(sum(r.ndcg_at_10 for r in rp_r5) / len(rp_r5), 4),
            "latency_p50_ms": percentile([r.latency_ms for r in rp_r5], 50),
            "latency_p95_ms": percentile([r.latency_ms for r in rp_r5], 95),
        }

    # Package version
    from synap_git import __version__

    return {
        "version": __version__,
        "timestamp": datetime.now(UTC).isoformat(),
        "tokenizer": "o200k_base",
        "repositories": repo_names,
        "total_queries": len(all_results),
        "metrics_overall": metrics_overall,
        "budget_evaluation": budget_eval,
        "by_category": by_category,
        "by_repo": by_repo,
        "results": [asdict(r) for r in all_results],
    }


def bench_cmd(
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output path for benchmark results JSON."),
    ] = Path("bench/numbers.json"),
    repos: Annotated[
        str | None,
        typer.Option("--repos", help="Comma-separated repo paths to benchmark."),
    ] = None,
    commits: Annotated[
        int, typer.Option("--commits", "-n", help="Commits per repo to evaluate.")
    ] = 15,
    budget_levels: Annotated[
        str, typer.Option("--budgets", help="Comma-separated token budgets.")
    ] = "500,1500,4000",
    quick: Annotated[
        bool, typer.Option("--quick", help="Run quick benchmark on subset of queries.")
    ] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress progress output.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output raw JSON to stdout.")] = False,
) -> None:
    """Run multi-repo ground-truth benchmark and output metrics to bench/numbers.json."""
    if repos:
        repo_paths = [Path(p.strip()).resolve() for p in repos.split(",") if p.strip()]
    else:
        # Default 3 repositories: Synapse, LeetSync, disha ai
        default_candidates = [
            Path("/Users/nitrousoxide/Code/synapse"),
            Path("/Users/nitrousoxide/Code/LeetSync"),
            Path("/Users/nitrousoxide/Code/disha ai"),
        ]
        repo_paths = [p for p in default_candidates if p.exists()]
        if not repo_paths:
            repo_paths = [Path.cwd()]

    budgets = [int(b.strip()) for b in budget_levels.split(",") if b.strip()]

    if not quiet and not json_output:
        console.print("[bold green]Starting Synapse Multi-Repo Benchmark...[/bold green]")
        console.print(f"Repositories: {[p.name for p in repo_paths]}")
        console.print(f"Budgets: {budgets} | Commits per repo: {commits}")

    results = run_benchmark(
        repo_paths=repo_paths,
        commits_per_repo=commits,
        budgets=budgets,
        quick=quick,
        quiet=quiet or json_output,
    )

    # Ensure parent output directory exists
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")

    if json_output:
        print(json.dumps(results, indent=2))
        return

    if not quiet:
        console.print(f"\n[green]✓ Benchmark complete! Results saved to {output}[/green]\n")

        # Display summary tables
        m = results["metrics_overall"]
        tbl = Table(title="Synapse Retrieval Performance Summary")
        tbl.add_column("Metric", style="cyan")
        tbl.add_column("Score", style="bold green")
        tbl.add_row("Recall@5", f"{m['recall_at_5']:.2%}")
        tbl.add_row("Recall@10", f"{m['recall_at_10']:.2%}")
        tbl.add_row("MRR", f"{m['mrr']:.4f}")
        tbl.add_row("nDCG@10", f"{m['ndcg_at_10']:.4f}")
        tbl.add_row("Latency (p50)", f"{m['latency_p50_ms']} ms")
        tbl.add_row("Latency (p95)", f"{m['latency_p95_ms']} ms")
        console.print(tbl)

        b_tbl = Table(title="Token Budget & Pack Efficiency vs. Naive Ripgrep Agent")
        b_tbl.add_column("Budget", style="cyan")
        b_tbl.add_column("Synapse Tokens", style="green")
        b_tbl.add_column("Synapse Recall", style="green")
        b_tbl.add_column("Naive Tokens", style="yellow")
        b_tbl.add_column("Naive Recall", style="yellow")
        b_tbl.add_column("Token Savings", style="bold magenta")

        for b_str, b_data in results["budget_evaluation"].items():
            b_tbl.add_row(
                b_str,
                f"{b_data['synapse']['avg_tokens']:.0f}",
                f"{b_data['synapse']['recall']:.2%}",
                f"{b_data['naive']['avg_tokens']:.0f}",
                f"{b_data['naive']['recall']:.2%}",
                f"{b_data['token_savings_pct']:.1f}%",
            )
        console.print(b_tbl)
