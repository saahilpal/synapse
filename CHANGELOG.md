# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
