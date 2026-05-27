# Security Policy

Synap handles repository structure, source summaries, manual notes, and agent-facing context. Treat the local `.synap/` directory as sensitive development infrastructure.

## Security Principles

- Local-first by default.
- Parser output and Git state are structural truth.
- AI-generated overlays are annotations only.
- All durable objects carry provenance.
- Agent and API outputs are bounded and redacted.
- Derived indexes and projections are rebuildable.

## Threat Classes

- Prompt injection or context poisoning through Markdown and manual notes.
- Secret exposure through retrieved snippets, metadata, logs, or API responses.
- Unauthorized mutation through agent-facing tool calls.
- Path traversal in API filters or UI requests.
- Object-store or SQLite corruption.

## Controls

- `SecretRedactor` recursively scrubs common credential keys and token patterns.
- `InputValidator` clamps limits and enforces repository path containment.
- `IngestionSanitizer` rejects unsafe manual note content.
- SQLite runs locally in WAL mode.
- `synap doctor` verifies database health, object integrity, and replay diagnostics.

## Reporting Vulnerabilities

Until a formal security contact exists, open a private maintainer channel or create a minimal public issue that does not disclose exploit details. Include the affected command, interface, or storage path and the expected trust boundary.
