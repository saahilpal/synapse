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


---

## ADR-007: Second-Pass System Transformation (Wiki, Logger, Truthful CLI, Git Memory, Query Router)

### Top 5 Major Improvements Ranked by User-Visible Impact

1. **Universal 1:1 Plain-English Wiki System & Retrievable Knowledge Base (Item 1)**:
   - Expand wiki coverage from code-only to 100% of non-ignored repository files (Source, Docs/text, Config/build, Data/SQL, Tests, Scripts/templates/notebooks; Binary/lockfile/generated recorded in DB).
   - Mirrored relative paths: `src/a/b.py` -> `.synap/wiki/src/a/b.py.md`. Zero README or index files.
   - Enforce 8th-grade reading level, short sentences, active voice, and fixed 6-part template (`What it does`, `How it works`, `Key parts`, `Connects to`, `Watch out for`, `Recent changes`).
   - Deterministic fact extraction first (AST, imports, git log) + LLM summary with validation (no empty sections, no invented symbols, reading level) and facts-only fallback marked "auto-extracted, no summary".
   - Full-text indexing of wiki markdown pages so "how does X work" queries return plain-English documentation directly.

2. **Unified Queue-Based Rotating Logger & Live Wiki Event Streaming (Item 3)**:
   - Root cause fixed: centralized `QueueHandler` + `QueueListener` in `src/synap_git/diagnostics/logger.py` with immediate auto-flushing to `.synap/logs/daemon.log`.
   - Every component (indexer, wiki, discovery, daemon, memory) logs through the same pipeline tagged with `component`.
   - Standardized structured Wiki events: `wiki_job_started`, `wiki_file_progress` (n/total), `wiki_file_done` (duration, model), `wiki_file_skipped` (reason), `wiki_file_failed` (error), `wiki_job_finished`.
   - Live tail in `/logs` with component filter. `/status` displays the last job summary and any failed files truthfully from real state.

3. **Streamlined Truthful CLI & Interactive Slash REPL (Item 2)**:
   - Audit and prune duplicate/overlapping subcommands down to a clean, non-confusing surface with exactly one command per intent.
   - REPL with at most 12 top-level slash commands: `/init`, `/status`, `/find`, `/remember`, `/forget`, `/wiki`, `/global`, `/ingest`, `/model`, `/skill`, `/logs`, `/doctor`, `/help`, `/quit`.
   - Running `synap` in a repo prints 3-line truthful status, then prompt. If no `.synap/`, prompt to initialize once. Plain text runs `/find`.
   - Remove ALL fake output: no fake sleeps, no placeholder numbers, no decorative banners. "Done" only after checking filesystem or SQLite rows.
   - Clean non-interactive CLI: `synap mcp`, `synap ctx "<task>"`, `synap remember`, `synap daemon start|stop|status` with `--json`.

4. **Git Commit History Memory Ingestion & Change Grounding (Item 4)**:
   - Ingest Git commit messages, authors, and touched files into memory (`git_commits` table).
   - Enables agents to ask "why was this changed" or "what changed recently in auth" and receive exact commit rationale and context instead of guessing.
   - Prefetch context from current branch and uncommitted git diff into the preamble and `/ctx`.

5. **Question-Type Query Router & Honest Token Cost Accounting (Item 4)**:
   - Route queries across 5 specialized paths: symbol lookup, "where is X", "how does X work", stack trace / bug blast radius, and architectural / convention queries.
   - Real token cost accounting: benchmark and report actual tokens an agent would read without Synapse (raw full files) vs token-budgeted Synapse context pack.

---

## ADR-008: Pass 3 — Unified Registry, Grounded Fact-Citing Wiki, and Multi-Repo Benchmark

### Context & Step 0 Audit Findings

1. **Defect in Wiki Generation on `.cursorrules` & Rules/Dotfiles**:
   - `.cursorrules` has no file extension and was misclassified by `_classify_file()` as `source_code`.
   - Without AST symbols, it hit the code fallback which hardcoded:
     `"Imports needed files and helper tools."`, `"Runs code through public functions and classes."`, `"Sends back results to callers."`
   - `_validate_page()` passed it because it only checked balanced fences, non-empty sections, reading level $\le 8.5$, and backticked code spans. Because the generic sentences contained no backticks and had short words, they passed all checks despite being 100% hallucinated.
   - Root cause: Missing file classification for dotfile rules (`.cursorrules`, `.windsurfrules`, `.clinerules`, `.cursor/rules/*`), hardcoded fallback sentences instead of actual line/heading/directive extraction, and lack of a specificity ground-truth check in `_validate_page`.

2. **Documentation & Command Registry Drift**:
   - `README.md` still documented deprecated/renamed commands (`synap install`, `synap blast`, `synap skeleton`, `synap pack`, `synap context`).
   - `SKILL.md` advised agents to call MCP tools that were not registered in `src/synap_git/mcp/server.py` (`restore_checkpoint`, `log_decision`, `get_callers`).
   - The TUI hints and CLI subcommand options lacked a single programmatic source of truth.

3. **Ungrounded Token Measurements**:
   - Token comparison tables previously relied on estimates rather than an automated benchmark script executing real tokenizers (`tiktoken o200k_base`) against an explicit naive agent baseline.

### Top 5 Major Improvements Ranked by Impact

1. **Unified Schema-Driven Command & Tool Registry (`src/synap_git/cli/registry.py`)**:
   - A single authoritative registry defines every command, argument, option, help description, exit codes, and output schema.
   - Automatically generates `--help`, `/help`, shell completions, the README command table, and the SKILL.md command section.
   - CI check enforces that no documentation or tool definition references an unregistered command.

2. **Grounded, Fact-Citing Wiki Engine with Specificity Validation (`src/synap_git/indexer/wiki.py`)**:
   - Support rule files, dotfiles, YAML workflows, Dockerfiles, and config files with dedicated fact extractors.
   - Eliminate hardcoded generic fallbacks. Every sentence in "How it works" and "Key parts" MUST cite an extracted fact (heading, key, symbol, import, or git commit).
   - `_validate_page()` enforces a specificity test: rejects generic boilerplate sentences.
   - Permanent regression tests in `tests/test_wiki_grounding.py` for `.cursorrules`, Dockerfiles, YAML workflows, and test files.

3. **Multi-Repo Git-History Benchmark (`synap bench` -> `bench/numbers.json`)**:
   - Automated benchmark using recent git commits across 3 distinct repositories (Synapse itself, a TypeScript repository, and a Python/mixed repository).
   - Generates queries from commit subjects + hand-crafted queries per type (symbol lookup, "where is X", "how does X work", stack trace, architecture).
   - Measures Recall@5, Recall@10, MRR, nDCG@10, p50/p95 latency, and token consumption using `tiktoken` (`o200k_base`) comparing Synapse pack tokens vs. a naive keyword ripgrep + full file read agent.
   - All numbers in README, SKILL.md, and documentation are strictly sourced from `bench/numbers.json`.

4. **Speed & Latency Optimization (2x+ Speedup)**:
   - Lazy imports across CLI entry points to achieve `<60ms` import time (`python -X importtime`).
   - Fast Unix domain socket IPC client (`.synap/daemon.sock`) to communicate with the warm background daemon, falling back to direct in-process execution.
   - Incremental indexing driven by `git status` / `git diff --name-only` + SHA-256 hashes instead of recursive directory tree walking.
   - Sub-token identifier indexing in FTS5 (splitting `camelCase` and `snake_case`) for instant symbol search.

5. **Token-Efficient Agent Output & Compact Protocol**:
   - Compact default line format (`path:line symbol — one-line why`) with `--budget` density packing and confidence indicator.
   - Progressive L0-L3 detail expansion.
   - Streamlined `SKILL.md` with an always-loaded section strictly under 600 tokens and on-demand detail references.
