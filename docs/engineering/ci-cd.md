# CI/CD

## Purpose

CI/CD keeps Synapse safe to change by running formatting, linting, typing, tests, and eventually release checks on every contribution.

## Architecture

```mermaid
flowchart LR
    Push[Push or PR]
    Lint[Ruff lint]
    Format[Ruff format]
    Type[Mypy]
    Test[Pytest]
    Release[Release checks]

    Push --> Lint --> Format --> Type --> Test --> Release
```

## Lifecycle

Local pre-commit hooks run fast checks. CI runs the full validation set. Release jobs add compatibility and packaging verification.

## Responsibilities

- Enforce style and typing.
- Run unit and integration tests.
- Preserve coverage visibility.
- Validate docs links later.
- Gate releases on replay compatibility.

## Data Flow

Source changes trigger CI, CI publishes status, maintainers merge only green changes except documented emergency fixes.

## Failure Modes

- CI differs from local tooling.
- Tests require unavailable external services.
- Optional dependency failures hide core regressions.

## Edge Cases

- Qdrant integration tests are skipped in core CI.
- MCP extra is optional.
- Python version matrix expands after MVP.

## Scalability Notes

Split slow replay and large-repository tests into scheduled jobs when needed.

## Security Notes

Do not expose secrets to pull requests from forks.

## Performance Considerations

Keep default CI under a few minutes during early development.

## Future Extensibility

Add signed release publication, docs publishing, and nightly compatibility jobs.

