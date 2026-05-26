# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-05-26

### Added — Hardening Loop 2: MCP Stability & Protocol Polish
- Deterministic MCP JSON envelope: every tool response carries `ok`, `data`, `warnings`, `trace_id`, `dirty_tree`.
- Structured error objects with `code`, `message`, and `suggestion` fields for all failure paths.
- `dirty_tree` propagation: agents are warned when the working tree is ahead of the index.
- `get_approved_memory()` and `get_pending_memory()` MCP tools exposing lesson trust status.
- `synapse mcp verify` command to assert full protocol contract compliance.

### Added — Hardening Loop 3: Lesson System Trust & Memory Lifecycle
- Formal `LessonStatus` enum enforcing explicit state machine: `PENDING → APPROVED/REJECTED`, `APPROVED → EXPIRED`.
- Retrieval gating: only `APPROVED`, non-expired lessons are injected into LLM context as `# APPROVED SYSTEM MEMORY`.
- `prune_expired_lessons()` transitions stale lessons to `EXPIRED` state on demand.
- `approval_actor` field on lessons for full human-governance provenance.
- `synapse memory status` — counts of pending, approved, expired lessons.
- `synapse memory prune` — forces expiry evaluation and prunes dead memory.
- `synapse memory verify` — checks approved lessons' `files_affected` against current repo state; reports dangling references.
- `synapse lessons approve <id>` and `synapse lessons reject <id>` — explicit human governance over pending lessons.

### Added — Hardening Loop 4: Tracing, Git Compliance & Release Hardening
- `GitIgnoreSpec` glob-to-regex parser in `RepositoryScanner` respects `.gitignore` patterns.
- Auto-protection: `SynapseRuntime.bootstrap()` automatically adds `.synapse/` to `.gitignore`.
- Enhanced binary file detection via extension blocklist + control-character ratio analysis.
- Symlink traversal prevention in `RepositoryScanner` (path-containment enforcement).
- `TraceStore` writes structured operational traces to `.synapse/trace_latest.json`.
- Full hybrid retrieval tracing: latency timeline, token allocation, truncation explanations, structural hops, dirty-tree warnings.
- `/api/v1/trace/latest` REST endpoint exposing the latest trace.
- Diagnostic Web UI with visual latency timeline, source provenance table, and dirty-tree badge.
- Daemon heartbeat file (`.synapse/daemon_heartbeat.json`) with PID, uptime, and recovery metrics.
- Daemon self-healing: SQLite corruption detected via `PRAGMA quick_check` triggers a wipe + re-bootstrap.
- `synapse rollback` — interactive rollback to a previous git commit with lesson preservation.
- `synapse recover` — explicit manual DB corruption recovery flow.
- `py.typed` marker for PEP 561 compliance.

### Changed
- CI pipeline split into 4 focused jobs: `lint`, `test`, `benchmark` (main only), `release-validation`.
- Release validation now runs `synapse init` before `synapse doctor` to ensure a valid Synapse DB context.
- `pytest` configured with `asyncio_default_fixture_loop_scope = "function"` to eliminate deprecation warnings.
- Benchmark tests gated behind `benchmark` marker; skipped in fast PR CI passes.

### Fixed
- `synapse doctor` in CI release validation step previously ran against an uninitialized directory.
- `ruff format` drift in `cli/main.py` and `indexer/daemon.py` resolved.

## [0.1.0] - 2026-05-25

### Added
- Core deterministic indexing engine using Tree-sitter and Git content hashes.
- 4-stage hybrid retrieval pipeline (Temporal, Structural, Lexical, Semantic).
- Model Context Protocol (MCP) server for IDE integration.
- "Why-This-Context" retrieval tracing system.
- Secure secret management via `python-keyring`.
- `synapse doctor` for system validation.
- Diagnostic UI dashboard.

### Changed
- Refactored entire architecture from event-sourcing to deterministic Git projections.
- Consolidated storage into unified SQLite schema with Recursive CTE support.
- Upgraded documentation to production infrastructure standards.

### Removed
- Legacy "cognitive OS" and "graph operating system" abstractions.
- Speculative async priority queues and replay engines.
- Brittle regex-based parsers.
