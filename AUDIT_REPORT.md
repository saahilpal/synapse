# Synapse Codebase Audit Report

**Audit Target**: Synapse Core Engine (`src/synap_git/`)
**Audit Date**: August 3, 2026
**Auditor**: Senior AI Systems Engineer

---

## 1. Executive Summary

1. **CLI `synap start` Double-Execution Block (High)**: Running `synap start` when the daemon is already active correctly identifies the running process, but fails to exit—instead proceeding to start a duplicate foreground FastMCP stdio server on the same terminal ([src/synap_git/cli/main.py:673-747](file:///Users/nitrousoxide/Code/synapse/src/synap_git/cli/main.py#L673-L747)).
2. **Language Support Discrepancy (Medium)**: The file scanner registers 38 language file extensions, but the Tree-sitter parser registry only contains symbol extraction logic for 7 languages (`python`, `javascript`/`tsx`, `go`, `rust`, `java`, `cpp`, `ruby`), leaving 31 file types without AST symbol extraction ([src/synap_git/parser/registry.py:107-220](file:///Users/nitrousoxide/Code/synapse/src/synap_git/parser/registry.py#L107-L220)).
3. **Subprocess Polling Overhead (Medium)**: The daemon polls Git state every 2 seconds by spawning `GitPython` subprocess calls regardless of filesystem activity, creating continuous CPU and disk I/O overhead on idle repositories ([src/synap_git/indexer/daemon.py:260-315](file:///Users/nitrousoxide/Code/synapse/src/synap_git/indexer/daemon.py#L260-L315)).
4. **Provider Embedding Gap (Medium)**: Anthropic and OpenRouter providers raise unhandled `NotImplementedError` when vector embedding generation is requested, disabling semantic search without graceful fallback ([src/synap_git/provider/anthropic.py:129](file:///Users/nitrousoxide/Code/synapse/src/synap_git/provider/anthropic.py#L129)).
5. **Symbol History Loss on Renames (Low)**: Primary keys (`file_id = sha256(path + content_hash)`) trigger `ON DELETE CASCADE` when files are renamed or modified, breaking historical symbol edge continuity across file moves ([src/synap_git/storage/sqlite.py:230-337](file:///Users/nitrousoxide/Code/synapse/src/synap_git/storage/sqlite.py#L230-L337)).

---

## 2. Findings Table

| ID | Component | Severity | Description | Evidence (file:line) | Fix Effort |
|---|---|---|---|---|---|
| AUD-01 | CLI | High | `synap start` doesn't exit after detecting active daemon; spawns duplicate foreground MCP server | [cli/main.py:674-747](file:///Users/nitrousoxide/Code/synapse/src/synap_git/cli/main.py#L674-L747) | S |
| AUD-02 | Parser | Medium | 31 of 38 scanner extensions lack AST symbol extraction rules in Tree-sitter registry | [parser/registry.py:107-220](file:///Users/nitrousoxide/Code/synapse/src/synap_git/parser/registry.py#L107-L220) | M |
| AUD-03 | Daemon | Medium | Git watcher polls `git.state()` every 2s via subprocess instead of OS file events (fsnotify/watchdog) | [indexer/daemon.py:260-315](file:///Users/nitrousoxide/Code/synapse/src/synap_git/indexer/daemon.py#L260-L315) | M |
| AUD-04 | Providers | Medium | Anthropic & OpenRouter providers raise `NotImplementedError` for `embed()` calls | [provider/anthropic.py:129](file:///Users/nitrousoxide/Code/synapse/src/synap_git/provider/anthropic.py#L129) | S |
| AUD-05 | Storage | Low | `sha256(path + content_hash)` file ID updates execute `DELETE FROM files`, cascading symbol deletion on rename | [storage/sqlite.py:337](file:///Users/nitrousoxide/Code/synapse/src/synap_git/storage/sqlite.py#L337) | M |
| AUD-06 | CLI | Low | `synap doctor` omits port availability & active daemon REST API health check | [cli/main.py:1389-1480](file:///Users/nitrousoxide/Code/synapse/src/synap_git/cli/main.py#L1389-L1480) | S |
| AUD-07 | Storage | Low | SQLite `synchronous=NORMAL` in WAL mode risks WAL corruption on abrupt power loss | [storage/sqlite.py:48](file:///Users/nitrousoxide/Code/synapse/src/synap_git/storage/sqlite.py#L48) | S |
| AUD-08 | Daemon | Low | Unhandled failed tasks in `wiki_queue` remain permanently in `failed` status without manual retry command | [indexer/daemon.py:365-378](file:///Users/nitrousoxide/Code/synapse/src/synap_git/indexer/daemon.py#L365-L378) | S |

---

## 3. Bugs

### 3.1 Duplicate MCP Server Launch in `synap start`
- **Location**: [src/synap_git/cli/main.py:670-750](file:///Users/nitrousoxide/Code/synapse/src/synap_git/cli/main.py#L670-L750)
- **Detail**: When `synap start` is invoked on a repository where the background daemon is already running:
  1. The CLI correctly detects the PID file and prints `✓ Synap daemon is already running (PID ...)`.
  2. However, line 678 sets `is_running = True` without returning from the function.
  3. Control falls through to line 743 (`server = SynapMCPServer(runtime); asyncio.run(server.run())`), causing the CLI to launch a second FastMCP server on stdio in the current terminal.

### 3.2 Unhandled `NotImplementedError` in Anthropic & OpenRouter Embedding Methods
- **Location**: [src/synap_git/provider/anthropic.py:129](file:///Users/nitrousoxide/Code/synapse/src/synap_git/provider/anthropic.py#L129), [src/synap_git/provider/openrouter.py:123](file:///Users/nitrousoxide/Code/synapse/src/synap_git/provider/openrouter.py#L123)
- **Detail**: Calling `.embed()` on an Anthropic or OpenRouter provider instance raises `NotImplementedError`. While `_generate_embeddings` catches this in `engine.py:300`, hybrid retrieval queries requiring embeddings fail with warnings.

---

## 4. Engineering Issues

### 4.1 Concurrency & SQLite Lock Management
- **Location**: [src/synap_git/storage/sqlite.py:284-297](file:///Users/nitrousoxide/Code/synapse/src/synap_git/storage/sqlite.py#L284-L297)
- **Detail**: `SynapStore.connect()` sets a busy timeout of 30.0 seconds. While SQLite WAL mode permits concurrent readers alongside one writer, simultaneous write operations (e.g., background daemon updating `wiki_queue` while CLI runs `synap checkpoint`) queue for up to 30 seconds before throwing `sqlite3.OperationalError: database is locked`.

### 4.2 Git Polling CPU Overhead
- **Location**: [src/synap_git/indexer/daemon.py:260-315](file:///Users/nitrousoxide/Code/synapse/src/synap_git/indexer/daemon.py#L260-L315)
- **Detail**: `_poll_git_loop` executes every 2 seconds, calling `git.state()` which invokes `git` subprocess calls via `GitPython`. On large repositories or battery-powered devices, continuous subprocess polling consumes CPU cycles even when no files are modified.

---

## 5. Missing & Incomplete Features

### 5.1 Language Parser Coverage vs. Scanner Extension Registry
- **Location**: [src/synap_git/indexer/scanner.py:39-78](file:///Users/nitrousoxide/Code/synapse/src/synap_git/indexer/scanner.py#L39-L78), [src/synap_git/parser/registry.py:107-220](file:///Users/nitrousoxide/Code/synapse/src/synap_git/parser/registry.py#L107-L220)
- **Detail**: `scanner.py` registers 38 language extensions (`.cs`, `.php`, `.swift`, `.kt`, `.scala`, `.sql`, `.html`, `.css`, `.xml`, `.lua`, `.dart`, etc.). However, `_parse_tree_sitter()` in `registry.py` only implements node extraction logic for 7 languages (`python`, `javascript`/`tsx`, `go`, `rust`, `java`, `cpp`, `ruby`). Files with other extensions are scanned but produce zero AST symbols.

### 5.2 Manual Retry for Permanently Failed Wiki Tasks
- **Location**: [src/synap_git/indexer/daemon.py:365-378](file:///Users/nitrousoxide/Code/synapse/src/synap_git/indexer/daemon.py#L365-L378)
- **Detail**: When L2 markdown wiki generation fails 3 times, task status is updated to `'failed'`. On startup, the daemon logs a warning, but there is no CLI subcommand or automated retry mechanism to re-enqueue failed wiki tasks without wiping the database.

---

## 6. Integration & Verification Summary

### 6.1 Verified Implementations
- **Test Suite**: 76 unit and integration tests pass cleanly in 132 seconds (`.venv/bin/pytest -v`).
- **Static Analysis**: `ruff check .` passed with 0 errors; `mypy src` passed with 0 issues across 46 source files.
- **Cycle Handling**: SQLite CTE graph traversal (`get_neighborhood`, [src/synap_git/storage/sqlite.py:444-461](file:///Users/nitrousoxide/Code/synapse/src/synap_git/storage/sqlite.py#L444-L461)) uses `UNION` (set deduplication) to prevent infinite loops on circular import graphs.
- **Token Budgeting**: `HybridRetrievalEngine` ([src/synap_git/retrieval/engine.py:177-237](file:///Users/nitrousoxide/Code/synapse/src/synap_git/retrieval/engine.py#L177-L237)) enforces exact token budgets using `tiktoken`.
- **Revert Detection & Approval**: `GitRepository.classify()` ([src/synap_git/git/state.py:111-130](file:///Users/nitrousoxide/Code/synapse/src/synap_git/git/state.py#L111-L130)) combines commit message parsing and tree OID ancestor iteration. Only approved lessons are injected into retrieval context ([src/synap_git/retrieval/engine.py:241](file:///Users/nitrousoxide/Code/synapse/src/synap_git/retrieval/engine.py#L241)).

---

## 7. Architecture Assessment

### Strengths
- **Deterministic Structural Grounding**: Tree-sitter parsing combined with SQLite Recursive CTE queries provides exact, verifiable code dependency graphs without non-deterministic AI indexing.
- **Robust FastMCP Facade**: Stdio tool handlers are cleanly isolated and wrapped with standardized JSON-RPC error handling and context-gating rules.
- **Self-Healing Storage**: Database corruption detection automatically triggers index recovery and rebuilds.

### Weaknesses
- **Subprocess Polling Overhead**: Polling GitPython every 2 seconds creates avoidable idle CPU usage.
- **Language Parser Asparity**: 31 out of 38 configured file extensions produce no AST symbols.

---

## 8. Prioritized Recommendations

1. **Fix `synap start` Control Flow (High Impact, Low Effort)**: Modify `synap start` in [src/synap_git/cli/main.py:678](file:///Users/nitrousoxide/Code/synapse/src/synap_git/cli/main.py#L678) to exit immediately after detecting an active daemon process unless an explicit `--foreground` flag is passed.
2. **Expand Tree-sitter Parser Handlers (High Impact, Medium Effort)**: Add AST symbol extraction rules in [src/synap_git/parser/registry.py](file:///Users/nitrousoxide/Code/synapse/src/synap_git/parser/registry.py) for C#, PHP, Swift, Kotlin, and Scala.
3. **Adopt File Watcher / Event-Driven Polling (Medium Impact, Medium Effort)**: Replace fixed 2s subprocess polling in [src/synap_git/indexer/daemon.py:260](file:///Users/nitrousoxide/Code/synapse/src/synap_git/indexer/daemon.py#L260) with `watchdog` filesystem events, falling back to polling only when git HEAD changes.
4. **Add `synap wiki retry` Subcommand (Low Impact, Small Effort)**: Add a CLI subcommand to reset `failed` status in `wiki_queue` to `pending`.
