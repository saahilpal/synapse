# Troubleshooting Synapse

Synapse is designed to be highly resilient, local-first, and append-only. When things go wrong, you have deep diagnostics available to inspect the state of your infrastructure.

## 1. Diagnostics & Health

If Synapse behaves unexpectedly, the first step is always to run the diagnostic tool:

```bash
synapse doctor .
```

This command:
- Checks the integrity of the Zlib Object Store.
- Validates the WAL-enabled SQLite Event Store.
- Verifies that all active structural nodes point to valid content hashes.

## 2. Common Issues

### The `.synapse` Folder is Missing
Synapse requires an initialized state folder in the root of your repository.
**Fix**: Ensure you have write permissions to the repository directory and run:
```bash
synapse init .
```

### SQLite Database Locks or Corruption
Synapse uses SQLite in Write-Ahead Log (WAL) mode. In the rare event of severe system-level corruption (e.g., hard power loss during a transaction commit), the database might become locked.
**Fix**: Because Synapse is append-only and hash-driven, you can always safely rebuild from scratch without losing repository code.
```bash
# Move the corrupted state
mv .synapse .synapse.backup

# Re-initialize
synapse init .
```

### Missing Structural Nodes
If a file exists in your repository but cannot be found in Synapse's search or MCP tools, it is likely being ignored by the scanner.
**Fix**:
1. Check if the file is ignored by `.gitignore` or `.synapseignore`.
2. Check if the file size exceeds the `SYNAPSE_MAX_FILE_BYTES` threshold.
3. Keep in mind that unsupported languages will produce a `FileNode` but will not yield detailed AST symbols (classes, functions).

### Stale AI Overlays
Because overlays are strictly bound to structural target hashes, if a file changes outside of Synapse's daemon watcher, the old overlay might linger briefly until the next scan.
**Fix**: Force an immediate invalidation scan:
```bash
synapse start . --force-scan
```

## 3. Performance Tuning

For exceptionally large monorepos, ingestion and memory might become bottlenecks.
- **Tune Exclusions**: Aggressively ignore generated output folders, `node_modules`, `target`, and `dist`.
- **Lower File Limits**: Decrease `SYNAPSE_MAX_FILE_BYTES` to skip large, low-value assets like minified bundle files.
- **Retrieval Bounding**: Ensure your agents are providing targeted structural queries. Broad queries (e.g., "Find everything") will hit hard traversal limits, returning a deterministic but truncated subgraph to protect token windows.
