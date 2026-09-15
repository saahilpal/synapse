# Troubleshooting Guide

This guide details common operational and environment issues encountered when running Synap, their root causes, and verified resolutions.

---

## 1. SQLite Database Corruption

### Symptom
Errors stating `database disk image is malformed`, locks, or database connection timeouts.

### Root Cause
Unclean shutdowns, process termination during database write loops, or system restarts while SQLite write-ahead logs (`WAL`) are being synchronized.

### Solutions
* **Auto-Healing:** The background daemon automatically checks integrity on startup using `PRAGMA quick_check`. If corruption is detected, it archives the damaged file, deletes `.synap/synap.db-wal` and `.synap/synap.db-shm`, and rebuilds fresh.
* **Manual Repair:** Run the repair CLI command:
  ```bash
  synap repair . -y
  ```
* **Full Reset:** Wipe the database directory and re-initialize:
  ```bash
  synap wipe . -y
  synap init .
  ```

---

## 2. Keyring Initialization Errors (CI / Headless Servers)

### Symptom
`synap setup` fails or cloud keys cannot be stored, reporting `keyring.errors.NoKeyringError`.

### Root Cause
On headless Linux servers, Docker containers, or CI/CD runners, native desktop keyring services (DBus, GNOME Keyring, KWallet) are absent.

### Solutions
* **Environment Variables:** Set keys directly in the shell environment:
  ```bash
  export SYNAP_OPENAI_API_KEY="sk-..."
  export SYNAP_GEMINI_API_KEY="AIza..."
  export SYNAP_ANTHROPIC_API_KEY="sk-ant-..."
  export SYNAP_OPENROUTER_API_KEY="sk-or-..."
  ```
* **Fallback Credentials File:** Save keys to `~/.synap/credentials`:
  ```ini
  SYNAP_OPENAI_API_KEY=sk-...
  ```
  **Critical Security Requirement:** On Unix systems, set strict permissions:
  ```bash
  chmod 600 ~/.synap/credentials
  ```
  *If group or other read permissions exist, Synap will ignore the file for security.*

---

## 3. Stale Daemon Heartbeat & PID Locks

### Symptom
Running `synap start` prints:
`Daemon started but did not report healthy status`
Or `synap doctor` reports a stale daemon heartbeat.

### Root Cause
The daemon process crashed or was forcefully killed (`kill -9`), leaving orphan lock files behind in `.synap/daemon.pid` and `.synap/daemon_heartbeat.json`.

### Solutions
* Gracefully stop the service:
  ```bash
  synap stop .
  ```
* If lockfiles persist after stopping, remove them manually:
  ```bash
  rm -f .synap/daemon.pid .synap/daemon_heartbeat.json
  synap start .
  ```

---

## 4. Code Symbols Missing from Retrieval

### Symptom
Search queries or MCP tools do not return symbols or code blocks for specific files.

### Root Cause
* The file extension is not yet mapped in `parser/registry.py`.
* File size exceeds `max_file_bytes` (default: 1MB).
* File path is matched by `.gitignore` or default exclusions (`.venv`, `node_modules`, `dist`).
* File contains binary bytes or control characters exceeding 10% in the first 1KB.

### Solutions
* Run `synap doctor` to confirm parser registry health.
* Increase file size threshold in `~/.config/synap/config.toml`:
  ```toml
  max_file_bytes = 2000000
  ```
* Verify if the file is tracked by Git:
  ```bash
  git check-ignore -v <path-to-file>
  ```

---

## 5. Stale or Failed Wiki Generations

### Symptom
Daemon startup prints:
`⚠ Found X permanently failed wiki pages. They will not be retried automatically.`

### Root Cause
An L2 documentation task encountered 3 consecutive errors (such as API rate limits or network timeouts), transitioning its status in `wiki_queue` to `"failed"`.

### Solutions
* **Re-queue All Failed Tasks:** Use the built-in retry command:
  ```bash
  synap wiki retry .
  ```
* **On-Demand Single Page Refresh:** Force lazy generation by requesting the page directly:
  ```bash
  synap wiki show src/my_file.py .
  ```

---

## 6. MCP Client Connection Failures

### Symptom
Cursor, Windsurf, or Claude Desktop reports `Connection closed` or fails to discover MCP tools.

### Root Cause
* Standard output (`stdout`) contamination: Print statements or raw text written to stdout break JSON-RPC protocol parsing.
* Incorrect repository path or missing Python binary in IDE configuration.

### Solutions
* Run verification to test the MCP server over stdio:
  ```bash
  synap mcp verify .
  ```
* Regenerate the IDE configuration snippet:
  ```bash
  synap mcp config .
  ```
* Ensure all custom plugins or script wrappers route logs strictly to `stderr`.

---

## 7. macOS Developer Tools / Git License Agreement

### Symptom
Commands or test suites fail with:
`You have not agreed to the Xcode license agreements. Please run 'sudo xcodebuild -license'`

### Root Cause
macOS `/usr/bin/git` is an Xcode developer shim. When Xcode is updated, Git commands fail until the license agreement is reviewed.

### Solutions
* Agree to the license:
  ```bash
  sudo xcodebuild -license
  ```
* Alternatively, prioritize the standalone Command Line Tools binary:
  ```bash
  export PATH="/Library/Developer/CommandLineTools/usr/bin:$PATH"
  ```
