# Synapse Architecture

Synap is a deterministic, Git-aware structural context engine. It functions as a background context daemon that indexes the repository structure and injects grounded developer memory into AI coding agents via the Model Context Protocol (MCP).

## The Git-Snapshot Model

Unlike standard indexers that run generic file watchers or compute arbitrary hashes, Synap uses Git commits as the absolute source of truth. Every repository state is defined as a projection of the active Git commit.

* **Deterministic Projections:** The codebase index is a pure function of your Git history and active tree. Switch branch or checkout an older commit, and the context shifts instantly.
* **Blob OID Change Detection:** Synap does not perform full filesystem scans or read all files on incremental updates. It uses `git diff-tree` to identify changed paths, reading only modified files.
* **Preservation Through Rollbacks:** While the structural code index swaps with the active Git commit, L3 behavioral memories (lessons) are preserved and carry forward.

## The 3-Layer Context Model

Synap provides context across three decoupled layers to ground the coding agent:

```
┌─────────────────────────────────────────────────────────┐
│              L3: Behavioral Memory                      │
│      (Checkpoints, Decisions, Revert Lessons)           │
└───────────────────────────┬─────────────────────────────┘
                            │ (Injected into)
┌───────────────────────────▼─────────────────────────────┐
│              L2: Semantic Documentation                 │
│         (File/Module Wikis, Project Overview)           │
└───────────────────────────┬─────────────────────────────┘
                            │ (Linked to)
┌───────────────────────────▼─────────────────────────────┐
│              L1: Structural Symbol Graph                │
│       (Tree-sitter parsed classes, functions, edges)    │
└─────────────────────────────────────────────────────────┘
```

### Layer 1: Structural Index (L1)

L1 is a deterministic mapping of codebase architecture. It extracts programming language symbols (classes, functions, methods) and parses imports to determine call and dependency edges.

* **Tree-sitter Parsing:** Extracts code nodes with high AST fidelity.
* **Unique Identification:** Maps every symbol by a primary key of `sha256(path + content_hash)` to eliminate duplication and collision.
* **SQLite Graph Traversal:** Stores relations and call dependencies in an SQL schema, traversed dynamically using SQLite Recursive Common Table Expressions (CTEs).

### Layer 2: Semantic Documentation (L2)

L2 provides human-readable context in the form of markdown summaries. It represents file, module, and project descriptions stored under `.synap/wiki/`.

* **Asynchronous LLM Worker:** Decouples slow, non-deterministic LLM wiki generation from the indexing pipeline. The daemon enqueues tasks to a persistent queue (`wiki_queue`) and processes them in the background.
* **Lazy Cache Fallback:** Triggers a synchronous generation pass to update the cache on the fly if the CLI, Web API, or MCP tools request an ungenerated or stale wiki page.

### Layer 3: Behavioral Memory (L3)

L3 represents developer-in-the-loop memory that captures current tasks, design patterns, and past failures.

* **Checkpoints:** Captures the state snapshot containing the active task description (`doing`), files affected, next steps, and blockers.
* **Decisions:** Logs technical and architectural decisions made by the agent.
* **Lessons:** Evaluates and stores rules generated automatically when a commit is reverted (detected via the Git commit ancestor graph). Active, approved lessons are prepended as system instructions during agent context packaging.
