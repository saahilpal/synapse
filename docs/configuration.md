# Configuration Reference

Synap uses Pydantic Settings for runtime configuration. It loads settings from environment variables and the global `config.toml` file.

---

## Configuration Location

1. **Environment Override:** If the `SYNAP_CONFIG` environment variable is defined, Synap reads configuration from that absolute path.
2. **Default Path:** By default, configuration is loaded from:
   * Unix/macOS: `~/.config/synap/config.toml`
   * Windows: `%USERPROFILE%\.config\synap\config.toml`

---

## Configuration Fields

Every setting can be specified as a key in `config.toml` (within the top-level namespace or nested under standard namespaces like `[llm]`) or as an environment variable prefixed with `SYNAP_` (e.g. `SYNAP_LOG_LEVEL`).

| Field Name | Type | Default | Description & Effect |
| :--- | :--- | :--- | :--- |
| `profile` | `string` | `"dev"` | Runtime profile: `"dev"`, `"test"`, or `"prod"`. Setting to `"test"` automatically configures logs to JSON format and level to `"DEBUG"`. |
| `mode` | `string` | `"active"` | Daemon state: `"active"` or `"idle"`. Idle mode pauses Git change sweeps. |
| `repository_path` | `string` | `"."` | Path to the repository root directory being monitored. |
| `state_path` | `string` | `".synap"` | Root directory for local database, cache objects, and logs. Resolved relative to `repository_path` if not absolute. |
| `sqlite_path` | `string` | `".synap/synap.db"` | Path to the SQLite database. |
| `object_path` | `string` | `".synap/objects"` | Directory where serialized objects are stored. |
| `log_path` | `string` | `".synap/logs"` | Directory where daemon log files are written. |
| `logging_mode` | `string` | `"human"` | Controls terminal logging format: `"human"` or `"json"`. |
| `log_level` | `string` | `"INFO"` | Minimum logging severity: `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`. |
| `max_file_bytes` | `integer` | `1000000` | Limits indexing to files smaller than this byte count to prevent parsing overhead. |
| `checkpoint_threshold` | `float` | `0.60` | Threshold ratio (0.0 to 1.0) of context window utilization. When reached, triggers a checkpoint recommendation. |
| `lesson_expiry_days` | `integer` | `7` | Number of days a behavioral memory lesson remains active before moving to the `"expired"` status. |
| `llm_provider` | `string` | `null` | Chosen generative AI service: `"openai"`, `"gemini"`, `"anthropic"`, `"ollama"`, `"openrouter"`. If null, runs in structural Mode A. |
| `llm_model` | `string` | `null` | Model identifier used for generative wiki entries and hybrid retrieval answers. |
| `embed_provider` | `string` | `null` | Provider for vector embeddings. Defaults to `llm_provider`. |
| `ollama_url` | `string` | `"http://127.0.0.1:11434"` | Endpoint URL for connecting to local Ollama daemon services. |
| `mcp_host` | `string` | `"127.0.0.1"` | Binding address for the MCP daemon service. |
| `mcp_port` | `integer` | `9876` | Diagnostic API and web UI server listening port. |
| `daemon_poll_interval_seconds` | `float` | `2.0` | Time interval in seconds between Git active commit change verification runs. |
| `shutdown_timeout_seconds` | `float` | `5.0` | Timeout period allowed for daemon server tasks to shut down gracefully before termination. |

---

## Credential Resolution Hierarchy

To call cloud LLMs (OpenAI, Gemini, Anthropic, OpenRouter), Synap requires API keys. It searches for keys sequentially using the following resolution order:

1. **System Keyring:** Resolves keys securely from the OS keyring backend (via `keyring.get_password("synap", "{provider}_api_key")`). Set during `synap setup`.
2. **Environment Variables:** Matches active environment keys:
   * `SYNAP_OPENAI_API_KEY`
   * `SYNAP_GEMINI_API_KEY`
   * `SYNAP_ANTHROPIC_API_KEY`
   * `SYNAP_OPENROUTER_API_KEY`
3. **Fallback Credentials File:** Reads keys from `~/.synap/credentials`.
   * **Security Rule:** On Unix systems, this file must have strict permissions (`chmod 600`) where group and public read access are completely blocked. If permissions are too open, the credentials fallback is skipped.
