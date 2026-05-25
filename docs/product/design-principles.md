# Design Principles

## Purpose

These principles keep Synapse from drifting into a large agent framework or generic memory product.

## Architecture

```mermaid
flowchart LR
    Local[Local-first]
    Git[Git-native]
    Bounded[Bounded cognition]
    Provenance[Provenance]
    Replay[Replayability]
    Trust[Trust]

    Local --> Git --> Bounded --> Provenance --> Replay --> Trust
```

## Lifecycle

Every feature proposal should be checked against the principles before implementation and again during review.

## Responsibilities

- Optimize cognitive efficiency.
- Keep raw noise out of durable memory.
- Prefer explicit human correction over hidden inference.
- Keep source-of-truth data replayable.
- Make model providers replaceable.

## Data Flow

The runtime accepts many sources but promotes only trusted, relevant, compressed, and provenance-backed facts.

## Failure Modes

- Adding cloud-only assumptions.
- Treating embeddings as truth.
- Hiding mutations behind an agent action.
- Building orchestration features before memory correctness.

## Edge Cases

- High-value raw content that should be retained as evidence.
- Low-confidence facts that are still useful for search.
- Temporary branch-specific assumptions.

## Scalability Notes

Scalability means retaining less and reconstructing more, not hoarding every observation.

## Security Notes

Trust and permission design is part of product design, not an implementation afterthought.

## Performance Considerations

The system should be pleasant to leave running all day on a laptop.

## Future Extensibility

Future features must preserve the core identity: Git-native cognition runtime, not autonomous agent platform.

