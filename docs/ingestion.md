# Ingestion Pipeline

Ingestion is the process of transforming raw repository files into durable, versioned structural context. Synapse approaches this with a strict focus on determinism and boundaries.

## The Ingestion Flow

```mermaid
flowchart LR
    Scan[Scanner] --> Hash[File Content Hashes]
    Hash --> Parse[AST / Markdown Parsing]
    Parse --> Delta[Context Deltas]
    Delta --> Txn[Event Transaction]
    Txn --> Store[(SQLite + Object Store)]
    
    classDef step fill:#1e293b,stroke:#8b5cf6,stroke-width:2px;
    class Scan,Hash,Parse,Delta,Txn,Store step;
```

## Core Principles

### 1. Deterministic Exclusion
Synapse automatically filters out noise. It excludes `.git`, `.synapse`, virtual environments, build outputs (e.g., `dist/`, `target/`), and dependency directories. Files exceeding a configurable `max_file_bytes` threshold are also safely skipped to prevent runaway memory allocation during parsing.

### 2. Hash-Driven Incremental Updates
Every ingested file is hashed via SHA-256. 
- When the daemon runs, it only parses files whose content hashes have changed.
- **Rename Detection**: If a file is deleted and a new file is added with the exact same content hash, Synapse records a deterministic `MoveEvent` rather than destroying and recreating the subgraph.

### 3. Strict Structural Boundaries
Synapse does not parse everything. To avoid graph explosion and maintain high-signal retrieval, the index intentionally tracks only:
- Packages and Modules
- Markdown Documents
- Classes and Functions
- Import Dependencies

*It specifically ignores variables, local expressions, tokens, and execution paths.*

### 4. Cascade Invalidation
Because Synapse uses an event-sourced append-only log, it handles modifications through **invalidation**.
When a file changes, Synapse appends records that invalidate:
- The old file node
- Previously parsed child symbols (classes, functions)
- Connected dependency edges
- Any AI-generated **Semantic Overlays** targeting those objects

This guarantees that an AI agent never receives stale structural information.
