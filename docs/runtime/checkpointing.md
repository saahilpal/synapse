# Checkpointing

## Purpose

Checkpointing creates compact snapshots of derived cognition state so startup and replay are fast without making snapshots the source of truth.

## Architecture

```mermaid
flowchart LR
    Head[Context head]
    Projections[Derived projections]
    Snapshot[Snapshot object]
    Verify[Hash verification]
    ReplayTail[Replay tail events]

    Head --> Projections --> Snapshot --> Verify --> ReplayTail
```

## Lifecycle

Checkpoints are created after stable context heads, verified before use, and invalidated when schema versions or object hashes do not match.

## Responsibilities

- Capture DAG head and projection state hashes.
- Store compact replay accelerators.
- Verify snapshot integrity.
- Support schema versioning.
- Delete unsafe or stale checkpoints.

## Data Flow

Snapshots summarize derived state and point back to event IDs and context object hashes.

## Failure Modes

- Snapshot becomes treated as canonical.
- Checkpoint misses unflushed events.
- Schema migration loads incompatible snapshot.
- Corrupted snapshot produces silent wrong context.

## Edge Cases

- User rolls back before latest snapshot.
- Branch-specific snapshot exists.
- Compaction runs while checkpoint is being written.
- Disk cleanup removes old snapshots.

## Scalability Notes

Keep snapshots periodic and bounded. Use retention policies by branch and recency.

## Security Notes

Snapshots may contain sensitive derived facts and require the same local protection as primary stores.

## Performance Considerations

Write snapshots atomically and compress only when it does not compete with active indexing.

## Future Extensibility

Add remote snapshot sharing only after trust, signing, and redaction policies are mature.

