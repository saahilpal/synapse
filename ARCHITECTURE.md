# Synapse Architecture

Synapse is a **persistent structural context infrastructure** designed specifically for AI coding agents.

Unlike traditional RAG (Retrieval-Augmented Generation) systems that rely on naive text chunking and vector similarity, Synapse treats the codebase as a deterministically bounded structural graph. It maps packages, modules, classes, and functions, and records their evolution over time using an event-sourced architecture.

## System Overview

Synapse does **not** use AI to define structural truth. Parsers, Git state, content hashes, SQLite transactions, and object-store integrity checks own the durable state. AI providers may optionally summarize, annotate, and explain already extracted context through **semantic overlays**.

```mermaid
architecture-beta
    group source(Source)
    service repo(Local Repository) in source
    
    group synapse(Synapse Core Engine)
    service scanner(Incremental Scanner) in synapse
    service parser(AST & Markdown Parser) in synapse
    service engine(Transaction Engine) in synapse
    service retrieve(Hybrid Retrieval) in synapse
    
    group storage(Durable State)
    service sqlite(SQLite WAL Event Store) in storage
    service objstore(Zlib Object Store) in storage

    group interface(Interfaces)
    service mcp(MCP Server) in interface
    service api(FastAPI) in interface
    service cli(Typer CLI) in interface
    
    repo:R --> L:scanner
    scanner:R --> L:parser
    parser:B --> T:engine
    
    engine:R --> L:sqlite
    engine:R --> L:objstore
    
    retrieve:L --> R:sqlite
    retrieve:L --> R:objstore
    
    retrieve:B --> T:mcp
    retrieve:B --> T:api
    retrieve:B --> T:cli
```

*(Note: The diagram above illustrates logical data flow. The actual implementation runs within a unified Python runtime.)*

---

## 1. Incremental Ingestion Pipeline

The ingestion pipeline transforms raw repository files into versioned structural context. It is designed to be incremental, bounded, and fast.

```mermaid
sequenceDiagram
    participant Repo as Local Repository
    participant Scan as RepositoryScanner
    participant Parse as ContextBuilder
    participant Store as EventStore & ObjectStore
    
    Repo->>Scan: File System Events / Poll
    Scan->>Scan: Deterministic exclusions & bounds check
    Scan->>Scan: Compute SHA-256 content hash
    Scan->>Parse: Yield changed/added files
    
    Parse->>Parse: Parse AST (Classes, Functions, Imports)
    Parse->>Parse: Identify file renames via hash matching
    
    alt If structural node modified
        Parse->>Parse: Invalidate stale node
        Parse->>Parse: Invalidate attached semantic overlays
    end
    
    Parse->>Store: Write Event Journal
    Parse->>Store: Write msgpack Objects
    Store-->>Parse: Commit success
```

### Core Responsibilities
- **`RepositoryScanner`**: Walks the repository applying deterministic exclusions (e.g., ignoring binaries, overly large files, hidden directories) and computes SHA-256 hashes.
- **Renames & Moves**: Handled by matching deleted and added files with identical content hashes.
- **Invalidation**: Modified files immediately invalidate their structural nodes, parsed symbols, and attached semantic overlays.

---

## 2. Structural Extraction & The Context Graph

Synapse maintains a purposely constrained structural graph. It does not track variables, per-line AST nodes, or speculative reasoning.

**Nodes Tracked:**
- Packages and module boundaries
- Files and Documents (Markdown)
- Classes and Functions
- Import Dependencies

By bounding the graph, Synapse avoids graph explosion and ensures retrieval queries return high-signal context.

---

## 3. Durable Storage Layer

The storage layer guarantees local-first reliability using a two-part system:

1. **`ObjectStore`**: Immutable `msgpack` objects compressed with `zlib` and addressed by their SHA-256 hash.
2. **`SQLiteEventStore`**: WAL-enabled SQLite tables tracking events, context commits, active heads, structural nodes/edges, and semantic projections.

```mermaid
erDiagram
    COMMIT ||--o{ EVENT : "contains"
    EVENT ||--|| NODE : "mutates"
    NODE ||--o{ EDGE : "connects to"
    NODE ||--o{ OVERLAY : "annotated by"
    
    COMMIT {
        string id PK
        string parent_id FK
        datetime timestamp
    }
    NODE {
        string id PK
        string kind
        string file_path
        string hash
    }
    OVERLAY {
        string id PK
        string node_id FK
        string summary
        boolean valid
    }
```

Context writes are orchestrated by the `ContextTransactionEngine`, which journals event payloads. If an ingestion cycle is interrupted, the transaction fails atomically, and replay diagnostics (`synapse doctor`) maintain integrity.

---

## 4. Hybrid Retrieval Flow

When an agent or developer requests context, Synapse executes a bounded, four-stage hybrid retrieval pipeline.

```mermaid
flowchart TD
    Req[Context Request] --> TFilter[1. Temporal Filtering]
    
    subgraph Pipeline
    TFilter -->|Active Head| STraverse[2. Structural Traversal]
    STraverse -->|Bounded Nodes| SRecall[3. Semantic Recall]
    SRecall -->|Ranked Nodes| LLMSynth[4. LLM Synthesis]
    end
    
    LLMSynth --> Resp[Agent Context Window]
    
    classDef step fill:#1e293b,stroke:#8b5cf6,stroke-width:2px;
    class TFilter,STraverse,SRecall,LLMSynth step;
```

1. **Temporal Filtering**: Reconstructs the active context at a chosen context head (ignoring stale or deleted nodes).
2. **Structural Traversal**: Finds matching nodes based on query parameters and expands through nearby dependency edges (up to a hard node limit).
3. **Semantic Recall**: Uses keyword and local embedding similarity to rank active semantic objects.
4. **LLM Synthesis** *(Optional)*: Synthesizes a natural language answer from the packed, cited context only, avoiding hallucination.

---

## 5. Semantic Overlays

Semantic overlays are non-destructive AI annotations attached to structural nodes. They provide human-readable summaries or developer notes. 

**Crucial Invariant**: Overlays cannot mutate structural nodes or create dependencies. If the underlying code is modified, the overlay is automatically invalidated by the ingestion pipeline until it is re-generated.

---

## 6. Runtime & Agent Interfaces

Synapse exposes its engine through several interfaces:
- **Typer CLI**: `init`, `status`, `search`, `rollback`, `doctor`.
- **FastAPI**: REST endpoints for context status, timelines, and raw projections.
- **Context UI**: A lightweight D3-based visualizer for the context graph and historical timeline.
- **SynapseMCPFacade**: Implementation of the Model Context Protocol (MCP). Exposes tools to agents (e.g., `get_current_context`, `search_context`, `explain_structure`).
