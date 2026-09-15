# Configuration Reference

Synap uses Pydantic Settings (`pydantic-settings` v2) for runtime configuration. Settings are automatically loaded from environment variables and an optional `config.toml` file.

---

## Configuration File Location

1. **Environment Override:** If the `SYNAP_CONFIG` environment variable is defined, Synap reads configuration from that absolute path.
2. **Default Path (XDG Compliant):**
   - **macOS / Linux:** `~/.config/synap/config.toml`
   - **Windows:** `%USERPROFILE%\.config\synap\config.toml`

---

## Configuration Fields

Every setting can be defined inside `config.toml` (top-level or under standard sections like `[llm]`) or as an environment variable prefixed with `SYNAP_` (e.g., `SYNAP_LOG_LEVEL=DEBUG`).

| Setting Key | Environment Variable | Type | Default | Description & Effect |
| :--- | :--- | :--- | :--- | :--- |
| `profile` | `SYNAP_PROFILE` | `string` | `"dev"` | Runtime profile: `"dev"`, `"test"`, or `"prod"`. Profile `"test"` forces `logging_mode="json"` and `log_level="DEBUG"`. |
| `mode` | `SYNAP_MODE` | `string` | `"active"` | Daemon mode: `"active"` or `"idle"`. In `"idle"` mode, Git change polling is paused. |
| `repository_path` | `SYNAP_REPOSITORY_PATH` | `string` | `"."` | Target repository directory to monitor and index. |
| `state_path` | `SYNAP_STATE_PATH` | `string` | `".synap"` | Root directory for local runtime data, SQLite DB, and logs. Resolved relative to `repository_path` if not absolute. |
| `sqlite_path` | `SYNAP_SQLITE_PATH` | `string` | `".synap/synap.db"` | Path to the SQLite database file. Defaults to `<state_path>/synap.db`. |
| `log_path` | `SYNAP_LOG_PATH` | `string` | `".synap/logs"` | Directory where rotating log files are saved. Defaults to `<state_path>/logs`. |
| `logging_mode` | `SYNAP_LOGGING_MODE` | `string` | `"human"` | Console logging format: `"human"` (Rich colored output) or `"json"` (structured JSON). |
| `log_level` | `SYNAP_LOG_LEVEL` | `string` | `"INFO"` | Minimum logging severity threshold: `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`. |
| `max_file_bytes` | `SYNAP_MAX_FILE_BYTES` | `integer` | `1000000` | Maximum file size in bytes to index (minimum `1024`). Files larger than this threshold are skipped. |
| `checkpoint_threshold`| `SYNAP_CHECKPOINT_THRESHOLD` | `float` | `0.60` | Ratio (0.0 to 1.0) of context window utilization triggering a checkpoint recommendation via `signal_low_context`. |
| `lesson_expiry_days` | `SYNAP_LESSON_EXPIRY_DAYS` | `integer` | `7` | Duration in days an approved lesson remains active before being marked `"expired"` by pruning. |
| `llm_provider` | `SYNAP_LLM_PROVIDER` | `string` | `null` | Generative provider: `"openai"`, `"gemini"`, `"anthropic"`, `"ollama"`, or `"openrouter"`. If null, runs in structural Mode A. |
| `llm_model` | `SYNAP_LLM_MODEL` | `string` | `null` | Specific model identifier for wiki generation and hybrid retrieval (e.g. `"gpt-4o"`). |
| `ollama_url` | `SYNAP_OLLAMA_URL` | `string` | `"http://127.0.0.1:11434"` | Endpoint URL for connecting to local Ollama daemon services. |
| `embedding_provider` | `SYNAP_EMBEDDING_PROVIDER` | `string` | `null` | Vector embedding provider: `"openai"`, `"gemini"`, `"ollama"`, `"anthropic"`, or `"openrouter"`. Defaults to `llm_provider` if omitted. |
| `embedding_model` | `SYNAP_EMBEDDING_MODEL` | `string` | `null` | Model identifier for embeddings (e.g. `"text-embedding-3-small"`, `"text-embedding-004"`). |
| `embedding_url` | `SYNAP_EMBEDDING_URL` | `string` | `null` | Custom base URL for embedding endpoints (e.g., custom Ollama host). Defaults to `ollama_url` if unset. |
| `mcp_host` | `SYNAP_MCP_HOST` | `string` | `"127.0.0.1"` | IP address binding for daemon services. |
| `mcp_port` | `SYNAP_MCP_PORT` | `integer` | `9876` | Diagnostic API and web UI HTTP port. Automatically seeks next available port if occupied. |
| `daemon_poll_interval_seconds` | `SYNAP_DAEMON_POLL_INTERVAL_SECONDS` | `float` | `2.0` | Interval in seconds between background Git commit polls. |
| `shutdown_timeout_seconds` | `SYNAP_SHUTDOWN_TIMEOUT_SECONDS` | `float` | `5.0` | Grace period in seconds allowed for active tasks to complete on daemon shutdown. |

---

## Example `config.toml`

```toml
profile = "dev"
log_level = "INFO"
max_file_bytes = 1000000
checkpoint_threshold = 0.60
lesson_expiry_days = 7

[llm]
llm_provider = "openai"
llm_model = "gpt-4o"

[embeddings]
embedding_provider = "openai"
embedding_model = "text-embedding-3-small"
```

---

## Credential Resolution Hierarchy

Synap connects securely to cloud LLM and embedding providers (OpenAI, Gemini, Anthropic, OpenRouter). API keys are resolved in the following priority order:

1. **System Keyring (Recommended):**
   - Stored in the native OS credential store: macOS Keychain, Linux Secret Service (libsecret/GNOME Keyring/KWallet), or Windows Credential Manager.
   - Automatically managed via `synap setup`.
   - Retrieved securely via `keyring.get_password("synap", "{provider}_api_key")`.

2. **Environment Variables:**
   - `SYNAP_OPENAI_API_KEY`
   - `SYNAP_GEMINI_API_KEY`
   - `SYNAP_ANTHROPIC_API_KEY`
   - `SYNAP_OPENROUTER_API_KEY`

3. **Fallback File (`~/.synap/credentials`):**
   - For headless CI/CD systems where no keyring service is running:
     ```ini
     SYNAP_OPENAI_API_KEY=sk-...
     SYNAP_GEMINI_API_KEY=AIza...
     SYNAP_ANTHROPIC_API_KEY=sk-ant-...
     SYNAP_OPENROUTER_API_KEY=sk-or-...
     ```
   - **Strict Security Rule:** On Unix systems, this file **must** have strict permissions (`chmod 600`). If group or world permissions are open, Synap will reject the file to prevent credential leaks.
