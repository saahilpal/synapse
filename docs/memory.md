# L3 Behavioral Memory

The L3 Behavioral Memory layer enables AI coding agents to preserve context across session resets, document architectural decisions, and prevent repeating past mistakes by automatically learning from Git reverts.

---

## 1. Context Checkpoints

Checkpoints store the state of active agent tasks to restore working context without token bloat.

### Data Schema
* `checkpoint_id` (UUID string) — Primary identifier.
* `branch` (string) — Active Git branch.
* `commit_hash` (string) — Active Git commit OID.
* `doing` (string) — High-level description of current work.
* `changed_files` (JSON array of strings) — File paths modified during the task.
* `next_step` (string) — Planned next implementation step.
* `blockers` (string) — Blockers, edge cases, or issues encountered.
* `created_at` (integer timestamp) — Creation timestamp.

### Creation & Automation
* **Agent Creation:** Coding agents save state via the `create_checkpoint` MCP tool or CLI `synap checkpoint create`.
* **Periodic Checkpointing:** The daemon automatically logs a checkpoint every 10 Git commits to capture project progression over time.
* **Restoration:** Restored via `restore_checkpoint` MCP tool or `synap checkpoint restore latest`.

---

## 2. Decision Log

Decisions allow agents and developers to record structural choices, library selections, and design rationales.

### Data Schema
* `decision_id` (UUID string) — Unique decision identifier.
* `branch` (string) — Associated Git branch.
* `commit_hash` (string) — Active Git commit hash.
* `content` (string) — Rationale or description of the architectural choice.
* `context` (string) — Code context, file paths, or issue references.
* `agent_id` (string) — Identifier of the agent or user making the decision.
* `created_at` (integer timestamp) — Timestamp when recorded.

### Querying Decisions
View logged architectural decisions using the CLI:
```bash
synap memory decisions . --limit 10
```
Or filter by a specific branch:
```bash
synap memory decisions . --branch feature/auth
```

---

## 3. Agent Lessons (Trust & Lifecycle)

Lessons prevent agents from repeating bad code patterns. If an agent commit breaks tests or production, and a developer executes `git revert`, Synap detects the revert and extracts a candidate lesson.

### Lesson Lifecycle Diagram
```
        git revert
            │
            ▼
    ┌───────────────┐
    │    PENDING    │ (Awaiting analysis & human approval)
    └───────┬───────┘
            │
      Human Review (Approve or Reject)
            ├──────────────────────┐
            ▼                      ▼
    ┌───────────────┐      ┌───────────────┐
    │   APPROVED    │      │   REJECTED    │
    └───────┬───────┘      └───────────────┘
            │
      Expiry Reached (Pruned hourly via lesson_expiry_days)
            ▼
    ┌───────────────┐
    │    EXPIRED    │
    └───────────────┘
```

### The 5-Phase Lifecycle
1. **Automatic Detection:** The background daemon monitors Git commit shifts. When a commit is identified as a revert, a lesson is added to the database with `"pending"` status.
2. **Analysis Submission:** The agent (via `submit_lesson_analysis` MCP tool) or developer provides root cause analysis explaining why the code failed and the rule to follow.
3. **Human Governance:**
   - Pending lessons remain inactive.
   - Developers review lessons using `synap lessons review` or approve via `synap lessons approve <id>`.
   - The approval actor is recorded (e.g. `"cli_user"`).
4. **Retrieval Gating:**
   - During hybrid search retrieval, **only approved, non-expired lessons** are injected.
   - They appear at the top of context packages as `# APPROVED SYSTEM MEMORY (CRITICAL: MUST ADHERE)`.
5. **Memory Expiration & Verification:**
   - Lessons remain valid for `lesson_expiry_days` (default: 7 days).
   - Stale lessons are pruned automatically by the daemon or manually via `synap memory prune`.
   - Run `synap memory verify` to ensure files referenced in approved lessons still exist in the repository:
     ```bash
     synap memory verify .
     ```

---

## CLI Memory Commands Quick Reference

| Command | Description |
| :--- | :--- |
| `synap memory status` | Displays counts of approved, pending, and expired lessons |
| `synap memory prune` | Purges expired lessons past their retention limit |
| `synap memory verify` | Detects dangling file references in approved lessons |
| `synap memory decisions` | Lists logged architectural decisions |
| `synap lessons list` | Lists all lessons with status filtering (`--status`) |
| `synap lessons approve <id>` | Approves a pending lesson |
| `synap lessons reject <id>` | Rejects and deactivates a lesson |
| `synap lessons review` | Interactive CLI wizard for reviewing pending lessons |
