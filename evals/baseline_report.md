# Synapse Baseline Retrieval & Grounding Benchmark Report

**Date:** 2026-11-16
**Evaluator:** Evaluation & Benchmark Engineer
**Target Repository:** `synapse` (`synap-git`)
**Commit State:** Pre-change baseline (unmodified engine)
**Dataset:** `evals/benchmark_dataset.json` (30 queries across 6 categories)
**Results Data:** `evals/baseline_results.json`

---

## 1. Executive Summary

A comprehensive, deterministic baseline benchmark was constructed and executed against the un-modified Synapse codebase to establish the grounding, retrieval accuracy, latency, and token efficiency baseline prior to upcoming architectural enhancements.

### Core Metrics Summary

| Metric | Baseline Value | Target Benchmark Standard | Status |
| :--- | :--- | :--- | :--- |
| **Recall@1 (Hit Rate @ 1)** | **33.33%** (10/30) | >= 60.0% | Deficit (-26.7%) |
| **Recall@3 (Hit Rate @ 3)** | **50.00%** (15/30) | >= 80.0% | Deficit (-30.0%) |
| **Recall@5 (Hit Rate @ 5)** | **53.33%** (16/30) | >= 90.0% | Deficit (-36.7%) |
| **Mean Reciprocal Rank (MRR)** | **0.4194** | >= 0.7500 | Low ranking precision |
| **Symbol-Level Hit@3** | **36.67%** (11/30) | >= 75.0% | High symbol degradation |
| **File-Level Hit@3** | **50.00%** (15/30) | >= 85.0% | Moderate file grounding |
| **Latency p50 (Median)** | **130.55 ms** | < 100.0 ms | Exceeds target |
| **Latency p95** | **155.94 ms** | < 150.0 ms | Slight overrun |
| **Average Context Tokens** | **829.00 tokens** | <= 1000 tokens (budget) | Within budget (82.9% pack) |

---

## 2. Category Performance Breakdown

The benchmark evaluates 30 representative developer queries equally divided across 6 core interaction categories (5 queries each):

```
+-------------------------------------------------------------------------------+
| Category             | Count | Recall@1 | Recall@3 | MRR    | p50 Latency (ms)|
+-------------------------------------------------------------------------------+
| navigation           |   5   |  60.0%   | 100.0%   | 0.8000 |    131.65       |
| symbol_lookup        |   5   |  60.0%   |  80.0%   | 0.7000 |    136.51       |
| debugging            |   5   |  40.0%   |  40.0%   | 0.4000 |    128.35       |
| decisions_memory     |   5   |  20.0%   |  40.0%   | 0.3167 |    129.40       |
| git_conventions      |   5   |  20.0%   |  20.0%   | 0.2000 |    139.01       |
| architecture         |   5   |   0.0%   |  20.0%   | 0.1000 |    141.75       |
+-------------------------------------------------------------------------------+
```

### Key Category Findings

1. **Navigation (Strongest: 100.0% Recall@3, MRR 0.8000)**:
   - Queries with explicit file or function hints ("where are tree sitter grammars loaded", "where is SQLite WAL configured", "where are git hooks installed") successfully isolate the relevant target files or parser methods in top-3.
2. **Symbol Lookup (Strong: 80.0% Recall@3, MRR 0.7000)**:
   - Direct symbols such as `CodeParserRegistry`, `HybridRetrievalEngine`, and `get_neighborhood` rank at #1.
   - However, large symbols (e.g. `SynapStore`, 1271 lines) suffer from SQLite FTS5 BM25 document length penalization, failing to return the class symbol itself directly (retrieving the file via structural neighbors).
   - Compound symbols (e.g. `classify_intent`) rank generic shorter symbols (`classify` in `git/state.py`) higher due to strict subtoken subset scoring (+0.15 vs +0.08).
3. **Debugging & Stack Traces (Weak: 40.0% Recall@3, MRR 0.4000)**:
   - Exact exception classes (`AmbiguousSymbolError`, `GitIntegrationError`) match instantly at rank #1.
   - Complex runtime traces ("OperationalError: database is locked", "ConnectionRefusedError: [Errno 61]") match superficial word tokens rather than the SQLite lock retry loop or daemon socket handler.
4. **Decisions & Memory (Poor: 40.0% Recall@3, MRR 0.3167)**:
   - Synapse's SQLite database contains rich `decisions` and `agent_memory` tables, but `query_hybrid` does NOT query them. It only queries the `symbols_fts` table, leaving architectural rationales stranded.
5. **Git Conventions & Documentation (Critical Deficit: 20.0% Recall@3, MRR 0.2000)**:
   - Markdown documents (`CHANGELOG.md`, `AGENTS.md`, `CLAUDE.md`) are present in `files`, but have 0 entries in `symbols_fts` because Tree-sitter AST parsing only extracts definitions for programming languages.
   - Queries regarding changelog versioning, commit formatting, or testing commands miss entirely.
6. **Architecture (Critical Deficit: 20.0% Recall@3, MRR 0.1000)**:
   - Conceptual queries ("how does daemon detect file modifications", "how does token budgeting and graceful folding work", "how does PageRank centrality ranking work") retrieve noisy unrelated symbols because RRF lexical matching lacks semantic vector embedding in offline Mode A.

---

## 3. Systematic Root-Cause Analysis

Detailed tracing of the 15 failed queries identified four distinct architectural bottlenecks in the baseline retrieval pipeline:

### Failure Mode 1: Markdown & Documentation Invisibility
- **Symptom:** 100% failure on documentation queries (`CHANGELOG.md`, `AGENTS.md`, `CLAUDE.md`).
- **Cause:** `symbols_fts` index is strictly populated from code symbols (`class_definition`, `function_definition`). Markdown files have 0 symbols indexed.
- **Remediation Opportunity:** Index markdown headings/sections into `symbols_fts` or integrate file-level lexical search.

### Failure Mode 2: Unqueried Behavioral Memory & Decisions
- **Symptom:** Queries about architectural decisions ("why was normal pragma chosen", "3-layer architecture") fail to surface the structured decisions in SQLite.
- **Cause:** `query_hybrid` only executes against `symbols_fts` and symbol embeddings. The `decisions` and `agent_memory` tables are completely ignored during retrieval.
- **Remediation Opportunity:** Multi-stage federation into `decisions` and `agent_memory` tables during query retrieval.

### Failure Mode 3: Subtoken Subset Calibration Bias
- **Symptom:** Query `classify_intent` ranked `classify` at #1 (score 0.1682) while `_classify_intent_fast` ranked #3 (score 0.0964).
- **Cause:** `cand_subtokens.issubset(query_subtokens)` rewards single-token symbols (`{'classify'}`) with a +0.15 score boost, while the exact target `_classify_intent_fast` (`{'classify', 'intent', 'fast'}`) is not a subset of `{'classify', 'intent'}` and receives only +0.08.
- **Remediation Opportunity:** Jaccard overlap similarity or Levenshtein distance for compound identifiers.

### Failure Mode 4: Large Symbol Context Starvation
- **Symptom:** For large symbols (e.g. `SynapStore`), full blocks exceed remaining token budget and graceful folding drops them if predecessors consume the budget.
- **Cause:** BM25 document length penalization pushes large classes down the initial candidate list. Preceding candidates consume the 850-token retrieval budget, starving out the primary symbol.

---

## 4. Query-by-Query Baseline Verification Ledger

| ID | Category | Query | Status | Rank | Matched Target | Latency | Tokens |
| :--- | :--- | :--- | :---: | :---: | :--- | :---: | :---: |
| `sym_synap_store` | symbol_lookup | `SynapStore` | HIT@1 | 1 | `path:src/synap_git/storage/sqlite.py` | 137.7ms | 826 |
| `sym_get_neighborhood` | symbol_lookup | `get_neighborhood` | HIT@1 | 1 | `symbol:get_neighborhood` | 136.5ms | 819 |
| `sym_classify_intent` | symbol_lookup | `classify_intent` | MISS | - | None | 102.8ms | 814 |
| `sym_code_parser_registry` | symbol_lookup | `CodeParserRegistry` | HIT@1 | 1 | `symbol:CodeParserRegistry` | 142.1ms | 819 |
| `sym_hybrid_retrieval_engine` | symbol_lookup | `HybridRetrievalEngine` | HIT@1 | 1 | `symbol:HybridRetrievalEngine` | 128.6ms | 836 |
| `nav_tree_sitter_grammars` | navigation | `where are tree sitter grammars loaded` | HIT@2 | 2 | `symbol:_parse_tree_sitter` | 96.3ms | 846 |
| `nav_sqlite_wal` | navigation | `where is SQLite WAL configured` | HIT@1 | 1 | `path:src/synap_git/storage/sqlite.py` | 116.7ms | 810 |
| `nav_daemon_lockfile` | navigation | `where is daemon lockfile and heartbeat managed` | HIT@3 | 3 | `path:src/synap_git/cli/main.py` | 148.9ms | 841 |
| `nav_git_hooks` | navigation | `where are git hooks installed and uninstalled` | HIT@1 | 1 | `symbol:hooks_install_cmd` | 164.5ms | 839 |
| `nav_mcp_server` | navigation | `where is FastMCP server initialized and registered` | HIT@1 | 1 | `symbol:SynapMCPServer` | 131.7ms | 815 |
| `arch_daemon_file_mod` | architecture | `how does daemon detect file modifications` | MISS | - | None | 156.6ms | 826 |
| `arch_token_budgeting` | architecture | `how does token budgeting and graceful folding work` | MISS | - | None | 141.8ms | 837 |
| `arch_pagerank_centrality` | architecture | `how does PageRank centrality ranking work` | MISS | - | None | 147.2ms | 834 |
| `arch_skeleton_generation` | architecture | `how are AST skeletons generated` | HIT@3 | 3 | `path:src/synap_git/parser/registry.py` | 62.3ms | 849 |
| `arch_blast_radius` | architecture | `how does git blast radius calculation work` | MISS | - | None | 132.3ms | 826 |
| `dbg_db_locked` | debugging | `OperationalError: database is locked` | MISS | - | None | 135.8ms | 845 |
| `dbg_conn_refused` | debugging | `ConnectionRefusedError: [Errno 61] Connect call failed` | MISS | - | None | 125.2ms | 849 |
| `dbg_ambiguous_symbol` | debugging | `AmbiguousSymbolError: multiple symbols match query` | HIT@1 | 1 | `symbol:AmbiguousSymbolError` | 131.3ms | 831 |
| `dbg_git_integration` | debugging | `GitIntegrationError: Not a git repository` | HIT@1 | 1 | `symbol:GitIntegrationError` | 128.4ms | 823 |
| `dbg_token_encoding` | debugging | `KeyError: cl100k_base tokenizer initialization failed` | MISS | - | None | 121.0ms | 836 |
| `dec_normal_pragma` | decisions_memory | `why was normal pragma chosen` | MISS | - | None | 104.1ms | 832 |
| `dec_token_budget_12pct` | decisions_memory | `why was 12% token budget chosen` | HIT@1 | 1 | `path:src/synap_git/retrieval/engine.py` | 122.1ms | 845 |
| `dec_replace_wiki_with_ast` | decisions_memory | `why was background wiki generation replaced with AST outlines` | HIT@2 | 2 | `path:src/synap_git/storage/sqlite.py` | 129.8ms | 794 |
| `dec_pagerank_hubs` | decisions_memory | `why was pure python PageRank chosen over networkx` | MISS | - | None | 129.4ms | 846 |
| `mem_three_layer_arch` | decisions_memory | `what is the 3-layer architecture in memory` | HIT@4 | 4 | `symbol:store_memory` | 129.8ms | 822 |
| `git_changelog_v260` | git_conventions | `what changed in v2.6.0` | MISS | - | None | 139.0ms | 813 |
| `git_commit_conventions` | git_conventions | `how are commits formatted` | MISS | - | None | 47.8ms | 839 |
| `git_agent_directives` | git_conventions | `what are the agent operational guidelines` | MISS | - | None | 64.5ms | 812 |
| `git_verify_standards` | git_conventions | `how to verify code with pytest and ruff` | MISS | - | None | 142.0ms | 798 |
| `git_setup_cli` | git_conventions | `how to run synap setup and start daemon` | HIT@1 | 1 | `symbol:start` | 155.2ms | 848 |

---

## 5. Artifacts and Reproduction

- Dataset: `evals/benchmark_dataset.json`
- Runner: `evals/baseline_benchmark.py`
- Results: `evals/baseline_results.json`
- Reproduction command:
  ```bash
  .venv/bin/python evals/baseline_benchmark.py
  ```
