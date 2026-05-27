# Example `.synapse` Layout

Synapse stores local repository intelligence and agent memory in `.synapse/`. This directory is strictly ignored by Git.

```text
.synapse/
  synapse.db             # L1 (Code Graph) + L3 (Agent Memory) SQLite database
  daemon_heartbeat.json  # Active status and PID of the Synapse daemon
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
