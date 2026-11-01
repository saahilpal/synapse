# Synapse Research, Benchmarks & Literature Review

**Document Version:** 2.5.0
**Authors:** Synapse Engineering & Context Research Team
**Evaluation Target:** Production Repositories (1k to 50k files)

---

## 1. Literature Grounding & Architectural Precedents

Synapse's context design is grounded in contemporary peer-reviewed research and production developer infrastructure:

### 1.1 Sourcegraph SCIP (Structured Code Intelligence Protocol)
- **Concept:** SCIP defines a language-agnostic protocol for indexing symbol definitions, references, and documentation into deterministic local files.
- **Synapse Adoption:** Rather than running heavyweight language servers in memory during agent sessions, Synapse pre-indexes AST symbols and edges into SQLite covering indexes. Lookups resolve in $< 0.5\text{ms}$ with zero runtime LSP overhead.

### 1.2 Aider Repository Maps
- **Concept:** Aider demonstrates that presenting an AI model with a compressed structural map of the repository (function signatures, classes, docstrings) yields higher code generation accuracy than dumping raw file contents.
- **Synapse Adoption:** Synapse provides `get_skeleton(file_path)` and Tier-2 file skeletons in hybrid retrieval, achieving an **80–90% token reduction** while preserving types, signatures, and docstrings.

### 1.3 RepoCoder (Iterative Context Retrieval)
- **Concept:** Zhang et al. (2023) demonstrated that iterative retrieval combining lexical queries with semantic similarity and previous model outputs significantly outperforms single-pass retrieval.
- **Synapse Adoption:** Synapse uses Reciprocal Rank Fusion (RRF) across BM25 lexical search, vector similarity, and Recursive CTE graph neighborhood expansion.

### 1.4 CrossCodeEval (Cross-File Dependency Grounding)
- **Concept:** Ding et al. (2023) showed that code generation accuracy degrades severely when agents cannot see cross-file caller and callee definitions.
- **Synapse Adoption:** Directed bidirectional traversal in SQLite (`get_neighborhood`, `get_blast_radius`) provides grounded caller blast radius before agents modify symbols.

---

## 2. Empirical Performance Benchmarks

The following benchmarks were measured locally on an Apple Silicon M-series system running Python 3.12 with SQLite 3.35+:

| Subsystem / Operation | Synapse Legacy | Synapse v2.5.0 | Measured Speedup | Technique |
| :--- | :---: | :---: | :---: | :--- |
| **2-Hop Directed Neighborhood** | 38.6ms | **0.20ms** | **193x** | SQLite Recursive CTE with covering index |
| **Batch Graph Expansion (50 seeds)**| 23.7ms | **0.10ms** | **237x** | Single SQL query replacing serial roundtrips |
| **FTS5 Lexical Search Pushdown** | 0.86ms | **0.32ms** | **2.69x** | FTS5 prefix match (`name:"query"*`) |
| **Git Inode Fingerprint Validation** | 2.15ms | **0.05ms** | **43x** | `stat().st_mtime` on HEAD/index/refs |
| **AST Skeletonization (Cached)** | 1.20ms | **0.001ms** | **1,000x** | `lru_cache` keyed by file content hash |
| **Personalized PageRank (20k nodes)**| 1,200ms | **170ms** | **7x** | Contiguous CSR array indexing |
| **Zero-Change Incremental Polling** | 185ms | **14ms** | **13x** | Short-circuit commit check |

---

## 3. Retrieval Accuracy & Token Economics

### Token Savings Breakdown
- **Full File Read vs. AST Skeleton:**
  - Standard 500-line file: ~3,200 tokens.
  - Synapse AST Skeleton: ~380 tokens (**88.1% token savings**).
- **Blast Radius Caller Tracing vs. Full Grep:**
  - Full repo text search output: ~8,000 tokens.
  - Synapse Blast Radius: ~450 tokens (**94.3% token savings**).

### Mode A (Zero-LLM Grounding)
Synapse's retrieval engine operates in 100% free **Mode A** when no LLM provider is configured:
1. Evaluates user query intent (conceptual vs. structural vs. logic).
2. Performs BM25 lexical token matching and expands the graph to structural neighbors.
3. Packs numbered line slices and skeletons into exact token budgets.
4. Returns cleanly formatted, line-numbered code blocks directly to the agent without external network calls.
