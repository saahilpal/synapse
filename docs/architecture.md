# Synapse Architecture & Storage Internals

This document details the low-level database schema, table structures, and graph query implementation for Synapse.

---

## Database Schema

All indexing, memory, and tracing metrics are persisted under `.synap/synap.db` in SQLite WAL mode.

### 1. `files`
Tracks file paths, git blob hashes, and module representations.
```sql
CREATE TABLE files (
    file_id      TEXT PRIMARY KEY,  -- sha256(path + content_hash)
    path         TEXT UNIQUE,       -- repository-relative file path
    git_oid      TEXT,              -- git blob object identifier
    content_hash TEXT,              -- sha256 hash of file content
    language     TEXT,              -- parsed programming language name
    module_key   TEXT,              -- dot-separated module representation
    updated_at   TEXT               -- ISO-8601 timestamp string
);
```

### 2. `symbols`
Stores parsed AST symbols (classes, functions, methods, variables).
```sql
CREATE TABLE symbols (
    symbol_id    TEXT PRIMARY KEY,  -- stable symbol hash identifier
    file_id      TEXT,              -- foreign key referencing files.file_id
    name         TEXT,              -- symbol token identifier name
    kind         TEXT,              -- symbol type: 'function', 'class', etc.
    start_line   INTEGER,           -- 1-based source code line start
    end_line     INTEGER,           -- 1-based source code line end
    ast_hash     TEXT,              -- structural AST hash for delta detection
    metadata_json TEXT              -- serialized attributes & docstrings
);
```

### 3. `edges`
Directed dependencies representing imports, calls, and inheritance.
```sql
CREATE TABLE edges (
    edge_id       TEXT PRIMARY KEY,
    source_symbol TEXT,             -- calling symbol id
    target_symbol TEXT,             -- called symbol id
    edge_type     TEXT              -- 'calls', 'imports', 'inherits'
);
```

### 4. `checkpoints`
Behavioral memory checkpoints capturing agent state and thought processes.
```sql
CREATE TABLE checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    branch        TEXT,
    commit_hash   TEXT,
    doing         TEXT,
    changed_files TEXT,             -- JSON array of file paths
    next_step     TEXT,
    blockers      TEXT,
    created_at    TEXT
);
```

### 5. `lessons`
Negative constraints and post-revert learnings to prevent regression loops.
```sql
CREATE TABLE lessons (
    lesson_id   TEXT PRIMARY KEY,
    revert_hash TEXT,
    what_failed TEXT,
    why_failed  TEXT,
    status      TEXT,               -- 'pending' or 'approved'
    created_at  TEXT
);
```

---

## Directed Graph Traversal (Recursive CTE)

Graph neighborhoods (callers, callees, dependencies) are traversed purely on the database engine using SQLite recursive Common Table Expressions:

```sql
WITH RECURSIVE neighborhood(id, d) AS (
    SELECT :symbol_id AS id, 0 AS d
    UNION
    SELECT target_symbol, d + 1
    FROM edges
    JOIN neighborhood ON source_symbol = id
    WHERE d < :depth
)
SELECT s.*, f.path AS source_path, MIN(n.d) AS distance
FROM symbols s
JOIN files f ON s.file_id = f.file_id
JOIN neighborhood n ON s.symbol_id = n.id
GROUP BY s.symbol_id
ORDER BY distance ASC
LIMIT :max_neighbors;
```
