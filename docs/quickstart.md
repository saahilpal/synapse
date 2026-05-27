# Quickstart

This guide will help you get Synapse up and running in your repository in under 5 minutes.

## 1. Installation

Synapse is distributed as a Python package. We recommend using `uv` for a fast, isolated installation.

```bash
uv tool install synapse
```

## 2. Global Setup

The first time you use Synapse, run the `setup` wizard. This will securely store your API keys in `~/.config/synapse/config.toml` and configure your preferred AI providers.

```bash
synapse setup .
```

> **Pro Tip:** If you use [Ollama](https://ollama.com/), Synapse will automatically detect it and use it for local-first, private context processing.

## 3. Initialize your Repository

Navigate to your project's root directory and initialize the local Synapse state:

```bash
cd /path/to/your/repo
synapse init .
```

This creates a `.synapse/` folder (add this to your `.gitignore`!) and performs the initial structural scan of your codebase.

## 4. Connect to your Agent

Synapse supports the **Model Context Protocol (MCP)**. Generate the MCP configuration snippet for your IDE:

```bash
synapse mcp config .
```

Copy the generated JSON structure into your Cursor, Windsurf, or Claude Desktop MCP configuration.

## 5. Launch the Platform

Start the full Synapse runtime. This command starts the background watcher daemon, the MCP server, and the diagnostic UI.

```bash
synapse run .
```

## 6. Verify and Use

Once the runtime is active, you can:

1.  **Open the UI:** Visit `http://127.0.0.1:9876` to inspect your repository's structural graph, checkpoints, L3 agent memory, and live traces.
2.  **Verify System Health:** Check the status of database integrity, parsers, and daemon connectivity:
    ```bash
    synapse doctor .
    ```
3.  **Interact via MCP:** In your IDE chat (e.g. Cursor), ask questions grounded by Synapse context.

---

## Next Steps

- **[Architecture](../ARCHITECTURE.md):** Learn about the internal "Source of Truth" engine.
- **[Troubleshooting](troubleshooting.md):** Common setup issues and diagnostic tips.
