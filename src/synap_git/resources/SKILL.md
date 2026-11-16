---
name: synap
description: Persistent Git-aware structural context, symbol graph navigation, and behavioral memory engine for AI coding agents. Triggers: fetch context before modifying code or starting tasks; query symbol graphs or skeletons before reading full files; save memory checkpoints, architectural decisions, and failure lessons after completing changes; never store secrets, credentials, or ephemeral logs.
---

# Synap Agent Guidance

Synapse is a local Git-aware structural context and memory engine. Use Synapse to navigate code token-efficiently and preserve state across agent turns.

## 1. When to Fetch Context (Read Path)
- **Session Start**: Always call `get_session_preamble()` at the beginning of a task to inspect active branch, latest checkpoint, and active negative constraints (revert lessons).
- **Resuming Work**: If a previous task or checkpoint exists, call `restore_checkpoint()`.
- **Before Modifying Code**:
  - Never read entire unfamiliar files when exploring.
  - Call `search(query="<symbol_or_keyword>", summary_only=True)` to discover candidate symbols.
  - Call `get_skeleton(file_path="...")` to view class/function signatures and docstrings (85% token reduction).
  - Call `get_outline(file_path="...")` to map file structure and line ranges.
  - Call `read_symbol(symbol="...", file_path="...")` to retrieve only the required symbol implementation.
  - Call `get_callers(symbol="...")` or `get_neighborhood(symbol="...", direction="upstream")` to check caller blast radius before editing.

## 2. When to Write Memory (Write Path)
- **Task Pauses & Handoffs**: Call `create_checkpoint(doing="...", next_step="...")` before finishing your turn, switching tasks, or when context window is filling up.
- **Architectural & Design Choices**: Call `log_decision(content="...", context_info="...")` immediately after deciding conventions, structural refactors, or technology tradeoffs.
- **Environment & Non-Code Facts**: Call `remember(key="...", content="...")` for verified runtime facts, ports, or environment requirements. Retrieve with `recall(key="...")`.
- **Bug Fixes & Post-Mortems**: Ensure failure root-causes and negative constraints are recorded so future agents do not repeat reverted mistakes.

## 3. Query Phrasing & Result Usage
- **Query Phrasing**: Use concise, exact symbol identifiers (e.g. `parse_ast`, `SynapRuntime`, `sqlite.py`) or narrow technical terms. Avoid conversational sentences in search queries.
- **Result Usage**:
  - Use search scores and symbol kinds to prioritize navigation targets.
  - Use skeleton outputs to plan edits without reading implementation bodies.
  - Use `get_diff()` and `get_test_recommendations()` to identify impacted tests before running verification.

## 4. What NEVER to Store
- **NEVER Store**:
  - Secrets, API keys, private tokens, passwords, or credentials.
  - Transient runtime outputs, ephemeral debug dumps, or raw terminal logs.
  - Duplicate code snippets or large file contents already tracked by Git.
  - PII (personally identifiable information) or proprietary credentials.
