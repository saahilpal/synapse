# Synapse Engineering & Operational Guidelines

## 1. Engineering Standards
- **Python Target**: Python 3.12+
- **Strict Typing**: Strictly enforced via `mypy` (`strict = true`). All function parameters and return types must have explicit annotations.
- **Linter & Formatter**: `ruff` (`line-length = 100`, double quotes). Run `ruff check .` and `ruff format .` on every change.
- **Structured Logging**: `structlog` (`structlog.get_logger()`). Never swallow exceptions.
- **Verification**: Run `.venv/bin/pytest -v`, `.venv/bin/ruff check .`, and `.venv/bin/mypy src`.

## 2. Synapse Navigation & Context Architecture
- **Session Start**: Call `get_session_preamble()`. If resuming an existing task, call `restore_checkpoint()`.
- **Progressive Exploration**:
  1. Call `search(query="...", summary_only=True)` to discover symbol names and paths without token bloat.
  2. Call `get_skeleton(file_path="...")` to inspect function signatures, docstrings, and classes (85% token savings).
  3. Call `read_symbol(symbol="...", file_path="...")` to view exact symbol implementations without reading the whole file.
  4. Call `get_callers(symbol="...")` to check caller blast radius before modifying code.
- **Verification & Test Execution**:
  1. Call `get_diff()` to review uncommitted code changes.
  2. Call `get_test_recommendations()` to identify impacted tests and receive recommended pytest commands.
- **Session Checkpointing**:
  - Call `create_checkpoint(doing="...", next_step="...")` before ending complex tasks or when context is high.
  - Call `log_decision(content="...", context_info="...")` for architectural choices.
  - Call `remember(key="...", content="...")` for critical runtime observations, and `recall(key="...")` to retrieve them.

# Synapse AI Agent Directives

This project uses Synapse for persistent structural context, graph navigation, and memory.
Follow these operational guidelines:

## 1. Session Start & Context Loading
- At the start of any conversation or task, call the MCP tool `get_session_preamble()`.
- Review the active branch, latest checkpoint, and approved negative constraints (lessons).
- If resuming an existing task, call `restore_checkpoint()`.
- Never repeat failures listed in approved lessons.

## 2. Progressive Code Navigation & Search
- When exploring, call `search(query="...", summary_only=True)` first to find relevant symbols with minimal token overhead.
- Use `get_skeleton(file_path="...")` to inspect function signatures, docstrings, and classes without implementation bodies (85% token savings).
- Use `get_outline(file_path="...")` to inspect file structure and line ranges.
- Use `read_symbol(symbol="...", file_path="...")` to read exact symbol code without reading entire files.
- Before modifying a symbol, use `get_callers(symbol="...")` or `get_neighborhood(symbol="...", direction="upstream")` to check caller blast radius.

## 3. Verification & Testing
- Use `get_diff()` to review uncommitted code changes.
- Use `get_test_recommendations()` to identify impacted test files and receive recommended pytest commands.

## 4. Session Checkpointing & Memory
- Before ending a complex task or when context is high, call `create_checkpoint(doing="...", next_step="...")`.
- Log key architectural decisions using `log_decision(content="...", context_info="...")`.
- Save critical environment facts or non-code observations using `remember(key="...", content="...")`, and look up with `recall(key="...")`.
