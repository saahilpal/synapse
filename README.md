# Synapse 🧠

<p align="center">
  <b>The Deterministic Context Injector for AI Coding Agents.</b>
</p>

<p align="center">
  <a href="https://github.com/saahilpal/synapse/actions"><img src="https://img.shields.io/github/actions/workflow/status/saahilpal/synapse/ci.yml?style=flat-square&color=3b82f6" alt="CI Status"></a>
  <a href="LICENSE.md"><img src="https://img.shields.io/github/license/saahilpal/synapse?style=flat-square&color=cbd5e1" alt="License"></a>
  <a href="SYNAPSE_BUILD_SPEC.md"><img src="https://img.shields.io/badge/spec-v1.0-green?style=flat-square" alt="Spec Compliant"></a>
</p>

---

Synapse is **NOT a RAG system.** It is a strict, deterministic background daemon that mirrors your Git state and proactively pushes exact contextual boundaries to AI coding agents via the Model Context Protocol (MCP). Agents do not query Synapse—Synapse *injects* reality into Agents.

## 🏛️ Philosophy & Vision

1. **DETERMINISTIC FIRST:** If the agent sees it, it exists exactly as shown in the local filesystem.
2. **PUSH, NOT PULL:** Agents are terrible at querying for what they don't know exists. Synapse bounds their context upfront.
3. **NOTHING HAPPENS SILENTLY:** Every action, decision, and LLM call is tracked, costed, and logged.
4. **LOCAL ONLY:** Your code never leaves your machine unless you explicitly configure a remote LLM. All state is kept in `.synapse/synapse.db`.
5. **MIRROR GIT EXACTLY:** Synapse's state machine is perfectly synced to `HEAD`. If you switch branches, your agent's memory switches branches instantly.

---

## 🏗️ High-Level Architecture (HLD)

Synapse bridges the gap between your local file system, Git history, and the LLM via a 3-layer indexing strategy.

```mermaid
graph TD
    subgraph Local Repository
        FS[File System]
        Git[Git History]
    end

    subgraph Synapse Daemon
        I[Indexer Engine]
        DB[(SQLite synapse.db)]
        W[Wiki Engine .synapse/wiki/]
        M[Context Injector memory.py]
    end

    subgraph IDE / AI
        MCP[MCP Server]
        Agent[AI Coding Agent]
    end

    FS -->|Change Events| I
    Git -->|Branch/Revert Events| I
    I -->|L1 Structural| DB
    I -->|L2 Semantic| W
    I -->|L3 Behavioral| DB

    DB --> M
    W --> M
    M -->|Injection Payload| MCP
    MCP <-->|Read/Write Tools| Agent
```

---

## 🧩 The 3 Layers of Context

Synapse provides three distinct layers of context to completely ground the agent:

### 1. L1: Structural (The Truth)
Deterministic mapping of code architecture using **Tree-sitter**.
- Fast, 100% accurate symbol extraction.
- Graph edges mapping `Imports`, `Inherits`, `Calls`, and `References`.
- Primary Key: `sha256(path + content_hash)` to completely eliminate edge-case collisions.

### 2. L2: Semantic (The "Why")
Hierarchical generated documentation stored locally as Markdown files (`.synapse/wiki/`).
- **File Level:** What does this file do?
- **Module Level:** How do these files relate?
- **Project Level:** `overview.md` and `architecture.md`.

### 3. L3: Behavioral (Agent Memory)
Synapse tracks the *history* of agent actions so the AI doesn't repeat past mistakes.
- **Checkpoints:** The active task the agent is performing (`synapse checkpoint`).
- **Decisions:** Architecture decisions logged by the agent.
- **Lessons:** Generated automatically when a developer runs `git revert` on an agent's commit!

---

## 🔄 Low-Level Data Flows (LLD)

### Git Mirroring Flow
Synapse's daemon watches the Git repository. The state of the repository completely drives the context.

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant Git as Git Repo
    participant Daemon as Synapse Daemon
    participant DB as SQLite DB

    Dev->>Git: git checkout feature-branch
    Git-->>Daemon: Branch Switch Event
    Daemon->>DB: Swap active context immediately

    Dev->>Git: git revert <agent-commit>
    Git-->>Daemon: Revert Detected (20-ancestor check)
    Daemon->>DB: Log Pending Lesson (What failed?)
    Daemon->>Dev: Prompt interactive review of failure
```

### Context Injection Flow
When an Agent starts a task, it receives a strict, pre-packaged header injection.

```mermaid
sequenceDiagram
    participant Agent
    participant MCP as MCP Server
    participant Memory as Context Injector
    participant DB as SQLite DB

    Agent->>MCP: Trigger Tool / Start Task
    MCP->>Memory: build_injection_context()
    Memory->>DB: Fetch Active Branch & Checkpoint
    Memory->>DB: Fetch Approved Lessons
    Memory->>DB: Check for Dirty Git Tree (Uncommitted changes)
    Memory-->>MCP: Formatted Context Header
    MCP-->>Agent: Proactive Context Grounding
```

---

## 🚀 Quick Start

### 1. Installation
Install the Synapse CLI via `pip` or `uv`:
```bash
pip install synapse
# or using uv:
uv tool install synapse
```

### 2. Setup & Initialize
Interactive onboarding to set up your LLM providers (keys stored securely in your OS keyring).
```bash
synapse setup .
```
Initialize the repo (Use `--skip-llm` to run in pure structural Mode A):
```bash
synapse init .
```

### 3. Start the Daemon
Run the background watcher to keep Synapse perfectly synced with Git:
```bash
synapse start .
```

### 4. Connect to IDE
Start the MCP server to expose Synapse to your AI Agent (Cursor, Windsurf, etc.):
```bash
synapse mcp start .
```

---

## 💻 CLI Command Reference

Synapse uses a powerful, strict CLI interface. Every destructive action prompts for approval.

### Core Lifecycle
- `synapse init .` : Perform Pass 1 and Pass 2 indexing.
- `synapse start .` : Launch the background polling daemon.
- `synapse status .` : View active branch, indexed symbols, daemon state, and memory metrics.
- `synapse rollback .` : Rollback active state to a previous commit.
- `synapse recover .` : Recover from a corrupted database state.
- `synapse run .` : Run all Synapse services (Daemon, MCP, UI) concurrently.

### L3 Memory Management
- `synapse memory status .` : View counts of approved, pending, and expired lessons.
- `synapse memory prune .` : Prune expired rules and cleanup memory.
- `synapse memory verify .` : Detect dangling file references in active memory.
- `synapse lessons approve <id> .` : Approve a pending revert lesson to activate it.
- `synapse lessons reject <id> .` : Reject and discard a pending lesson.
- `synapse checkpoint create . --doing "..."` : Save the current context state.
- `synapse checkpoint list .` : List all checkpoints for the active branch in a table.
- `synapse checkpoint restore <id> .` : Show details of a checkpoint (or "latest").

### Developer Tools
- `synapse wiki list .` : List all generated wiki documentation files.
- `synapse wiki show <filepath> .` : Render a specific wiki markdown page to the console.
- `synapse cost show .` : Display detailed aggregated LLM token usage and estimated costs.
- `synapse cost clear .` : Purge all LLM call cost history.
- `synapse doctor .` : Validate SQLite integrity, Tree-sitter, tokenizers, LLM providers, and daemon heartbeat.
- `synapse mcp verify .` : Verify MCP protocol, tool schemas, and contract stability.

---

## 🤝 Contributing

Synapse is built on the philosophy that AI tools must be transparent and controllable. If you're contributing:
- Do not introduce implicit RAG features.
- Adhere to the `SYNAPSE_BUILD_SPEC.md` strictly.
- Ensure all states are stored exclusively in `synapse.db` or `.synapse/wiki/`.

License: [Apache 2.0](LICENSE.md)
