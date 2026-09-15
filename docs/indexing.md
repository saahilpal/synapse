# Deterministic Indexing Architecture

Synap indexes repository structure deterministically using a decoupled two-path architecture designed to provide sub-second incremental updates while scaling to 100k+ file monorepos.

---

## The Two-Path Design

To balance deep initial graph extraction with minimal CPU and I/O overhead during development, Synap splits indexing into two distinct paths:

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
Invoked on `synap init` or when forced via `synap index --force`:
* **Scanner Discovery:** Traverses the repository tree, honoring `.gitignore` rules and built-in exclusions (`.git`, `.synap`, `.venv`, `node_modules`, `dist`, `build`, `target`, `.next`, `vendor`).
* **Process-Pool Concurrency:** Uses `ProcessPoolExecutor` to parse codebase ASTs concurrently across all CPU cores, processing files in chunks (500 files per chunk).
* **Pass 1 (AST Symbol Extraction):** Runs language-specific Tree-sitter grammars to extract symbols (classes, functions, methods, interfaces, modules). Generates stable, deterministic identifiers:
  $$\text{stable\_id} = \text{sha256}(\text{path} + \text{name} + \text{kind} + \text{start\_line})$$
* **Pass 2 (Bulk Edge Resolution):** Resolves imports and links dependency edges (`depends_on`, caller/callee, class inheritance) between symbols. Queries and inserts are batched in single SQLite transactions.
* **Wiki Enqueuing:** Places files and project synthesis summaries (`overview.md`, `architecture.md`, `schema.md`) into `wiki_queue`.

### 2. Incremental Indexing (`_incremental_index`)
Triggered automatically by the daemon or manually via `synap sync`:
* **Git Delta Isolation:** Executes Git diffing between commits:
  ```bash
  git diff-tree -r --no-commit-id --name-status <prev_commit> <current_commit>
  ```
  Immediately isolates added (`A`), modified (`M`), deleted (`D`), or renamed (`R`) files.
* **Selective AST Updates:** Only modified or added files are parsed. Old symbols and stale edges belonging to modified or removed files are pruned within a single atomic SQLite transaction.
* **Incremental Edge Relinking:** Dependency edges are recalculated strictly for symbols affected by the changed files, preserving the rest of the graph structure untouched.

---

## Supported Language Grammars

Synap integrates Tree-sitter parsers covering 25+ programming and configuration languages:

| Language | File Extensions | Extracted Symbol Types |
| :--- | :--- | :--- |
| **Python** | `.py` | Classes, functions, methods, imports |
| **TypeScript / JavaScript** | `.ts`, `.tsx`, `.js`, `.jsx` | Classes, functions, methods, interfaces, types, imports |
| **Rust** | `.rs` | Structs, enums, traits, functions, impl blocks, modules |
| **Go** | `.go` | Structs, interfaces, functions, methods, package imports |
| **C / C++** | `.c`, `.h`, `.cpp`, `.hpp`, `.cc` | Functions, structs, classes, namespaces, headers |
| **Java** | `.java` | Classes, interfaces, methods, imports |
| **C#** | `.cs` | Classes, interfaces, methods, namespaces |
| **Ruby** | `.rb` | Classes, modules, methods |
| **PHP** | `.php` | Classes, interfaces, functions, methods |
| **Swift** | `.swift` | Classes, structs, protocols, functions |
| **Kotlin / Scala** | `.kt`, `.kts`, `.scala` | Classes, objects, functions, traits |
| **Shell / Bash** | `.sh`, `.bash` | Functions |
| **SQL** | `.sql` | Tables, procedures, views |
| **Configuration / Data** | `.json`, `.toml`, `.yaml`, `.yml` | Document structure and top-level keys |

---

## Graph Edges & Relationships

The structural graph records relational bonds between code nodes:
* `depends_on` / `imports`: File-to-file and module-to-module dependencies.
* `calls`: Function/method caller-to-callee invocations.
* `inherits`: Class and interface inheritance hierarchies.
* `contains`: File-to-symbol and class-to-method ownership.

---

## Exclusions & Safety Controls

1. **GitIgnore Specifications:** Follows `.gitignore` rules recursively using an exact glob-to-regex matcher.
2. **Binary File Filtering:**
   - Extension blocklist (executables, archives, binaries, media).
   - Control character ratio check: Inspects the first 1KB of content. If control bytes exceed 10%, the file is skipped as binary.
3. **Size Limits:** Files exceeding `max_file_bytes` (default 1,000,000 bytes) are ignored to protect memory limits.

---

## SQLite Performance & Concurrency

* **WAL Mode:** Initialized with `PRAGMA journal_mode = WAL` and `PRAGMA synchronous = NORMAL`, allowing concurrent reader threads without write blocking.
* **FTS5 Full-Text Search:** Virtual table `symbols_fts` powers sub-millisecond lexical queries across symbol names and signatures.
* **Module Key Resolution:** Pre-computes and indexes dot-separated `module_key` lookups (e.g. `synap_git.indexer.scanner`) for $O(1)$ dependency graph traversal.
