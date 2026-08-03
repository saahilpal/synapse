# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-08-03

## [2.3.0] - 2026-08-03

### Added

- **CLI Cost & Usage Command**: Expose `synap cost` (alias `synap usage`) to show aggregated LLM calls, token counts, and estimated USD cost in the terminal.
- **Web UI: CLI Cost Integration**: The website CLI playground now surfaces an estimated cost line for sample commands so visitors can see token/cost economics.

### Changed

- **Frontend Defensive Rendering**: Guarded several UI paths against undefined symbol objects to prevent runtime errors in production (fixed `.type` property reads).

### Chore

- **Bumped package version** to `2.3.0`.
- **Release automation**: prepared changelog and release tag for GitHub release `v2.3.0`.

## [2.2.0] - 2026-08-03

### Added

- **AST Symbol Parser Expansion (AUD-02)**: Implemented Tree-sitter AST symbol extraction handlers for C#, PHP, Kotlin, Scala, and C.
- **Event-Driven File Watcher (AUD-03)**: Replaced continuous 2s subprocess polling with `watchdog` filesystem event tracking, reducing idle CPU usage to near-zero.
- **Daemon REST API Diagnostic Checks (AUD-06)**: Added daemon port availability and REST API endpoint status checks to `synap doctor`.
- **Wiki Task Requeue Subcommand (AUD-08)**: Added `synap wiki retry` CLI subcommand and `retry_failed_wiki_queue` storage method to requeue permanently failed wiki tasks back to pending state.

### Changed

- **CLI `synap start` Control Flow (AUD-01)**: Fixed `synap start` so it exits cleanly when a daemon is already running unless `--foreground` is explicitly passed.
- **SQLite WAL Performance Rationale (AUD-07)**: Documented `PRAGMA synchronous=NORMAL` in WAL mode as an intentional architectural tradeoff balancing write throughput and self-healing index recovery.

### Fixed

- **Graceful Embedding Provider Fallback (AUD-04)**: Configured Anthropic and OpenRouter providers to log a warning and return empty embedding vectors instead of raising unhandled `NotImplementedError`.
- **Symbol Preservation on File Renames (AUD-05)**: Added `-M` rename detection to `git diff-tree` in incremental indexing to preserve file symbol history and edges across renames.

## [2.1.7] - 2026-07-29

### Added

- **AI Engineer Rules**: Created standardized agent rulesets across `AGENTS.md`, `.cursorrules`, `.windsurfrules`, and `.github/copilot-instructions.md`.

### Fixed

- **Daemon Branch Switching Test Stability**: Resolved timing race condition in daemon branch checkout verification.
- **CLI Setup Connectivity**: Fixed setup connectivity verification and non-TTY prompt fallback handling.

## [2.1.6] - 2026-06-29

### Added

- **Universal Language Expansion**: Expanded tree-sitter AST parsing support from 4 hardcoded languages to dynamically supporting over ~50 languages using `tree-sitter-languages`. Also added dynamic shebang detection (`#!`) to parse extensionless scripts as python, ruby, node, and bash scripts.
- **API Rate Limiting**: Implemented a global `RateLimitedProvider` to throttle LLM and embedding calls to 3 requests per second to mitigate resource exhaustion on the diagnostic API.

### Fixed

- **Broad Exception Handling**: Eradicated remaining `except Exception:` blocks across diagnostics, daemon execution, indexer scanning, and module resolution, and replaced them with `OSError`, `sqlite3.Error`, and specific errors to prevent silent data corruption.
- **Async Sleep Compatibility**: Fixed thread-blocking `time.sleep()` in LLM retries by delegating to `anyio.from_thread.run(anyio.sleep)` if invoked inside FastMCP worker threads.
- **Edge Resolution & Source Paths**: Added support for resolving Javascript, Java, C++, Ruby, and more during import/edge resolution.
- **Module Path Trimming**: Improved module path mapping by trimming `internal/`, `source/`, `packages/`, `main/`, `java/`, `kotlin/`, `scala/` from module keys.
- **Wipe Confirmation**: Added a `--yes` confirmation bypass flag for `synap wipe` and enforced safety confirmation in non-interactive terminals.
- **Metadata Fixes**: Corrected repository URLs in `pyproject.toml` to correctly point to `synapse` instead of `synap-git`.

### Refactored

- **Daemon Teardown**: Refactored the forceful SIGTERM daemon teardown logic to safely toggle via `force_exit=True` rather than a blanket catch-all. Makes programmatic `daemon.stop()` safer without blocking terminal UI interactions.

## [2.1.4] - 2026-06-11

### Fixed

- **Graceful Shutdown Hang**: Fixed an edge case where `synap stop` would time out and forcefully terminate due to `concurrent.futures` threads preventing immediate python process exit when handling embeddings. The CLI now safely flushes databases and exits instantly.

## [2.1.3] - 2026-06-11

### Changed

- **CLI Interactivity Enhancement**: Wrapped all long-running `synap` CLI commands (`init`, `start`, `stop`, `rollback`, `repair`) with interactive rich status spinners to ensure users never stare at an empty screen.
- **Incremental Indexing Progress**: Added a rich progress status to the `_incremental_index` background loop to provide visibility into parsing tasks during cache hits.

## [2.1.2] - 2026-06-11

### Fixed

- **CRITICAL: Daemon Thread Explosion**: Patched a massive concurrency edge case in `SynapRuntime` where large repository indexing would trigger unbounded `threading.Thread` loops for LLM embeddings. A bounded `ThreadPoolExecutor` has been introduced to prevent OOMs, OS thread starvation, and rate-limit hits during first-run indexing.
- **Daemon Lifecycle**: Ensure `embedding_executor` shuts down cleanly without leaking background threads when the daemon loop receives SIGTERM.

## [2.1.1] - 2026-06-11

### Fixed

- **CRITICAL: MCP StdIO Stream Corruption**: Fixed a bug where `synap mcp start` and `signal_low_context` would accidentally print progress bars or notifications to `sys.stdout` instead of `sys.stderr`, which corrupted the MCP protocol stream and disconnected IDEs like Cursor/Windsurf.
- **UX Improvements**: Improved the silence logic in CLI initialization to prevent unnecessary rich formatting in JSON/MCP environments.

## [2.1.0] - 2026-05-29

### Added

- **CLI `search` command**: New user-facing command for executing hybrid structural searches directly from the terminal.
- **`embed_provider` configuration**: Added explicit control over the vector embedding provider via `SYNAP_EMBED_PROVIDER` or `config.toml`.

### Fixed

- **CRITICAL: Metadata Nullability Bug**: Resolved a type mismatch in `CodeSymbol` where `metadata=None` caused background worker crashes. Enforced strict `dict` contract with `default_factory`.
- **CRITICAL: Exception Swallowing**: Eradicated 26 instances of silent failure (`except Exception: pass`) across all core subsystems (API, Indexer, Storage, Retrieval, MCP, Providers). Replaced with structured, traceback-aware logging.
- **CRITICAL: SQLite Schema Integrity**: Fixed `NOT NULL` constraint failure in `llm_calls` table by aligning schema with insertion logic and adding `cost_usd` support.
- **HIGH: Repository-Local Logging**: Redirected daemon logs from a global shared directory to repository-local `.synap/logs` to prevent cross-repository log corruption and lock contention.
- **HIGH: Rollback Atomicity**: Reordered `synap rollback` operations to ensure Git state is successfully restored before purging index checkpoints.
- **MEDIUM: Provider Resiliency**: Added explicit handling for `NotImplementedError` in Anthropic and OpenRouter providers, preventing worker panics when embeddings are misconfigured.

## [2.0.0] - 2026-05-29

### Added

- **.synapignore Support**: Implemented context-aware filtering to prevent traversing symlinks, binary files, and files listed in `.synapignore` or `.gitignore`.
- **FTS5 Integration**: Shifted semantic full-text search directly to SQLite FTS5 with bounding limits (`LIMIT 50`) for `O(1)` lexical retrieval scaling on 10,000+ file monorepos.

### Fixed

- **LLM Hangs in Test Suite**: Isolated testing environment by strictly bypassing real LLM provider configs (`SYNAP_LLM_PROVIDER=""`) preventing test CI suite hangs.
- **Repository Path Scoping in Hybrid Engine**: Fixed a bug where `repo_path` initialization mistakenly truncated the path to `/tmp` in tests, failing contextual snippet aggregation.
- **Unbounded BM25 Expansion**: Bounded full-text search token extraction and BM25 results, preventing out-of-memory cascading in CTE traversal during monorepo indexing.

## [1.2.3] - 2026-05-28

### Added

- **Architecture Documentation Consolidation:** Merged duplicate `docs/architecture.md` into the root-level `ARCHITECTURE.md` to ensure a single, consistent source of architectural truth.

### Fixed

- **Release Version Sync:** Bumped package version in `src/synap_git/__init__.py` to `1.2.3` and updated configuration metadata to align with the release tag validation check in the pipeline.

## [1.1.2] - 2026-05-28

### Added

- **Technical Documentation (`docs/`):** Added detailed manuals for architecture, CLI reference, configuration fields, MCP tools schemas, two-path indexing, wiki queues, and memory lifecycles.
- **Main README:** Completely rewrote the `README.md` from scratch to align strictly with the implemented features, CLI commands, configuration options, and integration paths.

### Removed

- **Obsolete Docs:** Purged stale `quickstart.md`, `retrieval.md`, `roadmap.md`, `diagnostics.md`, `performance.md`, `benchmarks.md`, and `security.md` documents.
- **Draft Files:** Removed unreferenced root files `SYNAPSE_AUDIT_REPORT.md` and `SYNAPSE_AGENT_PROMPT.md  `.

## [1.1.1] - 2026-05-28

### Fixed

- **CRITICAL: N+1 query loop during edge resolution:** Migrated structural edge resolution to bulk FETCH queries, eliminating thousands of database calls per indexing run.
- **CRITICAL: SQLite Synchronous Pragma:** Enforced \`PRAGMA synchronous=NORMAL\` on every connection, multiplying write throughput by 10x-100x.
- **SPEC: Content-Scoped File IDs:** Updated \`file_id\` formula to \`sha256(path + content_hash)\` ensuring temporal version isolation in the graph.
- **HIGH: Wiki Generation Resiliency:** Implemented exponential backoff retries for LLM wiki generation to prevent data loss on transient network errors.
- **HIGH: Single Read Principle:** Optimized pipeline to read each file exactly once, halving I/O overhead.
- **MEDIUM: Automated Lesson Pruning:** Daemon now automatically prunes expired memory lessons hourly.
- **MEDIUM: Memory Bounded Indexing:** First-run indexing now processes in memory-bounded batches to prevent OOM on large repos.
- **LOW: Checkpoint Validation:** MCP \`create_checkpoint\` tool now validates all input fields to prevent malformed data.

### Added

- **Interactive Review Flow:** New CLI command \`synap lessons review\` for interactive management of agent-proposed lessons.
- **Context Monitoring:** New MCP tool \`signal_low_context\` for proactive agent context window monitoring.
- **Configurable Maintenance:** Added \`checkpoint_threshold\` and \`lesson_expiry_days\` to \`config.toml\`.
- **Improved Doctor:** \`synap doctor\` now checks for Git and GitHub CLI availability.
- **Onboarding Guidance:** \`synap init\` now provides explicit next steps for starting the system.

### Removed

- **Mock LLM Mode:** \`MockLLMProvider\` removed from the production codebase to maintain strict operational integrity.

## [1.1.0] - 2026-05-28

### Added — Git-Snapshot Projection & Performance Refactoring

- **Split Two-Path Indexing:** Separated initialization and incremental indexing into `_first_run_index` (full scan, CPU-parallelized) and `_incremental_index` (Git delta change detector).
- **Asynchronous Wiki Generation Queue:** Decoupled slow, non-deterministic LLM wiki generation from structural indexing using a persistent database queue (`wiki_queue`) processed asynchronously by a daemon worker.
- **Lazy Wiki Caching:** Added synchronous wiki generation fallback to CLI (`wiki show`), Web API, and MCP tools to dynamically build missing or stale pages on-demand.
- **Process Pool Parallel Parsing:** Parallelized Tree-sitter parsing on first run across all CPU cores utilizing process-based concurrency with independent parser instances.
- **SQLite Performance Hardening:**
    - WAL mode and NORMAL synchronous configuration enabled during writes.
    - Multi-row symbol and edge inserts batched into a single transaction via `executemany`.
    - Dot-separated `module_key` pre-computation and indexing for $O(1)$ module resolution.
    - SQLite FTS5 index integration for fast sub-millisecond symbol searches, avoiding full-table scans.
- **Web API Lazy Refreshes:** Updated the `/wiki/{filepath}` GET endpoint to perform lazy refreshes on stale or missing pages before returning content.

### Fixed

- **FTS5 Cascade Delete:** Added database trigger `tgr_symbols_delete` to automatically clean up virtual `symbols_fts` entries when parent symbols are deleted.
- **Duplicate File ID Collision:** Handled unique, path-scoped file identifier generation ensuring files with identical content (like empty `__init__.py`) do not conflict.

## [0.2.1] - 2026-05-27

### Added — Final Production Hardening & Release Execution

- `synap rollback --commit <ref>` option: directly target a commit by hash/reference without interactive selection prompt.
- `synap rollback --yes` / `-y` option: suppress confirmation prompt for non-interactive and scripted rollback flows.
- Non-interactive guard in `synap rollback`: fails fast with a clear error when used in piped/CI contexts without `--commit` or `--yes`.
- `synap rollback` invalid commit detection: validates commit reference via `git rev-parse --verify` and rejects unknown refs with a clear message.

### Fixed

- **SQLite migration short-circuit bug**: legacy un-versioned databases (user_version = 0) incorrectly skipped `CREATE TABLE IF NOT EXISTS` execution, leaving the `symbols` table and others uninitialized. The premature short-circuit is removed; all schema tables are now created correctly before bumping to version 1.
- **Python `import_from_statement` missing symbol extraction**: Tree-sitter AST parser only extracted the module identifier from `from X import Y` statements, discarding `Y`. Now correctly emits `module:symbol` pairs for all imported names, aliases, and grouped imports.
- **Namespace-aware call edge resolution**: Pass 2 import resolver now splits `module:symbol` import entries to narrow edge targets to the correct module file, eliminating false-positive dependency edges to duplicate class names in sibling namespaces.
- **FastAPI app version hardcoded**: `create_app()` used a hardcoded version string `"0.2.0"` instead of the canonical `__version__`. Now dynamically imported from `synap_git.__init__`.
- **Streaming generator cancellation safety**: confirmed `httpx` stream connections are closed cleanly on partial consumption (no socket leaks).
- **Degraded mode retry logic**: confirmed 2-stage exponential backoff and graceful structural fallback under fully-offline and timeout conditions.

### Changed

- Daemon resilience test (`test_daemon_resilience.py`) hardened against race condition where `SIGKILL` test read a stale PID from a prior run that had already exited.

## [0.2.0] - 2026-05-26

### Added — Final Polish & Release Readiness

- CLI usage management: `synap usage show` (displays Rich aggregated usage table and summary panel) and `synap usage clear`.
- CLI wiki management: `synap wiki list` and `synap wiki show <filepath>` (renders page in terminal via Rich Markdown).
- LLM call database logging: records `prompt_tokens`, `completion_tokens` for retrieval and wiki generation passes.
- Real-time daemon state: heartbeats integrated into `synap status`, `synap doctor`, and the Web UI status endpoints.
- Premium Web UI dashboard polish: dual L3 memory (Approved vs Pending) view, real-time LLM usage analytics, and active daemon PID badge.
- Defensive GHA release pipeline: `.github/workflows/release.yml` automates TestPyPI and PyPI publishing, tag alignment checking, and draft release generation.
- Clean Typer execution wrapper: intercepts configuration and credential exceptions to output actionable suggestions (e.g. `synap setup`) instead of tracebacks.

### Added — Hardening Loop 2: MCP Stability & Protocol Polish

- Deterministic MCP JSON envelope: every tool response carries `ok`, `data`, `warnings`, `trace_id`, `dirty_tree`.
- Structured error objects with `code`, `message`, and `suggestion` fields for all failure paths.
- `dirty_tree` propagation: agents are warned when the working tree is ahead of the index.
- `get_approved_memory()` and `get_pending_memory()` MCP tools exposing lesson trust status.
- `synap mcp verify` command to assert full protocol contract compliance.

### Added — Hardening Loop 3: Lesson System Trust & Memory Lifecycle

- Formal `LessonStatus` enum enforcing explicit state machine: `PENDING → APPROVED/REJECTED`, `APPROVED → EXPIRED`.
- Retrieval gating: only `APPROVED`, non-expired lessons are injected into LLM context as `# APPROVED SYSTEM MEMORY`.
- `prune_expired_lessons()` transitions stale lessons to `EXPIRED` state on demand.
- `approval_actor` field on lessons for full human-governance provenance.
- `synap memory status` — counts of pending, approved, expired lessons.
- `synap memory prune` — forces expiry evaluation and prunes dead memory.
- `synap memory verify` — checks approved lessons' `files_affected` against current repo state; reports dangling references.
- `synap lessons approve <id>` and `synap lessons reject <id>` — explicit human governance over pending lessons.

### Added — Hardening Loop 4: Tracing, Git Compliance & Release Hardening

- `GitIgnoreSpec` glob-to-regex parser in `RepositoryScanner` respects `.gitignore` patterns.
- Auto-protection: `SynapRuntime.bootstrap()` automatically adds `.synap/` to `.gitignore`.
- Enhanced binary file detection via extension blocklist + control-character ratio analysis.
- Symlink traversal prevention in `RepositoryScanner` (path-containment enforcement).
- `TraceStore` writes structured operational traces to `.synap/trace_latest.json`.
- Full hybrid retrieval tracing: latency timeline, token allocation, truncation explanations, structural hops, dirty-tree warnings.
- `/api/v1/trace/latest` REST endpoint exposing the latest trace.
- Diagnostic Web UI with visual latency timeline, source provenance table, and dirty-tree badge.
- Daemon heartbeat file (`.synap/daemon_heartbeat.json`) with PID, uptime, and recovery metrics.
- Daemon self-healing: SQLite corruption detected via `PRAGMA quick_check` triggers a wipe + re-bootstrap.
- `synap rollback` — interactive rollback to a previous git commit with lesson preservation.
- `synap recover` — explicit manual DB corruption recovery flow.
- `py.typed` marker for PEP 561 compliance.

### Changed

- CI pipeline split into 4 focused jobs: `lint`, `test`, `benchmark` (main only), `release-validation`.
- Release validation now runs `synap init` before `synap doctor` to ensure a valid Synap DB context.
- `pytest` configured with `asyncio_default_fixture_loop_scope = "function"` to eliminate deprecation warnings.
- Benchmark tests gated behind `benchmark` marker; skipped in fast PR CI passes.

### Fixed

- `synap doctor` in CI release validation step previously ran against an uninitialized directory.
- `ruff format` drift in `cli/main.py` and `indexer/daemon.py` resolved.

## [0.1.0] - 2026-05-25

### Added

- Core deterministic indexing engine using Tree-sitter and Git content hashes.
- 4-stage hybrid retrieval pipeline (Temporal, Structural, Lexical, Semantic).
- Model Context Protocol (MCP) server for IDE integration.
- "Why-This-Context" retrieval tracing system.
- Secure secret management via `python-keyring`.
- `synap doctor` for system validation.
- Diagnostic UI dashboard.

### Changed

- Refactored entire architecture from event-sourcing to deterministic Git projections.
- Consolidated storage into unified SQLite schema with Recursive CTE support.
- Upgraded documentation to production infrastructure standards.

### Removed

- Legacy "cognitive OS" and "graph operating system" abstractions.
- Speculative async priority queues and replay engines.
- Brittle regex-based parsers.
