# Synapse AI Engineer Guidelines & Agent Instructions

Welcome to the **Synapse** repository. Synapse is a high-performance, local Git-aware structural context engine for AI coding agents.

This document serves as the authoritative operational ruleset for AI coding agents, subagents, and automated engineering assistants contributing to or modifying this codebase.

---

## 1. System Architecture Overview

Synapse operates via a 3-layer context infrastructure:

* **L1 — Structural Code Graph**: AST traversal powered by Tree-sitter. Maps file-to-file imports, caller/callee symbols, class hierarchies, and Git OIDs into local SQLite graph tables.
* **L2 — Semantic Wiki**: Asynchronous documentation engine that maintains markdown summaries of files and modules, synced with Git history.
* **L3 — Behavioral Memory & Lessons**: Long-term agent memory storage (checkpoints, technical decisions, architectural constraints, and auto-extracted revert lessons).

---

## 2. Core Codebase Rules & Engineering Standards

### 2.1 Code Quality & Formatting
* **Python Target**: Python 3.12+
* **Type Safety**: Strictly enforced via `mypy` (`strict = true`). All function parameters and return types MUST have explicit type annotations.
* **Linter & Formatter**: `ruff` (`line-length = 100`, double quotes). Run `ruff check .` and `ruff format .` on every change.
* **Data Validation**: Use `pydantic` v2 and `pydantic-settings` v2 models.

### 2.2 Error Handling & Logging
* **Structured Logging**: Use `structlog` (`structlog.get_logger()`). Include key-value context fields (e.g., `path`, `error`, `commit`).
* **No Swallowed Exceptions**: Never use bare `except:` or silent `try-except-pass` blocks without logging.
* **Empirical Log Evidence**: Base all diagnostics on full stack traces and empirical log evidence.

### 2.3 Storage & Concurrency
* **Database Engine**: SQLite with Write-Ahead Logging (`WAL` mode) and `PRAGMA synchronous = NORMAL`.
* **Async I/O Safety**: Never block the asyncio main loop. Wrap heavy synchronous file reads, subprocess executions, or AST parses in `asyncio.to_thread()`.
* **Daemon Signal Safety**: Background processes MUST handle `SIGINT` and `SIGTERM` cleanly, releasing `.synap/daemon.pid` and `.synap/daemon_heartbeat.json` lockfiles.

---

## 3. Workflow & Testing Rules

### 3.1 Verification Requirement
* Every bug fix or feature implementation MUST be verified by executing tests:
  ```bash
  .venv/bin/pytest -v
  ```
* Ensure code passes static analysis:
  ```bash
  .venv/bin/ruff check .
  .venv/bin/mypy src
  ```

### 3.2 Documentation Integrity
* Keep `README.md`, `CHANGELOG.md`, and inline docstrings synchronized when modifying CLI options, configuration settings, or public MCP tool interfaces.

---

## 4. Release Checklist for AI Engineers

When releasing a new version:
1. Ensure all tests in `tests/` pass cleanly.
2. Verify package version in `src/synap_git/__init__.py`.
3. Update `CHANGELOG.md` with release highlights.
4. Verify CLI subcommands (`synap setup`, `synap start`, `synap stop`, `synap status`, `synap doctor`).
