# Synapse Architectural Decision Records (ADRs)

This document tracks all major architectural decisions, assumptions challenged, technology trade-offs, and ideas evaluated during the Synapse overhaul.

---

## ADR-001: Local LLM Auto-Discovery & Zero-LLM Deterministic Mode A

### Context
Synapse previously hardcoded `ollama` with `qwen2.5-coder:14b` at `http://localhost:11434`. When users ran different models (e.g. `qwen3.5:9b-nvfp4`) or alternate local engines (LM Studio, llama.cpp, vLLM, Jan), or when no local LLM was running, commands like `synap wiki generate` and `synap doctor` crashed or reported false positives.

### Decision
1. **Dynamic Multi-Runtime Discovery Engine (`src/synap_git/provider/discovery.py`)**:
   - Probe standard local LLM ports in parallel with low timeouts (500ms):
     - Ollama (`11434` / `OLLAMA_HOST`): `/api/tags`
     - LM Studio (`1234` / `LM_STUDIO_HOST`): `/v1/models`
     - llama.cpp (`8080` / `LLAMA_CPP_HOST`): `/v1/models`
     - vLLM (`8000` / `VLLM_HOST`): `/v1/models`
     - Jan (`1337` / `JAN_HOST`): `/v1/models`
   - Inspect installed models and automatically pick:
     - Best Chat Model (ranked by capability, parameter size, context window).
     - Best Embedding Model (checking for `nomic-embed-text`, `bge`, `mxbai-embed-large`, `all-minilm`).
   - Cache results in `.synap/provider_cache.json` with 1-hour TTL. Re-probe automatically on `/doctor`, `/model probe`, or on connectivity failure.
2. **Zero-LLM Mode A Guarantee**:
   - Every subsystem (retrieval, wiki, outline, skeleton, memory) MUST function 100% offline without any LLM running.
   - When no LLM is found, Synapse explicitly reports: `Mode A (Structural / Deterministic AST) active`. Local LLMs enhance context but are never a prerequisite for correct operation.

---

## ADR-002: Wiki Engine Rebuild — 1:1 Mirroring & Deterministic AST Generation

### Context
`WikiEngine` crashed on 100% of runs without a working Ollama model and produced a sprawling set of 15 synthetic pages (`architecture/*`, `flows/*`, `concepts/*`, `integrations/*`, `modules/*`) that hallucinated non-existent patterns. Its manifest tracking falsely marked failed runs as up to date.

### Decision
1. **1:1 Folder Tree Mirroring**:
   - Generate one markdown page per source file under `.synap/wiki/` matching the exact relative repository path:
     `src/synap_git/cli/main.py` -> `.synap/wiki/src/synap_git/cli/main.py.md`
   - Zero synthetic documentation files, zero `README.md` files, zero extra index files inside `.synap`.
   - The lookup index lives directly in SQLite (`wiki_pages` table).
2. **Deterministic Mode A Markdown Generator**:
   - When no LLM is available, generate structured, high-signal documentation from SQLite AST tables:
     - Purpose & module docstring.
     - Public exported symbols (classes, methods, signatures, types).
     - Internal & external dependencies (`imports`).
     - Key callers and callees (blast radius).
     - Related architectural decisions from `decisions` table.
   - When a local LLM is available, augment the file page with synthesized behavioral summaries and gotchas.
3. **Atomic Hash-Based Sync & Pruning**:
   - Manifest stores `{file_path: {sha256: ..., mtime: ..., page_path: ...}}`.
   - Before skipping a file, verify both content hash AND existence of target `.md` file on disk.
   - Delete orphaned `.md` pages and empty directories immediately when source files are deleted or renamed in Git.

---

## ADR-003: Two-Tier Vector Acceleration (`sqlite-vec` + NumPy BLAS Fallback)

### Context
Synapse stored vectors as JSON strings in `embeddings.vector` (`TEXT`) and computed cosine similarity via a custom SQLite Python callback function (`ORDER BY cosine_similarity(...)`). For 10k symbols, this performed 10,000 JSON deserializations and Python function calls per query, taking 400–800ms.

### Decision
1. **Vector Storage as Binary BLOB**:
   - Store float32 vectors as raw IEEE 754 byte buffers (`BLOB`). Reduces SQLite storage by ~70% and deserialization overhead to zero.
2. **Two-Tier Search Engine**:
   - Tier 1 (Accelerated): Try loading `sqlite-vec` C99 extension (`vec0` virtual table, 1–3ms search latency).
   - Tier 2 (Zero-Binary Fallback): Pre-load active vectors into an in-memory contiguous NumPy array (`float32`). Execute `np.dot(matrix, query_vec)` via BLAS in 1.8ms for 10k vectors.
   - Eliminates custom SQLite row-by-row Python callbacks completely.

---

## ADR-004: Strict Scope Isolation — Zero Silent Leakage Between Repo & Global

### Context
Developers need cross-project developer habits and global conventions, but automatic cross-repo merging risks leaking proprietary code context, hallucinating wrong architectural patterns, and violating compliance boundaries.

### Decision
1. **Repository-Local Default (`<repo>/.synap/synap.db`)**:
   - All runtime operations, MCP tools, and daemon tasks operate strictly on repo-local storage.
2. **Global Storage (`~/.synap/global_memory.db`)**:
   - Holds general developer preferences, universal style rules, and cross-repo tool choices.
   - **Zero Silent Leakage**: Global memories are NEVER automatically merged or injected into repo context prompts.
3. **Explicit Inspection & Ingestion Workflow**:
   - `/global` (`synap global list/search`) allows inspecting global memories.
   - `/ingest <id>` (`synap ingest <id>`) explicitly clones a global memory into the local repository with provenance tags (`source_scope='global'`, `source_global_id`).

---

## ADR-005: 8-Tool High-Signal MCP Protocol & Slash-Command TUI

### Context
The current MCP server exposed 24 tools (~4,200 tokens of schema overhead per prompt). The CLI exposed 45+ subcommands across 4,300 lines of code with extensive duplication.

### Decision
1. **Streamline MCP to 8 Core Tools**:
   - `get_session_preamble()`: Startup context (<800 tokens).
   - `search(query, summary_only=True, max_tokens=4000)`: Hybrid search.
   - `get_outline(file_path)`: Structural file inventory.
   - `get_skeleton(file_path)`: AST signature skeleton without function bodies (85% token reduction).
   - `read_symbol(symbol, file_path)`: Exact symbol source.
   - `create_checkpoint(doing, next_step, blockers)`: Task state preservation.
   - `remember(key, content, summary)`: Store decision/constraint.
   - `recall(key, limit)`: Retrieve memories.
2. **Interactive Slash-Command TUI (`prompt_toolkit` + `Rich`)**:
   - Running `synap` with no arguments in an interactive terminal launches a fast REPL (<30ms startup, full scrollback preserved, tab completion, history).
   - Commands: `/init`, `/status`, `/find`, `/remember`, `/forget`, `/wiki`, `/global`, `/ingest`, `/model`, `/skill`, `/doctor`, `/help`, `/exit`.
3. **Prune 48 Duplicate / Unused CLI Commands**:
   - Delete 9 redundant wiki commands, duplicate aliases (`sync`, `run`, `cost`, `preamble`, `mcp print-config`), and unused `InputValidator`.
   - Maintain 10 clean, machine-parseable subcommands for agents and CI scripts.

---

## ADR-006: Idempotent Agent Skill Distribution (`SKILL.md` & Sentinel Markers)

### Context
AI coding agents require instructions to use Synapse effectively. Past implementations either failed to install skills or risked overwriting human-maintained `CLAUDE.md`, `AGENTS.md`, or Cursor rule files.

### Decision
1. **Package-Distributed `SKILL.md`**:
   - Ship standardized `SKILL.md` as package data inside the wheel.
2. **Idempotent Sentinel Block Updates**:
   - Inject guidelines using bounded sentinel comments:
     ```markdown
     <!-- SYNAP_MANAGED_START: v1.0 -->
     ## Synapse AI Agent Directives
     ...
     <!-- SYNAP_MANAGED_END -->
     ```
   - If sentinels exist, replace only the bounded block; never overwrite human text before or after.
   - Install automatically on `synap init` or via `/skill sync` into `.claude/skills/synap/SKILL.md`, `CLAUDE.md`, `AGENTS.md`, and `.cursor/rules/synap.mdc`.
