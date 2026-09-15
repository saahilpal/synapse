# Model Context Protocol (MCP) Integration

Synap exposes a rich suite of context tools through the standard Model Context Protocol (MCP) using a standard input/output (`stdio`) transport. This enables AI coding agents in environments like Cursor, Windsurf, Claude Desktop, and custom agentic frameworks to ground their operations in real-time codebase structure.

---

## Connection Configuration

Generate the exact connection parameters for your current environment:
```bash
synap mcp config .
```

### 1. Cursor Configuration
Add to `.cursor/mcp.json` or your global Cursor Settings (`Cursor Settings -> Features -> MCP`):
```json
{
  "mcpServers": {
    "synap": {
      "command": "synap",
      "args": ["mcp", "serve", "/absolute/path/to/repository"]
    }
  }
}
```

### 2. Windsurf Configuration
Add to `~/.codeium/windsurf/mcp_config.json`:
```json
{
  "mcpServers": {
    "synap": {
      "command": "synap",
      "args": ["mcp", "serve", "/absolute/path/to/repository"]
    }
  }
}
```

### 3. Claude Desktop Configuration
Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "synap": {
      "command": "synap",
      "args": ["mcp", "serve", "/absolute/path/to/repository"]
    }
  }
}
```

---

## Transport & Stdio Hygiene

* **Pure JSON-RPC on `stdout`:** Synap strictly reserves standard output for JSON-RPC messages required by the MCP protocol specification.
* **Diagnostics on `stderr`:** All system logging, operational metrics, and error diagnostics from `structlog` are routed directly to standard error (`stderr`), preventing protocol stream parsing failures.
* **Verification:** Test connection viability using the CLI verification command:
  ```bash
  synap mcp verify .
  ```

---

## Deterministic JSON Envelope

Every MCP tool invocation returns a JSON string enclosed within a standardized, predictable envelope.

### Successful Response Schema
```json
{
  "ok": true,
  "data": {},
  "warnings": [],
  "trace_id": "8b51d087-93e1-4560-9304-c36b412ee17f",
  "dirty_tree": false
}
```
* `data` — The payload returned by the specific tool.
* `warnings` — List of warnings (e.g., `["Working tree is dirty. Index may be stale."]`).
* `dirty_tree` — Boolean flag indicating whether the Git working tree contains uncommitted changes.
* `trace_id` — Unique UUID string tracing the query lifecycle.

### Error Response Schema
```json
{
  "ok": false,
  "error": {
    "code": "NOT_FOUND",
    "message": "No checkpoint found for current branch.",
    "suggestion": "Ensure checkpoints exist for this branch."
  },
  "warnings": [],
  "trace_id": "8b51d087-93e1-4560-9304-c36b412ee17f",
  "dirty_tree": false
}
```
* `error.code` — Standardized error codes: `INTERNAL_ERROR`, `INDEX_STALE`, or `NOT_FOUND`.

---

## Tool Reference

### 1. `get_status`
Retrieves indexing state, active Git branch, HEAD commit hashes, and file counts.
* **Input Parameters:** None
* **Output Payload (`data`):**
  ```json
  {
    "repository_path": "/Users/username/project",
    "branch": "main",
    "git_commit": "d980cf7f4f6b2ea8b75e1c4df2e9d2d854eb75e1",
    "active_commit": "d980cf7f4f6b2ea8b75e1c4df2e9d2d854eb75e1",
    "symbols": 770,
    "files": 115,
    "mode": "active",
    "is_dirty": false
  }
  ```

### 2. `search`
Executes hybrid structural search for grounded context matches.
* **Input Parameters:**
  * `query` (string, required): Search phrase or symbol name.
  * `max_tokens` (integer, optional, default: 4000): Token budget limit.
* **Output Payload (`data`):**
  ```json
  {
    "result": "Grounded answer text summarizing source symbols...",
    "context": [
      {
        "symbol_id": "8c599187a...",
        "name": "parse_args",
        "kind": "function_definition",
        "start_line": 12,
        "end_line": 28,
        "source_path": "src/cli.py",
        "reason": "lexical:'parse_args'"
      }
    ],
    "trace": {
      "trace_id": "2d1b09b5-...",
      "latency_ms": 142.5,
      "nodes_explored": 8,
      "tokens_used": 1240
    }
  }
  ```

### 3. `create_checkpoint`
Saves the agent's task state and affected files as a branch-specific checkpoint.
* **Input Parameters:**
  * `doing` (string, required): Active task description.
  * `changed_files` (array of strings, required): Relative paths of modified files.
  * `next_step` (string, required): Planned subsequent actions.
  * `blockers` (string, required): Identified blockers or notes.
* **Output Payload (`data`):**
  ```json
  {
    "status": "success",
    "checkpoint_id": "18f5e27a-5b12-4011-b124-7fcd491baee2"
  }
  ```

### 4. `restore_checkpoint`
Restores the latest checkpoint saved on the current branch.
* **Input Parameters:** None
* **Output Payload (`data`):**
  ```json
  {
    "checkpoint_id": "18f5e27a-5b12-4011-b124-7fcd491baee2",
    "branch": "main",
    "commit_hash": "d980cf7...",
    "doing": "Refactoring API",
    "changed_files": "[\"src/api.py\"]",
    "next_step": "Run tests",
    "blockers": "None",
    "created_at": 1716000000
  }
  ```

### 5. `log_decision`
Logs technical and architectural decisions to persistent project storage.
* **Input Parameters:**
  * `content` (string, required): Description of the technical decision.
  * `context_info` (string, required): Contextual rationale leading to the choice.
* **Output Payload (`data`):**
  ```json
  {
    "status": "success",
    "decision_id": "9a01cf5b-7c18-4012-9c10-8b1e4cfb395b"
  }
  ```

### 6. `verify_system`
Checks SQLite database integrity and verifies runtime diagnostics.
* **Input Parameters:** None
* **Output Payload (`data`):**
  ```json
  {
    "database_integrity": "ok",
    "status": {
      "branch": "main",
      "symbols": 770,
      "files": 115
    }
  }
  ```

### 7. `submit_lesson_analysis`
Submits root cause analysis for a pending memory lesson (e.g., following a revert event).
* **Input Parameters:**
  * `lesson_id` (string, required): Unique identifier of the lesson.
  * `why_failed` (string, required): Explanation of why the code failed and what rule should be followed.
* **Output Payload (`data`):**
  ```json
  {
    "status": "success",
    "message": "Lesson awaiting human approval"
  }
  ```

### 8. `get_approved_memory`
Retrieves all approved, active memory lessons that agents must strictly obey.
* **Input Parameters:** None
* **Output Payload (`data`):**
  ```json
  {
    "status": "success",
    "lessons": [
      {
        "lesson_id": "1fa30b5...",
        "branch": "main",
        "revert_commit": "c4d0a92...",
        "reverted_from": "a1b2c3d...",
        "what_failed": "Database migration script syntax error",
        "why_failed": "Do not write un-aliased columns in postgres migration scripts.",
        "files_affected": "[\"migrations/001.sql\"]",
        "status": "approved",
        "created_at": 1716000000,
        "expires_at": 1716604800,
        "approval_actor": "cli_user"
      }
    ]
  }
  ```

### 9. `get_pending_memory`
Retrieves pending lessons awaiting human review.
* **Input Parameters:** None
* **Output Payload (`data`):**
  ```json
  {
    "status": "success",
    "lessons": []
  }
  ```

### 10. `signal_low_context`
Notifies that the agent is approaching context limits, recommending a checkpoint if usage exceeds the configured threshold (`checkpoint_threshold`).
* **Input Parameters:**
  * `token_count` (integer, required): Current token usage count.
  * `capacity` (integer, required): Context window limit.
* **Output Payload (`data`):**
  ```json
  {
    "should_checkpoint": true,
    "message": "Context usage is at 74.0%. Threshold (60.0%) reached. Checkpoint recommended."
  }
  ```
