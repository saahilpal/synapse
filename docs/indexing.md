# Deterministic Indexing Architecture

Synap indexes code structure deterministically using a decoupled two-path indexing architecture.

---

## The Two-Path Design

To scale across large repositories without introducing high CPU or disk I/O overhead, Synap splits indexing into two dedicated execution paths: first-run and incremental.

```
                  ┌──────────────────────────────┐
                  │      Git State Check         │
                  └──────────────┬───────────────┘
                                 │
                   Is first run? / Rebuild forced?
                   ┌─────────────┴─────────────┐
                  YES                          NO
          ┌────────▼────────┐          ┌───────▼────────┐
          │ First-Run Index │          │  Incremental   │
          │  (Full AST Scan)│          │   (Git Delta)  │
          └────────┬────────┘          └───────┬────────┘
                   │                           │
                   └─────────────┬─────────────┘
                                 ▼
                     ┌──────────────────────┐
                     │   SQLite Storage     │
                     │ (Graph, FTS5, Wiki)  │
                     └──────────────────────┘
```

### 1. First-Run Indexing (`_first_run_index`)
Invoked when initializing a repository (`synap init`) or when index rebuilding is forced.
* **Scanner Discovery:** Walks the repository tree, completely ignoring files and folders specified in `.gitignore` or default exclusions (`.venv`, `node_modules`, `dist`, etc.).
* **Process-Pool Concurrency:** Uses `ProcessPoolExecutor` to parse codebase ASTs in parallel. Work is divided into chunks (500 files per chunk) processed across all available CPU cores.
* **Pass 1 (AST Symbol Parsing):** Runs tree-sitter parsers to extract symbols (classes, functions, methods, modules). Generates stable, collision-free identifiers for symbols based on a `sha256(path + name + kind + start_line)` hash.
* **Pass 2 (Bulk Edge Resolution):** Resolves imports and links dependency edges (`depends_on`) between caller and callee modules. Grouped queries are performed in batch transactions to minimize DB connections.
* **Wiki Enqueuing:** Places files and project summaries (`overview.md`, `architecture.md`, `schema.md`) into the `wiki_queue` for asynchronous background generation.

### 2. Incremental Indexing (`_incremental_index`)
Invoked by the background daemon watcher when a Git commit or file change is detected.
* **Git Delta Detection:** Rather than reading all files, Synap executes:
  ```bash
  git diff-tree -r --no-commit-id --name-status <prev_commit> <current_commit>
  ```
  This immediately isolates added, modified, or deleted paths.
* **Selective AST Updates:** Only changed files are read and parsed by the Tree-sitter engine. Stale symbols for deleted or modified files are cleanly removed from SQLite tables.
* **Incremental Edge Resolution:** Re-resolves call and dependency edges strictly for symbols defined in changed files, preserving the rest of the graph structure.

---

## Exclusions & Controls

* **GitIgnore Spec:** Synap implements a custom glob-to-regex matcher to follow `.gitignore` specifications exactly.
* **Binary File Filtering:** Synap uses a file extension blocklist coupled with a control character ratio check (scans the first 1KB of content; if control characters exceed 10%, it is treated as binary) to bypass non-text content.
* **Size Limits:** Files exceeding `max_file_bytes` (default 1MB) are completely skipped.

---

## SQLite Optimizations

Synap applies high-throughput configurations to the SQLite indexing backend:
* **WAL Mode:** The database is initialized with `PRAGMA journal_mode=WAL` to allow concurrent readers and writers to access the database without locking.
* **Batch Inserts:** Inserts and deletes are wrapped in transaction blocks, executing symbol and edge insertions via `executemany` arrays.
* **FTS5 Integration:** Synap maintains a virtual table `symbols_fts` using SQLite FTS5 for sub-millisecond keyword symbol queries, avoiding slow wildcard `LIKE` queries.
* **Module Key Resolution:** Pre-computes and indexes a dot-separated `module_key` for every file (e.g. `src.utils.serialization`), allowing $O(1)$ module lookup.
