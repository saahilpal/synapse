# Professional Git Workflow & Developer Experience

This guide documents the professional Git workflow, configurations, and custom CLI integrations designed to make collaborating on Synapse a seamless developer experience.

---

## 1. Local Git Custom Aliases

To make Synapse's temporal context engine feel like a native extension of Git, we have configured a set of repository-local Git aliases. Developers can invoke Synapse operations directly through standard `git` commands:

| Command | Action | Description |
|---|---|---|
| `git synapse-status` | `uv run synapse status` | Inspect status of the active context head, events count, and branch state. |
| `git synapse-timeline` | `uv run synapse timeline` | Reconstruct the temporal timeline of context mutations. |
| `git synapse-doctor` | `uv run synapse doctor` | Run full database, snapshot, and event log consistency audits. |
| `git synapse-lineage` | `uv run synapse lineage` | Walk the context DAG and verify lineage integrity (the context `fsck`). |
| `git synapse-diff <left> <right>` | `uv run synapse diff ...` | Generate a semantic diff between two context commits. |
| `git synapse-compact` | `uv run synapse compact` | Deduplicate historical logs and run cold compaction. |

These are stored in the local repository configuration under `.git/config` and do not pollute your global Git settings.

---

## 2. Automated Quality Assurance (Pre-commit Hooks)

To enforce execution correctness and prevent broken code from ever being committed, Synapse integrates Git `pre-commit` hooks. 

Upon running `git commit`, the hook automatically triggers:
1. **Ruff**: Lints source code and applies formatting checks.
2. **Mypy**: Performs static type audits over `src/` and `tests/` directories.

To ensure your local hook is active:
```bash
uv run pre-commit install
```

If you ever need to run a manual validation check over the whole repository:
```bash
uv run pre-commit run --all-files
```

---

## 3. Professional Git Performance Settings

To keep the repository clean and ensure merge conflicts are minimized, the following local options have been enabled:

- **Rebase Pulls** (`pull.rebase = true`): Avoids cluttering the tree with empty "Merge branch 'main'" commits, keeping history clean and linear.
- **Auto-Prune Fetches** (`fetch.prune = true`): Automatically deletes references to remote branches that have been deleted on GitHub.
- **Whitespace Rules** (`core.whitespace = trailing-space,space-before-tab`): Configures Git to warn when tabs are mixed with spaces or trailing whitespaces are introduced.

---

## 4. Open Source Commit Standards

We enforce the **Conventional Commits** standard to make our history readable and traceable. Commit messages must be prefixed with a structural label:

- `feat(...)`: A new user-facing feature (e.g. `feat(validation): add tristate validation`).
- `fix(...)`: A bug fix (e.g. `fix(sqlite): resolve multi-process database locks`).
- `docs(...)`: Documentation-only updates (e.g. `docs(hld): update AI boundaries`).
- `refactor(...)`: Restructuring code without changing functionality.
- `test(...)`: Adding or updating test cases.
