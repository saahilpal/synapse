# CLI Command Reference

This document provides complete reference documentation for all commands and options available in the `synap` CLI tool.

---

## Core Commands

### `synap setup`

Interactive setup wizard for first-run environment configuration, provider selection, and secure credentials storage.

- **Usage:** `synap setup [PATH]`
- **Action:** Prompts for provider type (Ollama, OpenAI, Gemini, Anthropic, OpenRouter), models, and credentials. Keys are saved securely into the OS keyring.
- **Example:**
  ```bash
  synap setup .
  ```

### `synap init`

Initializes a repository and runs the full initial indexing process (first-run scan, Tree-sitter AST parsing, dependency graph creation, and wiki enqueuing).

- **Usage:** `synap init [PATH] [OPTIONS]`
- **Arguments:**
  - `PATH` — Target repository path (default: `.` active directory).
- **Options:**
  - `--force` — Rebuilds the index from scratch even if already initialized.
  - `--skip-llm` — Runs the indexer in structural Mode A only, bypassing LLM calls.
  - `--skip-wiki` — Skips wiki documentation enqueuing entirely.
  - `--quiet` — Silences CLI terminal output.
  - `--json` — Emits status results in structured JSON format.
- **Example:**
  ```bash
  synap init . --skip-llm
  ```

### `synap index`

Runs an on-demand structural indexing pass without re-running the initialization wizard.

- **Usage:** `synap index [PATH] [OPTIONS]`
- **Arguments:**
  - `PATH` — Target repository path (default: `.`).
- **Options:**
  - `--force` — Forces a complete re-index of all files in the repository.
  - `--skip-llm` — Skips LLM-dependent operations.
  - `--skip-wiki` — Skips documentation enqueuing.
  - `--quiet` — Silences progress bars and console logs.
  - `--json` — Outputs machine-readable status JSON.
- **Example:**
  ```bash
  synap index . --force
  ```

### `synap sync`

Explicitly synchronizes Git commit state, detects branch switches or commit movements, and runs an incremental AST delta update.

- **Usage:** `synap sync [PATH] [OPTIONS]`
- **Arguments:**
  - `PATH` — Repository path (default: `.`).
- **Options:**
  - `--json` — Outputs synchronization metrics and delta details in JSON.
- **Example:**
  ```bash
  synap sync .
  ```

### `synap start`

Launches the Synap daemon as a background detached process.

- **Usage:** `synap start [PATH]`
- **Action:** Spawns a background worker monitoring Git commit deltas, processing the L2 wiki queue, and serving the diagnostic REST API & web dashboard.
- **Example:**
  ```bash
  synap start .
  ```
- **Sample Output:**
  ```
  Starting Synap daemon...
  ✓ Synap daemon started (PID 12345)
  ✓ Runtime healthy
  ✓ UI available at http://127.0.0.1:9876
  ```

### `synap stop`

Gracefully shuts down the background daemon process and cleans lockfiles.

- **Usage:** `synap stop [PATH]`
- **Action:** Sends termination signal to the recorded daemon PID, releases `.synap/daemon.pid` and heartbeat files.
- **Example:**
  ```bash
  synap stop .
  ```

### `synap restart`

Restarts the background Synap daemon.

- **Usage:** `synap restart [PATH]`
- **Example:**
  ```bash
  synap restart .
  ```

### `synap status`

Displays the current repository context status, daemon health, indexed file counts, memory nodes, and Git commit OIDs.

- **Usage:** `synap status [PATH] [OPTIONS]`
- **Options:**
  - `--json` — Outputs all metrics and daemon state as machine-readable JSON.
- **Example:**
  ```bash
  synap status .
  ```

### `synap search`

Executes a hybrid structural search query combining lexical, AST symbol graph traversal, and semantic context.

- **Usage:** `synap search <QUERY> [OPTIONS]`
- **Arguments:**
  - `QUERY` (required) — Natural language or symbol search text.
- **Options:**
  - `-p`, `--path <PATH>` — Repository path (default: `.`).
  - `--max-tokens <INT>` — Maximum token budget allocated for context packing (default: `4000`).
- **Example:**
  ```bash
  synap search "How does the indexing engine handle Git commits?" --max-tokens 3000
  ```

### `synap logs`

Inspects or streams daemon logs.

- **Usage:** `synap logs [PATH] [OPTIONS]`
- **Options:**
  - `-t`, `--tail` — Continuously stream new log lines in real-time.
  - `-n`, `--lines <INT>` — Number of trailing log lines to display (default: `50`).
  - `-d`, `--debug` — Include debug and trace log levels.
- **Example:**
  ```bash
  synap logs -t -n 100
  ```

### `synap wipe`

Purges the local `.synap/` state directory (SQLite database, WAL files, checkpoints, and logs) for the specified repository.

- **Usage:** `synap wipe [PATH] [OPTIONS]`
- **Options:**
  - `-y`, `--yes` — Bypasses the confirmation prompt.
- **Example:**
  ```bash
  synap wipe . -y
  ```

### `synap rollback`

Rolls back indexing and repository context state to a previous Git commit.

- **Usage:** `synap rollback [PATH] [OPTIONS]`
- **Options:**
  - `-c`, `--commit <REF>` — Specific Git commit hash to roll back to.
  - `-y`, `--yes` — Bypasses confirmation prompt.
- **Example:**
  ```bash
  synap rollback . --commit 3a1b2c4 -y
  ```

### `synap repair`

Verifies SQLite database integrity (`PRAGMA quick_check`), repairs corrupted indexes, and triggers a clean index rebuild if needed.

- **Usage:** `synap repair [PATH] [OPTIONS]`
- **Options:**
  - `-y`, `--yes` — Automatically confirms rebuilding.
- **Example:**
  ```bash
  synap repair . -y
  ```

### `synap doctor`

Performs an extensive environment and system diagnostic check: Python environment, Tree-sitter parsers, SQLite WAL settings, Keyring access, Git CLI availability, and daemon health.

- **Usage:** `synap doctor [PATH]`
- **Example:**
  ```bash
  synap doctor .
  ```

### `synap run`

Runs the Synap daemon in the foreground. Ideal for debugging, development, and containerized deployments.

- **Usage:** `synap run [PATH]`
- **Example:**
  ```bash
  synap run .
  ```

### `synap ui`

Discovers the active daemon listening port from the heartbeat file and opens the Diagnostic Web Dashboard in your default browser.

- **Usage:** `synap ui [PATH]`
- **Example:**
  ```bash
  synap ui .
  ```

### `synap cost`

Calculates and prints aggregated LLM usage, input/output token counts, and estimated USD expenditure across all operations.

- **Usage:** `synap cost [PATH] [OPTIONS]`
- **Options:**
  - `--json` — Returns token and cost calculations as JSON.
- **Example:**
  ```bash
  synap cost .
  ```

### `synap version`

Displays the installed `synap` package version and Python runtime information.

- **Usage:** `synap version`
- **Example:**
  ```bash
  synap version
  ```

### `synap update`

Self-updates the installed `synap-git` package to the latest release using the active package manager (`uv` or `pip`).

- **Usage:** `synap update`
- **Example:**
  ```bash
  synap update
  ```

### `synap uninstall`

Removes global CLI links, helper scripts, and uninstalls `synap-git`.

- **Usage:** `synap uninstall [OPTIONS]`
- **Options:**
  - `-y`, `--yes` — Confirms uninstallation without prompting.
- **Example:**
  ```bash
  synap uninstall -y
  ```

---

## Model Context Protocol (MCP) Commands

### `synap mcp serve`

Runs the Model Context Protocol (MCP) server over standard I/O (`stdio`). This is the primary command used by AI coding agents (Cursor, Windsurf, Claude Desktop) to establish an MCP connection.

- **Usage:** `synap mcp serve [PATH]`
- **Note:** Standard output (`stdout`) is strictly reserved for JSON-RPC messages; all diagnostic and operational logs are routed to `stderr`.
- **Example:**
  ```bash
  synap mcp serve .
  ```

### `synap mcp start`

Alias for `synap mcp serve`.

- **Usage:** `synap mcp start [PATH]`
- **Example:**
  ```bash
  synap mcp start .
  ```

### `synap mcp config`

Generates ready-to-use JSON configuration blocks for Cursor, Windsurf, or Claude Desktop.

- **Usage:** `synap mcp config [PATH]`
- **Example:**
  ```bash
  synap mcp config .
  ```

### `synap mcp verify`

Verifies that the MCP server can initialize, validates schema envelopes, and tests communication over stdio.

- **Usage:** `synap mcp verify [PATH]`
- **Example:**
  ```bash
  synap mcp verify .
  ```

---

## L3 Memory Management Commands

### `synap memory status`

Displays counts of approved, pending, and expired memory lessons.

- **Usage:** `synap memory status [PATH]`
- **Example:**
  ```bash
  synap memory status .
  ```

### `synap memory prune`

Evaluates expiration timestamps (`lesson_expiry_days`) and transitions expired lessons from `"approved"` to `"expired"`.

- **Usage:** `synap memory prune [PATH]`
- **Example:**
  ```bash
  synap memory prune .
  ```

### `synap memory verify`

Validates that files referenced in approved lessons still exist in the repository, detecting dangling references caused by file renames or deletions.

- **Usage:** `synap memory verify [PATH] [OPTIONS]`
- **Options:**
  - `--json` — Returns healthy and dangling lesson lists in JSON format.
- **Example:**
  ```bash
  synap memory verify .
  ```

### `synap memory decisions`

Lists architectural and technical decisions logged by developers or AI agents.

- **Usage:** `synap memory decisions [PATH] [OPTIONS]`
- **Options:**
  - `-b`, `--branch <BRANCH>` — Filter by branch name, or specify `'all'` for all branches.
  - `-n`, `--limit <INT>` — Maximum number of decisions to return (default: `10`).
  - `--json` — Returns decisions array in JSON.
- **Example:**
  ```bash
  synap memory decisions . --limit 20
  ```

### `synap lessons list`

Lists all recorded lessons with status filtering.

- **Usage:** `synap lessons list [PATH] [OPTIONS]`
- **Options:**
  - `-s`, `--status <STATUS>` — Filter by status: `all` (default), `pending`, `approved`, or `rejected`.
  - `--json` — Emits lessons in JSON format.
- **Example:**
  ```bash
  synap lessons list . --status pending
  ```

### `synap lessons approve`

Approves a pending lesson, transitioning it to active status so it is injected into the agent's context during retrieval.

- **Usage:** `synap lessons approve <LESSON_ID> [PATH]`
- **Example:**
  ```bash
  synap lessons approve 1e2c345d-6789 .
  ```

### `synap lessons reject`

Rejects a pending or approved lesson, marking its status as `"rejected"`.

- **Usage:** `synap lessons reject <LESSON_ID> [PATH]`
- **Example:**
  ```bash
  synap lessons reject 1e2c345d-6789 .
  ```

### `synap lessons review`

Starts an interactive terminal wizard allowing the developer to review each pending lesson, inspect the diff/failure cause, and approve or reject it.

- **Usage:** `synap lessons review [PATH]`
- **Example:**
  ```bash
  synap lessons review .
  ```

---

## Checkpoint Commands

### `synap checkpoint create`

Saves the current agent's task state and affected files as a branch-specific checkpoint.

- **Usage:** `synap checkpoint create [PATH] [OPTIONS]`
- **Options:**
  - `--doing <TEXT>` — Description of the task currently being executed.
  - `--files <FILES>` — Comma-separated list of affected file paths.
  - `--next-step <TEXT>` — Next planned engineering step.
  - `--blockers <TEXT>` — Any blockers or open issues.
- **Example:**
  ```bash
  synap checkpoint create . --doing "Refactoring API routes" --files "src/api/app.py" --next-step "Add test cases"
  ```

### `synap checkpoint list`

Lists all checkpoints recorded on the active Git branch.

- **Usage:** `synap checkpoint list [PATH] [OPTIONS]`
- **Options:**
  - `--json` — Outputs checkpoint records as JSON.
- **Example:**
  ```bash
  synap checkpoint list .
  ```

### `synap checkpoint restore`

Inspects and outputs the details of a saved checkpoint to restore agent context.

- **Usage:** `synap checkpoint restore [CHECKPOINT_ID] [PATH]`
- **Arguments:**
  - `CHECKPOINT_ID` — Checkpoint UUID or `'latest'` (default: `'latest'`).
- **Example:**
  ```bash
  synap checkpoint restore latest .
  ```

---

## L2 Wiki Commands

### `synap wiki list`

Lists all generated markdown documentation pages stored under `.synap/wiki/`.

- **Usage:** `synap wiki list [PATH]`
- **Example:**
  ```bash
  synap wiki list .
  ```

### `synap wiki show`

Renders a specific wiki documentation page formatted in the terminal using Rich Markdown. If the page is missing or stale, it triggers on-demand lazy generation.

- **Usage:** `synap wiki show <FILEPATH> [PATH]`
- **Arguments:**
  - `FILEPATH` — Relative file path of the documented code file (e.g. `src/utils.py`).
- **Example:**
  ```bash
  synap wiki show src/synap_git/config.py .
  ```

### `synap wiki retry`

Re-queues all permanently failed documentation tasks in `wiki_queue` back to `"pending"` state for reprocessing.

- **Usage:** `synap wiki retry [PATH]`
- **Example:**
  ```bash
  synap wiki retry .
  ```

---

## LLM Usage Tracking Commands

### `synap usage show`

Renders an aggregated table displaying total calls, prompt tokens, completion tokens, and breakdown by purpose (`wiki`, `retrieval`).

- **Usage:** `synap usage show [PATH] [OPTIONS]`
- **Options:**
  - `--json` — Outputs call history and metrics in JSON format.
- **Example:**
  ```bash
  synap usage show .
  ```

### `synap usage clear`

Purges recorded LLM call logs from the database.

- **Usage:** `synap usage clear [PATH]`
- **Example:**
  ```bash
  synap usage clear .
  ```
