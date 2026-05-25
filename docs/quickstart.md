# Quickstart & Onboarding Guide

Welcome to Synapse—a Temporal Cognitive Operating System for Software Systems. This guide walks you through the one-command onboarding flow and explains how to scan a repository, commit context nodes, query history, and launch the monochrome visualization UI.

---

## 1. One-Command Onboarding

To set up your local workspace, run:
```bash
uv sync --all-extras --dev
```
This single command installs all dependencies, initializes your virtual environment (`.venv`), registers extras (like the MCP server interface), and installs development tools (ruff, mypy, pytest) deterministically.

To run the Visualizer Web UI:
```bash
uv run synapse ui
```
This fires up the FastAPI server at `http://localhost:8000`, exposing the D3 interactive temporal graph visualization.

---

## 2. CLI Workflows

Synapse features a fully-featured command-line interface. Run `uv run synapse --help` to explore all commands.

### Initialize Synapse in a Repository
Initializes the append-only event store and content-addressed storage inside `.synapse/`:
```bash
uv run synapse init
```

### Inspect System Status
Checks database health, active context count, and active branch head:
```bash
uv run synapse status
```

### Append a Manual Context Note
Add a durable fact to your temporal graph:
```bash
uv run synapse note "ADR decision: We will use SQLite in WAL mode for persistent events."
```

### View Context Lineage Timeline
Show the event sequence and context branch commits through time:
```bash
uv run synapse timeline
```

### Query Context Lineage
Verify the integrity of your DAG and search for anomalies:
```bash
uv run synapse lineage
```

### Compact History
Run the compaction pipeline to deduplicate duplicate states and migrate cold historical records:
```bash
uv run synapse compact
```

---

## 3. Environment & Configuration Guide

You can customize Synapse behavior by setting environment variables or modifying your configurations.

### Configuration file: `pyproject.toml`
Ruff lint configurations, mypy typing levels, and package dependencies are defined directly in [pyproject.toml](pyproject.toml).

### Environment Variables
- `SYNAPSE_PROFILE`: Set to `dev` or `prod` to select the runtime profile.
- `SYNAPSE_STATE_PATH`: Override the default location of the database and objects store (defaults to `.synapse/` in the repository root).
- `SYNAPSE_REPO_PATH`: Override the targeted code workspace directory.
