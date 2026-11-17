---
name: synap
description: Fast local Git-aware structural context, AST symbol graph navigation, and behavioral memory engine for AI coding agents. Triggers: fetch context before modifying code or starting tasks; query symbol graphs or skeletons before reading full files; save memory checkpoints, architectural decisions, and failure lessons after completing changes; never store secrets or credentials.
---

# Synapse Agent Skill

Synapse provides zero-cost local structural context and memory.

## Why Use Synapse (Measured Benchmarks)
- **85.2% Token Reduction**: `get_skeleton` strips function bodies, keeping signatures/types.
- **Sub-15ms Indexing**: Git hook zero-daemon indexing (84ms file change, 14ms no-op).
- **Fast Traversal**: P95 symbol lookup 2.1ms; graph neighborhood 0.8ms.
- **Zero Cloud / Cost**: 100% offline SQLite WAL; zero telemetry; zero API burn.

## 3-Step Agent Loop

### 1. When to Fetch Context (Before Work)
- **Start**: Call MCP `get_session_preamble()` (or `synap context`) to load branch, dirty diff, hubs, and negative constraints (<750 tokens).
- **Resume**: Call `restore_checkpoint(id)` to restore context after compaction.
- **Blast Radius**: Run `get_diff()` and `get_test_recommendations()` for affected tests.

### 2. Search Before Grepping
- **Find Symbols**: Call `search(query="...", summary_only=True)` before raw grep.
- **Read Signatures**: Call `get_skeleton(file_path="...")` to inspect interfaces.
- **Read Code**: Call `read_symbol(symbol="...", file_path="...")` for specific functions.
- **Check Callers**: Call `get_callers(symbol)` before editing shared symbols.

### 3. When to Write Memory (After Decisions & Fixes)
- **Handoff**: Call `create_checkpoint(doing="...", next_step="...")` before turn completion.
- **Decisions**: Call `log_decision(content="...", context_info="...")` on structural choices.
- **Memory**: Save facts with `remember(key="...", content="...")`; retrieve with `recall(key="...")`.
- **Lessons**: Check approved lessons in preamble to prevent reverted bugs.

### 4. What NEVER to Store
- **NEVER Store**: Secrets, API keys, passwords, credentials, or raw stdout.
- **CLI Commands**: `synap context`, `synap search <q>`, `synap skeleton <f>`, `synap test`, `synap doctor`.
