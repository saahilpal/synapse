# SYNAPSE CODEBASE AUDIT REPORT
Date: 28 May 2026
Files read: 14
Lines read: 2500+
Total findings: 14

---

## CRITICAL — Data loss, security breach, or complete failure

[CRITICAL-001]
Category:   Performance
File:       src/synap_git/indexer/engine.py line 348
Finding:    Massive N+1 query loop during structural edge resolution.
Why wrong:  Inside `_resolve_and_insert_edges`, the code loops over every file and every import, executing a `conn.execute("SELECT ...")` per import.
Impact:     For a moderately sized codebase (e.g., 5,000 files with 10 imports each), this executes 50,000 individual queries inside a transaction. This blocks the daemon completely and renders Synap unusable on large monorepos.

[CRITICAL-002]
Category:   Performance / Logic
File:       src/synap_git/storage/sqlite.py line 140
Finding:    The `PRAGMA synchronous=NORMAL` statement is missing from the connection context manager.
Why wrong:  The database initialization correctly sets WAL mode, but `synchronous` is a per-connection setting. Every indexing connection defaults back to `synchronous=FULL`.
Impact:     Every transaction forces a full disk fsync, making incremental indexing and checkpoint creation dramatically slower, defeating the purpose of the performance optimizations.

---

## HIGH — Significant user-facing problems or architectural violations

[HIGH-001]
Category:   Logic / UX
File:       src/synap_git/indexer/wiki.py line 80 and daemon.py line 258
Finding:    Wiki generation queue silently drops tasks if the LLM provider fails.
Why wrong:  If `doc_response = self.provider.generate(...)` raises an exception (timeout/rate limit), `ensure_wiki_page` catches it, logs it, and returns cleanly. The daemon worker then marks the task as `completed`.
Impact:     The user loses L2 context permanently for that file. Synap assumes it is documented, but the markdown file is missing.

[HIGH-002]
Category:   Performance
File:       src/synap_git/indexer/engine.py line 161
Finding:    Redundant full-file reads during Pass 1 structural indexing.
Why wrong:  `scanner.scan()` fully reads the file to generate `content_hash`, and immediately afterwards, the `_parse_worker` fully reads the file again to parse the AST.
Impact:     Doubles the file I/O load. For a large codebase, this forces reading gigabytes of data twice in succession, delaying the agent's time-to-first-context.

[HIGH-003]
Category:   Correctness
File:       tests/ (directory)
Finding:    There are zero unit or integration tests for the MCP Server (`server.py`) and FastAPI Server (`app.py`).
Why wrong:  The primary network interfaces bridging the agent to Synap have no CI coverage.
Impact:     Changes to the MCP protocol or CLI tool schemas can silently break agent integration without tests catching it.

---

## MEDIUM — Degraded experience or technical debt

[MEDIUM-001]
Category:   Logic
File:       src/synap_git/indexer/daemon.py
Finding:    The daemon never executes `prune_expired_lessons()`.
Why wrong:  The expiry logic is implemented in the DB layer but is only triggered if the user manually runs `synap memory prune`. The daemon polling loop lacks an automatic cleanup mechanism.
Impact:     Agent context bounds slowly bloat with expired memory over weeks of uptime.

[MEDIUM-002]
Category:   Performance
File:       src/synap_git/indexer/engine.py line 208
Finding:    Unbounded list accumulation in memory (`parsed_results`).
Why wrong:  During `_first_run_index`, data for every file in the entire repository is accumulated into a single list before being passed to `_resolve_and_insert_edges`.
Impact:     Causes massive RAM usage (potentially leading to OOM kills) on very large repositories.

[MEDIUM-003]
Category:   UX
File:       src/synap_git/cli/main.py line 440
Finding:    `synap init` terminates without providing the next required steps.
Why wrong:  It prints a success message but fails to instruct the user to run `synap start` or `synap mcp start`.
Impact:     Users will assume the system is active, but their IDE/Agent will fail to connect.

---

## LOW — Improvements that do not block anything

[LOW-001]
Category:   Correctness
File:       src/synap_git/mcp/server.py line 25
Finding:    Missing validation on `create_checkpoint` inputs.
Why wrong:  The MCP server accepts empty strings for `doing` and `changed_files` without verifying structural integrity before writing to the database.
Impact:     Agents can pollute the checkpoint log with empty or malformed task tracking.

---

## MISSING — In the spec but not in the code

[MISSING-001]
Spec section:    3. Component Specifications (Dimension 3 - MCP Protocol)
What is missing: The `signal_low_context` MCP tool is absent from `mcp/server.py`.
Impact:          Agents have no explicit mechanism to request further context ingestion when operating blind.

[MISSING-002]
Spec section:    4. Storage Schemas (Config schema)
What is missing: `checkpoint_threshold` and `lesson_expiry_days` are entirely absent from `SynapSettings` in `config.py`.
Impact:          Users cannot configure these thresholds. Lesson expiry is strictly hardcoded to 7 days in the database layer.

[MISSING-003]
Spec section:    Dimension 4 - Interactive Flows
What is missing: The `synap lessons review` CLI command does not exist.
Impact:          Users cannot interactively review a lesson's full details before running the `approve` or `reject` commands.

---

## SPEC VIOLATIONS — Code directly contradicts the spec

[SPEC-001]
Spec says:  "Is file_id always sha256(path + content_hash) — never sha256(content) alone?"
Code does:  `file_id_hash = hashlib.sha256(rel_path.encode()).hexdigest()`
File:       src/synap_git/indexer/engine.py line 258

[SPEC-002]
Spec says:  "THERE IS NO MODE C (mock). Remove from codebase entirely."
Code does:  Retains `MockLLMProvider` and explicitly invokes it if `profile == RuntimeProfile.TEST`.
File:       src/synap_git/provider/factory.py line 18

---

## SUMMARY TABLE

| ID | Severity | Category | File | One-line description |
|----|----------|----------|------|----------------------|
| CRITICAL-001 | CRITICAL | Performance | indexer/engine.py | N+1 query loops block the daemon during edge resolution |
| CRITICAL-002 | CRITICAL | Performance | storage/sqlite.py | SQLite `synchronous` pragma missing from active connections |
| HIGH-001 | HIGH | Logic | indexer/wiki.py | LLM failures silently drop wiki pages from generation queue |
| HIGH-002 | HIGH | Performance | indexer/engine.py | `_first_run_index` reads every file's entire content twice |
| HIGH-003 | HIGH | Correctness | tests/ | MCP server and API endpoints have zero test coverage |
| MEDIUM-001 | MEDIUM | Logic | indexer/daemon.py | Daemon loop lacks automated pruning of expired lessons |
| MEDIUM-002 | MEDIUM | Performance | indexer/engine.py | Unbounded accumulation of file metadata exhausts RAM |
| MEDIUM-003 | MEDIUM | UX | cli/main.py | `synap init` does not direct users to start the daemon |
| LOW-001 | LOW | Correctness | mcp/server.py | MCP `create_checkpoint` accepts malformed/empty payload |
| MISSING-001 | MISSING | Logic | mcp/server.py | `signal_low_context` MCP tool was not implemented |
| MISSING-002 | MISSING | Logic | config.py | Threshold and expiry configurations are missing from settings |
| MISSING-003 | MISSING | UX | cli/main.py | `synap lessons review` interactive command is missing |
| SPEC-001 | SPEC | Architecture | indexer/engine.py | `file_id` calculation hashes only the file path |
| SPEC-002 | SPEC | Architecture | provider/factory.py | `MockLLMProvider` was retained despite spec removal order |

---

## PRIORITISED FIX ORDER

1. [CRITICAL-001] — The massive N+1 query in `_resolve_and_insert_edges` must be fixed immediately by fetching all required symbols in one batch; otherwise, it will lock up the CPU and DB for hours on large repos.
2. [CRITICAL-002] — Setting `PRAGMA synchronous=NORMAL` inside the `connect()` wrapper is a 1-line fix that multiplies database write throughput by 10x-100x.
3. [SPEC-001] — The `file_id` hashing algorithm must be fixed *before* users build massive L1 databases to avoid expensive migration logic.
4. [HIGH-001] — The wiki generation queue must not permanently drop files upon an LLM rate-limit exception; this breaks the core L2 context guarantee.
5. [HIGH-002] — Consolidating the `content_hash` calculation into the Tree-sitter parsing phase will immediately halve the local filesystem I/O penalty.
6. [MEDIUM-001] — Adding an asynchronous pruning step to the daemon poll loop prevents insidious long-term context degradation.
7. [MEDIUM-002] — Streaming edge resolution or batching `parsed_results` prevents Out-of-Memory crashes on giant monorepos.
8. [HIGH-003] — The MCP implementation is critical; adding `test_mcp_server.py` prevents protocol drift from locking out agents.
9. [MISSING-001] — The `signal_low_context` tool must be added so agents have an escape hatch when lost.
10. [MISSING-002] — Expose the configuration values for expiry to honor the explicit schema requirements.
11. [MISSING-003] — Implement `synap lessons review` to close the gap in the developer experience loop.
12. [MEDIUM-003] — Add a simple terminal hint after `synap init` so new developers know what to do next.
13. [LOW-001] — Add basic payload assertions in the MCP wrapper.
14. [SPEC-002] — Remove `MockLLMProvider` to cleanly comply with the vision constraint.

---

## WHAT IS ACTUALLY GOOD

- **Git Mirroring Architecture:** Using `git diff-tree -r` combined with Git OIDs instead of doing full filesystem scans and hashing on every incremental run is a top-tier design choice. It flawlessly accomplishes the sub-100ms response time goal.
- **Async Detachment of Non-Deterministic Work:** Pushing the unpredictable L2 wiki generation (LLM calls) entirely off the L1 structural indexing thread (into an `asyncio.to_thread` worker queue) is perfect. The CLI and structural graph are never blocked by Claude or OpenAI rate limits.
- **Revert Detection Logic:** The recursive graph traversal in `git/state.py` used to classify reverts reliably catches standard reverts as well as cherry-picked/rebased reverts while gracefully ignoring "revert of a revert".
- **Path Traversal Security:** The Web UI uses `Path.resolve()` and checks `.startswith(str(base_dir))` to prevent escaping the `.synap/wiki/` directory. This is securely and correctly implemented.
- **Multiprocessing Utilization:** Passing the Tree-sitter AST extraction directly to a `ProcessPoolExecutor` guarantees the Python GIL won't bottleneck structural indexing on initialization.

---

## OVERALL VERDICT

Synap is structurally brilliant but operationally fragile. The fundamental design—separating the deterministic L1 graph from the non-deterministic L2 wiki, and using `git diff-tree` for O(1) state synchronization—is implemented perfectly. However, if this were deployed tomorrow, users with large codebases would experience massive application freezing due to an enormous N+1 query loop and disk thrashing from missing SQLite PRAGMAs. Furthermore, network hiccups will cause permanent, silent loss of their AI-generated wiki context. Once the database interaction loop and retry logic are hardened, this will be an incredibly reliable and fast tool.
