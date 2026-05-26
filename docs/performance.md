# Performance

Synapse is engineered for high-performance indexing and low-latency retrieval, even on massive monorepos.

## Indexing Performance

Indexing is divided into two phases:
1.  **Fast Scan:** We use content hashes (SHA-256) to identify changed files. On a repo with 10,000 files, this takes < 200ms.
2.  **Deterministic Parsing:** Changed files are parsed using Tree-sitter. This is an O(N) operation where N is the file size. Most source files parse in < 10ms.

## Retrieval Latency

Retrieval is optimized via SQLite:
- **Lexical Search:** Uses SQLite FTS5 for sub-millisecond keyword lookups.
- **Structural Expansion:** Uses Recursive CTEs to traverse the dependency graph in the database, avoiding expensive O(N) traversals in Python memory.
- **Semantic Recall:** Reranking is performed only on the top-scored candidates from the lexical and structural stages, ensuring total latency remains under 200ms.

## Resource Constraints

- **Memory:** Synapse maintains a minimal footprint by keeping the graph in SQLite rather than in-memory Python objects.
- **CPU:** High bursts are only expected during the initial `synapse init` or a large rebase.
