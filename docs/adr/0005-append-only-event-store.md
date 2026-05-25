# ADR 0005: Append-Only Event Store

## Status

Accepted.

## Context

Synapse must support rollback, replay, debugging, auditability, and deterministic recovery after crashes.

## Decision

Use an append-only event store as the durable history of observed and processed cognitive changes.

```mermaid
flowchart LR
    Input[Observed input]
    Event[Append event]
    Object[Create context object]
    Replay[Replay]
    Input --> Event --> Object --> Replay
```

## Consequences

- History is auditable and replayable.
- Corrections are represented as new events.
- Storage growth must be managed through compaction and snapshots.
- Event schema migrations require compatibility discipline.

## Alternatives Considered

- Mutable current-state tables only: rejected because rollback and audit would be weak.
- Full snapshot per commit: rejected because it wastes storage and hides causality.

