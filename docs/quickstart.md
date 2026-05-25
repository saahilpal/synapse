# Quickstart

This guide will walk you through initializing Synapse in a repository, inspecting the structural graph, and starting the daemon for continuous context updates.

## 1. Installation

Synapse is built in Python and relies on `uv` for fast dependency resolution.

```bash
uv tool install synapse-core
```

*(If you are developing Synapse locally, refer to the [Contributing Guide](../CONTRIBUTING.md) instead).*

## 2. Initialize a Repository

Navigate to any codebase where you want to provide structural context to your AI agents:

```bash
cd /path/to/your/project
synapse init .
```

**What happens here?**
Synapse scans your project, applies deterministic exclusions (ignoring `.git`, `node_modules`, `venv`, etc.), computes file content hashes, and parses the initial Abstract Syntax Trees (ASTs). It creates a `.synapse/` folder containing the SQLite event WAL and the Zlib object store.

## 3. Inspect the Context

You can verify that the graph was built correctly using the CLI:

```bash
# Check the status of the context head
synapse status .

# View the timeline of context commits
synapse commits .

# Perform a hybrid retrieval search
synapse search "authentication middleware" .
```

## 4. Start the Daemon and API

To ensure that your agents always have up-to-date context, start the Synapse daemon. This process watches for Git state changes and file system events, incrementally updating the graph.

```bash
synapse start .
```

## 5. Explore the UI

Synapse includes a lightweight, D3-based visualizer for inspecting the bounded context graph and historical timeline.

```bash
synapse ui . --host 127.0.0.1 --port 9876
```

Open `http://127.0.0.1:9876` in your browser to visually explore your repository's structure.

---

### Next Steps

- Learn how Synapse connects to AI agents via the [Model Context Protocol (MCP)](../README.md#agent-integration-mcp).
- Deep dive into the [Retrieval Pipeline](retrieval.md).
