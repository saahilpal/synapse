# Changelog

All notable changes to Synapse will be documented in this file.

The format follows Keep a Changelog conventions, and the project intends to use semantic versioning after the first public release.

## [Unreleased]

### Added

- **Validation State Tristate**: Introduced validation state (`Validated`, `Assumed`, `Invalidated`) on semantic annotations, graph nodes, and edges, with full serialization and frontend UI badge rendering.
- **Architectural Migration Audit**: Created `docs/architecture_migration_audit.md` to map repository-wide terminology.

### Changed

- **Substrate Repositioning**: Repositioned project from "Temporal Cognitive OS / AI OS" to **Temporal Source Context Management Substrate** and **Causal Software Evolution Graph**.
- **Terminology Convergence**: Aligned positioning, documentation, and user-facing CLI / API strings with the new substrate and causal graph model.
- **Deterministic vs AI Boundary Hardening**: Formalized the Semantic Overlay Contract, establishing that AI annotations can never modify structural AST or Git lineage truth.
- **Bounded Replay Model**: Explicitly defined replay as bounded temporal reconstruction using checkpoint snapshots and WAL logging.

- Interactive Visual Cognition UI (FastAPI and D3.js force-directed graph with timeline scrubber, progressive disclosure side panel, dynamic legend, note/incident logs).
- Projection Engine for slicing temporal cognition facts into bounded graphs (`overview`, `subsystem`, `replay`, `drift`, `assumption`, `incident`, and `branch`).
- Projection caching in SQLite database under `projection_cache` table.
- Security hardening module (`SecretRedactor` recursive credential scrubber, `SafeMarkdownRenderer` XSS filter, `InputValidator` clamp and safe path checks, `TrustClassifier`).
- Extraction of GraphNode and GraphEdge tuples during scan (package, module, document, dependency, decision, assumption nodes, depends_on, documents, and reference edges).
- Initial production-grade architecture documentation.
- Repository structure for runtime, cognition, storage, Git, MCP, API, and security modules.
- ADR system and initial architecture decisions.
- Engineering standards, security model, and roadmap.
- Typed runtime configuration with profiles, modes, storage paths, worker settings, logging mode, indexing mode, and MCP settings.
- Structlog-based observability with operation tracing and correlation IDs.
- Immutable schema-versioned domain models for events, context objects, semantic objects, graph objects, snapshots, trust, provenance, confidence, and validity.
- Content-addressed compressed object store under `.synapse/objects/`.
- SQLite WAL event store with migrations, append-only events, context DAG indexes, semantic/graph indexes, trust records, active heads, snapshots, and health checks.
- Context DAG engine with context creation, ancestry traversal, divergence, diff, and rollback activation.
- Cognitive Evolution Engine for semantic diffs, context timelines, confidence evolution, branch divergence, and cognitive replay.
- Assumption Engine for active, stale, and invalidated assumption tracking.
- Temporal cognition models for validity intervals, confidence windows, provenance chains, and temporal facts.
- GitPython-backed Git state detection for commits, branches, checkouts, merges, rebases, and reverts.
- Repository scanner for manifests, dependencies, languages, folder roles, and bounded file indexing.
- Markdown cognition extraction with heading hierarchy, links, semantic kinds, provenance, confidence, and stable IDs.
- Code parser foundation for Python and JS/TS structure extraction with Tree-sitter-ready boundaries.
- Async event pipeline, runtime daemon, replay engine, snapshot engine, drift detector, MCP facade, and real CLI commands.
- Initial pytest coverage for object integrity, replay determinism, DAG consistency, Git detection, serialization, migrations, concurrency, and extraction.
- Replay correctness package with deterministic trace output, context lineage reconstruction, active-head validation, checkpoint-aware replay, and corruption diagnostics.
- Journaled cognitive transaction engine for atomic event/object/context commits, idempotent transaction replay, and interrupted transaction recovery.
- Lineage verification package that acts as `git fsck` for cognition DAGs by detecting missing parents, corrupt objects, cycles, and invalid active heads.
- Temporal query, semantic impact, confidence scoring, drift timeline, temporal graph reconstruction, incident anchoring, and hot/warm/cold cognition tier foundations.
- CLI commands for `impact`, `lineage`, `confidence-decay`, `temporal-graph`, and `incident`.
- SQLite transaction journal tables for cognition transactions and transaction-object references.

### Changed

- SQLite storage schema bumped to version 4 with fast composite indices on context_hash, graph nodes/edges, and automatic migration on startup.
- Refactored `TemporalGraphEngine.reconstruct` to fetch semantic objects in a single bulk query to eliminate the N-query database bottleneck.
- Repositioned Synapse from a Git-native cognition store toward temporal cognition infrastructure.
- MCP/runtime search terminology now favors `search_cognition`; `search_memory` remains as a compatibility alias.
- Package metadata and CLI help now use temporal cognition positioning.
- Context hashing now uses one canonical primitive path for Pydantic models and datetimes.
