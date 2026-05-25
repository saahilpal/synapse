# Architecture

Synapse is a layered local runtime. Its central invariant is simple: **durable cognition is append-only, provenance-aware, temporally valid, and tied to Git history**.

## System Layers

```mermaid
flowchart TD
    subgraph Interface
        CLI[Typer CLI]
        REST[FastAPI REST API]
        WS[WebSocket events]
        MCP[MCP server]
        TUI[Textual dashboard]
    end

    subgraph Runtime
        Daemon[Runtime daemon]
        Queue[asyncio event queue]
        Scheduler[APScheduler jobs]
        Extract[Perception and extraction]
        Evolution[Cognitive Evolution Engine]
        Timeline[Timeline engine]
        Assumptions[Assumption engine]
        Drift[Drift timelines]
        Trust[Trust and confidence]
    end

    subgraph Storage
        SQLite[(SQLite WAL)]
        ObjectStore[Content-addressed objects]
        Graph[NetworkX graph projection]
        Vector[Semantic retrieval index]
        Snapshots[Snapshot cache]
    end

    subgraph Inputs
        Git[GitPython]
        Watchdog[Watchdog]
        Markdown[markdown-it-py]
        Treesitter[Tree-sitter]
        Notes[Manual notes]
    end

    CLI --> Daemon
    REST --> Daemon
    WS --> Daemon
    MCP --> Daemon
    TUI --> REST
    Git --> Queue
    Watchdog --> Queue
    Markdown --> Extract
    Treesitter --> Extract
    Notes --> Queue
    Queue --> Extract
    Extract --> Trust
    Trust --> Evolution
    Scheduler --> Drift
    Evolution --> Timeline
    Evolution --> Assumptions
    Evolution --> SQLite
    Evolution --> ObjectStore
    Evolution --> Graph
    Evolution --> Vector
    Evolution --> Snapshots
```

## Core Data Flow

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant Git as Git repository
    participant Daemon as Synapse daemon
    participant Extractor as Extraction pipeline
    participant Evolution as Cognitive Evolution Engine
    participant Store as Event store
    participant DAG as Temporal Context DAG
    participant Projection as Derived projections
    participant Agent as AI agent via MCP

    Dev->>Git: commit, revert, checkout, merge
    Git->>Daemon: lightweight Git event
    Daemon->>Extractor: enqueue semantic processing
    Extractor->>Extractor: parse, score, extract, validate
    Extractor->>Evolution: semantic observations
    Evolution->>Store: append EventRecord
    Evolution->>DAG: create ContextObject delta
    Evolution->>Evolution: semantic diff, lineage, confidence(t)
    DAG->>Projection: update active projections
    Agent->>Daemon: query current context
    Daemon-->>Agent: scoped, provenance-aware context
```

## Source Of Truth

The source of truth is the combination of:

- append-only `EventRecord` rows in SQLite;
- immutable content-addressed cognition objects;
- Context DAG lineage;
- Git commit references and provenance records.

Graph and retrieval indexes are derived views. Snapshots are acceleration artifacts. They may be rebuilt from events and objects.

## Bounded Contexts

- **Runtime:** process lifecycle, queues, scheduling, daemon mode.
- **Cognition:** extraction, semantic objects, relevance, confidence, compression, drift.
- **Evolution:** semantic diffs, timelines, assumption invalidation, confidence evolution, branch divergence, cognitive replay.
- **Replay:** deterministic reconstruction, replay diagnostics, lineage reconstruction, checkpoint-aware state hashes.
- **Transactions:** journaled event/object/context writes and interrupted transaction recovery.
- **Lineage:** `git fsck`-style validation for cognition DAG ancestry and active heads.
- **Storage:** SQLite, object store, graph projections, semantic retrieval indexes, snapshots.
- **Git:** commit linkage, branch cognition, rollback, merge semantics.
- **MCP/API:** controlled exposure to tools and agents.
- **Security:** trust model, permissions, context poisoning protection.

## Runtime Modes

- `idle`: watches for cheap events and serves context.
- `active`: processes recent commits and documentation updates.
- `indexing`: performs deeper AST and semantic enrichment.
- `low-power`: defers heavy embedding and graph compaction work.
- `replay`: reconstructs state deterministically from event history.

## Consistency Invariants

- Event processing must be idempotent.
- Context objects are immutable.
- Context DAG edges are never rewritten; supersession is represented by new events.
- Every durable semantic fact has provenance and confidence.
- Every durable semantic fact has temporal validity and can participate in confidence(t).
- Retrieval indexes never decide truth.
- Branch merges that affect cognition must surface conflicts explicitly.
- Replay, lineage verification, and transaction journals must agree before derived projections are trusted.

## Failure Model

Synapse assumes local process crashes, interrupted indexing, Git history rewrites, stale docs, conflicting branch facts, corrupted cache files, and malicious or low-trust notes. Recovery is replay-first: rebuild derived state from the event store and object store, then invalidate any cache that cannot prove its state hash.
