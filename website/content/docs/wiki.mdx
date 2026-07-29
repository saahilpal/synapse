# L2 Wiki Engine

The L2 Semantic layer provides human-readable markdown documentation for files, modules, and overall project structure under `.synap/wiki/`.

---

## Architecture & Lifecycle

Wiki documentation generation is decoupled from structural indexing to prevent slow LLM API calls from blocking CLI tools or AST traversals.

```
                  ┌──────────────────────────────┐
                  │    Index File or Project     │
                  └──────────────┬───────────────┘
                                 │
                            (Enqueues)
                                 ▼
                     ┌──────────────────────┐
                     │ SQLite wiki_queue    │
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
When a file is parsed or project initialization runs, tasks are enqueued into the `wiki_queue` database table:
* **Polling:** The daemon worker polls the database queue every 5 seconds for new `"pending"` jobs.
* **Worker Execution:** Pulls a task, queries details, and invokes the configured LLM provider to draft technical details.
* **Cleanup:** Once completed, the queue record is deleted.

### 2. Exponential Backoff & Failures
If LLM generation fails (e.g. rate limit, connection timeout):
* **Retries:** The task is re-inserted into the queue with status `"pending"` and increments the `attempts` count.
* **Backoff delay:** Before retrying a previously failed task, the worker sleeps for an exponential duration:
  ```python
  delay = min(30, 2 ** attempts)
  ```
* **Permanent Failure:** After 3 failed attempts, the task is marked as `"failed"`. permanently failed wiki pages are not automatically retried and warning alerts are output on daemon start.

### 3. Lazy Caching Fallback
If a developer requests a wiki page via the CLI (`synap wiki show`), the REST API endpoint (`/wiki/{filepath}`), or the MCP server, and the file is missing or marked stale:
* Synap intercepts the call and runs `ensure_wiki_page` synchronously.
* The LLM provider is invoked immediately, and the generated markdown is written to disk before returning the response.

### 4. Structural Fallback Placeholder
If no LLM provider is configured (running in structural Mode A):
* `ensure_wiki_page` checks if the target markdown page exists.
* If missing, it writes a lightweight placeholder:
  ```markdown
  # <filepath>
  Structural mode only. No LLM configured.
  ```
* This prevents errors and ensures the client receives structured documentation output.
