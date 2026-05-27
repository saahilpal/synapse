# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- CLI cost management: `synap cost show` (displays Rich aggregated pricing table and summary panel) and `synap cost clear`.
- CLI wiki management: `synap wiki list` and `synap wiki show <filepath>` (renders page in terminal via Rich Markdown).
- LLM call database logging: records `prompt_tokens`, `completion_tokens`, and calculates `cost_usd` dynamically for retrieval and wiki generation passes.
- Real-time daemon state: heartbeats integrated into `synap status`, `synap doctor`, and the Web UI status endpoints.
- Premium Web UI dashboard polish: dual L3 memory (Approved vs Pending) view, real-time LLM cost analytics, and active daemon PID badge.
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
