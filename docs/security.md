# Security

Synap is designed with a "Security-First" approach for professional development environments.

## Secret Management

Synap **never** stores API keys or secrets in the repository or in plaintext configuration files.
1.  **System Keyring:** We use `python-keyring` to store secrets in your OS-native secure storage (macOS Keychain, Windows Credential Locker, or Secret Service).
2.  **Environment Variables:** As a secondary option, Synap respects `SYNAP_*_API_KEY` environment variables.

## Data Privacy

1.  **Local-First:** By default, Synap indices and structural data remain on your local machine in the `.synap` directory.
2.  **Ollama Support:** For maximum privacy, use [Ollama](https://ollama.com/) to perform embeddings and LLM reasoning entirely on your local hardware.
3.  **Telemetry:** Synap does **not** include any hidden telemetry or "phone-home" features.

## Supply Chain Security

- **Pinned Dependencies:** All production dependencies are pinned to specific versions in `pyproject.toml` and `uv.lock`.
- **Minimal Surface:** We avoid large, non-deterministic frameworks, relying instead on proven, single-purpose libraries like `tree-sitter` and `sqlite`.
