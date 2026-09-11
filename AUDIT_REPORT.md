# Synapse Adversarial Audit Report: Codebase, CLI, Architecture & Website

**Target**: Synapse Context Engine (`synap-git` v2.4.0) & Marketing / Documentation Website
**Repository Path**: `/Users/nitrousoxide/Code/synapse`
**Website URL**: Local Next.js Instance (`http://localhost:3000`) & Docs (`/docs`)
**Audit Date**: September 11, 2026
**Auditor Persona**: Principal Systems Architect & Adversarial Product Critic
**Evaluation Mode**: Brutal, Unfiltered, Zero-Praise Technical Audit

---

## 1. Executive Summary

- **The MCP server integration is completely broken across both documentation and CLI generation.** The marketing homepage tells users to configure `synap mcp serve` (which does not exist, exit code 2). The documentation tells users to configure `synap mcp start` (which does not exist, exit code 2). The CLI command `synap mcp config` emits `synap start` without `--foreground`, which detaches a daemon and exits with code 0 immediately, causing Cursor, Windsurf, and Claude Code to disconnect on launch. Even when `--foreground` is supplied manually, `synap start` writes non-JSON ANSI terminal text to `sys.stdout` before FastMCP starts, fatally corrupting the JSON-RPC stdio protocol.
- **The L1 Structural Code Graph collapses into an all-to-all ball of mud.** In `src/synap_git/indexer/engine.py:925-941`, the indexer connects *every* symbol in a file to *every* imported symbol. In `src/synap_git/storage/sqlite.py:453-465`, graph neighborhood expansion uses an undirected recursive CTE. Because standard modules like `datetime`, `typing.Any`, and `dataclass` are imported universally, a 2-hop neighborhood query bridges almost every file in the repository. Searching for `"daemon"` returns 15 separate single-line `from typing import Any` and `from datetime import datetime` imports from unrelated files, squandering the agent's token budget on trivial standard library noise.
- **Multi-language AST claim is hollow: 9 of 11 supported languages have zero dependency edges.** Tree-sitter parsers exist for 11 languages, but `_parse_tree_sitter()` in `src/synap_git/parser/registry.py` only extracts import statements for Python, JavaScript/TSX, and Go. For Rust, Java, C++, C, C#, PHP, Kotlin, Scala, and Ruby, `imports` is hardcoded to an empty tuple. No dependency edges are ever created for these 9 languages.
- **Synapse is blind to active working tree changes.** Synapse only indexes committed Git states. Working tree filesystem changes trigger a watchdog notification that is classified as `GitChangeKind.UNCHANGED` in `daemon.py:345` and silently dropped. While an agent is writing code in an IDE session, Synapse's index remains frozen in the past. Furthermore, the daemon's filesystem watcher explicitly ignores `.git`, meaning `git commit` events do not trigger immediate updates and must wait up to 30 seconds for a fallback timer.
- **"Auto-extracted revert lessons" and "test failure memory" are marketing illusions.** Synapse has zero test runner integration (`pytest` or otherwise). When a Git revert is detected, `engine.py:217-218` inserts the hardcoded strings `what_failed="Revert detected automatically"` and `why_failed="Awaiting analysis from LLM or User"`. No LLM analysis is executed. Furthermore, in `src/synap_git/git/state.py:91-92`, `commit_message` and `commit_parent_hashes` are never populated from Git, leaving the commit message revert classification and merge detection branches as dead code.
- **Position-dependent symbol IDs destroy database edge continuity on single-line edits.** In `registry.py:274-276`, `stable_id` hashes `node.start_point[0]` (the starting line number). Inserting a single blank line at the top of a file shifts every line number down by 1, mutating every primary key in the file and cascading deletions across foreign keys in `edges` and `embeddings`.
- **Destructive and misleading CLI UX footguns.** `synap rollback` executes `git checkout <commit>`, forcefully putting the developer's working tree into a detached HEAD state and deleting all branch checkpoints. `synap repair` destroys all L3 behavioral memory even on healthy databases. `synap checkpoint create [PATH]` defines `path` as the first positional argument, causing `synap checkpoint create "Fixing auth"` to create a spurious directory named `Fixing auth/.synap` in the workspace.
- **Dishonest website benchmarks and fabricated capabilities.** The homepage "Live Benchmark" button is a hardcoded 800ms `setTimeout` that displays static CSS animations. The "780x faster" comparison pits a local SQLite query (9.2ms) against a strawman remote LLM classification roundtrip (7,214ms), completely ignoring competitors like Aider's repomap (0ms in-memory) or `ast-grep` (2ms). The site claims to use `sqlite_vec (WAL)` with precalculated Euclidean norms; the codebase contains zero references to `sqlite_vec` and instead runs a table scan calling a Python scalar function that deserializes JSON strings row-by-row.

---

## 2. Problem-Fit Verdict

### Stated Problem
> *"Context windows of AI coding agents become cluttered when fed raw codebase dumps, causing token waste. Standard vector search systems return isolated snippets that lack import relations, class hierarchies, and file-dependency bonds. Switching branches or checking out older commits disrupts agent operations, causing repetitive code failures."*

### Verdict: **Partially Solved (Broken Execution)**

Synapse accurately diagnoses a real failure mode of naive RAG in AI coding assistants: flat vector retrieval misses structural caller/callee context, and long-horizon agents repeatedly make the same architectural mistakes across branch checkouts.

However, Synapse fails to solve this problem for the following structural reasons:
1. **Context Pollution via Import Bridging**: Instead of delivering clean, structural subgraphs, Synapse's bidirectional recursive CTE bridges unrelated files across common standard library imports (`typing`, `datetime`). In practice, searching for a feature or symbol loads dozens of identical `import Any` lines from unrelated modules, causing the exact token waste Synapse claims to eliminate.
2. **Total Blindness to Active Editing Sessions**: AI coding agents work on dirty working trees, modifying files incrementally before committing. Synapse does not index uncommitted working tree deltas. An agent asking Synapse for context while refactoring receives stale code from the previous commit.
3. **Empty Dependency Graphs for Most Languages**: For 9 of its 11 languages (including Rust, C++, Java, and C#), no import statements are parsed, meaning no dependency edges exist. In these ecosystems, Synapse is merely a flat SQLite table of symbol names with no caller/callee graph whatsoever.
4. **Non-functional Agent Integration**: Because the FastMCP server connection is broken out of the box (wrong commands in docs, background exit in `synap mcp config`, stdout protocol corruption), an agent in Cursor or Windsurf cannot even connect to Synapse without manual codebase patching.

---

## 3. Differentiation Verdict

### Competitors & Alternatives
- **Aider (RepoMap)**: Local Tree-sitter map with PageRank over symbols. Zero-daemon, instant in-memory calculation, fully tracks dirty working tree.
- **Cursor / Windsurf**: Live LSP + in-memory vector index. Keystroke-level updates, cross-file reference finding, zero config.
- **Sourcegraph Cody / Augment Code**: Precise multi-repo SCIP/LSP code graphs with exact caller/callee jump-to-definition.
- **ast-grep**: On-demand CLI/LSP AST matching, sub-5ms, no persistent daemon overhead.
- **Mem0 / Letta**: Dedicated memory graphs with semantic entity extraction.

### Verdict: **Marginally Different (Mostly Cosmetic Packaging)**

Synapse is a repackaging of standard Tree-sitter parsing and SQLite storage behind a FastMCP facade, undermined by faulty graph logic.

| Dimension | Synapse Claim | Reality | Closest Competitor Equivalent |
|---|---|---|---|
| **Structural Graph** | Deterministic caller/callee graph | Only extracts file-level imports (for 3 languages only). Traversal is bidirectional, collapsing into a standard library bridge. | **Aider RepoMap**: Uses PageRank on Tree-sitter tags; works across dirty files without a daemon. |
| **Retrieval Speed** | "780x faster (9.2ms vs 7.2s)" | Compares local SQLite select against remote LLM classification. Vector search is an unindexed Python table scan. | **ast-grep / ripgrep**: 1-5ms without any daemon or multi-megabyte SQLite cache. |
| **L2 Semantic Wiki** | Git-synced architectural documentation | Background LLM summaries that attempt to document SVG files, lockfiles, and hallucinate non-existent folder trees. | **RepoPrompt / Claude Code memory**: Native markdown files checked into Git (`CLAUDE.md`, `.cursorrules`). |
| **L3 Behavioral Memory** | Automated revert lessons & error prevention | Inserts static string `"Awaiting analysis"`. Never reads commit messages (dead code) and has no test runner hooks. | **Cursor Rules / Windsurf Rules**: Direct developer instructions without SQLite lock contention. |

#### Strongest reason someone would choose Synapse
They want a standalone, open-source, local-first MCP server that combines code symbols, basic AST indexing, and an MCP interface without vendor lock-in to Cursor or proprietary cloud indexes.

#### Strongest reason someone would choose a competitor instead
Competitors actually work out of the box, index uncommitted keystrokes in real time, extract real symbol references instead of all-to-all import bridges, and do not crash MCP stdio clients with ANSI terminal escape sequences.

---

## 4. Comprehensive Findings Table

### Group 1: Logic, Flow & Correctness (Phase 3)

| Severity | Location | What's Wrong | Why It Matters | Concrete Fix |
|---|---|---|---|---|
| **CRITICAL** | `src/synap_git/cli/main.py:766-770`, `main.py:824-831` | `synap start --foreground` prints ANSI-colored terminal banners (`✓ Synap daemon started...`) directly to `sys.stdout` before FastMCP starts stdio JSON-RPC. | Stdout is reserved exclusively for JSON-RPC frames in MCP stdio transport. ANSI text causes immediate JSON parse errors in Cursor, Claude Code, and Windsurf, terminating the connection. | Replace `console.print` with `console.print(..., file=sys.stderr)` or suppress all banner output when running in stdio mode. |
| **CRITICAL** | `src/synap_git/cli/main.py:1851` | `synap mcp config` generates args `["start", abs_path]` without the `--foreground` flag. | `synap start` launches the daemon process into the background and immediately returns exit code 0. IDE MCP clients see the server process terminate immediately and mark it dead. | Change args in `mcp_config` to include `--foreground` or create a dedicated `synap mcp serve` command that runs FastMCP in the foreground. |
| **CRITICAL** | `src/synap_git/indexer/engine.py:925-941`, `src/synap_git/storage/sqlite.py:453-465` | Every symbol in a file is linked to every imported module (`depends_on`), and `get_neighborhood` traverses edges bidirectionally (`UNION target_symbol ... UNION source_symbol`). | Common imports (`datetime`, `typing`, `os`) connect all files in the repository into a single clique. 2-hop neighborhood expansion fills token budgets with dozens of useless `import Any` lines. | Only link function/class bodies that actually reference the imported identifier. Restrict graph traversal in `sqlite.py` to directed downstream/upstream paths rather than bidirectional unions, and filter out stdlib modules. |
| **CRITICAL** | `src/synap_git/parser/registry.py:87-265` | `imports` extraction is only implemented for Python, JavaScript/TSX, and Go. Rust, Java, C++, C, C#, PHP, Kotlin, Scala, and Ruby have no import extraction rules. | 9 out of 11 supported languages produce zero dependency edges. The graph is completely empty for C++, Rust, and Java projects. | Implement AST queries for `use_declaration` (Rust), `import_declaration` (Java/Kotlin/Scala), `preproc_include` (C/C++), and `using_directive` (C#) in `_parse_tree_sitter`. |
| **HIGH** | `src/synap_git/git/state.py:91-92`, `git/state.py:164-166`, `git/state.py:189-191` | `parent_hashes` is hardcoded to `()` and `commit_message` is hardcoded to `None` in `GitRepository.state()`. | In `classify()`, `message.startswith("Revert ")` and `len(current.commit_parent_hashes) > 1` are dead code branches. Revert commit messages are never detected by title, and merges are misclassified. | Populate `commit_message` via `git log -1 --format=%B HEAD` and `parent_hashes` via `git rev-parse HEAD^@` inside `GitRepository.state()`. |
| **HIGH** | `src/synap_git/parser/registry.py:274-276` | `stable_id` incorporates `node.start_point[0]` (starting line number) into the SHA-256 hash. | Inserting a single line at the top of a file shifts all subsequent lines down, altering every `symbol_id` in the file. This breaks all foreign key references in `edges` and `embeddings`. | Remove `start_point[0]` from the stable ID hash. Use `path:qualified_scope_name:kind` (e.g. `src/auth.py:AuthService.login:method`). Use start line only as a mutable column attribute. |
| **HIGH** | `src/synap_git/indexer/daemon.py:108-120`, `daemon.py:345-348` | Watchdog handler explicitly ignores `.git`, and working tree file modifications result in `GitChangeKind.UNCHANGED`, which executes zero indexing logic. | Commits are not detected immediately because `.git` is ignored (forcing a 30s backstop wait). Dirty working tree edits are never indexed, leaving the agent blind to uncommitted code. | Monitor `.git/refs/heads/` and `.git/HEAD` specifically in watchdog. Add working-tree delta parsing for dirty files so modified files are indexed into an ephemeral working table. |
| **HIGH** | `src/synap_git/indexer/engine.py:217-218` | `handle_revert` creates pending lessons with hardcoded strings: `what_failed="Revert detected automatically"`, `why_failed="Awaiting analysis from LLM or User"`. | No revert analysis or extraction actually happens. The lesson is an empty stub that expires after 7 days without user intervention. | Trigger an asynchronous LLM prompt comparing `git diff revert_commit^!`, generating an actual technical diagnosis of why the code was reverted. |
| **MEDIUM** | `src/synap_git/mcp/server.py:54-59` | `SynapMCPFacade.restore_checkpoint` accepts `checkpoint_id: str` but ignores it, unconditionally calling `self.runtime.store.get_latest_checkpoint(status.branch)`. | Agents cannot restore a specific checkpoint by ID; older checkpoints are permanently inaccessible via the MCP tool interface. | Change line 56 to `self.runtime.store.get_checkpoint(checkpoint_id)` if `checkpoint_id != "latest"`, else use `get_latest_checkpoint`. |
| **MEDIUM** | `src/synap_git/storage/sqlite.py:26-33`, `sqlite.py:532` | Vector similarity runs a full table scan calling a Python scalar function `_cosine_similarity` that parses JSON strings row-by-row in Python. | On large codebases (e.g. 50k+ symbols), this creates severe GIL contention and 100ms+ query latencies. The website claim of `sqlite_vec` is false. | Store vectors as raw binary blobs (`struct.pack` float32) or integrate the actual `sqlite-vec` extension library for native SIMD vector indexing. |
| **MEDIUM** | `src/synap_git/indexer/scanner.py`, `src/synap_git/indexer/wiki.py` | L2 wiki worker enqueues and generates documentation summaries for binary/asset files (`assets/ui-screenshot.svg.md`, `uv.lock.md`, `coverage.xml.md`, `py.typed.md`). | Wastes local and remote LLM tokens attempting to summarize SVG vector drawings, lockfiles, and empty marker files with mock text. | Add an explicit file extension and MIME check before enqueuing to `wiki_queue`. Exclude `.svg`, `.lock`, `.xml`, `.typed`, `.min.js`. |

---

### Group 2: CLI UX & Flow (Phase 4)

| Severity | Location | What's Wrong | Why It Matters | Concrete Fix |
|---|---|---|---|---|
| **CRITICAL** | `website/src/components/ui/ide-config-generator.tsx:26,36,48,62` | Marketing website instructs users to add `"args": ["mcp", "serve", "."]` to Cursor, Claude Code, Windsurf, and Roo Code. `synap mcp serve` does not exist. | Every single developer who follows the website's setup guide receives `Error: No such command 'serve'`. | Add `serve` subcommand under `mcp_app` in `src/synap_git/cli/main.py` that directly runs `SynapMCPServer(runtime).run()`. |
| **CRITICAL** | `website/content/docs/mcp.mdx:38,48,60`, `website/content/docs/cli.mdx:113` | Documentation instructs users to run `synap mcp start .`. `synap mcp start` does not exist. | Users following the official documentation receive `Error: No such command 'start'`. | Alias `mcp start` and `mcp serve` to the MCP server foreground runner in `main.py`. |
| **HIGH** | `src/synap_git/cli/main.py:1567-1570` | `synap rollback` executes `git checkout <commit>`. | Checks out an older commit into detached HEAD state, dirtying the developer's git tree and wiping out uncommitted work. | Make `rollback` roll back the Synapse database state to a previous commit's index *without* modifying the user's working tree Git checkout. |
| **HIGH** | `src/synap_git/cli/checkpoint.py:21-29` | In `synap checkpoint create [PATH]`, `path` is the first positional argument with default `.`. The checkpoint description `doing` is an option `--doing`. | Running `synap checkpoint create "Implemented auth"` interprets `"Implemented auth"` as the repository directory path, creating a spurious folder with a duplicate `.synap` database. | Change `doing` to be the primary required positional argument: `synap checkpoint create <doing> [PATH]`, or move `path` to `--path` option. |
| **HIGH** | `src/synap_git/cli/main.py:1014`, `main.py:1031` | `synap status` maps `status_info.symbols` to the label `"Memory:"` (e.g. `Memory: 847`). | Misleads users into thinking they have 847 memory items or 847MB RAM, when it is literally the AST symbol count. | Change label to `"Symbols:"` or `"Graph Symbols:"`, and add a separate `"Approved Lessons:"` row for actual L3 memory. |
| **MEDIUM** | `src/synap_git/cli/lessons.py` | There is no `synap lessons list` command. Users can only `approve`, `reject`, or `review` pending lessons. | Once a lesson is approved, a developer has no CLI command to list, inspect, or query approved lessons currently stored in SQLite. | Add `@app.command("list")` in `src/synap_git/cli/lessons.py` that displays all approved, pending, and expired lessons in a Rich table. |
| **MEDIUM** | `src/synap_git/cli/memory.py` | No command to query or view architectural decisions logged via `log_decision`. | Agents log decisions via MCP, but human engineers have no CLI interface to view them. | Add `synap memory decisions` or `synap decisions` subcommand in CLI. |
| **MEDIUM** | `src/synap_git/cli/main.py:1664` | `synap repair` wipes the SQLite file, unconditionally printing `⚠ Agent memory (L3) could not be recovered — starting fresh.` | Running `repair` permanently deletes all user-approved lessons and checkpoints, even if the database was healthy. | Back up `lessons`, `checkpoints`, and `decisions` tables into memory before dropping structural graph tables during repair. |

---

### Group 3: Website UX/UI & Positioning (Phase 5)

| Severity | Location | What's Wrong | Why It Matters | Concrete Fix |
|---|---|---|---|---|
| **CRITICAL** | `website/src/components/ui/mcp-inspector.tsx:48-73` | Inspector displays `log_decision` with parameters `{ decision, rationale, tags }` returning `{ status: "logged", active_constraints_count: 5 }`. | The real `log_decision` tool takes `{ content: str, context_info: str }` and returns `{ status: "success", decision_id: str }`. Any agent using the website schema fails. | Update `mcp-inspector.tsx` to display the actual Python parameters and real return values. |
| **CRITICAL** | `website/src/components/ui/mcp-inspector.tsx:103-126` | Inspector displays a tool named `get_memory`. | `get_memory` does not exist in `src/synap_git/mcp/server.py`. The real tools are `get_approved_memory` and `get_pending_memory`. | Replace `get_memory` with `get_approved_memory` and `get_pending_memory` in the UI component. |
| **HIGH** | `website/src/components/ui/benchmark-comparison.tsx:8-18` | "Run Live Benchmark" button executes a fake 800ms `setTimeout` that displays static CSS animations. | Sophisticated technical users inspecting network traffic or React source code immediately discover it is a fabricated simulation, destroying project credibility. | Replace the fake simulation with an honest explanation of SQLite latency vs remote LLMs, or remove the "Run Live Benchmark" button. |
| **HIGH** | `website/public/usage-widget.js:7`, `website/content/docs/web-ui.mdx:63` | `usage-widget.js` runs `fetch('/api/v1/usage')` on the documentation website host (port 3000), where no API exists. | The `/docs/web-ui` page renders an ugly error: `"Failed to load usage"` in the middle of the documentation. | Remove the script tag or point it to a configurable daemon URL with a mock fallback. |
| **MEDIUM** | `website/src/components/ui/synapse-hero.tsx:58-64` | Hero interactive graph claims node 3 is `"sqlite_vec (WAL)"`. | Synapse does not use `sqlite_vec`; it uses standard SQLite with a Python callback scalar function. Claiming `sqlite_vec` is false advertising. | Change label in `synapse-hero.tsx` to `"sqlite (WAL + FTS5)"`. |
| **MEDIUM** | `website/src/components/ui/token-calculator.tsx:20-25` | Calculator assumes every query dumps 100% of the entire repository into the model context (75k LOC = 60,000 raw tokens per query). | Modern IDE agents (Cursor, Windsurf, Claude Code) never dump the whole repo; they use BM25, LSP, and vector chunks. The savings calculation is exaggerated. | Update calculator baseline to compare against typical multi-file vector RAG (e.g. 8k-16k tokens) rather than full repository dumps. |
| **MEDIUM** | `website/src/app/docs/layout.tsx:16-48` | `/docs/web-ui` is absent from `NAV_GROUPS` in `layout.tsx`. | The Diagnostic Web UI documentation is completely orphaned and inaccessible from the sidebar. | Add `{ title: 'Diagnostic Web UI', href: '/docs/web-ui', icon: Monitor }` to the Integration group in `layout.tsx`. |
| **LOW** | `website/src/app/docs/layout.tsx:54` | Sidebar navigation is rendered statically above the content on mobile viewports (`w-full flex-col`). | On mobile devices, users must scroll past all 11 navigation links before reaching the documentation text on every single page load. | Add a collapsible mobile hamburger drawer for the docs sidebar. |

---

### Group 4: Skeptical User Gut-Check (Phase 6)

| Severity | Location | What's Wrong | Why It Matters | Concrete Fix |
|---|---|---|---|---|
| **CRITICAL** | Developer First-Run Journey | User installs package, copies Cursor snippet from homepage (`"args": ["mcp", "serve", "."]`), restarts Cursor. Cursor reports: `No such command 'serve'`. | User uninstalls within 90 seconds. | Ensure the CLI command in `ide-config-generator.tsx` matches an actual, tested CLI command. |
| **HIGH** | Agent Context Inspection | User connects agent, asks "Explain how our daemon handles Git events", agent queries Synapse `search`. Context window receives 15 instances of `from typing import Any` from test files. | User realizes Synapse is injecting standard library noise rather than real structural dependencies, and reverts to built-in Cursor search. | Fix edge insertion in `engine.py` and graph traversal in `sqlite.py`. |
| **HIGH** | Git Revert Verification | User makes a commit titled `Revert "add broken feature"`. Checks `synap lessons review`. CLI reports: `No pending lessons to review.` | User realizes the core advertised feature ("auto-extracted revert lessons") does not work because commit message parsing is dead code. | Populate `commit_message` in `GitRepository.state()`. |
| **MEDIUM** | Benchmark Credibility | Senior engineer checks website claim: "780x Faster. 9.2ms vs 7,214ms". Discovers the "Live Benchmark" button is a timer animating hardcoded numbers. | Destroys technical trust; marks the project as vaporware. | Ground benchmarks in transparent reproducible scripts (`benchmarks/run.py`). |

---

## 5. Quick Wins (High Impact, Low Effort)

*Ranked in order of urgency:*

1. **Add `synap mcp serve` & `synap mcp start` subcommands (15 mins)**:
   In `src/synap_git/cli/main.py`, mount `serve` and `start` on `mcp_app` to run `SynapMCPServer(runtime)` in the foreground without daemonizing. This immediately fixes the broken Cursor, Windsurf, Claude Code, and docs configurations.
2. **Silence stdout banners in stdio mode (10 mins)**:
   Ensure `sys.stdout` receives zero raw text when `--foreground` or `mcp serve` is active. Route all logging and banners to `sys.stderr` to prevent JSON-RPC framing corruption.
3. **Populate `commit_message` and `commit_parent_hashes` in `GitRepository.state()` (15 mins)**:
   Add `git log -1 --format=%B HEAD` and `git rev-parse HEAD^@` to lines 91-92 of `src/synap_git/git/state.py`. This revives the dead revert-detection and merge-detection logic.
4. **Fix `checkpoint create` argument order (15 mins)**:
   Change `src/synap_git/cli/checkpoint.py` so `doing` is the primary positional argument (`checkpoint create <doing> [PATH]`). Stops users from accidentally creating folders named after their commit notes.
5. **Add `synap lessons list` command (20 mins)**:
   Add `@app.command("list")` in `src/synap_git/cli/lessons.py` querying `store.get_lessons()` to allow users to view their active and approved memory rules.
6. **Correct `McpInspector` payloads on website (20 mins)**:
   Update `website/src/components/ui/mcp-inspector.tsx` to display real tool names (`get_approved_memory`, not `get_memory`) and real parameter names (`content`, `context_info` for `log_decision`).
7. **Fix `restore_checkpoint` parameter pass-through (10 mins)**:
   In `src/synap_git/mcp/server.py:56`, pass `checkpoint_id` to `store.get_checkpoint(checkpoint_id)` instead of discarding it.
8. **Add `/docs/web-ui` to docs navigation (5 mins)**:
   Add `web-ui` to `NAV_GROUPS` in `website/src/app/docs/layout.tsx` so the page is discoverable. Remove the broken `usage-widget.js` script tag from `web-ui.mdx`.

---

## 6. Big Rocks (High Impact, Substantial Effort)

1. **Re-architect the L1 Dependency Graph & Neighborhood Expansion**:
   - Stop creating `depends_on` edges between every symbol in a file and every imported module. Instead, parse AST call expressions (`call_expression`, `attribute`) to find true symbol-to-symbol call sites.
   - Ignore common standard library modules (`typing`, `sys`, `os`, `datetime`, `collections`, `abc`) during edge generation.
   - Make `get_neighborhood` traversal directed (upstream callers vs downstream callees) rather than an undirected `UNION` that bridges across standard library imports.
2. **Implement Real Working Tree Delta Indexing**:
   - Index uncommitted working tree changes into an ephemeral SQLite table (`working_symbols`, `working_edges`).
   - Query both committed and working-tree tables during hybrid retrieval so AI agents receive up-to-the-second context while typing or refactoring.
3. **Complete Import Extraction for All 11 Tree-sitter Languages**:
   - Implement Tree-sitter grammar queries for `use` in Rust, `import` in Java/Kotlin/Scala, `#include` in C/C++, `using` in C#, and `require`/`use` in PHP and Ruby.
   - Without this, Synapse's structural promise is invalid for 80% of enterprise programming languages.
4. **Implement Genuine Revert Analysis & Memory Extraction**:
   - Replace the static `"Awaiting analysis from LLM or User"` placeholder in `handle_revert` with an actual LLM prompt that analyzes the reverted patch and generates a concrete lesson (e.g. *"When modifying storage/sqlite.py, always acquire WAL locks before updating schema"*).
   - Automatically persist approved lessons into `.cursorrules` or `CLAUDE.md` so the agent respects them without needing manual MCP querying.

---

## 7. Scorecard

| Dimension | Score (1-10) | Justification |
|---|:---:|---|
| **Problem-Solution Fit** | **4 / 10** | Identifies the correct bottleneck (token waste and loss of structural bonds), but fails to index dirty working trees and floods the context window with standard library import statements. |
| **Differentiation** | **3 / 10** | Differentiators are largely cosmetic or strawman comparisons (comparing local SQLite to remote LLMs); lacks true caller/callee call-graph analysis and behaves identically to basic Tree-sitter tag extractors. |
| **Code Correctness** | **3 / 10** | Crippled by critical bugs: position-dependent symbol IDs break on blank lines, revert commit messages are never fetched (dead code), MCP config exits immediately, and stdout protocol framing is corrupted by ANSI banners. |
| **CLI UX** | **5 / 10** | Commands have Rich formatting and clean color schemes, but suffer from destructive footguns (`synap rollback` detaches Git HEAD, `synap repair` wipes memory, `checkpoint create` creates spurious directories). |
| **Website UX & Positioning** | **4 / 10** | Visually polished dark-mode aesthetics, but completely decoupled from engineering reality: advertises non-existent CLI commands, fake live benchmark timers, and non-existent database technologies (`sqlite_vec`). |
| **Overall Score** | **3.8 / 10** | **High technical promise, but severely compromised by broken integrations, invalid graph heuristics, and misleading marketing claims.** |
