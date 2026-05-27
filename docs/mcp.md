# MCP Integration

Synap exposes its capabilities via the **Model Context Protocol (MCP)**, allowing AI agents to perform grounded repository search and task analysis.

## IDE Setup

To connect Synap to your IDE (Cursor, Claude Desktop, Roo, etc.), run:
```bash
synap mcp config .
```
This will output a JSON configuration block. Follow the IDE-specific instructions below.

### Cursor
1. Open Cursor Settings -> Models -> MCP.
2. Click "Add New MCP Server".
3. Use the `command` and `args` from the Synap output.

### Claude Desktop
1. Open `~/Library/Application Support/Claude/claude_desktop_config.json`.
2. Add the `synapse` block to `mcpServers`.

## Available Tools

- `get_status`: Returns current branch, HEAD commit, and symbol counts.
- `search`: Performs hybrid search and returns grounded context + diagnostic trace.
- `get_task_context`: Generates a bounded context package for a specific development task.

---

## Agent Usage Example

**User:** "Explain the authentication flow."

**Agent (Cursor/Claude):**
1. Calls `search(query="authentication flow")`.
2. Receives symbols from `auth.py`, `service.py`, and `models.py`.
3. Explains the flow using the grounded code provided by Synap.
4. Cites exact file paths and symbol names.
