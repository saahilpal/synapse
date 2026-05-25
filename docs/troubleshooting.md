# Troubleshooting Guide

This guide compiles solutions for common issues encountered during setup, runtime execution, and integration with VS Code/Antigravity IDE.

---

## 1. IDE Python Interpreter Binding Issues
**Symptom**: Antigravity IDE keeps prompting "Select Python Environment" or the PET (Python Environment Tools) daemon crashes repeatedly.

### Solution: Direct settings pinning
If the IDE fails to automatically bind the virtual environment, bypass the PET auto-discovery by adding the path directly to your workspace configuration:
1. Open or create `.vscode/settings.json` in your workspace root.
2. Add the following configurations to force the IDE to use the correct Python interpreter:
   ```json
   {
     "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
     "python.useEnvironmentsExtension": false,
     "python.analysis.typeCheckingMode": "strict"
   }
   ```
3. Restart the IDE. The warnings will disappear.

---

## 2. macOS Apple Silicon (M1/M2/M3/M4/M5) Specifics
**Symptom**: Virtual environments created via standard python packages fail to compile tree-sitter or watchdog.

### Solution: Use `uv` native compilation
`uv` automatically installs pre-compiled wheels matching your Apple Silicon architecture (aarch64). Ensure you are utilizing `uv`:
```bash
# Verify uv path is correct
which uv

# Sync environment using native flags
uv sync --all-extras --dev
```
If compile errors persist, ensure Xcode Command Line Tools are active:
```bash
xcode-select --install
```

---

## 3. SQLite "database is locked" errors
**Symptom**: Concurrent reads/writes during background daemon scans raise SQLite busy errors.

### Solution: Connection Timeout
Synapse is configured to run SQLite in WAL (Write-Ahead Logging) mode which supports parallel reads/writes. However, to handle lock contention on slower SSDs, all connections now utilize a default `timeout=30.0` parameter. 
Ensure your database path is local (not on a network share or NFS drive) to prevent file lock lockups.

---

## 4. Replay State Divergence
**Symptom**: Replaying transactions yields a `State Hash Mismatch` diagnostic warning.

### Solution: Clean local projection cache
If local context files are corrupted or modified by hand, they can drift from the transaction log. Force a reconstruction of active indexes:
```bash
# Force clear the projection caches
uv run synapse compact --dedup
```
Or delete the active cache database:
```bash
rm -rf .synapse/synapse.db
```
Then run the initialization command to replay from the event log:
```bash
uv run synapse init
```
This deterministically reconstructs your state from scratch.
