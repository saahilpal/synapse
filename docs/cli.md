# CLI Command Reference

This document provides details on all CLI commands available in the `synap` tool.

---

## Core Commands

### `synap setup`
Interactive wizard for first-run environment configuration and credentials storage.
* **Usage:** `synap setup [PATH]`
* **Action:** Prompts for provider type, models, and credentials. API keys are saved directly into the OS keyring.
* **Example:**
```bash
synap setup .
```

### `synap init`
Initializes a repository and runs the initial indexing process.
* **Usage:** `synap init [PATH] [OPTIONS]`
* **Options:**
  * `--force` — Rebuilds the index from scratch even if already initialized.
  * `--skip-llm` — Runs the indexer in structural Mode A only, skipping wiki queue enqueuing.
  * `--skip-wiki` — Skips wiki enqueuing entirely.
  * `--quiet` — Silences CLI output.
  * `--json` — Outputs machine-readable status.
* **Example:**
```bash
synap init .
```
* **Output:**
```
✓ Initialized repository at abc1234

Next Steps:
  1. synap start . - Start the background daemon.
  2. synap mcp config  - Get JSON config for your IDE (Cursor/Windsurf).
  3. Connect your AI agent using the MCP config.
```

### `synap start`
Launches the Synap daemon in a background detached process.
* **Usage:** `synap start [PATH]`
* **Action:** Starts the watcher and serves the FastAPI diagnostics server.
* **Example:**
```bash
synap start .
```
* **Output:**
```
Starting Synap daemon...
✓ Synap daemon started (PID 12345)
✓ Runtime healthy
✓ UI available at http://127.0.0.1:9876
```

### `synap stop`
Gracefully shuts down the background daemon.
* **Usage:** `synap stop [PATH]`
* **Action:** Signals the PID process and clears local lockfiles.
* **Example:**
```bash
synap stop .
```
* **Output:**
```
Stopping Synap daemon (PID 12345)...
✓ Synap daemon stopped successfully.
```

### `synap restart`
Restarts the background watcher daemon.
* **Usage:** `synap restart [PATH]`
* **Example:**
```bash
synap restart .
```

### `synap status`
Shows current repository context status and daemon metrics.
* **Usage:** `synap status [PATH] [OPTIONS]`
* **Options:**
  * `--json` — Outputs status details in JSON format.
* **Example:**
```bash
synap status .
```

### `synap search`
Executes a hybrid structural search across the repository.
* **Usage:** `synap search <QUERY> [OPTIONS]`
* **Arguments:**
  * `query` — The natural language search query.
* **Options:**
  * `--path`, `-p` — Repository path.
  * `--max-tokens` — Maximum context window tokens (default: 4000).
* **Example:**
```bash
synap search "How does the indexing engine work?"
```
* **Output:**
```
Property      Value
──────────────╶───────────
Daemon:       Running (PID 12345, uptime 42s)
Repository:   synapse
Branch:       main
Indexed:      142 files
Memory:       840 nodes
LLM Provider: OpenAI
Model:        gpt-4o
CPU:          0.2%
RAM:          48.3 MB
```

### `synap logs`
Views or streams daemon logs.
* **Usage:** `synap logs [OPTIONS]`
* **Options:**
  * `--tail`, `-t` — Stream new log entries in real-time.
  * `--lines`, `-n` — Number of last lines to show (default: 50).
  * `--debug`, `-d` — Output debug and trace level logs.
* **Example:**
```bash
synap logs --lines 10
```

### `synap wipe`
Completely purges the local database and caches for the path.
* **Usage:** `synap wipe [PATH]`
* **Action:** Deletes symbols, edges, checkpoints, and files. Prompts for confirmation.
* **Example:**
```bash
synap wipe .
```

### `synap rollback`
Rolls back indexing and repository state to a previous commit.
* **Usage:** `synap rollback [PATH] [OPTIONS]`
* **Options:**
  * `--commit <REF>`, `-c` — Commit hash to rollback to directly.
  * `--yes`, `-y` — Skips confirmation prompts.
* **Example:**
```bash
synap rollback . --commit abc1234 -y
```

### `synap repair`
Repairs corrupted database files and rebuilds the index.
* **Usage:** `synap repair [PATH] [OPTIONS]`
* **Options:**
  * `--yes`, `-y` — Automatically confirms rebuilding if the DB file is healthy.
* **Example:**
```bash
synap repair .
```

### `synap doctor`
Validates system configuration, database, parser registry, and daemon health.
* **Usage:** `synap doctor [PATH]`
* **Example:**
```bash
synap doctor .
```

### `synap run`
Runs the daemon in the foreground (useful for development).
* **Usage:** `synap run [PATH]`
* **Example:**
```bash
synap run .
```

### `synap ui`
Opens the Synap Diagnostic Web Dashboard in your default browser.
* **Usage:** `synap ui [PATH]`
* **Example:**
```bash
synap ui .
```

---

## Model Context Protocol (MCP)

### `synap mcp start`
Starts the MCP stdio host.
* **Usage:** `synap mcp start [PATH]`
* **Example:**
```bash
synap mcp start .
```

### `synap mcp config`
Generates JSON server configuration blocks for Cursor or Windsurf.
* **Usage:** `synap mcp config [PATH]`
* **Example:**
```bash
synap mcp config .
```

### `synap mcp verify`
Validates protocol endpoints and schemas.
* **Usage:** `synap mcp verify [PATH]`
* **Example:**
```bash
synap mcp verify .
```

---

## L3 Memory Management

### `synap memory status`
Counts active, pending approval, and expired lessons.
* **Usage:** `synap memory status [PATH]`
* **Example:**
```bash
synap memory status .
```

### `synap memory prune`
Forces verification of expiration limits and prunes expired lessons.
* **Usage:** `synap memory prune [PATH]`
* **Example:**
```bash
synap memory prune .
```

### `synap memory verify`
Checks approved lessons' `files_affected` to detect dangling references.
* **Usage:** `synap memory verify [PATH]`
* **Example:**
```bash
synap memory verify .
```

### `synap lessons approve`
Approves a pending lesson to make it active.
* **Usage:** `synap lessons approve <LESSON_ID> [PATH]`
* **Example:**
```bash
synap lessons approve 1e2c345d-6789 .
```

### `synap lessons reject`
Rejects and deletes a pending or approved lesson.
* **Usage:** `synap lessons reject <LESSON_ID> [PATH]`
* **Example:**
```bash
synap lessons reject 1e2c345d-6789 .
```

### `synap lessons review`
Starts an interactive CLI wizard to review pending lessons.
* **Usage:** `synap lessons review [PATH]`
* **Example:**
```bash
synap lessons review .
```

### `synap checkpoint create`
Saves current agent progress as a checkpoint.
* **Usage:** `synap checkpoint create [PATH] [OPTIONS]`
* **Options:**
  * `--doing <TEXT>` — Active task description.
  * `--files <FILES>` — Comma-separated list of affected files.
  * `--next-step <TEXT>` — Planned next steps.
  * `--blockers <TEXT>` — Identified blockers.
* **Example:**
```bash
synap checkpoint create . --doing "Refactoring API" --files "src/api.py" --next-step "Test changes"
```

### `synap checkpoint list`
Lists all checkpoints saved on the active branch.
* **Usage:** `synap checkpoint list [PATH]`
* **Example:**
```bash
synap checkpoint list .
```

### `synap checkpoint restore`
Views checkpoint details.
* **Usage:** `synap checkpoint restore <CHECKPOINT_ID> [PATH]`
* **Example:**
```bash
synap checkpoint restore latest .
```

---

## Usage and Wiki Tools

### `synap usage show`
Renders table showing token allocations and query purposes.
* **Usage:** `synap usage show [PATH]`
* **Example:**
```bash
synap usage show .
```

### `synap cost`
Shows aggregated LLM calls, token counts, and estimated USD cost. This is an alias for `synap usage show` and prints the same aggregated table with an estimated cost total.
* **Usage:** `synap cost [PATH]`
* **Example:**
```bash
synap cost .
```

### `synap usage clear`
Purges LLM calls database entries.
* **Usage:** `synap usage clear [PATH]`
* **Example:**
```bash
synap usage clear .
```

### `synap wiki list`
Lists generated documentation files.
* **Usage:** `synap wiki list [PATH]`
* **Example:**
```bash
synap wiki list .
```

### `synap wiki show`
Renders markdown documentation inside the console.
* **Usage:** `synap wiki show <FILEPATH> [PATH]`
* **Example:**
```bash
synap wiki show src/main.py .
```
