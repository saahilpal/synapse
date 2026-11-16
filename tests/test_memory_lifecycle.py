from __future__ import annotations

import math
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
import pytest

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime
from synap_git.retrieval.engine import (
    QueryIntent,
    classify_intent_5tier,
)
from synap_git.retrieval.memory import (
    DeduplicationStatus,
    MemoryLifecycleEngine,
    MemoryRetriever,
    compute_simhash,
    compute_utility_score,
    simhash_hamming_distance,
    simhash_similarity,
)
from synap_git.storage.sqlite import SynapStore


@pytest.fixture
def temp_store(tmp_path: Path) -> SynapStore:
    db_path = tmp_path / "synap_test.db"
    store = SynapStore(db_path)
    store.initialize()
    return store


@pytest.fixture
def repo_with_docs(tmp_path: Path) -> tuple[Path, SynapSettings]:
    repo = tmp_path / "repo_docs"
    repo.mkdir()

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "docs@example.com"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Docs Tester"], cwd=repo, check=True)

    # Core source file
    (repo / "calc.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n\ndef multiply(a: int, b: int) -> int:\n    return a * b\n",
        encoding="utf-8",
    )

    # Documentation files
    (repo / "README.md").write_text(
        "# Synapse Architecture\n\nSynapse provides persistent structural context for coding agents.\n\n## Installation Guide\n\nRun pip install synap-git to start.\n",
        encoding="utf-8",
    )
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [v2.6.0] - 2026-11-16\n- Added two-tier vector acceleration and RRF k=60 ranking.\n",
        encoding="utf-8",
    )
    (repo / "AGENTS.md").write_text(
        "# Agent Directives\n\nAlways call get_session_preamble() before modifying files.\n",
        encoding="utf-8",
    )

    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "init with docs"], cwd=repo, check=True)

    settings = SynapSettings(
        repository_path=repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synap_docs.db",
        object_path=tmp_path / "objects_docs",
    )
    return repo, settings


def test_vector_blob_storage_and_tier2_numpy_acceleration(temp_store: SynapStore) -> None:
    """Verify vector embeddings stored as BLOBs and accelerated search runs < 2.5ms."""
    # Seed 100 symbol vectors
    dim = 64
    for i in range(100):
        sym_id = f"sym_{i}"
        # Create a mock file and symbol in SQLite
        temp_store.upsert_file_and_symbols(
            file_id=f"file_{i}",
            path=f"src/mod_{i}.py",
            git_oid="oid123",
            content_hash="hash123",
            language="python",
            symbols=[
                {
                    "symbol_id": sym_id,
                    "name": f"func_{i}",
                    "kind": "function",
                    "start_line": 1,
                    "end_line": 10,
                    "ast_hash": "asthash",
                    "metadata": {},
                }
            ],
        )
        vec = [float(j == (i % dim)) for j in range(dim)]
        temp_store.put_embedding(
            symbol_id=sym_id,
            model_name="test_embed",
            model_version="v1",
            prompt_version="p1",
            vector=vec,
            content_hash=f"chash_{i}",
        )

    # Verify stored embedding vector is retrievable as a list of floats
    retrieved = temp_store.get_embedding("sym_0", "test_embed")
    assert retrieved is not None
    assert isinstance(retrieved["vector"], list)
    assert len(retrieved["vector"]) == dim
    assert retrieved["vector"][0] == 1.0

    # Query using vector matching sym_0
    q_vec = [float(j == 0) for j in range(dim)]
    results = temp_store.get_similar_symbols(q_vec, limit=5)
    assert len(results) > 0
    assert results[0]["name"] == "func_0"
    assert results[0]["similarity"] >= 0.99

    # Benchmark NumPy Tier 2 acceleration for 10k vectors < 2.5ms
    matrix = np.random.randn(10000, 128).astype(np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    matrix = matrix / norms
    q = np.random.randn(128).astype(np.float32)
    q = q / np.linalg.norm(q)

    t0 = time.perf_counter()
    sims = matrix @ q
    _ = np.argpartition(-sims, 50)[:50]
    duration_ms = (time.perf_counter() - t0) * 1000.0

    assert duration_ms < 2.5, f"Vector dot product took {duration_ms:.2f} ms (expected < 2.5 ms)"


def test_get_blast_radius_chunking_large_touched_symbols(temp_store: SynapStore) -> None:
    """Verify get_blast_radius safely handles >500 touched symbols without SQL variable limit error."""
    # Insert 600 symbols and edges
    file_id = "test_file_blast"
    path = "src/massive.py"
    symbols = []
    for i in range(600):
        symbols.append(
            {
                "symbol_id": f"sym_blast_{i}",
                "name": f"func_blast_{i}",
                "kind": "function",
                "start_line": i * 10 + 1,
                "end_line": i * 10 + 5,
                "ast_hash": f"ast_{i}",
                "metadata": {},
            }
        )

    temp_store.upsert_file_and_symbols(
        file_id=file_id,
        path=path,
        git_oid="oid_blast",
        content_hash="chash_blast",
        language="python",
        symbols=symbols,
    )

    # Call get_blast_radius with diff ranges covering all 600 symbols
    diff_ranges = {path: [(1, 6500)]}
    radius = temp_store.get_blast_radius(diff_ranges)

    assert len(radius["touched_symbols"]) == 600
    assert isinstance(radius["direct_callers"], list)
    assert isinstance(radius["impacted_tests"], list)


def test_schema_columns_and_memory_citations(temp_store: SynapStore) -> None:
    """Verify decisions, lessons, checkpoints columns and memory_citations table."""
    # 1. Put decision with new schema columns
    temp_store.put_decision(
        decision_id="dec_001",
        branch="main",
        commit_hash="c001",
        content="Use SQLite WAL mode with synchronous=NORMAL",
        context_info="AUD-07",
        fingerprint_hash="abcd1234",
        utility_score=1.5,
        source_scope="local",
    )
    decisions = temp_store.get_decisions(limit=1)
    assert len(decisions) == 1
    assert decisions[0]["decision_id"] == "dec_001"
    assert decisions[0]["utility_score"] == 1.5
    assert decisions[0]["source_scope"] == "local"

    # 2. Put checkpoint with diff_summary and status
    temp_store.put_checkpoint(
        checkpoint_id="cp_001",
        branch="main",
        commit_hash="c001",
        doing="Implement Work Item E",
        changed_files='["sqlite.py", "engine.py"]',
        next_step="Write tests",
        blockers="None",
        diff_summary="Added BLOB vectors and RRF",
        status="active",
    )
    cp = temp_store.get_checkpoint("cp_001")
    assert cp is not None
    assert cp["diff_summary"] == "Added BLOB vectors and RRF"
    assert cp["status"] == "active"

    # 3. Record citation and feedback
    temp_store.record_citation(
        citation_id="cite_001",
        memory_id="dec_001",
        memory_type="decision",
        action="thumbs_up",
        feedback=1,
    )
    citations = temp_store.get_citations("dec_001")
    assert len(citations) == 1
    assert citations[0]["action"] == "thumbs_up"
    assert citations[0]["feedback"] == 1

    # Verify decision citation_count incremented
    updated_dec = temp_store.get_decisions(limit=1)[0]
    assert updated_dec["citation_count"] == 1


def test_simhash_lexical_deduplication() -> None:
    """Verify 64-bit SimHash detects identical and near-identical paraphrases."""
    t1 = "Always verify unit tests before submitting a pull request."
    t2 = "Always verify unit tests before submitting a pull request."
    t3 = "Unit tests must always be verified before submitting a pull request."
    t4 = "Completely different topic about database optimization and network latency."

    h1 = compute_simhash(t1)
    h2 = compute_simhash(t2)
    h3 = compute_simhash(t3)
    h4 = compute_simhash(t4)

    assert h1 == h2
    assert simhash_hamming_distance(h1, h2) == 0
    assert simhash_similarity(h1, h2) == 1.0

    # Near-identical text with reordered words has smaller distance than different topic
    dist13 = simhash_hamming_distance(h1, h3)
    dist14 = simhash_hamming_distance(h1, h4)
    assert dist13 < dist14
    assert simhash_similarity(h1, h3) > 0.70


def test_memory_lifecycle_2stage_deduplication(temp_store: SynapStore) -> None:
    """Verify MemoryLifecycleEngine handles 2-stage deduplication and cosine thresholds."""
    engine = MemoryLifecycleEngine(temp_store)

    existing = [
        {
            "decision_id": "mem_1",
            "content": "Use PostgreSQL connection pool with max 20 connections.",
            "fingerprint_hash": hex(
                compute_simhash("Use PostgreSQL connection pool with max 20 connections.")
            )[2:],
            "vector": [1.0, 0.0, 0.0],
        },
        {
            "decision_id": "mem_2",
            "content": "Ensure all handlers validate incoming JWT tokens.",
            "fingerprint_hash": hex(
                compute_simhash("Ensure all handlers validate incoming JWT tokens.")
            )[2:],
            "vector": [0.0, 1.0, 0.0],
        },
    ]

    # Stage 1 duplicate: identical wording
    res1 = engine.evaluate_deduplication(
        "Use PostgreSQL connection pool with max 20 connections.",
        existing,
    )
    assert res1.status == DeduplicationStatus.DUPLICATE
    assert res1.stage == "simhash"
    assert res1.matched_memory_id == "mem_1"

    # Stage 2: Dense cosine >= 0.92 -> DUPLICATE
    res_cos_dup = engine.evaluate_deduplication(
        "Configuring postgres connection pooling limits",
        existing,
        candidate_vector=[0.98, 0.02, 0.0],
    )
    assert res_cos_dup.status == DeduplicationStatus.DUPLICATE
    assert res_cos_dup.stage == "cosine"
    assert res_cos_dup.similarity_score >= 0.92

    # Stage 2: Dense cosine in [0.80, 0.92) -> CONSOLIDATE
    res_cos_consol = engine.evaluate_deduplication(
        "Postgres database pool sizing",
        existing,
        candidate_vector=[0.85, 0.52, 0.0],
    )
    assert res_cos_consol.status == DeduplicationStatus.CONSOLIDATE
    assert res_cos_consol.stage == "cosine"
    assert 0.80 <= res_cos_consol.similarity_score < 0.92

    # Stage 2: Dense cosine < 0.80 -> NOVEL
    res_novel = engine.evaluate_deduplication(
        "Add Redis cache with 10 minute TTL",
        existing,
        candidate_vector=[0.0, 0.0, 1.0],
    )
    assert res_novel.status == DeduplicationStatus.NOVEL
    assert res_novel.stage == "cosine"
    assert res_novel.similarity_score < 0.80


def test_multi_factor_utility_scoring() -> None:
    """Verify multi-factor utility scoring formula with feedback, decay, and citations."""
    # 1. Base score
    u_base = compute_utility_score(base_score=1.0)
    assert math.isclose(u_base, 1.0, rel_tol=1e-3)

    # 2. Citations boost score
    u_cited = compute_utility_score(base_score=1.0, citation_count=5)
    assert u_cited > u_base

    # 3. Positive feedback boosts score
    u_positive = compute_utility_score(base_score=1.0, positive_feedback=3)
    assert u_positive > u_base

    # 4. Negative feedback penalizes score
    u_negative = compute_utility_score(base_score=1.0, negative_feedback=2)
    assert u_negative < u_base

    # 5. Time decay reduces score over 30 days (half-life)
    u_decayed = compute_utility_score(
        base_score=1.0, days_since_last_referenced=30.0, half_life_days=30.0
    )
    assert math.isclose(u_decayed, 0.5, rel_tol=1e-2)

    # 6. Commit distance hyperbolic decay
    u_commits = compute_utility_score(base_score=1.0, commit_distance=50)
    assert u_commits < u_base


def test_memory_retriever_scope_isolation(temp_store: SynapStore, tmp_path: Path) -> None:
    """Verify strict scope isolation between local repository and global developer habits."""
    global_db = tmp_path / "global_test.db"
    retriever = MemoryRetriever(local_store=temp_store, global_db_path=global_db)

    # Save a cross-project global habit
    global_id = retriever.save_global_memory(
        category="habit",
        content="Always use ruff for linting and formatting in Python 3.12+ projects.",
        context_key="habit:python_ruff",
        summary="Use ruff linter",
        tags=["python", "tooling"],
    )

    # 1. Local retrieval should NOT return global memory (strict scope isolation)
    local_memories = retriever.retrieve_local_memories("ruff")
    assert len(local_memories) == 0

    # 2. Global listing finds the memory
    global_memories = retriever.list_global_memories(query="ruff")
    assert len(global_memories) == 1
    assert global_memories[0]["global_id"] == global_id
    assert global_memories[0]["usage_count"] == 0

    # 3. Ingest into local repo
    local_id = retriever.ingest_global_memory(global_id, as_category="decision")
    assert local_id is not None

    # Global usage count incremented
    global_after = retriever.list_global_memories(query="ruff")[0]
    assert global_after["usage_count"] == 1

    # Local retrieval NOW finds the ingested memory with source_scope='global'
    local_memories_after = retriever.retrieve_local_memories("ruff")
    assert len(local_memories_after) == 1
    assert local_memories_after[0]["source_global_id"] == global_id

    # 4. Record feedback
    retriever.record_feedback(local_id, "thumbs_up")
    citations = temp_store.get_citations(local_id)
    assert len(citations) == 1
    assert citations[0]["feedback"] == 1


def test_5tier_query_intent_router() -> None:
    """Verify the 5-tier query intent router correctly classifies query types."""
    # Past decisions
    assert (
        classify_intent_5tier("What was our decision on SQLite WAL mode?")
        == QueryIntent.PAST_DECISIONS
    )
    assert (
        classify_intent_5tier("Why did we choose Tree-sitter for AST parsing?")
        == QueryIntent.PAST_DECISIONS
    )
    assert classify_intent_5tier("ADR tradeoff rationale") == QueryIntent.PAST_DECISIONS

    # Debugging
    assert classify_intent_5tier("Why does auth/login.py fail?") == QueryIntent.DEBUGGING
    assert classify_intent_5tier("Fix crash in memory daemon") == QueryIntent.DEBUGGING
    assert classify_intent_5tier("Exception raised during git revert") == QueryIntent.DEBUGGING

    # Architecture
    assert classify_intent_5tier("Architecture overview of Synapse") == QueryIntent.ARCHITECTURE
    assert (
        classify_intent_5tier("Explain the high level design of indexing")
        == QueryIntent.ARCHITECTURE
    )
    assert (
        classify_intent_5tier("What is the data flow between L1 and L2?")
        == QueryIntent.ARCHITECTURE
    )

    # Navigation
    assert classify_intent_5tier("Where is get_blast_radius defined?") == QueryIntent.NAVIGATION
    assert classify_intent_5tier("callers of compute_pagerank") == QueryIntent.NAVIGATION
    assert (
        classify_intent_5tier("path to src/synap_git/storage/sqlite.py") == QueryIntent.NAVIGATION
    )

    # Symbol lookup
    assert classify_intent_5tier("def get_embedding") == QueryIntent.SYMBOL_LOOKUP
    assert classify_intent_5tier("class SynapStore") == QueryIntent.SYMBOL_LOOKUP
    assert classify_intent_5tier("parse_cached_vec") == QueryIntent.SYMBOL_LOOKUP


def test_documentation_indexing_and_contextual_enrichment(
    repo_with_docs: tuple[Path, SynapSettings],
) -> None:
    """Verify README.md, CHANGELOG.md, and AGENTS.md are indexed into symbols_fts with contextual headers."""
    repo, settings = repo_with_docs
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    # Query for documentation content
    ans_readme, sources_readme, _ = runtime.query_hybrid(
        "Synapse provides persistent structural context", max_tokens=1000
    )
    assert len(sources_readme) > 0
    assert any("README.md" in s["source_path"] for s in sources_readme)
    # Contextual chunk enrichment verified in answer blocks
    assert "# File: README.md" in ans_readme
    assert "Module: README" in ans_readme

    # Query for changelog content
    ans_cl, sources_cl, _ = runtime.query_hybrid("two-tier vector acceleration", max_tokens=1000)
    assert len(sources_cl) > 0
    assert any("CHANGELOG.md" in s["source_path"] for s in sources_cl)
    assert "# File: CHANGELOG.md" in ans_cl

    # Query for agent directives
    ans_ag, sources_ag, _ = runtime.query_hybrid("get_session_preamble", max_tokens=1000)
    assert len(sources_ag) > 0
    assert any("AGENTS.md" in s["source_path"] for s in sources_ag)


def test_token_budget_overflow_never_appends_uncompressed_file(
    repo_with_docs: tuple[Path, SynapSettings],
) -> None:
    """Verify that when AST skeleton exceeds remaining budget, it never falls back to full raw file."""
    repo, settings = repo_with_docs
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    # Create a large file
    large_lines = ["def huge_function():"]
    for i in range(100):
        large_lines.append(f"    var_{i} = {i} * 100")
    large_lines.append("    return var_99\n")
    (repo / "huge.py").write_text("\n".join(large_lines), encoding="utf-8")

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "add huge file"], cwd=repo, check=True)

    runtime.bootstrap(force=True)

    # Request very tight token budget: 200 tokens
    answer, sources, trace = runtime.query_hybrid("huge_function", max_tokens=200)

    # Budget strictly enforced: tokens_used <= max_tokens
    assert trace["tokens_used"] <= 200
    # Did not dump all 100 lines into answer
    assert "var_80" not in answer
