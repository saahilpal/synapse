# L2 Semantic Wiki Engine

Synap's engineering wiki has two deliberate inputs: Synap's structural index is the source of truth, and the configured local LLM is the prose author. The generator does not ask the model to infer a repository from a blind file dump.

## Commands

```bash
synap wiki status
synap wiki generate --incremental
synap wiki generate --full
synap wiki tree
synap wiki files
synap wiki file src/synap_git/indexer/wiki.py
synap wiki architecture
synap wiki flows
synap wiki concepts
synap wiki validate
```

Generation writes an exact tree, navigation, evidence, file explanations, and focused architecture/flow/concept pages under `.synap/wiki/`. `--incremental` compares SHA-256 source hashes from `generated/generation-manifest.json`; deleted file pages are removed and changed pages are regenerated. A model failure is reported and does not replace a valid explanatory page.

The L2 Semantic layer generates and maintains human-readable markdown documentation for files, modules, and overall project architecture under `.synap/wiki/`, synchronizing continuously with your Git commit history.

---

## Architecture & Lifecycle

Wiki documentation generation is decoupled from structural indexing to ensure that LLM API calls and network latencies never block CLI commands, Git hooks, or AST graph traversals.

```
                  ┌──────────────────────────────┐
                  │    Index File or Project     │
                  └──────────────┬───────────────┘
                                 │
                            (Enqueues)
                                 ▼
                     ┌──────────────────────┐
                     │  SQLite wiki_queue   │
                     └───────────┬──────────┘
                                 │
                   (Processed asynchronously by)
                                 ▼
                    ┌────────────────────────┐
                    │  Daemon Wiki Worker    │
                    └────────────┬───────────┘
                                 │
                            (Generates)
                                 ▼
                       ┌──────────────────┐
                       │  Markdown file   │
                       │  (.synap/wiki/)  │
                       └──────────────────┘
```

### 1. Asynchronous Queue Worker (`_wiki_worker_loop`)
When files are indexed or repository commits change:
* **Enqueuing:** New or modified files are added to the `wiki_queue` SQLite table with `"pending"` status.
* **Polling:** The background daemon worker polls `wiki_queue` for pending jobs every 5 seconds.
* **Worker Execution:** Fetches structural context (classes, functions, caller/callee edges), invokes the configured LLM provider, and writes formatted markdown under `.synap/wiki/<filepath>.md`.
* **Completion:** The queue entry is cleanly removed once the documentation file is written.

### 2. Failure Handling & `synap wiki retry`
If documentation generation encounters API rate limits, provider downtime, or network issues:
* **Retry Loop:** Tasks are re-queued with incremented `attempts` counters using exponential backoff:
  ```python
  delay = min(30, 2 ** attempts)
  ```
* **Permanent Failure:** After 3 consecutive failed attempts, the task status becomes `"failed"`.
* **Recovery Command:** All failed tasks can be re-queued in one step:
  ```bash
  synap wiki retry .
  ```

### 3. Git-Aware Invalidation
* Whenever a developer commits code changes, Synap's Git watcher runs `git diff-tree` to identify modified files.
* Existing wiki pages corresponding to modified files are flagged as stale and re-enqueued in `wiki_queue`.
* Deleted files have their associated `.md` wiki pages removed from `.synap/wiki/`.

### 4. Project-Level Synthesis Pages
In addition to file-level documentation, Synap generates high-level architectural synthesis pages during repository initialization:
* **`.synap/wiki/overview.md`**: Executive project overview, primary languages, directory structures, and entry points.
* **`.synap/wiki/architecture.md`**: Component interaction map, data flow pipelines, and subsystem dependencies.
* **`.synap/wiki/schema.md`**: Data models, schemas, and database entity relationships.

### 5. On-Demand Lazy Generation
If an agent or user requests a wiki page via CLI (`synap wiki show`), the REST API (`GET /wiki/{filepath}`), or an MCP tool before the background worker has processed it:
* `ensure_wiki_page` intercepts the request.
* If the page is missing or marked stale, it triggers synchronous generation on the fly so the caller immediately receives up-to-date documentation.

### 6. Local-model failure behavior
When no local LLM provider is configured or Ollama is unavailable, explanatory generation fails with an actionable error. Deterministic tree/navigation/evidence output may still be created, but existing explanatory pages are never replaced by generic placeholders. Retry after configuring the local model with `synap wiki generate --incremental`.

---

## CLI Management Commands

| Command | Purpose | Example |
| :--- | :--- | :--- |
| `synap wiki list` | List all generated wiki pages, sizes, and timestamps | `synap wiki list .` |
| `synap wiki show <path>` | Render a specific markdown page in the terminal | `synap wiki show src/engine.py .` |
| `synap wiki retry` | Re-queue all permanently failed tasks back to pending | `synap wiki retry .` |
