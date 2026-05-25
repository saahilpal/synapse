# Quickstart

Synapse runs locally against a repository and writes state under `.synapse/`.

## Install

```bash
uv sync --all-extras --dev
```

## Initialize

```bash
uv run synapse init .
```

This creates the local object store, SQLite database, and first context commit.

## Inspect

```bash
uv run synapse status .
uv run synapse commits .
uv run synapse search "authentication"
```

## Run the Daemon

```bash
uv run synapse start .
```

The daemon polls Git state and schedules bounded re-indexing when repository state changes.

## Run the UI

```bash
uv run synapse ui . --host 127.0.0.1 --port 9876
```

Open `http://127.0.0.1:9876`.
