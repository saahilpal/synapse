# Contributing

Synapse should be built like infrastructure: small contracts, deterministic behavior, explicit failure modes, and boring local operation.

## Development Setup

```bash
uv sync --all-extras --dev
uv run pre-commit install
uv run pytest
```

If `uv` is not installed, install it first from the official `uv` distribution instructions and avoid committing local virtual environments.

## Engineering Expectations

- Keep modules bounded by runtime, cognition, storage, Git, API, MCP, and security concerns.
- Prefer immutable data objects and explicit service interfaces.
- Use append-only events for durable changes.
- Make background jobs idempotent.
- Add tests for every replay, rollback, migration, parser, or event-schema change.
- Avoid provider-specific model logic in core runtime packages.

## Pull Request Checklist

- The change has a clear architectural boundary.
- Public behavior is documented.
- Tests include the relevant failure path.
- Event schema changes include migration notes.
- Security-sensitive changes update `docs/security/`.
- New subsystem decisions include an ADR when they affect long-term architecture.

## Documentation Standard

Subsystem documentation must include purpose, architecture, lifecycle, responsibilities, diagrams, data flow, failure modes, edge cases, scalability notes, security notes, performance considerations, and future extensibility.

