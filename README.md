# Synap

Local Git-aware structural context engine for AI coding agents.

[![CI Status](https://github.com/saahilpal/synap-git/actions/workflows/ci.yml/badge.svg)](https://github.com/saahilpal/synap-git/actions)
[![Version](https://img.shields.io/pypi/v/synap-git?color=3b82f6)](https://pypi.org/project/synap-git/)
[![License](https://img.shields.io/github/license/saahilpal/synap-git?color=cbd5e1)](LICENSE.md)
[![Python Version](https://img.shields.io/pypi/pyversions/synap-git)](https://pypi.org/project/synap-git/)

## The Problem

AI coding agents struggle to maintain codebase context because context windows are easily overwhelmed by raw file dumps. Traditional RAG systems often return fragmented, out-of-date, or semantically irrelevant code blocks. Switching branches or rolling back commits breaks agent state, leading to repetitive mistakes and context drift.

## What Synapse Does

Synap maintains a local structural context index of your codebase that synchronizes with your Git repository. It extracts AST symbols, resolves dependency edges, builds a file-level markdown wiki, and tracks agent behavioral lessons. This context is proactively packaged and injected into your AI agent via a Model Context Protocol (MCP) server.

## How It Works

Synap operates across three context layers: L1 (Structural), L2 (Semantic), and L3 (Behavioral).
* **L1 (Structural)** parses syntax using Tree-sitter to map functions, classes, and their call and dependency edges into a local SQLite database.
* **L2 (Semantic)** maintains a folder of markdown files summarizing the purpose of files, modules, and the overall project.
* **L3 (Behavioral)** tracks current task checkpoints, technical decisions, and past failures (lessons) to keep the agent grounded.

Synap runs on a Git-snapshot model. The index is a pure projection of the active Git commit, ensuring that switching branches or checking out commits immediately swaps the context. If you run `git revert` on an agent's commit, Synap detects the revert, prompts the user to analyze what failed, and logs it as an active behavioral lesson.

## Install

Install the package from PyPI:
```bash
pip install synap-git
```

### System Dependencies
* Git (system command line tool must be available on the PATH)
* Python >= 3.11
* SQLite (compiled with FTS5 support, default in modern Python builds)

## Quick Start

### 1. Configure the Provider
Initialize your LLM provider and credentials:
```bash
synap setup .
```
This prompts for a provider (Ollama, OpenAI, Gemini, Anthropic, OpenRouter) and securely stores API keys in your OS keyring.

### 2. Initialize the Repository
Bootstrap the index for the current directory:
```bash
synap init .
```
This performs a full parallel scan of the codebase and populates the database under `.synap/synap.db`.

### 3. Start the Daemon
Launch the background watcher to track Git branch changes and commits:
```bash
synap start .
```
The daemon starts in the background and hosts the Diagnostic Web UI on port 9876.

### 4. Connect to Your IDE
Generate the Model Context Protocol (MCP) configuration block:
```bash
synap mcp config .
```
Copy and paste this JSON configuration block into your MCP-compatible IDE (such as Cursor or Windsurf) to connect your agent.

## CLI Reference

Every CLI command operates on the target directory path (default is `.`):

* `synap setup [PATH]` — Interactive setup for provider connectivity, model settings, and keyring credentials.
* `synap init [PATH]` — Performs initial structural indexing and enqueues L2 documentation. Supports `--skip-llm` and `--skip-wiki`.
* `synap start [PATH]` — Detaches and launches the background git-monitoring daemon.
* `synap stop [PATH]` — Terminates the running background daemon and cleans up process PIDs.
* `synap restart [PATH]` — Restarts the background daemon process.
* `synap status [PATH]` — Displays daemon health, active branch, HEAD commit, index counts, and LLM configuration. Supports `--json`.
* `synap logs` — Views and tails Synap daemon log output. Supports `-t` (tail), `-n` (lines count), and `-d` (debug logs).
* `synap update` — Upgrades the local installation using pip, pipx, or uv.
* `synap version` — Prints the package version.
* `synap rollback [PATH]` — Checks out a previous Git commit, clears current checkpoint, and preserves approved memory. Supports `-c` (commit) and `-y` (yes).
* `synap repair [PATH]` — Performs database quick checks and rebuilds the index from HEAD. Supports `-y` (yes).
* `synap doctor [PATH]` — Verifies SQLite integrity, Tree-sitter parsers, tokenizers, dependencies, and daemon heartbeats.
* `synap run [PATH]` — Starts the background daemon in the foreground.
* `synap ui [PATH]` — Launches the Diagnostic UI in your default web browser.
* `synap mcp start [PATH]` — Serves the MCP stdio interface for agent connections.
* `synap mcp config [PATH]` — Outputs the JSON configuration block for IDE integration.
* `synap mcp verify [PATH]` — Asserts protocol schema compliance and tests MCP tools.
* `synap memory status [PATH]` — Displays counts of approved, pending, and expired L3 lessons.
* `synap memory prune [PATH]` — Evaluates expiration dates and deletes old memory lessons.
* `synap memory verify [PATH]` — Checks approved memory files against the filesystem to detect dangling references. Supports `--json`.
* `synap lessons approve <LESSON_ID> [PATH]` — Moves a pending lesson to the approved state.
* `synap lessons reject <LESSON_ID> [PATH]` — Rejects a pending or approved lesson.
* `synap lessons review [PATH]` — Starts an interactive CLI wizard to approve, edit, reject, or skip pending lessons.
* `synap checkpoint create [PATH]` — Creates a new developer state checkpoint. Supports `--doing`, `--files`, `--next-step`, and `--blockers`.
* `synap checkpoint list [PATH]` — Lists all saved checkpoints for the active branch.
* `synap checkpoint restore <CHECKPOINT_ID> [PATH]` — Displays details of a checkpoint (or "latest").
* `synap usage show [PATH]` — Renders a table of LLM calls, purpose, and accumulated token counts.
* `synap usage clear [PATH]` — Clears recorded LLM call metrics.
* `synap wiki list [PATH]` — Lists all generated L2 wiki pages.
* `synap wiki show <FILEPATH> [PATH]` — Renders a markdown page in the terminal.

## Configuration

Configuration is stored in `~/.config/synap/config.toml` (or custom path via `SYNAP_CONFIG`).

| Field Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `profile` | `string` | `"dev"` | Runtime profile: `"dev"`, `"test"`, or `"prod"`. |
| `mode` | `string` | `"active"` | Daemon operational mode: `"active"` or `"idle"`. |
| `repository_path` | `string` | `"."` | Path to the repository root directory. |
| `state_path` | `string` | `".synap"` | Storage location for database, logs, and wiki pages. |
| `sqlite_path` | `string` | `".synap/synap.db"` | SQLite database file location. |
| `object_path` | `string` | `".synap/objects"` | Directory for serialized artifacts. |
| `log_path` | `string` | `".synap/logs"` | Directory for daemon logs. |
| `logging_mode` | `string` | `"human"` | Log formatting style: `"human"` or `"json"`. |
| `log_level` | `string` | `"INFO"` | Daemon log level filtering. |
| `max_file_bytes` | `integer` | `1000000` | Maximum size of files indexed. |
| `checkpoint_threshold` | `float` | `0.60` | Percentage of context window used before checkpoint suggestion. |
| `lesson_expiry_days` | `integer` | `7` | Days before a memory lesson expires. |
| `llm_provider` | `string` | `null` | Chosen LLM API: `"openai"`, `"gemini"`, `"anthropic"`, `"ollama"`, `"openrouter"`. |
| `llm_model` | `string` | `null` | Named model for prompts and documentation. |
| `ollama_url` | `string` | `"http://127.0.0.1:11434"`| Base endpoint for local Ollama instances. |
| `mcp_host` | `string` | `"127.0.0.1"` | Bind host for the MCP server. |
| `mcp_port` | `integer` | `9876` | Default port for daemon API. |
| `daemon_poll_interval_seconds` | `float` | `2.0` | Polling loop duration for checking git changes. |
| `shutdown_timeout_seconds` | `float` | `5.0` | Grace period allowed for worker termination. |

## Supported Languages

Synap uses Tree-sitter parsers for the following extensions:
* **Python** (`.py`)
* **JavaScript / JSX** (`.js`, `.jsx`)
* **TypeScript / TSX** (`.ts`, `.tsx`)
* **Go** (`.go`)
* **Rust** (`.rs`)
* **Java** (`.java`)
* **C / C++** (`.cpp`, `.cc`, `.cxx`, `.hpp`, `.h`)
* **Ruby** (`.rb`)

## Supported Providers

* **Ollama** — Local model execution.
* **OpenAI** — Cloud-based GPT models.
* **Anthropic** — Claude models.
* **Gemini** — Google generative models.
* **OpenRouter** — Unified endpoint routing.

## MCP Integration

Verify your MCP connection string:
```bash
synap mcp config .
```

### Server Configuration JSON
Add this block to your Cursor or Windsurf MCP server settings:
```json
{
  "mcpServers": {
    "synap": {
      "command": "/path/to/python",
      "args": ["-m", "synap_git.cli", "mcp", "start", "/path/to/repo"],
      "autoConnect": true
    }
  }
}
```

## Web UI

The Synap daemon serves a dashboard on port `9876`. It shows:
* **State Overview** — Active branch, HEAD OID, file count, and symbol count.
* **L3 Agent Memory** — Lists of approved and pending lessons.
* **LLM Call Metrics** — Total calls, total tokens used, and history of recent completions.
* **Checkpoints** — Interactive timeline of recent agent checkpoints.
* **Operational Trace** — Visualization of the latest hybrid query execution, latency timeline, and token budget allocations.

## Architecture

Synap utilizes a 3-layer context model:
* **L1 (Structural Index)** — Parsed AST symbols and edges. These are fully regeneratable by wiping `.synap/` and running `synap init`.
* **L2 (Wiki Documentation)** — Locally stored summaries under `.synap/wiki/`. These are regeneratable.
* **L3 (Behavioral Memory)** — Stored checkpoints, decisions, and lessons. Approved lessons persist through Git rollbacks, checkouts, and index wipes.

## Performance

* **First Run** — Indexes 500 files in under 10 seconds using process-pool parallel parsing.
* **Incremental Runs** — Uses Git change classification (`git diff-tree`) to process updates under 50 milliseconds.
* **Token Cost** — Hybrid retrieval consumes around 1,500 to 3,500 tokens per query, keeping context packaging bounded.

## Limitations

* **Local git dependency** — Synap does not function outside of an active git repository.
* **Structural-only fallback** — Disables L2 generation and retrieval generation if no LLM provider is configured (running in structural Mode A).
* **Text files only** — Binary files and files exceeding `max_file_bytes` are excluded from indexing.

## Contributing

Run the test suite using pytest:
```bash
./.venv/bin/python -m pytest tests/ -x --tb=short
```

Run formatting and type checks:
```bash
./.venv/bin/ruff format src/
./.venv/bin/ruff check src/
./.venv/bin/mypy src/
```

## License

This project is licensed under the Apache-2.0 License. See [LICENSE.md](LICENSE.md) for details.
