# Synapse Target Architecture & Module Design Specification

**Phase**: 1 — Design
**Date**: November 16, 2026
**Status**: APPROVED FOR IMPLEMENTATION

---

## 1. System Architecture & Module Boundaries

Synapse is structured into 6 decoupled core domains with strict ownership boundaries:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        User & Agent Interfaces                         │
│  - Interactive Slash TUI (prompt_toolkit + Rich)                       │
│  - Minimal Non-Interactive CLI (10 subcommands)                        │
│  - FastMCP Stdio Server (8 high-signal tools)                          │
│  - Agent Rules & SKILL.md Idempotent Installer                         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   Context & Intelligence Core Engine                   │
│  - 5-Tier Intent Classifier & Query Router                             │
│  - Hybrid FTS5 + Dense Vector (RRF k=60) + PageRank Centrality         │
│  - Token-Budgeted Progressive Disclosure Context Packer                │
│  - Behavioral Memory Lifecycle (Dedupe, Consolidation, Utility Decay)  │
└──────────────────┬────────────────────────────────┬────────────────────┘
                   │                                │
                   ▼                                ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────┐
│        Local LLM & Embeddings        │  │     Git & AST Indexing       │
│  - Multi-Port Runtime Auto-Discovery │  │  - Incremental Tree-sitter   │
│  - Model Capability Evaluator        │  │  - Git Worktree & OID Sync   │
│  - Deterministic Zero-LLM (Mode A)   │  │  - 1:1 Folder Mirror Wiki    │
└──────────────────┬───────────────────┘  └──────────────┬───────────────┘
                   │                                     │
                   └──────────────────┬──────────────────┘
                                      │
                                      ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        Unified Storage Layer                           │
│  - Repo-Local: <repo>/.synap/synap.db (WAL Mode, synchronous=NORMAL)   │
│  - Global: ~/.synap/global_memory.db (Cross-Project Developer Habits)  │
│  - Two-Tier Vector Acceleration: sqlite-vec + In-Memory NumPy BLAS     │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Data Model & Schema Migrations

### 2.1 Repo-Local Database (`<repo>/.synap/synap.db`)

1. **Vector Storage Upgrade**:
   `embeddings` table column `vector` transitions from `TEXT` (JSON string) to `BLOB` (raw IEEE 754 float32 byte array).
2. **Behavioral Memory Schema Enhancements**:
   - `decisions`: add `fingerprint_hash TEXT`, `supersedes_id TEXT`, `utility_score REAL DEFAULT 1.0`, `citation_count INTEGER DEFAULT 0`, `last_referenced_at INTEGER`, `source_scope TEXT DEFAULT 'local'`, `source_global_id TEXT`, `status TEXT DEFAULT 'active'`.
   - `lessons`: add `fingerprint_hash TEXT`, `supersedes_id TEXT`, `utility_score REAL DEFAULT 1.0`, `citation_count INTEGER DEFAULT 0`, `last_referenced_at INTEGER`, `source_scope TEXT DEFAULT 'local'`, `source_global_id TEXT`.
   - `checkpoints`: add `diff_summary TEXT`, `status TEXT DEFAULT 'active'`.
   - `memory_citations`: new table tracking every agent injection, reference, and thumbs up/down feedback.
3. **1:1 Wiki Lookup Table**:
   - `wiki_pages`: `(file_path TEXT PRIMARY KEY, page_path TEXT NOT NULL, content_hash TEXT NOT NULL, updated_at INTEGER NOT NULL, is_llm_enhanced INTEGER NOT NULL DEFAULT 0)`.

### 2.2 Global Memory Database (`~/.synap/global_memory.db`)

```sql
CREATE TABLE IF NOT EXISTS global_memories (
    global_id TEXT PRIMARY KEY,
    context_key TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,             -- 'habit', 'style', 'tooling', 'anti_pattern'
    content TEXT NOT NULL,
    summary TEXT,
    tags TEXT,                          -- JSON array of strings: '["python", "typing"]'
    fingerprint_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    usage_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_global_category ON global_memories(category);
CREATE INDEX IF NOT EXISTS idx_global_fingerprint ON global_memories(fingerprint_hash);
```

---

## 3. Module Interfaces & Contracts

### 3.1 Local LLM Discovery Contract (`src/synap_git/provider/discovery.py`)

```python
@dataclass(frozen=True)
class DiscoveredRuntime:
    provider: str               # "ollama", "lm_studio", "llamacpp", "vllm", "jan"
    base_url: str               # "http://localhost:11434"
    chat_model: str | None      # "qwen3.5:9b-nvfp4"
    embedding_model: str | None # "nomic-embed-text:latest"
    is_available: bool

class RuntimeDiscoveryService:
    @classmethod
    def discover_active_runtime(cls, force_probe: bool = False) -> DiscoveredRuntime | None:
        """Probes standard ports in parallel (timeout 500ms). Caches for 1 hour."""
        ...
```

### 3.2 1:1 Wiki Engine Contract (`src/synap_git/indexer/wiki.py`)

```python
class MirrorWikiEngine:
    def sync_file_page(self, repo_relative_path: str, force: bool = False) -> Path:
        """
        Generates/updates .synap/wiki/<repo_relative_path>.md.
        In Mode A (no LLM): Generates deterministic AST summary (docstring, exported symbols, imports, callers, decisions).
        With LLM: Enhances with behavioral summary and gotchas.
        Returns target page path.
        """
        ...

    def prune_orphaned_pages(self) -> list[str]:
        """Deletes .synap/wiki/*.md files whose source files no longer exist in Git."""
        ...
```

### 3.3 Behavioral Memory & Scope Contract (`src/synap_git/retrieval/memory.py`)

```python
class MemoryRetriever:
    def list_global_memories(self, query: str = "", tag: str = "", limit: int = 10) -> list[dict[str, Any]]: ...
    def ingest_global_memory(self, global_id: str, as_category: str = "note") -> str: ...
    def record_feedback(self, memory_id: str, action: str) -> None: ...
```

### 3.4 Interactive Slash TUI Contract (`src/synap_git/cli/tui.py`)

```python
class SynapInteractiveREPL:
    def run(self) -> None:
        """Launches prompt_toolkit REPL with NestedCompleter, FileHistory, and Rich formatting."""
        ...
```

---

## 4. Phase 2 Disjoint File Ownership Matrix

To ensure zero concurrency collisions, files are partitioned strictly across 6 builders:

| Builder Agent | Mission / Work Item | Owned Files / Directories |
| :--- | :--- | :--- |
| **Builder A (Discovery)** | Item A: LLM/Runtime Auto-Discovery & Config | `src/synap_git/provider/discovery.py`<br>`src/synap_git/provider/factory.py`<br>`src/synap_git/config.py` |
| **Builder B (Wiki)** | Item B: 1:1 Mirroring Wiki & Mode A AST Generator | `src/synap_git/indexer/wiki.py`<br>`tests/test_wiki_generation.py` |
| **Builder C (Interface & TUI)** | Items C, F: Slash REPL & Minimal CLI | `src/synap_git/cli/tui.py`<br>`src/synap_git/cli/main.py`<br>`src/synap_git/mcp/server.py` |
| **Builder D (Packaging & Skill)** | Item D: SKILL.md & Idempotent Rule Installer | `src/synap_git/resources/SKILL.md`<br>`src/synap_git/cli/skill_installer.py`<br>`pyproject.toml` |
| **Builder E (Retrieval & Memory)** | Items E: Vector Acceleration, Memory Scope & RRF | `src/synap_git/storage/sqlite.py`<br>`src/synap_git/retrieval/engine.py`<br>`src/synap_git/retrieval/memory.py` |
| **Builder G (Cleanup & Bug Sweep)** | Item G: Bug Fixes, Token Logic, Security Pruning | `src/synap_git/security/`<br>`src/synap_git/indexer/engine.py`<br>`tests/test_package.py` |
