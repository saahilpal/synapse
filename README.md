# Synap

Local Git-aware structural context engine for AI coding agents.

[![CI Status](https://github.com/saahilpal/synapse/actions/workflows/ci.yml/badge.svg)](https://github.com/saahilpal/synapse/actions)
[![Version](https://img.shields.io/pypi/v/synap-git?color=3b82f6)](https://pypi.org/project/synap-git/)
[![Python Version](https://img.shields.io/pypi/pyversions/synap-git)](https://pypi.org/project/synap-git/)
[![License](https://img.shields.io/github/license/saahilpal/synapse?color=cbd5e1)](LICENSE.md)

## The Problem

Context windows of AI coding agents become cluttered when fed raw codebase dumps, causing token waste. Standard vector search systems return isolated snippets that lack import relations, class hierarchies, and file-dependency bonds. Switching branches or checking out older commits disrupts agent operations, causing repetitive code failures.

## What It Does

Synap builds a local structural code graph and a file-level markdown wiki synced to your Git commit history. It stores code symbols and dependency edges in a local SQLite database, generating L3 behavioral memory checkpoints and lessons. Coding agents receive structured, token-bounded context packages through a Model Context Protocol (MCP) server.

## High Level Design (HLD)

Synap coordinates local repository scanning, graph storage, wiki rendering, and MCP tool serving within a unified runtime daemon.

### Component Map

```
                          ┌────────────────────────┐
                          │     synap_git.cli      │
                          └───────────┬────────────┘
                                      │ (invokes)
                                      ▼
                          ┌────────────────────────┐
                          │  synap_git.indexer.    │
                          │        daemon          │
                          └─────┬────────────┬─────┘
          (starts watcher)      │            │      (hosts API server)
                 ┌──────────────┘            └──────────────┐
                 ▼                                          ▼
   ┌──────────────────────────┐               ┌──────────────────────────┐
   │   synap_git.git.state    │               │   synap_git.api.app      │
   └─────────────┬────────────┘               └─────────────┬────────────┘
                 │ (detects commits)                        │ (serves UI)
                 ▼                                          ▼
   ┌──────────────────────────┐               ┌──────────────────────────┐
   │   synap_git.indexer.     │               │   synap_git.api.static   │
   │         engine           │               └──────────────────────────┘
   └─────┬────────────┬───────┘
         │            │ (stores data)
         │            ▼
         │      ┌─────────────────────┐       ┌──────────────────────────┐
         │      │  synap_git.storage. │◀──────│    synap_git.mcp.server  │
         │      │       sqlite        │       └──────────────────────────┘
         │      └─────────────────────┘               (connects agent)
         │ (generates docs)
         ▼
   ┌──────────────────────────┐
   │    synap_git.indexer.    │
   │          wiki            │
   └──────────────────────────┘
```

* **synap_git.cli** — Mounts Typer subcommands for configuration, database repair, logs tailing, and service management.
* **synap_git.indexer.daemon** — Runs the background loop tracking commit shifts and processes asynchronous documentation tasks.
* **synap_git.api.app** — Serves REST endpoints for system metrics, LLM call logging, and diagnostic event streams.
* **synap_git.git.state** — Extracts Git commit OIDs, untracked changes status, and branch indicators.
* **synap_git.indexer.engine** — Orchestrates parallel file parsing, AST traversal, and database serialization.
* **synap_git.parser.registry** — Parses language-specific grammar using Tree-sitter.
* **synap_git.storage.sqlite** — Controls SQLite databases, Write-Ahead Logging (WAL), and FTS5 search indexing.
* **synap_git.indexer.wiki** — Generates file, module, and project markdown documentation summaries.
* **synap_git.retrieval.engine** — Controls lexical, structural, and semantic search queries with token budgeting.
* **synap_git.mcp.server** — Serves Model Context Protocol commands via stdio.

### The Layer Model

Synap isolates structural truth from non-deterministic summaries through three defined layers:

* **L1 (Structural Graph):** Tree-sitter parsers convert code files to AST symbols and import dependencies. Imports map caller-callee relations in a database graph, fully regeneratable from HEAD.
* **L2 (Semantic Wiki):** Asynchronous background prompts construct markdown summaries of files and modules. Missing pages are resolved on-demand through lazy loading.
* **L3 (Behavioral Memory):** Stored checkpoints, technical decisions, and lessons persist through branch swaps and index rollbacks.

### Runtime Topology

On daemon execution, Synap hosts all services in a single process using the asyncio event loop:
* **Git Watcher Loop:** Polls repository state every 2 seconds. Identifies branch switches, commit additions, merges, and reverts.
* **Uvicorn Server:** Hosts the REST API and HTML dashboard on port 9876.
* **Wiki Worker Task:** Listens to `wiki_queue` changes, generating summaries using LLM calls.

### Data Flow

```
[Git Commit] ──▶ [Git Watcher] ──▶ [Indexer Engine] ──▶ [SQLite DB] ──▶ [MCP Client]
                      │                  │                    ▲
                      │ (detects revert) │ (parallel parser)  │ (retrieval)
                      ▼                  ▼                    │
                [Pending Lesson]   [Symbols & Edges] ─────────┘
```

1. **Commit Detection:** Developer checks in a change. The daemon watches the commit shift and runs incremental indexing.
2. **Delta Extraction:** Synap calls `git diff-tree` to extract changed files.
3. **AST Update:** Parser scans modified code, writes new symbols, and deletes old dependencies inside a database transaction.
4. **Wiki Refresh:** Wiki status flags are set to `"stale"`, enqueuing documentation refreshes in the worker queue.
5. **Agent Grounding:** The coding agent triggers the MCP server. Hybrid retrieval parses query words, runs graph traversal, checks approved memories, and returns packaged context.

---

## Low Level Design (LLD)

### Database Schema

All indexing, memory, and tracing metrics are persisted under `.synap/synap.db`.

```
files
  file_id      TEXT  PK   sha256(path + content_hash)
  path         TEXT  UQ   repository-relative file path
  git_oid      TEXT       git blob object identifier
  content_hash TEXT       sha256 hash of file content
  language     TEXT       parsed programming language name
  module_key   TEXT       dot-separated module key representation
  updated_at   TEXT       timestamp string

symbols
  symbol_id     TEXT  PK   sha256 hash identifier
  file_id       TEXT  FK   references files(file_id)
  name          TEXT       symbol name (class/function identifier)
  kind          TEXT       syntax type (e.g. function_definition)
  start_line    INTEGER    starting line number
  end_line      INTEGER    ending line number
  ast_hash      TEXT       stable hash value of the AST subtree
  metadata_json TEXT       serialized symbol metadata attributes

edges
  edge_id       TEXT  PK   sha256 edge hash identifier
  source_symbol TEXT  FK   references symbols(symbol_id)
  target_symbol TEXT  FK   references symbols(symbol_id)
  edge_type     TEXT       relationship type (e.g. depends_on)

embeddings
  embedding_id   TEXT  PK   sha256 hash identifier
  symbol_id      TEXT  FK   references symbols(symbol_id)
  model_name     TEXT       associated LLM model
  model_version  TEXT       version string of model
  prompt_version TEXT       prompt design version identifier
  vector         BLOB       serialized float vector arrays
  content_hash   TEXT       underlying code block hash

active_state
  branch          TEXT  PK   git branch name
  git_commit_hash TEXT       git commit OID
  updated_at      TEXT       timestamp string

decisions
  decision_id  TEXT  PK   UUID string
  branch       TEXT       associated Git branch name
  commit_hash  TEXT       associated Git commit OID
  content      TEXT       technical design decision text
  context      TEXT       technical reasoning text
  agent_id     TEXT       agent identifiers
  created_at   INTEGER    unix epoch timestamp

checkpoints
  checkpoint_id TEXT  PK   UUID string
  branch        TEXT       associated Git branch name
  commit_hash   TEXT       associated Git commit OID
  doing         TEXT       current task explanation
  changed_files TEXT       JSON list of modified file paths
  next_step     TEXT       planned next action details
  decisions     TEXT       associated technical decisions
  blockers      TEXT       identified development obstacles
  token_count   INTEGER    active token usage counts
  created_at    INTEGER    unix epoch timestamp

lessons
  lesson_id      TEXT  PK   UUID string
  branch         TEXT       associated Git branch name
  revert_commit  TEXT       git revert commit hash
  reverted_from  TEXT       reverted commit hash
  what_failed    TEXT       explanation of failure
  why_failed     TEXT       remedy rule guidelines
  files_affected TEXT       JSON list of files modified
  status         TEXT       lesson status (pending, approved, expired)
  created_at     INTEGER    unix epoch timestamp
  approved_at    INTEGER    approval timestamp
  expires_at     INTEGER    expiry timestamp
  approval_actor TEXT       approver credentials identifier

llm_calls
  call_id       TEXT  PK   UUID string
  provider      TEXT       AI provider name
  model         TEXT       LLM model name
  input_tokens  INTEGER    input token count
  output_tokens INTEGER    output token count
  purpose       TEXT       call category (retrieval, wiki)
  file_path     TEXT       associated file path if applicable
  created_at    INTEGER    unix epoch timestamp
```
*Note: Schema versioning is managed via `user_version` pragmas (currently version 3).*

### Indexing Pipeline

Indexing translates source trees to SQLite relations:
1. **Bootstrap Check:** Compares HEAD commit hash with database records. Passes execution to first-run indexing if blank, or incremental indexing if commit history matches.
2. **First-run Indexing:** Parses all files. Files are split into chunks of 500. `ProcessPoolExecutor` uses all available CPU cores to execute AST parsing in parallel.
3. **AST Symbol Extraction:** Tree-sitter parsers process code bytes. Traversal scripts register functions and classes.
4. **First-pass Database Insert:** upserted files and symbol rows are written in SQLite transactions using `executemany` arrays.
5. **Incremental Indexing:** Monitors file changes. Uses `git diff-tree` to isolate changes, deleting obsolete symbols and re-parsing only changed files.
6. **Pass 2 Edge Resolution:** Resolves imports. Compares import paths with dot-separated `module_key` columns and FTS5 symbol indexes, storing matches in the `edges` table.

### Retrieval Design

Retrieval uses a four-stage hybrid query execution loop:
1. **Temporal Selection:** Filters data based on active branch state.
2. **Lexical Searching:** Queries terms using `symbols_fts` MATCH indexing, starting candidate scores at `1.0`.
3. **Structural Expansion:** Traverses neighbors up to 2 hops away using SQLite recursive CTEs. Neighbors receive a starting score of `0.8^distance`.
4. **Semantic Ranking:** Boosts matching queries by `+0.2` if the query matches symbol names. Sorts final context entries in descending order.

### MCP Protocol Tools

MCP server communicates via stdio, packaging database actions under a JSON envelope.

* **`get_status`** — Returns indexing counts, branch details, and HEAD commit hashes.
* **`search`** (inputs: `query` string, `max_tokens` integer) — Returns ranked context blocks and latency timelines.
* **`create_checkpoint`** (inputs: `doing` string, `changed_files` list, `next_step` string, `blockers` string) — Registers new thought snapshot.
* **`restore_checkpoint`** — Returns the latest checkpoint detail for the active branch.
* **`log_decision`** (inputs: `content` string, `context_info` string) — Logs architectural decisions.
* **`verify_system`** — Performs SQLite quick checks.
* **`submit_lesson_analysis`** (inputs: `lesson_id` string, `why_failed` string) — Saves lesson details under pending status.
* **`get_approved_memory`** — Returns active approved memory lessons.
* **`get_pending_memory`** — Returns pending lessons awaiting approval.
* **`signal_low_context`** (inputs: `token_count` integer, `capacity` integer) — Asserts window usage thresholds, recommending checkpoints if needed.

### Key Algorithms

#### Revert Detection
When the daemon watcher registers a checkout transition, it runs:
```bash
git log -n 1 --pretty=format:%s
```
If the commit message starts with `"Revert "`, Synap parses the commit message to extract the reverted commit hash. It runs `git show --name-only` to identify affected paths and inserts a pending lesson row.

#### Context Packing
Context is packed using `tiktoken`'s `cl100k_base` tokenizer.
* Enforces limit of `max_tokens - 600` (reserves 600 tokens for instructions).
* Appends active approved memory lessons under `# APPROVED SYSTEM MEMORY`.
* Formats code blocks sequentially. Candidate elements exceeding the remaining budget are truncated.

#### Graph CTE Traversal
Recursively traverses dependencies using SQLite SQL CTEs:
```sql
WITH RECURSIVE neighborhood(id, d) AS (
    SELECT ? as id, 0 as d
    UNION
    SELECT target_symbol, d + 1 FROM edges JOIN neighborhood ON source_symbol = id WHERE d < 2
    UNION
    SELECT source_symbol, d + 1 FROM edges JOIN neighborhood ON target_symbol = id WHERE d < 2
)
SELECT s.*, f.path as source_path, n.d as distance
FROM symbols s
JOIN files f ON s.file_id = f.file_id
JOIN neighborhood n ON s.symbol_id = n.id
ORDER BY n.d ASC
```

---

## Install

Install the python package:
```bash
pip install synap-git
```

### System Requirements
* Python >= 3.11
* Git Command Line Tool
* SQLite (compiled with FTS5 virtual table support)

---

## Quick Start

### 1. Setup LLM Credentials
Run interactive configuration to configure your model:
```bash
synap setup .
```

### 2. Run Ingestion
Initialize the local SQLite database index:
```bash
synap init .
```

### 3. Detach Watcher Daemon
Start background monitoring:
```bash
synap start .
```

### 4. Connect IDE
Generate configuration settings:
```bash
synap mcp config .
```

---

## CLI Reference

All commands support target path arguments:

* `synap setup [PATH]` — Runs provider configuration wizard.
* `synap init [PATH]` — Performs initial structural indexing. Supports `--skip-llm`, `--skip-wiki`.
* `synap wipe [PATH]` — Purges SQLite index.
* `synap start [PATH]` — Launches background daemon.
* `synap stop [PATH]` — Terminate background daemon.
* `synap restart [PATH]` — Restarts background daemon.
* `synap status [PATH]` — Prints active indexing parameters. Supports `--json`.
* `synap logs` — Views system logs. Supports `-t`, `-n`, `-d`.
* `synap update` — Upgrades Synap installation.
* `synap version` — Prints version.
* `synap rollback [PATH]` — Restores index state to previous commit. Supports `-c`, `-y`.
* `synap repair [PATH]` — Wipes index and rebuilds from HEAD. Supports `-y`.
* `synap doctor [PATH]` — Verifies database integrity and parsers.
* `synap run [PATH]` — Runs daemon in foreground.
* `synap ui [PATH]` — Launches HTML dashboard.
* `synap mcp start [PATH]` — Hosts MCP stdio server.
* `synap mcp config [PATH]` — Outputs Cursor connection blocks.
* `synap mcp verify [PATH]` — Asserts MCP server stability.
* `synap memory status [PATH]` — Lists lesson counts.
* `synap memory prune [PATH]` — Evaluates and deletes expired lessons.
* `synap memory verify [PATH]` — Checks lessons for missing files. Supports `--json`.
* `synap lessons approve <ID> [PATH]` — Approves a pending lesson.
* `synap lessons reject <ID> [PATH]` — Rejects a lesson.
* `synap lessons review [PATH]` — Launches interactive lesson review console.
* `synap checkpoint create [PATH]` — Logs progress snapshot. Supports `--doing`, `--files`, `--next-step`, `--blockers`.
* `synap checkpoint list [PATH]` — Renders checkpoint tables.
* `synap checkpoint restore <ID> [PATH]` — Displays checkpoint records.
* `synap usage show [PATH]` — Renders token metrics.
* `synap usage clear [PATH]` — Clears LLM call logs.
* `synap wiki list [PATH]` — Lists generated docs.
* `synap wiki show <FILE> [PATH]` — Renders wiki files.

---

## Configuration

Configuration values are parsed from `~/.config/synap/config.toml`.

| Field Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `profile` | `string` | `"dev"` | Active environment configuration profile. |
| `mode` | `string` | `"active"` | Watcher polling mode selector. |
| `repository_path` | `string` | `"."` | Repository root directory. |
| `state_path` | `string` | `".synap"` | Root storage path. |
| `sqlite_path` | `string` | `".synap/synap.db"` | Database file location. |
| `object_path` | `string` | `".synap/objects"` | Directory for serialized artifacts. |
| `log_path` | `string` | `".synap/logs"` | Directory for logs. |
| `logging_mode` | `string` | `"human"` | Log output format type. |
| `log_level` | `string` | `"INFO"` | Minimum logging level threshold. |
| `max_file_bytes` | `integer` | `1000000` | Size threshold for parsed files. |
| `checkpoint_threshold` | `float` | `0.60` | Threshold ratio for memory warnings. |
| `lesson_expiry_days` | `integer` | `7` | Days before memory lessons expire. |
| `llm_provider` | `string` | `null` | Generative provider: `openai`, `gemini`, `anthropic`, `ollama`, `openrouter`. |
| `llm_model` | `string` | `null` | Named model used for prompts. |
| `ollama_url` | `string` | `"http://127.0.0.1:11434"` | Endpoint URL for Ollama connectivity. |
| `mcp_host` | `string` | `"127.0.0.1"` | Bind host for local networking. |
| `mcp_port` | `integer` | `9876` | Server listener port. |
| `daemon_poll_interval_seconds` | `float` | `2.0` | Git state polling frequency. |
| `shutdown_timeout_seconds` | `float` | `5.0` | Timeout threshold for shutting down. |

---

## MCP Integration

Verify configurations using:
```bash
synap mcp config .
```

### Server Configuration Block
```json
{
  "mcpServers": {
    "synap": {
      "command": "/usr/local/bin/python",
      "args": ["-m", "synap_git.cli", "mcp", "start", "/Users/username/repo"],
      "autoConnect": true
    }
  }
}
```

---

## Supported Languages

Synap processes syntax for the following formats:
* **Python** (`.py`)
* **JavaScript / JSX** (`.js`, `.jsx`)
* **TypeScript / TSX** (`.ts`, `.tsx`)
* **Go** (`.go`)
* **Rust** (`.rs`)
* **Java** (`.java`)
* **C / C++** (`.cpp`, `.cc`, `.cxx`, `.hpp`, `.h`)
* **Ruby** (`.rb`)

---

## Supported Providers

* **Ollama** — Local model integration.
* **OpenAI** — Cloud GPT models. (Environment Variable: `SYNAP_OPENAI_API_KEY`)
* **Anthropic** — Cloud Claude models. (Environment Variable: `SYNAP_ANTHROPIC_API_KEY`)
* **Gemini** — Cloud Gemini models. (Environment Variable: `SYNAP_GEMINI_API_KEY`)
* **OpenRouter** — Unified cloud model routing. (Environment Variable: `SYNAP_OPENROUTER_API_KEY`)

---

## Limitations

* **Git workspace dependency:** Indexes and tracks metadata solely inside valid Git repositories.
* **Structural-only mode:** Runs without wiki generation or contextual LLM generation if `llm_provider` is unset.
* **Size exclusions:** Skips binary files and files larger than `max_file_bytes` (default 1MB).

---

## Contributing

Execute unit tests:
```bash
SYNAP_SKIP_STRESS=1 uv run pytest tests/ -x --tb=short
```

Format code and check types:
```bash
uv run ruff format src/
uv run ruff check src/
uv run mypy src/
```

---

## License

This codebase is licensed under the Apache-2.0 License. See [LICENSE.md](LICENSE.md) for details.
