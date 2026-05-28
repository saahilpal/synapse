# L3 Behavioral Memory

The L3 layer represents stateful memory that allows AI coding agents to preserve progress across context refreshes and prevent repeating past development failures.

---

## 1. Context Checkpoints

Checkpoints store the state of active agent tasks to resume context seamlessly.

* **Checkpoints Fields:**
  * `checkpoint_id` (UUID string) — Primary key.
  * `branch` (string) — Active Git branch.
  * `commit_hash` (string) — Active Git OID.
  * `doing` (string) — Description of the active agent task.
  * `changed_files` (JSON array of strings) — File paths modified during the task.
  * `next_step` (string) — Intent or planned next step.
  * `blockers` (string) — Obstacles or errors encountered.
  * `created_at` (integer timestamp) — Creation time.
* **Periodic Checkpointing:** In addition to manual creation via the `checkpoint create` CLI command or MCP server, the runtime automatically generates a checkpoint every 10 commits to capture history.

---

## 2. Decision Log

Decisions allow agents to document design choices and architectural details.

* **Decisions Fields:**
  * `decision_id` (UUID string) — Primary key.
  * `branch` (string) — Active Git branch.
  * `commit_hash` (string) — Active Git OID.
  * `content` (string) — Rationale or description of the choice.
  * `context` (string) — File context or logs leading to the decision.
  * `agent_id` (string) — Identifier of the agent making the decision.
  * `created_at` (integer timestamp) — Logged time.

---

## 3. Agent Lessons (Trust & Lifecycle)

Lessons prevent agents from repeating mistakes. If a commit made by an agent breaks the build or tests, and the developer runs `git revert`, Synap detects the event and prompts a review.

### Lifecycle Diagram
```
        git revert
            │
            ▼
    ┌───────────────┐
    │    PENDING    │
    └───────┬───────┘
            │
      Human Review (Approve/Reject)
            ├──────────────────────┐
            ▼                      ▼
    ┌───────────────┐      ┌───────────────┐
    │   APPROVED    │      │   REJECTED    │
    └───────┬───────┘      └───────────────┘
            │
      Expiry Reached (Pruned hourly/manually)
            ▼
    ┌───────────────┐
    │    EXPIRED    │
    └───────────────┘
```

### The Lesson Lifecycle
1. **Automatic Detection:** The background daemon watches Git branch switches and commits. If the git change matches a revert type (e.g. `revert` detected using `git diff`), a new lesson is created in the SQLite database with status `"pending"`.
2. **Analysis Submission:** The agent (using the `submit_lesson_analysis` MCP tool) or the developer updates the lesson with an explanation of why the change failed.
3. **Governance & Approval:**
   * Pending lessons are inactive.
   * Developers must review lessons using `synap lessons review` or `synap lessons approve <id>`.
   * When approved, the lesson transitions to `"approved"`, and the `approval_actor` is recorded (e.g. `"cli_user"` or `"mcp_agent"`).
4. **Retrieval Gating:** During hybrid context retrieval, **only** approved, non-expired lessons are fetched. They are injected at the top of the context block as `# APPROVED SYSTEM MEMORY (CRITICAL: MUST ADHERE)` to instruct the model on what patterns to avoid.
5. **Memory Expiration & Pruning:** Approved lessons carry a lifetime defined by the `lesson_expiry_days` setting (default: 7 days). Stale lessons are pruned hourly by the daemon or manually via `synap memory prune`, transitioning them to the `"expired"` state.
