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

## 4. Integrate with your Agent
Synapse is built to give context to your IDE. Install the MCP integration automatically:

```bash
synapse mcp install cursor
# also supports: claude, roo, cline
```

## 5. Start the All-in-One Runtime
You no longer need to start the UI, daemon, and MCP server separately. Just run:

```bash
synapse run .
```

This will automatically:
- Start the file-watcher daemon to incrementally update context on file saves.
- Start the MCP server so your IDE can query Synapse.
- Start the Context Visualizer UI at `http://127.0.0.1:9876`.

Open the UI in your browser to inspect the codebase graph, or open your IDE and ask it an architectural question to see the grounded retrieval in action.

---

### Next Steps

- Learn how to build [Semantic Overlays](overlays.md) directly from the UI.
- Deep dive into the [Retrieval Pipeline](retrieval.md).
