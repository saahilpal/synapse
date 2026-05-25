# Synapse

Persistent structural context infrastructure for AI coding agents.

Synapse indexes a local repository, stores versioned structural context, and returns grounded context windows to agents and developer tools. It is local-first, parser-grounded, and intentionally small.

## What It Does

- Ingests repository files with deterministic exclusions and content hashes.
- Extracts bounded structure: packages, modules, documents, classes, functions, and imports.
- Stores context commits in SQLite WAL plus a content-addressed object store.
- Invalidates stale structural nodes and semantic overlays during incremental scans.
- Retrieves context with temporal filtering, structural traversal, semantic recall, and optional LLM synthesis.
- Exposes CLI, FastAPI, UI, and MCP-facing helper APIs.

## What It Does Not Do

- It does not use AI to define structural truth.
- It does not store chat transcripts as memory.
- It does not build a universal knowledge graph.
- It does not require cloud infrastructure.

## Install

```bash
uv sync --all-extras --dev
uv run pre-commit install
```

## Use

```bash
uv run synapse init .
uv run synapse status .
uv run synapse search "auth module" .
uv run synapse doctor .
```

Start the daemon:

```bash
uv run synapse start .
```

Start the UI and API server:

```bash
uv run synapse ui . --host 127.0.0.1 --port 9876
```

Visit `http://127.0.0.1:9876`.

## Validate

```bash
uv run ruff check .
uv run ruff format .
uv run mypy src tests
uv run pytest
uv run python -m compileall -q src tests
```

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Quickstart](docs/quickstart.md)
- [Ingestion](docs/ingestion.md)
- [Retrieval](docs/retrieval.md)
- [Semantic Overlays](docs/overlays.md)
- [Troubleshooting](docs/troubleshooting.md)
