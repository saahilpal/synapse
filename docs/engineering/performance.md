# Performance

## Purpose

Synapse must be fast enough to run continuously on developer machines without turning cognition into a tax on normal Git workflows.

## Architecture

```mermaid
flowchart LR
    Cheap[Cheap event capture]
    Queue[Bounded async queue]
    Batch[Batching and debounce]
    Enrich[Lazy semantic enrichment]
    Index[Incremental indexes]
    Compact[Scheduled compaction]

    Cheap --> Queue --> Batch --> Enrich --> Index --> Compact
```

## Lifecycle

Performance controls start at ingestion: capture minimal events, debounce noisy filesystem changes, parse incrementally, embed selectively, and compact during idle windows.

## Responsibilities

- Keep Git hook and watcher paths lightweight.
- Avoid full repository rescans after small changes.
- Use content hashes to skip unchanged semantic units.
- Maintain hot/warm/cold memory tiers.
- Surface runtime mode and queue pressure to users.

## Data Flow

Only relevant semantic units flow into graph and vector updates. Low-value file churn produces event metadata but not durable cognition objects.

## Failure Modes

- Embedding every chunk causes memory and token blowups.
- Graph recomputation from scratch makes commits feel slow.
- Snapshot overuse hides replay bugs.
- Unbounded queues exhaust memory.

## Edge Cases

- Huge monorepos.
- Generated files.
- Vendored dependencies.
- Large Markdown specs.
- Rapid branch switching.

## Scalability Notes

The MVP optimizes for one local repository. Later scaling should add sharded indexes and external graph backends only behind stable storage ports.

## Security Notes

Performance shortcuts must not skip provenance, trust checks, or permission gates.

## Performance Considerations

Initial budgets:

- CLI status: under 200 ms after startup.
- Git event capture: under 50 ms synchronous work.
- Incremental Markdown update: proportional to changed file size.
- Replay from latest snapshot: under 5 seconds for typical projects.

## Future Extensibility

Add profiling commands under `synapse doctor` and persist anonymized local metrics only with explicit user opt-in.

