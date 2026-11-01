# Synapse System Architecture Overview

**Document Version:** 2.5.0
**Status:** Authoritative
**Target Platform:** Python 3.12+ / SQLite 3.35+ / FastMCP

---

## 1. High-Level Architecture

Synapse is a local, Git-aware structural context engine for AI coding agents. It extracts code syntax trees, resolves import and caller graphs, tracks commit lineage, and maintains persistent behavioral memory without relying on cloud services.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        AI Coding Agent (Client)                        │
│             (Cursor, Claude Code, Windsurf, Cline, Aider)              │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ FastMCP Protocol (Stdio)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                          FastMCP Server Layer                          │
│   - Session Preamble (Branch, Checkpoint, Rules, Hubs, Diff Ranges)    │
│   - Navigation: search, read_symbol, get_outline, get_neighborhood     │
│   - Verification: get_diff, get_test_recommendations                   │
│   - Cognitive Memory: create_checkpoint, remember, recall              │
└───────────────────┬────────────────────────────────┬───────────────────┘
                    │                                │
                    ▼                                ▼
┌──────────────────────────────────────┐ ┌───────────────────────────────┐
│       Hybrid Retrieval Engine        │ │     Git Intelligence Layer    │
│   - Fast Intent Classification       │ │   - Inode mtime Fingerprint   │
│   - Code-Case Sub-Tokenization       │ │   - Worktree / Commondir Map  │
│   - Proportional Token Packing       │ │   - Dirty Diff -U0 Slices     │
│   - Mode A Grounded Fallback         │ │   - In-Progress State Guards  │
└───────────────────┬──────────────────┘ └───────────────┬───────────────┘
                    │                                    │
                    ▼                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        Deterministic Storage Engine                    │
│   - SQLite WAL Mode (PRAGMA synchronous = NORMAL, busy_timeout = 30s)  │
│   - Covering Indexes (idx_edges_src_tgt, idx_edges_tgt_src)            │
│   - Recursive CTE Neighborhood Queries (< 0.2ms traversal)             │
│   - Virtual Table FTS5 BM25 with Prefix Matching                       │
│   - Contiguous CSR Personalized PageRank Hub Detection                 │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. The 3-Layer Context Infrastructure

Synapse organizes repository context into three distinct operational layers:

### L1 — Structural Code Graph (AST Traversal)
- Powered by Tree-sitter parsers across Python, TypeScript, JavaScript, Rust, Go, C/C++, and Java.
- Extracts symbols (functions, classes, methods, interfaces, types) and resolves caller/callee relationships and import dependencies.
- Produces deterministic, line-numbered code slices and AST skeletons with method bodies pruned (80–90% token reduction).

### L2 — Semantic Wiki (Asynchronous Summarization)
- Maintains compact markdown summaries of modules, directories, and files.
- Operates via an asynchronous queue (`wiki_queue`) using atomic SQLite `UPDATE ... RETURNING *` dequeue operations.
- Keeps wiki pages strictly synchronized with Git commit hashes.

### L3 — Behavioral Memory & Cognitive Constraints
- **Checkpoints:** Episodic task snapshots (`doing`, `changed_files`, `next_step`, `blockers`) tied to branches and commit hashes.
- **Decisions:** Persistent log of architectural choices with context rationale.
- **Approved Lessons:** Human-approved negative constraints extracted from automated revert commits (`git revert`).
- **Operational Memory:** Key-value environment facts and developer directives.

---

## 3. Storage Architecture: Two-Tier Storage Target

To eliminate single-point-of-failure risks where index cache corruption could wipe irreplaceable human-approved lessons, Synapse separates storage into two distinct lifecycles:

```
┌──────────────────────────────────────┐  ┌──────────────────────────────────────┐
│           synap_graph.db             │  │           synap_memory.db            │
│      (Derived Disposable Cache)      │  │        (Irreplaceable Truth)         │
├──────────────────────────────────────┤  ├──────────────────────────────────────┤
│ - files                              │  │ - checkpoints                        │
│ - symbols                            │  │ - decisions                          │
│ - edges                              │  │ - lessons                            │
│ - symbols_fts (FTS5)                 │  │ - agent_memory                       │
│ - embeddings                         │  │ - activity                           │
│                                      │  │                                      │
│ Reconstructible from Git at any time │  │ Never unlinked or wiped on recovery  │
└──────────────────────────────────────┘  └──────────────────────────────────────┘
```

---

## 4. Concurrency & Safety Controls

1. **Write-Ahead Logging (WAL Mode):**
   - All connections enable `PRAGMA journal_mode = WAL` and `PRAGMA synchronous = NORMAL`.
   - Concurrent readers execute simultaneously without blocking writes.
   - Long-running read transactions use `PRAGMA query_only = ON`.
2. **Advisory Kernel Locking:**
   - Background daemons acquire `fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)` on `.synap/daemon.pid`.
   - Eliminates stale PID recycling lockouts and dual-daemon race conditions.
3. **Atomic Task Dequeuing:**
   - Multi-worker queue consumption uses atomic `UPDATE ... RETURNING *` inside `BEGIN IMMEDIATE` transactions, preventing duplicate processing across workers.
4. **Git In-Progress Operations Protection:**
   - Indexing is automatically suspended during active merge conflicts (`MERGE_HEAD`), rebases (`rebase-merge`), or bisect operations to prevent corrupted syntax from entering the code graph.
