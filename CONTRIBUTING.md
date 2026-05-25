# Contributing

Synapse should stay small, deterministic, and useful to AI coding agents.

## Development Setup

```bash
uv sync --all-extras --dev
uv run pre-commit install
uv run pytest
```

## Engineering Expectations

- Keep modules bounded by context extraction, storage, runtime, retrieval, provider, API, MCP, UI, and security.
- Prefer immutable models and deterministic hashes.
- Use append-only events for durable changes.
- Keep background jobs idempotent.
- Add tests for migrations, parsers, transactions, rollback, retrieval, overlays, and corruption handling.
- Do not let provider-specific LLM logic leak into structural extraction or storage.
- Avoid new subsystems unless they directly improve persistent repository context.

## Pull Request Checklist

- Public behavior is documented.
- Failure paths are tested.
- Schema changes include migration handling.
- Security-sensitive changes update `SECURITY.md`.
- Retrieval changes respect traversal and token bounds.
