# RFC Process

RFCs are used for substantial changes to Synapse architecture, storage, security, interfaces, cognition semantics, or operational behavior.

## Lifecycle

```mermaid
flowchart LR
    Draft[Draft RFC]
    Discuss[Discussion]
    Revise[Revision]
    Accept[Accepted]
    Implement[Implementation]
    ADR[ADR if durable]

    Draft --> Discuss --> Revise --> Accept --> Implement --> ADR
```

## When To Write An RFC

- New storage backend.
- Event schema family changes.
- MCP tool capability changes.
- Trust or permission model changes.
- New memory lifecycle policy.
- Significant user workflow changes.

## Outcome

Accepted RFCs guide implementation. If the decision becomes a durable architectural constraint, create or update an ADR.

