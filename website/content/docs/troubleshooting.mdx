# Troubleshooting Guide

This guide details actual error scenarios encountered in Synap and provides steps to resolve them.

---

## 1. SQLite Database Corruption

### Symptom
Errors stating `database disk image is malformed` or database connection timeouts.

### Root Cause
Unclean shutdowns, process termination during database write loops, or system restarts while write-ahead logs (WAL) are flushed.

### Solutions
* **Auto-Healing:** The background daemon automatically checks integrity using `PRAGMA quick_check`. If corruption is detected, the daemon deletes `.synap/synap.db`, `.synap/synap.db-wal`, and `.synap/synap.db-shm` and boots fresh.
* **Manual Rebuild:** Run the repair CLI command:
  ```bash
  synap repair .
  ```
  Or completely wipe the database directory and re-initialize:
  ```bash
  synap wipe .
  synap init .
  ```

---

## 2. Keyring Initialization Errors (CI / Headless Servers)

### Symptom
`setup` commands fail or cloud keys cannot be stored, reporting keyring errors.

### Root Cause
On headless Linux instances, Docker containers, or CI environments, keyring services (like DBus, GNOME Keyring, or KWallet) are absent.

### Solutions
* **Environment Variables:** Set keys directly in the terminal session:
  ```bash
  export SYNAP_OPENAI_API_KEY="sk-..."
  ```
* **Fallback Credentials File:** Save keys to `~/.synap/credentials`:
  ```ini
  SYNAP_OPENAI_API_KEY=sk-...
  ```
  Ensure strict permission settings are applied to prevent Synap from skipping the file:
  ```bash
  chmod 600 ~/.synap/credentials
  ```

---

## 3. Stale Daemon Heartbeat & PID Locks

### Symptom
Running `synap start` prints:
`Daemon started but did not report healthy status`
Or `synap doctor` reports a stale daemon heartbeat.

### Root Cause
The daemon process crashed or was force-terminated, leaving stale lock files in `.synap/daemon.pid` and `.synap/daemon_heartbeat.json`.

### Solutions
* Stop services and clear lockfiles:
  ```bash
  synap stop .
  ```
* If the lock files persist, manually remove them:
  ```bash
  rm .synap/daemon.pid
  rm .synap/daemon_heartbeat.json
  ```
  Restart the daemon:
  ```bash
  synap start .
  ```

---

## 4. Code Symbols Not Appearing in Retrieval

### Symptom
Search queries or MCP tools do not return symbols or code blocks for a specific file.

### Root Cause
* File type is unsupported.
* File exceeds `max_file_bytes` limit (default 1MB).
* File matches exclusions in `.gitignore`.
* File is flagged as binary (contains control characters or null bytes).

### Solutions
* Run `synap doctor` to confirm Tree-sitter parser status.
* Check file size and update limits in `~/.config/synap/config.toml`:
  ```toml
  max_file_bytes = 2000000
  ```

---

## 5. Stale or Failed Wiki Generations

### Symptom
Daemon startup prints:
`⚠ Found X permanently failed wiki pages. They will not be retried automatically.`

### Root Cause
An L2 documentation generation task failed 3 consecutive times (typically due to LLM rate limits or network issues), moving its status in `wiki_queue` to `"failed"`.

### Solutions
* **Manual Refresh:** Force dynamic lazy regeneration by requesting the page directly:
  ```bash
  synap wiki show src/your_file.py .
  ```
* **Trigger Re-Index:** Modify or save the file to trigger an incremental indexing pass, which re-enqueues the wiki task.
