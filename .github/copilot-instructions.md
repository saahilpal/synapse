# GitHub Copilot Custom Instructions for Synapse

## Architecture Overview
Synapse is a local Git-aware structural context engine for AI coding agents.
- **L1**: AST parsing & import resolution via Tree-sitter -> SQLite graph.
- **L2**: Markdown Wiki summaries of code modules via async background LLM worker.
- **L3**: Behavioral memory, lessons from git reverts, L3 checkpoints.

## Code Style & Patterns
- **Python**: Python 3.12+
- **Type Annotations**: Strict typing for all public and private functions.
- **Pydantic**: Use Pydantic v2 BaseModels for request/response & config parsing.
- **Logging**: Use `structlog.get_logger()`. Include context key-value pairs.
- **Error Handling**: Do not swallow exceptions silently; log with `error` or `warning`.
- **Async I/O**: Use `asyncio.to_thread` when calling blocking file or DB functions in async contexts.
