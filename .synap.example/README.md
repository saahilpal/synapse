# Example `.synap` Layout

Synap stores local repository intelligence and agent memory in `.synap/`. This directory is strictly ignored by Git.

```text
.synap/
  synap.db             # L1 (Code Graph) + L3 (Agent Memory) SQLite database
  daemon_heartbeat.json  # Active status and PID of the Synap daemon
  objects/               # Immutable file snapshots (content-addressed)
  logs/                  # Runtime logs
  wiki/                  # L2 (Knowledge Wiki) generated Markdown
    overview.md          # Project-level summary
    architecture.md      # System design and data flow
    modules/             # Module-level documentation
      [module].md
    agent/               # Rendered agent history
      decisions.md
      lessons.md
```
