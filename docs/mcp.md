# Model Context Protocol (MCP) Integration

Synap exposes a suite of tools through the standard Model Context Protocol (MCP) using a Stdio transport. This allows AI coding agents in environments like Cursor or Windsurf to ground their actions in codebase context.

---

## Connection Configuration

Generate the connection parameters using:
```bash
synap mcp config .
```

Copy the generated block into your IDE settings under MCP Servers:
```json
{
  "mcpServers": {
    "synap": {
      "command": "/usr/local/bin/python",
      "args": ["-m", "synap_git.cli", "mcp", "start", "/Users/username/project"],
      "autoConnect": true
    }
  }
}
```

---

## Deterministic JSON Envelope

Every MCP tool invocation returns a JSON string structured inside a standardized envelope.

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
* `warnings` — List of warnings (e.g. `["Working tree is dirty. Index may be stale."]`).
* `dirty_tree` — Boolean flag indicating whether the Git working directory contains uncommitted changes.

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
* `error.code` — Standardized codes: `INTERNAL_ERROR`, `INDEX_STALE`, or `NOT_FOUND`.

---

## Tool Reference

### 1. `get_status`
Retrieves indexing state, branch name, and HEAD commit hashes.
* **Input Schema:** None
* **Output Payload (`data`):**
  ```json
  {
    "repository_path": "/Users/username/project",
    "branch": "main",
    "git_commit": "d980cf7f4f6b2ea8b75e1c4df2e9d2d854eb75e1",
    "active_commit": "d980cf7f4f6b2ea8b75e1c4df2e9d2d854eb75e1",
    "symbols": 420,
    "files": 38,
    "mode": "active",
    "is_dirty": false
  }
  ```

### 2. `search`
Queries the hybrid index for grounded context matches.
* **Input Schema:**
  * `query` (string, required): Keyword or phrase search terms.
  * `max_tokens` (integer, optional, default: 4000): Token limit budget.
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
Saves current agent thoughts and files as a branch-specific checkpoint.
* **Input Schema:**
  * `doing` (string, required): Action description.
  * `changed_files` (array of strings, required): Relative file paths.
  * `next_step` (string, required): Future planned steps.
  * `blockers` (string, required): Blockers or obstacles.
* **Output Payload (`data`):**
  ```json
  {
    "status": "success",
    "checkpoint_id": "18f5e27a-5b12-4011-b124-7fcd491baee2"
  }
  ```

### 4. `restore_checkpoint`
Restores the latest checkpoint saved on the current branch.
* **Input Schema:** None
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
Logs technical or design decisions to the project database logs.
* **Input Schema:**
  * `content` (string, required): Text description of the decision.
  * `context_info` (string, required): Contextual info leading to the decision.
* **Output Payload (`data`):**
  ```json
  {
    "status": "success",
    "decision_id": "9a01cf5b-7c18-4012-9c10-8b1e4cfb395b"
  }
  ```

### 6. `verify_system`
Checks SQLite database integrity and returns diagnostics.
* **Input Schema:** None
* **Output Payload (`data`):**
  ```json
  {
    "database_integrity": "ok",
    "status": {
      "branch": "main",
      "symbols": 420,
      "files": 38
    }
  }
  ```

### 7. `submit_lesson_analysis`
Submits analysis text explaining a failure or revert event to the pending memory queue.
* **Input Schema:**
  * `lesson_id` (string, required): Unique identifier of the lesson.
  * `why_failed` (string, required): Root cause analysis explaining why the code failed.
* **Output Payload (`data`):**
  ```json
  {
    "status": "success",
    "message": "Lesson awaiting human approval"
  }
  ```

### 8. `get_approved_memory`
Retrieves all approved, active memory lessons that the agent must adhere to.
* **Input Schema:** None
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
Retrieves all pending lessons awaiting review.
* **Input Schema:** None
* **Output Payload (`data`):**
  ```json
  {
    "status": "success",
    "lessons": []
  }
  ```

### 10. `signal_low_context`
Notifies that the agent's context is running low, recommending a checkpoint if usage exceeds config threshold.
* **Input Schema:**
  * `token_count` (integer, required): Active token usage count.
  * `capacity` (integer, required): Context window limit.
* **Output Payload (`data`):**
  ```json
  {
    "should_checkpoint": true,
    "message": "Context usage is at 74.0%. Threshold (60.0%) reached. Checkpoint recommended."
  }
  ```
